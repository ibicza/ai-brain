from dataclasses import replace

import numpy as np
import pytest

from ai_brain.training import primary_composition as c
from ai_brain.training.primary_composition_rng_audit import audit


def test_wide_profile_changes_only_style_not_labels_or_old_rng_geometry():
    old = c.scenes("train", 20, 91000, profile="diverse_clear")
    wide = c.scenes("train", 20, 91000, profile="background_clear")
    assert [(s.seed, s.items) for s in old] == [(s.seed, s.items) for s in wide]
    for original, new in zip(old, wide, strict=True):
        assert new.style == "diverse_background_clear"
        assert np.array_equal(
            c.render(new),
            c.render_diverse(original, background_override=c.sample_background(new)),
        )
    assert {
        s.style for s in c.scenes("transfer", 12, 92000, profile="background_clear")
    } == {"challenge_background_clear"}


def test_wide_background_is_not_conditioned_on_object_labels_or_hidden_state():
    original = c.scenes("train", 1, 93000, profile="background_clear")[0]
    baseline = c.sample_background(original)
    for color in c.COLORS:
        for shape in c.SHAPES:
            for pattern in c.PATTERNS:
                altered = replace(
                    original,
                    items=(
                        c.Item(color, shape, pattern),
                        c.Item(color, shape, pattern, True),
                    ),
                )
                assert np.array_equal(c.sample_background(altered), baseline)


def test_actual_background_domain_is_broad_finite_and_replayable():
    rows = c.scenes("train", 1000, 94000, profile="background_clear")
    samples = np.stack([c.sample_background(s) for s in rows])
    assert np.isfinite(samples).all()
    assert samples.min() >= 54 and samples.max() <= 211
    assert (samples.mean(-1) < 75).sum() > 70
    assert (samples.mean(-1) > 190).sum() > 70
    assert np.array_equal(samples, np.stack([c.sample_background(s) for s in rows]))


@pytest.mark.parametrize("profile", c.DATASET_PROFILES)
def test_background_audit_uses_the_selected_actual_renderer_family(profile):
    result = audit(seed=95100000, profile=profile)
    assert result["dataset_profile"] == profile
    assert result["known_shortcut_absent"]
    assert all(0.30 < a < 0.38 for a in result["background_only_pattern_accuracy"])


def test_wide_transfer_keeps_foreground_and_challenge_families_exactly_paired():
    for original in c.scenes("transfer", 10, 96000, profile="diverse_clear"):
        wide = replace(original, style="challenge_background_clear")
        assert np.array_equal(
            c.render(wide),
            c.render_diverse(original, background_override=c.sample_background(wide)),
        )


def test_direct_diverse_renderer_keeps_archival_background_draw_even_for_standard_scene():
    row = c.scenes("dev", 1, 98100, profile="legacy")[0]
    original_uniform = np.random.default_rng(row.seed).uniform(100, 180, 3)
    assert np.array_equal(
        c.sample_background(row, diverse_renderer=True), original_uniform
    )
    assert np.array_equal(
        c.render_diverse(row),
        c.render_diverse(row, background_override=original_uniform),
    )


def test_quadratic_profile_preserves_labels_and_holds_out_sinusoidal_transfer():
    old = c.scenes("train", 20, 101000, profile="background_clear")
    curved = c.scenes("train", 20, 101000, profile="curve_background_clear")
    assert [(s.seed, s.items) for s in old] == [(s.seed, s.items) for s in curved]
    assert {s.style for s in curved} == {"diverse_curve_background_clear"}
    assert c.scenes(
        "transfer", 20, 102000, profile="curve_background_clear"
    ) == c.scenes("transfer", 20, 102000, profile="background_clear")


@pytest.mark.parametrize("pattern", c.PATTERNS)
def test_quadratic_flag_does_not_change_unrelated_textures_or_geometry(pattern):
    original = c.scenes("train", 1, 103000, profile="background_clear")[0]
    original = replace(
        original,
        items=(
            c.Item("красный", "овал", pattern),
            c.Item("синий", "круг", "однотонный"),
        ),
    )
    curved = replace(original, style="diverse_curve_background_clear")
    before, after = c.render(original), c.render(curved)
    assert np.array_equal(after, c.render(curved))
    assert np.array_equal(before[:, 48:], after[:, 48:])
    assert np.array_equal(c.sample_background(original), c.sample_background(curved))
    if pattern == "полосатый":
        assert not np.array_equal(before[:, :48], after[:, :48])
    else:
        assert np.array_equal(before, after)


def test_quadratic_profile_retains_one_third_exact_straight_stripe_scenes():
    original = c.scenes("train", 1, 103002, profile="background_clear")[0]
    original = replace(
        original,
        items=(
            c.Item("красный", "овал", "полосатый"),
            c.Item("синий", "круг", "полосатый"),
        ),
    )
    assert original.seed % 3 == 0
    assert np.array_equal(
        c.render(original),
        c.render(replace(original, style="diverse_curve_background_clear")),
    )


def test_rich_profile_keeps_labels_background_and_sinusoidal_holdout():
    old = c.scenes("train", 20, 109000, profile="curve_background_clear")
    rich = c.scenes("train", 20, 109000, profile="rich_curve_background_clear")
    assert [(s.seed, s.items) for s in old] == [(s.seed, s.items) for s in rich]
    assert all(
        np.array_equal(c.sample_background(a), c.sample_background(b))
        for a, b in zip(old, rich, strict=True)
    )
    assert c.scenes(
        "transfer", 20, 109100, profile="rich_curve_background_clear"
    ) == c.scenes("transfer", 20, 109100, profile="curve_background_clear")
    row = replace(
        old[0],
        items=(
            c.Item("красный", "овал", "полосатый"),
            c.Item("синий", "круг", "однотонный"),
        ),
    )
    wide = replace(row, style="diverse_rich_curve_background_clear")
    assert np.array_equal(c.render(wide), c.render(wide))
    assert not np.array_equal(c.render(row)[:, :48], c.render(wide)[:, :48])
    assert np.array_equal(c.render(row)[:, 48:], c.render(wide)[:, 48:])
