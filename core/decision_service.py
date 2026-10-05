# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Decision Service
核心业务流程协调层：创建、保存、乐观锁并发检查、幂等去重、受控提交与精准回滚
"""

import os
import shutil
import sqlite3
import json
import uuid
import hashlib
import re
import time
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

    @staticmethod
    def _atomic_replace(src: Path, dst: Path, max_retries: int = 15, delay: float = 0.02):
        """原子替换文件，在 Windows 等存在短暂文件锁的平台上提供微重试保护"""
        for i in range(max_retries):
            try:
                os.replace(src, dst)
                return
            except PermissionError:
                if i == max_retries - 1:
                    raise
                time.sleep(delay)

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

        # 1. 幂等性检查 (指纹绑定 topic_id, expected_version 与规范化 data, N05/N11)
        req_hash = hashlib.sha256(f"{topic_id}:{expected_version}:{json.dumps(data, sort_keys=True, ensure_ascii=False)}".encode("utf-8")).hexdigest()
        cached_prep = None
        if request_id:
            is_valid, cached_res = self.db.check_idempotency(request_id, topic_id, req_hash)
            if not is_valid:
                raise IdempotencyConflictError(f"请求 ID [{request_id}] 冲突：相同 ID 携带了不同的请求数据、目标议题或预期版本")
            if cached_res is not None:
                if cached_res.get("status") in ("success", "completed") or cached_res.get("save_status") == "ok":
                    return self._resume_pending_phases(cached_res, topic_id, data, request_id, req_hash)
                elif cached_res.get("status") in ("prepared", "applied"):
                    if cached_res.get("expected_version") != expected_version:
                        raise IdempotencyConflictError(f"请求 ID [{request_id}] 冲突：预期版本由 {cached_res.get('expected_version')} 变更为 {expected_version}")
                    cached_prep = cached_res

        user_opinion = (data.get("new_user_opinion") or data.get("user_opinion") or "").strip()
        agent_reply = (data.get("new_agent_reply") or data.get("agent_reply") or "").strip()
        commit_msg = (data.get("commit_message") or "").strip()
        content_override = data.get("content_override")

        # 2. 版本检查与分配：在产生任何持久副作用前先校验版本 (R02, F02, F03, F15)
        existing_row = self.db.get_topic(topic_id)
        current_db_ver = existing_row.get("version", 1) if existing_row else 1
        md_file = self.config.decisions_dir / f"{topic_id}.md"
        existing_disk_text: Optional[str] = None
        is_interrupted_prior_attempt = False
        db_already_updated = False

        max_seq = self.db.get_topic_max_version(topic_id)
        initial_version = (max_seq + 1) if max_seq > 0 else 1

        if cached_prep is not None:
            prep_allocated_ver = cached_prep.get("allocated_version")
            if (
                existing_row
                and prep_allocated_ver is not None
                and existing_row.get("version") == prep_allocated_ver
                and (existing_row.get("last_request_id") == request_id if request_id else True)
            ):
                db_already_updated = True
                is_interrupted_prior_attempt = True
                allocated_version = prep_allocated_ver
            else:
                prep_expected_ver = cached_prep.get("expected_version")
                effective_expected = expected_version if expected_version is not None else prep_expected_ver
                if existing_row:
                    current_ver = existing_row.get("version", 1)
                    if effective_expected is not None and effective_expected != current_ver:
                        raise VersionConflictError(
                            current_version=current_ver,
                            expected_version=effective_expected,
                            topic_id=topic_id
                        )
                else:
                    if expected_version is not None and expected_version != initial_version:
                        raise VersionConflictError(
                            current_version=max_seq,
                            expected_version=expected_version,
                            topic_id=topic_id
                        )
                is_interrupted_prior_attempt = True
                allocated_version = prep_allocated_ver if prep_allocated_ver is not None else (current_db_ver + 1 if existing_row else initial_version)
        else:
            if existing_row:
                current_ver = existing_row.get("version", 1)
                if expected_version is not None and expected_version != current_ver:
                    raise VersionConflictError(
                        current_version=current_ver,
                        expected_version=expected_version,
                        topic_id=topic_id
                    )
                allocated_version = current_ver + 1
            else:
                if expected_version is not None and expected_version != initial_version:
                    raise VersionConflictError(
                        current_version=max_seq,
                        expected_version=expected_version,
                        topic_id=topic_id
                    )
                allocated_version = initial_version

        if md_file.exists():
            try:
                existing_disk_text = md_file.read_text(encoding="utf-8")
                parsed_disk = self.parser.parse_markdown_file(md_file)
                if parsed_disk:
                    disk_ver = parsed_disk.get("version", 1)
                    if is_interrupted_prior_attempt:
                        # 属于同一请求的中断续做：如果磁盘版本等于预分配版本或预期版本，均视为合法
                        if disk_ver not in (allocated_version, expected_version):
                            raise VersionConflictError(
                                current_version=disk_ver,
                                expected_version=expected_version,
                                topic_id=topic_id
                            )
                    else:
                        # 全新请求或不同请求：磁盘版本必须严格与预期版本一致
                        if expected_version is not None and disk_ver != expected_version:
                            raise VersionConflictError(
                                current_version=disk_ver,
                                expected_version=expected_version,
                                topic_id=topic_id
                            )
                        elif existing_row:
                            # 全量检测未入库的权威正文或元数据漂移 (F15, F09)
                            db_wf = existing_row.get("workflow_state") or existing_row.get("lifecycle_status", "decided")
                            disk_wf = parsed_disk.get("workflow_state") or parsed_disk.get("lifecycle_status", "decided")
                            fields_to_check = [
                                (parsed_disk.get("title"), existing_row.get("title")),
                                (parsed_disk.get("core_content", "").strip(), existing_row.get("content", "").strip()),
                                (parsed_disk.get("decision_outcome", "accepted"), existing_row.get("decision_outcome", "accepted")),
                                (parsed_disk.get("rejection_reason", "").strip(), existing_row.get("rejection_reason", "").strip()),
                                (disk_wf, db_wf),
                                (parsed_disk.get("section", "未分类"), existing_row.get("section", "未分类")),
                                (parsed_disk.get("implementation_state", "not_started"), existing_row.get("implementation_state", "not_started")),
                            ]
                            if any(d_val != b_val for d_val, b_val in fields_to_check):
                                raise VersionConflictError(
                                    current_version=disk_ver,
                                    expected_version=expected_version,
                                    topic_id=topic_id
                                )
            except VersionConflictError:
                raise
            except Exception:
                pass

        # 3. 准备议题字段与业务合法性校验
        title = (data.get("title") or topic_id).strip()
        wf_state = data.get("workflow_state") or data.get("lifecycle_status") or "discussing"
        outcome = data.get("decision_outcome", "")
        rejection_reason = data.get("rejection_reason", "").strip()
        superseded_by = data.get("superseded_by", "").strip()

        # 否决状态强制校验否决原因 (R09)
        if outcome == "rejected" and not rejection_reason:
            raise TopicValidationError("议题状态标记为已否决 (rejected) 时，必须填写具体的否决原因 (rejection_reason)")

        impl_state = data.get("implementation_state") or data.get("impl_status") or "not_started"

        # 保留原值策略 (R06)：区分未提供与显式清空，防止普通保存清空原有核验与替代信息
        if existing_row:
            impl_commit = data["impl_commit"].strip() if "impl_commit" in data else existing_row.get("impl_commit", "")
            impl_verifier = data["impl_verifier"].strip() if "impl_verifier" in data else existing_row.get("impl_verifier", "")
            if "superseded_by" not in data:
                superseded_by = existing_row.get("superseded_by", "")
            if "rejection_reason" not in data:
                rejection_reason = existing_row.get("rejection_reason", "")
            if "section" not in data:
                section = existing_row.get("section", "未分类")
            else:
                section = data.get("section", "未分类")
            if "object" not in data:
                obj = existing_row.get("object", "通用系统")
            else:
                obj = data.get("object", "通用系统")
            if "function" not in data:
                func = existing_row.get("function", "核心规范")
            else:
                func = data.get("function", "核心规范")
            if "priority" not in data:
                priority = existing_row.get("priority", "普通")
            else:
                priority = data.get("priority", "普通")
        else:
            impl_commit = data.get("impl_commit", "").strip()
            impl_verifier = data.get("impl_verifier", "").strip()
            section = data.get("section", "未分类")
            obj = data.get("object", "通用系统")
            func = data.get("function", "核心规范")
            priority = data.get("priority", "普通")

        dec_status = data.get("decision_status", "已定" if wf_state == "decided" else "待定")
        lifecycle_badge = self.get_lifecycle_badge(wf_state)

        # 4. 在对权威文件产生修改前，持久记录操作准备状态与预分配版本 (F02)
        target_expected_version = expected_version if expected_version is not None else (existing_row.get("version") if existing_row else None)
        if request_id and not cached_prep:
            prep_payload = {
                "status": "prepared",
                "operation_id": op_id,
                "topic_id": topic_id,
                "expected_version": target_expected_version,
                "allocated_version": allocated_version,
                "title": title,
                "save_status": "pending",
                "export_status": "pending",
                "git_status": "pending"
            }
            self.db.record_idempotency(request_id, topic_id, req_hash, prep_payload, status="prepared")

        # 5. 读取既有 Markdown 与历史轮次
        existing_doc = self.parser.parse_markdown_file(md_file)
        current_rounds = existing_doc["rounds"] if existing_doc else []

        # 幂等重试防护：只有确认属于同一请求的中断重试，且磁盘文件已包含上一轮讨论时，才去重该轮次 (F01, F02, U09)
        is_duplicate_round = False
        disk_ver = existing_doc.get("version") if existing_doc else None
        if is_interrupted_prior_attempt and disk_ver == allocated_version and current_rounds and (user_opinion or agent_reply or commit_msg):
            last_r = current_rounds[-1]
            last_u = (last_r.get("user_opinion") or "").strip()
            last_a = (last_r.get("agent_reply") or "").strip()
            last_c = (last_r.get("commit_message") or "").strip()
            if (not user_opinion or user_opinion == last_u) and \
               (not agent_reply or agent_reply == last_a) and \
               (not commit_msg or commit_msg == last_c):
                is_duplicate_round = True

        new_round_num = len(current_rounds) + (0 if is_duplicate_round else 1)
        core_content = content_override if content_override is not None else (existing_doc["core_content"] if existing_doc else "")

        new_round_info = None
        if (user_opinion or agent_reply or commit_msg) and not is_duplicate_round:
            new_round_info = {
                "commit_message": commit_msg,
                "user_opinion": user_opinion,
                "agent_reply": agent_reply
            }

        # 序列化 Markdown 并原子化写入磁盘 (临时文件 + os.replace)
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
            version=allocated_version,
            section=section
        )
        self.config.decisions_dir.mkdir(parents=True, exist_ok=True)
        temp_file = md_file.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
        try:
            temp_file.write_text(md_text, encoding="utf-8")
            self._atomic_replace(temp_file, md_file)
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

        # 6. 更新 SQLite 数据库结构化索引
        # 优先基于权威 Markdown 既有轮次构建，确保手工直接修改的讨论内容不被陈旧的数据库字段覆盖 (F05, U11)
        discussion = []
        if existing_doc and existing_doc.get("rounds"):
            for r in existing_doc["rounds"]:
                rnd = r.get("round", len(discussion) + 1)
                c_msg = (r.get("commit_message") or "").strip()
                u_op = (r.get("user_opinion") or "").strip()
                a_rep = (r.get("agent_reply") or "").strip()
                if c_msg:
                    discussion.append({"key": f"第 {rnd} 轮变更说明", "val": c_msg})
                if u_op:
                    discussion.append({"key": f"第 {rnd} 轮用户意见", "val": u_op})
                if a_rep:
                    discussion.append({"key": f"第 {rnd} 轮落实答复", "val": a_rep})
        elif existing_row and existing_row.get("discussion_json"):
            discussion = json.loads(existing_row["discussion_json"])
        
        has_commit = any(d.get("key") == f"第 {new_round_num} 轮变更说明" for d in discussion)
        has_opinion = any(d.get("key") == f"第 {new_round_num} 轮用户意见" for d in discussion)
        has_reply = any(d.get("key") == f"第 {new_round_num} 轮落实答复" for d in discussion)

        if commit_msg and not has_commit:
            discussion.append({"key": f"第 {new_round_num} 轮变更说明", "val": commit_msg})
        if user_opinion and not has_opinion:
            discussion.append({"key": f"第 {new_round_num} 轮用户意见", "val": user_opinion})
        if agent_reply and not has_reply:
            discussion.append({"key": f"第 {new_round_num} 轮落实答复", "val": agent_reply})

        if not db_already_updated:
            try:
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
                }, expected_version=target_expected_version, exact_version=allocated_version, request_id=request_id)
            except VersionConflictError:
                try:
                    with self.db.get_connection() as conn:
                        row = conn.cursor().execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
                        latest_row = dict(row) if row else None
                except Exception:
                    latest_row = None
                if latest_row and latest_row.get("version", 0) > (target_expected_version or 0):
                    self._sync_disk_from_db_row(topic_id, latest_row)
                elif existing_disk_text is not None:
                    try:
                        md_file.write_text(existing_disk_text, encoding="utf-8")
                    except Exception:
                        pass
                raise
        else:
            new_version = allocated_version

        if commit_msg:
            basis_str = f"用户指示: {user_opinion[:25]}..." if user_opinion else "用户明确决策"
            self.db.record_changelog(
                scope=f"[{title}](#{topic_id})",
                change=f"{commit_msg} [{lifecycle_badge}]",
                basis=basis_str
            )

        # 6.5. 获取保存前最新的历史快照 ID 作为防手滑撤销基线 (F01)
        prev_revs = self.db.get_revisions(limit=1, topic_id=topic_id)
        if not prev_revs:
            prev_revs = self.db.get_revisions(limit=1)
        prior_rev_id = prev_revs[0]["rev_id"] if prev_revs else None

        # 7. 提交 Revision 快照（在 Git 暂存 decisions.db 之前写入 DB，确保 Revision 进入 Git HEAD） (R10)
        rev_info = self.db.commit_revision(
            action_type="RECORD_DECISION",
            summary=f"[{lifecycle_badge}] {title} - {commit_msg or '更新决策内容'}",
            topic_id=topic_id,
            author="用户",
            user_opinion=user_opinion,
            agent_reply=agent_reply,
            new_lifecycle=wf_state,
            diff_summary=f"v{new_version}"
        )

        # 核心落盘后记录幂等中间状态
        preliminary_payload = {
            "status": "success",
            "operation_id": op_id,
            "topic_id": topic_id,
            "title": title,
            "new_version": new_version,
            "previous_version": current_db_ver if existing_row else None,
            "prior_rev_id": prior_rev_id,
            "round": new_round_num,
            "save_status": "ok",
            "export_status": "pending",
            "git_status": "pending",
            "revision_hash": rev_info["rev_hash"]
        }
        if request_id:
            self.db.record_idempotency(request_id, topic_id, req_hash, preliminary_payload, status="applied")

        # 8. 同步刷新 metadata.json 派生输出
        export_status = "ok"
        try:
            self.recovery.sync_metadata_json()
        except Exception:
            export_status = "failed"
            if request_id:
                preliminary_payload["export_status"] = "failed"
                self.db.record_idempotency(request_id, topic_id, req_hash, preliminary_payload, status="applied")
            raise

        # 9. 受控 Git 自动语义化提交（暂存区保护）
        staged_targets = [md_file, self.config.metadata_json_path, self.config.database_path]
        git_res: GitCommitResult = self.git.commit_decision(
            topic_title=title,
            lifecycle_badge=lifecycle_badge,
            summary=commit_msg,
            user_opinion=user_opinion,
            agent_reply=agent_reply,
            staged_files=staged_targets
        )

        response_payload = {
            "status": "success",
            "operation_id": op_id,
            "topic_id": topic_id,
            "title": title,
            "new_version": new_version,
            "previous_version": current_db_ver if existing_row else None,
            "prior_rev_id": prior_rev_id,
            "round": new_round_num,
            "save_status": "ok",
            "export_status": export_status,
            "git_status": git_res.status,
            "commit_hash": git_res.commit_hash,
            "git_message": git_res.message,
            "unrelated_staged_files": git_res.unrelated_files,
            "revision_hash": rev_info["rev_hash"],
            "message": f"决策已入库（版本 v{new_version}）！Git 状态: {git_res.message}"
        }

        # 记录已完成的最终幂等结果
        if request_id:
            self.db.record_idempotency(request_id, topic_id, req_hash, response_payload, status="completed")

        return response_payload

    def create_topic(self, data: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
        """创建全新议题，幂等重放检查优先于已存在检查 (R07)"""
        topic_id = self.validate_topic_id(data.get("id", ""))
        
        # 1. 幂等优先：若此请求 ID 之前已成功创建该议题，直接重放结果
        cached_res = None
        if request_id:
            req_hash = hashlib.sha256(f"{topic_id}:None:{json.dumps(data, sort_keys=True, ensure_ascii=False)}".encode("utf-8")).hexdigest()
            is_valid, cached_res = self.db.check_idempotency(request_id, topic_id, req_hash)
            if not is_valid:
                raise IdempotencyConflictError(f"请求 ID [{request_id}] 冲突：相同 ID 携带了不同的请求数据或目标议题")
            if cached_res is not None and (cached_res.get("status") in ("success", "completed") or cached_res.get("save_status") == "ok"):
                return self._resume_pending_phases(cached_res, topic_id, data, request_id, req_hash)

        # 2. 检查议题存在性 (若已存在且并非同一未完成请求的重试，则报错)
        existing = self.db.get_topic(topic_id)
        if existing and not (cached_res and cached_res.get("status") in ("prepared", "applied")):
            raise TopicValidationError(f"议题 ID [{topic_id}] 已存在")
        return self.save_topic(topic_id=topic_id, data=data, expected_version=None, request_id=request_id)

    def _resume_pending_phases(
        self,
        cached_res: Dict[str, Any],
        topic_id: str,
        data: Dict[str, Any],
        request_id: str,
        req_hash: str
    ) -> Dict[str, Any]:
        """幂等重放时自动续做并补偿未完成的导出与 Git 提交阶段 (F04, F08)"""
        # 1. 导出补偿
        if cached_res.get("export_status") != "ok":
            try:
                self.recovery.sync_metadata_json()
                cached_res["export_status"] = "ok"
            except Exception:
                pass

        # 2. Git 提交补偿
        if cached_res.get("git_status") == "pending" and self.config.git_commit_enabled:
            try:
                md_file = self.config.decisions_dir / f"{topic_id}.md"
                staged_targets = [md_file, self.config.database_path]
                if self.config.metadata_json_path.exists():
                    staged_targets.append(self.config.metadata_json_path)
                user_op = (data.get("new_user_opinion") or data.get("user_opinion") or "").strip()
                agent_rep = (data.get("new_agent_reply") or data.get("agent_reply") or "").strip()
                commit_m = (data.get("commit_message") or "").strip()
                git_res = self.git.commit_decision(
                    topic_title=cached_res.get("title", data.get("title", topic_id)),
                    lifecycle_badge=self.get_lifecycle_badge(cached_res.get("workflow_state", "discussing")),
                    summary=commit_m,
                    user_opinion=user_op,
                    agent_reply=agent_rep,
                    staged_files=staged_targets
                )
                cached_res["git_status"] = git_res.status
                if git_res.commit_hash:
                    cached_res["commit_hash"] = git_res.commit_hash
                if git_res.message:
                    cached_res["git_message"] = git_res.message
            except Exception:
                pass

        self.db.record_idempotency(request_id, topic_id, req_hash, cached_res, status="completed")
        cached_res["is_replay"] = True
        return cached_res

    def _reconstruct_rounds_from_topic(self, topic_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从议题快照数据无损重构讨论轮次，防止 Q&A 拆裂为伪轮次 (R06)"""
        if "rounds" in topic_data and isinstance(topic_data["rounds"], list) and topic_data["rounds"]:
            return topic_data["rounds"]

        discussion = topic_data.get("discussion") or topic_data.get("discussion_json") or []
        if isinstance(discussion, str):
            try:
                discussion = json.loads(discussion)
            except Exception:
                discussion = []

        rounds_map: Dict[int, Dict[str, Any]] = {}
        unmatched_items: List[Dict[str, Any]] = []

        for d in discussion:
            k = d.get("key", "")
            v = d.get("val", "")
            m = re.search(r'第\s*(\d+)\s*轮', k)
            if m:
                r_num = int(m.group(1))
                if r_num not in rounds_map:
                    rounds_map[r_num] = {
                        "title": f"第 {r_num} 轮定案与要求",
                        "user_opinion": "",
                        "agent_reply": "",
                        "commit_message": ""
                    }
                if "用户" in k:
                    rounds_map[r_num]["user_opinion"] = v
                elif "答复" in k or "落实" in k:
                    rounds_map[r_num]["agent_reply"] = v
                elif "变更" in k:
                    rounds_map[r_num]["commit_message"] = v
                else:
                    if rounds_map[r_num]["user_opinion"]:
                        rounds_map[r_num]["user_opinion"] += "\n" + v
                    else:
                        rounds_map[r_num]["user_opinion"] = v
            else:
                unmatched_items.append({"title": k or "历史讨论", "content": v})

        result = []
        for r_num in sorted(rounds_map.keys()):
            r_info = rounds_map[r_num]
            content_parts = []
            if r_info["commit_message"]:
                content_parts.append(f"- **变更说明**：{r_info['commit_message']}")
            if r_info["user_opinion"]:
                content_parts.append(f"- **💡 用户意见（最新原话）**：\n\n{r_info['user_opinion']}\n")
            if r_info["agent_reply"]:
                content_parts.append(f"- **🤖 团队答复（落实说明）**：\n\n{r_info['agent_reply']}\n")
            result.append({
                "title": r_info["title"],
                "content": "\n".join(content_parts).strip(),
                "user_opinion": r_info["user_opinion"],
                "agent_reply": r_info["agent_reply"],
                "commit_message": r_info["commit_message"]
            })

        for item in unmatched_items:
            result.append(item)

        return result

    def _sync_disk_from_db_row(self, topic_id: str, row: Dict[str, Any]):
        """根据数据库获胜行同步磁盘 Markdown 文件，防止落败写入者覆盖获胜者 (F03)"""
        try:
            wf_state = row.get("workflow_state") or row.get("lifecycle_status", "discussing")
            lifecycle_badge = self.get_lifecycle_badge(wf_state)
            rounds = self._reconstruct_rounds_from_topic(row)
            md_text = self.parser.serialize_markdown(
                topic_id=topic_id,
                title=row.get("title", topic_id),
                lifecycle_badge=lifecycle_badge,
                decision_status=row.get("decision_status", "已定"),
                impl_status=row.get("impl_status", "未实现"),
                priority=row.get("priority", "普通"),
                obj=row.get("object", "通用系统"),
                func=row.get("function", "核心规范"),
                core_content=row.get("content", ""),
                existing_rounds=rounds,
                workflow_state=wf_state,
                decision_outcome=row.get("decision_outcome", ""),
                rejection_reason=row.get("rejection_reason", ""),
                superseded_by=row.get("superseded_by", ""),
                implementation_state=row.get("implementation_state", "not_started"),
                impl_commit=row.get("impl_commit", ""),
                impl_verifier=row.get("impl_verifier", ""),
                version=row.get("version", 1),
                section=row.get("section", "未分类")
            )
            md_file = self.config.decisions_dir / f"{topic_id}.md"
            self.config.decisions_dir.mkdir(parents=True, exist_ok=True)
            temp_file = md_file.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
            temp_file.write_text(md_text, encoding="utf-8")
            self._atomic_replace(temp_file, md_file)
        except Exception:
            pass

    def restore_single_topic(
        self,
        topic_id: str,
        rev_id: int,
        author: str = "人类/Agent",
        reason: str = "",
        expected_version: Optional[int] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        P1-C: 精准恢复单个议题至历史快照状态，不波及其他议题，并保留完整字段与轮次结构 (R06, F02, F06, F07, F08)
        """
        topic_id = self.validate_topic_id(topic_id)

        # 1. 幂等性校验 (F08, U04, N07)
        req_hash = hashlib.sha256(f"{topic_id}:restore:{rev_id}".encode("utf-8")).hexdigest()
        cached_res = None
        if request_id:
            is_valid, cached_res = self.db.check_idempotency(request_id, topic_id, req_hash)
            if not is_valid:
                raise IdempotencyConflictError(f"请求 ID [{request_id}] 冲突：相同 ID 携带了不同的恢复目标快照或目标议题")
            if cached_res is not None:
                if (cached_res.get("status") in ("success", "completed") and cached_res.get("git_status") not in (None, "pending")):
                    return cached_res
                if cached_res.get("status") == "applied" or cached_res.get("git_status") == "pending":
                    # 断点续做：补偿后续未完成的元数据导出与 Git 提交阶段 (N01, N02)
                    self.recovery.sync_metadata_json()
                    cached_res["export_status"] = "ok"
                    git_res = self.git.commit_decision(
                        topic_title=cached_res.get("topic", {}).get("title") if cached_res.get("topic") else f"撤销议题 {topic_id}",
                        lifecycle_badge="单议题恢复" if cached_res.get("topic") else "撤销创建",
                        summary=f"恢复议题 [{topic_id}] 至历史快照 #{rev_id} ({cached_res.get('restored_from', '')})",
                        staged_files=[self.config.decisions_dir / f"{topic_id}.md", self.config.metadata_json_path, self.config.database_path]
                    )
                    cached_res["git_status"] = git_res.status
                    cached_res["commit_hash"] = git_res.commit_hash or "none"
                    cached_res["git_message"] = git_res.message
                    cached_res["status"] = "success"
                    self.db.record_idempotency(request_id, topic_id, req_hash, cached_res, status="completed")
                    return cached_res

        # 2. 版本前置乐观锁核验 (F02, U03) 与断点续做 (R03, R04, N07, N08)
        current_topic = self.db.get_topic(topic_id)
        current = current_topic
        current_ver = current_topic.get("version", 1) if current_topic else 0

        # 如果当前议题已经由本 request_id 完成写入（可能在 commit_revision 前崩溃或已写入 DB）
        if request_id and current_topic and current_topic.get("last_request_id") == request_id:
            rev_row = self.db.get_revision_by_id(rev_id)
            if not rev_row:
                raise ValueError(f"未找到指定的版本快照 #{rev_id}")

            snapshot = json.loads(rev_row["snapshot_json"])
            target_topic = next((t for t in snapshot.get("topics", []) if t["id"] == topic_id), None)
            if target_topic and current_topic.get("title") != target_topic.get("title"):
                raise IdempotencyConflictError(f"请求 ID [{request_id}] 冲突：目标快照 #{rev_id} 与已落盘议题不匹配")

            rev_list = self.db.get_revisions(limit=10, topic_id=topic_id)
            has_restore_rev = any(
                r.get("action_type") == "TOPIC_RESTORE" and f"rev_id={rev_id}" in (r.get("diff_summary") or "")
                for r in rev_list
            )
            conflict_rev = next(
                (r for r in rev_list if r.get("action_type") == "TOPIC_RESTORE" and "rev_id=" in (r.get("diff_summary") or "") and f"rev_id={rev_id}" not in (r.get("diff_summary") or "")),
                None
            )
            if conflict_rev:
                raise IdempotencyConflictError(f"请求 ID [{request_id}] 冲突：该请求已被记录为其他恢复操作，不能别名到 #{rev_id}")

            if not has_restore_rev:
                new_rev = self.db.commit_revision(
                    action_type="TOPIC_RESTORE",
                    summary=f"针对性恢复议题 [{current_topic['title']}] 至快照 {rev_row['rev_hash']} (断点补偿)",
                    topic_id=topic_id,
                    author=author,
                    diff_summary=f"restore_of={rev_row['rev_hash']}, rev_id={rev_id}, reason={reason or '用户按议题精准撤销 (断点补偿)'}"
                )
                latest_rev_hash = new_rev["rev_hash"]
            else:
                latest_rev_hash = rev_list[0]["rev_hash"]

            self.recovery.sync_metadata_json()
            res = {
                "status": "success",
                "topic": current_topic,
                "new_version": current_topic["version"],
                "restored_from": rev_row["rev_hash"],
                "new_revision": latest_rev_hash,
                "message": f"议题 [{topic_id}] 已成功恢复至快照（重放确认）"
            }
            git_res = self.git.commit_decision(
                topic_title=current_topic["title"],
                lifecycle_badge=self.get_lifecycle_badge(current_topic.get("workflow_state") or current_topic.get("lifecycle_status", "discussing")),
                summary=f"恢复议题 [{topic_id}] 至历史快照 #{rev_id} ({rev_row['rev_hash']})",
                staged_files=[self.config.decisions_dir / f"{topic_id}.md", self.config.metadata_json_path, self.config.database_path]
            )
            res["git_status"] = git_res.status
            res["commit_hash"] = git_res.commit_hash or "none"
            res["git_message"] = git_res.message
            self.db.record_idempotency(request_id, topic_id, req_hash, res, status="completed")
            return res

        # 针对撤销创建的断点续做（数据库中该议题已被删除） (N02)
        if request_id and current_topic is None:
            rev_list = self.db.get_revisions(limit=5, topic_id=topic_id)
            undo_rev = next((r for r in rev_list if r.get("action_type") == "TOPIC_REMOVE" and f"undo_creation_of={topic_id}" in (r.get("diff_summary") or "") and f"rev_id={rev_id}" in (r.get("diff_summary") or "")), None)
            if undo_rev:
                self.recovery.sync_metadata_json()
                res = {
                    "status": "success",
                    "topic": None,
                    "new_version": 0,
                    "restored_from": f"rev-{rev_id}",
                    "new_revision": undo_rev["rev_hash"],
                    "message": f"议题 [{topic_id}] 已成功撤销创建（重放确认）"
                }
                git_res = self.git.commit_decision(
                    topic_title=f"撤销议题 {topic_id}",
                    lifecycle_badge="撤销创建",
                    summary=f"撤销新建议题 [{topic_id}]（回退至未创建快照 #{rev_id}）",
                    staged_files=[self.config.decisions_dir / f"{topic_id}.md", self.config.metadata_json_path, self.config.database_path]
                )
                res["git_status"] = git_res.status
                res["commit_hash"] = git_res.commit_hash or "none"
                res["git_message"] = git_res.message
                self.db.record_idempotency(request_id, topic_id, req_hash, res, status="completed")
                return res

        if expected_version is not None and expected_version != current_ver:
            raise VersionConflictError(
                current_version=current_ver,
                expected_version=expected_version,
                topic_id=topic_id
            )

        # 3. 读取目标快照
        rev_row = self.db.get_revision_by_id(rev_id)
        if not rev_row:
            raise ValueError(f"未找到指定的版本快照 #{rev_id}")

        snapshot = json.loads(rev_row["snapshot_json"])
        target_topic = None
        for t in snapshot.get("topics", []):
            if t["id"] == topic_id:
                target_topic = t
                break

        md_file = self.config.decisions_dir / f"{topic_id}.md"
        old_file_bytes = md_file.read_bytes() if md_file.exists() else None

        # 4. 判断恢复语义：快照中存在该议题 vs 快照中无该议题（撤销创建）(F07, U02)
        if target_topic is not None:
            # 单议题正常回溯
            new_version = max(self.db.get_topic_max_version(topic_id), current_ver) + 1
            wf_state = target_topic.get("workflow_state") or target_topic.get("lifecycle_status", "discussing")
            lifecycle_badge = self.get_lifecycle_badge(wf_state)
            rounds = self._reconstruct_rounds_from_topic(target_topic)

            md_text = self.parser.serialize_markdown(
                topic_id=topic_id,
                title=target_topic["title"],
                lifecycle_badge=lifecycle_badge,
                decision_status=target_topic.get("decision_status", "已定"),
                impl_status=target_topic.get("impl_status", "未实现"),
                priority=target_topic.get("priority", "普通"),
                obj=target_topic.get("object", "通用系统"),
                func=target_topic.get("function", "核心规范"),
                core_content=target_topic.get("content", ""),
                existing_rounds=rounds,
                workflow_state=wf_state,
                decision_outcome=target_topic.get("decision_outcome", ""),
                rejection_reason=target_topic.get("rejection_reason", ""),
                superseded_by=target_topic.get("superseded_by", ""),
                implementation_state=target_topic.get("implementation_state", "not_started"),
                impl_commit=target_topic.get("impl_commit", ""),
                impl_verifier=target_topic.get("impl_verifier", ""),
                version=new_version,
                section=target_topic.get("section", "未分类")
            )
            self.config.decisions_dir.mkdir(parents=True, exist_ok=True)
            temp_file = md_file.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
            try:
                temp_file.write_text(md_text, encoding="utf-8")
                # 文件原子替换在数据库修改前执行 (F06, U05)
                self._atomic_replace(temp_file, md_file)
            finally:
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass

            db_applied = False
            try:
                self.db.upsert_topic(target_topic, expected_version=expected_version, exact_version=new_version, request_id=request_id)
                db_applied = True
                new_rev = self.db.commit_revision(
                    action_type="TOPIC_RESTORE",
                    summary=f"针对性恢复议题 [{target_topic['title']}] 至快照 {rev_row['rev_hash']}",
                    topic_id=topic_id,
                    author=author,
                    diff_summary=f"restore_of={rev_row['rev_hash']}, rev_id={rev_id}, reason={reason or '用户按议题精准撤销'}"
                )
            except VersionConflictError:
                # 乐观锁冲突：获胜写入者已先于本操作入库，绝不能用陈旧字节回滚覆盖获胜者的磁盘文件 (F07, N04)
                latest_row = self.db.get_topic(topic_id)
                if latest_row and latest_row.get("version", 0) > (expected_version or 0):
                    self._sync_disk_from_db_row(topic_id, latest_row)
                elif old_file_bytes is not None:
                    md_file.write_bytes(old_file_bytes)
                raise
            except Exception:
                # 数据库写入或审计失败时，将 DB 与 Markdown 均恢复到操作前基线 (R01, R05)
                if old_file_bytes is not None:
                    md_file.write_bytes(old_file_bytes)
                elif md_file.exists():
                    try:
                        md_file.unlink()
                    except OSError:
                        pass
                if db_applied:
                    if current:
                        self.db.upsert_topic(
                            current,
                            exact_version=current["version"],
                            request_id=current.get("last_request_id")
                        )
                    else:
                        with self.db.get_connection() as c:
                            c.cursor().execute("DELETE FROM topics WHERE id = ?", (topic_id,))
                            c.commit()
                raise

            res = {
                "status": "applied",
                "topic": target_topic,
                "new_version": new_version,
                "restored_from": rev_row["rev_hash"],
                "new_revision": new_rev["rev_hash"],
                "git_status": "pending",
                "export_status": "pending",
                "message": f"议题 [{topic_id}] 已成功恢复至快照 {rev_row['rev_hash']}"
            }
            if request_id:
                self.db.record_idempotency(request_id, topic_id, req_hash, res, status="applied")
        else:
            # 撤销新建议题 (F07, U02)
            archive_dir = self.config.decisions_dir / ".archived_rollback"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_target = archive_dir / f"{topic_id}_{uuid.uuid4().hex[:6]}.md"
            if md_file.exists():
                shutil.move(str(md_file), str(archive_target))

            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    if expected_version is not None:
                        cursor.execute("DELETE FROM topics WHERE id = ? AND version = ?", (topic_id, expected_version))
                    else:
                        cursor.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
                    if cursor.rowcount == 0:
                        cur_row = self.db.get_topic(topic_id)
                        cur_v = cur_row.get("version", 0) if cur_row else 0
                        raise VersionConflictError(current_version=cur_v, expected_version=expected_version, topic_id=topic_id)
                    conn.commit()

                new_rev = self.db.commit_revision(
                    action_type="TOPIC_REMOVE",
                    summary=f"撤销新建议题 [{topic_id}]（回退至未创建快照 {rev_row['rev_hash']}）",
                    topic_id=topic_id,
                    author=author,
                    diff_summary=f"undo_creation_of={topic_id}, rev_id={rev_id}"
                )
            except Exception:
                if archive_target.exists():
                    shutil.move(str(archive_target), str(md_file))
                if current:
                    self.db.upsert_topic(
                        current,
                        exact_version=current["version"],
                        request_id=current.get("last_request_id")
                    )
                latest_row = self.db.get_topic(topic_id)
                if latest_row:
                    self._sync_disk_from_db_row(topic_id, latest_row)
                raise

            res = {
                "status": "applied",
                "topic": None,
                "new_version": 0,
                "restored_from": rev_row["rev_hash"],
                "new_revision": new_rev["rev_hash"],
                "git_status": "pending",
                "export_status": "pending",
                "message": f"议题 [{topic_id}] 已成功撤销创建（回退至快照 {rev_row['rev_hash']}）"
            }
            if request_id:
                self.db.record_idempotency(request_id, topic_id, req_hash, res, status="applied")

        # 5. 同步 metadata.json
        self.recovery.sync_metadata_json()
        res["export_status"] = "ok"

        # 6. 执行受控 Git 提交并透传结果 (F08, U12)
        git_res = self.git.commit_decision(
            topic_title=target_topic["title"] if target_topic else f"撤销议题 {topic_id}",
            lifecycle_badge="单议题恢复" if target_topic else "撤销创建",
            summary=f"恢复议题 [{topic_id}] 至历史快照 #{rev_id} ({rev_row['rev_hash']})",
            staged_files=[md_file, self.config.metadata_json_path, self.config.database_path]
        )
        res["git_status"] = git_res.status
        res["commit_hash"] = git_res.commit_hash or "none"
        res["git_message"] = git_res.message

        res["status"] = "success"
        if request_id:
            self.db.record_idempotency(request_id, topic_id, req_hash, res, status="completed")

        return res

    def rollback_full(self, rev_id: int, author: str = "人类/Agent") -> Dict[str, Any]:
        """
        P1-C: 全库恢复至指定快照，同时清理目标快照外的多余文件并保持字段完整 (R05, R06, F04, F06)
        """
        # 0. 预检快照有效性及路径安全，在产生任何状态变更前完成强校验 (F04, I07)
        rev_row = self.db.get_revision_by_id(rev_id)
        if not rev_row:
            raise ValueError(f"未找到指定的版本快照 #{rev_id}")
        snapshot = json.loads(rev_row["snapshot_json"])
        target_topics = snapshot.get("topics", [])
        resolved_decisions_dir = self.config.decisions_dir.resolve()

        for t in target_topics:
            tid = t.get("id", "")
            if not re.match(r'^[a-zA-Z0-9_\-]+$', tid):
                raise ValueError(f"快照中包含非法的议题 ID: [{tid}]")
            md_file = (self.config.decisions_dir / f"{tid}.md").resolve()
            try:
                md_file.relative_to(resolved_decisions_dir)
            except ValueError:
                raise ValueError(f"检测到非法路径越界: [{tid}]")

        target_ids = {t["id"] for t in target_topics}

        # 备份数据库文件与当前 live 文件，以实现真正的原子性故障回滚 (U06, U07, R06, R12)
        db_path = self.config.database_path
        db_backup = db_path.with_suffix(f".bak.{uuid.uuid4().hex[:8]}")
        bak_conn = None
        try:
            bak_conn = sqlite3.connect(str(db_backup))
            with self.db.get_connection() as live_conn:
                live_conn.backup(bak_conn)
        except Exception:
            shutil.copy2(db_path, db_backup)
        finally:
            if bak_conn is not None:
                bak_conn.close()

        orig_metadata_bytes = self.config.metadata_json_path.read_bytes() if self.config.metadata_json_path.exists() else None

        live_backups = {}
        if self.config.decisions_dir.exists():
            for p in self.config.decisions_dir.glob("*.md"):
                live_backups[p.name] = p.read_bytes()

        archive_dir = self.config.decisions_dir / ".archived_rollback"
        archived_moves = []
        staged_files = [self.config.metadata_json_path, self.config.database_path]

        try:
            # 1. 归档快照之外的多余文件
            if self.config.decisions_dir.exists():
                for p in self.config.decisions_dir.glob("*.md"):
                    if p.stem not in target_ids:
                        archive_dir.mkdir(parents=True, exist_ok=True)
                        archive_target = archive_dir / f"{p.stem}_{uuid.uuid4().hex[:6]}.md"
                        shutil.move(str(p), str(archive_target))
                        archived_moves.append((archive_target, p))
                        staged_files.append(p)

            # 2. 校验与文件归档全部成功后，原子执行数据库回滚
            res = self.db.rollback_revision(rev_id, author)
            target_topics = res.get("snapshot", {}).get("topics", [])

            # 3. 写回快照中的所有 Markdown 文件 (原子替换并保持完整字段)
            for t in target_topics:
                tid = t["id"]
                md_file = (self.config.decisions_dir / f"{tid}.md").resolve()
                wf_state = t.get("workflow_state") or t.get("lifecycle_status", "discussing")
                badge = self.get_lifecycle_badge(wf_state)
                rounds = self._reconstruct_rounds_from_topic(t)

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
                    workflow_state=wf_state,
                    decision_outcome=t.get("decision_outcome", ""),
                    rejection_reason=t.get("rejection_reason", ""),
                    superseded_by=t.get("superseded_by", ""),
                    implementation_state=t.get("implementation_state", "not_started"),
                    impl_commit=t.get("impl_commit", ""),
                    impl_verifier=t.get("impl_verifier", ""),
                    version=t.get("version", 1),
                    section=t.get("section", "未分类")
                )
                temp_file = md_file.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
                try:
                    temp_file.write_text(md_text, encoding="utf-8")
                    os.replace(temp_file, md_file)
                finally:
                    if temp_file.exists():
                        try:
                            temp_file.unlink()
                        except OSError:
                            pass
                staged_files.append(md_file)

            # 4. 刷新 metadata.json
            self.recovery.sync_metadata_json()

            # 5. 递交 Git 提交并透传结果 (F08, U12)
            git_res = self.git.commit_decision(
                topic_title="全库快照回滚",
                lifecycle_badge="时间旅行",
                summary=f"全库回滚至快照 #{rev_id} ({res['rolled_back_to']})",
                staged_files=staged_files
            )
            res["git_status"] = git_res.status
            res["commit_hash"] = git_res.commit_hash
            res["git_message"] = git_res.message

            return res
        except Exception:
            # 全流程故障还原补偿 (U06, U07, R06, R12)
            # 1. 还原数据库 (优先通过 SQLite Backup API 还原, 兼顾 WAL 模式)
            if db_backup.exists():
                restored_via_backup_api = False
                bak_conn = None
                try:
                    bak_conn = sqlite3.connect(str(db_backup))
                    with self.db.get_connection() as live_conn:
                        bak_conn.backup(live_conn)
                    restored_via_backup_api = True
                except Exception:
                    pass
                finally:
                    if bak_conn is not None:
                        bak_conn.close()
                if not restored_via_backup_api:
                    shutil.copy2(db_backup, db_path)

            # 2. 还原 live 目录下的所有文件
            for p in self.config.decisions_dir.glob("*.md"):
                if p.name not in live_backups:
                    try:
                        p.unlink()
                    except OSError:
                        pass
            for fname, content in live_backups.items():
                (self.config.decisions_dir / fname).write_bytes(content)

            # 3. 清理本轮归档生成的多余文件
            for archive_target, _ in archived_moves:
                if archive_target.exists():
                    try:
                        archive_target.unlink()
                    except OSError:
                        pass

            # 4. 还原 metadata.json (R06)
            if orig_metadata_bytes is not None:
                self.config.metadata_json_path.write_bytes(orig_metadata_bytes)
            elif self.config.metadata_json_path.exists():
                try:
                    self.config.metadata_json_path.unlink()
                except OSError:
                    pass
            raise
        finally:
            if db_backup.exists():
                try:
                    db_backup.unlink()
                except OSError:
                    pass

    def record_verification(
        self,
        topic_id: str,
        impl_commit: str,
        verifier: str,
        test_summary: str = "",
        mark_verified: bool = True
    ) -> Dict[str, Any]:
        """
        P2-E: 关联实现证据到议题台账：
        原子更新 Markdown 权威文件与 SQLite 审计记录，完整保留 section 与正交状态 (R06)
        """
        topic_id = self.validate_topic_id(topic_id)
        row = self.db.get_topic(topic_id)
        if not row:
            raise TopicValidationError(f"未找到议题 [{topic_id}]")

        new_impl_state = "verified" if mark_verified else "implemented"
        impl_note = f"{verifier}: {test_summary}".strip() if test_summary else verifier

        current_ver = row["version"] if row["version"] is not None else 1
        new_version = current_ver + 1

        data = dict(row)
        data["implementation_state"] = new_impl_state
        data["impl_status"] = "已核验" if mark_verified else "已实现"
        data["impl_commit"] = impl_commit
        data["impl_verifier"] = impl_note

        # 1. 更新 Markdown 权威文件 (在数据库修改前执行原子替换, R09)
        md_file = self.config.decisions_dir / f"{topic_id}.md"
        parsed = self.parser.parse_markdown_file(md_file)
        orig_file_bytes = md_file.read_bytes() if md_file.exists() else None
        orig_metadata_bytes = self.config.metadata_json_path.read_bytes() if self.config.metadata_json_path.exists() else None
        if parsed:
            section = data.get("section") or parsed.get("section", "未分类")
            wf_state = data.get("workflow_state") or parsed.get("workflow_state", "discussing")
            badge = self.get_lifecycle_badge(wf_state)
            updated_md = self.parser.serialize_markdown(
                topic_id=topic_id,
                title=parsed["title"],
                lifecycle_badge=badge,
                decision_status=data.get("decision_status", "已定"),
                impl_status=data["impl_status"],
                priority=parsed.get("priority", "普通"),
                obj=parsed.get("object", "通用系统"),
                func=parsed.get("function", "核心规范"),
                core_content=parsed["core_content"],
                existing_rounds=parsed["rounds"],
                workflow_state=wf_state,
                decision_outcome=data.get("decision_outcome") or parsed.get("decision_outcome", ""),
                rejection_reason=data.get("rejection_reason") or parsed.get("rejection_reason", ""),
                superseded_by=data.get("superseded_by") or parsed.get("superseded_by", ""),
                implementation_state=new_impl_state,
                impl_commit=impl_commit,
                impl_verifier=impl_note,
                version=new_version,
                section=section
            )
            temp_file = md_file.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
            try:
                temp_file.write_text(updated_md, encoding="utf-8")
                self._atomic_replace(temp_file, md_file)
            finally:
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass

        # 2. 文件替换成功后，原子更新数据库并提交快照，失败则逆向补偿
        try:
            self.db.upsert_topic(data, expected_version=current_ver, exact_version=new_version)
            self.recovery.sync_metadata_json()
            rev = self.db.commit_revision(
                action_type="VERIFY_IMPLEMENTATION",
                summary=f"核验实现: [{data['title']}] -> {new_impl_state} (Commit: {impl_commit})",
                topic_id=topic_id,
                author=verifier,
                diff_summary=f"impl_commit={impl_commit}, verifier={impl_note}"
            )
        except Exception:
            if orig_file_bytes is not None:
                md_file.write_bytes(orig_file_bytes)
            self.db.upsert_topic(row, exact_version=current_ver)
            if orig_metadata_bytes is not None:
                self.config.metadata_json_path.write_bytes(orig_metadata_bytes)
            elif self.config.metadata_json_path.exists():
                try:
                    self.config.metadata_json_path.unlink()
                except OSError:
                    pass
            raise

        return {
            "status": "success",
            "topic_id": topic_id,
            "implementation_state": new_impl_state,
            "impl_commit": impl_commit,
            "impl_verifier": impl_note,
            "version": new_version,
            "revision_hash": rev["rev_hash"],
            "message": f"议题 [{topic_id}] 已成功核验并记录至台账与快照！"
        }
