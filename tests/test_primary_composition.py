import numpy as np
import pytest
import torch

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_objects as old
from ai_brain.training import primary_zero as base


@pytest.fixture(scope="module")
def model():
    torch.set_num_threads(2)
    torch.manual_seed(42)
    return c.CompositionModel(old.ObjectsModel(width=32, layers=1)).eval()


def test_renderer_reproducible_and_no_metadata_input():
    scene = c.scenes("train", 1, 123)[0]
    assert c.render(scene).shape == (96, 96, 3)
    assert np.array_equal(c.render(scene), c.render(scene))
    assert c.render(scene).flags.writeable


def test_combinations_really_held_and_no_pixels_shared():
    data = {
        split: c.prepare(c.scenes(split, 12, 2000 + i * 100))
        for i, split in enumerate(
            ("train", "dev", "calibration", "final", "combinations", "transfer")
        )
    }
    assert c.audit(data)["unique_images"] == 72
    data["dev"] = data["train"]
    with pytest.raises(ValueError, match="leakage"):
        c.audit(data)


def test_hidden_parts_are_unknown_not_generic_knowledge():
    scene = c.Scene(
        "test",
        1,
        (
            c.Item("зелёный", "овал", "полосатый", True),
            c.Item("красный", "круг", "однотонный"),
        ),
    )
    assert all(scene.gold(task, 0) == c.UNKNOWN for task in c.VALUES)
    assert scene.gold("color", 1) == c.ANSWERS.index("красный")
    with pytest.raises(ValueError):
        scene.gold("legs", 0)


@pytest.mark.parametrize("task", c.VALUES)
@pytest.mark.parametrize("side", (0, 1))
@pytest.mark.parametrize("template", range(3))
def test_bilingual_queries(task, side, template):
    tokens = c.encode_question(c.question(task, side, template))
    assert len(tokens) == base.QUESTION_LENGTH + 1
    assert tokens[-1] == base.READ_ID


def test_unsupported_description_is_rejected():
    with pytest.raises(ValueError):
        c.encode_question("Жираф сладкий?")
    assert c.describe([c.UNKNOWN] * 6)["object_identity"] == "UNKNOWN"
    with pytest.raises(ValueError):
        c.describe([c.ANSWERS.index("овал")] * 6)


def test_shared_core_gradient_and_old_weights_exact(model):
    original = {k: v.clone() for k, v in model.inherited.state_dict().items()}
    assert sum(isinstance(m, type(model.inherited.core)) for m in model.modules()) == 1
    model.train()
    assert not model.inherited.training
    images = (
        torch.from_numpy(c.render(c.scenes("train", 1, 321)[0]))
        .permute(2, 0, 1)[None]
        .float()
        / 255
    )
    q = torch.tensor([c.encode_question(c.question("pattern", 0))])
    logits = model(images, q)
    torch.nn.functional.cross_entropy(
        logits, torch.tensor([c.ANSWERS.index("однотонный")])
    ).backward()
    assert model.pixel_residual[-1].weight.grad.abs().sum() > 0
    assert model.new_words.weight.grad.abs().sum() > 0
    assert all(p.grad is None for p in model.inherited.parameters())
    assert all(
        torch.equal(v, model.inherited.state_dict()[k]) for k, v in original.items()
    )
    assert not torch.isfinite(logits[0, c.ANSWERS.index("круг")])
    old_q = torch.tensor([old.encode_question(old.OBJECT_QUESTIONS[0])])
    assert torch.equal(
        model.legacy_forward(images, old_q), model.inherited(images, old_q)
    )


def test_invalid_model_inputs(model):
    q = torch.tensor([c.encode_question(c.question("shape", 0))])
    with pytest.raises(ValueError):
        model(torch.full((1, 3, 96, 96), float("nan")), q)
    with pytest.raises(ValueError):
        model(torch.zeros(1, 3, 96, 96), q + 9999)


def test_candidate_roundtrip(model):
    other = c.CompositionModel(old.ObjectsModel(width=32, layers=1))
    other.load_candidate(model.candidate_state())
    assert not any(k.startswith("inherited.") for k in model.candidate_state())
    with pytest.raises(ValueError):
        other.load_candidate({})
    with pytest.raises(ValueError):
        c.CompositionModel(
            old.ObjectsModel(width=32, layers=1), attribute_attention=False
        ).load_candidate(model.candidate_state())


def test_abstention_and_metrics_fail_closed():
    p = np.eye(len(c.ANSWERS))[[0, 0, c.UNKNOWN]]
    assert c.select(p, [None, 0.99, 0.99]) == [c.UNKNOWN, 0, c.UNKNOWN]
    metrics = c.statistics([0, 1, c.UNKNOWN], [c.UNKNOWN, 0, c.UNKNOWN])
    assert metrics["false_assertions"] == 1
    assert metrics["answerable_recall"] == 0
    with pytest.raises(ValueError):
        c.select(p, [-1, 0.99, 0.99])
