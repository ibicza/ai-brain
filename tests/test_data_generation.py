import json
from pathlib import Path

from ai_brain.data.generators import GENERATOR_NAMES, generate_examples
from ai_brain.data.schema import TrainingExample
from ai_brain.data.templates import (
    CountedNoun,
    choose_past_be_verb,
    format_counted_noun,
    format_counted_noun_accusative,
)
from ai_brain.data.writer import (
    dataset_stats,
    generate_data_split,
    generate_jsonl,
    read_jsonl,
    write_jsonl,
)


def test_training_example_json_line_is_valid_json() -> None:
    example = TrainingExample(
        id="test:00000000",
        task_type="test",
        prompt="Вопрос?",
        answer="Ответ.",
        metadata={"value": 123},
    )

    loaded = json.loads(example.to_json_line())

    assert loaded["id"] == "test:00000000"
    assert loaded["prompt"] == "Вопрос?"
    assert loaded["answer"] == "Ответ."
    assert loaded["metadata"]["value"] == 123


def test_generation_is_deterministic_for_same_seed() -> None:
    first = generate_examples(count=100, seed=1234)
    second = generate_examples(count=100, seed=1234)

    assert [example.to_dict() for example in first] == [
        example.to_dict() for example in second
    ]


def test_eval_profile_uses_harder_numeric_ranges() -> None:
    train_example = generate_examples(
        count=1,
        seed=1234,
        task_types=["arithmetic.add"],
        profile="train",
    )[0]
    eval_example = generate_examples(
        count=1,
        seed=1234,
        task_types=["arithmetic.add"],
        profile="eval",
    )[0]

    assert 0 <= train_example.metadata["a"] <= 30
    assert 0 <= train_example.metadata["b"] <= 30
    assert 20 <= eval_example.metadata["a"] <= 80
    assert 20 <= eval_example.metadata["b"] <= 80


def test_generator_set_has_enough_first_stage_task_types() -> None:
    assert len(GENERATOR_NAMES) >= 30


def test_generates_known_task_types() -> None:
    examples = generate_examples(count=1000, seed=1234)

    generated_task_types = {example.task_type for example in examples}

    assert generated_task_types.issubset(set(GENERATOR_NAMES))
    assert "comparison.max" in generated_task_types
    assert "arithmetic.add" in generated_task_types
    assert "sequence.arithmetic_progression" in generated_task_types
    assert "quantity.direct" in generated_task_types
    assert "quantity.irrelevant_subject" in generated_task_types
    assert "quantity.object_mismatch" in generated_task_types
    assert "state_change.add" in generated_task_types
    assert "state_change.subtract" in generated_task_types
    assert "epistemic.insufficient_info" in generated_task_types
    assert "epistemic.irrelevant_fact" in generated_task_types
    assert "logic.transitive_height" in generated_task_types


def test_each_generator_can_generate_one_example() -> None:
    for task_type in GENERATOR_NAMES:
        examples = generate_examples(
            count=1,
            seed=1234,
            task_types=[task_type],
        )

        assert len(examples) == 1
        assert examples[0].task_type == task_type
        assert examples[0].prompt
        assert examples[0].answer
        assert examples[0].metadata


def test_generate_jsonl_writes_file(tmp_path: Path) -> None:
    output_path = tmp_path / "dataset.jsonl"

    result = generate_jsonl(
        output_path=output_path,
        count=10,
        seed=1234,
    )

    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert result["count"] == 10
    assert len(lines) == 10

    first = json.loads(lines[0])

    assert set(first) == {"id", "task_type", "prompt", "answer", "metadata"}


def test_counted_noun_formatting() -> None:
    noun = CountedNoun(
        one="яблоко",
        few="яблока",
        many="яблок",
        question="яблок",
        gender="neuter",
    )

    assert format_counted_noun(1, noun) == "1 яблоко"
    assert format_counted_noun(2, noun) == "2 яблока"
    assert format_counted_noun(5, noun) == "5 яблок"
    assert format_counted_noun(11, noun) == "11 яблок"
    assert format_counted_noun(21, noun) == "21 яблоко"


def test_accusative_counted_noun_formatting() -> None:
    noun = CountedNoun(
        one="монета",
        few="монеты",
        many="монет",
        question="монет",
        gender="feminine",
        accusative_one="монету",
    )

    assert format_counted_noun_accusative(1, noun) == "1 монету"
    assert format_counted_noun_accusative(2, noun) == "2 монеты"
    assert format_counted_noun_accusative(5, noun) == "5 монет"
    assert format_counted_noun_accusative(21, noun) == "21 монету"


def test_irrelevant_fact_has_different_subjects() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["epistemic.irrelevant_fact"],
    )[0]

    assert example.task_type == "epistemic.irrelevant_fact"
    assert example.metadata["epistemic_state"] == "irrelevant_subject"
    assert example.metadata["fact_subject"] != example.metadata["question_subject"]
    assert example.answer.startswith("Недостаточно информации:")


def test_direct_quantity_answer_matches_metadata_count() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["quantity.direct"],
    )[0]

    assert example.task_type == "quantity.direct"
    assert example.metadata["epistemic_state"] == "known"
    assert example.answer == str(example.metadata["count"])
    assert example.metadata["subject_genitive"] in example.prompt
    assert example.metadata["known_fact"] in example.prompt
    assert example.metadata["question"] in example.prompt


def test_quantity_object_mismatch_uses_different_nouns() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["quantity.object_mismatch"],
    )[0]

    assert example.task_type == "quantity.object_mismatch"
    assert example.metadata["epistemic_state"] == "object_mismatch"
    assert example.metadata["fact_noun"] != example.metadata["question_noun"]
    assert example.answer.startswith("Недостаточно информации:")


def test_location_mismatch_uses_different_locations() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["quantity.location_mismatch"],
    )[0]

    assert example.task_type == "quantity.location_mismatch"
    assert example.metadata["epistemic_state"] == "location_mismatch"
    assert example.metadata["fact_location"] != example.metadata["question_location"]
    assert example.answer.startswith("Недостаточно информации:")


def test_state_change_add_adds_delta() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["state_change.add"],
    )[0]

    assert example.task_type == "state_change.add"
    assert example.answer == str(example.metadata["start"] + example.metadata["delta"])


def test_state_change_subtract_subtracts_delta() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["state_change.subtract"],
    )[0]

    assert example.task_type == "state_change.subtract"
    assert example.answer == str(example.metadata["start"] - example.metadata["delta"])


def test_state_change_other_subject_does_not_change_target() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["state_change.other_subject_no_change"],
    )[0]

    assert example.metadata["target_subject"] != example.metadata["changed_subject"]
    assert example.answer == str(example.metadata["start"])


def test_logic_transitive_height_answers_highest_person() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["logic.transitive_height"],
    )[0]

    assert example.task_type == "logic.transitive_height"
    assert example.answer == example.metadata["high"]


def test_known_zero_quantity_answers_zero() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["quantity.known_zero"],
    )[0]

    assert example.task_type == "quantity.known_zero"
    assert example.metadata["epistemic_state"] == "known_zero"
    assert example.answer == "0"


def test_false_presupposition_does_not_answer_zero() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["epistemic.false_presupposition"],
    )[0]

    assert example.task_type == "epistemic.false_presupposition"
    assert example.metadata["epistemic_state"] == "false_presupposition"
    assert example.answer.startswith("Ложная предпосылка:")


def test_compare_sum_does_not_ask_ambiguous_equal_sums() -> None:
    examples = generate_examples(
        count=100,
        seed=1234,
        task_types=["arithmetic.compare_sum"],
    )

    for example in examples:
        assert example.metadata["left"] != example.metadata["right"]
        assert example.answer == str(
            max(example.metadata["left"], example.metadata["right"])
        )


def test_past_be_verb_agrees_with_singular_noun_gender() -> None:
    masculine = CountedNoun(
        one="карандаш",
        few="карандаша",
        many="карандашей",
        question="карандашей",
        gender="masculine",
    )
    feminine = CountedNoun(
        one="монета",
        few="монеты",
        many="монет",
        question="монет",
        gender="feminine",
        accusative_one="монету",
    )
    neuter = CountedNoun(
        one="яблоко",
        few="яблока",
        many="яблок",
        question="яблок",
        gender="neuter",
    )

    assert choose_past_be_verb(1, masculine) == "был"
    assert choose_past_be_verb(1, feminine) == "была"
    assert choose_past_be_verb(1, neuter) == "было"
    assert choose_past_be_verb(2, masculine) == "было"
    assert choose_past_be_verb(11, feminine) == "было"
    assert choose_past_be_verb(21, masculine) == "был"


def test_generate_data_split_writes_manifest_and_disjoint_prompts(
    tmp_path: Path,
) -> None:
    task_types = ["arithmetic.add", "arithmetic.subtract", "quantity.direct"]
    output_dir = tmp_path / "stage1"

    result = generate_data_split(
        output_dir=output_dir,
        train_count=12,
        eval_count=9,
        train_seed=1000,
        eval_seed=2000,
        task_types=task_types,
    )

    train_examples = read_jsonl(output_dir / "train.jsonl")
    eval_examples = read_jsonl(output_dir / "eval.jsonl")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert result["manifest_path"] == str(output_dir / "manifest.json")
    assert len(train_examples) == 12
    assert len(eval_examples) == 9
    assert {example["prompt"] for example in train_examples}.isdisjoint(
        {example["prompt"] for example in eval_examples}
    )
    assert manifest["task_types"] == task_types
    assert manifest["quality_checks"]["prompt_intersection_count"] == 0
    assert manifest["quality_checks"]["all_task_types_present"] is True
    assert manifest["split_policy"]["enforce_unique_prompts"] is True
    assert manifest["splits"]["train"]["profile"] == "train"
    assert manifest["splits"]["eval"]["profile"] == "eval"
    assert manifest["splits"]["train"]["duplicate_prompt_count"] == 0
    assert manifest["splits"]["eval"]["duplicate_prompt_count"] == 0
    assert manifest["splits"]["train"]["missing_task_types"] == []
    assert manifest["splits"]["eval"]["missing_task_types"] == []


def test_dataset_stats_counts_task_types_and_missing_types(tmp_path: Path) -> None:
    output_path = tmp_path / "dataset.jsonl"
    generate_jsonl(
        output_path=output_path,
        count=5,
        seed=1234,
        task_types=["arithmetic.add"],
    )

    stats = dataset_stats(
        input_path=output_path,
        expected_task_types=["arithmetic.add", "arithmetic.subtract"],
    )

    assert stats["count"] == 5
    assert stats["task_type_counts"] == {"arithmetic.add": 5}
    assert stats["missing_task_types"] == ["arithmetic.subtract"]
    assert stats["all_task_types_present"] is False
    assert stats["duplicate_prompt_count"] >= 0


def test_dataset_stats_reports_top_duplicate_prompts(tmp_path: Path) -> None:
    output_path = tmp_path / "duplicates.jsonl"
    duplicate = TrainingExample(
        id="duplicate:00000000",
        task_type="arithmetic.add",
        prompt="same prompt",
        answer="1",
        metadata={"source": "test"},
    )
    unique = TrainingExample(
        id="unique:00000000",
        task_type="arithmetic.subtract",
        prompt="different prompt",
        answer="2",
        metadata={"source": "test"},
    )
    write_jsonl(output_path, [duplicate, duplicate, unique])

    stats = dataset_stats(input_path=output_path)

    assert stats["duplicate_prompt_count"] == 1
    assert stats["top_duplicate_prompts"] == [
        {
            "prompt": "same prompt",
            "count": 2,
            "task_type": "arithmetic.add",
        }
    ]
