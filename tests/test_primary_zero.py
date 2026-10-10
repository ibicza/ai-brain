from dataclasses import replace

import numpy as np
import pytest
import torch

from ai_brain.training.primary_zero import (
    ANSWERS,
    COLORS,
    IMAGE_SIZE,
    QUESTION_LENGTH,
    QUESTIONS,
    SHAPES,
    UNKNOWN,
    VOCAB_SIZE,
    ObjectSpec,
    Scene,
    ZeroClassModel,
    audit_splits,
    calibrate,
    consensus_probabilities,
    corpus,
    encode_question,
    metrics,
    render,
    select_answer,
)


@pytest.fixture(scope="module")
def tiny_corpus():
    return corpus(train_scenes=28, holdout_scenes=14)


def scene(shape="круг", color="красный", kind="normal"):
    return Scene("unit", 12, "filled", kind, (ObjectSpec(shape, color, 32, 32, 8, 0),))


def one_hot(answer):
    values = [0.0] * VOCAB_SIZE
    values[answer] = 1.0
    return values


def test_textured_background_does_not_reuse_label_rng_bits():
    from ai_brain.training.primary_composition_rng_audit import audit_zero

    archival = audit_zero(independent_labels=False)
    independent = audit_zero()
    assert all(a > 0.85 for a in archival["background_only_count_shape_accuracy"])
    assert not archival["known_shortcut_absent"]
    assert independent["known_shortcut_absent"]
    assert all(
        0.13 < a < 0.22 for a in independent["background_only_count_shape_accuracy"]
    )


def components(mask):
    """Independent 8-connected pixel counter, not the scene object's length."""
    remaining = set(map(tuple, np.argwhere(mask)))
    count = 0
    while remaining:
        count += 1
        queue = [remaining.pop()]
        while queue:
            y, x = queue.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    pixel = (y + dy, x + dx)
                    if pixel in remaining:
                        remaining.remove(pixel)
                        queue.append(pixel)
    return count


def test_rendered_count_independent_pixel_oracle(tiny_corpus):
    for row in tiny_corpus["train"]:
        if (
            row.task != "count"
            or row.scene.style != "filled"
            or row.scene.kind not in {"normal", "mixed"}
        ):
            continue
        image, boxes = render(row.scene)
        assert components(np.any(image != 246, axis=2)) == row.answer
        assert len(boxes) == row.answer
        for box in boxes:
            x0, y0, x1, y1 = box["bbox_xyxy"]
            assert 0 <= x0 < x1 <= IMAGE_SIZE and 0 <= y0 < y1 <= IMAGE_SIZE


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("color", COLORS)
def test_prototype_identity_and_render(shape, color):
    s = scene(shape, color)
    image, evidence = render(s)
    assert s.gold("shape") == ANSWERS.index(shape)
    assert s.gold("color") == ANSWERS.index(color)
    assert s.gold("count") == 1
    assert evidence[0]["pixels"] >= 8
    assert image.dtype == np.uint8
    assert np.array_equal(image, render(s)[0])


def test_empty_is_zero_but_attributes_unknown():
    s = replace(scene(), objects=())
    assert s.gold("count") == 0
    assert s.gold("shape") == s.gold("color") == UNKNOWN


@pytest.mark.parametrize("kind", ("masked", "missing"))
def test_hidden_content_never_becomes_gold(kind):
    s = scene(kind=kind)
    assert all(s.gold(task) == UNKNOWN for task in QUESTIONS)
    assert render(s)[1] == []


def test_mixed_attributes_not_invented():
    a = ObjectSpec("круг", "красный", 17, 32, 6, 0)
    b = ObjectSpec("квадрат", "синий", 47, 32, 6, 0)
    s = replace(scene(), objects=(a, b), kind="mixed")
    assert s.gold("count") == 2
    assert s.gold("shape") == s.gold("color") == UNKNOWN


def test_all_question_templates_and_unknown_question_refusal():
    for questions in QUESTIONS.values():
        for question in questions:
            assert len(encode_question(question)) == QUESTION_LENGTH + 1
    with pytest.raises(ValueError, match="outside"):
        encode_question("Что такое арбуз?")


def test_audit_and_label_hash_tampering(tiny_corpus):
    audit = audit_splits(tiny_corpus)
    assert audit["constant_controls_shared"] is True
    row = tiny_corpus["train"][0]
    with pytest.raises(ValueError, match="pixel hash"):
        replace(row, image_sha256="0" * 64).validate()
    with pytest.raises(ValueError, match="oracle"):
        replace(row, answer=(row.answer + 1) % len(ANSWERS)).validate()


def test_nontrivial_image_leakage_rejected(tiny_corpus):
    row = next(
        r for r in tiny_corpus["train"] if r.scene.kind == "normal" and r.scene.objects
    )
    bad = {k: list(v) for k, v in tiny_corpus.items()}
    bad["final"][0] = row
    with pytest.raises(ValueError, match="pixel leakage"):
        audit_splits(bad)


def test_no_metadata_or_gold_in_learned_inputs_and_gradient():
    torch.set_num_threads(2)
    model = ZeroClassModel(width=16, layers=1)
    pixels = torch.from_numpy(render(scene())[0]).permute(2, 0, 1)[None].float() / 255
    query = torch.tensor([encode_question(QUESTIONS["shape"][0])])
    outputs = model(pixels, query)
    assert outputs.shape == (1, VOCAB_SIZE)
    outputs.sum().backward()
    assert model.vision[0].weight.grad is not None
    assert model.core.blocks[0].attention.qkv.weight.grad is not None
    with pytest.raises(ValueError, match="RGB"):
        model(pixels[:, :, :-1], query)


def test_invalid_output_mass_never_renormalized():
    p = [0.0] * VOCAB_SIZE
    p[0], p[-1] = 0.3, 0.7
    assert select_answer(p, 0.5) == UNKNOWN
    assert select_answer(one_hot(0), None) == UNKNOWN
    for bad in ([0.0] * VOCAB_SIZE, [float("nan")] * VOCAB_SIZE):
        with pytest.raises(ValueError, match="probabilities"):
            select_answer(bad, 0.5)


def test_all_unknown_is_not_success(tiny_corpus):
    rows = tiny_corpus["train"]
    stats = metrics([r.answer for r in rows], [UNKNOWN] * len(rows))
    assert stats["false_assertions"] == 0
    assert stats["answerable_recall"] == 0
    assert stats["accepted"] == 0


def test_consensus_disagreement_and_uncertainty_mass():
    assert (
        select_answer(consensus_probabilities([one_hot(0), one_hot(1)]), 0.5) == UNKNOWN
    )
    a, b = one_hot(0), one_hot(0)
    a[0], a[UNKNOWN] = 0.9, 0.1
    b[0], b[UNKNOWN] = 0.7, 0.3
    merged = consensus_probabilities([a, b])
    assert merged[0] == 0.7
    assert merged[UNKNOWN] == pytest.approx(0.3)
    assert select_answer(merged, 0.8) == UNKNOWN
    with pytest.raises(ValueError, match="two"):
        consensus_probabilities([one_hot(0)])


def test_calibration_separate_task_and_ineligible_refusal(tiny_corpus):
    rows = tiny_corpus["calibration"]
    assert all(
        t is not None
        for t in calibrate(
            rows, [one_hot(r.answer) for r in rows], min_accepted=1
        ).values()
    )
    assert all(
        t is None
        for t in calibrate(
            rows, [one_hot(UNKNOWN) for r in rows], min_accepted=1
        ).values()
    )
    with pytest.raises(ValueError, match="inputs"):
        calibrate(rows, [], min_accepted=1)


def test_invalid_geometry_rejected():
    obj = replace(scene().objects[0], radius=float("nan"))
    with pytest.raises(ValueError, match="geometry"):
        render(replace(scene(), objects=(obj,)))
    with pytest.raises(ValueError, match="overlapping"):
        render(replace(scene(), objects=(scene().objects[0], scene().objects[0])))
