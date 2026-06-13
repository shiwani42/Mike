"""Per-asset institutional memory.

Aggregates annotations and knowledge entries for a specific asset into a single
card showing "what does the SOC know about this asset?". Computed on the fly
from KV Store - no separate persistence needed.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from . import kvstore
from .config import load


def build_asset_card(asset_name: str, recent_n: int = 5) -> dict[str, Any]:
    """Return a structured card describing what's known about an asset.

    Substring-matches across the `asset` field of every annotation, so passing
    a subnet prefix like '10.200' picks up subnet-scoped notes too.
    """
    s = load()
    annotations = kvstore.query(s.kv_annotations)
    needle = asset_name.lower()
    matching = [
        a for a in annotations
        if needle in (a.get("asset", "") or "").lower()
    ]

    if not matching:
        return {"asset": asset_name, "found": False}

    matching.sort(key=lambda a: a.get("created_at", ""), reverse=True)

    dispositions = Counter(a.get("disposition", "") for a in matching if a.get("disposition"))
    analysts = Counter(a.get("analyst", "") for a in matching if a.get("analyst"))
    event_types = Counter(a.get("event_type", "") for a in matching if a.get("event_type"))

    knowledge = kvstore.query(s.kv_knowledge)
    et_seen = {et for et in event_types if et}
    related = [
        k for k in knowledge
        if any(et in (k.get("topic", "") or "") for et in et_seen)
    ]
    related.sort(
        key=lambda k: (float(k.get("confidence", 0) or 0), int(k.get("evidence_count", 0) or 0)),
        reverse=True,
    )

    return {
        "asset": asset_name,
        "found": True,
        "annotation_count": len(matching),
        "dispositions": dict(dispositions.most_common()),
        "top_disposition": dispositions.most_common(1)[0][0] if dispositions else "",
        "analysts": dict(analysts.most_common()),
        "event_types": dict(event_types.most_common()),
        "first_seen": matching[-1].get("created_at", ""),
        "last_seen": matching[0].get("created_at", ""),
        "recent_annotations": [
            {
                "alert_id": a.get("alert_id", ""),
                "disposition": a.get("disposition", ""),
                "reason": a.get("reason", ""),
                "analyst": a.get("analyst", ""),
                "created_at": a.get("created_at", ""),
            }
            for a in matching[:recent_n]
        ],
        "related_knowledge": [
            {
                "topic": k.get("topic", ""),
                "summary": k.get("summary", ""),
                "confidence": float(k.get("confidence", 0) or 0),
                "evidence_count": int(k.get("evidence_count", 0) or 0),
                "tags": k.get("tags", ""),
            }
            for k in related[:5]
        ],
    }
