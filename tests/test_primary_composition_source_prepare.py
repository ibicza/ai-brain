"""Source pixels and preprocessing guards, not independent semantic labels."""

import importlib.util
import io
import json
from pathlib import Path

import numpy as np
import pypdfium2
import pytest
from PIL import Image
from reportlab.pdfgen import canvas

spec = importlib.util.spec_from_file_location(
    "source_prepare",
    Path(__file__).parents[1] / "scripts/m33_composition_source_prepare.py",
)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
reader_spec = importlib.util.spec_from_file_location(
    "source_dataset",
    Path(__file__).parents[1] / "scripts/m33_composition_source_dataset.py",
)
reader = importlib.util.module_from_spec(reader_spec)
reader_spec.loader.exec_module(reader)


@pytest.fixture
def inputs(tmp_path):
    originals, derived = tmp_path / "originals", tmp_path / "derived"
    originals.mkdir()
    derived.mkdir()
    pdf = originals / "fixture.pdf"
    writer = canvas.Canvas(str(pdf), pagesize=(96, 96))
    writer.setFillColorRGB(1, 0, 0)
    writer.circle(24, 48, 12, stroke=0, fill=1)
    writer.save()
    doc = pypdfium2.PdfDocument(pdf)
    page = doc[0]
    bitmap = page.render(scale=1)
    image = bitmap.to_pil().convert("RGB")
    image.save(
        derived / "page.jpg", format="JPEG", quality=88, optimize=True, subsampling=0
    )
    image.close()
    bitmap.close()
    page.close()
    doc.close()
    policy = source.read(
        Path(__file__).parents[1] / "examples/m33/visual_source_controls_v1.json"
    )
    policy["sources"] = [
        {
            "id": "fixture",
            "pdf": "fixture.pdf",
            "pdf_sha256": source.sha(pdf),
            "pdf_page": 1,
            "preview": "page.jpg",
            "preview_sha256": source.sha(derived / "page.jpg"),
            "pixel_size": [96, 96],
            "dpi": 72,
        }
    ]
    policy["assets"] = [
        {
            "id": "red-circle",
            "source": "fixture",
            "bbox_pixels": [10, 34, 38, 62],
            "color": "красный",
            "shape": "круг",
            "pattern": "однотонный",
            "absent": False,
        },
        {
            "id": "empty",
            "source": "fixture",
            "bbox_pixels": [65, 34, 93, 62],
            "color": None,
            "shape": None,
            "pattern": None,
            "absent": True,
        },
    ]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(policy), encoding="utf-8")
    return manifest, originals, derived, tmp_path / "controls"


def test_fresh_pdf_rendering_and_original_bytes_are_verified(inputs):
    manifest, originals, derived, output = inputs
    before = source.sha(originals / "fixture.pdf")
    report = source.prepare(manifest, originals, derived, output)
    assert report["fresh_original_rendering_verified"]
    assert report["unique_source_assets"] == 2 and report["unique_pdf_books"] == 1
    assert report["paired_scenes"] == 2 and report["questions"] == 12
    assert report["training_or_calibration"] is False
    assert report["independent_source_examples"] is False
    assert source.sha(originals / "fixture.pdf") == before
    with np.load(output / "dataset.npz") as arrays:
        assert arrays["source_pixels"].shape == (2, 96, 96, 3)
        assert arrays["source_labels"].tolist() == [
            0,
            8,
            12,
            15,
            15,
            15,
            15,
            15,
            15,
            0,
            8,
            12,
        ]


def test_changed_preview_cannot_be_legitimized_by_rehashing_manifest(inputs):
    manifest, originals, derived, output = inputs
    with Image.open(derived / "page.jpg") as stored:
        changed = stored.convert("RGB")
    changed.putpixel((0, 0), (0, 0, 0))
    stream = io.BytesIO()
    changed.save(stream, format="JPEG", quality=88, optimize=True, subsampling=0)
    (derived / "page.jpg").write_bytes(stream.getvalue())
    policy = source.read(manifest)
    policy["sources"][0]["preview_sha256"] = source.sha(derived / "page.jpg")
    manifest.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="exact fresh rendering"):
        source.prepare(manifest, originals, derived, output)
    assert not output.exists()


def test_changed_pdf_is_rejected_before_output(inputs):
    manifest, originals, derived, output = inputs
    with (originals / "fixture.pdf").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="Original PDF/page-preview bytes"):
        source.prepare(manifest, originals, derived, output)
    assert not output.exists()


def test_existing_source_control_evidence_is_not_overwritten(inputs):
    manifest, originals, derived, output = inputs
    output.mkdir()
    marker = output / "preserve.txt"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="Fresh source-control"):
        source.prepare(manifest, originals, derived, output)
    assert marker.read_text() == "preserve"


@pytest.mark.parametrize(
    "box", [[-1, 0, 4, 4], [0, 0, 0, 4], [0, 0, 97, 4], [True, 0, 4, 4]]
)
def test_invalid_crop_geometry_is_rejected(box):
    asset = {
        "bbox_pixels": box,
        "absent": False,
        "color": "красный",
        "shape": "круг",
        "pattern": "однотонный",
    }
    with pytest.raises(ValueError, match="Invalid source crop"):
        source.asset_crop(asset, Image.new("RGB", (96, 96)))


def test_numeric_attribute_cannot_silently_become_unknown():
    asset = {
        "bbox_pixels": [0, 0, 4, 4],
        "absent": False,
        "color": 1,
        "shape": "круг",
        "pattern": "однотонный",
    }
    with pytest.raises(ValueError, match="explicit lexical meanings"):
        source.asset_crop(asset, Image.new("RGB", (96, 96)))


def test_source_path_escape_is_rejected_before_reading(inputs):
    manifest, originals, derived, _ = inputs
    row = source.read(manifest)["sources"][0]
    row["pdf"] = "../escape.pdf"
    with pytest.raises(ValueError, match="escaped scoped material"):
        source.verified_page(row, originals, derived)


def test_source_rgb_composites_and_gold_are_reconstructed_independently(inputs):
    manifest, originals, derived, output = inputs
    source.prepare(manifest, originals, derived, output)
    data, groups, hashes, receipt = reader.load(output, source.c)
    assert groups == ("red-circle", "empty")
    assert len(data["pixels"]) == 2 and len(data["records"]) == 12
    assert receipt["fresh_original_rendering_verified"] and len(hashes) == 7


def test_rehashed_wrong_source_composite_is_rejected_by_rgb_reassembly(inputs):
    manifest, originals, derived, output = inputs
    source.prepare(manifest, originals, derived, output)
    path = output / "dataset.npz"
    with np.load(path) as stored:
        arrays = {name: stored[name] for name in stored.files}
    arrays["source_pixels"][0, 0, 0] = 0
    np.savez_compressed(path, **arrays)
    report = source.read(output / "preparation-receipt.json")
    report["dataset_sha256"] = source.sha(path)
    (output / "preparation-receipt.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="exact crop pixels"):
        reader.load(output, source.c)


def test_rehashed_wrong_source_gold_is_rejected_from_original_annotations(inputs):
    import gzip

    manifest, originals, derived, output = inputs
    source.prepare(manifest, originals, derived, output)
    path = output / "records.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        meta = json.load(stream)
    meta["records"][0]["answer"] = 1
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(meta, stream)
    report = source.read(output / "preparation-receipt.json")
    report["records_sha256"] = source.sha(path)
    (output / "preparation-receipt.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="question/gold/pixel correspondence"):
        reader.load(output, source.c)


def test_source_gallery_does_not_clip_large_original_rois_or_overlap_neighbors():
    crops = [Image.new("RGB", (173, 211), (i * 20, 40, 50)) for i in range(10)]
    original = [np.asarray(crop).copy() for crop in crops]
    sheet = source.source_gallery(crops)
    pixels = np.asarray(sheet)
    assert sheet.size == (8 * 181, 2 * 219)
    for i, crop in enumerate(crops):
        x, y = i % 8 * 181 + 4, i // 8 * 219 + 4
        assert np.array_equal(pixels[y : y + 211, x : x + 173], original[i])
        assert np.array_equal(np.asarray(crop), original[i])
        crop.close()
    sheet.close()
