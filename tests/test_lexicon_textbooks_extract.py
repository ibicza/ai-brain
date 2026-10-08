"""Extraction integrity tests; no model or training data admission."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "lexicon_extract",
    Path(__file__).parents[1] / "scripts" / "lexicon_textbooks_extract.py",
)
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)


def test_preserve_refuses_overwrite(tmp_path):
    path = tmp_path / "user.json"
    extract.preserve(path, b"original")
    extract.preserve(path, b"original")
    with pytest.raises(ValueError, match="differs"):
        extract.preserve(path, b"altered")
    assert path.read_bytes() == b"original"


def test_family_groups_both_parts():
    assert extract.family("matematika_2kl_1ch_Muravyova.pdf") == extract.family(
        "matematika-muravjova-1kl-ch2.pdf"
    )
    assert extract.family("lit_chtenie_2k_ch1.pdf") == extract.family(
        "lit_chtenie_2k_ch2.pdf"
    )


def test_bbox_clipping_and_invalid():
    assert extract.pixel_bbox([-2, 10, 70, 110], 100, 100, (200, 200)) == (
        0,
        20,
        140,
        200,
    )
    with pytest.raises(ValueError):
        extract.pixel_bbox([110, 0, 120, 20], 100, 100, (200, 200))
    with pytest.raises(ValueError):
        extract.pixel_bbox([0, float("nan"), 20, 20], 100, 100, (200, 200))


def test_record_checks_admission_and_hash(tmp_path):
    item = extract.asset(tmp_path / "a.txt", tmp_path, b"test")
    record = {
        "original_sha256": "source",
        "training_admitted": False,
        "page_preview": item,
        "text_file": item,
        "images": [],
    }
    extract.verify_record(record, tmp_path, "source")
    record["training_admitted"] = True
    with pytest.raises(ValueError):
        extract.verify_record(record, tmp_path, "source")
    record["training_admitted"] = False
    (tmp_path / "a.txt").write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        extract.verify_record(record, tmp_path, "source")


def test_record_refuses_escape(tmp_path):
    item = {"path": "../outside", "sha256": "bad"}
    record = {
        "original_sha256": "source",
        "training_admitted": False,
        "page_preview": item,
        "text_file": item,
        "images": [],
    }
    with pytest.raises(ValueError):
        extract.verify_record(record, tmp_path, "source")


def test_extract_synthetic_pdf_and_resume(tmp_path):
    pytest.importorskip("pdfplumber")
    pytest.importorskip("pypdfium2")
    pytest.importorskip("reportlab.pdfgen.canvas")
    pytest.importorskip("PIL.Image")
    from PIL import Image
    from reportlab.pdfgen import canvas

    originals = tmp_path / "originals"
    originals.mkdir()
    picture = tmp_path / "picture.png"
    Image.new("RGB", (20, 20), "red").save(picture)
    pdf = originals / "test.pdf"
    document = canvas.Canvas(str(pdf), pagesize=(200, 200))
    document.drawString(20, 170, "apple")
    document.drawImage(str(picture), 40, 40, width=60, height=60)
    document.showPage()
    document.rect(30, 30, 50, 50)
    document.save()
    manifest = tmp_path / "manifest.json"
    book = {
        "path": "originals/test.pdf",
        "original_filename": "test.pdf",
        "sha256": extract.sha256(pdf),
        "source_id": "sha256:" + extract.sha256(pdf),
        "bytes": pdf.stat().st_size,
        "pages": 2,
    }
    manifest.write_text(json.dumps({"books": [book]}), encoding="utf-8")
    output = tmp_path / "out"
    first = extract.run(manifest, output)
    assert not first["failures"]
    assert first["total_pages"] == 2
    assert first["total_crops"] == 1
    assert first["books"][0]["ocr_review_pages"] == [2]
    assert extract.run(manifest, output) == first
    records = [
        json.loads(line)
        for line in (output / first["books"][0]["directory"] / "pages.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert records[0]["words"][0]["text"] == "apple"
    assert records[1]["vector_primitive_count"] == 1
    assert all(
        r["training_admitted"] is False and r["split"] == "UNASSIGNED" for r in records
    )
    assert extract.sha256(pdf) == book["sha256"]
    sheets = extract.contact_sheets(output)
    assert len(sheets) == 1 and sheets[0]["pdf_pages"] == [1, 2]
    assert extract.contact_sheets(output) == sheets


def test_bad_original_and_unknown_book(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"books": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        extract.run(manifest, tmp_path / "out", book_names=["missing.pdf"])
    with pytest.raises(ValueError):
        extract.run(manifest, tmp_path / "out", dpi=20)


def test_original_tampering_is_failure_not_admitted(tmp_path):
    original = tmp_path / "original.pdf"
    original.write_bytes(b"not a PDF")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "books": [
                    {
                        "path": "original.pdf",
                        "original_filename": "original.pdf",
                        "sha256": "wrong",
                        "bytes": original.stat().st_size,
                        "pages": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = extract.run(manifest, tmp_path / "output")
    assert result["status"] == "INCOMPLETE_FAILURES_REQUIRE_REVIEW"
    assert result["total_pages"] == 0 and result["training_admitted"] is False
    assert "does not match manifest" in result["failures"][0]["error"]


def test_nonzero_cropbox_uses_full_media_and_preserves_override(tmp_path):
    pytest.importorskip("pdfplumber")
    pytest.importorskip("pypdfium2")
    pytest.importorskip("reportlab.pdfgen.canvas")
    pytest.importorskip("PIL.Image")
    from PIL import Image
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import RectangleObject
    from reportlab.pdfgen import canvas

    picture = tmp_path / "red.png"
    Image.new("RGB", (20, 20), "red").save(picture)
    uncropped = tmp_path / "uncropped.pdf"
    document = canvas.Canvas(str(uncropped), pagesize=(200, 200))
    document.drawImage(str(picture), 40, 40, width=60, height=60)
    document.save()
    reader = PdfReader(uncropped)
    reader.pages[0].cropbox = RectangleObject((100, 0, 200, 200))
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    original = tmp_path / "original.pdf"
    writer.write(original)
    book = {
        "path": "original.pdf",
        "original_filename": "original.pdf",
        "sha256": extract.sha256(original),
        "source_id": "sha256:" + extract.sha256(original),
        "bytes": original.stat().st_size,
        "pages": 1,
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"books": [book]}), encoding="utf-8")
    output = tmp_path / "out"
    result = extract.run(manifest, output)
    assert not result["failures"]
    record_path = output / result["books"][0]["directory"] / "records" / "0001.json"
    record_bytes = record_path.read_bytes()
    record = json.loads(record_bytes)
    assert record["pixel_size"][0] == record["pixel_size"][1]
    assert record["original_cropbox_bottom_left"] == [100, 0, 200, 200]
    with Image.open(output / record["images"][0]["media"]["path"]) as image:
        colour = image.getpixel((image.width // 2, image.height // 2))
        assert colour[0] > 240 and colour[1] < 20
    corrections = extract.correct_geometry(manifest, output, 110)
    assert len(corrections["replacements"]) == 1
    assert record_path.read_bytes() == record_bytes
    corrected = json.loads(
        (output / corrections["replacements"][0]["corrected_record"]).read_text(
            encoding="utf-8"
        )
    )
    assert corrected["images"][0]["media_id"].endswith("-geometry-v2")
    assert extract.correct_geometry(manifest, output, 110) == corrections
    effective = extract.effective_coverage(output)
    assert effective["total_pages"] == 1 and effective["total_crops"] == 1
    assert effective["geometry_corrected_pages"] == 1
    assert effective["all_effective_media_hashes_verified"] is True
    assert effective["training_admitted"] is False
    assert (
        effective["superseded_unusable_media"][0]["images"][0]["media_id"]
        == record["images"][0]["media_id"]
    )
    assert extract.effective_coverage(output) == effective
