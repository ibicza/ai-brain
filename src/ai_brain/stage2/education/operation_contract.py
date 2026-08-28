"""Canonical operation vocabulary for every educational graph-node kind."""

from __future__ import annotations

from ai_brain.stage2.education.models import GraphNodeKind

CANONICAL_OPERATIONS: dict[GraphNodeKind, frozenset[str | None]] = {
    GraphNodeKind.GIVEN_VALUE: frozenset({None}),
    GraphNodeKind.FACT_LOOKUP: frozenset({None}),
    GraphNodeKind.FORMULA_PARSE: frozenset({"PARSE"}),
    GraphNodeKind.FORMULA_COMPOSITION: frozenset({"COMPOSE"}),
    GraphNodeKind.STOICHIOMETRIC_COUNT: frozenset({None}),
    GraphNodeKind.UNIT_NORMALIZATION: frozenset({"MULTIPLY"}),
    GraphNodeKind.ATOMIC_WEIGHT_LOOKUP: frozenset({None}),
    GraphNodeKind.MULTIPLY: frozenset({"MULTIPLY"}),
    GraphNodeKind.ADD: frozenset({"ADD"}),
    GraphNodeKind.DIVIDE: frozenset({"DIVIDE"}),
    GraphNodeKind.MOLE_RELATION: frozenset({"MULTIPLY", "DIVIDE"}),
    GraphNodeKind.AVOGADRO_RELATION: frozenset({"MULTIPLY", "DIVIDE"}),
    GraphNodeKind.ROUND_DISPLAY: frozenset({"ROUND_DISPLAY"}),
    GraphNodeKind.FINAL_RESULT: frozenset({"IDENTITY"}),
    GraphNodeKind.SOURCE_REFERENCE: frozenset({None}),
    GraphNodeKind.WARNING: frozenset({None}),
}


def verify_canonical_operation(kind: GraphNodeKind, operation: str | None) -> None:
    try:
        allowed = CANONICAL_OPERATIONS[kind]
    except KeyError as error:
        raise ValueError("graph node kind lacks an operation contract") from error
    if operation not in allowed:
        expected = ", ".join(
            "None" if item is None else item for item in sorted(allowed, key=str)
        )
        raise ValueError(
            f"incompatible educational kind/operation: {kind.value} permits {expected}"
        )
