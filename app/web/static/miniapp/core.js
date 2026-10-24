/* Mini App core: Telegram WebApp bridge, API client, escaping and formatting. */
(function (root) {
  "use strict";

  const tg = (root.Telegram && root.Telegram.WebApp) || null;
  const settings = { currency: "تومان" };

  /** Live read — some clients inject initData slightly after first paint. */
  function getInitData() {
    const w = root.Telegram && root.Telegram.WebApp;
    return (w && w.initData) || "";
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  /** Only absolute http(s) links may be opened; everything else is dropped. */
  function safeUrl(value) {
    const s = String(value || "").trim();
    return /^https?:\/\/[^\s]+$/i.test(s) ? s : "";
  }

  /** Same-origin relative panel path, never protocol-relative or absolute. */
  function safePanelPath(path) {
    const p = String(path || "");
    if (!p.startsWith("/") || p.startsWith("//") || p.includes("://") || p.includes("\\")) return "";
    return p;
  }

  function num(value) {
    return (Number(value) || 0).toLocaleString("fa-IR");
  }

  function money(value) {
    return num(value).replace(/٬/g, ",") + " " + settings.currency;
  }

  /** Persian/Arabic digits to ASCII, separators and spaces removed; "" when not a whole number. */
  function parseAmount(value) {
    const ascii = String(value || "")
      .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
      .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
      .replace(/[,٬،\s]/g, "");
    return /^\d{1,12}$/.test(ascii) ? Number(ascii) : null;
  }

  function setCurrency(value) {
    settings.currency = String(value || "تومان");
  }

  function formatDateTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (!Number.isFinite(d.getTime())) return "";
    try {
      return new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" }).format(d);
    } catch (_) {
      return d.toLocaleString("fa-IR");
    }
  }

  function haptic(kind) {
    if (!tg || !tg.HapticFeedback) return;
    try {
      if (kind === "select") tg.HapticFeedback.selectionChanged();
      else tg.HapticFeedback.notificationOccurred(kind === "err" ? "error" : "success");
    } catch (_) {}
  }

  function toast(message, kind) {
    const doc = root.document;
    if (!doc || !doc.body) return;
    const el = doc.createElement("div");
    el.className = "toast" + (kind === "err" ? " is-error" : "");
    el.setAttribute("role", kind === "err" ? "alert" : "status");
    el.textContent = String(message || "");
    doc.body.appendChild(el);
    root.setTimeout(() => el.remove(), 3200);
    haptic(kind === "err" ? "err" : "ok");
  }

  function confirmAction(message) {
    if (tg && typeof tg.showConfirm === "function") {
      return new Promise((resolve) => {
        try {
          tg.showConfirm(String(message), (ok) => resolve(!!ok));
        } catch (_) {
          resolve(!!(root.confirm && root.confirm(String(message))));
        }
      });
    }
    return Promise.resolve(!!(root.confirm && root.confirm(String(message))));
  }

  function openExternal(url) {
    const safe = safeUrl(url);
    if (!safe) return false;
    if (tg && typeof tg.openLink === "function") tg.openLink(safe);
    else root.open(safe, "_blank", "noopener");
    return true;
  }

  /** t.me links open inside Telegram; anything else goes through openExternal. */
  function openTelegramLink(url) {
    const safe = safeUrl(url);
    if (tg && typeof tg.openTelegramLink === "function" && /^https:\/\/t\.me\//i.test(safe)) {
      tg.openTelegramLink(safe);
      return true;
    }
    return openExternal(safe);
  }

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }

  const FALLBACK_ERROR = "ارتباط با سرور برقرار نشد؛ دوباره تلاش کنید.";

  const STATUS_ERRORS = {
    401: "نشست مینی‌اپ منقضی شده؛ مینی‌اپ را ببندید و دوباره باز کنید.",
    403: "این کار برای حساب شما مجاز نیست.",
    404: "مورد درخواستی پیدا نشد.",
    422: "ورودی نامعتبر است.",
  };

  /** Short Persian server text is shown as is; internal (ASCII) details never are. */
  function errorText(data, status) {
    const raw = data && (data.detail || data.message);
    const detail = typeof raw === "string" ? raw.trim() : "";
    if (detail && detail.length <= 200 && !/^[\x00-\x7F]*$/.test(detail)) return detail;
    return STATUS_ERRORS[status] || FALLBACK_ERROR;
  }

  /** ``opts.body`` is sent as JSON; ``opts.raw`` (a Blob) is sent as is, e.g. an image. */
  async function api(path, opts) {
    const options = opts || {};
    const hasBody = options.body !== undefined;
    const raw = options.raw;
    const contentType = raw ? raw.type || "application/octet-stream" : hasBody ? "application/json" : null;
    let res;
    try {
      res = await root.fetch(path, {
        method: options.method || "GET",
        headers: {
          "X-Telegram-Init-Data": getInitData(),
          ...(contentType ? { "Content-Type": contentType } : {}),
        },
        body: raw || (hasBody ? JSON.stringify(options.body) : undefined),
        cache: "no-store",
        credentials: "same-origin",
      });
    } catch (_) {
      throw new ApiError(FALLBACK_ERROR, 0);
    }
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (_) {
      data = null;
    }
    if (!res.ok) throw new ApiError(errorText(data, res.status), res.status);
    return data;
  }

  async function copyText(text) {
    const s = String(text || "");
    if (!s) return false;
    try {
      if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
        await root.navigator.clipboard.writeText(s);
        return true;
      }
    } catch (_) {}
    const doc = root.document;
    try {
      const ta = doc.createElement("textarea");
      ta.value = s;
      ta.setAttribute("readonly", "");
      ta.className = "visually-hidden";
      doc.body.appendChild(ta);
      ta.select();
      const ok = doc.execCommand("copy");
      ta.remove();
      return !!ok;
    } catch (_) {
      return false;
    }
  }

  /** Flash «کپی شد» on the button, then restore its own label. */
  function markCopied(btn) {
    if (!btn) return;
    if (!btn.dataset.copyIdle) btn.dataset.copyIdle = (btn.textContent || "").trim() || "کپی لینک";
    btn.textContent = "کپی شد";
    btn.classList.add("is-copied");
    if (btn._copyTimer) root.clearTimeout(btn._copyTimer);
    btn._copyTimer = root.setTimeout(() => {
      btn.textContent = btn.dataset.copyIdle;
      btn.classList.remove("is-copied");
    }, 1400);
  }

  /** Follow the Telegram light/dark theme; CSS reads Telegram's --tg-theme-* variables. */
  function applyTheme() {
    const doc = root.document;
    if (!doc || !doc.documentElement) return;
    const scheme = tg && tg.colorScheme === "light" ? "light" : "dark";
    doc.documentElement.setAttribute("data-theme", scheme);
    if (!tg) return;
    try {
      tg.setHeaderColor("bg_color");
      tg.setBackgroundColor("bg_color");
    } catch (_) {}
  }

  function initTelegram() {
    if (!tg) return;
    try {
      tg.ready();
      tg.expand();
    } catch (_) {}
    applyTheme();
    try {
      tg.onEvent("themeChanged", applyTheme);
    } catch (_) {}
  }

  const core = Object.freeze({
    tg, getInitData, esc, safeUrl, safePanelPath, num, money, parseAmount, setCurrency, formatDateTime,
    haptic, toast, confirmAction, openExternal, openTelegramLink, api, ApiError, copyText, markCopied,
    applyTheme, initTelegram,
  });
  root.PGMini = Object.assign(root.PGMini || {}, { core });
})(typeof window === "object" ? window : globalThis);
