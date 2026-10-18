const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader, renderPreview } = require('../app/web/static/user-service-preview.js');

test('preview renders loading and the selected service', async () => {
  const states = [];
  const load = createLoader(async (url, options) => {
    assert.equal(url, '/users/7/services/11/preview');
    assert.equal(options.credentials, 'same-origin');
    return { ok: true, json: async () => ({ username: 'service11' }) };
  }, (state) => states.push(state));
  await load('/users/7/services/11/preview');
  assert.deepEqual(states, [{ loading: true }, { data: { username: 'service11' } }]);
});

test('a late response cannot replace the newly selected service', async () => {
  const states = [];
  const replies = [];
  const signals = [];
  const load = createLoader((url, options) => {
    signals.push(options.signal);
    return new Promise((resolve) => replies.push(resolve));
  }, (state) => states.push(state));
  const first = load('/first');
  const second = load('/second');
  assert.equal(signals[0].aborted, true);
  replies[1]({ ok: true, json: async () => ({ username: 'second' }) });
  await second;
  replies[0]({ ok: true, json: async () => ({ username: 'first' }) });
  await first;
  assert.equal(states.at(-1).data.username, 'second');
  assert.equal(states.filter((state) => state.data).length, 1);
});

test('errors and unauthorized replies show a safe retry state', async () => {
  for (const fetchInfo of [
    async () => ({ ok: false, status: 403 }),
    async () => { throw new Error('secret-url'); },
    async () => ({ ok: true, json: async () => { throw new Error('bad json'); } }),
  ]) {
    const states = [];
    await createLoader(fetchInfo, (state) => states.push(state))('/preview');
    assert.equal(typeof states.at(-1).error, 'string');
    assert.equal(states.at(-1).error.includes('secret'), false);
  }
});

test('preview inserts hostile text as text and shows cached fallback warnings', () => {
  const elements = new Map();
  const field = { dataset: { previewField: 'username' } };
  const modal = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, {});
      return elements.get(selector);
    },
    querySelectorAll() { return [field]; },
    setAttribute() {},
  };
  const hostile = '<img src=x onerror=alert(1)>';
  renderPreview(modal, { data: { username: hostile, warning: 'پنل در دسترس نیست', status_tone: hostile } });
  assert.equal(field.textContent, hostile);
  assert.equal(field.innerHTML, undefined);
  assert.equal(elements.get('[data-preview-error]').hidden, false);
  assert.equal(elements.get('[data-preview-content]').hidden, false);
  assert.equal(elements.get('[data-preview-field="status_title"]').className, 'badge neutral');
  renderPreview(modal, { loading: true });
  assert.equal(elements.get('[data-preview-content]').hidden, true);
  assert.equal(elements.get('[data-preview-retry]').disabled, true);
});
