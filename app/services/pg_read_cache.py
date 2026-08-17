"""Tiny TTL cache for PasarGuard GET reads — keyed by client identity."""

from __future__ import annotations

import copy
import time
from typing import Any

_TTL_SEC = 4.0
_MAX = 256
_STORE: dict[tuple, tuple[float, Any]] = {}


def _key(ident: str, path: str, params: Any) -> tuple:
    if params is None:
        param_key = ""
    elif isinstance(params, dict):
        param_key = repr(tuple(sorted((str(k), str(v)) for k, v in params.items())))
    else:
        param_key = repr(params)
    return (str(ident or ""), str(path or ""), param_key)


def cache_get(ident: str, path: str, params: Any = None) -> Any | None:
    k = _key(ident, path, params)
    hit = _STORE.get(k)
    if not hit:
        return None
    ts, val = hit
    if time.monotonic() - ts > _TTL_SEC:
        _STORE.pop(k, None)
        return None
    return copy.deepcopy(val)


def cache_put(ident: str, path: str, params: Any, value: Any) -> None:
    if value is None:
        return
    if len(_STORE) >= _MAX:
        oldest = min(_STORE, key=lambda item: _STORE[item][0])
        _STORE.pop(oldest, None)
    _STORE[_key(ident, path, params)] = (time.monotonic(), copy.deepcopy(value))


def invalidate_ident(ident: str) -> None:
    prefix = str(ident or "")
    for k in [k for k in _STORE if k[0] == prefix]:
        _STORE.pop(k, None)
