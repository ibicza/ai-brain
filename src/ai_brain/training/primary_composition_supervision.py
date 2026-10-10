"""Training-only group sampling and foreground attention targets.

No labels, target masks or scene metadata are supplied to inference. This is
balanced sampling, not Group DRO, U-Net, a learned rejector or an object detector.
"""

import numpy as np
import torch
from torch.nn import functional as F

SAMPLING_RULES = ("legacy_48_16", "balanced_task_answer_32_32")


class GroupSampler:
    """Equal mass per task, then answer, then a uniform row in that group."""

    def __init__(self, records):
        self.groups = {}
        for i, record in enumerate(records):
            self.groups.setdefault(record["task"], {}).setdefault(
                record["answer"], []
            ).append(i)
        if not self.groups:
            raise ValueError("Nonempty training records required")

    def sample(self, rng, count, *, omit_pattern=False):
        if type(count) is not int or count < 1 or type(omit_pattern) is not bool:
            raise ValueError("Positive sample count and boolean curriculum required")
        tasks = sorted(t for t in self.groups if not omit_pattern or t != "pattern")
        if not tasks:
            raise ValueError("No eligible training task")
        result = []
        for _ in range(count):
            task = tasks[int(rng.integers(len(tasks)))]
            answers = sorted(self.groups[task])
            answer = answers[int(rng.integers(len(answers)))]
            rows = self.groups[task][answer]
            result.append(rows[int(rng.integers(len(rows)))])
        return np.asarray(result, dtype=np.int64)

    def audit(self):
        return {
            task: {str(answer): len(rows) for answer, rows in sorted(groups.items())}
            for task, groups in sorted(self.groups.items())
        }


def foreground_attention_loss(attention, masks):
    """KL from visible renderer foreground to word-conditioned visual attention.

    Empty/fully hidden targets have no auxiliary loss, not a hallucinated mask.
    Gold is never used as a gate or feature. Soft antialias coverage is retained.
    """
    if (
        attention.ndim != 2
        or masks.shape != (len(attention), 1, 96, 96)
        or not torch.isfinite(attention).all()
        or not torch.isfinite(masks).all()
        or torch.any((attention < 0) | (attention > 1))
        or torch.any((masks < 0) | (masks > 1))
        or not torch.allclose(
            attention.sum(1), torch.ones_like(attention[:, 0]), atol=1e-5
        )
    ):
        raise ValueError("Aligned probability attention and finite soft masks required")
    side = int(attention.shape[1] ** 0.5)
    if side * side != attention.shape[1]:
        raise ValueError("Square input-patch attention required")
    target = F.adaptive_avg_pool2d(masks, (side, side)).flatten(1)
    mass = target.sum(1)
    eligible = mass > 0
    if not eligible.any():
        return attention.sum() * 0
    target = target[eligible] / mass[eligible, None]
    return F.kl_div(
        attention[eligible].clamp_min(1e-12).log(), target, reduction="batchmean"
    )
