"""Offline audit of a discovered RNG shortcut; never an inference feature.

This specific leakage detector is a regression check, not a proof against every
possible shortcut. RNG domain separation is the source-level protection.
"""

from __future__ import annotations

import numpy as np

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_zero as z


def audit(*, seed: int, count: int = 10000, independent_labels: bool = True):
    if type(count) is not int or not 1000 <= count <= 10000:
        raise ValueError("Leakage audit requires 1000 to 10000 scenes")
    rows = c.scenes(
        "train",
        count,
        seed,
        profile="diverse_clear",
        independent_labels=independent_labels,
    )
    matrices = np.zeros((2, 3, 3), dtype=np.int64)
    for row in rows:
        background = np.random.default_rng(row.seed).uniform(100, 180, 3)
        guess = np.floor((background[:2] - 100) / 80 * 3).astype(int)
        for side, item in enumerate(row.items):
            matrices[side, c.PATTERNS.index(item.pattern), guess[side]] += 1
    accuracy = [float(m.trace() / count) for m in matrices]
    return {
        "schema": 1,
        "seed": seed,
        "count_per_side": count,
        "independent_labels": independent_labels,
        "label_rng_policy": c.LABEL_RNG_POLICY
        if independent_labels
        else "archival shared stream",
        "detector": "floor((base_background_channel - 100) / 80 * 3); R left, G right",
        "confusion_gold_by_background_prediction": matrices.tolist(),
        "background_only_pattern_accuracy": accuracy,
        "known_shortcut_absent": all(a < 0.38 for a in accuracy),
        "limits": "Tests the discovered pattern/background shortcut only; not a comprehensive independence or semantic-understanding proof.",
        "production_admitted": False,
    }


def audit_zero(*, seed=76100000, count=10000, independent_labels=True):
    """Legacy textured transfer noise; no claim that a trained model used it."""
    if type(count) is not int or not 1000 <= count <= 10000:
        raise ValueError("Leakage audit requires 1000 to 10000 scenes")
    matrices = np.zeros((2, 6, 6), dtype=np.int64)
    for i in range(count):
        row = z.make_scene(
            "audit",
            i,
            seed=seed + i,
            final_style=True,
            independent_labels=independent_labels,
        )
        if row.kind != "normal":
            continue
        # Top-left pixels are background, untouched by any possible object.
        noise = np.random.default_rng(row.seed).integers(-5, 6, (96, 96))
        guesses = np.floor((noise[0, :2] + 5.5) * 6 / 11).astype(int)
        matrices[0, len(row.objects), guesses[0]] += 1
        if row.objects:
            matrices[1, z.SHAPES.index(row.objects[0].shape), guesses[1]] += 1
    accuracy = [float(m.trace() / m.sum()) for m in matrices]
    return {
        "seed": seed,
        "total_scenes": count,
        "count_examples": int(matrices[0].sum()),
        "shape_examples": int(matrices[1].sum()),
        "independent_labels": independent_labels,
        "background_only_count_shape_accuracy": accuracy,
        "confusion_gold_by_background_prediction": matrices.tolist(),
        "known_shortcut_absent": all(a < 0.22 for a in accuracy),
        "limits": "Textured transfer backgrounds only. Ordinary training backgrounds are fixed. Does not show that historical models exploited this shortcut or invalidate their every skill.",
    }
