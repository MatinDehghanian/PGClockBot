#!/usr/bin/env python3
"""Headless Playwright probe for mobile shell geometry (iPhone-like viewport)."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "tests/fixtures/mobile_shell_probe.html"
VIEWPORT = {"width": 390, "height": 844}


def rect(page, sel: str) -> dict:
    box = page.locator(sel).bounding_box()
    if not box:
        return {"error": f"missing {sel}"}
    return {
        "top": round(box["y"], 1),
        "bottom": round(box["y"] + box["height"], 1),
        "height": round(box["height"], 1),
    }


def css(page, sel: str, prop: str) -> str:
    return page.locator(sel).evaluate(
        f"(el) => getComputedStyle(el).getPropertyValue('{prop}').trim()"
    )


def main() -> None:
    url = HTML.as_uri()
    out: dict = {"viewport": VIEWPORT, "url": url}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(url, wait_until="networkidle")

        topbar_h = float(css(page, ".topbar", "height").replace("px", "") or 0)
        shell = rect(page, ".shell")
        main = rect(page, ".main")
        footer = rect(page, ".site-footer")
        title = rect(page, ".page-head h1")

        page.locator("#menu-toggle").click()
        page.wait_for_timeout(300)
        side_open = rect(page, ".side.open")
        backdrop = rect(page, ".side-backdrop.show")

        browser.close()

    vh = VIEWPORT["height"]
    topbar_bottom = shell["top"] + topbar_h
    out.update(
        {
            "shell": shell,
            "main": main,
            "footer": footer,
            "title": title,
            "side_open": side_open,
            "backdrop": backdrop,
            "checks": {
                "title_below_topbar": title["top"] >= topbar_bottom - 2,
                "main_fills_to_bottom": abs(main["bottom"] - vh) <= 4,
                "footer_inside_main": footer["bottom"] <= main["bottom"] + 1,
                "footer_visible_above_viewport_bottom": footer["bottom"] <= vh,
                "side_open_reaches_bottom": abs(side_open["bottom"] - vh) <= 4,
                "no_gap_under_side": side_open["bottom"] >= vh - 4,
                "backdrop_reaches_bottom": abs(backdrop["bottom"] - vh) <= 4,
            },
        }
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    failed = [k for k, v in out["checks"].items() if not v]
    if failed:
        raise SystemExit(f"FAILED checks: {failed}")
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
