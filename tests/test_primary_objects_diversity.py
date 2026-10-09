"""Diversity changes never move related artwork into competing partitions."""

import importlib.util
import sys
from pathlib import Path

import pytest
import torch

from ai_brain.training.primary_object_augmentation import diverse_view

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location(
    "diversity_prepare",
    Path(__file__).parents[1] / "scripts/m33_objects_expand_prepare.py",
)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def test_related_colors_join_even_when_pixels_different():
    records = [
        {"declared_family": "publisher/book"},
        {"declared_family": "publisher/book"},
        {"declared_family": "other/book"},
    ]
    groups = prepare.declared_groups(records, [0, 1, 2])
    assert groups[0] == groups[1] != groups[2]


def test_predeclared_style_ownership_prevents_training_leakage():
    records = [
        {"source_id": "train", "answer": "book", "declared_split": "train"},
        {"source_id": "final", "answer": "book", "declared_split": "final"},
    ]
    admitted, excluded, _ = prepare.assign_groups(records, [0, 0])
    assert not admitted and len(excluded) == 2


def test_old_illustration_final_remains_regression_in_next_iteration():
    records = [
        {
            "source_id": "old-final",
            "answer": "book",
            "parent": True,
            "split": "regression",
            "declared_split": "final",
        }
    ]
    admitted, excluded, _ = prepare.assign_groups(records, [0])
    assert admitted[0][1] == "regression" and not excluded


def test_augmented_pixels_bounded_finite_and_reproducible():
    image = torch.ones(8, 3, 96, 96)
    image[:, :, 30:65, 35:60] = 0
    torch.manual_seed(99)
    output = diverse_view(image)
    torch.manual_seed(99)
    assert torch.equal(output, diverse_view(image))
    assert torch.isfinite(output).all() and output.min() >= 0 and output.max() <= 1
    assert not torch.equal(image, output)
    assert torch.equal(image[:, :, 30:65, 35:60], torch.zeros(8, 3, 35, 25))
    assert (output.mean(1) < 0.6).flatten(1).sum(1).min() > 300
    assert output[:, :, :3].mean() > 0.85


@pytest.mark.parametrize("shape", [(2, 3, 32, 32), (2, 1, 96, 96), (3, 96, 96)])
def test_bad_image_shape_rejected(shape):
    with pytest.raises(ValueError):
        diverse_view(torch.zeros(shape))
