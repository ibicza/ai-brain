from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from ai_brain.language.tokenizer.text_format import format_training_example


def iter_tokenizer_texts(paths: Iterable[Path]) -> Iterator[str]:
    for path in paths:
        yield from iter_tokenizer_texts_from_path(path)


def iter_tokenizer_texts_from_path(path: Path) -> Iterator[str]:
    if path.suffix.lower() == ".jsonl":
        yield from _iter_jsonl_examples(path)
        return

    yield path.read_text(encoding="utf-8")


def _iter_jsonl_examples(path: Path) -> Iterator[str]:
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue

            example = json.loads(stripped)
            if "prompt" in example and "answer" in example:
                yield format_training_example(example)
            else:
                yield json.dumps(example, ensure_ascii=False, sort_keys=True)
