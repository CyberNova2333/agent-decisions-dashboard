---
title: Architecture, Code Map & Migrations
description: Layered architecture, lifecycle diagram, write walkthrough summary, codebase map, and key schema/behavior migrations
---

# Architecture, Code Map & Migrations

::: warning AI Translation Notice
This page is synced from the primary Chinese guide ([原理与源码导览（含决策迁移）](/docs/architecture)). The repository's authoritative walkthrough and evidence audit under `repo-docs/` are written in Chinese; see the Chinese docs page for the full embedded walkthrough.
:::

## System Layering & Storage Topology

1. **Static Workbench (`web/`)**: `dashboard.html` + `app.js` implement the dual-pane master-detail workspace, focus review mode, and draft preservation. `markdown.js` strips raw HTML and checks link schemes; `diagrams.js` wraps vendored Mermaid 12.1.0 (strict mode, 50k chars / 500 edges max); `agent-question.js` activates only valid latest-round fences.
2. **Loopback Gateway & Process Lock (`core/server.py`, `core/locking.py`)**: Python `ThreadingHTTPServer` validates loopback origin/host rules and request size/timeout bounds; mutations serialize via an in-process reentrant lock keyed by normalized `database_path`.
3. **Orchestration & Authoritative Markdown (`core/decision_service.py`, `core/markdown_parser.py`)**: Before atomically replacing `decisions/<id>.md`, `_validate_document` performs a parse-and-reserialize round-trip check so broken Markdown fences never corrupt a topic file.
4. **Snapshots, Consistency & Isolated Git (`core/db.py`, `core/recovery.py`, `core/git_engine.py`)**: `decisions.db` stores full `revisions` snapshots, monotonic `topic_version_seq` (ABA prevention), and SHA-256-keyed `idempotency_keys`. `metadata.json` is export-only, and `GitEngine` aborts cleanly (`skipped_unrelated_staged`) if unrelated staged changes exist.

## Decision Lifecycle Interactive Diagram

<DiagramFrame
  src="/diagrams/decision-lifecycle.html"
  title="Decision State Lifecycle Interactive Diagram (pan / zoom / inspect supported)"
  aspect="966 / 326"
  new-tab-label="Open Fullscreen ↗"
/>

## End-to-End Write & Replay Walkthrough

A single `POST /api/topic/<id>/save` follows five sequential guarantees (detailed step-by-step in repository file `repo-docs/walkthroughs/one-real-run.md`):

1. **Read & Verify Target**: Confirm service data paths via `GET /api/status` (or `agent_hooks preflight`) and read current `version` from `GET /api/topic/<id>`.
2. **Persist Request Identity**: Generate a unique `request_id` per logical operation, bind `expected_version`, and store `request.json` before POSTing.
3. **Lock, Deduplicate & Validate**: Inside `ledger_lock`, match `(request_id, req_hash)` in `idempotency_keys` (replaying completed responses or resuming unfinished metadata/Git phases without appending duplicate rounds), verify `expected_version` against `topic_version_seq`, and run `_validate_document` round-trip check.
4. **Persist & Report Staged Receipts**: Atomically update `decisions/<id>.md`, update SQLite `topics` + `revisions`, export `metadata.json`, optionally run path-isolated Git commit, and return independent `save_status`, `export_status`, and `git_status` fields.
5. **Read-Only Post Check**: Run `core.agent_hooks after-write --topic <id> --receipt receipt.json` to confirm version parity and ledger consistency.

## Code Map and Key Migrations

### Repository Structure (`core/`, `web/`, `tests/`)

| Path | Responsibility | Key Symbols / Assets |
|---|---|---|
| `core/config.py` | Config loading, env precedence, relative path resolution, `topic_scope` | `load_config`, `Config.topic_is_active` |
| `core/contracts.py` | Portable ID regex/reserved-name check & orthogonal 3-axis enum mapping | `validate_portable_id`, `decision_axes` |
| `core/server.py` | Loopback HTTP handler, origin/size/timeout guards & CLI modes | `is_loopback_host`, `make_handler`, `main` |
| `core/decision_service.py` | Save, create, amend latest round, verify, archive delete & restore/rollback | `save_topic`, `edit_latest_round`, `delete_topic`, `restore_single_topic`, `rollback_full` |
| `core/db.py` | SQLite schema/migrations, `topic_version_seq`, `idempotency_keys`, hot backup | `upsert_topic`, `check_idempotency`, `commit_revision`, `backup_database` |
| `core/markdown_parser.py` | `schema_version: "2.0"` frontmatter & fence-aware round parser | `parse_markdown_text`, `amend_round`, `serialize_markdown` |
| `core/recovery.py` | Digest check, index rebuild from Markdown & summary export | `check_consistency`, `rebuild_index_from_markdown`, `sync_metadata_json` |
| `core/git_engine.py` | Clean-index guard, 30s timeout & path-isolated commits | `commit_decision`, `get_commit_history` |
| `core/agent_context.py` & `core/agent_hooks.py` | 5-bucket governance context query & read-only pre/post hooks | `query_context`, `before_task`, `after_write` |
| `web/` & `web/vendor/` | Dual-pane workbench, safe Markdown/Mermaid rendering, bundled vendor libs | `app.js`, `agent-question.js`, `markdown.js`, `diagrams.js` |
| `tests/` | Python unittest suite (227 tests) & Node frontend tests (12 tests) | `tests/test_*.py`, `tests/*.test.js` |

### Key Migrations & Breaking/Behavioral Changes

1. **Orthogonal 3-Axis Promotion**: Legacy topics placing `"deferred"` or `"superseded"` in `decision_outcome` are transparently interpreted in memory under `workflow_state` (`LEGACY_PROGRESS_OUTCOMES`) without silently rewriting disk files until the next explicit save or restore to `schema_version: "2.0"`.
2. **Safe Archive Delete (`delete_topic`)**: Deleting a topic moves `decisions/<id>.md` to `decisions/.archived_rollback/` with a random suffix and records a `TOPIC_REMOVE` revision linking `prior_rev_id`, enabling single-topic undo or full rollback.
3. **Scoped Topic Filtering (`topic_scope.active_topic_ids`)**: Long-lived ledgers can configure an array of active topic IDs to declutter lists and `GET /api/agent/context` without removing archived Markdown or breaking direct `/api/topic/<id>` links.
4. **`doc_data_json_path` Compatibility Key**: Retained in `DEFAULT_CONFIG` for legacy config compatibility only; authoritative persistence remains exclusively `decisions_dir/*.md` + `database_path`, with summary exports to `metadata_json_path`.

## Contributor Verification Commands

Run all checks against isolated temporary directories (never against a live ledger's `decisions.db`):

```sh
python3 -m unittest discover tests
node --test tests/*.test.js
node --check web/app.js && node --check web/markdown.js && node --check web/diagrams.js
git diff --check
pnpm --dir docs-site run docs:build
```

For full evidence claims, falsification criteria, and remaining risks (including single-process bounds and manual UI testing scope), refer to `repo-docs/references/source-evidence.md` and `repo-docs/references/quality-review.md` in the repository.
