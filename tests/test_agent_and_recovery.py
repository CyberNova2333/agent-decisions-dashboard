# -*- coding: utf-8 -*-
"""
Tests for AgentContextEngine and RecoveryManager:
Consistency Verification, Markdown-to-Index Reconstruction, and Agent Prompt Export
"""

import unittest
import tempfile
from pathlib import Path
from core.config import Config
from core.decision_service import DecisionService
from core.recovery import RecoveryManager
from core.agent_context import AgentContextEngine

class TestAgentAndRecovery(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.test_dir.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, base_dir=self.base_dir)
        self.service = DecisionService(self.cfg)
        self.recovery = RecoveryManager(self.cfg, self.service.db)
        self.agent = AgentContextEngine(self.cfg, self.service.db)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_rebuild_index_from_markdown(self):
        """P1-A: 以磁盘 Markdown 为事实源重建索引"""
        # 手工在磁盘写入两个 Markdown 文件
        self.cfg.decisions_dir.mkdir(parents=True, exist_ok=True)
        md1 = self.cfg.decisions_dir / "adr-rebuild-1.md"
        md1.write_text("""---
schema_version: "2.0"
id: "adr-rebuild-1"
title: "重建测试1"
workflow_state: "decided"
decision_outcome: "accepted"
implementation_state: "implemented"
impl_commit: "commit-111"
---

## 核心论述与现实依据

第一项内容
""", encoding="utf-8")

        md2 = self.cfg.decisions_dir / "adr-rebuild-2.md"
        md2.write_text("""---
schema_version: "2.0"
id: "adr-rebuild-2"
title: "重建测试2(被否决方案)"
workflow_state: "decided"
decision_outcome: "rejected"
rejection_reason: "性能损耗超过200%"
---

## 核心论述与现实依据

第二项内容
""", encoding="utf-8")

        # 触发重建
        res = self.recovery.rebuild_index_from_markdown()
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["rebuilt_count"], 2)

        # 验证 SQLite 中已成功索引
        t1 = self.service.db.get_topic("adr-rebuild-1")
        self.assertIsNotNone(t1)
        self.assertEqual(t1["title"], "重建测试1")
        self.assertEqual(t1["impl_commit"], "commit-111")

        t2 = self.service.db.get_topic("adr-rebuild-2")
        self.assertIsNotNone(t2)
        self.assertEqual(t2["decision_outcome"], "rejected")
        self.assertEqual(t2["rejection_reason"], "性能损耗超过200%")

        # 验证一致性检查应返回 True
        chk = self.recovery.check_consistency()
        self.assertTrue(chk["consistent"])

    def test_agent_context_separation_and_markdown(self):
        """P2-F: 验证 Agent 上下文导出中有效决策与已否决红线的明确分离"""
        # 准备数据
        self.service.save_topic(
            topic_id="adr-accepted",
            data={
                "title": "采纳方案：微内核",
                "workflow_state": "decided",
                "decision_outcome": "accepted",
                "implementation_state": "implemented",
                "impl_commit": "hash-abc",
                "object": "核心架构"
            }
        )
        self.service.save_topic(
            topic_id="adr-rejected",
            data={
                "title": "否决方案：重型框架",
                "workflow_state": "decided",
                "decision_outcome": "rejected",
                "rejection_reason": "过于臃肿，违背设计目标",
                "superseded_by": "adr-accepted",
                "object": "核心架构"
            }
        )

        ctx = self.agent.query_context(module="核心架构")
        self.assertEqual(len(ctx["active_decisions"]), 1)
        self.assertEqual(len(ctx["rejected_proposals"]), 1)

        self.assertEqual(ctx["active_decisions"][0]["id"], "adr-accepted")
        self.assertEqual(ctx["rejected_proposals"][0]["id"], "adr-rejected")
        self.assertEqual(ctx["rejected_proposals"][0]["rejection_reason"], "过于臃肿，违背设计目标")

        md_output = self.agent.format_as_markdown(ctx)
        self.assertIn("当前有效决策", md_output)
        self.assertIn("明确否决方案与红线", md_output)
        self.assertIn("过于臃肿，违背设计目标", md_output)

    def test_verification_evidence_binding(self):
        """P2-E: 关联实现代码提交与核验人证据"""
        self.service.save_topic(
            topic_id="adr-verify",
            data={"title": "待核验议题", "workflow_state": "decided"}
        )

        v_res = self.agent.record_verification(
            topic_id="adr-verify",
            impl_commit="commit-789xyz",
            verifier="Antigravity-AI",
            test_summary="全量单元测试与集成测试通过",
            mark_verified=True
        )

        self.assertEqual(v_res["status"], "success")
        self.assertEqual(v_res["implementation_state"], "verified")
        self.assertEqual(v_res["impl_commit"], "commit-789xyz")

        # 检查数据库已更新
        topic = self.service.db.get_topic("adr-verify")
        self.assertEqual(topic["implementation_state"], "verified")
        self.assertEqual(topic["impl_commit"], "commit-789xyz")
        self.assertIn("全量单元测试与集成测试通过", topic["impl_verifier"])

    def test_record_verification_preserves_section(self):
        """测试核验证据记录时不丢失 section 分类字段 (R06)"""
        self.service.save_topic(
            topic_id="adr-sec-preserve",
            data={
                "title": "分类保护测试",
                "section": "网络通信",
                "workflow_state": "decided"
            }
        )
        self.agent.record_verification(
            topic_id="adr-sec-preserve",
            impl_commit="hash-sec-1",
            verifier="QA",
            mark_verified=True
        )
        # 验证 Markdown 中的 section 仍是网络通信
        parsed = self.service.parser.parse_markdown_file(self.cfg.decisions_dir / "adr-sec-preserve.md")
        self.assertEqual(parsed["section"], "网络通信")
        self.assertEqual(parsed["implementation_state"], "verified")

    def test_rollback_no_deadlock_and_cleans_orphans(self):
        """测试全库快照回滚不自死锁，且清理目标快照外的多余议题文件 (R05)"""
        # 1. 保存议题 A，生成快照 rev 1
        res1 = self.service.save_topic(
            topic_id="adr-snapshot-a",
            data={"title": "快照 A 议题", "section": "底层协议"}
        )
        revs = self.service.db.get_revisions()
        rev1_id = revs[0]["rev_id"]

        # 2. 保存新议题 B
        self.service.save_topic(
            topic_id="adr-snapshot-b",
            data={"title": "快照 B 议题", "section": "UI 交互"}
        )
        file_b = self.cfg.decisions_dir / "adr-snapshot-b.md"
        self.assertTrue(file_b.exists())

        # 3. 回滚至快照 rev 1 (必须无锁成功)
        rb_res = self.service.rollback_full(rev1_id)
        self.assertEqual(rb_res["status"], "success")

        # 4. 验证数据库中只有议题 A，没有议题 B
        all_topics = self.service.db.get_all_topics()
        topic_ids = [t["id"] for t in all_topics]
        self.assertIn("adr-snapshot-a", topic_ids)
        self.assertNotIn("adr-snapshot-b", topic_ids)

        # 5. 验证议题 B 的文件已从 decisions 移出，不会在后续 rebuild 中复活
        self.assertFalse(file_b.exists())
        self.recovery.rebuild_index_from_markdown()
        all_topics_after = self.service.db.get_all_topics()
        self.assertNotIn("adr-snapshot-b", [t["id"] for t in all_topics_after])

    def test_single_topic_restore_preserves_all_fields_and_rounds(self):
        """测试单议题恢复保留 section、impl 证据，且轮次不分裂为两倍伪轮次 (R06)"""
        self.service.save_topic(
            topic_id="adr-field-preserve",
            data={
                "title": "单议题字段完整测试",
                "section": "存储架构",
                "impl_commit": "init-commit-111",
                "impl_verifier": "Lead: verified",
                "user_opinion": "坚持本地存储",
                "agent_reply": "落实为 SQLite"
            }
        )
        revs = self.service.db.get_revisions()
        target_rev = revs[0]["rev_id"]

        # 修改为新内容
        self.service.save_topic(
            topic_id="adr-field-preserve",
            data={
                "title": "被修改的标题",
                "user_opinion": "第二轮原话",
                "agent_reply": "第二轮答复"
            }
        )

        # 精准恢复单议题至 target_rev
        restore_res = self.service.restore_single_topic("adr-field-preserve", target_rev)
        self.assertEqual(restore_res["status"], "success")

        # 读取恢复后的 Markdown
        parsed = self.service.parser.parse_markdown_file(self.cfg.decisions_dir / "adr-field-preserve.md")
        self.assertEqual(parsed["section"], "存储架构")
        self.assertEqual(parsed["impl_commit"], "init-commit-111")
        self.assertEqual(parsed["impl_verifier"], "Lead: verified")
        # 轮次数应为 1，用户原话与答复在同一轮
        self.assertEqual(len(parsed["rounds"]), 1)
        self.assertIn("坚持本地存储", parsed["rounds"][0]["user_opinion"])
        self.assertIn("落实为 SQLite", parsed["rounds"][0]["agent_reply"])

if __name__ == "__main__":
    unittest.main()
