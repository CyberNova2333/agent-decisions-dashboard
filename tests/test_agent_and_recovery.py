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

if __name__ == "__main__":
    unittest.main()
