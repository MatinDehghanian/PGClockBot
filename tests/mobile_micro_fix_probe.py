#!/usr/bin/env python3
"""Micro-fix probes: sidebar bottom alignment + short-page footer flow."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHORT = ROOT / "tests/fixtures/mobile_shell_probe.html"
VIEWPORT = {"width": 390, "height": 844}
SAFE_BOTTOM = 34.0
FOOT_GAP = 16.0
TOL = 2.0


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(SHORT.resolve().as_uri(), wait_until="networkidle")
        page.evaluate(
            """() => {
          Object.defineProperty(window.visualViewport, 'height', { configurable: true, get: () => 720 });
          Object.defineProperty(window.visualViewport, 'offsetTop', { configurable: true, get: () => 0 });
        }"""
        )

        closed = page.evaluate("""() => {
          const shell = document.querySelector('.shell');
          const footer = document.querySelector('.site-footer');
          const last = document.querySelector('[data-probe-last]');
          const cs = (el,p)=> getComputedStyle(el).getPropertyValue(p).trim();
          const r = el => el.getBoundingClientRect();
          const shellR = r(shell); const footR = r(footer); const lastR = r(last);
          return {
            docScrollHeight: document.documentElement.scrollHeight,
            docClientHeight: document.documentElement.clientHeight,
            maxScroll: Math.max(0, document.documentElement.scrollHeight - document.documentElement.clientHeight),
            shellBottom: shellR.bottom,
            footerBottom: footR.bottom,
            contentToFooter: footR.top - lastR.bottom,
            footerToShell: shellR.bottom - footR.bottom,
            belowFooterInsideShell: shellR.bottom - footR.bottom - parseFloat(cs(shell,'padding-bottom')||0),
            footerMarginTop: cs(footer,'margin-top'),
            mainFlex: cs(document.querySelector('.main'),'flex'),
          };
        }""")

        page.locator("#menu-toggle").click()
        page.wait_for_timeout(200)
        open_drawer = page.evaluate("""() => {
          const side = document.querySelector('.side');
          const back = document.querySelector('.side-backdrop');
          const cs = (el,p)=> getComputedStyle(el).getPropertyValue(p).trim();
          const r = el => el.getBoundingClientRect();
          const sideR = r(side); const backR = r(back);
          return {
            sideBottom: sideR.bottom,
            backdropBottom: backR.bottom,
            sideBackdropDelta: Math.abs(sideR.bottom - backR.bottom),
            sideToLayoutBottom: window.innerHeight - sideR.bottom,
            backdropToLayoutBottom: window.innerHeight - backR.bottom,
            sidePaddingBottom: cs(side,'padding-bottom'),
          };
        }""")
        browser.close()

    errors: list[str] = []
    if closed["maxScroll"] > 0:
        errors.append(f"short page scrollable blank area: maxScroll={closed['maxScroll']}")
    if closed["contentToFooter"] > 40:
        errors.append(f"flex spacer above footer: {closed['contentToFooter']}px")
    if abs(closed["belowFooterInsideShell"] - FOOT_GAP) > TOL:
        errors.append(f"below-footer inside shell: {closed['belowFooterInsideShell']} != {FOOT_GAP}")
    if abs(closed["footerToShell"] - (FOOT_GAP + SAFE_BOTTOM)) > TOL:
        errors.append(f"footer→shell: {closed['footerToShell']}")
    if closed["footerMarginTop"] not in ("0px", "0"):
        errors.append(f"footer margin-top should be 0, got {closed['footerMarginTop']}")
    if open_drawer["sideBackdropDelta"] > TOL:
        errors.append(f"sidebar/backdrop bottom mismatch: {open_drawer['sideBackdropDelta']}")
    if open_drawer["sideToLayoutBottom"] > TOL:
        errors.append(f"sidebar gap to layout bottom: {open_drawer['sideToLayoutBottom']}")
    if open_drawer["backdropToLayoutBottom"] > TOL:
        errors.append(f"backdrop gap to layout bottom: {open_drawer['backdropToLayoutBottom']}")
    if open_drawer["sidePaddingBottom"] != f"{int(SAFE_BOTTOM)}px":
        errors.append(f"sidebar safe-bottom stack: padding-bottom={open_drawer['sidePaddingBottom']}")

    out = {"closed_short_page": closed, "sidebar_open": open_drawer, "passed": not errors, "errors": errors}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        raise SystemExit(1)
    print("MICRO_FIX_PASSED", file=sys.stderr)


if __name__ == "__main__":
    main()
