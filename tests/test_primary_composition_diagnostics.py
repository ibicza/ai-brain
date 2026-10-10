"""Diagnostic previews must show actual stored inputs, never reconstructed art."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

spec = importlib.util.spec_from_file_location(
    "composition_diagnostics",
    Path(__file__).parents[1] / "scripts/m33_composition_diagnostics.py",
)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


def fixture(root, *, corrupt=""):
    pixels = np.full((2, 96, 96, 3), 119, dtype=np.uint8)
    pixels[1, :, :, 0] = 71
    records = [
        {
            "scene_id": "transfer/0",
            "image_sha256": hashlib.sha256(pixels[1].tobytes()).hexdigest(),
            "question": "What color?",
            "task": "color",
            "side": 0,
            "answer": 0,
        },
        {
            "scene_id": "transfer/1",
            "image_sha256": hashlib.sha256(pixels[0].tobytes()).hexdigest(),
            "question": "What color?",
            "task": "color",
            "side": 1,
            "answer": 0,
        },
    ]
    data = {
        "records": records,
        "selected": [1, diagnostics.course.UNKNOWN],
        "probabilities": [[0.01, 0.99], [0, 1]],
    }
    for name, value in (
        ("transfer-predictions.json.gz", data),
        ("dataset-records.json.gz", {"transfer": {"records": records}}),
    ):
        with gzip.open(root / name, "wt", encoding="utf-8") as stream:
            json.dump(value, stream)
    labels = np.array([0, 0])
    indices = np.array([1, 0])
    if corrupt == "pixels":
        pixels[1, 0, 0, 0] += 1
    if corrupt == "labels":
        labels[0] = 1
    if corrupt == "indices":
        indices[0] = -1
    np.savez(
        root / "dataset.npz",
        transfer_pixels=pixels,
        transfer_labels=labels,
        transfer_image_index=indices,
    )
    return pixels


def test_exposed_preview_has_exact_saved_pixels_and_no_fresh_claim(tmp_path):
    pixels = fixture(tmp_path)
    output, preview = tmp_path / "diagnostic.json", tmp_path / "errors.png"
    result = diagnostics.exposed_errors(tmp_path, "transfer", output, preview)
    assert result["false_assertions"] == 1
    assert result["preview_records"] == [0]
    assert result["status"] == "EXPOSED_FINAL_ERRORS_NOT_FRESH_TEST"
    assert result["production_admitted"] is False
    with Image.open(preview) as image:
        assert np.array_equal(np.asarray(image)[:96, :96], pixels[1])
    assert len(result["sha256"]) == 4


@pytest.mark.parametrize("corrupt", ["pixels", "labels", "indices"])
def test_rejects_changed_saved_input_before_writing(tmp_path, corrupt):
    fixture(tmp_path, corrupt=corrupt)
    output, preview = tmp_path / "diagnostic.json", tmp_path / "errors.png"
    with pytest.raises(ValueError):
        diagnostics.exposed_errors(tmp_path, "transfer", output, preview)
    assert not output.exists() and not preview.exists()


def test_no_overwrite_and_no_unseen_split(tmp_path):
    output, preview = tmp_path / "diagnostic.json", tmp_path / "errors.png"
    with pytest.raises(ValueError, match="evaluated"):
        diagnostics.exposed_errors(tmp_path, "train", output, preview)
    output.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="Fresh"):
        diagnostics.exposed_errors(tmp_path, "transfer", output, preview)
    assert output.read_text(encoding="utf-8") == "keep"
