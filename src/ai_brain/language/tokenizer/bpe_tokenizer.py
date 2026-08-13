from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
from tokenizers.pre_tokenizers import ByteLevel

from ai_brain.language.tokenizer.special_tokens import SPECIAL_TOKENS, UNK_TOKEN


class ByteLevelBpeTokenizer:
    def __init__(self, tokenizer: Tokenizer) -> None:
        self._tokenizer = tokenizer

    @classmethod
    def train(
        cls,
        texts: Iterable[str],
        *,
        vocab_size: int = 8192,
        min_frequency: int = 2,
    ) -> ByteLevelBpeTokenizer:
        tokenizer = Tokenizer(models.BPE(unk_token=UNK_TOKEN, byte_fallback=True))
        tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
        tokenizer.decoder = decoders.ByteLevel()

        trainer = trainers.BpeTrainer(
            vocab_size=vocab_size,
            min_frequency=min_frequency,
            special_tokens=list(SPECIAL_TOKENS),
            initial_alphabet=ByteLevel.alphabet(),
        )
        tokenizer.train_from_iterator(texts, trainer=trainer)

        trained = cls(tokenizer)
        trained.validate_special_token_ids()
        return trained

    @classmethod
    def load(cls, path: Path) -> ByteLevelBpeTokenizer:
        tokenizer = Tokenizer.from_file(str(path))
        loaded = cls(tokenizer)
        loaded.validate_special_token_ids()
        return loaded

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._tokenizer.save(str(path))

    def encode(self, text: str) -> list[int]:
        return self._tokenizer.encode(text).ids

    def decode(self, ids: Iterable[int], *, skip_special_tokens: bool = False) -> str:
        return self._tokenizer.decode(
            list(ids),
            skip_special_tokens=skip_special_tokens,
        )

    def token_to_id(self, token: str) -> int | None:
        return self._tokenizer.token_to_id(token)

    def id_to_token(self, token_id: int) -> str | None:
        return self._tokenizer.id_to_token(token_id)

    @property
    def vocab_size(self) -> int:
        return self._tokenizer.get_vocab_size()

    def validate_special_token_ids(self) -> None:
        for expected_id, token in enumerate(SPECIAL_TOKENS):
            actual_id = self.token_to_id(token)
            if actual_id != expected_id:
                raise ValueError(
                    f"Special token {token!r} has id {actual_id}, "
                    f"expected {expected_id}"
                )

    def info(self) -> dict[str, Any]:
        return {
            "type": "byte_level_bpe",
            "vocab_size": self.vocab_size,
            "special_token_ids": {
                token: self.token_to_id(token) for token in SPECIAL_TOKENS
            },
            "byte_fallback": True,
        }
