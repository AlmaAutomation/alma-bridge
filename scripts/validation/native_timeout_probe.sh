#!/usr/bin/env bash
# Pilot-001 run 8 probe: native script that fails for an unrelated runtime reason.
# Not a compatibility mismatch — used only for shadow validation scenario H.
set -euo pipefail
echo "native_timeout_probe: sleeping then exiting with unrelated failure" >&2
sleep 3
exit 124
