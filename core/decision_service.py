# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Decision Service
核心业务流程协调层：创建、保存、乐观锁并发检查、幂等去重、受控提交与精准回滚
"""

import json
import uuid
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from core.config import Config
from core.db import DatabaseManager, VersionConflictError
from core.markdown_parser import TopicMarkdownParser
from core.git_engine import GitEngine, GitCommitResult
from core.recovery import RecoveryManager

class TopicValidationError(Exception):
    """议题参数或路径校验异常"""
    pass

class IdempotencyConflictError(Exception):
    """幂等键冲突异常"""
    pass

class DecisionService:
    def __init__(self, config: Config):
        self.config = config
        self.repo_root = config.base_dir
        self.db = DatabaseManager(config.database_path, config)
        self.git = GitEngine(self.repo_root, config)
        self.parser = TopicMarkdownParser()
        self.recovery = RecoveryManager(config, self.db)

    def validate_topic_id(self, topic_id: str) -> str:
        """安全校验 topic_id，彻底防止目录遍历与非法字符"""
        tid = (topic_id or "").strip()
        if not tid:
            raise TopicValidationError("Topic ID 不能为空")
        if not re.match(r'^[a-zA-Z0-9_\-]+$', tid):
            raise TopicValidationError(f"Topic ID 包含非法字符，仅允许字母、数字、下划线和连字符: '{tid}'")
        target_file = (self.config.decisions_dir / f"{tid}.md").resolve()
        try:
            target_file.relative_to(self.config.decisions_dir.resolve())
        except ValueError:
            raise TopicValidationError("检测到越界非法路径访问")
        return tid

    def get_lifecycle_badge(self, lifecycle_id: str) -> str:
        for state in self.config.lifecycle_states:
            if state["id"] == lifecycle_id:
                return state["badge"]
        if lifecycle_id == "decided": return "🟢 已决策"
        if lifecycle_id == "pending": return "🔴 待决策"
        return "🟡 待讨论"

    def save_topic(
        self,
        topic_id: str,
        data: Dict[str, Any],
        expected_version: Optional[int] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        保存议题决策的多阶段协同流程：
        1. Topic ID 与路径安全性校验
        2. request_id 幂等性校验与重放
        3. 乐观锁并发版本核验
        4. 权威 Markdown 实体文件持久化 (Frontmatter 2.0 + 讨论轮次追加)
        5. SQLite 结构化索引与变更审计记录
        6. 派生物 metadata.json 刷新
        7. 暂存区隔离保护的 Git 语义化提交
        8. Revision 快照链记录与幂等结果缓存
        """
        topic_id = self.validate_topic_id(topic_id)
        op_id = f"op-{uuid.uuid4().hex[:8]}"

        # 1. 幂等性检查
        req_hash = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        if request_id:
            is_valid, cached_res = self.db.check_idempotency(request_id, req_hash)
            if not is_valid:
                raise IdempotencyConflictError(f"请求 ID [{request_id}] 冲突：相同 ID 携带了不同的请求数据")
            if cached_res is not None:
                cached_res["is_replay"] = True
                return cached_res

        # 2. 准备议题字段
        title = (data.get("title") or topic_id).strip()
        wf_state = data.get("workflow_state") or data.get("lifecycle_status") or "discussing"
        outcome = data.get("decision_outcome", "")
        rejection_reason = data.get("rejection_reason", "").strip()
        superseded_by = data.get("superseded_by", "").strip()
        impl_state = data.get("implementation_state") or data.get("impl_status") or "not_started"
        impl_commit = data.get("impl_commit", "").strip()
        impl_verifier = data.get("impl_verifier", "").strip()
        priority = data.get("priority", "普通")
        section = data.get("section", "未分类")
        obj = data.get("object", "通用系统")
        func = data.get("function", "核心规范")
        dec_status = data.get("decision_status", "已定" if wf_state == "decided" else "待定")
        
        user_opinion = (data.get("new_user_opinion") or data.get("user_opinion") or "").strip()
        agent_reply = (data.get("new_agent_reply") or data.get("agent_reply") or "").strip()
        commit_msg = (data.get("commit_message") or "").strip()
        content_override = data.get("content_override")

        lifecycle_badge = self.get_lifecycle_badge(wf_state)

        # 3. 读取当前 Markdown 既有轮次
        md_file = self.config.decisions_dir / f"{topic_id}.md"
        existing_doc = self.parser.parse_markdown_file(md_file)
        current_rounds = existing_doc["rounds"] if existing_doc else []
        new_round_num = len(current_rounds) + 1

        core_content = content_override if content_override is not None else (existing_doc["core_content"] if existing_doc else "")

        new_round_info = None
        if user_opinion or agent_reply or commit_msg:
            new_round_info = {
                "commit_message": commit_msg,
                "user_opinion": user_opinion,
                "agent_reply": agent_reply
            }

        # 4. 写入权威事实源 Markdown (带 Frontmatter 2.0 规范)
        md_text = self.parser.serialize_markdown(
            topic_id=topic_id,
            title=title,
            lifecycle_badge=lifecycle_badge,
            decision_status=dec_status,
            impl_status=impl_state,
            priority=priority,
            obj=obj,
            func=func,
            core_content=core_content,
            existing_rounds=current_rounds,
            new_round=new_round_info,
            workflow_state=wf_state,
            decision_outcome=outcome,
            rejection_reason=rejection_reason,
            superseded_by=superseded_by,
            implementation_state=impl_state,
            impl_commit=impl_commit,
            impl_verifier=impl_verifier,
            version=(expected_version or 1) + 1,
            section=section
        )
        self.config.decisions_dir.mkdir(parents=True, exist_ok=True)
        md_file.write_text(md_text, encoding="utf-8")

        # 5. 更新 SQLite 数据库（携带乐观锁校验）
        topic_row = self.db.get_topic(topic_id)
        discussion = json.loads(topic_row["discussion_json"]) if (topic_row and topic_row.get("discussion_json")) else []
        if user_opinion:
            discussion.append({"key": f"第 {new_round_num} 轮用户意见", "val": user_opinion})
        if agent_reply:
            discussion.append({"key": f"第 {new_round_num} 轮落实答复", "val": agent_reply})

        new_version = self.db.upsert_topic({
            "id": topic_id,
            "title": title,
            "section": section,
            "object": obj,
            "function": func,
            "lifecycle_status": wf_state,
            "workflow_state": wf_state,
            "decision_outcome": outcome,
            "rejection_reason": rejection_reason,
            "superseded_by": superseded_by,
            "implementation_state": impl_state,
            "impl_commit": impl_commit,
            "impl_verifier": impl_verifier,
            "decision_status": dec_status,
            "impl_status": impl_state,
            "priority": priority,
            "content": core_content,
            "discussion": discussion
        }, expected_version=expected_version)

        if commit_msg:
            basis_str = f"用户指示: {user_opinion[:25]}..." if user_opinion else "用户明确决策"
            self.db.record_changelog(
                scope=f"[{title}](#{topic_id})",
                change=f"{commit_msg} [{lifecycle_badge}]",
                basis=basis_str
            )

        # 6. 同步刷新 metadata.json 派生输出
        self.recovery.sync_metadata_json()

        # 7. 受控 Git 自动语义化提交（暂存区保护）
        staged_targets = [md_file, self.config.metadata_json_path, self.config.database_path]
        git_res: GitCommitResult = self.git.commit_decision(
            topic_title=title,
            lifecycle_badge=lifecycle_badge,
            summary=commit_msg,
            user_opinion=user_opinion,
            agent_reply=agent_reply,
            staged_files=staged_targets
        )

        # 8. 记录 Revision 快照
        commit_info = git_res.commit_hash if git_res.success else f"skipped_{git_res.status}"
        rev_info = self.db.commit_revision(
            action_type="RECORD_DECISION",
            summary=f"[{lifecycle_badge}] {title} - {commit_msg or '更新决策内容'}",
            topic_id=topic_id,
            author="用户",
            user_opinion=user_opinion,
            agent_reply=agent_reply,
            new_lifecycle=wf_state,
            diff_summary=f"Git: {commit_info} (v{new_version})"
        )

        # 9. 构造结构化响应
        response_payload = {
            "status": "success",
            "operation_id": op_id,
            "topic_id": topic_id,
            "title": title,
            "new_version": new_version,
            "round": new_round_num,
            "save_status": "ok",
            "export_status": "ok",
            "git_status": git_res.status,
            "commit_hash": git_res.commit_hash,
            "git_message": git_res.message,
            "unrelated_staged_files": git_res.unrelated_files,
            "revision_hash": rev_info["rev_hash"],
            "message": f"决策已入库（版本 v{new_version}）！Git 状态: {git_res.message}"
        }

        # 记录幂等结果
        if request_id:
            self.db.record_idempotency(request_id, topic_id, req_hash, response_payload)

        return response_payload

    def create_topic(self, data: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
        """创建全新议题"""
        topic_id = self.validate_topic_id(data.get("id", ""))
        existing = self.db.get_topic(topic_id)
        if existing:
            raise TopicValidationError(f"议题 ID [{topic_id}] 已存在")
        return self.save_topic(topic_id=topic_id, data=data, expected_version=None, request_id=request_id)

    def restore_single_topic(
        self,
        topic_id: str,
        rev_id: int,
        author: str = "人类/Agent",
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        P1-C: 精准恢复单个议题至历史快照状态，不波及其他议题，并保留历史操作记录
        """
        topic_id = self.validate_topic_id(topic_id)
        res = self.db.restore_topic_from_revision(topic_id, rev_id, author, reason)
        topic_data = res["topic"]

        # 写回该议题的 Markdown 文本
        md_file = self.config.decisions_dir / f"{topic_id}.md"
        lifecycle_badge = self.get_lifecycle_badge(topic_data.get("lifecycle_status", "discussing"))
        
        rounds = []
        for d in topic_data.get("discussion", []):
            rounds.append({"title": d.get("key", "历史讨论"), "content": d.get("val", "")})

        md_text = self.parser.serialize_markdown(
            topic_id=topic_id,
            title=topic_data["title"],
            lifecycle_badge=lifecycle_badge,
            decision_status=topic_data.get("decision_status", "已定"),
            impl_status=topic_data.get("impl_status", "未实现"),
            priority=topic_data.get("priority", "普通"),
            obj=topic_data.get("object", "通用系统"),
            func=topic_data.get("function", "核心规范"),
            core_content=topic_data.get("content", ""),
            existing_rounds=rounds,
            workflow_state=topic_data.get("workflow_state", "discussing"),
            decision_outcome=topic_data.get("decision_outcome", ""),
            rejection_reason=topic_data.get("rejection_reason", ""),
            superseded_by=topic_data.get("superseded_by", ""),
            implementation_state=topic_data.get("implementation_state", "not_started"),
            version=res["new_version"]
        )
        self.config.decisions_dir.mkdir(parents=True, exist_ok=True)
        md_file.write_text(md_text, encoding="utf-8")

        # 同步 metadata.json
        self.recovery.sync_metadata_json()

        # 执行受控 Git 提交
        self.git.commit_decision(
            topic_title=topic_data["title"],
            lifecycle_badge="单议题恢复",
            summary=f"恢复议题 [{topic_id}] 至历史快照 #{rev_id} ({res['restored_from']})",
            staged_files=[md_file, self.config.metadata_json_path, self.config.database_path]
        )

        return res

    def rollback_full(self, rev_id: int, author: str = "人类/Agent") -> Dict[str, Any]:
        """
        P1-C: 全库恢复至指定快照，同时确保所有 Markdown 文件与数据库完全同步
        """
        res = self.db.rollback_revision(rev_id, author)
        snapshot = res["snapshot"]

        # 写回快照中的所有 Markdown 文件
        staged_files = [self.config.metadata_json_path, self.config.database_path]
        for t in snapshot.get("topics", []):
            tid = t["id"]
            md_file = self.config.decisions_dir / f"{tid}.md"
            badge = self.get_lifecycle_badge(t.get("lifecycle_status", "discussing"))
            rounds = []
            for d in t.get("discussion", []):
                rounds.append({"title": d.get("key", "历史讨论"), "content": d.get("val", "")})

            md_text = self.parser.serialize_markdown(
                topic_id=tid,
                title=t["title"],
                lifecycle_badge=badge,
                decision_status=t.get("decision_status", "已定"),
                impl_status=t.get("impl_status", "未实现"),
                priority=t.get("priority", "普通"),
                obj=t.get("object", "通用系统"),
                func=t.get("function", "核心规范"),
                core_content=t.get("content", ""),
                existing_rounds=rounds,
                workflow_state=t.get("workflow_state", "discussing"),
                decision_outcome=t.get("decision_outcome", ""),
                rejection_reason=t.get("rejection_reason", ""),
                superseded_by=t.get("superseded_by", ""),
                implementation_state=t.get("implementation_state", "not_started"),
                version=t.get("version", 1)
            )
            md_file.write_text(md_text, encoding="utf-8")
            staged_files.append(md_file)

        # 刷新 metadata.json
        self.recovery.sync_metadata_json()

        # 递交 Git 提交
        self.git.commit_decision(
            topic_title="全库快照回滚",
            lifecycle_badge="时间旅行",
            summary=f"全库回滚至快照 #{rev_id} ({res['rolled_back_to']})",
            staged_files=staged_files
        )

        return res
