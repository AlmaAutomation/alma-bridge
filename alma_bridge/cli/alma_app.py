"""Official Alma command-line interface."""

from __future__ import annotations

import traceback
from typing import Any, Callable, Dict, List, Optional, TypeVar

import typer

from alma_bridge.cli import formatters, handlers, json_output
from alma_bridge.cli.version_info import get_version_info
from alma_bridge.runtime_intelligence.family import BehaviorFamilyId
from alma_bridge.runtime_intelligence.models import CorpusKind

T = TypeVar("T")

app = typer.Typer(
    name="alma",
    help="Alma Bridge — compatibility intelligence, runtime intelligence, and execution.",
    add_completion=False,
    no_args_is_help=True,
)


@app.callback()
def global_options(
    ctx: typer.Context,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout only"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Include traceback details on stderr"),
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_mode
    ctx.obj["verbose"] = verbose


def _console():
    return formatters.make_console()


def _emit_success(ctx: typer.Context, command: str, data: Dict[str, Any]) -> None:
    if ctx.obj.get("json"):
        json_output.emit_json({"command": command, "data": data})
        return
    render = _RICH_RENDERERS.get(command)
    if render is not None:
        render(_console(), data)


def _emit_failure(
    ctx: typer.Context,
    command: str,
    message: str,
    *,
    exit_code: int = 1,
    exc: Optional[BaseException] = None,
    code: str = "error",
) -> None:
    if ctx.obj.get("json"):
        json_output.emit_error(command, message, code=code)
        if ctx.obj.get("verbose") and exc is not None:
            typer.echo(traceback.format_exc(), err=True)
    else:
        formatters.print_error(_console(), message)
        if ctx.obj.get("verbose") and exc is not None:
            typer.echo(traceback.format_exc(), err=True)
    raise typer.Exit(code=exit_code)


def _run_command(
    ctx: typer.Context,
    command: str,
    action: Callable[[], T],
    *,
    serializer: Callable[[T], Dict[str, Any]],
    exit_code_fn: Optional[Callable[[T], Optional[int]]] = None,
) -> None:
    try:
        result = action()
    except handlers.FileNotFoundCliError as exc:
        _emit_failure(ctx, command, str(exc), exc=exc, code="file_not_found")
    except handlers.SessionNotFoundError as exc:
        _emit_failure(ctx, command, str(exc), exc=exc, code="session_not_found")
    except handlers.UnsupportedFileCliError as exc:
        _emit_failure(ctx, command, str(exc), exc=exc, code="unsupported_file")
    except ValueError as exc:
        _emit_failure(ctx, command, str(exc), exc=exc, code="invalid_argument")
    except typer.Exit:
        raise
    except KeyboardInterrupt:
        typer.echo("Interrupted", err=True)
        raise typer.Exit(code=130) from None
    except Exception as exc:
        _emit_failure(ctx, command, str(exc), exc=exc, code="internal_error")

    _emit_success(ctx, command, serializer(result))
    if exit_code_fn is not None:
        code = exit_code_fn(result)
        if code:
            raise typer.Exit(code=code)


def _render_analysis(console, data: Dict[str, Any]) -> None:
    formatters.print_analysis_from_payload(console, data)


def _render_predict(console, data: Dict[str, Any]) -> None:
    formatters.print_predict(console, data)


def _render_inspect(console, data: Dict[str, Any]) -> None:
    formatters.print_inspect(console, data)


def _render_run(console, data: Dict[str, Any]) -> None:
    formatters.print_run_from_payload(console, data)


def _render_verify(console, data: Dict[str, Any]) -> None:
    formatters.print_verify(console, data)


def _render_report(console, data: Dict[str, Any]) -> None:
    formatters.print_report(console, data)


def _render_providers(console, data: Dict[str, Any]) -> None:
    formatters.print_providers(console, data.get("providers") or [])


def _render_version(console, data: Dict[str, Any]) -> None:
    formatters.print_version(console, data)


_RICH_RENDERERS = {
    "analyze": _render_analysis,
    "predict": _render_predict,
    "inspect": _render_inspect,
    "run": _render_run,
    "verify": _render_verify,
    "report": _render_report,
    "providers": _render_providers,
    "version": _render_version,
}


@app.command("analyze")
def analyze_command(
    ctx: typer.Context,
    exe: str = typer.Argument(..., help="Path to PE executable"),
    persist: bool = typer.Option(False, "--persist", help="Persist analysis to the ACI repository"),
) -> None:
    """Run Compatibility Intelligence analysis on a PE binary (read-only)."""
    _run_command(
        ctx,
        "analyze",
        lambda: handlers.analyze_executable(exe, persist=persist),
        serializer=handlers.serialize_analysis,
    )


@app.command("predict")
def predict_command(
    ctx: typer.Context,
    exe: str = typer.Argument(..., help="Path to PE executable"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider for prediction snapshot"),
    persist: bool = typer.Option(
        False,
        "--persist",
        help="Persist immutable prediction snapshot (explicit opt-in)",
    ),
) -> None:
    """Run pre-execution prediction (non-authoritative; not verified compatibility)."""
    _run_command(
        ctx,
        "predict",
        lambda: handlers.predict_executable(exe, provider_id=provider, persist=persist),
        serializer=lambda payload: payload,
    )


@app.command("inspect")
def inspect_command(
    ctx: typer.Context,
    exe: str = typer.Argument(..., help="Path to PE executable"),
) -> None:
    """Display imports, capabilities, provider coverage, and confidence (read-only)."""
    _run_command(
        ctx,
        "inspect",
        lambda: handlers.inspect_executable(exe),
        serializer=lambda payload: payload,
    )


@app.command("run")
def run_command(
    ctx: typer.Context,
    exe: str = typer.Argument(..., help="Path to executable"),
    args: Optional[List[str]] = typer.Argument(None, help="Arguments forwarded to the executable"),
    strategy: Optional[str] = typer.Option(None, "--strategy", help="Preferred Bridge strategy id"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Reuse an existing session id"),
) -> None:
    """Execute through BridgeOrchestrator (existing execution authority only)."""
    _run_command(
        ctx,
        "run",
        lambda: handlers.run_executable(
            exe,
            args=list(args or []),
            preferred_strategy_id=strategy,
            session_id=session_id,
        ),
        serializer=handlers.serialize_run_result,
        exit_code_fn=lambda result: 0 if result.success else 2,
    )


@app.command("verify")
def verify_command(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Bridge session id"),
) -> None:
    """Show stored VerificationEngine results (does not re-run verification)."""
    _run_command(
        ctx,
        "verify",
        lambda: handlers.verify_session(session_id),
        serializer=lambda payload: payload,
    )


@app.command("report")
def report_command(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Bridge session id"),
    corpus: str = typer.Option("engineering", "--corpus", help="Runtime Intelligence corpus track"),
    family: str = typer.Option("filesystem", "--family", help="Behavior family id"),
) -> None:
    """Show Runtime Intelligence summary scoped to session corpus enrollment."""
    _run_command(
        ctx,
        "report",
        lambda: handlers.report_session(
            session_id,
            corpus=CorpusKind(corpus),
            family_id=BehaviorFamilyId(family),
        ),
        serializer=lambda payload: payload,
    )


@app.command("providers")
def providers_command(ctx: typer.Context) -> None:
    """List available runtime providers (read-only inventory)."""
    _run_command(
        ctx,
        "providers",
        handlers.list_providers,
        serializer=lambda providers: {"providers": providers},
    )


@app.command("version")
def version_command(ctx: typer.Context) -> None:
    """Show Alma version and engine metadata."""
    _run_command(
        ctx,
        "version",
        get_version_info,
        serializer=lambda info: info,
    )


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("Interrupted", err=True)
        raise typer.Exit(code=130) from None


if __name__ == "__main__":
    main()
