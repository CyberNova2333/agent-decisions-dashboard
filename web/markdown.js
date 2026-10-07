// Small, dependency-free Markdown renderer. Raw HTML is always escaped.
(function (root) {
  "use strict";
  const escape = value => String(value).replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[ch]);

  function safeHref(value) {
    const href = value.trim();
    if (!href || /[\x00-\x20\x7f\\]/.test(href)) return null;
    if (href.startsWith("#")) return href;
    const topic = href.match(/^(?:(?:\/|\.\.?\/)?decisions\/|\.\/)?([A-Za-z0-9_-]+)\.md(?:#[^\s]*)?$/);
    if (topic) return `#${topic[1]}`;
    if (/^https?:\/\//i.test(href)) {
      try { const url = new URL(href); return url.username || url.password ? null : url.href; }
      catch (_) { return null; }
    }
    if (/^\/(?!\/)/.test(href)) return href;
    return null;
  }

  function inline(text) {
    let result = "", offset = 0;
    const tokens = /(`+)([^`\n]*?)\1|\[([^\]\n]+)\]\(((?:[^\s()]|\([^()\s]*\))+)(?:[ \t]+"[^"\n]*")?\)|\*\*([^*\n]+)\*\*/g;
    for (const match of text.matchAll(tokens)) {
      result += escape(text.slice(offset, match.index));
      if (match[1]) result += `<code>${escape(match[2])}</code>`;
      else if (match[3]) {
        const href = safeHref(match[4]);
        result += href ? `<a href="${escape(href)}" rel="noopener noreferrer">${escape(match[3])}</a>` : escape(match[0]);
      } else result += `<strong>${inline(match[5])}</strong>`;
      offset = match.index + match[0].length;
    }
    return result + escape(text.slice(offset));
  }

  function cells(line) {
    const parts = []; let cell = "", fence = 0;
    const source = line.trim();
    for (let i = 0; i < source.length; i++) {
      if (source[i] === "\\" && source[i + 1] === "|") { cell += "|"; i++; continue; }
      if (source[i] === "`") {
        let end = i + 1;
        while (source[end] === "`") end++;
        const size = end - i;
        if (!fence) fence = size; else if (size === fence) fence = 0;
        cell += source.slice(i, end); i = end - 1; continue;
      }
      if (source[i] === "|" && !fence) { parts.push(cell.trim()); cell = ""; }
      else cell += source[i];
    }
    parts.push(cell.trim());
    if (source.startsWith("|")) parts.shift();
    if (source.endsWith("|") && !source.endsWith("\\|")) parts.pop();
    return parts;
  }

  function render(value) {
    const lines = String(value ?? "").replace(/\r\n?/g, "\n").split("\n");
    const out = []; let paragraph = [];
    const flush = () => {
      if (paragraph.length) out.push(`<p>${paragraph.map(inline).join("<br>")}</p>`);
      paragraph = [];
    };
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const fence = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
      if (fence) {
        flush(); const code = [];
        const close = new RegExp(`^ {0,3}${fence[1][0]}{${fence[1].length},}\\s*$`);
        while (++i < lines.length && !close.test(lines[i])) code.push(lines[i]);
        const source = code.join("\n");
        const language = fence[2].trim().toLowerCase();
        const mermaid = language === "mermaid" || (language === "flowchart" && /^\s*(?:flowchart|graph)\s/.test(source));
        out.push(mermaid ? `<div class="mermaid-diagram"><pre><code>${escape(source)}</code></pre></div>` : `<pre><code>${escape(source)}</code></pre>`); continue;
      }
      if (!line.trim()) { flush(); continue; }
      const head = line.match(/^ {0,3}(#{1,6})\s+(.+)$/);
      if (head) { flush(); out.push(`<h${head[1].length}>${inline(head[2])}</h${head[1].length}>`); continue; }
      const separators = i + 1 < lines.length ? cells(lines[i + 1]) : [];
      const header = cells(line);
      if (line.includes("|") && separators.length === header.length && separators.every(c => /^:?-{3,}:?$/.test(c))) {
        flush();
        const align = separators.map(c => c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : "left");
        const row = (values, tag) => `<tr>${header.map((_, col) => `<${tag} style="text-align:${align[col]}">${inline(values[col] || "")}</${tag}>`).join("")}</tr>`;
        const rows = []; i++;
        while (i + 1 < lines.length && lines[i + 1].trim() && lines[i + 1].includes("|") && !/^\s*(`{3,}|~{3,})/.test(lines[i + 1])) rows.push(row(cells(lines[++i]), "td"));
        out.push(`<div class="markdown-table-scroll" tabindex="0" role="region" aria-label="Markdown 表格"><table><thead>${row(header, "th")}</thead><tbody>${rows.join("")}</tbody></table></div>`); continue;
      }
      const list = line.match(/^\s*(?:([-+*])|\d+[.)])\s+(.+)$/);
      if (list) {
        flush(); const tag = list[1] ? "ul" : "ol", items = [inline(list[2])];
        const pattern = list[1] ? /^\s*[-+*]\s+(.+)$/ : /^\s*\d+[.)]\s+(.+)$/;
        while (i + 1 < lines.length && pattern.test(lines[i + 1])) items.push(inline(lines[++i].match(pattern)[1]));
        out.push(`<${tag}>${items.map(item => `<li>${item}</li>`).join("")}</${tag}>`); continue;
      }
      if (/^\s*>/.test(line)) {
        flush(); const quoted = [inline(line.replace(/^\s*>\s?/, ""))];
        while (i + 1 < lines.length && /^\s*>/.test(lines[i + 1])) quoted.push(inline(lines[++i].replace(/^\s*>\s?/, "")));
        out.push(`<blockquote>${quoted.join("<br>")}</blockquote>`); continue;
      }
      paragraph.push(line);
    }
    flush();
    return `<div class="markdown-body">${out.join("")}</div>`;
  }
  root.DashboardMarkdown = { render, safeHref };
  if (typeof module !== "undefined") module.exports = root.DashboardMarkdown;
})(typeof window === "undefined" ? globalThis : window);
