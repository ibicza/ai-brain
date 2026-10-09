"""Train-only mild pixel variation; no metadata, labels or fabricated new gold."""

from __future__ import annotations

import torch
from torch.nn import functional as F


def diverse_view(images: torch.Tensor) -> torch.Tensor:
    if (
        images.ndim != 4
        or images.shape[1:] != (3, 96, 96)
        or not images.is_floating_point()
    ):
        raise ValueError("Expected floating RGB96x96 batch")
    count = len(images)
    device = images.device
    # Zoom out rather than crop out object parts. Geometry remains centered,
    # white fill is applied outside the frame, never black cutout rectangles.
    scale = 0.82 + torch.rand(count, device=device) * 0.18
    theta = torch.zeros(count, 2, 3, device=device, dtype=images.dtype)
    theta[:, 0, 0] = theta[:, 1, 1] = 1 / scale
    theta[:, :, 2] = (torch.rand(count, 2, device=device) - 0.5) * (4 / 96)
    grid = F.affine_grid(theta, images.shape, align_corners=False)
    output = 1 - F.grid_sample(
        1 - images, grid, align_corners=False, padding_mode="zeros"
    )
    # Color is not required to identify these eight objects. Partial grayscale
    # and light background exposure changes discourage palette memorization.
    gray = output.mean(1, keepdim=True)
    mix = torch.rand(count, 1, 1, 1, device=device) * 0.5
    output = output * (1 - mix) + gray * mix
    if torch.rand((), device=device) < 0.5:
        output = F.avg_pool2d(
            F.pad(output, (1, 1, 1, 1), mode="replicate"), 3, stride=1
        )
    exposure = 0.9 + torch.rand(count, 1, 1, 1, device=device) * 0.1
    background = torch.rand(count, 3, 1, 1, device=device) * 0.04
    output = output * exposure + background
    output = output + torch.randn_like(output) * 0.005
    return output.clamp(0, 1)
