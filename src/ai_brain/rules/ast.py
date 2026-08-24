"""Pure typed rule AST and exact interpreter.

These definitions preserve the frozen M-21 semantics without importing its
research/training script (and therefore without importing torch).
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

REGISTERS = ("R0", "R1", "R2", "R3")
LOGICAL_VARS = ("A", "B", "C", "D")
REG_BINDING = dict(zip(LOGICAL_VARS, REGISTERS, strict=True))
MAX_PREDS = 3
PredicateKind = Literal["EMPTY", "NONEMPTY"]
ActionKind = Literal["MOVE_ONE", "DROP_ONE", "HALT"]


@dataclass(frozen=True)
class PredicateAst:
    kind: PredicateKind
    variable: str

    def evaluate(self, binding: BindingAst, state: RegisterState) -> bool:
        value = state.counts[binding.physical(self.variable)]
        return value == 0 if self.kind == "EMPTY" else value > 0

    def alpha(self, rename: dict[str, str]) -> PredicateAst:
        return PredicateAst(self.kind, rename[self.variable])


@dataclass(frozen=True)
class ActionAst:
    kind: ActionKind
    source: str | None = None
    destination: str | None = None

    def resolve(self, binding: BindingAst) -> PhysicalAction:
        if self.kind == "MOVE_ONE":
            if self.source is None or self.destination is None:
                raise ValueError("MOVE_ONE requires source and destination")
            return PhysicalAction(
                "MOVE_ONE",
                binding.physical(self.source),
                binding.physical(self.destination),
            )
        if self.kind == "DROP_ONE":
            if self.source is None:
                raise ValueError("DROP_ONE requires source")
            return PhysicalAction("DROP_ONE", binding.physical(self.source))
        return PhysicalAction("HALT")

    def alpha(self, rename: dict[str, str]) -> ActionAst:
        return ActionAst(
            self.kind,
            rename[self.source] if self.source is not None else None,
            rename[self.destination] if self.destination is not None else None,
        )


@dataclass(frozen=True)
class ClauseAst:
    predicates: tuple[PredicateAst, ...]
    action: ActionAst

    def canonical(self) -> ClauseAst:
        return ClauseAst(
            tuple(sorted(self.predicates, key=lambda item: (item.variable, item.kind))),
            self.action,
        )

    def matches(self, binding: BindingAst, state: RegisterState) -> bool:
        return all(predicate.evaluate(binding, state) for predicate in self.predicates)

    def alpha(self, rename: dict[str, str]) -> ClauseAst:
        return ClauseAst(
            tuple(predicate.alpha(rename) for predicate in self.predicates),
            self.action.alpha(rename),
        )


@dataclass(frozen=True)
class ProgramAst:
    clauses: tuple[ClauseAst, ...]
    name: str = "program"

    def validate(self, variables: Sequence[str] | None = None) -> None:
        known = set(variables or sorted(program_variables(self)))
        if not self.clauses:
            raise ValueError("Program must contain at least one clause")
        for item in self.clauses:
            if len(item.predicates) > MAX_PREDS:
                raise ValueError("Too many predicates")
            for predicate in item.predicates:
                if predicate.kind not in {"EMPTY", "NONEMPTY"}:
                    raise ValueError(f"Unknown predicate kind {predicate.kind}")
                if predicate.variable not in known:
                    raise ValueError(f"Unknown predicate variable {predicate.variable}")
            action = item.action
            if action.kind not in {"MOVE_ONE", "DROP_ONE", "HALT"}:
                raise ValueError(f"Unknown action kind {action.kind}")
            for variable in (action.source, action.destination):
                if variable is not None and variable not in known:
                    raise ValueError(f"Unknown action variable {variable}")
            if action.kind == "MOVE_ONE" and (
                action.source is None or action.destination is None
            ):
                raise ValueError("MOVE_ONE requires two arguments")
            if action.kind == "DROP_ONE" and action.source is None:
                raise ValueError("DROP_ONE requires one argument")
            if action.kind == "HALT" and (
                action.source is not None or action.destination is not None
            ):
                raise ValueError("HALT takes no arguments")

    def applicable_clause_index(self, binding: BindingAst, state: RegisterState) -> int:
        matches = [
            index
            for index, item in enumerate(self.clauses)
            if item.matches(binding, state)
        ]
        if len(matches) != 1:
            raise ValueError(f"Program not deterministic for state {state}: {matches}")
        return matches[0]

    def semantic_json(
        self, *, alpha: bool = False, order_insensitive: bool = False
    ) -> str:
        if alpha and order_insensitive:
            candidates = []
            variables = sorted(program_variables(self))
            for order in itertools.permutations(variables):
                rename = {value: f"V{index}" for index, value in enumerate(order)}
                normalized = ProgramAst(
                    tuple(item.alpha(rename) for item in self.clauses), self.name
                )
                rows = [
                    clause_to_payload(item.canonical()) for item in normalized.clauses
                ]
                candidates.append(
                    json.dumps(sorted(rows, key=_json_key), sort_keys=True)
                )
            return min(candidates)
        program = alpha_normalize(self) if alpha else self
        rows = [clause_to_payload(item.canonical()) for item in program.clauses]
        if order_insensitive:
            rows = sorted(rows, key=_json_key)
        return json.dumps(rows, sort_keys=True)

    def semantic_hash(
        self, *, alpha: bool = False, order_insensitive: bool = False
    ) -> str:
        return stable_hash(
            self.semantic_json(alpha=alpha, order_insensitive=order_insensitive)
        )

    def alpha(self, variables: Sequence[str]) -> ProgramAst:
        rename = dict(zip(sorted(program_variables(self)), variables, strict=False))
        return ProgramAst(tuple(item.alpha(rename) for item in self.clauses), self.name)


@dataclass(frozen=True)
class BindingAst:
    mapping: dict[str, str]

    def __post_init__(self) -> None:
        if len(set(self.mapping.values())) != len(self.mapping):
            raise ValueError("Binding must be one-to-one")
        if any(register not in REGISTERS for register in self.mapping.values()):
            raise ValueError("Binding contains unknown register")

    def physical(self, variable: str) -> str:
        return self.mapping[variable]


@dataclass(frozen=True)
class RegisterState:
    counts: dict[str, int]

    def __post_init__(self) -> None:
        if set(self.counts) != set(REGISTERS):
            raise ValueError("RegisterState must contain all registers")
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in self.counts.values()
        ):
            raise TypeError("Register counts must be integers")
        if any(value < 0 for value in self.counts.values()):
            raise ValueError("Register counts must be non-negative")


@dataclass(frozen=True)
class PhysicalAction:
    kind: ActionKind
    source: str | None = None
    destination: str | None = None

    def render(self) -> str:
        if self.kind == "MOVE_ONE":
            return f"M {self.source} {self.destination}"
        if self.kind == "DROP_ONE":
            return f"D {self.source}"
        return "H"


def default_binding() -> BindingAst:
    return BindingAst(dict(REG_BINDING))


def make_program(clauses: list[ClauseAst], name: str = "program") -> ProgramAst:
    program = ProgramAst(tuple(clauses), name)
    program.validate(LOGICAL_VARS)
    return program


def exact_closed_loop(
    program: ProgramAst, state: RegisterState, binding: BindingAst | None = None
) -> dict[str, Any]:
    actual_binding = binding or default_binding()
    current = RegisterState(dict(state.counts))
    actions: list[str] = []
    invalid = False
    for _ in range(sum(state.counts.values()) + 8):
        action = program.clauses[
            program.applicable_clause_index(actual_binding, current)
        ].action.resolve(actual_binding)
        actions.append(action.render())
        current, step_invalid, terminated = step_state(current, action)
        invalid = invalid or step_invalid
        if invalid or terminated:
            break
    return {"final_state": current.counts, "invalid": invalid, "actions": actions}


def step_state(
    state: RegisterState, action: PhysicalAction
) -> tuple[RegisterState, bool, bool]:
    counts = dict(state.counts)
    if action.kind == "HALT":
        return RegisterState(counts), False, True
    if action.source is None:
        raise ValueError("State-changing action requires source")
    if counts[action.source] <= 0:
        return RegisterState(counts), True, False
    counts[action.source] -= 1
    if action.kind == "MOVE_ONE":
        if action.destination is None:
            raise ValueError("MOVE_ONE requires destination")
        counts[action.destination] += 1
    return RegisterState(counts), False, False


def parse_canonical_dsl(text: str) -> tuple[ProgramAst, BindingAst]:
    clauses: list[ClauseAst] = []
    binding = None
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        tokens = line.split()
        if (
            len(tokens) >= 8
            and len(tokens) % 2 == 0
            and all(tokens[index] in LOGICAL_VARS for index in range(0, len(tokens), 2))
        ):
            binding = BindingAst(
                {tokens[index]: tokens[index + 1] for index in range(0, len(tokens), 2)}
            )
        elif tokens[0] not in REGISTERS:
            clauses.append(_parse_clause_line(line))
    if binding is None:
        raise ValueError("DSL missing binding line")
    program = ProgramAst(tuple(clauses), "parsed")
    verify_m21_program(program, binding)
    return program, binding


def _parse_clause_line(line: str) -> ClauseAst:
    tokens = line.split()
    predicates: list[PredicateAst] = []
    index = 0
    while index < len(tokens) and tokens[index] in {"E", "NE"}:
        if index + 1 >= len(tokens):
            raise ValueError(f"Incomplete predicate: {line}")
        predicates.append(
            PredicateAst(
                "EMPTY" if tokens[index] == "E" else "NONEMPTY", tokens[index + 1]
            )
        )
        index += 2
    if index >= len(tokens):
        raise ValueError(f"Missing action in clause: {line}")
    action_token = tokens[index]
    remaining = tokens[index + 1 :]
    if action_token == "M" and len(remaining) == 2:
        action = ActionAst("MOVE_ONE", remaining[0], remaining[1])
    elif action_token == "D" and len(remaining) == 1:
        action = ActionAst("DROP_ONE", remaining[0])
    elif action_token == "H" and not remaining:
        action = ActionAst("HALT")
    else:
        raise ValueError(f"Invalid action in clause: {line}")
    return ClauseAst(tuple(predicates), action)


def render_canonical_program(
    program: ProgramAst, binding: BindingAst | None = None
) -> str:
    lines = [_render_clause(item) for item in program.clauses]
    actual_binding = binding or default_binding()
    lines.append(
        " ".join(
            f"{role} {register}"
            for role, register in sorted(actual_binding.mapping.items())
        )
    )
    return "\n".join(lines)


def _render_clause(item: ClauseAst) -> str:
    parts: list[str] = []
    for predicate in item.predicates:
        parts.extend(("E" if predicate.kind == "EMPTY" else "NE", predicate.variable))
    if item.action.kind == "MOVE_ONE":
        parts.extend(("M", item.action.source or "", item.action.destination or ""))
    elif item.action.kind == "DROP_ONE":
        parts.extend(("D", item.action.source or ""))
    else:
        parts.append("H")
    return " ".join(parts)


def verify_m21_program(program: ProgramAst, binding: BindingAst | None = None) -> None:
    actual_binding = binding or default_binding()
    program.validate(actual_binding.mapping.keys())
    for values in itertools.product((0, 1), repeat=len(REGISTERS)):
        state = RegisterState(dict(zip(REGISTERS, values, strict=True)))
        matches = [
            item for item in program.clauses if item.matches(actual_binding, state)
        ]
        if len(matches) != 1:
            raise ValueError(f"Program is not deterministic/exhaustive: {matches}")


def program_variables(program: ProgramAst) -> set[str]:
    variables: set[str] = set()
    for item in program.clauses:
        variables.update(predicate.variable for predicate in item.predicates)
        variables.update(
            value for value in (item.action.source, item.action.destination) if value
        )
    return variables


def alpha_normalize(program: ProgramAst) -> ProgramAst:
    rename: dict[str, str] = {}

    def normalized(variable: str | None) -> str | None:
        if variable is None:
            return None
        if variable not in rename:
            rename[variable] = f"V{len(rename)}"
        return rename[variable]

    return ProgramAst(
        tuple(
            ClauseAst(
                tuple(
                    PredicateAst(predicate.kind, normalized(predicate.variable) or "")
                    for predicate in item.predicates
                ),
                ActionAst(
                    item.action.kind,
                    normalized(item.action.source),
                    normalized(item.action.destination),
                ),
            )
            for item in program.clauses
        ),
        program.name,
    )


def clause_to_payload(item: ClauseAst) -> dict[str, Any]:
    return {
        "predicates": [asdict(predicate) for predicate in item.predicates],
        "action": asdict(item.action),
    }


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_key(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True)
