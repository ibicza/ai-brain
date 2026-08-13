import math

import pytest
import torch

from ai_brain.runtime.device import (
    format_device_info,
    get_device_info,
    run_smoke_train_step,
)


def test_cpu_smoke_train_step() -> None:
    info = get_device_info(prefer_cuda=False)

    result = run_smoke_train_step(info)

    assert result["device"] == "cpu"
    assert isinstance(result["loss"], float)
    assert math.isfinite(result["loss"])
    assert result["parameters_changed"] is True


def test_format_device_info() -> None:
    info = get_device_info(prefer_cuda=False)

    description = format_device_info(info)

    assert "device: cpu" in description
    assert "name: CPU" in description


def test_cuda_smoke_train_step_when_available() -> None:
    if not torch.cuda.is_available():
        pytest.skip("CUDA is not available")

    info = get_device_info(prefer_cuda=True)

    result = run_smoke_train_step(info)

    assert result["device"].startswith("cuda:")
    assert isinstance(result["loss"], float)
    assert math.isfinite(result["loss"])
    assert result["parameters_changed"] is True
