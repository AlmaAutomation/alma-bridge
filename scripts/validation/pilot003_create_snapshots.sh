#!/usr/bin/env bash
# Create immutable Pilot-003 source snapshots from known-good Wine environments.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
PILOT003_ROOT="${HOME}/.local/share/alma-bridge/prefixes/validation/pilot-003"
SNAP_ROOT="${PILOT003_ROOT}/snapshots"
PILOT002_T2="${HOME}/.local/share/alma-bridge/prefixes/validation/pilot-002/snapshots/source-t2-notepad64-20260714T000425Z"
PILOT002_T3="${HOME}/.local/share/alma-bridge/prefixes/validation/pilot-002/snapshots/source-t3-wordpad64-20260714T000425Z"
METADATA_JSON="${REPO}/data/validation/evidence/pilot-003/source-snapshots-${TS}.json"

die() { echo "pilot003_create_snapshots: $*" >&2; exit 1; }

tree_hash() {
  python3 - "$1" <<'PY'
import hashlib, sys
from pathlib import Path
prefix = Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(prefix.rglob("*")):
    if path.is_file():
        digest.update(str(path.relative_to(prefix)).encode())
        digest.update(path.read_bytes())
print(digest.hexdigest())
PY
}

file_hash() {
  sha256sum "$1" | awk '{print $1}'
}

wine_version() {
  wine --version 2>/dev/null | head -1 || echo "unknown"
}

windows_version() {
  echo "win10"
}

clone_snapshot() {
  local src="$1"
  local dest="$2"
  [[ -d "$src" ]] || die "missing source snapshot: $src"
  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  cp -a "$src" "$dest"
  chmod -R a-w "$dest" || true
}

create_notepad32_snapshot() {
  local dest="$1"
  rm -rf "$dest"
  mkdir -p "$dest"
  chmod u+w "$dest"
  WINEPREFIX="$dest" WINEDEBUG=-all wineboot -i
  local exe="${dest}/drive_c/windows/syswow64/notepad.exe"
  [[ -f "$exe" ]] || die "notepad32 missing after wineboot: $exe"
  chmod -R a-w "$dest" || true
}

mkdir -p "$SNAP_ROOT" "${REPO}/data/validation/evidence/pilot-003"

T2_DEST="${SNAP_ROOT}/source-t2-notepad64-${TS}"
T3_DEST="${SNAP_ROOT}/source-t3-wordpad64-${TS}"
T32_DEST="${SNAP_ROOT}/source-t3-notepad32-${TS}"

clone_snapshot "$PILOT002_T2" "$T2_DEST"
clone_snapshot "$PILOT002_T3" "$T3_DEST"
create_notepad32_snapshot "$T32_DEST"

WINE_VER="$(wine_version)"
T2_EXE="${T2_DEST}/drive_c/windows/system32/notepad.exe"
T3_EXE="${T3_DEST}/drive_c/Program Files/Windows NT/Accessories/wordpad.exe"
T32_EXE="${T32_DEST}/drive_c/windows/syswow64/notepad.exe"

python3 - "$METADATA_JSON" "$TS" "$WINE_VER" "$T2_DEST" "$T3_DEST" "$T32_DEST" "$T2_EXE" "$T3_EXE" "$T32_EXE" <<'PY'
import hashlib, json, os, sys
from pathlib import Path

def tree_hash(prefix: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(prefix.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(prefix)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()

def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

out, ts, wine_ver, t2, t3, t32, t2e, t3e, t32e = sys.argv[1:10]
records = []
for key, dest, exe, arch in [
    ("t2_notepad64", t2, t2e, "win64"),
    ("t3_wordpad64", t3, t3e, "win64"),
    ("t3_notepad32", t32, t32e, "win32"),
]:
    dest_path = Path(dest)
    exe_path = Path(exe)
    records.append({
        "snapshot_key": key,
        "path": str(dest_path),
        "realpath": os.path.realpath(dest),
        "aggregate_sha256": tree_hash(dest_path),
        "wine_version": wine_ver,
        "prefix_architecture": arch,
        "windows_version": "win10",
        "target_executable_path": str(exe_path.relative_to(dest_path)),
        "target_executable_sha256": file_hash(exe_path),
        "created_at_utc": ts,
        "immutable": True,
        "source_provenance": "pilot-002 verified snapshot clone" if "notepad32" not in key else "fresh wineboot -i disposable prefix",
    })
payload = {
    "campaign_id": "shadow-validation-pilot-003",
    "created_at_utc": ts,
    "snapshots": records,
}
Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
PY

echo "Wrote ${METADATA_JSON}"
