"""Bounded exact execution of active verified rules."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

from ai_brain.rules.ast import (
    REGISTERS,
    RegisterState,
    default_binding,
    parse_canonical_dsl,
    step_state,
)
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.stage1.models import (
    ExecutionFailureCode,
    ExecutionLimits,
    ExecutionResult,
    content_hash,
)

HARD_MAX_REGISTER_VALUE = 10_000_000
HARD_MAX_TOTAL_UNITS = 10_000_000
HARD_MAX_EXECUTION_STEPS = 10_000_008
HARD_MAX_TRACE_ACTIONS = 100_000


class BoundedExecutionError(RuntimeError):
    def __init__(
        self,
        code: ExecutionFailureCode,
        message: str,
        *,
        executed_steps: int = 0,
        result: ExecutionResult | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.executed_steps = executed_steps
        self.result = result


def validate_limits(limits: ExecutionLimits) -> None:
    integer_fields = {
        "max_register_value": (limits.max_register_value, HARD_MAX_REGISTER_VALUE),
        "max_total_units": (limits.max_total_units, HARD_MAX_TOTAL_UNITS),
        "max_execution_steps": (
            limits.max_execution_steps,
            HARD_MAX_EXECUTION_STEPS,
        ),
        "max_trace_actions": (limits.max_trace_actions, HARD_MAX_TRACE_ACTIONS),
    }
    for name, (value, ceiling) in integer_fields.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise BoundedExecutionError(
                ExecutionFailureCode.INVALID_LIMITS,
                f"{name} must be a positive integer",
            )
        if value > ceiling:
            raise BoundedExecutionError(
                ExecutionFailureCode.INVALID_LIMITS,
                f"{name} exceeds hard ceiling {ceiling}",
            )
    if not isinstance(limits.capture_trace, bool) or not isinstance(
        limits.fail_on_trace_overflow, bool
    ):
        raise BoundedExecutionError(
            ExecutionFailureCode.INVALID_LIMITS, "trace policy fields must be bool"
        )


def validate_initial_state(
    initial_state: dict[str, int], limits: ExecutionLimits
) -> RegisterState:
    validate_limits(limits)
    if not isinstance(initial_state, dict) or set(initial_state) != set(REGISTERS):
        raise BoundedExecutionError(
            ExecutionFailureCode.INVALID_STATE,
            "state must contain exactly R0, R1, R2, and R3",
        )
    for register in REGISTERS:
        value = initial_state[register]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BoundedExecutionError(
                ExecutionFailureCode.INVALID_STATE,
                f"{register} must be a non-negative integer",
            )
        if value > limits.max_register_value:
            raise BoundedExecutionError(
                ExecutionFailureCode.REGISTER_LIMIT_EXCEEDED,
                f"{register} exceeds max_register_value",
            )
    if sum(initial_state.values()) > limits.max_total_units:
        raise BoundedExecutionError(
            ExecutionFailureCode.TOTAL_LIMIT_EXCEEDED,
            "state exceeds max_total_units",
        )
    return RegisterState(dict(initial_state))


def execute_rule(
    memory_path: Path,
    rule_id: str,
    initial_state: dict[str, int],
    *,
    proposal_id: str = "",
    limits: ExecutionLimits | None = None,
) -> ExecutionResult:
    actual_limits = limits or ExecutionLimits()
    state = validate_initial_state(initial_state, actual_limits)
    memory = RuleMemory.load_with_backup(memory_path)
    if rule_id not in memory.records:
        raise BoundedExecutionError(
            ExecutionFailureCode.UNKNOWN_RULE, f"Unknown rule {rule_id}"
        )
    record = memory.records[rule_id]
    if record.deprecated or record.status not in {
        VerificationStatus.FORMALLY_VERIFIED,
        VerificationStatus.PROPERTY_VERIFIED,
    }:
        raise BoundedExecutionError(
            ExecutionFailureCode.RULE_NOT_ACTIVE,
            f"Rule {rule_id} is not active and verified",
        )
    program, _ = parse_canonical_dsl(record.program_json)
    binding = default_binding()
    current = state
    captured: list[str] = []
    trace_truncated = False
    action_hasher = hashlib.sha256()

    for executed_steps in range(1, actual_limits.max_execution_steps + 1):
        try:
            clause_index = program.applicable_clause_index(binding, current)
            action = program.clauses[clause_index].action.resolve(binding)
            rendered = action.render()
        except ValueError as exc:
            raise BoundedExecutionError(
                ExecutionFailureCode.INVALID_EXECUTION,
                str(exc),
                executed_steps=executed_steps - 1,
            ) from exc
        if actual_limits.capture_trace:
            if len(captured) < actual_limits.max_trace_actions:
                captured.append(rendered)
            else:
                trace_truncated = True
                if actual_limits.fail_on_trace_overflow:
                    partial = _result(
                        rule_id,
                        proposal_id,
                        initial_state,
                        current.counts,
                        executed_steps - 1,
                        False,
                        actual_limits,
                        trace_truncated,
                        captured,
                        action_hasher.hexdigest(),
                        ExecutionFailureCode.TRACE_LIMIT_EXCEEDED,
                    )
                    raise BoundedExecutionError(
                        ExecutionFailureCode.TRACE_LIMIT_EXCEEDED,
                        "trace exceeded max_trace_actions",
                        executed_steps=executed_steps - 1,
                        result=partial,
                    )
        action_hasher.update(rendered.encode("utf-8"))
        action_hasher.update(b"\n")
        current, invalid, halted = step_state(current, action)
        if invalid:
            partial = _result(
                rule_id,
                proposal_id,
                initial_state,
                current.counts,
                executed_steps,
                False,
                actual_limits,
                trace_truncated,
                captured,
                action_hasher.hexdigest(),
                ExecutionFailureCode.INVALID_EXECUTION,
            )
            raise BoundedExecutionError(
                ExecutionFailureCode.INVALID_EXECUTION,
                "rule attempted an invalid state transition",
                executed_steps=executed_steps,
                result=partial,
            )
        if halted:
            return _result(
                rule_id,
                proposal_id,
                initial_state,
                current.counts,
                executed_steps,
                True,
                actual_limits,
                trace_truncated,
                captured,
                action_hasher.hexdigest(),
                None,
            )

    partial = _result(
        rule_id,
        proposal_id,
        initial_state,
        current.counts,
        actual_limits.max_execution_steps,
        False,
        actual_limits,
        trace_truncated,
        captured,
        action_hasher.hexdigest(),
        ExecutionFailureCode.STEP_LIMIT_EXCEEDED,
    )
    raise BoundedExecutionError(
        ExecutionFailureCode.STEP_LIMIT_EXCEEDED,
        "execution reached max_execution_steps before HALT",
        executed_steps=actual_limits.max_execution_steps,
        result=partial,
    )


def _result(
    rule_id: str,
    proposal_id: str,
    initial_state: dict[str, int],
    final_state: dict[str, int],
    executed_steps: int,
    halted: bool,
    limits: ExecutionLimits,
    trace_truncated: bool,
    captured: list[str],
    action_stream_hash: str,
    failure: ExecutionFailureCode | None,
) -> ExecutionResult:
    core = {
        "rule_id": rule_id,
        "proposal_id": proposal_id,
        "initial_state_hash": content_hash(initial_state),
        "final_state_hash": content_hash(final_state),
        "executed_steps": executed_steps,
        "halted": halted,
        "trace_requested": limits.capture_trace,
        "trace_truncated": trace_truncated,
        "action_stream_hash": action_stream_hash,
        "limits": asdict(limits),
        "failure_reason": str(failure) if failure else None,
    }
    return ExecutionResult(
        rule_id=rule_id,
        proposal_id=proposal_id,
        initial_state=dict(initial_state),
        final_state=dict(final_state),
        executed_steps=executed_steps,
        halted=halted,
        trace_requested=limits.capture_trace,
        trace_truncated=trace_truncated,
        captured_actions=tuple(captured),
        action_stream_hash=action_stream_hash,
        execution_hash=content_hash(core),
        limits_version=limits.version,
        limits=asdict(limits),
        failure_reason=str(failure) if failure else None,
    )
