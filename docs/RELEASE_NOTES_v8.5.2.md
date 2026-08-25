# PGClockBot v8.5.2 — Release Notes

**Tag:** `v8.5.2`  
**App version:** `8.5.2`  
**Restore point:** tag `v8.5.1`

## Fixes (design-language root causes)

1. **User edit modal** — Restored panel-standard `data-modal-open="modal-user-edit"`; fragment load only. Removed parallel `data-user-edit-open` / `openUserEdit`.
2. **Service menu** — Back to panel `ui-select` (ported menu). Options use boxed borders (`.users-svc-boxed`).
3. **Mobile volume/expiry** — Shown under the service cell via `.users-svc-meta` (desktop columns unchanged).
4. **Section tabs black edge** — Removed scroll edge `mask-image` that painted a black crescent beside the first RTL tab; `scrollIntoView` uses `nearest`.
5. **Telegram preview open button** — Full-width on mobile again (`.tg-preview-gate > .actions` included in mobile action grid).

## Deploy

In-panel update to `8.5.2` (no new migration). Hard-refresh after update.
