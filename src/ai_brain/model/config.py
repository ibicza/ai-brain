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
    model_type: str = "tiny"
    input_layers: int = 1
    recurrent_layers: int = 1
    recurrent_cycles: int = 1
    output_layers: int = 0
    position_encoding: str = "absolute"

    def validate(self) -> None:
        if self.model_type not in {
            "tiny",
            "recurrent",
            "numeric",
            "abacus",
            "coupled",
            "gated_place",
        }:
            raise ValueError(
                "model_type must be 'tiny', 'recurrent', 'numeric', "
                "'abacus', 'coupled', or 'gated_place'"
            )

        if self.position_encoding not in {"absolute", "nope"}:
            raise ValueError("position_encoding must be 'absolute' or 'nope'")

        if self.vocab_size <= 0:
            raise ValueError("vocab_size must be positive")

        if self.max_sequence_length <= 0:
            raise ValueError("max_sequence_length must be positive")

        if self.d_model <= 0:
            raise ValueError("d_model must be positive")

        if self.num_heads <= 0:
            raise ValueError("num_heads must be positive")

        if self.d_model % self.num_heads != 0:
            raise ValueError("d_model must be divisible by num_heads")

        if self.ffn_hidden_dim <= 0:
            raise ValueError("ffn_hidden_dim must be positive")

        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0.0, 1.0)")

        if self.model_type in {"tiny", "numeric", "abacus", "coupled", "gated_place"}:
            if self.num_layers <= 0:
                raise ValueError("num_layers must be positive")
            return

        if self.input_layers < 0:
            raise ValueError("input_layers must be non-negative")

        if self.recurrent_layers != 1:
            raise ValueError("recurrent_layers must be 1 for the shared recurrent core")

        if self.recurrent_cycles <= 0:
            raise ValueError("recurrent_cycles must be positive")

        if self.output_layers < 0:
            raise ValueError("output_layers must be non-negative")


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
        model_type="tiny",
    )


def arithmetic_3m_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=1024,
        max_sequence_length=128,
        d_model=256,
        num_layers=4,
        num_heads=8,
        ffn_hidden_dim=1024,
        dropout=0.0,
        tie_embeddings=True,
        model_type="tiny",
    )


def arithmetic_10m_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=1024,
        max_sequence_length=128,
        d_model=384,
        num_layers=5,
        num_heads=8,
        ffn_hidden_dim=1536,
        dropout=0.0,
        tie_embeddings=True,
        model_type="tiny",
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
        model_type="tiny",
    )


def numeric_debug_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=256,
        max_sequence_length=32,
        d_model=64,
        num_layers=1,
        num_heads=4,
        ffn_hidden_dim=128,
        dropout=0.0,
        tie_embeddings=True,
        model_type="numeric",
    )


def numeric_tiny_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=1024,
        max_sequence_length=128,
        d_model=128,
        num_layers=2,
        num_heads=4,
        ffn_hidden_dim=512,
        dropout=0.0,
        tie_embeddings=True,
        model_type="numeric",
    )


def abacus_debug_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=256,
        max_sequence_length=32,
        d_model=64,
        num_layers=1,
        num_heads=4,
        ffn_hidden_dim=128,
        dropout=0.0,
        tie_embeddings=True,
        model_type="abacus",
    )


def abacus_tiny_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=1024,
        max_sequence_length=128,
        d_model=128,
        num_layers=2,
        num_heads=4,
        ffn_hidden_dim=512,
        dropout=0.0,
        tie_embeddings=True,
        model_type="abacus",
    )


def coupled_debug_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=256,
        max_sequence_length=32,
        d_model=64,
        num_layers=1,
        num_heads=4,
        ffn_hidden_dim=128,
        dropout=0.0,
        tie_embeddings=True,
        model_type="coupled",
    )


def coupled_tiny_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=1024,
        max_sequence_length=128,
        d_model=128,
        num_layers=2,
        num_heads=4,
        ffn_hidden_dim=512,
        dropout=0.0,
        tie_embeddings=True,
        model_type="coupled",
    )


def gated_place_debug_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=256,
        max_sequence_length=32,
        d_model=64,
        num_layers=1,
        num_heads=4,
        ffn_hidden_dim=128,
        dropout=0.0,
        tie_embeddings=True,
        model_type="gated_place",
    )


def gated_place_tiny_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=1024,
        max_sequence_length=128,
        d_model=128,
        num_layers=2,
        num_heads=4,
        ffn_hidden_dim=512,
        dropout=0.0,
        tie_embeddings=True,
        model_type="gated_place",
    )


def recurrent_debug_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=256,
        max_sequence_length=256,
        d_model=64,
        num_layers=1,
        num_heads=4,
        ffn_hidden_dim=128,
        dropout=0.0,
        tie_embeddings=True,
        model_type="recurrent",
        input_layers=1,
        recurrent_layers=1,
        recurrent_cycles=2,
        output_layers=1,
    )


def recurrent_tiny_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=1024,
        max_sequence_length=256,
        d_model=128,
        num_layers=1,
        num_heads=4,
        ffn_hidden_dim=512,
        dropout=0.0,
        tie_embeddings=True,
        model_type="recurrent",
        input_layers=1,
        recurrent_layers=1,
        recurrent_cycles=4,
        output_layers=1,
    )


MODEL_CONFIG_NAMES: tuple[str, ...] = (
    "debug",
    "tiny",
    "arithmetic_3m",
    "arithmetic_10m",
    "numeric_debug",
    "numeric_tiny",
    "abacus_debug",
    "abacus_tiny",
    "coupled_debug",
    "coupled_tiny",
    "gated_place_debug",
    "gated_place_tiny",
    "recurrent_debug",
    "recurrent_tiny",
)


def get_named_model_config(name: str) -> ModelConfig:
    if name == "debug":
        return debug_config()

    if name == "tiny":
        return tiny_config()

    if name == "arithmetic_3m":
        return arithmetic_3m_config()

    if name == "arithmetic_10m":
        return arithmetic_10m_config()

    if name == "numeric_debug":
        return numeric_debug_config()

    if name == "numeric_tiny":
        return numeric_tiny_config()

    if name == "abacus_debug":
        return abacus_debug_config()

    if name == "abacus_tiny":
        return abacus_tiny_config()

    if name == "coupled_debug":
        return coupled_debug_config()

    if name == "coupled_tiny":
        return coupled_tiny_config()

    if name == "gated_place_debug":
        return gated_place_debug_config()

    if name == "gated_place_tiny":
        return gated_place_tiny_config()

    if name == "recurrent_debug":
        return recurrent_debug_config()

    if name == "recurrent_tiny":
        return recurrent_tiny_config()

    available = ", ".join(MODEL_CONFIG_NAMES)
    raise ValueError(f"Unknown model config: {name}. Available configs: {available}")
