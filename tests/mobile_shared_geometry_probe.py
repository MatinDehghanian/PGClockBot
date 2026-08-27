#!/usr/bin/env python3
"""Shared-geometry forensic probe: short vs long must not change bottom system."""
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
EXPECTED = FOOT_GAP + SAFE_BOTTOM


def parse_px(val: str) -> float:
    try:
        return float(str(val).replace("px", "").strip() or 0)
    except ValueError:
        return -1.0


def measure(page) -> dict:
    return page.evaluate(
        """() => {
      const cs = (el,p)=> el ? getComputedStyle(el).getPropertyValue(p).trim() : '';
      const r = el => { const b=el.getBoundingClientRect(); return {top:b.top,bottom:b.bottom,height:b.height}; };
      const html=document.documentElement, body=document.body;
      const shell=document.querySelector('.shell');
      const main=document.querySelector('.main');
      const footer=document.querySelector('.site-footer');
      const side=document.querySelector('.side');
      const back=document.querySelector('.side-backdrop');
      const sf=document.querySelector('.side-foot');
      const ih=window.innerHeight;
      const sfR = sf ? r(sf) : null;
      const sfPad = sf ? parseFloat(cs(sf,'padding-bottom')||0) : 0;
      return {
        ih,
        navOpen: body.classList.contains('nav-open'),
        htmlOverflowX: cs(html,'overflow-x'),
        htmlOverflowY: cs(html,'overflow-y'),
        bodyOverflowX: cs(body,'overflow-x'),
        bodyOverflowY: cs(body,'overflow-y'),
        mainOverflowY: cs(main,'overflow-y'),
        sideTransform: cs(side,'transform'),
        sideBottomCss: cs(side,'bottom'),
        maxScroll: Math.max(0, html.scrollHeight - html.clientHeight),
        bodyMaxScroll: Math.max(0, body.scrollHeight - body.clientHeight),
        shellBottom: r(shell).bottom,
        footerBottom: r(footer).bottom,
        sideBottom: r(side).bottom,
        backBottom: r(back).bottom,
        sideFootContentBottom: sfR ? sfR.bottom - sfPad : null,
        gaps: {
          shell_to_ih: ih - r(shell).bottom,
          footer_to_ih: ih - r(footer).bottom,
          side_to_ih: ih - r(side).bottom,
          back_to_ih: ih - r(back).bottom,
          side_vs_back: Math.abs(r(side).bottom - r(back).bottom),
          footer_to_shell: r(shell).bottom - r(footer).bottom,
          sideFoot_content_to_ih: sfR ? ih - (sfR.bottom - sfPad) : null,
        },
        sidePadBottom: cs(side,'padding-bottom'),
        sideFootPadBottom: cs(sf,'padding-bottom'),
      };
    }"""
    )


def open_drawer(page) -> None:
    page.locator("#menu-toggle").click()
    page.wait_for_timeout(200)


def main() -> None:
    errors: list[str] = []
    out: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        short_closed = measure(page)
        open_drawer(page)
        short_open = measure(page)
        page.close()

        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(LONG.resolve().as_uri(), wait_until="networkidle")
        long_top = measure(page)
        page.evaluate(
            """() => {
          const el = document.scrollingElement || document.documentElement;
          const max = Math.max(0, el.scrollHeight - window.innerHeight);
          el.scrollTop = max;
        }"""
        )
        page.wait_for_timeout(50)
        long_bottom = measure(page)
        open_drawer(page)
        long_open = measure(page)
        page.close()
        browser.close()

    out.update(
        short_closed=short_closed,
        short_open=short_open,
        long_top=long_top,
        long_bottom=long_bottom,
        long_open=long_open,
    )

    # Scroll owner: html visible on BOTH axes (CSS couples x/y), body auto; main never
    for label, snap in (("short_closed", short_closed), ("long_bottom", long_bottom)):
        if snap["htmlOverflowX"] != "visible":
            errors.append(
                f"{label}: html overflow-x must be visible "
                f"(got {snap['htmlOverflowX']}) — hidden couples y→auto"
            )
        if snap["htmlOverflowY"] != "visible":
            errors.append(f"{label}: html overflow-y must be visible (got {snap['htmlOverflowY']})")
        if snap["bodyOverflowY"] not in ("auto", "scroll"):
            errors.append(f"{label}: body must be vertical scrollport (got {snap['bodyOverflowY']})")
        if snap["bodyOverflowX"] != "hidden":
            errors.append(f"{label}: body must clip x (got {snap['bodyOverflowX']})")
        if snap["mainOverflowY"] != "visible":
            errors.append(f"{label}: .main must not scroll")

    # Short page fills viewport; footer inset standard
    if abs(short_closed["gaps"]["shell_to_ih"]) > TOL:
        errors.append(f"short: shell_to_ih={short_closed['gaps']['shell_to_ih']}")
    if abs(short_closed["gaps"]["footer_to_ih"] - EXPECTED) > TOL:
        errors.append(f"short footer inset {short_closed['gaps']['footer_to_ih']} != {EXPECTED}")

    # Long at bottom same footer inset
    if abs(long_bottom["gaps"]["footer_to_ih"] - EXPECTED) > TOL:
        errors.append(f"long footer inset {long_bottom['gaps']['footer_to_ih']} != {EXPECTED}")
    if abs(short_closed["gaps"]["footer_to_ih"] - long_bottom["gaps"]["footer_to_ih"]) > TOL:
        errors.append("short/long footer inset mismatch")

    # Sidebar geometry independent of page length
    for label, snap in (("short_open", short_open), ("long_open", long_open)):
        if not snap["navOpen"]:
            errors.append(f"{label}: body.nav-open missing (fixture/prod parity)")
        if abs(snap["gaps"]["side_to_ih"]) > TOL:
            errors.append(f"{label}: side gap {snap['gaps']['side_to_ih']}")
        if abs(snap["gaps"]["back_to_ih"]) > TOL:
            errors.append(f"{label}: backdrop gap {snap['gaps']['back_to_ih']}")
        if snap["gaps"]["side_vs_back"] > TOL:
            errors.append(f"{label}: side/backdrop delta")
        if snap["sideTransform"] != "none":
            errors.append(f"{label}: side transform must be none")
        if snap["sidePadBottom"] not in ("0px", "0"):
            errors.append(f"{label}: side padding-bottom must be 0")
        sf_inset = snap["gaps"]["sideFoot_content_to_ih"]
        if sf_inset is None or abs(sf_inset - EXPECTED) > TOL:
            errors.append(f"{label}: side-foot content inset {sf_inset} != {EXPECTED}")
        if abs(sf_inset - snap["gaps"]["footer_to_ih"]) > TOL:
            errors.append(f"{label}: side-foot vs main footer mismatch")

    if abs(short_open["sideBottom"] - long_open["sideBottom"]) > TOL:
        errors.append(
            f"short page altered sidebar bottom ({short_open['sideBottom']} vs {long_open['sideBottom']})"
        )

    out["passed"] = not errors
    out["errors"] = errors
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        raise SystemExit(1)
    print("SHARED_GEOMETRY_PASSED", file=sys.stderr)


if __name__ == "__main__":
    main()
