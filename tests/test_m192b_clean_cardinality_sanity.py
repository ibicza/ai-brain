from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "m192b_clean_cardinality_sanity.py"
)
M192A_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "m192a_cardinality_lab.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "m192b_clean_cardinality_sanity",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_clean_prompts_do_not_contain_case_or_record_id() -> None:
    m192b = _load_module()
    datasets = m192b.build_datasets()

    for section in datasets.values():
        for examples in section.values():
            for example in examples:
                prompt = str(example["prompt"])
                assert not m192b.prompt_has_forbidden_marker(prompt)
                assert str(example["id"]) not in prompt
                assert f"CASE {example['metadata']['case_id']}" not in prompt
                assert f"ID {example['metadata']['case_id']}" not in prompt


def test_m192a_generator_no_longer_puts_case_in_prompts() -> None:
    source = M192A_PATH.read_text(encoding="utf-8")

    assert "CASE {" not in source
    assert "TRAIN_ONLY" not in source


def test_successor_prompt_is_minimal_and_canonical() -> None:
    m192b = _load_module()

    example = m192b.successor_symbol_example(3, index=123)

    assert example["prompt"] == "SUCC 3"
    assert example["answer"] == "FINAL 4"
    assert example["metadata"]["case_id"] == 123


def test_same_count_train_is_yes_no_balanced() -> None:
    m192b = _load_module()
    datasets = m192b.build_datasets()
    examples = datasets["train"]["same_count"]

    yes = sum(str(example["answer"]) == "FINAL YES" for example in examples)
    no = sum(str(example["answer"]) == "FINAL NO" for example in examples)

    assert yes == no


def test_semantic_fit_eval_uses_overlap_without_nuisance_markers() -> None:
    m192b = _load_module()
    datasets = m192b.build_datasets()
    audit = m192b.semantic_overlap_audit(datasets)

    assert audit["successor_symbol__successor_symbol_train_fit"] == 10
    assert audit["global_count__global_count_train_fit"] == 51
    assert audit["same_count__same_count_train_fit"] > 0
    assert all(
        not m192b.prompt_has_forbidden_marker(str(example["prompt"]))
        for example in datasets["eval"]["global_count_train_fit"]
    )


def test_iterative_transition_correctness() -> None:
    m192b = _load_module()

    example = m192b.iterative_count_example(4, "x", index=1)
    states = m192b.state_pairs(str(example["answer"]))

    assert states == [(0, 4), (1, 3), (2, 2), (3, 1), (4, 0)]
    assert m192b.valid_iterative_states(states)
