"""Human-review representation for a parsed proposal and verified candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ai_brain.stage1.models import RuleProposal, VerifiedCandidateBundle


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
