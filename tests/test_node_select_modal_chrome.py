"""Node meter colors = gauge tones; rounded focus; modal scrollbar clipped."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"


class NodeMeterMatchesGaugeTests(unittest.TestCase):
    def test_meter_uses_same_tokens_as_gauge(self):
        css = CSS.read_text(encoding="utf-8")
        gauge = css[css.find(".home-gauge-val {") : css.find(".home-gauge-warn")]
        self.assertIn("stroke: var(--ok-fg)", gauge)
        self.assertIn(".home-gauge-warn .home-gauge-val { stroke: var(--warn-fg); }", css)
        self.assertIn(".home-gauge-caution .home-gauge-val { stroke: var(--caution-fg", css)
        self.assertIn(".home-gauge-err .home-gauge-val { stroke: var(--destructive-fg); }", css)
        self.assertIn(".home-gauge-neutral .home-gauge-val { stroke: var(--muted-fg); }", css)

        fill = css[css.find(".pg-node-meter-fill {") : css.find(".pg-node-meter-ok")]
        self.assertIn("background: var(--ok-fg)", fill)
        self.assertIn("opacity: 1", fill)
        self.assertNotIn("opacity: 0.62", fill)
        self.assertIn(".pg-node-meter-ok .pg-node-meter-fill { background: var(--ok-fg); }", css)
        self.assertIn(".pg-node-meter-warn .pg-node-meter-fill { background: var(--warn-fg); }", css)
        self.assertIn(".pg-node-meter-caution .pg-node-meter-fill { background: var(--caution-fg", css)
        self.assertIn(".pg-node-meter-err .pg-node-meter-fill { background: var(--destructive-fg); }", css)
        neutral = css[
            css.find(".pg-node-meter-neutral .pg-node-meter-fill") : css.find(
                ".pg-node-meter-neutral .pg-node-meter-fill"
            )
            + 160
        ]
        self.assertIn("background: var(--muted-fg)", neutral)
        track = css[css.find(".pg-node-meter-track {") : css.find(".pg-node-meter-fill {")]
        self.assertIn("color-mix(in srgb, var(--muted-fg) 18%, transparent)", track)


class RoundedFocusChromeTests(unittest.TestCase):
    def test_focus_uses_box_shadow_not_sharp_outline(self):
        css = CSS.read_text(encoding="utf-8")
        marker = (
            "input:focus-visible, select:focus-visible, textarea:focus-visible, "
            "button:focus-visible, a:focus-visible {"
        )
        self.assertIn(marker, css)
        block = css.split(marker, 1)[1].split("}", 1)[0]
        self.assertIn("outline: none", block)
        self.assertIn("box-shadow:", block)
        self.assertNotIn("outline-offset", block)
        self.assertIn(".ui-select-toggle:active", css)
        self.assertIn("border-radius: var(--control-radius)", css)
        self.assertIn(
            ".btn-color-card .ui-select[data-tone] .ui-select-toggle:active",
            css,
        )


class ModalScrollbarClipTests(unittest.TestCase):
    def test_panel_clips_inner_scroll_shell(self):
        css = CSS.read_text(encoding="utf-8")
        panel = css[css.find(".ui-modal-panel {") : css.find(".ui-modal-scroll {")]
        self.assertIn("overflow: hidden", panel)
        self.assertNotIn("overflow: auto", panel)
        self.assertIn(".ui-modal-scroll {", css)
        scroll = css[css.find(".ui-modal-scroll {") : css.find(".ui-modal-panel-lg")]
        self.assertIn("overflow-y: auto", scroll)
        js = JS.read_text(encoding="utf-8")
        self.assertIn("ensureModalScrollShell", js)
        self.assertIn("ui-modal-scroll", js)
        self.assertIn("modalScrollRoot", js)


if __name__ == "__main__":
    unittest.main()
