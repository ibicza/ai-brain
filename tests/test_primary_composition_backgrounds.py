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
