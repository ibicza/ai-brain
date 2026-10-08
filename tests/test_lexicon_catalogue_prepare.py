"""Focused catalogue preservation tests; ZIP/XML fixtures are not deliverables."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest

SPEC = importlib.util.spec_from_file_location(
    "lexicon_catalogue_prepare", Path(__file__).parents[1] / "scripts/lexicon_catalogue_prepare.py"
)
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)

WORDS_HEADERS = [
    "ID понятия", "Слово / понятие", "Описание — до 20 слов", "Категория",
    "Другие названия / начертания", "Статус", "Полнота проверки, %",
    "Ошибочных принятых ответов", "Файлы для обучения", "Файлы для регрессии",
    "SHA модели", "Отчёт проверки", "Ограничения / примечания",
]
MEDIA_HEADERS = [
    "ID медиа", "ID понятия", "Путь к файлу / URL", "Разбиение", "Роль изображения",
    "Формат: рисунок / фото", "Вариант / состояние", "Источник / страница / область",
    "Права / лицензия", "Группа родственных изображений", "SHA-256 файла", "Статус разметки",
]
SAVED_WORD = [
    "vc0001", "кот", "Описание сохранено пользователем.", "Животное", "кошка",
    "Проверено пользователем", 87.5, 2, "user-training.png", "user-control.png",
    "user-model-sha", "user-report.json", "Пользовательское замечание",
]


def column(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def worksheet(headers, rows, override=""):
    data = []
    for number, values in enumerate([headers, *rows], 8):
        cells = []
        for index, value in enumerate(values, 1):
            ref = f"{column(index)}{number}"
            if value is None:
                continue
            if isinstance(value, bool):
                cells.append(f'<c r="{ref}" t="b"><v>{int(value)}</v></c>')
            elif isinstance(value, str):
                cells.append(f'<c r="{ref}" t="str"><v>{escape(value)}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        if number == 9:
            cells.append(override)
        data.append(f'<row r="{number}">{"".join(cells)}</row>')
    return '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(data) + '</sheetData></worksheet>'


def workbook(path, words=None, media=None, override="", third_sheet=False,
             word_headers=None, sheet_names=("Словарь", "Медиа"), shared_strings=()):
    sheets = [(sheet_names[0], 1), (sheet_names[1], 2)]
    if third_sheet:
        sheets.append(("Заметки пользователя", 3))
    with ZipFile(path, "w") as archive:
        if shared_strings is not None:
            archive.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + "".join(f'<si><t>{escape(value)}</t></si>' for value in shared_strings) + '</sst>')
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + "".join(f'<sheet name="{escape(name)}" sheetId="{n}" r:id="rId{n}"/>' for name, n in sheets) + '</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(f'<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{n}.xml"/>' for _, n in sheets) + '</Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", worksheet(word_headers or WORDS_HEADERS, words if words is not None else [SAVED_WORD], override))
        archive.writestr("xl/worksheets/sheet2.xml", worksheet(MEDIA_HEADERS, media or []))
        if third_sheet:
            archive.writestr("xl/worksheets/sheet3.xml", worksheet(["Important"], [["DO NOT DROP USER SHEET"]]))
    return path


def test_saved_xml_values_not_stale_seed_are_authoritative(tmp_path):
    file = workbook(tmp_path / "saved.xlsx")
    before = prepare.digest(file)
    headers, words, media_headers, media = prepare.read_saved_workbook(file)
    assert headers == WORDS_HEADERS and media_headers == MEDIA_HEADERS
    assert words == [SAVED_WORD] and media == []
    assert words[0][0] == "vc0001" and words[0][5] == "Проверено пользователем"
    assert words[0][6] == 87.5 and words[0][7] == 2
    assert prepare.digest(file) == before


def test_string_that_looks_numeric_is_not_coerced(tmp_path):
    row = SAVED_WORD.copy()
    row[6] = "85"
    file = workbook(tmp_path / "saved.xlsx", words=[row])
    words = prepare.read_saved_workbook(file)[1]
    assert words[0][6] == "85" and isinstance(words[0][6], str)


def test_inline_strings_work_without_shared_strings_table(tmp_path):
    row = SAVED_WORD.copy()
    row[6] = None
    file = workbook(tmp_path / "inline.xlsx", words=[row], shared_strings=None,
                    override='<c r="G9" t="inlineStr"><is><t>83</t></is></c>')
    words = prepare.read_saved_workbook(file)[1]
    assert words[0][6] == "83"


def test_shared_string_numeric_text_remains_a_string(tmp_path):
    row = SAVED_WORD.copy()
    row[6] = None
    file = workbook(tmp_path / "shared.xlsx", words=[row], shared_strings=("84",),
                    override='<c r="G9" t="s"><v>0</v></c>')
    words = prepare.read_saved_workbook(file)[1]
    assert words[0][6] == "84"


def test_formula_is_rejected_not_flattened(tmp_path):
    file = workbook(tmp_path / "formula.xlsx", override='<c r="M9"><f>1+1</f><v>2</v></c>')
    with pytest.raises(ValueError, match="formula|flatten"):
        prepare.read_saved_workbook(file)


def test_new_column_is_rejected_not_dropped(tmp_path):
    file = workbook(tmp_path / "columns.xlsx", override='<c r="N9" t="str"><v>new user field</v></c>')
    with pytest.raises(ValueError, match="columns|migration"):
        prepare.read_saved_workbook(file)


def test_new_user_sheet_requires_explicit_migration(tmp_path):
    file = workbook(tmp_path / "third.xlsx", third_sheet=True)
    with pytest.raises(ValueError):
        prepare.read_saved_workbook(file)


def test_changed_header_requires_explicit_migration(tmp_path):
    headers = WORDS_HEADERS.copy()
    headers[6] = "Пользовательская новая метрика"
    file = workbook(tmp_path / "headers.xlsx", word_headers=headers)
    with pytest.raises(ValueError):
        prepare.read_saved_workbook(file)


def test_changed_sheet_identity_requires_explicit_migration(tmp_path):
    file = workbook(tmp_path / "rename.xlsx", sheet_names=("Мои дополнительные сведения", "Медиа"))
    with pytest.raises(ValueError):
        prepare.read_saved_workbook(file)


class FakeMorphology:
    def parse(self, word):
        lemmas = {"коты": ["кот"], "замки": ["замок", "замкнуть"]}.get(word, [word])
        return [types.SimpleNamespace(normal_form=lemma, is_known=word in ("коты", "замки")) for lemma in lemmas]


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def asset(corpus, name, payload):
    path = corpus / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"path": name, "sha256": hashlib.sha256(payload).hexdigest()}


@pytest.fixture
def bundle(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    book = {"original_filename": "fixture.pdf", "sha256": "a" * 64, "pages": 1}
    manifest = tmp_path / "manifest.json"
    write_json(manifest, {"books": [book]})
    saved = SAVED_WORD.copy()
    other = [["vc0002", "замок", "Значение не определено.", "Кандидат", "", "Не обучено", None, None, "", "", "", "", ""], ["vc0003", "замкнуть", "Значение не определено.", "Кандидат", "", "Не обучено", None, None, "", "", "", "", ""]]
    file = workbook(tmp_path / "saved.xlsx", words=[saved, *other])
    image = asset(corpus, "reviews/fixture/crop.png", b"review pixels fixture")
    context = asset(corpus, "reviews/fixture/page.png", b"review whole scene fixture")
    write_json(corpus / "reviews/fixture/annotations.json", {"reviewer": "fixture", "books": [{"filename": book["original_filename"], "source_sha256": book["sha256"], "pages_visually_reviewed": [1]}], "concepts": [{"word": "кот", "description": "Домашняя кошка.", "existing_id": "vc0001", "evidence": [{"filename": book["original_filename"], "pdf_page": 1, "media_path": str(corpus / image["path"]), "media_sha256": image["sha256"], "whole_page_path": str(corpus / context["path"]), "whole_page_sha256": context["sha256"], "role": "object", "split": "UNASSIGNED", "training_admitted": False}]}]})
    preview = asset(corpus, "books/family/pages/0001.jpg", b"old whole page")
    text = asset(corpus, "books/family/text/0001.txt", "коты замки".encode())
    raster = asset(corpus, "books/family/placements/0001.jpg", b"old raw crop")
    record = {"page_id": "family-p0001", "family_id": "family", "original_filename": book["original_filename"], "original_sha256": book["sha256"], "pdf_page": 1, "page_preview": preview, "text_file": text, "text": "коты замки", "images": [{"media_id": "raw-r0001", "media": raster, "bbox": [1, 2, 3, 4]}]}
    record_file = corpus / "books/family/records/0001.json"
    write_json(record_file, record)
    return types.SimpleNamespace(corpus=corpus, workbook=file, manifest=manifest, output=tmp_path / "prepared.json", record=record, record_file=record_file)


def run_bundle(bundle):
    fake_module = types.SimpleNamespace(MorphAnalyzer=FakeMorphology)
    with patch.dict(sys.modules, {"pymorphy3": fake_module}):
        return prepare.run(bundle.workbook, bundle.corpus, bundle.output, bundle.manifest, bundle.corpus)


def test_run_preserves_saved_user_columns_and_leaves_unassigned_out_of_train(bundle):
    before = prepare.digest(bundle.workbook)
    result = run_bundle(bundle)
    saved = next(row for row in result["words"] if row[0] == "vc0001")
    assert saved[:13] == SAVED_WORD
    assert saved[8:10] == ["user-training.png", "user-control.png"]
    assert "crop.png" in saved[13]
    assert all(row[3] == "Не назначено" and row[15] == "Нет" for row in result["media"])
    assert not result["training_started"] and not result["training_admitted"]
    assert prepare.digest(bundle.workbook) == before


def test_existing_user_media_row_is_preserved_not_reclassified(bundle):
    old = ["user-media-17", "vc0001", "https://example.invalid/user.png", "Контроль",
           "Объект", "Фото", "Моя заметка", "Мой источник", "Мои права", "user-family", "user-media-sha", "Проверено пользователем"]
    workbook(bundle.workbook, words=[SAVED_WORD], media=[old])
    result = run_bundle(bundle)
    row = next(row for row in result["media"] if row[0] == "user-media-17")
    assert row[:12] == old
    assert row[3] == "Контроль"


def test_new_visual_concept_starts_pending_without_percent_or_training(bundle):
    path = bundle.corpus / "reviews/fixture/annotations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    fresh = dict(data["concepts"][0])
    fresh.pop("existing_id")
    fresh.update(word="персик", description="Плод персикового дерева.")
    data["concepts"].append(fresh)
    write_json(path, data)
    result = run_bundle(bundle)
    row = next(row for row in result["words"] if row[1] == "персик")
    assert row[0] == "vc0004"
    assert row[5] == "Сбор материалов" and row[6:8] == [None, None]
    assert row[8:12] == ["", "", "", ""]
    assert "crop.png" in row[13]


def test_review_crop_escape_is_rejected_even_if_hash_is_correct(bundle):
    path = bundle.corpus / "reviews/fixture/annotations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    outside = bundle.corpus.parent / "outside.png"
    outside.write_bytes(b"outside fixture")
    evidence = data["concepts"][0]["evidence"][0]
    evidence["media_path"] = str(outside)
    evidence["media_sha256"] = prepare.digest(outside)
    write_json(path, data)
    with pytest.raises(ValueError, match="confinement"):
        run_bundle(bundle)


@pytest.mark.parametrize("kind", ["outside", "missing_hash", "wrong_hash"])
def test_review_context_identity_and_confinement_guard(bundle, kind):
    path = bundle.corpus / "reviews/fixture/annotations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    evidence = data["concepts"][0]["evidence"][0]
    if kind == "outside":
        outside = bundle.corpus.parent / "outside-context.png"
        outside.write_bytes(b"outside context")
        evidence["whole_page_path"] = str(outside)
        evidence["whole_page_sha256"] = prepare.digest(outside)
    elif kind == "missing_hash":
        evidence.pop("whole_page_sha256")
    else:
        evidence["whole_page_sha256"] = "0" * 64
    write_json(path, data)
    with pytest.raises(ValueError, match="Context|context"):
        run_bundle(bundle)


def test_review_cannot_admit_training(bundle):
    path = bundle.corpus / "reviews/fixture/annotations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["training_admitted"] = True
    write_json(path, data)
    with pytest.raises(ValueError, match="admit training"):
        run_bundle(bundle)


def test_ambiguous_morphology_stays_candidate_and_retains_all_possible_ids(bundle):
    result = run_bundle(bundle)
    row = next(row for row in result["text"] if row[1] == "замки")
    assert row[3] == "vc0002; vc0003"
    assert row[7] == "Кандидат; не допущен к обучению"
    assert "неоднозначны" in row[8]
    assert row[9] == "Значение требует проверки по контексту источника."
    assert result["stats"]["lexical_occurrence_matches_not_sense_proofs"] == 2


def corrected_record(bundle):
    record = dict(bundle.record)
    record["page_preview"] = asset(bundle.corpus, "geometry-corrections/family/pages/0001.jpg", b"corrected whole page")
    record["text_file"] = asset(bundle.corpus, "geometry-corrections/family/text/0001.txt", "коты замки".encode())
    new_image = asset(bundle.corpus, "geometry-corrections/family/placements/0001.jpg", b"corrected raw crop")
    record["images"] = [{"media_id": "corrected-r0001", "media": new_image, "bbox": [2, 3, 4, 5]}]
    path = bundle.corpus / "geometry-corrections/family/records/0001.json"
    write_json(path, record)
    write_json(bundle.corpus / "geometry-corrections/replacement-index.json", {"replacements": [{"page_id": record["page_id"], "corrected_record": str(path.relative_to(bundle.corpus)), "corrected_record_sha256": prepare.digest(path)}]})
    return path


def test_geometry_replacement_is_whole_record_not_only_preview(bundle):
    corrected_record(bundle)
    result = run_bundle(bundle)
    paths = {row[2] for row in result["media"]}
    assert str((bundle.corpus / bundle.record["page_preview"]["path"]).resolve()) not in paths
    assert str((bundle.corpus / bundle.record["images"][0]["media"]["path"]).resolve()) not in paths
    assert any("geometry-corrections" in path and "placements" in path for path in paths)
    assert result["stats"]["corrected_pages"] == 1
    assert result["stats"]["effective_pages"] == 1


def test_corrected_record_digest_is_verified_before_use(bundle):
    path = corrected_record(bundle)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["text"] = "altered after correction seal"
    write_json(path, data)
    with pytest.raises(ValueError):
        run_bundle(bundle)


@pytest.mark.parametrize("character", ["\u0000", "\u0001", "\u001f", "\ufffe"])
def test_spreadsheet_controls_are_visible_escaped_not_erased(character):
    value = "до" + character + "после"
    assert prepare.spreadsheet_text(value) == "до\\u" + f"{ord(character):04x}" + "после"
    assert value == "до" + character + "после"


def test_valid_spreadsheet_text_and_existing_literal_escape_are_unchanged():
    value = "Русский текст\tс табом\nновая строка\remoji 🙂 и literal \\u0001"
    assert prepare.spreadsheet_text(value) == value


def test_display_escape_preserves_raw_text_and_admission_flags(bundle):
    text = "коты\u0001замки"
    bundle.record["text"] = text
    bundle.record["text_file"] = asset(bundle.corpus, "books/family/text/0001.txt", text.encode())
    write_json(bundle.record_file, bundle.record)
    raw_file = bundle.corpus / bundle.record["text_file"]["path"]
    before = prepare.digest(raw_file)
    result = run_bundle(bundle)
    assert any("\\u0001" in row[11] for row in result["text"])
    assert result["stats"]["xml_display_escaped_cells"] >= 1
    assert any("U+0001" in item["codepoints"] for item in result["spreadsheet_text_escapes"])
    assert raw_file.read_text(encoding="utf-8") == text
    assert prepare.digest(raw_file) == before
    assert not result["training_started"] and not result["training_admitted"]


def test_saved_user_control_requires_migration_not_automatic_escaping(bundle):
    original = prepare.read_saved_workbook(bundle.workbook)
    changed = tuple(original)
    changed[1][0][12] = "user\u0001note"
    before = prepare.digest(bundle.workbook)
    with patch.object(prepare, "read_saved_workbook", return_value=changed):
        with pytest.raises(ValueError, match="Saved user cell|migration"):
            run_bundle(bundle)
    assert prepare.digest(bundle.workbook) == before
