# PGClockBot v6.2.6 — Release Notes

**Tag:** `v6.2.6`  
**App version:** `6.2.6`

---

## UX / security

### Plan modal: مخاطب پلن + نوع پلن

- Audience control labeled **مخاطب پلن**; **نوع پلن** sits directly under it.
- For resellers, kind options are: اشتراک ثابت | اشتراک PAYG | بسته حجم | بسته کاربر.

### Addon packs are capacity-only

- When kind is volume/user addon, UI and API strip groups, PG role, permissions,
  create_pg_admin, share URL, allow_buy_extra, renew/duration/included fields.
- Server fail-closed: addons cannot smuggle subscription provisioning knobs.

### Catalog gated to subscribed resellers

- Apply/list flows stay on `plan_kind=subscription` only.
- Bot menu shows addon packs only when the reseller holds a subscription plan;
  handlers also require an active PG-admin subscription before listing/buying.
- Exception path no longer fail-opens addon buttons.

## Deploy

In-panel update to `6.2.6` (no new migration). Hard-refresh `/plans` after update.
