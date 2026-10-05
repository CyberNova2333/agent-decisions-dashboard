# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Undo Regressions (U01 - U15)
验证单议题精准恢复、撤销创建、版本乐观锁防护、幂等安全重放、
原子故障隔离回滚与历史可见性：
- U01: 正常单议题恢复不影响其他议题数据与全局历史链
- U02: 首次创建可通过回溯至未创建快照执行撤销，不重置其他议题
- U03: 携带过期版本号执行恢复被 409 拒绝，防止覆盖后续工作
- U04: 相同恢复请求具有幂等性，重试不重复生成版本或快照
- U05: 单议题恢复文件写入失败时不破坏数据库与快照一致性
- U06: 全库回滚文件写入失败时原子还原，不残留数据库不一致
- U07: 全库回滚数据库执行失败时原子撤回文件归档
- U08: prepared 状态重试不会误认其他操作分配的代次为自身写入
- U09: prepared 状态在文件写入前失败重试不误去重相同内容的讨论轮次
- U10: 重新创建相同 ID 议题接入历史最高版本序列，杜绝复用旧版本并发令牌
- U11: 外部直接修改 Markdown 讨论内容在后续普通保存与快照恢复中被完整保留
- U12: 恢复接口受控透传并暴露 Git 提交失败状态
- U13: 历史查询接口支持按议题过滤与分页，使旧版本状态在多次全局提交后仍可触达
- U14: 系统启动导入的基线状态被记录为初始快照，支持撤回首次决策
- U15: 误操作单议题恢复后可通过后续快照重新回退与时间旅行
"""

import contextlib
import http.client
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

from core.config import Config
from core.decision_service import DecisionService
from core.git_engine import GitCommitResult
from core.server import DashboardServer, make_handler


class TestUndoRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="test-undo-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, self.root)
        self.s = DecisionService(self.cfg)

    def doc(self, topic_id="a") -> Path:
        return self.cfg.decisions_dir / f"{topic_id}.md"

    def parsed(self, topic_id="a"):
        return self.s.parser.parse_markdown_file(self.doc(topic_id))

    def data(self, **kw):
        d = {
            "title": "Topic A",
            "section": "Backend",
            "workflow_state": "decided",
            "decision_outcome": "accepted",
            "content_override": "Stable body"
        }
        d.update(kw)
        return d

    def save(self, topic_id="a", **kw):
        r = self.s.db.get_topic(topic_id)
        return self.s.save_topic(topic_id, self.data(**kw), expected_version=r["version"] if r else None)

    def rev(self) -> int:
        return self.s.db.get_revisions()[0]["rev_id"]

    def state(self):
        return {
            "topics": [{k: t[k] for k in ("id", "title", "version", "discussion_json")} for t in self.s.db.get_all_topics()],
            "files": {p.name: p.read_text(encoding="utf-8") for p in self.cfg.decisions_dir.glob("*.md")},
            "revisions": len(self.s.db.get_revisions(limit=10000))
        }

    @contextlib.contextmanager
    def http(self):
        app = DashboardServer(self.cfg, web_dir=Path(__file__).resolve().parent.parent / "web")
        app.service = self.s
        app.db = self.s.db
        handler = make_handler(app)
        handler.log_message = lambda *x: None
        srv = HTTPServer(("127.0.0.1", 0), handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            yield srv
        finally:
            srv.shutdown()
            srv.server_close()
            th.join()

    def request(self, srv, path, data=None):
        c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
        c.request(
            "POST" if data is not None else "GET",
            path,
            json.dumps(data) if data is not None else None,
            {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{srv.server_port}"}
        )
        r = c.getresponse()
        v = {"status": r.status, "body": json.loads(r.read().decode("utf-8"))}
        c.close()
        return v

    def test_U01_normal_single_restore_preserves_other_topic_and_history(self):
        self.save(title="A before", new_user_opinion="Approved before")
        target = self.rev()
        self.save(title="A mistake")
        self.save("b", title="B unrelated new work")
        b_before = self.s.db.get_topic("b")
        b_bytes = self.doc("b").read_bytes()
        hist = len(self.s.db.get_revisions())
        res = self.s.restore_single_topic("a", target)
        self.assertEqual(self.s.db.get_topic("a")["title"], "A before")
        self.assertEqual(self.s.db.get_topic("b"), b_before)
        self.assertEqual(self.doc("b").read_bytes(), b_bytes)
        self.assertEqual(len(self.s.db.get_revisions()), hist + 1)
        self.assertEqual(self.s.db.get_revisions()[0]["action_type"], "TOPIC_RESTORE")

    def test_U02_first_creation_can_be_undone_without_resetting_other_topics(self):
        self.save("b", title="Existing B")
        before = self.rev()
        self.save(title="Accidental new topic")
        self.save("b", title="B later valid work")
        res = self.s.restore_single_topic("a", before)
        self.assertIsNone(self.s.db.get_topic("a"))
        self.assertFalse(self.doc("a").exists())
        self.assertIsNotNone(self.s.db.get_topic("b"))

    def test_U03_stale_restore_must_reject_before_overwriting_later_work(self):
        self.save(title="A v1")
        target = self.rev()
        self.save(title="Mistake v2")
        observed_version = 2
        self.save(title="Unseen correct v3")
        with self.http() as srv:
            r = self.request(srv, "/api/topic/a/restore", {"rev_id": target, "expected_version": observed_version, "request_id": "stale-undo"})
        self.assertEqual(r["status"], 409)

    def test_U04_same_restore_request_is_idempotent(self):
        self.save(title="A v1")
        target = self.rev()
        self.save(title="A v2")
        body = {"rev_id": target, "expected_version": 2, "request_id": "undo-once"}
        with self.http() as srv:
            first = self.request(srv, "/api/topic/a/restore", body)
            middle = self.state()
            second = self.request(srv, "/api/topic/a/restore", body)
        self.assertEqual(self.state(), middle)

    def test_U05_single_restore_file_failure_does_not_commit_db_only(self):
        self.save(title="Before")
        target = self.rev()
        self.save(title="Current")
        before = self.state()
        with patch("core.decision_service.os.replace", side_effect=PermissionError("injected cannot replace restored Markdown")):
            with self.assertRaises(PermissionError):
                self.s.restore_single_topic("a", target)
        after = self.state()
        self.assertEqual(after, before)

    def test_U06_full_restore_file_failure_does_not_commit_db_only(self):
        self.save(title="Before")
        target = self.rev()
        self.save(title="Current")
        before = self.state()
        with patch("core.decision_service.os.replace", side_effect=OSError("injected disk write failure")):
            with self.assertRaises(OSError):
                self.s.rollback_full(target)
        after = self.state()
        self.assertEqual(after, before)

    def test_U07_full_restore_db_failure_unwinds_archival(self):
        self.save()
        target = self.rev()
        self.save("b", title="Valid B")
        before = self.state()
        with patch.object(self.s.db, "rollback_revision", side_effect=sqlite3.OperationalError("injected database failure after archival")):
            with self.assertRaises(sqlite3.OperationalError):
                self.s.rollback_full(target)
        after = self.state()
        self.assertEqual(after, before)

    def test_U08_prepared_retry_cannot_claim_another_operations_allocated_version(self):
        self.save(title="Base")
        a = self.data(title="Operation A", new_user_opinion="A opinion")
        b = self.data(title="Operation B", new_user_opinion="B opinion")
        with patch("core.decision_service.os.replace", side_effect=OSError("injected before first authority replacement")):
            with self.assertRaises(OSError):
                self.s.save_topic("a", a, expected_version=1, request_id="op-A")
        winner = self.s.save_topic("a", b, expected_version=1, request_id="op-B")
        try:
            self.s.save_topic("a", a, expected_version=1, request_id="op-A")
        except Exception:
            pass
        self.assertEqual(self.parsed()["title"], self.s.db.get_topic("a")["title"])

    def test_U09_prepared_failure_before_file_does_not_deduplicate_prior_identical_round(self):
        data = self.data(new_user_opinion="Confirmed", new_agent_reply="Recorded", commit_message="Confirm")
        self.s.save_topic("a", data, request_id="first-operation")
        with patch("core.decision_service.os.replace", side_effect=OSError("injected before second operation file write")):
            with self.assertRaises(OSError):
                self.s.save_topic("a", data, expected_version=1, request_id="second-operation")
        res = self.s.save_topic("a", data, expected_version=1, request_id="second-operation")
        rounds = self.parsed()["rounds"]
        self.assertEqual(len(rounds), 2)

    def test_U10_recreate_same_id_must_not_reuse_version_token(self):
        empty = self.s.db.commit_revision("INIT", "Empty baseline")["rev_id"]
        self.save(title="Old v1")
        self.save(title="Old v2")
        self.save(title="Old v3")
        self.s.rollback_full(empty)
        created = self.s.create_topic(dict(self.data(title="Recreated A"), id="a"), request_id="recreate")
        self.assertGreater(created["new_version"], 3)

    def test_U11_manual_discussion_change_is_not_lost_by_ordinary_save(self):
        self.save(new_user_opinion="Original opinion", new_agent_reply="Original answer")
        p = self.doc()
        p.write_text(p.read_text(encoding="utf-8").replace("Original opinion", "Manually corrected opinion"), encoding="utf-8")
        self.save(title="Ordinary new save", new_user_opinion="Next opinion")
        target = self.rev()
        self.s.restore_single_topic("a", target)
        self.assertIn("Manually corrected opinion", self.doc().read_text(encoding="utf-8"))

    def test_U12_restore_must_report_git_failure(self):
        self.save(title="Before")
        target = self.rev()
        self.save(title="Current")
        with patch.object(self.s.git, "commit_decision", return_value=GitCommitResult(success=False, status="git_error", message="injected Git commit failure")):
            res = self.s.restore_single_topic("a", target)
        self.assertEqual(res.get("git_status"), "git_error")

    def test_U13_history_api_keeps_per_topic_previous_state_reachable(self):
        self.save(title="A correct")
        target = self.rev()
        self.save(title="A mistake")
        for i in range(31):
            self.save("b", title=f"B work {i}")
        with self.http() as srv:
            r = self.request(srv, "/api/git/log?topic_id=a&limit=100&offset=0")
        ids = [x["rev_id"] for x in r["body"]["revisions"]]
        self.assertIn(target, ids)

    def test_U14_imported_baseline_is_available_to_undo_first_decision(self):
        self.cfg.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.doc().write_text(
            self.s.parser.serialize_markdown(
                topic_id="a",
                title="Imported correct baseline",
                lifecycle_badge="🟢 已决策",
                decision_status="已定",
                impl_status="not_started",
                priority="普通",
                obj="通用系统",
                func="核心规范",
                core_content="Original imported text",
                existing_rounds=[],
                workflow_state="decided",
                decision_outcome="accepted",
                version=1,
                section="Backend"
            ),
            encoding="utf-8"
        )
        app = DashboardServer(self.cfg, web_dir=Path(__file__).resolve().parent.parent / "web")
        imported = app.db.get_topic("a")
        app.service.save_topic("a", self.data(title="First decision was wrong"), expected_version=imported["version"], request_id="first-after-import")
        revs = app.db.get_revisions()
        snapshot_titles = []
        for r in revs:
            snap = json.loads(app.db.get_revision_by_id(r["rev_id"])["snapshot_json"])
            snapshot_titles.extend(t["title"] for t in snap["topics"] if t["id"] == "a")
        self.assertIn("Imported correct baseline", snapshot_titles)

    def test_U15_prior_state_can_be_recovered_after_an_accidental_restore(self):
        self.save(title="A first")
        first = self.rev()
        self.save(title="A second")
        second = self.rev()
        self.save("b", title="B unaffected")
        before_b = self.s.db.get_topic("b")
        self.s.restore_single_topic("a", first)
        self.s.restore_single_topic("a", second)
        self.assertEqual(self.s.db.get_topic("a")["title"], "A second")
        self.assertEqual(self.s.db.get_topic("b"), before_b)
        self.assertIsNotNone(self.s.db.get_revision_by_id(first))
        self.assertIsNotNone(self.s.db.get_revision_by_id(second))


if __name__ == "__main__":
    unittest.main()
