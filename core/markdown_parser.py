# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Markdown Parser & Serializer
单议题独立 Markdown 文件解析器与 N 轮追加序列化器
支持 Frontmatter (schema_version: 2.0)、代码围栏精确匹配、正文注释与三级标题保护、多维状态提取
"""

import re
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


def is_fence_start(line: str) -> Optional[Tuple[str, int]]:
    """
    判断一行是否开启了代码围栏 (CommonMark 规范: 0-3 空格前导, 至少 3 个 ` 或 ~)。
    返回 (fence_char, fence_length) 或 None。
    """
    stripped_leading = line.lstrip(" ")
    leading_spaces = len(line) - len(stripped_leading)
    if leading_spaces > 3:
        return None
    if stripped_leading.startswith("```"):
        m = re.match(r"^`{3,}", stripped_leading)
        if m:
            return ("`", len(m.group(0)))
    elif stripped_leading.startswith("~~~"):
        m = re.match(r"^~{3,}", stripped_leading)
        if m:
            return ("~", len(m.group(0)))
    return None


def is_fence_close(line: str, open_char: str, open_len: int) -> bool:
    """
    判断一行是否闭合了当前代码围栏。
    闭合行必须以相同的字符开始，长度至少等于开启时的长度，且之后不能有除空格/制表符外的其他字符。
    """
    stripped_leading = line.lstrip(" ")
    leading_spaces = len(line) - len(stripped_leading)
    if leading_spaces > 3:
        return False
    pattern = rf"^{re.escape(open_char)}{{{open_len},}}[ \t]*$"
    return bool(re.match(pattern, stripped_leading))


class TopicMarkdownParser:
    @staticmethod
    def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
        """
        解析 YAML Frontmatter 元数据块。
        必须以独占一行的 --- 起始，并以独占一行的 --- 闭合。
        支持 JSON 编码值（包括换行与引号转义）、YAML 块标量 | 以及标准标量值。
        返回 (metadata_dict, remaining_body)
        """
        metadata: Dict[str, Any] = {}
        lines = text.splitlines(keepends=True)
        if not lines:
            return metadata, text

        # 检查首行是否是独占一行的 ---
        first_line = lines[0].strip()
        if first_line != "---":
            return metadata, text

        # 寻找闭合的独占一行的 ---
        close_idx = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                close_idx = i
                break

        if close_idx == -1:
            # 没有闭合的分隔符，视为没有 frontmatter
            return metadata, text

        front_lines = [l.rstrip("\r\n") for l in lines[1:close_idx]]
        remaining = "".join(lines[close_idx + 1:]).lstrip("\r\n")

        i = 0
        while i < len(front_lines):
            line = front_lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            if ":" in line:
                k, v = line.split(":", 1)
                key = k.strip()
                val = v.strip()

                # 支持 YAML 块标量 (| 或 >)
                if val in ("|", ">", "|-", ">-", "|+", ">+"):
                    block_lines = []
                    i += 1
                    while i < len(front_lines):
                        next_line = front_lines[i]
                        if next_line.startswith("  ") or next_line.startswith("\t"):
                            indent = 2 if next_line.startswith("  ") else 1
                            block_lines.append(next_line[indent:])
                            i += 1
                        elif not next_line.strip():
                            block_lines.append("")
                            i += 1
                        else:
                            break
                    metadata[key] = "\n".join(block_lines).strip("\n")
                    continue

                # 优先解析 JSON 转义字符串 (例如 json.dumps 产物)
                if val.startswith('"'):
                    try:
                        metadata[key] = json.loads(val)
                        i += 1
                        continue
                    except json.JSONDecodeError:
                        pass

                # 单引号字符串
                if val.startswith("'") and val.endswith("'") and len(val) >= 2:
                    metadata[key] = val[1:-1].replace("''", "'")
                    i += 1
                    continue

                # 布尔与数字转换
                if val.isdigit():
                    metadata[key] = int(val)
                elif val.lower() == "true":
                    metadata[key] = True
                elif val.lower() == "false":
                    metadata[key] = False
                else:
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    metadata[key] = val
                i += 1
            else:
                i += 1

        return metadata, remaining

    @classmethod
    def count_rounds(cls, file_path: Path) -> int:
        """极速统计单个 Markdown 文件中的讨论轮次数，具备完备代码围栏感知"""
        if not file_path.exists():
            return 1
        try:
            content = file_path.read_text(encoding="utf-8").replace("\r\n", "\n")
            open_char = None
            open_len = 0
            round_nums = []

            for line in content.splitlines():
                if open_char is not None:
                    if is_fence_close(line, open_char, open_len):
                        open_char = None
                        open_len = 0
                    continue

                fence_start = is_fence_start(line)
                if fence_start:
                    open_char, open_len = fence_start
                    continue

                stripped = line.strip()
                if stripped.startswith("###"):
                    m = re.search(r'###\s*(?:第\s*(\d+)\s*轮|Round\s*(\d+))', stripped, re.I)
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

        lines = body.splitlines()

        # 1. 提取标题（若 Frontmatter 未声明）：必须在代码围栏之外扫描
        if not title:
            open_char = None
            open_len = 0
            for line in lines:
                if open_char is not None:
                    if is_fence_close(line, open_char, open_len):
                        open_char = None
                        open_len = 0
                    continue
                fence_start = is_fence_start(line)
                if fence_start:
                    open_char, open_len = fence_start
                    continue
                if line.startswith("# ") and not line.startswith("## "):
                    title = line[2:].strip()
                    break
        if not title:
            title = topic_id

        # 2. 拆分“核心论述”与“历史讨论”（具有完备代码块感知）
        open_char = None
        open_len = 0
        split_idx = -1

        for i, line in enumerate(lines):
            if open_char is not None:
                if is_fence_close(line, open_char, open_len):
                    open_char = None
                    open_len = 0
                continue

            fence_start = is_fence_start(line)
            if fence_start:
                open_char, open_len = fence_start
                continue

            stripped_line = line.strip()
            if re.match(r"^##\s+(?:历史讨论与决策记录|discussion\s+history(?:\s*(?:and|&)\s*decisions?)?)\s*$", stripped_line, re.IGNORECASE):
                split_idx = i
                break

        if split_idx != -1:
            core_part = "\n".join(lines[:split_idx])
            history_part = "\n".join(lines[split_idx + 1:])
        else:
            core_part = body
            history_part = ""

        # 3. 提炼核心内容：必须有代码块保护，代码块内部的 '# comment' 绝不当作标题剔除
        core_lines = []
        open_char = None
        open_len = 0
        skip_header = True

        for line in core_part.splitlines():
            if open_char is not None:
                # 在代码块内，完全保留所有行
                core_lines.append(line)
                if is_fence_close(line, open_char, open_len):
                    open_char = None
                    open_len = 0
                continue

            fence_start = is_fence_start(line)
            if fence_start:
                open_char, open_len = fence_start
                core_lines.append(line)
                continue

            s = line.strip()
            # 过滤模板外框行
            if s.startswith("# ") and not s.startswith("## "):
                continue
            if s.startswith("> **锚点") or s.startswith("> **生命周期"):
                continue
            if "## 核心论述与现实依据" in s:
                skip_header = False
                continue
            core_lines.append(line)

        core_content = "\n".join(core_lines).strip()

        # 4. 解析历史轮次（严密的代码块安全隔离与仅匹配真实轮次标题）
        rounds: List[Dict[str, Any]] = []
        if history_part.strip():
            hist_lines = history_part.splitlines()
            current_round_title = None
            current_round_lines: List[str] = []
            open_char = None
            open_len = 0

            for line in hist_lines:
                if open_char is not None:
                    if is_fence_close(line, open_char, open_len):
                        open_char = None
                        open_len = 0
                    if current_round_title is not None:
                        current_round_lines.append(line)
                    continue

                fence_start = is_fence_start(line)
                if fence_start:
                    open_char, open_len = fence_start
                    if current_round_title is not None:
                        current_round_lines.append(line)
                    continue

                s = line.strip()
                # 只有符合轮次标题模式（例如 '### 第 1 轮...' 或 '### Round 1...'）才作为新轮次分界
                # 普通的 ### Subheading （如用户意见内的 ### Implementation notes 或 ### Round 2 retry policy）保留在轮次内部 (T06)
                if re.match(r"^###\s+(?:第\s*\d+\s*轮.*|Round\s*\d+\s*(?:[:(]|[-–—]|\bdecisions?\b|\brequirements?\b|\bdiscussion\b|\brecord\b|\bnotes?\b|$).*)", s, re.I):
                    if current_round_title is not None:
                        rounds.append(cls._build_round_dict(current_round_title, current_round_lines))
                    # 去掉前导 '### '
                    current_round_title = re.sub(r"^###\s+", "", s).strip()
                    current_round_lines = []
                else:
                    if current_round_title is not None:
                        current_round_lines.append(line)

            if current_round_title is not None:
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
            # 从旧版引用块提取
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
        """提炼轮次内容并分离用户原话与答复，具备完备代码围栏感知"""
        body = "\n".join(lines).strip()
        user_lines: List[str] = []
        agent_lines: List[str] = []
        commit_lines: List[str] = []

        current_target = None  # "user", "agent", "commit"
        open_char = None
        open_len = 0

        for line in lines:
            if open_char is not None:
                if is_fence_close(line, open_char, open_len):
                    open_char = None
                    open_len = 0
                if current_target == "user":
                    user_lines.append(line)
                elif current_target == "agent":
                    agent_lines.append(line)
                elif current_target == "commit":
                    commit_lines.append(line)
                continue

            fence_start = is_fence_start(line)
            if fence_start:
                open_char, open_len = fence_start
                if current_target == "user":
                    user_lines.append(line)
                elif current_target == "agent":
                    agent_lines.append(line)
                elif current_target == "commit":
                    commit_lines.append(line)
                continue

            # 围栏之外检测字段标头
            # 必须精准匹配协议支持的完整字段标头，严禁将包含标头单词的普通列表项（如 - **Team reply SLA**: 或 - **User opinion survey**:）误判为协议字段 (R1, N01, N03)
            bullet_m = re.match(r"^-\s+\*\*(.*?)\*\*[：:]?[ \t]*(.*)", line)
            if bullet_m:
                label_text = bullet_m.group(1).strip()
                rest_text = bullet_m.group(2).strip()

                user_label_m = re.match(
                    r"^(?:💡\s*)?(?:用户(?:意见)?|user\s*opinion)(?:\s*[（(]\s*(?:最新原话|latest\s*(?:verbatim|opinion|requirements?))\s*[）)])?$",
                    label_text,
                    re.IGNORECASE
                )
                agent_label_m = re.match(
                    r"^(?:🤖\s*)?(?:团队答复|团队回复|落实说明|答复|落实|(?:team|agent)\s*reply)(?:\s*[（(]\s*(?:落实说明|implementation\s*(?:details|notes?)|schedule)\s*[）)])?$",
                    label_text,
                    re.IGNORECASE
                )
                commit_label_m = re.match(
                    r"^(?:变更说明|change\s*summary)(?:\s*[（(]\s*(?:简要|变更说明|summary)\s*[）)])?$",
                    label_text,
                    re.IGNORECASE
                )

                if user_label_m:
                    current_target = "user"
                    if rest_text:
                        user_lines.append(rest_text)
                    continue
                elif agent_label_m:
                    current_target = "agent"
                    if rest_text:
                        agent_lines.append(rest_text)
                    continue
                elif commit_label_m:
                    current_target = "commit"
                    if rest_text:
                        commit_lines.append(rest_text)
                    continue

            if current_target == "user":
                user_lines.append(line)
            elif current_target == "agent":
                agent_lines.append(line)
            elif current_target == "commit":
                commit_lines.append(line)

        return {
            "title": title,
            "content": body,
            "user_opinion": "\n".join(user_lines).strip(),
            "agent_reply": "\n".join(agent_lines).strip(),
            "commit_message": "\n".join(commit_lines).strip()
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
        严密保护代码围栏与用户多行原话，追加第 n 轮讨论记录。
        所有字符串字段采用 JSON 规范安全转义，杜绝换行、引号与 --- 冲撞。
        """
        # 1. 结构化 YAML Frontmatter
        front = [
            "---",
            'schema_version: "2.0"',
            f'id: {json.dumps(topic_id, ensure_ascii=False)}',
            f'title: {json.dumps(title, ensure_ascii=False)}',
            f'version: {version}',
            f'section: {json.dumps(section, ensure_ascii=False)}',
            f'object: {json.dumps(obj, ensure_ascii=False)}',
            f'function: {json.dumps(func, ensure_ascii=False)}',
            f'priority: {json.dumps(priority, ensure_ascii=False)}',
            f'workflow_state: {json.dumps(workflow_state, ensure_ascii=False)}',
            f'decision_outcome: {json.dumps(decision_outcome, ensure_ascii=False)}',
            f'rejection_reason: {json.dumps(rejection_reason, ensure_ascii=False)}',
            f'superseded_by: {json.dumps(superseded_by, ensure_ascii=False)}',
            f'implementation_state: {json.dumps(implementation_state, ensure_ascii=False)}',
            f'impl_commit: {json.dumps(impl_commit, ensure_ascii=False)}',
            f'impl_verifier: {json.dumps(impl_verifier, ensure_ascii=False)}',
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
