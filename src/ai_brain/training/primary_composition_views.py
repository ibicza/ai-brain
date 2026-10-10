"""Bounded reflection consistency; RGB/query-only, no target boxes or labels.

Scores encode unanimity and minimum view confidence, not calibrated probability.
This policy is valid only for the course's left/right attribute questions.
"""

from __future__ import annotations

import torch

from ai_brain.training import primary_composition as c

VIEWS = ((False, False), (True, False), (False, True), (True, True))


def swap_sides(questions):
    if questions.ndim != 2 or questions.dtype != torch.long:
        raise ValueError("Invalid bounded question tokens")
    result = questions.clone()
    for left, right in (("левого", "правого"), ("left", "right")):
        a, b = c.WORD_IDS[left], c.WORD_IDS[right]
        result[questions == a] = b
        result[questions == b] = a
    return result


def reflected(images, questions, *, horizontal=False, vertical=False):
    if type(horizontal) is not bool or type(vertical) is not bool:
        raise ValueError("Reflection flags must be booleans")
    axes = ([2] if vertical else []) + ([3] if horizontal else [])
    return (
        images.flip(axes) if axes else images,
        swap_sides(questions) if horizontal else questions,
    )


def unanimous_scores(view_probabilities):
    """All views must agree; agreed score is the lowest observed confidence."""
    p = view_probabilities
    if (
        p.ndim != 3
        or p.shape[0] != 4
        or p.shape[2] != len(c.ANSWERS)
        or not p.is_floating_point()
        or not torch.isfinite(p).all()
        or torch.any((p < 0) | (p > 1))
        or not torch.allclose(p.sum(-1), torch.ones_like(p[..., 0]), atol=1e-5)
    ):
        raise ValueError("Invalid four-view probabilities")
    best = p.argmax(-1)
    agreed = (best == best[0]).all(0) & (best[0] != c.UNKNOWN)
    confidence = p.max(-1).values.min(0).values
    # A normalized score vector lets the existing refusal grid consume it.
    # On disagreement its argmax is UNKNOWN, never an averaged assertion.
    scores = torch.zeros_like(p[0])
    scores[:, c.UNKNOWN] = 1
    rows = torch.arange(len(scores), device=scores.device)[agreed]
    scores[rows, best[0, agreed]] = confidence[agreed]
    scores[rows, c.UNKNOWN] = 1 - confidence[agreed]
    return scores


@torch.no_grad()
def consistent_probabilities(model, images, questions):
    """No renderer facts; four fixed views, same own weights and question scope."""
    probabilities = []
    for horizontal, vertical in VIEWS:
        x, q = reflected(images, questions, horizontal=horizontal, vertical=vertical)
        probabilities.append(model(x, q).softmax(-1))
    return unanimous_scores(torch.stack(probabilities))


def augment_batch(images, questions, rng, *, supervision=None):
    """Independent fair reflections per example; all attribute labels unchanged."""
    horizontal = torch.as_tensor(
        rng.integers(0, 2, size=len(images)), device=images.device, dtype=torch.bool
    )
    vertical = torch.as_tensor(
        rng.integers(0, 2, size=len(images)), device=images.device, dtype=torch.bool
    )
    x = torch.where(horizontal[:, None, None, None], images.flip(3), images)
    x = torch.where(vertical[:, None, None, None], x.flip(2), x)
    q = torch.where(horizontal[:, None], swap_sides(questions), questions)
    if supervision is not None:
        if supervision.shape != (len(images), 1, 96, 96):
            raise ValueError("Aligned target foreground required")
        mask = torch.where(
            horizontal[:, None, None, None], supervision.flip(3), supervision
        )
        mask = torch.where(vertical[:, None, None, None], mask.flip(2), mask)
        return x, q, mask
    return x, q
