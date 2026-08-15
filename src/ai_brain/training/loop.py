from __future__ import annotations

import math
from dataclasses import asdict, replace
from typing import Any

import torch
import torch.nn.functional as F

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.model.config import get_named_model_config
from ai_brain.model.factory import build_model, model_class_name
from ai_brain.numeric_features import NUMERIC_FEATURE_KEYS
from ai_brain.runtime.device import get_device_info
from ai_brain.training.batching import sample_batch
from ai_brain.training.checkpoint import load_checkpoint, save_checkpoint
from ai_brain.training.config import TrainConfig
from ai_brain.training.lm_dataset import (
    IGNORE_INDEX,
    default_lm_cache_path,
    load_tokenized_lm_dataset,
    prepare_lm_dataset,
)
from ai_brain.training.metrics import append_metrics_jsonl, write_train_config


def compute_lm_loss(logits: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    if logits.ndim != 3:
        raise ValueError(
            "logits must have shape [batch_size, sequence_length, vocab_size]"
        )
    if labels.ndim != 2:
        raise ValueError("labels must have shape [batch_size, sequence_length]")
    if logits.shape[:2] != labels.shape:
        raise ValueError("logits and labels batch/sequence dimensions must match")

    shifted_logits = logits[:, :-1, :].contiguous()
    shifted_labels = labels[:, 1:].contiguous()
    return F.cross_entropy(
        shifted_logits.view(-1, shifted_logits.shape[-1]),
        shifted_labels.view(-1),
        ignore_index=IGNORE_INDEX,
    )


@torch.no_grad()
def evaluate_loss(
    *,
    model: torch.nn.Module,
    dataset,
    batch_size: int,
    batches: int,
    device: torch.device,
    seed: int,
) -> float:
    was_training = model.training
    model.eval()
    generator = torch.Generator().manual_seed(seed)
    losses: list[float] = []

    for _ in range(batches):
        batch = sample_batch(
            dataset,
            batch_size=batch_size,
            device=device,
            generator=generator,
        )
        logits = _model_logits(model, batch)
        loss = compute_lm_loss(logits, batch["labels"])
        if not torch.isfinite(loss):
            raise ValueError(f"Non-finite eval loss: {loss.item()}")
        loss_value = float(loss.detach().cpu().item())
        if math.isfinite(loss_value):
            losses.append(loss_value)

    if was_training:
        model.train()

    if not losses:
        raise ValueError("Evaluation produced no finite losses")
    return sum(losses) / len(losses)


def _model_logits(
    model: torch.nn.Module,
    batch: dict[str, torch.Tensor],
) -> torch.Tensor:
    if getattr(model, "uses_numeric_features", False):
        return model(
            batch["input_ids"],
            **{key: batch[key] for key in NUMERIC_FEATURE_KEYS},
        )
    if getattr(model, "uses_abacus_position_features", False):
        return model(
            batch["input_ids"],
            abacus_position_ids=batch["abacus_position_ids"],
        )
    if getattr(model, "uses_coupled_position_features", False):
        return model(
            batch["input_ids"],
            coupled_position_ids=batch["coupled_position_ids"],
        )
    if getattr(model, "uses_gated_place_features", False):
        return model(
            batch["input_ids"],
            digit_place_ids=batch["digit_place_ids"],
        )
    return model(batch["input_ids"])


def train_lm(config: TrainConfig) -> dict[str, Any]:
    config.validate()
    config.output_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = ByteLevelBpeTokenizer.load(config.tokenizer_path)
    model_config = replace(
        get_named_model_config(config.model_config_name),
        vocab_size=tokenizer.vocab_size,
        max_sequence_length=config.sequence_length,
    )
    model_config.validate()

    train_cache_path = default_lm_cache_path(
        cache_dir=config.cache_dir,
        input_path=config.train_path,
        tokenizer_path=config.tokenizer_path,
        sequence_length=config.sequence_length,
        loss_mode=config.loss_mode,
        numeric_tokenization=config.numeric_tokenization,
        abacus_random_offset_max=(
            config.abacus_random_offset_max
            if config.model_config_name.startswith("abacus_")
            else 0
        ),
        coupled_random_offset_max=(
            config.coupled_random_offset_max
            if config.model_config_name.startswith("coupled_")
            else 0
        ),
        position_offset_seed=config.seed,
    )
    eval_cache_path = default_lm_cache_path(
        cache_dir=config.cache_dir,
        input_path=config.eval_path,
        tokenizer_path=config.tokenizer_path,
        sequence_length=config.sequence_length,
        loss_mode=config.loss_mode,
        numeric_tokenization=config.numeric_tokenization,
        abacus_random_offset_max=0,
        coupled_random_offset_max=0,
        position_offset_seed=0,
    )

    train_cache_info = prepare_lm_dataset(
        input_path=config.train_path,
        tokenizer_path=config.tokenizer_path,
        output_path=train_cache_path,
        sequence_length=config.sequence_length,
        loss_mode=config.loss_mode,
        numeric_tokenization=config.numeric_tokenization,
        abacus_random_offset_max=(
            config.abacus_random_offset_max
            if config.model_config_name.startswith("abacus_")
            else 0
        ),
        coupled_random_offset_max=(
            config.coupled_random_offset_max
            if config.model_config_name.startswith("coupled_")
            else 0
        ),
        position_offset_seed=config.seed,
    )
    eval_cache_info = prepare_lm_dataset(
        input_path=config.eval_path,
        tokenizer_path=config.tokenizer_path,
        output_path=eval_cache_path,
        sequence_length=config.sequence_length,
        loss_mode=config.loss_mode,
        numeric_tokenization=config.numeric_tokenization,
        abacus_random_offset_max=0,
        coupled_random_offset_max=0,
        position_offset_seed=0,
    )

    train_dataset = load_tokenized_lm_dataset(train_cache_path)
    eval_dataset = load_tokenized_lm_dataset(eval_cache_path)

    device_info = get_device_info(prefer_cuda=not config.cpu)
    device = device_info.device

    torch.manual_seed(config.seed)
    if device_info.is_cuda:
        torch.cuda.manual_seed_all(config.seed)

    model = build_model(model_config).to(device)
    initialized_from_checkpoint = None
    if config.init_checkpoint_path is not None:
        checkpoint = load_checkpoint(config.init_checkpoint_path, map_location=device)
        checkpoint_state = checkpoint["model_state_dict"]
        model_state = model.state_dict()
        compatible_state = {
            key: value
            for key, value in checkpoint_state.items()
            if key in model_state and model_state[key].shape == value.shape
        }
        skipped_keys = sorted(set(checkpoint_state) - set(compatible_state))
        model_state.update(compatible_state)
        model.load_state_dict(model_state)
        initialized_from_checkpoint = {
            "path": str(config.init_checkpoint_path),
            "step": checkpoint.get("step"),
            "loaded_key_count": len(compatible_state),
            "skipped_key_count": len(skipped_keys),
            "skipped_keys_sample": skipped_keys[:10],
        }
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    generator = torch.Generator().manual_seed(config.seed)

    metrics_path = config.output_dir / "metrics.jsonl"
    train_config_payload = {
        "train_config": config.to_dict(),
        "model": model_class_name(model_config),
        "model_config": asdict(model_config),
        "device": str(device),
        "device_name": device_info.name,
        "tokenizer": tokenizer.info(),
        "train_cache": train_cache_info,
        "eval_cache": eval_cache_info,
        "initialized_from_checkpoint": initialized_from_checkpoint,
    }
    write_train_config(config.output_dir / "train_config.json", train_config_payload)

    checkpoint_paths: list[str] = []
    last_metrics: dict[str, Any] = {}

    model.train()
    for step in range(1, config.steps + 1):
        batch = sample_batch(
            train_dataset,
            batch_size=config.batch_size,
            device=device,
            generator=generator,
        )
        logits = _model_logits(model, batch)
        loss = compute_lm_loss(logits, batch["labels"])
        if not torch.isfinite(loss):
            raise ValueError(f"Non-finite train loss at step {step}: {loss.item()}")

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(
            model.parameters(),
            config.grad_clip_norm,
        )
        optimizer.step()

        train_loss = float(loss.detach().cpu().item())
        grad_norm_value = float(grad_norm.detach().cpu().item())
        last_metrics = {
            "step": step,
            "train_loss": train_loss,
            "lr": config.learning_rate,
            "grad_norm": grad_norm_value,
        }

        if step % config.eval_every == 0 or step == config.steps:
            eval_loss = evaluate_loss(
                model=model,
                dataset=eval_dataset,
                batch_size=config.batch_size,
                batches=config.eval_batches,
                device=device,
                seed=config.seed + step,
            )
            last_metrics = {**last_metrics, "eval_loss": eval_loss}
            append_metrics_jsonl(metrics_path, last_metrics)

        if step % config.save_every == 0 or step == config.steps:
            checkpoint_path = save_checkpoint(
                output_dir=config.output_dir,
                step=step,
                model=model,
                optimizer=optimizer,
                model_config=model_config,
                train_config=config,
                tokenizer_path=config.tokenizer_path,
                last_metrics=last_metrics,
            )
            checkpoint_paths.append(str(checkpoint_path))

    if device_info.is_cuda:
        torch.cuda.synchronize()

    return {
        "output_dir": str(config.output_dir),
        "metrics_path": str(metrics_path),
        "checkpoint_paths": checkpoint_paths,
        "final_step": config.steps,
        "last_metrics": last_metrics,
        "train_cache": train_cache_info,
        "eval_cache": eval_cache_info,
        "device": str(device),
        "device_name": device_info.name,
        "model_config": asdict(model_config),
        "initialized_from_checkpoint": initialized_from_checkpoint,
    }
