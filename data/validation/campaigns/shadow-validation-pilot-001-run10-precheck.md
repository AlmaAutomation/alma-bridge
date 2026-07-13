# Run 10 precondition query (read-only)

```bash
source /home/joshua/Desktop/Alma/alma-bridge/scripts/validation/pilot_env.sh
python3 - <<'PY'
import sqlite3
from pathlib import Path

launcher = Path("$ASCENSION_LAUNCHER")
# Use hash from DB after run 1 seeds profile; fallback query by recent sessions.
conn = sqlite3.connect("data/outcomes.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
rows = cur.execute(
    """
    SELECT profile_id, profile_revision, trust_state, lifecycle_state,
           bridge_family_key, bridge_manifest_hash, executable_hash
    FROM compatibility_profiles
    WHERE lifecycle_state IN ('VERIFIED', 'ACTIVE')
      AND trust_state IN ('locally_verified', 'imported')
    ORDER BY profile_revision DESC
    """
).fetchall()
by_hash = {}
for r in rows:
    by_hash.setdefault(r["executable_hash"], []).append(dict(r))
print("profiles_by_hash:", {k: len(v) for k, v in by_hash.items()})
for h, group in by_hash.items():
    if len(group) >= 2:
        families = {g["bridge_family_key"] for g in group}
        manifests = {g["bridge_manifest_hash"] for g in group}
        print("CANDIDATE_SET_OK", h, "count", len(group), "families", families, "manifests", manifests)
PY
```

Block run 10 unless output contains `CANDIDATE_SET_OK` with count >= 2 and distinct family or manifest.
