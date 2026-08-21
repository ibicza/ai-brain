"""Evaluator-only hidden target generation for M-22.3.

This module is intentionally outside ``src/ai_brain/rules``. Acquisition code
must not import it; the M-22.3 runner uses it only to build hidden artifacts and
to score final candidates.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass
from typing import Any

from ai_brain.rules.ast import (
    ActionAst,
    ClauseAst,
    PredicateAst,
    ProgramAst,
    RegisterState,
    exact_closed_loop,
    render_canonical_program,
)
from ai_brain.rules.grammar import enumerate_generic_programs

REGISTERS = ("R0", "R1", "R2", "R3")


@dataclass(frozen=True)
class HiddenTarget:
    target_id: str
    split: str
    family: str
    program: ProgramAst
    grammar_version: str = "m223_generic_v1"

    def to_hidden_json(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "split": self.split,
            "family": self.family,
            "grammar_version": self.grammar_version,
            "program": render_canonical_program(self.program),
            "exact_ast_hash": self.program.semantic_hash(
                alpha=False, order_insensitive=False
            ),
            "normalized_ast_hash": self.program.semantic_hash(
                alpha=False, order_insensitive=True
            ),
            "alpha_ast_hash": self.program.semantic_hash(
                alpha=True, order_insensitive=True
            ),
            "clause_count": len(self.program.clauses),
            "predicate_counts": [
                len(clause.predicates) for clause in self.program.clauses
            ],
            "action_counts": action_counts(self.program),
            "variables": sorted(program_variables_loose(self.program)),
        }


def predicate(kind: str, variable: str) -> PredicateAst:
    return PredicateAst(kind, variable)


def clause(predicates: tuple[PredicateAst, ...], action: ActionAst) -> ClauseAst:
    return ClauseAst(predicates, action)


def no_op_program(name: str = "noop") -> ProgramAst:
    return ProgramAst((ClauseAst((), ActionAst("HALT")),), name)


def m223_candidate_pool(size: int) -> list[ProgramAst]:
    programs = [no_op_program("m223_noop")]
    seen = {programs[0].semantic_hash(alpha=True, order_insensitive=True)}
    for program in enumerate_generic_programs(size * 2):
        key = program.semantic_hash(alpha=True, order_insensitive=True)
        if key in seen:
            continue
        seen.add(key)
        programs.append(program)
        if len(programs) >= size:
            break
    if len(programs) < size:
        raise RuntimeError(f"Could not build {size} alpha-unique candidates")
    return programs


def validation_states() -> list[RegisterState]:
    states = []
    base_values = (0, 1, 2, 5)
    for value in base_values:
        states.append(RegisterState({register: value for register in REGISTERS}))
    for register in REGISTERS:
        for value in (0, 1, 2, 5, 13):
            counts = {name: 0 for name in REGISTERS}
            counts[register] = value
            states.append(RegisterState(counts))
    for combo in (
        (0, 1, 2, 5),
        (5, 2, 1, 0),
        (1, 0, 5, 2),
        (2, 5, 0, 1),
        (3, 1, 4, 0),
        (0, 4, 1, 3),
    ):
        states.append(RegisterState(dict(zip(REGISTERS, combo, strict=True))))
    return dedupe_states(states)


def query_bank_states() -> list[RegisterState]:
    states = validation_states()
    for combo in itertools.product((0, 1, 2, 5), repeat=4):
        if sum(combo) <= 10:
            states.append(RegisterState(dict(zip(REGISTERS, combo, strict=True))))
    return dedupe_states(states)


def boundary_states() -> list[RegisterState]:
    states = []
    for value in list(range(11)) + [11, 20, 21, 50, 51, 100, 211, 1000]:
        states.append(RegisterState({register: value for register in REGISTERS}))
        for register in REGISTERS:
            counts = {name: 0 for name in REGISTERS}
            counts[register] = value
            states.append(RegisterState(counts))
    return dedupe_states(states)


def random_states(seed: int, count: int, max_value: int = 100) -> list[RegisterState]:
    import random

    rng = random.Random(seed)
    return [
        RegisterState({register: rng.randint(0, max_value) for register in REGISTERS})
        for _ in range(count)
    ]


def dedupe_states(states: list[RegisterState]) -> list[RegisterState]:
    seen = set()
    unique = []
    for state in states:
        key = tuple(state.counts[register] for register in REGISTERS)
        if key in seen:
            continue
        seen.add(key)
        unique.append(state)
    return unique


def execute(program: ProgramAst, state: RegisterState) -> dict[str, Any]:
    try:
        result = exact_closed_loop(program, state)
    except Exception as exc:  # noqa: BLE001 - verifier records evaluator failures.
        return {
            "final_state": {"error": type(exc).__name__, "message": str(exc)},
            "invalid": True,
            "halted": False,
            "actions": [],
        }
    return {
        "final_state": result["final_state"],
        "invalid": bool(result["invalid"]),
        "halted": bool(result["actions"] and result["actions"][-1] in {"H", "HALT"}),
        "actions": result["actions"],
    }


def fingerprint(program: ProgramAst, states: list[RegisterState]) -> str:
    import json

    rows = [execute(program, state)["final_state"] for state in states]
    return json.dumps(rows, sort_keys=True)


def formal_examples(
    program: ProgramAst, states: list[RegisterState]
) -> list[dict[str, Any]]:
    rows = []
    for state in states:
        execution = execute(program, state)
        rows.append(
            {
                "before": dict(state.counts),
                "after": execution["final_state"],
                "invalid": execution["invalid"],
                "halted": execution["halted"],
            }
        )
    return rows


def target_records(
    split: str, programs: list[ProgramAst], *, offset: int = 0
) -> list[HiddenTarget]:
    records = []
    for index, program in enumerate(programs):
        records.append(
            HiddenTarget(
                target_id=f"{split}-{offset + index:05d}",
                split=split,
                family=family_name(program),
                program=program,
            )
        )
    return records


def action_counts(program: ProgramAst) -> dict[str, int]:
    counts = {"MOVE_ONE": 0, "DROP_ONE": 0, "HALT": 0}
    for item in program.clauses:
        counts[item.action.kind] = counts.get(item.action.kind, 0) + 1
    return counts


def program_variables_loose(program: ProgramAst) -> set[str]:
    variables = set()
    for item in program.clauses:
        for pred in item.predicates:
            variables.add(pred.variable)
        if item.action.source:
            variables.add(item.action.source)
        if item.action.destination:
            variables.add(item.action.destination)
    return variables


def family_name(program: ProgramAst) -> str:
    clause_count = len(program.clauses)
    actions = action_counts(program)
    if clause_count == 1:
        return "one_clause_noop"
    if actions["MOVE_ONE"] and actions["DROP_ONE"]:
        return f"{clause_count}_clause_transfer_drop"
    if actions["MOVE_ONE"]:
        return f"{clause_count}_clause_transfer"
    if actions["DROP_ONE"]:
        return f"{clause_count}_clause_drop"
    return f"{clause_count}_clause_other"


def public_summary(target: HiddenTarget) -> dict[str, Any]:
    hidden = target.to_hidden_json()
    return {
        key: value
        for key, value in hidden.items()
        if key
        not in {
            "program",
            "exact_ast_hash",
            "normalized_ast_hash",
            "alpha_ast_hash",
        }
    }


def as_jsonable_state(state: RegisterState) -> dict[str, int]:
    return dict(state.counts)


def hidden_rows(targets: list[HiddenTarget]) -> list[dict[str, Any]]:
    return [target.to_hidden_json() for target in targets]


def target_stats(targets: list[HiddenTarget]) -> dict[str, Any]:
    from collections import Counter

    clauses = Counter(len(target.program.clauses) for target in targets)
    predicates = Counter(
        len(item.predicates) for target in targets for item in target.program.clauses
    )
    actions = Counter(
        item.action.kind for target in targets for item in target.program.clauses
    )
    families = Counter(target.family for target in targets)
    variables = Counter(
        variable
        for target in targets
        for variable in program_variables_loose(target.program)
    )
    return {
        "clause_count_distribution": dict(sorted(clauses.items())),
        "predicate_count_distribution": dict(sorted(predicates.items())),
        "action_distribution": dict(sorted(actions.items())),
        "variable_role_distribution": dict(sorted(variables.items())),
        "specification_type_distribution": dict(sorted(families.items())),
    }


def dataclass_row(row: Any) -> dict[str, Any]:
    return asdict(row)
