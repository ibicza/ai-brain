"""New trainable pixels must not alter legacy questions or checkpoint meaning."""

import inspect

import pytest
import torch

from ai_brain.training import primary_objects as obj
from ai_brain.training import primary_relations as old
from ai_brain.training import primary_zero as base


def model(channels=32, depth=0):
    torch.manual_seed(71)
    prior = old.RelationsModel(width=32)
    expanded = obj.ObjectsModel(
        width=32, vision_extension_channels=channels, vision_extension_depth=depth
    )
    expanded.load_previous(prior.state_dict())
    expanded.compatible_legacy_vocabulary = True
    return prior.eval(), expanded.eval()


def test_extension_initially_identity_and_legacy_stays_unchanged_when_trained():
    prior, expanded = model()
    images = torch.rand(3, 3, 96, 96)
    old_words = torch.tensor([old.encode_question(base.QUESTIONS["count"][0])] * 3)
    with torch.no_grad():
        before = expanded(images, old_words)[:, : old.VOCAB_SIZE]
        assert torch.allclose(before, prior(images, old_words), atol=1e-6, rtol=1e-6)
        expanded.vision_extension[-1].weight.fill_(0.1)
        assert torch.equal(expanded(images, old_words)[:, : old.VOCAB_SIZE], before)
        assert not torch.isfinite(
            expanded(images, old_words)[:, old.VOCAB_SIZE :]
        ).any()


def test_extension_changes_only_question_selected_rows_and_receives_gradients():
    _, expanded = model()
    images = torch.rand(2, 3, 96, 96)
    words = torch.tensor(
        [
            obj.encode_question(obj.OBJECT_QUESTIONS[0]),
            old.encode_question(base.QUESTIONS["count"][0]),
        ]
    )
    baseline = expanded.vision(images)
    assert torch.equal(expanded.visual_features(images, words), baseline)
    expanded.train()
    out = expanded(images, words)
    loss = -out[0].log_softmax(-1)[obj.OBJECT_IDS["яблоко"]]
    loss.backward()
    assert expanded.vision_extension[-1].weight.grad.abs().sum() > 0
    with torch.no_grad():
        expanded.vision_extension[-1].weight.add_(0.01)
        features = expanded.visual_features(images, words)
        assert not torch.equal(features[0], baseline[0])
        assert torch.equal(features[1], baseline[1])


@pytest.mark.parametrize("channels,depth", [(0, 0), (32, 0), (64, 2)])
def test_checkpoint_roundtrip_keeps_architecture_and_normalization(channels, depth):
    _, expanded = model(channels, depth)
    checkpoint = {
        "width": 32,
        "layers": 2,
        "model": expanded.state_dict(),
        "architecture": expanded.vision_extension_config,
        "compatible_legacy_vocabulary": True,
    }
    restored = obj.ObjectsModel.from_checkpoint(checkpoint).eval()
    images = torch.rand(1, 3, 96, 96)
    words = torch.tensor([obj.encode_question(obj.OBJECT_QUESTIONS[-1])])
    with torch.no_grad():
        assert torch.equal(expanded(images, words), restored(images, words))
    assert restored.compatible_legacy_vocabulary is True


def test_checkpoint_cannot_drop_extension_or_normalizer_metadata():
    _, expanded = model()
    with pytest.raises(ValueError):
        obj.ObjectsModel.from_checkpoint({"width": 32, "model": expanded.state_dict()})
    with pytest.raises(RuntimeError):
        obj.ObjectsModel.from_checkpoint(
            {
                "width": 32,
                "model": expanded.state_dict(),
                "compatible_legacy_vocabulary": True,
            }
        )


def test_learned_forward_still_has_no_labels_sources_or_task_input():
    assert list(inspect.signature(obj.ObjectsModel.forward).parameters) == [
        "self",
        "images",
        "questions",
        "return_intent",
    ]
    _, small = model(32, 0)
    _, large = model(64, 2)
    assert sum(p.numel() for p in large.parameters()) > sum(
        p.numel() for p in small.parameters()
    )


def test_object_unknown_adapter_preserves_legacy_and_has_no_impossible_answers():
    torch.manual_seed(91)
    prior = old.RelationsModel(width=32).eval()
    expanded = obj.ObjectsModel(
        width=32, vision_extension_channels=32, object_unknown_adapter=True
    ).eval()
    expanded.load_previous(prior.state_dict())
    expanded.compatible_legacy_vocabulary = True
    images = torch.rand(2, 3, 96, 96)
    words = torch.tensor(
        [
            obj.encode_question(obj.OBJECT_QUESTIONS[0]),
            old.encode_question(base.QUESTIONS["count"][0]),
        ]
    )
    before = expanded(images, words)
    with torch.no_grad():
        assert torch.allclose(
            before[1, : old.VOCAB_SIZE],
            prior(images[1:], words[1:])[0],
            atol=1e-6,
            rtol=1e-6,
        )
    allowed = set(obj.OBJECT_IDS.values()) | {obj.UNKNOWN}
    assert {i for i, v in enumerate(before[0]) if torch.isfinite(v)} == allowed
    (-before[0].log_softmax(-1)[obj.UNKNOWN]).backward()
    assert expanded.object_unknown_adapter.weight.grad.abs().sum() > 0
    with torch.no_grad():
        expanded.object_unknown_adapter.weight.fill_(1)
        expanded.object_unknown_adapter.bias.fill_(3)
        after = expanded(images, words)
    assert torch.equal(before[1], after[1])
    assert not torch.equal(before[0], after[0])
    checkpoint = {
        "width": 32,
        "layers": 2,
        "architecture": expanded.vision_extension_config,
        "compatible_legacy_vocabulary": True,
        "model": expanded.state_dict(),
    }
    restored = obj.ObjectsModel.from_checkpoint(checkpoint).eval()
    with torch.no_grad():
        assert torch.equal(restored(images, words), after)


def test_global_context_appends_identity_then_learns_only_object_rows():
    _, warm = model(32, 0)
    expanded = obj.ObjectsModel(
        width=32, vision_extension_channels=32, vision_global_context=True
    )
    checkpoint = {
        "width": 32,
        "layers": 2,
        "architecture": warm.vision_extension_config,
        "compatible_legacy_vocabulary": True,
        "model": warm.state_dict(),
    }
    expanded.load_object_warm_start(checkpoint)
    expanded.compatible_legacy_vocabulary = True
    warm.eval()
    expanded.eval()
    images = torch.rand(2, 3, 96, 96)
    questions = torch.tensor(
        [
            obj.encode_question(obj.OBJECT_QUESTIONS[0]),
            old.encode_question(base.QUESTIONS["count"][0]),
        ]
    )
    with torch.no_grad():
        baseline = warm(images, questions)
        assert torch.equal(expanded(images, questions), baseline)
    expanded.train()
    (
        -expanded(images, questions)[0].log_softmax(-1)[obj.OBJECT_IDS["яблоко"]]
    ).backward()
    assert expanded.vision_global_context[-1].weight.grad.abs().sum() > 0
    with torch.no_grad():
        expanded.vision_global_context[-1].weight.add_(0.1)
    expanded.eval()
    with torch.no_grad():
        changed = expanded(images, questions)
        assert not torch.equal(changed[0], baseline[0])
        assert torch.equal(changed[1], baseline[1])
    restored = obj.ObjectsModel.from_checkpoint(
        checkpoint
        | {
            "architecture": expanded.vision_extension_config,
            "model": expanded.state_dict(),
        }
    ).eval()
    with torch.no_grad():
        assert torch.equal(restored(images, questions), changed)


def test_context_migration_cannot_drop_branch_change_channels_or_use_nonzero_residual():
    _, warm = model(32, 0)
    checkpoint = {
        "width": 32,
        "layers": 2,
        "architecture": warm.vision_extension_config,
        "compatible_legacy_vocabulary": True,
        "model": warm.state_dict(),
    }
    target = obj.ObjectsModel(
        width=32, vision_extension_channels=64, vision_global_context=True
    )
    with pytest.raises(ValueError, match="architecture"):
        target.load_object_warm_start(checkpoint)
    target = obj.ObjectsModel(
        width=32, vision_extension_channels=32, vision_global_context=True
    )
    with torch.no_grad():
        target.vision_global_context[-1].bias.fill_(1)
    with pytest.raises(ValueError, match="exact zero"):
        target.load_object_warm_start(checkpoint)
    with pytest.raises(ValueError):
        obj.ObjectsModel(width=32, vision_global_context=True)
