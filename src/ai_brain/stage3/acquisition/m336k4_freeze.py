"""Prospective and committed F29 freeze for M-33.6k.4."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_REQUIRED_FREEZE_COMPONENTS,
    M336K2ProtocolError,
    m336k2_minimal_environment,
)

M336K4_READY_STATUS = "READY_FOR_TYPED_FINAL_JAVA_EXECUTION_V4"
M336K4_BRANCH = "exp/stage3-m336k4-typed-final-identity-v13"
M336K4_BRANCH_REF = f"refs/heads/{M336K4_BRANCH}"
M336K4_F29_ROOT = Path("artifacts/m336k4/f29-freeze")
M336K4_REQUIRED_FREEZE_COMPONENTS = frozenset(
    set(M336K2_REQUIRED_FREEZE_COMPONENTS)
    | {
        "typed_route_registry",
        "typed_schema_registry",
        "typed_route_manifest",
        "route_identity_bundle",
        "evaluator_policy",
        "canonical_request_builder_identity",
    }
)
_SHA = re.compile(r"[0-9a-f]{40}")
_HASH = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class M336K4FrozenComponent:
    name: str
    relative_path: str
    bytes_hash: str
    byte_count: int


@dataclass(frozen=True)
class M336K4FreezeManifest:
    schema_version: int
    contract_role: str
    implementation_tip: str
    exact_q29_sha: str
    exact_f29_sha: str
    committed_f29_tree: str
    readiness_hash: str
    authorization_hash: str
    route_hash: str
    route_identity_bundle_hash: str
    canonical_request_builder_hash: str
    components: tuple[M336K4FrozenComponent, ...]
    self_reference_safe_exclusions: tuple[str, ...]
    prospective_freeze_tree_hash: str
    manifest_hash: str

    @property
    def exact_q28_sha(self) -> str:
        return self.exact_q29_sha

    @property
    def exact_f28_sha(self) -> str:
        return self.exact_f29_sha

    @property
    def committed_f28_tree(self) -> str:
        return self.committed_f29_tree

    def canonical_object(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "implementation_tip": self.implementation_tip,
            "exact_q29_sha": self.exact_q29_sha,
            "exact_f29_sha": self.exact_f29_sha,
            "committed_f29_tree": self.committed_f29_tree,
            "readiness_hash": self.readiness_hash,
            "authorization_hash": self.authorization_hash,
            "route_hash": self.route_hash,
            "route_identity_bundle_hash": self.route_identity_bundle_hash,
            "canonical_request_builder_hash": self.canonical_request_builder_hash,
            "components": tuple(
                {
                    "name": item.name,
                    "relative_path": item.relative_path,
                    "bytes_hash": item.bytes_hash,
                    "byte_count": item.byte_count,
                }
                for item in self.components
            ),
            "self_reference_safe_exclusions": self.self_reference_safe_exclusions,
            "prospective_freeze_tree_hash": self.prospective_freeze_tree_hash,
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, value: dict) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K4 freeze manifest fields changed")
        result = cls(
            **{
                **value,
                "components": tuple(
                    M336K4FrozenComponent(**item)
                    for item in value.get("components", ())
                ),
                "self_reference_safe_exclusions": tuple(
                    value.get("self_reference_safe_exclusions", ())
                ),
            }
        )
        return result


@dataclass(frozen=True)
class M336K4CommittedFreezeAttestation:
    schema_version: int
    exact_f29_sha: str
    exact_q29_parent: str
    committed_tree_hash: str
    prospective_freeze_tree_hash: str
    prospective_tree_matches: bool
    route_identity_bundle_hash: str
    authorization_hash: str
    route_hash: str
    implementation_change_count: int
    merge_count: int
    head_upstream_remote_equal: bool
    worktree_clean: bool
    status: str
    attestation_hash: str

    @property
    def exact_f28_sha(self) -> str:
        return self.exact_f29_sha

    @property
    def exact_q28_parent(self) -> str:
        return self.exact_q29_parent


def verify_complete_m336k4_freeze(
    root: Path,
    manifest: M336K4FreezeManifest,
    *,
    allow_prospective_f29: bool = False,
) -> None:
    if (
        manifest.schema_version != 2
        or manifest.contract_role != "M336K4_F29_TYPED_FREEZE_V2"
        or {item.name for item in manifest.components}
        != M336K4_REQUIRED_FREEZE_COMPONENTS
        or len(manifest.components) != len(M336K4_REQUIRED_FREEZE_COMPONENTS)
    ):
        raise M336K2ProtocolError("M336K4 frozen component closure changed")
    for item in manifest.components:
        path = root.joinpath(*Path(item.relative_path).parts)
        if (
            not _safe_relative(item.relative_path)
            or not path.is_file()
            or path.stat().st_size != item.byte_count
            or bytes_hash(path.read_bytes()) != item.bytes_hash
        ):
            raise M336K2ProtocolError(f"M336K4 frozen component changed: {item.name}")
    body = manifest.canonical_object()
    claimed = body.pop("manifest_hash")
    hashes = (
        manifest.readiness_hash,
        manifest.authorization_hash,
        manifest.route_hash,
        manifest.route_identity_bundle_hash,
        manifest.canonical_request_builder_hash,
        manifest.prospective_freeze_tree_hash,
        claimed,
    )
    if (
        _SHA.fullmatch(manifest.implementation_tip) is None
        or _SHA.fullmatch(manifest.exact_q29_sha) is None
        or any(_HASH.fullmatch(value) is None for value in hashes)
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K4 freeze manifest binding is invalid")
    prospective = manifest.exact_f29_sha == "0" * 40
    prospective_tree = manifest.committed_f29_tree == "0" * 40
    if prospective != prospective_tree or (prospective and not allow_prospective_f29):
        raise M336K2ProtocolError("M336K4 F29 commit binding is invalid")


def materialize_m336k4_f29(
    *,
    repository: Path,
    git_executable: Path,
    exact_implementation_tip: str,
    exact_q29_sha: str,
    readiness: Path,
    component_sources: dict[str, Path],
    output: Path,
    expected_branch: str = M336K4_BRANCH,
    freeze_relative_root: str = M336K4_F29_ROOT.as_posix(),
) -> dict:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    destination = output.resolve(strict=False)
    if (
        destination.exists()
        or set(component_sources) != M336K4_REQUIRED_FREEZE_COMPONENTS
        or destination.relative_to(root).as_posix() != freeze_relative_root
    ):
        raise M336K2ProtocolError("M336K4 F29 destination/component set changed")
    _verify_q29_lineage(
        root, git, exact_implementation_tip, exact_q29_sha, expected_branch
    )
    readiness_value = _verified_object(readiness, "readiness_hash")
    if (
        readiness_value.get("status") != M336K4_READY_STATUS
        or readiness_value.get("exact_implementation_tip") != exact_implementation_tip
        or readiness_value.get("official_one_shot_counter_count") != 0
        or readiness_value.get("new_final_source_body_bytes") != 0
    ):
        raise M336K2ProtocolError("M336K4 Q29 readiness is not sealed and unspent")
    destination.mkdir(parents=True)
    try:
        component_root = destination / "components"
        component_root.mkdir()
        components = []
        for index, name in enumerate(sorted(component_sources)):
            source = component_sources[name].resolve(strict=True)
            _reject_metadata(source)
            target = component_root / f"{index:02d}-{name}.json"
            shutil.copyfile(source, target)
            components.append(
                M336K4FrozenComponent(
                    name=name,
                    relative_path=target.relative_to(root).as_posix(),
                    bytes_hash=bytes_hash(target.read_bytes()),
                    byte_count=target.stat().st_size,
                )
            )
        rows = tuple(
            (item.relative_path, item.byte_count, item.bytes_hash)
            for item in components
        )
        frozen_body = {
            "schema_version": 2,
            "contract_role": "M336K4_F29_FROZEN_FILE_MANIFEST",
            "files": rows,
            "file_count": len(rows),
        }
        (destination / "frozen_file_manifest.json").write_text(
            canonical_json(
                {**frozen_body, "frozen_file_manifest_hash": content_hash(frozen_body)}
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        prospective = content_hash(_tree_rows(destination))
        authorization_hash = _semantic_hash(
            component_sources["final_authorization"], "authorization_hash"
        )
        route_hash = _semantic_hash(
            component_sources["typed_route_manifest"], "manifest_hash"
        )
        bundle_hash = _semantic_hash(
            component_sources["route_identity_bundle"], "bundle_hash"
        )
        builder_hash = _semantic_hash(
            component_sources["canonical_request_builder_identity"], "builder_hash"
        )
        values = {
            "schema_version": 2,
            "contract_role": "M336K4_F29_TYPED_FREEZE_V2",
            "implementation_tip": exact_implementation_tip,
            "exact_q29_sha": exact_q29_sha,
            "exact_f29_sha": "0" * 40,
            "committed_f29_tree": "0" * 40,
            "readiness_hash": readiness_value["readiness_hash"],
            "authorization_hash": authorization_hash,
            "route_hash": route_hash,
            "route_identity_bundle_hash": bundle_hash,
            "canonical_request_builder_hash": builder_hash,
            "components": tuple(components),
            "self_reference_safe_exclusions": (
                f"{freeze_relative_root}/freeze_manifest.json",
                f"{freeze_relative_root}/f29_build_receipt.json",
            ),
            "prospective_freeze_tree_hash": prospective,
        }
        temporary = M336K4FreezeManifest(**values, manifest_hash="0" * 64)
        manifest = M336K4FreezeManifest(
            **values,
            manifest_hash=content_hash(
                {
                    k: v
                    for k, v in temporary.canonical_object().items()
                    if k != "manifest_hash"
                }
            ),
        )
        (destination / "freeze_manifest.json").write_text(
            canonical_json(manifest.canonical_object()) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verify_complete_m336k4_freeze(root, manifest, allow_prospective_f29=True)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336K4_F29_BUILD_RECEIPT",
        "exact_implementation_tip": exact_implementation_tip,
        "exact_q29_sha": exact_q29_sha,
        "component_count": len(components),
        "candidate_pool_hash": _object(component_sources["candidate_pool"])[
            "pool_hash"
        ],
        "route_identity_bundle_hash": bundle_hash,
        "freeze_manifest_hash": manifest.manifest_hash,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    (destination / "f29_build_receipt.json").write_text(
        canonical_json(receipt) + "\n", encoding="utf-8", newline="\n"
    )
    return receipt


def attest_committed_m336k4_f29(
    repository: Path,
    git_executable: Path,
    *,
    freeze_manifest: M336K4FreezeManifest,
    exact_f29_sha: str,
) -> M336K4CommittedFreezeAttestation:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    verify_complete_m336k4_freeze(root, freeze_manifest, allow_prospective_f29=True)
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    parent = _git(git, root, "rev-parse", f"{exact_f29_sha}^")
    tree = _git(git, root, "rev-parse", f"{exact_f29_sha}^{{tree}}")
    branch = _git(git, root, "branch", "--show-current")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    remote = _git(
        git, root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"
    ).split()[0]
    changes = tuple(
        item
        for item in _git(
            git,
            root,
            "diff",
            "--name-only",
            freeze_manifest.implementation_tip,
            exact_f29_sha,
            "--",
            "src",
            "scripts",
            "tools",
            "tests",
            "schemas",
        ).splitlines()
        if item
    )
    merges = int(
        _git(
            git,
            root,
            "rev-list",
            "--count",
            "--merges",
            f"{freeze_manifest.implementation_tip}..{exact_f29_sha}",
        )
    )
    prospective = _committed_prospective_identity(
        git, root, exact_f29_sha, freeze_manifest.self_reference_safe_exclusions
    )
    clean = not _git(git, root, "status", "--porcelain=v1")
    passed = (
        head == exact_f29_sha
        and parent == freeze_manifest.exact_q29_sha
        and head == upstream == remote
        and clean
        and not changes
        and merges == 0
        and prospective == freeze_manifest.prospective_freeze_tree_hash
    )
    body = {
        "schema_version": 2,
        "exact_f29_sha": exact_f29_sha,
        "exact_q29_parent": parent,
        "committed_tree_hash": tree,
        "prospective_freeze_tree_hash": freeze_manifest.prospective_freeze_tree_hash,
        "prospective_tree_matches": prospective
        == freeze_manifest.prospective_freeze_tree_hash,
        "route_identity_bundle_hash": freeze_manifest.route_identity_bundle_hash,
        "authorization_hash": freeze_manifest.authorization_hash,
        "route_hash": freeze_manifest.route_hash,
        "implementation_change_count": len(changes),
        "merge_count": merges,
        "head_upstream_remote_equal": head == upstream == remote,
        "worktree_clean": clean,
        "status": "PASS" if passed else "FAIL",
    }
    result = M336K4CommittedFreezeAttestation(
        **body, attestation_hash=content_hash(body)
    )
    if not passed:
        raise M336K2ProtocolError("M336K4 committed F29 attestation failed")
    return result


def _verify_q29_lineage(
    root: Path, git: Path, implementation: str, q29: str, branch: str
) -> None:
    remote = _git(
        git, root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"
    ).split()[0]
    changed = _git(
        git,
        root,
        "diff",
        "--name-only",
        implementation,
        q29,
        "--",
        "src",
        "scripts",
        "tools",
        "tests",
        "schemas",
    )
    if (
        _git(git, root, "rev-parse", "HEAD^{commit}") != q29
        or _git(git, root, "rev-parse", "HEAD^1") != implementation
        or _git(git, root, "branch", "--show-current") != branch
        or _git(git, root, "rev-parse", "@{upstream}^{commit}") != q29
        or remote != q29
        or _git(git, root, "status", "--porcelain=v1")
        or changed
    ):
        raise M336K2ProtocolError("M336K4 F29 requires exact pushed evidence-only Q29")


def _verified_object(path: Path, hash_field: str) -> dict:
    value = _object(path.resolve(strict=True))
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if not isinstance(claimed, str) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K4 component semantic hash changed")
    return value


def _semantic_hash(path: Path, field: str) -> str:
    return _verified_object(path, field)[field]


def _reject_metadata(path: Path) -> None:
    raw = path.read_bytes()
    if (
        path.suffix.casefold() not in {".json", ".jsonl"}
        or len(raw) > 20_000_000
        or b"public class " in raw
        or b"package " in raw
    ):
        raise M336K2ProtocolError("M336K4 F29 component is not metadata-only")
    _object(path)


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K4 JSON input is invalid") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K4 JSON input is not an object")
    return value


def _tree_rows(root: Path) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def _committed_prospective_identity(
    git: Path, root: Path, exact_f29_sha: str, exclusions: tuple[str, ...]
) -> str:
    freeze_root = {str(Path(item).parent).replace("\\", "/") for item in exclusions}
    if len(freeze_root) != 1:
        raise M336K2ProtocolError("M336K4 freeze exclusions changed")
    prefix = freeze_root.pop()
    raw = subprocess.run(
        (str(git), "ls-tree", "-r", "-z", "--name-only", exact_f29_sha, "--", prefix),
        cwd=root,
        check=True,
        capture_output=True,
        env=m336k2_minimal_environment(),
    ).stdout
    rows = []
    for value in raw.split(b"\0"):
        if not value:
            continue
        path = value.decode("utf-8")
        if path in exclusions:
            continue
        blob = subprocess.run(
            (str(git), "show", f"{exact_f29_sha}:{path}"),
            cwd=root,
            check=True,
            capture_output=True,
            env=m336k2_minimal_environment(),
        ).stdout
        rows.append(
            (Path(path).relative_to(prefix).as_posix(), len(blob), bytes_hash(blob))
        )
    return content_hash(tuple(sorted(rows, key=lambda item: item[0].encode("utf-8"))))


def _safe_relative(value: str) -> bool:
    path = Path(value)
    return (
        value == path.as_posix()
        and not path.is_absolute()
        and value not in {"", "."}
        and ".." not in path.parts
        and "\\" not in value
    )


def _git(git: Path, root: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()
