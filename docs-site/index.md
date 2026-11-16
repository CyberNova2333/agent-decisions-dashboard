---
layout: home

hero:
  name: Agent Decisions Dashboard
  text: 本机决策台账与审阅工作台
  tagline: 基于 Python 3.9+ 标准库、SQLite 与零构建静态前端打造，专为个人与本机 AI 编程工具协作记录结论、批注原话与版本历史。
  actions:
    - theme: brand
      text: 起步与配置部署
      link: /docs/
    - theme: alt
      text: API 与组件参考
      link: /api-reference/
    - theme: alt
      text: 原理与源码导览
      link: /docs/architecture
    - theme: alt
      text: GitHub 仓库
      link: https://github.com/CyberNova2333/agent-decisions-dashboard

features:
  - title: 零运行时依赖
    details: 后端仅用 Python 3.9+ 标准库与 SQLite，Mermaid 12.1.0 与 Anime.js 4.5.0 全部离线打包，启动无需 Node.js 或外网 CDN。
  - title: 三轴状态与 CAS 幂等
    details: 将进展、同意结论与实现进度正交拆解；写入强制检查 expected_version 与 request_id 指纹，支持安全归档删除与快照恢复。
  - title: 可控 Agent 协作接线
    details: 提供按 topic_scope 过滤的上下文导出、严格只读的 before-task / after-write 钩子与单选 agent-question 协议卡。
---

## 能力定位与明确边界

::: info 能做到什么程度（已实现能力）
- **零依赖单机启动与外部挂载**：仅靠 Python 3.9+ 标准库与内置 `sqlite3` 运行；通过 `--config /path/to/dashboard.config.json` 即时挂载任意本地项目台账。
- **可追溯记录、审阅与回滚**：维护 `schema_version: "2.0"` Markdown 权威正文 + SQLite 历史快照（`revisions`）、ABA 防护版本号、`request_id` 幂等重放、在线热备份（`/api/backup`）与路径隔离自动 Git 提交。
- **Agent 上下文与只读校验**：提供五桶过滤上下文导出（把 `partially_accepted` 归入待决需求，剥离过期否决），配套 `before-task` / `after-write` 只读 CLI 钩子与 `agent-question` 单选交互卡片。
:::

::: warning 明确不能做什么（非目标与硬限制）
- **不做远程访问与多人协作**：HTTP 网关严格拒绝非回环地址（如 `0.0.0.0`），采用进程内线程锁，**不支持多用户登录、鉴权权限分配或多进程并发共享同一个 `decisions.db`**。
- **不自动执行代码、测试或部署任务**：`accepted`、`verified` 与 `agent-question` 选中结果仅作为台账记录，**服务端与钩子绝不代跑构建/测试、也不授予 Shell 执行权限**。
- **仅靠 `metadata.json` 或 `Markdown` 不能替代完整数据库**：`metadata.json` 只是只读导出摘要，`Markdown` 仅存最新正文；历史快照与请求幂等键仅存在于 `decisions.db`。
:::

## 决策生命周期交互图

<div class="archify-diagram-card" style="margin: 1.5rem 0; border: 1px solid var(--vp-c-border); border-radius: 12px; overflow: hidden; background: var(--vp-c-bg-soft); box-shadow: 0 4px 16px rgba(0,0,0,0.06);">
  <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 18px; background: var(--vp-c-bg-elv); border-bottom: 1px solid var(--vp-c-border); font-size: 13px;">
    <span style="font-weight: 600; color: var(--vp-c-text-1); display: flex; align-items: center; gap: 8px;">
      <span style="font-size: 16px;">📐</span> 决策状态流转交互图（支持平移 / 缩放 / 节点探查）
    </span>
    <a href="/diagrams/decision-lifecycle.html" target="_blank" rel="noreferrer" style="font-size: 12px; color: var(--vp-c-brand-1); text-decoration: none; font-weight: 500;">
      在新窗口全屏打开 ↗
    </a>
  </div>
  <iframe src="/diagrams/decision-lifecycle.html" width="100%" height="520px" frameborder="0" style="display: block; border: none;" allowfullscreen loading="lazy"></iframe>
</div>

## 快速上手演示

```sh
git clone https://github.com/CyberNova2333/agent-decisions-dashboard.git
cd agent-decisions-dashboard
./start_dashboard.sh --port 8765
# 或直接执行：python3 -m core.server --port 8765 --no-browser
```

服务仅监听本机回环地址；启动后在浏览器打开 `http://127.0.0.1:8765/dashboard.html` 即可开始新建与批阅议题。

## 文档分层导航

::: tip 按照读者需求快速跳转
- **初次体验或挂载外部项目台账**：阅读 [起步与配置部署](/docs/)，包含 `./start_dashboard.sh` / `.bat` 启动方式、`dashboard.config.json` 配置矩阵与排错；
- **逐一查阅 HTTP 端点、CLI 与标准调用示例**：进入 [API 与组件参考](/api-reference/)（三栏式交互文档）或查看完整契约页 [接口与扩展契约](/docs/contracts)；
- **阅读实现链路、源码定位或迁移旧版记录**：查阅 [原理与源码导览](/docs/architecture)，了解完整保存主流程、代码地图与迁移说明；
- **维护仓库源码、提交 PR 或查看证据审计**：参阅仓库根目录 `repo-docs/README.md` 与 `CONTRIBUTING.md`。
:::
