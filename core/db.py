# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Database Manager
SQLite 结构化存储、正交状态模型、版本快照管理、版本乐观锁与一键回滚引擎
"""

import sqlite3
import json
import datetime
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from core.config import Config

class VersionConflictError(Exception):
    """并发写入版本冲突异常"""
    def __init__(self, current_version: int, expected_version: int, topic_id: str):
        self.current_version = current_version
        self.expected_version = expected_version
        self.topic_id = topic_id
        super().__init__(f"议题 [{topic_id}] 发生版本并发冲突：当前服务端版本为 v{current_version}，提交所基于的版本为 v{expected_version}")


from contextlib import contextmanager

class DatabaseManager:
    def __init__(self, db_path: Path, config: Optional[Config] = None):
        self.db_path = db_path
        self.config = config
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """初始化与自动迁移 SQLite 数据库表结构"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 系统元数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # 核心议题台账表（支持正交三态：工作流状态、决策结论、实现状态）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    section TEXT NOT NULL,
                    object TEXT NOT NULL,
                    function TEXT NOT NULL,
                    lifecycle_status TEXT NOT NULL, -- 兼容旧字段 ('decided', 'discussing', 'pending')
                    decision_status TEXT NOT NULL,
                    impl_status TEXT NOT NULL,
                    priority TEXT,
                    content TEXT,
                    sources TEXT,
                    discussion_json TEXT,
                    updated_at TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    workflow_state TEXT DEFAULT 'discussing',      -- 'pending', 'discussing', 'decided'
                    decision_outcome TEXT DEFAULT '',             -- 'accepted', 'rejected', 'deferred', 'superseded'
                    rejection_reason TEXT DEFAULT '',             -- 否决原因与重新讨论条件
                    superseded_by TEXT DEFAULT '',                -- 被哪个议题所替代 (ID)
                    implementation_state TEXT DEFAULT 'not_started', -- 'not_started', 'in_progress', 'implemented', 'verified'
                    impl_commit TEXT DEFAULT '',                  -- 实现提交 Hash / PR
                    impl_verifier TEXT DEFAULT ''                 -- 核验人或核验证据说明
                )
            """)

            # 自动迁移检查：补齐现有库可能缺失的扩展列
            existing_cols = {row["name"] for row in cursor.execute("PRAGMA table_info(topics)").fetchall()}
            migrations = [
                ("version", "INTEGER DEFAULT 1"),
                ("workflow_state", "TEXT DEFAULT 'discussing'"),
                ("decision_outcome", "TEXT DEFAULT ''"),
                ("rejection_reason", "TEXT DEFAULT ''"),
                ("superseded_by", "TEXT DEFAULT ''"),
                ("implementation_state", "TEXT DEFAULT 'not_started'"),
                ("impl_commit", "TEXT DEFAULT ''"),
                ("impl_verifier", "TEXT DEFAULT ''")
            ]
            for col_name, col_type in migrations:
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE topics ADD COLUMN {col_name} {col_type}")

            # 幂等性保存去重表 (Idempotency Keys)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    request_id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL,
                    req_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT DEFAULT 'completed'
                )
            """)
            cursor.execute("PRAGMA table_info(idempotency_keys)")
            ik_cols = [r["name"] for r in cursor.fetchall()]
            if "status" not in ik_cols:
                cursor.execute("ALTER TABLE idempotency_keys ADD COLUMN status TEXT DEFAULT 'completed'")

            # 议题版本代次单调递增高水位序列表，防止删除与回滚后复用 ABA 并发令牌 (F05)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topic_version_seq (
                    topic_id TEXT PRIMARY KEY,
                    max_version INTEGER NOT NULL
                )
            """)

            # 版本历史与不可篡改快照链 (Git-like Revisions)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS revisions (
                    rev_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rev_hash TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    author TEXT NOT NULL,
                    action_type TEXT NOT NULL, -- 'INIT', 'RECORD_DECISION', 'STATUS_CHANGE', 'NEW_TOPIC', 'ROLLBACK', 'TOPIC_RESTORE'
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

    def upsert_topic(
        self,
        data: Dict[str, Any],
        expected_version: Optional[int] = None,
        exact_version: Optional[int] = None,
        conn: Optional[sqlite3.Connection] = None
    ) -> int:
        """
        插入或更新单个议题，支持乐观锁版本检查与外部连接复用：
        若提供 exact_version，直接保留指定版本号；
        若提供 expected_version，检查当前版本一致性，发生冲突时抛出 VersionConflictError；
        返回更新后的版本号 (int)
        """
        now_iso = datetime.datetime.now().isoformat()
        
        # 字段映射与正交三态自动推导
        wf_state = data.get("workflow_state") or data.get("lifecycle_status") or "discussing"
        lc_status = data.get("lifecycle_status") or wf_state
        
        impl_state = data.get("implementation_state")
        if not impl_state:
            legacy_impl = data.get("impl_status", "")
            if legacy_impl in ["已实现", "已完成", "implemented"]:
                impl_state = "implemented"
            elif legacy_impl in ["进行中", "in_progress"]:
                impl_state = "in_progress"
            elif legacy_impl in ["已核验", "verified"]:
                impl_state = "verified"
            else:
                impl_state = "not_started"

        outcome = data.get("decision_outcome", "")
        rejection_reason = data.get("rejection_reason", "")
        superseded_by = data.get("superseded_by", "")
        impl_commit = data.get("impl_commit", "")
        impl_verifier = data.get("impl_verifier", "")

        def _execute(c: sqlite3.Connection) -> int:
            topic_id = data["id"]
            cursor = c.cursor()
            row = cursor.execute("SELECT version FROM topics WHERE id = ?", (topic_id,)).fetchone()

            if row:
                current_ver = row["version"] if row["version"] is not None else 1
                if expected_version is not None and expected_version != current_ver:
                    raise VersionConflictError(
                        current_version=current_ver,
                        expected_version=expected_version,
                        topic_id=topic_id
                    )
                new_version = exact_version if exact_version is not None else (current_ver + 1)
                if expected_version is not None:
                    cursor.execute("""
                        UPDATE topics SET
                            title=?, section=?, object=?, function=?,
                            lifecycle_status=?, decision_status=?, impl_status=?, priority=?,
                            content=?, sources=?, discussion_json=?, updated_at=?,
                            version=?, workflow_state=?, decision_outcome=?, rejection_reason=?,
                            superseded_by=?, implementation_state=?, impl_commit=?, impl_verifier=?
                        WHERE id = ? AND version = ?
                    """, (
                        data.get("title", ""),
                        data.get("section", "未分类"),
                        data.get("object", "通用系统"),
                        data.get("function", "核心规范"),
                        lc_status,
                        data.get("decision_status", "已定"),
                        data.get("impl_status", "未实现"),
                        data.get("priority", "普通"),
                        data.get("content", ""),
                        data.get("sources", ""),
                        json.dumps(data.get("discussion", []), ensure_ascii=False) if isinstance(data.get("discussion"), list) else data.get("discussion_json", "[]"),
                        data.get("updated_at", now_iso),
                        new_version,
                        wf_state,
                        outcome,
                        rejection_reason,
                        superseded_by,
                        impl_state,
                        impl_commit,
                        impl_verifier,
                        topic_id,
                        expected_version
                    ))
                    if cursor.rowcount == 0:
                        actual = cursor.execute("SELECT id, version FROM topics WHERE id = ?", (topic_id,)).fetchone()
                        raise VersionConflictError(
                            current_version=actual["version"] if actual else (current_ver + 1),
                            expected_version=expected_version,
                            topic_id=topic_id
                        )
                    cursor.execute("""
                        INSERT INTO topic_version_seq (topic_id, max_version) VALUES (?, ?)
                        ON CONFLICT(topic_id) DO UPDATE SET max_version = MAX(max_version, excluded.max_version)
                    """, (topic_id, new_version))
                    return new_version
            else:
                if expected_version is not None:
                    raise VersionConflictError(
                        current_version=None,
                        expected_version=expected_version,
                        topic_id=topic_id
                    )
                if exact_version is not None:
                    new_version = exact_version
                else:
                    seq_row = cursor.execute("SELECT max_version FROM topic_version_seq WHERE topic_id = ?", (topic_id,)).fetchone()
                    new_version = (seq_row["max_version"] + 1) if seq_row else 1

            cursor.execute("""
                INSERT INTO topics (
                    id, title, section, object, function,
                    lifecycle_status, decision_status, impl_status, priority,
                    content, sources, discussion_json, updated_at,
                    version, workflow_state, decision_outcome, rejection_reason,
                    superseded_by, implementation_state, impl_commit, impl_verifier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    updated_at=excluded.updated_at,
                    version=excluded.version,
                    workflow_state=excluded.workflow_state,
                    decision_outcome=excluded.decision_outcome,
                    rejection_reason=excluded.rejection_reason,
                    superseded_by=excluded.superseded_by,
                    implementation_state=excluded.implementation_state,
                    impl_commit=excluded.impl_commit,
                    impl_verifier=excluded.impl_verifier
            """, (
                topic_id,
                data.get("title", ""),
                data.get("section", "未分类"),
                data.get("object", "通用系统"),
                data.get("function", "核心规范"),
                lc_status,
                data.get("decision_status", "已定"),
                data.get("impl_status", "未实现"),
                data.get("priority", "普通"),
                data.get("content", ""),
                data.get("sources", ""),
                json.dumps(data.get("discussion", []), ensure_ascii=False) if isinstance(data.get("discussion"), list) else data.get("discussion_json", "[]"),
                data.get("updated_at", now_iso),
                new_version,
                wf_state,
                outcome,
                rejection_reason,
                superseded_by,
                impl_state,
                impl_commit,
                impl_verifier
            ))
            cursor.execute("""
                INSERT INTO topic_version_seq (topic_id, max_version) VALUES (?, ?)
                ON CONFLICT(topic_id) DO UPDATE SET max_version = MAX(max_version, excluded.max_version)
            """, (topic_id, new_version))
            return new_version

        if conn is not None:
            return _execute(conn)
        else:
            with self.get_connection() as c:
                res = _execute(c)
                c.commit()
                return res

    def check_idempotency(self, request_id: str, topic_id_or_hash: str, req_hash: Optional[str] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        检查幂等性请求状态：
        返回 (is_valid, cached_response)
        - 若未记录该 request_id，返回 (True, None) 表示可以正常执行
        - 若已记录且 topic_id 与 req_hash 一致，返回 (True, cached_response) 表示重复幂等调用
        - 若已记录但 topic_id 或 req_hash 不一致，返回 (False, None) 表示请求 ID 冲突
        """
        if not request_id:
            return True, None

        if req_hash is None:
            expected_topic = None
            expected_hash = topic_id_or_hash
        else:
            expected_topic = topic_id_or_hash
            expected_hash = req_hash

        with self.get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT topic_id, req_hash, response_json, status FROM idempotency_keys WHERE request_id = ?",
                (request_id,)
            ).fetchone()
            if not row:
                return True, None
            if expected_topic is not None and row["topic_id"] != expected_topic:
                return False, None
            if row["req_hash"] == expected_hash:
                return True, json.loads(row["response_json"])
            return False, None

    def record_idempotency(
        self,
        request_id: str,
        topic_id: str,
        req_hash: str,
        response_data: Dict[str, Any],
        status: str = "completed"
    ):
        """记录已完成或已持久化的幂等请求结果"""
        if not request_id:
            return
        now_iso = datetime.datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO idempotency_keys (request_id, topic_id, req_hash, response_json, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    topic_id=excluded.topic_id,
                    req_hash=excluded.req_hash,
                    response_json=excluded.response_json,
                    created_at=excluded.created_at,
                    status=excluded.status
            """, (request_id, topic_id, req_hash, json.dumps(response_data, ensure_ascii=False), now_iso, status))
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

    def get_revision_by_id(self, rev_id: int) -> Optional[Dict[str, Any]]:
        """按 rev_id 查询快照详情"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT * FROM revisions WHERE rev_id = ?",
                (rev_id,)
            ).fetchone()
            return dict(row) if row else None

    def restore_topic_from_revision(
        self,
        topic_id: str,
        target_rev_id: int,
        author: str = "人类/Agent",
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        P1-C: 单议题针对性回滚，不影响其他议题正常数据：
        从指定 Revision 快照中提取该议题的特定状态并恢复，生成新的 RESTORE_TOPIC 审计快照，
        保留完整历史记录与时间旅行可追踪性
        """
        rev = self.get_revision_by_id(target_rev_id)
        if not rev:
            raise ValueError(f"未找到指定的版本快照 #{target_rev_id}")

        snapshot = json.loads(rev["snapshot_json"])
        target_topic = None
        for t in snapshot.get("topics", []):
            if t["id"] == topic_id:
                target_topic = t
                break

        if not target_topic:
            raise ValueError(f"在快照 #{target_rev_id} ({rev['rev_hash']}) 中未找到议题 [{topic_id}] 的记录")

        # 写入数据库，递增版本号
        new_version = self.upsert_topic(target_topic)

        # 记录恢复审计 Revision 快照，保留原历史
        new_rev = self.commit_revision(
            action_type="TOPIC_RESTORE",
            summary=f"针对性恢复议题 [{target_topic['title']}] 至快照 {rev['rev_hash']}",
            topic_id=topic_id,
            author=author,
            diff_summary=f"restore_of={rev['rev_hash']}, rev_id={target_rev_id}, reason={reason or '用户按议题精准撤销'}"
        )

        return {
            "status": "success",
            "topic": target_topic,
            "new_version": new_version,
            "restored_from": rev["rev_hash"],
            "new_revision": new_rev["rev_hash"],
            "message": f"议题 [{topic_id}] 已成功恢复至快照 {rev['rev_hash']}"
        }

    def rollback_revision(self, target_rev_id: int, author: str = "人类/Agent") -> Dict[str, Any]:
        """将数据库完全回滚至指定的 Revision 快照，并返回快照数据以供文件同步"""
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

            # 获取历史最高写入代次（查持久序列 topic_version_seq 与当前 topics，杜绝删除与回滚后的 ABA 并发令牌复用） (F08, F05)
            current_max_versions = {}
            for r in cursor.execute("SELECT topic_id, max_version FROM topic_version_seq").fetchall():
                current_max_versions[r["topic_id"]] = r["max_version"]
            for r in cursor.execute("SELECT id, version FROM topics").fetchall():
                current_max_versions[r["id"]] = max(current_max_versions.get(r["id"], 0), r["version"] or 1)

            # 清空当前业务表并按快照恢复 (复用当前写连接以避免自死锁)
            cursor.execute("DELETE FROM topics")
            for t in snapshot.get("topics", []):
                tid = t["id"]
                prior_max = current_max_versions.get(tid, 0)
                snap_ver = t.get("version", 1)
                new_ver = max(prior_max, snap_ver) + 1
                t["version"] = new_ver
                self.upsert_topic(t, exact_version=new_ver, conn=conn)

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
            summary=f"全库回滚至快照 {target_hash} ({target_summary})",
            author=author,
            diff_summary=f"已重置全量业务表至版本 #{target_rev_id}"
        )
        return {
            "status": "success",
            "rolled_back_to": target_hash,
            "new_revision": new_rev["rev_hash"],
            "snapshot": snapshot,
            "message": f"成功全库回滚至快照 {target_hash}"
        }

    def backup_database(self, backup_path: Path) -> Dict[str, Any]:
        """
        使用 SQLite 官方 Backup API 进行无阻塞在线一致性热备份
        """
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as src_conn:
            dest_conn = sqlite3.connect(str(backup_path))
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()

        size_bytes = backup_path.stat().st_size
        return {
            "status": "success",
            "backup_path": str(backup_path),
            "size_bytes": size_bytes,
            "created_at": datetime.datetime.now().isoformat()
        }

    def export_full_data(self, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        """导出全量结构化数据"""
        if conn is None:
            with self.get_connection() as c:
                return self.export_full_data(conn=c)

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
                "updated_at": r["updated_at"],
                "version": r["version"] or 1,
                "workflow_state": r["workflow_state"] or "discussing",
                "decision_outcome": r["decision_outcome"] or "",
                "rejection_reason": r["rejection_reason"] or "",
                "superseded_by": r["superseded_by"] or "",
                "implementation_state": r["implementation_state"] or "not_started",
                "impl_commit": r["impl_commit"] or "",
                "impl_verifier": r["impl_verifier"] or ""
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

        return doc_data
