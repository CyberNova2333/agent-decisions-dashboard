# 源码证据审计

这是固定审计记录，记录 2026-10-29 的两遍调查；行为解释由主流程页承载，源码导航由代码地图承载。

## 遍历记录

| 遍历 | 实际检查 | 得到的依据 |
| --- | --- | --- |
| Pass 1 | 仓库目录、Git 状态、父级及 root AGENTS/CLAUDE、README、`pyproject.toml`、`core/server.py` 和原有 `docs/agent-workflow.md` 入口 | 确定真实入口、运行命令及现存文档；README 只作线索 |
| Pass 2 | `core/decision_service.py` 的请求指纹/版本/分阶段回执、`core/agent_hooks.py`，以及 `tests/test_decision_service.py`、`tests/test_usability_regressions.py` | 追踪主路径的输入、输出与失败分支，并对照测试断言 |

## 覆盖与排除

覆盖：从 HTTP 保存议题到版本历史、幂等回执与只读核对。未逐项讲解全部恢复/撤销算法、Markdown 渲染器和 UI 交互；不覆盖多人远程协作、跨进程写入协调或断电恢复保证。
调查时已有 README 与 `web/` 未提交 UI 改动，以及未跟踪数据库和前端资源。本轮保留这些内容，未将它们视为已提交、已验收或生产状态。

## 声明与证据

| Claim | Evidence | Confidence | Caveat | Used by |
| --- | --- | --- | --- | --- |
| 保存不能覆盖旧版本，重放绑定原请求 | [保存服务](../../core/decision_service.py) 搜索 `req_hash`、`expected_version`；[回归](../../tests/test_decision_service.py) | 已确认 | 未在本轮运行测试 | 主流程 Step 2–3 |
| 成功保存与 Git 提交是不同阶段 | [服务回执](../../core/decision_service.py) 搜索 `save_status`、`git_status` | 已确认 | Git 失败不代表讨论未落盘 | 主流程 Step 4 |
| 只读检查不验证业务代码实现 | [核对钩子](../../core/agent_hooks.py) 搜索 `after_write` | 已确认 | 不用于删除/全库恢复确认 | 主流程 Step 4 |
| 只同意部分范围需要保留原话 | [使用回归](../../tests/test_usability_regressions.py) 搜索 `partial_acceptance` | 已确认 | 服务不理解文本语义 | 主流程 Step 2 |

## 证伪检查与读者下一问

证伪检查：如果同 ID 改 payload 能再保存、旧版本覆盖当前 Markdown，或 `after-write` 接受过期回执，这份解释就失效。应复查对应断言和处理代码，而非只看成功页面。

读者下一问：恢复旧快照后怎样再次保存？需单独追踪 `core/recovery.py` 及恢复回归，本指南不宣称已完整解释恢复协议。

## 验证边界

本轮执行 `validate_repo_docs.py` 和 MkDocs 构建，退出码及完整输出保存在独立维护报告中；不将静态阅读当作业务测试通过。没有部署、生产验收或历史改写。
所有 `../../` 源码链接按当前磁盘核对；独立站点没有这些仓库文件，MkDocs 对此记 INFO，站内链接仍正常检查。未解析、展示或引用真实凭据和运行时数据库内容；现有未提交文件仅作本地摘要保全。
