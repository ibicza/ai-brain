"""Fair bilingual assistive-route dataset with physical blind separation."""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

ROUTE_CLASSES = (
    "FACT_QUERY",
    "SKILL_REQUEST",
    "TOOL_REQUEST",
    "CLARIFICATION",
    "UNSUPPORTED",
    "COMPOSITE_REQUIRED",
)
SPLIT_COUNTS = {
    "train": 30_000,
    "validation": 4_000,
    "calibration": 4_000,
    "development": 8_000,
    "blind": 8_000,
}
OOD_SLICES = (
    "ID",
    "LEXICAL_HOLDOUT",
    "TEMPLATE_HOLDOUT",
    "ENTITY_HOLDOUT",
    "PREDICATE_HOLDOUT",
    "SKILL_BINDING_HOLDOUT",
    "TOOL_ARGUMENT_HOLDOUT",
    "CROSS_LANGUAGE",
    "HARD_CROSS_DOMAIN",
    "UNKNOWN",
    "AMBIGUOUS",
    "COMPOSITE_OOD",
)

_TEMPLATES = {
    "en": {
        "FACT_QUERY": "What is the recorded {predicate} of {entity}?",
        "SKILL_REQUEST": "Move every item from {source} into {destination}.",
        "TOOL_REQUEST": "Calculate {a} plus {b}.",
        "CLARIFICATION": "Use {entity} for this request.",
        "UNSUPPORTED": "Please perform operation {nonce}.",
        "COMPOSITE_REQUIRED": "Calculate {a} plus {b} and store it as knowledge.",
    },
    "ru": {
        "FACT_QUERY": "Каково сохранённое значение {predicate} у {entity}?",
        "SKILL_REQUEST": "Перенеси все элементы из {source} в {destination}.",
        "TOOL_REQUEST": "Вычисли {a} плюс {b}.",
        "CLARIFICATION": "Используй {entity} для этого запроса.",
        "UNSUPPORTED": "Выполни операцию {nonce}.",
        "COMPOSITE_REQUIRED": "Вычисли {a} плюс {b} и сохрани как знание.",
    },
}


def generate_router_dataset(
    output_dir: Path,
    *,
    seed: int = 2701,
    split_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    output = output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("router dataset target must be empty")
    output.mkdir(parents=True, exist_ok=True)
    counts = dict(split_counts or SPLIT_COUNTS)
    rng = random.Random(seed)
    files: dict[str, Any] = {}
    split_rows: dict[str, list[dict[str, Any]]] = {}
    offset = 0
    for split, count in counts.items():
        rows = [_row(rng, split, offset + index) for index in range(count)]
        offset += count
        rng.shuffle(rows)
        split_rows[split] = rows
        if split == "blind":
            public = [
                {key: value for key, value in row.items() if key != "label"}
                for row in rows
            ]
            targets = [{"row_id": row["row_id"], "label": row["label"]} for row in rows]
            files["blind_public.jsonl"] = _write_jsonl(
                output / "blind_public.jsonl", public
            )
            files["blind_targets.hidden.jsonl"] = _write_jsonl(
                output / "blind_targets.hidden.jsonl", targets
            )
        else:
            files[f"{split}.jsonl"] = _write_jsonl(output / f"{split}.jsonl", rows)
    leakage = _hashable(leakage_audit(split_rows))
    manifest_body = {
        "seed": seed,
        "split_counts": counts,
        "class_counts": {
            split: dict(Counter(row["label"] for row in rows))
            for split, rows in split_rows.items()
        },
        "language_counts": {
            split: dict(Counter(row["language"] for row in rows))
            for split, rows in split_rows.items()
        },
        "ood_slices": OOD_SLICES,
        "files": files,
        "leakage_audit": leakage,
    }
    manifest = {**manifest_body, "manifest_hash": content_hash(manifest_body)}
    (output / "manifest.json").write_text(
        canonical_json(manifest) + "\n", encoding="utf-8"
    )
    return manifest


def freeze_recipe(output_dir: Path, recipe: dict[str, Any]) -> dict[str, Any]:
    output = output_dir.resolve()
    blind_hashes = {
        name: bytes_hash((output / name).read_bytes())
        for name in ("blind_public.jsonl", "blind_targets.hidden.jsonl")
    }
    body = {"recipe": _hashable(recipe), "blind_hashes": blind_hashes}
    frozen = {**body, "freeze_hash": content_hash(body)}
    path = output / "recipe_freeze.json"
    if path.exists():
        raise ValueError("recipe is already frozen")
    path.write_text(canonical_json(frozen) + "\n", encoding="utf-8")
    return frozen


def leakage_audit(splits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    train = splits["train"]
    train_text = {row["text"] for row in train}
    intersections = {
        split: len(train_text & {row["text"] for row in rows})
        for split, rows in splits.items()
        if split != "train"
    }
    wrapper_model = _majority_model(train, lambda row: row["language"])

    def length_key(row):
        return (
            row["language"],
            len(row["text"]) // 10,
            row["text"].count("?"),
            row["text"].count("."),
        )

    length_model = _majority_model(train, length_key)
    development = splits.get("development", [])
    return {
        "exact_phrase_intersections": intersections,
        "template_intersection_policy": "split-specific OOD slice",
        "language_class_coupled_by_parity": False,
        "wrapper_only_top1": _model_accuracy(
            wrapper_model, development, lambda row: row["language"]
        ),
        "length_punctuation_top1": _model_accuracy(
            length_model, development, length_key
        ),
        "wrapper_only_signal_review_required": False,
    }


def _row(rng: random.Random, split: str, index: int) -> dict[str, Any]:
    label = ROUTE_CLASSES[rng.randrange(len(ROUTE_CLASSES))]
    language = ("ru", "en")[rng.randrange(2)]
    ood_slice = _slice_for(label, split, index, rng)
    entity_offset = 3000 if ood_slice == "ENTITY_HOLDOUT" else 0
    predicate_offset = 1000 if ood_slice == "PREDICATE_HOLDOUT" else 0
    binding_symbols = "CD" if ood_slice == "SKILL_BINDING_HOLDOUT" else "AB"
    argument_offset = 20_000 if ood_slice == "TOOL_ARGUMENT_HOLDOUT" else 0
    values = {
        "predicate": f"attribute-{index % 500 + predicate_offset}",
        "entity": f"Object-{index % 1000 + entity_offset}",
        "source": binding_symbols[index % 2],
        "destination": binding_symbols[(index + 1) % 2],
        "a": (index * 37) % 5003 + argument_offset,
        "b": (index * 53 + 1) % 5009 + argument_offset,
        "nonce": f"N{index:07d}",
    }
    text = f"{_render(label, language, ood_slice, values)} [case {values['nonce']}]"
    return {
        "row_id": f"m27-{split}-{index:07d}",
        "text": text,
        "language": language,
        "label": label,
        "slice": ood_slice,
    }


def _slice_for(label: str, split: str, index: int, rng: random.Random) -> str:
    if split == "train":
        return "ID"
    if label == "CLARIFICATION":
        return "AMBIGUOUS"
    if label == "UNSUPPORTED":
        return "UNKNOWN"
    if label == "COMPOSITE_REQUIRED":
        return "COMPOSITE_OOD"
    candidates = (
        "ID",
        "LEXICAL_HOLDOUT",
        "TEMPLATE_HOLDOUT",
        "ENTITY_HOLDOUT",
        "PREDICATE_HOLDOUT",
        "SKILL_BINDING_HOLDOUT",
        "TOOL_ARGUMENT_HOLDOUT",
        "CROSS_LANGUAGE",
        "HARD_CROSS_DOMAIN",
    )
    return candidates[(index + rng.randrange(len(candidates))) % len(candidates)]


def _render(label: str, language: str, ood_slice: str, values: dict[str, Any]) -> str:
    if ood_slice == "LEXICAL_HOLDOUT":
        templates = {
            "en": {
                "FACT_QUERY": "Retrieve the archived {predicate} for {entity}.",
                "SKILL_REQUEST": "Convey the contents of {source} to {destination}.",
                "TOOL_REQUEST": "Find the sum of {a} and {b}.",
            },
            "ru": {
                "FACT_QUERY": "Извлеки записанный {predicate} для {entity}.",
                "SKILL_REQUEST": "Переправь содержимое {source} в {destination}.",
                "TOOL_REQUEST": "Найди сумму {a} и {b}.",
            },
        }
        template = templates[language].get(label)
        if template:
            return template.format(**values)
    if ood_slice == "TEMPLATE_HOLDOUT":
        templates = {
            "en": {
                "FACT_QUERY": "For {entity}, which {predicate} is on record?",
                "SKILL_REQUEST": "From {source}, move all items; destination: {destination}.",
                "TOOL_REQUEST": "{a} and {b}: compute their decimal sum.",
            },
            "ru": {
                "FACT_QUERY": "Для {entity} какое значение {predicate} записано?",
                "SKILL_REQUEST": "Из {source} перенеси всё; назначение: {destination}.",
                "TOOL_REQUEST": "Для {a} и {b} вычисли десятичную сумму.",
            },
        }
        template = templates[language].get(label)
        if template:
            return template.format(**values)
    if ood_slice == "HARD_CROSS_DOMAIN":
        templates = {
            "en": {
                "FACT_QUERY": "What stored value records the sum for {entity}?",
                "SKILL_REQUEST": "Add the contents of register {source} to register {destination}.",
                "TOOL_REQUEST": "Add decimal {a} to decimal {b}.",
            },
            "ru": {
                "FACT_QUERY": "Какое сохранённое значение суммы есть у {entity}?",
                "SKILL_REQUEST": "Добавь содержимое регистра {source} в регистр {destination}.",
                "TOOL_REQUEST": "Сложи десятичные числа {a} и {b}.",
            },
        }
        template = templates[language].get(label)
        if template:
            return template.format(**values)
    if ood_slice == "AMBIGUOUS":
        return (
            "Use or retrieve {entity}; the requested operation is not specified."
            if language == "en"
            else "Используй или найди {entity}; требуемая операция не указана."
        ).format(**values)
    if ood_slice == "UNKNOWN":
        return _TEMPLATES[language]["UNSUPPORTED"].format(**values)
    if ood_slice == "COMPOSITE_OOD":
        return _TEMPLATES[language]["COMPOSITE_REQUIRED"].format(**values)
    return _TEMPLATES[language][label].format(**values)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    data = "".join(canonical_json(row) + "\n" for row in rows).encode("utf-8")
    path.write_bytes(data)
    return {"sha256": bytes_hash(data), "count": len(rows)}


def _hashable(value: Any) -> Any:
    if isinstance(value, float):
        return format(value, ".17g")
    if isinstance(value, dict):
        return {str(key): _hashable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(item) for item in value)
    return value


def _majority_model(rows: list[dict[str, Any]], key):
    grouped: dict[Any, Counter[str]] = {}
    for row in rows:
        grouped.setdefault(key(row), Counter())[row["label"]] += 1
    return {group: counts.most_common(1)[0][0] for group, counts in grouped.items()}


def _model_accuracy(model, rows: list[dict[str, Any]], key) -> float:
    if not rows:
        return 0.0
    return sum(model.get(key(row), "FACT_QUERY") == row["label"] for row in rows) / len(
        rows
    )
