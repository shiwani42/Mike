"""Shared helpers for IMA custom search commands.

Runs inside Splunk's own Python interpreter, so we rely on splunklib (shipped
with Splunk) and Python stdlib only. No vendored deps.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

OLLAMA_ENDPOINT = os.environ.get("IMA_OLLAMA_ENDPOINT", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("IMA_OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")
OLLAMA_EMBED_MODEL = os.environ.get("IMA_OLLAMA_EMBED_MODEL", "nomic-embed-text")

KV_ANNOTATIONS = "ima_annotations"
KV_KNOWLEDGE = "ima_knowledge"
KV_ASSETS = "ima_assets"


def kv_query(svc, name: str, query_obj: dict[str, Any] | None = None) -> list[dict]:
    try:
        coll = svc.kvstore[name]
    except KeyError:
        return []
    return coll.data.query(query=query_obj or {})


def kv_insert(svc, name: str, record: dict[str, Any]) -> str:
    coll = svc.kvstore[name]
    return coll.data.insert(record).get("_key", "")


SYSTEM_PROMPT = (
    "You are a security-knowledge extractor for a SOC team. You will receive "
    "one or more analyst notes about why an alert was closed a certain way. "
    "Your job is to extract the UNDERLYING INSTITUTIONAL PATTERN -- never quote "
    "or copy analyst phrasing verbatim, always rewrite as a generalized pattern.\n"
    "\n"
    "Output ONLY a JSON object with these exact keys:\n"
    "- asset (string or null): the affected entity (host, subnet, user, asset class)\n"
    "- behavior_pattern (string): ONE compressed sentence, max 18 words.\n"
    "- environmental_quirk (string or null): if this is an environmental exception\n"
    "  (scheduled job, known traveler, sanctioned scanner, expected behavior),\n"
    "  describe it in max 12 words. Otherwise null.\n"
    "- tags (list of 2 to 5 short snake_case strings): pick from categories like\n"
    "  scheduled_job, known_traveler, sanctioned_pentest, approved_scanner,\n"
    "  real_threat, c2_traffic, ir_invoked, tune_rule, suppress.\n"
    "- confidence (number 0..1):\n"
    "    * 3+ independent notes agree -> 0.90-1.00\n"
    "    * 2 notes agree              -> 0.65-0.90\n"
    "    * 1 observation              -> 0.10-0.35 (not yet a pattern)\n"
    "\n"
    "Example GOOD compression:\n"
    "  Notes: \"Cobalt Strike beacon detected, C2 to 185.x.x.x. IR-CS-01 invoked.\"\n"
    "  -> behavior_pattern: \"Cobalt Strike C2 beacons require immediate endpoint\n"
    "                       isolation under playbook IR-CS-01.\"\n"
    "     tags: [\"c2_traffic\", \"cobalt_strike\", \"real_threat\", \"ir_invoked\"]\n"
    "     confidence: 0.20\n"
    "\n"
    "No prose, no markdown fences. JSON only."
)


def llm_extract(text: str) -> dict[str, Any]:
    """Call local Ollama for structured extraction. Falls back to a stub on error."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_ENDPOINT.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
        return json.loads(body["message"]["content"])
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError):
        return {
            "asset": None,
            "behavior_pattern": text.strip()[:280] or None,
            "environmental_quirk": None,
            "tags": [],
            "confidence": 0.0,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def embed(text: str):
    """Return an embedding vector for text via Ollama. None on failure."""
    payload = json.dumps({"model": OLLAMA_EMBED_MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_ENDPOINT.rstrip('/')}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            vec = json.loads(resp.read().decode("utf-8")).get("embedding")
        return vec if isinstance(vec, list) and vec else None
    except Exception:  # noqa: BLE001
        return None


def cosine_similarity(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(x * x for x in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def build_asset_card(svc, asset_name: str, recent_n: int = 5):
    """Return a per-asset institutional-memory card. Mirrors ima.asset_memory."""
    from collections import Counter

    annotations = kv_query(svc, KV_ANNOTATIONS)
    needle = asset_name.lower()
    matching = [
        a for a in annotations
        if needle in (a.get("asset", "") or "").lower()
    ]
    if not matching:
        return {"asset": asset_name, "found": False, "annotation_count": 0}

    matching.sort(key=lambda a: a.get("created_at", ""), reverse=True)

    dispositions = Counter(a.get("disposition", "") for a in matching if a.get("disposition"))
    analysts = Counter(a.get("analyst", "") for a in matching if a.get("analyst"))
    event_types = Counter(a.get("event_type", "") for a in matching if a.get("event_type"))

    knowledge = kv_query(svc, KV_KNOWLEDGE)
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
        "top_disposition": dispositions.most_common(1)[0][0] if dispositions else "",
        "dispositions": dict(dispositions.most_common()),
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
            }
            for k in related[:5]
        ],
    }
