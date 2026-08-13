from __future__ import annotations

from torch import nn


def count_parameters(model: nn.Module, *, trainable_only: bool = False) -> int:
    parameters = model.parameters()

    if trainable_only:
        return sum(
            parameter.numel() for parameter in parameters if parameter.requires_grad
        )

    return sum(parameter.numel() for parameter in parameters)


def format_parameter_count(parameter_count: int) -> str:
    if parameter_count >= 1_000_000_000:
        return f"{parameter_count / 1_000_000_000:.2f}B"

    if parameter_count >= 1_000_000:
        return f"{parameter_count / 1_000_000:.2f}M"

    if parameter_count >= 1_000:
        return f"{parameter_count / 1_000:.2f}K"

    return str(parameter_count)
