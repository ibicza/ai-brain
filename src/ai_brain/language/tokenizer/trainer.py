from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.io import iter_tokenizer_texts


def train_tokenizer(
    *,
    input_paths: Sequence[Path],
    output_path: Path,
    vocab_size: int = 8192,
    min_frequency: int = 2,
) -> dict[str, Any]:
    if not input_paths:
        raise ValueError("At least one input path is required")

    tokenizer = ByteLevelBpeTokenizer.train(
        iter_tokenizer_texts(input_paths),
        vocab_size=vocab_size,
        min_frequency=min_frequency,
    )
    tokenizer.save(output_path)

    return {
        "output_path": str(output_path),
        "input_paths": [str(path) for path in input_paths],
        "requested_vocab_size": vocab_size,
        "min_frequency": min_frequency,
        **tokenizer.info(),
    }
