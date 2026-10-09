"""Training-only multiview objectives, not additional inference knowledge.

Adaptations of AugMix JSD, SupCon's outside-log positive averaging, and VICReg.
UNKNOWN is not a semantic class and is excluded from supervised contrastive pairs.
"""

from __future__ import annotations

import torch
from torch.nn import functional as F


def js_consistency(first, second):
    """Jensen-Shannon divergence on the explicitly admitted finite answer logits."""
    if first.shape != second.shape or first.ndim != 2 or not first.numel():
        raise ValueError("Aligned nonempty answer matrices required")
    if not torch.isfinite(first).all() or not torch.isfinite(second).all():
        raise ValueError("Select finite admitted logits before computing JSD")
    p, q = first.softmax(-1), second.softmax(-1)
    mixture = ((p + q) * 0.5).clamp_min(1e-8).log()
    return (
        F.kl_div(mixture, p, reduction="batchmean")
        + F.kl_div(mixture, q, reduction="batchmean")
    ) * 0.5


def supervised_contrastive(first, second, labels, *, unknown, temperature=0.1):
    """Two-view SupCon; heterogeneous UNKNOWN rows are neither positives nor negatives."""
    if (
        first.shape != second.shape
        or first.ndim != 2
        or labels.shape != (len(first),)
        or temperature <= 0
        or not torch.isfinite(first).all()
        or not torch.isfinite(second).all()
    ):
        raise ValueError("Aligned finite features and positive temperature required")
    keep = labels != unknown
    if not keep.any():
        return (first.sum() + second.sum()) * 0
    features = F.normalize(torch.cat((first[keep], second[keep])), dim=-1)
    gold = labels[keep].repeat(2)
    logits = features @ features.T / temperature
    diagonal = torch.eye(len(features), device=features.device, dtype=torch.bool)
    positives = (gold[:, None] == gold[None]) & ~diagonal
    logits = logits.masked_fill(diagonal, float("-inf"))
    log_probability = logits - torch.logsumexp(logits, dim=1, keepdim=True)
    # masked_fill avoids 0 * -inf and retains exact outside-log averaging.
    return -(
        log_probability.masked_fill(~positives, 0).sum(1) / positives.sum(1)
    ).mean()


def vicreg(first, second):
    """Single-device VICReg with unbiased variance and both covariance penalties."""
    if (
        first.shape != second.shape
        or first.ndim != 2
        or len(first) < 2
        or first.shape[1] < 2
        or not torch.isfinite(first).all()
        or not torch.isfinite(second).all()
    ):
        raise ValueError("At least two aligned finite feature vectors required")
    invariance = F.mse_loss(first, second)
    variance, covariance = first.new_zeros(()), first.new_zeros(())
    dim = first.shape[1]
    diagonal = torch.eye(dim, device=first.device, dtype=torch.bool)
    for features in (first, second):
        centered = features - features.mean(0)
        variance = variance + F.relu(1 - (centered.var(0) + 1e-4).sqrt()).mean() / 2
        matrix = centered.T @ centered / (len(features) - 1)
        covariance = covariance + matrix.masked_fill(diagonal, 0).square().sum() / dim
    return 25 * invariance + 25 * variance + covariance
