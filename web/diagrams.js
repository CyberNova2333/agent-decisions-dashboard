// Render visible Mermaid blocks from pinned local resources, never a remote CDN.
(() => {
  "use strict";
  let library, sequence = 0, queue = Promise.resolve();
  const states = new WeakMap();
  function loadLibrary() {
    if (!library) library = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "vendor/mermaid-12.1.0.min.js";
      script.onload = () => resolve(window.mermaid);
      script.onerror = () => { library = null; script.remove(); reject(new Error("本地图表资源加载失败")); };
      document.head.appendChild(script);
    });
    return library;
  }
  function draw(node) {
    let state = states.get(node);
    if (!state) {
      const source = node.querySelector("code")?.textContent || "";
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "查看图表源码";
      details.append(summary, node.querySelector("pre"));
      const canvas = document.createElement("div");
      canvas.className = "mermaid-canvas";
      node.replaceChildren(canvas, details);
      state = { source, canvas, details, generation: 0 };
      states.set(node, state);
    }
    const generation = ++state.generation;
    state.canvas.textContent = "正在绘制流程图…";
    queue = queue.then(async () => {
      if (!node.isConnected || state.generation !== generation) return;
      try {
        if (state.source.length > 50000) throw new Error("图表超过 50,000 字符，请拆分后查看");
        if (/%%\s*\{|^\s*---|\b(?:img|icon)\s*:|url\s*\(|@import/im.test(state.source)) throw new Error("图表支持标准 Mermaid 语法；不执行配置指令或加载外部图片");
        const mermaid = await loadLibrary();
        if (!node.isConnected || state.generation !== generation) return;
        const css = getComputedStyle(document.body);
        const color = key => css.getPropertyValue(key).trim();
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", suppressErrorRendering: true,
          maxTextSize: 50000, maxEdges: 500, htmlLabels: false,
          flowchart: { htmlLabels: false }, theme: "base",
          themeVariables: { primaryColor: color("--bg-input"), primaryTextColor: color("--text-main"),
            primaryBorderColor: color("--color-primary"), lineColor: color("--text-dim"),
            secondaryColor: color("--bg-card"), tertiaryColor: color("--bg-app"),
            background: color("--bg-card"), mainBkg: color("--bg-input"),
            textColor: color("--text-main"), nodeTextColor: color("--text-main"),
            edgeLabelBackground: color("--bg-card"), fontFamily: color("--font-family") } });
        const { svg } = await mermaid.render(`board-mermaid-${++sequence}`, state.source);
        if (node.isConnected && state.generation === generation) {
          // The library's strict mode sanitizes SVG and disables diagram click callbacks.
          state.canvas.innerHTML = svg;
          state.canvas.classList.remove("diagram-error");
        }
      } catch (error) {
        if (node.isConnected && state.generation === generation) {
          state.canvas.textContent = `流程图无法绘制，请核对源码：${String(error.message || error).slice(0, 500)}`;
          state.canvas.classList.add("diagram-error");
          state.details.open = true;
        }
      }
    });
  }
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) { observer.unobserve(entry.target); draw(entry.target); }
  });
  function discover(node) {
    if (!(node instanceof Element)) return;
    if (node.matches(".mermaid-diagram") && !states.has(node)) observer.observe(node);
    for (const diagram of node.querySelectorAll(".mermaid-diagram")) if (!states.has(diagram)) observer.observe(diagram);
  }
  document.addEventListener("DOMContentLoaded", () => {
    discover(document.body);
    new MutationObserver(records => {
      for (const record of records) {
        for (const node of record.removedNodes) if (node instanceof Element && !node.isConnected) {
          observer.unobserve(node);
          for (const diagram of node.querySelectorAll(".mermaid-diagram")) observer.unobserve(diagram);
        }
        for (const node of record.addedNodes) discover(node);
      }
    }).observe(document.body, { childList: true, subtree: true });
    new MutationObserver(() => {
      for (const node of document.querySelectorAll(".mermaid-diagram")) {
        const state = states.get(node);
        if (state) state.generation++;
        observer.observe(node);
      }
    }).observe(document.body, { attributes: true, attributeFilter: ["data-theme", "data-accent"] });
  });
})();
