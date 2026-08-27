#!/usr/bin/env python3
"""PWA short+sidebar regression: sidebar geometry must not depend on page length."""
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
      // Ancestor overflow between side and viewport (exclude side itself)
      let el = side.parentElement;
      const ancestorOverflow = [];
      while (el) {
        const ox = cs(el,'overflow-x'), oy = cs(el,'overflow-y');
        ancestorOverflow.push({tag: el.tagName.toLowerCase(), cls: (el.className||'').toString().slice(0,40), ox, oy});
        el = el.parentElement;
      }
      return {
        ih,
        navOpen: body.classList.contains('nav-open'),
        htmlOverflowX: cs(html,'overflow-x'),
        htmlOverflowY: cs(html,'overflow-y'),
        bodyOverflowX: cs(body,'overflow-x'),
        bodyOverflowY: cs(body,'overflow-y'),
        mainOverflowY: cs(main,'overflow-y'),
        shellOverflowX: cs(shell,'overflow-x'),
        shellOverflowY: cs(shell,'overflow-y'),
        sideTransform: cs(side,'transform'),
        ancestorOverflow,
        shellBottom: r(shell).bottom,
        footerBottom: r(footer).bottom,
        sideBottom: r(side).bottom,
        backBottom: r(back).bottom,
        sideFootContentBottom: sfR ? sfR.bottom - sfPad : null,
        footerPad: parseFloat(cs(footer,'padding-bottom')||0),
        footerContentBottom: r(footer).bottom - parseFloat(cs(footer,'padding-bottom')||0),
        gaps: {
          shell_to_ih: ih - r(shell).bottom,
          footer_content_to_ih: ih - (r(footer).bottom - parseFloat(cs(footer,'padding-bottom')||0)),
          footer_box_to_ih: ih - r(footer).bottom,
          side_to_ih: ih - r(side).bottom,
          back_to_ih: ih - r(back).bottom,
          side_vs_back: Math.abs(r(side).bottom - r(back).bottom),
          sideFoot_content_to_ih: sfR ? ih - (sfR.bottom - sfPad) : null,
        },
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
        # Stress: force shell shorter than viewport WHILE drawer open — sidebar must stay pinned
        page.add_style_tag(
            content="""
          .shell { flex: none !important; height: 780px !important; min-height: 0 !important; }
          html:has(.shell) body { min-height: 0 !important; height: auto !important; }
        """
        )
        page.wait_for_timeout(50)
        short_stressed = measure(page)
        page.close()

        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3)
        page.goto(LONG.resolve().as_uri(), wait_until="networkidle")
        long_top = measure(page)
        page.evaluate(
            """() => {
          const el = document.scrollingElement || document.documentElement;
          el.scrollTop = Math.max(0, el.scrollHeight - window.innerHeight);
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
        short_stressed=short_stressed,
        long_top=long_top,
        long_bottom=long_bottom,
        long_open=long_open,
    )

    for label, snap in (("short_closed", short_closed), ("long_bottom", long_bottom)):
        if snap["htmlOverflowY"] != "visible" or snap["htmlOverflowX"] != "visible":
            errors.append(f"{label}: html must be overflow visible/visible")
        if snap["bodyOverflowY"] != "visible" or snap["bodyOverflowX"] != "visible":
            errors.append(
                f"{label}: body must be overflow visible/visible "
                f"(got {snap['bodyOverflowX']}/{snap['bodyOverflowY']}) — "
                "body overflow-y:auto is the content-sized fixed CB"
            )
        if snap["mainOverflowY"] != "visible":
            errors.append(f"{label}: .main must not scroll")

    # No ancestor of .side (except possibly side) may be a vertical scrollport
    for label, snap in (("short_open", short_open), ("long_open", long_open)):
        for anc in snap["ancestorOverflow"]:
            if anc["tag"] in ("html", "body") and anc["oy"] not in ("visible", "clip"):
                errors.append(f"{label}: ancestor {anc['tag']} overflow-y={anc['oy']} (fixed CB risk)")
            if "shell" in (anc.get("cls") or "") and anc["oy"] not in ("visible", "clip"):
                errors.append(f"{label}: .shell overflow-y={anc['oy']} (content-sized fixed CB risk)")

    if abs(short_closed["gaps"]["shell_to_ih"]) > TOL:
        errors.append(f"short: shell_to_ih={short_closed['gaps']['shell_to_ih']}")
    if abs(short_closed["gaps"]["footer_content_to_ih"] - EXPECTED) > TOL:
        errors.append(f"short footer inset {short_closed['gaps']['footer_content_to_ih']} != {EXPECTED}")
    if abs(long_bottom["gaps"]["footer_content_to_ih"] - EXPECTED) > TOL:
        errors.append(f"long footer inset {long_bottom['gaps']['footer_content_to_ih']} != {EXPECTED}")
    if abs(short_closed["gaps"]["footer_content_to_ih"] - long_bottom["gaps"]["footer_content_to_ih"]) > TOL:
        errors.append("short/long footer inset mismatch")
    if abs(short_closed["gaps"]["footer_box_to_ih"]) > TOL:
        errors.append(f"short: footer box must reach layout bottom ({short_closed['gaps']['footer_box_to_ih']})")

    for label, snap in (("short_open", short_open), ("long_open", long_open), ("short_stressed", short_stressed)):
        if not snap["navOpen"]:
            errors.append(f"{label}: body.nav-open missing")
        if abs(snap["gaps"]["side_to_ih"]) > TOL:
            errors.append(f"{label}: side gap {snap['gaps']['side_to_ih']}")
        if abs(snap["gaps"]["back_to_ih"]) > TOL:
            errors.append(f"{label}: backdrop gap {snap['gaps']['back_to_ih']}")
        if snap["sideTransform"] != "none":
            errors.append(f"{label}: side transform must be none")
        sf_inset = snap["gaps"]["sideFoot_content_to_ih"]
        # Under stress shell is short — side-foot may not match main footer; side box must still hit ih
        if label != "short_stressed":
            if sf_inset is None or abs(sf_inset - EXPECTED) > TOL:
                errors.append(f"{label}: side-foot content inset {sf_inset} != {EXPECTED}")

    # PRIMARY: short page must not alter sidebar bottom vs long
    if abs(short_open["sideBottom"] - long_open["sideBottom"]) > TOL:
        errors.append(
            f"PWA-short clue FAILED: short altered sidebar bottom "
            f"({short_open['sideBottom']} vs {long_open['sideBottom']})"
        )
    # Stress: shell short must NOT pull sidebar up
    if abs(short_stressed["gaps"]["side_to_ih"]) > TOL:
        errors.append(
            f"PWA-short stress FAILED: undersized shell moved sidebar "
            f"(side_to_ih={short_stressed['gaps']['side_to_ih']}, shell_to_ih={short_stressed['gaps']['shell_to_ih']})"
        )
    if short_stressed["gaps"]["shell_to_ih"] < 20:
        errors.append("stress setup failed: shell should be undersized")

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
