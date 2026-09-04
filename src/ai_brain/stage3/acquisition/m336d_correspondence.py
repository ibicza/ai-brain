"""SCM correspondence decisions independent from analysis and license status."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    SourceCorrespondenceStatus,
    SourceTreeCorrespondence,
    verify_source_tree_correspondence,
)

_COMPLETE = frozenset(
    {
        SourceCorrespondenceStatus.RAW_EXACT_MATCH,
        SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_CANONICAL_MATCH,
        SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE,
    }
)


@dataclass(frozen=True)
class ScmEntryCorrespondenceDecision:
    artifact_path: str
    scm_path: str | None
    correspondence_class: SourceCorrespondenceStatus
    selected: bool
    complete: bool
    reason: str
    decision_hash: str


@dataclass(frozen=True)
class ScmCorrespondenceDecision:
    entries: tuple[ScmEntryCorrespondenceDecision, ...]
    total_candidate_java_entries: int
    raw_exact_entries: int
    canonical_only_entries: int
    relocated_entries: int
    generated_entries: int
    unmatched_entries: int
    ambiguous_entries: int
    selected_entries: int
    selected_entries_with_complete_scm_correspondence: int
    complete_for_selected: bool
    correspondence_hash: str


def derive_scm_correspondence_decision(
    correspondence: SourceTreeCorrespondence,
    *,
    selected_paths: tuple[str, ...],
) -> ScmCorrespondenceDecision:
    verify_source_tree_correspondence(correspondence)
    selected = tuple(selected_paths)
    if selected != tuple(sorted(set(selected))):
        raise ValueError("selected correspondence paths must be sorted and unique")
    known = {item.artifact_path for item in correspondence.entries}
    missing = set(selected) - known
    if missing:
        raise ValueError(f"selected correspondence path is absent: {min(missing)}")
    selected_set = set(selected)
    rows = []
    for item in sorted(correspondence.entries, key=lambda value: value.artifact_path):
        complete = item.status in _COMPLETE
        is_selected = item.artifact_path in selected_set
        body = {
            "artifact_path": item.artifact_path,
            "scm_path": item.repository_path,
            "correspondence_class": item.status,
            "selected": is_selected,
            "complete": complete,
            "reason": (
                "MECHANICALLY_VERIFIED_CORRESPONDENCE"
                if complete
                else f"INCOMPLETE_{item.status.value}"
            ),
        }
        rows.append(
            ScmEntryCorrespondenceDecision(**body, decision_hash=content_hash(body))
        )
    entries = tuple(rows)
    counts = {
        status: sum(item.correspondence_class is status for item in entries)
        for status in SourceCorrespondenceStatus
    }
    selected_complete = sum(item.selected and item.complete for item in entries)
    summary = {
        "entries": entries,
        "total_candidate_java_entries": len(entries),
        "raw_exact_entries": counts[SourceCorrespondenceStatus.RAW_EXACT_MATCH],
        "canonical_only_entries": counts[
            SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH
        ],
        "relocated_entries": counts[SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH]
        + counts[SourceCorrespondenceStatus.PATH_RELOCATED_CANONICAL_MATCH],
        "generated_entries": counts[
            SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE
        ],
        "unmatched_entries": counts[SourceCorrespondenceStatus.UNMATCHED],
        "ambiguous_entries": counts[SourceCorrespondenceStatus.AMBIGUOUS_MATCH],
        "selected_entries": len(selected),
        "selected_entries_with_complete_scm_correspondence": selected_complete,
        "complete_for_selected": selected_complete == len(selected) and bool(selected),
    }
    return ScmCorrespondenceDecision(
        **summary, correspondence_hash=content_hash(summary)
    )


def require_verified_external_chain_correspondence(
    decision: ScmCorrespondenceDecision,
) -> None:
    if not isinstance(decision, ScmCorrespondenceDecision):
        raise TypeError("SCM correspondence decision must be typed")
    if not decision.complete_for_selected:
        raise ValueError(
            "VERIFIED_EXTERNAL_CHAIN requires complete selected SCM correspondence"
        )
    if (
        decision.selected_entries
        != decision.selected_entries_with_complete_scm_correspondence
    ):
        raise ValueError("selected SCM correspondence denominator mismatch")
