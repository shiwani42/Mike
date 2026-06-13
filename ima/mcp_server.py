"""MCP server exposing the Institutional Memory Agent as tools.

Any MCP client (Claude Desktop, SAIA Agent Mode, autonomous SOC agents, custom
agents over the wire) can call into the institutional knowledge graph via this
server. It's a thin wrapper over the same `ima.kvstore` and `ima.llm` modules
that back the CLI and the Splunk app — so the three surfaces share one logic.

Run with:  ima mcp serve            (stdio, for Claude Desktop)
       or: ima mcp serve --http     (HTTP transport for remote clients)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import kvstore
from .config import load
from .llm.foundation_sec import extract

mcp = FastMCP(
    name="ima",
    instructions=(
        "Institutional Memory Agent for a SOC team. Use these tools to query and "
        "record analyst reasoning about alert closures. The knowledge graph lives "
        "in Splunk KV Store; structured extraction happens via Foundation-Sec-1.1-8B "
        "(or a local Ollama stand-in). Prefer 'query_knowledge' before recommending "
        "any disposition — institutional memory often explains alerts that look "
        "novel to a new analyst."
    ),
)


@mcp.tool()
def query_knowledge(question: str) -> list[dict[str, Any]]:
    """Search the institutional knowledge graph for entries matching the question.

    Returns clusters of analyst reasoning ranked by confidence and evidence count.
    Use this before triaging a fresh alert to see whether the SOC has already
    encountered the same pattern (scheduled batch jobs, sanctioned pentests,
    known traveling executives, etc.).

    Args:
        question: free-text question, e.g. "finance Monday auth failures",
                  "ciso international travel", "RedTeam pentest".

    Returns:
        List of knowledge entries, each with topic, summary, evidence_count,
        confidence (0..1), tags. Empty list if nothing matches yet.
    """
    s = load()
    rows = kvstore.query(s.kv_knowledge)
    needle = question.lower()
    matches = []
    for r in rows:
        hay = " ".join(
            str(r.get(k, "")) for k in ("topic", "summary", "tags")
        ).lower()
        if needle in hay:
            matches.append({
                "topic": r.get("topic", ""),
                "summary": r.get("summary", ""),
                "evidence_count": int(r.get("evidence_count", 0) or 0),
                "confidence": float(r.get("confidence", 0) or 0),
                "tags": r.get("tags", ""),
                "updated_at": r.get("updated_at", ""),
            })
    matches.sort(key=lambda r: (r["confidence"], r["evidence_count"]), reverse=True)
    return matches


@mcp.tool()
def record_annotation(
    alert_id: str,
    disposition: str,
    reason: str,
    asset: str = "",
    event_type: str = "",
    source_ip: str = "",
    analyst: str = "agent",
) -> dict[str, Any]:
    """Record an analyst's reasoning about an alert closure.

    Persists to the ima_annotations KV Store collection. Call after closing or
    triaging an alert; the agent will cluster these notes into structured
    institutional knowledge entries on the next `build_knowledge` invocation.

    Args:
        alert_id:    notable / saved-search alert identifier (e.g. NOTABLE-1099).
        disposition: 'false_positive' | 'escalated' | 'suppressed' | 'true_positive'.
        reason:      one-sentence why-statement. The shorter the better.
        asset:       optional affected asset/host name.
        event_type:  optional event type or correlation rule name.
        source_ip:   optional source IP for the event.
        analyst:     who recorded this. Defaults to 'agent' when an autonomous
                     agent is making the call.
    """
    s = load()
    record = {
        "alert_id": alert_id,
        "event_type": event_type,
        "analyst": analyst,
        "disposition": disposition,
        "reason": reason,
        "source_ip": source_ip,
        "asset": asset,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    key = kvstore.insert(s.kv_annotations, record)
    return {"status": "saved", "_key": key, "alert_id": alert_id, "disposition": disposition}


@mcp.tool()
def list_recent_annotations(limit: int = 10) -> list[dict[str, Any]]:
    """List the most recently recorded analyst annotations.

    Useful for understanding the SOC's recent activity, finding similar past
    incidents, or auditing what other analysts have decided.

    Args:
        limit: max number of annotations to return (default 10, ordered newest first).
    """
    s = load()
    rows = kvstore.query(s.kv_annotations)
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return [
        {
            "alert_id": r.get("alert_id", ""),
            "disposition": r.get("disposition", ""),
            "reason": r.get("reason", ""),
            "asset": r.get("asset", ""),
            "analyst": r.get("analyst", ""),
            "event_type": r.get("event_type", ""),
            "created_at": r.get("created_at", ""),
        }
        for r in rows[:limit]
    ]


@mcp.tool()
def build_knowledge() -> dict[str, Any]:
    """Cluster recent annotations into structured knowledge entries.

    Groups annotations by (event_type, disposition), then runs Foundation-Sec-1.1-8B
    (or the local Ollama stand-in) to produce one structured knowledge entry per
    cluster (asset, behavior_pattern, environmental_quirk, tags, confidence).

    This is a relatively expensive operation (~30 sec per cluster on CPU). Run
    it on a schedule or after a batch of new annotations arrives.
    """
    s = load()
    annotations = kvstore.query(s.kv_annotations)
    if not annotations:
        return {"status": "no_annotations", "message": "Nothing to build."}

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for a in annotations:
        buckets[(a.get("event_type", ""), a.get("disposition", ""))].append(a)

    written: list[dict[str, Any]] = []
    for (event_type, disposition), items in buckets.items():
        notes = " | ".join(i.get("reason", "") for i in items if i.get("reason"))
        structured = extract(notes)
        record = {
            "topic": f"{event_type or 'unknown'} :: {disposition or 'unknown'}",
            "summary": structured.behavior_pattern or notes[:280],
            "evidence_count": len(items),
            "confidence": structured.confidence,
            "tags": ",".join(structured.tags),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        key = kvstore.insert(s.kv_knowledge, record)
        written.append({
            "topic": record["topic"],
            "evidence_count": record["evidence_count"],
            "confidence": record["confidence"],
            "_key": key,
        })

    return {
        "status": "built",
        "annotations_processed": len(annotations),
        "knowledge_entries_written": len(written),
        "entries": written,
    }


def serve_stdio() -> None:
    """Run the MCP server over stdio (for Claude Desktop, IDE clients)."""
    mcp.run(transport="stdio")


def serve_http(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the MCP server over streamable HTTP (for remote agents)."""
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    serve_stdio()
