from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.generation import generate_answer_ids, load_model_for_inference
from ai_brain.eval.normalize import extract_generated_answer, normalize_answer
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.runtime.device import get_device_info
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m191_faithful_systematic_addition"
RUNS_DIR = ROOT / "runs" / "m191_faithful_systematic_addition"
DOC_PATH = ROOT / "docs" / "m191_faithful_systematic_addition_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m191_faithful_systematic_addition_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 191000
MODEL_CONFIG = "arithmetic_3m"
POSITION_ENCODING = "relative"
NUMERIC_TOKENIZATION = "digit_safe"
BATCH_SIZE = 8

BASELINE_TRAIN_SIZES = (3000, 10000, 30000)
BASELINE_STEPS = 20000
LOCAL_STEPS = 5000
CURRICULUM_STAGE_STEPS = 5000
BASELINE_SEQUENCE_LENGTH = 256
LOCAL_SEQUENCE_LENGTH = 128
TRACE_SEQUENCE_LENGTH = 768
EVAL_PER_SPLIT = 60
ID_EVAL_COUNT = 300
RANGE_OOD_COUNT = 120

HOLDOUT_DIGIT_PAIRS = {
    (7, 5),
    (8, 6),
    (2, 9),
    (4, 7),
    (9, 8),
    (1, 6),
}
HOLDOUT_DIGIT_PAIR_KEYS = HOLDOUT_DIGIT_PAIRS | {(b, a) for a, b in HOLDOUT_DIGIT_PAIRS}

Variant = Literal["answer_control", "rfft", "turing", "rfft_aligned", "turing_aligned"]
StageName = Literal[
    "stage_a_1digit", "stage_b_1_2digit", "stage_c_1_3digit", "stage_d_1_5digit"
]

GENERIC_RFFT_RULE = (
    "RULE ADD:\n"
    "R1 process least-significant remaining digits\n"
    "R2 compute a_digit + b_digit + carry\n"
    "R3 output mod 10\n"
    "R4 new carry = floor(sum/10)\n"
    "R5 move left\n"
    "R6 repeat until finished"
)


@dataclass(frozen=True)
class AddCase:
    a: int
    b: int
    width: int | None = None

    @property
    def result(self) -> int:
        return self.a + self.b

    @property
    def digits(self) -> int:
        return self.width or max(len(str(self.a)), len(str(self.b)))

    @property
    def key(self) -> str:
        return f"{self.a}+{self.b}"

    @property
    def prompt(self) -> str:
        return f"ADD {self.a} + {self.b}"

    @property
    def local_pairs(self) -> tuple[tuple[int, int], ...]:
        a_digits = str(self.a).zfill(self.digits)
        b_digits = str(self.b).zfill(self.digits)
        return tuple((int(a), int(b)) for a, b in zip(a_digits, b_digits, strict=True))

    @property
    def local_states(self) -> tuple[tuple[int, int, int], ...]:
        carry = 0
        states: list[tuple[int, int, int]] = []
        for a_digit, b_digit in reversed(self.local_pairs):
            states.append((a_digit, b_digit, carry))
            carry = (a_digit + b_digit + carry) // 10
        return tuple(states)

    @property
    def has_heldout_pair(self) -> bool:
        return any(pair in HOLDOUT_DIGIT_PAIR_KEYS for pair in self.local_pairs)


@dataclass(frozen=True)
class TrainSpec:
    name: str
    variant: Variant
    train_path: Path
    eval_path: Path
    steps: int
    sequence_length: int
    seed: int
    init_checkpoint_path: Path | None = None


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-baselines")
    subparsers.add_parser("run-local")
    subparsers.add_parser("run-rfft")
    subparsers.add_parser("run-turing")
    subparsers.add_parser("run-format-controls")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-baselines":
        run_baselines()
    elif args.command == "run-local":
        run_local_transition()
    elif args.command == "run-rfft":
        run_curriculum("rfft")
    elif args.command == "run-turing":
        run_curriculum("turing")
    elif args.command == "run-format-controls":
        run_format_controls()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_baselines()
        run_local_transition()
        run_curriculum("rfft")
        run_curriculum("turing")
        run_format_controls()
        analyze_all()
        build_report(checks_passed=False)
    else:
        raise AssertionError(args.command)
    return 0


def prepare_datasets() -> None:
    if DATASET_DIR.exists():
        shutil.rmtree(DATASET_DIR)
    rng = random.Random(SEED)

    two_digit_cases = [
        AddCase(a=a, b=b, width=2)
        for a in range(10, 70)
        for b in range(10, 70)
        if not AddCase(a=a, b=b, width=2).has_heldout_pair
    ]
    rng.shuffle(two_digit_cases)
    id_eval_cases = two_digit_cases[:ID_EVAL_COUNT]
    train_pool = two_digit_cases[ID_EVAL_COUNT:]
    train_pair_set = _pair_set(train_pool)
    train_keys = {case.key for case in train_pool}
    id_eval_cases = [
        case for case in id_eval_cases if set(case.local_pairs) <= train_pair_set
    ][:240]
    _assert_id_split(train_pool, id_eval_cases)

    for train_size in BASELINE_TRAIN_SIZES:
        records = _records_for_cases(
            _balanced_replay(
                train_pool, train_size, rng=random.Random(SEED + train_size)
            ),
            variant="answer_control",
            split=f"baseline_train_{train_size}",
        )
        _write_jsonl(DATASET_DIR / "baseline" / f"train_{train_size}.jsonl", records)
    _write_jsonl(
        DATASET_DIR / "eval" / "clean_id.jsonl",
        _records_for_cases(id_eval_cases, variant="answer_control", split="clean_id"),
    )

    digit_pair_ood = _take_cases(
        _all_2digit_cases(require_heldout=True),
        count=240,
        seed=SEED + 10,
    )
    range_ood = _generate_range_ood_cases(
        count=RANGE_OOD_COUNT,
        allowed_pairs=train_pair_set,
        rng=random.Random(SEED + 11),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "digit_pair_ood.jsonl",
        _records_for_cases(
            digit_pair_ood, variant="answer_control", split="digit_pair_ood"
        ),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "range_ood.jsonl",
        _records_for_cases(range_ood, variant="answer_control", split="range_ood"),
    )
    for digits in (1, 2, 3, 4, 5, 6, 8, 10, 12):
        cases = _generate_supported_cases(
            count=EVAL_PER_SPLIT,
            digits=digits,
            allowed_pairs=train_pair_set,
            rng=random.Random(SEED + 100 + digits),
            exclude_keys=train_keys,
        )
        _write_jsonl(
            DATASET_DIR / "eval" / f"length_{digits}.jsonl",
            _records_for_cases(
                cases, variant="answer_control", split=f"length_{digits}"
            ),
        )

    _prepare_local_transition_datasets()
    for variant in ("rfft", "turing", "rfft_aligned", "turing_aligned"):
        _prepare_curriculum_datasets(variant, train_pair_set)

    _write_manifest(train_pool=train_pool, id_eval_cases=id_eval_cases)


def run_baselines() -> None:
    for index, train_size in enumerate(BASELINE_TRAIN_SIZES):
        spec = TrainSpec(
            name=f"baseline_{train_size}",
            variant="answer_control",
            train_path=DATASET_DIR / "baseline" / f"train_{train_size}.jsonl",
            eval_path=DATASET_DIR / "eval" / "clean_id.jsonl",
            steps=BASELINE_STEPS,
            sequence_length=BASELINE_SEQUENCE_LENGTH,
            seed=SEED + 1000 + index,
        )
        _train_and_eval(spec, eval_splits=_baseline_eval_splits())
    analyze_all()
    build_report(checks_passed=False)


def run_local_transition() -> None:
    spec = TrainSpec(
        name="local_transition_200",
        variant="answer_control",
        train_path=DATASET_DIR / "local_transition" / "train_all_200.jsonl",
        eval_path=DATASET_DIR / "local_transition" / "eval_all_200.jsonl",
        steps=LOCAL_STEPS,
        sequence_length=LOCAL_SEQUENCE_LENGTH,
        seed=SEED + 2000,
    )
    _train_and_eval(
        spec,
        eval_splits={
            "transition_train": DATASET_DIR / "local_transition" / "eval_all_200.jsonl",
            "transition_template_heldout": DATASET_DIR
            / "local_transition"
            / "eval_template_heldout.jsonl",
        },
        max_new_tokens=24,
    )
    analyze_all()
    build_report(checks_passed=False)


def run_curriculum(variant: Literal["rfft", "turing"]) -> None:
    _run_curriculum_variant(variant)
    analyze_all()
    build_report(checks_passed=False)


def run_format_controls() -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    best = _best_algorithmic_variant(analysis)
    if best not in {"rfft", "turing"}:
        return
    aligned = "rfft_aligned" if best == "rfft" else "turing_aligned"
    _run_curriculum_variant(aligned)
    analyze_all()
    build_report(checks_passed=False)


def analyze_all() -> None:
    payload = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "runs": {},
        "gates": {},
        "decision": "F - cannot reach clean ID >= .98; no OOD claim allowed",
    }
    for run_dir in sorted(RUNS_DIR.glob("*")):
        if not run_dir.is_dir():
            continue
        payload["runs"][run_dir.name] = _analyze_run(run_dir)
    payload["gates"] = _gate_summary(payload["runs"])
    payload["decision"] = _decision(payload)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    lines = [
        "# M-19.1 Faithful Systematic Addition Report",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        f"- device: `{_device_name(analysis)}`",
        "",
        "## M-19 Methodology Audit",
        "",
        "- M-19 clean in_range mixed the held-out digit-pair axis; M-19.1 clean ID excludes held-out digit pairs and asserts ID pairs are covered by train.",
        "- M-19 RFFT put the rule text only in the target. M-19.1 puts the generic rule in the input for faithful rule following.",
        "- M-19 length results were zero-shot 2-to-long extrapolation. M-19.1 uses staged 1, 1-2, 1-3, and 1-5 digit training.",
        "- M-19 state_machine did not preserve a persistent copied state. M-19.1 Turing traces copy full A/B/O/C/H state and apply local edits.",
        "",
        "## Corrected Split Verification",
        "",
        _split_table(analysis),
        "",
        "## Saturated ID Baseline",
        "",
        _baseline_table(analysis),
        "",
        "## Local 200-State Transition Test",
        "",
        _local_table(analysis),
        "",
        "## Faithful RFFT",
        "",
        _curriculum_table(analysis, "rfft"),
        "",
        "## Faithful Turing Program",
        "",
        _curriculum_table(analysis, "turing"),
        "",
        "## Real Length Curriculum",
        "",
        _length_curriculum_table(analysis),
        "",
        "## Format Controls",
        "",
        _format_control_table(analysis),
        "",
        "## Optional Verified Self-Improvement",
        "",
        _verified_self_improvement_status(analysis),
        "",
        "## Capacity Sweep",
        "",
        _capacity_status(analysis),
        "",
        "## Recommendation",
        "",
        str(analysis.get("decision", "unknown")),
        "",
    ]
    text = "\n".join(lines)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def _run_curriculum_variant(variant: Variant) -> None:
    previous_checkpoint: Path | None = None
    for stage_index, (stage, _lengths) in enumerate(_curriculum_stages().items()):
        train_path = DATASET_DIR / "curriculum" / variant / f"{stage}.jsonl"
        spec = TrainSpec(
            name=f"{variant}_{stage}",
            variant=variant,
            train_path=train_path,
            eval_path=DATASET_DIR / "curriculum" / variant / "eval_length_2.jsonl",
            steps=CURRICULUM_STAGE_STEPS,
            sequence_length=TRACE_SEQUENCE_LENGTH,
            seed=SEED + 3000 + stage_index,
            init_checkpoint_path=previous_checkpoint,
        )
        _train_and_eval(
            spec,
            eval_splits=_curriculum_eval_splits(variant),
            max_new_tokens=_max_new_tokens(variant),
        )
        previous_checkpoint = _checkpoint_path(RUNS_DIR / spec.name, spec.steps)


def _train_and_eval(
    spec: TrainSpec,
    *,
    eval_splits: dict[str, Path],
    max_new_tokens: int | None = None,
) -> None:
    output_dir = RUNS_DIR / spec.name
    checkpoint = _checkpoint_path(output_dir, spec.steps)
    if checkpoint.exists():
        result = {
            "status": "reused_existing_checkpoint",
            "checkpoint_path": str(checkpoint),
        }
    else:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        result = train_lm(
            TrainConfig(
                train_path=spec.train_path,
                eval_path=spec.eval_path,
                tokenizer_path=TOKENIZER_PATH,
                output_dir=output_dir,
                model_config_name=MODEL_CONFIG,
                steps=spec.steps,
                batch_size=BATCH_SIZE,
                sequence_length=spec.sequence_length,
                loss_mode="answer-only",
                numeric_tokenization=NUMERIC_TOKENIZATION,
                position_encoding=POSITION_ENCODING,
                segment_attention_mode="flat_causal",
                seed=spec.seed,
                eval_every=max(spec.steps // 4, 1),
                eval_batches=20,
                save_every=max(spec.steps // 4, 1),
                init_checkpoint_path=spec.init_checkpoint_path,
            )
        )
        checkpoint = _checkpoint_path(output_dir, spec.steps)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    for name, path in eval_splits.items():
        if (output_dir / "benchmark" / name / "summary.json").exists():
            continue
        _evaluate_checkpoint(
            checkpoint_path=checkpoint,
            eval_path=path,
            output_dir=output_dir / "benchmark" / name,
            variant=spec.variant,
            max_new_tokens=max_new_tokens or _max_new_tokens(spec.variant),
        )


def _evaluate_checkpoint(
    *,
    checkpoint_path: Path,
    eval_path: Path,
    output_dir: Path,
    variant: Variant,
    max_new_tokens: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    device_info = get_device_info()
    model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=TOKENIZER_PATH,
        device=device_info.device,
    )
    predictions = []
    for index, record in enumerate(_read_jsonl(eval_path)):
        generated_ids = generate_answer_ids(
            model=model,
            tokenizer=tokenizer,
            prompt=str(record["prompt"]),
            max_new_tokens=max_new_tokens,
            device=device_info.device,
            numeric_tokenization=NUMERIC_TOKENIZATION,
        )
        raw_generation = tokenizer.decode(generated_ids, skip_special_tokens=False)
        predictions.append(
            _prediction_payload(
                record=record,
                index=index,
                raw_generation=raw_generation,
                generated_ids=generated_ids,
                variant=variant,
            )
        )
    summary = _summarize(predictions)
    summary.update(
        {
            "eval_path": str(eval_path),
            "checkpoint_path": str(checkpoint_path),
            "checkpoint_step": checkpoint.get("step"),
            "device": str(device_info.device),
            "device_name": device_info.name,
            "variant": variant,
            "max_new_tokens": max_new_tokens,
        }
    )
    _write_jsonl(output_dir / "predictions.jsonl", predictions)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _prediction_payload(
    *,
    record: dict[str, Any],
    index: int,
    raw_generation: str,
    generated_ids: list[int],
    variant: Variant,
) -> dict[str, Any]:
    predicted = extract_generated_answer(raw_generation)
    expected = str(record["answer"])
    final_expected = extract_final_answer(expected)
    final_predicted = extract_final_answer(predicted)
    exact = normalize_answer(predicted) == normalize_answer(expected)
    final_exact = (
        exact
        if record["metadata"].get("kind") == "local_transition"
        else normalize_final_answer(final_predicted)
        == normalize_final_answer(final_expected)
    )
    return {
        "id": str(record.get("id", f"m191:{index}")),
        "task_type": str(record["task_type"]),
        "prompt": str(record["prompt"]),
        "expected": expected,
        "predicted": predicted,
        "raw_generation": raw_generation,
        "tokens_generated": len(generated_ids),
        "normalized_exact_match": exact,
        "final_expected": final_expected,
        "final_predicted": final_predicted,
        "final_normalized_exact_match": final_exact,
        "full_trace_exact": exact,
        "transition_exact": _transition_exact(expected, predicted, variant),
        "metadata": record.get("metadata", {}),
    }


def _summarize(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(predictions)
    if count == 0:
        return {"overall": _metric_payload([]), "by_task_type": {}}
    by_task_type = {}
    for task_type in sorted({str(p["task_type"]) for p in predictions}):
        by_task_type[task_type] = _metric_payload(
            [p for p in predictions if p["task_type"] == task_type]
        )
    by_length = {}
    for length in sorted({int(p["metadata"].get("digits", 0)) for p in predictions}):
        by_length[str(length)] = _metric_payload(
            [p for p in predictions if int(p["metadata"].get("digits", 0)) == length]
        )
    return {
        "overall": _metric_payload(predictions),
        "by_task_type": by_task_type,
        "by_length": by_length,
    }


def _metric_payload(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(predictions)
    if count == 0:
        return {
            "count": 0,
            "final_normalized_exact_match": 0.0,
            "normalized_exact_match": 0.0,
            "full_trace_exact": 0.0,
            "transition_exact": None,
            "empty_prediction_rate": 0.0,
            "avg_tokens_generated": 0.0,
        }
    transition_predictions = [
        p for p in predictions if p.get("transition_exact") is not None
    ]
    return {
        "count": count,
        "final_normalized_exact_match": sum(
            bool(p["final_normalized_exact_match"]) for p in predictions
        )
        / count,
        "normalized_exact_match": sum(
            bool(p["normalized_exact_match"]) for p in predictions
        )
        / count,
        "full_trace_exact": sum(bool(p["full_trace_exact"]) for p in predictions)
        / count,
        "transition_exact": (
            None
            if not transition_predictions
            else sum(bool(p["transition_exact"]) for p in transition_predictions)
            / len(transition_predictions)
        ),
        "empty_prediction_rate": sum(
            not str(p["predicted"]).strip() for p in predictions
        )
        / count,
        "avg_tokens_generated": sum(float(p["tokens_generated"]) for p in predictions)
        / count,
    }


def _records_for_cases(
    cases: list[AddCase],
    *,
    variant: Variant,
    split: str,
) -> list[dict[str, Any]]:
    return [
        _record_for_case(case, variant=variant, split=split, index=index)
        for index, case in enumerate(cases)
    ]


def _record_for_case(
    case: AddCase,
    *,
    variant: Variant,
    split: str,
    index: int,
) -> dict[str, Any]:
    prompt = _prompt_for_case(case, variant)
    answer = _answer_for_case(case, variant)
    bucket = _addition_bucket(case)
    return {
        "id": f"m191.{split}.{variant}.{index:06d}.{case.a}.{case.b}",
        "task_type": f"m191.add.{variant}.{bucket}",
        "prompt": prompt,
        "answer": answer,
        "metadata": {
            "kind": "addition",
            "split": split,
            "variant": variant,
            "a": case.a,
            "b": case.b,
            "result": case.result,
            "digits": case.digits,
            "result_digits": len(str(case.result)),
            "bucket": bucket,
            "local_pairs": [list(pair) for pair in case.local_pairs],
            "local_states": [list(state) for state in case.local_states],
            "has_heldout_pair": case.has_heldout_pair,
        },
    }


def _prompt_for_case(case: AddCase, variant: Variant) -> str:
    if variant == "answer_control":
        return case.prompt
    problem = _aligned_problem(case) if variant.endswith("_aligned") else case.prompt
    if variant.startswith("rfft"):
        return "\n".join(
            (
                GENERIC_RFFT_RULE,
                "",
                f"PROBLEM: {problem}",
                "",
                "INSTRUCTION: Recite the relevant rule steps and execute them.",
            )
        )
    return "\n".join(
        (
            "TURING PROGRAM ADD:",
            "Copy the full state at every step and edit only O, C, and H.",
            f"PROBLEM: {problem}",
            "INSTRUCTION: Execute the machine state transitions.",
        )
    )


def _answer_for_case(case: AddCase, variant: Variant) -> str:
    if variant == "answer_control":
        return f"FINAL {case.result}"
    if variant.startswith("rfft"):
        return _rfft_execution(case)
    return _turing_execution(case)


def _aligned_problem(case: AddCase) -> str:
    a = " ".join(reversed(str(case.a).zfill(case.digits)))
    b = " ".join(reversed(str(case.b).zfill(case.digits)))
    return f"ADD_LSD_FIRST A {a} B {b}"


def _rfft_execution(case: AddCase) -> str:
    carry = 0
    out_lsd: list[int] = []
    lines = ["EXECUTE ADD"]
    for index, (a_digit, b_digit, _carry_in) in enumerate(case.local_states):
        total = a_digit + b_digit + carry
        out_digit = total % 10
        next_carry = total // 10
        out_lsd.append(out_digit)
        lines.extend(
            (
                f"STEP {index} USE R1 R2 R3 R4 R5",
                f"DIGITS {a_digit} {b_digit} CARRY_IN {carry}",
                f"SUM {total}",
                f"WRITE {out_digit}",
                f"CARRY_OUT {next_carry}",
            )
        )
        carry = next_carry
    if carry:
        out_lsd.append(carry)
        lines.extend(
            (
                f"STEP {len(case.local_states)} USE R6 FINAL_CARRY",
                "DIGITS 0 0 CARRY_IN 1",
                "SUM 1",
                "WRITE 1",
                "CARRY_OUT 0",
            )
        )
    lines.append(f"FINAL {_digits_to_int_lsd(out_lsd)}")
    return "\n".join(lines)


def _turing_execution(case: AddCase) -> str:
    a_digits = [int(char) for char in str(case.a).zfill(case.digits)]
    b_digits = [int(char) for char in str(case.b).zfill(case.digits)]
    out_slots = ["_"] * (case.digits + 1)
    carry = 0
    head = case.digits - 1
    lines = ["STATE 0", *_state_lines(a_digits, b_digits, out_slots, carry, head)]
    for step, (a_digit, b_digit, _carry_in) in enumerate(case.local_states, start=1):
        total = a_digit + b_digit + carry
        out_digit = total % 10
        next_carry = total // 10
        out_slots[head + 1] = str(out_digit)
        lines.append(f"ACT {a_digit} {b_digit} C{carry} -> {out_digit} C{next_carry}")
        carry = next_carry
        head -= 1
        lines.append(f"STATE {step}")
        lines.extend(_state_lines(a_digits, b_digits, out_slots, carry, head))
    if carry:
        out_slots[0] = str(carry)
        lines.append("ACT FC C1 -> 1 C0")
        carry = 0
        lines.append(f"STATE {len(case.local_states) + 1}")
        lines.extend(_state_lines(a_digits, b_digits, out_slots, carry, -1))
    lines.append(f"FINAL {case.result}")
    return "\n".join(lines)


def _state_lines(
    a_digits: list[int],
    b_digits: list[int],
    out_slots: list[str],
    carry: int,
    head: int,
) -> list[str]:
    return [
        "A " + "".join(str(digit) for digit in a_digits),
        "B " + "".join(str(digit) for digit in b_digits),
        "O " + "".join(out_slots),
        f"C {carry}",
        f"H {head if head >= 0 else 'D'}",
    ]


def _prepare_local_transition_datasets() -> None:
    states = [(a, b, carry) for a in range(10) for b in range(10) for carry in range(2)]
    train_records = []
    for repeat in range(50):
        for index, (a, b, carry) in enumerate(states):
            train_records.append(
                _local_transition_record(
                    a=a,
                    b=b,
                    carry=carry,
                    split="train",
                    index=repeat * len(states) + index,
                    template="standard",
                )
            )
    eval_records = [
        _local_transition_record(
            a=a,
            b=b,
            carry=carry,
            split="eval_all_200",
            index=index,
            template="standard",
        )
        for index, (a, b, carry) in enumerate(states)
    ]
    heldout_records = [
        _local_transition_record(
            a=a,
            b=b,
            carry=carry,
            split="eval_template_heldout",
            index=index,
            template="heldout",
        )
        for index, (a, b, carry) in enumerate(states)
    ]
    _write_jsonl(
        DATASET_DIR / "local_transition" / "train_all_200.jsonl", train_records
    )
    _write_jsonl(DATASET_DIR / "local_transition" / "eval_all_200.jsonl", eval_records)
    _write_jsonl(
        DATASET_DIR / "local_transition" / "eval_template_heldout.jsonl",
        heldout_records,
    )


def _local_transition_record(
    *,
    a: int,
    b: int,
    carry: int,
    split: str,
    index: int,
    template: str,
) -> dict[str, Any]:
    total = a + b + carry
    out_digit = total % 10
    carry_out = total // 10
    prompt = (
        f"ADD_LOCAL a={a} b={b} carry={carry}"
        if template == "standard"
        else f"LOCAL_RULE ADD_DIGIT {a} {b} C{carry}"
    )
    return {
        "id": f"m191.local.{split}.{index:04d}.{a}.{b}.{carry}",
        "task_type": "m191.local_transition.add",
        "prompt": prompt,
        "answer": f"OUT {out_digit} CARRY {carry_out}",
        "metadata": {
            "kind": "local_transition",
            "split": split,
            "a_digit": a,
            "b_digit": b,
            "carry_in": carry,
            "out_digit": out_digit,
            "carry_out": carry_out,
            "digits": 1,
            "template": template,
        },
    }


def _prepare_curriculum_datasets(
    variant: str, train_pair_set: set[tuple[int, int]]
) -> None:
    for stage_index, (stage, lengths) in enumerate(_curriculum_stages().items()):
        cases = []
        per_length = 2000
        for length in lengths:
            cases.extend(
                _generate_supported_cases(
                    count=per_length,
                    digits=length,
                    allowed_pairs=train_pair_set,
                    rng=random.Random(SEED + 4000 + stage_index * 100 + length),
                    allow_repeats=True,
                )
            )
        _write_jsonl(
            DATASET_DIR / "curriculum" / variant / f"{stage}.jsonl",
            _records_for_cases(cases, variant=variant, split=stage),
        )
    for digits in (1, 2, 3, 4, 5, 6, 8, 10, 12):
        cases = _generate_supported_cases(
            count=EVAL_PER_SPLIT,
            digits=digits,
            allowed_pairs=train_pair_set,
            rng=random.Random(SEED + 5000 + digits),
        )
        _write_jsonl(
            DATASET_DIR / "curriculum" / variant / f"eval_length_{digits}.jsonl",
            _records_for_cases(cases, variant=variant, split=f"eval_length_{digits}"),
        )
    digit_pair_ood = _take_cases(
        _all_2digit_cases(require_heldout=True),
        count=EVAL_PER_SPLIT,
        seed=SEED + 5010,
    )
    _write_jsonl(
        DATASET_DIR / "curriculum" / variant / "eval_digit_pair_ood.jsonl",
        _records_for_cases(
            digit_pair_ood, variant=variant, split="eval_digit_pair_ood"
        ),
    )


def _curriculum_stages() -> dict[StageName, tuple[int, ...]]:
    return {
        "stage_a_1digit": (1,),
        "stage_b_1_2digit": (1, 2),
        "stage_c_1_3digit": (1, 2, 3),
        "stage_d_1_5digit": (1, 2, 3, 4, 5),
    }


def _baseline_eval_splits() -> dict[str, Path]:
    return {
        "clean_id": DATASET_DIR / "eval" / "clean_id.jsonl",
        "digit_pair_ood": DATASET_DIR / "eval" / "digit_pair_ood.jsonl",
        "range_ood": DATASET_DIR / "eval" / "range_ood.jsonl",
        "length_3": DATASET_DIR / "eval" / "length_3.jsonl",
    }


def _curriculum_eval_splits(variant: Variant) -> dict[str, Path]:
    root = DATASET_DIR / "curriculum" / variant
    result = {
        f"length_{digits}": root / f"eval_length_{digits}.jsonl"
        for digits in (1, 2, 3, 4, 5, 6, 8, 10, 12)
    }
    result["digit_pair_ood"] = root / "eval_digit_pair_ood.jsonl"
    return result


def _write_manifest(*, train_pool: list[AddCase], id_eval_cases: list[AddCase]) -> None:
    manifest = {
        "kind": "m191_faithful_systematic_addition",
        "seed": SEED,
        "model_config": MODEL_CONFIG,
        "position_encoding": POSITION_ENCODING,
        "numeric_tokenization": NUMERIC_TOKENIZATION,
        "holdout_digit_pairs": sorted(HOLDOUT_DIGIT_PAIRS),
        "holdout_digit_pair_keys": sorted(HOLDOUT_DIGIT_PAIR_KEYS),
        "train_pair_count": len(_pair_set(train_pool)),
        "id_pair_subset_of_train": _pair_set(id_eval_cases) <= _pair_set(train_pool),
        "splits": {
            "train_pool": _audit_cases(train_pool),
            "clean_id": _audit_cases(id_eval_cases),
            "digit_pair_ood": _audit_records(
                DATASET_DIR / "eval" / "digit_pair_ood.jsonl"
            ),
            "range_ood": _audit_records(DATASET_DIR / "eval" / "range_ood.jsonl"),
            **{
                f"length_{digits}": _audit_records(
                    DATASET_DIR / "eval" / f"length_{digits}.jsonl"
                )
                for digits in (1, 2, 3, 4, 5, 6, 8, 10, 12)
            },
        },
        "prompt_intersections": _prompt_intersections(),
    }
    _assert_manifest(manifest)
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _all_2digit_cases(*, require_heldout: bool) -> list[AddCase]:
    cases = []
    for a in range(10, 70):
        for b in range(10, 70):
            case = AddCase(a=a, b=b, width=2)
            if case.has_heldout_pair == require_heldout:
                cases.append(case)
    return cases


def _generate_supported_cases(
    *,
    count: int,
    digits: int,
    allowed_pairs: set[tuple[int, int]],
    rng: random.Random,
    min_value: int | None = None,
    max_value: int | None = None,
    allow_repeats: bool = False,
    exclude_keys: set[str] | None = None,
) -> list[AddCase]:
    cases: list[AddCase] = []
    used: set[str] = set()
    attempts = 0
    pairs = sorted(allowed_pairs - HOLDOUT_DIGIT_PAIR_KEYS)
    while len(cases) < count:
        attempts += 1
        if attempts > count * 5000:
            raise RuntimeError(
                f"Could not generate {count} supported {digits}-digit cases"
            )
        local_pairs = [rng.choice(pairs) for _ in range(digits)]
        if digits > 1 and (local_pairs[0][0] == 0 or local_pairs[0][1] == 0):
            local_pairs[0] = rng.choice(
                [pair for pair in pairs if pair[0] != 0 and pair[1] != 0]
            )
        a = int("".join(str(pair[0]) for pair in local_pairs))
        b = int("".join(str(pair[1]) for pair in local_pairs))
        if min_value is not None and (a < min_value or b < min_value):
            continue
        if max_value is not None and (a > max_value or b > max_value):
            continue
        case = AddCase(a=a, b=b, width=digits)
        if exclude_keys and case.key in exclude_keys:
            continue
        if not allow_repeats and case.key in used:
            continue
        used.add(case.key)
        cases.append(case)
    return cases


def _generate_range_ood_cases(
    *,
    count: int,
    allowed_pairs: set[tuple[int, int]],
    rng: random.Random,
) -> list[AddCase]:
    cases: list[AddCase] = []
    used: set[str] = set()
    allowed = allowed_pairs - HOLDOUT_DIGIT_PAIR_KEYS
    attempts = 0
    while len(cases) < count:
        attempts += 1
        if attempts > count * 5000:
            raise RuntimeError("Could not generate range OOD cases")
        a = rng.randint(70, 89)
        b = rng.randint(10, 19)
        if a + b >= 100:
            continue
        case = AddCase(a=a, b=b, width=2)
        if case.key in used:
            continue
        if not set(case.local_pairs) <= allowed:
            continue
        used.add(case.key)
        cases.append(case)
    return cases


def _take_cases(cases: list[AddCase], *, count: int, seed: int) -> list[AddCase]:
    rng = random.Random(seed)
    shuffled = list(cases)
    rng.shuffle(shuffled)
    if len(shuffled) < count:
        return [shuffled[index % len(shuffled)] for index in range(count)]
    return shuffled[:count]


def _balanced_replay(
    cases: list[AddCase], count: int, *, rng: random.Random
) -> list[AddCase]:
    shuffled = list(cases)
    rng.shuffle(shuffled)
    return [shuffled[index % len(shuffled)] for index in range(count)]


def _pair_set(cases: list[AddCase]) -> set[tuple[int, int]]:
    return {pair for case in cases for pair in case.local_pairs}


def _assert_id_split(train_pool: list[AddCase], id_eval_cases: list[AddCase]) -> None:
    train_keys = {case.key for case in train_pool}
    id_keys = {case.key for case in id_eval_cases}
    if train_keys & id_keys:
        raise AssertionError("clean ID eval must be prompt-disjoint from train pool")
    if not (_pair_set(id_eval_cases) <= _pair_set(train_pool)):
        raise AssertionError("clean ID digit-pair set must be covered by train")
    if any(case.has_heldout_pair for case in id_eval_cases):
        raise AssertionError("clean ID eval must not contain held-out digit pairs")


def _assert_manifest(manifest: dict[str, Any]) -> None:
    if not manifest["id_pair_subset_of_train"]:
        raise AssertionError("ID digit-pair set is not a subset of train")
    digit_pair_ood = manifest["splits"]["digit_pair_ood"]
    if digit_pair_ood["heldout_pair_count"] <= 0:
        raise AssertionError("digit_pair_OOD must contain held-out digit pairs")
    if max(manifest["prompt_intersections"].values()) != 0:
        raise AssertionError("prompt intersections must be zero")


def _audit_cases(cases: list[AddCase]) -> dict[str, Any]:
    pairs = _pair_set(cases)
    return {
        "count": len(cases),
        "operand_range": _range_text(
            [case.a for case in cases] + [case.b for case in cases]
        ),
        "digit_lengths": dict(Counter(str(case.digits) for case in cases)),
        "result_lengths": dict(Counter(str(len(str(case.result))) for case in cases)),
        "buckets": dict(Counter(_addition_bucket(case) for case in cases)),
        "digit_pair_count": len(pairs),
        "heldout_pair_count": sum(
            1
            for case in cases
            if any(pair in HOLDOUT_DIGIT_PAIR_KEYS for pair in case.local_pairs)
        ),
        "train_supported_pair_overlap": len(pairs),
    }


def _audit_records(path: Path) -> dict[str, Any]:
    return _audit_cases(
        [
            AddCase(
                a=int(record["metadata"]["a"]),
                b=int(record["metadata"]["b"]),
                width=int(record["metadata"]["digits"]),
            )
            for record in _read_jsonl(path)
            if record.get("metadata", {}).get("kind") == "addition"
        ]
    )


def _addition_bucket(case: AddCase) -> str:
    carry = 0
    internal_carry = False
    for a_digit, b_digit, _carry_in in case.local_states:
        total = a_digit + b_digit + carry
        next_carry = total // 10
        internal_carry = internal_carry or bool(next_carry)
        carry = next_carry
    if len(str(case.result)) > case.digits:
        return "final_overflow"
    if internal_carry:
        return "internal_carry"
    return "no_carry"


def _transition_exact(expected: str, predicted: str, variant: Variant) -> bool | None:
    if variant == "answer_control":
        return None
    expected_lines = _transition_lines(expected, variant)
    predicted_lines = _transition_lines(predicted, variant)
    return predicted_lines == expected_lines


def _transition_lines(text: str, variant: Variant) -> list[str]:
    prefixes = (
        ("STEP ", "DIGITS ", "SUM ", "WRITE ", "CARRY_OUT ")
        if variant.startswith("rfft")
        else ("STATE ", "A ", "B ", "O ", "C ", "H ", "ACT ")
    )
    return [
        line.strip()
        for line in text.strip().splitlines()
        if line.strip().startswith(prefixes)
    ]


def _digits_to_int_lsd(digits: list[int]) -> int:
    return int("".join(str(digit) for digit in reversed(digits)).lstrip("0") or "0")


def _max_new_tokens(variant: Variant) -> int:
    if variant == "answer_control":
        return 24
    if variant.startswith("rfft"):
        return 640
    return 760


def _checkpoint_path(output_dir: Path, step: int) -> Path:
    return output_dir / "checkpoints" / f"step_{step:06d}.pt"


def _analyze_run(run_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "metrics": _read_jsonl(run_dir / "metrics.jsonl")
        if (run_dir / "metrics.jsonl").exists()
        else [],
        "benchmarks": {},
        "train_config": _read_json_if_exists(run_dir / "train_config.json"),
    }
    for summary_path in sorted((run_dir / "benchmark").glob("*/summary.json")):
        result["benchmarks"][summary_path.parent.name] = _summary_payload(
            _read_json(summary_path)
        )
    return result


def _summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    overall = summary.get("overall", {})
    return {
        "count": int(overall.get("count", 0)),
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "full_nem": float(overall.get("normalized_exact_match", 0.0)),
        "trace_exact": float(overall.get("full_trace_exact", 0.0)),
        "transition_exact": _optional_float(overall.get("transition_exact")),
        "empty_rate": float(overall.get("empty_prediction_rate", 0.0)),
        "avg_tokens": float(overall.get("avg_tokens_generated", 0.0)),
        "summary": summary,
    }


def _gate_summary(runs: dict[str, Any]) -> dict[str, Any]:
    best_clean = max(
        (
            run.get("benchmarks", {}).get("clean_id", {}).get("final_nem", 0.0)
            for name, run in runs.items()
            if name.startswith("baseline_")
        ),
        default=0.0,
    )
    rfft_stage_d = runs.get("rfft_stage_d_1_5digit", {}).get("benchmarks", {})
    turing_stage_d = runs.get("turing_stage_d_1_5digit", {}).get("benchmarks", {})
    rfft_trained = _trained_length_fit(rfft_stage_d)
    turing_trained = _trained_length_fit(turing_stage_d)
    rfft_length_extrap = _length_extrapolation_fit(rfft_stage_d)
    turing_length_extrap = _length_extrapolation_fit(turing_stage_d)
    rfft_digit_ood = rfft_stage_d.get("digit_pair_ood", {}).get("final_nem", 0.0)
    turing_digit_ood = turing_stage_d.get("digit_pair_ood", {}).get("final_nem", 0.0)
    return {
        "clean_id_gate": best_clean >= 0.98,
        "best_clean_id": best_clean,
        "rfft_3digit_gate": rfft_stage_d.get("length_3", {}).get("final_nem", 0.0)
        >= 0.90,
        "turing_3digit_gate": turing_stage_d.get("length_3", {}).get("final_nem", 0.0)
        >= 0.90,
        "rfft_trained_1_5_gate": rfft_trained,
        "turing_trained_1_5_gate": turing_trained,
        "rfft_length_extrapolation_gate": rfft_length_extrap,
        "turing_length_extrapolation_gate": turing_length_extrap,
        "rfft_digit_pair_ood": rfft_digit_ood,
        "turing_digit_pair_ood": turing_digit_ood,
        "rfft_digit_pair_ood_gate": rfft_digit_ood >= 0.90,
        "turing_digit_pair_ood_gate": turing_digit_ood >= 0.90,
        "rfft_systematic_gate": rfft_trained
        and rfft_length_extrap
        and rfft_digit_ood >= 0.90,
        "turing_systematic_gate": turing_trained
        and turing_length_extrap
        and turing_digit_ood >= 0.90,
    }


def _decision(analysis: dict[str, Any]) -> str:
    gates = analysis.get("gates", {})
    if not gates.get("clean_id_gate", False):
        return "F - clean ID did not reach .98, so OOD interpretation is blocked; debug dataset/optimization first."
    rfft_systematic = gates.get("rfft_systematic_gate", False)
    turing_systematic = gates.get("turing_systematic_gate", False)
    if rfft_systematic and turing_systematic:
        return "C - both faithful RFFT and Turing Program pass length extrapolation and digit-pair OOD; prefer the faster representation."
    if rfft_systematic:
        return "A - faithful RFFT passes systematic OOD; adopt rule-following executor."
    if turing_systematic:
        return (
            "B - Turing Program passes systematic OOD; adopt state-transition executor."
        )
    if gates.get("rfft_trained_1_5_gate") or gates.get("turing_trained_1_5_gate"):
        return (
            "D - clean ID and trained 1-5 digit curriculum fit, but length extrapolation "
            "and held-out digit-pair OOD still fail. This is curriculum-length fitting, "
            "not faithful systematic addition generalization."
        )
    return "E - clean ID fits, but faithful curriculum variants did not even fit trained 1-5 digit lengths."


def _trained_length_fit(benches: dict[str, Any]) -> bool:
    return all(
        benches.get(f"length_{digits}", {}).get("final_nem", 0.0) >= 0.95
        for digits in (1, 2, 3, 4, 5)
    )


def _length_extrapolation_fit(benches: dict[str, Any]) -> bool:
    return all(
        benches.get(f"length_{digits}", {}).get("final_nem", 0.0) >= 0.90
        for digits in (6, 8, 10, 12)
    )


def _best_algorithmic_variant(analysis: dict[str, Any]) -> str:
    runs = analysis.get("runs", {})
    scores = {}
    for variant in ("rfft", "turing"):
        benchmarks = runs.get(f"{variant}_stage_d_1_5digit", {}).get("benchmarks", {})
        scores[variant] = sum(
            benchmarks.get(f"length_{digits}", {}).get("final_nem", 0.0)
            for digits in (3, 4, 5)
        )
    if not scores or max(scores.values(), default=0.0) == 0.0:
        return "none"
    return max(scores, key=scores.get)


def _split_table(analysis: dict[str, Any]) -> str:
    splits = analysis.get("manifest", {}).get("splits", {})
    rows = [
        "| split | count | range | digit lengths | result lengths | buckets | heldout pairs |",
        "|---|---:|---|---|---|---|---:|",
    ]
    for name, audit in splits.items():
        rows.append(
            f"| {name} | {audit.get('count', 0)} | {audit.get('operand_range', '')} | "
            f"{audit.get('digit_lengths', {})} | {audit.get('result_lengths', {})} | "
            f"{audit.get('buckets', {})} | {audit.get('heldout_pair_count', 0)} |"
        )
    prompt_intersections = analysis.get("manifest", {}).get("prompt_intersections", {})
    rows.extend(
        (
            "",
            f"Prompt intersections max: `{max(prompt_intersections.values(), default=0)}`.",
            f"ID pair subset of train: `{analysis.get('manifest', {}).get('id_pair_subset_of_train')}`.",
        )
    )
    return "\n".join(rows)


def _baseline_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| train size | train final loss | clean ID | digit-pair OOD | range OOD | length 3 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for size in BASELINE_TRAIN_SIZES:
        run = analysis.get("runs", {}).get(f"baseline_{size}", {})
        metrics = run.get("metrics", [])
        train_loss = metrics[-1].get("train_loss", 0.0) if metrics else 0.0
        benches = run.get("benchmarks", {})
        rows.append(
            f"| {size} | {train_loss:.6f} | {_bench(benches, 'clean_id'):.4f} | "
            f"{_bench(benches, 'digit_pair_ood'):.4f} | {_bench(benches, 'range_ood'):.4f} | "
            f"{_bench(benches, 'length_3'):.4f} |"
        )
    gate = analysis.get("gates", {}).get("clean_id_gate", False)
    rows.append(f"\nClean ID gate >= .98: `{gate}`.")
    return "\n".join(rows)


def _local_table(analysis: dict[str, Any]) -> str:
    run = analysis.get("runs", {}).get("local_transition_200", {})
    benches = run.get("benchmarks", {})
    return "\n".join(
        (
            "| eval | exact | avg tokens |",
            "|---|---:|---:|",
            f"| transition_train/all_200 | {_bench(benches, 'transition_train'):.4f} | {_avg_tokens(benches, 'transition_train'):.2f} |",
            f"| template_heldout/all_200 | {_bench(benches, 'transition_template_heldout'):.4f} | {_avg_tokens(benches, 'transition_template_heldout'):.2f} |",
        )
    )


def _curriculum_table(analysis: dict[str, Any], variant: str) -> str:
    rows = [
        "| stage | len1 | len2 | len3 | len4 | len5 | len6 | len8 | len10 | len12 | digit-pair OOD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for stage in _curriculum_stages():
        benches = (
            analysis.get("runs", {}).get(f"{variant}_{stage}", {}).get("benchmarks", {})
        )
        rows.append(
            f"| {stage} | "
            + " | ".join(
                f"{_bench(benches, f'length_{digits}'):.4f}"
                for digits in (1, 2, 3, 4, 5, 6, 8, 10, 12)
            )
            + f" | {_bench(benches, 'digit_pair_ood'):.4f} |"
        )
    return "\n".join(rows)


def _length_curriculum_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| variant | after 1 digit len1 | after 1-2 len2 | after 1-3 len3 | after 1-5 len5 | len8 | len12 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for variant in ("rfft", "turing"):
        runs = analysis.get("runs", {})
        rows.append(
            f"| {variant} | "
            f"{_bench(runs.get(f'{variant}_stage_a_1digit', {}).get('benchmarks', {}), 'length_1'):.4f} | "
            f"{_bench(runs.get(f'{variant}_stage_b_1_2digit', {}).get('benchmarks', {}), 'length_2'):.4f} | "
            f"{_bench(runs.get(f'{variant}_stage_c_1_3digit', {}).get('benchmarks', {}), 'length_3'):.4f} | "
            f"{_bench(runs.get(f'{variant}_stage_d_1_5digit', {}).get('benchmarks', {}), 'length_5'):.4f} | "
            f"{_bench(runs.get(f'{variant}_stage_d_1_5digit', {}).get('benchmarks', {}), 'length_8'):.4f} | "
            f"{_bench(runs.get(f'{variant}_stage_d_1_5digit', {}).get('benchmarks', {}), 'length_12'):.4f} |"
        )
    return "\n".join(rows)


def _format_control_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| variant | len3 | len5 | len8 | digit-pair OOD |",
        "|---|---:|---:|---:|---:|",
    ]
    for variant in ("rfft_aligned", "turing_aligned"):
        benches = (
            analysis.get("runs", {})
            .get(f"{variant}_stage_d_1_5digit", {})
            .get("benchmarks", {})
        )
        if benches:
            rows.append(
                f"| {variant} | {_bench(benches, 'length_3'):.4f} | "
                f"{_bench(benches, 'length_5'):.4f} | {_bench(benches, 'length_8'):.4f} | "
                f"{_bench(benches, 'digit_pair_ood'):.4f} |"
            )
    if len(rows) == 2:
        rows.append(
            "| skipped: no faithful variant passed systematic OOD gate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |"
        )
    return "\n".join(rows)


def _verified_self_improvement_status(analysis: dict[str, Any]) -> str:
    gates = analysis.get("gates", {})
    if gates.get("rfft_systematic_gate") or gates.get("turing_systematic_gate"):
        return "eligible: a faithful method passed systematic OOD; run only with an external verifier before adding generated samples."
    if gates.get("rfft_3digit_gate") or gates.get("turing_3digit_gate"):
        return (
            "skipped: 3-digit trained-length fit passed, but length extrapolation and/or "
            "digit-pair OOD failed, so self-generated samples would not be a faithful "
            "generalization signal."
        )
    return "skipped: no faithful method reached clean ID >= .98 and 3-digit >= .90."


def _capacity_status(analysis: dict[str, Any]) -> str:
    if not analysis.get("gates", {}).get("clean_id_gate", False):
        return "skipped: clean ID gate did not pass."
    if analysis.get("gates", {}).get("rfft_systematic_gate") or analysis.get(
        "gates", {}
    ).get("turing_systematic_gate"):
        return (
            "not needed for M-19.1: at least one faithful method passed systematic OOD."
        )
    return (
        "eligible for a separate follow-up: clean ID fits, but both faithful methods "
        "fail systematic OOD after fitting trained lengths. Do not treat this report "
        "as evidence for scaling alone."
    )


def _bench(benches: dict[str, Any], name: str) -> float:
    return float(benches.get(name, {}).get("final_nem", 0.0))


def _avg_tokens(benches: dict[str, Any], name: str) -> float:
    return float(benches.get(name, {}).get("avg_tokens", 0.0))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _prompt_intersections() -> dict[str, int]:
    result = {}
    train_prompts = set()
    for path in sorted((DATASET_DIR / "baseline").glob("train_*.jsonl")):
        train_prompts |= _prompts(path)
    for path in sorted((DATASET_DIR / "eval").glob("*.jsonl")):
        result[f"baseline_train_vs_{path.name}"] = len(train_prompts & _prompts(path))
    return result


def _range_text(values: list[int]) -> str:
    return "empty" if not values else f"{min(values)}..{max(values)}"


def _device_name(analysis: dict[str, Any]) -> str:
    for run in analysis.get("runs", {}).values():
        for benchmark in run.get("benchmarks", {}).values():
            summary = benchmark.get("summary", {})
            if summary.get("device"):
                return f"{summary.get('device')} ({summary.get('device_name')})"
    return "unknown"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
        )
        + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _prompts(path: Path) -> set[str]:
    return (
        {str(record["prompt"]) for record in _read_jsonl(path)}
        if path.exists()
        else set()
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> Any:
    return _read_json(path) if path.exists() else {}


if __name__ == "__main__":
    raise SystemExit(main())
