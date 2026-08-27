#!/usr/bin/env python3
"""Headless Playwright probe for mobile shell geometry (iPhone-like viewport)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML = ROOT / "tests/fixtures/mobile_shell_probe.html"
VIEWPORT = {"width": 390, "height": 844}
FOOT_GAP = 16.0
SAFE_BOTTOM = 34.0


def rect(page, sel: str) -> dict:
    box = page.locator(sel).bounding_box()
    if not box:
        return {"error": f"missing {sel}"}
    return {
        "top": round(box["y"], 1),
        "bottom": round(box["y"] + box["height"], 1),
        "height": round(box["height"], 1),
    }


def measure(page) -> dict:
    return page.evaluate(
        """() => {
      const shell = document.querySelector('.shell');
      const main = document.querySelector('.main');
      const footer = document.querySelector('.site-footer');
      const cs = (el, p) => el ? getComputedStyle(el).getPropertyValue(p).trim() : '';
      const r = el => el ? el.getBoundingClientRect() : null;
      const vh = window.innerHeight;
      const shellR = r(shell);
      const mainR = r(main);
      const footerR = r(footer);
      return {
        innerHeight: vh,
        docClientHeight: document.documentElement.clientHeight,
        docScrollTop: document.documentElement.scrollTop || document.body.scrollTop,
        visualViewportHeight: window.visualViewport ? window.visualViewport.height : null,
        mainOverflowY: cs(main, 'overflow-y'),
        shell: {
          bottom: shellR ? shellR.bottom : null,
          paddingBottom: cs(shell, 'padding-bottom'),
        },
        main: {
          bottom: mainR ? mainR.bottom : null,
          scrollHeight: main ? main.scrollHeight : null,
          clientHeight: main ? main.clientHeight : null,
          scrollTop: main ? main.scrollTop : null,
          paddingBottom: cs(main, 'padding-bottom'),
          maxHeight: cs(main, 'max-height'),
          height: cs(main, 'height'),
        },
        footer: {
          bottom: footerR ? footerR.bottom : null,
        },
        gap_footer_to_main_bottom: mainR && footerR ? mainR.bottom - footerR.bottom : null,
        gap_shell_to_viewport: shellR ? vh - shellR.bottom : null,
        gap_main_to_shell_bottom: shellR && mainR ? shellR.bottom - mainR.bottom : null,
      };
    }"""
    )


def main() -> None:
    fixture = Path(os.environ.get("MOBILE_PROBE_FIXTURE", str(DEFAULT_HTML)))
    url = fixture.resolve().as_uri()
    out: dict = {"viewport": VIEWPORT, "url": url, "fixture": fixture.name}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(url, wait_until="networkidle")

        title = rect(page, ".page-head h1")
        short = measure(page)
        page.locator("#menu-toggle").click()
        page.wait_for_timeout(250)
        side_open = rect(page, ".side.open")

        is_long = "probe_long" in fixture.name
        long_bottom = None
        if is_long:
            page.evaluate(
                """() => {
              const max = Math.max(
                document.documentElement.scrollHeight - window.innerHeight,
                0
              );
              window.scrollTo(0, max);
            }"""
            )
            long_bottom = measure(page)

        browser.close()

    vh = VIEWPORT["height"]
    foot_to_main = short.get("gap_footer_to_main_bottom")
    shell_gap = short.get("gap_shell_to_viewport")
    main_shell_gap = short.get("gap_main_to_shell_bottom")
    tol = 2.0
    topbar_bottom = 99.0

    checks = {
        "title_below_topbar": title["top"] >= topbar_bottom - tol,
        "main_fills_shell_content_box": main_shell_gap is not None and abs(main_shell_gap - SAFE_BOTTOM) <= tol,
        "main_not_scroller": short.get("mainOverflowY") == "visible",
        "main_max_height_unbounded": short["main"]["maxHeight"] in ("none", ""),
        "side_open_reaches_bottom": abs(side_open["bottom"] - vh) <= 4,
    }
    if not is_long:
        checks["no_shell_viewport_gap"] = shell_gap is not None and abs(shell_gap) <= tol
        checks["footer_gap_is_foot_gap_only"] = (
            foot_to_main is not None and abs(foot_to_main - FOOT_GAP) <= tol
        )

    if is_long:
        if long_bottom is not None:
            foot_to_main = long_bottom.get("gap_footer_to_main_bottom")
            checks["long_document_scrolled"] = (long_bottom.get("docScrollTop") or 0) > 0
            checks["main_stays_non_scroller"] = long_bottom.get("main", {}).get("scrollTop", 0) == 0
            checks["footer_gap_is_foot_gap_only"] = (
                foot_to_main is not None and abs(foot_to_main - FOOT_GAP) <= tol
            )
            checks["no_extra_scroll_blank"] = checks["footer_gap_is_foot_gap_only"]
    else:
        checks["footer_gap_is_foot_gap_only"] = (
            foot_to_main is not None and abs(foot_to_main - FOOT_GAP) <= tol
        )

    out["title"] = title
    out["short"] = short
    out["side_open"] = side_open
    if long_bottom:
        out["long_bottom"] = long_bottom
    out["checks"] = checks

    print(json.dumps(out, ensure_ascii=False, indent=2))
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise SystemExit(f"FAILED checks: {failed}")
    print("ALL CHECKS PASSED", file=sys.stderr)


if __name__ == "__main__":
    main()
