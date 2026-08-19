from __future__ import annotations

import argparse
import itertools
import json
import re
import socket
import subprocess
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.metrics import summarize_predictions, task_group
from ai_brain.eval.normalize import (
    extract_generated_answer,
    is_false_answer,
    normalize_answer,
)
from ai_brain.eval.runner import eval_lm
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import (
    BOS_TOKEN,
    END_TOKEN,
    EOS_TOKEN,
    PAD_TOKEN,
)
from ai_brain.language.tokenizer.text_format import format_inference_prompt
from ai_brain.training.config import TrainConfig
from ai_brain.training.lm_dataset import IGNORE_INDEX, encode_lm_example
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m192b_clean_cardinality"
RUNS_DIR = ROOT / "runs" / "m192b_clean_cardinality"
DOC_PATH = ROOT / "docs" / "m192b_clean_cardinality_sanity_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m192b_clean_cardinality_sanity_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 192200
MODEL_CONFIG = "arithmetic_3m"
POSITION_ENCODING = "relative"
NUMERIC_TOKENIZATION = "digit_safe"
BATCH_SIZE = 8
SEQUENCE_LENGTH = 256
ITERATIVE_SEQUENCE_LENGTH = 512
LOSS_MODE = "answer-only"
LEARNING_RATE = 3e-4
GRAD_CLIP_NORM = 1.0

TRAIN_COUNTS = tuple(range(11))
SUCCESSOR_COUNTS = tuple(range(10))
LENGTH_OOD_COUNTS = tuple(range(11, 21))
TRAIN_OBJECTS = ("x", "a", "k", "m", "n")
HELDOUT_OBJECTS = ("q", "z", "w", "y")
ALL_OBJECTS = TRAIN_OBJECTS + HELDOUT_OBJECTS
FORBIDDEN_PROMPT_PATTERNS = (
    r"\bCASE\b",
    r"\bID\b",
    r"\bEXAMPLE\b",
    r"\bTRAIN\b",
    r"\bEVAL\b",
    r"\bSPLIT\b",
    r"\bSEED\b",
)

STEPS = {
    "successor_symbol": 3000,
    "local_successor": 4000,
    "global_count": 6000,
    "same_count": 6000,
    "iterative_count": 9000,
}


@dataclass(frozen=True)
class TrainSpec:
    name: str
    train_path: Path
    eval_path: Path
    steps: int
    seed: int
    sequence_length: int = SEQUENCE_LENGTH


def main() -> None:
    parser = argparse.ArgumentParser(description="M-19.2b clean cardinality sanity.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-main")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-main":
        run_main()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_main()
        analyze_all()
        build_report(checks_passed=False)


def prepare_datasets() -> None:
    datasets = build_datasets()
    for section in ("train", "eval"):
        for name, examples in datasets[section].items():
            _write_jsonl(DATASET_DIR / section / f"{name}.jsonl", examples)

    prompts = {
        f"{section}/{name}": examples
        for section in ("train", "eval")
        for name, examples in datasets[section].items()
    }
    manifest = {
        "kind": "m192b_clean_cardinality_sanity",
        "seed": SEED,
        "model_config": MODEL_CONFIG,
        "position_encoding": POSITION_ENCODING,
        "numeric_tokenization": NUMERIC_TOKENIZATION,
        "train_counts": list(TRAIN_COUNTS),
        "successor_counts": list(SUCCESSOR_COUNTS),
        "length_ood_counts": list(LENGTH_OOD_COUNTS),
        "train_objects": list(TRAIN_OBJECTS),
        "heldout_objects": list(HELDOUT_OBJECTS),
        "nuisance_audit": nuisance_audit(datasets),
        "semantic_overlap_audit": semantic_overlap_audit(datasets),
        "prompt_intersections": prompt_intersections(prompts),
        "train_sets": {
            name: audit_examples(examples)
            for name, examples in datasets["train"].items()
        },
        "eval_splits": {
            name: audit_examples(examples)
            for name, examples in datasets["eval"].items()
        },
    }
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_main() -> None:
    _train_and_eval(
        TrainSpec(
            "successor_symbol",
            DATASET_DIR / "train" / "successor_symbol.jsonl",
            DATASET_DIR / "eval" / "successor_symbol_train_fit.jsonl",
            STEPS["successor_symbol"],
            SEED + 1,
        ),
        ["successor_symbol_train_fit", "successor_symbol_eval_same"],
    )
    analyze_all()
    if not successor_gate():
        build_report(checks_passed=False)
        return

    _train_and_eval(
        TrainSpec(
            "local_successor",
            DATASET_DIR / "train" / "local_successor.jsonl",
            DATASET_DIR / "eval" / "local_successor_train_fit.jsonl",
            STEPS["local_successor"],
            SEED + 2,
        ),
        [
            "local_successor_train_fit",
            "local_successor_seen_object",
            "local_successor_heldout_object",
            "local_successor_mixed_object",
        ],
    )

    _train_and_eval(
        TrainSpec(
            "global_count",
            DATASET_DIR / "train" / "global_count.jsonl",
            DATASET_DIR / "eval" / "global_count_train_fit.jsonl",
            STEPS["global_count"],
            SEED + 3,
        ),
        [
            "global_count_train_fit",
            "global_count_seen_object",
            "global_count_heldout_object",
            "global_count_mixed_object",
        ],
    )
    analyze_all()
    if count_fit_gate():
        _eval_existing_checkpoint(
            "global_count",
            [
                "global_count_separator_ood",
                "global_count_length_ood",
            ],
        )

    _train_and_eval(
        TrainSpec(
            "same_count",
            DATASET_DIR / "train" / "same_count.jsonl",
            DATASET_DIR / "eval" / "same_count_train_fit.jsonl",
            STEPS["same_count"],
            SEED + 4,
        ),
        [
            "same_count_train_fit",
            "same_count_seen_object",
            "same_count_heldout_object",
            "same_count_mixed_object",
        ],
    )
    analyze_all()

    if local_successor_gate():
        _train_and_eval(
            TrainSpec(
                "iterative_count",
                DATASET_DIR / "train" / "iterative_count.jsonl",
                DATASET_DIR / "eval" / "iterative_count_train_fit.jsonl",
                STEPS["iterative_count"],
                SEED + 5,
                sequence_length=ITERATIVE_SEQUENCE_LENGTH,
            ),
            [
                "iterative_count_train_fit",
                "iterative_count_seen",
                "iterative_count_length_ood",
            ],
        )
        analyze_all()
        if iterative_recurrent_gate():
            train_and_eval_gru_control()
    analyze_all()
    build_report(checks_passed=False)


def build_datasets() -> dict[str, dict[str, list[dict[str, Any]]]]:
    successor = [successor_symbol_example(n, index=n) for n in SUCCESSOR_COUNTS]
    local = [
        local_successor_example(n, obj, index=index)
        for index, (n, obj) in enumerate(
            itertools.product(SUCCESSOR_COUNTS, TRAIN_OBJECTS)
        )
    ]
    count = [
        count_example(n, obj, separator="space", index=index)
        for index, (n, obj) in enumerate(itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS))
    ]
    same = same_count_examples(TRAIN_COUNTS, TRAIN_OBJECTS, index_offset=0)
    iterative = [
        iterative_count_example(n, obj, index=index)
        for index, (n, obj) in enumerate(itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS))
    ]

    return {
        "train": {
            "successor_symbol": repeat_examples(successor, 4000),
            "local_successor": repeat_examples(local, 5000),
            "global_count": repeat_examples(count, 7000),
            "same_count": repeat_examples(same, 7000),
            "iterative_count": repeat_examples(iterative, 7000),
        },
        "eval": {
            "successor_symbol_train_fit": successor,
            "successor_symbol_eval_same": [
                successor_symbol_example(n, index=10_000 + n) for n in SUCCESSOR_COUNTS
            ],
            "local_successor_train_fit": local,
            "local_successor_seen_object": [
                local_successor_example(n, obj, index=11_000 + index)
                for index, (n, obj) in enumerate(
                    itertools.product(SUCCESSOR_COUNTS, TRAIN_OBJECTS)
                )
            ],
            "local_successor_heldout_object": [
                local_successor_example(n, obj, index=12_000 + index)
                for index, (n, obj) in enumerate(
                    itertools.product(SUCCESSOR_COUNTS, HELDOUT_OBJECTS)
                )
            ],
            "local_successor_mixed_object": [
                local_successor_example(n, obj, index=13_000 + index)
                for index, (n, obj) in enumerate(
                    itertools.product(SUCCESSOR_COUNTS, ALL_OBJECTS)
                )
            ],
            "global_count_train_fit": count,
            "global_count_seen_object": [
                count_example(n, obj, separator="space", index=14_000 + index)
                for index, (n, obj) in enumerate(
                    itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS)
                )
            ],
            "global_count_heldout_object": [
                count_example(n, obj, separator="space", index=15_000 + index)
                for index, (n, obj) in enumerate(
                    itertools.product(TRAIN_COUNTS, HELDOUT_OBJECTS)
                )
            ],
            "global_count_mixed_object": [
                mixed_count_example(n, index=16_000 + n) for n in TRAIN_COUNTS
            ],
            "global_count_separator_ood": [
                count_example(n, obj, separator="bar", index=17_000 + index)
                for index, (n, obj) in enumerate(
                    itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS)
                )
            ],
            "global_count_length_ood": [
                count_example(n, obj, separator="space", index=18_000 + index)
                for index, (n, obj) in enumerate(
                    itertools.product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS[:2])
                )
            ],
            "same_count_train_fit": same,
            "same_count_seen_object": same_count_examples(
                TRAIN_COUNTS, TRAIN_OBJECTS, index_offset=19_000
            ),
            "same_count_heldout_object": same_count_examples(
                TRAIN_COUNTS,
                HELDOUT_OBJECTS,
                index_offset=20_000,
            ),
            "same_count_mixed_object": mixed_same_count_examples(index_offset=21_000),
            "iterative_count_train_fit": iterative,
            "iterative_count_seen": [
                iterative_count_example(n, obj, index=22_000 + index)
                for index, (n, obj) in enumerate(
                    itertools.product(TRAIN_COUNTS, TRAIN_OBJECTS)
                )
            ],
            "iterative_count_length_ood": [
                iterative_count_example(n, obj, index=23_000 + index)
                for index, (n, obj) in enumerate(
                    itertools.product(LENGTH_OOD_COUNTS, TRAIN_OBJECTS[:2])
                )
            ],
        },
    }


def successor_symbol_example(n: int, *, index: int) -> dict[str, Any]:
    return record(index, "m192b.successor.symbol", f"SUCC {n}", f"FINAL {n + 1}", n=n)


def local_successor_example(n: int, obj: str, *, index: int) -> dict[str, Any]:
    return record(
        index,
        "m192b.successor.object_independent",
        f"STATE {n}\nNEXT_OBJECT {obj}",
        f"FINAL STATE {n + 1}",
        n=n,
        next_n=n + 1,
        object_family=obj,
    )


def count_example(n: int, obj: str, *, separator: str, index: int) -> dict[str, Any]:
    return record(
        index,
        "m192b.count.global",
        f"COUNT\n{object_sequence(n, [obj], separator=separator)}",
        f"FINAL {n}",
        n=n,
        object_family=obj,
        separator=separator,
    )


def mixed_count_example(n: int, *, index: int) -> dict[str, Any]:
    objects = [ALL_OBJECTS[(n + i) % len(ALL_OBJECTS)] for i in range(max(n, 1))]
    return record(
        index,
        "m192b.count.global",
        f"COUNT\n{object_sequence(n, objects, separator='space')}",
        f"FINAL {n}",
        n=n,
        object_family="mixed",
        separator="space",
    )


def same_count_examples(
    counts: Sequence[int],
    objects: Sequence[str],
    *,
    index_offset: int,
) -> list[dict[str, Any]]:
    examples = []
    index = index_offset
    for n, left_obj, right_obj in itertools.product(counts, objects[:3], objects[-3:]):
        examples.append(same_count_example(n, n, left_obj, right_obj, index=index))
        index += 1
        other = (n + 1) % (max(counts) + 1)
        examples.append(same_count_example(n, other, left_obj, right_obj, index=index))
        index += 1
    return examples


def mixed_same_count_examples(*, index_offset: int) -> list[dict[str, Any]]:
    examples = []
    index = index_offset
    for n in TRAIN_COUNTS:
        examples.append(same_count_example(n, n, "x", "q", index=index))
        index += 1
        examples.append(same_count_example(n, (n + 2) % 11, "a", "z", index=index))
        index += 1
    return examples


def same_count_example(
    left_n: int,
    right_n: int,
    left_obj: str,
    right_obj: str,
    *,
    index: int,
) -> dict[str, Any]:
    return record(
        index,
        "m192b.same_count",
        "SAME_COUNT\n"
        f"LEFT\n{object_sequence(left_n, [left_obj], separator='space')}\n"
        f"RIGHT\n{object_sequence(right_n, [right_obj], separator='space')}",
        f"FINAL {'YES' if left_n == right_n else 'NO'}",
        left_n=left_n,
        right_n=right_n,
        left_object_family=left_obj,
        right_object_family=right_obj,
    )


def iterative_count_example(n: int, obj: str, *, index: int) -> dict[str, Any]:
    lines = [f"STATE {0} REM {n}"]
    for step in range(n):
        lines.append("TAKE")
        lines.append(f"STATE {step + 1} REM {n - step - 1}")
    lines.append("HALT")
    lines.append(f"FINAL {n}")
    return record(
        index,
        "m192b.count.iterative",
        f"ITER_COUNT\n{object_sequence(n, [obj], separator='space')}",
        "\n".join(lines),
        n=n,
        object_family=obj,
    )


def object_sequence(n: int, objects: Sequence[str], *, separator: str) -> str:
    if n == 0:
        return "EMPTY"
    if separator == "space":
        sep = " "
    elif separator == "bar":
        sep = " | "
    else:
        raise ValueError(f"unknown separator: {separator}")
    return sep.join(objects[index % len(objects)] for index in range(n))


def record(
    index: int, task_type: str, prompt: str, answer: str, **metadata: Any
) -> dict[str, Any]:
    metadata = {"case_id": index, **metadata}
    return {
        "id": f"{task_type}:{index:06d}",
        "task_type": task_type,
        "prompt": prompt,
        "answer": answer,
        "metadata": metadata,
    }


def repeat_examples(
    examples: Sequence[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    return [dict(examples[index % len(examples)]) for index in range(count)]


def _train_and_eval(spec: TrainSpec, eval_splits: Sequence[str]) -> None:
    run_dir = RUNS_DIR / spec.name
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        result = train_lm(
            TrainConfig(
                train_path=spec.train_path,
                eval_path=spec.eval_path,
                tokenizer_path=TOKENIZER_PATH,
                output_dir=run_dir,
                model_config_name=MODEL_CONFIG,
                steps=spec.steps,
                batch_size=BATCH_SIZE,
                sequence_length=spec.sequence_length,
                loss_mode=LOSS_MODE,
                learning_rate=LEARNING_RATE,
                grad_clip_norm=GRAD_CLIP_NORM,
                numeric_tokenization=NUMERIC_TOKENIZATION,
                position_encoding=POSITION_ENCODING,
                seed=spec.seed,
                eval_every=max(spec.steps // 3, 1),
                eval_batches=20,
                save_every=max(spec.steps // 3, 1),
                cache_dir=ROOT / "cache" / "tokenized_m192b",
            )
        )
        (run_dir / "run_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        raise RuntimeError(f"No checkpoint for {spec.name}")
    _eval_checkpoint(spec.name, checkpoint, eval_splits)
    prune_intermediate_checkpoints(run_dir)


def _eval_existing_checkpoint(name: str, eval_splits: Sequence[str]) -> None:
    checkpoint = final_checkpoint(RUNS_DIR / name)
    if checkpoint is None:
        raise RuntimeError(f"No checkpoint for {name}")
    _eval_checkpoint(name, checkpoint, eval_splits)


def _eval_checkpoint(name: str, checkpoint: Path, eval_splits: Sequence[str]) -> None:
    for split in eval_splits:
        output_dir = RUNS_DIR / name / "eval" / split
        if (output_dir / "summary.json").exists():
            continue
        result = eval_lm(
            checkpoint_path=checkpoint,
            eval_path=DATASET_DIR / "eval" / f"{split}.jsonl",
            tokenizer_path=TOKENIZER_PATH,
            output_dir=output_dir,
            max_examples=None,
            max_new_tokens=256 if "iterative" in split else 32,
            seed=SEED,
            numeric_tokenization=NUMERIC_TOKENIZATION,
        )
        augment_iterative_summary(
            Path(result["predictions_path"]), Path(result["summary_path"])
        )


class GruLanguageModel(nn.Module):
    def __init__(self, *, vocab_size: int, hidden_size: int, pad_id: int) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, hidden_size, padding_idx=pad_id)
        self.gru = nn.GRU(hidden_size, hidden_size, batch_first=True)
        self.output = nn.Linear(hidden_size, vocab_size, bias=False)
        self.output.weight = self.embedding.weight

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(input_ids)
        hidden, _state = self.gru(embedded)
        return self.output(hidden)


def train_and_eval_gru_control() -> None:
    run_dir = RUNS_DIR / "gru_iterative_count"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "checkpoint.pt"
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    pad_id = required_token_id(tokenizer, PAD_TOKEN)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if not checkpoint_path.exists():
        train_records = _read_jsonl_if_exists(
            DATASET_DIR / "train" / "iterative_count.jsonl"
        )
        input_ids, labels = encode_records_for_gru(
            train_records,
            tokenizer=tokenizer,
            sequence_length=ITERATIVE_SEQUENCE_LENGTH,
        )
        dataset = TensorDataset(input_ids, labels)
        generator = torch.Generator().manual_seed(SEED + 600)
        loader = DataLoader(
            dataset,
            batch_size=BATCH_SIZE,
            shuffle=True,
            generator=generator,
            drop_last=True,
        )
        model = GruLanguageModel(
            vocab_size=tokenizer.vocab_size,
            hidden_size=256,
            pad_id=pad_id,
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
        metrics = []
        iterator = iter(loader)
        for step in range(1, STEPS["iterative_count"] + 1):
            try:
                batch_input_ids, batch_labels = next(iterator)
            except StopIteration:
                iterator = iter(loader)
                batch_input_ids, batch_labels = next(iterator)
            batch_input_ids = batch_input_ids.to(device)
            batch_labels = batch_labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch_input_ids)
            loss = compute_shifted_loss(logits, batch_labels)
            if not torch.isfinite(loss):
                raise ValueError(f"Non-finite GRU loss at step {step}: {loss.item()}")
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                GRAD_CLIP_NORM,
            )
            optimizer.step()
            if step % max(STEPS["iterative_count"] // 3, 1) == 0:
                metrics.append(
                    {
                        "step": step,
                        "train_loss": float(loss.item()),
                        "grad_norm": float(grad_norm),
                        "lr": LEARNING_RATE,
                    }
                )
        (run_dir / "metrics.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in metrics),
            encoding="utf-8",
        )
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "vocab_size": tokenizer.vocab_size,
                "hidden_size": 256,
                "pad_id": pad_id,
                "steps": STEPS["iterative_count"],
                "seed": SEED + 600,
            },
            checkpoint_path,
        )
        (run_dir / "run_result.json").write_text(
            json.dumps(
                {
                    "checkpoint_path": str(checkpoint_path),
                    "model": "script_local_gru_lm",
                    "steps": STEPS["iterative_count"],
                    "sequence_length": ITERATIVE_SEQUENCE_LENGTH,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    for split in (
        "iterative_count_train_fit",
        "iterative_count_seen",
        "iterative_count_length_ood",
    ):
        output_dir = run_dir / "eval" / split
        if (output_dir / "summary.json").exists():
            continue
        eval_gru_control(
            checkpoint_path=checkpoint_path,
            eval_path=DATASET_DIR / "eval" / f"{split}.jsonl",
            output_dir=output_dir,
            tokenizer=tokenizer,
            device=device,
        )


def encode_records_for_gru(
    records: Sequence[dict[str, Any]],
    *,
    tokenizer: ByteLevelBpeTokenizer,
    sequence_length: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    encoded = [
        encode_lm_example(
            prompt=str(record["prompt"]),
            answer=str(record["answer"]),
            tokenizer=tokenizer,
            sequence_length=sequence_length,
            loss_mode=LOSS_MODE,
            numeric_tokenization=NUMERIC_TOKENIZATION,
        )
        for record in records
    ]
    return (
        torch.tensor([example.input_ids for example in encoded], dtype=torch.long),
        torch.tensor([example.labels for example in encoded], dtype=torch.long),
    )


def compute_shifted_loss(logits: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    shifted_logits = logits[:, :-1, :].contiguous()
    shifted_labels = labels[:, 1:].contiguous()
    return F.cross_entropy(
        shifted_logits.view(-1, shifted_logits.shape[-1]),
        shifted_labels.view(-1),
        ignore_index=IGNORE_INDEX,
    )


def eval_gru_control(
    *,
    checkpoint_path: Path,
    eval_path: Path,
    output_dir: Path,
    tokenizer: ByteLevelBpeTokenizer,
    device: torch.device,
) -> None:
    checkpoint = torch.load(checkpoint_path, map_location=device)
    model = GruLanguageModel(
        vocab_size=int(checkpoint["vocab_size"]),
        hidden_size=int(checkpoint["hidden_size"]),
        pad_id=int(checkpoint["pad_id"]),
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions = []
    for index, record in enumerate(_read_jsonl_if_exists(eval_path)):
        generated_ids = generate_gru_answer_ids(
            model=model,
            tokenizer=tokenizer,
            prompt=str(record["prompt"]),
            device=device,
            max_new_tokens=256,
        )
        raw_generation = tokenizer.decode(generated_ids, skip_special_tokens=False)
        predicted = extract_generated_answer(raw_generation)
        expected = str(record["answer"])
        final_expected = extract_final_answer(expected)
        final_predicted = extract_final_answer(predicted)
        predictions.append(
            {
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
        )
    predictions_path = output_dir / "predictions.jsonl"
    predictions_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in predictions
        ),
        encoding="utf-8",
    )
    summary = {
        **summarize_predictions(predictions),
        "count": len(predictions),
        "checkpoint_path": str(checkpoint_path),
        "eval_path": str(eval_path),
        "predictions_path": str(predictions_path),
        "model": "script_local_gru_lm",
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    augment_iterative_summary(predictions_path, summary_path)


@torch.no_grad()
def generate_gru_answer_ids(
    *,
    model: GruLanguageModel,
    tokenizer: ByteLevelBpeTokenizer,
    prompt: str,
    device: torch.device,
    max_new_tokens: int,
) -> list[int]:
    bos_id = required_token_id(tokenizer, BOS_TOKEN)
    eos_id = required_token_id(tokenizer, EOS_TOKEN)
    end_id = required_token_id(tokenizer, END_TOKEN)
    ids = [
        bos_id,
        *tokenizer.encode(
            format_inference_prompt(prompt),
            numeric_tokenization=NUMERIC_TOKENIZATION,
        ),
    ]
    generated = torch.tensor([ids], dtype=torch.long, device=device)
    new_ids: list[int] = []
    for _ in range(max_new_tokens):
        context = generated[:, -ITERATIVE_SEQUENCE_LENGTH:]
        logits = model(context)
        next_id = int(torch.argmax(logits[:, -1, :], dim=-1).item())
        new_ids.append(next_id)
        generated = torch.cat(
            [
                generated,
                torch.tensor([[next_id]], dtype=torch.long, device=device),
            ],
            dim=1,
        )
        if next_id in {eos_id, end_id}:
            break
    return new_ids


def required_token_id(tokenizer: ByteLevelBpeTokenizer, token: str) -> int:
    token_id = tokenizer.token_to_id(token)
    if token_id is None:
        raise ValueError(f"Missing tokenizer token: {token}")
    return token_id


def analyze_all() -> None:
    payload = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "remote": remote_environment(),
        "runs": {},
    }
    for run_dir in sorted(RUNS_DIR.glob("*")):
        if run_dir.is_dir():
            payload["runs"][run_dir.name] = analyze_run(run_dir)
    payload["gates"] = gates(payload)
    payload["decision"] = decision(payload)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    lines = [
        "# M-19.2b Clean Cardinality Sanity Report",
        "",
        "## Remote Environment",
        "",
        remote_lines(analysis),
        "",
        "## Nuisance Audit",
        "",
        nuisance_table(analysis),
        "",
        "## Successor Fit",
        "",
        metric_table(
            analysis,
            ["successor_symbol"],
            ["successor_symbol_train_fit", "successor_symbol_eval_same"],
        ),
        "",
        "## Object-Independent Successor",
        "",
        metric_table(
            analysis,
            ["local_successor"],
            [
                "local_successor_train_fit",
                "local_successor_seen_object",
                "local_successor_heldout_object",
                "local_successor_mixed_object",
            ],
        ),
        "",
        "## Clean COUNT",
        "",
        metric_table(
            analysis,
            ["global_count"],
            [
                "global_count_train_fit",
                "global_count_seen_object",
                "global_count_heldout_object",
                "global_count_mixed_object",
            ],
        ),
        "",
        "## Clean SAME_COUNT",
        "",
        metric_table(
            analysis,
            ["same_count"],
            [
                "same_count_train_fit",
                "same_count_seen_object",
                "same_count_heldout_object",
                "same_count_mixed_object",
            ],
        ),
        "",
        "## M-19.2 vs M-19.2a vs M-19.2b",
        "",
        comparison_table(analysis),
        "",
        "## Isolated OOD Axes",
        "",
        metric_table(
            analysis,
            ["global_count"],
            [
                "global_count_heldout_object",
                "global_count_mixed_object",
                "global_count_separator_ood",
                "global_count_length_ood",
            ],
        ),
        "",
        "## Iterative Counting",
        "",
        gated_section(analysis, "iterative"),
        "",
        "## Recurrent Control",
        "",
        recurrent_status(analysis),
        "",
        "## Semantic Overlap Audit",
        "",
        semantic_overlap_table(analysis),
        "",
        "## Interpretation",
        "",
        str(analysis.get("decision", "not enough data")),
        "",
        "## Checks",
        "",
        f"- remote/local ruff + pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{git_commit()}`",
        "",
    ]
    text = "\n".join(lines)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def successor_gate() -> bool:
    analyze_all()
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    run = analysis.get("runs", {}).get("successor_symbol", {})
    return (
        score(run, "successor_symbol_train_fit") >= 0.999
        and score(run, "successor_symbol_eval_same") >= 0.99
    )


def local_successor_gate() -> bool:
    analyze_all()
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    run = analysis.get("runs", {}).get("local_successor", {})
    return (
        score(run, "local_successor_seen_object") >= 0.99
        and score(run, "local_successor_heldout_object") >= 0.95
    )


def count_fit_gate() -> bool:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    run = analysis.get("runs", {}).get("global_count", {})
    return (
        score(run, "global_count_train_fit") >= 0.99
        and score(run, "global_count_seen_object") >= 0.98
    )


def iterative_recurrent_gate() -> bool:
    analyze_all()
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    iterative = analysis.get("runs", {}).get("iterative_count", {})
    return (
        local_successor_gate()
        and score(iterative, "iterative_count_seen") >= 0.98
        and score(iterative, "iterative_count_length_ood") < 0.80
    )


def gates(analysis: dict[str, Any]) -> dict[str, bool]:
    runs = analysis.get("runs", {})
    successor = runs.get("successor_symbol", {})
    local = runs.get("local_successor", {})
    count = runs.get("global_count", {})
    iterative = runs.get("iterative_count", {})
    gru = runs.get("gru_iterative_count", {})
    return {
        "successor_fit": score(successor, "successor_symbol_train_fit") >= 0.999
        and score(successor, "successor_symbol_eval_same") >= 0.99,
        "local_successor": score(local, "local_successor_seen_object") >= 0.99
        and score(local, "local_successor_heldout_object") >= 0.95,
        "count_fit": score(count, "global_count_train_fit") >= 0.99
        and score(count, "global_count_seen_object") >= 0.98,
        "iterative_seen": score(iterative, "iterative_count_seen") >= 0.98,
        "iterative_length_useful": score(iterative, "iterative_count_length_ood")
        >= 0.80,
        "gru_iterative_length_useful": score(gru, "iterative_count_length_ood") >= 0.80,
    }


def decision(analysis: dict[str, Any]) -> str:
    g = analysis.get("gates", {})
    runs = analysis.get("runs", {})
    count = runs.get("global_count", {})
    same = runs.get("same_count", {})
    iterative = runs.get("iterative_count", {})
    if not g.get("successor_fit", False):
        return "E: even minimal successor cannot fit. Stop and debug training/eval infrastructure."
    if g.get("count_fit", False):
        heldout = score(count, "global_count_heldout_object")
        mixed = score(count, "global_count_mixed_object")
        if heldout >= 0.95 and mixed >= 0.95:
            if score(count, "global_count_length_ood") >= 0.80:
                return "A: removing nuisance IDs restores COUNT strongly. Continue concrete numeracy."
            if (
                g.get("local_successor", False)
                and g.get("iterative_seen", False)
                and score(iterative, "iterative_count_length_ood") < 0.80
            ):
                gru = runs.get("gru_iterative_count", {})
                if gru:
                    if score(gru, "iterative_count_length_ood") >= 0.80:
                        return "D: iterative Transformer fails length OOD but GRU/LSTM-style recurrence generalizes."
                    return "F: clean COUNT and iterative seen fit, but both Transformer and GRU control fail length OOD."
                return "D-gated: iterative Transformer fits seen but fails 11..20; run GRU/LSTM recurrent control next."
            return "F: clean COUNT fits but isolated length OOD fails; systematic generalization failure is now benchmark-clean."
    if score(same, "same_count_seen_object") >= 0.98 and not g.get("count_fit", False):
        return "C: SAME_COUNT works but digit COUNT does not. Build number symbols on top of relation/matching."
    if g.get("local_successor", False) and not g.get("count_fit", False):
        if (
            score(iterative, "iterative_count_seen") >= 0.98
            and score(iterative, "iterative_count_length_ood") < 0.80
        ):
            return "D-gated: iterative Transformer fits seen but fails 11..20; run GRU/LSTM recurrent control next."
        return "B: successor works but global count does not. Counting length is the specific bottleneck."
    return "B: minimal successor works, but object-independent successor/global count remain below gate."


def nuisance_audit(
    datasets: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    clean_prompts = [
        str(example["prompt"])
        for section in datasets.values()
        for examples in section.values()
        for example in examples
    ]
    return [
        {
            "source": "M-19.2 generator",
            "field": "CASE/example IDs",
            "present_in_prompt": False,
            "semantic_necessity": "none",
            "action": "audited; no clean-count prompt fix required",
        },
        {
            "source": "M-19.2 generator",
            "field": "train/eval or seed labels",
            "present_in_prompt": False,
            "semantic_necessity": "metadata/report only",
            "action": "audited; no clean-count prompt fix required",
        },
        {
            "source": "M-19.2a pre-fix generator",
            "field": "CASE/example IDs",
            "present_in_prompt": True,
            "semantic_necessity": "none",
            "action": "removed from generator prompts in this patch",
        },
        {
            "source": "M-19.2a pre-fix generator",
            "field": "train/eval labels",
            "present_in_prompt": True,
            "semantic_necessity": "metadata/report only",
            "action": "removed TRAIN_ONLY prompt-disjoint marker in this patch",
        },
        {
            "source": "M-19.2b generated datasets",
            "field": "forbidden prompt markers",
            "present_in_prompt": any(
                prompt_has_forbidden_marker(prompt) for prompt in clean_prompts
            ),
            "semantic_necessity": "none",
            "action": "test-enforced absent",
        },
    ]


def nuisance_pattern(field: str) -> str:
    if field == "TRAIN/EVAL labels":
        return r"\b(TRAIN|EVAL|SPLIT|TRAIN_ONLY)\b"
    if field == "seed-derived labels":
        return r"\bSEED\b"
    return rf"\b{re.escape(field)}\b"


def prompt_field_present(source_text: str, pattern: str) -> bool:
    for line in source_text.splitlines():
        if ("prompt" in line.lower() or 'f"' in line or "f'" in line) and re.search(
            pattern,
            line,
            flags=re.IGNORECASE,
        ):
            return True
    return False


def semantic_overlap_audit(
    datasets: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    train_prompts = {
        name: {str(example["prompt"]) for example in examples}
        for name, examples in datasets["train"].items()
    }
    eval_prompts = {
        name: {str(example["prompt"]) for example in examples}
        for name, examples in datasets["eval"].items()
    }
    return {
        f"{train_name}__{eval_name}": len(train_set & eval_set)
        for train_name, train_set in train_prompts.items()
        for eval_name, eval_set in eval_prompts.items()
    }


def prompt_intersections(groups: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    prompts = {
        name: {str(example["prompt"]) for example in examples}
        for name, examples in groups.items()
    }
    return {
        f"{left}__{right}": len(left_prompts & right_prompts)
        for left, left_prompts in prompts.items()
        for right, right_prompts in prompts.items()
        if left < right
    }


def prompt_has_forbidden_marker(prompt: str) -> bool:
    return any(
        re.search(pattern, prompt, flags=re.IGNORECASE)
        for pattern in FORBIDDEN_PROMPT_PATTERNS
    )


def audit_examples(examples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    prompts = [str(example["prompt"]) for example in examples]
    return {
        "count": len(examples),
        "unique_prompts": len(set(prompts)),
        "duplicate_prompt_count": len(prompts) - len(set(prompts)),
        "task_type_counts": dict(
            Counter(str(example["task_type"]) for example in examples)
        ),
        "forbidden_prompt_count": sum(
            prompt_has_forbidden_marker(prompt) for prompt in prompts
        ),
    }


def analyze_run(run_dir: Path) -> dict[str, Any]:
    payload = {
        "train_config": _read_json_if_exists(run_dir / "train_config.json"),
        "run_result": _read_json_if_exists(run_dir / "run_result.json"),
        "metrics": _read_jsonl_if_exists(run_dir / "metrics.jsonl"),
        "eval": {},
    }
    for summary_path in sorted((run_dir / "eval").glob("*/summary.json")):
        summary = _read_json(summary_path)
        overall = summary.get("overall", {})
        payload["eval"][summary_path.parent.name] = {
            "count": int(overall.get("count", 0)),
            "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
            "full_nem": float(overall.get("normalized_exact_match", 0.0)),
            "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
            "trace_diagnostics": summary.get("trace_diagnostics", {}),
        }
    return payload


def augment_iterative_summary(predictions_path: Path, summary_path: Path) -> None:
    predictions = _read_jsonl_if_exists(predictions_path)
    diagnostics = [
        iterative_trace_diagnostics(str(row["expected"]), str(row["predicted"]))
        for row in predictions
        if str(row["task_type"]) == "m192b.count.iterative"
    ]
    if not diagnostics:
        return
    summary = _read_json(summary_path)
    keys = sorted({key for item in diagnostics for key in item})
    summary["trace_diagnostics"] = {
        key: mean(item.get(key, 0.0) for item in diagnostics) for key in keys
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def iterative_trace_diagnostics(expected: str, predicted: str) -> dict[str, float]:
    expected_states = state_pairs(expected)
    predicted_states = state_pairs(predicted)
    return {
        "state_exact": float(predicted_states == expected_states),
        "halt_exact": float(("HALT" in predicted) == ("HALT" in expected)),
        "transition_valid": float(valid_iterative_states(predicted_states)),
        "final_line_present": float("FINAL" in predicted),
    }


def state_pairs(text: str) -> list[tuple[int, int]]:
    return [
        (int(m.group(1)), int(m.group(2)))
        for m in re.finditer(r"STATE (\d+) REM (\d+)", text)
    ]


def valid_iterative_states(states: Sequence[tuple[int, int]]) -> bool:
    if not states:
        return False
    for (count, rem), (next_count, next_rem) in itertools.pairwise(states):
        if next_count != count + 1 or next_rem != max(0, rem - 1):
            return False
    return True


def metric_table(
    analysis: dict[str, Any], runs: Sequence[str], splits: Sequence[str]
) -> str:
    rows = ["| run | " + " | ".join(splits) + " |", "|---|" + "---:|" * len(splits)]
    for run_name in runs:
        run = analysis.get("runs", {}).get(run_name, {})
        rows.append(
            f"| {run_name} | "
            + " | ".join(f"{score(run, split):.4f}" for split in splits)
            + " |"
        )
    return "\n".join(rows)


def comparison_table(analysis: dict[str, Any]) -> str:
    run = analysis.get("runs", {}).get("global_count", {})
    rows = [
        "| experiment | count seen | heldout object | mixed/format | length OOD | note |",
        "|---|---:|---:|---:|---:|---|",
        "| M-19.2 diagnostic_count_only | 0.9091 | 0.6667 | 0.1818 | n/a | pre-M-19.2b baseline |",
        "| M-19.2a global_count | 0.1818 | 0.1818 | 0.1818 | 0.0000 | CASE-confounded prompt surface |",
        (
            f"| M-19.2b clean global_count | {score(run, 'global_count_seen_object'):.4f} | "
            f"{score(run, 'global_count_heldout_object'):.4f} | "
            f"{score(run, 'global_count_mixed_object'):.4f} | "
            f"{score(run, 'global_count_length_ood'):.4f} | nuisance-free canonical prompt |"
        ),
    ]
    return "\n".join(rows)


def nuisance_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| source | field | present in prompt? | semantic necessity | action |",
        "|---|---|---|---|---|",
    ]
    for row in analysis.get("manifest", {}).get("nuisance_audit", []):
        rows.append(
            f"| {row['source']} | {row['field']} | {row['present_in_prompt']} | "
            f"{row['semantic_necessity']} | {row['action']} |"
        )
    return "\n".join(rows)


def semantic_overlap_table(analysis: dict[str, Any]) -> str:
    overlap = analysis.get("manifest", {}).get("semantic_overlap_audit", {})
    rows = ["| pair | raw prompt intersection | interpretation |", "|---|---:|---|"]
    for key, value in sorted(overlap.items()):
        if value:
            note = "intentional fit/memorization axis when syntax and semantics are identical"
            rows.append(f"| {key} | {value} | {note} |")
    if len(rows) == 2:
        rows.append("| none | 0 | no identical clean prompts |")
    return "\n".join(rows)


def gated_section(analysis: dict[str, Any], section: str) -> str:
    if section == "iterative" and not analysis.get("gates", {}).get(
        "local_successor", False
    ):
        return "skipped: local successor did not pass the >=.99 seen / >=.95 heldout-object gate."
    run = analysis.get("runs", {}).get("iterative_count")
    if not run:
        return "not run yet."
    table = metric_table(
        analysis,
        ["iterative_count"],
        [
            "iterative_count_train_fit",
            "iterative_count_seen",
            "iterative_count_length_ood",
        ],
    )
    diag = (
        run.get("eval", {})
        .get("iterative_count_length_ood", {})
        .get("trace_diagnostics", {})
    )
    return table + "\n\nTrace diagnostics: `" + json.dumps(diag, sort_keys=True) + "`"


def recurrent_status(analysis: dict[str, Any]) -> str:
    if "gru_iterative_count" in analysis.get("runs", {}):
        return metric_table(
            analysis,
            ["gru_iterative_count"],
            [
                "iterative_count_train_fit",
                "iterative_count_seen",
                "iterative_count_length_ood",
            ],
        )
    decision_text = str(analysis.get("decision", ""))
    if decision_text.startswith("D-gated"):
        return "gated but not run in this patch: next run should compare Transformer vs parameter-matched GRU/LSTM."
    return "skipped: recurrent control is only allowed after clean successor, object-independent successor, and iterative seen fit pass."


def score(run: dict[str, Any], split: str) -> float:
    return float(run.get("eval", {}).get(split, {}).get("final_nem", 0.0))


def remote_lines(analysis: dict[str, Any]) -> str:
    remote = analysis.get("remote", {})
    return "\n".join(
        [
            f"- hostname: `{remote.get('hostname', 'unknown')}`",
            f"- GPU: `{remote.get('gpu', 'unknown')}`",
            f"- CUDA visible: `{remote.get('cuda_visible', 'unknown')}`",
            f"- commit SHA: `{remote.get('git_commit', git_commit())}`",
        ]
    )


def remote_environment() -> dict[str, Any]:
    gpu = "unavailable"
    cuda_visible = False
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            gpu = result.stdout.strip()
            cuda_visible = True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {
        "hostname": socket.gethostname(),
        "gpu": gpu,
        "cuda_visible": cuda_visible,
        "git_commit": git_commit(),
        "git_branch": subprocess.getoutput("git branch --show-current"),
    }


def final_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    return checkpoints[-1] if checkpoints else None


def prune_intermediate_checkpoints(run_dir: Path) -> None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    for checkpoint in checkpoints[:-1]:
        checkpoint.unlink(missing_ok=True)


def _write_jsonl(path: Path, examples: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False, sort_keys=True))
            file.write("\n")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> Any:
    return _read_json(path) if path.exists() else {}


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


if __name__ == "__main__":
    main()
