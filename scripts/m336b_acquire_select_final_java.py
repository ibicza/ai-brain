"""One-shot M-33.6b final acquisition, qualification, selection, and sealing."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    append_disclosed_java_entries,
    build_disclosed_java_material_entry,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.java_source_selector import (
    frozen_m336b_final_source_selector_policy,
    m336b_selector_receipt,
    select_final_java_sources,
    verify_m336_final_source_corpus,
)
from ai_brain.stage3.acquisition.m336b_provenance import (
    AcquisitionPolicyMode,
    acquire_and_qualify_maven_source_candidates,
    frozen_m336b_candidate_pool,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _copy_selected(selected, roots, target: Path) -> tuple[Path, ...]:
    copied = []
    resolved_roots = tuple((name, root.resolve(strict=True)) for name, root in roots)
    for source in selected:
        matches = tuple(
            (name, root)
            for name, root in resolved_roots
            if source.resolve().is_relative_to(root)
        )
        if len(matches) != 1:
            raise ValueError("selected source has ambiguous candidate ownership")
        family, root = matches[0]
        destination = target / family / source.resolve().relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        copied.append(destination)
    return tuple(copied)


def _tree_rows(root: Path):
    return tuple(
        (path.relative_to(root).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def _declaration_fingerprints(index, family: str):
    return tuple(
        sorted(
            {
                content_hash(
                    (
                        item.receiver_type,
                        item.member_kind,
                        item.member_name,
                        item.canonical_source_signature,
                        item.erased_jvm_descriptor,
                    )
                )
                for item in index.declarations
                if item.source_unit_id.partition("/")[0] == family
                and item.member_kind in {"method", "constructor"}
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--f17-sha", required=True)
    parser.add_argument("--acquired-at", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry-root", type=Path, required=True)
    args = parser.parse_args()
    if any(path.exists() for path in (args.work_root, args.output, args.registry_root)):
        raise FileExistsError("one-shot final acquisition targets must not exist")
    if len(args.f17_sha) != 40 or any(
        character not in "0123456789abcdef" for character in args.f17_sha
    ):
        raise ValueError("final selector requires an exact lowercase F17 SHA")

    candidates = frozen_m336b_candidate_pool()
    result = acquire_and_qualify_maven_source_candidates(
        candidates,
        output_root=args.work_root,
        acquired_at=args.acquired_at,
        host=args.host,
        acquisition_run_id="m336b.final-java.global-acquisition.v1",
        minimum_eligible_roots=2,
        policy_mode=AcquisitionPolicyMode.FINAL,
    )
    if result.development_denylist_override_count:
        raise ValueError("development denylist override reached final acquisition")
    if result.qualification_set["status"] != "READY_FOR_SINGLE_SELECTION":
        raise ValueError("final candidate pool did not produce two eligible roots")
    roots = tuple(
        sorted(
            (item.policy.family_id, item.root)
            for item in result.candidates
            if item.qualification.status.value == "ELIGIBLE"
        )
    )
    if tuple(str(path.resolve()) for _family, path in roots) != tuple(
        result.qualification_set["eligible_roots"]
    ):
        raise ValueError("selector input differs from qualified eligible-root set")
    policy = frozen_m336b_final_source_selector_policy()
    selected = select_final_java_sources(roots, f13_sha=args.f17_sha, policy=policy)
    selector = m336b_selector_receipt(policy, selected, roots, args.f17_sha)

    args.output.mkdir(parents=True)
    snapshot_root = args.output / "source_snapshots"
    copied = _copy_selected(selected, roots, snapshot_root)
    with tempfile.TemporaryDirectory(prefix="m336b-corpus-verification-") as temporary:
        store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
        bundle = ingest_bundle(
            copied,
            bundle_id="m336b-final-java",
            domain_tags=("java-api",),
            imported_at=args.acquired_at,
            store=store,
            source_root=snapshot_root,
        )
        index = index_java_bundle(bundle, store)
        census = verify_m336_final_source_corpus(bundle, index, policy)

    entries = []
    for item in result.candidates:
        selected_paths = tuple(
            path.resolve().relative_to(item.root.resolve()).as_posix()
            for path in selected
            if path.resolve().is_relative_to(item.root.resolve())
        )
        coordinate = (
            f"{item.policy.coordinate.namespace}:{item.policy.coordinate.name}:"
            f"{item.policy.coordinate.version}"
        )
        entries.append(
            build_disclosed_java_material_entry(
                coordinate=coordinate,
                version=item.policy.coordinate.version,
                source_url=item.envelope.repository_metadata.requested_url,
                archive_hash=item.envelope.artifact_digest.downloaded_bytes_sha256,
                pom_hash=item.envelope.pom_digest.downloaded_bytes_sha256,
                raw_source_hashes=item.raw_source_hashes,
                canonical_source_hashes=item.canonical_source_hashes,
                source_tree_hash=item.envelope.scm_revision.source_tree_hash,
                selected_relative_paths=selected_paths,
                declaration_fingerprints=_declaration_fingerprints(
                    index, item.policy.family_id
                ),
                scm_revision=item.envelope.scm_revision.immutable_commit,
                correspondence_hash=item.envelope.correspondence.correspondence_hash,
                disclosure_reason="DOWNLOADED_DURING_H17",
                originating_chain="E16-F17-H17-E17",
            )
        )
    registry = append_disclosed_java_entries(args.registry_root, tuple(entries))
    verify_disclosed_java_registry(args.registry_root)

    receipts = tuple(
        {
            "family_id": item.policy.family_id,
            "coordinate": (
                f"{item.policy.coordinate.namespace}:{item.policy.coordinate.name}:"
                f"{item.policy.coordinate.version}"
            ),
            "requirement": item.policy.requirement,
            "source_archive_sha256": item.envelope.artifact_digest.downloaded_bytes_sha256,
            "pom_sha256": item.envelope.pom_digest.downloaded_bytes_sha256,
            "raw_source_hashes": item.raw_source_hashes,
            "canonical_source_hashes": item.canonical_source_hashes,
            "source_tree_hash": item.envelope.scm_revision.source_tree_hash,
            "scm_revision": item.envelope.scm_revision.immutable_commit,
            "correspondence_hash": item.envelope.correspondence.correspondence_hash,
            "artifact_authenticity_mode": item.envelope.artifact_authenticity_mode,
            "license_evidence_mode": item.envelope.license_evidence_mode,
            "qualification_status": item.qualification.status,
            "provenance_envelope_hash": item.envelope.envelope_hash,
            "qualification_decision_hash": item.qualification.decision_hash,
        }
        for item in result.candidates
    )
    acquisition_body = {
        "schema_version": 2,
        "f17_sha": args.f17_sha,
        "candidate_policy_hashes": tuple(item.policy_hash for item in candidates),
        "archives": receipts,
        "qualification_set_hash": result.qualification_set["qualification_set_hash"],
        "downloaded_candidate_count": len(result.candidates),
        "eligible_distinct_root_count": len(roots),
        "development_denylist_override_count": 0,
    }
    _write(
        args.output / "source_acquisition_receipts.json",
        {**acquisition_body, "manifest_hash": content_hash(acquisition_body)},
    )
    _write(
        args.output / "candidate_qualification_receipts.json", result.qualification_set
    )
    _write(args.output / "selector_receipt.json", selector)
    _write(args.output / "physical_census.json", asdict(census))
    overlap_body = {
        "schema_version": 2,
        "coordinate_overlap_count": sum(
            "COORDINATE" in item.disclosed_match.matching_classes
            for item in result.candidates
        ),
        "source_url_overlap_count": sum(
            "SOURCE_URL" in item.disclosed_match.matching_classes
            for item in result.candidates
        ),
        "archive_hash_overlap_count": sum(
            "ARCHIVE_BYTES" in item.disclosed_match.matching_classes
            for item in result.candidates
        ),
        "pom_hash_overlap_count": sum(
            "POM_BYTES" in item.disclosed_match.matching_classes
            for item in result.candidates
        ),
        "raw_source_overlap_count": census.raw_source_overlap_count,
        "canonical_source_overlap_count": census.canonical_source_overlap_count,
        "source_tree_overlap_count": sum(
            "SOURCE_TREE" in item.disclosed_match.matching_classes
            for item in result.candidates
        ),
        "selected_path_manifest_overlap_count": sum(
            "SELECTED_PATH_MANIFEST" in item.disclosed_match.matching_classes
            for item in result.candidates
        ),
        "declaration_fingerprint_overlap_count": census.declaration_fingerprint_overlap_count,
        "scm_revision_overlap_count": sum(
            "SCM_REVISION" in item.disclosed_match.matching_classes
            for item in result.candidates
        ),
        "correspondence_overlap_count": sum(
            "CORRESPONDENCE" in item.disclosed_match.matching_classes
            for item in result.candidates
        ),
        "normalized_similarity_overlap_count": census.normalized_similarity_overlap_count,
        "status": "PASS",
    }
    _write(
        args.output / "source_overlap.json",
        {**overlap_body, "report_hash": content_hash(overlap_body)},
    )
    execution_body = {
        "schema_version": 2,
        "qualification_completed_before_selection": True,
        "qualified_root_paths": tuple(str(path.resolve()) for _name, path in roots),
        "selector_input_paths": tuple(str(path.resolve()) for _name, path in roots),
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
        "selection_observed_evaluator_result": False,
        "selection_observed_parser_accuracy": False,
        "selector_receipt_hash": selector["receipt_hash"],
    }
    _write(
        args.output / "selection_execution.json",
        {**execution_body, "receipt_hash": content_hash(execution_body)},
    )

    bundle_root = args.output / "acquisition_bundle"
    bundle_root.mkdir()
    shutil.copytree(args.work_root / "candidates", bundle_root / "candidates")
    shutil.copytree(snapshot_root, bundle_root / "source_snapshots")
    for name in (
        "source_acquisition_receipts.json",
        "candidate_qualification_receipts.json",
        "selector_receipt.json",
        "physical_census.json",
        "source_overlap.json",
        "selection_execution.json",
    ):
        shutil.copy2(args.output / name, bundle_root / name)
    rows = _tree_rows(bundle_root)
    sealed_body = {
        "schema_version": 1,
        "file_count": len(rows),
        "files": rows,
        "bundle_tree_hash": content_hash(rows),
        "network_acquisition_count": 1,
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
        "registry_manifest_hash": registry.manifest_hash,
    }
    _write(
        args.output / "sealed_acquisition_bundle.json",
        {**sealed_body, "manifest_hash": content_hash(sealed_body)},
    )


if __name__ == "__main__":
    main()
