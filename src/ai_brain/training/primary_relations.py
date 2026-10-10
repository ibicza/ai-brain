"""Incremental procedural comparison/spatial course; never a textbook admission.

Old token IDs remain stable. Only RGB and question tokens enter the inherited
shared model; all object attributes/coordinates below belong to offline gold.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import asdict, dataclass, replace

import numpy as np
import torch
from torch import nn

from ai_brain.training import primary_zero as base

NEW_TASKS = ("same_shape", "same_color", "horizontal", "vertical")
TASKS = (*base.TASKS, *NEW_TASKS)
YES, NO = base.VOCAB_SIZE, base.VOCAB_SIZE + 1
UNKNOWN = base.UNKNOWN
ANSWER_TEXT = dict(enumerate(base.ANSWERS)) | {YES: "YES", NO: "NO"}
GENITIVE = dict(
    zip(
        base.COLORS,
        ("красного", "синего", "зелёного", "жёлтого", "оранжевого", "фиолетового"),
        strict=True,
    )
)
QUESTIONS = {
    "same_shape": (
        "У двух предметов одинаковые названия формы?",
        "Одинаковые ли названия формы у двух предметов?",
        "Названия формы двух предметов одинаковые?",
        "Названия формы у предметов одинаковые?",
        "У предметов одинаковые названия формы?",
    ),
    "same_color": (
        "У двух предметов одинаковый цвет?",
        "Одинаковый ли цвет у двух предметов?",
        "Цвет двух предметов одинаковый?",
        "Цвет у предметов одинаковый?",
        "У предметов одинаковый цвет?",
    ),
    "horizontal": (
        "{target} предмет {direction} {anchor}?",
        "На картинке {target} предмет {direction} {anchor}?",
        "{target} предмет на картинке {direction} {anchor}?",
        "Предмет {target} {direction} {anchor} на картинке?",
        "На картинке предмет {target} {direction} {anchor}?",
    ),
    "vertical": (
        "{target} предмет {direction} {anchor}?",
        "На картинке {target} предмет {direction} {anchor}?",
        "{target} предмет на картинке {direction} {anchor}?",
        "Предмет {target} {direction} {anchor} на картинке?",
        "На картинке предмет {target} {direction} {anchor}?",
    ),
}
DIRECTIONS = {"horizontal": ("левее", "правее"), "vertical": ("выше", "ниже")}


def question(
    task: str, template: int, target: str = "", anchor: str = "", direction: str = ""
) -> str:
    if task in base.TASKS:
        return base.QUESTIONS[task][template]
    if task in DIRECTIONS:
        if (
            target not in base.COLORS
            or anchor not in GENITIVE
            or target == anchor
            or direction not in DIRECTIONS[task]
        ):
            raise ValueError("invalid spatial reference/question")
        return QUESTIONS[task][template].format(
            target=target, anchor=GENITIVE[anchor], direction=direction
        )
    if task not in QUESTIONS:
        raise ValueError("unsupported task")
    return QUESTIONS[task][template]


SUPPORTED = {q for qs in base.QUESTIONS.values() for q in qs}
QUESTION_TASK = {q: task for task, qs in base.QUESTIONS.items() for q in qs}
TEACHING = {q for qs in base.QUESTIONS.values() for q in qs[:-1]}
for _task in NEW_TASKS:
    for _i in range(len(QUESTIONS[_task])):
        for _target in base.COLORS if _task in DIRECTIONS else ("",):
            for _anchor in base.COLORS if _task in DIRECTIONS else ("",):
                if _target == _anchor and _task in DIRECTIONS:
                    continue
                for _direction in DIRECTIONS.get(_task, ("",)):
                    _q = question(_task, _i, _target, _anchor, _direction)
                    SUPPORTED.add(_q)
                    if _q in QUESTION_TASK and QUESTION_TASK[_q] != _task:
                        raise ValueError("ambiguous supported question")
                    QUESTION_TASK[_q] = _task
                    if _i < len(QUESTIONS[_task]) - 1:
                        TEACHING.add(_q)
WORD_IDS = {w: base.WORD_OFFSET + i for i, w in enumerate(base.WORDS)}
NEW_WORDS = sorted(
    {w for q in TEACHING for w in re.findall(r"[а-яё]+|[.?]", q.lower())}
    - WORD_IDS.keys()
)
WORD_IDS.update({w: base.VOCAB_SIZE + 2 + i for i, w in enumerate(NEW_WORDS)})
VOCAB_SIZE = base.VOCAB_SIZE + 2 + len(NEW_WORDS)


def question_task(text: str) -> str:
    """Supported-question policy lookup outside learned forward; no gold input."""
    if text not in QUESTION_TASK:
        raise ValueError("question outside admitted relations scope")
    return QUESTION_TASK[text]


def mirror_questions(questions: torch.Tensor) -> torch.Tensor:
    """Logical involution from words alone; no task IDs/metadata/gold input."""
    left, right = WORD_IDS["левее"], WORD_IDS["правее"]
    return torch.where(
        questions == left, right, torch.where(questions == right, left, questions)
    )


def encode_question(text: str) -> list[int]:
    if text not in SUPPORTED:
        raise ValueError("question outside admitted relations scope")
    words = re.findall(r"[а-яё]+|[.?]", text.lower())
    if len(words) > base.QUESTION_LENGTH:
        raise ValueError("question would be truncated")
    return (
        [WORD_IDS[w] for w in words]
        + [base.PAD_ID] * (base.QUESTION_LENGTH - len(words))
        + [base.READ_ID]
    )


@dataclass(frozen=True)
class Sample:
    scene: base.Scene
    image_sha256: str
    task: str
    question: str
    answer: int
    target: str = ""
    anchor: str = ""
    direction: str = ""

    def gold(self) -> int:
        self.scene.validate()
        if self.task in base.TASKS:
            return self.scene.gold(self.task)
        if self.task not in NEW_TASKS:
            raise ValueError("unsupported task")
        if self.scene.kind in {"missing", "masked"}:
            return UNKNOWN
        if self.task.startswith("same_"):
            if len(self.scene.objects) != 2:
                return UNKNOWN
            attr = self.task.removeprefix("same_")
            return (
                YES if len({getattr(o, attr) for o in self.scene.objects}) == 1 else NO
            )
        matches = [
            [o for o in self.scene.objects if o.color == color]
            for color in (self.target, self.anchor)
        ]
        if any(len(items) != 1 for items in matches):
            return UNKNOWN  # absent or ambiguous reference is not a negative fact
        _, evidence = base.render(self.scene)
        boxes = [
            next(e["bbox_xyxy"] for e in evidence if e["color"] == color)
            for color in (self.target, self.anchor)
        ]
        a, b = boxes
        axis = 0 if self.task == "horizontal" else 1
        if a[axis + 2] <= b[axis]:
            negative_direction = True
        elif b[axis + 2] <= a[axis]:
            negative_direction = False
        else:
            return UNKNOWN  # axis projections overlap: conservative scope
        asked_negative = self.direction in {"левее", "выше"}
        return YES if negative_direction == asked_negative else NO

    def validate(self) -> None:
        encode_question(self.question)
        templates = (
            base.QUESTIONS[self.task]
            if self.task in base.TASKS
            else QUESTIONS[self.task]
        )
        if self.question not in {
            question(self.task, i, self.target, self.anchor, self.direction)
            for i in range(len(templates))
        }:
            raise ValueError("task/question/reference mismatch")
        image, _ = base.render(self.scene)
        if self.image_sha256 != hashlib.sha256(image.tobytes()).hexdigest():
            raise ValueError("pixel hash mismatch")
        if self.answer != self.gold():
            raise ValueError("oracle answer mismatch")


def sample(
    scene: base.Scene,
    task: str,
    template: int,
    target: str = "",
    anchor: str = "",
    direction: str = "",
) -> Sample:
    image, _ = base.render(scene)
    row = Sample(
        scene,
        hashlib.sha256(image.tobytes()).hexdigest(),
        task,
        question(task, template, target, anchor, direction),
        UNKNOWN,
        target,
        anchor,
        direction,
    )
    return replace(row, answer=row.gold())


def relation_scene(
    split: str,
    index: int,
    seed: int,
    *,
    spatial: bool,
    transfer: bool,
    independent_labels: bool = True,
) -> base.Scene:
    if type(independent_labels) is not bool:
        raise ValueError("Expected explicit label RNG policy")
    # Use a label/geometry stream distinct from base.render's background noise.
    rng = np.random.default_rng(
        np.random.SeedSequence([seed, 0x4D33524C]) if independent_labels else seed
    )
    kind = ("normal",) * 6 + ("masked", "missing")
    colors = rng.choice(base.COLORS, 2, replace=False)
    shapes = rng.choice(base.SHAPES, 2, replace=False)
    if not spatial:
        if rng.random() < 0.5:
            colors[1] = colors[0]
        if rng.random() < 0.5:
            shapes[1] = shapes[0]
    positions = [
        (24 + rng.uniform(-6, 6), 24 + rng.uniform(-6, 6)),
        (72 + rng.uniform(-6, 6), 72 + rng.uniform(-6, 6)),
    ]
    orientation = int(rng.integers(3))
    if orientation == 0:
        positions[1] = (positions[1][0], positions[0][1])
    elif orientation == 1:
        positions[1] = (positions[0][0], positions[1][1])
    if rng.random() < 0.5:
        positions = [(96 - x, y) for x, y in positions]
    if rng.random() < 0.5:
        positions = [(x, 96 - y) for x, y in positions]
    objects = tuple(
        base.ObjectSpec(
            str(shapes[j]),
            str(colors[j]),
            float(x),
            float(y),
            float(rng.uniform(8, 12)),
            float(rng.uniform(-0.2, 0.2)),
        )
        for j, (x, y) in enumerate(positions)
    )
    return base.Scene(
        f"{split}/{'spatial' if spatial else 'comparison'}/{index}",
        seed,
        "textured" if transfer else str(rng.choice(("filled", "outlined", "shaded"))),
        str(rng.choice(kind)),
        objects,
    )


def corpus(
    *,
    train_scenes: int = 6000,
    holdout_scenes: int = 720,
    round_id: int = 1,
    legacy_all_aliases: bool = False,
) -> dict[str, list[Sample]]:
    if min(train_scenes, holdout_scenes) < 24 or round_id < 1:
        raise ValueError("invalid curriculum sizes/round")
    splits = {}
    # Fresh first-block replay, never previous final examples/labels.
    replay = base.corpus(
        train_scenes=train_scenes,
        holdout_scenes=holdout_scenes,
        round_id=100 + round_id,
    )
    for offset, split in enumerate(
        ("train", "dev", "calibration", "final", "transfer")
    ):
        rows = []
        query_rng = np.random.default_rng(
            300_000_000 + round_id * 1_000_000 + offset * 100_000
        )
        for old in replay[split]:
            text = (
                old.question
                if split in {"final", "transfer"}
                else str(
                    query_rng.choice(
                        base.QUESTIONS[old.task]
                        if legacy_all_aliases
                        else base.QUESTIONS[old.task][:-1]
                    )
                )
            )
            rows.append(Sample(old.scene, old.image_sha256, old.task, text, old.answer))
        for i in range(train_scenes if split == "train" else holdout_scenes):
            for spatial in (False, True):
                scene = relation_scene(
                    split,
                    i,
                    200_000_000
                    + round_id * 1_000_000
                    + offset * 100_000
                    + i * 2
                    + spatial,
                    spatial=spatial,
                    transfer=split == "transfer",
                )
                if not spatial:
                    for task in NEW_TASKS[:2]:
                        template = (
                            -1
                            if split in {"final", "transfer"}
                            else int(query_rng.integers(len(QUESTIONS[task]) - 1))
                        )
                        rows.append(sample(scene, task, template))
                else:
                    target, anchor = (o.color for o in scene.objects)
                    reference_control = int(query_rng.integers(12))
                    if reference_control == 2:
                        # Explicit unseen reference in a visible image.
                        target = next(
                            c for c in base.COLORS if c not in {target, anchor}
                        )
                    elif reference_control == 5:
                        # Two candidates for target, and absent anchor.
                        scene = replace(
                            scene,
                            objects=(
                                scene.objects[0],
                                replace(scene.objects[1], color=target),
                            ),
                        )
                    for task in NEW_TASKS[2:]:
                        template = (
                            -1
                            if split in {"final", "transfer"}
                            else int(query_rng.integers(len(QUESTIONS[task]) - 1))
                        )
                        rows.append(
                            sample(
                                scene,
                                task,
                                template,
                                target,
                                anchor,
                                str(query_rng.choice(DIRECTIONS[task])),
                            )
                        )
        splits[split] = rows
    return splits


def audit_splits(splits: dict[str, list[Sample]]) -> dict:
    if set(splits) != {"train", "dev", "calibration", "final", "transfer"}:
        raise ValueError("require five separate splits")
    owners, result = {}, {}
    for split, rows in splits.items():
        if not rows:
            raise ValueError("empty split")
        for row in rows:
            row.validate()
            if (
                row.scene.kind not in {"masked", "missing"}
                and row.scene.objects
                and owners.setdefault(row.image_sha256, split) != split
            ):
                raise ValueError("nontrivial pixel leakage across splits")
        result[split] = {
            "examples": len(rows),
            "scenes": len({r.scene.scene_id for r in rows}),
            "labels": dict(Counter(ANSWER_TEXT[r.answer] for r in rows)),
        }
    return {
        "splits": result,
        "constant_controls_shared": True,
        "semantic_duplicate_detection": "NOT_IMPLEMENTED; one procedural family, no textbook transfer",
    }


class RelationsModel(base.ZeroClassModel):
    """Append-only vocabulary; same pixel/word forward, no task-ID input."""

    def __init__(self, *, width: int = 96, layers: int = 2) -> None:
        super().__init__(width=width, layers=layers)
        self.core.config = replace(self.core.config, vocab_size=VOCAB_SIZE)
        self.core.token_embedding = nn.Embedding(VOCAB_SIZE, width)
        self.core.lm_head = nn.Linear(width, VOCAB_SIZE, bias=False)
        self.question_intent = nn.Linear(width, len(TASKS))

    def load_starter(self, state: dict[str, torch.Tensor]) -> None:
        # Validate every old tensor using the original model before migration.
        original = base.ZeroClassModel(
            width=self.core.config.d_model, layers=self.core.config.num_layers
        )
        original.load_state_dict(state, strict=True)
        target = self.state_dict()
        for name, value in state.items():
            if name in {
                "core.token_embedding.weight",
                "core.lm_head.weight",
                "question_intent.weight",
                "question_intent.bias",
            }:
                target[name][: value.shape[0]].copy_(value)
            else:
                target[name].copy_(value)
        # New output rows start neutral, old raw logits are exactly preserved.
        target["core.lm_head.weight"][base.VOCAB_SIZE :].zero_()
        self.load_state_dict(target, strict=True)


def select_answer(probabilities: list[float], threshold: float | None) -> int:
    values = np.asarray(probabilities, dtype=float)
    if (
        values.shape != (VOCAB_SIZE,)
        or not np.isfinite(values).all()
        or np.any(values < 0)
        or not np.isclose(values.sum(), 1, atol=1e-5)
    ):
        raise ValueError("invalid full-vocabulary probabilities")
    if threshold is None:
        return UNKNOWN
    if not 0 <= threshold <= 1:
        raise ValueError("invalid threshold")
    best = int(values.argmax())
    return best if best in ANSWER_TEXT and values[best] >= threshold else UNKNOWN


def consensus_probabilities(views: list[list[float]]) -> list[float]:
    if len(views) < 2:
        raise ValueError("require two views")
    for view in views:
        select_answer(view, 0)
    labels = {int(np.argmax(v)) for v in views}
    result = [0.0] * VOCAB_SIZE
    if len(labels) != 1 or next(iter(labels)) not in ANSWER_TEXT:
        result[UNKNOWN] = 1
    else:
        label = next(iter(labels))
        confidence = min(v[label] for v in views)
        result[label] = confidence
        result[UNKNOWN] += 1 - confidence
    return result


def metrics(gold: list[int], predicted: list[int]) -> dict:
    if (
        not gold
        or len(gold) != len(predicted)
        or any(type(v) is not int or v not in ANSWER_TEXT for v in gold + predicted)
    ):
        raise ValueError("invalid metric labels")
    # Preserve exact output identity: a prototype answer cannot alias YES/NO.
    if any(v in {YES, NO} for v in gold + predicted):
        accepted = sum(p != UNKNOWN for p in predicted)
        answerable = sum(g != UNKNOWN for g in gold)
        unknown = len(gold) - answerable
        return {
            "examples": len(gold),
            "accepted": accepted,
            "false_assertions": sum(
                p != UNKNOWN and p != g for g, p in zip(gold, predicted, strict=True)
            ),
            "accuracy": sum(g == p for g, p in zip(gold, predicted, strict=True))
            / len(gold),
            "answerable_recall": sum(
                g == p and g != UNKNOWN for g, p in zip(gold, predicted, strict=True)
            )
            / answerable
            if answerable
            else None,
            "unknown_recall": sum(
                g == p == UNKNOWN for g, p in zip(gold, predicted, strict=True)
            )
            / unknown
            if unknown
            else None,
        }
    return base.metrics(gold, predicted)


def calibrate(
    rows: list[Sample], probabilities: list[list[float]], *, min_accepted: int = 50
) -> dict:
    if len(rows) != len(probabilities) or min_accepted < 1:
        raise ValueError("invalid calibration inputs")
    result = {}
    for task in TASKS:
        ids = [i for i, row in enumerate(rows) if row.task == task]
        choices = []
        grid = (
            (0.99, 0.995, 0.999, 0.9995, 0.9999)
            if task in NEW_TASKS
            else (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995)
        )
        for threshold in grid:
            stats = metrics(
                [rows[i].answer for i in ids],
                [select_answer(probabilities[i], threshold) for i in ids],
            )
            if not stats["false_assertions"] and stats["accepted"] >= min_accepted:
                choices.append((stats["accepted"], threshold))
        result[task] = max(choices)[1] if choices else None
    return result


def sample_record(row: Sample) -> dict:
    return asdict(row) | {
        "answer_text": ANSWER_TEXT[row.answer],
        "provenance": "OWN_PROCEDURAL_ORACLE_NOT_MODEL_PSEUDOLABEL",
        "scope": "bounded synthetic incremental course; not textbooks",
    }
