"""Incremental JSON preparation preserves actual saved user cells and IDs."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "lexicon_increment",
    Path(__file__).parents[1] / "scripts/lexicon_catalogue_increment.py",
)
increment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(increment)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    corpus = tmp_path / "sealed"
    reviews = tmp_path / "supplemental"
    originals = tmp_path / "originals"
    for path in (corpus, reviews, originals):
        path.mkdir()
    original = originals / "book.pdf"
    original.write_bytes(b"immutable original fixture")
    image = corpus / "page.jpg"
    image.write_bytes(b"immutable image fixture")
    workbook = tmp_path / "saved.xlsx"
    workbook.write_bytes(b"reader test seam, not Excel authoring")
    manifest = tmp_path / "manifest.json"
    source_sha = increment.digest(original)
    record = corpus / "books" / source_sha[:16] / "records/0001.json"
    record.parent.mkdir(parents=True)
    record.write_text(
        json.dumps(
            {
                "original_sha256": source_sha,
                "original_filename": "book.pdf",
                "pdf_page": 1,
                "page_id": source_sha[:16] + "-p0001",
                "page_preview": {"path": "page.jpg", "sha256": increment.digest(image)},
            }
        ),
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "books": [
                    {
                        "original_filename": "book.pdf",
                        "path": "originals/book.pdf",
                        "sha256": source_sha,
                        "pages": 10,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    words = [
        [
            "vc0001",
            "яблоко",
            "Пользовательское описание",
            "Моя категория",
            "яблочко; APPLE",
            "Пользовательский статус",
            0,
            2,
            "my train",
            "my regression",
            "model SHA",
            "my report",
            "my notes",
            "my existing links",
        ]
    ]
    media = [
        [
            "base-media",
            "",
            str(image),
            "Не назначено",
            "Сцена",
            "JPEG",
            "base notes",
            "source",
            "rights",
            "family",
            increment.digest(image),
            "draft",
            "text",
            str(image),
            "reviewer",
            "Нет",
            "PAGE_CONTEXT",
            1,
            "bbox",
        ]
    ]
    text = [
        [
            "word0001",
            "текст",
            "формы",
            "vc0001",
            4,
            5,
            "ru",
            "user status",
            "reason",
            "description",
            "sources",
            "context",
            "paths",
        ]
    ]
    coverage = [["book.pdf", source_sha, 10, 10, 10, 3, 0, "Нет", "user notes"]]
    rows = {"words": words, "media": media, "text": text, "coverage": coverage}
    tables = {
        name: {
            "headers": copy.deepcopy(increment.HEADERS[key]),
            "rows": copy.deepcopy(rows[key]),
            "freeze": True,
            "tables": True,
        }
        for name, key in increment.SHEETS.items()
    }
    monkeypatch.setattr(increment, "saved_tables", lambda _: copy.deepcopy(tables))
    evidence = {
        "filename": "book.pdf",
        "source_sha256": source_sha,
        "pdf_page": 1,
        "media_path": str(image),
        "media_sha256": increment.digest(image),
        "whole_page_path": str(image),
        "whole_page_sha256": increment.digest(image),
        "role": "scene-contains-object",
        "notes": "overview",
        "split": "UNASSIGNED",
        "training_admitted": False,
    }
    annotation = {
        "reviewer": "test_overview",
        "books": [
            {
                "filename": "book.pdf",
                "source_sha256": source_sha,
                "pages_overviewed": [1, 2],
            }
        ],
        "concepts": [
            {
                "word": "яблочко",
                "description": "Fruit",
                "evidence": [copy.deepcopy(evidence)],
            },
            {
                "word": "груша",
                "description": "Другой фрукт",
                "evidence": [copy.deepcopy(evidence)],
            },
        ],
        "unresolved": [],
    }
    annotation_path = reviews / "supplemental-annotations.json"
    annotation_path.write_text(
        json.dumps(annotation, ensure_ascii=False), encoding="utf-8"
    )

    def run(label="output", previous_prepared=None):
        annotation_path.write_text(
            json.dumps(annotation, ensure_ascii=False), encoding="utf-8"
        )
        return increment.run(
            workbook,
            manifest,
            corpus,
            reviews,
            tmp_path / (label + ".json"),
            [corpus, reviews],
            previous_prepared=previous_prepared,
        )

    return {
        "run": run,
        "rows": rows,
        "tables": tables,
        "annotation": annotation,
        "evidence": evidence,
        "corpus": corpus,
        "reviews": reviews,
        "original": original,
        "image": image,
        "record": record,
        "tmp": tmp_path,
    }


def test_all_saved_user_values_preserved_and_new_draft_associations(fixture):
    result = fixture["run"]()
    assert result["incremental"] is True
    assert result["words"][0][:13] == fixture["rows"]["words"][0][:13]
    assert result["words"][0][13].startswith("my existing links\n")
    assert result["words"][1][0] == "vc0002"
    assert result["words"][1][6:12] == [None, None, "", "", "", ""]
    assert result["media"][:1] == fixture["rows"]["media"]
    assert result["text"] == fixture["rows"]["text"]
    assert result["coverage"] == fixture["rows"]["coverage"]
    assert result["input_rows"] == {"words": 1, "media": 1, "text": 1, "coverage": 1}
    assert result["stats"]["pages_visually_reviewed"] == 3
    assert result["stats"]["overview_pages"] == 2
    assert result["stats"]["input_concepts"] == 1
    assert result["raw_assets"] == []
    assert all(
        row[3] == "Не назначено" and row[15] == "Нет" and "NOT_GOLD" in row[16]
        for row in result["media"][1:]
    )


def test_repeated_evidence_deduplicates_and_preserves_all_old_ids(fixture):
    concept = fixture["annotation"]["concepts"][0]
    concept["evidence"].append(copy.deepcopy(concept["evidence"][0]))
    result = fixture["run"]()
    assert len(result["media"]) == 3
    assert len(result["deduplicated_evidence"]) == 1
    for name, key in increment.SHEETS.items():
        fixture["tables"][name]["rows"] = copy.deepcopy(result[key])
    second = fixture["run"]("second")
    assert second["words"] == result["words"]
    assert second["media"] == result["media"]
    assert second["stats"]["new_visual_concepts"] == 0
    assert second["stats"]["new_media_rows"] == 0


def test_unknown_headers_and_duplicate_ids_refuse_migration(fixture):
    fixture["tables"]["Текст"]["headers"].append("User extra column")
    with pytest.raises(ValueError, match="migration"):
        fixture["run"]()
    fixture["tables"]["Текст"]["headers"].pop()
    fixture["tables"]["Словарь"]["rows"].append(
        copy.deepcopy(fixture["rows"]["words"][0])
    )
    with pytest.raises(ValueError, match="IDs"):
        fixture["run"]()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sha256", "wrong"),
        ("media_sha256", "wrong"),
        ("whole_page_sha256", "wrong"),
        ("pdf_page", 11),
        ("training_admitted", True),
        ("split", "TRAIN"),
    ],
)
def test_new_evidence_guards(fixture, field, value):
    fixture["annotation"]["concepts"][0]["evidence"][0][field] = value
    with pytest.raises(ValueError):
        fixture["run"]()


def test_asset_cannot_escape_allowlist(fixture):
    outside = fixture["tmp"] / "outside.jpg"
    outside.write_bytes(fixture["image"].read_bytes())
    fixture["annotation"]["concepts"][0]["evidence"][0]["media_path"] = str(outside)
    with pytest.raises(ValueError, match="allowlist"):
        fixture["run"]()


def test_source_bytes_and_superseded_assets_refused(fixture):
    fixture["original"].write_bytes(b"changed")
    with pytest.raises(ValueError, match="source bytes"):
        fixture["run"]()
    fixture["original"].write_bytes(b"immutable original fixture")
    report = {
        "superseded_unusable_media": [
            {"page_preview": {"path": "page.jpg"}, "images": []}
        ]
    }
    (fixture["corpus"] / "effective-coverage-report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Superseded"):
        fixture["run"]()


def test_new_xml_controls_escaped_without_old_cell_rewrite(fixture):
    fixture["annotation"]["concepts"][0]["evidence"][0]["notes"] = "new\x00note"
    result = fixture["run"]()
    assert "new\\u0000note" in result["media"][1][6]
    assert result["spreadsheet_text_escapes"][0]["row"] == 10
    assert result["words"][0][:13] == fixture["rows"]["words"][0][:13]


def test_link_limit_does_not_lose_media_rows(fixture):
    old = "x" * 32760
    fixture["tables"]["Словарь"]["rows"][0][13] = old
    result = fixture["run"]()
    assert result["words"][0][13] == old
    assert result["omitted_cell_links_still_in_media"] == {"vc0001": 1}
    assert result["media"][1][1] == "vc0001"


def test_long_new_description_rejected_and_original_descriptions_retained(fixture):
    fixture["annotation"]["concepts"][1]["description"] = "word " * 21
    with pytest.raises(ValueError, match="20 words"):
        fixture["run"]()


def test_formula_reader_error_is_not_silently_flattened(fixture, monkeypatch):
    def refuse(_):
        raise ValueError("Unexpected formula; explicit preservation required")

    monkeypatch.setattr(increment, "saved_tables", refuse)
    with pytest.raises(ValueError, match="formula"):
        fixture["run"]()


def test_full_scene_other_valid_page_cannot_be_attributed_to_page_one(fixture):
    other = fixture["corpus"] / "other-page.jpg"
    other.write_bytes(b"another valid page")
    evidence = fixture["annotation"]["concepts"][0]["evidence"][0]
    for prefix in ("media", "whole_page"):
        evidence[prefix + "_path"] = str(other)
        evidence[prefix + "_sha256"] = increment.digest(other)
    with pytest.raises(ValueError, match="effective page preview"):
        fixture["run"]()


def test_new_full_scene_requires_explicit_role(fixture):
    fixture["annotation"]["concepts"][0]["evidence"][0].pop("role")
    with pytest.raises(ValueError, match="role"):
        fixture["run"]()


def test_corrected_preview_required_and_old_rows_not_revalidated(fixture):
    old_record = json.loads(fixture["record"].read_text())
    corrected = fixture["corpus"] / "geometry-corrections/records/0001.json"
    corrected.parent.mkdir(parents=True)
    corrected_image = fixture["corpus"] / "geometry-corrections/page.jpg"
    corrected_image.write_bytes(b"corrected geometry")
    new_record = copy.deepcopy(old_record)
    new_record["page_preview"] = {
        "path": "geometry-corrections/page.jpg",
        "sha256": increment.digest(corrected_image),
    }
    corrected.write_text(json.dumps(new_record), encoding="utf-8")
    index = {
        "replacements": [
            {
                "page_id": old_record["page_id"],
                "pdf_page": 1,
                "original_sha256": old_record["original_sha256"],
                "corrected_record": "geometry-corrections/records/0001.json",
                "corrected_record_sha256": increment.digest(corrected),
            }
        ]
    }
    (fixture["corpus"] / "geometry-corrections/replacement-index.json").write_text(
        json.dumps(index)
    )
    with pytest.raises(ValueError, match="effective page preview"):
        fixture["run"]()
    for concept in fixture["annotation"]["concepts"]:
        evidence = concept["evidence"][0]
        for prefix in ("media", "whole_page"):
            evidence[prefix + "_path"] = str(corrected_image)
            evidence[prefix + "_sha256"] = increment.digest(corrected_image)
    result = fixture["run"]("corrected")
    assert result["media"][0] == fixture["rows"]["media"][0]
    assert result["media"][1][2] == str(corrected_image)


def previous_history(fixture):
    review = fixture["corpus"] / "old-review.json"
    review.write_text("{}")
    prior = {
        "training_started": False,
        "training_admitted": False,
        "review_files": [{"path": str(review), "sha256": increment.digest(review)}],
        "spreadsheet_text_escapes": [
            {"sheet_key": "text", "row": 9, "column": 12, "codepoints": ["U+001A"]}
        ],
    }
    for key in increment.HEADERS:
        prior[key] = copy.deepcopy(fixture["rows"][key])
        prior[key + "_headers"] = copy.deepcopy(increment.HEADERS[key])
    path = fixture["tmp"] / "previous.json"
    path.write_text(json.dumps(prior), encoding="utf-8")
    return path, prior, review


def test_previous_reviews_and_escapes_preserved_without_replacing_user_edit(fixture):
    path, prior, _ = previous_history(fixture)
    fixture["tables"]["Словарь"]["rows"][0][2] = "new user description"
    result = fixture["run"](previous_prepared=path)
    assert result["review_files"][0] == prior["review_files"][0]
    assert result["spreadsheet_text_escapes"][0] == prior["spreadsheet_text_escapes"][0]
    assert result["words"][0][2] == "new user description"
    assert result["previous_prepared_history"]["saved_value_differences_preserved"] == [
        {
            "sheet_key": "words",
            "row_index": 0,
            "column": 3,
            "policy": "ACTUAL_SAVED_USER_VALUE_PRESERVED",
        }
    ]


def test_previous_review_sha_and_source_confinement_required(fixture):
    path, prior, review = previous_history(fixture)
    review.write_text("changed")
    with pytest.raises(ValueError, match="allowlist"):
        fixture["run"](previous_prepared=path)
    review.write_text("{}")
    outside = fixture["tmp"] / "outside-review.json"
    outside.write_text("{}")
    prior["review_files"][0]["path"] = str(outside)
    path.write_text(json.dumps(prior))
    with pytest.raises(ValueError, match="allowlist"):
        fixture["run"](previous_prepared=path)


def test_previous_history_missing_identity_refuses_migration(fixture):
    path, prior, _ = previous_history(fixture)
    prior["words"][0][0] = "lost-user-id"
    path.write_text(json.dumps(prior))
    with pytest.raises(ValueError, match="identity"):
        fixture["run"](previous_prepared=path)
