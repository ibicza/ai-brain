from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import time
from collections import Counter
from collections.abc import Iterable
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
DATASET_DIR = ROOT / "datasets" / "m182_workspace_retrieval_validation"
RUNS_DIR = ROOT / "runs" / "m182_workspace_retrieval_validation"
DOC_PATH = ROOT / "docs" / "m182_workspace_retrieval_validation_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m182_workspace_retrieval_validation_report.md"
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

SEED = 18200
SEQUENCE_LENGTH = 256
MAX_NEW_TOKENS = 48
TRAIN_CASES_PER_OP = 1200
EVAL_CASES_PER_OP = 80
SMALL_TRAIN_PER_OP = 400
BINDING_TRAIN_PER_BUCKET = 80
BINDING_EVAL_PER_BUCKET = 20
JUNK_TRAIN_COUNTS = (0, 1, 2, 4, 8)
JUNK_EVAL_COUNTS = (0, 1, 2, 4, 8, 16, 32)
DISTRACTOR_COUNTS_TRAIN = (0, 1, 2, 4)
DISTRACTOR_COUNTS_EVAL = (0, 1, 2, 4, 8, 16)
RELEVANT_STEPS = 5000
RELEVANT_EXTRA_STEPS = 5000
RETRIEVAL_STEPS = 5000
ORACLE_STEPS = 8000
MIXED_STEPS = 8000
BINDING_STEPS = 8000
RETENTION_STEPS = 10000
STATE_STEPS = 5000

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-relevant")
    subparsers.add_parser("run-retrieval-only")
    subparsers.add_parser("run-oracle-chunks")
    subparsers.add_parser("run-mixed")
    subparsers.add_parser("run-variable-binding")
    subparsers.add_parser("run-retention")
    subparsers.add_parser("run-workspace-state")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-relevant":
        run_relevant()
    elif args.command == "run-retrieval-only":
        run_retrieval_only()
    elif args.command == "run-oracle-chunks":
        run_oracle_chunks()
    elif args.command == "run-mixed":
        run_mixed()
    elif args.command == "run-variable-binding":
        run_variable_binding()
    elif args.command == "run-retention":
        run_retention()
    elif args.command == "run-workspace-state":
        run_workspace_state()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_relevant()
        run_retrieval_only()
        analyze_all()
        if _relevant_gate(_read_json(RUNS_DIR / "analysis.json")):
            run_oracle_chunks()
            run_mixed()
            run_variable_binding()
            run_retention()
            analyze_all()
            if _oracle_gate(_read_json(RUNS_DIR / "analysis.json")):
                run_workspace_state()
                analyze_all()
        build_report(checks_passed=False)
    return 0


def prepare_datasets() -> None:
    if DATASET_DIR.exists():
        shutil.rmtree(DATASET_DIR)
    rng = random.Random(SEED)
    train_add, train_sub = generate_balanced_cases(
        TRAIN_CASES_PER_OP,
        rng=rng,
        low=10,
        high=89,
    )
    train_cases = interleave_balanced(train_add, train_sub)
    seen_eval_cases = interleave_balanced(
        train_add[:EVAL_CASES_PER_OP], train_sub[:EVAL_CASES_PER_OP]
    )
    unseen_add, unseen_sub = generate_balanced_cases(
        EVAL_CASES_PER_OP,
        rng=rng,
        low=10,
        high=89,
        exclude_keys={case.key for case in train_cases},
    )
    unseen_eval_cases = interleave_balanced(unseen_add, unseen_sub)
    heldout_add, heldout_sub = generate_balanced_cases(
        EVAL_CASES_PER_OP,
        rng=rng,
        low=90,
        high=109,
    )
    heldout_eval_cases = interleave_balanced(heldout_add, heldout_sub)

    _write_jsonl(
        DATASET_DIR / "train" / "relevant_context.jsonl",
        _relevant_context_records(train_cases, split="train", variant="train"),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "relevant_seen.jsonl",
        _relevant_context_records(seen_eval_cases, split="eval", variant="seen"),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "relevant_unseen.jsonl",
        _relevant_context_records(unseen_eval_cases, split="eval", variant="unseen"),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "relevant_heldout_operands.jsonl",
        _relevant_context_records(heldout_eval_cases, split="eval", variant="heldout"),
    )

    _write_jsonl(
        DATASET_DIR / "train" / "retrieval_only.jsonl",
        _retrieval_records(
            train_cases[: SMALL_TRAIN_PER_OP * 2], split="train", variant="train"
        ),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "retrieval_only_seen.jsonl",
        _retrieval_records(seen_eval_cases, split="eval", variant="seen"),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "retrieval_only_unseen.jsonl",
        _retrieval_records(unseen_eval_cases, split="eval", variant="unseen"),
    )

    oracle_train_records: list[dict[str, Any]] = []
    for junk_count in JUNK_TRAIN_COUNTS:
        oracle_train_records.extend(
            _oracle_chunk_records(
                train_cases[: SMALL_TRAIN_PER_OP * 2],
                split="train",
                junk_count=junk_count,
                heldout=False,
            )
        )
    _write_jsonl(DATASET_DIR / "train" / "oracle_chunks.jsonl", oracle_train_records)
    for junk_count in JUNK_EVAL_COUNTS:
        _write_jsonl(
            DATASET_DIR / "eval" / "oracle_chunks" / f"junk_{junk_count}.jsonl",
            _oracle_chunk_records(
                unseen_eval_cases,
                split="eval",
                junk_count=junk_count,
                heldout=True,
            ),
        )

    _write_jsonl(
        DATASET_DIR / "train" / "mixed_context.jsonl",
        _mixed_records(train_cases[: SMALL_TRAIN_PER_OP * 2], split="train"),
    )
    for name, records in _mixed_eval_sets(unseen_eval_cases).items():
        _write_jsonl(DATASET_DIR / "eval" / "mixed" / f"{name}.jsonl", records)

    _write_jsonl(
        DATASET_DIR / "train" / "variable_binding.jsonl",
        _variable_binding_records(train=True),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "variable_binding.jsonl",
        _variable_binding_records(train=False),
    )
    _write_jsonl(
        DATASET_DIR / "train" / "retention_replay.jsonl",
        _retention_replay_records(train_cases),
    )
    _write_jsonl(
        DATASET_DIR / "train" / "workspace_state.jsonl",
        _workspace_state_records(train_cases[: SMALL_TRAIN_PER_OP * 2], split="train"),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "workspace_state.jsonl",
        _workspace_state_records(unseen_eval_cases, split="eval"),
    )
    _write_manifest()


def generate_balanced_cases(
    count_per_op: int,
    *,
    rng: random.Random,
    low: int,
    high: int,
    exclude_keys: set[str] | None = None,
) -> tuple[list[Case], list[Case]]:
    excluded = exclude_keys or set()
    add_cases = _generate_op_cases(
        "add", count_per_op, rng=rng, low=low, high=high, excluded=excluded
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
    result: list[Case] = []
    for add_case, sub_case in zip(add_cases, sub_cases, strict=True):
        if add_case.op != "add" or sub_case.op != "sub":
            raise ValueError("interleave_balanced requires explicit ADD and SUB lists")
        result.extend([add_case, sub_case])
    return result


def assert_balanced_ops(
    records: Iterable[dict[str, Any]], *, dataset_name: str
) -> None:
    counts = Counter(str(record.get("metadata", {}).get("op")) for record in records)
    add_count = counts.get("add", 0)
    sub_count = counts.get("sub", 0)
    if add_count != sub_count:
        raise ValueError(
            f"{dataset_name} must be ADD/SUB balanced: add={add_count}, sub={sub_count}"
        )


def run_relevant() -> None:
    _ensure_robust_checkpoint()
    checkpoint = _run_train(
        name="from_robust",
        train_path=DATASET_DIR / "train" / "relevant_context.jsonl",
        eval_path=DATASET_DIR / "eval" / "relevant_seen.jsonl",
        steps=RELEVANT_STEPS,
        seed=SEED + 100,
        run_group="relevant",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    _eval_relevant_checkpoint(checkpoint=checkpoint, name="from_robust")

    extra_checkpoint = _run_train(
        name="from_robust_plus5k",
        train_path=DATASET_DIR / "train" / "relevant_context.jsonl",
        eval_path=DATASET_DIR / "eval" / "relevant_seen.jsonl",
        steps=RELEVANT_EXTRA_STEPS,
        seed=SEED + 101,
        run_group="relevant",
        init_checkpoint=checkpoint,
    )
    _eval_relevant_checkpoint(checkpoint=extra_checkpoint, name="from_robust_plus5k")


def _eval_relevant_checkpoint(*, checkpoint: Path, name: str) -> None:
    for eval_name in (
        "relevant_seen",
        "relevant_unseen",
        "relevant_heldout_operands",
    ):
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=RUNS_DIR / "relevant" / name / "benchmark" / eval_name,
            eval_path=DATASET_DIR / "eval" / f"{eval_name}.jsonl",
        )


def run_retrieval_only() -> None:
    _ensure_robust_checkpoint()
    checkpoint = _run_train(
        name="from_robust",
        train_path=DATASET_DIR / "train" / "retrieval_only.jsonl",
        eval_path=DATASET_DIR / "eval" / "retrieval_only_seen.jsonl",
        steps=RETRIEVAL_STEPS,
        seed=SEED + 200,
        run_group="retrieval_only",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    for eval_name in ("retrieval_only_seen", "retrieval_only_unseen"):
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=RUNS_DIR
            / "retrieval_only"
            / "from_robust"
            / "benchmark"
            / eval_name,
            eval_path=DATASET_DIR / "eval" / f"{eval_name}.jsonl",
        )


def run_oracle_chunks() -> None:
    _ensure_robust_checkpoint()
    checkpoint = _run_train(
        name="from_robust",
        train_path=DATASET_DIR / "train" / "oracle_chunks.jsonl",
        eval_path=DATASET_DIR / "eval" / "oracle_chunks" / "junk_0.jsonl",
        steps=ORACLE_STEPS,
        seed=SEED + 300,
        run_group="oracle_chunks",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    for junk_count in JUNK_EVAL_COUNTS:
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=RUNS_DIR
            / "oracle_chunks"
            / "from_robust"
            / "benchmark"
            / f"junk_{junk_count}",
            eval_path=DATASET_DIR
            / "eval"
            / "oracle_chunks"
            / f"junk_{junk_count}.jsonl",
        )


def run_mixed() -> None:
    _ensure_robust_checkpoint()
    checkpoint = _run_train(
        name="from_robust",
        train_path=DATASET_DIR / "train" / "mixed_context.jsonl",
        eval_path=DATASET_DIR / "eval" / "mixed" / "clean.jsonl",
        steps=MIXED_STEPS,
        seed=SEED + 400,
        run_group="mixed",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    for eval_name in ("clean", "irrelevant", "relevant", "mixed"):
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=RUNS_DIR / "mixed" / "from_robust" / "benchmark" / eval_name,
            eval_path=DATASET_DIR / "eval" / "mixed" / f"{eval_name}.jsonl",
        )


def run_variable_binding() -> None:
    _ensure_robust_checkpoint()
    checkpoint = _run_train(
        name="from_robust",
        train_path=DATASET_DIR / "train" / "variable_binding.jsonl",
        eval_path=DATASET_DIR / "eval" / "variable_binding.jsonl",
        steps=BINDING_STEPS,
        seed=SEED + 500,
        run_group="variable_binding",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    _eval_checkpoint(
        checkpoint=checkpoint,
        output_dir=RUNS_DIR
        / "variable_binding"
        / "from_robust"
        / "benchmark"
        / "variable_binding",
        eval_path=DATASET_DIR / "eval" / "variable_binding.jsonl",
    )


def run_retention() -> None:
    _ensure_robust_checkpoint()
    checkpoint = _run_train(
        name="replay_from_robust",
        train_path=DATASET_DIR / "train" / "retention_replay.jsonl",
        eval_path=DATASET_DIR / "eval" / "mixed" / "clean.jsonl",
        steps=RETENTION_STEPS,
        seed=SEED + 600,
        run_group="retention",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    evals = {
        "clean": DATASET_DIR / "eval" / "mixed" / "clean.jsonl",
        "irrelevant": DATASET_DIR / "eval" / "mixed" / "irrelevant.jsonl",
        "relevant": DATASET_DIR / "eval" / "mixed" / "relevant.jsonl",
        "retrieval_only": DATASET_DIR / "eval" / "retrieval_only_unseen.jsonl",
        "variable_binding": DATASET_DIR / "eval" / "variable_binding.jsonl",
    }
    for eval_name, eval_path in evals.items():
        _eval_checkpoint(
            checkpoint=checkpoint,
            output_dir=RUNS_DIR
            / "retention"
            / "replay_from_robust"
            / "benchmark"
            / eval_name,
            eval_path=eval_path,
        )


def run_workspace_state() -> None:
    _ensure_robust_checkpoint()
    checkpoint = _run_train(
        name="from_robust",
        train_path=DATASET_DIR / "train" / "workspace_state.jsonl",
        eval_path=DATASET_DIR / "eval" / "workspace_state.jsonl",
        steps=STATE_STEPS,
        seed=SEED + 700,
        run_group="workspace_state",
        init_checkpoint=ROBUST_CHECKPOINT,
    )
    _eval_checkpoint(
        checkpoint=checkpoint,
        output_dir=RUNS_DIR
        / "workspace_state"
        / "from_robust"
        / "benchmark"
        / "workspace_state",
        eval_path=DATASET_DIR / "eval" / "workspace_state.jsonl",
    )


def analyze_all() -> None:
    analysis = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "relevant": _collect_relevant(),
        "retrieval_only": _collect_retrieval_only(),
        "oracle_chunks": _collect_oracle_chunks(),
        "mixed": _collect_mixed(),
        "variable_binding": _collect_variable_binding(),
        "retention": _collect_retention(),
        "workspace_state": _collect_workspace_state(),
        "gates": {},
    }
    analysis["gates"]["relevant"] = _relevant_gate(analysis)
    analysis["gates"]["retrieval_only"] = _retrieval_gate(analysis)
    analysis["gates"]["oracle_chunks"] = _oracle_gate(analysis)
    analysis["gates"]["mixed"] = _mixed_gate(analysis)
    analysis["gates"]["variable_binding"] = _binding_gate(analysis)
    analysis["gates"]["workspace_state"] = _workspace_state_gate(analysis)
    analysis["decision"] = _decision(analysis)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    lines = [
        "# M-18.2 Workspace Retrieval Validation Report",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        f"- device: `{_device_name(analysis)}`",
        "",
        "## M-18.1 Bug Audit",
        "",
        "M-18.1 trained `workspace_relevant` on `train_cases[:600]`. Because the case list was grouped as all ADD before all SUB, that training file contained ADD only. M-18.2 removes positional slicing and asserts ADD/SUB balance in every arithmetic-context train split.",
        "",
        "The M-18.1 positive result is preserved as the starting point: the trained workspace model solved irrelevant distractor robustness. M-18.2 only revalidates relevant retrieval and binding.",
        "",
        "## Balanced Dataset Verification",
        "",
        _dataset_table(analysis),
        "",
        "## ADD/SUB Relevant Retrieval",
        "",
        _multi_eval_table(
            analysis.get("relevant", {}),
            ("relevant_seen", "relevant_unseen", "relevant_heldout_operands"),
        ),
        "",
        "## Retrieval-Only A/B/Pair",
        "",
        _retrieval_table(analysis),
        "",
        "## Oracle Chunk Selection",
        "",
        _oracle_table(analysis),
        "",
        "## Mixed Relevant+Irrelevant Context",
        "",
        _multi_eval_table(
            analysis.get("mixed", {}), ("clean", "irrelevant", "relevant", "mixed")
        ),
        "",
        "## Trained Variable Binding",
        "",
        _binding_table(analysis),
        "",
        "## Retention Matrix",
        "",
        _multi_eval_table(
            analysis.get("retention", {}),
            ("clean", "irrelevant", "relevant", "retrieval_only", "variable_binding"),
        ),
        "",
        "## Structured Workspace State",
        "",
        _workspace_state_table(analysis),
        "",
        "## Learned Selector",
        "",
        _learned_selector_status(analysis),
        "",
        "## Composition",
        "",
        _composition_status(analysis),
        "",
        "## Recommended Architecture",
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
    segment_mode: SegmentAttentionMode = "workspace",
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
        **_summarize(predictions),
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


def _relevant_context_records(
    cases: list[Case], *, split: str, variant: str, require_balanced: bool = True
) -> list[dict[str, Any]]:
    records = []
    for index, case in enumerate(cases):
        variant_code = sum(ord(char) for char in variant) % 100
        context_lines = [
            f"A = {case.a:02d}",
            f"J0 = {(case.a + case.b + 17 + index + variant_code) % 100:02d}",
            f"B = {case.b:02d}",
            f"J1 = {(case.a * 3 + case.b + 11 + index + variant_code) % 100:02d}",
            f"TAG = {variant_code:02d}",
        ]
        query = f"QUERY {case.op_token} A B"
        records.append(
            _context_record(
                record_id=f"m182.{split}.relevant.{variant}.{case.op}.{index:06d}",
                task_type=f"m182.relevant_context.{case.op}",
                context_lines=context_lines,
                access_flags=[True, False, True, False, False],
                query=query,
                answer=f"FINAL {case.result}",
                metadata={
                    "kind": "relevant_context",
                    "op": case.op,
                    "a": case.a,
                    "b": case.b,
                    "variant": variant,
                },
            )
        )
    if require_balanced:
        assert_balanced_ops(records, dataset_name=f"relevant_context.{split}.{variant}")
    return records


def _retrieval_records(
    cases: list[Case], *, split: str, variant: str
) -> list[dict[str, Any]]:
    records = []
    for index, case in enumerate(cases):
        context_lines = [
            f"A = {case.a:02d}",
            f"J0 = {(case.a + 31 + index) % 100:02d}",
            f"B = {case.b:02d}",
            f"J1 = {(case.b + 47 + index) % 100:02d}",
        ]
        for target, query, answer in (
            ("a", "QUERY VALUE A", f"FINAL {case.a}"),
            ("b", "QUERY VALUE B", f"FINAL {case.b}"),
            ("pair", "QUERY VALUES A B", f"FINAL A {case.a} B {case.b}"),
        ):
            records.append(
                _context_record(
                    record_id=f"m182.{split}.retrieval.{variant}.{target}.{index:06d}",
                    task_type=f"m182.retrieval.{target}",
                    context_lines=context_lines,
                    access_flags=[True, False, True, False],
                    query=query,
                    answer=answer,
                    metadata={
                        "kind": "retrieval_only",
                        "target": target,
                        "op": case.op,
                        "a": case.a,
                        "b": case.b,
                        "variant": variant,
                    },
                )
            )
    return records


def _oracle_chunk_records(
    cases: list[Case], *, split: str, junk_count: int, heldout: bool
) -> list[dict[str, Any]]:
    records = []
    for index, case in enumerate(cases):
        junk_prefix = "HX" if heldout else "K"
        chunks = [f"A = {case.a:02d}", f"B = {case.b:02d}"]
        for junk in range(junk_count):
            value = (
                case.a * (junk + 3) + case.b + index + (19 if heldout else 7)
            ) % 100
            chunks.insert(
                1 + ((junk * 2) % (len(chunks))), f"{junk_prefix}{junk} = {value:02d}"
            )
        access_flags = [chunk.startswith(("A =", "B =")) for chunk in chunks]
        query = f"QUERY {case.op_token} A B"
        records.append(
            _context_record(
                record_id=f"m182.{split}.oracle.j{junk_count}.{case.op}.{index:06d}",
                task_type=f"m182.oracle_chunks.junk{junk_count}.{case.op}",
                context_lines=chunks,
                access_flags=access_flags,
                query=query,
                answer=f"FINAL {case.result}",
                metadata={
                    "kind": "oracle_chunks",
                    "junk_count": junk_count,
                    "op": case.op,
                    "a": case.a,
                    "b": case.b,
                    "heldout": heldout,
                },
            )
        )
    assert_balanced_ops(records, dataset_name=f"oracle_chunks.{split}.junk{junk_count}")
    return records


def _mixed_records(cases: list[Case], *, split: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        records.append(
            _clean_record(case, split=split, index=index, task_class="clean")
        )
        records.append(
            _irrelevant_record(case, split=split, index=index, task_class="irrelevant")
        )
        records.extend(
            _relevant_context_records(
                [case],
                split=split,
                variant=f"mixed_relevant_{index:06d}",
                require_balanced=False,
            )
        )
        records.append(
            _mixed_relevant_irrelevant_record(case, split=split, index=index)
        )
    for task_class in (
        "clean",
        "irrelevant",
        "relevant_context",
        "mixed_relevant_irrelevant",
    ):
        subset = [
            record for record in records if record["metadata"]["kind"] == task_class
        ]
        assert_balanced_ops(subset, dataset_name=f"mixed.{split}.{task_class}")
    return records


def _mixed_eval_sets(cases: list[Case]) -> dict[str, list[dict[str, Any]]]:
    return {
        "clean": [
            _clean_record(case, split="eval", index=index, task_class="clean")
            for index, case in enumerate(cases)
        ],
        "irrelevant": [
            _irrelevant_record(case, split="eval", index=index, task_class="irrelevant")
            for index, case in enumerate(cases)
        ],
        "relevant": _relevant_context_records(
            cases, split="eval", variant="mixed_eval"
        ),
        "mixed": [
            _mixed_relevant_irrelevant_record(case, split="eval", index=index)
            for index, case in enumerate(cases)
        ],
    }


def _clean_record(
    case: Case, *, split: str, index: int, task_class: str
) -> dict[str, Any]:
    query = f"{case.op_token} {case.a:02d} {case.sign} {case.b:02d}"
    return _record_with_spans(
        record_id=f"m182.{split}.{task_class}.{case.op}.{index:06d}",
        task_type=f"m182.{task_class}.{case.op}",
        prompt=query,
        answer=f"FINAL {case.result}",
        spans=[("query", 0, len(query), False)],
        metadata={"kind": task_class, "op": case.op, "a": case.a, "b": case.b},
    )


def _irrelevant_record(
    case: Case, *, split: str, index: int, task_class: str
) -> dict[str, Any]:
    context = f"NOISE ADD {case.a:02d} + {(case.b + 7) % 90:02d} = {(case.a + case.b + 7) % 180}\nPAD {(case.a * 3 + index) % 100:02d}"
    query = f"{case.op_token} {case.a:02d} {case.sign} {case.b:02d}"
    prompt = f"{context}\n{query}"
    return _record_with_spans(
        record_id=f"m182.{split}.{task_class}.{case.op}.{index:06d}",
        task_type=f"m182.{task_class}.{case.op}",
        prompt=prompt,
        answer=f"FINAL {case.result}",
        spans=[
            ("context", 0, len(context), False),
            ("query", len(context) + 1, len(prompt), False),
        ],
        metadata={"kind": task_class, "op": case.op, "a": case.a, "b": case.b},
    )


def _mixed_relevant_irrelevant_record(
    case: Case, *, split: str, index: int
) -> dict[str, Any]:
    lines = [
        f"K0 = {(case.a + 23 + index) % 100:02d}",
        f"A = {case.a:02d}",
        f"OLD {case.op_token} {case.b:02d} {case.sign} {(case.a + 5) % 90:02d}",
        f"B = {case.b:02d}",
        f"K1 = {(case.a + case.b + 37 + index) % 100:02d}",
    ]
    query = f"QUERY {case.op_token} A B"
    return _context_record(
        record_id=f"m182.{split}.mixed_relevant_irrelevant.{case.op}.{index:06d}",
        task_type=f"m182.mixed_relevant_irrelevant.{case.op}",
        context_lines=lines,
        access_flags=[False, True, False, True, False],
        query=query,
        answer=f"FINAL {case.result}",
        metadata={
            "kind": "mixed_relevant_irrelevant",
            "op": case.op,
            "a": case.a,
            "b": case.b,
        },
    )


def _variable_binding_records(*, train: bool) -> list[dict[str, Any]]:
    rng = random.Random(SEED + (800 if train else 900))
    records = []
    depths = (1, 2, 3) if train else (1, 2, 3, 4)
    distractors_set = DISTRACTOR_COUNTS_TRAIN if train else DISTRACTOR_COUNTS_EVAL
    count = BINDING_TRAIN_PER_BUCKET if train else BINDING_EVAL_PER_BUCKET
    for depth in depths:
        for distractors in distractors_set:
            for index in range(count):
                value = 10 + rng.randrange(80)
                names = [chr(ord("A") + i) for i in range(depth + 1)]
                lines = [f"{names[0]} = {value:02d}"]
                lines.extend(
                    f"{names[i]} = {names[i - 1]}" for i in range(1, len(names))
                )
                for junk in range(distractors):
                    insert_at = 1 + ((junk * 2) % len(lines))
                    lines.insert(insert_at, f"J{junk} = {10 + rng.randrange(80):02d}")
                query = f"QUERY {names[-1]}"
                prompt = "\n".join([*lines, query])
                spans = []
                cursor = 0
                for line in lines:
                    access = not line.startswith("J")
                    spans.append(("context", cursor, cursor + len(line), access))
                    cursor += len(line) + 1
                spans.append(("query", len(prompt) - len(query), len(prompt), False))
                records.append(
                    _record_with_spans(
                        record_id=f"m182.binding.{'train' if train else 'eval'}.d{depth}.x{distractors}.{index:05d}",
                        task_type=f"m182.binding.depth{depth}.distractors{distractors}",
                        prompt=prompt,
                        answer=f"FINAL {value}",
                        spans=spans,
                        metadata={
                            "kind": "variable_binding",
                            "depth": depth,
                            "distractors": distractors,
                            "value": value,
                            "split": "train" if train else "eval",
                        },
                    )
                )
    return records


def _retention_replay_records(cases: list[Case]) -> list[dict[str, Any]]:
    base_cases = cases[: SMALL_TRAIN_PER_OP * 2]
    records = []
    records.extend(_mixed_records(base_cases, split="train"))
    records.extend(
        _retrieval_records(base_cases[:300], split="train", variant="retention")
    )
    records.extend(_variable_binding_records(train=True))
    return records


def _workspace_state_records(cases: list[Case], *, split: str) -> list[dict[str, Any]]:
    records = []
    for index, case in enumerate(cases):
        context_lines = [f"A = {case.a:02d}", f"B = {case.b:02d}"]
        query = f"QUERY {case.op_token} A B"
        answer = f"OP {case.op_token}\nA {case.a}\nB {case.b}\nFINAL {case.result}"
        records.append(
            _context_record(
                record_id=f"m182.{split}.workspace_state.{case.op}.{index:06d}",
                task_type=f"m182.workspace_state.{case.op}",
                context_lines=context_lines,
                access_flags=[True, True],
                query=query,
                answer=answer,
                metadata={
                    "kind": "workspace_state",
                    "op": case.op,
                    "a": case.a,
                    "b": case.b,
                },
            )
        )
    assert_balanced_ops(records, dataset_name=f"workspace_state.{split}")
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
    if len(context_lines) != len(access_flags):
        raise ValueError("context_lines and access_flags must have equal length")
    context = "\n".join(context_lines)
    prompt = f"{context}\n{query}" if context else query
    spans = []
    cursor = 0
    for line, access in zip(context_lines, access_flags, strict=True):
        spans.append(("context", cursor, cursor + len(line), access))
        cursor += len(line) + 1
    spans.append(("query", len(context) + (1 if context else 0), len(prompt), False))
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
            "segment_schema": "m182.v1",
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
    record: dict[str, Any], index: int, raw_generation: str, generated_ids: list[int]
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
            task_type=str(record["task_type"]), expected=expected, predicted=predicted
        ),
    }
    if record["task_type"].startswith("m182.workspace_state."):
        payload.update(_workspace_state_scores(expected=expected, predicted=predicted))
    return payload


def _workspace_state_scores(*, expected: str, predicted: str) -> dict[str, bool]:
    expected_lines = [line.strip() for line in expected.splitlines() if line.strip()]
    predicted_lines = [line.strip() for line in predicted.splitlines() if line.strip()]
    expected_map = _line_map(expected_lines)
    predicted_map = _line_map(predicted_lines)
    return {
        "op_exact": predicted_map.get("OP") == expected_map.get("OP"),
        "a_exact": predicted_map.get("A") == expected_map.get("A"),
        "b_exact": predicted_map.get("B") == expected_map.get("B"),
        "workspace_state_exact": all(
            predicted_map.get(key) == expected_map.get(key) for key in ("OP", "A", "B")
        ),
    }


def _line_map(lines: list[str]) -> dict[str, str]:
    result = {}
    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            result[parts[0]] = parts[1]
    return result


def _summarize(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_predictions(predictions)
    for payload in [summary["overall"], *summary["by_task_type"].values()]:
        matching = (
            predictions
            if payload is summary["overall"]
            else [
                prediction
                for prediction in predictions
                if prediction["task_type"] in summary["by_task_type"]
                and summary["by_task_type"][prediction["task_type"]] is payload
            ]
        )
        _add_generation_stats(payload, matching)
    if predictions and "workspace_state_exact" in predictions[0]:
        summary["workspace_state"] = _workspace_state_summary(predictions)
    return summary


def _add_generation_stats(
    payload: dict[str, Any], predictions: list[dict[str, Any]]
) -> None:
    count = len(predictions)
    if count == 0:
        payload["empty_prediction_rate"] = 0.0
        payload["avg_tokens_generated"] = 0.0
        return
    payload["empty_prediction_rate"] = (
        sum(not prediction["predicted"].strip() for prediction in predictions) / count
    )
    payload["avg_tokens_generated"] = (
        sum(float(prediction["tokens_generated"]) for prediction in predictions) / count
    )


def _workspace_state_summary(predictions: list[dict[str, Any]]) -> dict[str, float]:
    count = len(predictions) or 1
    return {
        "op_extraction": sum(
            bool(prediction.get("op_exact")) for prediction in predictions
        )
        / count,
        "a_extraction": sum(
            bool(prediction.get("a_exact")) for prediction in predictions
        )
        / count,
        "b_extraction": sum(
            bool(prediction.get("b_exact")) for prediction in predictions
        )
        / count,
        "workspace_state_exact": sum(
            bool(prediction.get("workspace_state_exact")) for prediction in predictions
        )
        / count,
        "final_arithmetic": sum(
            bool(prediction.get("final_normalized_exact_match"))
            for prediction in predictions
        )
        / count,
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
        "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
        "empty_prediction_rate": float(overall.get("empty_prediction_rate", 0.0)),
        "avg_tokens_generated": float(overall.get("avg_tokens_generated", 0.0)),
        "by_task_type": {
            key: float(value.get("final_normalized_exact_match", 0.0))
            for key, value in by_task.items()
        },
        "workspace_state": summary.get("workspace_state", {}),
        "summary": summary,
    }


def _collect_relevant() -> dict[str, Any]:
    result = {}
    for name in ("from_robust", "from_robust_plus5k", "from_scratch"):
        base = RUNS_DIR / "relevant" / name / "benchmark"
        if base.exists():
            payload = {
                eval_name: _read_summary_payload(base / eval_name)
                for eval_name in (
                    "relevant_seen",
                    "relevant_unseen",
                    "relevant_heldout_operands",
                )
            }
            if any(summary.get("status") == "complete" for summary in payload.values()):
                result[name] = payload
    return result or {"status": "missing"}


def _collect_retrieval_only() -> dict[str, Any]:
    base = RUNS_DIR / "retrieval_only" / "from_robust" / "benchmark"
    if not base.exists():
        return {"status": "missing"}
    return {
        "from_robust": {
            eval_name: _read_summary_payload(base / eval_name)
            for eval_name in ("retrieval_only_seen", "retrieval_only_unseen")
        }
    }


def _collect_oracle_chunks() -> dict[str, Any]:
    base = RUNS_DIR / "oracle_chunks" / "from_robust" / "benchmark"
    if not base.exists():
        return {"status": "skipped"}
    return {
        "from_robust": {
            f"junk_{junk_count}": _read_summary_payload(base / f"junk_{junk_count}")
            for junk_count in JUNK_EVAL_COUNTS
        }
    }


def _collect_mixed() -> dict[str, Any]:
    base = RUNS_DIR / "mixed" / "from_robust" / "benchmark"
    if not base.exists():
        return {"status": "skipped"}
    return {
        "from_robust": {
            eval_name: _read_summary_payload(base / eval_name)
            for eval_name in ("clean", "irrelevant", "relevant", "mixed")
        }
    }


def _collect_variable_binding() -> dict[str, Any]:
    base = RUNS_DIR / "variable_binding" / "from_robust" / "benchmark"
    if not base.exists():
        return {"status": "skipped"}
    return {
        "from_robust": {
            "variable_binding": _read_summary_payload(base / "variable_binding")
        }
    }


def _collect_retention() -> dict[str, Any]:
    base = RUNS_DIR / "retention" / "replay_from_robust" / "benchmark"
    if not base.exists():
        return {"status": "skipped"}
    return {
        "replay_from_robust": {
            eval_name: _read_summary_payload(base / eval_name)
            for eval_name in (
                "clean",
                "irrelevant",
                "relevant",
                "retrieval_only",
                "variable_binding",
            )
        }
    }


def _collect_workspace_state() -> dict[str, Any]:
    base = RUNS_DIR / "workspace_state" / "from_robust" / "benchmark"
    if not base.exists():
        return {"status": "skipped"}
    return {
        "from_robust": {
            "workspace_state": _read_summary_payload(base / "workspace_state")
        }
    }


def _relevant_gate(analysis: dict[str, Any]) -> bool:
    return any(
        _add_sub_gate(run.get("relevant_seen", {}), threshold=0.95)
        and _add_sub_gate(run.get("relevant_unseen", {}), threshold=0.95)
        for run in analysis.get("relevant", {}).values()
        if isinstance(run, dict)
    )


def _retrieval_gate(analysis: dict[str, Any]) -> bool:
    retrieval = (
        analysis.get("retrieval_only", {})
        .get("from_robust", {})
        .get("retrieval_only_unseen", {})
    )
    by_task = retrieval.get("by_task_type", {})
    return all(
        by_task.get(task, 0.0) >= 0.98
        for task in ("m182.retrieval.a", "m182.retrieval.b", "m182.retrieval.pair")
    )


def _oracle_gate(analysis: dict[str, Any]) -> bool:
    oracle = analysis.get("oracle_chunks", {}).get("from_robust", {})
    if not oracle:
        return False
    for junk_count in (0, 1, 2, 4, 8, 16):
        if not _add_sub_gate(oracle.get(f"junk_{junk_count}", {}), threshold=0.95):
            return False
    return True


def _mixed_gate(analysis: dict[str, Any]) -> bool:
    mixed = analysis.get("mixed", {}).get("from_robust", {})
    if not mixed:
        return False
    return (
        mixed.get("clean", {}).get("final_nem", 0.0) >= 0.98
        and mixed.get("irrelevant", {}).get("final_nem", 0.0) >= 0.95
        and _add_sub_gate(mixed.get("relevant", {}), threshold=0.95)
        and mixed.get("mixed", {}).get("final_nem", 0.0) >= 0.90
    )


def _binding_gate(analysis: dict[str, Any]) -> bool:
    payload = (
        analysis.get("variable_binding", {})
        .get("from_robust", {})
        .get("variable_binding", {})
    )
    by_task = payload.get("by_task_type", {})
    depth_scores: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: []}
    for task_type, score in by_task.items():
        depth = _binding_depth(task_type)
        if depth in depth_scores:
            depth_scores[depth].append(score)
    return (
        min(depth_scores[1] or [0.0]) >= 0.98
        and min(depth_scores[2] or [0.0]) >= 0.95
        and min(depth_scores[3] or [0.0]) >= 0.90
        and max(depth_scores[4] or [0.0]) >= 0.70
    )


def _workspace_state_gate(analysis: dict[str, Any]) -> bool:
    payload = (
        analysis.get("workspace_state", {})
        .get("from_robust", {})
        .get("workspace_state", {})
    )
    state = payload.get("workspace_state", {})
    return (
        state.get("op_extraction", 0.0) >= 0.95
        and state.get("a_extraction", 0.0) >= 0.95
        and state.get("b_extraction", 0.0) >= 0.95
        and state.get("workspace_state_exact", 0.0) >= 0.95
        and state.get("final_arithmetic", 0.0) >= 0.95
    )


def _add_sub_gate(summary: dict[str, Any], *, threshold: float) -> bool:
    by_task = summary.get("by_task_type", {})
    return (
        _task_family_score(by_task, ".add") >= threshold
        and _task_family_score(by_task, ".sub") >= threshold
        and summary.get("final_nem", 0.0) >= threshold
    )


def _task_family_score(by_task: dict[str, float], needle: str) -> float:
    values = [score for task, score in by_task.items() if needle in task]
    return min(values) if values else 0.0


def _dataset_table(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    if manifest.get("status") == "missing":
        return "missing"
    rows = ["| item | value |", "|---|---:|"]
    for key in (
        "train_relevant_context_count",
        "train_relevant_add_count",
        "train_relevant_sub_count",
        "train_mixed_context_count",
        "train_variable_binding_count",
        "prompt_intersections",
    ):
        rows.append(f"| {key} | {manifest.get(key)} |")
    return "\n".join(rows)


def _multi_eval_table(payload: dict[str, Any], eval_names: tuple[str, ...]) -> str:
    if payload.get("status") in {"missing", "skipped"}:
        return payload.get("status", "missing")
    rows = [
        "| run | eval | overall | ADD | SUB | full NEM | false | empty | avg tok |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run_name, evals in payload.items():
        for eval_name in eval_names:
            summary = evals.get(eval_name, {})
            by_task = summary.get("by_task_type", {})
            rows.append(
                f"| {run_name} | {eval_name} | {summary.get('final_nem', 0.0):.4f} | "
                f"{_task_family_score(by_task, '.add'):.4f} | {_task_family_score(by_task, '.sub'):.4f} | "
                f"{summary.get('full_nem', 0.0):.4f} | {summary.get('false_answer_rate', 0.0):.4f} | "
                f"{summary.get('empty_prediction_rate', 0.0):.4f} | {summary.get('avg_tokens_generated', 0.0):.2f} |"
            )
    return "\n".join(rows)


def _retrieval_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("retrieval_only", {})
    if payload.get("status") in {"missing", "skipped"}:
        return payload.get("status", "missing")
    rows = [
        "| run | eval | overall | A | B | pair | full NEM | false | empty | avg tok |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run_name, evals in payload.items():
        for eval_name in ("retrieval_only_seen", "retrieval_only_unseen"):
            summary = evals.get(eval_name, {})
            by_task = summary.get("by_task_type", {})
            rows.append(
                f"| {run_name} | {eval_name} | "
                f"{summary.get('final_nem', 0.0):.4f} | "
                f"{by_task.get('m182.retrieval.a', 0.0):.4f} | "
                f"{by_task.get('m182.retrieval.b', 0.0):.4f} | "
                f"{by_task.get('m182.retrieval.pair', 0.0):.4f} | "
                f"{summary.get('full_nem', 0.0):.4f} | "
                f"{summary.get('false_answer_rate', 0.0):.4f} | "
                f"{summary.get('empty_prediction_rate', 0.0):.4f} | "
                f"{summary.get('avg_tokens_generated', 0.0):.2f} |"
            )
    return "\n".join(rows)


def _oracle_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("oracle_chunks", {})
    if payload.get("status") in {"missing", "skipped"}:
        return payload.get("status", "skipped")
    rows = ["| run | junk chunks | overall | ADD | SUB |", "|---|---:|---:|---:|---:|"]
    for run_name, evals in payload.items():
        for junk_count in JUNK_EVAL_COUNTS:
            summary = evals.get(f"junk_{junk_count}", {})
            by_task = summary.get("by_task_type", {})
            rows.append(
                f"| {run_name} | {junk_count} | {summary.get('final_nem', 0.0):.4f} | "
                f"{_task_family_score(by_task, '.add'):.4f} | {_task_family_score(by_task, '.sub'):.4f} |"
            )
    return "\n".join(rows)


def _binding_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("variable_binding", {})
    if payload.get("status") in {"missing", "skipped"}:
        return payload.get("status", "skipped")
    summary = payload.get("from_robust", {}).get("variable_binding", {})
    rows = ["| depth | distractors | final NEM |", "|---:|---:|---:|"]
    for task_type, score in sorted(summary.get("by_task_type", {}).items()):
        rows.append(
            f"| {_binding_depth(task_type)} | {_binding_distractors(task_type)} | {score:.4f} |"
        )
    return "\n".join(rows)


def _workspace_state_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("workspace_state", {})
    if payload.get("status") in {"missing", "skipped"}:
        return "skipped: oracle chunks and direct relevant retrieval gates did not pass"
    summary = payload.get("from_robust", {}).get("workspace_state", {})
    state = summary.get("workspace_state", {})
    rows = ["| metric | score |", "|---|---:|"]
    for key in (
        "op_extraction",
        "a_extraction",
        "b_extraction",
        "workspace_state_exact",
        "final_arithmetic",
    ):
        rows.append(f"| {key} | {state.get(key, 0.0):.4f} |")
    return "\n".join(rows)


def _learned_selector_status(analysis: dict[str, Any]) -> str:
    if not _oracle_gate(analysis) or not _workspace_state_gate(analysis):
        return "skipped: learned selector is gated on oracle chunks and workspace state >= .95"
    return "not implemented in M-18.2 run: gate passed, next milestone should add the chunk-level learned selector"


def _composition_status(analysis: dict[str, Any]) -> str:
    if not (
        _mixed_gate(analysis)
        and _retrieval_gate(analysis)
        and _binding_gate(analysis)
        and _workspace_state_gate(analysis)
    ):
        return "skipped: composition gate did not pass"
    return "not implemented in M-18.2 run: all gates passed, next milestone may run minimal ADD_SUB through workspace state"


def _decision(analysis: dict[str, Any]) -> str:
    if not _relevant_gate(analysis):
        if _retrieval_gate(analysis):
            return (
                "OUTCOME D/E: the M-18.1 ADD/SUB asymmetry was a dataset bug, and "
                "retrieval-only A/B/pair is solved, but direct relevant arithmetic "
                "does not pass the strict per-op .95 gate. The bottleneck is the "
                "interface between retrieved context values and arithmetic execution, "
                "not raw value retrieval. Do not add a new architecture yet; next "
                "debug the workspace arithmetic interface and chunk access semantics."
            )
        return (
            "OUTCOME E: after fixing the ADD/SUB balance, direct relevant-context "
            "retrieval did not pass the .95 gate. Investigate segment-mask access "
            "semantics, data format, and training objective before adding a new architecture."
        )
    if not _oracle_gate(analysis):
        return (
            "OUTCOME C: balanced direct relevant context can be learned, but trained "
            "oracle chunk selection is still below gate. Keep relative_shaw + segmented "
            "workspace for irrelevant-context isolation, and debug the workspace/chunk interface."
        )
    if not _binding_gate(analysis):
        return (
            "OUTCOME B partial: oracle retrieval works, but trained variable binding "
            "does not meet depth targets. Continue with explicit binding curriculum/replay."
        )
    return (
        "OUTCOME B: relative_shaw + segmented workspace remains the current "
        "context/memory architecture. Proceed to learned chunk selector only after "
        "workspace-state metrics are also above gate."
    )


def _write_manifest() -> None:
    train_relevant = _iter_jsonl(DATASET_DIR / "train" / "relevant_context.jsonl")
    train_mixed = _iter_jsonl(DATASET_DIR / "train" / "mixed_context.jsonl")
    train_binding = _iter_jsonl(DATASET_DIR / "train" / "variable_binding.jsonl")
    eval_paths = {
        "relevant_seen": DATASET_DIR / "eval" / "relevant_seen.jsonl",
        "relevant_unseen": DATASET_DIR / "eval" / "relevant_unseen.jsonl",
        "relevant_heldout_operands": DATASET_DIR
        / "eval"
        / "relevant_heldout_operands.jsonl",
        "variable_binding": DATASET_DIR / "eval" / "variable_binding.jsonl",
    }
    for name, records in {
        "train_relevant": train_relevant,
        "train_mixed": train_mixed,
    }.items():
        arithmetic_records = [
            record
            for record in records
            if record.get("metadata", {}).get("op") in {"add", "sub"}
        ]
        assert_balanced_ops(arithmetic_records, dataset_name=name)
    manifest = {
        "kind": "m182_workspace_retrieval_validation",
        "seed": SEED,
        "model_config": "arithmetic_3m",
        "position_encoding": "relative",
        "numeric_tokenization": "digit_safe",
        "segment_attention_mode": "workspace",
        "sequence_length": SEQUENCE_LENGTH,
        "robust_checkpoint": str(ROBUST_CHECKPOINT),
        "train_relevant_context_count": len(train_relevant),
        "train_relevant_add_count": sum(
            record["metadata"].get("op") == "add" for record in train_relevant
        ),
        "train_relevant_sub_count": sum(
            record["metadata"].get("op") == "sub" for record in train_relevant
        ),
        "train_mixed_context_count": len(train_mixed),
        "train_variable_binding_count": len(train_binding),
        "train_variable_binding_in_retention": True,
        "task_type_distribution": _task_distribution(DATASET_DIR),
        "prompt_intersections": {
            f"train_relevant_vs_{name}": len(
                _prompts(DATASET_DIR / "train" / "relevant_context.jsonl")
                & _prompts(path)
            )
            for name, path in eval_paths.items()
        },
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _task_distribution(root: Path) -> dict[str, dict[str, int]]:
    result = {}
    for path in sorted(root.glob("**/*.jsonl")):
        result[str(path.relative_to(root))] = dict(
            Counter(record["task_type"] for record in _iter_jsonl(path))
        )
    return result


def _binding_depth(task_type: str) -> int:
    for part in task_type.split("."):
        if part.startswith("depth"):
            return int(part.removeprefix("depth"))
    return -1


def _binding_distractors(task_type: str) -> int:
    for part in task_type.split("."):
        if part.startswith("distractors"):
            return int(part.removeprefix("distractors"))
    return -1


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
    for section in (
        "relevant",
        "retrieval_only",
        "oracle_chunks",
        "mixed",
        "variable_binding",
        "retention",
        "workspace_state",
    ):
        payload = analysis.get(section, {})
        if not isinstance(payload, dict):
            continue
        for run_payload in payload.values():
            if not isinstance(run_payload, dict):
                continue
            for summary in run_payload.values():
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
