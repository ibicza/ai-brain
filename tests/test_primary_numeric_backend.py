from types import SimpleNamespace

import pytest

from ai_brain.training import primary_numeric_backend as numeric


@pytest.fixture
def backend(monkeypatch):
    backend = SimpleNamespace(
        fp32_precision="none",
        cuda=SimpleNamespace(matmul=SimpleNamespace(fp32_precision="ieee")),
        cudnn=SimpleNamespace(
            fp32_precision="none",
            conv=SimpleNamespace(fp32_precision="tf32"),
            rnn=SimpleNamespace(fp32_precision="tf32"),
            version=lambda: 95000,
        ),
    )
    monkeypatch.setattr(numeric.torch, "backends", backend)
    return backend


def test_ieee_sets_each_operator_and_legacy_never_mutates(backend):
    before = numeric.precision_settings()
    assert numeric.configure("legacy")["precision_settings"] == before
    explicit = numeric.configure("ieee")
    assert set(explicit["precision_settings"].values()) == {"ieee"}
    assert (
        numeric.check_contract(explicit)["precision_settings"]
        == explicit["precision_settings"]
    )


def test_archival_precision_contract_rejects_process_drift(backend):
    frozen = numeric.configure("legacy")
    backend.cudnn.conv.fp32_precision = "ieee"
    with pytest.raises(ValueError, match="differs from frozen"):
        numeric.check_contract(frozen)


@pytest.mark.parametrize("policy", (None, True, [], "fast", 1))
def test_unregistered_precision_cannot_silently_change_backend(backend, policy):
    before = numeric.precision_settings()
    with pytest.raises(ValueError, match="Registered numeric"):
        numeric.configure(policy)
    assert numeric.precision_settings() == before


def test_forged_ieee_contract_rejected(backend):
    frozen = numeric.configure("ieee")
    frozen["precision_settings"]["cuda_matmul"] = "tf32"
    with pytest.raises(ValueError, match="differs from frozen"):
        numeric.check_contract(frozen)
