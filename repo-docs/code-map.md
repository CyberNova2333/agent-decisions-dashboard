# 代码地图

先读[一次真实操作的阶段交接](walkthroughs/one-real-run.md)，再按这里的职责定位。覆盖范围为 从 HTTP 保存议题到版本历史、幂等回执与只读核对；这不是全仓库架构清单。

| 路径 | 职责 | 关键代码 | 与主流程的关系 |
| --- | --- | --- | --- |
| `core/` | 服务、业务保存、存储与只读检查 | [HTTP 入口](../core/server.py)、`DecisionService.save_topic`、[回执检查](../core/agent_hooks.py) | 接收请求，校验版本，协调保存并核对 |
| `core/` 中的存储支持 | Markdown、SQLite 历史、锁与 Git | [数据库](../core/db.py)、[解析器](../core/markdown_parser.py)、[项目锁](../core/locking.py)、[Git 阶段](../core/git_engine.py) | 当前内容与历史/提交各自有状态 |
| `web/` | 静态浏览器交互 | [页面请求与草稿](../web/app.js)、[选项解析](../web/agent-question.js)、`dashboard.html` | 页面读版本、提交讨论、显示回执 |
| `tests/` | 测试支持与回归 | [业务保存测试](../tests/test_decision_service.py)、[使用回归](../tests/test_usability_regressions.py)、[Agent 钩子测试](../tests/test_agent_hooks.py) | 对照主路径的成功与冲突分支 |

## `core/`

| 重要代码 | 功能 | 关键符号 | 调用方 / 使用方 |
| --- | --- | --- | --- |
| `server.py` | HTTP 读取/保存及错误边界 | `do_POST` | 浏览器和 Agent HTTP 客户端 |
| `decision_service.py` / `db.py` | 协调保存、历史和请求指纹 | `DecisionService.save_topic` | HTTP 处理；decision_service 回归 |
| `agent_hooks.py` | 核对目标、一致性和原始回执 | `before_task` / `after_write` | Agent 宿主只读接线 |

## `web/`

| 重要代码 | 功能 | 关键符号 | 调用方 / 使用方 |
| --- | --- | --- | --- |
| `app.js` / `dashboard.html` | 显示讨论与提交保存 | 本页未逐函数展开 UI | 浏览器；JS 与独立台账交互检查 |
| `agent-question.js` | 选项围栏及草稿协议 | `agent-question` | 前端；agent-question.test.js |

## `tests/`

| 重要代码 | 功能 | 关键符号 | 调用方 / 使用方 |
| --- | --- | --- | --- |
| `test_decision_service.py` | 保存、旧版本冲突与请求重放 | `test_optimistic_conflict_and_idempotency_in_service` | unittest |
| `test_usability_regressions.py` | 部分同意、原话与更正轮次 | `test_partial_acceptance_roundtrips_without_turning_whole_proposal_into_rule` | unittest |

## 修改入口与验证

变更请求或回执契约先检查 `core/server.py` 与 `core/decision_service.py`，再对照保存和 Agent 钩子测试。变更讨论轮次检查 `core/markdown_parser.py` 与使用回归；变更交互检查 `web/app.js`，同时复核 `web/agent-question.js` 的选项草稿和提交协议。

`core/config.py` 决定配置路径，`core/agent_context.py` 决定导出的结论分类；恢复维护另从 `core/recovery.py` 和原有 Agent 操作指南进入。本页仅索引这些相邻责任，不替代其专门验证。

## 覆盖范围

未逐项讲解全部恢复/撤销算法、Markdown 渲染器和 UI 交互；不覆盖多人远程协作、跨进程写入协调或断电恢复保证。

源码链接指向仓库文件。独立文档站不携带这些文件；可按表中的精确路径在克隆中查找。需要确认哪些代码已经逐段核对，查看[证据覆盖记录](references/source-evidence.md)。

证据状态：除特别标注外，本页基于当前源码已确认。
