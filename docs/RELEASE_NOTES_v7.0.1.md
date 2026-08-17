# PGClockBot v7.0.1 — Release Notes

**Tag:** `v7.0.1`  
**App version:** `7.0.1`

---

## Mini App

- Status chips use plain panel labels (no emoji/circle next to the tag).
- QR display is compact and matches the service-card theme (small white frame, dark card).
- Copy link flashes to «کپی شد» then returns to the normal label, same as the web panel.
- Open-panel shortcuts use the live panel address (`public_panel_base_url`), not `PUBLIC_BASE_URL`. If there is no domain, the HTTP+IP panel URL is used.

## Deploy

In-panel update to `7.0.1` (no new migration). Hard-refresh the Mini App after update.
