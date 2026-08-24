"""Public-only protocol and acquisition logic for black-box rule synthesis."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from ai_brain.rules.ast import (
    ProgramAst,
    RegisterState,
    exact_closed_loop,
    parse_canonical_dsl,
    render_canonical_program,
)
from ai_brain.rules.grammar import blackbox_candidate_pool
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import (
    VerificationResult,
    abstract_verify,
    property_states,
    property_verify,
    static_verify,
)

_DEMO_VALIDITY_CACHE: dict[str, bool] = {}
_DEMO_OUTPUT_CACHE: dict[tuple[str, str], dict[str, int] | None] = {}
_DEMO_FINGERPRINT_CACHE: dict[tuple[str, tuple[str, ...]], str] = {}


@dataclass(frozen=True)
class PublicAcquisitionTask:
    task_id: str
    mode: str
    specification: ProgramSpecification | None = None
    demonstrations: tuple[tuple[dict[str, int], dict[str, int]], ...] = ()
    candidate_budget: int = 10_000
    query_budget: int = 5
    query_answers: tuple[tuple[dict[str, int], dict[str, int]], ...] = ()
    rule_memory_view: tuple[dict[str, Any], ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "mode": self.mode,
            "specification": specification_to_json(self.specification),
            "demonstrations": [
                {"before": before, "after": after}
                for before, after in self.demonstrations
            ],
            "candidate_budget": self.candidate_budget,
            "query_budget": self.query_budget,
            "query_answers": [
                {"before": before, "after": after}
                for before, after in self.query_answers
            ],
            "rule_memory_view": list(self.rule_memory_view),
        }

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> PublicAcquisitionTask:
        return cls(
            task_id=str(row["task_id"]),
            mode=str(row["mode"]),
            specification=specification_from_json(row.get("specification")),
            demonstrations=tuple(
                (dict(item["before"]), dict(item["after"]))
                for item in row.get("demonstrations", ())
            ),
            candidate_budget=int(row.get("candidate_budget", 10_000)),
            query_budget=int(row.get("query_budget", 5)),
            query_answers=tuple(
                (dict(item["before"]), dict(item["after"]))
                for item in row.get("query_answers", ())
            ),
            rule_memory_view=tuple(
                dict(item) for item in row.get("rule_memory_view", ())
            ),
        )


@dataclass(frozen=True)
class PublicAcquisitionResult:
    task_id: str
    status: str
    candidate_ast: str | None
    verification_evidence: dict[str, Any] | None
    query_trace: tuple[dict[str, Any], ...] = ()
    search_trace: tuple[dict[str, Any], ...] = ()
    candidates_to_first_verified: int | None = None
    actual_property_checks: int = 0
    candidate_pool_size: int = 0
    wall_time_sec: float = 0.0
    requested_query: dict[str, int] | None = None
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def specification_to_json(spec: ProgramSpecification | None) -> dict[str, Any] | None:
    return asdict(spec) if spec is not None else None


def specification_from_json(row: dict[str, Any] | None) -> ProgramSpecification | None:
    if row is None:
        return None
    data = dict(row)
    for key in (
        "inputs",
        "outputs",
        "drops",
        "preserve",
        "terminate_when_empty",
        "allowed_variables",
        "allowed_primitives",
    ):
        data[key] = tuple(data.get(key, ()))
    data["transfers"] = tuple(tuple(item) for item in data.get("transfers", ()))
    data["phase_constraints"] = tuple(
        (str(item[0]), str(item[1]), item[2])
        for item in data.get("phase_constraints", ())
    )
    return ProgramSpecification(**data)


def verification_to_json(result: VerificationResult) -> dict[str, Any]:
    return {
        "accepted": result.accepted,
        "status": str(result.status),
        "reason": result.reason,
        "counterexample": result.counterexample,
        "verifier": "property_verify",
    }


def specification_signature(spec: ProgramSpecification) -> str:
    return json.dumps(
        specification_to_json(spec), sort_keys=True, separators=(",", ":")
    )


def acquire_public_task(
    task: PublicAcquisitionTask,
    candidates: list[ProgramAst] | None = None,
) -> PublicAcquisitionResult:
    """Acquire from public evidence only; hidden target objects are not accepted."""
    started = time.perf_counter()
    pool = candidates or blackbox_candidate_pool(task.candidate_budget)
    pool = pool[: task.candidate_budget]
    if task.mode == "full_spec":
        return _acquire_full_spec(task, pool, started)
    if task.mode == "demo":
        return _acquire_demo(task, pool, started)
    return PublicAcquisitionResult(
        task.task_id,
        str(VerificationStatus.UNSUPPORTED),
        None,
        None,
        candidate_pool_size=len(pool),
        wall_time_sec=time.perf_counter() - started,
        reason="unsupported_mode",
    )


def _acquire_full_spec(
    task: PublicAcquisitionTask, pool: list[ProgramAst], started: float
) -> PublicAcquisitionResult:
    spec = task.specification
    if spec is None or not spec.is_full():
        return PublicAcquisitionResult(
            task.task_id,
            str(VerificationStatus.UNSUPPORTED),
            None,
            None,
            candidate_pool_size=len(pool),
            wall_time_sec=time.perf_counter() - started,
            reason="missing_full_specification",
        )
    trace: list[dict[str, Any]] = []
    property_checks = 0
    for rank, candidate in enumerate(pool, start=1):
        static = static_verify(candidate)
        if not static.accepted:
            continue
        abstract = abstract_verify(candidate)
        if not abstract.accepted:
            continue
        property_checks += 1
        verified = property_verify(candidate, spec, large=True)
        if len(trace) < 20 or verified.accepted:
            trace.append(
                {
                    "candidate_rank": rank,
                    "property_accepted": verified.accepted,
                    "reason": verified.reason,
                }
            )
        if verified.accepted:
            return PublicAcquisitionResult(
                task.task_id,
                str(VerificationStatus.PROPERTY_VERIFIED),
                render_canonical_program(candidate),
                verification_to_json(verified),
                search_trace=tuple(trace),
                candidates_to_first_verified=rank,
                actual_property_checks=property_checks,
                candidate_pool_size=len(pool),
                wall_time_sec=time.perf_counter() - started,
                reason="first_property_satisfying_candidate",
            )
    return PublicAcquisitionResult(
        task.task_id,
        str(VerificationStatus.SEARCH_BUDGET_EXHAUSTED),
        None,
        None,
        search_trace=tuple(trace),
        actual_property_checks=property_checks,
        candidate_pool_size=len(pool),
        wall_time_sec=time.perf_counter() - started,
        reason="no_property_satisfying_candidate",
    )


def _acquire_demo(
    task: PublicAcquisitionTask, pool: list[ProgramAst], started: float
) -> PublicAcquisitionResult:
    observations = (*task.demonstrations, *task.query_answers)
    survivors = []
    for program in pool:
        if not _demo_candidate_valid(program):
            continue
        if _demo_consistent_or_false(program, observations):
            survivors.append(program)
    probe_states = property_states(ProgramSpecification(), large=True)
    classes: dict[str, list[ProgramAst]] = {}
    for program in survivors:
        key = _cached_behavioral_fingerprint(program, probe_states)
        classes.setdefault(key, []).append(program)
    trace = tuple(
        {"before": before, "after": after} for before, after in task.query_answers
    )
    if len(classes) == 1:
        selected = next(iter(classes.values()))[0]
        return PublicAcquisitionResult(
            task.task_id,
            str(VerificationStatus.IDENTIFIED_IN_HYPOTHESIS_SPACE),
            render_canonical_program(selected),
            {
                "accepted": True,
                "status": str(VerificationStatus.IDENTIFIED_IN_HYPOTHESIS_SPACE),
                "reason": "one_acquisition_visible_behavioral_class",
            },
            query_trace=trace,
            candidate_pool_size=len(pool),
            wall_time_sec=time.perf_counter() - started,
            reason="unique_behavioral_class",
        )
    if classes and len(task.query_answers) < task.query_budget:
        state = _choose_public_query(survivors, probe_states, task.query_answers)
        if state is not None:
            return PublicAcquisitionResult(
                task.task_id,
                "QUERY_REQUIRED",
                None,
                None,
                query_trace=trace,
                candidate_pool_size=len(pool),
                wall_time_sec=time.perf_counter() - started,
                requested_query=dict(state.counts),
                reason=f"{len(classes)}_classes_remain",
            )
    return PublicAcquisitionResult(
        task.task_id,
        str(VerificationStatus.AMBIGUOUS),
        None,
        None,
        query_trace=trace,
        candidate_pool_size=len(pool),
        wall_time_sec=time.perf_counter() - started,
        reason=f"{len(classes)}_classes_remain",
    )


def _demo_consistent_or_false(
    program: ProgramAst,
    observations: tuple[tuple[dict[str, int], dict[str, int]], ...],
) -> bool:
    for before, expected in observations:
        actual = _cached_demo_output(program, before)
        if actual is None or actual != expected:
            return False
    return True


def _demo_candidate_valid(program: ProgramAst) -> bool:
    key = program.semantic_hash(alpha=False, order_insensitive=False)
    if key not in _DEMO_VALIDITY_CACHE:
        _DEMO_VALIDITY_CACHE[key] = bool(
            static_verify(program).accepted and abstract_verify(program).accepted
        )
    return _DEMO_VALIDITY_CACHE[key]


def _cached_demo_output(
    program: ProgramAst, before: dict[str, int]
) -> dict[str, int] | None:
    program_key = program.semantic_hash(alpha=False, order_insensitive=False)
    state_key = json.dumps(before, sort_keys=True, separators=(",", ":"))
    key = (program_key, state_key)
    if key not in _DEMO_OUTPUT_CACHE:
        try:
            _DEMO_OUTPUT_CACHE[key] = exact_closed_loop(
                program, RegisterState(dict(before))
            )["final_state"]
        except Exception:  # noqa: BLE001 - invalid candidates are rejected evidence.
            _DEMO_OUTPUT_CACHE[key] = None
    return _DEMO_OUTPUT_CACHE[key]


def _cached_behavioral_fingerprint(
    program: ProgramAst, states: list[RegisterState]
) -> str:
    program_key = program.semantic_hash(alpha=False, order_insensitive=False)
    state_keys = tuple(
        json.dumps(state.counts, sort_keys=True, separators=(",", ":"))
        for state in states
    )
    key = (program_key, state_keys)
    if key not in _DEMO_FINGERPRINT_CACHE:
        rows = [_cached_demo_output(program, dict(state.counts)) for state in states]
        _DEMO_FINGERPRINT_CACHE[key] = json.dumps(rows, sort_keys=True)
    return _DEMO_FINGERPRINT_CACHE[key]


def _choose_public_query(
    survivors: list[ProgramAst],
    states: list[RegisterState],
    answered: tuple[tuple[dict[str, int], dict[str, int]], ...],
) -> RegisterState | None:
    asked = {json.dumps(before, sort_keys=True) for before, _after in answered}
    best: RegisterState | None = None
    best_partitions = 1
    for state in states:
        if json.dumps(state.counts, sort_keys=True) in asked:
            continue
        partitions = {
            _cached_behavioral_fingerprint(program, [state]) for program in survivors
        }
        if len(partitions) > best_partitions:
            best = state
            best_partitions = len(partitions)
    return best


def parse_result_program(row: dict[str, Any]) -> ProgramAst | None:
    text = row.get("candidate_ast")
    return parse_canonical_dsl(text)[0] if text else None


def safe_rule_route(
    specification: ProgramSpecification,
    memory_view: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Use an exact public signature or abstain and route to CEGIS."""
    signature = specification_signature(specification)
    matches = [
        row for row in memory_view if row.get("specification_signature") == signature
    ]
    if len(matches) == 1:
        return {
            "route": "RULE_MEMORY",
            "rule_id": matches[0]["rule_id"],
            "confidence": 1.0,
        }
    return {"route": "CEGIS", "rule_id": None, "confidence": 0.0}
