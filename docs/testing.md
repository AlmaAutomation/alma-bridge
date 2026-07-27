# Testing guidelines

## Running the suite

```bash
source .venv/bin/activate
PYTHONPATH=. pytest -q
```

Tests use autouse fixtures in `tests/conftest.py` to isolate data paths, reset
settings, and stabilize shared module bindings. See
`docs/reviews/full-suite-test-isolation-triage.md` for a recent full-suite
isolation investigation.

## `sys.modules` manipulation

Some tests assert import boundaries by temporarily removing modules from
`sys.modules` and re-importing. **Any test that pops or replaces entries in
`sys.modules` must restore the previous state before exiting** — use a `try` /
`finally` block (or an equivalent fixture teardown) even when the assertion
passes.

Failure to restore leaves collection-time imports (for example
`BridgeOrchestrator` in test modules and `api.routes.orchestrator`) bound to a
stale module object while later `monkeypatch.setattr("alma_bridge.learning.orchestrator.*", …)`
calls patch a different object in `sys.modules`. Those failures pass in
isolation but break unrelated tests under a full `pytest -q` run.

Example pattern:

```python
saved = {mod: sys.modules.get(mod) for mod in modules_to_touch}
try:
    for mod in modules_to_touch:
        sys.modules.pop(mod, None)
    importlib.import_module("some.module")
    assert "forbidden.module" not in sys.modules
finally:
    for mod, previous in saved.items():
        if previous is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = previous
```

Regression coverage lives in `tests/test_suite_isolation.py`.

## Shared singletons and monkeypatch targets

- Prefer `monkeypatch.setattr` over bare assignment so teardown is automatic.
- When patching orchestrator behavior, target names on
  `alma_bridge.learning.orchestrator` (the module under test), not ad hoc copies.
- The FastAPI layer exposes a module-level `api.routes.orchestrator` singleton;
  client tests that call `/bridge/run` execute through that instance.
