"""Property and observability checks for final-state equivalence groups."""

from __future__ import annotations

from pathlib import Path

from ai_brain.rules.ast import PhysicalAction, RegisterState, step_state
from ai_brain.stage1.execution import execute_rule
from ai_brain.stage1.models import ExecutionLimits
from ai_brain.stage2.models import SkillRecord
from ai_brain.stage2.registry import SkillRegistry
from ai_brain.stage2.semantics import build_final_state_equivalence_groups


def observe_execution(
    memory_path: Path,
    skill: SkillRecord,
    initial_state: dict[str, int],
) -> dict:
    result = execute_rule(
        memory_path,
        skill.rule_id,
        initial_state,
        limits=ExecutionLimits(capture_trace=True),
    )
    intermediate = _intermediate_states(initial_state, result.captured_actions)
    return {
        "skill_id": skill.skill_id,
        "specification_hash": skill.specification_hash,
        "final_state_effect_hash": skill.final_state_effect_hash,
        "initial_state": dict(initial_state),
        "final_state": result.final_state,
        "executed_steps": result.executed_steps,
        "captured_actions": list(result.captured_actions),
        "intermediate_states": intermediate,
        "action_stream_hash": result.action_stream_hash,
        "execution_hash": result.execution_hash,
    }


def validate_final_state_equivalence_classes(
    memory_path: Path,
    registry: SkillRegistry,
) -> dict:
    groups = build_final_state_equivalence_groups(registry.active_records())
    battery = _state_battery()
    trace_distinct_classes: list[str] = []
    checked_pairs = 0
    checked_executions = 0
    representative_pairs: list[dict] = []
    for group in groups:
        members = [registry.records[item] for item in group.member_skill_ids]
        if len(members) < 2:
            continue
        canonical = members[0]
        group_trace_distinct = False
        for candidate in members[1:]:
            checked_pairs += 1
            pair_difference = False
            first_difference: dict | None = None
            for state in battery:
                expected = observe_execution(memory_path, canonical, state)
                actual = observe_execution(memory_path, candidate, state)
                checked_executions += 2
                if expected["final_state"] != actual["final_state"]:
                    raise AssertionError(
                        "Invalid final-state equivalence class "
                        f"{group.equivalence_class_hash}: "
                        f"{canonical.skill_id} != {candidate.skill_id}"
                    )
                differs = any(
                    expected[field] != actual[field]
                    for field in (
                        "captured_actions",
                        "intermediate_states",
                        "action_stream_hash",
                    )
                )
                pair_difference = pair_difference or differs
                if differs and first_difference is None:
                    first_difference = {
                        "equivalence_class_hash": group.equivalence_class_hash,
                        "proof_kind": group.equivalence_proof_kind,
                        "first": expected,
                        "second": actual,
                    }
            group_trace_distinct = group_trace_distinct or pair_difference
            if first_difference is not None and len(representative_pairs) < 8:
                representative_pairs.append(first_difference)
        if group_trace_distinct:
            trace_distinct_classes.append(group.equivalence_class_hash)
    expected_trace_distinct = sum(group.member_count > 1 for group in groups)
    if len(trace_distinct_classes) != expected_trace_distinct:
        raise AssertionError("A multi-member final-state class lacked trace difference")
    return {
        "status": "PASS",
        "structural_skill_count": len(registry.active_records()),
        "final_state_effect_class_count": len(groups),
        "full_execution_equivalence_class_count": len(
            {item.specification_hash for item in registry.active_records()}
        ),
        "class_size_distribution": {
            str(size): sum(group.member_count == size for group in groups)
            for size in sorted({group.member_count for group in groups})
        },
        "order_sensitive_class_count": sum(group.order_sensitive for group in groups),
        "order_insensitive_class_count": sum(
            not group.order_sensitive for group in groups
        ),
        "trace_distinct_class_count": len(trace_distinct_classes),
        "trace_distinct_class_hashes": trace_distinct_classes,
        "state_battery": battery,
        "checked_pair_count": checked_pairs,
        "checked_execution_count": checked_executions,
        "representative_pairs": representative_pairs,
    }


def _intermediate_states(
    initial_state: dict[str, int], actions: tuple[str, ...]
) -> list[dict[str, int]]:
    current = RegisterState(dict(initial_state))
    states: list[dict[str, int]] = []
    for rendered in actions:
        action = _parse_physical_action(rendered)
        current, invalid, _ = step_state(current, action)
        if invalid:
            raise AssertionError(f"Captured action is invalid: {rendered}")
        states.append(dict(current.counts))
    return states


def _parse_physical_action(rendered: str) -> PhysicalAction:
    tokens = rendered.split()
    if tokens == ["H"]:
        return PhysicalAction("HALT")
    if len(tokens) == 2 and tokens[0] == "D":
        return PhysicalAction("DROP_ONE", source=tokens[1])
    if len(tokens) == 3 and tokens[0] == "M":
        return PhysicalAction("MOVE_ONE", source=tokens[1], destination=tokens[2])
    raise AssertionError(f"Unknown captured action: {rendered}")


def _state_battery() -> list[dict[str, int]]:
    return [
        {"R0": 0, "R1": 0, "R2": 0, "R3": 0},
        {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        {"R0": 0, "R1": 1, "R2": 0, "R3": 0},
        {"R0": 0, "R1": 0, "R2": 1, "R3": 0},
        {"R0": 0, "R1": 0, "R2": 0, "R3": 1},
        {"R0": 2, "R1": 3, "R2": 5, "R3": 7},
        {"R0": 10, "R1": 1, "R2": 4, "R3": 2},
        {"R0": 1, "R1": 10, "R2": 2, "R3": 4},
        {"R0": 4, "R1": 2, "R2": 10, "R3": 1},
        {"R0": 2, "R1": 4, "R2": 1, "R3": 10},
    ]
