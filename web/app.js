// Agent Decisions Dashboard Client Application
// 支持正交三态流转、否决红线约束、并发乐观锁冲突保护与单议题精准回溯
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
      outcome: "all",
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
    const icon = type === "success" ? "✅" : (type === "warning" ? "⚠️" : "❌");
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 4500);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
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
        const out = t.decision_outcome || "";
        if (state.filters.outcome === "rejected") {
          if (out !== "rejected" && !((t.decision_status || "").includes("否决"))) return false;
        } else if (state.filters.outcome === "accepted") {
          if (out === "rejected" || ((t.decision_status || "").includes("否决"))) return false;
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
          <button class="btn btn-secondary" style="margin-top: 1rem;" onclick="window.dashboardApp.resetFilters()">重置所有筛选</button>
        </div>
      `;
      return;
    }

    container.className = `topic-grid ${state.viewMode === "list" ? "list-view" : ""}`;

    container.innerHTML = filtered
      .map((t) => {
        const wf = t.workflow_state || t.lifecycle_status || "discussing";
        const lcInfo = getLifecycleBadge(wf);
        const rounds = t.rounds_count || 1;
        const ver = t.version || 1;

        const isRejected = (t.decision_outcome === "rejected") || ((t.decision_status || "").includes("否决"));
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
        <div class="topic-card" id="card-${t.id}">
          <div class="card-meta-line">
            <span class="badge ${lcInfo.badge_class}">${lcInfo.badge}</span>
            ${isRejected ? `<span class="badge badge-rejected">❌ 方案已否决</span>` : ""}
            ${implBadge}
            <span class="chip">#${t.id}</span>
            <span class="chip">v${ver}</span>
            <span class="chip">${escapeHtml(t.object || "通用")}</span>
            <span class="chip" style="color: var(--color-primary);">${escapeHtml(t.function || "规范")}</span>
            <span class="chip" style="margin-left: auto;">第 ${rounds} 轮讨论</span>
          </div>

          <h3 class="card-title" onclick="window.dashboardApp.toggleCard('${t.id}')">${escapeHtml(t.title)}</h3>
          
          <div class="card-summary">
            ${renderMarkdown(t.summary ? t.summary + "..." : "")}
          </div>

          ${rejectionHtml}

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
            <span style="font-size: 0.72rem; color: var(--text-muted);">decisions/${t.id}.md</span>
            <div style="display: flex; gap: 0.4rem;">
              <button class="btn btn-secondary" onclick="window.dashboardApp.copyCitation('${escapeHtml(t.title)}', '${t.id}')">🔗 引用</button>
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
    bodyEl.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 1rem;">正在按需解析 ${topicId}.md 核心论述与历史讨论...</div>`;
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

      if (t.decision_outcome === "rejected" || (t.decision_status || "").includes("否决")) {
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

  function openEditModal(topicId) {
    state.selectedTopicId = topicId;
    const meta = state.topicsMeta.find((t) => t.id === topicId);
    if (!meta) return;

    // 清空冲突提示
    const conflictBanner = document.getElementById("modal-conflict-banner");
    if (conflictBanner) {
      conflictBanner.style.display = "none";
      conflictBanner.innerHTML = "";
    }

    document.getElementById("modal-edit-title").innerText = `确定决策: ${meta.title}`;
    document.getElementById("modal-topic-id").innerText = `#${meta.id}`;
    document.getElementById("modal-topic-version").innerText = `v${meta.version || 1}`;
    document.getElementById("modal-topic-category").innerText = `${meta.object || "通用"} · ${meta.function || "规范"}`;

    const wf = meta.workflow_state || meta.lifecycle_status || "decided";
    document.getElementById("form-workflow-state").value = wf;
    
    const outcome = meta.decision_outcome || ((meta.decision_status || "").includes("否决") ? "rejected" : "accepted");
    document.getElementById("form-decision-outcome").value = outcome;
    onOutcomeChanged();

    document.getElementById("form-rejection-reason").value = meta.rejection_reason || "";

    const impl = meta.implementation_state || "not_started";
    document.getElementById("form-impl-state").value = impl;
    document.getElementById("form-impl-commit").value = meta.impl_commit || "";

    const nextRound = (meta.rounds_count || 1) + 1;
    document.getElementById("form-user-opinion").value = "";
    document.getElementById("form-user-opinion").placeholder = `输入第 ${nextRound} 轮的用户意见指示原话...`;

    document.getElementById("form-agent-reply").value = "";
    document.getElementById("form-agent-reply").placeholder = `输入第 ${nextRound} 轮的落实说明与排期...`;

    document.getElementById("form-commit-message").value = `第 ${nextRound} 轮决策：确认 [${meta.title}]`;

    document.getElementById("modal-edit-decision").classList.add("active");
  }

  async function submitDecision() {
    if (!state.selectedTopicId) return;
    const meta = state.topicsMeta.find((t) => t.id === state.selectedTopicId);
    if (!meta) return;

    const wf = document.getElementById("form-workflow-state").value;
    const outcome = document.getElementById("form-decision-outcome").value;
    const rejectionReason = document.getElementById("form-rejection-reason").value.trim();
    const implState = document.getElementById("form-impl-state").value;
    const implCommit = document.getElementById("form-impl-commit").value.trim();
    const userOpinion = document.getElementById("form-user-opinion").value.trim();
    const agentReply = document.getElementById("form-agent-reply").value.trim();
    const commitMsg = document.getElementById("form-commit-message").value.trim();

    if (!commitMsg) {
      alert("请输入 Git 变更提交说明 (Commit Message)");
      return;
    }

    if (outcome === "rejected" && !rejectionReason) {
      alert("明确否决方案时，必须录入否决原因与重新讨论前提，以便 Agent 遵守红线约束！");
      return;
    }

    const submitBtn = document.getElementById("btn-submit-decision");
    submitBtn.disabled = true;
    submitBtn.innerText = "正在保存并提交 Git...";

    const requestId = "req-" + Date.now() + "-" + Math.random().toString(36).substring(2, 8);

    try {
      const res = await fetch(`/api/topic/${meta.id}/save`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": requestId,
          "X-Expected-Version": String(meta.version || 1)
        },
        body: JSON.stringify({
          title: meta.title,
          object: meta.object,
          function: meta.function,
          section: meta.section,
          workflow_state: wf,
          lifecycle_status: wf,
          decision_outcome: outcome,
          rejection_reason: rejectionReason,
          implementation_state: implState,
          impl_commit: implCommit,
          priority: meta.priority,
          new_user_opinion: userOpinion,
          new_agent_reply: agentReply,
          commit_message: commitMsg,
          expected_version: meta.version || 1,
          request_id: requestId
        }),
      });

      const result = await res.json();

      if (res.status === 409 && result.error === "version_conflict") {
        // P1-D: 乐观并发冲突，保留用户草稿，提醒用户
        const banner = document.getElementById("modal-conflict-banner");
        if (banner) {
          banner.style.display = "block";
          banner.innerHTML = `
            <strong>⚠️ 并发修改冲突：</strong> 该议题已被其他会话更新至版本 <code>v${result.current_version}</code>。
            您的草稿已完好保留在下方编辑框中。请确认无误后再次点击提交。
          `;
        }
        meta.version = result.current_version;
        document.getElementById("modal-topic-version").innerText = `v${result.current_version}`;
        showToast(`⚠️ 并发冲突：已刷新至最新服务端版本 v${result.current_version}，您的草稿已保留！`, "warning");
        return;
      }

      if (res.ok && result.status === "success") {
        closeModal("modal-edit-decision");
        delete state.topicsDetailCache[meta.id];
        await loadMetadataList();

        if (result.git_status === "committed") {
          showToast(`✅ Git Commit [${result.commit_hash}] 提交成功！已升级至第 ${result.round} 轮。`);
        } else if (result.git_status === "skipped_unrelated_staged") {
          showToast(`🛡️ ${result.git_message}`, "warning");
        } else {
          showToast(`✅ 决策已保存至本地数据库与 Markdown 文件！`);
        }
      } else {
        alert(`保存出错: ${result.message || result.error}`);
      }
    } catch (e) {
      alert(`网络或服务异常: ${e.message}`);
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerText = "确定决策并生成 Git Commit";
    }
  }

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

  function copyAgentContext() {
    const textarea = document.getElementById("agent-context-markdown");
    if (!textarea || !textarea.value) return;
    navigator.clipboard.writeText(textarea.value).then(() => {
      showToast("📋 已成功复制 Agent 治理 Prompt Markdown！可直接粘贴至 Agent 工作上下文。");
      closeModal("modal-agent-context");
    });
  }

  // Time Machine & Rollback
  async function openTimeMachine() {
    const drawer = document.getElementById("drawer-time-machine");
    const container = document.getElementById("drawer-history-list");
    drawer.classList.add("active");
    container.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 2rem;">加载历史快照中...</div>`;

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
              <div style="font-size: 0.82rem; font-weight: 600;">${escapeHtml(c.message)}</div>
            </div>
          `;
        });

        let revsHtml = "";
        (data.revisions || []).forEach((r) => {
          const isSingleTopicAction = r.topic_id;
          revsHtml += `
            <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.6rem 0.8rem; margin-bottom: 0.6rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; margin-bottom: 0.3rem;">
                <span class="chip" style="font-family: var(--font-mono);">${r.rev_hash}</span>
                <div style="display: flex; gap: 0.3rem;">
                  ${state.selectedTopicId ? `
                    <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.15rem 0.4rem; color: var(--color-primary);" onclick="window.dashboardApp.restoreSingleTopic('${state.selectedTopicId}', ${r.rev_id})">
                      ⏪ 仅回滚当前议题
                    </button>
                  ` : ""}
                  <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.15rem 0.4rem; color: #ef4444;" onclick="window.dashboardApp.rollbackRevision(${r.rev_id})">
                    ⚠️ 全库快照重置
                  </button>
                </div>
              </div>
              <div style="font-size: 0.82rem; font-weight: 600;">${escapeHtml(r.summary)}</div>
              ${r.diff_summary ? `<div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.2rem;">${escapeHtml(r.diff_summary)}</div>` : ""}
            </div>
          `;
        });

        container.innerHTML = `
          ${state.selectedTopicId ? `<div style="background: rgba(14,165,233,0.1); border: 1px solid rgba(14,165,233,0.3); border-radius: var(--radius-sm); padding: 0.5rem; font-size: 0.78rem; margin-bottom: 0.8rem;">当前选中议题：<code>#${state.selectedTopicId}</code>，可执行单议题精准回溯。</div>` : ""}
          <h4 style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.5rem; text-transform: uppercase;">Git 自动语义提交日志</h4>
          ${commitsHtml || '<div style="color: var(--text-muted); font-size: 0.8rem;">暂无提交</div>'}
          <h4 style="font-size: 0.82rem; color: var(--text-muted); margin: 1.2rem 0 0.5rem; text-transform: uppercase;">SQLite 不可篡改快照链 (Revisions)</h4>
          ${revsHtml || '<div style="color: var(--text-muted); font-size: 0.8rem;">暂无快照</div>'}
        `;
      }
    } catch (e) {
      container.innerHTML = `<div style="color: #ef4444; padding: 2rem;">加载失败: ${e.message}</div>`;
    }
  }

  // P1-C: 单议题针对性回滚
  async function restoreSingleTopic(topicId, revId) {
    if (!confirm(`确定要仅将议题 [${topicId}] 精准回溯至快照 #${revId} 吗？其他议题将完全不受影响。`)) return;
    try {
      const res = await fetch(`/api/topic/${topicId}/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rev_id: revId, reason: "用户在看板中执行单议题精准回溯" }),
      });
      const data = await res.json();
      if (res.ok) {
        closeDrawer("drawer-time-machine");
        delete state.topicsDetailCache[topicId];
        await loadMetadataList();
        showToast(`⏪ 议题 [${topicId}] 已成功精准回滚至快照 ${data.restored_from}！`);
      } else {
        alert(`单议题回滚失败: ${data.message || data.error}`);
      }
    } catch (e) {
      alert(`请求异常: ${e.message}`);
    }
  }

  // 全库回滚
  async function rollbackRevision(revId) {
    if (!confirm(`⚠️ 严重警告：确定要将全库所有议题及文件完全重置至快照 #${revId} 吗？\n该操作将同步覆写 Markdown 文件和 SQLite 数据库。`)) return;
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
        showToast(`⏪ 全库已成功回滚至快照 ${data.rolled_back_to}！`);
      } else {
        alert(`全库回滚失败: ${data.message || data.error}`);
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
        if (targetPanel) targetPanel.style.display = "block";
      });
    });

    // Filter pills
    document.querySelectorAll(".filter-pills").forEach((container) => {
      bindFilterPills(container);
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
