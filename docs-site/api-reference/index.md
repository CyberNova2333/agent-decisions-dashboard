---
layout: page
sidebar: false
title: API 与组件参考
description: Agent Decisions Dashboard 全部 HTTP REST 端点、CAS 写入约束、只读 CLI 钩子与 agent-question 协议参考（APIFox 风格交互视图）。
---

<script setup lang="ts">
import { apiSpecZh } from '../.vitepress/data/api-spec'
</script>

<ApiExplorer :spec="apiSpecZh">

### 服务状态与一致性预检 (`GET /api/status`) {#get-api-status}

返回 `project_name`、绝对路径、`git_available` 与 `consistency` 摘要，仅监听回环地址。

### 议题列表与治理摘要 (`GET /api/topics`) {#get-api-topics}

返回受 `topic_scope` 过滤的议题清单、`settled_decisions`、`open_questions` 与三轴状态。

### 单议题完整详情与快照 (`GET /api/topic/{id}`) {#get-api-topic-detail}

返回单议题完整正文、CAS `version`、讨论轮次与快照 `rev_id`。

### 五桶 Agent 上下文导出 (`GET /api/agent/context`) {#get-api-agent-context}

按 `module`/`path`/`topic_id` 导出 `active_decisions`、`rejected_proposals`、`pending_requirements`、`deferred_topics` 与 `superseded_topics`。

### 新建议题与首版快照 (`POST /api/topic/create`) {#post-api-topic-create}

校验可移植 ID 与围栏往返，创建 Markdown 与首版 SQLite 快照。

### 追加讨论轮次 / 更正最近一轮 (`POST /api/topic/{id}/save`) {#post-api-topic-save}

基于 `expected_version` 与 `request_id` 幂等落盘，支持 `edit_latest_round`。

### 单议题归档删除 / 快照恢复 (`POST /api/topic/{id}/delete`) {#post-api-topic-delete-restore}

支持将 Markdown 归档到 `.archived_rollback/` 及按 `rev_id` 无损还原。

### 登记实现核验记录 (`POST /api/topic/{id}/verify`) {#post-api-topic-verify}

仅登记 `impl_commit` 与 `test_summary` 证据，不自动运行测试。

### 热备份与全库快照回滚 (`POST /api/backup`) {#post-api-backup-rollback}

在线生成 SQLite `.bak` 热备份、按 `expected_revision` 全库回滚以及锁内重建索引。

### 只读 Agent 钩子命令行 (`core.agent_hooks`) {#cli-agent-hooks}

提供 `before-task` 与 `after-write` 严格只读验证命令。

### `agent-question` 单选交互围栏 (`agent-question`) {#protocol-agent-question}

嵌入最新一轮 `new_agent_reply` 的 2–8 项非授权选项协议卡。

</ApiExplorer>
