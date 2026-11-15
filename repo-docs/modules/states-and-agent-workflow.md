# 模块：三轴状态模型与 Agent 工作流

本模块说明本仓库如何把“流程走到哪一步”“用户同意了什么范围”“工程实际落实与验证到什么程度”彻底拆开，以及外部 Agent 如何通过只读钩子、参数化上下文提取和 `agent-question` 协议卡参与协作而不越权。

## 1. 三轴正交状态与旧协议兼容

[状态与 ID 契约](../../core/contracts.py)中的 `decision_axes()` 把议题状态划分为三个正交维度，并在 `settled_decisions`、`open_questions` 概览表与 Agent 上下文中共同生效：

| 维度 | 允许枚举值 | 关键业务约束 |
| --- | --- | --- |
| `workflow_state` | `pending`, `discussing`, `decided`, `deferred`, `superseded` | 控制议题当前生命周期阶段；`deferred` 必须结合原话条件读取，`superseded` 保留原结论供追溯并可选填 `superseded_by`。 |
| `decision_outcome` | `""`, `accepted`, `partially_accepted`, `rejected` | `""` 表示尚未形成结论（不推断为同意）；首次切换至 `partially_accepted` 时必须有非空用户意见写明范围；`rejected` 必须提供非空 `rejection_reason`。 |
| `implementation_state` | `not_started`, `in_progress`, `implemented`, `verified` | 仅在 `canonical_impl_state` 校验通过后生效；`verified` 通常经由 `POST /api/topic/<id>/verify` 连同 `impl_commit`、`verifier`、`test_summary` 一起登记，且服务**不**自动执行测试。 |

对于历史文档中仍在 `decision_outcome` 写入 `"deferred"` 或 `"superseded"` 的旧格式记录，`LEGACY_PROGRESS_OUTCOMES` 会在读取阶段自动将其折叠归类为 `workflow_state`，并将内存中 `decision_outcome` 置空，原始 Markdown 与旧快照不会被静默重写；直到用户下次显式保存或恢复该议题时才升级写成独立的 `schema_version: "2.0"` 字段。

## 2. `topic_scope` 视图隔离与五桶上下文查询

通过 `dashboard.config.json` 的 `topic_scope.active_topic_ids`（`null` 表示全量展示，字符串数组表示活跃子集），项目可以在不物理删除旧议题的前提下收窄日常工作台视图与 Agent 提示词体积。

[上下文查询引擎](../../core/agent_context.py)基于活跃议题集合将约束归入五个互斥桶（供 JSON `GET /api/agent/context` 与 Markdown `--export-agent-context` 输出）：

1. **`active_decisions`**：同时满足 `workflow_state == "decided"` 且 `decision_outcome == "accepted"` 的当前有效定论；
2. **`rejected_proposals`**：满足 `decision_outcome == "rejected"` 且尚未被替代的红线议题；
3. **`pending_requirements`**：除已暂缓或已替代之外的所有 `partially_accepted`、`pending` 与 `discussing` 项（因此部分同意不会直接混入全局 `active_decisions`）；
4. **`deferred_topics`**：`workflow_state == "deferred"` 项，保留全部讨论原话以便读取恢复条件；
5. **`superseded_topics`**：`workflow_state == "superseded"` 项，仅作演进追溯；已淘汰旧否决不再计入当前红线。

`query_context` 支持 `module`（匹配 `section` / `object` / `function` 子串）、`path_keyword`（匹配正文或 `section` 子串）与 `topic_id`（精确匹配单个议题，若不存在直接抛出 `KeyError` 而非静默返回空列表，同时输出 `requested_topic`）。

## 3. 只读任务钩子（`core.agent_hooks`）

[Agent 钩子工具](../../core/agent_hooks.py)是一个无副作用的独立 CLI，旨在帮助 Agent 宿主或人工脚本核对读写前提：

- **强制本机安全策略**：仅允许回环地址 HTTP（`is_loopback_host`），显式使用空 `ProxyHandler({})` 与 `NoRedirects` 禁用代理和 HTTP 重定向，单次请求超时 10 秒。
- **`preflight` 预检**：首先拉取 `GET /api/status` 核对服务返回的 `database_path`、`decisions_dir`、`metadata_json_path` 是否与指定 `--config` 解析出的绝对路径完全一致，并要求 `consistency.consistent` 为真。
- **`before-task`**：预检通过后拉取 `/api/agent/context`（或指定 `--topic` 时再请求 `/api/topic/<id>`），向标准输出打印结构化 JSON。任何连接失败、目录错配、漂移、未知议题或参数错误均输出错误 JSON 至 `stderr` 并以退出码 **`2`** 中止。
- **`after-write`**：读取调用方本地保存的 `receipt.json`，再次检查一致性和当前版本，确认当前 `version` 与回执预期版本匹配，并如实报告 `git_committed` 字段；不用于确认 `delete_topic` 归档或全库回滚结果。

> 注意：仓库**不**会向用户环境自动安装全局 Agent 配置或 Git 写钩子；是否接入 `before-task` / `after-write` 由宿主或开发者自行决定。

## 4. `agent-question` 选项协议围栏

当 Agent 需要用户在有限候选方案中选择时，可在最新一轮 `new_agent_reply` 中嵌入一段 ```` ```agent-question ```` JSON 代码围栏（仅包含 `question` 字符串和 `2–8` 个去重选项，选项可为字符串或 `{ "label", "description" }`）。[选项协议模块](../../web/agent-question.js)遵循以下保护边界：

- 仅解析**最新一轮** Agent 回复，并且严格忽略被外层长代码围栏、缩进代码块或引用块包住的示例文本；
- 若出现多块有效协议、格式非法、重复选项或未闭合围栏，整段按原文安全回显而不激活单选卡片；
- 页面渲染单选按钮时**不预设任何默认答案**，用户可以只填自由文字、单选后补充多行文字，或在提交前修改选择；提交时选中的标签与自由补充统一拼入普通用户意见字段保存，**不会**自动篡改三轴状态。

继续阅读：[保存、幂等、归档与恢复机制](save-idempotency-and-recovery.md) · [一条真实主流程](../walkthroughs/one-real-run.md) · [代码地图](../code-map.md)

证据状态：除特别标注外，本页基于当前源码已确认。
