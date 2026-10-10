import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "numeric_probe",
    Path(__file__).parents[1] / "scripts/m33_composition_numeric_probe.py",
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_comparison_records_rounding_and_changed_argmax():
    a = np.array([[0.8, 0.2], [0.49, 0.51]])
    b = np.array([[0.801, 0.199], [0.52, 0.48]])
    report = probe.compare(a, b)
    assert report["examples"] == 2
    assert report["raw_argmax_disagreements"] == 1
    assert report["max_absolute_score_difference"] == pytest.approx(0.03)
    assert probe.compare(a, a)["max_absolute_score_difference"] == 0


@pytest.mark.parametrize(
    "candidate", ([], [[float("nan"), 1]], [[float("inf"), 1]], [1, 2], [[1, 2, 3]])
)
def test_invalid_score_intervention_comparisons_rejected(candidate):
    with pytest.raises(ValueError, match="Comparable finite"):
        probe.compare([[0.1, 0.9]], candidate)


def test_non_cuda_study_rejected_without_creating_output(tmp_path):
    output = tmp_path / "study"
    with pytest.raises(ValueError, match="Fresh CUDA"):
        probe.run(tmp_path / "missing", output, "cpu")
    assert not output.exists()
