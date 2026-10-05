# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Markdown Parser & Serializer
单议题独立 Markdown 文件解析器与 N 轮追加序列化器
支持 Frontmatter (schema_version: 2.0)、代码围栏容错与正交多维状态提取
"""

import re
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

class TopicMarkdownParser:
    @staticmethod
    def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
        """
        解析 YAML Frontmatter 元数据块
        返回 (metadata_dict, remaining_body)
        """
        metadata: Dict[str, Any] = {}
        if not text.startswith("---"):
            return metadata, text

        parts = text.split("---", 2)
        if len(parts) < 3:
            return metadata, text

        front_raw = parts[1]
        remaining = parts[2].lstrip("\r\n")

        for line in front_raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                key = k.strip()
                val = v.strip()
                # 剥除可能的外层引号
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                # 尝试类型转换
                if val.isdigit():
                    metadata[key] = int(val)
                elif val.lower() == "true":
                    metadata[key] = True
                elif val.lower() == "false":
                    metadata[key] = False
                else:
                    metadata[key] = val

        return metadata, remaining

    @classmethod
    def count_rounds(cls, file_path: Path) -> int:
        """极速统计单个 Markdown 文件中的讨论轮次数，具备代码围栏感知"""
        if not file_path.exists():
            return 1
        try:
            content = file_path.read_text(encoding="utf-8").replace("\r\n", "\n")
            in_code = False
            round_nums = []
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("```") or stripped.startswith("~~~"):
                    in_code = not in_code
                    continue
                if not in_code and stripped.startswith("###"):
                    m = re.search(r'第\s*(\d+)\s*轮|Round\s*(\d+)', stripped, re.I)
                    if m:
                        val = m.group(1) or m.group(2)
                        round_nums.append(int(val))
            if round_nums:
                return max(round_nums)
        except Exception:
            pass
        return 0

    @classmethod
    def parse_markdown_file(cls, file_path: Path) -> Optional[Dict[str, Any]]:
        """读取并结构化解析单个议题 Markdown 文件"""
        if not file_path.exists():
            return None

        try:
            raw_text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw_text = file_path.read_text(encoding="gbk", errors="replace")

        return cls.parse_markdown_text(raw_text, default_id=file_path.stem)

    @classmethod
    def parse_markdown_text(cls, raw_text: str, default_id: str = "") -> Dict[str, Any]:
        """从字符串解析议题，支持 Frontmatter 2.0 规范与旧版 Markdown 兼容解析"""
        text = raw_text.replace("\r\n", "\n")
        meta, body = cls._parse_frontmatter(text)

        topic_id = str(meta.get("id", "")).strip() or default_id
        title = str(meta.get("title", "")).strip()

        # 提取标题（若 Frontmatter 未声明）
        if not title:
            title_match = re.search(r'(?m)^#\s+([^\n]+)', body)
            title = title_match.group(1).strip() if title_match else topic_id

        # 拆分 核心论述 与 历史讨论（具有代码块感知）
        lines = body.splitlines()
        in_code = False
        split_idx = -1

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_code = not in_code
                continue
            if not in_code and "## 历史讨论与决策记录" in stripped:
                split_idx = i
                break

        if split_idx != -1:
            core_part = "\n".join(lines[:split_idx])
            history_part = "\n".join(lines[split_idx + 1:])
        else:
            core_part = body
            history_part = ""

        # 提炼核心内容
        core_lines = []
        skip_header = True
        for line in core_part.splitlines():
            s = line.strip()
            if s.startswith("# ") or s.startswith("> **锚点") or s.startswith("> **生命周期"):
                continue
            if "## 核心论述与现实依据" in s:
                skip_header = False
                continue
            core_lines.append(line)
        core_content = "\n".join(core_lines).strip()

        # 解析历史轮次（带代码块安全隔离）
        rounds: List[Dict[str, Any]] = []
        if history_part.strip():
            hist_lines = history_part.splitlines()
            current_round_title = None
            current_round_lines: List[str] = []
            in_hist_code = False

            for line in hist_lines:
                s = line.strip()
                if s.startswith("```") or s.startswith("~~~"):
                    in_hist_code = not in_hist_code
                    if current_round_title:
                        current_round_lines.append(line)
                    continue

                if not in_hist_code and s.startswith("### "):
                    if current_round_title:
                        rounds.append(cls._build_round_dict(current_round_title, current_round_lines))
                    current_round_title = s[4:].strip()
                    current_round_lines = []
                else:
                    if current_round_title:
                        current_round_lines.append(line)

            if current_round_title:
                rounds.append(cls._build_round_dict(current_round_title, current_round_lines))

        # 旧版引用块补充提取（若 Frontmatter 缺省）
        section = meta.get("section", "未分类")
        obj = meta.get("object", "通用系统")
        func = meta.get("function", "核心规范")
        wf_state = meta.get("workflow_state") or meta.get("lifecycle_status", "discussing")
        dec_status = meta.get("decision_status", "已定")
        impl_state = meta.get("implementation_state") or meta.get("impl_status", "not_started")
        priority = meta.get("priority", "普通")
        version = meta.get("version", 1)

        if not meta:
            # 从旧版引用块精准提取
            for key, attr in [
                ("所属对象", "object"),
                ("业务功能", "function"),
                ("决策状态", "decision_status"),
                ("实现现状", "impl_status"),
                ("优先级", "priority")
            ]:
                m = re.search(r'\*\*' + key + r'\*\*[：:]\s*`?([^`|\n]+)`?', core_part)
                if m:
                    val = m.group(1).strip()
                    if attr == "object": obj = val
                    elif attr == "function": func = val
                    elif attr == "decision_status": dec_status = val
                    elif attr == "impl_status": impl_state = val
                    elif attr == "priority": priority = val

            lc_m = re.search(r'\*\*生命周期\*\*[：:]\s*`?([^`|\n]+)`?', core_part)
            if lc_m:
                lc_text = lc_m.group(1).strip()
                if "已决策" in lc_text: wf_state = "decided"
                elif "待决策" in lc_text: wf_state = "pending"
                else: wf_state = "discussing"

        return {
            "id": topic_id,
            "title": title,
            "schema_version": meta.get("schema_version", "2.0"),
            "section": section,
            "object": obj,
            "function": func,
            "workflow_state": wf_state,
            "decision_outcome": meta.get("decision_outcome", ""),
            "rejection_reason": meta.get("rejection_reason", ""),
            "superseded_by": meta.get("superseded_by", ""),
            "implementation_state": impl_state,
            "impl_commit": meta.get("impl_commit", ""),
            "impl_verifier": meta.get("impl_verifier", ""),
            "priority": priority,
            "version": version,
            "raw_text": raw_text,
            "core_content": core_content,
            "rounds": rounds
        }

    @staticmethod
    def _build_round_dict(title: str, lines: List[str]) -> Dict[str, Any]:
        """提炼轮次内容并分离用户原话与答复"""
        body = "\n".join(lines).strip()
        user_op = ""
        agent_rep = ""
        commit_msg = ""

        # 提取字段
        user_m = re.search(r'(?m)^-\s+\*\*.*?用户.*?\*\*[：:]?[ \t]*(.+?)(?=\n- \*\*|\Z)', body, re.S)
        if user_m: user_op = user_m.group(1).strip()

        agent_m = re.search(r'(?m)^-\s+\*\*.*?(?:答复|落实).*?\*\*[：:]?[ \t]*(.+?)(?=\n- \*\*|\Z)', body, re.S)
        if agent_m: agent_rep = agent_m.group(1).strip()

        commit_m = re.search(r'(?m)^-\s+\*\*.*?变更说明.*?\*\*[：:]?[ \t]*(.+?)(?=\n- \*\*|\Z)', body, re.S)
        if commit_m: commit_msg = commit_m.group(1).strip()

        return {
            "title": title,
            "content": body,
            "user_opinion": user_op,
            "agent_reply": agent_rep,
            "commit_message": commit_msg
        }

    @staticmethod
    def serialize_markdown(
        topic_id: str,
        title: str,
        lifecycle_badge: str,
        decision_status: str,
        impl_status: str,
        priority: str,
        obj: str,
        func: str,
        core_content: str,
        existing_rounds: List[Dict[str, Any]],
        new_round: Optional[Dict[str, Any]] = None,
        workflow_state: str = "discussing",
        decision_outcome: str = "",
        rejection_reason: str = "",
        superseded_by: str = "",
        implementation_state: str = "not_started",
        impl_commit: str = "",
        impl_verifier: str = "",
        version: int = 1,
        section: str = "未分类"
    ) -> str:
        """
        序列化生成符合规范的单议题 Markdown：
        采用 Frontmatter (schema_version: 2.0) 机器元数据 + 人类友好展示双重结构，
        严密保护代码围栏与用户多行原话，追加第 n 轮讨论记录
        """
        # 1. 结构化 YAML Frontmatter
        front = [
            "---",
            'schema_version: "2.0"',
            f'id: "{topic_id}"',
            f'title: "{title}"',
            f'version: {version}',
            f'section: "{section}"',
            f'object: "{obj}"',
            f'function: "{func}"',
            f'priority: "{priority}"',
            f'workflow_state: "{workflow_state}"',
            f'decision_outcome: "{decision_outcome}"',
            f'rejection_reason: "{rejection_reason}"',
            f'superseded_by: "{superseded_by}"',
            f'implementation_state: "{implementation_state}"',
            f'impl_commit: "{impl_commit}"',
            f'impl_verifier: "{impl_verifier}"',
            "---",
            ""
        ]

        # 2. 人类可读标头与引用标头
        header = [
            f"# {title}",
            "",
            f"> **锚点 ID**：`{topic_id}` | **所属对象**：`{obj}` | **业务功能**：`{func}`",
            f"> **生命周期**：`{lifecycle_badge}` | **决策状态**：`{decision_status}` | **实现现状**：`{impl_status}` | **优先级**：`{priority}`",
            "",
            "## 核心论述与现实依据",
            "",
            core_content.strip(),
            "",
            "## 历史讨论与决策记录",
            ""
        ]

        # 3. 既有历史轮次
        rounds_md = []
        for r in existing_rounds:
            rounds_md.append(f"### {r['title']}")
            rounds_md.append(r["content"].strip())
            rounds_md.append("")

        # 4. 追加新一轮讨论
        if new_round:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            round_num = len(existing_rounds) + 1
            rounds_md.append(f"### 第 {round_num} 轮定案与要求 ({now_str})")
            if new_round.get("commit_message"):
                rounds_md.append(f"- **变更说明**：{new_round['commit_message'].strip()}")
            if new_round.get("user_opinion"):
                rounds_md.append(f"- **💡 用户意见（最新原话）**：\n\n{new_round['user_opinion'].strip()}\n")
            if new_round.get("agent_reply"):
                rounds_md.append(f"- **🤖 团队答复（落实说明）**：\n\n{new_round['agent_reply'].strip()}\n")
            rounds_md.append("")

        full_doc = "\n".join(front) + "\n".join(header) + "\n".join(rounds_md)
        return full_doc.strip() + "\n"
