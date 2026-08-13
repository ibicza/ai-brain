import json
from pathlib import Path

from ai_brain.data.generators import GENERATOR_NAMES, generate_examples
from ai_brain.data.schema import TrainingExample
from ai_brain.data.templates import CountedNoun, format_counted_noun
from ai_brain.data.writer import generate_jsonl


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
    first = generate_examples(count=20, seed=1234)
    second = generate_examples(count=20, seed=1234)

    assert [example.to_dict() for example in first] == [
        example.to_dict() for example in second
    ]


def test_generates_known_task_types() -> None:
    examples = generate_examples(count=200, seed=1234)

    generated_task_types = {example.task_type for example in examples}

    assert generated_task_types.issubset(set(GENERATOR_NAMES))
    assert "comparison.max" in generated_task_types
    assert "arithmetic.add" in generated_task_types
    assert "sequence.arithmetic_progression" in generated_task_types
    assert "epistemic.insufficient_info" in generated_task_types
    assert "epistemic.irrelevant_fact" in generated_task_types


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
    )

    assert format_counted_noun(1, noun) == "1 яблоко"
    assert format_counted_noun(2, noun) == "2 яблока"
    assert format_counted_noun(5, noun) == "5 яблок"
    assert format_counted_noun(11, noun) == "11 яблок"
    assert format_counted_noun(21, noun) == "21 яблоко"


def test_irrelevant_fact_has_different_subjects() -> None:
    example = generate_examples(
        count=1,
        seed=1234,
        task_types=["epistemic.irrelevant_fact"],
    )[0]

    assert example.task_type == "epistemic.irrelevant_fact"
    assert example.metadata["epistemic_state"] == "irrelevant_fact"
    assert example.metadata["fact_subject"] != example.metadata["question_subject"]
    assert example.answer.startswith("Недостаточно информации:")
