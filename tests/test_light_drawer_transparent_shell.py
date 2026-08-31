"""Light theme: closed mobile drawer must not leave a white slab.

Root cause (v8.8.1–v8.8.2): an unscoped
`html[data-theme=light] .side { background:#fff }` later in panel.css beat the
mobile transparent-shell rules (equal/higher specificity, later source order)
and painted a fixed drawer-width white box over the page while closed.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from css_blocks import at_rule, rule


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_WS = re.compile(r"\s+")


def _blank_comments(css: str) -> str:
    return _COMMENT.sub(lambda m: " " * len(m.group(0)), css)


def _top_level_rule_bodies(css: str, selector: str) -> list[tuple[int, str]]:
    """Bodies of top-level blocks whose prelude equals `selector` (not nested)."""
    scan = _blank_comments(css)
    want = _WS.sub(" ", selector).strip()
    out: list[tuple[int, str]] = []
    depth = 0
    start = 0
    i = 0
    while i < len(scan):
        ch = scan[i]
        if ch == "{":
            if depth == 0:
                prelude = _WS.sub(" ", css[start:i]).strip()
                if prelude == want:
                    # collect body
                    open_at = i
                    d = 0
                    for j in range(open_at, len(scan)):
                        if scan[j] == "{":
                            d += 1
                        elif scan[j] == "}":
                            d -= 1
                            if d == 0:
                                out.append((open_at, css[open_at + 1 : j]))
                                break
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                start = i + 1
        elif ch == ";" and depth == 0:
            start = i + 1
        i += 1
    return out


def _declares_opaque_background(body: str) -> bool:
    """True if the rule sets a non-transparent background / background-color."""
    scan = _blank_comments(body)
    for m in re.finditer(
        r"(?:^|;)\s*(background(?:-color)?)\s*:\s*([^;]+)",
        scan,
        re.IGNORECASE | re.MULTILINE,
    ):
        value = m.group(2).strip().lower()
        if value in ("transparent", "none", "initial", "inherit", "unset"):
            continue
        if "transparent" in value and "gradient" not in value:
            # e.g. color-mix(..., transparent) — still may paint; treat as opaque
            # only when a solid color is clearly intended.
            if value == "transparent":
                continue
        # Any explicit color / var / mix counts as paint on the shell.
        return True
    return False


class LightThemeClosedDrawerTests(unittest.TestCase):
    def test_mobile_side_shell_is_transparent(self):
        css = CSS.read_text(encoding="utf-8-sig")
        mobile = at_rule(css, "@media (max-width: 900px)")
        side = rule(mobile, ".side")
        self.assertIn("background: transparent;", side)
        self.assertIn("background-color: transparent;", side)
        # Closed drawer still slides via .side-panel (which keeps bg-card paint).
        panel = rule(mobile, ".side-panel")
        self.assertIn("background: var(--bg-card);", panel)
        self.assertIn("transform: translate3d(calc(100% + 24px), 0, 0);", panel)

    def test_no_unscoped_light_side_opaque_background(self):
        """Cascade guard: unscoped light .side must never paint opaque.

        Desktop light sidebar already uses `.side { background: var(--bg-card) }`
        with `--bg-card: #ffffff`. A later unscoped light `.side { #fff }` overrides
        the mobile transparent shell and recreates the white slab.
        """
        css = CSS.read_text(encoding="utf-8-sig")
        hits = _top_level_rule_bodies(css, 'html[data-theme="light"] .side')
        opaque = [(pos, body) for pos, body in hits if _declares_opaque_background(body)]
        self.assertEqual(
            opaque,
            [],
            "unscoped html[data-theme=light] .side must not set an opaque "
            "background (desktop uses var(--bg-card); mobile shell must stay "
            "transparent). Offending bodies: %r"
            % [body.strip() for _, body in opaque],
        )

    def test_light_bg_card_still_white_for_desktop_side(self):
        css = CSS.read_text(encoding="utf-8-sig")
        light = rule(css, 'html[data-theme="light"]')
        self.assertIn("--bg-card: #ffffff;", light)
        base_side = rule(css, ".side")
        self.assertIn("background: var(--bg-card);", base_side)


if __name__ == "__main__":
    unittest.main()
