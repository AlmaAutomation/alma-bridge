#!/usr/bin/env bash
# Canonical paths for shadow-validation-pilot-001 (no secrets).
export REPO="/home/joshua/Desktop/Alma/alma-bridge"
export API="http://127.0.0.1:9010"
export OPERATOR="Joshua"
export REVIEWER="Joshua/manual-review"
export ASCENSION_LAUNCHER="/home/joshua/.local/share/alma-bridge/prefixes/803984cf-660/drive_c/Program Files/Ascension Launcher/Ascension Launcher/Ascension Launcher.exe"
export INSTALLER_EXE="/home/joshua/Games/ascension-setup-1.0.101.exe"
export NATIVE_SCRIPT="/home/joshua/Desktop/Alma/alma-bridge/scripts/validation/native_timeout_probe.sh"
export PRIMARY_PREFIX="/home/joshua/.local/share/alma-bridge/prefixes/803984cf-660"
export VALIDATION_ROOT="/home/joshua/.local/share/alma-bridge/prefixes/validation/pilot-001"
export SOURCE_SNAPSHOT="${VALIDATION_ROOT}/source-prefix-snapshot"
export PREFIX_GUARD="${REPO}/scripts/validation/prefix_guard.sh"

export ALMA_BRIDGE_COMPATIBILITY_PROFILES_ENABLED=true
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_CREATION_ENABLED=true
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_SHADOW_MODE=true
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false
export ALMA_BRIDGE_OPERATOR_ENABLED=false
export ALMA_BRIDGE_OPERATOR_ALLOW_MUTATIONS=false
