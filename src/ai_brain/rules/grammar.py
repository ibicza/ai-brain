"""Target-independent AST grammar and candidate enumeration."""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from ai_brain.rules.ast import (
    LOGICAL_VARS,
    ActionAst,
    ClauseAst,
    PredicateAst,
    ProgramAst,
    make_program,
)


@dataclass(frozen=True)
class CandidateSpaceSummary:
    requested_budget: int
    raw_generated: int
    typed_valid: int
    deterministic_checked: int
    exact_ast_unique: int
    alpha_normalized_unique: int


def pred(kind: str, variable: str) -> PredicateAst:
    return PredicateAst(kind, variable)


def clause(predicates: Sequence[PredicateAst], action: ActionAst) -> ClauseAst:
    return ClauseAst(tuple(predicates), action)


def generic_transfer_one(source: str, destination: str, *, name: str) -> ProgramAst:
    return make_program(
        [
            clause(
                (pred("NONEMPTY", source),), ActionAst("MOVE_ONE", source, destination)
            ),
            clause((pred("EMPTY", source),), ActionAst("HALT")),
        ],
        name,
    )


def generic_drop_all(source: str, *, name: str) -> ProgramAst:
    return make_program(
        [
            clause((pred("NONEMPTY", source),), ActionAst("DROP_ONE", source)),
            clause((pred("EMPTY", source),), ActionAst("HALT")),
        ],
        name,
    )


def generic_two_phase(a: str, b: str, destination: str, *, name: str) -> ProgramAst:
    return make_program(
        [
            clause((pred("NONEMPTY", a),), ActionAst("MOVE_ONE", a, destination)),
            clause(
                (pred("EMPTY", a), pred("NONEMPTY", b)),
                ActionAst("MOVE_ONE", b, destination),
            ),
            clause((pred("EMPTY", a), pred("EMPTY", b)), ActionAst("HALT")),
        ],
        name,
    )


def generic_three_phase(
    a: str, b: str, c: str, destination: str, *, name: str
) -> ProgramAst:
    return make_program(
        [
            clause((pred("NONEMPTY", a),), ActionAst("MOVE_ONE", a, destination)),
            clause(
                (pred("EMPTY", a), pred("NONEMPTY", b)),
                ActionAst("MOVE_ONE", b, destination),
            ),
            clause(
                (pred("EMPTY", a), pred("EMPTY", b), pred("NONEMPTY", c)),
                ActionAst("MOVE_ONE", c, destination),
            ),
            clause(
                (pred("EMPTY", a), pred("EMPTY", b), pred("EMPTY", c)),
                ActionAst("HALT"),
            ),
        ],
        name,
    )


def generic_drop_then_transfer(
    a: str, b: str, destination: str, *, name: str
) -> ProgramAst:
    return make_program(
        [
            clause((pred("NONEMPTY", a),), ActionAst("DROP_ONE", a)),
            clause(
                (pred("EMPTY", a), pred("NONEMPTY", b)),
                ActionAst("MOVE_ONE", b, destination),
            ),
            clause((pred("EMPTY", a), pred("EMPTY", b)), ActionAst("HALT")),
        ],
        name,
    )


def decision_table_program(
    salt: int, variables: tuple[str, ...] = LOGICAL_VARS[:3]
) -> ProgramAst:
    clauses = []
    for pattern_index, pattern in enumerate(
        itertools.product((0, 1), repeat=len(variables))
    ):
        predicates = tuple(
            pred("NONEMPTY" if bit else "EMPTY", variable)
            for bit, variable in zip(pattern, variables, strict=True)
        )
        nonempty = [
            variable for bit, variable in zip(pattern, variables, strict=True) if bit
        ]
        if not nonempty:
            action = ActionAst("HALT")
        else:
            choices: list[ActionAst] = []
            for source in nonempty:
                choices.append(ActionAst("DROP_ONE", source))
                choices.extend(
                    ActionAst("MOVE_ONE", source, destination)
                    for destination in LOGICAL_VARS
                    if destination != source
                )
            choice_index = salt % len(choices)
            salt //= len(choices)
            action = choices[choice_index]
        clauses.append(clause(predicates, action))
    return make_program(clauses, f"decision_table_{salt}")


def enumerate_generic_programs(limit: int) -> Iterator[ProgramAst]:
    emitted = 0
    seen_alpha: set[str] = set()

    def accept(program: ProgramAst) -> bool:
        key = program.semantic_hash(alpha=True, order_insensitive=True)
        if key in seen_alpha:
            return False
        seen_alpha.add(key)
        return True

    for source in LOGICAL_VARS:
        program = generic_drop_all(source, name=f"generic_drop_{emitted}")
        if accept(program):
            yield program
            emitted += 1
            if emitted >= limit:
                return
        for destination in LOGICAL_VARS:
            if source == destination:
                continue
            program = generic_transfer_one(
                source, destination, name=f"generic_transfer_{emitted}"
            )
            if accept(program):
                yield program
                emitted += 1
                if emitted >= limit:
                    return
    for a, b, destination in itertools.permutations(LOGICAL_VARS, 3):
        program = generic_two_phase(
            a, b, destination, name=f"generic_two_phase_{emitted}"
        )
        if accept(program):
            yield program
            emitted += 1
            if emitted >= limit:
                return
        program = generic_drop_then_transfer(
            a, b, destination, name=f"generic_drop_transfer_{emitted}"
        )
        if accept(program):
            yield program
            emitted += 1
            if emitted >= limit:
                return
    for a, b, c, destination in itertools.permutations(LOGICAL_VARS, 4):
        program = generic_three_phase(
            a, b, c, destination, name=f"generic_three_phase_{emitted}"
        )
        if accept(program):
            yield program
            emitted += 1
            if emitted >= limit:
                return
    salt = 0
    while emitted < limit:
        program = decision_table_program(salt)
        salt += 1
        if not accept(program):
            continue
        yield program
        emitted += 1


def unique_programs(limit: int, *, dedupe_alpha: bool = True) -> list[ProgramAst]:
    seen = set()
    programs = []
    for program in enumerate_generic_programs(limit * 4 + 32):
        key = program.semantic_hash(alpha=dedupe_alpha, order_insensitive=True)
        if key in seen:
            continue
        seen.add(key)
        programs.append(program)
        if len(programs) >= limit:
            break
    return programs


def summarize_candidate_space(requested_budget: int) -> CandidateSpaceSummary:
    raw = list(enumerate_generic_programs(requested_budget))
    exact = {
        program.semantic_hash(alpha=False, order_insensitive=False) for program in raw
    }
    alpha = {
        program.semantic_hash(alpha=True, order_insensitive=True) for program in raw
    }
    return CandidateSpaceSummary(
        requested_budget=requested_budget,
        raw_generated=len(raw),
        typed_valid=len(raw),
        deterministic_checked=len(raw),
        exact_ast_unique=len(exact),
        alpha_normalized_unique=len(alpha),
    )
