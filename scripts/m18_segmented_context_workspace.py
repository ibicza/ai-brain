from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import torch
import torch.nn.functional as F

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
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import BOS_TOKEN
from ai_brain.language.tokenizer.text_format import format_inference_prompt
from ai_brain.runtime.device import get_device_info
from ai_brain.segments import (
    SEG_ANSWER,
    SEG_CONTEXT,
    SEG_CONTROL,
    SEG_QUERY,
    SEG_WORKSPACE,
    SegmentAttentionMode,
    build_segment_attention_allow_mask,
)
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
M175_DATASET_DIR = ROOT / "datasets" / "m175_distractor_routing"
DATASET_DIR = ROOT / "datasets" / "m18_segmented_context_workspace"
RUNS_DIR = ROOT / "runs" / "m18_segmented_context_workspace_v2"
DOC_PATH = ROOT / "docs" / "m18_segmented_context_workspace_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m18_segmented_context_workspace_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"
M174_RELATIVE_CHECKPOINT = (
    ROOT
    / "runs"
    / "m174_position_architecture"
    / "relative_shaw"
    / "checkpoints"
    / "step_020000.pt"
)

SEED = 18000
SEQUENCE_LENGTH = 256
MAX_NEW_TOKENS = 32
LENGTHS = (1, 2, 4, 8, 16, 32)
HARD_LENGTHS = (1, 2, 4, 8, 16)
PHASE3_FAMILIES = (
    "neutral",
    "random_vocab",
    "natural_phrase",
    "previous_arithmetic",
    "hard_negative",
)
TRAIN_STEPS = 8000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-oracle-segments")
    subparsers.add_parser("run-contamination-probe")
    subparsers.add_parser("run-training")
    subparsers.add_parser("run-selective-context")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-oracle-segments":
        run_oracle_segments()
    elif args.command == "run-contamination-probe":
        run_contamination_probe()
    elif args.command == "run-training":
        run_segment_training()
    elif args.command == "run-selective-context":
        run_selective_context()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_oracle_segments()
        run_contamination_probe()
        analyze_all()
        if _oracle_segment_gate(_read_json(RUNS_DIR / "analysis.json")):
            run_segment_training()
            analyze_all()
            if _training_gate(_read_json(RUNS_DIR / "analysis.json")):
                run_selective_context()
                analyze_all()
        build_report(checks_passed=False)
    return 0


def prepare_datasets() -> None:
    if not M175_DATASET_DIR.exists():
        raise FileNotFoundError(
            f"Missing M-17.5 datasets: {M175_DATASET_DIR}. "
            "Run scripts/m175_distractor_routing.py prepare-datasets first."
        )
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    _copy_enriched(
        M175_DATASET_DIR / "eval" / "clean.jsonl",
        DATASET_DIR / "eval" / "clean.jsonl",
    )
    for family in PHASE3_FAMILIES:
        for length in _family_lengths(family):
            _copy_enriched(
                M175_DATASET_DIR / "eval" / family / f"len_{length}.jsonl",
                DATASET_DIR / "eval" / family / f"len_{length}.jsonl",
            )

    train_records = _build_mixed_training_records()
    _write_jsonl(DATASET_DIR / "train" / "mixed_segmented.jsonl", train_records)
    _write_jsonl(
        DATASET_DIR / "eval" / "relevant_context.jsonl",
        _relevant_context_records(),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "variable_binding.jsonl",
        _variable_binding_records(),
    )
    _write_jsonl(
        DATASET_DIR / "eval" / "add_sub_composition.jsonl",
        _add_sub_records(),
    )
    _write_manifest()


def run_oracle_segments() -> None:
    _require_checkpoint()
    device_info = get_device_info()
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, checkpoint = load_model_for_inference(
        checkpoint_path=M174_RELATIVE_CHECKPOINT,
        tokenizer_path=TOKENIZER_PATH,
        device=device_info.device,
    )
    for mode in ("flat_causal", "old_key_oracle", "query_isolated", "workspace"):
        _eval_records(
            model=model,
            checkpoint=checkpoint,
            tokenizer=tokenizer,
            eval_path=DATASET_DIR / "eval" / "clean.jsonl",
            output_dir=RUNS_DIR / "phase3" / mode / "clean",
            segment_mode="flat_causal" if mode == "old_key_oracle" else mode,
            old_key_oracle=(mode == "old_key_oracle"),
            device=device_info.device,
        )
        for family in PHASE3_FAMILIES:
            for length in _family_lengths(family):
                _eval_records(
                    model=model,
                    checkpoint=checkpoint,
                    tokenizer=tokenizer,
                    eval_path=DATASET_DIR / "eval" / family / f"len_{length}.jsonl",
                    output_dir=RUNS_DIR / "phase3" / mode / family / f"len_{length}",
                    segment_mode="flat_causal" if mode == "old_key_oracle" else mode,
                    old_key_oracle=(mode == "old_key_oracle"),
                    device=device_info.device,
                )


def run_contamination_probe() -> None:
    _require_checkpoint()
    output_path = RUNS_DIR / "contamination_probe" / "summary.json"
    if output_path.exists():
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    device_info = get_device_info()
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _checkpoint = load_model_for_inference(
        checkpoint_path=M174_RELATIVE_CHECKPOINT,
        tokenizer_path=TOKENIZER_PATH,
        device=device_info.device,
    )
    records = _probe_record_pairs()
    buckets: dict[str, list[float]] = defaultdict(list)
    for clean, distracted in records:
        clean_positions = _role_positions(tokenizer, clean)
        for mode in ("flat_causal", "query_isolated", "workspace"):
            clean_hidden = _layer_hiddens(
                model=model,
                tokenizer=tokenizer,
                record=clean,
                mode=mode,
                device=device_info.device,
            )
            distracted_hidden = _layer_hiddens(
                model=model,
                tokenizer=tokenizer,
                record=distracted,
                mode=mode,
                device=device_info.device,
            )
            distracted_positions = _role_positions(tokenizer, distracted)
            for role, clean_index in clean_positions.items():
                distracted_index = distracted_positions[role]
                for layer_index in range(clean_hidden.shape[0]):
                    similarity = F.cosine_similarity(
                        clean_hidden[layer_index, clean_index],
                        distracted_hidden[layer_index, distracted_index],
                        dim=0,
                    )
                    buckets[f"{mode}.{role}.layer{layer_index + 1}"].append(
                        float(similarity.detach().cpu().item())
                    )
    summary = {
        key: {"count": len(values), "cosine": mean(values)}
        for key, values in sorted(buckets.items())
    }
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_segment_training() -> None:
    analysis_path = RUNS_DIR / "analysis.json"
    if not analysis_path.exists():
        analyze_all()
    if not _oracle_segment_gate(_read_json(analysis_path)):
        print("skip segment training: oracle segment gate did not pass")
        return
    for mode in ("query_isolated", "workspace"):
        output_dir = RUNS_DIR / "phase5_training" / mode
        checkpoint = output_dir / "checkpoints" / f"step_{TRAIN_STEPS:06d}.pt"
        if not checkpoint.exists():
            config = TrainConfig(
                train_path=DATASET_DIR / "train" / "mixed_segmented.jsonl",
                eval_path=DATASET_DIR / "eval" / "clean.jsonl",
                tokenizer_path=TOKENIZER_PATH,
                output_dir=output_dir,
                model_config_name="arithmetic_3m",
                steps=TRAIN_STEPS,
                batch_size=8,
                sequence_length=SEQUENCE_LENGTH,
                loss_mode="answer-only",
                learning_rate=3e-4,
                grad_clip_norm=1.0,
                numeric_tokenization="digit_safe",
                position_encoding="relative",
                segment_attention_mode=mode,
                seed=SEED + (1 if mode == "query_isolated" else 2),
                eval_every=1000,
                eval_batches=20,
                save_every=TRAIN_STEPS,
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
        _eval_trained_checkpoint(checkpoint=checkpoint, mode=mode)


def run_selective_context() -> None:
    analysis_path = RUNS_DIR / "analysis.json"
    if not analysis_path.exists():
        analyze_all()
    if not _training_gate(_read_json(analysis_path)):
        print("skip selective context: phase5 training gate did not pass")
        return
    best = _best_trained_mode(_read_json(analysis_path))
    if best is None:
        return
    checkpoint = (
        RUNS_DIR
        / "phase5_training"
        / best
        / "checkpoints"
        / f"step_{TRAIN_STEPS:06d}.pt"
    )
    _eval_trained_checkpoint(checkpoint=checkpoint, mode=best, extra=True)


def analyze_all() -> None:
    analysis = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "phase3": _collect_phase3(),
        "contamination_probe": _read_json_if_exists(
            RUNS_DIR / "contamination_probe" / "summary.json"
        ),
        "phase5_training": _collect_phase5(),
        "selective_context": _collect_selective_context(),
        "gates": {},
    }
    analysis["gates"]["oracle_segments"] = _oracle_segment_gate(analysis)
    analysis["gates"]["training"] = _training_gate(analysis)
    analysis["decision"] = _decision(analysis)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    lines = [
        "# M-18 Segmented Context Workspace Report",
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
        "## Flat vs Old Oracle vs Query-Isolated vs Workspace",
        "",
        _phase3_table(analysis),
        "",
        "## Distractor Robustness by Family and Length",
        "",
        _robustness_table(analysis),
        "",
        "## Layerwise Clean-vs-Distracted Hidden Similarity",
        "",
        _contamination_table(analysis),
        "",
        "## Clean Accuracy",
        "",
        _clean_table(analysis),
        "",
        "## Relevant-Context Retrieval",
        "",
        _selective_context_table(analysis),
        "",
        "## Oracle vs Learned Chunk Selection",
        "",
        _learned_selection_table(analysis),
        "",
        "## Variable-Binding Result",
        "",
        _variable_binding_table(analysis),
        "",
        "## ADD_SUB Composition",
        "",
        _composition_table(analysis),
        "",
        "## Recommended Context Architecture",
        "",
        analysis.get("decision", "missing"),
    ]
    text = "\n".join(lines)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def _copy_enriched(source: Path, target: Path) -> None:
    records = [_with_segment_spans(record) for record in _iter_jsonl(source)]
    _write_jsonl(target, records)


def _with_segment_spans(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    metadata = dict(result.get("metadata", {}))
    prompt = str(result["prompt"]).strip()
    active_start = int(metadata.get("active_prompt_start_char", 0))
    spans = []
    if active_start > 0:
        spans.append(
            {
                "start": 0,
                "end": active_start,
                "segment": "context",
                "access": False,
            }
        )
    spans.append(
        {
            "start": active_start,
            "end": len(prompt),
            "segment": "query",
            "access": False,
        }
    )
    metadata["segment_spans"] = spans
    metadata["segment_schema"] = "m18.v1"
    result["metadata"] = metadata
    return result


def _build_mixed_training_records() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    source_paths = [
        M175_DATASET_DIR / "train" / "stage0_clean.jsonl",
        M175_DATASET_DIR / "train" / "stage4_balanced.jsonl",
    ]
    for path in source_paths:
        if path.exists():
            candidates.extend(
                _with_segment_spans(record) for record in _iter_jsonl(path)
            )
    if not candidates:
        raise FileNotFoundError("Missing M-17.5 stage training datasets")
    buckets = {"clean": [], "easy": [], "natural": [], "hard": []}
    for record in candidates:
        family = str(record.get("metadata", {}).get("family", "clean"))
        if family == "clean":
            buckets["clean"].append(record)
        elif family in {"neutral", "random_vocab"}:
            buckets["easy"].append(record)
        elif family == "natural_phrase":
            buckets["natural"].append(record)
        else:
            buckets["hard"].append(record)
    per_bucket = min(2500, *(len(value) for value in buckets.values() if value))
    records = []
    for key in ("clean", "easy", "natural", "hard"):
        records.extend(buckets[key][:per_bucket])
    return records


def _relevant_context_records() -> list[dict[str, Any]]:
    records = []
    for index, (a, b) in enumerate(_case_values(240)):
        prompt = (
            f"A = {a:02d}\nJUNK = {(a + b + 17) % 90:02d}\nB = {b:02d}\nQUERY ADD A B"
        )
        records.append(
            _record_with_spans(
                record_id=f"m18.relevant.{index:05d}",
                task_type="m18.relevant_context",
                prompt=prompt,
                answer=f"FINAL {a + b}",
                spans=[
                    ("context", 0, len(f"A = {a:02d}"), True),
                    (
                        "context",
                        len(f"A = {a:02d}\n"),
                        len(f"A = {a:02d}\nJUNK = {(a + b + 17) % 90:02d}"),
                        False,
                    ),
                    (
                        "context",
                        len(f"A = {a:02d}\nJUNK = {(a + b + 17) % 90:02d}\n"),
                        len(
                            f"A = {a:02d}\nJUNK = {(a + b + 17) % 90:02d}\nB = {b:02d}"
                        ),
                        True,
                    ),
                    ("query", prompt.index("QUERY"), len(prompt), False),
                ],
                metadata={"a": a, "b": b, "kind": "relevant"},
            )
        )
    return records


def _variable_binding_records() -> list[dict[str, Any]]:
    records = []
    for depth in (1, 2, 4):
        for index, (a, b) in enumerate(_case_values(80, offset=depth * 31)):
            lines = [f"A = {a:02d}"]
            for distractor_index in range(depth * 2):
                lines.append(
                    f"X{distractor_index} = {(a + b + distractor_index * 13) % 90:02d}"
                )
            lines.append(f"B = {b:02d}")
            lines.append("QUERY ADD A B")
            prompt = "\n".join(lines)
            spans = []
            cursor = 0
            for line in lines[:-1]:
                access = line.startswith(("A =", "B ="))
                spans.append(("context", cursor, cursor + len(line), access))
                cursor += len(line) + 1
            spans.append(("query", prompt.index("QUERY"), len(prompt), False))
            records.append(
                _record_with_spans(
                    record_id=f"m18.binding.d{depth}.{index:05d}",
                    task_type=f"m18.variable_binding.depth{depth}",
                    prompt=prompt,
                    answer=f"FINAL {a + b}",
                    spans=spans,
                    metadata={"a": a, "b": b, "depth": depth},
                )
            )
    return records


def _add_sub_records() -> list[dict[str, Any]]:
    records = []
    for index, (a, b) in enumerate(_case_values(160)):
        sub = 10 + ((a + b + 7) % 40)
        intermediate = a + b
        final = intermediate - sub
        prompt = (
            f"QUERY ADD {a:02d} {b:02d}\n"
            f"WORKSPACE INTERMEDIATE {intermediate}\n"
            f"QUERY SUB {intermediate} {sub:02d}"
        )
        records.append(
            _record_with_spans(
                record_id=f"m18.add_sub.{index:05d}",
                task_type="m18.add_sub",
                prompt=prompt,
                answer=f"FINAL {final}",
                spans=[
                    ("query", 0, len(f"QUERY ADD {a:02d} {b:02d}"), False),
                    (
                        "workspace",
                        prompt.index("WORKSPACE"),
                        prompt.index("\nQUERY SUB"),
                        False,
                    ),
                    ("query", prompt.rindex("QUERY"), len(prompt), False),
                ],
                metadata={"a": a, "b": b, "sub": sub, "intermediate": intermediate},
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
            "segment_schema": "m18.v1",
            "segment_spans": [
                {"segment": segment, "start": start, "end": end, "access": access}
                for segment, start, end, access in spans
            ],
        },
    }


def _case_values(count: int, *, offset: int = 0) -> list[tuple[int, int]]:
    values = []
    for index in range(count):
        a = 10 + ((17 * index + 3 + offset) % 80)
        b = 10 + ((23 * index + 9 + offset) % 80)
        values.append((a, b))
    return values


def _eval_trained_checkpoint(
    *,
    checkpoint: Path,
    mode: SegmentAttentionMode,
    extra: bool = False,
) -> None:
    device_info = get_device_info()
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, loaded = load_model_for_inference(
        checkpoint_path=checkpoint,
        tokenizer_path=TOKENIZER_PATH,
        device=device_info.device,
    )
    base = RUNS_DIR / "phase5_training" / mode / "benchmark"
    _eval_records(
        model=model,
        checkpoint=loaded,
        tokenizer=tokenizer,
        eval_path=DATASET_DIR / "eval" / "clean.jsonl",
        output_dir=base / "clean",
        segment_mode=mode,
        old_key_oracle=False,
        device=device_info.device,
    )
    for family in PHASE3_FAMILIES:
        for length in _family_lengths(family):
            _eval_records(
                model=model,
                checkpoint=loaded,
                tokenizer=tokenizer,
                eval_path=DATASET_DIR / "eval" / family / f"len_{length}.jsonl",
                output_dir=base / family / f"len_{length}",
                segment_mode=mode,
                old_key_oracle=False,
                device=device_info.device,
            )
    if extra:
        for name in (
            "relevant_context",
            "variable_binding",
            "add_sub_composition",
        ):
            _eval_records(
                model=model,
                checkpoint=loaded,
                tokenizer=tokenizer,
                eval_path=DATASET_DIR / "eval" / f"{name}.jsonl",
                output_dir=base / name,
                segment_mode=mode,
                old_key_oracle=False,
                device=device_info.device,
            )


@torch.no_grad()
def _eval_records(
    *,
    model: torch.nn.Module,
    checkpoint: dict[str, Any],
    tokenizer: ByteLevelBpeTokenizer,
    eval_path: Path,
    output_dir: Path,
    segment_mode: SegmentAttentionMode,
    old_key_oracle: bool,
    device: torch.device,
) -> dict[str, Any]:
    summary_path = output_dir / "summary.json"
    if summary_path.exists():
        return _summary_payload(_read_json(summary_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions = []
    predictions_path = output_dir / "predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as file:
        for index, record in enumerate(_iter_jsonl(eval_path)):
            segment_ids, context_access = _segment_tensors_for_inference(
                tokenizer=tokenizer,
                record=record,
                device=device,
            )
            attention_key_mask = None
            if old_key_oracle:
                attention_key_mask = (segment_ids != SEG_CONTEXT).long()
            generated_ids = generate_answer_ids(
                model=model,
                tokenizer=tokenizer,
                prompt=str(record["prompt"]),
                max_new_tokens=MAX_NEW_TOKENS,
                device=device,
                numeric_tokenization="digit_safe",
                attention_key_mask=attention_key_mask,
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
        "checkpoint_path": str(M174_RELATIVE_CHECKPOINT),
        "checkpoint_step": checkpoint.get("step"),
        "eval_path": str(eval_path),
        "tokenizer_path": str(TOKENIZER_PATH),
        "numeric_tokenization": "digit_safe",
        "segment_attention_mode": segment_mode,
        "old_key_oracle": old_key_oracle,
        "predictions_path": str(predictions_path),
        "device": str(device),
        "device_name": get_device_info().name,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return _summary_payload(summary)


def _segment_tensors_for_inference(
    *,
    tokenizer: ByteLevelBpeTokenizer,
    record: dict[str, Any],
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor]:
    prompt = str(record["prompt"]).strip()
    text = format_inference_prompt(prompt)
    encoded = tokenizer.encode_with_offsets(text, numeric_tokenization="digit_safe")
    ids = [
        _required_token_id(tokenizer, BOS_TOKEN),
        *encoded.ids,
    ]
    expected_ids = build_inference_input_ids(
        prompt=prompt,
        tokenizer=tokenizer,
        device=torch.device("cpu"),
        numeric_tokenization="digit_safe",
    )[0].tolist()
    if ids != expected_ids:
        raise ValueError("segment tensor tokenization mismatch")
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
    segment_map = {
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
            "segment_id": segment_map[str(span["segment"])],
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


@torch.no_grad()
def _layer_hiddens(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    record: dict[str, Any],
    mode: SegmentAttentionMode,
    device: torch.device,
) -> torch.Tensor:
    input_ids = build_inference_input_ids(
        prompt=str(record["prompt"]),
        tokenizer=tokenizer,
        device=device,
        numeric_tokenization="digit_safe",
    )
    segment_ids, context_access = _segment_tensors_for_inference(
        tokenizer=tokenizer,
        record=record,
        device=device,
    )
    context = input_ids[:, -model.config.max_sequence_length :]
    segment_ids = segment_ids[:, -model.config.max_sequence_length :]
    context_access = context_access[:, -model.config.max_sequence_length :]
    allow_mask = build_segment_attention_allow_mask(
        segment_ids,
        mode=mode,
        context_access_mask=context_access,
    )
    x = model.embed_tokens_and_positions(context)
    result = model.forward_embeddings(
        x,
        attention_allow_mask=allow_mask,
        return_layer_hiddens=True,
    )
    return result["layer_hiddens"][:, 0].detach().cpu()


def _role_positions(
    tokenizer: ByteLevelBpeTokenizer,
    record: dict[str, Any],
) -> dict[str, int]:
    prompt = str(record["prompt"]).strip()
    active_start = int(record.get("metadata", {}).get("active_prompt_start_char", 0))
    active_prompt = prompt[active_start:]
    op_start = active_start
    first_number_start = active_start + active_prompt.index(" ") + 1
    first_number_end = first_number_start + 2
    second_number_start = active_start + active_prompt.rindex(" ") + 1
    second_number_end = second_number_start + 2
    text = format_inference_prompt(prompt)
    encoded = tokenizer.encode_with_offsets(text, numeric_tokenization="digit_safe")
    prompt_start = len("<|prompt|>\n")
    roles = {
        "op": (prompt_start + op_start, prompt_start + op_start + 3),
        "operand_a": (
            prompt_start + first_number_start,
            prompt_start + first_number_end,
        ),
        "operand_b": (
            prompt_start + second_number_start,
            prompt_start + second_number_end,
        ),
    }
    positions = {}
    for role, (start, end) in roles.items():
        matches = [
            token_index + 1
            for token_index, (token_start, token_end) in enumerate(encoded.offsets)
            if min(end, token_end) - max(start, token_start) > 0
        ]
        if not matches:
            raise ValueError(f"No token match for role {role}")
        positions[role] = matches[0]
    positions["answer_start"] = len(encoded.ids)
    return positions


def _probe_record_pairs() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    clean_path = DATASET_DIR / "eval" / "clean.jsonl"
    distracted_path = DATASET_DIR / "eval" / "hard_negative" / "len_4.jsonl"
    clean_by_key = {
        record.get("metadata", {}).get("case_key"): record
        for record in _iter_jsonl(clean_path)
    }
    pairs = []
    for record in _iter_jsonl(distracted_path):
        key = record.get("metadata", {}).get("case_key")
        if key in clean_by_key:
            pairs.append((clean_by_key[key], record))
        if len(pairs) >= 80:
            break
    return pairs


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


def _collect_phase3() -> dict[str, Any]:
    result = {}
    for mode in ("flat_causal", "old_key_oracle", "query_isolated", "workspace"):
        result[mode] = {
            "clean": _read_summary_payload(RUNS_DIR / "phase3" / mode / "clean")
        }
        for family in PHASE3_FAMILIES:
            result[mode][family] = {
                str(length): _read_summary_payload(
                    RUNS_DIR / "phase3" / mode / family / f"len_{length}"
                )
                for length in _family_lengths(family)
            }
    return result


def _collect_phase5() -> dict[str, Any]:
    result = {}
    for mode in ("query_isolated", "workspace"):
        base = RUNS_DIR / "phase5_training" / mode / "benchmark"
        if not base.exists():
            result[mode] = {"status": "missing"}
            continue
        payload = {"status": "complete", "clean": _read_summary_payload(base / "clean")}
        for family in PHASE3_FAMILIES:
            payload[family] = {
                str(length): _read_summary_payload(base / family / f"len_{length}")
                for length in _family_lengths(family)
            }
        for name in ("relevant_context", "variable_binding", "add_sub_composition"):
            payload[name] = _read_summary_payload(base / name)
        result[mode] = payload
    return result


def _collect_selective_context() -> dict[str, Any]:
    result = {}
    for mode, payload in _collect_phase5().items():
        if payload.get("status") == "complete":
            result[mode] = {
                "relevant_context": payload.get(
                    "relevant_context", {"status": "missing"}
                ),
                "variable_binding": payload.get(
                    "variable_binding", {"status": "missing"}
                ),
                "add_sub_composition": payload.get(
                    "add_sub_composition", {"status": "missing"}
                ),
            }
    return result


def _oracle_segment_gate(analysis: dict[str, Any]) -> bool:
    phase3 = analysis.get("phase3", {})
    if not phase3:
        return False
    clean = phase3.get("query_isolated", {}).get("clean", {}).get("final_nem", 0.0)
    values = []
    for mode in ("query_isolated", "workspace"):
        payload = phase3.get(mode, {})
        for family in PHASE3_FAMILIES:
            max_len = 8 if family in {"previous_arithmetic", "hard_negative"} else 16
            for length, result in payload.get(family, {}).items():
                if int(length) <= max_len:
                    values.append(float(result.get("final_nem", 0.0)))
    return clean >= 0.98 and bool(values) and min(values) >= 0.95


def _training_gate(analysis: dict[str, Any]) -> bool:
    phase5 = analysis.get("phase5_training", {})
    for payload in phase5.values():
        if payload.get("status") != "complete":
            continue
        clean = payload.get("clean", {}).get("final_nem", 0.0)
        robustness = _family_min(payload, PHASE3_FAMILIES, max_length=16)
        if clean >= 0.98 and robustness >= 0.95:
            return True
    return False


def _best_trained_mode(analysis: dict[str, Any]) -> SegmentAttentionMode | None:
    best_name = None
    best_score = -1.0
    for name, payload in analysis.get("phase5_training", {}).items():
        if payload.get("status") != "complete":
            continue
        score = min(
            payload.get("clean", {}).get("final_nem", 0.0),
            _family_min(payload, PHASE3_FAMILIES, max_length=16),
        )
        if score > best_score:
            best_name = name
            best_score = score
    return best_name


def _family_min(
    payload: dict[str, Any], families: tuple[str, ...], *, max_length: int
) -> float:
    values = []
    for family in families:
        for length, result in payload.get(family, {}).items():
            if int(length) <= max_length:
                values.append(result.get("final_nem", 0.0))
    return min(values) if values else 0.0


def _summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("status") == "missing":
        return summary
    overall = summary.get("overall", summary)
    return {
        "status": "complete",
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "full_nem": float(overall.get("normalized_exact_match", 0.0)),
        "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
        "empty_prediction_rate": float(overall.get("empty_prediction_rate", 0.0)),
        "avg_tokens_generated": float(overall.get("avg_tokens_generated", 0.0)),
        "summary": summary,
    }


def _read_summary_payload(path: Path) -> dict[str, Any]:
    summary_path = path / "summary.json"
    if not summary_path.exists():
        return {"status": "missing", "final_nem": 0.0}
    return _summary_payload(_read_json(summary_path))


def _dataset_table(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    if manifest.get("status") == "missing":
        return "missing"
    rows = ["| item | value |", "|---|---:|"]
    rows.append(f"| train mixed count | {manifest.get('train_mixed_count', 0)} |")
    rows.append(f"| clean eval count | {manifest.get('clean_eval_count', 0)} |")
    rows.append(
        f"| prompt intersections | {manifest.get('prompt_intersections', {})} |"
    )
    rows.append(f"| segment schema | {manifest.get('segment_schema', 'missing')} |")
    return "\n".join(rows)


def _phase3_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| family | length | flat | old oracle | query-isolated | workspace |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    phase3 = analysis.get("phase3", {})
    for family in PHASE3_FAMILIES:
        for length in _family_lengths(family):
            rows.append(
                f"| {family} | {length} | "
                f"{_score(phase3, 'flat_causal', family, length):.4f} | "
                f"{_score(phase3, 'old_key_oracle', family, length):.4f} | "
                f"{_score(phase3, 'query_isolated', family, length):.4f} | "
                f"{_score(phase3, 'workspace', family, length):.4f} |"
            )
    return "\n".join(rows)


def _robustness_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| mode | clean | min easy<=16 | natural<=16 | arithmetic<=8 | hard<=8 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    phase3 = analysis.get("phase3", {})
    for mode, payload in phase3.items():
        rows.append(
            f"| {mode} | {payload.get('clean', {}).get('final_nem', 0.0):.4f} | "
            f"{_family_min(payload, ('neutral', 'random_vocab'), max_length=16):.4f} | "
            f"{_family_min(payload, ('natural_phrase',), max_length=16):.4f} | "
            f"{_family_min(payload, ('previous_arithmetic',), max_length=8):.4f} | "
            f"{_family_min(payload, ('hard_negative',), max_length=8):.4f} |"
        )
    return "\n".join(rows)


def _contamination_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("contamination_probe", {})
    if payload.get("status") == "missing":
        return "missing"
    rows = ["| mode | role | layer | cosine | count |", "|---|---|---:|---:|---:|"]
    for key, value in payload.items():
        mode, role, layer = key.split(".")
        rows.append(
            f"| {mode} | {role} | {layer.replace('layer', '')} | "
            f"{value['cosine']:.4f} | {value['count']} |"
        )
    return "\n".join(rows)


def _clean_table(analysis: dict[str, Any]) -> str:
    rows = ["| source | mode | clean final NEM |", "|---|---|---:|"]
    for mode, payload in analysis.get("phase3", {}).items():
        rows.append(
            f"| phase3 | {mode} | {payload.get('clean', {}).get('final_nem', 0.0):.4f} |"
        )
    for mode, payload in analysis.get("phase5_training", {}).items():
        if payload.get("status") == "complete":
            rows.append(
                f"| phase5 | {mode} | {payload.get('clean', {}).get('final_nem', 0.0):.4f} |"
            )
    return "\n".join(rows)


def _selective_context_table(analysis: dict[str, Any]) -> str:
    rows = ["| mode | relevant context | status |", "|---|---:|---|"]
    for mode, payload in analysis.get("selective_context", {}).items():
        rel = payload.get("relevant_context", {})
        rows.append(
            f"| {mode} | {rel.get('final_nem', 0.0):.4f} | {rel.get('status', 'missing')} |"
        )
    return (
        "\n".join(rows)
        if len(rows) > 2
        else "skipped: oracle/training gate did not pass"
    )


def _learned_selection_table(analysis: dict[str, Any]) -> str:
    if not analysis.get("gates", {}).get("oracle_segments"):
        return "skipped: oracle segment routing did not pass, so learned chunk selection was not run"
    if not analysis.get("gates", {}).get("training"):
        return "skipped: segment training did not pass robustness gate"
    return "not implemented in this run: task requires it only after oracle and robustness gates pass"


def _variable_binding_table(analysis: dict[str, Any]) -> str:
    rows = ["| mode | variable binding final NEM | status |", "|---|---:|---|"]
    for mode, payload in analysis.get("selective_context", {}).items():
        binding = payload.get("variable_binding", {})
        rows.append(
            f"| {mode} | {binding.get('final_nem', 0.0):.4f} | {binding.get('status', 'missing')} |"
        )
    return (
        "\n".join(rows)
        if len(rows) > 2
        else "skipped: relevant-context gate did not pass"
    )


def _composition_table(analysis: dict[str, Any]) -> str:
    rows = ["| mode | ADD_SUB final NEM | status |", "|---|---:|---|"]
    for mode, payload in analysis.get("selective_context", {}).items():
        comp = payload.get("add_sub_composition", {})
        rows.append(
            f"| {mode} | {comp.get('final_nem', 0.0):.4f} | {comp.get('status', 'missing')} |"
        )
    return (
        "\n".join(rows)
        if len(rows) > 2
        else "skipped: relevant-context gate did not pass"
    )


def _score(phase3: dict[str, Any], mode: str, family: str, length: int) -> float:
    return float(
        phase3.get(mode, {}).get(family, {}).get(str(length), {}).get("final_nem", 0.0)
    )


def _decision(analysis: dict[str, Any]) -> str:
    if not analysis.get("gates", {}).get("oracle_segments"):
        return (
            "OUTCOME D: complete query/workspace isolation did not restore the "
            "required distractor robustness. Stop before learned routing and "
            "investigate representation/generation rather than adding another "
            "selector."
        )
    if not analysis.get("gates", {}).get("training"):
        return (
            "OUTCOME A partial: oracle segment routing works, but trained segment "
            "models did not pass the clean/robustness gate."
        )
    return (
        "OUTCOME B candidate: segment-aware attention should be retained and "
        "selective context/working-memory composition can be tested next."
    )


def _write_manifest() -> None:
    train_path = DATASET_DIR / "train" / "mixed_segmented.jsonl"
    clean_path = DATASET_DIR / "eval" / "clean.jsonl"
    manifest = {
        "kind": "m18_segmented_context_workspace",
        "seed": SEED,
        "segment_schema": "m18.v1",
        "segments": ["context", "query", "workspace", "answer", "control"],
        "m175_source": str(M175_DATASET_DIR),
        "relative_baseline_checkpoint": str(M174_RELATIVE_CHECKPOINT),
        "families": list(PHASE3_FAMILIES),
        "lengths": list(LENGTHS),
        "hard_lengths": list(HARD_LENGTHS),
        "train_mixed_count": len(_iter_jsonl(train_path)),
        "clean_eval_count": len(_iter_jsonl(clean_path)),
        "prompt_intersections": {
            "train_mixed_vs_clean": len(_prompts(train_path) & _prompts(clean_path)),
        },
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _family_lengths(family: str) -> tuple[int, ...]:
    return (
        HARD_LENGTHS if family in {"previous_arithmetic", "hard_negative"} else LENGTHS
    )


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


def _required_token_id(tokenizer: ByteLevelBpeTokenizer, token: str) -> int:
    token_id = tokenizer.token_to_id(token)
    if token_id is None:
        raise ValueError(f"Tokenizer missing special token: {token}")
    return token_id


def _require_checkpoint() -> None:
    if not M174_RELATIVE_CHECKPOINT.exists():
        raise FileNotFoundError(f"Missing checkpoint: {M174_RELATIVE_CHECKPOINT}")


def _device_name(analysis: dict[str, Any]) -> str:
    for mode in analysis.get("phase3", {}).values():
        summary = mode.get("clean", {}).get("summary", {})
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
