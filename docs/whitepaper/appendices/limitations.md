# Current Limitations

This appendix lists known constraints documented in the Phase 1 architecture audit (2026-07-31) and ADRs. Items marked **Future work** are planned but not implemented.

## Architecture and data

1. **No unified persistence layer.** Approximately twenty modules each call `sqlite3.connect()` with ad-hoc schemas. Read-only adapters reach into private `_connect()` methods (`ARCHITECTURE_REPORT` R1).

2. **Application identity is hash equality only.** Cross-session correlation uses `file_hash`; same application across versions or paths may not correlate (R8, ADR-002 consequences).

3. **Scattered SQLite stores.** Beyond `outcomes.db`, profile stores, shadow stores, automation stores, compliance healing store, and graph tables each own separate schemas (`DATA_FLOW.md` §3).

4. **Core import cycles.** Eleven mutual import cycles in the core cluster resolved via function-local imports (`IMPORT_GRAPH`, R2).

5. **Monolithic core API router.** `api/routes.py` spans ~1,255 lines across seven tag groups (R3, A1).

## Boundaries and encapsulation

6. **Read→core predicate smell.** `knowledge` and `comparison` import `aggregate_verification_passed` from `session.stop_on_success_verification` — pure function, but crosses package boundary (R6).

7. **Incomplete forbidden-import list.** Boundary tests omit literal fragments for `planner`, `remediation`, `execution.`, `automation`, `operator` (R4).

8. **Private cross-package access.** `intelligence/repository.py` uses `outcomes._connect()`; `comparison/queries.py` calls private `_to_knowledge_ref` (TD5).

9. **Duplicated framework heuristics.** `intelligence/evidence.py` re-implements detection logic also in `compatibility/framework_detection.py` (TD3).

## Product and deployment

10. **No frontend in this repository.** Operator surfaces are HTTP JSON APIs, external UIs on other ports, and CLI (`SYSTEM_OVERVIEW` §2).

11. **Open-by-default API auth.** `api_key=None` leaves mutating endpoints unauthenticated on localhost (R5, `SECURITY.md`).

12. **Hardcoded dev CORS origins.** `:9002`, `:3000`, `:3001` pinned in `main.py` (R5).

## Platform tier behavior

13. **Graph lazy ingestion.** Graph materializes on query; no background indexer (ADR-003 consequences).

14. **Knowledge computed on read.** Phase 1 has no dedicated knowledge persistence tables (ADR-004 §7).

15. **Advisor Phase 1 skips graph service.** `graph_summary` built from knowledge profile only to avoid ingestion side effects (ADR-006 §4).

16. **Ask Alma classification is pattern-based.** Unsupported questions receive explicit limitation responses (ADR-007 consequences).

17. **Legacy sessions lack run environment.** `run_environment_json` absent on pre-ADR-008 sessions; fields remain null (ADR-008, ADR-009).

## Testing

18. **Full-suite test isolation debt.** Shared-DB bleed and polluters tracked in `docs/reviews/full-suite-test-isolation-triage.md` (R7).

## Performance

19. **No end-to-end bridge latency benchmarks.** Compliance scan concurrency is documented (~3.8× on 4-target scan in README); core `/bridge/run` path is **not yet benchmarked**.

## Extensibility

20. **Plugin architecture is design-only.** No registry or plugin contracts implemented (`plugin-architecture.md`, Phase 8).

21. **App-specific legacy branches remain in core.** e.g. Ascension layout code flagged for plugin migration (TD7).

## Schema and planning debt

22. **`CompatibilityBridgePlan` not wired as orchestrator input.** Planner role split between schema and `session/services/planner.py` (TD6).

23. **Compliance/autopilot lifecycle separate from ADR-001 bridge lifecycle.** Host-policy paths not wrapped in verification gateway (ADR-001 migration notes).
