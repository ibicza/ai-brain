from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_brain.data.generators import (
    GENERATOR_NAMES,
    GeneratorName,
    generate_example,
    generate_examples,
)
from ai_brain.data.schema import TrainingExample


def write_jsonl(path: Path, examples: Sequence[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="\n") as file:
        for example in examples:
            file.write(example.to_json_line())
            file.write("\n")


def generate_jsonl(
    *,
    output_path: Path,
    count: int,
    seed: int,
    task_types: Sequence[GeneratorName] | None = None,
) -> dict[str, Any]:
    examples = generate_examples(
        count=count,
        seed=seed,
        task_types=task_types,
    )

    write_jsonl(output_path, examples)

    return {
        "output_path": str(output_path),
        "count": count,
        "seed": seed,
        "task_types": list(task_types) if task_types is not None else "all",
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def build_dataset_stats(
    examples: Sequence[TrainingExample | dict[str, Any]],
    *,
    expected_task_types: Sequence[GeneratorName] | None = None,
) -> dict[str, Any]:
    expected = tuple(expected_task_types or GENERATOR_NAMES)
    task_type_counts = Counter(
        _get_example_field(example, "task_type") for example in examples
    )
    prompts = [_get_example_field(example, "prompt") for example in examples]
    unique_prompts = set(prompts)
    missing_task_types = [
        task_type for task_type in expected if task_type_counts.get(task_type, 0) == 0
    ]

    return {
        "count": len(examples),
        "task_type_counts": dict(sorted(task_type_counts.items())),
        "missing_task_types": missing_task_types,
        "all_task_types_present": not missing_task_types,
        "unique_prompt_count": len(unique_prompts),
        "duplicate_prompt_count": len(prompts) - len(unique_prompts),
    }


def dataset_stats(
    *,
    input_path: Path,
    expected_task_types: Sequence[GeneratorName] | None = None,
) -> dict[str, Any]:
    examples = read_jsonl(input_path)
    stats = build_dataset_stats(examples, expected_task_types=expected_task_types)

    return {
        "input_path": str(input_path),
        **stats,
    }


def generate_data_split(
    *,
    output_dir: Path,
    train_count: int,
    eval_count: int,
    train_seed: int,
    eval_seed: int,
    task_types: Sequence[GeneratorName] | None = None,
) -> dict[str, Any]:
    allowed_task_types = tuple(task_types or GENERATOR_NAMES)

    train_examples = _generate_examples_with_coverage(
        count=train_count,
        seed=train_seed,
        task_types=allowed_task_types,
    )
    train_prompts = {example.prompt for example in train_examples}
    eval_examples = _generate_examples_with_coverage(
        count=eval_count,
        seed=eval_seed,
        task_types=allowed_task_types,
        blocked_prompts=train_prompts,
    )

    train_path = output_dir / "train.jsonl"
    eval_path = output_dir / "eval.jsonl"
    manifest_path = output_dir / "manifest.json"

    write_jsonl(train_path, train_examples)
    write_jsonl(eval_path, eval_examples)

    prompt_intersection = sorted(
        {example.prompt for example in train_examples}
        & {example.prompt for example in eval_examples}
    )
    train_stats = build_dataset_stats(
        train_examples,
        expected_task_types=allowed_task_types,
    )
    eval_stats = build_dataset_stats(
        eval_examples,
        expected_task_types=allowed_task_types,
    )

    manifest = {
        "version": 1,
        "task_types": list(allowed_task_types),
        "splits": {
            "train": {
                "path": train_path.name,
                "count": train_count,
                "seed": train_seed,
                **train_stats,
            },
            "eval": {
                "path": eval_path.name,
                "count": eval_count,
                "seed": eval_seed,
                **eval_stats,
            },
        },
        "quality_checks": {
            "prompt_intersection_count": len(prompt_intersection),
            "prompt_intersection_sample": prompt_intersection[:10],
            "no_prompt_intersection": not prompt_intersection,
            "all_task_types_present": (
                train_stats["all_task_types_present"]
                and eval_stats["all_task_types_present"]
            ),
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return {
        "output_dir": str(output_dir),
        "train_path": str(train_path),
        "eval_path": str(eval_path),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def _generate_examples_with_coverage(
    *,
    count: int,
    seed: int,
    task_types: Sequence[GeneratorName],
    blocked_prompts: set[str] | None = None,
) -> list[TrainingExample]:
    if count < 0:
        raise ValueError("count must be non-negative")

    if not task_types:
        raise ValueError("task_types must not be empty")

    rng = random.Random(seed)
    covered_task_types = list(task_types)
    rng.shuffle(covered_task_types)
    scheduled_task_types = covered_task_types[: min(count, len(covered_task_types))]

    examples: list[TrainingExample] = []
    blocked = set(blocked_prompts or ())
    attempt_limit = max(1000, count * 100)
    attempts = 0

    while len(examples) < count:
        if attempts >= attempt_limit:
            raise RuntimeError(
                "Could not generate a prompt-disjoint dataset split "
                f"after {attempt_limit} attempts"
            )

        task_type = (
            scheduled_task_types[len(examples)]
            if len(examples) < len(scheduled_task_types)
            else None
        )
        example = (
            generate_example(rng, len(examples), task_types=[task_type])
            if task_type is not None
            else generate_example(rng, len(examples), task_types=task_types)
        )
        attempts += 1

        if example.prompt in blocked:
            continue

        examples.append(example)

    return examples


def _get_example_field(example: TrainingExample | dict[str, Any], field: str) -> Any:
    if isinstance(example, dict):
        return example[field]

    return getattr(example, field)
