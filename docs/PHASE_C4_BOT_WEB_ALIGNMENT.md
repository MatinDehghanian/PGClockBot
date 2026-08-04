# Phase C4 — Bot / Web Authorization Alignment

**Status:** Implemented  
**Branch:** `cursor/phase-c4-bot-web-alignment-b96b`  
**Depends on:** C0–C3

---

## Goal

Web Panel menus/API and Telegram Bot menus/actions use the **same** shop authorization source (`AuthzContext` / `web_permissions`).

## What changed

| File | Change |
|------|--------|
| `app/services/authz.py` | `authz_from_profile`, `shop_feature_allowed`, `shop_menu_keys` |
| `app/services/resellers.py` | `has_perm` / `has_bot_perm` → `shop_feature_allowed` |
| `app/bot/auth.py` | `can_shop_feature` (Owner/Admin bypass + authz) |
| `app/api/app.py` | Login + `require_staff` ACL via `resolve_shop_permissions_from_profile` |
| `app/api/reseller_pages.py` / `shop_settings.py` | Same resolver |
| `app/bot/keyboards.py` / `reseller_settings.py` | `shop_feature_allowed` / resolver |
| `tests/test_phase_c4_bot_web_alignment.py` | Cross-platform parity tests |

## Behavior fix (alignment)

**Before:** Web soft-upgraded empty `web_permissions` to DEFAULT; Bot treated empty as deny.  
**After:** Both use the same rules — `None` → DEFAULT; `""` → deny; source column = `web_permissions` (`bot_permissions` mirrored only).

## Not changed

- Database schema / Alembic  
- Credentials / PG client selection  
- Owner bot admin tools (`is_platform_admin`)  
- pg_staff: still no shop features; Bot PG remains platform-admin only  

## Rollback

Revert C4 commits. No migrations.
