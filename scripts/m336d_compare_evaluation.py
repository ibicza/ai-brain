"""Compare platform-neutral independent M-33.6d evaluation artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

IGNORED = frozenset(
    {
        "evaluation.json",
        "evaluation_performance.json",
        "semantic/evaluation_summary.json",
        "semantic/evaluation_performance.json",
        "semantic/jdk_provider_receipt.json",
    }
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh evaluation comparison exists")
    windows = _rows(args.windows.resolve(strict=True))
    karina = _rows(args.karina.resolve(strict=True))
    paths = tuple(sorted(set(windows) | set(karina)))
    differences = tuple(
        path
        for path in paths
        if path not in IGNORED and windows.get(path) != karina.get(path)
    )
    left = json.loads((args.windows / "evaluation.json").read_text(encoding="utf-8"))
    right = json.loads((args.karina / "evaluation.json").read_text(encoding="utf-8"))
    semantic_fields = (
        "production_reference_license_agreement",
        "false_automatic_license_identity_count",
        "selected_root_unresolved_disagreement_count",
        "location_precision",
        "location_recall",
        "semantic_precision",
        "semantic_recall",
        "trust_precision",
        "trust_coverage",
        "field_evidence_exactness",
        "resolution_agreement",
        "wrong_trusted_count",
        "post_trust_pack_failures",
        "candidate_pack_compiled",
        "candidate_replay_status",
        "runtime_status",
    )
    field_differences = tuple(
        name for name in semantic_fields if left[name] != right[name]
    )
    body = {
        "schema_version": 1,
        "platform_neutral_artifact_count": sum(path not in IGNORED for path in paths),
        "byte_difference_count": len(differences),
        "semantic_field_difference_count": len(field_differences),
        "different_paths": differences,
        "different_semantic_fields": field_differences,
        "platform_independent_difference_count": len(differences)
        + len(field_differences),
        "status": "PASS" if not differences and not field_differences else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if body["status"] != "PASS":
        raise SystemExit("independent evaluation differs by platform")


def _rows(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): bytes_hash(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    }


if __name__ == "__main__":
    main()
