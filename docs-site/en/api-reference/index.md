---
layout: page
sidebar: false
title: API & Component Reference
description: Apifox-style interactive explorer for all Agent Decisions Dashboard HTTP endpoints, CAS writes, recovery routes, and read-only CLI hooks.
---

<script setup lang="ts">
import { apiSpecEn } from '../../.vitepress/data/api-spec'
</script>

<ApiExplorer :spec="apiSpecEn">

### Server Status & Consistency Preflight (`GET /api/status`) {#get-api-status}

Returns canonical paths, Git availability, and consistency checks on loopback.

### Filtered Topic Catalog (`GET /api/topics`) {#get-api-topics}

Returns `topic_scope`-filtered topics, settled decisions, and open questions.

### Single Topic Detail & Revisions (`GET /api/topic/{id}`) {#get-api-topic-detail}

Returns full Markdown content, CAS `version`, rounds, and revision snapshots.

### Five-Bucket Agent Context Export (`GET /api/agent/context`) {#get-api-agent-context}

Exports structured `active_decisions`, `rejected_proposals`, `pending_requirements`, `deferred_topics`, and `superseded_topics`.

### Create or CAS-Save Topic Round (`POST /api/topic/{id}/save`) {#post-api-topic-save}

Persists new topics and discussion rounds under `expected_version` and `request_id` idempotency.

### Archive Delete, Verify, Backup & Rollback (`POST /api/backup`) {#post-api-ops-verify}

Handles archival delete, snapshot restore, verification logging, SQLite backup, and rollback.

### Read-Only Agent Hooks & Question Fence (`core.agent_hooks`) {#cli-agent-hooks}

Provides strictly read-only `before-task` / `after-write` CLI hooks and `agent-question` radio cards.

</ApiExplorer>
