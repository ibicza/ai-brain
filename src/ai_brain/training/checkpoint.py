from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from ai_brain.model.config import ModelConfig
from ai_brain.training.config import TrainConfig


def save_checkpoint(
    *,
    output_dir: Path,
    step: int,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    model_config: ModelConfig,
    train_config: TrainConfig,
    tokenizer_path: Path,
    last_metrics: dict[str, Any],
) -> Path:
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / f"step_{step:06d}.pt"

    payload = {
        "step": step,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "model_config": asdict(model_config),
        "train_config": train_config.to_dict(),
        "tokenizer_path": str(tokenizer_path),
        "last_metrics": last_metrics,
    }
    torch.save(payload, checkpoint_path)
    return checkpoint_path


def load_checkpoint(
    path: Path, *, map_location: str | torch.device = "cpu"
) -> dict[str, Any]:
    return torch.load(path, map_location=map_location)
