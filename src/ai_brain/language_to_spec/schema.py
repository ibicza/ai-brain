"""Strict proposal schema and deterministic specification validation."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any

from ai_brain.rules.specifications import ProgramSpecification

VARIABLES = ("A", "B", "C", "D")
PRIMITIVES = ("DROP_ONE", "HALT", "MOVE_ONE")
SPECIFICATION_FIELDS = tuple(ProgramSpecification.__dataclass_fields__)


class ParseStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"
    CONTRADICTORY = "CONTRADICTORY"
    UNSUPPORTED = "UNSUPPORTED"


class SemanticFamily(StrEnum):
    NOOP = "NOOP"
    CLEAR = "CLEAR"
    DRAIN = "DRAIN"
    MERGE_TWO = "MERGE_TWO"
    MERGE_THREE = "MERGE_THREE"
    DROP_THEN_TRANSFER = "DROP_THEN_TRANSFER"


class ValidationCode(StrEnum):
    INVALID_SCHEMA = "INVALID_SCHEMA"
    MISSING_SPECIFICATION = "MISSING_SPECIFICATION"
    MISSING_DESTINATION = "MISSING_DESTINATION"
    AMBIGUOUS_PRONOUN = "AMBIGUOUS_PRONOUN"
    UNCLEAR_ORDER = "UNCLEAR_ORDER"
    MISSING_PRESERVE_BEHAVIOR = "MISSING_PRESERVE_BEHAVIOR"
    PRESERVE_TRANSFER_CONFLICT = "PRESERVE_TRANSFER_CONFLICT"
    DROP_TRANSFER_CONFLICT = "DROP_TRANSFER_CONFLICT"
    IMPOSSIBLE_TERMINATION = "IMPOSSIBLE_TERMINATION"
    MISSING_TERMINATION_CONDITION = "MISSING_TERMINATION_CONDITION"
    UNKNOWN_VARIABLE = "UNKNOWN_VARIABLE"
    SOURCE_EQUALS_DESTINATION = "SOURCE_EQUALS_DESTINATION"
    INVALID_TRANSFER = "INVALID_TRANSFER"
    INVALID_PHASE = "INVALID_PHASE"
    INVALID_PRIMITIVE = "INVALID_PRIMITIVE"
    FIELD_MISMATCH = "FIELD_MISMATCH"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


@dataclass(frozen=True)
class ValidationIssue:
    code: ValidationCode
    field: str
    message: str


@dataclass(frozen=True)
class LanguageProposal:
    status: ParseStatus
    language: str
    original_text: str
    specification: ProgramSpecification | None = None
    semantic_family: SemanticFamily | None = None
    issues: tuple[ValidationIssue, ...] = ()
    confidence: float = 0.0
    parser_name: str = ""
    provenance: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.language not in {"ru", "en"}:
            raise ValueError("language must be 'ru' or 'en'")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "provenance", tuple(self.provenance))


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def build_family_specification(
    family: SemanticFamily,
    *,
    sources: tuple[str, ...] = (),
    destination: str | None = None,
    preserve: tuple[str, ...] | None = None,
) -> ProgramSpecification:
    """Build one of the six frozen Stage-1 semantic families."""
    expected_sources = {
        SemanticFamily.NOOP: 0,
        SemanticFamily.CLEAR: 1,
        SemanticFamily.DRAIN: 1,
        SemanticFamily.MERGE_TWO: 2,
        SemanticFamily.MERGE_THREE: 3,
        SemanticFamily.DROP_THEN_TRANSFER: 2,
    }[family]
    if len(sources) != expected_sources:
        raise ValueError(f"{family} requires {expected_sources} source role(s)")
    if len(set(sources)) != len(sources) or any(v not in VARIABLES for v in sources):
        raise ValueError("sources must be distinct controlled variables")
    needs_destination = family in {
        SemanticFamily.DRAIN,
        SemanticFamily.MERGE_TWO,
        SemanticFamily.MERGE_THREE,
        SemanticFamily.DROP_THEN_TRANSFER,
    }
    if needs_destination != (destination is not None):
        raise ValueError(f"{family} destination requirement is not satisfied")
    if destination is not None:
        if destination not in VARIABLES:
            raise ValueError("destination must be a controlled variable")
        if destination in sources:
            raise ValueError("destination must differ from sources")

    phases: list[tuple[str, str, str | None]] = []
    if family == SemanticFamily.CLEAR:
        phases.append(("DROP_ONE", sources[0], None))
    elif family == SemanticFamily.DROP_THEN_TRANSFER:
        phases.extend(
            (
                ("DROP_ONE", sources[0], None),
                ("MOVE_ONE", sources[1], destination),
            )
        )
    elif needs_destination:
        phases.extend(("MOVE_ONE", source, destination) for source in sources)

    transfers = tuple(
        (source, str(target))
        for action, source, target in phases
        if action == "MOVE_ONE"
    )
    drops = tuple(source for action, source, _ in phases if action == "DROP_ONE")
    outputs = _ordered_unique(target for _, target in transfers)
    changed = set(sources) | set(outputs)
    inferred_preserve = tuple(
        variable for variable in VARIABLES if variable not in changed
    )
    preserve_roles = (
        inferred_preserve if preserve is None else _ordered_unique(preserve)
    )
    primitives = {"HALT", *(action for action, _, _ in phases)}
    if family == SemanticFamily.NOOP:
        preserve_roles = VARIABLES

    return ProgramSpecification(
        inputs=_ordered_unique(sources),
        outputs=outputs,
        transfers=transfers,
        drops=drops,
        preserve=tuple(sorted(preserve_roles)),
        terminate_when_empty=_ordered_unique(sources),
        phase_constraints=tuple(phases),
        allowed_variables=VARIABLES,
        allowed_primitives=tuple(sorted(primitives)),
        unsupported=False,
    )


def canonicalize_specification(spec: ProgramSpecification) -> ProgramSpecification:
    return replace(
        spec,
        inputs=_ordered_unique(spec.inputs),
        outputs=_ordered_unique(spec.outputs),
        transfers=tuple(spec.transfers),
        drops=_ordered_unique(spec.drops),
        preserve=tuple(sorted(set(spec.preserve))),
        terminate_when_empty=_ordered_unique(spec.terminate_when_empty),
        phase_constraints=tuple(spec.phase_constraints),
        allowed_variables=tuple(sorted(set(spec.allowed_variables))),
        allowed_primitives=tuple(sorted(set(spec.allowed_primitives))),
    )


def canonical_specification_json(spec: ProgramSpecification) -> str:
    return json.dumps(
        asdict(canonicalize_specification(spec)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def strict_specification_from_json(row: dict[str, Any]) -> ProgramSpecification:
    if set(row) != set(SPECIFICATION_FIELDS):
        missing = sorted(set(SPECIFICATION_FIELDS) - set(row))
        extra = sorted(set(row) - set(SPECIFICATION_FIELDS))
        raise ValueError(
            f"ProgramSpecification schema mismatch: missing={missing}, extra={extra}"
        )
    if not isinstance(row["unsupported"], bool):
        raise TypeError("unsupported must be bool")
    list_fields = {
        "inputs",
        "outputs",
        "drops",
        "preserve",
        "terminate_when_empty",
        "allowed_variables",
        "allowed_primitives",
    }
    if any(not isinstance(row[field], list) for field in list_fields):
        raise TypeError("ProgramSpecification role fields must be arrays")
    if not isinstance(row["transfers"], list) or not isinstance(
        row["phase_constraints"], list
    ):
        raise TypeError("transfers and phase_constraints must be arrays")
    return ProgramSpecification(**row)


def validate_specification(spec: ProgramSpecification) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    roles = set(spec.roles()) | set(spec.allowed_variables)
    unknown = sorted(roles - set(VARIABLES))
    if unknown:
        issues.append(
            ValidationIssue(
                ValidationCode.UNKNOWN_VARIABLE,
                "allowed_variables",
                f"Unknown controlled variables: {', '.join(unknown)}",
            )
        )
    for source, destination in spec.transfers:
        if source == destination:
            issues.append(
                ValidationIssue(
                    ValidationCode.SOURCE_EQUALS_DESTINATION,
                    "transfers",
                    f"Transfer {source}->{destination} has identical roles",
                )
            )
    changed = set(spec.drops) | {
        role for transfer in spec.transfers for role in transfer
    }
    preserve_conflicts = sorted(set(spec.preserve) & changed)
    if preserve_conflicts:
        issues.append(
            ValidationIssue(
                ValidationCode.PRESERVE_TRANSFER_CONFLICT,
                "preserve",
                f"Preserved roles are modified: {', '.join(preserve_conflicts)}",
            )
        )
    drop_transfer_conflicts = sorted(
        set(spec.drops) & {source for source, _ in spec.transfers}
    )
    if drop_transfer_conflicts:
        issues.append(
            ValidationIssue(
                ValidationCode.DROP_TRANSFER_CONFLICT,
                "drops",
                f"Roles are both dropped and transferred: {', '.join(drop_transfer_conflicts)}",
            )
        )
    action_phases = tuple(
        [("DROP_ONE", source, None) for source in spec.drops]
        + [("MOVE_ONE", source, destination) for source, destination in spec.transfers]
    )
    if Counter(action_phases) != Counter(spec.phase_constraints):
        issues.append(
            ValidationIssue(
                ValidationCode.INVALID_PHASE,
                "phase_constraints",
                "Phase actions do not match drop/transfer fields",
            )
        )
    phase_primitives = {action for action, _, _ in spec.phase_constraints} | {"HALT"}
    if not phase_primitives.issubset(set(spec.allowed_primitives)) or not set(
        spec.allowed_primitives
    ).issubset(PRIMITIVES):
        issues.append(
            ValidationIssue(
                ValidationCode.INVALID_PRIMITIVE,
                "allowed_primitives",
                "Allowed primitives do not match controlled phase actions",
            )
        )
    emptied = set(spec.drops) | {source for source, _ in spec.transfers}
    if emptied and not set(spec.terminate_when_empty).issuperset(emptied):
        issues.append(
            ValidationIssue(
                ValidationCode.MISSING_TERMINATION_CONDITION,
                "terminate_when_empty",
                "Every consumed source must be part of the termination condition",
            )
        )
    if set(spec.terminate_when_empty) - emptied:
        issues.append(
            ValidationIssue(
                ValidationCode.IMPOSSIBLE_TERMINATION,
                "terminate_when_empty",
                "Termination references a role that the program does not empty",
            )
        )
    phase_sources = _ordered_unique(source for _, source, _ in spec.phase_constraints)
    phase_outputs = _ordered_unique(
        str(destination)
        for action, _, destination in spec.phase_constraints
        if action == "MOVE_ONE"
    )
    if spec.inputs != phase_sources or spec.outputs != phase_outputs:
        issues.append(
            ValidationIssue(
                ValidationCode.FIELD_MISMATCH,
                "inputs",
                "Input/output masks do not match ordered phases",
            )
        )
    if not set(spec.roles()).issubset(set(spec.allowed_variables)):
        issues.append(
            ValidationIssue(
                ValidationCode.UNKNOWN_VARIABLE,
                "allowed_variables",
                "All referenced roles must be allowed",
            )
        )
    return tuple(issues)


def validate_proposal(proposal: LanguageProposal) -> tuple[ValidationIssue, ...]:
    issues = list(proposal.issues)
    if proposal.status == ParseStatus.SUPPORTED:
        if proposal.specification is None:
            issues.append(
                ValidationIssue(
                    ValidationCode.MISSING_SPECIFICATION,
                    "specification",
                    "A supported proposal requires a specification",
                )
            )
        else:
            issues.extend(validate_specification(proposal.specification))
            if proposal.specification.unsupported:
                issues.append(
                    ValidationIssue(
                        ValidationCode.UNSUPPORTED_OPERATION,
                        "unsupported",
                        "A supported proposal may not set unsupported",
                    )
                )
    elif (
        proposal.specification is not None
        and proposal.specification.unsupported
        and proposal.status != ParseStatus.UNSUPPORTED
    ):
        issues.append(
            ValidationIssue(
                ValidationCode.FIELD_MISMATCH,
                "status",
                "unsupported specification requires UNSUPPORTED status",
            )
        )
    return tuple(dict.fromkeys(issues))


def proposal_to_json(proposal: LanguageProposal) -> dict[str, Any]:
    return {
        "status": str(proposal.status),
        "language": proposal.language,
        "original_text": proposal.original_text,
        "specification": (
            json.loads(canonical_specification_json(proposal.specification))
            if proposal.specification is not None
            else None
        ),
        "semantic_family": (
            str(proposal.semantic_family)
            if proposal.semantic_family is not None
            else None
        ),
        "issues": [
            {"code": str(issue.code), "field": issue.field, "message": issue.message}
            for issue in proposal.issues
        ],
        "confidence": proposal.confidence,
        "parser_name": proposal.parser_name,
        "provenance": [list(item) for item in proposal.provenance],
    }


def proposal_from_json(row: dict[str, Any]) -> LanguageProposal:
    expected = {
        "status",
        "language",
        "original_text",
        "specification",
        "semantic_family",
        "issues",
        "confidence",
        "parser_name",
        "provenance",
    }
    if set(row) != expected:
        raise ValueError("LanguageProposal schema mismatch")
    specification = row["specification"]
    return LanguageProposal(
        status=ParseStatus(row["status"]),
        language=str(row["language"]),
        original_text=str(row["original_text"]),
        specification=(
            strict_specification_from_json(specification)
            if specification is not None
            else None
        ),
        semantic_family=(
            SemanticFamily(row["semantic_family"])
            if row["semantic_family"] is not None
            else None
        ),
        issues=tuple(
            ValidationIssue(
                ValidationCode(item["code"]), item["field"], item["message"]
            )
            for item in row["issues"]
        ),
        confidence=float(row["confidence"]),
        parser_name=str(row["parser_name"]),
        provenance=tuple(tuple(item) for item in row["provenance"]),
    )
