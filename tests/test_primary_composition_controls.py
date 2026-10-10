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
    for shape in (
        *c.SHAPES,
        *controls.EXTENDED_EXPOSURE_SHAPES,
        *controls.HELD_OUT_SHAPES,
    ):
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


def test_diverse_exposure_is_opt_in_and_never_imports_held_contours():
    standard = controls.scenes("exposure", 300, 301900)
    diverse = controls.scenes("exposure", 300, 301900, exposure_profile="diverse")
    assert standard == controls.scenes(
        "exposure", 300, 301900, exposure_profile="standard"
    )
    assert {i.shape for s in standard for i in s.items} - set(c.SHAPES) == set(
        controls.EXPOSURE_SHAPES
    )
    assert {i.shape for s in diverse for i in s.items} - set(c.SHAPES) == set(
        controls.EXTENDED_EXPOSURE_SHAPES
    )
    assert not {i.shape for s in diverse for i in s.items} & set(
        controls.HELD_OUT_SHAPES
    )
    held = controls.scenes("held_control", 60, 302900)
    assert held == controls.scenes(
        "held_control", 60, 302900, exposure_profile="diverse"
    )
    for item in (i for s in diverse for i in s.items if not i.hidden):
        scene = controls.ControlScene("scope", 42, (item, item))
        assert (scene.gold("shape", 0) == c.UNKNOWN) == (item.shape not in c.SHAPES)
        assert scene.gold("color", 0) != c.UNKNOWN
        assert scene.gold("pattern", 0) != c.UNKNOWN
    with pytest.raises(ValueError, match="Invalid control"):
        controls.scenes("exposure", 3, 42, exposure_profile="unregistered")


@pytest.mark.parametrize("shape", controls.EXTENDED_EXPOSURE_SHAPES)
def test_new_contours_are_bounded_visible_and_distinct_from_supported_shapes(shape):
    points = np.asarray(controls.vertices(shape))
    assert points.shape[1] == 2 and np.isfinite(points).all()
    assert np.abs(points).max() <= 1.000001
    for seed in range(20):
        scene = controls.ControlScene(
            "geometry",
            seed,
            (
                controls.ControlItem("красный", shape, "однотонный"),
                controls.ControlItem("синий", "круг", "однотонный"),
            ),
        )
        pixels = controls.render(scene)
        assert ((pixels[:, :48, 0] > 180) & (pixels[:, :48, 1] < 80)).sum() > 50


def test_audit_rejects_wrong_exposure_profile_and_extended_contours_in_final():
    native = {"train": c.prepare(c.scenes("train", 2, 80300))}
    extra = {
        "exposure": controls.prepare(
            controls.scenes("exposure", 60, 80400, exposure_profile="diverse")
        ),
        "control_final": controls.prepare(controls.scenes("held_control", 2, 80500)),
    }
    result = controls.audit(extra, native, exposure_profile="diverse")
    assert result["exposure_shapes"] == controls.EXTENDED_EXPOSURE_SHAPES
    with pytest.raises(ValueError, match="Held control"):
        controls.audit(extra, native)
    extra["control_final"]["scenes"][0]["items"][0]["shape"] = "heart"
    with pytest.raises(ValueError, match="Exposure contour"):
        controls.audit(extra, native, exposure_profile="diverse")


def test_palette_exposure_has_explicit_unknown_colors_and_separate_finals():
    train = controls.scenes("exposure", 300, 90400, exposure_profile="palette")
    held = controls.scenes("held_control", 300, 90500, exposure_profile="palette")
    train_colors = {i.color for s in train for i in s.items} - set(c.COLORS)
    held_colors = {i.color for s in held for i in s.items} - set(c.COLORS)
    assert train_colors == set(controls.PALETTE_UNKNOWN_RGB)
    assert held_colors == set(controls.PALETTE_HELD_RGB)
    assert not train_colors & held_colors
    assert all(s.renderer_profile == "palette" for s in (*train, *held))
    assert not {i.shape for s in train for i in s.items} & set(controls.HELD_OUT_SHAPES)
    for scene in (*train[:30], *held[:30]):
        image = controls.render(scene)
        assert image.dtype == np.uint8 and np.array_equal(image, controls.render(scene))
        assert image[0, 0].min() >= 246
        for side, item in enumerate(scene.items):
            assert (scene.gold("color", side) == c.UNKNOWN) == (
                item.hidden or item.color not in c.COLORS
            )


def test_palette_audit_rejects_held_color_in_training_even_with_correct_shape():
    native = {"train": c.prepare(c.scenes("train", 2, 90600))}
    extra = {
        "exposure": controls.prepare(
            controls.scenes("exposure", 12, 90700, exposure_profile="palette")
        ),
        "control_final": controls.prepare(
            controls.scenes("held_control", 12, 90800, exposure_profile="palette")
        ),
    }
    result = controls.audit(extra, native, exposure_profile="palette")
    assert result["held_unknown_colors"] == ("бирюзовый",)
    extra["exposure"]["scenes"][0]["items"][0]["color"] = "бирюзовый"
    with pytest.raises(ValueError, match="Held color"):
        controls.audit(extra, native, exposure_profile="palette")


@pytest.mark.parametrize("shape", ("parallelogram", "kite"))
def test_palette_new_contours_have_no_right_angles_and_are_bounded(shape):
    points = np.asarray(controls.vertices(shape))
    edges = np.roll(points, -1, axis=0) - points
    assert np.abs(points).max() <= 1
    assert np.abs((edges * np.roll(edges, -1, axis=0)).sum(axis=1)).min() > 0.01
    for seed in range(10):
        scene = controls.ControlScene(
            "bounded",
            seed,
            (
                controls.ControlItem("красный", shape, "однотонный"),
                controls.ControlItem("синий", "круг", "однотонный"),
            ),
            "palette",
        )
        assert controls.render(scene).shape == (96, 96, 3)


@pytest.mark.parametrize("profile", ("palette_independent", "palette_aspects"))
def test_independent_palette_covers_unknown_colors_on_every_supported_shape(profile):
    rows = controls.scenes(
        "exposure", 3000, 1304500000 + 60000, exposure_profile=profile
    )
    pairs = {
        (item.color, item.shape)
        for scene in rows
        for item in scene.items
        if not item.hidden
    }
    assert {
        (color, shape) for color in controls.PALETTE_UNKNOWN_RGB for shape in c.SHAPES
    } <= pairs
    counts = {
        (color_known, shape_known): 0
        for color_known in (False, True)
        for shape_known in (False, True)
    }
    for scene in rows:
        for item in scene.items:
            if not item.hidden:
                counts[item.color in c.COLORS, item.shape in c.SHAPES] += 1
    assert min(counts.values()) > 400
    held = controls.scenes(
        "held_control", 600, 1304500000 + 80000, exposure_profile=profile
    )
    assert not {i.color for s in rows for i in s.items} & set(controls.PALETTE_HELD_RGB)
    assert not {i.shape for s in rows for i in s.items} & set(controls.HELD_OUT_SHAPES)
    assert not {i.color for s in held for i in s.items} & set(
        controls.PALETTE_UNKNOWN_RGB
    )


def test_old_palette_profile_remains_the_archival_conditional_color_design():
    rows = controls.scenes("exposure", 300, 90400, exposure_profile="palette")
    assert all(
        item.shape not in c.SHAPES
        for scene in rows
        for item in scene.items
        if item.color not in c.COLORS
    )


def test_aspect_profile_changes_only_elongated_geometry_not_labels_or_other_items():
    from dataclasses import replace

    old_rows = controls.scenes(
        "exposure", 30, 151000, exposure_profile="palette_independent"
    )
    rows = controls.scenes("exposure", 30, 151000, exposure_profile="palette_aspects")
    assert [(s.seed, s.items) for s in rows] == [(s.seed, s.items) for s in old_rows]
    changed = 0
    for prior in old_rows:
        prior = replace(
            prior,
            items=(
                controls.ControlItem("красный", "овал", "однотонный"),
                controls.ControlItem("синий", "star", "полосатый"),
            ),
        )
        row = replace(prior, renderer_profile="palette_aspects")
        a, b = controls.render(prior), controls.render(row)
        # Close aspect draws can coincide after supersampled raster rounding.
        changed += not np.array_equal(a[:, :48], b[:, :48])
        assert np.array_equal(a[:, 48:], b[:, 48:])
        assert np.array_equal(b, controls.render(row))
    assert changed >= 25
