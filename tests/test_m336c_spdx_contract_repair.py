from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ai_brain.stage3.acquisition.final_artifact_contract import (
    FINAL_ARTIFACT_CONTRACT_REGISTRY,
    FinalArtifactContractRegistry,
)
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    load_disclosed_java_registry,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.java_type_universe import (
    JavaResolutionKind,
    build_java_type_universe,
    resolve_java_type,
    source_symbol_metadata,
)
from ai_brain.stage3.acquisition.m336c_contract_verification import (
    complete_hypothetical_h_stage,
    run_contract_mutation_battery,
    verify_contract_tree,
)
from ai_brain.stage3.acquisition.m336c_development import (
    prepare_disclosed_rehearsal,
)
from ai_brain.stage3.acquisition.m336c_future_pool import (
    future_candidate_families,
    run_future_pool_simulations,
)
from ai_brain.stage3.acquisition.m336c_h17_forensics import (
    H17_HISTORICAL_OUTCOME,
    build_h17_contract_forensics,
)
from ai_brain.stage3.acquisition.m336c_license_evaluator import (
    evaluate_independent_license_corpus,
)
from ai_brain.stage3.acquisition.m336c_readiness import (
    M336CReadinessDecision,
    build_m336c_raw_report,
    evaluate_m336c_readiness,
    verify_m336c_readiness,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.source_authority import (
    PublicationTarget,
    SourceUseScope,
    build_source_use_authorization,
    fuse_license_evidence,
    semantic_scope_invariant_hash,
    verify_source_use_authorization,
)
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.spdx_license import (
    AUTOMATIC_SPDX_MATCH_STATUSES,
    SPDXLicenseMatcher,
    classify_license_document,
)

PROJECT = Path(__file__).resolve().parents[1]


def test_frozen_spdx_snapshot_and_supported_templates(tmp_path):
    matcher = SPDXLicenseMatcher()
    assert matcher.snapshot["license_list_version"] == "3.28.0"
    assert len(matcher.snapshot["snapshot_manifest_hash"]) == 64
    for license_id in (
        "Apache-2.0",
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "GPL-2.0-only",
    ):
        receipt = matcher.match(
            (matcher.snapshot_root / f"{license_id}.txt").read_bytes(),
            source_document=f"{license_id}/LICENSE",
        )
        assert receipt.match_status in AUTOMATIC_SPDX_MATCH_STATUSES
        assert receipt.template_license_id == license_id
        assert receipt.spdx_snapshot_hash == matcher.snapshot_hash
    copied = tmp_path / "snapshot"
    copied.mkdir()
    for source in matcher.snapshot_root.iterdir():
        (copied / source.name).write_bytes(source.read_bytes())
    (copied / "Apache-2.0.txt").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="file hash"):
        SPDXLicenseMatcher(copied)


def test_independent_license_corpus_has_zero_false_authority():
    report = evaluate_independent_license_corpus()
    assert report.case_count == 1500
    assert report.valid_variant_count == 500
    assert report.substantive_mutation_count == 500
    assert report.control_count == 500
    assert report.automatically_trusted_precision == "1.000000"
    assert report.false_apache_match_count == 0
    assert report.false_automatic_match_count == 0
    assert report.optional_apache_variant_rejected_count == 0
    assert report.true_conflict_mutation_blocked_count == 500


def test_additional_license_terms_are_typed_and_never_automatic():
    matcher = SPDXLicenseMatcher()
    apache = (matcher.snapshot_root / "Apache-2.0.txt").read_bytes()
    exact = matcher.match(apache, source_document="LICENSE")
    additional = matcher.match(
        apache + b"\nAdditional restriction: redistribution is forbidden.\n",
        source_document="module/LICENSE",
    )
    assert additional.match_status.value == "NEAR_MATCH_REVIEW_REQUIRED"
    assert additional.template_license_id == "Apache-2.0"
    assert additional.match_status not in AUTOMATIC_SPDX_MATCH_STATUSES
    fusion = fuse_license_evidence(
        pom_expressions=("Apache-2.0",),
        document_receipts=(exact, additional),
        source_correspondence_complete=True,
    )
    assert fusion.status.value == "ADDITIONAL_TERMS"
    incompatible = matcher.match(
        (matcher.snapshot_root / "MIT.txt").read_bytes(),
        source_document="module/LICENSE",
    )
    conflict = fuse_license_evidence(
        pom_expressions=("Apache-2.0",),
        document_receipts=(exact, incompatible),
        source_correspondence_complete=True,
    )
    assert conflict.status.value == "TRUE_LICENSE_CONFLICT"


@pytest.mark.parametrize(
    ("path", "role"),
    (
        ("LICENSE", "PROJECT_LICENSE"),
        ("module/LICENSE.txt", "MODULE_LICENSE"),
        ("NOTICE", "NOTICE"),
        ("docs/LICENSE", "THIRD_PARTY_LICENSE"),
        ("THIRD-PARTY.txt", "THIRD_PARTY_LICENSE"),
        ("dependencies.txt", "DEPENDENCY_LICENSE"),
        ("Copyright.txt", "COPYRIGHT_NOTICE"),
    ),
)
def test_license_document_roles_are_typed(path, role):
    assert classify_license_document(path).value == role


def test_source_use_authority_cannot_be_self_granted_or_forged():
    with pytest.raises(ValueError, match="model may not grant"):
        build_source_use_authorization(
            authority_kind="MODEL",
            authority_id="self",
            authorized_scopes=(SourceUseScope.RAW_SOURCE_REDISTRIBUTION,),
            publication_targets=(PublicationTarget.RAW_SOURCE_PUBLICATION,),
            policy_version="forged",
        )
    with pytest.raises(ValueError, match="incomplete"):
        build_source_use_authorization(
            authority_kind="TASK_SUPPLIED_POLICY",
            authority_id="missing-scope",
            authorized_scopes=(),
            publication_targets=(PublicationTarget.METRICS_ONLY_PUBLICATION,),
            policy_version="v1",
        )
    with pytest.raises(ValueError, match="exceeds"):
        build_source_use_authorization(
            authority_kind="TASK_SUPPLIED_POLICY",
            authority_id="local-only",
            authorized_scopes=(SourceUseScope.PRIVATE_LOCAL_ANALYSIS,),
            publication_targets=(PublicationTarget.RAW_SOURCE_PUBLICATION,),
            policy_version="v1",
        )
    receipt = build_source_use_authorization(
        authority_kind="TASK_SUPPLIED_POLICY",
        authority_id="M-33.6c",
        authorized_scopes=(SourceUseScope.PRIVATE_LOCAL_ANALYSIS,),
        publication_targets=(PublicationTarget.METRICS_ONLY_PUBLICATION,),
        policy_version="v1",
    )
    assert PublicationTarget.RAW_SOURCE_PUBLICATION not in receipt.publication_targets
    forged = replace(
        receipt,
        authorized_scopes=(
            SourceUseScope.PRIVATE_LOCAL_ANALYSIS,
            SourceUseScope.RAW_SOURCE_REDISTRIBUTION,
        ),
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_source_use_authorization(forged)
    semantics = {"declarations": ("java:example.Type.method()",), "trusted": True}
    private = {
        "semantic_binding": semantics,
        "source_use_scope": SourceUseScope.PRIVATE_LOCAL_ANALYSIS,
        "raw_export_manifest": (),
    }
    redistributable = {
        "semantic_binding": semantics,
        "source_use_scope": SourceUseScope.RAW_SOURCE_REDISTRIBUTION,
        "raw_export_manifest": ("example/Type.java",),
    }
    assert semantic_scope_invariant_hash(private) == semantic_scope_invariant_hash(
        redistributable
    )


def test_generic_java_resolution_closes_nested_and_transitive_type_variables():
    universe = build_java_type_universe(
        (
            source_symbol_metadata(
                "example.Outer.Builder", access="PRIVATE", enclosing_access="PUBLIC"
            ),
        )
    )
    common = {
        "universe": universe,
        "package_name": "example",
        "receiver_type": "example.Outer",
        "explicit_imports": {},
        "wildcard_imports": (),
        "type_variables": {},
        "lexical_owner_types": ("example.Base",),
    }
    lexical = resolve_java_type("Builder", **common)
    assert lexical.resolved_type == "example.Outer.Builder"
    assert lexical.resolution_kind is JavaResolutionKind.LEXICAL
    private_sibling = resolve_java_type(
        "Builder",
        **{
            **common,
            "receiver_type": "example.Outer.Sibling",
        },
    )
    assert private_sibling.resolved_type == "example.Outer.Builder"
    platform = build_java_type_universe(())
    imported_member = resolve_java_type(
        "Entry",
        universe=platform,
        package_name="example",
        receiver_type="example.MapView",
        explicit_imports={"Map": ("java.util.Map",)},
        wildcard_imports=(),
        type_variables={},
    )
    assert imported_member.resolved_type == "java.util.Map.Entry"
    transitive = resolve_java_type(
        "T",
        universe=platform,
        package_name="example",
        receiver_type="example.Generic",
        explicit_imports={},
        wildcard_imports=(),
        type_variables={"V": "Object", "T": "V"},
    )
    assert transitive.resolved_type == "java.lang.Object"
    assert transitive.resolution_kind is JavaResolutionKind.TYPE_VARIABLE


def test_unresolved_declaration_annotation_is_a_trust_blocker(tmp_path):
    source = tmp_path / "Example.java"
    source.write_text(
        "package example; public class Example { @Missing public int value() { return 1; } }\n",
        encoding="utf-8",
        newline="\n",
    )
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        (source,),
        bundle_id="m336c-annotation",
        domain_tags=("java-api",),
        imported_at="1970-01-01T00:00:00Z",
        source_root=tmp_path,
        store=store,
    )
    index = index_java_bundle(bundle, store)
    declaration = next(
        item for item in index.declarations if item.member_name == "value"
    )
    assert declaration.supported is False
    assert declaration.unsupported_reason == "unresolved_annotation_type:Missing"


def test_unresolved_parameter_annotation_is_a_trust_blocker(tmp_path):
    source = tmp_path / "Example.java"
    source.write_text(
        "package example; public class Example { public void accept(@Missing String value) {} }\n",
        encoding="utf-8",
        newline="\n",
    )
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        (source,),
        bundle_id="m336c-parameter-annotation",
        domain_tags=("java-api",),
        imported_at="1970-01-01T00:00:00Z",
        source_root=tmp_path,
        store=store,
    )
    index = index_java_bundle(bundle, store)
    declaration = next(
        item for item in index.declarations if item.member_name == "accept"
    )
    assert declaration.supported is False
    assert declaration.unsupported_reason == "unresolved_annotation_type:Missing"


def test_all_six_disclosed_candidates_are_analysis_eligible(tmp_path):
    preparation = prepare_disclosed_rehearsal(
        disclosed_root=PROJECT
        / "evaluation/m336b_final_java/acquisition_bundle/candidates",
        work_root=tmp_path / "roots",
        selected_root=tmp_path / "selected",
    )
    assert len(preparation.assessments) == 6
    assert len(preparation.roots) == 6
    assert len(preparation.selected_sources) == 120
    assert preparation.selector_receipt["selector_invocation_count"] == 1
    assert preparation.selector_receipt["selector_rerun_count"] == 0
    assert (
        sum(
            item.eligible_source_set.total_entry_count
            for item in preparation.assessments
        )
        == 1684
    )
    assert (
        sum(
            item.eligible_source_set.analysis_eligible_entry_count
            for item in preparation.assessments
        )
        == 1684
    )
    assert (
        sum(
            item.eligible_source_set.publication_eligible_entry_count
            for item in preparation.assessments
        )
        == 0
    )
    assert (
        sum(
            item.eligible_source_set.excluded_entry_count
            for item in preparation.assessments
        )
        == 0
    )
    conflicts = {
        item.family_id: item.conflict_forensics.classification.value
        for item in preparation.assessments
        if item.conflict_forensics
    }
    assert conflicts == {
        "httpcore5": "OPTIONAL_APPENDIX_OMITTED",
        "log4j-api": "REPLACEABLE_TEXT_DIFFERENCE",
        "picocli": "BYTE_DIFFERENT_BUT_SPDX_EQUIVALENT",
        "reactor-core": "BYTE_DIFFERENT_BUT_SPDX_EQUIVALENT",
    }


def test_h17_contract_forensics_is_complete_and_nonmutating():
    report = build_h17_contract_forensics(PROJECT)
    assert report["historical_outcome"] == H17_HISTORICAL_OUTCOME
    assert report["path_count"] == 57
    assert report["unknown_path_count"] == 0
    assert report["unclassified_field_count"] == 0
    assert report["missing_mandatory_field_count"] == 0
    assert report["unexpected_field_count"] == 0
    assert report["role_mismatch_count"] == 0
    assert report["previously_extra_protected_field_classified_count"] == 36
    assert report["status"] == "PASS"


def test_contract_generated_h_stage_and_1008_mutations():
    baseline = verify_contract_tree(complete_hypothetical_h_stage())
    assert baseline.status == "PASS"
    assert baseline.unknown_path_count == 0
    assert baseline.missing_role_binding_count == 0
    assert baseline.disclosure_claim_mismatch_count == 0
    mutations = run_contract_mutation_battery()
    assert mutations.mutation_count == mutations.rejected_count == 1008
    assert mutations.accepted_count == 0
    assert mutations.status == "PASS"
    with pytest.raises(ValueError, match="caller-supplied"):
        FinalArtifactContractRegistry(
            FINAL_ARTIFACT_CONTRACT_REGISTRY.contract.artifact_types[:-1]
        )


def test_disclosed_registry_remains_append_only_and_complete():
    verify_disclosed_java_registry()
    entries = load_disclosed_java_registry()
    assert len(entries) == 6
    assert len({item.coordinate for item in entries}) == 6
    for item in entries:
        assert item.archive_hash
        assert item.pom_hash
        assert item.source_url
        assert item.raw_source_hashes
        assert item.canonical_source_hashes
        assert item.source_tree_hash
        assert item.scm_revision
        assert item.correspondence_hash
        assert isinstance(item.declaration_fingerprints, tuple)


def test_future_pool_is_metadata_only_and_failure_tolerant():
    families = future_candidate_families()
    assert len(families) >= 16
    assert len({item.organization for item in families}) >= 10
    assert not any(item.required for item in families)
    assert not any(item.source_body_inspection_permitted for item in families)
    simulations = run_future_pool_simulations()
    assert {item.scenario for item in simulations} == {
        "ZERO_FAILURES",
        "TWENTY_FIVE_PERCENT_FAILURES",
        "FIFTY_PERCENT_FAILURES",
        "LICENSE_REVIEW_CASES",
        "SCM_CORRESPONDENCE_FAILURES",
        "CHECKSUM_ABSENCE",
        "DUPLICATE_ORGANIZATIONS",
        "ROOT_CONTRIBUTION_IMBALANCE",
    }
    assert all(item.minimum_three_roots_survive for item in simulations)
    assert all(item.preferred_five_roots_survive for item in simulations)


def _passing_readiness_reports():
    values = {
        "license_matching": {
            "precision": "1.000000",
            "false_apache_matches": 0,
            "optional_variants_rejected": 0,
            "true_conflict_mutations": 500,
            "true_conflict_mutations_blocked": 500,
        },
        "evidence_fusion": {
            "old_conflicts": 4,
            "classified_old_conflicts": 4,
            "false_candidate_conflicts": 0,
        },
        "document_roles": {"document_count": 27, "unresolved_role_count": 0},
        "source_use": {
            "authority_axes_separate": True,
            "local_does_not_imply_publication": True,
            "scope_semantic_hash_equal": True,
            "model_created_approvals_accepted": 0,
        },
        "candidate_qualification": {
            "candidate_count": 6,
            "typed_candidate_count": 6,
            "analysis_eligible_root_count": 6,
            "publication_eligible_root_count": 0,
            "candidate_specific_branch_count": 0,
        },
        "selector": {"invocation_count": 1, "rerun_count": 0},
        "java_production": {
            "completed": True,
            "proposal_count": 3519,
            "post_trust_pack_failures": 0,
            "evaluator_dependency_count": 0,
            "golden_read_count": 0,
        },
        "candidate_replay": {"compiled": True, "replay_without_evaluator": True},
        "evaluator": {
            "ran_after_production_seal": True,
            "location_precision": "1.000000",
            "location_recall": "1.000000",
            "semantic_precision": "1.000000",
            "semantic_recall": "1.000000",
            "trust_precision": "1.000000",
            "trust_coverage": "0.900000",
            "wrong_trusted_count": 0,
            "field_evidence_exactness": "1.000000",
            "resolution_agreement": "1.000000",
        },
        "runtime": {
            "installed": True,
            "runtime_queries_pass": True,
            "no_network": True,
        },
        "artifact_contract": {
            "h17_unknown_paths": 0,
            "h17_unclassified_fields": 0,
            "h17_missing_fields": 0,
            "h17_unexpected_fields": 0,
            "h17_role_mismatches": 0,
            "hypothetical_unknown_paths": 0,
            "hypothetical_missing_roles": 0,
            "hypothetical_missing_fields": 0,
            "hypothetical_extra_fields": 0,
            "disclosure_claim_mismatches": 0,
        },
        "disclosure_mutations": {
            "mutation_count": 1008,
            "rejected_count": 1008,
            "accepted_count": 0,
        },
        "formatting_tests": {
            "ruff_format": True,
            "ruff_lint": True,
            "windows_suite": True,
            "karina_suite": True,
            "windows_clean": True,
            "karina_clean": True,
            "branch_upstream_equal": True,
            "new_untouched_corpus_acquired": False,
        },
        "cross_platform": {"platform_independent_difference_count": 0},
    }
    return tuple(build_m336c_raw_report(name, value) for name, value in values.items())


def test_readiness_is_independently_recomputed_and_tamper_evident():
    reports = _passing_readiness_reports()
    gate = evaluate_m336c_readiness(reports)
    assert gate.decision is M336CReadinessDecision.SAFE_CONSERVATIVE_SUBSET
    assert gate.pass_count == gate.mandatory_count
    verify_m336c_readiness(reports, gate)
    tampered_data = dict(reports[0].data)
    tampered_data["false_apache_matches"] = 1
    tampered_report = replace(reports[0], data=tampered_data)
    with pytest.raises(ValueError, match="hash mismatch"):
        evaluate_m336c_readiness((tampered_report, *reports[1:]))
    with pytest.raises(ValueError, match="criteria, or decision"):
        verify_m336c_readiness(
            reports,
            replace(gate, decision=M336CReadinessDecision.BLOCKED),
        )
    with pytest.raises(ValueError, match="criteria, or decision"):
        verify_m336c_readiness(reports, replace(gate, gate_hash="0" * 64))
