---
title: Setup & Configuration
description: Product scope, runtime modes, CLI arguments, dashboard.config.json matrix, and deployment troubleshooting
---

# Setup & Configuration

::: warning AI Translation Notice
This page is synced from the primary Chinese guide ([起步与配置部署](/docs/)). Refer to the Chinese version if any detail needs clarification.
:::

## Scope & Runtime Footprint

| Dimension | ✅ What It Can Do | ⛔ Explicit Non-Goals & Limits |
|---|---|---|
| **Runtime Stack** | Pure Python 3.9+ stdlib + `sqlite3`; offline bundled Mermaid/Anime.js/fonts with zero CDN | Does not require Node.js or pnpm at runtime (only for JS unit tests and building `docs-site/`) |
| **Storage & Concurrency** | Authoritative `decisions/*.md` + SQLite `revisions`, CAS `expected_version`, and `request_id` idempotency | Loopback-only socket + in-process `RLock`: **no remote auth or multi-process sharing of one DB** |
| **Agent Integration** | Five-bucket context export, read-only `before-task` / `after-write` CLI hooks, `agent-question` cards | No task scheduling, autonomous agents, or automatic build/test execution |
| **Ops & Git** | Online `/api/backup`, Markdown-grounded index rebuild, path-isolated `core.git_engine` commits | Stop server before `--rebuild-index`; never auto-pushes or stages unrelated code |

## Startup Modes & CLI Flags

| Mode / Platform | Command | Use Case |
|---|---|---|
| Linux / macOS launcher | `./start_dashboard.sh --port 8765` | Changes directory to repo root and forwards all arguments to `core.server` |
| Windows launcher | `start_dashboard.bat --port 8765` | Double-click or run from terminal with forwarded CLI flags |
| Python module directly | `python3 -m core.server --port 8765 --no-browser` | Headless startup, custom port, or script integration |
| Installed package entry | `agent-dashboard --config /path/to/dashboard.config.json` | Available after `pip install -e .` (`pyproject.toml` `core.server:main`) |
| Attach external project | `python3 -m core.server --config /path/to/project/dashboard.config.json` | Keeps service source separate; relative paths resolve against the config's parent directory |
| Read-only consistency check | `python3 -m core.server --config ... --check-consistency` | Verifies Markdown digests against SQLite `topics` and `metadata.json` then exits |
| Rebuild index from Markdown | `python3 -m core.server --config ... --rebuild-index` | Reconstructs `topics` & `metadata.json` from `decisions/*.md` (stop server first) |
| Export module context | `python3 -m core.server --config ... --export-agent-context 存储层` | Prints 5-bucket Markdown governance summary for the specified module and exits |

### CLI Arguments (`core.server`)

- `--config <path>`: Explicit config path; raises `FileNotFoundError` rather than falling back to repository defaults if missing.
- `--host <addr>` / `--port <int>`: Override bind host (loopback only) and port (default `8765`).
- `--no-browser`: Do not invoke `webbrowser.open(...)` on startup.
- `--check-consistency` / `--rebuild-index` / `--export-agent-context <module>`: One-shot maintenance/export commands that exit without binding an HTTP socket.

## Configuration Matrix and Precedence

Precedence order (highest wins):

`CLI flags (--host / --port)` > `Env vars (AGENT_DASHBOARD_HOST / AGENT_DASHBOARD_PORT)` > `dashboard.config.json` > `DEFAULT_CONFIG` in `core/config.py`

> Note: `load_config` applies a top-level `dict.update(user_data)`. Keep nested structures complete if overriding `git_commit`, `categories`, or `topic_scope`.

| Key / Env Var | Default | Type | Behavior & Path Resolution |
|---|---|---|---|
| `host` / `AGENT_DASHBOARD_HOST` | `"127.0.0.1"` | string | Bind address (loopback only) |
| `port` / `AGENT_DASHBOARD_PORT` | `8765` | int | Port number; non-integer env var values are ignored |
| `project_name` / `project_subtitle` | `"Agent Decisions Dashboard"` / ... | string | Workbench header title and `/api/status` metadata |
| `brand_logo` / `brand_icon` | `"AD"` / `"⚖️"` | string | Brand badge text and icon |
| `decisions_dir` | `"decisions"` | string | Authoritative Markdown directory; relative paths resolve from config directory |
| `database_path` | `"decisions.db"` | string | SQLite ledger, revisions, and idempotency store |
| `metadata_json_path` | `"decisions/metadata.json"` | string | Read-only summary export file |
| `doc_data_json_path` | `"doc_data.json"` | string | Legacy compatibility config key (unused as write/recovery entrypoint) |
| `topic_scope.active_topic_ids` | `null` | `string[] \| null` | `null` shows all topics; an array scopes lists, overviews, and `AgentContextEngine` while keeping direct `/api/topic/:id` access |
| `git_commit.enabled` | `true` | bool | Enable path-isolated Git commit after writes |
| `git_commit.commit_prefix` / `co_author` | `"feat(decision)"` / `""` | string | Auto-commit subject prefix and optional `Co-authored-by` trailer |
| `git_commit.include_user_opinion` / `include_agent_reply` | `true` / `true` | bool | Include discussion excerpt in auto-commit body |
| `categories.objects` / `functions` | 5 objects / 5 functions | `string[]` | Filter tag lists in the sidebar |
| `lifecycle_states` | 5-item array | array | Metadata for `decided`, `discussing`, `pending`, `deferred`, `superseded` |

## Deployment Troubleshooting FAQ

**1. Why does binding `0.0.0.0` or a LAN IP fail?**

`is_loopback_host` in `core/server.py` strictly blocks non-loopback bindings to prevent unauthenticated remote access to local decision files and Git operations. Keep `127.0.0.1` and vary `--port` if needed.

**2. Empty topic list with warning `[WARN] 只有 metadata.json 摘要，未找到权威 Markdown`?**

`metadata.json` is an export cache only and cannot be imported as a substitute for `decisions/*.md`. Restore the Markdown files from source or backup before restarting.

**3. How do I recover safely from a consistency mismatch?**

Do not delete `decisions.db` blindly (it holds unique `revisions` and `idempotency_keys`). Call `POST /api/backup` first to take an online SQLite backup, inspect `GET /api/recovery/check`, then restore or run offline `--rebuild-index` after stopping any running instance.

**4. Why does `git_status` report `skipped_unrelated_staged` or `no_identity` when the UI shows Saved?**

Ledger persistence and Git committing are decoupled stages. Unrelated staged files, missing local Git identity, or `.git/index.lock` skip only the Git commit without rolling back saved Markdown or SQLite data.

**5. Edits to Python config or `web/` files are not reflected in the open browser tab?**

Restart `core.server` after Python or `dashboard.config.json` changes. For `web/` edits, reload the browser page (save or back up any unsent draft comments first).
