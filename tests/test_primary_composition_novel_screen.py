"""Actual frozen-source cold-screen subprocess, including hostile policy edits."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from ai_brain.training import primary_objects as old

REPO = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, REPO / "scripts" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    root = tmp_path_factory.mktemp("novel-source-reference")
    package = load("m33_composition_package")
    pilot = load("m33_primary_composition_pilot")
    manifest = package.build(REPO, root / "source-capsule.tgz")
    torch.manual_seed(510)
    previous = old.ObjectsModel(width=32, layers=1)
    torch.save(
        {
            "model": previous.state_dict(),
            "width": 32,
            "layers": 1,
            "compatible_legacy_vocabulary": True,
        },
        root / "previous.pt",
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("AI_BRAIN_CAPSULE_SHA256", manifest["capsule_sha256"])
        pilot.run(
            SimpleNamespace(
                output=root / "experiment",
                spatial_readout=False,
                shape_edges=False,
                label_smoothing=0.0,
                reflection_consensus=True,
                auxiliary_images=12,
                consistency_loss=0.2,
                exposure_profile="diverse",
                numeric_precision="ieee",
                previous=root / "previous.pt",
                warm_candidate=None,
                dataset_profile="curve_background_clear",
                seed=13000,
                steps=2,
                eval_every=2,
                train_images=12,
                holdout_images=12,
                device="cpu",
            )
        )
    return root


def screen(reference, output, prepared_source=None):
    return subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/m33_composition_novel_screen.py"),
            "--reference",
            str(reference),
            "--output",
            str(output),
            "--seed",
            "60113000",
            "--count",
            "12",
            "--device",
            "cpu",
        ]
        + (["--prepared-source", str(prepared_source)] if prepared_source else []),
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
    )


def test_actual_original_capsule_is_used_for_frozen_cold_inference(reference, tmp_path):
    output = tmp_path / "cold"
    result = screen(reference, output)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / "result.json").read_text())
    freeze = json.loads((output / "preregistered-freeze.json").read_text())
    assert report["independent_inference_and_arithmetic_replayed"]
    assert report["production_admitted"] is False
    assert freeze["training_or_calibration"] is False
    assert freeze["families"] == ["semicircle", "teardrop", "chevron"]
    assert freeze["numeric_backend"]["policy"] == "ieee"
    assert set(report["per_family"]) >= set(freeze["families"])
    assert (output / "artifact-manifest.json").is_file()


def test_actual_original_capsule_replays_prepared_pdf_source(reference, tmp_path):
    import pypdfium2
    from reportlab.pdfgen import canvas

    source = load("m33_composition_source_prepare")
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
    policy = source.read(REPO / "examples/m33/visual_source_controls_v1.json")
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
    # Four explicit ROIs make twelve ordered scenes; this checks transport of
    # source tensors, not independent semantic labeling or trained performance.
    policy["assets"] = [
        {
            "id": "red-circle",
            "source": "fixture",
            "bbox_pixels": [10, 34, 38, 62],
            "color": "красный",
            "shape": "круг",
            "pattern": "однотонный",
            "absent": False,
        }
    ] + [
        {
            "id": f"empty-{i}",
            "source": "fixture",
            "bbox_pixels": box,
            "color": None,
            "shape": None,
            "pattern": None,
            "absent": True,
        }
        for i, box in enumerate(([65, 34, 93, 62], [65, 0, 93, 28], [65, 68, 93, 96]))
    ]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(policy), encoding="utf-8")
    prepared = tmp_path / "prepared"
    source.prepare(manifest, originals, derived, prepared)
    output = tmp_path / "source-screen"
    completed = screen(reference, output, prepared)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((output / "result.json").read_text())
    freeze = json.loads((output / "preregistered-freeze.json").read_text())
    assert report["independent_inference_and_arithmetic_replayed"]
    assert report["production_admitted"] is False
    assert set(report["per_source_asset"]) == {a["id"] for a in policy["assets"]}
    assert freeze["group_kind"] == "source_asset"
    assert len(freeze["source_preparation_hashes"]) == 7
    assert freeze["source_preparation_receipt"]["training_or_calibration"] is False
    assert (output / "actual-source-inputs.png").is_file()


def test_changed_threshold_is_rejected_before_output(reference, tmp_path):
    path = reference / "experiment/policy-frozen.json"
    original = path.read_bytes()
    try:
        policy = json.loads(original)
        policy["tasks"]["color"]["threshold"] = 0.123
        path.write_text(json.dumps(policy), encoding="utf-8")
        output = tmp_path / "tampered"
        result = screen(reference, output)
        assert result.returncode != 0
        assert "Reference frozen thresholds changed" in result.stderr
        assert not output.exists()
    finally:
        path.write_bytes(original)


def test_existing_evidence_output_cannot_be_overwritten(reference, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "preserve.txt"
    marker.write_text("old evidence", encoding="utf-8")
    result = screen(reference, output)
    assert result.returncode != 0 and "Fresh cold screen required" in result.stderr
    assert marker.read_text() == "old evidence"
