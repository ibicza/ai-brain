from __future__ import annotations

from dataclasses import replace

import torch

from ai_brain.model.config import recurrent_debug_config, recurrent_tiny_config
from ai_brain.model.recurrent_transformer import RecurrentCausalTransformer
from ai_brain.model.tiny_transformer import TransformerBlock
from ai_brain.model.utils import count_parameters


def test_recurrent_transformer_forward_shape() -> None:
    config = recurrent_debug_config()
    model = RecurrentCausalTransformer(config)
    input_ids = torch.randint(
        low=0,
        high=config.vocab_size,
        size=(2, 8),
        dtype=torch.long,
    )

    logits = model(input_ids)

    assert logits.shape == (2, 8, config.vocab_size)


def test_recurrent_transformer_causal_mask_prevents_future_leakage() -> None:
    torch.manual_seed(1234)
    config = recurrent_debug_config()
    model = RecurrentCausalTransformer(config)
    model.eval()

    input_ids = torch.tensor([[1, 2, 3, 4, 5]], dtype=torch.long)
    changed_future = input_ids.clone()
    changed_future[0, 4] = 99

    with torch.no_grad():
        original_logits = model(input_ids)
        changed_logits = model(changed_future)

    assert torch.allclose(original_logits[:, :4, :], changed_logits[:, :4, :])


def test_recurrent_parameter_count_is_positive() -> None:
    model = RecurrentCausalTransformer(recurrent_tiny_config())

    assert count_parameters(model) > 0


def test_recurrent_core_is_one_shared_block() -> None:
    model = RecurrentCausalTransformer(recurrent_tiny_config())

    assert isinstance(model.recurrent_core, TransformerBlock)
    assert not hasattr(model, "recurrent_cores")


def test_recurrent_parameter_count_does_not_scale_with_cycles() -> None:
    base_config = recurrent_debug_config()
    two_cycle_model = RecurrentCausalTransformer(
        replace(base_config, recurrent_cycles=2)
    )
    six_cycle_model = RecurrentCausalTransformer(
        replace(base_config, recurrent_cycles=6)
    )

    assert count_parameters(two_cycle_model) == count_parameters(six_cycle_model)
