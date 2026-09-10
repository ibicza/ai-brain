"""Hermetic command execution for the typed M-33.6k.2 route.

Private command plans carry absolute paths.  Public manifests contain only
content and path-identity hashes, so host paths never cross the publication
boundary.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import platform
import re
import site
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    M336J_REQUIRED_IMPORTS,
    compute_m336j_project_source_identity,
)
from ai_brain.stage3.acquisition.m336k2_controller import (
    M336K2StageReceipt,
    M336K2StageRequest,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_ROUTE_EVENTS,
    M336K2ExecutableBinding,
    M336K2ProtocolError,
    build_executable_binding,
    m336k2_minimal_environment,
    verify_executable_binding,
)

M336K2_COMMAND_EVENTS = M336K2_ROUTE_EVENTS[3:]
M336K2_REQUIRED_EXECUTABLE_ROLES = frozenset(
    {
        "git",
        "python",
        "java",
        "javac",
        "ssh",
        "scp",
        "tar",
        "powershell",
        "cmd",
    }
)


def m336k2_python_invocation_handle() -> Path:
    """Preserve a venv launcher/symlink while separately hashing its target."""

    return Path(sys.executable).absolute()


def build_m336k2_python_environment_manifest(
    *, repository: Path, python_executable: Path, git_executable: Path
) -> dict:
    """Capture the exact live local Python environment and project source identity."""

    root = repository.resolve(strict=True)
    python_handle = python_executable.absolute()
    python = python_handle.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    if m336k2_python_invocation_handle() != python_handle:
        raise M336K2ProtocolError("M336K2 environment capture used a different Python")
    if os.environ.get("PYTHONNOUSERSITE") != "1" or site.ENABLE_USER_SITE is not False:
        raise M336K2ProtocolError("M336K2 user-site loading is not disabled")
    if "torch" in sys.modules:
        raise M336K2ProtocolError("M336K2 environment capture imported torch")
    lock_path = root / "uv.lock"
    project_path = root / "pyproject.toml"
    locked = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    locked_versions: dict[str, set[str]] = {}
    for package in locked.get("package", ()):
        locked_versions.setdefault(_normalize_name(package["name"]), set()).add(
            str(package["version"])
        )
    packages = []
    for distribution in importlib.metadata.distributions():
        name = _normalize_name(distribution.metadata["Name"])
        version = distribution.version
        if name not in locked_versions or version not in locked_versions[name]:
            raise M336K2ProtocolError(
                "M336K2 installed distribution differs from uv.lock"
            )
        record = distribution.read_text("RECORD")
        file_manifest_hash = (
            bytes_hash(record.encode("utf-8"))
            if record is not None
            else content_hash(
                tuple(sorted(str(item) for item in distribution.files or ()))
            )
        )
        packages.append((name, version, file_manifest_hash))
    package_rows = tuple(sorted(packages))
    if not package_rows:
        raise M336K2ProtocolError("M336K2 Python package inventory is empty")
    source_identity = compute_m336j_project_source_identity(root, git)
    imports = []
    for module_name in M336J_REQUIRED_IMPORTS:
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__).resolve(strict=True)
        if module_name == "ai_brain" and not module_path.is_relative_to(root):
            raise M336K2ProtocolError("M336K2 project import escaped exact checkout")
        imports.append((module_name, bytes_hash(module_path.read_bytes())))
    if "torch" in sys.modules:
        raise M336K2ProtocolError("M336K2 import smoke loaded torch")
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_LOCAL_PYTHON_ENVIRONMENT_MANIFEST",
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "executable_content_hash": bytes_hash(python.read_bytes()),
        "package_count": len(package_rows),
        "package_manifest_hash": content_hash(package_rows),
        "project_source_identity_hash": source_identity,
        "project_import_smoke_hash": content_hash(
            {"project_source_identity": source_identity, "imports": tuple(imports)}
        ),
        "uv_lock_hash": bytes_hash(lock_path.read_bytes()),
        "pyproject_toml_hash": bytes_hash(project_path.read_bytes()),
        "user_site_loading_disabled": True,
        "torch_imported": False,
    }
    return {**body, "environment_manifest_hash": content_hash(body)}


def verify_m336k2_python_environment_manifest(
    expected: dict,
    *,
    repository: Path,
    python_executable: Path,
    git_executable: Path,
) -> None:
    actual = build_m336k2_python_environment_manifest(
        repository=repository,
        python_executable=python_executable,
        git_executable=git_executable,
    )
    if actual != expected:
        raise M336K2ProtocolError("M336K2 Python environment identity changed")


def _normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


@dataclass(frozen=True)
class M336K2CommandSpec:
    schema_version: int
    event: str
    executable: str
    arguments: tuple[str, ...]
    working_directory: str
    receipt_path: str
    receipt_hash_field: str
    expected_status: str
    specification_hash: str


@dataclass(frozen=True)
class M336K2PrivateExecutionPlan:
    schema_version: int
    route_run_id: str
    exact_f28_sha: str
    route_registry_hash: str
    commands: tuple[M336K2CommandSpec, ...]
    plan_hash: str


@dataclass(frozen=True)
class M336K2ExecutableDependencyManifest:
    schema_version: int
    contract_role: str
    bindings: tuple[M336K2ExecutableBinding, ...]
    python_invocation_handle_hash: str
    environment_identity_hash: str
    source_identity_hash: str
    command_renderer_hash: str
    minimal_environment_policy_hash: str
    missing_required_role_count: int
    manifest_hash: str


@dataclass(frozen=True)
class M336K2ExecutionCapsuleReceipt:
    schema_version: int
    contract_role: str
    route_registry_hash: str
    stage_worker_repository_path: str
    stage_worker_bytes_hash: str
    python_binding_hash: str
    command_contract_hash: str
    command_renderer_hash: str
    minimal_environment_policy_hash: str
    karina_public_execution_capsule_receipt_hash: str
    karina_executable_dependency_manifest_hash: str
    status: str
    receipt_hash: str


def command_renderer_identity() -> str:
    return content_hash(
        (
            "m336k2.command-renderer.v1",
            "argv-only",
            "absolute-executable",
            "shell-false",
            "no-profile",
            "no-login-shell",
            "minimal-environment",
        )
    )


def minimal_environment_policy_identity() -> str:
    return content_hash(tuple(sorted(m336k2_minimal_environment())))


def m336k2_native_command_contract_hash(
    *,
    repository: Path,
    dependency_manifest: M336K2ExecutableDependencyManifest,
) -> str:
    root = repository.resolve(strict=True)
    worker_relative = "scripts/m336k2_run_stage.py"
    worker = root.joinpath(*worker_relative.split("/")).resolve(strict=True)
    python_bindings = tuple(
        item for item in dependency_manifest.bindings if item.role == "python"
    )
    if len(python_bindings) != 1:
        raise M336K2ProtocolError("M336K2 Python executable binding changed")
    return content_hash(
        (
            "m336k2.native-stage-command-contract.v1",
            worker_relative,
            bytes_hash(worker.read_bytes()),
            python_bindings[0].binding_hash,
            tuple(
                (
                    event,
                    (
                        "-B",
                        "{REPOSITORY}/scripts/m336k2_run_stage.py",
                        "--request",
                        "{PRIVATE_STAGE_REQUEST}",
                        "--event",
                        event,
                        "--receipt",
                        f"{{PRIVATE_STAGE_RECEIPTS}}/{event}.json",
                    ),
                )
                for event in M336K2_COMMAND_EVENTS
            ),
        )
    )


def build_m336k2_execution_capsule_receipt(
    *,
    repository: Path,
    route_registry_hash: str,
    dependency_manifest: M336K2ExecutableDependencyManifest,
    karina_public_execution_capsule_receipt_hash: str,
    karina_executable_dependency_manifest_hash: str,
) -> M336K2ExecutionCapsuleReceipt:
    root = repository.resolve(strict=True)
    worker_relative = "scripts/m336k2_run_stage.py"
    worker = root.joinpath(*worker_relative.split("/")).resolve(strict=True)
    python_bindings = tuple(
        item for item in dependency_manifest.bindings if item.role == "python"
    )
    if (
        len(route_registry_hash) != 64
        or len(karina_public_execution_capsule_receipt_hash) != 64
        or len(karina_executable_dependency_manifest_hash) != 64
        or len(python_bindings) != 1
    ):
        raise M336K2ProtocolError("M336K2 execution capsule inputs changed")
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_NATIVE_EXECUTION_CAPSULE_RECEIPT",
        "route_registry_hash": route_registry_hash,
        "stage_worker_repository_path": worker_relative,
        "stage_worker_bytes_hash": bytes_hash(worker.read_bytes()),
        "python_binding_hash": python_bindings[0].binding_hash,
        "command_contract_hash": m336k2_native_command_contract_hash(
            repository=root,
            dependency_manifest=dependency_manifest,
        ),
        "command_renderer_hash": command_renderer_identity(),
        "minimal_environment_policy_hash": minimal_environment_policy_identity(),
        "karina_public_execution_capsule_receipt_hash": (
            karina_public_execution_capsule_receipt_hash
        ),
        "karina_executable_dependency_manifest_hash": (
            karina_executable_dependency_manifest_hash
        ),
        "status": "PASS",
    }
    return M336K2ExecutionCapsuleReceipt(**body, receipt_hash=content_hash(body))


def execution_capsule_receipt_from_dict(
    value: dict,
) -> M336K2ExecutionCapsuleReceipt:
    if set(value) != set(M336K2ExecutionCapsuleReceipt.__dataclass_fields__):
        raise M336K2ProtocolError("M336K2 execution capsule fields changed")
    receipt = M336K2ExecutionCapsuleReceipt(**value)
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    hashes = (
        receipt.route_registry_hash,
        receipt.stage_worker_bytes_hash,
        receipt.python_binding_hash,
        receipt.command_contract_hash,
        receipt.command_renderer_hash,
        receipt.minimal_environment_policy_hash,
        receipt.karina_public_execution_capsule_receipt_hash,
        receipt.karina_executable_dependency_manifest_hash,
    )
    if (
        receipt.contract_role != "M336K2_NATIVE_EXECUTION_CAPSULE_RECEIPT"
        or receipt.stage_worker_repository_path != "scripts/m336k2_run_stage.py"
        or receipt.status != "PASS"
        or any(len(item) != 64 for item in hashes)
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 execution capsule is invalid")
    return receipt


def build_m336k2_executable_dependency_manifest(
    *,
    executables: dict[str, tuple[Path, tuple[str, ...]]],
    python_invocation_handle: str,
    environment_identity_hash: str,
    source_identity_hash: str,
) -> M336K2ExecutableDependencyManifest:
    if (
        not python_invocation_handle
        or len(environment_identity_hash) != 64
        or len(source_identity_hash) != 64
    ):
        raise M336K2ProtocolError("M336K2 executable closure identity is invalid")
    normalized_roles = {item.casefold() for item in executables}
    missing = M336K2_REQUIRED_EXECUTABLE_ROLES - normalized_roles
    bindings = tuple(
        build_executable_binding(
            executable,
            role=role,
            version_arguments=version_arguments,
        )
        for role, (executable, version_arguments) in sorted(executables.items())
    )
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_HERMETIC_EXECUTABLE_DEPENDENCY_MANIFEST",
        "bindings": bindings,
        "python_invocation_handle_hash": content_hash(python_invocation_handle),
        "environment_identity_hash": environment_identity_hash,
        "source_identity_hash": source_identity_hash,
        "command_renderer_hash": command_renderer_identity(),
        "minimal_environment_policy_hash": minimal_environment_policy_identity(),
        "missing_required_role_count": len(missing),
    }
    result = M336K2ExecutableDependencyManifest(
        **body, manifest_hash=content_hash(body)
    )
    if missing:
        raise M336K2ProtocolError(
            f"M336K2 executable closure is incomplete: {len(missing)} missing"
        )
    return result


def executable_dependency_manifest_from_dict(
    value: dict,
) -> M336K2ExecutableDependencyManifest:
    if set(value) != set(M336K2ExecutableDependencyManifest.__dataclass_fields__):
        raise M336K2ProtocolError("M336K2 executable manifest fields changed")
    parsed = M336K2ExecutableDependencyManifest(
        **{
            **value,
            "bindings": tuple(
                M336K2ExecutableBinding(
                    **{
                        **item,
                        "version_arguments": tuple(item["version_arguments"]),
                    }
                )
                for item in value["bindings"]
            ),
        }
    )
    body = asdict(parsed)
    claimed = body.pop("manifest_hash")
    if (
        parsed.contract_role != "M336K2_HERMETIC_EXECUTABLE_DEPENDENCY_MANIFEST"
        or parsed.missing_required_role_count != 0
        or parsed.command_renderer_hash != command_renderer_identity()
        or parsed.minimal_environment_policy_hash
        != minimal_environment_policy_identity()
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 executable manifest is invalid")
    return parsed


def verify_m336k2_executable_handles(
    manifest: M336K2ExecutableDependencyManifest,
    handles: dict[str, Path],
) -> None:
    if set(handles) != M336K2_REQUIRED_EXECUTABLE_ROLES:
        raise M336K2ProtocolError("M336K2 executable handle roles changed")
    bindings = {item.role: item for item in manifest.bindings}
    if M336K2_REQUIRED_EXECUTABLE_ROLES - set(bindings):
        raise M336K2ProtocolError("M336K2 executable bindings are incomplete")
    for role, handle in handles.items():
        binding = bindings[role]
        verify_executable_binding(handle, binding)


def build_m336k2_private_execution_plan(
    *,
    route_run_id: str,
    exact_f28_sha: str,
    route_registry_hash: str,
    commands: tuple[M336K2CommandSpec, ...],
) -> M336K2PrivateExecutionPlan:
    if tuple(item.event for item in commands) != M336K2_COMMAND_EVENTS:
        raise M336K2ProtocolError("M336K2 private command plan order changed")
    if len({item.event for item in commands}) != len(commands):
        raise M336K2ProtocolError("M336K2 private command is duplicated")
    for item in commands:
        _verify_command_spec(item)
    body = {
        "schema_version": 1,
        "route_run_id": route_run_id,
        "exact_f28_sha": exact_f28_sha,
        "route_registry_hash": route_registry_hash,
        "commands": commands,
    }
    return M336K2PrivateExecutionPlan(**body, plan_hash=content_hash(body))


def build_m336k2_native_execution_plan(
    *,
    repository: Path,
    python_executable: Path,
    stage_request: Path,
    stage_receipt_root: Path,
    route_run_id: str,
    exact_f28_sha: str,
    route_registry_hash: str,
    dependency_manifest: M336K2ExecutableDependencyManifest,
    capsule: M336K2ExecutionCapsuleReceipt,
) -> M336K2PrivateExecutionPlan:
    root = repository.resolve(strict=True)
    python = python_executable.resolve(strict=True)
    request = stage_request.resolve(strict=True)
    receipts = stage_receipt_root.resolve(strict=False)
    expected_contract = m336k2_native_command_contract_hash(
        repository=root,
        dependency_manifest=dependency_manifest,
    )
    python_binding = tuple(
        item for item in dependency_manifest.bindings if item.role == "python"
    )
    if (
        len(python_binding) != 1
        or bytes_hash(python.read_bytes()) != python_binding[0].file_sha256
        or content_hash(python.as_posix()) != python_binding[0].path_identity_hash
        or capsule.route_registry_hash != route_registry_hash
        or capsule.stage_worker_bytes_hash
        != bytes_hash((root / capsule.stage_worker_repository_path).read_bytes())
        or capsule.python_binding_hash != python_binding[0].binding_hash
        or capsule.command_contract_hash != expected_contract
        or capsule.command_renderer_hash != command_renderer_identity()
        or capsule.minimal_environment_policy_hash
        != minimal_environment_policy_identity()
    ):
        raise M336K2ProtocolError("M336K2 native command contract changed")
    worker = root / capsule.stage_worker_repository_path
    commands = tuple(
        build_command_spec(
            event=event,
            executable=python,
            arguments=(
                "-B",
                str(worker),
                "--request",
                str(request),
                "--event",
                event,
                "--receipt",
                str(receipts / f"{event}.json"),
            ),
            working_directory=root,
            receipt_path=receipts / f"{event}.json",
            receipt_hash_field="receipt_hash",
            expected_status="PASS",
        )
        for event in M336K2_COMMAND_EVENTS
    )
    return build_m336k2_private_execution_plan(
        route_run_id=route_run_id,
        exact_f28_sha=exact_f28_sha,
        route_registry_hash=route_registry_hash,
        commands=commands,
    )


class M336K2HermeticCommandWorker:
    """Execute each frozen command exactly once and verify its typed receipt."""

    def __init__(self, plan: M336K2PrivateExecutionPlan) -> None:
        self._plan = plan
        self._commands = {item.event: item for item in plan.commands}
        self._completed: list[str] = []

    def __call__(self, request: M336K2StageRequest) -> M336K2StageReceipt:
        expected = M336K2_COMMAND_EVENTS[len(self._completed)]
        if request.event != expected or request.event in self._completed:
            raise M336K2ProtocolError("M336K2 command worker order changed")
        if (
            request.route_run_id != self._plan.route_run_id
            or request.exact_f28_sha != self._plan.exact_f28_sha
        ):
            raise M336K2ProtocolError("M336K2 command worker context changed")
        command = self._commands[request.event]
        receipt_path = Path(command.receipt_path)
        if receipt_path.exists():
            raise M336K2ProtocolError("M336K2 command receipt destination is stale")
        environment = m336k2_minimal_environment()
        source_root = Path(command.working_directory) / "src"
        if source_root.is_dir():
            environment.update(
                {
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONPATH": str(source_root.resolve(strict=True)),
                    "PYTHONUTF8": "1",
                }
            )
        result = subprocess.run(
            (command.executable, *command.arguments),
            cwd=command.working_directory,
            check=False,
            capture_output=True,
            env=environment,
        )
        if result.returncode != 0:
            raise M336K2ProtocolError(f"M336K2 stage command failed: {request.event}")
        receipt = _load_receipt(receipt_path)
        body = dict(receipt)
        claimed = body.pop(command.receipt_hash_field, None)
        if (
            not isinstance(claimed, str)
            or len(claimed) != 64
            or content_hash(body) != claimed
            or receipt.get("status") != command.expected_status
        ):
            raise M336K2ProtocolError(
                f"M336K2 stage command receipt failed: {request.event}"
            )
        operation_hash = content_hash(
            (
                command.specification_hash,
                claimed,
                bytes_hash(receipt_path.read_bytes()),
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
        self._completed.append(request.event)
        return M336K2StageReceipt(
            **receipt_body, receipt_hash=content_hash(receipt_body)
        )


def build_command_spec(
    *,
    event: str,
    executable: Path,
    arguments: tuple[str, ...],
    working_directory: Path,
    receipt_path: Path,
    receipt_hash_field: str,
    expected_status: str,
) -> M336K2CommandSpec:
    body = {
        "schema_version": 1,
        "event": event,
        "executable": str(executable.resolve(strict=True)),
        "arguments": arguments,
        "working_directory": str(working_directory.resolve(strict=True)),
        "receipt_path": str(receipt_path.resolve(strict=False)),
        "receipt_hash_field": receipt_hash_field,
        "expected_status": expected_status,
    }
    result = M336K2CommandSpec(**body, specification_hash=content_hash(body))
    _verify_command_spec(result)
    return result


def _verify_command_spec(spec: M336K2CommandSpec) -> None:
    body = asdict(spec)
    claimed = body.pop("specification_hash")
    executable = Path(spec.executable)
    working_directory = Path(spec.working_directory)
    receipt_path = Path(spec.receipt_path)
    if (
        spec.schema_version != 1
        or spec.event not in M336K2_COMMAND_EVENTS
        or not executable.is_absolute()
        or not executable.resolve(strict=True).is_file()
        or not working_directory.is_absolute()
        or not working_directory.resolve(strict=True).is_dir()
        or not receipt_path.is_absolute()
        or spec.receipt_hash_field == ""
        or spec.expected_status == ""
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 command specification is invalid")
    forbidden = {"git", "uv", "python", "python3", "java", "javac", "ssh", "scp", "tar"}
    for argument in spec.arguments:
        if argument.casefold() in forbidden:
            raise M336K2ProtocolError("M336K2 bare executable argument is forbidden")


def _load_receipt(path: Path) -> dict:
    try:
        value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 command receipt is invalid JSON") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 command receipt is not an object")
    return value
