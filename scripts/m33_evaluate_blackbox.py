"""Independent, read-only evaluator for frozen M-33 final artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.evaluation import (
    evaluate_proposals,
    verify_pack_evaluation,
)
from ai_brain.stage3.acquisition.heldout import (
    HeldoutTaskSemanticKey,
    verify_semantic_uniqueness,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.domains.loader import load_pack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--goldens", type=Path, required=True)
    parser.add_argument("--heldout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = _read(args.artifacts / "build_summary.json")
    domain_metrics = []
    all_segment_text = []
    total_segments = 0
    for item in summary["bundles"]:
        bundle_id = item["bundle_id"]
        pointers = item["pointers"]
        store = AcquisitionStore(args.artifacts / "acquisition" / bundle_id)
        store.verify()
        segments = store.load_segments(pointers["segment_set"])
        proposals = store.load_proposals(pointers["verified_proposal_set"])
        evidence = store.load_field_evidence(pointers["field_evidence_set"])
        golden = _read(args.goldens / f"{bundle_id}.json")
        _verify_golden(golden)
        metrics = evaluate_proposals(
            proposals,
            golden,
            segments,
            field_evidence=evidence,
        )
        pack = load_pack(args.artifacts / "packs" / bundle_id)
        pack_evaluation = verify_pack_evaluation(pack)
        body_segments = tuple(
            item for item in segments if item.kind.value != "DOCUMENT"
        )
        total_segments += len(body_segments)
        all_segment_text.extend(item.canonical_text for item in body_segments)
        domain_metrics.append(
            {
                "bundle_id": bundle_id,
                "metrics": metrics,
                "pack_evaluation": pack_evaluation,
                "pack_hash": pack.manifest.pack_content_hash,
            }
        )
    tasks = tuple(_semantic_key(item) for item in _read_jsonl(args.heldout))
    uniqueness = verify_semantic_uniqueness(tasks)
    duplicates = sum(count - 1 for count in Counter(all_segment_text).values())
    duplicate_rate = (
        "N/A" if not total_segments else f"{duplicates / total_segments:.6f}"
    )
    trusted_wrong = sum(
        item["metrics"]["wrong_automatically_verified"] for item in domain_metrics
    )
    result = {
        "status": (
            "PASS"
            if trusted_wrong == 0
            and uniqueness["semantic_key_count"] >= 500
            and all(
                item["pack_evaluation"]["status"] == "PASS" for item in domain_metrics
            )
            else "FAIL"
        ),
        "domains": domain_metrics,
        "semantic_uniqueness": uniqueness,
        "source_segment_count": total_segments,
        "exact_duplicate_segment_count": duplicates,
        "exact_duplicate_segment_rate": duplicate_rate,
        "wrong_automatically_trusted": trusted_wrong,
    }
    result = {**result, "evaluation_hash": content_hash(result)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(result) + "\n", encoding="utf-8", newline="\n"
    )
    print(canonical_json(result))
    return 0 if result["status"] == "PASS" else 1


def _verify_golden(value: dict) -> None:
    digest = value.get("golden_hash")
    body = {key: item for key, item in value.items() if key != "golden_hash"}
    if digest != content_hash(body):
        raise ValueError("independent golden hash mismatch")
    if not value.get("reviewer_method") or not value.get("rationale"):
        raise ValueError("independent golden lacks review method or rationale")
    if any("proposal_id" in item for item in value.get("expected", ())):
        raise ValueError("golden imports a production proposal identity")


def _semantic_key(row: dict) -> HeldoutTaskSemanticKey:
    return HeldoutTaskSemanticKey(
        operation_type=row["operation_type"],
        target_record_id=row["target_record_id"],
        requested_unknown=row.get("requested_unknown"),
        normalized_givens=tuple(
            tuple(item) for item in row.get("normalized_givens", ())
        ),
        units=tuple(tuple(item) for item in row.get("units", ())),
        conditions=tuple(row.get("conditions", ())),
        expected_answer_semantics=row["expected_answer_semantics"],
        semantic_hash=row["semantic_hash"],
    )


def _read(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object
    )


def _read_jsonl(path: Path):
    return tuple(
        json.loads(line, object_pairs_hook=_strict_object)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
