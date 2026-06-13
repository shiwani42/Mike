from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import load


@dataclass
class StructuredAnnotation:
    asset: str | None
    behavior_pattern: str | None
    environmental_quirk: str | None
    tags: list[str]
    confidence: float


_SYSTEM_PROMPT = (
    "You are a security-knowledge extractor for a SOC team. You will receive "
    "one or more analyst notes about why an alert was closed a certain way. "
    "Your job is to extract the UNDERLYING INSTITUTIONAL PATTERN — never quote "
    "or copy analyst phrasing verbatim, always rewrite as a generalized pattern.\n"
    "\n"
    "Output ONLY a JSON object with these exact keys:\n"
    "- asset (string or null): the affected entity (host, subnet, user, asset class)\n"
    "- behavior_pattern (string): ONE compressed sentence, max 18 words, describing\n"
    "  the recurring pattern or institutional fact. Never longer.\n"
    "- environmental_quirk (string or null): if this is an environmental exception\n"
    "  (scheduled job, known traveler, sanctioned scanner, expected behavior),\n"
    "  describe it in max 12 words. Otherwise null.\n"
    "- tags (list of 2 to 5 short snake_case strings): pick from disposition-typed\n"
    "  categories such as scheduled_job, known_traveler, sanctioned_pentest,\n"
    "  approved_scanner, real_threat, c2_traffic, ir_invoked, tune_rule, suppress.\n"
    "- confidence (number 0..1):\n"
    "    * 3+ independent analyst notes agree -> 0.90-1.00\n"
    "    * 2 notes agree                       -> 0.65-0.90\n"
    "    * 1 observation                       -> 0.10-0.35 (not yet a pattern)\n"
    "\n"
    "Examples of GOOD compression:\n"
    "  Notes: \"Cobalt Strike beacon detected, confirmed C2 traffic to 185.x.x.x.\n"
    "          Endpoint isolated, IR playbook IR-CS-01 invoked.\"\n"
    "  -> behavior_pattern: \"Cobalt Strike C2 beacons require immediate endpoint\n"
    "                       isolation under playbook IR-CS-01.\"\n"
    "     tags: [\"c2_traffic\", \"cobalt_strike\", \"real_threat\", \"ir_invoked\"]\n"
    "     confidence: 0.20\n"
    "\n"
    "  Notes: \"Internal Q2 pentest by RedTeam-3 against the staging subnet.\n"
    "          Source IP is on the approved-scanner allowlist. | Same RedTeam\n"
    "          pentest, week 2. Source is sanctioned, ticket SEC-883.\"\n"
    "  -> behavior_pattern: \"Sanctioned RedTeam pentest against the staging subnet\n"
    "                       can be suppressed.\"\n"
    "     tags: [\"sanctioned_pentest\", \"approved_scanner\", \"suppress\"]\n"
    "     confidence: 0.85\n"
    "\n"
    "No prose, no markdown fences, no preamble. JSON only."
)


def _stub(text: str) -> StructuredAnnotation:
    return StructuredAnnotation(
        asset=None,
        behavior_pattern=text.strip()[:280] or None,
        environmental_quirk=None,
        tags=[],
        confidence=0.0,
    )


def _parse(raw: str) -> StructuredAnnotation:
    data = json.loads(raw)
    return StructuredAnnotation(
        asset=data.get("asset"),
        behavior_pattern=data.get("behavior_pattern"),
        environmental_quirk=data.get("environmental_quirk"),
        tags=list(data.get("tags") or []),
        confidence=float(data.get("confidence", 0.0)),
    )


def _call_ollama(text: str) -> StructuredAnnotation:
    s = load()
    url = f"{s.ollama_endpoint.rstrip('/')}/api/chat"
    payload: dict[str, Any] = {
        "model": s.ollama_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }
    resp = httpx.post(url, json=payload, timeout=120.0)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return _parse(content)


def _call_splunk_hosted(text: str) -> StructuredAnnotation:
    s = load()
    headers = {"Content-Type": "application/json"}
    if s.foundation_sec_api_key:
        headers["Authorization"] = f"Bearer {s.foundation_sec_api_key}"
    payload: dict[str, Any] = {
        "model": "foundation-sec-1.1-8b-instruct",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
    }
    resp = httpx.post(s.foundation_sec_endpoint, headers=headers, json=payload, timeout=60.0)
    resp.raise_for_status()
    return _parse(resp.json()["choices"][0]["message"]["content"])


def embed(text: str) -> list[float] | None:
    """Get an embedding vector for the given text via Ollama.

    Returns None if embedding is unavailable (Ollama down, model not pulled,
    LLM_PROVIDER=stub, etc.) — callers should treat None as "fall back to
    substring search".
    """
    s = load()
    if s.llm_provider != "ollama":
        return None
    url = f"{s.ollama_endpoint.rstrip('/')}/api/embeddings"
    payload: dict[str, Any] = {"model": s.ollama_embed_model, "prompt": text}
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        vec = resp.json().get("embedding")
        return vec if isinstance(vec, list) and vec else None
    except Exception:  # noqa: BLE001
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(x * x for x in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def extract(text: str) -> StructuredAnnotation:
    """Turn one or more analyst notes into a structured institutional-knowledge entry.

    Backend resolution (set via LLM_PROVIDER in .env):
      - 'splunk_hosted' -> Foundation-Sec-1.1-8B on the Splunk-hosted endpoint
      - 'ollama'        -> local Ollama (default; uses OLLAMA_MODEL)
      - 'stub'          -> no-op echo (offline/CI mode)
    """
    s = load()
    provider = s.llm_provider
    try:
        if provider == "splunk_hosted" and s.foundation_sec_endpoint:
            return _call_splunk_hosted(text)
        if provider == "ollama":
            return _call_ollama(text)
        return _stub(text)
    except Exception:  # noqa: BLE001
        return _stub(text)
