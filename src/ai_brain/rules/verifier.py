"""Static, abstract-state, and property verification for the rule DSL."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

from ai_brain.rules.ast import (
    REG_BINDING,
    REGISTERS,
    ActionAst,
    ClauseAst,
    ProgramAst,
    RegisterState,
    exact_closed_loop,
    program_variables,
    verify_m21_program,
)
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus


@dataclass(frozen=True)
class VerificationResult:
    accepted: bool
    status: VerificationStatus
    reason: str = "ok"
    counterexample: dict[str, int] | None = None


def static_verify(program: ProgramAst) -> VerificationResult:
    try:
        verify_m21_program(program)
    except Exception as exc:  # noqa: BLE001 - exact verifier reason is result data.
        return VerificationResult(False, VerificationStatus.REJECTED, str(exc))
    for clause in program.clauses:
        action = clause.action
        if action.kind == "MOVE_ONE" and action.source == action.destination:
            return VerificationResult(False, VerificationStatus.REJECTED, "move_self")
        if action.kind not in {"MOVE_ONE", "DROP_ONE", "HALT"}:
            return VerificationResult(False, VerificationStatus.REJECTED, "bad_action")
    return VerificationResult(True, VerificationStatus.PROPERTY_VERIFIED)


def abstract_patterns(
    variables: tuple[str, ...] = ("A", "B", "C", "D"),
) -> list[dict[str, bool]]:
    return [
        dict(zip(variables, bits, strict=True))
        for bits in itertools.product((False, True), repeat=len(variables))
    ]


def clause_matches_abstract(clause: ClauseAst, pattern: dict[str, bool]) -> bool:
    for predicate in clause.predicates:
        value = pattern[predicate.variable]
        if predicate.kind == "EMPTY" and value:
            return False
        if predicate.kind == "NONEMPTY" and not value:
            return False
    return True


def abstract_transition_graph(program: ProgramAst) -> dict[str, Any]:
    graph = {}
    for pattern in abstract_patterns():
        matches = [
            index
            for index, clause in enumerate(program.clauses)
            if clause_matches_abstract(clause, pattern)
        ]
        key = "".join("1" if pattern[var] else "0" for var in ("A", "B", "C", "D"))
        graph[key] = {"matches": matches, "action": None, "next": None}
        if len(matches) == 1:
            action = program.clauses[matches[0]].action
            graph[key]["action"] = action.kind
            graph[key]["next"] = abstract_next(pattern, action)
    return graph


def abstract_next(pattern: dict[str, bool], action: ActionAst) -> str:
    next_pattern = dict(pattern)
    if action.kind in {"MOVE_ONE", "DROP_ONE"} and action.source is not None:
        next_pattern[action.source] = False
    if action.kind == "MOVE_ONE" and action.destination is not None:
        next_pattern[action.destination] = True
    return "".join("1" if next_pattern[var] else "0" for var in ("A", "B", "C", "D"))


def abstract_verify(program: ProgramAst) -> VerificationResult:
    graph = abstract_transition_graph(program)
    for key, node in graph.items():
        if len(node["matches"]) != 1:
            return VerificationResult(
                False, VerificationStatus.REJECTED, f"abstract_match_count_{key}"
            )
    for key in graph:
        seen = set()
        current = key
        for _ in range(12):
            if graph[current]["action"] == "HALT":
                break
            if current in seen:
                return VerificationResult(
                    False, VerificationStatus.REJECTED, "control_cycle"
                )
            seen.add(current)
            current = graph[current]["next"]
        else:
            return VerificationResult(False, VerificationStatus.REJECTED, "no_halt")
    return VerificationResult(True, VerificationStatus.PROPERTY_VERIFIED)


def property_states(
    spec: ProgramSpecification, *, large: bool = False
) -> list[RegisterState]:
    roles = spec.roles() or ("A",)
    values = (0, 1, 2, 5, 13, 29, 71, 211, 1000) if large else (0, 1, 2, 5, 13)
    states = []
    for combo in itertools.product(values[:4], repeat=min(3, len(roles))):
        counts = {register: 0 for register in REGISTERS}
        for role, value in zip(roles, combo, strict=False):
            counts[REG_BINDING[role]] = value
        states.append(RegisterState(counts))
    for role in roles:
        counts = {register: 0 for register in REGISTERS}
        counts[REG_BINDING[role]] = 2
        states.append(RegisterState(counts))
    for value in values:
        counts = {register: 0 for register in REGISTERS}
        for role in roles:
            counts[REG_BINDING[role]] = value
        states.append(RegisterState(counts))
    non_role_registers = [
        register
        for register in REGISTERS
        if register not in {REG_BINDING[role] for role in roles}
    ]
    for register in non_role_registers:
        for value in values:
            counts = {reg: 0 for reg in REGISTERS}
            counts[register] = value
            for role in roles[:2]:
                counts[REG_BINDING[role]] = 2
            states.append(RegisterState(counts))
    return states


def check_postconditions(
    spec: ProgramSpecification, before: dict[str, int], after: dict[str, int]
) -> VerificationResult:
    if spec.unsupported:
        return VerificationResult(
            False, VerificationStatus.UNSUPPORTED, "unsupported_spec"
        )
    expected = dict(before)
    for role in spec.drops:
        expected[REG_BINDING[role]] = 0
    for source, destination in spec.transfers:
        source_reg = REG_BINDING[source]
        destination_reg = REG_BINDING[destination]
        expected[destination_reg] += before[source_reg]
        expected[source_reg] = 0
    for role in spec.preserve:
        reg = REG_BINDING[role]
        if after[reg] != before[reg]:
            return VerificationResult(
                False,
                VerificationStatus.REJECTED,
                f"preserve_violation_{role}",
                before,
            )
    for role in spec.terminate_when_empty:
        reg = REG_BINDING[role]
        if after[reg] != 0:
            return VerificationResult(
                False, VerificationStatus.REJECTED, f"not_empty_{role}", before
            )
    for register, value in expected.items():
        if after[register] != value:
            return VerificationResult(
                False, VerificationStatus.REJECTED, f"wrong_value_{register}", before
            )
    return VerificationResult(True, VerificationStatus.PROPERTY_VERIFIED)


def property_verify(
    program: ProgramAst, spec: ProgramSpecification, *, large: bool = False
) -> VerificationResult:
    static = static_verify(program)
    if not static.accepted:
        return static
    abstract = abstract_verify(program)
    if not abstract.accepted:
        return abstract
    if spec.allowed_variables:
        unexpected = program_variables(program) - set(spec.allowed_variables)
        if unexpected:
            return VerificationResult(
                False,
                VerificationStatus.REJECTED,
                f"disallowed_variables_{','.join(sorted(unexpected))}",
            )
    if spec.allowed_primitives:
        unexpected = {clause.action.kind for clause in program.clauses} - set(
            spec.allowed_primitives
        )
        if unexpected:
            return VerificationResult(
                False,
                VerificationStatus.REJECTED,
                f"disallowed_primitives_{','.join(sorted(unexpected))}",
            )
    if spec.phase_constraints:
        actual_phases = tuple(
            (
                clause.action.kind,
                clause.action.source or "",
                clause.action.destination,
            )
            for clause in program.clauses
            if clause.action.kind != "HALT"
        )
        if actual_phases != spec.phase_constraints:
            return VerificationResult(
                False, VerificationStatus.REJECTED, "phase_constraint_violation"
            )
    for state in property_states(spec, large=large):
        before = dict(state.counts)
        try:
            execution = exact_closed_loop(program, state)
        except Exception as exc:  # noqa: BLE001
            return VerificationResult(
                False, VerificationStatus.REJECTED, str(exc), before
            )
        if execution["invalid"]:
            return VerificationResult(
                False, VerificationStatus.REJECTED, "invalid_execution", before
            )
        if not execution["actions"] or execution["actions"][-1] not in {"H", "HALT"}:
            return VerificationResult(
                False, VerificationStatus.REJECTED, "no_halt", before
            )
        after = execution["final_state"]
        result = check_postconditions(spec, before, after)
        if not result.accepted:
            return result
    return VerificationResult(True, VerificationStatus.PROPERTY_VERIFIED)
