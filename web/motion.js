/* Anime.js 渐进增强；只观察新增卡片，不改变台账与表单行为。 */
(() => {
  if (!window.anime) return;
  const { animate, createScope, stagger, utils } = window.anime;
  let motion;
  function start() {
    motion?.revert();
    motion = createScope({ mediaQueries: { reduced: '(prefers-reduced-motion: reduce)' } }).add(self => {
      if (self.matches.reduced) return;
      const enter = targets => animate(targets, { opacity: [0, 1], y: [8, 0], duration: 300, delay: stagger(40), ease: 'outQuart', onComplete: utils.cleanInlineStyles });
      enter('.brand > *, .header-actions > *');
      const known = new WeakSet();
      self.add('reveal', root => {
        const items = root.matches('.topic-card,.toast') ? [root] : [...root.querySelectorAll('.topic-card,.toast')];
        const fresh = items.filter(el => !known.has(el) && el.getClientRects().length);
        fresh.forEach(el => known.add(el));
        if (fresh.length) enter(fresh.slice(0, 16));
      });
      const observer = new MutationObserver(records => {
        for (const record of records) for (const node of record.addedNodes) if (node instanceof Element) self.methods.reveal(node);
      });
      self.methods.reveal(document.body);
      observer.observe(document.body, { childList: true, subtree: true });
      return () => observer.disconnect();
    });
  }
  start();
  addEventListener('pagehide', () => { motion?.revert(); motion = undefined; });
  addEventListener('pageshow', event => { if (event.persisted) start(); });
})();
