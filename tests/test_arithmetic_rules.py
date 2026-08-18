from __future__ import annotations

from ai_brain.arithmetic_rules import (
    ArithmeticCase,
    arithmetic_prompt,
    final_answer_from_trace,
    format_trace,
    trace_component_scores,
    verify_trace,
)


def test_arithmetic_prompt_is_plain_symbolic() -> None:
    assert arithmetic_prompt(ArithmeticCase(op="add", a=27, b=35)) == "ADD 27 + 35"


def test_scratchpad_addition_tracks_carry() -> None:
    case = ArithmeticCase(op="add", a=27, b=35)
    trace = format_trace(case, "scratchpad")

    assert "D0: 7+5+C0=12" in trace
    assert "OUT_D0 2" in trace
    assert "C 1" in trace
    assert trace.endswith("FINAL 62")
    assert verify_trace(case, trace, "scratchpad")


def test_answer_only_carry_borrow_metric_is_not_applicable() -> None:
    case = ArithmeticCase(op="add", a=27, b=35)

    answer_scores = trace_component_scores(case, "FINAL 62", "answer")
    scratchpad_scores = trace_component_scores(
        case,
        format_trace(case, "scratchpad"),
        "scratchpad",
    )

    assert answer_scores["carry_borrow_exact"] is None
    assert scratchpad_scores["carry_borrow_exact"] is True


def test_scratchpad_subtraction_tracks_borrow() -> None:
    case = ArithmeticCase(op="sub", a=83, b=27)
    trace = format_trace(case, "scratchpad")

    assert "D0: 3-7-B0=-4" in trace
    assert "OUT_D0 6" in trace
    assert "B 1" in trace
    assert trace.endswith("FINAL 56")
    assert verify_trace(case, trace, "scratchpad")


def test_rfft_uses_generic_rule_header() -> None:
    trace = format_trace(ArithmeticCase(op="add", a=27, b=35), "rfft")

    assert trace.startswith("RULE ADD\nR1 LSD\nR2 SUM_DIGITS_WITH_CARRY")
    assert "EXEC ADD" in trace


def test_state_machine_uses_repeated_local_transitions() -> None:
    trace = format_trace(ArithmeticCase(op="add", a=27, b=35), "state_machine")

    assert "READ 7 5 C0\nWRITE 2\nCARRY 1\nMOVE" in trace
    assert "READ 2 3 C1\nWRITE 6\nCARRY 0\nMOVE" in trace


def test_trace_component_scores_separate_final_from_trace() -> None:
    case = ArithmeticCase(op="add", a=27, b=35)
    bad_trace = "TRACE ADD\nD0: 7+5+C0=12\nOUT_D0 2\nC 1\nHALT\nFINAL 62"

    scores = trace_component_scores(case, bad_trace, "scratchpad")

    assert scores["final_exact"] is True
    assert scores["full_trace_exact"] is False
    assert scores["carry_borrow_exact"] is False


def test_final_answer_from_trace_returns_integer() -> None:
    assert final_answer_from_trace("x\nFINAL 149") == 149
