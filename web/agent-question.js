(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.DashboardAgentQuestion = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function normalize(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw) ||
        Object.keys(raw).some((key) => !["question", "options"].includes(key)) ||
        typeof raw.question !== "string" || !raw.question.trim() || raw.question.length > 2000 ||
        !Array.isArray(raw.options) || raw.options.length < 2 || raw.options.length > 8) return null;
    const options = [];
    const labels = new Set();
    for (const item of raw.options) {
      const option = typeof item === "string" ? { label: item } : item;
      if (!option || typeof option !== "object" || Array.isArray(option) ||
          Object.keys(option).some((key) => !["label", "description"].includes(key)) ||
          typeof option.label !== "string" || !option.label.trim() || option.label.length > 200 ||
          /[\r\n]/.test(option.label) ||
          (option.description !== undefined && (typeof option.description !== "string" || option.description.length > 1000))) return null;
      const label = option.label.trim();
      if (labels.has(label)) return null;
      labels.add(label);
      options.push({ label, description: option.description || "" });
    }
    return { question: raw.question.trim(), options };
  }

  function parse(reply) {
    const source = String(reply || "");
    const lines = source.split(/\r?\n/);
    const candidates = [];
    let open = null;
    let offset = 0;
    for (const line of lines) {
      if (open) {
        const close = /^ {0,3}(`{3,}|~{3,})[ \t]*$/.exec(line);
        if (close && close[1][0] === open.char && close[1].length >= open.length) {
          if (open.question) candidates.push({ start: open.start, end: offset + line.length, body: open.body.join("\n") });
          open = null;
        } else if (open.question) open.body.push(line);
      } else {
        const fence = /^ {0,3}(`{3,}|~{3,})([^\r\n]*)$/.exec(line);
        if (fence && !(fence[1][0] === "`" && fence[2].includes("`"))) {
          open = { char: fence[1][0], length: fence[1].length, start: offset, body: [], question: fence[1][0] === "`" && fence[2].trim() === "agent-question" };
        }
      }
      // Use the original newline length to remove only the actual protocol block.
      offset += line.length + (source.slice(offset + line.length, offset + line.length + 2) === "\r\n" ? 2 : 1);
    }
    const fallback = { cleanReply: source, question: null };
    if ((open && open.question) || candidates.length !== 1) return fallback;
    let raw;
    try { raw = JSON.parse(candidates[0].body); } catch (_) { return fallback; }
    const question = normalize(raw);
    if (!question) return fallback;
    return { cleanReply: (source.slice(0, candidates[0].start) + source.slice(candidates[0].end)).trim(), question };
  }

  function prefix(question, selected) {
    if (!question || !Number.isInteger(selected) || !question.options[selected]) return "";
    return `问题：${question.question}\n所选答案：${question.options[selected].label}`;
  }

  function compose(question, selected, text) {
    const answer = prefix(question, selected);
    let opinion = String(text || "");
    if (answer && question && opinion.startsWith("问题：")) {
      const answerLineStart = opinion.indexOf("\n所选答案：");
      const secondLineEnd = opinion.indexOf("\n", answerLineStart + 1);
      if (answerLineStart >= 0) {
        opinion = secondLineEnd >= 0 ? opinion.slice(secondLineEnd + 1) : "";
        if (opinion.startsWith("\n")) opinion = opinion.slice(1);
      }
    }
    return answer ? answer + (opinion ? "\n\n" + opinion : "") : opinion;
  }

  function splitSaved(question, text) {
    const opinion = String(text || "");
    if (question) {
      for (let selected = 0; selected < question.options.length; selected += 1) {
        const answer = prefix(question, selected);
        if (opinion === answer) return { selected, text: "" };
        if (opinion.startsWith(answer + "\n\n")) return { selected, text: opinion.slice(answer.length + 2) };
      }
    }
    return { selected: null, text: opinion };
  }

  return { parse, compose, splitSaved };
});
