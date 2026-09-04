"""Bread's command line.

    bread                     the banner and what you can do
    bread ask "..."           one question, answered and verified
    bread chat                an interactive session
    bread memory add "..."    tell Bread something to remember
    bread check file.py       find invented APIs without running anything
    bread serve               start the API for the web interface
    bread doctor              what is installed, what is missing, what to do

Everything runs locally. The CLI talks to the same code the web interface does,
so a model loaded here behaves identically there.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from sqlmodel import Session

from .config import REPO_ROOT, get_settings
from .db import get_engine, init_db, new_session
from .security import ensure_lan_guard, generate_api_key
from .services import memory as memory_service
from .services.gpu import dependency_report, gpu_status, platform_summary

console = Console()

app = typer.Typer(
    help="Bread: a local-first coding assistant.",
    no_args_is_help=False,
    add_completion=False,
)
memory_app = typer.Typer(help="What Bread remembers between conversations.")
models_app = typer.Typer(help="Load, unload and inspect local models.")
app.add_typer(memory_app, name="memory")
app.add_typer(models_app, name="models")

BANNER_PATH = REPO_ROOT / "prompts" / "banner.txt"


def banner() -> Text:
    """The wordmark, coloured like a crust."""

    raw = BANNER_PATH.read_text(encoding="utf-8").rstrip("\n") if BANNER_PATH.exists() else "Bread"
    text = Text()
    shades = ["#f7e6cf", "#eecfa4", "#e2b273", "#d5954a", "#c07a2f", "#9d5f26"]
    for index, line in enumerate(raw.splitlines()):
        text.append(line + "\n", style=shades[min(index, len(shades) - 1)])
    return text


def show_banner(subtitle: str = "") -> None:
    console.print(banner(), end="")
    settings = get_settings()
    line = subtitle or (
        f"local coding assistant  ·  v{settings.app_version}  ·  "
        f"{settings.model_backend} backend"
    )
    console.print(f"[#66768a]{line}[/#66768a]\n")


@app.callback(invoke_without_command=True)
def main(context: typer.Context) -> None:
    """Show the banner when Bread is run with no command."""

    if context.invoked_subcommand is not None:
        return

    show_banner()
    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column(style="#e2b273")
    table.add_column(style="#94a1b0")
    for command, description in (
        ('bread ask "..."', "answer one question, checking the code it writes"),
        ("bread chat", "an interactive session with memory"),
        ('bread memory add "..."', "tell Bread something worth remembering"),
        ("bread memory list", "see what it remembers"),
        ("bread check file.py", "find invented APIs without running anything"),
        ("bread serve", "start the API and the web interface"),
        ("bread models list", "what is available and what is loaded"),
        ("bread doctor", "what is installed and what to do about it"),
    ):
        table.add_row(command, description)
    console.print(table)
    console.print("\n[#4a596b]bread --help for everything else[/#4a596b]")


# --------------------------------------------------------------------- asking
def _load_backend(settings: Any) -> Any:
    from .services.inference import registry

    return registry.get_or_autoload(settings)


def _build_turns(
    session: Session,
    settings: Any,
    question: str,
    *,
    use_memory: bool,
    project: Path | None,
) -> tuple[list[Any], list[Any]]:
    from .services.inference.base import ChatTurn

    base_prompt = settings.system_prompt()
    recalled: list[Any] = []
    if use_memory:
        base_prompt, recalled = memory_service.augment_system_prompt(
            session, base_prompt, question, project=project
        )
    return (
        [
            ChatTurn(role="system", content=base_prompt),
            ChatTurn(role="user", content=question),
        ],
        recalled,
    )


@app.command()
def ask(
    question: str = typer.Argument(..., help="What to ask."),
    verify: bool = typer.Option(
        True, help="Check the generated code and let Bread repair its own mistakes."
    ),
    attempts: int = typer.Option(3, help="How many repair rounds to allow."),
    remember_fixes: bool = typer.Option(
        False, "--remember-fixes", help="Store what needed repairing, so it is not repeated."
    ),
    use_memory: bool = typer.Option(True, "--memory/--no-memory"),
    project: Path | None = typer.Option(
        None, help="Scope memory to this project directory. Defaults to the current one."
    ),
    temperature: float = typer.Option(0.2),
    max_tokens: int = typer.Option(900),
    raw: bool = typer.Option(False, "--raw", help="Print the answer with no framing."),
) -> None:
    """Ask one question and check the code in the answer."""

    from .services.inference.base import GenerationParams
    from .services.quality.repair import generate_verified, memory_notes

    settings = get_settings()
    init_db(settings)
    project = project or Path.cwd()

    with new_session() as session:
        turns, recalled = _build_turns(
            session, settings, question, use_memory=use_memory, project=project
        )

        if not raw:
            show_banner()
            if recalled:
                console.print(
                    f"[#4a596b]recalled {len(recalled)} memory "
                    f"entr{'y' if len(recalled) == 1 else 'ies'}[/#4a596b]"
                )

        backend = _load_backend(settings)
        params = GenerationParams(
            temperature=temperature, max_new_tokens=max_tokens, top_p=settings.top_p
        )

        if not verify:
            answer = backend.generate(turns, params)
            _print_answer(answer, raw=raw)
            return

        def report_attempt(attempt: Any) -> None:
            if raw:
                return
            if attempt.problem_count:
                console.print(
                    f"[#d5954a]attempt {attempt.number}: "
                    f"{attempt.problem_count} problem(s), repairing[/#d5954a]"
                )
            elif attempt.number > 1:
                console.print(f"[#6ee7b7]attempt {attempt.number}: clean[/#6ee7b7]")

        with (
            console.status("[#c07a2f]thinking[/#c07a2f]", spinner="dots")
            if not raw
            else _NullContext()
        ):
            result = generate_verified(
                backend, turns, params, max_attempts=attempts, on_attempt=report_attempt
            )

        _print_answer(result.answer, raw=raw)

        if raw:
            return

        first = result.attempts[0].problem_count if result.attempts else 0
        if result.repaired:
            console.print(
                f"\n[#6ee7b7]Repaired {first - result.problems_remaining} problem(s) "
                "before showing you this.[/#6ee7b7]"
            )
        if result.problems_remaining:
            console.print(
                f"\n[#f87171]{result.problems_remaining} problem(s) remain. "
                "Read the code before running it.[/#f87171]"
            )
            for finding in result.attempts[-1].report.certain:
                console.print(
                    f"  [#f87171]line {finding.line}: {escape(finding.message)}[/#f87171]"
                )

        if remember_fixes:
            notes = memory_notes(result)
            for note in notes:
                memory_service.remember(session, note, kind="correction", source="correction")
            if notes:
                console.print(f"\n[#4a596b]remembered {len(notes)} correction(s)[/#4a596b]")


class _NullContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_: object) -> None:
        return None


def _print_answer(answer: str, *, raw: bool) -> None:
    if raw:
        print(answer)
        return
    console.print()
    for block in _split_blocks(answer):
        kind, language, body = block
        if kind == "code":
            console.print(Syntax(body, language or "text", theme="ansi_dark", word_wrap=True))
        else:
            console.print(Markdown(body.strip()))


def _split_blocks(text: str) -> list[tuple[str, str, str]]:
    """Split an answer into prose and fenced code, so code can be highlighted."""

    blocks: list[tuple[str, str, str]] = []
    buffer: list[str] = []
    language = ""
    in_code = False

    for line in (text or "").splitlines():
        if line.strip().startswith("```"):
            blocks.append(("code" if in_code else "prose", language, "\n".join(buffer)))
            buffer = []
            language = line.strip()[3:].strip() if not in_code else ""
            in_code = not in_code
            continue
        buffer.append(line)

    blocks.append(("code" if in_code else "prose", language, "\n".join(buffer)))
    return [block for block in blocks if block[2].strip()]


@app.command()
def chat(
    use_memory: bool = typer.Option(True, "--memory/--no-memory"),
    verify: bool = typer.Option(True, help="Check and repair generated code."),
    project: Path | None = typer.Option(None),
) -> None:
    """An interactive session. Type /help for the commands it understands."""

    from .services.inference.base import ChatTurn, GenerationParams
    from .services.quality.repair import generate_verified

    settings = get_settings()
    init_db(settings)
    project = project or Path.cwd()

    show_banner()
    console.print(
        "[#4a596b]/help for commands, /exit to leave. "
        "Everything stays on this machine.[/#4a596b]\n"
    )

    history: list[Any] = []
    params = GenerationParams(
        max_new_tokens=settings.max_new_tokens, temperature=settings.temperature
    )

    with new_session() as session:
        backend = _load_backend(settings)

        while True:
            try:
                line = console.input("[#e2b273]bread[/#e2b273] [#4a596b]›[/#4a596b] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[#4a596b]bye[/#4a596b]")
                return

            if not line:
                continue
            if line in {"/exit", "/quit"}:
                return
            if line == "/help":
                _chat_help()
                continue
            if line == "/clear":
                history = []
                console.print("[#4a596b]history cleared[/#4a596b]")
                continue
            if line.startswith("/remember "):
                entry = memory_service.remember(session, line[len("/remember ") :])
                console.print(f"[#6ee7b7]remembered:[/#6ee7b7] {escape(entry.content)}")
                continue
            if line == "/memory":
                _print_memory(memory_service.list_entries(session, limit=20))
                continue

            base_prompt = settings.system_prompt()
            if use_memory:
                base_prompt, _recalled = memory_service.augment_system_prompt(
                    session, base_prompt, line, project=project
                )

            turns = [
                ChatTurn(role="system", content=base_prompt),
                *history,
                ChatTurn(role="user", content=line),
            ]

            if verify:
                result = generate_verified(backend, turns, params)
                answer = result.answer
                if result.problems_remaining:
                    console.print(
                        f"[#f87171]{result.problems_remaining} unresolved code "
                        "problem(s) in this answer[/#f87171]"
                    )
            else:
                answer = backend.generate(turns, params)

            _print_answer(answer, raw=False)
            console.print()
            history.extend(
                [ChatTurn(role="user", content=line), ChatTurn(role="assistant", content=answer)]
            )
            history = history[-12:]


def _chat_help() -> None:
    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column(style="#e2b273")
    table.add_column(style="#94a1b0")
    for command, description in (
        ("/remember <text>", "store something for later sessions"),
        ("/memory", "show what is remembered"),
        ("/clear", "forget this conversation, keep long-term memory"),
        ("/exit", "leave"),
    ):
        table.add_row(command, description)
    console.print(table)


# --------------------------------------------------------------------- memory
@memory_app.command("add")
def memory_add(
    text: str = typer.Argument(..., help="What to remember."),
    kind: str = typer.Option("fact", help="fact, preference, convention or correction."),
    project: Path | None = typer.Option(
        None, help="Scope to a project directory instead of everywhere."
    ),
    pin: bool = typer.Option(False, "--pin", help="Always include this, regardless of relevance."),
) -> None:
    """Tell Bread something worth carrying between conversations."""

    settings = get_settings()
    init_db(settings)
    with new_session() as session:
        try:
            entry = memory_service.remember(
                session,
                text,
                kind=kind,
                scope="project" if project else "global",
                project=project,
                pinned=pin,
            )
        except ValueError as error:
            console.print(f"[#f87171]{error}[/#f87171]")
            raise typer.Exit(2) from None
    console.print(
        f"[#6ee7b7]remembered[/#6ee7b7] [#e2b273]{entry.kind}[/#e2b273]  "
        f"{escape(entry.content)}"
    )


@memory_app.command("list")
def memory_list(
    scope: str | None = typer.Option(None, help="global or project."),
    kind: str | None = typer.Option(None),
    project: Path | None = typer.Option(None),
) -> None:
    """Show what Bread remembers."""

    settings = get_settings()
    init_db(settings)
    with new_session() as session:
        entries = memory_service.list_entries(session, scope=scope, kind=kind, project=project)
    _print_memory(entries)


def _print_memory(entries: list[Any]) -> None:
    if not entries:
        console.print("[#4a596b]nothing remembered yet[/#4a596b]")
        return
    table = Table(box=None, header_style="#66768a", padding=(0, 2, 0, 0))
    table.add_column("id", style="#4a596b")
    table.add_column("kind", style="#e2b273")
    table.add_column("scope", style="#94a1b0")
    table.add_column("uses", justify="right", style="#94a1b0")
    table.add_column("remembered", style="#e3e7ec")
    for entry in entries:
        table.add_row(
            entry.id[:8],
            ("pinned " if entry.pinned else "") + entry.kind,
            entry.scope,
            str(entry.use_count),
            escape(entry.content[:88]),
        )
    console.print(table)


@memory_app.command("forget")
def memory_forget(
    entry_id: str = typer.Argument(..., help="The id, or its first characters.")
) -> None:
    """Remove one entry."""

    settings = get_settings()
    init_db(settings)
    with new_session() as session:
        entries = memory_service.list_entries(session, limit=1000)
        matches = [entry for entry in entries if entry.id.startswith(entry_id)]
        if not matches:
            console.print(f"[#f87171]no entry starting with {entry_id}[/#f87171]")
            raise typer.Exit(1)
        if len(matches) > 1:
            console.print(f"[#f87171]{entry_id} matches {len(matches)} entries[/#f87171]")
            raise typer.Exit(1)
        content = matches[0].content
        memory_service.forget(session, matches[0].id)
    console.print(f"[#4a596b]forgot:[/#4a596b] {escape(content[:70])}")


@memory_app.command("stats")
def memory_stats() -> None:
    """How much is remembered, and what gets used."""

    settings = get_settings()
    init_db(settings)
    with new_session() as session:
        summary = memory_service.stats(session)
    console.print_json(json.dumps(summary))


# --------------------------------------------------------------------- checks
@app.command()
def check(
    path: Path = typer.Argument(..., help="A Python file, or a model answer with fenced code."),
    no_import: bool = typer.Option(False, "--no-import", help="Syntax and names only."),
) -> None:
    """Find invented APIs in code without running any of it."""

    from .services.quality.api_check import check_answer, check_code

    text = path.read_text(encoding="utf-8")
    report = (
        check_code(text, allow_import=not no_import)
        if path.suffix == ".py"
        else check_answer(text, allow_import=not no_import)
    )

    if report.syntax_error:
        console.print(f"[#f87171]syntax error: {escape(str(report.syntax_error))}[/#f87171]")
        raise typer.Exit(1)

    for finding in report.certain:
        console.print(f"[#f87171]line {finding.line:>4}[/#f87171]  {escape(finding.message)}")
    for finding in report.likely:
        console.print(f"[#d5954a]line {finding.line:>4}[/#d5954a]  {escape(finding.message)}")

    if report.certain:
        console.print(f"\n[#f87171]{len(report.certain)} problem(s).[/#f87171]")
        raise typer.Exit(1)
    if report.likely:
        console.print("\n[#d5954a]Nothing provably wrong; the above is worth a look.[/#d5954a]")
        return
    console.print("[#6ee7b7]Every name and signature resolves.[/#6ee7b7]")


# --------------------------------------------------------------------- server
@app.command()
def serve(
    host: str = typer.Option("", help="Override BREAD_HOST."),
    port: int = typer.Option(0, help="Override BREAD_PORT."),
    reload: bool = typer.Option(False, help="Auto-reload on code changes."),
) -> None:
    """Start the API, and the web interface if it has been built."""

    import uvicorn

    settings = get_settings()
    bind_host = host or settings.host
    bind_port = port or settings.port

    show_banner()

    if bind_host not in {"127.0.0.1", "localhost", "::1"}:
        console.print(
            Panel(
                f"You are about to bind Bread to [bold]{bind_host}[/bold].\n\n"
                "Anyone who can reach this port can chat with your model and read\n"
                "whatever you indexed. An API key will be required, and there is no\n"
                "transport encryption without a reverse proxy in front.",
                title="[bold yellow]LAN binding[/bold yellow]",
                border_style="yellow",
            )
        )
        if not settings.allow_lan_binding and not typer.confirm("Continue?", default=False):
            raise typer.Abort()

    init_db(settings)
    console.print(f"[#4a596b]http://{bind_host}:{bind_port}  ·  docs at /docs[/#4a596b]\n")
    uvicorn.run(
        "app.main:app", host=bind_host, port=bind_port, reload=reload, log_level=settings.log_level
    )


# --------------------------------------------------------------------- models
@models_app.command("list")
def models_list() -> None:
    """Every model in the catalogue, and which one is loaded."""

    from sqlmodel import select

    from .models import ModelRecord
    from .services.inference import registry

    settings = get_settings()
    init_db(settings)
    status = registry.status()

    with new_session() as session:
        records = session.exec(select(ModelRecord).order_by(ModelRecord.name)).all()

    table = Table(box=None, header_style="#66768a", padding=(0, 2, 0, 0))
    table.add_column("", style="#6ee7b7")
    table.add_column("name", style="#e3e7ec")
    table.add_column("backend", style="#94a1b0")
    table.add_column("quant", style="#94a1b0")
    table.add_column("model id", style="#4a596b")
    for record in records:
        loaded = status.loaded and status.model_id == record.model_id
        table.add_row(
            "●" if loaded else "",
            record.name,
            record.backend,
            record.quantization_mode,
            record.model_id,
        )
    console.print(table)


@models_app.command("load")
def models_load(
    model_id: str = typer.Argument(..., help="A model id from `bread models list`."),
    confirm_download: bool = typer.Option(
        False, "--download", help="Allow fetching weights that are not cached."
    ),
) -> None:
    """Load a model into memory."""

    from .services.inference import registry

    settings = get_settings()
    init_db(settings)
    with console.status(f"[#c07a2f]loading {model_id}[/#c07a2f]", spinner="dots"):
        status = registry.load(
            settings, {"model_id": model_id, "confirm_download": confirm_download}
        )
    console.print(
        f"[#6ee7b7]loaded[/#6ee7b7] {status.model_id} "
        f"({status.backend}, {status.load_seconds}s)"
    )


@models_app.command("unload")
def models_unload() -> None:
    """Release the loaded model."""

    from .services.inference import registry

    status = registry.unload()
    console.print(f"[#4a596b]unloaded {status.model_id or 'nothing'}[/#4a596b]")


# ---------------------------------------------------------------- environment
@app.command()
def doctor() -> None:
    """What is installed, what is missing, and what to do about it."""

    settings = get_settings()
    platform_info = platform_summary()
    gpu = gpu_status()
    dependencies = dependency_report()

    show_banner("environment report")

    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column(style="#66768a")
    table.add_column(style="#e3e7ec")
    table.add_row("python", platform_info["python_version"])
    table.add_row("platform", platform_info["platform"])
    table.add_row("data directory", str(settings.data_dir))
    table.add_row("model backend", settings.model_backend)
    table.add_row("model", settings.model_id)
    table.add_row("cuda", "available" if gpu["cuda_available"] else "not available")
    for device in gpu.get("devices", []):
        table.add_row(
            f"gpu {device['index']}",
            f"{device['name']}  {(device.get('total_memory_mb') or 0) / 1024:.1f} GB",
        )
    console.print(table)

    missing = [name for name, installed in dependencies.items() if not installed]
    present = [name for name, installed in dependencies.items() if installed]
    console.print(f"\n[#6ee7b7]installed[/#6ee7b7]  {', '.join(present) or 'none'}")
    if missing:
        console.print(f"[#4a596b]missing[/#4a596b]    {', '.join(missing)}")

    advice: list[str] = []
    if not dependencies.get("torch"):
        advice.append(
            "Install PyTorch with CUDA before anything else: "
            "pip install torch --index-url https://download.pytorch.org/whl/cu128"
        )
    elif not gpu["cuda_available"]:
        advice.append(
            "torch is installed but sees no CUDA device. Check the driver, and that "
            "torch was built for a matching CUDA version."
        )
    if not dependencies.get("bitsandbytes") and settings.quantization_mode != "none":
        advice.append(
            f"QUANTIZATION_MODE is {settings.quantization_mode} but bitsandbytes is "
            "missing. Install it, or set QUANTIZATION_MODE=none."
        )
    if not dependencies.get("sentence_transformers"):
        advice.append(
            "Retrieval will use the hashing fallback encoder. "
            "pip install sentence-transformers for real semantic search."
        )
    for warning in ensure_lan_guard(settings):
        advice.append(warning)

    if advice:
        console.print()
        for item in advice:
            console.print(f"  [#d5954a]•[/#d5954a] {item}")
    else:
        console.print("\n[#6ee7b7]Everything Bread needs is installed.[/#6ee7b7]")


@app.command("init-db")
def initialize_database() -> None:
    """Create the SQLite schema and seed the built-in catalogue."""

    settings = get_settings()
    init_db(settings)
    console.print(f"[#6ee7b7]database ready[/#6ee7b7] {settings.resolved_database_url}")


@app.command("create-key")
def create_key(label: str = typer.Option("local", help="A name you will recognise later.")) -> None:
    """Mint an API key. The plaintext is printed once and never stored."""

    settings = get_settings()
    init_db(settings)
    with Session(get_engine(settings)) as session:
        issued = generate_api_key(session, label)
    console.print(
        Panel(
            f"[bold]{issued.plaintext}[/bold]\n\nStore this now. Bread keeps only its "
            "SHA-256 hash.",
            title="New API key",
            border_style="green",
        )
    )


@app.command()
def status() -> None:
    """A short status line, for scripts and prompts."""

    from .services.inference import registry

    settings = get_settings()
    model = registry.status()
    gpu = gpu_status()
    console.print(
        f"bread {settings.app_version} | backend {settings.model_backend} | "
        f"model {'loaded' if model.loaded else 'not loaded'} | "
        f"cuda {'yes' if gpu['cuda_available'] else 'no'}"
    )


@app.command("system-prompt")
def show_system_prompt() -> None:
    """Print the active system prompt."""

    settings = get_settings()
    console.print(Panel(settings.system_prompt(), title=str(Path(settings.system_prompt_path))))


def run() -> None:
    """Console-script entry point."""

    # Make `bread` work from anywhere without installing the backend package.
    backend_root = str(REPO_ROOT / "backend")
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    app()


if __name__ == "__main__":
    run()
