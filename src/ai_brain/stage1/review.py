"""Human-review representation for a parsed proposal and verified candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from ai_brain.stage1.approval import validate_candidate_binding
from ai_brain.stage1.models import (
    RuleProposal,
    VerifiedCandidateBundle,
    VerifiedReviewArtifact,
    proposal_hash,
    utc_now,
    verified_review_content_hash,
)
from ai_brain.stage1.version import STAGE1_VERSION


@dataclass(frozen=True)
class ReviewView:
    proposal_id: str
    status: str
    original_input: str
    language: str | None
    family: str | None
    specification: dict | None
    issues: tuple[dict, ...]
    generated_rule: str
    verification_status: str
    warnings_ru: tuple[str, ...]
    warnings_en: tuple[str, ...]


def build_review_view(
    proposal: RuleProposal, candidate: VerifiedCandidateBundle | None = None
) -> ReviewView:
    issues = tuple(asdict(item) for item in proposal.issues)
    return ReviewView(
        proposal_id=proposal.proposal_id,
        status=str(proposal.status),
        original_input=proposal.original_input,
        language=proposal.language,
        family=str(proposal.semantic_family) if proposal.semantic_family else None,
        specification=asdict(proposal.specification)
        if proposal.specification
        else None,
        issues=issues,
        generated_rule=candidate.candidate_dsl if candidate else "",
        verification_status=candidate.verification_status
        if candidate
        else "NOT_VERIFIED",
        warnings_ru=tuple(f"{item.code}: {item.message}" for item in proposal.issues),
        warnings_en=tuple(f"{item.code}: {item.message}" for item in proposal.issues),
    )


def build_verified_review(
    proposal: RuleProposal, candidate: VerifiedCandidateBundle
) -> VerifiedReviewArtifact:
    validate_candidate_binding(proposal, candidate)
    if proposal.specification is None:
        raise ValueError("Proposal has no specification")
    specification = proposal.specification
    changed = tuple(
        sorted(
            set(specification.drops)
            | {role for transfer in specification.transfers for role in transfer}
        )
    )
    phases = tuple(specification.phase_constraints)
    summary = (
        "; ".join(
            f"{action} {source}{' -> ' + destination if destination else ''}"
            for action, source, destination in phases
        )
        or "HALT without state change"
    )
    artifact = VerifiedReviewArtifact(
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal_hash(proposal),
        specification_hash=candidate.specification_hash,
        original_input=proposal.original_input,
        semantic_effect_summary=summary,
        changed_registers=changed,
        preserved_registers=tuple(specification.preserve),
        termination_condition=tuple(specification.terminate_when_empty),
        ordered_phases=phases,
        compiler_name=candidate.compiler_name,
        candidate_dsl=candidate.candidate_dsl,
        candidate_hash=candidate.candidate_hash,
        static_verification_result=dict(
            candidate.verification_evidence["static_verification"]
        ),
        abstract_verification_result=dict(
            candidate.verification_evidence["abstract_verification"]
        ),
        property_verification_result=dict(
            candidate.verification_evidence["property_verification"]
        ),
        verification_evidence=dict(candidate.verification_evidence),
        evidence_hash=candidate.evidence_hash,
        stage1_version=STAGE1_VERSION,
        warnings=(
            "Controlled six-family DSL only",
            "Property verification is scoped to Stage-1 specification semantics",
        ),
        created_at=utc_now(),
        review_hash="",
    )
    return replace(artifact, review_hash=verified_review_content_hash(artifact))
