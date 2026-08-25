"""Verified known-family compilation with frozen generic CEGIS fallback."""

from __future__ import annotations

from ai_brain.rules.ast import parse_canonical_dsl, render_canonical_program
from ai_brain.rules.blackbox import PublicAcquisitionTask, acquire_public_task
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import abstract_verify, property_verify, static_verify
from ai_brain.stage1.known_family_compiler import compile_known_family
from ai_brain.stage1.models import (
    RuleProposal,
    SemanticFamily,
    VerifiedCandidateBundle,
    content_hash,
    proposal_hash,
    specification_hash,
    utc_now,
)


def verify_proposal(
    proposal: RuleProposal, *, canonical_candidate: str | None = None
) -> VerifiedCandidateBundle:
    if proposal.specification is None:
        raise ValueError("A complete specification is required")
    specification = proposal.specification
    compiler_name = "stage1_known_family_compiler_v1"
    if canonical_candidate is not None:
        program, _ = parse_canonical_dsl(canonical_candidate)
        compiler_name = "trusted_canonical_dsl_v1"
    elif proposal.semantic_family is not None:
        program = compile_known_family(specification, proposal.semantic_family)
    else:
        program = _generic_cegis(specification)
        compiler_name = "frozen_public_generic_cegis"
    static = static_verify(program)
    abstract = abstract_verify(program)
    verification = property_verify(program, specification, large=True)
    if (
        not verification.accepted
        or verification.status != VerificationStatus.PROPERTY_VERIFIED
    ):
        raise ValueError(f"Candidate verification failed: {verification.reason}")
    candidate_dsl = render_canonical_program(program)
    evidence = {
        "accepted": True,
        "status": str(verification.status),
        "reason": verification.reason,
        "counterexample": verification.counterexample,
        "verifier": "property_verify_large_v1",
        "specification_hash": specification_hash(specification),
        "static_verification": _verification_row(static),
        "abstract_verification": _verification_row(abstract),
        "property_verification": _verification_row(verification),
    }
    return VerifiedCandidateBundle(
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal_hash(proposal),
        specification_hash=specification_hash(specification),
        candidate_dsl=candidate_dsl,
        candidate_hash=content_hash(candidate_dsl),
        verification_status=str(verification.status),
        verification_evidence=evidence,
        evidence_hash=content_hash(evidence),
        compiler_name=compiler_name,
        created_at=utc_now(),
    )


def _generic_cegis(specification: ProgramSpecification):
    result = acquire_public_task(
        PublicAcquisitionTask(
            task_id=f"stage1-{specification_hash(specification)[:16]}",
            mode="full_spec",
            specification=specification,
            candidate_budget=512,
        )
    )
    if (
        result.status != str(VerificationStatus.PROPERTY_VERIFIED)
        or not result.candidate_ast
    ):
        raise ValueError(
            f"Generic CEGIS failed safely: {result.status} ({result.reason})"
        )
    return parse_canonical_dsl(result.candidate_ast)[0]


def known_family_for(value: str | None) -> SemanticFamily | None:
    return SemanticFamily(value) if value else None


def _verification_row(result) -> dict:
    return {
        "accepted": result.accepted,
        "status": str(result.status),
        "reason": result.reason,
        "counterexample": result.counterexample,
    }
