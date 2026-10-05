// Agent Decisions Dashboard Client Application
(function () {
  "use strict";

  const state = {
    config: {},
    topicsMeta: [],
    settledDecisions: [],
    openQuestions: [],
    changelog: [],
    topicsDetailCache: {},
    selectedTopicId: null,
    viewMode: "grid",
    currentView: "topics",
    filters: {
      lifecycle: "all",
      object: "all",
      searchQuery: "",
    },
    isServerOnline: false,
  };

  // Toast Notification
  function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const icon = type === "success" ? "✅" : "⚠️";
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // Two-Stage Loading: 1. Load Metadata List
  async function loadMetadataList() {
    try {
      const res = await fetch("/api/topics", { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        state.topicsMeta = data.topics || [];
        state.settledDecisions = data.settled_decisions || [];
        state.openQuestions = data.open_questions || [];
        state.changelog = data.changelog || [];
        if (data.config) applyConfig(data.config);

        state.isServerOnline = true;
        updateServerStatus(true);
        renderTopicCards();
        updateSidebarCounts();
        return;
      }
    } catch (e) {
      console.warn("Failed to load /api/topics, fallback to offline data", e);
    }

    // Offline fallback
    if (window.DASHBOARD_DEFAULT_DATA) {
      const def = window.DASHBOARD_DEFAULT_DATA;
      state.topicsMeta = def.topics || [];
      state.settledDecisions = def.settled_decisions || [];
      state.openQuestions = def.open_questions || [];
      state.changelog = def.changelog || [];
      if (def.config) applyConfig(def.config);
      updateServerStatus(false);
      renderTopicCards();
      updateSidebarCounts();
    }
  }

  function applyConfig(cfg) {
    state.config = cfg;
    if (cfg.project_name) {
      document.getElementById("page-title").innerText = cfg.project_name;
      document.getElementById("brand-title").childNodes[0].nodeValue = cfg.project_name + " ";
    }
    if (cfg.project_subtitle) {
      document.getElementById("brand-subtitle").innerText = cfg.project_subtitle;
    }
    if (cfg.brand_logo) {
      document.getElementById("brand-logo").innerText = cfg.brand_logo;
    }
    if (cfg.brand_icon) {
      const iconUri = `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>${encodeURIComponent(cfg.brand_icon)}</text></svg>`;
      document.getElementById("page-favicon").href = iconUri;
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
            <span class="filter-pill" data-type="object" data-val="${obj}">
              <span>${obj}</span>
              <span class="nav-badge" data-obj-badge="${obj}">0</span>
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
      const res = await fetch(`/api/topic/${topicId}`, { cache: "no-store" });
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
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // bold
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    // lists
    html = html.replace(/^- (.*$)/gim, "<li>$1</li>");
    html = html.replace(/\n\n/g, "<br><br>");
    return html;
  }

  function getFilteredTopics() {
    return state.topicsMeta.filter((t) => {
      if (state.filters.lifecycle !== "all" && t.lifecycle_status !== state.filters.lifecycle) {
        return false;
      }
      if (state.filters.object !== "all" && t.object !== state.filters.object) {
        return false;
      }
      if (state.filters.searchQuery) {
        const q = state.filters.searchQuery.toLowerCase();
        const str = `${t.title} ${t.id} ${t.summary} ${t.last_user_opinion} ${t.last_agent_reply}`.toLowerCase();
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
          <button class="btn btn-secondary" style="margin-top: 1rem;" onclick="window.dashboardApp.resetFilters()">重置所有筛选</button>
        </div>
      `;
      return;
    }

    container.className = `topic-grid ${state.viewMode === "list" ? "list-view" : ""}`;

    container.innerHTML = filtered
      .map((t) => {
        const lc = t.lifecycle_status || "discussing";
        const lcInfo = getLifecycleBadge(lc);
        const rounds = t.rounds_count || 1;

        return `
        <div class="topic-card" id="card-${t.id}">
          <div class="card-meta-line">
            <span class="badge ${lcInfo.badge_class}">${lcInfo.badge}</span>
            <span class="chip">#${t.id}</span>
            <span class="chip">${t.object || "通用"}</span>
            <span class="chip" style="color: var(--color-primary);">${t.function || "规范"}</span>
            <span class="chip" style="margin-left: auto;">第 ${rounds} 轮讨论</span>
          </div>

          <h3 class="card-title" onclick="window.dashboardApp.toggleCard('${t.id}')">${t.title}</h3>
          
          <div class="card-summary">
            ${renderMarkdown(t.summary ? t.summary + "..." : "")}
          </div>

          <!-- Dynamic Markdown body -->
          <div id="detail-body-${t.id}" style="display: none; border-top: 1px dashed var(--border-subtle); padding-top: 0.8rem;"></div>

          <!-- Latest Discussion -->
          <div class="discussion-box">
            <div class="discussion-title">
              <span>💬 最新决策记录（第 ${rounds} 轮）</span>
              <button class="btn btn-secondary" style="font-size: 0.72rem; padding: 0.2rem 0.5rem;" onclick="window.dashboardApp.openEditModal('${t.id}')">✏️ 确定决策</button>
            </div>
            <div class="discussion-row">
              <div class="discussion-label">💡 用户意见：</div>
              <div style="color: var(--text-main);">${t.last_user_opinion || "暂无原话记录"}</div>
            </div>
            <div class="discussion-row">
              <div class="discussion-label">🤖 落实答复：</div>
              <div style="color: var(--text-main);">${t.last_agent_reply || "—"}</div>
            </div>
          </div>

          <div class="card-footer">
            <span style="font-size: 0.72rem; color: var(--text-muted);">decisions/${t.id}.md</span>
            <div style="display: flex; gap: 0.4rem;">
              <button class="btn btn-secondary" onclick="window.dashboardApp.copyCitation('${t.title}', '${t.id}')">🔗 引用</button>
              <button class="btn btn-secondary" onclick="window.dashboardApp.toggleCard('${t.id}')">
                <span id="expand-btn-${t.id}">展开详情</span>
              </button>
              <button class="btn btn-primary" onclick="window.dashboardApp.openEditModal('${t.id}')">✏️ 记录决策</button>
            </div>
          </div>
        </div>
      `;
      })
      .join("");
  }

  async function toggleCard(topicId) {
    const detailBox = document.getElementById(`detail-body-${topicId}`);
    const btnText = document.getElementById(`expand-btn-${topicId}`);
    if (!detailBox) return;

    if (detailBox.style.display === "none") {
      detailBox.style.display = "block";
      if (btnText) btnText.innerText = "收起详情";
      detailBox.innerHTML = `<div style="color: var(--text-dim); padding: 0.5rem 0;">正在加载议题完整 Markdown 与历史轮次...</div>`;

      const detail = await fetchTopicDetail(topicId);
      if (detail) {
        let roundsHtml = "";
        if (detail.rounds && detail.rounds.length > 0) {
          roundsHtml = `
            <div style="margin-top: 1rem; border-top: 1px solid var(--border-subtle); padding-top: 0.8rem;">
              <h4 style="color: var(--color-primary); margin-bottom: 0.5rem; font-size: 0.88rem;">📜 历史讨论记录（共 ${detail.rounds.length} 轮）</h4>
              ${detail.rounds
                .map(
                  (r) => `
                <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.6rem 0.8rem; margin-bottom: 0.5rem;">
                  <div style="font-weight: 700; color: #38bdf8; font-size: 0.8rem; margin-bottom: 0.3rem;">${r.title}</div>
                  <div style="font-size: 0.8rem;">${renderMarkdown(r.content)}</div>
                </div>
              `
                )
                .join("")}
            </div>
          `;
        }

        detailBox.innerHTML = `
          <div style="font-size: 0.85rem; color: var(--text-main); margin-bottom: 0.8rem;">
            ${renderMarkdown(detail.core_content)}
          </div>
          ${roundsHtml}
        `;
      }
    } else {
      detailBox.style.display = "none";
      if (btnText) btnText.innerText = "展开详情";
    }
  }

  function updateSidebarCounts() {
    document.getElementById("count-topics").innerText = state.topicsMeta.length;
    document.getElementById("pill-count-all").innerText = state.topicsMeta.length;

    let decided = 0;
    let discussing = 0;
    let pending = 0;

    state.topicsMeta.forEach((t) => {
      const lc = t.lifecycle_status || "discussing";
      if (lc === "decided") decided++;
      else if (lc === "pending") pending++;
      else discussing++;
    });

    document.getElementById("pill-count-decided").innerText = decided;
    document.getElementById("pill-count-discussing").innerText = discussing;
    document.getElementById("pill-count-pending").innerText = pending;

    document.getElementById("count-settled").innerText = state.settledDecisions.length;
    document.getElementById("count-open").innerText = state.openQuestions.length;
    document.getElementById("count-changelog").innerText = state.changelog.length;
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
        renderTopicCards();
      });
    });
  }

  function openEditModal(topicId) {
    state.selectedTopicId = topicId;
    const meta = state.topicsMeta.find((t) => t.id === topicId);
    if (!meta) return;

    document.getElementById("modal-edit-title").innerText = `确定决策: ${meta.title}`;
    document.getElementById("modal-topic-id").innerText = `#${meta.id}`;
    document.getElementById("modal-topic-category").innerText = `${meta.object || "通用"} · ${meta.function || "规范"}`;

    document.getElementById("form-lifecycle-status").value = meta.lifecycle_status || "decided";
    document.getElementById("form-decision-status").value = meta.decision_status || "已定案";
    document.getElementById("form-impl-status").value = meta.impl_status || "未实现";

    const nextRound = (meta.rounds_count || 1) + 1;
    document.getElementById("form-user-opinion").value = "";
    document.getElementById("form-user-opinion").placeholder = `输入第 ${nextRound} 轮的用户意见原话...`;

    document.getElementById("form-agent-reply").value = "";
    document.getElementById("form-agent-reply").placeholder = `输入第 ${nextRound} 轮的落实说明与排期...`;

    document.getElementById("form-commit-message").value = `第 ${nextRound} 轮决策：确认 [${meta.title}]`;

    document.getElementById("modal-edit-decision").classList.add("active");
  }

  async function submitDecision() {
    if (!state.selectedTopicId) return;
    const meta = state.topicsMeta.find((t) => t.id === state.selectedTopicId);
    if (!meta) return;

    const lc = document.getElementById("form-lifecycle-status").value;
    const decStatus = document.getElementById("form-decision-status").value.trim();
    const implStatus = document.getElementById("form-impl-status").value.trim();
    const userOpinion = document.getElementById("form-user-opinion").value.trim();
    const agentReply = document.getElementById("form-agent-reply").value.trim();
    const commitMsg = document.getElementById("form-commit-message").value.trim();

    if (!commitMsg) {
      alert("请输入 Git 变更提交说明");
      return;
    }

    closeModal("modal-edit-decision");

    try {
      const res = await fetch(`/api/topic/${meta.id}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: meta.title,
          object: meta.object,
          function: meta.function,
          section: meta.section,
          lifecycle_status: lc,
          decision_status: decStatus,
          impl_status: implStatus,
          priority: meta.priority,
          new_user_opinion: userOpinion,
          new_agent_reply: agentReply,
          commit_message: commitMsg,
        }),
      });

      const result = await res.json();
      if (result.status === "success") {
        delete state.topicsDetailCache[meta.id];
        await loadMetadataList();
        showToast(`✅ Git Commit [${result.commit_hash}] 提交成功！已升级至第 ${result.round} 轮。`);
      } else {
        alert(`保存出错: ${result.message || result.error}`);
      }
    } catch (e) {
      alert(`网络或服务异常: ${e.message}`);
    }
  }

  async function openTimeMachine() {
    const drawer = document.getElementById("drawer-time-machine");
    const container = document.getElementById("drawer-history-list");
    drawer.classList.add("active");
    container.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 2rem;">加载历史中...</div>`;

    try {
      const res = await fetch("/api/git/log");
      if (res.ok) {
        const data = await res.json();
        let commitsHtml = "";
        (data.commits || []).forEach((c) => {
          commitsHtml += `
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.6rem 0.8rem; margin-bottom: 0.6rem;">
              <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.2rem;">
                <span style="font-family: var(--font-mono); color: var(--color-primary); font-weight: 700;">${c.hash}</span>
                <span>${c.date.split(" ")[0]}</span>
              </div>
              <div style="font-size: 0.82rem; font-weight: 600;">${c.message}</div>
            </div>
          `;
        });

        let revsHtml = "";
        (data.revisions || []).forEach((r) => {
          revsHtml += `
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.6rem 0.8rem; margin-bottom: 0.6rem;">
              <div style="display: flex; justify-content: space-between; font-size: 0.75rem; margin-bottom: 0.2rem;">
                <span class="chip">${r.rev_hash}</span>
                <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.1rem 0.4rem;" onclick="window.dashboardApp.rollbackRevision(${r.rev_id})">⏪ 回滚到此快照</button>
              </div>
              <div style="font-size: 0.82rem;">${r.summary}</div>
            </div>
          `;
        });

        container.innerHTML = `
          <h4 style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.5rem; text-transform: uppercase;">Git 自动语义提交日志</h4>
          ${commitsHtml || '<div style="color: var(--text-muted); font-size: 0.8rem;">暂无提交</div>'}
          <h4 style="font-size: 0.82rem; color: var(--text-muted); margin: 1.2rem 0 0.5rem; text-transform: uppercase;">SQLite 不可篡改快照链 (Revision)</h4>
          ${revsHtml || '<div style="color: var(--text-muted); font-size: 0.8rem;">暂无快照</div>'}
        `;
      }
    } catch (e) {
      container.innerHTML = `<div style="color: #ef4444; padding: 2rem;">加载失败: ${e.message}</div>`;
    }
  }

  async function rollbackRevision(revId) {
    if (!confirm(`确定要将全量数据库完全回滚至快照 #${revId} 吗？`)) return;
    try {
      const res = await fetch("/api/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rev_id: revId }),
      });
      const data = await res.json();
      if (res.ok) {
        closeDrawer("drawer-time-machine");
        state.topicsDetailCache = {};
        await loadMetadataList();
        showToast(`⏪ 已成功回滚至快照 ${data.rolled_back_to}！`);
      } else {
        alert(`回滚失败: ${data.error}`);
      }
    } catch (e) {
      alert(`请求异常: ${e.message}`);
    }
  }

  function copyCitation(title, id) {
    const text = `[${title}](#${id})`;
    navigator.clipboard.writeText(text).then(() => {
      showToast(`已复制引用格式：${text}`);
    });
  }

  function closeModal(modalId) {
    document.getElementById(modalId)?.classList.remove("active");
  }

  function closeDrawer(drawerId) {
    document.getElementById(drawerId)?.classList.remove("active");
  }

  function resetFilters() {
    state.filters.lifecycle = "all";
    state.filters.object = "all";
    state.filters.searchQuery = "";
    document.getElementById("search-input").value = "";
    document.querySelectorAll(".filter-pill").forEach((p) => {
      if (p.getAttribute("data-val") === "all") p.classList.add("active");
      else p.classList.remove("active");
    });
    renderTopicCards();
  }

  // Initialize
  document.addEventListener("DOMContentLoaded", () => {
    // Search input
    document.getElementById("search-input")?.addEventListener("input", (e) => {
      state.filters.searchQuery = e.target.value.trim();
      renderTopicCards();
    });

    // Theme toggle
    document.getElementById("btn-toggle-theme")?.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "dark";
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
    });

    // Grid / List view toggle
    document.getElementById("btn-view-grid")?.addEventListener("click", () => {
      state.viewMode = "grid";
      renderTopicCards();
    });
    document.getElementById("btn-view-list")?.addEventListener("click", () => {
      state.viewMode = "list";
      renderTopicCards();
    });

    // Time machine button
    document.getElementById("btn-time-machine")?.addEventListener("click", openTimeMachine);

    // Filter pills
    bindFilterPills(document.getElementById("lifecycle-filters-container"));

    // Initial fetch
    loadMetadataList();
  });

  // Export to window
  window.dashboardApp = {
    toggleCard,
    openEditModal,
    submitDecision,
    openTimeMachine,
    rollbackRevision,
    copyCitation,
    closeModal,
    closeDrawer,
    resetFilters,
  };
})();
