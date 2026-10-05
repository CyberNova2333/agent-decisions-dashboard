# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Recovery & Consistency Engine
索引双向重建、三态存储一致性检测与故障恢复引擎
"""

import json
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

    def check_consistency(self) -> Dict[str, Any]:
        """
        全面检测 Markdown 文件、SQLite 数据库以及 metadata.json 之间的一致性：
        - 查找磁盘上有但 SQLite 未索引的 Markdown 文件
        - 查找 SQLite 中存在但磁盘文件缺失的议题
        - 查找轮次数或版本号不一致的议题
        - 检测 metadata.json 是否与权威数据同步
        """
        decisions_dir = self.config.decisions_dir
        disk_files: Dict[str, Path] = {}
        if decisions_dir.exists():
            for p in decisions_dir.glob("*.md"):
                if p.is_file():
                    disk_files[p.stem] = p

        db_topics = {t["id"]: t for t in self.db.get_all_topics()}

        unindexed_markdown: List[str] = []
        missing_markdown: List[str] = []
        desynced_topics: List[Dict[str, Any]] = []

        # 1. 检查磁盘文件在 DB 中的状态
        for tid, file_path in disk_files.items():
            if tid not in db_topics:
                unindexed_markdown.append(tid)
            else:
                db_t = db_topics[tid]
                parsed = self.parser.parse_markdown_file(file_path)
                if parsed:
                    disk_rounds = len(parsed["rounds"])
                    db_rounds = len(parsed.get("rounds", []))
                    disk_ver = parsed.get("version", 1)
                    db_ver = db_t.get("version", 1)
                    if disk_ver != db_ver or disk_rounds != self.parser.count_rounds(file_path):
                        desynced_topics.append({
                            "id": tid,
                            "title": db_t["title"],
                            "disk_version": disk_ver,
                            "db_version": db_ver,
                            "disk_rounds": disk_rounds
                        })

        # 2. 检查 DB 中存在但磁盘无文件的议题
        for tid in db_topics:
            if tid not in disk_files:
                missing_markdown.append(tid)

        # 3. 检查 metadata.json 同步状态
        meta_synced = True
        meta_count = 0
        if self.config.metadata_json_path.exists():
            try:
                meta_data = json.loads(self.config.metadata_json_path.read_text(encoding="utf-8"))
                meta_topics = meta_data.get("topics", [])
                meta_count = len(meta_topics)
                if meta_count != len(db_topics):
                    meta_synced = False
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
        以 Markdown 文件为权威事实源，全量重建 SQLite 索引与 metadata.json：
        遍历 decisions/*.md，解析正文、Frontmatter 与历史讨论，逐条入库
        """
        decisions_dir = self.config.decisions_dir
        if not decisions_dir.exists():
            return {
                "status": "error",
                "message": f"目录不存在: {decisions_dir}",
                "rebuilt_count": 0
            }

        md_files = list(decisions_dir.glob("*.md"))
        rebuilt = []
        errors = []

        for p in md_files:
            try:
                parsed = self.parser.parse_markdown_file(p)
                if not parsed:
                    continue

                topic_id = parsed["id"]
                discussion = []
                for r in parsed.get("rounds", []):
                    u = r.get("user_opinion", "")
                    a = r.get("agent_reply", "")
                    title = r.get("title", "")
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
                    "impl_verifier": parsed.get("impl_verifier", "")
                }

                self.db.upsert_topic(topic_data)
                rebuilt.append(topic_id)
            except Exception as e:
                errors.append({"file": p.name, "error": str(e)})

        # 刷新派生物 metadata.json
        self.sync_metadata_json()

        return {
            "status": "success",
            "rebuilt_count": len(rebuilt),
            "rebuilt_ids": rebuilt,
            "errors": errors,
            "message": f"成功从 Markdown 事实源重建了 {len(rebuilt)} 条议题索引！"
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
