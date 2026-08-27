#!/usr/bin/env python3
"""Prove #panel-nav-clock behavior on slow MPA navigations (WebKit vs Chromium).

Proven facts:
- CSS animation-delay reveal FREEZES on WebKit once MPA nav starts (opacity stays 0).
- setTimeout DOES fire on WebKit during the outgoing-page wait.
- Immediate opacity (no CSS delay) stays visible on WebKit during slow nav.

Production (v8.5.33+) must use setTimeout anti-flicker + immediate opacity.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGE = """<!doctype html><html><head><title>FROM</title>
<style>
.panel-nav-clock{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;
  pointer-events:none;background:rgba(0,0,0,.5);opacity:0;visibility:hidden}
/* Legacy broken path (v8.5.31): CSS animation-delay */
.panel-nav-clock.cssdelay:not([hidden]){animation:panel-nav-clock-show 0s linear 140ms forwards}
@keyframes panel-nav-clock-show{to{opacity:1;visibility:visible}}
/* Fixed path: immediate opacity when unhidden */
.panel-nav-clock.imm:not([hidden]),
.panel-nav-clock.prod:not([hidden]){animation:none!important;opacity:1!important;visibility:visible!important}
.face{width:120px;height:120px;border-radius:50%;background:rgb(255,0,0)}
body{background:rgb(0,0,40);margin:0;min-height:100vh;color:#fff}
</style></head><body>
<a id="go" href="/slow">go</a>
<div id="panel-nav-clock" class="panel-nav-clock" hidden><span class="face"></span></div>
<script>
(function(){
  const c=document.getElementById('panel-nav-clock');
  window.__log=[];
  function snap(tag){
    const cs=getComputedStyle(c);
    const row={t:performance.now(),tag,hidden:c.hidden,opacity:cs.opacity,visibility:cs.visibility,
      play:cs.animationPlayState,delay:cs.animationDelay};
    window.__log.push(row);
    try{sessionStorage.setItem('navClockLog', JSON.stringify(window.__log));}catch(e){}
    return row;
  }
  window.snap=snap;
  window.armCssDelay=()=>{c.className='panel-nav-clock cssdelay';c.hidden=false;return snap('armCssDelay');};
  window.armImm=()=>{c.className='panel-nav-clock imm';c.hidden=false;return snap('armImm');};
  window.armProd=()=>{
    /* Match panel.js: setTimeout then immediate opacity */
    c.className='panel-nav-clock prod';
    clearTimeout(window.__tm);
    window.__tm=setTimeout(()=>{c.hidden=false;void c.offsetWidth;snap('toFire');},140);
    return snap('toSched');
  };
  function disarm(why){clearTimeout(window.__tm);c.hidden=true;snap('disarm-'+why);}
  window.addEventListener('pagehide',()=>disarm('pagehide'));
  window.startPoll=()=>{
    let n=0;
    const id=setInterval(()=>{
      snap('poll');
      n++;
      if(n>80) clearInterval(id);
    },50);
  };
})();
</script></body></html>"""

SLOW = """<!doctype html><html><head><title>SLOW</title></head><body>SLOW
<script>
try{window.__log=JSON.parse(sessionStorage.getItem('navClockLog')||'null')}catch(e){window.__log=null}
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/slow"):
            time.sleep(2.0)
            body = SLOW.encode()
        else:
            body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def run(engine_name, browser_type, base, mode):
    browser = browser_type.launch()
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(base + "/", wait_until="domcontentloaded")
    page.evaluate("() => window.startPoll()")
    if mode == "cssdelay":
        page.evaluate("() => window.armCssDelay()")
    elif mode == "imm":
        page.evaluate("() => window.armImm()")
    else:
        page.evaluate("() => window.armProd()")
    page.evaluate("() => { setTimeout(() => location.href='/slow', 0); return 'ok'; }")
    page.wait_for_url("**/slow", timeout=10000)
    log = page.evaluate("() => window.__log")
    browser.close()

    vis = [
        r
        for r in (log or [])
        if float(r.get("opacity") or 0) >= 0.95 and r.get("visibility") == "visible" and not r.get("hidden")
    ]
    polls = [r for r in (log or []) if r.get("tag") == "poll"]
    to_fire = [r for r in (log or []) if r.get("tag") == "toFire"]
    return {
        "engine": engine_name,
        "mode": mode,
        "visible_samples": len(vis),
        "timeout_fired": len(to_fire) > 0,
        "first_visible_t": vis[0]["t"] if vis else None,
        "poll_count": len(polls),
    }


def main() -> None:
    httpd, port = serve()
    base = f"http://127.0.0.1:{port}"
    out: dict = {"base": base, "cases": []}
    with sync_playwright() as p:
        for eng_name, eng in (("chromium", p.chromium), ("webkit", p.webkit)):
            for mode in ("cssdelay", "imm", "prod"):
                out["cases"].append(run(eng_name, eng, base, mode))

    def find(e, m):
        return next(c for c in out["cases"] if c["engine"] == e and c["mode"] == m)

    out["verdicts"] = {
        "webkit_cssdelay_fails": find("webkit", "cssdelay")["visible_samples"] == 0,
        "webkit_imm_works": find("webkit", "imm")["visible_samples"] > 0,
        "webkit_prod_setTimeout_works": find("webkit", "prod")["visible_samples"] > 0
        and find("webkit", "prod")["timeout_fired"],
        "chromium_prod_works": find("chromium", "prod")["visible_samples"] > 0,
    }
    errors = []
    if not out["verdicts"]["webkit_cssdelay_fails"]:
        errors.append("expected WebKit CSS-delay path to stay invisible during slow nav")
    if not out["verdicts"]["webkit_imm_works"]:
        errors.append("WebKit immediate opacity must work during slow nav")
    if not out["verdicts"]["webkit_prod_setTimeout_works"]:
        errors.append("WebKit production setTimeout path must show clock during slow nav")
    if not out["verdicts"]["chromium_prod_works"]:
        errors.append("Chromium production path must show clock")

    out["passed"] = not errors
    out["errors"] = errors
    print(json.dumps(out, ensure_ascii=False, indent=2))
    Path("/tmp/nav_clock_webkit_proof.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    if errors:
        raise SystemExit(1)
    print("NAV_CLOCK_WEBKIT_PROOF_PASSED", flush=True)


if __name__ == "__main__":
    main()
