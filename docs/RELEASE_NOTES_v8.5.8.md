# PGClockBot v8.5.8 — Release Notes

**Tag:** `v8.5.8`
**App version:** `8.5.8`
**Restore point:** tag `v8.5.7`

## Fixes

1. **Users table — service picker polish**
   - Plan select control is vertically centered in its row (`flex` wrap + `margin-top: 0` on `.ui-select`).
   - Dropdown menu shows an orange alert dot next to each plan that has an active alert (`data-alert` on `<option>` → dot in boxed menu row).
   - Removed the orange cell tint (`.has-svc-alert` background) — alert is dot-only, on the toggle and in the menu.
   - Expiry column shows days only (`5 روز`, `منقضی`) — no calendar date prefix.

## Deploy

In-panel update to `8.5.8` (no new migration). Hard-refresh after update.
