#!/usr/bin/env python3
"""Build the Persian PGClockBot guide into app/web/static/guide/.

Sources:
  docs/guide/pages/*.md
  docs/guide/theme/*
  app/services/guide_catalog.py

Usage:
  python scripts/build_guide.py

The built site is committed so production installs get /help without extra tools.
Re-run this script after editing Markdown, then commit the updated static files.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
from collections import OrderedDict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "docs" / "guide" / "pages"
THEME = ROOT / "docs" / "guide" / "theme"
OUT = ROOT / "app" / "web" / "static" / "guide"
WEB_STATIC = ROOT / "app" / "web" / "static"

sys.path.insert(0, str(ROOT))
from app.services.guide_catalog import NAV_ORDER, TOPICS, nav_topics  # noqa: E402


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip("\"'")
    return meta, body


def inline_md(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        text,
    )
    return text


def md_to_html(src: str) -> str:
    lines = src.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            code = html.escape("\n".join(buf))
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{code}</code></pre>")
            continue
        m = re.match(r"^:::(tip|warn|error|info)\s*$", line.strip())
        if m:
            kind = m.group(1)
            labels = {
                "tip": "نکته",
                "warn": "هشدار",
                "error": "خطای رایج",
                "info": "راهنما",
            }
            i += 1
            buf = []
            while i < len(lines) and lines[i].strip() != ":::":
                buf.append(lines[i])
                i += 1
            i += 1
            inner = md_to_html("\n".join(buf))
            out.append(
                f'<div class="guide-callout guide-callout--{kind}">'
                f'<strong class="guide-callout-label">{labels[kind]}</strong>'
                f"{inner}</div>"
            )
            continue
        if line.startswith("### "):
            title = line[4:].strip()
            out.append(f'<h3 id="{slugify(title)}">{inline_md(title)}</h3>')
            i += 1
            continue
        if line.startswith("## "):
            title = line[3:].strip()
            out.append(f'<h2 id="{slugify(title)}">{inline_md(title)}</h2>')
            i += 1
            continue
        if line.startswith("# "):
            i += 1
            continue
        if re.match(r"^[-*] ", line):
            items = []
            while i < len(lines) and re.match(r"^[-*] ", lines[i]):
                items.append(f"<li>{inline_md(lines[i][2:].strip())}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        if re.match(r"^\d+\. ", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                text = re.sub(r"^\d+\.\s*", "", lines[i]).strip()
                items.append(f"<li>{inline_md(text)}</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        if line.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith("> "):
                buf.append(lines[i][2:])
                i += 1
            out.append(f"<blockquote>{md_to_html(chr(10).join(buf))}</blockquote>")
            continue
        buf = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]):
            buf.append(lines[i])
            i += 1
        out.append(f"<p>{inline_md(' '.join(x.strip() for x in buf))}</p>")
    return "\n".join(out)


def _starts_block(line: str) -> bool:
    return bool(
        line.startswith("#")
        or line.startswith("```")
        or line.startswith(":::")
        or line.startswith("> ")
        or re.match(r"^[-*] ", line)
        or re.match(r"^\d+\. ", line)
    )


def slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^\w\u0600-\u06ff\-]+", "", s, flags=re.UNICODE)
    return s or "section"


ROLE_FA = {
    "owner": "مالک",
    "admin": "ادمین",
    "reseller": "نماینده",
    "pg_staff": "ادمین پاسارگارد",
    "principal": "نماینده ارشد",
}


def nav_groups_list():
    groups: OrderedDict[str, list] = OrderedDict()
    for t in nav_topics():
        g = t.get("nav_group") or "سایر"
        groups.setdefault(g, []).append(t)
    return list(groups.items())


def roles_label(roles: list[str]) -> str:
    return "، ".join(ROLE_FA.get(r, r) for r in roles)


def main() -> int:
    if not PAGES.is_dir():
        print(f"missing pages dir: {PAGES}", file=sys.stderr)
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shutil.copy2(THEME / "guide.css", OUT / "guide.css")
    shutil.copy2(THEME / "guide.js", OUT / "guide.js")
    shutil.copy2(WEB_STATIC / "fonts.css", OUT / "fonts.css")
    fonts_dir = WEB_STATIC / "fonts"
    if fonts_dir.is_dir():
        shutil.copytree(fonts_dir, OUT / "fonts")
    for name in ("logo-64.png", "logo.png"):
        src = WEB_STATIC / name
        if src.is_file():
            shutil.copy2(src, OUT / name)

    fonts_css = (OUT / "fonts.css").read_text(encoding="utf-8")
    fonts_css = fonts_css.replace('url("/static/fonts/', 'url("fonts/')
    fonts_css = fonts_css.replace("url('/static/fonts/", "url('fonts/")
    (OUT / "fonts.css").write_text(fonts_css, encoding="utf-8")

    env = Environment(
        loader=FileSystemLoader(str(THEME)),
        autoescape=select_autoescape(["html"]),
    )

    page_files = {p.stem: p for p in PAGES.glob("*.md")}
    built: list[dict] = []
    search_items: list[dict] = []
    groups = nav_groups_list()

    for tid in NAV_ORDER:
        meta = TOPICS[tid]
        path = page_files.get(tid) or page_files.get(meta["slug"])
        if not path:
            print(f"warn: no markdown for topic {tid}", file=sys.stderr)
            body_src = "## به‌زودی\n\nآموزش این بخش به‌زودی تکمیل می‌شود.\n"
        else:
            _fm, body_src = parse_frontmatter(path.read_text(encoding="utf-8"))
        body_html = md_to_html(body_src)
        built.append(
            {
                "id": tid,
                "slug": meta["slug"],
                "title": meta["title"],
                "summary": meta["summary"],
                "panel": meta.get("panel") or "",
                "roles": meta.get("roles") or [],
                "body_html": Markup(body_html),
                "body_text": re.sub(r"<[^>]+>", " ", body_html),
                "aliases": meta.get("aliases") or [],
            }
        )

    page_tpl = env.get_template("page.html")
    for idx, page in enumerate(built):
        prev = built[idx - 1] if idx > 0 else None
        nxt = built[idx + 1] if idx + 1 < len(built) else None
        dest = OUT / page["slug"]
        dest.mkdir(parents=True, exist_ok=True)
        html_out = page_tpl.render(
            title=page["title"],
            summary=page["summary"],
            body_html=page["body_html"],
            page_id=page["id"],
            root="../",
            nav_groups=groups,
            panel_path=page["panel"],
            panel_href=page["panel"] or "#",
            roles_label=roles_label(page["roles"]),
            prev=prev,
            next=nxt,
        )
        (dest / "index.html").write_text(html_out, encoding="utf-8")
        search_items.append(
            {
                "id": page["id"],
                "title": page["title"],
                "summary": page["summary"],
                "aliases": page["aliases"],
                "body": page["body_text"][:4000],
                "href": f"{page['slug']}/index.html",
            }
        )

    index_md = PAGES / "index.md"
    if index_md.is_file():
        _, index_body = parse_frontmatter(index_md.read_text(encoding="utf-8"))
        index_html_body = Markup(md_to_html(index_body))
    else:
        index_html_body = Markup("<p>از فهرست کناری یا کارت‌های زیر موضوع را انتخاب کنید.</p>")

    featured_ids = ["start", "plans", "finance", "users", "resellers", "troubleshooting"]
    featured = [p for p in built if p["id"] in featured_ids]
    home_html = env.get_template("home.html").render(
        root="./",
        nav_groups=groups,
        body_html=index_html_body,
        featured=featured,
    )
    (OUT / "index.html").write_text(home_html, encoding="utf-8")

    (OUT / "search-index.json").write_text(
        json.dumps(search_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    catalog = {
        tid: {
            "title": TOPICS[tid]["title"],
            "summary": TOPICS[tid]["summary"],
            "slug": TOPICS[tid]["slug"],
            "panel": TOPICS[tid].get("panel") or "",
        }
        for tid in NAV_ORDER
    }
    (OUT / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for page in built:
        local = [{**it, "href": f"../{it['href']}"} for it in search_items]
        (OUT / page["slug"] / "search-index.json").write_text(
            json.dumps(local, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"built {len(built)} pages → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
