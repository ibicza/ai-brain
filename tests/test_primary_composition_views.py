"""Semantic remapping, conservative score arithmetic and independent replay."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
import torch

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_composition_views as v


def test_side_swap_is_exact_involution_for_every_supported_query():
    for task in c.VALUES:
        for side in (0, 1):
            for template in range(3):
                q = torch.tensor([c.encode_question(c.question(task, side, template))])
                original = q.clone()
                swapped = v.swap_sides(q)
                assert swapped[0].tolist() == c.encode_question(
                    c.question(task, 1 - side, template)
                )
                assert torch.equal(v.swap_sides(swapped), q)
                assert torch.equal(q, original)


def test_reflection_pixels_and_questions_keep_original_untouched():
    x = torch.arange(36).reshape(1, 3, 3, 4).float()
    q = torch.tensor([c.encode_question(c.question("shape", 0))])
    xx, qq = v.reflected(x, q, horizontal=True, vertical=True)
    assert torch.equal(xx, x.flip((2, 3)))
    assert torch.equal(qq, v.swap_sides(q))
    back_x, back_q = v.reflected(xx, qq, horizontal=True, vertical=True)
    assert torch.equal(back_x, x) and torch.equal(back_q, q)


def test_one_disagreeing_confident_view_forces_unknown():
    pp = torch.zeros(4, 2, len(c.ANSWERS))
    pp[:, :, 0] = 0.98
    pp[:, :, c.UNKNOWN] = 0.02
    pp[3, 0, 0], pp[3, 0, 1] = 0, 0.98
    pp[2, 1, 0], pp[2, 1, c.UNKNOWN] = 0.91, 0.09
    result = v.unanimous_scores(pp)
    assert result[0, c.UNKNOWN] == 1
    assert result[0].argmax() == c.UNKNOWN
    assert result[1, 0] == pytest.approx(0.91)
    assert result[1, c.UNKNOWN] == pytest.approx(0.09)
    assert torch.allclose(result.sum(-1), torch.ones(2))


@pytest.mark.parametrize("bad", ("nan", "negative", "sum", "views"))
def test_invalid_view_outputs_are_rejected(bad):
    p = torch.zeros(4, 1, len(c.ANSWERS))
    p[:, :, c.UNKNOWN] = 1
    if bad == "nan":
        p[0, 0, 0] = float("nan")
    elif bad == "negative":
        p[0, 0, 0] = -0.1
    elif bad == "sum":
        p[0, 0, 0] = 0.2
    else:
        p = p[:3]
    with pytest.raises(ValueError, match="four-view"):
        v.unanimous_scores(p)


def test_training_reflections_are_reproducible_and_do_not_mutate_input():
    x = torch.rand(20, 3, 96, 96)
    q = torch.tensor([c.encode_question(c.question("color", i % 2)) for i in range(20)])
    before = x.clone(), q.clone()
    a = v.augment_batch(x, q, np.random.default_rng(19))
    b = v.augment_batch(x, q, np.random.default_rng(19))
    assert all(torch.equal(aa, bb) for aa, bb in zip(a, b, strict=True))
    assert torch.equal(x, before[0]) and torch.equal(q, before[1])
    assert all(
        row.tolist() in (q[i].tolist(), v.swap_sides(q[i : i + 1])[0].tolist())
        for i, row in enumerate(a[1])
    )


def test_independent_replay_matches_fixed_policy_without_calling_helper(monkeypatch):
    torch.set_num_threads(2)
    from ai_brain.training import primary_objects as old

    model = c.CompositionModel(old.ObjectsModel(width=32, layers=1)).eval()
    data = c.prepare(c.scenes("final", 2, 220111, profile="diverse_clear"))
    pixels = (
        torch.from_numpy(data["pixels"][data["image_index"]])
        .permute(0, 3, 1, 2)
        .float()
        / 255
    )
    questions = torch.from_numpy(data["questions"])
    expected = v.consistent_probabilities(model, pixels, questions).numpy()
    spec = importlib.util.spec_from_file_location(
        "view_replay", Path(__file__).parents[1] / "scripts/m33_composition_verify.py"
    )
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    monkeypatch.setattr(
        v,
        "consistent_probabilities",
        lambda *a: pytest.fail("replay must be independent"),
    )
    arrays = {
        "final_" + k: data[k] for k in ("pixels", "questions", "labels", "image_index")
    }
    actual = verifier.replay(model, arrays, "final", "cpu", reflection_consensus=True)
    np.testing.assert_allclose(actual, expected, atol=2e-6)
