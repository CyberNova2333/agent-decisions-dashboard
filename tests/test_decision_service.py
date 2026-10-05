# -*- coding: utf-8 -*-
"""
Tests for DecisionService: End-to-End Save Pipeline, Path Traversal Defense, and Restoration
"""

import unittest
import tempfile
import json
from pathlib import Path
from core.config import Config
from core.decision_service import DecisionService, TopicValidationError, IdempotencyConflictError
from core.db import VersionConflictError

class TestDecisionService(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.test_dir.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, base_dir=self.base_dir)
        self.service = DecisionService(self.cfg)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_path_traversal_defense(self):
        """P2: 路径越界与非法 ID 强校验"""
        with self.assertRaises(TopicValidationError):
            self.service.validate_topic_id("../../etc/passwd")

        with self.assertRaises(TopicValidationError):
            self.service.validate_topic_id("topic/../sub")

        with self.assertRaises(TopicValidationError):
            self.service.validate_topic_id("topic id with spaces")

        # 合法 ID
        self.assertEqual(self.service.validate_topic_id("adr-001_core"), "adr-001_core")

    def test_save_pipeline_syncs_markdown_and_db(self):
        """测试一次保存完整协调：写 Markdown、写 SQLite、刷新 metadata.json、出具 operation_id"""
        res = self.service.save_topic(
            topic_id="adr-full-flow",
            data={
                "title": "端到端全流程测试",
                "workflow_state": "decided",
                "decision_outcome": "accepted",
                "implementation_state": "implemented",
                "commit_message": "全流程验收",
                "user_opinion": "已全部核准",
                "agent_reply": "已全部实现",
                "priority": "高"
            },
            request_id="req-pipeline-1"
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["operation_id"].startswith("op-"))
        self.assertEqual(res["new_version"], 1)
        self.assertEqual(res["round"], 1)

        # 检查权威 Markdown 文件
        md_file = self.cfg.decisions_dir / "adr-full-flow.md"
        self.assertTrue(md_file.exists())
        md_text = md_file.read_text(encoding="utf-8")
        self.assertIn('title: "端到端全流程测试"', md_text)
        self.assertIn("已全部核准", md_text)

        # 检查派生物 metadata.json
        self.assertTrue(self.cfg.metadata_json_path.exists())
        meta_data = json.loads(self.cfg.metadata_json_path.read_text(encoding="utf-8"))
        self.assertEqual(meta_data["total_topics"], 1)
        self.assertEqual(meta_data["topics"][0]["id"], "adr-full-flow")

    def test_optimistic_conflict_and_idempotency_in_service(self):
        """测试服务层并发冲突与幂等重放机制"""
        r1 = self.service.save_topic(
            topic_id="adr-idemp",
            data={"title": "版本测试"},
            request_id="req-idemp-1"
        )
        self.assertEqual(r1["new_version"], 1)

        # 重放：相同 request_id 与数据，返回缓存响应
        r1_replay = self.service.save_topic(
            topic_id="adr-idemp",
            data={"title": "版本测试"},
            request_id="req-idemp-1"
        )
        self.assertTrue(r1_replay.get("is_replay"))

        # 冲突：相同 request_id 但不同 payload，抛出 IdempotencyConflictError
        with self.assertRaises(IdempotencyConflictError):
            self.service.save_topic(
                topic_id="adr-idemp",
                data={"title": "篡改后的版本测试"},
                request_id="req-idemp-1"
            )

        # 并发冲突：期望版本为 10，实际为 1
        with self.assertRaises(VersionConflictError):
            self.service.save_topic(
                topic_id="adr-idemp",
                data={"title": "并发更新"},
                expected_version=10,
                request_id="req-idemp-2"
            )

    def test_version_conflict_leaves_markdown_untouched(self):
        """测试版本冲突拒绝时，权威 Markdown 文件绝不被副作用修改 (R02)"""
        # 1. 建立初始议题 v1
        self.service.save_topic(
            topic_id="adr-conflict-safe",
            data={"title": "初始合法标题", "user_opinion": "初始原话"}
        )
        md_file = self.cfg.decisions_dir / "adr-conflict-safe.md"
        content_v1 = md_file.read_text(encoding="utf-8")

        # 2. 尝试用冲突版本 (期望 99) 提交修改
        with self.assertRaises(VersionConflictError):
            self.service.save_topic(
                topic_id="adr-conflict-safe",
                data={"title": "过期的冲突标题", "user_opinion": "过期的原话"},
                expected_version=99
            )

        # 3. 验证文件绝对没有被修改
        content_after = md_file.read_text(encoding="utf-8")
        self.assertEqual(content_v1, content_after)
        self.assertNotIn("过期的冲突标题", content_after)

    def test_unified_version_allocation(self):
        """测试新建议题在 Markdown、SQLite 与返回体中统一为版本 1 (R02)"""
        res = self.service.create_topic(
            data={"id": "adr-ver-1", "title": "统一版本测试"}
        )
        self.assertEqual(res["new_version"], 1)

        # 检查 SQLite
        db_topic = self.service.db.get_topic("adr-ver-1")
        self.assertEqual(db_topic["version"], 1)

        # 检查 Markdown
        parsed = self.service.parser.parse_markdown_file(self.cfg.decisions_dir / "adr-ver-1.md")
        self.assertEqual(parsed["version"], 1)

    def test_idempotency_scoped_to_topic_id(self):
        """测试相同的 request_id 作用于不同 topic_id 时必须判定为冲突 (R07)"""
        self.service.save_topic(
            topic_id="adr-scope-a",
            data={"title": "相同请求体"},
            request_id="shared-req-id"
        )

        with self.assertRaises(IdempotencyConflictError):
            self.service.save_topic(
                topic_id="adr-scope-b",
                data={"title": "相同请求体"},
                request_id="shared-req-id"
            )

    def test_create_topic_idempotent_retry(self):
        """测试 create_topic 重试时优先重放，不误报议题已存在 (R07)"""
        r1 = self.service.create_topic(
            data={"id": "adr-create-idemp", "title": "创建幂等"},
            request_id="req-create-1"
        )
        self.assertEqual(r1["new_version"], 1)

        # 相同 request_id 重发 create_topic
        r2 = self.service.create_topic(
            data={"id": "adr-create-idemp", "title": "创建幂等"},
            request_id="req-create-1"
        )
        self.assertTrue(r2.get("is_replay"))
        self.assertEqual(r2["new_version"], 1)

if __name__ == "__main__":
    unittest.main()

