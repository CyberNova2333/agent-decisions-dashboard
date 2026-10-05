# -*- coding: utf-8 -*-
"""
Tests for AgentContextEngine and RecoveryManager:
Consistency Verification, Markdown-to-Index Reconstruction, and Agent Prompt Export
"""

import unittest
import tempfile
import json
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

    def test_rebuild_preserves_version_and_is_idempotent(self):
        """测试 Markdown 重建保留文件声明的 version，且多次重建保持严格幂等 (R04)"""
        self.cfg.decisions_dir.mkdir(parents=True, exist_ok=True)
        md = self.cfg.decisions_dir / "adr-ver-7.md"
        md.write_text("""---
schema_version: "2.0"
id: "adr-ver-7"
title: "版本保留测试"
version: 7
workflow_state: "decided"
---

# 版本保留测试

## 核心论述与现实依据
内容
""", encoding="utf-8")

        # 首次重建
        res1 = self.recovery.rebuild_index_from_markdown()
        self.assertEqual(res1["status"], "success")
        t = self.service.db.get_topic("adr-ver-7")
        self.assertEqual(t["version"], 7)

        # 连续第二次重建：版本号必须依然是 7，绝不能累加为 8 (R04)
        res2 = self.recovery.rebuild_index_from_markdown()
        self.assertEqual(res2["status"], "success")
        t_again = self.service.db.get_topic("adr-ver-7")
        self.assertEqual(t_again["version"], 7)

    def test_rebuild_removes_deleted_markdown_topics(self):
        """测试删除磁盘 Markdown 后重建索引，数据库同步移除该议题 (R04)"""
        self.service.save_topic("adr-to-delete", {"title": "即将删除的文件"})
        md_file = self.cfg.decisions_dir / "adr-to-delete.md"
        self.assertTrue(md_file.exists())
        self.assertIsNotNone(self.service.db.get_topic("adr-to-delete"))

        # 删除磁盘文件
        md_file.unlink()

        # 重建索引
        self.recovery.rebuild_index_from_markdown()
        # 数据库中应该已被移除
        self.assertIsNone(self.service.db.get_topic("adr-to-delete"))

    def test_consistency_check_catches_content_drift(self):
        """测试外部直接修改 Markdown 正文时，一致性检查精准捕获内容漂移 (R04)"""
        self.service.save_topic("adr-drift", {"title": "防漂移测试", "user_opinion": "初始意见"})
        md_file = self.cfg.decisions_dir / "adr-drift.md"

        # 外部直接修改 Markdown 内容，但不改版本号
        raw_text = md_file.read_text(encoding="utf-8")
        modified_text = raw_text.replace("防漂移测试", "外部篡改后的标题")
        md_file.write_text(modified_text, encoding="utf-8")

        chk = self.recovery.check_consistency()
        self.assertFalse(chk["consistent"])
        self.assertEqual(len(chk["desynced_topics"]), 1)
        self.assertTrue(chk["desynced_topics"][0]["content_drift"])

    def test_consistency_check_catches_metadata_drift(self):
        """测试 metadata.json 中的字段发生漂移时，一致性检查精准报警 (R04)"""
        self.service.save_topic("adr-meta-drift", {"title": "元数据漂移测试"})
        
        # 篡改 metadata.json 的标题，但不改条目数量
        meta_content = json.loads(self.cfg.metadata_json_path.read_text(encoding="utf-8"))
        meta_content["topics"][0]["title"] = "篡改元数据标题"
        self.cfg.metadata_json_path.write_text(json.dumps(meta_content, ensure_ascii=False), encoding="utf-8")

        chk = self.recovery.check_consistency()
        self.assertFalse(chk["consistent"])
        self.assertFalse(chk["metadata_json_synced"])

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

    def test_superseded_and_deferred_excluded_from_active_decisions(self):
        """测试被替代 (superseded) 或已暂缓 (deferred) 决策绝不作为必须遵守约束导出 (R09)"""
        from core.decision_service import TopicValidationError
        self.service.save_topic(
            topic_id="adr-superseded",
            data={
                "title": "已作废旧方案",
                "workflow_state": "decided",
                "decision_outcome": "superseded",
                "superseded_by": "adr-new",
                "object": "网关"
            }
        )
        self.service.save_topic(
            topic_id="adr-deferred",
            data={
                "title": "暂缓执行方案",
                "workflow_state": "decided",
                "decision_outcome": "deferred",
                "object": "网关"
            }
        )
        ctx = self.agent.query_context(module="网关")
        active_ids = [t["id"] for t in ctx["active_decisions"]]
        self.assertNotIn("adr-superseded", active_ids)
        self.assertNotIn("adr-deferred", active_ids)

    def test_implemented_unverified_in_pending_requirements(self):
        """测试已实现但尚未核验 (implemented) 的议题进入待落实/待核验清单 (R09)"""
        self.service.save_topic(
            topic_id="adr-impl-unverified",
            data={
                "title": "待核验实现",
                "workflow_state": "decided",
                "decision_outcome": "accepted",
                "implementation_state": "implemented",
                "object": "业务"
            }
        )
        ctx = self.agent.query_context(module="业务")
        pending_ids = [t["id"] for t in ctx["pending_requirements"]]
        self.assertIn("adr-impl-unverified", pending_ids)

    def test_rejected_requires_rejection_reason_backend(self):
        """测试后端拒绝无理由的否决状态 (R09)"""
        from core.decision_service import TopicValidationError
        with self.assertRaises(TopicValidationError):
            self.service.save_topic(
                topic_id="adr-no-reason",
                data={
                    "title": "无理由否决",
                    "workflow_state": "decided",
                    "decision_outcome": "rejected",
                    "rejection_reason": ""  # 空理由，后端必须拒绝
                }
            )

if __name__ == "__main__":
    unittest.main()
