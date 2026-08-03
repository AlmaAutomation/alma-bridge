# Alma Bridge — Plugin Architecture (Design-Only Stub)

**Status:** Stub — design-only scope, deferred to **Phase 8** of the [v1.2 Work Plan](./V1.2_WORK_PLAN.md).
**No implementation is proposed for v1.2.**

This placeholder exists so the plugin concept has a stable home. The authoritative design intent already lives in:

- [`alma-bridge-platform-direction.md` → "Expand plugin boundaries"](./alma-bridge-platform-direction.md) — plugin families, contracts, and non-negotiable rules (plugins return plans/evidence, never declare success; cannot bypass `PolicyGate`/`prefix_lock`; declare `plugin_id`+version; explicit registry at startup).
- [ARCHITECTURE_REPORT](./ARCHITECTURE_REPORT.md) TD7 — migrating app-specific legacy branches (e.g. Ascension) out of the core.

## Design questions to resolve in Phase 8 (before any code)

1. Registry shape: explicit startup registry vs. entry-point discovery (platform-direction mandates explicit, no untrusted dynamic loading in v1).
2. Contracts per plugin family: framework detector, dependency resolver, runtime installer, launch planner, verification strategy, knowledge provider.
3. Provenance: how `plugin_id`+version is threaded into `EvidenceReference` / regression baselines.
4. Boundary enforcement: plugins must sit on the core side of the authority line but be forbidden from calling `verification_gateway.declare_verified_session_success()`.

## Prerequisites

Phase 8 depends on a **decoupled core** (Phase 5) and a **converged planner** (Phase 7) so that "register a detector/planner without editing `learning/orchestrator.py`" becomes achievable.

Acceptance criteria for a future implementation phase are to be written here at the start of Phase 8.
