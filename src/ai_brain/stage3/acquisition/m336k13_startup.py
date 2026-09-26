"""Controller-domain launcher for exact M336K13 plan attestation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5_OPERATION_MODES,
    M336K5PythonInvocationPlan,
    _powershell_boot_environment,
    validate_m336k5_python_invocation,
)


def run_m336k13_python_invocation(
    *,
    plan_path: Path,
    operation: str,
    actual_launcher_plan_receipt: Path,
    execution_scope: str,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    import json

    value = json.loads(plan_path.resolve(strict=True).read_text(encoding="utf-8"))
    plan = M336K5PythonInvocationPlan.from_dict(value)
    validate_m336k5_python_invocation(plan)
    mode = operation.casefold()
    if mode not in M336K5_OPERATION_MODES:
        raise M336K2ProtocolError("M336K13 invocation operation is invalid")
    bootstrap_arguments = (
        "--invocation-plan",
        str(plan_path.resolve(strict=True)),
        "--operation",
        mode,
        "--actual-launcher-plan-receipt",
        str(actual_launcher_plan_receipt.resolve(strict=False)),
        "--execution-scope",
        execution_scope,
    )
    if plan.platform_role == "KARINA":
        command = (
            str(Path(plan.python_executable).absolute()),
            "-s",
            "-B",
            str(Path(plan.bootstrap_script).resolve(strict=True)),
            *bootstrap_arguments,
        )
        environment = dict(plan.sanitized_environment.variables)
    elif plan.platform_role == "WINDOWS" and plan.powershell_executable is not None:
        launcher = Path(plan.repository) / "scripts" / "m336k5_launch_python.ps1"
        command = (
            str(Path(plan.powershell_executable).resolve(strict=True)),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher.resolve(strict=True)),
            "-InvocationPlan",
            str(plan_path.resolve(strict=True)),
            "-Operation",
            mode,
            "-ActualLauncherPlanReceipt",
            str(actual_launcher_plan_receipt.resolve(strict=False)),
            "-ExecutionScope",
            execution_scope,
        )
        environment = _powershell_boot_environment(plan.sanitized_environment)
    else:
        raise M336K2ProtocolError("M336K13 local runner platform is invalid")
    return subprocess.run(
        command,
        cwd=Path(plan.working_directory).resolve(strict=True),
        check=False,
        capture_output=capture_output,
        env=environment,
    )
