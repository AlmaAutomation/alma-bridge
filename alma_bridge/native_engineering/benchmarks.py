"""Performance and correctness benchmark definitions and runners."""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from alma_bridge.native_engineering.digest import digest_of
from alma_bridge.native_engineering.errors import BenchmarkExecutionError
from alma_bridge.native_engineering.models import (
    NATIVE_ENGINEERING_ENGINE_VERSION,
    BenchmarkMetric,
    BenchmarkResult,
    utc_now_iso,
)

FIXTURE_BENCHMARKS = {
    "hello64.exe": {"benchmark_id": "runtime_hello64", "apis": ["GetStdHandle", "WriteFile", "ExitProcess"]},
    "stdout_write.exe": {"benchmark_id": "runtime_stdout_write", "apis": ["WriteFile"]},
    "stderr_write.exe": {"benchmark_id": "runtime_stderr_write", "apis": ["WriteFile"]},
    "exit_code.exe": {"benchmark_id": "runtime_exit_code", "apis": ["ExitProcess"]},
    "file_write.exe": {"benchmark_id": "runtime_file_write", "apis": ["CreateFileW", "WriteFile", "CloseHandle"]},
    "file_read.exe": {"benchmark_id": "runtime_file_read", "apis": ["CreateFileW", "ReadFile", "CloseHandle"]},
    "environment_read.exe": {"benchmark_id": "runtime_environment_read", "apis": ["GetEnvironmentVariableW", "ExitProcess"]},
    "unicode_argv.exe": {"benchmark_id": "runtime_unicode_argv", "apis": ["GetCommandLineW", "ExitProcess"]},
    "file_append_unsupported.exe": {
        "benchmark_id": "runtime_append_historical",
        "apis": ["CreateFileW", "WriteFile"],
    },
    "append_existing_success.exe": {
        "benchmark_id": "runtime_append_success",
        "apis": ["CreateFileW", "WriteFile", "CloseHandle"],
    },
    "append_repeated.exe": {
        "benchmark_id": "runtime_append_repeated",
        "apis": ["CreateFileW", "WriteFile", "CloseHandle"],
    },
    "append_unicode.exe": {
        "benchmark_id": "runtime_append_unicode",
        "apis": ["CreateFileW", "WriteFile", "CloseHandle"],
    },
}

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "native_runtime" / "bin"


def list_benchmark_definitions() -> List[dict]:
    return [
        {"benchmark_id": meta["benchmark_id"], "fixture_name": name, "api_symbols": meta["apis"]}
        for name, meta in sorted(FIXTURE_BENCHMARKS.items())
    ]


def _run_fixture_benchmark(
    fixture_path: Path,
    *,
    benchmark_id: str,
    api_symbols: List[str],
    expect_failure: bool = False,
) -> BenchmarkResult:
    """Run timing benchmark via native runtime worker (explicit invocation only)."""
    if not fixture_path.is_file():
        raise BenchmarkExecutionError(f"Fixture not found: {fixture_path}")

    from alma_bridge.native_runtime.runtime import run_pe_in_workspace

    workspace = fixture_path.parent / "_bench_workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    try:
        result = run_pe_in_workspace(
            fixture_path,
            env={"ALMA_TEST_VAR": "benchmark"},
            workspace=workspace,
        )
    except Exception as exc:
        raise BenchmarkExecutionError(str(exc)) from exc
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    exit_code = result.exit_code if hasattr(result, "exit_code") else getattr(result, "return_code", None)
    output_verified = bool(getattr(result, "stdout", "") or getattr(result, "stderr", "") or exit_code is not None)
    if expect_failure:
        output_verified = exit_code != 0 or not getattr(result, "success", True)

    body = {
        "benchmark_id": benchmark_id,
        "fixture_name": fixture_path.name,
        "elapsed_ms": round(elapsed_ms, 3),
        "exit_code": exit_code,
    }
    return BenchmarkResult(
        benchmark_id=benchmark_id,
        fixture_name=fixture_path.name,
        api_symbol=api_symbols[0] if api_symbols else "",
        metrics=[
            BenchmarkMetric(name="elapsed_ms", value=round(elapsed_ms, 3), unit="ms", tolerance_percent=25.0),
        ],
        exit_code=exit_code,
        output_verified=output_verified,
        recorded_at=utc_now_iso(),
        run_digest=digest_of(body),
        engine_version=NATIVE_ENGINEERING_ENGINE_VERSION,
    )


def run_benchmark(
    fixture_name: str,
    *,
    fixtures_dir: Optional[Path] = None,
    allow_execution: bool = False,
) -> BenchmarkResult:
    """Execute a single benchmark. Requires explicit allow_execution=True."""
    if not allow_execution:
        meta = FIXTURE_BENCHMARKS.get(fixture_name, {})
        return BenchmarkResult(
            benchmark_id=meta.get("benchmark_id", f"pending_{fixture_name}"),
            fixture_name=fixture_name,
            api_symbol=(meta.get("apis") or [""])[0],
            metrics=[BenchmarkMetric(name="elapsed_ms", value=0.0, unit="ms")],
            output_verified=False,
            recorded_at=utc_now_iso(),
            run_digest=digest_of({"fixture": fixture_name, "status": "not_executed"}),
        )

    meta = FIXTURE_BENCHMARKS.get(fixture_name)
    if meta is None:
        raise BenchmarkExecutionError(f"Unknown fixture benchmark: {fixture_name}")

    base = fixtures_dir or DEFAULT_FIXTURES_DIR
    return _run_fixture_benchmark(
        base / fixture_name,
        benchmark_id=meta["benchmark_id"],
        api_symbols=meta["apis"],
        expect_failure=meta.get("expect_failure", False),
    )


def run_all_benchmarks(
    *,
    fixtures_dir: Optional[Path] = None,
    allow_execution: bool = False,
) -> List[BenchmarkResult]:
    return [
        run_benchmark(name, fixtures_dir=fixtures_dir, allow_execution=allow_execution)
        for name in sorted(FIXTURE_BENCHMARKS.keys())
    ]
