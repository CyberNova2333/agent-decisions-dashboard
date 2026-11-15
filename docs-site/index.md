---
layout: home

hero:
  name: Agent Decisions Dashboard
  text: 本机决策台账与审阅工作台
  tagline: 基于 Python 3.9+ 标准库、SQLite 与零构建静态前端打造，专为个人与本机 AI 编程工具协作记录结论、批注原话与版本历史。
  actions:
    - theme: brand
      text: 1. 起步与配置部署
      link: /docs/
    - theme: alt
      text: 2. 接口与扩展契约
      link: /docs/contracts
    - theme: alt
      text: 3. 原理与源码导览
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

## 按身份/目标快速入口

| 读者身份 / 目标 | 推荐从这里开始 | 说明 |
|---|---|---|
| 初次体验或挂载外部项目台账 | [Stage 1 · 起步与配置部署](/docs/) | 包含 `./start_dashboard.sh` / `.bat` 启动方式、`dashboard.config.json` 配置矩阵与排错 |
| 集成 HTTP API、Agent 钩子或选型评估 | [Stage 2 · 接口与扩展契约](/docs/contracts) | 汇总回环安全边界、REST 端点、三轴状态约束、`agent-question` 与 `before-task` / `after-write` |
| 阅读实现链路、源码定位或迁移旧版记录 | [Stage 3 · 原理与源码导览（含决策迁移）](/docs/architecture) | 嵌入完整保存主流程走读、目录代码地图、协议迁移及可证伪验证方法 |
| 维护仓库源码、提交 PR 或查看证据审计 | 仓库根目录 `repo-docs/README.md` 与 `CONTRIBUTING.md` | 本仓库 Standard 源码指南与双遍源码调查记录（随仓库源码维护，不单独打包） |

## 决策生命周期交互图

<div class="diagram-card" style="margin: 1.5rem 0; border: 1px solid var(--vp-c-border); border-radius: 12px; overflow: hidden; background: var(--vp-c-bg-soft); box-shadow: 0 4px 16px rgba(0,0,0,0.06);">
  <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 18px; background: var(--vp-c-bg-elv); border-bottom: 1px solid var(--vp-c-border); font-size: 13px;">
    <span style="font-weight: 600; color: var(--vp-c-text-1); display: flex; align-items: center; gap: 8px;">
      决策状态流转交互图（支持平移 / 缩放 / 节点探查）
    </span>
    <a href="/diagrams/decision-lifecycle.html" target="_blank" rel="noreferrer" style="font-size: 12px; color: var(--vp-c-brand-1); text-decoration: none; font-weight: 500;">
      在新窗口全屏打开 ↗
    </a>
  </div>
  <iframe src="/diagrams/decision-lifecycle.html" width="100%" height="520px" frameborder="0" style="display: block; border: none;" allowfullscreen loading="lazy"></iframe>
</div>

## 最简启动路径

```sh
git clone https://github.com/CyberNova2333/agent-decisions-dashboard.git
cd agent-decisions-dashboard
./start_dashboard.sh --port 8765
# 或直接执行：python3 -m core.server --port 8765 --no-browser
```

服务仅监听本机回环地址；启动后在浏览器打开 `http://127.0.0.1:8765/dashboard.html` 即可开始新建与批阅议题。
