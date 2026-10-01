"""Delete reason must survive POST from kebab ops AND user-edit modal.

Root causes covered:
1) Confirm stacked under edit (z-index) — bringModalToFront.
2) Ops kebab: panelConfirm → closeRowActions → menu display:none →
   native form.submit() drops fields on mobile WebKit → empty reason flash.
3) v10.1.16 body-level display:none form.submit() STILL dropped fields on
   mobile WebKit — same class of bug. v10.1.19 posts via fetch(URLSearchParams).
"""

from __future__ import annotations

import json
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
        env = dict(**{k: v for k, v in __import__("os").environ.items()})
        env["NODE_PATH"] = "/tmp/jsdom-deps/node_modules"
        proc = subprocess.run(
            ["node", str(path)],
            cwd="/tmp",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=env,
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
        self.assertIn("URLSearchParams", body)
        self.assertIn("window.fetch(action", body)
        self.assertIn("body.append(pair[0]", body)
        self.assertIn("Preserve repeated keys", body)
        self.assertIn("Must NOT use display:none", body)

    def test_confirm_success_uses_submit_form_post_not_native(self):
        js = JS.read_text(encoding="utf-8")
        start = js.find("window.panelConfirm(opts).then")
        self.assertGreater(start, 0)
        block = js[start : start + 1100]
        self.assertIn("submitFormPost(form, overrides)", block)
        self.assertIn("overrides.confirm_reason", block)
        code_only = "\n".join(
            ln for ln in block.splitlines() if not ln.strip().startswith("/*") and "*/" not in ln
        )
        self.assertNotIn("form.submit();", code_only)
        self.assertIn("submitFormPost(form, overrides);", code_only)

    def test_kebab_css_hides_unported_menu(self):
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
            window.fetch = function(url, init){
              const params = Object.fromEntries(init.body.entries());
              window.__posted = { url: String(url), method: init.method, params };
              return Promise.resolve({ url: 'https://example.test/users?ok=1', ok: true });
            };
            window.location.assign = function(){};
            submitFormPost(document.getElementById('del'), {
              reason: 'تخلف تکرار شده',
              confirm_reason: 'تخلف تکرار شده',
            });
            const p = window.__posted;
            const out = {
              url: p && p.url,
              method: p && p.method,
              reason: p && p.params.reason || '',
              confirm_reason: p && p.params.confirm_reason || '',
              csrf: p && p.params.csrf_token || '',
            };
            out.ok = out.url.indexOf('/users/7/delete') >= 0
              && out.method === 'POST'
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
            window.fetch = function(url, init){
              const params = Object.fromEntries(init.body.entries());
              window.__posted = { url: String(url), params };
              return Promise.resolve({ url: 'https://example.test/users?ok=1', ok: true });
            };
            window.location.assign = function(){};
            submitFormPost(document.getElementById('del'), {
              reason: 'درخواست خود کاربر',
              confirm_reason: 'درخواست خود کاربر',
            });
            const p = window.__posted;
            const out = {
              reason: p.params.reason,
              confirm_reason: p.params.confirm_reason,
              csrf: p.params.csrf_token,
              url: p.url,
            };
            out.ok = out.reason === 'درخواست خود کاربر'
              && out.confirm_reason === 'درخواست خود کاربر'
              && out.csrf === 'tok-edit'
              && out.url.indexOf('/users/9/delete') >= 0;
            process.stdout.write(JSON.stringify(out));
            """
        ).replace("__COLLECT__", collect).replace("__SUBMIT__", submit)
        payload = _run_node(script)
        self.assertTrue(payload.get("ok"), payload)

    def test_bulk_delete_posts_all_ids_with_shared_reason(self):
        """Bulk bars append many ``ids`` fields; submitFormPost must keep them all."""
        js_src = JS.read_text(encoding="utf-8")
        collect = _fn_src(js_src, "collectFormFields")
        submit = _fn_src(js_src, "submitFormPost")
        script = textwrap.dedent(
            """
            const { JSDOM } = require('jsdom');
            const dom = new JSDOM(`<!doctype html><html><body>
              <meta name="csrf-token" content="tok-bulk" />
              <form id="bulk" method="post" action="/users/bulk-action">
                <input type="hidden" name="action" value="delete" />
                <input type="hidden" name="return_to" value="/users" />
                <input type="hidden" name="ids" value="11" />
                <input type="hidden" name="ids" value="22" />
                <input type="hidden" name="ids" value="33" />
              </form>
            </body></html>`, { url: 'https://example.test/users' });
            const { window } = dom;
            const { document } = window;
            function csrfToken(){ return 'tok-bulk'; }
            __COLLECT__
            __SUBMIT__
            window.__posted = null;
            window.fetch = function(url, init){
              const body = init.body;
              window.__posted = {
                url: String(url),
                method: init.method,
                ids: body.getAll('ids'),
                reason: body.get('reason') || '',
                confirm_reason: body.get('confirm_reason') || '',
                action: body.get('action') || '',
                csrf: body.get('csrf_token') || '',
              };
              return Promise.resolve({ url: 'https://example.test/users?ok=1', ok: true });
            };
            window.location.assign = function(){};
            submitFormPost(document.getElementById('bulk'), {
              reason: 'حذف گروهی تست',
              confirm_reason: 'حذف گروهی تست',
            });
            const p = window.__posted;
            const out = {
              ids: p && p.ids,
              reason: p && p.reason,
              confirm_reason: p && p.confirm_reason,
              action: p && p.action,
              csrf: p && p.csrf,
              url: p && p.url,
            };
            out.ok = Array.isArray(out.ids)
              && out.ids.length === 3
              && out.ids.join(',') === '11,22,33'
              && out.reason === 'حذف گروهی تست'
              && out.confirm_reason === 'حذف گروهی تست'
              && out.action === 'delete'
              && out.csrf === 'tok-bulk'
              && out.url.indexOf('/users/bulk-action') >= 0;
            process.stdout.write(JSON.stringify(out));
            """
        ).replace("__COLLECT__", collect).replace("__SUBMIT__", submit)
        payload = _run_node(script)
        self.assertTrue(payload.get("ok"), payload)


if __name__ == "__main__":
    unittest.main()
