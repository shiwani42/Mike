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
    "You are a security-knowledge extractor for a SOC team. Given one or more "
    "analyst notes about alert closures, extract the institutional knowledge "
    "they contain.\n\n"
    "Output ONLY a JSON object with these exact keys:\n"
    "- asset (string or null): the affected asset, host, subnet, or user name\n"
    "- behavior_pattern (string or null): one short sentence summarising the "
    "  institutional pattern (e.g. 'Finance batch job triggers failed-auth "
    "  bursts every Monday 6am.')\n"
    "- environmental_quirk (string or null): if this is an environmental "
    "  exception (scheduled job, known traveler, sanctioned scanner, expected "
    "  behavior), describe it. Otherwise null.\n"
    "- tags (list of short strings): short keywords like 'scheduled_job', "
    "  'known_traveler', 'sanctioned_pentest', 'real_threat', 'tune_rule'\n"
    "- confidence (number between 0 and 1): how confident you are this is a "
    "  stable, recurring institutional pattern (vs. a one-off observation)\n\n"
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
