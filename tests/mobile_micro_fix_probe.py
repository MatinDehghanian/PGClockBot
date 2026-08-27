#!/usr/bin/env python3
"""Micro-fix probes: short-page footer fill + sidebar bottom + nav clock."""
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


def measure_page(page) -> dict:
    return page.evaluate(
        """() => {
      const cs = (el,p)=> el ? getComputedStyle(el).getPropertyValue(p).trim() : '';
      const r = el => { const b = el.getBoundingClientRect(); return {top:b.top,bottom:b.bottom,height:b.height}; };
      const shell = document.querySelector('.shell');
      const main = document.querySelector('.main');
      const footer = document.querySelector('.site-footer');
      const last = document.querySelector('[data-probe-last]');
      const side = document.querySelector('.side');
      const back = document.querySelector('.side-backdrop');
      const sideFoot = document.querySelector('.side-foot');
      const shellR = r(shell); const footR = r(footer); const mainR = r(main);
      return {
        innerHeight: window.innerHeight,
        maxScroll: Math.max(0, document.documentElement.scrollHeight - document.documentElement.clientHeight),
        mainIsScroller: ['auto','scroll'].includes(cs(main,'overflow-y')),
        mainOverflow: cs(main,'overflow-y'),
        mainFlex: cs(main,'flex'),
        shellFlex: cs(shell,'flex'),
        footerMarginTop: cs(footer,'margin-top'),
        shell: {rect: shellR, padBottom: cs(shell,'padding-bottom')},
        main: {rect: mainR, padBottom: cs(main,'padding-bottom')},
        footer: {rect: footR},
        last: {rect: r(last)},
        gaps: {
          shell_to_layout: window.innerHeight - shellR.bottom,
          footer_to_shell: shellR.bottom - footR.bottom,
          below_footer_inside_shell: shellR.bottom - footR.bottom - parseFloat(cs(shell,'padding-bottom')||0),
          content_to_footer: footR.top - last.getBoundingClientRect().bottom,
        },
        side: {
          rect: r(side),
          padBottom: cs(side,'padding-bottom'),
          bottom: cs(side,'bottom'),
          open: side.classList.contains('open'),
        },
        backdrop: {rect: r(back)},
        sideFoot: sideFoot ? {
          rect: r(sideFoot),
          padBottom: cs(sideFoot,'padding-bottom'),
        } : null,
      };
    }"""
    )


def open_sidebar(page) -> None:
    page.locator("#menu-toggle").click()
    page.wait_for_timeout(200)


def main() -> None:
    errors: list[str] = []
    out: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # —— Short page ——
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        page.evaluate(
            """() => {
          Object.defineProperty(window.visualViewport,'height',{configurable:true,get:()=>720});
          Object.defineProperty(window.visualViewport,'offsetTop',{configurable:true,get:()=>0});
        }"""
        )
        short_closed = measure_page(page)
        open_sidebar(page)
        short_open = measure_page(page)
        page.close()

        # —— Long page ——
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(LONG.resolve().as_uri(), wait_until="networkidle")
        long_top = measure_page(page)
        page.evaluate(
            """() => {
          const max = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
          window.scrollTo(0, max);
        }"""
        )
        long_bottom = measure_page(page)
        page.close()

        # —— Nav clock geometry (no layout shift) ——
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        # Inject clock markup like base.html (fixture has no base wrapper)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        page.evaluate(
            """() => {
          if (!document.getElementById('panel-nav-clock')) {
            const el = document.createElement('div');
            el.id = 'panel-nav-clock';
            el.className = 'panel-nav-clock';
            el.hidden = true;
            el.setAttribute('aria-hidden','true');
            el.innerHTML = '<span class="panel-load-clock" aria-hidden="true"><span class="panel-load-clock-face"><span class="panel-load-clock-hand panel-load-clock-hour"></span><span class="panel-load-clock-hand panel-load-clock-minute"></span><span class="panel-load-clock-hub"></span></span></span>';
            document.body.appendChild(el);
          }
        }"""
        )
        before = page.evaluate(
            """() => ({
              shellH: document.querySelector('.shell').getBoundingClientRect().height,
              docSH: document.documentElement.scrollHeight,
              bodyOverflow: getComputedStyle(document.body).overflowY,
            })"""
        )
        page.evaluate(
            """() => {
              const el = document.getElementById('panel-nav-clock');
              el.hidden = false;
              el.setAttribute('aria-hidden','false');
            }"""
        )
        after = page.evaluate(
            """() => {
              const el = document.getElementById('panel-nav-clock');
              const cs = getComputedStyle(el);
              return {
                shellH: document.querySelector('.shell').getBoundingClientRect().height,
                docSH: document.documentElement.scrollHeight,
                bodyOverflow: getComputedStyle(document.body).overflowY,
                clock: {
                  position: cs.position,
                  pointerEvents: cs.pointerEvents,
                  zIndex: cs.zIndex,
                  display: cs.display,
                },
              };
            }"""
        )
        page.close()
        browser.close()

    out["short_closed"] = short_closed
    out["short_open"] = short_open
    out["long_top"] = long_top
    out["long_bottom"] = long_bottom
    out["nav_clock"] = {"before": before, "after": after}

    # Short page: shell fills viewport; no blank after footer; footer bottom-aligned
    if short_closed["mainIsScroller"]:
        errors.append("short: .main must not be vertical scroller")
    if abs(short_closed["gaps"]["shell_to_layout"]) > TOL:
        errors.append(f"short: shell must fill viewport (shell_to_layout={short_closed['gaps']['shell_to_layout']})")
    if abs(short_closed["gaps"]["below_footer_inside_shell"] - FOOT_GAP) > TOL:
        errors.append(
            f"short: blank below footer inside shell={short_closed['gaps']['below_footer_inside_shell']} != {FOOT_GAP}"
        )
    if abs(short_closed["gaps"]["footer_to_shell"] - (FOOT_GAP + SAFE_BOTTOM)) > TOL:
        errors.append(f"short: footer→shell={short_closed['gaps']['footer_to_shell']}")
    if short_closed["maxScroll"] > 0:
        errors.append(f"short: unexpected scroll maxScroll={short_closed['maxScroll']}")
    if short_closed["footerMarginTop"] in ("0px", "0"):
        errors.append("short: footer margin-top should resolve from auto (not 0)")
    # Resolved auto margin is a positive spacer above footer on short pages
    if short_closed["gaps"]["content_to_footer"] < 100:
        errors.append(
            f"short: footer not bottom-aligned (content_to_footer={short_closed['gaps']['content_to_footer']})"
        )

    # Sidebar open: drawer + backdrop to layout bottom; safe-area on foot only
    so = short_open
    side_gap = abs(so["innerHeight"] - so["side"]["rect"]["bottom"])
    back_gap = abs(so["innerHeight"] - so["backdrop"]["rect"]["bottom"])
    delta = abs(so["side"]["rect"]["bottom"] - so["backdrop"]["rect"]["bottom"])
    if side_gap > TOL:
        errors.append(f"sidebar: side gap to layout bottom={side_gap}")
    if back_gap > TOL:
        errors.append(f"sidebar: backdrop gap to layout bottom={back_gap}")
    if delta > TOL:
        errors.append(f"sidebar: side/backdrop bottom delta={delta}")
    if so["side"]["padBottom"] not in ("0px", "0"):
        errors.append(f"sidebar: side padding-bottom should be 0 (inner safe-area), got {so['side']['padBottom']}")
    if so["sideFoot"] and abs(parse_px(so["sideFoot"]["padBottom"]) - SAFE_BOTTOM) > TOL:
        errors.append(f"sidebar: side-foot safe-bottom missing ({so['sideFoot']['padBottom']})")

    # Long page still scrolls via document
    if long_top["mainIsScroller"] or long_bottom["mainIsScroller"]:
        errors.append("long: .main must not be scroller")
    if long_bottom["maxScroll"] <= 0 and long_top["maxScroll"] <= 0:
        errors.append("long: document should be scrollable")
    # After scroll to bottom, footer still in flow with same foot-gap
    if abs(long_bottom["gaps"]["below_footer_inside_shell"] - FOOT_GAP) > TOL:
        errors.append(f"long: below-footer gap changed ({long_bottom['gaps']['below_footer_inside_shell']})")

    # Nav clock: no geometry change
    if abs(before["shellH"] - after["shellH"]) > TOL:
        errors.append("nav-clock: shell height changed when shown")
    if abs(before["docSH"] - after["docSH"]) > TOL:
        errors.append("nav-clock: document scrollHeight changed when shown")
    if after["clock"]["position"] != "fixed":
        errors.append("nav-clock: must be position:fixed")
    if after["clock"]["pointerEvents"] != "none":
        errors.append("nav-clock: must be pointer-events:none")

    out["passed"] = not errors
    out["errors"] = errors
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        raise SystemExit(1)
    print("MICRO_FIX_PASSED", file=sys.stderr)


def parse_px(val: str) -> float:
    try:
        return float(val.replace("px", "").strip() or 0)
    except ValueError:
        return -1


if __name__ == "__main__":
    main()
