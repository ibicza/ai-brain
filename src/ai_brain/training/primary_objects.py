"""Append-only own object naming course on reviewed real participant drawings.

One shared inherited pixel/word model; labels and source IDs are never inputs.
This bounded object vocabulary is not general sight, language or M33 closure.
"""

from __future__ import annotations

import re
from dataclasses import replace

import numpy as np
import torch
from torch import nn

from ai_brain.training import primary_relations as previous
from ai_brain.training import primary_zero as base

OBJECTS = ("яблоко", "банан", "морковь", "рыба", "дерево", "кружка", "стул", "книга")
OBJECT_IDS = {name: previous.VOCAB_SIZE + i for i, name in enumerate(OBJECTS)}
UNKNOWN = previous.UNKNOWN
ANSWER_TEXT = previous.ANSWER_TEXT | {
    identifier: word for word, identifier in OBJECT_IDS.items()
}
TASKS = (*previous.TASKS, "object")
OBJECT_QUESTIONS = (
    "Назови предмет на картинке.",
    "Какой предмет изображён на картинке?",
    "Что изображено на картинке?",
    "Назови изображённый предмет.",
    "Name the object.",
    "What object is shown?",
    "Какой предмет на картинке изображён?",
    "Name the shown object.",
)
TEACHING = OBJECT_QUESTIONS[:-2]
WORD_IDS = dict(previous.WORD_IDS)
NEW_WORDS = sorted(
    {w for q in TEACHING for w in re.findall(r"[a-zа-яё]+|[.?]", q.lower())}
    - WORD_IDS.keys()
)
WORD_IDS.update(
    {word: previous.VOCAB_SIZE + len(OBJECTS) + i for i, word in enumerate(NEW_WORDS)}
)
VOCAB_SIZE = previous.VOCAB_SIZE + len(OBJECTS) + len(NEW_WORDS)


def question_task(text: str) -> str:
    if text in OBJECT_QUESTIONS:
        return "object"
    return previous.question_task(text)


def encode_question(text: str) -> list[int]:
    question_task(text)
    words = re.findall(r"[a-zа-яё]+|[.?]", text.lower())
    if len(words) > base.QUESTION_LENGTH:
        raise ValueError("Question would be truncated")
    return (
        [WORD_IDS[word] for word in words]
        + [base.PAD_ID] * (base.QUESTION_LENGTH - len(words))
        + [base.READ_ID]
    )


class ObjectsModel(previous.RelationsModel):
    """Same inherited forward; only append vocabulary and supervised intent rows."""

    def __init__(self, *, width: int = 96, layers: int = 2) -> None:
        super().__init__(width=width, layers=layers)
        self.core.config = replace(self.core.config, vocab_size=VOCAB_SIZE)
        self.core.token_embedding = nn.Embedding(VOCAB_SIZE, width)
        self.core.lm_head = nn.Linear(width, VOCAB_SIZE, bias=False)
        self.question_intent = nn.Linear(width, len(TASKS))
        self.compatible_legacy_vocabulary = False
        self.register_buffer(
            "object_questions",
            torch.tensor([encode_question(text) for text in OBJECT_QUESTIONS]),
            persistent=False,
        )

    def forward(self, images, questions, *, return_intent=False):
        result = super().forward(images, questions, return_intent=return_intent)
        if not self.compatible_legacy_vocabulary:
            return result
        logits, intents = result if return_intent else (result, None)
        # Closed supported-word compatibility policy, not a gold/task input.
        # Unchanged legacy questions retain their previous vocabulary normalizer.
        is_object = (questions[:, None] == self.object_questions[None]).all(-1).any(-1)
        tail = logits[:, previous.VOCAB_SIZE :].masked_fill(
            ~is_object[:, None], float("-inf")
        )
        logits = torch.cat((logits[:, : previous.VOCAB_SIZE], tail), dim=-1)
        return (logits, intents) if return_intent else logits

    def load_previous(self, state: dict[str, torch.Tensor]) -> None:
        original = previous.RelationsModel(
            width=self.core.config.d_model, layers=self.core.config.num_layers
        )
        original.load_state_dict(state, strict=True)
        target = self.state_dict()
        expandable = {
            "core.token_embedding.weight",
            "core.lm_head.weight",
            "question_intent.weight",
            "question_intent.bias",
        }
        for name, value in state.items():
            if name in expandable:
                target[name][: value.shape[0]].copy_(value)
            else:
                target[name].copy_(value)
        target["core.lm_head.weight"][previous.VOCAB_SIZE :].zero_()
        self.load_state_dict(target, strict=True)


def select_answer(probabilities, threshold: float | None) -> int:
    values = np.asarray(probabilities, dtype=float)
    if (
        values.shape != (VOCAB_SIZE,)
        or not np.isfinite(values).all()
        or np.any(values < 0)
        or not np.isclose(values.sum(), 1, atol=1e-5)
    ):
        raise ValueError("Invalid full-vocabulary probabilities")
    if threshold is None:
        return UNKNOWN
    if not 0 <= threshold <= 1:
        raise ValueError("Invalid threshold")
    label = int(values.argmax())
    return label if label in ANSWER_TEXT and values[label] >= threshold else UNKNOWN


def consensus_probabilities(views):
    if len(views) < 2:
        raise ValueError("Require multiple views")
    for view in views:
        select_answer(view, 0)
    labels = {int(np.argmax(view)) for view in views}
    result = [0.0] * VOCAB_SIZE
    if len(labels) != 1 or next(iter(labels)) not in ANSWER_TEXT:
        result[UNKNOWN] = 1
    else:
        label = next(iter(labels))
        confidence = min(view[label] for view in views)
        result[label] = confidence
        result[UNKNOWN] += 1 - confidence
    return result


def metrics(gold, predicted):
    if (
        not gold
        or len(gold) != len(predicted)
        or any(type(v) is not int or v not in ANSWER_TEXT for v in gold + predicted)
    ):
        raise ValueError("Invalid metric labels")
    accepted = sum(v != UNKNOWN for v in predicted)
    answerable = sum(v != UNKNOWN for v in gold)
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


def calibrate(tasks, gold, probabilities, min_accepted=50):
    if (
        len(tasks) != len(gold)
        or len(gold) != len(probabilities)
        or min_accepted < 1
        or set(tasks) - set(TASKS)
    ):
        raise ValueError("Invalid calibration inputs")
    thresholds = {}
    for task in TASKS:
        indices = [i for i, value in enumerate(tasks) if value == task]
        if not indices:
            thresholds[task] = None
            continue
        choices = []
        grid = (
            (0.99, 0.995, 0.999, 0.9995, 0.9999)
            if task in (*previous.NEW_TASKS, "object")
            else (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995)
        )
        for threshold in grid:
            stats = metrics(
                [gold[i] for i in indices],
                [select_answer(probabilities[i], threshold) for i in indices],
            )
            if stats["false_assertions"] == 0 and stats["accepted"] >= min_accepted:
                choices.append((stats["accepted"], threshold))
        thresholds[task] = max(choices)[1] if choices else None
    return thresholds
