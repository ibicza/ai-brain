from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Literal

import torch

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.generation import (
    build_inference_input_ids,
    generate_answer_ids,
    load_model_for_inference,
)
from ai_brain.eval.metrics import summarize_predictions, task_group
from ai_brain.eval.normalize import (
    extract_generated_answer,
    is_false_answer,
    normalize_answer,
)
from ai_brain.eval.runner import eval_lm
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import END_TOKEN, EOS_TOKEN
from ai_brain.language.tokenizer.text_format import format_inference_prompt
from ai_brain.runtime.device import get_device_info
from ai_brain.training.config import TrainConfig
from ai_brain.training.lm_dataset import (
    RELEVANCE_IGNORE_INDEX,
    default_lm_cache_path,
    load_tokenized_lm_dataset,
    prepare_lm_dataset,
)
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m175_distractor_routing"
RUNS_DIR = ROOT / "runs" / "m175_distractor_routing_v2"
DOC_PATH = ROOT / "docs" / "m175_distractor_routing_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m175_distractor_routing_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"
M174_RELATIVE_CHECKPOINT = (
    ROOT
    / "runs"
    / "m174_position_architecture"
    / "relative_shaw"
    / "checkpoints"
    / "step_020000.pt"
)

SEED = 317500
TRAIN_PER_OP = 3500
EVAL_PER_OP = 60
SEQUENCE_LENGTH = 256
MAX_NEW_TOKENS = 32
LENGTHS = (1, 2, 4, 8, 16, 32)
HARD_LENGTHS = (1, 2, 4, 8, 16)
CURRICULUM_STEPS = 4000
VARIANT_STEPS = 8000
DIFF_FIT_STEPS = 10000
RELEVANCE_LAMBDAS = (0.05, 0.1, 0.25)

EASY_FAMILIES = ("neutral", "random_vocab")
SEMANTIC_FAMILIES = ("natural_phrase",)
ARITHMETIC_FAMILIES = (
    "previous_arithmetic",
    "previous_same_op",
    "previous_opposite_op",
)
HARD_FAMILIES = ("hard_negative",)
FAMILIES = (*EASY_FAMILIES, *SEMANTIC_FAMILIES, *ARITHMETIC_FAMILIES, *HARD_FAMILIES)

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
    init_checkpoint_path: Path | None = None
    steps: int = VARIANT_STEPS
    relevance_mode: str = "none"
    relevance_loss_weight: float = 0.0
    attention_variant: str = "standard"
    seed: int = SEED


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-oracle")
    subparsers.add_parser("run-routing")
    subparsers.add_parser("run-all")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-oracle":
        run_oracle_and_attention()
    elif args.command == "run-routing":
        run_routing_ladder()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_oracle_and_attention()
        analyze_all()
        if _oracle_restores(_read_json(RUNS_DIR / "analysis.json")):
            run_routing_ladder()
        analyze_all()
        build_report(checks_passed=False)
    return 0


def prepare_datasets() -> None:
    rng = random.Random(SEED)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    splits = {op: _split_cases(op, rng) for op in ("add", "sub")}
    eval_cases = [case for op in ("add", "sub") for case in splits[op]["eval"]]

    _write_jsonl(
        DATASET_DIR / "eval" / "clean.jsonl",
        _records_for_cases(eval_cases, family="clean", length=0, split="eval"),
    )
    for family in FAMILIES:
        for length in _family_lengths(family):
            _write_jsonl(
                DATASET_DIR / "eval" / family / f"len_{length}.jsonl",
                _records_for_cases(
                    eval_cases,
                    family=family,
                    length=length,
                    split="eval",
                    heldout=True,
                ),
            )

    _write_train_sets(splits, rng)
    _write_variable_binding_probe(eval_cases)
    _write_manifest(splits)


def run_oracle_and_attention() -> None:
    _require_relative_checkpoint()
    families = ("neutral", "random_vocab", "natural_phrase", "previous_arithmetic")
    for family in families:
        for length in _family_lengths(family):
            eval_path = DATASET_DIR / "eval" / family / f"len_{length}.jsonl"
            _eval_checkpoint(
                checkpoint=M174_RELATIVE_CHECKPOINT,
                eval_path=eval_path,
                output_dir=RUNS_DIR / "baseline" / family / f"len_{length}",
            )
            _eval_oracle_mask(
                checkpoint=M174_RELATIVE_CHECKPOINT,
                eval_path=eval_path,
                output_dir=RUNS_DIR / "oracle_mask" / family / f"len_{length}",
            )
    _attention_diagnostics(
        checkpoint=M174_RELATIVE_CHECKPOINT,
        output_dir=RUNS_DIR / "attention_diagnostics",
    )


def run_routing_ladder() -> None:
    analysis_path = RUNS_DIR / "analysis.json"
    if not analysis_path.exists():
        analyze_all()
    if not _oracle_restores(_read_json(analysis_path)):
        print("skip routing ladder: oracle mask did not restore performance")
        return
    stage_checkpoint = _run_strong_curriculum()
    for weight in RELEVANCE_LAMBDAS:
        checkpoint = _run_spec(
            RunSpec(
                name=f"relevance_aux_l{str(weight).replace('.', '_')}",
                train_path=DATASET_DIR / "train" / "stage4_balanced.jsonl",
                eval_path=DATASET_DIR / "eval" / "clean.jsonl",
                init_checkpoint_path=M174_RELATIVE_CHECKPOINT,
                steps=VARIANT_STEPS,
                relevance_mode="aux",
                relevance_loss_weight=weight,
                seed=SEED + int(weight * 1000),
            )
        )
        run_name = f"relevance_aux_l{str(weight).replace('.', '_')}"
        _eval_all_benchmarks(
            checkpoint=checkpoint,
            output_dir=RUNS_DIR / run_name / "benchmark",
        )
        _eval_relevance_metrics(
            checkpoint=checkpoint,
            eval_path=DATASET_DIR / "eval" / "hard_negative" / "len_4.jsonl",
            output_dir=RUNS_DIR / run_name / "benchmark",
        )
    best_aux = _best_aux_checkpoint()
    gate_checkpoint = _run_spec(
        RunSpec(
            name="relevance_gate_l0_1",
            train_path=DATASET_DIR / "train" / "stage4_balanced.jsonl",
            eval_path=DATASET_DIR / "eval" / "clean.jsonl",
            init_checkpoint_path=best_aux
            or stage_checkpoint
            or M174_RELATIVE_CHECKPOINT,
            steps=VARIANT_STEPS,
            relevance_mode="gate",
            relevance_loss_weight=0.1,
            seed=SEED + 201,
        )
    )
    _eval_all_benchmarks(
        checkpoint=gate_checkpoint,
        output_dir=RUNS_DIR / "relevance_gate_l0_1" / "benchmark",
    )
    _eval_relevance_metrics(
        checkpoint=gate_checkpoint,
        eval_path=DATASET_DIR / "eval" / "hard_negative" / "len_4.jsonl",
        output_dir=RUNS_DIR / "relevance_gate_l0_1" / "benchmark",
    )
    diff_checkpoint = _run_spec(
        RunSpec(
            name="differential_relative_fit",
            train_path=DATASET_DIR / "train" / "stage0_clean.jsonl",
            eval_path=DATASET_DIR / "eval" / "clean.jsonl",
            init_checkpoint_path=M174_RELATIVE_CHECKPOINT,
            steps=DIFF_FIT_STEPS,
            attention_variant="differential",
            seed=SEED + 301,
        )
    )
    _eval_all_benchmarks(
        checkpoint=diff_checkpoint,
        output_dir=RUNS_DIR / "differential_relative_fit" / "benchmark",
    )


def analyze_all() -> None:
    analysis: dict[str, Any] = {
        "manifest": _read_json(DATASET_DIR / "manifest.json"),
        "oracle": _collect_oracle_results(),
        "attention_diagnostics": _read_json_if_exists(
            RUNS_DIR / "attention_diagnostics" / "summary.json"
        ),
        "curriculum": _collect_curriculum_results(),
        "routing_variants": _collect_routing_variants(),
        "variable_binding": _collect_variable_binding_results(),
    }
    analysis["gate"] = _composition_gate(analysis)
    analysis["composition"] = {
        "status": "skipped",
        "reason": analysis["gate"]["reason"],
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    lines = [
        "# M-17.5 Distractor Routing Report",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        f"- device: `{_device_name(analysis)}`",
        "",
        "## Oracle Mask Result",
        "",
        _oracle_table(analysis),
        "",
        "## Attention Mass Analysis",
        "",
        _attention_table(analysis),
        "",
        "## Distractor Curriculum Learning Curves",
        "",
        _curriculum_table(analysis),
        "",
        "## Relevance Classifier Metrics",
        "",
        _relevance_table(analysis),
        "",
        "## Baseline vs Auxiliary vs Learned Gate vs Oracle",
        "",
        _ladder_table(analysis),
        "",
        "## Differential Attention Comparison",
        "",
        _differential_table(analysis),
        "",
        "## Hard-Negative Robustness",
        "",
        _hard_negative_table(analysis),
        "",
        "## Variable-Binding Routing Probe",
        "",
        _variable_binding_table(analysis),
        "",
        "## Composition Retest",
        "",
        f"{analysis['composition']['status']}: {analysis['composition']['reason']}",
        "",
        "## Recommended Attention/Routing Architecture",
        "",
        _decision(analysis),
    ]
    text = "\n".join(lines)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def _run_strong_curriculum() -> Path | None:
    previous = M174_RELATIVE_CHECKPOINT
    for stage in range(1, 5):
        name = f"strong_curriculum_stage{stage}"
        output_dir = RUNS_DIR / name
        checkpoint = _checkpoint_path(output_dir, CURRICULUM_STEPS)
        if not checkpoint.exists():
            _run_spec(
                RunSpec(
                    name=name,
                    train_path=DATASET_DIR / "train" / f"stage{stage}_balanced.jsonl",
                    eval_path=DATASET_DIR / "eval" / "clean.jsonl",
                    init_checkpoint_path=previous,
                    steps=CURRICULUM_STEPS,
                    seed=SEED + 10 + stage,
                )
            )
        previous = checkpoint
        _eval_all_benchmarks(
            checkpoint=previous,
            output_dir=RUNS_DIR / name / "benchmark",
        )
    return previous if previous != M174_RELATIVE_CHECKPOINT else None


def _run_spec(spec: RunSpec) -> Path:
    output_dir = RUNS_DIR / spec.name
    checkpoint = _checkpoint_path(output_dir, spec.steps)
    if checkpoint.exists():
        print(f"skip existing run: {spec.name}")
        return checkpoint
    output_dir.mkdir(parents=True, exist_ok=True)
    config = TrainConfig(
        train_path=spec.train_path,
        eval_path=spec.eval_path,
        tokenizer_path=TOKENIZER_PATH,
        output_dir=output_dir,
        model_config_name="arithmetic_3m",
        steps=spec.steps,
        batch_size=8,
        sequence_length=SEQUENCE_LENGTH,
        loss_mode="answer-only",
        learning_rate=3e-4,
        grad_clip_norm=1.0,
        numeric_tokenization="digit_safe",
        position_encoding="relative",
        attention_variant=spec.attention_variant,
        relevance_mode=spec.relevance_mode,
        relevance_loss_weight=spec.relevance_loss_weight,
        init_checkpoint_path=spec.init_checkpoint_path,
        seed=spec.seed,
        eval_every=max(1000, spec.steps // 4),
        eval_batches=20,
        save_every=spec.steps,
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
    return checkpoint


def _eval_all_benchmarks(*, checkpoint: Path, output_dir: Path) -> None:
    _eval_checkpoint(
        checkpoint=checkpoint,
        eval_path=DATASET_DIR / "eval" / "clean.jsonl",
        output_dir=output_dir / "clean",
    )
    for family in FAMILIES:
        for length in _family_lengths(family):
            _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=DATASET_DIR / "eval" / family / f"len_{length}.jsonl",
                output_dir=output_dir / family / f"len_{length}",
            )
    _eval_checkpoint(
        checkpoint=checkpoint,
        eval_path=DATASET_DIR / "probe" / "variable_binding.jsonl",
        output_dir=output_dir / "variable_binding",
    )


def _eval_checkpoint(
    *, checkpoint: Path, eval_path: Path, output_dir: Path
) -> dict[str, Any]:
    summary_path = output_dir / "summary.json"
    if summary_path.exists():
        return _summary_payload(_read_json(summary_path))
    summary = eval_lm(
        checkpoint_path=checkpoint,
        eval_path=eval_path,
        tokenizer_path=TOKENIZER_PATH,
        output_dir=output_dir,
        max_new_tokens=MAX_NEW_TOKENS,
        numeric_tokenization="digit_safe",
    )["summary"]
    return _summary_payload(summary)


def _eval_oracle_mask(
    *, checkpoint: Path, eval_path: Path, output_dir: Path
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
            generated_ids = _generate_with_mask(
                model=model,
                tokenizer=tokenizer,
                record=record,
                device=device_info.device,
                oracle_mask=True,
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
        "oracle_mask": True,
        "predictions_path": str(predictions_path),
        "device": str(device_info.device),
        "device_name": device_info.name,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return _summary_payload(summary)


def _attention_diagnostics(*, checkpoint: Path, output_dir: Path) -> None:
    summary_path = output_dir / "summary.json"
    if summary_path.exists():
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    device_info = get_device_info()
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _loaded = load_model_for_inference(
        checkpoint_path=checkpoint,
        tokenizer_path=TOKENIZER_PATH,
        device=device_info.device,
    )
    buckets: dict[str, list[dict[str, float]]] = defaultdict(list)
    for family in ("neutral", "natural_phrase", "previous_arithmetic", "hard_negative"):
        for length in (1, 2, 4, 8):
            path = DATASET_DIR / "eval" / family / f"len_{length}.jsonl"
            if not path.exists():
                continue
            for index, record in enumerate(_iter_jsonl(path)):
                if index >= 40:
                    break
                generated_ids, masses = _generate_with_attention_masses(
                    model=model,
                    tokenizer=tokenizer,
                    record=record,
                    device=device_info.device,
                )
                raw_generation = tokenizer.decode(
                    generated_ids, skip_special_tokens=False
                )
                prediction = _prediction_payload(
                    record, index, raw_generation, generated_ids
                )
                key = f"{family}.correct_{prediction['final_normalized_exact_match']}"
                buckets[key].extend(masses)
    summary = {}
    for key, values in buckets.items():
        summary[key] = {
            "count": len(values),
            "relevant_attention_mass": mean(v["relevant"] for v in values),
            "distractor_attention_mass": mean(v["distractor"] for v in values),
            "generated_attention_mass": mean(v["generated"] for v in values),
            "relevant_distractor_ratio": mean(
                v["relevant"] / max(v["distractor"], 1e-8) for v in values
            ),
        }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


@torch.no_grad()
def _eval_relevance_metrics(
    *,
    checkpoint: Path,
    eval_path: Path,
    output_dir: Path,
) -> None:
    metrics_path = output_dir / "relevance_metrics.json"
    if metrics_path.exists():
        return
    device_info = get_device_info()
    model, _loaded = load_model_for_inference(
        checkpoint_path=checkpoint,
        tokenizer_path=TOKENIZER_PATH,
        device=device_info.device,
    )
    if getattr(model, "relevance_head", None) is None:
        metrics_path.write_text(
            json.dumps({"status": "missing"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return
    cache_path = default_lm_cache_path(
        cache_dir=RUNS_DIR / "tokenized_eval",
        input_path=eval_path,
        tokenizer_path=TOKENIZER_PATH,
        sequence_length=SEQUENCE_LENGTH,
        loss_mode="answer-only",
        numeric_tokenization="digit_safe",
    )
    prepare_lm_dataset(
        input_path=eval_path,
        tokenizer_path=TOKENIZER_PATH,
        output_path=cache_path,
        sequence_length=SEQUENCE_LENGTH,
        loss_mode="answer-only",
        numeric_tokenization="digit_safe",
    )
    dataset = load_tokenized_lm_dataset(cache_path)
    tp = fp = fn = 0
    for index in range(len(dataset)):
        batch = {
            key: value.unsqueeze(0).to(device_info.device)
            for key, value in dataset[index].items()
        }
        output = model(batch["input_ids"], return_relevance=True)
        logits = output["relevance_logits"]
        labels = batch["relevance_labels"]
        mask = labels != RELEVANCE_IGNORE_INDEX
        predicted = torch.sigmoid(logits[mask]) >= 0.5
        expected = labels[mask].bool()
        tp += int((predicted & expected).sum().item())
        fp += int((predicted & ~expected).sum().item())
        fn += int((~predicted & expected).sum().item())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)
    metrics = {
        "status": "complete",
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "eval_path": str(eval_path),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


@torch.no_grad()
def _generate_with_mask(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    record: dict[str, Any],
    device: torch.device,
    oracle_mask: bool,
) -> list[int]:
    attention_key_mask = None
    if oracle_mask:
        attention_key_mask = _attention_key_mask(record, tokenizer, device)
    return generate_answer_ids(
        model=model,
        tokenizer=tokenizer,
        prompt=str(record["prompt"]),
        max_new_tokens=MAX_NEW_TOKENS,
        device=device,
        numeric_tokenization="digit_safe",
        attention_key_mask=attention_key_mask,
    )


@torch.no_grad()
def _generate_with_attention_masses(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    record: dict[str, Any],
    device: torch.device,
) -> tuple[list[int], list[dict[str, float]]]:
    eos_id = _required_token_id(tokenizer, EOS_TOKEN)
    end_id = _required_token_id(tokenizer, END_TOKEN)
    generated = build_inference_input_ids(
        prompt=str(record["prompt"]),
        tokenizer=tokenizer,
        device=device,
        numeric_tokenization="digit_safe",
    )
    initial_len = generated.shape[1]
    classes = _token_class_mask(record, tokenizer, device)
    masses = []
    new_ids = []
    for _ in range(MAX_NEW_TOKENS):
        context = generated[:, -model.config.max_sequence_length :]
        logits = model(context)
        next_token_id = int(torch.argmax(logits[:, -1, :], dim=-1).item())
        for layer_index, block in enumerate(model.blocks):
            attention = block.attention.last_attention_weights
            if attention is None:
                continue
            weights = attention[0, :, -1, :]
            relevant = _slice_class(classes["relevant"], context.shape[1])
            distractor = _slice_class(classes["distractor"], context.shape[1])
            generated_mask = torch.zeros(
                generated.shape[1],
                dtype=torch.bool,
                device=device,
            )
            generated_mask[initial_len : generated.shape[1]] = True
            masses.append(
                {
                    "layer": float(layer_index),
                    "relevant": float(weights[:, relevant].sum(dim=1).mean().item())
                    if bool(relevant.any())
                    else 0.0,
                    "distractor": float(weights[:, distractor].sum(dim=1).mean().item())
                    if bool(distractor.any())
                    else 0.0,
                    "generated": float(
                        weights[:, generated_mask[-context.shape[1] :]]
                        .sum(dim=1)
                        .mean()
                        .item()
                    )
                    if bool(generated_mask.any())
                    else 0.0,
                }
            )
        new_token = torch.tensor([[next_token_id]], device=device, dtype=torch.long)
        generated = torch.cat([generated, new_token], dim=1)
        new_ids.append(next_token_id)
        if next_token_id in {eos_id, end_id}:
            break
    return new_ids, masses


def _attention_key_mask(
    record: dict[str, Any],
    tokenizer: ByteLevelBpeTokenizer,
    device: torch.device,
) -> torch.Tensor:
    classes = _token_class_mask(record, tokenizer, device)
    mask = ~(classes["distractor"])
    return mask.unsqueeze(0).long()


def _token_class_mask(
    record: dict[str, Any],
    tokenizer: ByteLevelBpeTokenizer,
    device: torch.device,
) -> dict[str, torch.Tensor]:
    prompt = str(record["prompt"]).strip()
    metadata = record.get("metadata", {})
    active_start_char = int(metadata.get("active_prompt_start_char", 0))
    text = format_inference_prompt(prompt)
    encoded = tokenizer.encode_with_offsets(text, numeric_tokenization="digit_safe")
    prompt_start = len("<|prompt|>\n")
    active_start = prompt_start + active_start_char
    ids_len = len(encoded.ids) + 1
    relevant = torch.zeros(ids_len, dtype=torch.bool, device=device)
    distractor = torch.zeros(ids_len, dtype=torch.bool, device=device)
    for index, (_start, end) in enumerate(encoded.offsets, start=1):
        if end <= prompt_start:
            relevant[index] = True
        elif end <= active_start:
            distractor[index] = True
        else:
            relevant[index] = True
    relevant[0] = True
    return {"relevant": relevant, "distractor": distractor}


def _slice_class(mask: torch.Tensor, context_length: int) -> torch.Tensor:
    if mask.shape[0] >= context_length:
        return mask[-context_length:]
    pad = torch.zeros(
        context_length - mask.shape[0], dtype=torch.bool, device=mask.device
    )
    return torch.cat([mask, pad], dim=0)


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


def _split_cases(op: Primitive, rng: random.Random) -> dict[str, list[Case]]:
    if op == "add":
        cases = [Case(op, a, b) for a in range(10, 100) for b in range(10, 100)]
    else:
        cases = [Case(op, a, b) for a in range(10, 100) for b in range(1, a + 1)]
    rng.shuffle(cases)
    return {"eval": cases[:EVAL_PER_OP], "train": cases[EVAL_PER_OP:]}


def _write_train_sets(
    splits: dict[str, dict[str, list[Case]]],
    rng: random.Random,
) -> None:
    stage_specs = {
        "stage0_clean": ("clean",),
        "stage1_balanced": ("clean", *EASY_FAMILIES),
        "stage2_balanced": ("clean", *EASY_FAMILIES, *SEMANTIC_FAMILIES),
        "stage3_balanced": (
            "clean",
            *EASY_FAMILIES,
            *SEMANTIC_FAMILIES,
            *ARITHMETIC_FAMILIES,
        ),
        "stage4_balanced": (
            "clean",
            *EASY_FAMILIES,
            *SEMANTIC_FAMILIES,
            *ARITHMETIC_FAMILIES,
            *HARD_FAMILIES,
        ),
    }
    for name, families in stage_specs.items():
        records = []
        for op in ("add", "sub"):
            for _ in range(TRAIN_PER_OP):
                case = rng.choice(splits[op]["train"])
                family = rng.choice(families)
                length = 0 if family == "clean" else rng.randint(1, 16)
                records.append(_record(case, family=family, length=length, split=name))
        rng.shuffle(records)
        _write_jsonl(DATASET_DIR / "train" / f"{name}.jsonl", records)


def _write_variable_binding_probe(cases: list[Case]) -> None:
    records = []
    for chain_count in (0, 1, 2, 4, 8):
        for index, case in enumerate(cases):
            prompt = _binding_prompt(case, chain_count)
            records.append(
                {
                    **_base_record(case, prompt, "variable_binding", len(records)),
                    "task_type": f"m175.binding.chain_{chain_count}",
                    "metadata": {
                        "op": case.op_token,
                        "chain_count": chain_count,
                        "active_prompt_start_char": prompt.rfind("QUERY"),
                    },
                }
            )
    _write_jsonl(DATASET_DIR / "probe" / "variable_binding.jsonl", records)


def _records_for_cases(
    cases: list[Case],
    *,
    family: str,
    length: int,
    split: str,
    heldout: bool = True,
) -> list[dict[str, Any]]:
    return [
        _record(
            case,
            family=family,
            length=length,
            split=split,
            index=index,
            heldout=heldout,
        )
        for index, case in enumerate(cases)
    ]


def _record(
    case: Case,
    *,
    family: str,
    length: int,
    split: str,
    index: int | None = None,
    heldout: bool = False,
) -> dict[str, Any]:
    prompt, active_start = _prompt_with_distractor(
        case,
        family=family,
        length=length,
        heldout=heldout,
    )
    record = _base_record(case, prompt, split, 0 if index is None else index)
    record["task_type"] = f"m175.{case.op}.{family}"
    record["metadata"].update(
        {
            "family": family,
            "length": length,
            "active_prompt_start_char": active_start,
        }
    )
    return record


def _base_record(case: Case, prompt: str, split: str, index: int) -> dict[str, Any]:
    return {
        "id": f"m175.{case.op}.{split}.{index:06d}",
        "task_type": f"m175.{case.op}",
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


def _prompt_with_distractor(
    case: Case,
    *,
    family: str,
    length: int,
    heldout: bool,
) -> tuple[str, int]:
    active = _canonical_prompt(case)
    if family == "clean" or length <= 0:
        return active, 0
    prefix = _distractor_prefix(case, family=family, length=length, heldout=heldout)
    return f"{prefix}\n{active}", len(prefix) + 1


def _canonical_prompt(case: Case) -> str:
    return f"{case.op_token} {case.a:02d} {case.sign} {case.b:02d}"


def _distractor_prefix(
    case: Case,
    *,
    family: str,
    length: int,
    heldout: bool,
) -> str:
    if family == "neutral":
        return " ".join(["CTX" if heldout else "PAD"] * length)
    if family == "random_vocab":
        vocab = [
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
            "QUARTZ",
            "RIVER",
            "SOLAR",
            "TULIP",
        ]
        return " ".join(
            vocab[(length + 5 * index) % len(vocab)] for index in range(length)
        )
    if family == "natural_phrase":
        chunks = ["ASIDE", "UNUSED", "IGNORE", "OTHER"] if heldout else ["NOTE"]
        return " ".join(chunks[index % len(chunks)] for index in range(length))
    if family in ARITHMETIC_FAMILIES or family == "hard_negative":
        lines = []
        for index in range(length):
            op = _distractor_op(case, family, index)
            a, b = _distractor_operands(case, family, index)
            sign = "+" if op == "ADD" else "-"
            result = a + b if op == "ADD" else max(0, a - b)
            if heldout:
                lines.append(f"DONE {op}{a}{sign}{b}={result}")
            else:
                lines.append(f"D{op[0]}{a}{sign}{b}={result}")
        return " ".join(lines)
    raise AssertionError(family)


def _distractor_op(case: Case, family: str, index: int) -> str:
    if family == "previous_same_op":
        return case.op_token
    if family == "previous_opposite_op":
        return "SUB" if case.op == "add" else "ADD"
    if family == "hard_negative":
        return case.op_token
    return "ADD" if index % 2 == 0 else "SUB"


def _distractor_operands(case: Case, family: str, index: int) -> tuple[int, int]:
    if family == "hard_negative":
        if index % 2 == 0:
            return case.a, 10 + ((case.b + 17 * index + 9) % 80)
        return 10 + ((case.a + 13 * index + 7) % 80), case.b
    a = 10 + ((case.a + 19 * index + 11) % 80)
    b = 10 + ((case.b + 23 * index + 13) % 80)
    if case.op == "sub" and a < b:
        a, b = b, a
    return a, b


def _binding_prompt(case: Case, chain_count: int) -> str:
    lines = [f"A = {case.a}", f"B = {case.b}"]
    for index in range(chain_count):
        name = chr(ord("C") + index)
        value = 10 + ((case.a + case.b + index * 17) % 80)
        lines.append(f"{name} = {value}")
    lines.append(f"QUERY {case.op_token} A B")
    return "\n".join(lines)


def _family_lengths(family: str) -> tuple[int, ...]:
    return HARD_LENGTHS if family in {*ARITHMETIC_FAMILIES, *HARD_FAMILIES} else LENGTHS


def _write_manifest(splits: dict[str, dict[str, list[Case]]]) -> None:
    manifest = {
        "kind": "m175_distractor_routing",
        "seed": SEED,
        "train_per_op": TRAIN_PER_OP,
        "eval_per_op": EVAL_PER_OP,
        "families": list(FAMILIES),
        "lengths": list(LENGTHS),
        "hard_lengths": list(HARD_LENGTHS),
        "relative_baseline_checkpoint": str(M174_RELATIVE_CHECKPOINT),
        "prompt_intersections": _prompt_intersections(),
        "case_counts": {
            op: {split: len(cases) for split, cases in payload.items()}
            for op, payload in splits.items()
        },
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _prompt_intersections() -> dict[str, int]:
    train = _prompts(DATASET_DIR / "train" / "stage4_balanced.jsonl")
    clean = _prompts(DATASET_DIR / "eval" / "clean.jsonl")
    return {"stage4_vs_clean_eval": len(train & clean)}


def _collect_oracle_results() -> dict[str, Any]:
    result = {}
    for family in ("neutral", "random_vocab", "natural_phrase", "previous_arithmetic"):
        result[family] = {}
        for length in _family_lengths(family):
            normal = _read_summary_payload(
                RUNS_DIR / "baseline" / family / f"len_{length}"
            )
            oracle = _read_summary_payload(
                RUNS_DIR / "oracle_mask" / family / f"len_{length}"
            )
            result[family][str(length)] = {"normal": normal, "oracle": oracle}
    return result


def _collect_curriculum_results() -> dict[str, Any]:
    result = {}
    for stage in range(1, 5):
        name = f"strong_curriculum_stage{stage}"
        result[name] = _collect_benchmark(RUNS_DIR / name / "benchmark")
    return result


def _collect_routing_variants() -> dict[str, Any]:
    names = [
        *(
            f"relevance_aux_l{str(weight).replace('.', '_')}"
            for weight in RELEVANCE_LAMBDAS
        ),
        "relevance_gate_l0_1",
        "differential_relative_fit",
    ]
    return {name: _collect_benchmark(RUNS_DIR / name / "benchmark") for name in names}


def _collect_variable_binding_results() -> dict[str, Any]:
    result = {}
    for name in (
        "strong_curriculum_stage4",
        "relevance_gate_l0_1",
        "differential_relative_fit",
    ):
        result[name] = _read_summary_payload(
            RUNS_DIR / name / "benchmark" / "variable_binding"
        )
    return result


def _collect_benchmark(base: Path) -> dict[str, Any]:
    if not base.exists():
        return {"status": "missing"}
    result = {"status": "complete", "clean": _read_summary_payload(base / "clean")}
    for family in FAMILIES:
        result[family] = {
            str(length): _read_summary_payload(base / family / f"len_{length}")
            for length in _family_lengths(family)
        }
    result["relevance"] = _read_json_if_exists(base / "relevance_metrics.json")
    return result


def _read_summary_payload(path: Path) -> dict[str, Any]:
    summary_path = path / "summary.json"
    if not summary_path.exists():
        return {"status": "missing", "final_nem": 0.0, "by_task_type": {}}
    return _summary_payload(_read_json(summary_path))


def _summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    overall = summary.get("overall", summary)
    by_task = summary.get("by_task_type", {})
    return {
        "status": "complete",
        "summary": summary,
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
        "by_task_type": {
            key: float(value.get("final_normalized_exact_match", 0.0))
            for key, value in by_task.items()
        },
    }


def _oracle_restores(analysis: dict[str, Any]) -> bool:
    values = []
    for family, curve in analysis.get("oracle", {}).items():
        for length, payload in curve.items():
            limit = 8 if family == "previous_arithmetic" else 16
            if int(length) <= limit:
                values.append(payload["oracle"]["final_nem"])
    return bool(values) and min(values) >= 0.95


def _composition_gate(analysis: dict[str, Any]) -> dict[str, Any]:
    candidates = {
        **analysis.get("curriculum", {}),
        **analysis.get("routing_variants", {}),
    }
    best_name, best = _best_candidate(candidates)
    if not best:
        return {"should_run": False, "reason": "no complete routing candidate"}
    clean = best["clean"]["final_nem"]
    easy = _family_min(best, (*EASY_FAMILIES,), max_length=16)
    natural = _family_min(best, SEMANTIC_FAMILIES, max_length=16)
    previous = _family_min(best, ARITHMETIC_FAMILIES, max_length=8)
    hard = _family_min(best, HARD_FAMILIES, max_length=8)
    passed = (
        clean >= 0.98
        and easy >= 0.95
        and natural >= 0.90
        and previous >= 0.90
        and hard >= 0.85
    )
    return {
        "should_run": passed,
        "candidate": best_name,
        "reason": (
            f"clean={clean:.4f}, easy={easy:.4f}, natural={natural:.4f}, "
            f"previous={previous:.4f}, hard={hard:.4f}"
        ),
    }


def _best_candidate(
    candidates: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    best_name = None
    best_payload = None
    best_score = -1.0
    for name, payload in candidates.items():
        if payload.get("status") != "complete":
            continue
        score = min(
            payload["clean"]["final_nem"],
            _family_min(payload, EASY_FAMILIES, max_length=16),
            _family_min(payload, SEMANTIC_FAMILIES, max_length=16),
            _family_min(payload, (*ARITHMETIC_FAMILIES, *HARD_FAMILIES), max_length=8),
        )
        if score > best_score:
            best_score = score
            best_name = name
            best_payload = payload
    return best_name, best_payload


def _family_min(
    payload: dict[str, Any], families: tuple[str, ...], *, max_length: int
) -> float:
    values = []
    for family in families:
        for length, result in payload.get(family, {}).items():
            if int(length) <= max_length:
                values.append(result["final_nem"])
    return min(values) if values else 0.0


def _best_aux_checkpoint() -> Path | None:
    best_name = None
    best_loss = float("inf")
    for weight in RELEVANCE_LAMBDAS:
        name = f"relevance_aux_l{str(weight).replace('.', '_')}"
        metrics = RUNS_DIR / name / "metrics.jsonl"
        if not metrics.exists():
            continue
        last = _last_jsonl(metrics)
        loss = float(last.get("eval_loss", float("inf")))
        if loss < best_loss:
            best_loss = loss
            best_name = name
    if best_name is None:
        return None
    return _checkpoint_path(RUNS_DIR / best_name, VARIANT_STEPS)


def _spec_payload(spec: RunSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "train_path": str(spec.train_path),
        "eval_path": str(spec.eval_path),
        "init_checkpoint_path": str(spec.init_checkpoint_path)
        if spec.init_checkpoint_path
        else None,
        "steps": spec.steps,
        "relevance_mode": spec.relevance_mode,
        "relevance_loss_weight": spec.relevance_loss_weight,
        "attention_variant": spec.attention_variant,
        "seed": spec.seed,
    }


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


def _last_jsonl(path: Path) -> dict[str, Any]:
    last: dict[str, Any] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            last = json.loads(line)
    return last


def _checkpoint_path(output_dir: Path, step: int) -> Path:
    return output_dir / "checkpoints" / f"step_{step:06d}.pt"


def _required_token_id(tokenizer: ByteLevelBpeTokenizer, token: str) -> int:
    token_id = tokenizer.token_to_id(token)
    if token_id is None:
        raise ValueError(f"Tokenizer is missing required special token: {token}")
    return token_id


def _require_relative_checkpoint() -> None:
    if not M174_RELATIVE_CHECKPOINT.exists():
        raise FileNotFoundError(
            f"Missing M-17.4 relative checkpoint: {M174_RELATIVE_CHECKPOINT}"
        )


def _oracle_table(analysis: dict[str, Any]) -> str:
    rows = ["| family | length | normal | oracle |", "|---|---:|---:|---:|"]
    for family, curve in analysis.get("oracle", {}).items():
        for length, payload in curve.items():
            rows.append(
                f"| {family} | {length} | {payload['normal']['final_nem']:.4f} | "
                f"{payload['oracle']['final_nem']:.4f} |"
            )
    return "\n".join(rows)


def _attention_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("attention_diagnostics", {})
    if payload.get("status") == "missing":
        return "missing"
    rows = [
        "| bucket | count | relevant mass | distractor mass | generated mass | rel/dist |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, value in sorted(payload.items()):
        rows.append(
            f"| {key} | {value['count']} | {value['relevant_attention_mass']:.4f} | "
            f"{value['distractor_attention_mass']:.4f} | "
            f"{value['generated_attention_mass']:.4f} | "
            f"{value['relevant_distractor_ratio']:.4f} |"
        )
    return "\n".join(rows)


def _curriculum_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| run | clean | easy min16 | semantic min16 | hard/arith min8 |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, payload in analysis.get("curriculum", {}).items():
        if payload.get("status") != "complete":
            continue
        rows.append(_candidate_row(name, payload))
    return "\n".join(rows)


def _relevance_table(analysis: dict[str, Any]) -> str:
    rows = ["| run | precision | recall | f1 |", "|---|---:|---:|---:|"]
    for name, payload in analysis.get("routing_variants", {}).items():
        rel = payload.get("relevance", {})
        if not rel or rel.get("status") == "missing":
            continue
        rows.append(
            f"| {name} | {rel.get('precision', 0.0):.4f} | "
            f"{rel.get('recall', 0.0):.4f} | {rel.get('f1', 0.0):.4f} |"
        )
    return "\n".join(rows) if len(rows) > 2 else "not available"


def _ladder_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| run | clean | easy min16 | semantic min16 | hard/arith min8 |",
        "|---|---:|---:|---:|---:|",
    ]
    baseline = _baseline_ladder_payload(analysis)
    if baseline:
        rows.append(_candidate_row("relative_shaw_baseline", baseline))
    oracle = _oracle_ladder_payload(analysis)
    if oracle:
        rows.append(_candidate_row("oracle_mask_upper_bound", oracle))
    for name, payload in analysis.get("routing_variants", {}).items():
        if payload.get("status") == "complete":
            rows.append(_candidate_row(name, payload))
    return "\n".join(rows)


def _candidate_row(name: str, payload: dict[str, Any]) -> str:
    return (
        f"| {name} | {payload['clean']['final_nem']:.4f} | "
        f"{_family_min(payload, EASY_FAMILIES, max_length=16):.4f} | "
        f"{_family_min(payload, SEMANTIC_FAMILIES, max_length=16):.4f} | "
        f"{_family_min(payload, (*ARITHMETIC_FAMILIES, *HARD_FAMILIES), max_length=8):.4f} |"
    )


def _differential_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("routing_variants", {}).get("differential_relative_fit", {})
    if payload.get("status") != "complete":
        return payload.get("status", "missing")
    return _candidate_row("differential_relative_fit", payload)


def _hard_negative_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| run | len1 | len2 | len4 | len8 | len16 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for group in ("curriculum", "routing_variants"):
        for name, payload in analysis.get(group, {}).items():
            if payload.get("status") != "complete" or "hard_negative" not in payload:
                continue
            scores = [
                payload["hard_negative"].get(str(length), {}).get("final_nem", 0.0)
                for length in HARD_LENGTHS
            ]
            rows.append(
                f"| {name} | " + " | ".join(f"{score:.4f}" for score in scores) + " |"
            )
    return "\n".join(rows)


def _variable_binding_table(analysis: dict[str, Any]) -> str:
    rows = ["| run | final NEM |", "|---|---:|"]
    for name, payload in analysis.get("variable_binding", {}).items():
        if payload.get("status") == "complete":
            rows.append(f"| {name} | {payload['final_nem']:.4f} |")
    return "\n".join(rows) if len(rows) > 2 else "missing"


def _baseline_ladder_payload(analysis: dict[str, Any]) -> dict[str, Any] | None:
    oracle = analysis.get("oracle", {})
    if not oracle:
        return None
    payload = {"status": "complete", "clean": {"final_nem": 1.0}}
    for family, curve in oracle.items():
        payload[family] = {length: value["normal"] for length, value in curve.items()}
    return payload


def _oracle_ladder_payload(analysis: dict[str, Any]) -> dict[str, Any] | None:
    oracle = analysis.get("oracle", {})
    if not oracle:
        return None
    payload = {"status": "complete", "clean": {"final_nem": 1.0}}
    for family, curve in oracle.items():
        payload[family] = {length: value["oracle"] for length, value in curve.items()}
    return payload


def _decision(analysis: dict[str, Any]) -> str:
    if not _oracle_restores(analysis):
        return "OUTCOME E: even oracle masking did not restore robustness; stop before learned routing."
    candidates = {
        **analysis.get("curriculum", {}),
        **analysis.get("routing_variants", {}),
    }
    best_name, best = _best_candidate(candidates)
    if best is None:
        return "OUTCOME A: oracle mask restores performance, confirming routing as the bottleneck; learned routing runs are missing."
    if analysis["gate"]["should_run"]:
        return f"OUTCOME B/C: `{best_name}` passes routing gate; proceed to minimal ADD_SUB composition."
    oracle_payload = _oracle_ladder_payload(analysis)
    oracle_easy = _family_min(oracle_payload or {}, EASY_FAMILIES, max_length=16)
    if oracle_easy >= 0.95:
        return (
            "OUTCOME D: oracle routing works but learned curriculum/gating did not "
            f"reach the gate. Best candidate: `{best_name}`. Next step: more explicit "
            "router or segmented working-context architecture."
        )
    return f"OUTCOME A partial: best learned candidate is `{best_name}`, but robustness remains below composition gate."


def _device_name(analysis: dict[str, Any]) -> str:
    for family in analysis.get("oracle", {}).values():
        for payload in family.values():
            summary = payload.get("normal", {}).get("summary", {})
            if "device" in summary:
                return f"{summary.get('device')} ({summary.get('device_name')})"
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
