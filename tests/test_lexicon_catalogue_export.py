"""Read-only exports preserve past measurements and separate review levels."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "catalogue_export",
    Path(__file__).parents[1] / "scripts/lexicon_catalogue_export.py",
)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def fixture(tmp_path, monkeypatch):
    workbook = tmp_path / "saved.xlsx"
    workbook.write_bytes(b"saved fixture, reader mocked")
    words = [[None] * 14 for _ in range(2)]
    words[0][6] = 0.7
    media = [[None] * 19 for _ in range(2)]
    media[0][3], media[0][15] = "train", "Да"
    media[1][3], media[1][15] = "Не назначено", "Нет"
    media[1][0], media[1][7], media[1][16] = (
        "p1",
        "book.pdf; PDF 1; SHA x",
        "PAGE_CONTEXT",
    )
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps({"books": [{"filename": "book.pdf", "pages_overviewed": [1]}]})
    )
    data = {
        "input_workbook_sha256": export.sha(workbook),
        "input_rows": {"words": 1, "media": 1},
        "stats": {"concepts": 2, "new_visual_concepts": 1, "limits": "draft"},
        "review_files": [{"path": str(review), "sha256": export.sha(review)}],
    }
    tables = {}
    for name, key, rows, width in [
        ("Словарь", "words", words, 14),
        ("Медиа", "media", media, 19),
        ("Текст", "text", [], 13),
        ("Покрытие", "coverage", [], 9),
    ]:
        headers = [f"column-{i}" for i in range(width)]
        data[key], data[key + "_headers"] = rows, headers
        tables[name] = {
            "headers": headers,
            "rows": rows,
            "freeze": True,
            "tables": True,
        }
    monkeypatch.setattr(export, "saved_tables", lambda _: tables)
    prepared = tmp_path / "prepared.json"
    return workbook, prepared, data


def test_preserve_old_metrics_and_admission_and_separate_overview(
    tmp_path, monkeypatch
):
    workbook, prepared, data = fixture(tmp_path, monkeypatch)
    prepared.write_text(json.dumps(data))
    export.run(workbook, prepared, tmp_path / "exports")
    report = json.loads((tmp_path / "exports/catalogue_report.json").read_text())
    assert report["overview_pages"] == 1
    assert report["detailed_review_pages"] == 0
    queue = (tmp_path / "exports/review_queue.csv").read_text(encoding="utf-8-sig")
    assert "Просмотрена обзорно" in queue
    assert "Не завершена" in queue


@pytest.mark.parametrize("error", ["admission", "split", "metric"])
def test_new_rows_cannot_claim_training_or_measured_mastery(
    tmp_path, monkeypatch, error
):
    workbook, prepared, data = fixture(tmp_path, monkeypatch)
    if error == "admission":
        data["media"][1][15] = "Да"
    elif error == "split":
        data["media"][1][3] = "train"
    else:
        data["words"][1][6] = 1
    prepared.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        export.run(workbook, prepared, tmp_path / "exports")
