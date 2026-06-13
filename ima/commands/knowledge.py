from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .. import kvstore
from ..config import load
from ..llm.foundation_sec import cosine_similarity, embed, extract

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


def _row_text(r: dict) -> str:
    return " ".join(str(r.get(k, "")) for k in ("topic", "summary", "tags"))


def _semantic_rank(question: str, rows: list[dict], min_sim: float = 0.4) -> list[tuple[float, dict]]:
    """Embed the question + each row, return (similarity, row) pairs sorted desc.
    Returns [] if embedding is unavailable.
    """
    q_emb = embed(question)
    if q_emb is None:
        return []
    scored: list[tuple[float, dict]] = []
    for r in rows:
        r_emb = embed(_row_text(r))
        if r_emb is None:
            continue
        sim = cosine_similarity(q_emb, r_emb)
        if sim >= min_sim:
            scored.append((sim, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored


def _substring_rank(question: str, rows: list[dict]) -> list[tuple[float, dict]]:
    needle = question.lower()
    return [(1.0, r) for r in rows if needle in _row_text(r).lower()]


@app.command("query")
def query(
    question: str = typer.Argument(..., help="Free-text question for the agent."),
    semantic: bool = typer.Option(True, "--semantic/--substring", help="Use embeddings (default) or substring match."),
    top_k: int = typer.Option(5, help="Max results to return."),
) -> None:
    """Ask the institutional knowledge graph.

    Default mode is semantic (embeddings via Ollama nomic-embed-text). Falls back
    to substring match if the embedding model isn't reachable.
    """
    s = load()
    rows = kvstore.query(s.kv_knowledge)

    method = "semantic"
    scored: list[tuple[float, dict]] = []
    if semantic:
        scored = _semantic_rank(question, rows)
        if not scored:
            method = "substring (semantic unavailable)"
            scored = _substring_rank(question, rows)
    else:
        method = "substring"
        scored = _substring_rank(question, rows)

    if not scored:
        console.print(f"[yellow]No matching institutional knowledge[/yellow] (method: {method}).")
        return

    table = Table("sim", "topic", "evidence", "confidence", "summary")
    for sim, r in scored[:top_k]:
        table.add_row(
            f"{sim:.2f}",
            str(r.get("topic", "")),
            str(r.get("evidence_count", "")),
            f"{float(r.get('confidence', 0)):.2f}",
            str(r.get("summary", ""))[:120],
        )
    console.print(Panel.fit(table, title=f"Knowledge matching: {question!r}  [{method}]"))
