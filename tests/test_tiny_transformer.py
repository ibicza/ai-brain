import torch

from ai_brain.model.config import (
    abacus_debug_config,
    coupled_debug_config,
    debug_config,
    gated_place_debug_config,
    numeric_debug_config,
    tiny_config,
)
from ai_brain.model.tiny_transformer import (
    TinyAbacusPositionTransformer,
    TinyCausalTransformer,
    TinyCoupledPositionTransformer,
    TinyGatedPlaceTransformer,
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


def test_abacus_position_transformer_forward_shape() -> None:
    config = abacus_debug_config()
    model = TinyAbacusPositionTransformer(config)
    input_ids = torch.randint(0, config.vocab_size, size=(2, 8), dtype=torch.long)
    abacus_position_ids = torch.randint(0, 16, size=(2, 8), dtype=torch.long)

    logits = model(input_ids, abacus_position_ids=abacus_position_ids)

    assert logits.shape == (2, 8, config.vocab_size)


def test_coupled_position_transformer_forward_shape() -> None:
    config = coupled_debug_config()
    model = TinyCoupledPositionTransformer(config)
    input_ids = torch.randint(0, config.vocab_size, size=(2, 8), dtype=torch.long)
    coupled_position_ids = torch.randint(0, 16, size=(2, 8), dtype=torch.long)

    logits = model(input_ids, coupled_position_ids=coupled_position_ids)

    assert logits.shape == (2, 8, config.vocab_size)


def test_gated_place_transformer_starts_with_zero_gate() -> None:
    config = gated_place_debug_config()
    model = TinyGatedPlaceTransformer(config)
    input_ids = torch.randint(0, config.vocab_size, size=(2, 8), dtype=torch.long)
    digit_place_ids = torch.randint(0, 5, size=(2, 8), dtype=torch.long)

    logits = model(input_ids, digit_place_ids=digit_place_ids)

    assert logits.shape == (2, 8, config.vocab_size)
    assert float(model.place_alpha.detach().item()) == 0.0
