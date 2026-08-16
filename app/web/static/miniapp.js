/* Telegram Mini App client — role shells matching web panel IA */
(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#09090b");
      tg.setBackgroundColor("#09090b");
    } catch (_) {}
  }

  const initData = (tg && tg.initData) || "";
  const root = document.getElementById("root");
  const navEl = document.getElementById("nav");
  const helloEl = document.getElementById("hello");
  const subEl = document.getElementById("subtitle");
  const roleEl = document.getElementById("role-badge");

  let state = null;
  let currency = "تومان";
  let activeView = "home";

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function safeUrl(u) {
    const s = String(u || "").trim();
    if (!s) return "";
    const low = s.toLowerCase();
    if (
      low.startsWith("javascript:") ||
      low.startsWith("data:") ||
      low.startsWith("vbscript:")
    ) {
      return "";
    }
    return s;
  }

  function money(n) {
    return (Number(n) || 0).toLocaleString("fa-IR") + " " + currency;
  }

  function num(n) {
    return (Number(n) || 0).toLocaleString("fa-IR");
  }

  async function api(path) {
    const res = await fetch(path, {
      headers: { "X-Telegram-Init-Data": initData },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  function personaLabel(p) {
    if (p === "admin") return "ادمین";
    if (p === "reseller") return "نماینده";
    return "کاربر";
  }

  function hashView() {
    const h = (location.hash || "").replace(/^#/, "").trim();
    return h || "home";
  }

  function setView(id) {
    activeView = id || "home";
    if (location.hash.replace(/^#/, "") !== activeView) {
      history.replaceState(null, "", "#" + activeView);
    }
    document.querySelectorAll(".panel").forEach((el) => {
      el.classList.toggle("active", el.dataset.view === activeView);
    });
    document.querySelectorAll(".ma-nav button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === activeView);
    });
  }

  function openPanelPath(path) {
    const base = (state && state.panel_base) || "";
    const url = safeUrl(base + path);
    if (!url) return;
    if (tg && tg.openLink) tg.openLink(url);
    else window.open(url, "_blank");
  }

  function renderNav(nav) {
    navEl.innerHTML = "";
    (nav || []).forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.view = item.id;
      btn.textContent = item.label;
      btn.addEventListener("click", () => setView(item.id));
      navEl.appendChild(btn);
    });
  }

  function statsHtml(stats, keys) {
    return (
      '<div class="stat-grid">' +
      keys
        .map(
          ([k, label]) =>
            `<div class="stat"><span>${esc(label)}</span><strong>${esc(
              num(stats[k])
            )}</strong></div>`
        )
        .join("") +
      "</div>"
    );
  }

  function linksHtml(links) {
    if (!links || !links.length) {
      return '<p class="hint">برای لینک مستقیم به وب‌پنل، HTTPS و آدرس عمومی را در تنظیمات فعال کنید.</p>';
    }
    return links
      .map(
        (l) =>
          `<div class="link-row row"><div><strong>${esc(l.label)}</strong></div>
          <button type="button" class="btn ghost sm" data-path="${esc(
            l.path
          )}">باز کردن</button></div>`
      )
      .join("");
  }

  function customerServices(customer) {
    const list = (customer && customer.services) || [];
    if (!list.length) return '<p class="muted">سرویسی ندارید</p>';
    return list
      .map((s) => {
        const url = esc(s.subscription_url || "");
        return `<div class="svc-row row">
          <div class="svc-meta"><strong>${esc(s.username || "—")}</strong><code>${url}</code></div>
          <button type="button" class="btn secondary sm" data-svc="${Number(s.id) || 0}">جزئیات</button>
        </div>`;
      })
      .join("");
  }

  function customerPlans(customer) {
    const list = (customer && customer.plans) || [];
    if (!list.length) return '<p class="muted">پلنی فعال نیست</p>';
    return list
      .map(
        (p) =>
          `<div class="plan-row row">
            <div class="plan-meta">
              <strong>${esc(p.name)}</strong>
              <div class="muted">${esc(p.days)} روز · ${esc(p.gb ?? "∞")} گیگ</div>
            </div>
            <div class="price">${esc(money(p.price))}</div>
          </div>`
      )
      .join("");
  }

  function renderUser(data) {
    const c = data.customer || {};
    return {
      home: `
        <div class="card wallet-card">
          <p class="wallet-label">موجودی کیف پول</p>
          <p class="wallet-value">${esc(money(c.wallet))}</p>
          <p class="hint">خرید و تمدید از دکمه‌های ربات انجام می‌شود؛ اینجا وضعیت سریع است.</p>
        </div>
        <div class="card">
          <h3>خلاصه</h3>
          <div class="stat-grid">
            <div class="stat"><span>سرویس‌ها</span><strong>${esc(num((c.services || []).length))}</strong></div>
            <div class="stat"><span>پلن‌های فعال</span><strong>${esc(num((c.plans || []).length))}</strong></div>
          </div>
        </div>`,
      services: `
        <div class="card"><h3>سرویس‌های من</h3>${customerServices(c)}
          <div id="detail" class="card card-soft" style="display:none;margin-top:var(--space-2)"></div>
        </div>`,
      shop: `
        <div class="card"><h3>خرید پلن</h3>${customerPlans(c)}
          <p class="hint">برای تکمیل خرید به ربات برگردید.</p>
        </div>`,
    };
  }

  function renderReseller(data) {
    const ops = data.ops || {};
    const stats = ops.stats || {};
    const shop = ops.shop || {};
    const billing = shop.billing;
    let billingHtml = "";
    if (billing) {
      billingHtml = `<div class="card wallet-card">
        <p class="wallet-label">کیف پول فروشگاهی (PAYG)</p>
        <p class="wallet-value">${esc(money(billing.balance))}</p>
        ${
          billing.suspended
            ? '<div class="flash-err">حساب به‌خاطر موجودی صفر مسدود است</div>'
            : ""
        }
      </div>`;
    }
    return {
      home: `
        ${billingHtml}
        <div class="card">
          <h3>فروشگاه من</h3>
          ${statsHtml(stats, [
            ["users", "کاربران"],
            ["orders", "سفارش‌ها"],
            ["pending", "رسید معلق"],
            ["tickets", "تیکت باز"],
            ["services", "سرویس‌ها"],
            ["revenue", "درآمد"],
          ])}
          ${
            shop.bot_username
              ? `<p class="hint" dir="ltr">@${esc(shop.bot_username)}</p>`
              : '<p class="hint">ربات اختصاصی هنوز تنظیم نشده — از وب‌پنل تکمیل کنید.</p>'
          }
        </div>`,
      shop: `
        <div class="card">
          <h3>دسترسی سریع وب‌پنل</h3>
          ${linksHtml(ops.panel_links)}
        </div>
        <div class="card">
          <h3>پلن‌های فروشگاه</h3>
          <div class="stat"><span>پلن فعال</span><strong>${esc(num(stats.plans))}</strong></div>
          <p class="hint">مدیریت کامل پلن‌ها در وب‌پنل است.</p>
        </div>`,
      support: `
        <div class="card">
          <h3>پشتیبانی فروشگاه</h3>
          <div class="stat-grid">
            <div class="stat"><span>تیکت باز</span><strong>${esc(num(stats.tickets))}</strong></div>
            <div class="stat"><span>رسید معلق</span><strong>${esc(num(stats.pending))}</strong></div>
          </div>
          <button type="button" class="btn block" style="margin-top:var(--space-2)" data-path="/tickets">رفتن به تیکت‌ها در وب</button>
        </div>`,
    };
  }

  function renderAdmin(data) {
    const ops = data.ops || {};
    const stats = ops.stats || {};
    return {
      home: `
        <div class="card">
          <h3>نمای کلی پلتفرم</h3>
          ${statsHtml(stats, [
            ["users", "کاربران"],
            ["resellers", "نمایندگان"],
            ["orders", "سفارش‌ها"],
            ["pending", "رسید معلق"],
            ["tickets", "تیکت باز"],
            ["revenue", "درآمد"],
          ])}
        </div>`,
      ops: `
        <div class="card">
          <h3>عملیات سریع</h3>
          ${linksHtml(ops.panel_links)}
          <p class="hint">صفحات وب‌پنل نیاز به لاگین دارند؛ اگر قبلاً وارد شده‌اید مستقیم باز می‌شوند.</p>
        </div>
        <div class="card">
          <h3>وضعیت</h3>
          <div class="stat-grid">
            <div class="stat"><span>سرویس‌ها</span><strong>${esc(num(stats.services))}</strong></div>
            <div class="stat"><span>رسید معلق</span><strong>${esc(num(stats.pending))}</strong></div>
          </div>
        </div>`,
      support: `
        <div class="card">
          <h3>پشتیبانی</h3>
          <div class="stat"><span>تیکت باز</span><strong>${esc(num(stats.tickets))}</strong></div>
          <button type="button" class="btn block" style="margin-top:var(--space-2)" data-path="/tickets">باز کردن تیکت‌ها</button>
          <button type="button" class="btn secondary block" style="margin-top:var(--space-1)" data-path="/resellers">بخش نمایندگان</button>
        </div>`,
    };
  }

  function mount(data) {
    currency = data.currency || "تومان";
    state = data;
    const name = (data.user && data.user.name) || "";
    helloEl.textContent = name ? "سلام " + name : "مینی‌اپ";
    roleEl.textContent = personaLabel(data.persona);
    subEl.textContent =
      data.persona === "admin"
        ? "پنل سریع ادمین — آمار و میانبر وب"
        : data.persona === "reseller"
          ? "پنل سریع نماینده — فروشگاه و پشتیبانی"
          : "کیف پول، سرویس‌ها و پلن‌ها";

    renderNav(data.nav);

    let panels;
    if (data.persona === "admin") panels = renderAdmin(data);
    else if (data.persona === "reseller") panels = renderReseller(data);
    else panels = renderUser(data);

    root.innerHTML = Object.keys(panels)
      .map(
        (id) =>
          `<section class="panel" data-view="${esc(id)}">${panels[id]}</section>`
      )
      .join("");

    root.querySelectorAll("[data-path]").forEach((btn) => {
      btn.addEventListener("click", () => openPanelPath(btn.getAttribute("data-path")));
    });
    root.querySelectorAll("[data-svc]").forEach((btn) => {
      btn.addEventListener("click", () => showSvc(Number(btn.getAttribute("data-svc"))));
    });

    const wanted = hashView();
    const ok = (data.nav || []).some((n) => n.id === wanted);
    setView(ok ? wanted : (data.nav[0] && data.nav[0].id) || "home");
  }

  async function showSvc(id) {
    const box = document.getElementById("detail");
    if (!box) return;
    box.style.display = "block";
    box.textContent = "در حال دریافت…";
    try {
      const data = await api("/api/mini/service/" + id);
      const i = data.info || {};
      const url = safeUrl(data.service.url || "");
      box.textContent = "";
      const h3 = document.createElement("h3");
      h3.textContent = data.service.username || "";
      const muted = document.createElement("div");
      muted.className = "muted";
      muted.textContent =
        "وضعیت: " +
        (i.status || "—") +
        " · مصرف: " +
        (i.used_traffic ?? "—") +
        " / " +
        (i.data_limit ?? "∞");
      const p = document.createElement("p");
      const code = document.createElement("code");
      code.textContent = url;
      p.appendChild(code);
      box.appendChild(h3);
      box.appendChild(muted);
      box.appendChild(p);
      if (url) {
        const btn = document.createElement("button");
        btn.className = "btn block";
        btn.type = "button";
        btn.textContent = "باز کردن لینک";
        btn.addEventListener("click", () => {
          if (tg && tg.openLink) tg.openLink(url);
        });
        box.appendChild(btn);
      }
    } catch (e) {
      box.textContent = "";
      const err = document.createElement("div");
      err.className = "error";
      err.textContent = String(e.message || e);
      box.appendChild(err);
    }
  }

  async function load() {
    root.innerHTML =
      '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
    try {
      const data = await api("/api/mini/me");
      mount(data);
    } catch (e) {
      root.textContent = "";
      const err = document.createElement("div");
      err.className = "error";
      err.appendChild(
        document.createTextNode("برای استفاده ابتدا ربات را /start کنید.")
      );
      err.appendChild(document.createElement("br"));
      err.appendChild(document.createTextNode(String(e.message || e)));
      root.appendChild(err);
      navEl.innerHTML = "";
    }
  }

  window.addEventListener("hashchange", () => {
    if (!state) return;
    const wanted = hashView();
    const ok = (state.nav || []).some((n) => n.id === wanted);
    if (ok) setView(wanted);
  });

  load();
})();
