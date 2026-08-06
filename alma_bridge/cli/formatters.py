"""Rich terminal formatters for Alma CLI output."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def make_console() -> Console:
    return Console(highlight=False)


def print_version(console: Console, info: Dict[str, Any]) -> None:
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    table.add_column("key", style="bold cyan")
    table.add_column("value")
    for key, value in info.items():
        table.add_row(key, str(value))
    console.print(Panel(table, title="Alma", border_style="blue"))


def print_providers(console: Console, providers: List[Dict[str, Any]]) -> None:
    table = Table(title="Runtime Providers", box=box.ROUNDED, header_style="bold magenta")
    table.add_column("Provider")
    table.add_column("Version")
    table.add_column("Experimental", justify="center")
    table.add_column("Capabilities")
    for entry in providers:
        caps = entry.get("capabilities") or {}
        cap_summary = ", ".join(f"{k}={v}" for k, v in sorted(caps.items())[:4])
        if len(caps) > 4:
            cap_summary += ", …"
        table.add_row(
            entry.get("provider_id", ""),
            entry.get("provider_version", ""),
            "yes" if entry.get("experimental") else "no",
            cap_summary,
        )
    console.print(table)


def print_analysis_from_payload(console: Console, data: Dict[str, Any]) -> None:
    header = Text.assemble(
        ("Analysis ", "bold"),
        (data.get("file_path", ""), "cyan"),
    )
    digest = data.get("binary_digest") or ""
    console.print(Panel(header, subtitle=f"digest {digest}", border_style="green"))
    pred = (data.get("prediction") or {})
    conf = pred.get("confidence") or {}
    provider_decision = data.get("provider_decision") or {}
    table = Table(box=box.SIMPLE_HEAD)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Binary digest", digest)
    table.add_row("Native compatible", _bool_label(pred.get("native_compatible")))
    table.add_row("Wine compatible", _bool_label(pred.get("wine_compatible")))
    table.add_row("Confidence", str(conf.get("level", "unknown")))
    table.add_row("Score", str(conf.get("score", "—")))
    table.add_row("Recommended provider", _recommended_label(provider_decision, pred))
    table.add_row("Highest coverage", _highest_coverage_label(provider_decision))
    coverage = data.get("coverage") or {}
    table.add_row("APIs analyzed", str(coverage.get("total_apis", "—")))
    console.print(table)


def print_analysis(console: Console, result: Any) -> None:
    from alma_bridge.cli import handlers

    print_analysis_from_payload(console, handlers.serialize_analysis(result))


def print_predict(console: Console, payload: Dict[str, Any]) -> None:
    provider_decision = payload.get("provider_decision") or {}
    selected = _selected_label(provider_decision, payload)
    recommended = _recommended_label(provider_decision, payload.get("prediction") or {})
    console.print(
        Panel(
            f"[bold yellow]Non-authoritative prediction[/] — not verified compatibility\n"
            f"{payload.get('disclaimer', '')}\n"
            f"[bold]Selected provider[/] [cyan]{selected}[/]\n"
            f"[bold]Recommended[/] [cyan]{recommended}[/]\n"
            f"[bold]Highest coverage[/] {_highest_coverage_label(provider_decision)}",
            title="Runtime Intelligence Prediction",
            border_style="blue",
        )
    )
    prediction = payload.get("prediction") or {}
    table = Table(box=box.SIMPLE_HEAD)
    table.add_column("Signal")
    table.add_column("Value")
    table.add_row("Native compatible", _bool_label(prediction.get("native_compatible")))
    table.add_row("Wine compatible", _bool_label(prediction.get("wine_compatible")))
    conf = prediction.get("confidence") or {}
    table.add_row("Confidence", str(conf.get("level", "unknown")))
    table.add_row("Evidence", prediction.get("evidence_summary") or "—")
    console.print(table)
    if payload.get("snapshot_id"):
        console.print(f"[dim]Snapshot persisted:[/] {payload['snapshot_id']}")


def print_inspect(console: Console, payload: Dict[str, Any]) -> None:
    console.print(
        Panel(
            f"{payload.get('file_path')}\n"
            f"[dim]{payload.get('architecture')} · {payload.get('subsystem')} · "
            f"{payload.get('import_count')} imports[/dim]",
            title="Inspect",
            border_style="cyan",
        )
    )
    conf = payload.get("confidence") or {}
    provider_decision = payload.get("provider_decision") or {}
    console.print(
        f"[bold]Confidence[/] {conf.get('level', 'unknown')} "
        f"({conf.get('score', '—')}) · "
        f"[bold]Recommended provider[/] [cyan]{_recommended_label(provider_decision, payload)}[/]"
    )
    highest = provider_decision.get("highest_coverage_provider")
    if highest and not provider_decision.get("highest_coverage_eligible"):
        console.print(
            f"[bold]Highest coverage[/] [cyan]{highest}[/] "
            f"({provider_decision.get('highest_coverage_percent', 0):.1f}%) "
            f"[yellow]— highest coverage, not eligible[/]"
        )
    _print_coverage_table(console, payload.get("provider_coverage") or [])
    _print_imports_table(console, payload.get("imports") or [], limit=12)
    _print_capabilities_table(console, payload.get("capabilities") or [])


def print_run_from_payload(console: Console, data: Dict[str, Any]) -> None:
    status = "[green]success[/]" if data.get("success") else "[red]failed[/]"
    console.print(
        Panel(
            f"Session [cyan]{data.get('session_id')}[/]\n"
            f"Outcome: {status}\n"
            f"{data.get('summary') or ''}",
            title="Run",
            border_style="green" if data.get("success") else "red",
        )
    )
    attempts = data.get("attempts") or []
    if attempts:
        table = Table(title="Attempts", box=box.SIMPLE)
        table.add_column("#", justify="right")
        table.add_column("Strategy")
        table.add_column("Runtime")
        table.add_column("Success")
        table.add_column("Exit")
        for attempt in attempts:
            table.add_row(
                str(attempt.get("attempt_number")),
                str(attempt.get("strategy_id")),
                str(attempt.get("runtime")),
                _bool_label(attempt.get("success")),
                str(attempt.get("exit_code") if attempt.get("exit_code") is not None else "—"),
            )
        console.print(table)


def print_run_result(console: Console, result: Any) -> None:
    from alma_bridge.cli import handlers

    print_run_from_payload(console, handlers.serialize_run_result(result))


def print_verify(console: Console, payload: Dict[str, Any]) -> None:
    status = payload.get("verification_status", "unverifiable")
    latest = payload.get("latest_verification")
    if status == "unverifiable":
        console.print(
            Panel(
                "No stored VerificationEngine results for this session.",
                title=f"Verify · {payload.get('session_id')} (unverifiable)",
                border_style="yellow",
            )
        )
        return
    passed = status == "verified"
    label = "[green]verified[/]" if passed else "[red]failed[/]"
    console.print(
        Panel(
            f"Stored verification status: {label}\n"
            f"Confidence: {(latest or {}).get('confidence')}\n"
            f"Reason: {(latest or {}).get('failure_reason') or '—'}",
            title=f"Verify · {payload.get('session_id')}",
            border_style="green" if passed else "red",
        )
    )
    checks = (latest or {}).get("checks") or []
    if checks:
        table = Table(box=box.SIMPLE_HEAD)
        table.add_column("Check")
        table.add_column("Kind")
        table.add_column("Passed")
        table.add_column("Confidence")
        for check in checks:
            table.add_row(
                check.get("verifier_id", ""),
                check.get("check_kind", ""),
                _bool_label(check.get("passed")),
                str(check.get("confidence")),
            )
        console.print(table)


def print_report(console: Console, payload: Dict[str, Any]) -> None:
    idx = payload.get("compatibility_index") or {}
    kn = payload.get("knowledge_coverage") or {}
    enrollment = payload.get("corpus_enrollment_status", "unknown")
    console.print(
        Panel(
            f"Session [cyan]{payload.get('session_id')}[/]\n"
            f"{payload.get('file_path')}\n"
            f"Corpus [bold]{payload.get('corpus')}[/] · Provider [cyan]{payload.get('provider_id')}[/] · "
            f"Family [cyan]{payload.get('family_id')}[/]\n"
            f"Corpus enrollment: [bold]{enrollment}[/]",
            title="Runtime Intelligence Summary",
            border_style="blue",
        )
    )
    if enrollment == "not_enrolled":
        console.print(
            "[yellow]Session binary is not enrolled in the selected corpus; "
            "Runtime Intelligence metrics are not borrowed from other corpora.[/]"
        )
    table = Table(box=box.ROUNDED)
    table.add_column("Metric")
    table.add_column("Status")
    table.add_column("Value")
    table.add_row("Compatibility Index", idx.get("status", "—"), _metric_value(idx.get("index_value")))
    table.add_row(
        "Knowledge Coverage",
        kn.get("status", "—"),
        _metric_value(kn.get("knowledge_coverage_value")),
    )
    console.print(table)
    snapshot = payload.get("prediction_snapshot")
    if snapshot:
        console.print(f"[dim]Prediction snapshot:[/] {snapshot.get('snapshot_id', '—')}")


def print_error(console: Console, message: str) -> None:
    console.print(Panel(message, title="Error", border_style="red"))


def _bool_label(value: Any) -> str:
    if value is True:
        return "[green]yes[/]"
    if value is False:
        return "[red]no[/]"
    return str(value)


def _recommended_label(provider_decision: Dict[str, Any], pred_or_payload: Dict[str, Any]) -> str:
    recommended = provider_decision.get("recommended_provider")
    if recommended is None:
        recommended = pred_or_payload.get("recommended_provider_id")
    return str(recommended) if recommended else "—"


def _highest_coverage_label(provider_decision: Dict[str, Any]) -> str:
    highest = provider_decision.get("highest_coverage_provider")
    if not highest:
        return "—"
    pct = provider_decision.get("highest_coverage_percent", 0)
    label = f"{highest} ({pct:.1f}%)"
    if not provider_decision.get("highest_coverage_eligible"):
        return f"{label} — highest coverage, not eligible"
    return label


def _selected_label(provider_decision: Dict[str, Any], payload: Dict[str, Any]) -> str:
    selected = provider_decision.get("selected_execution_provider")
    if selected is None:
        selected = payload.get("selected_provider_id")
    if provider_decision.get("prediction_status") == "no_eligible_provider":
        return "—"
    if selected is None and provider_decision.get("recommended_provider") is None:
        return "—"
    return str(selected) if selected else "—"


def _metric_value(value: Any) -> str:
    if value is None:
        return "[yellow]insufficient evidence[/]"
    return str(value)


def _print_coverage_table(console: Console, rows: Iterable[Dict[str, Any]]) -> None:
    table = Table(title="Provider Coverage", box=box.SIMPLE_HEAD)
    table.add_column("Provider")
    table.add_column("Coverage", justify="right")
    table.add_column("Supported", justify="right")
    table.add_column("Unsupported", justify="right")
    for row in rows:
        table.add_row(
            row.get("provider_id", ""),
            f"{row.get('coverage_percent', 0):.1f}%",
            str(row.get("supported", 0)),
            str(row.get("unsupported", 0)),
        )
    console.print(table)


def _print_imports_table(console: Console, imports: List[Dict[str, Any]], *, limit: int) -> None:
    table = Table(title=f"Imports (top {min(limit, len(imports))})", box=box.SIMPLE_HEAD)
    table.add_column("DLL")
    table.add_column("Function")
    for item in imports[:limit]:
        table.add_row(item.get("dll", ""), item.get("function", ""))
    console.print(table)


def _print_capabilities_table(console: Console, capabilities: List[Dict[str, Any]]) -> None:
    if not capabilities:
        return
    table = Table(title="Required Capabilities", box=box.SIMPLE_HEAD)
    table.add_column("Capability")
    table.add_column("Complexity")
    table.add_column("APIs")
    for cap in capabilities:
        apis = cap.get("required_by_apis") or []
        table.add_row(cap.get("capability_id", ""), cap.get("complexity", ""), ", ".join(apis[:3]))
    console.print(table)
