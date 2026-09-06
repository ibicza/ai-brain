from __future__ import annotations

import base64
import gzip
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.java_jdk_provider import (
    m336_public_compiler_semantic_identity_hash,
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.java_production import (
    run_java_acquisition_pipeline,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    build_source_entry_binding,
    build_source_entry_id,
)
from ai_brain.stage3.acquisition.m336g_publication import (
    JAVA_PUBLIC_REPLAY_COMMITMENT_DEPENDENCY_PREFIX,
    JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME,
    ArtifactConfidentialityRole,
    _count_private_roles,
    assert_private_destination,
    audit_publication_boundary,
    build_sealed_java_replay_input_manifest,
    public_artifact_inventory_identity,
    public_path_count,
    run_java_public_pack_contract_validation,
    selected_source_entry_identities,
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336g_staging import validate_public_staging
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle


def test_private_role_counter_distinguishes_artifacts_from_classification_text():
    assert (
        _count_private_roles(
            {
                "required_role": "PRIVATE_SOURCE_INPUT",
                "classification": "PRIVATE_HOST_OBSERVATION",
                "description": "PRIVATE_SOURCE_INPUT",
            }
        )
        == 0
    )
    assert (
        _count_private_roles(
            {
                "contract_role": "PRIVATE_SOURCE_INPUT",
                "nested": [{"artifact_role": "PRIVATE_HOST_OBSERVATION"}],
            }
        )
        == 2
    )


def test_disclosed_regression_compares_source_entry_identity_set():
    first = {
        "files": [
            {"source_entry_identity_hash": "a" * 64},
            {"source_entry_identity_hash": "b" * 64},
        ],
        "manifest_hash": "1" * 64,
    }
    reordered_with_different_envelope = {
        "files": [
            {"source_entry_identity_hash": "b" * 64},
            {"source_entry_identity_hash": "a" * 64},
        ],
        "manifest_hash": "2" * 64,
    }
    assert selected_source_entry_identities(first) == selected_source_entry_identities(
        reordered_with_different_envelope
    )
    with pytest.raises(ValueError, match="duplicate SourceEntryId"):
        selected_source_entry_identities(
            {
                "files": [
                    {"source_entry_identity_hash": "a" * 64},
                    {"source_entry_identity_hash": "a" * 64},
                ]
            }
        )


def test_public_artifact_inventory_identity_separates_root_roles():
    values = {
        public_artifact_inventory_identity(
            platform_role="windows",
            root_role=root_role,
            relative_path="public_jdk_identity_receipt.json",
            sha256="a" * 64,
        )
        for root_role in ("production", "evaluation")
    }
    assert len(values) == 2


def _public_pack(tmp_path: Path):
    vault = tmp_path / "vault"
    source = vault / "candidates/demo/sources/demo/A.java"
    source.parent.mkdir(parents=True)
    raw = b"package demo; public class A { public int get(int v) { return v; } }\n"
    source.write_bytes(raw)
    source_root = tmp_path / "selected"
    selected = source_root / "demo/demo/A.java"
    selected.parent.mkdir(parents=True)
    selected.write_bytes(raw)
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        (selected,),
        bundle_id="m336-final-java",
        domain_tags=("java-api",),
        imported_at="1970-01-01T00:00:00Z",
        source_root=source_root,
        store=store,
    )
    identity = build_source_entry_id(
        candidate_family_id="demo",
        source_jar_sha256="1" * 64,
        archive_relative_path="demo/A.java",
        raw_source_sha256=bundle.documents[0].bytes_hash,
        canonical_source_sha256=bundle.documents[0].canonical_text_hash,
    )
    binding = build_source_entry_binding(
        source_entry_id=identity,
        archive_path="demo/A.java",
        scm_path="src/demo/A.java",
        vault_path="candidates/demo/sources/demo/A.java",
        selected_path="demo/demo/A.java",
        production_document_identity=bundle.documents[0].document_id,
    )
    batch = run_java_acquisition_pipeline(
        bundle, store, deterministic_run_id="m336g.test"
    )
    authorizations = verify_java_production_batch(batch, store)
    by_id = {item.trusted_proposal_id: item for item in authorizations}
    proposals = []
    approvals = []
    for proposal in batch.trusted_proposals:
        approved, _review, approval = review_proposal(
            proposal,
            reviewer_identity="m336g-test-process",
            reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
            decision=ReviewDecision.APPROVE,
            rationale="source-free public pack test",
            timestamp="1970-01-01T00:00:00Z",
            trust_authorization=by_id[proposal.proposal_id],
        )
        proposals.append(approved)
        approvals.append(approval)
    pack_root = tmp_path / "pack"
    pack = compile_provisional_pack(
        bundle,
        batch.segmentation.segments,
        tuple(proposals),
        tuple(approvals),
        pack_root,
        domain_id="m336-final-java",
        production_trust_batch=batch,
        production_authorizations=authorizations,
        java_source_entry_bindings=(binding,),
        store=store,
    )
    return raw, vault, binding, batch, pack, pack_root


def test_public_candidate_pack_is_source_free_and_contract_closed(tmp_path):
    raw, _vault, _binding, batch, pack, pack_root = _public_pack(tmp_path)
    receipt = verify_java_public_candidate_pack(pack_root)
    assert receipt.status == "PASS"
    assert receipt.unknown_entry_count == 0
    assert receipt.source_bearing_entry_count == 0
    assert receipt.private_role_entry_count == 0
    assert receipt.absolute_path_count == 0
    assert receipt.reversible_source_payload_count == 0
    assert not (pack_root / "java_production_closure.json").exists()
    assert not (pack_root / "java_replay.json").exists()
    assert (pack_root / JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME).is_file()
    assert not any(raw in item.read_bytes() for item in pack_root.iterdir())
    commitment = json.loads(
        (pack_root / JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME).read_text()
    )
    rendered = canonical_json(commitment)
    assert "raw_source_blobs" not in rendered
    assert "canonical_text_blobs" not in rendered
    assert commitment["release_identity_hash"] == batch.release_identity.identity_hash
    assert pack.manifest.dependency_packs[0] == (
        JAVA_PUBLIC_REPLAY_COMMITMENT_DEPENDENCY_PREFIX + commitment["commitment_hash"]
    )


@pytest.mark.parametrize(
    "payload",
    (
        {"raw_source_blobs": ["hidden"]},
        {"renamed": {"nested": {"source_body": "hidden"}}},
        {"contract_role": "PRIVATE_SOURCE_INPUT"},
        {"error": r"C:\\private\\jdk\\bin\\javac.exe"},
        {"error": "C:/private/jdk/bin/javac.exe"},
        {"error": r"\\\\server\\share\\secret"},
        {"error": r"\\\\?\\C:\\private\\secret"},
        {"error": "/home/user/private"},
        {"error": "/tmp/private"},
        {"error": "/opt/private"},
        {"error": "/mnt/private"},
        {"error": "file:///tmp/private"},
        {"error": "~/private"},
        {"path": "../private"},
        {"items": [{"path": "/private/arbitrary"}]},
    ),
)
def test_recursive_pack_mutations_fail_closed(tmp_path, payload):
    _raw, _vault, _binding, _batch, _pack, pack_root = _public_pack(tmp_path)
    path = pack_root / "evaluation_manifest.json"
    value = json.loads(path.read_text())
    value["mutation"] = payload
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError):
        verify_java_public_candidate_pack(pack_root)


def test_complete_base64_and_hex_source_mutations_fail(tmp_path):
    raw, _vault, _binding, _batch, _pack, pack_root = _public_pack(tmp_path)
    for index, encoded in enumerate((base64.b64encode(raw).decode(), raw.hex())):
        target = tmp_path / f"mutated-{index}"
        shutil.copytree(pack_root, target)
        path = target / "evaluation_manifest.json"
        value = json.loads(path.read_text())
        value["opaque_payload"] = encoded
        path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
        with pytest.raises(ValueError, match="source"):
            verify_java_public_candidate_pack(target)


def test_encoded_gzip_source_mutation_fails(tmp_path):
    raw, _vault, _binding, _batch, _pack, pack_root = _public_pack(tmp_path)
    path = pack_root / "evaluation_manifest.json"
    value = json.loads(path.read_text())
    value["opaque_payload"] = base64.b64encode(gzip.compress(raw)).decode()
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="source"):
        verify_java_public_candidate_pack(pack_root)


def test_unknown_pack_entry_and_private_destination_fail(tmp_path):
    _raw, _vault, _binding, _batch, _pack, pack_root = _public_pack(tmp_path)
    (pack_root / "unknown.bin").write_bytes(b"opaque")
    with pytest.raises(ValueError, match="entry set"):
        verify_java_public_candidate_pack(pack_root)
    public = tmp_path / "public"
    public.mkdir()
    with pytest.raises(ValueError, match="protected root"):
        assert_private_destination(public / "private.json", public_roots=(public,))


def test_private_manifest_contains_identities_but_no_source_blobs(tmp_path):
    raw, vault, binding, _batch, _pack, _pack_root = _public_pack(tmp_path)
    manifest = build_sealed_java_replay_input_manifest(
        bindings=(binding,),
        selected_paths=(binding.selected_path,),
        vault_root=vault,
        selected_source_manifest_hash="2" * 64,
        source_entry_binding_manifest_hash="3" * 64,
        compiler_semantic_identity_hash="4" * 64,
    )
    rendered = canonical_json(asdict(manifest)).encode()
    assert raw not in rendered
    assert base64.b64encode(raw) not in rendered
    assert raw.hex().encode() not in rendered
    assert manifest.source_count == 1


def test_path_detector_avoids_urls_and_maven_coordinates():
    assert public_path_count({"url": "https://example.test/a/b"}) == 0
    assert public_path_count({"coordinate": "org.example:artifact:1.0"}) == 0
    assert public_path_count({"path": "/srv/private"}) == 1


def test_publication_roles_are_exact_and_private_never_passes_public_audit():
    audit, receipt = audit_publication_boundary(
        (
            ("pack", ArtifactConfidentialityRole.PUBLIC_DERIVED_PACK, True),
            ("private", ArtifactConfidentialityRole.PRIVATE_SOURCE_INPUT, False),
        )
    )
    assert audit.private_source_artifacts_in_public_roots == 0
    assert receipt.status == "PASS"
    _audit, blocked = audit_publication_boundary(
        (("private", ArtifactConfidentialityRole.PRIVATE_SOURCE_INPUT, True),)
    )
    assert blocked.status == "FAIL"


def test_jdk_public_receipt_has_no_host_paths():
    root = Path(r"W:\toolbox_IDEA\programs\IdeaProjects\.jdks\ms-21.0.11")
    if not root.is_dir():
        pytest.skip("frozen Windows JDK is unavailable")
    private, public = verify_m336_jdk_provider_evidence(
        platform="windows", java=root / "bin/java.exe", javac=root / "bin/javac.exe"
    )
    assert private.contract_role == "PRIVATE_HOST_OBSERVATION"
    assert public.contract_role == "PUBLIC_PLATFORM_TELEMETRY"
    assert public.semantic_compiler_identity_hash == (
        m336_public_compiler_semantic_identity_hash()
    )
    rendered = canonical_json(asdict(public))
    for name in (
        "java_path",
        "javac_path",
        "release_path",
        "java_home",
        "jdk_home",
        "installation_root",
        "executable_path",
    ):
        assert name not in rendered
    assert public_path_count(json.loads(rendered)) == 0


def test_public_staging_scans_exact_candidate_and_installed_bytes(tmp_path):
    _raw, vault, _binding, _batch, _pack, pack_root = _public_pack(tmp_path / "fixture")
    staging = tmp_path / "staging"
    candidate = staging / "candidate_pack"
    installed = staging / "installed_pack"
    shutil.copytree(pack_root, candidate)
    shutil.copytree(pack_root, installed)
    roles = {
        path.relative_to(staging).as_posix(): (
            ArtifactConfidentialityRole.PUBLIC_DERIVED_PACK
        )
        for path in staging.rglob("*")
        if path.is_file()
    }
    manifest, receipt = validate_public_staging(
        staging_root=staging,
        artifact_roles=roles,
        sealed_vault_root=vault,
        candidate_pack_relative_path="candidate_pack",
        installed_pack_relative_path="installed_pack",
        prospective_git_tree_hash="1" * 40,
    )
    assert manifest.candidate_pack_tree_hash == manifest.installed_pack_tree_hash
    assert receipt.status == "PASS"
    assert receipt.post_scan_modified_file_count == 0


def test_recursive_producer_contract_gate_covers_outer_and_pack_entries(tmp_path):
    _raw, _vault, _binding, _batch, _pack, pack_root = _public_pack(tmp_path)
    repository = Path(__file__).resolve().parents[1]
    legacy = json.loads(
        (
            repository / "evaluation/m336d_final_java/h19/acquisition_receipts.json"
        ).read_text(encoding="utf-8")
    )
    report = run_java_public_pack_contract_validation(legacy, pack_root)
    assert report.status == "PASS"
    assert report.public_producer_count == report.covered_producer_count == 14
    assert report.declared_producer_variant_count == 41
    assert report.tested_producer_variant_count == 41
    assert (
        report.pack_entry_producer_count
        == report.covered_pack_entry_producer_count
        == report.declared_pack_entry_variant_count
        == report.tested_pack_entry_variant_count
        == 11
    )
    assert report.unknown_candidate_pack_entry_count == 0
    assert report.uncontracted_public_artifact_count == 0
