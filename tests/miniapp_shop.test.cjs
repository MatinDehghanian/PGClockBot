"use strict";
// A shop's Mini App sends the key from its own address; the platform Mini App sends none.
const assert = require("node:assert/strict");
const { loadMiniApp, settle } = require("./miniapp_env.cjs");

const KEY = "Ab3_-xY9Ab3_-xY9Ab3_-x";
const routes = async () => ({ status: 404, body: { detail: "پیدا نشد" } });

async function shopHeaders(pathname) {
  const env = loadMiniApp({ routes, pathname });
  env.mini.app.start();
  await settle();
  assert.ok(env.calls.length > 0, "the app asked the server for /me");
  return env.calls.map((call) => call.headers["X-Mini-Shop"]);
}

(async () => {
  assert.deepEqual([...new Set(await shopHeaders("/miniapp/"))], [undefined], "platform page sends no shop");
  assert.deepEqual([...new Set(await shopHeaders(`/miniapp/s/${KEY}/`))], [KEY]);
  assert.deepEqual([...new Set(await shopHeaders(`/miniapp/s/${KEY}`))], [KEY]);
  for (const bad of ["/miniapp/s/short/", `/miniapp/s/${KEY}/extra`, `/miniapp/s/${KEY}%3Cx/`, "/other/s/" + KEY + "/"]) {
    assert.deepEqual([...new Set(await shopHeaders(bad))], [undefined], `no key from ${bad}`);
  }
  console.log("miniapp shop ok");
})().catch((err) => { console.error(err); process.exit(1); });
