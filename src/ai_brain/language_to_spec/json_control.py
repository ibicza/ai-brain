"""Free-JSON causal-LM control with schema-enumerated constrained decoding."""

from __future__ import annotations

import itertools
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from ai_brain.eval.generation import build_inference_input_ids, load_model_for_inference
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import END_TOKEN, EOS_TOKEN
from ai_brain.language_to_spec.generator import load_language_rows
from ai_brain.language_to_spec.schema import (
    VARIABLES,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    build_family_specification,
    canonicalize_specification,
    strict_specification_from_json,
)
from ai_brain.runtime.device import get_device_info
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm


def _answer_payload(
    status: ParseStatus,
    specification: Any | None,
    code: ValidationCode | None = None,
) -> str:
    payload: dict[str, Any] = {
        "specification": (
            asdict(canonicalize_specification(specification))
            if specification is not None
            else None
        ),
        "status": str(status),
    }
    if code is not None:
        payload["error"] = str(code)
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def valid_control_answers() -> tuple[str, ...]:
    answers = set()
    for family in SemanticFamily:
        if family == SemanticFamily.NOOP:
            assignments = ((),)
        elif family == SemanticFamily.CLEAR:
            assignments = tuple((value,) for value in VARIABLES)
        elif family == SemanticFamily.DRAIN:
            assignments = tuple(itertools.permutations(VARIABLES, 2))
        elif family in {SemanticFamily.MERGE_TWO, SemanticFamily.DROP_THEN_TRANSFER}:
            assignments = tuple(itertools.permutations(VARIABLES, 3))
        else:
            assignments = tuple(itertools.permutations(VARIABLES, 4))
        for assignment in assignments:
            sources = assignment if family == SemanticFamily.CLEAR else assignment[:-1]
            destination = (
                None
                if family in {SemanticFamily.NOOP, SemanticFamily.CLEAR}
                else assignment[-1]
            )
            spec = build_family_specification(
                family, sources=tuple(sources), destination=destination
            )
            answers.add(_answer_payload(ParseStatus.SUPPORTED, spec))
    negative = {
        ParseStatus.AMBIGUOUS: (
            ValidationCode.MISSING_DESTINATION,
            ValidationCode.AMBIGUOUS_PRONOUN,
            ValidationCode.UNCLEAR_ORDER,
            ValidationCode.MISSING_PRESERVE_BEHAVIOR,
        ),
        ParseStatus.CONTRADICTORY: (
            ValidationCode.PRESERVE_TRANSFER_CONFLICT,
            ValidationCode.DROP_TRANSFER_CONFLICT,
            ValidationCode.IMPOSSIBLE_TERMINATION,
        ),
        ParseStatus.UNSUPPORTED: (ValidationCode.UNSUPPORTED_OPERATION,),
    }
    for status, codes in negative.items():
        answers.update(_answer_payload(status, None, code) for code in codes)
    return tuple(sorted(answers))


def train_free_json_control(
    *,
    train_path: Path,
    validation_path: Path,
    tokenizer_path: Path,
    output_dir: Path,
    seed: int,
    steps: int = 3_000,
    cpu: bool = False,
) -> dict[str, Any]:
    return train_lm(
        TrainConfig(
            train_path=train_path,
            eval_path=validation_path,
            tokenizer_path=tokenizer_path,
            output_dir=output_dir,
            model_config_name="tiny",
            steps=steps,
            batch_size=8,
            sequence_length=512,
            loss_mode="answer-only",
            learning_rate=3e-4,
            grad_clip_norm=1.0,
            seed=seed,
            eval_every=250,
            eval_batches=20,
            save_every=steps,
            cpu=cpu,
        )
    )


def _candidate_token_sequences(
    tokenizer: ByteLevelBpeTokenizer,
) -> tuple[tuple[int, ...], ...]:
    eos_id = tokenizer.token_to_id(EOS_TOKEN)
    if eos_id is None:
        raise ValueError("Tokenizer is missing EOS")
    return tuple(
        tuple(tokenizer.encode(answer + "\n" + END_TOKEN) + [eos_id])
        for answer in valid_control_answers()
    )


@torch.no_grad()
def constrained_generate_batch(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    prompts: Sequence[str],
    device: torch.device,
    max_new_tokens: int = 256,
) -> list[str]:
    candidates = _candidate_token_sequences(tokenizer)
    end_id = tokenizer.token_to_id(END_TOKEN)
    if end_id is None:
        raise ValueError("Tokenizer is missing END")
    prompt_ids = [
        build_inference_input_ids(prompt=prompt, tokenizer=tokenizer, device=device)[
            0
        ].tolist()
        for prompt in prompts
    ]
    active = [list(candidates) for _ in prompts]
    generated: list[list[int]] = [[] for _ in prompts]
    done = [False] * len(prompts)
    model.eval()
    for _ in range(max_new_tokens):
        if all(done):
            break
        sequences = [
            (prompt + suffix)[-model.config.max_sequence_length :]
            for prompt, suffix in zip(prompt_ids, generated, strict=True)
        ]
        max_length = max(len(sequence) for sequence in sequences)
        input_ids = torch.zeros(
            (len(sequences), max_length), dtype=torch.long, device=device
        )
        attention_mask = torch.zeros_like(input_ids)
        last_indices = []
        for index, sequence in enumerate(sequences):
            input_ids[index, : len(sequence)] = torch.tensor(sequence, device=device)
            attention_mask[index, : len(sequence)] = 1
            last_indices.append(len(sequence) - 1)
        logits = model(input_ids, attention_key_mask=attention_mask)
        for index in range(len(prompts)):
            if done[index]:
                continue
            prefix_length = len(generated[index])
            matching = [
                candidate
                for candidate in active[index]
                if len(candidate) > prefix_length
                and candidate[:prefix_length] == tuple(generated[index])
            ]
            allowed = {candidate[prefix_length] for candidate in matching}
            if not allowed:
                done[index] = True
                continue
            token_scores = logits[index, last_indices[index]]
            next_id = max(
                allowed, key=lambda token_id: float(token_scores[token_id].item())
            )
            generated[index].append(next_id)
            active[index] = [
                candidate
                for candidate in matching
                if candidate[prefix_length] == next_id
            ]
            if next_id == end_id:
                done[index] = True
    outputs = []
    for ids in generated:
        if end_id in ids:
            ids = ids[: ids.index(end_id)]
        outputs.append(tokenizer.decode(ids, skip_special_tokens=False).strip())
    return outputs


def _score_json_prediction(prediction: str, row: dict[str, Any]) -> dict[str, float]:
    valid_json = 0.0
    schema_valid = 0.0
    semantic_exact = 0.0
    status_correct = 0.0
    try:
        payload = json.loads(prediction)
        valid_json = 1.0
        if set(payload) not in (
            {"status", "specification"},
            {"status", "specification", "error"},
        ):
            raise ValueError("unexpected JSON fields")
        status = ParseStatus(payload["status"])
        specification = payload["specification"]
        if specification is not None:
            strict_specification_from_json(specification)
        if status == ParseStatus.SUPPORTED and specification is None:
            raise ValueError("supported output requires specification")
        if status != ParseStatus.SUPPORTED and specification is not None:
            raise ValueError("abstention output cannot carry specification")
        schema_valid = 1.0
        status_correct = float(str(status) == row["status"])
        semantic_exact = float(
            status_correct
            and specification == row["canonical_specification"]
            and payload.get("error") == row["error_code"]
        )
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        pass
    return {
        "valid_json": valid_json,
        "schema_valid": schema_valid,
        "whole_specification_exact": float(prediction == row["answer"]),
        "semantic_specification_exact": semantic_exact,
        "status_correct": status_correct,
    }


def evaluate_free_json_control(
    *,
    checkpoint_path: Path,
    tokenizer_path: Path,
    rows: Sequence[dict[str, Any]],
    cpu: bool = False,
    batch_size: int = 32,
) -> dict[str, Any]:
    device = get_device_info(prefer_cuda=not cpu).device
    tokenizer = ByteLevelBpeTokenizer.load(tokenizer_path)
    model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=tokenizer_path,
        device=device,
    )
    scores = []
    predictions = []
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        outputs = constrained_generate_batch(
            model=model,
            tokenizer=tokenizer,
            prompts=[row["text"] for row in batch],
            device=device,
        )
        predictions.extend(outputs)
        scores.extend(
            _score_json_prediction(output, row)
            for output, row in zip(outputs, batch, strict=True)
        )
    metric_names = tuple(scores[0]) if scores else ()
    return {
        "count": len(rows),
        "checkpoint_step": checkpoint.get("step"),
        "constrained_decoding": "finite schema-enumerated prefix grammar",
        **{
            metric: sum(score[metric] for score in scores) / max(1, len(scores))
            for metric in metric_names
        },
        "samples": [
            {
                "text": row["text"],
                "target": row["answer"],
                "prediction": prediction,
            }
            for row, prediction in list(zip(rows, predictions, strict=True))[:50]
        ],
    }


def load_and_evaluate_free_json(
    checkpoint_path: Path,
    tokenizer_path: Path,
    dataset_path: Path,
    *,
    cpu: bool = False,
) -> dict[str, Any]:
    return evaluate_free_json_control(
        checkpoint_path=checkpoint_path,
        tokenizer_path=tokenizer_path,
        rows=load_language_rows(dataset_path),
        cpu=cpu,
    )
