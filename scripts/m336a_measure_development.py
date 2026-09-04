"""Measure deterministic M-33.6a mechanisms without acquiring source material."""

from __future__ import annotations

import argparse
import statistics
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_corpus import (
    disclosed_candidate_match,
    load_m336a_disclosed_candidate_denylist,
)
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    verify_m336_git_freeze_protocol,
)
from ai_brain.stage3.acquisition.java_freeze_roles import (
    build_final_artifact_role_manifest,
    dump_final_artifact_role_manifest,
    extract_disclosure_claims,
    load_final_artifact_role_manifest,
)
from ai_brain.stage3.acquisition.maven_provenance import (
    correspond_source_trees,
    license_text_evidence,
    maven_coordinate,
    normalize_license_text,
    parse_maven_pom,
    verify_sha256_sidecar,
)
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    ArtifactQualificationDecision,
    CandidateQualificationStatus,
    CandidateRequirement,
    LicenseEvidenceMode,
    qualify_candidate_set,
)

F15 = "d377a206bb251508b94680dd267f0c5cd02dd2aa"
H15 = "ae86c630a4141dc97cfe97fd4a46d2eeaacc5831"
E15 = "b4f8b881ab15e995c8df9e17e4704f5dec34e028"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _percentile(values, percentile):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, (len(ordered) * percentile + 99) // 100 - 1))
    return ordered[index]


def _measure(name, operation, *, repetitions=101):
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - started) // 1_000)
    total_us = sum(samples)
    body = {
        "operation": name,
        "sample_count": len(samples),
        "p50_microseconds": int(statistics.median(samples)),
        "p95_microseconds": _percentile(samples, 95),
        "p99_microseconds": _percentile(samples, 99),
        "throughput_per_second": f"{len(samples) * 1_000_000 / max(total_us, 1):.6f}",
    }
    return {**body, "measurement_hash": content_hash(body)}


def build(repository: Path, platform: str):
    coordinate = maven_coordinate(
        group_id="org.example", artifact_id="fixture", version="1"
    )
    pom = b"""<project><modelVersion>4.0.0</modelVersion><groupId>org.example</groupId><artifactId>fixture</artifactId><version>1</version><licenses><license><name>Apache License, Version 2.0</name><url>https://www.apache.org/licenses/LICENSE-2.0.txt</url></license></licenses><scm><connection>scm:git:https://github.com/example/fixture.git</connection></scm></project>"""
    payload = b"fixture artifact"
    sidecar = __import__("hashlib").sha256(payload).hexdigest().encode()
    java = tuple(
        (f"p/C{i}.java", f"package p; class C{i} {{ void m() {{}} }}\n".encode())
        for i in range(20)
    )
    h = {
        "evaluation/m336_final_java/selector_receipt.json": (
            canonical_json({"selected_relative_paths": ["root/A.java"]}) + "\n"
        ).encode(),
        "evaluation/m336_final_java/production_process_audit.json": b'{"count":0}\n',
    }
    manifest = build_final_artifact_role_manifest(h)
    manifest_raw = dump_final_artifact_role_manifest(manifest)
    denylist = load_m336a_disclosed_candidate_denylist()
    matrix = _load_matrix(repository)
    decisions = []
    for index, row in enumerate(matrix["candidates"]):
        body = {
            "coordinate": maven_coordinate(
                group_id=row["coordinate"].split(":")[0],
                artifact_id=row["coordinate"].split(":")[1],
                version=row["coordinate"].split(":")[2],
            ),
            "requirement": CandidateRequirement.OPTIONAL,
            "status": CandidateQualificationStatus.ELIGIBLE,
            "evidence_mode": LicenseEvidenceMode(row["license_evidence_mode"]),
            "reasons": ("COMPLETE_FROZEN_EVIDENCE",),
            "eligible_root": f"fixture-{index}",
            "provenance_identity_hash": row["correspondence_hash"],
        }
        decisions.append(
            ArtifactQualificationDecision(**body, decision_hash=content_hash(body))
        )

    tracemalloc.start()
    measurements = (
        _measure("pom_load_verification", lambda: parse_maven_pom(pom, coordinate)),
        _measure(
            "checksum_verification", lambda: verify_sha256_sidecar(payload, sidecar)
        ),
        _measure(
            "license_normalization",
            lambda: normalize_license_text(b"fixture\r\ntext\r\n"),
        ),
        _measure(
            "scm_license_verification",
            lambda: license_text_evidence("LICENSE", b"fixture\n"),
        ),
        _measure(
            "source_tree_correspondence",
            lambda: correspond_source_trees(java, java),
            repetitions=31,
        ),
        _measure(
            "candidate_qualification",
            lambda: qualify_candidate_set(tuple(decisions), minimum_eligible_roots=2),
        ),
        _measure(
            "denylist_lookup",
            lambda: disclosed_candidate_match(
                archive_hash=denylist["archive_hashes"][0]
            ),
            repetitions=31,
        ),
        _measure(
            "role_manifest_serialization",
            lambda: load_final_artifact_role_manifest(manifest_raw),
        ),
        _measure(
            "disclosure_claim_extraction",
            lambda: extract_disclosure_claims(h, manifest),
        ),
        _measure(
            "freeze_verification",
            lambda: verify_m336_git_freeze_protocol(
                repository,
                f15_sha=F15,
                h15_sha=H15,
                e15_sha=E15,
                upstream="origin/exp/stage3-m336-fresh-java-freeze",
            ),
            repetitions=3,
        ),
    )
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    historical = verify_m336_git_freeze_protocol(
        repository,
        f15_sha=F15,
        h15_sha=H15,
        e15_sha=E15,
        upstream="origin/exp/stage3-m336-fresh-java-freeze",
    )
    sidecar_statuses = tuple(
        status
        for row in matrix["candidates"]
        for status in row["sha256_sidecars"].values()
    )
    mechanism_body = {
        "schema_version": 1,
        "provenance_matrix_hash": matrix["matrix_hash"],
        "denylist_manifest_hash": denylist["manifest_hash"],
        "candidate_count": len(matrix["candidates"]),
        "typed_qualification_receipt_count": sum(
            "qualification_receipt" in row for row in matrix["candidates"]
        ),
        "intrinsically_verified_count": sum(
            row["intrinsic_license_status"] == "VERIFIED"
            for row in matrix["candidates"]
        ),
        "future_eligible_count": matrix["future_eligible_candidate_count"],
        "archive_pom_checksum_policy_pass": all(
            item in {"VERIFIED", "NOT_PUBLISHED"} for item in sidecar_statuses
        ),
        "sha256_sidecar_verified_count": sidecar_statuses.count("VERIFIED"),
        "sha256_sidecar_not_published_count": sidecar_statuses.count("NOT_PUBLISHED"),
        "detached_signature_bound_count": sum(
            len(row["detached_signature_hashes"]) for row in matrix["candidates"]
        ),
        "correspondence_exact_count": sum(
            row["exact_match_count"] for row in matrix["candidates"]
        ),
        "correspondence_unmatched_count": sum(
            row["unmatched_count"] for row in matrix["candidates"]
        ),
        "correspondence_ambiguous_count": sum(
            row["ambiguous_match_count"] for row in matrix["candidates"]
        ),
        "historical_protocol_integrity": historical.protocol_integrity,
        "historical_experiment_outcome": historical.historical_experiment_outcome,
        "historical_false_disclosure_token_count": historical.historical_false_disclosure_token_count,
        "historical_role_manifest_matches": historical.committed_role_manifest_matches,
        "new_untouched_corpus_acquired": False,
    }
    performance_body = {
        "schema_version": 1,
        "platform": platform,
        "measurements": measurements,
        "peak_python_memory_bytes": peak,
    }
    return (
        {**mechanism_body, "report_hash": content_hash(mechanism_body)},
        asdict(historical),
        {**performance_body, "report_hash": content_hash(performance_body)},
    )


def _load_matrix(repository):
    return __import__("json").loads(
        (
            repository / "evaluation/m336a_disclosed_provenance/provenance_matrix.json"
        ).read_text(encoding="utf-8")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--platform", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    mechanism, historical, performance = build(args.repository.resolve(), args.platform)
    _write(args.output / "mechanism_summary.json", mechanism)
    _write(args.output / "historical_freeze.json", historical)
    _write(args.output / "performance.json", performance)


if __name__ == "__main__":
    main()
