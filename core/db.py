# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Database Manager
SQLite 结构化存储、版本快照管理与一键回滚引擎
"""

import sqlite3
import json
import datetime
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from core.config import Config

class DatabaseManager:
    def __init__(self, db_path: Path, config: Optional[Config] = None):
        self.db_path = db_path
        self.config = config
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """初始化 SQLite 数据库表结构"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 系统元数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # 核心议题台账表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    section TEXT NOT NULL,
                    object TEXT NOT NULL,
                    function TEXT NOT NULL,
                    lifecycle_status TEXT NOT NULL, -- 'decided', 'discussing', 'pending'
                    decision_status TEXT NOT NULL,
                    impl_status TEXT NOT NULL,
                    priority TEXT,
                    content TEXT,
                    sources TEXT,
                    discussion_json TEXT,
                    updated_at TEXT NOT NULL
                )
            """)

            # 版本历史与不可篡改快照链 (Git-like Revisions)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS revisions (
                    rev_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rev_hash TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    author TEXT NOT NULL,
                    action_type TEXT NOT NULL, -- 'INIT', 'RECORD_DECISION', 'STATUS_CHANGE', 'NEW_TOPIC', 'ROLLBACK'
                    topic_id TEXT,
                    topic_title TEXT,
                    summary TEXT NOT NULL,
                    old_lifecycle TEXT,
                    new_lifecycle TEXT,
                    user_opinion TEXT,
                    agent_reply TEXT,
                    diff_summary TEXT,
                    snapshot_json TEXT NOT NULL
                )
            """)

            # 已定结论清单表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settled_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    requirement TEXT NOT NULL,
                    details TEXT NOT NULL
                )
            """)

            # 未决议题攻坚表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS open_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item TEXT NOT NULL,
                    issue TEXT NOT NULL,
                    focus TEXT NOT NULL,
                    topic_ref TEXT NOT NULL
                )
            """)

            # 审计变更日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS changelog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    change TEXT NOT NULL,
                    basis TEXT NOT NULL
                )
            """)
            conn.commit()

    def get_all_topics(self) -> List[Dict[str, Any]]:
        """获取所有议题记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT * FROM topics ORDER BY rowid ASC").fetchall()
            return [dict(r) for r in rows]

    def get_topic(self, topic_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 查询单个议题"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            return dict(row) if row else None

    def upsert_topic(self, data: Dict[str, Any]):
        """插入或更新单个议题"""
        now_iso = datetime.datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO topics (
                    id, title, section, object, function,
                    lifecycle_status, decision_status, impl_status, priority,
                    content, sources, discussion_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    section=excluded.section,
                    object=excluded.object,
                    function=excluded.function,
                    lifecycle_status=excluded.lifecycle_status,
                    decision_status=excluded.decision_status,
                    impl_status=excluded.impl_status,
                    priority=excluded.priority,
                    content=excluded.content,
                    sources=excluded.sources,
                    discussion_json=excluded.discussion_json,
                    updated_at=excluded.updated_at
            """, (
                data["id"],
                data.get("title", ""),
                data.get("section", "未分类"),
                data.get("object", "通用系统"),
                data.get("function", "核心规范"),
                data.get("lifecycle_status", "discussing"),
                data.get("decision_status", "已定"),
                data.get("impl_status", "未实现"),
                data.get("priority", "普通"),
                data.get("content", ""),
                data.get("sources", ""),
                json.dumps(data.get("discussion", []), ensure_ascii=False) if isinstance(data.get("discussion"), list) else data.get("discussion_json", "[]"),
                data.get("updated_at", now_iso)
            ))
            conn.commit()

    def record_changelog(self, scope: str, change: str, basis: str):
        """记录一条变更日志"""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO changelog (date, scope, change, basis) VALUES (?, ?, ?, ?)",
                (today, scope, change, basis)
            )
            conn.commit()

    def commit_revision(
        self,
        action_type: str,
        summary: str,
        topic_id: Optional[str] = None,
        author: str = "人类/Agent",
        user_opinion: str = "",
        agent_reply: str = "",
        new_lifecycle: Optional[str] = None,
        old_lifecycle: Optional[str] = None,
        diff_summary: str = ""
    ) -> Dict[str, Any]:
        """为当前全量数据库生成一份不可篡改的 Revision 快照，支持随时时间旅行回退"""
        now_dt = datetime.datetime.now()
        now_str = now_dt.isoformat()
        rev_hash = "rev-" + hashlib.sha1((now_str + summary).encode("utf-8")).hexdigest()[:8]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            topic_title = ""
            if topic_id:
                row = cursor.execute("SELECT title FROM topics WHERE id = ?", (topic_id,)).fetchone()
                if row:
                    topic_title = row["title"]

            snapshot = self.export_full_data(conn)

            cursor.execute("""
                INSERT INTO revisions (
                    rev_hash, created_at, author, action_type, topic_id, topic_title,
                    summary, old_lifecycle, new_lifecycle, user_opinion, agent_reply,
                    diff_summary, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rev_hash, now_str, author, action_type, topic_id, topic_title,
                summary, old_lifecycle, new_lifecycle, user_opinion, agent_reply,
                diff_summary, json.dumps(snapshot, ensure_ascii=False)
            ))
            conn.commit()
            rev_id = cursor.lastrowid
            return {"rev_id": rev_id, "rev_hash": rev_hash, "created_at": now_str}

    def get_revisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取版本快照提交列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT rev_id, rev_hash, created_at, author, action_type,
                       topic_id, topic_title, summary, old_lifecycle,
                       new_lifecycle, user_opinion, agent_reply, diff_summary
                FROM revisions
                ORDER BY rev_id DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def rollback_revision(self, target_rev_id: int, author: str = "人类/Agent") -> Dict[str, Any]:
        """将数据库完全回滚至指定的 Revision 快照"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT rev_id, rev_hash, summary, snapshot_json FROM revisions WHERE rev_id = ?",
                (target_rev_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"未找到指定的版本快照 #{target_rev_id}")

            target_hash = row["rev_hash"]
            target_summary = row["summary"]
            snapshot = json.loads(row["snapshot_json"])

            # 清空当前业务表并按快照恢复
            cursor.execute("DELETE FROM topics")
            for t in snapshot.get("topics", []):
                cursor.execute("""
                    INSERT INTO topics (
                        id, title, section, object, function,
                        lifecycle_status, decision_status, impl_status, priority,
                        content, sources, discussion_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    t["id"], t["title"], t.get("section", ""), t.get("object", ""),
                    t.get("function", ""), t.get("lifecycle_status", "discussing"),
                    t.get("decision_status", "已定"), t.get("impl_status", "未实现"),
                    t.get("priority", "普通"), t.get("content", ""), t.get("sources", ""),
                    json.dumps(t.get("discussion", []), ensure_ascii=False),
                    t.get("updated_at", datetime.datetime.now().isoformat())
                ))

            cursor.execute("DELETE FROM settled_decisions")
            for s in snapshot.get("settled_decisions", []):
                cursor.execute(
                    "INSERT INTO settled_decisions (title, requirement, details) VALUES (?, ?, ?)",
                    (s["title"], s["requirement"], s["details"])
                )

            cursor.execute("DELETE FROM open_questions")
            for q in snapshot.get("open_questions", []):
                cursor.execute(
                    "INSERT INTO open_questions (item, issue, focus, topic_ref) VALUES (?, ?, ?, ?)",
                    (q["item"], q["issue"], q["focus"], q["topic_ref"])
                )
            conn.commit()

        # 生成回滚审计记录
        new_rev = self.commit_revision(
            action_type="ROLLBACK",
            summary=f"回滚至快照 {target_hash} ({target_summary})",
            author=author,
            diff_summary=f"已重置全量议题至版本 #{target_rev_id}"
        )
        return {
            "status": "success",
            "rolled_back_to": target_hash,
            "new_revision": new_rev["rev_hash"],
            "message": f"成功回滚至快照 {target_hash}"
        }

    def export_full_data(self, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        """导出全量结构化数据"""
        should_close = False
        if conn is None:
            conn = self.get_connection()
            should_close = True

        cursor = conn.cursor()

        topics = []
        for r in cursor.execute("SELECT * FROM topics ORDER BY rowid ASC"):
            topics.append({
                "id": r["id"],
                "title": r["title"],
                "section": r["section"],
                "object": r["object"],
                "function": r["function"],
                "lifecycle_status": r["lifecycle_status"],
                "decision_status": r["decision_status"],
                "impl_status": r["impl_status"],
                "priority": r["priority"],
                "content": r["content"],
                "sources": r["sources"],
                "discussion": json.loads(r["discussion_json"]) if r["discussion_json"] else [],
                "updated_at": r["updated_at"]
            })

        settled = []
        for r in cursor.execute("SELECT title, requirement, details FROM settled_decisions ORDER BY id ASC"):
            settled.append({
                "title": r["title"],
                "requirement": r["requirement"],
                "details": r["details"]
            })

        open_q = []
        for r in cursor.execute("SELECT item, issue, focus, topic_ref FROM open_questions ORDER BY id ASC"):
            open_q.append({
                "item": r["item"],
                "issue": r["issue"],
                "focus": r["focus"],
                "topic_ref": r["topic_ref"]
            })

        changes = []
        for r in cursor.execute("SELECT date, scope, change, basis FROM changelog ORDER BY id DESC"):
            changes.append({
                "date": r["date"],
                "scope": r["scope"],
                "change": r["change"],
                "basis": r["basis"]
            })

        doc_data = {
            "metadata": {
                "project_name": self.config.project_name if self.config else "Agent Decisions Dashboard",
                "updated_at": datetime.datetime.now().isoformat(),
                "total_topics": len(topics)
            },
            "topics": topics,
            "settled_decisions": settled,
            "open_questions": open_q,
            "changelog": changes
        }

        if should_close:
            conn.close()

        return doc_data
