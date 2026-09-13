"""Persistent, preservation-bound Karina execution capsule for M-33.6k.6."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    KarinaPublicExecutionCapsuleReceipt,
    load_private_execution_capsule,
    verify_execution_capsule,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_python_startup_policy,
    startup_receipt_from_path,
)

M336K6_CAPSULE_STRATEGY = "PROTECTED_DETACHED_GIT_WORKTREE"
M336K6_CAPSULE_PREFIX = PurePosixPath(
    "/home/ibicza/.local/share/ai-brain/m336k6/capsules"
)
M336K6_REQUIRED_UNTIL = "E31_FINAL_QUALITY_COMPLETE"
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_PARTS = frozenset(
    {
        "tmp",
        "pytest",
        "quality",
        "disposable",
        "transfer",
        "staging",
        "production",
        "evaluation",
        "cleanup",
    }
)


@dataclass(frozen=True)
class M336K6CapsuleContentEntry:
    relative_path: str
    byte_count: int
    bytes_hash: str

    def verify(self) -> None:
        path = PurePosixPath(self.relative_path)
        if (
            not self.relative_path
            or path.is_absolute()
            or ".." in path.parts
            or self.byte_count < 0
            or _SHA256.fullmatch(self.bytes_hash) is None
        ):
            raise M336K2ProtocolError("M336K6 capsule content entry is invalid")


@dataclass(frozen=True)
class M336K6CapsuleContentManifest:
    schema_version: int
    contract_role: str
    execution_strategy: str
    implementation_sha: str
    entries: tuple[M336K6CapsuleContentEntry, ...]
    entry_count: int
    byte_count: int
    source_tree_hash: str
    uv_lock_hash: str
    pyproject_toml_hash: str
    manifest_hash: str

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("manifest_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "manifest_hash": self.manifest_hash}

    def verify(self) -> None:
        for entry in self.entries:
            entry.verify()
        ordered = tuple(
            sorted(self.entries, key=lambda item: item.relative_path.encode("utf-8"))
        )
        if (
            self.schema_version != 1
            or self.contract_role != "M336K6_CAPSULE_CONTENT_MANIFEST"
            or self.execution_strategy != M336K6_CAPSULE_STRATEGY
            or _SHA1.fullmatch(self.implementation_sha) is None
            or self.entries != ordered
            or len({item.relative_path for item in self.entries}) != len(self.entries)
            or self.entry_count != len(self.entries)
            or self.byte_count != sum(item.byte_count for item in self.entries)
            or any(
                _SHA256.fullmatch(value) is None
                for value in (
                    self.source_tree_hash,
                    self.uv_lock_hash,
                    self.pyproject_toml_hash,
                    self.manifest_hash,
                )
            )
            or self.source_tree_hash
            != content_hash(tuple(asdict(item) for item in self.entries))
            or self.manifest_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K6 capsule content manifest is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K6 capsule manifest fields changed")
        entries = value.get("entries")
        if type(entries) is not list or any(type(item) is not dict for item in entries):
            raise M336K2ProtocolError("M336K6 capsule entries changed")
        result = cls(
            **{
                **value,
                "entries": tuple(M336K6CapsuleContentEntry(**item) for item in entries),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K6CapsuleLifecyclePolicy:
    schema_version: int
    contract_role: str
    lifecycle_owner: str
    created_before_phase: str
    required_until_phase: str
    cleanup_eligible_before_required_until: bool
    recreation_after_f31_allowed: bool
    runtime_strategy_fallback_allowed: bool
    protected_worktree_required: bool
    liveness_verifier: str
    policy_hash: str

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("policy_hash")
        return value

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != "M336K6_CAPSULE_LIFECYCLE_POLICY"
            or self.lifecycle_owner != "M336K6_FINAL_ROUTE_CONTROLLER"
            or self.created_before_phase != "EXACT_CROSS_PLATFORM_QUALIFICATION"
            or self.required_until_phase != M336K6_REQUIRED_UNTIL
            or self.cleanup_eligible_before_required_until
            or self.recreation_after_f31_allowed
            or self.runtime_strategy_fallback_allowed
            or not self.protected_worktree_required
            or self.liveness_verifier != "verify_m336k6_persistent_capsule"
            or self.policy_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K6 capsule lifecycle policy is invalid")

    @classmethod
    def build(cls) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": "M336K6_CAPSULE_LIFECYCLE_POLICY",
            "lifecycle_owner": "M336K6_FINAL_ROUTE_CONTROLLER",
            "created_before_phase": "EXACT_CROSS_PLATFORM_QUALIFICATION",
            "required_until_phase": M336K6_REQUIRED_UNTIL,
            "cleanup_eligible_before_required_until": False,
            "recreation_after_f31_allowed": False,
            "runtime_strategy_fallback_allowed": False,
            "protected_worktree_required": True,
            "liveness_verifier": "verify_m336k6_persistent_capsule",
        }
        return cls(**body, policy_hash=content_hash(body))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K6 lifecycle policy fields changed")
        result = cls(**value)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K6PrivateExecutionCapsule:
    schema_version: int
    contract_role: str
    execution_strategy: str
    capsule_root: str
    source_root: str
    git_store: str
    private_route_root: str
    python_invocation_handle: str
    resolved_python_binary: str
    python_environment_prefix: str
    git_executable: str
    ssh_executable: str
    java_executable: str
    javac_executable: str
    shell_executable: str
    legacy_capsule_path: str
    content_manifest_path: str
    lifecycle_policy_path: str
    host_identity_receipt_path: str
    implementation_sha: str
    project_source_identity: str
    legacy_public_receipt_hash: str
    python_environment_manifest_hash: str
    executable_dependency_manifest_hash: str
    startup_policy_hash: str
    bootstrap_source_hash: str
    launcher_source_hash: str
    ssh_executable_content_hash: str
    content_manifest_hash: str
    lifecycle_policy_hash: str
    capsule_root_identity_hash: str
    capsule_identity_hash: str

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("capsule_identity_hash")
        return value

    def verify_structure(self) -> None:
        paths = (
            self.capsule_root,
            self.source_root,
            self.git_store,
            self.private_route_root,
            self.python_invocation_handle,
            self.resolved_python_binary,
            self.python_environment_prefix,
            self.git_executable,
            self.ssh_executable,
            self.java_executable,
            self.javac_executable,
            self.shell_executable,
            self.legacy_capsule_path,
            self.content_manifest_path,
            self.lifecycle_policy_path,
            self.host_identity_receipt_path,
        )
        if any(not PurePosixPath(path).is_absolute() for path in paths):
            raise M336K2ProtocolError("M336K6 private capsule paths must be absolute")
        verify_m336k6_capsule_location(PurePosixPath(self.capsule_root))
        root = PurePosixPath(self.capsule_root)
        if (
            self.schema_version != 1
            or self.contract_role != "M336K6_PRIVATE_EXECUTION_CAPSULE"
            or self.execution_strategy != M336K6_CAPSULE_STRATEGY
            or not PurePosixPath(self.source_root).is_relative_to(root)
            or not PurePosixPath(self.git_store).is_relative_to(root)
            or PurePosixPath(self.private_route_root).is_relative_to(root)
            or _SHA1.fullmatch(self.implementation_sha) is None
            or any(
                _SHA256.fullmatch(value) is None
                for value in (
                    self.project_source_identity,
                    self.legacy_public_receipt_hash,
                    self.python_environment_manifest_hash,
                    self.executable_dependency_manifest_hash,
                    self.startup_policy_hash,
                    self.bootstrap_source_hash,
                    self.launcher_source_hash,
                    self.ssh_executable_content_hash,
                    self.content_manifest_hash,
                    self.lifecycle_policy_hash,
                    self.capsule_root_identity_hash,
                    self.capsule_identity_hash,
                )
            )
            or self.capsule_root_identity_hash
            != content_hash(("M336K6_CAPSULE_ROOT", self.capsule_root))
            or self.capsule_identity_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K6 private capsule identity is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K6 private capsule fields changed")
        result = cls(**value)
        result.verify_structure()
        return result


@dataclass(frozen=True)
class M336K6PublicExecutionCapsuleReceipt:
    schema_version: int
    contract_role: str
    execution_strategy: str
    capsule_root_identity_hash: str
    capsule_identity_hash: str
    implementation_sha: str
    project_source_identity: str
    content_manifest_hash: str
    lifecycle_policy_hash: str
    legacy_public_receipt_hash: str
    python_environment_manifest_hash: str
    executable_dependency_manifest_hash: str
    startup_policy_hash: str
    bootstrap_source_hash: str
    launcher_source_hash: str
    ssh_executable_content_hash: str
    stable_host_identity_hash: str
    cleanup_managed_root_count: int
    mutable_quality_dependency_count: int
    verification_status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336K6CapsuleLivenessReceipt:
    schema_version: int
    contract_role: str
    phase: str
    capsule_identity_hash: str
    content_manifest_hash: str
    lifecycle_policy_hash: str
    startup_receipt_hash: str
    legacy_public_receipt_hash: str
    verified_file_count: int
    missing_file_count: int
    changed_file_count: int
    unexpected_file_count: int
    mutable_quality_dependency_count: int
    symlink_target_change_count: int
    protected_worktree_locked: bool
    status: str
    receipt_hash: str


def verify_m336k6_capsule_location(root: PurePosixPath) -> None:
    """Reject every path class that can be reclaimed as disposable work."""

    if not root.is_absolute() or not root.is_relative_to(M336K6_CAPSULE_PREFIX):
        raise M336K2ProtocolError("M336K6 capsule is outside persistent namespace")
    relative = root.relative_to(M336K6_CAPSULE_PREFIX)
    if len(relative.parts) != 1 or not relative.name.startswith("capsule-"):
        raise M336K2ProtocolError("M336K6 capsule root identity is invalid")
    tokens = set(re.split(r"[^a-z0-9]+", root.as_posix().casefold()))
    if tokens & _FORBIDDEN_PARTS:
        raise M336K2ProtocolError("M336K6 capsule uses a disposable path class")


def build_m336k6_capsule_content_manifest(
    source_root: Path, git_executable: Path, implementation_sha: str
) -> M336K6CapsuleContentManifest:
    root = source_root.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    _verify_git_worktree(root, git, implementation_sha, require_locked=False)
    raw = _run(git, root, "ls-files", "-z")
    paths = tuple(
        sorted(
            (item.decode("utf-8") for item in raw.split(b"\0") if item),
            key=lambda item: item.encode("utf-8"),
        )
    )
    if not paths:
        raise M336K2ProtocolError("M336K6 capsule source manifest is empty")
    entries = tuple(
        M336K6CapsuleContentEntry(
            relative_path=relative,
            byte_count=(root / relative).stat().st_size,
            bytes_hash=bytes_hash((root / relative).read_bytes()),
        )
        for relative in paths
    )
    body = {
        "schema_version": 1,
        "contract_role": "M336K6_CAPSULE_CONTENT_MANIFEST",
        "execution_strategy": M336K6_CAPSULE_STRATEGY,
        "implementation_sha": implementation_sha,
        "entries": entries,
        "entry_count": len(entries),
        "byte_count": sum(item.byte_count for item in entries),
        "source_tree_hash": content_hash(tuple(asdict(item) for item in entries)),
        "uv_lock_hash": bytes_hash((root / "uv.lock").read_bytes()),
        "pyproject_toml_hash": bytes_hash((root / "pyproject.toml").read_bytes()),
    }
    result = M336K6CapsuleContentManifest(**body, manifest_hash=content_hash(body))
    result.verify()
    return result


def verify_m336k6_persistent_capsule(
    capsule_path: Path,
    *,
    phase: str,
    startup_receipt_path: Path,
    execution_verifier: Callable[
        [Path], tuple[KarinaPublicExecutionCapsuleReceipt, Any, Any, Any]
    ] = verify_execution_capsule,
) -> M336K6CapsuleLivenessReceipt:
    """Authoritative live verifier used at every lifecycle boundary."""

    if not phase or any(character in phase for character in "\r\n\0"):
        raise M336K2ProtocolError("M336K6 liveness phase is invalid")
    value = _object(capsule_path.resolve(strict=True))
    capsule = M336K6PrivateExecutionCapsule.from_dict(value)
    startup = startup_receipt_from_path(startup_receipt_path)
    if (
        startup.startup_policy_hash != capsule.startup_policy_hash
        or startup.project_source_identity != capsule.project_source_identity
    ):
        raise M336K2ProtocolError("M336K6 liveness startup binding changed")
    verify_m336k6_required_paths(capsule)
    root = Path(capsule.capsule_root).resolve(strict=True)
    source = Path(capsule.source_root).resolve(strict=True)
    git_store = Path(capsule.git_store).resolve(strict=True)
    if source.parent != root or git_store.parent != root:
        raise M336K2ProtocolError("M336K6 capsule root layout changed")
    git = Path(capsule.git_executable).resolve(strict=True)
    _verify_git_worktree(source, git, capsule.implementation_sha, require_locked=True)
    lifecycle = M336K6CapsuleLifecyclePolicy.from_dict(
        _object(Path(capsule.lifecycle_policy_path).resolve(strict=True))
    )
    manifest = M336K6CapsuleContentManifest.from_dict(
        _object(Path(capsule.content_manifest_path).resolve(strict=True))
    )
    if (
        lifecycle.policy_hash != capsule.lifecycle_policy_hash
        or manifest.manifest_hash != capsule.content_manifest_hash
        or manifest.implementation_sha != capsule.implementation_sha
    ):
        raise M336K2ProtocolError("M336K6 capsule frozen binding changed")
    missing = changed = symlinks = 0
    for entry in manifest.entries:
        path = source / entry.relative_path
        if not path.exists() or not path.is_file():
            missing += 1
            continue
        if path.is_symlink():
            symlinks += 1
        if (
            path.stat().st_size != entry.byte_count
            or bytes_hash(path.read_bytes()) != entry.bytes_hash
        ):
            changed += 1
    tracked = {
        item.decode("utf-8")
        for item in _run(git, source, "ls-files", "-z").split(b"\0")
        if item
    }
    unexpected = len(tracked - {item.relative_path for item in manifest.entries})
    if missing or changed or unexpected or symlinks:
        raise M336K2ProtocolError("M336K6 capsule source content changed")
    legacy_path = Path(capsule.legacy_capsule_path).resolve(strict=True)
    legacy = load_private_execution_capsule(legacy_path)
    if (
        str(legacy.repository_checkout) != capsule.source_root
        or str(legacy.private_root) != capsule.private_route_root
        or str(legacy.python_executable) != capsule.python_invocation_handle
        or legacy.expected_head != capsule.implementation_sha
    ):
        raise M336K2ProtocolError("M336K6 legacy execution binding changed")
    receipt, python, dependencies, _audit = execution_verifier(legacy_path)
    verify_m336k6_execution_identities(
        capsule,
        legacy_public_receipt_hash=receipt.receipt_hash,
        python_environment_manifest_hash=python.environment_manifest_hash,
        executable_dependency_manifest_hash=dependencies.manifest_hash,
        implementation_sha=legacy.expected_head,
    )
    if (
        build_m336k5_python_startup_policy().policy_hash != capsule.startup_policy_hash
        or bytes_hash((source / "scripts/m336k5_python_bootstrap.py").read_bytes())
        != capsule.bootstrap_source_hash
        or bytes_hash(
            (source / "src/ai_brain/stage3/acquisition/m336k5_startup.py").read_bytes()
        )
        != capsule.launcher_source_hash
        or bytes_hash(Path(capsule.ssh_executable).resolve(strict=True).read_bytes())
        != capsule.ssh_executable_content_hash
    ):
        raise M336K2ProtocolError("M336K6 capsule startup/tool identity changed")
    if Path(capsule.python_invocation_handle).absolute() != Path(
        capsule.python_environment_prefix
    ) / "bin" / "python" or Path(capsule.resolved_python_binary).resolve(
        strict=True
    ) != Path(capsule.python_invocation_handle).resolve(strict=True):
        raise M336K2ProtocolError("M336K6 capsule execution environment changed")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K6_CAPSULE_LIVENESS_RECEIPT",
        "phase": phase,
        "capsule_identity_hash": capsule.capsule_identity_hash,
        "content_manifest_hash": manifest.manifest_hash,
        "lifecycle_policy_hash": lifecycle.policy_hash,
        "startup_receipt_hash": startup.receipt_hash,
        "legacy_public_receipt_hash": receipt.receipt_hash,
        "verified_file_count": len(manifest.entries),
        "missing_file_count": missing,
        "changed_file_count": changed,
        "unexpected_file_count": unexpected,
        "mutable_quality_dependency_count": 0,
        "symlink_target_change_count": symlinks,
        "protected_worktree_locked": True,
        "status": "PASS",
    }
    return M336K6CapsuleLivenessReceipt(**body, receipt_hash=content_hash(body))


def verify_m336k6_required_paths(
    capsule: M336K6PrivateExecutionCapsule,
    *,
    path_exists: Callable[[str], bool] | None = None,
) -> None:
    """Fail closed when any declared persistent binding has disappeared."""

    capsule.verify_structure()
    exists = path_exists or (lambda value: Path(value).exists())
    required = (
        capsule.capsule_root,
        capsule.source_root,
        capsule.git_store,
        capsule.private_route_root,
        capsule.python_invocation_handle,
        capsule.resolved_python_binary,
        capsule.python_environment_prefix,
        capsule.git_executable,
        capsule.ssh_executable,
        capsule.java_executable,
        capsule.javac_executable,
        capsule.shell_executable,
        capsule.legacy_capsule_path,
        capsule.content_manifest_path,
        capsule.lifecycle_policy_path,
        capsule.host_identity_receipt_path,
    )
    if any(not exists(value) for value in required):
        raise M336K2ProtocolError("M336K6 required capsule binding is missing")


def verify_m336k6_execution_identities(
    capsule: M336K6PrivateExecutionCapsule,
    *,
    legacy_public_receipt_hash: str,
    python_environment_manifest_hash: str,
    executable_dependency_manifest_hash: str,
    implementation_sha: str,
) -> None:
    """Compare live execution identities with the immutable capsule declaration."""

    if (
        legacy_public_receipt_hash != capsule.legacy_public_receipt_hash
        or python_environment_manifest_hash != capsule.python_environment_manifest_hash
        or executable_dependency_manifest_hash
        != capsule.executable_dependency_manifest_hash
        or implementation_sha != capsule.implementation_sha
    ):
        raise M336K2ProtocolError("M336K6 live execution identity changed")


def build_m336k6_public_capsule_receipt(
    capsule: M336K6PrivateExecutionCapsule, stable_host_identity_hash: str
) -> M336K6PublicExecutionCapsuleReceipt:
    capsule.verify_structure()
    if _SHA256.fullmatch(stable_host_identity_hash) is None:
        raise M336K2ProtocolError("M336K6 stable host identity is invalid")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K6_PERSISTENT_EXECUTION_CAPSULE",
        "execution_strategy": capsule.execution_strategy,
        "capsule_root_identity_hash": capsule.capsule_root_identity_hash,
        "capsule_identity_hash": capsule.capsule_identity_hash,
        "implementation_sha": capsule.implementation_sha,
        "project_source_identity": capsule.project_source_identity,
        "content_manifest_hash": capsule.content_manifest_hash,
        "lifecycle_policy_hash": capsule.lifecycle_policy_hash,
        "legacy_public_receipt_hash": capsule.legacy_public_receipt_hash,
        "python_environment_manifest_hash": capsule.python_environment_manifest_hash,
        "executable_dependency_manifest_hash": capsule.executable_dependency_manifest_hash,
        "startup_policy_hash": capsule.startup_policy_hash,
        "bootstrap_source_hash": capsule.bootstrap_source_hash,
        "launcher_source_hash": capsule.launcher_source_hash,
        "ssh_executable_content_hash": capsule.ssh_executable_content_hash,
        "stable_host_identity_hash": stable_host_identity_hash,
        "cleanup_managed_root_count": 0,
        "mutable_quality_dependency_count": 0,
        "verification_status": "PASS",
    }
    return M336K6PublicExecutionCapsuleReceipt(**body, receipt_hash=content_hash(body))


def write_m336k6_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _verify_git_worktree(
    root: Path, git: Path, implementation_sha: str, *, require_locked: bool
) -> None:
    if _SHA1.fullmatch(implementation_sha) is None:
        raise M336K2ProtocolError("M336K6 implementation identity is invalid")
    head = _run(git, root, "rev-parse", "HEAD^{commit}").decode().strip()
    status = _run(git, root, "status", "--porcelain=v1")
    if head != implementation_sha or status:
        raise M336K2ProtocolError("M336K6 protected worktree is not clean exact HEAD")
    if require_locked:
        raw = _run(git, root, "worktree", "list", "--porcelain", "-z")
        records = raw.split(b"\0\0")
        resolved = str(root.resolve(strict=True)).replace("\\", "/")
        matched = tuple(
            record
            for record in records
            if (b"worktree " + resolved.encode()) in record.replace(b"\\", b"/")
        )
        if len(matched) != 1 or b"\0locked" not in matched[0]:
            raise M336K2ProtocolError("M336K6 protected worktree is not locked")


def _run(executable: Path, cwd: Path, *arguments: str) -> bytes:
    return subprocess.run(
        (str(executable), *arguments),
        cwd=cwd,
        check=True,
        capture_output=True,
        env=m336k2_minimal_environment(),
    ).stdout


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K6 capsule JSON is invalid") from error
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K6 capsule JSON is not an object")
    return value
