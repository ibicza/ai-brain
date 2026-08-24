"""Experimental abstract-template plus concrete-role binding acquisition."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ai_brain.language_to_spec.fair_model import infer_semantic_family
from ai_brain.rules.ast import ProgramAst, render_canonical_program
from ai_brain.rules.blackbox import (
    PublicAcquisitionResult,
    specification_signature,
    verification_to_json,
)
from ai_brain.rules.grammar import (
    generic_drop_all,
    generic_drop_then_transfer,
    generic_no_op,
    generic_three_phase,
    generic_transfer_one,
    generic_two_phase,
)
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import abstract_verify, property_verify, static_verify


@dataclass(frozen=True)
class TemplateBindingAudit:
    template_family: str | None
    template_found: bool
    binding_found: bool
    binding: tuple[tuple[str, str], ...]
    property_verified: bool
    candidate: ProgramAst | None
    acquisition: PublicAcquisitionResult


def instantiate_specification_template(
    specification: ProgramSpecification,
) -> tuple[str, tuple[tuple[str, str], ...], ProgramAst]:
    family = infer_semantic_family(specification)
    sources = tuple(specification.inputs)
    destination = specification.outputs[0] if specification.outputs else None
    logical_slots = ("SOURCE_1", "SOURCE_2", "SOURCE_3")
    binding = list(zip(logical_slots, sources, strict=False))
    if destination is not None:
        binding.append(("DESTINATION", destination))
    name = f"m231_bound_{family.lower()}"
    if family.value == "NOOP":
        program = generic_no_op(name=name)
    elif family.value == "CLEAR":
        program = generic_drop_all(sources[0], name=name)
    elif family.value == "DRAIN":
        program = generic_transfer_one(sources[0], destination, name=name)
    elif family.value == "MERGE_TWO":
        program = generic_two_phase(*sources, destination, name=name)
    elif family.value == "MERGE_THREE":
        program = generic_three_phase(*sources, destination, name=name)
    else:
        program = generic_drop_then_transfer(*sources, destination, name=name)
    return str(family), tuple(binding), program


def acquire_with_concrete_binding(
    specification: ProgramSpecification, *, task_id: str = "m231-binding"
) -> TemplateBindingAudit:
    started = time.perf_counter()
    try:
        family, binding, candidate = instantiate_specification_template(specification)
    except (KeyError, ValueError, IndexError) as exc:
        acquisition = PublicAcquisitionResult(
            task_id,
            str(VerificationStatus.UNSUPPORTED),
            None,
            None,
            wall_time_sec=time.perf_counter() - started,
            reason=f"template_or_binding_failed:{exc}",
        )
        return TemplateBindingAudit(None, False, False, (), False, None, acquisition)
    static = static_verify(candidate)
    abstract = abstract_verify(candidate)
    verified = property_verify(candidate, specification, large=True)
    accepted = static.accepted and abstract.accepted and verified.accepted
    evidence = verification_to_json(verified)
    evidence["specification_signature"] = specification_signature(specification)
    evidence["template_family"] = family
    evidence["binding"] = dict(binding)
    acquisition = PublicAcquisitionResult(
        task_id,
        str(
            VerificationStatus.PROPERTY_VERIFIED
            if accepted
            else VerificationStatus.SEARCH_BUDGET_EXHAUSTED
        ),
        render_canonical_program(candidate) if accepted else None,
        evidence if accepted else None,
        candidates_to_first_verified=1 if accepted else None,
        actual_property_checks=1,
        candidate_pool_size=1,
        wall_time_sec=time.perf_counter() - started,
        reason=(
            "public_specification_template_and_binding_verified"
            if accepted
            else "bound_candidate_failed_verification"
        ),
    )
    return TemplateBindingAudit(
        family,
        True,
        bool(binding) or family.endswith("NOOP"),
        binding,
        accepted,
        candidate if accepted else None,
        acquisition,
    )
