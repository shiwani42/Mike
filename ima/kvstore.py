from __future__ import annotations

from typing import Any

from splunklib.binding import HTTPError

from .config import Settings, load
from .splunk_client import service

ANNOTATION_FIELDS = {
    "field.alert_id": "string",
    "field.event_type": "string",
    "field.analyst": "string",
    "field.disposition": "string",
    "field.reason": "string",
    "field.source_ip": "string",
    "field.asset": "string",
    "field.created_at": "string",
}

KNOWLEDGE_FIELDS = {
    "field.topic": "string",
    "field.summary": "string",
    "field.evidence_count": "number",
    "field.confidence": "number",
    "field.tags": "string",
    "field.updated_at": "string",
}

ASSET_FIELDS = {
    "field.asset": "string",
    "field.owner": "string",
    "field.notes": "string",
    "field.behavioral_exceptions": "string",
    "field.updated_at": "string",
}


def _ensure_collection(name: str, fields: dict[str, str]) -> str:
    svc = service()
    coll = svc.kvstore
    if name in coll:
        return "exists"
    coll.create(name, fields=fields)
    return "created"


def init_collections() -> dict[str, str]:
    s: Settings = load()
    return {
        s.kv_annotations: _ensure_collection(s.kv_annotations, ANNOTATION_FIELDS),
        s.kv_knowledge: _ensure_collection(s.kv_knowledge, KNOWLEDGE_FIELDS),
        s.kv_assets: _ensure_collection(s.kv_assets, ASSET_FIELDS),
    }


def insert(collection_name: str, record: dict[str, Any]) -> str:
    svc = service()
    coll = svc.kvstore[collection_name]
    result = coll.data.insert(record)
    return result.get("_key", "")


def query(collection_name: str, query_obj: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    svc = service()
    try:
        coll = svc.kvstore[collection_name]
    except (KeyError, HTTPError):
        return []
    return coll.data.query(query=query_obj or {})
