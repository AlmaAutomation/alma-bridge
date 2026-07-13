#!/usr/bin/env bash
# shadow-validation-pilot-001 baseline freeze — run once before first pilot run.
set -euo pipefail

REPO="/home/joshua/Desktop/Alma/alma-bridge"
CAMPAIGN_ID="shadow-validation-pilot-001"
MANIFEST="$REPO/data/validation/campaigns/${CAMPAIGN_ID}.json"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
FREEZE_RECORD="$REPO/data/validation/logs/pilot-001/freeze-${TS}.json"

cd "$REPO"
source "$REPO/scripts/validation/pilot_env.sh"

sha256_file() { sha256sum "$1" | awk '{print $1}'; }

echo "=== 1. Git baseline ==="
GIT_BRANCH="$(git branch --show-current)"
GIT_SHA="$(git rev-parse HEAD)"
if [ -n "$(git status --porcelain)" ]; then
  echo "BLOCKER: Working tree dirty."
  git status --short
  exit 1
fi
echo "branch=$GIT_BRANCH sha=$GIT_SHA clean=true"

echo "=== 2. Campaign input hashes ==="
MANIFEST_HASH="$(sha256_file "$MANIFEST")"
CSV_HASH="$(sha256_file "$REPO/data/validation/campaigns/${CAMPAIGN_ID}-runs.csv")"
CMD_HASH="$(sha256_file "$REPO/data/validation/campaigns/${CAMPAIGN_ID}-commands.md")"
SCENARIO_HASH="$(sha256_file "$REPO/data/validation/shadow_scenario_manifest_v1.json")"
COMMIT_HASH="$(git rev-parse HEAD)"
COMMIT_TREE_HASH="$(git rev-parse 'HEAD^{tree}')"

echo "=== 3. Test suite (>=505 passed, 0 failed) ==="
START_TS=$(date +%s)
.venv/bin/pytest -q --tb=line -ra | tee "data/validation/logs/pilot-001/test-baseline-${TS}.log"
END_TS=$(date +%s)
RUNTIME_SEC=$((END_TS - START_TS))
PASS_LINE="$(grep -E '^[0-9]+ passed' data/validation/logs/pilot-001/test-baseline-${TS}.log | tail -1)"
PASS_COUNT="$(echo "$PASS_LINE" | awk '{print $1}')"
FAIL_COUNT="$(echo "$PASS_LINE" | awk '{print $4}' | tr -d ',')"
FAIL_COUNT="${FAIL_COUNT:-0}"
if [ "${PASS_COUNT:-0}" -lt 505 ] || [ "${FAIL_COUNT:-0}" -gt 0 ]; then
  echo "BLOCKER: Test baseline not met (passed=${PASS_COUNT:-0}, failed=${FAIL_COUNT:-0})"
  exit 1
fi

echo "=== 4. Backup outcomes.db ==="
mkdir -p data/validation/backups
DB_BACKUP="data/validation/backups/outcomes.db.bak.${TS}"
cp data/outcomes.db "$DB_BACKUP"
DB_BACKUP_HASH="$(sha256_file "$DB_BACKUP")"

echo "=== 5. Sync scenario manifest ==="
.venv/bin/alma-bridge-shadow-validation sync-manifest | tee "data/validation/logs/pilot-001/sync-manifest-${TS}.json"

echo "=== 6. Source prefix snapshot (read-only clone) ==="
mkdir -p "$VALIDATION_ROOT"
if [ ! -d "$SOURCE_SNAPSHOT" ]; then
  cp -a "$PRIMARY_PREFIX" "$SOURCE_SNAPSHOT"
  chmod -R a-w "$SOURCE_SNAPSHOT" || true
fi
SOURCE_SNAPSHOT_HASH="$(find "$SOURCE_SNAPSHOT" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')"

echo "=== 7. Evidence and log directories ==="
for n in $(seq -w 1 12); do
  mkdir -p "data/validation/evidence/pilot-001/run${n}"
done
mkdir -p data/validation/logs/pilot-001

echo "=== 8. Runtime versions ==="
PYTHON_VERSION="$(python3 --version | awk '{print $2}')"
OS_DIST="$(lsb_release -ds 2>/dev/null || grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"')"
KERNEL_VERSION="$(uname -r)"
WINE_VERSION="$(wine --version 2>/dev/null || echo null)"
PROTON_VERSION="${PROTON_VERSION:-null}"

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

manifest_path = Path("$MANIFEST")
manifest = json.loads(manifest_path.read_text())
manifest.update({
    "status": "in_progress",
    "git_commit_sha": "$GIT_SHA",
    "git_branch": "$GIT_BRANCH",
    "working_tree_clean": True,
    "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "outcomes_db_backup_path": "$DB_BACKUP",
    "outcomes_db_backup_sha256": "$DB_BACKUP_HASH",
    "wine_version": None if "$WINE_VERSION" == "null" else "$WINE_VERSION",
    "python_version": "$PYTHON_VERSION",
    "os_distribution": "$OS_DIST",
    "kernel_version": "$KERNEL_VERSION",
    "input_hashes": {
        "campaign_manifest_sha256": "$MANIFEST_HASH",
        "runs_csv_sha256": "$CSV_HASH",
        "commands_md_sha256": "$CMD_HASH",
        "scenario_manifest_sha256": "$SCENARIO_HASH",
        "git_commit_sha": "$COMMIT_HASH",
        "git_commit_tree_sha256": "$COMMIT_TREE_HASH",
        "db_backup_sha256": "$DB_BACKUP_HASH",
        "source_prefix_snapshot_aggregate_sha256": "$SOURCE_SNAPSHOT_HASH",
    },
    "test_baseline": {
        "required_passing": 505,
        "required_failures": 0,
        "verified_for_this_campaign": True,
        "passed": int("$PASS_COUNT"),
        "failed": int("$FAIL_COUNT"),
        "runtime_seconds": int("$RUNTIME_SEC"),
        "verified_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    },
})
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
PY

cat > "$FREEZE_RECORD" <<EOF
{
  "campaign_id": "${CAMPAIGN_ID}",
  "frozen_at_utc": "${TS}",
  "git_commit_sha": "${GIT_SHA}",
  "working_tree_clean": true,
  "test_passed": ${PASS_COUNT},
  "test_failed": ${FAIL_COUNT},
  "test_runtime_seconds": ${RUNTIME_SEC},
  "outcomes_db_backup_path": "${DB_BACKUP}",
  "outcomes_db_backup_sha256": "${DB_BACKUP_HASH}",
  "input_hashes": {
    "campaign_manifest_sha256": "${MANIFEST_HASH}",
    "runs_csv_sha256": "${CSV_HASH}",
    "commands_md_sha256": "${CMD_HASH}",
    "scenario_manifest_sha256": "${SCENARIO_HASH}",
    "git_commit_sha": "${COMMIT_HASH}",
    "git_commit_tree_sha256": "${COMMIT_TREE_HASH}",
    "db_backup_sha256": "${DB_BACKUP_HASH}",
    "source_prefix_snapshot_aggregate_sha256": "${SOURCE_SNAPSHOT_HASH}"
  }
}
EOF

echo "Freeze complete: $FREEZE_RECORD"
