# Agent Decisions Dashboard：源码阅读指南

把用户原话、Agent 答复和当前结论保存成可追溯的本机台账。一次写入同时协调 Markdown 权威文件、SQLite 版本历史与幂等回执、摘要导出和可选 Git 提交，响应里的分阶段状态必须逐项核对。

本指南采用 Standard 包，覆盖 **从 HTTP 保存、幂等与版本恢复，到三轴状态契约与只读 Agent 钩子的核心主链路**；不覆盖多人远程协作、跨进程写入协调、自动任务调度或断电恢复保证。

## 阅读路径

| 读者目标 | 从这里开始 | 读完后获得什么 |
| --- | --- | --- |
| 第一次理解主链路 | [沿一次真实操作走到底](walkthroughs/one-real-run.md) | 看懂读取版本、幂等保存、分阶段回执与只读核对的完整交接 |
| 按职责定位源码与测试 | [按职责寻找改动入口](code-map.md) | 快速找到 `core/`、`web/` 与 `tests/` 的责任归属与未覆盖边界 |
| 深入持久化、并发锁与归档恢复 | [保存、幂等、归档与恢复机制](modules/save-idempotency-and-recovery.md) | 掌握 CAS 版本序列、请求指纹重放、轮次修正、`delete_topic` 归档与索引重建 |
| 理解三轴状态与 Agent 接线 | [三轴状态模型与 Agent 工作流](modules/states-and-agent-workflow.md) | 厘清工作流/结论/实现隔离、旧别名兼容、`agent-question` 围栏与只读钩子 |
| 核对核心术语与数据口径 | [核心术语表](glossary.md) | 统一 `request_id`、`expected_version`、`topic_scope` 等关键概念边界 |
| 审查源码依据与可信度 | [源码证据审计](references/source-evidence.md) | 区分源码已确认事实、回归测试覆盖与运行环境前置条件 |
| 检查讲解是否足够 | [阅读质量审计](references/quality-review.md) | 核对读者心智模型问答、可证伪条件与剩余风险 |
| 查看文档同步基线 | [指南变更记录](change-log.md) | 确认 `Synced through` 提交基线与本轮文档重构范围 |

## 运行与验证

Python 3.9 及以上即可直接从源码启动，后端零第三方运行时依赖；Node.js 仅用于运行前端 JS 单元测试与语法检查，Git 仅在启用自动提交时使用。

```sh
python3 -m core.server --config dashboard.config.json --no-browser
python3 -m unittest discover tests
node --test tests/*.test.js
node --check web/app.js && node --check web/markdown.js && node --check web/diagrams.js
```

启动前确认配置指向目标数据目录；同一数据目录在同一时刻只应由单个服务进程管理。禁止对生产使用中的 `decisions.db` 执行测试或自动重建。

## 面向对象文档站

面向上手部署、HTTP 接口契约与双语浏览的文档位于 `docs-site/`（VitePress 静态站点，与 Python 业务运行环境依赖分离），并重用本指南的走读与设计约束：

```sh
pnpm --dir docs-site install --frozen-lockfile
pnpm --dir docs-site run docs:dev -- --host 127.0.0.1
pnpm --dir docs-site run docs:build
```

证据状态：除特别标注外，本页基于当前源码已确认。
