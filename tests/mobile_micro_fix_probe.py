#!/usr/bin/env python3
"""Footer inset unity + sidebar anchors + nav-clock state transitions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHORT = ROOT / "tests/fixtures/mobile_shell_probe.html"
LONG = ROOT / "tests/fixtures/mobile_shell_probe_long.html"
VIEWPORT = {"width": 390, "height": 844}
SAFE_BOTTOM = 34.0
FOOT_GAP = 16.0
TOL = 2.0


def parse_px(val: str) -> float:
    try:
        return float(str(val).replace("px", "").strip() or 0)
    except ValueError:
        return -1.0


def measure(page) -> dict:
    return page.evaluate(
        f"""() => {{
      const FOOT_GAP = {FOOT_GAP};
      const SAFE_BOTTOM = {SAFE_BOTTOM};
      const cs = (el,p)=> el ? getComputedStyle(el).getPropertyValue(p).trim() : '';
      const r = el => {{ const b = el.getBoundingClientRect(); return {{top:b.top,bottom:b.bottom,height:b.height}}; }};
      const shell = document.querySelector('.shell');
      const main = document.querySelector('.main');
      const footer = document.querySelector('.site-footer');
      const side = document.querySelector('.side');
      const back = document.querySelector('.side-backdrop');
      const sideFoot = document.querySelector('.side-foot');
      const last = document.querySelector('[data-probe-last]');
      const shellR = r(shell); const footR = r(footer); const mainR = r(main);
      const sideR = r(side); const backR = r(back); const sfR = sideFoot ? r(sideFoot) : null;
      const layoutBottom = window.innerHeight;
      return {{
        innerHeight: layoutBottom,
        maxScroll: Math.max(0, document.documentElement.scrollHeight - document.documentElement.clientHeight),
        mainIsScroller: ['auto','scroll'].includes(cs(main,'overflow-y')),
        mainOverflow: cs(main,'overflow-y'),
        shell: {{rect: shellR, padBottom: cs(shell,'padding-bottom')}},
        main: {{rect: mainR, padBottom: cs(main,'padding-bottom'), transform: cs(main,'transform')}},
        footer: {{rect: footR, marginTop: cs(footer,'margin-top')}},
        last: {{rect: last ? r(last) : null}},
        side: {{
          rect: sideR,
          padBottom: cs(side,'padding-bottom'),
          bottom: cs(side,'bottom'),
          top: cs(side,'top'),
          right: cs(side,'right'),
          transform: cs(side,'transform'),
          open: side.classList.contains('open'),
        }},
        backdrop: {{
          rect: backR,
          bottom: cs(back,'bottom'),
          top: cs(back,'top'),
          transform: cs(back,'transform'),
        }},
        sideFoot: sfR ? {{
          rect: sfR,
          padBottom: cs(sideFoot,'padding-bottom'),
        }} : null,
        gaps: {{
          footer_to_layout: layoutBottom - footR.bottom,
          footer_to_shell: shellR.bottom - footR.bottom,
          below_footer_inside_shell: shellR.bottom - footR.bottom - parseFloat(cs(shell,'padding-bottom')||0),
          shell_to_layout: layoutBottom - shellR.bottom,
          side_to_layout: layoutBottom - sideR.bottom,
          backdrop_to_layout: layoutBottom - backR.bottom,
          side_vs_backdrop: Math.abs(sideR.bottom - backR.bottom),
          sideFoot_to_sideBottom: sfR ? (sideR.bottom - sfR.bottom) : null,
          sideFoot_to_layout: sfR ? (layoutBottom - sfR.bottom) : null,
          expected_footer_inset: FOOT_GAP + SAFE_BOTTOM,
        }},
      }};
    }}"""
    )


def open_sidebar(page) -> None:
    page.locator("#menu-toggle").click()
    page.wait_for_timeout(250)


def main() -> None:
    errors: list[str] = []
    out: dict = {"viewport": VIEWPORT}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        short_closed = measure(page)
        open_sidebar(page)
        short_open = measure(page)
        page.close()

        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(LONG.resolve().as_uri(), wait_until="networkidle")
        long_top = measure(page)
        page.evaluate(
            """() => {
          const max = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
          window.scrollTo(0, max);
        }"""
        )
        page.wait_for_timeout(50)
        long_bottom = measure(page)
        open_sidebar(page)
        long_open = measure(page)
        page.close()

        # Nav clock state machine on a fixture page with injected clock + panel.js logic proxy
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        page.add_style_tag(path=str(ROOT / "app/web/static/panel.css"))
        page.evaluate(
            """() => {
          let el = document.getElementById('panel-nav-clock');
          if (!el) {
            el = document.createElement('div');
            el.id = 'panel-nav-clock';
            el.className = 'panel-nav-clock';
            el.hidden = true;
            el.setAttribute('aria-hidden','true');
            el.innerHTML = '<span class="panel-load-clock"><span class="panel-load-clock-face"><span class="panel-load-clock-hand panel-load-clock-hour"></span><span class="panel-load-clock-hand panel-load-clock-minute"></span><span class="panel-load-clock-hub"></span></span></span>';
            document.body.appendChild(el);
          }
          // Mirror production arm: remove hidden immediately (CSS delay handles reveal)
          window.__armNavClock = () => { el.hidden = false; el.setAttribute('aria-hidden','false'); };
          window.__disarmNavClock = () => { el.hidden = true; el.setAttribute('aria-hidden','true'); };
          window.__clockState = () => {
            const cs = getComputedStyle(el);
            return {
              hidden: el.hidden,
              opacity: cs.opacity,
              visibility: cs.visibility,
              pointerEvents: cs.pointerEvents,
              position: cs.position,
              shellH: document.querySelector('.shell').getBoundingClientRect().height,
              docSH: document.documentElement.scrollHeight,
            };
          };
        }"""
        )
        s0 = page.evaluate("() => window.__clockState()")
        page.evaluate("() => window.__armNavClock()")
        s_armed = page.evaluate("() => window.__clockState()")
        page.wait_for_timeout(160)
        s_visible = page.evaluate("() => window.__clockState()")
        page.evaluate("() => window.__disarmNavClock()")
        s_disarmed = page.evaluate("() => window.__clockState()")
        page.close()
        browser.close()

    out["short_closed"] = short_closed
    out["short_open"] = short_open
    out["long_top"] = long_top
    out["long_bottom"] = long_bottom
    out["long_open"] = long_open
    out["nav_clock"] = {
        "initial": s0,
        "armed_immediate": s_armed,
        "after_delay": s_visible,
        "disarmed": s_disarmed,
    }

    expected = FOOT_GAP + SAFE_BOTTOM

    # A) Footer: short closed + long at bottom share same layout inset
    short_inset = short_closed["gaps"]["footer_to_layout"]
    long_inset = long_bottom["gaps"]["footer_to_layout"]
    if abs(short_inset - expected) > TOL:
        errors.append(f"short footer inset {short_inset} != {expected}")
    if abs(long_inset - expected) > TOL:
        errors.append(f"long footer inset {long_inset} != {expected}")
    if abs(short_inset - long_inset) > TOL:
        errors.append(f"short/long footer inset mismatch {short_inset} vs {long_inset}")
    if abs(short_closed["gaps"]["below_footer_inside_shell"] - FOOT_GAP) > TOL:
        errors.append("short: blank below footer inside shell != foot-gap")
    if short_closed["mainIsScroller"] or long_bottom["mainIsScroller"]:
        errors.append(".main must not be vertical scroller")
    if abs(short_closed["gaps"]["shell_to_layout"]) > TOL:
        errors.append("short: shell must fill viewport (no blank under footer)")

    # Sidebar open: drawer+backdrop to layout bottom; foot inset matches main footer
    for label, snap in (("short_open", short_open), ("long_open", long_open)):
        if snap["gaps"]["side_to_layout"] > TOL:
            errors.append(f"{label}: side gap to layout={snap['gaps']['side_to_layout']}")
        if snap["gaps"]["backdrop_to_layout"] > TOL:
            errors.append(f"{label}: backdrop gap to layout={snap['gaps']['backdrop_to_layout']}")
        if snap["gaps"]["side_vs_backdrop"] > TOL:
            errors.append(f"{label}: side/backdrop delta={snap['gaps']['side_vs_backdrop']}")
        if snap["side"]["padBottom"] not in ("0px", "0"):
            errors.append(f"{label}: side padding-bottom must be 0")
        if snap["side"]["transform"] not in ("none",):
            errors.append(f"{label}: side must not use transform (got {snap['side']['transform']})")
        sf_pad = parse_px((snap.get("sideFoot") or {}).get("padBottom") or "0")
        if abs(sf_pad - expected) > TOL:
            errors.append(f"{label}: side-foot padBottom {sf_pad} != {expected}")
        # side-foot border-box reaches drawer bottom (pad is inner); content edge must
        # match main footer bottom within tolerance
        sf_content_bottom = snap["sideFoot"]["rect"]["bottom"] - sf_pad
        main_foot_bottom = snap["footer"]["rect"]["bottom"]
        if abs(sf_content_bottom - main_foot_bottom) > TOL:
            errors.append(
                f"{label}: side-foot content bottom {sf_content_bottom} vs main footer {main_foot_bottom}"
            )
        sf_content_inset = snap["innerHeight"] - sf_content_bottom
        if abs(sf_content_inset - expected) > TOL:
            errors.append(f"{label}: side-foot content inset {sf_content_inset} != {expected}")

    # C) Nav clock transitions
    if not s0["hidden"] or float(s0["opacity"]) > 0.01:
        errors.append("nav-clock: must start hidden")
    if s_armed["hidden"]:
        errors.append("nav-clock: arm must clear [hidden] immediately")
    if float(s_armed["opacity"]) > 0.05:
        errors.append("nav-clock: must stay invisible during 140ms anti-flicker window")
    if float(s_visible["opacity"]) < 0.95 or s_visible["visibility"] != "visible":
        errors.append("nav-clock: must become visible after delay")
    if not s_disarmed["hidden"]:
        errors.append("nav-clock: disarm must set hidden")
    if s_armed["pointerEvents"] != "none" or s_armed["position"] != "fixed":
        errors.append("nav-clock: must stay fixed + pointer-events:none")
    if abs(s0["shellH"] - s_visible["shellH"]) > TOL or abs(s0["docSH"] - s_visible["docSH"]) > TOL:
        errors.append("nav-clock: must not change document/shell geometry")

    out["passed"] = not errors
    out["errors"] = errors
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        raise SystemExit(1)
    print("FOOTER_SIDEBAR_CLOCK_PASSED", file=sys.stderr)


if __name__ == "__main__":
    main()
