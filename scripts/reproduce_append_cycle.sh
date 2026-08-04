#!/usr/bin/env bash
# Reproduce native-alma append engineering cycle from clean environment.
# Usage: scripts/reproduce_append_cycle.sh [WORKTREE_DIR]
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

echo "==> Fresh venv"
python3 -m venv .venv-repro
# shellcheck disable=SC1091
source .venv-repro/bin/activate
pip install --upgrade pip -q
pip install -e ".[dev]" -q

echo "==> Build shim and fixtures"
bash tests/fixtures/native_runtime/build_fixtures.sh

echo "==> Verify fixture digests"
python3 - <<'PY'
import hashlib, json, sys
from pathlib import Path
manifest = json.loads(Path("tests/fixtures/native_runtime/manifest.json").read_text())
bin_dir = Path("tests/fixtures/native_runtime/bin")
for digest, name in manifest["fixtures"].items():
    path = bin_dir / name
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == digest, f"digest mismatch: {name}"
print(f"verified {len(manifest['fixtures'])} fixture digests")
PY

echo "==> Materialize durable work item store"
python3 -c "from alma_bridge.native_lab.bootstrap_append_cycle import materialize_committed_store; materialize_committed_store()"

echo "==> Append fixture matrix + security + anti-simulation"
pytest tests/native_runtime/test_append_behavior.py \
  tests/native_runtime/test_append_security.py \
  tests/native_runtime/test_anti_simulation.py \
  tests/runtime/test_append_conformance.py \
  tests/release/test_append_cycle_audit.py -q

echo "==> Platform suites"
pytest tests/native_lab tests/native_engineering tests/certification \
  tests/compatibility_intelligence tests/evidence tests/research -q

echo "==> Full backend suite"
pytest -q

echo "REPRODUCTION COMPLETE"
