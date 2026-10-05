# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - HTTP Server & REST API
基于 Python 标准库的高性能决策看板服务端
具备安全防护、乐观锁并发检查、幂等去重与 Agent 上下文导出接口
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
from core.db import DatabaseManager, VersionConflictError
from core.markdown_parser import TopicMarkdownParser
from core.git_engine import GitEngine
from core.decision_service import DecisionService, TopicValidationError, IdempotencyConflictError
from core.recovery import RecoveryManager
from core.agent_context import AgentContextEngine

MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB 最大请求体限制防 DoS

class DashboardServer:
    def __init__(self, config: Config, web_dir: Optional[Path] = None, host: Optional[str] = None, port: Optional[int] = None):
        self.config = config
        self.repo_root = config.base_dir
        self.web_dir = web_dir or (Path(__file__).resolve().parent.parent / "web")
        self.host = host or getattr(config, "host", "127.0.0.1")
        self.port = port or getattr(config, "port", 8765)
        self.service = DecisionService(config)
        self.recovery = RecoveryManager(config, self.service.db)
        self.agent = AgentContextEngine(config, self.service.db)
        self.db = self.service.db
        self.git = self.service.git
        self.parser = self.service.parser

        # 启动时自检并初始化：若库为空且有 metadata.json，则自动导入
        self._ensure_initial_data()

    def _ensure_initial_data(self):
        """冷启动自愈：数据库为空时从 Markdown 或 metadata.json 导入初始议题"""
        try:
            db_topics = self.db.get_all_topics()
            if not db_topics:
                # 优先从 Markdown 重建
                if self.config.decisions_dir.exists() and list(self.config.decisions_dir.glob("*.md")):
                    self.recovery.rebuild_index_from_markdown()
                elif self.config.metadata_json_path.exists():
                    data = json.loads(self.config.metadata_json_path.read_text(encoding="utf-8"))
                    for t in data.get("topics", []):
                        self.db.upsert_topic(t)
        except Exception as e:
            print(f"[WARN] 初始数据自检异常: {e}")

    def load_all_topics_meta(self) -> list:
        """从 SQLite 读取所有议题的元数据列表（毫秒级冷启动）"""
        topics_list = []
        try:
            db_topics = self.db.get_all_topics()
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
                    "sources": r.get("sources", ""),
                    "rounds_count": rounds_count,
                    "last_user_opinion": user_op if user_op != "—" else "",
                    "last_agent_reply": agent_rep if agent_rep != "—" else "",
                    "updated_at": r["updated_at"]
                })
        except Exception as e:
            print(f"[WARN] 读取元数据失败: {e}")
        return topics_list


def make_handler(server: DashboardServer):
    class RequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(server.web_dir), **kwargs)

        def _get_allowed_origin(self) -> Optional[str]:
            origin = self.headers.get("Origin")
            if not origin:
                return None
            try:
                parsed_origin = urllib.parse.urlparse(origin)
                if parsed_origin.scheme not in ("http", "https"):
                    return None
                host = parsed_origin.hostname
                allowed_hosts = {"localhost", "127.0.0.1"}
                srv_host = getattr(server, "host", None) or getattr(server.config, "host", "127.0.0.1")
                if srv_host:
                    allowed_hosts.add(srv_host)
                if host in allowed_hosts:
                    return origin
            except Exception:
                pass
            return None

        def end_headers(self):
            try:
                allowed_origin = self._get_allowed_origin()
                if allowed_origin:
                    self.send_header("Access-Control-Allow-Origin", allowed_origin)
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Request-ID, X-Expected-Version")
                    self.send_header("Vary", "Origin")
            except Exception:
                pass
            super().end_headers()

        def do_OPTIONS(self):
            origin = self.headers.get("Origin")
            if origin and not self._get_allowed_origin():
                self.send_response(403)
                super().end_headers()
                return
            self.send_response(200)
            self.end_headers()

        def _send_json(self, status_code: int, data: Any):
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

        def _send_text(self, status_code: int, text: str, content_type: str = "text/plain; charset=utf-8"):
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(text.encode("utf-8"))

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query_params = urllib.parse.parse_qs(parsed.query)

            if path == "/":
                self.send_response(302)
                self.send_header("Location", "/dashboard.html")
                self.end_headers()
                return

            elif path == "/api/config":
                self._send_json(200, server.config.to_dict())
                return

            elif path == "/api/status":
                head_hash = server.git.get_head_hash(short=True)
                consistency = server.recovery.check_consistency()
                res = {
                    "status": "ok",
                    "project_name": server.config.project_name,
                    "database": str(server.config.database_path.name),
                    "git_commit": head_hash,
                    "topics_dir": str(server.config.decisions_dir),
                    "consistency": consistency,
                    "server_time": datetime.datetime.now().isoformat()
                }
                self._send_json(200, res)
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
                self._send_json(200, res)
                return

            elif path.startswith("/api/topic/"):
                raw_id = path.replace("/api/topic/", "").strip()
                try:
                    topic_id = server.service.validate_topic_id(raw_id)
                except TopicValidationError as e:
                    self._send_json(400, {"error": "invalid_topic_id", "message": str(e)})
                    return

                md_file = server.config.decisions_dir / f"{topic_id}.md"
                detail = server.parser.parse_markdown_file(md_file)
                if not detail:
                    # 尝试从 DB 补充
                    row = server.db.get_topic(topic_id)
                    if row:
                        detail = {
                            "id": row["id"],
                            "title": row["title"],
                            "version": row.get("version", 1),
                            "workflow_state": row.get("workflow_state", "discussing"),
                            "core_content": row.get("content", ""),
                            "rounds": []
                        }

                if detail:
                    self._send_json(200, detail)
                else:
                    self._send_json(404, {"error": "not_found", "message": f"未找到议题 [{topic_id}]"})
                return

            elif path == "/api/git/log":
                commits = server.git.get_commit_history(limit=30)
                revisions = server.db.get_revisions(limit=30)
                self._send_json(200, {"commits": commits, "revisions": revisions})
                return

            elif path == "/api/agent/context":
                # 面向 Agent 的上下文只读导出
                mod = query_params.get("module", [None])[0]
                kw = query_params.get("path", [None])[0]
                tid = query_params.get("topic_id", [None])[0]
                fmt = query_params.get("format", ["json"])[0]

                ctx = server.agent.query_context(module=mod, path_keyword=kw, topic_id=tid)
                if fmt.lower() == "markdown":
                    md_text = server.agent.format_as_markdown(ctx)
                    self._send_text(200, md_text, content_type="text/markdown; charset=utf-8")
                else:
                    self._send_json(200, ctx)
                return

            elif path == "/api/recovery/check":
                report = server.recovery.check_consistency()
                self._send_json(200, report)
                return

            return super().do_GET()

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            # 跨站请求防御：若带有非受信任的 Origin，阻断写请求 (R12)
            origin = self.headers.get("Origin")
            if origin and not self._get_allowed_origin():
                self._send_json(403, {"error": "forbidden_origin", "message": f"跨站请求已被本地安全策略阻断: {origin}"})
                return

            cl_header = self.headers.get("Content-Length")
            try:
                length = int(cl_header) if cl_header is not None else 0
                if length < 0:
                    self._send_json(400, {"error": "bad_request", "message": "Content-Length 必须为非负整数"})
                    return
            except (ValueError, TypeError):
                self._send_json(400, {"error": "bad_request", "message": "Content-Length 格式非法，必须为整数"})
                return

            if length > MAX_BODY_SIZE:
                self._send_json(413, {"error": "payload_too_large", "message": f"请求体超限 (最大允许 {MAX_BODY_SIZE} 字节)"})
                return

            try:
                raw_bytes = self.rfile.read(length) if length > 0 else b"{}"
                raw_body = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                self._send_json(400, {"error": "bad_encoding", "message": "请求体必须为 UTF-8 编码格式"})
                return

            try:
                data = json.loads(raw_body) if raw_body else {}
            except Exception as e:
                self._send_json(400, {"error": "bad_json", "message": f"无效的 JSON 数据: {e}"})
                return

            if not isinstance(data, dict):
                self._send_json(400, {"error": "bad_json", "message": "顶层 JSON 数据必须是对象 (Object)"})
                return

            request_id = self.headers.get("X-Request-ID") or data.get("request_id")
            expected_ver_raw = self.headers.get("X-Expected-Version") or data.get("expected_version")
            expected_ver = None
            if expected_ver_raw is not None:
                try:
                    expected_ver = int(expected_ver_raw)
                    if expected_ver < 1:
                        self._send_json(400, {"error": "invalid_expected_version", "message": "X-Expected-Version 必须是大于等于 1 的正整数"})
                        return
                except (ValueError, TypeError):
                    self._send_json(400, {"error": "invalid_expected_version", "message": "X-Expected-Version 格式非法，必须是有效整数"})
                    return

            # 1. 保存议题
            if path.startswith("/api/topic/") and path.endswith("/save"):
                raw_id = path.replace("/api/topic/", "").replace("/save", "").strip()
                try:
                    res = server.service.save_topic(
                        topic_id=raw_id,
                        data=data,
                        expected_version=expected_ver,
                        request_id=request_id
                    )
                    self._send_json(200, res)
                except VersionConflictError as e:
                    current_data = server.db.get_topic(e.topic_id)
                    self._send_json(409, {
                        "error": "version_conflict",
                        "message": str(e),
                        "current_version": e.current_version,
                        "expected_version": e.expected_version,
                        "current_topic": current_data
                    })
                except IdempotencyConflictError as e:
                    self._send_json(409, {"error": "idempotency_conflict", "message": str(e)})
                except TopicValidationError as e:
                    self._send_json(400, {"error": "validation_error", "message": str(e)})
                except Exception as e:
                    self._send_json(500, {"error": "server_error", "message": str(e)})
                return

            # 2. 新建议题
            elif path == "/api/topic/create":
                try:
                    res = server.service.create_topic(data, request_id=request_id)
                    self._send_json(200, res)
                except TopicValidationError as e:
                    self._send_json(400, {"error": "validation_error", "message": str(e)})
                except Exception as e:
                    self._send_json(500, {"error": "server_error", "message": str(e)})
                return

            # 3. 单议题针对性回滚 (P1-C)
            elif path.startswith("/api/topic/") and path.endswith("/restore"):
                raw_id = path.replace("/api/topic/", "").replace("/restore", "").strip()
                rev_id = data.get("rev_id")
                if not rev_id:
                    self._send_json(400, {"error": "missing_rev_id", "message": "缺少 rev_id 参数"})
                    return
                try:
                    res = server.service.restore_single_topic(
                        topic_id=raw_id,
                        rev_id=int(rev_id),
                        author=data.get("author", "用户/前端"),
                        reason=data.get("reason", "")
                    )
                    self._send_json(200, res)
                except Exception as e:
                    self._send_json(500, {"error": "restore_failed", "message": str(e)})
                return

            # 4. 关联实现证据与核验 (P2-E)
            elif path.startswith("/api/topic/") and path.endswith("/verify"):
                raw_id = path.replace("/api/topic/", "").replace("/verify", "").strip()
                commit_hash = data.get("impl_commit", "").strip()
                verifier = data.get("verifier", "Agent/CI").strip()
                test_summary = data.get("test_summary", "").strip()
                mark_verified = bool(data.get("mark_verified", True))
                if not commit_hash:
                    self._send_json(400, {"error": "missing_commit", "message": "必须提供实现代码的 Git 提交 Hash"})
                    return
                try:
                    res = server.agent.record_verification(
                        topic_id=raw_id,
                        impl_commit=commit_hash,
                        verifier=verifier,
                        test_summary=test_summary,
                        mark_verified=mark_verified
                    )
                    self._send_json(200, res)
                except Exception as e:
                    self._send_json(500, {"error": "verify_failed", "message": str(e)})
                return

            # 5. 全库快照回滚
            elif path == "/api/rollback":
                rev_id = data.get("rev_id")
                if not rev_id:
                    self._send_json(400, {"error": "missing_rev_id", "message": "缺少 rev_id"})
                    return
                try:
                    res = server.service.rollback_full(
                        rev_id=int(rev_id),
                        author=data.get("author", "用户/看板")
                    )
                    self._send_json(200, res)
                except Exception as e:
                    self._send_json(500, {"error": "rollback_failed", "message": str(e)})
                return

            # 6. 从 Markdown 重新全量重建索引 (P1-A Recovery)
            elif path == "/api/recovery/rebuild":
                try:
                    res = server.recovery.rebuild_index_from_markdown()
                    self._send_json(200, res)
                except Exception as e:
                    self._send_json(500, {"error": "rebuild_failed", "message": str(e)})
                return

            # 7. SQLite 在线热备份 (Section 5)
            elif path == "/api/backup":
                backup_filename = f"decisions_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                target_p = server.config.base_dir / "backups" / backup_filename
                try:
                    res = server.db.backup_database(target_p)
                    self._send_json(200, res)
                except Exception as e:
                    self._send_json(500, {"error": "backup_failed", "message": str(e)})
                return

            self._send_json(404, {"error": "not_found", "message": f"未找到接口: {path}"})

    return RequestHandler

def main():
    parser = argparse.ArgumentParser(description="Agent Decisions Dashboard Server")
    parser.add_argument("--config", type=str, help="配置文件路径")
    parser.add_argument("--host", type=str, help="绑定主机地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, help="绑定服务端口 (默认 8765)")
    parser.add_argument("--no-browser", action="store_true", help="启动时不自动打开浏览器")
    parser.add_argument("--check-consistency", action="store_true", help="检查 Markdown、SQLite 与 metadata.json 一致性后退出")
    parser.add_argument("--rebuild-index", action="store_true", help="以 Markdown 文件为事实源全量重建索引后退出")
    parser.add_argument("--export-agent-context", type=str, help="按模块导出 Agent 治理 Prompt Markdown 后退出")
    args = parser.parse_args()

    cfg_path = Path(args.config) if args.config else None
    config = load_config(cfg_path)

    # CLI 独立操作模式
    if args.check_consistency:
        rec = RecoveryManager(config)
        report = rec.check_consistency()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if report["consistent"] else 1)

    if args.rebuild_index:
        rec = RecoveryManager(config)
        res = rec.rebuild_index_from_markdown()
        print(f"重建完成: {res['message']}")
        sys.exit(0)

    if args.export_agent_context:
        agent_eng = AgentContextEngine(config)
        ctx = agent_eng.query_context(module=args.export_agent_context)
        print(agent_eng.format_as_markdown(ctx))
        sys.exit(0)

    host = args.host or config.host
    port = args.port or config.port

    server = DashboardServer(config, host=host, port=port)
    handler_class = make_handler(server)

    httpd = HTTPServer((host, port), handler_class)
    url = f"http://{host}:{port}/dashboard.html"
    print("=" * 64)
    print(f"  {config.project_name} - 服务已启动")
    print(f"  服务地址: {url}")
    print(f"  数据目录: {config.decisions_dir}")
    print(f"  数据库:   {config.database_path}")
    print(f"  安全策略: 绑定主机={host} | 最大请求体=10MB | 暂存区保护=已启用")
    print("=" * 64)

    if not args.no_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已正常退出")

if __name__ == "__main__":
    main()
