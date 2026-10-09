"""Candidate choice must not peek at calibration/final or silently swap datasets."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "object_selection", ROOT / "scripts/m33_objects_select.py"
)
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)


def candidates(tmp_path):
    roots = []
    for name, channels, depth, score in (
        ("head0", 0, 0, 0.8),
        ("vision32", 32, 0, 0.2),
        ("vision64", 64, 2, 0.4),
    ):
        root = tmp_path / name
        root.mkdir()
        (root / "best.pt").write_bytes(b"checkpoint" + name.encode())
        protocol = {
            "development_only": True,
            "config": {"steps": 10000, "round_id": 10911},
        }
        (root / "protocol.json").write_text(json.dumps(protocol))
        report = {
            "status": "DEVELOPMENT_ONLY_NO_CALIBRATION_OR_FINAL",
            "production_admitted": False,
            "checkpoint_sha256": selector.sha(root / "best.pt"),
            "protocol_sha256": selector.sha(root / "protocol.json"),
            "inherited_tensors_byte_preserved": True,
            "best_dev_loss": score,
            "history": [{"dev_loss": score}],
            "dataset_sha256": "same-dataset",
            "best_step": 5000,
            "architecture": {
                "vision_extension_channels": channels,
                "vision_extension_depth": depth,
            },
            "parameters": 100,
        }
        (root / "development-report.json").write_text(json.dumps(report))
        roots.append(root)
    return roots


def test_winner_selected_by_development_loss_and_frozen(tmp_path):
    result = selector.select(candidates(tmp_path), tmp_path / "selection.json")
    assert result["winner"]["name"] == "vision32"
    assert result["selection_used"] == "DEVELOPMENT_ONLY"
    with pytest.raises(ValueError):
        selector.select([], tmp_path / "selection.json")


def test_tuning_mode_allows_recorded_learning_rate_changes_not_dataset_changes(
    tmp_path,
):
    roots = candidates(tmp_path)
    path = roots[1] / "protocol.json"
    protocol = json.loads(path.read_text())
    protocol["config"]["learning_rate"] = 0.0003
    path.write_text(json.dumps(protocol))
    report_path = roots[1] / "development-report.json"
    report = json.loads(report_path.read_text())
    report["protocol_sha256"] = selector.sha(path)
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        selector.select(roots, tmp_path / "matched.json")
    result = selector.select(roots, tmp_path / "tuning.json", tuning=True)
    assert result["winner"]["learning_rate"] == 0.0003
    assert (
        result["comparison"]
        == "DEVELOPMENT_HYPERPARAMETER_TUNING_NOT_WEIGHT_SIZE_CAUSAL_PROOF"
    )


@pytest.mark.parametrize(
    "bad", ["final", "checkpoint", "dataset", "score", "architecture"]
)
def test_contaminated_or_inconsistent_candidates_rejected(tmp_path, bad):
    roots = candidates(tmp_path)
    root = roots[0]
    if bad == "final":
        (root / "object-final-predictions.json").write_text("[]")
    elif bad == "checkpoint":
        (root / "best.pt").write_bytes(b"swapped")
    else:
        path = root / "development-report.json"
        report = json.loads(path.read_text())
        if bad == "dataset":
            report["dataset_sha256"] = "different-dataset"
        elif bad == "score":
            report["best_dev_loss"] = float("nan")
        else:
            report["architecture"]["vision_extension_channels"] = 16
        path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        selector.select(roots, tmp_path / "selection.json")
