"""Development study agreement never averages contradictory assertions."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "m33_composition_dev_probe",
    Path(__file__).parents[1] / "scripts/m33_composition_dev_probe.py",
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_agreement_uses_the_weakest_candidate_and_refuses_disagreement():
    a = [[0.94, 0.02, 0.04], [0.95, 0.02, 0.03], [0.02, 0.01, 0.97]]
    b = [[0.91, 0.01, 0.08], [0.02, 0.95, 0.03], [0.92, 0.01, 0.07]]
    p = probe.fuse([a, b], unknown=2)
    assert np.allclose(p[0], [0.91, 0.0, 0.09])
    assert np.array_equal(p[1:], [[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]])
    assert np.allclose(p.sum(-1), 1)
    assert np.array_equal(p, probe.fuse([b, a], unknown=2))


@pytest.mark.parametrize(
    "scores,unknown",
    [
        ([[[0.9, 0.1]]], 1),
        ([[[float("nan"), 0.1]], [[0.9, 0.1]]], 1),
        ([[[0.5, 0.6]], [[0.9, 0.1]]], 1),
        ([[[-0.1, 1.1]], [[0.9, 0.1]]], 1),
        ([[[0.9, 0.1]], [[0.9, 0.1]]], -1),
        ([[[0.9, 0.1]], [[0.9, 0.1]]], True),
    ],
)
def test_invalid_scores_or_unknown_scope_are_rejected(scores, unknown):
    with pytest.raises(ValueError, match="agreement"):
        probe.fuse(scores, unknown)
