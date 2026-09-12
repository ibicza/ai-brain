"""Assess and optionally delete one marked project-generated M336K5 root."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_cleanup import (
    assess_m336k5_cleanup_candidate,
    delete_m336k5_cleanup_candidate,
    write_m336k5_project_generated_marker,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    marker = commands.add_parser("mark")
    marker.add_argument("--root", type=Path, required=True)
    marker.add_argument("--category", required=True)
    marker.add_argument("--terminal-run-id", required=True)
    marker.add_argument("--output", type=Path, required=True)
    delete = commands.add_parser("delete")
    delete.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "mark":
        marker_hash = write_m336k5_project_generated_marker(
            args.root,
            category=args.category,
            terminal_run_id=args.terminal_run_id,
        )
        body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336K5_CLEANUP_MARKER_RECEIPT",
            "category": args.category,
            "marker_hash": marker_hash,
            "status": "PASS",
        }
        write_canonical_json(args.output, {**body, "receipt_hash": content_hash(body)})
        return
    request = _object(args.request)
    expected = {
        "root",
        "category",
        "allowed_base_roots",
        "preservation_paths",
        "active_process_paths",
        "open_file_paths",
        "active_ledger_paths",
        "current_route_paths",
        "unique_evidence_paths",
        "unique_uncommitted_paths",
        "assessment_output",
        "receipt_output",
        "execute",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K5 cleanup request fields changed")
    assessment_output = Path(request.pop("assessment_output"))
    receipt_output = Path(request.pop("receipt_output"))
    execute = request.pop("execute")
    for name in tuple(request):
        if name.endswith("_paths") or name == "allowed_base_roots":
            request[name] = tuple(Path(value) for value in request[name])
    request["root"] = Path(request["root"])
    assessment = assess_m336k5_cleanup_candidate(**request)
    write_canonical_json(assessment_output, asdict(assessment))
    if execute is not True:
        return
    receipt = delete_m336k5_cleanup_candidate(request["root"], assessment)
    write_canonical_json(receipt_output, asdict(receipt))


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("M336K5 cleanup request is not an object")
    return value


if __name__ == "__main__":
    main()
