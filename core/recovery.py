# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Recovery & Consistency Engine
索引双向重建、三态存储一致性检测与故障恢复引擎
支持权威版本保持、幂等重建、内容漂移检测与孤儿清理 (R04)
"""

import re
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from core.config import Config
from core.db import DatabaseManager
from core.markdown_parser import TopicMarkdownParser


class RecoveryManager:
    def __init__(self, config: Config, db: Optional[DatabaseManager] = None):
        self.config = config
        self.db = db or DatabaseManager(config.database_path, config)
        self.parser = TopicMarkdownParser()

    @staticmethod
    def _compute_digest(data: Dict[str, Any], core_content: str, rounds: List[Dict[str, Any]]) -> str:
        """计算议题内容的规范化 SHA-256 摘要，用于精准检测内容漂移"""
        rounds_str_parts = []
        for r in rounds:
            rounds_str_parts.append(f"{r.get('title', '')}:{r.get('content', '')}:{r.get('user_opinion', '')}:{r.get('agent_reply', '')}:{r.get('commit_message', '')}")
        rounds_str = "||".join(rounds_str_parts)

        fields = [
            str(data.get("id", "")).strip(),
            str(data.get("title", "")).strip(),
            str(data.get("section", "")).strip(),
            str(data.get("object", "")).strip(),
            str(data.get("function", "")).strip(),
            str(data.get("workflow_state", "")).strip(),
            str(data.get("decision_outcome", "")).strip(),
            str(data.get("rejection_reason", "")).strip(),
            str(data.get("superseded_by", "")).strip(),
            str(data.get("implementation_state", "")).strip(),
            str(data.get("impl_commit", "")).strip(),
            str(data.get("impl_verifier", "")).strip(),
            str(data.get("version", 1)),
            core_content.strip(),
            rounds_str
        ]
        return hashlib.sha256("|".join(fields).encode("utf-8")).hexdigest()

    def check_consistency(self) -> Dict[str, Any]:
        """
        全面检测 Markdown 文件、SQLite 数据库以及 metadata.json 之间的一致性：
        - 查找磁盘上有但 SQLite 未索引的 Markdown 文件
        - 查找 SQLite 中存在但磁盘文件缺失的议题
        - 计算内容摘要对比，精准发现同版本正文漂移 (R04)
        - 深入校验 metadata.json 导出字段是否与权威数据完全一致
        """
        decisions_dir = self.config.decisions_dir
        disk_files: Dict[str, Path] = {}
        if decisions_dir.exists():
            for p in decisions_dir.glob("*.md"):
                if p.is_file() and not p.name.startswith("."):
                    disk_files[p.stem] = p

        db_topics = {t["id"]: t for t in self.db.get_all_topics()}

        unindexed_markdown: List[str] = []
        missing_markdown: List[str] = []
        desynced_topics: List[Dict[str, Any]] = []

        # 1. 检查磁盘文件在 DB 中的状态与内容保真度
        for tid, file_path in disk_files.items():
            if tid not in db_topics:
                unindexed_markdown.append(tid)
            else:
                db_t = db_topics[tid]
                parsed = self.parser.parse_markdown_file(file_path)
                if parsed:
                    disk_ver = parsed.get("version", 1)
                    db_ver = db_t.get("version", 1)
                    disk_rounds = len(parsed["rounds"])

                    # 提取 DB 端的讨论 rounds 用于比对 (F10)
                    db_discussion = []
                    if db_t.get("discussion_json"):
                        try:
                            raw_disc = db_t["discussion_json"]
                            db_discussion = json.loads(raw_disc) if isinstance(raw_disc, str) else raw_disc
                        except Exception:
                            db_discussion = []

                    db_rounds_reconstructed = []
                    if db_discussion:
                        rounds_map: Dict[int, Dict[str, Any]] = {}
                        for d in db_discussion:
                            k = d.get("key", "")
                            v = d.get("val", "")
                            m = re.search(r'第\s*(\d+)\s*轮', k)
                            if m:
                                r_num = int(m.group(1))
                                if r_num not in rounds_map:
                                    rounds_map[r_num] = {"title": f"第 {r_num} 轮", "user_opinion": "", "agent_reply": "", "commit_message": ""}
                                if "用户" in k: rounds_map[r_num]["user_opinion"] = v
                                elif "答复" in k or "落实" in k: rounds_map[r_num]["agent_reply"] = v
                                elif "变更" in k: rounds_map[r_num]["commit_message"] = v
                            else:
                                rounds_map[len(rounds_map) + 1] = {"title": k, "user_opinion": v, "agent_reply": "", "commit_message": ""}
                        for r_num in sorted(rounds_map.keys()):
                            db_rounds_reconstructed.append(rounds_map[r_num])

                    disk_digest = self._compute_digest(parsed, parsed.get("core_content", ""), parsed.get("rounds", []))
                    
                    # 组装 DB 规范化数据比对
                    db_t_norm = {
                        "id": db_t["id"],
                        "title": db_t["title"],
                        "section": db_t.get("section", "未分类"),
                        "object": db_t.get("object", "通用系统"),
                        "function": db_t.get("function", "核心规范"),
                        "workflow_state": db_t.get("workflow_state") or db_t.get("lifecycle_status", "discussing"),
                        "decision_outcome": db_t.get("decision_outcome", ""),
                        "rejection_reason": db_t.get("rejection_reason", ""),
                        "superseded_by": db_t.get("superseded_by", ""),
                        "implementation_state": db_t.get("implementation_state", "not_started"),
                        "impl_commit": db_t.get("impl_commit", ""),
                        "impl_verifier": db_t.get("impl_verifier", ""),
                        "version": db_ver
                    }
                    db_digest = self._compute_digest(db_t_norm, db_t.get("content", ""), db_rounds_reconstructed)

                    if disk_ver != db_ver or disk_digest != db_digest:
                        desynced_topics.append({
                            "id": tid,
                            "title": db_t["title"],
                            "disk_version": disk_ver,
                            "db_version": db_ver,
                            "disk_rounds": disk_rounds,
                            "version_mismatch": disk_ver != db_ver,
                            "content_drift": disk_digest != db_digest
                        })

        # 2. 检查 DB 中存在但磁盘无文件的议题
        for tid in db_topics:
            if tid not in disk_files:
                missing_markdown.append(tid)

        # 3. 检查 metadata.json 同步状态与字段一致性 (R04, F10)
        meta_synced = True
        meta_count = 0
        if self.config.metadata_json_path.exists():
            try:
                meta_data = json.loads(self.config.metadata_json_path.read_text(encoding="utf-8"))
                meta_topics = meta_data.get("topics", [])
                meta_count = len(meta_topics)
                if meta_count != len(db_topics):
                    meta_synced = False
                else:
                    for mt in meta_topics:
                        mid = mt.get("id")
                        if mid not in db_topics:
                            meta_synced = False
                            break
                        dbt = db_topics[mid]
                        # 全量比对关键业务字段 (F10)
                        if mt.get("title") != dbt.get("title") or \
                           mt.get("version") != dbt.get("version") or \
                           mt.get("workflow_state") != (dbt.get("workflow_state") or dbt.get("lifecycle_status")) or \
                           mt.get("decision_outcome") != dbt.get("decision_outcome") or \
                           mt.get("implementation_state") != dbt.get("implementation_state") or \
                           mt.get("priority") != dbt.get("priority") or \
                           mt.get("section") != dbt.get("section"):
                            meta_synced = False
                            break
            except Exception:
                meta_synced = False
        else:
            meta_synced = (len(db_topics) == 0)

        is_consistent = (
            len(unindexed_markdown) == 0 and
            len(missing_markdown) == 0 and
            len(desynced_topics) == 0 and
            meta_synced
        )

        return {
            "consistent": is_consistent,
            "total_disk_markdown": len(disk_files),
            "total_db_topics": len(db_topics),
            "metadata_json_topics": meta_count,
            "metadata_json_synced": meta_synced,
            "unindexed_markdown": unindexed_markdown,
            "missing_markdown": missing_markdown,
            "desynced_topics": desynced_topics
        }

    def rebuild_index_from_markdown(self) -> Dict[str, Any]:
        """
        以 Markdown 文件为绝对权威事实源，全量重建 SQLite 索引与 metadata.json (R04)：
        1. 预先解析并校验全部 Markdown 文件，检测格式与 ID 匹配性
        2. 在单数据库事务内构建精确投影：保留文件固有版本，清除无对应文件的旧索引
        3. 重建过程保持严格幂等，绝不额外创造业务版本
        """
        decisions_dir = self.config.decisions_dir
        if not decisions_dir.exists():
            return {
                "status": "error",
                "message": f"目录不存在: {decisions_dir}",
                "rebuilt_count": 0
            }

        md_files = [p for p in decisions_dir.glob("*.md") if not p.name.startswith(".")]
        parsed_items = []
        errors = []
        seen_ids = set()

        # 1. 扫描、解析并校验所有文件
        for p in md_files:
            try:
                parsed = self.parser.parse_markdown_file(p)
                topic_id = parsed.get("id") or p.stem
                if not re.match(r'^[a-zA-Z0-9_\-]+$', topic_id) or topic_id != p.stem:
                    errors.append({"file": p.name, "error": f"议题 ID 非法或与文件名不匹配: [{topic_id}] vs [{p.stem}]"})
                    raise ValueError(f"发现非法或越界的议题 ID: [{topic_id}] in {p.name}")
                if topic_id in seen_ids:
                    errors.append({"file": p.name, "error": f"发现重复的议题 ID: [{topic_id}]"})
                    continue
                seen_ids.add(topic_id)

                discussion = []
                for r in parsed.get("rounds", []):
                    u = r.get("user_opinion", "")
                    a = r.get("agent_reply", "")
                    c = r.get("commit_message", "")
                    title = r.get("title", "")
                    if c:
                        discussion.append({"key": f"{title} 变更说明", "val": c})
                    if u:
                        discussion.append({"key": f"{title} 用户意见", "val": u})
                    if a:
                        discussion.append({"key": f"{title} 落实答复", "val": a})

                topic_data = {
                    "id": topic_id,
                    "title": parsed["title"],
                    "section": parsed.get("section", "未分类"),
                    "object": parsed.get("object", "通用系统"),
                    "function": parsed.get("function", "核心规范"),
                    "lifecycle_status": parsed.get("workflow_state", "discussing"),
                    "decision_status": "已定" if parsed.get("workflow_state") == "decided" else "待定",
                    "impl_status": parsed.get("implementation_state", "not_started"),
                    "priority": parsed.get("priority", "普通"),
                    "content": parsed.get("core_content", ""),
                    "sources": "",
                    "discussion": discussion,
                    "workflow_state": parsed.get("workflow_state", "discussing"),
                    "decision_outcome": parsed.get("decision_outcome", ""),
                    "rejection_reason": parsed.get("rejection_reason", ""),
                    "superseded_by": parsed.get("superseded_by", ""),
                    "implementation_state": parsed.get("implementation_state", "not_started"),
                    "impl_commit": parsed.get("impl_commit", ""),
                    "impl_verifier": parsed.get("impl_verifier", ""),
                    "version": parsed.get("version", 1)
                }
                parsed_items.append({
                    "id": topic_id,
                    "version": parsed.get("version", 1),
                    "data": topic_data
                })
            except Exception as e:
                errors.append({"file": p.name, "error": str(e)})

        # 2. 在同一事务中原子替换当前索引投影 (保留历史 Revisions)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # 仅删除磁盘对应文件确实已不存在的议题，绝不将临时读取失败的文件误判为删除 (F09)
            existing_rows = cursor.execute("SELECT id FROM topics").fetchall()
            for erow in existing_rows:
                tid = erow["id"]
                target_md = decisions_dir / f"{tid}.md"
                if not target_md.exists():
                    cursor.execute("DELETE FROM topics WHERE id = ?", (tid,))

            for item in parsed_items:
                # 明确指定 exact_version，保持文件固有版本号，多次重建绝不累加版本 (R04)
                self.db.upsert_topic(item["data"], exact_version=item["version"], conn=conn)
            conn.commit()

        # 3. 刷新派生物 metadata.json
        self.sync_metadata_json()

        rebuilt_ids = [item["id"] for item in parsed_items]
        status = "success" if not errors else "partial"
        return {
            "status": status,
            "rebuilt_count": len(rebuilt_ids),
            "rebuilt_ids": rebuilt_ids,
            "errors": errors,
            "message": f"从 Markdown 重建了 {len(rebuilt_ids)} 条议题索引（保留文件版本号）！"
        }

    def sync_metadata_json(self):
        """将当前数据库数据派生同步至 metadata.json"""
        topics = self.db.get_all_topics()
        meta_list = []
        for r in topics:
            topic_id = r["id"]
            md_file = self.config.decisions_dir / f"{topic_id}.md"
            rounds_count = self.parser.count_rounds(md_file)
            meta_list.append({
                "id": topic_id,
                "title": r["title"],
                "file": f"decisions/{topic_id}.md",
                "section": r["section"],
                "object": r["object"],
                "function": r["function"],
                "lifecycle_status": r["lifecycle_status"],
                "workflow_state": r.get("workflow_state") or r["lifecycle_status"],
                "decision_outcome": r.get("decision_outcome") or "",
                "rejection_reason": r.get("rejection_reason") or "",
                "superseded_by": r.get("superseded_by") or "",
                "implementation_state": r.get("implementation_state") or "not_started",
                "impl_commit": r.get("impl_commit") or "",
                "impl_verifier": r.get("impl_verifier") or "",
                "version": r.get("version", 1),
                "decision_status": r["decision_status"],
                "impl_status": r["impl_status"],
                "priority": r.get("priority", "普通"),
                "summary": (r["content"] or "").split("\n\n")[0].replace("\n", " ")[:140],
                "rounds_count": rounds_count,
                "updated_at": r["updated_at"]
            })

        self.config.metadata_json_path.parent.mkdir(parents=True, exist_ok=True)
        import datetime
        self.config.metadata_json_path.write_text(json.dumps({
            "updated_at": datetime.datetime.now().isoformat(),
            "total_topics": len(meta_list),
            "topics": meta_list
        }, ensure_ascii=False, indent=2), encoding="utf-8")
