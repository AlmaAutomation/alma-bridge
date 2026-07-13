#!/usr/bin/env bash
# Pilot-002 native success probe: reproducible exit-0 script for profile validation.
# Distinct from native_timeout_probe.sh (scenario H unrelated failure).
set -euo pipefail
echo "native_success_probe: ok" >&2
exit 0
