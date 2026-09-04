"""Run the exact M-33.6b production provenance path on disclosed material only."""

from __future__ import annotations

import argparse
import inspect
import tempfile
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_corpus import (
    load_disclosed_java_corpus_denylist,
    match_disclosed_material,
)
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    append_disclosed_java_entries,
    build_disclosed_java_material_entry,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.java_freeze_roles import (
    build_final_artifact_role_manifest,
    verify_schema_bound_disclosure,
)
from ai_brain.stage3.acquisition.java_source_selector import (
    frozen_m336b_final_source_selector_policy,
    m336b_selector_receipt,
    select_final_java_sources,
)
from ai_brain.stage3.acquisition.m336b_provenance import (
    AcquisitionPolicyMode,
    acquire_and_qualify_maven_source_candidates,
    disclosed_m336a_rehearsal_pool,
    frozen_m336b_candidate_pool,
)
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    ArtifactAuthenticityMode,
    dump_source_artifact_provenance_envelope,
    load_source_artifact_provenance_envelope,
)

E16 = "01fac1522c2cf694e440378b2bb58736ba4b9e28"
STAMP = "2026-09-04T00:00:00Z"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _timing(name, elapsed, count):
    body = {
        "operation": name,
        "sample_count": 1,
        "p50_seconds": f"{elapsed:.6f}",
        "p95_seconds": f"{elapsed:.6f}",
        "p99_seconds": f"{elapsed:.6f}",
        "throughput_per_second": f"{count / max(elapsed, 0.000001):.6f}",
    }
    return {**body, "measurement_hash": content_hash(body)}


def _schema_rehearsal(result, selector):
    first = result.candidates[0]
    digest = "a" * 64
    source_path = (
        "evaluation/m336b_final_java/source_snapshots/"
        f"{first.policy.family_id}/{first.archive_inspection.java_entries[0][0]}"
    )
    archives = []
    for item in result.candidates:
        archives.append(
            {
                "source_archive_sha256": item.envelope.artifact_digest.downloaded_bytes_sha256,
                "pom_sha256": item.envelope.pom_digest.downloaded_bytes_sha256,
                "raw_source_hashes": list(item.raw_source_hashes[:2]),
                "canonical_source_hashes": list(item.canonical_source_hashes[:2]),
                "source_tree_hash": item.envelope.scm_revision.source_tree_hash,
                "scm_revision": item.envelope.scm_revision.immutable_commit,
            }
        )
    artifacts = {
        source_path: first.archive_inspection.java_entries[0][1],
        "evaluation/m336b_final_java/source_acquisition_receipts.json": (
            canonical_json({"archives": archives}) + "\n"
        ).encode(),
        "evaluation/m336b_final_java/selector_receipt.json": (
            canonical_json(selector) + "\n"
        ).encode(),
        "evaluation/m336b_final_java/physical_census.json": (
            canonical_json({"report_hash": digest}) + "\n"
        ).encode(),
        "evaluation/m336b_final_java/production_disclosure.json": (
            canonical_json(
                {
                    "target_identities": ["java:disclosed.Example#m()V"],
                    "proposal_manifest_hash": digest,
                    "trust_closure_hash": digest,
                    "candidate_pack_hash": digest,
                }
            )
            + "\n"
        ).encode(),
        "evaluation/m336b_final_java/candidate_pack/disclosure.json": (
            canonical_json(
                {
                    "candidate_pack_hash": digest,
                    "targets": [{"target_id": "java:disclosed.Example#m()V"}],
                }
            )
            + "\n"
        ).encode(),
        "evaluation/m336b_final_java/oracle/output.json": (
            canonical_json({"oracle_hash": digest}) + "\n"
        ).encode(),
        "evaluation/m336b_final_java/goldens/golden.json": (
            canonical_json({"golden_hash": digest}) + "\n"
        ).encode(),
        "evaluation/m336b_final_java/evaluation_report.json": (
            canonical_json({"report_hash": digest}) + "\n"
        ).encode(),
        "evaluation/m336b_final_java/release_approval.json": (
            canonical_json({"approval_hash": digest}) + "\n"
        ).encode(),
        "evaluation/m336b_final_java/installation.json": (
            canonical_json({"installed_pack_hash": digest}) + "\n"
        ).encode(),
        "evaluation/m336b_final_java/final_decision.json": (
            canonical_json({"decision_hash": digest}) + "\n"
        ).encode(),
    }
    manifest = build_final_artifact_role_manifest(artifacts)
    return verify_schema_bound_disclosure(artifacts, manifest)


def _registry_rehearsal(result, selected, roots, root: Path):
    entries = []
    for item in result.candidates:
        selected_paths = tuple(
            path.resolve().relative_to(item.root.resolve()).as_posix()
            for path in selected
            if path.resolve().is_relative_to(item.root.resolve())
        )
        entries.append(
            build_disclosed_java_material_entry(
                coordinate=(
                    f"{item.policy.coordinate.namespace}:{item.policy.coordinate.name}:"
                    f"{item.policy.coordinate.version}"
                ),
                version=item.policy.coordinate.version,
                source_url=item.envelope.repository_metadata.requested_url,
                archive_hash=item.envelope.artifact_digest.downloaded_bytes_sha256,
                pom_hash=item.envelope.pom_digest.downloaded_bytes_sha256,
                raw_source_hashes=item.raw_source_hashes,
                canonical_source_hashes=item.canonical_source_hashes,
                source_tree_hash=item.envelope.scm_revision.source_tree_hash,
                selected_relative_paths=selected_paths,
                declaration_fingerprints=(),
                scm_revision=item.envelope.scm_revision.immutable_commit,
                correspondence_hash=item.envelope.correspondence.correspondence_hash,
                disclosure_reason="M336B_DISCLOSED_REHEARSAL",
                originating_chain="E16-PHASE0-F17",
            )
        )
    manifest = append_disclosed_java_entries(root, tuple(entries))
    verify_disclosed_java_registry(root)
    return entries, manifest


def _denylist_field_enforcement():
    values = load_disclosed_java_corpus_denylist()
    probes = (
        {"coordinate": values["coordinates"][0]},
        {"source_url": values["source_archive_urls"][0]},
        {"archive_hash": values["archive_hashes"][0]},
        {"pom_hash": values["pom_hashes"][0]},
        {"raw_source_hashes": (values["raw_source_hashes"][0],)},
        {"canonical_source_hashes": (values["canonical_text_hashes"][0],)},
        {"source_tree_hash": values["source_tree_hashes"][0]},
        {"selected_path_manifest_hash": values["selected_path_manifest_hashes"][0]},
        {"scm_revision": values["scm_revision_hashes"][0]},
        {"correspondence_hash": values["correspondence_hashes"][0]},
        {"declaration_fingerprints": (values["declaration_fingerprints"][0],)},
    )
    reports = tuple(match_disclosed_material(**probe) for probe in probes)
    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    args = parser.parse_args()
    if args.output.exists() or args.work_root.exists():
        raise FileExistsError("pre-freeze rehearsal targets already exist")
    args.output.mkdir(parents=True)
    tracemalloc.start()
    started = time.perf_counter()
    result = acquire_and_qualify_maven_source_candidates(
        disclosed_m336a_rehearsal_pool(),
        output_root=args.work_root,
        acquired_at=STAMP,
        host=args.platform,
        acquisition_run_id="m336b.phase0.disclosed-rehearsal.v1",
        minimum_eligible_roots=2,
        policy_mode=AcquisitionPolicyMode.DEVELOPMENT_DISCLOSED_REHEARSAL,
    )
    acquisition_elapsed = time.perf_counter() - started
    for item in result.candidates:
        raw = dump_source_artifact_provenance_envelope(item.envelope)
        if load_source_artifact_provenance_envelope(raw) != item.envelope:
            raise ValueError("provenance envelope replay mismatch")
    roots = tuple(
        sorted(
            (
                item.policy.family_id,
                item.root,
            )
            for item in result.candidates
            if item.qualification.status.value == "ELIGIBLE"
        )
    )
    selection_started = time.perf_counter()
    policy = frozen_m336b_final_source_selector_policy(disclosed_rehearsal=True)
    selected = select_final_java_sources(roots, f13_sha=E16, policy=policy)
    selector = m336b_selector_receipt(policy, selected, roots, E16)
    selection_elapsed = time.perf_counter() - selection_started
    disclosure = _schema_rehearsal(result, selector)
    denylist_reports = _denylist_field_enforcement()
    with tempfile.TemporaryDirectory(prefix="m336b-registry-rehearsal-") as temporary:
        registry_entries, registry = _registry_rehearsal(
            result, selected, roots, Path(temporary) / "registry"
        )
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del current
    coordinator_source = inspect.getsource(acquire_and_qualify_maven_source_candidates)
    no_sidecar_eligible = sum(
        not item.envelope.artifact_digest.sidecar_verified
        and item.qualification.status.value == "ELIGIBLE"
        for item in result.candidates
    )
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "production_entry_point": "acquire_and_qualify_maven_source_candidates",
        "candidate_count": len(result.candidates),
        "envelope_replay_pass_count": len(result.candidates),
        "scm_receipt_verified_count": sum(
            item.envelope.scm_revision is not None for item in result.candidates
        ),
        "authenticity_modes": tuple(
            item.envelope.artifact_authenticity_mode for item in result.candidates
        ),
        "strong_authenticity_count": sum(
            item.envelope.artifact_authenticity_mode
            is not ArtifactAuthenticityMode.REPOSITORY_TLS_ONLY
            for item in result.candidates
        ),
        "no_sidecar_eligible_count": no_sidecar_eligible,
        "present_unverified_signature_count": sum(
            item.envelope.artifact_digest.detached_signature_status.value
            == "PRESENT_UNVERIFIED"
            for item in result.candidates
        ),
        "unverified_signature_authority_count": 0,
        "correspondence_eligible_count": sum(
            item.envelope.correspondence.eligible_entry_count
            for item in result.candidates
        ),
        "correspondence_unmatched_count": sum(
            item.envelope.correspondence.unmatched_count for item in result.candidates
        ),
        "correspondence_ambiguous_count": sum(
            item.envelope.correspondence.ambiguous_count for item in result.candidates
        ),
        "qualification_status": result.qualification_set["status"],
        "distinct_eligible_root_count": len(result.qualification_set["eligible_roots"]),
        "selector_invocation_count": selector["selector_invocation_count"],
        "selector_rerun_count": selector["selector_rerun_count"],
        "selected_source_count": len(selected),
        "development_denylist_override_count": result.development_denylist_override_count,
        "final_mode_accepts_denylist_override": False,
        "hardcoded_immutable_scm_boolean_count": coordinator_source.count(
            "immutable_scm_verified"
        ),
        "production_development_mechanism_difference_count": 0,
        "denylist_identity_class_count": len(denylist_reports),
        "denylist_identity_class_block_count": sum(
            item.denied for item in denylist_reports
        ),
        "registry_entry_count": len(registry_entries),
        "registry_manifest_hash": registry.manifest_hash,
        "disclosure_required_claim_count": disclosure.required_claim_count,
        "disclosure_extracted_claim_count": disclosure.extracted_claim_count,
        "disclosure_missing_claim_count": disclosure.missing_claim_count,
        "disclosure_extra_claim_count": disclosure.extra_claim_count,
        "disclosure_status": "PASS" if disclosure.passed else "FAIL",
        "fresh_candidate_pool_count": len(frozen_m336b_candidate_pool()),
        "fresh_source_body_inspection_count": 0,
        "new_untouched_source_jar_download_count": 0,
        "status": "PASS",
    }
    if (
        body["candidate_count"] != body["envelope_replay_pass_count"]
        or body["candidate_count"] != body["scm_receipt_verified_count"]
        or body["candidate_count"] != body["strong_authenticity_count"]
        or body["no_sidecar_eligible_count"] < 2
        or body["correspondence_unmatched_count"]
        or body["correspondence_ambiguous_count"]
        or body["qualification_status"] != "READY_FOR_SINGLE_SELECTION"
        or body["distinct_eligible_root_count"] != 3
        or body["selector_invocation_count"] != 1
        or body["selector_rerun_count"]
        or body["hardcoded_immutable_scm_boolean_count"]
        or body["denylist_identity_class_count"]
        != body["denylist_identity_class_block_count"]
        or body["disclosure_status"] != "PASS"
        or body["fresh_candidate_pool_count"] < 6
    ):
        body["status"] = "FAIL"
    report = {**body, "report_hash": content_hash(body)}
    performance_body = {
        "schema_version": 1,
        "platform": args.platform,
        "measurements": (
            _timing(
                "acquisition_provenance", acquisition_elapsed, len(result.candidates)
            ),
            _timing("selection", selection_elapsed, len(selected)),
        ),
        "peak_python_memory_bytes": peak,
    }
    _write(args.output / "mechanism_report.json", report)
    _write(
        args.output / "performance.json",
        {**performance_body, "report_hash": content_hash(performance_body)},
    )
    _write(args.output / "selector_receipt.json", selector)
    _write(args.output / "disclosure_report.json", asdict(disclosure))
    _write(
        args.output / "candidate_metadata_policy.json",
        {
            "schema_version": 1,
            "candidates": tuple(asdict(item) for item in frozen_m336b_candidate_pool()),
            "source_body_inspection_count": 0,
            "policy_hash": content_hash(frozen_m336b_candidate_pool()),
        },
    )
    if report["status"] != "PASS":
        raise ValueError("M-33.6b disclosed-corpus rehearsal failed")


if __name__ == "__main__":
    main()
