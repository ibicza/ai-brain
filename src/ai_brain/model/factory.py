from __future__ import annotations

from typing import Any

from torch import nn

from ai_brain.model.config import ModelConfig
from ai_brain.model.recurrent_transformer import RecurrentCausalTransformer
from ai_brain.model.tiny_transformer import TinyCausalTransformer


def build_model(config: ModelConfig) -> nn.Module:
    config.validate()
    if config.model_type == "tiny":
        return TinyCausalTransformer(config)
    if config.model_type == "recurrent":
        return RecurrentCausalTransformer(config)
    raise ValueError(f"Unknown model_type: {config.model_type}")


def model_class_name(config: ModelConfig) -> str:
    if config.model_type == "tiny":
        return "TinyCausalTransformer"
    if config.model_type == "recurrent":
        return "RecurrentCausalTransformer"
    raise ValueError(f"Unknown model_type: {config.model_type}")


def model_config_from_checkpoint(payload: dict[str, Any]) -> ModelConfig:
    model_config_payload = dict(payload["model_config"])
    model_config_payload.setdefault("model_type", "tiny")
    return ModelConfig(**model_config_payload)
