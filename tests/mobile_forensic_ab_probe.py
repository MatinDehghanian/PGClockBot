#!/usr/bin/env python3
"""A/B forensic: shared short-page + sidebar gap = html fixed containing block.

Chromium does not treat overflow≠visible on html as a fixed CB (WebKit does).
We prove the SHARED MECHANISM with a transform CB (honored by Chromium), and
prove the CSS-axis coupling that forces html overflow-y:auto in this codebase.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHORT = ROOT / "tests/fixtures/mobile_shell_probe.html"
VIEWPORT = {"width": 390, "height": 844}
IH = VIEWPORT["height"]
SHORT_H = 800
EXPECTED_GAP = IH - SHORT_H  # 44


MEASURE = """() => {
  const r = el => { const b = el.getBoundingClientRect(); return {bottom:b.bottom,height:b.height}; };
  const cs = (el,p)=> getComputedStyle(el).getPropertyValue(p).trim();
  const html = document.documentElement;
  const body = document.body;
  const shell = document.querySelector('.shell');
  const side = document.querySelector('.side');
  const back = document.querySelector('.side-backdrop');
  const footer = document.querySelector('.site-footer');
  const ih = window.innerHeight;
  return {
    ih,
    htmlOverflowX: cs(html,'overflow-x'),
    htmlOverflowY: cs(html,'overflow-y'),
    bodyOverflowX: cs(body,'overflow-x'),
    bodyOverflowY: cs(body,'overflow-y'),
    htmlBottom: r(html).bottom,
    shellBottom: r(shell).bottom,
    sideBottom: r(side).bottom,
    backBottom: r(back).bottom,
    footerBottom: r(footer).bottom,
    gaps: {
      html_to_ih: ih - r(html).bottom,
      shell_to_ih: ih - r(shell).bottom,
      side_to_ih: ih - r(side).bottom,
      back_to_ih: ih - r(back).bottom,
    },
  };
}"""


def main() -> None:
    errors: list[str] = []
    out: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # --- 1) Overflow-axis coupling (why overflow-y:visible alone fails) ---
        page = browser.new_page(viewport=VIEWPORT)
        page.goto("about:blank")
        coupling = page.evaluate(
            """() => {
          const probe = (css) => {
            const s = document.createElement('style');
            s.textContent = 'html{' + css + '}';
            document.head.appendChild(s);
            const cs = getComputedStyle(document.documentElement);
            const out = {css, x: cs.overflowX, y: cs.overflowY};
            s.remove();
            return out;
          };
          return {
            hidden_x_visible_y: probe('overflow-x:hidden;overflow-y:visible'),
            both_visible: probe('overflow-x:visible;overflow-y:visible'),
            shorthand_visible: probe('overflow:visible'),
          };
        }"""
        )
        page.close()
        out["overflow_axis_coupling"] = coupling
        if coupling["hidden_x_visible_y"]["y"] != "auto":
            errors.append("expected overflow-x:hidden to force overflow-y:auto")
        if coupling["both_visible"]["y"] != "visible" or coupling["both_visible"]["x"] != "visible":
            errors.append("expected both-visible to compute visible/visible")

        # --- 2) Shared mechanism via transform CB (Chromium analog of WebKit) ---
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        page.add_style_tag(
            content=f"""
          html {{
            transform: translate3d(0,0,0) !important;
            height: {SHORT_H}px !important;
            max-height: {SHORT_H}px !important;
            min-height: 0 !important;
            overflow: hidden !important;
          }}
          html body {{ min-height: 0 !important; height: {SHORT_H}px !important; }}
          .shell {{ flex: none !important; height: {SHORT_H}px !important; min-height: 0 !important; }}
        """
        )
        page.locator("#menu-toggle").click()
        page.wait_for_timeout(200)
        shared = page.evaluate(MEASURE)
        page.close()
        out["shared_cb_mechanism"] = shared
        if abs(shared["gaps"]["side_to_ih"] - EXPECTED_GAP) > 1:
            errors.append(f"CB: side gap {shared['gaps']['side_to_ih']} != {EXPECTED_GAP}")
        if abs(shared["gaps"]["shell_to_ih"] - EXPECTED_GAP) > 1:
            errors.append(f"CB: shell gap {shared['gaps']['shell_to_ih']} != {EXPECTED_GAP}")
        if abs(shared["gaps"]["side_to_ih"] - shared["gaps"]["shell_to_ih"]) > 1:
            errors.append("CB: side/shell gaps differ — not a shared cause")

        # --- 3) Target model: html visible both axes → sidebar independent of shell ---
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        page.add_style_tag(
            content=f"""
          html:has(.shell) {{
            height: auto !important;
            overflow-x: visible !important;
            overflow-y: visible !important;
            transform: none !important;
          }}
          html:has(.shell) body {{
            overflow-x: hidden !important;
            overflow-y: auto !important;
          }}
          .shell {{
            flex: none !important;
            height: {SHORT_H}px !important;
            max-height: {SHORT_H}px !important;
            min-height: 0 !important;
          }}
        """
        )
        page.locator("#menu-toggle").click()
        page.wait_for_timeout(200)
        fixed = page.evaluate(MEASURE)
        page.close()
        out["target_model"] = fixed
        if fixed["htmlOverflowY"] != "visible" or fixed["htmlOverflowX"] != "visible":
            errors.append(
                f"target: html overflow must be visible/visible "
                f"(got {fixed['htmlOverflowX']}/{fixed['htmlOverflowY']})"
            )
        if abs(fixed["gaps"]["side_to_ih"]) > 1:
            errors.append(f"target: side must pin to viewport, gap={fixed['gaps']['side_to_ih']}")
        if abs(fixed["gaps"]["back_to_ih"]) > 1:
            errors.append(f"target: backdrop must pin to viewport, gap={fixed['gaps']['back_to_ih']}")
        if abs(fixed["gaps"]["shell_to_ih"] - EXPECTED_GAP) > 1:
            errors.append("target: shell should stay short (proves independence)")

        # --- 4) Live stylesheet: html must compute visible/visible after real CSS ---
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        live = page.evaluate(MEASURE)
        page.locator("#menu-toggle").click()
        page.wait_for_timeout(200)
        live_open = page.evaluate(MEASURE)
        page.close()
        browser.close()
        out["live_css"] = {"closed": live, "open": live_open}
        if live["htmlOverflowX"] != "visible" or live["htmlOverflowY"] != "visible":
            errors.append(
                f"live CSS: html overflow must be visible/visible "
                f"(got {live['htmlOverflowX']}/{live['htmlOverflowY']}) — "
                "global overflow-x:hidden is still coupling axes"
            )
        if live["bodyOverflowY"] not in ("auto", "scroll"):
            errors.append(f"live CSS: body must be scrollport, got {live['bodyOverflowY']}")
        if abs(live_open["gaps"]["side_to_ih"]) > 1:
            errors.append(f"live open side gap {live_open['gaps']['side_to_ih']}")

    proof = {
        "root_cause": (
            "Global html overflow-x:hidden couples overflow-y to auto; "
            "WebKit uses that as fixed containing block; short-page html "
            "height:100% fill then places shell AND fixed sidebar on the same "
            "non-viewport bottom → one shared gap."
        ),
        "gap_between": "visible viewport bottom (innerHeight) vs html fixed-CB bottom",
        "why_long_ok": "long content/scroll masks html-vs-visual mismatch",
        "why_pwa_normal_ok": "tall content same as long page",
        "why_short_breaks_both": "shell bottom and sidebar bottom share html CB",
        "minimal_fix": "html overflow visible on BOTH axes; body alone scrolls + clips x",
        "chromium_note": (
            "Chromium does not use overflow on html as fixed CB; transform CB "
            "proves the shared mechanism. Real iPhone Safari/PWA not available in CI."
        ),
        "shared_cause_proven": abs(shared["gaps"]["side_to_ih"] - shared["gaps"]["shell_to_ih"]) <= 1
        and abs(shared["gaps"]["side_to_ih"] - EXPECTED_GAP) <= 1
        and abs(fixed["gaps"]["side_to_ih"]) <= 1
        and live["htmlOverflowY"] == "visible",
    }
    out["proof"] = proof
    out["passed"] = not errors
    out["errors"] = errors
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        raise SystemExit(1)
    print("FORENSIC_AB_PASSED", file=sys.stderr)


if __name__ == "__main__":
    main()
