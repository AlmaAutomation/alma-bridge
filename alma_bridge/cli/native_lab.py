"""CLI for Native Runtime Development Laboratory workflow coordination."""

from __future__ import annotations

import argparse
import json
import sys

from alma_bridge.native_lab.errors import NativeLabError
from alma_bridge.native_lab.models import NATIVE_LAB_SCHEMA_VERSION, WorkItemStatus
from alma_bridge.native_lab.service import NativeLabService


def _service() -> NativeLabService:
    return NativeLabService.shared()


def _cmd_list(_args: argparse.Namespace) -> int:
    items = _service().list_work_items()
    print(
        json.dumps(
            {
                "schema_version": NATIVE_LAB_SCHEMA_VERSION,
                "count": len(items),
                "work_items": [i.model_dump(mode="json") for i in items],
            },
            indent=2,
        )
    )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        item = _service().get_work_item(args.work_item_id)
        card = _service().get_engineering_card(args.work_item_id)
    except NativeLabError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "work_item": item.model_dump(mode="json"),
                "engineering_card": card.model_dump(mode="json"),
            },
            indent=2,
        )
    )
    return 0


def _cmd_create_from_candidate(args: argparse.Namespace) -> int:
    try:
        item = _service().create_from_candidate(args.candidate_id)
    except NativeLabError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(item.model_dump(mode="json"), indent=2))
    return 0


def _cmd_checklist(args: argparse.Namespace) -> int:
    try:
        checklist = _service().get_checklist(args.work_item_id)
    except NativeLabError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(checklist.model_dump(mode="json"), indent=2))
    return 0


def _cmd_attach_test_evidence(args: argparse.Namespace) -> int:
    try:
        reference = _service().attach_evidence(
            args.work_item_id,
            args.artifact,
            attached_by=args.attached_by or "cli",
        )
    except NativeLabError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(reference.model_dump(mode="json"), indent=2))
    return 0


def _cmd_request_certification(args: argparse.Namespace) -> int:
    try:
        event = _service().request_certification(args.work_item_id)
    except NativeLabError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(event.model_dump(mode="json"), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="alma-native-lab",
        description="Native Runtime Development Laboratory — human workflow coordination only",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List engineering work items").set_defaults(func=_cmd_list)

    show_p = sub.add_parser("show", help="Show work item and engineering card")
    show_p.add_argument("work_item_id")
    show_p.set_defaults(func=_cmd_show)

    create_p = sub.add_parser("create-from-candidate", help="Create work item from expansion candidate")
    create_p.add_argument("candidate_id")
    create_p.set_defaults(func=_cmd_create_from_candidate)

    checklist_p = sub.add_parser("checklist", help="Show deterministic checklist")
    checklist_p.add_argument("work_item_id")
    checklist_p.set_defaults(func=_cmd_checklist)

    attach_p = sub.add_parser("attach-test-evidence", help="Attach test evidence reference")
    attach_p.add_argument("work_item_id")
    attach_p.add_argument("artifact")
    attach_p.add_argument("--attached-by", default="cli")
    attach_p.set_defaults(func=_cmd_attach_test_evidence)

    cert_p = sub.add_parser("request-certification", help="Request certification review")
    cert_p.add_argument("work_item_id")
    cert_p.set_defaults(func=_cmd_request_certification)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
