from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

from ai_brain.arithmetic_rules import (
    ArithmeticCase,
    TraceFormat,
    arithmetic_prompt,
    final_answer_from_trace,
    format_trace,
    trace_component_scores,
)
from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.generation import generate_answer_ids, load_model_for_inference
from ai_brain.eval.metrics import summarize_predictions, task_group
from ai_brain.eval.normalize import (
    extract_generated_answer,
    is_false_answer,
    normalize_answer,
)
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.runtime.device import get_device_info
from ai_brain.segments import SEG_ANSWER, SEG_CONTROL, SEG_QUERY, SEG_WORKSPACE
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm
from ai_brain.workspace_abi import WorkspaceState, serialize_workspace_state

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m19_rule_based_executor"
RUNS_DIR = ROOT / "runs" / "m19_rule_based_executor"
DOC_PATH = ROOT / "docs" / "m19_rule_based_executor_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m19_rule_based_executor_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 19000
SEQUENCE_LENGTH = 384
MAX_NEW_TOKENS = {
    "answer": 32,
    "scratchpad": 160,
    "rfft": 220,
    "state_machine": 180,
}
TRAIN_PER_OP = 1500
EVAL_PER_AXIS_OP = 120
VARIANTS: tuple[TraceFormat, ...] = ("answer", "scratchpad", "rfft", "state_machine")
VARIANT_STEPS = {
    "answer": 8000,
    "scratchpad": 8000,
    "rfft": 10000,
    "state_machine": 10000,
}
HOLDOUT_DIGIT_PAIRS = {
    (7, 5),
    (8, 6),
    (2, 9),
    (4, 7),
    (9, 8),
    (1, 6),
}
HOLDOUT_DIGIT_PAIR_KEYS = HOLDOUT_DIGIT_PAIRS | {(b, a) for a, b in HOLDOUT_DIGIT_PAIRS}
OOD_AXES = (
    "in_range",
    "operand_range_ood",
    "digit_combo_ood",
    "result_range_ood",
    "length_3digit",
    "length_4digit",
    "length_5digit",
)


@dataclass(frozen=True)
class CaseWithAxis:
    case: ArithmeticCase
    axis: str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    for variant in VARIANTS:
        subparsers.add_parser(f"run-{variant.replace('_', '-')}")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command.startswith("run-") and args.command != "run-all":
        run_variant(args.command.removeprefix("run-").replace("-", "_"))
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        for variant in VARIANTS:
            run_variant(variant)
            analyze_all()
        build_report(checks_passed=False)
    return 0


def prepare_datasets() -> None:
    if DATASET_DIR.exists():
        shutil.rmtree(DATASET_DIR)
    rng = random.Random(SEED)
    train_cases = _generate_axis_cases(
        "in_range",
        TRAIN_PER_OP,
        rng=rng,
        exclude_digit_pairs=HOLDOUT_DIGIT_PAIR_KEYS,
    )
    train_keys = {item.case.key for item in train_cases}
    eval_cases = {
        axis: _generate_axis_cases(
            axis,
            EVAL_PER_AXIS_OP,
            rng=rng,
            exclude_keys=train_keys,
        )
        for axis in OOD_AXES
    }
    for variant in VARIANTS:
        _write_jsonl(
            DATASET_DIR / variant / "train.jsonl",
            [
                _record(item.case, variant=variant, split="train", axis=item.axis)
                for item in train_cases
            ],
        )
        for axis, cases in eval_cases.items():
            _write_jsonl(
                DATASET_DIR / variant / "eval" / f"{axis}.jsonl",
                [
                    _record(item.case, variant=variant, split="eval", axis=axis)
                    for item in cases
                ],
            )
        _write_jsonl(
            DATASET_DIR / variant / "eval" / "workspace_abi_heldout.jsonl",
            [
                _record(
                    item.case,
                    variant=variant,
                    split="eval",
                    axis="workspace_abi_heldout",
                    workspace_prompt=True,
                )
                for item in eval_cases["operand_range_ood"]
            ],
        )
    _write_manifest(train_cases, eval_cases)


def run_variant(variant: str) -> None:
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant: {variant}")
    trace_format = _trace_format(variant)
    checkpoint = _run_train(
        variant=trace_format,
        train_path=DATASET_DIR / variant / "train.jsonl",
        eval_path=DATASET_DIR / variant / "eval" / "in_range.jsonl",
        steps=VARIANT_STEPS[trace_format],
        seed=SEED + VARIANTS.index(trace_format) * 100,
    )
    for axis in (*OOD_AXES, "workspace_abi_heldout"):
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=RUNS_DIR / variant / "benchmark" / axis,
            eval_path=DATASET_DIR / variant / "eval" / f"{axis}.jsonl",
            variant=trace_format,
        )


def analyze_all() -> None:
    analysis = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "variants": {
            variant: {
                axis: _read_summary_payload(RUNS_DIR / variant / "benchmark" / axis)
                for axis in (*OOD_AXES, "workspace_abi_heldout")
            }
            for variant in VARIANTS
        },
        "gates": {},
    }
    analysis["gates"] = {
        variant: _variant_gate(analysis["variants"][variant]) for variant in VARIANTS
    }
    analysis["best_variant"] = _best_variant(analysis)
    analysis["decision"] = _decision(analysis)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    lines = [
        "# M-19 Rule-Based Arithmetic Executor Report",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        f"- device: `{_device_name(analysis)}`",
        "",
        "## OOD Split Audit",
        "",
        _audit_table(analysis),
        "",
        "## Answer-Only Baseline",
        "",
        _variant_table(analysis, "answer"),
        "",
        "## Scratchpad Baseline",
        "",
        _variant_table(analysis, "scratchpad"),
        "",
        "## RFFT",
        "",
        _variant_table(analysis, "rfft"),
        "",
        "## State-Machine Trace",
        "",
        _variant_table(analysis, "state_machine"),
        "",
        "## Length Curriculum",
        "",
        _length_table(analysis),
        "",
        "## Optional Self-Improvement",
        "",
        _self_improvement_status(analysis),
        "",
        "## Workspace ABI Compatibility",
        "",
        _workspace_gap_table(analysis),
        "",
        "## Retrieved Operands -> Executor",
        "",
        _retrieved_operand_status(analysis),
        "",
        "## Multi-Seed",
        "",
        _multi_seed_status(analysis),
        "",
        "## Recommendation For Stage-1 Reasoning Executor",
        "",
        analysis.get("decision", "missing"),
    ]
    text = "\n".join(lines)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def _run_train(
    *,
    variant: TraceFormat,
    train_path: Path,
    eval_path: Path,
    steps: int,
    seed: int,
) -> Path:
    output_dir = RUNS_DIR / variant
    checkpoint = _checkpoint_path(output_dir, steps)
    if checkpoint.exists():
        print(f"skip existing run: {variant}")
        return checkpoint
    config = TrainConfig(
        train_path=train_path,
        eval_path=eval_path,
        tokenizer_path=TOKENIZER_PATH,
        output_dir=output_dir,
        model_config_name="arithmetic_3m",
        steps=steps,
        batch_size=8,
        sequence_length=SEQUENCE_LENGTH,
        loss_mode="answer-only",
        learning_rate=3e-4,
        grad_clip_norm=1.0,
        numeric_tokenization="digit_safe",
        position_encoding="relative",
        segment_attention_mode="workspace",
        seed=seed,
        eval_every=max(1000, steps // 5),
        eval_batches=20,
        save_every=steps,
    )
    started = time.time()
    result = train_lm(config)
    (output_dir / "run_result.json").write_text(
        json.dumps(
            {"elapsed_seconds": time.time() - started, "train_result": result},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return checkpoint


@torch.no_grad()
def _eval_checkpoint(
    *,
    checkpoint: Path,
    output_dir: Path,
    eval_path: Path,
    variant: TraceFormat,
) -> dict[str, Any]:
    summary_path = output_dir / "summary.json"
    if summary_path.exists():
        return _summary_payload(_read_json(summary_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    device_info = get_device_info()
    model, loaded = load_model_for_inference(
        checkpoint_path=checkpoint,
        tokenizer_path=TOKENIZER_PATH,
        device=device_info.device,
    )
    predictions = []
    predictions_path = output_dir / "predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as file:
        for index, record in enumerate(_iter_jsonl(eval_path)):
            segment_ids, context_access = _segment_tensors_for_inference(
                tokenizer=tokenizer,
                record=record,
                device=device_info.device,
            )
            generated_ids = generate_answer_ids(
                model=model,
                tokenizer=tokenizer,
                prompt=str(record["prompt"]),
                max_new_tokens=MAX_NEW_TOKENS[variant],
                device=device_info.device,
                numeric_tokenization="digit_safe",
                segment_ids=segment_ids,
                context_access_mask=context_access,
                segment_attention_mode="workspace",
            )
            raw_generation = tokenizer.decode(generated_ids, skip_special_tokens=False)
            prediction = _prediction_payload(
                record, index, raw_generation, generated_ids, variant=variant
            )
            predictions.append(prediction)
            file.write(
                json.dumps(prediction, ensure_ascii=False, sort_keys=True) + "\n"
            )
    summary = {
        **_summarize(predictions),
        "count": len(predictions),
        "checkpoint_path": str(checkpoint),
        "checkpoint_step": loaded.get("step"),
        "eval_path": str(eval_path),
        "tokenizer_path": str(TOKENIZER_PATH),
        "numeric_tokenization": "digit_safe",
        "segment_attention_mode": "workspace",
        "predictions_path": str(predictions_path),
        "device": str(device_info.device),
        "device_name": device_info.name,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return _summary_payload(summary)


def _record(
    case: ArithmeticCase,
    *,
    variant: TraceFormat,
    split: str,
    axis: str,
    workspace_prompt: bool = False,
) -> dict[str, Any]:
    prompt = arithmetic_prompt(case)
    spans = [("query", 0, len(prompt), False)]
    if workspace_prompt:
        prompt = serialize_workspace_state(
            WorkspaceState(op=case.op, a=case.a, b=case.b)
        )
        spans = [("workspace", 0, len(prompt), False)]
    return {
        "id": f"m19.{split}.{variant}.{axis}.{case.op}.{case.a}.{case.b}",
        "task_type": f"m19.{variant}.{axis}.{case.op}.{_bucket(case)}",
        "prompt": prompt,
        "answer": format_trace(case, variant),
        "metadata": {
            "segment_schema": "m19.v1",
            "segment_spans": [
                {"segment": segment, "start": start, "end": end, "access": access}
                for segment, start, end, access in spans
            ],
            "variant": variant,
            "axis": axis,
            "op": case.op,
            "a": case.a,
            "b": case.b,
            "result": case.result,
            "digits": max(len(str(case.a)), len(str(case.b))),
            "answer_digits": len(str(case.result)),
            "bucket": _bucket(case),
            "digit_pairs": _digit_pairs(case),
        },
    }


def _generate_axis_cases(
    axis: str,
    count_per_op: int,
    *,
    rng: random.Random,
    exclude_digit_pairs: set[tuple[int, int]] | None = None,
    exclude_keys: set[str] | None = None,
) -> list[CaseWithAxis]:
    add_cases = _generate_cases_for_op(
        "add",
        axis,
        count_per_op,
        rng=rng,
        exclude_digit_pairs=exclude_digit_pairs,
        exclude_keys=exclude_keys,
    )
    sub_cases = _generate_cases_for_op(
        "sub",
        axis,
        count_per_op,
        rng=rng,
        exclude_digit_pairs=exclude_digit_pairs,
        exclude_keys=exclude_keys,
    )
    return [
        CaseWithAxis(case=case, axis=axis)
        for pair in zip(add_cases, sub_cases, strict=True)
        for case in pair
    ]


def _generate_cases_for_op(
    op: str,
    axis: str,
    count: int,
    *,
    rng: random.Random,
    exclude_digit_pairs: set[tuple[int, int]] | None,
    exclude_keys: set[str] | None,
) -> list[ArithmeticCase]:
    cases: list[ArithmeticCase] = []
    used: set[str] = set()
    attempts = 0
    while len(cases) < count:
        attempts += 1
        if attempts > count * 2000:
            raise RuntimeError(f"Could not generate {axis}/{op}")
        a, b = _sample_operands(axis, op=op, rng=rng)
        if op == "sub" and a < b:
            a, b = b, a
        case = ArithmeticCase(op=op, a=a, b=b)
        if case.key in used:
            continue
        if exclude_keys and case.key in exclude_keys:
            continue
        if exclude_digit_pairs and _contains_digit_pair(case, exclude_digit_pairs):
            continue
        if axis == "digit_combo_ood" and not _contains_digit_pair(
            case, HOLDOUT_DIGIT_PAIR_KEYS
        ):
            continue
        if axis == "result_range_ood" and not _is_result_range_ood(case):
            continue
        used.add(case.key)
        cases.append(case)
    return cases


def _sample_operands(axis: str, *, op: str, rng: random.Random) -> tuple[int, int]:
    if axis in {"in_range", "digit_combo_ood"}:
        return rng.randint(10, 69), rng.randint(10, 69)
    if axis == "operand_range_ood":
        return rng.randint(70, 99), rng.randint(70, 99)
    if axis == "result_range_ood":
        if op == "sub":
            return rng.randint(70, 99), rng.randint(10, 39)
        return rng.randint(60, 89), rng.randint(60, 89)
    if axis == "length_3digit":
        return rng.randint(100, 999), rng.randint(100, 999)
    if axis == "length_4digit":
        return rng.randint(1000, 9999), rng.randint(1000, 9999)
    if axis == "length_5digit":
        return rng.randint(10000, 99999), rng.randint(10000, 99999)
    raise ValueError(f"Unknown axis: {axis}")


def _contains_digit_pair(case: ArithmeticCase, pairs: set[tuple[int, int]]) -> bool:
    return any(pair in pairs for pair in _digit_pairs(case))


def _digit_pairs(case: ArithmeticCase) -> list[tuple[int, int]]:
    width = max(len(str(case.a)), len(str(case.b)))
    a_digits = str(case.a).zfill(width)
    b_digits = str(case.b).zfill(width)
    return [(int(a), int(b)) for a, b in zip(a_digits, b_digits, strict=True)]


def _is_result_range_ood(case: ArithmeticCase) -> bool:
    if case.op == "add":
        return case.result >= 140
    return case.result >= 50


def _bucket(case: ArithmeticCase) -> str:
    if case.op == "add":
        if case.result >= 10 ** max(len(str(case.a)), len(str(case.b))):
            return "length_growth"
        if any(a + b >= 10 for a, b in _digit_pairs(case)):
            return "carry"
        return "no_carry"
    return "borrow" if any(a < b for a, b in _digit_pairs(case)) else "no_borrow"


def _segment_tensors_for_inference(
    *,
    tokenizer: ByteLevelBpeTokenizer,
    record: dict[str, Any],
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor]:
    prompt = str(record["prompt"]).strip()
    text = f"<|prompt|>\n{prompt}\n<|answer|>\n"
    encoded = tokenizer.encode_with_offsets(text, numeric_tokenization="digit_safe")
    prompt_start = len("<|prompt|>\n")
    prompt_end = prompt_start + len(prompt)
    spans = _normalized_spans(record)
    segment_ids = [SEG_CONTROL]
    access_mask = [0]
    for start, end in encoded.offsets:
        if start >= prompt_end or end <= prompt_start:
            segment_ids.append(SEG_ANSWER if start >= prompt_end else SEG_CONTROL)
            access_mask.append(0)
            continue
        relative_start = max(0, start - prompt_start)
        relative_end = min(len(prompt), end - prompt_start)
        span = _matching_span(spans, relative_start, relative_end)
        segment_ids.append(span["segment_id"] if span else SEG_QUERY)
        access_mask.append(int(span["access"]) if span else 0)
    return (
        torch.tensor([segment_ids], dtype=torch.long, device=device),
        torch.tensor([access_mask], dtype=torch.long, device=device),
    )


def _normalized_spans(record: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = {
        "query": SEG_QUERY,
        "workspace": SEG_WORKSPACE,
        "answer": SEG_ANSWER,
        "control": SEG_CONTROL,
    }
    metadata = record.get("metadata", {})
    raw_spans = metadata.get("segment_spans", []) if isinstance(metadata, dict) else []
    return [
        {
            "start": int(span["start"]),
            "end": int(span["end"]),
            "segment_id": mapping[str(span["segment"])],
            "access": bool(span.get("access", False)),
        }
        for span in raw_spans
    ]


def _matching_span(
    spans: list[dict[str, Any]], start: int, end: int
) -> dict[str, Any] | None:
    best = None
    best_overlap = 0
    for span in spans:
        overlap = min(end, span["end"]) - max(start, span["start"])
        if overlap > best_overlap:
            best = span
            best_overlap = overlap
    return best


def _prediction_payload(
    record: dict[str, Any],
    index: int,
    raw_generation: str,
    generated_ids: list[int],
    *,
    variant: TraceFormat,
) -> dict[str, Any]:
    predicted = extract_generated_answer(raw_generation)
    expected = str(record["answer"])
    metadata = record["metadata"]
    case = ArithmeticCase(
        op=metadata["op"],
        a=int(metadata["a"]),
        b=int(metadata["b"]),
    )
    scores = trace_component_scores(case, predicted, variant)
    final_expected = extract_final_answer(expected)
    final_predicted = extract_final_answer(predicted)
    return {
        "id": str(record.get("id", f"{record['task_type']}:{index:06d}")),
        "task_type": str(record["task_type"]),
        "task_group": task_group(str(record["task_type"])),
        "prompt": str(record["prompt"]),
        "expected": expected,
        "predicted": predicted,
        "raw_generation": raw_generation,
        "tokens_generated": len(generated_ids),
        "exact_match": predicted == expected,
        "normalized_exact_match": normalize_answer(predicted)
        == normalize_answer(expected),
        "final_expected": final_expected,
        "final_predicted": final_predicted,
        "oracle_final_predicted": final_answer_from_trace(predicted),
        "final_exact_match": final_predicted == final_expected,
        "final_normalized_exact_match": scores["final_exact"]
        or normalize_final_answer(final_predicted)
        == normalize_final_answer(final_expected),
        "false_answer": is_false_answer(
            task_type=str(record["task_type"]), expected=expected, predicted=predicted
        ),
        **scores,
    }


def _summarize(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_predictions(predictions)
    _add_trace_metrics(summary["overall"], predictions)
    for task_type, payload in summary["by_task_type"].items():
        _add_trace_metrics(
            payload,
            [
                prediction
                for prediction in predictions
                if prediction["task_type"] == task_type
            ],
        )
    return summary


def _add_trace_metrics(
    payload: dict[str, Any], predictions: list[dict[str, Any]]
) -> None:
    count = len(predictions)
    if count == 0:
        payload.update(
            {
                "full_trace_exact": 0.0,
                "digit_exact": 0.0,
                "carry_borrow_exact": None,
                "empty_prediction_rate": 0.0,
                "avg_tokens_generated": 0.0,
            }
        )
        return
    payload["full_trace_exact"] = (
        sum(bool(p.get("full_trace_exact")) for p in predictions) / count
    )
    payload["digit_exact"] = (
        sum(bool(p.get("digit_exact")) for p in predictions) / count
    )
    carry_predictions = [
        p for p in predictions if p.get("carry_borrow_exact") is not None
    ]
    payload["carry_borrow_exact"] = (
        None
        if not carry_predictions
        else sum(bool(p.get("carry_borrow_exact")) for p in carry_predictions)
        / len(carry_predictions)
    )
    payload["empty_prediction_rate"] = (
        sum(not p["predicted"].strip() for p in predictions) / count
    )
    payload["avg_tokens_generated"] = (
        sum(float(p["tokens_generated"]) for p in predictions) / count
    )


def _summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("status") == "missing":
        return {"status": "missing", "final_nem": 0.0}
    overall = summary.get("overall", summary)
    return {
        "status": "complete",
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "full_nem": float(overall.get("normalized_exact_match", 0.0)),
        "trace_exact": float(overall.get("full_trace_exact", 0.0)),
        "digit_exact": float(overall.get("digit_exact", 0.0)),
        "carry_borrow_exact": _optional_float(overall.get("carry_borrow_exact")),
        "by_task_type": {
            key: float(value.get("final_normalized_exact_match", 0.0))
            for key, value in summary.get("by_task_type", {}).items()
        },
        "summary": summary,
    }


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _variant_gate(payload: dict[str, Any]) -> bool:
    return (
        payload.get("in_range", {}).get("final_nem", 0.0) >= 0.98
        and payload.get("operand_range_ood", {}).get("final_nem", 0.0) >= 0.95
        and payload.get("digit_combo_ood", {}).get("final_nem", 0.0) >= 0.95
        and payload.get("length_3digit", {}).get("final_nem", 0.0) >= 0.95
    )


def _best_variant(analysis: dict[str, Any]) -> str:
    scores = {
        variant: sum(
            analysis["variants"][variant].get(axis, {}).get("final_nem", 0.0)
            for axis in OOD_AXES
        )
        for variant in VARIANTS
    }
    return max(scores, key=scores.get)


def _decision(analysis: dict[str, Any]) -> str:
    best = analysis.get("best_variant", "unknown")
    if analysis.get("gates", {}).get("rfft"):
        return "OUTCOME A: RFFT met the systematic generalization gate; adopt explicit rule-following executor."
    if analysis.get("gates", {}).get("state_machine"):
        return "OUTCOME B: state-machine trace met the systematic generalization gate; adopt local transition executor."
    best_ood = (
        analysis.get("variants", {})
        .get(best, {})
        .get("operand_range_ood", {})
        .get("final_nem", 0.0)
    )
    if best_ood < 0.95:
        return (
            f"OUTCOME E: no tested representation reached operand-range OOD >= .95. "
            f"Best exploratory variant was `{best}`; current 5.29M objective/format still "
            "does not yield systematic arithmetic. Next run a controlled capacity/objective sweep."
        )
    return (
        f"OUTCOME D candidate: `{best}` is the strongest variant but did not clear all "
        "length/digit-combination gates. Try easy-to-hard verified expansion before scaling."
    )


def _audit_table(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    if manifest.get("status") == "missing":
        return "missing"
    rows = [
        "| split | count | operand range | digit lengths | answer lengths | buckets | digit pairs |",
        "|---|---:|---|---|---|---|---:|",
    ]
    for name, audit in manifest.get("split_audit", {}).items():
        rows.append(
            f"| {name} | {audit['count']} | {audit['operand_range']} | "
            f"{audit['operand_digit_lengths']} | {audit['answer_digit_lengths']} | "
            f"{audit['buckets']} | {audit['digit_pair_count']} |"
        )
    return "\n".join(rows)


def _variant_table(analysis: dict[str, Any], variant: str) -> str:
    payload = analysis.get("variants", {}).get(variant, {})
    if not payload:
        return "missing"
    rows = [
        "| eval axis | final NEM | trace exact | digit exact | carry/borrow |",
        "|---|---:|---:|---:|---:|",
    ]
    for axis in (*OOD_AXES, "workspace_abi_heldout"):
        summary = payload.get(axis, {})
        rows.append(
            f"| {axis} | {summary.get('final_nem', 0.0):.4f} | "
            f"{summary.get('trace_exact', 0.0):.4f} | "
            f"{summary.get('digit_exact', 0.0):.4f} | "
            f"{_fmt_optional(summary.get('carry_borrow_exact'))} |"
        )
    return "\n".join(rows)


def _fmt_optional(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.4f}"


def _length_table(analysis: dict[str, Any]) -> str:
    rows = ["| variant | 3-digit | 4-digit | 5-digit |", "|---|---:|---:|---:|"]
    for variant in VARIANTS:
        payload = analysis.get("variants", {}).get(variant, {})
        rows.append(
            f"| {variant} | {payload.get('length_3digit', {}).get('final_nem', 0.0):.4f} | "
            f"{payload.get('length_4digit', {}).get('final_nem', 0.0):.4f} | "
            f"{payload.get('length_5digit', {}).get('final_nem', 0.0):.4f} |"
        )
    return "\n".join(rows)


def _workspace_gap_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| variant | operand OOD standalone | workspace ABI | gap |",
        "|---|---:|---:|---:|",
    ]
    for variant in VARIANTS:
        payload = analysis.get("variants", {}).get(variant, {})
        standalone = payload.get("operand_range_ood", {}).get("final_nem", 0.0)
        workspace = payload.get("workspace_abi_heldout", {}).get("final_nem", 0.0)
        rows.append(
            f"| {variant} | {standalone:.4f} | {workspace:.4f} | {abs(standalone - workspace):.4f} |"
        )
    return "\n".join(rows)


def _self_improvement_status(analysis: dict[str, Any]) -> str:
    best = analysis.get("best_variant", "unknown")
    if best not in {"rfft", "state_machine"}:
        return "skipped: no rule representation passed the exploratory gate"
    return f"skipped: `{best}` should be used for the next verified easy-to-hard run"


def _retrieved_operand_status(analysis: dict[str, Any]) -> str:
    best = analysis.get("best_variant", "unknown")
    workspace_score = (
        analysis.get("variants", {})
        .get(best, {})
        .get("workspace_abi_heldout", {})
        .get("final_nem", 0.0)
    )
    if workspace_score < 0.95:
        return "skipped: workspace ABI executor did not pass OOD gate"
    return "skipped: retrieved operand pipeline is the next step after workspace OOD passes"


def _multi_seed_status(analysis: dict[str, Any]) -> str:
    best = analysis.get("best_variant", "unknown")
    if not analysis.get("gates", {}).get(best, False):
        return (
            "skipped: no variant passed gates, so multi-seed confirmation is premature"
        )
    return f"pending: run 3 seeds for `{best}`"


def _write_manifest(
    train_cases: list[CaseWithAxis], eval_cases: dict[str, list[CaseWithAxis]]
) -> None:
    split_audit = {"train": _audit_cases(train_cases)}
    split_audit.update(
        {axis: _audit_cases(cases) for axis, cases in eval_cases.items()}
    )
    manifest = {
        "kind": "m19_rule_based_executor",
        "seed": SEED,
        "model_config": "arithmetic_3m",
        "numeric_tokenization": "digit_safe",
        "position_encoding": "relative",
        "sequence_length": SEQUENCE_LENGTH,
        "train_range": "10..69, 2-digit, prompt-disjoint from eval, selected digit-pairs held out",
        "holdout_digit_pairs": sorted(HOLDOUT_DIGIT_PAIRS),
        "holdout_digit_pair_keys": sorted(HOLDOUT_DIGIT_PAIR_KEYS),
        "split_audit": split_audit,
        "task_type_distribution": _task_distribution(DATASET_DIR),
        "prompt_intersections": _prompt_intersections(),
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _audit_cases(items: list[CaseWithAxis]) -> dict[str, Any]:
    cases = [item.case for item in items]
    operands = [value for case in cases for value in (case.a, case.b)]
    return {
        "count": len(cases),
        "operand_range": f"{min(operands)}..{max(operands)}" if operands else "empty",
        "result_range": f"{min(case.result for case in cases)}..{max(case.result for case in cases)}"
        if cases
        else "empty",
        "operand_digit_lengths": dict(
            Counter(max(len(str(case.a)), len(str(case.b))) for case in cases)
        ),
        "answer_digit_lengths": dict(Counter(len(str(case.result)) for case in cases)),
        "buckets": dict(Counter(_bucket(case) for case in cases)),
        "digit_pair_count": len(
            {pair for case in cases for pair in _digit_pairs(case)}
        ),
    }


def _task_distribution(root: Path) -> dict[str, dict[str, int]]:
    return {
        str(path.relative_to(root)): dict(
            Counter(record["task_type"] for record in _iter_jsonl(path))
        )
        for path in sorted(root.glob("**/*.jsonl"))
    }


def _prompt_intersections() -> dict[str, int]:
    result = {}
    for variant in VARIANTS:
        train_prompts = _prompts(DATASET_DIR / variant / "train.jsonl")
        for eval_path in sorted((DATASET_DIR / variant / "eval").glob("*.jsonl")):
            result[f"{variant}:train_vs_{eval_path.name}"] = len(
                train_prompts & _prompts(eval_path)
            )
    return result


def _read_summary_payload(path: Path) -> dict[str, Any]:
    summary_path = path / "summary.json"
    if not summary_path.exists():
        return {"status": "missing", "final_nem": 0.0}
    return _summary_payload(_read_json(summary_path))


def _checkpoint_path(output_dir: Path, step: int) -> Path:
    return output_dir / "checkpoints" / f"step_{step:06d}.pt"


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
        )
        + "\n",
        encoding="utf-8",
    )


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _prompts(path: Path) -> set[str]:
    return (
        {record["prompt"] for record in _iter_jsonl(path)} if path.exists() else set()
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> Any:
    return _read_json(path) if path.exists() else {"status": "missing"}


def _trace_format(value: str) -> TraceFormat:
    if value not in VARIANTS:
        raise ValueError(f"Unknown trace format: {value}")
    return value  # type: ignore[return-value]


def _device_name(analysis: dict[str, Any]) -> str:
    for variant in VARIANTS:
        for summary in analysis.get("variants", {}).get(variant, {}).values():
            raw = summary.get("summary", {}) if isinstance(summary, dict) else {}
            if "device" in raw:
                return f"{raw.get('device')} ({raw.get('device_name')})"
    return "unknown"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
