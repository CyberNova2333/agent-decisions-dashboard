# -*- coding: utf-8 -*-
"""
Tests for TopicMarkdownParser: Frontmatter 2.0, Code Fence Isolation, and Multiline Quotes
"""

import unittest
from pathlib import Path
from core.markdown_parser import TopicMarkdownParser

class TestMarkdownParser(unittest.TestCase):
    def setUp(self):
        self.parser = TopicMarkdownParser()

    def test_legacy_format_parsing(self):
        legacy_md = """# 系统架构选型：状态机轻量内核

> **锚点 ID**：`adr-001` | **所属对象**：`架构设计` | **业务功能**：`核心拓扑`
> **生命周期**：`🟢 已决策` | **决策状态**：`已定` | **实现现状**：`已实现` | **优先级**：`高`

## 核心论述与现实依据

这是核心论述文本。

## 历史讨论与决策记录

### 第 1 轮定案与要求 (2026-10-05 10:00)
- **变更说明**：初始化架构决策
- **💡 用户意见（最新原话）**：坚决采用轻量单文件方案。
- **🤖 团队答复（落实说明）**：遵命，已落实。
"""
        parsed = self.parser.parse_markdown_text(legacy_md, default_id="adr-001")
        self.assertEqual(parsed["id"], "adr-001")
        self.assertEqual(parsed["title"], "系统架构选型：状态机轻量内核")
        self.assertEqual(parsed["workflow_state"], "decided")
        self.assertEqual(parsed["object"], "架构设计")
        self.assertEqual(parsed["function"], "核心拓扑")
        self.assertEqual(len(parsed["rounds"]), 1)
        self.assertIn("坚决采用轻量单文件方案", parsed["rounds"][0]["user_opinion"])

    def test_frontmatter_2_0_parsing_and_serialization(self):
        serialized = self.parser.serialize_markdown(
            topic_id="adr-002",
            title="存储层规范",
            lifecycle_badge="🟢 已决策",
            decision_status="已定",
            impl_status="已实现",
            priority="紧急",
            obj="存储系统",
            func="数据库拓扑",
            core_content="使用 SQLite 作为高性能派生索引。",
            existing_rounds=[],
            new_round={
                "commit_message": "首次定案",
                "user_opinion": "不要用复杂的分布式数据库，就用本地 SQLite 文件。",
                "agent_reply": "已采用 SQLite 规范。"
            },
            workflow_state="decided",
            decision_outcome="accepted",
            implementation_state="implemented",
            impl_commit="deadbeef",
            version=1,
            section="数据持久化"
        )

        parsed = self.parser.parse_markdown_text(serialized, default_id="adr-002")
        self.assertEqual(parsed["id"], "adr-002")
        self.assertEqual(parsed["schema_version"], "2.0")
        self.assertEqual(parsed["title"], "存储层规范")
        self.assertEqual(parsed["workflow_state"], "decided")
        self.assertEqual(parsed["decision_outcome"], "accepted")
        self.assertEqual(parsed["implementation_state"], "implemented")
        self.assertEqual(parsed["impl_commit"], "deadbeef")
        self.assertEqual(parsed["version"], 1)
        self.assertEqual(len(parsed["rounds"]), 1)

    def test_code_fence_isolation_no_false_rounds(self):
        """
        P2-G: 代码围栏感知测试：
        用户原话或正文包含了带有 ### 的代码块，严禁被误判为历史讨论轮次分界！
        """
        complex_md = """---
schema_version: "2.0"
id: "adr-code"
title: "代码块测试"
---

# 代码块测试

## 核心论述与现实依据

正文中的代码块：
```markdown
### 假轮次标题
- **用户意见**：假意见
```

## 历史讨论与决策记录

### 第 1 轮定案与要求 (2026-10-05 12:00)
- **变更说明**：真实轮次
- **💡 用户意见（最新原话）**：
```python
def foo():
    # ### 第 99 轮伪造标题
    return True
```
- **🤖 团队答复（落实说明）**：收到代码。
"""
        parsed = self.parser.parse_markdown_text(complex_md, default_id="adr-code")
        # 应该只有 1 个真实的轮次，围栏内部的 ### 不得成为新轮次！
        self.assertEqual(len(parsed["rounds"]), 1)
        self.assertEqual(parsed["rounds"][0]["title"], "第 1 轮定案与要求 (2026-10-05 12:00)")
        self.assertIn("def foo():", parsed["rounds"][0]["content"])

    def test_crlf_normalization(self):
        """测试 Windows CRLF 换行符无损归一化"""
        crlf_md = "# 标题\r\n\r\n## 核心论述与现实依据\r\n\r\n正文\r\n\r\n## 历史讨论与决策记录\r\n\r\n### 第 1 轮\r\n- **变更说明**：测试\r\n"
        parsed = self.parser.parse_markdown_text(crlf_md, default_id="crlf-test")
        self.assertEqual(parsed["title"], "标题")
        self.assertEqual(len(parsed["rounds"]), 1)

if __name__ == "__main__":
    unittest.main()
