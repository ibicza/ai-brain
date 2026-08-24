"""Exact execution of active verified rules against external register state."""

from __future__ import annotations

from pathlib import Path

from ai_brain.rules.ast import RegisterState, exact_closed_loop, parse_canonical_dsl
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.stage1.models import ExecutionResult, content_hash


def execute_rule(
    memory_path: Path, rule_id: str, initial_state: dict[str, int]
) -> ExecutionResult:
    memory = RuleMemory.load_with_backup(memory_path)
    if rule_id not in memory.records:
        raise KeyError(f"Unknown rule {rule_id}")
    record = memory.records[rule_id]
    if record.deprecated:
        raise ValueError(f"Rule {rule_id} is deprecated")
    if record.status not in {
        VerificationStatus.FORMALLY_VERIFIED,
        VerificationStatus.PROPERTY_VERIFIED,
    }:
        raise ValueError(f"Rule {rule_id} is not verified")
    state = RegisterState(dict(initial_state))
    program, _ = parse_canonical_dsl(record.program_json)
    raw = exact_closed_loop(program, state)
    if raw["invalid"] or not raw["actions"] or raw["actions"][-1] != "H":
        raise RuntimeError("Exact execution did not terminate safely")
    core = {
        "rule_id": rule_id,
        "initial_state": initial_state,
        "final_state": raw["final_state"],
        "actions": raw["actions"],
    }
    return ExecutionResult(
        rule_id=rule_id,
        initial_state=dict(initial_state),
        final_state=dict(raw["final_state"]),
        actions=tuple(raw["actions"]),
        execution_hash=content_hash(core),
    )
