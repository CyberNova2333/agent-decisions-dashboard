# -*- coding: utf-8 -*-
"""
Tests for GitEngine: Staging Isolation, Repo Checks, and Status Feedback
"""

import unittest
import tempfile
import subprocess
import shutil
from pathlib import Path
from core.git_engine import GitEngine, GitCommitResult
from core.config import Config

class TestGitEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.test_dir.name)
        
        # 初始化真实的临时 Git 仓库
        subprocess.run(["git", "init"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.repo_dir), capture_output=True, check=True)

        # 初始提交
        readme = self.repo_dir / "README.md"
        readme.write_text("# Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init commit"], cwd=str(self.repo_dir), capture_output=True, check=True)

        self.cfg = Config({"git_commit": {"enabled": True}}, base_dir=self.repo_dir)
        self.engine = GitEngine(self.repo_dir, self.cfg)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_repo_detection(self):
        self.assertTrue(self.engine.is_git_repo())
        head = self.engine.get_head_hash(short=True)
        self.assertNotEqual(head, "none")
        self.assertEqual(len(head), 7)

    def test_staging_isolation_unrelated_files_preserved(self):
        """
        P1-B: 核心安全测试：
        用户工作区存在非台账已暂存代码 (src/app.py)，自动提交严禁顺带提交该文件！
        必须跳过自动提交，且非台账文件的暂存状态保持不变。
        """
        src_file = self.repo_dir / "src" / "app.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("print('user work in progress')", encoding="utf-8")
        
        # 用户暂存了自己的代码
        subprocess.run(["git", "add", "src/app.py"], cwd=str(self.repo_dir), capture_output=True, check=True)
        
        # 验证此时暂存区有 src/app.py
        staged_before = self.engine.get_staged_files()
        self.assertIn("src/app.py", staged_before)

        # 准备台账文件
        decision_file = self.repo_dir / "decisions" / "adr-001.md"
        decision_file.parent.mkdir(parents=True, exist_ok=True)
        decision_file.write_text("# ADR 001\n", encoding="utf-8")

        # 执行台账提交
        result = self.engine.commit_decision(
            topic_title="架构测试",
            lifecycle_badge="🟢 已决策",
            summary="尝试自动提交",
            staged_files=[decision_file]
        )

        # 必须拒绝自动提交以保护用户暂存区
        self.assertFalse(result.success)
        self.assertEqual(result.status, "skipped_unrelated_staged")
        self.assertIn("src/app.py", result.unrelated_files)

        # 验证用户的 src/app.py 仍旧在暂存区，没有被清空、也没有被误提交！
        staged_after = self.engine.get_staged_files()
        self.assertIn("src/app.py", staged_after)

    def test_clean_commit_when_only_decision_files(self):
        """当暂存区干净时，台账变更可安全自动提交"""
        decision_file = self.repo_dir / "decisions" / "adr-001.md"
        decision_file.parent.mkdir(parents=True, exist_ok=True)
        decision_file.write_text("# ADR 001\n", encoding="utf-8")

        result = self.engine.commit_decision(
            topic_title="架构测试",
            lifecycle_badge="🟢 已决策",
            summary="正常提交",
            user_opinion="明确同意",
            agent_reply="已执行",
            staged_files=[decision_file]
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "committed")
        self.assertNotEqual(result.commit_hash, "")

        # 检查 commit log 包含 Co-Author
        history = self.engine.get_commit_history(limit=1)
        self.assertEqual(len(history), 1)
        self.assertIn("架构测试", history[0]["message"])

    def test_lock_file_detection(self):
        """测试存在 .git/index.lock 时安全报错，避免死锁或冲突"""
        lock_file = self.repo_dir / ".git" / "index.lock"
        lock_file.write_text("locked", encoding="utf-8")
        try:
            self.assertTrue(self.engine.is_locked())
            res = self.engine.commit_decision("标题", "badge", "测试锁定")
            self.assertFalse(res.success)
            self.assertEqual(res.status, "locked")
        finally:
            if lock_file.exists():
                lock_file.unlink()

    def test_interleaved_staging_race_defense(self):
        """测试预检与提交之间外部进程插入 git add 时，绝不污染提交 (R10)"""
        unrelated_file = self.repo_dir / "user_work.py"
        unrelated_file.write_text("critical_secret = 42\n", encoding="utf-8")

        decision_file = self.repo_dir / "decisions" / "adr-race.md"
        decision_file.parent.mkdir(parents=True, exist_ok=True)
        decision_file.write_text("# Decision\n", encoding="utf-8")

        # 模拟在执行提交过程中发生外部暂存
        subprocess.run(["git", "add", "user_work.py"], cwd=str(self.repo_dir), check=True, capture_output=True)

        res = self.engine.commit_decision(
            topic_title="竞态保护测试",
            lifecycle_badge="🟢 已决策",
            summary="竞态测试",
            staged_files=[decision_file]
        )

        # 必须拒绝自动提交，保护用户的 user_work.py
        self.assertFalse(res.success)
        self.assertEqual(res.status, "skipped_unrelated_staged")
        self.assertIn("user_work.py", res.unrelated_files)

        # 检查最新提交，绝不包含 user_work.py
        last_commit_files = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            cwd=str(self.repo_dir),
            capture_output=True,
            text=True
        ).stdout
        self.assertNotIn("user_work.py", last_commit_files)

    def test_revision_is_persisted_inside_git_head_database(self):
        """测试提交至 Git 的 decisions.db 中包含本次生成的 Revision 快照 (R10)"""
        import sqlite3
        from core.decision_service import DecisionService

        # 启用 Git 自动提交
        service_cfg = Config({"git_commit": {"enabled": True}}, base_dir=self.repo_dir)
        service = DecisionService(service_cfg)

        save_res = service.save_topic(
            topic_id="adr-git-rev",
            data={"title": "快照同步测试", "workflow_state": "decided"}
        )
        self.assertEqual(save_res["git_status"], "committed")

        # 从 Git HEAD 中直接导出 decisions.db
        git_db_bytes = subprocess.run(
            ["git", "show", "HEAD:decisions.db"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        ).stdout

        temp_db_path = self.repo_dir / "temp_head_check.db"
        temp_db_path.write_bytes(git_db_bytes)

        # 检查导出的 Git HEAD decisions.db 中 revisions 表不为空且包含对应记录
        conn = sqlite3.connect(str(temp_db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute("SELECT * FROM revisions").fetchall()
        conn.close()

        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[-1]["rev_hash"], save_res["revision_hash"])

if __name__ == "__main__":
    unittest.main()
