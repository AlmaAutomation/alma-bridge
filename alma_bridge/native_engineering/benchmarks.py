"""Performance and correctness benchmark definitions and runners."""

from __future__ import annotations

import hashlib
import platform
import statistics
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from alma_bridge.native_engineering.digest import digest_of
from alma_bridge.native_engineering.errors import BenchmarkExecutionError
from alma_bridge.native_engineering.models import (
    NATIVE_ENGINEERING_ENGINE_VERSION,
    BenchmarkBaselineStats,
    BenchmarkHostEnvironment,
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

APPEND_BASELINE_BENCHMARKS = [
    "append_existing_success.exe",
    "append_repeated.exe",
    "file_write.exe",
]

DEFAULT_WARMUP = 3
DEFAULT_ITERATIONS = 10
DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "native_runtime" / "bin"
SHIM_VERSION = "0.2.1-m2"


def list_benchmark_definitions() -> List[dict]:
    return [
        {"benchmark_id": meta["benchmark_id"], "fixture_name": name, "api_symbols": meta["apis"]}
        for name, meta in sorted(FIXTURE_BENCHMARKS.items())
    ]


def _fixture_digest(fixture_path: Path) -> str:
    if fixture_path.is_file():
        return hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    return ""


def _host_environment(fixture_path: Path) -> BenchmarkHostEnvironment:
    cpu = ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
    except OSError:
        cpu = platform.processor() or "unknown"
    compiler = "unknown"
    try:
        proc = subprocess.run(
            ["x86_64-w64-mingw32-gcc", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.stdout:
            compiler = proc.stdout.splitlines()[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return BenchmarkHostEnvironment(
        host_arch=platform.machine(),
        cpu_model=cpu,
        kernel_version=platform.release(),
        compiler=compiler,
        shim_version=SHIM_VERSION,
        fixture_digest=_fixture_digest(fixture_path),
        workspace_type="isolated_tmp",
    )


def _median_abs_deviation(values: List[float]) -> float:
    if not values:
        return 0.0
    med = statistics.median(values)
    return statistics.median(abs(v - med) for v in values)


def _run_single_timing(fixture_path: Path, workspace: Path) -> float:
    from alma_bridge.native_runtime.runtime import run_pe_in_workspace

    start = time.perf_counter()
    run_pe_in_workspace(fixture_path, env={"ALMA_TEST_VAR": "benchmark"}, workspace=workspace)
    return (time.perf_counter() - start) * 1000.0


def _run_fixture_benchmark(
    fixture_path: Path,
    *,
    benchmark_id: str,
    api_symbols: List[str],
    expect_failure: bool = False,
    warmup: int = 0,
    iterations: int = 1,
) -> BenchmarkResult:
    """Run timing benchmark via native runtime worker (explicit invocation only)."""
    if not fixture_path.is_file():
        raise BenchmarkExecutionError(f"Fixture not found: {fixture_path}")

    workspace = fixture_path.parent / "_bench_workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    samples: List[float] = []
    for _ in range(warmup):
        _run_single_timing(fixture_path, workspace)
    for _ in range(iterations):
        samples.append(_run_single_timing(fixture_path, workspace))

    elapsed_ms = statistics.median(samples) if samples else 0.0

    from alma_bridge.native_runtime.runtime import run_pe_in_workspace

    run_result = run_pe_in_workspace(
        fixture_path,
        env={"ALMA_TEST_VAR": "benchmark"},
        workspace=workspace,
    )
    exit_code = run_result.exit_code
    output_verified = bool(run_result.stdout or run_result.stderr or exit_code is not None)
    if expect_failure:
        output_verified = exit_code != 0 or not run_result.success

    baseline = None
    if iterations > 1 and samples:
        baseline = BenchmarkBaselineStats(
            warmup_count=warmup,
            iteration_count=iterations,
            median_ms=round(statistics.median(samples), 3),
            min_ms=round(min(samples), 3),
            max_ms=round(max(samples), 3),
            mean_ms=round(statistics.mean(samples), 3),
            stddev_ms=round(statistics.pstdev(samples), 3) if len(samples) > 1 else 0.0,
            mad_ms=round(_median_abs_deviation(samples), 3),
            sample_size=len(samples),
        )

    body = {
        "benchmark_id": benchmark_id,
        "fixture_name": fixture_path.name,
        "elapsed_ms": round(elapsed_ms, 3),
        "exit_code": exit_code,
        "sample_size": len(samples),
    }
    return BenchmarkResult(
        benchmark_id=benchmark_id,
        fixture_name=fixture_path.name,
        api_symbol=api_symbols[0] if api_symbols else "",
        metrics=[
            BenchmarkMetric(name="elapsed_ms", value=round(elapsed_ms, 3), unit="ms", tolerance_percent=25.0),
        ],
        baseline=baseline,
        host_environment=_host_environment(fixture_path),
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
    baseline: bool = False,
    warmup: int = DEFAULT_WARMUP,
    iterations: int = DEFAULT_ITERATIONS,
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
        warmup=warmup if baseline else 0,
        iterations=iterations if baseline else 1,
    )


def run_append_baseline_suite(
    *,
    fixtures_dir: Optional[Path] = None,
    allow_execution: bool = False,
) -> List[BenchmarkResult]:
    """Run reproducible append-cycle benchmark baselines."""
    return [
        run_benchmark(
            name,
            fixtures_dir=fixtures_dir,
            allow_execution=allow_execution,
            baseline=True,
        )
        for name in APPEND_BASELINE_BENCHMARKS
    ]


def run_all_benchmarks(
    *,
    fixtures_dir: Optional[Path] = None,
    allow_execution: bool = False,
) -> List[BenchmarkResult]:
    return [
        run_benchmark(name, fixtures_dir=fixtures_dir, allow_execution=allow_execution)
        for name in sorted(FIXTURE_BENCHMARKS.keys())
    ]
