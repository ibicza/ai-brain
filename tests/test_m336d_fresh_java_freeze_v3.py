from __future__ import annotations

import base64
import io
import json
import zipfile
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    build_disclosed_java_material_entry,
)
from ai_brain.stage3.acquisition.m336d_adaptive_attacker import (
    run_adaptive_mutation_battery,
)
from ai_brain.stage3.acquisition.m336d_authority import (
    M336D_AUTHORITY_STATEMENT_SHA256,
    DerivedSourceAuthorizationReceipt,
    SourceAuthorizationBinding,
    load_pinned_authority_registry_for_development,
)
from ai_brain.stage3.acquisition.m336d_contracts import (
    PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    canonical_public_json,
)
from ai_brain.stage3.acquisition.m336d_correspondence import (
    derive_scm_correspondence_decision,
)
from ai_brain.stage3.acquisition.m336d_final_pipeline import (
    _candidate_overlap_counts,
    _disclosure_append,
    _failure_scenarios,
    _pom_declared_java_releases,
    _qualification_report,
    _select_once,
    _sidecar_value,
    frozen_candidate_seeds,
    frozen_prior_identity_denylist,
    scan_local_cache_names,
    validate_candidate_pool,
)
from ai_brain.stage3.acquisition.m336d_h17_mapping import (
    build_h17_occurrence_mapping,
)
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336d_legal_inventory import (
    LegalDocumentContainer,
    inventory_legal_documents,
)
from ai_brain.stage3.acquisition.m336d_readiness import (
    M336DReadinessDecision,
    M336DReadinessMode,
    build_primary_receipt,
    evaluate_m336d_readiness,
    verify_m336d_readiness,
)
from ai_brain.stage3.acquisition.m336d_spdx_expression import (
    LicenseApplicabilityScope,
    LicenseScopeKind,
    ScopedLicenseEvidence,
    ScopedLicenseStatus,
    parse_spdx_expression,
    pom_license_evidence,
    resolve_scoped_license,
)
from ai_brain.stage3.acquisition.m336d_spdx_reference import (
    build_independent_spdx_corpus,
    run_independent_spdx_differential,
)
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    SourceCorrespondenceStatus,
    SourceTreeCorrespondence,
    SourceTreeCorrespondenceEntry,
)
from ai_brain.stage3.acquisition.source_authority import (
    PublicationTarget,
    SourceUseScope,
)

PROJECT = Path(__file__).resolve().parents[1]
AUTHORITY = (
    b"M336D_USER_AUTHORITY_V1\n"
    b"source_use=PRIVATE_LOCAL_ANALYSIS,LOCAL_RESEARCH_EVALUATION,DERIVED_KNOWLEDGE_ONLY,RAW_SOURCE_RETENTION,PUBLIC_REPRODUCIBLE_EVALUATION\n"
    b"publication_allow=DERIVED_PACK_PUBLICATION,METRICS_ONLY_PUBLICATION\n"
    b"publication_deny=RAW_SOURCE_PUBLICATION,SOURCE_EXCERPT_PUBLICATION\n"
    b"raw_storage=LOCAL_SEALED_VAULT_ONLY\n"
    b"authority_may_narrow=true\n"
    b"authority_may_widen=false\n"
)


def _binding(**changes):
    values = {
        "f19_sha": "1" * 40,
        "acquisition_run_id": "run-1",
        "candidate_family_id": "candidate-1",
        "maven_coordinate": "org.example:example:1.0",
        "source_repository_url": "https://example.invalid/repository",
        "source_jar_sha256": "1" * 64,
        "pom_sha256": "2" * 64,
        "immutable_scm_commit": "3" * 40,
        "scm_archive_sha256": "4" * 64,
        "source_tree_hash": "5" * 64,
        "local_vault_manifest_hash": "6" * 64,
    }
    values.update(changes)
    return SourceAuthorizationBinding(**values)


def _registry(tmp_path):
    path = tmp_path / "authority.txt"
    path.write_bytes(AUTHORITY)
    return load_pinned_authority_registry_for_development(
        path, expected_statement_sha256=M336D_AUTHORITY_STATEMENT_SHA256
    )


def test_frozen_authority_root_is_unique_narrowing_and_replay_safe(tmp_path):
    assert bytes_hash(AUTHORITY) == M336D_AUTHORITY_STATEMENT_SHA256
    registry = _registry(tmp_path)
    assert registry.root.statement_sha256 == M336D_AUTHORITY_STATEMENT_SHA256
    receipt = registry.issue(_binding())
    child = registry.issue(
        _binding(),
        source_use_scopes=(SourceUseScope.DERIVED_KNOWLEDGE_ONLY,),
        publication_targets=(PublicationTarget.METRICS_ONLY_PUBLICATION,),
        parent=receipt,
    )
    registry.verify(child, expected_binding=_binding(), parent=receipt)
    with pytest.raises(ValueError, match="widen|absent"):
        registry.issue(
            _binding(),
            source_use_scopes=(SourceUseScope.RAW_SOURCE_REDISTRIBUTION,),
            parent=receipt,
        )
    with pytest.raises(ValueError, match="binding"):
        registry.verify(receipt, expected_binding=_binding(candidate_family_id="other"))
    with pytest.raises(TypeError):
        DerivedSourceAuthorizationReceipt(**asdict(receipt))
    forged = AUTHORITY.replace(b"METRICS_ONLY_PUBLICATION", b"RAW_SOURCE_PUBLICATION")
    forged_path = tmp_path / "forged.txt"
    forged_path.write_bytes(forged)
    with pytest.raises(ValueError, match="sole frozen"):
        load_pinned_authority_registry_for_development(
            forged_path, expected_statement_sha256=bytes_hash(forged)
        )


def test_spdx_expression_precedence_with_and_exact_scopes():
    expression = parse_spdx_expression(
        "(Apache-2.0 OR MIT) AND GPL-2.0-only WITH Classpath-exception-2.0"
    )
    assert "WITH Classpath-exception-2.0" in expression.canonical()
    root = LicenseApplicabilityScope.build(LicenseScopeKind.PROJECT_ROOT)
    module = LicenseApplicabilityScope.build(LicenseScopeKind.MODULE_PATH, "module")
    evidence = (
        ScopedLicenseEvidence.build(
            expression=parse_spdx_expression("Apache-2.0"),
            scope=root,
            evidence_receipt_hashes=("1" * 64,),
            status=ScopedLicenseStatus.RESOLVED,
            reason="ROOT",
        ),
        ScopedLicenseEvidence.build(
            expression=parse_spdx_expression("MIT"),
            scope=module,
            evidence_receipt_hashes=("2" * 64,),
            status=ScopedLicenseStatus.RESOLVED,
            reason="MODULE",
        ),
    )
    assert (
        resolve_scoped_license("module/src/A.java", evidence).expression.canonical()
        == "MIT"
    )
    assert (
        resolve_scoped_license("other/A.java", evidence).expression.canonical()
        == "Apache-2.0"
    )
    unspecified = pom_license_evidence(("Apache-2.0", "MIT"), evidence_hash="3" * 64)
    assert (
        unspecified.status
        is ScopedLicenseStatus.REVIEW_REQUIRED_UNSPECIFIED_MULTI_LICENSE
    )


def test_complete_legal_document_inventory_precedes_role_selection():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "demo-" + "a" * 40 + "/LICENSE",
            (
                PROJECT / "src/ai_brain/stage3/acquisition/data/spdx/3.28.0/MIT.txt"
            ).read_bytes(),
        )
        archive.writestr(
            "demo-" + "a" * 40 + "/module/COPYING.txt", b"unknown legal terms"
        )
        archive.writestr("demo-" + "a" * 40 + "/vendor/NOTICE.md", b"NOTICE only")
        archive.writestr("demo-" + "a" * 40 + "/src/A.java", b"class A {}")
    report = inventory_legal_documents(
        (LegalDocumentContainer("demo", output.getvalue()),)
    )
    assert report.discovered_document_count == 3
    assert report.classified_document_count == 3
    assert report.unclassified_document_count == 0
    assert {item.path.rsplit("/", 1)[-1] for item in report.rows} == {
        "LICENSE",
        "COPYING.txt",
        "NOTICE.md",
    }


def test_scm_correspondence_counts_are_derived_from_rows():
    rows = []
    for index, status in enumerate(
        (
            SourceCorrespondenceStatus.RAW_EXACT_MATCH,
            SourceCorrespondenceStatus.UNMATCHED,
        )
    ):
        body = {
            "artifact_path": f"src/A{index}.java",
            "repository_path": f"repo/A{index}.java" if index == 0 else None,
            "raw_sha256": str(index + 1) * 64,
            "canonical_sha256": str(index + 2) * 64,
            "status": status,
        }
        rows.append(
            SourceTreeCorrespondenceEntry(**body, entry_hash=content_hash(body))
        )
    body = {
        "entries": tuple(rows),
        "exact_match_count": 1,
        "relocated_match_count": 0,
        "generated_match_count": 0,
        "unmatched_count": 1,
        "ambiguous_count": 0,
        "eligible_entry_count": 1,
        "raw_exact_match_count": 1,
        "canonical_only_match_count": 0,
        "relocated_raw_match_count": 0,
        "relocated_canonical_match_count": 0,
        "normalization_receipt_hash": None,
    }
    correspondence = SourceTreeCorrespondence(
        **body, correspondence_hash=content_hash(body)
    )
    report = derive_scm_correspondence_decision(
        correspondence, selected_paths=("src/A0.java",)
    )
    assert report.total_candidate_java_entries == 2
    assert report.selected_entries_with_complete_scm_correspondence == 1
    assert report.complete_for_selected


def test_public_contract_is_recursive_canonical_and_source_safe():
    valid = canonical_public_json(
        {
            "schema_version": 1,
            "f19_sha": "3" * 40,
            "maximum_one_root_fraction": "0.333333",
            "metrics_used_count": 0,
            "oracle_golden_read_count": 0,
            "root_distribution": [["alpha", 60], ["beta", 60], ["gamma", 60]],
            "selected_file_count": 180,
            "selected_manifest_hash": "2" * 64,
            "selected_root_count": 3,
            "selector_invocation_count": 1,
            "selector_rerun_count": 0,
            "selector_seed": "m336d-frozen-selector-seed-v1",
            "selector_version": "m336d-global-selector-v1",
        }
    )
    valid_body = json.loads(valid)
    valid_body["receipt_hash"] = content_hash(valid_body)
    valid = canonical_public_json(valid_body)
    assert (
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "h19/selector_receipt.json", valid
        ).status
        == "PASS"
    )
    leaked = json.loads(valid)
    leaked["receipt_hash"] = base64.b64encode(b"public class Secret {}").decode()
    with pytest.raises(ValueError, match="encoded source"):
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "h19/selector_receipt.json", canonical_public_json(leaked)
        )
    with pytest.raises(ValueError, match="duplicate"):
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate_tree(
            (("h19/selector_receipt.json", valid), ("h19/selector_receipt.json", valid))
        )
    with pytest.raises(ValueError, match="no unique typed contract"):
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "h19/candidate_pack.sqlite3", b"SQLite format 3\x00" + b"\x00" * 496
        )


def test_leak_scan_checks_all_fresh_java_with_bounded_exact_windows(tmp_path):
    vault = tmp_path / "vault"
    source = vault / "candidates/fresh/sources/Fresh.java"
    source.parent.mkdir(parents=True)
    raw = b"public class Fresh {\n" + b"    int value = 1;\n" * 30 + b"}\n"
    source.write_bytes(raw)
    public_safe = tmp_path / "public-safe"
    public_safe.mkdir()
    (public_safe / "report.json").write_text(
        '{"schema_version":1,"status":"PASS"}\n', encoding="utf-8"
    )
    assert scan_fresh_source_leaks(vault, public_safe)["fresh_source_leak_count"] == 0
    public_window = tmp_path / "public-window"
    public_window.mkdir()
    (public_window / "report.log").write_bytes(b"prefix" + raw[10:266] + b"suffix")
    report = scan_fresh_source_leaks(vault, public_window)
    assert report["exact_256_byte_source_window_count"] == 1
    public_encoded = tmp_path / "public-encoded"
    public_encoded.mkdir()
    (public_encoded / "report.json").write_text(
        json.dumps({"payload": base64.b64encode(raw).decode("ascii")}) + "\n",
        encoding="utf-8",
    )
    assert (
        scan_fresh_source_leaks(vault, public_encoded)[
            "base64_or_hex_source_body_count"
        ]
        == 1
    )


def test_disclosure_append_denominator_is_downloaded_source_jars_only():
    base = {
        "coordinate": "example:artifact:1.0",
        "source_url": "https://repo.maven.apache.org/maven2/example/artifact/1.0/artifact-1.0-sources.jar",
        "pom_sha256": "2" * 64,
        "_raw_source_hashes": ("3" * 64,),
        "_canonical_source_hashes": ("4" * 64,),
        "source_tree_hash": "5" * 64,
        "immutable_scm_commit": "6" * 40,
        "correspondence": {"correspondence_hash": "7" * 64},
    }
    downloaded = {
        **base,
        "family_id": "downloaded",
        "source_jar_sha256": "1" * 64,
    }
    failed_before_download = {
        **base,
        "family_id": "not-downloaded",
        "coordinate": "example:other:1.0",
        "source_jar_sha256": "0" * 64,
    }
    append = _disclosure_append(
        [failed_before_download, downloaded],
        {"files": ()},
    )
    assert append["downloaded_candidate_count"] == 1
    assert append["attempted_candidate_count"] == 2
    assert append["all_downloaded_candidates_included"]


def test_exact_h17_occurrence_mapping_is_36_of_36():
    report = build_h17_occurrence_mapping(PROJECT)
    assert report.historical_occurrence_count == 36
    assert report.mapped_occurrence_count == 36
    assert report.unmapped_occurrence_count == 0
    assert (
        len({(item.h17_artifact_path, item.json_pointer) for item in report.rows}) == 36
    )


def test_adaptive_mutations_reject_at_intended_layers():
    report = run_adaptive_mutation_battery()
    assert report.mutation_count >= 10_000
    assert report.accepted_count == 0
    assert report.wrong_rejection_layer_count == 0


def test_independent_java_spdx_reference_has_required_denominator_and_agreement():
    jdk = Path(r"W:\toolbox_IDEA\programs\IdeaProjects\.jdks\openjdk-25.0.2\bin")
    if not (jdk / "javac.exe").is_file():
        pytest.skip("local JDK 21+ compiler is unavailable")
    assert len(build_independent_spdx_corpus()) >= 10_000
    report = run_independent_spdx_differential(
        javac=jdk / "javac.exe", java=jdk / "java.exe"
    )
    assert report.production_reference_agreement == "1.000000"
    assert report.false_automatic_license_identity_count == 0
    assert report.valid_optional_variant_rejected_count == 0
    assert report.substantive_mutation_accepted_count == 0
    assert report.multiple_match_automatic_acceptance_count == 0
    assert report.isolation_audit.production_to_reference_dependency_count == 0
    assert report.isolation_audit.reference_to_production_dependency_count == 0


def test_readiness_v2_recomputes_every_criterion_from_primary_receipts():
    payloads = {
        "authority": {
            "root_count": 1,
            "derived_receipt_valid_count": 6,
            "derived_receipt_count": 6,
            "scope_intersection_valid_count": 6,
            "scope_intersection_count": 6,
            "forgery_accepted_count": 0,
            "derived_pack_publication_allowed": True,
            "metrics_publication_allowed": True,
        },
        "license_differential": {
            "case_count": 10800,
            "disagreement_count": 0,
            "false_automatic_license_identity_count": 0,
            "valid_optional_variant_rejected_count": 0,
            "substantive_mutation_accepted_count": 0,
            "multiple_match_automatic_acceptance_count": 0,
        },
        "document_inventory": {
            "discovered_document_count": 24,
            "classified_document_count": 24,
            "unclassified_document_count": 0,
        },
        "correspondence": {
            "total_candidate_java_entries": 1684,
            "selected_entries": 120,
            "selected_entries_with_complete_scm_correspondence": 120,
        },
        "qualification": {
            "candidate_count": 6,
            "qualified_candidate_count": 6,
            "analysis_eligible_root_count": 6,
        },
        "selector": {
            "invocation_count": 1,
            "rerun_count": 0,
            "selected_file_count": 120,
        },
        "ordering": {
            "production_sequence": 1,
            "seal_sequence": 2,
            "evaluator_sequence": 3,
        },
        "pack": {"compile_pass_count": 2, "replay_pass_count": 2, "run_count": 2},
        "semantic_metrics": {
            "location_correct": 9824,
            "location_predicted": 9824,
            "semantic_correct": 9824,
            "semantic_predicted": 9824,
            "semantic_gold_count": 10000,
        },
        "trust_metrics": {
            "trust_correct": 9258,
            "trusted_count": 9258,
            "eligible_count": 10000,
            "wrong_trusted_count": 0,
        },
        "runtime": {"passed_count": 4, "query_count": 4},
        "artifact_contract": {"valid_artifact_count": 20, "artifact_count": 20},
        "adaptive_mutations": {
            "mutation_count": 10260,
            "accepted_count": 0,
            "wrong_rejection_layer_count": 0,
        },
        "h17_mapping": {
            "historical_occurrence_count": 36,
            "mapped_occurrence_count": 36,
            "unmapped_occurrence_count": 0,
        },
        "leak_scan": {"leak_count": 0, "scanned_artifact_count": 20},
        "cross_platform": {"difference_count": 0, "comparison_count": 17},
        "quality": {"passed_count": 10, "check_count": 10},
        "freshness": {
            "pre_f19_source_body_byte_count": 0,
            "global_acquisition_count": 0,
            "fresh_overlap_count": 0,
        },
    }
    receipts = tuple(
        build_primary_receipt(name, payload, source_report_hash=content_hash(payload))
        for name, payload in sorted(payloads.items())
    )
    gate = evaluate_m336d_readiness(
        receipts, mode=M336DReadinessMode.PRE_FREEZE_DISCLOSED
    )
    assert gate.decision is M336DReadinessDecision.PRE_FREEZE_PASS
    assert gate.pass_count == gate.mandatory_count
    verify_m336d_readiness(receipts, gate)
    changed = list(receipts)
    changed[0] = replace(
        changed[0], payload={**changed[0].payload, next(iter(changed[0].payload)): 999}
    )
    with pytest.raises(ValueError, match="changed"):
        verify_m336d_readiness(tuple(changed), gate)


def test_final_metadata_seeds_and_pool_enforce_diversity_and_optional_only():
    seeds = frozen_candidate_seeds()
    assert len(seeds) == 30
    assert len({item.organization_id for item in seeds}) >= 16
    assert (
        max(
            sum(other.organization_id == item.organization_id for other in seeds)
            for item in seeds
        )
        <= 2
    )
    candidates = []
    for item in seeds:
        candidate = {
            "family_id": item.family_id,
            "organization_id": item.organization_id,
            "requirement": "OPTIONAL",
        }
        candidates.append({**candidate, "policy_hash": content_hash(candidate)})
    candidates = tuple(candidates)
    body = {
        "schema_version": 1,
        "policy_version": "m336d.metadata-pool.v1",
        "candidate_count": len(candidates),
        "organization_count": len({item.organization_id for item in seeds}),
        "maximum_candidates_per_organization": 2,
        "required_candidate_count": 0,
        "optional_candidate_count": len(candidates),
        "pre_f19_source_body_bytes_received": 0,
        "candidates": candidates,
        "failed_seed_receipt_hashes": (),
    }
    pool = {**body, "pool_hash": content_hash(body)}
    assert len(validate_candidate_pool(pool)) == 30
    forged = {**pool, "pre_f19_source_body_bytes_received": 1}
    with pytest.raises(ValueError, match="hash/schema"):
        validate_candidate_pool(forged)


def test_local_cache_census_reads_names_and_metadata_only(tmp_path, monkeypatch):
    seed = frozen_candidate_seeds()[0]
    cache = tmp_path / "cache"
    cache.mkdir()
    source = cache / f"{seed.artifact_id}-{seed.version}-sources.jar"
    source.write_bytes(b"never read")
    repository_name = seed.scm_repository.removesuffix(".git").rsplit("/", 1)[-1]
    checkout = cache / repository_name
    (checkout / ".git").mkdir(parents=True)
    (cache / f"{repository_name}-{seed.scm_ref.rsplit('/', 1)[-1]}.zip").write_bytes(
        b"never read either"
    )

    def forbidden_read(_self):
        raise AssertionError("cache census read a source body")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read)
    report = scan_local_cache_names((("maven", cache),), platform="windows")
    assert report["source_body_bytes_read"] == 0
    assert report["excluded_family_ids"] == (seed.family_id,)
    assert {item["reason"] for item in report["matches"]} == {
        "EXACT_SOURCE_JAR_FILENAME_PRESENT",
        "SCM_ARCHIVE_FILENAME_PRESENT",
        "SCM_CHECKOUT_DIRECTORY_NAME_PRESENT",
    }
    assert all(item["excluded"] for item in report["matches"])
    assert all(item["receipt_hash"] for item in report["matches"])


def test_candidate_seeds_exclude_every_frozen_prior_identity_class():
    seeds = frozen_candidate_seeds()
    denylist = frozen_prior_identity_denylist()
    coordinates = {
        f"{item.group_id}:{item.artifact_id}:{item.version}" for item in seeds
    }
    pairs = {
        "/".join(item.scm_repository.removesuffix(".git").rsplit("/", 2)[-2:]).lower()
        for item in seeds
    }
    assert not (
        {item.family_id for item in seeds} & set(denylist["excluded_family_ids"])
    )
    assert not (coordinates & set(denylist["excluded_coordinates"]))
    assert not (
        {item.scm_repository for item in seeds}
        & set(denylist["excluded_scm_repositories"])
    )
    assert not ({item.scm_ref for item in seeds} & set(denylist["excluded_scm_refs"]))
    assert not (pairs & set(denylist["excluded_organization_repository_pairs"]))
    assert {"slf4j-api", "okio-jvm"} <= set(denylist["excluded_family_ids"])


def test_qualification_decisions_are_atomic_and_unknown_legal_docs_fail_closed():
    item = {
        "family_id": "candidate-a",
        "organization_id": "organization-a",
        "coordinate": "example:candidate-a:1",
        "artifact_authenticity_mode": "MAVEN_CENTRAL_PLUS_IMMUTABLE_SCM",
        "source_jar_sha256": "1" * 64,
        "pom_sha256": "2" * 64,
        "scm_archive_sha256": "3" * 64,
        "immutable_scm_commit": "4" * 40,
        "correspondence_complete_for_all_entries": True,
        "scoped_license_expressions": ("Apache-2.0",),
        "unclassified_legal_document_count": 1,
        "unknown_legal_document_role_count": 1,
        "preselection_overlap_counts": {},
        "analysis_eligible": False,
        "candidate_eligible_source_entry_count": 0,
        "legal_document_count": 2,
        "authority_receipt_hash": "5" * 64,
        "authority": {
            "permitted_source_use_scopes": ("RAW_SOURCE_RETENTION",),
            "permitted_publication_targets": (
                "DERIVED_PACK_PUBLICATION",
                "METRICS_ONLY_PUBLICATION",
            ),
            "denied_publication_targets": (
                "RAW_SOURCE_PUBLICATION",
                "SOURCE_EXCERPT_PUBLICATION",
            ),
        },
        "qualification_errors": ("LICENSE:UNKNOWN_LICENSE_DOCUMENT",),
    }
    decision = _qualification_report([item])["decisions"][0]
    assert decision["source_authenticity_decision"] == "AUTHENTIC"
    assert decision["scm_correspondence_decision"] == "COMPLETE"
    assert decision["scoped_license_decision"] == "REVIEW_REQUIRED"
    assert decision["knowledge_acquisition_eligibility_decision"] == "INELIGIBLE"
    assert decision["raw_source_publication_decision"] == "DENIED"
    assert decision["source_excerpt_publication_decision"] == "DENIED"
    assert decision["derived_pack_publication_decision"] == "NOT_APPLICABLE"
    assert decision["metrics_publication_decision"] == "ALLOWED"


def test_metadata_receipt_helpers_freeze_sidecar_and_declared_java_release():
    assert _sidecar_value(("a" * 64 + "  candidate-sources.jar\n").encode()) == "a" * 64
    with pytest.raises(ValueError, match="malformed"):
        _sidecar_value(b"not-a-checksum")
    pom = b"""<project><properties>
      <maven.compiler.release>21</maven.compiler.release>
      <java.version>17</java.version>
    </properties></project>"""
    assert _pom_declared_java_releases(pom) == (
        ("java.version", "17"),
        ("maven.compiler.release", "21"),
    )


def test_failure_simulation_uses_all_required_real_identity_scenarios():
    candidates = tuple(
        {
            "family_id": f"family-{index}",
            "organization_id": f"organization-{index // 2}",
            "source_sha256_sidecar_available": index % 2 == 0,
            "source_content_length": 100 + index,
            "pom_license_declarations": ()
            if index == 1
            else (("Apache-2.0", "Apache", "a" * 64),),
            "scm_repository": (
                f"https://github.com/apache/repository-{index}.git"
                if index < 2
                else f"https://github.com/example/repository-{index}.git"
            ),
        }
        for index in range(8)
    )
    report = _failure_scenarios(candidates, locally_excluded=("cached-family",))
    rows = {item["scenario_id"]: item for item in report["scenarios"]}
    required = {
        "without-sha256-sidecars",
        "scm-only-authenticity",
        "largest-organization-concentration",
        "multi-license-review",
        "above-size-percentile-75",
        "correlated-apache-hosted-repositories",
        "correlated-github-metadata-failure",
        "checksum-endpoint-outage",
        "scm-correspondence-failure-after-acquisition",
        "license-review-after-acquisition",
        "local-cache-exclusions",
    }
    assert required <= rows.keys()
    assert sum(name.startswith("individual:") for name in rows) == 8
    assert sum(name.startswith("organization:") for name in rows) == 4
    assert sum(name.startswith("deterministic-25-") for name in rows) == 4
    assert sum(name.startswith("deterministic-50-") for name in rows) == 8
    assert rows["local-cache-exclusions"]["failed_family_ids"] == ("cached-family",)
    assert report["minimum_roots_surviving_50_percent_loss"] == 4


def test_final_selector_invokes_once_for_exact_180_balanced_files(tmp_path):
    acquired = []
    for family in ("alpha", "beta", "gamma"):
        relatives = []
        for index in range(60):
            relative = f"p/{family}/C{index:03d}.java"
            path = tmp_path / "candidates" / family / "sources" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"package p.{family}; public class C{index:03d} {{ public void run() {{}} }}\n",
                encoding="utf-8",
                newline="\n",
            )
            relatives.append(relative)
        acquired.append(
            {
                "family_id": family,
                "analysis_eligible": True,
                "complete_correspondence_paths": tuple(relatives),
            }
        )
    selected, receipt = _select_once(acquired, tmp_path, f19_sha="1" * 40)
    assert selected["file_count"] == 180
    assert selected["root_count"] == 3
    assert selected["root_distribution"] == (
        ("alpha", 60),
        ("beta", 60),
        ("gamma", 60),
    )
    assert receipt["selector_invocation_count"] == 1
    assert receipt["selector_rerun_count"] == 0
    assert receipt["metrics_used_count"] == 0
    assert receipt["oracle_golden_read_count"] == 0
    assert (
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "h19/selector_receipt.json", canonical_public_json(receipt)
        ).status
        == "PASS"
    )
    forged = dict(receipt)
    forged["selected_manifest_hash"] = "9" * 64
    with pytest.raises(ValueError, match="invariant"):
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            "h19/selector_receipt.json", canonical_public_json(forged)
        )


def test_freshness_overlap_covers_every_disclosed_identity_class():
    archive = content_hash("archive")
    pom = content_hash("pom")
    raw = content_hash("raw")
    canonical = content_hash("canonical")
    tree = content_hash("tree")
    correspondence = content_hash("correspondence")
    declaration = content_hash(("demo", canonical))
    source_url = "https://repo.maven.apache.org/maven2/g/demo/1/demo-1-sources.jar"
    prior = build_disclosed_java_material_entry(
        coordinate="g:demo:1",
        version="1",
        source_url=source_url,
        archive_hash=archive,
        pom_hash=pom,
        raw_source_hashes=(raw,),
        canonical_source_hashes=(canonical,),
        source_tree_hash=tree,
        selected_relative_paths=("a.java",),
        declaration_fingerprints=(declaration,),
        scm_revision="1" * 40,
        correspondence_hash=correspondence,
        disclosure_reason="TEST",
        originating_chain="TEST",
    )
    current = {
        "coordinate": "g:demo:1",
        "family_id": "demo",
        "source_url": source_url,
        "source_jar_sha256": archive,
        "pom_sha256": pom,
        "_raw_source_hashes": (raw,),
        "_canonical_source_hashes": (canonical,),
        "source_tree_hash": tree,
        "immutable_scm_commit": "1" * 40,
        "correspondence": {"correspondence_hash": correspondence},
    }
    counts = _candidate_overlap_counts(current, (prior,), selected_paths=("a.java",))
    assert len(counts) == 12
    assert set(counts.values()) == {1}


def test_m336d_json_schemas_close_every_explicit_object_recursively():
    schema_root = Path("schemas/stage3")
    schemas = tuple(sorted(schema_root.glob("m336d_*.schema.json")))
    assert len(schemas) == 11

    def inspect(value, location: str) -> None:
        if isinstance(value, dict):
            value_type = value.get("type")
            if value_type == "object" or (
                isinstance(value_type, list) and "object" in value_type
            ):
                assert value.get("additionalProperties") is False, location
            for key, nested in value.items():
                inspect(nested, f"{location}/{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                inspect(nested, f"{location}/{index}")

    for path in schemas:
        inspect(json.loads(path.read_text(encoding="utf-8")), path.as_posix())
