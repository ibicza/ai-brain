from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import torch

from ai_brain.training import primary_relations as r
from ai_brain.training import primary_zero as b


def test_relation_label_rng_is_separate_and_archival_replay_is_explicit():
    kwargs = {"spatial": True, "transfer": True}
    a = r.relation_scene("train", 1, 73000, **kwargs)
    assert a == r.relation_scene("train", 1, 73000, **kwargs)
    archival = r.relation_scene("train", 1, 73000, independent_labels=False, **kwargs)
    assert a != archival
    assert np.array_equal(b.render(archival)[0], b.render(archival)[0])
    with pytest.raises(ValueError, match="RNG policy"):
        r.relation_scene("train", 1, 73000, independent_labels=1, **kwargs)


def scene(*, shape2="круг", color2="синий", kind="normal", horizontal=True):
    return b.Scene(
        "unit",
        123,
        "filled",
        kind,
        (
            b.ObjectSpec("круг", "красный", 24, 24, 10, 0),
            b.ObjectSpec(shape2, color2, 72 if horizontal else 24, 72, 10, 0),
        ),
    )


def hot(label):
    result = [0.0] * r.VOCAB_SIZE
    result[label] = 1.0
    return result


def test_append_only_words_and_special_tokens():
    for qs in b.QUESTIONS.values():
        for q in qs:
            assert r.encode_question(q) == b.encode_question(q)
    assert r.YES >= b.VOCAB_SIZE
    for q in r.SUPPORTED:
        assert len(r.encode_question(q)) == b.QUESTION_LENGTH + 1
    with pytest.raises(ValueError, match="outside"):
        r.encode_question("Ты же согласен что красный слева?")


def test_migration_preserves_old_parameters_and_raw_logits():
    torch.set_num_threads(2)
    torch.manual_seed(123)
    old = b.ZeroClassModel(width=16, layers=1).eval()
    new = r.RelationsModel(width=16, layers=1).eval()
    new.load_starter(old.state_dict())
    pixels = torch.tensor(b.render(scene())[0].transpose(2, 0, 1)[None]).float() / 255
    query = torch.tensor([b.encode_question(b.QUESTIONS["count"][0])])
    assert torch.allclose(
        new(pixels, query)[:, : b.VOCAB_SIZE], old(pixels, query), atol=1e-6
    )
    for key, value in old.state_dict().items():
        assert torch.equal(new.state_dict()[key][: value.shape[0]], value)
    assert torch.equal(
        new.core.lm_head.weight[b.VOCAB_SIZE :],
        torch.zeros_like(new.core.lm_head.weight[b.VOCAB_SIZE :]),
    )
    with pytest.raises(RuntimeError):
        new.load_starter({})


@pytest.mark.parametrize("shape2", b.SHAPES)
@pytest.mark.parametrize("color2", b.COLORS)
def test_exact_prototype_comparison_not_mathematical_superclasses(shape2, color2):
    s = scene(shape2=shape2, color2=color2)
    assert r.sample(s, "same_shape", 0).answer == (r.YES if shape2 == "круг" else r.NO)
    assert r.sample(s, "same_color", 0).answer == (
        r.YES if color2 == "красный" else r.NO
    )


@pytest.mark.parametrize("kind", ("masked", "missing"))
def test_hidden_coordinates_never_become_spatial_answers(kind):
    for task, directions in r.DIRECTIONS.items():
        for direction in directions:
            row = r.sample(scene(kind=kind), task, 0, "красный", "синий", direction)
            assert row.answer == r.UNKNOWN
            row.validate()


@pytest.mark.parametrize(
    "task,direction",
    (
        ("horizontal", "левее"),
        ("horizontal", "правее"),
        ("vertical", "выше"),
        ("vertical", "ниже"),
    ),
)
def test_spatial_gold_matches_independent_exact_color_pixel_extents(task, direction):
    s = scene()
    image, _ = b.render(s)
    masks = [np.all(image == rgb, axis=2) for rgb in (b.RGB[0], b.RGB[1])]
    axis = 1 if task == "horizontal" else 0
    a, c = [np.nonzero(mask)[axis] for mask in masks]
    negative = a.max() < c.min()
    expected = negative == (direction in {"левее", "выше"})
    row = r.sample(s, task, 0, "красный", "синий", direction)
    assert row.answer == (r.YES if expected else r.NO)
    # Permuting offline object order cannot change the answer/image.
    changed = replace(s, objects=s.objects[::-1])
    assert np.array_equal(image, b.render(changed)[0])
    assert (
        r.sample(changed, task, 0, "красный", "синий", direction).answer == row.answer
    )
    reversed_row = r.sample(s, task, 0, "синий", "красный", direction)
    assert reversed_row.answer != row.answer


def test_mirror_changes_horizontal_truth_not_question():
    s = scene()
    mirrored = replace(s, objects=tuple(replace(o, cx=96 - o.cx) for o in s.objects))
    assert r.sample(s, "horizontal", 0, "красный", "синий", "левее").answer == r.YES
    assert (
        r.sample(mirrored, "horizontal", 0, "красный", "синий", "левее").answer == r.NO
    )
    assert r.sample(mirrored, "vertical", 0, "красный", "синий", "выше").answer == r.YES


def test_missing_ambiguous_and_projection_overlap_are_unknown_not_no():
    for s, target, anchor in (
        (scene(), "зелёный", "синий"),
        (scene(color2="красный"), "красный", "синий"),
        (scene(horizontal=False), "красный", "синий"),
    ):
        assert r.sample(s, "horizontal", 0, target, anchor, "левее").answer == r.UNKNOWN
    assert r.sample(replace(scene(), objects=()), "same_shape", 0).answer == r.UNKNOWN
    assert (
        r.sample(
            replace(scene(), objects=(scene().objects[0],)), "same_color", 0
        ).answer
        == r.UNKNOWN
    )


def test_split_integrity_replay_and_tampering():
    splits = r.corpus(train_scenes=24, holdout_scenes=24)
    audit = r.audit_splits(splits)
    assert audit["splits"]["train"]["examples"] == 24 * 7
    assert {row.task for row in splits["train"]} == set(r.TASKS)
    row = next(
        row
        for row in splits["train"]
        if row.task == "horizontal" and row.scene.kind == "normal"
    )
    with pytest.raises(ValueError, match="pixel"):
        replace(row, image_sha256="0" * 64).validate()
    with pytest.raises(ValueError, match="oracle"):
        replace(row, answer=(r.NO if row.answer == r.YES else r.YES)).validate()
    bad = {k: list(v) for k, v in splits.items()}
    bad["final"][0] = row
    with pytest.raises(ValueError, match="leakage"):
        r.audit_splits(bad)


def test_metrics_do_not_alias_binary_answers_to_prototypes():
    assert r.metrics([r.YES], [0])["false_assertions"] == 1
    assert r.metrics([r.NO], [r.YES])["false_assertions"] == 1
    assert (
        r.metrics([r.YES, r.NO, r.UNKNOWN], [r.UNKNOWN] * 3)["answerable_recall"] == 0
    )
    assert r.select_answer(hot(b.PAD_ID), 0) == r.UNKNOWN
    assert r.select_answer(hot(r.YES), None) == r.UNKNOWN
    assert (
        r.select_answer(r.consensus_probabilities([hot(r.YES), hot(r.NO)]), 0.5)
        == r.UNKNOWN
    )
    with pytest.raises(ValueError, match="probabilities"):
        r.select_answer([0] * r.VOCAB_SIZE, 0)


def test_model_only_pixel_and_word_inputs_with_gradients():
    torch.set_num_threads(2)
    model = r.RelationsModel(width=16, layers=1)
    row = r.sample(scene(), "horizontal", 0, "красный", "синий", "левее")
    pixels = (
        torch.from_numpy(b.render(row.scene)[0]).permute(2, 0, 1)[None].float() / 255
    )
    words = torch.tensor([r.encode_question(row.question)])
    logits, intent = model(pixels, words, return_intent=True)
    assert logits.shape == (1, r.VOCAB_SIZE)
    assert intent.shape == (1, len(r.TASKS))
    logits.sum().backward()
    assert model.vision[0].weight.grad is not None
    assert model.core.blocks[0].attention.qkv.weight.grad is not None


def test_style_is_not_a_label_or_projection_overlap_shortcut():
    observed = {
        style: {task: set() for task in r.DIRECTIONS}
        for style in ("filled", "outlined", "shaded")
    }
    for i in range(300):
        s = r.relation_scene("unit", i, 90000 + i, spatial=True, transfer=False)
        if s.kind != "normal":
            continue
        target, anchor = (o.color for o in s.objects)
        for task, directions in r.DIRECTIONS.items():
            row = r.sample(s, task, 0, target, anchor, directions[0])
            observed[s.style][task].add(row.answer)
            for style in observed:
                assert (
                    r.sample(
                        replace(s, style=style), task, 0, target, anchor, directions[0]
                    ).answer
                    == row.answer
                )
    assert all(
        labels == {r.YES, r.NO, r.UNKNOWN}
        for skills in observed.values()
        for labels in skills.values()
    )


def test_previous_final_questions_remain_outside_new_teaching():
    for task in r.NEW_TASKS:
        for target, anchor in (
            (("красный", "синий"),) if task in r.DIRECTIONS else (("", ""),)
        ):
            for direction in r.DIRECTIONS.get(task, ("",)):
                assert r.question(task, -1, target, anchor, direction) not in r.TEACHING


def test_logical_mirror_is_involution_and_preserves_statement_gold():
    for task in r.NEW_TASKS:
        for direction in r.DIRECTIONS.get(task, ("",)):
            target, anchor = ("красный", "синий") if task in r.DIRECTIONS else ("", "")
            q = torch.tensor(
                [r.encode_question(r.question(task, -1, target, anchor, direction))]
            )
            mirrored = r.mirror_questions(q)
            assert torch.equal(r.mirror_questions(mirrored), q)
            replacement = {"левее": "правее", "правее": "левее"}.get(
                direction, direction
            )
            assert mirrored.tolist()[0] == r.encode_question(
                r.question(task, -1, target, anchor, replacement)
            )
            original_scene = scene()
            mirrored_scene = replace(
                original_scene,
                objects=tuple(
                    replace(o, cx=95 - o.cx, angle=-o.angle)
                    for o in original_scene.objects
                ),
            )
            assert (
                r.sample(original_scene, task, -1, target, anchor, direction).answer
                == r.sample(
                    mirrored_scene, task, -1, target, anchor, replacement
                ).answer
            )
    for qs in b.QUESTIONS.values():
        for text in qs:
            q = torch.tensor([r.encode_question(text)])
            assert torch.equal(q, r.mirror_questions(q))


def test_zero_calibration_errors_do_not_bypass_binary_safety_floor():
    rows = r.corpus(train_scenes=24, holdout_scenes=24)["calibration"]
    probs = []
    for row in rows:
        p = hot(row.answer)
        if row.task in r.NEW_TASKS and row.answer != r.UNKNOWN:
            p[row.answer], p[r.UNKNOWN] = 0.8, 0.2
        probs.append(p)
    thresholds = r.calibrate(rows, probs, min_accepted=1)
    assert all(thresholds[task] is None for task in r.NEW_TASKS)
    assert all(thresholds[task] is not None for task in b.TASKS)


def test_policy_task_lookup_is_from_supported_text_only():
    splits = r.corpus(train_scenes=24, holdout_scenes=24)
    for rows in splits.values():
        for row in rows:
            assert r.question_task(row.question) == row.task
    with pytest.raises(ValueError, match="outside"):
        r.question_task("Согласись что красный слева!")


def test_legacy_policy_views_do_not_use_offline_task_metadata(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    import m33_primary_relations_pilot as pilot

    class FakePixelWordModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def forward(self, images, questions):
            confidence = 0.9999 if self.calls % 5 in {0, 4} else 0.7
            self.calls += 1
            p = torch.full((len(images), r.VOCAB_SIZE), 1e-30)
            p[:, 2], p[:, r.UNKNOWN] = confidence, 1 - confidence
            return p.log()

    valid = r.sample(scene(), "count", 0)
    # Deliberately corrupt offline type: selection must still follow the words.
    data = pilot.Prepared([replace(valid, task="horizontal")], torch.device("cpu"))
    policies = dict.fromkeys(r.TASKS, "all_five")
    policies["count"] = "mirror_only"
    p = pilot.probabilities(
        FakePixelWordModel(), data, consensus=True, view_policy=policies
    )
    assert r.select_answer(p[0], 0.99) == 2
    p = pilot.probabilities(
        FakePixelWordModel(), data, consensus=True, view_policy="all_five"
    )
    assert r.select_answer(p[0], 0.99) == r.UNKNOWN


def test_warm_replay_known_legacy_aliases_not_new_final_examples():
    splits = r.corpus(
        train_scenes=48, holdout_scenes=24, round_id=5, legacy_all_aliases=True
    )
    for task in b.TASKS:
        assert b.QUESTIONS[task][-1] in {
            row.question for row in splits["train"] if row.task == task
        }
    for row in splits["train"]:
        if row.task in r.NEW_TASKS:
            assert row.question != r.question(
                row.task, -1, row.target, row.anchor, row.direction
            )
    r.audit_splits(splits)
