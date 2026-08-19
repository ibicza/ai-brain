from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "m192a_cardinality_lab.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("m192a_cardinality_lab", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_object_count_tokenization_has_no_aggregate_leak() -> None:
    m192a = _load_module()

    rows = m192a.tokenization_audit()

    assert rows
    assert not any(row["single_aggregate_token"] for row in rows)
    assert all(
        row["object_span_count"] == row["tokenized_object_span_count"]
        for row in rows
        if row["count"] > 0
    )


def test_heldout_objects_are_absent_from_training_sets() -> None:
    m192a = _load_module()
    rng = m192a.random.Random(m192a.SEED)
    eval_splits = m192a.build_eval_splits(rng)
    eval_prompts = {
        str(example["prompt"])
        for examples in eval_splits.values()
        for example in examples
    }
    trains = m192a.build_train_sets(rng, blocked_prompts=eval_prompts)

    heldout_markers = {m192a.obj_token(obj) for obj in m192a.HELDOUT_OBJECTS}
    for examples in trains.values():
        text = "\n".join(
            f"{example['prompt']}\n{example['answer']}" for example in examples
        )
        assert not any(marker in text for marker in heldout_markers)


def test_strict_trains_have_no_full_count_11_to_20_examples() -> None:
    m192a = _load_module()
    rng = m192a.random.Random(m192a.SEED)
    eval_splits = m192a.build_eval_splits(rng)
    eval_prompts = {
        str(example["prompt"])
        for examples in eval_splits.values()
        for example in examples
    }
    trains = m192a.build_train_sets(rng, blocked_prompts=eval_prompts)

    for name, examples in trains.items():
        assert m192a.full_count_ood_seen(examples) == 0, name


def test_matching_pair_generation_correctness() -> None:
    m192a = _load_module()
    rng = m192a.random.Random(123)

    examples = m192a.matching_examples(
        rng,
        count=9,
        counts=(0, 1, 2, 3),
        heldout=False,
    )

    assert examples
    for example in examples:
        meta = example["metadata"]
        expected_pairs = min(meta["left_count"], meta["right_count"])
        answer = str(example["answer"])
        assert answer.count("PAIR ") == expected_pairs
        if meta["left_count"] == meta["right_count"]:
            assert "FINAL SAME" in answer
        elif meta["left_count"] > meta["right_count"]:
            assert "FINAL LEFT_MORE" in answer
        else:
            assert "FINAL RIGHT_MORE" in answer


def test_pointer_movement_correctness() -> None:
    m192a = _load_module()

    example = m192a.pointer_tape_example(3, "X", "space", index=1)
    states = m192a.pointer_state_pairs(str(example["answer"]))

    assert states == [(0, 0), (1, 1), (2, 2), (3, 3)]
    assert m192a.valid_pointer_states(states)
    assert str(example["answer"]).endswith("FINAL 3")


def test_iterative_transition_correctness() -> None:
    m192a = _load_module()

    example = m192a.iterative_count_example(4, "X", "space", index=1)
    states = m192a.iterative_state_pairs(str(example["answer"]))

    assert states == [(0, 4), (1, 3), (2, 2), (3, 1), (4, 0)]
    assert m192a.valid_countdown_states(states)
    assert str(example["answer"]).endswith("FINAL 4")


def test_no_prompt_overlap_across_primary_splits() -> None:
    m192a = _load_module()
    rng = m192a.random.Random(m192a.SEED)
    eval_splits = m192a.build_eval_splits(rng)
    eval_prompts = {
        str(example["prompt"])
        for examples in eval_splits.values()
        for example in examples
    }
    trains = m192a.build_train_sets(rng, blocked_prompts=eval_prompts)

    intersections = m192a.prompt_intersections(trains, eval_splits)

    assert max(intersections.values()) == 0
