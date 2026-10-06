// Agent Decisions Dashboard Client Application
// Frontend fix 2026-10-05: explicit conflict review, metadata preservation, safe DOM events.
// Backend transaction / parser / restore defects require separate fixes.
(function () {
  "use strict";

  const state = {
    config: {},
    topicsMeta: [],
    settledDecisions: [],
    openQuestions: [],
    changelog: [],
    topicsDetailCache: Object.create(null),
    editSession: null,
    draftsByTopic: new Map(),
    selectedTopicId: null,
    viewMode: "grid",
    currentView: "topics",
    filters: {
      lifecycle: "all",
      object: "all",
      outcome: "all",
      searchQuery: "",
    },
    isServerOnline: false,
    pendingRestores: Object.create(null),
  };

  // Server/user strings must never be interpreted as HTML or executable JS.
  function showToast(message, type = "success", action = null) {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const safeType = ["success", "warning", "error"].includes(type) ? type : "error";
    const toast = document.createElement("div");
    toast.className = `toast ${safeType}`;
    const icon = document.createElement("span");
    icon.textContent = safeType === "success" ? "✅" : safeType === "warning" ? "⚠️" : "❌";
    const text = document.createElement("span");
    text.textContent = String(message ?? "");
    toast.append(icon, text);
    if (action && action.text) {
      const actionBtn = document.createElement("button");
      actionBtn.className = "btn btn-secondary";
      actionBtn.style.marginLeft = "0.75rem";
      actionBtn.style.padding = "0.15rem 0.5rem";
      actionBtn.style.fontSize = "0.75rem";
      actionBtn.style.borderRadius = "var(--radius-sm)";
      actionBtn.textContent = action.text;
      if (typeof action.onClick === "function") {
        actionBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          action.onClick();
        });
      }
      toast.appendChild(actionBtn);
    }
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 4500);
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
    // Matches the supplied backend's topic-ID contract.
    if (!/^[a-zA-Z0-9_-]+$/.test(id)) throw new Error("议题 ID 无效");
    return `/api/topic/${encodeURIComponent(id)}`;
  }

  // Two-Stage Loading: 1. Load Metadata List
  async function loadMetadataList() {
    try {
      const res = await fetch("/api/topics", { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        if (!Array.isArray(data.topics)) throw new Error("议题列表响应格式无效");
        state.topicsMeta = data.topics;
        state.settledDecisions = data.settled_decisions || [];
        state.openQuestions = data.open_questions || [];
        state.changelog = data.changelog || [];
        if (data.config) applyConfig(data.config);

        state.isServerOnline = true;
        updateServerStatus(true);
        renderTopicCards();
        renderSettledDecisions();
        renderOpenQuestions();
        renderChangelog();
        updateSidebarCounts();
        return true;
      }
    } catch (e) {
      console.warn("Failed to load /api/topics, fallback to offline data", e);
    }

    // A failed refresh must not replace already loaded data with demo records.
    updateServerStatus(false);
    if (!state.topicsMeta.length && window.DASHBOARD_DEFAULT_DATA) {
      const def = window.DASHBOARD_DEFAULT_DATA;
      state.topicsMeta = def.topics || [];
      state.settledDecisions = def.settled_decisions || [];
      state.openQuestions = def.open_questions || [];
      state.changelog = def.changelog || [];
      if (def.config) applyConfig(def.config);
      updateServerStatus(false);
      renderTopicCards();
      renderSettledDecisions();
      renderOpenQuestions();
      renderChangelog();
      updateSidebarCounts();
    }
    return false;
  }

  function applyConfig(cfg) {
    state.config = cfg;
    if (cfg.project_name) {
      const pageTitleEl = document.getElementById("page-title");
      if (pageTitleEl) pageTitleEl.innerText = cfg.project_name;
      const brandTitleEl = document.getElementById("brand-title");
      if (brandTitleEl) {
        const brandNameSpan = brandTitleEl.querySelector("[data-brand-name]");
        if (brandNameSpan) {
          brandNameSpan.innerText = cfg.project_name;
        } else {
          const brandIconEl = document.getElementById("brand-icon");
          if (brandIconEl && brandIconEl.parentNode === brandTitleEl) {
            let textNode = null;
            for (const node of brandTitleEl.childNodes) {
              if (node === brandIconEl) break;
              if (node.nodeType === Node.TEXT_NODE) {
                textNode = node;
                break;
              }
            }
            if (textNode) {
              textNode.nodeValue = cfg.project_name + " ";
            } else {
              brandTitleEl.insertBefore(document.createTextNode(cfg.project_name + " "), brandIconEl);
            }
          } else {
            brandTitleEl.innerText = cfg.project_name;
          }
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
      const iconUri = `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>${encodeURIComponent(cfg.brand_icon)}</text></svg>`;
      const fav = document.getElementById("page-favicon");
      if (fav) fav.href = iconUri;
      const brandIconEl = document.getElementById("brand-icon");
      if (brandIconEl) brandIconEl.innerText = cfg.brand_icon;
    }

    if (cfg.lifecycle_states && Array.isArray(cfg.lifecycle_states)) {
      cfg.lifecycle_states.forEach((s) => {
        const opt = document.querySelector(`#form-workflow-state option[value="${s.id}"]`);
        if (opt) {
          const label = s.name || s.id;
          opt.innerText = (s.badge && !s.badge.includes(label)) ? `${s.badge} ${label}` : (s.badge || label);
        }
        const pill = document.querySelector(`[data-type="lifecycle"][data-val="${s.id}"]`);
        if (pill) {
          const span = pill.querySelector("span:first-child");
          if (span) {
            span.innerText = s.badge || s.name || s.id;
          }
        }
      });
    }

    // Populate category filters
    if (cfg.categories && cfg.categories.objects) {
      const container = document.getElementById("object-filters-container");
      if (container) {
        let html = `
          <span class="filter-pill active" data-type="object" data-val="all">
            <span>全部对象</span>
            <span class="nav-badge" id="pill-count-all-obj">${state.topicsMeta.length}</span>
          </span>
        `;
        cfg.categories.objects.forEach((obj) => {
          html += `
            <span class="filter-pill" data-type="object" data-val="${escapeHtml(obj)}">
              <span>${escapeHtml(obj)}</span>
              <span class="nav-badge" data-obj-badge="${escapeHtml(obj)}">0</span>
            </span>
          `;
        });
        container.innerHTML = html;
        bindFilterPills(container);
      }
    }
  }

  function updateServerStatus(online) {
    state.isServerOnline = online;
    const dot = document.getElementById("server-status-dot");
    const text = document.getElementById("server-status-text");
    if (dot && text) {
      if (online) {
        dot.className = "server-dot online";
        text.innerText = "Git + SQLite 在线";
      } else {
        dot.className = "server-dot offline";
        text.innerText = "离线预览模式";
      }
    }
  }

  // Two-Stage Loading: 2. On-Demand Fetch Single Topic Markdown
  async function fetchTopicDetail(topicId) {
    if (state.topicsDetailCache[topicId]) {
      return state.topicsDetailCache[topicId];
    }

    try {
      const res = await fetch(topicPath(topicId), { cache: "no-store" });
      if (res.ok) {
        const detail = await res.json();
        state.topicsDetailCache[topicId] = detail;
        return detail;
      }
    } catch (e) {
      console.warn(`Failed to fetch topic ${topicId}`, e);
    }

    const meta = state.topicsMeta.find((t) => t.id === topicId);
    return {
      id: topicId,
      core_content: meta ? meta.summary || "" : "",
      rounds: [
        {
          title: "第 1 轮讨论与定案",
          content: `- **💡 用户意见**：${meta ? meta.last_user_opinion || "—" : "—"}\n- **🤖 团队答复**：${meta ? meta.last_agent_reply || "—" : "—"}`
        }
      ]
    };
  }

  function getLifecycleBadge(lc) {
    if (state.config.lifecycle_states) {
      const found = state.config.lifecycle_states.find((s) => s.id === lc);
      if (found) return found;
    }
    if (lc === "decided") return { badge: "🟢 已决策", badge_class: "badge-decided" };
    if (lc === "pending") return { badge: "🔴 待决策", badge_class: "badge-pending" };
    return { badge: "🟡 待讨论", badge_class: "badge-discussing" };
  }

  function renderMarkdown(text) {
    if (!text) return "";
    let html = escapeHtml(text);
    // bold
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    // lists
    html = html.replace(/^- (.*$)/gim, "<li>$1</li>");
    html = html.replace(/\n\n/g, "<br><br>");
    return html;
  }

  function getCanonicalOutcome(t) {
    if (t.decision_outcome) {
      return t.decision_outcome;
    }
    const status = String(t.decision_status || "");
    if (status.includes("非否决")) return (t.workflow_state || t.lifecycle_status) === "decided" ? "accepted" : "";
    if (status.includes("否决")) return "rejected";
    if (status.includes("已定") || status.includes("采纳")) return "accepted";
    if (status.includes("推迟") || status.includes("待定")) return "deferred";
    if (status.includes("替代")) return "superseded";
    const wf = t.workflow_state || t.lifecycle_status;
    if (wf === "decided") return "accepted";
    return "";
  }

  function getFilteredTopics() {
    return state.topicsMeta.filter((t) => {
      const wf = t.workflow_state || t.lifecycle_status || "discussing";
      if (state.filters.lifecycle !== "all" && wf !== state.filters.lifecycle) {
        return false;
      }
      if (state.filters.object !== "all" && t.object !== state.filters.object) {
        return false;
      }
      if (state.filters.outcome !== "all") {
        const canonicalOut = getCanonicalOutcome(t);
        if (state.filters.outcome === "rejected") {
          if (canonicalOut !== "rejected") return false;
        } else if (state.filters.outcome === "accepted") {
          if (canonicalOut !== "accepted") return false;
        } else {
          if (canonicalOut !== state.filters.outcome) return false;
        }
      }
      if (state.filters.searchQuery) {
        const q = state.filters.searchQuery.toLowerCase();
        const str = `${t.title} ${t.id} ${t.summary} ${t.rejection_reason || ""} ${t.last_user_opinion || ""} ${t.last_agent_reply || ""}`.toLowerCase();
        if (!str.includes(q)) return false;
      }
      return true;
    });
  }

  function renderTopicCards() {
    const container = document.getElementById("topics-container");
    if (!container) return;

    const filtered = getFilteredTopics();
    const countLabel = document.getElementById("filtered-count-label");
    if (countLabel) {
      countLabel.innerText = `显示 ${filtered.length} / ${state.topicsMeta.length} 项议题`;
    }

    if (filtered.length === 0) {
      container.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 4rem 1rem; color: var(--text-dim);">
          <div style="font-size: 2.5rem; margin-bottom: 0.8rem;">🔍</div>
          <h3>未找到匹配的议题</h3>
          <p style="margin-top: 0.4rem; font-size: 0.85rem;">请尝试调整筛选条件或搜索关键词</p>
          <button class="btn btn-secondary" style="margin-top: 1rem;" data-action="reset">重置所有筛选</button>
        </div>
      `;
      return;
    }

    container.classList.add("topic-grid");
    container.classList.toggle("list-view", state.viewMode === "list");

    container.innerHTML = filtered
      .map((t) => {
        const wf = t.workflow_state || t.lifecycle_status || "discussing";
        const lcInfo = getLifecycleBadge(wf);
        const rounds = t.rounds_count || 1;
        const ver = t.version || 1;

        const isRejected = (getCanonicalOutcome(t) === "rejected");
        const implState = t.implementation_state || t.impl_status || "not_started";

        // Implementation Badge
        let implBadge = "";
        if (implState === "verified") {
          implBadge = `<span class="badge badge-verified" title="已通过自动化测试或人工核验">🧪 已核验</span>`;
        } else if (implState === "implemented") {
          implBadge = `<span class="badge badge-decided" title="代码已提交落地">🔨 已实现</span>`;
        } else if (implState === "in_progress") {
          implBadge = `<span class="badge badge-in-progress" title="正在开发中">⏳ 进行中</span>`;
        }

        // Rejection Banner
        let rejectionHtml = "";
        if (isRejected) {
          rejectionHtml = `
            <div class="rejection-box">
              <strong>❌ 明确否决红线：</strong> ${escapeHtml(t.rejection_reason || "用户或团队已明确否决此方案，严禁重新提议")}
              ${t.superseded_by ? `<div style="font-size: 0.75rem; margin-top: 0.2rem; color: var(--text-dim);">替代议题：<code>#${escapeHtml(t.superseded_by)}</code></div>` : ""}
            </div>
          `;
        }

        return `
        <div class="topic-card" id="card-${escapeHtml(t.id)}">
          <div class="card-meta-line">
            <span class="badge ${escapeHtml(lcInfo.badge_class)}">${escapeHtml(lcInfo.badge)}</span>
            ${isRejected ? `<span class="badge badge-rejected">❌ 方案已否决</span>` : ""}
            ${implBadge}
            <span class="chip">#${escapeHtml(t.id)}</span>
            <span class="chip">v${escapeHtml(ver)}</span>
            <span class="chip">${escapeHtml(t.object || "通用")}</span>
            <span class="chip" style="color: var(--color-primary);">${escapeHtml(t.function || "规范")}</span>
            <span class="chip" style="margin-left: auto;">第 ${escapeHtml(rounds)} 轮讨论</span>
          </div>

          <h3 class="card-title" data-action="toggle" data-topic-id="${escapeHtml(t.id)}">${escapeHtml(t.title)}</h3>
          
          <div class="card-summary">
            ${renderMarkdown(t.summary ? t.summary + "..." : "")}
          </div>

          ${rejectionHtml}

          <!-- Dynamic Markdown body -->
          <div id="detail-body-${escapeHtml(t.id)}" style="display: none; border-top: 1px dashed var(--border-subtle); padding-top: 0.8rem;"></div>

          <!-- Latest Discussion -->
          <div class="discussion-box">
            <div class="discussion-title">
              <span>💬 最新决策记录（第 ${escapeHtml(rounds)} 轮）</span>
              <button class="btn btn-secondary" style="font-size: 0.72rem; padding: 0.2rem 0.5rem;" data-action="edit" data-topic-id="${escapeHtml(t.id)}">✏️ 确定决策</button>
            </div>
            <div class="discussion-row">
              <div class="discussion-label">💡 用户意见：</div>
              <div style="color: var(--text-main);">${renderMarkdown(t.last_user_opinion || "暂无原话记录")}</div>
            </div>
            <div class="discussion-row">
              <div class="discussion-label">🤖 落实答复：</div>
              <div style="color: var(--text-main);">${renderMarkdown(t.last_agent_reply || "—")}</div>
            </div>
            ${t.impl_commit ? `
              <div class="discussion-row" style="font-size: 0.75rem; color: var(--text-dim); border-top: 1px dashed var(--border-subtle); padding-top: 0.3rem;">
                <span>落地证据代码：</span><code>${escapeHtml(t.impl_commit)}</code>
                ${t.impl_verifier ? `<span> · 核验人: ${escapeHtml(t.impl_verifier)}</span>` : ""}
              </div>
            ` : ""}
          </div>

          <div class="card-footer">
            <span style="font-size: 0.72rem; color: var(--text-muted);">decisions/${escapeHtml(t.id)}.md</span>
            <div style="display: flex; gap: 0.4rem;">
              <button class="btn btn-secondary" data-action="copy" data-topic-id="${escapeHtml(t.id)}">🔗 引用</button>
              <button class="btn btn-secondary" data-action="toggle" data-topic-id="${escapeHtml(t.id)}">
                <span id="expand-btn-${escapeHtml(t.id)}">展开详情</span>
              </button>
              <button class="btn btn-primary" data-action="edit" data-topic-id="${escapeHtml(t.id)}">✏️ 记录决策</button>
            </div>
          </div>
        </div>
      `;
      })
      .join("");
  }

  async function toggleCard(topicId) {
    state.selectedTopicId = topicId;
    const bodyEl = document.getElementById(`detail-body-${topicId}`);
    const btnSpan = document.getElementById(`expand-btn-${topicId}`);
    if (!bodyEl) return;

    if (bodyEl.style.display === "block") {
      bodyEl.style.display = "none";
      if (btnSpan) btnSpan.innerText = "展开详情";
      return;
    }

    bodyEl.style.display = "block";
    bodyEl.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 1rem;">正在按需解析 ${escapeHtml(topicId)}.md 核心论述与历史讨论...</div>`;
    if (btnSpan) btnSpan.innerText = "收起详情";

    const detail = await fetchTopicDetail(topicId);
    let roundsHtml = "";
    (detail.rounds || []).forEach((r) => {
      roundsHtml += `
        <div style="margin-top: 0.8rem; background: var(--bg-card); border-left: 3px solid var(--color-primary); padding: 0.6rem 0.8rem; border-radius: var(--radius-sm);">
          <div style="font-weight: 700; font-size: 0.82rem; margin-bottom: 0.3rem; color: var(--text-main);">${escapeHtml(r.title)}</div>
          <div style="font-size: 0.82rem; line-height: 1.5; color: var(--text-dim);">${renderMarkdown(r.content)}</div>
        </div>
      `;
    });

    bodyEl.innerHTML = `
      <div style="margin-bottom: 1rem;">
        <h4 style="font-size: 0.85rem; color: var(--color-primary); margin-bottom: 0.4rem;">📖 核心论述与现实依据</h4>
        <div style="font-size: 0.85rem; line-height: 1.6; color: var(--text-main);">${renderMarkdown(detail.core_content || "暂无核心正文")}</div>
      </div>
      <div>
        <h4 style="font-size: 0.85rem; color: var(--color-primary); margin-bottom: 0.4rem;">📜 历史多轮决策演进 (${(detail.rounds || []).length} 轮)</h4>
        ${roundsHtml || '<div style="color: var(--text-muted); font-size: 0.8rem;">暂无既往轮次</div>'}
      </div>
    `;
  }

  function updateSidebarCounts() {
    let decided = 0, discussing = 0, pending = 0, rejected = 0;
    const objCounts = {};

    state.topicsMeta.forEach((t) => {
      const wf = t.workflow_state || t.lifecycle_status || "discussing";
      if (wf === "decided") decided++;
      else if (wf === "pending") pending++;
      else discussing++;

      if (getCanonicalOutcome(t) === "rejected") {
        rejected++;
      }

      const obj = t.object || "其他";
      objCounts[obj] = (objCounts[obj] || 0) + 1;
    });

    document.getElementById("count-topics").innerText = state.topicsMeta.length;
    document.getElementById("pill-count-all").innerText = state.topicsMeta.length;
    document.getElementById("pill-count-decided").innerText = decided;
    document.getElementById("pill-count-discussing").innerText = discussing;
    document.getElementById("pill-count-pending").innerText = pending;
    
    const rejEl = document.getElementById("pill-count-rejected");
    if (rejEl) rejEl.innerText = rejected;

    document.getElementById("count-settled").innerText = state.settledDecisions.length;
    document.getElementById("count-open").innerText = state.openQuestions.length;
    document.getElementById("count-changelog").innerText = state.changelog.length;
  }

  function renderSettledDecisions() {
    const container = document.getElementById("settled-container");
    if (!container) return;
    if (!state.settledDecisions.length) {
      container.innerHTML = `<div style="color: var(--text-dim); padding: 1.5rem; text-align: center;">暂无已定结论记录</div>`;
      return;
    }
    container.innerHTML = state.settledDecisions.map(item => `
      <div class="card" style="margin-bottom: 1rem; padding: 1rem; border: 1px solid var(--border-color); border-radius: 6px;">
        <h4 style="margin: 0 0 0.5rem 0; font-size: 1.05rem;">🎯 ${escapeHtml(item.title || "")}</h4>
        <div style="font-size: 0.95rem; margin-bottom: 0.5rem;"><strong>要求/红线：</strong>${escapeHtml(item.requirement || "")}</div>
        <div style="font-size: 0.85rem; color: var(--text-dim);"><strong>落实说明：</strong>${escapeHtml(item.details || "")}</div>
      </div>
    `).join("");
  }

  function renderOpenQuestions() {
    const container = document.getElementById("open-container");
    if (!container) return;
    if (!state.openQuestions.length) {
      container.innerHTML = `<div style="color: var(--text-dim); padding: 1.5rem; text-align: center;">暂无待决策议题</div>`;
      return;
    }
    container.innerHTML = state.openQuestions.map(item => `
      <div class="card" style="margin-bottom: 1rem; padding: 1rem; border: 1px solid var(--border-color); border-radius: 6px;">
        <h4 style="margin: 0 0 0.5rem 0; font-size: 1.05rem;">❓ ${escapeHtml(item.item || "")}</h4>
        <div style="font-size: 0.95rem; margin-bottom: 0.5rem;"><strong>待决难点：</strong>${escapeHtml(item.issue || "")}</div>
        <div style="font-size: 0.85rem; color: var(--text-dim);"><strong>攻坚聚焦点：</strong>${escapeHtml(item.focus || "")}${item.topic_ref ? ` (关联议题: #${escapeHtml(item.topic_ref)})` : ""}</div>
      </div>
    `).join("");
  }

  function renderChangelog() {
    const container = document.getElementById("changelog-container");
    if (!container) return;
    if (!state.changelog.length) {
      container.innerHTML = `<div style="color: var(--text-dim); padding: 1.5rem; text-align: center;">暂无变更审计日志</div>`;
      return;
    }
    container.innerHTML = state.changelog.map(item => `
      <div class="card" style="margin-bottom: 0.75rem; padding: 0.75rem 1rem; border: 1px solid var(--border-color); border-radius: 6px;">
        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: var(--text-dim); margin-bottom: 0.25rem;">
          <span><strong>范围：</strong>${escapeHtml(item.scope || "")}</span>
          <span>${escapeHtml(item.date || "")}</span>
        </div>
        <div style="font-size: 0.95rem; margin-bottom: 0.25rem;"><strong>变更：</strong>${escapeHtml(item.change || "")}</div>
        <div style="font-size: 0.85rem; color: var(--text-dim);"><strong>依据：</strong>${escapeHtml(item.basis || "")}</div>
      </div>
    `).join("");
  }

  function bindFilterPills(container) {
    container.querySelectorAll(".filter-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        container.querySelectorAll(".filter-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        const type = pill.getAttribute("data-type");
        const val = pill.getAttribute("data-val");
        if (type === "lifecycle") state.filters.lifecycle = val;
        if (type === "object") state.filters.object = val;
        if (type === "outcome") state.filters.outcome = val;
        renderTopicCards();
      });
    });
  }

  function onOutcomeChanged() {
    const outcome = document.getElementById("form-decision-outcome").value;
    const group = document.getElementById("group-rejection-reason");
    if (group) {
      group.style.display = outcome === "rejected" ? "block" : "none";
    }
  }

  const EDIT_FIELDS = [
    { key: "workflow_state", id: "form-workflow-state", label: "工作流状态" },
    { key: "decision_outcome", id: "form-decision-outcome", label: "决策结果" },
    { key: "rejection_reason", id: "form-rejection-reason", label: "否决原因" },
    { key: "implementation_state", id: "form-impl-state", label: "实现状态" },
    { key: "impl_commit", id: "form-impl-commit", label: "实现 Commit / PR" },
  ];
  const DISCUSSION_FIELDS = [
    { key: "new_user_opinion", id: "form-user-opinion" },
    { key: "new_agent_reply", id: "form-agent-reply" },
    { key: "commit_message", id: "form-commit-message" },
  ];
  const READ_ONLY_FIELDS = [
    ["title", "标题"], ["object", "对象分类"], ["function", "功能分类"],
    ["section", "章节"], ["priority", "优先级"],
    ["impl_verifier", "核验人 / 核验证据"], ["superseded_by", "替代议题"],
  ];

  function valuesFromMeta(meta) {
    const workflow = meta.workflow_state || meta.lifecycle_status || "discussing";
    const outcome = getCanonicalOutcome(meta);
    return {
      workflow_state: workflow,
      decision_outcome: outcome,
      rejection_reason: meta.rejection_reason || "",
      implementation_state: meta.implementation_state || "not_started",
      impl_commit: meta.impl_commit || "",
    };
  }

  function rememberDraft(session) {
    if (state.editSession !== session) return;
    for (const field of [...EDIT_FIELDS, ...DISCUSSION_FIELDS]) {
      session.draft[field.key] = document.getElementById(field.id).value;
    }
  }

  function writeEditForm(session) {
    for (const field of [...EDIT_FIELDS, ...DISCUSSION_FIELDS]) {
      const input = document.getElementById(field.id);
      const value = String(session.draft[field.key] ?? "");
      // Preserve unknown/empty values rather than silently choosing 'accepted'.
      if (input.tagName === "SELECT" && !Array.from(input.options).some((o) => o.value === value)) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value ? `${value}（保留原值）` : "未设置（保留原值）";
        input.appendChild(option);
      }
      input.value = value;
    }
    onOutcomeChanged();
    updateModalInfo(session);
    updateEditControls(session);
  }

  function updateModalInfo(session) {
    const meta = session.base;
    const isEn = document.documentElement.lang?.toLowerCase().startsWith("en");
    const titleEl = document.getElementById("modal-edit-title");
    if (titleEl) {
      if (!titleEl.hasAttribute("data-default-title")) {
        titleEl.setAttribute("data-default-title", titleEl.textContent.trim());
      }
      const defaultTitle = titleEl.getAttribute("data-default-title");
      if (defaultTitle && defaultTitle !== "✏️ 确定决策并提交 Git") {
        titleEl.textContent = `${defaultTitle}: ${meta.title}`;
      } else if (isEn) {
        titleEl.textContent = `Record decision: ${meta.title}`;
      } else {
        titleEl.textContent = `确定决策: ${meta.title}`;
      }
    }
    const topicIdEl = document.getElementById("modal-topic-id");
    if (topicIdEl) topicIdEl.textContent = `#${session.topicId}`;
    const topicVerEl = document.getElementById("modal-topic-version");
    if (topicVerEl) topicVerEl.textContent = `v${meta.version ?? "未知"}`;
    const topicCatEl = document.getElementById("modal-topic-category");
    if (topicCatEl) topicCatEl.textContent = `${meta.object || "通用"} · ${meta.function || "规范"}`;

    const nextRound = (Number(meta.rounds_count) || 0) + 1;
    const userOpEl = document.getElementById("form-user-opinion");
    if (userOpEl) {
      if (!userOpEl.hasAttribute("data-default-placeholder")) {
        userOpEl.setAttribute("data-default-placeholder", userOpEl.placeholder || "");
      }
      const origPlaceholder = userOpEl.getAttribute("data-default-placeholder");
      if (origPlaceholder && origPlaceholder !== "录入用户明确意见或指示原话...") {
        userOpEl.placeholder = origPlaceholder;
      } else if (isEn) {
        userOpEl.placeholder = `Enter round ${nextRound} user requirements...`;
      } else {
        userOpEl.placeholder = `输入第 ${nextRound} 轮的用户意见指示原话...`;
      }
    }
    const agentRepEl = document.getElementById("form-agent-reply");
    if (agentRepEl) {
      if (!agentRepEl.hasAttribute("data-default-placeholder")) {
        agentRepEl.setAttribute("data-default-placeholder", agentRepEl.placeholder || "");
      }
      const origPlaceholder = agentRepEl.getAttribute("data-default-placeholder");
      if (origPlaceholder && origPlaceholder !== "录入团队技术回应与落地承诺..." && origPlaceholder !== "输入第 n 轮的落实说明与排期...") {
        agentRepEl.placeholder = origPlaceholder;
      } else if (isEn) {
        agentRepEl.placeholder = `Enter round ${nextRound} agent reply and schedule...`;
      } else {
        agentRepEl.placeholder = `输入第 ${nextRound} 轮的落实说明与排期...`;
      }
    }
  }

  function updateButtonLabel(button, text) {
    const labelSpan = button.querySelector("[data-save-label]");
    if (labelSpan) {
      labelSpan.textContent = text;
      return;
    }
    const iconSpan = button.querySelector("[data-save-icon]");
    if (iconSpan) {
      const parent = iconSpan.parentNode;
      for (const child of Array.from(parent.childNodes)) {
        if (child !== iconSpan) {
          parent.removeChild(child);
        }
      }
      parent.appendChild(document.createTextNode(" " + text));
      return;
    }
    button.textContent = text;
  }

  function updateEditControls(session) {
    if (state.editSession !== session) return;
    const button = document.getElementById("btn-submit-decision");
    if (!button) return;
    const isEn = document.documentElement.lang?.toLowerCase().startsWith("en");
    if (!button.hasAttribute("data-default-text")) {
      const labelEl = button.querySelector("[data-save-label]");
      const iconEl = button.querySelector("[data-save-icon]");
      let initialText = "";
      if (labelEl) {
        initialText = labelEl.textContent.trim();
      } else if (iconEl) {
        const parent = iconEl.parentNode;
        initialText = Array.from(parent.childNodes)
          .filter(n => n !== iconEl)
          .map(n => n.textContent)
          .join("").trim();
      } else {
        initialText = button.textContent.trim();
      }
      button.setAttribute("data-default-text", initialText || (isEn ? "Save decision" : "确定决策并生成 Git Commit"));
    }
    const defaultText = button.getAttribute("data-default-text");
    button.disabled = Boolean(session.saving || session.conflict || !state.isServerOnline);
    const text = session.saving ? (isEn ? "Saving..." : "正在确认并保存...") :
      session.conflict ? (isEn ? "Please resolve conflicts first" : "请先核对并合并冲突") :
      session.uncertain ? (isEn ? "Retry original request" : "重试原请求（核对保存结果）") : defaultText;
    updateButtonLabel(button, text);
    // An uncertain request can only be replayed byte-for-byte, not edited in place.
    for (const field of [...EDIT_FIELDS, ...DISCUSSION_FIELDS]) {
      const el = document.getElementById(field.id);
      if (el) el.disabled = Boolean(session.saving || session.conflict || session.uncertain);
    }
  }

  function makeTextElement(tag, text) {
    const element = document.createElement(tag);
    element.textContent = String(text ?? "");
    return element;
  }

  function bannerFor(session) {
    if (state.editSession !== session) return null;
    const banner = document.getElementById("modal-conflict-banner");
    if (banner) {
      banner.replaceChildren();
      banner.style.display = "block";
    }
    return banner;
  }

  function clearEditBanner() {
    const banner = document.getElementById("modal-conflict-banner");
    if (banner) {
      banner.replaceChildren();
      banner.style.display = "none";
    }
  }

  function renderUncertainBanner(session, message) {
    const banner = bannerFor(session);
    if (!banner) return;
    banner.append(
      makeTextElement("strong", "⚠️ 尚未确认保存结果"),
      makeTextElement("p", `${message} 服务端可能已完成部分或全部写入。草稿和原请求 ID 已保留；下方按钮只会重放原请求，不会生成新的业务请求。请勿通过刷新页面后另行提交来重试。`)
    );
  }

  function setConflict(session, currentVersion) {
    // Crucially, do not advance base.version until the user reviews the merge.
    session.request = null;
    session.uncertain = false;
    session.conflict = { currentVersion, latest: null };
    delete state.topicsDetailCache[session.topicId];
    renderConflictBanner(session);
  }

  function renderConflictBanner(session) {
    const banner = bannerFor(session);
    if (!banner || !session.conflict) return;
    banner.append(
      makeTextElement("strong", "⚠️ 检测到版本冲突，已暂停提交"),
      makeTextElement("p", `编辑基于 v${session.base.version}；服务端报告 v${session.conflict.currentVersion ?? "未知"}。本地草稿已保留，版本号不会自动跳过冲突。请加载最新元数据并逐项核对。`)
    );
    const button = makeTextElement("button", "加载最新版本并核对草稿");
    button.id = "btn-load-conflict";
    button.type = "button";
    button.className = "btn btn-secondary";
    button.disabled = Boolean(session.reviewing);
    button.addEventListener("click", () => loadConflictReview(session));
    banner.appendChild(button);
  }

  async function latestTopicMetadata(topicId) {
    // /api/topics reads DB metadata. Do not rebase from a truncated preview or
    // Markdown detail: the reviewed backend can modify Markdown before a 409.
    const response = await fetch("/api/topics", { cache: "no-store" });
    if (!response.ok) throw new Error(`无法核对最新版本（HTTP ${response.status}）`);
    const data = await response.json();
    if (!Array.isArray(data.topics)) throw new Error("服务端议题列表格式无效");
    const topic = data.topics.find((item) => item.id === topicId);
    if (!topic) throw new Error("议题已不存在；草稿仍保留，请核对是否被删除或恢复");
    if (!Number.isSafeInteger(topic.version) || topic.version < 1) {
      throw new Error("服务端缺少有效版本号，为避免覆盖已停止保存");
    }
    return { ...topic };
  }

  async function loadConflictReview(session) {
    if (state.editSession !== session || !session.conflict || session.reviewing) return;
    session.reviewing = true;
    renderConflictBanner(session);
    try {
      const latest = await latestTopicMetadata(session.topicId);
      if (state.editSession !== session || !session.conflict) return;
      session.conflict.latest = latest;
      renderMergeReview(session, latest);
    } catch (error) {
      if (state.editSession === session) {
        renderConflictBanner(session);
        document.getElementById("modal-conflict-banner")?.appendChild(makeTextElement("p", `读取失败：${error.message}。仍禁止覆盖，可再次尝试加载。`));
      }
    } finally {
      session.reviewing = false;
      if (state.editSession === session) {
        const button = document.getElementById("btn-load-conflict");
        if (button) button.disabled = false;
      }
    }
  }

  function renderMergeReview(session, latest) {
    const banner = bannerFor(session);
    if (!banner) return;
    const original = valuesFromMeta(session.base);
    const remote = valuesFromMeta(latest);
    const choices = new Map();
    banner.append(
      makeTextElement("strong", `核对版本 v${session.base.version} → v${latest.version}`),
      makeTextElement("p", "服务端已变更的字段默认采用最新值；本地新增的用户意见、Agent 答复和提交说明保留。选择使用本地旧值会覆盖对应的新值。确认合并不会自动提交。")
    );
    const wrapper = document.createElement("div");
    wrapper.style.cssText = "overflow:auto;max-height:340px;margin:0.6rem 0";
    const table = document.createElement("table");
    table.style.cssText = "width:100%;font-size:0.76rem;border-collapse:collapse;text-align:left";
    const header = document.createElement("tr");
    for (const label of ["字段", "打开时", "服务端最新", "本地草稿 / 选择"]) header.appendChild(makeTextElement("th", label));
    table.appendChild(header);
    const addRow = (label, before, current, local, control) => {
      const row = document.createElement("tr");
      for (const value of [label, before, current, local]) {
        const cell = makeTextElement("td", value === "" || value == null ? "（空）" : value);
        cell.style.cssText = "padding:0.4rem;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere;border-top:1px solid var(--border-subtle)";
        row.appendChild(cell);
      }
      if (control) row.lastElementChild.appendChild(control);
      table.appendChild(row);
    };
    for (const field of EDIT_FIELDS) {
      let choice = null;
      if (remote[field.key] !== original[field.key] && remote[field.key] !== session.draft[field.key]) {
        choice = document.createElement("select");
        choice.className = "form-select";
        choice.dataset.mergeField = field.key;
        choice.setAttribute("aria-label", `${field.label}冲突处理`);
        for (const [value, text] of [["server", "采用服务端最新值"], ["local", "使用本地草稿（覆盖新值）"]]) {
          const option = makeTextElement("option", text);
          option.value = value;
          choice.appendChild(option);
        }
        choices.set(field.key, choice);
      }
      addRow(field.label, original[field.key], remote[field.key], session.draft[field.key], choice);
    }
    for (const [key, label] of READ_ONLY_FIELDS) {
      if ((session.base[key] ?? "") !== (latest[key] ?? "")) {
        addRow(label, session.base[key], latest[key], "只读元数据：采用服务端最新值");
      }
    }
    wrapper.appendChild(table);
    banner.appendChild(wrapper);
    const confirmButton = makeTextElement("button", "确认以上合并，返回编辑（不提交）");
    confirmButton.id = "btn-apply-conflict";
    confirmButton.type = "button";
    confirmButton.className = "btn btn-primary";
    confirmButton.addEventListener("click", () => {
      if (state.editSession !== session || session.conflict?.latest !== latest) return;
      for (const field of EDIT_FIELDS) {
        const choice = choices.get(field.key);
        if (choice) {
          if (choice.value === "server") session.draft[field.key] = remote[field.key];
        } else if (remote[field.key] !== original[field.key]) {
          session.draft[field.key] = remote[field.key];
        }
      }
      session.base = { ...latest };
      session.conflict = null;
      session.request = null;
      session.uncertain = false;
      clearEditBanner();
      writeEditForm(session);
      showToast("已合并最新元数据并保留新增讨论。请检查表单后再提交。", "warning");
    });
    banner.appendChild(confirmButton);
  }

  function openEditModal(topicId) {
    if (state.editSession?.saving) {
      showToast("正在确认当前议题的保存结果，暂不能切换议题。", "warning");
      return;
    }
    const meta = state.topicsMeta.find((item) => item.id === topicId);
    if (!meta) return;
    if (state.editSession) rememberDraft(state.editSession);
    let session = state.draftsByTopic.get(topicId);
    if (!session) {
      const nextRound = (Number(meta.rounds_count) || 0) + 1;
      session = {
        topicId, base: { ...meta }, saving: false, reviewing: false,
        request: null, uncertain: false, conflict: null,
        draft: { ...valuesFromMeta(meta), new_user_opinion: "", new_agent_reply: "",
          commit_message: `第 ${nextRound} 轮决策：确认 [${meta.title}]` },
      };
      session.initialDraft = JSON.stringify(session.draft);
      state.draftsByTopic.set(topicId, session);
    }
    state.selectedTopicId = topicId;
    state.editSession = session;
    clearEditBanner();
    writeEditForm(session);
    if (session.conflict) renderConflictBanner(session);
    else if (session.uncertain) renderUncertainBanner(session, "上次保存的响应未能确认。");
    document.getElementById("modal-edit-decision").classList.add("active");
    if (!state.isServerOnline) showToast("当前为离线预览；草稿可编辑，但不会向后端提交。", "warning");
  }

  function createRequestId() {
    if (globalThis.crypto?.randomUUID) return `req-${globalThis.crypto.randomUUID()}`;
    return `req-${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  }

  function decisionPayload(session, requestId) {
    const meta = session.base;
    const draft = session.draft;
    const wf = draft.workflow_state;
    const outcome = draft.decision_outcome;
    const initial = valuesFromMeta(meta);
    const unchangedDecision = wf === initial.workflow_state && outcome === initial.decision_outcome;
    const decisionStatus = unchangedDecision && meta.decision_status ? meta.decision_status :
      outcome === "rejected" ? "已否决" : outcome === "superseded" ? "已替代" :
        outcome === "deferred" ? "暂缓" : wf === "decided" ? "已定" : "待定";
    return {
      title: meta.title,
      object: meta.object ?? "通用系统", function: meta.function ?? "核心规范",
      section: meta.section ?? "未分类", priority: meta.priority ?? "普通",
      workflow_state: wf, lifecycle_status: wf, decision_status: decisionStatus,
      decision_outcome: outcome, rejection_reason: draft.rejection_reason.trim(),
      implementation_state: draft.implementation_state, impl_commit: draft.impl_commit.trim(),
      // The current backend treats omitted fields as empty, so send preserved values.
      impl_verifier: meta.impl_verifier ?? "", superseded_by: meta.superseded_by ?? "",
      new_user_opinion: draft.new_user_opinion.trim(), new_agent_reply: draft.new_agent_reply.trim(),
      commit_message: draft.commit_message.trim(), expected_version: meta.version, request_id: requestId,
    };
  }

  async function submitDecision() {
    const session = state.editSession;
    if (!session || session.saving) return;
    if (session.conflict) {
      showToast("冲突尚未解决，请先核对并合并最新版本。", "warning");
      return;
    }
    if (!state.isServerOnline) {
      showToast("当前为离线预览，已阻止保存。", "warning");
      return;
    }
    rememberDraft(session);
    if (!session.request) {
      if (!session.draft.commit_message.trim()) {
        showToast("请输入 Git 变更提交说明。", "warning");
        return;
      }
      if (session.draft.decision_outcome === "rejected" && !session.draft.rejection_reason.trim()) {
        showToast("明确否决方案时，必须录入否决原因与重新讨论前提。", "warning");
        return;
      }
      if (!Number.isSafeInteger(session.base.version) || session.base.version < 1) {
        showToast("编辑基线缺少有效版本号，已停止保存。请重新加载议题。", "error");
        return;
      }
    }
    session.saving = true; // Set before the first await: prevents rapid double submits.
    updateEditControls(session);
    try {
      if (!session.request) {
        const latest = await latestTopicMetadata(session.topicId);
        if (latest.version !== session.base.version) {
          setConflict(session, latest.version);
          return;
        }
        // Preflight reduces stale POSTs; only an atomic backend check can close the race.
        const requestId = createRequestId();
        session.request = {
          id: requestId, version: session.base.version,
          body: JSON.stringify(decisionPayload(session, requestId)),
        };
      }
      const request = session.request;
      const response = await fetch(`${topicPath(session.topicId)}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Request-ID": request.id,
          "X-Expected-Version": String(request.version) },
        body: request.body,
      });
      const result = await response.json();
      if (response.status === 409 && result.error === "version_conflict") {
        setConflict(session, result.current_version);
        return;
      }
      if (response.ok && result.status === "success") {
        // Once the server confirms success, refresh/clipboard failures must not
        // reclassify the save as uncertain or re-enable the old request.
        session.request = null;
        session.uncertain = false;
        state.draftsByTopic.delete(session.topicId);
        delete state.topicsDetailCache[session.topicId];
        if (state.editSession === session) {
          state.editSession = null;
          document.getElementById("modal-edit-decision").classList.remove("active");
        }
        const savedTopicId = session.topicId;
        const priorRevId = result.prior_rev_id;
        const targetExpectedVersion = result.new_version;
        const undoAction = {
          text: "撤销这次提交",
          onClick: async () => {
            state.selectedTopicId = savedTopicId;
            try {
              if (priorRevId != null) {
                await restoreSingleTopic(savedTopicId, priorRevId, true, targetExpectedVersion);
              } else {
                const logRes = await fetch(`/api/git/log?topic_id=${encodeURIComponent(savedTopicId)}&limit=5`);
                if (logRes.ok) {
                  const logData = await logRes.json();
                  const revs = logData.revisions || [];
                  if (revs.length > 1) {
                    await restoreSingleTopic(savedTopicId, revs[1].rev_id, true, targetExpectedVersion);
                  }
                }
              }
            } catch (err) {
              console.error("Undo failed:", err);
            }
            await openTimeMachine(savedTopicId);
          },
        };
        if (result.git_status === "committed") {
          showToast(`决策已保存，Git Commit [${result.commit_hash || ""}] 已提交。`, "success", undoAction);
        } else {
          showToast(`决策已保存；Git 状态：${result.git_message || result.git_status || "未确认"}`, "warning", undoAction);
        }
        const refreshed = await loadMetadataList();
        if (!refreshed) showToast("保存已经成功，但列表刷新失败；请勿重复提交同一讨论。", "warning");
        return;
      }
      const message = result.message || result.error || `HTTP ${response.status}`;
      if (response.status >= 500 || response.status === 409 || response.ok) {
        session.uncertain = true;
        renderUncertainBanner(session, String(message));
      } else {
        session.request = null;
        session.uncertain = false;
        clearEditBanner();
        showToast(`保存被拒绝：${message}`, "error");
      }
    } catch (error) {
      if (session.request) {
        session.uncertain = true;
        renderUncertainBanner(session, error.message);
      } else {
        showToast(`无法保存：${error.message}`, "error");
      }
    } finally {
      session.saving = false;
      updateEditControls(session);
    }
  }

  // Drafts are tab-local (not written to localStorage). Warn before discarding them.
  window.addEventListener("beforeunload", (event) => {
    if (state.editSession) rememberDraft(state.editSession);
    const dirty = Array.from(state.draftsByTopic.values()).some((session) =>
      session.request || session.conflict || JSON.stringify(session.draft) !== session.initialDraft
    );
    if (dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  // Agent Context Modal
  async function openAgentContextModal() {
    const modal = document.getElementById("modal-agent-context");
    const textarea = document.getElementById("agent-context-markdown");
    modal.classList.add("active");
    textarea.value = "正在提取有效决策与已否决红线约束...";

    try {
      const res = await fetch("/api/agent/context?format=markdown");
      if (res.ok) {
        const mdText = await res.text();
        textarea.value = mdText;
      } else {
        textarea.value = "加载 Agent 上下文失败: 服务端响应异常";
      }
    } catch (e) {
      textarea.value = `加载失败: ${e.message}`;
    }
  }

  async function copyAgentContext() {
    const textarea = document.getElementById("agent-context-markdown");
    if (!textarea || !textarea.value) return;
    try {
      await writeClipboard(textarea.value);
      showToast("📋 已复制 Agent 上下文 Markdown。");
      closeModal("modal-agent-context");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  // Time Machine & Rollback
  async function openTimeMachine(targetTopicId = null, offset = 0, append = false) {
    if (targetTopicId !== null && targetTopicId !== undefined) {
      state.selectedTopicId = targetTopicId;
    }
    const drawer = document.getElementById("drawer-time-machine");
    const container = document.getElementById("drawer-history-list");
    drawer.classList.add("active");
    if (!append) {
      container.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 2rem;">加载历史快照中...</div>`;
    }

    try {
      const topicParam = state.selectedTopicId ? `topic_id=${encodeURIComponent(state.selectedTopicId)}&` : "";
      const url = `/api/git/log?${topicParam}limit=100&offset=${offset}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`历史接口返回 HTTP ${res.status}`);
      const data = await res.json();
      const revisions = data.revisions || [];
      const commits = data.commits || [];

      let revsHtml = "";
      revisions.forEach((r) => {
        const hasTopicInSnapshot = Array.isArray(r.snapshot_topic_ids)
          ? r.snapshot_topic_ids.includes(state.selectedTopicId)
          : (!r.topic_id || r.topic_id === state.selectedTopicId);
        revsHtml += `
          <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.6rem 0.8rem; margin-bottom: 0.6rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; margin-bottom: 0.3rem;">
              <span class="chip" style="font-family: var(--font-mono);">${escapeHtml(r.rev_hash)}</span>
              <div style="display: flex; gap: 0.3rem;">
                ${state.selectedTopicId ? (hasTopicInSnapshot ? `
                  <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.15rem 0.4rem; color: var(--color-primary);" data-history-action="restore" data-topic-id="${escapeHtml(state.selectedTopicId)}" data-revision-id="${escapeHtml(r.rev_id)}">
                    ⏪ 仅回滚当前议题
                  </button>
                ` : `
                  <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.15rem 0.4rem; color: #f59e0b;" data-history-action="restore" data-topic-id="${escapeHtml(state.selectedTopicId)}" data-revision-id="${escapeHtml(r.rev_id)}">
                    ⏪ 撤销创建（未包含该议题）
                  </button>
                `) : ""}
                <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.15rem 0.4rem; color: #ef4444;" data-history-action="rollback" data-revision-id="${escapeHtml(r.rev_id)}">
                  ⚠️ 全库快照重置
                </button>
              </div>
            </div>
            <div style="font-size: 0.82rem; font-weight: 600;">${escapeHtml(r.summary)}</div>
            ${r.diff_summary ? `<div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.2rem;">${escapeHtml(r.diff_summary)}</div>` : ""}
          </div>
        `;
      });

      const nextOffset = offset + revisions.length;
      const loadMoreHtml = revisions.length >= 100 ? `
        <div id="history-load-more-container" style="text-align: center; margin: 1rem 0;">
          <button class="btn btn-secondary" data-history-action="load-more" data-offset="${nextOffset}" style="width: 100%; font-size: 0.8rem; padding: 0.4rem;">
            加载更多历史
          </button>
        </div>
      ` : "";

      if (append) {
        document.getElementById("history-load-more-container")?.remove();
        const revContainer = document.getElementById("time-machine-revisions-list");
        if (revContainer) {
          revContainer.insertAdjacentHTML("beforeend", revsHtml);
        }
        if (loadMoreHtml) {
          container.insertAdjacentHTML("beforeend", loadMoreHtml);
        }
      } else {
        let commitsHtml = "";
        commits.forEach((c) => {
          commitsHtml += `
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.6rem 0.8rem; margin-bottom: 0.6rem;">
              <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.2rem;">
                <span style="font-family: var(--font-mono); color: var(--color-primary); font-weight: 700;">${escapeHtml(c.hash)}</span>
                <span>${escapeHtml(String(c.date || "").split(" ")[0])}</span>
              </div>
              <div style="font-size: 0.82rem; font-weight: 600;">${escapeHtml(c.message)}</div>
            </div>
          `;
        });

        container.innerHTML = `
          ${state.selectedTopicId ? `<div style="background: rgba(14,165,233,0.1); border: 1px solid rgba(14,165,233,0.3); border-radius: var(--radius-sm); padding: 0.5rem; font-size: 0.78rem; margin-bottom: 0.8rem;">当前选中议题：<code>#${escapeHtml(state.selectedTopicId)}</code>，可执行单议题精准回溯。</div>` : ""}
          <h4 style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.5rem; text-transform: uppercase;">Git 自动语义提交日志</h4>
          ${commitsHtml || '<div style="color: var(--text-muted); font-size: 0.8rem;">暂无提交</div>'}
          <h4 style="font-size: 0.82rem; color: var(--text-muted); margin: 1.2rem 0 0.5rem; text-transform: uppercase;">SQLite 历史快照 (Revisions)</h4>
          <div id="time-machine-revisions-list">${revsHtml || '<div style="color: var(--text-muted); font-size: 0.8rem;">暂无快照</div>'}</div>
          ${loadMoreHtml}
        `;
      }
    } catch (e) {
      if (!append) {
        container.innerHTML = `<div style="color: #ef4444; padding: 2rem;">加载失败: ${escapeHtml(e.message)}</div>`;
      } else {
        showToast(`加载更多历史失败: ${e.message}`, "error");
      }
    }
  }

  // P1-C: 单议题针对性回滚
  async function restoreSingleTopic(topicId, revId, keepDrawerOpen = false, forcedExpectedVersion = null) {
    if (!Number.isSafeInteger(Number(revId)) || Number(revId) < 1) return;
    if (state.isRestoring) {
      showToast("已有恢复任务正在处理中，请勿重复操作", "warning");
      return;
    }
    if (!confirm(`将议题 [${topicId}] 恢复至快照 #${revId}？`)) return;

    state.isRestoring = true;
    const restoreKey = `${topicId}:${revId}`;
    try {
      const currentTopic = (state.topicsMeta || []).find((t) => t.id === topicId) || state.topicsDetailCache[topicId];
      if (currentTopic && (currentTopic.version === undefined || currentTopic.version === null)) {
        showToast("无法获取当前议题版本，已终止恢复以防数据覆盖", "error");
        return;
      }
      let expectedVersion;
      if (forcedExpectedVersion !== null && forcedExpectedVersion !== undefined) {
        expectedVersion = forcedExpectedVersion;
      } else {
        expectedVersion = currentTopic ? currentTopic.version : undefined;
      }

      if (!state.pendingRestores[restoreKey]) {
        state.pendingRestores[restoreKey] = {
          requestId: "restore-" + (window.crypto?.randomUUID?.() || (Date.now() + "-" + Math.random().toString(36).slice(2))),
          expectedVersion: expectedVersion,
        };
      }
      const pending = state.pendingRestores[restoreKey];
      const requestId = typeof pending === "object" ? pending.requestId : pending;
      const effectiveExpectedVersion = (typeof pending === "object" && pending.expectedVersion !== undefined) ? pending.expectedVersion : expectedVersion;

      const res = await fetch(`${topicPath(topicId)}/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rev_id: revId,
          reason: "用户在看板中执行单议题精准回溯",
          expected_version: effectiveExpectedVersion,
          request_id: requestId,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data && data.restored_from) {
        delete state.pendingRestores[restoreKey];
        if (!keepDrawerOpen) {
          closeDrawer("drawer-time-machine");
        }
        delete state.topicsDetailCache[topicId];
        await loadMetadataList();
        if (data.git_status === "git_error") {
          showToast(`⏪ 议题 [${topicId}] 已成功精准回滚至快照 ${data.restored_from}，但 Git 提交失败: ${data.git_message || "Git 错误"}`, "warning");
        } else {
          showToast(`⏪ 议题 [${topicId}] 已成功精准回滚至快照 ${data.restored_from}！`);
        }
      } else if (res.ok) {
        if (!keepDrawerOpen) {
          closeDrawer("drawer-time-machine");
        }
        delete state.topicsDetailCache[topicId];
        await loadMetadataList();
        showToast(`⚠️ 议题 [${topicId}] 回滚响应异常 (快照 undefined)，请重试原请求`, "warning");
      } else {
        if (res.status < 500) {
          delete state.pendingRestores[restoreKey];
        }
        if (!keepDrawerOpen) {
          closeDrawer("drawer-time-machine");
        }
        delete state.topicsDetailCache[topicId];
        await loadMetadataList();
        showToast(`单议题回滚失败: ${data.message || data.error || ("HTTP " + res.status)}`, "error");
      }
    } catch (e) {
      if (!keepDrawerOpen) {
        closeDrawer("drawer-time-machine");
      }
      showToast(`请求异常: ${e.message}`, "error");
    } finally {
      state.isRestoring = false;
    }
  }

  // 全库回滚
  async function rollbackRevision(revId) {
    if (!Number.isSafeInteger(Number(revId)) || Number(revId) < 1) return;
    if (!confirm(`⚠️ 全库恢复至快照 #${revId}？\n此前端补丁未修复后端恢复的一致性问题。请先完整备份，不要在未修复的生产实例上执行。`)) return;
    try {
      const res = await fetch("/api/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rev_id: revId }),
      });
      const data = await res.json();
      if (res.ok) {
        closeDrawer("drawer-time-machine");
        state.topicsDetailCache = Object.create(null);
        await loadMetadataList();
        if (data.git_status === "git_error") {
          showToast(`⏪ 全库已成功回滚至快照 ${data.rolled_back_to}，但 Git 提交失败: ${data.git_message || "Git 错误"}`, "warning");
        } else {
          showToast(`⏪ 全库已成功回滚至快照 ${data.rolled_back_to}！`);
        }
      } else {
        alert(`全库回滚失败: ${data.message || data.error}`);
      }
    } catch (e) {
      alert(`请求异常: ${e.message}`);
    }
  }

  async function writeClipboard(text) {
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      throw new Error("浏览器不支持当前页面的剪贴板访问，请使用 localhost 或 HTTPS 并检查权限。");
    }
    await navigator.clipboard.writeText(text);
  }

  async function copyCitation(title, id) {
    const text = `[${title}](#${id})`;
    try {
      await writeClipboard(text);
      showToast(`已复制引用格式：${text}`);
    } catch (error) {
      showToast(`复制失败：${error.message}`, "error");
    }
  }

  function closeModal(modalId) {
    if (modalId === "modal-edit-decision" && state.editSession) {
      if (state.editSession.saving) {
        showToast("正在确认保存结果，请勿关闭编辑窗口。", "warning");
        return;
      }
      rememberDraft(state.editSession);
      state.editSession = null;
    }
    document.getElementById(modalId)?.classList.remove("active");
  }

  function closeDrawer(drawerId) {
    document.getElementById(drawerId)?.classList.remove("active");
  }

  function resetFilters() {
    state.filters.lifecycle = "all";
    state.filters.object = "all";
    state.filters.outcome = "all";
    state.filters.searchQuery = "";
    const searchInput = document.getElementById("search-input");
    if (searchInput) searchInput.value = "";
    document.querySelectorAll(".filter-pill").forEach((p) => {
      if (p.getAttribute("data-val") === "all") p.classList.add("active");
      else p.classList.remove("active");
    });
    renderTopicCards();
  }

  // Initialization
  document.addEventListener("DOMContentLoaded", () => {
    // Search input
    const searchInput = document.getElementById("search-input");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        state.filters.searchQuery = e.target.value.trim();
        renderTopicCards();
      });
    }

    // View toggle buttons
    document.getElementById("btn-view-grid")?.addEventListener("click", () => {
      state.viewMode = "grid";
      renderTopicCards();
    });
    document.getElementById("btn-view-list")?.addEventListener("click", () => {
      state.viewMode = "list";
      renderTopicCards();
    });

    // Theme toggle
    document.getElementById("btn-toggle-theme")?.addEventListener("click", () => {
      const current = document.body.getAttribute("data-theme") || "dark";
      const next = current === "dark" ? "light" : "dark";
      document.body.setAttribute("data-theme", next);
    });

    // Navigation items
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.addEventListener("click", () => {
        document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
        item.classList.add("active");
        const view = item.getAttribute("data-view");
        document.querySelectorAll(".view-panel").forEach((p) => (p.style.display = "none"));
        const targetPanel = document.getElementById(`view-${view}`);
        if (targetPanel) {
          targetPanel.style.display = "block";
          if (view === "settled") renderSettledDecisions();
          else if (view === "open") renderOpenQuestions();
          else if (view === "changelog") renderChangelog();
        }
      });
    });

    // Filter pills
    document.querySelectorAll(".filter-pills").forEach((container) => {
      bindFilterPills(container);
    });

    // Delegation survives card/history re-renders. No server values enter JS source.
    document.getElementById("topics-container")?.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target.closest("[data-action]") : null;
      if (!target || !event.currentTarget.contains(target)) return;
      const action = target.dataset.action;
      if (action === "reset") return resetFilters();
      const topic = state.topicsMeta.find((item) => item.id === target.dataset.topicId);
      if (!topic) return;
      if (action === "toggle") toggleCard(topic.id);
      if (action === "edit") openEditModal(topic.id);
      if (action === "copy") copyCitation(topic.title, topic.id);
    });
    document.getElementById("drawer-history-list")?.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target.closest("[data-history-action]") : null;
      if (!target || !event.currentTarget.contains(target)) return;
      if (target.dataset.historyAction === "load-more") {
        const offset = Number(target.dataset.offset) || 0;
        openTimeMachine(state.selectedTopicId, offset, true);
        return;
      }
      const revision = Number(target.dataset.revisionId);
      if (!Number.isSafeInteger(revision) || revision < 1) return;
      if (target.dataset.historyAction === "restore") restoreSingleTopic(target.dataset.topicId || state.selectedTopicId, revision);
      if (target.dataset.historyAction === "rollback") rollbackRevision(revision);
    });

    // Initial load
    loadMetadataList();
  });

  // Global exports for inline HTML handlers
  window.dashboardApp = {
    toggleCard,
    openEditModal,
    submitDecision,
    openTimeMachine,
    rollbackRevision,
    restoreSingleTopic,
    openAgentContextModal,
    copyAgentContext,
    onOutcomeChanged,
    copyCitation,
    closeModal,
    closeDrawer,
    resetFilters,
  };
})();
