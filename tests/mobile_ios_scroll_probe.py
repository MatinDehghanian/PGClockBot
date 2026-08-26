#!/usr/bin/env python3
"""Measure mobile layout BEFORE vs AFTER first scroll (iOS visual viewport proxy)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/mobile_ios_scroll_probe.html"
VIEWPORT = {"width": 390, "height": 844}
LAYOUT_VH = 844
VISUAL_VH = 720


def measure(page, label: str) -> dict:
    return page.evaluate(f"() => window.__measureGeometry({json.dumps(label)})")


def stub_visual_viewport(page, visual_h: int) -> None:
    page.evaluate(
        """(visualH) => {
      if (window.visualViewport) {
        Object.defineProperty(window.visualViewport, 'height', { configurable: true, get: () => visualH });
        Object.defineProperty(window.visualViewport, 'offsetTop', { configurable: true, get: () => 0 });
      }
    }""",
        visual_h,
    )


def simulate_nested_dvh_shell(page, layout_h: int) -> None:
    page.evaluate(
        """(layoutH) => {
      const shell = document.querySelector('.shell');
      if (shell) {
        shell.style.height = layoutH + 'px';
        shell.style.maxHeight = layoutH + 'px';
      }
    }""",
        layout_h,
    )


def simulate_dvh_recalc(page, h: int) -> None:
    page.evaluate(
        """(h) => {
      const shell = document.querySelector('.shell');
      if (shell) {
        shell.style.height = h + 'px';
        shell.style.maxHeight = h + 'px';
      }
    }""",
        h,
    )


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(FIXTURE.resolve().as_uri(), wait_until="networkidle")

        nested = page.locator(".main").evaluate(
            "el => ['auto','scroll'].includes(getComputedStyle(el).overflowY)"
        )
        stub_visual_viewport(page, VISUAL_VH)

        if nested:
            simulate_nested_dvh_shell(page, LAYOUT_VH)
            before = measure(page, "nested_before")
            page.locator(".main").evaluate("el => { el.scrollTop = 8; }")
            simulate_dvh_recalc(page, VISUAL_VH + 60)
            after = measure(page, "nested_after")
        else:
            before = measure(page, "document_before")
            page.evaluate("() => window.scrollTo(0, 8)")
            after = measure(page, "document_after")

        browser.close()

    shell_delta = abs(before["shell"]["rect"]["bottom"] - after["shell"]["rect"]["bottom"])
    footer_delta = abs(before["footer"]["rect"]["bottom"] - after["footer"]["rect"]["bottom"])
    gap_before = before["gaps"]["footerBottom_to_visualViewportBottom"]
    gap_after = after["gaps"]["footerBottom_to_visualViewportBottom"]
    gap_delta = None if gap_before is None or gap_after is None else gap_after - gap_before

    out = {
        "nested_main_scroller": nested,
        "before": before,
        "after": after,
        "analysis": {
            "shell_bottom_delta_px": shell_delta,
            "footer_bottom_delta_px": footer_delta,
            "footer_to_visual_gap_before": gap_before,
            "footer_to_visual_gap_after": gap_after,
            "gap_delta": gap_delta,
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    if nested:
        if gap_delta is not None and gap_delta < -10:
            print("NESTED_MODEL: gap shrinks after dvh recalc (bug reproduced)", file=sys.stderr)
        sys.exit(0)

    if shell_delta <= 1 and footer_delta <= 1 and (gap_delta is None or abs(gap_delta) <= 2):
        print("DOCUMENT_SCROLL_STABLE: shell/footer/gap unchanged after first scroll", file=sys.stderr)
        sys.exit(0)

    raise SystemExit(
        f"UNSTABLE: shell_delta={shell_delta} footer_delta={footer_delta} gap_delta={gap_delta}"
    )


if __name__ == "__main__":
    main()
