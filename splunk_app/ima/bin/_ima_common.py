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

import splunklib.client as splunk_client

OLLAMA_ENDPOINT = os.environ.get("IMA_OLLAMA_ENDPOINT", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("IMA_OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")

KV_ANNOTATIONS = "ima_annotations"
KV_KNOWLEDGE = "ima_knowledge"
KV_ASSETS = "ima_assets"


def service_from_metadata(meta) -> splunk_client.Service:
    """Build a splunklib Service from a CSC metadata object."""
    info = meta.searchinfo
    return splunk_client.connect(
        host=info.splunkd_uri.split("://")[1].split(":")[0],
        port=int(info.splunkd_uri.rsplit(":", 1)[1]),
        scheme=info.splunkd_uri.split("://")[0],
        token=info.session_key,
        app="ima",
        owner="nobody",
    )


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
    "You are a security-knowledge extractor for a SOC team. Given one or more "
    "analyst notes about alert closures, extract the institutional knowledge "
    "they contain.\n\n"
    "Output ONLY a JSON object with these exact keys:\n"
    "- asset (string or null)\n"
    "- behavior_pattern (string or null): one short sentence summarising the "
    "  institutional pattern\n"
    "- environmental_quirk (string or null)\n"
    "- tags (list of short strings)\n"
    "- confidence (number between 0 and 1)\n\n"
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
