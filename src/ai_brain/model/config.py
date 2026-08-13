from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int = 1024
    max_sequence_length: int = 128
    d_model: int = 128
    num_layers: int = 2
    num_heads: int = 4
    ffn_hidden_dim: int = 512
    dropout: float = 0.0
    tie_embeddings: bool = True

    def validate(self) -> None:
        if self.vocab_size <= 0:
            raise ValueError("vocab_size must be positive")

        if self.max_sequence_length <= 0:
            raise ValueError("max_sequence_length must be positive")

        if self.d_model <= 0:
            raise ValueError("d_model must be positive")

        if self.num_layers <= 0:
            raise ValueError("num_layers must be positive")

        if self.num_heads <= 0:
            raise ValueError("num_heads must be positive")

        if self.d_model % self.num_heads != 0:
            raise ValueError("d_model must be divisible by num_heads")

        if self.ffn_hidden_dim <= 0:
            raise ValueError("ffn_hidden_dim must be positive")

        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0.0, 1.0)")


def tiny_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=1024,
        max_sequence_length=128,
        d_model=128,
        num_layers=2,
        num_heads=4,
        ffn_hidden_dim=512,
        dropout=0.0,
        tie_embeddings=True,
    )


def debug_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=256,
        max_sequence_length=32,
        d_model=64,
        num_layers=1,
        num_heads=4,
        ffn_hidden_dim=128,
        dropout=0.0,
        tie_embeddings=True,
    )
