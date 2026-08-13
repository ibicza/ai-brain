from __future__ import annotations

from typing import Any

import torch

from ai_brain.model.config import ModelConfig, debug_config, tiny_config
from ai_brain.model.tiny_transformer import TinyCausalTransformer
from ai_brain.model.utils import count_parameters, format_parameter_count
from ai_brain.runtime.device import DeviceInfo, get_device_info


def get_named_model_config(name: str) -> ModelConfig:
    if name == "debug":
        return debug_config()

    if name == "tiny":
        return tiny_config()

    raise ValueError(f"Unknown model config: {name}")


def run_model_smoke_step(
    info: DeviceInfo | None = None,
    *,
    config_name: str = "debug",
    seed: int = 1234,
    batch_size: int = 2,
    sequence_length: int = 16,
) -> dict[str, Any]:
    info = info or get_device_info()
    config = get_named_model_config(config_name)

    if sequence_length > config.max_sequence_length:
        raise ValueError(
            "sequence_length exceeds config.max_sequence_length: "
            f"{sequence_length} > {config.max_sequence_length}"
        )

    torch.manual_seed(seed)
    if info.is_cuda:
        torch.cuda.manual_seed_all(seed)

    model = TinyCausalTransformer(config).to(info.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

    input_ids = torch.randint(
        low=0,
        high=config.vocab_size,
        size=(batch_size, sequence_length),
        device=info.device,
        dtype=torch.long,
    )
    target_ids = torch.randint(
        low=0,
        high=config.vocab_size,
        size=(batch_size, sequence_length),
        device=info.device,
        dtype=torch.long,
    )

    before_step = [parameter.detach().clone() for parameter in model.parameters()]

    logits = model(input_ids)
    loss = torch.nn.functional.cross_entropy(
        logits.view(-1, config.vocab_size),
        target_ids.view(-1),
    )

    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()

    if info.is_cuda:
        torch.cuda.synchronize()

    parameters_changed = any(
        not torch.equal(before, after.detach())
        for before, after in zip(before_step, model.parameters(), strict=True)
    )

    parameter_count = count_parameters(model)

    return {
        "model": "TinyCausalTransformer",
        "config_name": config_name,
        "device": str(info.device),
        "device_name": info.name,
        "batch_size": batch_size,
        "sequence_length": sequence_length,
        "vocab_size": config.vocab_size,
        "parameters": parameter_count,
        "parameters_human": format_parameter_count(parameter_count),
        "logits_shape": list(logits.shape),
        "loss": float(loss.detach().cpu().item()),
        "parameters_changed": parameters_changed,
    }
