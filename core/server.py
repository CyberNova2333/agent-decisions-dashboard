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
import ipaddress
import re
import socket
import hashlib
import sqlite3
import time
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
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
from core.contracts import decision_axes
from core.locking import ledger_lock

MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB 最大请求体限制防 DoS
REQUEST_TIMEOUT = 10


def is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = False  # server_close waits for in-flight writes on clean shutdown.
    def __init__(self, address, handler):
        if not is_loopback_host(address[0]):
            raise ValueError("看板仅支持本机回环地址监听")
        if ":" in address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(address, handler)

class DashboardServer:
    def __init__(self, config: Config, web_dir: Optional[Path] = None, host: Optional[str] = None, port: Optional[int] = None):
        self.host = config.host if host is None else host
        self.port = config.port if port is None else port
        if not is_loopback_host(self.host):
            raise ValueError("看板没有远程认证，仅允许 localhost 或回环 IP 地址监听")
        self.config = config
        self.repo_root = config.base_dir
        builtin_web = Path(__file__).resolve().parent / "web"
        source_web = Path(__file__).resolve().parent.parent / "web"
        self.web_dir = web_dir or (builtin_web if builtin_web.exists() else source_web)
        self.service = DecisionService(config)
        self.recovery = RecoveryManager(config, self.service.db)
        self.agent = AgentContextEngine(config, self.service.db)
        self.db = self.service.db
        self.git = self.service.git
        self.parser = self.service.parser

        # 启动时自检并初始化：只从权威 Markdown 导入
        self._ensure_initial_data()

    def _ensure_initial_data(self):
        """数据库为空时从 Markdown 导入；摘要导出不能用于恢复正文。"""
        try:
            db_topics = self.db.get_all_topics()
            if not db_topics:
                # 优先从 Markdown 重建
                if self.config.decisions_dir.exists() and list(self.config.decisions_dir.glob("*.md")):
                    self.recovery.rebuild_index_from_markdown()
                elif self.config.metadata_json_path.exists():
                    print("[WARN] 只有 metadata.json 摘要，未找到权威 Markdown；未导入议题，请恢复原始文档")

            # 若修订历史为空（如全新空项目），建立初始空基线快照供回滚/撤销首次创建 (R11)
            if len(self.db.get_revisions(limit=1)) == 0:
                self.db.commit_revision(
                    action_type="INIT",
                    summary="项目初始基线快照",
                    author="系统初始化"
                )
        except Exception as e:
            print(f"[WARN] 初始数据自检异常: {e}")

    def load_all_topics_meta(self) -> list:
        """从当前 SQLite 索引读取元数据；文件漂移由一致性检查处理。"""
        topics_list = []
        db_topics = self.db.get_all_topics()
        for r in db_topics:
            topic_id = r["id"]
            if not self.config.topic_is_active(topic_id):
                continue

            discussion = json.loads(r["discussion_json"]) if r.get("discussion_json") else []
            rounds = self.service._reconstruct_rounds_from_topic(dict(r, discussion=discussion))
            rounds_count = len(rounds)
            latest = rounds[-1] if rounds else {}
            user_op = latest.get("user_opinion", "")
            agent_rep = latest.get("agent_reply", "")
            last_user, last_agent = "", ""
            for entry in discussion:
                if "用户" in entry.get("key", ""): last_user = entry.get("val", "")
                elif "答复" in entry.get("key", "") or "落实" in entry.get("key", ""): last_agent = entry.get("val", "")

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
                "last_user_opinion": last_user if last_user != "—" else "",
                "last_agent_reply": last_agent if last_agent != "—" else "",
                "latest_round_user_opinion": user_op,
                "latest_round_agent_reply": agent_rep,
                "updated_at": r["updated_at"]
            })
        return topics_list

    def load_changelog(self) -> list:
        """读取当前产品视图的变更记录。

        议题变更的 scope 采用 ``[标题](#topic-id)`` 链接格式；启用活动范围
        时隐藏已迁出的议题，无法关联议题的全局记录仍保留。数据库本身不做
        删除，因此归档快照和直接议题查询仍能看到完整历史。
        """
        changes = self.db.get_changelog()
        active_ids = self.config.active_topic_ids
        if active_ids is None:
            return changes
        filtered = []
        for change in changes:
            scope = str(change.get("scope") or "")
            match = re.search(r"\(#([A-Za-z0-9][A-Za-z0-9_-]*)\)", scope)
            if match and match.group(1) not in active_ids:
                continue
            filtered.append(change)
        return filtered

    @staticmethod
    def overview_from_topics(topics):
        """概览是当前议题的投影，不依赖需要另外维护的历史导入表。"""
        settled, pending = [], []
        for topic in topics:
            wf, outcome = decision_axes(topic)
            if wf in ("decided", "deferred") and outcome in ("accepted", "partially_accepted", "rejected"):
                label = "部分同意" if outcome == "partially_accepted" else "已否决" if outcome == "rejected" else "已决策"
                if wf == "deferred":
                    label += " · 推迟再议（按原话中的条件继续）"
                settled.append({"title": topic["title"], "requirement": topic["summary"],
                                "details": topic["rejection_reason"] if outcome == "rejected" else topic["decision_status"],
                                "topic_ref": topic["id"], "outcome_label": label})
            if wf == "pending":
                pending.append({"item": topic["title"], "issue": topic["summary"],
                                "focus": topic["last_user_opinion"], "topic_ref": topic["id"]})
        return settled, pending


def make_handler(server: DashboardServer):
    class RequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(server.web_dir), **kwargs)

        def setup(self):
            super().setup()
            self.connection.settimeout(REQUEST_TIMEOUT)
            self._body_read = False

        def _drain_rejected_body(self):
            # Closing with unread input can reset the socket on Windows and hide
            # the error response. Send it first, then discard only a small body,
            # within a fixed deadline; never parse or execute the rejected data.
            if self._body_read or self.headers.get_all("Transfer-Encoding"):
                return
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0]):
                return
            remaining = int(lengths[0]) if len(lengths[0]) < 8 else 0
            if not 0 < remaining <= 65536:
                return
            self.close_connection = True
            deadline = time.monotonic() + 0.1
            try:
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_WR)
                while remaining:
                    timeout = deadline - time.monotonic()
                    if timeout <= 0:
                        break
                    self.connection.settimeout(timeout)
                    chunk = self.rfile.read1(min(remaining, 8192))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                pass

        def send_error(self, code, message=None, explain=None):
            super().send_error(code, message, explain)
            if code >= 400 and hasattr(self, "headers"):
                self._drain_rejected_body()

        def _trusted_authority(self, value: str, scheme: str = "http") -> bool:
            try:
                parsed = urllib.parse.urlsplit(f"{scheme}://{value}")
                allowed_hosts = {server.host, self.server.server_address[0], "localhost"}
                return (
                    scheme == "http" and parsed.hostname in allowed_hosts
                    and parsed.username is None and parsed.password is None
                    and not parsed.path and not parsed.query and not parsed.fragment
                    and (parsed.port or 80) == self.server.server_port
                )
            except ValueError:
                return False

        def parse_request(self):
            if not super().parse_request():
                return False
            hosts = self.headers.get_all("Host", [])
            if len(hosts) != 1 or not self._trusted_authority(hosts[0]):
                self.send_error(403, "Untrusted Host")
                return False
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1 or (origins and not self._get_allowed_origin()):
                self.send_error(403, "Untrusted Origin")
                return False
            return True

        def _get_allowed_origin(self) -> Optional[str]:
            origin = self.headers.get("Origin")
            if not origin:
                return None
            try:
                parsed_origin = urllib.parse.urlsplit(origin)
                request_host = urllib.parse.urlsplit("http://" + self.headers.get("Host", "")).hostname
                if (not parsed_origin.path and not parsed_origin.query and not parsed_origin.fragment
                        and parsed_origin.hostname == request_host
                        and self._trusted_authority(parsed_origin.netloc, parsed_origin.scheme)):
                    return origin
            except Exception:
                pass
            return None

        def end_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
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

        def send_head(self):
            # SimpleHTTPRequestHandler otherwise follows links outside the web root.
            target = Path(self.translate_path(self.path)).resolve()
            try:
                target.relative_to(server.web_dir.resolve())
            except ValueError:
                self.send_error(404)
                return None
            if not target.is_file():
                self.send_error(404)
                return None
            return super().send_head()

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
            if status_code >= 400:
                self._drain_rejected_body()

        def _send_text(self, status_code: int, text: str, content_type: str = "text/plain; charset=utf-8"):
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(text.encode("utf-8"))

        def do_GET(self):
            # Reads must not observe a half-finished file/index mutation.
            with ledger_lock(server.config.database_path):
                try:
                    self._dispatch_get()
                except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                    self._send_json(500, {"error": "read_failed", "message": str(exc)})

        def _dispatch_get(self):
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
                    "database_path": str(server.config.database_path.resolve()),
                    "git_commit": head_hash,
                    "topics_dir": str(server.config.decisions_dir.resolve()),
                    "consistency": consistency,
                    "server_time": datetime.datetime.now().isoformat()
                }
                self._send_json(200, res)
                return

            elif path == "/api/topics":
                meta_list = server.load_all_topics_meta()
                settled, pending = server.overview_from_topics(meta_list)
                res = {
                    "topics": meta_list,
                    "capabilities": {
                        "edit_latest_round": True,
                        "partially_accepted": True,
                        "independent_progress": True,
                        "delete_topic": True,
                        "verify_topic": True,
                        "edit_proposal": True,
                        "recovery_tools": True,
                    },
                    "settled_decisions": settled,
                    "open_questions": pending,
                    "changelog": server.load_changelog(),
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
                raw_limit = query_params.get("limit", ["30"])[0]
                raw_offset = query_params.get("offset", ["0"])[0]
                tid = query_params.get("topic_id", [None])[0]
                try:
                    limit_val = max(1, min(1000, int(raw_limit)))
                except (ValueError, TypeError):
                    limit_val = 30
                try:
                    offset_val = max(0, int(raw_offset))
                except (ValueError, TypeError):
                    offset_val = 0

                commits = server.git.get_commit_history(limit=limit_val)
                revisions = server.db.get_revisions(limit=limit_val, offset=offset_val, topic_id=tid)
                head_revision = server.db.get_revisions(limit=1)
                self._send_json(200, {"commits": commits, "revisions": revisions,
                                      "current_revision": head_revision[0]["rev_id"] if head_revision else 0})
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

            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self._send_json(403, {"error": "forbidden_origin", "message": "拒绝跨站写入"})
                return
            if self.headers.get_content_type() != "application/json":
                self._send_json(415, {"error": "unsupported_media_type", "message": "写请求必须使用 application/json"})
                return
            if self.headers.get_all("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                self._send_json(400, {"error": "bad_request", "message": "必须提供唯一 Content-Length，不支持 Transfer-Encoding"})
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
                self._body_read = True
                raw_bytes = self.rfile.read(length) if length > 0 else b"{}"
            except (TimeoutError, OSError):
                self._send_json(408, {"error": "request_timeout", "message": "请求体读取超时或中断"})
                return
            if length and len(raw_bytes) != length:
                self._send_json(400, {"error": "incomplete_body", "message": "请求体不完整"})
                return

            # 跨站请求防御：若带有非受信任的 Origin，阻断写请求 (R12, F10)
            origin = self.headers.get("Origin")
            if origin and not self._get_allowed_origin():
                self._send_json(403, {"error": "forbidden_origin", "message": f"跨站请求已被本地安全策略阻断: {origin}"})
                return

            try:
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

            with ledger_lock(server.config.database_path):
                self._dispatch_post(data)

        def _dispatch_post(self, data):
            path = urllib.parse.urlparse(self.path).path
            for field in ("rev_id", "expected_revision"):
                if field in data and (type(data[field]) is not int or data[field] < 1):
                    self._send_json(400, {"error": "validation_error", "message": f"{field} 必须为正整数"})
                    return

            request_id = self.headers.get("X-Request-ID", data.get("request_id"))
            if request_id is not None and (not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 256):
                self._send_json(400, {"error": "invalid_request_id", "message": "请求 ID 必须为 1–256 字符的非空字符串"})
                return
            expected_ver_raw = self.headers.get("X-Expected-Version", data.get("expected_version"))
            expected_ver = None
            if expected_ver_raw is not None:
                try:
                    if type(expected_ver_raw) is not int and not (isinstance(expected_ver_raw, str) and re.fullmatch(r"[0-9]+", expected_ver_raw)):
                        raise ValueError("invalid version type")
                    expected_ver = int(expected_ver_raw)
                    if expected_ver < 1:
                        self._send_json(400, {"error": "invalid_expected_version", "message": "X-Expected-Version 必须是大于等于 1 的正整数"})
                        return
                except (ValueError, TypeError):
                    self._send_json(400, {"error": "invalid_expected_version", "message": "X-Expected-Version 格式非法，必须是有效整数"})
                    return

            match = re.fullmatch(r"/api/topic/([^/]+)/(save|restore|verify|delete)", path)
            if path.startswith("/api/topic/") and path != "/api/topic/create":
                if not match:
                    self._send_json(404, {"error": "not_found"})
                    return
                try:
                    server.service.validate_topic_id(match[1])
                except TopicValidationError as e:
                    self._send_json(400, {"error": "validation_error", "message": str(e)})
                    return
                creation_replay = False
                if expected_ver is None and match[2] == "save" and request_id:
                    req_hash = hashlib.sha256(f"{match[1]}:None:{json.dumps(data, sort_keys=True, ensure_ascii=False)}".encode("utf-8")).hexdigest()
                    valid, cached = server.db.check_idempotency(request_id, match[1], req_hash)
                    creation_replay = valid and cached is not None
                elif expected_ver is None and match[2] == "restore" and request_id:
                    req_hash = server.service.restore_request_hash(
                        match[1], data.get("rev_id"), data.get("author", "用户/前端"), data.get("reason", ""), None)
                    valid, cached = server.db.check_idempotency(request_id, match[1], req_hash)
                    creation_replay = valid and cached is not None
                if expected_ver is None and not creation_replay and (match[2] in ("verify", "delete") or server.db.get_topic(match[1])):
                    self._send_json(428, {"error": "version_required", "message": "请先读取议题，再携带 expected_version 写入"})
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
                except IdempotencyConflictError as e:
                    self._send_json(409, {"error": "idempotency_conflict", "message": str(e)})
                except Exception as e:
                    self._send_json(500, {"error": "server_error", "message": str(e)})
                return

            # 3. 单议题针对性回滚 (P1-C, F02, F06, F08)
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
                        reason=data.get("reason", ""),
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
                    self._send_json(500, {"error": "restore_failed", "message": str(e)})
                return

            # 4. 关联实现证据与核验 (P2-E, F11)
            elif path.startswith("/api/topic/") and path.endswith("/verify"):
                raw_id = path.replace("/api/topic/", "").replace("/verify", "").strip()
                commit_hash = data.get("impl_commit")
                if not isinstance(commit_hash, str) or not commit_hash.strip():
                    self._send_json(400, {"error": "missing_commit", "message": "必须提供实现代码的 Git 提交 Hash (非空字符串)"})
                    return
                commit_hash = commit_hash.strip()

                if "mark_verified" in data:
                    raw_mv = data["mark_verified"]
                    if not isinstance(raw_mv, bool):
                        self._send_json(400, {"error": "invalid_mark_verified", "message": "mark_verified 必须为布尔值 (true/false)"})
                        return
                    mark_verified = raw_mv
                else:
                    mark_verified = True

                verifier = data.get("verifier", "Agent/CI")
                if not isinstance(verifier, str):
                    self._send_json(400, {"error": "invalid_verifier", "message": "verifier 必须为字符串"})
                    return
                verifier = verifier.strip()

                test_summary = data.get("test_summary", "")
                if not isinstance(test_summary, str):
                    self._send_json(400, {"error": "invalid_test_summary", "message": "test_summary 必须为字符串"})
                    return
                test_summary = test_summary.strip()

                try:
                    res = server.service.record_verification(
                        topic_id=raw_id,
                        impl_commit=commit_hash,
                        verifier=verifier,
                        test_summary=test_summary,
                        mark_verified=mark_verified,
                        expected_version=expected_ver,
                        request_id=request_id
                    )
                    self._send_json(200, res)
                except VersionConflictError as e:
                    self._send_json(409, {"error": "version_conflict", "message": str(e),
                                         "current_version": e.current_version, "expected_version": e.expected_version})
                except IdempotencyConflictError as e:
                    self._send_json(409, {"error": "idempotency_conflict", "message": str(e)})
                except TopicValidationError as e:
                    self._send_json(400, {"error": "validation_error", "message": str(e)})
                except Exception as e:
                    self._send_json(500, {"error": "verify_failed", "message": str(e)})
                return

            # 4.5. 归档删除单个议题
            elif path.startswith("/api/topic/") and path.endswith("/delete"):
                raw_id = path.replace("/api/topic/", "").replace("/delete", "").strip()
                try:
                    res = server.service.delete_topic(
                        topic_id=raw_id,
                        author=data.get("author", "用户/前端"),
                        reason=data.get("reason", ""),
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
                    self._send_json(500, {"error": "delete_failed", "message": str(e)})
                return

            # 5. 全库快照回滚
            elif path == "/api/rollback":
                expected_revision = data.get("expected_revision")
                if expected_revision is None:
                    self._send_json(428, {"error": "revision_required", "message": "请先读取历史列表，再携带 current_revision 作为 expected_revision"})
                    return
                rev_id = data.get("rev_id")
                if not rev_id:
                    self._send_json(400, {"error": "missing_rev_id", "message": "缺少 rev_id"})
                    return
                try:
                    res = server.service.rollback_full(
                        rev_id=int(rev_id),
                        author=data.get("author", "用户/看板"),
                        expected_revision=expected_revision
                    )
                    self._send_json(200, res)
                except VersionConflictError as e:
                    self._send_json(409, {"error": "revision_conflict", "message": "看板已有新记录，请重新打开历史列表并核对后再恢复",
                                         "current_revision": e.current_version})
                except Exception as e:
                    self._send_json(500, {"error": "rollback_failed", "message": str(e)})
                return

            # 6. 从 Markdown 重新全量重建索引 (P1-A Recovery)
            elif path == "/api/recovery/rebuild":
                try:
                    res = server.recovery.rebuild_index_from_markdown()
                    self._send_json(200 if res.get("status") == "success" else 409, res)
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
        print(json.dumps(res, ensure_ascii=False, indent=2))
        sys.exit(0 if res.get("status") == "success" else 1)

    if args.export_agent_context:
        agent_eng = AgentContextEngine(config)
        ctx = agent_eng.query_context(module=args.export_agent_context)
        print(agent_eng.format_as_markdown(ctx))
        sys.exit(0)

    host = args.host or config.host
    port = args.port or config.port

    server = DashboardServer(config, host=host, port=port)
    handler_class = make_handler(server)

    httpd = DashboardHTTPServer((host, port), handler_class)
    url_host = f"[{host}]" if ":" in host else host
    url = f"http://{url_host}:{httpd.server_port}/dashboard.html"
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
        print("\n正在等待已接收请求结束…")
    finally:
        httpd.server_close()
        print("服务已正常退出")

if __name__ == "__main__":
    main()
