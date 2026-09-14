"""Explicit source-domain contracts for the M-33.6k.8 final route.

The current controller and the preserved Karina capsule are intentionally built
from different project revisions. This module keeps those authority domains
separate and owns the shared rehearsal/official freeze-input assembler.
"""

from __future__ import annotations

import ast
import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    m336k2_minimal_environment,
)

CURRENT_IMPLEMENTATION_CONTROLLER = "CURRENT_IMPLEMENTATION_CONTROLLER"
PERSISTENT_KARINA_RUNTIME_CAPSULE = "PERSISTENT_KARINA_RUNTIME_CAPSULE"
CROSS_DOMAIN_BRIDGE = "CROSS_DOMAIN_BRIDGE"
PHASE_NEUTRAL_SHARED_POLICY = "PHASE_NEUTRAL_SHARED_POLICY"
HISTORICAL_READ_ONLY = "HISTORICAL_READ_ONLY"
M336K8_SOURCE_DOMAINS = frozenset(
    {
        CURRENT_IMPLEMENTATION_CONTROLLER,
        PERSISTENT_KARINA_RUNTIME_CAPSULE,
        CROSS_DOMAIN_BRIDGE,
        PHASE_NEUTRAL_SHARED_POLICY,
        HISTORICAL_READ_ONLY,
    }
)
M336K8_TRACKED_ROOTS = ("src", "scripts", "tools", "schemas")
M336K8_TRACKED_FILE_NAMES = ("pyproject.toml", "uv.lock")
M336K8_SOURCE_IDENTITY_ALGORITHM = "m336k8.git-and-live-source-rows.v1"
M336K8_BRIDGE_PATHS = (
    ("STDLIB_BOOTSTRAP", "scripts/m336k5_python_bootstrap.py"),
    ("KARINA_TARGET", "scripts/m336j_karina_execution.py"),
    (
        "REMOTE_COMMAND_RENDERER",
        "src/ai_brain/stage3/acquisition/m336j_execution.py",
    ),
    (
        "STARTUP_RECEIPT_SCHEMA",
        "src/ai_brain/stage3/acquisition/m336k5_startup.py",
    ),
    ("REMOTE_SCHEMAS", "src/ai_brain/stage3/acquisition/m336j_schemas.py"),
    ("REMOTE_ROUTE_REGISTRY", "src/ai_brain/stage3/acquisition/m336j_registry.py"),
    ("REMOTE_TRANSPORT", "src/ai_brain/stage3/acquisition/m336j_transport.py"),
)
_HASH_LENGTH = 64
_SHA_LENGTH = 40


def _is_hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _HASH_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_sha(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _SHA_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _field_names(cls: type) -> set[str]:
    return {item.name for item in fields(cls)}


def _strict_fields(value: object, cls: type, label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _field_names(cls):
        raise M336K2ProtocolError(f"M336K8 {label} fields changed")
    return value


def _hashed_body(value: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if not _is_hash(claimed) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K8 semantic hash changed")
    return body


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (canonical_json(dict(value)) + "\n").encode("utf-8")


def _git_bytes(git: Path, root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        env=m336k2_minimal_environment(),
    ).stdout


def _git_text(git: Path, root: Path, *arguments: str) -> str:
    return _git_bytes(git, root, *arguments).decode("utf-8", errors="strict").strip()


@dataclass(frozen=True)
class M336K8ProjectSourceIdentityPolicy:
    schema_version: int
    contract_role: str
    algorithm_id: str
    tracked_roots: tuple[str, ...]
    tracked_file_names: tuple[str, ...]
    path_ordering: str
    file_bytes_hash_algorithm: str
    canonical_row_encoding: str
    project_identity_hash_algorithm: str
    live_checkout_verification_required: bool
    committed_tree_verification_required: bool
    clean_checkout_required: bool
    policy_hash: str

    ROLE: ClassVar[str] = "M336K8_PROJECT_SOURCE_IDENTITY_POLICY"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("policy_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "policy_hash": self.policy_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.algorithm_id != M336K8_SOURCE_IDENTITY_ALGORITHM
            or self.tracked_roots != M336K8_TRACKED_ROOTS
            or self.tracked_file_names != M336K8_TRACKED_FILE_NAMES
            or self.path_ordering != "UTF8_REPOSITORY_RELATIVE_BYTE_ORDER"
            or self.file_bytes_hash_algorithm != "SHA256"
            or self.canonical_row_encoding
            != "PROJECT_CANONICAL_JSON_TUPLE_PATH_AND_SHA256"
            or self.project_identity_hash_algorithm != "PROJECT_CONTENT_HASH_SHA256"
            or self.live_checkout_verification_required is not True
            or self.committed_tree_verification_required is not True
            or self.clean_checkout_required is not True
            or self.policy_hash != content_hash(self._body())
            or any(Path(item).is_absolute() for item in self.tracked_roots)
            or any(Path(item).is_absolute() for item in self.tracked_file_names)
        ):
            raise M336K2ProtocolError("M336K8 source identity policy is invalid")

    @classmethod
    def build(cls) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "algorithm_id": M336K8_SOURCE_IDENTITY_ALGORITHM,
            "tracked_roots": M336K8_TRACKED_ROOTS,
            "tracked_file_names": M336K8_TRACKED_FILE_NAMES,
            "path_ordering": "UTF8_REPOSITORY_RELATIVE_BYTE_ORDER",
            "file_bytes_hash_algorithm": "SHA256",
            "canonical_row_encoding": "PROJECT_CANONICAL_JSON_TUPLE_PATH_AND_SHA256",
            "project_identity_hash_algorithm": "PROJECT_CONTENT_HASH_SHA256",
            "live_checkout_verification_required": True,
            "committed_tree_verification_required": True,
            "clean_checkout_required": True,
        }
        result = cls(**body, policy_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, cls, "source identity policy")
        result = cls(
            **{
                **strict,
                "tracked_roots": tuple(strict["tracked_roots"]),
                "tracked_file_names": tuple(strict["tracked_file_names"]),
            }
        )
        result.verify()
        return result


def _source_scopes(policy: M336K8ProjectSourceIdentityPolicy) -> tuple[str, ...]:
    policy.verify()
    return (*policy.tracked_roots, *policy.tracked_file_names)


def _committed_source_rows(
    repository: Path,
    git_executable: Path,
    exact_commit: str,
    policy: M336K8ProjectSourceIdentityPolicy,
) -> tuple[tuple[str, str], ...]:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    if not _is_sha(exact_commit):
        raise M336K2ProtocolError("M336K8 committed source commit is invalid")
    raw = _git_bytes(
        git,
        root,
        "ls-tree",
        "-r",
        "-z",
        "--name-only",
        exact_commit,
        "--",
        *_source_scopes(policy),
    )
    paths = tuple(
        sorted(
            (
                item.decode("utf-8", errors="strict")
                for item in raw.split(b"\0")
                if item
            ),
            key=lambda item: item.encode("utf-8"),
        )
    )
    if not paths:
        raise M336K2ProtocolError("M336K8 committed source path set is empty")
    return tuple(
        (path, bytes_hash(_git_bytes(git, root, "show", f"{exact_commit}:{path}")))
        for path in paths
    )


def _live_source_rows(
    repository: Path,
    git_executable: Path,
    policy: M336K8ProjectSourceIdentityPolicy,
) -> tuple[tuple[str, str], ...]:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    raw = _git_bytes(git, root, "ls-files", "-z", "--", *_source_scopes(policy))
    paths = tuple(
        sorted(
            (
                item.decode("utf-8", errors="strict")
                for item in raw.split(b"\0")
                if item
            ),
            key=lambda item: item.encode("utf-8"),
        )
    )
    if not paths or any(not (root / path).is_file() for path in paths):
        raise M336K2ProtocolError("M336K8 live source path set is unavailable")
    return tuple((path, bytes_hash((root / path).read_bytes())) for path in paths)


@dataclass(frozen=True)
class M336K8ProjectSourceIdentityReceipt:
    schema_version: int
    contract_role: str
    exact_implementation_tip: str
    source_identity_policy_hash: str
    tracked_path_set_hash: str
    tracked_file_count: int
    committed_project_source_identity: str
    live_project_source_identity: str
    identity_difference_count: int
    path_set_difference_count: int
    worktree_clean: bool
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K8_PROJECT_SOURCE_IDENTITY_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        passed = (
            self.identity_difference_count == 0
            and self.path_set_difference_count == 0
            and self.worktree_clean
            and self.tracked_file_count > 0
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or not _is_sha(self.exact_implementation_tip)
            or any(
                not _is_hash(value)
                for value in (
                    self.source_identity_policy_hash,
                    self.tracked_path_set_hash,
                    self.committed_project_source_identity,
                    self.live_project_source_identity,
                    self.receipt_hash,
                )
            )
            or type(self.tracked_file_count) is not int
            or self.tracked_file_count < 1
            or type(self.identity_difference_count) is not int
            or type(self.path_set_difference_count) is not int
            or type(self.worktree_clean) is not bool
            or self.status != ("PASS" if passed else "FAIL")
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 source identity receipt is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict_fields(value, cls, "source identity receipt"))
        result.verify()
        return result


def build_m336k8_project_source_identity_receipt(
    *,
    repository: Path,
    git_executable: Path,
    exact_implementation_tip: str,
    policy: M336K8ProjectSourceIdentityPolicy,
) -> M336K8ProjectSourceIdentityReceipt:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    policy.verify()
    resolved = _git_text(
        git, root, "rev-parse", f"{exact_implementation_tip}^{{commit}}"
    )
    if resolved != exact_implementation_tip:
        raise M336K2ProtocolError("M336K8 implementation tip does not resolve exactly")
    committed = _committed_source_rows(root, git, exact_implementation_tip, policy)
    live = _live_source_rows(root, git, policy)
    committed_paths = tuple(item[0] for item in committed)
    live_paths = tuple(item[0] for item in live)
    path_difference_count = len(set(committed_paths) ^ set(live_paths))
    committed_identity = content_hash(committed)
    live_identity = content_hash(live)
    clean = not _git_text(
        git, root, "status", "--porcelain=v1", "--", *_source_scopes(policy)
    )
    passed = committed_identity == live_identity and not path_difference_count and clean
    body = {
        "schema_version": 1,
        "contract_role": M336K8ProjectSourceIdentityReceipt.ROLE,
        "exact_implementation_tip": exact_implementation_tip,
        "source_identity_policy_hash": policy.policy_hash,
        "tracked_path_set_hash": content_hash(committed_paths),
        "tracked_file_count": len(committed),
        "committed_project_source_identity": committed_identity,
        "live_project_source_identity": live_identity,
        "identity_difference_count": int(committed_identity != live_identity),
        "path_set_difference_count": path_difference_count,
        "worktree_clean": clean,
        "status": "PASS" if passed else "FAIL",
    }
    result = M336K8ProjectSourceIdentityReceipt(**body, receipt_hash=content_hash(body))
    result.verify()
    return result


@dataclass(frozen=True)
class M336K8ControllerStartupBinding:
    schema_version: int
    contract_role: str
    source_domain: str
    exact_implementation_tip: str
    project_source_identity_policy_hash: str
    project_source_identity_receipt_hash: str
    controller_project_source_identity: str
    controller_python_environment_manifest_hash: str
    controller_executable_dependency_manifest_hash: str
    startup_policy_hash: str
    sanitized_environment_policy_hash: str
    startup_receipt_schema_hash: str
    bootstrap_source_hash: str
    windows_launcher_source_hash: str
    validate_only_target_source_hash: str
    final_controller_target_source_hash: str
    binding_hash: str

    ROLE: ClassVar[str] = "M336K8_CONTROLLER_STARTUP_BINDING"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("binding_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "binding_hash": self.binding_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.source_domain != CURRENT_IMPLEMENTATION_CONTROLLER
            or not _is_sha(self.exact_implementation_tip)
            or any(not _is_hash(item) for item in hashes)
            or self.binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 controller startup binding is invalid")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "source_domain": CURRENT_IMPLEMENTATION_CONTROLLER,
            **values,
        }
        if set(body) != _field_names(cls) - {"binding_hash"}:
            raise M336K2ProtocolError("M336K8 controller startup inputs changed")
        result = cls(**body, binding_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict_fields(value, cls, "controller startup binding"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K8PersistentCapsuleSourceBinding:
    schema_version: int
    contract_role: str
    source_domain: str
    persistent_capsule_binding_set_hash: str
    capsule_implementation_tip: str
    capsule_project_source_identity: str
    capsule_python_environment_manifest_hash: str
    capsule_executable_dependency_manifest_hash: str
    capsule_identity_hash: str
    capsule_content_manifest_hash: str
    capsule_lifecycle_policy_hash: str
    capsule_liveness_receipt_hash: str
    persistent_public_receipt_hash: str
    legacy_public_receipt_hash: str
    stable_host_identity_hash: str
    bridge_surface_manifest_hash: str
    binding_hash: str

    ROLE: ClassVar[str] = "M336K8_PERSISTENT_CAPSULE_SOURCE_BINDING"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("binding_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "binding_hash": self.binding_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.source_domain != PERSISTENT_KARINA_RUNTIME_CAPSULE
            or not _is_sha(self.capsule_implementation_tip)
            or any(not _is_hash(item) for item in hashes)
            or self.binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 persistent capsule binding is invalid")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "source_domain": PERSISTENT_KARINA_RUNTIME_CAPSULE,
            **values,
        }
        if set(body) != _field_names(cls) - {"binding_hash"}:
            raise M336K2ProtocolError("M336K8 persistent capsule inputs changed")
        result = cls(**body, binding_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict_fields(value, cls, "persistent capsule binding"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K8BridgeSurfaceEntry:
    logical_role: str
    repository_relative_path: str
    controller_bytes_hash: str
    capsule_bytes_hash: str
    byte_equality_required: bool
    schema_compatibility_required: bool
    status: str

    def verify(self) -> None:
        path = Path(self.repository_relative_path)
        passed = (
            not self.byte_equality_required
            or self.controller_bytes_hash == self.capsule_bytes_hash
        ) and self.schema_compatibility_required
        if (
            not self.logical_role
            or path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != self.repository_relative_path
            or not _is_hash(self.controller_bytes_hash)
            or not _is_hash(self.capsule_bytes_hash)
            or type(self.byte_equality_required) is not bool
            or type(self.schema_compatibility_required) is not bool
            or self.status != ("PASS" if passed else "FAIL")
        ):
            raise M336K2ProtocolError("M336K8 bridge entry is invalid")


@dataclass(frozen=True)
class M336K8BridgeSurfaceManifest:
    schema_version: int
    contract_role: str
    entries: tuple[M336K8BridgeSurfaceEntry, ...]
    entry_count: int
    controller_tree_hash: str
    capsule_tree_hash: str
    missing_entry_count: int
    extra_entry_count: int
    changed_entry_count: int
    schema_compatibility_count: int
    schema_incompatibility_count: int
    manifest_hash: str

    ROLE: ClassVar[str] = "M336K8_BRIDGE_SURFACE_MANIFEST"

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "entries": tuple(asdict(item) for item in self.entries),
            "entry_count": self.entry_count,
            "controller_tree_hash": self.controller_tree_hash,
            "capsule_tree_hash": self.capsule_tree_hash,
            "missing_entry_count": self.missing_entry_count,
            "extra_entry_count": self.extra_entry_count,
            "changed_entry_count": self.changed_entry_count,
            "schema_compatibility_count": self.schema_compatibility_count,
            "schema_incompatibility_count": self.schema_incompatibility_count,
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "manifest_hash": self.manifest_hash}

    def verify(self) -> None:
        for item in self.entries:
            item.verify()
        counts = (
            self.missing_entry_count,
            self.extra_entry_count,
            self.changed_entry_count,
            self.schema_incompatibility_count,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.entry_count != len(self.entries)
            or any(type(value) is not int or value < 0 for value in counts)
            or self.schema_compatibility_count + self.schema_incompatibility_count
            != self.entry_count
            or any(counts)
            or self.controller_tree_hash != self.capsule_tree_hash
            or any(
                not _is_hash(item)
                for item in (
                    self.controller_tree_hash,
                    self.capsule_tree_hash,
                    self.manifest_hash,
                )
            )
            or self.manifest_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 bridge surface is not PASS")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, cls, "bridge surface")
        if type(strict["entries"]) is not list:
            raise M336K2ProtocolError("M336K8 bridge entries changed")
        result = cls(
            **{
                **strict,
                "entries": tuple(
                    M336K8BridgeSurfaceEntry(**item) for item in strict["entries"]
                ),
            }
        )
        result.verify()
        return result


def build_m336k8_bridge_surface_manifest(
    *, repository: Path, capsule_content_manifest: Mapping[str, Any]
) -> M336K8BridgeSurfaceManifest:
    root = repository.resolve(strict=True)
    entries_value = capsule_content_manifest.get("entries")
    if type(entries_value) is not list:
        raise M336K2ProtocolError("M336K8 capsule content entries are invalid")
    capsule_entries = {
        item.get("relative_path"): item for item in entries_value if type(item) is dict
    }
    entries = []
    missing = 0
    for role, relative in M336K8_BRIDGE_PATHS:
        path = root.joinpath(*relative.split("/"))
        capsule = capsule_entries.get(relative)
        if (
            not path.is_file()
            or capsule is None
            or not _is_hash(capsule.get("bytes_hash"))
        ):
            missing += 1
            continue
        controller_hash = bytes_hash(path.read_bytes())
        capsule_hash = capsule["bytes_hash"]
        entries.append(
            M336K8BridgeSurfaceEntry(
                logical_role=role,
                repository_relative_path=relative,
                controller_bytes_hash=controller_hash,
                capsule_bytes_hash=capsule_hash,
                byte_equality_required=True,
                schema_compatibility_required=True,
                status="PASS" if controller_hash == capsule_hash else "FAIL",
            )
        )
    controller_rows = tuple(
        (item.logical_role, item.repository_relative_path, item.controller_bytes_hash)
        for item in entries
    )
    capsule_rows = tuple(
        (item.logical_role, item.repository_relative_path, item.capsule_bytes_hash)
        for item in entries
    )
    body = {
        "schema_version": 1,
        "contract_role": M336K8BridgeSurfaceManifest.ROLE,
        "entries": tuple(entries),
        "entry_count": len(entries),
        "controller_tree_hash": content_hash(controller_rows),
        "capsule_tree_hash": content_hash(capsule_rows),
        "missing_entry_count": missing,
        "extra_entry_count": 0,
        "changed_entry_count": sum(
            item.controller_bytes_hash != item.capsule_bytes_hash for item in entries
        ),
        "schema_compatibility_count": len(entries),
        "schema_incompatibility_count": 0,
    }
    temporary = M336K8BridgeSurfaceManifest(**body, manifest_hash="0" * 64)
    result = M336K8BridgeSurfaceManifest(
        **body, manifest_hash=content_hash(temporary._body())
    )
    result.verify()
    return result


@dataclass(frozen=True)
class M336K8SourceDomainCompatibilityReceipt:
    schema_version: int
    contract_role: str
    controller_startup_binding_hash: str
    persistent_capsule_source_binding_hash: str
    controller_project_source_identity: str
    capsule_project_source_identity: str
    full_project_identity_equality_required: bool
    full_project_identity_difference_count: int
    bridge_surface_manifest_hash: str
    bridge_changed_entry_count: int
    bridge_schema_incompatibility_count: int
    controller_manifest_origin_valid: bool
    capsule_manifest_origin_valid: bool
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K8_SOURCE_DOMAIN_COMPATIBILITY_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        passed = (
            self.full_project_identity_equality_required is False
            and self.bridge_changed_entry_count == 0
            and self.bridge_schema_incompatibility_count == 0
            and self.controller_manifest_origin_valid
            and self.capsule_manifest_origin_valid
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(
                not _is_hash(item)
                for item in (
                    self.controller_startup_binding_hash,
                    self.persistent_capsule_source_binding_hash,
                    self.controller_project_source_identity,
                    self.capsule_project_source_identity,
                    self.bridge_surface_manifest_hash,
                    self.receipt_hash,
                )
            )
            or self.full_project_identity_difference_count
            != int(
                self.controller_project_source_identity
                != self.capsule_project_source_identity
            )
            or self.status != ("PASS" if passed else "FAIL")
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 source-domain compatibility is invalid")

    @classmethod
    def build(
        cls,
        controller: M336K8ControllerStartupBinding,
        capsule: M336K8PersistentCapsuleSourceBinding,
        bridge: M336K8BridgeSurfaceManifest,
    ) -> Self:
        controller.verify()
        capsule.verify()
        bridge.verify()
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "controller_startup_binding_hash": controller.binding_hash,
            "persistent_capsule_source_binding_hash": capsule.binding_hash,
            "controller_project_source_identity": controller.controller_project_source_identity,
            "capsule_project_source_identity": capsule.capsule_project_source_identity,
            "full_project_identity_equality_required": False,
            "full_project_identity_difference_count": int(
                controller.controller_project_source_identity
                != capsule.capsule_project_source_identity
            ),
            "bridge_surface_manifest_hash": bridge.manifest_hash,
            "bridge_changed_entry_count": bridge.changed_entry_count,
            "bridge_schema_incompatibility_count": bridge.schema_incompatibility_count,
            "controller_manifest_origin_valid": True,
            "capsule_manifest_origin_valid": True,
            "status": "PASS",
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict_fields(value, cls, "source-domain compatibility"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K8FreezeAssemblyEntry:
    component_name: str
    source_domain: str
    producer_role: str
    expected_producer_commit_role: str
    typed_loader: str
    semantic_hash_field: str
    consumer_roles: tuple[str, ...]
    byte_equality_with_other_domain_required: bool

    def canonical_object(self) -> dict[str, Any]:
        return asdict(self)

    def verify(self) -> None:
        if (
            not self.component_name
            or self.source_domain not in M336K8_SOURCE_DOMAINS
            or not self.producer_role
            or not self.expected_producer_commit_role
            or not self.typed_loader
            or not self.semantic_hash_field
            or not self.consumer_roles
            or type(self.byte_equality_with_other_domain_required) is not bool
        ):
            raise M336K2ProtocolError("M336K8 freeze assembly entry is invalid")


_ASSEMBLY_COMPONENTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "controller_python_environment_manifest",
        CURRENT_IMPLEMENTATION_CONTROLLER,
        "CONTROLLER_STARTUP_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "controller_executable_dependency_manifest",
        CURRENT_IMPLEMENTATION_CONTROLLER,
        "CONTROLLER_EXECUTABLE_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "controller_source_identity_policy",
        PHASE_NEUTRAL_SHARED_POLICY,
        "SOURCE_IDENTITY_POLICY_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "controller_source_identity_receipt",
        CURRENT_IMPLEMENTATION_CONTROLLER,
        "SOURCE_IDENTITY_RECEIPT_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "controller_startup_binding",
        CURRENT_IMPLEMENTATION_CONTROLLER,
        "CONTROLLER_STARTUP_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "persistent_capsule_python_environment_manifest",
        PERSISTENT_KARINA_RUNTIME_CAPSULE,
        "PERSISTENT_CAPSULE",
        "CAPSULE_IMPLEMENTATION_TIP",
    ),
    (
        "persistent_capsule_executable_dependency_manifest",
        PERSISTENT_KARINA_RUNTIME_CAPSULE,
        "PERSISTENT_CAPSULE",
        "CAPSULE_IMPLEMENTATION_TIP",
    ),
    (
        "persistent_capsule_source_binding",
        PERSISTENT_KARINA_RUNTIME_CAPSULE,
        "PERSISTENT_CAPSULE_BINDING_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "bridge_surface_manifest",
        CROSS_DOMAIN_BRIDGE,
        "BRIDGE_SURFACE_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "source_domain_compatibility",
        CROSS_DOMAIN_BRIDGE,
        "SOURCE_DOMAIN_COMPATIBILITY_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "resource_budget_policy",
        PHASE_NEUTRAL_SHARED_POLICY,
        "M336K7_FROZEN_RESOURCE_CONTRACT",
        "HISTORICAL_F32",
    ),
    (
        "resource_observation",
        PHASE_NEUTRAL_SHARED_POLICY,
        "M336K7_FROZEN_RESOURCE_CONTRACT",
        "HISTORICAL_F32",
    ),
    (
        "storage_reservation",
        PHASE_NEUTRAL_SHARED_POLICY,
        "M336K7_FROZEN_RESOURCE_CONTRACT",
        "HISTORICAL_F32",
    ),
    (
        "resource_gate",
        PHASE_NEUTRAL_SHARED_POLICY,
        "M336K7_FROZEN_RESOURCE_CONTRACT",
        "HISTORICAL_F32",
    ),
    (
        "capsule_binding_set",
        PERSISTENT_KARINA_RUNTIME_CAPSULE,
        "M336K7_CAPSULE_BINDING_SET",
        "HISTORICAL_F32",
    ),
    (
        "legacy_capsule_compatibility",
        CROSS_DOMAIN_BRIDGE,
        "M336K7_LEGACY_COMPATIBILITY",
        "HISTORICAL_F32",
    ),
    (
        "capsule_liveness",
        PERSISTENT_KARINA_RUNTIME_CAPSULE,
        "PERSISTENT_CAPSULE_LIVENESS",
        "LIVE_PREFREEZE",
    ),
    (
        "legacy_controller_alias_receipt",
        CROSS_DOMAIN_BRIDGE,
        "LEGACY_ALIAS_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "route_identity_bundle",
        CURRENT_IMPLEMENTATION_CONTROLLER,
        "CURRENT_ROUTE_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "final_authorization",
        CURRENT_IMPLEMENTATION_CONTROLLER,
        "CURRENT_AUTHORIZATION_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
    (
        "post_freeze_input_bundle",
        CROSS_DOMAIN_BRIDGE,
        "POST_FREEZE_BUNDLE_BUILDER",
        "IMPLEMENTATION_TIP",
    ),
)


def _default_hash_field(name: str) -> str:
    return {
        "controller_python_environment_manifest": "environment_manifest_hash",
        "controller_executable_dependency_manifest": "manifest_hash",
        "controller_source_identity_policy": "policy_hash",
        "controller_source_identity_receipt": "receipt_hash",
        "controller_startup_binding": "binding_hash",
        "persistent_capsule_python_environment_manifest": "identity_hash",
        "persistent_capsule_executable_dependency_manifest": "manifest_hash",
        "persistent_capsule_source_binding": "binding_hash",
        "bridge_surface_manifest": "manifest_hash",
        "source_domain_compatibility": "receipt_hash",
        "resource_budget_policy": "policy_hash",
        "resource_observation": "observation_hash",
        "storage_reservation": "receipt_hash",
        "resource_gate": "receipt_hash",
        "capsule_binding_set": "binding_set_hash",
        "legacy_capsule_compatibility": "receipt_hash",
        "capsule_liveness": "receipt_hash",
        "legacy_controller_alias_receipt": "receipt_hash",
        "route_identity_bundle": "bundle_hash",
        "final_authorization": "authorization_hash",
        "post_freeze_input_bundle": "bundle_hash",
    }[name]


def _build_assembly_entries() -> tuple[M336K8FreezeAssemblyEntry, ...]:
    return tuple(
        M336K8FreezeAssemblyEntry(
            component_name=name,
            source_domain=domain,
            producer_role=producer,
            expected_producer_commit_role=commit_role,
            typed_loader=f"load_{name}",
            semantic_hash_field=_default_hash_field(name),
            consumer_roles=("POST_FREEZE_VALIDATOR", "COMPATIBILITY_GATE_V2"),
            byte_equality_with_other_domain_required=name
            in {"legacy_controller_alias_receipt", "bridge_surface_manifest"},
        )
        for name, domain, producer, commit_role in _ASSEMBLY_COMPONENTS
    )


@dataclass(frozen=True)
class M336K8FreezeAssemblyPlan:
    schema_version: int
    contract_role: str
    entries: tuple[M336K8FreezeAssemblyEntry, ...]
    component_count: int
    producer_origin_map_hash: str
    plan_hash: str

    ROLE: ClassVar[str] = "M336K8_FREEZE_ASSEMBLY_PLAN"

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "entries": tuple(item.canonical_object() for item in self.entries),
            "component_count": self.component_count,
            "producer_origin_map_hash": self.producer_origin_map_hash,
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "plan_hash": self.plan_hash}

    def verify(self) -> None:
        for item in self.entries:
            item.verify()
        origins = tuple(
            (
                item.component_name,
                item.source_domain,
                item.producer_role,
                item.expected_producer_commit_role,
            )
            for item in self.entries
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.component_count != len(self.entries)
            or len({item.component_name for item in self.entries}) != len(self.entries)
            or self.entries != _build_assembly_entries()
            or self.producer_origin_map_hash != content_hash(origins)
            or self.plan_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 freeze assembly plan is invalid")

    @classmethod
    def build(cls) -> Self:
        entries = _build_assembly_entries()
        origins = tuple(
            (
                item.component_name,
                item.source_domain,
                item.producer_role,
                item.expected_producer_commit_role,
            )
            for item in entries
        )
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "entries": entries,
            "component_count": len(entries),
            "producer_origin_map_hash": content_hash(origins),
        }
        temporary = cls(**body, plan_hash="0" * 64)
        result = cls(**body, plan_hash=content_hash(temporary._body()))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, cls, "freeze assembly plan")
        result = cls(
            **{
                **strict,
                "entries": tuple(
                    M336K8FreezeAssemblyEntry(
                        **{**item, "consumer_roles": tuple(item["consumer_roles"])}
                    )
                    for item in strict["entries"]
                ),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K8FreezeAssemblyReceipt:
    schema_version: int
    contract_role: str
    assembly_plan_hash: str
    producer_origin_map_hash: str
    component_count: int
    controller_domain_component_count: int
    capsule_domain_component_count: int
    cross_domain_component_count: int
    shared_policy_component_count: int
    wrong_origin_count: int
    missing_component_count: int
    extra_component_count: int
    semantic_binding_mismatch_count: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K8_FREEZE_ASSEMBLY_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        failures = (
            self.wrong_origin_count,
            self.missing_component_count,
            self.extra_component_count,
            self.semantic_binding_mismatch_count,
        )
        domain_total = (
            self.controller_domain_component_count
            + self.capsule_domain_component_count
            + self.cross_domain_component_count
            + self.shared_policy_component_count
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(
                not _is_hash(item)
                for item in (
                    self.assembly_plan_hash,
                    self.producer_origin_map_hash,
                    self.receipt_hash,
                )
            )
            or domain_total != self.component_count
            or any(type(item) is not int or item < 0 for item in failures)
            or self.status != ("PASS" if not any(failures) else "FAIL")
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 freeze assembly receipt is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict_fields(value, cls, "freeze assembly receipt"))
        result.verify()
        return result


class M336K8FreezeInputAssembler:
    """The only authority for rehearsal and official component origins."""

    @staticmethod
    def assemble(
        *,
        plan: M336K8FreezeAssemblyPlan,
        component_values: Mapping[str, Mapping[str, Any]],
        component_origins: Mapping[str, str],
        semantic_verifier: Callable[[str, Mapping[str, Mapping[str, Any]]], int],
    ) -> M336K8FreezeAssemblyReceipt:
        plan.verify()
        planned = {item.component_name: item for item in plan.entries}
        supplied = set(component_values)
        missing = set(planned) - supplied
        extra = supplied - set(planned)
        wrong_origin = sum(
            component_origins.get(name) != entry.source_domain
            for name, entry in planned.items()
            if name in supplied
        )
        semantic_mismatches = 0
        semantic_values = {
            **{name: dict(value) for name, value in component_values.items()},
            "freeze_assembly_plan": plan.canonical_object(),
        }
        for name, entry in planned.items():
            if name not in supplied:
                continue
            value = component_values[name]
            _hashed_body(value, entry.semantic_hash_field)
            semantic_mismatches += semantic_verifier(name, semantic_values)
        counts = {
            CURRENT_IMPLEMENTATION_CONTROLLER: 0,
            PERSISTENT_KARINA_RUNTIME_CAPSULE: 0,
            CROSS_DOMAIN_BRIDGE: 0,
            PHASE_NEUTRAL_SHARED_POLICY: 0,
        }
        for item in plan.entries:
            counts[item.source_domain] += 1
        body = {
            "schema_version": 1,
            "contract_role": M336K8FreezeAssemblyReceipt.ROLE,
            "assembly_plan_hash": plan.plan_hash,
            "producer_origin_map_hash": plan.producer_origin_map_hash,
            "component_count": len(plan.entries),
            "controller_domain_component_count": counts[
                CURRENT_IMPLEMENTATION_CONTROLLER
            ],
            "capsule_domain_component_count": counts[PERSISTENT_KARINA_RUNTIME_CAPSULE],
            "cross_domain_component_count": counts[CROSS_DOMAIN_BRIDGE],
            "shared_policy_component_count": counts[PHASE_NEUTRAL_SHARED_POLICY],
            "wrong_origin_count": wrong_origin,
            "missing_component_count": len(missing),
            "extra_component_count": len(extra),
            "semantic_binding_mismatch_count": semantic_mismatches,
            "status": "PASS"
            if not (wrong_origin or missing or extra or semantic_mismatches)
            else "FAIL",
        }
        result = M336K8FreezeAssemblyReceipt(**body, receipt_hash=content_hash(body))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K8LegacyControllerAliasReceipt:
    schema_version: int
    contract_role: str
    controller_python_environment_manifest_hash: str
    legacy_python_environment_manifest_alias_hash: str
    controller_executable_dependency_manifest_hash: str
    legacy_executable_dependency_manifest_alias_hash: str
    python_environment_byte_difference_count: int
    python_environment_semantic_difference_count: int
    executable_dependency_byte_difference_count: int
    executable_dependency_semantic_difference_count: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K8_LEGACY_CONTROLLER_ALIAS_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        differences = (
            self.python_environment_byte_difference_count,
            self.python_environment_semantic_difference_count,
            self.executable_dependency_byte_difference_count,
            self.executable_dependency_semantic_difference_count,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(
                not _is_hash(item)
                for item in (
                    self.controller_python_environment_manifest_hash,
                    self.legacy_python_environment_manifest_alias_hash,
                    self.controller_executable_dependency_manifest_hash,
                    self.legacy_executable_dependency_manifest_alias_hash,
                    self.receipt_hash,
                )
            )
            or any(differences)
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 legacy controller aliases are invalid")

    @classmethod
    def build(
        cls,
        *,
        controller_environment: Mapping[str, Any],
        legacy_environment: Mapping[str, Any],
        controller_dependencies: Mapping[str, Any],
        legacy_dependencies: Mapping[str, Any],
    ) -> Self:
        controller_environment_bytes = _canonical_bytes(controller_environment)
        legacy_environment_bytes = _canonical_bytes(legacy_environment)
        controller_dependency_bytes = _canonical_bytes(controller_dependencies)
        legacy_dependency_bytes = _canonical_bytes(legacy_dependencies)
        passed = (
            controller_environment_bytes == legacy_environment_bytes
            and controller_dependency_bytes == legacy_dependency_bytes
        )
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "controller_python_environment_manifest_hash": controller_environment[
                "environment_manifest_hash"
            ],
            "legacy_python_environment_manifest_alias_hash": legacy_environment[
                "environment_manifest_hash"
            ],
            "controller_executable_dependency_manifest_hash": controller_dependencies[
                "manifest_hash"
            ],
            "legacy_executable_dependency_manifest_alias_hash": legacy_dependencies[
                "manifest_hash"
            ],
            "python_environment_byte_difference_count": int(
                controller_environment_bytes != legacy_environment_bytes
            ),
            "python_environment_semantic_difference_count": int(
                dict(controller_environment) != dict(legacy_environment)
            ),
            "executable_dependency_byte_difference_count": int(
                controller_dependency_bytes != legacy_dependency_bytes
            ),
            "executable_dependency_semantic_difference_count": int(
                dict(controller_dependencies) != dict(legacy_dependencies)
            ),
            "status": "PASS" if passed else "FAIL",
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict_fields(value, cls, "legacy controller alias receipt"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K8PostFreezeInputBundleV2:
    schema_version: int
    contract_role: str
    controller_project_source_identity_policy_hash: str
    controller_project_source_identity_receipt_hash: str
    controller_python_environment_manifest_hash: str
    controller_executable_dependency_manifest_hash: str
    controller_startup_binding_hash: str
    persistent_capsule_binding_set_hash: str
    persistent_capsule_source_binding_hash: str
    persistent_capsule_python_environment_manifest_hash: str
    persistent_capsule_executable_dependency_manifest_hash: str
    bridge_surface_manifest_hash: str
    source_domain_compatibility_receipt_hash: str
    freeze_assembly_plan_hash: str
    freeze_assembly_receipt_hash: str
    legacy_controller_alias_receipt_hash: str
    startup_policy_hash: str
    resource_budget_policy_hash: str
    resource_observation_hash: str
    storage_reservation_receipt_hash: str
    resource_gate_receipt_hash: str
    capsule_liveness_receipt_hash: str
    capsule_content_manifest_hash: str
    capsule_lifecycle_policy_hash: str
    route_identity_bundle_hash: str
    route_registry_hash: str
    route_manifest_hash: str
    final_authorization_hash: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    archive_policy_hash: str
    terminal_policy_hash: str
    selector_policy_hash: str
    evaluator_policy_hash: str
    threshold_manifest_hash: str
    publication_contract_hash: str
    bundle_hash: str

    ROLE: ClassVar[str] = "M336K8_POST_FREEZE_INPUT_BUNDLE_V2"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("bundle_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "bundle_hash": self.bundle_hash}

    def verify(self) -> None:
        body = self._body()
        forbidden = {
            "python_environment_manifest_hash",
            "executable_dependency_manifest_hash",
        }
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.bundle_hash != content_hash(body)
            or forbidden & set(body)
        ):
            raise M336K2ProtocolError("M336K8 post-freeze bundle is invalid")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = {"schema_version": 2, "contract_role": cls.ROLE, **values}
        if set(body) != _field_names(cls) - {"bundle_hash"}:
            raise M336K2ProtocolError("M336K8 post-freeze bundle inputs changed")
        result = cls(**body, bundle_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        result = cls(**_strict_fields(value, cls, "post-freeze input bundle"))
        result.verify()
        return result


M336K8_POST_FREEZE_CONSUMED_COMPONENTS = (
    *(item[0] for item in _ASSEMBLY_COMPONENTS),
    "freeze_assembly_plan",
    "freeze_assembly_receipt",
    "frozen_contract_compatibility_v2",
)


@dataclass(frozen=True)
class M336K8FrozenContractArtifactResult:
    artifact_name: str
    source_domain: str
    producer_role: str
    producer_schema_hash: str
    consumer_schema_hash: str
    producer_field_count: int
    consumer_field_count: int
    missing_field_count: int
    extra_field_count: int
    roundtrip_difference_count: int
    semantic_check_count: int
    semantic_binding_mismatch_count: int
    producer_origin_mismatch_count: int
    consumer_coverage_count: int
    status: str


@dataclass(frozen=True)
class M336K8FrozenContractCompatibilityGateV2:
    schema_version: int
    contract_role: str
    artifacts: tuple[M336K8FrozenContractArtifactResult, ...]
    consumed_artifact_count: int
    compatibility_artifact_count: int
    uncovered_consumer_count: int
    unused_compatibility_artifact_count: int
    missing_field_count: int
    extra_field_count: int
    roundtrip_difference_count: int
    semantic_check_count: int
    semantic_binding_mismatch_count: int
    producer_origin_mismatch_count: int
    phase_specific_active_field_count: int
    mandatory_default_lookup_count: int
    direct_legacy_capsule_comparison_count: int
    status: str
    report_hash: str

    ROLE: ClassVar[str] = "M336K8_FROZEN_CONTRACT_COMPATIBILITY_GATE_V2"

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "artifacts": tuple(asdict(item) for item in self.artifacts),
            **{
                name: getattr(self, name)
                for name in _field_names(type(self))
                - {"schema_version", "contract_role", "artifacts", "report_hash"}
            },
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "report_hash": self.report_hash}

    def verify(self) -> None:
        failures = (
            self.uncovered_consumer_count,
            self.unused_compatibility_artifact_count,
            self.missing_field_count,
            self.extra_field_count,
            self.roundtrip_difference_count,
            self.semantic_binding_mismatch_count,
            self.producer_origin_mismatch_count,
            self.phase_specific_active_field_count,
            self.mandatory_default_lookup_count,
            self.direct_legacy_capsule_comparison_count,
        )
        passed = not any(failures) and all(
            item.status == "PASS" for item in self.artifacts
        )
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or self.consumed_artifact_count
            != len(M336K8_POST_FREEZE_CONSUMED_COMPONENTS)
            or self.compatibility_artifact_count != len(self.artifacts)
            or self.semantic_check_count < self.compatibility_artifact_count
            or any(type(item) is not int or item < 0 for item in failures)
            or self.status != ("PASS" if passed else "FAIL")
            or self.report_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 compatibility gate V2 is invalid")

    @classmethod
    def run(
        cls,
        *,
        plan: M336K8FreezeAssemblyPlan,
        artifacts: Mapping[
            str, tuple[Mapping[str, Any], Callable[[dict[str, Any]], Any]]
        ],
        semantic_verifier: Callable[[str, Mapping[str, Mapping[str, Any]]], int],
        current_route_sources: tuple[Path, ...],
    ) -> Self:
        plan.verify()
        expected = set(M336K8_POST_FREEZE_CONSUMED_COMPONENTS)
        supplied = set(artifacts) | {"frozen_contract_compatibility_v2"}
        origins = {item.component_name: item for item in plan.entries}
        generated_origins = {
            "freeze_assembly_plan": (
                CROSS_DOMAIN_BRIDGE,
                "FREEZE_ASSEMBLY_PLAN_BUILDER",
            ),
            "freeze_assembly_receipt": (
                CROSS_DOMAIN_BRIDGE,
                "FREEZE_INPUT_ASSEMBLER",
            ),
        }
        values = {
            name: json.loads(canonical_json(pair[0]))
            for name, pair in artifacts.items()
        }
        results = []
        for name in sorted(artifacts):
            produced, consumer = artifacts[name]
            serialized_produced = json.loads(canonical_json(produced))
            loaded = consumer(serialized_produced)
            if hasattr(loaded, "canonical_object"):
                canonical = loaded.canonical_object()
            else:
                canonical = asdict(loaded)
            producer_fields = set(produced)
            consumer_fields = set(canonical)
            missing = consumer_fields - producer_fields
            extra = producer_fields - consumer_fields
            roundtrip = int(_canonical_bytes(produced) != _canonical_bytes(canonical))
            semantic_mismatch = semantic_verifier(name, values)
            origin = origins.get(name)
            generated_origin = generated_origins.get(name)
            origin_mismatch = int(origin is None and generated_origin is None)
            source_domain = (
                origin.source_domain
                if origin is not None
                else generated_origin[0]
                if generated_origin is not None
                else HISTORICAL_READ_ONLY
            )
            producer_role = (
                origin.producer_role
                if origin is not None
                else generated_origin[1]
                if generated_origin is not None
                else "UNDECLARED"
            )
            results.append(
                M336K8FrozenContractArtifactResult(
                    artifact_name=name,
                    source_domain=source_domain,
                    producer_role=producer_role,
                    producer_schema_hash=content_hash(tuple(sorted(producer_fields))),
                    consumer_schema_hash=content_hash(tuple(sorted(consumer_fields))),
                    producer_field_count=len(producer_fields),
                    consumer_field_count=len(consumer_fields),
                    missing_field_count=len(missing),
                    extra_field_count=len(extra),
                    roundtrip_difference_count=roundtrip,
                    semantic_check_count=1,
                    semantic_binding_mismatch_count=semantic_mismatch,
                    producer_origin_mismatch_count=origin_mismatch,
                    consumer_coverage_count=1,
                    status=(
                        "PASS"
                        if not (
                            missing
                            or extra
                            or roundtrip
                            or semantic_mismatch
                            or origin_mismatch
                        )
                        else "FAIL"
                    ),
                )
            )
        # The report validates its own fixed schema without recursively binding
        # its report hash. This closes the real validator's self-consumption.
        gate_fields = tuple(sorted(_field_names(cls)))
        results.append(
            M336K8FrozenContractArtifactResult(
                artifact_name="frozen_contract_compatibility_v2",
                source_domain=CROSS_DOMAIN_BRIDGE,
                producer_role="COMPATIBILITY_GATE_V2",
                producer_schema_hash=content_hash(gate_fields),
                consumer_schema_hash=content_hash(gate_fields),
                producer_field_count=len(gate_fields),
                consumer_field_count=len(gate_fields),
                missing_field_count=0,
                extra_field_count=0,
                roundtrip_difference_count=0,
                semantic_check_count=1,
                semantic_binding_mismatch_count=0,
                producer_origin_mismatch_count=0,
                consumer_coverage_count=1,
                status="PASS",
            )
        )
        phase_count, mandatory_defaults, legacy_comparisons = _source_static_counts(
            current_route_sources
        )
        totals = {
            "uncovered_consumer_count": len(expected - supplied),
            "unused_compatibility_artifact_count": len(supplied - expected),
            "missing_field_count": sum(item.missing_field_count for item in results),
            "extra_field_count": sum(item.extra_field_count for item in results),
            "roundtrip_difference_count": sum(
                item.roundtrip_difference_count for item in results
            ),
            "semantic_check_count": sum(item.semantic_check_count for item in results),
            "semantic_binding_mismatch_count": sum(
                item.semantic_binding_mismatch_count for item in results
            ),
            "producer_origin_mismatch_count": sum(
                item.producer_origin_mismatch_count for item in results
            ),
            "phase_specific_active_field_count": phase_count,
            "mandatory_default_lookup_count": mandatory_defaults,
            "direct_legacy_capsule_comparison_count": legacy_comparisons,
        }
        failures = tuple(
            value for name, value in totals.items() if name != "semantic_check_count"
        )
        body = {
            "schema_version": 2,
            "contract_role": cls.ROLE,
            "artifacts": tuple(results),
            "consumed_artifact_count": len(expected),
            "compatibility_artifact_count": len(results),
            **totals,
            "status": (
                "PASS"
                if not any(failures) and all(item.status == "PASS" for item in results)
                else "FAIL"
            ),
        }
        temporary = cls(**body, report_hash="0" * 64)
        result = cls(**body, report_hash=content_hash(temporary._body()))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, cls, "compatibility gate V2")
        result = cls(
            **{
                **strict,
                "artifacts": tuple(
                    M336K8FrozenContractArtifactResult(**item)
                    for item in strict["artifacts"]
                ),
            }
        )
        result.verify()
        return result


def m336k8_semantic_binding_mismatches(
    name: str, values: Mapping[str, Mapping[str, Any]]
) -> int:
    """Execute cross-artifact semantic relations for assembler and gate."""

    mismatches = 0
    policy = values.get("controller_source_identity_policy", {})
    receipt = values.get("controller_source_identity_receipt", {})
    environment = values.get("controller_python_environment_manifest", {})
    dependency = values.get("controller_executable_dependency_manifest", {})
    startup = values.get("controller_startup_binding", {})
    capsule_binding = values.get("capsule_binding_set", {})
    capsule = values.get("persistent_capsule_source_binding", {})
    capsule_environment = values.get(
        "persistent_capsule_python_environment_manifest", {}
    )
    capsule_dependency = values.get(
        "persistent_capsule_executable_dependency_manifest", {}
    )
    capsule_liveness = values.get("capsule_liveness", {})
    bridge = values.get("bridge_surface_manifest", {})
    compatibility = values.get("source_domain_compatibility", {})
    assembly_plan = values.get("freeze_assembly_plan", {})
    assembly_receipt = values.get("freeze_assembly_receipt", {})
    alias = values.get("legacy_controller_alias_receipt", {})
    if name == "controller_source_identity_receipt":
        mismatches += int(
            receipt.get("source_identity_policy_hash") != policy.get("policy_hash")
        )
        mismatches += int(
            receipt.get("committed_project_source_identity")
            != receipt.get("live_project_source_identity")
        )
    elif name == "controller_python_environment_manifest":
        mismatches += int(
            environment.get("source_domain") != CURRENT_IMPLEMENTATION_CONTROLLER
        )
        mismatches += int(
            environment.get("project_source_identity_hash")
            != receipt.get("live_project_source_identity")
        )
        mismatches += int(
            environment.get("exact_implementation_tip")
            != receipt.get("exact_implementation_tip")
        )
    elif name == "controller_executable_dependency_manifest":
        mismatches += int(
            dependency.get("environment_identity_hash")
            != environment.get("environment_manifest_hash")
        )
        mismatches += int(
            dependency.get("source_identity_hash")
            != receipt.get("live_project_source_identity")
        )
    elif name == "controller_startup_binding":
        relations = (
            (
                startup.get("project_source_identity_policy_hash"),
                policy.get("policy_hash"),
            ),
            (
                startup.get("project_source_identity_receipt_hash"),
                receipt.get("receipt_hash"),
            ),
            (
                startup.get("controller_project_source_identity"),
                receipt.get("live_project_source_identity"),
            ),
            (
                startup.get("controller_python_environment_manifest_hash"),
                environment.get("environment_manifest_hash"),
            ),
            (
                startup.get("controller_executable_dependency_manifest_hash"),
                dependency.get("manifest_hash"),
            ),
        )
        mismatches += sum(left != right for left, right in relations)
        mismatches += int(
            startup.get("source_domain") != CURRENT_IMPLEMENTATION_CONTROLLER
        )
        mismatches += int(
            startup.get("exact_implementation_tip")
            != receipt.get("exact_implementation_tip")
        )
    elif name == "persistent_capsule_source_binding":
        mismatches += int(
            capsule.get("source_domain") != PERSISTENT_KARINA_RUNTIME_CAPSULE
        )
        relations = (
            (
                capsule.get("persistent_capsule_binding_set_hash"),
                capsule_binding.get("binding_set_hash"),
            ),
            (
                capsule.get("capsule_implementation_tip"),
                capsule_binding.get("implementation_tip"),
            ),
            (
                capsule.get("capsule_python_environment_manifest_hash"),
                capsule_environment.get("identity_hash"),
            ),
            (
                capsule.get("capsule_executable_dependency_manifest_hash"),
                capsule_dependency.get("manifest_hash"),
            ),
            (
                capsule.get("capsule_identity_hash"),
                capsule_binding.get("capsule_identity_hash"),
            ),
            (
                capsule.get("capsule_content_manifest_hash"),
                capsule_binding.get("capsule_content_manifest_hash"),
            ),
            (
                capsule.get("capsule_lifecycle_policy_hash"),
                capsule_binding.get("capsule_lifecycle_policy_hash"),
            ),
            (
                capsule.get("capsule_liveness_receipt_hash"),
                capsule_liveness.get("receipt_hash"),
            ),
            (
                capsule.get("persistent_public_receipt_hash"),
                capsule_binding.get("persistent_capsule_public_receipt_hash"),
            ),
            (
                capsule.get("legacy_public_receipt_hash"),
                capsule_binding.get("legacy_public_capsule_receipt_hash"),
            ),
            (
                capsule.get("stable_host_identity_hash"),
                capsule_binding.get("stable_karina_host_identity_hash"),
            ),
            (
                capsule.get("bridge_surface_manifest_hash"),
                bridge.get("manifest_hash"),
            ),
        )
        mismatches += sum(left != right for left, right in relations)
    elif name == "bridge_surface_manifest":
        mismatches += int(
            bridge.get("controller_tree_hash") != bridge.get("capsule_tree_hash")
        )
        mismatches += int(bool(bridge.get("changed_entry_count")))
        mismatches += int(bool(bridge.get("schema_incompatibility_count")))
    elif name == "source_domain_compatibility":
        relations = (
            (
                compatibility.get("controller_startup_binding_hash"),
                startup.get("binding_hash"),
            ),
            (
                compatibility.get("persistent_capsule_source_binding_hash"),
                capsule.get("binding_hash"),
            ),
            (
                compatibility.get("bridge_surface_manifest_hash"),
                bridge.get("manifest_hash"),
            ),
        )
        mismatches += sum(left != right for left, right in relations)
        mismatches += int(
            compatibility.get("full_project_identity_equality_required") is not False
        )
        mismatches += int(
            compatibility.get("controller_project_source_identity")
            != receipt.get("live_project_source_identity")
        )
        mismatches += int(
            compatibility.get("capsule_project_source_identity")
            != capsule.get("capsule_project_source_identity")
        )
        mismatches += int(
            compatibility.get("full_project_identity_difference_count")
            != int(
                receipt.get("live_project_source_identity")
                != capsule.get("capsule_project_source_identity")
            )
        )
        mismatches += int(
            compatibility.get("controller_manifest_origin_valid") is not True
        )
        mismatches += int(
            compatibility.get("capsule_manifest_origin_valid") is not True
        )
    elif name == "legacy_controller_alias_receipt":
        mismatches += int(
            alias.get("controller_python_environment_manifest_hash")
            != environment.get("environment_manifest_hash")
        )
        mismatches += int(
            alias.get("controller_executable_dependency_manifest_hash")
            != dependency.get("manifest_hash")
        )
        mismatches += int(
            alias.get("legacy_python_environment_manifest_alias_hash")
            != environment.get("environment_manifest_hash")
        )
        mismatches += int(
            alias.get("legacy_executable_dependency_manifest_alias_hash")
            != dependency.get("manifest_hash")
        )
    elif name == "freeze_assembly_receipt":
        mismatches += int(
            assembly_receipt.get("assembly_plan_hash") != assembly_plan.get("plan_hash")
        )
        mismatches += int(
            assembly_receipt.get("producer_origin_map_hash")
            != assembly_plan.get("producer_origin_map_hash")
        )
    elif name == "post_freeze_input_bundle":
        post = values[name]
        relations = {
            "controller_project_source_identity_policy_hash": policy.get("policy_hash"),
            "controller_project_source_identity_receipt_hash": receipt.get(
                "receipt_hash"
            ),
            "controller_python_environment_manifest_hash": environment.get(
                "environment_manifest_hash"
            ),
            "controller_executable_dependency_manifest_hash": dependency.get(
                "manifest_hash"
            ),
            "controller_startup_binding_hash": startup.get("binding_hash"),
            "persistent_capsule_source_binding_hash": capsule.get("binding_hash"),
            "bridge_surface_manifest_hash": bridge.get("manifest_hash"),
            "source_domain_compatibility_receipt_hash": compatibility.get(
                "receipt_hash"
            ),
            "freeze_assembly_plan_hash": assembly_plan.get("plan_hash"),
            "legacy_controller_alias_receipt_hash": alias.get("receipt_hash"),
        }
        if assembly_receipt:
            relations["freeze_assembly_receipt_hash"] = assembly_receipt.get(
                "receipt_hash"
            )
        mismatches += sum(
            post.get(field) != expected for field, expected in relations.items()
        )
    return mismatches


def _source_static_counts(paths: tuple[Path, ...]) -> tuple[int, int, int]:
    phase_tokens = ("f30", "f31", "f32", "f33", "pre_f3", "post_f3")
    phase_fields = 0
    default_lookups = 0
    direct_comparisons = 0
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                phase_fields += int(
                    any(token in node.target.id.casefold() for token in phase_tokens)
                )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
            ):
                default_lookups += 1
            if isinstance(node, ast.Compare):
                rendered = ast.dump(node, include_attributes=False)
                direct_comparisons += int(
                    "capsule_project_source_identity" in rendered
                    and "controller_project_source_identity" in rendered
                    and any(isinstance(item, ast.Eq) for item in node.ops)
                )
    return phase_fields, default_lookups, direct_comparisons


def require_m336k8_frozen_bytes(expected: bytes, consumed: bytes) -> None:
    if expected != consumed:
        raise M336K2ProtocolError("M336K8 committed frozen bytes were replaced")


def forbid_m336k8_post_freeze_mutation(
    *, exact_freeze_sha: str, operation: str
) -> None:
    if exact_freeze_sha != "0" * 40 and operation in {
        "CLEANUP",
        "CAPSULE_RECREATE",
        "CAPSULE_REMOVE",
        "FROZEN_INPUT_REGENERATE",
    }:
        raise M336K2ProtocolError("M336K8 mutation is forbidden after freeze")


def require_m336k8_evidence_only_diff(changed_paths: tuple[str, ...]) -> None:
    protected = (*M336K8_TRACKED_ROOTS, *M336K8_TRACKED_FILE_NAMES)
    if any(
        path == scope or path.startswith(scope + "/")
        for path in changed_paths
        for scope in protected
    ):
        raise M336K2ProtocolError("M336K8 evidence-only commit changed source")


def require_m336k8_execution_authority(
    *, post_freeze_validation_accepted: bool, operation: str
) -> None:
    guarded = {
        "RELEASE_STORAGE_RESERVATION",
        "INVOKE_FINAL_CONTROLLER",
    }
    if operation in guarded and post_freeze_validation_accepted is not True:
        raise M336K2ProtocolError("M336K8 execution lacks accepted validate-only")
