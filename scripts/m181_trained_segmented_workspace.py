from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import torch

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
from ai_brain.segments import (
    SEG_ANSWER,
    SEG_CONTEXT,
    SEG_CONTROL,
    SEG_QUERY,
    SEG_WORKSPACE,
    SegmentAttentionMode,
)
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m181_trained_segmented_workspace"
RUNS_DIR = ROOT / "runs" / "m181_trained_segmented_workspace"
DOC_PATH = ROOT / "docs" / "m181_trained_segmented_workspace_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m181_trained_segmented_workspace_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 18100
SEQUENCE_LENGTH = 256
MAX_NEW_TOKENS = 32
TRAIN_CASES_PER_OP = 1200
EVAL_CASES_PER_OP = 60
FIT_STEPS = (5000, 10000, 20000)
LENGTHS = (1, 2, 4, 8, 16, 32, 64)
TRAIN_LENGTHS = (1, 2, 4, 8, 16)
FAMILIES = (
    "neutral",
    "random_vocab",
    "natural_phrase",
    "previous_arithmetic",
    "hard_negative",
)
MODES: dict[str, SegmentAttentionMode] = {
    "flat_relative": "flat_causal",
    "isolated_relative": "query_isolated",
    "workspace_relative": "workspace",
}

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
    def task_type(self) -> str:
        return f"m181.{self.op}"

    @property
    def key(self) -> str:
        return f"{self.op}:{self.a}:{self.b}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-fit")
    subparsers.add_parser("run-robustness")
    subparsers.add_parser("run-relevant-context")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-fit":
        run_fit()
    elif args.command == "run-robustness":
        run_robustness()
    elif args.command == "run-relevant-context":
        run_relevant_context()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_fit()
        analyze_all()
        if _fit_gate(_read_json(RUNS_DIR / "analysis.json")):
            run_robustness()
            analyze_all()
            if _robustness_gate(_read_json(RUNS_DIR / "analysis.json")):
                run_relevant_context()
                analyze_all()
        build_report(checks_passed=False)
    return 0


def prepare_datasets() -> None:
    rng = random.Random(SEED)
    train_cases = _generate_cases(TRAIN_CASES_PER_OP, rng=rng, offset=0)
    eval_cases = _generate_cases(
        EVAL_CASES_PER_OP,
        rng=rng,
        offset=10000,
        exclude_keys={case.key for case in train_cases},
    )
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    _write_jsonl(
        DATASET_DIR / "train" / "paired_irrelevant.jsonl",
        _paired_irrelevant_records(train_cases),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "clean.jsonl",
        _records_for_cases(eval_cases, split="eval", family="clean", length=0),
    )
    for family in FAMILIES:
        for length in LENGTHS:
            _write_jsonl(
                DATASET_DIR / "eval" / family / f"len_{length}.jsonl",
                _records_for_cases(
                    eval_cases,
                    split="eval",
                    family=family,
                    length=length,
                    heldout=True,
                ),
            )

    _write_jsonl(
        DATASET_DIR / "train" / "workspace_relevant.jsonl",
        _relevant_context_records(train_cases[:600]),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "relevant_context.jsonl",
        _relevant_context_records(eval_cases, heldout=True),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "oracle_chunks.jsonl",
        _oracle_chunk_records(eval_cases),
    )
    _write_jsonl(
        DATASET_DIR / "train" / "variable_binding.jsonl",
        _variable_binding_records(train=True),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "variable_binding.jsonl",
        _variable_binding_records(train=False),
    )
    _write_manifest(train_cases, eval_cases)


def run_fit() -> None:
    for steps in FIT_STEPS:
        for name, segment_mode in MODES.items():
            _run_train(
                name=f"{name}_{steps}",
                train_path=DATASET_DIR / "train" / "paired_irrelevant.jsonl",
                eval_path=DATASET_DIR / "eval" / "clean.jsonl",
                steps=steps,
                segment_mode=segment_mode,
                seed=SEED + steps + list(MODES).index(name),
            )
            _eval_checkpoint(
                checkpoint=_checkpoint_path(
                    RUNS_DIR / "fit" / f"{name}_{steps}", steps
                ),
                output_dir=RUNS_DIR / "fit" / f"{name}_{steps}" / "benchmark" / "clean",
                eval_path=DATASET_DIR / "eval" / "clean.jsonl",
                segment_mode=segment_mode,
            )
        analyze_all()
        if _fit_gate(_read_json(RUNS_DIR / "analysis.json"), steps=steps):
            return


def run_robustness() -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    selected_steps = int(analysis["gates"]["selected_fit_steps"])
    for name, segment_mode in MODES.items():
        checkpoint = _checkpoint_path(
            RUNS_DIR / "fit" / f"{name}_{selected_steps}", selected_steps
        )
        benchmark_dir = RUNS_DIR / "robustness" / f"{name}_{selected_steps}"
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=benchmark_dir / "clean",
            eval_path=DATASET_DIR / "eval" / "clean.jsonl",
            segment_mode=segment_mode,
        )
        for family in FAMILIES:
            for length in LENGTHS:
                _eval_checkpoint(
                    checkpoint=checkpoint,
                    output_dir=benchmark_dir / family / f"len_{length}",
                    eval_path=DATASET_DIR / "eval" / family / f"len_{length}.jsonl",
                    segment_mode=segment_mode,
                )


def run_relevant_context() -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    if not _robustness_gate(analysis):
        print("skip relevant context: robustness gate did not pass")
        return
    selected_steps = int(analysis["gates"]["selected_fit_steps"])
    workspace_checkpoint = _checkpoint_path(
        RUNS_DIR / "fit" / f"workspace_relative_{selected_steps}",
        selected_steps,
    )
    output_dir = RUNS_DIR / "relevant_context" / "workspace_relevant"
    target_steps = 5000
    if not _checkpoint_path(output_dir, target_steps).exists():
        _run_train(
            name="workspace_relevant",
            train_path=DATASET_DIR / "train" / "workspace_relevant.jsonl",
            eval_path=DATASET_DIR / "eval" / "relevant_context.jsonl",
            steps=target_steps,
            segment_mode="workspace",
            seed=SEED + 900,
            init_checkpoint=workspace_checkpoint,
            run_group="relevant_context",
        )
    checkpoint = _checkpoint_path(output_dir, target_steps)
    for eval_name in ("relevant_context", "oracle_chunks", "variable_binding"):
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=output_dir / "benchmark" / eval_name,
            eval_path=DATASET_DIR / "eval" / f"{eval_name}.jsonl",
            segment_mode="workspace",
        )


def analyze_all() -> None:
    analysis = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "fit": _collect_fit(),
        "robustness": _collect_robustness(),
        "relevant_context": _collect_relevant_context(),
        "gates": {},
    }
    analysis["gates"]["fit"] = _fit_gate(analysis)
    analysis["gates"]["selected_fit_steps"] = _selected_fit_steps(analysis)
    analysis["gates"]["robustness"] = _robustness_gate(analysis)
    analysis["gates"]["relevant_context"] = _relevant_context_gate(analysis)
    analysis["decision"] = _decision(analysis)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    lines = [
        "# M-18.1 Trained Segmented Workspace Report",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        f"- device: `{_device_name(analysis)}`",
        "",
        "## Dataset Verification",
        "",
        _dataset_table(analysis),
        "",
        "## Flat vs Isolated vs Workspace FIT",
        "",
        _fit_table(analysis),
        "",
        "## Distractor Robustness",
        "",
        _robustness_table(analysis),
        "",
        "## Relevant Context Retrieval",
        "",
        _relevant_context_table(analysis),
        "",
        "## Oracle Chunk Selection",
        "",
        _oracle_chunk_table(analysis),
        "",
        "## Variable Binding by Chain Depth and Distractor Count",
        "",
        _variable_binding_table(analysis),
        "",
        "## Consistency Loss Ablation",
        "",
        _consistency_table(analysis),
        "",
        "## Hard-Distractor Mining Effect",
        "",
        _hard_mining_table(analysis),
        "",
        "## Learned Selector",
        "",
        _learned_selector_table(analysis),
        "",
        "## Composition",
        "",
        _composition_table(analysis),
        "",
        "## Recommended Core Context Architecture",
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
    name: str,
    train_path: Path,
    eval_path: Path,
    steps: int,
    segment_mode: SegmentAttentionMode,
    seed: int,
    init_checkpoint: Path | None = None,
    run_group: str = "fit",
) -> Path:
    output_dir = RUNS_DIR / run_group / name
    checkpoint = _checkpoint_path(output_dir, steps)
    if checkpoint.exists():
        print(f"skip existing run: {run_group}/{name}")
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
        segment_attention_mode=segment_mode,
        seed=seed,
        eval_every=max(1000, steps // 5),
        eval_batches=20,
        save_every=steps,
        init_checkpoint_path=init_checkpoint,
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
    segment_mode: SegmentAttentionMode,
) -> dict[str, Any]:
    summary_path = output_dir / "summary.json"
    if summary_path.exists():
        return _summary_payload(_read_json(summary_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    device_info = get_device_info()
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
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
                max_new_tokens=MAX_NEW_TOKENS,
                device=device_info.device,
                numeric_tokenization="digit_safe",
                segment_ids=segment_ids,
                context_access_mask=context_access,
                segment_attention_mode=segment_mode,
            )
            raw_generation = tokenizer.decode(generated_ids, skip_special_tokens=False)
            prediction = _prediction_payload(
                record, index, raw_generation, generated_ids
            )
            predictions.append(prediction)
            file.write(
                json.dumps(prediction, ensure_ascii=False, sort_keys=True) + "\n"
            )
    summary = {
        **summarize_predictions(predictions),
        "count": len(predictions),
        "checkpoint_path": str(checkpoint),
        "checkpoint_step": loaded.get("step"),
        "eval_path": str(eval_path),
        "tokenizer_path": str(TOKENIZER_PATH),
        "numeric_tokenization": "digit_safe",
        "segment_attention_mode": segment_mode,
        "predictions_path": str(predictions_path),
        "device": str(device_info.device),
        "device_name": device_info.name,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return _summary_payload(summary)


def _generate_cases(
    count_per_op: int,
    *,
    rng: random.Random,
    offset: int,
    exclude_keys: set[str] | None = None,
) -> list[Case]:
    cases: list[Case] = []
    used: set[str] = set()
    excluded = exclude_keys or set()
    for op in ("add", "sub"):
        attempts = 0
        while len([case for case in cases if case.op == op]) < count_per_op:
            attempts += 1
            if attempts > count_per_op * 200:
                raise RuntimeError(f"Could not generate enough {op} cases")
            a = 10 + ((rng.randrange(10000) + offset + attempts * 17) % 80)
            b = 10 + ((rng.randrange(10000) + offset + attempts * 23) % 80)
            if op == "sub" and a < b:
                a, b = b, a
            case = Case(op=op, a=a, b=b)
            if case.key in used or case.key in excluded:
                continue
            used.add(case.key)
            cases.append(case)
    return cases


def _paired_irrelevant_records(cases: list[Case]) -> list[dict[str, Any]]:
    records = []
    for index, case in enumerate(cases):
        records.append(
            _record_for_case(case, split="train", family="clean", length=0, index=index)
        )
        family_a = FAMILIES[index % len(FAMILIES)]
        family_b = FAMILIES[(index * 3 + 1) % len(FAMILIES)]
        length_a = TRAIN_LENGTHS[index % len(TRAIN_LENGTHS)]
        length_b = TRAIN_LENGTHS[(index * 5 + 2) % len(TRAIN_LENGTHS)]
        records.append(
            _record_for_case(
                case,
                split="train",
                family=family_a,
                length=length_a,
                index=index,
            )
        )
        records.append(
            _record_for_case(
                case,
                split="train",
                family=family_b,
                length=length_b,
                index=index,
            )
        )
    return records


def _records_for_cases(
    cases: list[Case],
    *,
    split: str,
    family: str,
    length: int,
    heldout: bool = False,
) -> list[dict[str, Any]]:
    return [
        _record_for_case(
            case,
            split=split,
            family=family,
            length=length,
            index=index,
            heldout=heldout,
        )
        for index, case in enumerate(cases)
    ]


def _record_for_case(
    case: Case,
    *,
    split: str,
    family: str,
    length: int,
    index: int,
    heldout: bool = False,
) -> dict[str, Any]:
    query = _query(case)
    prompt = query
    spans = [("query", 0, len(query), False)]
    active_start = 0
    if family != "clean":
        context = _distractor_context(
            case, family=family, length=length, heldout=heldout
        )
        prompt = f"{context}\n{query}"
        spans = [
            ("context", 0, len(context), False),
            ("query", len(context) + 1, len(prompt), False),
        ]
        active_start = len(context) + 1
    return _record_with_spans(
        record_id=f"m181.{split}.{family}.{length}.{case.op}.{index:06d}",
        task_type=f"{case.task_type}.{family}",
        prompt=prompt,
        answer=f"FINAL {case.result}",
        spans=spans,
        metadata={
            "op": case.op,
            "a": case.a,
            "b": case.b,
            "answer_value": case.result,
            "family": family,
            "length": length,
            "split": split,
            "case_key": case.key,
            "active_prompt_start_char": active_start,
        },
    )


def _query(case: Case) -> str:
    return f"{case.op_token} {case.a:02d} {case.sign} {case.b:02d}"


def _distractor_context(case: Case, *, family: str, length: int, heldout: bool) -> str:
    if family == "neutral":
        return " ".join(("CTX" if heldout else "PAD") for _ in range(length))
    if family == "random_vocab":
        vocab = (
            "ALPHA",
            "BRAVO",
            "CLOUD",
            "DELTA",
            "ECHO",
            "FLAME",
            "GLASS",
            "HARBOR",
            "IVORY",
            "JAZZ",
            "KILO",
            "LEMON",
            "MANGO",
            "NOVA",
            "OCEAN",
            "PULSE",
        )
        return " ".join(
            vocab[(index * 7 + length) % len(vocab)] for index in range(length)
        )
    if family == "natural_phrase":
        words = ("ASIDE", "UNUSED", "IGNORE", "OTHER") if heldout else ("NOTE", "SKIP")
        return " ".join(words[index % len(words)] for index in range(length))
    lines = []
    for index in range(length):
        op = (
            case.op_token
            if family == "hard_negative"
            else ("ADD" if index % 2 == 0 else "SUB")
        )
        a = 10 + ((case.a + 11 * index + (7 if heldout else 3)) % 80)
        b = 10 + ((case.b + 13 * index + (9 if heldout else 5)) % 80)
        if op == "SUB" and a < b:
            a, b = b, a
        if family == "hard_negative" and index % 2 == 0:
            a = case.a
        result = a + b if op == "ADD" else a - b
        sign = "+" if op == "ADD" else "-"
        prefix = "DONE" if heldout else "D"
        lines.append(f"{prefix}{op}{a:02d}{sign}{b:02d}={result}")
    return " ".join(lines)


def _relevant_context_records(
    cases: list[Case], *, heldout: bool = False
) -> list[dict[str, Any]]:
    records = []
    for index, case in enumerate(cases):
        context_lines = [
            f"A = {case.a:02d}",
            f"junk1 = {(case.a + case.b + 17) % 90:02d}",
            f"B = {case.b:02d}",
            f"junk2 = {(case.a * 3 + case.b + 11) % 90:02d}",
        ]
        context = "\n".join(context_lines)
        query = f"QUERY {case.op_token} A B"
        prompt = f"{context}\n{query}"
        spans = []
        cursor = 0
        for line in context_lines:
            access = line.startswith(("A =", "B ="))
            spans.append(("context", cursor, cursor + len(line), access))
            cursor += len(line) + 1
        spans.append(("query", len(context) + 1, len(prompt), False))
        records.append(
            _record_with_spans(
                record_id=f"m181.relevant.{case.op}.{index:06d}",
                task_type=f"m181.relevant_context.{case.op}",
                prompt=prompt,
                answer=f"FINAL {case.result}",
                spans=spans,
                metadata={
                    "op": case.op,
                    "a": case.a,
                    "b": case.b,
                    "heldout": heldout,
                    "kind": "relevant_context",
                },
            )
        )
    return records


def _oracle_chunk_records(cases: list[Case]) -> list[dict[str, Any]]:
    records = []
    for index, case in enumerate(cases):
        chunks = [
            f"K0 = {(case.a + 19) % 90:02d}",
            f"A = {case.a:02d}",
            f"K1 = {(case.b + 23) % 90:02d}",
            f"B = {case.b:02d}",
            f"K2 = {(case.a + case.b + 29) % 90:02d}",
        ]
        context = "\n".join(chunks)
        query = f"QUERY {case.op_token} A B"
        prompt = f"{context}\n{query}"
        spans = []
        cursor = 0
        for chunk_index, chunk in enumerate(chunks):
            spans.append(
                ("context", cursor, cursor + len(chunk), chunk_index in {1, 3})
            )
            cursor += len(chunk) + 1
        spans.append(("query", len(context) + 1, len(prompt), False))
        records.append(
            _record_with_spans(
                record_id=f"m181.oracle_chunk.{case.op}.{index:06d}",
                task_type=f"m181.oracle_chunk.{case.op}",
                prompt=prompt,
                answer=f"FINAL {case.result}",
                spans=spans,
                metadata={"op": case.op, "kind": "oracle_chunk"},
            )
        )
    return records


def _variable_binding_records(*, train: bool) -> list[dict[str, Any]]:
    rng = random.Random(SEED + (700 if train else 900))
    records = []
    count = 40 if train else 20
    for depth in (1, 2, 3, 4):
        for distractors in (0, 1, 2, 4, 8):
            for index in range(count):
                value = 10 + rng.randrange(80)
                names = [chr(ord("A") + i) for i in range(depth + 1)]
                lines = [f"{names[0]} = {value:02d}"]
                lines.extend(
                    f"{names[i]} = {names[i - 1]}" for i in range(1, len(names))
                )
                for junk in range(distractors):
                    lines.insert(
                        1 + (junk % len(lines)),
                        f"J{junk} = {10 + rng.randrange(80):02d}",
                    )
                query = f"QUERY {names[-1]}"
                prompt = "\n".join([*lines, query])
                spans = []
                cursor = 0
                for line in lines:
                    access = not line.startswith("J")
                    spans.append(("context", cursor, cursor + len(line), access))
                    cursor += len(line) + 1
                spans.append(("query", prompt.index("QUERY"), len(prompt), False))
                records.append(
                    _record_with_spans(
                        record_id=f"m181.binding.d{depth}.x{distractors}.{index:05d}",
                        task_type=f"m181.binding.depth{depth}.distractors{distractors}",
                        prompt=prompt,
                        answer=f"FINAL {value}",
                        spans=spans,
                        metadata={
                            "depth": depth,
                            "distractors": distractors,
                            "value": value,
                            "split": "train" if train else "eval",
                        },
                    )
                )
    return records


def _record_with_spans(
    *,
    record_id: str,
    task_type: str,
    prompt: str,
    answer: str,
    spans: list[tuple[str, int, int, bool]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": record_id,
        "task_type": task_type,
        "prompt": prompt,
        "answer": answer,
        "metadata": {
            **metadata,
            "segment_schema": "m181.v1",
            "segment_spans": [
                {"segment": segment, "start": start, "end": end, "access": access}
                for segment, start, end, access in spans
            ],
        },
    }


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
        prompt_relative_start = max(0, start - prompt_start)
        prompt_relative_end = min(len(prompt), end - prompt_start)
        span = _matching_span(spans, prompt_relative_start, prompt_relative_end)
        if span is None:
            segment_ids.append(SEG_QUERY)
            access_mask.append(0)
        else:
            segment_ids.append(span["segment_id"])
            access_mask.append(int(span["access"]))
    return (
        torch.tensor([segment_ids], dtype=torch.long, device=device),
        torch.tensor([access_mask], dtype=torch.long, device=device),
    )


def _normalized_spans(record: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = {
        "context": SEG_CONTEXT,
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
) -> dict[str, Any]:
    predicted = extract_generated_answer(raw_generation)
    expected = str(record["answer"])
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
        "final_exact_match": final_predicted == final_expected,
        "final_normalized_exact_match": normalize_final_answer(final_predicted)
        == normalize_final_answer(final_expected),
        "false_answer": is_false_answer(
            task_type=str(record["task_type"]),
            expected=expected,
            predicted=predicted,
        ),
    }


def _collect_fit() -> dict[str, Any]:
    result = {}
    for steps in FIT_STEPS:
        result[str(steps)] = {}
        for name in MODES:
            result[str(steps)][name] = _read_summary_payload(
                RUNS_DIR / "fit" / f"{name}_{steps}" / "benchmark" / "clean"
            )
    return result


def _collect_robustness() -> dict[str, Any]:
    selected = _selected_fit_steps({"fit": _collect_fit(), "gates": {}})
    if selected is None:
        return {"status": "skipped"}
    result: dict[str, Any] = {"selected_steps": selected}
    for name in MODES:
        base = RUNS_DIR / "robustness" / f"{name}_{selected}"
        payload: dict[str, Any] = {"clean": _read_summary_payload(base / "clean")}
        for family in FAMILIES:
            payload[family] = {
                str(length): _read_summary_payload(base / family / f"len_{length}")
                for length in LENGTHS
            }
        result[name] = payload
    return result


def _collect_relevant_context() -> dict[str, Any]:
    base = RUNS_DIR / "relevant_context" / "workspace_relevant" / "benchmark"
    if not base.exists():
        return {"status": "skipped"}
    return {
        "workspace_relevant": {
            "relevant_context": _read_summary_payload(base / "relevant_context"),
            "oracle_chunks": _read_summary_payload(base / "oracle_chunks"),
            "variable_binding": _read_summary_payload(base / "variable_binding"),
        }
    }


def _fit_gate(analysis: dict[str, Any], *, steps: int | None = None) -> bool:
    fit = analysis.get("fit", {})
    step_keys = [str(steps)] if steps is not None else [str(step) for step in FIT_STEPS]
    for step_key in step_keys:
        payload = fit.get(step_key, {})
        if not payload:
            continue
        if any(_clean_add_sub_pass(result) for result in payload.values()):
            return True
    return False


def _selected_fit_steps(analysis: dict[str, Any]) -> int | None:
    fit = analysis.get("fit", {})
    for steps in FIT_STEPS:
        payload = fit.get(str(steps), {})
        if payload and any(_clean_add_sub_pass(result) for result in payload.values()):
            return steps
    return None


def _clean_add_sub_pass(summary: dict[str, Any]) -> bool:
    by_task = summary.get("by_task_type", {})
    add = _task_family_score(by_task, ".add")
    sub = _task_family_score(by_task, ".sub")
    return add >= 0.98 and sub >= 0.98


def _task_family_score(by_task: dict[str, float], needle: str) -> float:
    values = [score for task, score in by_task.items() if needle in task]
    return min(values) if values else 0.0


def _robustness_gate(analysis: dict[str, Any]) -> bool:
    robust = analysis.get("robustness", {})
    if robust.get("status") == "skipped":
        return False
    workspace = robust.get("workspace_relative", {})
    if not workspace:
        return False
    clean = workspace.get("clean", {}).get("final_nem", 0.0)
    values = []
    for family in FAMILIES:
        for length, result in workspace.get(family, {}).items():
            if int(length) <= 16:
                values.append(float(result.get("final_nem", 0.0)))
    return clean >= 0.98 and bool(values) and min(values) >= 0.95


def _relevant_context_gate(analysis: dict[str, Any]) -> bool:
    payload = analysis.get("relevant_context", {}).get("workspace_relevant", {})
    if not payload:
        return False
    relevant = payload.get("relevant_context", {}).get("final_nem", 0.0)
    oracle_chunks = payload.get("oracle_chunks", {}).get("final_nem", 0.0)
    return relevant >= 0.95 and oracle_chunks >= 0.95


def _summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("status") == "missing":
        return {"status": "missing", "final_nem": 0.0, "by_task_type": {}}
    overall = summary.get("overall", summary)
    by_task = summary.get("by_task_type", {})
    return {
        "status": "complete",
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "full_nem": float(overall.get("normalized_exact_match", 0.0)),
        "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
        "empty_prediction_rate": float(overall.get("empty_prediction_rate", 0.0)),
        "avg_tokens_generated": float(overall.get("avg_tokens_generated", 0.0)),
        "by_task_type": {
            key: float(value.get("final_normalized_exact_match", 0.0))
            for key, value in by_task.items()
        },
        "summary": summary,
    }


def _read_summary_payload(path: Path) -> dict[str, Any]:
    summary_path = path / "summary.json"
    if not summary_path.exists():
        return {"status": "missing", "final_nem": 0.0, "by_task_type": {}}
    return _summary_payload(_read_json(summary_path))


def _dataset_table(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    if manifest.get("status") == "missing":
        return "missing"
    rows = ["| item | value |", "|---|---:|"]
    for key in (
        "train_paired_irrelevant_count",
        "train_clean_fraction",
        "eval_clean_count",
        "prompt_intersections",
    ):
        rows.append(f"| {key} | {manifest.get(key)} |")
    return "\n".join(rows)


def _fit_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| steps | variant | clean overall | clean ADD | clean SUB | fit gate |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for steps, payload in analysis.get("fit", {}).items():
        for name, summary in payload.items():
            by_task = summary.get("by_task_type", {})
            rows.append(
                f"| {steps} | {name} | {summary.get('final_nem', 0.0):.4f} | "
                f"{_task_family_score(by_task, '.add'):.4f} | "
                f"{_task_family_score(by_task, '.sub'):.4f} | "
                f"{'pass' if _clean_add_sub_pass(summary) else 'fail'} |"
            )
    return "\n".join(rows)


def _robustness_table(analysis: dict[str, Any]) -> str:
    robust = analysis.get("robustness", {})
    if robust.get("status") == "skipped":
        return "skipped: fit gate did not pass"
    rows = [
        "| variant | clean | min<=16 | len32 min | len64 min | ADD clean | SUB clean |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in MODES:
        payload = robust.get(name, {})
        if not payload:
            continue
        by_task = payload.get("clean", {}).get("by_task_type", {})
        rows.append(
            f"| {name} | {payload.get('clean', {}).get('final_nem', 0.0):.4f} | "
            f"{_robustness_min(payload, max_length=16):.4f} | "
            f"{_robustness_at(payload, length=32):.4f} | "
            f"{_robustness_at(payload, length=64):.4f} | "
            f"{_task_family_score(by_task, '.add'):.4f} | "
            f"{_task_family_score(by_task, '.sub'):.4f} |"
        )
    return "\n".join(rows)


def _robustness_min(payload: dict[str, Any], *, max_length: int) -> float:
    values = []
    for family in FAMILIES:
        for length, result in payload.get(family, {}).items():
            if int(length) <= max_length:
                values.append(result.get("final_nem", 0.0))
    return min(values) if values else 0.0


def _robustness_at(payload: dict[str, Any], *, length: int) -> float:
    values = [
        payload.get(family, {}).get(str(length), {}).get("final_nem", 0.0)
        for family in FAMILIES
    ]
    return min(values) if values else 0.0


def _relevant_context_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("relevant_context", {})
    if payload.get("status") == "skipped":
        return "skipped: robustness gate did not pass"
    rows = ["| run | overall | ADD | SUB |", "|---|---:|---:|---:|"]
    for name, result in payload.items():
        summary = result.get("relevant_context", {})
        by_task = summary.get("by_task_type", {})
        rows.append(
            f"| {name} | {summary.get('final_nem', 0.0):.4f} | "
            f"{_task_family_score(by_task, '.add'):.4f} | "
            f"{_task_family_score(by_task, '.sub'):.4f} |"
        )
    return "\n".join(rows)


def _oracle_chunk_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("relevant_context", {})
    if payload.get("status") == "skipped":
        return "skipped: robustness gate did not pass"
    rows = ["| run | overall | ADD | SUB |", "|---|---:|---:|---:|"]
    for name, result in payload.items():
        summary = result.get("oracle_chunks", {})
        by_task = summary.get("by_task_type", {})
        rows.append(
            f"| {name} | {summary.get('final_nem', 0.0):.4f} | "
            f"{_task_family_score(by_task, '.add'):.4f} | "
            f"{_task_family_score(by_task, '.sub'):.4f} |"
        )
    return "\n".join(rows)


def _variable_binding_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("relevant_context", {})
    if payload.get("status") == "skipped":
        return "skipped: robustness/relevant-context gate did not pass"
    rows = ["| run | depth | distractors | final NEM |", "|---|---:|---:|---:|"]
    for name, result in payload.items():
        summary = result.get("variable_binding", {})
        by_task = summary.get("by_task_type", {})
        if not by_task:
            rows.append(f"| {name} | all | all | {summary.get('final_nem', 0.0):.4f} |")
            continue
        for task_type, score in sorted(by_task.items()):
            depth, distractors = _binding_task_labels(task_type)
            rows.append(f"| {name} | {depth} | {distractors} | {score:.4f} |")
    return "\n".join(rows)


def _consistency_table(_analysis: dict[str, Any]) -> str:
    return "skipped: consistency loss is only run after the base segmented model passes robustness/retrieval gates"


def _hard_mining_table(_analysis: dict[str, Any]) -> str:
    return "skipped: hard-distractor mining is only run after an initial robust segmented model exists"


def _learned_selector_table(analysis: dict[str, Any]) -> str:
    if not _robustness_gate(analysis):
        return "skipped: oracle workspace did not pass robustness gate"
    return "skipped: learned selector requires oracle chunks >= .95 after relevant-context training"


def _composition_table(analysis: dict[str, Any]) -> str:
    if not _robustness_gate(analysis):
        return "skipped: composition gate did not pass"
    return "skipped: ADD_SUB is only run after relevant retrieval and variable binding gates pass"


def _decision(analysis: dict[str, Any]) -> str:
    if not analysis.get("gates", {}).get("fit"):
        return (
            "OUTCOME D: no trained segmented model reached clean ADD/SUB fit within "
            "the 20k gate, so robustness conclusions are blocked by fit."
        )
    if not analysis.get("gates", {}).get("robustness"):
        return (
            "OUTCOME D: even models trained from scratch with segmented masks did "
            "not reach irrelevant-context robustness >= .95 through len16. Stop "
            "segment-mask direction before learned selectors."
        )
    if not analysis.get("gates", {}).get("relevant_context"):
        return (
            "OUTCOME A partial: training under workspace masks solves irrelevant "
            "distractor robustness, but oracle-access relevant context/chunk retrieval "
            "fails. Keep segmented workspace as the isolation architecture, but next "
            "work should target controlled retrieval/router training before learned "
            "selectors or composition."
        )
    return (
        "OUTCOME A/B candidate: trained segmented workspace passed the initial "
        "robustness gate; continue with relevant context and chunk selection."
    )


def _binding_task_labels(task_type: str) -> tuple[str, str]:
    depth = "?"
    distractors = "?"
    for part in task_type.split("."):
        if part.startswith("depth"):
            depth = part.removeprefix("depth")
        if part.startswith("distractors"):
            distractors = part.removeprefix("distractors")
    return depth, distractors


def _write_manifest(train_cases: list[Case], eval_cases: list[Case]) -> None:
    train_path = DATASET_DIR / "train" / "paired_irrelevant.jsonl"
    clean_eval_path = DATASET_DIR / "eval" / "clean.jsonl"
    train_records = _iter_jsonl(train_path)
    clean_count = sum(
        1 for record in train_records if record["metadata"]["family"] == "clean"
    )
    manifest = {
        "kind": "m181_trained_segmented_workspace",
        "seed": SEED,
        "model_config": "arithmetic_3m",
        "position_encoding": "relative",
        "numeric_tokenization": "digit_safe",
        "sequence_length": SEQUENCE_LENGTH,
        "fit_steps": list(FIT_STEPS),
        "families": list(FAMILIES),
        "train_lengths": list(TRAIN_LENGTHS),
        "eval_lengths": list(LENGTHS),
        "train_case_count": len(train_cases),
        "eval_case_count": len(eval_cases),
        "train_paired_irrelevant_count": len(train_records),
        "train_clean_fraction": clean_count / len(train_records),
        "eval_clean_count": len(_iter_jsonl(clean_eval_path)),
        "prompt_intersections": {
            "train_vs_clean_eval": len(_prompts(train_path) & _prompts(clean_eval_path))
        },
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


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


def _device_name(analysis: dict[str, Any]) -> str:
    for step_payload in analysis.get("fit", {}).values():
        for summary in step_payload.values():
            raw = summary.get("summary", {})
            if "device" in raw:
                return f"{raw.get('device')} ({raw.get('device_name')})"
    return "unknown"


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
