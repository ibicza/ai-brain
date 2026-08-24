"""Structural, semantic, property, and behavioral equivalence for language specs."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any

from ai_brain.language_to_spec.schema import canonicalize_specification
from ai_brain.rules.ast import ProgramAst, RegisterState, exact_closed_loop
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.verifier import property_states, property_verify


def structural_specification_equal(
    left: ProgramSpecification, right: ProgramSpecification
) -> bool:
    return canonicalize_specification(left) == canonicalize_specification(right)


def _merge_like(spec: ProgramSpecification) -> bool:
    return (
        not spec.drops
        and len(spec.transfers) >= 2
        and len({destination for _, destination in spec.transfers}) == 1
        and all(action == "MOVE_ONE" for action, _, _ in spec.phase_constraints)
    )


def semantic_specification_payload(spec: ProgramSpecification) -> dict[str, Any]:
    canonical = canonicalize_specification(spec)
    payload = asdict(canonical)
    for field in (
        "preserve",
        "terminate_when_empty",
        "allowed_variables",
        "allowed_primitives",
    ):
        payload[field] = sorted(payload[field])
    if _merge_like(canonical):
        payload["inputs"] = sorted(payload["inputs"])
        payload["transfers"] = sorted(payload["transfers"])
        payload["phase_constraints"] = sorted(
            payload["phase_constraints"], key=lambda row: (row[1], row[2] or "")
        )
    return payload


def semantic_specification_signature(spec: ProgramSpecification) -> str:
    return json.dumps(
        semantic_specification_payload(spec),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def semantic_specification_equal(
    left: ProgramSpecification, right: ProgramSpecification
) -> bool:
    return semantic_specification_signature(left) == semantic_specification_signature(
        right
    )


def property_equivalent(
    program: ProgramAst, specification: ProgramSpecification
) -> bool:
    return property_verify(program, specification, large=True).accepted


def behaviorally_equivalent(
    left: ProgramAst,
    right: ProgramAst,
    specification: ProgramSpecification,
) -> bool:
    for state in property_states(specification, large=True):
        try:
            left_result = exact_closed_loop(left, RegisterState(dict(state.counts)))
            right_result = exact_closed_loop(right, RegisterState(dict(state.counts)))
        except Exception:  # noqa: BLE001 - any runtime failure disproves equivalence.
            return False
        if left_result["final_state"] != right_result["final_state"]:
            return False
    return True


def reversed_merge_order(spec: ProgramSpecification) -> ProgramSpecification:
    """Test helper: reverse only semantically commutative merge source order."""
    if not _merge_like(spec):
        return spec
    return replace(
        spec,
        inputs=tuple(reversed(spec.inputs)),
        transfers=tuple(reversed(spec.transfers)),
        terminate_when_empty=tuple(reversed(spec.terminate_when_empty)),
        phase_constraints=tuple(reversed(spec.phase_constraints)),
    )
