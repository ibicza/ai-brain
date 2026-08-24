"""Deterministic compiler for the six frozen structural rule families."""

from __future__ import annotations

from ai_brain.rules.ast import ProgramAst
from ai_brain.rules.grammar import (
    generic_drop_all,
    generic_drop_then_transfer,
    generic_no_op,
    generic_three_phase,
    generic_transfer_one,
    generic_two_phase,
)
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.models import SemanticFamily
from ai_brain.stage1.specifications import infer_family, validate_specification


def compile_known_family(
    specification: ProgramSpecification, family: SemanticFamily | None = None
) -> ProgramAst:
    problems = validate_specification(specification)
    if problems:
        raise ValueError(f"Invalid specification: {', '.join(problems)}")
    actual = family or infer_family(specification)
    if actual is None:
        raise ValueError("Specification is outside known families")
    name = f"stage1_{actual.value.lower()}"
    if actual == SemanticFamily.NOOP:
        return generic_no_op(name=name)
    if actual == SemanticFamily.CLEAR:
        return generic_drop_all(specification.drops[0], name=name)
    phases = specification.phase_constraints
    if actual == SemanticFamily.DRAIN:
        return generic_transfer_one(phases[0][1], str(phases[0][2]), name=name)
    if actual == SemanticFamily.MERGE_TWO:
        return generic_two_phase(
            phases[0][1], phases[1][1], str(phases[0][2]), name=name
        )
    if actual == SemanticFamily.MERGE_THREE:
        return generic_three_phase(
            phases[0][1], phases[1][1], phases[2][1], str(phases[0][2]), name=name
        )
    if actual == SemanticFamily.DROP_THEN_TRANSFER:
        return generic_drop_then_transfer(
            phases[0][1], phases[1][1], str(phases[1][2]), name=name
        )
    raise ValueError(f"Unsupported family {actual}")
