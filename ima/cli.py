from __future__ import annotations

import typer

from . import __version__
from .commands import alerts as alerts_cmd
from .commands import auth as auth_cmd
from .commands import demo as demo_cmd
from .commands import knowledge as knowledge_cmd
from .commands import kv as kv_cmd
from .commands import mcp as mcp_cmd

app = typer.Typer(
    name="ima",
    help="Institutional Memory Agent - Splunk-native knowledge graph from analyst behavior.",
    no_args_is_help=True,
)

app.add_typer(auth_cmd.app, name="auth")
app.add_typer(kv_cmd.app, name="kv")
app.add_typer(alerts_cmd.app, name="alerts")
app.add_typer(knowledge_cmd.app, name="knowledge")
app.add_typer(demo_cmd.app, name="demo")
app.add_typer(mcp_cmd.app, name="mcp")


@app.command()
def version() -> None:
    """Print the ima version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
