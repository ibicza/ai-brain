"""Contract tests: old IDs/weights, learned-input boundary and conservative policy."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

from ai_brain.training import primary_objects as obj
from ai_brain.training import primary_relations as old
from ai_brain.training import primary_zero as base


def distribution(label, confidence=1.0):
    values = [0.0] * obj.VOCAB_SIZE
    values[label] = confidence
    values[obj.UNKNOWN] += 1 - confidence
    return values


def test_old_word_answer_and_special_ids_preserved():
    for word, identifier in old.WORD_IDS.items():
        assert obj.WORD_IDS[word] == identifier
    for identifier, word in old.ANSWER_TEXT.items():
        assert obj.ANSWER_TEXT[identifier] == word
    for templates in base.QUESTIONS.values():
        for question in templates:
            assert obj.encode_question(question) == old.encode_question(question)
    for question in old.SUPPORTED:
        assert obj.encode_question(question) == old.encode_question(question)


def test_all_supported_new_words_are_teaching_vocabulary():
    for text in obj.OBJECT_QUESTIONS:
        tokens = obj.encode_question(text)
        assert len(tokens) == base.QUESTION_LENGTH + 1
        assert tokens[-1] == base.READ_ID
        assert obj.question_task(text) == "object"
    assert len(set(obj.OBJECT_IDS.values())) == 8
    assert min(obj.OBJECT_IDS.values()) == old.VOCAB_SIZE


def test_unsupported_question_is_not_guessed():
    with pytest.raises(ValueError):
        obj.encode_question("Что это за лекарство?")


def test_previous_weight_migration_preserves_all_old_tensors_and_raw_logits():
    torch.manual_seed(3)
    old_model = old.RelationsModel(width=32, layers=1).eval()
    new_model = obj.ObjectsModel(width=32, layers=1).eval()
    new_model.load_previous(old_model.state_dict())
    for name, value in old_model.state_dict().items():
        migrated = new_model.state_dict()[name]
        assert (
            torch.equal(migrated[: value.shape[0]], value)
            if migrated.shape != value.shape
            else torch.equal(migrated, value)
        )
    assert torch.count_nonzero(new_model.core.lm_head.weight[old.VOCAB_SIZE :]) == 0
    images = torch.rand(2, 3, 96, 96)
    questions = torch.tensor([old.encode_question(base.QUESTIONS["count"][0])] * 2)
    with torch.no_grad():
        old_logits = old_model(images, questions)
        new_logits = new_model(images, questions)
    # Enlarged GEMM output can change last-bit rounding; tensor migration above
    # remains byte-exact. Do not confuse full softmax with unchanged old logits.
    torch.testing.assert_close(
        old_logits, new_logits[:, : old.VOCAB_SIZE], rtol=1e-5, atol=1e-6
    )
    # Softmax normalization changes despite exact old raw logits; recalibrate.
    assert not torch.equal(
        old_logits.softmax(-1), new_logits.softmax(-1)[:, : old.VOCAB_SIZE]
    )


def test_inherited_forward_has_no_metadata_input():
    import inspect

    parameters = set(inspect.signature(obj.ObjectsModel.forward).parameters)
    assert parameters == {"self", "images", "questions", "return_intent"}
    model = obj.ObjectsModel(width=32, layers=1)
    with pytest.raises(TypeError):
        model(torch.zeros(1, 3, 96, 96), torch.zeros(1, 13, dtype=torch.long), gold=1)


def test_compatibility_normalizer_preserves_legacy_probabilities_without_teacher():
    torch.manual_seed(4)
    before = old.RelationsModel(width=32, layers=1).eval()
    after = obj.ObjectsModel(width=32, layers=1).eval()
    after.load_previous(before.state_dict())
    after.compatible_legacy_vocabulary = True
    images = torch.rand(2, 3, 96, 96)
    words = torch.tensor([old.encode_question(base.QUESTIONS["shape"][0])] * 2)
    with torch.no_grad():
        expected = before(images, words).softmax(-1)
        actual = after(images, words).softmax(-1)
    torch.testing.assert_close(
        actual[:, : old.VOCAB_SIZE], expected, rtol=1e-5, atol=1e-6
    )
    assert actual[:, old.VOCAB_SIZE :].count_nonzero() == 0
    new_words = torch.tensor([obj.encode_question(obj.OBJECT_QUESTIONS[0])] * 2)
    with torch.no_grad():
        assert (
            after(images, new_words).softmax(-1)[:, old.VOCAB_SIZE :].count_nonzero()
            > 0
        )


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_invalid_threshold_rejected(value):
    with pytest.raises(ValueError):
        obj.select_answer(distribution(obj.UNKNOWN), value)


@pytest.mark.parametrize(
    "values",
    [
        [0.0] * obj.VOCAB_SIZE,
        [float("nan")] * obj.VOCAB_SIZE,
        [1.0],
        [-1.0] * obj.VOCAB_SIZE,
    ],
)
def test_invalid_probabilities_rejected(values):
    with pytest.raises(ValueError):
        obj.select_answer(values, 0.99)


def test_unapproved_token_unknown_and_no_threshold_unknown():
    word_id = obj.WORD_IDS[obj.NEW_WORDS[0]]
    assert obj.select_answer(distribution(word_id), 0) == obj.UNKNOWN
    assert (
        obj.select_answer(distribution(obj.OBJECT_IDS["яблоко"]), None) == obj.UNKNOWN
    )


def test_consensus_disagreement_abstains():
    apple = obj.OBJECT_IDS["яблоко"]
    book = obj.OBJECT_IDS["книга"]
    assert (
        obj.select_answer(
            obj.consensus_probabilities([distribution(apple), distribution(book)]), 0.99
        )
        == obj.UNKNOWN
    )
    result = obj.consensus_probabilities(
        [distribution(apple, 0.999), distribution(apple, 0.991)]
    )
    assert result[apple] == pytest.approx(0.991)
    assert obj.select_answer(result, 0.995) == obj.UNKNOWN


def test_no_error_claim_for_unknown_on_everything():
    gold = [obj.OBJECT_IDS["яблоко"]] * 20 + [obj.UNKNOWN] * 10
    stats = obj.metrics(gold, [obj.UNKNOWN] * 30)
    assert stats["false_assertions"] == 0
    assert stats["answerable_recall"] == 0
    assert stats["accepted"] == 0


def test_calibration_rejects_one_confident_error():
    apple = obj.OBJECT_IDS["яблоко"]
    book = obj.OBJECT_IDS["книга"]
    gold = [apple] * 50 + [obj.UNKNOWN]
    thresholds = obj.calibrate(
        ["object"] * 51, gold, [distribution(apple)] * 50 + [distribution(book)]
    )
    assert thresholds["object"] is None


def test_calibration_requires_support_and_safety_floor():
    apple = obj.OBJECT_IDS["яблоко"]
    assert (
        obj.calibrate(["object"] * 50, [apple] * 50, [distribution(apple, 0.98)] * 50)[
            "object"
        ]
        is None
    )
    assert (
        obj.calibrate(["object"] * 49, [apple] * 49, [distribution(apple)] * 49)[
            "object"
        ]
        is None
    )
    assert (
        obj.calibrate(["object"] * 50, [apple] * 50, [distribution(apple)] * 50)[
            "object"
        ]
        == 0.9999
    )


def test_only_mirror_direction_tokens_change():
    for text in obj.OBJECT_QUESTIONS:
        words = torch.tensor([obj.encode_question(text)])
        assert torch.equal(words, old.mirror_questions(words))


def test_exact_and_mirrored_image_families_kept_together():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "object_prepare",
        Path(__file__).resolve().parents[1] / "scripts/m33_objects_prepare.py",
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        if exc.name == "PIL":
            pytest.skip(
                "Bundled preprocessing runtime supplies Pillow; remote trainer uses prepared NumPy"
            )
        raise
    image = np.full((96, 96, 3), 255, dtype=np.uint8)
    image[10:65, 10:25] = 0
    other = np.full_like(image, 255)
    other[20:80, 50:60] = 0
    groups = module.families([image, image.copy(), image[:, ::-1].copy(), other])
    assert groups[0] == groups[1] == groups[2]
    assert groups[0] != groups[3]
