# Agent Decisions Dashboard

[中文完整说明](README.md) · [Chinese source guide](repo-docs/README.md)

A local decision ledger for human and agent collaboration. It preserves discussion text, separates workflow, decision outcome and implementation state, and retains version history. A Python standard-library service serves static HTML/CSS/JavaScript; no frontend build or npm install is needed to run it.

## Run

Requires Python 3.9+. From this repository:

```sh
python -m core.server --port 8765 --no-browser
python -m core.server --config <target-project-config.json> --no-browser
```

Open `http://127.0.0.1:8765/dashboard.html`. Relative data paths resolve against the config directory. Only one process may manage a data directory. Git is optional and needs a prepared repository and identity for automatic commits. Use a separate data directory for experiments.

## Capabilities and boundaries

Create topics, append both sides of a discussion, amend the latest round while preserving history, filter decisions, render Markdown and local diagrams, and inspect or restore history. Partial acceptance must retain the user's scope in their own words. Agent-provided options do not authorize work or change decision state automatically.

Writes use the HTTP service, an observed `expected_version` and a unique `request_id`. Preserve the original request and receipt; retry uncertain results with identical data. Check `save_status`, `export_status` and `git_status` separately. Markdown stores current content; SQLite also stores history and receipts. Summary exports are not complete backups.

This is a local ledger, without remote multi-user access control, scheduling or autonomous agents. Accepted decisions and registered verification labels do not prove implementation or tests. Read [the agent workflow](docs/agent-workflow.md) before integrating.

## Verification

```sh
python -m unittest discover tests
node --test tests/*.test.js
node --check web/app.js
git diff --check
```

Node is needed only for frontend checks. UI changes also need browser testing against an isolated ledger. These commands were inspected, not run as part of this documentation sync.

## License

[GPL-3.0-or-later](LICENSE). Vendored frontend resources retain their own license notices under `web/vendor/`.

## Documentation site

The [Chinese source guide](repo-docs/README.md) follows one implemented workflow, then links to a code map and evidence audit. It does not claim complete architecture coverage.

```sh
npm --prefix docs-site ci
npm --prefix docs-site run docs:dev -- --host 127.0.0.1
npm --prefix docs-site run docs:build
```

The documentation site uses the default VitePress theme, with dependencies installed separately from the application. Output defaults to `docs-site/.vitepress/dist/`; append `-- --outDir <external-absolute-directory>` for an isolated build. Markdown remains in `repo-docs/` and is included by the site. Repository source links are shown as exact paths; source files and local resources are not published.

For behavior-changing edits and repository questions, follow the `repo-docs` Sync gate in [the Agent rules](AGENTS.md); update stale guide pages and record meaningful changes.
