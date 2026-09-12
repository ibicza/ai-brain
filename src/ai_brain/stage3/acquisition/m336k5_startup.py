"""Hermetic process-start contracts for the M-33.6k.5 final route."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Self

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    KarinaPrivateExecutionCapsule,
    KarinaPublicExecutionCapsuleReceipt,
    KarinaRemoteCommandPlan,
    KarinaRemoteTokenClass,
    build_remote_command_plan,
    compute_m336j_project_source_identity,
    m336k5_karina_environment,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError

M336K5_STARTUP_POLICY_ID = "m336k5.hermetic-python-startup.v1"
M336K5_FIXED_ENVIRONMENT = (
    ("GIT_CONFIG_NOSYSTEM", "1"),
    ("GIT_TERMINAL_PROMPT", "0"),
    ("PIP_NO_INDEX", "1"),
    ("PYTHONDONTWRITEBYTECODE", "1"),
    ("PYTHONHASHSEED", "0"),
    ("PYTHONIOENCODING", "utf-8"),
    ("PYTHONNOUSERSITE", "1"),
    ("PYTHONUTF8", "1"),
    ("TZ", "UTC"),
    ("UV_OFFLINE", "1"),
)
M336K5_FORBIDDEN_ENVIRONMENT = (
    "PYTHONBREAKPOINT",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)
M336K5_WINDOWS_INHERITED_ENVIRONMENT = (
    "COMSPEC",
    "PATHEXT",
    "PROGRAMDATA",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "WINDIR",
)
M336K5_KARINA_FIXED_ENVIRONMENT = (
    ("LC_ALL", "C.UTF-8"),
    ("PATH", "/usr/bin:/bin"),
)
M336K5_WINDOWS_FIXED_ENVIRONMENT = (("PATH", ""),)
M336K5_REQUIRED_INTERPRETER_ARGUMENTS = ("-s", "-B")
M336K5_PROCESS_ROLES = frozenset(
    {
        "FINAL_CONTROLLER",
        "VALIDATE_ONLY",
        "NATIVE_STAGE_WORKER",
        "GOLDEN_AUTHOR",
        "EXACT_QUALITY",
        "KARINA_HOST_PREFLIGHT",
        "KARINA_CAPSULE_METADATA",
        "KARINA_STORAGE_PREFLIGHT",
        "KARINA_PRODUCTION",
        "KARINA_REPLAY",
        "KARINA_EVALUATOR",
        "KARINA_RUNTIME",
        "TEST",
        "BUILD_HELPER",
        "DISPOSABLE_CONTROLLER",
    }
)
M336K5_OPERATION_MODES = frozenset({"validate", "execute"})
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class M336K5PythonStartupPolicy:
    schema_version: int
    contract_role: str
    policy_id: str
    required_interpreter_arguments: tuple[str, ...]
    fixed_environment: tuple[tuple[str, str], ...]
    forbidden_environment_names: tuple[str, ...]
    windows_inherited_environment_names: tuple[str, ...]
    windows_fixed_environment: tuple[tuple[str, str], ...]
    karina_fixed_environment: tuple[tuple[str, str], ...]
    project_import_mechanism: str
    user_site_effective_state_required: bool
    caller_environment_map_allowed: bool
    profile_startup_allowed: bool
    login_shell_allowed: bool
    torch_at_startup_allowed: bool
    policy_hash: str

    def canonical_object(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Self:
        expected = set(cls.__dataclass_fields__)
        if type(value) is not dict or set(value) != expected:
            raise M336K2ProtocolError("M336K5 startup policy fields changed")
        result = cls(
            **{
                **value,
                "required_interpreter_arguments": tuple(
                    value["required_interpreter_arguments"]
                ),
                "fixed_environment": _pairs(value["fixed_environment"]),
                "forbidden_environment_names": tuple(
                    value["forbidden_environment_names"]
                ),
                "windows_inherited_environment_names": tuple(
                    value["windows_inherited_environment_names"]
                ),
                "windows_fixed_environment": _pairs(value["windows_fixed_environment"]),
                "karina_fixed_environment": _pairs(value["karina_fixed_environment"]),
            }
        )
        verify_m336k5_python_startup_policy(result)
        return result


@dataclass(frozen=True)
class M336K5SanitizedEnvironment:
    schema_version: int
    contract_role: str
    platform_role: str
    inherited_names: tuple[str, ...]
    variables: tuple[tuple[str, str], ...]
    removed_names: tuple[str, ...]
    startup_policy_hash: str
    environment_hash: str

    def canonical_object(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K5 sanitized environment fields changed")
        result = cls(
            **{
                **value,
                "inherited_names": tuple(value["inherited_names"]),
                "variables": _pairs(value["variables"]),
                "removed_names": tuple(value["removed_names"]),
            }
        )
        _verify_sanitized_environment(result)
        return result


@dataclass(frozen=True)
class M336K5PythonInvocationPlan:
    schema_version: int
    contract_role: str
    platform_role: str
    process_role: str
    python_executable: str
    git_executable: str
    powershell_executable: str | None
    repository: str
    working_directory: str
    bootstrap_script: str
    target_kind: str
    target: str
    execute_arguments: tuple[str, ...]
    validate_arguments: tuple[str, ...]
    execute_startup_receipt: str
    validate_startup_receipt: str
    expected_python_implementation: str
    expected_python_version: str
    expected_environment_prefix: str
    expected_python_executable_hash: str
    expected_bootstrap_source_hash: str
    expected_target_source_hash: str
    expected_project_source_identity: str
    startup_policy: M336K5PythonStartupPolicy
    sanitized_environment: M336K5SanitizedEnvironment
    invocation_plan_hash: str

    def _body(self) -> dict:
        value = asdict(self)
        value.pop("invocation_plan_hash")
        return value

    def canonical_object(self) -> dict:
        return {**self._body(), "invocation_plan_hash": self.invocation_plan_hash}

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K5 invocation plan fields changed")
        result = cls(
            **{
                **value,
                "execute_arguments": tuple(value["execute_arguments"]),
                "validate_arguments": tuple(value["validate_arguments"]),
                "startup_policy": M336K5PythonStartupPolicy.from_dict(
                    value["startup_policy"]
                ),
                "sanitized_environment": M336K5SanitizedEnvironment.from_dict(
                    value["sanitized_environment"]
                ),
            }
        )
        validate_m336k5_python_invocation(result, verify_local_files=False)
        return result


@dataclass(frozen=True)
class M336K5PythonStartupReceipt:
    schema_version: int
    contract_role: str
    startup_policy_hash: str
    interpreter_binding_hash: str
    invocation_argument_hash: str
    sanitized_environment_hash: str
    project_source_identity: str
    user_site_disabled_result: bool
    python_no_user_site: int
    site_enable_user_site: bool
    user_site_path_membership: bool
    unsafe_path_count: int
    unexpected_startup_module_count: int
    torch_imported: bool
    status: str
    receipt_hash: str

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K5 startup receipt fields changed")
        result = cls(**value)
        body = asdict(result)
        claimed = body.pop("receipt_hash")
        if (
            content_hash(body) != claimed
            or result.status != "PASS"
            or not result.user_site_disabled_result
            or result.python_no_user_site != 1
            or result.site_enable_user_site
            or result.user_site_path_membership
            or result.unsafe_path_count
            or result.unexpected_startup_module_count
            or result.torch_imported
        ):
            raise M336K2ProtocolError("M336K5 startup receipt is invalid")
        return result


def build_m336k5_python_startup_policy() -> M336K5PythonStartupPolicy:
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_HERMETIC_PYTHON_STARTUP_POLICY",
        "policy_id": M336K5_STARTUP_POLICY_ID,
        "required_interpreter_arguments": M336K5_REQUIRED_INTERPRETER_ARGUMENTS,
        "fixed_environment": M336K5_FIXED_ENVIRONMENT,
        "forbidden_environment_names": M336K5_FORBIDDEN_ENVIRONMENT,
        "windows_inherited_environment_names": M336K5_WINDOWS_INHERITED_ENVIRONMENT,
        "windows_fixed_environment": M336K5_WINDOWS_FIXED_ENVIRONMENT,
        "karina_fixed_environment": M336K5_KARINA_FIXED_ENVIRONMENT,
        "project_import_mechanism": (
            "BOOTSTRAP_INSERT_EXACT_REPOSITORY_SRC_AFTER_STDLIB_VERIFICATION"
        ),
        "user_site_effective_state_required": True,
        "caller_environment_map_allowed": False,
        "profile_startup_allowed": False,
        "login_shell_allowed": False,
        "torch_at_startup_allowed": False,
    }
    result = M336K5PythonStartupPolicy(**body, policy_hash=content_hash(body))
    verify_m336k5_python_startup_policy(result)
    return result


def verify_m336k5_python_startup_policy(policy: M336K5PythonStartupPolicy) -> None:
    body = asdict(policy)
    claimed = body.pop("policy_hash")
    if (
        policy.schema_version != 1
        or policy.contract_role != "M336K5_HERMETIC_PYTHON_STARTUP_POLICY"
        or policy.policy_id != M336K5_STARTUP_POLICY_ID
        or policy.required_interpreter_arguments
        != M336K5_REQUIRED_INTERPRETER_ARGUMENTS
        or policy.fixed_environment != M336K5_FIXED_ENVIRONMENT
        or policy.forbidden_environment_names != M336K5_FORBIDDEN_ENVIRONMENT
        or policy.windows_inherited_environment_names
        != M336K5_WINDOWS_INHERITED_ENVIRONMENT
        or policy.windows_fixed_environment != M336K5_WINDOWS_FIXED_ENVIRONMENT
        or policy.karina_fixed_environment != M336K5_KARINA_FIXED_ENVIRONMENT
        or policy.caller_environment_map_allowed
        or policy.profile_startup_allowed
        or policy.login_shell_allowed
        or policy.torch_at_startup_allowed
        or not policy.user_site_effective_state_required
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K5 startup policy is invalid")


def build_m336k5_sanitized_environment(
    *,
    platform_role: str,
    parent_environment: Mapping[str, str] | None = None,
) -> M336K5SanitizedEnvironment:
    policy = build_m336k5_python_startup_policy()
    parent = dict(os.environ if parent_environment is None else parent_environment)
    role = platform_role.upper()
    inherited: tuple[str, ...]
    variables: dict[str, str]
    if role == "WINDOWS":
        inherited = tuple(
            name for name in M336K5_WINDOWS_INHERITED_ENVIRONMENT if name in parent
        )
        variables = {name: parent[name] for name in inherited}
        variables.update(M336K5_WINDOWS_FIXED_ENVIRONMENT)
    elif role == "KARINA":
        inherited = ()
        variables = dict(M336K5_KARINA_FIXED_ENVIRONMENT)
    else:
        raise M336K2ProtocolError("M336K5 startup platform role is invalid")
    variables.update(M336K5_FIXED_ENVIRONMENT)
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_SANITIZED_PYTHON_ENVIRONMENT",
        "platform_role": role,
        "inherited_names": inherited,
        "variables": tuple(sorted(variables.items())),
        "removed_names": M336K5_FORBIDDEN_ENVIRONMENT,
        "startup_policy_hash": policy.policy_hash,
    }
    result = M336K5SanitizedEnvironment(**body, environment_hash=content_hash(body))
    _verify_sanitized_environment(result)
    return result


def build_m336k5_python_invocation(
    *,
    platform_role: str,
    process_role: str,
    python_executable: Path,
    git_executable: Path,
    repository: Path,
    working_directory: Path,
    bootstrap_script: Path,
    target: Path | str,
    execute_arguments: tuple[str, ...],
    validate_arguments: tuple[str, ...] = (),
    execute_startup_receipt: Path,
    validate_startup_receipt: Path,
    powershell_executable: Path | None = None,
    parent_environment: Mapping[str, str] | None = None,
    expected_python_implementation: str | None = None,
    expected_python_version: str | None = None,
    expected_environment_prefix: Path | None = None,
    expected_python_executable_hash: str | None = None,
    expected_bootstrap_source_hash: str | None = None,
    expected_target_source_hash: str | None = None,
    expected_project_source_identity: str | None = None,
    target_kind: str = "SCRIPT",
) -> M336K5PythonInvocationPlan:
    root = repository.resolve(strict=True)
    python_handle = python_executable.absolute()
    python_resolved = python_handle.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    bootstrap = bootstrap_script.resolve(strict=True)
    cwd = working_directory.resolve(strict=True)
    role = process_role.upper()
    kind = target_kind.upper()
    if role not in M336K5_PROCESS_ROLES or kind not in {"SCRIPT", "MODULE"}:
        raise M336K2ProtocolError("M336K5 invocation role or target kind is invalid")
    if kind == "SCRIPT":
        target_value = str(Path(target).resolve(strict=True))
        target_hash = bytes_hash(Path(target_value).read_bytes())
    else:
        target_value = str(target)
        target_hash = content_hash(("PYTHON_MODULE", target_value))
    if expected_target_source_hash is not None:
        target_hash = expected_target_source_hash
    environment = build_m336k5_sanitized_environment(
        platform_role=platform_role, parent_environment=parent_environment
    )
    policy = build_m336k5_python_startup_policy()
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_PRIVATE_PYTHON_INVOCATION_PLAN",
        "platform_role": platform_role.upper(),
        "process_role": role,
        "python_executable": str(python_handle),
        "git_executable": str(git),
        "powershell_executable": str(powershell_executable.resolve(strict=True))
        if powershell_executable is not None
        else None,
        "repository": str(root),
        "working_directory": str(cwd),
        "bootstrap_script": str(bootstrap),
        "target_kind": kind,
        "target": target_value,
        "execute_arguments": execute_arguments,
        "validate_arguments": validate_arguments,
        "execute_startup_receipt": str(execute_startup_receipt.resolve(strict=False)),
        "validate_startup_receipt": str(validate_startup_receipt.resolve(strict=False)),
        "expected_python_implementation": expected_python_implementation
        or platform.python_implementation(),
        "expected_python_version": expected_python_version or platform.python_version(),
        "expected_environment_prefix": str(
            (expected_environment_prefix or Path(sys.prefix)).resolve(strict=True)
        ),
        "expected_python_executable_hash": expected_python_executable_hash
        or bytes_hash(python_resolved.read_bytes()),
        "expected_bootstrap_source_hash": expected_bootstrap_source_hash
        or bytes_hash(bootstrap.read_bytes()),
        "expected_target_source_hash": target_hash,
        "expected_project_source_identity": expected_project_source_identity
        or compute_m336j_project_source_identity(root, git),
        "startup_policy": policy,
        "sanitized_environment": environment,
    }
    temporary = M336K5PythonInvocationPlan(**body, invocation_plan_hash="0" * 64)
    result = M336K5PythonInvocationPlan(
        **body, invocation_plan_hash=content_hash(temporary._body())
    )
    validate_m336k5_python_invocation(result)
    return result


def validate_m336k5_python_invocation(
    plan: M336K5PythonInvocationPlan, *, verify_local_files: bool = True
) -> None:
    verify_m336k5_python_startup_policy(plan.startup_policy)
    _verify_sanitized_environment(plan.sanitized_environment)
    hashes = (
        plan.expected_python_executable_hash,
        plan.expected_bootstrap_source_hash,
        plan.expected_target_source_hash,
        plan.expected_project_source_identity,
        plan.invocation_plan_hash,
    )
    if (
        plan.schema_version != 1
        or plan.contract_role != "M336K5_PRIVATE_PYTHON_INVOCATION_PLAN"
        or plan.platform_role not in {"WINDOWS", "KARINA"}
        or plan.process_role not in M336K5_PROCESS_ROLES
        or plan.target_kind not in {"SCRIPT", "MODULE"}
        or any(_HASH.fullmatch(value) is None for value in hashes)
        or plan.startup_policy.policy_hash
        != plan.sanitized_environment.startup_policy_hash
        or plan.sanitized_environment.platform_role != plan.platform_role
        or content_hash(plan._body()) != plan.invocation_plan_hash
        or not plan.execute_startup_receipt
        or not plan.validate_startup_receipt
    ):
        raise M336K2ProtocolError("M336K5 Python invocation plan is invalid")
    if not verify_local_files:
        return
    python = Path(plan.python_executable).resolve(strict=True)
    git = Path(plan.git_executable).resolve(strict=True)
    root = Path(plan.repository).resolve(strict=True)
    bootstrap = Path(plan.bootstrap_script).resolve(strict=True)
    if (
        not python.is_file()
        or not git.is_file()
        or not root.is_dir()
        or not Path(plan.working_directory).resolve(strict=True).is_dir()
        or not bootstrap.is_file()
        or bytes_hash(python.read_bytes()) != plan.expected_python_executable_hash
        or bytes_hash(bootstrap.read_bytes()) != plan.expected_bootstrap_source_hash
        or (
            plan.target_kind == "SCRIPT"
            and bytes_hash(Path(plan.target).resolve(strict=True).read_bytes())
            != plan.expected_target_source_hash
        )
        or compute_m336j_project_source_identity(root, git)
        != plan.expected_project_source_identity
    ):
        raise M336K2ProtocolError("M336K5 invocation executable/source binding changed")


def write_m336k5_python_invocation_plan(
    plan: M336K5PythonInvocationPlan, output: Path
) -> None:
    from ai_brain.stage2.facts.canonical import canonical_json

    validate_m336k5_python_invocation(plan)
    target = output.resolve(strict=False)
    if target.exists():
        raise FileExistsError("M336K5 invocation plan output must be fresh")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(plan.canonical_object()) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def run_m336k5_python_invocation(
    *,
    plan_path: Path,
    operation: str,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    import json

    value = json.loads(plan_path.resolve(strict=True).read_text(encoding="utf-8"))
    plan = M336K5PythonInvocationPlan.from_dict(value)
    validate_m336k5_python_invocation(plan)
    mode = operation.casefold()
    if mode not in M336K5_OPERATION_MODES:
        raise M336K2ProtocolError("M336K5 invocation operation is invalid")
    if plan.platform_role == "KARINA":
        command = (
            str(Path(plan.python_executable).absolute()),
            "-s",
            "-B",
            str(Path(plan.bootstrap_script).resolve(strict=True)),
            "--invocation-plan",
            str(plan_path.resolve(strict=True)),
            "--operation",
            mode,
        )
        return subprocess.run(
            command,
            cwd=Path(plan.working_directory).resolve(strict=True),
            check=False,
            capture_output=capture_output,
            env=dict(plan.sanitized_environment.variables),
        )
    if plan.platform_role != "WINDOWS" or plan.powershell_executable is None:
        raise M336K2ProtocolError("M336K5 local runner platform is invalid")
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
    )
    return subprocess.run(
        command,
        cwd=Path(plan.working_directory).resolve(strict=True),
        check=False,
        capture_output=capture_output,
        env=_powershell_boot_environment(plan.sanitized_environment),
    )


def build_m336k5_karina_invocation(
    *,
    component_id: str,
    capsule: KarinaPrivateExecutionCapsule,
    public_capsule: KarinaPublicExecutionCapsuleReceipt,
    process_role: str,
    target: PurePosixPath,
    target_arguments: tuple[tuple[KarinaRemoteTokenClass, str | PurePosixPath], ...],
    bootstrap_source_hash: str,
    target_source_hash: str,
    project_source_identity: str,
    startup_receipt: PurePosixPath,
    stdin_payload: bytes = b"",
    stdin_payload_hash: str | None = None,
    stdin_payload_size: int | None = None,
) -> tuple[KarinaRemoteCommandPlan, dict]:
    """Build one typed remote command whose first project import follows bootstrap."""

    role = process_role.upper()
    if role not in M336K5_PROCESS_ROLES:
        raise M336K2ProtocolError("M336K5 Karina process role is invalid")
    policy = build_m336k5_python_startup_policy()
    environment = build_m336k5_sanitized_environment(platform_role="KARINA")
    if environment.variables != m336k5_karina_environment():
        raise M336K2ProtocolError("M336K5 Karina environment policy diverged")
    bootstrap = capsule.repository_checkout / "scripts/m336k5_python_bootstrap.py"
    arguments = tuple(str(value) for _kind, value in target_arguments)
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_PRIVATE_PYTHON_INVOCATION_PLAN",
        "platform_role": "KARINA",
        "process_role": role,
        "python_executable": str(capsule.python_executable),
        "git_executable": str(capsule.git_executable),
        "powershell_executable": None,
        "repository": str(capsule.repository_checkout),
        "working_directory": str(capsule.repository_checkout),
        "bootstrap_script": str(bootstrap),
        "target_kind": "SCRIPT",
        "target": str(target),
        "execute_arguments": arguments,
        "validate_arguments": arguments,
        "execute_startup_receipt": str(startup_receipt),
        "validate_startup_receipt": str(startup_receipt),
        "expected_python_implementation": public_capsule.python_implementation,
        "expected_python_version": public_capsule.python_version,
        "expected_environment_prefix": str(capsule.python_executable.parent.parent),
        "expected_python_executable_hash": public_capsule.python_executable_content_hash,
        "expected_bootstrap_source_hash": bootstrap_source_hash,
        "expected_target_source_hash": target_source_hash,
        "expected_project_source_identity": project_source_identity,
        "startup_policy": policy.canonical_object(),
        "sanitized_environment": environment.canonical_object(),
    }
    inline_plan = {**body, "invocation_plan_hash": content_hash(body)}
    typed_arguments = (
        (KarinaRemoteTokenClass.FLAG, "-s"),
        (KarinaRemoteTokenClass.FLAG, "-B"),
        (KarinaRemoteTokenClass.PRIVATE_PATH, bootstrap),
        (KarinaRemoteTokenClass.FLAG, "--inline-plan-json"),
        (
            KarinaRemoteTokenClass.OPAQUE_ARGUMENT,
            json.dumps(
                inline_plan,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        ),
        (KarinaRemoteTokenClass.FLAG, "--operation"),
        (KarinaRemoteTokenClass.SUBCOMMAND, "execute"),
    )
    plan_values = {
        "component_id": component_id,
        "capsule": capsule,
        "arguments": typed_arguments,
        "expected_capsule_receipt_hash": public_capsule.receipt_hash,
    }
    if stdin_payload_hash is None:
        legacy = build_remote_command_plan(**plan_values, stdin_payload=stdin_payload)
    else:
        legacy = build_remote_command_plan(
            **plan_values,
            stdin_payload_hash=stdin_payload_hash,
            stdin_payload_size=stdin_payload_size,
        )
    command_body = {
        "schema_version": legacy.schema_version,
        "component_id": legacy.component_id,
        "environment": environment.variables,
        "argv": legacy.argv,
        "expected_capsule_receipt_hash": legacy.expected_capsule_receipt_hash,
        "stdin_payload_hash": legacy.stdin_payload_hash,
        "stdin_payload_size": legacy.stdin_payload_size,
    }
    return (
        KarinaRemoteCommandPlan(
            **command_body, command_plan_hash=content_hash(command_body)
        ),
        inline_plan,
    )


def startup_receipt_from_path(path: Path) -> M336K5PythonStartupReceipt:
    import json

    try:
        value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K5 startup receipt JSON is invalid") from error
    return M336K5PythonStartupReceipt.from_dict(value)


def _verify_sanitized_environment(environment: M336K5SanitizedEnvironment) -> None:
    body = asdict(environment)
    claimed = body.pop("environment_hash")
    variables = dict(environment.variables)
    fixed = dict(M336K5_FIXED_ENVIRONMENT)
    platform_fixed = dict(
        M336K5_WINDOWS_FIXED_ENVIRONMENT
        if environment.platform_role == "WINDOWS"
        else M336K5_KARINA_FIXED_ENVIRONMENT
    )
    expected_names = set(environment.inherited_names) | set(fixed) | set(platform_fixed)
    if (
        environment.schema_version != 1
        or environment.contract_role != "M336K5_SANITIZED_PYTHON_ENVIRONMENT"
        or environment.platform_role not in {"WINDOWS", "KARINA"}
        or tuple(sorted(environment.variables)) != environment.variables
        or len(variables) != len(environment.variables)
        or environment.removed_names != M336K5_FORBIDDEN_ENVIRONMENT
        or environment.startup_policy_hash
        != build_m336k5_python_startup_policy().policy_hash
        or set(variables) != expected_names
        or any(variables.get(name) != value for name, value in fixed.items())
        or any(variables.get(name) != value for name, value in platform_fixed.items())
        or any(name in variables for name in M336K5_FORBIDDEN_ENVIRONMENT)
        or (
            environment.platform_role == "WINDOWS"
            and any(
                name not in M336K5_WINDOWS_INHERITED_ENVIRONMENT
                for name in environment.inherited_names
            )
        )
        or (environment.platform_role == "KARINA" and environment.inherited_names)
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K5 sanitized environment is invalid")


def _powershell_boot_environment(
    environment: M336K5SanitizedEnvironment,
) -> dict[str, str]:
    values = dict(environment.variables)
    return {
        name: values[name]
        for name in M336K5_WINDOWS_INHERITED_ENVIRONMENT
        if name in values
    }


def _pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        raise M336K2ProtocolError("M336K5 environment pairs are invalid")
    result = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise M336K2ProtocolError("M336K5 environment pair is invalid")
        name, entry = item
        if type(name) is not str or type(entry) is not str:
            raise M336K2ProtocolError("M336K5 environment pair type is invalid")
        result.append((name, entry))
    return tuple(result)
