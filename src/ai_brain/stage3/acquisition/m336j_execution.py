"""Hermetic, path-independent Karina execution contracts for M-33.6j."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import platform
import re
import shlex
import site
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_jdk_provider import (
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.m336h_contracts import strict_json_file

M336J_EXECUTION_STRATEGY = "DIRECT_PROJECT_PYTHON"
M336J_CAPSULE_SCHEMA_VERSION = 1
M336J_COMMAND_PLAN_SCHEMA_VERSION = 1
M336J_MINIMAL_PATH = "/usr/bin:/bin"
M336J_REQUIRED_IMPORTS = (
    "ai_brain",
    "ai_brain.stage3.acquisition.m336i_production",
    "ai_brain.stage3.acquisition.m336j_execution",
    "numpy",
    "tokenizers",
    "tree_sitter",
    "tree_sitter_java",
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_PRIVATE_FIELDS = frozenset(
    {
        "schema_version",
        "execution_strategy",
        "python_executable",
        "git_executable",
        "java_executable",
        "javac_executable",
        "shell_executable",
        "repository_checkout",
        "private_root",
        "expected_head",
        "host_identity_receipt",
        "expected_host_identity_receipt_hash",
        "expected_public_jdk_identity_receipt_hash",
        "expected_public_receipt_hash",
    }
)


class KarinaRemoteTokenClass(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    SUBCOMMAND = "SUBCOMMAND"
    FLAG = "FLAG"
    PRIVATE_PATH = "PRIVATE_PATH"
    PUBLIC_IDENTITY = "PUBLIC_IDENTITY"
    OPAQUE_ARGUMENT = "OPAQUE_ARGUMENT"


@dataclass(frozen=True)
class KarinaPrivateExecutionCapsule:
    schema_version: int
    execution_strategy: str
    python_executable: PurePosixPath
    git_executable: PurePosixPath
    java_executable: PurePosixPath
    javac_executable: PurePosixPath
    shell_executable: PurePosixPath
    repository_checkout: PurePosixPath
    private_root: PurePosixPath
    expected_head: str
    host_identity_receipt: PurePosixPath
    expected_host_identity_receipt_hash: str
    expected_public_jdk_identity_receipt_hash: str
    expected_public_receipt_hash: str | None


@dataclass(frozen=True)
class KarinaExecutableIdentity:
    logical_role: str
    binary_hash: str
    normalized_version_hash: str
    invocation_count_limit: int
    path_lookup_allowed: bool
    network_allowed: bool
    child_process_policy: str
    identity_hash: str


@dataclass(frozen=True)
class KarinaPythonEnvironmentIdentity:
    implementation: str
    version: str
    executable_content_hash: str
    package_count: int
    package_manifest_hash: str
    environment_manifest_hash: str
    uv_lock_hash: str
    pyproject_toml_hash: str
    project_import_smoke_hash: str
    user_site_loading_disabled: bool
    torch_imported: bool
    identity_hash: str


@dataclass(frozen=True)
class KarinaRemoteEnvironmentPolicy:
    schema_version: int
    policy_id: str
    path_entry_count: int
    uv_directory_present: bool
    python_no_user_site: bool
    python_no_bytecode: bool
    locale: str
    timezone: str
    login_shell_allowed: bool
    profile_startup_allowed: bool
    network_allowed: bool
    project_source_import_path_bound: bool
    policy_hash: str


@dataclass(frozen=True)
class RemoteExecutableDependency:
    logical_role: str
    public_binary_hash: str
    normalized_version_hash: str
    invocation_count_limit: int
    path_lookup_allowed: bool
    network_allowed: bool
    child_process_policy: str
    identity_hash: str


@dataclass(frozen=True)
class RemoteExecutableDependencyManifest:
    schema_version: int
    execution_strategy: str
    dependencies: tuple[RemoteExecutableDependency, ...]
    dependency_count: int
    bare_executable_lookup_count: int
    network_enabled_dependency_count: int
    manifest_hash: str


@dataclass(frozen=True)
class RemoteExecutableDependencyAudit:
    schema_version: int
    manifest_hash: str
    observed_roles: tuple[str, ...]
    unregistered_role_count: int
    bare_executable_lookup_count: int
    changed_identity_count: int
    status: str
    audit_hash: str


@dataclass(frozen=True)
class KarinaPublicExecutionCapsuleReceipt:
    schema_version: int
    host_identity_receipt_hash: str
    execution_strategy: str
    python_implementation: str
    python_version: str
    python_executable_content_hash: str
    python_environment_package_manifest_hash: str
    uv_lock_hash: str
    pyproject_toml_hash: str
    git_executable_content_hash: str
    normalized_git_version_hash: str
    java_public_identity_receipt_hash: str
    shell_executable_content_hash: str
    minimal_environment_policy_hash: str
    project_import_smoke_hash: str
    executable_dependency_manifest_hash: str
    verification_status: str
    receipt_hash: str


@dataclass(frozen=True)
class KarinaRemoteCommandToken:
    token_class: KarinaRemoteTokenClass
    value: str


@dataclass(frozen=True)
class KarinaRemoteCommandPlan:
    schema_version: int
    component_id: str
    environment: tuple[tuple[str, str], ...]
    argv: tuple[KarinaRemoteCommandToken, ...]
    expected_capsule_receipt_hash: str
    stdin_payload_hash: str
    stdin_payload_size: int
    command_plan_hash: str


@dataclass(frozen=True)
class KarinaRemoteCommandReceipt:
    schema_version: int
    component_id: str
    command_plan_hash: str
    token_class_counts: tuple[tuple[str, int], ...]
    executable_identity_hashes: tuple[str, ...]
    environment_policy_hash: str
    exit_code: int
    response_hash: str
    response_size: int
    status: str
    receipt_hash: str


def load_private_execution_capsule(path: Path) -> KarinaPrivateExecutionCapsule:
    """Load the private path-bearing capsule without projecting paths publicly."""

    value = strict_json_file(path)
    if not isinstance(value, dict) or set(value) != _PRIVATE_FIELDS:
        raise ValueError("M336J private execution capsule fields changed")
    path_fields = (
        "python_executable",
        "git_executable",
        "java_executable",
        "javac_executable",
        "shell_executable",
        "repository_checkout",
        "private_root",
        "host_identity_receipt",
    )
    converted = dict(value)
    for name in path_fields:
        candidate = PurePosixPath(value[name])
        if not candidate.is_absolute():
            raise ValueError("M336J private capsule paths must be absolute")
        converted[name] = candidate
    capsule = KarinaPrivateExecutionCapsule(**converted)
    if (
        capsule.schema_version != M336J_CAPSULE_SCHEMA_VERSION
        or capsule.execution_strategy != M336J_EXECUTION_STRATEGY
        or _GIT_SHA.fullmatch(capsule.expected_head) is None
        or _SHA256.fullmatch(capsule.expected_host_identity_receipt_hash) is None
        or _SHA256.fullmatch(capsule.expected_public_jdk_identity_receipt_hash) is None
        or (
            capsule.expected_public_receipt_hash is not None
            and _SHA256.fullmatch(capsule.expected_public_receipt_hash) is None
        )
    ):
        raise ValueError("M336J private execution capsule identity is invalid")
    repository = capsule.repository_checkout
    private_root = capsule.private_root
    if private_root.is_relative_to(repository) or repository.is_relative_to(
        private_root
    ):
        raise ValueError("M336J private root and Git checkout must be separate")
    return capsule


def minimal_environment_policy() -> KarinaRemoteEnvironmentPolicy:
    body = {
        "schema_version": 2,
        "policy_id": "m336j.karina-minimal-environment.v2",
        "path_entry_count": 2,
        "uv_directory_present": False,
        "python_no_user_site": True,
        "python_no_bytecode": True,
        "locale": "C.UTF-8",
        "timezone": "UTC",
        "login_shell_allowed": False,
        "profile_startup_allowed": False,
        "network_allowed": False,
        "project_source_import_path_bound": True,
    }
    return KarinaRemoteEnvironmentPolicy(**body, policy_hash=content_hash(body))


def minimal_environment(
    repository_checkout: str | Path | PurePosixPath,
) -> tuple[tuple[str, str], ...]:
    if isinstance(repository_checkout, Path):
        if not repository_checkout.is_absolute():
            raise ValueError("M336J project source import root must be absolute")
        project_source = str(repository_checkout / "src")
    else:
        repository = PurePosixPath(str(repository_checkout))
        if not repository.is_absolute():
            raise ValueError("M336J project source import root must be absolute")
        project_source = (repository / "src").as_posix()
    return (
        ("LC_ALL", "C.UTF-8"),
        ("PATH", M336J_MINIMAL_PATH),
        ("PIP_NO_INDEX", "1"),
        ("PYTHONDONTWRITEBYTECODE", "1"),
        ("PYTHONNOUSERSITE", "1"),
        ("PYTHONPATH", project_source),
        ("TZ", "UTC"),
        ("UV_OFFLINE", "1"),
    )


def verify_execution_capsule(
    capsule_path: Path,
) -> tuple[
    KarinaPublicExecutionCapsuleReceipt,
    KarinaPythonEnvironmentIdentity,
    RemoteExecutableDependencyManifest,
    RemoteExecutableDependencyAudit,
]:
    """Verify all live identities from the direct interpreter before route work."""

    capsule = load_private_execution_capsule(capsule_path)
    repository = Path(str(capsule.repository_checkout)).resolve(strict=True)
    python_handle = Path(str(capsule.python_executable)).absolute()
    python_executable = python_handle.resolve(strict=True)
    git_executable = Path(str(capsule.git_executable))
    java_executable = Path(str(capsule.java_executable))
    javac_executable = Path(str(capsule.javac_executable))
    shell_executable = Path(str(capsule.shell_executable))
    host_identity_receipt = Path(str(capsule.host_identity_receipt))
    if Path(sys.executable).absolute() != python_handle:
        raise ValueError("M336J worker is not running under capsule Python")
    prefix = Path(sys.prefix).resolve(strict=True)
    if prefix.is_relative_to(repository) or not python_handle.is_relative_to(prefix):
        raise ValueError("M336J Python prefix is not the frozen external environment")
    for executable in (
        python_executable,
        git_executable,
        java_executable,
        javac_executable,
        shell_executable,
    ):
        if not executable.resolve(strict=True).is_file():
            raise ValueError("M336J capsule executable is not a regular file")
    if site.ENABLE_USER_SITE is not False or os.environ.get("PYTHONNOUSERSITE") != "1":
        raise ValueError("M336J user-site loading is not disabled")
    if any(
        os.environ.get(name) != value
        for name, value in minimal_environment(capsule.repository_checkout)
    ):
        raise ValueError("M336J worker environment differs from the minimal policy")
    if "torch" in sys.modules:
        raise ValueError("M336J execution capsule imported torch")
    private_root = Path(str(capsule.private_root)).resolve(strict=True)
    if not private_root.is_dir() or private_root.is_relative_to(repository):
        raise ValueError("M336J private root is not a separate directory")
    probe = private_root / ".m336j-write-probe"
    try:
        with probe.open("xb") as stream:
            stream.write(b"")
    finally:
        probe.unlink(missing_ok=True)

    git_head = _run(
        git_executable,
        "-C",
        repository,
        "rev-parse",
        "HEAD^{commit}",
    )
    git_status = _run(
        git_executable,
        "-C",
        repository,
        "status",
        "--porcelain=v1",
    )
    if git_head != capsule.expected_head or git_status:
        raise ValueError("M336J capsule repository is not clean exact HEAD")

    host = strict_json_file(host_identity_receipt)
    if not isinstance(host, dict):
        raise TypeError("M336J host identity receipt is not an object")
    host_body = dict(host)
    host_hash = host_body.pop("receipt_hash", None)
    if (
        content_hash(host_body) != host_hash
        or host_hash != capsule.expected_host_identity_receipt_hash
        or host.get("verification_status") != "PASS"
        or host.get("hostname_hash") != bytes_hash(platform.node().encode())
        or str(host.get("os_family", "")).casefold() != platform.system().casefold()
        or str(host.get("architecture", "")).casefold() != platform.machine().casefold()
    ):
        raise ValueError("M336J stable Karina identity changed")

    _private_jdk, public_jdk = verify_m336_jdk_provider_evidence(
        platform="karina",
        java=java_executable,
        javac=javac_executable,
    )
    if public_jdk.receipt_hash != capsule.expected_public_jdk_identity_receipt_hash:
        raise ValueError("M336J Karina JDK identity changed")

    python_identity = _python_environment_identity(capsule, git_executable)
    dependencies = _dependency_manifest(
        capsule, python_identity, public_jdk.receipt_hash
    )
    audit = audit_remote_dependencies(dependencies, tuple(_dependency_roles()))
    git_version = _run(git_executable, "--version")
    policy = minimal_environment_policy()
    body = {
        "schema_version": 1,
        "host_identity_receipt_hash": host_hash,
        "execution_strategy": M336J_EXECUTION_STRATEGY,
        "python_implementation": python_identity.implementation,
        "python_version": python_identity.version,
        "python_executable_content_hash": python_identity.executable_content_hash,
        "python_environment_package_manifest_hash": (
            python_identity.package_manifest_hash
        ),
        "uv_lock_hash": python_identity.uv_lock_hash,
        "pyproject_toml_hash": python_identity.pyproject_toml_hash,
        "git_executable_content_hash": bytes_hash(
            git_executable.resolve(strict=True).read_bytes()
        ),
        "normalized_git_version_hash": content_hash(git_version),
        "java_public_identity_receipt_hash": public_jdk.receipt_hash,
        "shell_executable_content_hash": bytes_hash(
            shell_executable.resolve(strict=True).read_bytes()
        ),
        "minimal_environment_policy_hash": policy.policy_hash,
        "project_import_smoke_hash": python_identity.project_import_smoke_hash,
        "executable_dependency_manifest_hash": dependencies.manifest_hash,
        "verification_status": "PASS",
    }
    receipt = KarinaPublicExecutionCapsuleReceipt(
        **body, receipt_hash=content_hash(body)
    )
    if (
        capsule.expected_public_receipt_hash is not None
        and receipt.receipt_hash != capsule.expected_public_receipt_hash
    ):
        raise ValueError("M336J public capsule receipt differs from frozen receipt")
    return receipt, python_identity, dependencies, audit


def run_karina_host_preflight_v2(capsule_path: Path) -> dict:
    """Run the exact future host preflight under the direct project interpreter."""

    receipt, python, dependencies, audit = verify_execution_capsule(capsule_path)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_KARINA_HOST_PREFLIGHT_V2",
        "host_identity_hash": receipt.host_identity_receipt_hash,
        "execution_capsule_receipt_hash": receipt.receipt_hash,
        "python_environment_manifest_hash": python.environment_manifest_hash,
        "executable_dependency_manifest_hash": dependencies.manifest_hash,
        "dependency_audit_hash": audit.audit_hash,
        "bare_executable_lookup_count": dependencies.bare_executable_lookup_count,
        "profile_startup_dependency_count": 0,
        "network_access_count": 0,
        "torch_imported": python.torch_imported,
        "status": "PASS",
    }
    return {**body, "receipt_hash": content_hash(body)}


def build_remote_command_plan(
    *,
    component_id: str,
    capsule: KarinaPrivateExecutionCapsule,
    arguments: Sequence[tuple[KarinaRemoteTokenClass, str | Path | PurePosixPath]],
    stdin_payload: bytes = b"",
    stdin_payload_hash: str | None = None,
    stdin_payload_size: int | None = None,
    expected_capsule_receipt_hash: str,
) -> KarinaRemoteCommandPlan:
    """Build a typed direct-Python plan; values remain unrendered until SSH."""

    if not component_id or _SHA256.fullmatch(expected_capsule_receipt_hash) is None:
        raise ValueError("M336J command plan identity is invalid")
    if stdin_payload_hash is None:
        payload_hash = bytes_hash(stdin_payload)
        payload_size = len(stdin_payload)
    else:
        if stdin_payload or _SHA256.fullmatch(stdin_payload_hash) is None:
            raise ValueError("M336J file-backed stdin identity is invalid")
        if stdin_payload_size is None or stdin_payload_size < 0:
            raise ValueError("M336J file-backed stdin size is invalid")
        payload_hash = stdin_payload_hash
        payload_size = stdin_payload_size
    argv = (
        KarinaRemoteCommandToken(
            KarinaRemoteTokenClass.EXECUTABLE,
            str(capsule.python_executable),
        ),
        *(KarinaRemoteCommandToken(kind, str(value)) for kind, value in arguments),
    )
    _validate_tokens(argv)
    body = {
        "schema_version": M336J_COMMAND_PLAN_SCHEMA_VERSION,
        "component_id": component_id,
        "environment": minimal_environment(capsule.repository_checkout),
        "argv": argv,
        "expected_capsule_receipt_hash": expected_capsule_receipt_hash,
        "stdin_payload_hash": payload_hash,
        "stdin_payload_size": payload_size,
    }
    return KarinaRemoteCommandPlan(**body, command_plan_hash=content_hash(body))


def render_remote_command(
    plan: KarinaRemoteCommandPlan,
    *,
    shell_executable: str | Path | PurePosixPath,
    repository_checkout: str | Path | PurePosixPath,
) -> str:
    """Render a deterministic POSIX command with no profile or PATH lookup."""

    _verify_command_plan(plan, repository_checkout=repository_checkout)
    resolved_shell = PurePosixPath(str(shell_executable))
    if not resolved_shell.is_absolute():
        raise ValueError("M336J shell executable handle must be absolute")
    environment = " ".join(
        f"{name}={shlex.quote(value)}" for name, value in plan.environment
    )
    argv = shlex.join(tuple(token.value for token in plan.argv))
    inner = f"{environment} exec {argv}"
    rendered = shlex.join((str(resolved_shell), "-c", inner))
    if any(
        forbidden in rendered
        for forbidden in (".profile", ".bash_profile", ".bashrc", "bash -l")
    ):
        raise ValueError("M336J rendered command depends on shell startup")
    return rendered


def command_receipt(
    *,
    plan: KarinaRemoteCommandPlan,
    dependency_manifest: RemoteExecutableDependencyManifest,
    exit_code: int,
    response: bytes | None = None,
    response_hash: str | None = None,
    response_size: int | None = None,
) -> KarinaRemoteCommandReceipt:
    if response_hash is None:
        raw = response if response is not None else b""
        response_hash = bytes_hash(raw)
        response_size = len(raw)
    elif response is not None or _SHA256.fullmatch(response_hash) is None:
        raise ValueError("M336J streamed response identity is invalid")
    if response_size is None or response_size < 0:
        raise ValueError("M336J streamed response size is invalid")
    counts = tuple(
        sorted(
            (
                kind.value,
                sum(token.token_class == kind for token in plan.argv),
            )
            for kind in KarinaRemoteTokenClass
        )
    )
    body = {
        "schema_version": 1,
        "component_id": plan.component_id,
        "command_plan_hash": plan.command_plan_hash,
        "token_class_counts": counts,
        "executable_identity_hashes": tuple(
            sorted(item.identity_hash for item in dependency_manifest.dependencies)
        ),
        "environment_policy_hash": minimal_environment_policy().policy_hash,
        "exit_code": exit_code,
        "response_hash": response_hash,
        "response_size": response_size,
        "status": "PASS" if exit_code == 0 else "FAIL",
    }
    return KarinaRemoteCommandReceipt(**body, receipt_hash=content_hash(body))


def audit_remote_dependencies(
    manifest: RemoteExecutableDependencyManifest,
    observed_roles: Iterable[str],
) -> RemoteExecutableDependencyAudit:
    observed = tuple(sorted(observed_roles))
    registered = {item.logical_role: item for item in manifest.dependencies}
    missing = tuple(role for role in observed if role not in registered)
    changed = sum(
        item.identity_hash
        != content_hash(
            {
                key: value
                for key, value in asdict(item).items()
                if key != "identity_hash"
            }
        )
        for item in manifest.dependencies
    )
    body = {
        "schema_version": 1,
        "manifest_hash": manifest.manifest_hash,
        "observed_roles": observed,
        "unregistered_role_count": len(missing),
        "bare_executable_lookup_count": manifest.bare_executable_lookup_count,
        "changed_identity_count": changed,
        "status": (
            "PASS"
            if not missing and not changed and not manifest.bare_executable_lookup_count
            else "FAIL"
        ),
    }
    audit = RemoteExecutableDependencyAudit(**body, audit_hash=content_hash(body))
    if audit.status != "PASS":
        raise ValueError("M336J remote executable dependency audit failed")
    return audit


def public_value_has_private_path(value: Any) -> bool:
    encoded = json.dumps(value, sort_keys=True, default=str)
    return bool(re.search(r"(?:[A-Za-z]:[\\/]|/(?:home|tmp|var|opt|usr)/)", encoded))


def _python_environment_identity(
    capsule: KarinaPrivateExecutionCapsule,
    git_executable: Path,
) -> KarinaPythonEnvironmentIdentity:
    repository = Path(str(capsule.repository_checkout)).resolve(strict=True)
    lock_path = repository / "uv.lock"
    project_path = repository / "pyproject.toml"
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    locked_versions: dict[str, set[str]] = {}
    for package in lock.get("package", []):
        locked_versions.setdefault(_normalize_name(package["name"]), set()).add(
            str(package["version"])
        )
    packages = []
    for distribution in importlib.metadata.distributions():
        name = _normalize_name(distribution.metadata["Name"])
        version = distribution.version
        if name not in locked_versions or version not in locked_versions[name]:
            raise ValueError("M336J installed distribution differs from uv.lock")
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
        raise ValueError("M336J Python environment package inventory is empty")

    imports = []
    for module_name in M336J_REQUIRED_IMPORTS:
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__).resolve(strict=True)
        if module_name == "ai_brain" and not module_path.is_relative_to(repository):
            raise ValueError("M336J project import is not bound to exact checkout")
        imports.append((module_name, bytes_hash(module_path.read_bytes())))
    if "torch" in sys.modules:
        raise ValueError("M336J project import smoke imported torch")
    executable_hash = bytes_hash(
        Path(str(capsule.python_executable)).resolve(strict=True).read_bytes()
    )
    package_hash = content_hash(package_rows)
    project_source_identity = compute_m336j_project_source_identity(
        repository, git_executable
    )
    import_hash = content_hash(
        {
            "project_source_identity": project_source_identity,
            "imports": tuple(imports),
        }
    )
    environment_hash = content_hash(
        {
            "executable_hash": executable_hash,
            "package_manifest_hash": package_hash,
            "project_source_identity": project_source_identity,
            "import_smoke_hash": import_hash,
        }
    )
    body = {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "executable_content_hash": executable_hash,
        "package_count": len(package_rows),
        "package_manifest_hash": package_hash,
        "environment_manifest_hash": environment_hash,
        "uv_lock_hash": bytes_hash(lock_path.read_bytes()),
        "pyproject_toml_hash": bytes_hash(project_path.read_bytes()),
        "project_import_smoke_hash": import_hash,
        "user_site_loading_disabled": True,
        "torch_imported": False,
    }
    return KarinaPythonEnvironmentIdentity(**body, identity_hash=content_hash(body))


def compute_m336j_project_source_identity(
    repository: Path, git_executable: Path
) -> str:
    """Hash the implementation surface that remains frozen after R25.

    Evidence-only Q25/F25 commits intentionally change the Git tree.  The capsule
    therefore binds the complete executable project surface rather than the
    whole commit tree, while the private capsule independently enforces the
    exact phase HEAD and a clean checkout.
    """

    root = repository.resolve(strict=True)
    resolved_git = git_executable.resolve(strict=True)
    result = subprocess.run(
        (
            str(resolved_git),
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--",
            "src",
            "scripts",
            "tools",
            "schemas",
            "pyproject.toml",
            "uv.lock",
        ),
        check=True,
        capture_output=True,
        env=dict(minimal_environment(root)),
    )
    paths = tuple(
        sorted(
            (
                item.decode("utf-8", errors="strict")
                for item in result.stdout.split(b"\0")
                if item
            ),
            key=lambda item: item.encode("utf-8"),
        )
    )
    if not paths:
        raise ValueError("M336J project source identity is empty")
    if any(not (root / path).is_file() for path in paths):
        raise ValueError("M336J tracked project source is unavailable")
    return content_hash(
        tuple((path, bytes_hash((root / path).read_bytes())) for path in paths)
    )


def _dependency_manifest(
    capsule: KarinaPrivateExecutionCapsule,
    python: KarinaPythonEnvironmentIdentity,
    public_jdk_receipt_hash: str,
) -> RemoteExecutableDependencyManifest:
    paths = {
        "PROJECT_PYTHON": Path(str(capsule.python_executable)),
        "GIT": Path(str(capsule.git_executable)),
        "JAVA": Path(str(capsule.java_executable)),
        "JAVAC": Path(str(capsule.javac_executable)),
        "POSIX_SHELL": Path(str(capsule.shell_executable)),
    }
    version_hashes = {
        "PROJECT_PYTHON": content_hash(
            (python.implementation, python.version, python.environment_manifest_hash)
        ),
        "GIT": content_hash(_run(Path(str(capsule.git_executable)), "--version")),
        "JAVA": public_jdk_receipt_hash,
        "JAVAC": public_jdk_receipt_hash,
        "POSIX_SHELL": content_hash(
            bytes_hash(
                Path(str(capsule.shell_executable)).resolve(strict=True).read_bytes()
            )
        ),
    }
    limits = {
        "PROJECT_PYTHON": 16,
        "GIT": 8,
        "JAVA": 8,
        "JAVAC": 8,
        "POSIX_SHELL": 16,
    }
    dependencies = []
    for role in _dependency_roles():
        item_body = {
            "logical_role": role,
            "public_binary_hash": bytes_hash(
                paths[role].resolve(strict=True).read_bytes()
            ),
            "normalized_version_hash": version_hashes[role],
            "invocation_count_limit": limits[role],
            "path_lookup_allowed": False,
            "network_allowed": False,
            "child_process_policy": (
                "REGISTERED_EXACT_CHILDREN_ONLY"
                if role in {"PROJECT_PYTHON", "POSIX_SHELL"}
                else "NO_CHILD_PROCESSES"
            ),
        }
        dependencies.append(
            RemoteExecutableDependency(
                **item_body, identity_hash=content_hash(item_body)
            )
        )
    ordered = tuple(dependencies)
    body = {
        "schema_version": 1,
        "execution_strategy": M336J_EXECUTION_STRATEGY,
        "dependencies": ordered,
        "dependency_count": len(ordered),
        "bare_executable_lookup_count": sum(
            item.path_lookup_allowed for item in ordered
        ),
        "network_enabled_dependency_count": sum(
            item.network_allowed for item in ordered
        ),
    }
    return RemoteExecutableDependencyManifest(**body, manifest_hash=content_hash(body))


def _dependency_roles() -> tuple[str, ...]:
    return ("PROJECT_PYTHON", "GIT", "JAVA", "JAVAC", "POSIX_SHELL")


def _normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _run(executable: Path, *arguments: str | Path) -> str:
    resolved = executable.resolve(strict=True)
    result = subprocess.run(
        (str(resolved), *(str(item) for item in arguments)),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            "LC_ALL": "C.UTF-8",
            "PATH": M336J_MINIMAL_PATH,
            "PIP_NO_INDEX": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TZ": "UTC",
            "UV_OFFLINE": "1",
        },
    )
    return (result.stdout or result.stderr).strip()


def _validate_tokens(tokens: Sequence[KarinaRemoteCommandToken]) -> None:
    if not tokens or tokens[0].token_class != KarinaRemoteTokenClass.EXECUTABLE:
        raise ValueError("M336J first command token must be an executable")
    for token in tokens:
        value = token.value
        if (
            not value
            or "\x00" in value
            or "\n" in value
            or "\r" in value
            or any(0xD800 <= ord(character) <= 0xDFFF for character in value)
        ):
            raise ValueError("M336J command token is not safely representable")
        if token.token_class == KarinaRemoteTokenClass.EXECUTABLE:
            path = PurePosixPath(value)
            if not path.is_absolute():
                raise ValueError("M336J executable token requires an absolute handle")


def _verify_command_plan(
    plan: KarinaRemoteCommandPlan,
    *,
    repository_checkout: str | Path | PurePosixPath,
) -> None:
    body = asdict(plan)
    claimed = body.pop("command_plan_hash")
    if (
        plan.schema_version != M336J_COMMAND_PLAN_SCHEMA_VERSION
        or content_hash(body) != claimed
        or tuple(sorted(plan.environment)) != plan.environment
        or tuple(plan.environment) != minimal_environment(repository_checkout)
    ):
        raise ValueError("M336J command plan changed")
    for name, value in plan.environment:
        if _ENV_NAME.fullmatch(name) is None or "\x00" in value or "\n" in value:
            raise ValueError("M336J command environment is unsafe")
    _validate_tokens(plan.argv)


def public_dataclass(value: Any) -> Mapping[str, Any]:
    """Return a canonical-friendly projection while rejecting private paths."""

    result = asdict(value)
    if public_value_has_private_path(result):
        raise ValueError("M336J public receipt contains a private path")
    return result


def public_execution_capsule_receipt_from_dict(
    value: Mapping[str, Any],
) -> KarinaPublicExecutionCapsuleReceipt:
    if set(value) != set(KarinaPublicExecutionCapsuleReceipt.__dataclass_fields__):
        raise ValueError("M336J public capsule receipt fields changed")
    receipt = KarinaPublicExecutionCapsuleReceipt(**value)
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    if content_hash(body) != claimed or receipt.verification_status != "PASS":
        raise ValueError("M336J public capsule receipt is invalid")
    if public_value_has_private_path(body):
        raise ValueError("M336J public capsule receipt contains a private path")
    return receipt


def python_environment_identity_from_dict(
    value: Mapping[str, Any],
) -> KarinaPythonEnvironmentIdentity:
    if set(value) != set(KarinaPythonEnvironmentIdentity.__dataclass_fields__):
        raise ValueError("M336J Python environment identity fields changed")
    identity = KarinaPythonEnvironmentIdentity(**value)
    body = asdict(identity)
    claimed = body.pop("identity_hash")
    if (
        content_hash(body) != claimed
        or not identity.user_site_loading_disabled
        or identity.torch_imported
        or identity.package_count < 1
    ):
        raise ValueError("M336J Python environment identity is invalid")
    if public_value_has_private_path(body):
        raise ValueError("M336J Python environment identity contains a private path")
    return identity


def dependency_manifest_from_dict(
    value: Mapping[str, Any],
) -> RemoteExecutableDependencyManifest:
    if set(value) != set(RemoteExecutableDependencyManifest.__dataclass_fields__):
        raise ValueError("M336J dependency manifest fields changed")
    dependencies = tuple(
        RemoteExecutableDependency(**item) for item in value["dependencies"]
    )
    manifest = RemoteExecutableDependencyManifest(
        **{**value, "dependencies": dependencies}
    )
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    if (
        content_hash(body) != claimed
        or manifest.dependency_count != len(dependencies)
        or manifest.bare_executable_lookup_count
        or manifest.network_enabled_dependency_count
    ):
        raise ValueError("M336J dependency manifest is invalid")
    audit_remote_dependencies(manifest, _dependency_roles())
    return manifest


def private_toolchain_schema_hash() -> str:
    return content_hash(
        tuple(
            (field.name, str(field.type))
            for field in KarinaPrivateExecutionCapsule.__dataclass_fields__.values()
        )
    )


def command_plan_schema_hash() -> str:
    return content_hash(
        tuple(
            (field.name, str(field.type))
            for field in KarinaRemoteCommandPlan.__dataclass_fields__.values()
        )
    )
