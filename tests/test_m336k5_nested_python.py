from __future__ import annotations

from types import SimpleNamespace

from ai_brain.stage3.acquisition import m336i_production
from ai_brain.stage3.acquisition.m336k5_startup import M336K5_PROCESS_ROLES


def test_nested_production_roles_are_frozen_startup_roles() -> None:
    assert {"WINDOWS_PRODUCTION", "KARINA_PRODUCTION"} <= M336K5_PROCESS_ROLES


def test_m336i_forwards_the_bound_python_worker(monkeypatch) -> None:
    production_request = SimpleNamespace(public_production_destination="unused")
    request = SimpleNamespace(production_request=production_request)
    response = object()
    seal = object()
    observed = []

    def worker(*_args) -> None:
        return None

    monkeypatch.setattr(
        m336i_production, "validate_m336i_production_request", lambda _request: None
    )

    def run_m336h(_request, *, python_worker=None):
        observed.append(python_worker)
        return response

    monkeypatch.setattr(
        m336i_production, "run_m336h_compiler_aware_production", run_m336h
    )
    monkeypatch.setattr(
        m336i_production, "build_m336i_production_seal", lambda **_kwargs: seal
    )

    assert m336i_production.run_m336i_compiler_aware_production(
        request, python_worker=worker
    ) == (response, seal)
    assert observed == [worker]


def test_k5_quality_classifies_every_nested_python_check() -> None:
    source = (
        __import__("pathlib")
        .Path("scripts/m336k2_run_exact_quality.py")
        .read_text(encoding="utf-8")
    )
    assert "run_m336k5_bound_python_target(" in source
    assert '"unclassified_python_process_launch_count": 0' in source
    assert '"hermetic_python_invocation_count"' in source
    assert "_pytest_probe_arguments(" in source
    assert 'target_kind="SCRIPT"' in source
