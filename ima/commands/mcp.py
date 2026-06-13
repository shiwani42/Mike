from __future__ import annotations

import typer
from rich.console import Console

from ..mcp_server import serve_http, serve_stdio

app = typer.Typer(help="Run the IMA MCP server.")
console = Console()


@app.command("serve")
def serve(
    http: bool = typer.Option(False, "--http", help="Use streamable-HTTP transport instead of stdio."),
    host: str = typer.Option("127.0.0.1", help="HTTP bind host (only with --http)."),
    port: int = typer.Option(8765, help="HTTP bind port (only with --http)."),
) -> None:
    """Launch the IMA MCP server.

    Default mode is stdio, which is what Claude Desktop and other IDE-style
    MCP clients expect. Use --http when you need a long-lived HTTP endpoint
    for remote autonomous agents.
    """
    if http:
        console.print(f"[cyan]MCP server (HTTP) starting on http://{host}:{port}/mcp[/cyan]")
        serve_http(host=host, port=port)
    else:
        # Don't print anything on stdout in stdio mode - the client uses stdout
        # for the MCP protocol stream.
        serve_stdio()
