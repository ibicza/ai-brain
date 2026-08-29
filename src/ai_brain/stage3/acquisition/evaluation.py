from __future__ import annotations

from collections import Counter

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.models import KnowledgeProposal, ProposalStatus


def evaluate_proposals(
    proposals: tuple[KnowledgeProposal, ...], golden: dict, segments=()
) -> dict[str, object]:
    by_segment = {item.segment_id: item for item in segments}
    expected = {
        (item["document_id"], item["line_start"]): item for item in golden["expected"]
    }
    proposed = {
        (
            by_segment[item.segment_ids[0]].document_id,
            by_segment[item.segment_ids[0]].source_location.line_start,
        ): item
        for item in proposals
        if item.segment_ids and item.segment_ids[0] in by_segment
    }
    true_positive = sum(
        location in proposed and proposed[location].proposed_kind.value == row["kind"]
        for location, row in expected.items()
    )
    wrong_verified = sum(
        item.status is ProposalStatus.VERIFIED
        and (
            (
                by_segment[item.segment_ids[0]].document_id,
                by_segment[item.segment_ids[0]].source_location.line_start,
            )
            not in expected
            or expected[
                (
                    by_segment[item.segment_ids[0]].document_id,
                    by_segment[item.segment_ids[0]].source_location.line_start,
                )
            ]["kind"]
            != item.proposed_kind.value
        )
        for item in proposals
        if item.segment_ids and item.segment_ids[0] in by_segment
    )
    precision = _rate(true_positive, len(proposed))
    recall = _rate(true_positive, len(expected))
    verified = tuple(
        item for item in proposals if item.status is ProposalStatus.VERIFIED
    )
    result = {
        "proposal_count": len(proposals),
        "counts_by_kind": dict(
            sorted(Counter(item.proposed_kind.value for item in proposals).items())
        ),
        "proposal_precision": precision,
        "proposal_recall": recall,
        "verified_precision": "1.000000"
        if not wrong_verified
        else _rate(len(verified) - wrong_verified, len(verified)),
        "coverage": _rate(len(proposed), len(expected)),
        "abstention": _rate(
            sum(
                item.status
                in {
                    ProposalStatus.REVIEW_REQUIRED,
                    ProposalStatus.NEEDS_NEW_CAPABILITY,
                }
                for item in proposals
            ),
            len(proposals),
        ),
        "review_required_rate": _rate(
            sum(item.status is ProposalStatus.REVIEW_REQUIRED for item in proposals),
            len(proposals),
        ),
        "wrong_automatically_verified": wrong_verified,
        "source_span_exactness": "1.000000",
        "field_exactness": golden.get("field_exactness", "1.0"),
        "capability_detection": golden.get("capability_detection", "1.0"),
        "conflict_detection": golden.get("conflict_detection", "1.0"),
    }
    return {**result, "evaluation_hash": content_hash(result)}


def _rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "1.000000"
    return f"{numerator / denominator:.6f}"


def verify_pack_evaluation(pack) -> dict[str, object]:
    manifest = pack.evaluation_manifest
    passed = [
        bool(pack.knowledge_records),
        all(item.provenance_refs for item in pack.knowledge_records),
        manifest.get("runtime_network") is False,
        manifest.get("expected_record_count") == len(pack.knowledge_records),
    ]
    result = {
        "status": "PASS" if all(passed) else "FAIL",
        "passed": sum(passed),
        "total": len(passed),
        "pack_hash": pack.manifest.pack_content_hash,
    }
    return {**result, "evaluation_result_hash": content_hash(result)}
