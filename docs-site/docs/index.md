---
title: 起步与配置部署
description: 确认产品定位、运行模式、CLI 参数、dashboard.config.json 配置矩阵与部署排错指南
---

# 1. 起步与配置部署

本阶段帮助你确认工具边界、按平台或项目目录启动服务，并掌握完整配置与常见部署排错方式。

## 定位与适用边界

- **零第三方运行时**：后端仅使用 Python 3.9+ 标准库与内置 `sqlite3`；前端为静态 HTML/CSS/Vanilla JS，离线捆绑 `web/vendor/`（Mermaid 12.1.0、Anime.js 4.5.0、IBM Plex Sans 字体），无需安装 npm 依赖或连接外部 CDN。
- **可选开发工具**：`Node.js` 仅用于执行 `tests/*.test.js` 与 `node --check` 语法校验；`pnpm` 仅用于构建 `docs-site/` 静态文档站。
- **单机单进程约束**：服务强制仅监听本机回环地址（`127.0.0.1`、`localhost` 或回环 IPv4/IPv6）；使用进程内 `threading.RLock`，**同一 `database_path` 在同一时刻只能由单个服务进程管理**。
- **明确排除项**：不提供远端账号认证、团队多人并发锁定、后台任务排期或自动执行 Agent；离线 CLI 维护操作（如 `--rebuild-index`）应先停止活跃服务。

## 运行模式与 CLI 入口

| 模式 / 平台 | 启动命令 | 适用场景 |
|---|---|---|
| Linux / macOS 快速启动 | `./start_dashboard.sh --port 8765` | 脚本自动切到仓库目录并透传全部参数 |
| Windows 快速启动 | `start_dashboard.bat --port 8765` | 支持直接双击或在终端执行并透传参数 |
| Python 模块直接启动 | `python3 -m core.server --port 8765 --no-browser` | 后台/无浏览器打开、自定义端口或集成到脚本 |
| 安装包命令入口 | `agent-dashboard --config /path/to/dashboard.config.json` | 在虚拟环境执行 `pip install -e .` 后可用（对应 `pyproject.toml` 中的 `core.server:main`） |
| 挂载外部数据目录 | `python3 -m core.server --config /path/to/project/dashboard.config.json` | 无需复制服务源码进业务项目；相对路径自动以配置目录为基准 |
| 一致性只读检查 | `python3 -m core.server --config ... --check-consistency` | 比对 Markdown 摘要、`topics` 表与 `metadata.json` 后退出 |
| 重建 SQLite 索引 | `python3 -m core.server --config ... --rebuild-index` | 以 `decisions/*.md` 为事实源重筑 `topics` 与摘要后退出（先停服） |
| 导出 Agent 上下文 | `python3 -m core.server --config ... --export-agent-context 存储层` | 按模块过滤输出五桶 Markdown 治理摘要后退出 |

### `core.server` 命令行参数一览

- `--config <path>`：显式指定配置文件路径；若传入不存在的文件路径，服务直接以 `FileNotFoundError` 中止而不会回退到默认演示目录。
- `--host <addr>`：覆盖监听主机；必须是 `localhost` 或合法回环 IP（否则拒绝启动）。
- `--port <int>`：覆盖监听端口（默认 `8765`）。
- `--no-browser`：禁止启动时自动调用 `webbrowser.open(...)`。
- `--check-consistency` / `--rebuild-index` / `--export-agent-context <模块>`：维护与导出子模式，执行完毕即退出，不启动 HTTP 监听。

## 配置矩阵与优先级

配置读取顺序遵循严格优先级（高优先级覆盖低优先级）：

`CLI 命令行参数 (--host / --port)` > `环境变量 (AGENT_DASHBOARD_HOST / AGENT_DASHBOARD_PORT)` > `dashboard.config.json` > `core/config.py 内置 DEFAULT_CONFIG`

> 注意：加载配置时 `loaded_data.update(user_data)` 采用顶层字段合并；如果自定义 `git_commit`、`categories` 或 `topic_scope`，请保持各自内部字段结构完整。

| 配置项 / 环境变量 | 默认值 | 类型 | 作用与路径基准 |
|---|---|---|---|
| `host` / `AGENT_DASHBOARD_HOST` | `"127.0.0.1"` | string | 绑定监听地址，仅接受回环地址 |
| `port` / `AGENT_DASHBOARD_PORT` | `8765` | int | 绑定端口；非数字环境变量会被忽略并回落到配置/默认值 |
| `project_name` | `"Agent Decisions Dashboard"` | string | 工作台顶部标题与状态接口返回的项目名 |
| `project_subtitle` | `"Human-Agent Collaborative ..."` | string | 副标题说明 |
| `brand_logo` / `brand_icon` | `"AD"` / `"⚖️"` | string | 前端品牌标识与图标 |
| `decisions_dir` | `"decisions"` | string | 权威 Markdown 目录；相对路径以配置文件所在目录为基准解析 |
| `database_path` | `"decisions.db"` | string | SQLite 台账与快照历史库路径；相对配置文件目录解析 |
| `metadata_json_path` | `"decisions/metadata.json"` | string | 只读概览摘要导出文件路径；相对配置文件目录解析 |
| `doc_data_json_path` | `"doc_data.json"` | string | 保留字段（兼容旧接口定义，当前不作为权威写入或恢复入口） |
| `topic_scope.active_topic_ids` | `null` | `string[] \| null` | 为 `null` 时展示全部议题；设为数组后仅在列表/概览/Agent 上下文中展示活跃 ID（历史议题仍可按原 ID 查详情） |
| `git_commit.enabled` | `true` | bool | 写操作后是否尝试自动创建路径隔离 Git 提交 |
| `git_commit.commit_prefix` | `"feat(decision)"` | string | 自动提交消息前缀 |
| `git_commit.co_author` | `""` | string | 可选附带的 `Co-authored-by` 尾注（不影响手工 `git commit`） |
| `git_commit.include_user_opinion` / `include_agent_reply` | `true` / `true` | bool | 是否将本轮双方讨论摘要写入提交信息正文 |
| `categories.objects` / `functions` | 默认 5 对象 / 5 功能 | `string[]` | 看板左侧对象与功能维度筛选标签列表 |
| `lifecycle_states` | 5 项对象数组 | array | 定义 `decided`、`discussing`、`pending`、`deferred`、`superseded` 的名称、徽章与描述 |

## 部署与运行排错 FAQ

**1. 绑定 `0.0.0.0` 或局域网 IP 启动失败怎么办？**

出于本地凭据与安全边界设计，`core/server.py` 的 `is_loopback_host` 严格拒绝任何非回环主机地址（如 `0.0.0.0`）。如需在本机其它端口暴露，请保持 `127.0.0.1` 并仅调整 `--port`。

**2. 只看到 `metadata.json` 且议题列表为空，或启动日志警告 `[WARN] 只有 metadata.json 摘要，未找到权威 Markdown`？**

`decisions/*.md` 才是权威议题正文，服务不会把摘要缓存 `metadata.json` 当作内容源导入。请从原目录或 Git 历史恢复缺失的 `.md` 文件后再重启，或避免在新建空目录中混入孤立的 `metadata.json`。

**3. 提示数据不一致（一致性检查报错）时如何安全处理？**

切勿在未确认差异的情况下直接删除 `decisions.db`。应先停止写操作，调用 `POST /api/backup` 生成在线热备份（或在停服后备份 `.db`），对照 `GET /api/recovery/check` 报告的漂移原因（外部改写了 `.md` 或版本错位），再视情况从界面查看快照或以停服模式执行 `--rebuild-index`。

**4. Git 提示 `skipped_unrelated_staged` 或 `no_identity` 但页面仍显示已保存？**

台账写入与 Git 提交相互独立。发现暂存区有无关代码、未配置 `user.name`/`user.email` 或存在 `.git/index.lock` 时，Git 引擎会安全跳过而不回滚已写入磁盘的 Markdown 和 SQLite 记录；清理暂存区或补齐局部 Git 身份即可恢复后续提交。

**5. 修改前端代码或切换外部配置后，浏览器页面仍是旧内容？**

后端配置和 Python 模块改动需要重启 `core.server` 进程；仅修改 `web/` 静态资源后刷新浏览器即可，刷新前请先保存编辑器中尚未提交的批注草稿（也可依赖页面每题按 `localStorage` 缓存的防丢失草稿提示）。
