"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../app/web/static/miniapp.js"), "utf8");
const calls = [];
let row = null, submit, pendingPost;
const button = {disabled: false};
const form = {
  elements: {reason: {value: "دلیل مشتری"}},
  addEventListener: (_, handler) => {submit = handler;},
  querySelector: () => button,
};
const cancelHost = {hidden: true, innerHTML: "", querySelectorAll: () => [], querySelector: () => form};
const context = vm.createContext({
  URLSearchParams, window: {addEventListener() {}}, location: {hash: ""}, setTimeout() {},
  document: {
    getElementById: () => ({}), querySelectorAll: () => [],
    querySelector: (selector) => selector.startsWith("[data-cancellation-host=") ? cancelHost : null,
    createElement: () => ({remove() {}}), body: {appendChild() {}},
  },
  fetch: async (url, options) => {
    calls.push({url, options});
    if (options.method === "POST") {
      if (pendingPost) await pendingPost;
      row = {id: 1, status: "pending", label: "در انتظار بررسی", operator_note: "<svg onload=alert(1)>", refund_amount: null};
    }
    return {ok: true, text: async () => JSON.stringify({request: row})};
  },
});
vm.runInContext(source.replace(/  load\(\);\s*\}\)\(\);\s*$/, `
  toast = () => {};
  globalThis.testUI = {showCancellation, serviceCardHtml};
})();`), context);

(async () => {
  const ui = context.testUI;
  await ui.showCancellation(11);
  assert.ok(cancelHost.innerHTML.includes("data-cancellation-form"));
  let release;
  pendingPost = new Promise((resolve) => {release = resolve;});
  const event = {preventDefault() {}};
  const first = submit(event);
  await submit(event);
  assert.equal(calls.filter((call) => call.options.method === "POST").length, 1);
  release();
  await first;
  assert.ok(!cancelHost.innerHTML.includes("data-cancellation-form"));
  assert.ok(cancelHost.innerHTML.includes("&lt;svg"));
  assert.ok(!cancelHost.innerHTML.includes("<svg"));
  const card = ui.serviceCardHtml({id: 11, is_cancelled: true, addons_allowed: true});
  assert.ok(!card.includes("data-renew="));
  assert.ok(!card.includes("data-addons="));
  assert.ok(card.includes('data-cancellation="11"'));
  console.log("Mini App cancellation interactions passed");
})().catch((err) => {console.error(err); process.exitCode = 1;});
