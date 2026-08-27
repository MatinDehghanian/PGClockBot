#!/usr/bin/env python3
"""First-paint gap regression: layout-100% fill vs 100svh fill.

Proves the tablet/Safari symptom mechanism and that live CSS uses 100svh.
Chromium headless has svh==ih, so the visual-fold case is exercised via
explicit min-height overrides matching measured visual heights.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHORT = ROOT / "tests/fixtures/mobile_shell_probe.html"
CSS = ROOT / "app/web/static/panel.css"
VIEWPORT = {"width": 390, "height": 844}
VISUAL = 720
TOL = 2.0

MEAS = """() => {
  const r = el => el.getBoundingClientRect();
  const vv = window.visualViewport;
  const ih = window.innerHeight;
  const vvh = vv ? vv.height : ih;
  const footer = document.querySelector('.site-footer');
  const shell = document.querySelector('.shell');
  const html = document.documentElement;
  const body = document.body;
  return {
    ih, vvh,
    htmlMinH: getComputedStyle(html).minHeight,
    bodyMinH: getComputedStyle(body).minHeight,
    htmlH: getComputedStyle(html).height,
    shellH: r(shell).height,
    footerBottom: r(footer).bottom,
    footer_below_visual: r(footer).bottom - vvh,
    shell_to_visual: vvh - r(shell).bottom,
    bodyOY: getComputedStyle(body).overflowY,
    mainOY: getComputedStyle(document.querySelector('.main')).overflowY,
  };
}"""


def stub_vv(page, h: float) -> None:
    page.evaluate(
        """(h) => {
      if (!window.visualViewport) return;
      Object.defineProperty(window.visualViewport, 'height', {configurable:true, get:() => h});
      Object.defineProperty(window.visualViewport, 'offsetTop', {configurable:true, get:() => 0});
    }""",
        h,
    )


def main() -> None:
    errors: list[str] = []
    css = CSS.read_text(encoding="utf-8")
    mobile = css.split("@media (max-width: 900px)", 1)[1]
    html_rule = mobile.split("html:has(.shell) {\n", 1)[1].split("}", 1)[0]
    body_rule = mobile.split("html:has(.shell) body {\n", 1)[1].split("}", 1)[0]
    if "min-height: 100svh;" not in html_rule or "height: auto;" not in html_rule:
        errors.append("html must use height:auto + min-height:100svh (not height:100%)")
    import re
    if re.search(r"(?m)^\s*height:\s*100%;", html_rule):
        errors.append("html must not use height:100% (layout ICB fill)")
    if "min-height: 100svh;" not in body_rule:
        errors.append("body must use min-height:100svh")
    if "overflow-y: auto;" in body_rule:
        errors.append("body must not be overflow-y:auto (fixed CB regression)")

    out: dict = {"css_ok": not errors}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        stub_vv(page, VISUAL)

        # Broken model: fill to layout 100%/844 while vv=720
        page.add_style_tag(
            content=f"""
          @media (max-width: 900px) {{
            html:has(.shell) {{ height: {VIEWPORT['height']}px !important; min-height: 0 !important; }}
            html:has(.shell) body {{ min-height: {VIEWPORT['height']}px !important; }}
          }}
        """
        )
        page.wait_for_timeout(30)
        broken = page.evaluate(MEAS)
        page.close()

        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        stub_vv(page, VISUAL)
        # Fixed model stand-in: fill to visual (what 100svh is on real Safari with chrome)
        page.add_style_tag(
            content=f"""
          @media (max-width: 900px) {{
            html:has(.shell) {{ height: auto !important; min-height: {VISUAL}px !important; }}
            html:has(.shell) body {{ min-height: {VISUAL}px !important; }}
            .shell {{ min-height: {VISUAL}px !important; height: auto !important; }}
          }}
        """
        )
        page.wait_for_timeout(30)
        fixed = page.evaluate(MEAS)

        # Live CSS (chromium: svh==ih) — still must keep body not scrollport
        page2 = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page2.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        live = page2.evaluate(MEAS)
        page2.close()
        page.close()
        browser.close()

    out["broken"] = broken
    out["fixed"] = fixed
    out["live"] = live

    if broken["footer_below_visual"] < 20:
        errors.append(f"broken setup: expected footer below visual, got {broken['footer_below_visual']}")
    if fixed["footer_below_visual"] > TOL:
        errors.append(f"svh-stand-in: footer must not sit below visual (got {fixed['footer_below_visual']})")
    if live["bodyOY"] != "visible" or live["mainOY"] != "visible":
        errors.append("live: body/main must stay overflow-y visible")

    # Expanding vv without CSS change clears the broken gap (explains scroll-fixes-it)
    out["why_scroll_fixes"] = (
        "Under chrome-visible first paint, layout-sized fill parks footer below "
        "visual fold. Scroll hides chrome → visualViewport grows toward layout → "
        "gap disappears without CSS box resize."
    )

    out["passed"] = not errors
    out["errors"] = errors
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        raise SystemExit(1)
    print("FIRST_PAINT_GAP_PASSED", file=sys.stderr)


if __name__ == "__main__":
    main()
