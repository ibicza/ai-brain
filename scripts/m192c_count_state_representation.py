from __future__ import annotations

import argparse
import itertools
import json
import re
import socket
import subprocess
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.generation import (
    build_inference_input_ids,
    generate_answer_ids,
    load_model_for_inference,
)
from ai_brain.eval.normalize import extract_generated_answer
from ai_brain.eval.runner import eval_lm
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.training.config import TrainConfig
from ai_brain.training.lm_dataset import IGNORE_INDEX
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m192c_count_state_representation"
RUNS_DIR = ROOT / "runs" / "m192c_count_state_representation"
DOC_PATH = ROOT / "docs" / "m192c_count_state_representation_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m192c_count_state_representation_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 192300
MODEL_CONFIG = "arithmetic_3m"
POSITION_ENCODING = "relative"
NUMERIC_TOKENIZATION = "digit_safe"
BATCH_SIZE = 8
SEQUENCE_LENGTH = 256
TRACE_SEQUENCE_LENGTH = 512
LOSS_MODE = "answer-only"
LEARNING_RATE = 3e-4
GRAD_CLIP_NORM = 1.0

TRAIN_COUNTS = tuple(range(11))
LENGTH_OOD_COUNTS = tuple(range(11, 21))
FAR_COUNTS = tuple(range(21, 31))
SUCCESSOR_COUNTS = tuple(range(10))
STRUCTURED_TRAIN_COUNTS = tuple(range(13))
TRAIN_OBJECTS = ("x", "a", "k", "m", "n")
HELDOUT_OBJECTS = ("q", "z", "w", "y")
ALL_OBJECTS = TRAIN_OBJECTS + HELDOUT_OBJECTS
EXPANSION_EXAMPLES_PER_COUNT = (1, 5, 10, 25, 50, 100)

FORBIDDEN_PROMPT_PATTERNS = (
    r"\bCASE\b",
    r"\bID\b",
    r"\bEXAMPLE\b",
    r"\bTRAIN\b",
    r"\bEVAL\b",
    r"\bSPLIT\b",
    r"\bSEED\b",
)

STEPS = {
    "decimal_iterative": 9000,
    "unary_count": 9000,
    "take_stop_transformer": 6000,
    "same_count_length": 6000,
    "matching_action": 6000,
    "structured_counter": 6000,
    "unary_decoder": 4000,
    "range_expansion": 1200,
}


@dataclass(frozen=True)
class TrainSpec:
    name: str
    train_path: Path
    eval_path: Path
    steps: int
    seed: int
    sequence_length: int = SEQUENCE_LENGTH
    init_checkpoint_path: Path | None = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M-19.2c count-state representation lab."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-core")
    subparsers.add_parser("run-sample-efficiency")
    subparsers.add_parser("run-probes")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-core":
        run_core()
    elif args.command == "run-sample-efficiency":
        run_sample_efficiency()
    elif args.command == "run-probes":
        run_probes()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_core()
        run_sample_efficiency()
        run_probes()
        analyze_all()
        build_report(checks_passed=False)


def prepare_datasets() -> None:
    datasets = build_datasets()
    for section in ("train", "eval"):
        for name, examples in datasets[section].items():
            _write_jsonl(DATASET_DIR / section / f"{name}.jsonl", examples)

    leakage = full_count_leakage(datasets["train"])
    manifest = {
        "kind": "m192c_count_state_representation",
        "seed": SEED,
        "model_config": MODEL_CONFIG,
        "position_encoding": POSITION_ENCODING,
        "numeric_tokenization": NUMERIC_TOKENIZATION,
        "train_counts": list(TRAIN_COUNTS),
        "length_ood_counts": list(LENGTH_OOD_COUNTS),
        "far_counts": list(FAR_COUNTS),
        "train_objects": list(TRAIN_OBJECTS),
        "heldout_objects": list(HELDOUT_OBJECTS),
        "nuisance_audit": nuisance_audit(datasets),
        "train_sets": {
            name: audit_examples(examples)
            for name, examples in datasets["train"].items()
        },
        "eval_splits": {
            name: audit_examples(examples)
            for name, examples in datasets["eval"].items()
        },
        "full_count_11_20_leakage": leakage,
        "zero_shot_full_count_11_20_leakage": {
            name: value
            for name, value in leakage.items()
            if not name.startswith("range_expansion_")
        },
        "few_shot_expansion_counts": {
            str(k): len(datasets["train"][f"range_expansion_{k}"])
            for k in EXPANSION_EXAMPLES_PER_COUNT
        },
    }
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_core() -> None:
    specs = [
        TrainSpec(
            "decimal_iterative",
            DATASET_DIR / "train" / "decimal_iterative.jsonl",
            DATASET_DIR / "eval" / "decimal_iterative_train_fit.jsonl",
            STEPS["decimal_iterative"],
            SEED + 1,
            TRACE_SEQUENCE_LENGTH,
        ),
        TrainSpec(
            "unary_count",
            DATASET_DIR / "train" / "unary_count.jsonl",
            DATASET_DIR / "eval" / "unary_count_train_fit.jsonl",
            STEPS["unary_count"],
            SEED + 2,
            TRACE_SEQUENCE_LENGTH,
        ),
        TrainSpec(
            "take_stop_transformer",
            DATASET_DIR / "train" / "take_stop_action.jsonl",
            DATASET_DIR / "eval" / "take_stop_seen_steps.jsonl",
            STEPS["take_stop_transformer"],
            SEED + 3,
        ),
        TrainSpec(
            "same_count_length",
            DATASET_DIR / "train" / "same_count.jsonl",
            DATASET_DIR / "eval" / "same_count_seen.jsonl",
            STEPS["same_count_length"],
            SEED + 4,
        ),
        TrainSpec(
            "matching_action",
            DATASET_DIR / "train" / "matching_action.jsonl",
            DATASET_DIR / "eval" / "matching_action_seen_steps.jsonl",
            STEPS["matching_action"],
            SEED + 5,
        ),
        TrainSpec(
            "structured_counter",
            DATASET_DIR / "train" / "structured_counter.jsonl",
            DATASET_DIR / "eval" / "structured_counter_seen.jsonl",
            STEPS["structured_counter"],
            SEED + 6,
        ),
        TrainSpec(
            "unary_decoder",
            DATASET_DIR / "train" / "unary_decoder_0_10.jsonl",
            DATASET_DIR / "eval" / "unary_decoder_seen.jsonl",
            STEPS["unary_decoder"],
            SEED + 7,
        ),
    ]
    for spec in specs:
        _train_and_eval(spec, eval_splits_for_run(spec.name))
        if spec.name == "take_stop_transformer":
            eval_take_stop_transformer_environment()
        if spec.name == "matching_action":
            eval_matching_action_environment()
    train_and_eval_gru_action_control()
    analyze_all()
    build_report(checks_passed=False)


def run_sample_efficiency() -> None:
    global_checkpoint = final_checkpoint(RUNS_DIR / "global_count_concept")
    if global_checkpoint is None:
        _train_and_eval(
            TrainSpec(
                "global_count_concept",
                DATASET_DIR / "train" / "global_count_0_10.jsonl",
                DATASET_DIR / "eval" / "global_count_seen.jsonl",
                6000,
                SEED + 50,
            ),
            ["global_count_seen", "global_count_length_ood"],
        )
        global_checkpoint = final_checkpoint(RUNS_DIR / "global_count_concept")
    if global_checkpoint is None:
        raise RuntimeError("global_count_concept did not produce a checkpoint")

    for k in EXPANSION_EXAMPLES_PER_COUNT:
        train_path = DATASET_DIR / "train" / f"range_expansion_{k}.jsonl"
        eval_splits = [
            "range_expansion_eval_seen_objects",
            "range_expansion_eval_heldout_objects",
        ]
        _train_and_eval(
            TrainSpec(
                f"range_direct_{k}",
                train_path,
                DATASET_DIR / "eval" / "range_expansion_eval_seen_objects.jsonl",
                STEPS["range_expansion"],
                SEED + 100 + k,
            ),
            eval_splits,
        )
        _train_and_eval(
            TrainSpec(
                f"range_concept_{k}",
                train_path,
                DATASET_DIR / "eval" / "range_expansion_eval_seen_objects.jsonl",
                STEPS["range_expansion"],
                SEED + 200 + k,
                init_checkpoint_path=global_checkpoint,
            ),
            eval_splits,
        )
    analyze_all()
    build_report(checks_passed=False)


def run_probes() -> None:
    probe_specs = {
        "global_count_concept": probe_prompts_global_count,
        "unary_count": probe_prompts_unary_count,
        "take_stop_transformer": probe_prompts_terminal_action_count,
        "structured_counter": probe_prompts_structured_counter,
    }
    for run_name, prompt_builder in probe_specs.items():
        run_dir = RUNS_DIR / run_name
        checkpoint = final_checkpoint(run_dir)
        if checkpoint is None:
            continue
        result = cardinality_probe(checkpoint, prompt_builder)
        probe_dir = run_dir / "probes"
        probe_dir.mkdir(parents=True, exist_ok=True)
        (probe_dir / "cardinality_probe.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def probe_prompts_global_count(
    counts: Sequence[int], objects: Sequence[str]
) -> list[tuple[int, str]]:
    return [
        (n, f"COUNT\n{object_sequence(n, [obj], separator='space')}")
        for n, obj in itertools.product(counts, objects)
    ]


def probe_prompts_unary_count(
    counts: Sequence[int], objects: Sequence[str]
) -> list[tuple[int, str]]:
    return [
        (n, f"UNARY_COUNT\n{object_sequence(n, [obj], separator='space')}")
        for n, obj in itertools.product(counts, objects)
    ]


def probe_prompts_terminal_action_count(
    counts: Sequence[int], objects: Sequence[str]
) -> list[tuple[int, str]]:
    return [
        (n, action_prompt(n=n, obj=obj, head=n))
        for n, obj in itertools.product(counts, objects)
    ]


def probe_prompts_structured_counter(
    counts: Sequence[int], objects: Sequence[str]
) -> list[tuple[int, str]]:
    return [
        (n, f"STRUCT_COUNT_STEP\nSTATE {structured_state(n)}\nNEXT_OBJECT {obj}")
        for n, obj in itertools.product(counts, objects)
    ]


def cardinality_probe(
    checkpoint_path: Path,
    prompt_builder: Any,
) -> dict[str, Any]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=TOKENIZER_PATH,
        device=device,
    )
    train_prompts = prompt_builder(TRAIN_COUNTS, TRAIN_OBJECTS[:2])
    test_prompts = prompt_builder(TRAIN_COUNTS, TRAIN_OBJECTS[2:])
    train_vectors = probe_vectors(model, tokenizer, train_prompts, device)
    test_vectors = probe_vectors(model, tokenizer, test_prompts, device)
    centroids = {
        count: torch.stack(
            [vec for value, vec in train_vectors if value == count]
        ).mean(dim=0)
        for count in TRAIN_COUNTS
    }
    correct = 0
    for count, vec in test_vectors:
        predicted = nearest_centroid(vec, centroids)
        correct += int(predicted == count)
    same_cosines, different_cosines = probe_pair_cosines(test_vectors)
    successor_cosines = probe_successor_cosines(centroids)
    return {
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_step": checkpoint.get("step"),
        "train_prompt_count": len(train_prompts),
        "test_prompt_count": len(test_prompts),
        "centroid_probe_accuracy": correct / len(test_vectors) if test_vectors else 0.0,
        "same_quantity_cosine": mean(same_cosines),
        "different_quantity_cosine": mean(different_cosines),
        "successor_direction_cosine": mean(successor_cosines),
    }


def probe_vectors(
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    prompts: Sequence[tuple[int, str]],
    device: torch.device,
) -> list[tuple[int, torch.Tensor]]:
    vectors = []
    with torch.no_grad():
        for count, prompt in prompts:
            input_ids = build_inference_input_ids(
                prompt=prompt,
                tokenizer=tokenizer,
                device=device,
                numeric_tokenization=NUMERIC_TOKENIZATION,
            )
            if input_ids.shape[1] > model.config.max_sequence_length:
                input_ids = input_ids[:, -model.config.max_sequence_length :]
            x = model.embed_tokens_and_positions(input_ids)
            _logits, hidden = model.forward_embeddings(x, return_hidden=True)
            vectors.append((count, hidden[0, -1].detach().cpu()))
    return vectors


def nearest_centroid(vec: torch.Tensor, centroids: dict[int, torch.Tensor]) -> int:
    return max(
        centroids,
        key=lambda count: F.cosine_similarity(vec, centroids[count], dim=0).item(),
    )


def probe_pair_cosines(
    vectors: Sequence[tuple[int, torch.Tensor]],
) -> tuple[list[float], list[float]]:
    same = []
    different = []
    for (left_count, left_vec), (right_count, right_vec) in itertools.combinations(
        vectors, 2
    ):
        value = F.cosine_similarity(left_vec, right_vec, dim=0).item()
        if left_count == right_count:
            same.append(value)
        else:
            different.append(value)
    return same, different


def probe_successor_cosines(centroids: dict[int, torch.Tensor]) -> list[float]:
    directions = [
        centroids[count + 1] - centroids[count]
        for count in TRAIN_COUNTS
        if count + 1 in centroids
    ]
    return [
        F.cosine_similarity(left, right, dim=0).item()
        for left, right in itertools.combinations(directions, 2)
    ]


def build_datasets() -> dict[str, dict[str, list[dict[str, Any]]]]:
    decimal = [
        decimal_iterative_example(n, obj, index=index)
        for index, (n, obj) in enumerate(itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS))
    ]
    unary = [
        unary_count_example(n, obj, index=index)
        for index, (n, obj) in enumerate(itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS))
    ]
    take_stop = [
        take_stop_action_example(n, obj, head, index=index)
        for index, (n, obj, head) in enumerate(
            action_state_product(TRAIN_COUNTS, TRAIN_OBJECTS)
        )
    ]
    same_count = same_count_examples(TRAIN_COUNTS, TRAIN_OBJECTS, index_offset=0)
    matching = [
        matching_action_example(left, right, left_obj, right_obj, index=index)
        for index, (left, right, left_obj, right_obj) in enumerate(
            matching_state_product(TRAIN_COUNTS, TRAIN_OBJECTS)
        )
    ]
    structured = [
        structured_counter_example(n, obj, index=index)
        for index, (n, obj) in enumerate(
            itertools.product(STRUCTURED_TRAIN_COUNTS, TRAIN_OBJECTS)
        )
        if n < 20
    ]
    global_count = [
        global_count_example(n, obj, index=index)
        for index, (n, obj) in enumerate(itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS))
    ]
    expansion_eval_seen = [
        global_count_example(n, obj, index=20_000 + index)
        for index, (n, obj) in enumerate(
            itertools.product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS)
        )
    ]
    expansion_eval_heldout = [
        global_count_example(n, obj, index=21_000 + index)
        for index, (n, obj) in enumerate(
            itertools.product(LENGTH_OOD_COUNTS, HELDOUT_OBJECTS)
        )
    ]

    train = {
        "decimal_iterative": repeat_examples(decimal, 7000),
        "unary_count": repeat_examples(unary, 7000),
        "take_stop_action": repeat_examples(take_stop, 7000),
        "same_count": repeat_examples(same_count, 7000),
        "matching_action": repeat_examples(matching, 7000),
        "structured_counter": repeat_examples(structured, 6000),
        "unary_decoder_0_10": repeat_examples(
            [unary_decoder_example(n, index=n) for n in TRAIN_COUNTS],
            4000,
        ),
        "global_count_0_10": repeat_examples(global_count, 7000),
    }
    for k in EXPANSION_EXAMPLES_PER_COUNT:
        train[f"range_expansion_{k}"] = range_expansion_examples(k)

    eval_sets = {
        "decimal_iterative_train_fit": decimal,
        "decimal_iterative_seen": [
            decimal_iterative_example(n, obj, index=10_000 + index)
            for index, (n, obj) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS)
            )
        ],
        "decimal_iterative_length_ood": [
            decimal_iterative_example(n, obj, index=11_000 + index)
            for index, (n, obj) in enumerate(
                itertools.product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS[:2])
            )
        ],
        "unary_count_train_fit": unary,
        "unary_count_seen": [
            unary_count_example(n, obj, index=12_000 + index)
            for index, (n, obj) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS)
            )
        ],
        "unary_count_heldout_object": [
            unary_count_example(n, obj, index=13_000 + index)
            for index, (n, obj) in enumerate(
                itertools.product(TRAIN_COUNTS, HELDOUT_OBJECTS)
            )
        ],
        "unary_count_length_ood": [
            unary_count_example(n, obj, index=14_000 + index)
            for index, (n, obj) in enumerate(
                itertools.product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS[:2])
            )
        ],
        "unary_count_far_ood": [
            unary_count_example(n, obj, index=15_000 + index)
            for index, (n, obj) in enumerate(
                itertools.product(FAR_COUNTS, TRAIN_OBJECTS[:1])
            )
        ],
        "take_stop_seen_steps": take_stop,
        "take_stop_length_steps": [
            take_stop_action_example(n, obj, head, index=16_000 + index)
            for index, (n, obj, head) in enumerate(
                action_state_product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS[:2])
            )
        ],
        "take_stop_far_steps": [
            take_stop_action_example(n, "x", head, index=17_000 + index)
            for index, (n, _obj, head) in enumerate(
                action_state_product(FAR_COUNTS, ("x",))
            )
        ],
        "same_count_seen": same_count,
        "same_count_length_ood": same_count_examples(
            LENGTH_OOD_COUNTS,
            TRAIN_OBJECTS,
            index_offset=18_000,
        ),
        "same_count_length_heldout": same_count_examples(
            LENGTH_OOD_COUNTS,
            HELDOUT_OBJECTS,
            index_offset=19_000,
        ),
        "matching_action_seen_steps": matching,
        "matching_action_length_steps": [
            matching_action_example(
                left, right, left_obj, right_obj, index=22_000 + index
            )
            for index, (left, right, left_obj, right_obj) in enumerate(
                matching_state_product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS[:2])
            )
        ],
        "structured_counter_seen": [
            structured_counter_example(n, obj, index=23_000 + index)
            for index, (n, obj) in enumerate(
                itertools.product(STRUCTURED_TRAIN_COUNTS[:-1], TRAIN_OBJECTS[:2])
            )
        ],
        "structured_counter_length_ood": [
            structured_counter_example(n, obj, index=24_000 + index)
            for index, (n, obj) in enumerate(
                itertools.product(range(13, 20), TRAIN_OBJECTS[:2])
            )
        ],
        "unary_decoder_seen": [
            unary_decoder_example(n, index=25_000 + n) for n in TRAIN_COUNTS
        ],
        "unary_decoder_length_ood": [
            unary_decoder_example(n, index=26_000 + n) for n in LENGTH_OOD_COUNTS
        ],
        "global_count_seen": global_count,
        "global_count_length_ood": expansion_eval_seen,
        "range_expansion_eval_seen_objects": expansion_eval_seen,
        "range_expansion_eval_heldout_objects": expansion_eval_heldout,
    }
    return {"train": train, "eval": eval_sets}


def eval_splits_for_run(name: str) -> list[str]:
    return {
        "decimal_iterative": [
            "decimal_iterative_train_fit",
            "decimal_iterative_seen",
            "decimal_iterative_length_ood",
        ],
        "unary_count": [
            "unary_count_train_fit",
            "unary_count_seen",
            "unary_count_heldout_object",
            "unary_count_length_ood",
            "unary_count_far_ood",
        ],
        "take_stop_transformer": [
            "take_stop_seen_steps",
            "take_stop_length_steps",
            "take_stop_far_steps",
        ],
        "same_count_length": [
            "same_count_seen",
            "same_count_length_ood",
            "same_count_length_heldout",
        ],
        "matching_action": [
            "matching_action_seen_steps",
            "matching_action_length_steps",
        ],
        "structured_counter": [
            "structured_counter_seen",
            "structured_counter_length_ood",
        ],
        "unary_decoder": ["unary_decoder_seen", "unary_decoder_length_ood"],
    }[name]


def decimal_iterative_example(n: int, obj: str, *, index: int) -> dict[str, Any]:
    lines = [f"STATE {0} REM {n}"]
    for step in range(n):
        lines.append("TAKE")
        lines.append(f"STATE {step + 1} REM {n - step - 1}")
    lines.append("HALT")
    lines.append(f"FINAL {n}")
    return record(
        index,
        "m192c.decimal_iterative",
        f"DECIMAL_ITER_COUNT\n{object_sequence(n, [obj], separator='space')}",
        "\n".join(lines),
        n=n,
        object_family=obj,
        full_count=True,
        representation="decimal",
    )


def unary_count_example(n: int, obj: str, *, index: int) -> dict[str, Any]:
    lines = [f"COUNT_STATE {unary_state(0)} REM {n}"]
    for step in range(n):
        lines.append("TAKE")
        lines.append(f"COUNT_STATE {unary_state(step + 1)} REM {n - step - 1}")
    lines.append("HALT")
    lines.append(f"FINAL {unary_state(n)}")
    return record(
        index,
        "m192c.unary_count",
        f"UNARY_COUNT\n{object_sequence(n, [obj], separator='space')}",
        "\n".join(lines),
        n=n,
        object_family=obj,
        full_count=True,
        representation="unary",
    )


def take_stop_action_example(
    n: int, obj: str, head: int, *, index: int
) -> dict[str, Any]:
    return record(
        index,
        "m192c.take_stop_action",
        action_prompt(n=n, obj=obj, head=head),
        f"FINAL {'TAKE' if head < n else 'STOP'}",
        n=n,
        head=head,
        object_family=obj,
        expected_action="TAKE" if head < n else "STOP",
    )


def action_prompt(*, n: int, obj: str, head: int) -> str:
    left = object_sequence(head, [obj], separator="space")
    current = obj if head < n else "END"
    right = object_sequence(max(n - head - 1, 0), [obj], separator="space")
    return f"COUNT_ACTION\nLEFT {left}\nHEAD {current}\nRIGHT {right}"


def matching_action_example(
    left: int,
    right: int,
    left_obj: str,
    right_obj: str,
    *,
    index: int,
) -> dict[str, Any]:
    action = matching_oracle_action(left, right)
    return record(
        index,
        "m192c.matching_action",
        "MATCH_ACTION\n"
        f"LEFT {object_sequence(left, [left_obj], separator='space')}\n"
        f"RIGHT {object_sequence(right, [right_obj], separator='space')}",
        f"FINAL {action}",
        left_count=left,
        right_count=right,
        left_object_family=left_obj,
        right_object_family=right_obj,
        expected_action=action,
    )


def matching_oracle_action(left: int, right: int) -> str:
    if left > 0 and right > 0:
        return "PAIR"
    if left > 0:
        return "LEFT_MORE"
    if right > 0:
        return "RIGHT_MORE"
    return "SAME"


def structured_counter_example(n: int, obj: str, *, index: int) -> dict[str, Any]:
    return record(
        index,
        "m192c.structured_counter",
        f"STRUCT_COUNT_STEP\nSTATE {structured_state(n)}\nNEXT_OBJECT {obj}",
        f"FINAL STATE {structured_state(n + 1)}",
        n=n,
        next_n=n + 1,
        object_family=obj,
        representation="tens_ones",
    )


def unary_decoder_example(n: int, *, index: int) -> dict[str, Any]:
    return record(
        index,
        "m192c.unary_decoder",
        f"DECODE_UNARY\n{unary_state(n)}",
        f"FINAL {n}",
        n=n,
        representation="unary_to_decimal",
    )


def global_count_example(n: int, obj: str, *, index: int) -> dict[str, Any]:
    return record(
        index,
        "m192c.global_count",
        f"COUNT\n{object_sequence(n, [obj], separator='space')}",
        f"FINAL {n}",
        n=n,
        object_family=obj,
        full_count=True,
        representation="decimal_label",
    )


def same_count_examples(
    counts: Sequence[int],
    objects: Sequence[str],
    *,
    index_offset: int,
) -> list[dict[str, Any]]:
    examples = []
    index = index_offset
    for n, left_obj, right_obj in itertools.product(counts, objects[:3], objects[-3:]):
        examples.append(same_count_example(n, n, left_obj, right_obj, index=index))
        index += 1
        examples.append(same_count_example(n, n + 1, left_obj, right_obj, index=index))
        index += 1
        examples.append(same_count_example(n + 1, n, left_obj, right_obj, index=index))
        index += 1
    return examples


def same_count_example(
    left_n: int,
    right_n: int,
    left_obj: str,
    right_obj: str,
    *,
    index: int,
) -> dict[str, Any]:
    return record(
        index,
        "m192c.same_count",
        "SAME_COUNT\n"
        f"LEFT {object_sequence(left_n, [left_obj], separator='space')}\n"
        f"RIGHT {object_sequence(right_n, [right_obj], separator='space')}",
        f"FINAL {'YES' if left_n == right_n else 'NO'}",
        left_n=left_n,
        right_n=right_n,
        left_object_family=left_obj,
        right_object_family=right_obj,
    )


def range_expansion_examples(examples_per_count: int) -> list[dict[str, Any]]:
    examples = []
    index = 30_000 + examples_per_count * 1000
    for n in LENGTH_OOD_COUNTS:
        for offset in range(examples_per_count):
            obj = TRAIN_OBJECTS[offset % len(TRAIN_OBJECTS)]
            examples.append(global_count_example(n, obj, index=index))
            index += 1
    return examples


def action_state_product(
    counts: Sequence[int],
    objects: Sequence[str],
) -> Iterable[tuple[int, str, int]]:
    for n, obj in itertools.product(counts, objects):
        for head in range(n + 1):
            yield n, obj, head


def matching_state_product(
    counts: Sequence[int],
    objects: Sequence[str],
) -> Iterable[tuple[int, int, str, str]]:
    for left, right, left_obj, right_obj in itertools.product(
        counts, counts, objects[:2], objects[-2:]
    ):
        if (
            abs(left - right) <= 1
            or left in {0, max(counts)}
            or right in {0, max(counts)}
        ):
            yield left, right, left_obj, right_obj


def object_sequence(n: int, objects: Sequence[str], *, separator: str) -> str:
    if n == 0:
        return "EMPTY"
    sep = " " if separator == "space" else " | "
    return sep.join(objects[index % len(objects)] for index in range(n))


def unary_state(n: int) -> str:
    return "EMPTY" if n == 0 else " ".join("C" for _ in range(n))


def unary_length(state: str) -> int:
    stripped = state.strip()
    if stripped == "EMPTY" or not stripped:
        return 0
    return len(re.findall(r"\bC\b", stripped))


def structured_state(n: int) -> str:
    tens, ones = divmod(n, 10)
    return f"T{tens} O{ones}"


def structured_to_int(state: str) -> int:
    match = re.search(r"T(\d+) O(\d+)", state)
    if not match:
        raise ValueError(f"invalid structured state: {state}")
    return int(match.group(1)) * 10 + int(match.group(2))


def record(
    index: int, task_type: str, prompt: str, answer: str, **metadata: Any
) -> dict[str, Any]:
    metadata = {"case_id": index, **metadata}
    return {
        "id": f"{task_type}:{index:06d}",
        "task_type": task_type,
        "prompt": prompt,
        "answer": answer,
        "metadata": metadata,
    }


def repeat_examples(
    examples: Sequence[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    return [dict(examples[index % len(examples)]) for index in range(count)]


def _train_and_eval(spec: TrainSpec, eval_splits: Sequence[str]) -> None:
    run_dir = RUNS_DIR / spec.name
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        result = train_lm(
            TrainConfig(
                train_path=spec.train_path,
                eval_path=spec.eval_path,
                tokenizer_path=TOKENIZER_PATH,
                output_dir=run_dir,
                model_config_name=MODEL_CONFIG,
                steps=spec.steps,
                batch_size=BATCH_SIZE,
                sequence_length=spec.sequence_length,
                loss_mode=LOSS_MODE,
                learning_rate=LEARNING_RATE,
                grad_clip_norm=GRAD_CLIP_NORM,
                numeric_tokenization=NUMERIC_TOKENIZATION,
                position_encoding=POSITION_ENCODING,
                seed=spec.seed,
                eval_every=max(spec.steps // 3, 1),
                eval_batches=20,
                save_every=max(spec.steps // 3, 1),
                cache_dir=ROOT / "cache" / "tokenized_m192c",
                init_checkpoint_path=spec.init_checkpoint_path,
            )
        )
        (run_dir / "run_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        raise RuntimeError(f"No checkpoint for {spec.name}")
    for split in eval_splits:
        output_dir = run_dir / "eval" / split
        if (output_dir / "summary.json").exists():
            continue
        result = eval_lm(
            checkpoint_path=checkpoint,
            eval_path=DATASET_DIR / "eval" / f"{split}.jsonl",
            tokenizer_path=TOKENIZER_PATH,
            output_dir=output_dir,
            max_examples=None,
            max_new_tokens=384
            if any(key in split for key in ("iterative", "unary_count"))
            else 64,
            seed=SEED,
            numeric_tokenization=NUMERIC_TOKENIZATION,
        )
        augment_summary(Path(result["predictions_path"]), Path(result["summary_path"]))
    prune_intermediate_checkpoints(run_dir)


class GruActionModel(nn.Module):
    def __init__(
        self, *, vocab_size: int, hidden_size: int, action_count: int, pad_id: int
    ) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, hidden_size, padding_idx=pad_id)
        self.gru = nn.GRU(hidden_size, hidden_size, batch_first=True)
        self.output = nn.Linear(hidden_size, action_count)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(input_ids)
        hidden, _state = self.gru(embedded)
        return self.output(hidden)


ACTION_VOCAB = {
    "<pad>": 0,
    "<end>": 1,
    **{obj: index + 2 for index, obj in enumerate(ALL_OBJECTS)},
}
ACTION_IDS = {"TAKE": 0, "STOP": 1}


def train_and_eval_gru_action_control() -> None:
    run_dir = RUNS_DIR / "gru_action_control"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "checkpoint.pt"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if not checkpoint_path.exists():
        input_ids, labels = gru_action_dataset(
            TRAIN_COUNTS, TRAIN_OBJECTS, repeat=400, max_length=32
        )
        loader = DataLoader(
            TensorDataset(input_ids, labels),
            batch_size=BATCH_SIZE,
            shuffle=True,
            generator=torch.Generator().manual_seed(SEED + 300),
            drop_last=True,
        )
        model = GruActionModel(
            vocab_size=len(ACTION_VOCAB),
            hidden_size=128,
            action_count=len(ACTION_IDS),
            pad_id=ACTION_VOCAB["<pad>"],
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
        iterator = iter(loader)
        metrics = []
        for step in range(1, 3000 + 1):
            try:
                batch_input_ids, batch_labels = next(iterator)
            except StopIteration:
                iterator = iter(loader)
                batch_input_ids, batch_labels = next(iterator)
            batch_input_ids = batch_input_ids.to(device)
            batch_labels = batch_labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch_input_ids)
            loss = F.cross_entropy(
                logits.view(-1, logits.shape[-1]),
                batch_labels.view(-1),
                ignore_index=IGNORE_INDEX,
            )
            if not torch.isfinite(loss):
                raise ValueError(
                    f"Non-finite GRU action loss at step {step}: {loss.item()}"
                )
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(
                model.parameters(), GRAD_CLIP_NORM
            )
            optimizer.step()
            if step % 1000 == 0:
                metrics.append(
                    {
                        "step": step,
                        "train_loss": float(loss.item()),
                        "grad_norm": float(grad_norm),
                    }
                )
        (run_dir / "metrics.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in metrics),
            encoding="utf-8",
        )
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "vocab_size": len(ACTION_VOCAB),
                "hidden_size": 128,
                "action_count": len(ACTION_IDS),
                "pad_id": ACTION_VOCAB["<pad>"],
            },
            checkpoint_path,
        )
    for split, counts in {
        "gru_action_seen": TRAIN_COUNTS,
        "gru_action_length_ood": LENGTH_OOD_COUNTS,
        "gru_action_far_ood": FAR_COUNTS,
    }.items():
        summary_path = run_dir / "eval" / split / "summary.json"
        if summary_path.exists():
            continue
        summary = eval_gru_action(
            checkpoint_path, counts=counts, objects=TRAIN_OBJECTS[:2], device=device
        )
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    (run_dir / "run_result.json").write_text(
        json.dumps(
            {"model": "script_local_gru_action", "steps": 3000},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def gru_action_dataset(
    counts: Sequence[int],
    objects: Sequence[str],
    *,
    repeat: int,
    max_length: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    rows = []
    label_rows = []
    examples = [(n, obj) for n, obj in itertools.product(counts, objects)]
    for index in range(repeat):
        n, obj = examples[index % len(examples)]
        seq = [ACTION_VOCAB[obj] for _ in range(n)] + [ACTION_VOCAB["<end>"]]
        labels = [ACTION_IDS["TAKE"] for _ in range(n)] + [ACTION_IDS["STOP"]]
        pad = max_length - len(seq)
        rows.append(seq + [ACTION_VOCAB["<pad>"]] * pad)
        label_rows.append(labels + [IGNORE_INDEX] * pad)
    return torch.tensor(rows, dtype=torch.long), torch.tensor(
        label_rows, dtype=torch.long
    )


def eval_gru_action(
    checkpoint_path: Path,
    *,
    counts: Sequence[int],
    objects: Sequence[str],
    device: torch.device,
) -> dict[str, Any]:
    checkpoint = torch.load(checkpoint_path, map_location=device)
    model = GruActionModel(
        vocab_size=int(checkpoint["vocab_size"]),
        hidden_size=int(checkpoint["hidden_size"]),
        action_count=int(checkpoint["action_count"]),
        pad_id=int(checkpoint["pad_id"]),
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    rows = []
    with torch.no_grad():
        for n, obj in itertools.product(counts, objects):
            seq = [ACTION_VOCAB[obj] for _ in range(n)] + [ACTION_VOCAB["<end>"]]
            input_ids = torch.tensor([seq], dtype=torch.long, device=device)
            pred = torch.argmax(model(input_ids), dim=-1)[0].tolist()
            actions = [
                "TAKE" if item == ACTION_IDS["TAKE"] else "STOP" for item in pred
            ]
            consumed = 0
            stopped = False
            for action in actions:
                if action == "TAKE" and consumed < n:
                    consumed += 1
                elif action == "STOP":
                    stopped = True
                    break
                else:
                    break
            rows.append(
                {
                    "n": n,
                    "object": obj,
                    "take_accuracy": sum(a == "TAKE" for a in actions[:n]) / max(n, 1),
                    "stop_accuracy": float(actions[n] == "STOP"),
                    "final_count_correct": float(consumed == n and stopped),
                    "actions": actions,
                }
            )
    return {
        "overall": {
            "count": len(rows),
            "take_accuracy": mean(row["take_accuracy"] for row in rows),
            "stop_accuracy": mean(row["stop_accuracy"] for row in rows),
            "final_external_count": mean(row["final_count_correct"] for row in rows),
            "final_normalized_exact_match": mean(
                row["final_count_correct"] for row in rows
            ),
        },
        "rows": rows,
    }


def eval_take_stop_transformer_environment() -> None:
    run_dir = RUNS_DIR / "take_stop_transformer"
    checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        return
    for split, counts in {
        "take_stop_env_seen": TRAIN_COUNTS,
        "take_stop_env_length_ood": LENGTH_OOD_COUNTS,
        "take_stop_env_far_ood": FAR_COUNTS,
    }.items():
        out_dir = run_dir / "eval" / split
        if (out_dir / "summary.json").exists():
            continue
        rows = eval_transformer_action_environment(
            checkpoint=checkpoint,
            counts=counts,
            objects=TRAIN_OBJECTS[:2],
        )
        write_environment_summary(out_dir, rows)


def eval_transformer_action_environment(
    *,
    checkpoint: Path,
    counts: Sequence[int],
    objects: Sequence[str],
) -> list[dict[str, Any]]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint, tokenizer_path=TOKENIZER_PATH, device=device
    )
    rows = []
    for n, obj in itertools.product(counts, objects):
        head = 0
        actions = []
        for _step in range(max(n + 3, 3)):
            prompt = action_prompt(n=n, obj=obj, head=head)
            action = generate_action(
                model=model, tokenizer=tokenizer, prompt=prompt, device=device
            )
            actions.append(action)
            if action == "TAKE" and head < n:
                head += 1
            elif action == "STOP":
                break
            else:
                break
        rows.append(
            {
                "n": n,
                "object": obj,
                "actions": actions,
                "final_count_correct": float(
                    head == n and actions and actions[-1] == "STOP"
                ),
                "take_accuracy": sum(action == "TAKE" for action in actions[:n])
                / max(n, 1),
                "stop_accuracy": float(len(actions) > n and actions[n] == "STOP"),
            }
        )
    return rows


def eval_matching_action_environment() -> None:
    run_dir = RUNS_DIR / "matching_action"
    checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        return
    for split, counts in {
        "matching_env_seen": TRAIN_COUNTS,
        "matching_env_length_ood": LENGTH_OOD_COUNTS,
    }.items():
        out_dir = run_dir / "eval" / split
        if (out_dir / "summary.json").exists():
            continue
        rows = eval_matching_transformer_environment(
            checkpoint=checkpoint, counts=counts
        )
        write_environment_summary(out_dir, rows)


def eval_matching_transformer_environment(
    *,
    checkpoint: Path,
    counts: Sequence[int],
) -> list[dict[str, Any]]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint, tokenizer_path=TOKENIZER_PATH, device=device
    )
    rows = []
    pairs = (
        [(n, n) for n in counts]
        + [(n, n + 1) for n in counts[:-1]]
        + [(n + 1, n) for n in counts[:-1]]
    )
    for left, right in pairs:
        current_left = left
        current_right = right
        actions = []
        for _step in range(max(left, right) + 3):
            prompt = (
                "MATCH_ACTION\n"
                f"LEFT {object_sequence(current_left, ['x'], separator='space')}\n"
                f"RIGHT {object_sequence(current_right, ['a'], separator='space')}"
            )
            action = generate_action(
                model=model, tokenizer=tokenizer, prompt=prompt, device=device
            )
            actions.append(action)
            if action == "PAIR" and current_left > 0 and current_right > 0:
                current_left -= 1
                current_right -= 1
            elif action in {"SAME", "LEFT_MORE", "RIGHT_MORE"}:
                break
            else:
                break
        expected = (
            matching_oracle_action(left, right)
            if min(left, right) == 0
            else matching_oracle_action(0, right - left)
            if left <= right
            else matching_oracle_action(left - right, 0)
        )
        correct = (
            actions
            and actions[-1] == expected
            and min(current_left, current_right) == 0
        )
        rows.append(
            {
                "left": left,
                "right": right,
                "actions": actions,
                "final_count_correct": float(correct),
            }
        )
    return rows


def generate_action(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    prompt: str,
    device: torch.device,
) -> str:
    generated = generate_answer_ids(
        model=model,
        tokenizer=tokenizer,
        prompt=prompt,
        max_new_tokens=16,
        device=device,
        numeric_tokenization=NUMERIC_TOKENIZATION,
    )
    answer = extract_generated_answer(
        tokenizer.decode(generated, skip_special_tokens=False)
    )
    final = normalize_final_answer(extract_final_answer(answer)).upper()
    if final in {"TAKE", "STOP", "PAIR", "SAME", "LEFT_MORE", "RIGHT_MORE"}:
        return final
    return "INVALID"


def write_environment_summary(output_dir: Path, rows: Sequence[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "overall": {
            "count": len(rows),
            "take_accuracy": mean(float(row.get("take_accuracy", 0.0)) for row in rows),
            "stop_accuracy": mean(float(row.get("stop_accuracy", 0.0)) for row in rows),
            "final_external_count": mean(
                float(row.get("final_count_correct", 0.0)) for row in rows
            ),
            "final_normalized_exact_match": mean(
                float(row.get("final_count_correct", 0.0)) for row in rows
            ),
        },
        "rows": list(rows),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def augment_summary(predictions_path: Path, summary_path: Path) -> None:
    predictions = _read_jsonl_if_exists(predictions_path)
    if not predictions:
        return
    summary = _read_json(summary_path)
    if any(str(row["task_type"]) == "m192c.unary_count" for row in predictions):
        summary["unary_diagnostics"] = unary_diagnostics(predictions)
    if any(str(row["task_type"]) == "m192c.decimal_iterative" for row in predictions):
        summary["iterative_diagnostics"] = iterative_diagnostics(predictions)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def unary_diagnostics(predictions: Sequence[dict[str, Any]]) -> dict[str, float]:
    rows = []
    for row in predictions:
        if str(row["task_type"]) != "m192c.unary_count":
            continue
        expected = extract_final_answer(str(row["expected"]))
        predicted = extract_final_answer(str(row["predicted"]))
        expected_len = unary_length(expected)
        predicted_len = unary_length(predicted)
        rows.append(
            {
                "final_unary_length": float(expected_len == predicted_len),
                "decoded_cardinality": float(expected_len == predicted_len),
                "halt_exact": float(
                    ("HALT" in str(row["predicted"]))
                    == ("HALT" in str(row["expected"]))
                ),
                "state_update_exact": float(
                    unary_state_lengths(str(row["predicted"]))
                    == unary_state_lengths(str(row["expected"]))
                ),
            }
        )
    return average_dicts(rows)


def iterative_diagnostics(predictions: Sequence[dict[str, Any]]) -> dict[str, float]:
    rows = []
    for row in predictions:
        if str(row["task_type"]) != "m192c.decimal_iterative":
            continue
        rows.append(
            {
                "state_exact": float(
                    decimal_states(str(row["predicted"]))
                    == decimal_states(str(row["expected"]))
                ),
                "transition_valid": float(
                    valid_decimal_states(decimal_states(str(row["predicted"])))
                ),
                "halt_exact": float(
                    ("HALT" in str(row["predicted"]))
                    == ("HALT" in str(row["expected"]))
                ),
            }
        )
    return average_dicts(rows)


def unary_state_lengths(text: str) -> list[int]:
    return [
        unary_length(match.group(1))
        for match in re.finditer(r"COUNT_STATE (.*?) REM", text)
    ]


def decimal_states(text: str) -> list[tuple[int, int]]:
    return [
        (int(m.group(1)), int(m.group(2)))
        for m in re.finditer(r"STATE (\d+) REM (\d+)", text)
    ]


def valid_decimal_states(states: Sequence[tuple[int, int]]) -> bool:
    if not states:
        return False
    for (count, rem), (next_count, next_rem) in itertools.pairwise(states):
        if next_count != count + 1 or next_rem != max(0, rem - 1):
            return False
    return True


def analyze_all() -> None:
    payload = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "remote": remote_environment(),
        "runs": {},
    }
    for run_dir in sorted(RUNS_DIR.glob("*")):
        if run_dir.is_dir():
            payload["runs"][run_dir.name] = analyze_run(run_dir)
    payload["sample_efficiency"] = sample_efficiency(payload)
    payload["decision"] = decision(payload)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def analyze_run(run_dir: Path) -> dict[str, Any]:
    payload = {
        "train_config": _read_json_if_exists(run_dir / "train_config.json"),
        "run_result": _read_json_if_exists(run_dir / "run_result.json"),
        "metrics": _read_jsonl_if_exists(run_dir / "metrics.jsonl"),
        "eval": {},
        "probes": _read_json_if_exists(run_dir / "probes" / "cardinality_probe.json"),
    }
    for summary_path in sorted((run_dir / "eval").glob("*/summary.json")):
        summary = _read_json(summary_path)
        overall = summary.get("overall", {})
        payload["eval"][summary_path.parent.name] = {
            "count": int(overall.get("count", 0)),
            "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
            "full_nem": float(overall.get("normalized_exact_match", 0.0)),
            "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
            "take_accuracy": float(overall.get("take_accuracy", 0.0)),
            "stop_accuracy": float(overall.get("stop_accuracy", 0.0)),
            "final_external_count": float(overall.get("final_external_count", 0.0)),
            "unary_diagnostics": summary.get("unary_diagnostics", {}),
            "iterative_diagnostics": summary.get("iterative_diagnostics", {}),
        }
    return payload


def sample_efficiency(analysis: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for regime in ("direct", "concept"):
        for k in EXPANSION_EXAMPLES_PER_COUNT:
            run = analysis.get("runs", {}).get(f"range_{regime}_{k}", {})
            rows.append(
                {
                    "regime": regime,
                    "examples_per_count": k,
                    "training_examples": k * len(LENGTH_OOD_COUNTS),
                    "steps": STEPS["range_expansion"],
                    "seen_final_nem": score(run, "range_expansion_eval_seen_objects"),
                    "heldout_final_nem": score(
                        run, "range_expansion_eval_heldout_objects"
                    ),
                }
            )
    return {
        "rows": rows,
        "direct_examples_to_95": first_examples_to_threshold(rows, "direct", 0.95),
        "concept_examples_to_95": first_examples_to_threshold(rows, "concept", 0.95),
    }


def first_examples_to_threshold(
    rows: Sequence[dict[str, Any]], regime: str, threshold: float
) -> int | None:
    reached = [
        int(row["training_examples"])
        for row in rows
        if row["regime"] == regime and float(row["seen_final_nem"]) >= threshold
    ]
    return min(reached) if reached else None


def decision(analysis: dict[str, Any]) -> str:
    runs = analysis.get("runs", {})
    decimal = score(runs.get("decimal_iterative", {}), "decimal_iterative_length_ood")
    unary = score(runs.get("unary_count", {}), "unary_count_length_ood")
    take_stop = env_score(
        runs.get("take_stop_transformer", {}), "take_stop_env_length_ood"
    )
    gru = env_score(runs.get("gru_action_control", {}), "gru_action_length_ood")
    same = score(runs.get("same_count_length", {}), "same_count_length_ood")
    sample = analysis.get("sample_efficiency", {})
    direct = sample.get("direct_examples_to_95")
    concept = sample.get("concept_examples_to_95")
    if unary >= 0.90 or take_stop >= 0.95:
        return "OUTCOME A/E: procedural counting works when the state/output burden is made compositional or external."
    if gru >= 0.95 and take_stop < 0.95:
        return "OUTCOME D: recurrent action-only control generalizes where Transformer action-only does not."
    if same >= 0.95 and max(decimal, unary, take_stop) < 0.90:
        return "OUTCOME C: SAME_COUNT length generalizes better than explicit count-symbol production."
    if direct and concept and concept * 3 <= direct:
        return "OUTCOME B: concept pretraining dramatically reduces expansion cost."
    return "OUTCOME F: no procedural zero-shot or sample-efficiency benefit was sufficient in this setup."


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    lines = [
        "# M-19.2c Counting State Representation",
        "",
        "## Remote Environment",
        "",
        remote_lines(analysis),
        "",
        "## M-19.2b Starting Point",
        "",
        "M-19.2b restored clean COUNT/SUCC/SAME_COUNT fit to 1.0, but COUNT and iterative 11..20 remained 0.0 for both Transformer and GRU controls.",
        "",
        "## Nuisance/Data Audit",
        "",
        nuisance_table(analysis),
        "",
        "## Decimal Iterative Baseline",
        "",
        metric_table(
            analysis,
            ["decimal_iterative"],
            [
                "decimal_iterative_train_fit",
                "decimal_iterative_seen",
                "decimal_iterative_length_ood",
            ],
        ),
        diagnostics_table(
            analysis,
            "decimal_iterative",
            "decimal_iterative_length_ood",
            "iterative_diagnostics",
        ),
        "",
        "## Unary Counter",
        "",
        metric_table(
            analysis,
            ["unary_count"],
            [
                "unary_count_train_fit",
                "unary_count_seen",
                "unary_count_heldout_object",
                "unary_count_length_ood",
                "unary_count_far_ood",
            ],
        ),
        diagnostics_table(
            analysis, "unary_count", "unary_count_length_ood", "unary_diagnostics"
        ),
        "",
        "## Unary + External Decoder",
        "",
        "Unary external decoder counts the final generated `C` tokens; its score is reported as `decoded_cardinality` in unary diagnostics.",
        "",
        "## External Counter / TAKE-STOP",
        "",
        metric_table(
            analysis,
            ["take_stop_transformer"],
            [
                "take_stop_seen_steps",
                "take_stop_length_steps",
                "take_stop_far_steps",
                "take_stop_env_seen",
                "take_stop_env_length_ood",
                "take_stop_env_far_ood",
            ],
        ),
        "",
        "## Pointer Action-Only",
        "",
        "The TAKE/STOP Transformer is the action-only pointer variant: the model emits only local control actions while the environment moves the pointer and maintains the count.",
        "",
        "## GRU/LSTM Action-Only",
        "",
        env_table(
            analysis,
            ["gru_action_control"],
            ["gru_action_seen", "gru_action_length_ood", "gru_action_far_ood"],
        ),
        "",
        "## Structured Tens/Ones Counter",
        "",
        metric_table(
            analysis,
            ["structured_counter"],
            ["structured_counter_seen", "structured_counter_length_ood"],
        ),
        "",
        "## Unary -> Numeric Decoder",
        "",
        metric_table(
            analysis,
            ["unary_decoder"],
            ["unary_decoder_seen", "unary_decoder_length_ood"],
        ),
        "",
        "## Zero-Shot vs Curriculum Expansion",
        "",
        sample_efficiency_table(analysis),
        "",
        "## Progressive Range Expansion",
        "",
        "Not run as a separate long curriculum; M-19.2c uses few-shot range-expansion curves as the lightweight proxy before spending more GPU hours.",
        "",
        "## Known Successor States Control",
        "",
        "Covered by structured tens/ones and unary-decoder conditions: they separate known local successor operations from unseen rendered decimal states.",
        "",
        "## SAME_COUNT Length OOD",
        "",
        metric_table(
            analysis,
            ["same_count_length"],
            ["same_count_seen", "same_count_length_ood", "same_count_length_heldout"],
        ),
        "",
        "## One-to-One Action Matching",
        "",
        metric_table(
            analysis,
            ["matching_action"],
            [
                "matching_action_seen_steps",
                "matching_action_length_steps",
                "matching_env_seen",
                "matching_env_length_ood",
            ],
        ),
        "",
        "## Representation Probes",
        "",
        representation_probe_table(analysis),
        "",
        "## Sample Efficiency",
        "",
        sample_efficiency_summary(analysis),
        "",
        "## Interpretation",
        "",
        str(analysis.get("decision", "not enough data")),
        "",
        "## Recommended Next Step",
        "",
        recommendation(analysis),
        "",
        "## Checks",
        "",
        f"- remote/local ruff + pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{git_commit()}`",
        "",
    ]
    text = "\n".join(lines)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def metric_table(
    analysis: dict[str, Any], runs: Sequence[str], splits: Sequence[str]
) -> str:
    rows = ["| run | " + " | ".join(splits) + " |", "|---|" + "---:|" * len(splits)]
    for run_name in runs:
        run = analysis.get("runs", {}).get(run_name, {})
        rows.append(
            f"| {run_name} | "
            + " | ".join(f"{combined_score(run, split):.4f}" for split in splits)
            + " |"
        )
    return "\n".join(rows)


def env_table(
    analysis: dict[str, Any], runs: Sequence[str], splits: Sequence[str]
) -> str:
    rows = [
        "| run | split | final external count | TAKE acc | STOP acc |",
        "|---|---|---:|---:|---:|",
    ]
    for run_name in runs:
        run = analysis.get("runs", {}).get(run_name, {})
        for split in splits:
            item = run.get("eval", {}).get(split, {})
            rows.append(
                f"| {run_name} | {split} | {item.get('final_external_count', 0.0):.4f} | "
                f"{item.get('take_accuracy', 0.0):.4f} | {item.get('stop_accuracy', 0.0):.4f} |"
            )
    return "\n".join(rows)


def diagnostics_table(
    analysis: dict[str, Any], run_name: str, split: str, key: str
) -> str:
    diag = (
        analysis.get("runs", {})
        .get(run_name, {})
        .get("eval", {})
        .get(split, {})
        .get(key, {})
    )
    if not diag:
        return ""
    rows = ["", "| diagnostic | value |", "|---|---:|"]
    rows.extend(f"| {name} | {value:.4f} |" for name, value in sorted(diag.items()))
    return "\n".join(rows)


def sample_efficiency_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| regime | examples/count | new examples | seen 11..20 | heldout 11..20 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in analysis.get("sample_efficiency", {}).get("rows", []):
        rows.append(
            f"| {row['regime']} | {row['examples_per_count']} | {row['training_examples']} | "
            f"{row['seen_final_nem']:.4f} | {row['heldout_final_nem']:.4f} |"
        )
    return "\n".join(rows)


def representation_probe_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| run | centroid acc | same-count cosine | diff-count cosine | successor-dir cosine |",
        "|---|---:|---:|---:|---:|",
    ]
    found = False
    for run_name in (
        "global_count_concept",
        "unary_count",
        "take_stop_transformer",
        "structured_counter",
    ):
        probe = analysis.get("runs", {}).get(run_name, {}).get("probes", {})
        if not probe:
            continue
        found = True
        rows.append(
            f"| {run_name} | {probe.get('centroid_probe_accuracy', 0.0):.4f} | "
            f"{probe.get('same_quantity_cosine', 0.0):.4f} | "
            f"{probe.get('different_quantity_cosine', 0.0):.4f} | "
            f"{probe.get('successor_direction_cosine', 0.0):.4f} |"
        )
    if found:
        return "\n".join(rows)
    return "No hidden-state probes were available for this report build."


def sample_efficiency_summary(analysis: dict[str, Any]) -> str:
    sample = analysis.get("sample_efficiency", {})
    return (
        f"- direct examples to 95%: `{sample.get('direct_examples_to_95')}`\n"
        f"- concept-pretrained examples to 95%: `{sample.get('concept_examples_to_95')}`\n"
        "- pretraining cost is reported separately in `global_count_concept/metrics.jsonl`; adaptation cost is the fixed expansion run budget per row."
    )


def nuisance_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| check | value |",
        "|---|---:|",
    ]
    audit = analysis.get("manifest", {}).get("nuisance_audit", {})
    for key, value in sorted(audit.items()):
        rows.append(f"| {key} | {value} |")
    return "\n".join(rows)


def recommendation(analysis: dict[str, Any]) -> str:
    decision_text = str(analysis.get("decision", ""))
    if "OUTCOME A" in decision_text or "OUTCOME E" in decision_text:
        return "Use action-only/external-state counting as the next concrete numeracy interface."
    if "OUTCOME D" in decision_text:
        return "Use a recurrent controller for counting/workspace actions before returning to addition."
    if "OUTCOME B" in decision_text:
        return (
            "Continue concept-first numeracy through progressive curriculum expansion."
        )
    if "OUTCOME C" in decision_text:
        return "Build number symbols on top of cardinality-equivalence training."
    return "Stop demanding zero-shot range transfer from plain textual counting; try structural state/input changes before addition."


def score(run: dict[str, Any], split: str) -> float:
    return float(run.get("eval", {}).get(split, {}).get("final_nem", 0.0))


def env_score(run: dict[str, Any], split: str) -> float:
    return float(run.get("eval", {}).get(split, {}).get("final_external_count", 0.0))


def combined_score(run: dict[str, Any], split: str) -> float:
    item = run.get("eval", {}).get(split, {})
    return float(item.get("final_external_count", item.get("final_nem", 0.0)))


def nuisance_audit(
    datasets: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    prompts = [
        str(example["prompt"])
        for section in datasets.values()
        for examples in section.values()
        for example in examples
    ]
    return {
        "prompt_count": len(prompts),
        "forbidden_prompt_count": sum(
            prompt_has_forbidden_marker(prompt) for prompt in prompts
        ),
        "contains_case": any("CASE" in prompt for prompt in prompts),
        "contains_train_eval_marker": any(
            re.search(r"\b(TRAIN|EVAL|SPLIT|SEED)\b", prompt) for prompt in prompts
        ),
    }


def prompt_has_forbidden_marker(prompt: str) -> bool:
    return any(
        re.search(pattern, prompt, flags=re.IGNORECASE)
        for pattern in FORBIDDEN_PROMPT_PATTERNS
    )


def audit_examples(examples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    prompts = [str(example["prompt"]) for example in examples]
    return {
        "count": len(examples),
        "unique_prompts": len(set(prompts)),
        "duplicate_prompt_count": len(prompts) - len(set(prompts)),
        "task_type_counts": dict(
            Counter(str(example["task_type"]) for example in examples)
        ),
        "forbidden_prompt_count": sum(
            prompt_has_forbidden_marker(prompt) for prompt in prompts
        ),
    }


def full_count_leakage(train: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {
        name: sum(
            bool(example.get("metadata", {}).get("full_count"))
            and int(example.get("metadata", {}).get("n", -1)) in LENGTH_OOD_COUNTS
            for example in examples
        )
        for name, examples in train.items()
    }


def average_dicts(rows: Sequence[dict[str, float]]) -> dict[str, float]:
    keys = sorted({key for row in rows for key in row})
    return {key: mean(row.get(key, 0.0) for row in rows) for key in keys}


def final_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    return checkpoints[-1] if checkpoints else None


def prune_intermediate_checkpoints(run_dir: Path) -> None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    for checkpoint in checkpoints[:-1]:
        checkpoint.unlink(missing_ok=True)


def required_token_id(tokenizer: ByteLevelBpeTokenizer, token: str) -> int:
    token_id = tokenizer.token_to_id(token)
    if token_id is None:
        raise ValueError(f"Missing tokenizer token: {token}")
    return token_id


def _write_jsonl(path: Path, examples: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False, sort_keys=True))
            file.write("\n")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> Any:
    return _read_json(path) if path.exists() else {}


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def remote_lines(analysis: dict[str, Any]) -> str:
    remote = analysis.get("remote", {})
    return "\n".join(
        [
            f"- hostname: `{remote.get('hostname', 'unknown')}`",
            f"- GPU: `{remote.get('gpu', 'unknown')}`",
            f"- CUDA visible: `{remote.get('cuda_visible', 'unknown')}`",
            f"- commit SHA: `{remote.get('git_commit', git_commit())}`",
        ]
    )


def remote_environment() -> dict[str, Any]:
    gpu = "unavailable"
    cuda_visible = False
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            gpu = result.stdout.strip()
            cuda_visible = True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {
        "hostname": socket.gethostname(),
        "gpu": gpu,
        "cuda_visible": cuda_visible,
        "git_commit": git_commit(),
        "git_branch": subprocess.getoutput("git branch --show-current"),
    }


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


if __name__ == "__main__":
    main()
