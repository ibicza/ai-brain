from __future__ import annotations

import torch

from ai_brain.training.lm_dataset import TokenizedLmDataset


def sample_batch(
    dataset: TokenizedLmDataset,
    *,
    batch_size: int,
    device: torch.device,
    generator: torch.Generator,
) -> dict[str, torch.Tensor]:
    if len(dataset) == 0:
        raise ValueError("Cannot sample from an empty dataset")

    indices = torch.randint(
        low=0,
        high=len(dataset),
        size=(batch_size,),
        generator=generator,
    )
    return batch_by_indices(dataset, indices=indices, device=device)


def batch_by_indices(
    dataset: TokenizedLmDataset,
    *,
    indices: torch.Tensor,
    device: torch.device,
) -> dict[str, torch.Tensor]:
    return {
        "input_ids": dataset.input_ids[indices].to(device),
        "labels": dataset.labels[indices].to(device),
        "attention_mask": dataset.attention_mask[indices].to(device),
        "digit_value_ids": dataset.digit_value_ids[indices].to(device),
        "digit_place_ids": dataset.digit_place_ids[indices].to(device),
        "number_role_ids": dataset.number_role_ids[indices].to(device),
        "operation_step_ids": dataset.operation_step_ids[indices].to(device),
    }


def batch_shapes(batch: dict[str, torch.Tensor]) -> dict[str, list[int]]:
    return {key: list(value.shape) for key, value in batch.items()}
