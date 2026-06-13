from __future__ import annotations

from datetime import datetime, timedelta, timezone

import typer
from rich.console import Console
from rich.table import Table

from .. import kvstore
from ..config import load

app = typer.Typer(help="Demo data seeding and reset helpers.")
console = Console()


SEED_ANNOTATIONS = [
    # Cluster: failed_auth_burst :: false_positive (3 — strong pattern)
    {
        "alert_id": "NOTABLE-1001",
        "event_type": "failed_auth_burst",
        "disposition": "false_positive",
        "analyst": "harinath",
        "asset": "acct-prod-01",
        "source_ip": "10.42.1.7",
        "reason": "Finance batch job throws 400 failed auths every Monday 6am - expected, owned by FIN-ENG team.",
    },
    {
        "alert_id": "NOTABLE-1014",
        "event_type": "failed_auth_burst",
        "disposition": "false_positive",
        "analyst": "james",
        "asset": "acct-prod-01",
        "source_ip": "10.42.1.7",
        "reason": "Same Monday batch job firing again, finance accounting reconciliation. Ticket FIN-2204 tracks the suppression request.",
    },
    {
        "alert_id": "NOTABLE-1029",
        "event_type": "failed_auth_burst",
        "disposition": "false_positive",
        "analyst": "shiwani",
        "asset": "acct-prod-01",
        "source_ip": "10.42.1.7",
        "reason": "Finance Monday batch again. We should tune the correlation rule to exclude this asset+time window.",
    },
    # Cluster: dlp_exfil_attempt :: escalated (2 — real threat pattern)
    {
        "alert_id": "NOTABLE-1102",
        "event_type": "dlp_exfil_attempt",
        "disposition": "escalated",
        "analyst": "harinath",
        "asset": "laptop-eng-44",
        "source_ip": "10.99.4.22",
        "reason": "Engineer pushing 2GB to external Dropbox at 11pm - confirmed unauthorized after IR call. Endpoint quarantined.",
    },
    {
        "alert_id": "NOTABLE-1147",
        "event_type": "dlp_exfil_attempt",
        "disposition": "escalated",
        "analyst": "james",
        "asset": "laptop-sales-08",
        "source_ip": "10.99.7.11",
        "reason": "Sales rep uploading customer list to personal Gmail before leaving company. HR involved, legal hold issued.",
    },
    # Cluster: unusual_login :: false_positive (2 — known traveler pattern)
    {
        "alert_id": "NOTABLE-1203",
        "event_type": "unusual_login",
        "disposition": "false_positive",
        "analyst": "shiwani",
        "asset": "laptop-exec-ciso",
        "source_ip": "203.0.113.45",
        "reason": "CISO traveling - Singapore login is expected this week. Calendar shows the conference. Don't escalate her travel logins.",
    },
    {
        "alert_id": "NOTABLE-1221",
        "event_type": "unusual_login",
        "disposition": "false_positive",
        "analyst": "harinath",
        "asset": "laptop-exec-ciso",
        "source_ip": "203.0.113.99",
        "reason": "CISO London this time. Same pattern - international travel triggers geo-anomaly. Need an asset exception for executive travel.",
    },
    # Cluster: port_scan :: suppressed (2 — internal pentest pattern)
    {
        "alert_id": "NOTABLE-1305",
        "event_type": "port_scan",
        "disposition": "suppressed",
        "analyst": "james",
        "asset": "subnet-10.200.0.0_24",
        "source_ip": "10.200.0.45",
        "reason": "Internal Q2 pentest by RedTeam-3 against the staging subnet. Source IP is on the approved-scanner allowlist.",
    },
    {
        "alert_id": "NOTABLE-1318",
        "event_type": "port_scan",
        "disposition": "suppressed",
        "analyst": "shiwani",
        "asset": "subnet-10.200.0.0_24",
        "source_ip": "10.200.0.45",
        "reason": "Same RedTeam pentest, week 2. Source is sanctioned, ticket SEC-883.",
    },
    # Cluster: malware_signature :: escalated (1 — real malware)
    {
        "alert_id": "NOTABLE-1402",
        "event_type": "malware_signature",
        "disposition": "escalated",
        "analyst": "harinath",
        "asset": "laptop-eng-12",
        "source_ip": "10.99.4.55",
        "reason": "Cobalt Strike beacon detected, confirmed C2 traffic to 185.x.x.x. Endpoint isolated, IR playbook IR-CS-01 invoked.",
    },
]


@app.command("seed")
def seed(
    spread_days: int = typer.Option(14, help="Spread annotations over the last N days."),
    clear_first: bool = typer.Option(False, "--clear", help="Wipe ima_annotations and ima_knowledge first."),
) -> None:
    """Seed realistic demo annotations into KV Store."""
    s = load()
    if clear_first:
        _clear(s.kv_annotations)
        _clear(s.kv_knowledge)
        console.print("[yellow]Cleared annotations and knowledge collections.[/yellow]")

    now = datetime.now(timezone.utc)
    step = timedelta(days=spread_days) / max(len(SEED_ANNOTATIONS) - 1, 1)
    table = Table("alert_id", "event_type", "disposition", "asset", "analyst")
    written = 0
    for i, base in enumerate(SEED_ANNOTATIONS):
        record = dict(base)
        record["created_at"] = (now - (len(SEED_ANNOTATIONS) - 1 - i) * step).isoformat()
        kvstore.insert(s.kv_annotations, record)
        written += 1
        table.add_row(
            record["alert_id"],
            record["event_type"],
            record["disposition"],
            record["asset"],
            record["analyst"],
        )
    console.print(table)
    console.print(f"[green]Seeded[/green] {written} annotations into {s.kv_annotations}.")


def _clear(collection: str) -> None:
    rows = kvstore.query(collection)
    from ..splunk_client import service
    svc = service()
    coll = svc.kvstore[collection]
    for r in rows:
        try:
            coll.data.delete_by_id(r["_key"])
        except Exception:  # noqa: BLE001
            pass
