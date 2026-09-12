from __future__ import annotations

from types import SimpleNamespace

from ai_brain.stage3.acquisition import m336i_production
from ai_brain.stage3.acquisition.m336k5_startup import M336K5_PROCESS_ROLES
from scripts import m336k2_run_exact_quality, m336k5_quality_probe


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


def test_k5_quality_uses_fresh_output_specific_temp_root(tmp_path, monkeypatch) -> None:
    logs = tmp_path / "quality-logs"
    logs.mkdir()
    observed_cleanup_roots = []

    def hermetic_check(**kwargs):
        cleanup_root = kwargs.get("cleanup_root")
        if cleanup_root is not None:
            observed_cleanup_roots.append(cleanup_root)
        return {"name": kwargs["name"], "exit_code": 0}

    monkeypatch.setattr(
        m336k2_run_exact_quality, "_hermetic_python_check", hermetic_check
    )
    monkeypatch.setattr(
        m336k2_run_exact_quality,
        "_check",
        lambda name, *_args, **_kwargs: {"name": name, "exit_code": 0},
    )
    repository = tmp_path / "repository"
    repository.mkdir()
    checks = m336k2_run_exact_quality._run_hermetic_checks(
        platform_role="WINDOWS",
        repository=repository,
        logs=logs,
        invocation_root=tmp_path / "invocations",
        python=tmp_path / "python",
        git=tmp_path / "git",
        powershell=tmp_path / "pwsh",
        javac=tmp_path / "javac",
        expected_startup_receipt_hash="a" * 64,
        targeted=("tests/test_targeted.py",),
        stage3_java_tests=("tests/test_stage3.py",),
        executable_directories=(),
    )

    expected_root = tmp_path / "quality-logs-temp"
    assert len(checks) == 10
    assert observed_cleanup_roots
    assert all(path.is_relative_to(expected_root) for path in observed_cleanup_roots)
    assert not expected_root.exists()


def test_k5_quality_probe_binds_subprocess_import_root_after_bootstrap(
    tmp_path, monkeypatch
) -> None:
    repository = tmp_path / "repository"
    source = repository / "src"
    source.mkdir(parents=True)
    handles = []
    for name in ("git", "javac", "python", "pwsh"):
        handle = tmp_path / name
        handle.write_bytes(b"")
        handles.append(handle)
    args = SimpleNamespace(
        git_executable=handles[0],
        javac_executable=handles[1],
        python_executable=handles[2],
        powershell_executable=handles[3],
    )
    monkeypatch.chdir(repository)
    monkeypatch.delenv("PYTHONPATH", raising=False)

    m336k5_quality_probe._bind_exact_tool_path(args)

    assert __import__("os").environ["PYTHONPATH"] == str(source.resolve())
