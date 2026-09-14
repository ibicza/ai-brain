"""Execute the 44 closed-under-rehash M-33.6k.8 mutations."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import startup_receipt_from_path
from ai_brain.stage3.acquisition.m336k8_mutations import (
    M336K8_MUTATION_CASES,
    run_m336k8_mutation_suite,
)

_SOURCE_DOMAIN_SEMANTIC_CASE_COUNT = 21


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    startup = startup_receipt_from_path(args.startup_receipt.resolve(strict=True))
    if output.exists():
        raise M336K2ProtocolError("M336K8 mutation report output is stale")
    if not (repository / ".git").exists():
        raise M336K2ProtocolError("M336K8 mutation repository is invalid")

    results = run_m336k8_mutation_suite()
    semantic_rejections = sum(
        item.rejection_layer == "SOURCE_DOMAIN_SEMANTIC" for item in results
    )
    if (
        len(results) != len(M336K8_MUTATION_CASES)
        or any(item.status != "REJECTED" for item in results)
        or any(item.fully_rehashed is not True for item in results)
        or semantic_rejections != _SOURCE_DOMAIN_SEMANTIC_CASE_COUNT
    ):
        raise M336K2ProtocolError("M336K8 mutation suite is incomplete")

    body = {
        "schema_version": 1,
        "contract_role": ("PUBLIC_SAFE_M336K8_CLOSED_UNDER_REHASH_MUTATION_REPORT"),
        "mutation_case_count": len(results),
        "accepted_invalid_case_count": 0,
        "wrong_rejection_layer_count": 0,
        "hash_only_cross_domain_rejection_count": 0,
        "fully_rehashed_source_domain_rejection_count": semantic_rejections,
        "source_domain_semantic_rejection_count": semantic_rejections,
        "startup_receipt_hash": startup.receipt_hash,
        "results": tuple(asdict(item) for item in results),
        "status": "PASS",
    }
    report = {**body, "report_hash": content_hash(body)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(report) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(report))


if __name__ == "__main__":
    main()
