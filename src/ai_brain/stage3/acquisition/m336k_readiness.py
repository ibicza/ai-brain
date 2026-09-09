"""Closed pre-freeze readiness gate for M-33.6k."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import content_hash

M336K_READY_STATUS = "READY_FOR_CANDIDATE_ISOLATED_FINAL_FREEZE"


@dataclass(frozen=True)
class M336KReadinessGate:
    schema_version: int
    contract_role: str
    exact_r27_sha: str
    archive_campaign_receipt_hash: str
    mixed_candidate_campaign_receipt_hash: str
    f26_inventory_receipt_hash: str
    f26_disclosure_report_hash: str
    candidate_rehearsal_report_hash: str
    full_route_rehearsal_report_hash: str
    cross_platform_report_hash: str
    source_leak_report_hash: str
    windows_quality_receipt_hash: str
    karina_quality_receipt_hash: str
    archive_case_count: int
    wrong_archive_decision_count: int
    unsafe_accepted_archive_count: int
    archive_candidate_local_escape_count: int
    mixed_candidate_attempt_count: int
    mixed_candidate_terminal_count: int
    mixed_candidate_missing_terminal_count: int
    mixed_candidate_escape_count: int
    f26_candidate_count: int
    f26_inventory_row_count: int
    f26_unaccounted_candidate_count: int
    f26_disclosure_entry_count: int
    candidate_local_error_escape_count: int
    unexpected_swallowed_exception_count: int
    authoritative_archive_inspection_count: int
    minimum_authoritative_inspections_per_candidate: int
    maximum_authoritative_inspections_per_candidate: int
    rejected_source_index_entry_count: int
    rejected_census_entry_count: int
    disclosed_full_route_status: str
    windows_quality_status: str
    karina_quality_status: str
    platform_neutral_difference_count: int
    source_leak_count: int
    final_new_acquisition_reservation_count: int
    final_new_acquisition_invocation_count: int
    new_untouched_source_body_bytes: int
    status: str
    readiness_hash: str


def build_m336k_readiness_gate(
    *,
    exact_r27_sha: str,
    archive_campaign: dict,
    mixed_campaign: dict,
    inventory: dict,
    disclosure: dict,
    candidate_rehearsal: dict,
    full_route_rehearsal: dict,
    cross_platform: dict,
    source_leak: dict,
    windows_quality: dict,
    karina_quality: dict,
) -> M336KReadinessGate:
    """Recompute the gate only from sealed measured exact-R27 evidence."""

    values = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_PRE_FREEZE_READINESS",
        "exact_r27_sha": exact_r27_sha,
        "archive_campaign_receipt_hash": archive_campaign["receipt_hash"],
        "mixed_candidate_campaign_receipt_hash": mixed_campaign["receipt_hash"],
        "f26_inventory_receipt_hash": inventory["receipt_hash"],
        "f26_disclosure_report_hash": disclosure["report_hash"],
        "candidate_rehearsal_report_hash": candidate_rehearsal["report_hash"],
        "full_route_rehearsal_report_hash": full_route_rehearsal["report_hash"],
        "cross_platform_report_hash": cross_platform["report_hash"],
        "source_leak_report_hash": source_leak["report_hash"],
        "windows_quality_receipt_hash": windows_quality["receipt_hash"],
        "karina_quality_receipt_hash": karina_quality["receipt_hash"],
        "archive_case_count": archive_campaign["case_count"],
        "wrong_archive_decision_count": archive_campaign[
            "wrong_archive_decision_count"
        ],
        "unsafe_accepted_archive_count": archive_campaign[
            "unsafe_accepted_archive_count"
        ],
        "archive_candidate_local_escape_count": archive_campaign[
            "candidate_local_case_escape_count"
        ],
        "mixed_candidate_attempt_count": mixed_campaign["total_attempt_count"],
        "mixed_candidate_terminal_count": mixed_campaign["total_terminal_count"],
        "mixed_candidate_missing_terminal_count": mixed_campaign[
            "missing_terminal_count"
        ],
        "mixed_candidate_escape_count": mixed_campaign["candidate_local_escape_count"],
        "f26_candidate_count": inventory["frozen_candidate_count"],
        "f26_inventory_row_count": inventory["candidate_inventory_row_count"],
        "f26_unaccounted_candidate_count": inventory["unaccounted_candidate_count"],
        "f26_disclosure_entry_count": disclosure["f26_disclosure_entry_count"],
        "candidate_local_error_escape_count": candidate_rehearsal[
            "candidate_local_error_escape_count"
        ],
        "unexpected_swallowed_exception_count": candidate_rehearsal[
            "unexpected_swallowed_exception_count"
        ],
        "authoritative_archive_inspection_count": candidate_rehearsal[
            "authoritative_archive_inspection_count"
        ],
        "minimum_authoritative_inspections_per_candidate": candidate_rehearsal[
            "minimum_authoritative_inspections_per_candidate"
        ],
        "maximum_authoritative_inspections_per_candidate": candidate_rehearsal[
            "maximum_authoritative_inspections_per_candidate"
        ],
        "rejected_source_index_entry_count": candidate_rehearsal[
            "rejected_source_index_entry_count"
        ],
        "rejected_census_entry_count": candidate_rehearsal[
            "rejected_census_entry_count"
        ],
        "disclosed_full_route_status": full_route_rehearsal["status"],
        "windows_quality_status": windows_quality["status"],
        "karina_quality_status": karina_quality["status"],
        "platform_neutral_difference_count": cross_platform[
            "platform_neutral_difference_count"
        ],
        "source_leak_count": source_leak["fresh_source_leak_count"],
        "final_new_acquisition_reservation_count": 0,
        "final_new_acquisition_invocation_count": 0,
        "new_untouched_source_body_bytes": 0,
        "status": M336K_READY_STATUS,
    }
    zero_fields = (
        "wrong_archive_decision_count",
        "unsafe_accepted_archive_count",
        "archive_candidate_local_escape_count",
        "mixed_candidate_missing_terminal_count",
        "mixed_candidate_escape_count",
        "f26_unaccounted_candidate_count",
        "candidate_local_error_escape_count",
        "unexpected_swallowed_exception_count",
        "rejected_source_index_entry_count",
        "rejected_census_entry_count",
        "platform_neutral_difference_count",
        "source_leak_count",
        "final_new_acquisition_reservation_count",
        "final_new_acquisition_invocation_count",
        "new_untouched_source_body_bytes",
    )
    if (
        len(exact_r27_sha) != 40
        or set(exact_r27_sha) - set("0123456789abcdef")
        or archive_campaign.get("status") != "PASS"
        or archive_campaign.get("case_count", 0) < 5_000
        or mixed_campaign.get("status") != "PASS"
        or mixed_campaign.get("batch_count") != 10
        or mixed_campaign.get("total_attempt_count")
        != mixed_campaign.get("total_terminal_count")
        or inventory.get("frozen_candidate_count") != 66
        or inventory.get("candidate_inventory_row_count") != 66
        or disclosure.get("status") != "PASS"
        or disclosure.get("f26_candidates_accounted") != 66
        or disclosure.get("f26_disclosure_entry_count") != 66
        or candidate_rehearsal.get("status") != "PASS"
        or candidate_rehearsal.get("candidate_count") != 66
        or candidate_rehearsal.get("terminal_receipt_count") != 66
        or candidate_rehearsal.get("authoritative_archive_inspection_count") != 66
        or candidate_rehearsal.get("minimum_authoritative_inspections_per_candidate")
        != 1
        or candidate_rehearsal.get("maximum_authoritative_inspections_per_candidate")
        != 1
        or full_route_rehearsal.get("status") != "PASS"
        or full_route_rehearsal.get("selected_file_count") != 180
        or full_route_rehearsal.get("selected_root_count", 0) < 3
        or cross_platform.get("status") != "PASS"
        or source_leak.get("status") != "PASS"
        or windows_quality.get("status") != "PASS"
        or karina_quality.get("status") != "PASS"
        or windows_quality.get("exact_sha") != exact_r27_sha
        or karina_quality.get("exact_sha") != exact_r27_sha
        or any(values[name] for name in zero_fields)
    ):
        raise ValueError("M336K readiness acceptance criteria failed")
    return M336KReadinessGate(**values, readiness_hash=content_hash(values))
