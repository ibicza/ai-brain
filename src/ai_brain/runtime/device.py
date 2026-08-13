from dataclasses import dataclass
from typing import Any

import torch
from torch import nn


@dataclass(frozen=True)
class DeviceInfo:
    device: torch.device
    name: str
    cuda_available: bool
    cuda_device_count: int
    total_memory_bytes: int | None = None
    compute_capability: tuple[int, int] | None = None

    @property
    def is_cuda(self) -> bool:
        return self.device.type == "cuda"

    @property
    def total_memory_gb(self) -> float | None:
        if self.total_memory_bytes is None:
            return None
        return self.total_memory_bytes / 1024**3


def get_device_info(prefer_cuda: bool = True) -> DeviceInfo:
    cuda_available = torch.cuda.is_available()
    cuda_device_count = torch.cuda.device_count() if cuda_available else 0

    if prefer_cuda and cuda_available:
        device_index = torch.cuda.current_device()
        properties = torch.cuda.get_device_properties(device_index)

        return DeviceInfo(
            device=torch.device(f"cuda:{device_index}"),
            name=properties.name,
            cuda_available=True,
            cuda_device_count=cuda_device_count,
            total_memory_bytes=properties.total_memory,
            compute_capability=torch.cuda.get_device_capability(device_index),
        )

    return DeviceInfo(
        device=torch.device("cpu"),
        name="CPU",
        cuda_available=cuda_available,
        cuda_device_count=cuda_device_count,
    )


def format_device_info(info: DeviceInfo | None = None) -> str:
    info = info or get_device_info()

    lines = [
        f"device: {info.device}",
        f"name: {info.name}",
        f"cuda_available: {info.cuda_available}",
        f"cuda_device_count: {info.cuda_device_count}",
    ]

    if info.total_memory_gb is not None:
        lines.append(f"total_memory_gb: {info.total_memory_gb:.2f}")

    if info.compute_capability is not None:
        major, minor = info.compute_capability
        lines.append(f"compute_capability: {major}.{minor}")

    return "\n".join(lines)


def run_smoke_train_step(
    info: DeviceInfo | None = None,
    *,
    seed: int = 1234,
    batch_size: int = 8,
    input_dim: int = 32,
    hidden_dim: int = 64,
    output_dim: int = 16,
) -> dict[str, Any]:
    info = info or get_device_info()

    torch.manual_seed(seed)
    if info.is_cuda:
        torch.cuda.manual_seed_all(seed)

    model = nn.Sequential(
        nn.Linear(input_dim, hidden_dim),
        nn.GELU(),
        nn.Linear(hidden_dim, output_dim),
    ).to(info.device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-2)

    x = torch.randn(batch_size, input_dim, device=info.device)
    target = torch.randn(batch_size, output_dim, device=info.device)

    before_step = [parameter.detach().clone() for parameter in model.parameters()]

    prediction = model(x)
    loss = nn.functional.mse_loss(prediction, target)

    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()

    if info.is_cuda:
        torch.cuda.synchronize()

    parameters_changed = any(
        not torch.equal(before, after.detach())
        for before, after in zip(before_step, model.parameters(), strict=True)
    )

    return {
        "device": str(info.device),
        "device_name": info.name,
        "loss": float(loss.detach().cpu().item()),
        "parameters_changed": parameters_changed,
    }
