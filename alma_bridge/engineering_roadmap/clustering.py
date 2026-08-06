"""Deterministic registry-backed blocker clustering for engineering roadmap analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.expansion.models import EvidenceQualityLevel
from alma_bridge.engineering_roadmap.errors import EngineeringRoadmapError
from alma_bridge.engineering_roadmap.models import (
    BlockerClusterClassification,
    BlockerClusterSpec,
    BlockerClusteringResult,
    ProvisionalBlockerCluster,
    UnclusteredBlocker,
)
from alma_bridge.native_engineering.specifications import API_CAPABILITY_MAP
from alma_bridge.runtime_intelligence.family import (
    family_for_behavior,
    family_for_capability,
)
from alma_bridge.runtime_intelligence.models import BehaviorFamilyId

BLOCKER_CLUSTER_REGISTRY_VERSION = "blocker_cluster_registry_v1"

HARD_EXCLUSION_LIMITATION = "hard_excluded_or_high_risk"


class ParsedBlockerKind(str, Enum):
    UNKNOWN_API = "unknown_api"
    BEHAVIOR_GAP = "behavior_gap"
    UNSUPPORTED = "unsupported"


class BlockerClusterRegistryError(EngineeringRoadmapError):
    """Raised when the blocker cluster registry is invalid."""


@dataclass(frozen=True)
class ParsedBlocker:
    raw: str
    kind: Optional[ParsedBlockerKind]
    symbol: Optional[str]
    dll: Optional[str]
    parseable: bool
    reason: Optional[str] = None


def _dedupe_sorted(values: Iterable[str]) -> List[str]:
    return sorted(set(values))


def _build_registry() -> Tuple[BlockerClusterSpec, ...]:
    version = BLOCKER_CLUSTER_REGISTRY_VERSION
    specs = (
        BlockerClusterSpec(
            cluster_id="cluster.memory_mapped_file_v1",
            title="Memory-mapped file",
            api_symbols=[
                "CreateFileMappingW",
                "MapViewOfFile",
                "UnmapViewOfFile",
                "FlushViewOfFile",
            ],
            capability_id="memory.mapped_file",
            family_id=BehaviorFamilyId.MEMORY,
            prerequisite_capability_ids=["filesystem.basic_io", "memory.virtual_mapping"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.synchronization_primitives_v1",
            title="Synchronization primitives",
            api_symbols=[
                "CreateMutexW",
                "WaitForSingleObject",
                "WaitForSingleObjectEx",
                "InitializeCriticalSection",
                "InitializeCriticalSectionAndSpinCount",
                "EnterCriticalSection",
                "LeaveCriticalSection",
                "DeleteCriticalSection",
                "TryEnterCriticalSection",
            ],
            capability_id="threading.basic",
            family_id=BehaviorFamilyId.SYNCHRONIZATION,
            prerequisite_capability_ids=["process.threading"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.heap_management_v1",
            title="Heap management",
            api_symbols=[
                "GetProcessHeap",
                "HeapAlloc",
                "HeapFree",
                "HeapReAlloc",
                "HeapSize",
                "HeapValidate",
                "HeapCompact",
                "HeapCreate",
                "HeapDestroy",
            ],
            capability_id="memory.heap",
            family_id=BehaviorFamilyId.MEMORY,
            prerequisite_capability_ids=["crt.process_heap"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.file_position_locking_v1",
            title="File position and locking",
            api_symbols=[
                "SetFilePointer",
                "SetFilePointerEx",
                "SetEndOfFile",
                "LockFile",
                "LockFileEx",
                "UnlockFile",
                "UnlockFileEx",
            ],
            capability_id="filesystem.basic_io",
            behavior_id="file_position_and_locking",
            family_id=BehaviorFamilyId.FILESYSTEM,
            prerequisite_capability_ids=["filesystem.basic_io:open_existing_readwrite"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.directory_enumeration_v1",
            title="Directory enumeration",
            api_symbols=[
                "FindFirstFileW",
                "FindFirstFileExW",
                "FindNextFileW",
                "FindClose",
            ],
            capability_id="filesystem.directory_enumeration",
            family_id=BehaviorFamilyId.FILESYSTEM,
            prerequisite_capability_ids=["filesystem.basic_io"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.unicode_locale_v1",
            title="Unicode and locale transformation",
            api_symbols=[
                "MultiByteToWideChar",
                "WideCharToMultiByte",
                "CompareStringW",
                "LCMapStringW",
                "GetLocaleInfoW",
                "GetStringTypeW",
                "EnumSystemLocalesW",
                "GetACP",
                "GetOEMCP",
                "GetCPInfo",
            ],
            capability_id="crt.unicode_locale",
            family_id=BehaviorFamilyId.CRT,
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.threading_lifecycle_v1",
            title="Threading lifecycle",
            api_symbols=[
                "CreateThread",
                "ExitThread",
                "ResumeThread",
                "GetCurrentThread",
                "GetCurrentThreadId",
            ],
            capability_id="threading.basic",
            family_id=BehaviorFamilyId.SYNCHRONIZATION,
            prerequisite_capability_ids=["cluster.synchronization_primitives_v1"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.tls_fls_v1",
            title="TLS and FLS storage",
            api_symbols=[
                "TlsAlloc",
                "TlsFree",
                "TlsGetValue",
                "TlsSetValue",
                "FlsAlloc",
                "FlsFree",
                "FlsGetValue",
                "FlsSetValue",
            ],
            capability_id="crt.tls_fls",
            family_id=BehaviorFamilyId.CRT,
            prerequisite_capability_ids=["threading.basic"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.console_io_v1",
            title="Console and pipe I/O",
            api_symbols=[
                "ReadConsoleW",
                "WriteConsoleW",
                "GetConsoleMode",
                "SetConsoleTextAttribute",
                "GetConsoleScreenBufferInfo",
                "PeekNamedPipe",
                "CreatePipe",
            ],
            capability_id="console.io",
            family_id=BehaviorFamilyId.CONSOLE,
            prerequisite_capability_ids=["console.stdout"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.process_module_loading_v1",
            title="Process and module loading",
            api_symbols=[
                "LoadLibraryA",
                "LoadLibraryExW",
                "FreeLibrary",
                "FreeLibraryAndExitThread",
                "GetModuleHandleW",
                "GetModuleHandleExW",
                "TerminateProcess",
                "DuplicateHandle",
            ],
            capability_id="process.creation",
            family_id=BehaviorFamilyId.CRT,
            independently_implementable=False,
            limitations=[HARD_EXCLUSION_LIMITATION],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.file_metadata_v1",
            title="File metadata",
            api_symbols=[
                "GetFileAttributesA",
                "GetFileAttributesW",
                "GetFileAttributesExW",
                "SetFileAttributesW",
                "GetFileInformationByHandle",
                "GetFileSize",
                "GetFileSizeEx",
                "SetFileTime",
            ],
            capability_id="filesystem.metadata",
            family_id=BehaviorFamilyId.FILESYSTEM,
            prerequisite_capability_ids=["filesystem.basic_io"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.path_directory_operations_v1",
            title="Path and directory operations",
            api_symbols=[
                "GetCurrentDirectoryW",
                "SetCurrentDirectoryW",
                "GetFullPathNameA",
                "GetFullPathNameW",
                "GetTempPathA",
                "GetTempPathW",
                "CreateDirectoryW",
                "DeleteFileA",
                "DeleteFileW",
            ],
            capability_id="filesystem.path_directory",
            family_id=BehaviorFamilyId.FILESYSTEM,
            prerequisite_capability_ids=["filesystem.basic_io"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.seh_exceptions_v1",
            title="Structured exception handling",
            api_symbols=[
                "RaiseException",
                "RtlUnwind",
                "RtlUnwindEx",
                "RtlVirtualUnwind",
                "SetUnhandledExceptionFilter",
                "UnhandledExceptionFilter",
            ],
            capability_id="crt.error_handling",
            family_id=BehaviorFamilyId.CRT,
            prerequisite_capability_ids=["error.handling"],
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.timing_performance_v1",
            title="Timing and performance counters",
            api_symbols=[
                "QueryPerformanceCounter",
                "GetTickCount",
                "GetSystemTime",
                "GetSystemTimeAsFileTime",
                "GetSystemTimePreciseAsFileTime",
                "Sleep",
            ],
            capability_id="process.timing",
            family_id=BehaviorFamilyId.CRT,
            registry_version=version,
        ),
        BlockerClusterSpec(
            cluster_id="cluster.interlocked_slist_v1",
            title="Interlocked singly linked list",
            api_symbols=[
                "InitializeSListHead",
                "InterlockedPushEntrySList",
                "InterlockedFlushSList",
            ],
            capability_id="threading.interlocked",
            family_id=BehaviorFamilyId.SYNCHRONIZATION,
            prerequisite_capability_ids=["threading.basic"],
            registry_version=version,
        ),
    )
    return specs


BLOCKER_CLUSTER_REGISTRY: Tuple[BlockerClusterSpec, ...] = _build_registry()

BEHAVIOR_GAP_CLUSTER_SPECS: Dict[str, BlockerClusterSpec] = {
    "open_existing_readwrite": BlockerClusterSpec(
        cluster_id="behavior_gap.open_existing_readwrite",
        title="Open existing file read-write behavior gap",
        api_symbols=[],
        capability_id="filesystem.basic_io",
        behavior_id="open_existing_readwrite",
        family_id=BehaviorFamilyId.FILESYSTEM,
        prerequisite_capability_ids=["filesystem.basic_io/create_always_write"],
        registry_version=BLOCKER_CLUSTER_REGISTRY_VERSION,
        limitations=["known_behavior_gap"],
    ),
}


def _validate_registry(specs: Sequence[BlockerClusterSpec]) -> Dict[str, str]:
    symbol_to_cluster: Dict[str, str] = {}
    for spec in specs:
        for symbol in spec.api_symbols:
            if symbol in symbol_to_cluster:
                raise BlockerClusterRegistryError(
                    f"symbol {symbol!r} appears in both {symbol_to_cluster[symbol]!r} "
                    f"and {spec.cluster_id!r}"
                )
            symbol_to_cluster[symbol] = spec.cluster_id
    return symbol_to_cluster


_SYMBOL_TO_CLUSTER: Dict[str, str] = _validate_registry(BLOCKER_CLUSTER_REGISTRY)
_CLUSTER_BY_ID: Dict[str, BlockerClusterSpec] = {
    spec.cluster_id: spec for spec in BLOCKER_CLUSTER_REGISTRY
}


def parse_blocker(raw_blocker: str) -> ParsedBlocker:
    """Parse a blocker string into a deterministic structured form."""
    raw = (raw_blocker or "").strip()
    if not raw:
        return ParsedBlocker(
            raw=raw_blocker,
            kind=None,
            symbol=None,
            dll=None,
            parseable=False,
            reason="malformed_blocker",
        )

    if raw.startswith("unknown_api:"):
        payload = raw[len("unknown_api:") :]
        if "!" not in payload:
            return ParsedBlocker(
                raw=raw,
                kind=None,
                symbol=None,
                dll=None,
                parseable=False,
                reason="malformed_blocker",
            )
        dll, symbol = payload.split("!", 1)
        dll = dll.strip()
        symbol = symbol.strip()
        if not dll or not symbol or "*" in symbol or "?" in symbol:
            return ParsedBlocker(
                raw=raw,
                kind=None,
                symbol=None,
                dll=dll or None,
                parseable=False,
                reason="malformed_blocker",
            )
        return ParsedBlocker(
            raw=raw,
            kind=ParsedBlockerKind.UNKNOWN_API,
            symbol=symbol,
            dll=dll,
            parseable=True,
        )

    if raw.startswith("behavior_gap:"):
        behavior_id = raw[len("behavior_gap:") :].strip()
        if not behavior_id:
            return ParsedBlocker(
                raw=raw,
                kind=None,
                symbol=None,
                dll=None,
                parseable=False,
                reason="malformed_blocker",
            )
        return ParsedBlocker(
            raw=raw,
            kind=ParsedBlockerKind.BEHAVIOR_GAP,
            symbol=behavior_id,
            dll=None,
            parseable=True,
        )

    if "=" in raw:
        return ParsedBlocker(
            raw=raw,
            kind=ParsedBlockerKind.UNSUPPORTED,
            symbol=raw.split("=", 1)[0].strip() or None,
            dll=None,
            parseable=False,
            reason="unsupported_blocker_format",
        )

    return ParsedBlocker(
        raw=raw,
        kind=None,
        symbol=None,
        dll=None,
        parseable=False,
        reason="malformed_blocker",
    )


def _resolve_capability_metadata(
    spec: BlockerClusterSpec,
    matched_symbols: Sequence[str],
) -> Tuple[str, Optional[str], BehaviorFamilyId, BlockerClusterClassification]:
    mapped: List[Tuple[str, str, Optional[str]]] = []
    for symbol in matched_symbols:
        entry = API_CAPABILITY_MAP.get(symbol)
        if entry is not None:
            capability_id, behaviors = entry
            behavior_id = behaviors[0] if behaviors else None
            mapped.append((symbol, capability_id, behavior_id))

    if mapped:
        _, capability_id, behavior_id = mapped[0]
        family = family_for_behavior(behavior_id) if behavior_id else None
        if family is None:
            family = family_for_capability(capability_id)
        if family is None:
            family = spec.family_id
        resolved_behavior = behavior_id or spec.behavior_id
        classification = (
            BlockerClusterClassification.UNKNOWN
            if capability_id == "api.unknown"
            else BlockerClusterClassification.KNOWN
        )
        return capability_id, resolved_behavior, family, classification

    if spec.capability_id == "api.unknown":
        return spec.capability_id, spec.behavior_id, spec.family_id, BlockerClusterClassification.UNKNOWN

    return (
        spec.capability_id,
        spec.behavior_id,
        spec.family_id,
        BlockerClusterClassification.PROVISIONAL,
    )


def _assess_evidence_quality(evidence_references: Sequence[str]) -> EvidenceQualityLevel:
    refs = [ref for ref in evidence_references if ref]
    if len(refs) >= 2:
        return EvidenceQualityLevel.WEAK
    if refs:
        return EvidenceQualityLevel.INSUFFICIENT
    return EvidenceQualityLevel.INSUFFICIENT


def _assess_suitability(
    *,
    matched_symbol_count: int,
    capability_id: str,
    independently_implementable: bool,
    limitations: Sequence[str],
    evidence_snapshot_digest: str,
) -> Tuple[bool, str]:
    if matched_symbol_count <= 0:
        return False, "no_blockers_clustered"
    if capability_id == "api.unknown":
        return False, "capability_unknown"
    if HARD_EXCLUSION_LIMITATION in limitations:
        return False, HARD_EXCLUSION_LIMITATION
    if not independently_implementable:
        return False, "not_independently_implementable"
    if not (evidence_snapshot_digest or "").strip():
        return False, "missing_evidence_snapshot_digest"
    return True, "descriptive_bounded_cluster_only"


def compute_cluster_digest(cluster: ProvisionalBlockerCluster) -> str:
    payload: Mapping[str, object] = {
        "cluster_id": cluster.cluster_id,
        "title": cluster.title,
        "api_symbols": _dedupe_sorted(cluster.api_symbols),
        "capability_id": cluster.capability_id,
        "behavior_id": cluster.behavior_id or "",
        "family_id": cluster.family_id.value,
        "classification": cluster.classification.value,
        "prerequisite_capability_ids": _dedupe_sorted(cluster.prerequisite_capability_ids),
        "independently_implementable": cluster.independently_implementable,
        "fixture_available": cluster.fixture_available,
        "native_alma_coverage_percent": cluster.native_alma_coverage_percent,
        "evidence_quality": cluster.evidence_quality.value,
        "suitable_as_bounded_opportunity": cluster.suitable_as_bounded_opportunity,
        "suitability_reason": cluster.suitability_reason,
        "limitations": _dedupe_sorted(cluster.limitations),
        "evidence_references": _dedupe_sorted(cluster.evidence_references),
    }
    return sha256_v1(payload)


def compute_unclustered_digest(item: UnclusteredBlocker) -> str:
    payload: Mapping[str, object] = {
        "raw_blocker": item.raw_blocker,
        "parsed_symbol": item.parsed_symbol or "",
        "reason": item.reason,
        "evidence_references": _dedupe_sorted(item.evidence_references),
    }
    return sha256_v1(payload)


def compute_clustering_report_digest(
    *,
    clusters: Sequence[ProvisionalBlockerCluster],
    unclustered: Sequence[UnclusteredBlocker],
    registry_version: str,
    evidence_snapshot_digest: str,
) -> str:
    payload: Mapping[str, object] = {
        "clusters": sorted(cluster.digest for cluster in clusters),
        "unclustered": sorted(item.digest for item in unclustered),
        "registry_version": registry_version,
        "evidence_snapshot_digest": evidence_snapshot_digest,
    }
    return sha256_v1(payload)


def _build_api_cluster(
    spec: BlockerClusterSpec,
    matched_symbols: Sequence[str],
    *,
    evidence_snapshot_digest: str,
    evidence_references: Sequence[str],
    native_alma_coverage_by_capability: Optional[Mapping[str, float]],
    fixture_capabilities: Optional[Set[str]],
) -> ProvisionalBlockerCluster:
    symbols = _dedupe_sorted(matched_symbols)
    capability_id, behavior_id, family_id, classification = _resolve_capability_metadata(spec, symbols)
    limitations = _dedupe_sorted(spec.limitations)
    refs = _dedupe_sorted(evidence_references)
    coverage = None
    if native_alma_coverage_by_capability is not None:
        coverage = native_alma_coverage_by_capability.get(capability_id)
    fixture_available = bool(fixture_capabilities and capability_id in fixture_capabilities)
    suitable, suitability_reason = _assess_suitability(
        matched_symbol_count=len(symbols),
        capability_id=capability_id,
        independently_implementable=spec.independently_implementable,
        limitations=limitations,
        evidence_snapshot_digest=evidence_snapshot_digest,
    )
    cluster = ProvisionalBlockerCluster(
        cluster_id=spec.cluster_id,
        title=spec.title,
        api_symbols=symbols,
        capability_id=capability_id,
        behavior_id=behavior_id,
        family_id=family_id,
        classification=classification,
        prerequisite_capability_ids=_dedupe_sorted(spec.prerequisite_capability_ids),
        independently_implementable=spec.independently_implementable,
        fixture_available=fixture_available,
        native_alma_coverage_percent=coverage,
        evidence_quality=_assess_evidence_quality(refs),
        suitable_as_bounded_opportunity=suitable,
        suitability_reason=suitability_reason,
        limitations=limitations,
        evidence_references=refs,
        digest="",
    )
    return cluster.model_copy(update={"digest": compute_cluster_digest(cluster)})


def _build_behavior_gap_cluster(
    spec: BlockerClusterSpec,
    *,
    evidence_snapshot_digest: str,
    evidence_references: Sequence[str],
    native_alma_coverage_by_capability: Optional[Mapping[str, float]],
    fixture_capabilities: Optional[Set[str]],
) -> ProvisionalBlockerCluster:
    limitations = _dedupe_sorted(spec.limitations)
    refs = _dedupe_sorted(evidence_references)
    coverage = None
    if native_alma_coverage_by_capability is not None:
        coverage = native_alma_coverage_by_capability.get(spec.capability_id)
    fixture_available = bool(fixture_capabilities and spec.capability_id in fixture_capabilities)
    suitable, suitability_reason = _assess_suitability(
        matched_symbol_count=1,
        capability_id=spec.capability_id,
        independently_implementable=spec.independently_implementable,
        limitations=limitations,
        evidence_snapshot_digest=evidence_snapshot_digest,
    )
    cluster = ProvisionalBlockerCluster(
        cluster_id=spec.cluster_id,
        title=spec.title,
        api_symbols=[],
        capability_id=spec.capability_id,
        behavior_id=spec.behavior_id,
        family_id=spec.family_id,
        classification=BlockerClusterClassification.KNOWN,
        prerequisite_capability_ids=_dedupe_sorted(spec.prerequisite_capability_ids),
        independently_implementable=spec.independently_implementable,
        fixture_available=fixture_available,
        native_alma_coverage_percent=coverage,
        evidence_quality=_assess_evidence_quality(refs),
        suitable_as_bounded_opportunity=suitable,
        suitability_reason=suitability_reason,
        limitations=limitations,
        evidence_references=refs,
        digest="",
    )
    return cluster.model_copy(update={"digest": compute_cluster_digest(cluster)})


def cluster_blockers(
    blockers: Sequence[str],
    *,
    evidence_snapshot_digest: str,
    evidence_references: Sequence[str] = (),
    native_alma_coverage_by_capability: Optional[Mapping[str, float]] = None,
    fixture_capabilities: Optional[Set[str]] = None,
) -> BlockerClusteringResult:
    """Cluster parsed blockers using the deterministic registry."""
    deduped_blockers = _dedupe_sorted(blockers)
    symbol_hits: Dict[str, Set[str]] = {spec.cluster_id: set() for spec in BLOCKER_CLUSTER_REGISTRY}
    behavior_gaps: Set[str] = set()
    unclustered_items: List[UnclusteredBlocker] = []

    for raw in deduped_blockers:
        parsed = parse_blocker(raw)
        if not parsed.parseable:
            item = UnclusteredBlocker(
                raw_blocker=parsed.raw,
                parsed_symbol=parsed.symbol,
                reason=parsed.reason or "malformed_blocker",
                evidence_references=_dedupe_sorted(evidence_references),
                digest="",
            )
            unclustered_items.append(
                item.model_copy(update={"digest": compute_unclustered_digest(item)})
            )
            continue

        if parsed.kind == ParsedBlockerKind.BEHAVIOR_GAP:
            assert parsed.symbol is not None
            if parsed.symbol in BEHAVIOR_GAP_CLUSTER_SPECS:
                behavior_gaps.add(parsed.symbol)
            else:
                item = UnclusteredBlocker(
                    raw_blocker=parsed.raw,
                    parsed_symbol=parsed.symbol,
                    reason="known_behavior_gap_unregistered",
                    evidence_references=_dedupe_sorted(evidence_references),
                    digest="",
                )
                unclustered_items.append(
                    item.model_copy(update={"digest": compute_unclustered_digest(item)})
                )
            continue

        assert parsed.kind == ParsedBlockerKind.UNKNOWN_API
        assert parsed.symbol is not None
        cluster_id = _SYMBOL_TO_CLUSTER.get(parsed.symbol)
        if cluster_id is None:
            item = UnclusteredBlocker(
                raw_blocker=parsed.raw,
                parsed_symbol=parsed.symbol,
                reason="not_in_cluster_registry",
                evidence_references=_dedupe_sorted(evidence_references),
                digest="",
            )
            unclustered_items.append(
                item.model_copy(update={"digest": compute_unclustered_digest(item)})
            )
            continue
        symbol_hits[cluster_id].add(parsed.symbol)

    clusters: List[ProvisionalBlockerCluster] = []
    for spec in BLOCKER_CLUSTER_REGISTRY:
        matched = symbol_hits.get(spec.cluster_id) or set()
        if not matched:
            continue
        clusters.append(
            _build_api_cluster(
                spec,
                sorted(matched),
                evidence_snapshot_digest=evidence_snapshot_digest,
                evidence_references=evidence_references,
                native_alma_coverage_by_capability=native_alma_coverage_by_capability,
                fixture_capabilities=fixture_capabilities,
            )
        )

    for behavior_id in sorted(behavior_gaps):
        spec = BEHAVIOR_GAP_CLUSTER_SPECS[behavior_id]
        clusters.append(
            _build_behavior_gap_cluster(
                spec,
                evidence_snapshot_digest=evidence_snapshot_digest,
                evidence_references=evidence_references,
                native_alma_coverage_by_capability=native_alma_coverage_by_capability,
                fixture_capabilities=fixture_capabilities,
            )
        )

    clusters.sort(key=lambda cluster: cluster.cluster_id)
    unclustered_items.sort(key=lambda item: (item.reason, item.raw_blocker))

    clustered_blocker_count = sum(len(cluster.api_symbols) for cluster in clusters)
    clustered_blocker_count += len(behavior_gaps)
    report_digest = compute_clustering_report_digest(
        clusters=clusters,
        unclustered=unclustered_items,
        registry_version=BLOCKER_CLUSTER_REGISTRY_VERSION,
        evidence_snapshot_digest=evidence_snapshot_digest,
    )
    return BlockerClusteringResult(
        clusters=clusters,
        unclustered=unclustered_items,
        input_blocker_count=len(deduped_blockers),
        clustered_blocker_count=clustered_blocker_count,
        unclustered_blocker_count=len(unclustered_items),
        registry_version=BLOCKER_CLUSTER_REGISTRY_VERSION,
        evidence_snapshot_digest=evidence_snapshot_digest,
        report_digest=report_digest,
    )
