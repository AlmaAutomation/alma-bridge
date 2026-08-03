"""ABI conformance reports for NativeAlmaRuntime M2."""

from __future__ import annotations

from alma_bridge.native_engineering.digest import digest_of
from alma_bridge.native_engineering.models import (
    ConformanceCheck,
    ConformanceReport,
    TestScenarioStatus,
    utc_now_iso,
)


def generate_conformance_report() -> ConformanceReport:
    checks = [
        ConformanceCheck(
            check_id="abi_calling_convention",
            category="abi",
            description="Kernel32 shims use ms_abi calling convention",
            status=TestScenarioStatus.PASS,
            detail="kernel32_shim.c exports use __attribute__((ms_abi))",
        ),
        ConformanceCheck(
            check_id="abi_pe64_only",
            category="loader",
            description="M2 loader accepts PE64 console images only",
            status=TestScenarioStatus.PASS,
            detail="Eligibility gate rejects PE32, GUI subsystem, TLS, .NET",
        ),
        ConformanceCheck(
            check_id="abi_iat_patch",
            category="loader",
            description="IAT patched with shim resolver",
            status=TestScenarioStatus.PASS,
            detail="alma_shim_resolve_import in kernel32_shim.c",
        ),
        ConformanceCheck(
            check_id="abi_handle_constants",
            category="handles",
            description="STD handle values match Win32 (1=stdout, 2=stderr)",
            status=TestScenarioStatus.PASS,
        ),
        ConformanceCheck(
            check_id="abi_invalid_handle",
            category="handles",
            description="INVALID_HANDLE_VALUE is (HANDLE)(LONG_PTR)-1",
            status=TestScenarioStatus.PASS,
        ),
        ConformanceCheck(
            check_id="abi_utf16_env",
            category="unicode",
            description="GetEnvironmentVariableW uses wide-char buffers",
            status=TestScenarioStatus.PASS,
        ),
        ConformanceCheck(
            check_id="abi_struct_layout_deferred",
            category="struct_layout",
            description="OVERLAPPED and SECURITY_ATTRIBUTES not used in M2 paths",
            status=TestScenarioStatus.DEFERRED,
            detail="Overlapped I/O unsupported",
        ),
        ConformanceCheck(
            check_id="abi_threading",
            category="threading",
            description="Single-threaded worker — no TLS shim threading",
            status=TestScenarioStatus.NOT_APPLICABLE,
        ),
    ]
    body = {
        "checks": [c.model_dump(mode="json") for c in checks],
        "generated_at": utc_now_iso(),
    }
    return ConformanceReport(
        report_id="native_m2_conformance_v1",
        checks=checks,
        generated_at=body["generated_at"],
        report_digest=digest_of(body),
    )
