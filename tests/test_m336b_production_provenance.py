from __future__ import annotations

from dataclasses import asdict, replace
from inspect import signature
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_corpus import match_disclosed_material
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    append_disclosed_java_entries,
    build_disclosed_java_material_entry,
    load_disclosed_java_registry,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.java_freeze_roles import (
    build_final_artifact_role_manifest,
    verify_schema_bound_disclosure,
)
from ai_brain.stage3.acquisition.m336b_provenance import frozen_m336b_candidate_pool
from ai_brain.stage3.acquisition.m336b_readiness import (
    M336BPreFreezeDecision,
    evaluate_m336b_pre_freeze_gate,
)
from ai_brain.stage3.acquisition.maven_provenance import (
    apache_2_license_identity,
    correspond_source_trees,
    license_text_evidence,
    maven_coordinate,
    resolve_license_evidence,
)
from ai_brain.stage3.acquisition.scm_revision import (
    _parse_ls_remote,
    canonical_github_repository,
)
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    SOURCE_ARTIFACT_PROVENANCE_SCHEMA_VERSION,
    ArtifactAuthenticityMode,
    ArtifactDigestEvidence,
    CandidateQualificationStatus,
    CandidateRequirement,
    DetachedSignatureStatus,
    LicenseClaim,
    LicenseEvidenceMode,
    ProvenanceStatus,
    RepositoryMetadataEvidence,
    SourceCorrespondenceStatus,
    build_provenance_audit_event,
    build_provenance_envelope,
    dump_source_artifact_provenance_envelope,
    load_source_artifact_provenance_envelope,
    qualify_artifact,
    qualify_candidate_set,
    verify_artifact_qualification_decision,
    verify_candidate_qualification_set,
    verify_source_artifact_provenance_envelope,
)


def _repository(url: str, size: int) -> RepositoryMetadataEvidence:
    body = {
        "requested_url": url,
        "final_url": url,
        "redirect_chain": (),
        "content_length": size,
        "media_type": "application/octet-stream",
    }
    return RepositoryMetadataEvidence(
        repository_host="repo.maven.apache.org",
        **body,
        network_receipt_hash=content_hash(body),
    )


def _envelope(*, sidecar=True, signature_status=DetachedSignatureStatus.ABSENT):
    coordinate = maven_coordinate(
        group_id="org.example", artifact_id="fixture", version="1"
    )
    source = b"source"
    pom = b"pom"
    signature = b"signature"
    digest = ArtifactDigestEvidence(
        downloaded_bytes_sha256=bytes_hash(source),
        sidecar_sha256=bytes_hash(source) if sidecar else None,
        sidecar_verified=sidecar,
        detached_signature_url="https://repo.maven.apache.org/maven2/signature.asc"
        if signature_status is not DetachedSignatureStatus.ABSENT
        else None,
        artifact_size=len(source),
        detached_signature_sha256=bytes_hash(signature)
        if signature_status is not DetachedSignatureStatus.ABSENT
        else None,
        detached_signature_status=signature_status,
    )
    pom_digest = ArtifactDigestEvidence(
        bytes_hash(pom), bytes_hash(pom), True, None, len(pom)
    )
    claim_body = {
        "spdx_identifier": "Apache-2.0",
        "declaration_source": "MAVEN_POM",
        "declared_name": "Apache-2.0",
    }
    claim = LicenseClaim(**claim_body, declaration_hash=content_hash(claim_body))
    audit = build_provenance_audit_event(
        acquired_at="2026-09-04T00:00:00Z",
        host="fixture",
        acquisition_run_id="fixture",
        network_receipt_hashes=("1" * 64, "2" * 64),
    )
    envelope = build_provenance_envelope(
        schema_version=SOURCE_ARTIFACT_PROVENANCE_SCHEMA_VERSION,
        coordinate=coordinate,
        artifact_digest=digest,
        repository_metadata=_repository(
            f"{coordinate.repository}/{coordinate.canonical_repository_path}",
            len(source),
        ),
        pom_digest=pom_digest,
        pom_repository_metadata=_repository(
            f"{coordinate.repository}/org/example/fixture/1/fixture-1.pom",
            len(pom),
        ),
        license_claims=(claim,),
        license_texts=(license_text_evidence("META-INF/LICENSE", b"not canonical"),),
        license_evidence_mode=LicenseEvidenceMode.CONFLICTING_LICENSE_EVIDENCE,
        license_status=ProvenanceStatus.CONFLICT,
        scm_revision=None,
        correspondence=None,
        conflicts=("EMBEDDED_LICENSE_CONFLICT",),
        audit_event=audit,
    )
    return envelope, source, pom


def test_v2_envelope_is_strict_canonical_and_semantically_derived(monkeypatch):
    monkeypatch.setattr(
        "ai_brain.stage3.acquisition.maven_provenance.APACHE_2_LICENSE_RAW_SHA256",
        bytes_hash(b"not canonical\n"),
    )
    envelope, source, pom = _envelope()
    # Rebuild after the canonical identity patch so the result is VERIFIED.
    envelope = build_provenance_envelope(
        **{
            **{
                key: value
                for key, value in asdict(envelope).items()
                if key
                not in {
                    "semantic_identity_hash",
                    "envelope_hash",
                    "artifact_authenticity_mode",
                }
            },
            "coordinate": envelope.coordinate,
            "artifact_digest": envelope.artifact_digest,
            "repository_metadata": envelope.repository_metadata,
            "pom_digest": envelope.pom_digest,
            "pom_repository_metadata": envelope.pom_repository_metadata,
            "license_claims": envelope.license_claims,
            "license_texts": envelope.license_texts,
            "license_evidence_mode": LicenseEvidenceMode.EMBEDDED_EXACT_LICENSE,
            "license_status": ProvenanceStatus.VERIFIED,
            "scm_revision": None,
            "correspondence": None,
            "conflicts": (),
            "audit_event": envelope.audit_event,
        }
    )
    verify_source_artifact_provenance_envelope(
        envelope, artifact_bytes=source, pom_bytes=pom
    )
    raw = dump_source_artifact_provenance_envelope(envelope)
    assert (
        dump_source_artifact_provenance_envelope(
            load_source_artifact_provenance_envelope(raw)
        )
        == raw
    )
    with pytest.raises(ValueError, match="field set"):
        load_source_artifact_provenance_envelope(
            raw.replace(
                b'{"artifact_authenticity_mode":',
                b'{"extra":0,"artifact_authenticity_mode":',
                1,
            )
        )
    mutated = build_provenance_envelope(
        schema_version=2,
        coordinate=envelope.coordinate,
        artifact_digest=envelope.artifact_digest,
        repository_metadata=envelope.repository_metadata,
        pom_digest=envelope.pom_digest,
        pom_repository_metadata=envelope.pom_repository_metadata,
        license_claims=envelope.license_claims,
        license_texts=envelope.license_texts,
        license_evidence_mode=LicenseEvidenceMode.POM_DECLARATION_ONLY,
        license_status=ProvenanceStatus.REVIEW_REQUIRED,
        scm_revision=None,
        correspondence=None,
        conflicts=(),
        audit_event=envelope.audit_event,
    )
    with pytest.raises(ValueError, match="license result"):
        verify_source_artifact_provenance_envelope(mutated)


def test_unverified_signature_never_grants_authority():
    envelope, _source, _pom = _envelope(
        sidecar=False,
        signature_status=DetachedSignatureStatus.PRESENT_UNVERIFIED,
    )
    assert (
        envelope.artifact_authenticity_mode
        is ArtifactAuthenticityMode.REPOSITORY_TLS_ONLY
    )
    decision = qualify_artifact(
        envelope, requirement=CandidateRequirement.OPTIONAL, eligible_root="root"
    )
    assert decision.status is CandidateQualificationStatus.CONFLICT


def test_correspondence_v2_separates_raw_canonical_and_relocated():
    artifact = (
        ("p/A.java", b"class A {}\r\n"),
        ("p/B.java", b"class B {}\n"),
    )
    repository = (
        ("src/p/A.java", b"class A {}\n"),
        ("elsewhere/B.java", b"class B {}\n"),
    )
    result = correspond_source_trees(artifact, repository)
    assert [item.status for item in result.entries] == [
        SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH,
    ]
    assert result.canonical_only_match_count == 1
    assert result.relocated_raw_match_count == 1


def test_scm_ref_parser_binds_annotated_and_lightweight_tags():
    ref = "refs/tags/v1"
    raw = f"{'1' * 40}\t{ref}\n{'2' * 40}\t{ref}^{{}}\n".encode()
    assert _parse_ls_remote(raw, ref) == {ref: "1" * 40, f"{ref}^{{}}": "2" * 40}
    assert canonical_github_repository("git@github.com:owner/repo.git")[0] == (
        "https://github.com/owner/repo.git"
    )
    with pytest.raises(ValueError, match="unexpected"):
        _parse_ls_remote(raw + b"0\trefs/heads/main\n", ref)


def test_qualification_closure_rejects_duplicate_roots_and_decisions(monkeypatch):
    monkeypatch.setattr(
        "ai_brain.stage3.acquisition.maven_provenance.APACHE_2_LICENSE_RAW_SHA256",
        bytes_hash(b"not canonical\n"),
    )
    envelope, _source, _pom = _envelope()
    envelope = replace(
        envelope,
        license_evidence_mode=LicenseEvidenceMode.EMBEDDED_EXACT_LICENSE,
        license_status=ProvenanceStatus.VERIFIED,
        conflicts=(),
    )
    # Rehash through the only builder.
    envelope = build_provenance_envelope(
        schema_version=2,
        coordinate=envelope.coordinate,
        artifact_digest=envelope.artifact_digest,
        repository_metadata=envelope.repository_metadata,
        pom_digest=envelope.pom_digest,
        pom_repository_metadata=envelope.pom_repository_metadata,
        license_claims=envelope.license_claims,
        license_texts=envelope.license_texts,
        license_evidence_mode=envelope.license_evidence_mode,
        license_status=envelope.license_status,
        scm_revision=None,
        correspondence=None,
        conflicts=(),
        audit_event=envelope.audit_event,
    )
    decision = qualify_artifact(
        envelope, requirement=CandidateRequirement.OPTIONAL, eligible_root="same-root"
    )
    verify_artifact_qualification_decision(
        decision,
        envelope=envelope,
        requirement=CandidateRequirement.OPTIONAL,
        expected_coordinate=envelope.coordinate,
    )
    assert (
        qualify_candidate_set((decision, decision), minimum_eligible_roots=2)["status"]
        == "BLOCKED"
    )
    candidate = type(
        "Candidate",
        (),
        {
            "coordinate": envelope.coordinate,
            "requirement": CandidateRequirement.OPTIONAL,
        },
    )()
    receipt = qualify_candidate_set((decision,), minimum_eligible_roots=1)
    with pytest.raises(ValueError, match="denominator mismatch"):
        verify_candidate_qualification_set(
            receipt,
            candidates=(candidate,),
            decisions=(decision, decision),
            envelopes=(envelope, envelope),
            minimum_eligible_roots=1,
        )


def _registry_entry(index=1):
    return build_disclosed_java_material_entry(
        coordinate=f"org.example:artifact{index}:1",
        version="1",
        source_url=f"https://repo.maven.apache.org/maven2/artifact{index}.jar",
        archive_hash=f"{index:064x}",
        pom_hash=f"{index + 1:064x}",
        raw_source_hashes=(f"{index + 2:064x}",),
        canonical_source_hashes=(f"{index + 3:064x}",),
        source_tree_hash=f"{index + 4:064x}",
        selected_relative_paths=(f"root{index}/A.java",),
        declaration_fingerprints=(f"{index + 5:064x}",),
        scm_revision=f"{index:040x}",
        correspondence_hash=f"{index + 6:064x}",
        disclosure_reason="DOWNLOADED_DURING_H17",
        originating_chain="E16-F17-H17-E17",
    )


def test_disclosed_registry_is_append_only_and_truncation_fails(tmp_path: Path):
    root = tmp_path / "registry"
    first = _registry_entry(1)
    second = _registry_entry(20)
    append_disclosed_java_entries(root, (first,))
    append_disclosed_java_entries(root, (second,))
    assert set(load_disclosed_java_registry(root)) == {first, second}
    (root / "entries" / f"{first.entry_hash}.json").unlink()
    with pytest.raises((ValueError, FileNotFoundError), match="truncated|find"):
        verify_disclosed_java_registry(root)


def test_match_report_and_disclosure_denominators_are_typed():
    report = match_disclosed_material()
    assert report.matching_classes == () and not report.denied
    selector = {
        "evaluation/m336b_final_java/selector_receipt.json": (
            canonical_json({"selector_output_hash": "a" * 64}) + "\n"
        ).encode()
    }
    disclosure = verify_schema_bound_disclosure(
        selector, build_final_artifact_role_manifest(selector)
    )
    assert not disclosure.passed and disclosure.missing_claim_count == 3


def test_frozen_metadata_only_pool_has_six_optional_independent_families():
    pool = frozen_m336b_candidate_pool()
    assert len(pool) == 6
    assert len({item.family_id for item in pool}) == len(pool)
    assert all(item.requirement is CandidateRequirement.OPTIONAL for item in pool)
    assert all(not hasattr(item, "expected_source_hash") for item in pool)
    assert apache_2_license_identity()


def test_production_license_resolver_has_no_caller_asserted_scm_boolean():
    parameters = signature(resolve_license_evidence).parameters
    assert "immutable_scm_verified" not in parameters
    assert "scm_revision_receipt" in parameters


def _hashed_report(**body):
    return {**body, "report_hash": content_hash(body)}


def test_pre_freeze_gate_recomputes_raw_reports_and_rejects_counter_mutation():
    rehearsal_body = {
        "status": "PASS",
        "production_entry_point": "acquire_and_qualify_maven_source_candidates",
        "candidate_count": 3,
        "envelope_replay_pass_count": 3,
        "scm_receipt_verified_count": 3,
        "strong_authenticity_count": 3,
        "no_sidecar_eligible_count": 2,
        "present_unverified_signature_count": 3,
        "unverified_signature_authority_count": 0,
        "correspondence_eligible_count": 100,
        "correspondence_unmatched_count": 0,
        "correspondence_ambiguous_count": 0,
        "qualification_status": "READY_FOR_SINGLE_SELECTION",
        "distinct_eligible_root_count": 3,
        "registry_entry_count": 3,
        "registry_manifest_hash": "a" * 64,
        "denylist_identity_class_count": 11,
        "denylist_identity_class_block_count": 11,
        "disclosure_required_claim_count": 20,
        "disclosure_extracted_claim_count": 20,
        "disclosure_missing_claim_count": 0,
        "disclosure_extra_claim_count": 0,
        "hardcoded_immutable_scm_boolean_count": 0,
        "production_development_mechanism_difference_count": 0,
    }
    quality_body = {
        "ruff_pass": True,
        "targeted_pass": True,
        "no_torch_network_pass": True,
        "full_suite_pass": True,
    }
    comparison_body = {"difference_count": 0, "status": "PASS"}
    access_body = {
        "fresh_source_jar_get_count": 0,
        "fresh_source_tree_body_get_count": 0,
        "fresh_java_body_inspection_count": 0,
    }
    reports = {
        "windows_rehearsal": _hashed_report(**rehearsal_body),
        "karina_rehearsal": _hashed_report(**rehearsal_body),
        "platform_comparison": _hashed_report(**comparison_body),
        "windows_quality": _hashed_report(**quality_body),
        "karina_quality": _hashed_report(**quality_body),
        "source_access_audit": _hashed_report(**access_body),
    }
    gate = evaluate_m336b_pre_freeze_gate(reports)
    assert gate.decision is M336BPreFreezeDecision.READY_TO_CREATE_F17
    reports["windows_rehearsal"]["selector_rerun_count"] = 1
    with pytest.raises(ValueError, match="hash mismatch"):
        evaluate_m336b_pre_freeze_gate(reports)
