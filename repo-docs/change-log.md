# 指南变更记录

## 2026-10-29：建立主流程指南并对齐文档入口

- 触发：用户授权 widened docs sync；同步决策为 `foreground patch`，在共享工作树完成指定文档层。
- 建立阅读路径、主流程、代码地图、两遍源码证据与阅读质量审计；范围限定为从 HTTP 保存议题到版本历史、幂等回执与只读核对。
- 验证：`validate_repo_docs.py --lite` 退出 0。

Synced through b732e7c9c6fd23d696efb852c6cf174f9768881b

## 界面与配套实现整理（2026-10-29）

整理看板色彩、排版、筛选区块和响应式布局，接入本地 Anime.js 与字体资源并保留许可。

Synced through af17fede87aaa7a4b6c42e3bec9b6d443e1d6382；本节对应随后提交的工作树。

## 工作台交互重构与议题归档能力（2026-11-11）

重构前端为双栏主从工作台、三段式详情驾驶舱与底部可折叠拍板栏，补齐更正最近一轮、提案编辑、实现核验、参数化上下文提取、一致性诊断热备份及全界面自绘 SVG 图标体系；后端新增 `DecisionService.delete_topic` 与 `POST /api/topic/<id>/delete` 安全归档及撤销恢复接口。

验证：`python -m unittest discover tests`（227 项通过）、`node --test tests/*.test.js`（12 项通过）、`node --check web/app.js` 与 `git diff --check` 通过。

Synced through df389872dba882a973d3c3dc2245acb4a33186a7；本节对应随后提交的工作树。

## 全库文档体系重置与 Standard 模式升级（2026-11-15）

- 清理 `docs-site/` 中的通用模板占位符与虚假配置示例，确立 Tier B 三阶段递进文档站结构（起步与配置部署 / 接口与扩展契约 / 原理与源码导览与决策迁移），保留现有质感主题与交互式 `/diagrams/decision-lifecycle.html` 生命周期图。
- 将原本分散于 `docs/agent-workflow.md` 的 Agent 操作规程与重试示例迁入文档站契约页及 `repo-docs/modules/states-and-agent-workflow.md`，同步删除冗余 `docs/agent-workflow.md` 并更新 `AGENTS.md` 入口引用。
- 将 `repo-docs/` 升级为 Standard 结构，补全 `modules/` 两篇深潜文档与 `glossary.md`，并更新 `code-map.md` 覆盖 `topic_scope`、`delete_topic`、`agent_context.py` 与 `recovery.py`。
- 校准 `README.md` 与 `README.en.md` 为简洁清晰的 6 段式导航总入口，清理 `DESIGN.md` 中的本机 Windows 失效路径并修正 `meta.json` 不存在的启动脚本名。
- 验证边界：运行 `validate_repo_docs.py`（Standard 模式，无 `--lite`）、`pnpm --dir docs-site run docs:build`、227 项 Python 单元测试与 12 项 Node 测试；真机浏览器手工回归与 Windows `.bat` 实测仍以对应环境实操为准。

Synced through 3ee46d3be2b1f0a1f51114b779b2b9abe9599459
