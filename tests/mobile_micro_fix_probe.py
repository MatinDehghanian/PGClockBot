#!/usr/bin/env python3
"""Footer inset unity + sidebar anchors + nav-clock state transitions.

Geometry contract (v8.5.34):
  - One inset path: both .site-footer and .side-foot use padding-bottom =
    --bottom-inset (foot-gap + safe-bottom) and shared --footer-bar-h.
  - Separator tops (border-top / rect.top) align when sidebar is open.
  - Content-bottom → layout bottom == --bottom-inset for both footers.
  - Shell fills the viewport on short pages; .main is not a vertical scroller.
  - Nav clock arms immediately (no CSS delay / no setTimeout race).
"""
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
      const footPad = parseFloat(cs(footer,'padding-bottom')||0);
      const sfPad = sideFoot ? parseFloat(cs(sideFoot,'padding-bottom')||0) : 0;
      return {{
        innerHeight: layoutBottom,
        maxScroll: Math.max(0, document.documentElement.scrollHeight - document.documentElement.clientHeight),
        mainIsScroller: ['auto','scroll'].includes(cs(main,'overflow-y')),
        mainOverflow: cs(main,'overflow-y'),
        shell: {{rect: shellR, padBottom: cs(shell,'padding-bottom')}},
        main: {{rect: mainR, padBottom: cs(main,'padding-bottom'), transform: cs(main,'transform')}},
        footer: {{
          rect: footR,
          marginTop: cs(footer,'margin-top'),
          padBottom: cs(footer,'padding-bottom'),
          contentBottom: footR.bottom - footPad,
        }},
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
          contentBottom: sfR.bottom - sfPad,
        }} : null,
        gaps: {{
          footer_content_to_layout: layoutBottom - (footR.bottom - footPad),
          footer_box_to_layout: layoutBottom - footR.bottom,
          footer_to_shell: shellR.bottom - footR.bottom,
          shell_to_layout: layoutBottom - shellR.bottom,
          side_to_layout: layoutBottom - sideR.bottom,
          backdrop_to_layout: layoutBottom - backR.bottom,
          side_vs_backdrop: Math.abs(sideR.bottom - backR.bottom),
          sideFoot_content_to_layout: sfR ? (layoutBottom - (sfR.bottom - sfPad)) : null,
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
          window.__armNavClock = () => {
            el.hidden = false;
            el.setAttribute('aria-hidden','false');
            void el.offsetWidth;
          };
          window.__disarmNavClock = () => {
            el.hidden = true;
            el.setAttribute('aria-hidden','true');
          };
          window.__clockState = () => {
            const cs = getComputedStyle(el);
            return {
              hidden: el.hidden,
              opacity: cs.opacity,
              visibility: cs.visibility,
              pointerEvents: cs.pointerEvents,
              position: cs.position,
              backgroundImage: cs.backgroundImage,
              backgroundColor: cs.backgroundColor,
              matteColor: getComputedStyle(el, '::before').backgroundColor,
              shellH: document.querySelector('.shell').getBoundingClientRect().height,
              docSH: document.documentElement.scrollHeight,
            };
          };
        }"""
        )
        s0 = page.evaluate("() => window.__clockState()")
        page.evaluate("() => window.__armNavClock()")
        s_armed = page.evaluate("() => window.__clockState()")
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
        "armed": s_armed,
        "disarmed": s_disarmed,
    }

    expected = FOOT_GAP + SAFE_BOTTOM

    # A) Content-bottom inset is constant (short closed + long at bottom)
    short_inset = short_closed["gaps"]["footer_content_to_layout"]
    long_inset = long_bottom["gaps"]["footer_content_to_layout"]
    if abs(short_inset - expected) > TOL:
        errors.append(f"short footer content inset {short_inset} != {expected}")
    if abs(long_inset - expected) > TOL:
        errors.append(f"long footer content inset {long_inset} != {expected}")
    if abs(short_inset - long_inset) > TOL:
        errors.append(f"short/long footer inset mismatch {short_inset} vs {long_inset}")

    main_pb = parse_px(short_closed["main"]["padBottom"])
    if abs(main_pb) > TOL:
        errors.append(f"short: .main must not own bottom inset (padBottom={main_pb})")
    foot_pb = parse_px(short_closed["footer"]["padBottom"])
    if abs(foot_pb - expected) > TOL:
        errors.append(f"short: site-footer padBottom {foot_pb} != {expected}")
    if abs(short_closed["gaps"]["footer_box_to_layout"]) > TOL:
        errors.append(
            f"short: site-footer box must reach layout bottom "
            f"(gap={short_closed['gaps']['footer_box_to_layout']})"
        )
    if short_closed["mainIsScroller"] or long_bottom["mainIsScroller"]:
        errors.append(".main must not be vertical scroller")
    if abs(short_closed["gaps"]["shell_to_layout"]) > TOL:
        errors.append("short: shell must fill viewport (no blank under footer)")
    if parse_px(short_closed["shell"]["padBottom"]) > TOL:
        errors.append("short: shell padding-bottom must be 0 (no empty safe strip)")

    # Sidebar open: drawer+backdrop to layout bottom; separators + content inset match
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
        sf_content_bottom = snap["sideFoot"]["contentBottom"]
        main_content_bottom = snap["footer"]["contentBottom"]
        if abs(sf_content_bottom - main_content_bottom) > TOL:
            errors.append(
                f"{label}: content bottoms misaligned side={sf_content_bottom} main={main_content_bottom}"
            )
        sf_top = snap["sideFoot"]["rect"]["top"]
        ft_top = snap["footer"]["rect"]["top"]
        if abs(sf_top - ft_top) > TOL:
            errors.append(f"{label}: footer separators misaligned side={sf_top} main={ft_top}")
        sf_content_inset = snap["gaps"]["sideFoot_content_to_layout"]
        if abs(sf_content_inset - expected) > TOL:
            errors.append(f"{label}: side-foot content inset {sf_content_inset} != {expected}")

    # C) Nav clock: immediate visible arm
    if not s0["hidden"] or float(s0["opacity"]) > 0.01:
        errors.append("nav-clock: must start hidden")
    if s_armed["hidden"] or float(s_armed["opacity"]) < 0.95 or s_armed["visibility"] != "visible":
        errors.append("nav-clock: arm must show immediately")
    if not s_disarmed["hidden"]:
        errors.append("nav-clock: disarm must set hidden")
    if s_armed["pointerEvents"] != "none" or s_armed["position"] != "fixed":
        errors.append("nav-clock: must stay fixed + pointer-events:none")
    blank = ("rgba(0, 0, 0, 0)", "transparent", "rgba(0,0,0,0)")
    # The matte paints on ::before, never on the fixed box: Safari 26+ tints its
    # own toolbars from the background of fixed boxes at the viewport edge.
    if (s_armed.get("backgroundColor") or "").lower() not in blank:
        errors.append("nav-clock: fixed box must stay transparent (browser-chrome tint)")
    if (s_armed.get("matteColor") or "").lower() in blank:
        errors.append("nav-clock: ::before must paint the light matte")
    if abs(s0["shellH"] - s_armed["shellH"]) > TOL or abs(s0["docSH"] - s_armed["docSH"]) > TOL:
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
