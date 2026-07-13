#!/usr/bin/env python3
"""Alma fleet agent — register with Bridge, heartbeat, or run automation locally."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def _post(url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc


def _get(url: str) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc


def cmd_register(args: argparse.Namespace) -> None:
    result = _post(
        f"{args.bridge_url.rstrip('/')}/automation/agent/register",
        {"agent_id": args.agent_id, "meta": {"source": "alma-agent-cli"}},
    )
    print(json.dumps(result, indent=2))


def cmd_heartbeat(args: argparse.Namespace) -> None:
    if not args.agent_id:
        raise SystemExit("--agent-id required for heartbeat")
    result = _post(
        f"{args.bridge_url.rstrip('/')}/automation/agent/heartbeat",
        {"agent_id": args.agent_id},
    )
    print(json.dumps(result, indent=2))


def cmd_run(args: argparse.Namespace) -> None:
    if not args.agent_id:
        raise SystemExit("--agent-id required for run")
    payload: Dict[str, Any] = {
        "agent_id": args.agent_id,
        "apply": args.apply,
        "allow_mutations": args.allow_mutations,
        "verify": not args.no_verify,
    }
    if args.scan_path:
        payload["scan_path"] = args.scan_path
    if args.recipe:
        payload["playbook_recipe"] = args.recipe
    if args.approval_token:
        payload["approval_token"] = args.approval_token
    if args.sudo_password:
        payload["sudo_password"] = args.sudo_password
    result = _post(
        f"{args.bridge_url.rstrip('/')}/automation/agent/run",
        payload,
    )
    print(json.dumps(result, indent=2))


def cmd_health(args: argparse.Namespace) -> None:
    result = _get(f"{args.bridge_url.rstrip('/')}/automation/health")
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Alma fleet automation agent")
    parser.add_argument(
        "--bridge-url",
        default="http://127.0.0.1:9010",
        help="Alma Bridge base URL",
    )
    parser.add_argument("--agent-id", help="Persistent agent identifier")

    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register", help="Register this host as a fleet agent")
    reg.set_defaults(func=cmd_register)

    hb = sub.add_parser("heartbeat", help="Send heartbeat + machine health")
    hb.set_defaults(func=cmd_heartbeat)

    run = sub.add_parser("run", help="Run full automation pipeline on this host")
    run.add_argument("--scan-path", help="Optional directory to scan")
    run.add_argument(
        "--recipe",
        choices=[
            "school-lab",
            "container-lab",
            "potato-browser-only",
            "full-legacy-x86",
            "connectivity-only",
        ],
        help="Built-in playbook recipe",
    )
    run.add_argument("--apply", action="store_true", help="Apply playbook steps")
    run.add_argument(
        "--allow-mutations",
        action="store_true",
        help="Allow sudo mutations (requires passwordless sudo or --sudo-password)",
    )
    run.add_argument("--approval-token", help="One-time approval token instead of allow_mutations")
    run.add_argument("--sudo-password", help="Sudo password (cached ~15 min)")
    run.add_argument("--no-verify", action="store_true", help="Skip post-apply verification")
    run.set_defaults(func=cmd_run)

    health = sub.add_parser("health", help="Fetch machine health dashboard data")
    health.set_defaults(func=cmd_health)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
