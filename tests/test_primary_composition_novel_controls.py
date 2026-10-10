import importlib.util
from pathlib import Path

import numpy as np
import pytest

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_composition_controls as controls

spec = importlib.util.spec_from_file_location(
    "novel_controls",
    Path(__file__).parents[1] / "scripts/m33_composition_novel_controls.py",
)
novel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(novel)


def test_cold_families_are_outside_all_prior_training_and_control_families():
    assert not set(novel.FAMILIES) & {
        *c.SHAPES,
        *controls.EXTENDED_EXPOSURE_SHAPES,
        *controls.HELD_OUT_SHAPES,
    }
    data = novel.generate(120, 50110000, c)
    assert {i["shape"] for s in data["scenes"] for i in s["items"]} == {
        *novel.FAMILIES,
        *c.SHAPES,
    }
    for record in data["records"]:
        if record["task"] == "shape" and record["family"] in novel.FAMILIES:
            assert record["answer"] == c.UNKNOWN


@pytest.mark.parametrize("family", novel.FAMILIES)
def test_cold_geometry_is_bounded_visible_and_reproducible(family):
    points = np.asarray(novel.contour(family))
    assert np.isfinite(points).all() and np.abs(points).max() <= 1.000001
    for seed in range(20):
        item = {
            "color": "красный",
            "shape": family,
            "pattern": "однотонный",
            "hidden": False,
        }
        row = {"seed": seed, "items": [item, item]}
        pixels = novel.render(row, c)
        assert pixels.shape == (96, 96, 3) and pixels.dtype == np.uint8
        assert np.array_equal(pixels, novel.render(row, c))
        assert ((pixels[:, :48, 0] > 180) & (pixels[:, :48, 1] < 80)).sum() > 50


def test_cold_hidden_targets_and_question_gold_correspondence():
    data = novel.generate(24, 50310000, c)
    assert np.all(data["pixels"][0, :, :48] == data["pixels"][0, 0, 0])
    for i, record in enumerate(data["records"]):
        assert c.QUERIES[record["question"]] == (record["task"], record["side"])
        assert data["labels"][i] == record["answer"]
        assert data["image_index"][i] == i // 6
    assert all(r["answer"] == c.UNKNOWN for r in data["records"][:3])
