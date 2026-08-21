"""Verified subprogram library and generic call-plan search."""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from ai_brain.rules.ast import (
    LOGICAL_VARS,
    ProgramAst,
    RegisterState,
    exact_closed_loop,
)
from ai_brain.rules.grammar import generic_drop_all, generic_transfer_one
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.verifier import check_postconditions, property_states


@dataclass(frozen=True)
class MacroCall:
    name: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class MacroPlan:
    calls: tuple[MacroCall, ...]


def subprogram_library() -> dict[str, ProgramAst]:
    return {
        "DRAIN": generic_transfer_one("A", "B", name="subprogram_drain"),
        "CLEAR": generic_drop_all("A", name="subprogram_clear"),
    }


def instantiate_call(call: MacroCall) -> ProgramAst:
    if call.name == "DRAIN":
        return generic_transfer_one(call.args[0], call.args[1], name="call_drain")
    if call.name == "CLEAR":
        return generic_drop_all(call.args[0], name="call_clear")
    raise ValueError(f"Unknown subprogram {call.name}")


def execute_plan(plan: MacroPlan, state: RegisterState) -> dict[str, int]:
    current = dict(state.counts)
    for call in plan.calls:
        program = instantiate_call(call)
        current = exact_closed_loop(program, RegisterState(dict(current)))[
            "final_state"
        ]
    return current


def possible_calls() -> list[MacroCall]:
    calls = [MacroCall("CLEAR", (source,)) for source in LOGICAL_VARS]
    calls.extend(
        MacroCall("DRAIN", (source, destination))
        for source, destination in itertools.permutations(LOGICAL_VARS, 2)
    )
    return calls


def search_macro_plan(
    spec: ProgramSpecification, *, max_depth: int = 4
) -> tuple[MacroPlan | None, int]:
    evaluated = 0
    calls = possible_calls()
    for depth in range(1, max_depth + 1):
        for combo in itertools.product(calls, repeat=depth):
            plan = MacroPlan(tuple(combo))
            evaluated += 1
            ok = True
            for state in property_states(spec):
                result = check_postconditions(
                    spec, dict(state.counts), execute_plan(plan, state)
                )
                if not result.accepted:
                    ok = False
                    break
            if ok:
                return plan, evaluated
    return None, evaluated
