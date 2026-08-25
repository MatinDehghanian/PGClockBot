# PGClockBot v8.5.12 — Release Notes

**Tag:** `v8.5.12`
**App version:** `8.5.12`
**Restore point:** tag `v8.5.11`

## Fixes

1. **Safari iOS 26 — solid black address/tab bar (the actual “black bar”)**
   - Symptom: In Safari on iPhone, the bottom URL/tab bar is **solid opaque black** while other sites (e.g. Google) show the native **Liquid Glass** translucent bar.
   - Root: Safari 26+ **ignores `theme-color`**. It tints the bottom toolbar by sampling the **`background-color` of `position: fixed` elements within ~3px of the viewport bottom**. Our mobile `.shell` (`background: #09090b`, fixed full viewport) and closed `.side` drawer (`bottom: 0`, dark bg) forced Safari to paint a solid black bar — not a layout gap.
   - Fix (`html.ios-safari` only — in-browser Safari, not Home Screen PWA):
     - `.shell { background: transparent }` — dark bg moves to `.main` only (content area)
     - `theme-color` set to `transparent`; theme switcher skips meta updates on ios-safari
     - `.side:not(.open) { bottom: auto; height: calc(...) }` — closed drawer no longer anchors to bottom edge

## Deploy

In-panel update to `8.5.12`. Close Safari tab and reopen (cache `panel.css`).
