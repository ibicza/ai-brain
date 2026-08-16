from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Literal

from ai_brain.eval.runner import eval_lm
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m173_position_shift_invariance"
RUNS_DIR = ROOT / "runs" / "m173_position_shift_invariance"
DOC_PATH = ROOT / "docs" / "m173_position_shift_invariance_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m173_position_shift_invariance_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"
M171_RUNS_DIR = ROOT / "runs" / "m171_primitive_language"

SEED = 317300
TRAIN_COUNT = 9000
EVAL_COUNT_PER_OP = 250
STEPS = 8000
LANGUAGE_STEPS = 5000
SEQUENCE_LENGTH = 128
MAX_NEW_TOKENS = 32
SHIFT_OFFSETS = (0, 1, 2, 4, 8, 16, 32)
CONTENT_PREFIX_SHIFTS = SHIFT_OFFSETS
CONTEXTS = (
    "canonical",
    "task_prefix",
    "step_prefix",
    "state_prefix",
    "previous_result",
    "previous_operation",
    "language_parse_prefix",
)

Primitive = Literal["add", "sub"]


@dataclass(frozen=True)
class Case:
    op: Primitive
    a: int
    b: int

    @property
    def op_token(self) -> str:
        return "ADD" if self.op == "add" else "SUB"

    @property
    def sign(self) -> str:
        return "+" if self.op == "add" else "-"

    @property
    def result(self) -> int:
        return self.a + self.b if self.op == "add" else self.a - self.b

    @property
    def key(self) -> str:
        return f"{self.op}:{self.a}:{self.b}"


@dataclass(frozen=True)
class RunSpec:
    name: str
    train_path: Path
    eval_path: Path
    position_encoding: str = "absolute"
    position_shift_max: int = 0
    steps: int = STEPS
    seed: int = SEED
    sequence_length: int = SEQUENCE_LENGTH
    model_config_name: str = "arithmetic_3m"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-variants")
    subparsers.add_parser("run-language")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-variants":
        run_specs(variant_specs())
    elif args.command == "run-language":
        run_language_bridge()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_specs(variant_specs())
        analyze_all()
        run_language_bridge()
        analyze_all()
        build_report(checks_passed=False)
    return 0


def prepare_datasets() -> None:
    rng = random.Random(SEED)
    all_cases = {op: _split_cases(op, rng) for op in ("add", "sub")}
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    _write_train_datasets(all_cases, rng)
    _write_shift_evals(all_cases)
    _write_context_evals(all_cases)
    _write_language_bridge(rng)
    _write_manifest(all_cases)


def variant_specs() -> list[RunSpec]:
    train = DATASET_DIR / "train_canonical.jsonl"
    content = DATASET_DIR / "train_content_prefix_0_8.jsonl"
    eval_path = DATASET_DIR / "eval" / "shift_0.jsonl"
    return [
        RunSpec(
            name="ape_canonical",
            train_path=train,
            eval_path=eval_path,
            position_encoding="absolute",
            position_shift_max=0,
            seed=SEED + 1,
        ),
        RunSpec(
            name="shape_8",
            train_path=train,
            eval_path=eval_path,
            position_encoding="shifted_absolute",
            position_shift_max=8,
            seed=SEED + 2,
        ),
        RunSpec(
            name="shape_32",
            train_path=train,
            eval_path=eval_path,
            position_encoding="shifted_absolute",
            position_shift_max=32,
            seed=SEED + 3,
        ),
        RunSpec(
            name="shape_64",
            train_path=train,
            eval_path=eval_path,
            position_encoding="shifted_absolute",
            position_shift_max=64,
            seed=SEED + 4,
        ),
        RunSpec(
            name="nope",
            train_path=train,
            eval_path=eval_path,
            position_encoding="nope",
            seed=SEED + 5,
        ),
        RunSpec(
            name="content_prefix_0_8",
            train_path=content,
            eval_path=eval_path,
            position_encoding="absolute",
            seed=SEED + 6,
        ),
        RunSpec(
            name="shape_32_content_prefix_0_8",
            train_path=content,
            eval_path=eval_path,
            position_encoding="shifted_absolute",
            position_shift_max=32,
            seed=SEED + 7,
        ),
    ]


def language_specs(best_position_encoding: str, best_shift_max: int) -> list[RunSpec]:
    train = DATASET_DIR / "language" / "train_parse.jsonl"
    eval_path = DATASET_DIR / "language" / "eval_seen.jsonl"
    return [
        RunSpec(
            name="language_ape",
            train_path=train,
            eval_path=eval_path,
            position_encoding="absolute",
            position_shift_max=0,
            steps=LANGUAGE_STEPS,
            seed=SEED + 80,
            sequence_length=192,
        ),
        RunSpec(
            name="language_best_position",
            train_path=train,
            eval_path=eval_path,
            position_encoding=best_position_encoding,
            position_shift_max=best_shift_max,
            steps=LANGUAGE_STEPS,
            seed=SEED + 81,
            sequence_length=192,
        ),
    ]


def run_specs(specs: list[RunSpec]) -> None:
    for spec in specs:
        checkpoint = _checkpoint_path(spec)
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
            model_config_name=spec.model_config_name,
            steps=spec.steps,
            batch_size=8,
            sequence_length=spec.sequence_length,
            loss_mode="answer-only",
            learning_rate=3e-4,
            grad_clip_norm=1.0,
            numeric_tokenization="digit_safe",
            position_encoding=spec.position_encoding,
            position_shift_max=spec.position_shift_max,
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


def run_language_bridge() -> None:
    analysis = (
        _read_json(RUNS_DIR / "analysis.json")
        if (RUNS_DIR / "analysis.json").exists()
        else {}
    )
    best = _best_position_variant(analysis)
    specs = language_specs(
        best_position_encoding=str(best.get("position_encoding", "absolute")),
        best_shift_max=int(best.get("position_shift_max", 0)),
    )
    run_specs(specs)


def analyze_all() -> None:
    analysis = {
        "manifest": _read_json(DATASET_DIR / "manifest.json"),
        "ape_m171": _analyze_m171_baseline(),
        "variants": _analyze_variant_specs(),
    }
    analysis["method_summary"] = _method_summary(analysis["variants"])
    analysis["best_variant"] = _best_position_variant(analysis)
    analysis["context_retest"] = _context_retest(analysis["best_variant"])
    analysis["composition_gate"] = _composition_gate(analysis)
    analysis["composition"] = _composition_retest(analysis["composition_gate"])
    analysis["language_bridge"] = _language_retest(analysis["best_variant"])
    analysis["multiseed"] = _multiseed_summary(analysis)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    commit = _git_commit()
    lines = [
        "# M-17.3 Position-Shift Invariance Report",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{commit}`",
        f"- device: `{_device_name(analysis)}`",
        "",
        "## Dataset Verification",
        "",
        _dataset_notes(analysis),
        "",
        "## APE Pure Position-Shift Curve",
        "",
        _shift_curve_table(analysis.get("ape_m171", {}).get("pure_position", {})),
        "",
        "## Content-Prefix Shift Curve",
        "",
        _shift_curve_table(analysis.get("ape_m171", {}).get("content_prefix", {})),
        "",
        "## Position Method Comparison",
        "",
        _method_comparison_table(analysis),
        "",
        "## M-17.2 Context Retest",
        "",
        _context_table(analysis),
        "",
        "## ADD_SUB Retest",
        "",
        _composition_table(analysis),
        "",
        "## Language Bridge Retest",
        "",
        _language_table(analysis),
        "",
        "## Multi-Seed Results",
        "",
        _multiseed_table(analysis),
        "",
        "## Relative Position Baseline",
        "",
        "Deferred: M-17.3 implements the mandatory SHAPE-style shifted absolute positions and NoPE baseline. A true T5-style relative attention bias is intentionally not mixed into this diagnostic patch.",
        "",
        "## Decision",
        "",
        _decision(analysis),
    ]
    text = "\n".join(lines)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def _split_cases(op: Primitive, rng: random.Random) -> dict[str, list[Case]]:
    if op == "add":
        candidates = [Case(op, a, b) for a in range(10, 100) for b in range(10, 100)]
    else:
        candidates = [Case(op, a, b) for a in range(10, 100) for b in range(1, a + 1)]
    rng.shuffle(candidates)
    train_unique_count = min(6000, len(candidates) - EVAL_COUNT_PER_OP)
    train_unique = candidates[:train_unique_count]
    eval_cases = candidates[train_unique_count : train_unique_count + EVAL_COUNT_PER_OP]
    train = []
    while len(train) < TRAIN_COUNT // 2:
        rng.shuffle(train_unique)
        train.extend(train_unique[: (TRAIN_COUNT // 2) - len(train)])
    return {"train": train, "eval": eval_cases}


def _write_train_datasets(
    all_cases: dict[str, dict[str, list[Case]]],
    rng: random.Random,
) -> None:
    train_records = []
    prefix_records = []
    index = 0
    for op in ("add", "sub"):
        for case in all_cases[op]["train"]:
            train_records.append(_record(case, _canonical_prompt(case), "train", index))
            prefix_len = rng.randint(0, 8)
            prefix_records.append(
                _record(case, _content_prefix_prompt(case, prefix_len), "train", index)
            )
            index += 1
    rng.shuffle(train_records)
    rng.shuffle(prefix_records)
    _write_jsonl(DATASET_DIR / "train_canonical.jsonl", train_records)
    _write_jsonl(DATASET_DIR / "train_content_prefix_0_8.jsonl", prefix_records)


def _write_shift_evals(all_cases: dict[str, dict[str, list[Case]]]) -> None:
    eval_dir = DATASET_DIR / "eval"
    for shift in CONTENT_PREFIX_SHIFTS:
        combined = []
        for op in ("add", "sub"):
            records = [
                _record(case, _content_prefix_prompt(case, shift), "eval", index)
                for index, case in enumerate(all_cases[op]["eval"])
            ]
            _write_jsonl(eval_dir / op / f"content_shift_{shift}.jsonl", records)
            combined.extend(records)
        _write_jsonl(eval_dir / f"content_shift_{shift}.jsonl", combined)
        if shift == 0:
            _write_jsonl(eval_dir / "shift_0.jsonl", combined)
            for op in ("add", "sub"):
                _write_jsonl(
                    eval_dir / op / "shift_0.jsonl",
                    [
                        _record(case, _canonical_prompt(case), "eval", index)
                        for index, case in enumerate(all_cases[op]["eval"])
                    ],
                )


def _write_context_evals(all_cases: dict[str, dict[str, list[Case]]]) -> None:
    context_dir = DATASET_DIR / "contexts"
    for context in CONTEXTS:
        combined = []
        for op in ("add", "sub"):
            records = [
                _record(case, _context_prompt(case, context), "eval", index)
                for index, case in enumerate(all_cases[op]["eval"])
            ]
            _write_jsonl(context_dir / op / f"{context}.jsonl", records)
            combined.extend(records)
        _write_jsonl(context_dir / f"{context}.jsonl", combined)


def _write_language_bridge(rng: random.Random) -> None:
    base = DATASET_DIR / "language"
    train_records = []
    train_prompts = set()
    for index in range(4000):
        op: Primitive = "add" if index % 2 == 0 else "sub"
        case = _random_case(op, rng)
        template_id = index % 5
        record = _language_record(case, template_id, "train", index)
        train_prompts.add(record["prompt"])
        train_records.append(record)
    seen = []
    heldout = []
    for index in range(EVAL_COUNT_PER_OP * 2):
        while True:
            op = "add" if index % 2 == 0 else "sub"
            case = _random_case(op, rng)
            seen_record = _language_record(case, index % 5, "seen", index)
            heldout_record = _language_record(case, 5 + (index % 3), "heldout", index)
            if (
                seen_record["prompt"] not in train_prompts
                and heldout_record["prompt"] not in train_prompts
            ):
                seen.append(seen_record)
                heldout.append(heldout_record)
                break
    _write_jsonl(base / "train_parse.jsonl", train_records)
    _write_jsonl(base / "eval_seen.jsonl", seen)
    _write_jsonl(base / "eval_heldout.jsonl", heldout)


def _write_manifest(all_cases: dict[str, dict[str, list[Case]]]) -> None:
    train_prompts = {
        record["prompt"]
        for record in _read_jsonl(DATASET_DIR / "train_canonical.jsonl")
    }
    eval_prompts = {
        record["prompt"]
        for path in (DATASET_DIR / "eval").rglob("*.jsonl")
        for record in _read_jsonl(path)
    }
    manifest = {
        "seed": SEED,
        "train_count": TRAIN_COUNT,
        "eval_count_per_op": EVAL_COUNT_PER_OP,
        "shifts": list(SHIFT_OFFSETS),
        "contexts": list(CONTEXTS),
        "m171_checkpoints": {
            "add": str(_m171_checkpoint("add")) if _m171_checkpoint("add") else None,
            "sub": str(_m171_checkpoint("sub")) if _m171_checkpoint("sub") else None,
        },
        "prompt_intersections": len(train_prompts & eval_prompts),
        "case_counts": {
            op: {split: len(cases) for split, cases in payload.items()}
            for op, payload in all_cases.items()
        },
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _random_case(op: Primitive, rng: random.Random) -> Case:
    a = rng.randint(10, 99)
    b = rng.randint(10, 99) if op == "add" else rng.randint(1, a)
    return Case(op, a, b)


def _canonical_prompt(case: Case) -> str:
    return f"{case.op_token} {case.a:02d} {case.sign} {case.b:02d}"


def _content_prefix_prompt(case: Case, prefix_len: int) -> str:
    base = _canonical_prompt(case)
    if prefix_len <= 0:
        return base
    return f"{' '.join(['X'] * prefix_len)} {base}"


def _context_prompt(case: Case, context: str) -> str:
    expr = f"{case.a:02d} {case.sign} {case.b:02d}"
    if context == "canonical":
        return _canonical_prompt(case)
    if context == "task_prefix":
        return f"TASK {case.op_token}\n{expr}"
    if context == "step_prefix":
        return f"STEP2 {case.op_token} {expr}"
    if context == "state_prefix":
        return f"STATE {case.a}\nOP {case.op_token}\nARG {case.b}"
    if context == "previous_result":
        return f"STEP1 RESULT {case.a}\n{case.op_token} {expr}"
    if context == "previous_operation":
        prev_a = max(1, case.a // 2)
        prev_b = case.a - prev_a
        return f"{prev_a} + {prev_b} = {case.a}\nSTEP2 {case.op_token} {expr}"
    if context == "language_parse_prefix":
        return f"OP {case.op_token}\nA {case.a}\nB {case.b}\nRUN"
    raise AssertionError(context)


def _language_record(
    case: Case, template_id: int, split: str, index: int
) -> dict[str, Any]:
    if case.op == "add":
        templates = (
            "У Васи было {a}. Ему дали {b}.",
            "На полке лежало {a}. Добавили {b}.",
            "Было {a} монет, потом прибавили {b}.",
            "Старт {a}. Изменение плюс {b}.",
            "Количество {a}; пришло ещё {b}.",
            "После события плюс {b} к состоянию {a}.",
            "Обнови состояние: начало {a}, прирост {b}.",
            "Суммируй изменение: было {a}, добавка {b}.",
        )
    else:
        templates = (
            "У Васи было {a}. Он отдал {b}.",
            "На полке лежало {a}. Убрали {b}.",
            "Было {a} монет, потом забрали {b}.",
            "Старт {a}. Изменение минус {b}.",
            "Количество {a}; ушло {b}.",
            "После события минус {b} от состояния {a}.",
            "Обнови состояние: начало {a}, расход {b}.",
            "Вычти изменение: было {a}, убрали {b}.",
        )
    prompt = templates[template_id].format(a=case.a, b=case.b)
    return {
        "id": f"m173.language.{split}.{index:06d}",
        "task_type": f"m173.language.{case.op}",
        "prompt": prompt,
        "answer": f"OP {case.op_token}\nA {case.a}\nB {case.b}",
        "metadata": {"op": case.op_token, "split": split, "case_key": case.key},
    }


def _record(case: Case, prompt: str, split: str, index: int) -> dict[str, Any]:
    return {
        "id": f"m173.{case.op}.{split}.{index:06d}",
        "task_type": f"m173.{case.op}",
        "prompt": prompt,
        "answer": f"FINAL {case.result}",
        "metadata": {
            "op": case.op_token,
            "a": case.a,
            "b": case.b,
            "answer_value": case.result,
            "case_key": case.key,
            "split": split,
        },
    }


def _analyze_m171_baseline() -> dict[str, Any]:
    result = {"pure_position": {}, "content_prefix": {}}
    for op in ("add", "sub"):
        checkpoint = _m171_checkpoint(op)
        if checkpoint is None:
            continue
        pure = {}
        content = {}
        for offset in SHIFT_OFFSETS:
            pure[str(offset)] = _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=DATASET_DIR / "eval" / op / "shift_0.jsonl",
                output_dir=RUNS_DIR / "ape_m171" / op / "pure" / f"offset_{offset}",
                position_offset=offset,
            )
            content[str(offset)] = _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=DATASET_DIR / "eval" / op / f"content_shift_{offset}.jsonl",
                output_dir=RUNS_DIR / "ape_m171" / op / "content" / f"shift_{offset}",
                position_offset=0,
            )
        result["pure_position"][op] = pure
        result["content_prefix"][op] = content
    return result


def _analyze_variant_specs() -> dict[str, Any]:
    result = {}
    for spec in variant_specs():
        checkpoint = _checkpoint_path(spec)
        if not checkpoint.exists():
            result[spec.name] = {"status": "missing", "run_spec": _spec_payload(spec)}
            continue
        pure = {}
        content = {}
        for offset in SHIFT_OFFSETS:
            pure[str(offset)] = _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=DATASET_DIR / "eval" / "shift_0.jsonl",
                output_dir=RUNS_DIR / spec.name / "eval" / "pure" / f"offset_{offset}",
                position_offset=offset,
            )
            content[str(offset)] = _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=DATASET_DIR / "eval" / f"content_shift_{offset}.jsonl",
                output_dir=RUNS_DIR
                / spec.name
                / "eval"
                / "content"
                / f"shift_{offset}",
                position_offset=0,
            )
        result[spec.name] = {
            "status": "complete",
            "run_spec": _spec_payload(spec),
            "pure_position": pure,
            "content_prefix": content,
            "train_loss": _last_train_loss(RUNS_DIR / spec.name / "metrics.jsonl"),
        }
    return result


def _context_retest(best: dict[str, Any]) -> dict[str, Any]:
    checkpoint = Path(str(best.get("checkpoint", "")))
    if not checkpoint.is_file():
        return {"status": "missing"}
    result = {}
    for context in CONTEXTS:
        result[context] = _eval_checkpoint(
            checkpoint=checkpoint,
            eval_path=DATASET_DIR / "contexts" / f"{context}.jsonl",
            output_dir=RUNS_DIR / "context_retest" / context,
            position_offset=0,
        )
    return result


def _composition_retest(gate: dict[str, Any]) -> dict[str, Any]:
    return {"status": "skipped", "reason": gate["reason"]}


def _language_retest(best: dict[str, Any]) -> dict[str, Any]:
    if best.get("status") == "missing":
        return {"status": "missing", "reason": "no complete position variant"}
    result = {}
    specs = language_specs(
        best_position_encoding=str(best.get("position_encoding", "absolute")),
        best_shift_max=int(best.get("position_shift_max", 0)),
    )
    for spec in specs:
        checkpoint = _checkpoint_path(spec)
        if not checkpoint.exists():
            result[spec.name] = {"status": "missing", "run_spec": _spec_payload(spec)}
            continue
        result[spec.name] = {
            "status": "complete",
            "run_spec": _spec_payload(spec),
            "seen": _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=DATASET_DIR / "language" / "eval_seen.jsonl",
                output_dir=RUNS_DIR / spec.name / "eval" / "seen",
                position_offset=0,
            ),
            "heldout": _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=DATASET_DIR / "language" / "eval_heldout.jsonl",
                output_dir=RUNS_DIR / spec.name / "eval" / "heldout",
                position_offset=0,
            ),
        }
    return result


def _eval_checkpoint(
    *,
    checkpoint: Path,
    eval_path: Path,
    output_dir: Path,
    position_offset: int,
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
            position_offset=position_offset,
        )["summary"]
    overall = summary.get("overall", summary)
    by_task = summary.get("by_task_type", {})
    return {
        "summary": summary,
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "normalized_exact_match": float(overall.get("normalized_exact_match", 0.0)),
        "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
        "empty_prediction_rate": float(summary.get("empty_prediction_rate", 0.0)),
        "avg_tokens_generated": float(summary.get("avg_tokens_generated", 0.0)),
        "by_task_type": {
            key: float(value.get("final_normalized_exact_match", 0.0))
            for key, value in by_task.items()
        },
    }


def _method_summary(variants: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for name, payload in variants.items():
        if payload.get("status") != "complete":
            continue
        result[name] = {
            "canonical": _final_nem(payload["pure_position"].get("0", {})),
            "pure_shift_8": _final_nem(payload["pure_position"].get("8", {})),
            "pure_shift_32": _final_nem(payload["pure_position"].get("32", {})),
            "content_shift_8": _final_nem(payload["content_prefix"].get("8", {})),
            "content_shift_16": _final_nem(payload["content_prefix"].get("16", {})),
            "content_shift_32": _final_nem(payload["content_prefix"].get("32", {})),
        }
    return result


def _best_position_variant(analysis: dict[str, Any]) -> dict[str, Any]:
    variants = analysis.get("variants", {})
    best_name = None
    best_score = -1.0
    for name, payload in variants.items():
        if payload.get("status") != "complete":
            continue
        content_scores = [
            _final_nem(payload["content_prefix"].get(str(offset), {}))
            for offset in (1, 2, 4, 8)
        ]
        pure_scores = [
            _final_nem(payload["pure_position"].get(str(offset), {}))
            for offset in (0, 1, 2, 4, 8, 16, 32)
        ]
        score = min(content_scores) + 0.25 * min(pure_scores)
        if score > best_score:
            best_name = name
            best_score = score
    if best_name is None:
        return {"status": "missing"}
    payload = variants[best_name]
    spec = payload["run_spec"]
    return {
        "name": best_name,
        "checkpoint": str(_checkpoint_path_from_name(best_name, int(spec["steps"]))),
        "position_encoding": spec["position_encoding"],
        "position_shift_max": spec["position_shift_max"],
        "score": best_score,
    }


def _composition_gate(analysis: dict[str, Any]) -> dict[str, Any]:
    best_name = analysis.get("best_variant", {}).get("name")
    if not best_name:
        return {"should_run": False, "reason": "no complete position variant"}
    best_payload = analysis["variants"][best_name]
    neutral_scores = [
        _final_nem(best_payload["content_prefix"].get(str(offset), {}))
        for offset in (1, 2, 4, 8)
    ]
    context_scores = [
        _final_nem(analysis["context_retest"].get(context, {}))
        for context in ("canonical", "task_prefix", "step_prefix", "state_prefix")
    ]
    neutral_min = min(neutral_scores) if neutral_scores else 0.0
    context_min = min(context_scores) if context_scores else 0.0
    should_run = neutral_min >= 0.95 and context_min >= 0.90
    reason = (
        "position/context gate passed"
        if should_run
        else f"gate failed: neutral_min={neutral_min:.4f}, context_min={context_min:.4f}"
    )
    return {
        "should_run": should_run,
        "reason": reason,
        "neutral_min": neutral_min,
        "context_min": context_min,
    }


def _multiseed_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    # M-17.3 only launches additional seeds after a variant crosses the neutral
    # robustness threshold. This summary records whether that condition was met.
    qualifying = []
    for name, payload in analysis.get("variants", {}).items():
        if payload.get("status") != "complete":
            continue
        values = [
            _final_nem(payload["content_prefix"].get(str(offset), {}))
            for offset in (1, 2, 4, 8)
        ]
        if values and min(values) >= 0.90:
            qualifying.append(name)
    if not qualifying:
        return {
            "status": "not_run",
            "reason": "no variant reached neutral shift >= 0.90",
        }
    return {"status": "pending", "qualifying_variants": qualifying}


def _shift_curve_table(payload: dict[str, Any]) -> str:
    lines = ["| offset | ADD | SUB |", "|---:|---:|---:|"]
    for offset in SHIFT_OFFSETS:
        lines.append(
            f"| {offset} | "
            f"{_fmt(_final_nem(payload.get('add', {}).get(str(offset), {})))} | "
            f"{_fmt(_final_nem(payload.get('sub', {}).get(str(offset), {})))} |"
        )
    return "\n".join(lines)


def _method_comparison_table(analysis: dict[str, Any]) -> str:
    lines = [
        "| method | canonical | pure1 | pure2 | pure4 | pure8 | pure16 | pure32 | content1 | content2 | content4 | content8 | content16 | content32 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, payload in analysis.get("variants", {}).items():
        if payload.get("status") != "complete":
            continue
        pure = payload["pure_position"]
        content = payload["content_prefix"]
        lines.append(
            f"| {name} | "
            f"{_fmt(_final_nem(pure.get('0', {})))} | "
            f"{_fmt(_final_nem(pure.get('1', {})))} | "
            f"{_fmt(_final_nem(pure.get('2', {})))} | "
            f"{_fmt(_final_nem(pure.get('4', {})))} | "
            f"{_fmt(_final_nem(pure.get('8', {})))} | "
            f"{_fmt(_final_nem(pure.get('16', {})))} | "
            f"{_fmt(_final_nem(pure.get('32', {})))} | "
            f"{_fmt(_final_nem(content.get('1', {})))} | "
            f"{_fmt(_final_nem(content.get('2', {})))} | "
            f"{_fmt(_final_nem(content.get('4', {})))} | "
            f"{_fmt(_final_nem(content.get('8', {})))} | "
            f"{_fmt(_final_nem(content.get('16', {})))} | "
            f"{_fmt(_final_nem(content.get('32', {})))} |"
        )
    return "\n".join(lines)


def _context_table(analysis: dict[str, Any]) -> str:
    lines = ["| context | final NEM |", "|---|---:|"]
    for context in CONTEXTS:
        lines.append(
            f"| {context} | {_fmt(_final_nem(analysis.get('context_retest', {}).get(context, {})))} |"
        )
    return "\n".join(lines)


def _composition_table(analysis: dict[str, Any]) -> str:
    comp = analysis.get("composition", {})
    if comp.get("status") == "skipped":
        return f"Composition skipped: {comp.get('reason', 'gate failed')}."
    return json.dumps(comp, ensure_ascii=False, indent=2)


def _language_table(analysis: dict[str, Any]) -> str:
    lines = ["| run | seen | heldout |", "|---|---:|---:|"]
    for name, payload in analysis.get("language_bridge", {}).items():
        if payload.get("status") != "complete":
            lines.append(f"| {name} | missing | missing |")
            continue
        lines.append(
            f"| {name} | {_fmt(_final_nem(payload.get('seen', {})))} | "
            f"{_fmt(_final_nem(payload.get('heldout', {})))} |"
        )
    return "\n".join(lines)


def _multiseed_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("multiseed", {})
    if payload.get("status") != "complete":
        return payload.get("reason", payload.get("status", "not available"))
    lines = [
        "| variant | metric | mean | std | min | max |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for variant, metrics in payload.get("results", {}).items():
        for metric, values in metrics.items():
            lines.append(
                f"| {variant} | {metric} | {_fmt(mean(values))} | {_fmt(pstdev(values))} | "
                f"{_fmt(min(values))} | {_fmt(max(values))} |"
            )
    return "\n".join(lines)


def _decision(analysis: dict[str, Any]) -> str:
    best_name = analysis.get("best_variant", {}).get("name", "n/a")
    best_payload = analysis.get("variants", {}).get(best_name, {})
    if not best_payload:
        return "OUTCOME D: no complete positional method run is available."
    content8 = _final_nem(best_payload["content_prefix"].get("8", {}))
    context_min = analysis.get("composition_gate", {}).get("context_min", 0.0)
    if content8 >= 0.95 and context_min < 0.90:
        return (
            "OUTCOME B: the best positional method fixes neutral prefix shift, "
            "but semantic/context wrappers remain weak."
        )
    if content8 >= 0.95 and context_min >= 0.90:
        return (
            "OUTCOME C candidate: invocation is position-robust enough; composition "
            "must be tested to separate routing from state-transition limits."
        )
    return (
        "OUTCOME D: no tested positional method made neutral content-prefix shifts "
        "robust enough for composition claims."
    )


def _dataset_notes(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    return "\n".join(
        [
            f"- train_count: `{manifest.get('train_count')}`",
            f"- eval_count_per_op: `{manifest.get('eval_count_per_op')}`",
            f"- shifts: `{manifest.get('shifts')}`",
            f"- contexts: `{manifest.get('contexts')}`",
            f"- prompt_intersections: `{manifest.get('prompt_intersections')}`",
            f"- M-17.1 checkpoints: `{manifest.get('m171_checkpoints')}`",
            f"- best_variant: `{analysis.get('best_variant')}`",
        ]
    )


def _device_name(analysis: dict[str, Any]) -> str:
    for payload in analysis.get("variants", {}).values():
        if payload.get("status") == "complete":
            summary = payload["pure_position"]["0"]["summary"]
            return f"{summary.get('device')} ({summary.get('device_name')})"
    return "unknown"


def _final_nem(payload: dict[str, Any]) -> float:
    return float(payload.get("final_nem", 0.0)) if payload else 0.0


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def _checkpoint_path(spec: RunSpec) -> Path:
    return _checkpoint_path_from_name(spec.name, spec.steps)


def _checkpoint_path_from_name(name: str, steps: int) -> Path:
    return RUNS_DIR / name / "checkpoints" / f"step_{steps:06d}.pt"


def _m171_checkpoint(op: Primitive) -> Path | None:
    path = (
        M171_RUNS_DIR / f"primitive_{op}_scale_30000" / "checkpoints" / "step_020000.pt"
    )
    return path if path.exists() else None


def _spec_payload(spec: RunSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "train_path": str(spec.train_path),
        "eval_path": str(spec.eval_path),
        "position_encoding": spec.position_encoding,
        "position_shift_max": spec.position_shift_max,
        "steps": spec.steps,
        "seed": spec.seed,
        "sequence_length": spec.sequence_length,
        "model_config_name": spec.model_config_name,
    }


def _last_train_loss(metrics_path: Path) -> float | None:
    if not metrics_path.exists():
        return None
    last = None
    with metrics_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last = json.loads(line)
    return None if last is None else float(last.get("train_loss", 0.0))


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
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


if __name__ == "__main__":
    raise SystemExit(main())
