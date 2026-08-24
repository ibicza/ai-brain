"""Strict construction and validation of the six Stage-1 families."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.models import PRIMITIVES, VARIABLES, SemanticFamily


def build_family_specification(
    family: SemanticFamily,
    *,
    sources: tuple[str, ...] = (),
    destination: str | None = None,
    preserve: tuple[str, ...] | None = None,
) -> ProgramSpecification:
    source_counts = {
        SemanticFamily.NOOP: 0,
        SemanticFamily.CLEAR: 1,
        SemanticFamily.DRAIN: 1,
        SemanticFamily.MERGE_TWO: 2,
        SemanticFamily.MERGE_THREE: 3,
        SemanticFamily.DROP_THEN_TRANSFER: 2,
    }
    if len(sources) != source_counts[family]:
        raise ValueError(f"{family} requires {source_counts[family]} source role(s)")
    if len(set(sources)) != len(sources) or any(
        value not in VARIABLES for value in sources
    ):
        raise ValueError("sources must be distinct A/B/C/D roles")
    needs_destination = family not in {SemanticFamily.NOOP, SemanticFamily.CLEAR}
    if needs_destination != (destination is not None):
        raise ValueError("destination requirement is not satisfied")
    if destination is not None and (
        destination not in VARIABLES or destination in sources
    ):
        raise ValueError("destination must be a different A/B/C/D role")
    phases: list[tuple[str, str, str | None]] = []
    if family == SemanticFamily.CLEAR:
        phases.append(("DROP_ONE", sources[0], None))
    elif family == SemanticFamily.DROP_THEN_TRANSFER:
        phases.extend(
            (("DROP_ONE", sources[0], None), ("MOVE_ONE", sources[1], destination))
        )
    elif destination is not None:
        phases.extend(("MOVE_ONE", source, destination) for source in sources)
    transfers = tuple(
        (source, str(target))
        for action, source, target in phases
        if action == "MOVE_ONE"
    )
    drops = tuple(source for action, source, _ in phases if action == "DROP_ONE")
    changed = set(sources) | ({destination} if destination else set())
    inferred = tuple(value for value in VARIABLES if value not in changed)
    preserved = tuple(sorted(inferred if preserve is None else set(preserve)))
    if family == SemanticFamily.NOOP:
        preserved = VARIABLES
    primitives = tuple(sorted({"HALT", *(action for action, _, _ in phases)}))
    return ProgramSpecification(
        inputs=sources,
        outputs=(destination,) if destination else (),
        transfers=transfers,
        drops=drops,
        preserve=preserved,
        terminate_when_empty=sources,
        allowed_variables=VARIABLES,
        allowed_primitives=primitives,
        phase_constraints=tuple(phases),
    )


def infer_family(specification: ProgramSpecification) -> SemanticFamily | None:
    if not specification.transfers and not specification.drops:
        return SemanticFamily.NOOP
    if len(specification.drops) == 1 and not specification.transfers:
        return SemanticFamily.CLEAR
    if not specification.drops and len(specification.transfers) in {1, 2, 3}:
        return {
            1: SemanticFamily.DRAIN,
            2: SemanticFamily.MERGE_TWO,
            3: SemanticFamily.MERGE_THREE,
        }[len(specification.transfers)]
    if len(specification.drops) == 1 and len(specification.transfers) == 1:
        return SemanticFamily.DROP_THEN_TRANSFER
    return None


def validate_specification(specification: ProgramSpecification) -> tuple[str, ...]:
    problems: list[str] = []
    roles = set(specification.roles()) | set(specification.allowed_variables)
    if roles - set(VARIABLES):
        problems.append("unknown_variable")
    if set(specification.allowed_primitives) - set(PRIMITIVES):
        problems.append("invalid_primitive")
    if any(source == destination for source, destination in specification.transfers):
        problems.append("source_equals_destination")
    changed = set(specification.drops) | {
        role for pair in specification.transfers for role in pair
    }
    if set(specification.preserve) & changed:
        problems.append("preserve_conflict")
    actual_phases = tuple(
        [("DROP_ONE", role, None) for role in specification.drops]
        + [
            ("MOVE_ONE", source, destination)
            for source, destination in specification.transfers
        ]
    )
    if actual_phases != specification.phase_constraints:
        problems.append("phase_mismatch")
    if set(specification.terminate_when_empty) != {
        action[1] for action in specification.phase_constraints
    }:
        problems.append("termination_mismatch")
    if not specification.is_full():
        problems.append("empty_specification")
    return tuple(problems)


def specification_from_dict(row: dict[str, Any]) -> ProgramSpecification:
    expected = {field.name for field in fields(ProgramSpecification)}
    if set(row) != expected:
        raise ValueError(
            f"ProgramSpecification schema mismatch: missing={sorted(expected - set(row))}, "
            f"extra={sorted(set(row) - expected)}"
        )
    if not isinstance(row["unsupported"], bool):
        raise TypeError("unsupported must be bool")
    return ProgramSpecification(**row)
