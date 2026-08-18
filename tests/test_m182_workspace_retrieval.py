from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "m182_workspace_retrieval_validation.py"
)


def _load_m182():
    spec = importlib.util.spec_from_file_location("m182_workspace", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load M-18.2 script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_m182_interleaves_balanced_cases_before_slicing() -> None:
    m182 = _load_m182()
    add_cases, sub_cases = m182.generate_balanced_cases(
        10,
        rng=random.Random(123),
        low=10,
        high=89,
    )
    cases = m182.interleave_balanced(add_cases, sub_cases)
    sliced = cases[:12]

    assert [case.op for case in sliced] == ["add", "sub"] * 6


def test_m182_assert_balanced_ops_rejects_add_only_dataset() -> None:
    m182 = _load_m182()
    records = [
        {"metadata": {"op": "add"}},
        {"metadata": {"op": "add"}},
    ]

    with pytest.raises(ValueError, match="ADD/SUB balanced"):
        m182.assert_balanced_ops(records, dataset_name="regression.add_only")


def test_m182_relevant_context_records_are_balanced() -> None:
    m182 = _load_m182()
    add_cases, sub_cases = m182.generate_balanced_cases(
        4,
        rng=random.Random(456),
        low=10,
        high=89,
    )
    records = m182._relevant_context_records(
        m182.interleave_balanced(add_cases, sub_cases),
        split="train",
        variant="test",
    )
    op_counts = {
        op: sum(record["metadata"]["op"] == op for record in records)
        for op in ("add", "sub")
    }

    assert op_counts == {"add": 4, "sub": 4}


def test_m182_retention_replay_includes_trained_variable_binding() -> None:
    m182 = _load_m182()
    add_cases, sub_cases = m182.generate_balanced_cases(
        8,
        rng=random.Random(789),
        low=10,
        high=89,
    )
    records = m182._retention_replay_records(
        m182.interleave_balanced(add_cases, sub_cases)
    )

    assert any(
        str(record["task_type"]).startswith("m182.binding.") for record in records
    )
