from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .. import kvstore
from ..config import load
from ..llm.foundation_sec import extract

app = typer.Typer(help="Build and query the institutional knowledge graph.")
console = Console()


@app.command("build")
def build() -> None:
    """Cluster annotations into knowledge entries via Foundation-Sec-1.1-8B."""
    s = load()
    annotations = kvstore.query(s.kv_annotations)
    if not annotations:
        console.print("[yellow]No annotations yet.[/yellow] Run `ima alerts annotate ...` first.")
        raise typer.Exit(code=0)

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for a in annotations:
        key = (a.get("event_type", ""), a.get("disposition", ""))
        buckets[key].append(a)

    written = 0
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
        kvstore.insert(s.kv_knowledge, record)
        written += 1
    console.print(f"[green]Built[/green] {written} knowledge entries from {len(annotations)} annotations.")


@app.command("query")
def query(question: str = typer.Argument(..., help="Free-text question for the agent.")) -> None:
    """Naive substring lookup across the knowledge collection (LLM synthesis comes later)."""
    s = load()
    rows = kvstore.query(s.kv_knowledge)
    needle = question.lower()
    matches = [
        r for r in rows
        if needle in (r.get("topic", "") + " " + r.get("summary", "") + " " + r.get("tags", "")).lower()
    ]
    if not matches:
        console.print("[yellow]No matching institutional knowledge yet.[/yellow]")
        return
    table = Table("topic", "evidence", "confidence", "summary")
    for r in matches:
        table.add_row(
            str(r.get("topic", "")),
            str(r.get("evidence_count", "")),
            f"{float(r.get('confidence', 0)):.2f}",
            str(r.get("summary", ""))[:120],
        )
    console.print(Panel.fit(table, title=f"Knowledge matching: {question!r}"))
