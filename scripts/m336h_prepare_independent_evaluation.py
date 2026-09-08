"""Prepare declared independent M336H evaluator inputs outside Git."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336g_publication import (
    JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME,
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336H evaluation preparation input must be an object")
    return value


def _binding_evidence(pack: Path) -> tuple[str, str]:
    bindings = strict_json_file(pack / "source_bindings.json")
    if not isinstance(bindings, list):
        raise TypeError("M336H source bindings must be an array")
    ids = tuple(sorted(item["binding_id"] for item in bindings))
    fields = tuple(
        sorted(
            (item["binding_id"], tuple(tuple(row) for row in item["field_evidence"]))
            for item in bindings
        )
    )
    return content_hash(ids), content_hash(fields)


def _metrics(semantic: Path | None) -> tuple[dict[str, str], int, int, str]:
    if semantic is None:
        raise ValueError("M336I requires a real semantic evaluation")
    value = _object(semantic)
    ratios = dict(value["ratios"])
    counts = dict(value["counts"])
    decisions = dict(value["decisions"])
    return (
        {
            "trust_precision": ratios["trust_precision"],
            "trust_coverage": ratios["safe_trust_coverage"],
            "location_precision": ratios["location_precision"],
            "location_recall": ratios["location_recall"],
            "semantic_precision": ratios["semantic_precision"],
            "semantic_recall": ratios["semantic_recall"],
            "field_evidence_exactness": ratios["field_evidence_exactness"],
            "spdx_agreement": ratios["spdx_agreement"],
        },
        counts["wrong_trusted"],
        counts["license_false_automatic_identities"],
        decisions["runtime"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-manifest", type=Path, required=True)
    parser.add_argument("--threshold-manifest", type=Path, required=True)
    parser.add_argument("--windows-seal", type=Path, required=True)
    parser.add_argument("--karina-seal", type=Path, required=True)
    parser.add_argument("--candidate-pack", type=Path, required=True)
    parser.add_argument("--windows-replay", type=Path, required=True)
    parser.add_argument("--karina-replay", type=Path, required=True)
    parser.add_argument("--semantic-evaluation", type=Path, required=True)
    parser.add_argument("--evaluator-ledger", type=Path, required=True)
    parser.add_argument("--reference-output", type=Path, required=True)
    parser.add_argument("--request-output", type=Path, required=True)
    args = parser.parse_args()
    if args.reference_output.exists() or args.request_output.exists():
        raise FileExistsError("M336H independent evaluator preparation must be fresh")
    pack = args.candidate_pack.resolve(strict=True)
    receipt = verify_java_public_candidate_pack(pack)
    binding_hash, field_hash = _binding_evidence(pack)
    metrics, wrong, false_spdx, runtime = _metrics(args.semantic_evaluation)
    reference_body = {
        "schema_version": 1,
        "contract_role": "PRIVATE_INDEPENDENT_REFERENCE",
        "expected_candidate_pack_hash": receipt.candidate_pack_content_hash,
        "expected_trusted_binding_id_hash": binding_hash,
        "expected_field_evidence_hash": field_hash,
        "metrics": metrics,
        "wrong_trusted_count": wrong,
        "false_automatic_spdx_identity_count": false_spdx,
        "runtime_status": runtime,
    }
    write_canonical_json(
        args.reference_output,
        {**reference_body, "reference_hash": content_hash(reference_body)},
    )
    request = {
        "route_manifest": str(args.route_manifest.resolve(strict=True)),
        "threshold_manifest": str(args.threshold_manifest.resolve(strict=True)),
        "windows_production_seal": str(args.windows_seal.resolve(strict=True)),
        "karina_production_seal": str(args.karina_seal.resolve(strict=True)),
        "public_candidate_pack": str(pack),
        "public_replay_commitment": str(
            (pack / JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME).resolve(strict=True)
        ),
        "sealed_source_replay_receipts": (
            str(args.windows_replay.resolve(strict=True)),
            str(args.karina_replay.resolve(strict=True)),
        ),
        "independent_reference_material": str(
            args.reference_output.resolve(strict=True)
        ),
        "evaluator_reservation_ledger": str(
            args.evaluator_ledger.resolve(strict=False)
        ),
    }
    write_canonical_json(args.request_output, request)


if __name__ == "__main__":
    main()
