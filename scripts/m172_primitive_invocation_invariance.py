from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ai_brain.eval.runner import eval_lm
from ai_brain.runtime.device import get_device_info
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m172_primitive_invocation"
RUNS_DIR = ROOT / "runs" / "m172_primitive_invocation"
DOC_PATH = ROOT / "docs" / "m172_primitive_invocation_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m172_primitive_invocation_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"
M171_RUNS_DIR = ROOT / "runs" / "m171_primitive_language"

SEED = 317200
EVAL_COUNT = 250
TRAIN_COUNT = 9000
CONTEXT_STEPS = 8000
STRUCTURED_STEPS = 8000
COMPOSITION_STEPS = 10000
LANGUAGE_STEPS = 5000
MAX_NEW_TOKENS = 48

Primitive = Literal["add", "sub"]
Context = Literal[
    "canonical",
    "task_prefix",
    "step_prefix",
    "state_prefix",
    "previous_result",
    "previous_operation",
    "language_parse_prefix",
]

CONTEXTS: tuple[Context, ...] = (
    "canonical",
    "task_prefix",
    "step_prefix",
    "state_prefix",
    "previous_result",
    "previous_operation",
    "language_parse_prefix",
)
NEUTRAL_PREFIXES = ("neutral_0", "neutral_1", "neutral_2", "neutral_4", "neutral_8")
SEMANTIC_PREFIXES = (
    "semantic_result",
    "semantic_step",
    "semantic_previous_operation",
)
TF_PROBES = (
    "b1_canonical",
    "b2_state_canonical",
    "b3_state_step",
    "b4_prev_op_canonical",
)
STRUCTURED_CONTEXTS = (
    "structured_standalone",
    "structured_step",
    "structured_state",
    "structured_previous_result",
    "structured_previous_operation",
)
M172_TASKS = (
    "context",
    "neutral",
    "teacher_forced",
    "context_aug",
    "structured",
    "composition",
    "language",
)

STATE_ADD_TEMPLATES = (
    "У Веры было {a} монет. Ей дали еще {b} монет.",
    "У Олега было {a} книг. Он получил еще {b} книг.",
    "У Маши было {a} жетонов. К ним добавили {b} жетонов.",
    "В коробке лежало {a} деталей. Положили еще {b} деталей.",
    "На счете было {a}. Поступление равно {b}.",
    "У Ильи старт {a}, прирост {b}.",
    "Сначала было {a} карточек, потом добавили {b}.",
    "В наборе {a} предметов. Добавили {b} предметов.",
)
STATE_SUB_TEMPLATES = (
    "У Веры было {a} монет. Она потратила {b} монет.",
    "У Олега было {a} книг. Он отдал {b} книг.",
    "У Маши было {a} жетонов. У нее забрали {b} жетонов.",
    "В коробке лежало {a} деталей. Вынули {b} деталей.",
    "На счете было {a}. Списание равно {b}.",
    "У Ильи старт {a}, уменьшение {b}.",
    "Сначала было {a} карточек, потом убрали {b}.",
    "В наборе {a} предметов. Убрали {b} предметов.",
)

FINAL_RE = re.compile(r"(?im)^\s*FINAL\s+(?P<value>[+-]?\d+)\s*$")
OUT_RE = re.compile(r"(?im)^\s*OUT\s+(?P<value>[+-]?\d+)\s*$")
OP_RE = re.compile(r"(?im)^\s*(?:OP|<OP>)\s*(?P<op>ADD|SUB)\s*$")
A_RE = re.compile(r"(?im)^\s*(?:A|<A>)\s+(?P<a>\d+)\s*$")
B_RE = re.compile(r"(?im)^\s*(?:B|<B>)\s+(?P<b>\d+)\s*$")
STRUCT_OP_RE = re.compile(r"(?im)^\s*<OP_(?P<op>ADD|SUB)>\s*$")


@dataclass(frozen=True)
class Case:
    op: Primitive
    a: int
    b: int

    @property
    def result(self) -> int:
        if self.op == "add":
            return self.a + self.b
        return self.a - self.b

    @property
    def op_token(self) -> str:
        return "ADD" if self.op == "add" else "SUB"

    @property
    def sign(self) -> str:
        return "+" if self.op == "add" else "-"

    @property
    def key(self) -> str:
        return f"{self.op}:{self.a}:{self.b}"


@dataclass(frozen=True)
class RunSpec:
    name: str
    train_path: Path
    eval_path: Path
    steps: int
    group: str
    seed: int
    sequence_length: int = 192
    model_config: str = "arithmetic_3m"


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-controls")
    subparsers.add_parser("run-context-augmentation")
    subparsers.add_parser("run-structured")
    subparsers.add_parser("run-composition")
    subparsers.add_parser("run-language")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-controls":
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-context-augmentation":
        run_specs(context_aug_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-structured":
        run_specs(structured_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-composition":
        run_composition_if_gated()
        analyze_composition_merge()
        build_report(checks_passed=False)
    elif args.command == "run-language":
        run_specs(language_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        analyze_all()
        run_specs(context_aug_specs())
        run_specs(structured_specs())
        analyze_all()
        run_composition_if_gated()
        analyze_composition_merge()
        run_specs(language_specs())
        analyze_all()
        build_report(checks_passed=False)
    else:
        raise AssertionError(args.command)
    return 0


def prepare_datasets() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    add_train, add_seen, add_unseen = _split_cases("add", rng)
    sub_train, sub_seen, sub_unseen = _split_cases("sub", rng)
    all_cases = {
        "add": {"train": add_train, "seen": add_seen, "unseen": add_unseen},
        "sub": {"train": sub_train, "seen": sub_seen, "unseen": sub_unseen},
    }

    _write_context_controls(all_cases)
    _write_context_aug(all_cases)
    _write_structured(all_cases)
    _write_composition(rng)
    _write_language_bridge(rng)
    manifest = {
        "kind": "m172_primitive_invocation_invariance",
        "seed": SEED,
        "eval_count": EVAL_COUNT,
        "train_count": TRAIN_COUNT,
        "contexts": list(CONTEXTS),
        "structured_contexts": list(STRUCTURED_CONTEXTS),
        "m171_checkpoints": {
            "add": str(_m171_checkpoint("add")) if _m171_checkpoint("add") else None,
            "sub": str(_m171_checkpoint("sub")) if _m171_checkpoint("sub") else None,
        },
        "prompt_intersections": _prompt_intersections(include_train_probes=True),
        "heldout_prompt_intersections": _prompt_intersections(
            include_train_probes=False
        ),
        "task_type_counts": _task_type_counts(DATASET_DIR),
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def context_aug_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name=f"context_augmented_{op}",
            train_path=DATASET_DIR / "context_aug" / op / "train_multi_wrapper.jsonl",
            eval_path=DATASET_DIR / "context_aug" / op / "eval_seen_all.jsonl",
            steps=CONTEXT_STEPS,
            group="context_aug",
            seed=SEED + (10 if op == "add" else 20),
        )
        for op in ("add", "sub")
    ]


def structured_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name=f"structured_op_{op}",
            train_path=DATASET_DIR / "structured" / op / "train_structured.jsonl",
            eval_path=DATASET_DIR / "structured" / op / "eval_seen_all.jsonl",
            steps=STRUCTURED_STEPS,
            group="structured",
            seed=SEED + (30 if op == "add" else 40),
        )
        for op in ("add", "sub")
    ]


def composition_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name="structured_add_sub",
            train_path=DATASET_DIR / "composition" / "train_add_sub.jsonl",
            eval_path=DATASET_DIR / "composition" / "eval_seen.jsonl",
            steps=COMPOSITION_STEPS,
            group="composition",
            seed=SEED + 50,
            sequence_length=256,
        )
    ]


def language_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name="language_to_structured_parse",
            train_path=DATASET_DIR / "language" / "train_parse.jsonl",
            eval_path=DATASET_DIR / "language" / "eval_seen.jsonl",
            steps=LANGUAGE_STEPS,
            group="language",
            seed=SEED + 60,
            sequence_length=192,
        )
    ]


def run_composition_if_gated() -> None:
    analysis = (
        _read_json(RUNS_DIR / "analysis.json")
        if (RUNS_DIR / "analysis.json").exists()
        else {}
    )
    gate = _composition_gate(analysis)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "composition_gate.json").write_text(
        json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if not gate["should_run"]:
        print(f"skip composition: {gate['reason']}")
        return
    run_specs(composition_specs())


def run_specs(specs: Sequence[RunSpec]) -> None:
    for spec in specs:
        checkpoint = _checkpoint_path(spec, spec.steps)
        if checkpoint.exists():
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
            learning_rate=3e-4,
            grad_clip_norm=1.0,
            numeric_tokenization="digit_safe",
            seed=spec.seed,
            eval_every=1000,
            eval_batches=20,
            save_every=5000,
        )
        started = time.time()
        result = train_lm(config)
        (output_dir / "run_result.json").write_text(
            json.dumps(
                {
                    "run_spec": _spec_payload(spec),
                    "elapsed_seconds": time.time() - started,
                    "train_result": result,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def analyze_all() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    analysis: dict[str, Any] = {
        "controls": _analyze_controls(),
        "context_aug": _analyze_specs(context_aug_specs()),
        "structured": _analyze_specs(structured_specs()),
        "composition": _analyze_specs(composition_specs()),
        "language": _analyze_specs(language_specs()),
    }
    analysis["context_invariance"] = _context_invariance_summary(analysis["controls"])
    analysis["neutral_prefix"] = _neutral_prefix_summary(analysis["controls"])
    analysis["teacher_forced_factorization"] = _teacher_forced_summary(
        analysis["controls"]
    )
    analysis["context_aug_summary"] = _simple_run_summary(analysis["context_aug"])
    analysis["structured_summary"] = _simple_run_summary(analysis["structured"])
    analysis["composition_summary"] = _composition_summary(analysis["composition"])
    analysis["language_summary"] = _language_summary(analysis)
    analysis["composition_gate"] = _composition_gate(analysis)
    _write_analysis(analysis)


def analyze_composition_merge() -> None:
    analysis_path = RUNS_DIR / "analysis.json"
    analysis = _read_json(analysis_path) if analysis_path.exists() else {}
    analysis["composition"] = _analyze_specs(composition_specs())
    analysis["composition_summary"] = _composition_summary(analysis["composition"])
    analysis["composition_gate"] = _composition_gate(analysis)
    _write_analysis(analysis)


def build_report(*, checks_passed: bool) -> None:
    analysis = (
        _read_json(RUNS_DIR / "analysis.json")
        if (RUNS_DIR / "analysis.json").exists()
        else {}
    )
    manifest = (
        _read_json(DATASET_DIR / "manifest.json")
        if (DATASET_DIR / "manifest.json").exists()
        else {}
    )
    device = get_device_info(prefer_cuda=True)
    lines = [
        "# M-17.2 Primitive Invocation and Context Invariance",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        f"- device: `{device.device}` ({device.name})",
        "",
        "## Dataset Verification",
        "",
        _dataset_notes(manifest),
        "",
        "## Context Invariance Matrix",
        "",
        _context_matrix_table(analysis),
        "",
        "## Neutral Prefix vs Semantic Prefix",
        "",
        _neutral_table(analysis),
        "",
        "## Teacher-Forced Factorization",
        "",
        _teacher_forced_table(analysis),
        "",
        "## Context Augmentation",
        "",
        _context_aug_table(analysis),
        "",
        "## Structured Operation Representation",
        "",
        _structured_table(analysis),
        "",
        "## Composition Retest",
        "",
        _composition_table(analysis),
        "",
        "## Optional Held-Out Composition",
        "",
        _heldout_composition_note(analysis),
        "",
        "## Language -> Structured Bridge",
        "",
        _language_table(analysis),
        "",
        "## Decision",
        "",
        _decision(analysis),
        "",
        "## Next Milestone",
        "",
        _next_milestone(analysis),
        "",
    ]
    text = "\n".join(lines)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def _split_cases(
    op: Primitive, rng: random.Random
) -> tuple[list[Case], list[Case], list[Case]]:
    if op == "add":
        candidates = [Case(op, a, b) for a in range(10, 100) for b in range(10, 100)]
    else:
        candidates = [Case(op, a, b) for a in range(10, 100) for b in range(1, a + 1)]
    rng.shuffle(candidates)
    train_unique_count = max(EVAL_COUNT, int(len(candidates) * 0.72))
    train_unique_count = min(train_unique_count, len(candidates) - (2 * EVAL_COUNT))
    seen_start = train_unique_count
    unseen_start = seen_start + EVAL_COUNT
    train_base = candidates[:train_unique_count]
    seen_cases = candidates[seen_start:unseen_start]
    unseen_pool = candidates[unseen_start:]
    train_cases = _repeat_cases(train_base, TRAIN_COUNT, rng)
    unseen_cases = _balanced_sample(unseen_pool, EVAL_COUNT, rng)
    return train_cases, seen_cases, unseen_cases


def _repeat_cases(cases: Sequence[Case], count: int, rng: random.Random) -> list[Case]:
    result: list[Case] = []
    shuffled = list(cases)
    while len(result) < count:
        rng.shuffle(shuffled)
        result.extend(shuffled[: count - len(result)])
    return result


def _balanced_sample(
    cases: Sequence[Case], count: int, rng: random.Random
) -> list[Case]:
    buckets: dict[str, list[Case]] = defaultdict(list)
    for case in cases:
        buckets[_case_bucket(case)].append(case)
    result: list[Case] = []
    bucket_names = sorted(buckets)
    offsets = {
        name: rng.randrange(max(1, len(values))) for name, values in buckets.items()
    }
    while len(result) < count:
        for name in bucket_names:
            values = buckets[name]
            if not values:
                continue
            index = (offsets[name] + len(result)) % len(values)
            result.append(values[index])
            if len(result) >= count:
                break
    return result


def _case_bucket(case: Case) -> str:
    if case.op == "add":
        carry = "final_carry" if case.result >= 100 else "no_final_carry"
        units = "units_carry" if case.a % 10 + case.b % 10 >= 10 else "no_units_carry"
        return f"{carry}:{units}"
    borrow = "borrow" if case.a % 10 < case.b % 10 else "no_borrow"
    return borrow


def _write_context_controls(all_cases: dict[str, dict[str, list[Case]]]) -> None:
    for op in ("add", "sub"):
        base = DATASET_DIR / "controls" / op
        base.mkdir(parents=True, exist_ok=True)
        for split in ("train", "seen", "unseen"):
            cases = (
                all_cases[op]["train"][:EVAL_COUNT]
                if split == "train"
                else all_cases[op][split]
            )
            for context in CONTEXTS:
                records = [
                    _record(
                        case,
                        prompt=_plain_prompt(case, context),
                        task_type=f"m172.{op}.{context}",
                        split=split,
                        index=index,
                        extra={"context": context, "phase": "context_invariance"},
                    )
                    for index, case in enumerate(cases)
                ]
                _write_jsonl(base / f"eval_{split}_{context}.jsonl", records)
        for split in ("seen", "unseen"):
            cases = all_cases[op][split]
            for prefix_name in NEUTRAL_PREFIXES:
                records = [
                    _record(
                        case,
                        prompt=_neutral_prompt(case, prefix_name),
                        task_type=f"m172.{op}.{prefix_name}",
                        split=split,
                        index=index,
                        extra={"prefix": prefix_name, "phase": "neutral_prefix"},
                    )
                    for index, case in enumerate(cases)
                ]
                _write_jsonl(base / f"eval_{split}_{prefix_name}.jsonl", records)
            for prefix_name in SEMANTIC_PREFIXES:
                records = [
                    _record(
                        case,
                        prompt=_semantic_prefix_prompt(case, prefix_name),
                        task_type=f"m172.{op}.{prefix_name}",
                        split=split,
                        index=index,
                        extra={"prefix": prefix_name, "phase": "semantic_prefix"},
                    )
                    for index, case in enumerate(cases)
                ]
                _write_jsonl(base / f"eval_{split}_{prefix_name}.jsonl", records)
        if op == "sub":
            for split in ("seen", "unseen"):
                cases = all_cases[op][split]
                for probe in TF_PROBES:
                    records = [
                        _record(
                            case,
                            prompt=_tf_prompt(case, probe),
                            task_type=f"m172.sub.{probe}",
                            split=split,
                            index=index,
                            extra={
                                "probe": probe,
                                "phase": "teacher_forced_factorization",
                            },
                        )
                        for index, case in enumerate(cases)
                    ]
                    _write_jsonl(base / f"eval_{split}_{probe}.jsonl", records)


def _write_context_aug(all_cases: dict[str, dict[str, list[Case]]]) -> None:
    train_contexts: tuple[Context, ...] = (
        "canonical",
        "task_prefix",
        "step_prefix",
        "state_prefix",
        "previous_result",
    )
    for op in ("add", "sub"):
        base = DATASET_DIR / "context_aug" / op
        base.mkdir(parents=True, exist_ok=True)
        train_records = []
        for index, case in enumerate(all_cases[op]["train"]):
            context = train_contexts[index % len(train_contexts)]
            train_records.append(
                _record(
                    case,
                    prompt=_plain_prompt(case, context),
                    task_type=f"m172.{op}.context_aug_train",
                    split="train",
                    index=index,
                    extra={"context": context, "phase": "context_aug"},
                )
            )
        _write_jsonl(base / "train_multi_wrapper.jsonl", train_records)
        for split in ("train", "seen", "unseen"):
            records_all = []
            for context in CONTEXTS:
                cases = (
                    all_cases[op]["train"][:EVAL_COUNT]
                    if split == "train"
                    else all_cases[op][split]
                )
                records = [
                    _record(
                        case,
                        prompt=_plain_prompt(case, context),
                        task_type=f"m172.{op}.context_aug_{context}",
                        split=split,
                        index=index,
                        extra={
                            "context": context,
                            "phase": "context_aug",
                            "held_out_wrapper": context == "previous_operation",
                        },
                    )
                    for index, case in enumerate(cases)
                ]
                _write_jsonl(base / f"eval_{split}_{context}.jsonl", records)
                records_all.extend(records)
            _write_jsonl(base / f"eval_{split}_all.jsonl", records_all)


def _write_structured(all_cases: dict[str, dict[str, list[Case]]]) -> None:
    train_contexts = (
        "structured_standalone",
        "structured_step",
        "structured_state",
        "structured_previous_result",
    )
    for op in ("add", "sub"):
        base = DATASET_DIR / "structured" / op
        base.mkdir(parents=True, exist_ok=True)
        train_records = []
        for index, case in enumerate(all_cases[op]["train"]):
            context = train_contexts[index % len(train_contexts)]
            train_records.append(
                _record(
                    case,
                    prompt=_structured_prompt(case, context),
                    task_type=f"m172.{op}.structured_train",
                    split="train",
                    index=index,
                    extra={"context": context, "phase": "structured"},
                )
            )
        _write_jsonl(base / "train_structured.jsonl", train_records)
        for split in ("train", "seen", "unseen"):
            records_all = []
            for context in STRUCTURED_CONTEXTS:
                cases = (
                    all_cases[op]["train"][:EVAL_COUNT]
                    if split == "train"
                    else all_cases[op][split]
                )
                records = [
                    _record(
                        case,
                        prompt=_structured_prompt(case, context),
                        task_type=f"m172.{op}.{context}",
                        split=split,
                        index=index,
                        extra={
                            "context": context,
                            "phase": "structured",
                            "held_out_wrapper": context
                            == "structured_previous_operation",
                        },
                    )
                    for index, case in enumerate(cases)
                ]
                _write_jsonl(base / f"eval_{split}_{context}.jsonl", records)
                records_all.extend(records)
            _write_jsonl(base / f"eval_{split}_all.jsonl", records_all)


def _write_composition(rng: random.Random) -> None:
    base = DATASET_DIR / "composition"
    base.mkdir(parents=True, exist_ok=True)
    candidates = [
        (a, b, c)
        for a in range(10, 100)
        for b in range(10, 100)
        for c in range(1, a + b + 1)
    ]
    rng.shuffle(candidates)
    train_base = candidates[:6000]
    seen = candidates[6000 : 6000 + EVAL_COUNT]
    unseen = candidates[6000 + EVAL_COUNT : 6000 + (2 * EVAL_COUNT)]
    train_probe = train_base[:EVAL_COUNT]
    train_cases = []
    while len(train_cases) < TRAIN_COUNT:
        rng.shuffle(train_base)
        train_cases.extend(train_base[: TRAIN_COUNT - len(train_cases)])
    _write_jsonl(
        base / "train_add_sub.jsonl",
        [
            _composition_record(case, "train", index)
            for index, case in enumerate(train_cases)
        ],
    )
    _write_jsonl(
        base / "eval_train.jsonl",
        [
            _composition_record(case, "train", index)
            for index, case in enumerate(train_probe)
        ],
    )
    _write_jsonl(
        base / "eval_seen.jsonl",
        [_composition_record(case, "seen", index) for index, case in enumerate(seen)],
    )
    _write_jsonl(
        base / "eval_unseen.jsonl",
        [
            _composition_record(case, "unseen", index)
            for index, case in enumerate(unseen)
        ],
    )
    for probe in ("tf1_step1_result", "tf2_full_step1_state", "tf3_step2_only"):
        _write_jsonl(
            base / f"eval_{probe}.jsonl",
            [
                _composition_tf_record(case, probe, index)
                for index, case in enumerate(unseen)
            ],
        )
    sub_add_unseen = [
        (a, b, c)
        for a in range(20, 150)
        for b in range(1, a + 1)
        for c in range(10, 100)
    ]
    rng.shuffle(sub_add_unseen)
    _write_jsonl(
        base / "eval_sub_add_heldout.jsonl",
        [
            _sub_add_record(case, "heldout", index)
            for index, case in enumerate(sub_add_unseen[:EVAL_COUNT])
        ],
    )


def _write_language_bridge(rng: random.Random) -> None:
    base = DATASET_DIR / "language"
    base.mkdir(parents=True, exist_ok=True)
    train_records = []
    eval_seen = []
    eval_heldout = []
    train_prompts = set()
    for index in range(4000):
        op: Primitive = "add" if index % 2 == 0 else "sub"
        a = rng.randint(10, 99)
        b = rng.randint(10, 99) if op == "add" else rng.randint(1, a)
        template = (STATE_ADD_TEMPLATES if op == "add" else STATE_SUB_TEMPLATES)[
            index % 5
        ]
        record = _language_parse_record(Case(op, a, b), template, "train", index)
        train_prompts.add(record["prompt"])
        train_records.append(record)
    for index in range(EVAL_COUNT):
        seen_record, heldout_record = _language_eval_pair(index, rng, train_prompts)
        eval_seen.append(seen_record)
        eval_heldout.append(heldout_record)
    _write_language_bridge_outputs(base, train_records, eval_seen, eval_heldout)


def _language_eval_pair(
    index: int, rng: random.Random, train_prompts: set[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    while True:
        op: Primitive = "add" if index % 2 == 0 else "sub"
        a = rng.randint(10, 99)
        b = rng.randint(10, 99) if op == "add" else rng.randint(1, a)
        case = Case(op, a, b)
        seen_record = _language_parse_record(
            case,
            (STATE_ADD_TEMPLATES if op == "add" else STATE_SUB_TEMPLATES)[index % 5],
            "seen",
            index,
        )
        heldout_record = _language_parse_record(
            case,
            (STATE_ADD_TEMPLATES if op == "add" else STATE_SUB_TEMPLATES)[
                5 + index % 3
            ],
            "heldout",
            index,
        )
        if (
            seen_record["prompt"] not in train_prompts
            and heldout_record["prompt"] not in train_prompts
        ):
            return seen_record, heldout_record


def _write_language_bridge_outputs(
    base: Path,
    train_records: Sequence[dict[str, Any]],
    eval_seen: Sequence[dict[str, Any]],
    eval_heldout: Sequence[dict[str, Any]],
) -> None:
    _write_jsonl(base / "train_parse.jsonl", train_records)
    _write_jsonl(base / "eval_seen.jsonl", eval_seen)
    _write_jsonl(base / "eval_heldout.jsonl", eval_heldout)
    _write_jsonl(
        base / "eval_structured_execution.jsonl",
        [
            _structured_execution_from_parse(record, index)
            for index, record in enumerate(eval_heldout)
        ],
    )


def _plain_prompt(case: Case, context: Context) -> str:
    expr = f"{case.a:02d} {case.sign} {case.b:02d}"
    if context == "canonical":
        return f"{case.op_token} {expr}"
    if context == "task_prefix":
        return f"TASK {case.op_token}\n{expr}"
    if context == "step_prefix":
        return f"STEP2 {case.op_token} {expr}"
    if context == "state_prefix":
        return f"STATE {case.a}\nOP {case.op_token}\nARG {case.b}"
    if context == "previous_result":
        return f"STEP1 RESULT {case.a}\n{case.op_token} {expr}"
    if context == "previous_operation":
        prev = _previous_operation_for(case.a)
        return f"{prev[0]} + {prev[1]} = {case.a}\nSTEP2 {case.op_token} {expr}"
    if context == "language_parse_prefix":
        return f"OP {case.op_token}\nA {case.a}\nB {case.b}\nRUN"
    raise AssertionError(context)


def _neutral_prompt(case: Case, prefix_name: str) -> str:
    count = int(prefix_name.removeprefix("neutral_"))
    prefix = " ".join(["X"] * count)
    base = _plain_prompt(case, "canonical")
    return base if not prefix else f"{prefix}\n{base}"


def _semantic_prefix_prompt(case: Case, prefix_name: str) -> str:
    if prefix_name == "semantic_result":
        return f"RESULT {case.a}\n{_plain_prompt(case, 'canonical')}"
    if prefix_name == "semantic_step":
        return _plain_prompt(case, "previous_result").replace("\n", "\nSTEP2 ")
    if prefix_name == "semantic_previous_operation":
        return _plain_prompt(case, "previous_operation")
    raise AssertionError(prefix_name)


def _tf_prompt(case: Case, probe: str) -> str:
    if case.op != "sub":
        raise ValueError("teacher-forced probes are defined for SUB")
    canonical = _plain_prompt(case, "canonical")
    prev = _previous_operation_for(case.a)
    if probe == "b1_canonical":
        return canonical
    if probe == "b2_state_canonical":
        return f"STEP1 RESULT {case.a}\n{canonical}"
    if probe == "b3_state_step":
        return f"STEP1 RESULT {case.a}\nSTEP2 SUB {case.a:02d} - {case.b:02d}"
    if probe == "b4_prev_op_canonical":
        return f"STEP1 ADD {prev[0]} {prev[1]}\nSTEP1 RESULT {case.a}\n{canonical}"
    raise AssertionError(probe)


def _structured_prompt(case: Case, context: str) -> str:
    body = f"<OP_{case.op_token}>\n<A> {case.a}\n<B> {case.b}\n<OUT>"
    if context == "structured_standalone":
        return body
    if context == "structured_step":
        return f"<STEP>\n{body}"
    if context == "structured_state":
        return f"<STATE>\n<A> {case.a}\n{body}"
    if context == "structured_previous_result":
        return f"<STEP1>\n<RESULT> {case.a}\n<STEP2>\n{body}"
    if context == "structured_previous_operation":
        prev = _previous_operation_for(case.a)
        return f"<STEP1>\n<OP_ADD>\n<A> {prev[0]}\n<B> {prev[1]}\n<OUT> {case.a}\n<STEP2>\n{body}"
    raise AssertionError(context)


def _previous_operation_for(value: int) -> tuple[int, int]:
    left = max(10, min(value - 10, value // 2))
    right = value - left
    if right < 0:
        return 0, value
    return left, right


def _record(
    case: Case,
    *,
    prompt: str,
    task_type: str,
    split: str,
    index: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "op": case.op_token,
        "primitive": case.op,
        "a": case.a,
        "b": case.b,
        "answer_value": case.result,
        "case_key": case.key,
        "split": split,
        "bucket": _case_bucket(case),
    }
    metadata.update(extra or {})
    return {
        "id": f"{task_type}.{split}.{index:06d}",
        "task_type": task_type,
        "prompt": prompt,
        "answer": f"FINAL {case.result}",
        "metadata": metadata,
    }


def _composition_record(
    case: tuple[int, int, int], split: str, index: int
) -> dict[str, Any]:
    a, b, c = case
    step1 = a + b
    final = step1 - c
    answer = (
        f"<STEP>\n<OP_ADD>\n<A> {a}\n<B> {b}\nOUT {step1}\n\n"
        f"<STEP>\n<OP_SUB>\n<A> {step1}\n<B> {c}\nOUT {final}\nFINAL {final}"
    )
    return {
        "id": f"m172.add_sub.{split}.{index:06d}",
        "task_type": "m172.add_sub",
        "prompt": f"<COMPOSE_ADD_SUB>\n<A> {a}\n<B> {b}\n<C> {c}",
        "answer": answer,
        "metadata": {
            "a": a,
            "b": b,
            "c": c,
            "step1": step1,
            "step2": final,
            "answer_value": final,
            "split": split,
        },
    }


def _composition_tf_record(
    case: tuple[int, int, int], probe: str, index: int
) -> dict[str, Any]:
    a, b, c = case
    step1 = a + b
    final = step1 - c
    if probe == "tf1_step1_result":
        prompt = f"<COMPOSE_ADD_SUB>\n<STEP1_RESULT> {step1}\n<C> {c}"
    elif probe == "tf2_full_step1_state":
        prompt = f"<STEP>\n<OP_ADD>\n<A> {a}\n<B> {b}\nOUT {step1}\n<STEP2>\n<C> {c}"
    elif probe == "tf3_step2_only":
        prompt = f"<OP_SUB>\n<A> {step1}\n<B> {c}\n<OUT>"
    else:
        raise AssertionError(probe)
    return {
        "id": f"m172.add_sub.{probe}.{index:06d}",
        "task_type": f"m172.add_sub.{probe}",
        "prompt": prompt,
        "answer": f"OUT {final}\nFINAL {final}",
        "metadata": {
            "a": a,
            "b": b,
            "c": c,
            "step1": step1,
            "step2": final,
            "answer_value": final,
            "probe": probe,
            "split": probe,
        },
    }


def _sub_add_record(
    case: tuple[int, int, int], split: str, index: int
) -> dict[str, Any]:
    a, b, c = case
    step1 = a - b
    final = step1 + c
    return {
        "id": f"m172.sub_add.{split}.{index:06d}",
        "task_type": "m172.sub_add_heldout",
        "prompt": f"<COMPOSE_SUB_ADD>\n<A> {a}\n<B> {b}\n<C> {c}",
        "answer": f"<STEP>\n<OP_SUB>\n<A> {a}\n<B> {b}\nOUT {step1}\n\n<STEP>\n<OP_ADD>\n<A> {step1}\n<B> {c}\nOUT {final}\nFINAL {final}",
        "metadata": {
            "a": a,
            "b": b,
            "c": c,
            "step1": step1,
            "step2": final,
            "answer_value": final,
            "split": split,
        },
    }


def _language_parse_record(
    case: Case, template: str, split: str, index: int
) -> dict[str, Any]:
    return {
        "id": f"m172.language_parse.{split}.{index:06d}",
        "task_type": "m172.language_parse",
        "prompt": template.format(a=case.a, b=case.b),
        "answer": f"<OP_{case.op_token}>\n<A> {case.a}\n<B> {case.b}",
        "metadata": {
            "op": case.op_token,
            "a": case.a,
            "b": case.b,
            "split": split,
            "answer_value": case.result,
        },
    }


def _structured_execution_from_parse(
    record: dict[str, Any], index: int
) -> dict[str, Any]:
    metadata = record["metadata"]
    case = Case(
        "add" if metadata["op"] == "ADD" else "sub",
        int(metadata["a"]),
        int(metadata["b"]),
    )
    return _record(
        case,
        prompt=_structured_prompt(case, "structured_standalone"),
        task_type="m172.language_structured_execution",
        split="heldout",
        index=index,
        extra={"phase": "language_bridge", "context": "structured_standalone"},
    )


def _analyze_controls() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for op in ("add", "sub"):
        checkpoint = _m171_checkpoint(op)
        op_payload: dict[str, Any] = {
            "checkpoint": str(checkpoint) if checkpoint else None,
            "splits": {},
        }
        if checkpoint is None:
            op_payload["status"] = "missing_m171_checkpoint"
            results[op] = op_payload
            continue
        for path in sorted((DATASET_DIR / "controls" / op).glob("eval_*.jsonl")):
            split_name = path.stem.removeprefix("eval_")
            op_payload["splits"][split_name] = _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=path,
                output_dir=RUNS_DIR / "controls" / op / split_name,
            )
        op_payload["status"] = "complete"
        results[op] = op_payload
    return results


def _analyze_specs(specs: Sequence[RunSpec]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for spec in specs:
        checkpoints = _available_checkpoints(spec)
        if not checkpoints:
            results[spec.name] = {"status": "missing", "run_spec": _spec_payload(spec)}
            continue
        run_payload: dict[str, Any] = {
            "status": "complete",
            "run_spec": _spec_payload(spec),
            "checkpoints": {},
            "train_loss": _last_train_loss(RUNS_DIR / spec.name / "metrics.jsonl"),
        }
        for step, checkpoint in checkpoints.items():
            step_payload: dict[str, Any] = {"checkpoint": str(checkpoint), "splits": {}}
            for split_name, eval_path in _eval_paths_for_spec(spec).items():
                step_payload["splits"][split_name] = _eval_checkpoint(
                    checkpoint=checkpoint,
                    eval_path=eval_path,
                    output_dir=RUNS_DIR
                    / spec.name
                    / "eval"
                    / f"step_{step:06d}"
                    / split_name,
                )
            run_payload["checkpoints"][str(step)] = step_payload
        results[spec.name] = run_payload
    return results


def _eval_checkpoint(
    *, checkpoint: Path, eval_path: Path, output_dir: Path
) -> dict[str, Any]:
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
    return _enrich_eval_summary(
        eval_path=eval_path,
        predictions_path=Path(summary["predictions_path"]),
        summary=summary,
    )


def _enrich_eval_summary(
    *, eval_path: Path, predictions_path: Path, summary: dict[str, Any]
) -> dict[str, Any]:
    overall = summary.get("overall", summary)
    expected_by_id = {record["id"]: record for record in _read_jsonl(eval_path)}
    predictions = _read_jsonl(predictions_path)
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: defaultdict(lambda: {"count": 0, "final_correct": 0})
    )
    trace = {
        "step1_accuracy": 0.0,
        "step2_accuracy": 0.0,
        "final_accuracy": 0.0,
        "op_accuracy": 0.0,
        "arg_a_accuracy": 0.0,
        "arg_b_accuracy": 0.0,
    }
    counts = Counter()
    corrects = Counter()
    for pred in predictions:
        record = expected_by_id[pred["id"]]
        metadata = record.get("metadata", {})
        final_correct = bool(pred.get("final_normalized_exact_match"))
        for key in ("context", "prefix", "probe", "op", "bucket", "split"):
            if key in metadata:
                item = buckets[key][str(metadata[key])]
                item["count"] += 1
                item["final_correct"] += int(final_correct)
        _update_trace_counts(corrects, counts, metadata, str(pred.get("predicted", "")))
    for name in trace:
        trace[name] = corrects[name] / counts[name] if counts[name] else None
    result = {
        "summary": summary,
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "normalized_exact_match": float(overall.get("normalized_exact_match", 0.0)),
        "empty_prediction_rate": float(overall.get("empty_prediction_rate", 0.0)),
        "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
        "avg_tokens_generated": float(summary.get("avg_tokens_generated", 0.0)),
        "buckets": {
            key: {
                value: {
                    "count": payload["count"],
                    "final_nem": payload["final_correct"] / payload["count"]
                    if payload["count"]
                    else 0.0,
                }
                for value, payload in values.items()
            }
            for key, values in buckets.items()
        },
        "trace_metrics": trace,
    }
    return result


def _update_trace_counts(
    corrects: Counter[str],
    counts: Counter[str],
    metadata: dict[str, Any],
    predicted: str,
) -> None:
    expected_final = str(metadata.get("answer_value", ""))
    final = _extract_number_after(FINAL_RE, predicted)
    counts["final_accuracy"] += 1
    corrects["final_accuracy"] += int(final == expected_final)
    if "step1" in metadata:
        outs = [match.group("value") for match in OUT_RE.finditer(predicted)]
        if outs:
            counts["step1_accuracy"] += 1
            corrects["step1_accuracy"] += int(outs[0] == str(metadata["step1"]))
        if len(outs) > 1:
            counts["step2_accuracy"] += 1
            corrects["step2_accuracy"] += int(outs[1] == str(metadata["step2"]))
    op = _extract_op(predicted)
    if "op" in metadata:
        counts["op_accuracy"] += 1
        corrects["op_accuracy"] += int(op == metadata["op"])
    a = _extract_number_after(A_RE, predicted)
    b = _extract_number_after(B_RE, predicted)
    if "a" in metadata:
        counts["arg_a_accuracy"] += 1
        corrects["arg_a_accuracy"] += int(a == str(metadata["a"]))
    if "b" in metadata:
        counts["arg_b_accuracy"] += 1
        corrects["arg_b_accuracy"] += int(b == str(metadata["b"]))


def _extract_number_after(pattern: re.Pattern[str], text: str) -> str | None:
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    group = "value" if "value" in pattern.groupindex else next(iter(pattern.groupindex))
    return matches[-1].group(group)


def _extract_op(text: str) -> str | None:
    matches = list(STRUCT_OP_RE.finditer(text))
    if matches:
        return matches[-1].group("op")
    matches = list(OP_RE.finditer(text))
    if matches:
        return matches[-1].group("op")
    return None


def _context_invariance_summary(controls: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for op, payload in controls.items():
        splits = payload.get("splits", {})
        result[op] = {}
        for context in CONTEXTS:
            result[op][context] = {
                split: _final_nem(splits.get(f"{split}_{context}", {}))
                for split in ("train", "seen", "unseen")
            }
    return result


def _neutral_prefix_summary(controls: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for op, payload in controls.items():
        splits = payload.get("splits", {})
        result[op] = {
            name: _final_nem(splits.get(f"unseen_{name}", {}))
            for name in (*NEUTRAL_PREFIXES, *SEMANTIC_PREFIXES)
        }
    return result


def _teacher_forced_summary(controls: dict[str, Any]) -> dict[str, Any]:
    sub = controls.get("sub", {}).get("splits", {})
    return {probe: _final_nem(sub.get(f"unseen_{probe}", {})) for probe in TF_PROBES}


def _simple_run_summary(runs: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for run_name, payload in runs.items():
        if payload.get("status") != "complete":
            continue
        final_step = str(payload["run_spec"]["steps"])
        step_payload = payload["checkpoints"].get(final_step)
        if not step_payload:
            continue
        result[run_name] = {
            split: {
                "final_nem": _final_nem(split_payload),
                "buckets": split_payload.get("buckets", {}),
                "trace": split_payload.get("trace_metrics", {}),
            }
            for split, split_payload in step_payload["splits"].items()
        }
    return result


def _composition_summary(runs: dict[str, Any]) -> dict[str, Any]:
    return _simple_run_summary(runs)


def _language_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    summary = _simple_run_summary(analysis.get("language", {}))
    structured_exec: dict[str, Any] = {}
    add_checkpoint = _best_structured_checkpoint(analysis, "add")
    sub_checkpoint = _best_structured_checkpoint(analysis, "sub")
    bridge_path = DATASET_DIR / "language" / "eval_structured_execution.jsonl"
    if add_checkpoint and sub_checkpoint and bridge_path.exists():
        for op, checkpoint in (("add", add_checkpoint), ("sub", sub_checkpoint)):
            filtered = (
                RUNS_DIR / "language_bridge" / f"eval_structured_execution_{op}.jsonl"
            )
            records = [
                record
                for record in _read_jsonl(bridge_path)
                if record["metadata"]["primitive"] == op
            ]
            _write_jsonl(filtered, records)
            structured_exec[op] = _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=filtered,
                output_dir=RUNS_DIR / "language_bridge" / f"structured_exec_{op}",
            )
    summary["structured_execution_from_parse"] = structured_exec
    return summary


def _composition_gate(analysis: dict[str, Any]) -> dict[str, Any]:
    structured = analysis.get("structured_summary", {})
    required: list[float] = []
    for run_name in ("structured_op_add", "structured_op_sub"):
        payload = structured.get(run_name, {})
        for split, values in payload.items():
            if split.startswith("unseen_"):
                required.append(float(values.get("final_nem", 0.0)))
    if not required:
        return {
            "should_run": False,
            "min_context_score": None,
            "reason": "structured context runs missing",
        }
    min_score = min(required)
    return {
        "should_run": min_score >= 0.95,
        "min_context_score": min_score,
        "reason": "primitive invocation reached gate"
        if min_score >= 0.95
        else "primitive invocation below 0.95 gate",
    }


def _eval_paths_for_spec(spec: RunSpec) -> dict[str, Path]:
    if spec.group == "context_aug":
        op = "add" if spec.name.endswith("_add") else "sub"
        base = DATASET_DIR / "context_aug" / op
        return {
            **{
                f"seen_{context}": base / f"eval_seen_{context}.jsonl"
                for context in CONTEXTS
            },
            **{
                f"unseen_{context}": base / f"eval_unseen_{context}.jsonl"
                for context in CONTEXTS
            },
            "train_all": base / "eval_train_all.jsonl",
        }
    if spec.group == "structured":
        op = "add" if spec.name.endswith("_add") else "sub"
        base = DATASET_DIR / "structured" / op
        return {
            **{
                f"seen_{context}": base / f"eval_seen_{context}.jsonl"
                for context in STRUCTURED_CONTEXTS
            },
            **{
                f"unseen_{context}": base / f"eval_unseen_{context}.jsonl"
                for context in STRUCTURED_CONTEXTS
            },
            "train_all": base / "eval_train_all.jsonl",
        }
    if spec.group == "composition":
        base = DATASET_DIR / "composition"
        return {
            "train": base / "eval_train.jsonl",
            "seen": base / "eval_seen.jsonl",
            "unseen": base / "eval_unseen.jsonl",
            "tf1_step1_result": base / "eval_tf1_step1_result.jsonl",
            "tf2_full_step1_state": base / "eval_tf2_full_step1_state.jsonl",
            "tf3_step2_only": base / "eval_tf3_step2_only.jsonl",
            "sub_add_heldout": base / "eval_sub_add_heldout.jsonl",
        }
    if spec.group == "language":
        base = DATASET_DIR / "language"
        return {
            "seen": base / "eval_seen.jsonl",
            "heldout": base / "eval_heldout.jsonl",
        }
    raise AssertionError(spec.group)


def _best_structured_checkpoint(analysis: dict[str, Any], op: Primitive) -> Path | None:
    run = analysis.get("structured", {}).get(f"structured_op_{op}", {})
    if run.get("status") != "complete":
        return None
    final_step = str(run["run_spec"]["steps"])
    checkpoint = run["checkpoints"].get(final_step, {}).get("checkpoint")
    return Path(checkpoint) if checkpoint else None


def _available_checkpoints(spec: RunSpec) -> dict[int, Path]:
    checkpoint_dir = RUNS_DIR / spec.name / "checkpoints"
    if not checkpoint_dir.exists():
        return {}
    result: dict[int, Path] = {}
    for path in sorted(checkpoint_dir.glob("step_*.pt")):
        try:
            step = int(path.stem.removeprefix("step_"))
        except ValueError:
            continue
        result[step] = path
    return result


def _checkpoint_path(spec: RunSpec, step: int) -> Path:
    return RUNS_DIR / spec.name / "checkpoints" / f"step_{step:06d}.pt"


def _m171_checkpoint(op: Primitive) -> Path | None:
    path = (
        M171_RUNS_DIR / f"primitive_{op}_scale_30000" / "checkpoints" / "step_020000.pt"
    )
    return path if path.exists() else None


def _final_nem(payload: dict[str, Any]) -> float:
    if not payload:
        return 0.0
    summary = payload.get("summary", {})
    overall = summary.get("overall", summary)
    return float(
        payload.get(
            "final_nem",
            overall.get("final_normalized_exact_match", 0.0),
        )
    )


def _write_analysis(analysis: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _last_train_loss(path: Path) -> float | None:
    if not path.exists():
        return None
    last = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last = json.loads(line)
    return None if last is None else float(last.get("train_loss", 0.0))


def _spec_payload(spec: RunSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "train_path": str(spec.train_path),
        "eval_path": str(spec.eval_path),
        "steps": spec.steps,
        "group": spec.group,
        "seed": spec.seed,
        "sequence_length": spec.sequence_length,
        "model_config": spec.model_config,
    }


def _prompt_intersections(*, include_train_probes: bool) -> dict[str, int]:
    result: dict[str, int] = {}
    for directory in DATASET_DIR.rglob("*"):
        if not directory.is_dir():
            continue
        train_files = list(directory.glob("train*.jsonl"))
        eval_files = [
            file
            for file in directory.glob("eval*.jsonl")
            if include_train_probes or not file.name.startswith("eval_train")
        ]
        if not train_files or not eval_files:
            continue
        train_prompts = {
            record["prompt"] for file in train_files for record in _read_jsonl(file)
        }
        eval_prompts = {
            record["prompt"] for file in eval_files for record in _read_jsonl(file)
        }
        result[str(directory.relative_to(DATASET_DIR))] = len(
            train_prompts & eval_prompts
        )
    return result


def _task_type_counts(root: Path) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for path in root.rglob("*.jsonl"):
        for record in _read_jsonl(path):
            counter[str(record["task_type"])] += 1
    return dict(sorted(counter.items()))


def _dataset_notes(manifest: dict[str, Any]) -> str:
    lines = [
        f"- train_count: `{manifest.get('train_count')}`",
        f"- eval_count: `{manifest.get('eval_count')}`",
        f"- contexts: `{manifest.get('contexts')}`",
        f"- structured_contexts: `{manifest.get('structured_contexts')}`",
        f"- M-17.1 checkpoints: `{manifest.get('m171_checkpoints')}`",
        f"- prompt intersections including train probes: `{manifest.get('prompt_intersections')}`",
        f"- heldout prompt intersections: `{manifest.get('heldout_prompt_intersections')}`",
    ]
    return "\n".join(lines)


def _context_matrix_table(analysis: dict[str, Any]) -> str:
    matrix = analysis.get("context_invariance", {})
    rows = [
        "| primitive | context | train | seen | unseen |",
        "|---|---|---:|---:|---:|",
    ]
    for op in ("add", "sub"):
        for context in CONTEXTS:
            values = matrix.get(op, {}).get(context, {})
            rows.append(
                f"| {op.upper()} | {context} | {_fmt(values.get('train'))} | {_fmt(values.get('seen'))} | {_fmt(values.get('unseen'))} |"
            )
    return "\n".join(rows)


def _neutral_table(analysis: dict[str, Any]) -> str:
    neutral = analysis.get("neutral_prefix", {})
    rows = ["| primitive | prefix | unseen final NEM |", "|---|---|---:|"]
    for op in ("add", "sub"):
        for name, score in neutral.get(op, {}).items():
            rows.append(f"| {op.upper()} | {name} | {_fmt(score)} |")
    return "\n".join(rows)


def _teacher_forced_table(analysis: dict[str, Any]) -> str:
    values = analysis.get("teacher_forced_factorization", {})
    labels = {
        "b1_canonical": "B1 canonical",
        "b2_state_canonical": "B2 state + canonical SUB",
        "b3_state_step": "B3 state + STEP2 SUB",
        "b4_prev_op_canonical": "B4 previous op + canonical SUB",
    }
    rows = ["| probe | unseen final NEM |", "|---|---:|"]
    for key in TF_PROBES:
        rows.append(f"| {labels[key]} | {_fmt(values.get(key))} |")
    return "\n".join(rows)


def _context_aug_table(analysis: dict[str, Any]) -> str:
    summary = analysis.get("context_aug_summary", {})
    rows = ["| run | split/context | final NEM |", "|---|---|---:|"]
    canonical = analysis.get("context_invariance", {})
    for op in ("add", "sub"):
        rows.append(
            f"| canonical-only {op} | unseen previous_operation | {_fmt(canonical.get(op, {}).get('previous_operation', {}).get('unseen'))} |"
        )
    for run_name, payload in summary.items():
        for split, values in sorted(payload.items()):
            if split in {
                "train_all",
                "unseen_previous_operation",
                "unseen_language_parse_prefix",
                "unseen_canonical",
            }:
                rows.append(
                    f"| {run_name} | {split} | {_fmt(values.get('final_nem'))} |"
                )
    return "\n".join(rows)


def _structured_table(analysis: dict[str, Any]) -> str:
    summary = analysis.get("structured_summary", {})
    rows = [
        "| representation | run | split/context | final NEM |",
        "|---|---|---|---:|",
    ]
    aug = analysis.get("context_aug_summary", {})
    for run_name, payload in aug.items():
        rows.append(
            f"| plain text | {run_name} | unseen_previous_operation | {_fmt(payload.get('unseen_previous_operation', {}).get('final_nem'))} |"
        )
    for run_name, payload in summary.items():
        for split, values in sorted(payload.items()):
            if split in {
                "train_all",
                "unseen_structured_standalone",
                "unseen_structured_previous_operation",
                "unseen_structured_step",
                "unseen_structured_state",
            }:
                rows.append(
                    f"| structured OP | {run_name} | {split} | {_fmt(values.get('final_nem'))} |"
                )
    return "\n".join(rows)


def _composition_table(analysis: dict[str, Any]) -> str:
    gate = analysis.get("composition_gate", {})
    summary = analysis.get("composition_summary", {})
    if not gate.get("should_run") and not summary:
        return f"Composition skipped: {gate.get('reason')} (min_context_score={_fmt(gate.get('min_context_score'))})."
    rows = ["| split | final | step1 | step2 |", "|---|---:|---:|---:|"]
    payload = summary.get("structured_add_sub", {})
    for split, values in sorted(payload.items()):
        trace = values.get("trace", {})
        rows.append(
            f"| {split} | {_fmt(values.get('final_nem'))} | {_fmt(trace.get('step1_accuracy'))} | {_fmt(trace.get('step2_accuracy'))} |"
        )
    return "\n".join(rows)


def _heldout_composition_note(analysis: dict[str, Any]) -> str:
    comp = analysis.get("composition_summary", {}).get("structured_add_sub", {})
    trained = comp.get("unseen", {}).get("final_nem")
    heldout = comp.get("sub_add_heldout", {}).get("final_nem")
    if trained is None:
        return "SUB_ADD held-out composition not tested because trained ADD_SUB did not run."
    if trained < 0.90:
        return f"SUB_ADD held-out composition is not interpreted because trained ADD_SUB unseen={trained:.4f} < 0.90."
    return f"SUB_ADD held-out final NEM: {_fmt(heldout)}."


def _language_table(analysis: dict[str, Any]) -> str:
    lang = analysis.get("language_summary", {})
    parse = lang.get("language_to_structured_parse", {})
    rows = [
        "| component | split | final/parse NEM | op | argA | argB |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for split, values in sorted(parse.items()):
        trace = values.get("trace", {})
        rows.append(
            f"| language -> structured parse | {split} | {_fmt(values.get('final_nem'))} | {_fmt(trace.get('op_accuracy'))} | {_fmt(trace.get('arg_a_accuracy'))} | {_fmt(trace.get('arg_b_accuracy'))} |"
        )
    structured = lang.get("structured_execution_from_parse", {})
    for op, values in sorted(structured.items()):
        rows.append(
            f"| structured parse -> arithmetic | {op} | {_fmt(values.get('final_nem'))} | n/a | n/a | n/a |"
        )
    return "\n".join(rows)


def _decision(analysis: dict[str, Any]) -> str:
    context = analysis.get("context_invariance", {})
    canonical_scores = [
        context.get(op, {}).get("canonical", {}).get("unseen", 0.0)
        for op in ("add", "sub")
    ]
    prefixed_scores = [
        context.get(op, {}).get(name, {}).get("unseen", 0.0)
        for op in ("add", "sub")
        for name in CONTEXTS
        if name != "canonical"
    ]
    structured_scores = [
        values.get("final_nem", 0.0)
        for payload in analysis.get("structured_summary", {}).values()
        for split, values in payload.items()
        if split.startswith("unseen_")
    ]
    comp = analysis.get("composition_summary", {}).get("structured_add_sub", {})
    lang = analysis.get("language_summary", {}).get("language_to_structured_parse", {})
    parts: list[str] = []
    if (
        canonical_scores
        and min(canonical_scores) >= 0.95
        and prefixed_scores
        and min(prefixed_scores) < 0.95
    ):
        parts.append(
            "OUTCOME A: canonical ADD/SUB are high, but prefixed/wrapped contexts are lower, indicating contextual primitive invocation failure."
        )
    if (
        structured_scores
        and min(structured_scores) >= 0.95
        and comp
        and comp.get("unseen", {}).get("final_nem", 0.0) < 0.90
    ):
        parts.append(
            "OUTCOME B: invocation is fixed in structured contexts, but trained composition still fails."
        )
    if (
        comp
        and comp.get("unseen", {}).get("final_nem", 0.0) >= 0.90
        and comp.get("sub_add_heldout", {}).get("final_nem", 0.0) < 0.90
    ):
        parts.append(
            "OUTCOME C: trained composition works, but held-out composition does not."
        )
    if structured_scores and min(structured_scores) >= 0.95:
        parts.append(
            "OUTCOME D: structured operation tokens improve invocation invariance."
        )
    heldout_parse = lang.get("heldout", {})
    if heldout_parse and heldout_parse.get("final_nem", 0.0) < 0.80:
        parts.append(
            "OUTCOME E: language parsing into the shared structured primitive representation is a separate bottleneck."
        )
    return (
        " ".join(parts)
        if parts
        else "No decisive outcome yet; complete missing runs and rebuild the report."
    )


def _next_milestone(analysis: dict[str, Any]) -> str:
    decision = _decision(analysis)
    if "OUTCOME A" in decision:
        return "Standardize operation representation and use a context-augmentation curriculum before broad composition."
    if "OUTCOME B" in decision:
        return "Investigate working-memory/state propagation with recurrent/input-injection probes."
    if "OUTCOME C" in decision:
        return "Proceed to M-18 RFFT / explicit rule-following on clean systematic composition."
    if "OUTCOME E" in decision:
        return "Train a small language frontend that emits the exact shared structured operation language."
    return "Finish missing M-17.2 diagnostics."


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


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
    raise SystemExit(main())
