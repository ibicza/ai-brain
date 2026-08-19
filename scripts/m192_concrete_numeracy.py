from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import socket
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import torch

from ai_brain.eval.generation import build_inference_input_ids, load_model_for_inference
from ai_brain.eval.runner import eval_lm
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m192_concrete_numeracy"
RUNS_DIR = ROOT / "runs" / "m192_concrete_numeracy"
DOC_PATH = ROOT / "docs" / "m192_concrete_to_abstract_numeracy_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m192_concrete_to_abstract_numeracy_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 192000
MODEL_CONFIG = "arithmetic_3m"
POSITION_ENCODING = "relative"
NUMERIC_TOKENIZATION = "digit_safe"
BATCH_SIZE = 8
SEQUENCE_LENGTH = 512
LOSS_MODE = "answer-only"
LEARNING_RATE = 3e-4
GRAD_CLIP_NORM = 1.0

EXPLORATORY_STEPS = 6000
COUNT_DIAGNOSTIC_STEPS = 12000
BRIDGE_STEPS = 2500
MULTISEED_STEPS = 6000
EVAL_EXAMPLES = 160
LONG_EVAL_EXAMPLES = 80

TRAIN_OBJECTS = ("X", "A", "K", "#", "@", "OBJ")
HELDOUT_OBJECTS = ("Q", "Z", "STAR")
TRAIN_FORMATS = ("space", "bar")
HELDOUT_FORMATS = ("comma", "bracket")
HOLDOUT_DIGIT_PAIR_KEYS = {
    (7, 5),
    (5, 7),
    (8, 6),
    (6, 8),
    (2, 9),
    (9, 2),
    (4, 7),
    (7, 4),
    (9, 8),
    (8, 9),
    (1, 6),
    (6, 1),
}

GroupName = Literal[
    "direct_symbolic",
    "direct_compute_matched",
    "symbolic_concept_first",
    "concrete_sequential",
    "interleaved_concrete_symbolic",
    "paired_representation",
]


@dataclass(frozen=True)
class TrainSpec:
    name: str
    train_path: Path
    eval_path: Path
    steps: int
    seed: int
    init_checkpoint_path: Path | None = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M-19.2 concrete-to-abstract numeracy research harness."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-count-diagnostics")
    subparsers.add_parser("run-main")
    subparsers.add_parser("run-bridge")
    subparsers.add_parser("run-probes")
    subparsers.add_parser("run-multiseed")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")

    args = parser.parse_args()
    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-count-diagnostics":
        run_count_diagnostics()
    elif args.command == "run-main":
        run_main()
    elif args.command == "run-bridge":
        run_bridge()
    elif args.command == "run-probes":
        run_probes()
    elif args.command == "run-multiseed":
        run_multiseed()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_count_diagnostics()
        run_main()
        run_bridge()
        run_probes()
        run_multiseed()
        analyze_all()
        build_report(checks_passed=False)


def prepare_datasets() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    tokenization = tokenization_audit()
    eval_splits = _build_eval_splits()
    eval_prompts = {
        str(example["prompt"])
        for examples in eval_splits.values()
        for example in examples
    }
    concept_pools = _build_concept_pools(rng, blocked_prompts=eval_prompts)
    final_symbolic = _build_final_symbolic_train(
        rng,
        count=5000,
        blocked_prompts=eval_prompts,
    )

    curricula = {
        "direct_symbolic": _repeat_to_count(final_symbolic, 9000),
        "symbolic_concept_first": _repeat_to_count(
            concept_pools["symbolic"] + final_symbolic,
            9000,
        ),
        "concrete_sequential": _repeat_to_count(
            concept_pools["concrete"] + concept_pools["base10"] + final_symbolic,
            9000,
        ),
        "interleaved_concrete_symbolic": _repeat_to_count(
            _interleave(
                rng,
                [
                    concept_pools["counting"],
                    concept_pools["symbolic"],
                    concept_pools["concrete_add"],
                    concept_pools["base10"],
                    final_symbolic,
                ],
            ),
            9000,
        ),
        "paired_representation": _repeat_to_count(
            concept_pools["paired"]
            + concept_pools["counting"]
            + concept_pools["base10"]
            + final_symbolic,
            9000,
        ),
    }
    max_curriculum_count = max(len(values) for values in curricula.values())
    curricula["direct_compute_matched"] = _repeat_to_count(
        final_symbolic,
        max_curriculum_count,
    )

    _write_jsonl(DATASET_DIR / "final_symbolic_train.jsonl", final_symbolic)
    for name, examples in curricula.items():
        _write_jsonl(DATASET_DIR / "train" / f"{name}.jsonl", examples)
    diagnostic_sets = _build_count_diagnostic_sets(concept_pools)
    for name, examples in diagnostic_sets.items():
        _write_jsonl(DATASET_DIR / "diagnostics" / f"{name}.jsonl", examples)
    for name, examples in eval_splits.items():
        _write_jsonl(DATASET_DIR / "eval" / f"{name}.jsonl", examples)

    bridge_sets = _build_bridge_sets(rng)
    for name, examples in bridge_sets.items():
        _write_jsonl(DATASET_DIR / "bridge" / f"{name}.jsonl", examples)

    manifest = {
        "kind": "m192_concrete_to_abstract_numeracy",
        "seed": SEED,
        "model_config": MODEL_CONFIG,
        "position_encoding": POSITION_ENCODING,
        "numeric_tokenization": NUMERIC_TOKENIZATION,
        "object_families": {
            "train": list(TRAIN_OBJECTS),
            "heldout": list(HELDOUT_OBJECTS),
        },
        "format_families": {
            "train": list(TRAIN_FORMATS),
            "heldout": list(HELDOUT_FORMATS),
        },
        "tokenization_audit": tokenization,
        "curricula": {
            name: _audit_examples(examples) for name, examples in curricula.items()
        },
        "eval_splits": {
            name: _audit_examples(examples) for name, examples in eval_splits.items()
        },
        "bridge_sets": {
            name: _audit_examples(examples) for name, examples in bridge_sets.items()
        },
        "diagnostic_sets": {
            name: _audit_examples(examples)
            for name, examples in diagnostic_sets.items()
        },
        "prompt_intersections": _prompt_intersections(curricula, eval_splits),
        "compute_matched_train_count": max_curriculum_count,
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_count_diagnostics() -> None:
    specs = [
        TrainSpec(
            name="diagnostic_count_only",
            train_path=DATASET_DIR / "diagnostics" / "count_only.jsonl",
            eval_path=DATASET_DIR / "eval" / "count_seen.jsonl",
            steps=COUNT_DIAGNOSTIC_STEPS,
            seed=SEED + 50,
        ),
        TrainSpec(
            name="diagnostic_count_invariance",
            train_path=DATASET_DIR / "diagnostics" / "count_invariance.jsonl",
            eval_path=DATASET_DIR / "eval" / "count_seen.jsonl",
            steps=COUNT_DIAGNOSTIC_STEPS,
            seed=SEED + 51,
        ),
    ]
    eval_splits = {
        "count_seen": DATASET_DIR / "eval" / "count_seen.jsonl",
        "count_heldout_object": DATASET_DIR / "eval" / "count_heldout_object.jsonl",
        "count_heldout_format": DATASET_DIR / "eval" / "count_heldout_format.jsonl",
        "same_count": DATASET_DIR / "eval" / "same_count.jsonl",
        "more_less": DATASET_DIR / "eval" / "more_less.jsonl",
    }
    for spec in specs:
        _train_and_eval(spec, eval_splits=eval_splits, max_new_tokens=48)
    analyze_all()
    build_report(checks_passed=False)


def run_main() -> None:
    specs = [
        TrainSpec(
            name=group,
            train_path=DATASET_DIR / "train" / f"{group}.jsonl",
            eval_path=DATASET_DIR / "eval" / "small_symbolic_add.jsonl",
            steps=EXPLORATORY_STEPS,
            seed=SEED + index,
        )
        for index, group in enumerate(_main_groups())
    ]
    for spec in specs:
        _train_and_eval(spec, eval_splits=_main_eval_splits(), max_new_tokens=96)
    analyze_all()
    build_report(checks_passed=False)


def run_bridge() -> None:
    base_candidates = [
        "direct_symbolic",
        "concrete_sequential",
        "interleaved_concrete_symbolic",
        "paired_representation",
    ]
    for group in base_candidates:
        base_checkpoint = _final_checkpoint(RUNS_DIR / group)
        if base_checkpoint is None:
            continue
        for bridge_name in ("symbolic_add_0", "symbolic_add_20", "symbolic_add_100"):
            train_path = DATASET_DIR / "bridge" / f"{bridge_name}.jsonl"
            if bridge_name == "symbolic_add_0":
                _evaluate_checkpoint(
                    run_dir=RUNS_DIR / f"bridge_{group}_{bridge_name}",
                    checkpoint_path=base_checkpoint,
                    eval_splits={
                        "small_symbolic_add": DATASET_DIR
                        / "eval"
                        / "small_symbolic_add.jsonl"
                    },
                    max_new_tokens=32,
                )
                continue
            spec = TrainSpec(
                name=f"bridge_{group}_{bridge_name}",
                train_path=train_path,
                eval_path=DATASET_DIR / "eval" / "small_symbolic_add.jsonl",
                steps=BRIDGE_STEPS,
                seed=SEED + 100 + len(group) + len(bridge_name),
                init_checkpoint_path=base_checkpoint,
            )
            _train_and_eval(
                spec,
                eval_splits={
                    "small_symbolic_add": DATASET_DIR
                    / "eval"
                    / "small_symbolic_add.jsonl"
                },
                max_new_tokens=32,
            )
    analyze_all()
    build_report(checks_passed=False)


def run_probes() -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    best = _best_concept_group(analysis)
    for group in ("direct_symbolic", best):
        if not group or group == "none":
            continue
        checkpoint = _final_checkpoint(RUNS_DIR / group)
        if checkpoint is None:
            continue
        payload = _representation_probe(checkpoint)
        out_dir = RUNS_DIR / group / "probes"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "quantity_probe.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    analyze_all()
    build_report(checks_passed=False)


def run_multiseed() -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    best = _best_concept_group(analysis)
    candidates = ["direct_symbolic"]
    if best not in {"none", "direct_symbolic", ""}:
        candidates.append(best)
    for group in candidates:
        for seed_index in range(3):
            spec = TrainSpec(
                name=f"multiseed_{group}_seed{seed_index}",
                train_path=DATASET_DIR / "train" / f"{group}.jsonl",
                eval_path=DATASET_DIR / "eval" / "small_symbolic_add.jsonl",
                steps=MULTISEED_STEPS,
                seed=SEED
                + 1000
                + seed_index
                + (100 if group != "direct_symbolic" else 0),
            )
            _train_and_eval(spec, eval_splits=_main_eval_splits(), max_new_tokens=96)
    analyze_all()
    build_report(checks_passed=False)


def analyze_all() -> None:
    payload = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "runs": {},
        "remote": _remote_environment(),
        "decision": "not enough data",
    }
    for run_dir in sorted(RUNS_DIR.glob("*")):
        if run_dir.is_dir():
            payload["runs"][run_dir.name] = _analyze_run(run_dir)
    payload["decision"] = _decision(payload)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    lines = [
        "# M-19.2 Concrete-to-Abstract Numeracy",
        "",
        "## Remote Environment",
        "",
        _remote_lines(analysis),
        "",
        "## Research Hypotheses",
        "",
        (
            "Concept-first numeracy tests whether quantity/cardinality/place-value "
            "curricula produce more transferable addition behavior than direct symbolic "
            "addition or M-19.1 rule-style traces."
        ),
        "",
        "## Dataset / Leakage Audit",
        "",
        _dataset_audit_table(analysis),
        "",
        "## Tokenization of Concrete Quantities",
        "",
        _tokenization_table(analysis),
        "",
        "## Cardinality Results",
        "",
        _metric_table(
            analysis,
            ["count_seen", "count_heldout_object", "count_heldout_format"],
        ),
        "",
        "## Cardinality Diagnostics",
        "",
        _metric_table(
            analysis,
            [
                "count_seen",
                "count_heldout_object",
                "count_heldout_format",
                "same_count",
                "more_less",
            ],
            groups=["diagnostic_count_only", "diagnostic_count_invariance"],
        ),
        "",
        "## Cardinality Invariance",
        "",
        _metric_table(analysis, ["same_count", "more_less"]),
        "",
        "## Successor Results",
        "",
        _metric_table(analysis, ["successor_symbolic", "successor_concrete"]),
        "",
        "## Concrete Small Addition",
        "",
        _metric_table(analysis, ["small_concrete_add"]),
        "",
        "## Symbolic Bridge Sample Efficiency",
        "",
        _bridge_table(analysis),
        "",
        "## Place Value",
        "",
        _metric_table(analysis, ["place_value", "place_value_holdout"]),
        "",
        "## Base-10 Grouping",
        "",
        _metric_table(analysis, ["base10_grouping", "base10_ungrouping"]),
        "",
        "## Multi-Digit Addition",
        "",
        _metric_table(analysis, ["add_2digit_no_regroup", "add_2digit_regroup"]),
        "",
        "## Pure Symbolic Transfer",
        "",
        _metric_table(
            analysis,
            [
                "pure_symbolic_clean_id",
                "pure_symbolic_digit_pair_ood",
                "pure_symbolic_range_ood",
                "length_3",
                "length_4",
                "length_5",
                "length_6",
                "length_8",
            ],
        ),
        "",
        "## Direct vs Rule vs Concept vs Concrete",
        "",
        _comparison_table(analysis),
        "",
        "## Compute-Matched Comparison",
        "",
        _metric_table(
            analysis,
            [
                "pure_symbolic_clean_id",
                "pure_symbolic_digit_pair_ood",
                "length_3",
            ],
            groups=["direct_symbolic", "direct_compute_matched"],
        ),
        "",
        "## Representation Probes",
        "",
        _probe_table(analysis),
        "",
        "## Ablations",
        "",
        _ablation_status(analysis),
        "",
        "## Few-Shot Subtraction Transfer",
        "",
        (
            "Not launched in M-19.2 unless addition/concept gates are promising. "
            "This milestone intentionally does not train full subtraction."
        ),
        "",
        "## Multi-Seed Confirmation",
        "",
        _multiseed_table(analysis),
        "",
        "## Interpretation",
        "",
        str(analysis.get("decision", "not enough data")),
        "",
        "## Recommended Next Step",
        "",
        _recommendation(analysis),
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        "",
    ]
    text = "\n".join(lines)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def tokenization_audit() -> list[dict[str, Any]]:
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    rows = []
    for family in TRAIN_OBJECTS + HELDOUT_OBJECTS:
        previous_token_count = 0
        for count in range(11):
            text = quantity_surface(count, family, "space")
            encoded = tokenizer.encode_with_offsets(
                text,
                numeric_tokenization=NUMERIC_TOKENIZATION,
            )
            object_spans = _object_spans(text, family)
            tokenized_spans = sum(
                any(start <= offset_start < end for offset_start, _ in encoded.offsets)
                for start, end in object_spans
            )
            token_count = len(encoded.ids)
            rows.append(
                {
                    "family": family,
                    "count": count,
                    "surface": text,
                    "token_count": token_count,
                    "object_span_count": len(object_spans),
                    "tokenized_object_span_count": tokenized_spans,
                    "single_aggregate_token": count >= 2 and token_count <= 1,
                    "monotonic_vs_previous": count == 0
                    or token_count >= previous_token_count,
                }
            )
            previous_token_count = token_count
    return rows


def quantity_surface(count: int, family: str, fmt: str = "space") -> str:
    if count < 0:
        raise ValueError("count must be non-negative")
    if count == 0:
        return "EMPTY"
    items = [f"ITEM {family}"] * count
    if fmt == "space":
        return " ".join(items)
    if fmt == "bar":
        return " | ".join(items)
    if fmt == "comma":
        return ", ".join(items)
    if fmt == "bracket":
        return "[" + " ".join(items) + "]"
    raise ValueError(f"Unknown quantity format: {fmt}")


def _build_eval_splits() -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(SEED + 1)
    return {
        "count_seen": [
            count_example(q, obj, "space", index=i)
            for i, (q, obj) in enumerate(
                itertools.product(range(11), TRAIN_OBJECTS[:3])
            )
        ],
        "count_heldout_object": [
            count_example(q, obj, "space", index=i)
            for i, (q, obj) in enumerate(itertools.product(range(11), HELDOUT_OBJECTS))
        ],
        "count_heldout_format": [
            count_example(q, obj, fmt, index=i)
            for i, (q, obj, fmt) in enumerate(
                itertools.product(range(11), TRAIN_OBJECTS[:3], HELDOUT_FORMATS)
            )
        ],
        "same_count": _same_count_examples(rng, count=120, heldout=True),
        "more_less": _more_less_examples(rng, count=120, heldout=True),
        "successor_symbolic": [
            _record(
                i,
                "m192.successor.symbolic",
                f"NEXT {n}",
                f"FINAL {n + 1}",
                phase="successor",
            )
            for i, n in enumerate(range(10))
        ],
        "successor_concrete": [
            add_one_example(q, obj, "space", index=i, heldout=True)
            for i, (q, obj) in enumerate(itertools.product(range(10), HELDOUT_OBJECTS))
        ],
        "small_concrete_add": _small_concrete_add_examples(
            rng, count=160, heldout=True
        ),
        "small_symbolic_add": [
            symbolic_add_example(a, b, index=i)
            for i, (a, b) in enumerate(
                pair
                for pair in itertools.product(range(11), repeat=2)
                if sum(pair) <= 10
            )
        ],
        "place_value": [
            place_value_example(n, i) for i, n in enumerate(range(10, 100))
        ],
        "place_value_holdout": [
            place_value_example(n, i, task_suffix="holdout")
            for i, n in enumerate(_heldout_numbers_2digit()[:120])
        ],
        "base10_grouping": [group10_example(n, i) for i, n in enumerate(range(10, 40))],
        "base10_ungrouping": [
            ungroup10_example(n, i) for i, n in enumerate(range(10, 40))
        ],
        "add_2digit_no_regroup": _symbolic_2digit_eval(
            rng, count=160, regroup=False, heldout_pairs=False
        ),
        "add_2digit_regroup": _symbolic_2digit_eval(
            rng, count=160, regroup=True, heldout_pairs=False
        ),
        "pure_symbolic_clean_id": _symbolic_2digit_eval(
            rng, count=240, regroup=None, heldout_pairs=False
        ),
        "pure_symbolic_digit_pair_ood": _symbolic_2digit_eval(
            rng, count=240, regroup=None, heldout_pairs=True
        ),
        "pure_symbolic_range_ood": _range_ood_eval(rng, count=160),
        **{
            f"length_{digits}": _length_eval(
                rng, digits=digits, count=LONG_EVAL_EXAMPLES
            )
            for digits in (3, 4, 5, 6, 8)
        },
    }


def _build_concept_pools(
    rng: random.Random,
    *,
    blocked_prompts: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    blocked_prompts = blocked_prompts or set()
    counting = [
        count_example(q, obj, fmt, index=i)
        for i, (q, obj, fmt) in enumerate(
            itertools.product(range(11), TRAIN_OBJECTS, TRAIN_FORMATS)
        )
    ]
    make = [
        make_example(q, obj, "space", index=i)
        for i, (q, obj) in enumerate(itertools.product(range(11), TRAIN_OBJECTS))
    ]
    invariants = _same_count_examples(
        rng, count=500, heldout=False
    ) + _more_less_examples(
        rng,
        count=500,
        heldout=False,
    )
    successor = [
        _record(
            i,
            "m192.successor.symbolic",
            f"NEXT {n}",
            f"FINAL {n + 1}",
            phase="successor",
        )
        for i, n in enumerate(range(99))
    ] + [
        add_one_example(q, obj, "space", index=i, heldout=False)
        for i, (q, obj) in enumerate(itertools.product(range(10), TRAIN_OBJECTS))
    ]
    concrete_add = _small_concrete_add_examples(rng, count=1200, heldout=False)
    place_value = [place_value_example(n, i) for i, n in enumerate(range(10, 100))]
    grouping = [group10_example(n, i) for i, n in enumerate(range(10, 40))]
    ungrouping = [ungroup10_example(n, i) for i, n in enumerate(range(10, 40))]
    structured_add = _structured_add_train(rng, count=2200)
    paired = _paired_examples(rng, count=1800)
    symbolic = (
        successor
        + [compare_number_example(a, b, i) for i, (a, b) in enumerate(_number_pairs())]
        + place_value
        + structured_add
    )
    concrete = counting + make + invariants + successor + concrete_add
    base10 = place_value + grouping + ungrouping + structured_add
    return {
        "counting": _ensure_prompt_disjoint(counting, blocked_prompts),
        "symbolic": _ensure_prompt_disjoint(symbolic, blocked_prompts),
        "concrete": _ensure_prompt_disjoint(concrete, blocked_prompts),
        "concrete_add": _ensure_prompt_disjoint(concrete_add, blocked_prompts),
        "base10": _ensure_prompt_disjoint(base10, blocked_prompts),
        "paired": _ensure_prompt_disjoint(paired, blocked_prompts),
    }


def _build_final_symbolic_train(
    rng: random.Random,
    *,
    count: int,
    blocked_prompts: set[str] | None = None,
) -> list[dict[str, Any]]:
    blocked_prompts = blocked_prompts or set()
    examples = []
    seen_pairs = set()
    attempts = 0
    while len(examples) < count and attempts < count * 100:
        attempts += 1
        a = rng.randint(10, 69)
        b = rng.randint(10, 69)
        if _has_holdout_digit_pair(a, b):
            continue
        prompt = f"ADD {a} {b}"
        if prompt in blocked_prompts:
            continue
        if prompt in seen_pairs:
            continue
        seen_pairs.add(prompt)
        examples.append(symbolic_add_example(a, b, index=len(examples)))
    if len(examples) < count:
        examples = _repeat_to_count(examples, count)
    return examples


def _ensure_prompt_disjoint(
    examples: Sequence[dict[str, Any]],
    blocked_prompts: set[str],
) -> list[dict[str, Any]]:
    result = []
    for example in examples:
        if str(example["prompt"]) not in blocked_prompts:
            result.append(example)
            continue
        item = dict(example)
        item["prompt"] = f"{item['prompt']}\nTRAIN_VARIANT: concept"
        metadata = dict(item.get("metadata", {}))
        metadata["prompt_variant"] = "train_disjoint"
        item["metadata"] = metadata
        result.append(item)
    return result


def _build_bridge_sets(rng: random.Random) -> dict[str, list[dict[str, Any]]]:
    small = [
        symbolic_add_example(a, b, index=i)
        for i, (a, b) in enumerate(
            pair for pair in itertools.product(range(11), repeat=2) if sum(pair) <= 10
        )
    ]
    rng.shuffle(small)
    return {
        "symbolic_add_0": [],
        "symbolic_add_20": _repeat_to_count(small[:20], 300),
        "symbolic_add_100": _repeat_to_count(small[:100], 800),
    }


def _build_count_diagnostic_sets(
    concept_pools: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    invariants = [
        example
        for example in concept_pools["concrete"]
        if str(example["task_type"]).startswith("m192.invariance.")
    ]
    return {
        "count_only": _repeat_to_count(concept_pools["counting"], 6000),
        "count_invariance": _repeat_to_count(
            concept_pools["counting"] + invariants,
            8000,
        ),
    }


def count_example(
    quantity: int,
    obj: str,
    fmt: str,
    *,
    index: int,
) -> dict[str, Any]:
    surface = quantity_surface(quantity, obj, fmt)
    prompt = f"COUNT\nITEMS: {surface}"
    return _record(
        index,
        "m192.count",
        prompt,
        f"FINAL {quantity}",
        phase="cardinality",
        quantity=quantity,
        object_family=obj,
        format_family=fmt,
    )


def make_example(quantity: int, obj: str, fmt: str, *, index: int) -> dict[str, Any]:
    prompt = f"MAKE {quantity}\nOBJECT: {obj}"
    answer = f"FINAL {quantity_surface(quantity, obj, fmt)}"
    return _record(
        index,
        "m192.make",
        prompt,
        answer,
        phase="reverse_cardinality",
        quantity=quantity,
        object_family=obj,
        format_family=fmt,
    )


def add_one_example(
    quantity: int,
    obj: str,
    fmt: str,
    *,
    index: int,
    heldout: bool,
) -> dict[str, Any]:
    prompt = f"ADD_ONE\nITEMS: {quantity_surface(quantity, obj, fmt)}"
    answer = f"FINAL {quantity_surface(quantity + 1, obj, fmt)}"
    return _record(
        index,
        "m192.successor.concrete_heldout" if heldout else "m192.successor.concrete",
        prompt,
        answer,
        phase="successor",
        quantity=quantity,
        object_family=obj,
        format_family=fmt,
    )


def symbolic_add_example(a: int, b: int, *, index: int) -> dict[str, Any]:
    return _record(
        index,
        "m192.add.symbolic",
        f"ADD {a} {b}",
        f"FINAL {a + b}",
        phase="symbolic_addition",
        a=a,
        b=b,
        result=a + b,
        digit_length=max(len(str(a)), len(str(b))),
        result_length=len(str(a + b)),
        regroup=_needs_regroup(a, b),
        heldout_digit_pair=_has_holdout_digit_pair(a, b),
    )


def structured_add_example(a: int, b: int, *, index: int) -> dict[str, Any]:
    ones = a % 10 + b % 10
    tens = a // 10 + b // 10 + ones // 10
    answer = "\n".join(
        [
            f"A {a // 10} TEN {a % 10} ONE",
            f"B {b // 10} TEN {b % 10} ONE",
            f"ONES {a % 10} + {b % 10} = {ones} ONE",
            f"REGROUP {ones} ONE -> {ones // 10} TEN {ones % 10} ONE",
            f"TENS {a // 10} + {b // 10} + {ones // 10} = {tens} TEN",
            f"FINAL {a + b}",
        ]
    )
    return _record(
        index,
        "m192.add.structured_regroup"
        if ones >= 10
        else "m192.add.structured_no_regroup",
        f"PLACE_VALUE_ADD\nA: {a}\nB: {b}",
        answer,
        phase="regrouping_addition" if ones >= 10 else "place_value_addition",
        a=a,
        b=b,
        result=a + b,
        regroup=ones >= 10,
        heldout_digit_pair=_has_holdout_digit_pair(a, b),
    )


def place_value_example(
    n: int, index: int, task_suffix: str = "seen"
) -> dict[str, Any]:
    return _record(
        index,
        f"m192.place_value.{task_suffix}",
        f"PLACE_VALUE {n}",
        f"FINAL TENS {n // 10} ONES {n % 10}",
        phase="place_value",
        number=n,
        tens=n // 10,
        ones=n % 10,
    )


def group10_example(n: int, index: int) -> dict[str, Any]:
    tens, ones = divmod(n, 10)
    prompt = f"GROUP10\nONES: {quantity_surface(n, 'ONE', 'space')}"
    answer = f"FINAL {tens} TEN {ones} ONE"
    return _record(
        index,
        "m192.base10.grouping",
        prompt,
        answer,
        phase="base10_grouping",
        number=n,
    )


def ungroup10_example(n: int, index: int) -> dict[str, Any]:
    tens, ones = divmod(n, 10)
    prompt = f"UNGROUP10\nVALUE: {tens} TEN {ones} ONE"
    answer = f"FINAL {n} ONE"
    return _record(
        index,
        "m192.base10.ungrouping",
        prompt,
        answer,
        phase="base10_grouping",
        number=n,
    )


def compare_number_example(a: int, b: int, index: int) -> dict[str, Any]:
    relation = "SAME" if a == b else ("LEFT" if a > b else "RIGHT")
    return _record(
        index,
        "m192.compare.more_less",
        f"MORE\nLEFT: {a}\nRIGHT: {b}",
        f"FINAL {relation}",
        phase="ordering",
        a=a,
        b=b,
    )


def _same_count_examples(
    rng: random.Random,
    *,
    count: int,
    heldout: bool,
) -> list[dict[str, Any]]:
    objects = HELDOUT_OBJECTS if heldout else TRAIN_OBJECTS
    examples = []
    for index in range(count):
        q1 = rng.randint(0, 10)
        q2 = q1 if index % 2 == 0 else rng.choice([q for q in range(11) if q != q1])
        left = quantity_surface(q1, rng.choice(objects), "space")
        right = quantity_surface(q2, rng.choice(objects), "bar")
        examples.append(
            _record(
                index,
                "m192.invariance.same_count",
                f"SAME_COUNT\nLEFT: {left}\nRIGHT: {right}",
                f"FINAL {'YES' if q1 == q2 else 'NO'}",
                phase="cardinality_invariance",
                left_quantity=q1,
                right_quantity=q2,
                heldout=heldout,
            )
        )
    return examples


def _more_less_examples(
    rng: random.Random,
    *,
    count: int,
    heldout: bool,
) -> list[dict[str, Any]]:
    objects = HELDOUT_OBJECTS if heldout else TRAIN_OBJECTS
    examples = []
    for index in range(count):
        q1 = rng.randint(0, 10)
        q2 = rng.randint(0, 10)
        relation = "SAME" if q1 == q2 else ("LEFT" if q1 > q2 else "RIGHT")
        examples.append(
            _record(
                index,
                "m192.invariance.more_less",
                "MORE\n"
                f"LEFT: {quantity_surface(q1, rng.choice(objects), 'space')}\n"
                f"RIGHT: {quantity_surface(q2, rng.choice(objects), 'bar')}",
                f"FINAL {relation}",
                phase="cardinality_invariance",
                left_quantity=q1,
                right_quantity=q2,
                heldout=heldout,
            )
        )
    return examples


def _small_concrete_add_examples(
    rng: random.Random,
    *,
    count: int,
    heldout: bool,
) -> list[dict[str, Any]]:
    objects = HELDOUT_OBJECTS if heldout else TRAIN_OBJECTS
    examples = []
    for index in range(count):
        a = rng.randint(0, 10)
        b = rng.randint(0, 10 - a)
        obj_a = rng.choice(objects)
        obj_b = rng.choice(objects)
        prompt = (
            "COMBINE_COUNT\n"
            f"GROUP_A: {quantity_surface(a, obj_a, 'space')}\n"
            f"GROUP_B: {quantity_surface(b, obj_b, 'bar')}"
        )
        examples.append(
            _record(
                index,
                "m192.add.concrete_small",
                prompt,
                f"FINAL {a + b}",
                phase="concrete_addition",
                a=a,
                b=b,
                result=a + b,
                heldout=heldout,
            )
        )
    return examples


def _symbolic_2digit_eval(
    rng: random.Random,
    *,
    count: int,
    regroup: bool | None,
    heldout_pairs: bool,
) -> list[dict[str, Any]]:
    examples = []
    seen_prompts = set()
    attempts = 0
    while len(examples) < count and attempts < count * 300:
        attempts += 1
        a = rng.randint(10, 69)
        b = rng.randint(10, 69)
        if _has_holdout_digit_pair(a, b) != heldout_pairs:
            continue
        if regroup is not None and _needs_regroup(a, b) != regroup:
            continue
        prompt = f"ADD {a} {b}"
        if prompt in seen_prompts:
            continue
        seen_prompts.add(prompt)
        examples.append(symbolic_add_example(a, b, index=len(examples)))
    return examples


def _range_ood_eval(rng: random.Random, *, count: int) -> list[dict[str, Any]]:
    examples = []
    seen = set()
    attempts = 0
    while len(examples) < count and attempts < count * 500:
        attempts += 1
        a = rng.randint(70, 99)
        b = rng.randint(20, 49)
        if _has_holdout_digit_pair(a, b):
            continue
        prompt = f"ADD {a} {b}"
        if prompt in seen:
            continue
        seen.add(prompt)
        examples.append(symbolic_add_example(a, b, index=len(examples)))
    if len(examples) < count:
        raise RuntimeError(
            f"Could not generate {count} range-OOD examples; got {len(examples)}"
        )
    return examples


def _length_eval(
    rng: random.Random,
    *,
    digits: int,
    count: int,
) -> list[dict[str, Any]]:
    low = 10 ** (digits - 1)
    high = 10**digits - 1
    examples = []
    seen = set()
    while len(examples) < count:
        a = rng.randint(low, high)
        b = rng.randint(low, high)
        if _has_holdout_digit_pair(a, b):
            continue
        prompt = f"ADD {a} {b}"
        if prompt in seen:
            continue
        seen.add(prompt)
        examples.append(symbolic_add_example(a, b, index=len(examples)))
    return examples


def _structured_add_train(rng: random.Random, *, count: int) -> list[dict[str, Any]]:
    examples = []
    seen = set()
    while len(examples) < count:
        a = rng.randint(10, 69)
        b = rng.randint(10, 69)
        if _has_holdout_digit_pair(a, b):
            continue
        prompt = f"PLACE_VALUE_ADD\nA: {a}\nB: {b}"
        if prompt in seen:
            continue
        seen.add(prompt)
        examples.append(structured_add_example(a, b, index=len(examples)))
        if len(seen) > 2600 and len(examples) < count:
            examples = _repeat_to_count(examples, count)
            break
    return examples


def _paired_examples(rng: random.Random, *, count: int) -> list[dict[str, Any]]:
    examples = []
    for index in range(count):
        q = rng.randint(0, 10)
        obj = rng.choice(TRAIN_OBJECTS)
        prompt = (
            f"SAME_VALUE\nQUANTITY: {quantity_surface(q, obj, 'space')}\nSYMBOL: {q}"
        )
        examples.append(
            _record(
                index,
                "m192.paired.quantity_symbol",
                prompt,
                "FINAL YES",
                phase="paired_representation",
                quantity=q,
                object_family=obj,
            )
        )
        a = rng.randint(0, 10)
        b = rng.randint(0, 10 - a)
        prompt = (
            "PAIRED_ADD\n"
            f"CONCRETE_A: {quantity_surface(a, obj, 'space')}\n"
            f"CONCRETE_B: {quantity_surface(b, rng.choice(TRAIN_OBJECTS), 'bar')}\n"
            f"SYMBOLIC: {a} + {b}"
        )
        examples.append(
            _record(
                index + count,
                "m192.paired.concrete_symbolic_add",
                prompt,
                f"FINAL {a + b}",
                phase="paired_representation",
                a=a,
                b=b,
                result=a + b,
            )
        )
    return examples[:count]


def _record(
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


def _train_and_eval(
    spec: TrainSpec,
    *,
    eval_splits: dict[str, Path],
    max_new_tokens: int,
) -> None:
    run_dir = RUNS_DIR / spec.name
    run_dir.mkdir(parents=True, exist_ok=True)
    final_checkpoint = _final_checkpoint(run_dir)
    if final_checkpoint is None:
        result = train_lm(
            TrainConfig(
                train_path=spec.train_path,
                eval_path=spec.eval_path,
                tokenizer_path=TOKENIZER_PATH,
                output_dir=run_dir,
                model_config_name=MODEL_CONFIG,
                steps=spec.steps,
                batch_size=BATCH_SIZE,
                sequence_length=SEQUENCE_LENGTH,
                loss_mode=LOSS_MODE,
                learning_rate=LEARNING_RATE,
                grad_clip_norm=GRAD_CLIP_NORM,
                numeric_tokenization=NUMERIC_TOKENIZATION,
                position_encoding=POSITION_ENCODING,
                seed=spec.seed,
                eval_every=spec.steps,
                eval_batches=20,
                save_every=spec.steps,
                cache_dir=ROOT / "cache" / "tokenized_m192",
                init_checkpoint_path=spec.init_checkpoint_path,
            )
        )
        (run_dir / "run_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        final_checkpoint = _final_checkpoint(run_dir)
    if final_checkpoint is None:
        raise RuntimeError(f"No checkpoint produced for {spec.name}")
    _evaluate_checkpoint(
        run_dir=run_dir,
        checkpoint_path=final_checkpoint,
        eval_splits=eval_splits,
        max_new_tokens=max_new_tokens,
    )
    _prune_intermediate_checkpoints(run_dir)


def _evaluate_checkpoint(
    *,
    run_dir: Path,
    checkpoint_path: Path,
    eval_splits: dict[str, Path],
    max_new_tokens: int,
) -> None:
    for split_name, eval_path in eval_splits.items():
        summary_path = run_dir / "eval" / split_name / "summary.json"
        if summary_path.exists():
            continue
        eval_lm(
            checkpoint_path=checkpoint_path,
            eval_path=eval_path,
            tokenizer_path=TOKENIZER_PATH,
            output_dir=run_dir / "eval" / split_name,
            max_examples=None,
            max_new_tokens=max_new_tokens,
            seed=SEED,
            numeric_tokenization=NUMERIC_TOKENIZATION,
        )


def _representation_probe(checkpoint_path: Path) -> dict[str, Any]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=TOKENIZER_PATH,
        device=device,
    )
    prompts = []
    for q in range(11):
        forms = [
            str(q),
            quantity_surface(q, "X", "space"),
            quantity_surface(q, "A", "space"),
            quantity_surface(q, "ONE", "space"),
        ]
        prompts.extend((q, f"COUNT\nITEMS: {form}") for form in forms)

    vectors: list[tuple[int, torch.Tensor]] = []
    with torch.no_grad():
        for q, prompt in prompts:
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
            vectors.append((q, hidden[0, -1].detach().cpu()))

    same_values = []
    different_values = []
    for (q1, v1), (q2, v2) in itertools.combinations(vectors, 2):
        score = torch.nn.functional.cosine_similarity(v1, v2, dim=0).item()
        if q1 == q2:
            same_values.append(score)
        else:
            different_values.append(score)
    centroids = {
        q: torch.stack([v for value, v in vectors if value == q]).mean(dim=0)
        for q in range(11)
    }
    correct = 0
    for q, vector in vectors:
        predicted = max(
            centroids,
            key=lambda candidate: torch.nn.functional.cosine_similarity(
                vector,
                centroids[candidate],
                dim=0,
            ).item(),
        )
        correct += int(predicted == q)
    return {
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_step": checkpoint.get("step"),
        "same_quantity_cosine": _mean(same_values),
        "different_quantity_cosine": _mean(different_values),
        "centroid_probe_accuracy": correct / len(vectors),
        "count": len(vectors),
    }


def _analyze_run(run_dir: Path) -> dict[str, Any]:
    payload = {
        "train_config": _read_json_if_exists(run_dir / "train_config.json"),
        "run_result": _read_json_if_exists(run_dir / "run_result.json"),
        "metrics": _read_jsonl_if_exists(run_dir / "metrics.jsonl"),
        "eval": {},
        "probes": _read_json_if_exists(run_dir / "probes" / "quantity_probe.json"),
    }
    for summary_path in sorted((run_dir / "eval").glob("*/summary.json")):
        payload["eval"][summary_path.parent.name] = _summary_payload(
            _read_json(summary_path)
        )
    return payload


def _summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    overall = summary.get("overall", {})
    return {
        "count": int(overall.get("count", 0)),
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "full_nem": float(overall.get("normalized_exact_match", 0.0)),
        "empty_rate": float(overall.get("empty_prediction_rate", 0.0)),
        "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
        "avg_tokens": float(overall.get("avg_tokens_generated", 0.0)),
        "by_task_type": {
            key: float(value.get("final_normalized_exact_match", 0.0))
            for key, value in summary.get("by_task_type", {}).items()
        },
    }


def _main_eval_splits() -> dict[str, Path]:
    names = [
        "count_seen",
        "count_heldout_object",
        "count_heldout_format",
        "same_count",
        "more_less",
        "successor_symbolic",
        "successor_concrete",
        "small_concrete_add",
        "small_symbolic_add",
        "place_value",
        "place_value_holdout",
        "base10_grouping",
        "base10_ungrouping",
        "add_2digit_no_regroup",
        "add_2digit_regroup",
        "pure_symbolic_clean_id",
        "pure_symbolic_digit_pair_ood",
        "pure_symbolic_range_ood",
        "length_3",
        "length_4",
        "length_5",
        "length_6",
        "length_8",
    ]
    return {name: DATASET_DIR / "eval" / f"{name}.jsonl" for name in names}


def _main_groups() -> tuple[GroupName, ...]:
    return (
        "direct_symbolic",
        "direct_compute_matched",
        "symbolic_concept_first",
        "concrete_sequential",
        "interleaved_concrete_symbolic",
        "paired_representation",
    )


def _decision(analysis: dict[str, Any]) -> str:
    runs = analysis.get("runs", {})
    count_best = max(
        (_score(run, "count_heldout_object") for run in runs.values()),
        default=0.0,
    )
    place_best = max(
        (_score(run, "place_value_holdout") for run in runs.values()), default=0.0
    )
    concrete_add_best = max(
        (_score(run, "small_concrete_add") for run in runs.values()),
        default=0.0,
    )
    direct_ood = _score(runs.get("direct_symbolic", {}), "pure_symbolic_digit_pair_ood")
    best_group = _best_concept_group(analysis)
    best_ood = _score(runs.get(best_group, {}), "pure_symbolic_digit_pair_ood")
    if count_best < 0.98:
        return (
            "STOP: cardinality did not generalize to held-out object families. "
            "Do not interpret later addition as grounded numeracy yet."
        )
    if place_best < 0.95:
        return (
            "STOP: cardinality is learnable, but place-value did not reach the "
            ".95 gate. Diagnose base-10 representation before symbolic ADD claims."
        )
    if concrete_add_best < 0.98:
        return (
            "STOP: concrete small addition did not reach .98. The bridge to "
            "symbolic addition is not ready."
        )
    if best_ood > direct_ood + 0.05:
        return (
            "PROMISING: the best concept/concrete curriculum beats direct symbolic "
            "on digit-pair OOD. Confirm with multi-seed and ablate the winning stages."
        )
    return (
        "NEGATIVE/MIXED: concept curriculum reached prerequisite gates only if shown "
        "above, but did not clearly beat direct symbolic OOD in this run."
    )


def _best_concept_group(analysis: dict[str, Any]) -> str:
    candidates = [
        "symbolic_concept_first",
        "concrete_sequential",
        "interleaved_concrete_symbolic",
        "paired_representation",
    ]
    runs = analysis.get("runs", {})
    if not runs:
        return "none"
    return max(
        candidates,
        key=lambda name: (
            _score(runs.get(name, {}), "pure_symbolic_digit_pair_ood")
            + _score(runs.get(name, {}), "pure_symbolic_range_ood")
            + _score(runs.get(name, {}), "length_3")
        ),
        default="none",
    )


def _score(run: dict[str, Any], split: str) -> float:
    return float(run.get("eval", {}).get(split, {}).get("final_nem", 0.0))


def _dataset_audit_table(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    rows = [
        "| area | item | count | task types | prompt intersection max |",
        "|---|---|---:|---|---:|",
    ]
    intersections = manifest.get("prompt_intersections", {})
    max_intersection = max(intersections.values(), default=0)
    for area in ("curricula", "eval_splits", "bridge_sets", "diagnostic_sets"):
        for name, audit in manifest.get(area, {}).items():
            rows.append(
                f"| {area} | {name} | {audit.get('count', 0)} | "
                f"{audit.get('task_type_counts', {})} | {max_intersection} |"
            )
    return "\n".join(rows)


def _tokenization_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| family | max count | monotonic | aggregate leak rows |",
        "|---|---:|---|---:|",
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in analysis.get("manifest", {}).get("tokenization_audit", []):
        grouped[row["family"]].append(row)
    for family, values in sorted(grouped.items()):
        rows.append(
            f"| {family} | {max(v['count'] for v in values)} | "
            f"{all(v['monotonic_vs_previous'] for v in values)} | "
            f"{sum(bool(v['single_aggregate_token']) for v in values)} |"
        )
    return "\n".join(rows)


def _metric_table(
    analysis: dict[str, Any],
    splits: list[str],
    *,
    groups: Sequence[str] | None = None,
) -> str:
    groups = list(groups) if groups is not None else list(_main_groups())
    rows = ["| group | " + " | ".join(splits) + " |", "|---|" + "---:|" * len(splits)]
    runs = analysis.get("runs", {})
    for group in groups:
        run = runs.get(group, {})
        rows.append(
            f"| {group} | "
            + " | ".join(f"{_score(run, split):.4f}" for split in splits)
            + " |"
        )
    return "\n".join(rows)


def _comparison_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| baseline | clean ID | digit-pair OOD | range OOD | length3 | length8 |",
        "|---|---:|---:|---:|---:|---:|",
        "| M-19.1 RFFT | 1.0000 trained lengths 1-5 | 0.0333 | n/a | 1.0000 trained | 0.0000 |",
        "| M-19.1 Turing | 1.0000 trained lengths 1-5 | 0.0000 | n/a | 1.0000 trained | 0.0000 |",
    ]
    runs = analysis.get("runs", {})
    for group in _main_groups():
        run = runs.get(group, {})
        rows.append(
            f"| {group} | {_score(run, 'pure_symbolic_clean_id'):.4f} | "
            f"{_score(run, 'pure_symbolic_digit_pair_ood'):.4f} | "
            f"{_score(run, 'pure_symbolic_range_ood'):.4f} | "
            f"{_score(run, 'length_3'):.4f} | {_score(run, 'length_8'):.4f} |"
        )
    return "\n".join(rows)


def _bridge_table(analysis: dict[str, Any]) -> str:
    rows = ["| run | small symbolic ADD |", "|---|---:|"]
    for name, run in sorted(analysis.get("runs", {}).items()):
        if name.startswith("bridge_"):
            rows.append(f"| {name} | {_score(run, 'small_symbolic_add'):.4f} |")
    if len(rows) == 2:
        rows.append("| not run yet | 0.0000 |")
    return "\n".join(rows)


def _probe_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| group | same quantity cosine | different quantity cosine | centroid probe acc |",
        "|---|---:|---:|---:|",
    ]
    for name, run in sorted(analysis.get("runs", {}).items()):
        probe = run.get("probes")
        if probe:
            rows.append(
                f"| {name} | {probe.get('same_quantity_cosine', 0.0):.4f} | "
                f"{probe.get('different_quantity_cosine', 0.0):.4f} | "
                f"{probe.get('centroid_probe_accuracy', 0.0):.4f} |"
            )
    if len(rows) == 2:
        rows.append("| not run yet | 0.0000 | 0.0000 | 0.0000 |")
    return "\n".join(rows)


def _multiseed_table(analysis: dict[str, Any]) -> str:
    grouped: dict[str, list[float]] = defaultdict(list)
    for name, run in analysis.get("runs", {}).items():
        if name.startswith("multiseed_"):
            group = name.removeprefix("multiseed_").rsplit("_seed", 1)[0]
            grouped[group].append(_score(run, "pure_symbolic_digit_pair_ood"))
    rows = ["| group | seeds | digit-pair OOD mean | std |", "|---|---:|---:|---:|"]
    for group, values in sorted(grouped.items()):
        rows.append(
            f"| {group} | {len(values)} | {_mean(values):.4f} | {_std(values):.4f} |"
        )
    if len(rows) == 2:
        rows.append("| not run yet | 0 | 0.0000 | 0.0000 |")
    return "\n".join(rows)


def _ablation_status(analysis: dict[str, Any]) -> str:
    if "PROMISING" in str(analysis.get("decision", "")):
        return (
            "Promising result detected; next run should ablate reverse MAKE, "
            "SAME_COUNT/MORE/LESS, successor, base-10 grouping, and paired examples."
        )
    return "Skipped: no promising concrete/interleaved result yet."


def _recommendation(analysis: dict[str, Any]) -> str:
    decision = str(analysis.get("decision", ""))
    if decision.startswith("STOP: cardinality"):
        return "Tighten object-token curriculum and COUNT formatting before any addition work."
    if decision.startswith("STOP: cardinality is learnable"):
        return "Focus next on base-10 grouping/place-value, not architecture or subtraction."
    if "PROMISING" in decision:
        return (
            "Run targeted ablations and then the few-shot subtraction transfer probe."
        )
    return "Treat this as a negative control unless multi-seed or ablations reveal a delayed-payoff effect."


def _remote_lines(analysis: dict[str, Any]) -> str:
    remote = analysis.get("remote", {})
    lines = [
        f"- hostname: `{remote.get('hostname', 'unknown')}`",
        f"- GPU: `{remote.get('gpu', 'unknown')}`",
        f"- CUDA visible: `{remote.get('cuda_visible', 'unknown')}`",
        f"- commit SHA: `{_git_commit()}`",
    ]
    return "\n".join(lines)


def _remote_environment() -> dict[str, Any]:
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
        "python": subprocess.getoutput("python --version"),
        "git_commit": _git_commit(),
        "git_branch": subprocess.getoutput("git branch --show-current"),
    }


def _final_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    return checkpoints[-1] if checkpoints else None


def _prune_intermediate_checkpoints(run_dir: Path) -> None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    for checkpoint in checkpoints[:-1]:
        checkpoint.unlink(missing_ok=True)


def _write_jsonl(path: Path, examples: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False, sort_keys=True))
            file.write("\n")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    return _read_json(path) if path.exists() else {}


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _audit_examples(examples: Sequence[dict[str, Any]]) -> dict[str, Any]:
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
        "format_families": sorted(
            {
                str(item.get("format_family"))
                for item in metadata
                if item.get("format_family")
            }
        ),
        "heldout_digit_pair_count": sum(
            bool(item.get("heldout_digit_pair")) for item in metadata
        ),
        "digit_lengths": dict(
            Counter(
                str(item.get("digit_length"))
                for item in metadata
                if item.get("digit_length")
            )
        ),
        "result_lengths": dict(
            Counter(
                str(item.get("result_length"))
                for item in metadata
                if item.get("result_length")
            )
        ),
    }


def _prompt_intersections(
    curricula: dict[str, list[dict[str, Any]]],
    eval_splits: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    result = {}
    for train_name, train_examples in curricula.items():
        train_prompts = {str(example["prompt"]) for example in train_examples}
        for eval_name, eval_examples in eval_splits.items():
            eval_prompts = {str(example["prompt"]) for example in eval_examples}
            result[f"{train_name}__{eval_name}"] = len(train_prompts & eval_prompts)
    return result


def _interleave(
    rng: random.Random,
    pools: Sequence[Sequence[dict[str, Any]]],
) -> list[dict[str, Any]]:
    cursors = [0 for _ in pools]
    result = []
    while any(cursor < len(pool) for cursor, pool in zip(cursors, pools, strict=True)):
        order = list(range(len(pools)))
        rng.shuffle(order)
        for index in order:
            if cursors[index] < len(pools[index]):
                result.append(pools[index][cursors[index]])
                cursors[index] += 1
    return result


def _repeat_to_count(
    examples: Sequence[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    if not examples:
        return []
    result = []
    for index in range(count):
        item = dict(examples[index % len(examples)])
        item["id"] = f"{item['task_type']}:repeat:{index:06d}"
        result.append(item)
    return result


def _number_pairs() -> list[tuple[int, int]]:
    return [(a, b) for a in range(20) for b in range(20)]


def _heldout_numbers_2digit() -> list[int]:
    return [n for n in range(10, 100) if n % 10 in {5, 6, 7, 8, 9}]


def _needs_regroup(a: int, b: int) -> bool:
    return (a % 10) + (b % 10) >= 10


def _has_holdout_digit_pair(a: int, b: int) -> bool:
    pairs = zip(reversed(str(a)), reversed(str(b)), strict=False)
    return any(
        (int(left), int(right)) in HOLDOUT_DIGIT_PAIR_KEYS for left, right in pairs
    )


def _object_spans(text: str, family: str) -> list[tuple[int, int]]:
    spans = []
    cursor = 0
    while True:
        start = text.find(family, cursor)
        if start < 0:
            return spans
        end = start + len(family)
        spans.append((start, end))
        cursor = end


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _std(values: Iterable[float]) -> float:
    values = list(values)
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _git_commit() -> str:
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
