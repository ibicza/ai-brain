"""Fair, strict-explicit bilingual dataset for the M-23.1 retest."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Any

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language_to_spec.equivalence import semantic_specification_signature
from ai_brain.language_to_spec.generator import normalize_language_text
from ai_brain.language_to_spec.schema import (
    VARIABLES,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    build_family_specification,
    canonicalize_specification,
)
from ai_brain.rules.specifications import ProgramSpecification

FAIR_SPLIT_COUNTS = {
    "train": 20_000,
    "validation_train_surface": 2_000,
    "calibration": 2_000,
    "test_id": 500,
    "test_lexical_holdout": 500,
    "test_template_holdout": 500,
    "test_variable_permutation": 500,
    "test_order_holdout": 500,
    "test_cross_language": 500,
    "test_negation_preserve": 500,
    "test_ambiguous": 500,
    "test_contradictory": 500,
    "test_unsupported": 500,
    "test_composed_ood": 500,
}

TRAIN_LEXICON = {
    "en": {
        "move": ("move", "transfer"),
        "drop": ("clear", "remove"),
        "preserve": ("leave unchanged", "preserve"),
        "stop": ("stop", "finish"),
    },
    "ru": {
        "move": ("перемести", "перенеси"),
        "drop": ("очисти", "удали"),
        "preserve": ("не изменяй", "сохрани без изменений"),
        "stop": ("остановись", "заверши работу"),
    },
}

HOLDOUT_LEXICON = {
    "en": {
        "move": ("convey", "channel"),
        "drop": ("purge", "expunge"),
        "preserve": ("retain untouched", "maintain intact"),
        "stop": ("cease execution", "conclude"),
    },
    "ru": {
        "move": ("перебрось", "переправь"),
        "drop": ("ликвидируй", "избавься от содержимого"),
        "preserve": ("сбереги как есть", "поддерживай без изменений"),
        "stop": ("прерви выполнение", "закончи операцию"),
    },
}

_TRAIN_ORDERS = (
    ("main", "preserve", "terminate"),
    ("main", "terminate", "preserve"),
)
_HOLDOUT_ORDERS = (
    ("preserve", "main", "terminate"),
    ("terminate", "preserve", "main"),
)
_PUNCTUATION = (".", "!", ";")
_HARMLESS = {
    "en": (
        "Use only the named registers",
        "The register names are literal",
        "Apply the instruction exactly",
        "No extra operation is requested",
        "This is the complete command",
        "Only the stated contents matter",
        "Keep the stated phase order",
        "The result remains in the named destination",
        "Do not invent an additional action",
        "The operation is deterministic",
        "All register names are explicit",
        "No sample identifier is part of this command",
    ),
    "ru": (
        "Используй только названные регистры",
        "Имена регистров указаны буквально",
        "Выполни инструкцию точно",
        "Дополнительных действий не требуется",
        "Это полная команда",
        "Учитывай только указанное содержимое",
        "Соблюдай заданный порядок фаз",
        "Результат остаётся в названном приёмнике",
        "Не добавляй новое действие",
        "Операция детерминирована",
        "Все имена регистров заданы явно",
        "В команде нет видимого идентификатора примера",
    ),
}


def assignments_for(
    family: SemanticFamily, *, holdout: bool | None = None
) -> tuple[tuple[str, ...], ...]:
    if family == SemanticFamily.NOOP:
        return ((),)
    if family == SemanticFamily.CLEAR:
        rows = tuple((role,) for role in VARIABLES)
    elif family == SemanticFamily.DRAIN:
        rows = tuple(itertools.permutations(VARIABLES, 2))
    elif family in {SemanticFamily.MERGE_TWO, SemanticFamily.DROP_THEN_TRANSFER}:
        rows = tuple(itertools.permutations(VARIABLES, 3))
    else:
        rows = tuple(itertools.permutations(VARIABLES, 4))
    heldout = tuple(row for index, row in enumerate(rows) if index % 4 == 0)
    train = tuple(row for index, row in enumerate(rows) if index % 4 != 0)
    if holdout is None:
        return rows
    return heldout if holdout else train


def roles_from_assignment(
    family: SemanticFamily, assignment: tuple[str, ...]
) -> tuple[tuple[str, ...], str | None]:
    if family == SemanticFamily.NOOP:
        return (), None
    if family == SemanticFamily.CLEAR:
        return assignment, None
    return assignment[:-1], assignment[-1]


def specification_for(family: SemanticFamily, assignment: tuple[str, ...]) -> Any:
    sources, destination = roles_from_assignment(family, assignment)
    return build_family_specification(family, sources=sources, destination=destination)


def _join(language: str, roles: Iterable[str]) -> str:
    values = tuple(roles)
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    conjunction = " and " if language == "en" else " и "
    return ", ".join(values[:-1]) + conjunction + values[-1]


def _lexeme(language: str, concept: str, profile: str, rng: random.Random) -> str:
    lexicon = HOLDOUT_LEXICON if profile == "holdout" else TRAIN_LEXICON
    return rng.choice(lexicon[language][concept])


def _operation_clause(
    language: str,
    family: SemanticFamily,
    sources: tuple[str, ...],
    destination: str | None,
    *,
    lexical_profile: str,
    template_profile: str,
    template_index: int,
    rng: random.Random,
) -> tuple[str, tuple[str, ...]]:
    move = _lexeme(language, "move", lexical_profile, rng)
    drop = _lexeme(language, "drop", lexical_profile, rng)
    used: list[str] = []
    if family == SemanticFamily.NOOP:
        return (
            "Leave all registers unchanged and stop immediately"
            if language == "en"
            else "Оставь все регистры без изменений и сразу остановись",
            (),
        )
    source_text = _join(language, sources)
    if family == SemanticFamily.CLEAR:
        used.append(drop)
        if language == "en":
            forms = (
                f"{drop.capitalize()} every item from {sources[0]}",
                f"Please {drop} the complete contents of {sources[0]}",
            )
            heldout = (
                f"{drop.capitalize()} everything in {sources[0]} so nothing remains",
                f"{drop.capitalize()} the contents of {sources[0]} until it is empty",
            )
        else:
            forms = (
                f"{drop.capitalize()} все элементы из {sources[0]}",
                f"Пожалуйста, {drop} полное содержимое {sources[0]}",
            )
            heldout = (
                f"{drop.capitalize()} всё из {sources[0]}, чтобы ничего не осталось",
                f"{drop.capitalize()} содержимое {sources[0]} до полного опустошения",
            )
        return (heldout if template_profile == "holdout" else forms)[
            template_index % 2
        ], tuple(used)
    if family == SemanticFamily.DROP_THEN_TRANSFER:
        used.extend((drop, move))
        first, second = sources
        if language == "en":
            forms = (
                f"First {drop} {first}, then {move} every item from {second} into {destination}",
                f"{drop.capitalize()} {first} before you {move} the contents of {second} to {destination}",
            )
            heldout = (
                f"Phase one must {drop} {first}; only afterward {move} {second} toward {destination}",
                f"{drop.capitalize()} everything in {first} before you {move} {second} to {destination}",
            )
        else:
            forms = (
                f"Сначала {drop} {first}, затем {move} все элементы из {second} в {destination}",
                f"{drop.capitalize()} {first} до того, как {move} содержимое {second} в {destination}",
            )
            heldout = (
                f"На первой фазе {drop} {first}; только после этого {move} {second} в {destination}",
                f"{drop.capitalize()} всё из {first} до того, как {move} {second} в {destination}",
            )
        return (heldout if template_profile == "holdout" else forms)[
            template_index % 2
        ], tuple(used)
    used.append(move)
    if language == "en":
        forms = (
            f"{move.capitalize()} every item from {source_text} into {destination}",
            f"Please {move} all contents of {source_text} to {destination}",
        )
        heldout = (
            f"{move.capitalize()} the complete contents held by {source_text} to {destination}",
            f"{move.capitalize()} everything from {source_text} so that {destination} receives it",
        )
    else:
        forms = (
            f"{move.capitalize()} все элементы из {source_text} в {destination}",
            f"Пожалуйста, {move} всё содержимое {source_text} в {destination}",
        )
        heldout = (
            f"{move.capitalize()} полное содержимое {source_text} в {destination}",
            f"{move.capitalize()} всё из {source_text}, чтобы {destination} получил содержимое",
        )
    return (heldout if template_profile == "holdout" else forms)[
        template_index % 2
    ], tuple(used)


def _preserve_clause(
    language: str,
    preserve: tuple[str, ...],
    lexical_profile: str,
    rng: random.Random,
    *,
    negation_focus: bool,
) -> tuple[str, tuple[str, ...]]:
    if not preserve:
        return (
            "No register is required to remain unchanged"
            if language == "en"
            else "Нет регистра, который требуется сохранить без изменений",
            (),
        )
    preserve_verb = _lexeme(language, "preserve", lexical_profile, rng)
    roles = _join(language, preserve)
    if negation_focus and lexical_profile == "train":
        return (
            (f"Do not modify {roles}" if language == "en" else f"Не меняй {roles}"),
            ("do not modify" if language == "en" else "не меняй",),
        )
    return f"{preserve_verb.capitalize()} {roles}", (preserve_verb,)


def _termination_clause(
    language: str,
    consumed: tuple[str, ...],
    lexical_profile: str,
    rng: random.Random,
) -> tuple[str, tuple[str, ...]]:
    if not consumed:
        return (
            "Stop immediately; no register must first become empty"
            if language == "en"
            else "Остановись сразу; ни один регистр не должен сначала опустеть",
            (),
        )
    stop = _lexeme(language, "stop", lexical_profile, rng)
    roles = _join(language, consumed)
    if language == "en":
        return f"{stop.capitalize()} when {roles} are empty", (stop,)
    return f"{stop.capitalize()}, когда {roles} опустеют", (stop,)


def render_supported(
    *,
    language: str,
    family: SemanticFamily,
    assignment: tuple[str, ...],
    lexical_profile: str,
    template_profile: str,
    order_profile: str,
    negation_focus: bool,
    rng: random.Random,
) -> tuple[str, Any, dict[str, Any]]:
    sources, destination = roles_from_assignment(family, assignment)
    spec = specification_for(family, assignment)
    template_index = rng.randrange(2)
    main, main_lexemes = _operation_clause(
        language,
        family,
        sources,
        destination,
        lexical_profile=lexical_profile,
        template_profile=template_profile,
        template_index=template_index,
        rng=rng,
    )
    preserve, preserve_lexemes = _preserve_clause(
        language,
        spec.preserve,
        lexical_profile,
        rng,
        negation_focus=negation_focus,
    )
    terminate, stop_lexemes = _termination_clause(
        language, sources, lexical_profile, rng
    )
    order = rng.choice(_HOLDOUT_ORDERS if order_profile == "holdout" else _TRAIN_ORDERS)
    clauses = {"main": main, "preserve": preserve, "terminate": terminate}
    selected = [clauses[name] for name in order]
    harmless_count = rng.randrange(5)
    if harmless_count:
        selected.extend(rng.sample(_HARMLESS[language], harmless_count))
    punctuation = rng.choice(_PUNCTUATION)
    text = (punctuation + " ").join(selected) + punctuation
    metadata = {
        "assignment": list(assignment),
        "clause_order": list(order),
        "explicit_operation": True,
        "explicit_sources": True,
        "explicit_destination": True,
        "explicit_preserve": True,
        "explicit_termination": True,
        "explicit_order": True,
        "strict_complete": True,
        "lexical_items": [*main_lexemes, *preserve_lexemes, *stop_lexemes],
        "template_id": f"{template_profile}_{template_index}",
        "role_assignment": "".join(assignment) or "NONE",
    }
    return text, spec, metadata


def _answer(
    status: ParseStatus,
    specification: Any | None,
    code: ValidationCode | None,
) -> str:
    payload: dict[str, Any] = {
        "status": str(status),
        "specification": (
            asdict(canonicalize_specification(specification))
            if specification is not None
            else None
        ),
    }
    if code is not None:
        payload["error"] = str(code)
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _row(
    *,
    text: str,
    language: str,
    status: ParseStatus,
    family: SemanticFamily | None,
    specification: Any | None,
    code: ValidationCode | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "text": text,
        "prompt": text,
        "answer": _answer(status, specification, code),
        "language": language,
        "status": str(status),
        "canonical_specification": (
            asdict(canonicalize_specification(specification))
            if specification is not None
            else None
        ),
        "semantic_family": str(family) if family is not None else None,
        "surface_template_family": metadata["template_id"],
        "lexical_family": metadata.get("lexical_profile", "train"),
        "error_code": str(code) if code is not None else None,
        "metadata": metadata,
    }


_AMBIGUOUS_CODES = (
    ValidationCode.MISSING_DESTINATION,
    ValidationCode.AMBIGUOUS_PRONOUN,
    ValidationCode.UNCLEAR_ORDER,
    ValidationCode.MISSING_PRESERVE_BEHAVIOR,
)
_CONTRADICTORY_CODES = (
    ValidationCode.PRESERVE_TRANSFER_CONFLICT,
    ValidationCode.DROP_TRANSFER_CONFLICT,
    ValidationCode.IMPOSSIBLE_TERMINATION,
)


def render_negative(
    status: ParseStatus, language: str, code: ValidationCode, rng: random.Random
) -> tuple[str, dict[str, Any]]:
    a, b, c, d = rng.sample(VARIABLES, 4)
    metadata: dict[str, Any] = {
        "assignment": [a, b, c, d],
        "role_assignment": f"{a}{b}{c}{d}",
        "template_id": f"negative_{code}",
        "lexical_profile": "train",
        "strict_complete": False,
        "explicit_operation": True,
        "explicit_sources": True,
        "explicit_destination": True,
        "explicit_preserve": True,
        "explicit_termination": True,
        "explicit_order": True,
        "lexical_items": [],
    }
    if status == ParseStatus.AMBIGUOUS:
        resolved = None
        if code == ValidationCode.MISSING_DESTINATION:
            text = (
                f"Move every item from {a}. Leave {c} and {d} unchanged. Stop when {a} is empty."
                if language == "en"
                else f"Перемести все элементы из {a}. Не изменяй {c} и {d}. Остановись, когда {a} опустеет."
            )
            answer = b
            resolved = build_family_specification(
                SemanticFamily.DRAIN, sources=(a,), destination=b
            )
            metadata["explicit_destination"] = False
            partial = {"actions": [["MOVE_ONE", a, None]], "preserve": [c, d]}
        elif code == ValidationCode.UNCLEAR_ORDER:
            text = (
                f"Clear {a} and move {b} into {c}. Leave {d} unchanged. Stop when {a} and {b} are empty."
                if language == "en"
                else f"Очисти {a} и перенеси {b} в {c}. Не изменяй {d}. Остановись, когда {a} и {b} опустеют."
            )
            answer = "yes" if language == "en" else "да"
            resolved = build_family_specification(
                SemanticFamily.DROP_THEN_TRANSFER,
                sources=(a, b),
                destination=c,
            )
            metadata["explicit_order"] = False
            partial = {
                "actions": [["DROP_ONE", a, None], ["MOVE_ONE", b, c]],
                "preserve": [d],
            }
        elif code == ValidationCode.MISSING_PRESERVE_BEHAVIOR:
            text = (
                f"Move every item from {a} into {b}. Stop when {a} is empty."
                if language == "en"
                else f"Перемести все элементы из {a} в {b}. Остановись, когда {a} опустеет."
            )
            answer = f"{c} {d}"
            resolved = build_family_specification(
                SemanticFamily.DRAIN, sources=(a,), destination=b
            )
            metadata["explicit_preserve"] = False
            partial = {"actions": [["MOVE_ONE", a, b]], "preserve": None}
        else:
            text = (
                f"Move every item from {a} into {b}. Leave {c} unchanged and leave it unchanged. Stop when {a} is empty."
                if language == "en"
                else f"Перемести все элементы из {a} в {b}. Не изменяй {c} и его тоже не изменяй. Остановись, когда {a} опустеет."
            )
            answer = d
            resolved = build_family_specification(
                SemanticFamily.DRAIN, sources=(a,), destination=b
            )
            partial = {
                "actions": [["MOVE_ONE", a, b]],
                "preserve": [c],
                "candidate_referents": [c, d],
            }
        metadata.update(
            {
                "clarification_answer": answer,
                "partial_interpretation": partial,
                "resolved_specification": asdict(canonicalize_specification(resolved)),
            }
        )
    elif status == ParseStatus.CONTRADICTORY:
        if code == ValidationCode.PRESERVE_TRANSFER_CONFLICT:
            text = (
                f"Move every item from {a} into {b}, but leave {a} unchanged. Stop when {a} is empty."
                if language == "en"
                else f"Перемести все элементы из {a} в {b}, но {a} не изменяй. Остановись, когда {a} опустеет."
            )
        elif code == ValidationCode.DROP_TRANSFER_CONFLICT:
            text = (
                f"Clear {a} and transfer every item from {a} into {b}. Leave {c} and {d} unchanged."
                if language == "en"
                else f"Очисти {a} и перенеси все элементы из {a} в {b}. Не изменяй {c} и {d}."
            )
        else:
            text = (
                f"Leave {a} unchanged and stop only when {a} is empty."
                if language == "en"
                else f"Не изменяй {a} и остановись только когда {a} опустеет."
            )
    else:
        text = (
            f"Copy every item from {a} into {b} without emptying {a}."
            if language == "en"
            else f"Скопируй все элементы из {a} в {b}, не очищая {a}."
        )
    suffix_count = rng.randrange(4)
    if suffix_count:
        text += " " + ". ".join(rng.sample(_HARMLESS[language], suffix_count)) + "."
    return text, metadata


def _unique_row(
    factory: Any, seen: set[str], *, attempts: int = 10_000
) -> dict[str, Any]:
    for _ in range(attempts):
        row = factory()
        normalized = normalize_language_text(row["text"])
        if normalized not in seen:
            seen.add(normalized)
            return row
    raise RuntimeError("Could not generate a globally unique fair language row")


def _family_quotas(pair_count: int) -> dict[SemanticFamily, int]:
    families = tuple(SemanticFamily)
    base, remainder = divmod(pair_count, len(families))
    return {
        family: base + int(index < remainder) for index, family in enumerate(families)
    }


def _supported_rows(
    count: int,
    *,
    split: str,
    seed: int,
    seen: set[str],
) -> list[dict[str, Any]]:
    if count % 2:
        raise ValueError("Supported fair split counts must be even for bilingual pairs")
    pair_count = count // 2
    role_rng = random.Random(seed + 11)
    surface_rng = random.Random(seed + 23)
    order_rng = random.Random(seed + 37)
    shuffle_rng = random.Random(seed + 53)
    lexical_profile = (
        "holdout" if split in {"test_lexical_holdout", "test_composed_ood"} else "train"
    )
    template_profile = (
        "holdout"
        if split in {"test_template_holdout", "test_composed_ood"}
        else "train"
    )
    order_profile = "holdout" if split == "test_order_holdout" else "train"
    role_holdout = split == "test_variable_permutation"
    quotas = _family_quotas(pair_count)
    pair_specs: list[tuple[SemanticFamily, tuple[str, ...]]] = []
    for family, quota in quotas.items():
        assignments = list(assignments_for(family, holdout=role_holdout))
        role_rng.shuffle(assignments)
        pair_specs.extend(
            (family, assignments[index % len(assignments)]) for index in range(quota)
        )
    shuffle_rng.shuffle(pair_specs)
    rows: list[dict[str, Any]] = []
    for pair_index, (family, assignment) in enumerate(pair_specs):
        pair_id = f"{split}-pair-{pair_index:05d}"
        for language in ("ru", "en"):

            def make(
                language: str = language,
                family: SemanticFamily = family,
                assignment: tuple[str, ...] = assignment,
                pair_id: str = pair_id,
            ) -> dict[str, Any]:
                text, spec, metadata = render_supported(
                    language=language,
                    family=family,
                    assignment=assignment,
                    lexical_profile=lexical_profile,
                    template_profile=template_profile,
                    order_profile=order_profile,
                    negation_focus=split == "test_negation_preserve",
                    rng=surface_rng if language == "ru" else order_rng,
                )
                metadata.update(
                    {
                        "pair_id": pair_id,
                        "lexical_profile": lexical_profile,
                        "split_axis": split,
                    }
                )
                return _row(
                    text=text,
                    language=language,
                    status=ParseStatus.SUPPORTED,
                    family=family,
                    specification=spec,
                    code=None,
                    metadata=metadata,
                )

            rows.append(_unique_row(make, seen))
    shuffle_rng.shuffle(rows)
    return rows


def _negative_rows(
    count: int,
    *,
    status: ParseStatus,
    seed: int,
    seen: set[str],
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    codes = (
        _AMBIGUOUS_CODES
        if status == ParseStatus.AMBIGUOUS
        else _CONTRADICTORY_CODES
        if status == ParseStatus.CONTRADICTORY
        else (ValidationCode.UNSUPPORTED_OPERATION,)
    )
    rows = []
    for index in range(count):
        language = ("ru", "en")[(index // len(codes)) % 2]
        code = codes[index % len(codes)]

        def make(
            language: str = language, code: ValidationCode = code
        ) -> dict[str, Any]:
            text, metadata = render_negative(status, language, code, rng)
            return _row(
                text=text,
                language=language,
                status=status,
                family=None,
                specification=None,
                code=code,
                metadata=metadata,
            )

        rows.append(_unique_row(make, seen))
    rng.shuffle(rows)
    return rows


def _mixed_split(
    count: int, *, split: str, seed: int, seen: set[str]
) -> list[dict[str, Any]]:
    supported = count * 7 // 10
    supported -= supported % 2
    remaining = count - supported
    each = remaining // 3
    counts = [each, each, remaining - 2 * each]
    rows = _supported_rows(supported, split=split, seed=seed, seen=seen)
    for offset, (status, status_count) in enumerate(
        zip(
            (
                ParseStatus.AMBIGUOUS,
                ParseStatus.CONTRADICTORY,
                ParseStatus.UNSUPPORTED,
            ),
            counts,
            strict=True,
        )
    ):
        rows.extend(
            _negative_rows(
                status_count,
                status=status,
                seed=seed + 101 * (offset + 1),
                seen=seen,
            )
        )
    random.Random(seed + 809).shuffle(rows)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _matrix(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                "|".join(
                    str(
                        row.get(key)
                        if key != "role_assignment"
                        else row["metadata"].get(key)
                    )
                    for key in keys
                )
                for row in rows
            ).items()
        )
    )


def _percentile(values: list[int], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)
    return float(ordered[index])


def _length_summary(
    rows: list[dict[str, Any]], tokenizer: ByteLevelBpeTokenizer
) -> dict[str, Any]:
    byte_lengths = [len(row["text"].encode("utf-8")) + 1 for row in rows]
    bpe_lengths = [len(tokenizer.encode(row["text"])) + 1 for row in rows]
    by_language = {}
    for language in ("ru", "en"):
        indices = [i for i, row in enumerate(rows) if row["language"] == language]
        by_language[language] = {
            "byte_avg": mean(byte_lengths[i] for i in indices) if indices else 0.0,
            "byte_p95": _percentile([byte_lengths[i] for i in indices], 0.95),
            "byte_max": max((byte_lengths[i] for i in indices), default=0),
            "bpe_avg": mean(bpe_lengths[i] for i in indices) if indices else 0.0,
            "bpe_p95": _percentile([bpe_lengths[i] for i in indices], 0.95),
            "bpe_max": max((bpe_lengths[i] for i in indices), default=0),
        }
    return {
        "byte": {
            "avg": mean(byte_lengths),
            "p95": _percentile(byte_lengths, 0.95),
            "max": max(byte_lengths),
            "truncated_at_768": sum(length > 768 for length in byte_lengths),
        },
        "bpe": {
            "avg": mean(bpe_lengths),
            "p95": _percentile(bpe_lengths, 0.95),
            "max": max(bpe_lengths),
            "truncated_at_256": sum(length > 256 for length in bpe_lengths),
        },
        "by_language": by_language,
    }


def _mutual_information_language_family(rows: list[dict[str, Any]]) -> float:
    supported = [row for row in rows if row["status"] == str(ParseStatus.SUPPORTED)]
    joint = Counter((row["language"], row["semantic_family"]) for row in supported)
    language = Counter(row["language"] for row in supported)
    family = Counter(row["semantic_family"] for row in supported)
    total = len(supported)
    result = 0.0
    for (lang, fam), count in joint.items():
        probability = count / total
        result += probability * math.log2(
            probability / ((language[lang] / total) * (family[fam] / total))
        )
    return result


def _split_summary(
    rows: list[dict[str, Any]], tokenizer: ByteLevelBpeTokenizer
) -> dict[str, Any]:
    specs_by_language: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["canonical_specification"] is not None:
            spec = canonicalize_specification(
                ProgramSpecification(**row["canonical_specification"])
            )
            specs_by_language[row["language"]].add(
                semantic_specification_signature(spec)
            )
    return {
        "count": len(rows),
        "language_family": _matrix(rows, ("language", "semantic_family")),
        "language_status": _matrix(rows, ("language", "status")),
        "language_family_status": _matrix(
            rows, ("language", "semantic_family", "status")
        ),
        "language_role_assignment": _matrix(rows, ("language", "role_assignment")),
        "concrete_specification_counts": {
            language: len(signatures)
            for language, signatures in sorted(specs_by_language.items())
        },
        "explicit_complete": sum(
            bool(row["metadata"].get("strict_complete")) for row in rows
        ),
        "incomplete": sum(
            not bool(row["metadata"].get("strict_complete")) for row in rows
        ),
        "language_family_mutual_information_bits": _mutual_information_language_family(
            rows
        ),
        "lengths": _length_summary(rows, tokenizer),
    }


def _values(rows: list[dict[str, Any]], getter: Any) -> set[str]:
    return {str(getter(row)) for row in rows}


def generate_fair_language_dataset(
    output_dir: Path,
    *,
    tokenizer_path: Path,
    split_counts: dict[str, int] | None = None,
    seed: int = 23_100,
) -> dict[str, Any]:
    counts = dict(FAIR_SPLIT_COUNTS if split_counts is None else split_counts)
    tokenizer = ByteLevelBpeTokenizer.load(tokenizer_path)
    seen: set[str] = set()
    splits: dict[str, list[dict[str, Any]]] = {}
    for split_index, (split, count) in enumerate(counts.items()):
        split_seed = seed + split_index * 1_009
        if split in {"train", "validation_train_surface", "calibration"}:
            rows = _mixed_split(count, split=split, seed=split_seed, seen=seen)
        elif split == "test_ambiguous":
            rows = _negative_rows(
                count,
                status=ParseStatus.AMBIGUOUS,
                seed=split_seed,
                seen=seen,
            )
        elif split == "test_contradictory":
            rows = _negative_rows(
                count,
                status=ParseStatus.CONTRADICTORY,
                seed=split_seed,
                seen=seen,
            )
        elif split == "test_unsupported":
            rows = _negative_rows(
                count,
                status=ParseStatus.UNSUPPORTED,
                seed=split_seed,
                seen=seen,
            )
        else:
            rows = _supported_rows(count, split=split, seed=split_seed, seen=seen)
        splits[split] = rows
        _write_jsonl(output_dir / f"{split}.jsonl", rows)

    train = splits["train"]
    train_text = _values(train, lambda row: row["text"])
    train_normalized = _values(train, lambda row: normalize_language_text(row["text"]))
    train_lexemes = {
        item for row in train for item in row["metadata"].get("lexical_items", ())
    }
    train_templates = _values(train, lambda row: row["metadata"]["template_id"])
    train_roles = _values(train, lambda row: row["metadata"]["role_assignment"])
    train_specs = _values(train, lambda row: row["answer"])
    overlaps = {}
    for split, rows in splits.items():
        if split == "train":
            continue
        overlap_lexemes = {
            item for row in rows for item in row["metadata"].get("lexical_items", ())
        }
        overlaps[split] = {
            "exact_text": len(train_text & _values(rows, lambda row: row["text"])),
            "normalized_text": len(
                train_normalized
                & _values(rows, lambda row: normalize_language_text(row["text"]))
            ),
            "lexical_items": len(train_lexemes & overlap_lexemes),
            "template_ids": len(
                train_templates
                & _values(rows, lambda row: row["metadata"]["template_id"])
            ),
            "role_assignments": len(
                train_roles
                & _values(rows, lambda row: row["metadata"]["role_assignment"])
            ),
            "specifications": len(
                train_specs & _values(rows, lambda row: row["answer"])
            ),
        }
    supported_train = [
        row for row in train if row["status"] == str(ParseStatus.SUPPORTED)
    ]
    specs_by_language = {
        language: {
            row["answer"] for row in supported_train if row["language"] == language
        }
        for language in ("ru", "en")
    }
    paired_targets_equal = True
    pair_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for split in ("train", "validation_train_surface", "test_cross_language"):
        for row in splits[split]:
            if row["status"] == str(ParseStatus.SUPPORTED):
                pair_groups[row["metadata"]["pair_id"]].append(row)
    for pair in pair_groups.values():
        paired_targets_equal &= (
            len(pair) == 2
            and {row["language"] for row in pair} == {"ru", "en"}
            and len({row["answer"] for row in pair}) == 1
        )
    visible_id_hits = sum(
        bool(re.search(r"(?:sample|task|pair)[-_ ]?\d{3,}", row["text"], re.IGNORECASE))
        for rows in splits.values()
        for row in rows
    )
    manifest = {
        "schema_version": 2,
        "seed": seed,
        "explicitness_policy": "STRICT_EXPLICIT",
        "closed_world_default_mixed_into_primary": False,
        "counts": counts,
        "total_count": sum(counts.values()),
        "splits": {
            split: _split_summary(rows, tokenizer) for split, rows in splits.items()
        },
        "train_overlap_audit": overlaps,
        "all_supported_train_specs_bilingual": specs_by_language["ru"]
        == specs_by_language["en"],
        "supported_train_spec_count": len(specs_by_language["ru"]),
        "paired_targets_semantically_equal": paired_targets_equal,
        "model_visible_id_hits": visible_id_hits,
        "normalized_text_globally_unique": len(seen) == sum(counts.values()),
        "lexical_holdout_absent_from_train_lexicon": not (
            train_lexemes
            & {
                item
                for row in splits["test_lexical_holdout"]
                for item in row["metadata"].get("lexical_items", ())
            }
        ),
        "sha256": {
            split: hashlib.sha256(
                (output_dir / f"{split}.jsonl").read_bytes()
            ).hexdigest()
            for split in splits
        },
    }
    if not manifest["all_supported_train_specs_bilingual"]:
        raise AssertionError("Every supported train specification must be bilingual")
    if not paired_targets_equal or visible_id_hits:
        raise AssertionError("Bilingual pair integrity or visible-ID audit failed")
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest
