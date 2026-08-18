from __future__ import annotations

from ai_brain.workspace_abi import (
    WorkspaceState,
    canonical_workspace_answer,
    parse_workspace_state,
    serialize_workspace_state,
    workspace_slot_scores,
)


def test_workspace_state_serializes_to_source_invariant_abi() -> None:
    state = WorkspaceState(op="add", a=27, b=35)

    assert serialize_workspace_state(state) == "<WS>\n<OP_ADD>\n<A> 27\n<B> 35\n</WS>"


def test_workspace_state_round_trip_for_subtraction() -> None:
    state = WorkspaceState(op="sub", a=83, b=27)

    assert parse_workspace_state(serialize_workspace_state(state)) == state


def test_workspace_parser_ignores_surrounding_generated_text() -> None:
    parsed = parse_workspace_state("noise\n<WS>\n<OP_ADD>\n<A> 9\n<B> 4\n</WS>\nmore")

    assert parsed == WorkspaceState(op="add", a=9, b=4)


def test_workspace_slot_scores_separate_slots() -> None:
    expected = WorkspaceState(op="add", a=27, b=35)
    predicted = WorkspaceState(op="sub", a=27, b=30)

    assert workspace_slot_scores(expected=expected, predicted=predicted) == {
        "op_exact": False,
        "a_exact": True,
        "b_exact": False,
        "workspace_exact": False,
    }


def test_canonical_workspace_answer_uses_same_format_for_all_sources() -> None:
    assert canonical_workspace_answer("add", 27, 35) == serialize_workspace_state(
        WorkspaceState(op="add", a=27, b=35)
    )
