from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_brain.data.answer_format import AnswerFormatName, apply_answer_format
from ai_brain.data.generators import (
    GENERATOR_NAMES,
    GenerationProfileName,
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
    profile: GenerationProfileName = "train",
    task_preset: str | None = None,
    answer_format: AnswerFormatName = "normal_answer",
) -> dict[str, Any]:
    examples = [
        apply_answer_format(example, answer_format)
        for example in generate_examples(
            count=count,
            seed=seed,
            task_types=task_types,
            profile=profile,
        )
    ]

    write_jsonl(output_path, examples)

    return {
        "output_path": str(output_path),
        "count": count,
        "seed": seed,
        "profile": profile,
        "task_preset": task_preset,
        "answer_format": answer_format,
        "task_types": list(task_types) if task_types is not None else "all",
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def build_dataset_stats(
    examples: Sequence[TrainingExample | dict[str, Any]],
    *,
    expected_task_types: Sequence[GeneratorName] | None = None,
    top_duplicate_limit: int = 20,
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
        "top_duplicate_prompts": _get_top_duplicate_prompts(
            examples,
            limit=top_duplicate_limit,
        ),
    }


def dataset_stats(
    *,
    input_path: Path,
    expected_task_types: Sequence[GeneratorName] | None = None,
    top_duplicate_limit: int = 20,
) -> dict[str, Any]:
    examples = read_jsonl(input_path)
    stats = build_dataset_stats(
        examples,
        expected_task_types=expected_task_types,
        top_duplicate_limit=top_duplicate_limit,
    )

    return {
        "input_path": str(input_path),
        **stats,
    }


def generate_range_ablation(
    *,
    output_dir: Path,
    train_count: int,
    eval_same_count: int,
    eval_shifted_count: int,
    train_seed: int,
    eval_same_seed: int,
    eval_shifted_seed: int,
    task_types: Sequence[GeneratorName] | None = None,
    train_profile: GenerationProfileName = "train_same",
    eval_same_profile: GenerationProfileName = "eval_same",
    eval_shifted_profile: GenerationProfileName = "eval_shifted",
    task_preset: str | None = None,
    enforce_unique_prompts: bool = True,
    answer_format: AnswerFormatName = "normal_answer",
) -> dict[str, Any]:
    allowed_task_types = tuple(task_types or GENERATOR_NAMES)

    train_examples = _generate_examples_with_coverage(
        count=train_count,
        seed=train_seed,
        task_types=allowed_task_types,
        split_name="train",
        profile=train_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
    )
    train_prompts = {example.prompt for example in train_examples}
    eval_same_examples = _generate_examples_with_coverage(
        count=eval_same_count,
        seed=eval_same_seed,
        task_types=allowed_task_types,
        split_name="eval",
        profile=eval_same_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
        blocked_prompts=train_prompts,
    )
    eval_same_prompts = {example.prompt for example in eval_same_examples}
    eval_shifted_examples = _generate_examples_with_coverage(
        count=eval_shifted_count,
        seed=eval_shifted_seed,
        task_types=allowed_task_types,
        split_name="eval",
        profile=eval_shifted_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
        blocked_prompts=train_prompts | eval_same_prompts,
    )

    train_path = output_dir / "train_same.jsonl"
    eval_same_path = output_dir / "eval_same.jsonl"
    eval_shifted_path = output_dir / "eval_shifted.jsonl"
    manifest_path = output_dir / "manifest.json"

    write_jsonl(train_path, train_examples)
    write_jsonl(eval_same_path, eval_same_examples)
    write_jsonl(eval_shifted_path, eval_shifted_examples)

    eval_shifted_prompts = {example.prompt for example in eval_shifted_examples}

    train_stats = build_dataset_stats(
        train_examples,
        expected_task_types=allowed_task_types,
    )
    eval_same_stats = build_dataset_stats(
        eval_same_examples,
        expected_task_types=allowed_task_types,
    )
    eval_shifted_stats = build_dataset_stats(
        eval_shifted_examples,
        expected_task_types=allowed_task_types,
    )

    train_eval_same_intersection = sorted(train_prompts & eval_same_prompts)
    train_eval_shifted_intersection = sorted(train_prompts & eval_shifted_prompts)
    eval_same_shifted_intersection = sorted(eval_same_prompts & eval_shifted_prompts)

    manifest = {
        "version": 1,
        "task_preset": task_preset,
        "answer_format": answer_format,
        "task_types": list(allowed_task_types),
        "splits": {
            "train_same": {
                "path": train_path.name,
                "count": train_count,
                "seed": train_seed,
                "profile": train_profile,
                **train_stats,
            },
            "eval_same": {
                "path": eval_same_path.name,
                "count": eval_same_count,
                "seed": eval_same_seed,
                "profile": eval_same_profile,
                **eval_same_stats,
            },
            "eval_shifted": {
                "path": eval_shifted_path.name,
                "count": eval_shifted_count,
                "seed": eval_shifted_seed,
                "profile": eval_shifted_profile,
                **eval_shifted_stats,
            },
        },
        "split_policy": {
            "name": "stable_prompt_hash_mod_2",
            "salt": _SPLIT_HASH_SALT,
            "enforce_unique_prompts": enforce_unique_prompts,
        },
        "quality_checks": {
            "train_eval_same_intersection_count": len(train_eval_same_intersection),
            "train_eval_shifted_intersection_count": len(
                train_eval_shifted_intersection
            ),
            "eval_same_shifted_intersection_count": len(eval_same_shifted_intersection),
            "train_eval_same_intersection_sample": train_eval_same_intersection[:10],
            "train_eval_shifted_intersection_sample": train_eval_shifted_intersection[
                :10
            ],
            "eval_same_shifted_intersection_sample": eval_same_shifted_intersection[
                :10
            ],
            "no_train_eval_same_intersection": not train_eval_same_intersection,
            "no_train_eval_shifted_intersection": not train_eval_shifted_intersection,
            "no_eval_same_shifted_intersection": not eval_same_shifted_intersection,
            "all_task_types_present": (
                train_stats["all_task_types_present"]
                and eval_same_stats["all_task_types_present"]
                and eval_shifted_stats["all_task_types_present"]
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
        "train_same_path": str(train_path),
        "eval_same_path": str(eval_same_path),
        "eval_shifted_path": str(eval_shifted_path),
        "manifest_path": str(manifest_path),
        "task_preset": task_preset,
        "answer_format": answer_format,
        "manifest": manifest,
    }


def generate_data_split(
    *,
    output_dir: Path,
    train_count: int,
    eval_count: int,
    train_seed: int,
    eval_seed: int,
    task_types: Sequence[GeneratorName] | None = None,
    train_profile: GenerationProfileName = "train",
    eval_profile: GenerationProfileName = "eval",
    task_preset: str | None = None,
    enforce_unique_prompts: bool = True,
    answer_format: AnswerFormatName = "normal_answer",
) -> dict[str, Any]:
    allowed_task_types = tuple(task_types or GENERATOR_NAMES)

    train_examples = _generate_examples_with_coverage(
        count=train_count,
        seed=train_seed,
        task_types=allowed_task_types,
        split_name="train",
        profile=train_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
    )
    eval_examples = _generate_examples_with_coverage(
        count=eval_count,
        seed=eval_seed,
        task_types=allowed_task_types,
        split_name="eval",
        profile=eval_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
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
        "task_preset": task_preset,
        "answer_format": answer_format,
        "task_types": list(allowed_task_types),
        "splits": {
            "train": {
                "path": train_path.name,
                "count": train_count,
                "seed": train_seed,
                "profile": train_profile,
                **train_stats,
            },
            "eval": {
                "path": eval_path.name,
                "count": eval_count,
                "seed": eval_seed,
                "profile": eval_profile,
                **eval_stats,
            },
        },
        "split_policy": {
            "name": "stable_prompt_hash_mod_2",
            "salt": _SPLIT_HASH_SALT,
            "enforce_unique_prompts": enforce_unique_prompts,
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
        "task_preset": task_preset,
        "answer_format": answer_format,
        "manifest": manifest,
    }


_SPLIT_HASH_SALT = "ai-brain-m46-v1"


def _generate_examples_with_coverage(
    *,
    count: int,
    seed: int,
    task_types: Sequence[GeneratorName],
    split_name: str | None = None,
    profile: GenerationProfileName = "train",
    enforce_unique_prompts: bool = True,
    answer_format: AnswerFormatName = "normal_answer",
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
    seen_prompts: set[str] = set()
    blocked = blocked_prompts or set()
    attempt_limit = max(10_000, count * 200)
    attempts = 0

    while len(examples) < count:
        if attempts >= attempt_limit:
            raise RuntimeError(
                "Could not generate enough unique prompts "
                f"for split={split_name!r}, profile={profile!r}: "
                f"accepted {len(examples)} of {count} examples "
                f"after {attempt_limit} attempts. "
                "Expand generator ranges or lower the requested count."
            )

        task_type = (
            scheduled_task_types[len(examples)]
            if len(examples) < len(scheduled_task_types)
            else None
        )
        example = (
            generate_example(
                rng,
                len(examples),
                task_types=[task_type],
                profile=profile,
            )
            if task_type is not None
            else generate_example(
                rng,
                len(examples),
                task_types=task_types,
                profile=profile,
            )
        )
        example = apply_answer_format(example, answer_format)
        attempts += 1

        if split_name is not None and not _prompt_belongs_to_split(
            example.prompt,
            split_name,
        ):
            continue

        if example.prompt in blocked:
            continue

        if enforce_unique_prompts and example.prompt in seen_prompts:
            continue

        seen_prompts.add(example.prompt)
        examples.append(example)

    return examples


def _get_top_duplicate_prompts(
    examples: Sequence[TrainingExample | dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    prompt_counts = Counter(
        _get_example_field(example, "prompt") for example in examples
    )
    prompt_task_types: dict[str, str] = {}
    for example in examples:
        prompt = _get_example_field(example, "prompt")
        prompt_task_types.setdefault(prompt, _get_example_field(example, "task_type"))

    return [
        {
            "prompt": prompt,
            "count": count,
            "task_type": prompt_task_types[prompt],
        }
        for prompt, count in prompt_counts.most_common(limit)
        if count > 1
    ]


def _prompt_belongs_to_split(prompt: str, split_name: str) -> bool:
    if split_name not in {"train", "eval"}:
        raise ValueError(f"Unknown split name: {split_name}")

    digest = hashlib.blake2b(
        f"{_SPLIT_HASH_SALT}\0{prompt}".encode(),
        digest_size=8,
    ).digest()
    bucket = int.from_bytes(digest, "big") % 2

    return (split_name == "train" and bucket == 0) or (
        split_name == "eval" and bucket == 1
    )


def _get_example_field(example: TrainingExample | dict[str, Any], field: str) -> Any:
    if isinstance(example, dict):
        return example[field]

    return getattr(example, field)
