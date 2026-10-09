import pytest
import torch

from ai_brain.training import primary_objects as obj
from ai_brain.training import primary_relations as old
from ai_brain.training import primary_zero as base
from ai_brain.training.primary_object_augmentation import background_view


def pair():
    torch.manual_seed(503)
    warm = obj.ObjectsModel(
        width=32, vision_extension_channels=32, object_unknown_adapter=True
    ).eval()
    warm.compatible_legacy_vocabulary = True
    checkpoint = {
        "width": 32,
        "layers": 2,
        "architecture": warm.vision_extension_config,
        "compatible_legacy_vocabulary": True,
        "model": warm.state_dict(),
    }
    target = obj.ObjectsModel(
        width=32,
        vision_extension_channels=32,
        object_unknown_adapter=True,
        object_readout_adapter=True,
    ).eval()
    target.load_object_warm_start(checkpoint)
    images = torch.rand(2, 3, 96, 96)
    questions = torch.tensor(
        [
            obj.encode_question(obj.OBJECT_QUESTIONS[0]),
            old.encode_question(base.QUESTIONS["count"][0]),
        ]
    )
    return warm, target, images, questions


def test_zero_append_identity_then_trainable_only_on_object_questions():
    warm, target, images, questions = pair()
    with torch.no_grad():
        before = warm(images, questions)
        assert torch.equal(target(images, questions), before)
    (-target(images, questions)[0].log_softmax(-1)[obj.OBJECT_IDS["яблоко"]]).backward()
    assert target.object_readout_adapter[-1].weight.grad.abs().sum() > 0
    with torch.no_grad():
        target.object_readout_adapter[-1].weight.add_(0.01)
        changed = target(images, questions)
    assert torch.equal(before[1], changed[1])
    assert not torch.equal(before[0], changed[0])
    for name, value in warm.state_dict().items():
        assert torch.equal(target.state_dict()[name], value)
    restored = obj.ObjectsModel.from_checkpoint(
        {
            "width": 32,
            "layers": 2,
            "architecture": target.vision_extension_config,
            "compatible_legacy_vocabulary": True,
            "model": target.state_dict(),
        }
    ).eval()
    with torch.no_grad():
        assert torch.equal(restored(images, questions), changed)


def test_nonzero_readout_migration_rejected():
    warm, target, _, _ = pair()
    with torch.no_grad():
        target.object_readout_adapter[-1].bias.fill_(1)
    with pytest.raises(ValueError, match="exact zero"):
        target.load_object_warm_start(
            {
                "width": 32,
                "layers": 2,
                "architecture": warm.vision_extension_config,
                "compatible_legacy_vocabulary": True,
                "model": warm.state_dict(),
            }
        )


def test_all_seven_legacy_tasks_bypass_trained_readout_and_unknown_adapters():
    warm, target, _, _ = pair()
    texts = [
        next(q for q in sorted(old.SUPPORTED) if old.question_task(q) == task)
        for task in old.TASKS
    ]
    questions = torch.tensor([old.encode_question(q) for q in texts])
    images = torch.rand(len(texts), 3, 96, 96)
    with torch.no_grad():
        before = warm(images, questions)
        for parameter in target.object_readout_adapter.parameters():
            parameter.normal_(0, 0.1)
        for parameter in target.object_unknown_adapter.parameters():
            parameter.normal_(0, 0.1)
        assert torch.equal(target(images, questions), before)


def test_checkpoint_cannot_silently_drop_readout_architecture():
    _, target, _, _ = pair()
    architecture = dict(target.vision_extension_config)
    architecture.pop("object_readout_adapter")
    with pytest.raises(RuntimeError):
        obj.ObjectsModel.from_checkpoint(
            {
                "width": 32,
                "layers": 2,
                "architecture": architecture,
                "compatible_legacy_vocabulary": True,
                "model": target.state_dict(),
            }
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"object_readout_adapter": True},
        {"object_readout_adapter": True, "vision_extension_channels": 32},
        {
            "object_readout_adapter": 1,
            "vision_extension_channels": 32,
            "object_unknown_adapter": True,
        },
    ],
)
def test_readout_configuration_is_strict(kwargs):
    with pytest.raises(ValueError):
        obj.ObjectsModel(**kwargs)


def test_canvas_augmentation_preserves_foreground_not_treated_as_new_evidence():
    torch.manual_seed(703)
    images = torch.zeros(2, 3, 96, 96)
    images[:, 0, 40:56, 40:56] = 1
    output = background_view(images)
    assert output.shape == images.shape and output.min() >= 0 and output.max() <= 1
    assert output[:, 0, 43:53, 43:53].min() > 0.99
    assert output[:, 1:, 43:53, 43:53].max() < 0.001
    assert output[:, :, :, 0].sum() > 0
    assert not torch.equal(output[0], output[1])
    with pytest.raises(ValueError):
        background_view(torch.zeros(2, 3, 95, 96))
