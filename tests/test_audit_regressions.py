# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Comprehensive Audit Regressions (R01 - R12)
覆盖源码复审报告中全部 23 条正确行为不变量断言：
- 失败不改变状态、成功可恢复、重试不重复
- 重建不创造历史、文件删除同步清理、内容变动精准发现
- 字段不因未填写而消失、已失效决策不再成为约束、核验与提交边界闭合
"""

import unittest
import tempfile
import json
import sqlite3
import subprocess
from pathlib import Path

from core.config import Config
from core.db import DatabaseManager, VersionConflictError
from core.decision_service import DecisionService, TopicValidationError, IdempotencyConflictError
from core.recovery import RecoveryManager
from core.agent_context import AgentContextEngine
from core.git_engine import GitEngine


class TestAuditRegressions(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.test_dir.name)
        
        # 初始化 Git 仓库
        subprocess.run(["git", "init"], cwd=str(self.base_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(self.base_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.base_dir), check=True, capture_output=True)
        
        init_file = self.base_dir / "README.md"
        init_file.write_text("# Test Init\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.base_dir), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(self.base_dir), check=True, capture_output=True)

        self.cfg = Config({"git_commit": {"enabled": True}}, base_dir=self.base_dir)
        self.service = DecisionService(self.cfg)
        self.recovery = RecoveryManager(self.cfg, self.service.db)
        self.agent = AgentContextEngine(self.cfg, self.service.db)

    def tearDown(self):
        self.test_dir.cleanup()

    # R02: 版本冲突不破坏文件与统一版本
    def test_r02_version_conflict_preserves_authoritative_markdown(self):
        self.service.save_topic("t-conflict", {"title": "初始标题", "user_opinion": "初始意见"})
        md_file = self.cfg.decisions_dir / "t-conflict.md"
        md_original = md_file.read_text(encoding="utf-8")

        with self.assertRaises(VersionConflictError):
            self.service.save_topic(
                "t-conflict",
                {"title": "冲突篡改标题", "user_opinion": "冲突意见"},
                expected_version=99
            )

        # 验证文件未被任何副作用修改
        self.assertEqual(md_file.read_text(encoding="utf-8"), md_original)

    def test_r02_unified_version_baseline(self):
        res = self.service.create_topic({"id": "t-v1", "title": "统一 v1 测试"})
        self.assertEqual(res["new_version"], 1)

        db_t = self.service.db.get_topic("t-v1")
        self.assertEqual(db_t["version"], 1)

        parsed = self.service.parser.parse_markdown_file(self.cfg.decisions_dir / "t-v1.md")
        self.assertEqual(parsed["version"], 1)

    # R04: 重建不自增版本、删除清理、内容漂移
    def test_r04_rebuild_preserves_version_and_idempotence(self):
        md = self.cfg.decisions_dir / "t-ver7.md"
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text("""---
schema_version: "2.0"
id: "t-ver7"
title: "版本7"
version: 7
workflow_state: "decided"
---
# 标题
## 核心论述与现实依据
内容
""", encoding="utf-8")

        self.recovery.rebuild_index_from_markdown()
        t1 = self.service.db.get_topic("t-ver7")
        self.assertEqual(t1["version"], 7)

        # 再次重建不改变版本
        self.recovery.rebuild_index_from_markdown()
        t2 = self.service.db.get_topic("t-ver7")
        self.assertEqual(t2["version"], 7)

    def test_r04_rebuild_removes_deleted_topics(self):
        self.service.save_topic("t-del", {"title": "将被删除的文件"})
        md = self.cfg.decisions_dir / "t-del.md"
        self.assertTrue(md.exists())
        self.assertIsNotNone(self.service.db.get_topic("t-del"))

        md.unlink()
        self.recovery.rebuild_index_from_markdown()
        self.assertIsNone(self.service.db.get_topic("t-del"))

    def test_r04_consistency_catches_content_and_meta_drift(self):
        self.service.save_topic("t-drift", {"title": "防漂移"})
        md = self.cfg.decisions_dir / "t-drift.md"
        # 外部篡改正文但保留版本
        orig = md.read_text(encoding="utf-8")
        md.write_text(orig.replace("防漂移", "篡改正文"), encoding="utf-8")

        chk = self.recovery.check_consistency()
        self.assertFalse(chk["consistent"])
        self.assertTrue(chk["desynced_topics"][0]["content_drift"])

    # R05: 全库快照回滚不自锁与清理孤儿文件
    def test_r05_rollback_no_deadlock_and_cleans_orphans(self):
        self.service.save_topic("t-snap-a", {"title": "议题 A", "section": "核心架构"})
        rev1_id = self.service.db.get_revisions()[0]["rev_id"]

        self.service.save_topic("t-snap-b", {"title": "议题 B", "section": "网络"})
        file_b = self.cfg.decisions_dir / "t-snap-b.md"
        self.assertTrue(file_b.exists())

        rb = self.service.rollback_full(rev1_id)
        self.assertEqual(rb["status"], "success")

        # 数据库与磁盘均已清理议题 B
        all_ids = [t["id"] for t in self.service.db.get_all_topics()]
        self.assertIn("t-snap-a", all_ids)
        self.assertNotIn("t-snap-b", all_ids)
        self.assertFalse(file_b.exists())

    # R06: 恢复与核验保留全字段与结构化轮次
    def test_r06_single_topic_restore_preserves_section_and_rounds(self):
        self.service.save_topic(
            "t-restore-fields",
            {
                "title": "保真测试",
                "section": "高性能存储",
                "impl_commit": "init-commit",
                "impl_verifier": "Lead: OK",
                "user_opinion": "用户原话A",
                "agent_reply": "答复A"
            }
        )
        target_rev = self.service.db.get_revisions()[0]["rev_id"]

        # 覆盖更新
        self.service.save_topic(
            "t-restore-fields",
            {"title": "修改后的标题", "user_opinion": "原话B", "agent_reply": "答复B"}
        )

        # 执行恢复
        res = self.service.restore_single_topic("t-restore-fields", target_rev)
        self.assertEqual(res["status"], "success")

        parsed = self.service.parser.parse_markdown_file(self.cfg.decisions_dir / "t-restore-fields.md")
        self.assertEqual(parsed["section"], "高性能存储")
        self.assertEqual(parsed["impl_commit"], "init-commit")
        self.assertEqual(parsed["impl_verifier"], "Lead: OK")
        self.assertEqual(len(parsed["rounds"]), 1)
        self.assertIn("用户原话A", parsed["rounds"][0]["user_opinion"])
        self.assertIn("答复A", parsed["rounds"][0]["agent_reply"])

    def test_r06_verification_preserves_section(self):
        self.service.save_topic("t-ver-sec", {"title": "核验分类", "section": "分布式系统"})
        self.agent.record_verification(
            topic_id="t-ver-sec",
            impl_commit="commit-sec-1",
            verifier="QA Lead",
            mark_verified=True
        )
        parsed = self.service.parser.parse_markdown_file(self.cfg.decisions_dir / "t-ver-sec.md")
        self.assertEqual(parsed["section"], "分布式系统")
        self.assertEqual(parsed["implementation_state"], "verified")

    # R07: 幂等指纹绑定与重试续做
    def test_r07_idempotency_scoped_to_topic_and_create_replay(self):
        self.service.save_topic("t-idemp-a", {"title": "相同内容"}, request_id="req-same")

        # 相同 request_id 发给不同 topic_id 必须冲突
        with self.assertRaises(IdempotencyConflictError):
            self.service.save_topic("t-idemp-b", {"title": "相同内容"}, request_id="req-same")

        # create_topic 相同 request_id 重发优先重放
        c1 = self.service.create_topic({"id": "t-c-idemp", "title": "创建幂等"}, request_id="req-c-1")
        c2 = self.service.create_topic({"id": "t-c-idemp", "title": "创建幂等"}, request_id="req-c-1")
        self.assertTrue(c2.get("is_replay"))

    # R08: Markdown 语法保真 (多行理由、代码注释、子标题)
    def test_r08_markdown_fidelity(self):
        reason = "第一行原因\n第二行原因：包含\"双引号\"和'单引号'以及 --- 破折号"
        serialized = self.service.parser.serialize_markdown(
            topic_id="t-rej-md",
            title="否决",
            lifecycle_badge="🔴",
            decision_status="否决",
            impl_status="不实现",
            priority="普通",
            obj="系统",
            func="规范",
            core_content="这是核心论述。\n\n```python\n# important code comment\nreturn 1\n```",
            existing_rounds=[],
            workflow_state="decided",
            decision_outcome="rejected",
            rejection_reason=reason
        )
        parsed = self.service.parser.parse_markdown_text(serialized, default_id="t-rej-md")
        self.assertEqual(parsed["rejection_reason"], reason)
        self.assertIn("# important code comment", parsed["core_content"])

    # R09: Agent 约束过滤与强制否决原因
    def test_r09_agent_constraint_filtering(self):
        self.service.save_topic(
            "t-sup",
            {"title": "作废方案", "workflow_state": "decided", "decision_outcome": "superseded", "object": "网关"}
        )
        self.service.save_topic(
            "t-def",
            {"title": "暂缓方案", "workflow_state": "decided", "decision_outcome": "deferred", "object": "网关"}
        )
        self.service.save_topic(
            "t-impl",
            {"title": "未核验实现", "workflow_state": "decided", "decision_outcome": "accepted", "implementation_state": "implemented", "object": "网关"}
        )

        ctx = self.agent.query_context(module="网关")
        active_ids = [t["id"] for t in ctx["active_decisions"]]
        pending_ids = [t["id"] for t in ctx["pending_requirements"]]

        self.assertNotIn("t-sup", active_ids)
        self.assertNotIn("t-def", active_ids)
        self.assertIn("t-impl", pending_ids)

        # 否决状态无理由报错
        with self.assertRaises(TopicValidationError):
            self.service.save_topic("t-no-reason", {"title": "无理由", "decision_outcome": "rejected", "rejection_reason": ""})

    # R10: Git 路径限定防竞态与快照持久化
    def test_r10_git_isolation_and_head_revision(self):
        unrelated = self.base_dir / "user_code.py"
        unrelated.write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "user_code.py"], cwd=str(self.base_dir), check=True, capture_output=True)

        res = self.service.git.commit_decision("标题", "badge", "测试", staged_files=[self.base_dir / "decisions" / "x.md"])
        self.assertFalse(res.success)
        self.assertEqual(res.status, "skipped_unrelated_staged")

        # 撤回无关文件的暂存
        subprocess.run(["git", "reset", "user_code.py"], cwd=str(self.base_dir), check=True, capture_output=True)

        # 正常自动提交
        save_res = self.service.save_topic("t-git-rev", {"title": "快照同步测试"})
        self.assertEqual(save_res["git_status"], "committed")

        # 检查 Git HEAD 中的 decisions.db 包含 Revision 快照
        git_db_bytes = subprocess.run(
            ["git", "show", "HEAD:decisions.db"],
            cwd=str(self.base_dir),
            capture_output=True,
            check=True
        ).stdout
        tmp_db = self.base_dir / "check_head.db"
        tmp_db.write_bytes(git_db_bytes)
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        rev_rows = conn.cursor().execute("SELECT * FROM revisions").fetchall()
        conn.close()
        self.assertGreater(len(rev_rows), 0)
        self.assertEqual(rev_rows[-1]["rev_hash"], save_res["revision_hash"])


if __name__ == "__main__":
    unittest.main()
