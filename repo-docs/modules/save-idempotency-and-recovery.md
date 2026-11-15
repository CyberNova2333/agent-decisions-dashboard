# 模块：保存、幂等、归档与恢复机制

本模块解析写请求如何越过单机并发竞争，在 Markdown 权威文件、SQLite 版本历史、摘要缓存与 Git 提交之间保持可追溯性，以及异常后如何撤销或重建。核心实现集中在[决策业务服务](../../core/decision_service.py)、[SQLite 持久化管理器](../../core/db.py)、[Markdown 解析器](../../core/markdown_parser.py)与[恢复管理器](../../core/recovery.py)。

## 1. 进程内锁与 ABA 防护

所有写路径均由[项目锁](../../core/locking.py)基于规范化后的 `database_path` 获取进程内可重入线程锁（`@serialized` / `ledger_lock`）。需要明确的是，该锁只协调同一 Python 进程内来自 Web UI 与 Agent HTTP 客户端的多线程请求；多进程同时读写同一份 `decisions.db` 与 `decisions/` 超出当前设计保证。

当一个议题经过保存后被归档删除并重新创建，版本号若重新从 `1` 开始可能误撞旧快照或旧版本约束。[SQLite 存储](../../core/db.py)为此维护独立的 `topic_version_seq` 表，记录每个 `topic_id` 历史达到过的最高版本。重新创建或恢复时通过 `_advance_version`（在 `upsert_topic` 内部计算 `max(current_ver, max_seq)`）保证新版本单调递增。

## 2. 幂等重放与部分阶段续做（`_resume_pending_phases`）

客户端在写操作（`create`、`save`、`restore`、`verify`、`delete`）时可携带 `request_id`。服务端在写入关键台账行之前，先基于操作类型、目标 ID、期望版本与规范化 JSON 参数计算 SHA-256 指纹：

- **已完成操作**：`idempotency_keys` 状态为 `completed`（或 `success`）且 `git_status` 已终结时，直接回放缓存结果并附带 `is_replay: true`。
- **中间态断点续做**：若上次请求已完成 `decisions/*.md` 写入与 SQLite 提交（记录为 `applied` 或 `git_status == "pending"`），但后续 `metadata.json` 导出或 Git 提交尚未结束或超时，同请求重放不会重复写盘、增加版本或追加轮次，而是由 `_resume_pending_phases`（以及 `delete_topic` 中的对应续做分支）补做 `sync_metadata_json()` 并通过 `_pending_git_status` 判断是否适合继续自动 Git 提交（若自动提交已关闭或仓库已有后续新提交，则安全跳过，防止把旧讨论混入新提交）。

## 3. 权威 Markdown 往返校验与轮次修正

[Markdown 解析器](../../core/markdown_parser.py)处理 `schema_version: "2.0"` Frontmatter 与 `## 💬 讨论与演进历程` 下的轮次区块（`### 第 N 轮（...）`）。解析器和序列化器共享基于围栏长度和引号字符追踪的 `is_fence_start` / `is_fence_close` 逻辑，保证代码块内的标题或模板标记不会被拆分成真实讨论轮次。

在覆盖 `decisions/<id>.md` 前，`DecisionService._validate_document` 会对新生成的 Markdown 文本执行完整解析再重序列化比对，只要存在未闭合围栏或会在下次加载时结构畸变，就直接拒绝写入并保留磁盘原件。

当请求设置 `edit_latest_round: true` 时，`amend_round` 仅改写最后一个轮次中的 `user_opinion` 或 `agent_reply`（未提供的另一方保持原文，禁止重写历史更早轮次），并在 `revisions` 中保留修正前的完整快照。

## 4. 归档删除（`delete_topic`）、单议题恢复与全库回滚

- **安全归档删除**：`delete_topic` 要求精确的 `expected_version`，先将 `decisions/<id>.md` 移动至 `decisions/.archived_rollback/<id>_<6位十六进制>.md`，随后在 SQLite 事务中按 `(id, version)` 删除 `topics` 行、写入 `TOPIC_REMOVE` 审计快照（记录 `prior_rev_id` 以便追溯删前最新状态），再同步 `metadata.json` 与可选 Git 变更（仅当 `.md`、数据库或摘要仍在仓库追踪路径内时按路径隔离提交）。
- **单议题恢复（`restore_single_topic`）**：支持从指定 `rev_id` 快照（包括已被归档删除的议题）把内容还原到磁盘并写入 `RESTORE_TOPIC` 新修订；对于恢复删前状态的场景，会先沿 `TOPIC_REMOVE` 的 `prior_rev_id` 寻址到删除前真实快照。
- **全库回滚（`rollback_full`）**：接收全局 `expected_revision` 与目标 `rev_id`，将全部议题恢复到指定全局修订状态（同时把被撤销的后续新建议题 Markdown 移入 `.archived_rollback/`），并生成 `ROLLBACK` 记录。全库回滚要求先读取 `/api/git/log` 获取 `current_revision` 防止盲目覆盖他人写入（`428` / `409`）。

## 5. 一致性诊断、索引重建与热备份

[恢复管理器](../../core/recovery.py)负责比对三处状态：`decisions/*.md`、SQLite `topics` 表以及 `decisions/metadata.json`。`check_consistency` 对每份 Markdown 计算摘要并在发生 ID 大小写别名冲突、孤立数据库行、缺漏 Markdown、版本号或正文摘要漂移、以及 `metadata.json` 过期时返回具体诊断项。

- `--check-consistency` / `GET /api/recovery/check` 仅只读诊断。
- `--rebuild-index` / `POST /api/recovery/rebuild` 以 `decisions/*.md` 为事实源重筑 `topics` 与 `metadata.json`（保留历史表 `revisions` 不删库；若服务正在运行且未先解决漂移，应避免并发写入）。
- `POST /api/backup` 调用 SQLite 原生 `backup_database()` API 生成在线热备份（`.bak_YYYYMMDD_HHMMSS`），供重大重建或迁移前存档。

继续阅读：[三轴状态模型与 Agent 工作流](states-and-agent-workflow.md) · [代码地图](../code-map.md) · [核心术语表](../glossary.md)

证据状态：除特别标注外，本页基于当前源码已确认。
