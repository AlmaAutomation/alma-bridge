"""Safe execution of modernization playbook steps (sudo-gated, allowlisted)."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from alma_bridge.compliance.pm import detect_package_manager
from alma_bridge.config import settings
from alma_bridge.execution.privileges import prepare_sudo

# Step IDs that mutate system state and require sudo preparation.
PRIVILEGED_STEP_IDS = frozenset(
    {
        "clock_sync",
        "install_ca_bundle",
        "enable_multiarch",
        "install_i386_runtime",
        "install_browser",
        "tune_swappiness",
        "ldconfig_refresh",
    }
)

# Step IDs that only write under the user home directory.
USER_LOCAL_STEP_IDS = frozenset(
    {
        "write_browser_launcher",
        "school_desktop_shortcut",
    }
)
# Step IDs the apply engine knows how to run safely (fixed handlers, not arbitrary shell).
HANDLED_STEP_IDS = PRIVILEGED_STEP_IDS | USER_LOCAL_STEP_IDS

# Autopilot pathway remediation commands we allow when allow_mutations=True.
# Matched as prefixes after stripping leading sudo.
_ALLOWED_MUTATION_PREFIXES = (
    "timedatectl set-ntp",
    "ntpdate ",
    "chronyc makestep",
    "cp ",
    "update-ca-certificates",
    "dpkg --add-architecture",
    "apt-get update",
    "apt-get install",
    "apt install",
    "dnf install",
    "yum install",
    "pacman -Sy",
    "pacman -S ",
    "zypper install",
    "apk add",
    "ldconfig",
    "install -m",
    "mkdir -p",
    "tee ",
)


def _run_shell(command: str, *, timeout: float = 120.0, cwd: Optional[str] = None) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "command": command,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-3000:],
            "stderr": (proc.stderr or "")[-1500:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"command": command, "exit_code": None, "stdout": "", "stderr": "timeout", "ok": False}
    except Exception as exc:  # noqa: BLE001
        return {"command": command, "exit_code": None, "stdout": "", "stderr": str(exc), "ok": False}


def _privileged_shell(
    command: str,
    *,
    sudo_password: Optional[str] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Run a sudo command without a TTY (uses cached credentials or -S password)."""
    cmd = command.strip()
    if not cmd.startswith("sudo "):
        return _run_shell(cmd, timeout=timeout)

    core = cmd[5:].strip()
    # Non-interactive first — works after prepare_sudo() warms the ticket cache.
    result = _run_shell(f"sudo -n {core}", timeout=timeout)
    if result["ok"]:
        return result

    if sudo_password:
        try:
            proc = subprocess.run(
                ["sudo", "-S", "sh", "-c", core],
                input=f"{sudo_password}\n",
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "command": f"sudo -S {core}",
                "exit_code": proc.returncode,
                "stdout": (proc.stdout or "")[-3000:],
                "stderr": (proc.stderr or "")[-1500:],
                "ok": proc.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"command": cmd, "exit_code": None, "stdout": "", "stderr": "timeout", "ok": False}
        except Exception as exc:  # noqa: BLE001
            return {"command": cmd, "exit_code": None, "stdout": "", "stderr": str(exc), "ok": False}

    result["stderr"] = (
        (result.get("stderr") or "")
        + "\nHint: enter sudo password in the UI, run `sudo -v` in a terminal, "
        "or configure passwordless sudo for allowlisted commands."
    ).strip()
    return result


def _strip_sudo(cmd: str) -> str:
    return re.sub(r"^\s*sudo\s+", "", cmd.strip())


def is_allowed_mutation_command(command: str) -> bool:
    """True if this autopilot/playbook command is on the mutation allowlist."""
    if not command or not command.strip():
        return False
    core = _strip_sudo(command)
    if any(tok in core for tok in ("rm -", "mkfs", " dd ", ">|", "curl ", "wget ")):
        # curl/wget blocked for mutations except our CA handler uses Python urllib internally
        if not core.startswith("curl -s localhost") and "alma-ca" not in core:
            if core.startswith("curl ") or core.startswith("wget "):
                return False
    return any(core.startswith(prefix) for prefix in _ALLOWED_MUTATION_PREFIXES)


def _handler_clock_sync(_step: Dict[str, Any], **_ctx) -> Dict[str, Any]:
    pwd = _ctx.get("sudo_password")
    for cmd in (
        "sudo timedatectl set-ntp true",
        "sudo chronyc makestep",
        "sudo ntpdate pool.ntp.org",
    ):
        result = _privileged_shell(cmd, sudo_password=pwd, timeout=30)
        if result["ok"]:
            return result
    return result


def _handler_install_ca_bundle(step: Dict[str, Any], **_ctx) -> Dict[str, Any]:
    """Fetch Alma CA bundle and install into the system trust store."""
    import certifi
    import urllib.request

    ca_path = settings.compliance_ca_file or certifi.where()
    try:
        if ca_path.startswith("http"):
            with urllib.request.urlopen(ca_path, timeout=10) as resp:
                pem = resp.read().decode("utf-8")
        else:
            pem = Path(ca_path).read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return {"command": "fetch ca bundle", "ok": False, "stderr": str(exc), "exit_code": 1, "stdout": ""}

    tmp = Path(tempfile.gettempdir()) / "alma-ca-bundle.pem"
    tmp.write_text(pem, encoding="utf-8")

    if os.path.exists("/usr/local/share/ca-certificates"):
        cmd = (
            f"sudo cp {tmp} /usr/local/share/ca-certificates/alma-ca.crt && "
            "sudo update-ca-certificates"
        )
    elif os.path.exists("/etc/pki/ca-trust/source/anchors"):
        cmd = f"sudo cp {tmp} /etc/pki/ca-trust/source/anchors/alma-ca.pem && sudo update-ca-trust"
    else:
        return {
            "command": "install ca",
            "ok": True,
            "stdout": f"CA bundle saved to {tmp} — install manually for this distro",
            "stderr": "",
            "exit_code": 0,
        }
    return _privileged_shell(cmd, sudo_password=_ctx.get("sudo_password"), timeout=60)


def _handler_enable_multiarch(_step: Dict[str, Any], **_ctx) -> Dict[str, Any]:
    pm = _ctx.get("package_manager") or detect_package_manager()
    pwd = _ctx.get("sudo_password")
    if pm == "apt":
        return _privileged_shell(
            "sudo sh -c 'dpkg --add-architecture i386 && apt-get update'",
            sudo_password=pwd,
            timeout=180,
        )
    return {"command": "enable_multiarch", "ok": True, "stdout": "Not required for this package manager", "stderr": "", "exit_code": 0}


def _handler_install_i386_runtime(step: Dict[str, Any], **_ctx) -> Dict[str, Any]:
    pwd = _ctx.get("sudo_password")
    cmd = step.get("command")
    if cmd and is_allowed_mutation_command(cmd):
        return _privileged_shell(cmd, sudo_password=pwd, timeout=300)
    pm = _ctx.get("package_manager") or detect_package_manager()
    if pm == "apt":
        cmd = "sudo apt-get install -y libc6:i386 libstdc++6:i386 zlib1g:i386"
    elif pm in ("dnf", "yum"):
        cmd = f"sudo {pm} install -y glibc.i686 libstdc++.i686 zlib.i686"
    else:
        return {"command": "", "ok": False, "stderr": "unsupported package manager", "exit_code": 1, "stdout": ""}
    return _privileged_shell(cmd, sudo_password=pwd, timeout=300)


def _handler_install_browser(step: Dict[str, Any], **_ctx) -> Dict[str, Any]:
    cmd = step.get("command")
    if not cmd or not is_allowed_mutation_command(cmd):
        return {"command": cmd or "", "ok": False, "stderr": "blocked or missing install command", "exit_code": 1, "stdout": ""}
    return _privileged_shell(cmd, sudo_password=_ctx.get("sudo_password"), timeout=600)


def _handler_write_browser_launcher(step: Dict[str, Any], **_ctx) -> Dict[str, Any]:
    script = step.get("script_content") or step.get("launch_script")
    if not script:
        return {"command": "write launcher", "ok": False, "stderr": "no script content", "exit_code": 1, "stdout": ""}
    dest = Path.home() / ".local" / "bin" / "alma-browser"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(script if script.endswith("\n") else script + "\n", encoding="utf-8")
    dest.chmod(0o755)
    return {
        "command": f"write {dest}",
        "ok": True,
        "stdout": f"Launcher written to {dest}",
        "stderr": "",
        "exit_code": 0,
    }


def _handler_school_desktop_shortcut(_step: Dict[str, Any], **_ctx) -> Dict[str, Any]:
    launcher = Path.home() / ".local" / "bin" / "alma-browser"
    if not launcher.exists():
        return {
            "command": "school_desktop_shortcut",
            "ok": False,
            "stderr": "alma-browser launcher missing — run write_browser_launcher first",
            "stdout": "",
            "exit_code": 1,
        }
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop = desktop_dir / "alma-classroom-browser.desktop"
    content = (
        "[Desktop Entry]\n"
        "Name=Classroom Browser\n"
        "Comment=Alma potato-optimized browser for school lab\n"
        f"Exec={launcher}\n"
        "Icon=web-browser\n"
        "Terminal=false\n"
        "Type=Application\n"
        "Categories=Network;Education;\n"
    )
    desktop.write_text(content, encoding="utf-8")
    desktop.chmod(0o755)
    return {
        "command": f"write {desktop}",
        "ok": True,
        "stdout": f"Desktop shortcut written to {desktop}",
        "stderr": "",
        "exit_code": 0,
    }


def _handler_tune_swappiness(step: Dict[str, Any], **_ctx) -> Dict[str, Any]:
    pwd = _ctx.get("sudo_password")
    value = step.get("swappiness", 10)
    cmd = f"sudo sysctl -w vm.swappiness={int(value)}"
    r1 = _privileged_shell(cmd, sudo_password=pwd, timeout=10)
    persist = f"sudo sh -c \"echo 'vm.swappiness={int(value)}' > /etc/sysctl.d/99-alma-potato.conf\""
    r2 = _privileged_shell(persist, sudo_password=pwd, timeout=10)
    return r2 if r2["ok"] else r1


def _handler_ldconfig(_step: Dict[str, Any], **_ctx) -> Dict[str, Any]:
    return _privileged_shell("sudo ldconfig", sudo_password=_ctx.get("sudo_password"), timeout=30)


_STEP_HANDLERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "clock_sync": _handler_clock_sync,
    "install_ca_bundle": _handler_install_ca_bundle,
    "enable_multiarch": _handler_enable_multiarch,
    "install_i386_runtime": _handler_install_i386_runtime,
    "install_browser": _handler_install_browser,
    "write_browser_launcher": _handler_write_browser_launcher,
    "school_desktop_shortcut": _handler_school_desktop_shortcut,
    "tune_swappiness": _handler_tune_swappiness,
    "ldconfig_refresh": _handler_ldconfig,
}


def apply_playbook_steps(
    steps: List[Dict[str, Any]],
    *,
    step_ids: Optional[List[str]] = None,
    allow_mutations: bool = False,
    stop_on_error: bool = True,
    package_manager: Optional[str] = None,
    sudo_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Run selected playbook steps. Requires ``allow_mutations=True``."""
    if not allow_mutations:
        return {
            "applied": False,
            "success": False,
            "reason": "allow_mutations is false — plan only",
            "results": [],
        }

    wanted = set(step_ids) if step_ids else None
    selected_ids: List[str] = []
    for step in steps:
        sid = step.get("id")
        if step.get("kind") == "diagnostic":
            continue
        if wanted is not None and sid not in wanted:
            continue
        if sid in HANDLED_STEP_IDS or (
            step.get("command") and is_allowed_mutation_command(step.get("command"))
        ):
            selected_ids.append(str(sid))

    needs_sudo = any(sid in PRIVILEGED_STEP_IDS for sid in selected_ids) or any(
        step.get("id") not in HANDLED_STEP_IDS
        and step.get("command")
        and is_allowed_mutation_command(step.get("command"))
        for step in steps
        if (wanted is None or step.get("id") in wanted)
        and step.get("kind") != "diagnostic"
    )
    if needs_sudo:
        sudo_ok, sudo_err = prepare_sudo(requested=True, password=sudo_password)
        if not sudo_ok:
            return {
                "applied": False,
                "success": False,
                "reason": sudo_err,
                "results": [],
            }

    results: List[Dict[str, Any]] = []
    applied_any = False

    for step in steps:
        sid = step.get("id")
        if step.get("kind") == "diagnostic":
            continue
        if wanted is not None and sid not in wanted:
            continue
        if sid not in HANDLED_STEP_IDS:
            cmd = step.get("command")
            if cmd and is_allowed_mutation_command(cmd):
                result = _privileged_shell(cmd, sudo_password=sudo_password, timeout=300)
                result["step_id"] = sid
                results.append(result)
                applied_any = True
                if stop_on_error and not result["ok"]:
                    break
            continue

        handler = _STEP_HANDLERS.get(str(sid))
        if not handler:
            continue
        result = dict(handler(step, package_manager=package_manager, sudo_password=sudo_password))
        result["step_id"] = sid
        results.append(result)
        applied_any = True
        if stop_on_error and not result["ok"]:
            break

    return {
        "applied": applied_any,
        "success": all(r.get("ok") for r in results) if results else False,
        "results": results,
    }


def apply_pathway_steps(
    pathway: Dict[str, Any],
    *,
    allow_mutations: bool = False,
    stop_on_error: bool = True,
    timeout: float = 120.0,
    sudo_password: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run remediation steps from an autopilot pathway (mutation allowlist only)."""
    if not allow_mutations:
        return []

    sudo_ok, sudo_err = prepare_sudo(requested=True, password=sudo_password)
    if not sudo_ok:
        return [
            {
                "command": None,
                "ok": False,
                "stderr": sudo_err,
                "stdout": "",
                "exit_code": 1,
                "step_id": pathway.get("id"),
            }
        ]

    results: List[Dict[str, Any]] = []
    for step in pathway.get("steps") or []:
        if step.get("kind") == "diagnostic":
            continue
        cmd = step.get("command")
        if not cmd or not is_allowed_mutation_command(cmd):
            results.append(
                {
                    "command": cmd,
                    "ok": False,
                    "stderr": "blocked — not on mutation allowlist",
                    "stdout": "",
                    "exit_code": 1,
                    "step_id": step.get("description", "")[:40],
                }
            )
            if stop_on_error:
                break
            continue
        if cmd.strip().startswith("sudo "):
            result = _privileged_shell(cmd, sudo_password=sudo_password, timeout=timeout)
        else:
            result = _run_shell(cmd, timeout=timeout)
        result["step_id"] = pathway.get("id")
        results.append(result)
        if stop_on_error and not result["ok"]:
            break
    return results
