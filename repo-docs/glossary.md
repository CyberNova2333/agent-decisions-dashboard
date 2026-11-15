# 核心术语表

本页统一当前代码库中容易混淆的机制与字段口径，每项概念均对应后端或前端真实实现，不引入概念延伸或推测。

| 中文概念 | 代码标识符 / 字段 | 准确定义与边界 |
| --- | --- | --- |
| 三轴正交状态 | `workflow_state`, `decision_outcome`, `implementation_state` | [状态契约](../core/contracts.py) 定义的三组独立枚举：进展（5 值）、是否同意结论（空或 3 值）、工程实现（4 值）。同意不等于已实现，推迟不清空结论。 |
| 局部同意 | `decision_outcome: "partially_accepted"` | 仅部分范围获准实施。首次切换至此值时服务要求非空用户意见以写明边界；在[上下文引擎](../core/agent_context.py)中进入 `pending_requirements`，不直接作为全局已定规则 `active_decisions`。 |
| 推迟再议与替代 | `deferred`, `superseded`, `superseded_by` | 新协议（`schema_version: "2.0"`）下属于 `workflow_state`；读取旧数据中残留的 `decision_outcome` 别名时在内存解释为进展并置空结论，直到下一次正常保存或恢复时升级写回。 |
| 议题唯一标识符 | `topic_id` / `validate_portable_id` | `^[a-zA-Z0-9_-]{1,128}$`，拒绝 `.`/`..`、路径分隔符、Windows 保留文件名（如 `CON`、`NUL`）以及与现有议题仅大小写不同的别名冲突。 |
| 乐观锁版本与 ABA 序号 | `expected_version`, `topic_version_seq` | `topics.version` 从 1 递增；`topic_version_seq`（位于 `decisions.db`）记录历史上曾经到达过的最大版本号，防止议题删除重创后与旧版本回执混淆。 |
| 幂等请求身份与指纹 | `request_id`, `req_hash`, `idempotency_keys` | 客户端为每个独立写操作生成的 `1–256` 字符字符串。后端计算规范化 JSON + 操作参数 SHA-256 指纹，同键同参返回缓存回执（含 `is_replay: true`），同键异参返回 `409 idempotency_conflict`。 |
| 分阶段回执 | `save_status`, `export_status`, `git_status` | 写操作响应中分别指示 SQLite/Markdown 主台账、`metadata.json` 摘要同步和可选 Git 提交的结果；台账成功不代表 Git 已提交。 |
| 未完结的 Git 挂起态 | `git_status == "pending"` | 表示主台账已写入但 Git 阶段尚待收尾的中间态；幂等重放时会触发 `_resume_pending_phases` 判断是安全补交还是按已有新提交跳过。 |
| 幂等重放标志 | `is_replay: true` | 同一 `request_id` 携带一致参数重放时响应中返回的标志，表示本次请求复用了既有结果或仅续做后段导出/Git，未重复追加轮次。 |
| 轮次更正 | `edit_latest_round: true` | 在[Markdown 解析器](../core/markdown_parser.py) `amend_round` 支持下原位替换最近一轮讨论的用户或 Agent 文本，不增加轮次数，仅可覆盖最新一轮且原版本保留于 `revisions` 快照。 |
| 安全归档删除 | `delete_topic`, `.archived_rollback/`, `TOPIC_REMOVE` | 将 `decisions/<id>.md` 移入 `decisions/.archived_rollback/`（附随机后缀），删除 `topics` 索引行，并记录带 `prior_rev_id` 的 `TOPIC_REMOVE` 审计快照以便单议题或全库撤销。 |
| 话题视图范围 | `topic_scope.active_topic_ids` | 可选配置的活跃 ID 白名单；启用后列表视图、概览统计与 `AgentContextEngine` 仅返回活跃项及已声明的关联，历史/被迁出议题仍保留在磁盘与数据库中且可按 ID 直达详情。 |
| 只读任务钩子 | `core.agent_hooks` (`before-task`, `after-write`) | 通过本机 HTTP（禁止代理与重定向）执行配置目录核对、一致性检查、上下文拉取及回执验证的独立 CLI；失败返回退出码 `2`，不执行任何写入或修复动作。 |
| 选项协议围栏 | ```` ```agent-question ```` | 仅在最新一轮 Agent 回复中生效的单选卡片协议：允许 1 个问题、2–8 个选项，不设默认选中项；用户选择后连同自由补充文本一起写入普通用户意见，不产生额外状态更改。 |

证据状态：除特别标注外，本页基于当前源码已确认。
