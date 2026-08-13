# PGClockBot v5.2.12 — Release Notes

**Tag:** `v5.2.12`  
**App version:** `5.2.12`

---

## Clarify

Hard-delete of a bot user is real (success flash only after DB commit). If the same Telegram account messages the bot again, middleware `get_or_create_user` creates a **fresh empty** account — which can look like “delete failed” in the panel.

## Changes

- Delete confirm / help text warns that messaging the bot again recreates an empty account for the same Telegram id.
- Automated tests cover hard-delete removal and post-delete recreate via `get_or_create_user`.

## Deploy

In-panel update to `5.2.12` (or deploy this tag). Hard-refresh the panel.
