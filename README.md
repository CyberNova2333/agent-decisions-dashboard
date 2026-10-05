# Agent Decisions Dashboard ⚖️

> **通用 AI Agent 结对编程架构决策台账与 Git 自动化治理看板**  
> *Human-Agent Collaborative Architecture Decision Ledger & Automated Governance Dashboard*

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://python.org)
[![Zero Dependency](https://img.shields.io/badge/Dependencies-Zero%20(Standard%20Lib)-orange.svg)]()
[![Tests: Passing](https://img.shields.io/badge/Tests-19%20Passing-brightgreen.svg)]()

在人类与 AI 智能体（Agent）进行长程、复杂的工程研发与协同编码时，传统的大文档容易发生**“历史结论被冲刷覆盖”、“多轮答复无法精确定位追溯”、“AI 重复提出已被明确否决的旧提案”、“代码已拍板但无法区分实现与决策”**等痛点。

`agent-decisions-dashboard` 是一套轻量、本地优先且具备严密契约的架构决策台账系统。它将单议题 Markdown、多轮原话保留、正交生命周期流转、SQLite 元数据索引、暂存区保护的 Git 语义化提交以及面向 Agent 的只读上下文导出融为一体，为 AI 辅助编程提供严谨的治理红线与审计基线。

---

## 🏛️ 系统架构与职责边界

系统由六大核心模块协同运作，职责边界清晰解耦：

```mermaid
flowchart TD
    subgraph UI["现代化前端看板 (Web SPA / app.js)"]
        CARD["卡片流 &amp; 正交三态筛选<br/>(工作流 / 决策结论 / 实现状态)"]
        MODAL["决策录入 &amp; 冲突保护弹窗<br/>(保留草稿 / 乐观并发锁)"]
        DRAWER["时间机器面板<br/>(单议题精准回溯 / 全库重置)"]
        PROMPT["Agent Context 导出弹窗<br/>(一键复制治理约束 Prompt)"]
    end

    subgraph Service["业务协调层 (core/decision_service.py)"]
        SVC["DecisionService<br/>- 幂等校验 (request_id)<br/>- 乐观锁核验 (expected_version)<br/>- 路径穿越防御<br/>- 多阶段保存状态机"]
    end

    subgraph CoreModules["核心引擎模块"]
        SERVER["HTTP 服务层 (core/server.py)<br/>标准库 http.server / 10MB 限流 / 本地回环"]
        PARSER["Markdown 解析器 (core/markdown_parser.py)<br/>Frontmatter 2.0 / 代码围栏隔离 / 原话保留"]
        DB["数据库引擎 (core/db.py)<br/>SQLite 结构化存储 / 快照链 / Backup API"]
        GIT["Git 提交引擎 (core/git_engine.py)<br/>暂存区保护 / 隔离提交 / Co-Author 附加"]
        RECOVERY["一致性恢复引擎 (core/recovery.py)<br/>Markdown-as-Source 索引重建 / 一致性检测"]
        AGENT_CTX["Agent 上下文引擎 (core/agent_context.py)<br/>有效决策 / 否决红线分离 / 实现证据绑定"]
    end

    subgraph Storage["持久化与权威事实源"]
        MD_FILES["decisions/&lt;id&gt;.md (权威事实源)"]
        SQLITE_DB["decisions.db (高性能派生索引与快照链)"]
        META_JSON["decisions/metadata.json (派生导出物)"]
        GIT_REPO[".git 版本库历史"]
    end

    UI <-->|REST API| SERVER
    SERVER --> SVC
    SVC --> PARSER
    SVC --> DB
    SVC --> GIT
    SVC --> RECOVERY
    SERVER --> AGENT_CTX
    AGENT_CTX --> DB

    PARSER <--> MD_FILES
    DB <--> SQLITE_DB
    RECOVERY --> META_JSON
    GIT --> GIT_REPO
```

---

## 🛡️ 核心治理机制与安全契约

### 1. 明确唯一事实源与索引双向重建 (P1-A)
- **以 Markdown 文件为权威事实源**：每个 `decisions/<id>.md` 记录完整的机器元数据、论述正文与全部历史讨论轮次。
- **SQLite 作为高性能派生索引与时间旅行快照**：支持毫秒级冷启动与复杂多维查询。
- **派生导出物**：`metadata.json` 定位为只读衍生文件，随时由权威数据生成，杜绝维护三套独立写入口。
- 提供显式重建命令：`python -m core.server --rebuild-index` 可在数据库损坏或新克隆仓库时以 Markdown 为基准秒级全量重建。

### 2. Git 暂存区隔离保护 (P1-B)
- **严禁意外夹带用户代码**：自动提交前自动执行 `git diff --cached --name-only` 扫描暂存区。
- **受控隔离提交**：若发现暂存区包含非本次台账操作的其他工程代码（例如用户正在编辑的代码文件），系统将**自动安全跳过 Git 提交**并保留已落盘的 Markdown 与 SQLite 数据，绝对不污染用户暂存区，也不执行任何危险的 `reset` 或 `stash` 操作。

### 3. 清晰的回滚边界与单议题精准回溯 (P1-C)
- **单议题历史精准回退**：默认支持 `/api/topic/:id/restore`，从历史快照中仅提取指定议题的状态并恢复，完全不波及其他议题的正常演进，并以 `action_type="TOPIC_RESTORE"` 生成新的审计版本，原历史完整保留。
- **全库快照重置**：`/api/rollback` 同步覆写 SQLite 数据库与磁盘对应的 Markdown 文件，杜绝数据库与文件脱节。

### 4. 并发乐观锁与幂等性防重放 (P1-D)
- **版本乐观锁**：每次写入请求携带读取时的 `expected_version`。若议题已被其他页面或 Agent 更改，服务端返回 `409 Conflict`。
- **草稿无损保留**：前端在并发冲突时弹出明确横幅，完整保留用户在输入框中填写的草稿，避免静默覆盖。
- **幂等性保障**：支持客户端携带 `X-Request-ID`。相同请求数据重试时直接重放原结果，避免产生多余轮次；相同 ID 携带不同内容时明确报错。

### 5. 正交状态模型与否决红线约束 (P2-E)
将复杂的业务生命周期拆解为正交三维空间：
- **工作流状态 (`workflow_state`)**：`pending`（待决策）| `discussing`（待讨论）| `decided`（已决策）
- **决策结论 (`decision_outcome`)**：`accepted`（已采纳）| `rejected`（明确否决）| `deferred`（推迟）| `superseded`（已被替代）
- **实现状态 (`implementation_state`)**：`not_started`（未开始）| `in_progress`（进行中）| `implemented`（已实现）| `verified`（已核验）
- **❌ 明确否决方案红线**：被否决方案同样是重要资产。系统强制保存否决原因与重新讨论前提，并在卡片与 Agent Prompt 中重点标红，防止 Agent 反复重提被否决的设计。
- **代码实现证据核验**：通过 `/api/topic/:id/verify` 绑定实际工程提交 Hash、核验人与测试报告，分清“决策提交”与“代码实现提交”。

### 6. 面向 Agent 的治理上下文导出 (P2-F)
- 提供 `/api/agent/context?module=...&format=markdown` 接口。
- 精准按模块输出**有效决策必须遵守清单**、**明确否决方案红线清单**与**待落实待核验清单**，可一键复制并注入 Agent System Prompt 或任务前置上下文。

### 7. Frontmatter 2.0 规范与代码围栏容错 (P2-G)
- 采用 `schema_version: "2.0"` YAML Frontmatter 规范，分离机器属性与人类阅读展示。
- 解析器具备**代码块（```）安全感知**，即使用户原话或正文中包含带有 `###`、标题符号或换行符的代码，也绝对不会破坏轮次解析。
- 原生支持 Windows CRLF 与 Linux LF 换行符无损互转。

---

## 🚀 快速上手 (Quick Start)

### 1. 运行环境要求
- Python 3.9 及以上
- Git 2.0 及以上
- **零外部第三方依赖**（纯标准库实现）

### 2. 启动服务
- **Windows 用户**：双击运行 [`start_dashboard.bat`](./start_dashboard.bat)
- **Linux / macOS 用户**：
  ```bash
  chmod +x start_dashboard.sh
  ./start_dashboard.sh
  ```
- **命令行启动**：
  ```bash
  python -m core.server --port 8765
  ```

访问看板：**`http://127.0.0.1:8765`**。

### 3. CLI 维护工具命令
```bash
# 检查 Markdown 文件、SQLite 索引与 metadata.json 的一致性
python -m core.server --check-consistency

# 以 decisions/*.md 为权威事实源全量重建数据库索引
python -m core.server --rebuild-index

# 按模块导出供 Agent 注入的 Prompt Markdown 治理约束
python -m core.server --export-agent-context "核心架构"
```

---

## 🔌 RESTful API 规范

| 接口路径 | 方法 | 说明 |
|---|---|---|
| `/api/config` | `GET` | 获取当前看板项目配置 |
| `/api/status` | `GET` | 获取服务运行状态、HEAD Hash 与存储一致性报告 |
| `/api/topics` | `GET` | **核心第一阶段**：毫秒级加载所有议题元数据列表 |
| `/api/topic/:id` | `GET` | **核心第二阶段**：按需异步读取解析单个议题 Markdown 正文与历史轮次 |
| `/api/topic/:id/save` | `POST` | 保存决策：乐观锁核验 -> 写 Markdown -> 更新 DB -> 导出 JSON -> 暂存区保护提交 -> 快照归档 |
| `/api/topic/create` | `POST` | 安全创建全新议题（校验 ID 防路径穿越） |
| `/api/topic/:id/restore` | `POST` | **单议题针对性回溯**：从指定快照恢复该议题，不影响其他议题 |
| `/api/topic/:id/verify` | `POST` | **实现证据核验绑定**：关联代码实现 Commit Hash、核验人与测试说明 |
| `/api/agent/context` | `GET` | 面向 Agent 导出只读决策与否决红线约束 (`?format=markdown|json`) |
| `/api/recovery/check` | `GET` | 检查三态存储一致性报告 |
| `/api/recovery/rebuild` | `POST` | 从 Markdown 文件全量重建 SQLite 索引 |
| `/api/backup` | `POST` | 使用 SQLite Online Backup API 执行无阻塞热备份 |
| `/api/rollback` | `POST` | 全库快照重置（同步写回 Markdown 与数据库） |
| `/api/git/log` | `GET` | 查询 Git 提交记录与 Revision 快照链 |

---

## 📄 单议题 Markdown 格式标准 (`schema_version: "2.0"`)

位于 `decisions/<id>.md` 的议题文件结构：

````markdown
---
schema_version: "2.0"
id: "adr-001-architecture-style"
title: "轻量微内核与单一可执行文件架构"
version: 2
section: "核心架构"
object: "通用系统"
function: "核心规范"
priority: "高"
workflow_state: "decided"
decision_outcome: "accepted"
rejection_reason: ""
superseded_by: ""
implementation_state: "implemented"
impl_commit: "de371b8"
impl_verifier: "Antigravity-AI (单元测试 19/19 通过)"
---

# 轻量微内核与单一可执行文件架构

> **锚点 ID**：`adr-001-architecture-style` | **所属对象**：`通用系统` | **业务功能**：`核心规范`
> **生命周期**：`🟢 已决策` | **决策状态**：`已定` | **实现现状**：`implemented` | **优先级**：`高`

## 核心论述与现实依据

系统定位为人机协同决策治理台账，必须保证本地优先、极简启动与无外部依赖。

## 历史讨论与决策记录

### 第 1 轮定案与要求 (2026-10-05 10:00)
- **变更说明**：初始化架构决策
- **💡 用户意见（最新原话）**：
采用标准库开发，不引入外部第三方框架，保证单执行脚本直接启动。
- **🤖 团队答复（落实说明）**：
已基于 Python 标准库 http.server 与 sqlite3 构建核心微内核。
````

---

## 🧪 自动化测试验证

项目内置完整的单元与回归测试套件，覆盖架构审查报告中的全部 P1 / P2 关键场景：

```bash
python -m unittest discover tests
```

- `test_git_engine.py`：暂存区隔离保护、存在其他已暂存文件时拒绝误提交、锁定检测
- `test_db_and_concurrency.py`：乐观并发版本锁（409 Conflict）、幂等键去重重放、单议题回退、SQLite 在线备份
- `test_markdown_parser.py`：Frontmatter 2.0 往返序列化、代码围栏内假轮次隔离、多行原话保留、CRLF 归一化
- `test_decision_service.py`：端到端状态机协调、非法 ID 与路径穿越强拦截、多阶段状态输出
- `test_agent_and_recovery.py`：以 Markdown 为事实源重建索引、有效决策与否决红线分离、代码实现核验证据绑定

---

## 📜 开源许可证

本项目采用 **[GNU General Public License v3.0 (GPLv3)](./LICENSE)** 许可证开源。  
欢迎在各类人机协同、自主 Agent 治理与软件工程研发项目中引用与二次开发。
