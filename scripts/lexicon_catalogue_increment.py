"""Prepare append-only additions from actual saved four-sheet catalogue values.

Reads XLSX with lexicon_catalogue_export.saved_tables, never authors Excel.
The supported schema is exactly 14/19/13/9 columns. Unknown columns, formulas,
renamed sheets or duplicate IDs require explicit migration, never seed rebuild.
Old cells are immutable except append-only unassigned media links in words N.
Overview coverage is separate JSON metadata, not detailed semantic review.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

XML_INVALID = re.compile("[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")
MAX_CELL = 32767
SHEETS = {"Словарь": "words", "Медиа": "media", "Текст": "text", "Покрытие": "coverage"}
HEADERS = {
    "words": [
        "ID понятия",
        "Слово / понятие",
        "Описание — до 20 слов",
        "Категория",
        "Другие названия / начертания",
        "Статус",
        "Полнота проверки, %",
        "Ошибочных принятых ответов",
        "Файлы для обучения",
        "Файлы для регрессии",
        "SHA модели",
        "Отчёт проверки",
        "Ограничения / примечания",
        "Медиа — разбиение не назначено",
    ],
    "media": [
        "ID медиа",
        "ID понятия",
        "Путь к файлу / URL",
        "Разбиение",
        "Роль изображения",
        "Формат: рисунок / фото",
        "Вариант / состояние",
        "Источник / страница / область",
        "Права / лицензия",
        "Группа родственных изображений",
        "SHA-256 файла",
        "Статус разметки",
        "Надпись / предложенный текст",
        "Полная сцена",
        "Проверяющий",
        "Допуск обучения",
        "Тип ресурса",
        "Печатная страница",
        "Координаты PDF",
    ],
    "text": [
        "ID записи",
        "Слово / предлагаемая лемма",
        "Формы в источнике",
        "Возможные ID понятий",
        "Вхождений в PDF-тексте",
        "Вхождений в OCR",
        "Язык",
        "Статус",
        "Причина сомнения",
        "Описание — до 20 слов",
        "Примеры источников",
        "Пример контекста",
        "Файлы текста",
    ],
    "coverage": [
        "Книга",
        "SHA оригинала",
        "Страниц PDF",
        "Страниц извлечено",
        "Страниц OCR",
        "Визуально просмотрено",
        "Исправлений геометрии",
        "Допуск обучения",
        "Ограничения",
    ],
}
ROLES = {
    "scene-contains-object": "Сцена содержит объект",
    "page-contains-symbol": "Страница содержит символ",
    "object": "Объект сцены",
    "scene-instance": "Объект сцены",
    "scene": "Сцена",
    "symbol": "Символ",
    "pictogram": "Учебная пиктограмма",
    "diagram": "Схема",
    "decorative": "Декорация",
    "decoration": "Декорация",
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def saved_tables(path: Path) -> dict:
    source = Path(__file__).with_name("lexicon_catalogue_export.py")
    spec = importlib.util.spec_from_file_location(
        "lexicon_catalogue_export_reader", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.saved_tables(path)


def normal(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def checked_asset(value: str, expected: str, roots: list[Path]) -> Path:
    path = Path(value).resolve()
    if (
        not any(path.is_relative_to(root) for root in roots)
        or not path.is_file()
        or not expected
        or digest(path) != expected
    ):
        raise ValueError("asset source/hash/allowlist mismatch: " + str(path))
    return path


def effective_preview(
    corpus: Path, original: dict, page: int, replacements: dict
) -> dict:
    """Bind a new full-scene association to the canonical effective PDF page."""
    page_id = original["sha256"][:16] + f"-p{page:04d}"
    replacement = replacements.get(page_id)
    relative = (
        replacement["corrected_record"]
        if replacement
        else f"books/{original['sha256'][:16]}/records/{page:04d}.json"
    )
    record_path = (corpus / relative).resolve()
    if not record_path.is_relative_to(corpus) or not record_path.is_file():
        raise ValueError("Effective page record missing or escapes corpus")
    if replacement and (
        replacement["original_sha256"] != original["sha256"]
        or replacement["pdf_page"] != page
        or digest(record_path) != replacement["corrected_record_sha256"]
    ):
        raise ValueError("Effective correction record binding/hash mismatch")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if (
        record["page_id"] != page_id
        or record["pdf_page"] != page
        or record["original_sha256"] != original["sha256"]
        or record["original_filename"] != original["original_filename"]
    ):
        raise ValueError("Effective record original/page identity mismatch")
    return record["page_preview"]


def input_snapshot(tables: dict) -> dict:
    if list(tables) != list(SHEETS):
        raise ValueError("Four-sheet schema/order changed; explicit migration required")
    result = {}
    for name, key in SHEETS.items():
        table = tables[name]
        if (
            table["headers"] != HEADERS[key]
            or not table.get("freeze")
            or not table.get("tables")
        ):
            raise ValueError(
                "Headers or native table/pane schema changed; explicit migration required"
            )
        if any(len(row) != len(HEADERS[key]) for row in table["rows"]):
            raise ValueError("Unknown/missing columns; explicit migration required")
        result[key] = copy.deepcopy(table["rows"])
    for key in ("words", "media", "text"):
        identifiers = [
            row[0] for row in result[key] if any(v not in (None, "") for v in row)
        ]
        if any(not isinstance(value, str) or not value for value in identifiers) or len(
            set(identifiers)
        ) != len(identifiers):
            raise ValueError(
                "Existing IDs missing/duplicated; explicit migration required"
            )
    return result


def append_links(previous, paths: list[str]) -> tuple[str | None, int]:
    if previous not in (None, "") and not isinstance(previous, str):
        raise ValueError("Existing media-link cell is not text; migration required")
    text = previous or ""
    unique = [p for p in dict.fromkeys(paths) if p not in text.splitlines()]
    marker = "Остальные ссылки: лист Медиа, фильтр ID понятия."
    added = 0
    for path in unique:
        suffix = ("\n" if text else "") + path
        reserve = len(marker) + 1 if added + 1 < len(unique) else 0
        if len(text) + len(suffix) + reserve > MAX_CELL:
            break
        text += suffix
        added += 1
    omitted = len(unique) - added
    if omitted and len(text) + len(marker) + (1 if text else 0) <= MAX_CELL:
        text += ("\n" if text else "") + marker
    return text if text or previous is not None else None, omitted


def escape_new_row(row: list, key: str, row_number: int, escapes: list) -> list:
    for column, value in enumerate(row):
        if isinstance(value, str):
            if XML_INVALID.search(value):
                escapes.append(
                    {
                        "sheet_key": key,
                        "row": row_number,
                        "column": column + 1,
                        "codepoints": sorted(
                            {
                                f"U+{ord(m.group()):04X}"
                                for m in XML_INVALID.finditer(value)
                            }
                        ),
                    }
                )
                row[column] = XML_INVALID.sub(
                    lambda match: "\\u" + f"{ord(match.group()):04x}", value
                )
            if len(row[column]) > MAX_CELL:
                raise ValueError(
                    "New cell exceeds Excel limit; explicit migration required"
                )
    return row


def run(
    workbook: Path,
    manifest_path: Path,
    corpus: Path,
    reviews_root: Path,
    output: Path,
    allow_roots: list[Path],
    annotations: list[Path] | None = None,
    previous_prepared: Path | None = None,
) -> dict:
    corpus, reviews_root = corpus.resolve(), reviews_root.resolve()
    roots = [path.resolve() for path in allow_roots]
    if set(roots) != {corpus, reviews_root}:
        raise ValueError(
            "Explicit allowlist must be exactly corpus and supplemental review roots"
        )
    if output.resolve().is_relative_to(corpus) or output.exists():
        raise ValueError("Output must be fresh and outside sealed corpus")
    workbook_sha = digest(workbook)
    manifest_sha = digest(manifest_path)
    input_values = input_snapshot(saved_tables(workbook))
    values = copy.deepcopy(input_values)
    input_counts = {key: len(rows) for key, rows in input_values.items()}
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    books = {book["original_filename"]: book for book in source_manifest["books"]}
    by_id = {row[0]: row for row in values["words"] if row[0]}
    aliases = defaultdict(set)

    def index_word(row):
        aliases[normal(row[1])].add(row[0])
        for alias in re.split(r"[;\n]", str(row[4] or "")):
            if alias.strip():
                aliases[normal(alias)].add(row[0])

    for row in by_id.values():
        index_word(row)
    sequence = max(
        (
            int(identifier[2:])
            for identifier in by_id
            if re.fullmatch(r"vc\d+", identifier)
        ),
        default=0,
    )
    existing_pairs = {(row[1], row[10], row[4]) for row in values["media"]}
    media_ids = {row[0] for row in values["media"] if row[0]}
    known_assets = {
        (str(Path(row[2]).resolve()), row[10]) for row in values["media"] if row[2]
    }
    links, overview, detailed = defaultdict(list), defaultdict(set), defaultdict(set)
    raw_assets, review_files, unresolved, duplicates, escapes = [], [], [], [], []
    history = None
    previous_sha = digest(previous_prepared) if previous_prepared else None
    if previous_prepared:
        previous = json.loads(previous_prepared.read_text(encoding="utf-8"))
        if (
            previous.get("training_started") is not False
            or previous.get("training_admitted") is not False
        ):
            raise ValueError("Previous prepared history admits or started training")
        differences = []
        for key, headers in HEADERS.items():
            if previous.get(key + "_headers") != headers or len(previous[key]) > len(
                input_values[key]
            ):
                raise ValueError(
                    "Previous history schema/prefix missing; migration required"
                )
            for offset, old in enumerate(previous[key]):
                actual = input_values[key][offset]
                if len(old) != len(headers) or old[0] != actual[0]:
                    raise ValueError(
                        "Previous history identity/order mismatch; migration required"
                    )
                for column, (before, current) in enumerate(
                    zip(old, actual, strict=True)
                ):
                    if before != current and not (
                        before in (None, "") and current in (None, "")
                    ):
                        differences.append(
                            {
                                "sheet_key": key,
                                "row_index": offset,
                                "column": column + 1,
                                "policy": "ACTUAL_SAVED_USER_VALUE_PRESERVED",
                            }
                        )
        for review in previous.get("review_files", []):
            checked_asset(review["path"], review["sha256"], [corpus])
            if review not in review_files:
                review_files.append(copy.deepcopy(review))
        for audit in previous.get("spreadsheet_text_escapes", []):
            key = audit["sheet_key"]
            if (
                key not in HEADERS
                or not 1 <= audit["column"] <= len(HEADERS[key])
                or not 9 <= audit["row"] < 9 + len(previous[key])
            ):
                raise ValueError("Previous display escape audit outside history table")
            if audit not in escapes:
                escapes.append(copy.deepcopy(audit))
        history = {
            "path": str(previous_prepared.resolve()),
            "sha256": previous_sha,
            "prefix_rows": {key: len(previous[key]) for key in HEADERS},
            "blank_none_equivalence": True,
            "saved_value_differences_preserved": differences,
            "preserved_review_files": len(review_files),
            "preserved_escape_audits": len(escapes),
            "policy": "Stable identities/order required; actual saved user edits are retained, never replaced with history.",
        }
    source_verified = {}
    blocked_paths = set()
    replacement_index = corpus / "geometry-corrections/replacement-index.json"
    replacements = {}
    if replacement_index.exists():
        for replacement in json.loads(replacement_index.read_text(encoding="utf-8"))[
            "replacements"
        ]:
            if replacement["page_id"] in replacements:
                raise ValueError("Duplicate effective page correction")
            replacements[replacement["page_id"]] = replacement
    effective_report = corpus / "effective-coverage-report.json"
    if effective_report.exists():
        for superseded in json.loads(effective_report.read_text(encoding="utf-8"))[
            "superseded_unusable_media"
        ]:
            blocked_paths.add((corpus / superseded["page_preview"]["path"]).resolve())
            blocked_paths.update(
                (corpus / item["path"]).resolve() for item in superseded["images"]
            )
    annotation_paths = sorted(
        annotations
        if annotations is not None
        else reviews_root.glob("**/*annotations.json")
    )
    for annotation_path in annotation_paths:
        if not annotation_path.resolve().is_relative_to(reviews_root):
            raise ValueError("Supplemental annotation outside review root")
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        if annotation.get("training_admitted", False):
            raise ValueError("Supplemental annotation admits training")
        review = {
            "path": str(annotation_path.resolve()),
            "sha256": digest(annotation_path),
        }
        if review not in review_files:
            review_files.append(review)
        declared_books = {}
        for book in annotation["books"]:
            original = books[book["filename"]]
            if book["source_sha256"] != original["sha256"]:
                raise ValueError("Supplemental book original SHA mismatch")
            declared_books[book["filename"]] = book["source_sha256"]
            for field, target in (
                ("pages_overviewed", overview),
                ("pages_full_resolution_reviewed", detailed),
            ):
                for page in book.get(field, []):
                    if not isinstance(page, int) or not 1 <= page <= original["pages"]:
                        raise ValueError("Supplemental coverage page out of bounds")
                    target[book["filename"]].add(page)
        unresolved.extend(annotation.get("unresolved", []))
        for concept in annotation["concepts"]:
            if (
                not concept.get("word")
                or not isinstance(concept.get("description"), str)
                or len(concept["description"].split()) > 20
            ):
                raise ValueError("New description/word invalid or exceeds 20 words")
            target = concept.get("existing_id")
            if target is not None and target not in by_id:
                raise ValueError("Unknown explicit existing concept ID")
            if target is None:
                matches = aliases.get(normal(concept["word"]), set())
                if len(matches) == 1:
                    target = next(iter(matches))
                else:
                    sequence += 1
                    target = f"vc{sequence:04d}"
                    other_names = concept.get("aliases", [])
                    other_names = (
                        "; ".join(other_names)
                        if isinstance(other_names, list)
                        else other_names
                    )
                    row = [
                        target,
                        concept["word"],
                        concept["description"],
                        concept.get("category", "Предмет из учебника"),
                        other_names,
                        "Сбор материалов",
                        None,
                        None,
                        "",
                        "",
                        "",
                        "",
                        "Предложено агентом; ожидает пользовательской проверки. Обучение не запускалось.",
                        "",
                    ]
                    row = escape_new_row(
                        row, "words", len(values["words"]) + 9, escapes
                    )
                    values["words"].append(row)
                    by_id[target] = row
                    index_word(row)
                    if len(matches) > 1:
                        unresolved.append(
                            {
                                "word": concept["word"],
                                "issue": "AMBIGUOUS_EXACT_ALIAS_NOT_MERGED",
                                "candidate_ids": sorted(matches),
                                "new_id": target,
                            }
                        )
            for evidence in concept["evidence"]:
                name = evidence["filename"]
                original = books[name]
                if (
                    declared_books.get(name) != original["sha256"]
                    or evidence.get("source_sha256", declared_books.get(name))
                    != original["sha256"]
                ):
                    raise ValueError(
                        "Each new label needs verified original source SHA"
                    )
                source = (manifest_path.parent / original["path"]).resolve()
                if not source.is_relative_to(manifest_path.parent.resolve()):
                    raise ValueError("Original source path escapes manifest corpus")
                if source not in source_verified:
                    if digest(source) != original["sha256"]:
                        raise ValueError("Original source bytes changed")
                    source_verified[source] = original["sha256"]
                page = evidence["pdf_page"]
                if (
                    not isinstance(page, int)
                    or isinstance(page, bool)
                    or not 1 <= page <= original["pages"]
                ):
                    raise ValueError("New label PDF page out of bounds")
                if (
                    evidence.get("training_admitted", False)
                    or evidence.get("split", "UNASSIGNED") != "UNASSIGNED"
                ):
                    raise ValueError("New evidence must remain unassigned/unadmitted")
                image = checked_asset(
                    evidence["media_path"], evidence["media_sha256"], roots
                )
                context_value = (
                    evidence.get("whole_page_path")
                    or evidence.get("parent_scene_path")
                    or evidence.get("context_path")
                )
                context_sha = (
                    evidence.get("whole_page_sha256")
                    or evidence.get("parent_scene_sha256")
                    or evidence.get("context_sha256")
                )
                if not context_value or not context_sha:
                    raise ValueError(
                        "Every new label requires preserved context path and SHA"
                    )
                context = checked_asset(context_value, context_sha, roots)
                if image in blocked_paths or context in blocked_paths:
                    raise ValueError(
                        "Superseded geometry asset cannot re-enter current catalogue"
                    )
                role_key = evidence.get("role")
                if role_key not in ROLES:
                    raise ValueError(
                        "Unknown supplemental role; explicit migration required"
                    )
                if role_key in ("scene-contains-object", "page-contains-symbol"):
                    preview = effective_preview(corpus, original, page, replacements)
                    canonical = checked_asset(
                        str(corpus / preview["path"]), preview["sha256"], [corpus]
                    )
                    if (
                        image != canonical
                        or context != canonical
                        or evidence["media_sha256"] != preview["sha256"]
                        or context_sha != preview["sha256"]
                        or evidence.get(
                            "page_id", original["sha256"][:16] + f"-p{page:04d}"
                        )
                        != original["sha256"][:16] + f"-p{page:04d}"
                    ):
                        raise ValueError(
                            "Full-scene association does not match effective page preview"
                        )
                role = ROLES[role_key]
                pair = (target, evidence["media_sha256"], role)
                if pair in existing_pairs:
                    duplicates.append(
                        {
                            "concept_id": target,
                            "sha256": pair[1],
                            "role": role,
                            "review": str(annotation_path),
                            "source": name,
                            "pdf_page": page,
                        }
                    )
                    continue
                existing_pairs.add(pair)
                identifier = (
                    "review2-"
                    + hashlib.sha256("|".join(pair).encode("utf-8")).hexdigest()[:20]
                )
                if identifier in media_ids:
                    raise ValueError("New stable media ID collision")
                media_ids.add(identifier)
                overview_only = role_key in (
                    "scene-contains-object",
                    "page-contains-symbol",
                ) or evidence.get("overview_only", False)
                notes = evidence.get("notes", "")
                if overview_only:
                    notes += "\nОбзорная связь: сцена содержит понятие; не локализация и не single-object gold."
                box = evidence.get("bbox_points") or evidence.get("bbox")
                row = [
                    identifier,
                    target,
                    str(image),
                    "Не назначено",
                    role,
                    "Рисунок / фото из PDF",
                    notes,
                    f"{name}; PDF {page}; SHA {original['sha256']}",
                    "adu.by; некоммерческое использование; ограничения исходника сохраняются",
                    original["sha256"][:16] + f"-p{page:04d}",
                    evidence["media_sha256"],
                    "Агент предложил; ожидает пользователя",
                    evidence.get("visible_text")
                    or evidence.get("label_text_visible")
                    or "",
                    str(context),
                    annotation["reviewer"],
                    "Нет",
                    "CONTACT_OVERVIEW_CONTAINS_OBJECT_NOT_GOLD"
                    if overview_only
                    else "AGENT_REVIEW_DRAFT_NOT_GOLD",
                    evidence.get("printed_page"),
                    json.dumps(box) if box else "",
                ]
                values["media"].append(
                    escape_new_row(row, "media", len(values["media"]) + 9, escapes)
                )
                links[target].append(str(image))
                for asset_path, asset_sha in (
                    (image, evidence["media_sha256"]),
                    (context, context_sha),
                ):
                    asset_pair = (str(asset_path), asset_sha)
                    if asset_pair not in known_assets:
                        known_assets.add(asset_pair)
                        raw_assets.append(
                            {"path": asset_pair[0], "sha256": asset_pair[1]}
                        )
    omitted_links = {}
    for target, paths in links.items():
        by_id[target][13], omitted = append_links(by_id[target][13], paths)
        if omitted:
            omitted_links[target] = omitted
    for key in ("media", "text", "coverage"):
        if values[key][: input_counts[key]] != input_values[key]:
            raise ValueError("Existing table rows changed")
    if any(
        current[:13] != old[:13]
        or not str(current[13] or "").startswith(str(old[13] or ""))
        for current, old in zip(
            values["words"][: input_counts["words"]], input_values["words"], strict=True
        )
    ):
        raise ValueError("Saved user word values lost or replaced")
    if (
        digest(workbook) != workbook_sha
        or digest(manifest_path) != manifest_sha
        or any(digest(source) != value for source, value in source_verified.items())
        or (previous_prepared is not None and digest(previous_prepared) != previous_sha)
        or any(
            digest(Path(review["path"])) != review["sha256"] for review in review_files
        )
    ):
        raise ValueError("Workbook/original source changed during preparation")
    coverage = values["coverage"]
    result = {
        "schema": 2,
        "incremental": True,
        "previous_prepared_history": history,
        "input_workbook_sha256": workbook_sha,
        "input_rows": input_counts,
        "input_headers": copy.deepcopy(HEADERS),
        "training_started": False,
        "training_admitted": False,
        "raw_assets": raw_assets,
        "review_files": review_files,
        "unresolved": unresolved,
        "spreadsheet_text_escapes": escapes,
        "overview_coverage": {
            "pages_by_book": {name: sorted(pages) for name, pages in overview.items()},
            "full_resolution_pages_by_book_not_promoted_to_detailed_coverage": {
                name: sorted(pages) for name, pages in detailed.items()
            },
            "limit": "contact overview is not exhaustive object localisation or verified labels",
        },
        "deduplicated_evidence": duplicates,
        "omitted_cell_links_still_in_media": omitted_links,
        "stats": {
            "input_concepts": input_counts["words"],
            "input_media_rows": input_counts["media"],
            "concepts": len(values["words"]),
            "new_visual_concepts": len(values["words"]) - input_counts["words"],
            "media_rows": len(values["media"]),
            "new_media_rows": len(values["media"]) - input_counts["media"],
            "text_entries": len(values["text"]),
            "effective_pages": sum(row[3] for row in coverage),
            "ocr_pages": sum(row[4] for row in coverage),
            "pages_visually_reviewed": sum(row[5] for row in coverage),
            "corrected_pages": sum(row[6] for row in coverage),
            "missing_ocr": [row[0] for row in coverage if row[3] != row[4]],
            "overview_pages": sum(len(pages) for pages in overview.values()),
            "reviewed_occurrences": len(values["media"]) - input_counts["media"],
            "xml_display_escaped_cells": len(escapes),
            "limits": "Preserved saved user values; supplemental overview associations remain proposals, not training gold.",
        },
    }
    for key, rows in values.items():
        result[key] = rows
        result[key + "_headers"] = copy.deepcopy(HEADERS[key])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--reviews-root", type=Path, required=True)
    parser.add_argument("--allow-root", type=Path, action="append", required=True)
    parser.add_argument("--annotations", type=Path, action="append")
    parser.add_argument("--previous-prepared", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepared = run(
        args.workbook,
        args.manifest,
        args.corpus,
        args.reviews_root,
        args.output,
        args.allow_root,
        args.annotations,
        args.previous_prepared,
    )
    print(json.dumps(prepared["stats"], ensure_ascii=True))
