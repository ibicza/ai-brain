"""Build role-specific H17 disclosure summaries from sealed final artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    production = args.production_root.resolve(strict=True)
    evaluation = args.evaluation_root.resolve(strict=True)
    output = args.output_root.resolve()
    destinations = tuple(
        output / name
        for name in (
            "production_disclosure.json",
            "candidate_pack_disclosure.json",
            "oracle_disclosure.json",
            "golden_disclosure.json",
            "evaluation_disclosure.json",
        )
    )
    if any(path.exists() for path in destinations):
        raise FileExistsError("final disclosure summaries must be new")
    sealed = _load(production / "production_output.json")
    summary = _load(production / "production_summary.json")
    targets = tuple(
        sorted(
            {
                f"java:{row['receiver_type']}#{row['erased_jvm_descriptor']}"
                for row in sealed["candidate_rows"]
            }
        )
    )
    production_body = {
        "target_identities": targets,
        "production_output_hash": sealed["production_output_hash"],
        "proposal_manifest_hash": sealed["proposal_manifest_hash"],
        "trust_closure_hash": sealed["trust_closure_hash"],
        "candidate_pack_hash": summary["candidate_pack_hash"],
        "candidate_pack_tree_hash": summary["candidate_tree_hash"],
    }
    _write(output / "production_disclosure.json", production_body)
    _write(
        output / "candidate_pack_disclosure.json",
        {
            "candidate_pack_hash": summary["candidate_pack_hash"],
            "targets": tuple({"target_id": item} for item in targets),
        },
    )
    oracle_root = evaluation / "oracle"
    oracle_rows = tuple(
        (path.relative_to(oracle_root).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(
            (item for item in oracle_root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(oracle_root).as_posix().encode("utf-8"),
        )
    )
    _write(
        output / "oracle_disclosure.json", {"oracle_hash": content_hash(oracle_rows)}
    )
    golden = oracle_root / "semantic_goldens.json"
    _write(
        output / "golden_disclosure.json",
        {"golden_hash": bytes_hash(golden.read_bytes())},
    )
    report = _load(evaluation / "evaluation_report.json")
    report_hash = report.get("report_hash") or bytes_hash(
        (evaluation / "evaluation_report.json").read_bytes()
    )
    _write(
        output / "evaluation_disclosure.json",
        {"report_hash": report_hash, "target_identities": targets},
    )


if __name__ == "__main__":
    main()
