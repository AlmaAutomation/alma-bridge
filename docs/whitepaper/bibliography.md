# Bibliography

References cited in the Alma Bridge technical white paper. Internal paths are relative to the repository root unless noted.

## Architecture Decision Records

1. ADR-001 — Authoritative Bridge Lifecycle and Verification Boundary. `docs/adr/ADR-001-authoritative-bridge-lifecycle.md`. Accepted 2026-07-13.
2. ADR-002 — Compatibility Intelligence Boundary. `docs/adr/ADR-002-compatibility-intelligence-boundary.md`. Accepted 2026-07-27.
3. ADR-003 — Compatibility Graph is Non-Authoritative and Evidence-Derived. `docs/adr/ADR-003-compatibility-graph-non-authoritative.md`. Accepted 2026-07-27.
4. ADR-004 — Compatibility Knowledge Aggregation is Non-Authoritative and Evidence-Derived. `docs/adr/ADR-004-compatibility-knowledge-aggregation.md`. Accepted 2026-07-28.
5. ADR-005 — Compatibility Regression Intelligence is Read-Only Profile Comparison. `docs/adr/ADR-005-compatibility-regression-intelligence.md`. Accepted 2026-07-28.
6. ADR-006 — AI Advisor is Read-Only and Deterministic in Phase 1. `docs/adr/ADR-006-ai-advisor-read-only-boundary.md`. Accepted 2026-07-28.
7. ADR-007 — Ask Alma is Evidence-Grounded and Read-Only. `docs/adr/ADR-007-ask-alma-evidence-grounded-qa.md`. Accepted 2026-07-28.
8. ADR-008 — Compatibility Run Environment and Application Catalog. `docs/adr/ADR-008-compatibility-run-environment-catalog.md`. Accepted.
9. ADR-009 — Environment-Aware Session Comparison. `docs/adr/ADR-009-environment-aware-session-comparison.md`. Accepted 2026-07-28.

## Phase 1 Architecture Audit (2026-07-31)

10. System Overview. `docs/architecture/SYSTEM_OVERVIEW.md`.
11. Layer Diagram. `docs/architecture/LAYER_DIAGRAM.md`.
12. Data Flow. `docs/architecture/DATA_FLOW.md`.
13. Read-Only Boundaries. `docs/architecture/READ_ONLY_BOUNDARIES.md`.
14. API Boundaries. `docs/architecture/API_BOUNDARIES.md`.
15. Import Graph. `docs/architecture/IMPORT_GRAPH.md`.
16. Dependency Graph. `docs/architecture/DEPENDENCY_GRAPH.md`.
17. Package Boundaries. `docs/architecture/PACKAGE_BOUNDARIES.md`.
18. Architecture Report. `docs/architecture/ARCHITECTURE_REPORT.md`.
19. Platform Direction. `docs/architecture/alma-bridge-platform-direction.md`.
20. Plugin Architecture (design-only). `docs/architecture/plugin-architecture.md`.
21. V1.2 Work Plan. `docs/architecture/V1.2_WORK_PLAN.md`.

## Reviews

22. Full-Suite Test Isolation Triage. `docs/reviews/full-suite-test-isolation-triage.md`.
23. Compatibility Profile Architecture Review. `docs/reviews/compatibility-profile-architecture-review.md`.
24. Compatibility Intelligence Phase 1 Regression Triage. `docs/reviews/compatibility-intelligence-phase1-regression-triage.md`.

## Repository root documentation

25. README. `README.md`.
26. SECURITY. `SECURITY.md`.
27. Testing conventions. `docs/testing.md`.

## Primary implementation modules (representative)

28. FastAPI application entry. `alma_bridge/main.py`.
29. API router aggregation. `alma_bridge/api/routes.py`.
30. Bridge orchestrator. `alma_bridge/learning/orchestrator.py`.
31. Verification gateway. `alma_bridge/session/verification_gateway.py`.
32. Verification engine. `alma_bridge/session/services/verification.py`.
33. Aggregate verification predicate. `alma_bridge/session/stop_on_success_verification.py`.
34. Outcomes store. `alma_bridge/storage/outcomes.py`.
35. Evidence bundle builder. `alma_bridge/intelligence/evidence.py`.
36. Automation runner. `alma_bridge/automation/runner.py`.
37. Sysdet importer. `alma_bridge/importers/sysdet.py`.
38. Graph service. `alma_bridge/graph/service.py`.
39. Knowledge service. `alma_bridge/knowledge/service.py`.
40. Regression service. `alma_bridge/regression/service.py`.
41. Comparison service. `alma_bridge/comparison/service.py`.
42. Advisor service. `alma_bridge/advisor/service.py`.
43. Ask Alma service. `alma_bridge/ask/service.py`.
44. Catalog service. `alma_bridge/catalog/service.py`.

## Tests (architecture enforcement)

45. Verification authority. `tests/test_verification_authority.py`.
46. Orchestrator authority. `tests/test_orchestrator_authority.py`.
47. Architecture invariants. `tests/test_architecture_invariants.py`.
48. Suite isolation. `tests/test_suite_isolation.py`.
49. Per-package boundary tests. `tests/*/test_*architecture_boundaries.py` (intelligence, graph, knowledge, regression, comparison, advisor, ask, catalog).

## External Alma projects (referenced, not in this repo)

50. almasysdet — binary scanning and static compatibility rules. Referenced in `README.md`.
51. alma_resolve — Wine/Proton launcher recovery scripts. Referenced in `README.md`.

## External standards and libraries (cited where used)

52. FastAPI — HTTP framework for `create_app()`.
53. Pydantic Settings — configuration via `ALMA_BRIDGE_*` environment prefix (`alma_bridge/config.py`).
54. SQLite3 — primary persistence (`storage/outcomes.py` and subsystem stores).
55. certifi — CA bundle for TLS compliance probes (`README.md`, compliance module).
56. scikit-learn HistGradientBoostingClassifier — strategy ranker training (`README.md`).

## White paper package (this directory)

57. Main document. `docs/whitepaper/alma_bridge_whitepaper.md`.
58. Self-review audit. `docs/whitepaper/appendices/self_review.md`.
