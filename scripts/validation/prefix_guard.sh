#!/usr/bin/env bash
# Pre-run guard for shadow-validation-pilot-001 disposable prefix operations.
# Fails if source/destination paths are unsafe for validation mutations.
set -euo pipefail

PRIMARY_PREFIX="${PRIMARY_PREFIX:-$HOME/.local/share/alma-bridge/prefixes/803984cf-660}"
VALIDATION_ROOT="${VALIDATION_ROOT:-$HOME/.local/share/alma-bridge/prefixes/validation/pilot-001}"
SOURCE_PREFIX="${1:-}"
DEST_PREFIX="${2:-}"

die() { echo "prefix_guard: $*" >&2; exit 1; }

resolve() { realpath -m "$1" 2>/dev/null || readlink -f "$1"; }

PRIMARY_RP="$(resolve "$PRIMARY_PREFIX")"
ROOT_RP="$(resolve "$VALIDATION_ROOT")"

[[ -n "$SOURCE_PREFIX" ]] || die "usage: prefix_guard.sh <source_prefix> <dest_prefix>"
[[ -n "$DEST_PREFIX" ]] || die "usage: prefix_guard.sh <source_prefix> <dest_prefix>"

SOURCE_RP="$(resolve "$SOURCE_PREFIX")"
DEST_RP="$(resolve "$DEST_PREFIX")"

[[ "$SOURCE_RP" != "$DEST_RP" ]] || die "source and destination resolve to the same path: $SOURCE_RP"

case "$DEST_RP" in
  "$PRIMARY_RP"|"$PRIMARY_RP"/*) die "destination is inside primary prefix: $DEST_RP" ;;
esac

case "$SOURCE_RP" in
  "$ROOT_RP"/*) ;;
  "$PRIMARY_RP"|"$PRIMARY_RP"/*) ;;
  *) die "source prefix outside approved validation scope: $SOURCE_RP" ;;
esac

case "$DEST_RP" in
  "$ROOT_RP"/*) ;;
  *) die "destination outside campaign validation root: $DEST_RP" ;;
esac

if [[ -L "$DEST_PREFIX" ]]; then
  LINK_RP="$(resolve "$(readlink "$DEST_PREFIX")")"
  case "$LINK_RP" in
    "$PRIMARY_RP"|"$PRIMARY_RP"/*) die "destination symlink targets primary prefix: $LINK_RP" ;;
  esac
fi

if [[ -e "$SOURCE_PREFIX" && -e "$DEST_PREFIX" ]]; then
  SRC_DEV="$(stat -c '%d:%i' "$SOURCE_PREFIX")"
  DST_DEV="$(stat -c '%d:%i' "$DEST_PREFIX")"
  [[ "$SRC_DEV" != "$DST_DEV" ]] || die "source and destination share inode: $SRC_DEV"
fi

echo "prefix_guard: OK source=$SOURCE_RP dest=$DEST_RP"
