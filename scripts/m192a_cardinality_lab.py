from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import socket
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

from ai_brain.eval.generation import build_inference_input_ids, load_model_for_inference
from ai_brain.eval.runner import eval_lm
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m192a_cardinality_lab"
RUNS_DIR = ROOT / "runs" / "m192a_cardinality_lab"
DOC_PATH = ROOT / "docs" / "m192a_cardinality_formation_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m192a_cardinality_formation_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 192100
MODEL_CONFIG = "arithmetic_3m"
POSITION_ENCODING = "relative"
NUMERIC_TOKENIZATION = "digit_safe"
BATCH_SIZE = 8
SEQUENCE_LENGTH = 512
POINTER_SEQUENCE_LENGTH = 768
LOSS_MODE = "answer-only"
LEARNING_RATE = 3e-4
GRAD_CLIP_NORM = 1.0

TRAIN_COUNTS = tuple(range(11))
LENGTH_OOD_COUNTS = tuple(range(11, 21))
SCAFFOLD_COUNTS = tuple(range(21))
TRAIN_OBJECTS = ("x", "a", "k", "m", "n")
HELDOUT_OBJECTS = ("q", "z", "w", "y")
SEPARATORS = ("space", "bar")
OOD_SEPARATORS = ("comma", "slash")
STEPS = {
    "global_count": 9000,
    "local_successor_strict": 6000,
    "local_successor_scaffolded": 6000,
    "iterative_count": 9000,
    "pointer_tape": 9000,
    "matching": 9000,
    "hybrid_strict": 12000,
    "hybrid_scaffolded": 12000,
}


@dataclass(frozen=True)
class TrainSpec:
    name: str
    train_path: Path
    eval_path: Path
    steps: int
    seed: int
    sequence_length: int = SEQUENCE_LENGTH


def main() -> None:
    parser = argparse.ArgumentParser(description="M-19.2a cardinality formation lab.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-main")
    subparsers.add_parser("run-probes")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-main":
        run_main()
    elif args.command == "run-probes":
        run_probes()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_main()
        run_probes()
        analyze_all()
        build_report(checks_passed=False)


def prepare_datasets() -> None:
    rng = random.Random(SEED)
    eval_splits = build_eval_splits(rng)
    eval_prompts = {
        str(example["prompt"])
        for examples in eval_splits.values()
        for example in examples
    }
    trains = build_train_sets(rng, blocked_prompts=eval_prompts)

    for name, examples in trains.items():
        _write_jsonl(DATASET_DIR / "train" / f"{name}.jsonl", examples)
    for name, examples in eval_splits.items():
        _write_jsonl(DATASET_DIR / "eval" / f"{name}.jsonl", examples)

    manifest = {
        "kind": "m192a_cardinality_formation_lab",
        "seed": SEED,
        "model_config": MODEL_CONFIG,
        "position_encoding": POSITION_ENCODING,
        "numeric_tokenization": NUMERIC_TOKENIZATION,
        "train_counts": list(TRAIN_COUNTS),
        "length_ood_counts": list(LENGTH_OOD_COUNTS),
        "scaffold_counts": list(SCAFFOLD_COUNTS),
        "train_objects": list(TRAIN_OBJECTS),
        "heldout_objects": list(HELDOUT_OBJECTS),
        "tokenization_audit": tokenization_audit(),
        "train_sets": {
            name: audit_examples(examples) for name, examples in trains.items()
        },
        "eval_splits": {
            name: audit_examples(examples) for name, examples in eval_splits.items()
        },
        "prompt_intersections": prompt_intersections(trains, eval_splits),
        "strict_full_count_11_20_in_train": {
            name: full_count_ood_seen(examples) for name, examples in trains.items()
        },
    }
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_main() -> None:
    specs = [
        TrainSpec(
            name=name,
            train_path=DATASET_DIR / "train" / f"{name}.jsonl",
            eval_path=DATASET_DIR / "eval" / "seen_count_seen_object.jsonl",
            steps=STEPS[name],
            seed=SEED + index,
            sequence_length=POINTER_SEQUENCE_LENGTH
            if name == "pointer_tape"
            else SEQUENCE_LENGTH,
        )
        for index, name in enumerate(STEPS)
    ]
    for spec in specs:
        _train_and_eval(spec, eval_splits=eval_splits_for_run(spec.name))
    analyze_all()
    build_report(checks_passed=False)


def run_probes() -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    for name in ("global_count", best_method(analysis)):
        checkpoint = final_checkpoint(RUNS_DIR / name)
        if checkpoint is None:
            continue
        payload = representation_probe(checkpoint)
        out_dir = RUNS_DIR / name / "probes"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "quantity_probe.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    analyze_all()
    build_report(checks_passed=False)


def analyze_all() -> None:
    payload = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "remote": remote_environment(),
        "runs": {},
    }
    for run_dir in sorted(RUNS_DIR.glob("*")):
        if run_dir.is_dir():
            payload["runs"][run_dir.name] = analyze_run(run_dir)
    payload["decision"] = decision(payload)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    lines = [
        "# M-19.2a Cardinality Formation Laboratory",
        "",
        "## Remote Environment",
        "",
        remote_lines(analysis),
        "",
        "## M-19.2 Failure Audit",
        "",
        (
            "M-19.2 failed the COUNT gate: saturated count-only reached seen "
            "0.9091, held-out object 0.6667, and held-out format 0.1818. "
            "M-19.2a isolates cardinality formation before any addition work."
        ),
        "",
        "## Tokenization Audit",
        "",
        tokenization_table(analysis),
        "",
        "## Evaluation Axis Definitions",
        "",
        axis_table(analysis),
        "",
        "## Global Count",
        "",
        metric_table(analysis, ["global_count"], primary_axes()),
        "",
        "## Local Successor",
        "",
        metric_table(
            analysis,
            ["local_successor_strict", "local_successor_scaffolded"],
            [
                "local_successor_seen",
                "local_successor_heldout_object",
                "successor_11_20",
            ],
        ),
        "",
        "## Iterative Counting",
        "",
        metric_table(analysis, ["iterative_count"], primary_axes()),
        trace_table(analysis, ["iterative_count"], ["iterative_count_length_ood"]),
        "",
        "## Pointer/Tape Counting",
        "",
        metric_table(analysis, ["pointer_tape"], primary_axes()),
        trace_table(analysis, ["pointer_tape"], ["pointer_count_length_ood"]),
        "",
        "## Peano/Successor Control",
        "",
        metric_table(
            analysis,
            [
                "local_successor_strict",
                "local_successor_scaffolded",
                "hybrid_scaffolded",
            ],
            ["peano_seen", "peano_length_ood", "successor_11_20"],
        ),
        "",
        "## One-to-One Matching",
        "",
        metric_table(
            analysis,
            ["matching"],
            ["matching_seen", "matching_heldout_object", "matching_length_ood"],
        ),
        trace_table(analysis, ["matching"], ["matching_length_ood"]),
        "",
        "## Hybrid Curriculum",
        "",
        metric_table(analysis, ["hybrid_strict", "hybrid_scaffolded"], primary_axes()),
        "",
        "## Object Identity Invariance",
        "",
        metric_table(
            analysis,
            list(STEPS),
            [
                "seen_count_heldout_object",
                "mixed_object_identity",
                "reordered_object_identity",
            ],
        ),
        "",
        "## Length OOD 11..20",
        "",
        metric_table(
            analysis,
            list(STEPS),
            [
                "iterative_count_length_ood",
                "global_count_length_ood",
                "matching_length_ood",
            ],
        ),
        "",
        "## Format Decomposition",
        "",
        metric_table(
            analysis,
            list(STEPS),
            ["separator_ood", "prompt_syntax_ood"],
        ),
        "",
        "## Representation Probes",
        "",
        probe_table(analysis),
        "",
        "## Sample Efficiency",
        "",
        sample_efficiency_table(analysis),
        "",
        "## Capacity Check if gated",
        "",
        capacity_status(analysis),
        "",
        "## Recurrent Control if gated",
        "",
        recurrent_status(analysis),
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
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{git_commit()}`",
        "",
    ]
    text = "\n".join(lines)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def build_train_sets(
    rng: random.Random,
    *,
    blocked_prompts: set[str],
) -> dict[str, list[dict[str, Any]]]:
    global_count = repeat_examples(
        [
            count_example(q, obj, sep, syntax="canonical", index=i)
            for i, (q, obj, sep) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS, SEPARATORS)
            )
        ],
        7000,
    )
    local_strict = repeat_examples(
        [
            successor_example(q, obj, syntax="canonical", index=i)
            for i, (q, obj) in enumerate(itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS))
            if q < 10
        ]
        + [peano_example(q, index=1000 + q) for q in TRAIN_COUNTS if q < 10],
        5000,
    )
    local_scaffolded = repeat_examples(
        [
            successor_example(q, obj, syntax="canonical", index=i)
            for i, (q, obj) in enumerate(
                itertools.product(SCAFFOLD_COUNTS[:-1], TRAIN_OBJECTS)
            )
        ]
        + [peano_example(q, index=2000 + q) for q in SCAFFOLD_COUNTS[:-1]],
        5000,
    )
    iterative = repeat_examples(
        [
            iterative_count_example(q, obj, sep, index=i)
            for i, (q, obj, sep) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS, SEPARATORS)
            )
        ],
        7000,
    )
    pointer = repeat_examples(
        [
            pointer_tape_example(q, obj, sep, index=i)
            for i, (q, obj, sep) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS, SEPARATORS)
            )
        ],
        7000,
    )
    matching = repeat_examples(
        matching_examples(rng, count=1400, counts=TRAIN_COUNTS, heldout=False),
        7000,
    )
    hybrid_strict = balanced_repeat(
        [
            iterative,
            local_strict,
            matching,
            more_less_examples(rng, count=1600, counts=TRAIN_COUNTS, heldout=False),
            digit_state_examples(TRAIN_COUNTS),
        ],
        9000,
    )
    hybrid_scaffolded = balanced_repeat(
        [
            iterative,
            local_scaffolded,
            matching,
            more_less_examples(rng, count=1600, counts=TRAIN_COUNTS, heldout=False),
            digit_state_examples(SCAFFOLD_COUNTS),
        ],
        9000,
    )
    result = {
        "global_count": global_count,
        "local_successor_strict": local_strict,
        "local_successor_scaffolded": local_scaffolded,
        "iterative_count": iterative,
        "pointer_tape": pointer,
        "matching": matching,
        "hybrid_strict": hybrid_strict,
        "hybrid_scaffolded": hybrid_scaffolded,
    }
    return {
        name: ensure_prompt_disjoint(examples, blocked_prompts)
        for name, examples in result.items()
    }


def build_eval_splits(rng: random.Random) -> dict[str, list[dict[str, Any]]]:
    return {
        "seen_count_seen_object": [
            count_example(q, obj, "space", syntax="canonical", index=10_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS[:3])
            )
        ],
        "seen_count_heldout_object": [
            count_example(q, obj, "space", syntax="canonical", index=11_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(TRAIN_COUNTS, HELDOUT_OBJECTS)
            )
        ],
        "mixed_object_identity": [
            count_example(q, None, "space", syntax="canonical", index=12_000 + i)
            for i, q in enumerate(TRAIN_COUNTS)
        ],
        "reordered_object_identity": reordered_examples(),
        "separator_ood": [
            count_example(q, obj, sep, syntax="canonical", index=13_000 + i)
            for i, (q, obj, sep) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS[:3], OOD_SEPARATORS)
            )
        ],
        "prompt_syntax_ood": [
            count_example(q, obj, "space", syntax="alternate", index=14_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS[:3])
            )
        ],
        "global_count_length_ood": [
            count_example(q, obj, "space", syntax="canonical", index=15_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS[:3])
            )
        ],
        "local_successor_seen": [
            successor_example(q, obj, syntax="canonical", index=16_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(TRAIN_COUNTS[:-1], TRAIN_OBJECTS[:3])
            )
        ],
        "local_successor_heldout_object": [
            successor_example(q, obj, syntax="canonical", index=17_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(TRAIN_COUNTS[:-1], HELDOUT_OBJECTS)
            )
        ],
        "successor_11_20": [
            successor_example(q, obj, syntax="canonical", index=18_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(range(10, 20), TRAIN_OBJECTS[:3])
            )
        ],
        "iterative_count_seen": [
            iterative_count_example(q, obj, "space", index=19_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS[:3])
            )
        ],
        "iterative_count_length_ood": [
            iterative_count_example(q, obj, "space", index=20_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS[:2])
            )
        ],
        "pointer_count_seen": [
            pointer_tape_example(q, obj, "space", index=21_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS[:3])
            )
        ],
        "pointer_count_length_ood": [
            pointer_tape_example(q, obj, "space", index=22_000 + i)
            for i, (q, obj) in enumerate(
                itertools.product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS[:2])
            )
        ],
        "peano_seen": [peano_example(q, index=23_000 + q) for q in TRAIN_COUNTS],
        "peano_length_ood": [
            peano_example(q, index=24_000 + q) for q in LENGTH_OOD_COUNTS
        ],
        "matching_seen": matching_examples(
            rng,
            count=140,
            counts=TRAIN_COUNTS,
            heldout=False,
            index_offset=25_000,
        ),
        "matching_heldout_object": matching_examples(
            rng,
            count=140,
            counts=TRAIN_COUNTS,
            heldout=True,
            index_offset=26_000,
        ),
        "matching_length_ood": matching_examples(
            rng,
            count=120,
            counts=LENGTH_OOD_COUNTS,
            heldout=True,
            index_offset=27_000,
        ),
        "more_less": more_less_examples(
            rng,
            count=160,
            counts=TRAIN_COUNTS,
            heldout=True,
            index_offset=28_000,
        ),
    }


def eval_splits_for_run(name: str) -> dict[str, Path]:
    all_splits = {
        split: DATASET_DIR / "eval" / f"{split}.jsonl"
        for split in [
            "seen_count_seen_object",
            "seen_count_heldout_object",
            "mixed_object_identity",
            "reordered_object_identity",
            "separator_ood",
            "prompt_syntax_ood",
            "global_count_length_ood",
            "local_successor_seen",
            "local_successor_heldout_object",
            "successor_11_20",
            "iterative_count_seen",
            "iterative_count_length_ood",
            "pointer_count_seen",
            "pointer_count_length_ood",
            "peano_seen",
            "peano_length_ood",
            "matching_seen",
            "matching_heldout_object",
            "matching_length_ood",
            "more_less",
        ]
    }
    if name.startswith("local_successor"):
        return {
            key: all_splits[key]
            for key in [
                "local_successor_seen",
                "local_successor_heldout_object",
                "successor_11_20",
                "peano_seen",
                "peano_length_ood",
            ]
        }
    if name == "matching":
        return {
            key: all_splits[key]
            for key in [
                "matching_seen",
                "matching_heldout_object",
                "matching_length_ood",
                "more_less",
            ]
        }
    if name == "pointer_tape":
        return {
            key: all_splits[key]
            for key in [
                "pointer_count_seen",
                "pointer_count_length_ood",
                "seen_count_heldout_object",
                "mixed_object_identity",
                "separator_ood",
                "prompt_syntax_ood",
                "global_count_length_ood",
            ]
        }
    if name == "iterative_count":
        return {
            key: all_splits[key]
            for key in [
                "iterative_count_seen",
                "iterative_count_length_ood",
                "seen_count_heldout_object",
                "mixed_object_identity",
                "separator_ood",
                "prompt_syntax_ood",
                "global_count_length_ood",
            ]
        }
    return {
        key: all_splits[key]
        for key in [
            "seen_count_seen_object",
            "seen_count_heldout_object",
            "mixed_object_identity",
            "reordered_object_identity",
            "separator_ood",
            "prompt_syntax_ood",
            "global_count_length_ood",
            "iterative_count_seen",
            "iterative_count_length_ood",
            "pointer_count_seen",
            "pointer_count_length_ood",
            "matching_seen",
            "matching_heldout_object",
            "matching_length_ood",
            "more_less",
            "peano_seen",
            "peano_length_ood",
        ]
    }


def primary_axes() -> list[str]:
    return [
        "seen_count_seen_object",
        "seen_count_heldout_object",
        "mixed_object_identity",
        "reordered_object_identity",
        "separator_ood",
        "global_count_length_ood",
        "more_less",
    ]


def obj_token(name: str) -> str:
    return name


def object_sequence(
    count: int,
    *,
    obj: str | None,
    sep: str,
    rng: random.Random | None = None,
) -> str:
    if count == 0:
        return "EMPTY"
    rng = rng or random.Random(SEED + count)
    objects = (
        [obj_token(obj)] * count
        if obj is not None
        else [
            obj_token(rng.choice(TRAIN_OBJECTS + HELDOUT_OBJECTS)) for _ in range(count)
        ]
    )
    if sep == "space":
        return " ".join(objects)
    if sep == "bar":
        return " | ".join(objects)
    if sep == "comma":
        return ", ".join(objects)
    if sep == "slash":
        return " / ".join(objects)
    raise ValueError(f"Unknown separator: {sep}")


def count_example(
    count: int,
    obj: str | None,
    sep: str,
    *,
    syntax: str,
    index: int,
) -> dict[str, Any]:
    surface = object_sequence(count, obj=obj, sep=sep)
    if syntax == "canonical":
        prompt = f"COUNT_SET\nITEMS {surface}\nCASE {index}"
    elif syntax == "alternate":
        prompt = f"CARDINALITY?\nBAG {surface}\nQUERY TOTAL\nCASE {index}"
    else:
        raise ValueError(f"Unknown count syntax: {syntax}")
    return record(
        index,
        "m192a.count.global",
        prompt,
        f"FINAL {count}",
        count=count,
        object_family=obj or "mixed",
        separator=sep,
        syntax=syntax,
        procedure="global_count",
    )


def successor_example(
    count: int, obj: str, *, syntax: str, index: int
) -> dict[str, Any]:
    if syntax == "canonical":
        prompt = f"COUNT_STATE {count}\nNEXT_OBJECT {obj_token(obj)}\nCASE {index}"
    else:
        prompt = (
            f"ADD_NEXT_OBJECT\nSTATE {count}\nOBJECT {obj_token(obj)}\nCASE {index}"
        )
    return record(
        index,
        "m192a.successor.local",
        prompt,
        f"FINAL COUNT_STATE {count + 1}",
        count=count,
        next_count=count + 1,
        object_family=obj,
        syntax=syntax,
        procedure="local_successor",
    )


def peano_example(count: int, *, index: int) -> dict[str, Any]:
    prompt = f"PEANO_DEPTH\nTERM {peano(count)}\nCASE {index}"
    return record(
        index,
        "m192a.peano.depth",
        prompt,
        f"FINAL {count}",
        count=count,
        procedure="peano",
    )


def iterative_count_example(
    count: int, obj: str, sep: str, *, index: int
) -> dict[str, Any]:
    surface = object_sequence(count, obj=obj, sep=sep)
    lines = [f"STATE COUNT 0 REM {count}"]
    for step in range(count):
        lines.append("TAKE_ONE")
        lines.append(f"STATE COUNT {step + 1} REM {count - step - 1}")
    lines.append("HALT")
    lines.append(f"FINAL {count}")
    return record(
        index,
        "m192a.count.iterative",
        f"ITER_COUNT\nITEMS {surface}\nCASE {index}",
        "\n".join(lines),
        count=count,
        object_family=obj,
        separator=sep,
        procedure="iterative",
    )


def pointer_tape_example(
    count: int, obj: str, sep: str, *, index: int
) -> dict[str, Any]:
    surface = object_sequence(count, obj=obj, sep=sep)
    base = [obj_token(obj)] * count
    lines = []
    for head in range(count + 1):
        tape = base.copy()
        tape.insert(head, "^")
        lines.append(f"STATE COUNT {head} HEAD {head} TAPE {' '.join(tape)}")
    lines.append(f"HALT COUNT {count}")
    lines.append(f"FINAL {count}")
    return record(
        index,
        "m192a.count.pointer_tape",
        f"POINTER_COUNT\nTAPE {surface}\nCASE {index}",
        "\n".join(lines),
        count=count,
        object_family=obj,
        separator=sep,
        procedure="pointer_tape",
    )


def matching_examples(
    rng: random.Random,
    *,
    count: int,
    counts: Sequence[int],
    heldout: bool,
    index_offset: int = 0,
) -> list[dict[str, Any]]:
    objects = HELDOUT_OBJECTS if heldout else TRAIN_OBJECTS
    examples = []
    for offset in range(count):
        left_count = rng.choice(counts)
        if offset % 3 == 0:
            right_count = left_count
        elif offset % 3 == 1:
            right_count = max(min(counts), left_count - 1)
        else:
            right_count = min(max(counts), left_count + 1)
        left_items = [obj_token(rng.choice(objects)) for _ in range(left_count)]
        right_items = [obj_token(rng.choice(objects)) for _ in range(right_count)]
        pairs = [
            f"PAIR {left} {right}"
            for left, right in zip(left_items, right_items, strict=False)
        ]
        left_remain = max(0, left_count - right_count)
        right_remain = max(0, right_count - left_count)
        final = (
            "SAME"
            if left_remain == right_remain == 0
            else ("LEFT_MORE" if left_remain > 0 else "RIGHT_MORE")
        )
        index = index_offset + offset
        answer = "\n".join(
            pairs
            + [
                f"LEFT_REMAIN {left_remain}",
                f"RIGHT_REMAIN {right_remain}",
                f"FINAL {final}",
            ]
        )
        examples.append(
            record(
                index,
                "m192a.matching.one_to_one",
                "MATCH_COUNT\n"
                f"LEFT {' '.join(left_items) if left_items else 'EMPTY'}\n"
                f"RIGHT {' '.join(right_items) if right_items else 'EMPTY'}\n"
                f"CASE {index}",
                answer,
                left_count=left_count,
                right_count=right_count,
                heldout=heldout,
                procedure="matching",
            )
        )
    return examples


def more_less_examples(
    rng: random.Random,
    *,
    count: int,
    counts: Sequence[int],
    heldout: bool,
    index_offset: int = 0,
) -> list[dict[str, Any]]:
    objects = HELDOUT_OBJECTS if heldout else TRAIN_OBJECTS
    examples = []
    for offset in range(count):
        left = rng.choice(counts)
        right = rng.choice(counts)
        final = "SAME" if left == right else ("LEFT" if left > right else "RIGHT")
        index = index_offset + offset
        examples.append(
            record(
                index,
                "m192a.compare.more_less",
                "MORE_LESS\n"
                f"LEFT {object_sequence(left, obj=rng.choice(objects), sep='space')}\n"
                f"RIGHT {object_sequence(right, obj=rng.choice(objects), sep='bar')}\n"
                f"CASE {index}",
                f"FINAL {final}",
                left_count=left,
                right_count=right,
                heldout=heldout,
                procedure="more_less",
            )
        )
    return examples


def digit_state_examples(counts: Sequence[int]) -> list[dict[str, Any]]:
    examples = []
    for index, count in enumerate(counts):
        examples.append(
            record(
                index,
                "m192a.digit_state.state_to_symbol",
                f"STATE_TO_SYMBOL\nCOUNT_STATE {count}\nCASE {30_000 + index}",
                f"FINAL {count}",
                count=count,
                procedure="digit_state",
            )
        )
        examples.append(
            record(
                index + 1000,
                "m192a.digit_state.symbol_to_state",
                f"SYMBOL_TO_STATE\nSYMBOL {count}\nCASE {31_000 + index}",
                f"FINAL COUNT_STATE {count}",
                count=count,
                procedure="digit_state",
            )
        )
    return examples


def reordered_examples() -> list[dict[str, Any]]:
    examples = []
    rng = random.Random(SEED + 99)
    for index, count in enumerate(TRAIN_COUNTS):
        objects = [
            obj_token(rng.choice(TRAIN_OBJECTS + HELDOUT_OBJECTS)) for _ in range(count)
        ]
        forward = " ".join(objects) if objects else "EMPTY"
        backward = " ".join(reversed(objects)) if objects else "EMPTY"
        examples.append(
            record(
                32_000 + index,
                "m192a.invariance.reordered",
                f"SAME_CARDINALITY_AFTER_REORDER\nA {forward}\nB {backward}\nCASE {index}",
                f"FINAL {count}",
                count=count,
                procedure="reordered_identity",
            )
        )
    return examples


def peano(count: int) -> str:
    if count == 0:
        return "ZERO"
    return "S(" * count + "ZERO" + ")" * count


def record(
    index: int,
    task_type: str,
    prompt: str,
    answer: str,
    **metadata: Any,
) -> dict[str, Any]:
    return {
        "id": f"{task_type}:{index:06d}",
        "task_type": task_type,
        "prompt": prompt,
        "answer": answer,
        "metadata": metadata,
    }


def ensure_prompt_disjoint(
    examples: Sequence[dict[str, Any]],
    blocked_prompts: set[str],
) -> list[dict[str, Any]]:
    result = []
    for example in examples:
        item = dict(example)
        if str(item["prompt"]) in blocked_prompts:
            item["prompt"] = f"{item['prompt']}\nTRAIN_ONLY yes"
            metadata = dict(item.get("metadata", {}))
            metadata["prompt_variant"] = "train_only_disjoint"
            item["metadata"] = metadata
        result.append(item)
    return result


def repeat_examples(
    examples: Sequence[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    result = []
    for index in range(count):
        item = dict(examples[index % len(examples)])
        item["id"] = f"{item['task_type']}:repeat:{index:06d}"
        result.append(item)
    return result


def balanced_repeat(
    pools: Sequence[Sequence[dict[str, Any]]],
    count: int,
) -> list[dict[str, Any]]:
    result = []
    cursors = [0 for _ in pools]
    while len(result) < count:
        for pool_index, pool in enumerate(pools):
            if len(result) >= count:
                break
            item = dict(pool[cursors[pool_index] % len(pool)])
            item["id"] = f"{item['task_type']}:balanced:{len(result):06d}"
            result.append(item)
            cursors[pool_index] += 1
    return result


def tokenization_audit() -> list[dict[str, Any]]:
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    rows = []
    for obj in TRAIN_OBJECTS + HELDOUT_OBJECTS:
        for count in range(21):
            surface = object_sequence(count, obj=obj, sep="space")
            encoded = tokenizer.encode_with_offsets(
                surface,
                numeric_tokenization=NUMERIC_TOKENIZATION,
            )
            spans = object_spans(surface)
            tokenized_spans = sum(
                any(start <= offset_start < end for offset_start, _ in encoded.offsets)
                for start, end in spans
            )
            rows.append(
                {
                    "object": obj,
                    "count": count,
                    "surface": surface,
                    "token_count": len(encoded.ids),
                    "object_span_count": len(spans),
                    "tokenized_object_span_count": tokenized_spans,
                    "single_aggregate_token": count >= 2 and len(encoded.ids) <= 1,
                }
            )
    mixed = object_sequence(5, obj=None, sep="space")
    encoded = tokenizer.encode_with_offsets(
        mixed, numeric_tokenization=NUMERIC_TOKENIZATION
    )
    rows.append(
        {
            "object": "mixed",
            "count": 5,
            "surface": mixed,
            "token_count": len(encoded.ids),
            "object_span_count": len(object_spans(mixed)),
            "tokenized_object_span_count": len(object_spans(mixed)),
            "single_aggregate_token": False,
        }
    )
    return rows


def object_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\b[xakmnqzwy]\b", text)]


def _train_and_eval(spec: TrainSpec, *, eval_splits: dict[str, Path]) -> None:
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
                cache_dir=ROOT / "cache" / "tokenized_m192a",
            )
        )
        (run_dir / "run_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        raise RuntimeError(f"No checkpoint produced for {spec.name}")
    for split, eval_path in eval_splits.items():
        summary_path = run_dir / "eval" / split / "summary.json"
        if summary_path.exists():
            continue
        result = eval_lm(
            checkpoint_path=checkpoint,
            eval_path=eval_path,
            tokenizer_path=TOKENIZER_PATH,
            output_dir=run_dir / "eval" / split,
            max_examples=None,
            max_new_tokens=max_new_tokens_for_split(split),
            seed=SEED,
            numeric_tokenization=NUMERIC_TOKENIZATION,
        )
        augment_trace_summary(
            Path(result["predictions_path"]),
            Path(result["summary_path"]),
        )
    evaluate_sample_efficiency(run_dir, eval_splits)
    prune_intermediate_checkpoints(run_dir)


def max_new_tokens_for_split(split: str) -> int:
    if "pointer" in split:
        return 1800
    if "iterative" in split:
        return 512
    if "matching" in split:
        return 256
    return 64


def augment_trace_summary(predictions_path: Path, summary_path: Path) -> None:
    predictions = _read_jsonl_if_exists(predictions_path)
    if not predictions:
        return
    diagnostics = [
        trace_diagnostics(p["expected"], p["predicted"]) for p in predictions
    ]
    if not any(diagnostics):
        return
    summary = _read_json(summary_path)
    summary["trace_diagnostics"] = average_diagnostics(diagnostics)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def trace_diagnostics(expected: str, predicted: str) -> dict[str, float] | None:
    if "STATE COUNT" in expected and "REM" in expected:
        expected_states = iterative_state_pairs(expected)
        predicted_states = iterative_state_pairs(predicted)
        return {
            "state_count_exact": float(
                [c for c, _r in predicted_states] == [c for c, _r in expected_states]
            ),
            "remaining_exact": float(
                [r for _c, r in predicted_states] == [r for _c, r in expected_states]
            ),
            "halt_exact": float(("HALT" in predicted) == ("HALT" in expected)),
            "step_transition_valid": float(valid_countdown_states(predicted_states)),
        }
    if "STATE COUNT" in expected and "HEAD" in expected:
        expected_states = pointer_state_pairs(expected)
        predicted_states = pointer_state_pairs(predicted)
        return {
            "state_count_exact": float(
                [c for c, _h in predicted_states] == [c for c, _h in expected_states]
            ),
            "pointer_head_exact": float(
                [h for _c, h in predicted_states] == [h for _c, h in expected_states]
            ),
            "halt_exact": float(
                ("HALT COUNT" in predicted) == ("HALT COUNT" in expected)
            ),
            "step_transition_valid": float(valid_pointer_states(predicted_states)),
        }
    if "PAIR " in expected or "LEFT_REMAIN" in expected:
        return {
            "pair_count_exact": float(
                predicted.count("PAIR ") == expected.count("PAIR ")
            ),
            "remain_exact": float(remain_lines(predicted) == remain_lines(expected)),
            "halt_exact": 0.0,
            "step_transition_valid": 0.0,
        }
    return None


def average_diagnostics(values: Sequence[dict[str, float] | None]) -> dict[str, float]:
    present = [value for value in values if value is not None]
    keys = sorted({key for value in present for key in value})
    return {key: mean(value.get(key, 0.0) for value in present) for key in keys}


def iterative_state_pairs(text: str) -> list[tuple[int, int]]:
    return [
        (int(match.group(1)), int(match.group(2)))
        for match in re.finditer(r"STATE COUNT (\d+) REM (\d+)", text)
    ]


def pointer_state_pairs(text: str) -> list[tuple[int, int]]:
    return [
        (int(match.group(1)), int(match.group(2)))
        for match in re.finditer(r"STATE COUNT (\d+) HEAD (\d+) TAPE", text)
    ]


def valid_countdown_states(states: Sequence[tuple[int, int]]) -> bool:
    if not states:
        return False
    for (count, rem), (next_count, next_rem) in itertools.pairwise(states):
        if next_count != count + 1 or next_rem != max(0, rem - 1):
            return False
    return True


def valid_pointer_states(states: Sequence[tuple[int, int]]) -> bool:
    if not states:
        return False
    for (count, head), (next_count, next_head) in itertools.pairwise(states):
        if next_count != count + 1 or next_head != head + 1:
            return False
    return True


def remain_lines(text: str) -> tuple[str, ...]:
    return tuple(
        line
        for line in text.splitlines()
        if line.startswith(("LEFT_REMAIN", "RIGHT_REMAIN"))
    )


def evaluate_sample_efficiency(run_dir: Path, eval_splits: dict[str, Path]) -> None:
    targets = {
        key: eval_splits[key]
        for key in (
            "seen_count_seen_object",
            "seen_count_heldout_object",
            "global_count_length_ood",
        )
        if key in eval_splits
    }
    if not targets:
        return
    out_path = run_dir / "sample_efficiency.json"
    if out_path.exists():
        return
    rows = []
    for checkpoint in sorted((run_dir / "checkpoints").glob("step_*.pt")):
        step = int(checkpoint.stem.removeprefix("step_"))
        for split, eval_path in targets.items():
            output_dir = run_dir / "sample_efficiency" / f"step_{step:06d}" / split
            if not (output_dir / "summary.json").exists():
                eval_lm(
                    checkpoint_path=checkpoint,
                    eval_path=eval_path,
                    tokenizer_path=TOKENIZER_PATH,
                    output_dir=output_dir,
                    max_examples=None,
                    max_new_tokens=max_new_tokens_for_split(split),
                    seed=SEED,
                    numeric_tokenization=NUMERIC_TOKENIZATION,
                )
            summary = _read_json(output_dir / "summary.json")
            rows.append(
                {
                    "step": step,
                    "split": split,
                    "final_nem": float(
                        summary["overall"]["final_normalized_exact_match"]
                    ),
                }
            )
    out_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def representation_probe(checkpoint_path: Path) -> dict[str, Any]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=TOKENIZER_PATH,
        device=device,
    )
    prompts = []
    for count in TRAIN_COUNTS:
        prompts.extend(
            [
                (
                    count,
                    f"COUNT_SET\nITEMS {object_sequence(count, obj='x', sep='space')}\nCASE P{count}",
                ),
                (
                    count,
                    f"COUNT_SET\nITEMS {object_sequence(count, obj=None, sep='space')}\nCASE M{count}",
                ),
                (count, f"COUNT_STATE {count}"),
                (count, f"PEANO_DEPTH\nTERM {peano(count)}"),
            ]
        )
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
    same = []
    different = []
    successor_directions = []
    for (left_count, left_vec), (right_count, right_vec) in itertools.combinations(
        vectors, 2
    ):
        score = torch.nn.functional.cosine_similarity(left_vec, right_vec, dim=0).item()
        if left_count == right_count:
            same.append(score)
        else:
            different.append(score)
    centroids = {
        count: torch.stack([vec for value, vec in vectors if value == count]).mean(
            dim=0
        )
        for count in TRAIN_COUNTS
    }
    for count in range(10):
        successor_directions.append(centroids[count + 1] - centroids[count])
    direction_cosines = [
        torch.nn.functional.cosine_similarity(a, b, dim=0).item()
        for a, b in itertools.combinations(successor_directions, 2)
    ]
    correct = 0
    for count, vec in vectors:
        predicted = max(
            centroids,
            key=lambda candidate: torch.nn.functional.cosine_similarity(
                vec,
                centroids[candidate],
                dim=0,
            ).item(),
        )
        correct += int(predicted == count)
    return {
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_step": checkpoint.get("step"),
        "same_quantity_cosine": mean(same),
        "different_quantity_cosine": mean(different),
        "centroid_probe_accuracy": correct / len(vectors),
        "successor_direction_cosine": mean(direction_cosines),
        "count": len(vectors),
    }


def analyze_run(run_dir: Path) -> dict[str, Any]:
    payload = {
        "train_config": _read_json_if_exists(run_dir / "train_config.json"),
        "run_result": _read_json_if_exists(run_dir / "run_result.json"),
        "metrics": _read_jsonl_if_exists(run_dir / "metrics.jsonl"),
        "eval": {},
        "sample_efficiency": _read_json_if_exists(run_dir / "sample_efficiency.json"),
        "probes": _read_json_if_exists(run_dir / "probes" / "quantity_probe.json"),
    }
    for summary_path in sorted((run_dir / "eval").glob("*/summary.json")):
        payload["eval"][summary_path.parent.name] = summary_payload(
            _read_json(summary_path)
        )
    return payload


def summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    overall = summary.get("overall", {})
    return {
        "count": int(overall.get("count", 0)),
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "full_nem": float(overall.get("normalized_exact_match", 0.0)),
        "empty_rate": float(overall.get("empty_prediction_rate", 0.0)),
        "avg_tokens": float(overall.get("avg_tokens_generated", 0.0)),
        "trace_diagnostics": summary.get("trace_diagnostics", {}),
    }


def decision(analysis: dict[str, Any]) -> str:
    runs = analysis.get("runs", {})
    promising = []
    for name in STEPS:
        run = runs.get(name, {})
        seen = score(run, "seen_count_seen_object")
        heldout = score(run, "seen_count_heldout_object")
        mixed = score(run, "mixed_object_identity")
        sep = score(run, "separator_ood")
        more = score(run, "more_less")
        length = max(
            score(run, "global_count_length_ood"),
            score(run, "iterative_count_length_ood"),
            score(run, "pointer_count_length_ood"),
            score(run, "matching_length_ood"),
        )
        if (
            seen >= 0.98
            and heldout >= 0.95
            and mixed >= 0.95
            and sep >= 0.95
            and more >= 0.95
        ):
            promising.append((name, length))
    if promising:
        best_name, best_length = max(promising, key=lambda item: item[1])
        if best_length >= 0.95:
            return (
                f"OUTCOME D/strong: {best_name} passes cardinality invariance and "
                "strong 11..20 length OOD. Return to concrete addition using this curriculum."
            )
        if best_length >= 0.80:
            return (
                f"OUTCOME D/useful: {best_name} passes cardinality invariance and "
                "useful 11..20 length OOD. Freeze it and test concrete addition next."
            )
        return (
            f"PROMISING ID: {best_name} passes object/mixed/separator invariance but "
            "length OOD remains weak. Capacity check is gated."
        )
    fitted = [
        name
        for name in STEPS
        if score(runs.get(name, {}), "seen_count_seen_object") >= 0.98
        or score(runs.get(name, {}), "iterative_count_seen") >= 0.98
        or score(runs.get(name, {}), "pointer_count_seen") >= 0.98
        or score(runs.get(name, {}), "matching_seen") >= 0.98
    ]
    if fitted:
        return (
            "OUTCOME F/partial fit: at least one method fits its seen task, but none "
            "passes the full cardinality invariance gate."
        )
    return (
        "OUTCOME F: none of the tested textual counting-stick procedures formed "
        "robust cardinality under the current decoder-only Transformer setup."
    )


def best_method(analysis: dict[str, Any]) -> str:
    runs = analysis.get("runs", {})
    if not runs:
        return "global_count"
    return max(
        STEPS,
        key=lambda name: sum(
            score(runs.get(name, {}), split)
            for split in [
                "seen_count_seen_object",
                "seen_count_heldout_object",
                "mixed_object_identity",
                "separator_ood",
                "global_count_length_ood",
                "iterative_count_length_ood",
                "pointer_count_length_ood",
                "matching_length_ood",
            ]
        ),
    )


def score(run: dict[str, Any], split: str) -> float:
    return float(run.get("eval", {}).get(split, {}).get("final_nem", 0.0))


def trace_score(run: dict[str, Any], split: str, key: str) -> float:
    return float(
        run.get("eval", {}).get(split, {}).get("trace_diagnostics", {}).get(key, 0.0)
    )


def metric_table(
    analysis: dict[str, Any],
    groups: Sequence[str],
    splits: Sequence[str],
) -> str:
    rows = ["| method | " + " | ".join(splits) + " |", "|---|" + "---:|" * len(splits)]
    runs = analysis.get("runs", {})
    for group in groups:
        run = runs.get(group, {})
        rows.append(
            f"| {group} | "
            + " | ".join(f"{score(run, split):.4f}" for split in splits)
            + " |"
        )
    return "\n".join(rows)


def trace_table(
    analysis: dict[str, Any],
    groups: Sequence[str],
    splits: Sequence[str],
) -> str:
    keys = [
        "state_count_exact",
        "remaining_exact",
        "step_transition_valid",
        "pair_count_exact",
        "remain_exact",
    ]
    rows = [
        "",
        "| method | split | " + " | ".join(keys) + " |",
        "|---|---|" + "---:|" * len(keys),
    ]
    runs = analysis.get("runs", {})
    for group in groups:
        run = runs.get(group, {})
        for split in splits:
            rows.append(
                f"| {group} | {split} | "
                + " | ".join(f"{trace_score(run, split, key):.4f}" for key in keys)
                + " |"
            )
    return "\n".join(rows)


def tokenization_table(analysis: dict[str, Any]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in analysis.get("manifest", {}).get("tokenization_audit", []):
        grouped[row["object"]].append(row)
    rows = [
        "| object | max count | object span visible | aggregate leak rows |",
        "|---|---:|---|---:|",
    ]
    for obj, values in sorted(grouped.items()):
        rows.append(
            f"| {obj} | {max(int(v['count']) for v in values)} | "
            f"{all(v['object_span_count'] == v['tokenized_object_span_count'] for v in values)} | "
            f"{sum(bool(v['single_aggregate_token']) for v in values)} |"
        )
    return "\n".join(rows)


def axis_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| split | count | task types | object families | counts |",
        "|---|---:|---|---|---|",
    ]
    for name, audit in analysis.get("manifest", {}).get("eval_splits", {}).items():
        rows.append(
            f"| {name} | {audit.get('count', 0)} | {audit.get('task_type_counts', {})} | "
            f"{audit.get('object_families', [])} | {audit.get('counts', [])} |"
        )
    intersections = analysis.get("manifest", {}).get("prompt_intersections", {})
    rows.append("")
    rows.append(f"Prompt intersection max: `{max(intersections.values(), default=0)}`.")
    strict = analysis.get("manifest", {}).get("strict_full_count_11_20_in_train", {})
    rows.append(f"Strict full-count 11..20 in train: `{strict}`.")
    return "\n".join(rows)


def probe_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| method | same cosine | different cosine | centroid acc | successor direction cosine |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, run in sorted(analysis.get("runs", {}).items()):
        probe = run.get("probes")
        if probe:
            rows.append(
                f"| {name} | {probe.get('same_quantity_cosine', 0.0):.4f} | "
                f"{probe.get('different_quantity_cosine', 0.0):.4f} | "
                f"{probe.get('centroid_probe_accuracy', 0.0):.4f} | "
                f"{probe.get('successor_direction_cosine', 0.0):.4f} |"
            )
    if len(rows) == 2:
        rows.append("| not run | 0.0000 | 0.0000 | 0.0000 | 0.0000 |")
    return "\n".join(rows)


def sample_efficiency_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| method | split | >=.80 | >=.90 | >=.95 | >=.98 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    thresholds = (0.80, 0.90, 0.95, 0.98)
    for name, run in sorted(analysis.get("runs", {}).items()):
        values = run.get("sample_efficiency") or []
        by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in values:
            by_split[str(row["split"])].append(row)
        for split, split_rows in sorted(by_split.items()):
            cells = []
            for threshold in thresholds:
                reached = [
                    int(row["step"])
                    for row in split_rows
                    if float(row["final_nem"]) >= threshold
                ]
                cells.append(str(min(reached)) if reached else "not reached")
            rows.append(f"| {name} | {split} | " + " | ".join(cells) + " |")
    if len(rows) == 2:
        rows.append(
            "| not run | n/a | not reached | not reached | not reached | not reached |"
        )
    return "\n".join(rows)


def capacity_status(analysis: dict[str, Any]) -> str:
    decision_text = str(analysis.get("decision", ""))
    if "PROMISING ID" in decision_text:
        return "gated: a method fits cardinality invariance but length OOD is low; compare tiny/arithmetic_3m/arithmetic_10m next."
    return "skipped: no method passed the seen/object/mixed/separator invariance gate."


def recurrent_status(analysis: dict[str, Any]) -> str:
    if "partial fit" in str(analysis.get("decision", "")):
        return "not run: recurrent control is reserved for methods that fit seen data but fail length OOD after invariance is solved."
    return "skipped: Transformer methods did not pass the gating criteria."


def recommendation(analysis: dict[str, Any]) -> str:
    text = str(analysis.get("decision", ""))
    if text.startswith("OUTCOME D"):
        return "Return to concrete addition, using the winning cardinality curriculum as a frozen prerequisite."
    if "PROMISING ID" in text:
        return "Run the gated capacity check, then retry 11..20 length OOD."
    if "partial fit" in text:
        return "Diagnose why object/separator invariance fails before any addition or recurrent work."
    return "Stop textual counting-stick grounding for this decoder setup unless a more structural input representation is introduced."


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


def audit_examples(examples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    prompts = [str(example["prompt"]) for example in examples]
    metadata = [example.get("metadata", {}) for example in examples]
    return {
        "count": len(examples),
        "unique_prompts": len(set(prompts)),
        "duplicate_prompt_count": len(prompts) - len(set(prompts)),
        "task_type_counts": dict(
            Counter(str(example["task_type"]) for example in examples)
        ),
        "object_families": sorted(
            {
                str(item.get("object_family"))
                for item in metadata
                if item.get("object_family")
            }
        ),
        "separators": sorted(
            {str(item.get("separator")) for item in metadata if item.get("separator")}
        ),
        "counts": sorted(
            {
                int(item.get("count"))
                for item in metadata
                if item.get("count") is not None
            }
        ),
    }


def prompt_intersections(
    trains: dict[str, list[dict[str, Any]]],
    eval_splits: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    result = {}
    for train_name, train_examples in trains.items():
        train_prompts = {str(example["prompt"]) for example in train_examples}
        for eval_name, eval_examples in eval_splits.items():
            eval_prompts = {str(example["prompt"]) for example in eval_examples}
            result[f"{train_name}__{eval_name}"] = len(train_prompts & eval_prompts)
    return result


def full_count_ood_seen(examples: Sequence[dict[str, Any]]) -> int:
    return sum(
        str(example["task_type"])
        in {"m192a.count.global", "m192a.count.iterative", "m192a.count.pointer_tape"}
        and int(example.get("metadata", {}).get("count", -1)) in LENGTH_OOD_COUNTS
        for example in examples
    )


def final_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    return checkpoints[-1] if checkpoints else None


def prune_intermediate_checkpoints(run_dir: Path) -> None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    for checkpoint in checkpoints[:-1]:
        checkpoint.unlink(missing_ok=True)


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


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


if __name__ == "__main__":
    main()
