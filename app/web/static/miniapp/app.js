/* Mini App shell: routing, screens per role, bottom sheet and user actions. */
(function (root) {
  "use strict";

  const { core, render: R } = root.PGMini;
  const tg = core.tg;
  const doc = root.document;

  const SEARCH_DEBOUNCE_MS = 350;
  const ACTIVITY_PAGE = 20;
  const ACTIVITY_MORE = 50;
  // Links saved before the redesign keep working.
  const LEGACY_VIEWS = new Map([["wallet", "account"]]);
  const UNKNOWN_OUTCOME = "نتیجهٔ درخواست مشخص نشد. پیش از تلاش دوباره، سرویس‌ها و تراکنش‌ها را بررسی کنید.";
  const RENEW_UNKNOWN_OUTCOME = "نتیجهٔ تمدید مشخص نشد. دوباره «تأیید» را بزنید؛ این تمدید فقط یک بار انجام می‌شود.";

  const els = {};
  const state = {
    me: null,
    view: "home",
    serviceId: null,
    ticketId: null,
    tickets: new Map(),
    then: null,
    resources: {},
    services: null,
    details: new Map(),
    selectedPlanId: null,
    activityLimit: ACTIVITY_PAGE,
    renewPreview: null,
    topupCurrent: null,
    checkout: null,
    addonPacks: [],
    sheet: null,
    sheetSeq: 0,
    viewSeq: 0,
    busy: new Set(),
    searchTimer: null,
    backBound: false,
  };

  /* ---------- helpers ---------- */

  function persona() {
    return (state.me && state.me.persona) || "user";
  }

  function commerce() {
    return !!(state.me && state.me.commerce_allowed);
  }

  function customer() {
    return (state.me && state.me.customer) || {};
  }

  function features() {
    const c = customer();
    return { walletPay: !!c.wallet_pay_enabled, qr: !!c.qr_enabled };
  }

  function homeViewId() {
    const nav = (state.me && state.me.nav) || [];
    return nav.length ? nav[0].id : "home";
  }

  // Screens below a tab: where Back goes and which tab stays highlighted.
  const SUB_VIEWS = new Map([
    ["service", { parent: "services", tab: "services" }],
    ["support", { parent: "account", tab: "account" }],
    ["ticket", { parent: "support", tab: "account" }],
  ]);

  function navTab(view) {
    const sub = SUB_VIEWS.get(view);
    return sub ? sub.tab : view;
  }

  function viewAllowed(view) {
    if (SUB_VIEWS.has(view)) return commerce();
    return ((state.me && state.me.nav) || []).some((n) => n.id === view);
  }

  function intAttr(el, name) {
    const n = Number(el.getAttribute(name));
    return Number.isInteger(n) && n > 0 ? n : 0;
  }

  /** Run one action at a time per key; the trigger stays disabled while it runs. */
  async function guarded(key, trigger, fn) {
    if (state.busy.has(key)) return;
    state.busy.add(key);
    if (trigger) trigger.disabled = true;
    try {
      await fn();
    } finally {
      state.busy.delete(key);
      if (trigger && trigger.isConnected) trigger.disabled = false;
    }
  }

  /* ---------- resources ---------- */

  const FETCHERS = {
    plans: () => core.api("/api/mini/plans"),
    activity: () => core.api("/api/mini/activity?limit=" + state.activityLimit),
    ops: () => core.api("/api/mini/ops"),
    topup: () => core.api("/api/mini/topup"),
    support: () => core.api("/api/mini/support"),
  };

  const inflight = new Map();

  /** Load a shared resource once (callers share one request); re-render the view when it settles. */
  function ensure(name) {
    const current = state.resources[name];
    if (current && current.status === "ready") return Promise.resolve(current);
    if (inflight.has(name)) return inflight.get(name);
    state.resources[name] = { status: "loading" };
    const seq = state.viewSeq;
    const request = (async () => {
      let result;
      try {
        result = { status: "ready", data: await FETCHERS[name]() };
      } catch (err) {
        result = { status: "error", error: err.message };
      }
      // An invalidated request must not overwrite newer state.
      if (inflight.get(name) !== request) return result;
      inflight.delete(name);
      state.resources[name] = result;
      if (seq === state.viewSeq) renderView();
      return result;
    })();
    inflight.set(name, request);
    return request;
  }

  function invalidate(name) {
    delete state.resources[name];
    inflight.delete(name);
  }

  function resource(name) {
    const r = state.resources[name];
    if (!r) {
      ensure(name);
      return { status: "loading" };
    }
    return r;
  }

  function invalidateCommerce() {
    invalidate("activity");
    state.services = null;
    state.details.clear();
  }

  async function reloadMe() {
    const me = await core.api("/api/mini/me");
    applyMe(me);
  }

  function applyMe(me) {
    state.me = me;
    core.setCurrency(me.currency);
    els.nav.innerHTML = R.navHtml(me.nav, navTab(state.view));
  }

  /* ---------- routing and back button ---------- */

  function hashRoute() {
    const raw = String(root.location.hash || "").replace(/^#/, "");
    const match = /^(service|ticket)\/(\d{1,10})$/.exec(raw);
    if (match && match[1] === "service") return { view: "service", serviceId: Number(match[2]) };
    if (match) return { view: "ticket", ticketId: Number(match[2]) };
    return { view: LEGACY_VIEWS.get(raw) || raw || "home" };
  }

  function go(view, opts) {
    const options = opts || {};
    const next = viewAllowed(view) ? view : homeViewId();
    closeSheet();
    if (state.view === "shop" && next !== "shop") dropCheckout();
    state.view = next;
    state.serviceId = next === "service" ? Number(options.serviceId) || null : null;
    // The detail screen always shows live usage, so each visit reads it again.
    if (state.serviceId) state.details.delete(state.serviceId);
    state.ticketId = next === "ticket" ? Number(options.ticketId) || null : null;
    if (state.ticketId) state.tickets.delete(state.ticketId);
    state.then = options.then || null;
    if (next === "service" && !state.serviceId) state.view = "services";
    if (next === "ticket" && !state.ticketId) state.view = "support";
    const hash = state.view === "service" ? "service/" + state.serviceId
      : state.view === "ticket" ? "ticket/" + state.ticketId : state.view;
    if (String(root.location.hash || "").replace(/^#/, "") !== hash) {
      root.history.replaceState(null, "", "#" + hash);
    }
    state.viewSeq += 1;
    els.nav.innerHTML = R.navHtml(state.me.nav, navTab(state.view));
    renderView();
    root.scrollTo(0, 0);
    syncTelegramBackButton();
  }

  function hasOpenOverlay() {
    return !!state.sheet;
  }

  function closeOpenOverlays() {
    if (!state.sheet) return false;
    closeSheet();
    return true;
  }

  /**
   * Android/iOS system back only navigates *inside* a Mini App when
   * Telegram.WebApp.BackButton is visible. Without show()+onClick, the OS
   * back key closes the WebApp. Chat bots cannot intercept hardware back —
   * only this WebApp API can.
   */
  function syncTelegramBackButton() {
    if (!tg || !tg.BackButton) return;
    const show = hasOpenOverlay() || (state.me && state.view !== homeViewId());
    try {
      if (show) tg.BackButton.show();
      else tg.BackButton.hide();
    } catch (_) {}
  }

  function onTelegramBack() {
    if (closeOpenOverlays()) return;
    const sub = SUB_VIEWS.get(state.view);
    if (sub) {
      go(sub.parent);
      return;
    }
    if (state.view !== homeViewId()) go(homeViewId());
  }

  function bindTelegramBackButton() {
    if (!tg || !tg.BackButton || state.backBound) return;
    state.backBound = true;
    try {
      tg.BackButton.onClick(onTelegramBack);
    } catch (_) {
      try {
        tg.onEvent("backButtonClicked", onTelegramBack);
      } catch (__) {}
    }
  }

  /* ---------- bottom sheet ---------- */

  function openSheet(kind, title, bodyHtml, ctx) {
    state.sheetSeq += 1;
    state.sheet = { kind, ...(ctx || {}) };
    els.sheetTitle.textContent = title;
    els.sheetBody.innerHTML = bodyHtml;
    els.sheet.hidden = false;
    doc.body.classList.add("has-sheet");
    els.sheetClose.focus();
    syncTelegramBackButton();
    return state.sheetSeq;
  }

  /** Replace the sheet body only if the same sheet is still open. */
  function setSheetBody(seq, html) {
    if (seq !== state.sheetSeq || !state.sheet) return false;
    els.sheetBody.innerHTML = html;
    return true;
  }

  function closeSheet() {
    if (!state.sheet) return;
    state.sheet = null;
    state.sheetSeq += 1;
    state.renewPreview = null;
    state.topupCurrent = null;
    els.sheet.hidden = true;
    els.sheetBody.innerHTML = "";
    doc.body.classList.remove("has-sheet");
    syncTelegramBackButton();
  }

  /* ---------- views ---------- */

  function viewHead(title, subtitle, { subtitleLtr } = {}) {
    const sub = subtitle
      ? `<span class="muted sm"${subtitleLtr ? ' dir="ltr"' : ""}>${core.esc(subtitle)}</span>`
      : "";
    return `<header class="view-head"><div>${sub}<h1>${core.esc(title)}</h1></div></header>`;
  }

  function settled(r, rows, retry) {
    if (r.status === "loading") return R.loadingHtml(rows);
    if (r.status === "error") return R.errorHtml(r.error, retry);
    return null;
  }

  function greetingHtml() {
    const name = (state.me.user && state.me.user.name) || "";
    const roles = { admin: "ادمین", reseller: "نماینده", user: "مشتری" };
    return `<header class="view-head">
      <div><h1>${core.esc(name ? "سلام، " + name : "سلام")}</h1></div>
      <span class="role-chip">${core.esc(roles[persona()] || "مشتری")}</span>
    </header>`;
  }

  function myServicesHtml(home) {
    const recent = home.recent || [];
    if (!home.service_count) {
      return `<section class="card">${R.emptyHtml("هنوز سرویسی ندارید.", { view: "shop", label: "خرید اولین سرویس" })}</section>`;
    }
    return `<section class="card" aria-label="سرویس‌های من">
      <div class="card-head"><h2 class="card-title">سرویس‌های من <span class="muted sm">(${core.esc(core.num(home.service_count))})</span></h2>
        <button type="button" class="link-btn" data-action="goto" data-view="services">همه</button></div>
      ${recent.map(R.glanceRowHtml).join("")}
    </section>`;
  }

  function shopPeekHtml() {
    const r = resource("ops");
    const body = settled(r, 1, "retry")
      || R.statsHtml(r.data.stats, [["users", "کاربران"], ["orders", "سفارش‌ها"], ["pending", "رسید معلق"], ["tickets", "تیکت باز"]], { columns: 2 });
    return `<section class="card" aria-label="فروشگاه من">
      <div class="card-head"><h2 class="card-title">فروشگاه من</h2>
        <button type="button" class="link-btn" data-action="goto" data-view="ops">بیشتر</button></div>
      ${body}
    </section>`;
  }

  function customerHomeHtml() {
    const c = customer();
    const home = c.home || { service_count: 0, attention: [], recent: [] };
    return greetingHtml()
      + R.walletCardHtml(c, { actions: true })
      + (home.attention || []).map(R.attentionCardHtml).join("")
      + (persona() === "reseller" ? shopPeekHtml() : "")
      + myServicesHtml(home);
  }

  const ADMIN_STATS = [
    ["revenue", "درآمد", true], ["users", "کاربران"], ["resellers", "نمایندگان"],
    ["orders", "سفارش‌ها"], ["services", "سرویس‌ها"], ["tickets", "تیکت باز"],
  ];
  const RESELLER_STATS = [
    ["revenue", "درآمد", true], ["users", "کاربران"], ["orders", "سفارش‌ها"],
    ["services", "سرویس‌ها"], ["plans", "پلن‌ها"], ["tickets", "تیکت باز"],
  ];
  const ATTENTION = [
    ["pending", "رسیدهای در انتظار تأیید", "finance"],
    ["tickets", "تیکت‌های باز", "tickets"],
  ];

  function adminHomeHtml() {
    const r = resource("ops");
    const body = settled(r, 3, "retry");
    if (body) return greetingHtml() + body;
    const ops = r.data;
    return greetingHtml()
      + `<section class="card" aria-label="نیاز به اقدام"><h2 class="card-title">نیاز به اقدام</h2>${R.attentionListHtml(ops.stats, ops.panel_links, ATTENTION)}</section>`
      + `<section class="card" aria-label="نمای کلی"><h2 class="card-title">نمای کلی پلتفرم</h2>${R.statsHtml(ops.stats, ADMIN_STATS)}</section>`;
  }

  function resellerOpsHtml(ops) {
    const shop = ops.shop || {};
    const billing = shop.billing;
    return viewHead("فروشگاه من", shop.bot_username ? "@" + shop.bot_username : "", { subtitleLtr: true })
      + (billing ? `<section class="card wallet-card" aria-label="اعتبار فروشگاه">
          <div class="card-head"><span class="muted">اعتبار فروشگاه (پرداخت به‌ازای مصرف)</span>${billing.suspended ? '<span class="badge is-danger">مسدود</span>' : ""}</div>
          <p class="wallet-value">${core.esc(core.money(billing.balance))}</p>
        </section>` : "")
      + `<section class="card" aria-label="نیاز به اقدام"><div class="card-head"><h2 class="card-title">نیاز به اقدام</h2>${shop.active ? '<span class="badge is-ok">ربات فعال</span>' : '<span class="badge is-warn">ربات غیرفعال</span>'}</div>${R.attentionListHtml(ops.stats, ops.panel_links, ATTENTION)}</section>`
      + `<section class="card" aria-label="آمار فروشگاه"><h2 class="card-title">آمار فروشگاه</h2>${R.statsHtml(ops.stats, RESELLER_STATS)}</section>`
      + `<section class="card list-card" aria-label="میانبر پنل"><h2 class="card-title">میانبر پنل وب</h2>${R.linksHtml(ops.panel_links)}</section>`;
  }

  function opsViewHtml() {
    const r = resource("ops");
    const body = settled(r, 3, "retry");
    if (body) return viewHead(persona() === "admin" ? "میانبرها" : "فروشگاه من") + body;
    if (persona() === "reseller") return resellerOpsHtml(r.data);
    return viewHead("میانبرهای پنل وب")
      + `<section class="card list-card">${R.linksHtml(r.data.panel_links)}</section>`;
  }

  function servicesViewHtml() {
    const q = (state.services && state.services.q) || "";
    return viewHead("سرویس‌ها")
      + `<label class="search-field">${R.icon("search", 18)}<span class="visually-hidden">جست‌وجوی نام سرویس</span>
          <input type="search" data-input="service-search" maxlength="64" placeholder="جست‌وجوی نام سرویس" value="${core.esc(q)}" dir="auto"></label>
        <div id="svc-list">${serviceListHtml()}</div>`;
  }

  function serviceListHtml() {
    const s = state.services;
    if (!s || (s.status === "loading" && !s.items.length)) return R.loadingHtml(3);
    if (s.status === "error" && !s.items.length) return R.errorHtml(s.error, "retry");
    if (!s.items.length) {
      return s.q
        ? R.emptyHtml("سرویسی با این نام پیدا نشد.")
        : R.emptyHtml("هنوز سرویسی ندارید.", { view: "shop", label: "خرید سرویس" });
    }
    const more = s.next
      ? `<button type="button" class="btn ghost block" data-action="services-more"${s.status === "loading" ? " disabled" : ""}>${s.status === "loading" ? "در حال دریافت…" : "سرویس‌های بیشتر"}</button>`
      : "";
    const err = s.status === "error" ? R.errorHtml(s.error) : "";
    return `<div class="svc-list">${s.items.map(R.serviceRowHtml).join("")}</div>${err}${more}`;
  }

  async function loadServices(reset) {
    const prev = state.services;
    const q = prev ? prev.q : "";
    if (!reset && prev && (prev.status === "loading" || !prev.next)) return;
    const page = reset || !prev ? { items: [], next: null, q, status: "loading" } : prev;
    page.status = "loading";
    page.seq = (prev && prev.seq ? prev.seq : 0) + (reset ? 1 : 0);
    state.services = page;
    const seq = page.seq;
    renderServiceList();
    const params = new URLSearchParams();
    if (!reset && page.next) params.set("before_id", String(page.next));
    if (q) params.set("q", q);
    try {
      const data = await core.api("/api/mini/services" + (params.toString() ? "?" + params : ""));
      if (state.services !== page || page.seq !== seq) return;
      page.items = page.items.concat(data.items || []);
      page.next = data.next_before_id || null;
      page.status = "ready";
    } catch (err) {
      if (state.services !== page || page.seq !== seq) return;
      page.status = "error";
      page.error = err.message;
    }
    renderServiceList();
  }

  function renderServiceList() {
    if (state.view !== "services") return;
    const host = doc.getElementById("svc-list");
    if (host) host.innerHTML = serviceListHtml();
  }

  function serviceViewHtml() {
    const id = state.serviceId;
    const row = state.details.get(id);
    if (!row) {
      loadDetail(id);
      return R.loadingHtml(3);
    }
    if (row.status === "loading") return R.loadingHtml(3);
    if (row.status === "error") return viewHead("جزئیات سرویس") + R.errorHtml(row.error, "retry");
    return R.serviceDetailHtml(row.data, features());
  }

  async function loadDetail(id) {
    state.details.set(id, { status: "loading" });
    try {
      const data = await core.api("/api/mini/service/" + id);
      state.details.set(id, { status: "ready", data: data.service });
    } catch (err) {
      state.details.set(id, { status: "error", error: err.message });
    }
    if (state.view !== "service" || state.serviceId !== id) return;
    renderView();
    const then = state.then;
    state.then = null;
    const row = state.details.get(id);
    if (then === "renew" && row.status === "ready" && !row.data.is_cancelled && !row.data.cancellation_pending) {
      showRenew(id);
    }
  }

  function shopViewHtml() {
    const c = customer();
    const r = resource("plans");
    const body = settled(r, 3, "retry");
    const head = viewHead("خرید سرویس", "موجودی: " + core.money(c.wallet));
    if (body) return head + body;
    if (!r.data.wallet_pay_enabled) {
      return head + `<section class="card"><p class="muted">پرداخت با کیف پول در تنظیمات ربات غیرفعال است؛ خرید را از داخل ربات انجام دهید.</p></section>`;
    }
    const plans = r.data.plans || [];
    if (!plans.some((p) => p.id === state.selectedPlanId)) {
      const firstPaid = plans.find((p) => !p.is_trial) || plans[0];
      state.selectedPlanId = firstPaid ? firstPaid.id : null;
    }
    return head + R.planOptionsHtml(plans, state.selectedPlanId)
      + `<div id="checkout">${checkoutCardHtml()}</div>`;
  }

  function checkoutCardHtml() {
    const plan = selectedPlan();
    const wallet = customer().wallet;
    return state.checkout && plan && state.checkout.planId === plan.id
      ? R.discountedCheckoutHtml(state.checkout, plan, wallet)
      : R.checkoutHtml(plan, wallet);
  }

  function renderCheckout() {
    const host = doc.getElementById("checkout");
    if (host) host.innerHTML = checkoutCardHtml();
  }

  function selectedPlan() {
    const r = state.resources.plans;
    const plans = (r && r.status === "ready" && r.data.plans) || [];
    return plans.find((p) => p.id === state.selectedPlanId) || null;
  }

  function accountViewHtml() {
    const user = state.me.user || {};
    const r = resource("activity");
    const body = settled(r, 3, "retry");
    const rows = body || R.activityHtml(r.data.items);
    const canMore = !body && state.activityLimit < ACTIVITY_MORE && (r.data.items || []).length >= state.activityLimit;
    const topups = resource("topup");
    return viewHead(user.name || "حساب من", "حساب")
      + R.walletCardHtml(customer())
      + (topups.status === "ready" ? R.recentTopupsHtml(topups.data.recent) : "")
      + `<section class="card list-card" aria-label="پشتیبانی"><button type="button" class="list-row" data-action="goto" data-view="support">
          ${R.icon("chat")}<span class="list-row-label">پشتیبانی و تیکت‌ها</span>${R.icon("chevron", 16)}</button></section>`
      + `<section class="card" aria-label="تراکنش‌ها"><h2 class="card-title">تراکنش‌ها</h2>${rows}
          ${canMore ? '<button type="button" class="btn ghost block" data-action="activity-more">تراکنش‌های بیشتر</button>' : ""}</section>`;
  }

  function supportViewHtml() {
    const r = resource("support");
    return viewHead("پشتیبانی") + (settled(r, 3, "retry") || R.supportHtml(r.data));
  }

  function ticketViewHtml() {
    const id = state.ticketId;
    const row = state.tickets.get(id);
    if (!row) {
      loadTicket(id);
      return R.loadingHtml(3);
    }
    if (row.status === "loading") return R.loadingHtml(3);
    if (row.status === "error") return viewHead("تیکت") + R.errorHtml(row.error, "retry");
    return R.ticketThreadHtml(row.data);
  }

  async function loadTicket(id) {
    state.tickets.set(id, { status: "loading" });
    try {
      const data = await core.api("/api/mini/support/tickets/" + id);
      state.tickets.set(id, { status: "ready", data: data.ticket });
    } catch (err) {
      state.tickets.set(id, { status: "error", error: err.message });
    }
    if (state.view === "ticket" && state.ticketId === id) renderView();
  }

  const VIEW_RENDERERS = {
    home: () => (commerce() ? customerHomeHtml() : adminHomeHtml()),
    services: servicesViewHtml,
    service: serviceViewHtml,
    shop: shopViewHtml,
    account: accountViewHtml,
    ops: opsViewHtml,
    support: supportViewHtml,
    ticket: ticketViewHtml,
  };

  function renderView() {
    if (!state.me) return;
    const renderer = VIEW_RENDERERS[state.view] || VIEW_RENDERERS.home;
    els.root.innerHTML = `<div class="view" data-view="${core.esc(state.view)}">${renderer()}</div>`;
    if (state.view === "services" && !state.services) loadServices(true);
  }

  /* ---------- service actions ---------- */

  function detailRow(id) {
    const row = state.details.get(id);
    return row && row.status === "ready" ? row.data : null;
  }

  async function refreshService(id, trigger) {
    await guarded("refresh:" + id, trigger, async () => {
      try {
        const data = await core.api("/api/mini/service/" + id);
        state.details.set(id, { status: "ready", data: data.service });
        if (state.view === "service" && state.serviceId === id) renderView();
        if (data.service && data.service.error) core.toast(data.service.error_message || "دریافت اطلاعات سرویس ناموفق بود", "err");
        else core.toast("اطلاعات سرویس به‌روز شد");
      } catch (err) {
        core.toast(err.message, "err");
      }
    });
  }

  async function copyLink(id, trigger) {
    const row = detailRow(id);
    const ok = row && (await core.copyText(core.safeUrl(row.subscription_url)));
    if (ok) core.markCopied(trigger);
    else core.toast("کپی نشد", "err");
  }

  function openLink(id) {
    const row = detailRow(id);
    if (!row || !core.openExternal(row.subscription_url)) core.toast("لینک معتبر نیست", "err");
  }

  async function showQr(id) {
    const seq = openSheet("qr", "QR کد اشتراک", R.loadingHtml(1), { serviceId: id });
    try {
      const data = await core.api("/api/mini/service/" + id + "/qr");
      setSheetBody(seq, R.qrHtml(data.png_base64));
    } catch (err) {
      setSheetBody(seq, R.errorHtml(err.message));
    }
  }

  async function showRenew(id) {
    const seq = openSheet("renew", "تمدید سرویس", R.loadingHtml(2), { serviceId: id });
    const r = await ensure("plans");
    if (r.status !== "ready") {
      setSheetBody(seq, R.errorHtml(r.error || "دریافت پلن‌ها ناموفق بود"));
      return;
    }
    setSheetBody(seq, r.data.wallet_pay_enabled
      ? R.renewPlansHtml(r.data.plans, id)
      : R.emptyHtml("پرداخت با کیف پول غیرفعال است."));
  }

  async function previewRenew(id, planId) {
    const seq = state.sheetSeq;
    state.renewPreview = null;
    setSheetBody(seq, R.loadingHtml(2));
    try {
      const preview = await core.api(`/api/mini/service/${id}/renewal-preview?plan_id=${planId}`);
      if (seq !== state.sheetSeq) return;
      state.renewPreview = { serviceId: id, planId, terms: preview.terms, price: preview.price, requestKey: preview.request_key };
      setSheetBody(seq, R.renewPreviewHtml(preview, id, planId));
    } catch (err) {
      setSheetBody(seq, R.errorHtml(err.message) + `<button type="button" class="btn ghost block" data-action="renew" data-id="${id}">انتخاب پلن</button>`);
    }
  }

  async function confirmRenew(id, planId, trigger) {
    const preview = state.renewPreview;
    if (!preview || preview.serviceId !== id || preview.planId !== planId || !commerce()) return;
    await guarded("renew:" + id, trigger, async () => {
      try {
        const res = await core.api("/api/mini/renew", {
          method: "POST",
          body: { service_id: id, plan_id: planId, preview: { terms: preview.terms, price: preview.price, request_key: preview.requestKey } },
        });
        await afterPurchase(res.message || "تمدید انجام شد", { serviceId: id });
      } catch (err) {
        // Keep the preview: a retry re-sends its request key, which the server
        // applies at most once, so a lost response can never renew twice.
        core.toast(err.status === 0 ? RENEW_UNKNOWN_OUTCOME : err.message, "err");
      }
    });
  }

  async function showAddons(id, kind) {
    if (kind !== "volume" && kind !== "duration") return;
    const title = kind === "volume" ? "افزایش حجم" : "افزایش زمان";
    const seq = openSheet("addons", title, R.loadingHtml(2), { serviceId: id, kind });
    state.addonPacks = [];
    try {
      const data = await core.api(`/api/mini/service/${id}/addons?kind=${encodeURIComponent(kind)}`);
      if (seq !== state.sheetSeq) return;
      if (data.kind && data.kind !== kind) throw new Error("نوع بسته‌ها با بخش انتخاب‌شده مطابقت ندارد؛ دوباره تلاش کنید");
      state.addonPacks = (data.packs || []).filter((p) => p.kind === kind);
      setSheetBody(seq, R.addonPacksHtml(state.addonPacks, id));
    } catch (err) {
      setSheetBody(seq, R.errorHtml(err.message));
    }
  }

  async function buyAddon(id, packId, trigger) {
    const sheet = state.sheet;
    const pack = state.addonPacks.find((p) => p.id === packId);
    const svc = detailRow(id);
    if (!sheet || sheet.kind !== "addons" || sheet.serviceId !== id || !pack || !svc || pack.kind !== sheet.kind) return;
    if (!commerce() || !features().walletPay) {
      core.toast("پرداخت با کیف پول مجاز نیست", "err");
      return;
    }
    await guarded("addon:" + id, trigger, async () => {
      const label = pack.kind === "volume" ? "افزایش حجم" : "افزایش زمان";
      const ok = await core.confirmAction(`${label} سرویس «${svc.username}» با بستهٔ «${pack.name}» (+${pack.amount_label}) به مبلغ ${core.money(pack.price)} از کیف پول؟`);
      if (!ok) return;
      try {
        const res = await core.api("/api/mini/addon", {
          method: "POST", body: { service_id: id, pack_id: packId, kind: pack.kind, price: pack.price },
        });
        await afterPurchase(res.message || "بسته اضافه شد", { serviceId: id });
      } catch (err) {
        core.toast(err.status === 0 ? UNKNOWN_OUTCOME : err.message, "err");
        if (err.status === 0) await showFreshState({ serviceId: id });
      }
    });
  }

  async function showAutomation(id) {
    const seq = openSheet("automation", "تمدید خودکار", R.loadingHtml(2), { serviceId: id });
    try {
      const data = await core.api(`/api/mini/service/${id}/automation`);
      setSheetBody(seq, R.automationHtml(data, id));
    } catch (err) {
      setSheetBody(seq, R.errorHtml(err.message));
    }
  }

  async function saveAutomation(form) {
    const id = intAttr(form, "data-id");
    const button = form.querySelector("button[type=submit]");
    await guarded("automation:" + id, button, async () => {
      const enabled = !!form.elements.enabled.checked;
      const choiceId = Number(form.elements.choice_id.value) || null;
      if (enabled && !choiceId) {
        core.toast("پلن یا بسته را انتخاب کنید", "err");
        return;
      }
      try {
        await core.api(`/api/mini/service/${id}/automation`, {
          method: "POST", body: { action: form.getAttribute("data-auto-action"), enabled, choice_id: choiceId },
        });
        core.toast("تنظیمات ذخیره شد");
        if (state.sheet && state.sheet.kind === "automation") showAutomation(id);
      } catch (err) {
        core.toast(err.message, "err");
      }
    });
  }

  async function showCancellation(id) {
    const seq = openSheet("cancellation", "درخواست لغو", R.loadingHtml(2), { serviceId: id });
    try {
      const data = await core.api(`/api/mini/service/${id}/cancellation`);
      setSheetBody(seq, R.cancellationHtml(data.request, id));
    } catch (err) {
      setSheetBody(seq, R.errorHtml(err.message));
    }
  }

  async function submitCancellation(form) {
    const id = intAttr(form, "data-id");
    const button = form.querySelector("button[type=submit]");
    const reason = String(form.elements.reason.value || "").trim();
    if (!reason) return;
    await guarded("cancel:" + id, button, async () => {
      const ok = await core.confirmAction("درخواست لغو این سرویس ثبت شود؟ سرویس تا تأیید اپراتور فعال می‌ماند.");
      if (!ok) return;
      try {
        await core.api(`/api/mini/service/${id}/cancellation`, { method: "POST", body: { reason } });
        core.toast("درخواست ثبت شد");
        state.details.delete(id);
        showCancellation(id);
        if (state.view === "service" && state.serviceId === id) loadDetail(id);
      } catch (err) {
        core.toast(err.message, "err");
      }
    });
  }

  /* ---------- wallet top-up ---------- */

  const RECEIPT_MAX_SIDE = 1600;
  const RECEIPT_UNKNOWN_OUTCOME = "نتیجهٔ ارسال رسید مشخص نشد؛ «شارژهای اخیر» را بررسی کنید. هر پرداخت فقط یک رسید می‌پذیرد.";

  async function openTopup() {
    if (!commerce()) return;
    const seq = openSheet("topup", "شارژ کیف پول", R.loadingHtml(2));
    invalidate("topup");
    const r = await ensure("topup");
    if (r.status !== "ready") {
      setSheetBody(seq, R.errorHtml(r.error || "دریافت روش‌های شارژ ناموفق بود"));
      return;
    }
    setSheetBody(seq, R.topupFormHtml(r.data));
  }

  function topupAmount(form, options) {
    const preset = form.elements.preset ? String(form.elements.preset.value || "custom") : "custom";
    const amount = preset === "custom" ? core.parseAmount(form.elements.custom_amount.value) : Number(preset);
    if (!amount || amount < options.min_amount || amount > options.max_amount) return null;
    return amount;
  }

  async function startTopup(form) {
    const r = state.resources.topup;
    if (!r || r.status !== "ready") return;
    const button = form.querySelector("button[type=submit]");
    await guarded("topup-start", button, async () => {
      const amount = topupAmount(form, r.data);
      if (!amount) {
        core.toast(`مبلغ را بین ${core.money(r.data.min_amount)} و ${core.money(r.data.max_amount)} وارد کنید`, "err");
        return;
      }
      const method = String(form.elements.method.value || "");
      const dest = form.elements["dest_" + method];
      const seq = state.sheetSeq;
      try {
        const data = await core.api("/api/mini/topup", {
          method: "POST", body: { amount, method, ...(dest ? { dest_id: String(dest.value) } : {}) },
        });
        invalidate("topup");
        state.topupCurrent = data.topup;
        setSheetBody(seq, R.topupPayHtml(data.topup));
      } catch (err) {
        core.toast(err.message, "err");
      }
    });
  }

  function openReceiptSheet(paymentId) {
    state.topupCurrent = null;
    openSheet("receipt", "ارسال رسید", R.receiptFormHtml(paymentId));
  }

  /** Re-encode as a bounded JPEG: smaller upload, and the photo's location data is dropped. */
  async function prepareReceipt(file) {
    if (!file || !/^image\//.test(String(file.type || ""))) throw new Error("تصویر رسید را انتخاب کنید");
    try {
      const bitmap = await root.createImageBitmap(file);
      const scale = Math.min(1, RECEIPT_MAX_SIDE / Math.max(bitmap.width, bitmap.height));
      const canvas = doc.createElement("canvas");
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      if (bitmap.close) bitmap.close();
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
      if (blob) return blob;
    } catch (_) {
      // Fall back to the original file; the server checks type and size again.
    }
    if (file.type === "image/jpeg" || file.type === "image/png") return file;
    throw new Error("این نوع تصویر پشتیبانی نمی‌شود؛ عکس JPG یا PNG انتخاب کنید");
  }

  async function uploadReceipt(form) {
    const paymentId = intAttr(form, "data-id");
    const button = form.querySelector("button[type=submit]");
    const files = form.elements.receipt && form.elements.receipt.files;
    if (!paymentId || !files || !files.length) {
      core.toast("تصویر رسید را انتخاب کنید", "err");
      return;
    }
    await guarded("receipt:" + paymentId, button, async () => {
      let image;
      try {
        image = await prepareReceipt(files[0]);
      } catch (err) {
        core.toast(err.message, "err");
        return;
      }
      try {
        const res = await core.api(`/api/mini/topup/${paymentId}/receipt`, { method: "POST", raw: image });
        core.toast(res.message || "رسید ثبت شد");
        closeSheet();
      } catch (err) {
        core.toast(err.status === 0 ? RECEIPT_UNKNOWN_OUTCOME : err.message, "err");
        if (err.status !== 0) return;
      }
      invalidate("topup");
      await refreshAfterChange();
      renderView();
    });
  }

  function openTopupLink() {
    const t = state.topupCurrent;
    const url = t && (t.method === "psp" ? t.checkout_url : t.gateway_link);
    if (!core.openExternal(url)) core.toast("لینک پرداخت معتبر نیست", "err");
  }

  async function checkTopup(settlementId, trigger) {
    await guarded("topup-check", trigger, async () => {
      try {
        const res = await core.api("/api/mini/topup/check", { method: "POST", body: { settlement_id: settlementId } });
        core.toast(res.message);
        if (res.outcome === "settled" || res.outcome === "closed") {
          closeSheet();
          invalidate("topup");
          await refreshAfterChange();
          renderView();
        }
      } catch (err) {
        core.toast(err.message, "err");
      }
    });
  }

  async function copyValue(trigger) {
    const ok = await core.copyText(trigger.getAttribute("data-value"));
    if (ok) core.markCopied(trigger);
    else core.toast("کپی نشد", "err");
  }

  /* ---------- support ---------- */

  function textField(form, name) {
    const field = form.elements[name];
    return String((field && field.value) || "").trim();
  }

  async function submitNewTicket(form) {
    const subject = textField(form, "subject");
    const body = textField(form, "body");
    if (!subject || !body) {
      core.toast("موضوع و متن پیام را بنویسید", "err");
      return;
    }
    await guarded("ticket-new", form.querySelector("button[type=submit]"), async () => {
      try {
        const res = await core.api("/api/mini/support/tickets", { method: "POST", body: { subject, body } });
        core.toast(res.message || "تیکت ثبت شد");
        invalidate("support");
        go("ticket", { ticketId: res.ticket_id });
      } catch (err) {
        core.toast(err.status === 0 ? "نتیجه مشخص نشد؛ پیش از ارسال دوباره، فهرست تیکت‌ها را ببینید." : err.message, "err");
        if (err.status === 0) {
          closeSheet();
          invalidate("support");
          renderView();
        }
      }
    });
  }

  async function submitTicketReply(form) {
    const id = intAttr(form, "data-id");
    const body = textField(form, "body");
    if (!id || !body) {
      core.toast("متن پیام را بنویسید", "err");
      return;
    }
    await guarded("ticket-reply:" + id, form.querySelector("button[type=submit]"), async () => {
      try {
        await core.api(`/api/mini/support/tickets/${id}/messages`, { method: "POST", body: { body } });
        invalidate("support");
        await loadTicket(id);
      } catch (err) {
        core.toast(err.status === 0 ? "نتیجه مشخص نشد؛ گفتگو دوباره خوانده شد." : err.message, "err");
        if (err.status === 0) await loadTicket(id);
      }
    });
  }

  function openContact(index) {
    const r = state.resources.support;
    const contact = r && r.status === "ready" ? (r.data.contacts || [])[index] : null;
    if (!contact || !core.openTelegramLink(contact.url)) core.toast("لینک پشتیبان معتبر نیست", "err");
  }

  /* ---------- purchases ---------- */

  async function buyPlan(planId, trigger) {
    const plan = selectedPlan();
    if (!plan || plan.id !== planId || !commerce()) return;
    await guarded("buy", trigger, async () => {
      const ok = await core.confirmAction(`خرید «${plan.name}» به مبلغ ${core.money(plan.price)} از کیف پول؟`);
      if (!ok) return;
      try {
        const res = await core.api("/api/mini/buy", { method: "POST", body: { plan_id: planId, price: plan.price } });
        await afterPurchase(res.message || "خرید انجام شد", { view: "services" });
      } catch (err) {
        core.toast(err.status === 0 ? UNKNOWN_OUTCOME : err.message, "err");
        if (err.status === 0) await showFreshState({ view: "services" });
      }
    });
  }

  /* ---------- discount and gift codes ---------- */

  const PAY_UNKNOWN_OUTCOME = "نتیجهٔ پرداخت مشخص نشد. دوباره «پرداخت» را بزنید؛ مبلغ فقط یک بار کسر می‌شود.";

  async function applyDiscount(form) {
    const plan = selectedPlan();
    const code = textField(form, "code");
    if (!plan || !commerce()) return;
    if (!code) {
      core.toast("کد تخفیف را بنویسید", "err");
      return;
    }
    await guarded("discount", form.querySelector("button[type=submit]"), async () => {
      try {
        const res = await core.api("/api/mini/checkout", { method: "POST", body: { plan_id: plan.id, price: plan.price, code } });
        state.checkout = { ...res.checkout, planId: plan.id };
        core.haptic("ok");
        renderCheckout();
      } catch (err) {
        core.toast(err.message, "err");
      }
    });
  }

  /** Release an unpaid discounted order (best effort; stale ones are also cleaned up on the server). */
  function dropCheckout() {
    const checkout = state.checkout;
    state.checkout = null;
    if (!checkout) return;
    core.api(`/api/mini/checkout/${checkout.order_id}/cancel`, { method: "POST", body: {} }).catch(() => {});
  }

  async function payCheckout(trigger) {
    const checkout = state.checkout;
    if (!checkout || !commerce()) return;
    await guarded("checkout-pay", trigger, async () => {
      const ok = await core.confirmAction(`پرداخت ${core.money(checkout.amount)} از کیف پول با کد «${checkout.code}»؟`);
      if (!ok) return;
      try {
        const res = await core.api(`/api/mini/checkout/${checkout.order_id}/pay`, { method: "POST", body: {} });
        state.checkout = null;
        await afterPurchase(res.message || "خرید انجام شد", { view: "services" });
      } catch (err) {
        // Paying the same order again is safe: the server never debits it twice.
        core.toast(err.status === 0 ? PAY_UNKNOWN_OUTCOME : err.message, "err");
      }
    });
  }

  async function cancelCheckout(trigger) {
    const checkout = state.checkout;
    if (!checkout) return;
    await guarded("checkout-cancel", trigger, async () => {
      try {
        await core.api(`/api/mini/checkout/${checkout.order_id}/cancel`, { method: "POST", body: {} });
      } catch (err) {
        if (err.status !== 0) core.toast(err.message, "err");
      }
      state.checkout = null;
      renderCheckout();
    });
  }

  async function redeemGift(form) {
    const code = textField(form, "code");
    if (!code) {
      core.toast("کد هدیه را بنویسید", "err");
      return;
    }
    await guarded("gift", form.querySelector("button[type=submit]"), async () => {
      try {
        const res = await core.api("/api/mini/wallet/redeem", { method: "POST", body: { code } });
        core.toast(`${res.message || "کیف پول شارژ شد"}: ${core.money(res.amount)}`);
        closeSheet();
      } catch (err) {
        core.toast(err.status === 0 ? "نتیجه مشخص نشد؛ موجودی دوباره خوانده شد." : err.message, "err");
        if (err.status !== 0) return;
      }
      await refreshAfterChange();
      renderView();
    });
  }

  async function refreshAfterChange() {
    invalidateCommerce();
    try {
      await reloadMe();
    } catch (err) {
      core.toast(err.message, "err");
    }
  }

  async function afterPurchase(message, target) {
    core.toast(message);
    await showFreshState(target);
  }

  /** After a purchase, or a lost response that may have charged the wallet: never auto-retry. */
  async function showFreshState(target) {
    await refreshAfterChange();
    if (target.serviceId) go("service", { serviceId: target.serviceId });
    else go(target.view);
  }

  /* ---------- event wiring ---------- */

  function openPanelPath(path) {
    const p = core.safePanelPath(path);
    if (!p) return;
    const ops = state.resources.ops;
    const base = (ops && ops.status === "ready" && ops.data.panel_base) || state.me.panel_base || "";
    core.openExternal(String(base).replace(/\/+$/, "") + p);
  }

  function retryCurrentView() {
    if (state.view === "services") {
      state.services = null;
    } else if (state.view === "service") {
      state.details.delete(state.serviceId);
    } else if (state.view === "ticket") {
      state.tickets.delete(state.ticketId);
    } else {
      for (const name of Object.keys(state.resources)) {
        if (state.resources[name].status === "error") invalidate(name);
      }
    }
    renderView();
  }

  const ACTIONS = {
    goto: (el) => go(el.getAttribute("data-view")),
    "open-service": (el) => go("service", { serviceId: intAttr(el, "data-id"), then: el.getAttribute("data-then") }),
    "refresh-service": (el) => refreshService(intAttr(el, "data-id"), el),
    "copy-link": (el) => copyLink(intAttr(el, "data-id"), el),
    "open-link": (el) => openLink(intAttr(el, "data-id")),
    "show-qr": (el) => showQr(intAttr(el, "data-id")),
    renew: (el) => showRenew(intAttr(el, "data-id")),
    "preview-renew": (el) => previewRenew(intAttr(el, "data-id"), intAttr(el, "data-plan")),
    "confirm-renew": (el) => confirmRenew(intAttr(el, "data-id"), intAttr(el, "data-plan"), el),
    addons: (el) => showAddons(intAttr(el, "data-id"), el.getAttribute("data-kind")),
    "buy-addon": (el) => buyAddon(intAttr(el, "data-id"), intAttr(el, "data-pack"), el),
    automation: (el) => showAutomation(intAttr(el, "data-id")),
    cancellation: (el) => showCancellation(intAttr(el, "data-id")),
    buy: (el) => buyPlan(intAttr(el, "data-id"), el),
    "open-panel": (el) => openPanelPath(el.getAttribute("data-path")),
    "services-more": () => loadServices(false),
    "activity-more": () => {
      state.activityLimit = ACTIVITY_MORE;
      invalidate("activity");
      renderView();
    },
    "close-sheet": () => closeSheet(),
    topup: () => openTopup(),
    "topup-receipt": (el) => openReceiptSheet(intAttr(el, "data-id")),
    "open-topup-link": () => openTopupLink(),
    "check-topup": (el) => checkTopup(intAttr(el, "data-id"), el),
    "copy-value": (el) => copyValue(el),
    "checkout-pay": (el) => payCheckout(el),
    "checkout-cancel": (el) => cancelCheckout(el),
    "gift-code": () => openSheet("gift", "کد هدیه", R.giftFormHtml()),
    "ticket-new": () => openSheet("ticket-new", "تیکت جدید", R.ticketNewFormHtml()),
    "open-ticket": (el) => go("ticket", { ticketId: intAttr(el, "data-id") }),
    "refresh-ticket": (el) => loadTicket(intAttr(el, "data-id")),
    "open-contact": (el) => openContact(Number(el.getAttribute("data-index"))),
    retry: () => retryCurrentView(),
  };

  function onClick(event) {
    const el = event.target.closest("[data-action]");
    if (!el || el.disabled) return;
    const name = el.getAttribute("data-action");
    if (!Object.prototype.hasOwnProperty.call(ACTIONS, name) || el.matches("input[data-action=select-plan]")) return;
    const action = ACTIONS[name];
    event.preventDefault();
    action(el, event);
  }

  function onChange(event) {
    const el = event.target;
    if (el.matches && el.matches("[data-input=receipt-file]")) {
      const label = el.closest(".file-field").querySelector(".file-field-label");
      const file = el.files && el.files[0];
      // textContent: the file name is user data.
      if (label) label.textContent = file ? "تصویر انتخاب‌شده: " + file.name : "انتخاب تصویر رسید";
      return;
    }
    if (!el.matches || !el.matches("input[data-action=select-plan]")) return;
    state.selectedPlanId = intAttr(el, "data-id");
    core.haptic("select");
    doc.querySelectorAll(".plan-option").forEach((label) => {
      label.classList.toggle("is-selected", label.contains(el));
    });
    dropCheckout();
    renderCheckout();
  }

  const FORMS = { automation: saveAutomation, cancellation: submitCancellation, topup: startTopup, receipt: uploadReceipt,
    "ticket-new": submitNewTicket, "ticket-reply": submitTicketReply, discount: applyDiscount, gift: redeemGift };

  function formHandler(form) {
    const kind = form.getAttribute && form.getAttribute("data-form");
    return Object.prototype.hasOwnProperty.call(FORMS, kind) ? FORMS[kind] : null;
  }

  function submitForm(form) {
    const handler = formHandler(form);
    return handler ? handler(form) : null;
  }

  function onSubmit(event) {
    const form = event.target;
    if (!formHandler(form)) return;
    event.preventDefault();
    submitForm(form);
  }

  function onInput(event) {
    const el = event.target;
    if (!el.matches || !el.matches("[data-input=service-search]")) return;
    root.clearTimeout(state.searchTimer);
    state.searchTimer = root.setTimeout(() => {
      const q = String(el.value || "").trim().slice(0, 64);
      if (state.services && state.services.q === q) return;
      state.services = { items: [], next: null, q, status: "loading", seq: (state.services && state.services.seq) || 0 };
      loadServices(true);
    }, SEARCH_DEBOUNCE_MS);
  }

  function bindEvents() {
    doc.addEventListener("click", onClick);
    doc.addEventListener("change", onChange);
    doc.addEventListener("submit", onSubmit);
    doc.addEventListener("input", onInput);
    els.sheet.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeSheet();
    });
    root.addEventListener("hashchange", () => {
      if (!state.me) return;
      const route = hashRoute();
      if (route.view !== state.view || (route.serviceId || null) !== state.serviceId
        || (route.ticketId || null) !== state.ticketId) go(route.view, route);
    });
  }

  /* ---------- boot ---------- */

  function sleep(ms) {
    return new Promise((resolve) => root.setTimeout(resolve, ms));
  }

  async function waitForInitData(maxAttempts) {
    for (let i = 0; i < maxAttempts; i++) {
      if (core.getInitData()) return true;
      await sleep(40 * (i + 1));
    }
    return !!core.getInitData();
  }

  function bootErrorText(err) {
    if (!core.getInitData()) {
      return "مینی‌اپ را از دکمهٔ «Open» کنار چت یا دکمهٔ داخل ربات باز کنید.";
    }
    if (err && err.status === 404) return "برای استفاده، ابتدا ربات را /start کنید.";
    return (err && err.message) || "بارگذاری مینی‌اپ ناموفق بود.";
  }

  function showBootError(err) {
    els.nav.innerHTML = "";
    els.root.innerHTML = R.errorHtml(bootErrorText(err), "reload");
  }

  async function boot() {
    els.root.innerHTML = R.loadingHtml(3);
    try {
      await waitForInitData(6);
      if (!core.getInitData()) throw new core.ApiError("no initData", 401);
      applyMe(await core.api("/api/mini/me"));
      const route = hashRoute();
      go(route.view, route);
    } catch (err) {
      showBootError(err);
    }
    syncTelegramBackButton();
  }

  ACTIONS.reload = () => boot();

  function start() {
    els.root = doc.getElementById("root");
    els.nav = doc.getElementById("nav");
    els.sheet = doc.getElementById("sheet");
    els.sheetTitle = doc.getElementById("sheet-title");
    els.sheetBody = doc.getElementById("sheet-body");
    els.sheetClose = doc.getElementById("sheet-close");
    core.initTelegram();
    bindTelegramBackButton();
    bindEvents();
    boot();
  }

  root.PGMini.app = Object.freeze({ start, state, go, ACTIONS, submitForm, closeSheet, syncTelegramBackButton });
  if (root.PGMini.autostart !== false) start();
})(typeof window === "object" ? window : globalThis);
