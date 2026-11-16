---
title: 接口与扩展契约
description: HTTP API、安全边界、三轴状态契约、CAS 幂等与重试、agent-question 协议及只读 Agent 钩子完整指南
---

# 接口与扩展契约

本阶段定义 HTTP 读写接口、三轴状态与 Markdown 存储契约、Agent 只读钩子与 `agent-question` 单选围栏协议。任何自动化接入都必须通过 HTTP 服务与只读命令行交互，禁止直接改写 `decisions.db` 或 `decisions/metadata.json`。

## 能力边界与安全假设

1. **回环网络边界**：`core/server.py` 启动前校验 `is_loopback_host(host)`，仅接受 `localhost` 或回环 IPv4/IPv6；静态文件服务 `send_head` 禁止任何软链接逃逸到 `web/` 目录之外。
2. **跨站写入防护**：写请求检查 `Host`、`Origin`（允许本机回环源或空 `Origin`）与 `Sec-Fetch-Site`（拒绝 `cross-site`），强制 `Content-Type: application/json`，拒绝 `Transfer-Encoding`，要求唯一非负整数 `Content-Length`，限制最大请求体为 `10 MiB`（`MAX_BODY_SIZE = 10 * 1024 * 1024`），读取超时 `10s`，Git 命令超时 `30s`。
3. **可移植议题 ID（`validate_portable_id`）**：只允许 `1–128` 位 `[a-zA-Z0-9_-]`；拒绝 `.`/`..`、路径分隔符、Windows 设备保留名（`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`）及与已有议题仅大小写不同的 ID，避免跨系统目录冲突。
4. **语义非授权原则**：`accepted`、`verified` 与 `agent-question` 单选答案仅是台账记录数据。服务端不自动执行项目构建、不代跑测试、也不把已通过或已核验标签转化为 Shell 执行权限。

## HTTP REST API 参考

### 只读查询端点（`GET`）

| 路径 | 关键查询参数 | 响应与说明 |
|---|---|---|
| `/` | — | `302` 重定向至 `/dashboard.html` |
| `/api/config` | — | 返回当前加载的配置对象（`Config.to_dict()`） |
| `/api/status` | — | 返回 `project_name`、绝对路径（`decisions_dir`, `database_path`, `metadata_json_path`）、Git 可用性及 `consistency` 摘要；供 `agent_hooks` 预检目标目录 |
| `/api/topics` | — | 返回受 `topic_scope` 过滤的议题列表、能力字段、`settled_decisions`、`open_questions`、`changelog` 与配置 |
| `/api/topic/<id>` | — | 返回单议题完整详情、`version`、`content`、`discussion`、关联议题与最近快照列表（历史被迁出议题仍可直达） |
| `/api/git/log` | `limit`, `offset`, `topic_id` | 返回 Git 提交历史、SQLite `revisions` 快照与当前全局 `current_revision` |
| `/api/agent/context` | `module`, `path`, `topic_id`, `format=json\|markdown` | 返回五桶结构化上下文 JSON 或 Markdown 摘要；指定不存在的 `topic_id` 直接报错而非静默为空 |
| `/api/recovery/check` | — | 对比 Markdown、`topics` 与 `metadata.json`，返回详细一致性报告 |

### 受保护写端点（`POST`）

所有修改单议题状态的 POST 请求可传入顶层 JSON 字段 `expected_version` / `request_id`，或通过 HTTP 请求头 `X-Expected-Version` / `X-Request-Id` 传递。

| 路径 | 必填 / 关键字段 | 行为与说明 |
|---|---|---|
| `/api/topic/create` | `id`, `title`, 可选 `content_override`, 三轴字段, `request_id` | 创建新议题并写入首版快照；省略字段取默认值 |
| `/api/topic/<id>/save` | `expected_version`（已有议题必填）, `request_id`, `new_user_opinion`, `new_agent_reply`, `edit_latest_round`, 三轴字段, `commit_message` | 追加新一轮讨论、更新字段或更正最近一轮；同一 `request_id` + 同载荷可幂等重放 |
| `/api/topic/<id>/restore` | `rev_id`, `expected_version`（现存议题必填；已删议题复原或创建重放可省）, `author`, `reason`, `request_id` | 将单议题恢复到指定 `rev_id`（已删议题沿 `TOPIC_REMOVE` 的 `prior_rev_id` 追溯） |
| `/api/topic/<id>/verify` | `expected_version`, `impl_commit`（非空）, `verifier`, `test_summary`, `mark_verified`（bool）, `request_id` | 仅登记调用方提供的实现证据；**不**替调用方运行测试 |
| `/api/topic/<id>/delete` | `expected_version`, 可选 `author`, `reason`, `request_id` | 将 Markdown 移至 `decisions/.archived_rollback/`，清理 `topics` 行并记 `TOPIC_REMOVE` 审计快照以便撤销 |
| `/api/rollback` | `rev_id`, `expected_revision`（必填，来自 `/api/git/log`） | 全库回滚至指定全局修订，未传 `expected_revision` 返回 `428`、过期返回 `409` |
| `/api/recovery/rebuild` | — | 锁内以 `decisions/*.md` 重筑 `topics` 与 `metadata.json`（保留 `revisions`）；发现漂移阻断时返回 `409` |
| `/api/backup` | — | 调用 SQLite Backup API 在同目录生成 `.bak_YYYYMMDD_HHMMSS` 在线热备份 |

### 常见 HTTP 状态码

- `200`：成功完成或幂等重放（含 `is_replay: true`）。
- `400`：非法 ID、字段类型错误、未通过 `_validate_document` 围栏往返校验、首次切换至 `partially_accepted` 缺少用户原话或 `rejected` 缺少 `rejection_reason`。
- `403`：非法 `Host`、`Origin` 或 `Sec-Fetch-Site: cross-site`。
- `404`：未知接口或未找到对应议题。
- `408` / `413` / `415`：请求体读取超时（10s）、超 10 MiB 或非 `application/json`。
- `409`：`version_conflict`（带 `current_version` 与 `current_topic`）、`idempotency_conflict` 或 `revision_conflict`。
- `428`：已有议题写入缺少 `expected_version`（`version_required`）或全库回滚缺少 `expected_revision`（`revision_required`）。

## 数据、三轴状态与幂等契约

1. **三轴正交模型（`core/contracts.py`）**：
   - `workflow_state`：`pending`（待决策）、`discussing`（待讨论）、`decided`（已决策）、`deferred`（推迟再议）、`superseded`（已被替代）。
   - `decision_outcome`：`""`（空，不推定为同意）、`accepted`（已同意）、`partially_accepted`（部分同意，必须在原话说明范围，在上下文引擎中进入 `pending_requirements`）、`rejected`（已否决）。
   - `implementation_state`：`not_started`、`in_progress`、`implemented`、`verified`。
   - **重要分隔**：同意“条件满足后再议”应填 `decision_outcome: "accepted"` + `workflow_state: "deferred"`，Agent 需读 `deferred_topics` 中的原话条件，不得提前实施；被替代议题设 `workflow_state: "superseded"` 与 `superseded_by`，保留原结论仅作追溯（旧否决不再计入当前红线）。
2. **Markdown `schema_version: "2.0"` 与局部更正**：
   - 权威 `.md` 文件使用 YAML Frontmatter 存放元数据，`## 💬 讨论与演进历程` 下记录 `### 第 N 轮（...）`；已有议题省略的请求字段保持原值，传入空字符串表示清空支持清空的字段。
   - 仅在用户明确要求修正**刚刚提交的最近一轮**时才加 `edit_latest_round: true`，携带读取时的 `expected_version`，并只传需修改的 `new_user_opinion` 或 `new_agent_reply`（另一方保留原文，旧文本留在 SQLite `revisions` 快照中）。禁止用来重写更早轮次。
3. **分阶段回执与幂等重试铁律**：
   - 写响应分开返回 `save_status`、`export_status` 与 `git_status`（如 `committed`、`disabled`、`skipped_unrelated_staged`）。台账已保存但 Git 未提交时，**禁止重新生成新 `request_id` 再 POST**，否则会追加重复轮次。
   - 在发出 POST 前应将完整请求 JSON 写到本地临时文件；超时或连接断开时，**原样重发保存的请求文件（同 `request_id`、同 `expected_version`、同载荷）**，切勿先读最新版本号再改包重发。

## Agent 工作流、只读钩子与 `agent-question`

### 1. 只读命令 `core.agent_hooks`

任务钩子只读不写，**本仓库不附带会自动生效的用户级配置或自动安装 Git 钩子**，由调用方或 Agent 宿主在适当阶段显式执行：

```sh
# 1) 任务开始前校验目标项目、一致性并导出上下文 JSON
python3 -m core.agent_hooks --config /path/to/dashboard.config.json before-task
python3 -m core.agent_hooks --config /path/to/dashboard.config.json before-task --module 存储层
python3 -m core.agent_hooks --config /path/to/dashboard.config.json before-task --topic adr-storage

# 2) HTTP 写入成功并本地保存 receipt.json 后核对台账版本与一致性
python3 -m core.agent_hooks --config /path/to/dashboard.config.json after-write --topic adr-storage --receipt /path/to/receipt.json
```

- 仅允许连接本机回环 HTTP，禁用系统代理与重定向；可用 `--url http://127.0.0.1:其他端口` 覆盖连接地址，但仍会比对目标配置里的真实数据目录路径。
- `before-task` 输出含 `active_decisions`、`rejected_proposals`、`pending_requirements`、`deferred_topics`、`superseded_topics`（指定 `--topic` 时另附 `requested_topic`）。
- 退出码 `0` 表示通过（需额外核实回执中 `git_committed` 等字段）；退出码 `2` 表示配置/连接/目录/一致性/回执校验失败或参数非法（错误 JSON 输出到 `stderr`）。`after-write` 不用于确认 `delete_topic` 归档或全库回滚。

### 2. Python 标准库写盘与原样重试示例

下列示例演示先存请求、再 POST、再落盘回执的标准库流程（路径应选在项目本地临时忽略目录，切勿把讨论原话或回执提交到公开仓库）：

```python
import json
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8765"
topic_id = "adr-storage"
with urlopen(base + "/api/topic/" + topic_id) as response:
    topic = json.load(response)

request_data = {
    "expected_version": topic["version"],
    "request_id": str(uuid.uuid4()),
    "new_user_opinion": "用户本轮实际确认原话",
    "new_agent_reply": "本轮实际回应与核对证据",
    "commit_message": "docs(decision): 追加存储议题讨论",
}
Path("request.json").write_text(json.dumps(request_data, ensure_ascii=False), encoding="utf-8")

req = Request(
    base + "/api/topic/" + topic_id + "/save",
    json.dumps(request_data).encode("utf-8"),
    {"Content-Type": "application/json"},
)
with urlopen(req) as response:
    receipt = json.load(response)
Path("receipt.json").write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
```

> 严格约束：仅在已获得用户明确授权且原话内容确定时执行写入；示例文案不得直接写入真实台账。

### 3. `agent-question` 选项协议围栏

当需要用户在有限方案中做选择时，可在最新一轮 `new_agent_reply` 内嵌入 ```` ```agent-question ```` JSON 代码围栏（不要把推荐答案预填进 `new_user_opinion`）：

````python
question = {
    "question": "这轮先实现哪种保存方式？",
    "options": [
        {"label": "先保存到本地", "description": "先完成本机使用流程"},
        {"label": "先讨论同步需求", "description": "明确范围后再实施"},
    ],
}
new_agent_reply = (
    "请确认本轮范围。\n\n```agent-question\n"
    + json.dumps(question, ensure_ascii=False, indent=2)
    + "\n```"
)
````

- 仅最新一轮有效，且每轮只允许 **1 个问题、2–8 个不同选项**（字符串或 `{ "label", "description" }`）；
- 讲解该格式时必须使用更长的外层代码围栏（如 4 个反引号）包裹，防止误激活单选卡；多块、非法或未闭合协议会退化为安全纯文本展示；
- 界面不预设默认选中项，用户可单独写字或单选后继续补充多行文字，提交时统一记入普通用户意见，**不**自动更改三轴状态。

## 扩展与接口排错 FAQ

| 场景 / 错误码 | 原因与正确处理方式 |
|---|---|
| 服务离线或目标目录不符 | 核对 `--config` 指向的目录、`--port` 与运行中服务；禁止连上默认端口或示例目录盲写 |
| `428 version_required` | 写入既有议题未传 `expected_version`（或全库回滚未传 `expected_revision`）；先读取最新详情/历史后再构造新请求 |
| `409 version_conflict` / `idempotency_conflict` | 版本冲突时先读取最新版本与远端差异，保留原草稿合并后再用新 `request_id` 提交；若为同键异参冲突，核对是否误复用了旧 `request_id` |
| 一致性报告文件/索引漂移 | 检查是否有人手工改过 `.md` 或仍有未完成请求；先在线备份 `decisions.db` 再人工核对差异，勿与在线写入并发运行维护命令 |
| `400` 模板与围栏往返校验失败 | 正文或原话中出现了未闭合的代码围栏或与 `## 💬 讨论与演进历程` / 轮次标题冲突的裸模板标题；按提示闭合围栏或将示例放入外层长围栏，禁止靠删减用户原话绕过检查 |
| Git 未提交（`git_status != "committed"`） | 如实向用户报告 `git_status` 与 `git_message`；台账保存成功、Git 提交成功与推送是三个独立结果 |
