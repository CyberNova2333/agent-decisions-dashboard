"""Optional, read-only task hooks. No global Agent configuration is installed."""
import argparse
import ipaddress
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, quote
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler

from core.config import load_config
from core.contracts import validate_portable_id


class HookError(ValueError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AgentHooks:
    def __init__(self, config, base_url=None):
        self.config = config
        host = config.host
        self.base_url = (base_url or f"http://{'[' + host + ']' if ':' in host else host}:{config.port}").rstrip("/")
        url = urlsplit(self.base_url)
        try:
            local = url.hostname == "localhost" or ipaddress.ip_address(url.hostname).is_loopback
            valid_port = url.port is None or 1 <= url.port <= 65535
        except (ValueError, TypeError):
            local, valid_port = False, False
        if url.scheme != "http" or not local or not valid_port or url.username or url.password or url.path or url.query or url.fragment:
            raise HookError("钩子只连接明确的本机 HTTP 看板地址")
        # Local records must not be sent to a proxy or a redirect destination.
        self.opener = build_opener(ProxyHandler({}), NoRedirects())

    def get(self, path):
        try:
            with self.opener.open(self.base_url + path, timeout=10) as response:
                raw = response.read(50 * 1024 * 1024 + 1)
                if len(raw) > 50 * 1024 * 1024:
                    raise HookError("上下文过大，请按模块或议题查询")
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            raise HookError(f"看板返回 HTTP {exc.code}：{path}；未执行写入") from exc
        except (URLError, OSError, ValueError) as exc:
            raise HookError(f"无法读取看板：{exc}；未执行写入") from exc

    def preflight(self):
        status = self.get("/api/status")
        if not isinstance(status, dict) or status.get("status") != "ok":
            raise HookError("看板状态响应无效")
        for field, expected in (("database_path", self.config.database_path), ("topics_dir", self.config.decisions_dir)):
            actual = status.get(field)
            # Treat server paths as text, never resolve an untrusted UNC path.
            if not isinstance(actual, str) or os.path.normcase(os.path.normpath(actual)) != os.path.normcase(str(expected.resolve())):
                raise HookError(f"连接的看板与指定配置不匹配：{field}；请核对服务端口和配置文件")
        consistency = status.get("consistency")
        if not isinstance(consistency, dict) or consistency.get("consistent") is not True:
            raise HookError("台账文件、索引或导出不一致；先核对文件和未完成请求，不要自动重建或继续写入")
        return status

    def before_task(self, module=None, topic_id=None, path_keyword=None):
        self.preflight()
        requested_topic = None
        if topic_id:
            validate_portable_id(topic_id)
            requested_topic = self.get("/api/topic/" + quote(topic_id, safe=""))
        query = urlencode({key: value for key, value in
                           (("module", module), ("topic_id", topic_id), ("path", path_keyword)) if value})
        context = self.get("/api/agent/context?" + query)
        if not isinstance(context, dict):
            raise HookError("看板上下文响应无效")
        if requested_topic is not None:
            # Explicit topic reads retain deferred/superseded records too.
            context["requested_topic"] = requested_topic
        return context

    def after_write(self, topic_id, receipt):
        validate_portable_id(topic_id)
        if not isinstance(receipt, dict) or receipt.get("status") != "success":
            raise HookError("保存回执未确认成功；保留原请求 ID、原版本和原 payload 排查/重试")
        nested_topic = receipt.get("topic") or {}
        if not isinstance(nested_topic, dict):
            raise HookError("回执 topic 字段格式无效")
        receipt_topic = receipt.get("topic_id") or nested_topic.get("id")
        if receipt_topic != topic_id:
            raise HookError("回执议题与 --topic 不匹配")
        version = receipt.get("new_version", receipt.get("version"))
        if type(version) is not int or version < 1:
            raise HookError("回执没有有效议题版本；本钩子不用于确认删除或全库恢复")
        for field in ("save_status", "export_status"):
            if field in receipt and receipt[field] != "ok":
                raise HookError(f"保存仍有未完成阶段：{field}={receipt[field]}")
        if receipt.get("git_status") == "pending":
            raise HookError("Git 阶段仍待确认；不要把保存报告为全部完成")
        self.preflight()
        topic = self.get("/api/topic/" + quote(topic_id, safe=""))
        if not isinstance(topic, dict) or topic.get("version") != version:
            raise HookError("回执版本已不是当前版本；重新读取并核对，不要自动覆盖后续改动")
        git_status = receipt.get("git_status", "not_applicable")
        return {"status": "checked", "topic_id": topic_id, "version": version,
                "consistent": True, "git_status": git_status,
                "git_committed": git_status == "committed",
                "note": "只确认台账保存与当前版本；不证明实现代码或测试已通过"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Agent 任务前/写入后只读检查钩子")
    parser.add_argument("--config", type=Path, help="目标项目配置；相对数据路径以配置目录为准")
    parser.add_argument("--url", help="覆盖连接地址（仅本机 HTTP，仍校验目标数据路径）")
    commands = parser.add_subparsers(dest="command", required=True)
    before = commands.add_parser("before-task", help="确认项目与一致性，输出完整决策上下文 JSON")
    before.add_argument("--module")
    before.add_argument("--topic")
    before.add_argument("--path", dest="path_keyword")
    after = commands.add_parser("after-write", help="核对成功回执、当前版本及一致性")
    after.add_argument("--topic", required=True)
    after.add_argument("--receipt", type=Path, required=True, help="原始 HTTP 成功响应 JSON 文件")
    args = parser.parse_args(argv)
    try:
        hooks = AgentHooks(load_config(args.config), args.url)
        if args.command == "before-task":
            result = hooks.before_task(args.module, args.topic, args.path_keyword)
        else:
            receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
            result = hooks.after_write(args.topic, receipt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (HookError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "blocked", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
