from __future__ import annotations

import json as _json
import time
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .. import kvstore
from ..config import load
from ..splunk_client import service

app = typer.Typer(help="Observe and annotate alerts.")
console = Console()

DEFAULT_WATCH_SPL = (
    'search (sourcetype="ima:alert") OR (index=_audit action=alert_fired) OR (index=notable) '
    '| eval alert_id=coalesce(alert_id, event_id, ss_name."-".strftime(_time,"%s"), _cd) '
    '| eval event_type=coalesce(event_type, search_name, source, sourcetype) '
    '| eval src=coalesce(src, source_ip) '
    '| eval dest=coalesce(dest, asset) '
    '| table _time, alert_id, event_type, asset, src, dest, severity, _raw'
)

DISPOSITION_KEYS = {
    "f": "false_positive",
    "e": "escalated",
    "s": "suppressed",
    "t": "true_positive",
}


@app.command("list")
def list_alerts(
    earliest: str = typer.Option("-24h", help="Splunk earliest time modifier."),
    limit: int = typer.Option(20, help="Max events to return."),
) -> None:
    """List recent notable events / alerts from Splunk."""
    rows = _fetch_alerts(earliest, limit)
    table = Table("_time", "alert_id", "event_type", "severity")
    for r in rows:
        table.add_row(
            r.get("_time", ""),
            r.get("alert_id", ""),
            r.get("event_type", ""),
            r.get("severity", ""),
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} alerts in window {earliest}.[/dim]")


def _fetch_alerts(earliest: str, limit: int = 100) -> list[dict]:
    svc = service()
    spl = f"{DEFAULT_WATCH_SPL} | head {limit}"
    job = svc.jobs.oneshot(spl, earliest_time=earliest, output_mode="json")
    return _json.loads(job.read().decode()).get("results", [])


def _already_annotated_ids() -> set[str]:
    s = load()
    rows = kvstore.query(s.kv_annotations)
    return {r.get("alert_id", "") for r in rows if r.get("alert_id")}


@app.command("watch")
def watch(
    earliest: str = typer.Option("-1h", help="How far back to scan on each pass."),
    interval: int = typer.Option(15, help="Seconds between polls. Use 0 for single pass."),
    limit: int = typer.Option(20, help="Max alerts to surface per pass."),
) -> None:
    """Poll Splunk for unannotated alerts and prompt the analyst inline.

    The 'magic moment': fires whenever an alert closes without context, asks the
    analyst for a 10-second disposition + reason, persists to KV Store.
    Stop with Ctrl-C.
    """
    s = load()
    console.print(
        Panel.fit(
            f"Watching Splunk for unannotated alerts.\n"
            f"earliest={earliest}  interval={interval}s  annotations -> {s.kv_annotations}\n"
            f"Dispositions: [bold]f[/bold]alse_positive  [bold]e[/bold]scalated  "
            f"[bold]s[/bold]uppressed  [bold]t[/bold]rue_positive  [bold]k[/bold]=skip  [bold]q[/bold]=quit",
            title="ima alerts watch",
            border_style="cyan",
        )
    )

    while True:
        try:
            alerts = _fetch_alerts(earliest, limit)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]fetch error[/red]: {exc}")
            if interval == 0:
                raise typer.Exit(code=1)
            time.sleep(interval)
            continue

        seen = _already_annotated_ids()
        new = [a for a in alerts if a.get("alert_id") and a["alert_id"] not in seen]

        if not new:
            console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')} no new unannotated alerts ({len(alerts)} in window).[/dim]")
        else:
            for a in new:
                action = _prompt_one(a)
                if action == "quit":
                    raise typer.Exit(code=0)

        if interval == 0:
            return
        time.sleep(interval)


def _prompt_one(alert: dict) -> str:
    """Render an alert and capture the analyst's disposition. Returns 'quit', 'skip', or 'saved'."""
    s = load()
    aid = alert.get("alert_id", "?")
    et = alert.get("event_type", "?")
    src = alert.get("src") or alert.get("source_ip") or ""
    dest = alert.get("dest") or alert.get("asset") or ""
    when = alert.get("_time", "")

    console.print(
        Panel(
            f"[bold]{aid}[/bold]  [yellow]{et}[/yellow]\n"
            f"time: {when}\n"
            f"src:  {src}\n"
            f"dest: {dest}",
            title=":rotating_light: unannotated alert",
            border_style="yellow",
        )
    )
    choice = Prompt.ask(
        "Disposition [f/e/s/t/k/q]",
        choices=list(DISPOSITION_KEYS) + ["k", "q"],
        default="k",
    )
    if choice == "q":
        return "quit"
    if choice == "k":
        console.print("[dim]skipped[/dim]")
        return "skip"

    disposition = DISPOSITION_KEYS[choice]
    reason = Prompt.ask("Reason (one sentence)")
    record = {
        "alert_id": aid,
        "event_type": et,
        "analyst": s.username or "me",
        "disposition": disposition,
        "reason": reason,
        "source_ip": src,
        "asset": dest,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    key = kvstore.insert(s.kv_annotations, record)
    console.print(f"[green]saved[/green] key={key}  disposition={disposition}\n")
    return "saved"


@app.command("annotate")
def annotate(
    alert_id: str = typer.Argument(..., help="Alert ID this annotation is about."),
    disposition: str = typer.Option(..., help="e.g. false_positive, escalated, suppressed."),
    reason: str = typer.Option(..., help="10-second free-text reason."),
    analyst: str = typer.Option("me", help="Analyst handle."),
    asset: str = typer.Option("", help="Affected asset (optional)."),
    source_ip: str = typer.Option("", help="Source IP (optional)."),
    event_type: str = typer.Option("", help="Event type (optional)."),
) -> None:
    """Record a one-liner annotation against an alert into KV Store."""
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
    console.print(f"[green]Saved[/green] annotation key={key}")
