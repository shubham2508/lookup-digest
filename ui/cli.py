"""`digest ui`: the local debug UI."""
from __future__ import annotations

import typer


def ui(
    port: int = typer.Option(8765, "--port"),
    host: str = typer.Option("127.0.0.1", "--host"),
    no_browser: bool = typer.Option(False, "--no-browser", help="don't open the browser"),
) -> None:
    """Run digests and trace every stage and LLM call in the browser (stdlib server, localhost only)."""
    from .server import serve

    serve(host=host, port=port, open_browser=not no_browser)
