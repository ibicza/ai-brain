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


def screen(reference, output):
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
        ],
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
