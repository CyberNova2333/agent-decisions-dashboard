---
title: API Contracts & Extensions
description: Loopback security rules, HTTP REST API, orthogonal 3-axis model, CAS/idempotency retry contract, agent-question fence, and read-only hooks
---

# 2. API Contracts & Extensions

::: warning AI Translation Notice
This page is synced from the primary Chinese guide ([接口与扩展契约](/docs/contracts)). Refer to the Chinese version if any detail is ambiguous.
:::

All external integrations and agents must interact through the HTTP API and read-only CLI hooks — never edit `decisions.db` or `decisions/metadata.json` directly.

## Security Boundaries & Capability Limits

1. **Loopback isolation**: `is_loopback_host` permits `localhost` and loopback IPv4/IPv6 addresses only. `send_head` rejects symlinks escaping `web/`.
2. **Cross-site & payload defense**: Mutating requests enforce `Host`, `Origin` (loopback or empty), and `Sec-Fetch-Site` (blocks `cross-site`), require `Content-Type: application/json`, reject `Transfer-Encoding`, require a single `Content-Length`, cap payloads at `10 MiB` (`10s` read timeout), and cap Git invocations at `30s`.
3. **Portable topic IDs (`validate_portable_id`)**: Allows 1–128 chars `[a-zA-Z0-9_-]`; rejects traversal segments, Windows reserved names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`), and case-insensitive alias collisions.
4. **Non-authorizing labels**: `accepted`, `verified`, and `agent-question` radio selections are ledger data only — the server never executes tests, runs builds, or grants shell execution rights.

## HTTP REST API Reference

### Read-Only Endpoints (`GET`)

| Endpoint | Query Params | Purpose |
|---|---|---|
| `/` | — | `302` redirect to `/dashboard.html` |
| `/api/config` | — | Returns resolved config dictionary |
| `/api/status` | — | Returns `project_name`, absolute paths, Git readiness, and `consistency` digest |
| `/api/topics` | — | Returns `topic_scope`-filtered topic list, capabilities, `settled_decisions`, `open_questions`, `changelog`, config |
| `/api/topic/<id>` | — | Returns full topic detail, `version`, `content`, `discussion`, and recent revisions (reachable even if filtered out by `topic_scope`) |
| `/api/git/log` | `limit`, `offset`, `topic_id` | Returns Git commit log, SQLite `revisions`, and `current_revision` |
| `/api/agent/context` | `module`, `path`, `topic_id`, `format=json\|markdown` | Returns 5 context buckets; explicit unknown `topic_id` errors instead of returning empty |
| `/api/recovery/check` | — | Compares Markdown digests against SQLite `topics` and `metadata.json` |

### Protected Write Endpoints (`POST`)

Topic mutations accept `expected_version` / `request_id` in JSON body or via `X-Expected-Version` / `X-Request-Id` headers.

| Endpoint | Key Payload Fields | Behavior |
|---|---|---|
| `/api/topic/create` | `id`, `title`, optional `content_override`, 3-axis fields, `request_id` | Creates topic Markdown, SQLite row, and initial revision |
| `/api/topic/<id>/save` | `expected_version` (required when topic exists), `request_id`, `new_user_opinion`, `new_agent_reply`, `edit_latest_round`, 3-axis fields, `commit_message` | Appends round or amends latest round (`edit_latest_round: true`); replays identically for matching `request_id` + payload |
| `/api/topic/<id>/restore` | `rev_id`, `expected_version` (required for live topic), `author`, `reason`, `request_id` | Restores single topic snapshot (traces `TOPIC_REMOVE` -> `prior_rev_id` when deleted) |
| `/api/topic/<id>/verify` | `expected_version`, `impl_commit` (non-empty), `verifier`, `test_summary`, `mark_verified` (bool), `request_id` | Records caller-supplied verification metadata without executing tests |
| `/api/topic/<id>/delete` | `expected_version`, optional `author`, `reason`, `request_id` | Moves `.md` to `.archived_rollback/`, deletes `topics` row, writes `TOPIC_REMOVE` revision for undo |
| `/api/rollback` | `rev_id`, `expected_revision` (required from `/api/git/log`) | Full-ledger rollback (`428` if missing, `409` on revision drift) |
| `/api/recovery/rebuild` | — | Rebuilds `topics` and `metadata.json` from `decisions/*.md` while preserving `revisions` (`409` on guarded drift) |
| `/api/backup` | — | Creates hot SQLite backup via Backup API |

Common errors: `400` validation/round-trip fence failure, `403` forbidden origin/host, `404` not found, `409` `version_conflict` / `idempotency_conflict` / `revision_conflict`, `428` missing `expected_version` or `expected_revision`.

## Orthogonal 3-Axis & Idempotency Contracts

- **`workflow_state`**: `pending`, `discussing`, `decided`, `deferred`, `superseded`.
- **`decision_outcome`**: `""`, `accepted`, `partially_accepted` (first switch requires non-empty user opinion stating scope; grouped under `pending_requirements`), `rejected` (requires non-empty `rejection_reason`).
- **`implementation_state`**: `not_started`, `in_progress`, `implemented`, `verified`.
- **Save & retry discipline**: Persist the exact `request.json` before POSTing. On timeout, retry the exact saved `request_id`, `expected_version`, and payload — never bump `expected_version` or allocate a new `request_id` after `save_status` succeeded even if `git_status` skipped/failed.
- **Latest-round amendment**: Use `edit_latest_round: true` only when the user explicitly requests fixing the latest round; pass only the amended field (`new_user_opinion` or `new_agent_reply`) so the other stays intact and prior snapshots stay preserved.

## Agent Hooks (`core.agent_hooks`) & `agent-question`

The repository **never auto-installs** global agent hooks or Git hooks. Host tools or developers run `core.agent_hooks` explicitly:

```sh
python3 -m core.agent_hooks --config /path/to/dashboard.config.json before-task --module 存储层
python3 -m core.agent_hooks --config /path/to/dashboard.config.json after-write --topic adr-storage --receipt /path/to/receipt.json
```

- Loopback HTTP only (`--url` overrides address while still checking data path parity via `/api/status`); proxies and redirects disabled.
- Exit code `0` means ledger consistency/receipt check passed (still check `git_committed` explicitly); exit code `2` emits structured JSON error on `stderr`. `after-write` does not verify `delete_topic` archive or full-ledger rollback.
- **Stdlib retry pattern**: Fetch `GET /api/topic/<id>`, persist `request.json` outside tracked public files, POST to `/api/topic/<id>/save`, and save `receipt.json`.
- **`agent-question` JSON fence**: Place inside the latest `new_agent_reply` with 1 `question` string and 2–8 unique options (strings or `{ "label", "description" }`). Enclose docs/examples in longer outer backticks so they never activate radio controls; UI has no pre-selected default and never mutates 3-axis state automatically.

## Extension Troubleshooting

| Condition | Action |
|---|---|
| Server offline or config mismatch | Verify `--config`, port, and running instance; never fall back to blind writes on default port |
| `428 version_required` | Read `/api/topic/<id>` or `/api/git/log` first before constructing a write |
| `409` conflict | Re-read latest state, compare drafts manually, then submit with a fresh `request_id` |
| `400` round-trip validation error | Close unclosed Markdown fences or wrap literal discussion-header examples in outer fences |
| `git_status != "committed"` | Report `git_status` honestly; ledger save and Git commit are distinct phases |
