import json
from pathlib import Path

from ai_brain.data.answer_format import apply_answer_format
from ai_brain.data.generators import GENERATOR_NAMES, generate_examples
from ai_brain.data.number_format import (
    digits_of_number,
    format_plain_digit_number,
    format_role_number,
    place_names_for_digits,
)
from ai_brain.data.presets import TASK_PRESETS, resolve_task_selection
from ai_brain.data.schema import TrainingExample
from ai_brain.data.templates import (
    CountedNoun,
    choose_past_be_verb,
    format_counted_noun,
    format_counted_noun_accusative,
)
from ai_brain.data.writer import (
    dataset_stats,
    generate_arithmetic_primitive_split,
    generate_data_split,
    generate_digit_table_curriculum,
    generate_jsonl,
    generate_range_ablation,
    generate_range_primed,
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


def test_same_and_shifted_profiles_use_expected_numeric_ranges() -> None:
    train_same = generate_examples(
        count=1,
        seed=1234,
        task_types=["arithmetic.add"],
        profile="train_same",
    )[0]
    eval_same = generate_examples(
        count=1,
        seed=2234,
        task_types=["arithmetic.add"],
        profile="eval_same",
    )[0]
    eval_shifted = generate_examples(
        count=1,
        seed=1234,
        task_types=["arithmetic.add"],
        profile="eval_shifted",
    )[0]

    assert 0 <= train_same.metadata["a"] <= 30
    assert 0 <= train_same.metadata["b"] <= 30
    assert 0 <= eval_same.metadata["a"] <= 30
    assert 0 <= eval_same.metadata["b"] <= 30
    assert 20 <= eval_shifted.metadata["a"] <= 80
    assert 20 <= eval_shifted.metadata["b"] <= 80


def test_m12_shifted_profiles_use_expected_numeric_bands() -> None:
    train_prime = generate_examples(
        count=1,
        seed=1234,
        task_types=["quantity.direct"],
        profile="train_shifted_prime",
    )[0]
    in_distribution = generate_examples(
        count=1,
        seed=2234,
        task_types=["quantity.direct"],
        profile="eval_shifted_in_distribution",
    )[0]
    holdout = generate_examples(
        count=1,
        seed=3234,
        task_types=["quantity.direct"],
        profile="eval_shifted_holdout",
    )[0]
    far = generate_examples(
        count=1,
        seed=4234,
        task_types=["quantity.direct"],
        profile="eval_far_shifted",
    )[0]

    assert 21 <= train_prime.metadata["count"] <= 60
    assert 21 <= in_distribution.metadata["count"] <= 60
    assert 61 <= holdout.metadata["count"] <= 100
    assert 101 <= far.metadata["count"] <= 300


def test_m12_shifted_profiles_keep_sorting_short_lengths() -> None:
    for profile in (
        "train_shifted_prime",
        "eval_shifted_in_distribution",
        "eval_shifted_holdout",
        "eval_far_shifted",
    ):
        examples = generate_examples(
            count=100,
            seed=4400,
            task_types=TASK_PRESETS["sorting_short"].task_types,
            profile=profile,
        )

        assert max(len(example.metadata["numbers"]) for example in examples) <= 4
        assert min(len(example.metadata["numbers"]) for example in examples) >= 3


def test_eval_shifted_keeps_sorting_short_lengths() -> None:
    examples = generate_examples(
        count=100,
        seed=3400,
        task_types=TASK_PRESETS["sorting_short"].task_types,
        profile="eval_shifted",
    )

    assert max(len(example.metadata["numbers"]) for example in examples) <= 4
    assert min(len(example.metadata["numbers"]) for example in examples) >= 3


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


def test_digit_spaced_format_spaces_numbers_but_keeps_case_prefix() -> None:
    example = TrainingExample(
        id="arithmetic.add:00000000",
        task_type="arithmetic.add",
        prompt="case 12. Add 53 + 43?",
        answer="96",
        metadata={"a": 53, "b": 43, "operation": "addition"},
    )

    formatted = apply_answer_format(example, "digit_spaced")

    assert formatted.prompt == "case 12. Add 5 3 + 4 3?"
    assert formatted.answer == "9 6"
    assert formatted.metadata["answer_format"] == "digit_spaced"
    assert formatted.metadata["original_prompt"] == example.prompt
    assert formatted.metadata["original_answer"] == example.answer


def test_scratchpad_format_addition_reports_digit_steps() -> None:
    example = TrainingExample(
        id="arithmetic.add:00000000",
        task_type="arithmetic.add",
        prompt="Add 53 + 43?",
        answer="96",
        metadata={"a": 53, "b": 43, "operation": "addition"},
    )

    formatted = apply_answer_format(example, "scratchpad")

    assert formatted.answer == "ones: 3 + 3 = 6\ntens: 5 + 4 = 9\nanswer: 96"
    assert formatted.metadata["answer_format"] == "scratchpad"


def test_scratchpad_format_missing_addend_reports_missing_step() -> None:
    example = TrainingExample(
        id="arithmetic.missing_addend:00000000",
        task_type="arithmetic.missing_addend",
        prompt="5 + ? = 17. What is missing?",
        answer="12",
        metadata={"a": 5, "missing": 12, "total": 17},
    )

    formatted = apply_answer_format(example, "scratchpad")

    assert formatted.answer == (
        "known: 5\ntarget: 17\nmissing: 17 - 5 = 12\nanswer: 12"
    )


def test_scratchpad_format_double_step_reports_two_steps() -> None:
    example = TrainingExample(
        id="arithmetic.double_step:00000000",
        task_type="arithmetic.double_step",
        prompt="10 + 7 - 4",
        answer="13",
        metadata={"a": 10, "b": 7, "c": 4, "operation": "add_then_subtract"},
    )

    formatted = apply_answer_format(example, "scratchpad")

    assert formatted.answer == "step 1: 10 + 7 = 17\nstep 2: 17 - 4 = 13\nanswer: 13"


def test_scratchpad_format_sorting_reports_selection_steps() -> None:
    example = TrainingExample(
        id="sorting.ascending:00000000",
        task_type="sorting.ascending",
        prompt="Sort ascending: 92, 60, 85.",
        answer="60, 85, 92",
        metadata={"numbers": [92, 60, 85], "operation": "sort_ascending"},
    )

    formatted = apply_answer_format(example, "scratchpad")

    assert formatted.answer == (
        "numbers: 92, 60, 85\n"
        "step 1: smallest is 60\n"
        "remaining: 92, 85\n"
        "step 2: smallest is 85\n"
        "remaining: 92\n"
        "step 3: smallest is 92\n"
        "answer: 60, 85, 92"
    )


def test_scratchpad_format_state_change_reports_start_change_and_digits() -> None:
    example = TrainingExample(
        id="state_change.add:00000000",
        task_type="state_change.add",
        prompt="Vasya had 52. Got 30.",
        answer="82",
        metadata={"start": 52, "delta": 30, "operation": "state_add"},
    )

    formatted = apply_answer_format(example, "scratchpad")

    assert formatted.answer == (
        "start: 52\nchange: +30\nones: 2 + 0 = 2\ntens: 5 + 3 = 8\nanswer: 82"
    )


def test_reversed_answer_format_outputs_reversed_digits_only() -> None:
    example = TrainingExample(
        id="arithmetic.add:00000000",
        task_type="arithmetic.add",
        prompt="Add 53 + 43?",
        answer="96",
        metadata={"a": 53, "b": 43, "operation": "addition"},
    )

    formatted = apply_answer_format(example, "reversed_answer")

    assert formatted.answer == "6 9"
    assert formatted.metadata["answer_format"] == "reversed_answer"


def test_canonical_numeric_addition_uses_lsd_first_carry_rows() -> None:
    example = TrainingExample(
        id="arithmetic.add:00000000",
        task_type="arithmetic.add",
        prompt="Add 71 + 63?",
        answer="134",
        metadata={"a": 71, "b": 63, "operation": "addition"},
    )

    formatted = apply_answer_format(example, "canonical_numeric")

    assert formatted.answer == (
        "OP ADD\nA 7 1\nB 6 3\nP0 1 3 C0 -> S4 C0\nP1 7 6 C0 -> S3 C1\nOUT 1 3 4"
    )
    assert formatted.metadata["answer_format"] == "canonical_numeric"


def test_canonical_numeric_subtraction_uses_borrow_rows() -> None:
    example = TrainingExample(
        id="arithmetic.subtract:00000000",
        task_type="arithmetic.subtract",
        prompt="52 - 18",
        answer="34",
        metadata={"a": 52, "b": 18, "operation": "subtraction"},
    )

    formatted = apply_answer_format(example, "canonical_numeric")

    assert formatted.answer == (
        "OP SUB\nA 5 2\nB 1 8\nP0 2 8 B0 -> S4 B1\nP1 5 1 B1 -> S3 B0\nOUT 3 4"
    )


def test_canonical_numeric_missing_addend_uses_subtraction() -> None:
    example = TrainingExample(
        id="arithmetic.missing_addend:00000000",
        task_type="arithmetic.missing_addend",
        prompt="49 + blank = 70",
        answer="21",
        metadata={"a": 49, "missing": 21, "total": 70},
    )

    formatted = apply_answer_format(example, "canonical_numeric")

    assert formatted.answer == (
        "OP MISS_ADD\n"
        "KNOWN 4 9\n"
        "TARGET 7 0\n"
        "AS SUB TARGET KNOWN\n"
        "P0 0 9 B0 -> S1 B1\n"
        "P1 7 4 B1 -> S2 B0\n"
        "OUT 2 1"
    )


def test_canonical_numeric_double_step_reports_mid_and_out() -> None:
    example = TrainingExample(
        id="arithmetic.double_step:00000000",
        task_type="arithmetic.double_step",
        prompt="45 + 49 - 42",
        answer="52",
        metadata={"a": 45, "b": 49, "c": 42, "operation": "add_then_subtract"},
    )

    formatted = apply_answer_format(example, "canonical_numeric")

    assert "OP DOUBLE" in formatted.answer
    assert "STEP1 ADD" in formatted.answer
    assert "MID 9 4" in formatted.answer
    assert "STEP2 SUB" in formatted.answer
    assert formatted.answer.endswith("OUT 5 2")


def test_canonical_numeric_compare_sum_uses_both_additions() -> None:
    example = TrainingExample(
        id="arithmetic.compare_sum:00000000",
        task_type="arithmetic.compare_sum",
        prompt="Compare 33 + 50 and 33 + 46",
        answer="83",
        metadata={"a": 33, "b": 50, "c": 33, "d": 46, "left": 83, "right": 79},
    )

    formatted = apply_answer_format(example, "canonical_numeric")

    assert "OP COMP_SUM" in formatted.answer
    assert "LEFT_OUT 8 3" in formatted.answer
    assert "RIGHT_OUT 7 9" in formatted.answer
    assert "COMPARE 8 3 > 7 9" in formatted.answer
    assert formatted.answer.endswith("OUT 8 3")


def test_canonical_numeric_state_change_add() -> None:
    example = TrainingExample(
        id="state_change.add:00000000",
        task_type="state_change.add",
        prompt="Vasya had 52. Got 30.",
        answer="82",
        metadata={"start": 52, "delta": 30, "operation": "state_add"},
    )

    formatted = apply_answer_format(example, "canonical_numeric")

    assert formatted.answer == (
        "OP STATE_ADD\n"
        "SUBJ SAME\n"
        "OBJ SAME\n"
        "START 5 2\n"
        "CHANGE 3 0\n"
        "P0 2 0 C0 -> S2 C0\n"
        "P1 5 3 C0 -> S8 C0\n"
        "OUT 8 2"
    )


def test_canonical_numeric_sorting_uses_compact_min_steps() -> None:
    example = TrainingExample(
        id="sorting.ascending:00000000",
        task_type="sorting.ascending",
        prompt="Sort ascending: 26, 34, 27, 78.",
        answer="26, 27, 34, 78",
        metadata={"numbers": [26, 34, 27, 78], "operation": "sort_ascending"},
    )

    formatted = apply_answer_format(example, "canonical_numeric")

    assert formatted.answer == (
        "OP SORT_ASC\n"
        "N 2 6 | 3 4 | 2 7 | 7 8\n"
        "S0 MIN 2 6\n"
        "S1 MIN 2 7\n"
        "S2 MIN 3 4\n"
        "S3 MIN 7 8\n"
        "OUT 26, 27, 34, 78"
    )


def test_canonical_numeric_quantity_direct_copy() -> None:
    example = TrainingExample(
        id="quantity.direct:00000000",
        task_type="quantity.direct",
        prompt="Masha has 73 apples.",
        answer="73",
        metadata={"count": 73, "operation": "known"},
    )

    formatted = apply_answer_format(example, "canonical_numeric")

    assert formatted.answer == ("OP COPY_QTY\nSUBJ SAME\nOBJ SAME\nN 7 3\nOUT 7 3")


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
        assert {"a", "b", "c", "d"}.issubset(example.metadata)
        assert example.metadata["left"] == example.metadata["a"] + example.metadata["b"]
        assert (
            example.metadata["right"] == example.metadata["c"] + example.metadata["d"]
        )
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


def test_task_preset_registry_contains_required_presets() -> None:
    assert {
        "arithmetic",
        "quantity_direct",
        "sorting_short",
        "state_change",
        "digit_add_carry",
        "digit_sub_borrow",
        "add_2digit_no_carry",
        "add_2digit_with_carry",
        "sub_2digit_no_borrow",
        "sub_2digit_with_borrow",
        "missing_addend_simple",
        "compare_sum_simple",
        "double_step_simple",
    }.issubset(TASK_PRESETS)
    assert TASK_PRESETS["quantity_direct"].task_types == (
        "quantity.direct",
        "quantity.location_direct",
        "quantity.known_zero",
    )
    assert TASK_PRESETS["sorting_short"].default_train_profile == "train_short"
    assert TASK_PRESETS["sorting_short"].default_eval_profile == "eval_short"


def test_resolve_task_selection_expands_task_preset() -> None:
    task_types, task_preset = resolve_task_selection(
        task_preset="arithmetic",
        task_types=None,
    )

    assert task_preset == "arithmetic"
    assert task_types == list(TASK_PRESETS["arithmetic"].task_types)


def test_resolve_task_selection_rejects_preset_with_task_type() -> None:
    try:
        resolve_task_selection(
            task_preset="arithmetic",
            task_types=["arithmetic.add"],
        )
    except ValueError as error:
        assert str(error) == "Cannot use --task-preset together with --task-type."
    else:
        raise AssertionError("Expected ValueError")


def test_resolve_task_selection_rejects_unknown_preset() -> None:
    try:
        resolve_task_selection(task_preset="foo", task_types=None)
    except ValueError as error:
        message = str(error)
        assert "Unknown task preset: foo. Available presets:" in message
        assert "arithmetic" in message
        assert "digit_add_carry" in message
        assert "double_step_simple" in message
    else:
        raise AssertionError("Expected ValueError")


def test_generate_jsonl_accepts_task_preset_metadata(tmp_path: Path) -> None:
    output_path = tmp_path / "quantity_direct.jsonl"
    task_types = list(TASK_PRESETS["quantity_direct"].task_types)

    result = generate_jsonl(
        output_path=output_path,
        count=12,
        seed=3100,
        task_types=task_types,
        task_preset="quantity_direct",
    )
    examples = read_jsonl(output_path)

    assert result["task_preset"] == "quantity_direct"
    assert result["answer_format"] == "normal_answer"
    assert result["task_types"] == task_types
    assert {example["task_type"] for example in examples}.issubset(set(task_types))


def test_generate_data_split_accepts_task_preset_metadata(tmp_path: Path) -> None:
    output_dir = tmp_path / "arithmetic"
    task_types = list(TASK_PRESETS["arithmetic"].task_types)

    result = generate_data_split(
        output_dir=output_dir,
        train_count=20,
        eval_count=15,
        train_seed=3200,
        eval_seed=4200,
        task_types=task_types,
        task_preset="arithmetic",
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert result["task_preset"] == "arithmetic"
    assert result["manifest"]["task_preset"] == "arithmetic"
    assert result["answer_format"] == "normal_answer"
    assert manifest["task_preset"] == "arithmetic"
    assert manifest["answer_format"] == "normal_answer"
    assert manifest["task_types"] == task_types


def test_each_task_preset_only_produces_allowed_task_types() -> None:
    for preset in TASK_PRESETS.values():
        examples = generate_examples(
            count=80,
            seed=9100,
            task_types=preset.task_types,
            profile=preset.default_profile,
        )

        assert {example.task_type for example in examples}.issubset(
            set(preset.task_types)
        )


def test_sorting_short_uses_only_sorting_and_short_lengths() -> None:
    short_examples = generate_examples(
        count=100,
        seed=3400,
        task_types=TASK_PRESETS["sorting_short"].task_types,
        profile="eval_short",
    )
    normal_examples = generate_examples(
        count=100,
        seed=3400,
        task_types=TASK_PRESETS["sorting_short"].task_types,
        profile="eval",
    )

    assert {example.task_type for example in short_examples}.issubset(
        {"sorting.ascending", "sorting.descending"}
    )
    assert max(len(example.metadata["numbers"]) for example in short_examples) <= 4
    assert min(len(example.metadata["numbers"]) for example in short_examples) >= 3
    assert min(len(example.metadata["numbers"]) for example in normal_examples) >= 5


def test_generate_jsonl_applies_answer_format(tmp_path: Path) -> None:
    output_path = tmp_path / "digit_spaced.jsonl"

    result = generate_jsonl(
        output_path=output_path,
        count=5,
        seed=1234,
        task_types=["arithmetic.add"],
        answer_format="digit_spaced",
    )
    examples = read_jsonl(output_path)

    assert result["answer_format"] == "digit_spaced"
    assert {example["metadata"]["answer_format"] for example in examples} == {
        "digit_spaced"
    }
    assert all("original_answer" in example["metadata"] for example in examples)


def test_generate_data_split_manifest_records_answer_format(tmp_path: Path) -> None:
    output_dir = tmp_path / "scratchpad_split"

    result = generate_data_split(
        output_dir=output_dir,
        train_count=12,
        eval_count=9,
        train_seed=1000,
        eval_seed=2000,
        task_types=["arithmetic.add", "arithmetic.subtract", "sorting.ascending"],
        answer_format="scratchpad",
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    train_examples = read_jsonl(output_dir / "train.jsonl")

    assert result["answer_format"] == "scratchpad"
    assert manifest["answer_format"] == "scratchpad"
    assert {example["metadata"]["answer_format"] for example in train_examples} == {
        "scratchpad"
    }


def test_generate_range_ablation_writes_three_disjoint_splits(tmp_path: Path) -> None:
    output_dir = tmp_path / "range_ablation"

    result = generate_range_ablation(
        output_dir=output_dir,
        train_count=12,
        eval_same_count=9,
        eval_shifted_count=8,
        train_seed=1000,
        eval_same_seed=2000,
        eval_shifted_seed=3000,
        task_types=["arithmetic.add", "arithmetic.subtract"],
        task_preset="arithmetic",
        answer_format="canonical_numeric",
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    train = read_jsonl(output_dir / "train_same.jsonl")
    eval_same = read_jsonl(output_dir / "eval_same.jsonl")
    eval_shifted = read_jsonl(output_dir / "eval_shifted.jsonl")

    assert result["answer_format"] == "canonical_numeric"
    assert len(train) == 12
    assert len(eval_same) == 9
    assert len(eval_shifted) == 8
    assert manifest["splits"]["train_same"]["profile"] == "train_same"
    assert manifest["splits"]["eval_same"]["profile"] == "eval_same"
    assert manifest["splits"]["eval_shifted"]["profile"] == "eval_shifted"
    assert manifest["quality_checks"]["no_train_eval_same_intersection"] is True
    assert manifest["quality_checks"]["no_train_eval_shifted_intersection"] is True
    assert manifest["quality_checks"]["no_eval_same_shifted_intersection"] is True
    assert {example["metadata"]["answer_format"] for example in train} == {
        "canonical_numeric"
    }


def test_generate_range_primed_writes_manifest_and_disjoint_splits(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "m12"

    result = generate_range_primed(
        output_dir=output_dir,
        train_count=20,
        eval_same_count=8,
        eval_shifted_in_distribution_count=7,
        eval_shifted_holdout_count=6,
        eval_far_shifted_count=5,
        train_same_seed=1000,
        train_shifted_prime_seed=1100,
        eval_same_seed=2000,
        eval_shifted_in_distribution_seed=2100,
        eval_shifted_holdout_seed=2200,
        eval_far_shifted_seed=2300,
        shifted_prime_fraction=0.25,
        task_types=["arithmetic.add", "arithmetic.subtract"],
        task_preset="arithmetic",
        answer_format="scratchpad",
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert result["answer_format"] == "scratchpad"
    assert result["shifted_prime_fraction"] == 0.25
    assert len(read_jsonl(output_dir / "train.jsonl")) == 20
    assert len(read_jsonl(output_dir / "train_same.jsonl")) == 15
    assert len(read_jsonl(output_dir / "train_shifted_prime.jsonl")) == 5
    assert (output_dir / "eval_shifted_in_distribution.jsonl").exists()
    assert (output_dir / "eval_shifted_holdout.jsonl").exists()
    assert (output_dir / "eval_far_shifted.jsonl").exists()
    assert manifest["kind"] == "range_primed"
    assert manifest["answer_format"] == "scratchpad"
    assert manifest["profiles"]["train_shifted_prime"] == "train_shifted_prime"
    assert manifest["seeds"]["eval_far_shifted"] == 2300
    assert manifest["splits"]["train_shifted_prime"]["task_type_counts"]
    assert manifest["splits"]["eval_far_shifted"]["numeric_range_summary"]["count"] > 0
    assert manifest["quality_checks"]["all_prompt_intersections_zero"] is True
    assert (
        manifest["quality_checks"]["no_train_prime_eval_prompt_intersections"] is True
    )
    assert set(manifest["quality_checks"]["numeric_overlap_summaries"]) == {
        "eval_same",
        "eval_shifted_in_distribution",
        "eval_shifted_holdout",
        "eval_far_shifted",
    }


def test_number_format_helpers_format_roles_and_places() -> None:
    assert digits_of_number(134) == [1, 3, 4]
    assert place_names_for_digits(1) == ["U"]
    assert place_names_for_digits(2) == ["T", "U"]
    assert place_names_for_digits(3) == ["H", "T", "U"]
    assert format_role_number("A", 71) == "A_T 7 A_U 1"
    assert format_role_number("OUT", 134) == "OUT_H 1 OUT_T 3 OUT_U 4"
    assert format_plain_digit_number(134) == "1 3 4"


def test_place_role_numeric_addition_transforms_prompt_and_answer() -> None:
    example = TrainingExample(
        id="arithmetic.add:00000000",
        task_type="arithmetic.add",
        prompt="case 12. ????? ????? ????? 71 ? 63.",
        answer="134",
        metadata={"a": 71, "b": 63, "operation": "addition"},
    )

    formatted = apply_answer_format(example, "place_role_numeric")

    assert formatted.prompt == ("case 12. ????? ????? ????? A_T 7 A_U 1 ? B_T 6 B_U 3.")
    assert formatted.answer == (
        "OP ADD\n"
        "A_T 7 A_U 1\n"
        "B_T 6 B_U 3\n"
        "P_U A_U 1 B_U 3 C_IN 0 -> S_U 4 C_OUT 0\n"
        "P_T A_T 7 B_T 6 C_IN 0 -> S_T 3 C_OUT 1\n"
        "OUT_H 1 OUT_T 3 OUT_U 4"
    )
    assert formatted.metadata["answer_format"] == "place_role_numeric"
    assert formatted.metadata["original_prompt"] == example.prompt


def test_place_role_numeric_quantity_direct_tags_prompt_number() -> None:
    example = TrainingExample(
        id="quantity.direct:00000000",
        task_type="quantity.direct",
        prompt="? ???? ???? 73 ???????. ??????? ???????? ???? ? ?????",
        answer="73",
        metadata={"count": 73, "operation": "known"},
    )

    formatted = apply_answer_format(example, "place_role_numeric")

    assert "N_T 7 N_U 3 ???????" in formatted.prompt
    assert formatted.answer == (
        "OP COPY_QTY\nSUBJ SAME\nOBJ SAME\nN_T 7 N_U 3\nOUT_T 7 OUT_U 3"
    )


def test_place_role_numeric_state_change_add_tags_prompt_numbers() -> None:
    example = TrainingExample(
        id="state_change.add:00000000",
        task_type="state_change.add",
        prompt=(
            "? ???? ???? 52 ?????. ???? ???? ??? 30 ??????. "
            "??????? ?????? ????? ? ?????"
        ),
        answer="82",
        metadata={"start": 52, "delta": 30, "operation": "state_add"},
    )

    formatted = apply_answer_format(example, "place_role_numeric")

    assert "START_T 5 START_U 2" in formatted.prompt
    assert "CHANGE_T 3 CHANGE_U 0" in formatted.prompt
    assert formatted.answer.endswith("OUT_T 8 OUT_U 2")


def test_place_role_numeric_sorting_keeps_normal_out_list() -> None:
    example = TrainingExample(
        id="sorting.ascending:00000000",
        task_type="sorting.ascending",
        prompt="?????? ????? ?? ???????? ? ????????: 26, 34, 27, 78.",
        answer="26, 27, 34, 78",
        metadata={"numbers": [26, 34, 27, 78], "operation": "sort_ascending"},
    )

    formatted = apply_answer_format(example, "place_role_numeric")

    assert formatted.prompt == (
        "?????? ????? ?? ???????? ? ????????: "
        "N0_T 2 N0_U 6, N1_T 3 N1_U 4, "
        "N2_T 2 N2_U 7, N3_T 7 N3_U 8."
    )
    assert "S0 MIN N0_T 2 N0_U 6" in formatted.answer
    assert formatted.answer.endswith("OUT 26, 27, 34, 78")


def test_r2l_numeric_outputs_reversed_work_and_normal_final_answer() -> None:
    example = TrainingExample(
        id="arithmetic.add:00000000",
        task_type="arithmetic.add",
        prompt="case 12. Add 53 + 43?",
        answer="96",
        metadata={"a": 53, "b": 43, "operation": "addition"},
    )

    formatted = apply_answer_format(example, "r2l_numeric")

    assert formatted.prompt == "case 12. Add 5 3 + 4 3?"
    assert formatted.answer == "REV 6 9\nanswer: 96"
    assert formatted.metadata["answer_format"] == "r2l_numeric"
    assert formatted.metadata["original_answer"] == "96"


def test_r2l_numeric_keeps_non_decimal_answers_final_answer_scored() -> None:
    example = TrainingExample(
        id="sorting.ascending:00000000",
        task_type="sorting.ascending",
        prompt="Sort 92, 60, 85.",
        answer="60, 85, 92",
        metadata={"numbers": [92, 60, 85]},
    )

    formatted = apply_answer_format(example, "r2l_numeric")

    assert formatted.prompt == "Sort 9 2, 6 0, 8 5."
    assert formatted.answer == "answer: 60, 85, 92"


def test_rtl_numeric_outputs_lsd_first_work_and_normal_final_answer() -> None:
    example = TrainingExample(
        id="arithmetic.add_2digit_composed:00000000",
        task_type="arithmetic.add_2digit_composed",
        prompt="ADD2_COMPOSED 84 + 65",
        answer="149",
        metadata={"a": 84, "b": 65},
    )

    formatted = apply_answer_format(example, "rtl_numeric")

    assert formatted.answer == "OUT_RTL 9 4 1\nFINAL 149"
    assert formatted.metadata["answer_format"] == "rtl_numeric"


def test_compact_lsd_trace_formats_addition_with_final_carry() -> None:
    example = TrainingExample(
        id="arithmetic.add_2digit_composed:00000000",
        task_type="arithmetic.add_2digit_composed",
        prompt="ADD2_COMPOSED 84 + 65",
        answer="149",
        metadata={"a": 84, "b": 65},
    )

    formatted = apply_answer_format(example, "compact_lsd_trace")

    assert formatted.answer == (
        "OP ADD_RTL\n"
        "U 4 5 C0 -> 9 C0\n"
        "T 8 6 C0 -> 4 C1\n"
        "H C1 -> 1\n"
        "OUT_RTL 9 4 1\n"
        "FINAL 149"
    )
    assert formatted.metadata["answer_format"] == "compact_lsd_trace"


def test_compact_lsd_trace_formats_subtraction_with_borrow() -> None:
    example = TrainingExample(
        id="arithmetic.sub_2digit_composed:00000000",
        task_type="arithmetic.sub_2digit_composed",
        prompt="SUB2_COMPOSED 52 - 18",
        answer="34",
        metadata={"a": 52, "b": 18},
    )

    formatted = apply_answer_format(example, "compact_lsd_trace")

    assert formatted.answer == (
        "OP SUB_RTL\nU 2 8 B0 -> 4 B1\nT 5 1 B1 -> 3 B0\nOUT_RTL 4 3\nFINAL 34"
    )


def test_compact_digit_trace_formats_2digit_addition() -> None:
    example = TrainingExample(
        id="arithmetic.add_2digit_with_carry:00000000",
        task_type="arithmetic.add_2digit_with_carry",
        prompt="ADD2 71 + 63",
        answer="134",
        metadata={"a": 71, "b": 63, "operation": "add_2digit_with_carry"},
    )

    formatted = apply_answer_format(example, "compact_digit_trace")

    assert (
        formatted.answer
        == "OP ADD\nA 7 1\nB 6 3\nU 1 3 0 -> 4 0\nT 7 6 0 -> 3 1\nOUT 134"
    )
    assert formatted.metadata["answer_format"] == "compact_digit_trace"


def test_compact_digit_trace_formats_digit_sub_borrow() -> None:
    example = TrainingExample(
        id="arithmetic.digit_sub_borrow:00000000",
        task_type="arithmetic.digit_sub_borrow",
        prompt="DIGIT_SUB a=2 b=8 borrow=0",
        answer="S 4 B 1",
        metadata={
            "a": 2,
            "b": 8,
            "borrow_in": 0,
            "diff_digit": 4,
            "borrow_out": 1,
        },
    )

    formatted = apply_answer_format(example, "compact_digit_trace")

    assert formatted.answer == "S 4 B 1"


def test_arithmetic_primitive_profiles_split_digit_combinations() -> None:
    train = generate_examples(
        count=200,
        seed=6100,
        task_types=["arithmetic.digit_add_carry"],
        profile="train_same",
    )
    holdout = generate_examples(
        count=100,
        seed=6200,
        task_types=["arithmetic.digit_add_carry"],
        profile="eval_holdout_digit_combinations",
    )

    assert {example.metadata["holdout_digit_combo"] for example in train} == {False}
    assert {example.metadata["holdout_digit_combo"] for example in holdout} == {True}
    assert len({example.metadata["digit_combo_key"] for example in train}) > 20
    assert len({example.metadata["digit_combo_key"] for example in holdout}) > 10


def test_generate_arithmetic_primitive_split_writes_digit_holdout_manifest(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "m13_digit_add"

    result = generate_arithmetic_primitive_split(
        output_dir=output_dir,
        train_count=80,
        eval_same_count=40,
        eval_shifted_in_distribution_count=40,
        eval_holdout_digit_combinations_count=30,
        eval_far_range_count=30,
        train_seed=1000,
        eval_same_seed=2000,
        eval_shifted_in_distribution_seed=3000,
        eval_holdout_digit_combinations_seed=4000,
        eval_far_range_seed=5000,
        task_types=["arithmetic.digit_add_carry"],
        task_preset="digit_add_carry",
        answer_format="compact_digit_trace",
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert result["answer_format"] == "compact_digit_trace"
    assert len(read_jsonl(output_dir / "train.jsonl")) == 80
    assert len(read_jsonl(output_dir / "eval_holdout_digit_combinations.jsonl")) == 30
    assert (output_dir / "eval_far_range.jsonl").exists()
    assert manifest["kind"] == "arithmetic_primitive"
    assert manifest["quality_checks"]["all_prompt_intersections_zero"] is True
    assert (
        manifest["splits"]["train_same"]["digit_combination_coverage"][
            "unique_digit_combo_count"
        ]
        > 0
    )
    assert (
        manifest["quality_checks"]["digit_combo_overlaps_with_train"][
            "eval_holdout_digit_combinations"
        ]["eval_unseen_digit_combo_fraction"]
        == 1.0
    )


def test_m14_digit_table_task_types_are_registered() -> None:
    task_types = {
        "arithmetic.digit_add_no_carry",
        "arithmetic.digit_add_with_carry_input",
        "arithmetic.digit_add_carry_out",
        "arithmetic.digit_sub_no_borrow",
        "arithmetic.digit_sub_with_borrow_input",
        "arithmetic.digit_sub_borrow_out",
        "arithmetic.add_2digit_composed",
        "arithmetic.sub_2digit_composed",
    }

    for task_type in task_types:
        examples = generate_examples(count=1, seed=7100, task_types=[task_type])

        assert examples[0].task_type == task_type
        assert examples[0].prompt
        assert examples[0].answer


def test_compact_digit_trace_formats_m14_composed_task_type() -> None:
    example = TrainingExample(
        id="arithmetic.add_2digit_composed:00000000",
        task_type="arithmetic.add_2digit_composed",
        prompt="ADD2_COMPOSED 71 + 63",
        answer="134",
        metadata={"a": 71, "b": 63, "operation": "add_2digit_composed"},
    )

    formatted = apply_answer_format(example, "compact_digit_trace")

    assert formatted.answer == (
        "OP ADD\nA 7 1\nB 6 3\nU 1 3 0 -> 4 0\nT 7 6 0 -> 3 1\nOUT 134"
    )


def test_generate_digit_table_curriculum_writes_coverage_manifest(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "m14"

    result = generate_digit_table_curriculum(
        output_dir=output_dir,
        seed=31000,
        digit_table_repeats=1,
        eval_digit_table_repeats=1,
        composition_count=120,
        eval_composition_count=60,
        answer_format="compact_digit_trace",
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    expected_files = {
        "train_digit_table.jsonl",
        "eval_digit_table_seen.jsonl",
        "eval_digit_table_holdout.jsonl",
        "train_2digit_composition.jsonl",
        "train_mixed.jsonl",
        "eval_2digit_same.jsonl",
        "eval_2digit_holdout_combo.jsonl",
        "eval_2digit_far.jsonl",
        "manifest.json",
    }

    assert result["answer_format"] == "compact_digit_trace"
    assert manifest["kind"] == "digit_table_curriculum"
    assert expected_files.issubset({path.name for path in output_dir.iterdir()})
    assert manifest["splits"]["train_digit_table"]["count"] == 400
    assert manifest["splits"]["train_2digit_composition"]["count"] == 120
    assert manifest["splits"]["train_mixed"]["count"] == 520
    assert manifest["quality_checks"]["all_prompt_intersections_zero"] is True

    coverage = manifest["splits"]["train_digit_table"]["digit_operation_coverage"]
    assert coverage["add_pair_count"] == 100
    assert coverage["sub_pair_count"] == 100
    assert coverage["carry_in_values"] == [0, 1]
    assert coverage["carry_out_values"] == [0, 1]
    assert coverage["borrow_in_values"] == [0, 1]
    assert coverage["borrow_out_values"] == [0, 1]

    holdout_overlap = manifest["quality_checks"]["composition_holdout_combo_overlap"]
    assert holdout_overlap["eval_unseen_digit_combo_count"] > 0
    assert holdout_overlap["eval_unseen_digit_combo_fraction"] > 0.0

    digit_table_overlap = manifest["quality_checks"][
        "composition_holdout_combos_seen_in_digit_table"
    ]
    assert digit_table_overlap["eval_overlap_fraction"] == 1.0
