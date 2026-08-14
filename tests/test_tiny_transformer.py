import torch

from ai_brain.model.config import debug_config, numeric_debug_config, tiny_config
from ai_brain.model.tiny_transformer import (
    TinyCausalTransformer,
    TinyNumericCausalTransformer,
)
from ai_brain.model.utils import count_parameters, format_parameter_count


def test_tiny_transformer_forward_shape() -> None:
    config = debug_config()
    model = TinyCausalTransformer(config)

    input_ids = torch.randint(
        low=0,
        high=config.vocab_size,
        size=(2, 8),
        dtype=torch.long,
    )

    logits = model(input_ids)

    assert logits.shape == (2, 8, config.vocab_size)


def test_tiny_transformer_backward_step() -> None:
    config = debug_config()
    model = TinyCausalTransformer(config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

    input_ids = torch.randint(
        low=0,
        high=config.vocab_size,
        size=(2, 8),
        dtype=torch.long,
    )
    target_ids = torch.randint(
        low=0,
        high=config.vocab_size,
        size=(2, 8),
        dtype=torch.long,
    )

    logits = model(input_ids)

    loss = torch.nn.functional.cross_entropy(
        logits.view(-1, config.vocab_size),
        target_ids.view(-1),
    )

    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()

    assert torch.isfinite(loss)


def test_parameter_count_is_positive() -> None:
    model = TinyCausalTransformer(tiny_config())

    parameter_count = count_parameters(model)

    assert parameter_count > 0
    assert format_parameter_count(parameter_count).endswith("K")


def test_numeric_tiny_transformer_forward_shape() -> None:
    config = numeric_debug_config()
    model = TinyNumericCausalTransformer(config)

    input_ids = torch.randint(
        low=0,
        high=config.vocab_size,
        size=(2, 8),
        dtype=torch.long,
    )
    digit_value_ids = torch.randint(0, 11, size=(2, 8), dtype=torch.long)
    digit_place_ids = torch.randint(0, 5, size=(2, 8), dtype=torch.long)
    number_role_ids = torch.randint(0, 8, size=(2, 8), dtype=torch.long)
    operation_step_ids = torch.randint(0, 9, size=(2, 8), dtype=torch.long)

    logits = model(
        input_ids,
        digit_value_ids=digit_value_ids,
        digit_place_ids=digit_place_ids,
        number_role_ids=number_role_ids,
        operation_step_ids=operation_step_ids,
    )

    assert logits.shape == (2, 8, config.vocab_size)


def test_numeric_tiny_transformer_defaults_missing_features_to_none() -> None:
    config = numeric_debug_config()
    model = TinyNumericCausalTransformer(config)
    input_ids = torch.randint(0, config.vocab_size, size=(2, 8), dtype=torch.long)

    logits = model(input_ids)

    assert logits.shape == (2, 8, config.vocab_size)
