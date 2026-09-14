"""Regression: CSP nonce injection + delete-reason extraction (v10 panel fixes)."""

from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from app.services.csp_nonce import buffer_and_inject_nonce, inject_script_nonces
from app.services.delete_reason import delete_reason_too_short, extract_delete_reason

ROOT = Path(__file__).resolve().parents[1]


class CspNonceInjectionTests(unittest.TestCase):
    def test_injects_nonce_on_scripts_without_one(self):
        html = (
            '<html><script>var a=1</script>'
            '<script src="/static/panel.js"></script>'
            '<script nonce="keep">var b=2</script>'
            '<script type="application/json">{"x":1}</script></html>'
        )
        out = inject_script_nonces(html, "abc123")
        self.assertIn('<script nonce="abc123">var a=1</script>', out)
        self.assertIn('src="/static/panel.js" nonce="abc123"', out)
        self.assertIn('<script nonce="keep">', out)
        self.assertIn('type="application/json" nonce="abc123"', out)

    def test_middleware_streaming_response_gets_nonce(self):
        app = FastAPI()

        @app.middleware("http")
        async def stamp(request: Request, call_next):
            response = await call_next(request)
            return await buffer_and_inject_nonce(response, "mid-nonce")

        @app.get("/page")
        async def page():
            return HTMLResponse(
                "<html><head></head><body><script>window.X=1</script></body></html>"
            )

        client = TestClient(app)
        r = client.get("/page")
        self.assertEqual(r.status_code, 200)
        self.assertIn('nonce="mid-nonce"', r.text)
        self.assertIn("<script nonce=\"mid-nonce\">window.X=1</script>", r.text)

    def test_app_middleware_imports_buffer_helper(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("buffer_and_inject_nonce", src)
        self.assertIn("csp_nonce", src)

    def test_defer_template_has_nonce_attr(self):
        defer = (ROOT / "app/web/templates/_panel_widgets_defer.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("csp_nonce", defer)
        self.assertIn("nonce=", defer)


class DeleteReasonExtractionTests(unittest.TestCase):
    def test_prefers_reason_then_confirm_reason(self):
        self.assertEqual(extract_delete_reason({"reason": "abc"}), "abc")
        self.assertEqual(
            extract_delete_reason({"reason": "", "confirm_reason": "حذف تست"}),
            "حذف تست",
        )
        self.assertEqual(extract_delete_reason({}), "")

    def test_too_short(self):
        self.assertTrue(delete_reason_too_short("ab"))
        self.assertFalse(delete_reason_too_short("abc"))
        self.assertFalse(delete_reason_too_short("حذف"))

    def test_users_delete_uses_helper(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("extract_delete_reason", src)
        self.assertIn("delete_reason_too_short", src)

    def test_panel_js_replaces_stale_reason_fields(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("Replace any prior empty/stale reason fields", js)
        self.assertIn("form.id === 'confirm-form'", js)
        self.assertIn("setCustomValidity", js)
        self.assertIn("علت حذف باید حداقل", js)


if __name__ == "__main__":
    unittest.main()
