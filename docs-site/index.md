---
layout: home
repoGuideSource: "repo-docs/README.md"

hero:
  name: Agent Decisions Dashboard
  text: 本机决策记录与追溯台账
  tagline: 把用户原话、Agent 答复与最终结论归档为可审计的本机 SQLite 历史与可验证 Git 提交。
  actions:
    - theme: brand
      text: 开启文档阅读
      link: /walkthroughs/one-real-run
    - theme: alt
      text: 架构代码地图
      link: /code-map
    - theme: alt
      text: GitHub 仓库
      link: https://github.com/CyberNova2333/agent-decisions-dashboard

features:
  - title: 全链路决策台账
    details: 将人机多轮对话输入、模型回复、中间决策断言与最终共识同步写入结构化 SQLite 历史与 Markdown 归档。
  - title: 幂等回执与只读核验
    details: HTTP 保存请求支持幂等凭证回执，多端审计只读核对，确保记录真实可信、不可篡改。
  - title: 可选 Git 自动化提交
    details: 自动协同本地 Git 仓库将重要架构与开发决策落盘签名，杜绝事后凭空臆测历史上下文。
---

## 这是什么

**Agent Decisions Dashboard** 是一个运行在本机的决策记录与审计工具。在多 Agent 协同编程或深度研发过程中，它解决的是“复杂对话结论如何长期沉淀为可信依据”的难题。

系统通过本地 HTTP 接口接收 Agent 钩子与外部调用，把用户原始需求、Agent 决策推理与最终代码修改记录结构化存入 SQLite，并同步生成人类友好的 Markdown 纪要与 Git 提交，形成完整的双向验证证据链。


## 架构全景

<div class="archify-diagram-card" style="margin: 1.5rem 0; border: 1px solid var(--vp-c-border); border-radius: 12px; overflow: hidden; background: var(--vp-c-bg-soft); box-shadow: 0 4px 16px rgba(0,0,0,0.06);">
  <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 18px; background: var(--vp-c-bg-elv); border-bottom: 1px solid var(--vp-c-border); font-size: 13px;">
    <span style="font-weight: 600; color: var(--vp-c-text-1); display: flex; align-items: center; gap: 8px;">
      <span style="font-size: 16px;">📐</span> 决策流转全生命周期（交互式架构图表，支持平移 / 缩放 / 探查）
    </span>
    <a href="/diagrams/decision-lifecycle.html" target="_blank" rel="noreferrer" style="font-size: 12px; color: var(--vp-c-brand-1); text-decoration: none; font-weight: 500;">
      在新窗口全屏打开 ↗
    </a>
  </div>
  <iframe src="/diagrams/decision-lifecycle.html" width="100%" height="520px" frameborder="0" style="display: block; border: none;" allowfullscreen loading="lazy"></iframe>
</div>

## 怎么用 / 快速上手

### 1. 启动本地台账服务

Python 3.9+ 即可直接从源码运行，无第三方运行时依赖：

```bash
# 启动本地决策台账服务（默认监听本地端口）
python -m core.server
```

### 2. 通过 API 记录决策

向本地服务发送一条决策记录：

```bash
curl -X POST http://127.0.0.1:8765/api/decisions \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "代码托管平台与双端同步规范",
    "prompt": "将主要代码托管平台切换为 GitHub 个人主开发命名空间",
    "decision": "默认使用 GitHub noreply 邮箱及独立签名私钥，严禁凭证混用与泄露",
    "git_commit": true
  }'
```

服务将返回包含全局唯一决策 ID 与 SHA-256 校验和的幂等回执。

## 分层阅读与快速跳转

::: tip 按读者角色快速检索
- **初次接触 / 快速理解**：从[一条真实主流程](/walkthroughs/one-real-run)读起，顺着一次 HTTP 保存走完入库、Markdown 生成与回执校验全流程。
- **架构设计 / 模块定位**：从[代码地图](/code-map)进入，按职责查看服务入口、SQLite 存储驱动、Markdown 导出器与测试分布。
- **审计复核 / 核心贡献**：从[源码证据](/references/source-evidence)核对真实测试断言与实现细节，查阅[阅读质量审计](/references/quality-review)了解当前边界与剩余风险。
:::

---

## 完整项目指南概览

<!--@include: ../repo-docs/README.md-->
