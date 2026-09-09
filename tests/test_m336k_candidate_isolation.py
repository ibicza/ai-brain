from __future__ import annotations

import io
import runpy
import stat
import zipfile
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k_acquisition import (
    CandidateAcquisitionOutcome,
    CandidateAcquisitionStage,
    CandidateFailureScope,
    CandidateLocalFailure,
    CandidateTerminalStatus,
    M336KAcquisitionLedger,
    build_candidate_terminal_receipt,
    run_candidate_isolated_acquisition,
)
from ai_brain.stage3.acquisition.m336k_archive import (
    ArchiveBindingVerificationStatusV2,
    ArchiveDuplicateClassV2,
    ArchiveEntryKindV2,
    ArchiveInspectionDecisionV2,
    ArchiveInspectionPolicyV2,
    archive_decision_is_accepted,
    build_candidate_archive_inspection_binding,
    inspect_source_archive_v2,
    public_archive_forensics,
    verify_candidate_archive_inspection_binding,
)
from ai_brain.stage3.acquisition.m336k_campaigns import (
    run_archive_mutation_campaign,
    run_mixed_candidate_fault_campaign,
)
from ai_brain.stage3.acquisition.m336k_final_pipeline import (
    M336K_FINAL_RUN_ID,
    build_m336k_final_acquisition_authorization,
    m336k_candidate_terminal_policy,
    m336k_final_acquisition_authorization_from_dict,
    m336k_global_continuation_policy,
    verify_m336k_final_acquisition_authorization,
)
from ai_brain.stage3.acquisition.m336k_publication import (
    build_m336k_compatibility_summary,
)
from ai_brain.stage3.acquisition.m336k_readiness import (
    M336K_READY_STATUS,
    build_m336k_readiness_gate,
)


def _archive(entries, *, compression=zipfile.ZIP_STORED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for entry in entries:
            if len(entry) == 2:
                name, payload = entry
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.external_attr = (0o100644 & 0xFFFF) << 16
            else:
                name, payload, mode = entry
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.external_attr = (mode & 0xFFFF) << 16
            info.compress_type = compression
            archive.writestr(info, payload)
    return output.getvalue()


def _policy(family="candidate"):
    body = {
        "family_id": family,
        "organization_id": "example",
        "coordinate": f"org.example:{family}:1.0.0",
        "source_url": f"https://repo.maven.apache.org/{family}-sources.jar",
        "requirement": "OPTIONAL",
    }
    return {**body, "policy_hash": content_hash(body)}


def _outcome(policy, run_id, status, stage, code):
    receipt = build_candidate_terminal_receipt(
        policy=policy,
        acquisition_run_id=run_id,
        status=status,
        failure_stage=stage,
        reason_codes=(code,),
    )
    return CandidateAcquisitionOutcome(
        terminal_receipt=receipt,
        pipeline_item={},
        archive_result=None,
        archive_binding=None,
        authoritative_archive_inspection_count=0,
    )


def test_ordinary_archive_is_accepted_and_binding_replays() -> None:
    raw = _archive(
        (
            ("org/example/Example.java", b"package org.example; class Example {}\n"),
            ("LICENSE", b"permission is hereby granted\n"),
        )
    )
    result = inspect_source_archive_v2(raw)
    assert result.receipt.decision is ArchiveInspectionDecisionV2.ACCEPTED
    assert len(result.java_entries) == 1
    binding = build_candidate_archive_inspection_binding(
        candidate_identity=("candidate", "org.example:candidate:1.0.0"),
        result=result,
    )
    verified = verify_candidate_archive_inspection_binding(
        binding=binding,
        candidate_identity=("candidate", "org.example:candidate:1.0.0"),
        source_archive=raw,
    )
    assert verified.status is ArchiveBindingVerificationStatusV2.VERIFIED
    assert verified.independently_observed_receipt_hash == result.receipt.receipt_hash


def test_redundant_identical_directories_are_the_only_accepted_duplicates() -> None:
    raw = _archive(
        (("org/", b"", stat.S_IFDIR | 0o755), ("org/", b"", stat.S_IFDIR | 0o755))
    )
    result = inspect_source_archive_v2(raw)
    assert result.receipt.decision is (
        ArchiveInspectionDecisionV2.ACCEPTED_WITH_REDUNDANT_DIRECTORY_ENTRIES
    )
    assert result.receipt.path_groups[0].duplicate_class is (
        ArchiveDuplicateClassV2.REDUNDANT_IDENTICAL_DIRECTORY_ENTRY
    )


@pytest.mark.parametrize(
    ("entries", "decision", "classification"),
    (
        (
            (("A.java", b"same"), ("A.java", b"same")),
            ArchiveInspectionDecisionV2.REJECTED_AMBIGUOUS_DUPLICATE_FILE,
            ArchiveDuplicateClassV2.DUPLICATE_IDENTICAL_REGULAR_FILE,
        ),
        (
            (("A.java", b"first"), ("A.java", b"last")),
            ArchiveInspectionDecisionV2.REJECTED_CONFLICTING_DUPLICATE_FILE,
            ArchiveDuplicateClassV2.DUPLICATE_CONFLICTING_REGULAR_FILE,
        ),
        (
            (("A", b"file"), ("A/", b"", stat.S_IFDIR | 0o755)),
            ArchiveInspectionDecisionV2.REJECTED_FILE_DIRECTORY_CONFLICT,
            ArchiveDuplicateClassV2.FILE_DIRECTORY_PATH_CONFLICT,
        ),
    ),
)
def test_duplicate_regular_and_file_directory_paths_fail_closed(
    entries, decision, classification
) -> None:
    result = inspect_source_archive_v2(_archive(entries))
    assert result.receipt.decision is decision
    assert result.receipt.path_groups[0].duplicate_class is classification
    assert not archive_decision_is_accepted(result.receipt.decision)
    assert result.java_entries == ()


@pytest.mark.parametrize(
    "entries",
    (
        (
            ("caf\N{LATIN SMALL LETTER E WITH ACUTE}.java", b"a"),
            ("cafe\N{COMBINING ACUTE ACCENT}.java", b"b"),
        ),
        (("Case.java", b"a"), ("case.java", b"b")),
    ),
)
def test_normalization_casefold_and_separator_aliases_are_rejected(entries) -> None:
    result = inspect_source_archive_v2(_archive(entries))
    assert (
        result.receipt.decision
        is ArchiveInspectionDecisionV2.REJECTED_NORMALIZATION_COLLISION
    )


def test_backslash_separator_is_rejected() -> None:
    raw = _archive((("a/b.java", b"a"),)).replace(b"a/b.java", b"a\\b.java")
    result = inspect_source_archive_v2(raw)
    assert result.receipt.decision is (
        ArchiveInspectionDecisionV2.REJECTED_NORMALIZATION_COLLISION
    )


@pytest.mark.parametrize(
    "path",
    ("../escape.java", "/absolute.java", "C:/drive.java", "//server/share.java"),
)
def test_unsafe_paths_are_candidate_local_rejections(path: str) -> None:
    result = inspect_source_archive_v2(_archive(((path, b"x"),)))
    assert (
        result.receipt.decision is ArchiveInspectionDecisionV2.REJECTED_PATH_TRAVERSAL
    )


def test_symlink_encrypted_unknown_and_malformed_are_typed() -> None:
    symlink = inspect_source_archive_v2(
        _archive((("link", b"target", stat.S_IFLNK | 0o777),))
    )
    assert symlink.receipt.decision is ArchiveInspectionDecisionV2.REJECTED_SYMLINK

    encrypted_raw = bytearray(_archive((("A.java", b"source"),)))
    encrypted_raw[6:8] = (1).to_bytes(2, "little")
    central = encrypted_raw.find(b"PK\x01\x02")
    encrypted_raw[central + 8 : central + 10] = (1).to_bytes(2, "little")
    encrypted = inspect_source_archive_v2(bytes(encrypted_raw))
    assert encrypted.receipt.decision is ArchiveInspectionDecisionV2.REJECTED_ENCRYPTED

    unknown = inspect_source_archive_v2(
        _archive((("fifo", b"", stat.S_IFIFO | 0o644),))
    )
    assert unknown.receipt.entries[0].entry_kind is ArchiveEntryKindV2.OTHER
    assert unknown.receipt.decision is (
        ArchiveInspectionDecisionV2.REVIEW_REQUIRED_UNKNOWN_ARCHIVE_CONSTRUCT
    )
    malformed = inspect_source_archive_v2(b"not a zip")
    assert malformed.receipt.decision is ArchiveInspectionDecisionV2.REJECTED_MALFORMED


def test_size_compression_and_license_conflicts_are_typed() -> None:
    default = ArchiveInspectionPolicyV2.frozen_default()
    body = asdict(replace(default, maximum_entry_count=1, policy_hash=""))
    body.pop("policy_hash")
    strict = ArchiveInspectionPolicyV2(**body, policy_hash=content_hash(body))
    too_many = inspect_source_archive_v2(
        _archive((("A.java", b"a"), ("B.java", b"b"))), policy=strict
    )
    assert too_many.receipt.decision is ArchiveInspectionDecisionV2.REJECTED_SIZE_LIMIT

    bomb = inspect_source_archive_v2(
        _archive((("bomb.java", b"0" * 1_000_000),), compression=zipfile.ZIP_DEFLATED)
    )
    assert bomb.receipt.decision is (
        ArchiveInspectionDecisionV2.REJECTED_COMPRESSION_LIMIT
    )
    conflict = inspect_source_archive_v2(
        _archive((("LICENSE", b"license one"), ("license.txt", b"license two")))
    )
    assert conflict.receipt.decision is (
        ArchiveInspectionDecisionV2.REJECTED_LICENSE_CONFLICT
    )


def test_public_forensics_has_hashes_but_no_source_paths_or_payloads() -> None:
    raw = _archive(
        (("secret/Example.java", b"first"), ("secret/Example.java", b"second"))
    )
    result = inspect_source_archive_v2(raw)
    public = public_archive_forensics(result)
    encoded = str(public)
    assert "secret/Example.java" not in encoded
    assert "first" not in encoded
    assert "second" not in encoded
    assert public["unclassified_duplicate_group_count"] == 0


def test_candidate_local_failures_complete_global_acquisition(tmp_path: Path) -> None:
    policies = tuple(_policy(f"candidate-{index}") for index in range(8))
    run_id = "m336k.mixed.test"

    def attempt(policy):
        index = int(policy["family_id"].rsplit("-", 1)[1])
        if index in {0, 3, 7}:
            raise CandidateLocalFailure(
                status=CandidateTerminalStatus.INELIGIBLE_ARCHIVE,
                stage=CandidateAcquisitionStage.SOURCE_ARCHIVE_INSPECTION,
                reason_code="REJECTED_CONFLICTING_DUPLICATE_FILE",
            )
        return _outcome(
            policy,
            run_id,
            CandidateTerminalStatus.ELIGIBLE_FOR_QUALIFICATION,
            CandidateAcquisitionStage.COMPLETE,
            "CANDIDATE_ACQUISITION_COMPLETE",
        )

    ledger = M336KAcquisitionLedger(tmp_path / "ledger.jsonl")
    result = run_candidate_isolated_acquisition(
        candidates=policies,
        vault_root=tmp_path / "vault",
        ledger=ledger,
        acquisition_run_id=run_id,
        authorization_hash="a" * 64,
        pool_hash="b" * 64,
        attempt=attempt,
    )
    assert result.global_receipt.status == "ACQUISITION_COMPLETED"
    assert result.global_receipt.attempted_count == len(policies)
    assert result.global_receipt.terminal_count == len(policies)
    assert result.global_receipt.missing_terminal_count == 0
    assert result.global_receipt.duplicate_terminal_count == 0
    assert result.ledger_receipt.final_event == "ACQUISITION_COMPLETED"
    assert result.ledger_receipt.all_candidates_terminal_count == 1
    assert result.ledger_receipt.acquisition_failure_count == 0
    assert all(
        item.terminal_receipt.failure_scope
        in {CandidateFailureScope.CANDIDATE, CandidateFailureScope.NONE}
        for item in result.candidate_outcomes
    )


def test_unexpected_failure_is_global_and_never_swallowed(tmp_path: Path) -> None:
    policies = (_policy(),)
    ledger = M336KAcquisitionLedger(tmp_path / "ledger.jsonl")

    def unexpected(_policy):
        raise AssertionError("programming invariant")

    with pytest.raises(AssertionError, match="programming invariant"):
        run_candidate_isolated_acquisition(
            candidates=policies,
            vault_root=tmp_path / "vault",
            ledger=ledger,
            acquisition_run_id="m336k.global-failure.test",
            authorization_hash="a" * 64,
            pool_hash="b" * 64,
            attempt=unexpected,
        )
    assert ledger.receipt().final_event == "ACQUISITION_FAILED"
    assert ledger.receipt().acquisition_failure_count == 1


def test_complete_5000_case_archive_campaign() -> None:
    receipt = run_archive_mutation_campaign(5_000)
    assert receipt.status == "PASS"
    assert receipt.case_count == 5_000
    assert receipt.unique_archive_count == 5_000
    assert receipt.wrong_archive_decision_count == 0
    assert receipt.unsafe_accepted_archive_count == 0
    assert receipt.candidate_local_case_escape_count == 0


def test_complete_mixed_candidate_campaign(tmp_path: Path) -> None:
    receipt = run_mixed_candidate_fault_campaign(tmp_path / "mixed")
    assert receipt.status == "PASS"
    assert receipt.batch_count == 10
    assert receipt.total_attempt_count == 660
    assert receipt.total_terminal_count == 660
    assert receipt.missing_terminal_count == 0
    assert receipt.acquisition_completion_count == 10
    assert receipt.acquisition_failure_count == 0
    assert receipt.selector_invocation_count == 0


def test_final_authorization_roundtrip_and_policy_bindings() -> None:
    archive = ArchiveInspectionPolicyV2.frozen_default()
    terminal = m336k_candidate_terminal_policy()
    continuation = m336k_global_continuation_policy()
    authorization = build_m336k_final_acquisition_authorization(
        exact_r27_sha="1" * 40,
        exact_q27_sha="2" * 40,
        branch_ref="refs/heads/exp/stage3-m336k-candidate-fault-isolation-v11",
        acquisition_run_id=M336K_FINAL_RUN_ID,
        candidate_pool_hash="3" * 64,
        acquisition_policy_hash="4" * 64,
        archive_policy_hash=archive.policy_hash,
        candidate_terminal_policy_hash=terminal["policy_hash"],
        global_continuation_policy_hash=continuation["policy_hash"],
        route_manifest_hash="5" * 64,
        registry_manifest_hash="6" * 64,
        threshold_manifest_hash="7" * 64,
        allowed_network_hosts=("codeload.github.com", "repo.maven.apache.org"),
        expected_global_acquisition_count=1,
        expected_windows_acquisition_count=1,
        expected_karina_acquisition_count=0,
        candidate_retries_allowed=False,
        candidate_replacements_allowed=False,
        pre_f27_source_body_bytes=0,
    )
    roundtrip = m336k_final_acquisition_authorization_from_dict(asdict(authorization))
    assert roundtrip == authorization
    assert terminal["candidate_local_failures_continue"] is True
    assert terminal["unexpected_exceptions_are_global"] is True
    assert continuation["candidate_rejection_is_global_failure"] is False
    with pytest.raises(ValueError, match="invalid M336K"):
        verify_m336k_final_acquisition_authorization(
            replace(authorization, candidate_retries_allowed=True)
        )


def test_readiness_gate_requires_measured_candidate_isolation() -> None:
    exact = "a" * 40
    archive = {
        "receipt_hash": "1" * 64,
        "status": "PASS",
        "case_count": 5_000,
        "wrong_archive_decision_count": 0,
        "unsafe_accepted_archive_count": 0,
        "candidate_local_case_escape_count": 0,
    }
    mixed = {
        "receipt_hash": "2" * 64,
        "status": "PASS",
        "batch_count": 10,
        "total_attempt_count": 660,
        "total_terminal_count": 660,
        "missing_terminal_count": 0,
        "candidate_local_escape_count": 0,
    }
    inventory = {
        "receipt_hash": "3" * 64,
        "frozen_candidate_count": 66,
        "candidate_inventory_row_count": 66,
        "unaccounted_candidate_count": 0,
    }
    disclosure = {
        "report_hash": "4" * 64,
        "status": "PASS",
        "f26_candidates_accounted": 66,
        "f26_disclosure_entry_count": 66,
    }
    rehearsal = {
        "report_hash": "5" * 64,
        "status": "PASS",
        "candidate_count": 66,
        "terminal_receipt_count": 66,
        "candidate_local_error_escape_count": 0,
        "unexpected_swallowed_exception_count": 0,
        "authoritative_archive_inspection_count": 66,
        "minimum_authoritative_inspections_per_candidate": 1,
        "maximum_authoritative_inspections_per_candidate": 1,
        "rejected_source_index_entry_count": 0,
        "rejected_census_entry_count": 0,
    }
    full_route = {
        "report_hash": "6" * 64,
        "status": "PASS",
        "selected_file_count": 180,
        "selected_root_count": 3,
    }
    cross = {
        "report_hash": "7" * 64,
        "status": "PASS",
        "platform_neutral_difference_count": 0,
    }
    leak = {
        "report_hash": "8" * 64,
        "status": "PASS",
        "fresh_source_leak_count": 0,
    }
    windows = {"receipt_hash": "9" * 64, "status": "PASS", "exact_sha": exact}
    karina = {"receipt_hash": "b" * 64, "status": "PASS", "exact_sha": exact}

    gate = build_m336k_readiness_gate(
        exact_r27_sha=exact,
        archive_campaign=archive,
        mixed_campaign=mixed,
        inventory=inventory,
        disclosure=disclosure,
        candidate_rehearsal=rehearsal,
        full_route_rehearsal=full_route,
        cross_platform=cross,
        source_leak=leak,
        windows_quality=windows,
        karina_quality=karina,
    )
    assert gate.status == M336K_READY_STATUS
    assert gate.final_new_acquisition_invocation_count == 0
    with pytest.raises(ValueError, match="readiness acceptance"):
        build_m336k_readiness_gate(
            exact_r27_sha=exact,
            archive_campaign={**archive, "wrong_archive_decision_count": 1},
            mixed_campaign=mixed,
            inventory=inventory,
            disclosure=disclosure,
            candidate_rehearsal=rehearsal,
            full_route_rehearsal=full_route,
            cross_platform=cross,
            source_leak=leak,
            windows_quality=windows,
            karina_quality=karina,
        )


def test_compatibility_summary_excludes_platform_specific_preflight_hash(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "ai_brain.stage3.acquisition.m336k_publication.load_disclosed_java_registry",
        lambda _root: (),
    )
    (tmp_path / "registry_manifest.json").write_text("{}", encoding="utf-8")
    census = SimpleNamespace(
        analysis_eligible_file_count=200,
        parser_valid_file_count=190,
        callable_file_count=180,
        production_supported_file_count=175,
        selectable_root_count=4,
        selectable_file_count=170,
        census_hash="1" * 64,
    )
    shared = {
        "qualification_report": {"analysis_eligible_root_count": 4},
        "selectability_census": census,
        "feasibility_proof": SimpleNamespace(
            balanced_capacity=160, proof_hash="2" * 64
        ),
        "portable_vault_manifest": SimpleNamespace(
            manifest_hash="3" * 64, portable_tree_hash="4" * 64
        ),
        "source_entry_binding_manifest": SimpleNamespace(manifest_hash="5" * 64),
        "status": "PASS",
    }
    qualification = {"candidate_count": 0, "report_hash": content_hash([])}
    windows = build_m336k_compatibility_summary(
        exact_sha="7" * 40,
        preflight=SimpleNamespace(report_hash="8" * 64, **shared),
        qualification=qualification,
        registry_root=tmp_path,
    )
    karina = build_m336k_compatibility_summary(
        exact_sha="7" * 40,
        preflight=SimpleNamespace(report_hash="9" * 64, **shared),
        qualification=qualification,
        registry_root=tmp_path,
    )
    assert windows == karina
    assert "preflight_report_hash" not in windows
    qualification.update(
        {
            "schema_version": 1,
            "candidates": [],
            "historical_qualification_report_hash": "6" * 64,
        }
    )
    verify_qualification_inputs = runpy.run_path(
        "scripts/m336f_run_disclosed_closure.py"
    )["_verify_qualification_inputs"]
    verify_qualification_inputs(
        qualification,
        windows,
        r21_sha="7" * 40,
        binding_manifest_hash="5" * 64,
        census_hash="1" * 64,
        exact_phase="R27",
    )
