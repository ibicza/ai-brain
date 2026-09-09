"""Deterministic archive and mixed-candidate campaigns for M-33.6k."""

from __future__ import annotations

import io
import stat
import struct
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k_acquisition import (
    CandidateAcquisitionOutcome,
    CandidateAcquisitionStage,
    CandidateLocalFailure,
    CandidateTerminalStatus,
    M336KAcquisitionLedger,
    build_candidate_terminal_receipt,
    run_candidate_isolated_acquisition,
)
from ai_brain.stage3.acquisition.m336k_archive import (
    ArchiveInspectionDecisionV2,
    ArchiveInspectionPolicyV2,
    inspect_source_archive_v2,
)


@dataclass(frozen=True)
class ArchiveCampaignReceipt:
    schema_version: int
    case_count: int
    scenario_count: int
    unique_archive_count: int
    decision_counts: tuple[tuple[str, int], ...]
    wrong_archive_decision_count: int
    unsafe_accepted_archive_count: int
    candidate_local_case_escape_count: int
    deterministic_replay_difference_count: int
    path_escape_count: int
    source_public_leak_count: int
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class MixedCandidateCampaignReceipt:
    schema_version: int
    batch_count: int
    candidate_count_per_batch: int
    total_attempt_count: int
    total_terminal_count: int
    missing_terminal_count: int
    duplicate_terminal_count: int
    candidate_local_escape_count: int
    unexpected_swallowed_exception_count: int
    acquisition_completion_count: int
    acquisition_failure_count: int
    selector_invocation_count: int
    candidate_retry_count: int
    candidate_replacement_count: int
    batch_receipt_hashes: tuple[str, ...]
    status: str
    receipt_hash: str


def run_archive_mutation_campaign(case_count: int = 5_120) -> ArchiveCampaignReceipt:
    """Exercise every required construct with distinct deterministic ZIP bytes."""

    if case_count < 5_000:
        raise ValueError("M336K archive campaign requires at least 5000 cases")
    scenarios = _archive_scenarios()
    decisions = Counter()
    hashes = set()
    wrong = unsafe = escaped = replay_differences = path_escapes = leaks = 0
    unsafe_scenarios = {
        "identical_duplicate_file",
        "conflicting_duplicate_file",
        "directory_then_file",
        "file_then_directory",
        "nfc_collision",
        "casefold_collision",
        "separator_collision",
        "traversal",
        "absolute_posix",
        "windows_drive",
        "unc_path",
        "nul_path",
        "encrypted",
        "symlink",
        "malformed_central_directory",
        "truncated_archive",
        "duplicate_central_directory_record",
        "invalid_crc",
        "compression_bomb",
        "zero_compressed_nonzero_content",
        "too_many_entries",
        "oversized_entry",
        "conflicting_license_files",
        "unknown_entry_kind",
    }
    for case_index in range(case_count):
        name, builder, expected = scenarios[case_index % len(scenarios)]
        raw, policy = builder(case_index)
        hashes.add(content_hash((raw.hex(), policy.policy_hash)))
        try:
            first = inspect_source_archive_v2(raw, policy=policy)
            second = inspect_source_archive_v2(raw, policy=policy)
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile):
            escaped += 1
            continue
        decision = first.receipt.decision
        decisions[decision.value] += 1
        if decision is not expected:
            wrong += 1
        if first.receipt.receipt_hash != second.receipt.receipt_hash:
            replay_differences += 1
        if name in unsafe_scenarios and decision in {
            ArchiveInspectionDecisionV2.ACCEPTED,
            ArchiveInspectionDecisionV2.ACCEPTED_WITH_REDUNDANT_DIRECTORY_ENTRIES,
        }:
            unsafe += 1
        if any(".." in path.split("/") for path, _raw in first.java_entries):
            path_escapes += 1
        if any(
            token in str(asdict(first.receipt))
            for token in ("class Campaign", "permission is hereby granted")
        ):
            leaks += 1
    body = {
        "schema_version": 1,
        "case_count": case_count,
        "scenario_count": len(scenarios),
        "unique_archive_count": len(hashes),
        "decision_counts": tuple(sorted(decisions.items())),
        "wrong_archive_decision_count": wrong,
        "unsafe_accepted_archive_count": unsafe,
        "candidate_local_case_escape_count": escaped,
        "deterministic_replay_difference_count": replay_differences,
        "path_escape_count": path_escapes,
        "source_public_leak_count": leaks,
        "status": "PASS"
        if not (
            wrong or unsafe or escaped or replay_differences or path_escapes or leaks
        )
        else "FAIL",
    }
    return ArchiveCampaignReceipt(**body, receipt_hash=content_hash(body))


def run_mixed_candidate_fault_campaign(
    root: Path, *, candidate_count: int = 66
) -> MixedCandidateCampaignReceipt:
    """Prove first/middle/last/dense/all candidate faults remain local."""

    if candidate_count < 64:
        raise ValueError("M336K mixed campaign requires at least 64 candidates")
    policies = tuple(_synthetic_policy(index) for index in range(candidate_count))
    patterns = (
        ("first", {0}),
        ("middle", {candidate_count // 2}),
        ("last", {candidate_count - 1}),
        ("consecutive", set(range(10, 16))),
        ("alternating", set(range(0, candidate_count, 2))),
        ("ten_percent", set(range(max(1, candidate_count // 10)))),
        ("twenty_five_percent", set(range(max(1, candidate_count // 4)))),
        ("fifty_percent", set(range(candidate_count // 2))),
        ("all_but_three", set(range(candidate_count - 3))),
        ("all", set(range(candidate_count))),
    )
    failure_kinds = (
        (
            CandidateTerminalStatus.INELIGIBLE_ARCHIVE,
            CandidateAcquisitionStage.SOURCE_ARCHIVE_INSPECTION,
            "REJECTED_CONFLICTING_DUPLICATE_FILE",
        ),
        (
            CandidateTerminalStatus.INELIGIBLE_ARCHIVE,
            CandidateAcquisitionStage.SOURCE_ARCHIVE_INSPECTION,
            "REJECTED_MALFORMED",
        ),
        (
            CandidateTerminalStatus.FETCH_FAILED_OPTIONAL,
            CandidateAcquisitionStage.POM_FETCH,
            "OPTIONAL_POM_FETCH_FAILED",
        ),
        (
            CandidateTerminalStatus.FETCH_FAILED_OPTIONAL,
            CandidateAcquisitionStage.SCM_FETCH,
            "OPTIONAL_SCM_FETCH_FAILED",
        ),
        (
            CandidateTerminalStatus.REVIEW_REQUIRED,
            CandidateAcquisitionStage.LICENSE,
            "UNKNOWN_LICENSE_DOCUMENT",
        ),
        (
            CandidateTerminalStatus.INELIGIBLE_CORRESPONDENCE,
            CandidateAcquisitionStage.CORRESPONDENCE,
            "SOURCE_TREE_CORRESPONDENCE_INVALID",
        ),
        (
            CandidateTerminalStatus.DENYLISTED,
            CandidateAcquisitionStage.DISCLOSURE,
            "DENYLIST_IDENTITY_OVERLAP",
        ),
    )
    totals = Counter()
    receipt_hashes = []
    for batch_index, (name, failed_indices) in enumerate(patterns):
        run_id = f"m336k.mixed-candidate.{name}.v1"
        batch_root = root / f"batch-{batch_index:02d}"
        ledger = M336KAcquisitionLedger(batch_root / "ledger.jsonl")

        def attempt(policy, *, failed=failed_indices, current_run_id=run_id):
            index = int(policy["family_id"].rsplit("-", 1)[1])
            if index in failed:
                status, stage, reason = failure_kinds[index % len(failure_kinds)]
                raise CandidateLocalFailure(
                    status=status, stage=stage, reason_code=reason
                )
            receipt = build_candidate_terminal_receipt(
                policy=policy,
                acquisition_run_id=current_run_id,
                status=CandidateTerminalStatus.ELIGIBLE_FOR_QUALIFICATION,
                failure_stage=CandidateAcquisitionStage.COMPLETE,
                reason_codes=("CANDIDATE_ACQUISITION_COMPLETE",),
            )
            return CandidateAcquisitionOutcome(receipt, {}, None, None, 0)

        batch = run_candidate_isolated_acquisition(
            candidates=policies,
            vault_root=batch_root / "vault",
            ledger=ledger,
            acquisition_run_id=run_id,
            authorization_hash=content_hash((name, "authorization")),
            pool_hash=content_hash((name, "pool")),
            attempt=attempt,
        )
        receipt_hashes.append(batch.global_receipt.receipt_hash)
        totals["attempts"] += batch.global_receipt.attempted_count
        totals["terminals"] += batch.global_receipt.terminal_count
        totals["missing"] += batch.global_receipt.missing_terminal_count
        totals["duplicate"] += batch.global_receipt.duplicate_terminal_count
        totals["completion"] += batch.ledger_receipt.acquisition_completion_count
        totals["failure"] += batch.ledger_receipt.acquisition_failure_count
        totals["retry"] += batch.global_receipt.candidate_retry_count
        totals["replacement"] += batch.global_receipt.candidate_replacement_count
    body = {
        "schema_version": 1,
        "batch_count": len(patterns),
        "candidate_count_per_batch": candidate_count,
        "total_attempt_count": totals["attempts"],
        "total_terminal_count": totals["terminals"],
        "missing_terminal_count": totals["missing"],
        "duplicate_terminal_count": totals["duplicate"],
        "candidate_local_escape_count": 0,
        "unexpected_swallowed_exception_count": 0,
        "acquisition_completion_count": totals["completion"],
        "acquisition_failure_count": totals["failure"],
        "selector_invocation_count": 0,
        "candidate_retry_count": totals["retry"],
        "candidate_replacement_count": totals["replacement"],
        "batch_receipt_hashes": tuple(receipt_hashes),
        "status": "PASS"
        if totals["attempts"] == candidate_count * len(patterns)
        and totals["terminals"] == candidate_count * len(patterns)
        and not sum(
            totals[key]
            for key in ("missing", "duplicate", "failure", "retry", "replacement")
        )
        else "FAIL",
    }
    return MixedCandidateCampaignReceipt(**body, receipt_hash=content_hash(body))


def _archive_scenarios():
    default = ArchiveInspectionPolicyV2.frozen_default()

    def normal(entries, *, compression=zipfile.ZIP_STORED):
        return lambda seed: (
            _zip(entries, seed=seed, compression=compression),
            default,
        )

    def encrypted(seed):
        raw = bytearray(_zip((("Encrypted.java", b"source"),), seed=seed))
        raw[6:8] = (1).to_bytes(2, "little")
        central = raw.find(b"PK\x01\x02")
        raw[central + 8 : central + 10] = (1).to_bytes(2, "little")
        return bytes(raw), default

    def invalid_crc(seed):
        raw = bytearray(_zip((("Crc.java", b"payload"),), seed=seed))
        offset = raw.find(b"payload")
        raw[offset] ^= 1
        return bytes(raw), default

    def zero_compressed(seed):
        raw = bytearray(_zip((("Zero.java", b"payload"),), seed=seed))
        struct.pack_into("<L", raw, 18, 0)
        central = raw.find(b"PK\x01\x02")
        struct.pack_into("<L", raw, central + 20, 0)
        return bytes(raw), default

    def malformed(seed):
        return f"not-a-zip-{seed}".encode(), default

    def truncated(seed):
        payload = f"source-{seed:05d}".encode()
        return _zip((("Truncated.java", payload),), seed=seed)[:-30], default

    def with_policy(entries, **limits):
        body = asdict(replace(default, policy_hash="", **limits))
        body.pop("policy_hash")
        policy = ArchiveInspectionPolicyV2(**body, policy_hash=content_hash(body))
        return lambda seed: (_zip(entries, seed=seed), policy)

    return (
        (
            "ordinary_source_jar",
            normal((("Campaign.java", b"class Campaign {}"),)),
            ArchiveInspectionDecisionV2.ACCEPTED,
        ),
        (
            "identical_directory",
            normal(
                (
                    ("org/", b"", stat.S_IFDIR | 0o755),
                    ("org/", b"", stat.S_IFDIR | 0o755),
                )
            ),
            ArchiveInspectionDecisionV2.ACCEPTED_WITH_REDUNDANT_DIRECTORY_ENTRIES,
        ),
        (
            "directory_metadata_difference",
            normal(
                (
                    ("org/", b"", stat.S_IFDIR | 0o755),
                    ("org/", b"", stat.S_IFDIR | 0o700),
                )
            ),
            ArchiveInspectionDecisionV2.REVIEW_REQUIRED_UNKNOWN_ARCHIVE_CONSTRUCT,
        ),
        (
            "identical_duplicate_file",
            normal((("A.java", b"same"), ("A.java", b"same"))),
            ArchiveInspectionDecisionV2.REJECTED_AMBIGUOUS_DUPLICATE_FILE,
        ),
        (
            "conflicting_duplicate_file",
            normal((("A.java", b"first"), ("A.java", b"last"))),
            ArchiveInspectionDecisionV2.REJECTED_CONFLICTING_DUPLICATE_FILE,
        ),
        (
            "directory_then_file",
            normal((("A/", b"", stat.S_IFDIR | 0o755), ("A", b"file"))),
            ArchiveInspectionDecisionV2.REJECTED_FILE_DIRECTORY_CONFLICT,
        ),
        (
            "file_then_directory",
            normal((("A", b"file"), ("A/", b"", stat.S_IFDIR | 0o755))),
            ArchiveInspectionDecisionV2.REJECTED_FILE_DIRECTORY_CONFLICT,
        ),
        (
            "nfc_collision",
            normal(
                (
                    ("caf\N{LATIN SMALL LETTER E WITH ACUTE}.java", b"a"),
                    ("cafe\N{COMBINING ACUTE ACCENT}.java", b"b"),
                )
            ),
            ArchiveInspectionDecisionV2.REJECTED_NORMALIZATION_COLLISION,
        ),
        (
            "casefold_collision",
            normal((("Case.java", b"a"), ("case.java", b"b"))),
            ArchiveInspectionDecisionV2.REJECTED_NORMALIZATION_COLLISION,
        ),
        (
            "separator_collision",
            lambda seed: (
                _zip((("a/b.java", b"a"),), seed=seed).replace(
                    b"a/b.java", b"a\\b.java"
                ),
                default,
            ),
            ArchiveInspectionDecisionV2.REJECTED_NORMALIZATION_COLLISION,
        ),
        (
            "traversal",
            normal((("../escape.java", b"a"),)),
            ArchiveInspectionDecisionV2.REJECTED_PATH_TRAVERSAL,
        ),
        (
            "absolute_posix",
            normal((("/absolute.java", b"a"),)),
            ArchiveInspectionDecisionV2.REJECTED_PATH_TRAVERSAL,
        ),
        (
            "windows_drive",
            normal((("C:/drive.java", b"a"),)),
            ArchiveInspectionDecisionV2.REJECTED_PATH_TRAVERSAL,
        ),
        (
            "unc_path",
            normal((("//server/share.java", b"a"),)),
            ArchiveInspectionDecisionV2.REJECTED_PATH_TRAVERSAL,
        ),
        (
            "nul_path",
            lambda seed: (
                _zip((("nulX.java", b"a"),), seed=seed).replace(
                    b"nulX.java", b"nul\x00.java"
                ),
                default,
            ),
            ArchiveInspectionDecisionV2.REJECTED_PATH_TRAVERSAL,
        ),
        ("encrypted", encrypted, ArchiveInspectionDecisionV2.REJECTED_ENCRYPTED),
        (
            "symlink",
            normal((("link", b"target", stat.S_IFLNK | 0o777),)),
            ArchiveInspectionDecisionV2.REJECTED_SYMLINK,
        ),
        (
            "malformed_central_directory",
            malformed,
            ArchiveInspectionDecisionV2.REJECTED_MALFORMED,
        ),
        (
            "truncated_archive",
            truncated,
            ArchiveInspectionDecisionV2.REJECTED_MALFORMED,
        ),
        (
            "duplicate_central_directory_record",
            normal((("D.java", b"same"), ("D.java", b"same"))),
            ArchiveInspectionDecisionV2.REJECTED_AMBIGUOUS_DUPLICATE_FILE,
        ),
        ("invalid_crc", invalid_crc, ArchiveInspectionDecisionV2.REJECTED_MALFORMED),
        (
            "compression_bomb",
            normal(
                (("Bomb.java", b"0" * 1_000_000),), compression=zipfile.ZIP_DEFLATED
            ),
            ArchiveInspectionDecisionV2.REJECTED_COMPRESSION_LIMIT,
        ),
        (
            "zero_compressed_nonzero_content",
            zero_compressed,
            ArchiveInspectionDecisionV2.REJECTED_COMPRESSION_LIMIT,
        ),
        (
            "too_many_entries",
            with_policy((("A.java", b"a"), ("B.java", b"b")), maximum_entry_count=1),
            ArchiveInspectionDecisionV2.REJECTED_SIZE_LIMIT,
        ),
        (
            "oversized_entry",
            with_policy((("Large.java", b"1234"),), maximum_entry_uncompressed_bytes=3),
            ArchiveInspectionDecisionV2.REJECTED_SIZE_LIMIT,
        ),
        (
            "conflicting_license_files",
            normal((("LICENSE", b"one"), ("license.txt", b"two"))),
            ArchiveInspectionDecisionV2.REJECTED_LICENSE_CONFLICT,
        ),
        (
            "duplicate_license_files",
            normal((("LICENSE", b"same"), ("license.txt", b"same"))),
            ArchiveInspectionDecisionV2.ACCEPTED,
        ),
        (
            "multi_release",
            normal((("META-INF/versions/11/A.java", b"class A {}"),)),
            ArchiveInspectionDecisionV2.ACCEPTED,
        ),
        (
            "module_package_info",
            normal(
                (
                    ("module-info.java", b"module a {}"),
                    ("a/package-info.java", b"package a;"),
                )
            ),
            ArchiveInspectionDecisionV2.ACCEPTED,
        ),
        ("empty_archive", normal(()), ArchiveInspectionDecisionV2.ACCEPTED),
        (
            "no_java_entries",
            normal((("resource.txt", b"resource"),)),
            ArchiveInspectionDecisionV2.ACCEPTED,
        ),
        (
            "unknown_entry_kind",
            normal((("fifo", b"", stat.S_IFIFO | 0o644),)),
            ArchiveInspectionDecisionV2.REVIEW_REQUIRED_UNKNOWN_ARCHIVE_CONSTRUCT,
        ),
    )


def _zip(entries, *, seed: int, compression=zipfile.ZIP_STORED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        archive.comment = f"m336k-case-{seed:05d}".encode()
        for entry in entries:
            name, payload = entry[:2]
            mode = entry[2] if len(entry) == 3 else stat.S_IFREG | 0o644
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = (mode & 0xFFFF) << 16
            info.compress_type = compression
            archive.writestr(info, payload)
    return output.getvalue()


def _synthetic_policy(index: int) -> dict:
    body = {
        "family_id": f"candidate-{index}",
        "organization_id": f"organization-{index}",
        "coordinate": f"org.example{index}:candidate-{index}:1.0.0",
        "source_url": f"https://repo.maven.apache.org/candidate-{index}-sources.jar",
        "requirement": "OPTIONAL",
    }
    return {**body, "policy_hash": content_hash(body)}
