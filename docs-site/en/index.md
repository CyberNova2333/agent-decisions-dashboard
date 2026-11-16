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
      text: Contracts & Hooks
      link: /en/docs/contracts
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
- **Integrating HTTP API, state contracts, or agent hooks**: Read [API Contracts & Extensions](/en/docs/contracts) for loopback security rules, REST endpoints, 3-axis model, `agent-question`, and `core.agent_hooks`;
- **Tracing persistence flow, code map, or schema migrations**: See [Architecture, Code & Migrations](/en/docs/architecture) for request/storage lifecycle, `core/` & `web/` & `tests/` map, and migration notes;
- **Deep Chinese source guide & two-pass audit**: See `repo-docs/README.md` in the repository root.
:::
