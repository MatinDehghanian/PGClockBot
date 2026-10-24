/* Mini App views as escaped HTML strings. Pure functions: no DOM, no network. */
(function (root) {
  "use strict";

  const core = root.PGMini.core;
  const { esc, num, money, faDigits } = core;

  const STROKE = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';
  const ICON_PATHS = {
    home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    svc: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    shop: '<path d="M5 8h14l-1 12H6z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
    account: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    store: '<path d="M4 10v10h16V10"/><path d="M3 10 5 4h14l2 6z"/>',
    ops: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M3 12h2M19 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.5 4.5L20 16"/><path d="M20 20v-4h-4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    timer: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M9 2h6"/>',
    auto: '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8"/><path d="M4 4v4h4"/><path d="M12 8v4l2 2"/>',
    cancel: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    chevron: '<path d="m15 6-6 6 6 6"/>',
    // RTL: "back" points right.
    back: '<path d="m9 6 6 6-6 6"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    chat: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
  };

  function icon(name, size) {
    const s = Number(size) || 20;
    return `<svg aria-hidden="true" focusable="false" width="${s}" height="${s}" viewBox="0 0 24 24" ${STROKE}>${ICON_PATHS[name] || ICON_PATHS.home}</svg>`;
  }

  function isOnHoldStatus(status) {
    const s = String(status || "").toLowerCase().replace(/-/g, "_");
    return s === "on_hold" || s === "onhold";
  }

  function statusTone(status) {
    const s = String(status || "").toLowerCase();
    if (s === "active") return "ok";
    if (s === "limited" || s === "disabled" || isOnHoldStatus(s)) return "warn";
    if (s === "expired") return "danger";
    return "";
  }

  function badge(text, tone) {
    return `<span class="badge${tone ? " is-" + esc(tone) : ""}">${esc(text)}</span>`;
  }

  function meterTone(pct) {
    if (pct >= 90) return "danger";
    if (pct >= 75) return "warn";
    return "";
  }

  function meterHtml(pct) {
    if (pct == null || !Number.isFinite(Number(pct))) return "";
    const value = Math.max(0, Math.min(100, Math.round(Number(pct))));
    return `<div class="meter${meterTone(value) ? " is-" + meterTone(value) : ""}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${value}" aria-label="درصد مصرف حجم"><i style="width:${value}%"></i></div>`;
  }

  /** Remaining-time label — never map on_hold + null days to «نامحدود». */
  function expireDaysLabel(s) {
    if (s && s.expire_days_label) return faDigits(s.expire_days_label);
    if (s && s.expire_days != null) return num(s.expire_days) + " روز";
    if (s && (s.pending_start || isOnHoldStatus(s.status))) return "پس از اتصال";
    if (!s || s.error || !s.status || s.status === "—") return "—";
    return "نامحدود";
  }

  function serviceStatusBadge(s) {
    if (s.is_cancelled) return badge("لغوشده", "danger");
    if (s.cancellation_pending) return badge("در انتظار لغو", "warn");
    return badge(s.status_fa || s.status || "—", statusTone(s.status));
  }

  function serviceErrorHtml(s) {
    if (!s.error) return "";
    return `<p class="inline-error" role="status">${esc(s.error_message || "دریافت اطلاعات سرویس ناموفق بود؛ دوباره تلاش کنید.")}</p>`;
  }

  function serviceRowHtml(s) {
    const id = Number(s.id) || 0;
    return `<button type="button" class="svc-row" data-action="open-service" data-id="${id}">
      <span class="svc-row-head"><strong dir="ltr">${esc(s.username || "—")}</strong>${serviceStatusBadge(s)}</span>
      ${meterHtml(s.traffic_pct)}
      <span class="svc-row-meta"><span>${esc(faDigits(s.traffic || "—"))}</span><span>${esc(expireDaysLabel(s))}</span></span>
      ${serviceErrorHtml(s)}
    </button>`;
  }

  function glanceRowHtml(g) {
    const id = Number(g.id) || 0;
    return `<button type="button" class="svc-row" data-action="open-service" data-id="${id}">
      <span class="svc-row-head"><strong dir="ltr">${esc(g.username || "—")}</strong>${serviceStatusBadge(g)}</span>
      <span class="svc-row-meta"><span>${esc(faDigits(g.remaining_label || "—"))}</span>${icon("chevron", 16)}</span>
    </button>`;
  }

  function attentionCardHtml(g) {
    const id = Number(g.id) || 0;
    const ended = ["expired", "limited"].includes(String(g.status || "").toLowerCase());
    const title = ended ? "سرویس به پایان رسیده" : "سرویس رو به پایان است";
    return `<div class="notice is-warn">
      ${icon("clock", 22)}
      <div class="notice-body"><strong>${esc(title)}: <span dir="ltr">${esc(g.username || "—")}</span></strong>
        <span>${esc(faDigits(g.remaining_label || ""))}</span></div>
      <button type="button" class="btn sm is-warn" data-action="open-service" data-id="${id}" data-then="renew">تمدید</button>
    </div>`;
  }

  /** Expiry in the Persian calendar; the server's label only for cases without a date (on hold). */
  function expireDateText(s) {
    return core.formatDate(s.expire_at) || faDigits(s.expire || "—");
  }

  function serviceUsageHtml(s) {
    const fetched = s.info_fetched_at ? core.formatDateTime(s.info_fetched_at) : "";
    return `<section class="card" aria-label="مصرف سرویس">
      <div class="card-head">${serviceStatusBadge(s)}${fetched ? `<span class="muted sm">به‌روز: ${esc(fetched)}</span>` : ""}</div>
      <p class="usage-line"><strong>${esc(faDigits(s.traffic || "—"))}</strong></p>
      ${meterHtml(s.traffic_pct)}
      <div class="tile-grid">
        <div class="tile"><span>زمان باقی‌مانده</span><strong>${esc(expireDaysLabel(s))}</strong></div>
        <div class="tile"><span>انقضا</span><strong>${esc(expireDateText(s))}</strong></div>
        <div class="tile"><span>آخرین اتصال</span><strong>${esc(core.formatDateTime(s.online_at) || "—")}</strong></div>
      </div>
      ${serviceErrorHtml(s)}
    </section>`;
  }

  /** Host only: the full link is a credential and must not sit on screen (screenshots). */
  function maskedUrl(url) {
    try {
      return new URL(url).host + "/•••";
    } catch (_) {
      return "•••";
    }
  }

  function serviceLinkHtml(s, features) {
    const id = Number(s.id) || 0;
    const url = core.safeUrl(s.subscription_url);
    if (!url) return "";
    return `<section class="card" aria-label="لینک اشتراک">
      <h2 class="card-title">لینک اشتراک</h2>
      <div class="link-box" dir="ltr">${esc(maskedUrl(url))}</div>
      <div class="btn-row">
        <button type="button" class="btn" data-action="copy-link" data-id="${id}">کپی لینک</button>
        ${features.qr ? `<button type="button" class="btn ghost" data-action="show-qr" data-id="${id}">QR کد</button>` : ""}
        <button type="button" class="btn ghost" data-action="open-link" data-id="${id}">باز کردن</button>
      </div>
    </section>`;
  }

  function actionRow(action, id, iconName, label, extra) {
    return `<button type="button" class="list-row${extra && extra.danger ? " is-danger" : ""}" data-action="${esc(action)}" data-id="${id}"${extra && extra.kind ? ` data-kind="${esc(extra.kind)}"` : ""}>
      ${icon(iconName)}<span class="list-row-label">${esc(label)}</span>${icon("chevron", 16)}
    </button>`;
  }

  function serviceActionsHtml(s, features) {
    const id = Number(s.id) || 0;
    const open = !s.is_cancelled && !s.cancellation_pending;
    const rows = [];
    if (open && features.walletPay) rows.push(actionRow("renew", id, "refresh", "تمدید سرویس"));
    if (open && features.walletPay && s.addons_allowed) {
      rows.push(actionRow("addons", id, "plus", "افزایش حجم", { kind: "volume" }));
      rows.push(actionRow("addons", id, "timer", "افزایش زمان", { kind: "duration" }));
    }
    if (open) rows.push(actionRow("automation", id, "auto", "تمدید خودکار"));
    rows.push(actionRow("cancellation", id, "cancel", s.is_cancelled || s.cancellation_pending ? "وضعیت درخواست لغو" : "درخواست لغو سرویس", { danger: true }));
    return `<section class="card list-card" aria-label="عملیات سرویس">${rows.join("")}</section>`;
  }

  function serviceDetailHtml(s, features) {
    const id = Number(s.id) || 0;
    return `<header class="view-head">
        <div><span class="muted sm">جزئیات سرویس</span><h1 dir="ltr">${esc(s.username || "—")}</h1></div>
        <button type="button" class="icon-btn" data-action="refresh-service" data-id="${id}" aria-label="به‌روزرسانی اطلاعات از پنل">${icon("refresh")}</button>
      </header>
      ${serviceUsageHtml(s)}
      ${serviceLinkHtml(s, features)}
      ${serviceActionsHtml(s, features)}`;
  }

  function priceHtml(quote) {
    return root.PGClockCatalogPrice.renderPrice(quote, money, esc);
  }

  function planMetaText(p) {
    const days = p.days ? `${num(p.days)} روز` : "نامحدود";
    const gb = p.gb == null || p.gb === "" ? "حجم نامحدود" : `${num(p.gb)} گیگ`;
    return `${days} · ${gb}`;
  }

  function planOptionsHtml(plans, selectedId) {
    if (!plans || !plans.length) return emptyHtml("پلنی برای خرید فعال نیست.");
    return `<div class="plan-list" role="radiogroup" aria-label="پلن‌ها">${plans.map((p) => {
      const id = Number(p.id) || 0;
      const checked = id === Number(selectedId);
      return `<label class="plan-option${checked ? " is-selected" : ""}">
        <input type="radio" name="plan" value="${id}" data-action="select-plan" data-id="${id}"${checked ? " checked" : ""}>
        <span class="plan-meta"><strong>${esc(p.name)}</strong>${p.is_trial ? badge("تست", "ok") : ""}<span class="muted sm">${esc(planMetaText(p))}</span></span>
        <span class="plan-price">${priceHtml(p)}</span>
      </label>`;
    }).join("")}</div>`;
  }

  const LOW_BALANCE = `<p class="inline-error">موجودی کیف پول کافی نیست.</p>
      <button type="button" class="btn ghost block" data-action="topup">شارژ کیف پول</button>`;

  function checkoutHtml(plan, wallet) {
    if (!plan) return `<section class="card"><p class="muted">یک پلن را انتخاب کنید.</p></section>`;
    const price = Number(plan.price) || 0;
    const enough = price <= (Number(wallet) || 0);
    return `<section class="card" aria-label="خلاصهٔ سفارش">
      <div class="sum-row"><span class="muted">پلن</span><span>${esc(plan.name)}</span></div>
      <div class="sum-row"><span class="muted">موجودی کیف پول</span><span>${esc(money(wallet))}</span></div>
      <div class="sum-row is-total"><span>قابل پرداخت</span><span>${priceHtml(plan)}</span></div>
      ${plan.is_trial ? "" : `<form class="code-form" data-form="discount">
        <label class="form-field"><span class="muted sm">کد تخفیف (اختیاری)</span>
          <span class="code-line"><input type="text" name="code" maxlength="64" autocomplete="off" dir="ltr" autocapitalize="characters">
          <button type="submit" class="btn ghost">اعمال</button></span></label>
      </form>`}
      ${enough ? "" : LOW_BALANCE}
      <button type="button" class="btn block" data-action="buy" data-id="${Number(plan.id) || 0}"${enough ? "" : " disabled"}>${plan.is_trial ? "دریافت سرویس تست" : "پرداخت از کیف پول"}</button>
    </section>`;
  }

  function discountedCheckoutHtml(checkout, plan, wallet) {
    const enough = Number(checkout.amount) <= (Number(wallet) || 0);
    return `<section class="card" aria-label="خلاصهٔ سفارش با تخفیف">
      <div class="sum-row"><span class="muted">پلن</span><span>${esc(plan ? plan.name : "")}</span></div>
      <div class="sum-row"><span class="muted">قیمت</span><s>${esc(money(checkout.original_amount))}</s></div>
      <div class="sum-row"><span class="muted">تخفیف <bdi dir="ltr">${esc(checkout.code)}</bdi></span><span class="is-plus tx-amt"><span aria-hidden="true">−</span><bdi>${esc(money(checkout.discount))}</bdi></span></div>
      <div class="sum-row is-total"><span>قابل پرداخت</span><span>${esc(money(checkout.amount))}</span></div>
      ${enough ? "" : LOW_BALANCE}
      <div class="btn-col">
        <button type="button" class="btn block" data-action="checkout-pay"${enough ? "" : " disabled"}>پرداخت از کیف پول</button>
        <button type="button" class="btn ghost block" data-action="checkout-cancel">حذف کد و انصراف</button>
      </div>
    </section>`;
  }

  function giftFormHtml() {
    return `<form class="code-form" data-form="gift">
      <label class="form-field"><span>کد هدیه</span>
        <input type="text" name="code" maxlength="64" autocomplete="off" dir="ltr" autocapitalize="characters"></label>
      <button type="submit" class="btn block">ثبت کد و شارژ کیف پول</button>
    </form>`;
  }

  function renewPlansHtml(plans, serviceId) {
    const list = (plans || []).filter((p) => !p.is_trial);
    if (!list.length) return emptyHtml("پلنی برای تمدید فعال نیست.");
    return `<p class="muted sm">پلن تمدید را انتخاب کنید؛ پیش از پرداخت، نتیجه را می‌بینید.</p>
      <div class="plan-list">${list.map((p) => `<button type="button" class="plan-option" data-action="preview-renew" data-id="${Number(serviceId) || 0}" data-plan="${Number(p.id) || 0}">
        <span class="plan-meta"><strong>${esc(p.name)}</strong><span class="muted sm">${esc(planMetaText(p))}</span></span>
        <span class="plan-price">${priceHtml(p)}</span>
      </button>`).join("")}</div>`;
  }

  function renewPreviewHtml(preview, serviceId, planId) {
    const sid = Number(serviceId) || 0;
    const pid = Number(planId) || 0;
    return `<div class="sum-row"><span class="muted">پلن</span><strong>${esc(preview.plan_name)}</strong></div>
      <div class="sum-row is-total"><span>مبلغ</span><span>${priceHtml(preview)}</span></div>
      ${(preview.lines || []).map((line) => `<p class="sm">${esc(line)}</p>`).join("")}
      ${(preview.warnings || []).map((line) => `<p class="inline-error">${esc(line)}</p>`).join("")}
      ${preview.notice ? `<p class="muted sm">${esc(preview.notice)}</p>` : ""}
      <div class="btn-col">
        <button type="button" class="btn block" data-action="confirm-renew" data-id="${sid}" data-plan="${pid}">تأیید و پرداخت از کیف پول</button>
        <button type="button" class="btn ghost block" data-action="renew" data-id="${sid}">انتخاب پلن دیگر</button>
      </div>`;
  }

  function addonPacksHtml(packs, serviceId) {
    if (!packs || !packs.length) return emptyHtml("بسته‌ای برای خرید فعال نیست.");
    const sid = Number(serviceId) || 0;
    return `<p class="muted sm">بسته پس از پرداخت به همین سرویس اضافه می‌شود.</p>
      <div class="plan-list">${packs.map((p) => `<button type="button" class="plan-option" data-action="buy-addon" data-id="${sid}" data-pack="${Number(p.id) || 0}">
        <span class="plan-meta"><strong>${esc(p.name)}</strong><span class="muted sm">+${esc(p.amount_label)}</span>${p.description ? `<span class="muted sm">${esc(p.description)}</span>` : ""}</span>
        <span class="plan-price">${priceHtml(p)}</span>
      </button>`).join("")}</div>`;
  }

  function automationHtml(data, serviceId) {
    const sid = Number(serviceId) || 0;
    const actions = (data && data.actions) || [];
    return `<p class="muted sm">با روشن کردن هر گزینه، خرید تکرارشونده با قیمت فعلی از کیف پول انجام می‌شود. بستهٔ زمان یا حجم برای مورد تمام‌شده اولویت دارد؛ در غیر این صورت تمدید کامل انجام می‌شود.</p>
      ${data && data.needs_review ? `<p class="inline-error">سفارش #${num(data.pending_order_id)} نیاز به بررسی پشتیبانی دارد؛ اجرای خودکار متوقف است.</p>` : ""}
      ${actions.map((a, index) => `<form class="auto-form" data-form="automation" data-id="${sid}" data-auto-action="${esc(a.action)}">
        <label class="check-row"><input type="checkbox" name="enabled"${a.enabled ? " checked" : ""}><span>${esc(a.label)}</span></label>
        <label class="form-field"><span class="visually-hidden">انتخاب پلن یا بسته برای ${esc(a.label)}</span>
          <select name="choice_id" id="auto-choice-${index}">
            <option value="">انتخاب پلن یا بسته</option>
            ${(a.choices || []).map((c) => `<option value="${Number(c.id) || 0}"${Number(c.id) === Number(a.choice_id) ? " selected" : ""}>${esc(c.name)} — ${esc(money(c.price))}</option>`).join("")}
          </select></label>
        ${a.unavailable ? '<p class="inline-error">گزینهٔ قبلی حذف یا غیرفعال شده؛ پلن یا بستهٔ جدید انتخاب کنید.</p>' : ""}
        <button type="submit" class="btn sm">ذخیره</button>
      </form>`).join("")}`;
  }

  function cancellationHtml(row, serviceId) {
    const sid = Number(serviceId) || 0;
    const canRequest = !row || ["rejected", "withdrawn"].includes(row.status);
    return `<p class="muted sm">مبلغ برگشتی را اپراتور تعیین می‌کند و پس از تأیید غیرفعال‌شدن سرویس به کیف پول برمی‌گردد. ثبت درخواست، سرویس را غیرفعال نمی‌کند.</p>
      ${row ? `<div class="card inset"><strong>${esc(row.label)}</strong>
        ${row.refund_amount == null ? "" : `<p class="sm">اعتبار برگشتی: ${esc(money(row.refund_amount))}</p>`}
        ${row.operator_note ? `<p class="sm pre-line">${esc(row.operator_note)}</p>` : ""}</div>` : ""}
      ${canRequest ? `<form data-form="cancellation" data-id="${sid}">
        <label class="form-field"><span>دلیل لغو</span><textarea name="reason" rows="3" maxlength="1000" required></textarea></label>
        <button type="submit" class="btn block is-danger">ثبت درخواست لغو</button>
      </form>` : ""}`;
  }

  function qrHtml(pngBase64) {
    const data = String(pngBase64 || "");
    if (!/^[A-Za-z0-9+/]+=*$/.test(data)) return errorHtml("ساخت QR ناموفق بود.");
    return `<div class="qr-frame"><img alt="QR کد لینک اشتراک" src="data:image/png;base64,${data}"></div>
      <p class="muted sm center">برای افزودن اشتراک، این کد را در برنامهٔ اتصال اسکن کنید.</p>`;
  }

  function activityHtml(rows) {
    if (!rows || !rows.length) return emptyHtml("هنوز تراکنشی ندارید.");
    return rows.map((a) => {
      const amount = Number(a.amount) || 0;
      const sign = amount > 0 ? "+" : amount < 0 ? "−" : "";
      const kind = amount < 0 ? "برداشت" : "واریز";
      return `<div class="tx-row">
        <span class="tx-meta"><span>${esc(a.reason || "—")}</span><span class="muted sm">${esc(core.formatDateTime(a.created_at))}</span></span>
        <span class="tx-amt${amount >= 0 ? " is-plus" : " is-minus"}"><span class="visually-hidden">${kind}</span><span aria-hidden="true">${sign}</span><bdi>${esc(money(Math.abs(amount)))}</bdi></span>
      </div>`;
    }).join("");
  }

  function walletCardHtml(customer, { actions } = {}) {
    const c = customer || {};
    return `<section class="card wallet-card" aria-label="کیف پول">
      <div class="card-head"><span class="muted">موجودی کیف پول</span>${badge(c.wallet_pay_enabled ? "پرداخت فعال" : "فقط مشاهده", c.wallet_pay_enabled ? "ok" : "")}</div>
      <p class="wallet-value">${esc(money(c.wallet))}</p>
      <div class="btn-row">
        <button type="button" class="btn" data-action="topup">شارژ کیف پول</button>
        ${actions
          ? '<button type="button" class="btn ghost" data-action="goto" data-view="shop">خرید سرویس</button>'
          : '<button type="button" class="btn ghost" data-action="gift-code">کد هدیه</button>'}
      </div>
    </section>`;
  }

  const TOPUP_STATUS_TONES = { approved: "ok", rejected: "danger" };

  function topupFormHtml(options) {
    const methods = (options && options.methods) || [];
    if (!methods.length) {
      return emptyHtml(options && options.bot_only
        ? "شارژ کیف پول فعلاً فقط از داخل ربات ممکن است."
        : "روش شارژی فعال نیست.");
    }
    const presets = options.presets || [];
    return `<form class="topup-form" data-form="topup">
      <fieldset class="field-group"><legend>مبلغ شارژ</legend>
        <div class="chip-grid">${presets.map((n, i) => `<label class="chip"><input type="radio" name="preset" value="${Number(n) || 0}"${i === 0 ? " checked" : ""}><span>${esc(money(n))}</span></label>`).join("")}
          <label class="chip"><input type="radio" name="preset" value="custom"${presets.length ? "" : " checked"}><span>مبلغ دلخواه</span></label>
        </div>
        <label class="form-field"><span class="muted sm">مبلغ دلخواه (${esc(money(options.min_amount))} تا ${esc(money(options.max_amount))})</span>
          <input type="text" name="custom_amount" inputmode="numeric" autocomplete="off" dir="ltr" maxlength="16"></label>
      </fieldset>
      <fieldset class="field-group"><legend>روش پرداخت</legend>
        ${methods.map((m, i) => `<label class="method-option">
          <input type="radio" name="method" value="${esc(m.key)}"${i === 0 ? " checked" : ""}>
          <span class="plan-meta"><strong>${esc(m.label)}</strong>${m.needs_receipt ? '<span class="muted sm">پس از واریز، تصویر رسید را بفرستید</span>' : '<span class="muted sm">پرداخت آنلاین و تأیید خودکار</span>'}</span>
          ${(m.choices || []).length ? `<select name="dest_${esc(m.key)}" aria-label="مقصد ${esc(m.label)}">${m.choices.map((c) => `<option value="${esc(c.id)}">${esc(c.label)}</option>`).join("")}</select>` : ""}
        </label>`).join("")}
      </fieldset>
      ${options.bot_only ? '<p class="muted sm">روش «بزن به کارت» فقط از داخل ربات در دسترس است.</p>' : ""}
      <button type="submit" class="btn block">ادامه</button>
    </form>`;
  }

  function copyRow(label, value) {
    return `<div class="copy-row"><span class="muted sm">${esc(label)}</span>
      <div class="copy-line"><strong dir="ltr">${esc(value)}</strong>
      <button type="button" class="btn ghost sm" data-action="copy-value" data-value="${esc(value)}">کپی</button></div></div>`;
  }

  function receiptFormHtml(paymentId) {
    const id = Number(paymentId) || 0;
    return `<form class="receipt-form" data-form="receipt" data-id="${id}">
      <label class="file-field"><span class="file-field-label">انتخاب تصویر رسید</span>
        <span class="muted sm">عکس JPG یا PNG، حداکثر ۸ مگابایت</span>
        <input type="file" name="receipt" class="visually-hidden" accept="image/jpeg,image/png,image/*" data-input="receipt-file"></label>
      <button type="submit" class="btn block">ارسال رسید</button>
      <p class="muted sm">تصویر رسید برای شما در ربات هم فرستاده می‌شود. می‌توانید رسید را مستقیم در ربات هم بفرستید.</p>
    </form>`;
  }

  function topupPayHtml(t) {
    const rows = [`<div class="sum-row is-total"><span>مبلغ</span><span>${esc(money(t.amount))}</span></div>`];
    if (t.method === "card") {
      rows.push(copyRow("شمارهٔ کارت", t.card_number || ""));
      if (t.card_holder) rows.push(`<p class="sm">به نام ${esc(t.card_holder)}</p>`);
    } else if (t.method === "gateway") {
      rows.push(`<p class="sm">پرداخت از طریق ${esc(t.gateway_name || "درگاه")}</p>`);
      if (t.gateway_link) rows.push(`<button type="button" class="btn block ghost" data-action="open-topup-link">ورود به ${esc(t.gateway_name || "درگاه")}</button>`);
    } else if (t.method === "crypto") {
      rows.push(`<p class="sm">${esc(t.crypto_asset || "")}${t.crypto_network ? " · شبکهٔ " + esc(t.crypto_network) : ""}</p>`);
      rows.push(copyRow("آدرس کیف پول", t.crypto_address || ""));
    } else if (t.method === "psp") {
      rows.push(t.checkout_url
        ? '<button type="button" class="btn block" data-action="open-topup-link">ورود به درگاه پرداخت</button>'
        : errorHtml("لینک درگاه آماده نشد؛ دوباره تلاش کنید."));
      if (t.settlement_id) rows.push(`<button type="button" class="btn block ghost" data-action="check-topup" data-id="${Number(t.settlement_id) || 0}">بررسی پرداخت</button>`);
      rows.push('<p class="muted sm">پس از پرداخت، کیف پول خودکار شارژ می‌شود؛ اگر برنگشتید «بررسی پرداخت» را بزنید.</p>');
    }
    if (t.note) rows.push(`<p class="muted sm pre-line">${esc(t.note)}</p>`);
    rows.push(`<p class="muted sm">شمارهٔ پرداخت: ${esc(num(t.payment_id))}</p>`);
    if (t.needs_receipt) rows.push(receiptFormHtml(t.payment_id));
    return rows.join("");
  }

  function recentTopupsHtml(rows) {
    if (!rows || !rows.length) return "";
    return `<section class="card list-card" aria-label="شارژهای اخیر"><h2 class="card-title">شارژهای اخیر</h2>
      ${rows.map((r) => `<div class="list-row">
        <span class="list-row-label">${esc(money(r.amount))}<span class="muted sm"> · ${esc(core.formatDateTime(r.created_at))}</span></span>
        ${r.waiting_receipt
          ? `<button type="button" class="btn sm" data-action="topup-receipt" data-id="${Number(r.id) || 0}">ارسال رسید</button>`
          : badge(r.status_fa, TOPUP_STATUS_TONES[r.status] || "warn")}
      </div>`).join("")}
    </section>`;
  }

  const TICKET_TONES = { open: "warn", answered: "ok", closed: "" };

  function supportHtml(data) {
    const contacts = (data && data.contacts) || [];
    const tickets = (data && data.tickets) || [];
    return `<section class="card" aria-label="پشتیبانی">
        <p class="pre-line">${esc(data.text || "")}</p>
        <button type="button" class="btn block" data-action="ticket-new">تیکت جدید</button>
        ${contacts.length ? `<div class="btn-col">${contacts.map((c, i) => `<button type="button" class="btn ghost block" data-action="open-contact" data-index="${i}">گفتگو با ${esc(c.title)}</button>`).join("")}</div>` : ""}
      </section>
      <section class="card list-card" aria-label="تیکت‌های من"><h2 class="card-title">تیکت‌های من</h2>
        ${tickets.length ? tickets.map((t) => `<button type="button" class="list-row" data-action="open-ticket" data-id="${Number(t.id) || 0}">
          <span class="list-row-label"><span>${esc(t.subject)}</span><span class="muted sm"> · #${esc(num(t.id))}</span></span>
          ${badge(t.status_fa, TICKET_TONES[t.status] || "")}
        </button>`).join("") : '<p class="muted sm">هنوز تیکتی ندارید.</p>'}
      </section>`;
  }

  function ticketNewFormHtml() {
    return `<form class="ticket-form" data-form="ticket-new">
      <label class="form-field"><span>موضوع</span><input type="text" name="subject" maxlength="120" autocomplete="off"></label>
      <label class="form-field"><span>متن پیام</span><textarea name="body" rows="5" maxlength="2000"></textarea></label>
      <button type="submit" class="btn block">ثبت تیکت</button>
    </form>`;
  }

  function ticketThreadHtml(t) {
    const id = Number(t.id) || 0;
    return `<header class="view-head">
        <div><span class="muted sm">تیکت #${esc(num(id))}</span><h1>${esc(t.subject)}</h1></div>
        <button type="button" class="icon-btn" data-action="refresh-ticket" data-id="${id}" aria-label="به‌روزرسانی گفتگو">${icon("refresh")}</button>
      </header>
      <div class="card-head">${badge(t.status_fa, TICKET_TONES[t.status] || "")}</div>
      <ol class="thread" aria-label="پیام‌ها">${(t.messages || []).map((m) => `<li class="bubble${m.from_staff ? " is-staff" : " is-mine"}">
        <span class="bubble-who muted sm">${m.from_staff ? "پشتیبانی" : "شما"} · ${esc(core.formatDateTime(m.created_at))}</span>
        <p class="pre-line">${esc(m.body)}</p></li>`).join("")}</ol>
      ${t.is_closed
        ? '<p class="muted sm center">این تیکت بسته شده است؛ برای ادامه، تیکت تازه بسازید.</p>'
        : `<form class="ticket-form" data-form="ticket-reply" data-id="${id}">
          <label class="form-field"><span class="visually-hidden">پاسخ شما</span><textarea name="body" rows="3" maxlength="2000" placeholder="پاسخ خود را بنویسید"></textarea></label>
          <button type="submit" class="btn block">ارسال</button>
        </form>`}`;
  }

  function statsHtml(stats, keys, { columns } = {}) {
    const s = stats || {};
    return `<div class="tile-grid${columns === 2 ? " cols-2" : ""}">${keys.map(([key, label, isMoney]) =>
      `<div class="tile${isMoney ? " is-wide" : ""}"><span>${esc(label)}</span><strong>${esc(isMoney ? money(s[key]) : num(s[key]))}</strong></div>`
    ).join("")}</div>`;
  }

  /** Counts that need someone to act, each opening its panel page when one exists. */
  function attentionListHtml(stats, links, items) {
    const byId = new Map((links || []).map((l) => [l.id, l]));
    const rows = items
      .filter(([key]) => Number((stats || {})[key]) > 0)
      .map(([key, label, linkId]) => {
        const link = byId.get(linkId);
        const count = `<span class="count">${esc(num(stats[key]))}</span>`;
        return link
          ? `<button type="button" class="list-row" data-action="open-panel" data-path="${esc(link.path)}"><span class="list-row-label">${esc(label)}</span>${count}</button>`
          : `<div class="list-row"><span class="list-row-label">${esc(label)}</span>${count}</div>`;
      });
    if (!rows.length) return '<p class="muted sm">کار معوقی نیست.</p>';
    return rows.join("");
  }

  function linksHtml(links) {
    if (!links || !links.length) return '<p class="muted sm">آدرس پنل در دسترس نیست.</p>';
    return links.map((l) => `<button type="button" class="list-row" data-action="open-panel" data-path="${esc(l.path)}">
      <span class="list-row-label">${esc(l.label)}</span>${icon("chevron", 16)}</button>`).join("");
  }

  function navHtml(nav, active) {
    return (nav || []).map((item) => {
      const current = item.id === active;
      return `<button type="button" class="nav-btn${current ? " is-active" : ""}" data-action="goto" data-view="${esc(item.id)}"${current ? ' aria-current="page"' : ""}>${icon(item.icon, 22)}<span>${esc(item.label)}</span></button>`;
    }).join("");
  }

  /** Visible way back for screens below a tab (Telegram's own Back button is easy to miss). */
  function backBarHtml(label) {
    return `<button type="button" class="back-link" data-action="back">${icon("back", 18)}<span>بازگشت به ${esc(label)}</span></button>`;
  }

  function loadingHtml(rows) {
    return `<div class="loading" aria-busy="true" aria-label="در حال بارگذاری">${'<div class="skeleton"></div>'.repeat(Number(rows) || 3)}</div>`;
  }

  function emptyHtml(message, cta) {
    return `<div class="empty"><p>${esc(message)}</p>${cta ? `<button type="button" class="btn" data-action="goto" data-view="${esc(cta.view)}">${esc(cta.label)}</button>` : ""}</div>`;
  }

  function errorHtml(message, retry) {
    return `<div class="error-box" role="alert"><p>${esc(message)}</p>${retry ? `<button type="button" class="btn ghost sm" data-action="${esc(retry)}">تلاش دوباره</button>` : ""}</div>`;
  }

  root.PGMini.render = Object.freeze({
    icon, isOnHoldStatus, statusTone, expireDaysLabel, meterHtml, serviceRowHtml, glanceRowHtml,
    attentionCardHtml, serviceDetailHtml, planOptionsHtml, checkoutHtml, discountedCheckoutHtml, giftFormHtml, renewPlansHtml,
    renewPreviewHtml, addonPacksHtml, automationHtml, cancellationHtml, qrHtml, activityHtml,
    backBarHtml, walletCardHtml, supportHtml, ticketNewFormHtml, ticketThreadHtml, topupFormHtml, topupPayHtml, receiptFormHtml, recentTopupsHtml, statsHtml, attentionListHtml, linksHtml, navHtml, loadingHtml, emptyHtml,
    errorHtml,
  });
})(typeof window === "object" ? window : globalThis);
