import json

from ai_brain.cli import main


def test_device_command_cpu(capsys) -> None:
    exit_code = main(["device", "--cpu"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "device: cpu" in captured.out
    assert "name: CPU" in captured.out


def test_smoke_command_cpu(capsys) -> None:
    exit_code = main(["smoke", "--cpu"])

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert exit_code == 0
    assert result["device"] == "cpu"
    assert isinstance(result["loss"], float)
    assert result["parameters_changed"] is True


def test_model_info_command(capsys) -> None:
    exit_code = main(["model-info"])

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert exit_code == 0
    assert result["model"] == "TinyCausalTransformer"
    assert result["parameters"] > 0
    assert result["parameters"] == result["trainable_parameters"]
    assert result["config"]["d_model"] == 128
