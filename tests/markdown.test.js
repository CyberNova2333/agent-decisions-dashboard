const test = require('node:test');
const assert = require('node:assert/strict');
const md = require('../web/markdown.js');

test('single newlines and blank lines remain distinct', () => {
  assert.match(md.render('one\ntwo\n\nfour'), /one<br>two<\/p><p>four/);
});
test('tables support alignment, escaped pipes and inline code pipes', () => {
  const html = md.render('| Left | Right |\n| :--- | ---: |\n| a\\|b | `c|d` |');
  assert.equal((html.match(/<th /g) || []).length, 2);
  assert.match(html, /text-align:right/);
  assert.match(html, /a\|b/);
  assert.match(html, /<code>c\|d<\/code>/);
});
test('code fences do not turn table or HTML into markup', () => {
  const html = md.render('```html\n<img src=x onerror=alert(1)>\n| a | b |\n| --- | --- |\n```');
  assert.ok(!html.includes('<table>'));
  assert.ok(!html.includes('<img'));
  assert.match(html, /&lt;img/);
});
test('topic Markdown paths and anchors are navigable', () => {
  assert.equal(md.safeHref('../decisions/topic-id.md'), '#topic-id');
  assert.equal(md.safeHref('/decisions/topic-id.md'), '#topic-id');
  assert.match(md.render('[Next](#topic-id)'), /href="#topic-id"/);
  assert.match(md.render('[Next](https://example.com)'), /href="https:\/\/example.com\/"/);
  assert.match(md.render('**[Next](#topic-id "label")**'), /<strong><a href="#topic-id"/);
  assert.match(md.render('[Next](https://example.com/a_(b))'), /href="https:\/\/example.com\/a_\(b\)"/);
});
test('unsafe link schemes and HTML remain literal', () => {
  for (const link of ['javascript:alert(1)', 'data:text/html,test', '//evil.test', 'file:///tmp/a', 'java\nscript:test', 'https://user:pass@example.com', '\\evil.test']) {
    assert.equal(md.safeHref(link), null, link);
  }
  assert.ok(!md.render('<svg onload=alert(1)>').includes('<svg'));
  assert.ok(!md.render('[x](javascript:alert(1))').includes('<a '));
});
test('Mermaid source stays escaped until diagram rendering', () => {
  const html = md.render('```mermaid\nflowchart LR\nA["<script>bad</script>"] --> B\n```');
  assert.match(html, /class="mermaid-diagram"/);
  assert.match(html, /&lt;script&gt;/);
  assert.ok(!html.includes('<script>'));
});
