import numpy as np
import pytest

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_composition_controls as controls


def test_control_geometry_labels_are_not_the_legacy_shape_scope():
    scene = controls.ControlScene(
        "scope",
        1,
        (
            controls.ControlItem("зелёный", "triangle", "пятнистый"),
            controls.ControlItem("синий", "круг", "однотонный"),
        ),
    )
    assert scene.gold("shape", 0) == c.UNKNOWN
    assert scene.gold("color", 0) == c.ANSWERS.index("зелёный")
    assert scene.gold("pattern", 0) == c.ANSWERS.index("пятнистый")
    assert scene.gold("shape", 1) == c.ANSWERS.index("круг")


def test_unknown_families_are_separated_before_training():
    train = controls.scenes("exposure", 60, 201101)
    test = controls.scenes("held_control", 60, 301101)
    train_shapes = {x.shape for r in train for x in r.items} - set(c.SHAPES)
    test_shapes = {x.shape for r in test for x in r.items} - set(c.SHAPES)
    assert train_shapes == set(controls.EXPOSURE_SHAPES)
    assert test_shapes == set(controls.HELD_OUT_SHAPES)
    assert not train_shapes & test_shapes
    assert all(
        (x.color, x.shape) not in c.HELD_COMBINATIONS for r in train for x in r.items
    )


def test_render_is_deterministic_finite_and_contained():
    for shape in (*c.SHAPES, *controls.EXPOSURE_SHAPES, *controls.HELD_OUT_SHAPES):
        scene = controls.ControlScene(
            "geometry",
            49,
            (
                controls.ControlItem("красный", shape, "полосатый"),
                controls.ControlItem("белый", "круг", "пятнистый"),
            ),
        )
        image = controls.render(scene)
        assert image.shape == (96, 96, 3) and image.dtype == np.uint8
        assert np.array_equal(image, controls.render(scene))


def test_absent_target_does_not_leave_object_pixels_or_give_attribute_answers():
    a = controls.ControlItem("красный", "star", "полосатый", True)
    b = controls.ControlItem("синий", "квадрат", "однотонный")
    scene = controls.ControlScene("hidden", 82, (a, b))
    image = controls.render(scene)
    assert np.all(image[:, :48] == image[0, 0])
    assert all(scene.gold(task, 0) == c.UNKNOWN for task in c.VALUES)


def test_controls_keep_target_and_pixel_hash_correspondence():
    data = controls.prepare(controls.scenes("held_control", 8, 400111))
    assert data["pixels"].shape == (8, 96, 96, 3)
    assert data["questions"].shape == (48, 13)
    for i, record in enumerate(data["records"]):
        assert c.QUERIES[record["question"]] == (record["task"], record["side"])
        assert record["answer"] == data["labels"][i]
        assert data["image_index"][i] == i // 6
    assert len({r["image_sha256"] for r in data["records"]}) == 8


def test_invalid_control_requests_are_rejected():
    with pytest.raises(ValueError):
        controls.scenes("final", 20, 501)
    with pytest.raises(ValueError):
        controls.scenes("exposure", 0, 501)


def test_control_audit_forbids_family_and_seed_leakage():
    native = {"train": c.prepare(c.scenes("train", 4, 70100))}
    extra = {
        "exposure": controls.prepare(
            controls.scenes("exposure", 4, 70200, cohort="exposure")
        ),
        "control_calibration": controls.prepare(
            controls.scenes("exposure", 4, 70300, cohort="control_calibration")
        ),
        "control_final": controls.prepare(
            controls.scenes("held_control", 4, 70400, cohort="control_final")
        ),
    }
    result = controls.audit(extra, native)
    assert result["unique_scene_seeds"] == result["unique_scene_identities"] == 16
    extra["exposure"]["scenes"][0]["items"][0]["shape"] = "pentagon"
    with pytest.raises(ValueError, match="Held control"):
        controls.audit(extra, native)
    extra["exposure"]["scenes"][0]["items"][0]["shape"] = "cross"
    extra["control_final"]["scenes"][0]["seed"] = 70100
    with pytest.raises(ValueError, match="seed leakage"):
        controls.audit(extra, native)
