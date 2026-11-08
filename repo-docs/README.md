# Agent Decisions Dashboard：源码阅读指南

把用户原话、Agent 答复和当前结论保存成可追溯的本机台账。一次保存同时涉及 Markdown、SQLite 历史、摘要导出和可选 Git 提交，回执必须逐项核对。

本指南采用 Lite 包加代码地图，聚焦 **从 HTTP 保存议题到版本历史、幂等回执与只读核对**。未逐项讲解全部恢复/撤销算法、Markdown 渲染器和 UI 交互；不覆盖多人远程协作、跨进程写入协调或断电恢复保证。

## 阅读路径

| 读者目标 | 从这里开始 | 读完后获得什么 |
| --- | --- | --- |
| 第一次理解行为 | [沿一次真实操作走到底](walkthroughs/one-real-run.md) | 看懂输入、阶段交接、输出和失败边界 |
| 已了解行为，准备改代码 | [按职责寻找改动入口](code-map.md) | 找到范围内实现、测试和未覆盖区域 |
| 审核证据 | [核对两遍源码调查](references/source-evidence.md) | 区分源码事实、测试意图与未跑验证 |
| 检查讲解是否足够 | [查看读者模拟与剩余风险](references/quality-review.md) | 判断哪些结论需要补充验证 |
| 查看同步历史 | [查看指南变更](change-log.md) | 确认同步基线和本轮范围 |

## 运行与验证

Python 3.9+ 即可从源码启动，无运行时第三方依赖。Node 仅用于前端测试；Git 自动提交需要独立配置。

```sh
python -m core.server --config <目标数据项目的配置文件> --no-browser
python -m unittest discover tests
node --test tests/*.test.js
node --check web/app.js
```

启动前确认配置指向目标数据目录。同一目录仅由一个服务进程管理，使用真实台账时不要执行测试或自动重建。

这里给出的业务命令来自现有源码或脚本；本轮只执行文档结构校验与站点构建，没有运行业务测试、安装钩子、停止服务或部署。测试文件的存在表示可检查的验证意图，不表示本轮通过。

## 文档站

文档站采用 VitePress 默认主题，依赖与业务项目分开安装。默认输出 `docs-site/.vitepress/dist/`；独立核验可在构建命令后加 `-- --outDir <仓库外绝对目录>`。指南正文只维护 `repo-docs/`，站点通过 include 读取；网页中的仓库源码链接显示为精确文件路径，不复制源码或本机资源。

```sh
pnpm --dir docs-site install --frozen-lockfile
pnpm --dir docs-site run docs:dev -- --host 127.0.0.1
pnpm --dir docs-site run docs:build
```

独立网页构建会把文档目录之外的仓库链接显示为精确文件路径，避免产生失效跳转；原始 Markdown 仍保留可核对的源码链接。站点只发布指南，源码和本机资源不会随文档打包。

证据状态：除特别标注外，本页基于当前源码已确认。
