from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.runner import eval_lm
from ai_brain.runtime.device import get_device_info
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m17_clean_compositional"
RUNS_DIR = ROOT / "runs" / "m17_clean_compositional"
DOC_PATH = ROOT / "docs" / "m17_clean_compositional_curriculum_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m17_clean_compositional_curriculum_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 317000
TRAIN_COUNT = 3000
EVAL_COUNT = 500
COMPOSITION_TRAIN_COUNT = 3000
COMPOSITION_EVAL_COUNT = 500
SINGLE_STEPS = 5000
JOINT_STEPS = 5000
STAGED_STEPS = 5000
COMPOSITION_STEPS = 5000
TINY_CONTROL_STEPS = 5000
MAX_NEW_TOKENS = 24

PrimitiveName = Literal[
    "add",
    "sub",
    "missing_addend",
    "compare_numbers",
    "compare_sum",
    "state_add",
    "state_sub",
]

PRIMITIVES: tuple[PrimitiveName, ...] = (
    "add",
    "sub",
    "missing_addend",
    "compare_numbers",
    "compare_sum",
    "state_add",
    "state_sub",
)
SYMBOLIC_PRIMITIVES: tuple[PrimitiveName, ...] = (
    "add",
    "sub",
    "missing_addend",
    "compare_numbers",
    "compare_sum",
)
STAGES: tuple[tuple[str, tuple[PrimitiveName, ...]], ...] = (
    ("stage1_add_sub", ("add", "sub")),
    ("stage2_missing_compare", ("add", "sub", "missing_addend", "compare_numbers")),
    (
        "stage3_compare_sum",
        ("add", "sub", "missing_addend", "compare_numbers", "compare_sum"),
    ),
    ("stage4_state", PRIMITIVES),
)

STATE_ADD_TEMPLATES = (
    "У Веры было {a} монет. Вере дали ещё {b} монет. Сколько стало?",
    "У Олега было {a} карандашей. Ему добавили {b} карандашей. Сколько стало?",
    "На полке было {a} книг. Поставили ещё {b} книг. Сколько теперь книг?",
    "В коробке лежало {a} деталей. Добавили {b} деталей. Сколько деталей стало?",
)
STATE_SUB_TEMPLATES = (
    "У Веры было {a} монет. У Веры забрали {b} монет. Сколько осталось?",
    "У Олега было {a} карандашей. Он отдал {b} карандашей. Сколько осталось?",
    "На полке было {a} книг. Сняли {b} книг. Сколько книг осталось?",
    "В коробке лежало {a} деталей. Убрали {b} деталей. Сколько деталей осталось?",
)

STEP1_RE = re.compile(r"(?im)^\s*STEP1\s+(?P<value>[+-]?\d+)\s*$")
STEP2_RE = re.compile(r"(?im)^\s*STEP2\s+(?P<value>[+-]?\d+)\s*$")


@dataclass(frozen=True)
class RunSpec:
    name: str
    train_path: Path
    eval_path: Path
    model_config: str = "arithmetic_3m"
    steps: int = SINGLE_STEPS
    seed: int = SEED
    init_checkpoint: Path | None = None
    group: str = "single"
    sequence_length: int = 128


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-singles")
    subparsers.add_parser("run-joint")
    subparsers.add_parser("run-staged")
    subparsers.add_parser("run-compositions")
    subparsers.add_parser("run-tiny-control")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-singles":
        run_specs(single_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-joint":
        run_specs(joint_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-staged":
        run_staged()
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-compositions":
        run_specs(composition_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-tiny-control":
        run_specs(tiny_control_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_specs(single_specs())
        run_specs(joint_specs())
        run_staged()
        run_specs(composition_specs())
        run_specs(tiny_control_specs())
        analyze_all()
        build_report(checks_passed=False)
    else:
        raise AssertionError(args.command)
    return 0


def prepare_datasets() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    primitive_records = {
        primitive: _build_primitive_splits(primitive, rng=random.Random(SEED + index))
        for index, primitive in enumerate(PRIMITIVES, start=1)
    }
    composition_records = _build_composition_splits(
        primitive_records=primitive_records,
        rng=random.Random(SEED + 100),
    )

    manifest: dict[str, Any] = {
        "kind": "m17_clean_compositional_curriculum",
        "seed": SEED,
        "answer_format": "FINAL <value>",
        "numeric_tokenization": "digit_safe",
        "train_count_per_primitive": TRAIN_COUNT,
        "eval_count": EVAL_COUNT,
        "primitive_splits": {},
        "joint_splits": {},
        "composition_splits": {},
    }

    for primitive, splits in primitive_records.items():
        primitive_dir = DATASET_DIR / primitive
        primitive_dir.mkdir(parents=True, exist_ok=True)
        split_info = {
            split: _write_jsonl(primitive_dir / f"{split}.jsonl", records)
            for split, records in splits.items()
        }
        manifest["primitive_splits"][primitive] = {
            "files": split_info,
            "verification": _verify_splits(splits),
            "distribution": {
                split: _distribution(records) for split, records in splits.items()
            },
        }

    joint_splits = {
        "train_joint_symbolic": _balanced_mix(
            [primitive_records[name]["train"] for name in SYMBOLIC_PRIMITIVES],
            count_per_bucket=TRAIN_COUNT,
            seed=SEED + 200,
        ),
        "train_joint_all": _balanced_mix(
            [primitive_records[name]["train"] for name in PRIMITIVES],
            count_per_bucket=TRAIN_COUNT,
            seed=SEED + 201,
        ),
    }
    for stage_name, stage_primitives in STAGES:
        joint_splits[f"train_{stage_name}"] = _balanced_mix(
            [primitive_records[name]["train"] for name in stage_primitives],
            count_per_bucket=TRAIN_COUNT,
            seed=SEED + 300 + len(stage_primitives),
        )
    for split, records in joint_splits.items():
        manifest["joint_splits"][split] = _write_jsonl(
            DATASET_DIR / f"{split}.jsonl", records
        )

    composition_dir = DATASET_DIR / "composition"
    composition_dir.mkdir(parents=True, exist_ok=True)
    for split, records in composition_records.items():
        manifest["composition_splits"][split] = _write_jsonl(
            composition_dir / f"{split}.jsonl",
            records,
        )

    manifest["composition_verification"] = _verify_splits(composition_records)
    manifest["composition_distribution"] = {
        split: _distribution(records) for split, records in composition_records.items()
    }
    manifest["state_templates"] = {
        "state_add": list(STATE_ADD_TEMPLATES),
        "state_sub": list(STATE_SUB_TEMPLATES),
    }
    manifest["sample_records"] = {
        primitive: primitive_records[primitive]["train"][0] for primitive in PRIMITIVES
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def single_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name=f"single_{primitive}_3m",
            train_path=DATASET_DIR / primitive / "train.jsonl",
            eval_path=DATASET_DIR / primitive / "eval_seen.jsonl",
            steps=SINGLE_STEPS,
            seed=SEED + index,
            group="single",
        )
        for index, primitive in enumerate(PRIMITIVES, start=10)
    ]


def joint_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name="joint_symbolic_3m",
            train_path=DATASET_DIR / "train_joint_symbolic.jsonl",
            eval_path=DATASET_DIR / "add" / "eval_seen.jsonl",
            steps=JOINT_STEPS,
            seed=SEED + 50,
            group="joint",
        ),
        RunSpec(
            name="joint_all_3m",
            train_path=DATASET_DIR / "train_joint_all.jsonl",
            eval_path=DATASET_DIR / "add" / "eval_seen.jsonl",
            steps=JOINT_STEPS,
            seed=SEED + 51,
            group="joint",
        ),
    ]


def composition_specs() -> list[RunSpec]:
    primitive_plus_add_sub = DATASET_DIR / "composition" / "train_holdout_sub_add.jsonl"
    return [
        RunSpec(
            name="composition_seen_add_sub_sub_add_3m",
            train_path=DATASET_DIR / "composition" / "train_seen_compositions.jsonl",
            eval_path=DATASET_DIR / "composition" / "eval_add_sub_seen.jsonl",
            steps=COMPOSITION_STEPS,
            seed=SEED + 70,
            group="composition",
            sequence_length=256,
        ),
        RunSpec(
            name="composition_holdout_sub_add_3m",
            train_path=primitive_plus_add_sub,
            eval_path=DATASET_DIR / "composition" / "eval_add_sub_seen.jsonl",
            steps=COMPOSITION_STEPS,
            seed=SEED + 71,
            group="composition",
            sequence_length=256,
        ),
    ]


def tiny_control_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name="tiny_control_joint_symbolic",
            train_path=DATASET_DIR / "train_joint_symbolic.jsonl",
            eval_path=DATASET_DIR / "add" / "eval_seen.jsonl",
            model_config="tiny",
            steps=TINY_CONTROL_STEPS,
            seed=SEED + 90,
            group="control",
        )
    ]


def run_staged() -> None:
    checkpoint: Path | None = None
    for index, (stage_name, _stage_primitives) in enumerate(STAGES, start=1):
        spec = RunSpec(
            name=f"staged_{index}_{stage_name}_3m",
            train_path=DATASET_DIR / f"train_{stage_name}.jsonl",
            eval_path=DATASET_DIR / "add" / "eval_seen.jsonl",
            steps=STAGED_STEPS,
            seed=SEED + 60 + index,
            init_checkpoint=checkpoint,
            group="staged",
        )
        run_specs([spec])
        checkpoint = _checkpoint_path(spec)


def run_specs(specs: Sequence[RunSpec]) -> None:
    for spec in specs:
        checkpoint_path = _checkpoint_path(spec)
        if checkpoint_path.exists():
            print(f"skip existing run: {spec.name}")
            continue
        output_dir = RUNS_DIR / spec.name
        output_dir.mkdir(parents=True, exist_ok=True)
        config = TrainConfig(
            train_path=spec.train_path,
            eval_path=spec.eval_path,
            tokenizer_path=TOKENIZER_PATH,
            output_dir=output_dir,
            model_config_name=spec.model_config,
            steps=spec.steps,
            batch_size=8,
            sequence_length=spec.sequence_length,
            loss_mode="answer-only",
            numeric_tokenization="digit_safe",
            eval_every=max(250, spec.steps // 5),
            eval_batches=20,
            save_every=spec.steps,
            seed=spec.seed,
            init_checkpoint_path=spec.init_checkpoint,
        )
        started = time.time()
        result = train_lm(config)
        payload = {
            "run_spec": _spec_payload(spec),
            "train_result": result,
            "elapsed_seconds": time.time() - started,
        }
        (output_dir / "run_result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def analyze_all() -> None:
    analysis: dict[str, Any] = {
        "single": _analyze_specs(single_specs()),
        "joint": _analyze_specs(joint_specs()),
        "staged": _analyze_specs(_staged_specs_for_analysis()),
        "composition": _analyze_specs(composition_specs()),
        "control": _analyze_specs(tiny_control_specs()),
    }
    analysis["single_summary"] = _single_summary(analysis["single"])
    analysis["joint_retention"] = _joint_retention(analysis)
    analysis["staged_retention_matrix"] = _staged_retention_matrix(analysis)
    analysis["composition_summary"] = _composition_summary(analysis["composition"])
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis_path = RUNS_DIR / "analysis.json"
    manifest_path = DATASET_DIR / "manifest.json"
    analysis = _read_json(analysis_path) if analysis_path.exists() else {}
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    device = get_device_info(prefer_cuda=True)
    commit = _git_commit()

    lines = [
        "# M-17 Clean Compositional Reasoning Curriculum",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{commit}`",
        f"- device: `{device.device}` ({device.name})",
        "",
        "## Dataset Design",
        "",
        (
            "- task types: ADD, SUB, MISSING_ADDEND, COMPARE_NUMBERS, "
            "COMPARE_SUM, STATE_ADD, STATE_SUB"
        ),
        (
            "- prompts: deterministic symbolic prompts plus balanced Russian "
            "state-change templates"
        ),
        (
            "- answers: `FINAL <value>`; composition answers also include `STEP1` "
            "and `STEP2` diagnostics"
        ),
        "- numeric tokenization: `digit_safe`",
        (
            "- ranges: symbolic and state primitives use two-digit operands "
            "`10..99`; subtraction is non-negative; composition uses two-digit "
            "operands with non-negative finals"
        ),
        (
            "- balancing: train/eval sampling is bucket-balanced by carry/borrow, "
            "output length, or relation where applicable; joint/staged datasets use "
            "equal task sampling"
        ),
        f"- train examples per primitive: {manifest.get('train_count_per_primitive', 'n/a')}",
        f"- eval examples per split: {manifest.get('eval_count', 'n/a')}",
        "",
        "### Train/Eval Intersections",
        "",
        _manifest_intersections_table(manifest),
        "",
        "## Single Primitive Results",
        "",
        _single_table(analysis),
        "",
        "## Joint Multitask Results",
        "",
        _joint_table(analysis),
        "",
        "## Staged Curriculum",
        "",
        _staged_table(analysis),
        "",
        "## Composition Results",
        "",
        _composition_table(analysis),
        "",
        "## Symbolic vs Language Context Transfer",
        "",
        _context_transfer_text(analysis),
        "",
        "## Tiny vs 5.29M Control",
        "",
        _control_text(analysis),
        "",
        "## Failure Samples",
        "",
        _failure_samples_text(analysis),
        "",
        "## Interpretation",
        "",
        _interpretation(analysis),
        "",
        "## Recommended Next Milestone",
        "",
        _recommendation(analysis),
        "",
    ]
    text = "\n".join(lines)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def _build_primitive_splits(
    primitive: PrimitiveName,
    *,
    rng: random.Random,
) -> dict[str, list[dict[str, Any]]]:
    if primitive in {"add", "missing_addend", "state_add"}:
        cases = [(a, b) for a in range(10, 100) for b in range(10, 100)]
        key_fn = lambda pair: (
            "3_digit" if pair[0] + pair[1] >= 100 else "2_digit",
            _carry_bucket(pair[0], pair[1]),
        )
    elif primitive in {"sub", "state_sub"}:
        cases = [(a, b) for a in range(10, 100) for b in range(10, a + 1)]
        key_fn = lambda pair: (
            "borrow" if pair[0] % 10 < pair[1] % 10 else "no_borrow",
            f"{len(str(pair[0] - pair[1]))}_digit",
        )
    elif primitive == "compare_numbers":
        cases = [(a, b) for a in range(10, 100) for b in range(10, 100)]
        key_fn = lambda pair: _compare_relation(pair[0], pair[1])
    elif primitive == "compare_sum":
        cases = _compare_sum_candidates(rng)
        key_fn = lambda values: _compare_relation(
            values[0] + values[1], values[2] + values[3]
        )
    else:
        raise AssertionError(primitive)

    train_cases = _balanced_sample(
        cases, TRAIN_COUNT, key_fn=key_fn, seed=rng.randint(1, 10**9)
    )
    train_keys = {_case_key(primitive, case) for case in train_cases}
    remaining = [case for case in cases if _case_key(primitive, case) not in train_keys]
    eval_seen_cases = _balanced_sample(
        train_cases, EVAL_COUNT, key_fn=key_fn, seed=rng.randint(1, 10**9)
    )
    eval_unseen_cases = _balanced_sample(
        remaining, EVAL_COUNT, key_fn=key_fn, seed=rng.randint(1, 10**9)
    )
    eval_train_cases = _balanced_sample(
        train_cases, EVAL_COUNT, key_fn=key_fn, seed=rng.randint(1, 10**9)
    )

    return {
        "train": [
            _primitive_record(primitive, case, "train", index)
            for index, case in enumerate(train_cases)
        ],
        "eval_train": [
            _primitive_record(primitive, case, "eval_train", index)
            for index, case in enumerate(eval_train_cases)
        ],
        "eval_seen": [
            _primitive_record(primitive, case, "eval_seen", index)
            for index, case in enumerate(eval_seen_cases)
        ],
        "eval_unseen": [
            _primitive_record(primitive, case, "eval_unseen", index)
            for index, case in enumerate(eval_unseen_cases)
        ],
    }


def _build_composition_splits(
    *,
    primitive_records: dict[PrimitiveName, dict[str, list[dict[str, Any]]]],
    rng: random.Random,
) -> dict[str, list[dict[str, Any]]]:
    triples = _composition_triples(rng, count=12000)
    key_fn = lambda item: (item[3], "3_digit" if item[4] >= 100 else "2_digit")
    add_sub_cases = [item for item in triples if item[3] == "add_sub"]
    sub_add_cases = [item for item in triples if item[3] == "sub_add"]
    train_add_sub = _balanced_sample(
        add_sub_cases,
        COMPOSITION_TRAIN_COUNT,
        key_fn=key_fn,
        seed=SEED + 401,
    )
    train_sub_add = _balanced_sample(
        sub_add_cases,
        COMPOSITION_TRAIN_COUNT,
        key_fn=key_fn,
        seed=SEED + 402,
    )
    train_keys = {_composition_key(item) for item in [*train_add_sub, *train_sub_add]}
    remaining_add_sub = [
        item for item in add_sub_cases if _composition_key(item) not in train_keys
    ]
    remaining_sub_add = [
        item for item in sub_add_cases if _composition_key(item) not in train_keys
    ]
    eval_add_sub = _balanced_sample(
        train_add_sub,
        COMPOSITION_EVAL_COUNT,
        key_fn=key_fn,
        seed=SEED + 403,
    )
    eval_sub_add = _balanced_sample(
        train_sub_add,
        COMPOSITION_EVAL_COUNT,
        key_fn=key_fn,
        seed=SEED + 404,
    )
    eval_add_sub_unseen = _balanced_sample(
        remaining_add_sub,
        COMPOSITION_EVAL_COUNT,
        key_fn=key_fn,
        seed=SEED + 405,
    )
    eval_sub_add_unseen = _balanced_sample(
        remaining_sub_add,
        COMPOSITION_EVAL_COUNT,
        key_fn=key_fn,
        seed=SEED + 406,
    )
    eval_add_sub_unseen = _unique_composition_teacher_forced(
        eval_add_sub_unseen,
        remaining_add_sub,
        count=COMPOSITION_EVAL_COUNT,
        seed=SEED + 408,
    )
    eval_sub_add_unseen = _unique_composition_teacher_forced(
        eval_sub_add_unseen,
        remaining_sub_add,
        count=COMPOSITION_EVAL_COUNT,
        seed=SEED + 409,
    )

    primitive_replay = _balanced_mix(
        [
            primitive_records["add"]["train"],
            primitive_records["sub"]["train"],
        ],
        count_per_bucket=TRAIN_COUNT,
        seed=SEED + 407,
    )
    train_seen_records = [
        *[
            _composition_record(item, "train_seen_compositions", index)
            for index, item in enumerate(train_add_sub)
        ],
        *[
            _composition_record(
                item, "train_seen_compositions", index + len(train_add_sub)
            )
            for index, item in enumerate(train_sub_add)
        ],
    ]
    train_holdout = [
        *primitive_replay,
        *[
            _composition_record(item, "train_holdout_sub_add", index)
            for index, item in enumerate(train_add_sub)
        ],
    ]
    return {
        "train_seen_compositions": train_seen_records,
        "train_holdout_sub_add": train_holdout,
        "eval_add_sub_seen": [
            _composition_record(item, "eval_add_sub_seen", index)
            for index, item in enumerate(eval_add_sub)
        ],
        "eval_sub_add_seen": [
            _composition_record(item, "eval_sub_add_seen", index)
            for index, item in enumerate(eval_sub_add)
        ],
        "eval_add_sub_unseen": [
            _composition_record(item, "eval_add_sub_unseen", index)
            for index, item in enumerate(eval_add_sub_unseen)
        ],
        "eval_sub_add_unseen": [
            _composition_record(item, "eval_sub_add_unseen", index)
            for index, item in enumerate(eval_sub_add_unseen)
        ],
        "eval_sub_add_teacher_forced": [
            _teacher_forced_record(item, "eval_sub_add_teacher_forced", index)
            for index, item in enumerate(eval_sub_add_unseen)
        ],
        "eval_add_sub_teacher_forced": [
            _teacher_forced_record(item, "eval_add_sub_teacher_forced", index)
            for index, item in enumerate(eval_add_sub_unseen)
        ],
    }


def _primitive_record(
    primitive: PrimitiveName,
    case: tuple[int, ...],
    split: str,
    index: int,
) -> dict[str, Any]:
    if primitive in {"add", "missing_addend", "state_add"}:
        a, b = case
        answer_value = a + b
        carry_bucket = _carry_bucket(a, b)
        metadata: dict[str, Any] = {
            "primitive": primitive,
            "split": split,
            "a": a,
            "b": b,
            "answer_value": answer_value,
            "output_length": f"{len(str(answer_value))}_digit",
            "carry_bucket": carry_bucket,
            "units_carry": int(a % 10 + b % 10 >= 10),
            "final_carry": int(answer_value >= 100),
            "combo_key": _case_key(primitive, case),
            "digit_keys": [f"U:{a % 10}:{b % 10}", f"T:{a // 10}:{b // 10}"],
        }
        if primitive == "add":
            prompt = f"ADD {a:02d} + {b:02d}"
        elif primitive == "missing_addend":
            prompt = f"MISSING {a:02d} + ? = {answer_value}"
            metadata["known"] = a
            metadata["target"] = b
            answer_value = b
            metadata["answer_value"] = answer_value
        else:
            template_index = _state_template_index(
                a,
                b,
                split=split,
                template_count=len(STATE_ADD_TEMPLATES),
            )
            template = STATE_ADD_TEMPLATES[template_index]
            prompt = template.format(a=a, b=b)
    elif primitive in {"sub", "state_sub"}:
        a, b = case
        answer_value = a - b
        borrow_bucket = "borrow" if a % 10 < b % 10 else "no_borrow"
        metadata = {
            "primitive": primitive,
            "split": split,
            "a": a,
            "b": b,
            "answer_value": answer_value,
            "output_length": f"{len(str(answer_value))}_digit",
            "borrow_bucket": borrow_bucket,
            "combo_key": _case_key(primitive, case),
            "digit_keys": [f"U:{a % 10}:{b % 10}", f"T:{a // 10}:{b // 10}"],
        }
        if primitive == "sub":
            prompt = f"SUB {a:02d} - {b:02d}"
        else:
            template_index = _state_template_index(
                a,
                b,
                split=split,
                template_count=len(STATE_SUB_TEMPLATES),
            )
            template = STATE_SUB_TEMPLATES[template_index]
            prompt = template.format(a=a, b=b)
    elif primitive == "compare_numbers":
        a, b = case
        relation = _compare_relation(a, b)
        answer_value = relation
        prompt = f"COMPARE {a:02d} {b:02d}"
        metadata = {
            "primitive": primitive,
            "split": split,
            "a": a,
            "b": b,
            "relation": relation,
            "combo_key": _case_key(primitive, case),
        }
    elif primitive == "compare_sum":
        a, b, c, d = case
        left = a + b
        right = c + d
        relation = "LEFT" if left > right else "RIGHT" if right > left else "EQUAL"
        answer_value = relation
        prompt = f"COMPARE_SUM {a:02d} + {b:02d} | {c:02d} + {d:02d}"
        metadata = {
            "primitive": primitive,
            "split": split,
            "a": a,
            "b": b,
            "c": c,
            "d": d,
            "left": left,
            "right": right,
            "relation": relation,
            "combo_key": _case_key(primitive, case),
            "left_carry_bucket": _carry_bucket(a, b),
            "right_carry_bucket": _carry_bucket(c, d),
        }
    else:
        raise AssertionError(primitive)
    return {
        "id": f"m17.{primitive}.{split}.{index:06d}",
        "task_type": f"m17.{primitive}",
        "prompt": prompt,
        "answer": f"FINAL {answer_value}",
        "metadata": metadata,
    }


def _composition_record(
    item: tuple[int, int, int, str, int, int],
    split: str,
    index: int,
) -> dict[str, Any]:
    a, b, c, op, step1, final = item
    if op == "add_sub":
        prompt = f"DOUBLE ADD_SUB {a:02d} + {b:02d} - {c:02d}"
    elif op == "sub_add":
        prompt = f"DOUBLE SUB_ADD {a:02d} - {b:02d} + {c:02d}"
    else:
        raise AssertionError(op)
    return {
        "id": f"m17.{op}.{split}.{index:06d}",
        "task_type": f"m17.{op}",
        "prompt": prompt,
        "answer": f"STEP1 {step1}\nSTEP2 {final}\nFINAL {final}",
        "metadata": {
            "primitive": op,
            "split": split,
            "a": a,
            "b": b,
            "c": c,
            "step1": step1,
            "step2": final,
            "answer_value": final,
            "output_length": f"{len(str(final))}_digit",
            "combo_key": _composition_key(item),
            "first_carry_bucket": _carry_bucket(a, b) if op == "add_sub" else None,
            "first_borrow_bucket": (
                "borrow" if op == "sub_add" and a % 10 < b % 10 else "no_borrow"
            ),
        },
    }


def _teacher_forced_record(
    item: tuple[int, int, int, str, int, int],
    split: str,
    index: int,
) -> dict[str, Any]:
    _a, _b, c, op, step1, final = item
    if op == "add_sub":
        prompt = f"SUB {step1} - {c:02d}"
    elif op == "sub_add":
        prompt = f"ADD {step1} + {c:02d}"
    else:
        raise AssertionError(op)
    return {
        "id": f"m17.{op}.teacher_forced.{index:06d}",
        "task_type": f"m17.{op}.teacher_forced",
        "prompt": prompt,
        "answer": f"FINAL {final}",
        "metadata": {
            "primitive": op,
            "split": split,
            "step1": step1,
            "c": c,
            "answer_value": final,
            "combo_key": _composition_key(item),
        },
    }


def _unique_composition_teacher_forced(
    preferred: Sequence[tuple[int, int, int, str, int, int]],
    fallback: Sequence[tuple[int, int, int, str, int, int]],
    *,
    count: int,
    seed: int,
) -> list[tuple[int, int, int, str, int, int]]:
    rng = random.Random(seed)
    fallback_items = list(fallback)
    rng.shuffle(fallback_items)
    selected: list[tuple[int, int, int, str, int, int]] = []
    prompts: set[str] = set()
    keys: set[str] = set()
    for item in [*preferred, *fallback_items]:
        record = _teacher_forced_record(item, "dedup_probe", len(selected))
        prompt = record["prompt"]
        key = _composition_key(item)
        if prompt in prompts or key in keys:
            continue
        selected.append(item)
        prompts.add(prompt)
        keys.add(key)
        if len(selected) >= count:
            return selected
    raise ValueError(f"Could not build {count} unique teacher-forced prompts")


def _compare_sum_candidates(rng: random.Random) -> list[tuple[int, int, int, int]]:
    equal: list[tuple[int, int, int, int]] = []
    left: list[tuple[int, int, int, int]] = []
    right: list[tuple[int, int, int, int]] = []
    seen: set[tuple[int, int, int, int]] = set()
    while min(len(equal), len(left), len(right)) < 3000:
        values = tuple(rng.randint(10, 99) for _ in range(4))
        if values in seen:
            continue
        seen.add(values)
        relation = _compare_relation(values[0] + values[1], values[2] + values[3])
        if relation == "EQUAL":
            equal.append(values)
        elif relation == "GT":
            left.append(values)
        else:
            right.append(values)
    return [*equal, *left, *right]


def _state_template_index(
    a: int,
    b: int,
    *,
    split: str,
    template_count: int,
) -> int:
    base = (a * 31 + b * 17) % template_count
    if split in {"eval_seen", "eval_unseen"}:
        return (base + 1) % template_count
    return base


def _composition_triples(
    rng: random.Random,
    *,
    count: int,
) -> list[tuple[int, int, int, str, int, int]]:
    items: list[tuple[int, int, int, str, int, int]] = []
    seen: set[tuple[int, int, int, str]] = set()
    while len(items) < count:
        a = rng.randint(10, 99)
        b = rng.randint(10, 99)
        c = rng.randint(10, 99)
        op = "add_sub" if len(items) % 2 == 0 else "sub_add"
        if op == "add_sub":
            step1 = a + b
            final = step1 - c
        else:
            if a < b:
                a, b = b, a
            step1 = a - b
            final = step1 + c
        if (a, b, c, op) in seen:
            continue
        if final < 0:
            continue
        seen.add((a, b, c, op))
        items.append((a, b, c, op, step1, final))
    return items


def _balanced_sample[T](
    items: Sequence[T],
    count: int,
    *,
    key_fn: Callable[[T], Any],
    seed: int,
) -> list[T]:
    if count > len(items):
        raise ValueError(f"Cannot sample {count} unique items from {len(items)}")
    rng = random.Random(seed)
    buckets: dict[Any, list[T]] = defaultdict(list)
    for item in items:
        buckets[key_fn(item)].append(item)
    for bucket in buckets.values():
        rng.shuffle(bucket)

    selected: list[T] = []
    bucket_keys = sorted(buckets, key=str)
    cursor = 0
    while len(selected) < count:
        key = bucket_keys[cursor % len(bucket_keys)]
        cursor += 1
        bucket = buckets[key]
        if bucket:
            selected.append(bucket.pop())
        if all(not buckets[key] for key in bucket_keys):
            break
    if len(selected) < count:
        remaining = [item for bucket in buckets.values() for item in bucket]
        rng.shuffle(remaining)
        selected.extend(remaining[: count - len(selected)])
    rng.shuffle(selected)
    return selected[:count]


def _balanced_mix(
    record_groups: Sequence[Sequence[dict[str, Any]]],
    *,
    count_per_bucket: int,
    seed: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    mixed: list[dict[str, Any]] = []
    for group_index, group in enumerate(record_groups):
        records = list(group)
        if not records:
            continue
        sampled = [records[index % len(records)] for index in range(count_per_bucket)]
        rng.shuffle(sampled)
        for index, record in enumerate(sampled):
            cloned = json.loads(json.dumps(record, ensure_ascii=False))
            cloned["id"] = f"{record['id']}.mix{group_index}.{index:06d}"
            mixed.append(cloned)
    rng.shuffle(mixed)
    return mixed


def _analyze_specs(specs: Sequence[RunSpec]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for spec in specs:
        checkpoint = _checkpoint_path(spec)
        if not checkpoint.exists():
            results[spec.name] = {"status": "missing"}
            continue
        split_paths = _eval_paths_for_spec(spec)
        run_results: dict[str, Any] = {
            "status": "complete",
            "run_spec": _spec_payload(spec),
            "checkpoint": str(checkpoint),
            "splits": {},
            "train_loss": _last_train_loss(RUNS_DIR / spec.name / "metrics.jsonl"),
        }
        for split_name, eval_path in split_paths.items():
            output_dir = RUNS_DIR / spec.name / "eval" / split_name
            summary_path = output_dir / "summary.json"
            if summary_path.exists():
                summary = _read_json(summary_path)
            else:
                summary = eval_lm(
                    checkpoint_path=checkpoint,
                    eval_path=eval_path,
                    tokenizer_path=TOKENIZER_PATH,
                    output_dir=output_dir,
                    max_new_tokens=MAX_NEW_TOKENS,
                    numeric_tokenization="digit_safe",
                )["summary"]
            run_results["splits"][split_name] = _enrich_eval_summary(
                eval_path=eval_path,
                predictions_path=Path(summary["predictions_path"]),
                summary=summary,
            )
        results[spec.name] = run_results
    return results


def _eval_paths_for_spec(spec: RunSpec) -> dict[str, Path]:
    if spec.group == "single":
        primitive = spec.name.removeprefix("single_").removesuffix("_3m")
        return {
            "train": DATASET_DIR / primitive / "eval_train.jsonl",
            "seen": DATASET_DIR / primitive / "eval_seen.jsonl",
            "unseen": DATASET_DIR / primitive / "eval_unseen.jsonl",
        }
    if spec.group in {"joint", "control"}:
        primitives = SYMBOLIC_PRIMITIVES if "symbolic" in spec.name else PRIMITIVES
        return {
            f"{primitive}_unseen": DATASET_DIR / primitive / "eval_unseen.jsonl"
            for primitive in primitives
        }
    if spec.group == "staged":
        stage_index = int(spec.name.split("_", 2)[1])
        primitives = STAGES[stage_index - 1][1]
        return {
            f"{primitive}_unseen": DATASET_DIR / primitive / "eval_unseen.jsonl"
            for primitive in primitives
        }
    if spec.group == "composition":
        return {
            "add_sub_seen": DATASET_DIR / "composition" / "eval_add_sub_seen.jsonl",
            "sub_add_seen": DATASET_DIR / "composition" / "eval_sub_add_seen.jsonl",
            "add_sub_unseen": DATASET_DIR / "composition" / "eval_add_sub_unseen.jsonl",
            "sub_add_unseen": DATASET_DIR / "composition" / "eval_sub_add_unseen.jsonl",
            "add_sub_teacher_forced": DATASET_DIR
            / "composition"
            / "eval_add_sub_teacher_forced.jsonl",
            "sub_add_teacher_forced": DATASET_DIR
            / "composition"
            / "eval_sub_add_teacher_forced.jsonl",
        }
    raise AssertionError(spec.group)


def _enrich_eval_summary(
    *,
    eval_path: Path,
    predictions_path: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    records = {record["id"]: record for record in _read_jsonl(eval_path)}
    predictions = _read_jsonl(predictions_path)
    enriched = {
        "overall": summary["overall"],
        "by_task_type": summary.get("by_task_type", {}),
        "buckets": _bucket_metrics(predictions, records),
        "digit_accuracy": _digit_metrics(predictions, records),
        "trace": _trace_metrics(predictions, records),
        "failure_samples": _failure_samples(predictions, records, limit=5),
    }
    return enriched


def _bucket_metrics(
    predictions: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    bucket_values: dict[str, dict[str, list[bool]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for prediction in predictions:
        record = records.get(prediction["id"], {})
        metadata = record.get("metadata", {})
        correct = bool(prediction["final_normalized_exact_match"])
        for key in (
            "carry_bucket",
            "borrow_bucket",
            "output_length",
            "relation",
            "first_carry_bucket",
            "first_borrow_bucket",
        ):
            value = metadata.get(key)
            if value is not None:
                bucket_values[key][str(value)].append(correct)
    return {
        key: {
            value: {
                "count": len(values),
                "final_normalized_exact_match": _rate(values),
            }
            for value, values in sorted(value_map.items())
        }
        for key, value_map in sorted(bucket_values.items())
    }


def _digit_metrics(
    predictions: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    total = 0
    exact_digits = 0
    per_position: dict[str, list[bool]] = defaultdict(list)
    for prediction in predictions:
        expected = normalize_final_answer(
            extract_final_answer(str(prediction["expected"]))
        )
        predicted = normalize_final_answer(
            extract_final_answer(str(prediction["predicted"]))
        )
        if not expected.isdigit():
            continue
        record = records.get(prediction["id"], {})
        expected_meta = str(record.get("metadata", {}).get("answer_value", expected))
        expected = expected_meta if expected_meta.isdigit() else expected
        if not predicted.isdigit():
            predicted = ""
        width = max(len(expected), len(predicted))
        expected_padded = expected.zfill(width)
        predicted_padded = predicted.zfill(width)
        for offset, (expected_digit, predicted_digit) in enumerate(
            zip(reversed(expected_padded), reversed(predicted_padded), strict=True)
        ):
            name = ("units", "tens", "hundreds", "thousands")[min(offset, 3)]
            correct = expected_digit == predicted_digit
            per_position[name].append(correct)
            exact_digits += int(correct)
            total += 1
    return {
        "per_digit_accuracy": exact_digits / total if total else None,
        **{
            f"{name}_accuracy": _rate(values)
            for name, values in sorted(per_position.items())
        },
    }


def _trace_metrics(
    predictions: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    step1: list[bool] = []
    step2: list[bool] = []
    step2_given_step1: list[bool] = []
    for prediction in predictions:
        record = records.get(prediction["id"], {})
        metadata = record.get("metadata", {})
        if "step1" not in metadata or "step2" not in metadata:
            continue
        predicted = str(prediction["predicted"])
        predicted_step1 = _regex_value(STEP1_RE, predicted)
        predicted_step2 = _regex_value(STEP2_RE, predicted)
        is_step1 = predicted_step1 == str(metadata["step1"])
        is_step2 = predicted_step2 == str(metadata["step2"])
        step1.append(is_step1)
        step2.append(is_step2)
        if is_step1:
            step2_given_step1.append(is_step2)
    return {
        "step1_accuracy": _rate(step1),
        "step2_accuracy": _rate(step2),
        "step2_given_correct_step1": _rate(step2_given_step1),
    }


def _failure_samples(
    predictions: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for prediction in predictions:
        if prediction["final_normalized_exact_match"]:
            continue
        record = records.get(prediction["id"], {})
        samples.append(
            {
                "prompt": prediction["prompt"],
                "expected": prediction["expected"],
                "predicted": prediction["predicted"],
                "metadata": record.get("metadata", {}),
            }
        )
        if len(samples) >= limit:
            break
    return samples


def _single_summary(single: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for run_name, payload in single.items():
        if payload.get("status") != "complete":
            continue
        primitive = run_name.removeprefix("single_").removesuffix("_3m")
        splits = payload["splits"]
        result[primitive] = {
            "train": _final_nem(splits.get("train")),
            "seen": _final_nem(splits.get("seen")),
            "unseen": _final_nem(splits.get("unseen")),
            "train_loss": payload.get("train_loss"),
        }
    return result


def _joint_retention(analysis: dict[str, Any]) -> dict[str, Any]:
    single = analysis.get("single_summary", {})
    result: dict[str, Any] = {}
    for run_name, payload in analysis.get("joint", {}).items():
        if payload.get("status") != "complete":
            continue
        rows = {}
        for split_name, split_payload in payload["splits"].items():
            primitive = split_name.removesuffix("_unseen")
            joint_score = _final_nem(split_payload)
            single_score = single.get(primitive, {}).get("unseen")
            rows[primitive] = {
                "single_unseen": single_score,
                "joint_unseen": joint_score,
                "retention_delta": (
                    joint_score - single_score
                    if single_score is not None and joint_score is not None
                    else None
                ),
            }
        result[run_name] = rows
    return result


def _staged_retention_matrix(analysis: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for run_name, payload in analysis.get("staged", {}).items():
        if payload.get("status") != "complete":
            continue
        result[run_name] = {
            split_name.removesuffix("_unseen"): _final_nem(split_payload)
            for split_name, split_payload in payload["splits"].items()
        }
    return result


def _composition_summary(composition: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for run_name, payload in composition.items():
        if payload.get("status") != "complete":
            continue
        result[run_name] = {
            split: {
                "final_nem": _final_nem(split_payload),
                "step1_accuracy": split_payload["trace"].get("step1_accuracy"),
                "step2_accuracy": split_payload["trace"].get("step2_accuracy"),
                "step2_given_correct_step1": split_payload["trace"].get(
                    "step2_given_correct_step1"
                ),
            }
            for split, split_payload in payload["splits"].items()
        }
    return result


def _staged_specs_for_analysis() -> list[RunSpec]:
    return [
        RunSpec(
            name=f"staged_{index}_{stage_name}_3m",
            train_path=DATASET_DIR / f"train_{stage_name}.jsonl",
            eval_path=DATASET_DIR / "add" / "eval_seen.jsonl",
            steps=STAGED_STEPS,
            seed=SEED + 60 + index,
            init_checkpoint=None,
            group="staged",
        )
        for index, (stage_name, _stage_primitives) in enumerate(STAGES, start=1)
    ]


def _checkpoint_path(spec: RunSpec) -> Path:
    return RUNS_DIR / spec.name / "checkpoints" / f"step_{spec.steps:06d}.pt"


def _spec_payload(spec: RunSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "train_path": str(spec.train_path),
        "eval_path": str(spec.eval_path),
        "model_config": spec.model_config,
        "steps": spec.steps,
        "seed": spec.seed,
        "init_checkpoint": str(spec.init_checkpoint) if spec.init_checkpoint else None,
        "group": spec.group,
        "sequence_length": spec.sequence_length,
    }


def _write_jsonl(path: Path, records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")
    return {"path": str(path), "count": len(records)}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_splits(splits: dict[str, Sequence[dict[str, Any]]]) -> dict[str, Any]:
    prompts = {
        name: {record["prompt"] for record in records}
        for name, records in splits.items()
    }
    train_prompts = prompts.get("train", set())
    if not train_prompts:
        train_prompts = prompts.get("train_seen_compositions", set())
    return {
        "prompt_intersections_with_train": {
            name: len(train_prompts.intersection(split_prompts))
            for name, split_prompts in prompts.items()
            if name not in {"train", "train_seen_compositions", "train_holdout_sub_add"}
        },
        "prompt_duplicates": {
            name: _duplicate_count(record["prompt"] for record in records)
            for name, records in splits.items()
        },
        "task_type_counts": {
            name: dict(Counter(record["task_type"] for record in records))
            for name, records in splits.items()
        },
    }


def _distribution(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metadata = [record.get("metadata", {}) for record in records]
    keys = [
        "primitive",
        "carry_bucket",
        "borrow_bucket",
        "output_length",
        "relation",
    ]
    return {
        key: dict(Counter(str(item[key]) for item in metadata if key in item))
        for key in keys
    }


def _duplicate_count(values: Iterable[str]) -> int:
    counts = Counter(values)
    return sum(count - 1 for count in counts.values() if count > 1)


def _case_key(primitive: PrimitiveName, case: tuple[int, ...]) -> str:
    return f"{primitive}:{':'.join(str(value) for value in case)}"


def _composition_key(item: tuple[int, int, int, str, int, int]) -> str:
    a, b, c, op, _step1, _final = item
    return f"{op}:{a}:{b}:{c}"


def _carry_bucket(a: int, b: int) -> str:
    units = a % 10 + b % 10 >= 10
    final = a + b >= 100
    if final:
        return "final_carry"
    if units:
        return "units_carry"
    return "no_carry"


def _compare_relation(a: int, b: int) -> str:
    if a < b:
        return "LT"
    if a > b:
        return "GT"
    return "EQUAL"


def _rate(values: Sequence[bool]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _regex_value(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return match.group("value")


def _final_nem(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    return payload["overall"].get("final_normalized_exact_match")


def _last_train_loss(path: Path) -> float | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        return None
    payload = json.loads(lines[-1])
    return payload.get("train_loss")


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _manifest_intersections_table(manifest: dict[str, Any]) -> str:
    rows = [
        "| split group | split | prompt intersection | duplicates |",
        "|---|---:|---:|---:|",
    ]
    primitive_splits = manifest.get("primitive_splits", {})
    for primitive, payload in sorted(primitive_splits.items()):
        verification = payload.get("verification", {})
        intersections = verification.get("prompt_intersections_with_train", {})
        duplicates = verification.get("prompt_duplicates", {})
        for split, count in sorted(intersections.items()):
            rows.append(
                f"| {primitive} | {split} | {count} | {duplicates.get(split, 'n/a')} |"
            )
    composition = manifest.get("composition_verification", {})
    for split, count in sorted(
        composition.get("prompt_intersections_with_train", {}).items()
    ):
        duplicates = composition.get("prompt_duplicates", {}).get(split, "n/a")
        rows.append(f"| composition | {split} | {count} | {duplicates} |")
    return "\n".join(rows) if len(rows) > 2 else "No manifest available."


def _single_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| task | train | seen | unseen | train loss | digit metrics | carry/borrow buckets |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for primitive, payload in sorted(analysis.get("single_summary", {}).items()):
        run = analysis.get("single", {}).get(f"single_{primitive}_3m", {})
        unseen_payload = run.get("splits", {}).get("unseen", {})
        bucket_text = _bucket_summary(unseen_payload)
        digit_text = _digit_summary(unseen_payload)
        rows.append(
            "| "
            f"{primitive} | {_fmt(payload.get('train'))} | {_fmt(payload.get('seen'))} | "
            f"{_fmt(payload.get('unseen'))} | {_fmt(payload.get('train_loss'))} | "
            f"{digit_text} | {bucket_text} |"
        )
    return "\n".join(rows) if len(rows) > 2 else "No completed single runs yet."


def _joint_table(analysis: dict[str, Any]) -> str:
    retention = analysis.get("joint_retention", {})
    rows = [
        "| run | task | single unseen | joint unseen | retention delta |",
        "|---|---|---:|---:|---:|",
    ]
    for run_name, task_rows in sorted(retention.items()):
        for task, values in sorted(task_rows.items()):
            rows.append(
                f"| {run_name} | {task} | {_fmt(values.get('single_unseen'))} | "
                f"{_fmt(values.get('joint_unseen'))} | "
                f"{_fmt(values.get('retention_delta'))} |"
            )
    return "\n".join(rows) if len(rows) > 2 else "No completed joint runs yet."


def _staged_table(analysis: dict[str, Any]) -> str:
    matrix = analysis.get("staged_retention_matrix", {})
    headers = list(PRIMITIVES)
    rows = [
        "| training stage | " + " | ".join(headers) + " |",
        "|---|" + "|".join("---:" for _ in headers) + "|",
    ]
    for stage, values in sorted(matrix.items()):
        rows.append(
            f"| {stage} | "
            + " | ".join(_fmt(values.get(header)) for header in headers)
            + " |"
        )
    return "\n".join(rows) if len(rows) > 2 else "No completed staged runs yet."


def _composition_table(analysis: dict[str, Any]) -> str:
    summary = analysis.get("composition_summary", {})
    rows = [
        "| run | composition | trained/held-out | final NEM | step1 | step2 | teacher-forced |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for run_name, split_rows in sorted(summary.items()):
        for split, values in sorted(split_rows.items()):
            if "teacher_forced" in split:
                continue
            regime = (
                "held-out"
                if "holdout" in run_name and split.startswith("sub_add")
                else "trained"
            )
            tf_key = split.replace("_unseen", "_teacher_forced").replace(
                "_seen", "_teacher_forced"
            )
            tf_score = split_rows.get(tf_key, {}).get("final_nem")
            rows.append(
                f"| {run_name} | {split} | {regime} | {_fmt(values.get('final_nem'))} | "
                f"{_fmt(values.get('step1_accuracy'))} | {_fmt(values.get('step2_accuracy'))} | "
                f"{_fmt(tf_score)} |"
            )
    return "\n".join(rows) if len(rows) > 2 else "No completed composition runs yet."


def _context_transfer_text(analysis: dict[str, Any]) -> str:
    single = analysis.get("single_summary", {})
    add = single.get("add", {}).get("unseen")
    state_add = single.get("state_add", {}).get("unseen")
    sub = single.get("sub", {}).get("unseen")
    state_sub = single.get("state_sub", {}).get("unseen")
    return (
        f"- ADD symbolic unseen: {_fmt(add)}; STATE_ADD language unseen: {_fmt(state_add)}\n"
        f"- SUB symbolic unseen: {_fmt(sub)}; STATE_SUB language unseen: {_fmt(state_sub)}\n"
        "- Cross-training transfer is not mixed into the primary numeric benchmark; "
        "this section compares separately trained symbolic and language-grounded tasks."
    )


def _control_text(analysis: dict[str, Any]) -> str:
    control = analysis.get("control", {})
    if not control:
        return "Tiny control has not been run yet."
    rows = []
    for run_name, payload in sorted(control.items()):
        if payload.get("status") != "complete":
            rows.append(f"- {run_name}: missing")
            continue
        scores = {
            split: _final_nem(split_payload)
            for split, split_payload in payload.get("splits", {}).items()
        }
        rows.append(f"- {run_name}: {scores}")
    return "\n".join(rows)


def _failure_samples_text(analysis: dict[str, Any]) -> str:
    samples: list[str] = []
    for group in ("single", "joint", "staged", "composition", "control"):
        for run_name, payload in analysis.get(group, {}).items():
            if payload.get("status") != "complete":
                continue
            for split_name, split_payload in payload.get("splits", {}).items():
                failures = split_payload.get("failure_samples", [])
                if not failures:
                    continue
                sample = failures[0]
                samples.append(
                    f"- {run_name}/{split_name}: `{sample['prompt']}` expected "
                    f"`{sample['expected']}` predicted `{sample['predicted']}`"
                )
                if len(samples) >= 12:
                    return "\n".join(samples)
    return "\n".join(samples) if samples else "No failure samples available."


def _interpretation(analysis: dict[str, Any]) -> str:
    single = analysis.get("single_summary", {})
    weak = [
        primitive
        for primitive, values in single.items()
        if values.get("unseen") is not None and values["unseen"] < 0.90
    ]
    if weak:
        return (
            "Outcome E: some individual primitives remain below the minimum usable "
            f"unseen threshold. Weak primitives: {', '.join(weak)}."
        )
    retention = analysis.get("joint_retention", {})
    severe = []
    for run_name, rows in retention.items():
        for task, values in rows.items():
            delta = values.get("retention_delta")
            if delta is not None and delta < -0.10:
                severe.append(f"{run_name}/{task}")
    if severe:
        return (
            "Outcome C: single primitives are high, but joint training shows "
            f"severe degradation in {', '.join(severe)}."
        )
    comp = analysis.get("composition_summary", {})
    heldout_scores = [
        values["final_nem"]
        for run_name, rows in comp.items()
        if "holdout" in run_name
        for split, values in rows.items()
        if split.startswith("sub_add_unseen")
    ]
    trained_scores = [
        values["final_nem"]
        for run_name, rows in comp.items()
        if "seen" in run_name
        for split, values in rows.items()
        if split.endswith("_unseen")
    ]
    if (
        trained_scores
        and min(trained_scores) >= 0.90
        and heldout_scores
        and max(heldout_scores) < 0.60
    ):
        return (
            "Outcome B: primitives and trained compositions are usable, but the "
            "held-out composition remains weak."
        )
    if trained_scores and min(trained_scores) < 0.90:
        return (
            "Outcome D/E boundary: trained multi-step autoregressive compositions "
            "are still weak, so inspect teacher-forced scores before architecture work."
        )
    if heldout_scores and max(heldout_scores) >= 0.60:
        return (
            "Outcome A-like: the held-out composition has non-trivial transfer. "
            "Use the exact table above to decide whether it reaches useful or strong."
        )
    return "Outcome cannot be chosen until all runs are complete."


def _recommendation(analysis: dict[str, Any]) -> str:
    interpretation = _interpretation(analysis)
    if "Outcome B" in interpretation:
        return "M-18 should test explicit rule-following / composition supervision."
    if "Outcome C" in interpretation:
        return "Next milestone should focus on retention: balanced replay, adapters, or plastic-weight variants."
    if "Outcome D" in interpretation:
        return "Next milestone should focus on working memory/state propagation diagnostics before recurrent architecture."
    if "Outcome E" in interpretation:
        return "Fix the weak individual primitives before drawing conclusions about composition."
    if "Outcome A" in interpretation:
        return "Proceed to a broader clean reasoning curriculum with these primitives as stable foundations."
    return "Complete missing runs, then rebuild this report with checks recorded."


def _bucket_summary(payload: dict[str, Any]) -> str:
    buckets = payload.get("buckets", {})
    parts = []
    for key in ("carry_bucket", "borrow_bucket", "output_length", "relation"):
        if key not in buckets:
            continue
        inner = ", ".join(
            f"{name}:{_fmt(values.get('final_normalized_exact_match'))}"
            for name, values in sorted(buckets[key].items())
        )
        parts.append(f"{key}({inner})")
    return "; ".join(parts) if parts else "n/a"


def _digit_summary(payload: dict[str, Any]) -> str:
    metrics = payload.get("digit_accuracy", {})
    if not metrics or metrics.get("per_digit_accuracy") is None:
        return "n/a"
    keys = (
        "per_digit_accuracy",
        "units_accuracy",
        "tens_accuracy",
        "hundreds_accuracy",
    )
    return ", ".join(
        f"{key.removesuffix('_accuracy')}:{_fmt(metrics.get(key))}"
        for key in keys
        if metrics.get(key) is not None
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
