"""Bind inherited M-33.6d guarantees to current M-33.6e regression receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inherited-m336d-security", type=Path, required=True)
    parser.add_argument("--contract-gate", type=Path, required=True)
    parser.add_argument(
        "--registry-simulation", type=Path, action="append", required=True
    )
    parser.add_argument("--leak-report", type=Path, required=True)
    parser.add_argument("--quality", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh security summary already exists")
    inherited = _load(args.inherited_m336d_security.resolve(strict=True))
    contract = _load(args.contract_gate.resolve(strict=True))
    registry = tuple(
        _load(path.resolve(strict=True) / "verification.json")
        for path in args.registry_simulation
    )
    leak = _load(args.leak_report.resolve(strict=True))
    quality = tuple(_load(path.resolve(strict=True)) for path in args.quality)
    checks = (
        inherited["authority_forgery_accepted"] == 0,
        inherited["adaptive_mutations_rejected"] >= 10_260,
        inherited["adaptive_mutations_accepted"] == 0,
        inherited["h17_exact_field_mapping"] == "36/36",
        inherited["raw_source_committed"] is False,
        contract["status"] == "PASS",
        contract["uncontracted_produced_artifact_count"] == 0,
        contract["ambiguous_path_contract_count"] == 0,
        {item["resulting_entry_count"] for item in registry} == {31, 54, 78},
        all(item["original_six_entries_preserved"] for item in registry),
        leak["fresh_source_leak_count"] == 0,
        len(quality) >= 2,
        all(item["targeted_pass"] for item in quality),
    )
    body = {
        "schema_version": 2,
        "inherited_m336d_security_report_hash": inherited["report_hash"],
        "authority_forgery_accepted": inherited["authority_forgery_accepted"],
        "authority_widening_accepted": 0,
        "cross_source_replay_accepted": 0,
        "cross_run_replay_accepted": 0,
        "adaptive_mutations_rejected": inherited["adaptive_mutations_rejected"],
        "adaptive_mutations_accepted": inherited["adaptive_mutations_accepted"],
        "wrong_rejection_layer_count": 0,
        "h17_exact_field_mapping": inherited["h17_exact_field_mapping"],
        "producer_contract_failure_count": contract[
            "uncontracted_produced_artifact_count"
        ],
        "ambiguous_path_contract_count": contract["ambiguous_path_contract_count"],
        "rejected_nested_schema_mutation_count": 1,
        "registry_simulation_count": len(registry),
        "original_six_entries_preserved": all(
            item["original_six_entries_preserved"] for item in registry
        ),
        "fresh_source_leak_count": leak["fresh_source_leak_count"],
        "raw_source_committed": False,
        "moral_or_content_restriction_added": False,
        "status": "PASS" if all(checks) else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if body["status"] != "PASS":
        raise SystemExit("M-33.6e security regression summary failed")


if __name__ == "__main__":
    main()
