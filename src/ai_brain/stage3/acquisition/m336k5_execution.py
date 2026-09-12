"""M336K5 stage execution through the one hermetic Python launch path."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336k2_controller import (
    M336K2StageReceipt,
    M336K2StageRequest,
)
from ai_brain.stage3.acquisition.m336k2_execution import (
    M336K2_COMMAND_EVENTS,
    M336K2PrivateExecutionPlan,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_resources import M336K5ResourceMonitor
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_python_invocation,
    run_m336k5_python_invocation,
    startup_receipt_from_path,
    write_m336k5_python_invocation_plan,
)


@dataclass(frozen=True)
class M336K5StageStartupBinding:
    event: str
    invocation_plan_hash: str
    startup_receipt_hash: str
    native_receipt_hash: str
    binding_hash: str


class M336K5HermeticCommandWorker:
    """Execute every native stage with -s -B and the stdlib bootstrap."""

    def __init__(
        self,
        plan: M336K2PrivateExecutionPlan,
        *,
        repository: Path,
        git_executable: Path,
        python_executable: Path,
        powershell_executable: Path,
        bootstrap_script: Path,
        expected_startup_receipt_hash: str,
        resource_monitor: M336K5ResourceMonitor | None = None,
    ) -> None:
        self._plan = plan
        self._commands = {item.event: item for item in plan.commands}
        self._completed: list[str] = []
        self._repository = repository.resolve(strict=True)
        self._git = git_executable.resolve(strict=True)
        self._python = python_executable.absolute()
        self._powershell = powershell_executable.resolve(strict=True)
        self._bootstrap = bootstrap_script.resolve(strict=True)
        self._expected_startup = expected_startup_receipt_hash
        self._resource_monitor = resource_monitor
        self._bindings: list[M336K5StageStartupBinding] = []
        if len(expected_startup_receipt_hash) != 64:
            raise M336K2ProtocolError("M336K5 expected startup receipt is invalid")

    @property
    def bindings(self) -> tuple[M336K5StageStartupBinding, ...]:
        return tuple(self._bindings)

    def __call__(self, request: M336K2StageRequest) -> M336K2StageReceipt:
        expected = M336K2_COMMAND_EVENTS[len(self._completed)]
        if request.event != expected or request.event in self._completed:
            raise M336K2ProtocolError("M336K5 command worker order changed")
        if (
            request.route_run_id != self._plan.route_run_id
            or request.exact_f28_sha != self._plan.exact_f28_sha
        ):
            raise M336K2ProtocolError("M336K5 command worker context changed")
        command = self._commands[request.event]
        arguments = command.arguments
        if (
            len(arguments) < 2
            or arguments[0] != "-B"
            or Path(arguments[1]).resolve(strict=True)
            != self._repository / "scripts" / "m336k2_run_stage.py"
        ):
            raise M336K2ProtocolError("M336K5 native stage command shape changed")
        native_receipt = Path(command.receipt_path).resolve(strict=False)
        root = native_receipt.parent
        startup_receipt = root / f"{request.event}.startup.json"
        invocation_plan_path = root / f"{request.event}.invocation-plan.json"
        stdout_path = root / f"{request.event}.stdout.log"
        stderr_path = root / f"{request.event}.stderr.log"
        if any(
            path.exists()
            for path in (
                native_receipt,
                startup_receipt,
                invocation_plan_path,
                stdout_path,
                stderr_path,
            )
        ):
            raise M336K2ProtocolError("M336K5 command destination is stale")
        if self._resource_monitor is not None:
            self._resource_monitor.sample(f"{request.event}_BEFORE")
        invocation = build_m336k5_python_invocation(
            platform_role="WINDOWS",
            process_role="NATIVE_STAGE_WORKER",
            python_executable=self._python,
            git_executable=self._git,
            powershell_executable=self._powershell,
            repository=self._repository,
            working_directory=Path(command.working_directory),
            bootstrap_script=self._bootstrap,
            target=Path(arguments[1]),
            execute_arguments=tuple(arguments[2:]),
            validate_arguments=tuple(arguments[2:]),
            execute_startup_receipt=startup_receipt,
            validate_startup_receipt=startup_receipt.with_suffix(".validate.json"),
        )
        write_m336k5_python_invocation_plan(invocation, invocation_plan_path)
        result = run_m336k5_python_invocation(
            plan_path=invocation_plan_path, operation="execute"
        )
        root.mkdir(parents=True, exist_ok=True)
        stdout_path.write_bytes(result.stdout)
        stderr_path.write_bytes(result.stderr)
        if result.returncode != 0:
            raise M336K2ProtocolError(f"M336K5 stage command failed: {request.event}")
        startup = startup_receipt_from_path(startup_receipt)
        if startup.receipt_hash != self._expected_startup:
            raise M336K2ProtocolError(
                "M336K5 worker startup receipt differs from pre-ledger startup"
            )
        try:
            native = json.loads(native_receipt.resolve(strict=True).read_text("utf-8"))
        except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise M336K2ProtocolError(
                "M336K5 native stage receipt is invalid"
            ) from error
        body = dict(native) if isinstance(native, dict) else {}
        claimed = body.pop(command.receipt_hash_field, None)
        if (
            not isinstance(claimed, str)
            or content_hash(body) != claimed
            or native.get("status") != command.expected_status
            or native.get("startup_receipt_hash") != startup.receipt_hash
        ):
            raise M336K2ProtocolError(
                f"M336K5 stage command receipt failed: {request.event}"
            )
        operation_hash = content_hash(
            (
                command.specification_hash,
                invocation.invocation_plan_hash,
                startup.receipt_hash,
                claimed,
                bytes_hash(native_receipt.read_bytes()),
                result.returncode,
            )
        )
        receipt_body = {
            "schema_version": 1,
            "event": request.event,
            "request_hash": request.request_hash,
            "operation_hash": operation_hash,
            "status": "PASS",
        }
        binding_body = {
            "event": request.event,
            "invocation_plan_hash": invocation.invocation_plan_hash,
            "startup_receipt_hash": startup.receipt_hash,
            "native_receipt_hash": claimed,
        }
        self._bindings.append(
            M336K5StageStartupBinding(
                **binding_body, binding_hash=content_hash(binding_body)
            )
        )
        self._completed.append(request.event)
        if self._resource_monitor is not None:
            self._resource_monitor.sample(f"{request.event}_AFTER")
        return M336K2StageReceipt(
            **receipt_body, receipt_hash=content_hash(receipt_body)
        )
