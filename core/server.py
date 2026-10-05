# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - HTTP Server & REST API
基于 Python 标准库的高性能决策看板服务端
"""

import sys
import os
import json
import datetime
import argparse
import webbrowser
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.config import Config, load_config
from core.db import DatabaseManager
from core.markdown_parser import TopicMarkdownParser
from core.git_engine import GitEngine

class DashboardServer:
    def __init__(self, config: Config, web_dir: Optional[Path] = None):
        self.config = config
        self.repo_root = config.base_dir
        self.web_dir = web_dir or (Path(__file__).resolve().parent.parent / "web")
        self.db = DatabaseManager(config.database_path, config)
        self.git = GitEngine(self.repo_root, config)
        self.parser = TopicMarkdownParser()

    def get_lifecycle_badge(self, lifecycle_id: str) -> str:
        for state in self.config.lifecycle_states:
            if state["id"] == lifecycle_id:
                return state["badge"]
        return "🟡 待讨论"

    def load_all_topics_meta(self) -> list:
        """从 SQLite 读取所有议题的元数据列表（毫秒级冷启动）"""
        topics_list = []
        try:
            db_topics = self.db.get_all_topics()
            if not db_topics and self.config.metadata_json_path.exists():
                try:
                    data = json.loads(self.config.metadata_json_path.read_text(encoding="utf-8"))
                    topics_list = data.get("topics", [])
                    for t in topics_list:
                        self.db.upsert_topic(t)
                    return topics_list
                except Exception:
                    pass

            for r in db_topics:
                topic_id = r["id"]
                md_file = self.config.decisions_dir / f"{topic_id}.md"
                rounds_count = self.parser.count_rounds(md_file)

                discussion = json.loads(r["discussion_json"]) if r.get("discussion_json") else []
                user_op = ""
                agent_rep = ""
                for d in discussion:
                    k = d.get("key", "")
                    if "用户" in k:
                        user_op = d.get("val", "")
                    elif "答复" in k or "说明" in k:
                        agent_rep = d.get("val", "")

                topics_list.append({
                    "id": topic_id,
                    "title": r["title"],
                    "file": f"decisions/{topic_id}.md",
                    "section": r["section"],
                    "object": r["object"],
                    "function": r["function"],
                    "lifecycle_status": r["lifecycle_status"],
                    "decision_status": r["decision_status"],
                    "impl_status": r["impl_status"],
                    "priority": r.get("priority", "普通"),
                    "summary": (r["content"] or "").split("\n\n")[0].replace("\n", " ")[:140],
                    "sources": r.get("sources", ""),
                    "rounds_count": rounds_count,
                    "last_user_opinion": user_op if user_op != "—" else "",
                    "last_agent_reply": agent_rep if agent_rep != "—" else "",
                    "updated_at": r["updated_at"]
                })
        except Exception as e:
            print(f"[WARN] 读取元数据失败: {e}")
            if self.config.metadata_json_path.exists():
                try:
                    data = json.loads(self.config.metadata_json_path.read_text(encoding="utf-8"))
                    topics_list = data.get("topics", [])
                except Exception:
                    pass
        return topics_list

    def save_topic_and_commit(self, topic_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        保存议题决策：
        1. 在 decisions/<id>.md 中追加第 n 轮讨论记录并更新标头
        2. 更新 SQLite 数据库与 metadata.json
        3. 自动递交 Git 语义化提交
        4. 记录全量 Revision 数据库快照
        """
        title = data.get("title", "")
        lc = data.get("lifecycle_status", "decided")
        dec_status = data.get("decision_status", "已定")
        impl_status = data.get("impl_status", "未实现")
        priority = data.get("priority", "普通")
        user_opinion = data.get("new_user_opinion", "").strip()
        agent_reply = data.get("new_agent_reply", "").strip()
        commit_msg = data.get("commit_message", "").strip()
        content_override = data.get("content_override")
        obj = data.get("object", "通用系统")
        func = data.get("function", "核心规范")
        sources = data.get("sources", "")

        md_file = self.config.decisions_dir / f"{topic_id}.md"
        existing = self.parser.parse_markdown_file(md_file)

        now_dt = datetime.datetime.now()
        now_iso = now_dt.isoformat()

        current_rounds = existing["rounds"] if existing else []
        new_round_num = len(current_rounds) + 1

        core_content = content_override if content_override is not None else (existing["core_content"] if existing else "")
        lifecycle_badge = self.get_lifecycle_badge(lc)

        new_round_info = None
        if user_opinion or agent_reply or commit_msg:
            new_round_info = {
                "commit_message": commit_msg,
                "user_opinion": user_opinion,
                "agent_reply": agent_reply
            }

        # 1. 写回单议题 Markdown
        md_text = self.parser.serialize_markdown(
            topic_id=topic_id,
            title=title,
            lifecycle_badge=lifecycle_badge,
            decision_status=dec_status,
            impl_status=impl_status,
            priority=priority,
            obj=obj,
            func=func,
            core_content=core_content,
            existing_rounds=current_rounds,
            new_round=new_round_info
        )
        self.config.decisions_dir.mkdir(parents=True, exist_ok=True)
        md_file.write_text(md_text, encoding="utf-8")

        # 2. 更新 SQLite 数据库
        topic_row = self.db.get_topic(topic_id)
        discussion = json.loads(topic_row["discussion_json"]) if (topic_row and topic_row.get("discussion_json")) else []
        if user_opinion:
            discussion.append({"key": f"第 {new_round_num} 轮用户意见", "val": user_opinion})
        if agent_reply:
            discussion.append({"key": f"第 {new_round_num} 轮落实答复", "val": agent_reply})

        self.db.upsert_topic({
            "id": topic_id,
            "title": title,
            "section": data.get("section", "未分类"),
            "object": obj,
            "function": func,
            "lifecycle_status": lc,
            "decision_status": dec_status,
            "impl_status": impl_status,
            "priority": priority,
            "content": core_content,
            "sources": sources,
            "discussion": discussion,
            "updated_at": now_iso
        })

        if commit_msg:
            self.db.record_changelog(
                scope=f"[{title}](#{topic_id})",
                change=f"{commit_msg} [{lifecycle_badge}]",
                basis=f"用户原话: {user_opinion[:30]}..." if user_opinion else "用户明确决策"
            )

        # 3. 同步 metadata.json 与 doc_data.json
        all_meta = self.load_all_topics_meta()
        self.config.metadata_json_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.metadata_json_path.write_text(json.dumps({
            "updated_at": now_iso,
            "total_topics": len(all_meta),
            "topics": all_meta
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        # 4. 执行 Git 自动语义化提交
        staged = [md_file, self.config.metadata_json_path, self.config.database_path]
        commit_success, commit_result = self.git.commit_decision(
            topic_title=title,
            lifecycle_badge=lifecycle_badge,
            summary=commit_msg,
            user_opinion=user_opinion,
            agent_reply=agent_reply,
            staged_files=staged
        )

        commit_hash = commit_result if commit_success else "local"

        # 5. 记录 Revision 快照
        self.db.commit_revision(
            action_type="RECORD_DECISION",
            summary=f"[{lifecycle_badge}] {title} - {commit_msg}",
            topic_id=topic_id,
            author="用户",
            user_opinion=user_opinion,
            agent_reply=agent_reply,
            new_lifecycle=lc,
            diff_summary=f"Git Commit: {commit_hash}"
        )

        return {
            "status": "success",
            "commit_hash": commit_hash,
            "round": new_round_num,
            "topic_id": topic_id,
            "updated_at": now_iso,
            "message": f"决策已入库并生成 Git 提交 ({commit_hash})！"
        }


def make_handler(server: DashboardServer):
    class RequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(server.web_dir), **kwargs)

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            super().end_headers()

        def do_OPTIONS(self):
            self.send_response(200)
            self.end_headers()

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/":
                self.send_response(302)
                self.send_header("Location", "/dashboard.html")
                self.end_headers()
                return

            elif path == "/api/config":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(server.config.to_dict(), ensure_ascii=False).encode("utf-8"))
                return

            elif path == "/api/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                head_hash = server.git.get_head_hash(short=True)
                res = {
                    "status": "ok",
                    "project_name": server.config.project_name,
                    "database": str(server.config.database_path.name),
                    "git_commit": head_hash,
                    "topics_dir": str(server.config.decisions_dir),
                    "server_time": datetime.datetime.now().isoformat()
                }
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            elif path == "/api/topics":
                meta_list = server.load_all_topics_meta()
                full_data = server.db.export_full_data()
                res = {
                    "topics": meta_list,
                    "settled_decisions": full_data.get("settled_decisions", []),
                    "open_questions": full_data.get("open_questions", []),
                    "changelog": full_data.get("changelog", []),
                    "config": server.config.to_dict()
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            elif path.startswith("/api/topic/"):
                topic_id = path.replace("/api/topic/", "").strip()
                md_file = server.config.decisions_dir / f"{topic_id}.md"
                detail = server.parser.parse_markdown_file(md_file)
                if detail:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(detail, ensure_ascii=False).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()
                return

            elif path == "/api/git/log":
                commits = server.git.get_commit_history(limit=30)
                revisions = server.db.get_revisions(limit=30)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "commits": commits,
                    "revisions": revisions
                }, ensure_ascii=False).encode("utf-8"))
                return

            return super().do_GET()

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(raw_body) if raw_body else {}

            if path.startswith("/api/topic/") and path.endswith("/save"):
                topic_id = path.replace("/api/topic/", "").replace("/save", "").strip()
                res = server.save_topic_and_commit(topic_id, data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            elif path == "/api/topic/create":
                topic_id = data.get("id", "").strip()
                if not topic_id:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "缺少 topic ID"}, ensure_ascii=False).encode("utf-8"))
                    return

                res = server.save_topic_and_commit(topic_id, data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            elif path == "/api/rollback":
                rev_id = data.get("rev_id")
                try:
                    res = server.db.rollback_revision(rev_id)
                    server.git.stage_files([server.config.database_path])
                    server.git.commit_decision(
                        topic_title="全量数据库快照",
                        lifecycle_badge="时间旅行",
                        summary=f"回滚全量快照 #{rev_id}"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))
                return

            self.send_response(404)
            self.end_headers()

    return RequestHandler

def main():
    parser = argparse.ArgumentParser(description="Agent Decisions Dashboard Server")
    parser.add_argument("--config", type=str, help="配置文件路径")
    parser.add_argument("--host", type=str, help="绑定主机地址")
    parser.add_argument("--port", type=int, help="绑定服务端口")
    parser.add_argument("--no-browser", action="store_true", help="启动时不自动打开浏览器")
    args = parser.parse_args()

    cfg_path = Path(args.config) if args.config else None
    config = load_config(cfg_path)

    host = args.host or config.host
    port = args.port or config.port

    server = DashboardServer(config)
    handler_class = make_handler(server)

    httpd = HTTPServer((host, port), handler_class)
    url = f"http://{host}:{port}/dashboard.html"
    print("=" * 60)
    print(f"  {config.project_name} - 启动成功")
    print(f"  服务地址: {url}")
    print(f"  数据目录: {config.decisions_dir}")
    print(f"  数据库:   {config.database_path}")
    print("=" * 60)

    if not args.no_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已退出")

if __name__ == "__main__":
    main()
