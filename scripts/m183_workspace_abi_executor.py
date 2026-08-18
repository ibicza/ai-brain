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
)
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm
from ai_brain.workspace_abi import (
    WorkspaceState,
    canonical_workspace_answer,
    parse_workspace_state,
    serialize_workspace_state,
    workspace_slot_scores,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m183_workspace_abi_executor"
RUNS_DIR = ROOT / "runs" / "m183_workspace_abi_executor"
DOC_PATH = ROOT / "docs" / "m183_workspace_abi_executor_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m183_workspace_abi_executor_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"
ROBUST_CHECKPOINT = (
    ROOT
    / "runs"
    / "m181_trained_segmented_workspace"
    / "fit"
    / "workspace_relative_20000"
    / "checkpoints"
    / "step_020000.pt"
)

SEED = 18300
SEQUENCE_LENGTH = 256
FINAL_MAX_NEW_TOKENS = 32
WORKSPACE_MAX_NEW_TOKENS = 64
TRAIN_PER_OP = 1600
EVAL_PER_OP = 100
BRIDGE_TRAIN_PER_OP = 800
EXECUTOR_STEPS = 10000
BRIDGE_STEPS = 6000
BINDING_BRIDGE_STEPS = 6000
ORACLE_BRIDGE_STEPS = 6000
JUNK_TRAIN_COUNTS = (0, 1, 2, 4, 8)
JUNK_EVAL_COUNTS = (0, 1, 2, 4, 8, 16, 32)
DISTRACTOR_COUNTS_TRAIN = (0, 1, 2, 4)
DISTRACTOR_COUNTS_EVAL = (0, 1, 2, 4, 8, 16)

Primitive = Literal["add", "sub"]


@dataclass(frozen=True)
class Case:
    op: Primitive
    a: int
    b: int

    @property
    def sign(self) -> str:
        return "+" if self.op == "add" else "-"

    @property
    def op_token(self) -> str:
        return "ADD" if self.op == "add" else "SUB"

    @property
    def result(self) -> int:
        return self.a + self.b if self.op == "add" else self.a - self.b

    @property
    def workspace(self) -> WorkspaceState:
        return WorkspaceState(op=self.op, a=self.a, b=self.b)

    @property
    def key(self) -> str:
        return f"{self.op}:{self.a}:{self.b}"

    @property
    def carry_bucket(self) -> str:
        if self.op == "sub":
            return "borrow" if self.a % 10 < self.b % 10 else "no_borrow"
        units_carry = self.a % 10 + self.b % 10 >= 10
        final_carry = self.a + self.b >= 100
        if final_carry:
            return "final_carry"
        if units_carry:
            return "units_carry"
        return "no_carry"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-executor")
    subparsers.add_parser("run-bridge")
    subparsers.add_parser("run-binding-bridge")
    subparsers.add_parser("run-oracle-bridge")
    subparsers.add_parser("run-pipeline")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-executor":
        run_executor()
    elif args.command == "run-bridge":
        run_bridge()
    elif args.command == "run-binding-bridge":
        run_binding_bridge()
    elif args.command == "run-oracle-bridge":
        run_oracle_bridge()
    elif args.command == "run-pipeline":
        run_pipeline()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_executor()
        analyze_all()
        if _executor_gate(_read_json(RUNS_DIR / "analysis.json")):
            run_bridge()
            run_binding_bridge()
            run_oracle_bridge()
            run_pipeline()
            analyze_all()
        build_report(checks_passed=False)
    return 0


def prepare_datasets() -> None:
    if DATASET_DIR.exists():
        shutil.rmtree(DATASET_DIR)
    rng = random.Random(SEED)
    train_cases = interleave_balanced(
        *_generate_balanced_cases(TRAIN_PER_OP, rng=rng, low=10, high=89)
    )
    train_keys = {case.key for case in train_cases}
    seen_cases = interleave_balanced(
        *_generate_balanced_cases(
            EVAL_PER_OP,
            rng=rng,
            low=10,
            high=89,
            exclude=train_keys,
        )
    )
    unseen_cases = interleave_balanced(
        *_generate_balanced_cases(
            EVAL_PER_OP,
            rng=rng,
            low=10,
            high=89,
            exclude=train_keys | {case.key for case in seen_cases},
        )
    )
    heldout_cases = interleave_balanced(
        *_generate_balanced_cases(EVAL_PER_OP, rng=rng, low=90, high=109)
    )

    _write_jsonl(
        DATASET_DIR / "train" / "executor_equivalence.jsonl",
        [
            record
            for case in train_cases
            for record in (
                _standalone_executor_record(case, split="train", variant="train"),
                _workspace_executor_record(case, split="train", variant="train"),
            )
        ],
    )
    for name, cases in (
        ("seen", seen_cases),
        ("unseen", unseen_cases),
        ("heldout_operands", heldout_cases),
    ):
        _write_jsonl(
            DATASET_DIR / "eval" / "executor" / f"standalone_{name}.jsonl",
            [
                _standalone_executor_record(case, split="eval", variant=name)
                for case in cases
            ],
        )
        _write_jsonl(
            DATASET_DIR / "eval" / "executor" / f"workspace_{name}.jsonl",
            [
                _workspace_executor_record(case, split="eval", variant=name)
                for case in cases
            ],
        )

    bridge_train_cases = train_cases[: BRIDGE_TRAIN_PER_OP * 2]
    _write_jsonl(
        DATASET_DIR / "train" / "bridge_relevant_to_workspace.jsonl",
        _bridge_records(bridge_train_cases, split="train", variant="train"),
    )
    for name, cases in (
        ("seen", seen_cases),
        ("unseen", unseen_cases),
        ("heldout_operands", heldout_cases),
        ("mixed", unseen_cases),
    ):
        _write_jsonl(
            DATASET_DIR / "eval" / "bridge" / f"{name}.jsonl",
            _bridge_records(
                cases,
                split="eval",
                variant=name,
                mixed_irrelevant=name == "mixed",
            ),
        )

    _write_jsonl(
        DATASET_DIR / "train" / "binding_to_workspace.jsonl",
        _binding_bridge_records(train=True),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "binding_to_workspace.jsonl",
        _binding_bridge_records(train=False),
    )

    oracle_train: list[dict[str, Any]] = []
    for junk_count in JUNK_TRAIN_COUNTS:
        oracle_train.extend(
            _oracle_bridge_records(
                bridge_train_cases,
                split="train",
                junk_count=junk_count,
                heldout=False,
            )
        )
    _write_jsonl(
        DATASET_DIR / "train" / "oracle_chunk_to_workspace.jsonl", oracle_train
    )
    for junk_count in JUNK_EVAL_COUNTS:
        _write_jsonl(
            DATASET_DIR / "eval" / "oracle_bridge" / f"junk_{junk_count}.jsonl",
            _oracle_bridge_records(
                unseen_cases,
                split="eval",
                junk_count=junk_count,
                heldout=True,
            ),
        )

    _write_manifest()


def run_executor() -> None:
    _ensure_robust_checkpoint()
    checkpoint = _run_train(
        name="canonical_executor",
        train_path=DATASET_DIR / "train" / "executor_equivalence.jsonl",
        eval_path=DATASET_DIR / "eval" / "executor" / "workspace_seen.jsonl",
        steps=EXECUTOR_STEPS,
        seed=SEED + 100,
        run_group="executor",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    for prefix in ("standalone", "workspace"):
        for name in ("seen", "unseen", "heldout_operands"):
            _eval_checkpoint(
                checkpoint=checkpoint,
                output_dir=RUNS_DIR
                / "executor"
                / "canonical_executor"
                / "benchmark"
                / f"{prefix}_{name}",
                eval_path=DATASET_DIR / "eval" / "executor" / f"{prefix}_{name}.jsonl",
                max_new_tokens=FINAL_MAX_NEW_TOKENS,
            )


def run_bridge() -> None:
    checkpoint = _run_train(
        name="relevant_to_workspace",
        train_path=DATASET_DIR / "train" / "bridge_relevant_to_workspace.jsonl",
        eval_path=DATASET_DIR / "eval" / "bridge" / "seen.jsonl",
        steps=BRIDGE_STEPS,
        seed=SEED + 200,
        run_group="bridge",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    for name in ("seen", "unseen", "heldout_operands", "mixed"):
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=RUNS_DIR
            / "bridge"
            / "relevant_to_workspace"
            / "benchmark"
            / name,
            eval_path=DATASET_DIR / "eval" / "bridge" / f"{name}.jsonl",
            max_new_tokens=WORKSPACE_MAX_NEW_TOKENS,
            score_workspace=True,
        )


def run_binding_bridge() -> None:
    checkpoint = _run_train(
        name="binding_to_workspace",
        train_path=DATASET_DIR / "train" / "binding_to_workspace.jsonl",
        eval_path=DATASET_DIR / "eval" / "binding_to_workspace.jsonl",
        steps=BINDING_BRIDGE_STEPS,
        seed=SEED + 300,
        run_group="binding_bridge",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    _eval_checkpoint(
        checkpoint=checkpoint,
        output_dir=RUNS_DIR
        / "binding_bridge"
        / "binding_to_workspace"
        / "benchmark"
        / "binding_to_workspace",
        eval_path=DATASET_DIR / "eval" / "binding_to_workspace.jsonl",
        max_new_tokens=WORKSPACE_MAX_NEW_TOKENS,
        score_workspace=True,
    )


def run_oracle_bridge() -> None:
    checkpoint = _run_train(
        name="oracle_chunk_to_workspace",
        train_path=DATASET_DIR / "train" / "oracle_chunk_to_workspace.jsonl",
        eval_path=DATASET_DIR / "eval" / "oracle_bridge" / "junk_0.jsonl",
        steps=ORACLE_BRIDGE_STEPS,
        seed=SEED + 400,
        run_group="oracle_bridge",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    for junk_count in JUNK_EVAL_COUNTS:
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=RUNS_DIR
            / "oracle_bridge"
            / "oracle_chunk_to_workspace"
            / "benchmark"
            / f"junk_{junk_count}",
            eval_path=DATASET_DIR
            / "eval"
            / "oracle_bridge"
            / f"junk_{junk_count}.jsonl",
            max_new_tokens=WORKSPACE_MAX_NEW_TOKENS,
            score_workspace=True,
        )


def run_pipeline() -> None:
    executor = _checkpoint_path(
        RUNS_DIR / "executor" / "canonical_executor", EXECUTOR_STEPS
    )
    bridge = _checkpoint_path(
        RUNS_DIR / "bridge" / "relevant_to_workspace", BRIDGE_STEPS
    )
    binding_bridge = _checkpoint_path(
        RUNS_DIR / "binding_bridge" / "binding_to_workspace",
        BINDING_BRIDGE_STEPS,
    )
    _eval_two_phase(
        bridge_checkpoint=bridge,
        executor_checkpoint=executor,
        eval_path=DATASET_DIR / "eval" / "bridge" / "heldout_operands.jsonl",
        output_dir=RUNS_DIR / "pipeline" / "relevant_heldout",
    )
    _eval_two_phase(
        bridge_checkpoint=binding_bridge,
        executor_checkpoint=executor,
        eval_path=DATASET_DIR / "eval" / "binding_to_workspace.jsonl",
        output_dir=RUNS_DIR / "pipeline" / "binding",
    )


def analyze_all() -> None:
    analysis = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "executor": _collect_executor(),
        "bridge": _collect_bridge(),
        "binding_bridge": _collect_binding_bridge(),
        "oracle_bridge": _collect_oracle_bridge(),
        "pipeline": _collect_pipeline(),
        "gates": {},
    }
    analysis["gates"]["executor"] = _executor_gate(analysis)
    analysis["gates"]["bridge"] = _bridge_gate(analysis)
    analysis["gates"]["binding_bridge"] = _binding_bridge_gate(analysis)
    analysis["gates"]["oracle_bridge"] = _oracle_bridge_gate(analysis)
    analysis["decision"] = _decision(analysis)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    lines = [
        "# M-18.3 Canonical Workspace ABI Executor Report",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        f"- device: `{_device_name(analysis)}`",
        "",
        "## Canonical Workspace ABI",
        "",
        "Canonical state is source-invariant:",
        "",
        "```text",
        serialize_workspace_state(WorkspaceState(op="add", a=27, b=35)),
        "```",
        "",
        "## Dataset Verification",
        "",
        _dataset_table(analysis),
        "",
        "## Canonical Symbolic vs Workspace Arithmetic Equivalence",
        "",
        _executor_equivalence_table(analysis),
        "",
        "## Teacher-Forced Workspace Upper Bound",
        "",
        _workspace_upper_bound_table(analysis),
        "",
        "## Retrieval -> Workspace Parse",
        "",
        _workspace_generation_table(
            analysis.get("bridge", {}), ("seen", "unseen", "heldout_operands", "mixed")
        ),
        "",
        "## Executor Given Workspace",
        "",
        _executor_given_workspace_table(analysis),
        "",
        "## End-To-End Relevant Arithmetic",
        "",
        _pipeline_table(analysis, "relevant_heldout"),
        "",
        "## Heldout Operands",
        "",
        _heldout_table(analysis),
        "",
        "## Binding Depth -> Workspace -> Final",
        "",
        _binding_table(analysis),
        "",
        "## Oracle Chunk -> Workspace -> Final",
        "",
        _oracle_table(analysis),
        "",
        "## Shared vs Frozen Executor Retention",
        "",
        _retention_table(analysis),
        "",
        "## ADD_SUB",
        "",
        _composition_status(analysis),
        "",
        "## Held-Out SUB_ADD",
        "",
        _heldout_composition_status(analysis),
        "",
        "## Decision",
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
    seed: int,
    run_group: str,
    init_checkpoint: Path | None,
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
        segment_attention_mode="workspace",
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
    max_new_tokens: int,
    score_workspace: bool = False,
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
                max_new_tokens=max_new_tokens,
                device=device_info.device,
                numeric_tokenization="digit_safe",
                segment_ids=segment_ids,
                context_access_mask=context_access,
                segment_attention_mode="workspace",
            )
            raw_generation = tokenizer.decode(generated_ids, skip_special_tokens=False)
            prediction = _prediction_payload(
                record,
                index,
                raw_generation,
                generated_ids,
                score_workspace=score_workspace,
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


@torch.no_grad()
def _eval_two_phase(
    *,
    bridge_checkpoint: Path,
    executor_checkpoint: Path,
    eval_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    summary_path = output_dir / "summary.json"
    if summary_path.exists():
        return _read_json(summary_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    device_info = get_device_info()
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    bridge_model, bridge_loaded = load_model_for_inference(
        checkpoint_path=bridge_checkpoint,
        tokenizer_path=TOKENIZER_PATH,
        device=device_info.device,
    )
    executor_model, executor_loaded = load_model_for_inference(
        checkpoint_path=executor_checkpoint,
        tokenizer_path=TOKENIZER_PATH,
        device=device_info.device,
    )
    rows = []
    predictions_path = output_dir / "predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as file:
        for index, record in enumerate(_iter_jsonl(eval_path)):
            expected_workspace = parse_workspace_state(str(record["answer"]))
            if expected_workspace is None:
                raise ValueError(
                    f"Pipeline eval expects workspace target: {record['id']}"
                )
            bridge_segments, bridge_access = _segment_tensors_for_inference(
                tokenizer=tokenizer,
                record=record,
                device=device_info.device,
            )
            bridge_ids = generate_answer_ids(
                model=bridge_model,
                tokenizer=tokenizer,
                prompt=str(record["prompt"]),
                max_new_tokens=WORKSPACE_MAX_NEW_TOKENS,
                device=device_info.device,
                numeric_tokenization="digit_safe",
                segment_ids=bridge_segments,
                context_access_mask=bridge_access,
                segment_attention_mode="workspace",
            )
            bridge_text = extract_generated_answer(
                tokenizer.decode(bridge_ids, skip_special_tokens=False)
            )
            predicted_workspace = parse_workspace_state(bridge_text)
            generated_workspace_text = (
                serialize_workspace_state(predicted_workspace)
                if predicted_workspace is not None
                else bridge_text
            )
            executor_record = _workspace_executor_record(
                Case(
                    op=expected_workspace.op,
                    a=expected_workspace.a,
                    b=expected_workspace.b,
                ),
                split="pipeline",
                variant="generated",
                prompt_override=generated_workspace_text,
            )
            executor_segments, executor_access = _segment_tensors_for_inference(
                tokenizer=tokenizer,
                record=executor_record,
                device=device_info.device,
            )
            final_ids = generate_answer_ids(
                model=executor_model,
                tokenizer=tokenizer,
                prompt=str(executor_record["prompt"]),
                max_new_tokens=FINAL_MAX_NEW_TOKENS,
                device=device_info.device,
                numeric_tokenization="digit_safe",
                segment_ids=executor_segments,
                context_access_mask=executor_access,
                segment_attention_mode="workspace",
            )
            raw_final = tokenizer.decode(final_ids, skip_special_tokens=False)
            final_prediction = _prediction_payload(
                executor_record,
                index,
                raw_final,
                final_ids,
                score_workspace=False,
            )
            slot_scores = workspace_slot_scores(
                expected=expected_workspace,
                predicted=predicted_workspace,
            )
            row = {
                "id": str(record.get("id", index)),
                "task_type": str(record["task_type"]),
                "workspace_text": bridge_text,
                "workspace_correct": slot_scores["workspace_exact"],
                "op_exact": slot_scores["op_exact"],
                "a_exact": slot_scores["a_exact"],
                "b_exact": slot_scores["b_exact"],
                "final_expected": final_prediction["final_expected"],
                "final_predicted": final_prediction["final_predicted"],
                "final_normalized_exact_match": final_prediction[
                    "final_normalized_exact_match"
                ],
            }
            rows.append(row)
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    count = len(rows) or 1
    summary = {
        "count": len(rows),
        "workspace_exact": sum(row["workspace_correct"] for row in rows) / count,
        "op_exact": sum(row["op_exact"] for row in rows) / count,
        "a_exact": sum(row["a_exact"] for row in rows) / count,
        "b_exact": sum(row["b_exact"] for row in rows) / count,
        "end_to_end_final_nem": sum(row["final_normalized_exact_match"] for row in rows)
        / count,
        "bridge_checkpoint_step": bridge_loaded.get("step"),
        "executor_checkpoint_step": executor_loaded.get("step"),
        "predictions_path": str(predictions_path),
        "device": str(device_info.device),
        "device_name": device_info.name,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def _standalone_executor_record(
    case: Case, *, split: str, variant: str
) -> dict[str, Any]:
    prompt = f"{case.op_token} {case.a:02d} {case.sign} {case.b:02d}"
    return _record_with_spans(
        record_id=f"m183.{split}.standalone.{variant}.{case.op}.{case.a}.{case.b}",
        task_type=f"m183.executor.standalone.{case.op}.{case.carry_bucket}",
        prompt=prompt,
        answer=f"FINAL {case.result}",
        spans=[("query", 0, len(prompt), False)],
        metadata=_case_metadata(case, kind="standalone", variant=variant),
    )


def _workspace_executor_record(
    case: Case,
    *,
    split: str,
    variant: str,
    prompt_override: str | None = None,
) -> dict[str, Any]:
    prompt = prompt_override or serialize_workspace_state(case.workspace)
    return _record_with_spans(
        record_id=f"m183.{split}.workspace.{variant}.{case.op}.{case.a}.{case.b}",
        task_type=f"m183.executor.workspace.{case.op}.{case.carry_bucket}",
        prompt=prompt,
        answer=f"FINAL {case.result}",
        spans=[("workspace", 0, len(prompt), False)],
        metadata=_case_metadata(case, kind="workspace", variant=variant),
    )


def _bridge_records(
    cases: list[Case],
    *,
    split: str,
    variant: str,
    mixed_irrelevant: bool = False,
) -> list[dict[str, Any]]:
    records = []
    for index, case in enumerate(cases):
        lines = [f"A = {case.a:02d}", f"B = {case.b:02d}"]
        access = [True, True]
        if mixed_irrelevant:
            lines = [
                f"J0 = {(case.a + 17 + index) % 100:02d}",
                lines[0],
                f"OLD {case.op_token} {case.b:02d} {case.sign} {(case.a + 9) % 100:02d}",
                lines[1],
                f"J1 = {(case.a + case.b + 23 + index) % 100:02d}",
            ]
            access = [False, True, False, True, False]
        query = f"QUERY {case.op_token} A B"
        records.append(
            _context_record(
                record_id=f"m183.{split}.bridge.{variant}.{case.op}.{index:06d}",
                task_type=f"m183.bridge.relevant.{case.op}.{case.carry_bucket}",
                context_lines=lines,
                access_flags=access,
                query=query,
                answer=canonical_workspace_answer(case.op, case.a, case.b),
                metadata=_case_metadata(case, kind="bridge", variant=variant),
            )
        )
    assert_balanced_ops(records, dataset_name=f"bridge.{split}.{variant}")
    return records


def _binding_bridge_records(*, train: bool) -> list[dict[str, Any]]:
    rng = random.Random(SEED + (600 if train else 700))
    records = []
    depths = (1, 2, 3) if train else (1, 2, 3, 4)
    distractor_counts = DISTRACTOR_COUNTS_TRAIN if train else DISTRACTOR_COUNTS_EVAL
    count = 50 if train else 15
    for depth in depths:
        for distractors in distractor_counts:
            for index in range(count):
                op: Primitive = "add" if index % 2 == 0 else "sub"
                a_value = 10 + rng.randrange(80)
                b_value = 10 + rng.randrange(80)
                if op == "sub" and a_value < b_value:
                    a_value, b_value = b_value, a_value
                names = [chr(ord("X") + step) for step in range(depth + 1)]
                lines = [f"{names[0]} = {a_value:02d}"]
                lines.extend(
                    f"{names[step]} = {names[step - 1]}"
                    for step in range(1, len(names))
                )
                lines.append(f"B = {b_value:02d}")
                access = [True] * len(lines)
                for junk in range(distractors):
                    insert_at = 1 + ((junk * 2) % len(lines))
                    lines.insert(insert_at, f"J{junk} = {10 + rng.randrange(80):02d}")
                    access.insert(insert_at, False)
                case = Case(op=op, a=a_value, b=b_value)
                query = f"QUERY {case.op_token} {names[-1]} B"
                records.append(
                    _context_record(
                        record_id=f"m183.binding_bridge.{'train' if train else 'eval'}.d{depth}.x{distractors}.{index:05d}",
                        task_type=f"m183.binding_bridge.depth{depth}.distractors{distractors}.{op}",
                        context_lines=lines,
                        access_flags=access,
                        query=query,
                        answer=canonical_workspace_answer(op, a_value, b_value),
                        metadata={
                            **_case_metadata(
                                case,
                                kind="binding_bridge",
                                variant="train" if train else "eval",
                            ),
                            "depth": depth,
                            "distractors": distractors,
                        },
                    )
                )
    return records


def _oracle_bridge_records(
    cases: list[Case],
    *,
    split: str,
    junk_count: int,
    heldout: bool,
) -> list[dict[str, Any]]:
    records = []
    for index, case in enumerate(cases):
        lines = [f"A = {case.a:02d}", f"B = {case.b:02d}"]
        access = [True, True]
        prefix = "HX" if heldout else "K"
        for junk in range(junk_count):
            insert_at = 1 + ((junk * 2) % len(lines))
            value = (
                case.a * (junk + 3) + case.b + index + (19 if heldout else 7)
            ) % 100
            lines.insert(insert_at, f"{prefix}{junk} = {value:02d}")
            access.insert(insert_at, False)
        query = f"QUERY {case.op_token} A B"
        records.append(
            _context_record(
                record_id=f"m183.{split}.oracle_bridge.j{junk_count}.{case.op}.{index:06d}",
                task_type=f"m183.oracle_bridge.junk{junk_count}.{case.op}",
                context_lines=lines,
                access_flags=access,
                query=query,
                answer=canonical_workspace_answer(case.op, case.a, case.b),
                metadata={
                    **_case_metadata(case, kind="oracle_bridge", variant=split),
                    "junk_count": junk_count,
                    "heldout": heldout,
                },
            )
        )
    assert_balanced_ops(records, dataset_name=f"oracle_bridge.{split}.junk{junk_count}")
    return records


def _context_record(
    *,
    record_id: str,
    task_type: str,
    context_lines: list[str],
    access_flags: list[bool],
    query: str,
    answer: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    context = "\n".join(context_lines)
    prompt = f"{context}\n{query}"
    spans = []
    cursor = 0
    for line, access in zip(context_lines, access_flags, strict=True):
        spans.append(("context", cursor, cursor + len(line), access))
        cursor += len(line) + 1
    spans.append(("query", len(context) + 1, len(prompt), False))
    return _record_with_spans(
        record_id=record_id,
        task_type=task_type,
        prompt=prompt,
        answer=answer,
        spans=spans,
        metadata=metadata,
    )


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
            "segment_schema": "m183.v1",
            "segment_spans": [
                {"segment": segment, "start": start, "end": end, "access": access}
                for segment, start, end, access in spans
            ],
        },
    }


def _case_metadata(case: Case, *, kind: str, variant: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "variant": variant,
        "op": case.op,
        "a": case.a,
        "b": case.b,
        "answer_value": case.result,
        "carry_bucket": case.carry_bucket,
    }


def _generate_balanced_cases(
    count_per_op: int,
    *,
    rng: random.Random,
    low: int,
    high: int,
    exclude: set[str] | None = None,
) -> tuple[list[Case], list[Case]]:
    excluded = exclude or set()
    add_cases = _generate_op_cases(
        "add",
        count_per_op,
        rng=rng,
        low=low,
        high=high,
        excluded=excluded,
    )
    sub_cases = _generate_op_cases(
        "sub",
        count_per_op,
        rng=rng,
        low=low,
        high=high,
        excluded=excluded | {case.key for case in add_cases},
    )
    return add_cases, sub_cases


def _generate_op_cases(
    op: Primitive,
    count: int,
    *,
    rng: random.Random,
    low: int,
    high: int,
    excluded: set[str],
) -> list[Case]:
    cases: list[Case] = []
    used: set[str] = set()
    attempts = 0
    while len(cases) < count:
        attempts += 1
        if attempts > count * 500:
            raise RuntimeError(f"Could not generate enough {op} cases")
        a = rng.randint(low, high)
        b = rng.randint(low, high)
        if op == "sub" and a < b:
            a, b = b, a
        case = Case(op=op, a=a, b=b)
        if case.key in used or case.key in excluded:
            continue
        used.add(case.key)
        cases.append(case)
    return cases


def interleave_balanced(add_cases: list[Case], sub_cases: list[Case]) -> list[Case]:
    if len(add_cases) != len(sub_cases):
        raise ValueError("ADD/SUB case lists must be equal length")
    cases: list[Case] = []
    for add_case, sub_case in zip(add_cases, sub_cases, strict=True):
        if add_case.op != "add" or sub_case.op != "sub":
            raise ValueError("Expected explicit ADD and SUB lists")
        cases.extend([add_case, sub_case])
    return cases


def assert_balanced_ops(records: list[dict[str, Any]], *, dataset_name: str) -> None:
    counts = Counter(str(record.get("metadata", {}).get("op")) for record in records)
    if counts.get("add", 0) != counts.get("sub", 0):
        raise ValueError(f"{dataset_name} must be ADD/SUB balanced: {dict(counts)}")


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
    spans: list[dict[str, Any]],
    start: int,
    end: int,
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
    score_workspace: bool,
) -> dict[str, Any]:
    predicted = extract_generated_answer(raw_generation)
    expected = str(record["answer"])
    final_expected = extract_final_answer(expected)
    final_predicted = extract_final_answer(predicted)
    payload = {
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
    if score_workspace:
        expected_state = parse_workspace_state(expected)
        if expected_state is None:
            raise ValueError(f"Expected workspace state in record: {record['id']}")
        predicted_state = parse_workspace_state(predicted)
        payload.update(
            workspace_slot_scores(expected=expected_state, predicted=predicted_state)
        )
    return payload


def _summarize(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_predictions(predictions)
    for key, payload in summary["by_task_type"].items():
        _add_extra_stats(
            payload,
            [
                prediction
                for prediction in predictions
                if prediction["task_type"] == key
            ],
        )
    _add_extra_stats(summary["overall"], predictions)
    if predictions and "workspace_exact" in predictions[0]:
        summary["workspace"] = _workspace_summary(predictions)
    return summary


def _add_extra_stats(
    payload: dict[str, Any], predictions: list[dict[str, Any]]
) -> None:
    count = len(predictions)
    payload["empty_prediction_rate"] = (
        sum(not prediction["predicted"].strip() for prediction in predictions) / count
        if count
        else 0.0
    )
    payload["avg_tokens_generated"] = (
        sum(float(prediction["tokens_generated"]) for prediction in predictions) / count
        if count
        else 0.0
    )


def _workspace_summary(predictions: list[dict[str, Any]]) -> dict[str, float]:
    count = len(predictions) or 1
    return {
        key: sum(bool(prediction.get(key)) for prediction in predictions) / count
        for key in ("op_exact", "a_exact", "b_exact", "workspace_exact")
    }


def _summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("status") == "missing":
        return {"status": "missing", "final_nem": 0.0, "by_task_type": {}}
    overall = summary.get("overall", summary)
    by_task = summary.get("by_task_type", {})
    return {
        "status": "complete",
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "full_nem": float(overall.get("normalized_exact_match", 0.0)),
        "workspace": summary.get("workspace", {}),
        "by_task_type": {
            key: float(value.get("final_normalized_exact_match", 0.0))
            for key, value in by_task.items()
        },
        "summary": summary,
    }


def _collect_executor() -> dict[str, Any]:
    base = RUNS_DIR / "executor" / "canonical_executor" / "benchmark"
    if not base.exists():
        return {"status": "missing"}
    return {
        name: _read_summary_payload(base / name)
        for name in (
            "standalone_seen",
            "standalone_unseen",
            "standalone_heldout_operands",
            "workspace_seen",
            "workspace_unseen",
            "workspace_heldout_operands",
        )
    }


def _collect_bridge() -> dict[str, Any]:
    base = RUNS_DIR / "bridge" / "relevant_to_workspace" / "benchmark"
    if not base.exists():
        return {"status": "skipped"}
    return {
        name: _read_summary_payload(base / name)
        for name in ("seen", "unseen", "heldout_operands", "mixed")
    }


def _collect_binding_bridge() -> dict[str, Any]:
    base = RUNS_DIR / "binding_bridge" / "binding_to_workspace" / "benchmark"
    if not base.exists():
        return {"status": "skipped"}
    return {
        "binding_to_workspace": _read_summary_payload(base / "binding_to_workspace")
    }


def _collect_oracle_bridge() -> dict[str, Any]:
    base = RUNS_DIR / "oracle_bridge" / "oracle_chunk_to_workspace" / "benchmark"
    if not base.exists():
        return {"status": "skipped"}
    return {
        f"junk_{junk_count}": _read_summary_payload(base / f"junk_{junk_count}")
        for junk_count in JUNK_EVAL_COUNTS
    }


def _collect_pipeline() -> dict[str, Any]:
    result = {}
    for name in ("relevant_heldout", "binding"):
        path = RUNS_DIR / "pipeline" / name / "summary.json"
        if path.exists():
            result[name] = _read_json(path)
    return result or {"status": "skipped"}


def _executor_gate(analysis: dict[str, Any]) -> bool:
    executor = analysis.get("executor", {})
    workspace = executor.get("workspace_heldout_operands", {})
    by_task = workspace.get("by_task_type", {})
    return (
        workspace.get("final_nem", 0.0) >= 0.98
        and _task_score(by_task, ".add.") >= 0.98
        and _task_score(by_task, ".sub.") >= 0.98
    )


def _bridge_gate(analysis: dict[str, Any]) -> bool:
    bridge = analysis.get("bridge", {})
    heldout = bridge.get("heldout_operands", {})
    workspace = heldout.get("workspace", {})
    return workspace.get("workspace_exact", 0.0) >= 0.98


def _binding_bridge_gate(analysis: dict[str, Any]) -> bool:
    payload = (
        analysis.get("binding_bridge", {})
        .get("binding_to_workspace", {})
        .get("workspace", {})
    )
    return payload.get("workspace_exact", 0.0) >= 0.95


def _oracle_bridge_gate(analysis: dict[str, Any]) -> bool:
    oracle = analysis.get("oracle_bridge", {})
    if oracle.get("status") == "skipped":
        return False
    return all(
        oracle.get(f"junk_{junk_count}", {})
        .get("workspace", {})
        .get("workspace_exact", 0.0)
        >= 0.95
        for junk_count in (0, 1, 2, 4, 8, 16)
    )


def _task_score(by_task: dict[str, float], needle: str) -> float:
    values = [score for task, score in by_task.items() if needle in task]
    return min(values) if values else 0.0


def _dataset_table(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    if manifest.get("status") == "missing":
        return "missing"
    rows = ["| item | value |", "|---|---:|"]
    for key in (
        "executor_train_count",
        "bridge_train_count",
        "binding_bridge_train_count",
        "oracle_bridge_train_count",
        "prompt_intersections",
    ):
        rows.append(f"| {key} | {manifest.get(key)} |")
    return "\n".join(rows)


def _executor_equivalence_table(analysis: dict[str, Any]) -> str:
    executor = analysis.get("executor", {})
    if executor.get("status") == "missing":
        return "missing"
    rows = [
        "| split | standalone | workspace | gap |",
        "|---|---:|---:|---:|",
    ]
    for name in ("seen", "unseen", "heldout_operands"):
        standalone = executor.get(f"standalone_{name}", {}).get("final_nem", 0.0)
        workspace = executor.get(f"workspace_{name}", {}).get("final_nem", 0.0)
        rows.append(
            f"| {name} | {standalone:.4f} | {workspace:.4f} | {abs(standalone - workspace):.4f} |"
        )
    return "\n".join(rows)


def _workspace_upper_bound_table(analysis: dict[str, Any]) -> str:
    executor = analysis.get("executor", {})
    if executor.get("status") == "missing":
        return "missing"
    rows = ["| split | overall | ADD | SUB |", "|---|---:|---:|---:|"]
    for name in ("seen", "unseen", "heldout_operands"):
        payload = executor.get(f"workspace_{name}", {})
        by_task = payload.get("by_task_type", {})
        rows.append(
            f"| {name} | {payload.get('final_nem', 0.0):.4f} | "
            f"{_task_score(by_task, '.add.'):.4f} | "
            f"{_task_score(by_task, '.sub.'):.4f} |"
        )
    return "\n".join(rows)


def _workspace_generation_table(payload: dict[str, Any], names: tuple[str, ...]) -> str:
    if payload.get("status") in {"missing", "skipped"}:
        return payload.get("status", "skipped")
    rows = [
        "| eval | workspace exact | OP | A | B | final/string NEM |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in names:
        summary = payload.get(name, {})
        workspace = summary.get("workspace", {})
        rows.append(
            f"| {name} | {workspace.get('workspace_exact', 0.0):.4f} | "
            f"{workspace.get('op_exact', 0.0):.4f} | "
            f"{workspace.get('a_exact', 0.0):.4f} | "
            f"{workspace.get('b_exact', 0.0):.4f} | "
            f"{summary.get('full_nem', 0.0):.4f} |"
        )
    return "\n".join(rows)


def _executor_given_workspace_table(analysis: dict[str, Any]) -> str:
    if not _executor_gate(analysis):
        return (
            "blocked: teacher-forced workspace executor did not pass heldout .98 gate"
        )
    return _workspace_upper_bound_table(analysis)


def _pipeline_table(analysis: dict[str, Any], name: str) -> str:
    pipeline = analysis.get("pipeline", {})
    if pipeline.get("status") == "skipped" or name not in pipeline:
        return "skipped: upstream gate did not pass"
    summary = pipeline[name]
    rows = ["| metric | score |", "|---|---:|"]
    for key in (
        "workspace_exact",
        "op_exact",
        "a_exact",
        "b_exact",
        "end_to_end_final_nem",
    ):
        rows.append(f"| {key} | {summary.get(key, 0.0):.4f} |")
    return "\n".join(rows)


def _heldout_table(analysis: dict[str, Any]) -> str:
    rows = ["| component | heldout score |", "|---|---:|"]
    rows.append(
        f"| workspace executor | {analysis.get('executor', {}).get('workspace_heldout_operands', {}).get('final_nem', 0.0):.4f} |"
    )
    rows.append(
        f"| retrieval->workspace | {analysis.get('bridge', {}).get('heldout_operands', {}).get('workspace', {}).get('workspace_exact', 0.0):.4f} |"
    )
    rows.append(
        f"| end-to-end final | {analysis.get('pipeline', {}).get('relevant_heldout', {}).get('end_to_end_final_nem', 0.0):.4f} |"
    )
    return "\n".join(rows)


def _binding_table(analysis: dict[str, Any]) -> str:
    bridge = analysis.get("binding_bridge", {})
    if bridge.get("status") == "skipped":
        return "skipped: executor gate did not pass"
    rows = ["| component | score |", "|---|---:|"]
    summary = bridge.get("binding_to_workspace", {})
    workspace = summary.get("workspace", {})
    rows.append(
        f"| binding->workspace exact | {workspace.get('workspace_exact', 0.0):.4f} |"
    )
    rows.append(
        f"| binding end-to-end final | {analysis.get('pipeline', {}).get('binding', {}).get('end_to_end_final_nem', 0.0):.4f} |"
    )
    return "\n".join(rows)


def _oracle_table(analysis: dict[str, Any]) -> str:
    oracle = analysis.get("oracle_bridge", {})
    if oracle.get("status") == "skipped":
        return "skipped: executor gate did not pass"
    rows = [
        "| junk chunks | workspace exact | OP | A | B |",
        "|---:|---:|---:|---:|---:|",
    ]
    for junk_count in JUNK_EVAL_COUNTS:
        workspace = oracle.get(f"junk_{junk_count}", {}).get("workspace", {})
        rows.append(
            f"| {junk_count} | {workspace.get('workspace_exact', 0.0):.4f} | "
            f"{workspace.get('op_exact', 0.0):.4f} | "
            f"{workspace.get('a_exact', 0.0):.4f} | "
            f"{workspace.get('b_exact', 0.0):.4f} |"
        )
    return "\n".join(rows)


def _retention_table(analysis: dict[str, Any]) -> str:
    executor = analysis.get("executor", {})
    before = executor.get("workspace_heldout_operands", {}).get("final_nem", 0.0)
    return (
        "| design | arithmetic before | arithmetic after bridge | drop |\n"
        "|---|---:|---:|---:|\n"
        f"| frozen executor | {before:.4f} | {before:.4f} | 0.0000 |\n"
        "| shared core | not run | not run | not run |"
    )


def _composition_status(analysis: dict[str, Any]) -> str:
    if not (
        _executor_gate(analysis)
        and _bridge_gate(analysis)
        and _binding_bridge_gate(analysis)
    ):
        return "skipped: workspace bridge/executor gates did not pass"
    return "skipped: minimal ADD_SUB is gated for the next run after ABI gates pass"


def _heldout_composition_status(analysis: dict[str, Any]) -> str:
    if "skipped" in _composition_status(analysis):
        return "skipped: ADD_SUB gate did not pass"
    return "skipped: SUB_ADD is only run after trained ADD_SUB >= .90"


def _decision(analysis: dict[str, Any]) -> str:
    if not _executor_gate(analysis):
        return (
            "OUTCOME C precursor: canonical ABI is defined, but the neural arithmetic "
            "executor did not reach the .98 heldout workspace upper-bound gate. Stop "
            "before bridge/composition; first make workspace-form arithmetic match "
            "standalone arithmetic or replace text serialization with a stronger slot "
            "interface."
        )
    if not _bridge_gate(analysis):
        return (
            "OUTCOME C: executor works, but retrieval->workspace generation fails. "
            "Next inspect structured state generation or slot-based latent workspace."
        )
    return (
        "OUTCOME A candidate: canonical workspace ABI passed the executor and bridge "
        "gates; continue toward frozen executor composition."
    )


def _write_manifest() -> None:
    train_executor = DATASET_DIR / "train" / "executor_equivalence.jsonl"
    train_bridge = DATASET_DIR / "train" / "bridge_relevant_to_workspace.jsonl"
    train_binding = DATASET_DIR / "train" / "binding_to_workspace.jsonl"
    train_oracle = DATASET_DIR / "train" / "oracle_chunk_to_workspace.jsonl"
    eval_paths = sorted((DATASET_DIR / "eval").glob("**/*.jsonl"))
    manifest = {
        "kind": "m183_workspace_abi_executor",
        "seed": SEED,
        "model_config": "arithmetic_3m",
        "position_encoding": "relative",
        "numeric_tokenization": "digit_safe",
        "segment_attention_mode": "workspace",
        "sequence_length": SEQUENCE_LENGTH,
        "workspace_abi_example": serialize_workspace_state(
            WorkspaceState(op="add", a=27, b=35)
        ),
        "robust_checkpoint": str(ROBUST_CHECKPOINT),
        "executor_train_count": len(_iter_jsonl(train_executor)),
        "bridge_train_count": len(_iter_jsonl(train_bridge)),
        "binding_bridge_train_count": len(_iter_jsonl(train_binding)),
        "oracle_bridge_train_count": len(_iter_jsonl(train_oracle)),
        "task_type_distribution": _task_distribution(DATASET_DIR),
        "prompt_intersections": {
            f"executor_train_vs_{path.relative_to(DATASET_DIR)}": len(
                _prompts(train_executor) & _prompts(path)
            )
            for path in eval_paths
        },
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _task_distribution(root: Path) -> dict[str, dict[str, int]]:
    return {
        str(path.relative_to(root)): dict(
            Counter(record["task_type"] for record in _iter_jsonl(path))
        )
        for path in sorted(root.glob("**/*.jsonl"))
    }


def _read_summary_payload(path: Path) -> dict[str, Any]:
    summary_path = path / "summary.json"
    if not summary_path.exists():
        return {"status": "missing", "final_nem": 0.0, "by_task_type": {}}
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


def _ensure_robust_checkpoint() -> None:
    if not ROBUST_CHECKPOINT.exists():
        raise FileNotFoundError(
            f"M-18.1 robust checkpoint is required: {ROBUST_CHECKPOINT}"
        )


def _device_name(analysis: dict[str, Any]) -> str:
    for section in ("executor", "bridge", "binding_bridge", "oracle_bridge"):
        payload = analysis.get(section, {})
        if not isinstance(payload, dict):
            continue
        for summary in payload.values():
            raw = summary.get("summary", {}) if isinstance(summary, dict) else {}
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
