"""M-33.6d readiness V2 recomputed from hash-bound primary receipts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash


class M336DReadinessMode(StrEnum):
    PRE_FREEZE_DISCLOSED = "PRE_FREEZE_DISCLOSED"
    FINAL_FRESH = "FINAL_FRESH"


class M336DReadinessDecision(StrEnum):
    PRE_FREEZE_PASS = "PRE_FREEZE_PASS"
    FRESH_JAVA_PROVEN = "FRESH_JAVA_PROVEN"
    FRESH_JAVA_SEMANTICS_PASS_EXPORT_BLOCKED = (
        "FRESH_JAVA_SEMANTICS_PASS_EXPORT_BLOCKED"
    )
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class M336DPrimaryReceipt:
    schema_version: int
    report_type: str
    payload: dict
    source_report_hash: str
    receipt_hash: str


@dataclass(frozen=True)
class M336DReadinessCriterion:
    name: str
    primary_report_hashes: tuple[str, ...]
    numerator: int
    denominator: int
    formula: str
    observed_result: str
    threshold: str
    passed: bool
    criterion_hash: str


@dataclass(frozen=True)
class M336DReadinessGateV2:
    schema_version: int
    mode: M336DReadinessMode
    primary_receipt_hashes: tuple[tuple[str, str], ...]
    criteria: tuple[M336DReadinessCriterion, ...]
    mandatory_count: int
    pass_count: int
    failed_criteria: tuple[str, ...]
    decision: M336DReadinessDecision
    gate_hash: str


_REPORT_FIELDS = {
    "authority": {
        "root_count",
        "derived_receipt_valid_count",
        "derived_receipt_count",
        "scope_intersection_valid_count",
        "scope_intersection_count",
        "forgery_accepted_count",
        "derived_pack_publication_allowed",
        "metrics_publication_allowed",
    },
    "license_differential": {
        "case_count",
        "disagreement_count",
        "false_automatic_license_identity_count",
        "valid_optional_variant_rejected_count",
        "substantive_mutation_accepted_count",
        "multiple_match_automatic_acceptance_count",
    },
    "document_inventory": {
        "discovered_document_count",
        "classified_document_count",
        "unclassified_document_count",
    },
    "correspondence": {
        "total_candidate_java_entries",
        "selected_entries",
        "selected_entries_with_complete_scm_correspondence",
    },
    "qualification": {
        "candidate_count",
        "qualified_candidate_count",
        "analysis_eligible_root_count",
    },
    "selector": {"invocation_count", "rerun_count", "selected_file_count"},
    "ordering": {"production_sequence", "seal_sequence", "evaluator_sequence"},
    "pack": {"compile_pass_count", "replay_pass_count", "run_count"},
    "semantic_metrics": {
        "location_correct",
        "location_predicted",
        "semantic_correct",
        "semantic_predicted",
        "semantic_gold_count",
    },
    "trust_metrics": {
        "trust_correct",
        "trusted_count",
        "eligible_count",
        "wrong_trusted_count",
    },
    "runtime": {"passed_count", "query_count"},
    "artifact_contract": {"valid_artifact_count", "artifact_count"},
    "adaptive_mutations": {
        "mutation_count",
        "accepted_count",
        "wrong_rejection_layer_count",
    },
    "h17_mapping": {
        "historical_occurrence_count",
        "mapped_occurrence_count",
        "unmapped_occurrence_count",
    },
    "leak_scan": {"leak_count", "scanned_artifact_count"},
    "cross_platform": {"difference_count", "comparison_count"},
    "quality": {"passed_count", "check_count"},
    "freshness": {
        "pre_f19_source_body_byte_count",
        "global_acquisition_count",
        "fresh_overlap_count",
    },
}


def build_primary_receipt(
    report_type: str, payload: dict, *, source_report_hash: str
) -> M336DPrimaryReceipt:
    expected = _REPORT_FIELDS.get(report_type)
    if expected is None or set(payload) != expected:
        raise ValueError("M-33.6d primary receipt schema is incomplete or substituted")
    _validate_primary_scalars(payload)
    if not _is_hash(source_report_hash):
        raise ValueError("M-33.6d primary source report hash is invalid")
    body = {
        "schema_version": 1,
        "report_type": report_type,
        "payload": payload,
        "source_report_hash": source_report_hash,
    }
    return M336DPrimaryReceipt(**body, receipt_hash=content_hash(body))


def load_primary_receipts(root: Path) -> tuple[M336DPrimaryReceipt, ...]:
    root = root.resolve(strict=True)
    receipts = []
    for report_type in sorted(_REPORT_FIELDS):
        path = (root / f"{report_type}.json").resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("primary readiness receipt escapes its root")
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
        if "\r" in text or not text.endswith("\n") or text.endswith("\n\n"):
            raise ValueError("primary readiness receipt is not canonical UTF-8/LF")
        value = json.loads(text, object_pairs_hook=_unique)
        if (canonical_json(value) + "\n").encode() != raw:
            raise ValueError("primary readiness receipt is not canonical JSON")
        receipt = build_primary_receipt(
            value["report_type"],
            value["payload"],
            source_report_hash=value["source_report_hash"],
        )
        if (
            set(value)
            != {
                "schema_version",
                "report_type",
                "payload",
                "source_report_hash",
                "receipt_hash",
            }
            or value["schema_version"] != 1
            or receipt.receipt_hash != value["receipt_hash"]
        ):
            raise ValueError("primary readiness receipt hash or framing mismatch")
        receipts.append(receipt)
    if {item.report_type for item in receipts} != set(_REPORT_FIELDS):
        raise ValueError("primary readiness receipt denominator mismatch")
    return tuple(receipts)


def evaluate_m336d_readiness(
    receipts: tuple[M336DPrimaryReceipt, ...], *, mode: M336DReadinessMode
) -> M336DReadinessGateV2:
    mode = M336DReadinessMode(mode)
    by_type = _verify_receipt_set(receipts)
    data = {name: receipt.payload for name, receipt in by_type.items()}
    criteria = []

    def exact(name: str, report: str, observed: int, expected: int) -> None:
        _criterion(
            criteria,
            name,
            (by_type[report].receipt_hash,),
            observed,
            1,
            "EQ",
            str(observed),
            str(expected),
            observed == expected,
        )

    def all_rows(name: str, report: str, numerator: int, denominator: int) -> None:
        _criterion(
            criteria,
            name,
            (by_type[report].receipt_hash,),
            numerator,
            denominator,
            "RATIO_EQ",
            _ratio(numerator, denominator),
            "1.000000",
            denominator > 0 and numerator == denominator,
        )

    authority = data["authority"]
    exact("authority_root_count", "authority", authority["root_count"], 1)
    all_rows(
        "derived_authorization_receipts",
        "authority",
        authority["derived_receipt_valid_count"],
        authority["derived_receipt_count"],
    )
    all_rows(
        "authority_scope_intersection",
        "authority",
        authority["scope_intersection_valid_count"],
        authority["scope_intersection_count"],
    )
    exact(
        "authority_forgery_acceptance",
        "authority",
        authority["forgery_accepted_count"],
        0,
    )
    exact(
        "derived_pack_publication_authority",
        "authority",
        int(authority["derived_pack_publication_allowed"]),
        1,
    )
    exact(
        "metrics_publication_authority",
        "authority",
        int(authority["metrics_publication_allowed"]),
        1,
    )

    license_data = data["license_differential"]
    all_rows(
        "independent_spdx_agreement",
        "license_differential",
        license_data["case_count"] - license_data["disagreement_count"],
        license_data["case_count"],
    )
    for field in (
        "false_automatic_license_identity_count",
        "valid_optional_variant_rejected_count",
        "substantive_mutation_accepted_count",
        "multiple_match_automatic_acceptance_count",
    ):
        exact(field, "license_differential", license_data[field], 0)

    inventory = data["document_inventory"]
    all_rows(
        "legal_document_denominator",
        "document_inventory",
        inventory["classified_document_count"],
        inventory["discovered_document_count"],
    )
    exact(
        "unclassified_legal_documents",
        "document_inventory",
        inventory["unclassified_document_count"],
        0,
    )
    correspondence = data["correspondence"]
    all_rows(
        "selected_scm_correspondence",
        "correspondence",
        correspondence["selected_entries_with_complete_scm_correspondence"],
        correspondence["selected_entries"],
    )
    all_rows(
        "candidate_scm_correspondence_denominator",
        "correspondence",
        correspondence["total_candidate_java_entries"],
        correspondence["total_candidate_java_entries"],
    )
    qualification = data["qualification"]
    all_rows(
        "typed_candidate_qualification",
        "qualification",
        qualification["qualified_candidate_count"],
        qualification["candidate_count"],
    )
    minimum_roots = 6 if mode is M336DReadinessMode.PRE_FREEZE_DISCLOSED else 3
    _criterion(
        criteria,
        "analysis_eligible_roots",
        (by_type["qualification"].receipt_hash,),
        qualification["analysis_eligible_root_count"],
        1,
        "GE",
        str(qualification["analysis_eligible_root_count"]),
        str(minimum_roots),
        qualification["analysis_eligible_root_count"] >= minimum_roots,
    )

    selector = data["selector"]
    exact("selector_invocation", "selector", selector["invocation_count"], 1)
    exact("selector_rerun", "selector", selector["rerun_count"], 0)
    minimum_selected = 1 if mode is M336DReadinessMode.PRE_FREEZE_DISCLOSED else 180
    _criterion(
        criteria,
        "selected_file_count",
        (by_type["selector"].receipt_hash,),
        selector["selected_file_count"],
        1,
        "GE",
        str(selector["selected_file_count"]),
        str(minimum_selected),
        selector["selected_file_count"] >= minimum_selected,
    )
    ordering = data["ordering"]
    ordered = (
        ordering["production_sequence"]
        < ordering["seal_sequence"]
        < ordering["evaluator_sequence"]
    )
    _criterion(
        criteria,
        "production_seal_evaluator_order",
        (by_type["ordering"].receipt_hash,),
        int(ordered),
        1,
        "EQ",
        str(int(ordered)),
        "1",
        ordered,
    )
    pack = data["pack"]
    all_rows(
        "candidate_pack_compile", "pack", pack["compile_pass_count"], pack["run_count"]
    )
    all_rows(
        "candidate_pack_replay", "pack", pack["replay_pass_count"], pack["run_count"]
    )

    semantic = data["semantic_metrics"]
    all_rows(
        "location_precision",
        "semantic_metrics",
        semantic["location_correct"],
        semantic["location_predicted"],
    )
    all_rows(
        "semantic_precision",
        "semantic_metrics",
        semantic["semantic_correct"],
        semantic["semantic_predicted"],
    )
    _ratio_threshold(
        criteria,
        "semantic_recall",
        by_type["semantic_metrics"].receipt_hash,
        semantic["semantic_correct"],
        semantic["semantic_gold_count"],
        950_000,
    )
    trust = data["trust_metrics"]
    all_rows(
        "trust_precision",
        "trust_metrics",
        trust["trust_correct"],
        trust["trusted_count"],
    )
    _ratio_threshold(
        criteria,
        "trust_coverage",
        by_type["trust_metrics"].receipt_hash,
        trust["trusted_count"],
        trust["eligible_count"],
        850_000,
    )
    exact("wrong_trusted", "trust_metrics", trust["wrong_trusted_count"], 0)
    all_rows(
        "runtime_results",
        "runtime",
        data["runtime"]["passed_count"],
        data["runtime"]["query_count"],
    )
    all_rows(
        "artifact_contract_validation",
        "artifact_contract",
        data["artifact_contract"]["valid_artifact_count"],
        data["artifact_contract"]["artifact_count"],
    )
    mutations = data["adaptive_mutations"]
    exact(
        "adaptive_mutation_acceptance",
        "adaptive_mutations",
        mutations["accepted_count"],
        0,
    )
    exact(
        "adaptive_mutation_rejection_layer",
        "adaptive_mutations",
        mutations["wrong_rejection_layer_count"],
        0,
    )
    _criterion(
        criteria,
        "adaptive_mutation_denominator",
        (by_type["adaptive_mutations"].receipt_hash,),
        mutations["mutation_count"],
        1,
        "GE",
        str(mutations["mutation_count"]),
        "10000",
        mutations["mutation_count"] >= 10_000,
    )
    h17 = data["h17_mapping"]
    all_rows(
        "h17_exact_mapping",
        "h17_mapping",
        h17["mapped_occurrence_count"],
        h17["historical_occurrence_count"],
    )
    exact(
        "h17_unmapped_occurrences", "h17_mapping", h17["unmapped_occurrence_count"], 0
    )
    exact("public_source_leaks", "leak_scan", data["leak_scan"]["leak_count"], 0)
    _criterion(
        criteria,
        "leak_scan_denominator",
        (by_type["leak_scan"].receipt_hash,),
        data["leak_scan"]["scanned_artifact_count"],
        1,
        "GE",
        str(data["leak_scan"]["scanned_artifact_count"]),
        "1",
        data["leak_scan"]["scanned_artifact_count"] > 0,
    )
    exact(
        "cross_platform_differences",
        "cross_platform",
        data["cross_platform"]["difference_count"],
        0,
    )
    all_rows(
        "cross_platform_comparisons",
        "cross_platform",
        data["cross_platform"]["comparison_count"],
        data["cross_platform"]["comparison_count"],
    )
    all_rows(
        "quality_gates",
        "quality",
        data["quality"]["passed_count"],
        data["quality"]["check_count"],
    )
    freshness = data["freshness"]
    exact(
        "pre_f19_source_body_bytes",
        "freshness",
        freshness["pre_f19_source_body_byte_count"],
        0,
    )
    expected_acquisitions = 0 if mode is M336DReadinessMode.PRE_FREEZE_DISCLOSED else 1
    exact(
        "global_fresh_acquisition",
        "freshness",
        freshness["global_acquisition_count"],
        expected_acquisitions,
    )
    exact("fresh_overlap", "freshness", freshness["fresh_overlap_count"], 0)

    result = tuple(criteria)
    failed = tuple(item.name for item in result if not item.passed)
    if failed:
        decision = M336DReadinessDecision.BLOCKED
    elif mode is M336DReadinessMode.PRE_FREEZE_DISCLOSED:
        decision = M336DReadinessDecision.PRE_FREEZE_PASS
    elif (
        authority["derived_pack_publication_allowed"]
        and authority["metrics_publication_allowed"]
    ):
        decision = M336DReadinessDecision.FRESH_JAVA_PROVEN
    else:
        decision = M336DReadinessDecision.FRESH_JAVA_SEMANTICS_PASS_EXPORT_BLOCKED
    body = {
        "schema_version": 2,
        "mode": mode,
        "primary_receipt_hashes": tuple(
            sorted((name, item.receipt_hash) for name, item in by_type.items())
        ),
        "criteria": result,
        "mandatory_count": len(result),
        "pass_count": sum(item.passed for item in result),
        "failed_criteria": failed,
        "decision": decision,
    }
    return M336DReadinessGateV2(**body, gate_hash=content_hash(body))


def verify_m336d_readiness(
    receipts: tuple[M336DPrimaryReceipt, ...], claimed: M336DReadinessGateV2
) -> None:
    recomputed = evaluate_m336d_readiness(receipts, mode=claimed.mode)
    if recomputed != claimed:
        raise ValueError(
            "M-33.6d primary row, denominator, ratio, criterion, or decision changed"
        )


def _criterion(
    result, name, hashes, numerator, denominator, formula, observed, threshold, passed
):
    if denominator <= 0:
        passed = False
    body = {
        "name": name,
        "primary_report_hashes": tuple(sorted(hashes)),
        "numerator": numerator,
        "denominator": denominator,
        "formula": formula,
        "observed_result": observed,
        "threshold": threshold,
        "passed": bool(passed),
    }
    result.append(M336DReadinessCriterion(**body, criterion_hash=content_hash(body)))


def _ratio_threshold(result, name, receipt_hash, numerator, denominator, threshold_ppm):
    observed = _ratio(numerator, denominator)
    _criterion(
        result,
        name,
        (receipt_hash,),
        numerator,
        denominator,
        "RATIO_GE",
        observed,
        f"{threshold_ppm / 1_000_000:.6f}",
        denominator > 0 and numerator * 1_000_000 >= denominator * threshold_ppm,
    )


def _ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "EMPTY_DENOMINATOR"
    return f"{numerator / denominator:.6f}"


def _verify_receipt_set(receipts):
    if len(receipts) != len(_REPORT_FIELDS):
        raise ValueError("M-33.6d primary receipt denominator mismatch")
    by_type = {}
    for receipt in receipts:
        rebuilt = build_primary_receipt(
            receipt.report_type,
            receipt.payload,
            source_report_hash=receipt.source_report_hash,
        )
        if rebuilt != receipt or receipt.report_type in by_type:
            raise ValueError("M-33.6d primary receipt changed or duplicated")
        by_type[receipt.report_type] = receipt
    if set(by_type) != set(_REPORT_FIELDS):
        raise ValueError("M-33.6d primary receipt set is incomplete")
    return by_type


def _validate_primary_scalars(payload):
    for name, value in payload.items():
        if isinstance(value, bool):
            continue
        if not isinstance(value, int) or value < 0:
            raise ValueError(
                f"M-33.6d primary metric is not a nonnegative integer: {name}"
            )


def _is_hash(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate primary receipt JSON key")
        result[key] = value
    return result
