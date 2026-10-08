"""Prepare workbook additions, without authoring Excel or admitting training data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
WORD = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:[-’'][A-Za-zА-Яа-яЁё]+)*")
XML_INVALID = re.compile("[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def spreadsheet_text(value: str) -> str:
    """Visible reversible display escapes; never erase source text or XML controls."""
    return XML_INVALID.sub(lambda m: "\\u" + f"{ord(m.group()):04x}", value)


def digest(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normal(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip().casefold()


def read_saved_workbook(file: Path) -> tuple[list, list, list, list]:
    """Read-only XML avoids losing saved user values to a stale seed JSON."""
    with ZipFile(file) as archive:
        assert archive.testzip() is None
        metadata = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet_names = [
            sheet.get("name") for sheet in metadata.findall("s:sheets/s:sheet", NS)
        ]
        if sheet_names != ["Словарь", "Медиа"]:
            raise ValueError(
                "Workbook sheets changed; preserve them with an explicit schema migration"
            )
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(si.itertext()) for si in shared.findall("s:si", NS)]
        result = []
        for sheet_number, width in ((1, 13), (2, 12)):
            sheet = ET.fromstring(
                archive.read(f"xl/worksheets/sheet{sheet_number}.xml")
            )
            records = {}
            for row in sheet.findall(".//s:sheetData/s:row", NS):
                number = int(row.get("r"))
                if number < 8:
                    continue
                values = [None] * width
                for cell in row.findall("s:c", NS):
                    letters = re.match("[A-Z]+", cell.get("r")).group()
                    col = 0
                    for letter in letters:
                        col = col * 26 + ord(letter) - 64
                    if col > width:
                        raise ValueError(
                            "User added columns; preserve them with a schema migration"
                        )
                    if cell.find("s:f", NS) is not None:
                        raise ValueError(
                            "User formulas require explicit preservation; do not flatten"
                        )
                    value = cell.find("s:v", NS)
                    if cell.get("t") == "s":
                        parsed = strings[int(value.text)]
                    elif cell.get("t") == "inlineStr":
                        parsed = "".join(cell.find("s:is", NS).itertext())
                    elif cell.get("t") == "str":
                        parsed = value.text if value is not None else None
                    elif value is None:
                        parsed = None
                    elif cell.get("t") == "b":
                        parsed = value.text == "1"
                    else:
                        parsed = float(value.text)
                        if parsed.is_integer():
                            parsed = int(parsed)
                    values[col - 1] = parsed
                records[number] = values
            header = records.pop(8)
            expected_headers = (
                [
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
                ]
                if sheet_number == 1
                else [
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
                ]
            )
            if header != expected_headers:
                raise ValueError(
                    "Column meaning/order changed; explicit schema migration required"
                )
            rows = [
                v
                for _, v in sorted(records.items())
                if any(x not in (None, "") for x in v)
            ]
            result.extend([header, rows])
    return tuple(result)


def run(
    workbook: Path, corpus: Path, output: Path, manifest: Path, dictionaries: Path
) -> dict:
    sys.path.insert(0, str(dictionaries))
    import pymorphy3

    morphology = pymorphy3.MorphAnalyzer()
    workbook_sha = digest(workbook)
    wh, words, mh, existing_media = read_saved_workbook(workbook)
    source_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    books = {b["original_filename"]: b for b in source_manifest["books"]}
    words = [r + [""] for r in words]
    wh = wh + ["Медиа — разбиение не назначено"]
    by_id = {r[0]: r for r in words}
    alias_index = defaultdict(set)

    def index_word(r):
        alias_index[normal(r[1])].add(r[0])
        for alias in str(r[4] or "").split(";"):
            if alias.strip():
                alias_index[normal(alias)].add(r[0])

    for r in words:
        index_word(r)
    sequence = max(int(r[0][2:]) for r in words if re.fullmatch(r"vc\d+", str(r[0])))
    media = [r + [""] * 7 for r in existing_media]
    mh += [
        "Надпись / предложенный текст",
        "Полная сцена",
        "Проверяющий",
        "Допуск обучения",
        "Тип ресурса",
        "Печатная страница",
        "Координаты PDF",
    ]
    review_coverage = defaultdict(set)
    review_files = []
    audit_notes = defaultdict(list)
    role_overrides = {}
    audit = corpus / "reviews/math/independent-audit.json"
    if audit.exists():
        review_files.append({"path": str(audit), "sha256": digest(audit)})
        for comparison in json.loads(audit.read_text(encoding="utf-8"))["comparisons"]:
            path = str(Path(comparison["media_path"]).resolve())
            if digest(Path(path)) != comparison["media_sha256"]:
                raise ValueError("Audit media identity mismatch")
            audit_notes[path].append(
                comparison["judgment"] + ": " + comparison["review_note"]
            )
            if "0095" in Path(path).stem and comparison["proposed_word"] == "наушники":
                role_overrides[path] = "Учебная пиктограмма"
    audit = corpus / "reviews/world_language/independent-math-audit.json"
    queue = corpus / "reviews/math/blind-image-queue.json"
    if audit.exists() and queue.exists():
        review_files.extend(
            {"path": str(p), "sha256": digest(p)} for p in (audit, queue)
        )
        queued = {r["item"]: r for r in json.loads(queue.read_text(encoding="utf-8"))}
        for item in json.loads(audit.read_text(encoding="utf-8"))["items"]:
            audit_notes[str(Path(queued[item["item"]]["image"]).resolve())].append(
                item["result"]
                + ": "
                + item.get(
                    "recommendation",
                    "Независимое чтение совпало; пользователь ещё не проверил.",
                )
            )
    reviewed_links = defaultdict(list)
    unresolved = []
    reviewed_occurrences = 0
    new_visual = 0
    for filename in sorted(corpus.glob("reviews/*/*annotations.json")):
        annotation = json.loads(filename.read_text(encoding="utf-8"))
        if annotation.get("training_admitted", False):
            raise ValueError("Catalogue preparation cannot admit training")
        review_files.append({"path": str(filename), "sha256": digest(filename)})
        for b in annotation["books"]:
            assert b["source_sha256"] == books[b["filename"]]["sha256"]
            review_coverage[b["filename"]].update(b["pages_visually_reviewed"])
        unresolved.extend(annotation.get("unresolved", []))
        for c in annotation["concepts"]:
            if len(c["description"].split()) > 20:
                raise ValueError("Description exceeds user limit: " + c["word"])
            target = c.get("existing_id")
            if target is not None and target not in by_id:
                raise ValueError("Unknown existing concept ID")
            if target is None:
                matches = alias_index.get(normal(c["word"]), set())
                if len(matches) == 1:
                    target = next(iter(matches))
                else:
                    sequence += 1
                    target = f"vc{sequence:04d}"
                    aliases = c.get("aliases", [])
                    if isinstance(aliases, list):
                        aliases = "; ".join(aliases)
                    row = [
                        target,
                        c["word"],
                        c["description"],
                        c.get("category", "Предмет из учебника"),
                        aliases,
                        "Сбор материалов",
                        None,
                        None,
                        "",
                        "",
                        "",
                        "",
                        "Подпись предложена агентом по изображению; требуется пользовательское подтверждение. Обучение не запускалось.",
                        "",
                    ]
                    words.append(row)
                    by_id[target] = row
                    index_word(row)
                    new_visual += 1
            for ordinal, e in enumerate(c["evidence"]):
                if (
                    e.get("training_admitted", False)
                    or e.get("split", "UNASSIGNED") != "UNASSIGNED"
                ):
                    raise ValueError(
                        "Review assets must remain unassigned and unadmitted"
                    )
                book = books[e["filename"]]
                assert 1 <= e["pdf_page"] <= book["pages"]
                image = Path(e["media_path"])
                if (
                    not image.resolve().is_relative_to(corpus.resolve())
                    or digest(image) != e["media_sha256"]
                ):
                    raise ValueError("Review media identity/confinement failure")
                context = (
                    e.get("whole_page_path")
                    or e.get("parent_scene_path")
                    or e.get("context_path")
                )
                context_sha = (
                    e.get("whole_page_sha256")
                    or e.get("parent_scene_sha256")
                    or e.get("context_sha256")
                )
                if context and (
                    not Path(context).resolve().is_relative_to(corpus.resolve())
                    or not context_sha
                    or digest(Path(context)) != context_sha
                ):
                    raise ValueError("Context identity/confinement mismatch")
                label_context = e.get("label_context_path")
                if label_context and (
                    not Path(label_context).resolve().is_relative_to(corpus.resolve())
                    or digest(Path(label_context)) != e["label_context_sha256"]
                ):
                    raise ValueError("Label context identity/confinement mismatch")
                mid = (
                    "review-"
                    + hashlib.sha256(
                        (
                            annotation["reviewer"] + str(image) + target + str(ordinal)
                        ).encode()
                    ).hexdigest()[:16]
                )
                visible = e.get("visible_text") or e.get("label_text_visible") or ""
                role = role_overrides.get(str(image.resolve())) or {
                    "object": "Объект сцены",
                    "scene-instance": "Объект сцены",
                    "scene": "Сцена",
                    "pictogram": "Учебная пиктограмма",
                    "symbol": "Символ",
                    "diagram": "Схема",
                    "decorative": "Декорация",
                    "decoration": "Декорация",
                }.get(e.get("role"), e.get("role", "Неоднозначно"))
                bbox = e.get("bbox_points") or e.get("bbox")
                notes = [e.get("notes", "")]
                notes.extend(audit_notes.get(str(image.resolve()), []))
                if e.get("printed_label_text"):
                    notes.append(
                        "Название взято из подписи, не доказано независимым узнаванием вида: "
                        + e["printed_label_text"]
                    )
                if label_context:
                    notes.append("Контекст с подписью: " + label_context)
                if e.get("text_leakage_status"):
                    notes.append("Надписи в вырезке: " + e["text_leakage_status"])
                if e.get("duplicate_source_occurrences"):
                    notes.append(
                        "Повторные, не независимые источники: "
                        + json.dumps(
                            e["duplicate_source_occurrences"], ensure_ascii=False
                        )
                    )
                media.append(
                    [
                        mid,
                        target,
                        str(image),
                        "Не назначено",
                        role,
                        "Рисунок / фото из PDF",
                        "\n".join(n for n in notes if n),
                        f"{e['filename']}; PDF {e['pdf_page']}; SHA {book['sha256']}",
                        "adu.by; некоммерческое использование; ограничения исходника сохраняются",
                        book["sha256"][:16] + f"-p{e['pdf_page']:04d}",
                        e["media_sha256"],
                        "Агент проверил; ожидает пользователя",
                        visible,
                        str(context or ""),
                        annotation["reviewer"],
                        "Нет",
                        "Проверенная агентом вырезка — не gold",
                        e.get("printed_page"),
                        json.dumps(bbox) if bbox else "",
                    ]
                )
                reviewed_links[target].append(str(image))
                reviewed_occurrences += 1
    for target, paths in reviewed_links.items():
        # Never misassign unassigned assets to the existing training/regression fields.
        by_id[target][13] = "\n".join(dict.fromkeys(paths))

    corrections_path = corpus / "geometry-corrections/replacement-index.json"
    corrections = {}
    if corrections_path.exists():
        for replacement in json.loads(corrections_path.read_text(encoding="utf-8"))[
            "replacements"
        ]:
            replacement_path = (corpus / replacement["corrected_record"]).resolve()
            if not replacement_path.is_relative_to(corpus.resolve()):
                raise ValueError("Correction path escaped corpus")
            if digest(replacement_path) != replacement["corrected_record_sha256"]:
                raise ValueError("Correction record hash mismatch")
            corrections[replacement["page_id"]] = replacement_path
    text_entries = {}
    observed_pages = defaultdict(set)
    ocr_pages = defaultdict(set)
    lexical_matches = 0
    missing_ocr = []
    raw_assets = []

    @lru_cache(maxsize=100000)
    def analyse(word):
        if re.search("[А-Яа-яЁё]", word):
            parsed = morphology.parse(word)
            known = [p for p in parsed if p.is_known]
            candidates = known or parsed
            lemmas = sorted({p.normal_form for p in candidates})
            ambiguous = len(lemmas) > 1
            key = "surface:" + word if ambiguous or not known else "lemma:" + lemmas[0]
            label = word if ambiguous or not known else lemmas[0]
            return (
                key,
                label,
                lemmas,
                "ru",
                "Словоформа / значение неоднозначны"
                if ambiguous
                else (
                    "Нет словарного подтверждения"
                    if not known
                    else "Смысл по контексту не проверен"
                ),
            )
        return "surface:" + word, word, [], "latin", "Язык и значение требуют проверки"

    def tokens(text, record, method, text_path):
        nonlocal lexical_matches
        for match in WORD.finditer(text):
            surface = normal(match.group())
            if len(surface) > 60:
                continue
            key, label, lemmas, language, reason = analyse(surface)
            if key not in text_entries:
                text_entries[key] = {
                    "id": "tx-" + hashlib.sha256(key.encode()).hexdigest()[:16],
                    "word": label,
                    "forms": Counter(),
                    "lemmas": lemmas,
                    "language": language,
                    "reason": reason,
                    "counts": Counter(),
                    "concepts": set(),
                    "sources": [],
                    "paths": [],
                    "context": "",
                }
            entry = text_entries[key]
            entry["forms"][surface] += 1
            entry["counts"][method] += 1
            matches = set(alias_index.get(surface, set()))
            for lemma in lemmas:
                matches.update(alias_index.get(lemma, set()))
            if matches:
                lexical_matches += 1
                entry["concepts"].update(matches)
            source = (
                f"{record['original_filename']}; PDF {record['pdf_page']}; {method}"
            )
            if source not in entry["sources"] and len(entry["sources"]) < 5:
                entry["sources"].append(source)
            if text_path not in entry["paths"] and len(entry["paths"]) < 5:
                entry["paths"].append(text_path)
            if not entry["context"]:
                entry["context"] = " ".join(
                    text[max(0, match.start() - 55) : match.end() + 90].split()
                )

    for file in sorted(corpus.glob("books/*/records/*.json")):
        record = json.loads(file.read_text(encoding="utf-8"))
        if record["page_id"] in corrections:
            file = corrections[record["page_id"]]
            record = json.loads(file.read_text(encoding="utf-8"))
        observed_pages[record["original_filename"]].add(record["pdf_page"])
        for kind, asset in [
            ("PAGE_CONTEXT", record["page_preview"]),
            ("PDF_TEXT", record["text_file"]),
        ]:
            absolute = str((corpus / asset["path"]).resolve())
            raw_assets.append({"path": absolute, "sha256": asset["sha256"]})
            media.append(
                [
                    record["page_id"] + "-" + kind,
                    "",
                    absolute,
                    "Не назначено",
                    "Полная страница" if kind == "PAGE_CONTEXT" else "Текст PDF",
                    "PDF",
                    "Семантическая разметка не завершена",
                    f"{record['original_filename']}; PDF {record['pdf_page']}; SHA {record['original_sha256']}",
                    "adu.by; ограничения исходника сохраняются",
                    record["family_id"],
                    asset["sha256"],
                    "Черновик",
                    "",
                    "",
                    "Автоматическое извлечение",
                    "Нет",
                    kind,
                    None,
                    "",
                ]
            )
        tokens(
            record["text"],
            record,
            "PDF",
            str((corpus / record["text_file"]["path"]).resolve()),
        )
        ocr = file.parent.parent / "ocr" / file.name
        if ocr.exists():
            result = json.loads(ocr.read_text(encoding="utf-8"))
            assert (
                result["page_id"] == record["page_id"]
                and result["image_sha256"] == record["page_preview"]["sha256"]
            )
            ocr_pages[record["original_filename"]].add(record["pdf_page"])
            tokens(result["text"], record, "OCR", str(ocr))
            raw_assets.append({"path": str(ocr), "sha256": digest(ocr)})
            media.append(
                [
                    record["page_id"] + "-OCR",
                    "",
                    str(ocr),
                    "Не назначено",
                    "Текст OCR",
                    "JSON",
                    "Предложенный текст, не проверен",
                    f"{record['original_filename']}; PDF {record['pdf_page']}",
                    "adu.by; ограничения исходника сохраняются",
                    record["family_id"],
                    digest(ocr),
                    "Черновик",
                    "",
                    "",
                    "Windows.Media.Ocr ru",
                    "Нет",
                    "OCR_DRAFT",
                    None,
                    "",
                ]
            )
        else:
            missing_ocr.append(record["page_id"])
        for image in record["images"]:
            asset = image["media"]
            absolute = str((corpus / asset["path"]).resolve())
            raw_assets.append({"path": absolute, "sha256": asset["sha256"]})
            media.append(
                [
                    image["media_id"],
                    "",
                    absolute,
                    "Не назначено",
                    "Неоднозначно",
                    "Изображение PDF",
                    "Размещение raster-ресурса, не обязательно целый предмет",
                    f"{record['original_filename']}; PDF {record['pdf_page']}; SHA {record['original_sha256']}",
                    "adu.by; ограничения исходника сохраняются",
                    record["family_id"],
                    asset["sha256"],
                    "Черновик",
                    "",
                    str((corpus / record["page_preview"]["path"]).resolve()),
                    "Автоматическое извлечение",
                    "Нет",
                    "RASTER_PLACEMENT_NOT_OBJECT",
                    None,
                    json.dumps(image["bbox"]),
                ]
            )

    text_headers = [
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
    ]
    text_rows = []
    for _, entry in sorted(
        text_entries.items(), key=lambda kv: (kv[1]["language"], kv[1]["word"])
    ):
        text_rows.append(
            [
                entry["id"],
                entry["word"],
                "; ".join(entry["forms"]),
                "; ".join(sorted(entry["concepts"])),
                entry["counts"]["PDF"],
                entry["counts"]["OCR"],
                entry["language"],
                "Кандидат; не допущен к обучению",
                entry["reason"],
                "Значение требует проверки по контексту источника.",
                "\n".join(entry["sources"]),
                entry["context"],
                "\n".join(entry["paths"]),
            ]
        )
    coverage_headers = [
        "Книга",
        "SHA оригинала",
        "Страниц PDF",
        "Страниц извлечено",
        "Страниц OCR",
        "Визуально просмотрено",
        "Исправлений геометрии",
        "Допуск обучения",
        "Ограничения",
    ]
    coverage = []
    for name, b in books.items():
        coverage.append(
            [
                name,
                b["sha256"],
                b["pages"],
                len(observed_pages[name]),
                len(ocr_pages[name]),
                len(review_coverage[name]),
                sum(
                    json.loads(p.read_text(encoding="utf-8"))["original_filename"]
                    == name
                    for p in corrections.values()
                ),
                "Нет",
                "Автоизвлечение и OCR не равны проверенной разметке всех иллюстраций/слов.",
            ]
        )
    assert len({r[0] for r in words}) == len(words)
    assert len({r[0] for r in media}) == len(media)
    assert all(len(str(r[2]).split()) <= 20 for r in words)
    result = {
        "schema": 1,
        "input_workbook_sha256": workbook_sha,
        "training_started": False,
        "training_admitted": False,
        "words_headers": wh,
        "words": words,
        "media_headers": mh,
        "media": media,
        "text_headers": text_headers,
        "text": text_rows,
        "coverage_headers": coverage_headers,
        "coverage": coverage,
        "raw_assets": raw_assets,
        "review_files": review_files,
        "unresolved": unresolved,
        "stats": {
            "concepts": len(words),
            "new_visual_concepts": new_visual,
            "reviewed_occurrences": reviewed_occurrences,
            "media_rows": len(media),
            "text_entries": len(text_rows),
            "effective_pages": sum(map(len, observed_pages.values())),
            "ocr_pages": sum(map(len, ocr_pages.values())),
            "pages_visually_reviewed": sum(map(len, review_coverage.values())),
            "corrected_pages": len(corrections),
            "missing_ocr": missing_ocr,
            "lexical_occurrence_matches_not_sense_proofs": lexical_matches,
            "limits": "Visual review is a sampled first pass. PDF/OCR tokens and lemma candidates require contextual review.",
        },
    }
    display_escapes = []
    for key in ("words", "media", "text", "coverage"):
        for row_number, row in enumerate(result[key], 9):
            for column, value in enumerate(row, 1):
                if isinstance(value, str) and XML_INVALID.search(value):
                    # Input workbook values must not be silently transformed.
                    old_count = (
                        len(words) - new_visual
                        if key == "words"
                        else len(existing_media)
                        if key == "media"
                        else 0
                    )
                    if row_number - 9 < old_count:
                        raise ValueError(
                            "Saved user cell has unsupported XML text; explicit migration required"
                        )
                    display_escapes.append(
                        {
                            "sheet_key": key,
                            "row": row_number,
                            "column": column,
                            "codepoints": sorted(
                                {
                                    f"U+{ord(m.group()):04X}"
                                    for m in XML_INVALID.finditer(value)
                                }
                            ),
                        }
                    )
                    row[column - 1] = spreadsheet_text(value)
    result["spreadsheet_text_escapes"] = display_escapes
    result["stats"]["xml_display_escaped_cells"] = len(display_escapes)
    if digest(workbook) != workbook_sha:
        raise ValueError("Workbook changed while preparing additions")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result["stats"], ensure_ascii=False))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--workbook", type=Path, required=True)
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--manifest",
        type=Path,
        default=Path("learning_materials/belarus_primary/manifest.json"),
    )
    p.add_argument(
        "--dictionaries",
        type=Path,
        default=Path("D:/ai-brain-data/visual-lexicon/tools/python-libs"),
    )
    a = p.parse_args()
    run(a.workbook, a.corpus, a.output, a.manifest, a.dictionaries)
