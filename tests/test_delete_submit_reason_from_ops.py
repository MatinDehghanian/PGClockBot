"""Delete reason must survive POST from kebab ops AND user-edit modal.

Root causes covered:
1) Confirm stacked under edit (z-index) — bringModalToFront.
2) Ops kebab: panelConfirm → closeRowActions → menu display:none →
   native form.submit() drops fields on mobile WebKit → empty reason flash.
   Fix: submitFormPost() builds a body-level form with reason from JS memory.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app/web/static/panel.js"
CSS = ROOT / "app/web/static/panel.css"
USERS = ROOT / "app/web/templates/users.html"
USER_EDIT = ROOT / "app/web/templates/_user_edit_body.html"


def _fn_src(js: str, name: str) -> str:
    key = f"function {name}("
    start = js.find(key)
    if start < 0:
        raise AssertionError(f"missing {name}")
    i = js.find("{", start)
    depth = 0
    for j in range(i, len(js)):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[start : j + 1]
    raise AssertionError(f"unbalanced {name}")


def _run_node(script: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "proof.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(path)],
            cwd="/tmp",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr or proc.stdout or "node failed")
        return json.loads(proc.stdout)


class DeleteSubmitStaticTests(unittest.TestCase):
    def test_submit_form_post_helper_exists(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("function submitFormPost(", js)
        self.assertIn("window.panelSubmitFormPost = submitFormPost", js)
        body = _fn_src(js, "submitFormPost")
        self.assertIn("document.body.appendChild(tmp)", body)
        self.assertIn("tmp.submit()", body)

    def test_confirm_success_uses_submit_form_post_not_native(self):
        js = JS.read_text(encoding="utf-8")
        start = js.find("window.panelConfirm(opts).then")
        self.assertGreater(start, 0)
        # First then-handler (form submit intercept)
        block = js[start : start + 1100]
        self.assertIn("submitFormPost(form, overrides)", block)
        self.assertIn("overrides.confirm_reason", block)
        # Executable native submit must not remain in the confirm success path.
        code_only = "\n".join(
            ln for ln in block.splitlines() if not ln.strip().startswith("/*") and "*/" not in ln
        )
        self.assertNotIn("form.submit();", code_only)
        self.assertIn("submitFormPost(form, overrides);", code_only)

    def test_kebab_css_hides_unported_menu(self):
        """Documents the trap: un-ported menu is display:none (WebKit field drop)."""
        css = CSS.read_text(encoding="utf-8")
        block = css.split(".row-actions-menu:not(.is-ported) {", 1)[1].split("}", 1)[0]
        self.assertIn("display: none !important", block)

    def test_both_entry_points_require_reason(self):
        users = USERS.read_text(encoding="utf-8")
        delete = users.split('action="/users/{{ u.id }}/delete"', 1)[1].split("</form>", 1)[0]
        self.assertIn('data-confirm-reason="1"', delete)
        self.assertIn('name="reason"', delete)
        edit = USER_EDIT.read_text(encoding="utf-8")
        edel = edit.split('action="/users/{{ user.id }}/delete"', 1)[1].split("</form>", 1)[0]
        self.assertIn('data-confirm-reason="1"', edel)
        self.assertIn('name="reason"', edel)


class DeleteSubmitRuntimeProof(unittest.TestCase):
    def test_reason_survives_when_origin_form_is_display_none(self):
        """Simulate ops kebab after closeRowActions: form in display:none menu."""
        js_src = JS.read_text(encoding="utf-8")
        collect = _fn_src(js_src, "collectFormFields")
        submit = _fn_src(js_src, "submitFormPost")
        script = textwrap.dedent(
            """
            const { JSDOM } = require('jsdom');
            const dom = new JSDOM(`<!doctype html><html><body>
              <meta name="csrf-token" content="tok-abc" />
              <div class="row-actions">
                <div class="row-actions-menu" style="display:none !important;width:0;height:0;overflow:hidden">
                  <form id="del" method="post" action="/users/7/delete">
                    <input type="hidden" name="reason" value="" />
                    <button type="submit">حذف</button>
                  </form>
                </div>
              </div>
            </body></html>`, { url: 'https://example.test/users' });
            const { window } = dom;
            const { document } = window;
            function csrfToken(){ return 'tok-abc'; }
            __COLLECT__
            __SUBMIT__
            window.__posted = null;
            const orig = window.HTMLFormElement.prototype.submit;
            window.HTMLFormElement.prototype.submit = function(){
              const entries = [];
              this.querySelectorAll('input').forEach((el) => entries.push([el.name, el.value]));
              window.__posted = {
                parent: this.parentNode && this.parentNode.tagName,
                action: this.getAttribute('action'),
                entries,
              };
            };
            const form = document.getElementById('del');
            // Reason lives in JS memory (confirm result) — stamp via overrides.
            submitFormPost(form, {
              reason: 'تخلف تکرار شده',
              confirm_reason: 'تخلف تکرار شده',
            });
            const posted = window.__posted;
            const map = Object.fromEntries(posted.entries);
            const out = {
              parent: posted.parent,
              action: posted.action,
              reason: map.reason || '',
              confirm_reason: map.confirm_reason || '',
              csrf: map.csrf_token || '',
            };
            out.ok = out.parent === 'BODY'
              && out.reason === 'تخلف تکرار شده'
              && out.confirm_reason === 'تخلف تکرار شده'
              && out.csrf === 'tok-abc';
            process.stdout.write(JSON.stringify(out));
            """
        ).replace("__COLLECT__", collect).replace("__SUBMIT__", submit)
        payload = _run_node(script)
        self.assertTrue(payload.get("ok"), payload)

    def test_edit_modal_delete_also_posts_reason_on_body_form(self):
        js_src = JS.read_text(encoding="utf-8")
        collect = _fn_src(js_src, "collectFormFields")
        submit = _fn_src(js_src, "submitFormPost")
        script = textwrap.dedent(
            """
            const { JSDOM } = require('jsdom');
            const dom = new JSDOM(`<!doctype html><html><body>
              <meta name="csrf-token" content="tok-edit" />
              <div class="ui-modal open" id="modal-user-edit">
                <form id="del" method="post" action="/users/9/delete">
                  <input type="hidden" name="reason" value="" />
                  <button type="submit">حذف کاربر</button>
                </form>
              </div>
            </body></html>`, { url: 'https://example.test/users' });
            const { window } = dom;
            const { document } = window;
            function csrfToken(){ return 'tok-edit'; }
            __COLLECT__
            __SUBMIT__
            window.__posted = null;
            window.HTMLFormElement.prototype.submit = function(){
              const entries = [];
              this.querySelectorAll('input').forEach((el) => entries.push([el.name, el.value]));
              window.__posted = Object.fromEntries(entries);
              window.__parent = this.parentNode && this.parentNode.tagName;
            };
            submitFormPost(document.getElementById('del'), {
              reason: 'درخواست خود کاربر',
              confirm_reason: 'درخواست خود کاربر',
            });
            const out = {
              parent: window.__parent,
              reason: window.__posted.reason,
              csrf: window.__posted.csrf_token,
            };
            out.ok = out.parent === 'BODY' && out.reason === 'درخواست خود کاربر' && out.csrf === 'tok-edit';
            process.stdout.write(JSON.stringify(out));
            """
        ).replace("__COLLECT__", collect).replace("__SUBMIT__", submit)
        payload = _run_node(script)
        self.assertTrue(payload.get("ok"), payload)


if __name__ == "__main__":
    unittest.main()
