# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Agent Context & Verification Engine
面向 Agent 的只读上下文导出、已否决红线约束输出与实现证据核验绑定
"""

import datetime
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from core.config import Config
from core.db import DatabaseManager
from core.markdown_parser import TopicMarkdownParser
from core.recovery import RecoveryManager

class AgentContextEngine:
    def __init__(self, config: Config, db: Optional[DatabaseManager] = None):
        self.config = config
        self.db = db or DatabaseManager(config.database_path, config)
        self.parser = TopicMarkdownParser()
        self.recovery = RecoveryManager(config, self.db)

    def query_context(
        self,
        module: Optional[str] = None,
        path_keyword: Optional[str] = None,
        topic_id: Optional[str] = None,
        include_rejected: bool = True
    ) -> Dict[str, Any]:
        """
        检索指定模块/路径相关的决策上下文，分离：
        1. 有效决策 (Active Decisions)
        2. 已否决方案与红线约束 (Rejected Proposals)
        3. 待实现/待核验要求 (Pending Requirements)
        """
        all_topics = self.db.get_all_topics()
        filtered = []

        mod_lower = module.lower() if module else ""
        path_lower = path_keyword.lower() if path_keyword else ""
        tid_lower = topic_id.lower() if topic_id else ""

        for t in all_topics:
            if tid_lower and t["id"].lower() != tid_lower:
                continue

            if mod_lower:
                section_str = (t.get("section") or "").lower()
                object_str = (t.get("object") or "").lower()
                func_str = (t.get("function") or "").lower()
                if mod_lower not in section_str and mod_lower not in object_str and mod_lower not in func_str:
                    continue

            if path_lower:
                content_str = (t.get("content") or "").lower()
                if path_lower not in content_str and path_lower not in (t.get("section") or "").lower():
                    continue

            filtered.append(t)

        active_decisions: List[Dict[str, Any]] = []
        rejected_proposals: List[Dict[str, Any]] = []
        pending_requirements: List[Dict[str, Any]] = []

        for t in filtered:
            outcome = t.get("decision_outcome", "")
            wf = t.get("workflow_state") or t.get("lifecycle_status", "discussing")
            impl = t.get("implementation_state") or "not_started"

            item = {
                "id": t["id"],
                "title": t["title"],
                "version": t.get("version", 1),
                "section": t.get("section", ""),
                "object": t.get("object", ""),
                "function": t.get("function", ""),
                "workflow_state": wf,
                "decision_outcome": outcome,
                "implementation_state": impl,
                "impl_commit": t.get("impl_commit", ""),
                "impl_verifier": t.get("impl_verifier", ""),
                "content": t.get("content") or "",
                "discussion": json.loads(t.get("discussion_json") or "[]"),
                "summary": (t.get("content") or "").split("\n\n")[0].replace("\n", " ")[:200]
            }

            legacy_status = t.get("decision_status", "")
            if outcome == "rejected" or (not outcome and "否决" in legacy_status and "非否决" not in legacy_status):
                item["rejection_reason"] = t.get("rejection_reason", "未记录具体否决原因")
                item["superseded_by"] = t.get("superseded_by", "")
                if include_rejected:
                    rejected_proposals.append(item)
            elif outcome in ["superseded", "deferred"]:
                # 被替代或已暂缓的议题绝不进入“当前有效决策 (必须遵守)” (R09)
                pass
            elif wf == "decided" and outcome in ["accepted", ""]:
                # 只有明确采纳的已定决策才属于强制遵守红线
                active_decisions.append(item)
                # 若尚未核验 (包括已实现但待核验 implemented)，进入待落实与待核验清单 (R09)
                if impl in ["not_started", "in_progress", "implemented"]:
                    pending_requirements.append(item)
            else:
                pending_requirements.append(item)

        return {
            "query": {
                "module": module or "all",
                "path_keyword": path_keyword or "",
                "topic_id": topic_id or "",
                "generated_at": datetime.datetime.now().isoformat()
            },
            "counts": {
                "total_matched": len(filtered),
                "active_decisions": len(active_decisions),
                "rejected_proposals": len(rejected_proposals),
                "pending_requirements": len(pending_requirements)
            },
            "active_decisions": active_decisions,
            "rejected_proposals": rejected_proposals if include_rejected else [],
            "pending_requirements": pending_requirements
        }

    def format_as_markdown(self, context_data: Dict[str, Any]) -> str:
        """将上下文格式化为适合作为 Agent System Prompt 或任务前置 Context 的 Markdown 规范"""
        q = context_data["query"]
        md = [
            "# 架构治理与决策约束台账 (Agent Context)",
            "",
            f"> **生成时间**：`{q['generated_at']}` | **检索模块**：`{q['module']}`",
            "> **说明**：在执行代码变更与架构建议前，必须严格遵守下列已拍板红线，禁止再次提议已被否决的方案。",
            "",
            "## 1. 当前有效决策 (必须遵守)",
            ""
        ]

        if not context_data["active_decisions"]:
            md.append("*暂无匹配的已定决策*")
            md.append("")
        else:
            for item in context_data["active_decisions"]:
                impl_info = f"实现状态: {item['implementation_state']}"
                if item["impl_commit"]:
                    impl_info += f" | 提交引用: `{item['impl_commit']}`"
                if item["impl_verifier"]:
                    impl_info += f" | 核验者: {item['impl_verifier']}"
                md.append(f"### [{item['id']}] {item['title']} (v{item['version']})")
                md.append(f"- **分类**：{item['object']} · {item['function']} | **状态**：{impl_info}")
                md.append(f"\n{item.get('content', item['summary'])}")
                for entry in item.get("discussion", []):
                    md.append(f"\n**{entry['key']}**\n\n{entry['val']}")
                md.append("")

        md.append("## 2. 明确否决方案与红线 (严禁重提)")
        md.append("")
        if not context_data["rejected_proposals"]:
            md.append("*暂无明确否决方案*")
            md.append("")
        else:
            for item in context_data["rejected_proposals"]:
                md.append(f"### ❌ [{item['id']}] {item['title']}")
                md.append(f"- **否决原因**：{item.get('rejection_reason', '用户或团队已明确否决')}")
                if item.get("superseded_by"):
                    md.append(f"- **替代方案**：请参考议题 `#{item['superseded_by']}`")
                md.append(item.get("content", ""))
                for entry in item.get("discussion", []):
                    md.append(f"\n**{entry['key']}**\n\n{entry['val']}")
                md.append("")

        md.append("## 3. 待落实与待核验清单")
        md.append("")
        if not context_data["pending_requirements"]:
            md.append("*暂无待落实要求*")
            md.append("")
        else:
            for item in context_data["pending_requirements"]:
                md.append(f"- **[{item['id']}] {item['title']}** (当前: `{item['workflow_state']}` / `{item['implementation_state']}`)")
                if item not in context_data["active_decisions"]:
                    md.append(item.get("content", ""))
                    for entry in item.get("discussion", []):
                        md.append(f"\n**{entry['key']}**\n\n{entry['val']}")
            md.append("")

        return "\n".join(md)

    def record_verification(
        self, topic_id: str, impl_commit: str, verifier: str,
        test_summary: str = "", mark_verified: bool = True,
        expected_version: Optional[int] = None, request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """All evidence writes use the same validated, transactional service path."""
        from core.decision_service import DecisionService
        service = DecisionService(self.config)
        service.db = self.db
        service.recovery = self.recovery
        return service.record_verification(
            topic_id, impl_commit, verifier, test_summary, mark_verified,
            expected_version=expected_version, request_id=request_id
        )
