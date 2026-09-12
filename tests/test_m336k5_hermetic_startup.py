from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5_FORBIDDEN_ENVIRONMENT,
    build_m336k5_python_invocation,
    build_m336k5_python_startup_policy,
    build_m336k5_sanitized_environment,
    run_m336k5_python_invocation,
    startup_receipt_from_path,
    write_m336k5_python_invocation_plan,
)

ROOT = Path(__file__).resolve().parents[1]


def _powershell() -> Path:
    value = (
        shutil.which("pwsh.exe")
        or shutil.which("pwsh")
        or shutil.which("powershell.exe")
        or shutil.which("powershell")
    )
    if value is None:
        pytest.skip("Windows PowerShell is unavailable")
    return Path(value).resolve(strict=True)


def _git() -> Path:
    value = shutil.which("git.exe") or shutil.which("git")
    if value is None:
        pytest.skip("Git is unavailable")
    return Path(value).resolve(strict=True)


def test_startup_policy_is_fail_closed() -> None:
    policy = build_m336k5_python_startup_policy()
    assert policy.required_interpreter_arguments == ("-s", "-B")
    assert policy.caller_environment_map_allowed is False
    assert policy.profile_startup_allowed is False
    assert policy.login_shell_allowed is False
    environment = build_m336k5_sanitized_environment(
        platform_role="WINDOWS",
        parent_environment={
            **os.environ,
            "PYTHONPATH": "hostile",
            "PYTHONHOME": "hostile",
            "PYTHONNOUSERSITE": "0",
        },
    )
    values = dict(environment.variables)
    assert values["PYTHONNOUSERSITE"] == "1"
    assert values["PATH"] == ""
    assert not set(M336K5_FORBIDDEN_ENVIRONMENT) & set(values)


@pytest.mark.parametrize(
    "case",
    (
        "NO_USER_SITE_ABSENT",
        "NO_USER_SITE_ZERO",
        "NO_USER_SITE_FALSE",
        "FAKE_USER_BASE",
        "PYTHONPATH_SHADOW_PACKAGE",
        "WRONG_PYTHONHOME",
        "PYTHONSTARTUP_MARKER",
        "USER_SITE_FAKE_AI_BRAIN",
        "USER_SITE_FAKE_DEPENDENCIES",
        "SITECUSTOMIZE_MARKER",
        "USERCUSTOMIZE_MARKER",
        "EMPTY_PATH",
        "HOSTILE_PATH",
        "POWERSHELL_PROFILE_UNAVAILABLE",
        "HOME_UNAVAILABLE",
        "SHADOW_CURRENT_DIRECTORY",
    ),
)
def test_external_launcher_sanitizes_hostile_parent(tmp_path: Path, case: str) -> None:
    marker = tmp_path / "startup-marker-executed"
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    marker_code = f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')\n"
    for name in (
        "sitecustomize.py",
        "usercustomize.py",
        "ai_brain.py",
        "numpy.py",
        "tokenizers.py",
        "torch.py",
        "tree_sitter.py",
        "tree_sitter_java.py",
    ):
        (shadow / name).write_text(marker_code, encoding="utf-8")
    startup = tmp_path / "python-startup.py"
    startup.write_text(marker_code, encoding="utf-8")
    parent = dict(os.environ)
    working_directory = tmp_path
    if case == "NO_USER_SITE_ABSENT":
        parent.pop("PYTHONNOUSERSITE", None)
    elif case == "NO_USER_SITE_ZERO":
        parent["PYTHONNOUSERSITE"] = "0"
    elif case == "NO_USER_SITE_FALSE":
        parent["PYTHONNOUSERSITE"] = "false"
    elif case in {
        "FAKE_USER_BASE",
        "USER_SITE_FAKE_AI_BRAIN",
        "USER_SITE_FAKE_DEPENDENCIES",
    }:
        parent["PYTHONUSERBASE"] = str(shadow)
        parent["PYTHONPATH"] = str(shadow)
    elif case == "PYTHONPATH_SHADOW_PACKAGE":
        parent["PYTHONPATH"] = str(shadow)
    elif case == "WRONG_PYTHONHOME":
        parent["PYTHONHOME"] = str(shadow)
    elif case == "PYTHONSTARTUP_MARKER":
        parent["PYTHONSTARTUP"] = str(startup)
    elif case in {"SITECUSTOMIZE_MARKER", "USERCUSTOMIZE_MARKER"}:
        parent["PYTHONPATH"] = str(shadow)
    elif case == "EMPTY_PATH":
        parent["PATH"] = ""
    elif case == "HOSTILE_PATH":
        parent["PATH"] = str(shadow)
    elif case == "POWERSHELL_PROFILE_UNAVAILABLE":
        parent["USERPROFILE"] = str(tmp_path / "missing-profile")
        parent["PSMODULEPATH"] = str(shadow)
    elif case == "HOME_UNAVAILABLE":
        parent.pop("HOME", None)
        parent.pop("USERPROFILE", None)
    elif case == "SHADOW_CURRENT_DIRECTORY":
        working_directory = shadow
    else:  # pragma: no cover - parameter list is closed above
        raise AssertionError(case)
    plan = build_m336k5_python_invocation(
        platform_role="WINDOWS",
        process_role="TEST",
        python_executable=Path(sys.executable),
        git_executable=_git(),
        powershell_executable=_powershell(),
        repository=ROOT,
        working_directory=working_directory,
        bootstrap_script=ROOT / "scripts" / "m336k5_python_bootstrap.py",
        target=ROOT / "scripts" / "m336k5_startup_probe.py",
        execute_arguments=("--output", str(tmp_path / "probe.json")),
        validate_arguments=("--output", str(tmp_path / "unused-probe.json")),
        execute_startup_receipt=tmp_path / "startup-execute.json",
        validate_startup_receipt=tmp_path / "startup-validate.json",
        parent_environment=parent,
    )
    plan_path = tmp_path / "plan.json"
    write_m336k5_python_invocation_plan(plan, plan_path)
    result = run_m336k5_python_invocation(plan_path=plan_path, operation="execute")
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    startup = startup_receipt_from_path(tmp_path / "startup-execute.json")
    probe = json.loads((tmp_path / "probe.json").read_text(encoding="utf-8"))
    assert startup.status == "PASS"
    assert probe["startup_receipt_hash"] == startup.receipt_hash
    assert probe["python_no_user_site_environment"] == "1"
    assert probe["python_no_user_site_flag"] == 1
    assert probe["site_enable_user_site"] is False
    assert probe["user_site_path_membership"] is False
    assert probe["python_path_present"] is False
    assert probe["python_home_present"] is False
    assert probe["python_user_base_present"] is False
    assert probe["python_startup_present"] is False
    assert probe["torch_imported"] is False
    assert not marker.exists()
