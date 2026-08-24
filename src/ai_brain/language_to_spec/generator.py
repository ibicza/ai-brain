"""Reproducible controlled RU/EN language dataset and strict OOD splits."""

from __future__ import annotations

import hashlib
import itertools
import json
import random
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.language_to_spec.schema import (
    VARIABLES,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    build_family_specification,
    canonicalize_specification,
)

DEFAULT_SPLIT_COUNTS = {
    "train": 20_000,
    "validation": 2_000,
    "test_id": 500,
    "test_lexical_holdout": 500,
    "test_template_holdout": 500,
    "test_variable_permutation": 500,
    "test_order_holdout": 500,
    "test_cross_language": 500,
    "test_ambiguous": 500,
    "test_contradictory": 500,
    "test_unsupported": 500,
    "test_negation_preserve": 500,
}

_TRAIN_ORDERS = (("main", "preserve", "terminate"), ("main", "terminate", "preserve"))
_HOLDOUT_ORDERS = (("preserve", "main", "terminate"), ("terminate", "preserve", "main"))
_PUNCTUATION = (".", "!", ".", ";")

_LEXICON = {
    "en": {
        "train_move": ("move", "transfer"),
        "holdout_move": ("relocate", "shift"),
        "train_drop": ("clear", "remove", "drop"),
        "holdout_drop": ("discard", "empty out"),
        "train_preserve": ("leave unchanged", "preserve"),
        "holdout_preserve": ("keep intact", "do not alter"),
        "train_stop": ("stop", "finish"),
        "holdout_stop": ("terminate", "complete the task"),
    },
    "ru": {
        "train_move": ("перемести", "перенеси"),
        "holdout_move": ("переложи", "направь"),
        "train_drop": ("очисти", "удали содержимое"),
        "holdout_drop": ("освободи", "убери содержимое"),
        "train_preserve": ("не изменяй", "сохрани без изменений"),
        "holdout_preserve": ("оставь нетронутым", "не трогай"),
        "train_stop": ("заверши работу", "остановись"),
        "holdout_stop": ("прекрати выполнение", "окончи задачу"),
    },
}

_HARMLESS = {
    "en": (
        "Use only the named registers",
        "No other register needs attention",
        "Follow the stated order",
        "The command is complete",
        "Apply this instruction exactly",
        "Nothing else should be done",
        "The register names are literal",
        "This is the whole operation",
        "Work only with these contents",
        "Keep the result in the requested register",
        "The remaining state is irrelevant",
        "Perform one controlled operation",
    ),
    "ru": (
        "Используй только названные регистры",
        "Другие регистры не требуют действий",
        "Соблюдай указанный порядок",
        "Команда приведена полностью",
        "Выполни инструкцию точно",
        "Больше ничего делать не нужно",
        "Имена регистров указаны буквально",
        "Это вся операция",
        "Работай только с этим содержимым",
        "Оставь результат в указанном регистре",
        "Остальное состояние несущественно",
        "Выполни одну управляемую операцию",
    ),
}


def normalize_language_text(text: str) -> str:
    return " ".join(re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE))


def _join_roles(language: str, roles: tuple[str, ...]) -> str:
    if len(roles) <= 1:
        return roles[0] if roles else ""
    conjunction = " and " if language == "en" else " и "
    return ", ".join(roles[:-1]) + conjunction + roles[-1]


def _assignments(
    family: SemanticFamily, *, holdout: bool
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
    seen = tuple(row for index, row in enumerate(rows) if index % 4 != 0)
    return heldout if holdout else seen


def _roles_from_assignment(
    family: SemanticFamily, assignment: tuple[str, ...]
) -> tuple[tuple[str, ...], str | None]:
    if family == SemanticFamily.NOOP:
        return (), None
    if family == SemanticFamily.CLEAR:
        return assignment, None
    return assignment[:-1], assignment[-1]


def _choose_lexeme(
    rng: random.Random, language: str, concept: str, lexical_family: str
) -> str:
    group = "holdout" if lexical_family == "holdout" else "train"
    return rng.choice(_LEXICON[language][f"{group}_{concept}"])


def _render_main(
    *,
    language: str,
    family: SemanticFamily,
    sources: tuple[str, ...],
    destination: str | None,
    template_index: int,
    lexical_family: str,
    rng: random.Random,
) -> str:
    source_text = _join_roles(language, sources)
    move = _choose_lexeme(rng, language, "move", lexical_family)
    drop = _choose_lexeme(rng, language, "drop", lexical_family)
    heldout = template_index >= 100
    slot = template_index % 4
    if language == "en":
        if family == SemanticFamily.NOOP:
            return (
                "Leave every register unchanged and stop immediately"
                if not heldout
                else "Make no state change; terminate at once"
            )
        if family == SemanticFamily.CLEAR:
            templates = (
                f"{drop.capitalize()} all items from {sources[0]}",
                f"Please {drop} register {sources[0]}",
                f"Register {sources[0]} must be made empty by removing its items",
                f"Remove every item currently held in {sources[0]}",
            )
            holdout_templates = (
                f"Let {sources[0]} end empty by discarding what it holds",
                f"Empty out the contents currently stored by {sources[0]}",
                f"Nothing may remain inside {sources[0]}",
                f"Dispose of the complete contents of {sources[0]}",
            )
            return (holdout_templates if heldout else templates)[slot]
        if family == SemanticFamily.DROP_THEN_TRANSFER:
            first, second = sources
            templates = (
                f"First {drop} {first}, then {move} every item from {second} into {destination}",
                f"{drop.capitalize()} register {first}; afterwards {move} {second} to {destination}",
                f"Before moving all items from {second} into {destination}, {drop} {first}",
                f"In order, {drop} {first} and then {move} the contents of {second} to {destination}",
            )
            holdout_templates = (
                f"Only after {first} has been emptied, {move} everything in {second} toward {destination}",
                f"Dispose of {first}'s contents before relocating {second}'s contents into {destination}",
                f"The first phase empties {first}; the next phase sends {second} to {destination}",
                f"Make {first} empty, followed by shifting all of {second} into {destination}",
            )
            return (holdout_templates if heldout else templates)[slot]
        templates = (
            f"{move.capitalize()} every item from {source_text} into {destination}",
            f"Please {move} all contents of {source_text} to {destination}",
            f"{destination} should receive every item from {source_text}",
            f"From {source_text}, {move} everything into {destination}",
        )
        holdout_templates = (
            f"Let {destination} collect everything currently held by {source_text}",
            f"Empty {source_text} by relocating their items to {destination}",
            f"The complete contents of {source_text} must end up inside {destination}",
            f"Send what {source_text} contain toward {destination} until they are empty",
        )
        return (holdout_templates if heldout else templates)[slot]

    if family == SemanticFamily.NOOP:
        return (
            "Не изменяй ни один регистр и сразу заверши работу"
            if not heldout
            else "Оставь состояние прежним; немедленно прекрати выполнение"
        )
    if family == SemanticFamily.CLEAR:
        templates = (
            f"{drop.capitalize()} все элементы из {sources[0]}",
            f"Пожалуйста, {drop} регистр {sources[0]}",
            f"Регистр {sources[0]} должен опустеть после удаления содержимого",
            f"Убери все элементы, находящиеся в {sources[0]}",
        )
        holdout_templates = (
            f"Пусть {sources[0]} останется пустым после удаления всего содержимого",
            f"Полностью освободи регистр {sources[0]}",
            f"Внутри {sources[0]} не должно ничего остаться",
            f"Устрани всё содержимое регистра {sources[0]}",
        )
        return (holdout_templates if heldout else templates)[slot]
    if family == SemanticFamily.DROP_THEN_TRANSFER:
        first, second = sources
        templates = (
            f"Сначала {drop} {first}, затем {move} все элементы из {second} в {destination}",
            f"{drop.capitalize()} регистр {first}; после этого {move} {second} в {destination}",
            f"Перед переносом всего из {second} в {destination} {drop} {first}",
            f"По очереди {drop} {first}, а потом {move} содержимое {second} в {destination}",
        )
        holdout_templates = (
            f"Только когда {first} будет очищен, направь всё из {second} в {destination}",
            f"Убери содержимое {first} до перемещения содержимого {second} в {destination}",
            f"Первая фаза опустошает {first}, следующая отправляет {second} в {destination}",
            f"Сделай {first} пустым, после чего переложи весь {second} в {destination}",
        )
        return (holdout_templates if heldout else templates)[slot]
    templates = (
        f"{move.capitalize()} все элементы из {source_text} в {destination}",
        f"Пожалуйста, {move} содержимое {source_text} в {destination}",
        f"В {destination} должны оказаться все элементы из {source_text}",
        f"Из {source_text} {move} всё в {destination}",
    )
    holdout_templates = (
        f"Пусть {destination} соберёт всё, что сейчас находится в {source_text}",
        f"Освободи {source_text}, переложив их элементы в {destination}",
        f"Полное содержимое {source_text} должно в итоге находиться в {destination}",
        f"Направляй содержимое {source_text} в {destination}, пока источники не опустеют",
    )
    return (holdout_templates if heldout else templates)[slot]


def _render_preserve(
    language: str, preserve: tuple[str, ...], lexical_family: str, rng: random.Random
) -> str:
    if not preserve:
        return ""
    verb = _choose_lexeme(rng, language, "preserve", lexical_family)
    roles = _join_roles(language, preserve)
    if language == "en":
        return f"{verb.capitalize()} {roles}"
    return f"{verb.capitalize()} {roles}"


def _render_termination(
    language: str, sources: tuple[str, ...], lexical_family: str, rng: random.Random
) -> str:
    if not sources:
        return ""
    verb = _choose_lexeme(rng, language, "stop", lexical_family)
    roles = _join_roles(language, sources)
    if language == "en":
        return f"{verb.capitalize()} when {roles} are empty"
    return f"{verb.capitalize()}, когда {roles} опустеют"


def _surface_text(
    *,
    language: str,
    family: SemanticFamily,
    assignment: tuple[str, ...],
    lexical_family: str,
    template_family: str,
    clause_order: tuple[str, ...],
    rng: random.Random,
) -> tuple[str, Any, dict[str, Any]]:
    sources, destination = _roles_from_assignment(family, assignment)
    spec = build_family_specification(family, sources=sources, destination=destination)
    template_index = (100 if template_family == "holdout" else 0) + rng.randrange(4)
    clauses = {
        "main": _render_main(
            language=language,
            family=family,
            sources=sources,
            destination=destination,
            template_index=template_index,
            lexical_family=lexical_family,
            rng=rng,
        ),
        "preserve": _render_preserve(language, spec.preserve, lexical_family, rng),
        "terminate": _render_termination(language, sources, lexical_family, rng),
    }
    include_preserve = family == SemanticFamily.NOOP or rng.random() < 0.75
    include_termination = family == SemanticFamily.NOOP or rng.random() < 0.8
    selected = []
    for name in clause_order:
        if name == "preserve" and not include_preserve:
            continue
        if name == "terminate" and not include_termination:
            continue
        if clauses[name]:
            selected.append(clauses[name])
    harmless_count = rng.choice((0, 1, 2, 2, 3, 4))
    if harmless_count:
        selected.extend(rng.sample(_HARMLESS[language], harmless_count))
    punctuation = rng.choice(_PUNCTUATION)
    text = (punctuation + " ").join(selected) + punctuation
    metadata = {
        "template_index": template_index,
        "clause_order": list(clause_order),
        "explicit_preserve": include_preserve,
        "explicit_termination": include_termination,
        "assignment": list(assignment),
    }
    return text, spec, metadata


def _negative_text(
    status: ParseStatus,
    language: str,
    rng: random.Random,
    *,
    forced_code: ValidationCode | None = None,
) -> tuple[str, ValidationCode, dict[str, Any]]:
    roles = rng.sample(VARIABLES, 3)
    a, b, c = roles
    if status == ParseStatus.AMBIGUOUS:
        code = forced_code or rng.choice(
            (
                ValidationCode.MISSING_DESTINATION,
                ValidationCode.AMBIGUOUS_PRONOUN,
                ValidationCode.UNCLEAR_ORDER,
                ValidationCode.MISSING_PRESERVE_BEHAVIOR,
            )
        )
        variants = {
            "en": {
                ValidationCode.MISSING_DESTINATION: f"Move every item from {a}.",
                ValidationCode.AMBIGUOUS_PRONOUN: f"Move all items from {a} into {b}, then clear it.",
                ValidationCode.UNCLEAR_ORDER: f"Clear {a} and move {b} into {c} in the required order.",
                ValidationCode.MISSING_PRESERVE_BEHAVIOR: f"Move {a} into {b} and keep the other register unchanged.",
            },
            "ru": {
                ValidationCode.MISSING_DESTINATION: f"Перемести все элементы из {a}.",
                ValidationCode.AMBIGUOUS_PRONOUN: f"Перемести всё из {a} в {b}, затем очисти его.",
                ValidationCode.UNCLEAR_ORDER: f"Очисти {a} и перенеси {b} в {c} в нужном порядке.",
                ValidationCode.MISSING_PRESERVE_BEHAVIOR: f"Перенеси {a} в {b}, а другой регистр не изменяй.",
            },
        }
    elif status == ParseStatus.CONTRADICTORY:
        code = forced_code or rng.choice(
            (
                ValidationCode.PRESERVE_TRANSFER_CONFLICT,
                ValidationCode.DROP_TRANSFER_CONFLICT,
                ValidationCode.IMPOSSIBLE_TERMINATION,
            )
        )
        variants = {
            "en": {
                ValidationCode.PRESERVE_TRANSFER_CONFLICT: f"Move all items from {a} into {b}, but leave {a} unchanged.",
                ValidationCode.DROP_TRANSFER_CONFLICT: f"Clear {a} and also transfer all of {a} into {b}.",
                ValidationCode.IMPOSSIBLE_TERMINATION: f"Leave {a} unchanged and stop only when {a} is empty.",
            },
            "ru": {
                ValidationCode.PRESERVE_TRANSFER_CONFLICT: f"Перемести всё из {a} в {b}, но {a} не изменяй.",
                ValidationCode.DROP_TRANSFER_CONFLICT: f"Очисти {a} и одновременно перенеси всё из {a} в {b}.",
                ValidationCode.IMPOSSIBLE_TERMINATION: f"Не изменяй {a} и заверши работу только когда {a} опустеет.",
            },
        }
    else:
        code = ValidationCode.UNSUPPORTED_OPERATION
        operation = rng.choice(("copy", "swap", "sort", "multiply", "duplicate"))
        en = {
            "copy": f"Copy every item from {a} into {b} without emptying {a}.",
            "swap": f"Swap the contents of {a} and {b}.",
            "sort": f"Sort the items in {a} and store them in {b}.",
            "multiply": f"Multiply the item count in {a} by two.",
            "duplicate": f"Duplicate each item from {a} into both {b} and {c}.",
        }
        ru = {
            "copy": f"Скопируй все элементы из {a} в {b}, не очищая {a}.",
            "swap": f"Поменяй местами содержимое {a} и {b}.",
            "sort": f"Отсортируй элементы в {a} и сохрани их в {b}.",
            "multiply": f"Умножь количество элементов в {a} на два.",
            "duplicate": f"Продублируй каждый элемент из {a} одновременно в {b} и {c}.",
        }
        variants = {"en": {code: en[operation]}, "ru": {code: ru[operation]}}
    text = variants[language][code]
    preambles = {
        "en": ("", "Please note: ", "The instruction says: ", "For this task, "),
        "ru": ("", "Обрати внимание: ", "В инструкции сказано: ", "Для этой задачи "),
    }
    suffix_count = rng.choice((0, 1, 2, 3))
    suffixes = rng.sample(_HARMLESS[language], suffix_count)
    punctuation = rng.choice((".", "!", ";"))
    rendered = rng.choice(preambles[language]) + text.rstrip(".!;") + punctuation
    if suffixes:
        rendered += " " + ". ".join(suffixes) + "."
    metadata: dict[str, Any] = {"assignment": roles}
    if status == ParseStatus.AMBIGUOUS:
        if code == ValidationCode.MISSING_DESTINATION:
            resolved = build_family_specification(
                SemanticFamily.DRAIN, sources=(a,), destination=b
            )
            answer = b
        elif code == ValidationCode.UNCLEAR_ORDER:
            resolved = build_family_specification(
                SemanticFamily.DROP_THEN_TRANSFER, sources=(a, b), destination=c
            )
            answer = "yes" if language == "en" else "да"
        else:
            resolved = build_family_specification(
                SemanticFamily.DRAIN, sources=(a,), destination=b
            )
            answer = c
        metadata["clarification_answer"] = answer
        metadata["resolved_specification"] = asdict(
            canonicalize_specification(resolved)
        )
    return rendered, code, metadata


def _model_answer(
    status: ParseStatus, specification: Any | None, code: ValidationCode | None
) -> str:
    payload: dict[str, Any] = {
        "specification": (
            asdict(canonicalize_specification(specification))
            if specification is not None
            else None
        ),
        "status": str(status),
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
    template_family: str,
    lexical_family: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "text": text,
        "prompt": text,
        "answer": _model_answer(status, specification, code),
        "language": language,
        "status": str(status),
        "canonical_specification": (
            asdict(canonicalize_specification(specification))
            if specification is not None
            else None
        ),
        "semantic_family": str(family) if family is not None else None,
        "surface_template_family": template_family,
        "lexical_family": lexical_family,
        "error_code": str(code) if code is not None else None,
        "metadata": metadata,
    }


def _generate_rows(
    *,
    count: int,
    seed: int,
    mode: str,
    seen_normalized: set[str],
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    local_seen: set[str] = set()
    supported_modes = {
        "train",
        "validation",
        "id",
        "lexical_holdout",
        "template_holdout",
        "variable_permutation",
        "order_holdout",
        "cross_language",
        "negation_preserve",
    }
    if mode == "train":
        status_cycle = (
            *(ParseStatus.SUPPORTED for _ in range(14)),
            ParseStatus.AMBIGUOUS,
            ParseStatus.AMBIGUOUS,
            ParseStatus.CONTRADICTORY,
            ParseStatus.CONTRADICTORY,
            ParseStatus.UNSUPPORTED,
            ParseStatus.UNSUPPORTED,
        )
    elif mode == "validation":
        status_cycle = (
            *(ParseStatus.SUPPORTED for _ in range(7)),
            ParseStatus.AMBIGUOUS,
            ParseStatus.CONTRADICTORY,
            ParseStatus.UNSUPPORTED,
        )
    elif mode == "ambiguous":
        status_cycle = (ParseStatus.AMBIGUOUS,)
    elif mode == "contradictory":
        status_cycle = (ParseStatus.CONTRADICTORY,)
    elif mode == "unsupported":
        status_cycle = (ParseStatus.UNSUPPORTED,)
    else:
        status_cycle = (ParseStatus.SUPPORTED,)

    pair_specs: list[tuple[SemanticFamily, tuple[str, ...]]] = []
    if mode == "cross_language":
        for family in SemanticFamily:
            for assignment in _assignments(family, holdout=False):
                pair_specs.append((family, assignment))
    attempts = 0
    while len(rows) < count:
        attempts += 1
        if attempts > count * 2_000:
            raise RuntimeError(f"Could not generate {count} unique rows for {mode}")
        status = status_cycle[len(rows) % len(status_cycle)]
        language = "ru" if (len(rows) + seed) % 2 == 0 else "en"
        if mode == "cross_language":
            pair_index = len(rows) // 2
            language = "ru" if len(rows) % 2 == 0 else "en"
            family, assignment = pair_specs[pair_index % len(pair_specs)]
        else:
            family = list(SemanticFamily)[len(rows) % len(SemanticFamily)]
            assignment = rng.choice(
                _assignments(
                    family,
                    holdout=mode == "variable_permutation"
                    and family != SemanticFamily.NOOP,
                )
            )
        if status == ParseStatus.SUPPORTED and mode in supported_modes:
            lexical_family = "holdout" if mode == "lexical_holdout" else "train"
            template_family = "holdout" if mode == "template_holdout" else "train"
            order = rng.choice(
                _HOLDOUT_ORDERS if mode == "order_holdout" else _TRAIN_ORDERS
            )
            text, spec, metadata = _surface_text(
                language=language,
                family=family,
                assignment=assignment,
                lexical_family=lexical_family,
                template_family=template_family,
                clause_order=order,
                rng=rng,
            )
            if mode == "negation_preserve":
                metadata["negation_focus"] = True
                untouched = spec.preserve
                if untouched:
                    preserve_clause = _render_preserve(
                        language, untouched, "train", rng
                    )
                    text = preserve_clause + ". " + text
            if mode == "cross_language":
                metadata["pair_id"] = f"pair-{pair_index:04d}"
            row = _row(
                text=text,
                language=language,
                status=status,
                family=family,
                specification=spec,
                code=None,
                template_family=f"supported_{metadata['template_index']}",
                lexical_family=lexical_family,
                metadata=metadata,
            )
        else:
            text, code, metadata = _negative_text(status, language, rng)
            row = _row(
                text=text,
                language=language,
                status=status,
                family=None,
                specification=None,
                code=code,
                template_family=f"negative_{code}",
                lexical_family="train",
                metadata=metadata,
            )
        normalized = normalize_language_text(row["text"])
        if normalized in local_seen or normalized in seen_normalized:
            continue
        local_seen.add(normalized)
        rows.append(row)
    seen_normalized.update(local_seen)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _values(rows: list[dict[str, Any]], key: str) -> set[str]:
    return {str(row[key]) for row in rows}


def _spec_signatures(rows: list[dict[str, Any]]) -> set[str]:
    return {
        json.dumps(
            row["canonical_specification"], sort_keys=True, separators=(",", ":")
        )
        for row in rows
        if row["canonical_specification"] is not None
    }


def _split_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "language": dict(sorted(Counter(row["language"] for row in rows).items())),
        "status": dict(sorted(Counter(row["status"] for row in rows).items())),
        "semantic_family": dict(
            sorted(Counter(str(row["semantic_family"]) for row in rows).items())
        ),
        "surface_template_family_count": len(_values(rows, "surface_template_family")),
        "lexical_family_count": len(_values(rows, "lexical_family")),
        "specification_count": len(_spec_signatures(rows)),
    }


def generate_language_dataset(
    output_dir: Path,
    *,
    split_counts: dict[str, int] | None = None,
    seed: int = 23_000,
) -> dict[str, Any]:
    counts = dict(DEFAULT_SPLIT_COUNTS if split_counts is None else split_counts)
    modes = {
        "train": "train",
        "validation": "validation",
        "test_id": "id",
        "test_lexical_holdout": "lexical_holdout",
        "test_template_holdout": "template_holdout",
        "test_variable_permutation": "variable_permutation",
        "test_order_holdout": "order_holdout",
        "test_cross_language": "cross_language",
        "test_ambiguous": "ambiguous",
        "test_contradictory": "contradictory",
        "test_unsupported": "unsupported",
        "test_negation_preserve": "negation_preserve",
    }
    global_seen: set[str] = set()
    splits: dict[str, list[dict[str, Any]]] = {}
    for index, (split, count) in enumerate(counts.items()):
        splits[split] = _generate_rows(
            count=count,
            seed=seed + index * 997,
            mode=modes[split],
            seen_normalized=global_seen,
        )
        _write_jsonl(output_dir / f"{split}.jsonl", splits[split])

    train = splits["train"]
    train_text = {row["text"] for row in train}
    train_normalized = {normalize_language_text(row["text"]) for row in train}
    train_templates = _values(train, "surface_template_family")
    train_lexical = _values(train, "lexical_family")
    train_specs = _spec_signatures(train)
    overlap: dict[str, Any] = {}
    for split, rows in splits.items():
        if split == "train":
            continue
        overlap[split] = {
            "exact_text": len(train_text & {row["text"] for row in rows}),
            "normalized_text": len(
                train_normalized
                & {normalize_language_text(row["text"]) for row in rows}
            ),
            "surface_template": len(
                train_templates & _values(rows, "surface_template_family")
            ),
            "lexical_family": len(train_lexical & _values(rows, "lexical_family")),
            "specification": len(train_specs & _spec_signatures(rows)),
        }
    pair_groups: dict[str, list[dict[str, Any]]] = {}
    for row in splits["test_cross_language"]:
        pair_groups.setdefault(row["metadata"]["pair_id"], []).append(row)
    cross_pair_valid = all(
        len(pair) == 2
        and {row["language"] for row in pair} == {"ru", "en"}
        and len(_spec_signatures(pair)) == 1
        for pair in pair_groups.values()
    )
    model_visible_id_hits = sum(
        bool(re.search(r"(?:sample|task|pair)[-_ ]?\d{3,}", row["text"], re.IGNORECASE))
        for rows in splits.values()
        for row in rows
    )
    manifest = {
        "schema_version": 1,
        "seed": seed,
        "counts": counts,
        "total_count": sum(counts.values()),
        "splits": {name: _split_summary(rows) for name, rows in splits.items()},
        "train_overlap_audit": overlap,
        "cross_language_pair_count": len(pair_groups),
        "cross_language_pairs_semantically_equal": cross_pair_valid,
        "model_visible_sample_id_hits": model_visible_id_hits,
        "normalized_text_globally_unique": len(global_seen) == sum(counts.values()),
        "sha256": {
            split: hashlib.sha256(
                (output_dir / f"{split}.jsonl").read_bytes()
            ).hexdigest()
            for split in splits
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def load_language_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
