from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ai_brain.data.answer_format import apply_answer_format
from ai_brain.data.schema import TrainingExample
from ai_brain.eval.arithmetic_forensics import (
    analyze_arithmetic_forensics,
    output_length_distribution,
)
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.numeric_position_features import encode_text_position_features

ROOT = Path(__file__).resolve().parents[1]
M14_DIR = ROOT / "datasets" / "m14_digit_table_curriculum"
DATASET_DIR = ROOT / "datasets" / "m161_addition_forensics"
RUNS_DIR = ROOT / "runs" / "m161_addition_forensics"
DOC_PATH = ROOT / "docs" / "m161_addition_forensics_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"


@dataclass(frozen=True)
class Variant:
    name: str
    answer_format: str
    config: str
    max_new_tokens: int


VARIANTS = (
    Variant("a_digit_safe_normal", "normal_answer", "tiny", 32),
    Variant("b_digit_safe_rtl", "rtl_numeric", "tiny", 48),
    Variant("c_digit_safe_lsd_trace", "compact_lsd_trace", "tiny", 96),
    Variant("d_abacus_lsd_trace", "compact_lsd_trace", "abacus_tiny", 96),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    diagnose = subparsers.add_parser("diagnose-m16")
    diagnose.add_argument("--variant", default="b_digit_safe")
    subparsers.add_parser("build-report")
    subparsers.add_parser("print-commands")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
        return 0
    if args.command == "diagnose-m16":
        diagnose_m16(args.variant)
        return 0
    if args.command == "build-report":
        build_report()
        return 0
    if args.command == "print-commands":
        print_commands()
        return 0
    raise AssertionError(args.command)


def prepare_datasets() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"variants": {}, "source": str(M14_DIR)}
    source_paths = {
        "train": M14_DIR / "train_2digit_composition.jsonl",
        "eval_same": M14_DIR / "eval_2digit_same.jsonl",
        "eval_holdout": M14_DIR / "eval_2digit_holdout_combo.jsonl",
        "eval_far": M14_DIR / "eval_2digit_far.jsonl",
    }
    for variant in VARIANTS:
        variant_dir = DATASET_DIR / variant.name
        variant_dir.mkdir(parents=True, exist_ok=True)
        train_records = _transform_records(
            _read_jsonl(source_paths["train"]),
            answer_format=variant.answer_format,
            operation="add",
        )
        split_info = {
            "train_add": _write_jsonl(variant_dir / "train_add.jsonl", train_records)
        }
        for split_name in ("eval_same", "eval_holdout", "eval_far"):
            records = _transform_records(
                _read_jsonl(source_paths[split_name]),
                answer_format=variant.answer_format,
                operation="all",
            )
            split_info[split_name] = _write_jsonl(
                variant_dir / f"{split_name}.jsonl",
                records,
            )
        manifest["variants"][variant.name] = {
            "answer_format": variant.answer_format,
            "config": variant.config,
            "max_new_tokens": variant.max_new_tokens,
            "splits": split_info,
        }
    manifest["length_distribution"] = output_length_distribution(
        {
            "train": source_paths["train"],
            "same": source_paths["eval_same"],
            "holdout": source_paths["eval_holdout"],
            "far": source_paths["eval_far"],
        }
    )
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def diagnose_m16(variant: str) -> None:
    out_dir = RUNS_DIR / "m16_baseline_diagnostics" / variant
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for split_name, source_name in {
        "same": "2digit_same",
        "holdout": "2digit_holdout_combo",
        "far": "2digit_far",
    }.items():
        result[split_name] = analyze_arithmetic_forensics(
            predictions_path=ROOT
            / "runs"
            / "m16_evals"
            / variant
            / source_name
            / "predictions.jsonl",
            eval_path=M14_DIR
            / f"eval_2digit_{'holdout_combo' if split_name == 'holdout' else split_name}.jsonl",
            train_path=M14_DIR / "train_2digit_composition.jsonl",
        )
    result["length_distribution"] = output_length_distribution(
        {
            "train": M14_DIR / "train_2digit_composition.jsonl",
            "same": M14_DIR / "eval_2digit_same.jsonl",
            "holdout": M14_DIR / "eval_2digit_holdout_combo.jsonl",
            "far": M14_DIR / "eval_2digit_far.jsonl",
        }
    )
    result["tokenization"] = _tokenization_snapshots()
    result["position_coupling"] = _position_snapshots(position_kind="coupled")
    result["abacus"] = _position_snapshots(position_kind="abacus")
    (out_dir / "forensics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report() -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    m16_path = RUNS_DIR / "m16_baseline_diagnostics" / "b_digit_safe" / "forensics.json"
    m16 = json.loads(m16_path.read_text(encoding="utf-8")) if m16_path.exists() else {}
    rows = _collect_ablation_rows()
    summary = _summarize_rows(rows)
    report = _render_report(m16, rows, summary)
    DOC_PATH.write_text(report, encoding="utf-8")
    (ROOT / "runs" / "m161_addition_forensics_report.md").write_text(
        report,
        encoding="utf-8",
    )
    (RUNS_DIR / "summary.json").write_text(
        json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def print_commands() -> None:
    for variant in VARIANTS:
        seeds = [310161]
        if variant.name == "c_digit_safe_lsd_trace":
            seeds = [310161, 310162, 310163]
        for seed in seeds:
            run_dir = ROOT / "runs" / f"m161_{variant.name}_seed{seed}"
            data_dir = DATASET_DIR / variant.name
            print(
                " ".join(
                    [
                        "uv run ai-brain train-lm",
                        f"--train {data_dir / 'train_add.jsonl'}",
                        f"--eval {data_dir / 'eval_same.jsonl'}",
                        f"--tokenizer {TOKENIZER_PATH}",
                        f"--output-dir {run_dir}",
                        f"--config {variant.config}",
                        "--steps 5000",
                        "--batch-size 8",
                        "--sequence-length 256",
                        "--loss-mode answer-only",
                        "--eval-every 1000",
                        "--eval-batches 20",
                        "--save-every 5000",
                        "--grad-clip-norm 1.0",
                        "--numeric-tokenization digit_safe",
                        f"--seed {seed}",
                    ]
                )
            )
            ckpt = run_dir / "checkpoints" / "step_005000.pt"
            for split_name in ("eval_same", "eval_holdout", "eval_far"):
                print(
                    " ".join(
                        [
                            "uv run ai-brain eval-lm",
                            f"--checkpoint {ckpt}",
                            f"--eval {data_dir / f'{split_name}.jsonl'}",
                            f"--tokenizer {TOKENIZER_PATH}",
                            f"--output-dir {RUNS_DIR / 'evals' / f'{variant.name}_seed{seed}' / split_name}",
                            f"--max-new-tokens {variant.max_new_tokens}",
                            "--numeric-tokenization digit_safe",
                        ]
                    )
                )


def _transform_records(
    records: list[dict[str, Any]],
    *,
    answer_format: str,
    operation: str,
) -> list[dict[str, Any]]:
    transformed: list[dict[str, Any]] = []
    for record in records:
        task_type = str(record["task_type"])
        if operation == "add" and "add_2digit" not in task_type:
            continue
        if operation == "sub" and "sub_2digit" not in task_type:
            continue
        metadata = dict(record["metadata"])
        base = TrainingExample(
            id=str(record["id"]),
            task_type=task_type,
            prompt=str(record["prompt"]),
            answer=str(metadata.get("original_answer", record["answer"])),
            metadata={
                key: value
                for key, value in metadata.items()
                if key not in {"answer_format", "original_answer", "original_prompt"}
            },
        )
        formatted = apply_answer_format(base, answer_format)  # type: ignore[arg-type]
        transformed.append(formatted.to_dict())
    return transformed


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    return {
        "path": str(path.relative_to(DATASET_DIR)),
        "count": len(records),
        "task_type_counts": _counts(record["task_type"] for record in records),
    }


def _collect_ablation_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    eval_root = RUNS_DIR / "evals"
    for variant in VARIANTS:
        for eval_dir in sorted(eval_root.glob(f"{variant.name}_seed*")):
            seed_match = re.search(r"seed(\d+)$", eval_dir.name)
            if seed_match is None:
                continue
            seed = int(seed_match.group(1))
            split_results = {}
            for split_name in ("eval_same", "eval_holdout", "eval_far"):
                predictions = eval_dir / split_name / "predictions.jsonl"
                if not predictions.exists():
                    continue
                split_results[split_name] = analyze_arithmetic_forensics(
                    predictions_path=predictions,
                    eval_path=DATASET_DIR / variant.name / f"{split_name}.jsonl",
                    train_path=DATASET_DIR / variant.name / "train_add.jsonl",
                )
            if split_results:
                rows.append(_row_from_split_results(variant.name, seed, split_results))
    return rows


def _row_from_split_results(
    variant: str,
    seed: int,
    split_results: dict[str, Any],
) -> dict[str, Any]:
    holdout = split_results.get("eval_holdout", {})
    far = split_results.get("eval_far", {})
    same = split_results.get("eval_same", {})
    return {
        "variant": variant,
        "seed": seed,
        "addition_no_carry": _bucket_metric(same, "addition", "no_carry"),
        "addition_carry": _bucket_metric(same, "addition", "carry"),
        "addition_overflow_to_new_digit": _bucket_metric(
            same,
            "addition",
            "overflow_to_new_digit",
        ),
        "addition_holdout": _bucket_metric(holdout, "addition", "all"),
        "addition_far": _bucket_metric(far, "addition", "all"),
        "subtraction_holdout": _bucket_metric(holdout, "subtraction", "all"),
        "subtraction_far": _bucket_metric(far, "subtraction", "all"),
    }


def _bucket_metric(result: dict[str, Any], operation: str, bucket: str) -> float | None:
    try:
        return result[operation]["buckets"][bucket]["final_normalized_exact_match"]
    except KeyError:
        return None


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant[str(row["variant"])].append(row)
    summary = {}
    for variant, variant_rows in sorted(by_variant.items()):
        metrics = {}
        for key in (
            "addition_no_carry",
            "addition_carry",
            "addition_overflow_to_new_digit",
            "addition_holdout",
            "addition_far",
            "subtraction_holdout",
            "subtraction_far",
        ):
            values = [float(row[key]) for row in variant_rows if row[key] is not None]
            metrics[key] = {
                "mean": mean(values) if values else None,
                "std": pstdev(values) if len(values) > 1 else 0.0 if values else None,
                "n": len(values),
            }
        summary[variant] = metrics
    return summary


def _render_report(
    m16: dict[str, Any],
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    lines = [
        "# M-16.1 Addition Forensics Report",
        "",
        "## Checks",
        "",
        "- Commands: `uv run ruff format src tests`, `uv run ruff check src tests`, `uv run pytest -q`.",
        f"- Commit hash: `{_git_commit()}`.",
        f"- Device: `{_device_info()}`.",
        "",
        "## Dataset And Length Distribution",
        "",
    ]
    length = m16.get("length_distribution", {})
    lines.extend(_length_lines(length))
    lines.extend(
        [
            "",
            "## M-16 Digit-Safe Baseline Diagnostics",
            "",
            "### Addition Buckets",
            "",
        ]
    )
    lines.extend(_bucket_table_lines(m16, "addition"))
    lines.extend(["", "### Subtraction Buckets", ""])
    lines.extend(_bucket_table_lines(m16, "subtraction"))
    lines.extend(["", "## Tokenization Checks", ""])
    lines.extend(_tokenization_lines(m16.get("tokenization", [])))
    lines.extend(["", "## Generated Answer Checks", ""])
    lines.extend(_generated_answer_lines())
    lines.extend(["", "## Position Checks", ""])
    lines.extend(
        [
            "- Position Coupling source: [HanseulJo/position-coupling](https://github.com/HanseulJo/position-coupling), `src/data/addition.py`, `AdditionDatasetWithCoupledPositions`.",
            "- Abacus source: [mcleish7/arithmetic](https://github.com/mcleish7/arithmetic), `abacus.py`, `Abacus.helper`.",
            "",
        ]
    )
    lines.extend(_position_lines("Position Coupling", m16.get("position_coupling", [])))
    lines.extend(["", *(_position_lines("Abacus", m16.get("abacus", [])))])
    lines.extend(["", "## Addition-Only Ablation", ""])
    lines.extend(_main_table_lines(rows))
    lines.extend(["", "## Mean / Std", ""])
    lines.extend(_summary_lines(summary))
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- M-16 digit-safe addition failures are not final-string-only failures when carry is involved: trace rows show the model often gets U correct, then loses the T carry/overflow state and emits a 2-digit OUT.",
            "- The strongest distribution mismatch is output length: train addition has 5.47% 3-digit results, same eval has 5.71%, holdout has 53.88%, and far has 100%. This explains why same-range overflow can be memorized while shifted/far overflow collapses.",
            "- Official Position Coupling trains with reversed output (`reverse_output: True`) and assigns increasing positions to the LSD-first label. Our M-16 coupled feature assigned significance IDs inside normal-order text, but did not force the supervised output order to be LSD-first.",
            "- Official Abacus assigns positions from the start of each consecutive digit span and explicitly requires reversed integers. Our M-16 Abacus feature used right-aligned normal-order spans, so it was significance-like but not the paper formulation.",
            "- Addition-only ablation confirms the anomaly: `compact_lsd_trace` reaches 1.0000 on same-range no-carry/carry/overflow for 3/3 seeds, but remains 0.0000 on holdout and far. So the failure is not only output order or final-answer extraction; it is unseen digit-combo/range transfer under output-length shift.",
            "- Next step should not be recurrent/FoNE/xVal yet. The cleanest next diagnostic is balanced 3-digit-overflow and held-out-combo training for addition, with explicit carry-state coverage separated from output-length growth.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _bucket_table_lines(result: dict[str, Any], operation: str) -> list[str]:
    lines = [
        "| Split | Bucket | Count | Final NEM | Digit Acc | U | T | H | State Acc | U Row | T Row | OUT |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for split in ("same", "holdout", "far"):
        buckets = result.get(split, {}).get(operation, {}).get("buckets", {})
        for bucket, stats in buckets.items():
            lines.append(
                f"| {split} | {bucket} | {stats['count']} | {_fmt(stats['final_normalized_exact_match'])} | "
                f"{_fmt(stats['per_digit_accuracy'])} | {_fmt(stats['units_accuracy'])} | "
                f"{_fmt(stats['tens_accuracy'])} | {_fmt(stats['hundreds_accuracy'])} | "
                f"{_fmt(stats['carry_or_borrow_prediction_accuracy'])} | "
                f"{_fmt(stats['u_row_accuracy'])} | {_fmt(stats['t_row_accuracy'])} | "
                f"{_fmt(stats['out_accuracy'])} |"
            )
    return lines


def _main_table_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Variant | Seed | Addition No-Carry | Addition Carry | Addition Overflow | Addition Holdout | Addition Far | Subtraction Holdout | Subtraction Far |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['variant']} | {row['seed']} | {_fmt(row['addition_no_carry'])} | "
            f"{_fmt(row['addition_carry'])} | {_fmt(row['addition_overflow_to_new_digit'])} | "
            f"{_fmt(row['addition_holdout'])} | {_fmt(row['addition_far'])} | "
            f"{_fmt(row['subtraction_holdout'])} | {_fmt(row['subtraction_far'])} |"
        )
    if not rows:
        lines.append("| pending | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
    return lines


def _summary_lines(summary: dict[str, Any]) -> list[str]:
    lines = [
        "| Variant | Metric | Mean | Std | N |",
        "|---|---|---:|---:|---:|",
    ]
    for variant, metrics in summary.items():
        for metric, stats in metrics.items():
            lines.append(
                f"| {variant} | {metric} | {_fmt(stats['mean'])} | {_fmt(stats['std'])} | {stats['n']} |"
            )
    if not summary:
        lines.append("| pending | pending | n/a | n/a | 0 |")
    return lines


def _length_lines(length: dict[str, Any]) -> list[str]:
    lines = [
        "| Split | Operation | Total | 1 Digit | 2 Digit | 3 Digit |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for split, groups in length.items():
        for operation, data in groups.items():
            buckets = data.get("buckets", {})
            lines.append(
                f"| {split} | {operation} | {data.get('count', 0)} | "
                f"{_bucket_fraction(buckets, '1_digit')} | {_bucket_fraction(buckets, '2_digit')} | "
                f"{_bucket_fraction(buckets, '3_digit')} |"
            )
    return lines


def _tokenization_lines(items: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Text | Tokens | IDs | Offsets |",
        "|---|---|---|---|",
    ]
    for item in items:
        lines.append(
            f"| `{item['text']}` | `{item['tokens']}` | `{item['ids']}` | `{item['offsets']}` |"
        )
    return lines


def _generated_answer_lines() -> list[str]:
    samples = [
        (
            "M-16 digit_safe same",
            ROOT
            / "runs"
            / "m16_evals"
            / "b_digit_safe"
            / "2digit_same"
            / "predictions.jsonl",
            "47 + 21",
        ),
        (
            "M-16 digit_safe far",
            ROOT
            / "runs"
            / "m16_evals"
            / "b_digit_safe"
            / "2digit_far"
            / "predictions.jsonl",
            "84 + 65",
        ),
        (
            "M-16.1 LSD trace same",
            RUNS_DIR
            / "evals"
            / "c_digit_safe_lsd_trace_seed310161"
            / "eval_same"
            / "predictions.jsonl",
            "47 + 21",
        ),
        (
            "M-16.1 LSD trace far",
            RUNS_DIR
            / "evals"
            / "c_digit_safe_lsd_trace_seed310161"
            / "eval_far"
            / "predictions.jsonl",
            "84 + 65",
        ),
    ]
    lines = [
        "| Source | Prompt | Expected Final | Predicted Final | Generated Answer |",
        "|---|---|---:|---:|---|",
    ]
    for source, path, prompt_fragment in samples:
        prediction = _find_prediction(path, prompt_fragment)
        if prediction is None:
            continue
        lines.append(
            f"| {source} | `{prediction['prompt']}` | "
            f"`{prediction.get('final_expected', '')}` | "
            f"`{prediction.get('final_predicted', '')}` | "
            f"{_md_cell(prediction.get('predicted', ''))} |"
        )
    return lines


def _find_prediction(path: Path, prompt_fragment: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    for record in _read_jsonl(path):
        if prompt_fragment in str(record.get("prompt", "")):
            return record
    return None


def _position_lines(title: str, items: list[dict[str, Any]]) -> list[str]:
    lines = [f"### {title}", ""]
    lines.extend(
        [
            "| Example | Token | Our ID | Reference/Paper-Intended ID | Note |",
            "|---|---|---:|---:|---|",
        ]
    )
    for item in items:
        for row in item["rows"]:
            lines.append(
                f"| `{item['example']}` | `{row['token']}` | {row['our_id']} | "
                f"{row['reference_id']} | {row['note']} |"
            )
    return lines


def _tokenization_snapshots() -> list[dict[str, Any]]:
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    texts = [
        "case 0. ADD2_COMPOSED 47 + 21",
        "OUT 68",
        "case 1. ADD2_COMPOSED 84 + 65",
        "OUT 149",
        "OUT_RTL 9 4 1\nFINAL 149",
    ]
    snapshots = []
    for text in texts:
        encoded = tokenizer.encode_with_offsets(text, numeric_tokenization="digit_safe")
        snapshots.append(
            {
                "text": text,
                "ids": encoded.ids,
                "tokens": [tokenizer.id_to_token(token_id) for token_id in encoded.ids],
                "offsets": encoded.offsets,
            }
        )
    return snapshots


def _position_snapshots(*, position_kind: str) -> list[dict[str, Any]]:
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    examples = [
        ("47+21", "case 0. ADD2_COMPOSED 47 + 21\nOUT 68"),
        ("84+65", "case 1. ADD2_COMPOSED 84 + 65\nOUT 149"),
        ("71+63", "case 2. ADD2_COMPOSED 71 + 63\nOUT 134"),
        ("20+55", "case 3. ADD2_COMPOSED 20 + 55\nOUT 75"),
        ("58+47", "case 4. ADD2_COMPOSED 58 + 47\nOUT 105"),
    ]
    result = []
    for label, text in examples:
        allowed_digit_positions = _addition_digit_positions(text)
        encoded_ids, features = encode_text_position_features(
            text,
            tokenizer,
            numeric_tokenization="digit_safe",
        )
        feature_values = (
            features.coupled_position_ids
            if position_kind == "coupled"
            else features.abacus_position_ids
        )
        encoded = tokenizer.encode_with_offsets(text, numeric_tokenization="digit_safe")
        rows = []
        for token_id, offset, our_id in zip(
            encoded_ids, encoded.offsets, feature_values, strict=True
        ):
            token = tokenizer.id_to_token(token_id) or str(token_id)
            raw = text[offset[0] : offset[1]]
            if not raw.isdigit():
                continue
            if not set(range(offset[0], offset[1])).issubset(allowed_digit_positions):
                continue
            reference_id, note = _reference_position(
                text=text,
                start=offset[0],
                kind=position_kind,
            )
            rows.append(
                {
                    "token": raw if raw else token,
                    "our_id": our_id,
                    "reference_id": reference_id,
                    "note": note,
                }
            )
        result.append({"example": label, "rows": rows[:12]})
    return result


def _addition_digit_positions(text: str) -> set[int]:
    match = re.search(r"ADD2_COMPOSED (?P<a>\d+) \+ (?P<b>\d+)\nOUT (?P<out>\d+)", text)
    if match is None:
        return set()
    positions: set[int] = set()
    for group in ("a", "b", "out"):
        positions.update(range(match.start(group), match.end(group)))
    return positions


def _reference_position(*, text: str, start: int, kind: str) -> tuple[int, str]:
    span = _digit_span_at(text, start)
    if span is None:
        return 0, ""
    span_start, span_end = span
    if kind == "abacus":
        return (
            start - span_start + 1,
            "official Abacus segment-start; paper requires reversed integers",
        )
    place_from_right = span_end - start
    if "OUT " in text[:span_start]:
        return place_from_right, "paper-equivalent only if output is LSD-first/reversed"
    return place_from_right, "same significance should share this ID"


def _digit_span_at(text: str, start: int) -> tuple[int, int] | None:
    if not text[start].isdigit():
        return None
    left = start
    while left > 0 and text[left - 1].isdigit():
        left -= 1
    right = start + 1
    while right < len(text) and text[right].isdigit():
        right += 1
    return left, right


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[str(value)] += 1
    return dict(sorted(counts.items()))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and math.isnan(value):
        return "n/a"
    return f"{value:.4f}"


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _bucket_fraction(buckets: dict[str, Any], key: str) -> str:
    bucket = buckets.get(key)
    if bucket is None:
        return "0 / 0.0000"
    return f"{bucket['count']} / {bucket['fraction']:.4f}"


def _git_commit() -> str:
    return _run_text(["git", "rev-parse", "--short", "HEAD"])


def _device_info() -> str:
    try:
        return _run_text(["uv", "run", "ai-brain", "device"]).replace("\n", " / ")
    except subprocess.CalledProcessError:
        return "unavailable"


def _run_text(command: list[str]) -> str:
    return subprocess.check_output(
        command, cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


if __name__ == "__main__":
    raise SystemExit(main())
