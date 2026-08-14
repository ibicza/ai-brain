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


def generate_range_primed(
    *,
    output_dir: Path,
    train_count: int,
    eval_same_count: int,
    eval_shifted_in_distribution_count: int,
    eval_shifted_holdout_count: int,
    eval_far_shifted_count: int,
    train_same_seed: int,
    train_shifted_prime_seed: int,
    eval_same_seed: int,
    eval_shifted_in_distribution_seed: int,
    eval_shifted_holdout_seed: int,
    eval_far_shifted_seed: int,
    shifted_prime_fraction: float,
    task_types: Sequence[GeneratorName] | None = None,
    train_same_profile: GenerationProfileName = "train_same",
    train_shifted_prime_profile: GenerationProfileName = "train_shifted_prime",
    eval_same_profile: GenerationProfileName = "eval_same",
    eval_shifted_in_distribution_profile: GenerationProfileName = (
        "eval_shifted_in_distribution"
    ),
    eval_shifted_holdout_profile: GenerationProfileName = "eval_shifted_holdout",
    eval_far_shifted_profile: GenerationProfileName = "eval_far_shifted",
    task_preset: str | None = None,
    enforce_unique_prompts: bool = True,
    answer_format: AnswerFormatName = "normal_answer",
) -> dict[str, Any]:
    if train_count < 0:
        raise ValueError("train_count must be non-negative")
    if not 0.0 <= shifted_prime_fraction <= 1.0:
        raise ValueError("shifted_prime_fraction must be between 0.0 and 1.0")

    allowed_task_types = tuple(task_types or GENERATOR_NAMES)
    train_shifted_prime_count = round(train_count * shifted_prime_fraction)
    train_same_count = train_count - train_shifted_prime_count

    train_same_examples = _generate_examples_with_coverage(
        count=train_same_count,
        seed=train_same_seed,
        task_types=allowed_task_types,
        split_name="train",
        profile=train_same_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
    )
    train_same_prompts = {example.prompt for example in train_same_examples}
    train_shifted_prime_examples = _generate_examples_with_coverage(
        count=train_shifted_prime_count,
        seed=train_shifted_prime_seed,
        task_types=allowed_task_types,
        split_name="train",
        profile=train_shifted_prime_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
        blocked_prompts=train_same_prompts,
    )

    train_examples = [*train_same_examples, *train_shifted_prime_examples]
    random.Random((train_same_seed << 16) ^ train_shifted_prime_seed).shuffle(
        train_examples
    )
    blocked_prompts = {example.prompt for example in train_examples}

    eval_same_examples = _generate_examples_with_coverage(
        count=eval_same_count,
        seed=eval_same_seed,
        task_types=allowed_task_types,
        split_name="eval",
        profile=eval_same_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
        blocked_prompts=blocked_prompts,
    )
    blocked_prompts |= {example.prompt for example in eval_same_examples}

    eval_shifted_in_distribution_examples = _generate_examples_with_coverage(
        count=eval_shifted_in_distribution_count,
        seed=eval_shifted_in_distribution_seed,
        task_types=allowed_task_types,
        split_name="eval",
        profile=eval_shifted_in_distribution_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
        blocked_prompts=blocked_prompts,
    )
    blocked_prompts |= {
        example.prompt for example in eval_shifted_in_distribution_examples
    }

    eval_shifted_holdout_examples = _generate_examples_with_coverage(
        count=eval_shifted_holdout_count,
        seed=eval_shifted_holdout_seed,
        task_types=allowed_task_types,
        split_name="eval",
        profile=eval_shifted_holdout_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
        blocked_prompts=blocked_prompts,
    )
    blocked_prompts |= {example.prompt for example in eval_shifted_holdout_examples}

    eval_far_shifted_examples = _generate_examples_with_coverage(
        count=eval_far_shifted_count,
        seed=eval_far_shifted_seed,
        task_types=allowed_task_types,
        split_name="eval",
        profile=eval_far_shifted_profile,
        enforce_unique_prompts=enforce_unique_prompts,
        answer_format=answer_format,
        blocked_prompts=blocked_prompts,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "train": output_dir / "train.jsonl",
        "train_same": output_dir / "train_same.jsonl",
        "train_shifted_prime": output_dir / "train_shifted_prime.jsonl",
        "eval_same": output_dir / "eval_same.jsonl",
        "eval_shifted_in_distribution": output_dir
        / "eval_shifted_in_distribution.jsonl",
        "eval_shifted_holdout": output_dir / "eval_shifted_holdout.jsonl",
        "eval_far_shifted": output_dir / "eval_far_shifted.jsonl",
    }
    split_examples = {
        "train": train_examples,
        "train_same": train_same_examples,
        "train_shifted_prime": train_shifted_prime_examples,
        "eval_same": eval_same_examples,
        "eval_shifted_in_distribution": eval_shifted_in_distribution_examples,
        "eval_shifted_holdout": eval_shifted_holdout_examples,
        "eval_far_shifted": eval_far_shifted_examples,
    }
    for split_name, examples in split_examples.items():
        write_jsonl(paths[split_name], examples)

    split_profiles = {
        "train": "mixed",
        "train_same": train_same_profile,
        "train_shifted_prime": train_shifted_prime_profile,
        "eval_same": eval_same_profile,
        "eval_shifted_in_distribution": eval_shifted_in_distribution_profile,
        "eval_shifted_holdout": eval_shifted_holdout_profile,
        "eval_far_shifted": eval_far_shifted_profile,
    }
    split_seeds = {
        "train": None,
        "train_same": train_same_seed,
        "train_shifted_prime": train_shifted_prime_seed,
        "eval_same": eval_same_seed,
        "eval_shifted_in_distribution": eval_shifted_in_distribution_seed,
        "eval_shifted_holdout": eval_shifted_holdout_seed,
        "eval_far_shifted": eval_far_shifted_seed,
    }

    split_prompt_sets = {
        split_name: {example.prompt for example in examples}
        for split_name, examples in split_examples.items()
    }
    prompt_intersections = _build_prompt_intersection_summaries(split_prompt_sets)
    eval_split_names = (
        "eval_same",
        "eval_shifted_in_distribution",
        "eval_shifted_holdout",
        "eval_far_shifted",
    )
    train_prime_eval_intersections = {
        split_name: prompt_intersections[
            _intersection_key("train_shifted_prime", split_name)
        ]
        for split_name in eval_split_names
    }

    numeric_summaries = {
        split_name: _build_numeric_range_summary(examples)
        for split_name, examples in split_examples.items()
    }
    numeric_overlap_summaries = {
        split_name: _build_numeric_overlap_summary(
            train_shifted_prime_examples,
            split_examples[split_name],
        )
        for split_name in eval_split_names
    }

    manifest = {
        "version": 1,
        "kind": "range_primed",
        "task_preset": task_preset,
        "answer_format": answer_format,
        "shifted_prime_fraction": shifted_prime_fraction,
        "task_types": list(allowed_task_types),
        "profiles": split_profiles,
        "seeds": split_seeds,
        "splits": {
            split_name: {
                "path": paths[split_name].name,
                "count": len(examples),
                "seed": split_seeds[split_name],
                "profile": split_profiles[split_name],
                "numeric_range_summary": numeric_summaries[split_name],
                **build_dataset_stats(
                    examples,
                    expected_task_types=allowed_task_types,
                ),
            }
            for split_name, examples in split_examples.items()
        },
        "split_policy": {
            "name": "stable_prompt_hash_mod_2",
            "salt": _SPLIT_HASH_SALT,
            "enforce_unique_prompts": enforce_unique_prompts,
        },
        "quality_checks": {
            "prompt_intersections": prompt_intersections,
            "train_prime_eval_prompt_intersections": train_prime_eval_intersections,
            "no_train_prime_eval_prompt_intersections": all(
                summary["count"] == 0
                for summary in train_prime_eval_intersections.values()
            ),
            "all_prompt_intersections_zero": all(
                summary["count"] == 0
                for pair_key, summary in prompt_intersections.items()
                if pair_key
                not in {
                    _intersection_key("train", "train_same"),
                    _intersection_key("train", "train_shifted_prime"),
                }
            ),
            "all_task_types_present": all(
                build_dataset_stats(
                    examples,
                    expected_task_types=allowed_task_types,
                )["all_task_types_present"]
                for examples in split_examples.values()
            ),
            "numeric_overlap_summaries": numeric_overlap_summaries,
        },
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return {
        "output_dir": str(output_dir),
        "train_path": str(paths["train"]),
        "train_same_path": str(paths["train_same"]),
        "train_shifted_prime_path": str(paths["train_shifted_prime"]),
        "eval_same_path": str(paths["eval_same"]),
        "eval_shifted_in_distribution_path": str(paths["eval_shifted_in_distribution"]),
        "eval_shifted_holdout_path": str(paths["eval_shifted_holdout"]),
        "eval_far_shifted_path": str(paths["eval_far_shifted"]),
        "manifest_path": str(manifest_path),
        "task_preset": task_preset,
        "answer_format": answer_format,
        "shifted_prime_fraction": shifted_prime_fraction,
        "manifest": manifest,
    }


def generate_digit_table_curriculum(
    *,
    output_dir: Path,
    seed: int = 31000,
    digit_table_repeats: int = 10,
    eval_digit_table_repeats: int = 2,
    composition_count: int = 8_000,
    eval_composition_count: int = 2_000,
    answer_format: AnswerFormatName = "compact_digit_trace",
) -> dict[str, Any]:
    if digit_table_repeats <= 0:
        raise ValueError("digit_table_repeats must be positive")
    if eval_digit_table_repeats <= 0:
        raise ValueError("eval_digit_table_repeats must be positive")
    if composition_count <= 0 or eval_composition_count <= 0:
        raise ValueError("composition counts must be positive")

    output_dir.mkdir(parents=True, exist_ok=True)
    split_seeds = {
        "train_digit_table": seed + 1,
        "eval_digit_table_seen": seed + 2,
        "eval_digit_table_holdout": seed + 3,
        "train_2digit_composition": seed + 4,
        "eval_2digit_same": seed + 5,
        "eval_2digit_holdout_combo": seed + 6,
        "eval_2digit_far": seed + 7,
        "train_mixed": seed + 8,
    }

    train_digit_table = _build_digit_table_examples(
        repeats=digit_table_repeats,
        seed=split_seeds["train_digit_table"],
        split_label="train_digit_table",
        answer_format=answer_format,
    )
    eval_digit_table_seen = _build_digit_table_examples(
        repeats=eval_digit_table_repeats,
        seed=split_seeds["eval_digit_table_seen"],
        split_label="eval_digit_table_seen",
        answer_format=answer_format,
    )
    eval_digit_table_holdout = _build_digit_table_examples(
        repeats=eval_digit_table_repeats,
        seed=split_seeds["eval_digit_table_holdout"],
        split_label="eval_digit_table_holdout",
        answer_format=answer_format,
    )

    train_2digit_composition = _build_2digit_composition_examples(
        count=composition_count,
        seed=split_seeds["train_2digit_composition"],
        split_label="train_2digit_composition",
        mode="train",
        answer_format=answer_format,
    )
    eval_2digit_same = _build_2digit_composition_examples(
        count=eval_composition_count,
        seed=split_seeds["eval_2digit_same"],
        split_label="eval_2digit_same",
        mode="same",
        blocked_prompts={example.prompt for example in train_2digit_composition},
        answer_format=answer_format,
    )
    blocked_eval_prompts = {example.prompt for example in train_2digit_composition}
    blocked_eval_prompts |= {example.prompt for example in eval_2digit_same}
    eval_2digit_holdout_combo = _build_2digit_composition_examples(
        count=eval_composition_count,
        seed=split_seeds["eval_2digit_holdout_combo"],
        split_label="eval_2digit_holdout_combo",
        mode="holdout_combo",
        blocked_prompts=blocked_eval_prompts,
        answer_format=answer_format,
    )
    blocked_eval_prompts |= {example.prompt for example in eval_2digit_holdout_combo}
    eval_2digit_far = _build_2digit_composition_examples(
        count=eval_composition_count,
        seed=split_seeds["eval_2digit_far"],
        split_label="eval_2digit_far",
        mode="far",
        blocked_prompts=blocked_eval_prompts,
        answer_format=answer_format,
    )

    train_mixed = [*train_digit_table, *train_2digit_composition]
    random.Random(split_seeds["train_mixed"]).shuffle(train_mixed)

    split_examples = {
        "train_digit_table": train_digit_table,
        "eval_digit_table_seen": eval_digit_table_seen,
        "eval_digit_table_holdout": eval_digit_table_holdout,
        "train_2digit_composition": train_2digit_composition,
        "train_mixed": train_mixed,
        "eval_2digit_same": eval_2digit_same,
        "eval_2digit_holdout_combo": eval_2digit_holdout_combo,
        "eval_2digit_far": eval_2digit_far,
    }
    paths = {
        split_name: output_dir / f"{split_name}.jsonl" for split_name in split_examples
    }
    for split_name, examples in split_examples.items():
        write_jsonl(paths[split_name], examples)

    prompt_sets = {
        split_name: {example.prompt for example in examples}
        for split_name, examples in split_examples.items()
    }
    prompt_intersections = _build_prompt_intersection_summaries(prompt_sets)
    digit_table_combos = _digit_combo_set(train_digit_table)
    composition_train_combos = _digit_combo_set(train_2digit_composition)

    manifest = {
        "version": 1,
        "kind": "digit_table_curriculum",
        "answer_format": answer_format,
        "seeds": split_seeds,
        "digit_table_repeats": digit_table_repeats,
        "eval_digit_table_repeats": eval_digit_table_repeats,
        "composition_count": composition_count,
        "eval_composition_count": eval_composition_count,
        "splits": {
            split_name: {
                "path": paths[split_name].name,
                "count": len(examples),
                "task_type_counts": dict(
                    sorted(Counter(example.task_type for example in examples).items())
                ),
                "digit_combination_coverage": _build_digit_combo_summary(examples),
                "digit_operation_coverage": _build_digit_operation_coverage(examples),
                "numeric_range_summary": _build_numeric_range_summary(examples),
                "unique_prompt_count": len({example.prompt for example in examples}),
                "duplicate_prompt_count": len(examples)
                - len({example.prompt for example in examples}),
            }
            for split_name, examples in split_examples.items()
        },
        "quality_checks": {
            "prompt_intersections": prompt_intersections,
            "all_prompt_intersections_zero": all(
                summary["count"] == 0
                for pair_key, summary in prompt_intersections.items()
                if pair_key
                not in {
                    _intersection_key("train_mixed", "train_digit_table"),
                    _intersection_key("train_mixed", "train_2digit_composition"),
                }
            ),
            "digit_table_combo_count": len(digit_table_combos),
            "composition_train_combo_count": len(composition_train_combos),
            "composition_holdout_combo_overlap": _build_digit_combo_overlap_summary(
                composition_train_combos,
                _digit_combo_set(eval_2digit_holdout_combo),
            ),
            "composition_holdout_combos_seen_in_digit_table": _build_digit_combo_overlap_summary(
                digit_table_combos,
                _digit_combo_set(eval_2digit_holdout_combo),
            ),
        },
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return {
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "answer_format": answer_format,
        "paths": {split_name: str(path) for split_name, path in paths.items()},
        "manifest": manifest,
    }


def generate_arithmetic_primitive_split(
    *,
    output_dir: Path,
    train_count: int,
    eval_same_count: int,
    eval_shifted_in_distribution_count: int,
    eval_holdout_digit_combinations_count: int,
    eval_far_range_count: int,
    train_seed: int,
    eval_same_seed: int,
    eval_shifted_in_distribution_seed: int,
    eval_holdout_digit_combinations_seed: int,
    eval_far_range_seed: int,
    task_types: Sequence[GeneratorName],
    task_preset: str | None = None,
    train_profile: GenerationProfileName = "train_same",
    eval_same_profile: GenerationProfileName = "eval_same",
    eval_shifted_in_distribution_profile: GenerationProfileName = (
        "eval_shifted_in_distribution"
    ),
    eval_holdout_digit_combinations_profile: GenerationProfileName = (
        "eval_holdout_digit_combinations"
    ),
    eval_far_range_profile: GenerationProfileName = "eval_far_range",
    enforce_unique_prompts: bool = True,
    answer_format: AnswerFormatName = "compact_digit_trace",
) -> dict[str, Any]:
    allowed_task_types = tuple(task_types)
    if not allowed_task_types:
        raise ValueError("task_types must not be empty")

    split_specs = {
        "train_same": {
            "count": train_count,
            "seed": train_seed,
            "profile": train_profile,
            "split_name": "train",
        },
        "eval_same": {
            "count": eval_same_count,
            "seed": eval_same_seed,
            "profile": eval_same_profile,
            "split_name": "eval",
        },
        "eval_shifted_in_distribution": {
            "count": eval_shifted_in_distribution_count,
            "seed": eval_shifted_in_distribution_seed,
            "profile": eval_shifted_in_distribution_profile,
            "split_name": "eval",
        },
        "eval_holdout_digit_combinations": {
            "count": eval_holdout_digit_combinations_count,
            "seed": eval_holdout_digit_combinations_seed,
            "profile": eval_holdout_digit_combinations_profile,
            "split_name": "eval",
        },
        "eval_far_range": {
            "count": eval_far_range_count,
            "seed": eval_far_range_seed,
            "profile": eval_far_range_profile,
            "split_name": "eval",
        },
    }

    split_examples: dict[str, list[TrainingExample]] = {}
    blocked_prompts: set[str] = set()
    for split_name, spec in split_specs.items():
        examples = _generate_examples_with_coverage(
            count=spec["count"],
            seed=spec["seed"],
            task_types=allowed_task_types,
            split_name=spec["split_name"],
            profile=spec["profile"],
            enforce_unique_prompts=enforce_unique_prompts,
            answer_format=answer_format,
            blocked_prompts=blocked_prompts,
        )
        split_examples[split_name] = examples
        blocked_prompts |= {example.prompt for example in examples}

    split_examples["train"] = list(split_examples["train_same"])
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        split_name: output_dir / f"{split_name}.jsonl" for split_name in split_examples
    }
    paths["train"] = output_dir / "train.jsonl"
    for split_name, examples in split_examples.items():
        write_jsonl(paths[split_name], examples)

    split_prompt_sets = {
        split_name: {example.prompt for example in examples}
        for split_name, examples in split_examples.items()
    }
    prompt_intersections = _build_prompt_intersection_summaries(split_prompt_sets)
    numeric_summaries = {
        split_name: _build_numeric_range_summary(examples)
        for split_name, examples in split_examples.items()
    }
    digit_coverage = {
        split_name: _build_digit_combo_summary(examples)
        for split_name, examples in split_examples.items()
    }
    eval_split_names = (
        "eval_same",
        "eval_shifted_in_distribution",
        "eval_holdout_digit_combinations",
        "eval_far_range",
    )
    train_digit_combos = _digit_combo_set(split_examples["train_same"])
    digit_combo_overlaps = {
        split_name: _build_digit_combo_overlap_summary(
            train_digit_combos,
            _digit_combo_set(split_examples[split_name]),
        )
        for split_name in eval_split_names
    }

    manifest = {
        "version": 1,
        "kind": "arithmetic_primitive",
        "task_preset": task_preset,
        "answer_format": answer_format,
        "task_types": list(allowed_task_types),
        "profiles": {
            split_name: spec["profile"] for split_name, spec in split_specs.items()
        }
        | {"train": "train_same"},
        "seeds": {split_name: spec["seed"] for split_name, spec in split_specs.items()}
        | {"train": train_seed},
        "splits": {
            split_name: {
                "path": paths[split_name].name,
                "count": len(examples),
                "seed": train_seed
                if split_name == "train"
                else split_specs[split_name]["seed"],
                "profile": "train_same"
                if split_name == "train"
                else split_specs[split_name]["profile"],
                "numeric_range_summary": numeric_summaries[split_name],
                "digit_combination_coverage": digit_coverage[split_name],
                **build_dataset_stats(
                    examples,
                    expected_task_types=allowed_task_types,
                ),
            }
            for split_name, examples in split_examples.items()
        },
        "quality_checks": {
            "prompt_intersections": prompt_intersections,
            "all_prompt_intersections_zero": all(
                summary["count"] == 0
                for pair_key, summary in prompt_intersections.items()
                if pair_key != _intersection_key("train", "train_same")
            ),
            "all_task_types_present": all(
                build_dataset_stats(
                    examples,
                    expected_task_types=allowed_task_types,
                )["all_task_types_present"]
                for split_name, examples in split_examples.items()
                if split_name != "train"
            ),
            "digit_combo_overlaps_with_train": digit_combo_overlaps,
        },
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return {
        "output_dir": str(output_dir),
        "train_path": str(paths["train"]),
        "train_same_path": str(paths["train_same"]),
        "eval_same_path": str(paths["eval_same"]),
        "eval_shifted_in_distribution_path": str(paths["eval_shifted_in_distribution"]),
        "eval_holdout_digit_combinations_path": str(
            paths["eval_holdout_digit_combinations"]
        ),
        "eval_far_range_path": str(paths["eval_far_range"]),
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


_DIGIT_TABLE_TASK_TYPES = (
    "arithmetic.digit_add_no_carry",
    "arithmetic.digit_add_with_carry_input",
    "arithmetic.digit_add_carry_out",
    "arithmetic.digit_sub_no_borrow",
    "arithmetic.digit_sub_with_borrow_input",
    "arithmetic.digit_sub_borrow_out",
)

_COMPOSITION_TASK_TYPES = (
    "arithmetic.add_2digit_composed",
    "arithmetic.sub_2digit_composed",
)


def _build_digit_table_examples(
    *,
    repeats: int,
    seed: int,
    split_label: str,
    answer_format: AnswerFormatName,
) -> list[TrainingExample]:
    base_examples: list[TrainingExample] = []
    for a in range(10):
        for b in range(10):
            base_examples.extend(
                _digit_table_examples_for_pair(a=a, b=b, split_label=split_label)
            )

    examples: list[TrainingExample] = []
    rng = random.Random(seed)
    for repeat in range(repeats):
        repeated = list(base_examples)
        rng.shuffle(repeated)
        for example in repeated:
            index = len(examples)
            case_id = seed * 1_000_000 + repeat * 100_000 + index
            prompt = f"case {case_id}. {example.prompt}"
            examples.append(
                apply_answer_format(
                    TrainingExample(
                        id=f"{example.task_type}:{split_label}:{index:08d}",
                        task_type=example.task_type,
                        prompt=prompt,
                        answer=example.answer,
                        metadata={**example.metadata, "split": split_label},
                    ),
                    answer_format,
                )
            )
    return examples


def _digit_table_examples_for_pair(
    *,
    a: int,
    b: int,
    split_label: str,
) -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    if a + b < 10:
        examples.append(
            _make_digit_add_table_example("arithmetic.digit_add_no_carry", a, b, 0)
        )
    if a + b >= 10:
        examples.append(
            _make_digit_add_table_example("arithmetic.digit_add_carry_out", a, b, 0)
        )
    examples.append(
        _make_digit_add_table_example("arithmetic.digit_add_with_carry_input", a, b, 1)
    )

    if a >= b:
        examples.append(
            _make_digit_sub_table_example("arithmetic.digit_sub_no_borrow", a, b, 0)
        )
    if a < b:
        examples.append(
            _make_digit_sub_table_example("arithmetic.digit_sub_borrow_out", a, b, 0)
        )
    examples.append(
        _make_digit_sub_table_example("arithmetic.digit_sub_with_borrow_input", a, b, 1)
    )
    return examples


def _make_digit_add_table_example(
    task_type: str,
    a: int,
    b: int,
    carry: int,
) -> TrainingExample:
    total = a + b + carry
    digit = total % 10
    carry_out = total // 10
    combo_key = f"add:{a}:{b}:{carry}"
    return TrainingExample(
        id=f"{task_type}:template",
        task_type=task_type,
        prompt=f"ADD_DIGIT a={a} b={b} c={carry}",
        answer=f"S {digit} C {carry_out}",
        metadata={
            "a": a,
            "b": b,
            "carry_in": carry,
            "sum_digit": digit,
            "carry_out": carry_out,
            "digit_combo_key": combo_key,
            "digit_combo_keys": [combo_key],
            "operation": task_type.rsplit(".", 1)[-1],
        },
    )


def _make_digit_sub_table_example(
    task_type: str,
    a: int,
    b: int,
    borrow: int,
) -> TrainingExample:
    raw = a - b - borrow
    borrow_out = 1 if raw < 0 else 0
    digit = raw + 10 if raw < 0 else raw
    combo_key = f"sub:{a}:{b}:{borrow}"
    return TrainingExample(
        id=f"{task_type}:template",
        task_type=task_type,
        prompt=f"SUB_DIGIT a={a} b={b} borrow={borrow}",
        answer=f"S {digit} B {borrow_out}",
        metadata={
            "a": a,
            "b": b,
            "borrow_in": borrow,
            "diff_digit": digit,
            "borrow_out": borrow_out,
            "digit_combo_key": combo_key,
            "digit_combo_keys": [combo_key],
            "operation": task_type.rsplit(".", 1)[-1],
        },
    )


def _build_2digit_composition_examples(
    *,
    count: int,
    seed: int,
    split_label: str,
    mode: str,
    answer_format: AnswerFormatName,
    blocked_prompts: set[str] | None = None,
) -> list[TrainingExample]:
    rng = random.Random(seed)
    examples: list[TrainingExample] = []
    seen_prompts: set[str] = set()
    blocked = blocked_prompts or set()
    attempts = 0
    while len(examples) < count:
        attempts += 1
        if attempts > count * 500:
            raise RuntimeError(
                f"Could not generate enough composition examples for {mode}"
            )
        task_type = rng.choice(_COMPOSITION_TASK_TYPES)
        if task_type == "arithmetic.add_2digit_composed":
            example = _sample_add_2digit_composed(
                rng, mode, split_label, len(examples), seed
            )
        else:
            example = _sample_sub_2digit_composed(
                rng, mode, split_label, len(examples), seed
            )
        if example.prompt in blocked or example.prompt in seen_prompts:
            continue
        seen_prompts.add(example.prompt)
        examples.append(apply_answer_format(example, answer_format))
    return examples


def _sample_add_2digit_composed(
    rng: random.Random,
    mode: str,
    split_label: str,
    index: int,
    seed: int,
) -> TrainingExample:
    for _ in range(10_000):
        a, b = _sample_2digit_operands(rng, mode)
        has_holdout = _composition_has_holdout_combo(_add_combo_keys_2digit(a, b))
        if mode == "holdout_combo" and not has_holdout:
            continue
        if mode != "holdout_combo" and has_holdout:
            continue
        return _make_add_2digit_composed(split_label, index, seed, a, b)
    raise RuntimeError("Could not sample add_2digit_composed")


def _sample_sub_2digit_composed(
    rng: random.Random,
    mode: str,
    split_label: str,
    index: int,
    seed: int,
) -> TrainingExample:
    for _ in range(10_000):
        a, b = _sample_2digit_operands(rng, mode)
        if a < b:
            a, b = b, a
        has_holdout = _composition_has_holdout_combo(_sub_combo_keys_2digit(a, b))
        if mode == "holdout_combo" and not has_holdout:
            continue
        if mode != "holdout_combo" and has_holdout:
            continue
        return _make_sub_2digit_composed(split_label, index, seed, a, b)
    raise RuntimeError("Could not sample sub_2digit_composed")


def _sample_2digit_operands(rng: random.Random, mode: str) -> tuple[int, int]:
    if mode == "far":
        return rng.randint(60, 99), rng.randint(60, 99)
    if mode in {"holdout_combo", "shifted"}:
        return rng.randint(20, 79), rng.randint(20, 79)
    return rng.randint(10, 59), rng.randint(10, 59)


def _make_add_2digit_composed(
    split_label: str,
    index: int,
    seed: int,
    a: int,
    b: int,
) -> TrainingExample:
    combo_keys = _add_combo_keys_2digit(a, b)
    return TrainingExample(
        id=f"arithmetic.add_2digit_composed:{split_label}:{index:08d}",
        task_type="arithmetic.add_2digit_composed",
        prompt=f"case {seed + index}. ADD2_COMPOSED {a} + {b}",
        answer=str(a + b),
        metadata={
            "a": a,
            "b": b,
            "digit_combo_keys": combo_keys,
            "digit_combo_key": "|".join(combo_keys),
            "operation": "add_2digit_composed",
        },
    )


def _make_sub_2digit_composed(
    split_label: str,
    index: int,
    seed: int,
    a: int,
    b: int,
) -> TrainingExample:
    combo_keys = _sub_combo_keys_2digit(a, b)
    return TrainingExample(
        id=f"arithmetic.sub_2digit_composed:{split_label}:{index:08d}",
        task_type="arithmetic.sub_2digit_composed",
        prompt=f"case {seed + index}. SUB2_COMPOSED {a} - {b}",
        answer=str(a - b),
        metadata={
            "a": a,
            "b": b,
            "digit_combo_keys": combo_keys,
            "digit_combo_key": "|".join(combo_keys),
            "operation": "sub_2digit_composed",
        },
    )


def _add_combo_keys_2digit(a: int, b: int) -> list[str]:
    at, au = divmod(a, 10)
    bt, bu = divmod(b, 10)
    ones_carry = 1 if au + bu >= 10 else 0
    return [f"add:{au}:{bu}:0", f"add:{at}:{bt}:{ones_carry}"]


def _sub_combo_keys_2digit(a: int, b: int) -> list[str]:
    at, au = divmod(a, 10)
    bt, bu = divmod(b, 10)
    ones_borrow = 1 if au < bu else 0
    return [f"sub:{au}:{bu}:0", f"sub:{at}:{bt}:{ones_borrow}"]


def _composition_has_holdout_combo(combo_keys: Sequence[str]) -> bool:
    return any(_combo_key_is_composition_holdout(key) for key in combo_keys)


def _combo_key_is_composition_holdout(combo_key: str) -> bool:
    op, left, right, carry_or_borrow = combo_key.split(":")
    value = int(left) * 17 + int(right) * 7 + int(carry_or_borrow) * 11
    return value % 5 == (0 if op == "add" else 1)


def _build_digit_operation_coverage(
    examples: Sequence[TrainingExample | dict[str, Any]],
) -> dict[str, Any]:
    coverage = {
        "add_pairs": set(),
        "sub_pairs": set(),
        "carry_in_values": set(),
        "carry_out_values": set(),
        "borrow_in_values": set(),
        "borrow_out_values": set(),
    }
    for example in examples:
        metadata = _get_example_field(example, "metadata")
        if not isinstance(metadata, dict):
            continue
        task_type = _get_example_field(example, "task_type")
        if "digit_add" in task_type:
            coverage["add_pairs"].add((metadata["a"], metadata["b"]))
            coverage["carry_in_values"].add(metadata["carry_in"])
            coverage["carry_out_values"].add(metadata["carry_out"])
        if "digit_sub" in task_type:
            coverage["sub_pairs"].add((metadata["a"], metadata["b"]))
            coverage["borrow_in_values"].add(metadata["borrow_in"])
            coverage["borrow_out_values"].add(metadata["borrow_out"])
    return {
        "add_pair_count": len(coverage["add_pairs"]),
        "sub_pair_count": len(coverage["sub_pairs"]),
        "carry_in_values": sorted(coverage["carry_in_values"]),
        "carry_out_values": sorted(coverage["carry_out_values"]),
        "borrow_in_values": sorted(coverage["borrow_in_values"]),
        "borrow_out_values": sorted(coverage["borrow_out_values"]),
    }


def _digit_combo_set(examples: Sequence[TrainingExample | dict[str, Any]]) -> set[str]:
    combos: set[str] = set()
    for example in examples:
        metadata = _get_example_field(example, "metadata")
        if not isinstance(metadata, dict):
            continue
        value = metadata.get("digit_combo_keys")
        if isinstance(value, list):
            combos.update(str(item) for item in value)
        elif metadata.get("digit_combo_key"):
            combos.add(str(metadata["digit_combo_key"]))
    return combos


def _build_digit_combo_summary(
    examples: Sequence[TrainingExample | dict[str, Any]],
) -> dict[str, Any]:
    combos = sorted(_digit_combo_set(examples))
    by_op = Counter(combo.split(":", 1)[0] for combo in combos)
    return {
        "unique_digit_combo_count": len(combos),
        "unique_digit_combo_count_by_op": dict(sorted(by_op.items())),
        "sample": combos[:30],
    }


def _build_digit_combo_overlap_summary(
    train_combos: set[str],
    eval_combos: set[str],
) -> dict[str, Any]:
    overlap = sorted(train_combos & eval_combos)
    holdout_only = sorted(eval_combos - train_combos)
    return {
        "train_unique_digit_combo_count": len(train_combos),
        "eval_unique_digit_combo_count": len(eval_combos),
        "overlap_count": len(overlap),
        "eval_overlap_fraction": len(overlap) / len(eval_combos)
        if eval_combos
        else 0.0,
        "eval_unseen_digit_combo_count": len(holdout_only),
        "eval_unseen_digit_combo_fraction": (
            len(holdout_only) / len(eval_combos) if eval_combos else 0.0
        ),
        "unseen_sample": holdout_only[:30],
    }


def _build_prompt_intersection_summaries(
    split_prompt_sets: dict[str, set[str]],
) -> dict[str, dict[str, Any]]:
    split_names = list(split_prompt_sets)
    summaries: dict[str, dict[str, Any]] = {}
    for left_index, left_name in enumerate(split_names):
        for right_name in split_names[left_index + 1 :]:
            intersection = sorted(
                split_prompt_sets[left_name] & split_prompt_sets[right_name]
            )
            summaries[_intersection_key(left_name, right_name)] = {
                "count": len(intersection),
                "sample": intersection[:10],
            }
    return summaries


def _intersection_key(left_name: str, right_name: str) -> str:
    return "__".join(sorted((left_name, right_name)))


def _build_numeric_range_summary(
    examples: Sequence[TrainingExample | dict[str, Any]],
) -> dict[str, Any]:
    values = sorted(
        value
        for example in examples
        for value in _extract_input_metadata_numbers(
            _get_example_field(example, "metadata")
        )
    )
    unique_values = sorted(set(values))
    if not values:
        return {
            "count": 0,
            "unique_count": 0,
            "min": None,
            "max": None,
            "sample": [],
        }

    by_key_values = _extract_input_metadata_numbers_by_key(examples)

    return {
        "count": len(values),
        "unique_count": len(unique_values),
        "min": values[0],
        "max": values[-1],
        "sample": unique_values[:20],
        "by_key": {
            key: _summarize_numeric_values(key_values)
            for key, key_values in sorted(by_key_values.items())
        },
    }


def _build_numeric_overlap_summary(
    train_prime_examples: Sequence[TrainingExample | dict[str, Any]],
    eval_examples: Sequence[TrainingExample | dict[str, Any]],
) -> dict[str, Any]:
    train_values = {
        value
        for example in train_prime_examples
        for value in _extract_input_metadata_numbers(
            _get_example_field(example, "metadata")
        )
    }
    eval_values = {
        value
        for example in eval_examples
        for value in _extract_input_metadata_numbers(
            _get_example_field(example, "metadata")
        )
    }
    overlap = sorted(train_values & eval_values)
    eval_unique_count = len(eval_values)
    train_unique_count = len(train_values)
    train_by_key = _extract_input_metadata_numbers_by_key(train_prime_examples)
    eval_by_key = _extract_input_metadata_numbers_by_key(eval_examples)

    return {
        "train_prime_unique_numeric_count": train_unique_count,
        "eval_unique_numeric_count": eval_unique_count,
        "overlap_count": len(overlap),
        "eval_overlap_fraction": (
            len(overlap) / eval_unique_count if eval_unique_count else 0.0
        ),
        "train_prime_overlap_fraction": (
            len(overlap) / train_unique_count if train_unique_count else 0.0
        ),
        "overlap_sample": overlap[:20],
        "by_key": _build_numeric_overlap_by_key(train_by_key, eval_by_key),
    }


def _summarize_numeric_values(values: Sequence[int]) -> dict[str, Any]:
    sorted_values = sorted(values)
    unique_values = sorted(set(sorted_values))
    if not sorted_values:
        return {
            "count": 0,
            "unique_count": 0,
            "min": None,
            "max": None,
            "sample": [],
        }

    return {
        "count": len(sorted_values),
        "unique_count": len(unique_values),
        "min": sorted_values[0],
        "max": sorted_values[-1],
        "sample": unique_values[:20],
    }


def _extract_input_metadata_numbers_by_key(
    examples: Sequence[TrainingExample | dict[str, Any]],
) -> dict[str, list[int]]:
    by_key: dict[str, list[int]] = {}
    for example in examples:
        metadata = _get_example_field(example, "metadata")
        if not isinstance(metadata, dict):
            continue
        for key, value in metadata.items():
            if key not in _INPUT_NUMERIC_METADATA_KEYS:
                continue
            by_key.setdefault(key, []).extend(_extract_metadata_numbers(value))
    return by_key


def _build_numeric_overlap_by_key(
    train_by_key: dict[str, list[int]],
    eval_by_key: dict[str, list[int]],
) -> dict[str, dict[str, Any]]:
    overlap_by_key = {}
    for key in sorted(set(train_by_key) | set(eval_by_key)):
        train_values = set(train_by_key.get(key, []))
        eval_values = set(eval_by_key.get(key, []))
        overlap = sorted(train_values & eval_values)
        overlap_by_key[key] = {
            "train_prime_unique_numeric_count": len(train_values),
            "eval_unique_numeric_count": len(eval_values),
            "overlap_count": len(overlap),
            "eval_overlap_fraction": (
                len(overlap) / len(eval_values) if eval_values else 0.0
            ),
            "train_prime_overlap_fraction": (
                len(overlap) / len(train_values) if train_values else 0.0
            ),
            "overlap_sample": overlap[:20],
        }
    return overlap_by_key


_INPUT_NUMERIC_METADATA_KEYS = {
    "a",
    "b",
    "c",
    "d",
    "total",
    "start",
    "delta",
    "count",
    "numbers",
    "known",
    "target",
    "missing",
    "mid",
}


def _extract_input_metadata_numbers(metadata: Any) -> list[int]:
    if not isinstance(metadata, dict):
        return []

    numbers: list[int] = []
    for key, value in metadata.items():
        if key in _INPUT_NUMERIC_METADATA_KEYS:
            numbers.extend(_extract_metadata_numbers(value))
    return numbers


def _extract_metadata_numbers(value: Any) -> list[int]:
    if isinstance(value, bool):
        return []

    if isinstance(value, int):
        return [value]

    if isinstance(value, float) and value.is_integer():
        return [int(value)]

    if isinstance(value, dict):
        numbers: list[int] = []
        for nested_value in value.values():
            numbers.extend(_extract_metadata_numbers(nested_value))
        return numbers

    if isinstance(value, list | tuple):
        numbers = []
        for nested_value in value:
            numbers.extend(_extract_metadata_numbers(nested_value))
        return numbers

    return []


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
