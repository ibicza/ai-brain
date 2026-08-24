"""Counterexample-guided inductive synthesis for the rule DSL."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from ai_brain.rules.ast import ProgramAst, RegisterState, exact_closed_loop
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import property_states, property_verify


class OracleAccessError(RuntimeError):
    pass


class AcquisitionTask:
    def __init__(
        self,
        *,
        task_id: str,
        specification: ProgramSpecification | None,
        demonstrations: Sequence[tuple[dict[str, int], dict[str, int]]] = (),
        search_budget: int = 1000,
        query_budget: int = 5,
    ) -> None:
        self.task_id = task_id
        self.specification = specification
        self.demonstrations = tuple(demonstrations)
        self.search_budget = search_budget
        self.query_budget = query_budget

    @property
    def target_ast(self) -> Any:
        raise OracleAccessError("target_ast is evaluator-only")

    @property
    def target_hash(self) -> str:
        raise OracleAccessError("target_hash is evaluator-only")

    @property
    def target_name(self) -> str:
        raise OracleAccessError("target_name is evaluator-only")

    @property
    def target_template(self) -> str:
        raise OracleAccessError("target_template is evaluator-only")


class HiddenTaskOracle:
    def __init__(self, target_program: ProgramAst) -> None:
        self._target_program = target_program

    def query(self, initial_state: RegisterState) -> dict[str, int]:
        return exact_closed_loop(self._target_program, initial_state)["final_state"]

    def score_after_termination(self, candidate: ProgramAst) -> bool:
        return candidate.semantic_hash(
            alpha=True, order_insensitive=True
        ) == self._target_program.semantic_hash(alpha=True, order_insensitive=True)


@dataclass(frozen=True)
class AcquisitionResult:
    status: VerificationStatus
    program: ProgramAst | None
    reason: str
    candidates_evaluated: int
    semantic_class_count: int
    query_count: int
    trace: tuple[dict[str, Any], ...] = ()


def demos_consistent(
    program: ProgramAst, demonstrations: Sequence[tuple[dict[str, int], dict[str, int]]]
) -> bool:
    for before, after in demonstrations:
        actual = exact_closed_loop(program, RegisterState(dict(before)))["final_state"]
        if actual != after:
            return False
    return True


def behavioral_fingerprint(program: ProgramAst, states: Sequence[RegisterState]) -> str:
    rows = []
    for state in states:
        try:
            rows.append(exact_closed_loop(program, state)["final_state"])
        except Exception as exc:  # noqa: BLE001
            rows.append({"error": str(exc)})
    return json.dumps(rows, sort_keys=True)


def semantic_classes(
    programs: Sequence[ProgramAst], states: Sequence[RegisterState]
) -> dict[str, list[ProgramAst]]:
    classes: dict[str, list[ProgramAst]] = defaultdict(list)
    for program in programs:
        classes[behavioral_fingerprint(program, states)].append(program)
    return classes


def choose_discriminating_state(
    programs: Sequence[ProgramAst], spec: ProgramSpecification
) -> RegisterState:
    best = property_states(spec)[0]
    best_partitions = -1
    for state in property_states(spec, large=True):
        partitions = {
            json.dumps(exact_closed_loop(program, state)["final_state"], sort_keys=True)
            for program in programs
        }
        if len(partitions) > best_partitions:
            best_partitions = len(partitions)
            best = state
    return best


def cegis_acquire(
    task: AcquisitionTask,
    candidates: Sequence[ProgramAst],
    *,
    query_callback: Callable[[RegisterState], dict[str, int]] | None = None,
    rank_key: Callable[[ProgramAst], float] | None = None,
) -> AcquisitionResult:
    trace = []
    ordered = sorted(candidates, key=rank_key or (lambda _program: 0.0), reverse=True)
    ordered = ordered[: task.search_budget]
    survivors = []
    for program in ordered:
        if task.specification is not None:
            verified = property_verify(program, task.specification)
            if not verified.accepted:
                continue
        if task.demonstrations and not demos_consistent(program, task.demonstrations):
            continue
        survivors.append(program)
    if not survivors:
        status = (
            VerificationStatus.UNSUPPORTED
            if task.specification and task.specification.unsupported
            else VerificationStatus.SEARCH_BUDGET_EXHAUSTED
        )
        return AcquisitionResult(status, None, "no_survivors", len(ordered), 0, 0)
    states = property_states(task.specification or ProgramSpecification())
    classes = semantic_classes(survivors, states)
    demos = list(task.demonstrations)
    queries = 0
    while (
        len(classes) > 1 and queries < task.query_budget and query_callback is not None
    ):
        state = choose_discriminating_state(
            survivors, task.specification or ProgramSpecification()
        )
        observed = query_callback(state)
        demos.append((dict(state.counts), observed))
        survivors = [
            program for program in survivors if demos_consistent(program, (demos[-1],))
        ]
        classes = semantic_classes(survivors, states)
        queries += 1
        trace.append({"query": dict(state.counts), "remaining_classes": len(classes)})
    if len(classes) == 1:
        status = (
            VerificationStatus.PROPERTY_VERIFIED
            if task.specification and task.specification.is_full()
            else VerificationStatus.IDENTIFIED_IN_HYPOTHESIS_SPACE
        )
        return AcquisitionResult(
            status,
            next(iter(classes.values()))[0],
            "unique_semantic_class",
            len(ordered),
            1,
            queries,
            tuple(trace),
        )
    return AcquisitionResult(
        VerificationStatus.AMBIGUOUS,
        None,
        "multiple_semantic_classes",
        len(ordered),
        len(classes),
        queries,
        tuple(trace),
    )


def random_ranker(seed: int = 0) -> Callable[[ProgramAst], float]:
    rng = random.Random(seed)
    cache: dict[str, float] = {}

    def score(program: ProgramAst) -> float:
        key = program.semantic_hash(alpha=False, order_insensitive=False)
        if key not in cache:
            cache[key] = rng.random()
        return cache[key]

    return score
