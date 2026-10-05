# -*- coding: utf-8 -*-
"""
Tests for DatabaseManager: Schema, Concurrency Optimistic Lock, Idempotency, and Restore
"""

import unittest
import tempfile
from pathlib import Path
from core.db import DatabaseManager, VersionConflictError
from core.config import Config

class TestDatabaseAndConcurrency(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.test_dir.name)
        self.cfg = Config({"git_commit": {"enabled": False}}, base_dir=self.base_dir)
        self.db = DatabaseManager(self.cfg.database_path, self.cfg)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_schema_and_upsert(self):
        v1 = self.db.upsert_topic({
            "id": "adr-test-1",
            "title": "测试议题",
            "workflow_state": "decided",
            "decision_outcome": "accepted",
            "implementation_state": "implemented",
            "impl_commit": "c0ffee"
        })
        self.assertEqual(v1, 1)

        t = self.db.get_topic("adr-test-1")
        self.assertIsNotNone(t)
        self.assertEqual(t["title"], "测试议题")
        self.assertEqual(t["workflow_state"], "decided")
        self.assertEqual(t["decision_outcome"], "accepted")
        self.assertEqual(t["implementation_state"], "implemented")
        self.assertEqual(t["impl_commit"], "c0ffee")
        self.assertEqual(t["version"], 1)

    def test_optimistic_locking_conflict(self):
        """P1-D: 并发乐观锁测试：当 expected_version 与服务端不一致时抛出 VersionConflictError"""
        v1 = self.db.upsert_topic({"id": "adr-conflict", "title": "初始版本"})
        self.assertEqual(v1, 1)

        # 客户端 A 成功升级至 v2
        v2 = self.db.upsert_topic({"id": "adr-conflict", "title": "客户端A更新"}, expected_version=1)
        self.assertEqual(v2, 2)

        # 客户端 B 仍拿着旧版本 v1 尝试提交，必须报错
        with self.assertRaises(VersionConflictError) as ctx:
            self.db.upsert_topic({"id": "adr-conflict", "title": "客户端B覆盖"}, expected_version=1)
        
        self.assertEqual(ctx.exception.current_version, 2)
        self.assertEqual(ctx.exception.expected_version, 1)

    def test_idempotency_keys(self):
        """P1-D: 幂等性保存测试：相同 request_id 重放返回缓存结果，不同 payload 报冲突"""
        req_id = "req-uuid-1234"
        req_hash = "hash-abc"
        res_data = {"status": "success", "round": 2}

        # 首次检查
        is_valid, cached = self.db.check_idempotency(req_id, req_hash)
        self.assertTrue(is_valid)
        self.assertIsNone(cached)

        # 记录
        self.db.record_idempotency(req_id, "adr-test", req_hash, res_data)

        # 相同 hash 重试：应返回相同 cached
        is_valid, cached = self.db.check_idempotency(req_id, req_hash)
        self.assertTrue(is_valid)
        self.assertEqual(cached["status"], "success")
        self.assertEqual(cached["round"], 2)

        # 相同 request_id 但不同 payload (不同 hash)：应拒绝
        is_valid, _ = self.db.check_idempotency(req_id, "different-hash")
        self.assertFalse(is_valid)

    def test_single_topic_restore(self):
        """P1-C: 单议题针对性回溯，不影响其他议题，生成新审计快照"""
        # 创建两个议题
        self.db.upsert_topic({"id": "topic-a", "title": "议题A-版本1"})
        self.db.upsert_topic({"id": "topic-b", "title": "议题B-版本1"})
        rev1 = self.db.commit_revision("INIT", "初始化状态")

        # 修改议题 A 和 议题 B
        self.db.upsert_topic({"id": "topic-a", "title": "议题A-版本2"})
        self.db.upsert_topic({"id": "topic-b", "title": "议题B-版本2"})
        self.db.commit_revision("UPDATE", "更新两个议题")

        # 此时执行仅恢复 topic-a 到 rev1 快照
        restore_res = self.db.restore_topic_from_revision("topic-a", rev1["rev_id"], reason="撤回 A 的改动")
        self.assertEqual(restore_res["status"], "success")

        # 验证：topic-a 已恢复为“议题A-版本1”，而 topic-b 依然是“议题B-版本2”！
        ta = self.db.get_topic("topic-a")
        tb = self.db.get_topic("topic-b")
        self.assertEqual(ta["title"], "议题A-版本1")
        self.assertEqual(tb["title"], "议题B-版本2")

    def test_online_backup(self):
        """测试 SQLite 官方 Backup API 在线备份有效性"""
        self.db.upsert_topic({"id": "bak-test", "title": "备份测试"})
        backup_file = self.base_dir / "backups" / "test_backup.db"
        res = self.db.backup_database(backup_file)
        self.assertEqual(res["status"], "success")
        self.assertTrue(backup_file.exists())
        self.assertGreater(backup_file.stat().st_size, 0)

if __name__ == "__main__":
    unittest.main()
