#!/usr/bin/env python3
"""Full mobile scroll journey: first load → scroll → bottom → top (short + long)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
MEASURE_JS = (ROOT / "tests/fixtures/mobile_scroll_measure.js").read_text(encoding="utf-8")
FIXTURES = {
    "short": ROOT / "tests/fixtures/mobile_shell_probe.html",
    "long": ROOT / "tests/fixtures/mobile_shell_probe_long.html",
}
VIEWPORT = {"width": 390, "height": 844}
LAYOUT_VH = 844
VISUAL_VH = 720
FOOT_GAP = 16.0
SAFE_BOTTOM = 34.0
TOL = 2.0


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


def inject_measure(page) -> None:
    page.evaluate(MEASURE_JS)


def measure(page, step: str) -> dict:
    return page.evaluate("(step) => window.__mobileScrollMeasure(step)", step)


def run_journey(page, label: str) -> dict:
    steps: dict[str, dict] = {}

    stub_visual_viewport(page, VISUAL_VH)
    steps["first_load"] = measure(page, f"{label}_first_load")
    steps["before_scroll"] = measure(page, f"{label}_before_scroll")

    page.evaluate("() => window.scrollTo(0, 8)")
    steps["after_small_scroll"] = measure(page, f"{label}_after_small_scroll")

    page.evaluate(
        """() => {
      const max = Math.max(
        document.documentElement.scrollHeight - window.innerHeight,
        0
      );
      window.scrollTo(0, max);
    }"""
    )
    steps["at_bottom"] = measure(page, f"{label}_at_bottom")

    page.evaluate("() => window.scrollTo(0, 0)")
    steps["back_to_top"] = measure(page, f"{label}_back_to_top")

    page.locator("#menu-toggle").click()
    page.wait_for_timeout(200)
    steps["sidebar_open"] = measure(page, f"{label}_sidebar_open")

    page.locator("#menu-toggle").click()
    page.wait_for_timeout(200)
    steps["sidebar_closed"] = measure(page, f"{label}_sidebar_closed")

    return steps


def assert_journey(name: str, steps: dict[str, dict], is_long: bool) -> list[str]:
    errors: list[str] = []
    first = steps["first_load"]
    after_scroll = steps["after_small_scroll"]
    at_bottom = steps["at_bottom"]
    back = steps["back_to_top"]

    owners = first["scrollOwners"]
    if owners["mainIsScroller"]:
        errors.append(f"{name}: .main must not be vertical scroller")
    if not owners["documentScrolls"]:
        errors.append(f"{name}: document must be vertical scroller")
    if owners["mainScrollTop"] not in (0, None):
        errors.append(f"{name}: .main scrollTop must stay 0")

    shell_h = first["shell"]["height"]
    shell_min = first["shell"]["minHeight"]
    for unit in ("dvh", "svh", "lvh", "vh"):
        if unit in shell_h or unit in shell_min:
            errors.append(f"{name}: shell uses viewport unit {unit!r}")

    def invariant(step_a: dict, step_b: dict, label: str) -> None:
        if abs(step_a["shell"]["rect"]["height"] - step_b["shell"]["rect"]["height"]) > TOL:
            errors.append(f"{name}: shell height changed {label}")
        for key in (
            "footer_to_mainBottom",
            "mainBottom_to_shellBottom",
            "footer_to_shellBottom",
            "blankBelowFooterInsideShell",
        ):
            a = step_a["gaps"].get(key)
            b = step_b["gaps"].get(key)
            if a is not None and b is not None and abs(a - b) > TOL:
                errors.append(f"{name}: {key} changed {label} ({a} → {b})")

    invariant(first, after_scroll, "after first scroll")

    gap_before = first["gaps"]["footer_to_mainBottom"]
    gap_after = after_scroll["gaps"]["footer_to_mainBottom"]
    if gap_before is not None and abs(gap_before - FOOT_GAP) > TOL:
        errors.append(f"{name}: footer→main gap on load {gap_before} != {FOOT_GAP}")
    if gap_after is not None and abs(gap_after - FOOT_GAP) > TOL:
        errors.append(f"{name}: footer→main gap after scroll {gap_after} != {FOOT_GAP}")

    blank = first["gaps"]["blankBelowFooterInsideShell"]
    if blank is not None and blank > FOOT_GAP + TOL:
        errors.append(f"{name}: artificial blank below footer on load: {blank}px")

    main_shell = first["gaps"]["mainBottom_to_shellBottom"]
    if main_shell is not None and abs(main_shell - SAFE_BOTTOM) > TOL:
        errors.append(f"{name}: main→shell gap {main_shell} != safe-bottom {SAFE_BOTTOM}")

    if is_long:
        if at_bottom["docScrollTop"] <= 0:
            errors.append(f"{name}: document did not scroll on long page")
        footer_vis = at_bottom["footer"]["rect"]["bottom"]
        layout_bottom = at_bottom["innerHeight"]
        if footer_vis > layout_bottom + TOL:
            errors.append(
                f"{name}: footer not reachable at bottom scroll "
                f"(footer={footer_vis}, layoutViewport={layout_bottom})"
            )
        invariant(first, at_bottom, "at scroll bottom")
    else:
        shell_vis_before = first["gaps"]["shellBottom_to_visualViewportBottom"]
        shell_vis_after = after_scroll["gaps"]["shellBottom_to_visualViewportBottom"]
        if shell_vis_before is not None and shell_vis_after is not None:
            if abs(shell_vis_after - shell_vis_before) > TOL:
                errors.append(
                    f"{name}: shell/visual gap changed after scroll "
                    f"({shell_vis_before} → {shell_vis_after})"
                )

    invariant(first, back, "after scroll round-trip")

    open_step = steps["sidebar_open"]
    if open_step["scrollOwners"]["mainIsScroller"]:
        errors.append(f"{name}: sidebar open must not nest scroll on .main")

    return errors


def main() -> None:
    results: dict = {"viewport": VIEWPORT, "visual_vh": VISUAL_VH, "journeys": {}}
    all_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, fixture in FIXTURES.items():
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
            page.goto(fixture.resolve().as_uri(), wait_until="networkidle")
            inject_measure(page)
            steps = run_journey(page, name)
            page.close()
            results["journeys"][name] = steps
            all_errors.extend(assert_journey(name, steps, is_long=(name == "long")))

        browser.close()

    results["passed"] = not all_errors
    results["errors"] = all_errors
    print(json.dumps(results, ensure_ascii=False, indent=2))

    if all_errors:
        for err in all_errors:
            print(err, file=sys.stderr)
        raise SystemExit(1)
    print("SCROLL_JOURNEY_PASSED", file=sys.stderr)


if __name__ == "__main__":
    main()
