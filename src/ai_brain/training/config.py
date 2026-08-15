from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from ai_brain.language.tokenizer.bpe_tokenizer import NumericTokenizationMode

LossMode = Literal["answer-only", "full"]
LOSS_MODES: tuple[LossMode, ...] = ("answer-only", "full")


@dataclass(frozen=True)
class TrainConfig:
    train_path: Path
    eval_path: Path
    tokenizer_path: Path
    output_dir: Path
    model_config_name: str = "debug"
    steps: int = 200
    batch_size: int = 8
    sequence_length: int = 256
    loss_mode: LossMode = "answer-only"
    learning_rate: float = 3e-4
    grad_clip_norm: float = 1.0
    numeric_tokenization: NumericTokenizationMode = "default_bpe"
    abacus_random_offset_max: int = 0
    seed: int = 1234
    eval_every: int = 50
    eval_batches: int = 20
    save_every: int = 100
    cache_dir: Path = Path("cache/tokenized")
    init_checkpoint_path: Path | None = None
    cpu: bool = False

    def validate(self) -> None:
        if self.steps <= 0:
            raise ValueError("steps must be positive")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.sequence_length < 2:
            raise ValueError("sequence_length must be at least 2")
        if self.loss_mode not in LOSS_MODES:
            raise ValueError(f"Unknown loss_mode: {self.loss_mode}")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        if self.grad_clip_norm <= 0:
            raise ValueError("grad_clip_norm must be positive")
        if self.numeric_tokenization not in {"default_bpe", "digit_safe"}:
            raise ValueError(
                f"Unknown numeric_tokenization: {self.numeric_tokenization}"
            )
        if self.abacus_random_offset_max < 0:
            raise ValueError("abacus_random_offset_max must be non-negative")
        if self.eval_every <= 0:
            raise ValueError("eval_every must be positive")
        if self.eval_batches <= 0:
            raise ValueError("eval_batches must be positive")
        if self.save_every <= 0:
            raise ValueError("save_every must be positive")

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        for key in (
            "train_path",
            "eval_path",
            "tokenizer_path",
            "output_dir",
            "cache_dir",
        ):
            result[key] = str(result[key])
        if result["init_checkpoint_path"] is not None:
            result["init_checkpoint_path"] = str(result["init_checkpoint_path"])
        return result
