"""Build an overprovisioned local-only Java pool for disposable route proof."""

from __future__ import annotations

import argparse
from pathlib import Path

from m336i_build_authorized_rehearsal_fixture import (
    FIXTURE_COMMIT,
    _pom,
    _source_archive,
)

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-count", type=int, default=80)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M336K2 disposable pool output must be fresh")
    if args.candidate_count < 80:
        raise ValueError("M336K2 disposable pool requires at least 80 families")
    candidates = []
    for index in range(args.candidate_count):
        family = f"m336k2-fixture-{index:03d}"
        body = {
            "family_id": family,
            "organization_id": f"m336k2-fixture-org-{index:03d}",
            "group_id": "invalid.m336k2",
            "artifact_id": family,
            "version": "1.0.0",
            "coordinate": f"invalid.m336k2:{family}:1.0.0",
            "source_url": f"https://fixture.invalid/{family}-sources.jar",
            "pom_url": f"https://fixture.invalid/{family}.pom",
            "scm_archive_head_url": f"https://fixture.invalid/{family}.zip",
            "source_content_length": len(_source_archive(family)),
            "source_sha256_sidecar_available": False,
            "source_sha256_sidecar_value": None,
            "source_signature_available": False,
            "metadata_pom_sha256": bytes_hash(_pom(family)),
            "metadata_receipt_hashes": [content_hash((family, "metadata"))],
            "pom_license_declarations": [
                [
                    "Apache-2.0",
                    "Apache License, Version 2.0",
                    content_hash("Apache-2.0"),
                ]
            ],
            "scm_repository": f"https://fixture.invalid/{family}.git",
            "scm_ref": "refs/tags/1.0.0",
            "scm_commit": FIXTURE_COMMIT,
            "repository_source_prefixes": ["src"],
            "metadata_authority": "LOCAL_DETERMINISTIC_DISPOSABLE_PROVIDER",
            "metadata_compilation_risk": "ZERO_EXTERNAL_COMPILE_DEPENDENCIES",
            "requirement": "OPTIONAL",
        }
        candidates.append({**body, "policy_hash": content_hash(body)})
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_METADATA_ONLY_CANDIDATE_POOL",
        "candidate_count": len(candidates),
        "organization_count": len(candidates),
        "maximum_candidates_per_organization": 1,
        "pre_freeze_source_body_bytes": 0,
        "claims_final_eligibility": False,
        "candidates": candidates,
    }
    pool = {**body, "pool_hash": content_hash(body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(pool) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(pool))


if __name__ == "__main__":
    main()
