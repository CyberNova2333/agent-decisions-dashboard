---
layout: home

hero:
  name: Agent Decisions Dashboard
  text: Local Decision Ledger & Review Workbench
  tagline: Built with the Python 3.9+ standard library, SQLite, and zero-build static assets to record discussions, review opinions, and version snapshots alongside local AI coding tools.
  actions:
    - theme: brand
      text: Setup & Config
      link: /en/docs/
    - theme: alt
      text: API & Components
      link: /en/api-reference/
    - theme: alt
      text: Architecture & Code
      link: /en/docs/architecture
    - theme: alt
      text: GitHub Repo
      link: https://github.com/CyberNova2333/agent-decisions-dashboard

features:
  - title: Zero Runtime Dependencies
    details: Backend runs purely on the Python 3.9+ stdlib and SQLite; Mermaid 12.1.0 and Anime.js 4.5.0 are bundled offline with no Node.js or external CDN required at runtime.
  - title: Orthogonal States & CAS Idempotency
    details: Separates workflow, decision outcome, and implementation state; writes enforce expected_version and request_id deduplication with safe archive deletion and snapshot recovery.
  - title: Read-Only Agent Integration
    details: Provides topic_scope-filtered context exports, read-only before-task / after-write CLI hooks, and non-authorizing agent-question radio cards.
---

::: warning AI Translation Notice
The English documentation is maintained alongside the primary Chinese docs. In case of any subtle discrepancy, please treat the [Chinese documentation](/) as authoritative.
:::

## Capabilities & Explicit Boundaries

::: info What It Can Do (Delivered Scope)
- **Zero-Dependency Local Startup & External Attach**: Runs solely on the Python 3.9+ standard library and SQLite; attach any external project directory cleanly via `--config /path/to/dashboard.config.json`.
- **Traceable Ledger, Review & Recovery**: Coordinates authoritative `schema_version: "2.0"` Markdown files with SQLite `revisions`, CAS `expected_version` locks, `request_id` idempotent replay, online `/api/backup`, and path-isolated auto Git commits.
- **Scoped Agent Context & Read-Only Hooks**: Exports five-bucket decision context, isolates `partially_accepted` as pending requirements, and exposes `before-task` / `after-write` CLI verification plus non-authorizing `agent-question` cards.
:::

::: warning What It Explicitly Cannot Do (Non-Goals & Hard Limits)
- **No Remote Hosting or Multi-User Concurrency**: Loopback-only (`127.0.0.1` / `localhost`, rejecting `0.0.0.0`) with an in-process lock — **no user accounts, RBAC, remote authentication, or multi-process sharing of one `decisions.db`**.
- **Never Executes Code, Builds, or Tests**: Marking `accepted`/`verified` or selecting an `agent-question` option records ledger text only — **the server and hooks never trigger builds, run tests, or grant execution authority**.
- **`metadata.json` / Markdown Alone Do Not Replace `decisions.db`**: `metadata.json` is a read-only summary export and Markdown holds latest content only; full `revisions` and `idempotency_keys` live solely in `decisions.db`.
:::

## Decision Lifecycle Interactive Diagram

<div class="archify-diagram-card" style="margin: 1.5rem 0; border: 1px solid var(--vp-c-border); border-radius: 12px; overflow: hidden; background: var(--vp-c-bg-soft); box-shadow: 0 4px 16px rgba(0,0,0,0.06);">
  <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 18px; background: var(--vp-c-bg-elv); border-bottom: 1px solid var(--vp-c-border); font-size: 13px;">
    <span style="font-weight: 600; color: var(--vp-c-text-1); display: flex; align-items: center; gap: 8px;">
      <span style="font-size: 16px;">📐</span> Decision State Lifecycle Interactive Diagram (pan / zoom / inspect supported)
    </span>
    <a href="/diagrams/decision-lifecycle.html" target="_blank" rel="noreferrer" style="font-size: 12px; color: var(--vp-c-brand-1); text-decoration: none; font-weight: 500;">
      Open Fullscreen ↗
    </a>
  </div>
  <iframe src="/diagrams/decision-lifecycle.html" width="100%" height="520px" frameborder="0" style="display: block; border: none;" allowfullscreen loading="lazy"></iframe>
</div>

## Quick Start Demo

```sh
git clone https://github.com/CyberNova2333/agent-decisions-dashboard.git
cd agent-decisions-dashboard
./start_dashboard.sh --port 8765
# Or run directly: python3 -m core.server --port 8765 --no-browser
```

The server binds exclusively to loopback addresses; open `http://127.0.0.1:8765/dashboard.html` in a browser to create and review topics.

## Documentation Guide

::: tip Quick Navigation by Role & Goal
- **First local run or attaching an external project**: Start with [Setup & Configuration](/en/docs/) for `./start_dashboard.sh` / `.bat`, CLI flags, `dashboard.config.json` matrix, and troubleshooting;
- **Explore endpoints, hooks & copy-ready call examples**: Open [API & Component Reference](/en/api-reference/) or read the full prose spec in [API Contracts & Extensions](/en/docs/contracts);
- **Tracing persistence flow, code map, or schema migrations**: See [Architecture, Code & Migrations](/en/docs/architecture) for request/storage lifecycle and `core/` / `web/` / `tests/` map;
- **Deep Chinese source guide & two-pass audit**: See `repo-docs/README.md` in the repository root.
:::
