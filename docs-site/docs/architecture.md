---
title: 原理与源码导览（含决策迁移）
description: 系统分层架构、生命周期交互图、真实运行主流程走读、代码地图与关键决策迁移说明
repoGuideSource: repo-docs/walkthroughs/one-real-run.md
---

# 原理与源码导览（含决策迁移）

本阶段串联起交互界面、HTTP 回环服务、CAS 并发控制与双源持久化，并直接复用仓库 `repo-docs/` 的真实走读与代码位置索引，同时记录已确认的协议与数据迁移决策。

## 系统分层与存储拓扑

1. **交互层（`web/`）**：`dashboard.html` + `app.js` 构成双栏主从工作台、三段式详情驾驶舱与专注批阅流；`markdown.js` 禁用原生 HTML 并校验链接协议，`diagrams.js` 离线封装 `web/vendor/mermaid-12.1.0.min.js`（strict 模式、5 万字符与 500 边上限），`agent-question.js` 仅解析最新一轮有效单选围栏。
2. **回环接入与锁边界（`core/server.py`、`core/locking.py`）**：基于 Python 标准库 `ThreadingHTTPServer`，按请求校验证书/Origin/Sec-Fetch-Site/回环来源；业务写入通过基于规范化 `database_path` 的进程内可重入锁串行协调。
3. **业务编排与权威文件（`core/decision_service.py`、`core/markdown_parser.py`）**：写操作在覆写 `decisions/<id>.md` 前必须通过 `_validate_document` 往返解析检验并执行原子替换；Markdown 承载每个议题的当前全部正文与讨论轮次。
4. **快照历史、一致性与可选提交（`core/db.py`、`core/recovery.py`、`core/git_engine.py`）**：SQLite `decisions.db` 额外持有全量 `revisions` 快照、`topic_version_seq` 单调版本序号与 `idempotency_keys` 幂等回执缓存；`metadata.json` 为只读概览导出；`GitEngine` 检查暂存区干净度后执行 30s 超时受限的路径隔离提交。

## 交互式生命周期图

<DiagramFrame
  src="/diagrams/decision-lifecycle.html"
  title="决策状态流转交互图（支持平移 / 缩放 / 节点探查）"
  aspect="966 / 326"
  new-tab-label="在新窗口全屏打开 ↗"
/>

## 真实运行全链路走读

以下主链路走读直接同步自仓库源码指南 `repo-docs/walkthroughs/one-real-run.md`（网页中的源码路径已转换为仓库相对路径标识）：

<!--@include: ../../repo-docs/walkthroughs/one-real-run.md{2,}-->

## 源码目录与模块地图

### `core/` 服务与存储内核

| 文件路径 | 核心职责 | 关键符号 |
|---|---|---|
| `core/config.py` | 配置加载、环境变量覆盖、相对路径解析与 `topic_scope` 过滤 | `load_config`, `Config.topic_is_active` |
| `core/contracts.py` | 议题 ID 可移植性检查与三轴状态枚举及旧别名折叠 | `validate_portable_id`, `decision_axes`, `canonical_impl_state` |
| `core/server.py` | 回环 HTTP 网关、CLI 模式分发、安全请求头与容量校验 | `is_loopback_host`, `make_handler`, `main` |
| `core/decision_service.py` | 议题创建、保存、幂等续做、轮次更正、核验登记、归档删除与恢复 | `DecisionService.save_topic`, `edit_latest_round`, `delete_topic`, `restore_single_topic`, `rollback_full` |
| `core/db.py` | SQLite 建表与迁移、ABA 单调序列、幂等键、修订快照与在线热备 | `DatabaseManager.upsert_topic`, `check_idempotency`, `commit_revision`, `backup_database` |
| `core/markdown_parser.py` | `schema_version: "2.0"` Frontmatter 与围栏感知讨论解析/拼装 | `TopicMarkdownParser.parse_markdown_text`, `amend_round`, `serialize_markdown` |
| `core/recovery.py` | 摘要摘要比对、从权威 Markdown 重筑 `topics` 与导出 `metadata.json` | `RecoveryManager.check_consistency`, `rebuild_index_from_markdown`, `sync_metadata_json` |
| `core/locking.py` | 进程内按规范化 `database_path` 隔离的可重入并发锁 | `ledger_lock`, `serialized` |
| `core/git_engine.py` | 暂存区纯净检查、超时守卫与路径隔离 Git 提交 | `GitEngine.commit_decision`, `get_commit_history` |
| `core/agent_context.py` | 五桶治理上下文聚合与 Markdown 导出 | `AgentContextEngine.query_context`, `format_as_markdown` |
| `core/agent_hooks.py` | 回环只读任务前后钩子与一致性预检 CLI | `AgentHooks.preflight`, `before_task`, `after_write` |

### `web/` 静态前端与 `tests/` 验证集

| 目录 / 文件 | 职责与覆盖内容 |
|---|---|
| `web/dashboard.html`、`web/app.js` | 双栏主从工作台、三段式详情驾驶舱、专注批阅与草稿防丢失管理 |
| `web/agent-question.js`、`web/markdown.js`、`web/diagrams.js` | 单选围栏解析、无原生 HTML 的 Markdown 渲染、离线 Mermaid 12.1.0 渲染封装 |
| `web/vendor/` | 离线打包的 Mermaid 12.1.0、Anime.js 4.5.0、IBM Plex Sans 字体与各自许可 |
| `tests/*.py`（`unittest`） | 覆盖保存幂等、CAS/ABA、安全边界、状态/撤销/使用回归、`topic_scope`、Git 守卫与恢复（227 项） |
| `tests/*.test.js`（`node --test`） | 覆盖 `agent-question` 围栏协议、XSS 转义与 Markdown 表格/链接渲染（12 项） |

### 持久化与恢复机制

有关 ABA 单调版本序列 `topic_version_seq`、断点续做 `_resume_pending_phases`、SQLite 在线热备份与全库回滚的更多细节，请查阅仓库文档 `repo-docs/modules/save-idempotency-and-recovery.md` 与 `repo-docs/modules/states-and-agent-workflow.md`。

## 关键边界与决策迁移

以下演进均已落地当前代码，升级旧台账目录或迁移旧脚本时请重点核对：

1. **三轴正交状态与旧 `decision_outcome` 别名迁移**：
   - 旧格式允许在 `decision_outcome` 中填写 `"deferred"` 或 `"superseded"`；当前版本通过 `LEGACY_PROGRESS_OUTCOMES` 在读取时将其映射为 `workflow_state` 并把 `decision_outcome` 置空（**不自动改写磁盘旧文件**）。
   - 仅当对该议题执行正常保存或恢复时，才会升级写回 `schema_version: "2.0"` 的独立 `workflow_state` + `decision_outcome` + `implementation_state` 三轴字段。
2. **安全归档删除替代直接删档（`delete_topic`）**：
   - 删除议题不再直接抹除 `.md` 文件，而是移入 `decisions/.archived_rollback/<id>_<随机后缀>.md` 并写入带 `prior_rev_id` 的 `TOPIC_REMOVE` 快照；调用 `POST /api/topic/<id>/restore` 或全局回滚即可按需撤销。
3. **视图范围收敛（`topic_scope.active_topic_ids`）**：
   - 当老项目积累大量历史议题时，无需从磁盘删除旧 `.md` 或改历史库：只需在 `dashboard.config.json` 配置 `topic_scope.active_topic_ids` 数组，工作台列表与 `GET /api/agent/context` 会自动收敛为活跃议题视图，同时保留 `/api/topic/<id>` 直接查阅历史议题的能力。
4. **`doc_data_json_path` 配置键定位调整**：
   - `DEFAULT_CONFIG` 仍保留 `doc_data_json_path` 键名以兼容既有配置，但当前版本不再将该文件作为权威导入或重建来源，摘要统一导出至 `metadata_json_path`，权威数据始终以 `decisions_dir/*.md` 与 `database_path` 为准。

## 源码证据与验证边界

提交任何影响业务或前端交互的修改后，请在独立测试目录下运行完整验证（切勿直接对日常运行中的用户 `decisions.db` 执行重建或测试）：

```sh
python3 -m unittest discover tests
node --test tests/*.test.js
node --check web/app.js && node --check web/markdown.js && node --check web/diagrams.js
git diff --check
```

文档构建与结构检查（面向仓库维护者）：

```sh
python3 /home/cybernova/.gemini/skills/repo-docs/scripts/validate_repo_docs.py --repo-root . repo-docs
pnpm --dir docs-site run docs:build
```

有关每条架构结论对应的具体源码搜索锚点、可证伪条件与剩余风险（如多进程协调、断电保证及手工浏览器交互检查范围），完整审计表保存在仓库 `repo-docs/references/source-evidence.md` 与 `repo-docs/references/quality-review.md`。
