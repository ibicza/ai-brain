"""Reproducible bilingual query data with a physically separated blind target file."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ai_brain.stage1.models import content_hash, utc_now
from ai_brain.stage2.models import SkillRecord
from ai_brain.stage2.registry import SkillRegistry

DATASET_SCHEMA_VERSION = 1
DEFAULT_SPLIT_COUNTS = {
    "train": 20_000,
    "validation": 2_000,
    "calibration": 2_000,
    "development": 4_000,
    "blind": 4_000,
}
EVALUATION_SLICES = (
    "ID",
    "LEXICAL_HOLDOUT",
    "TEMPLATE_HOLDOUT",
    "VARIABLE_PERMUTATION",
    "ORDER_HOLDOUT",
    "CROSS_LANGUAGE",
    "COMPOSED_OOD",
    "UNKNOWN",
    "AMBIGUOUS",
    "HARD_NEIGHBOR",
)


@dataclass(frozen=True)
class QueryDatasetManifest:
    schema_version: int
    seed: int
    split_counts: dict[str, int]
    languages: dict[str, int]
    query_kinds: dict[str, int]
    evaluation_slices: dict[str, int]
    family_counts: dict[str, int]
    skill_counts: dict[str, int]
    contingency_matrices: dict[str, dict[str, int]]
    files: dict[str, dict[str, Any]]
    blind_public_sha256: str
    blind_targets_sha256: str
    blind_frozen_at: str
    registry_hash: str
    model_visible_fields: tuple[str, ...] = ("text", "language")


def generate_query_dataset(
    registry: SkillRegistry,
    output_dir: Path,
    *,
    seed: int = 25_001,
    split_counts: dict[str, int] | None = None,
) -> QueryDatasetManifest:
    """Generate all splits and freeze blind labels before model selection."""
    counts = dict(DEFAULT_SPLIT_COUNTS if split_counts is None else split_counts)
    if set(counts) != set(DEFAULT_SPLIT_COUNTS) or any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in counts.values()
    ):
        raise ValueError("split_counts must contain five positive integer splits")
    skills = sorted(registry.active_records(), key=lambda item: item.skill_id)
    if len(skills) != 89:
        raise ValueError("M-25 query dataset requires the frozen 89-skill catalog")
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    used_text: set[str] = set()
    all_rows: list[dict[str, Any]] = []
    file_metadata: dict[str, dict[str, Any]] = {}

    for split_index, (split, count) in enumerate(counts.items()):
        rows = _generate_split(
            skills,
            split,
            count,
            rng=random.Random(rng.randrange(2**63) + split_index),
            used_text=used_text,
        )
        if split == "blind":
            public_rows = [_public_blind_row(row) for row in rows]
            target_rows = [_blind_target_row(row) for row in rows]
            public_path = output_dir / "blind.jsonl"
            target_path = output_dir / "blind_targets.hidden.jsonl"
            _write_jsonl(public_path, public_rows)
            _write_jsonl(target_path, target_rows)
            file_metadata["blind"] = _file_metadata(public_path, public_rows)
            file_metadata["blind_targets"] = _file_metadata(target_path, target_rows)
        else:
            path = output_dir / f"{split}.jsonl"
            _write_jsonl(path, rows)
            file_metadata[split] = _file_metadata(path, rows)
        all_rows.extend(rows)

    _validate_dataset(all_rows, skills, counts)
    matrices = _contingencies(all_rows)
    manifest = QueryDatasetManifest(
        schema_version=DATASET_SCHEMA_VERSION,
        seed=seed,
        split_counts=counts,
        languages=dict(Counter(row["language"] for row in all_rows)),
        query_kinds=dict(Counter(row["query_kind"] for row in all_rows)),
        evaluation_slices=dict(Counter(row["evaluation_slice"] for row in all_rows)),
        family_counts=dict(Counter(row["target_family"] for row in all_rows)),
        skill_counts=dict(
            Counter(
                row["target_skill_id"]
                for row in all_rows
                if row["target_skill_id"] is not None
            )
        ),
        contingency_matrices=matrices,
        files=file_metadata,
        blind_public_sha256=file_metadata["blind"]["sha256"],
        blind_targets_sha256=file_metadata["blind_targets"]["sha256"],
        blind_frozen_at=utc_now(),
        registry_hash=registry.manifest.registry_hash,
    )
    path = output_dir / "manifest.json"
    path.write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return manifest


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def verify_blind_freeze(output_dir: Path) -> None:
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    for name, filename in (
        ("blind_public_sha256", "blind.jsonl"),
        ("blind_targets_sha256", "blind_targets.hidden.jsonl"),
    ):
        actual = _sha256(output_dir / filename)
        if actual != manifest[name]:
            raise ValueError(f"Frozen blind artifact changed: {filename}")


def model_visible_text(row: dict[str, Any]) -> str:
    return f"{row['language']}\n{row['text']}"


def _generate_split(
    skills: list[SkillRecord],
    split: str,
    count: int,
    *,
    rng: random.Random,
    used_text: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    known_index = 0
    attempts = 0
    while len(rows) < count:
        attempts += 1
        if attempts > count * 100:
            raise RuntimeError(f"Could not create prompt-disjoint {split} split")
        index = len(rows)
        language = "ru" if (index + rng.randrange(2)) % 2 else "en"
        slice_name = EVALUATION_SLICES[(index * 7 + rng.randrange(10)) % 10]
        if slice_name == "UNKNOWN":
            kind = "unsupported"
            skill = None
            text = _negative_text(language, index, rng, ambiguous=False)
        elif slice_name == "AMBIGUOUS":
            kind = "ambiguous"
            skill = None
            text = _negative_text(language, index, rng, ambiguous=True)
        else:
            kind = "hard_neighbor" if slice_name == "HARD_NEIGHBOR" else "supported"
            skill = skills[
                (known_index * 37 + rng.randrange(len(skills))) % len(skills)
            ]
            known_index += 1
            text = _supported_text(skill, language, split, slice_name, index, rng)
        normalized = " ".join(text.casefold().split())
        if normalized in used_text:
            continue
        used_text.add(normalized)
        query_id = (
            f"query-{content_hash({'split': split, 'index': index, 'text': text})[:24]}"
        )
        rows.append(
            {
                "schema_version": DATASET_SCHEMA_VERSION,
                "query_id": query_id,
                "text": text,
                "language": language,
                "query_kind": kind,
                "evaluation_slice": slice_name,
                "target_skill_id": None if skill is None else skill.skill_id,
                "target_rule_id": None if skill is None else skill.rule_id,
                "target_specification_hash": (
                    None if skill is None else skill.specification_hash
                ),
                "target_family": "NONE" if skill is None else skill.semantic_family,
                "known": skill is not None,
                "ambiguous": kind == "ambiguous",
            }
        )
    rng.shuffle(rows)
    return rows


def _supported_text(
    skill: SkillRecord,
    language: str,
    split: str,
    slice_name: str,
    index: int,
    rng: random.Random,
) -> str:
    aliases = skill.aliases_ru if language == "ru" else skill.aliases_en
    examples = (
        skill.controlled_examples_ru
        if language == "ru"
        else skill.controlled_examples_en
    )
    surfaces = aliases + examples
    base = surfaces[(index + rng.randrange(len(surfaces))) % len(surfaces)]
    prefixes = {
        "en": (
            "Please carry out this request: ",
            "Apply the following state change: ",
            "I need this register operation: ",
            "Safely perform: ",
            "For the current state, ",
            "The requested effect is: ",
            "Execute only this operation: ",
            "Handle these registers as follows: ",
        ),
        "ru": (
            "Выполни этот запрос: ",
            "Примени следующее изменение состояния: ",
            "Нужна такая операция с регистрами: ",
            "Безопасно выполни: ",
            "Для текущего состояния: ",
            "Требуемый эффект: ",
            "Выполни только эту операцию: ",
            "Обработай регистры так: ",
        ),
    }
    suffixes = {
        "en": (
            " Keep every stated invariant.",
            " Respect the stated source order.",
            " Do not infer any extra operation.",
            " Use exactly the stated destination.",
            " Preserve the named unaffected registers.",
            " Stop at the stated condition.",
            " The register letters are significant.",
            " Apply no additional state change.",
        ),
        "ru": (
            " Соблюдай все указанные инварианты.",
            " Учитывай заданный порядок источников.",
            " Не добавляй других операций.",
            " Используй именно указанный приёмник.",
            " Сохрани названные неизменяемые регистры.",
            " Остановись по указанному условию.",
            " Буквы регистров имеют значение.",
            " Не вноси дополнительных изменений состояния.",
        ),
    }
    # Split selection changes surface families, never model-visible labels.
    split_offset = list(DEFAULT_SPLIT_COUNTS).index(split)
    prefix = prefixes[language][(index + split_offset + rng.randrange(8)) % 8]
    suffix = suffixes[language][(index * 3 + split_offset + rng.randrange(8)) % 8]
    if slice_name == "CROSS_LANGUAGE":
        prefix = prefixes[language][(index + 5) % 8]
    if slice_name == "HARD_NEIGHBOR":
        suffix += (
            " Distinguish each source and destination."
            if language == "en"
            else " Различай каждый источник и приёмник."
        )
    separators = (" ", "\n", " -- ", ": ")
    separator = separators[(index + rng.randrange(4)) % 4]
    return f"{prefix.rstrip()}{separator}{base}{suffix}"


def _negative_text(
    language: str, index: int, rng: random.Random, *, ambiguous: bool
) -> str:
    registers = "ABCD"
    first = registers[(index + rng.randrange(4)) % 4]
    second = registers[(index * 3 + rng.randrange(4)) % 4]
    if second == first:
        second = registers[(registers.index(first) + 1) % 4]
    if ambiguous:
        templates = {
            "en": (
                "Move every item from {a}; choose the destination.",
                "Transfer {a} into it and leave the others unchanged.",
                "Clear or transfer {a} to {b}; the intended action is unspecified.",
                "Move {a} and {b} but the destination is missing.",
            ),
            "ru": (
                "Перенеси все элементы из {a}; приёмник не указан.",
                "Перемести {a} туда и не меняй остальные регистры.",
                "Очисти или перенеси {a} в {b}; нужное действие не уточнено.",
                "Перенеси {a} и {b}, но приёмник не указан.",
            ),
        }
    else:
        templates = {
            "en": (
                "Sort the values in {a} and store them in {b}.",
                "Multiply {a} by {b}.",
                "Copy {a} into {b} without clearing {a}.",
                "Swap registers {a} and {b}.",
                "Compare {a} and {b} and keep the larger value.",
                "Use register E as a source and move it into {b}.",
                "Divide {a} by {b} using a loop.",
            ),
            "ru": (
                "Отсортируй значения в {a} и сохрани их в {b}.",
                "Умножь {a} на {b}.",
                "Скопируй {a} в {b}, не очищая {a}.",
                "Поменяй местами регистры {a} и {b}.",
                "Сравни {a} и {b} и оставь большее значение.",
                "Используй регистр E как источник и перенеси его в {b}.",
                "Раздели {a} на {b} с помощью цикла.",
            ),
        }
    values = templates[language]
    text = values[(index + rng.randrange(len(values))) % len(values)].format(
        a=first, b=second
    )
    prefixes = {
        "en": (
            "Request: ",
            "For these registers: ",
            "Operator note: ",
            "Please evaluate: ",
            "Before dispatch, consider: ",
            "The user asks: ",
            "Proposed operation: ",
            "Current instruction: ",
        ),
        "ru": (
            "Запрос: ",
            "Для этих регистров: ",
            "Примечание оператора: ",
            "Проверь: ",
            "До запуска рассмотри: ",
            "Пользователь просит: ",
            "Предлагаемая операция: ",
            "Текущая инструкция: ",
        ),
    }
    qualifiers = {
        "en": (
            " Please decide safely.",
            " No exact structural rule was supplied.",
            " Ask before choosing a skill.",
            " Do not guess the missing detail.",
            " Treat register letters literally.",
            " This request may be outside the installed catalog.",
        ),
        "ru": (
            " Прими безопасное решение.",
            " Точное структурное правило не задано.",
            " Уточни запрос до выбора навыка.",
            " Не угадывай отсутствующую деталь.",
            " Воспринимай буквы регистров буквально.",
            " Запрос может быть вне установленного каталога.",
        ),
    }
    prefix = prefixes[language][(index * 3 + rng.randrange(8)) % 8]
    separator = ("", " ", "\n", " -- ")[(index + rng.randrange(4)) % 4]
    qualifier = qualifiers[language][(index * 5 + rng.randrange(6)) % 6]
    return f"{prefix.rstrip()}{separator}{text}{qualifier}"


def _public_blind_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": row["schema_version"],
        "query_id": row["query_id"],
        "text": row["text"],
        "language": row["language"],
    }


def _blind_target_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "query_id",
            "query_kind",
            "evaluation_slice",
            "target_skill_id",
            "target_rule_id",
            "target_specification_hash",
            "target_family",
            "known",
            "ambiguous",
        )
    }


def _validate_dataset(
    rows: list[dict[str, Any]], skills: list[SkillRecord], counts: dict[str, int]
) -> None:
    if len(rows) != sum(counts.values()):
        raise ValueError("dataset row count mismatch")
    texts = [" ".join(row["text"].casefold().split()) for row in rows]
    if len(texts) != len(set(texts)):
        raise ValueError("query text intersects across dataset splits")
    forbidden = {item.skill_id for item in skills} | {item.rule_id for item in skills}
    forbidden.update(counts)
    for row in rows:
        visible = model_visible_text(row)
        if any(token in visible for token in forbidden):
            raise ValueError("model-visible text leaks an ID or split name")


def _contingencies(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    dimensions = (
        ("language_x_kind", "language", "query_kind"),
        ("language_x_slice", "language", "evaluation_slice"),
        ("family_x_language", "target_family", "language"),
        ("family_x_slice", "target_family", "evaluation_slice"),
    )
    result: dict[str, dict[str, int]] = {}
    for name, first, second in dimensions:
        counter: defaultdict[str, int] = defaultdict(int)
        for row in rows:
            counter[f"{row[first]} | {row[second]}"] += 1
        result[name] = dict(sorted(counter.items()))
    return result


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    path.write_text(content, encoding="utf-8")


def _file_metadata(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"path": path.name, "count": len(rows), "sha256": _sha256(path)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
