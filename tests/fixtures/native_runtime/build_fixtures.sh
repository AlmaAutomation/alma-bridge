#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/src"
BIN="$ROOT/bin"
SHIM="$(cd "$ROOT/../../../alma_bridge/native_runtime/shim" && pwd)"
mkdir -p "$BIN"

build_pe() {
  local src_name="$1"
  local out_name="$2"
  local bits="$3"
  local compiler=""
  if [[ "$bits" == "64" ]]; then
    compiler="${MINGW64:-x86_64-w64-mingw32-gcc}"
  else
    compiler="${MINGW32:-i686-w64-mingw32-gcc}"
  fi
  if ! command -v "$compiler" >/dev/null 2>&1; then
    echo "skip $out_name ($compiler not found)"
    return 0
  fi
  "$compiler" -O2 -o "$BIN/$out_name" "$SRC/$src_name" -lkernel32 -e entry -nostartfiles -Wl,--subsystem,console 2>/dev/null \
    || "$compiler" -O2 -o "$BIN/$out_name" "$SRC/$src_name" -lkernel32
  echo "built $BIN/$out_name"
}

build_pe hello64.c hello64.exe 64
build_pe hello32.c hello32.exe 32
for fixture in stdout_write stderr_write exit_code unicode_argv environment_read file_read file_write file_append_unsupported; do
  build_pe "${fixture}.c" "${fixture}.exe" 64
done

if command -v gcc >/dev/null 2>&1; then
  gcc -shared -fPIC -O2 -o "$SHIM/libalma_native_shim.so" \
    "$SHIM/pe_loader.c" "$SHIM/kernel32_shim.c"
  echo "built shim $SHIM/libalma_native_shim.so"
fi

if command -v python3 >/dev/null 2>&1; then
  ROOT="$ROOT" BIN="$BIN" python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
root = Path(os.environ["ROOT"])
bin_dir = Path(os.environ["BIN"])
manifest = {hashlib.sha256(pe.read_bytes()).hexdigest(): pe.name for pe in sorted(bin_dir.glob("*.exe"))}
(root / "manifest.json").write_text(json.dumps({"fixtures": manifest}, indent=2) + "\n")
print(f"updated manifest with {len(manifest)} digests")
PY
fi

echo "fixture build complete"
