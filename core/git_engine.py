# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Git Engine
决策变更自动 Git 语义化提交、暂存区隔离保护、Co-Author 附加与日志追溯引擎
"""

import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from core.config import Config

@dataclass
class GitCommitResult:
    success: bool
    status: str  # "committed", "skipped_unrelated_staged", "not_a_repo", "disabled", "clean", "locked", "no_identity", "git_error"
    commit_hash: str = ""
    message: str = ""
    unrelated_files: List[str] = field(default_factory=list)

    def __getitem__(self, index: int):
        """兼容原有 (bool, str) 的解包与索引访问"""
        if index == 0:
            return self.success
        elif index == 1:
            return self.commit_hash if self.success else (self.message or self.status)
        raise IndexError("GitCommitResult only supports index 0 or 1 for legacy tuple unpacking")

    def __iter__(self):
        """兼容 success, result = git.commit_decision(...)"""
        yield self.success
        yield self.commit_hash if self.success else (self.message or self.status)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "commit_hash": self.commit_hash,
            "message": self.message,
            "unrelated_files": self.unrelated_files
        }


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
        success, out, _ = self.run_git(["rev-parse", "--is-inside-work-tree"])
        return success and out.strip() == "true"

    def is_locked(self) -> bool:
        """检查是否存在 .git/index.lock 文件"""
        lock_file = self.repo_root / ".git" / "index.lock"
        return lock_file.exists()

    def check_identity(self) -> Tuple[bool, str]:
        """检查 Git 提交者身份是否已配置"""
        s1, name, _ = self.run_git(["config", "user.name"])
        s2, email, _ = self.run_git(["config", "user.email"])
        if not s1 or not name.strip() or not s2 or not email.strip():
            # 尝试检查环境变量
            s3, ident, _ = self.run_git(["var", "GIT_AUTHOR_IDENT"])
            if not s3 or not ident.strip():
                return False, "Git 身份未配置 (缺少 user.name 或 user.email)"
        return True, ""

    def get_head_hash(self, short: bool = True) -> str:
        """获取当前 HEAD 提交 Hash"""
        args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
        success, out, _ = self.run_git(args)
        return out.strip() if success and out else "none"

    def get_staged_files(self) -> List[str]:
        """获取当前已在 Git 暂存区中的所有文件相对路径 (POSIX 格式)"""
        success, out, _ = self.run_git(["diff", "--cached", "--name-only"])
        if not success or not out:
            return []
        return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]

    def normalize_rel_path(self, path: Path) -> str:
        """将路径转换为相对于仓库根目录的标准 POSIX 字符串"""
        try:
            rel = path.relative_to(self.repo_root)
            return str(rel).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

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
        """添加指定文件至暂存区"""
        rel_paths = [self.normalize_rel_path(p) for p in paths]
        if not rel_paths:
            return True

        success, _, _ = self.run_git(["add", "--"] + rel_paths)
        return success

    def commit_decision(
        self,
        topic_title: str,
        lifecycle_badge: str,
        summary: str,
        user_opinion: str = "",
        agent_reply: str = "",
        staged_files: Optional[List[Path]] = None
    ) -> GitCommitResult:
        """
        递交一次决策 Git Commit，具备以下保护机制：
        1. 检查是否为有效 Git 仓库及是否存在 index.lock
        2. 检查 Git 用户名/邮箱身份配置
        3. 暂存区隔离检测：若检测到非本次台账操作的暂存文件，严禁自动提交以避免夹带用户其他未完成代码
        4. 语义化提交格式并自动追加 Co-Author
        """
        git_cfg = self.config.git_commit if self.config else {}
        if not git_cfg.get("enabled", True):
            return GitCommitResult(
                success=True,
                status="disabled",
                commit_hash=self.get_head_hash(),
                message="Git 自动提交已在配置中禁用"
            )

        # 1. 基础环境与状态检查
        if not self.is_git_repo():
            return GitCommitResult(
                success=False,
                status="not_a_repo",
                message="当前目录不是有效 Git 仓库"
            )

        if self.is_locked():
            return GitCommitResult(
                success=False,
                status="locked",
                message="Git 索引被锁定 (.git/index.lock 存在)，可能有其他进程正在操作"
            )

        id_ok, id_msg = self.check_identity()
        if not id_ok:
            return GitCommitResult(
                success=False,
                status="no_identity",
                message=id_msg
            )

        # 2. 暂存区保护检查 (P1-B)：严禁意外提交用户已经暂存的其他工作区文件
        target_rel_files = set()
        if staged_files:
            target_rel_files = {self.normalize_rel_path(p) for p in staged_files}

        current_staged = self.get_staged_files()
        unrelated_staged = [f for f in current_staged if f not in target_rel_files]

        if unrelated_staged:
            # 检测到非本次台账操作的暂存文件，不污染用户暂存区，保留数据并安全跳过 Git 提交
            return GitCommitResult(
                success=False,
                status="skipped_unrelated_staged",
                commit_hash=self.get_head_hash(),
                message=f"暂存区存在 {len(unrelated_staged)} 个非台账文件已暂存，为保护工作区，已跳过自动提交。",
                unrelated_files=unrelated_staged
            )

        # 3. 组装 Commit Message
        prefix = git_cfg.get("commit_prefix", "feat(decision)")
        co_author = git_cfg.get("co_author", "Antigravity <antigravity@google.com>")

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

        # 4. 暂存本次相关文件
        if staged_files:
            ok = self.stage_files(staged_files)
            if not ok:
                return GitCommitResult(
                    success=False,
                    status="git_error",
                    message="执行 git add 暂存文件失败"
                )

        # 5. 提交前二次安全校验：防止暂存区预检后发生外部并发 git add 竞态 (R10)
        current_staged = self.get_staged_files()
        unrelated_staged = [f for f in current_staged if f not in target_rel_files]
        if unrelated_staged:
            return GitCommitResult(
                success=False,
                status="skipped_unrelated_staged",
                commit_hash=self.get_head_hash(),
                message=f"检测到并发暂存冲突：存在 {len(unrelated_staged)} 个非台账文件已暂存，为保护工作区，已跳过自动提交。",
                unrelated_files=unrelated_staged
            )

        # 6. 执行提交：必须通过 pathspec 显式限定本次提交的文件范围，杜绝夹带任何外界暂存 (R10)
        commit_cmd = ["commit", "-m", commit_msg]
        if target_rel_files:
            commit_cmd.extend(["--"] + sorted(list(target_rel_files)))

        success, out, err = self.run_git(commit_cmd)
        if success:
            head = self.get_head_hash(short=True)
            return GitCommitResult(
                success=True,
                status="committed",
                commit_hash=head,
                message=f"成功递交 Git 提交 [{head}]"
            )

        # 检查是否因为工作区无修改而无需提交
        if "nothing to commit" in out or "nothing to commit" in err or "无文件要提交" in out or "干净工作区" in out:
            head = self.get_head_hash(short=True)
            return GitCommitResult(
                success=True,
                status="clean",
                commit_hash=head,
                message="文件内容未变更，无需生成新提交"
            )

        return GitCommitResult(
            success=False,
            status="git_error",
            message=err or out
        )
