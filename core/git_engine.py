# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Git Engine
决策变更自动 Git 语义化提交、Co-Author 附加与日志追溯引擎
"""

import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from core.config import Config

class GitEngine:
    def __init__(self, repo_root: Path, config: Optional[Config] = None):
        self.repo_root = repo_root
        self.config = config
        self._git_bin = shutil.which("git") or "git"

    def run_git(self, args: List[str]) -> Tuple[bool, str, str]:
        """安全执行 git 命令并返回 (成功, stdout, stderr)"""
        try:
            res = subprocess.run(
                [self._git_bin] + args,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
        except Exception as e:
            return False, "", str(e)

    def is_git_repo(self) -> bool:
        """检查当前根目录是否为有效 Git 仓库"""
        success, _, _ = self.run_git(["rev-parse", "--is-inside-work-tree"])
        return success

    def get_head_hash(self, short: bool = True) -> str:
        """获取当前 HEAD 提交 Hash"""
        args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
        success, out, _ = self.run_git(args)
        return out.strip() if success and out else "none"

    def get_commit_history(self, limit: int = 30) -> List[Dict[str, str]]:
        """获取最近 Git 提交记录"""
        success, log_out, _ = self.run_git([
            "log", f"-n{limit}", "--pretty=format:%h|%an|%ad|%s", "--date=iso"
        ])
        commits = []
        if success and log_out:
            for line in log_out.splitlines():
                parts = line.split("|")
                if len(parts) >= 4:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3]
                    })
        return commits

    def stage_files(self, paths: List[Path]) -> bool:
        """添加文件至暂存区"""
        rel_paths = []
        for p in paths:
            try:
                rel = p.relative_to(self.repo_root)
                rel_paths.append(str(rel).replace("\\", "/"))
            except ValueError:
                rel_paths.append(str(p))

        if not rel_paths:
            return True

        success, _, _ = self.run_git(["add"] + rel_paths)
        return success

    def commit_decision(
        self,
        topic_title: str,
        lifecycle_badge: str,
        summary: str,
        user_opinion: str = "",
        agent_reply: str = "",
        staged_files: Optional[List[Path]] = None
    ) -> Tuple[bool, str]:
        """
        递交一次决策 Git Commit：
        按照 Conventional Commit 规范，格式化提交说明并自动追加 Co-Author
        """
        git_cfg = self.config.git_commit if self.config else {}
        if not git_cfg.get("enabled", True):
            return True, "git commit disabled in config"

        prefix = git_cfg.get("commit_prefix", "feat(decision)")
        co_author = git_cfg.get("co_author", "Antigravity <antigravity@google.com>")

        # 1. 组装 Commit Message
        header = f"{prefix}: [{lifecycle_badge}] {topic_title} - {summary or '更新决策内容'}"
        body_parts = []

        if user_opinion and git_cfg.get("include_user_opinion", True):
            body_parts.append(f"用户指示：{user_opinion}")
        if agent_reply and git_cfg.get("include_agent_reply", True):
            body_parts.append(f"落实答复：{agent_reply}")

        body_text = "\n\n".join(body_parts)
        if body_text:
            commit_msg = f"{header}\n\n{body_text}"
        else:
            commit_msg = header

        if co_author:
            commit_msg += f"\n\nCo-authored-by: {co_author}"

        # 2. 暂存相关文件
        if staged_files:
            self.stage_files(staged_files)

        # 3. 提交
        success, out, err = self.run_git(["commit", "-m", commit_msg])
        if success:
            head = self.get_head_hash(short=True)
            return True, head
        return False, err or out
