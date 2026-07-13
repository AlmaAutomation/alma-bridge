from __future__ import annotations

from typing import Iterable

from alma_bridge.learning.ranker import ranker_status
from alma_bridge.storage import outcomes


def _line(name: str, value: float | int, labels: dict[str, str] | None = None) -> str:
    if labels:
        label_text = ",".join(f'{key}="{val}"' for key, val in labels.items())
        return f"{name}{{{label_text}}} {value}"
    return f"{name} {value}"


def render_bridge_metrics() -> str:
    stats = outcomes.get_stats()
    ranker = ranker_status()
    metadata = ranker.get("metadata") or {}
    metrics = metadata.get("metrics") or {}

    lines: list[str] = [
        "# HELP alma_bridge_up Bridge API is running",
        "# TYPE alma_bridge_up gauge",
        _line("alma_bridge_up", 1),
        "# HELP alma_bridge_attempts_total Recorded bridge attempts",
        "# TYPE alma_bridge_attempts_total counter",
        _line("alma_bridge_attempts_total", stats.get("total_attempts", 0)),
        "# HELP alma_bridge_successes_total Successful bridge attempts",
        "# TYPE alma_bridge_successes_total counter",
        _line("alma_bridge_successes_total", stats.get("total_successes", 0)),
        "# HELP alma_bridge_success_rate Overall bridge success rate",
        "# TYPE alma_bridge_success_rate gauge",
        _line("alma_bridge_success_rate", stats.get("success_rate", 0.0)),
        "# HELP alma_bridge_ranker_loaded Whether ML ranker artifact is loaded",
        "# TYPE alma_bridge_ranker_loaded gauge",
        _line("alma_bridge_ranker_loaded", 1 if ranker.get("model_loaded") else 0),
    ]

    if metrics.get("f1") is not None:
        lines.extend(
            [
                "# HELP alma_bridge_ranker_f1 Ranker F1 score",
                "# TYPE alma_bridge_ranker_f1 gauge",
                _line("alma_bridge_ranker_f1", metrics["f1"]),
            ]
        )

    for item in stats.get("top_strategies", [])[:5]:
        lines.append(
            _line(
                "alma_bridge_strategy_attempts_total",
                item.get("attempts", 0),
                {"strategy_id": str(item.get("strategy_id", "unknown"))},
            )
        )

    return "\n".join(lines) + "\n"


def render_scanner_metrics(
    *,
    precision: float,
    recall: float,
    f1: float,
    extra_lines: Iterable[str] = (),
) -> str:
    lines = [
        "# HELP alma_scanner_up Scanner API is running",
        "# TYPE alma_scanner_up gauge",
        _line("alma_scanner_up", 1),
        "# HELP alma_scanner_ml_precision Scanner ML precision",
        "# TYPE alma_scanner_ml_precision gauge",
        _line("alma_scanner_ml_precision", precision),
        "# HELP alma_scanner_ml_recall Scanner ML recall",
        "# TYPE alma_scanner_ml_recall gauge",
        _line("alma_scanner_ml_recall", recall),
        "# HELP alma_scanner_ml_f1 Scanner ML F1",
        "# TYPE alma_scanner_ml_f1 gauge",
        _line("alma_scanner_ml_f1", f1),
        *extra_lines,
    ]
    return "\n".join(lines) + "\n"
