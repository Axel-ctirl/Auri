"""Bread's command line interface.

python -m app.cli serve            # start the API (localhost by default)
python -m app.cli status           # GPU, dependencies, loaded model
python -m app.cli create-key       # mint an API key for LAN use
python -m app.cli init-db          # create tables and seed defaults
python -m app.cli check            # one-shot environment report
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlmodel import Session

from .config import get_settings
from .db import get_engine, init_db
from .security import ensure_lan_guard, generate_api_key
from .services.gpu import dependency_report, gpu_status, platform_summary

console = Console()
app = typer.Typer(help="Bread: a local-first coding assistant.", no_args_is_help=True)


@app.command()
def serve(
    host: str = typer.Option("", help="Override BREAD_HOST. Leave empty to use .env."),
    port: int = typer.Option(0, help="Override BREAD_PORT."),
    reload: bool = typer.Option(False, help="Auto-reload on code changes."),
) -> None:
    """Start the API server."""

    import uvicorn

    settings = get_settings()
    bind_host = host or settings.host
    bind_port = port or settings.port

    if bind_host not in {"127.0.0.1", "localhost", "::1"}:
        console.print(
            Panel(
                "\n".join(
                    [
                        f"You are about to bind Bread to [bold]{bind_host}[/bold].",
                        "",
                        "Anyone who can reach this port can chat with your model and",
                        "read whatever you indexed. Bread will require an API key, but",
                        "there is no transport encryption unless you put a reverse",
                        "proxy in front of it.",
                    ]
                ),
                title="[bold yellow]LAN binding[/bold yellow]",
                border_style="yellow",
            )
        )
        if not settings.allow_lan_binding and not typer.confirm("Continue?", default=False):
            raise typer.Abort()

    init_db(settings)
    uvicorn.run(
        "app.main:app",
        host=bind_host,
        port=bind_port,
        reload=reload,
        log_level=settings.log_level,
    )


@app.command("init-db")
def initialize_database() -> None:
    """Create the SQLite schema and seed the built-in catalogue."""

    settings = get_settings()
    init_db(settings)
    console.print(f"[green]Database ready:[/green] {settings.resolved_database_url}")


@app.command("create-key")
def create_key(label: str = typer.Option("local", help="A name you will recognise later.")) -> None:
    """Mint an API key. The plaintext is printed once and never stored."""

    settings = get_settings()
    init_db(settings)
    with Session(get_engine(settings)) as session:
        issued = generate_api_key(session, label)
    console.print(
        Panel(
            f"[bold]{issued.plaintext}[/bold]\n\n"
            "Store this now. Bread keeps only its SHA-256 hash.",
            title="New API key",
            border_style="green",
        )
    )


@app.command()
def status() -> None:
    """Print GPU, dependency and configuration status."""

    settings = get_settings()
    platform_info = platform_summary()
    gpu = gpu_status()

    table = Table(title="Bread status", show_header=False, border_style="cyan")
    table.add_row("Version", settings.app_version)
    table.add_row("Python", platform_info["python_version"])
    table.add_row("Platform", platform_info["platform"])
    table.add_row("Data directory", str(settings.data_dir))
    table.add_row("Model backend", settings.model_backend)
    table.add_row("Model id", settings.model_id)
    table.add_row("Quantization", settings.quantization_mode)
    table.add_row("Embedding model", settings.embedding_model_id)
    table.add_row("RAG", "on" if settings.rag_enabled else "off")
    table.add_row("CUDA available", "yes" if gpu["cuda_available"] else "no")
    for device in gpu.get("devices", []):
        table.add_row(
            f"GPU {device['index']}",
            f"{device['name']}  {device.get('total_memory_mb', 0) / 1024:.1f} GB",
        )
    console.print(table)

    deps = Table(title="Optional dependencies", border_style="cyan")
    deps.add_column("Package")
    deps.add_column("Installed")
    for name, installed in dependency_report().items():
        deps.add_row(name, "[green]yes[/green]" if installed else "[red]no[/red]")
    console.print(deps)

    for note in gpu.get("notes", []) + ensure_lan_guard(settings):
        console.print(f"[yellow]note:[/yellow] {note}")


@app.command()
def check(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output.")
) -> None:
    """Environment report suitable for pasting into a bug report."""

    settings = get_settings()
    payload = {
        "version": settings.app_version,
        "platform": platform_summary(),
        "gpu": gpu_status(),
        "dependencies": dependency_report(),
        "model_backend": settings.model_backend,
        "model_id": settings.model_id,
        "data_dir": str(settings.data_dir),
        "warnings": ensure_lan_guard(settings),
    }
    if json_output:
        console.print_json(json.dumps(payload))
    else:
        console.print(payload)


@app.command("system-prompt")
def show_system_prompt() -> None:
    """Print the active system prompt."""

    settings = get_settings()
    console.print(Panel(settings.system_prompt(), title=str(Path(settings.system_prompt_path))))


if __name__ == "__main__":
    app()
