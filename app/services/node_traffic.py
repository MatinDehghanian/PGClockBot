"""Merge PasarGuard node list with realtime / traffic fields."""

from __future__ import annotations

from typing import Any

from app.services.formatting import format_bytes
from app.services.pasarguard import as_list


def _as_int(value: Any) -> int | None:
    if value is None or value is False:
        return None
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _pick_bytes(obj: dict, *keys: str) -> int | None:
    for key in keys:
        if key in obj and obj.get(key) is not None:
            n = _as_int(obj.get(key))
            if n is not None:
                return n
    return None


def _index_realtime(raw: Any) -> dict[int, dict]:
    """Normalize realtime_stats payload → {node_id: stats_dict}."""
    out: dict[int, dict] = {}
    if raw is None:
        return out
    rows: list = []
    if isinstance(raw, dict):
        # { "1": {...}, "2": {...} } or { "nodes": [...] } or { "stats": [...] }
        for key in ("nodes", "stats", "realtime", "items", "data"):
            if key in raw:
                rows = as_list(raw, key) or ([] if not isinstance(raw[key], list) else raw[key])
                break
        if not rows:
            # id-keyed map
            for k, v in raw.items():
                if isinstance(v, dict) and str(k).isdigit():
                    out[int(k)] = v
            return out
    elif isinstance(raw, list):
        rows = raw
    for row in rows:
        if not isinstance(row, dict):
            continue
        nid = row.get("node_id") if row.get("node_id") is not None else row.get("id")
        try:
            nid_i = int(nid)
        except (TypeError, ValueError):
            continue
        out[nid_i] = row
    return out


def enrich_nodes_with_traffic(nodes: list | None, realtime: Any = None) -> list[dict]:
    """Attach uplink/downlink/total (+ Persian text) onto each node dict."""
    rt = _index_realtime(realtime)
    enriched: list[dict] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        n = dict(node)
        try:
            nid = int(n.get("id"))
        except (TypeError, ValueError):
            nid = None
        stats = rt.get(nid) if nid is not None else None
        src = stats if isinstance(stats, dict) else {}
        # Prefer realtime; fall back to fields already on the node
        uplink = _pick_bytes(
            src,
            "uplink",
            "upload",
            "outgoing_bandwidth",
            "outgoing",
            "sent",
            "tx",
        )
        if uplink is None:
            uplink = _pick_bytes(
                n,
                "uplink",
                "upload",
                "outgoing_bandwidth",
                "outgoing",
                "traffic_up",
                "tx",
            )
        downlink = _pick_bytes(
            src,
            "downlink",
            "download",
            "incoming_bandwidth",
            "incoming",
            "received",
            "rx",
        )
        if downlink is None:
            downlink = _pick_bytes(
                n,
                "downlink",
                "download",
                "incoming_bandwidth",
                "incoming",
                "traffic_down",
                "rx",
            )
        total = _pick_bytes(src, "traffic", "total", "used_traffic", "bandwidth")
        if total is None:
            total = _pick_bytes(n, "traffic", "total", "used_traffic", "bandwidth")
        if total is None and uplink is not None and downlink is not None:
            total = int(uplink) + int(downlink)
        elif total is None:
            total = uplink if uplink is not None else downlink

        n["_traffic_up"] = uplink
        n["_traffic_down"] = downlink
        n["_traffic_total"] = total
        n["_traffic_up_text"] = format_bytes(uplink) if uplink is not None else "—"
        n["_traffic_down_text"] = format_bytes(downlink) if downlink is not None else "—"
        n["_traffic_total_text"] = format_bytes(total) if total is not None else "—"
        enriched.append(n)
    return enriched
