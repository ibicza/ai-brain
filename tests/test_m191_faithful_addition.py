from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_m191_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "m191_faithful_systematic_addition.py"
    )
    spec = importlib.util.spec_from_file_location(
        "m191_faithful_systematic_addition", path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_faithful_rfft_puts_generic_rule_in_input_without_answer() -> None:
    m191 = _load_m191_module()
    case = m191.AddCase(a=27, b=35, width=2)

    prompt = m191._prompt_for_case(case, "rfft")
    answer = m191._answer_for_case(case, "rfft")

    assert "RULE ADD:" in prompt
    assert "PROBLEM: ADD 27 + 35" in prompt
    assert "FINAL 62" not in prompt
    assert "STEP 0 USE R1 R2 R3 R4 R5" in answer
    assert answer.endswith("FINAL 62")


def test_turing_trace_copies_persistent_state_with_local_edits() -> None:
    m191 = _load_m191_module()
    case = m191.AddCase(a=27, b=35, width=2)

    trace = m191._answer_for_case(case, "turing")

    assert trace.count("STATE ") >= 3
    assert trace.count("A 27") >= 3
    assert trace.count("B 35") >= 3
    assert "O ___" in trace
    assert "O __2" in trace
    assert "O _62" in trace
    assert trace.endswith("FINAL 62")


def test_clean_id_split_requires_pair_subset_and_prompt_disjoint() -> None:
    m191 = _load_m191_module()
    train = [m191.AddCase(a=12, b=34, width=2), m191.AddCase(a=56, b=80, width=2)]
    clean_id = [m191.AddCase(a=16, b=30, width=2)]

    m191._assert_id_split(train, clean_id)


def test_digit_pair_ood_detects_heldout_pair() -> None:
    m191 = _load_m191_module()
    case = m191.AddCase(a=17, b=65, width=2)

    assert case.has_heldout_pair
