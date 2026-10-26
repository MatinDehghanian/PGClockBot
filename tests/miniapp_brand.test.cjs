"use strict";
// Mini App brand and shortcuts: escaped shop text, safe logo and colour, shortcuts only for open sections.
const assert = require("node:assert/strict");
const { loadMiniApp, settle } = require("./miniapp_env.cjs");

const HOSTILE = "<img src=x onerror=alert(1)>";
const KEY = "Ab3_-xY9Ab3_-xY9Ab3_-x";
const NAV = {
  user: [{ id: "home", label: "خانه", icon: "home" }, { id: "services", label: "سرویس‌ها", icon: "svc" },
    { id: "shop", label: "خرید", icon: "shop" }, { id: "account", label: "حساب", icon: "account" }],
  admin: [{ id: "home", label: "داشبورد", icon: "home" }, { id: "ops", label: "میانبرها", icon: "ops" }],
};
const HOME = { service_count: 1, attention: [{ id: 7, username: "soon", status: "active", status_fa: "فعال", remaining_label: "۲ روز" }],
  recent: [{ id: 8, username: "svc", status: "active", status_fa: "فعال", remaining_label: "۹ روز" }] };

function me(persona, extra) {
  const commerce = persona !== "admin";
  return {
    persona, nav: NAV[persona], commerce_allowed: commerce, currency: "تومان", panel_base: "https://panel.example.com",
    user: { id: 1, name: "a" },
    brand: { name: HOSTILE, tagline: HOSTILE, logo_url: "", accent: "", notice: HOSTILE },
    customer: { wallet: 1000, wallet_pay_enabled: commerce, qr_enabled: true, commerce_allowed: commerce, home: commerce ? HOME : { service_count: 0, attention: [], recent: [] } },
    ...(extra || {}),
  };
}

const OPS = (canReview) => ({ stats: { pending: 1, tickets: 0, revenue: 5 }, can_review: canReview, panel_base: "https://panel.example.com",
  panel_links: [{ id: "finance", label: HOSTILE, path: "/finance" }] });

async function boot(body, { pathname, canReview = true } = {}) {
  const env = loadMiniApp({
    pathname,
    routes: async (_method, url) => {
      if (url === "/api/mini/me") return { status: 200, body };
      if (url === "/api/mini/ops") return { status: 200, body: OPS(canReview) };
      return { status: 404, body: { detail: "پیدا نشد" } };
    },
  });
  const props = new Map();
  env.context.document.documentElement.style = {
    setProperty: (name, value) => props.set(name, value),
    removeProperty: (name) => props.delete(name),
  };
  env.props = props;
  env.mini.app.start();
  await settle();
  return env;
}

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test("shop name, caption and notice are escaped", async () => {
  const env = await boot(me("user"));
  const html = env.element("root").innerHTML;
  assert.ok(!html.includes("<img src=x"), "no raw markup from shop text");
  assert.ok(html.split("&lt;img src=x").length - 1 >= 3, "name, caption and notice are shown escaped");
  assert.ok(html.includes("اطلاعیهٔ فروشگاه"));
});

test("an empty notice shows no banner", async () => {
  const env = await boot(me("user", { brand: { name: "Nova", tagline: "", logo_url: "", accent: "", notice: "  " } }));
  assert.ok(!env.element("root").innerHTML.includes("اطلاعیهٔ فروشگاه"));
});

test("only a saved profile photo is used as the logo", async () => {
  for (const [logo, shown] of [
    ["/media/uploads/r5_bot_tg_photo_ab12.jpg", true], ["https://evil.example/x.jpg", false],
    ['/media/uploads/x.jpg" onerror="alert(1)', false], ["javascript:alert(1)", false], ["/media/uploads/../x.jpg", false],
  ]) {
    const env = await boot(me("user", { brand: { name: "Nova", logo_url: logo } }));
    const html = env.element("root").innerHTML;
    assert.equal(html.includes("data-brand-logo"), shown, logo);
    assert.ok(html.includes('class="brand-initial">N<'), "the initial is always there as a fallback");
  }
});

test("a valid accent colour is applied with readable text, anything else keeps the default", async () => {
  let env = await boot(me("user", { brand: { name: "a", accent: "#f97316" } }));
  assert.equal(env.props.get("--brand-custom"), "#f97316");
  assert.equal(env.props.get("--accent-ink"), "#1c1007", "dark text on a light orange");
  env = await boot(me("user", { brand: { name: "a", accent: "#1e3a8a" } }));
  assert.equal(env.props.get("--accent-ink"), "#ffffff", "white text on a dark blue");
  for (const bad of ["red", "#fff", "#123456;background:url(x)", "", null]) {
    env = await boot(me("user", { brand: { name: "a", accent: bad } }));
    assert.ok(!env.props.has("--brand-custom"), String(bad));
  }
});

test("a shop without a saved brand shows its own name", async () => {
  const body = me("user", { shop: { name: "Shop Name" } });
  delete body.brand;
  const env = await boot(body, { pathname: `/miniapp/s/${KEY}/` });
  assert.ok(env.element("root").innerHTML.includes("Shop Name"));
});

const SHORTCUTS = {
  topup: 'class="shortcut" data-action="topup"',
  support: 'class="shortcut" data-action="goto" data-view="support"',
  club: 'class="shortcut" data-action="goto" data-view="club"',
  gift: 'class="shortcut" data-action="gift-code"',
  guides: 'class="shortcut" data-action="guides" data-id="7"',
  renew: 'class="shortcut" data-action="open-service" data-id="7" data-then="renew"',
  buy: 'class="shortcut" data-action="goto" data-view="shop"',
};

test("home shortcuts appear only for the sections this Mini App has opened", async () => {
  let env = await boot(me("user"));
  let html = env.element("root").innerHTML;
  for (const [name, markup] of Object.entries(SHORTCUTS)) {
    assert.ok(html.includes(markup), `platform shows ${name}; renew and guides act on the service ending soon`);
  }
  env = await boot(me("user", { sections: ["services", "shop"], shop: { name: "s" } }), { pathname: `/miniapp/s/${KEY}/` });
  html = env.element("root").innerHTML;
  for (const name of ["topup", "support", "club", "gift", "guides"]) {
    assert.ok(!html.includes(SHORTCUTS[name]), `closed section hidden: ${name}`);
  }
  assert.ok(html.includes(SHORTCUTS.buy) && html.includes(SHORTCUTS.renew));
});

test("renew shortcut needs a service and wallet payments", async () => {
  const customer = { wallet: 0, wallet_pay_enabled: false, qr_enabled: true, commerce_allowed: true };
  let env = await boot(me("user", { customer: { ...customer, home: HOME } }));
  assert.ok(!env.element("root").innerHTML.includes(SHORTCUTS.renew), "no renew without wallet payments");
  env = await boot(me("user", { customer: { ...customer, wallet_pay_enabled: true, home: { service_count: 0, attention: [], recent: [] } } }));
  assert.ok(!env.element("root").innerHTML.includes('data-then="renew"'), "no renew without a service");
});

test("admin shortcuts offer receipt review only to accounts that may review", async () => {
  let env = await boot(me("admin"));
  let html = env.element("root").innerHTML;
  assert.ok(/class="shortcut" data-action="goto" data-view="review"/.test(html));
  assert.ok(html.includes('data-action="open-panel" data-path="/finance"'));
  assert.ok(!html.includes("<img src=x"), "panel link labels are escaped");
  env = await boot(me("admin"), { canReview: false });
  html = env.element("root").innerHTML;
  assert.ok(!html.includes('data-view="review"'));
  assert.ok(!html.includes('data-action="topup"') && !html.includes('data-view="shop"'), "no commerce shortcuts for admin");
});

(async () => {
  for (const [name, fn] of tests) {
    try { await fn(); } catch (err) { console.error("FAILED:", name); throw err; }
  }
  console.log(`Mini App brand: ${tests.length} checks passed`);
})().catch((err) => { console.error(err); process.exitCode = 1; });
