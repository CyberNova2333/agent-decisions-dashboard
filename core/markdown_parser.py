# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Markdown Parser & Serializer
单议题独立 Markdown 文件解析器与 N 轮追加序列化器
"""

import re
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

class TopicMarkdownParser:
    @staticmethod
    def count_rounds(file_path: Path) -> int:
        """极速统计单个 Markdown 文件中的讨论轮次数"""
        if not file_path.exists():
            return 1
        try:
            content = file_path.read_text(encoding="utf-8")
            rounds = re.findall(r'(?m)^###\s+第\s+(\d+)\s+轮', content)
            if rounds:
                return max([int(x) for x in rounds])
        except Exception:
            pass
        return 1

    @staticmethod
    def parse_markdown_file(file_path: Path) -> Optional[Dict[str, Any]]:
        """读取并结构化解析单个议题 Markdown 文件"""
        if not file_path.exists():
            return None

        raw_text = file_path.read_text(encoding="utf-8")
        topic_id = file_path.stem

        # 提取标题
        title_match = re.search(r'(?m)^#\s+([^\n]+)', raw_text)
        title = title_match.group(1).strip() if title_match else topic_id

        # 拆分 核心论述 与 历史讨论
        core_content = ""
        history_section = ""

        if "## 历史讨论与决策记录" in raw_text:
            parts = raw_text.split("## 历史讨论与决策记录", 1)
            core_part = parts[0]
            history_section = parts[1].strip()

            if "## 核心论述与现实依据" in core_part:
                core_content = core_part.split("## 核心论述与现实依据", 1)[1].strip()
            else:
                core_content = core_part.strip()
        else:
            core_content = raw_text.strip()

        # 解析各轮次讨论
        rounds: List[Dict[str, str]] = []
        if history_section:
            round_blocks = re.split(r'\n(?=### 第 \d+ 轮)', "\n" + history_section)
            for rb in round_blocks:
                rb = rb.strip()
                if not rb or not rb.startswith("###"):
                    continue
                lines = rb.splitlines()
                round_title = lines[0].replace("###", "").strip()
                body = "\n".join(lines[1:]).strip()
                rounds.append({
                    "title": round_title,
                    "content": body
                })

        return {
            "id": topic_id,
            "title": title,
            "raw_text": raw_text,
            "core_content": core_content,
            "rounds": rounds
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
        existing_rounds: List[Dict[str, str]],
        new_round: Optional[Dict[str, str]] = None
    ) -> str:
        """
        序列化生成符合规范的单议题 Markdown：
        保留所有历史轮次，不覆盖对方意见，追加第 n 轮决策记录
        """
        md_lines = [
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

        # 写入既有历史轮次
        for r in existing_rounds:
            md_lines.append(f"### {r['title']}")
            md_lines.append(r["content"].strip())
            md_lines.append("")

        # 追加新一轮讨论
        if new_round:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            round_num = len(existing_rounds) + 1
            md_lines.append(f"### 第 {round_num} 轮定案与要求 ({now_str})")
            if new_round.get("commit_message"):
                md_lines.append(f"- **变更说明**：{new_round['commit_message'].strip()}")
            if new_round.get("user_opinion"):
                md_lines.append(f"- **💡 用户意见（最新原话）**：{new_round['user_opinion'].strip()}")
            if new_round.get("agent_reply"):
                md_lines.append(f"- **🤖 团队答复（落实说明）**：{new_round['agent_reply'].strip()}")
            md_lines.append("")

        return "\n".join(md_lines).strip() + "\n"
