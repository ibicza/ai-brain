import math

from ai_brain.model.smoke import run_model_smoke_step
from ai_brain.runtime.device import get_device_info


def test_model_smoke_step_cpu() -> None:
    info = get_device_info(prefer_cuda=False)

    result = run_model_smoke_step(info, config_name="debug")

    assert result["model"] == "TinyCausalTransformer"
    assert result["config_name"] == "debug"
    assert result["device"] == "cpu"
    assert result["logits_shape"] == [2, 16, 256]
    assert isinstance(result["loss"], float)
    assert math.isfinite(result["loss"])
    assert result["parameters_changed"] is True
