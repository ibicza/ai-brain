from dataclasses import replace

import numpy as np
import pytest
import torch

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_composition_controls as controls
from ai_brain.training import primary_composition_supervision as s
from ai_brain.training import primary_composition_views as views
from ai_brain.training import primary_objects as old


def test_sampler_equal_task_then_answer_not_uniform_rows():
    records = [{"task": "shape", "answer": 1}] * 500 + [
        {"task": "shape", "answer": 2},
        {"task": "color", "answer": 3},
        {"task": "pattern", "answer": 4},
    ]
    sampler = s.GroupSampler(records)
    chosen = sampler.sample(np.random.default_rng(42), 18000)
    counts = {}
    for i in chosen:
        key = (records[i]["task"], records[i]["answer"])
        counts[key] = counts.get(key, 0) + 1
    assert 2800 < counts[("shape", 1)] < 3200
    assert 2800 < counts[("shape", 2)] < 3200
    assert 5700 < counts[("color", 3)] < 6300
    assert 5700 < counts[("pattern", 4)] < 6300
    assert np.array_equal(chosen, sampler.sample(np.random.default_rng(42), 18000))
    assert all(
        records[i]["task"] != "pattern"
        for i in sampler.sample(np.random.default_rng(43), 1000, omit_pattern=True)
    )
    with pytest.raises(ValueError):
        sampler.sample(np.random.default_rng(1), 0)


def test_foreground_is_exact_visible_mask_without_paper_and_no_rgb_change():
    scene = controls.scenes(
        "exposure", 1, 2134567, exposure_profile="palette_paper_aspects"
    )[0]
    scene = replace(
        scene,
        items=(
            replace(scene.items[0], hidden=False),
            replace(scene.items[1], hidden=True),
        ),
    )
    rgb, masks = controls.render(scene, return_foreground=True)
    assert np.array_equal(rgb, controls.render(scene))
    assert masks.shape == (2, 96, 96) and masks.dtype == np.uint8
    assert masks[0].sum() > 0 and masks[1].sum() == 0
    assert masks[0, :, 48:].sum() == 0
    assert not np.array_equal(masks[0], np.ones((96, 96), np.uint8) * 255)
    data = controls.prepare([scene], include_foreground=True)
    assert np.array_equal(data["pixels"][0], rgb)
    assert np.array_equal(data["foreground"][0], masks)
    assert "foreground" not in controls.prepare([scene])


def test_gold_attention_excludes_empty_targets_and_has_correct_gradient():
    logits = torch.zeros(2, 144, requires_grad=True)
    attention = logits.softmax(1)
    masks = torch.zeros(2, 1, 96, 96)
    masks[0, :, :8, :8] = 1
    loss = s.foreground_attention_loss(attention, masks)
    loss.backward()
    assert torch.isfinite(loss) and logits.grad[0, 0] < 0
    assert torch.all(logits.grad[0, 1:] > 0)
    assert torch.count_nonzero(logits.grad[1]) == 0
    assert s.foreground_attention_loss(attention, torch.zeros_like(masks)) == 0
    with pytest.raises(ValueError):
        s.foreground_attention_loss(attention, masks + 2)


def test_training_attention_does_not_change_inference_logits_or_inherited_tensors():
    torch.set_num_threads(2)
    model = c.CompositionModel(
        old.ObjectsModel(width=32, layers=1), spatial_readout=True, shape_edges=True
    ).eval()
    before = {k: v.clone() for k, v in model.inherited.state_dict().items()}
    images = torch.rand(2, 3, 96, 96)
    q = torch.tensor([c.encode_question(c.question("shape", side)) for side in (0, 1)])
    logits, attention = model(images, q, return_attention=True)
    assert torch.equal(logits, model(images, q))
    assert attention.shape == (2, 144)
    masks = torch.zeros(2, 1, 96, 96)
    masks[:, :, 24:48, 12:36] = 1
    s.foreground_attention_loss(attention, masks).backward()
    assert model.query_projection[0].weight.grad.abs().sum() > 0
    assert model.pixel_residual[-1].weight.grad.abs().sum() > 0
    assert all(p.grad is None for p in model.inherited.parameters())
    assert all(
        torch.equal(v, model.inherited.state_dict()[k]) for k, v in before.items()
    )


def test_reflection_keeps_mask_and_question_target_aligned_without_extra_rng_draws():
    images = torch.rand(10, 3, 96, 96)
    masks = images[:, :1].clone()
    q = torch.tensor([c.encode_question(c.question("shape", 0))] * 10)
    x, questions, targets = views.augment_batch(
        images, q, np.random.default_rng(51), supervision=masks
    )
    ordinary_x, ordinary_q = views.augment_batch(images, q, np.random.default_rng(51))
    assert torch.equal(x, ordinary_x) and torch.equal(questions, ordinary_q)
    assert torch.equal(targets, x[:, :1])
