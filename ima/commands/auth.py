from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..config import load
from ..splunk_client import service

app = typer.Typer(help="Connection and auth diagnostics.")
console = Console()


@app.command("check")
def check() -> None:
    """Verify Splunk REST connectivity and print server info."""
    s = load()
    console.print(f"[bold]Target[/bold]: {s.base_url} (app={s.app}, owner={s.owner})")
    try:
        svc = service()
        info = svc.info
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]FAIL[/red]: {exc}")
        raise typer.Exit(code=1)

    table = Table(show_header=False, box=None)
    for key in ("version", "build", "serverName", "os_name", "licenseState"):
        table.add_row(key, str(info.get(key, "")))
    console.print(table)
    console.print("[green]OK[/green] - authenticated to splunkd.")
