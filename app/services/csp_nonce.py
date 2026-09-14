"""CSP nonce helpers — keep inline scripts alive when script-src carries a nonce.

Browsers ignore ``'unsafe-inline'`` once a nonce/hash is present in ``script-src``.
Panel templates still ship many inline ``<script>`` blocks without a nonce, so HTML
responses must receive the request nonce on every opening ``<script>`` tag.

Starlette ``@app.middleware("http")`` wraps the downstream response in a
``_StreamingResponse`` without a ``.body`` attribute — callers must buffer
``body_iterator`` (see ``buffer_and_inject_nonce``).
"""

from __future__ import annotations

import re
from typing import Optional

from starlette.datastructures import MutableHeaders
from starlette.responses import Response

_SCRIPT_OPEN_RE = re.compile(r"<script\b[^>]*>", re.IGNORECASE)
_NONCE_ATTR_RE = re.compile(r"\bnonce\s*=", re.IGNORECASE)


def inject_script_nonces(html: str, nonce: str) -> str:
    """Add ``nonce="…"`` to every ``<script>`` opening tag that lacks one."""
    if not html or not nonce:
        return html
    # Keep nonce attribute values free of quotes that would break the tag.
    safe = str(nonce).replace('"', "").replace("'", "").strip()
    if not safe:
        return html

    def _add(match: re.Match[str]) -> str:
        tag = match.group(0)
        if _NONCE_ATTR_RE.search(tag):
            return tag
        return tag[:-1] + f' nonce="{safe}">'

    return _SCRIPT_OPEN_RE.sub(_add, html)


def inject_nonce_into_response(response: Response, nonce: Optional[str]) -> Response:
    """Rewrite a buffered HTML response body so inline scripts carry ``nonce``.

    Only works when ``response.body`` is already materialized (plain
    ``HTMLResponse``). Prefer ``buffer_and_inject_nonce`` inside
    ``@app.middleware("http")`` handlers.
    """
    if not nonce:
        return response
    ctype = (response.headers.get("content-type") or "").lower()
    if "text/html" not in ctype:
        return response
    body = getattr(response, "body", None)
    if not isinstance(body, (bytes, bytearray)) or not body:
        return response
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return response
    updated = inject_script_nonces(text, nonce)
    if updated == text:
        return response
    new_body = updated.encode("utf-8")
    response.body = new_body
    response.headers["content-length"] = str(len(new_body))
    return response


async def buffer_and_inject_nonce(response: Response, nonce: Optional[str]) -> Response:
    """Buffer a (possibly streaming) HTML response and stamp script nonces.

    Safe to call for non-HTML responses — returns the original object unchanged.
    """
    if not nonce:
        return response
    ctype = (response.headers.get("content-type") or "").lower()
    if "text/html" not in ctype:
        return response

    body = getattr(response, "body", None)
    if isinstance(body, (bytes, bytearray)) and body:
        raw = bytes(body)
    else:
        iterator = getattr(response, "body_iterator", None)
        if iterator is None:
            return response
        chunks: list[bytes] = []
        async for chunk in iterator:
            if isinstance(chunk, bytes):
                chunks.append(chunk)
            else:
                chunks.append(str(chunk).encode("utf-8"))
        raw = b"".join(chunks)

    if not raw:
        return response
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return Response(
            content=raw,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
            background=getattr(response, "background", None),
        )

    updated = inject_script_nonces(text, nonce)
    new_body = updated.encode("utf-8")
    headers = MutableHeaders(response.headers)
    headers["content-length"] = str(len(new_body))
    # Drop Content-Encoding if we rewrote plaintext (should not be gzip here).
    if "content-encoding" in headers:
        del headers["content-encoding"]
    return Response(
        content=new_body,
        status_code=response.status_code,
        headers=dict(headers),
        media_type=response.media_type,
        background=getattr(response, "background", None),
    )
