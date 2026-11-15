# 源码证据审计

本页记录基于当前 `HEAD` 源码树的两遍核查依据与验证边界；行为步骤由[主流程走读](../walkthroughs/one-real-run.md)承载，目录与模块索引由[代码地图](../code-map.md)承载。

## 遍历记录

| 遍历 | 实际检查 | 得到的依据 |
| --- | --- | --- |
| Pass 1 | 仓库目录、工作区 `AGENTS.md` / `CLAUDE.md`、`pyproject.toml`、`dashboard.config.json`、`start_dashboard.*`、`core/server.py`、`core/config.py` 与旧文档 | 核实纯 Python 标准库零第三方运行时依赖的真实启动入口、端口与配置优先级，识别出旧 `docs-site` 中存在模板残留 |
| Pass 2 | `core/decision_service.py`（`save_topic`、`edit_latest_round`、`delete_topic`、`restore_single_topic`、`rollback_full`）、`core/db.py`、`core/contracts.py`、`core/recovery.py`、`core/agent_hooks.py`、`core/agent_context.py`、`web/agent-question.js` 与 `tests/*.py`、`tests/*.test.js` | 确认三轴状态、ABA 版本序列、SHA-256 请求指纹幂等、安全归档删除、只读钩子校验规则及前后端安全边界 |

## 覆盖与排除

覆盖：HTTP 回环服务入口、三轴状态模型与 `topic_scope`、CAS 乐观锁与 `request_id` 重放、`edit_latest_round` / `delete_topic` / 恢复与重建流水线、只读 Agent 钩子及静态前端 `agent-question` 与 Mermaid/Markdown 防护。未展开逐行 CSS 样式 Token 细节（见根目录 `DESIGN.md`）与仓库维护守卫脚本（`tools/repo_maintenance_guard.py`）；不包含跨进程协调、远程身份认证或断电写落盘保证。

## 声明与证据

| Claim | Evidence | Confidence | Caveat | Used by |
| --- | --- | --- | --- | --- |
| 过期版本不能覆盖新记录，同键同参幂等重放、异参报错 `409` | [保存服务](../../core/decision_service.py) 搜索 `req_hash` / `expected_version`、[数据库](../../core/db.py) `topic_version_seq`、[业务测试](../../tests/test_decision_service.py) | 已确认 | 需在同一服务进程内且通过 HTTP 或 `DecisionService` 调用 | 主流程 Step 2–3、保存与恢复模块 |
| 台账保存、摘要导出与可选 Git 提交分阶段独立报告 | [保存服务](../../core/decision_service.py) 搜索 `save_status` / `export_status` / `git_status`、[Git 引擎](../../core/git_engine.py) | 已确认 | Git 提交失败或跳过不影响台账已保存事实 | 主流程 Step 4 |
| `delete_topic` 归档 Markdown 并保留 `TOPIC_REMOVE` 审计与删前快照引用 | [保存服务](../../core/decision_service.py) `delete_topic`、[撤销回归](../../tests/test_undo_regressions.py) | 已确认 | `after-write` 钩子不用于确认删除或全库回滚 | 主流程 Step 4、保存与恢复模块 |
| 只读钩子校验数据目录、一致性与版本匹配，绝不自动写入或跑测试 | [只读钩子](../../core/agent_hooks.py) `preflight` / `before_task` / `after_write`、[钩子测试](../../tests/test_agent_hooks.py) | 已确认 | 需人工或宿主显式配置并传入目标 `--config` | 主流程 Step 1/4、状态与工作流模块 |
| 局部同意要求非空用户原话，且三轴相互独立、`agent-question` 不自动改状态 | [状态契约](../../core/contracts.py)、[选项模块](../../web/agent-question.js)、[使用回归](../../tests/test_usability_regressions.py)、[前端选项测试](../../tests/agent-question.test.js) | 已确认 | 服务只验证非空文本与围栏格式，不裁决自然语言语义 | 主流程 Step 2、状态与工作流模块 |

## 证伪检查与读者下一问

证伪检查：若同 `request_id` 修改载荷仍能写入、过期 `expected_version` 覆盖现有 Markdown、`after-write` 接受过期版本号，或未声明 `new_user_opinion` 即成功首次切换至 `partially_accepted`，则本指南对应解释失效，应立即回查对应实现与回归测试。

读者下一问：若外部人工直接编辑了 `decisions/*.md` 导致 `check_consistency` 报摘要漂移，应先备份当前 `decisions.db`（`POST /api/backup`），对照 Markdown 与 SQLite `revisions` 历史差异后再决定是否执行 `--rebuild-index` 或单议题恢复；本指南不将自动重建视为无损合并工具。

## 验证边界

本轮同步期间实跑了完整 Python 单元测试（`python3 -m unittest discover tests`：227 项通过）、Node 前端测试（`node --test tests/*.test.js`：12 项通过）、前端脚本语法检查（`node --check`）、文档结构脚本校验（`validate_repo_docs.py`）与 VitePress 文档站静态构建（`pnpm --dir docs-site run docs:build`）。真机浏览器复杂手动交互及 Windows 批处理路径未在本 Linux 环境中完整复测。

证据状态：除特别标注外，本页基于当前源码已确认。
