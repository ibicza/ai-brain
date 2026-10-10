"""Transport preconditions only; a real remote receipt is still required."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "novel_remote",
    Path(__file__).parents[1] / "scripts/m33_composition_novel_remote.py",
)
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    root = tmp_path / "reference"
    root.mkdir()
    (root / "source-capsule.tgz").write_bytes(b"fake guard-only capsule")
    (root / "remote-receipt.json").write_text(
        json.dumps(
            {
                "status": "REMOTE_CONTINUATION_REPLAYED",
                "remote": "/home/ibicza/ai-brain/runs/m33-composition-20261010-v12",
                "source_capsule_sha256": remote.sha(root / "source-capsule.tgz"),
            }
        ),
        encoding="utf-8",
    )

    def forbidden_network():
        raise AssertionError("Unsafe input must not reach network")

    monkeypatch.setattr(remote.paramiko, "SSHClient", forbidden_network)
    return SimpleNamespace(
        reference=root,
        repo=Path(__file__).parents[1],
        key=tmp_path / "unused-key",
        child="cold-family-screen-v1",
        count=600,
        seed=2211041000,
    )


@pytest.mark.parametrize(
    "name,value",
    [
        ("child", "../../escape"),
        ("count", True),
        ("count", 0),
        ("count", 6001),
        ("seed", -1),
    ],
)
def test_invalid_scoped_inputs_do_not_create_files_or_connect(inputs, name, value):
    setattr(inputs, name, value)
    with pytest.raises(ValueError, match="Scoped fresh bounded"):
        remote.run(inputs)
    assert sorted(p.name for p in inputs.reference.iterdir()) == [
        "remote-receipt.json",
        "source-capsule.tgz",
    ]


def test_completed_capsule_mismatch_is_rejected_before_output(inputs):
    (inputs.reference / "source-capsule.tgz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Local completed source archive changed"):
        remote.run(inputs)
    assert not (inputs.reference / inputs.child).exists()


def test_existing_cold_evidence_is_not_replaced(inputs):
    child = inputs.reference / inputs.child
    child.mkdir()
    marker = child / "preserve.txt"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="Fresh local cold screen"):
        remote.run(inputs)
    assert marker.read_text() == "preserve"


def test_failed_preflight_cannot_be_treated_as_completed_model(inputs):
    path = inputs.reference / "remote-receipt.json"
    receipt = json.loads(path.read_text())
    receipt["status"] = "REMOTE_PREFLIGHT_FAILED_NOT_TRAINED"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="Completed explicit remote"):
        remote.run(inputs)
    assert not (inputs.reference / inputs.child).exists()
