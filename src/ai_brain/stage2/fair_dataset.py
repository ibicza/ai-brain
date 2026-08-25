"""Leakage-controlled M-25.1 bilingual skill-retrieval benchmark."""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ai_brain.stage1.models import content_hash, utc_now
from ai_brain.stage1.specifications import infer_family, specification_from_dict
from ai_brain.stage2.models import SkillRecord
from ai_brain.stage2.registry import SkillRegistry

FAIR_DATASET_SCHEMA_VERSION = 2
DEFAULT_FAIR_SPLIT_COUNTS = {
    "train": 24_000,
    "validation": 3_000,
    "calibration": 3_000,
    "development": 6_000,
    "blind": 6_000,
}
EVALUATION_SLICES = (
    "ID",
    "CATALOG_LEXICAL_HOLDOUT",
    "TRUE_LEXICAL_OOD",
    "TEMPLATE_HOLDOUT",
    "VARIABLE_PERMUTATION",
    "ZERO_QUERY_SKILL",
    "ORDER_HOLDOUT",
    "CROSS_LANGUAGE_TRANSFER",
    "COMPOSED_OOD",
    "UNKNOWN",
    "AMBIGUOUS",
    "HARD_NEIGHBOR",
)
TRAIN_QUERY_TEMPLATES = (
    "train.direct",
    "train.effect_first",
    "train.context_first",
    "train.invariants_first",
    "train.request_form",
    "train.compact",
)
TEMPLATE_HOLDOUT = (
    "holdout.question",
    "holdout.stop_first",
    "holdout.two_sentence",
    "holdout.parenthetical",
)
ORDER_HOLDOUT_TEMPLATES = ("holdout.reverse_clauses", "holdout.preserve_first")
NEUTRAL_WRAPPERS = {
    "en": (
        "Current task",
        "For this state",
        "Requested change",
        "Instruction",
        "Please process",
        "Operator request",
    ),
    "ru": (
        "Текущая задача",
        "Для этого состояния",
        "Требуемое изменение",
        "Инструкция",
        "Выполни запрос",
        "Запрос оператора",
    ),
}
NEUTRAL_SUFFIXES = {
    "en": (
        "Use the register letters literally",
        "Apply this to the current values",
        "Follow the stated role names",
        "Keep the request scope unchanged",
        "Process the named registers",
        "Use the present register state",
        "Treat each named role distinctly",
        "Apply only the described state change",
    ),
    "ru": (
        "Учитывай буквы регистров буквально",
        "Примени это к текущим значениям",
        "Следуй указанным именам ролей",
        "Не меняй область запроса",
        "Обработай названные регистры",
        "Используй текущее состояние регистров",
        "Различай каждую названную роль",
        "Примени только описанное изменение состояния",
    ),
}
TRAIN_QUERY_LEXICON = {
    "en": {
        "move": ("relocate", "route", "send"),
        "clear": ("discard", "remove", "empty"),
        "stop": ("finish", "end", "halt"),
        "preserve": ("maintain", "keep intact", "retain the state of"),
    },
    "ru": {
        "move": ("направь", "передай", "отправь"),
        "clear": ("удали", "опустоши", "убери"),
        "stop": ("заверши", "прекрати", "закончи"),
        "preserve": ("сохрани", "оставь нетронутым", "поддерживай состояние"),
    },
}
CATALOG_ALIAS_LEXICON = {
    "en": {
        "move": ("move", "convey"),
        "clear": ("clear", "purge"),
        "stop": ("stop", "conclude"),
        "preserve": ("leave unchanged", "retain untouched"),
    },
    "ru": {
        "move": ("перенеси", "переправь"),
        "clear": ("очисти", "ликвидируй"),
        "stop": ("остановись", "закончи операцию"),
        "preserve": ("не изменяй", "сбереги как есть"),
    },
}
LEXICAL_TRUE_OOD = {
    "en": {
        "move": ("funnel", "channel onward"),
        "clear": ("annul the contents of", "void"),
        "stop": ("cease processing", "terminate now"),
        "preserve": ("freeze the contents of", "hold invariant"),
    },
    "ru": {
        "move": ("транспортируй", "перелей дальше"),
        "clear": ("аннулируй содержимое", "обнули содержимое"),
        "stop": ("прекрати обработку", "финализируй"),
        "preserve": ("зафиксируй содержимое", "удержи инвариантным"),
    },
}
UNKNOWN_OPERATION_LEXICON = {
    "en": ("copy", "swap", "sort", "compare", "multiply", "divide", "condition"),
    "ru": (
        "скопируй",
        "поменяй местами",
        "отсортируй",
        "сравни",
        "умножь",
        "раздели",
        "если",
    ),
}
AMBIGUITY_TEMPLATES = ("missing_destination", "missing_source", "obscured_role")
CONTROLLED_CANONICAL = {
    "en": ("move", "clear", "stop"),
    "ru": ("перенеси", "очисти", "остановись"),
}
CONTROLLED_EXTENDED = {
    "en": ("convey", "purge", "conclude"),
    "ru": ("переправь", "ликвидируй", "закончи операцию"),
}


@dataclass(frozen=True)
class FairQueryDatasetManifest:
    schema_version: int
    seed: int
    split_counts: dict[str, int]
    languages: dict[str, int]
    query_kinds: dict[str, int]
    evaluation_slices: dict[str, int]
    family_counts: dict[str, int]
    skill_counts: dict[str, int]
    zero_query_skill_ids: tuple[str, ...]
    variable_holdout_skill_ids: tuple[str, ...]
    ru_train_only_skill_ids: tuple[str, ...]
    en_train_only_skill_ids: tuple[str, ...]
    surface_inventory_hashes: dict[str, str]
    query_surface_inventory_hash: str
    ood_split_definition_hash: str
    prompt_intersections: dict[str, int]
    files: dict[str, dict[str, Any]]
    blind_public_sha256: str
    blind_targets_sha256: str
    blind_frozen_at: str
    registry_hash: str
    model_visible_fields: tuple[str, ...] = ("text", "language")


def generate_fair_query_dataset(
    registry: SkillRegistry,
    output_dir: Path,
    *,
    seed: int = 25_101,
    split_counts: dict[str, int] | None = None,
) -> FairQueryDatasetManifest:
    counts = dict(DEFAULT_FAIR_SPLIT_COUNTS if split_counts is None else split_counts)
    if set(counts) != set(DEFAULT_FAIR_SPLIT_COUNTS) or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 24
        for value in counts.values()
    ):
        raise ValueError("fair split counts must contain five integers >= 24")
    skills = sorted(registry.active_records(), key=lambda item: item.skill_id)
    if len(skills) != 89:
        raise ValueError("M-25.1 requires the frozen 89-skill catalog")
    metadata = {item.skill_id: _skill_fields(item) for item in skills}
    zero_ids = _balanced_holdout(skills, 18, offset=0)
    remaining = [item for item in skills if item.skill_id not in zero_ids]
    variable_ids = tuple(item.skill_id for item in remaining[::11][:8])
    remaining = [item for item in remaining if item.skill_id not in variable_ids]
    ru_only = tuple(item.skill_id for item in remaining[::9][:6])
    en_only = tuple(
        item.skill_id for item in remaining if item.skill_id not in ru_only
    )[::9][:6]
    neighbor_map = _build_neighbor_map(skills, metadata)

    output_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    rows_by_split: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, dict[str, Any]] = {}
    for split_index, (split, count) in enumerate(counts.items()):
        rows = _generate_split(
            split,
            count,
            skills,
            metadata,
            neighbor_map,
            zero_ids=set(zero_ids),
            variable_ids=set(variable_ids),
            ru_only=set(ru_only),
            en_only=set(en_only),
            used=used,
            rng=random.Random(seed + split_index * 10_007),
        )
        rows_by_split[split] = rows
        if split == "blind":
            public = [_public_blind_row(row) for row in rows]
            targets = [_blind_target_row(row) for row in rows]
            public_path = output_dir / "blind_public.jsonl"
            target_path = output_dir / "blind_targets.hidden.jsonl"
            _write_jsonl(public_path, public)
            _write_jsonl(target_path, targets)
            files["blind_public"] = _file_metadata(public_path, public)
            files["blind_targets"] = _file_metadata(target_path, targets)
        else:
            path = output_dir / f"{split}.jsonl"
            _write_jsonl(path, rows)
            files[split] = _file_metadata(path, rows)

    _validate_fair_dataset(
        rows_by_split,
        skills,
        zero_ids=set(zero_ids),
        variable_ids=set(variable_ids),
        ru_only=set(ru_only),
        en_only=set(en_only),
    )
    all_rows = list(itertools.chain.from_iterable(rows_by_split.values()))
    inventory = surface_inventory()
    inventory_hashes = {key: content_hash(value) for key, value in inventory.items()}
    prompt_intersections = _prompt_intersections(rows_by_split)
    manifest = FairQueryDatasetManifest(
        schema_version=FAIR_DATASET_SCHEMA_VERSION,
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
        zero_query_skill_ids=zero_ids,
        variable_holdout_skill_ids=variable_ids,
        ru_train_only_skill_ids=ru_only,
        en_train_only_skill_ids=en_only,
        surface_inventory_hashes=inventory_hashes,
        query_surface_inventory_hash=content_hash(inventory),
        ood_split_definition_hash=content_hash(
            {
                "slices": EVALUATION_SLICES,
                "zero": zero_ids,
                "variable": variable_ids,
                "ru_only": ru_only,
                "en_only": en_only,
            }
        ),
        prompt_intersections=prompt_intersections,
        files=files,
        blind_public_sha256=files["blind_public"]["sha256"],
        blind_targets_sha256=files["blind_targets"]["sha256"],
        blind_frozen_at=utc_now(),
        registry_hash=registry.manifest.registry_hash,
    )
    (output_dir / "surface_inventories.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return manifest


def surface_inventory() -> dict[str, Any]:
    return {
        "TRAIN_QUERY_LEXICON": TRAIN_QUERY_LEXICON,
        "TRAIN_QUERY_TEMPLATES": TRAIN_QUERY_TEMPLATES,
        "CATALOG_ALIAS_LEXICON": CATALOG_ALIAS_LEXICON,
        "CATALOG_EXAMPLE_TEMPLATES": ("catalog.canonical", "catalog.extended"),
        "LEXICAL_CATALOG_HOLDOUT": CATALOG_ALIAS_LEXICON,
        "LEXICAL_TRUE_OOD": LEXICAL_TRUE_OOD,
        "TEMPLATE_HOLDOUT": TEMPLATE_HOLDOUT,
        "CONTROLLED_CANONICAL": CONTROLLED_CANONICAL,
        "CONTROLLED_EXTENDED": CONTROLLED_EXTENDED,
        "UNKNOWN_OPERATION_LEXICON": UNKNOWN_OPERATION_LEXICON,
        "AMBIGUITY_TEMPLATES": AMBIGUITY_TEMPLATES,
        "NEUTRAL_WRAPPERS": NEUTRAL_WRAPPERS,
        "NEUTRAL_SUFFIXES": NEUTRAL_SUFFIXES,
    }


def verify_fair_blind_freeze(output_dir: Path) -> None:
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    for key, filename in (
        ("blind_public_sha256", "blind_public.jsonl"),
        ("blind_targets_sha256", "blind_targets.hidden.jsonl"),
    ):
        if _sha256(output_dir / filename) != manifest[key]:
            raise ValueError(f"Frozen blind artifact changed: {filename}")


def load_fair_blind(output_dir: Path) -> list[dict[str, Any]]:
    public = _load_jsonl(output_dir / "blind_public.jsonl")
    targets = {
        row["query_id"]: row
        for row in _load_jsonl(output_dir / "blind_targets.hidden.jsonl")
    }
    return [{**row, **targets[row["query_id"]]} for row in public]


def _generate_split(
    split: str,
    count: int,
    skills: list[SkillRecord],
    metadata: dict[str, dict[str, Any]],
    neighbor_map: dict[str, tuple[str, str]],
    *,
    zero_ids: set[str],
    variable_ids: set[str],
    ru_only: set[str],
    en_only: set[str],
    used: set[str],
    rng: random.Random,
) -> list[dict[str, Any]]:
    by_id = {item.skill_id: item for item in skills}
    ordinary = [
        item
        for item in skills
        if item.skill_id not in zero_ids and item.skill_id not in variable_ids
    ]
    zero = [item for item in skills if item.skill_id in zero_ids]
    variable = [item for item in skills if item.skill_id in variable_ids]
    rows: list[dict[str, Any]] = []
    attempts = 0
    while len(rows) < count:
        attempts += 1
        if attempts > count * 500:
            raise RuntimeError(
                f"could not create disjoint fair split {split}: "
                f"rows={len(rows)}, slice={_slice_for(split, len(rows))}"
            )
        index = len(rows)
        slice_name = _slice_for(split, index)
        language = ("ru", "en")[(index + rng.randrange(2)) % 2]
        skill: SkillRecord | None
        pair_id = None
        neighbor_id = None
        changed_field = None
        counterfactual_text = None
        if slice_name in {"UNKNOWN", "AMBIGUOUS"}:
            skill = None
            text, template_id, lexical_family, unknown_family = _negative_surface(
                language, slice_name, rng
            )
            query_kind = "ambiguous" if slice_name == "AMBIGUOUS" else "unsupported"
        else:
            pool = (
                zero
                if slice_name == "ZERO_QUERY_SKILL"
                else variable
                if slice_name == "VARIABLE_PERMUTATION"
                else ordinary
            )
            skill = pool[(index * 37 + rng.randrange(len(pool))) % len(pool)]
            if split == "train":
                if skill.skill_id in ru_only:
                    language = "ru"
                elif skill.skill_id in en_only:
                    language = "en"
            elif slice_name == "CROSS_LANGUAGE_TRANSFER":
                cross_pool = [
                    item for item in ordinary if item.skill_id in ru_only | en_only
                ]
                skill = cross_pool[
                    (index + rng.randrange(len(cross_pool))) % len(cross_pool)
                ]
                language = "en" if skill.skill_id in ru_only else "ru"
            if slice_name == "HARD_NEIGHBOR":
                pool = [
                    item
                    for item in pool
                    if item.skill_id in neighbor_map
                    and (
                        split != "train"
                        or neighbor_map[item.skill_id][1] not in zero_ids | variable_ids
                    )
                ]
                skill = pool[(index * 37 + rng.randrange(len(pool))) % len(pool)]
                changed_field, neighbor_id = neighbor_map[skill.skill_id]
                if index % 2:
                    skill, neighbor_id = by_id[neighbor_id], skill.skill_id
                pair_id = f"pair-{split}-{index // 2:06d}"
                if split == "train":
                    if skill.skill_id in ru_only:
                        language = "ru"
                    elif skill.skill_id in en_only:
                        language = "en"
            surface_seed = rng.randrange(2**63)
            text, template_id, lexical_family = _known_surface(
                metadata[skill.skill_id],
                language,
                split,
                slice_name,
                index,
                random.Random(surface_seed),
            )
            if neighbor_id is not None:
                counterfactual_text, _, _ = _known_surface(
                    metadata[neighbor_id],
                    language,
                    split,
                    slice_name,
                    index,
                    random.Random(surface_seed),
                )
                counterfactual_normalized = _normalize(counterfactual_text)
                if counterfactual_normalized in used:
                    continue
                used.add(counterfactual_normalized)
            query_kind = (
                "hard_neighbor" if slice_name == "HARD_NEIGHBOR" else "supported"
            )
            unknown_family = None
        normalized = _normalize(text)
        if normalized in used:
            continue
        used.add(normalized)
        row = {
            "schema_version": FAIR_DATASET_SCHEMA_VERSION,
            "query_id": f"query-{content_hash({'split': split, 'text': text})[:24]}",
            "text": text,
            "language": language,
            "query_kind": query_kind,
            "evaluation_slice": slice_name,
            "template_id": template_id,
            "lexical_family": lexical_family,
            "target_skill_id": skill.skill_id if skill else None,
            "target_rule_id": skill.rule_id if skill else None,
            "target_family": skill.semantic_family if skill else "NONE",
            "known": skill is not None,
            "ambiguous": query_kind == "ambiguous",
            "unknown_family": unknown_family,
            "neighbor_skill_id": neighbor_id,
            "changed_field": changed_field,
            "query_pair_id": pair_id,
            "counterfactual_text": counterfactual_text,
            "counterfactual_target_skill_id": neighbor_id,
        }
        rows.append(row)
    rng.shuffle(rows)
    return rows


def _slice_for(split: str, index: int) -> str:
    if split == "train":
        cycle = (
            ("ID",) * 14
            + ("HARD_NEIGHBOR",) * 2
            + (
                "UNKNOWN",
                "AMBIGUOUS",
            )
        )
        return cycle[index % len(cycle)]
    if split in {"validation", "calibration"}:
        return ("ID", "ID", "HARD_NEIGHBOR", "UNKNOWN", "AMBIGUOUS")[index % 5]
    if split == "development":
        development_slices = tuple(
            item for item in EVALUATION_SLICES if item != "TRUE_LEXICAL_OOD"
        )
        return development_slices[index % len(development_slices)]
    return EVALUATION_SLICES[index % len(EVALUATION_SLICES)]


def _known_surface(
    fields: dict[str, Any],
    language: str,
    split: str,
    slice_name: str,
    index: int,
    rng: random.Random,
) -> tuple[str, str, str]:
    if slice_name in {"CATALOG_LEXICAL_HOLDOUT"}:
        lexicon = CATALOG_ALIAS_LEXICON[language]
        lexical_family = "catalog_holdout"
    elif slice_name == "TRUE_LEXICAL_OOD" or (
        slice_name == "COMPOSED_OOD" and split == "blind"
    ):
        lexicon = LEXICAL_TRUE_OOD[language]
        lexical_family = "true_ood"
    else:
        lexicon = TRAIN_QUERY_LEXICON[language]
        lexical_family = "train"
    if slice_name in {"TEMPLATE_HOLDOUT", "COMPOSED_OOD"}:
        template_id = TEMPLATE_HOLDOUT[index % len(TEMPLATE_HOLDOUT)]
    elif slice_name == "ORDER_HOLDOUT":
        template_id = ORDER_HOLDOUT_TEMPLATES[index % len(ORDER_HOLDOUT_TEMPLATES)]
    else:
        template_id = TRAIN_QUERY_TEMPLATES[index % len(TRAIN_QUERY_TEMPLATES)]
    words = {key: values[rng.randrange(len(values))] for key, values in lexicon.items()}
    op, preserve, stop = _effect_phrases(fields, language, words)
    wrapper = NEUTRAL_WRAPPERS[language][rng.randrange(len(NEUTRAL_WRAPPERS[language]))]
    punctuation = (".", ";", "!", ":")[rng.randrange(4)]
    text = _apply_template(
        template_id, wrapper, op, preserve, stop, punctuation, language
    )
    suffix = NEUTRAL_SUFFIXES[language][rng.randrange(len(NEUTRAL_SUFFIXES[language]))]
    return f"{text} {suffix}.", template_id, lexical_family


def _effect_phrases(fields: dict[str, Any], language: str, words: dict[str, str]):
    family = fields["family"]
    sources = fields["sources"]
    destination = fields["destination"]
    preserved = fields["preserve"]
    if language == "en":
        if family == "NOOP":
            op = "make no state change"
        elif family == "CLEAR":
            op = f"{words['clear']} every unit from {sources[0]}"
        elif family == "DROP_THEN_TRANSFER":
            op = f"first {words['clear']} {sources[0]}, then {words['move']} every unit from {sources[1]} to {destination}"
        else:
            ordered = " then ".join(sources)
            op = f"{words['move']} every unit from {ordered} to {destination} in that source order"
        preserve = (
            f"{words['preserve']} {', '.join(preserved)}"
            if preserved
            else "change no additional register"
        )
        stop = f"{words['stop']} after the named sources are empty"
    else:
        if family == "NOOP":
            op = "не меняй состояние"
        elif family == "CLEAR":
            op = f"{words['clear']} все единицы из {sources[0]}"
        elif family == "DROP_THEN_TRANSFER":
            op = f"сначала {words['clear']} {sources[0]}, затем {words['move']} все единицы из {sources[1]} в {destination}"
        else:
            ordered = " затем ".join(sources)
            op = f"{words['move']} все единицы из {ordered} в {destination} в указанном порядке источников"
        preserve = (
            f"{words['preserve']} {', '.join(preserved)}"
            if preserved
            else "не меняй дополнительные регистры"
        )
        stop = f"{words['stop']}, когда названные источники опустеют"
    return op, preserve, stop


def _apply_template(template_id, wrapper, op, preserve, stop, punctuation, language):
    if template_id == "train.direct":
        return f"{wrapper}: {op}; {preserve}; {stop}{punctuation}"
    if template_id == "train.effect_first":
        return f"{wrapper}: {op}{punctuation} {preserve}; {stop}."
    if template_id == "train.context_first":
        return f"{wrapper} -- {op}; {stop}; {preserve}{punctuation}"
    if template_id == "train.invariants_first":
        return f"{wrapper}: {preserve}; {op}; {stop}{punctuation}"
    if template_id == "train.request_form":
        lead = "Requested operation" if language == "en" else "Требуемая операция"
        return f"{wrapper}. {lead}: {op}. {preserve}. {stop}{punctuation}"
    if template_id == "train.compact":
        return f"{wrapper}/{op}/{preserve}/{stop}{punctuation}"
    if template_id == "holdout.question":
        lead = "Can you" if language == "en" else "Можешь"
        return f"{wrapper}: {lead} {op}, while you {preserve}, and {stop}?"
    if template_id == "holdout.stop_first":
        return (
            f"{wrapper}: {stop}; before that, {op}; throughout, {preserve}{punctuation}"
        )
    if template_id == "holdout.two_sentence":
        return f"{wrapper}. {op}; {preserve}. {stop}{punctuation}"
    if template_id == "holdout.parenthetical":
        return f"{wrapper}: {op} ({preserve}); {stop}{punctuation}"
    if template_id == "holdout.reverse_clauses":
        return f"{wrapper}: {stop}; {preserve}; {op}{punctuation}"
    return f"{wrapper}: {preserve}. {stop}. {op}{punctuation}"


def _negative_surface(language, slice_name, rng):
    wrapper = NEUTRAL_WRAPPERS[language][rng.randrange(len(NEUTRAL_WRAPPERS[language]))]
    suffix = NEUTRAL_SUFFIXES[language][rng.randrange(len(NEUTRAL_SUFFIXES[language]))]
    punctuation = (".", ";", "!", ":")[rng.randrange(4)]
    template_id = TRAIN_QUERY_TEMPLATES[rng.randrange(len(TRAIN_QUERY_TEMPLATES))]
    preserve = (
        "maintain every unnamed register, unchanged"
        if language == "en"
        else "сохрани каждый неназванный регистр, не меняя его"
    )
    stop = (
        "finish exactly after the described request is complete"
        if language == "en"
        else "заверши точно после выполнения описанного запроса"
    )
    a, b = ("AB", "BC", "CD", "DA")[rng.randrange(4)]
    if slice_name == "UNKNOWN":
        operations = {
            "en": (
                ("copy", f"copy {a} into {b} without emptying {a}"),
                ("swap", f"swap {a} and {b}"),
                ("sort", f"sort the contents of {a}"),
                ("compare", f"compare {a} with {b}"),
                ("multiply", f"multiply the counts in {a} and {b}"),
                ("register_e", f"move every unit from register E into {b}"),
                ("conditional", f"if {a} is nonempty, move {b} into {a}"),
            ),
            "ru": (
                ("copy", f"скопируй {a} в {b}, не опустошая {a}"),
                ("swap", f"поменяй местами {a} и {b}"),
                ("sort", f"отсортируй содержимое {a}"),
                ("compare", f"сравни {a} и {b}"),
                ("multiply", f"умножь количества в {a} и {b}"),
                ("register_e", f"перенеси всё из регистра E в {b}"),
                ("conditional", f"если {a} непуст, перенеси {b} в {a}"),
            ),
        }
        family, operation = operations[language][
            rng.randrange(len(operations[language]))
        ]
        text = _apply_template(
            template_id,
            wrapper,
            operation,
            preserve,
            stop,
            punctuation,
            language,
        )
        return (
            f"{text} {suffix}.",
            template_id,
            "unknown",
            family,
        )
    templates = {
        "en": (
            f"move every unit from {a}",
            f"move every unit into {b}",
            f"clear one register and then move {a} into {b}",
        ),
        "ru": (
            f"перенеси все единицы из {a}",
            f"перенеси все единицы в {b}",
            f"очисти один регистр, затем перенеси {a} в {b}",
        ),
    }
    ambiguity_index = rng.randrange(len(AMBIGUITY_TEMPLATES))
    template = AMBIGUITY_TEMPLATES[ambiguity_index]
    text = _apply_template(
        template_id,
        wrapper,
        templates[language][ambiguity_index],
        preserve,
        stop,
        punctuation,
        language,
    )
    return (
        f"{text} {suffix}.",
        template,
        "ambiguous",
        template,
    )


def _skill_fields(skill: SkillRecord) -> dict[str, Any]:
    specification = specification_from_dict(skill.effect_schema)
    family = infer_family(specification)
    return {
        "family": family.value,
        "sources": tuple(specification.inputs),
        "destination": specification.outputs[0] if specification.outputs else None,
        "preserve": tuple(specification.preserve),
        "phase_constraints": tuple(specification.phase_constraints),
    }


def _semantic_field_difference(first: dict, second: dict) -> tuple[str, ...]:
    return tuple(
        key for key in ("family", "sources", "destination") if first[key] != second[key]
    )


def semantic_field_difference(
    first: SkillRecord, second: SkillRecord
) -> tuple[str, ...]:
    """Return the conceptual catalog fields changed by a counterfactual pair."""
    return _semantic_field_difference(_skill_fields(first), _skill_fields(second))


def _build_neighbor_map(skills, metadata):
    result = {}
    for skill in skills:
        candidates = []
        for other in skills:
            if other.skill_id == skill.skill_id:
                continue
            differences = _semantic_field_difference(
                metadata[skill.skill_id], metadata[other.skill_id]
            )
            if len(differences) == 1:
                candidates.append((differences[0], other.skill_id))
        if candidates:
            result[skill.skill_id] = min(candidates, key=lambda row: (row[0], row[1]))
    return result


def _balanced_holdout(skills, count, offset):
    by_family: dict[str, list[SkillRecord]] = {}
    for skill in skills:
        by_family.setdefault(skill.semantic_family, []).append(skill)
    selected = [items[offset % len(items)] for items in by_family.values()]
    remaining = [item for item in skills if item not in selected]
    selected.extend(remaining[offset::4][: count - len(selected)])
    return tuple(sorted(item.skill_id for item in selected[:count]))


def _validate_fair_dataset(
    rows_by_split, skills, *, zero_ids, variable_ids, ru_only, en_only
):
    train = rows_by_split["train"]
    train_targets = {row["target_skill_id"] for row in train if row["known"]}
    if train_targets & zero_ids:
        raise ValueError("zero-query skill leaked into train positives")
    if train_targets & variable_ids:
        raise ValueError("variable holdout assignment leaked into train positives")
    for row in train:
        if row["target_skill_id"] in ru_only and row["language"] != "ru":
            raise ValueError("RU-only transfer skill leaked EN training query")
        if row["target_skill_id"] in en_only and row["language"] != "en":
            raise ValueError("EN-only transfer skill leaked RU training query")
    all_text = [
        _normalize(row["text"]) for rows in rows_by_split.values() for row in rows
    ]
    if len(all_text) != len(set(all_text)):
        raise ValueError("fair query prompts are not disjoint")
    forbidden = (
        "no exact structural",
        "ask before",
        "do not guess",
        "outside the installed",
        "unsupported",
        "unknown operation",
        "clarification is required",
        "точное структурное",
        "уточни запрос",
        "не угадывай",
        "вне установленного",
    )
    if any(marker in text.casefold() for text in all_text for marker in forbidden):
        raise ValueError("label-revealing phrase in fair dataset")
    corpus = " ".join(_catalog_text(item).casefold() for item in skills)
    preblind = " ".join(
        row["text"].casefold()
        for split, rows in rows_by_split.items()
        if split != "blind"
        for row in rows
    )
    for language in LEXICAL_TRUE_OOD.values():
        for values in language.values():
            for phrase in values:
                if phrase.casefold() in corpus or phrase.casefold() in preblind:
                    raise ValueError(f"true lexical OOD phrase leaked: {phrase}")
    train_templates = {row["template_id"] for row in train}
    if train_templates & set(TEMPLATE_HOLDOUT + ORDER_HOLDOUT_TEMPLATES):
        raise ValueError("heldout template leaked into train")


def _catalog_text(skill):
    return "\n".join(
        (
            skill.canonical_name_ru,
            skill.canonical_name_en,
            skill.effect_summary,
            *skill.aliases_ru,
            *skill.aliases_en,
            *skill.controlled_examples_ru,
            *skill.controlled_examples_en,
        )
    )


def _prompt_intersections(rows_by_split):
    sets = {
        name: {_normalize(row["text"]) for row in rows}
        for name, rows in rows_by_split.items()
    }
    return {
        f"{left}_x_{right}": len(sets[left] & sets[right])
        for index, left in enumerate(sets)
        for right in list(sets)[index + 1 :]
    }


def _public_blind_row(row):
    return {key: row[key] for key in ("schema_version", "query_id", "text", "language")}


def _blind_target_row(row):
    return {
        key: value
        for key, value in row.items()
        if key not in {"schema_version", "text", "language"}
    }


def _normalize(text):
    return " ".join(text.casefold().split())


def _write_jsonl(path, rows):
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )


def _load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _file_metadata(path, rows):
    return {"path": path.name, "count": len(rows), "sha256": _sha256(path)}


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
