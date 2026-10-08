"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../app/web/static/miniapp.js"), "utf8");
const host = {hidden: false, dataset: {}, innerHTML: "", querySelectorAll: () => []};
const calls = [];
const preview = {
  terms: {version: 1, volume_bytes: 10, duration_seconds: 30},
  price: 200, request_key: "a".repeat(32), plan_name: "<img src=x onerror=alert(1)>",
  lines: ["حجم مانده: ۷ گیگ", "حجم پس از تمدید: ۱۷ گیگ"], warnings: [], notice: "مصرف تا اجرا کم می‌شود",
};
let pendingResponse = null;
let loseResponse = false;
const context = vm.createContext({
  window: {addEventListener() {}}, location: {hash: ""}, setTimeout() {},
  document: {
    getElementById: () => ({}),
    querySelector: (selector) => selector.startsWith("[data-renew-host=") ? host : null,
    querySelectorAll: () => [], createElement: () => ({remove() {}}), body: {appendChild() {}},
  },
  fetch: async (url, options) => {
    calls.push({url, options});
    if (options.method === "POST" && loseResponse) throw new Error("response lost");
    if (pendingResponse) await pendingResponse;
    return {ok: true, text: async () => JSON.stringify(options.method === "POST" ? {message: "تمدید شد"} : preview)};
  },
});
// Expose the actual handlers while replacing navigation and initial loading.
vm.runInContext(source.replace(/  load\(\);\s*\}\)\(\);\s*$/, `
  reload = async () => {};
  setView = () => {};
  globalThis.testUI = {previewRenew, doRenew, showRenew, setState: (value) => {state = value;}};
})();`), context);

(async () => {
  const ui = context.testUI;
  ui.setState({commerce_allowed: true, customer: {wallet_pay_enabled: true, plans: []}});
  await ui.previewRenew(1, 2);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.method, "GET");
  assert.ok(host.innerHTML.includes("۱۷ گیگ"));
  assert.ok(host.innerHTML.includes("data-confirm-renew"));
  assert.ok(host.innerHTML.includes("&lt;img"));
  assert.ok(!host.innerHTML.includes("<img"));

  loseResponse = true;
  await ui.doRenew(1, 2);
  loseResponse = false;
  await Promise.all([ui.doRenew(1, 2), ui.doRenew(1, 2)]);
  const posts = calls.filter((call) => call.options.method === "POST");
  assert.equal(posts.length, 2);
  assert.deepEqual(JSON.parse(posts[0].options.body), JSON.parse(posts[1].options.body));
  assert.equal(JSON.parse(posts[1].options.body).preview.request_key, preview.request_key);
  await ui.doRenew(1, 2);
  assert.equal(calls.filter((call) => call.options.method === "POST").length, 2);

  let release;
  pendingResponse = new Promise((resolve) => {release = resolve;});
  const stale = ui.previewRenew(1, 2);
  ui.showRenew(1); // Close the sheet before its response arrives.
  assert.equal(host.hidden, true);
  release();
  await stale;
  assert.equal(host.innerHTML, "");
  console.log("Mini App renewal preview and payment retry checks passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
