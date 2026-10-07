const test = require('node:test');
const assert = require('node:assert/strict');
const questions = require('../web/agent-question.js');

const raw = { question: '请选择实现路径', options: ['本轮实施', { label: '稍后处理', description: '先完成已有功能' }] };
const block = (value = raw) => '```agent-question\n' + JSON.stringify(value) + '\n```';

test('one complete question accepts string and described options without a default selection', () => {
  const result = questions.parse('背景\n\n' + block() + '\n\n后记');
  assert.equal(result.question.question, raw.question);
  assert.equal(result.question.options[1].description, '先完成已有功能');
  assert.match(result.cleanReply, /^背景\s+后记$/);
  assert.deepEqual(questions.splitSaved(result.question, '原话\n下一行'), { selected: null, text: '原话\n下一行' });
});

test('outer code fences and quoted or indented examples never activate questions', () => {
  for (const source of ['````markdown\n' + block() + '\n````', '~~~markdown\n' + block() + '\n~~~',
    block().split('\n').map(line => '> ' + line).join('\n'), block().split('\n').map(line => '    ' + line).join('\n')]) {
    assert.deepEqual(questions.parse(source), { cleanReply: source, question: null });
  }
});

test('invalid, repeated, ambiguous and unclosed protocols retain all original text', () => {
  const invalid = [null, [], {}, { ...raw, options: ['one'] }, { ...raw, options: Array(9).fill('one') },
    { ...raw, options: ['one', ' one '] }, { ...raw, options: ['one', 2] },
    { ...raw, options: ['one', { label: 'two', description: 2 }] },
    { ...raw, options: ['one', { label: 'two', extra: true }] },
    { ...raw, allow_multiple: true }, { ...raw, question: 'a'.repeat(2001) },
    { ...raw, options: ['one', 'multi\nline'] }, { ...raw, options: ['one', 'a'.repeat(201)] }];
  const sources = [...invalid.map(value => block(value)), '```agent-question\ninvalid\n```', block() + '\n' + block(),
    '```agent-question\n' + JSON.stringify(raw), block() + '\n```agent-question\n{}'];
  for (const source of sources) assert.deepEqual(questions.parse(source), { cleanReply: source, question: null });
});

test('fence scanner handles CRLF and longer backtick delimiters without losing surrounding text', () => {
  const source = ('before\n````agent-question\n' + JSON.stringify(raw) + '\n````\nafter').replaceAll('\n', '\r\n');
  const result = questions.parse(source);
  assert.equal(result.question.question, raw.question);
  assert.equal(result.cleanReply, 'before\r\n\r\nafter');
});

test('choice changes, cancellation and exact saved-prefix restoration preserve multiline free text', () => {
  const question = questions.parse(block()).question;
  const text = '第一行\n第二行\n\n补充段落';
  for (const selected of [0, 1, null]) {
    const saved = questions.compose(question, selected, text);
    assert.deepEqual(questions.splitSaved(question, saved), { selected, text });
    if (selected !== null) assert.ok(saved.startsWith('问题：请选择实现路径\n所选答案：' + question.options[selected].label + '\n\n'));
  }
  assert.equal(questions.compose(question, null, text), text);
  assert.deepEqual(questions.splitSaved(question, questions.compose(question, 0, '')), { selected: 0, text: '' });
  const edited = '问题：请选择实现路径\n所选答案：本轮实施但有条件\n\n' + text;
  assert.deepEqual(questions.splitSaved(question, edited), { selected: null, text: edited });
  assert.equal(questions.compose(question, null, edited), edited);
  assert.equal(questions.compose(question, 1, edited), '问题：请选择实现路径\n所选答案：稍后处理\n\n' + text);
});

test('HTML and script-like strings remain inert data, not interpreted markup', () => {
  const hostile = { question: '<img src=x onerror=alert(1)>', options: ['<svg onload=alert(1)>', { label: '" onclick="alert(1)', description: '</button><script>alert(1)</script>' }] };
  const question = questions.parse(block(hostile)).question;
  assert.equal(question.question, hostile.question);
  assert.equal(question.options[1].description, hostile.options[1].description);
  assert.equal(questions.compose(question, 0, '<b>text</b>'), '问题：' + hostile.question + '\n所选答案：' + hostile.options[0] + '\n\n<b>text</b>');
});
