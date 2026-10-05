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
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import Config
from core.decision_service import DecisionService
from core.db import VersionConflictError
from core.server import DashboardServer


class TestAuditInvariants(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="audit-inv-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, self.root)
        self.s = DecisionService(self.cfg)

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


if __name__ == "__main__":
    unittest.main()
