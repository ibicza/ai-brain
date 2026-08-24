from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "m192c_count_state_representation.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "m192c_count_state_representation",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_unary_state_length_equals_cardinality() -> None:
    m192c = _load_module()

    for n in range(31):
        assert m192c.unary_length(m192c.unary_state(n)) == n


def test_external_counter_oracle_takes_then_stops() -> None:
    m192c = _load_module()

    actions = [
        m192c.take_stop_action_example(4, "x", head, index=head)["metadata"][
            "expected_action"
        ]
        for head in range(5)
    ]

    assert actions == ["TAKE", "TAKE", "TAKE", "TAKE", "STOP"]


def test_stop_only_after_final_object_in_oracle_procedure() -> None:
    m192c = _load_module()

    for n in range(11):
        for head in range(n):
            example = m192c.take_stop_action_example(n, "x", head, index=head)
            assert example["answer"] == "FINAL TAKE"
        terminal = m192c.take_stop_action_example(n, "x", n, index=999)
        assert terminal["answer"] == "FINAL STOP"


def test_tens_ones_state_conversion_round_trips() -> None:
    m192c = _load_module()

    for n in range(31):
        assert m192c.structured_to_int(m192c.structured_state(n)) == n


def test_no_11_to_20_full_count_leakage_in_zero_shot_train_sets() -> None:
    m192c = _load_module()
    datasets = m192c.build_datasets()
    leakage = m192c.full_count_leakage(datasets["train"])

    assert leakage["decimal_iterative"] == 0
    assert leakage["unary_count"] == 0
    assert leakage["global_count_0_10"] == 0


def test_exact_few_shot_expansion_counts() -> None:
    m192c = _load_module()
    datasets = m192c.build_datasets()

    for examples_per_count in m192c.EXPANSION_EXAMPLES_PER_COUNT:
        examples = datasets["train"][f"range_expansion_{examples_per_count}"]
        assert len(examples) == examples_per_count * len(m192c.LENGTH_OOD_COUNTS)


def test_same_count_11_to_20_generator_correctness() -> None:
    m192c = _load_module()
    examples = m192c.same_count_examples(
        m192c.LENGTH_OOD_COUNTS,
        m192c.TRAIN_OBJECTS,
        index_offset=0,
    )

    assert examples
    for example in examples:
        meta = example["metadata"]
        expected = "FINAL YES" if meta["left_n"] == meta["right_n"] else "FINAL NO"
        assert example["answer"] == expected


def test_action_matching_environment_oracle() -> None:
    m192c = _load_module()

    assert m192c.matching_oracle_action(3, 3) == "PAIR"
    assert m192c.matching_oracle_action(0, 0) == "SAME"
    assert m192c.matching_oracle_action(2, 0) == "LEFT_MORE"
    assert m192c.matching_oracle_action(0, 2) == "RIGHT_MORE"


def test_no_forbidden_prompt_markers() -> None:
    m192c = _load_module()
    datasets = m192c.build_datasets()

    prompts = [
        str(example["prompt"])
        for section in datasets.values()
        for examples in section.values()
        for example in examples
    ]

    assert prompts
    assert not any(m192c.prompt_has_forbidden_marker(prompt) for prompt in prompts)


def test_probe_prompt_builders_cover_train_counts_without_markers() -> None:
    m192c = _load_module()
    builders = [
        m192c.probe_prompts_global_count,
        m192c.probe_prompts_unary_count,
        m192c.probe_prompts_terminal_action_count,
        m192c.probe_prompts_structured_counter,
    ]

    for builder in builders:
        prompts = builder(m192c.TRAIN_COUNTS, m192c.TRAIN_OBJECTS[:2])
        assert sorted({count for count, _prompt in prompts}) == list(m192c.TRAIN_COUNTS)
        assert not any(
            m192c.prompt_has_forbidden_marker(prompt) for _count, prompt in prompts
        )
