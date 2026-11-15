# 代码地图

初次理解端到端保存与回执交接请先读[一条真实主流程](walkthroughs/one-real-run.md)，再按本页职责表定位代码与测试。本页覆盖当前仓库 `core/`、`web/`、`tests/` 与 `examples/` 的实际代码组织。

| 路径 | 职责 | 关键代码 | 与主流程的关系 |
| --- | --- | --- | --- |
| `core/` | HTTP 网关、业务保存、存储、锁与只读钩子 | [HTTP 服务](../core/server.py)、[业务保存服务](../core/decision_service.py)、[数据库管理器](../core/db.py)、[Agent 钩子](../core/agent_hooks.py) | 接收本机请求，校验边界并协调权威文件、快照与提交 |
| `web/` | 零构建静态浏览器工作台与离线渲染库 | [主应用逻辑](../web/app.js)、[选项协议卡片](../web/agent-question.js)、[Markdown 渲染](../web/markdown.js)、[Mermaid 封装](../web/diagrams.js) | 负责列表筛选、双栏专注批阅、草稿保护与本地图表渲染 |
| `tests/` | Python 回归与前端 Node 单元测试 | [保存流水线测试](../tests/test_decision_service.py)、[安全边界测试](../tests/test_security_boundaries.py)、[主题范围测试](../tests/test_topic_scope.py)、[前端选项测试](../tests/agent-question.test.js) | 校验状态迁移、CAS 冲突、XSS 转义与并发安全不变式 |
| `examples/` | 独立示例配置与样板议题 | [示例议题目录](../examples/decisions/metadata.json) | 供演示或隔离试验参考，不得混作目标工作区配置 |

## `core/`

| 重要代码 | 功能 | 关键符号 | 调用方 / 使用方 |
| --- | --- | --- | --- |
| [配置加载器](../core/config.py) | 加载 `dashboard.config.json`、环境变量与相对路径解析 | `load_config`, `Config.topic_is_active` | 服务启动、`AgentHooks` 预检 |
| [状态与 ID 契约](../core/contracts.py) | 校验可移植议题 ID 与三轴状态枚举映射 | `decision_axes`, `validate_portable_id`, `canonical_impl_state` | `DecisionService`, `AgentContextEngine`, `RecoveryManager` |
| [HTTP 回环网关](../core/server.py) | 回环校验、Origin/请求头防守、CLI 维护模式与 REST 路由 | `is_loopback_host`, `make_handler`, `main` | 浏览器前端、外部 Agent HTTP 客户端、`start_dashboard.*` |
| [决策业务服务](../core/decision_service.py) | 创建、保存、轮次更正、核验登记、归档删除与回滚恢复 | `DecisionService.save_topic`, `edit_latest_round`, `delete_topic`, `restore_single_topic`, `rollback_full` | HTTP POST 路由处理器 |
| [SQLite 存储](../core/db.py) | 建表迁移、CAS 序列（`topic_version_seq`）、幂等键与快照备份 | `DatabaseManager.upsert_topic`, `check_idempotency`, `commit_revision`, `backup_database` | `DecisionService`, `RecoveryManager` |
| [Markdown 解析](../core/markdown_parser.py) | `schema_version: "2.0"` Frontmatter 与围栏感知讨论解析/拼装 | `TopicMarkdownParser.parse_markdown_text`, `amend_round`, `serialize_markdown` | `DecisionService`, `RecoveryManager` |
| [一致性与重建](../core/recovery.py) | 摘要比对检查、从权威 Markdown 重建索引与导出 `metadata.json` | `RecoveryManager.check_consistency`, `rebuild_index_from_markdown`, `sync_metadata_json` | HTTP 恢复接口、`--check-consistency`、`--rebuild-index` |
| [项目级并发锁](../core/locking.py) | 按规范化数据库路径提供进程内可重入线程锁 | `ledger_lock`, `serialized` | `DecisionService`, `RecoveryManager` 写操作 |
| [Git 提交引擎](../core/git_engine.py) | 超时保护（30s）、暂存区污染检查与路径隔离决策提交 | `GitEngine.commit_decision`, `get_commit_history` | `DecisionService` 写后提交、`GET /api/git/log` |
| [上下文查询引擎](../core/agent_context.py) | 按模块/路径/范围分组导出五类上下文桶与 Markdown 摘要 | `AgentContextEngine.query_context`, `format_as_markdown` | `GET /api/agent/context`、`--export-agent-context` |
| [只读任务钩子](../core/agent_hooks.py) | 本机回环预检、`before-task` 拉取与 `after-write` 回执核对 | `AgentHooks.preflight`, `before_task`, `after_write` | 外部 Agent 宿主或人工命令行核对 |

## `web/`

| 重要代码 | 功能 | 关键符号 | 调用方 / 使用方 |
| --- | --- | --- | --- |
| [主应用控制器](../web/app.js) | 双栏主从工作台、三段式详情驾驶舱、专注批阅、草稿备份与归档撤销 | 渲染、筛选、批阅与保存控制器 | [工作台页面入口](../web/dashboard.html) |
| [选项协议卡](../web/agent-question.js) | 仅对最新一轮有效 `agent-question` JSON 围栏解析 2–8 项单选并保留用户补充文本 | 围栏扫描与答案合并逻辑 | `app.js`、`tests/agent-question.test.js` |
| [安全 Markdown 渲染](../web/markdown.js) | 禁用原生 HTML、校验链接协议、支持表格与任务列表渲染 | 块/行内渲染与 HTML 转义 | `app.js`、`tests/markdown.test.js` |
| [Mermaid 封装](../web/diagrams.js) | 离线调用 `web/vendor/mermaid-12.1.0.min.js`，限制 5 万字符与 500 边并设为 strict 模式 | 图表渲染调度 | `app.js`、`dashboard.html` |

`web/vendor/` 下打包了离线 Mermaid 12.1.0、Anime.js 4.5.0 与 IBM Plex Sans 字体及原始 LICENSE 文件，不需运行时访问外网 CDN。

## `examples/`

| 重要代码 | 功能 | 关键符号 | 调用方 / 使用方 |
| --- | --- | --- | --- |
| [架构风格示例](../examples/decisions/adr-001-architecture-style.md)、[存储选型示例](../examples/decisions/adr-002-storage-engine.md)、[示例元数据](../examples/decisions/metadata.json) | 展示 `schema_version: "2.0"` 标准议题与摘要结构 | 示例演示数据 | 仅作演示参考，不要混淆为实际业务台账 |

## `tests/`

| 重要代码 | 功能 | 关键符号 | 调用方 / 使用方 |
| --- | --- | --- | --- |
| [业务保存与幂等](../tests/test_decision_service.py)、[数据库与并发](../tests/test_db_and_concurrency.py) | 验证版本冲突 `409`、同 `request_id` 重放、载荷冲突与 `topic_version_seq` ABA 防护 | `test_optimistic_conflict_and_idempotency_in_service` | `unittest` |
| [安全边界](../tests/test_security_boundaries.py)、[最终审计](../tests/test_final_audit.py) | 验证回环限定、跨站 Origin/Sec-Fetch-Site 拒绝、符号链接越界防护与保留字 ID 拦截 | `SecurityBoundariesTests` | `unittest` |
| [状态与回归](../tests/test_progress_states.py)、[使用回归](../tests/test_usability_regressions.py)、[Undo 回归](../tests/test_undo_regressions.py) | 验证 `partially_accepted`、旧别名兼容、`edit_latest_round`、`delete_topic` 归档与撤销恢复 | `test_partial_acceptance_roundtrips_without_turning_whole_proposal_into_rule` | `unittest` |
| [话题范围](../tests/test_topic_scope.py)、[Agent 钩子](../tests/test_agent_hooks.py)、[恢复与上下文](../tests/test_agent_and_recovery.py) | 验证 `topic_scope.active_topic_ids` 过滤、`before-task`/`after-write` 退出码与一致性重建 | `TopicScopeTests`, `AgentHooksTests` | `unittest` |
| [Git 引擎](../tests/test_git_engine.py)、[Markdown 解析](../tests/test_markdown_parser.py)、[产品契约](../tests/test_product_contracts.py) | 验证 `skipped_unrelated_staged` 保护、围栏安全解析与往返检查 | `GitEngineTests`, `MarkdownParserTests` | `unittest` |
| [前端选项测试](../tests/agent-question.test.js)、[Markdown 渲染测试](../tests/markdown.test.js) | 使用 Node 原生运行器验证草稿还原、XSS 转义与 Mermaid 代码转义 | `node --test` | 开发者与维护检查 |

## 覆盖范围

本代码地图与指南覆盖主服务运行链、三轴状态模型、幂等与归档恢复机制、只读钩子及前端安全边界。本目录未逐行展开 CSS 质感 Token 细节（见根目录设计规范 `DESIGN.md`）以及 Git 维护守卫脚本（`tools/repo_maintenance_guard.py`）；亦不保证跨进程文件锁、远程多用户协同或断电瞬时落盘一致性。

源码链接均指向仓库真实文件；独立发布的静态文档站不包含这些 Python/JS 源码文件，阅读站内文档时请以显示的文件路径在本地克隆中核对。相关证据记录见[源码证据审计](references/source-evidence.md)。

证据状态：除特别标注外，本页基于当前源码已确认。
