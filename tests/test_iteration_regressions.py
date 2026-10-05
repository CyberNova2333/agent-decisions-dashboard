# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Iteration Regressions (I01 - I19)
基于 c9d3d42d 架构复审与回归测试集整理：
- I01: 干净的双端保存与重建往返检测结果必须为 consistent (F06)
- I02: 不同 request_id 携带相同文字的独立操作必须保留独立轮次 (F01)
- I03: 跨轮次复用相同用户意见在快照恢复后完整保留 (F01)
- I04: 纯元数据变更在数据库失败后重试可正常续做 (F02)
- I05: 业务数据落盘后 Revision 写入失败时，相同请求重试补齐快照与提交 (F02)
- I06: 落败的并发写入者 CAS 失败补偿绝不能用旧文件覆盖获胜者 (F03)
- I07: 全库回滚前置强校验非法快照路径，拒绝前不修改业务表或归档文件 (F04)
- I08: 全库回滚归档失败时完整保留源文件与数据库一致性 (F04)
- I09: 议题删除再恢复后单调递增高水位代次防旧并发令牌 ABA 复用 (F05)
- I10: 带有项目发布默认 .gitignore 的全新仓库正常提交数据库与决策 (F07)
- I11: create_topic 续做阶段同时修复元数据导出与补齐 Git 提交 (F08)
- I12: 外部直接修改权威文件决策结论与否决原因时阻断旧客户端覆盖 (F09)
- I13: 严格同源策略校验 Origin 端口与显式白名单，拒绝端口不符请求 (F10)
- I14: 相同 request_id 重放返回缓存结果且不重复追加轮次
- I15: 干净无讨论议题一致性检查通过
- I16: 无 ignore 配置的全新 Git 仓库正常提交
- I17: 创建阶段首个 INSERT 失败后相同请求重试成功恢复
- I18: 写入失败后携带不同 request_id 的请求绝不被冒认为前序续做
- I19: decisions.db 已被 Git 跟踪时新增忽略规则不影响后续提交
"""

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from core.config import Config
from core.decision_service import DecisionService, VersionConflictError

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestIterationRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dashboard-c9-audit-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = Config({"git_commit": {"enabled": False}}, self.root)
        self.s = DecisionService(self.config)

    def md(self, tid="a"):
        return self.config.decisions_dir / f"{tid}.md"

    def parsed(self, tid="a"):
        return self.s.parser.parse_markdown_file(self.md(tid))

    def seed(self, tid="a", **kwargs):
        data = {
            "title": f"Topic {tid}",
            "section": "Backend",
            "workflow_state": "decided",
            "decision_outcome": "accepted",
            "content_override": "Stable body"
        }
        data.update(kwargs)
        row = self.s.db.get_topic(tid)
        return self.s.save_topic(tid, data, expected_version=row["version"] if row else None)

    def rev(self):
        return self.s.db.get_revisions()[0]["rev_id"]

    def git(self, *cmd):
        return subprocess.run(["git", *cmd], cwd=self.root, capture_output=True, text=True, check=True).stdout.strip()

    def git_on(self, with_project_ignore=False):
        self.git("init")
        self.git("config", "user.name", "Audit")
        self.git("config", "user.email", "audit@example.invalid")
        (self.root / "README.md").write_text("isolated fixture\n", encoding="utf-8")
        if with_project_ignore:
            shutil.copyfile(REPO_ROOT / ".gitignore", self.root / ".gitignore")
        self.git("add", ".")
        self.git("commit", "-m", "baseline")
        self.config = Config({"git_commit": {"enabled": True}}, self.root)
        self.s = DecisionService(self.config)

    def test_I01_clean_roundtrip_should_report_consistent(self):
        self.seed(new_user_opinion="Please keep history", new_agent_reply="Understood", commit_message="First decision")
        first = self.s.recovery.check_consistency()
        self.s.recovery.rebuild_index_from_markdown()
        second = self.s.recovery.check_consistency()
        self.assertTrue(first["consistent"] and second["consistent"], "Ordinary unmodified round is reported as content drift even after rebuilding")

    def test_I02_distinct_requests_with_same_words_keep_two_rounds(self):
        data = {"title": "Repeated confirmation", "new_user_opinion": "Confirmed", "new_agent_reply": "Recorded"}
        self.s.save_topic("a", data, request_id="distinct-1")
        result = self.s.save_topic("a", data, expected_version=1, request_id="distinct-2")
        self.assertEqual(len(self.parsed()["rounds"]), 2, "Distinct operations with identical text must not collapse into one round")

    def test_I03_repeated_field_in_later_round_survives_snapshot_restore(self):
        self.seed(new_user_opinion="Please verify again", new_agent_reply="First answer", commit_message="Round one")
        self.seed(new_user_opinion="Please verify again", new_agent_reply="Second answer", commit_message="Round two")
        target = self.rev()
        self.s.restore_single_topic("a", target)
        after = self.parsed()["rounds"]
        self.assertEqual(after[1].get("user_opinion"), "Please verify again", "Value deduplication across all history drops the later round field")

    def test_I04_metadata_only_save_recovers_after_db_failure(self):
        self.seed()
        data = {"title": "Only title changed"}
        with patch.object(self.s.db, "upsert_topic", side_effect=sqlite3.OperationalError("injected database unavailable")):
            with self.assertRaises(sqlite3.OperationalError):
                self.s.save_topic("a", data, expected_version=1, request_id="metadata-only")
        result = None
        try:
            result = self.s.save_topic("a", data, expected_version=1, request_id="metadata-only")
        except Exception:
            pass
        self.assertIsNotNone(result, "Same metadata-only request cannot recover because heuristic requires a matching discussion round")

    def test_I05_receipt_survives_failure_after_db_before_revision(self):
        self.seed()
        data = {"title": "Committed to database", "new_user_opinion": "A genuine new operation"}
        with patch.object(self.s.db, "commit_revision", side_effect=sqlite3.OperationalError("injected revision write failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.s.save_topic("a", data, expected_version=1, request_id="revision-failure")
        result = None
        try:
            result = self.s.save_topic("a", data, expected_version=1, request_id="revision-failure")
        except Exception:
            pass
        self.assertIsNotNone(result, "Data applied but no durable operation receipt exists; identical retry is rejected instead of finishing history/export")

    def test_I06_losing_writer_must_not_restore_old_markdown_over_winner(self):
        self.seed()
        b_ready = threading.Event()
        a_done = threading.Event()
        original = os.replace
        outcomes = {}

        def replace(src, dst):
            if Path(dst) == self.md():
                name = threading.current_thread().name
                if name == "writer-A":
                    if not b_ready.wait(5):
                        raise RuntimeError("B did not reach file replacement")
                elif name == "writer-B":
                    b_ready.set()
                    if not a_done.wait(5):
                        raise RuntimeError("A did not finish")
            return original(src, dst)

        def write(who):
            threading.current_thread().name = "writer-" + who
            try:
                outcomes[who] = {
                    "status": "success",
                    "result": self.s.save_topic("a", {"title": "Winner " + who, "new_user_opinion": "Operation " + who}, expected_version=1, request_id="concurrent-" + who)
                }
            except Exception as e:
                outcomes[who] = {"status": type(e).__name__, "error": str(e)}
            finally:
                if who == "A":
                    a_done.set()

        with patch("core.decision_service.os.replace", side_effect=replace):
            with ThreadPoolExecutor(max_workers=2) as pool:
                fa = pool.submit(write, "A")
                fb = pool.submit(write, "B")
                fa.result(timeout=12)
                fb.result(timeout=12)
        disk = self.parsed()
        db = self.s.db.get_topic("a")
        self.assertEqual(outcomes["A"]["status"], "success")
        self.assertEqual(outcomes["B"]["status"], "VersionConflictError")
        self.assertEqual((disk["title"], disk["version"]), (db["title"], db["version"]), "Losing writer restored v1 file on top of winning v2 database")

    def test_I07_invalid_snapshot_rejected_before_any_state_mutation(self):
        self.seed()
        target = self.rev()
        self.seed("b")
        before_ids = [r["id"] for r in self.s.db.get_all_topics()]
        rev = self.s.db.get_revision_by_id(target)
        snap = json.loads(rev["snapshot_json"])
        snap["topics"][0]["id"] = "../outside-canary"
        with self.s.db.get_connection() as c:
            c.execute("UPDATE revisions SET snapshot_json=? WHERE rev_id=?", (json.dumps(snap), target))
            c.commit()
        canary = self.root / "outside-canary.md"
        canary.write_text("outside unchanged", encoding="utf-8")
        exc = None
        try:
            self.s.rollback_full(target)
        except Exception as e:
            exc = repr(e)
        after_ids = [r["id"] for r in self.s.db.get_all_topics()]
        self.assertIsNotNone(exc)
        self.assertEqual(canary.read_text(encoding="utf-8"), "outside unchanged")
        self.assertEqual(after_ids, before_ids, "Path is rejected only AFTER database is replaced and live documents archived")

    def test_I08_failed_archival_preserves_database_as_well_as_file(self):
        self.seed()
        target = self.rev()
        self.seed("b")
        before = self.s.db.get_topic("b")
        before_file = self.md("b").read_bytes()
        with patch("core.decision_service.shutil.move", side_effect=OSError("injected archive failure")):
            with self.assertRaises(OSError):
                self.s.rollback_full(target)
        after = self.s.db.get_topic("b")
        self.assertEqual(self.md("b").read_bytes(), before_file)
        self.assertIsNotNone(after, "Archival failure leaves file intact but has already deleted live database row")

    def test_I09_removed_topic_restoration_does_not_reuse_old_token(self):
        empty = self.s.db.commit_revision("BASELINE", "empty before topic")["rev_id"]
        self.seed()
        first = self.rev()
        self.seed(title="Old branch v2")
        self.seed(title="Old branch v3")
        self.s.rollback_full(empty)
        self.s.rollback_full(first)
        restored = self.s.db.get_topic("a")
        self.s.save_topic("a", {"title": "New branch v3"}, expected_version=restored["version"])
        res = None
        try:
            res = self.s.save_topic("a", {"title": "Stale old-v3 client"}, expected_version=3, request_id="stale-pre-delete")
        except Exception:
            pass
        self.assertIsNone(res, "Per-topic maximum was lost when topic disappeared; stale old-v3 client overwrites new branch")

    def test_I10_fresh_repo_with_shipped_ignore_can_commit(self):
        self.git_on(with_project_ignore=True)
        result = self.seed(new_user_opinion="First real decision")
        self.assertEqual(result["git_status"], "committed", "Shipped .gitignore excludes default DB that commit pipeline explicitly adds")

    def test_I11_create_replay_finishes_git_not_only_json(self):
        self.git_on()
        payload = {"id": "a", "title": "Create retry"}
        with patch.object(self.s.recovery, "sync_metadata_json", side_effect=OSError("injected export failure")):
            with self.assertRaises(OSError):
                self.s.create_topic(payload, request_id="create-pending")
        result = self.s.create_topic(payload, request_id="create-pending")
        self.assertEqual(result["git_status"], "committed", "Creation replay repairs export but skips pending Git phase")

    def test_I12_direct_outcome_edit_not_silently_overwritten(self):
        self.seed()
        before = self.md().read_text(encoding="utf-8")
        edited = before.replace('decision_outcome: "accepted"', 'decision_outcome: "rejected"').replace('rejection_reason: ""', 'rejection_reason: "External review rejected this"')
        self.assertNotEqual(edited, before)
        self.md().write_text(edited, encoding="utf-8")
        res = None
        exc = None
        try:
            res = self.s.save_topic("a", {"title": "Topic a", "workflow_state": "decided", "decision_outcome": "accepted", "new_user_opinion": "Stale editor comment"}, expected_version=1)
        except Exception as e:
            exc = repr(e)
        outcome = self.parsed()["decision_outcome"]
        self.assertTrue(exc is not None or outcome == "rejected", "Authority drift guard only compares title/body and overwrites changed decision outcome")

    def test_I13_wrong_port_origin_should_require_explicit_allowlist(self):
        import http.client
        from http.server import HTTPServer
        from core.server import DashboardServer, make_handler
        app = DashboardServer(self.config, web_dir=REPO_ROOT / "web")
        handler = make_handler(app)
        handler.log_message = lambda *x: None
        srv = HTTPServer(("127.0.0.1", 0), handler)
        app.port = srv.server_port
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        other = 1 if srv.server_port != 1 else 2
        origin = f"http://127.0.0.1:{other}"
        con = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
        try:
            con.request("POST", "/api/topic/a/save", json.dumps({"title": "Other origin"}), {"Origin": origin, "Content-Type": "application/json"})
            r = con.getresponse()
            status = r.status
            r.read().decode()
        finally:
            con.close()
            srv.shutdown()
            srv.server_close()
            thread.join()
        self.assertEqual(status, 403, "Default origin check ignores scheme/port; a different local web origin can write and read responses")

    def test_I14_same_request_id_replay_control(self):
        data = {"title": "Same retry", "new_user_opinion": "Round once"}
        self.s.save_topic("a", data, request_id="same")
        result = self.s.save_topic("a", data, request_id="same")
        self.assertTrue(result["is_replay"])
        self.assertEqual(len(self.parsed()["rounds"]), 1)

    def test_I15_clean_topic_without_discussion_control(self):
        self.seed()
        state = self.s.recovery.check_consistency()
        self.assertTrue(state["consistent"])

    def test_I16_fresh_git_without_ignore_control(self):
        self.git_on()
        result = self.seed()
        self.assertEqual(result["git_status"], "committed")

    def test_I17_incomplete_create_without_db_row_recovers(self):
        data = {"id": "a", "title": "Created then DB unavailable", "new_user_opinion": "Initial discussion"}
        with patch.object(self.s.db, "upsert_topic", side_effect=sqlite3.OperationalError("injected first INSERT failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.s.create_topic(data, request_id="creation-db-failure")
        result = None
        try:
            result = self.s.create_topic(data, request_id="creation-db-failure")
        except Exception:
            pass
        self.assertIsNotNone(result)

    def test_I18_changed_request_after_failed_write_is_not_assumed_same(self):
        self.seed()
        first = {"title": "Operation one", "new_user_opinion": "Confirmed", "new_agent_reply": "Agreed"}
        with patch.object(self.s.db, "upsert_topic", side_effect=sqlite3.OperationalError("injected DB failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.s.save_topic("a", first, expected_version=1, request_id="op-one")
        second = {"title": "Unrelated operation two", "new_user_opinion": "Confirmed", "new_agent_reply": "Agreed"}
        res = None
        try:
            res = self.s.save_topic("a", second, expected_version=1, request_id="op-two")
        except Exception:
            pass
        self.assertIsNone(res, "Content-based interruption detection treats a different request as continuation and overwrites first pending write")

    def test_I19_tracked_db_not_broken_by_ignore_control(self):
        self.git_on()
        shutil.copyfile(REPO_ROOT / ".gitignore", self.root / ".gitignore")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "add project ignore after DB is tracked")
        result = self.seed()
        self.assertEqual(result["git_status"], "committed")


if __name__ == "__main__":
    unittest.main()
