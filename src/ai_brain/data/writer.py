from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_brain.data.generators import GeneratorName, generate_examples


def write_jsonl(path: Path, examples: Sequence[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="\n") as file:
        for example in examples:
            file.write(example.to_json_line())
            file.write("\n")


def generate_jsonl(
    *,
    output_path: Path,
    count: int,
    seed: int,
    task_types: Sequence[GeneratorName] | None = None,
) -> dict[str, Any]:
    examples = generate_examples(
        count=count,
        seed=seed,
        task_types=task_types,
    )

    write_jsonl(output_path, examples)

    return {
        "output_path": str(output_path),
        "count": count,
        "seed": seed,
        "task_types": list(task_types) if task_types is not None else "all",
    }
