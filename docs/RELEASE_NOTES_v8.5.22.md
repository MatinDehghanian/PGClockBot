# PGClockBot v8.5.22 — Release Notes

**Tag:** `v8.5.22`
**App version:** `8.5.22`

## Fixes

1. **Removed page loading system entirely** — `#page-load-veil`, `#page-skeleton`, `page-loading` CSS/JS, `armVeil()` in widget defer. Root cause of black broken pages on navigation (screenshot 1).

2. **Mobile/PWA full height** — shell + sidebar use `100lvh` with `bottom: 0`. v8.5.21 used `100dvh` + `max-height: 100dvh` which leaves a black strip on iOS when the URL bar hides (screenshot 2).

3. **No `--safari-overlay`, no drawer `height:0`** — keeps sidebar/page full height without the gaps from v8.5.16–8.5.19.

4. Widget `/body` fetch still runs silently (no overlay).

5. SW cache **`pgclock-shell-v12`**.

## Deploy

Update to **8.5.22**, clear website data once, hard refresh.
