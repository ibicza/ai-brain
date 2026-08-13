from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch

from ai_brain.eval.generation import generate_answer_ids, load_model_for_inference
from ai_brain.eval.metrics import summarize_predictions, task_group
from ai_brain.eval.normalize import (
    extract_generated_answer,
    is_false_answer,
    normalize_answer,
)
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.runtime.device import get_device_info


def generate_answer(
    *,
    checkpoint_path: Path,
    tokenizer_path: Path,
    prompt: str,
    max_new_tokens: int = 32,
    cpu: bool = False,
) -> dict[str, Any]:
    if max_new_tokens <= 0:
        raise ValueError("max_new_tokens must be positive")

    device_info = get_device_info(prefer_cuda=not cpu)
    tokenizer = ByteLevelBpeTokenizer.load(tokenizer_path)
    model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=tokenizer_path,
        device=device_info.device,
    )
    generated_ids = generate_answer_ids(
        model=model,
        tokenizer=tokenizer,
        prompt=prompt,
        max_new_tokens=max_new_tokens,
        device=device_info.device,
    )
    raw_generation = tokenizer.decode(generated_ids, skip_special_tokens=False)
    answer = extract_generated_answer(raw_generation)

    return {
        "prompt": prompt,
        "answer": answer,
        "raw_generation": raw_generation,
        "tokens_generated": len(generated_ids),
        "checkpoint_step": checkpoint.get("step"),
        "device": str(device_info.device),
        "device_name": device_info.name,
    }


def eval_lm(
    *,
    checkpoint_path: Path,
    eval_path: Path,
    tokenizer_path: Path,
    output_dir: Path,
    max_examples: int | None = None,
    max_new_tokens: int = 32,
    seed: int = 1234,
    cpu: bool = False,
) -> dict[str, Any]:
    if max_examples is not None and max_examples <= 0:
        raise ValueError("max_examples must be positive")
    if max_new_tokens <= 0:
        raise ValueError("max_new_tokens must be positive")

    torch.manual_seed(seed)
    device_info = get_device_info(prefer_cuda=not cpu)
    tokenizer = ByteLevelBpeTokenizer.load(tokenizer_path)
    model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=tokenizer_path,
        device=device_info.device,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = output_dir / "predictions.jsonl"
    summary_path = output_dir / "summary.json"

    predictions: list[dict[str, Any]] = []
    with predictions_path.open("w", encoding="utf-8") as output_file:
        for index, record in enumerate(_iter_eval_records(eval_path)):
            if max_examples is not None and index >= max_examples:
                break

            generated_ids = generate_answer_ids(
                model=model,
                tokenizer=tokenizer,
                prompt=record["prompt"],
                max_new_tokens=max_new_tokens,
                device=device_info.device,
            )
            raw_generation = tokenizer.decode(generated_ids, skip_special_tokens=False)
            predicted = extract_generated_answer(raw_generation)
            expected = str(record["answer"])
            exact_match = predicted == expected
            normalized_exact_match = normalize_answer(predicted) == normalize_answer(
                expected
            )
            false_answer = is_false_answer(
                task_type=str(record["task_type"]),
                expected=expected,
                predicted=predicted,
            )
            prediction = {
                "id": str(record.get("id", f"{record['task_type']}:{index:06d}")),
                "task_type": str(record["task_type"]),
                "task_group": task_group(str(record["task_type"])),
                "prompt": str(record["prompt"]),
                "expected": expected,
                "predicted": predicted,
                "raw_generation": raw_generation,
                "tokens_generated": len(generated_ids),
                "exact_match": exact_match,
                "normalized_exact_match": normalized_exact_match,
                "false_answer": false_answer,
            }
            predictions.append(prediction)
            output_file.write(
                json.dumps(prediction, ensure_ascii=False, sort_keys=True)
            )
            output_file.write("\n")

    summary = {
        **summarize_predictions(predictions),
        "count": len(predictions),
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_step": checkpoint.get("step"),
        "eval_path": str(eval_path),
        "tokenizer_path": str(tokenizer_path),
        "predictions_path": str(predictions_path),
        "max_examples": max_examples,
        "max_new_tokens": max_new_tokens,
        "seed": seed,
        "device": str(device_info.device),
        "device_name": device_info.name,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return {
        "output_dir": str(output_dir),
        "predictions_path": str(predictions_path),
        "summary_path": str(summary_path),
        "summary": summary,
    }


def _iter_eval_records(path: Path):
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            if (
                "prompt" not in record
                or "answer" not in record
                or "task_type" not in record
            ):
                raise ValueError(f"Record is missing prompt/answer/task_type in {path}")
            yield record
