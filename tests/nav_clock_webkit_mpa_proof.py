#!/usr/bin/env python3
"""WebKit vs Chromium: does CSS-delay / setTimeout / immediate arm paint during slow MPA nav?"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

PAGE = """<!doctype html><html><head><title>FROM</title>
<style>
.panel-nav-clock{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;
  pointer-events:none;background:transparent;opacity:0;visibility:hidden}
.panel-nav-clock:not([hidden]){animation:panel-nav-clock-show 0s linear 140ms forwards}
@keyframes panel-nav-clock-show{to{opacity:1;visibility:visible}}
.panel-nav-clock.imm:not([hidden]){animation:none!important;opacity:1!important;visibility:visible!important}
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
  window.armProd=()=>{c.classList.remove('imm');c.hidden=false;return snap('armProd');};
  window.armImm=()=>{c.classList.add('imm');c.hidden=false;return snap('armImm');};
  window.armTo=()=>{
    c.classList.add('imm');
    clearTimeout(window.__tm);
    window.__tm=setTimeout(()=>{c.hidden=false;snap('toFire');},140);
    return snap('toSched');
  };
  function disarm(why){clearTimeout(window.__tm);c.hidden=true;snap('disarm-'+why);}
  window.addEventListener('pagehide',()=>disarm('pagehide'));
  // Persist samples on a timer (rAF may freeze on WebKit during nav)
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
    if mode == "prod":
        armed = page.evaluate("() => window.armProd()")
    elif mode == "imm":
        armed = page.evaluate("() => window.armImm()")
    else:
        armed = page.evaluate("() => window.armTo()")
    pre = page.evaluate("() => window.snap('pre')")

    # schedule nav; evaluate returns before unload
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
    poll_vis = [r for r in polls if float(r.get("opacity") or 0) >= 0.95]
    disarm = [r for r in (log or []) if str(r.get("tag", "")).startswith("disarm")]
    to_fire = [r for r in (log or []) if r.get("tag") == "toFire"]

    return {
        "engine": engine_name,
        "mode": mode,
        "armed": armed,
        "pre": pre,
        "log_len": len(log or []),
        "visible_samples": len(vis),
        "poll_count": len(polls),
        "poll_visible": len(poll_vis),
        "timeout_fired": len(to_fire) > 0,
        "pagehide_at": disarm[0]["t"] if disarm else None,
        "first_visible_t": vis[0]["t"] if vis else None,
        "last_poll": polls[-1] if polls else None,
        "tail": (log or [])[-6:],
    }


def main():
    httpd, port = serve()
    base = f"http://127.0.0.1:{port}"
    out = {"base": base, "cases": []}
    with sync_playwright() as p:
        for eng_name, eng in (("chromium", p.chromium), ("webkit", p.webkit)):
            for mode in ("prod", "imm", "timeout"):
                print(f"run {eng_name} {mode}", flush=True)
                out["cases"].append(run(eng_name, eng, base, mode))
    # verdicts
    def find(e, m):
        return next(c for c in out["cases"] if c["engine"] == e and c["mode"] == m)

    out["verdicts"] = {
        "chromium_prod_visible_during_slow_nav": find("chromium", "prod")["visible_samples"] > 0,
        "webkit_prod_visible_during_slow_nav": find("webkit", "prod")["visible_samples"] > 0,
        "chromium_imm_visible_during_slow_nav": find("chromium", "imm")["visible_samples"] > 0,
        "webkit_imm_visible_during_slow_nav": find("webkit", "imm")["visible_samples"] > 0,
        "chromium_timeout_fires": find("chromium", "timeout")["timeout_fired"],
        "webkit_timeout_fires": find("webkit", "timeout")["timeout_fired"],
        "webkit_prod_polls_continue": find("webkit", "prod")["poll_count"] > 5,
        "webkit_prod_first_visible_t": find("webkit", "prod")["first_visible_t"],
        "chromium_prod_first_visible_t": find("chromium", "prod")["first_visible_t"],
    }
    print(json.dumps(out, indent=2))
    Path = __import__("pathlib").Path
    Path("/tmp/nav_clock_proof_out/webkit_vs_chromium.json").write_text(json.dumps(out, indent=2))
    httpd.shutdown()


if __name__ == "__main__":
    main()
