// Agent Decisions Dashboard — Master-Detail Workbench & Governance Client
// Supports Split-Pane Cockpit, 4-Tab Unified Composer (Append / Amend / Proposal / Verify),
// Universal Agent-Question Option Cards, Immersive Focus Review, CAS Conflict Merge,
// Scoped Time Machine, Parameterized Agent Context & 3-Way Consistency Maintenance.
(function () {
  "use strict";

  const appearanceStorageKey = "agent-decisions-dashboard.appearance";
  const layoutStorageKey = "agent-decisions-dashboard.layout";
  const systemPrefersDark = () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  const appearance = { mode: systemPrefersDark() ? "dark" : "light", accent: "blue" };
  let dnSwitchView = null;

  try {
    const saved = JSON.parse(localStorage.getItem(appearanceStorageKey) || "null");
    if (saved && (saved.mode === "dark" || saved.mode === "light")) {
      appearance.mode = saved.mode;
    }
  } catch (_) { /* ignore storage error */ }

  const SVG_PATHS = {
    sun: '<circle cx="12" cy="12" r="4.5"/><line x1="12" y1="2" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="6.34" y2="6.34"/><line x1="17.66" y1="17.66" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="6.34" y2="17.66"/><line x1="17.66" y1="6.34" x2="19.07" y2="4.93"/>',
    moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    half: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    circle: '<circle cx="12" cy="12" r="8"/>',
    chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    question: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    pause: '<circle cx="12" cy="12" r="10"/><line x1="10" y1="15" x2="10" y2="9"/><line x1="14" y1="15" x2="14" y2="9"/>',
    archive: '<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
    code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>',
    doc: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
  };

  function iconSvg(name) {
    const body = SVG_PATHS[name];
    if (!body) return "";
    return `<svg class="ui-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  }

  window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    appearance.mode = e.matches ? "dark" : "light";
    applyAppearance(false);
  });

  function applyAppearance(persist = false) {
    document.body.dataset.theme = appearance.mode;
    document.body.dataset.accent = appearance.accent;
    const picker = document.getElementById("theme-accent");
    if (picker) picker.value = appearance.accent;
    const toggle = document.getElementById("btn-toggle-theme");
    if (toggle) {
      const label = appearance.mode === "dark" ? "切换为浅色模式" : "切换为深色模式";
      toggle.title = label;
      toggle.setAttribute("aria-label", label);
      toggle.innerHTML = appearance.mode === "dark"
        ? `${iconSvg("sun")}<span>浅色</span>`
        : `${iconSvg("moon")}<span>深色</span>`;
    }
    if (dnSwitchView) {
      dnSwitchView.apply(appearance.mode === "dark");
    }
    if (persist) {
      try { localStorage.setItem(appearanceStorageKey, JSON.stringify(appearance)); }
      catch (_) { /* Keep the selected appearance for this tab when storage is blocked. */ }
    }
  }

  function initDayNightSwitch() {
    // Keep the compact single-row header theme button instead of the wide SVG switch
    applyAppearance(false);
  }

  applyAppearance();

  const state = {
    config: {},
    capabilities: {},
    topicsMeta: [],
    settledDecisions: [],
    openQuestions: [],
    changelog: [],
    topicsDetailCache: Object.create(null),
    detailRequests: new Map(),
    detailQueue: [],
    detailActive: 0,
    expandedTopics: new Set(),
    metadataRequest: 0,
    expansionRequest: 0,
    workbenchRenderRequest: 0,
    editSession: null,
    createRequest: null,
    creating: false,
    createAutoSlug: true,
    draftsByTopic: new Map(),
    selectedTopicId: null,
    composerMode: "append", // "append" | "amend" | "proposal" | "verify"
    dockExpanded: false,
    mobileDetailOpen: false,
    viewMode: "split", // "split" | "grid" | "list"
    currentView: "topics",
    sidebarCollapsed: true,
    sortBy: "actionable_first",
    filters: {
      lifecycle: "all",
      object: "all",
      function: "all",
      outcome: "all",
      implementation: "all",
      searchQuery: "",
    },
    isServerOnline: false,
    consistencyStatus: null,
    hasLoadedTopics: false,
    pendingRestores: Object.create(null),
    historyRevision: null,
    timeMachineScope: "all", // "topic" | "all"
    timeMachineTopicId: null,
    agentContextText: "",
    review: {
      active: false,
      scope: "filtered", // "filtered" | "actionable" | "all"
      index: 0,
      drafts: new Map(),
      saving: false,
      detailRequest: 0,
      overviewOpen: false,
    },
  };

  try {
    const savedLayout = JSON.parse(localStorage.getItem(layoutStorageKey) || "null");
    if (savedLayout) {
      if (["split", "grid", "list"].includes(savedLayout.viewMode)) state.viewMode = savedLayout.viewMode;
      if (typeof savedLayout.dockExpanded === "boolean") state.dockExpanded = savedLayout.dockExpanded;
      if (savedLayout.sortBy) state.sortBy = savedLayout.sortBy;
    }
  } catch (_) { /* ignore */ }

  function persistLayoutPrefs() {
    try {
      localStorage.setItem(layoutStorageKey, JSON.stringify({
        viewMode: state.viewMode,
        dockExpanded: state.dockExpanded,
        sortBy: state.sortBy,
      }));
    } catch (_) { /* ignore */ }
  }

  function showToast(message, type = "success", action = null) {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const safeType = ["success", "warning", "error", "info"].includes(type) ? (type === "info" ? "success" : type) : "error";
    const toast = document.createElement("div");
    toast.className = `toast ${safeType}`;
    const text = document.createElement("span");
    text.textContent = String(message ?? "");
    toast.append(text);
    const labelText = action?.text || action?.label;
    const clickFn = action?.onClick || action?.callback;
    if (labelText && typeof clickFn === "function") {
      const actionBtn = document.createElement("button");
      actionBtn.type = "button";
      actionBtn.className = "btn btn-secondary btn-sm";
      actionBtn.style.marginLeft = "0.75rem";
      actionBtn.textContent = labelText;
      actionBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        toast.remove();
        clickFn();
      });
      toast.appendChild(actionBtn);
    }
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 5500);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function topicPath(topicId) {
    const id = String(topicId ?? "");
    if (!/^[a-zA-Z0-9_-]+$/.test(id)) throw new Error("议题 ID 无效");
    return `/api/topic/${encodeURIComponent(id)}`;
  }

  function createRequestId(prefix = "req") {
    if (globalThis.crypto?.randomUUID) return `${prefix}-${globalThis.crypto.randomUUID()}`;
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  }

  const statusLabel = (value) => String(value || "").replace(/[\p{Extended_Pictographic}\p{Emoji_Presentation}\u2300-\u27BF\uFE0F]/gu, "").trim();

  function getLifecycleBadge(lc) {
    if (state.config.lifecycle_states) {
      const found = state.config.lifecycle_states.find((s) => s.id === lc);
      if (found) return { ...found, badge: statusLabel(found.badge || found.name || found.id) };
    }
    if (lc === "decided") return { badge: "已决策", badge_class: "badge-decided" };
    if (lc === "pending") return { badge: "待决策", badge_class: "badge-pending" };
    if (lc === "deferred") return { badge: "推迟再议", badge_class: "badge-discussing" };
    if (lc === "superseded") return { badge: "已被替代", badge_class: "badge-superseded" };
    return { badge: "待讨论", badge_class: "badge-discussing" };
  }

  function renderMarkdown(text) {
    return window.DashboardMarkdown.render(text);
  }

  function getStoredOutcome(t) {
    if (typeof t?.decision_outcome === "string" && t.decision_outcome) return t.decision_outcome;
    if (typeof t?.decision_outcome === "string" && t.decision_outcome === "") {
      const status = String(t.decision_status || "");
      if (status.includes("非否决")) return "";
      if (status.includes("否决")) return "rejected";
      if (status.includes("部分同意")) return "partially_accepted";
      if (status.includes("采纳") || status.includes("已同意")) return "accepted";
      if (status.includes("推迟") || status.includes("暂缓")) return "deferred";
      if (status.includes("替代")) return "superseded";
      return "";
    }
    return "";
  }

  function getCanonicalOutcome(t) {
    const outcome = getStoredOutcome(t);
    return ["deferred", "superseded"].includes(outcome) ? "" : outcome;
  }

  function getCanonicalWorkflow(t) {
    const outcome = getStoredOutcome(t);
    return ["deferred", "superseded"].includes(outcome) ? outcome : (t?.workflow_state || t?.lifecycle_status || "discussing");
  }

  function parseTopicAgentQuestion(t) {
    const reply = String(t?.latest_round_agent_reply ?? t?.last_agent_reply ?? "");
    return window.DashboardAgentQuestion.parse(reply);
  }

  function hasPendingQuestion(t) {
    const parsed = parseTopicAgentQuestion(t);
    if (!parsed.question) return false;
    const latestUser = String(t?.latest_round_user_opinion ?? t?.last_user_opinion ?? "").trim();
    const split = window.DashboardAgentQuestion.splitSaved(parsed.question, latestUser);
    return split.selected === null && !latestUser;
  }

  function isTopicActionable(t) {
    const wf = getCanonicalWorkflow(t);
    const out = getCanonicalOutcome(t);
    if (wf === "superseded" || wf === "deferred") return false;
    if (hasPendingQuestion(t)) return true;
    if (wf === "pending" || wf === "discussing") return true;
    if (out === "" || out === "partially_accepted") return true;
    return false;
  }

  function isSessionDirty(session) {
    if (!session) return false;
    if (session.pendingRequest || session.conflict) return true;
    return JSON.stringify(session.fields) !== session.initialSnapshot || session.questionSelected !== session.initialQuestionSelected;
  }

  function priorityRank(priority) {
    const p = String(priority || "普通").trim();
    if (p === "最高" || p.toLowerCase() === "critical" || p === "P0") return 4;
    if (p === "高" || p.toLowerCase() === "high" || p === "P1") return 3;
    if (p === "普通" || p.toLowerCase() === "normal" || p === "中" || p === "P2") return 2;
    return 1;
  }

  // Two-Stage Loading: 1. Load Metadata List
  async function loadMetadataList() {
    const request = ++state.metadataRequest;
    try {
      const res = await fetch("/api/topics", { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        if (request !== state.metadataRequest) return false;
        if (!Array.isArray(data.topics)) throw new Error("议题列表响应格式无效");
        for (const topic of data.topics) {
          if (state.topicsDetailCache[topic.id]?.version !== topic.version) {
            delete state.topicsDetailCache[topic.id];
          }
        }
        state.topicsMeta = data.topics;
        state.capabilities = data.capabilities || {};
        state.hasLoadedTopics = true;
        state.settledDecisions = data.settled_decisions || [];
        state.openQuestions = data.open_questions || [];
        state.changelog = data.changelog || [];
        if (data.config) applyConfig(data.config);

        state.isServerOnline = true;
        updateServerStatus(true);
        populateDatalistsAndSelects();
        ensureValidSelection();
        renderAllViews();
        checkConsistencySilently();
        return true;
      }
    } catch (e) {
      console.warn("Failed to load /api/topics, fallback to offline data", e);
    }

    if (request !== state.metadataRequest) return false;
    updateServerStatus(false);
    if (!state.hasLoadedTopics && window.DASHBOARD_DEFAULT_DATA) {
      const def = window.DASHBOARD_DEFAULT_DATA;
      state.topicsMeta = def.topics || [];
      state.settledDecisions = def.settled_decisions || [];
      state.openQuestions = def.open_questions || [];
      state.changelog = def.changelog || [];
      if (def.config) applyConfig(def.config);
      updateServerStatus(false);
      const statusTextEl = document.getElementById("server-status-text");
      if (statusTextEl) statusTextEl.textContent = "离线示例（非已保存数据）";
      populateDatalistsAndSelects();
      ensureValidSelection();
      renderAllViews();
    }
    return false;
  }

  async function checkConsistencySilently() {
    try {
      const res = await fetch("/api/status", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      state.consistencyStatus = data;
      const dot = document.getElementById("server-status-dot");
      const text = document.getElementById("server-status-text");
      if (dot && text && state.isServerOnline) {
        if (data.consistency && !data.consistency.consistent) {
          dot.className = "server-dot warning";
          text.textContent = "待同步";
        } else {
          dot.className = "server-dot online";
          text.textContent = "服务在线";
        }
      }
    } catch (_) { /* ignore */ }
  }

  function renderAllViews() {
    updateSidebarCounts();
    renderActiveFiltersBar();
    renderTopicCards();
    renderSettledDecisions();
    renderOpenQuestions();
    renderChangelog();
    if (state.review.active) renderReview();
  }

  function ensureValidSelection() {
    const filtered = getFilteredTopics();
    if (state.selectedTopicId && state.topicsMeta.some((t) => t.id === state.selectedTopicId)) {
      return;
    }
    if (filtered.length > 0) {
      state.selectedTopicId = filtered[0].id;
    } else if (state.topicsMeta.length > 0) {
      state.selectedTopicId = state.topicsMeta[0].id;
    } else {
      state.selectedTopicId = null;
    }
  }

  function bindFilterPills(root = document) {
    root.querySelectorAll(".filter-pill[data-type]").forEach((pill) => {
      if (pill.dataset.bound === "true") return;
      pill.dataset.bound = "true";
      pill.addEventListener("click", () => {
        const type = pill.dataset.type;
        const val = pill.dataset.val;
        if (type === "lifecycle") {
          state.filters.lifecycle = val;
        } else if (type === "outcome") {
          state.filters.outcome = val;
        } else if (type === "object") {
          state.filters.object = val;
        }
        syncFilterPillsActiveState();
        renderActiveFiltersBar();
        renderTopicCards();
      });
    });
  }

  function syncFilterPillsActiveState() {
    document.querySelectorAll('#lifecycle-filters-container .filter-pill, #quick-workflow-strip .filter-pill').forEach((el) => {
      el.classList.toggle("active", el.dataset.val === state.filters.lifecycle);
    });
    document.querySelectorAll('#outcome-filters-container .filter-pill').forEach((el) => {
      el.classList.toggle("active", el.dataset.val === state.filters.outcome);
    });
    document.querySelectorAll('#object-filters-container .filter-pill').forEach((el) => {
      el.classList.toggle("active", el.dataset.val === state.filters.object);
    });
    const fnSel = document.getElementById("function-filter");
    if (fnSel && fnSel.value !== state.filters.function) fnSel.value = state.filters.function;
    const implSel = document.getElementById("implementation-filter");
    if (implSel && implSel.value !== state.filters.implementation) implSel.value = state.filters.implementation;
  }

  function updateSidebarCounts() {
    const all = state.topicsMeta;
    const setTxt = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.textContent = String(v);
    };

    const actionableCount = all.filter((t) => isTopicActionable(t)).length;
    const settledCount = (state.settledDecisions || []).length || all.filter((t) => getCanonicalWorkflow(t) === "decided").length;
    const changelogCount = (state.changelog || []).length;

    setTxt("count-topics", all.length);
    setTxt("count-open", actionableCount);
    setTxt("count-settled", settledCount);
    setTxt("count-changelog", changelogCount);

    setTxt("top-count-topics", all.length);
    setTxt("top-count-open", actionableCount);
    setTxt("top-count-settled", settledCount);
    setTxt("top-count-changelog", changelogCount);

    setTxt("review-actionable-badge", actionableCount);

    setTxt("pill-count-all", all.length);
    setTxt("pill-count-actionable", actionableCount);
    setTxt("pill-count-decided", all.filter((t) => getCanonicalWorkflow(t) === "decided").length);
    setTxt("pill-count-discussing", all.filter((t) => getCanonicalWorkflow(t) === "discussing").length);
    setTxt("pill-count-pending", all.filter((t) => getCanonicalWorkflow(t) === "pending").length);
    setTxt("pill-count-deferred", all.filter((t) => getCanonicalWorkflow(t) === "deferred").length);
    setTxt("pill-count-superseded", all.filter((t) => getCanonicalWorkflow(t) === "superseded").length);

    setTxt("pill-count-accepted", all.filter((t) => getCanonicalOutcome(t) === "accepted").length);
    setTxt("pill-count-partial", all.filter((t) => getCanonicalOutcome(t) === "partially_accepted").length);
    setTxt("pill-count-rejected", all.filter((t) => getCanonicalOutcome(t) === "rejected").length);
    setTxt("pill-count-unsettled", all.filter((t) => getCanonicalOutcome(t) === "").length);

    setTxt("pill-count-all-obj", all.length);
    document.querySelectorAll("[data-obj-badge]").forEach((badge) => {
      const objName = badge.dataset.objBadge;
      badge.textContent = String(all.filter((t) => t.object === objName).length);
    });
  }

  function populateDatalistsAndSelects() {
    const objectsSet = new Set(state.config?.categories?.objects || []);
    const functionsSet = new Set(state.config?.categories?.functions || []);
    const sectionsSet = new Set();

    state.topicsMeta.forEach((t) => {
      if (t.object) objectsSet.add(t.object);
      if (t.function) functionsSet.add(t.function);
      if (t.section) sectionsSet.add(t.section);
    });

    const fillDatalist = (id, values) => {
      const dl = document.getElementById(id);
      if (!dl) return;
      dl.innerHTML = Array.from(values).filter(Boolean).map((v) => `<option value="${escapeHtml(v)}"></option>`).join("");
    };
    fillDatalist("datalist-objects", objectsSet);
    fillDatalist("datalist-functions", functionsSet);
    fillDatalist("datalist-sections", sectionsSet);
    fillDatalist("datalist-topic-ids", state.topicsMeta.map((t) => t.id));

    // Populate Object Filter Pills
    const objContainer = document.getElementById("object-filters-container");
    if (objContainer) {
      let html = `
        <span class="filter-pill ${state.filters.object === "all" ? "active" : ""}" data-type="object" data-val="all">
          <span>全部对象</span>
          <span class="nav-badge" id="pill-count-all-obj">${state.topicsMeta.length}</span>
        </span>
      `;
      Array.from(objectsSet).filter(Boolean).forEach((obj) => {
        const active = state.filters.object === obj ? "active" : "";
        html += `
          <span class="filter-pill ${active}" data-type="object" data-val="${escapeHtml(obj)}">
            <span>${escapeHtml(obj)}</span>
            <span class="nav-badge" data-obj-badge="${escapeHtml(obj)}">0</span>
          </span>
        `;
      });
      objContainer.innerHTML = html;
      bindFilterPills(objContainer);
    }

    // Populate Function Select Filter
    const funcSelect = document.getElementById("function-filter");
    if (funcSelect) {
      const currentVal = state.filters.function || "all";
      funcSelect.innerHTML = `<option value="all">全部业务功能</option>` +
        Array.from(functionsSet).filter(Boolean).map((fn) =>
          `<option value="${escapeHtml(fn)}"${fn === currentVal ? " selected" : ""}>功能：${escapeHtml(fn)}</option>`
        ).join("");
    }
  }

  function applyConfig(cfg) {
    state.config = cfg || {};
    if (cfg.project_name) {
      const pageTitleEl = document.getElementById("page-title");
      if (pageTitleEl) pageTitleEl.innerText = cfg.project_name;
      const brandTitleEl = document.getElementById("brand-title");
      if (brandTitleEl) {
        const brandNameSpan = brandTitleEl.querySelector("[data-brand-name]");
        if (brandNameSpan) {
          brandNameSpan.innerText = cfg.project_name;
        }
      }
    }
    if (cfg.project_subtitle !== undefined && cfg.project_subtitle !== null) {
      const el = document.getElementById("brand-subtitle");
      if (el) el.innerText = cfg.project_subtitle;
    }
    if (cfg.brand_logo) {
      const el = document.getElementById("brand-logo");
      if (el) el.innerText = cfg.brand_logo;
    }
    if (cfg.brand_icon) {
      const fav = document.getElementById("page-favicon");
      if (fav) fav.href = "brand-logo.svg";
      const cleanBrandIcon = statusLabel(cfg.brand_icon);
      const brandIconEl = document.getElementById("brand-icon");
      if (brandIconEl && cleanBrandIcon) {
        brandIconEl.innerText = cleanBrandIcon;
      }
    }

    if (cfg.lifecycle_states && Array.isArray(cfg.lifecycle_states)) {
      cfg.lifecycle_states.forEach((s) => {
        const opt = document.querySelector(`#form-workflow-state option[value="${s.id}"]`);
        if (opt) {
          const label = s.name || s.id;
          opt.innerText = (s.badge && !s.badge.includes(label)) ? `${statusLabel(s.badge)} ${label}` : (statusLabel(s.badge) || label);
        }
        const pill = document.querySelector(`[data-type="lifecycle"][data-val="${s.id}"]`);
        if (pill) {
          const span = pill.querySelector("span:first-child");
          if (span) {
            span.innerText = statusLabel(s.badge || s.name || s.id);
          }
        }
      });
    }
  }

  function updateServerStatus(online) {
    state.isServerOnline = online;
    const createBtn = document.getElementById("btn-create-topic");
    if (createBtn) createBtn.disabled = !online;
    const dot = document.getElementById("server-status-dot");
    const text = document.getElementById("server-status-text");
    if (dot && text) {
      if (online) {
        dot.className = "server-dot online";
        text.innerText = "本机服务在线";
      } else {
        dot.className = "server-dot offline";
        text.innerText = "离线预览（不可保存）";
      }
    }
  }

  // Two-Stage Loading: 2. On-Demand Fetch Single Topic Markdown
  async function fetchTopicDetail(topicId) {
    const key = `${topicId}@${state.topicsMeta.find((t) => t.id === topicId)?.version}`;
    if (state.detailRequests.has(key)) return state.detailRequests.get(key);
    const request = new Promise((resolve, reject) => {
      state.detailQueue.push(() => readTopicDetail(topicId).then(resolve, reject));
    });
    state.detailRequests.set(key, request);
    pumpDetailQueue();
    try { return await request; }
    finally { if (state.detailRequests.get(key) === request) state.detailRequests.delete(key); }
  }

  function pumpDetailQueue() {
    while (state.detailActive < 4 && state.detailQueue.length) {
      const task = state.detailQueue.shift();
      state.detailActive++;
      task().finally(() => { state.detailActive--; pumpDetailQueue(); });
    }
  }

  async function readTopicDetail(topicId) {
    if (state.topicsDetailCache[topicId]) {
      return state.topicsDetailCache[topicId];
    }

    try {
      const res = await fetch(topicPath(topicId), { cache: "no-store" });
      if (res.ok) {
        const detail = await res.json();
        if (detail.version === state.topicsMeta.find((t) => t.id === topicId)?.version) {
          state.topicsDetailCache[topicId] = detail;
        }
        return detail;
      }
    } catch (e) {
      console.warn(`Failed to fetch topic ${topicId}`, e);
    }

    const meta = state.topicsMeta.find((t) => t.id === topicId);
    return {
      id: topicId,
      title: meta ? meta.title : topicId,
      version: meta ? meta.version : 1,
      core_content: meta ? meta.summary || "" : "",
      rounds: meta && meta.rounds_count ? [
        {
          title: "第 1 轮讨论与定案",
          user_opinion: meta.latest_round_user_opinion ?? meta.last_user_opinion ?? "",
          agent_reply: meta.latest_round_agent_reply ?? meta.last_agent_reply ?? "",
          content: `- **用户意见**：${meta.last_user_opinion || "—"}\n- **团队答复**：${meta.last_agent_reply || "—"}`,
        },
      ] : [],
    };
  }

  function getFilteredTopics() {
    const filtered = state.topicsMeta.filter((t) => {
      const wf = getCanonicalWorkflow(t);
      const canonicalOut = getCanonicalOutcome(t);

      if (state.filters.lifecycle !== "all") {
        if (state.filters.lifecycle === "actionable") {
          if (!isTopicActionable(t)) return false;
        } else if (wf !== state.filters.lifecycle) {
          return false;
        }
      }
      if (state.filters.object !== "all" && t.object !== state.filters.object) {
        return false;
      }
      if (state.filters.function !== "all" && t.function !== state.filters.function) {
        return false;
      }
      if (state.filters.implementation !== "all" && (t.implementation_state || "not_started") !== state.filters.implementation) {
        return false;
      }
      if (state.filters.outcome !== "all") {
        if (state.filters.outcome === "unsettled") {
          if (canonicalOut !== "") return false;
        } else if (canonicalOut !== state.filters.outcome) {
          return false;
        }
      }
      if (state.filters.searchQuery) {
        const q = state.filters.searchQuery.toLowerCase();
        const str = `${t.title} ${t.id} ${t.object || ""} ${t.function || ""} ${t.section || ""} ${t.summary || ""} ${t.rejection_reason || ""} ${t.last_user_opinion || ""} ${t.last_agent_reply || ""} ${t.impl_commit || ""} ${t.sources || ""}`.toLowerCase();
        if (!str.includes(q)) return false;
      }
      return true;
    });

    return sortTopics(filtered);
  }

  function sortTopics(list) {
    const arr = [...list];
    const mode = state.sortBy || "actionable_first";
    arr.sort((a, b) => {
      if (mode === "actionable_first") {
        const qA = hasPendingQuestion(a) ? 1 : 0;
        const qB = hasPendingQuestion(b) ? 1 : 0;
        if (qA !== qB) return qB - qA;
        const actA = isTopicActionable(a) ? 1 : 0;
        const actB = isTopicActionable(b) ? 1 : 0;
        if (actA !== actB) return actB - actA;
        const pDiff = priorityRank(b.priority) - priorityRank(a.priority);
        if (pDiff !== 0) return pDiff;
        return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
      }
      if (mode === "updated_desc") {
        return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
      }
      if (mode === "priority_desc") {
        const pDiff = priorityRank(b.priority) - priorityRank(a.priority);
        if (pDiff !== 0) return pDiff;
        return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
      }
      if (mode === "rounds_desc") {
        const rDiff = (b.rounds_count || 0) - (a.rounds_count || 0);
        if (rDiff !== 0) return rDiff;
        return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
      }
      if (mode === "id_asc") {
        return String(a.id || "").localeCompare(String(b.id || ""));
      }
      return 0;
    });
    return arr;
  }

  function renderActiveFiltersBar() {
    const bar = document.getElementById("active-filters-bar");
    if (!bar) return;
    const chips = [];
    const lcNames = {
      actionable: "待处理/有提问",
      decided: "已决策",
      discussing: "待讨论",
      pending: "待决策",
      deferred: "推迟再议",
      superseded: "已被替代",
    };
    const outNames = {
      accepted: "已采纳",
      partially_accepted: "部分同意",
      rejected: "明确否决",
      unsettled: "尚无结论",
    };
    const implNames = {
      not_started: "未开始",
      in_progress: "进行中",
      implemented: "已实现",
      verified: "已核验",
    };

    if (state.filters.lifecycle !== "all") {
      chips.push({ key: "lifecycle", label: `工作流: ${lcNames[state.filters.lifecycle] || state.filters.lifecycle}` });
    }
    if (state.filters.outcome !== "all") {
      chips.push({ key: "outcome", label: `结论: ${outNames[state.filters.outcome] || state.filters.outcome}` });
    }
    if (state.filters.object !== "all") {
      chips.push({ key: "object", label: `对象: ${state.filters.object}` });
    }
    if (state.filters.function !== "all") {
      chips.push({ key: "function", label: `功能: ${state.filters.function}` });
    }
    if (state.filters.implementation !== "all") {
      chips.push({ key: "implementation", label: `落地: ${implNames[state.filters.implementation] || state.filters.implementation}` });
    }
    if (state.filters.searchQuery) {
      chips.push({ key: "searchQuery", label: `搜索: "${state.filters.searchQuery}"` });
    }

    if (!chips.length) {
      bar.hidden = true;
      bar.innerHTML = "";
      return;
    }

    bar.hidden = false;
    bar.innerHTML = chips.map((c) =>
      `<button type="button" class="active-filter-chip" data-clear-filter="${escapeHtml(c.key)}" title="点击移除此筛选条件"><span>${escapeHtml(c.label)}</span><span>&times;</span></button>`
    ).join("") + `<button type="button" class="btn btn-secondary btn-sm" data-clear-filter="all">清空筛选</button>`;
  }

  function renderOutcomeBadgeHtml(t) {
    const out = getCanonicalOutcome(t);
    if (out === "accepted") return '<span class="badge badge-decided">已采纳</span>';
    if (out === "partially_accepted") return '<span class="badge badge-partial">部分同意</span>';
    if (out === "rejected") return '<span class="badge badge-rejected">已否决</span>';
    return '<span class="badge badge-superseded">尚无结论</span>';
  }

  function renderImplBadgeHtml(t) {
    const implState = t.implementation_state || t.impl_status || "not_started";
    if (implState === "verified") {
      return '<span class="badge badge-verified" title="已登记核验凭据">已核验</span>';
    }
    if (implState === "implemented") {
      return '<span class="badge badge-decided" title="已标记代码实现">已实现</span>';
    }
    if (implState === "in_progress") {
      return '<span class="badge badge-in-progress" title="正在开发落地">进行中</span>';
    }
    return '<span class="badge badge-superseded">实现: 未开始</span>';
  }

  function renderTopicCards() {
    const container = document.getElementById("topics-container");
    const workbenchContainer = document.getElementById("workbench-container");
    const toggleAllBtn = document.getElementById("btn-toggle-all");
    if (!container || !workbenchContainer) return;

    workbenchContainer.className = `workbench-container mode-${state.viewMode}${state.viewMode === "split" && state.mobileDetailOpen ? " mobile-detail-open" : ""}`;
    if (toggleAllBtn) toggleAllBtn.hidden = state.viewMode === "split";

    const filtered = getFilteredTopics();
    const countLabel = document.getElementById("filtered-count-label");
    if (countLabel) {
      countLabel.innerText = `显示 ${filtered.length} / ${state.topicsMeta.length} 项议题`;
    }

    if (filtered.length === 0) {
      updateExpandButton();
      container.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 3.5rem 1rem; color: var(--text-dim); background: var(--canvas-subtle); border: 1px dashed var(--border-default); border-radius: 6px;">
          <h3 style="color: var(--fg-default); margin-bottom: 6px;">${state.topicsMeta.length ? "未找到匹配当前筛选条件的议题" : "当前台账还没有议题"}</h3>
          <p style="font-size: 13px;">${state.topicsMeta.length ? "可以点击下方按钮重置筛选条件，或修改顶部搜索关键词。" : "点击右上角“新建议题”创建第一条架构决策。"}</p>
          ${state.topicsMeta.length ? '<button class="btn btn-secondary" style="margin-top: 12px;" data-action="reset">重置所有筛选</button>' : ""}
        </div>
      `;
      renderWorkbenchDetailPane(null);
      return;
    }

    if (!state.selectedTopicId || !filtered.some((t) => t.id === state.selectedTopicId)) {
      state.selectedTopicId = filtered[0].id;
    }

    if (state.viewMode === "split") {
      container.innerHTML = filtered.map((t) => {
        const wf = getCanonicalWorkflow(t);
        const lcInfo = getLifecycleBadge(wf);
        const isSelected = t.id === state.selectedTopicId;
        const hasQ = hasPendingQuestion(t);
        const session = state.draftsByTopic.get(t.id);
        const dirty = isSessionDirty(session);
        const cleanLatestReply = parseTopicAgentQuestion(t).cleanReply;
        const snippetSource = (t.latest_round_user_opinion || cleanLatestReply || t.summary || "暂无摘要").replace(/\s+/g, " ").trim();

        return `
          <div class="master-topic-item${isSelected ? " selected" : ""}" id="card-${escapeHtml(t.id)}" data-action="select" data-topic-id="${escapeHtml(t.id)}" tabindex="0" role="button" aria-pressed="${isSelected ? "true" : "false"}">
            <div class="master-item-top">
              <span class="badge ${escapeHtml(lcInfo.badge_class)}">${escapeHtml(lcInfo.badge)}</span>
              ${renderOutcomeBadgeHtml(t)}
              ${hasQ ? '<span class="badge badge-pending" title="Agent 提出了选项等待拍板">待答复提问</span>' : ""}
              ${dirty ? '<span class="badge badge-in-progress" title="存在尚未提交的本地草稿">草稿未保存</span>' : ""}
              <span class="chip" style="margin-left: auto;">#${escapeHtml(t.id)}</span>
            </div>
            <div class="master-item-title">${escapeHtml(t.title)}</div>
            <div class="master-item-Snippet">${escapeHtml(snippetSource.slice(0, 120))}</div>
            <div class="master-item-bottom">
              <span>${escapeHtml(t.object || "通用")} · ${escapeHtml(t.function || "规范")} · 优先级:${escapeHtml(t.priority || "普通")}</span>
              <span class="mono">v${escapeHtml(t.version || 1)} · ${escapeHtml(t.rounds_count || 0)} 轮</span>
            </div>
          </div>
        `;
      }).join("");

      const selectedTopic = state.topicsMeta.find((t) => t.id === state.selectedTopicId) || filtered[0];
      renderWorkbenchDetailPane(selectedTopic);
      return;
    }

    // Grid or List View
    container.innerHTML = filtered.map((t) => {
      const wf = getCanonicalWorkflow(t);
      const lcInfo = getLifecycleBadge(wf);
      const rounds = t.rounds_count ?? 0;
      const ver = t.version || 1;
      const isRejected = getCanonicalOutcome(t) === "rejected";
      const hasQ = hasPendingQuestion(t);
      const session = state.draftsByTopic.get(t.id);
      const dirty = isSessionDirty(session);

      let rejectionHtml = "";
      const replacement = t.superseded_by || "";
      const replacementHtml = /^[a-zA-Z0-9_-]{1,128}$/.test(replacement)
        ? `<a href="#${escapeHtml(replacement)}">#${escapeHtml(replacement)}</a>` : escapeHtml(replacement);
      if (isRejected) {
        const rejectionLabel = wf === "superseded" ? "历史否决记录" : wf === "deferred" ? "暂缓议题的否决记录" : "明确否决红线";
        rejectionHtml = `
          <div class="rejection-box">
            <strong>${rejectionLabel}：</strong> ${escapeHtml(t.rejection_reason || "用户或团队已明确否决此方案")}
            ${replacement && wf !== "superseded" ? `<div style="font-size: 12px; margin-top: 0.2rem; color: var(--text-dim);">替代议题：${replacementHtml}</div>` : ""}
          </div>
        `;
      }

      return `
        <div class="topic-card" id="card-${escapeHtml(t.id)}">
          <div class="card-meta-line">
            <span class="badge ${escapeHtml(lcInfo.badge_class)}">${escapeHtml(lcInfo.badge)}</span>
            ${renderOutcomeBadgeHtml(t)}
            ${renderImplBadgeHtml(t)}
            ${hasQ ? '<span class="badge badge-pending">待答复提问</span>' : ""}
            ${dirty ? '<span class="badge badge-in-progress">草稿</span>' : ""}
            <span class="chip">#${escapeHtml(t.id)}</span>
            <span class="chip">v${escapeHtml(ver)}</span>
            <span class="chip">${escapeHtml(t.object || "通用")} · ${escapeHtml(t.function || "规范")}</span>
            <span class="chip" style="margin-left: auto;">第 ${escapeHtml(rounds)} 轮</span>
          </div>

          <h3 class="card-title" data-action="open-workbench" data-topic-id="${escapeHtml(t.id)}" title="点击在分栏工作台中打开完整上下文">${escapeHtml(t.title)}</h3>

          <div class="card-summary">
            ${/^\s*(`{3,}|~{3,})/.test(t.summary || "")
              ? "正文以图表或代码开头，点击展开详情或在工作台查看。"
              : renderMarkdown(t.summary ? t.summary + "..." : "")}
          </div>

          ${rejectionHtml}
          ${wf === "deferred" ? '<p class="form-label">按原话中的时间或条件继续；同意此安排不代表立即实施。</p>' : ""}
          ${wf === "superseded" ? `<p class="form-label">原结论仅供追溯。${replacement ? `替代议题：${replacementHtml}` : "可在工作台中填写替代议题。"}</p>` : ""}

          <div id="detail-body-${escapeHtml(t.id)}" style="display: none; border-top: 1px dashed var(--border-subtle); padding-top: 0.8rem;"></div>

          <div class="discussion-box">
            <div class="discussion-title">
              <span>最新决策记录（第 ${escapeHtml(rounds)} 轮）</span>
              <div style="display: flex; gap: 6px;">
                ${rounds && state.capabilities.edit_latest_round ? `<button class="btn btn-secondary btn-sm" type="button" data-action="open-workbench" data-composer-mode="amend" data-topic-id="${escapeHtml(t.id)}">更正本轮</button>` : ""}
                <button class="btn btn-secondary btn-sm" type="button" data-action="open-workbench" data-composer-mode="proposal" data-topic-id="${escapeHtml(t.id)}">改正文/分类</button>
              </div>
            </div>
            <div class="discussion-row">
              <div class="discussion-label">用户意见：</div>
              <div style="color: var(--text-main);">${renderMarkdown((t.latest_round_user_opinion ?? t.last_user_opinion) || "暂无原话记录")}</div>
            </div>
            <div class="discussion-row">
              <div class="discussion-label">落实答复：</div>
              <div style="color: var(--text-main);">${renderMarkdown(parseTopicAgentQuestion(t).cleanReply || "—")}</div>
            </div>
            ${t.impl_commit ? `
              <div class="discussion-row" style="font-size: 12px; color: var(--text-dim); border-top: 1px dashed var(--border-subtle); padding-top: 0.3rem;">
                <span>实现提交引用：</span><code>${escapeHtml(t.impl_commit)}</code>
                ${t.impl_verifier ? `<span> · 核验: ${escapeHtml(t.impl_verifier)}</span>` : ""}
              </div>
            ` : ""}
          </div>

          <div class="card-footer">
            <span style="font-size: 12px; color: var(--text-muted);">decisions/${escapeHtml(t.id)}.md</span>
            <div style="display: flex; gap: 0.4rem; flex-wrap: wrap;">
              <button class="btn btn-secondary btn-sm" type="button" data-action="copy" data-topic-id="${escapeHtml(t.id)}">引用</button>
              <button class="btn btn-secondary btn-sm" type="button" data-action="history" data-topic-id="${escapeHtml(t.id)}">历史</button>
              <button class="btn btn-secondary btn-sm" type="button" data-action="toggle" data-topic-id="${escapeHtml(t.id)}">
                <span id="expand-btn-${escapeHtml(t.id)}">展开详情</span>
              </button>
              <button class="btn btn-primary btn-sm" type="button" data-action="open-workbench" data-topic-id="${escapeHtml(t.id)}">进入工作台决策</button>
            </div>
          </div>
        </div>
      `;
    }).join("");

    refreshExpandedCards();
    updateExpandButton();
  }

  // =========================================================================
  // Helpers: Mermaid, Modals, Drawers, Per-Topic Draft Sessions & Questions
  // =========================================================================
  function renderMermaidDiagrams(root = document) {
    if (!window.mermaid || !root) return;
    const nodes = root.querySelectorAll(".mermaid-diagram:not([data-processed])");
    if (nodes.length > 0) {
      try {
        window.mermaid.run({ nodes: Array.from(nodes) });
      } catch (_) { /* ignore mermaid render errors */ }
    }
  }

  function openModal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add("open", "active");
    el.style.display = "flex";
    el.setAttribute("aria-hidden", "false");
  }

  function closeModal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("open", "active");
    el.style.display = "none";
    el.setAttribute("aria-hidden", "true");
  }

  function openDrawer(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add("open", "active");
    el.style.display = "flex";
    el.setAttribute("aria-hidden", "false");
  }

  function closeDrawer(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("open", "active");
    el.style.display = "none";
    el.setAttribute("aria-hidden", "true");
  }

  function createTopicSession(topic, mode = "append") {
    const actualMode = mode === "amend" && (topic.rounds_count || 0) > 0 ? "amend" : "append";
    const parsedQ = parseTopicAgentQuestion(topic);
    const rawLatestUser = String(topic.latest_round_user_opinion ?? topic.last_user_opinion ?? "");
    const rawLatestAgent = String(topic.latest_round_agent_reply ?? topic.last_agent_reply ?? "");

    let questionSelected = null;
    let userText = "";
    let agentText = "";

    if (actualMode === "amend") {
      if (parsedQ.question) {
        const split = window.DashboardAgentQuestion.splitSaved(parsedQ.question, rawLatestUser);
        questionSelected = split.selected;
        userText = split.text;
      } else {
        userText = rawLatestUser;
      }
      agentText = rawLatestAgent;
    } else if (parsedQ.question) {
      // Do NOT pre-select recommended options per AGENTS.md
      questionSelected = null;
      userText = "";
    }

    const fields = {
      workflow_state: getCanonicalWorkflow(topic),
      decision_outcome: getCanonicalOutcome(topic),
      implementation_state: topic.implementation_state || topic.impl_status || "not_started",
      rejection_reason: topic.rejection_reason || "",
      superseded_by: topic.superseded_by || "",
      new_user_opinion: userText,
      new_agent_reply: agentText,
      impl_commit: topic.impl_commit || "",
      commit_message: "",
      title: topic.title || "",
      section: topic.section || "架构设计与工程规范",
      object: topic.object || "通用",
      function: topic.function || "规范",
      priority: topic.priority || "普通",
      sources: topic.sources || "",
      content_override: state.topicsDetailCache[topic.id]?.core_content ?? "",
    };

    return {
      topicId: topic.id,
      baseVersion: topic.version || 1,
      editMode: actualMode,
      composerTab: state.composerMode || "append",
      question: parsedQ.question,
      questionSelected,
      initialQuestionSelected: questionSelected,
      fields,
      initialSnapshot: JSON.stringify(fields),
      proposalTouched: false,
      pendingRequest: null,
      conflict: null,
      submitting: false,
    };
  }

  function getOrCreateSession(topic, mode) {
    if (!topic) return null;
    let session = state.draftsByTopic.get(topic.id);
    const requestedMode = mode === "amend" && (topic.rounds_count || 0) > 0 ? "amend" : (mode === "append" ? "append" : null);

    if (!session || (!isSessionDirty(session) && session.baseVersion !== (topic.version || 1))) {
      session = createTopicSession(topic, requestedMode || "append");
      state.draftsByTopic.set(topic.id, session);
      return session;
    }

    if (requestedMode && session.editMode !== requestedMode) {
      session.editMode = requestedMode;
      const parsedQ = parseTopicAgentQuestion(topic);
      session.question = parsedQ.question;
      if (requestedMode === "amend") {
        const rawUser = String(topic.latest_round_user_opinion ?? topic.last_user_opinion ?? "");
        if (parsedQ.question) {
          const split = window.DashboardAgentQuestion.splitSaved(parsedQ.question, rawUser);
          session.questionSelected = split.selected;
          session.fields.new_user_opinion = split.text;
        } else {
          session.fields.new_user_opinion = rawUser;
        }
        session.fields.new_agent_reply = String(topic.latest_round_agent_reply ?? topic.last_agent_reply ?? "");
      } else {
        session.questionSelected = null;
        session.fields.new_user_opinion = "";
        session.fields.new_agent_reply = "";
      }
      session.pendingRequest = null;
    }
    return session;
  }

  function composeSessionOpinion(session) {
    const rawText = session.fields.new_user_opinion || "";
    if (session.question && session.questionSelected !== null && session.questionSelected !== undefined) {
      return window.DashboardAgentQuestion.compose(session.question, session.questionSelected, rawText);
    }
    return rawText;
  }

  function buildSavePayloadFromSession(session) {
    const f = session.fields;
    const payload = {
      workflow_state: f.workflow_state,
      decision_outcome: f.decision_outcome,
      implementation_state: f.implementation_state,
      rejection_reason: f.rejection_reason,
      superseded_by: f.superseded_by,
      impl_commit: f.impl_commit,
    };

    if (session.composerTab === "proposal" || session.proposalTouched) {
      payload.title = f.title;
      payload.section = f.section;
      payload.object = f.object;
      payload.function = f.function;
      payload.priority = f.priority;
      payload.sources = f.sources;
      payload.content_override = f.content_override;
    }

    const composedOpinion = composeSessionOpinion(session);
    if (session.editMode === "amend") {
      payload.edit_latest_round = true;
      payload.new_user_opinion = composedOpinion;
      payload.new_agent_reply = f.new_agent_reply;
      payload.commit_message = f.commit_message;
    } else {
      if (composedOpinion.trim()) payload.new_user_opinion = composedOpinion;
      if ((f.new_agent_reply || "").trim()) payload.new_agent_reply = f.new_agent_reply;
      if ((f.commit_message || "").trim()) payload.commit_message = f.commit_message;
    }

    return payload;
  }

  function renderAgentQuestionInto(containerId, session, onSelectChange) {
    const box = document.getElementById(containerId);
    if (!box) return;
    if (!session || !session.question) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }

    const q = session.question;
    box.hidden = false;
    box.innerHTML = `
      <div class="agent-question-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="font-weight: 600; color: var(--accent-fg); display: inline-flex; align-items: center; gap: 6px;">${iconSvg("question")}<span>Agent 待拍板问题：${escapeHtml(q.question)}</span></span>
        <span style="font-size: 11px; color: var(--fg-muted);">点击选项选中，再次点击可取消；推荐项不会自动勾选</span>
      </div>
      <div class="agent-question-options" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 8px;">
        ${q.options.map((opt, idx) => {
          const isSelected = session.questionSelected === idx;
          return `
            <button type="button" class="agent-question-option${isSelected ? " selected" : ""}" data-opt-index="${idx}" aria-pressed="${isSelected ? "true" : "false"}">
              <div class="agent-question-option-title" style="font-weight: 600; font-size: 13px; display: flex; align-items: center; gap: 6px;">${isSelected ? iconSvg("check") : iconSvg("circle")}<span>${escapeHtml(opt.label)}</span></div>
              ${opt.description ? `<div class="agent-question-option-desc" style="font-size: 12px; color: var(--fg-muted); margin-top: 3px;">${escapeHtml(opt.description)}</div>` : ""}
            </button>
          `;
        }).join("")}
      </div>
    `;

    box.querySelectorAll(".agent-question-option").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.optIndex);
        session.questionSelected = session.questionSelected === idx ? null : idx;
        session.pendingRequest = null;
        renderAgentQuestionInto(containerId, session, onSelectChange);
        if (onSelectChange) onSelectChange(session.questionSelected);
      });
    });
  }

  // =========================================================================
  // Sidebar, Views, Filters & View Mode Controls
  // =========================================================================
  function toggleSidebar(forceClose = null) {
    if (typeof forceClose === "boolean") {
      state.sidebarCollapsed = forceClose;
    } else {
      state.sidebarCollapsed = !state.sidebarCollapsed;
    }
    applySidebarState();
  }

  function applySidebarState() {
    const layout = document.getElementById("app-layout");
    const sidebar = document.getElementById("app-sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (layout) layout.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
    if (sidebar) sidebar.classList.toggle("collapsed", state.sidebarCollapsed);
    if (backdrop) backdrop.hidden = state.sidebarCollapsed;
  }

  function switchView(viewName) {
    state.currentView = viewName;
    document.querySelectorAll(".sidebar .nav-item[data-view], .header-view-tab[data-view]").forEach((item) => {
      item.classList.toggle("active", item.dataset.view === viewName);
    });
    ["topics", "open", "settled", "changelog"].forEach((v) => {
      const panel = document.getElementById(`view-${v}`);
      if (panel) panel.style.display = v === viewName ? "block" : "none";
    });
    if (!state.sidebarCollapsed) {
      toggleSidebar(true);
    }
  }

  function setViewMode(mode) {
    if (!["split", "grid", "list"].includes(mode)) return;
    state.viewMode = mode;
    ["split", "grid", "list"].forEach((m) => {
      const btn = document.getElementById(`btn-view-${m}`);
      if (btn) btn.classList.toggle("active", m === mode);
    });
    persistLayoutPrefs();
    renderTopicCards();
  }

  function setSortMode(mode) {
    state.sortBy = mode;
    const sel = document.getElementById("sort-select");
    if (sel && sel.value !== mode) sel.value = mode;
    persistLayoutPrefs();
    renderTopicCards();
  }

  function clearSingleFilter(key) {
    if (key === "searchQuery") {
      state.filters.searchQuery = "";
      const sInput = document.getElementById("search-input");
      if (sInput) sInput.value = "";
      const clearBtn = document.getElementById("btn-clear-search");
      if (clearBtn) clearBtn.hidden = true;
    } else if (key in state.filters) {
      state.filters[key] = "all";
    }
    syncFilterPillsActiveState();
    renderActiveFiltersBar();
    renderTopicCards();
  }

  function resetFilters() {
    state.filters = {
      lifecycle: "all",
      object: "all",
      function: "all",
      outcome: "all",
      implementation: "all",
      searchQuery: "",
    };
    const sInput = document.getElementById("search-input");
    if (sInput) sInput.value = "";
    const clearBtn = document.getElementById("btn-clear-search");
    if (clearBtn) clearBtn.hidden = true;
    syncFilterPillsActiveState();
    renderActiveFiltersBar();
    renderTopicCards();
  }

  // =========================================================================
  // Overview Panels: Open Questions, Settled Decisions & Changelog
  // =========================================================================
  function renderOpenQuestions() {
    const container = document.getElementById("open-container");
    if (!container) return;
    const actionable = state.topicsMeta.filter((t) => isTopicActionable(t));
    if (actionable.length === 0) {
      container.innerHTML = `<div style="padding: 2.5rem; text-align: center; color: var(--fg-muted); background: var(--canvas-subtle); border: 1px dashed var(--border-default); border-radius: 6px;">当前没有待拍板或含未答复提问的议题。</div>`;
      return;
    }

    container.innerHTML = actionable.map((t) => {
      const wf = getCanonicalWorkflow(t);
      const lcInfo = getLifecycleBadge(wf);
      const parsedQ = parseTopicAgentQuestion(t);
      return `
        <div class="topic-card" style="margin-bottom: 12px;">
          <div class="card-meta-line">
            <span class="badge ${escapeHtml(lcInfo.badge_class)}">${escapeHtml(lcInfo.badge)}</span>
            ${renderOutcomeBadgeHtml(t)}
            ${parsedQ.question ? '<span class="badge badge-pending">含结构化待选提问</span>' : ""}
            <span class="chip">#${escapeHtml(t.id)}</span>
            <span class="chip">${escapeHtml(t.object || "通用")} · ${escapeHtml(t.function || "规范")}</span>
            <button type="button" class="btn btn-primary btn-sm" style="margin-left: auto;" data-overview-open="${escapeHtml(t.id)}">在工作台处理 →</button>
          </div>
          <h3 class="card-title" data-overview-open="${escapeHtml(t.id)}">${escapeHtml(t.title)}</h3>
          ${parsedQ.question ? `
            <div style="margin-top: 8px; padding: 10px; background: var(--canvas-subtle); border: 1px solid var(--border-default); border-radius: 6px;">
              <div style="font-weight: 600; color: var(--accent-fg); margin-bottom: 4px;">${escapeHtml(parsedQ.question.question)}</div>
              <div style="font-size: 12px; color: var(--fg-muted);">候选项：${parsedQ.question.options.map((o) => escapeHtml(o.label)).join(" / ")}</div>
            </div>
          ` : `<div class="card-summary">${renderMarkdown((t.summary || "").slice(0, 180))}</div>`}
        </div>
      `;
    }).join("");

    container.querySelectorAll("[data-overview-open]").forEach((el) => {
      el.addEventListener("click", () => {
        switchView("topics");
        selectTopic(el.dataset.overviewOpen, "append");
      });
    });
  }

  function renderSettledDecisions() {
    const container = document.getElementById("settled-container");
    if (!container) return;
    const settled = state.topicsMeta.filter((t) => {
      const wf = getCanonicalWorkflow(t);
      const out = getCanonicalOutcome(t);
      return wf === "decided" || out === "accepted" || out === "rejected" || out === "partially_accepted" || wf === "deferred";
    });

    if (settled.length === 0) {
      container.innerHTML = `<div style="padding: 2.5rem; text-align: center; color: var(--fg-muted); background: var(--canvas-subtle); border: 1px dashed var(--border-default); border-radius: 6px;">暂无已定结论或否决红线记录。</div>`;
      return;
    }

    container.innerHTML = settled.map((t) => {
      const wf = getCanonicalWorkflow(t);
      const lcInfo = getLifecycleBadge(wf);
      const out = getCanonicalOutcome(t);
      return `
        <div class="topic-card" style="margin-bottom: 12px;">
          <div class="card-meta-line">
            <span class="badge ${escapeHtml(lcInfo.badge_class)}">${escapeHtml(lcInfo.badge)}</span>
            ${renderOutcomeBadgeHtml(t)}
            ${renderImplBadgeHtml(t)}
            <span class="chip">#${escapeHtml(t.id)}</span>
            <span class="chip">${escapeHtml(t.object || "通用")} · ${escapeHtml(t.function || "规范")}</span>
            <button type="button" class="btn btn-secondary btn-sm" style="margin-left: auto;" data-settled-open="${escapeHtml(t.id)}">查看详情</button>
          </div>
          <h3 class="card-title" data-settled-open="${escapeHtml(t.id)}">${escapeHtml(t.title)}</h3>
          ${out === "rejected" ? `<div class="rejection-box" style="margin-top: 8px;"><strong>否决红线：</strong>${escapeHtml(t.rejection_reason || "已否决")}</div>` : ""}
          <div style="font-size: 13px; color: var(--fg-muted); margin-top: 6px;">
            <strong>最新拍板意见：</strong>${escapeHtml((t.latest_round_user_opinion || t.last_user_opinion || t.summary || "—").slice(0, 160))}
          </div>
        </div>
      `;
    }).join("");

    container.querySelectorAll("[data-settled-open]").forEach((el) => {
      el.addEventListener("click", () => {
        switchView("topics");
        selectTopic(el.dataset.settledOpen);
      });
    });
  }

  function renderChangelog() {
    const container = document.getElementById("changelog-container");
    if (!container) return;
    const logs = state.changelog || [];
    if (logs.length === 0) {
      container.innerHTML = `<div style="padding: 2.5rem; text-align: center; color: var(--fg-muted); background: var(--canvas-subtle); border: 1px dashed var(--border-default); border-radius: 6px;">暂无变更审计日志。</div>`;
      return;
    }

    container.innerHTML = logs.map((entry) => `
      <div class="topic-card" style="margin-bottom: 10px; padding: 12px 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 4px;">
          <strong style="font-size: 13px;">${renderMarkdown(entry.scope || "台账变更")}</strong>
          <span class="mono" style="font-size: 11px; color: var(--fg-muted);">${escapeHtml(entry.date || entry.timestamp || "")}</span>
        </div>
        <div style="font-size: 13px; color: var(--fg-default);">${escapeHtml(entry.change || "")}</div>
        ${entry.basis ? `<div style="font-size: 12px; color: var(--fg-muted); margin-top: 4px;">依据：${escapeHtml(entry.basis)}</div>` : ""}
      </div>
    `).join("");
  }

  // =========================================================================
  // Master-Detail Workbench Right Pane & 4-Tab Action Composer
  // =========================================================================
  function selectTopic(topicId, composerMode) {
    const topic = state.topicsMeta.find((t) => t.id === topicId);
    if (!topic) return;
    state.selectedTopicId = topicId;
    if (window.innerWidth <= 960) {
      state.mobileDetailOpen = true;
      if (!composerMode) {
        state.dockExpanded = false;
      }
    }
    if (composerMode) {
      state.composerMode = composerMode;
      state.dockExpanded = true;
      const session = getOrCreateSession(topic, composerMode === "amend" ? "amend" : "append");
      session.composerTab = composerMode;
    }

    if (state.viewMode !== "split") {
      setViewMode("split");
      return;
    }

    const workbenchContainer = document.getElementById("workbench-container");
    if (workbenchContainer) {
      workbenchContainer.classList.toggle("mobile-detail-open", state.mobileDetailOpen);
    }

    document.querySelectorAll(".master-topic-item").forEach((el) => {
      const match = el.dataset.topicId === topicId;
      el.classList.toggle("selected", match);
      el.setAttribute("aria-pressed", match ? "true" : "false");
    });

    renderWorkbenchDetailPane(topic);
  }

  function closeMobileDetail() {
    state.mobileDetailOpen = false;
    const workbenchContainer = document.getElementById("workbench-container");
    if (workbenchContainer) {
      workbenchContainer.classList.remove("mobile-detail-open");
    }
  }

  function renderRoundsTimelineHtml(rounds, topicId, canEditLatest) {
    if (!Array.isArray(rounds) || rounds.length === 0) {
      return `
        <div class="empty-round-notice" style="padding: 14px 16px; background: var(--canvas-subtle); border: 1px dashed var(--border-default); border-radius: 6px; color: var(--fg-muted); font-size: 13px;">
          当前议题尚未记录讨论轮次。可点击底部固定栏<strong>「追加拍板」</strong>随时录入用户拍板原话与 Agent 落实方案。
        </div>
      `;
    }

    return `<div class="timeline-rounds">` + rounds.map((r, idx) => {
      const isLatest = idx === rounds.length - 1;
      const roundNum = r.round || (idx + 1);
      const parsedReply = window.DashboardAgentQuestion.parse(String(r.agent_reply || ""));
      const hasQ = Boolean(parsedReply.question);
      return `
        <div class="timeline-round-card${isLatest ? " latest-round" : ""}">
          <div class="timeline-round-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="badge ${isLatest ? "badge-decided" : "badge-superseded"}">第 ${escapeHtml(roundNum)} 轮讨论</span>
              ${isLatest ? '<span class="chip">最新轮次</span>' : ""}
              ${hasQ ? '<span class="badge badge-pending">含结构化提问</span>' : ""}
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
              ${r.commit_message ? `<span class="mono" style="font-size: 11px; color: var(--fg-muted);" title="关联归档摘要">${escapeHtml(r.commit_message)}</span>` : ""}
              ${isLatest && canEditLatest ? `<button type="button" class="btn btn-secondary btn-sm" data-composer-tab="amend" data-topic-id="${escapeHtml(topicId)}">更正本轮</button>` : ""}
            </div>
          </div>
          <div class="timeline-round-body">
            <div class="timeline-party-block party-user">
              <div class="timeline-party-label">用户拍板意见 / 批注原话</div>
              <div class="markdown-body">${r.user_opinion ? renderMarkdown(r.user_opinion) : '<span style="color: var(--fg-subtle);">（本轮未填写用户意见）</span>'}</div>
            </div>
            <div class="timeline-party-block party-agent">
              <div class="timeline-party-label">Agent 方案答复 / 落实说明</div>
              <div class="markdown-body">${parsedReply.cleanReply ? renderMarkdown(parsedReply.cleanReply) : '<span style="color: var(--fg-subtle);">（本轮未填写 Agent 答复）</span>'}</div>
              ${hasQ ? `
                <div style="margin-top: 8px; padding: 8px 10px; background: var(--canvas-default); border: 1px solid var(--border-default); border-radius: 6px; font-size: 12px;">
                  <div style="font-weight: 600; color: var(--accent-fg); margin-bottom: 4px;">附带待选问题：${escapeHtml(parsedReply.question.question)}</div>
                  <div style="color: var(--fg-muted);">包含 ${escapeHtml(parsedReply.question.options.length)} 个候选方案 · 可直接在上方待办卡或底部拍板栏点选</div>
                </div>
              ` : ""}
            </div>
          </div>
        </div>
      `;
    }).join("") + `</div>`;
  }

  function renderWorkbenchDetailPane(topic) {
    const pane = document.getElementById("topic-detail-pane");
    if (!pane) return;

    if (!topic) {
      pane.innerHTML = `
        <div class="workbench-empty-state" style="padding: 4rem 2rem; text-align: center; color: var(--fg-muted); margin: auto;">
          <h3 style="color: var(--fg-default); margin-bottom: 8px;">未选择议题</h3>
          <p style="font-size: 13px;">请从左侧列表中选择一个议题，或点击右上角「新建」。</p>
        </div>
      `;
      return;
    }

    const wf = getCanonicalWorkflow(topic);
    const out = getCanonicalOutcome(topic);
    const lcInfo = getLifecycleBadge(wf);
    const roundsCount = topic.rounds_count ?? 0;
    const ver = topic.version || 1;
    const canAmend = roundsCount > 0 && state.capabilities.edit_latest_round !== false;

    let activeTab = state.composerMode || "append";
    if (activeTab === "amend" && !canAmend) activeTab = "append";

    const editMode = activeTab === "amend" ? "amend" : "append";
    const session = getOrCreateSession(topic, editMode);
    session.composerTab = activeTab;

    const cachedDetail = state.topicsDetailCache[topic.id];
    const coreProposalMd = cachedDetail ? (cachedDetail.core_content || "") : (topic.summary || "");
    const roundsList = cachedDetail ? (cachedDetail.rounds || []) : [];

    const replacement = topic.superseded_by || "";
    const replacementHtml = /^[a-zA-Z0-9_-]{1,128}$/.test(replacement)
      ? `<a href="#${escapeHtml(replacement)}">#${escapeHtml(replacement)}</a>` : escapeHtml(replacement);

    const curOut = session.fields.decision_outcome ?? out;
    const curWf = session.fields.workflow_state || wf;

    pane.innerHTML = `
      <div class="detail-cockpit">
        <!-- Zone 1: Sticky Compact Top Header -->
        <div class="detail-cockpit-header">
          <div class="detail-header-badges">
            <span class="badge ${escapeHtml(lcInfo.badge_class)}">${escapeHtml(lcInfo.badge)}</span>
            ${renderOutcomeBadgeHtml(topic)}
            ${renderImplBadgeHtml(topic)}
            <span class="chip mono">#${escapeHtml(topic.id)} · v${escapeHtml(ver)}</span>
            <span class="chip">${escapeHtml(topic.object || "通用")} · ${escapeHtml(topic.function || "规范")}</span>
            <span class="chip">优先级:${escapeHtml(topic.priority || "普通")}</span>
            <span class="chip">${escapeHtml(roundsCount)} 轮</span>
            ${topic.updated_at ? `<span style="font-size: 11px; color: var(--fg-muted); margin-left: auto;">${escapeHtml(topic.updated_at)}</span>` : ""}
          </div>

          <div class="detail-header-title-row">
            <div class="detail-title-group">
              <button type="button" class="btn btn-secondary btn-sm mobile-back-btn" id="btn-mobile-back" title="返回议题列表">← 返回列表</button>
              <h2 class="detail-topic-title">${escapeHtml(topic.title)}</h2>
            </div>
            <div class="detail-header-actions">
              <button type="button" class="btn btn-secondary btn-sm" data-action="copy" data-topic-id="${escapeHtml(topic.id)}" title="复制此议题的 Markdown 引用链接">${iconSvg("copy")}<span>引用</span></button>
              <button type="button" class="btn btn-secondary btn-sm" data-action="context-topic" data-topic-id="${escapeHtml(topic.id)}" title="提取此议题的专属 Agent 上下文">${iconSvg("code")}<span>上下文</span></button>
              <button type="button" class="btn btn-secondary btn-sm" data-action="history" data-topic-id="${escapeHtml(topic.id)}" title="查看此议题的历史版本快照与单点恢复">${iconSvg("clock")}<span>历史</span></button>
              <button type="button" class="btn btn-secondary btn-sm" data-action="review-from-here" data-topic-id="${escapeHtml(topic.id)}" title="从当前议题进入全屏沉浸批阅">批阅</button>
              <button type="button" class="btn btn-danger btn-sm" data-action="delete-topic" data-topic-id="${escapeHtml(topic.id)}" title="归档移除此议题（支持一键撤销恢复）">${iconSvg("archive")}<span>归档</span></button>
            </div>
          </div>

          ${out === "rejected" ? `
            <div class="rejection-box" style="margin-top: 4px; margin-bottom: 0; padding: 6px 10px;">
              <strong>明确否决红线：</strong> ${escapeHtml(topic.rejection_reason || "用户或团队已明确否决此方案")}
              ${replacement ? `<span style="margin-left: 8px; font-size: 12px; color: var(--fg-muted);">替代方案：${replacementHtml}</span>` : ""}
            </div>
          ` : ""}

          ${wf === "deferred" ? `
            <div class="composer-banner" style="margin-top: 4px; margin-bottom: 0;">
              <strong>推迟再议（Deferred）：</strong> 已记录触发条件，条件满足前 Agent 不得提前编码实施。
            </div>
          ` : ""}

          ${wf === "superseded" ? `
            <div class="composer-banner" style="margin-top: 4px; margin-bottom: 0;">
              <strong>已被替代（Superseded）：</strong> 原结论仅供历史追溯。${replacement ? `当前替代议题：${replacementHtml}` : ""}
            </div>
          ` : ""}

          ${topic.impl_commit || topic.impl_verifier || topic.impl_summary ? `
            <div style="margin-top: 4px; padding: 4px 10px; background: var(--canvas-default); border: 1px solid var(--border-default); border-radius: 6px; font-size: 12px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
              <span><strong>落地核验：</strong></span>
              ${topic.impl_commit ? `<span>提交/PR: <code>${escapeHtml(topic.impl_commit)}</code></span>` : ""}
              ${topic.impl_verifier ? `<span>核验人: <strong>${escapeHtml(topic.impl_verifier)}</strong></span>` : ""}
              ${topic.verified_at ? `<span style="color: var(--fg-muted);">${escapeHtml(topic.verified_at)}</span>` : ""}
              ${topic.impl_summary ? `<span style="color: var(--fg-muted);">摘要: ${escapeHtml(topic.impl_summary)}</span>` : ""}
            </div>
          ` : ""}
        </div>

        <!-- Zone 2: Independently Scrollable Reading & Discussion Area -->
        <div class="detail-cockpit-body">
          <div class="detail-reading-column">
            <!-- Inline Interactive Agent-Question Card right at the top of the reading area -->
            <div id="wb-reading-question" class="agent-question-box" hidden></div>

            <details class="detail-section-card" open>
              <summary class="detail-section-summary">
                <span>核心提案正文与架构背景</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                  ${(cachedDetail?.sources || topic.sources) ? `<span class="mono" style="font-size: 11px; color: var(--fg-muted);">锚点: ${escapeHtml(cachedDetail?.sources || topic.sources)}</span>` : ""}
                  <button type="button" class="btn btn-secondary btn-sm" data-composer-tab="proposal" data-topic-id="${escapeHtml(topic.id)}" onclick="event.stopPropagation();">改正文/分类</button>
                </div>
              </summary>
              <div class="detail-proposal-content markdown-body" id="workbench-proposal-body">
                ${cachedDetail
                  ? (coreProposalMd ? renderMarkdown(coreProposalMd) : '<p style="color: var(--fg-muted);">（暂无提案正文，可点击右上角「改正文/分类」补充）</p>')
                  : `<div style="color: var(--fg-muted); font-size: 13px;">正在加载完整提案正文与历史轮次...</div>`}
              </div>
            </details>

            <details class="detail-section-card" open>
              <summary class="detail-section-summary">
                <span>多轮讨论与决策时间线（共 ${escapeHtml(roundsCount)} 轮）</span>
                <span style="font-size: 12px; color: var(--fg-muted); font-weight: 400;">保留历次原话，最新轮次优先</span>
              </summary>
              <div class="detail-timeline-content" id="workbench-timeline-body">
                ${cachedDetail
                  ? renderRoundsTimelineHtml(roundsList, topic.id, canAmend)
                  : `<div style="color: var(--fg-muted); font-size: 13px; padding: 12px 0;">正在同步讨论轮次记录...</div>`}
              </div>
            </details>
          </div>
        </div>

        <!-- Zone 3: Pinned Bottom Collapsible Action Dock (Zero Scroll to Act) -->
        <div class="cockpit-action-dock${state.dockExpanded ? "" : " dock-collapsed"}" id="workbench-composer-card">
          <div class="cockpit-dock-bar">
            <div class="composer-tabs-bar" role="tablist">
              <button type="button" class="composer-tab-btn${activeTab === "append" ? " active" : ""}" data-composer-tab="append" data-topic-id="${escapeHtml(topic.id)}">
                追加拍板 (第 ${escapeHtml(roundsCount + 1)} 轮)
              </button>
              ${canAmend ? `
                <button type="button" class="composer-tab-btn${activeTab === "amend" ? " active" : ""}" data-composer-tab="amend" data-topic-id="${escapeHtml(topic.id)}">
                  更正第 ${escapeHtml(roundsCount)} 轮
                </button>
              ` : ""}
              <button type="button" class="composer-tab-btn${activeTab === "proposal" ? " active" : ""}" data-composer-tab="proposal" data-topic-id="${escapeHtml(topic.id)}">
                改正文/分类
              </button>
              <button type="button" class="composer-tab-btn${activeTab === "verify" ? " active" : ""}" data-composer-tab="verify" data-topic-id="${escapeHtml(topic.id)}">
                登记核验
              </button>
            </div>

            <div class="dock-quick-controls">
              <div class="dock-quick-outcomes" title="快捷拍板：点击自动展开底部工作台或直接保存">
                <button type="button" class="tactile-pill pill-success${curOut === "accepted" ? " active" : ""}" data-dock-quick-outcome="accepted">${iconSvg("check")}<span>采纳</span></button>
                <button type="button" class="tactile-pill pill-warning${curOut === "partially_accepted" ? " active" : ""}" data-dock-quick-outcome="partially_accepted">${iconSvg("half")}<span>部分同意</span></button>
                <button type="button" class="tactile-pill pill-danger${curOut === "rejected" ? " active" : ""}" data-dock-quick-outcome="rejected">${iconSvg("x")}<span>否决</span></button>
                <button type="button" class="tactile-pill${curWf === "deferred" ? " active" : ""}" data-dock-quick-workflow="deferred">${iconSvg("pause")}<span>推迟</span></button>
              </div>
              <button type="button" class="btn btn-primary btn-sm" id="btn-dock-quick-save" title="立即保存当前状态与意见 (Ctrl+Enter)">保存</button>
              <button type="button" class="btn btn-secondary btn-sm" id="btn-toggle-dock" aria-expanded="${state.dockExpanded ? "true" : "false"}">
                ${state.dockExpanded ? "收起面板" : "展开拍板台"}
              </button>
            </div>
          </div>

          <div class="cockpit-dock-drawer" id="cockpit-dock-drawer">
            <div id="workbench-conflict-banner" class="conflict-banner" style="display: none; margin: 0 auto 10px; max-width: 920px;"></div>
            <div class="composer-tab-body">
              ${renderComposerTabBodyHtml(topic, session, activeTab, cachedDetail)}
            </div>
          </div>
        </div>
      </div>
    `;

    renderMermaidDiagrams(pane);
    bindWorkbenchComposerEvents(topic, session, activeTab, cachedDetail);

    if (!cachedDetail) {
      fetchTopicDetail(topic.id).then((detail) => {
        if (!detail || state.selectedTopicId !== topic.id) return;
        const propEl = document.getElementById("workbench-proposal-body");
        if (propEl) {
          propEl.innerHTML = detail.core_content
            ? renderMarkdown(detail.core_content)
            : '<p style="color: var(--fg-muted);">（暂无提案正文，可点击右上角「改正文/分类」补充）</p>';
          renderMermaidDiagrams(propEl);
        }
        const tlEl = document.getElementById("workbench-timeline-body");
        if (tlEl) {
          tlEl.innerHTML = renderRoundsTimelineHtml(detail.rounds || [], topic.id, canAmend);
          renderMermaidDiagrams(tlEl);
          tlEl.querySelectorAll("[data-composer-tab]").forEach((btn) => {
            btn.addEventListener("click", () => {
              state.composerMode = btn.dataset.composerTab;
              state.dockExpanded = true;
              persistLayoutPrefs();
              renderWorkbenchDetailPane(topic);
            });
          });
        }
        const propTextarea = document.getElementById("wb-proposal-content");
        if (propTextarea && !session.proposalTouched) {
          session.fields.content_override = detail.core_content || "";
          propTextarea.value = session.fields.content_override;
        }
        const sourcesInput = document.getElementById("wb-proposal-sources");
        if (sourcesInput && !session.proposalTouched) {
          session.fields.sources = detail.sources || topic.sources || "";
          sourcesInput.value = session.fields.sources;
        }
      });
    }
  }

  function renderThreeAxisControlsHtml(prefix, fields) {
    const wf = fields.workflow_state || "discussing";
    const out = fields.decision_outcome ?? "";
    const impl = fields.implementation_state || "not_started";
    const isRejected = out === "rejected";
    const isSuperseded = wf === "superseded";

    return `
      <div class="three-axis-grid">
        <div class="axis-box">
          <div class="axis-box-title">1. 工作流进展 (Workflow)</div>
          <div class="tactile-pill-group" id="${prefix}-wf-pills">
            <button type="button" class="tactile-pill${wf === "discussing" ? " active" : ""}" data-axis="workflow_state" data-value="discussing">待讨论</button>
            <button type="button" class="tactile-pill${wf === "pending" ? " active" : ""}" data-axis="workflow_state" data-value="pending">待决策</button>
            <button type="button" class="tactile-pill${wf === "decided" ? " active" : ""}" data-axis="workflow_state" data-value="decided">${iconSvg("check")}<span>已决策</span></button>
            <button type="button" class="tactile-pill${wf === "deferred" ? " active" : ""}" data-axis="workflow_state" data-value="deferred">推迟再议</button>
            <button type="button" class="tactile-pill${wf === "superseded" ? " active" : ""}" data-axis="workflow_state" data-value="superseded">已被替代</button>
          </div>
        </div>

        <div class="axis-box">
          <div class="axis-box-title">2. 决策结论 (Outcome)</div>
          <div class="tactile-pill-group" id="${prefix}-out-pills">
            <button type="button" class="tactile-pill${out === "" ? " active" : ""}" data-axis="decision_outcome" data-value="">尚无结论</button>
            <button type="button" class="tactile-pill pill-success${out === "accepted" ? " active" : ""}" data-axis="decision_outcome" data-value="accepted">${iconSvg("check")}<span>同意采纳</span></button>
            <button type="button" class="tactile-pill pill-warning${out === "partially_accepted" ? " active" : ""}" data-axis="decision_outcome" data-value="partially_accepted">${iconSvg("half")}<span>部分同意</span></button>
            <button type="button" class="tactile-pill pill-danger${out === "rejected" ? " active" : ""}" data-axis="decision_outcome" data-value="rejected">${iconSvg("x")}<span>明确否决</span></button>
          </div>
          <div id="${prefix}-outcome-hint" class="form-hint" style="margin-top: 4px; font-size: 11px; color: var(--fg-muted); display: none;"></div>
        </div>

        <div class="axis-box">
          <div class="axis-box-title">3. 代码实现状态 (Implementation)</div>
          <div class="tactile-pill-group" id="${prefix}-impl-pills">
            <button type="button" class="tactile-pill${impl === "not_started" ? " active" : ""}" data-axis="implementation_state" data-value="not_started">未开始</button>
            <button type="button" class="tactile-pill${impl === "in_progress" ? " active" : ""}" data-axis="implementation_state" data-value="in_progress">进行中</button>
            <button type="button" class="tactile-pill pill-success${impl === "implemented" ? " active" : ""}" data-axis="implementation_state" data-value="implemented">已实现</button>
            <button type="button" class="tactile-pill pill-verified${impl === "verified" ? " active" : ""}" data-axis="implementation_state" data-value="verified">${iconSvg("shield")}<span>已核验</span></button>
          </div>
        </div>
      </div>

      <div id="${prefix}-rejection-block" class="conditional-field-box danger-box" style="display: ${isRejected ? "block" : "none"}; margin-top: 8px;">
        <label class="form-label" for="${prefix}-rejection-reason" style="color: var(--danger-fg);">明确否决原因（必填，将写入 Agent 禁止触碰红线清单）</label>
        <input type="text" id="${prefix}-rejection-reason" class="form-input" value="${escapeHtml(fields.rejection_reason || "")}" placeholder="请简明扼要说明否决原因，防止 Agent 再次生成同类方案...">
      </div>

      <div id="${prefix}-superseded-block" class="conditional-field-box" style="display: ${(isSuperseded || fields.superseded_by) ? "block" : "none"}; margin-top: 8px;">
        <label class="form-label" for="${prefix}-superseded-by">替代议题 ID 或说明（选填，例如新议题 slug）</label>
        <input type="text" id="${prefix}-superseded-by" class="form-input" list="datalist-topic-ids" value="${escapeHtml(fields.superseded_by || "")}" placeholder="例如: new-storage-engine">
      </div>
    `;
  }

  function renderComposerTabBodyHtml(topic, session, activeTab, cachedDetail) {
    const f = session.fields;
    const roundsCount = topic.rounds_count ?? 0;

    if (activeTab === "append" || activeTab === "amend") {
      const isAmend = activeTab === "amend";
      return `
        ${renderThreeAxisControlsHtml("wb", f)}

        <div id="wb-agent-question" class="agent-question-box" hidden style="margin-top: 8px;"></div>

        <div class="composer-split-inputs" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; margin-top: 8px;">
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label" for="wb-user-opinion">
              ${isAmend ? `更正第 ${escapeHtml(roundsCount)} 轮用户意见` : "新增用户拍板意见 / 批注原话"}
            </label>
            <textarea id="wb-user-opinion" class="form-textarea" rows="3" style="min-height: 68px;" placeholder="支持多行 Markdown。若选择部分同意，请写明同意与保留的具体范围...">${escapeHtml(f.new_user_opinion || "")}</textarea>
          </div>

          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label" for="wb-agent-reply">
              ${isAmend ? `更正第 ${escapeHtml(roundsCount)} 轮 Agent 答复` : "新增 Agent 落实答复（支持 agent-question 围栏）"}
            </label>
            <textarea id="wb-agent-reply" class="form-textarea" rows="3" style="min-height: 68px;" placeholder="记录 Agent 的分析或执行承诺...">${escapeHtml(f.new_agent_reply || "")}</textarea>
          </div>
        </div>

        <details class="optional-details-box" style="margin-top: 8px; padding: 6px 10px;">
          <summary style="font-size: 12px;">附加实现提交引用 / 归档版本备注（选填）</summary>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin-top: 8px;">
            <div class="form-group" style="margin-bottom: 0;">
              <label class="form-label" for="wb-impl-commit">关联实现 Commit / PR 引用</label>
              <input type="text" id="wb-impl-commit" class="form-input mono" value="${escapeHtml(f.impl_commit || "")}" placeholder="例如: a1b2c3d 或 PR #42">
            </div>
            <div class="form-group" style="margin-bottom: 0;">
              <label class="form-label" for="wb-commit-msg">归档版本备注 / Commit Message</label>
              <input type="text" id="wb-commit-msg" class="form-input" value="${escapeHtml(f.commit_message || "")}" placeholder="简述本次决策或变更重点...">
            </div>
          </div>
        </details>

        <div class="composer-footer-actions" style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border-muted);">
          <span style="font-size: 12px; color: var(--fg-muted);">基准版本: <code class="mono">v${escapeHtml(session.baseVersion)}</code> · ${isAmend ? "更正最近一轮不空增轮次" : "仅改状态不填文字不会空增轮次"} · <kbd>Ctrl+Enter</kbd></span>
          <div style="display: flex; gap: 8px;">
            <button type="button" class="btn btn-secondary btn-sm" id="wb-btn-reset-draft">重置草稿</button>
            <button type="button" class="btn btn-primary btn-sm" id="wb-btn-save">${isAmend ? "保存本轮更正" : "保存决策与讨论"}</button>
          </div>
        </div>
      `;
    }

    if (activeTab === "proposal") {
      const proposalValue = session.proposalTouched
        ? f.content_override
        : (cachedDetail ? (cachedDetail.core_content || "") : f.content_override);
      const sourcesValue = session.proposalTouched
        ? f.sources
        : (cachedDetail ? (cachedDetail.sources || topic.sources || "") : (f.sources || ""));

      return `
        <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 10px; margin-bottom: 8px;">
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label" for="wb-proposal-title">议题标题</label>
            <input type="text" id="wb-proposal-title" class="form-input" value="${escapeHtml(f.title || topic.title || "")}">
          </div>
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label" for="wb-proposal-sources">代码/文档锚点 (Sources)</label>
            <input type="text" id="wb-proposal-sources" class="form-input mono" value="${escapeHtml(sourcesValue)}" placeholder="core/decision_service.py">
          </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; margin-bottom: 8px;">
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label" for="wb-proposal-section">所属章节 (Section)</label>
            <input type="text" id="wb-proposal-section" class="form-input" list="datalist-sections" value="${escapeHtml(f.section || topic.section || "架构设计与工程规范")}">
          </div>
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label" for="wb-proposal-object">架构对象 (Object)</label>
            <input type="text" id="wb-proposal-object" class="form-input" list="datalist-objects" value="${escapeHtml(f.object || topic.object || "通用")}">
          </div>
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label" for="wb-proposal-function">业务功能 (Function)</label>
            <input type="text" id="wb-proposal-function" class="form-input" list="datalist-functions" value="${escapeHtml(f.function || topic.function || "规范")}">
          </div>
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label" for="wb-proposal-priority">优先级 (Priority)</label>
            <select id="wb-proposal-priority" class="form-select">
              ${["最高", "高", "普通", "低"].map((p) => `<option value="${escapeHtml(p)}" ${(f.priority || topic.priority || "普通") === p ? "selected" : ""}>${escapeHtml(p)}</option>`).join("")}
            </select>
          </div>
        </div>

        <div class="form-group" style="margin-bottom: 0;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <label class="form-label" for="wb-proposal-content" style="margin-bottom: 0;">核心提案正文 (Markdown)</label>
            <button type="button" class="btn btn-secondary btn-sm" id="wb-btn-toggle-preview">切换预览</button>
          </div>
          <textarea id="wb-proposal-content" class="form-textarea mono" rows="5" placeholder="在此编写方案背景、核心设计约束、Mermaid 流程图或对比表格...">${escapeHtml(proposalValue)}</textarea>
          <div id="wb-proposal-preview" class="markdown-body" hidden style="margin-top: 8px; padding: 12px; background: var(--canvas-default); border: 1px solid var(--border-default); border-radius: 6px; max-height: 240px; overflow-y: auto;"></div>
        </div>

        <div class="composer-footer-actions" style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border-muted);">
          <span style="font-size: 12px; color: var(--fg-muted);">基准版本: <code class="mono">v${escapeHtml(session.baseVersion)}</code> · 同步更新 <code>decisions/${escapeHtml(topic.id)}.md</code></span>
          <button type="button" class="btn btn-primary btn-sm" id="wb-btn-save-proposal">保存提案正文与元数据</button>
        </div>
      `;
    }

    // activeTab === "verify"
    const isVerified = (topic.implementation_state || "") === "verified";
    return `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 8px;">
        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label" for="wb-verify-commit">实现提交 SHA / PR 编号（必填）</label>
          <input type="text" id="wb-verify-commit" class="form-input mono" value="${escapeHtml(topic.impl_commit || f.impl_commit || "")}" placeholder="例如: 8f3a19c 或 PR #108">
        </div>
        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label" for="wb-verify-verifier">核验人 / 验证主体</label>
          <input type="text" id="wb-verify-verifier" class="form-input" value="${escapeHtml(topic.impl_verifier || "developer")}" placeholder="CyberNova / CI-Runner">
        </div>
      </div>

      <div class="form-group" style="margin-bottom: 8px;">
        <label class="form-label" for="wb-verify-summary">核验证据与回归测试摘要（选填）</label>
        <textarea id="wb-verify-summary" class="form-textarea" rows="2" style="min-height: 54px;" placeholder="例如: 单元测试与前端回归全部通过...">${escapeHtml(topic.impl_summary || "")}</textarea>
      </div>

      <div class="composer-footer-actions" style="display: flex; justify-content: space-between; align-items: center; padding-top: 8px; border-top: 1px solid var(--border-muted); flex-wrap: wrap; gap: 8px;">
        <label style="font-size: 12px; display: inline-flex; align-items: center; gap: 6px; cursor: pointer;">
          <input type="checkbox" id="wb-verify-mark-verified" ${isVerified || topic.implementation_state !== "implemented" ? "checked" : ""}>
          <span>直接标记为 <strong>已核验 (verified)</strong>（取消勾选则仅标记为 已实现）</span>
        </label>
        <button type="button" class="btn btn-primary btn-sm" id="wb-btn-submit-verify">提交核验凭据</button>
      </div>
    `;
  }

  function bindThreeAxisEvents(prefix, session) {
    const syncBlocks = () => {
      const wf = session.fields.workflow_state;
      const out = session.fields.decision_outcome;
      const impl = session.fields.implementation_state;

      document.querySelectorAll(`#${prefix}-wf-pills .tactile-pill`).forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.value === wf);
      });
      document.querySelectorAll(`#${prefix}-out-pills .tactile-pill`).forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.value === out);
      });
      document.querySelectorAll(`#${prefix}-impl-pills .tactile-pill`).forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.value === impl);
      });

      document.querySelectorAll("[data-dock-quick-outcome]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.dockQuickOutcome === out);
      });
      document.querySelectorAll("[data-dock-quick-workflow]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.dockQuickWorkflow === wf);
      });

      const rejBlock = document.getElementById(`${prefix}-rejection-block`);
      if (rejBlock) rejBlock.style.display = out === "rejected" ? "block" : "none";

      const supBlock = document.getElementById(`${prefix}-superseded-block`);
      if (supBlock) supBlock.style.display = (wf === "superseded" || session.fields.superseded_by) ? "block" : "none";
    };

    ["wf", "out", "impl"].forEach((grp) => {
      const container = document.getElementById(`${prefix}-${grp}-pills`);
      if (!container) return;
      container.querySelectorAll(".tactile-pill").forEach((btn) => {
        btn.addEventListener("click", () => {
          const axis = btn.dataset.axis;
          const val = btn.dataset.value;
          session.fields[axis] = val;
          session.pendingRequest = null;
          if (axis === "decision_outcome" && val && (session.fields.workflow_state === "discussing" || session.fields.workflow_state === "pending")) {
            session.fields.workflow_state = "decided";
          }
          syncBlocks();
        });
      });
    });

    const rejInput = document.getElementById(`${prefix}-rejection-reason`);
    rejInput?.addEventListener("input", () => {
      session.fields.rejection_reason = rejInput.value;
      session.pendingRequest = null;
    });
    const supInput = document.getElementById(`${prefix}-superseded-by`);
    supInput?.addEventListener("input", () => {
      session.fields.superseded_by = supInput.value;
      session.pendingRequest = null;
    });

    syncBlocks();
  }

  function bindWorkbenchComposerEvents(topic, session, activeTab, cachedDetail) {
    document.getElementById("btn-mobile-back")?.addEventListener("click", () => {
      closeMobileDetail();
    });

    document.getElementById("btn-toggle-dock")?.addEventListener("click", () => {
      state.dockExpanded = !state.dockExpanded;
      persistLayoutPrefs();
      const dock = document.getElementById("workbench-composer-card");
      const btn = document.getElementById("btn-toggle-dock");
      if (dock) dock.classList.toggle("dock-collapsed", !state.dockExpanded);
      if (btn) {
        btn.setAttribute("aria-expanded", state.dockExpanded ? "true" : "false");
        btn.textContent = state.dockExpanded ? "收起面板" : "展开拍板台";
      }
    });

    document.querySelectorAll("#topic-detail-pane [data-composer-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nextTab = btn.dataset.composerTab;
        if (state.composerMode === nextTab && state.dockExpanded && btn.closest(".cockpit-dock-bar")) {
          state.dockExpanded = false;
        } else {
          state.composerMode = nextTab;
          state.dockExpanded = true;
        }
        persistLayoutPrefs();
        renderWorkbenchDetailPane(topic);
      });
    });

    // Quick outcome pills on the pinned dock bar
    document.querySelectorAll("#topic-detail-pane [data-dock-quick-outcome]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const val = btn.dataset.dockQuickOutcome;
        session.fields.decision_outcome = val;
        if (val && (session.fields.workflow_state === "discussing" || session.fields.workflow_state === "pending")) {
          session.fields.workflow_state = "decided";
        }
        session.pendingRequest = null;
        state.composerMode = "append";
        state.dockExpanded = true;
        persistLayoutPrefs();
        renderWorkbenchDetailPane(topic);
        if (val === "rejected") {
          document.getElementById("wb-rejection-reason")?.focus();
        } else if (val === "partially_accepted") {
          document.getElementById("wb-user-opinion")?.focus();
        }
      });
    });

    document.querySelectorAll("#topic-detail-pane [data-dock-quick-workflow]").forEach((btn) => {
      btn.addEventListener("click", () => {
        session.fields.workflow_state = btn.dataset.dockQuickWorkflow;
        session.pendingRequest = null;
        state.composerMode = "append";
        state.dockExpanded = true;
        persistLayoutPrefs();
        renderWorkbenchDetailPane(topic);
      });
    });

    document.getElementById("btn-dock-quick-save")?.addEventListener("click", () => {
      if (activeTab === "verify") {
        submitVerification(topic.id);
      } else {
        if (activeTab === "proposal") session.proposalTouched = true;
        submitTopicSave(topic.id, session, "workbench");
      }
    });

    // Render interactive agent-question in the reading area, and a compact status bar in the dock
    const updateDockQuestionSummary = () => {
      const dockQ = document.getElementById("wb-agent-question");
      if (!dockQ) return;
      if (!session || !session.question) {
        dockQ.hidden = true;
        dockQ.innerHTML = "";
        return;
      }
      dockQ.hidden = false;
      const selIdx = session.questionSelected;
      const selOpt = (selIdx !== null && selIdx !== undefined) ? session.question.options[selIdx] : null;
      dockQ.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: 12px;">
          <span>
            <strong>待拍板提问：</strong>
            ${selOpt
              ? `<span style="color: var(--success-fg); font-weight: 600;">已选「${escapeHtml(selOpt.label)}」</span>`
              : `<span style="color: var(--attention-fg);">尚未点选候选方案（可在上方问题卡片中点选，或直接填写下方拍板意见）</span>`}
          </span>
          ${selOpt ? `<button type="button" class="btn btn-secondary btn-sm" id="wb-clear-q-sel">取消点选</button>` : ""}
        </div>
      `;
      document.getElementById("wb-clear-q-sel")?.addEventListener("click", () => {
        session.questionSelected = null;
        session.pendingRequest = null;
        syncBothQuestionBoxes();
      });
    };

    const syncBothQuestionBoxes = () => {
      renderAgentQuestionInto("wb-reading-question", session, () => {
        updateDockQuestionSummary();
        if (!state.dockExpanded) {
          state.dockExpanded = true;
          persistLayoutPrefs();
          const dock = document.getElementById("workbench-composer-card");
          const btn = document.getElementById("btn-toggle-dock");
          if (dock) dock.classList.remove("dock-collapsed");
          if (btn) {
            btn.setAttribute("aria-expanded", "true");
            btn.textContent = "收起面板";
          }
        }
      });
      updateDockQuestionSummary();
    };
    syncBothQuestionBoxes();

    if (activeTab === "append" || activeTab === "amend") {
      bindThreeAxisEvents("wb", session);

      const userOp = document.getElementById("wb-user-opinion");
      userOp?.addEventListener("input", () => {
        session.fields.new_user_opinion = userOp.value;
        session.pendingRequest = null;
      });

      const agentRep = document.getElementById("wb-agent-reply");
      agentRep?.addEventListener("input", () => {
        session.fields.new_agent_reply = agentRep.value;
        session.pendingRequest = null;
        const parsed = window.DashboardAgentQuestion.parse(agentRep.value || "");
        if (parsed.question) {
          session.question = parsed.question;
          syncBothQuestionBoxes();
        }
      });

      const implCommit = document.getElementById("wb-impl-commit");
      implCommit?.addEventListener("input", () => {
        session.fields.impl_commit = implCommit.value;
        session.pendingRequest = null;
      });

      const commitMsg = document.getElementById("wb-commit-msg");
      commitMsg?.addEventListener("input", () => {
        session.fields.commit_message = commitMsg.value;
        session.pendingRequest = null;
      });

      document.getElementById("wb-btn-reset-draft")?.addEventListener("click", () => {
        state.draftsByTopic.delete(topic.id);
        renderTopicCards();
        showToast("已重置当前议题的未保存草稿", "info");
      });

      document.getElementById("wb-btn-save")?.addEventListener("click", () => {
        submitTopicSave(topic.id, session, "workbench");
      });
    } else if (activeTab === "proposal") {
      const markTouched = () => { session.proposalTouched = true; session.pendingRequest = null; };
      const titleInput = document.getElementById("wb-proposal-title");
      const secInput = document.getElementById("wb-proposal-section");
      const objInput = document.getElementById("wb-proposal-object");
      const fnInput = document.getElementById("wb-proposal-function");
      const prioSelect = document.getElementById("wb-proposal-priority");
      const srcInput = document.getElementById("wb-proposal-sources");
      const contentArea = document.getElementById("wb-proposal-content");
      const previewBox = document.getElementById("wb-proposal-preview");

      if (cachedDetail && !session.proposalTouched) {
        session.fields.content_override = cachedDetail.core_content || "";
        session.fields.sources = cachedDetail.sources || topic.sources || "";
      }

      titleInput?.addEventListener("input", () => { markTouched(); session.fields.title = titleInput.value; });
      secInput?.addEventListener("input", () => { markTouched(); session.fields.section = secInput.value; });
      objInput?.addEventListener("input", () => { markTouched(); session.fields.object = objInput.value; });
      fnInput?.addEventListener("input", () => { markTouched(); session.fields.function = fnInput.value; });
      prioSelect?.addEventListener("change", () => { markTouched(); session.fields.priority = prioSelect.value; });
      srcInput?.addEventListener("input", () => { markTouched(); session.fields.sources = srcInput.value; });
      contentArea?.addEventListener("input", () => {
        markTouched();
        session.fields.content_override = contentArea.value;
        if (previewBox && !previewBox.hidden) {
          previewBox.innerHTML = renderMarkdown(contentArea.value || "");
          renderMermaidDiagrams(previewBox);
        }
      });

      document.getElementById("wb-btn-toggle-preview")?.addEventListener("click", () => {
        if (!previewBox) return;
        previewBox.hidden = !previewBox.hidden;
        if (!previewBox.hidden) {
          previewBox.innerHTML = renderMarkdown(contentArea ? contentArea.value : "");
          renderMermaidDiagrams(previewBox);
        }
      });

      document.getElementById("wb-btn-save-proposal")?.addEventListener("click", () => {
        session.proposalTouched = true;
        if (titleInput) session.fields.title = titleInput.value;
        if (secInput) session.fields.section = secInput.value;
        if (objInput) session.fields.object = objInput.value;
        if (fnInput) session.fields.function = fnInput.value;
        if (prioSelect) session.fields.priority = prioSelect.value;
        if (srcInput) session.fields.sources = srcInput.value;
        if (contentArea) session.fields.content_override = contentArea.value;
        submitTopicSave(topic.id, session, "workbench");
      });
    } else if (activeTab === "verify") {
      document.getElementById("wb-btn-submit-verify")?.addEventListener("click", () => {
        submitVerification(topic.id);
      });
    }
  }

  // =========================================================================
  // Save, Verify, Delete & CAS Conflict Resolution
  // =========================================================================
  function validateSessionBeforeSave(topic, session) {
    const f = session.fields;
    if (f.decision_outcome === "rejected" && !(f.rejection_reason || "").trim()) {
      showToast("选择「明确否决」时，必须填写否决原因以供 Agent 避坑", "error");
      return false;
    }
    const composedOpinion = composeSessionOpinion(session).trim();
    const priorOutcome = getCanonicalOutcome(topic);
    if (f.decision_outcome === "partially_accepted" && priorOutcome !== "partially_accepted" && !composedOpinion) {
      showToast("选择「部分同意」时，请在用户意见中写明同意与保留的具体范围", "error");
      return false;
    }
    return true;
  }

  function renderConflictResolutionBanner(bannerId, topicId, session, conflictData, sourceContext) {
    const banner = document.getElementById(bannerId);
    if (!banner) return;
    const latest = conflictData.latest_topic || {};
    const latestVer = conflictData.current_version || latest.version || "?";

    banner.style.display = "block";
    banner.innerHTML = `
      <div style="font-weight: 600; color: var(--danger-fg); margin-bottom: 6px;">
        检测到并发版本冲突（本地基于 v${escapeHtml(session.baseVersion)}，服务端最新为 v${escapeHtml(latestVer)}）
      </div>
      <div style="font-size: 12px; color: var(--fg-muted); margin-bottom: 8px;">
        后台或其它终端刚刚更新了此议题。请核对服务端最新状态，选择保留您的草稿继续合并提交，或重新加载服务端最新内容：
      </div>
      <div style="font-size: 12px; padding: 8px; background: var(--canvas-default); border: 1px solid var(--border-default); border-radius: 6px; margin-bottom: 10px;">
        <div><strong>服务端当前状态：</strong>工作流 <code>${escapeHtml(latest.workflow_state || "")}</code> · 结论 <code>${escapeHtml(latest.decision_outcome || "尚无结论")}</code> · 实现 <code>${escapeHtml(latest.implementation_state || "not_started")}</code></div>
        ${latest.latest_round_user_opinion ? `<div style="margin-top: 4px;"><strong>服务端最新用户意见：</strong>${escapeHtml(latest.latest_round_user_opinion.slice(0, 120))}</div>` : ""}
        ${latest.latest_round_agent_reply ? `<div style="margin-top: 4px;"><strong>服务端最新 Agent 答复：</strong>${escapeHtml(latest.latest_round_agent_reply.slice(0, 120))}</div>` : ""}
      </div>
      <div style="display: flex; gap: 8px; flex-wrap: wrap;">
        <button type="button" class="btn btn-primary btn-sm" id="${bannerId}-adopt-base">对齐到最新基准版本 (v${escapeHtml(latestVer)}) 并保留我的草稿重新提交</button>
        <button type="button" class="btn btn-secondary btn-sm" id="${bannerId}-discard">放弃本地草稿并加载最新内容</button>
      </div>
    `;

    document.getElementById(`${bannerId}-adopt-base`)?.addEventListener("click", async () => {
      session.baseVersion = Number(latestVer);
      session.pendingRequest = null;
      session.conflict = null;
      banner.style.display = "none";
      await submitTopicSave(topicId, session, sourceContext);
    });

    document.getElementById(`${bannerId}-discard`)?.addEventListener("click", async () => {
      state.draftsByTopic.delete(topicId);
      delete state.topicsDetailCache[topicId];
      banner.style.display = "none";
      await loadMetadataList();
      showToast("已放弃本地冲突草稿并同步最新数据", "info");
    });
  }

  async function submitTopicSave(topicId, session, sourceContext = "workbench") {
    const topic = state.topicsMeta.find((t) => t.id === topicId);
    if (!topic) return false;
    if (session.submitting) return false;

    if (!validateSessionBeforeSave(topic, session)) {
      return false;
    }

    let requestId;
    let expectedVersion;
    let payload;

    if (session.pendingRequest && session.pendingRequest.requestId) {
      requestId = session.pendingRequest.requestId;
      expectedVersion = session.pendingRequest.expectedVersion;
      payload = session.pendingRequest.payload;
    } else {
      requestId = createRequestId("save");
      expectedVersion = session.baseVersion;
      payload = buildSavePayloadFromSession(session);
      payload.expected_version = expectedVersion;
      payload.request_id = requestId;
      session.pendingRequest = { requestId, expectedVersion, payload };
    }

    session.submitting = true;
    try {
      const res = await fetch(`${topicPath(topicId)}/save`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-Id": requestId,
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => ({}));

      if (res.status === 409) {
        session.conflict = data;
        const bannerId = sourceContext === "modal" ? "modal-conflict-banner" : "workbench-conflict-banner";
        renderConflictResolutionBanner(bannerId, topicId, session, data, sourceContext);
        showToast("版本冲突 (409)：请先核对服务端最新变更", "error");
        return false;
      }

      if (!res.ok) {
        session.pendingRequest = null;
        showToast(data.error || `保存失败 (HTTP ${res.status})`, "error");
        return false;
      }

      state.draftsByTopic.delete(topicId);
      delete state.topicsDetailCache[topicId];
      await loadMetadataList();

      const undoAction = data.prior_rev_id
        ? {
            text: "撤销此次修改",
            onClick: () => restoreSingleTopic(topicId, data.prior_rev_id),
          }
        : null;

      showToast(
        `已保存 #${topicId} (v${data.new_version || (expectedVersion + 1)})${(data.is_replay || data.idempotent_replay) ? " [幂等重放]" : ""}`,
        "success",
        undoAction
      );
      return true;
    } catch (err) {
      showToast(`网络异常，再次点击保存将使用原 Request ID 幂等重试：${err.message}`, "error");
      return false;
    } finally {
      session.submitting = false;
    }
  }

  async function submitVerification(topicId) {
    const topic = state.topicsMeta.find((t) => t.id === topicId);
    if (!topic) return;

    const commitInput = document.getElementById("wb-verify-commit");
    const verifierInput = document.getElementById("wb-verify-verifier");
    const summaryInput = document.getElementById("wb-verify-summary");
    const markVerifiedCheck = document.getElementById("wb-verify-mark-verified");

    const implCommit = (commitInput?.value || "").trim();
    if (!implCommit) {
      showToast("请填写关联实现 Commit SHA 或 PR 编号", "error");
      commitInput?.focus();
      return;
    }

    const requestId = createRequestId("verify");
    const payload = {
      impl_commit: implCommit,
      verifier: (verifierInput?.value || "developer").trim() || "developer",
      test_summary: (summaryInput?.value || "").trim(),
      mark_verified: markVerifiedCheck ? Boolean(markVerifiedCheck.checked) : true,
      expected_version: topic.version || 1,
      request_id: requestId,
    };

    try {
      const res = await fetch(`${topicPath(topicId)}/verify`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-Id": requestId,
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(data.error || `核验登记失败 (HTTP ${res.status})`, "error");
        return;
      }

      state.draftsByTopic.delete(topicId);
      delete state.topicsDetailCache[topicId];
      await loadMetadataList();
      showToast(
        `已登记 #${topicId} 实现核验 (${payload.mark_verified ? "已核验" : "已实现"} · v${data.new_version})`,
        "success",
        data.prior_rev_id
          ? { text: "撤销核验", onClick: () => restoreSingleTopic(topicId, data.prior_rev_id) }
          : null
      );
    } catch (err) {
      showToast(`核验请求异常：${err.message}`, "error");
    }
  }

  async function deleteTopic(topicId) {
    const topic = state.topicsMeta.find((t) => t.id === topicId);
    if (!topic) return;

    if (!window.confirm(`确定要归档移除议题「${topic.title}」(#${topic.id}) 吗？\n\n原 Markdown 文件将移入安全归档目录，并在 SQLite 保留历史快照，支持一键撤销恢复。`)) {
      return;
    }

    const requestId = createRequestId("del");
    const expectedVersion = topic.version || 1;
    try {
      const res = await fetch(`${topicPath(topicId)}/delete`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-Id": requestId,
        },
        body: JSON.stringify({
          expected_version: expectedVersion,
          request_id: requestId,
          reason: `控制台归档移除议题: ${topic.title}`,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(data.error || `移除议题失败 (HTTP ${res.status})`, "error");
        return;
      }

      state.draftsByTopic.delete(topicId);
      delete state.topicsDetailCache[topicId];
      if (state.selectedTopicId === topicId) {
        state.selectedTopicId = null;
      }
      await loadMetadataList();

      showToast(
        `已归档移除议题 #${topicId}`,
        "success",
        data.prior_rev_id
          ? {
              text: "撤销移除并恢复",
              onClick: () => restoreSingleTopic(topicId, data.prior_rev_id),
            }
          : null
      );
    } catch (err) {
      showToast(`移除请求异常：${err.message}`, "error");
    }
  }

  // =========================================================================
  // Grid/List Card Detail Expansion
  // =========================================================================
  function updateExpandButton() {
    const btn = document.getElementById("btn-toggle-all");
    if (!btn) return;
    const filtered = getFilteredTopics();
    const allExpanded = filtered.length > 0 && filtered.every((t) => state.expandedTopics.has(t.id));
    btn.textContent = allExpanded ? "收起全部" : "展开全部";
  }

  async function toggleCardDetails(topicId) {
    if (state.expandedTopics.has(topicId)) {
      state.expandedTopics.delete(topicId);
    } else {
      state.expandedTopics.add(topicId);
    }
    await refreshExpandedCards();
    updateExpandButton();
  }

  async function refreshExpandedCards() {
    for (const topic of state.topicsMeta) {
      const box = document.getElementById(`detail-body-${topic.id}`);
      const btnLabel = document.getElementById(`expand-btn-${topic.id}`);
      if (!box) continue;

      if (!state.expandedTopics.has(topic.id)) {
        box.style.display = "none";
        if (btnLabel) btnLabel.innerText = "展开详情";
        continue;
      }

      box.style.display = "block";
      if (btnLabel) btnLabel.innerText = "收起详情";
      const detail = await fetchTopicDetail(topic.id);
      if (!detail) continue;

      const rounds = detail.rounds || [];
      box.innerHTML = `
        <div style="margin-bottom: 10px;">
          <div style="font-size: 12px; font-weight: 600; color: var(--fg-muted); margin-bottom: 4px;">完整提案正文：</div>
          <div class="markdown-body">${renderMarkdown(detail.core_content || "暂无正文")}</div>
        </div>
        <div>
          <div style="font-size: 12px; font-weight: 600; color: var(--fg-muted); margin-bottom: 6px;">全部讨论轮次 (${rounds.length})：</div>
          ${renderRoundsTimelineHtml(rounds, topic.id, (topic.rounds_count || 0) > 0)}
        </div>
      `;
      renderMermaidDiagrams(box);
    }
  }

  function toggleExpandAll() {
    const filtered = getFilteredTopics();
    const allExpanded = filtered.length > 0 && filtered.every((t) => state.expandedTopics.has(t.id));
    if (allExpanded) {
      filtered.forEach((t) => state.expandedTopics.delete(t.id));
    } else {
      filtered.forEach((t) => state.expandedTopics.add(t.id));
    }
    refreshExpandedCards();
    updateExpandButton();
  }

  function copyTopicLink(topicId) {
    const topic = state.topicsMeta.find((t) => t.id === topicId);
    const title = topic ? topic.title : topicId;
    const text = `[${title}](decisions/${topicId}.md)`;
    navigator.clipboard?.writeText(text).then(() => {
      showToast(`已复制引用：${text}`, "success");
    }).catch(() => {
      showToast(`引用格式：${text}`, "info");
    });
  }

  // =========================================================================
  // Fullscreen Immersive Focus Review View (#review-view)
  // =========================================================================
  function getReviewTopicsList() {
    const scope = state.review.scope || "filtered";
    if (scope === "actionable") {
      return state.topicsMeta.filter((t) => isTopicActionable(t));
    }
    if (scope === "all") {
      return [...state.topicsMeta];
    }
    return getFilteredTopics();
  }

  function openReviewView(startTopicId = null, initialScope = null) {
    if (initialScope && ["filtered", "actionable", "all"].includes(initialScope)) {
      state.review.scope = initialScope;
    }
    let list = getReviewTopicsList();
    if (list.length === 0 && state.review.scope !== "all") {
      state.review.scope = "all";
      list = getReviewTopicsList();
    }
    if (list.length === 0) {
      showToast("当前没有可批阅的议题", "info");
      return;
    }

    const targetId = startTopicId || state.selectedTopicId;
    const idx = targetId ? list.findIndex((t) => t.id === targetId) : 0;
    state.review.index = idx >= 0 ? idx : 0;
    state.review.active = true;

    const rv = document.getElementById("review-view");
    if (rv) {
      rv.classList.add("open", "active");
      rv.setAttribute("aria-hidden", "false");
    }
    renderReview();
  }

  function closeReviewView() {
    state.review.active = false;
    const rv = document.getElementById("review-view");
    if (rv) {
      rv.classList.remove("open", "active");
      rv.setAttribute("aria-hidden", "true");
    }
    renderTopicCards();
  }

  function setReviewScope(scope) {
    if (!["filtered", "actionable", "all"].includes(scope)) return;
    const currentList = getReviewTopicsList();
    const currentTopic = currentList[state.review.index];
    state.review.scope = scope;
    const nextList = getReviewTopicsList();
    if (currentTopic) {
      const idx = nextList.findIndex((t) => t.id === currentTopic.id);
      state.review.index = idx >= 0 ? idx : 0;
    } else {
      state.review.index = 0;
    }
    renderReview();
  }

  function renderReviewChoicePills(containerId, options, currentVal, onSelect) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = options.map((opt) => {
      const active = opt.value === currentVal;
      return `<button type="button" class="tactile-pill ${opt.cls || ""}${active ? " active" : ""}" data-val="${escapeHtml(opt.value)}" aria-pressed="${active ? "true" : "false"}">${opt.icon ? iconSvg(opt.icon) : ""}<span>${escapeHtml(opt.label)}</span></button>`;
    }).join("");
    container.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => onSelect(btn.dataset.val));
    });
  }

  async function renderReview() {
    const list = getReviewTopicsList();
    const total = list.length;

    document.querySelectorAll("[data-review-scope]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.reviewScope === state.review.scope);
    });

    const idxEl = document.getElementById("review-index");
    const totalEl = document.getElementById("review-total");
    const idEl = document.getElementById("review-topic-id");
    const metaEl = document.getElementById("review-topic-meta");
    const titleEl = document.getElementById("review-topic-title");
    const detailBodyEl = document.getElementById("review-detail-body");
    const replyEl = document.getElementById("review-agent-reply");

    if (total === 0) {
      if (idxEl) idxEl.textContent = "00";
      if (totalEl) totalEl.textContent = "00";
      if (titleEl) titleEl.textContent = "当前批阅范围没有匹配的议题";
      if (detailBodyEl) detailBodyEl.innerHTML = `<p style="color: var(--fg-muted);">请点击顶部切换至「全部议题」。</p>`;
      return;
    }

    if (state.review.index >= total) state.review.index = total - 1;
    if (state.review.index < 0) state.review.index = 0;

    const topic = list[state.review.index];
    const session = getOrCreateSession(topic);
    const f = session.fields;

    if (idxEl) idxEl.textContent = String(state.review.index + 1).padStart(2, "0");
    if (totalEl) totalEl.textContent = String(total).padStart(2, "0");
    if (idEl) idEl.textContent = `#${topic.id} · v${topic.version || 1}`;
    if (titleEl) titleEl.textContent = topic.title;
    if (metaEl) {
      const lcInfo = getLifecycleBadge(f.workflow_state);
      metaEl.innerHTML = `
        <span class="badge ${escapeHtml(lcInfo.badge_class)}">${escapeHtml(lcInfo.badge)}</span>
        <span class="chip">${escapeHtml(topic.object || "通用")} · ${escapeHtml(topic.function || "规范")}</span>
        <span class="chip">第 ${escapeHtml(topic.rounds_count || 0)} 轮</span>
      `;
    }

    // Overview Drawer inside Review View
    const overviewEl = document.getElementById("review-overview");
    if (overviewEl) {
      overviewEl.innerHTML = list.map((t, i) => `
        <button type="button" class="btn ${i === state.review.index ? "btn-primary" : "btn-secondary"} btn-sm" data-review-jump="${i}" style="text-align: left; justify-content: flex-start;">
          <span>${String(i + 1).padStart(2, "0")}. ${escapeHtml(t.title)}</span>
        </button>
      `).join("");
      overviewEl.querySelectorAll("[data-review-jump]").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.review.index = Number(btn.dataset.reviewJump);
          renderReview();
        });
      });
    }

    // 3-Axis Choice Options
    renderReviewChoicePills("review-workflow-options", [
      { value: "discussing", label: "待讨论" },
      { value: "pending", label: "待决策" },
      { value: "decided", label: "已决策", icon: "check" },
      { value: "deferred", label: "推迟再议" },
      { value: "superseded", label: "已被替代" },
    ], f.workflow_state, (val) => {
      f.workflow_state = val;
      session.pendingRequest = null;
      renderReview();
    });

    renderReviewChoicePills("review-outcome-options", [
      { value: "", label: "尚无结论" },
      { value: "accepted", label: "同意采纳", cls: "pill-success", icon: "check" },
      { value: "partially_accepted", label: "部分同意", cls: "pill-warning", icon: "half" },
      { value: "rejected", label: "明确否决", cls: "pill-danger", icon: "x" },
    ], f.decision_outcome, (val) => {
      f.decision_outcome = val;
      if (val && (f.workflow_state === "discussing" || f.workflow_state === "pending")) {
        f.workflow_state = "decided";
      }
      session.pendingRequest = null;
      renderReview();
    });

    renderReviewChoicePills("review-implementation-options", [
      { value: "not_started", label: "未开始" },
      { value: "in_progress", label: "进行中" },
      { value: "implemented", label: "已实现", cls: "pill-success" },
      { value: "verified", label: "已核验", cls: "pill-verified", icon: "shield" },
    ], f.implementation_state, (val) => {
      f.implementation_state = val;
      session.pendingRequest = null;
      renderReview();
    });

    // Conditional Rejection & Superseded inputs
    const rejGroup = document.getElementById("review-group-rejection");
    const rejInput = document.getElementById("review-rejection-reason-input");
    if (rejGroup) rejGroup.hidden = f.decision_outcome !== "rejected";
    if (rejInput && rejInput.value !== (f.rejection_reason || "")) rejInput.value = f.rejection_reason || "";

    const supGroup = document.getElementById("review-group-superseded");
    const supInput = document.getElementById("review-superseded-by-input");
    if (supGroup) supGroup.hidden = !(f.workflow_state === "superseded" || f.superseded_by);
    if (supInput && supInput.value !== (f.superseded_by || "")) supInput.value = f.superseded_by || "";

    // Append vs Amend mode switcher
    document.querySelectorAll("#review-mode-switcher [data-review-mode]").forEach((btn) => {
      const m = btn.dataset.reviewMode;
      btn.classList.toggle("active", m === session.editMode);
      if (m === "amend") btn.disabled = !(topic.rounds_count > 0);
    });

    // Agent Question & Reply
    renderAgentQuestionInto("review-agent-question", session);
    const parsedQ = parseTopicAgentQuestion(topic);
    if (replyEl) {
      replyEl.innerHTML = parsedQ.cleanReply
        ? renderMarkdown(parsedQ.cleanReply)
        : '<span style="color: var(--fg-muted);">（最新轮次暂无 Agent 落实答复）</span>';
      renderMermaidDiagrams(replyEl);
    }

    // Opinion & Auxiliary Inputs
    const opInput = document.getElementById("review-user-opinion-input");
    const implInput = document.getElementById("review-impl-commit-input");
    const msgInput = document.getElementById("review-commit-message-input");
    if (opInput && opInput.value !== (f.new_user_opinion || "")) opInput.value = f.new_user_opinion || "";
    if (implInput && implInput.value !== (f.impl_commit || "")) implInput.value = f.impl_commit || "";
    if (msgInput && msgInput.value !== (f.commit_message || "")) msgInput.value = f.commit_message || "";

    // Core Proposal & Timeline
    if (detailBodyEl) {
      const cached = state.topicsDetailCache[topic.id];
      if (cached) {
        detailBodyEl.innerHTML = `
          <div class="markdown-body">${renderMarkdown(cached.core_content || "暂无正文")}</div>
        `;
        renderMermaidDiagrams(detailBodyEl);
      } else {
        detailBodyEl.innerHTML = `<div class="markdown-body">${renderMarkdown(topic.summary || "正在加载完整提案正文...")}</div>`;
        fetchTopicDetail(topic.id).then((detail) => {
          if (!detail || !state.review.active) return;
          const currentNow = getReviewTopicsList()[state.review.index];
          if (currentNow?.id !== topic.id) return;
          detailBodyEl.innerHTML = `<div class="markdown-body">${renderMarkdown(detail.core_content || "暂无正文")}</div>`;
          renderMermaidDiagrams(detailBodyEl);
        });
      }
    }
  }

  function prevReviewTopic() {
    const list = getReviewTopicsList();
    if (!list.length) return;
    state.review.index = (state.review.index - 1 + list.length) % list.length;
    renderReview();
  }

  function nextReviewTopic() {
    const list = getReviewTopicsList();
    if (!list.length) return;
    state.review.index = (state.review.index + 1) % list.length;
    renderReview();
  }

  async function submitReview(advanceNext = false) {
    const list = getReviewTopicsList();
    const topic = list[state.review.index];
    if (!topic) return;
    const session = getOrCreateSession(topic);

    const rejInput = document.getElementById("review-rejection-reason-input");
    const supInput = document.getElementById("review-superseded-by-input");
    const opInput = document.getElementById("review-user-opinion-input");
    const implInput = document.getElementById("review-impl-commit-input");
    const msgInput = document.getElementById("review-commit-message-input");

    if (rejInput) session.fields.rejection_reason = rejInput.value;
    if (supInput) session.fields.superseded_by = supInput.value;
    if (opInput) session.fields.new_user_opinion = opInput.value;
    if (implInput) session.fields.impl_commit = implInput.value;
    if (msgInput) session.fields.commit_message = msgInput.value;

    const ok = await submitTopicSave(topic.id, session, "review");
    if (!ok) return;

    if (advanceNext) {
      const updatedList = getReviewTopicsList();
      if (updatedList.length > 0) {
        if (state.review.index >= updatedList.length) {
          state.review.index = 0;
        } else if (updatedList[state.review.index]?.id === topic.id) {
          state.review.index = (state.review.index + 1) % updatedList.length;
        }
      }
    }
    renderReview();
  }

  // =========================================================================
  // Legacy Edit Decision Modal (#modal-edit-decision)
  // =========================================================================
  function onOutcomeChanged() {
    const wf = document.getElementById("form-workflow-state")?.value || "discussing";
    const out = document.getElementById("form-decision-outcome")?.value || "";
    const supGroup = document.getElementById("group-superseded-by");
    const rejGroup = document.getElementById("group-rejection-reason");
    if (supGroup) supGroup.style.display = wf === "superseded" ? "block" : "none";
    if (rejGroup) rejGroup.style.display = out === "rejected" ? "block" : "none";
  }

  function openDecisionModal(topicId, mode = "append") {
    const topic = state.topicsMeta.find((t) => t.id === topicId);
    if (!topic) return;
    state.selectedTopicId = topicId;
    const session = getOrCreateSession(topic, mode);
    const f = session.fields;

    const idEl = document.getElementById("modal-topic-id");
    const verEl = document.getElementById("modal-topic-version");
    const catEl = document.getElementById("modal-topic-category");
    if (idEl) idEl.textContent = `#${topic.id}`;
    if (verEl) verEl.textContent = `v${topic.version || 1}`;
    if (catEl) catEl.textContent = `${topic.object || "通用"} · ${topic.function || "规范"}`;

    const setVal = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.value = v ?? "";
    };
    setVal("form-workflow-state", f.workflow_state);
    setVal("form-decision-outcome", f.decision_outcome);
    setVal("form-superseded-by", f.superseded_by);
    setVal("form-rejection-reason", f.rejection_reason);
    setVal("form-impl-state", f.implementation_state);
    setVal("form-impl-commit", f.impl_commit);
    setVal("form-user-opinion", f.new_user_opinion);
    setVal("form-agent-reply", f.new_agent_reply);
    setVal("form-commit-message", f.commit_message);

    onOutcomeChanged();
    openModal("modal-edit-decision");
  }

  async function submitDecision() {
    const topicId = state.selectedTopicId;
    const topic = state.topicsMeta.find((t) => t.id === topicId);
    if (!topic) return;
    const session = getOrCreateSession(topic);
    const f = session.fields;

    f.workflow_state = document.getElementById("form-workflow-state")?.value || "discussing";
    f.decision_outcome = document.getElementById("form-decision-outcome")?.value || "";
    f.superseded_by = document.getElementById("form-superseded-by")?.value || "";
    f.rejection_reason = document.getElementById("form-rejection-reason")?.value || "";
    f.implementation_state = document.getElementById("form-impl-state")?.value || "not_started";
    f.impl_commit = document.getElementById("form-impl-commit")?.value || "";
    f.new_user_opinion = document.getElementById("form-user-opinion")?.value || "";
    f.new_agent_reply = document.getElementById("form-agent-reply")?.value || "";
    f.commit_message = document.getElementById("form-commit-message")?.value || "";

    const ok = await submitTopicSave(topicId, session, "modal");
    if (ok) closeModal("modal-edit-decision");
  }

  // =========================================================================
  // Create New Topic Modal (#modal-create-topic)
  // =========================================================================
  function slugifyTitle(title) {
    const ascii = String(title || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 48);
    if (ascii.length >= 3) return ascii;
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    return `topic-${stamp}-${Math.floor(100 + Math.random() * 900)}`;
  }

  function openCreateModal() {
    state.createAutoSlug = true;
    openModal("modal-create-topic");
    document.getElementById("create-title")?.focus();
  }

  async function submitCreate() {
    if (state.creating) return;
    const titleInput = document.getElementById("create-title");
    const idInput = document.getElementById("create-id");
    const objInput = document.getElementById("create-object");
    const fnInput = document.getElementById("create-function");
    const secInput = document.getElementById("create-section");
    const prioSelect = document.getElementById("create-priority");
    const wfSelect = document.getElementById("create-workflow");
    const srcInput = document.getElementById("create-sources");
    const contentInput = document.getElementById("create-content");
    const userOpInput = document.getElementById("create-user-opinion");
    const agentRepInput = document.getElementById("create-agent-reply");

    const title = (titleInput?.value || "").trim();
    let topicId = (idInput?.value || "").trim();
    if (!topicId && title) {
      topicId = slugifyTitle(title);
      if (idInput) idInput.value = topicId;
    }

    if (!title || !topicId) {
      showToast("请填写议题标题与议题唯一标识 ID", "error");
      return;
    }
    if (!/^[a-zA-Z0-9_-]{1,128}$/.test(topicId)) {
      showToast("议题 ID 仅允许字母、数字、下划线或连字符", "error");
      return;
    }

    const requestId = state.createRequest || createRequestId("create");
    state.createRequest = requestId;
    state.creating = true;

    const payload = {
      id: topicId,
      title,
      object: (objInput?.value || "通用").trim() || "通用",
      function: (fnInput?.value || "规范").trim() || "规范",
      section: (secInput?.value || "架构设计与工程规范").trim() || "架构设计与工程规范",
      priority: prioSelect?.value || "普通",
      workflow_state: wfSelect?.value || "pending",
      sources: (srcInput?.value || "").trim(),
      content: contentInput?.value || "",
      content_override: contentInput?.value || "",
      new_user_opinion: (userOpInput?.value || "").trim(),
      new_agent_reply: (agentRepInput?.value || "").trim(),
      request_id: requestId,
    };

    try {
      const res = await fetch("/api/topic/create", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-Id": requestId,
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        state.createRequest = null;
        showToast(data.error || `创建议题失败 (HTTP ${res.status})`, "error");
        return;
      }

      state.createRequest = null;
      if (titleInput) titleInput.value = "";
      if (idInput) idInput.value = "";
      if (contentInput) contentInput.value = "";
      if (userOpInput) userOpInput.value = "";
      if (agentRepInput) agentRepInput.value = "";

      closeModal("modal-create-topic");
      state.selectedTopicId = topicId;
      await loadMetadataList();
      showToast(`已创建议题 #${topicId}`, "success");
    } catch (err) {
      showToast(`创建议题网络异常：${err.message}`, "error");
    } finally {
      state.creating = false;
    }
  }

  // =========================================================================
  // Parameterized Agent Context Extractor (#modal-agent-context)
  // =========================================================================
  function openAgentContextModal(prefillTopicId = "") {
    const topicInput = document.getElementById("ctx-filter-topic");
    if (topicInput && typeof prefillTopicId === "string") {
      topicInput.value = prefillTopicId;
    }
    openModal("modal-agent-context");
    refreshAgentContext();
  }

  async function refreshAgentContext() {
    const modVal = (document.getElementById("ctx-filter-module")?.value || "").trim();
    const pathVal = (document.getElementById("ctx-filter-path")?.value || "").trim();
    const topicVal = (document.getElementById("ctx-filter-topic")?.value || "").trim();
    const fmtVal = (document.getElementById("ctx-format")?.value || "markdown").trim();

    const params = new URLSearchParams();
    if (modVal) params.set("module", modVal);
    if (pathVal) params.set("path", pathVal);
    if (topicVal) params.set("topic_id", topicVal);

    const hookParts = ["python -m core.agent_hooks --config dashboard.config.json before-task"];
    if (modVal) hookParts.push(`--module "${modVal}"`);
    if (pathVal) hookParts.push(`--path "${pathVal}"`);
    if (topicVal) hookParts.push(`--topic "${topicVal}"`);
    const hookEl = document.getElementById("ctx-hook-cmd");
    if (hookEl) hookEl.textContent = hookParts.join(" ");

    const apiParams = new URLSearchParams(params);
    apiParams.set("format", fmtVal);
    const apiEl = document.getElementById("ctx-api-url");
    if (apiEl) apiEl.textContent = `GET /api/agent/context?${apiParams.toString()}`;

    const outTextarea = document.getElementById("agent-context-markdown");

    try {
      const jsonParams = new URLSearchParams(params);
      jsonParams.set("format", "json");
      const jsonRes = await fetch(`/api/agent/context?${jsonParams.toString()}`);
      const jsonData = await jsonRes.json().catch(() => ({}));

      const setStat = (id, arr) => {
        const el = document.getElementById(id);
        if (el) el.textContent = String((arr || []).length);
      };
      setStat("ctx-stat-active", jsonData.active_decisions);
      setStat("ctx-stat-rejected", jsonData.rejected_proposals);
      setStat("ctx-stat-pending", jsonData.pending_requirements);
      setStat("ctx-stat-deferred", jsonData.deferred_topics);
      setStat("ctx-stat-superseded", jsonData.superseded_topics);

      if (fmtVal === "json") {
        const txt = JSON.stringify(jsonData, null, 2);
        state.agentContextText = txt;
        if (outTextarea) outTextarea.value = txt;
      } else {
        const mdParams = new URLSearchParams(params);
        mdParams.set("format", "markdown");
        const mdRes = await fetch(`/api/agent/context?${mdParams.toString()}`);
        const mdText = await mdRes.text();
        state.agentContextText = mdText;
        if (outTextarea) outTextarea.value = mdText;
      }
    } catch (err) {
      if (outTextarea) outTextarea.value = `提取失败：${err.message}`;
    }
  }

  function copyAgentContext() {
    const text = state.agentContextText || document.getElementById("agent-context-markdown")?.value || "";
    if (!text) return;
    navigator.clipboard?.writeText(text).then(() => {
      showToast("已复制 Agent 上下文规范至剪贴板", "success");
    }).catch(() => {
      showToast("复制失败，请手动全选复制", "error");
    });
  }

  // =========================================================================
  // Ledger Health & Maintenance Modal (#modal-maintenance)
  // =========================================================================
  function openMaintenanceModal() {
    openModal("modal-maintenance");
    refreshMaintenanceReport();
  }

  async function refreshMaintenanceReport() {
    const container = document.getElementById("maintenance-report-container");
    if (container) container.innerHTML = `<div style="color: var(--fg-muted);">正在扫描磁盘 Markdown、SQLite 与 metadata.json...</div>`;

    try {
      const [statusRes, checkRes] = await Promise.all([
        fetch("/api/status", { cache: "no-store" }),
        fetch("/api/recovery/check", { cache: "no-store" }),
      ]);
      const statusData = await statusRes.json().catch(() => ({}));
      const checkData = await checkRes.json().catch(() => ({}));
      const consistent = Boolean(checkData.consistent);

      const missingDb = checkData.missing_in_db || [];
      const missingMd = checkData.missing_in_markdown || [];
      const mismatches = checkData.version_mismatches || checkData.content_mismatches || [];

      if (container) {
        container.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;">
            <div>
              <span class="badge ${consistent ? "badge-decided" : "badge-rejected"}" style="font-size: 13px; padding: 4px 10px;">
                ${consistent ? "三方存储完全一致 (Consistent)" : "检测到未同步文件或索引漂移"}
              </span>
            </div>
            <div style="font-size: 12px; color: var(--fg-muted);">
              议题总数: <strong>${escapeHtml(statusData.topics_count ?? state.topicsMeta.length)}</strong> ·
              历史快照: <strong>${escapeHtml(statusData.revisions_count ?? 0)}</strong>
            </div>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px;">
            <div style="padding: 10px; background: var(--canvas-default); border: 1px solid var(--border-default); border-radius: 6px;">
              <div style="font-size: 11px; color: var(--fg-muted);">未索引 Markdown 文件</div>
              <div style="font-size: 16px; font-weight: 600; margin-top: 2px;">${missingDb.length} 项</div>
            </div>
            <div style="padding: 10px; background: var(--canvas-default); border: 1px solid var(--border-default); border-radius: 6px;">
              <div style="font-size: 11px; color: var(--fg-muted);">缺失权威 Markdown</div>
              <div style="font-size: 16px; font-weight: 600; margin-top: 2px;">${missingMd.length} 项</div>
            </div>
            <div style="padding: 10px; background: var(--canvas-default); border: 1px solid var(--border-default); border-radius: 6px;">
              <div style="font-size: 11px; color: var(--fg-muted);">版本或内容漂移</div>
              <div style="font-size: 16px; font-weight: 600; margin-top: 2px;">${mismatches.length} 项</div>
            </div>
          </div>
        `;
      }
    } catch (err) {
      if (container) container.innerHTML = `<div style="color: var(--danger-fg);">检测异常：${escapeHtml(err.message)}</div>`;
    }
  }

  async function rebuildIndexFromMarkdown() {
    const resultBanner = document.getElementById("maintenance-action-result");
    try {
      const res = await fetch("/api/recovery/rebuild", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(data.error || "重建索引失败", "error");
        return;
      }
      state.topicsDetailCache = Object.create(null);
      await loadMetadataList();
      await refreshMaintenanceReport();
      if (resultBanner) {
        resultBanner.hidden = false;
        resultBanner.textContent = `已从权威 Markdown 重建 SQLite 索引与 metadata.json（共处理 ${data.rebuilt_count ?? state.topicsMeta.length} 项议题）。`;
      }
      showToast("已从权威 Markdown 重建索引", "success");
    } catch (err) {
      showToast(`重建索引失败：${err.message}`, "error");
    }
  }

  async function triggerDatabaseBackup() {
    const resultBanner = document.getElementById("maintenance-action-result");
    try {
      const res = await fetch("/api/backup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(data.error || "热备份失败", "error");
        return;
      }
      if (resultBanner) {
        resultBanner.hidden = false;
        resultBanner.textContent = `已完成 SQLite 在线一致性热备份：${data.backup_path || "backups/"}`;
      }
      showToast(`已生成在线热备份：${data.backup_path || "成功"}`, "success");
    } catch (err) {
      showToast(`热备份异常：${err.message}`, "error");
    }
  }

  // =========================================================================
  // Scoped Time Machine Drawer (#drawer-time-machine)
  // =========================================================================
  async function openTimeMachine(topicId = null) {
    if (topicId) {
      state.timeMachineTopicId = topicId;
      state.timeMachineScope = "topic";
    } else {
      state.timeMachineTopicId = state.selectedTopicId;
      state.timeMachineScope = "all";
    }
    syncTimeMachineButtons();
    openDrawer("drawer-time-machine");
    await renderTimeMachineRevisions();
  }

  function syncTimeMachineButtons() {
    document.getElementById("btn-tm-scope-topic")?.classList.toggle("active", state.timeMachineScope === "topic");
    document.getElementById("btn-tm-scope-all")?.classList.toggle("active", state.timeMachineScope === "all");
  }

  async function switchTimeMachineScope(scope) {
    state.timeMachineScope = scope;
    if (scope === "topic" && !state.timeMachineTopicId) {
      state.timeMachineTopicId = state.selectedTopicId || (state.topicsMeta[0]?.id ?? null);
    }
    syncTimeMachineButtons();
    await renderTimeMachineRevisions();
  }

  async function renderTimeMachineRevisions() {
    const container = document.getElementById("drawer-history-list");
    if (!container) return;
    container.innerHTML = `<div style="color: var(--fg-muted); font-size: 13px;">正在读取版本快照历史...</div>`;

    const filterTopicId = state.timeMachineScope === "topic" ? state.timeMachineTopicId : null;
    try {
      const query = filterTopicId ? `?topic_id=${encodeURIComponent(filterTopicId)}&limit=80` : `?limit=80`;
      const res = await fetch(`/api/revisions${query}`, { cache: "no-store" });
      const data = await res.json().catch(() => ({}));
      const revisions = data.revisions || [];

      if (revisions.length === 0) {
        container.innerHTML = `<div style="color: var(--fg-muted); font-size: 13px; padding: 16px 0;">暂无匹配的历史快照记录。</div>`;
        return;
      }

      container.innerHTML = revisions.map((rev) => {
        const tid = rev.topic_id || "";
        return `
          <div class="revision-item" style="padding: 12px; background: var(--canvas-subtle); border: 1px solid var(--border-default); border-radius: 6px; margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px;">
              <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <span class="chip mono">#rev-${escapeHtml(rev.rev_id)}</span>
                <span class="badge badge-decided">${escapeHtml(rev.action_type || "UPDATE")}</span>
                ${tid ? `<span class="chip mono">#${escapeHtml(tid)}</span>` : ""}
              </div>
              <span style="font-size: 11px; color: var(--fg-muted);">${escapeHtml(rev.timestamp || "")}</span>
            </div>
            <div style="font-size: 13px; color: var(--fg-default); margin-bottom: 8px;">
              ${escapeHtml(rev.summary || rev.reason || "版本快照")}
            </div>
            <div style="display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap;">
              ${tid ? `
                <button type="button" class="btn btn-secondary btn-sm" data-tm-action="restore-single" data-topic-id="${escapeHtml(tid)}" data-rev-id="${escapeHtml(rev.rev_id)}">
                  恢复此议题到此版本
                </button>
              ` : ""}
              <button type="button" class="btn btn-danger btn-sm" data-tm-action="rollback-all" data-rev-id="${escapeHtml(rev.rev_id)}">
                全库回滚到此快照点
              </button>
            </div>
          </div>
        `;
      }).join("");
    } catch (err) {
      container.innerHTML = `<div style="color: var(--danger-fg);">读取历史版本失败：${escapeHtml(err.message)}</div>`;
    }
  }

  async function restoreSingleTopic(topicId, revId) {
    const existing = state.topicsMeta.find((t) => t.id === topicId);
    const expectedVersion = existing ? existing.version : null;
    const requestId = createRequestId("restore");

    try {
      const body = { rev_id: Number(revId), request_id: requestId };
      if (expectedVersion !== null && expectedVersion !== undefined) {
        body.expected_version = expectedVersion;
      }
      const res = await fetch(`${topicPath(topicId)}/restore`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-Id": requestId,
        },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(data.error || `恢复议题失败 (HTTP ${res.status})`, "error");
        return;
      }

      state.draftsByTopic.delete(topicId);
      delete state.topicsDetailCache[topicId];
      state.selectedTopicId = topicId;
      await loadMetadataList();
      if (document.getElementById("drawer-time-machine")?.classList.contains("open")) {
        await renderTimeMachineRevisions();
      }
      showToast(`已将议题 #${topicId} 恢复至快照 #rev-${revId}`, "success");
    } catch (err) {
      showToast(`恢复请求异常：${err.message}`, "error");
    }
  }

  async function rollbackRevision(revId) {
    if (!window.confirm(`确定要将全库回滚到历史修订点 #rev-${revId} 吗？\n该时间点之后的变更将被还原（回滚前会自动生成保护快照）。`)) {
      return;
    }
    try {
      const res = await fetch(`/api/rollback/${encodeURIComponent(revId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(data.error || `全库回滚失败 (HTTP ${res.status})`, "error");
        return;
      }
      state.draftsByTopic.clear();
      state.topicsDetailCache = Object.create(null);
      await loadMetadataList();
      await renderTimeMachineRevisions();
      showToast(`已回滚至修订点 #rev-${revId}`, "success");
    } catch (err) {
      showToast(`回滚请求异常：${err.message}`, "error");
    }
  }

  // =========================================================================
  // Event Delegation & Initialization
  // =========================================================================
  function bindGlobalEvents() {
    initDayNightSwitch();
    applySidebarState();
    bindFilterPills(document);

    document.getElementById("btn-toggle-theme")?.addEventListener("click", () => {
      appearance.mode = appearance.mode === "dark" ? "light" : "dark";
      applyAppearance(true);
    });

    document.getElementById("btn-toggle-sidebar")?.addEventListener("click", () => toggleSidebar());
    document.getElementById("sidebar-backdrop")?.addEventListener("click", () => toggleSidebar(true));

    // Sidebar & Top Header view switchers
    document.querySelectorAll(".sidebar .nav-item[data-view], .header-view-tab[data-view]").forEach((item) => {
      item.addEventListener("click", () => switchView(item.dataset.view));
    });

    // Global Search
    const searchInput = document.getElementById("search-input");
    const clearSearchBtn = document.getElementById("btn-clear-search");
    searchInput?.addEventListener("input", () => {
      state.filters.searchQuery = searchInput.value.trim();
      if (clearSearchBtn) clearSearchBtn.hidden = !state.filters.searchQuery;
      renderActiveFiltersBar();
      renderTopicCards();
    });
    clearSearchBtn?.addEventListener("click", () => clearSingleFilter("searchQuery"));

    // Select Filters
    document.getElementById("function-filter")?.addEventListener("change", (e) => {
      state.filters.function = e.target.value;
      renderActiveFiltersBar();
      renderTopicCards();
    });
    document.getElementById("implementation-filter")?.addEventListener("change", (e) => {
      state.filters.implementation = e.target.value;
      renderActiveFiltersBar();
      renderTopicCards();
    });

    // Active Filter Chips
    document.getElementById("active-filters-bar")?.addEventListener("click", (e) => {
      const chip = e.target.closest("[data-clear-filter]");
      if (!chip) return;
      const key = chip.dataset.clearFilter;
      if (key === "all") resetFilters();
      else clearSingleFilter(key);
    });

    // Sort & View Modes
    document.getElementById("sort-select")?.addEventListener("change", (e) => setSortMode(e.target.value));
    document.getElementById("btn-view-split")?.addEventListener("click", () => setViewMode("split"));
    document.getElementById("btn-view-grid")?.addEventListener("click", () => setViewMode("grid"));
    document.getElementById("btn-view-list")?.addEventListener("click", () => setViewMode("list"));
    document.getElementById("btn-toggle-all")?.addEventListener("click", toggleExpandAll);
    document.getElementById("btn-refresh-topics")?.addEventListener("click", () => loadMetadataList());

    // Header Review Button
    document.getElementById("btn-review-view")?.addEventListener("click", () => openReviewView());

    // Delegated clicks inside #workbench-container
    document.getElementById("workbench-container")?.addEventListener("click", (e) => {
      const actionEl = e.target.closest("[data-action]");
      if (actionEl) {
        const action = actionEl.dataset.action;
        const topicId = actionEl.dataset.topicId;
        const composerMode = actionEl.dataset.composerMode;
        if (action === "select") {
          selectTopic(topicId);
        } else if (action === "open-workbench") {
          selectTopic(topicId, composerMode || "append");
        } else if (action === "copy") {
          copyTopicLink(topicId);
        } else if (action === "history") {
          openTimeMachine(topicId);
        } else if (action === "toggle") {
          toggleCardDetails(topicId);
        } else if (action === "context-topic") {
          openAgentContextModal(topicId);
        } else if (action === "review-from-here") {
          openReviewView(topicId);
        } else if (action === "delete-topic") {
          deleteTopic(topicId);
        } else if (action === "reset") {
          resetFilters();
        }
        return;
      }

      const masterItem = e.target.closest(".master-topic-item");
      if (masterItem && masterItem.dataset.topicId) {
        selectTopic(masterItem.dataset.topicId);
      }
    });

    // Review Mode Controls
    document.querySelectorAll("[data-review-scope]").forEach((btn) => {
      btn.addEventListener("click", () => setReviewScope(btn.dataset.reviewScope));
    });
    document.getElementById("btn-review-overview")?.addEventListener("click", () => {
      state.review.overviewOpen = !state.review.overviewOpen;
      const panel = document.getElementById("review-overview-panel");
      if (panel) {
        panel.classList.toggle("open", state.review.overviewOpen);
        panel.setAttribute("aria-hidden", state.review.overviewOpen ? "false" : "true");
      }
    });
    document.getElementById("btn-review-previous")?.addEventListener("click", prevReviewTopic);
    document.getElementById("btn-review-next")?.addEventListener("click", nextReviewTopic);
    document.getElementById("btn-review-open-workbench")?.addEventListener("click", () => {
      const current = getReviewTopicsList()[state.review.index];
      closeReviewView();
      if (current) selectTopic(current.id);
    });
    document.getElementById("btn-review-close")?.addEventListener("click", closeReviewView);

    document.querySelectorAll("#review-mode-switcher [data-review-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const current = getReviewTopicsList()[state.review.index];
        if (!current) return;
        getOrCreateSession(current, btn.dataset.reviewMode);
        renderReview();
      });
    });

    document.getElementById("review-rejection-reason-input")?.addEventListener("input", (e) => {
      const current = getReviewTopicsList()[state.review.index];
      if (!current) return;
      const s = getOrCreateSession(current);
      s.fields.rejection_reason = e.target.value;
      s.pendingRequest = null;
    });
    document.getElementById("review-superseded-by-input")?.addEventListener("input", (e) => {
      const current = getReviewTopicsList()[state.review.index];
      if (!current) return;
      const s = getOrCreateSession(current);
      s.fields.superseded_by = e.target.value;
      s.pendingRequest = null;
    });
    document.getElementById("review-user-opinion-input")?.addEventListener("input", (e) => {
      const current = getReviewTopicsList()[state.review.index];
      if (!current) return;
      const s = getOrCreateSession(current);
      s.fields.new_user_opinion = e.target.value;
      s.pendingRequest = null;
    });
    document.getElementById("review-impl-commit-input")?.addEventListener("input", (e) => {
      const current = getReviewTopicsList()[state.review.index];
      if (!current) return;
      const s = getOrCreateSession(current);
      s.fields.impl_commit = e.target.value;
      s.pendingRequest = null;
    });
    document.getElementById("review-commit-message-input")?.addEventListener("input", (e) => {
      const current = getReviewTopicsList()[state.review.index];
      if (!current) return;
      const s = getOrCreateSession(current);
      s.fields.commit_message = e.target.value;
      s.pendingRequest = null;
    });

    document.getElementById("btn-review-reset")?.addEventListener("click", () => {
      const current = getReviewTopicsList()[state.review.index];
      if (!current) return;
      state.draftsByTopic.delete(current.id);
      renderReview();
      showToast("已重置本页草稿", "info");
    });
    document.getElementById("btn-review-submit")?.addEventListener("click", () => submitReview(false));
    document.getElementById("btn-review-submit-next")?.addEventListener("click", () => submitReview(true));

    // Create Modal Auto-Slug & Markdown Preview
    const createTitle = document.getElementById("create-title");
    const createId = document.getElementById("create-id");
    createTitle?.addEventListener("input", () => {
      if (state.createAutoSlug && createId) {
        createId.value = slugifyTitle(createTitle.value);
      }
    });
    createId?.addEventListener("input", () => {
      state.createAutoSlug = !createId.value.trim();
    });
    document.getElementById("btn-toggle-create-preview")?.addEventListener("click", () => {
      const preview = document.getElementById("create-content-preview");
      const content = document.getElementById("create-content");
      if (!preview) return;
      preview.hidden = !preview.hidden;
      if (!preview.hidden) {
        preview.innerHTML = renderMarkdown(content?.value || "");
        renderMermaidDiagrams(preview);
      }
    });

    // Agent Context filter auto-refresh
    ["ctx-filter-module", "ctx-filter-path", "ctx-filter-topic", "ctx-format"].forEach((id) => {
      document.getElementById(id)?.addEventListener("change", refreshAgentContext);
    });

    // Time Machine Drawer Actions
    document.getElementById("drawer-history-list")?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-tm-action]");
      if (!btn) return;
      if (btn.dataset.tmAction === "restore-single") {
        restoreSingleTopic(btn.dataset.topicId, btn.dataset.revId);
      } else if (btn.dataset.tmAction === "rollback-all") {
        rollbackRevision(btn.dataset.revId);
      }
    });

    // Hash Navigation
    window.addEventListener("hashchange", () => {
      const hashId = decodeURIComponent(window.location.hash.replace(/^#/, "")).trim();
      if (hashId && state.topicsMeta.some((t) => t.id === hashId)) {
        switchView("topics");
        selectTopic(hashId);
      }
    });

    // Keyboard Shortcuts
    document.addEventListener("keydown", (e) => {
      const inInput = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
      if (state.review.active) {
        if (e.key === "Escape") {
          e.preventDefault();
          closeReviewView();
          return;
        }
        if ((e.altKey || !inInput) && e.key === "ArrowLeft") {
          e.preventDefault();
          prevReviewTopic();
          return;
        }
        if ((e.altKey || !inInput) && e.key === "ArrowRight") {
          e.preventDefault();
          nextReviewTopic();
          return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          submitReview(true);
          return;
        }
      } else {
        if (!inInput && e.key === "/") {
          e.preventDefault();
          document.getElementById("search-input")?.focus();
          return;
        }
        if (!inInput && e.key === "[") {
          e.preventDefault();
          toggleSidebar();
          return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          const activeEl = document.activeElement;
          if (activeEl && activeEl.closest("#workbench-composer-card") && state.selectedTopicId) {
            e.preventDefault();
            const topic = state.topicsMeta.find((t) => t.id === state.selectedTopicId);
            if (topic) {
              if (state.composerMode === "verify") {
                submitVerification(topic.id);
              } else {
                const session = getOrCreateSession(topic);
                submitTopicSave(topic.id, session, "workbench");
              }
            }
          }
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindGlobalEvents();
    loadMetadataList();
  });

  window.dashboardApp = {
    state,
    loadMetadataList,
    loadInitialData: loadMetadataList,
    selectTopic,
    switchView,
    setViewMode,
    setSortMode,
    toggleSidebar,
    resetFilters,
    resetAllFilters: resetFilters,
    openModal,
    closeModal,
    openDrawer,
    closeDrawer,
    onOutcomeChanged,
    openDecisionModal,
    closeDecisionModal: () => closeModal("modal-edit-decision"),
    submitDecision,
    submitTopicSave,
    submitVerification,
    deleteTopic,
    openReviewView,
    closeReviewView,
    prevReviewTopic,
    nextReviewTopic,
    submitReview,
    openCreateModal,
    closeCreateModal: () => closeModal("modal-create-topic"),
    submitCreate,
    openAgentContextModal,
    closeAgentContextModal: () => closeModal("modal-agent-context"),
    refreshAgentContext,
    copyAgentContext,
    openMaintenanceModal,
    closeMaintenanceModal: () => closeModal("modal-maintenance"),
    refreshMaintenanceReport,
    rebuildIndexFromMarkdown,
    triggerDatabaseBackup,
    openTimeMachine,
    closeTimeMachine: () => closeDrawer("drawer-time-machine"),
    switchTimeMachineScope,
    restoreSingleTopic,
    rollbackRevision,
    toggleCardDetails,
    toggleExpandAll,
    copyTopicLink,
  };
})();
