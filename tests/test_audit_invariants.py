# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - State-Invariant Regressions (R01 - R14)
验证恢复、审计、核验、重建与并发乐观锁的状态不变量与原子故障恢复能力：
- R01: 单议题恢复在 revision 插入失败时原子撤销业务变更并还原文件
- R02: 撤销创建在 audit/revision 记录失败时原子撤回数据库删除并还原文件
- R03: 恢复流程在元数据导出失败中断后可安全精确重试并成功断点续做
- R04: 恢复流程在末尾幂等写入失败后仍保留操作身份可精确重放
- R05: 单议题恢复在真正写入时严格核验 expected_version，防止并发写覆盖
- R06: 全库回滚在元数据导出部分写入中断时原子还原有效元数据文件
- R07: 缺失预期版本号的 prepared 保存重试绝不复用已被其他写入占用的版本令牌
- R08: 索引重建维护不会抹除中断保存请求的 last_request_id 归属标记
- R09: 验证结果记录在 Markdown 文件写入失败时原子回滚数据库状态
- R10: 项目已有历史后再导入新议题时自动建立该议题的编辑前初始基线快照
- R11: 全新项目首次创建议题前自动记录空态快照，支持撤回首个议题的创建
- R12: SQLite WAL 模式下全库回滚在文件失败时通过事务性备份安全原子还原
- R13: 正常单议题恢复与幂等重放保持其他议题数据完全一致
- R14: 单议题恢复在文件替换前注入故障不产生任何业务状态变更
"""

import contextlib
import http.client
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

from core.config import Config
from core.decision_service import DecisionService
from core.db import VersionConflictError
from core.server import DashboardServer, make_handler


class TestAuditInvariants(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="audit-inv-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, self.root)
        self.s = DecisionService(self.cfg)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True).stdout.strip()

    def enable_git(self):
        self.git("init", "-q")
        self.git("config", "user.name", "Audit Test")
        self.git("config", "user.email", "audit@example.invalid")
        self.git("commit", "--allow-empty", "-qm", "Initial fixture")
        self.cfg._data["git_commit"]["enabled"] = True

    def data(self, **kw):
        d = {
            "title": "Topic A",
            "section": "Backend",
            "workflow_state": "decided",
            "decision_outcome": "accepted",
            "content_override": "Stable body",
        }
        d.update(kw)
        return d

    def doc(self, t="a"):
        return self.cfg.decisions_dir / f"{t}.md"

    def save(self, t="a", **kw):
        r = self.s.db.get_topic(t)
        return self.s.save_topic(t, self.data(**kw), expected_version=r["version"] if r else None)

    def rev(self):
        return self.s.db.get_revisions(1)[0]["rev_id"]

    def state(self):
        return {
            "topics": [
                {
                    k: r.get(k)
                    for k in (
                        "id",
                        "title",
                        "version",
                        "discussion_json",
                        "last_request_id",
                        "implementation_state",
                    )
                }
                for r in self.s.db.get_all_topics()
            ],
            "files": {p.name: p.read_text(encoding="utf-8") for p in self.cfg.decisions_dir.glob("*.md")},
            "revisions": self.s.db.get_revisions(1000),
            "metadata": (
                self.cfg.metadata_json_path.read_text(encoding="utf-8")
                if self.cfg.metadata_json_path.exists()
                else None
            ),
        }

    def error(self, fn):
        try:
            return {"result": fn()}
        except Exception as e:
            return {"exception": type(e).__name__, "message": str(e)}

    def restore_setup(self):
        self.save(title="Correct v1")
        target = self.rev()
        self.save(title="Current v2")
        return target

    def test_R01_single_restore_revision_failure_preserves_consistency(self):
        target = self.restore_setup()
        before = self.state()
        with patch.object(self.s.db, "commit_revision", side_effect=sqlite3.OperationalError("injected revision INSERT failure")):
            r = self.error(lambda: self.s.restore_single_topic("a", target, expected_version=2, request_id="r01"))
        after = self.state()
        self.assertEqual(after, before, "File compensation restored old Markdown but DB remains restored at new version")

    def test_R02_undo_creation_revision_failure_preserves_consistency(self):
        self.save("b", title="Existing B")
        target = self.rev()
        self.save(title="New A")
        before = self.state()
        with patch.object(self.s.db, "commit_revision", side_effect=sqlite3.OperationalError("injected removal audit failure")):
            r = self.error(lambda: self.s.restore_single_topic("a", target, expected_version=1, request_id="r02"))
        after = self.state()
        self.assertEqual(after, before, "File was restored but DELETE of business row remains committed")

    def test_R03_restore_export_failure_is_safely_retriable(self):
        target = self.restore_setup()
        args = {"expected_version": 2, "request_id": "restore-export-once"}
        with patch.object(self.s.recovery, "sync_metadata_json", side_effect=OSError("injected export unavailable")):
            first = self.error(lambda: self.s.restore_single_topic("a", target, **args))
        middle = self.state()
        second = self.error(lambda: self.s.restore_single_topic("a", target, **args))
        after = self.state()
        self.assertNotIn("exception", second, "Exact replay now conflicts with its own committed version; no operation record exists")
        self.assertEqual(json.loads(after["metadata"])["topics"][0]["version"], self.s.db.get_topic("a")["version"])

    def test_R04_restore_result_record_failure_does_not_lose_request_identity(self):
        target = self.restore_setup()
        args = {"expected_version": 2, "request_id": "restore-cache-once"}
        with patch.object(self.s.db, "record_idempotency", side_effect=sqlite3.OperationalError("injected idempotency INSERT failure")):
            first = self.error(lambda: self.s.restore_single_topic("a", target, **args))
        second = self.error(lambda: self.s.restore_single_topic("a", target, **args))
        self.assertNotIn("exception", second, "Committed restoration cannot be replayed after final idempotency write failed")

    def test_R05_restore_rechecks_version_at_actual_write(self):
        target = self.restore_setup()
        real = self.s.db.get_revision_by_id
        once = False
        interleaved = {}

        def lookup(rev):
            nonlocal once
            if not once:
                once = True
                interleaved.update(self.save(title="Later valid v3"))
            return real(rev)

        with patch.object(self.s.db, "get_revision_by_id", side_effect=lookup):
            r = self.error(lambda: self.s.restore_single_topic("a", target, expected_version=2, request_id="restore-race"))
        self.assertEqual(self.s.db.get_topic("a")["title"], "Later valid v3", "Restore checks version only before reading snapshot; actual upsert is unconditional")

    def test_R06_full_rollback_export_partial_write_preserves_valid_export(self):
        target = self.restore_setup()
        self.save("b", title="B live")
        before = self.state()
        real = Path.write_text
        seen = False

        def write(p, txt, *args, **kw):
            nonlocal seen
            if p == self.cfg.metadata_json_path and not seen:
                seen = True
                real(p, '{"topics": [', encoding="utf-8")
                raise OSError("injected partial JSON write / disk full")
            return real(p, txt, *args, **kw)

        with patch.object(Path, "write_text", write):
            r = self.error(lambda: self.s.rollback_full(target))
        after = self.state()
        self.assertEqual(after, before, "Full rollback restores DB and Markdown, but leaves metadata.json truncated")

    def test_R07_prepared_retry_without_version_never_reuses_other_operation_token(self):
        self.save(title="Original v1")
        body = self.data(title="R1 target", new_user_opinion="R1 text")
        with patch.object(self.s, "_atomic_replace", side_effect=OSError("injected before first replace")):
            first = self.error(lambda: self.s.save_topic("a", body, request_id="unversioned-r1"))
        other = self.save(title="R2 correct")
        before = self.state()
        retry = self.error(lambda: self.s.save_topic("a", body, request_id="unversioned-r1"))
        after = self.state()
        self.assertTrue("exception" in retry or self.s.db.get_topic("a")["version"] > other["new_version"], "Different state accepted with already used v2; prepared baseline was not enforced")

    def test_R08_rebuild_keeps_prepared_operation_recoverable(self):
        self.save(title="Original")
        body = self.data(title="R1 after", new_user_opinion="Once")
        with patch.object(self.s.db, "commit_revision", side_effect=sqlite3.OperationalError("injected revision failure")):
            first = self.error(lambda: self.s.save_topic("a", body, expected_version=1, request_id="rebuild-r1"))
        before = self.state()
        rebuilt = self.s.recovery.rebuild_index_from_markdown()
        middle = self.state()
        retry = self.error(lambda: self.s.save_topic("a", body, expected_version=1, request_id="rebuild-r1"))
        self.assertNotIn("exception", retry, "Rebuild erases last_request_id ownership stored only on disposable index row")

    def test_R09_verification_file_failure_preserves_consistency(self):
        self.save(title="Unverified")
        before = self.state()
        with patch.object(self.s, "_atomic_replace", side_effect=OSError("injected verify file replace failure")):
            r = self.error(lambda: self.s.record_verification("a", "abc1234", "Reviewer", "Tests passed"))
        after = self.state()
        self.assertEqual(after, before, "Verification failed but DB is verified while Markdown remains not_started")

    def test_R10_later_imported_topic_has_pre_edit_baseline(self):
        self.save(title="Existing A")
        self.doc("b").write_text(
            self.s.parser.serialize_markdown(
                topic_id="b",
                title="Imported B correct",
                lifecycle_badge="🟢 已决策",
                decision_status="已定",
                impl_status="not_started",
                priority="普通",
                obj="通用系统",
                func="核心规范",
                core_content="Imported body",
                existing_rounds=[],
                workflow_state="decided",
                decision_outcome="accepted",
                version=1,
                section="Backend",
            ),
            encoding="utf-8",
        )
        rebuild = self.s.recovery.rebuild_index_from_markdown()
        self.save("b", title="First edit mistaken")
        vals = []
        for rev in self.s.db.get_revisions(1000):
            vals += [t["title"] for t in json.loads(self.s.db.get_revision_by_id(rev["rev_id"])["snapshot_json"])["topics"] if t["id"] == "b"]
        self.assertIn("Imported B correct", vals, "Baseline capture runs only when entire revision table is empty")

    def test_R11_fresh_first_creation_has_absence_baseline(self):
        web_dir = Path(__file__).resolve().parent.parent / "web"
        app = DashboardServer(self.cfg, web_dir=web_dir)
        before = app.db.get_revisions(1000)
        app.service.create_topic(dict(self.data(title="First accidental topic"), id="a"), request_id="first-create")
        after = app.db.get_revisions(1000)
        states = [json.loads(app.db.get_revision_by_id(r["rev_id"])["snapshot_json"])["topics"] for r in after]
        self.assertTrue(any(not any(t["id"] == "a" for t in topics) for topics in states), "Fresh project has no empty baseline before first creation")

    def test_R12_wal_full_rollback_failure_preserves_state(self):
        self.save(title="A v1")
        target = self.rev()
        keeper = sqlite3.connect(str(self.cfg.database_path))
        self.addCleanup(keeper.close)
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("PRAGMA wal_autocheckpoint=0")
        keeper.commit()
        keeper.execute("BEGIN")
        keeper.execute("SELECT * FROM topics").fetchall()

        self.save(title="A v2 current")
        before = self.state()
        wal_before = Path(str(self.cfg.database_path) + "-wal").exists()
        self.assertTrue(wal_before, "Test precondition: active WAL must exist")

        with patch("core.decision_service.os.replace", side_effect=OSError("injected restored Markdown replace failure")):
            r = self.error(lambda: self.s.rollback_full(target))
        after = self.state()
        self.assertEqual(after, before, "Copying main .db is not a transactionally complete WAL backup or restore")

    def test_R13_control_normal_restore_and_replay(self):
        target = self.restore_setup()
        self.save("b", title="B unchanged")
        before_b = self.s.db.get_topic("b")
        args = {"expected_version": 2, "request_id": "control-restore"}
        first = self.s.restore_single_topic("a", target, **args)
        middle = self.state()
        second = self.s.restore_single_topic("a", target, **args)
        after = self.state()
        self.assertEqual(after, middle)
        self.assertEqual(before_b, self.s.db.get_topic("b"))
        self.assertEqual(self.s.db.get_topic("a")["title"], "Correct v1")

    def test_R14_control_fault_before_restored_file_has_no_business_change(self):
        target = self.restore_setup()
        before = self.state()
        with patch("core.decision_service.os.replace", side_effect=OSError("injected before file replace")):
            r = self.error(lambda: self.s.restore_single_topic("a", target, expected_version=2, request_id="control-fail"))
        self.assertEqual(before, self.state())

    def test_N01_restore_resume_with_real_git_enabled(self):
        self.enable_git()
        target = self.restore_setup()
        head = self.git("rev-parse", "HEAD")
        args = {"expected_version": 2, "request_id": "git-restore"}
        with patch.object(self.s.recovery, "sync_metadata_json", side_effect=OSError("injected one-time export failure")):
            first = self.error(lambda: self.s.restore_single_topic("a", target, **args))
        retry = self.error(lambda: self.s.restore_single_topic("a", target, **args))
        self.assertNotIn("exception", retry, "Restore retry calls GitEngine with non-existent keyword arguments when enabled")
        self.assertEqual(retry["result"]["git_status"], "committed")

    def test_N02_undo_creation_export_failure_is_retriable(self):
        self.save("b", title="B baseline")
        target = self.rev()
        self.save(title="Accidental A")
        args = {"expected_version": 1, "request_id": "remove-retry"}
        with patch.object(self.s.recovery, "sync_metadata_json", side_effect=OSError("injected export failure after removal")):
            first = self.error(lambda: self.s.restore_single_topic("a", target, **args))
        middle = self.state()
        retry = self.error(lambda: self.s.restore_single_topic("a", target, **args))
        self.assertNotIn("exception", retry, "Exact removal retry conflicts with version 0 after successful DELETE")

    def test_N03_verification_revision_failure_restores_export_too(self):
        self.save(title="Unverified")
        before = self.state()
        with patch.object(self.s.db, "commit_revision", side_effect=sqlite3.OperationalError("injected verification audit failure")):
            response = self.error(lambda: self.s.record_verification("a", "abc1234", "Reviewer", "Tests passed"))
        after = self.state()
        self.assertEqual(after, before, "Verification compensates Markdown and DB, but metadata still claims verified at v2")

    def test_N04_restore_compensation_preserves_winning_file(self):
        target = self.restore_setup()
        real = os.replace
        once = False
        winner = {}

        def replace(src, dst):
            nonlocal once
            if Path(dst) == self.doc("a") and not once:
                once = True
                winner.update(self.save(title="Winner v3"))
            return real(src, dst)

        with patch("core.decision_service.os.replace", side_effect=replace):
            response = self.error(lambda: self.s.restore_single_topic("a", target, expected_version=2, request_id="restore-race"))
        self.assertEqual(self.s.db.get_topic("a")["title"], "Winner v3")
        self.assertEqual(self.s.parser.parse_markdown_file(self.doc("a"))["title"], "Winner v3", "CAS rejects loser but stale byte compensation overwrites winner file")

    def test_N05_changed_precondition_cannot_reuse_allocated_token(self):
        self.save(title="Start v1")
        body = self.data(title="R1 target", new_user_opinion="R1 opinion")
        with patch.object(self.s, "_atomic_replace", side_effect=OSError("injected before first file replace")):
            first = self.error(lambda: self.s.save_topic("a", body, expected_version=1, request_id="request-r1"))
        other = self.save(title="R2 wins v2")
        retry = self.error(lambda: self.s.save_topic("a", body, expected_version=2, request_id="request-r1"))
        self.assertTrue("exception" in retry or self.s.db.get_topic("a")["version"] > other["new_version"], "Different operation content accepted with same previously-used v2")

    def test_N06_undo_creation_checks_version_at_delete(self):
        self.save("b", title="Before A")
        target = self.rev()
        self.save(title="A v1")
        real = self.s.db.get_revision_by_id
        once = False
        winner = {}

        def lookup(r):
            nonlocal once
            if not once:
                once = True
                winner.update(self.save(title="A later v2"))
            return real(r)

        with patch.object(self.s.db, "get_revision_by_id", side_effect=lookup):
            response = self.error(lambda: self.s.restore_single_topic("a", target, expected_version=1, request_id="remove-race"))
        self.assertIsNotNone(self.s.db.get_topic("a"), "Undo-creation DELETE has no version predicate and removes a later edit")

    def test_N07_completed_restore_cannot_alias_another_operation(self):
        target = self.restore_setup()
        different_target = self.rev()
        args = {"expected_version": 2, "request_id": "same-id"}
        with patch.object(self.s.recovery, "sync_metadata_json", side_effect=OSError("injected export fail")):
            first = self.error(lambda: self.s.restore_single_topic("a", target, reason="Restore v1", **args))
        retry = self.error(lambda: self.s.restore_single_topic("a", different_target, reason="Different target", **args))
        self.assertIn("exception", retry, "last_request_id-only resumption accepts SAME key with DIFFERENT restore target")

    def test_N08_process_exit_does_not_lose_restore_audit(self):
        repo_path = Path(__file__).resolve().parent.parent
        target = self.restore_setup()
        code = '''import sys, os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from core.config import Config
from core.decision_service import DecisionService
s = DecisionService(Config({'git_commit': {'enabled': False}}, Path(sys.argv[2])))
with patch.object(s.db, 'commit_revision', side_effect=lambda **kw: os._exit(86)):
    s.restore_single_topic('a', int(sys.argv[3]), expected_version=2, request_id='crashed-restore')
'''
        r = subprocess.run([sys.executable, "-c", code, str(repo_path), str(self.root), str(target)], capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 86, "Crash injection must be reached")
        restarted = DashboardServer(self.cfg, web_dir=repo_path / "web")
        retry = self.error(lambda: restarted.service.restore_single_topic("a", target, expected_version=2, request_id="crashed-restore"))
        self.assertTrue(any(x["action_type"] == "TOPIC_RESTORE" for x in self.s.db.get_revisions(1000)), "Restarted operation reports success without ever recording the restored state in history")

    def test_N09_control_normal_restore_git_and_replay(self):
        self.enable_git()
        target = self.restore_setup()
        args = {"expected_version": 2, "request_id": "normal-restore"}
        first = self.s.restore_single_topic("a", target, **args)
        middle = self.state()
        replay = self.s.restore_single_topic("a", target, **args)
        self.assertEqual(first["git_status"], "committed")
        self.assertEqual(self.state(), middle)

    def test_N10_control_cancel_before_effects(self):
        target = self.restore_setup()
        before = self.state()
        with patch("core.decision_service.os.replace", side_effect=OSError("injected before replace")):
            r = self.error(lambda: self.s.restore_single_topic("a", target, expected_version=2, request_id="fail-before-write"))
        self.assertEqual(self.state(), before)

    def test_N11_header_precondition_change_is_not_new_content_at_old_token(self):
        repo_path = Path(__file__).resolve().parent.parent
        self.save(title="Start v1")
        app = DashboardServer(self.cfg, web_dir=repo_path / "web")
        handler = make_handler(app)
        handler.log_message = lambda *x: None
        srv = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()

        def post(version):
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
            try:
                conn.request("POST", "/api/topic/a/save", json.dumps(self.data(title="Request R1", new_user_opinion="R1")), {"Content-Type": "application/json", "X-Request-ID": "header-r1", "X-Expected-Version": str(version)})
                r = conn.getresponse()
                return {"status": r.status, "body": json.loads(r.read())}
            finally:
                conn.close()

        try:
            with patch.object(app.service, "_atomic_replace", side_effect=OSError("injected before R1 file replace")):
                first = post(1)
            winner = self.save(title="Request R2")
            retry = post(2)
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join()

        self.assertTrue(retry["status"] != 200 or retry["body"].get("new_version", 0) > winner["new_version"], "HTTP header path accepts R1 with reused v2 despite R2 already having v2")


if __name__ == "__main__":
    unittest.main()
