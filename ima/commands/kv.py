from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from .. import kvstore

app = typer.Typer(help="KV Store management for the institutional memory graph.")
console = Console()


@app.command("init")
def init() -> None:
    """Create the three KV Store collections (annotations, knowledge, assets)."""
    results = kvstore.init_collections()
    table = Table("collection", "status")
    for name, status in results.items():
        table.add_row(name, status)
    console.print(table)


@app.command("ls")
def ls(collection: str = typer.Argument(..., help="Collection name to dump.")) -> None:
    """Dump rows from a KV Store collection."""
    rows = kvstore.query(collection)
    console.print(f"[bold]{collection}[/bold]: {len(rows)} rows")
    for r in rows:
        console.print(r)
