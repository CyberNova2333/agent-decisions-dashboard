# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Decision Service
核心业务流程协调层：创建、保存、乐观锁并发检查、幂等去重、受控提交与精准回滚
"""

import os
import shutil
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

        # 1. 幂等性检查 (指纹绑定 topic_id 与规范化 data)
        req_hash = hashlib.sha256(f"{topic_id}:{json.dumps(data, sort_keys=True, ensure_ascii=False)}".encode("utf-8")).hexdigest()
        if request_id:
            is_valid, cached_res = self.db.check_idempotency(request_id, topic_id, req_hash)
            if not is_valid:
                raise IdempotencyConflictError(f"请求 ID [{request_id}] 冲突：相同 ID 携带了不同的请求数据或目标议题")
            if cached_res is not None and cached_res.get("status") in ("success", "completed"):
                return self._resume_pending_phases(cached_res, topic_id, data, request_id, req_hash)

        user_opinion = (data.get("new_user_opinion") or data.get("user_opinion") or "").strip()
        agent_reply = (data.get("new_agent_reply") or data.get("agent_reply") or "").strip()
        commit_msg = (data.get("commit_message") or "").strip()

        # 2. 版本检查与分配：在产生任何持久副作用前先校验版本 (R02, F02, F03, F15)
        existing_row = self.db.get_topic(topic_id)
        current_db_ver = existing_row.get("version", 1) if existing_row else 1
        md_file = self.config.decisions_dir / f"{topic_id}.md"
        existing_disk_text: Optional[str] = None
        is_interrupted_prior_attempt = False

        if md_file.exists():
            try:
                existing_disk_text = md_file.read_text(encoding="utf-8")
                parsed_disk = self.parser.parse_markdown_file(md_file)
                if parsed_disk:
                    disk_ver = parsed_disk.get("version", 1)
                    disk_rounds = parsed_disk.get("rounds", [])
                    
                    # 检查磁盘是否已在上次中断的写入中先一步落盘了本请求的轮次 (F03)
                    last_matches = False
                    if disk_rounds and (user_opinion or agent_reply or commit_msg):
                        last_r = disk_rounds[-1]
                        last_u = (last_r.get("user_opinion") or "").strip()
                        last_a = (last_r.get("agent_reply") or "").strip()
                        last_c = (last_r.get("commit_message") or "").strip()
                        if (not user_opinion or user_opinion == last_u) and \
                           (not agent_reply or agent_reply == last_a) and \
                           (not commit_msg or commit_msg == last_c):
                            last_matches = True

                    if expected_version is not None and disk_ver == expected_version + 1 and current_db_ver == expected_version and last_matches:
                        is_interrupted_prior_attempt = True
                    elif expected_version is not None and disk_ver != expected_version:
                        raise VersionConflictError(
                            current_version=disk_ver,
                            expected_version=expected_version,
                            topic_id=topic_id
                        )
                    elif existing_row and not is_interrupted_prior_attempt:
                        # 检测未入库的正文或元数据漂移 (F15)
                        if parsed_disk.get("title") != existing_row.get("title") or parsed_disk.get("core_content", "").strip() != existing_row.get("content", "").strip():
                            raise VersionConflictError(
                                current_version=disk_ver,
                                expected_version=expected_version,
                                topic_id=topic_id
                            )
            except VersionConflictError:
                raise
            except Exception:
                pass

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
            if expected_version is not None and expected_version != 1:
                raise VersionConflictError(
                    current_version=0,
                    expected_version=expected_version,
                    topic_id=topic_id
                )
            allocated_version = 1

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
        user_opinion = (data.get("new_user_opinion") or data.get("user_opinion") or "").strip()
        agent_reply = (data.get("new_agent_reply") or data.get("agent_reply") or "").strip()
        commit_msg = (data.get("commit_message") or "").strip()
        content_override = data.get("content_override")

        lifecycle_badge = self.get_lifecycle_badge(wf_state)

        # 4. 读取既有 Markdown 与历史轮次
        md_file = self.config.decisions_dir / f"{topic_id}.md"
        existing_doc = self.parser.parse_markdown_file(md_file)
        current_rounds = existing_doc["rounds"] if existing_doc else []

        # 幂等重试防护：检查最后一轮是否已包含当前请求的讨论内容，杜绝因更早数据库异常重试时重复追加轮次 (F03)
        is_duplicate_round = False
        if current_rounds and (user_opinion or agent_reply or commit_msg):
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

        # 5. 序列化 Markdown 并原子化写入磁盘 (临时文件 + os.replace)
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
            os.replace(temp_file, md_file)
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

        # 6. 更新 SQLite 数据库结构化索引
        discussion = json.loads(existing_row["discussion_json"]) if (existing_row and existing_row.get("discussion_json")) else []
        has_commit = any(d.get("val") == commit_msg for d in discussion if "变更说明" in d.get("key", "")) if commit_msg else False
        has_opinion = any(d.get("val") == user_opinion for d in discussion if "用户意见" in d.get("key", "")) if user_opinion else False
        has_reply = any(d.get("val") == agent_reply for d in discussion if "答复" in d.get("key", "") or "落实" in d.get("key", "")) if agent_reply else False

        if commit_msg and not has_commit:
            discussion.append({"key": f"第 {new_round_num} 轮变更说明", "val": commit_msg})
        if user_opinion and not has_opinion:
            discussion.append({"key": f"第 {new_round_num} 轮用户意见", "val": user_opinion})
        if agent_reply and not has_reply:
            discussion.append({"key": f"第 {new_round_num} 轮落实答复", "val": agent_reply})

        target_expected_version = expected_version if expected_version is not None else (existing_row.get("version") if existing_row else None)
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
            }, expected_version=target_expected_version, exact_version=allocated_version)
        except VersionConflictError:
            if existing_disk_text is not None:
                try:
                    md_file.write_text(existing_disk_text, encoding="utf-8")
                except Exception:
                    pass
            raise

        if commit_msg:
            basis_str = f"用户指示: {user_opinion[:25]}..." if user_opinion else "用户明确决策"
            self.db.record_changelog(
                scope=f"[{title}](#{topic_id})",
                change=f"{commit_msg} [{lifecycle_badge}]",
                basis=basis_str
            )

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
        if request_id:
            req_hash = hashlib.sha256(f"{topic_id}:{json.dumps(data, sort_keys=True, ensure_ascii=False)}".encode("utf-8")).hexdigest()
            is_valid, cached_res = self.db.check_idempotency(request_id, topic_id, req_hash)
            if not is_valid:
                raise IdempotencyConflictError(f"请求 ID [{request_id}] 冲突：相同 ID 携带了不同的请求数据或目标议题")
            if cached_res is not None and cached_res.get("status") in ("success", "completed"):
                return self._resume_pending_phases(cached_res, topic_id, data, request_id, req_hash)

        # 2. 检查议题存在性
        existing = self.db.get_topic(topic_id)
        if existing:
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

        discussion = topic_data.get("discussion") or []
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

    def restore_single_topic(
        self,
        topic_id: str,
        rev_id: int,
        author: str = "人类/Agent",
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        P1-C: 精准恢复单个议题至历史快照状态，不波及其他议题，并保留完整字段与轮次结构 (R06)
        """
        topic_id = self.validate_topic_id(topic_id)
        res = self.db.restore_topic_from_revision(topic_id, rev_id, author, reason)
        topic_data = res["topic"]

        # 写回该议题的 Markdown 文本
        md_file = self.config.decisions_dir / f"{topic_id}.md"
        wf_state = topic_data.get("workflow_state") or topic_data.get("lifecycle_status", "discussing")
        lifecycle_badge = self.get_lifecycle_badge(wf_state)
        
        rounds = self._reconstruct_rounds_from_topic(topic_data)

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
            workflow_state=wf_state,
            decision_outcome=topic_data.get("decision_outcome", ""),
            rejection_reason=topic_data.get("rejection_reason", ""),
            superseded_by=topic_data.get("superseded_by", ""),
            implementation_state=topic_data.get("implementation_state", "not_started"),
            impl_commit=topic_data.get("impl_commit", ""),
            impl_verifier=topic_data.get("impl_verifier", ""),
            version=res["new_version"],
            section=topic_data.get("section", "未分类")
        )
        self.config.decisions_dir.mkdir(parents=True, exist_ok=True)
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
        P1-C: 全库恢复至指定快照，同时清理目标快照外的多余文件并保持字段完整 (R05, R06)
        """
        res = self.db.rollback_revision(rev_id, author)
        snapshot = res["snapshot"]

        target_topics = snapshot.get("topics", [])
        target_ids = {t["id"] for t in target_topics}

        staged_files = [self.config.metadata_json_path, self.config.database_path]

        # 1. 处理快照之外的多余现存文件：移入归档区并暂存 Git 删除，防止重启或重建时复活 (R05)
        archive_dir = self.config.decisions_dir / ".archived_rollback"
        if self.config.decisions_dir.exists():
            for p in self.config.decisions_dir.glob("*.md"):
                if p.stem not in target_ids:
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    archive_target = archive_dir / f"{p.stem}_{uuid.uuid4().hex[:6]}.md"
                    try:
                        shutil.move(str(p), str(archive_target))
                        staged_files.append(p)
                    except Exception as e:
                        # 绝不静默删除源文件！必须保留原文件并中止破坏性操作 (F07)
                        raise OSError(f"归档孤儿文件失败: {p.name} -> {e}") from e

        # 2. 写回快照中的所有 Markdown 文件 (原子替换并保持完整字段)
        resolved_decisions_dir = self.config.decisions_dir.resolve()
        for t in target_topics:
            tid = t["id"]
            if not re.match(r'^[a-zA-Z0-9_\-]+$', tid):
                raise ValueError(f"快照中包含非法的议题 ID: [{tid}]")
            md_file = (self.config.decisions_dir / f"{tid}.md").resolve()
            try:
                md_file.relative_to(resolved_decisions_dir)
            except ValueError:
                raise ValueError(f"检测到非法路径越界: [{tid}]")
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

        # 3. 刷新 metadata.json
        self.recovery.sync_metadata_json()

        # 4. 递交 Git 提交
        self.git.commit_decision(
            topic_title="全库快照回滚",
            lifecycle_badge="时间旅行",
            summary=f"全库回滚至快照 #{rev_id} ({res['rolled_back_to']})",
            staged_files=staged_files
        )

        return res

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

        data = dict(row)
        data["implementation_state"] = new_impl_state
        data["impl_status"] = "已核验" if mark_verified else "已实现"
        data["impl_commit"] = impl_commit
        data["impl_verifier"] = impl_note

        new_version = self.db.upsert_topic(data)

        # 更新 Markdown 权威文件 (保留原 section 等所有字段)
        md_file = self.config.decisions_dir / f"{topic_id}.md"
        parsed = self.parser.parse_markdown_file(md_file)
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
                os.replace(temp_file, md_file)
            finally:
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass

        self.recovery.sync_metadata_json()

        rev = self.db.commit_revision(
            action_type="VERIFY_IMPLEMENTATION",
            summary=f"核验实现: [{data['title']}] -> {new_impl_state} (Commit: {impl_commit})",
            topic_id=topic_id,
            author=verifier,
            diff_summary=f"impl_commit={impl_commit}, verifier={impl_note}"
        )

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
