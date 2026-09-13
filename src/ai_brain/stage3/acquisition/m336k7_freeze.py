"""Typed F32 freeze and committed-tree attestation for M-33.6k.7."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k5_freeze import (
    M336K6_REQUIRED_FREEZE_COMPONENTS,
)

M336K7_READY_STATUS = "READY_FOR_FROZEN_RESOURCE_BOUND_FINAL_JAVA_EXECUTION_V7"
M336K7_BRANCH = "exp/stage3-m336k7-frozen-contract-final-v16"
M336K7_F32_ROOT = Path("artifacts/m336k7/f32-freeze")
M336K7_REQUIRED_FREEZE_COMPONENTS = frozenset(
    (M336K6_REQUIRED_FREEZE_COMPONENTS - {"resource_budget"})
    | {
        "resource_budget_policy",
        "resource_observation",
        "resource_gate",
        "capsule_binding_set",
        "legacy_capsule_compatibility",
        "post_freeze_input_bundle",
        "frozen_contract_compatibility",
    }
)
M336K7_FREEZE_MANIFEST_CONTRACT = {
    "schema_version": 1,
    "contract_role": "M336K7_F32_TYPED_FREEZE_V1",
    "required_component_names": tuple(sorted(M336K7_REQUIRED_FREEZE_COMPONENTS)),
    "self_reference_safe_exclusions": (
        f"{M336K7_F32_ROOT.as_posix()}/freeze_manifest.json",
        f"{M336K7_F32_ROOT.as_posix()}/f32_build_receipt.json",
    ),
}
M336K7_FREEZE_MANIFEST_CONTRACT_HASH = content_hash(M336K7_FREEZE_MANIFEST_CONTRACT)
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class M336K7FrozenComponent:
    name: str
    relative_path: str
    bytes_hash: str
    byte_count: int

    def verify(self) -> None:
        relative = Path(self.relative_path)
        if (
            not self.name
            or relative.is_absolute()
            or not self.relative_path
            or self.relative_path != relative.as_posix()
            or ".." in relative.parts
            or "\\" in self.relative_path
            or _HASH.fullmatch(self.bytes_hash) is None
            or type(self.byte_count) is not int
            or self.byte_count < 0
        ):
            raise M336K2ProtocolError("M336K7 frozen component is invalid")


@dataclass(frozen=True)
class M336K7FreezeManifest:
    schema_version: int
    contract_role: str
    implementation_tip: str
    exact_q32_sha: str
    exact_f32_sha: str
    committed_f32_tree: str
    readiness_hash: str
    authorization_hash: str
    route_hash: str
    route_identity_bundle_hash: str
    canonical_request_builder_hash: str
    freeze_manifest_contract_hash: str
    components: tuple[M336K7FrozenComponent, ...]
    self_reference_safe_exclusions: tuple[str, ...]
    prospective_freeze_tree_hash: str
    manifest_hash: str

    @property
    def exact_q30_sha(self) -> str:
        return self.exact_q32_sha

    @property
    def exact_f30_sha(self) -> str:
        return self.exact_f32_sha

    @property
    def exact_q28_sha(self) -> str:
        return self.exact_q32_sha

    @property
    def exact_f28_sha(self) -> str:
        return self.exact_f32_sha

    @property
    def committed_f28_tree(self) -> str:
        return self.committed_f32_tree

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "implementation_tip": self.implementation_tip,
            "exact_q32_sha": self.exact_q32_sha,
            "exact_f32_sha": self.exact_f32_sha,
            "committed_f32_tree": self.committed_f32_tree,
            "readiness_hash": self.readiness_hash,
            "authorization_hash": self.authorization_hash,
            "route_hash": self.route_hash,
            "route_identity_bundle_hash": self.route_identity_bundle_hash,
            "canonical_request_builder_hash": self.canonical_request_builder_hash,
            "freeze_manifest_contract_hash": self.freeze_manifest_contract_hash,
            "components": tuple(asdict(item) for item in self.components),
            "self_reference_safe_exclusions": self.self_reference_safe_exclusions,
            "prospective_freeze_tree_hash": self.prospective_freeze_tree_hash,
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "manifest_hash": self.manifest_hash}

    def verify(self, repository: Path, *, allow_prospective: bool = False) -> None:
        root = repository.resolve(strict=True)
        names = {item.name for item in self.components}
        for item in self.components:
            item.verify()
            path = root.joinpath(*Path(item.relative_path).parts)
            if (
                not path.is_file()
                or path.stat().st_size != item.byte_count
                or bytes_hash(path.read_bytes()) != item.bytes_hash
            ):
                raise M336K2ProtocolError(
                    f"M336K7 frozen component changed: {item.name}"
                )
        hashes = (
            self.readiness_hash,
            self.authorization_hash,
            self.route_hash,
            self.route_identity_bundle_hash,
            self.canonical_request_builder_hash,
            self.freeze_manifest_contract_hash,
            self.prospective_freeze_tree_hash,
            self.manifest_hash,
        )
        prospective = self.exact_f32_sha == "0" * 40
        if (
            self.schema_version != 1
            or self.contract_role != "M336K7_F32_TYPED_FREEZE_V1"
            or names != M336K7_REQUIRED_FREEZE_COMPONENTS
            or len(self.components) != len(names)
            or _SHA.fullmatch(self.implementation_tip) is None
            or _SHA.fullmatch(self.exact_q32_sha) is None
            or _SHA.fullmatch(self.exact_f32_sha) is None
            or _SHA.fullmatch(self.committed_f32_tree) is None
            or any(_HASH.fullmatch(value) is None for value in hashes)
            or self.freeze_manifest_contract_hash
            != M336K7_FREEZE_MANIFEST_CONTRACT_HASH
            or self.self_reference_safe_exclusions
            != M336K7_FREEZE_MANIFEST_CONTRACT["self_reference_safe_exclusions"]
            or prospective != (self.committed_f32_tree == "0" * 40)
            or prospective
            and not allow_prospective
            or self.manifest_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 freeze manifest is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K7 freeze manifest fields changed")
        components = value["components"]
        exclusions = value["self_reference_safe_exclusions"]
        if type(components) is not list or type(exclusions) is not list:
            raise M336K2ProtocolError("M336K7 freeze manifest collections changed")
        result = cls(
            **{
                **value,
                "components": tuple(
                    M336K7FrozenComponent(**item) for item in components
                ),
                "self_reference_safe_exclusions": tuple(exclusions),
            }
        )
        return result


@dataclass(frozen=True)
class M336K7CommittedFreezeAttestation:
    schema_version: int
    contract_role: str
    exact_f32_sha: str
    exact_q32_parent: str
    committed_tree_hash: str
    prospective_freeze_tree_hash: str
    prospective_tree_matches: bool
    route_identity_bundle_hash: str
    authorization_hash: str
    route_hash: str
    post_freeze_input_bundle_hash: str
    implementation_change_count: int
    merge_count: int
    head_upstream_remote_equal: bool
    worktree_clean: bool
    status: str
    attestation_hash: str

    @property
    def exact_f28_sha(self) -> str:
        return self.exact_f32_sha

    @property
    def exact_q28_parent(self) -> str:
        return self.exact_q32_parent

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("attestation_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "attestation_hash": self.attestation_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self._body().items()
            if name.endswith("_hash") and name != "committed_tree_hash"
        ) + (self.attestation_hash,)
        if (
            self.schema_version != 1
            or self.contract_role != "M336K7_COMMITTED_F32_ATTESTATION"
            or _SHA.fullmatch(self.exact_f32_sha) is None
            or _SHA.fullmatch(self.exact_q32_parent) is None
            or _SHA.fullmatch(self.committed_tree_hash) is None
            or any(_HASH.fullmatch(value) is None for value in hashes)
            or not self.prospective_tree_matches
            or self.implementation_change_count != 0
            or self.merge_count != 0
            or not self.head_upstream_remote_equal
            or not self.worktree_clean
            or self.status != "PASS"
            or self.attestation_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 committed F32 attestation is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K7 F32 attestation fields changed")
        result = cls(**value)
        result.verify()
        return result


def materialize_m336k7_f32(
    *,
    repository: Path,
    git_executable: Path,
    exact_implementation_tip: str,
    exact_q32_sha: str,
    readiness: Path,
    component_sources: dict[str, Path],
    output: Path,
    expected_branch: str = M336K7_BRANCH,
    freeze_relative_root: str = M336K7_F32_ROOT.as_posix(),
) -> dict[str, Any]:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    destination = output.resolve(strict=False)
    if (
        destination.exists()
        or set(component_sources) != M336K7_REQUIRED_FREEZE_COMPONENTS
        or destination.relative_to(root).as_posix() != freeze_relative_root
    ):
        raise M336K2ProtocolError("M336K7 F32 destination/component set changed")
    _verify_q32_lineage(
        root, git, exact_implementation_tip, exact_q32_sha, expected_branch
    )
    readiness_value = _verified_object(readiness, "readiness_hash")
    if (
        readiness_value["status"] != M336K7_READY_STATUS
        or readiness_value["exact_implementation_tip"] != exact_implementation_tip
        or readiness_value["official_one_shot_counter_count"] != 0
        or readiness_value["new_final_source_body_bytes"] != 0
    ):
        raise M336K2ProtocolError("M336K7 Q32 readiness is not sealed and unspent")
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
                M336K7FrozenComponent(
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
            "schema_version": 1,
            "contract_role": "M336K7_F32_FROZEN_FILE_MANIFEST",
            "files": rows,
            "file_count": len(rows),
        }
        frozen_file = {
            **frozen_body,
            "frozen_file_manifest_hash": content_hash(frozen_body),
        }
        (destination / "frozen_file_manifest.json").write_text(
            canonical_json(frozen_file) + "\n", encoding="utf-8", newline="\n"
        )
        prospective = content_hash(_tree_rows(destination))
        values = {
            "schema_version": 1,
            "contract_role": "M336K7_F32_TYPED_FREEZE_V1",
            "implementation_tip": exact_implementation_tip,
            "exact_q32_sha": exact_q32_sha,
            "exact_f32_sha": "0" * 40,
            "committed_f32_tree": "0" * 40,
            "readiness_hash": readiness_value["readiness_hash"],
            "authorization_hash": _semantic_hash(
                component_sources["final_authorization"], "authorization_hash"
            ),
            "route_hash": _semantic_hash(
                component_sources["typed_route_manifest"], "manifest_hash"
            ),
            "route_identity_bundle_hash": _semantic_hash(
                component_sources["route_identity_bundle"], "bundle_hash"
            ),
            "canonical_request_builder_hash": _semantic_hash(
                component_sources["canonical_request_builder_identity"],
                "builder_hash",
            ),
            "freeze_manifest_contract_hash": M336K7_FREEZE_MANIFEST_CONTRACT_HASH,
            "components": tuple(components),
            "self_reference_safe_exclusions": (
                f"{freeze_relative_root}/freeze_manifest.json",
                f"{freeze_relative_root}/f32_build_receipt.json",
            ),
            "prospective_freeze_tree_hash": prospective,
        }
        temporary = M336K7FreezeManifest(**values, manifest_hash="0" * 64)
        manifest = M336K7FreezeManifest(
            **values, manifest_hash=content_hash(temporary._body())
        )
        (destination / "freeze_manifest.json").write_text(
            canonical_json(manifest.canonical_object()) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        manifest.verify(root, allow_prospective=True)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K7_F32_BUILD_RECEIPT",
        "exact_implementation_tip": exact_implementation_tip,
        "exact_q32_sha": exact_q32_sha,
        "component_count": len(components),
        "candidate_pool_hash": _object(component_sources["candidate_pool"])[
            "pool_hash"
        ],
        "post_freeze_input_bundle_hash": _semantic_hash(
            component_sources["post_freeze_input_bundle"], "bundle_hash"
        ),
        "freeze_manifest_hash": manifest.manifest_hash,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    (destination / "f32_build_receipt.json").write_text(
        canonical_json(receipt) + "\n", encoding="utf-8", newline="\n"
    )
    return receipt


def attest_committed_m336k7_f32(
    repository: Path,
    git_executable: Path,
    *,
    freeze_manifest: M336K7FreezeManifest,
    exact_f32_sha: str,
) -> M336K7CommittedFreezeAttestation:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    freeze_manifest.verify(root, allow_prospective=True)
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    parent = _git(git, root, "rev-parse", f"{exact_f32_sha}^")
    tree = _git(git, root, "rev-parse", f"{exact_f32_sha}^{{tree}}")
    branch = _git(git, root, "branch", "--show-current")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    remote = _git(
        git, root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"
    ).split()[0]
    changes = tuple(
        line
        for line in _git(
            git,
            root,
            "diff",
            "--name-only",
            freeze_manifest.implementation_tip,
            exact_f32_sha,
            "--",
            "src",
            "scripts",
            "tools",
            "tests",
            "schemas",
        ).splitlines()
        if line
    )
    merges = int(
        _git(
            git,
            root,
            "rev-list",
            "--count",
            "--merges",
            f"{freeze_manifest.implementation_tip}..{exact_f32_sha}",
        )
    )
    prospective = _committed_prospective_identity(
        git, root, exact_f32_sha, freeze_manifest.self_reference_safe_exclusions
    )
    clean = not _git(git, root, "status", "--porcelain=v1")
    passed = (
        head == exact_f32_sha
        and parent == freeze_manifest.exact_q32_sha
        and head == upstream == remote
        and clean
        and not changes
        and merges == 0
        and prospective == freeze_manifest.prospective_freeze_tree_hash
    )
    components = {item.name: item for item in freeze_manifest.components}
    bundle_path = root.joinpath(
        *Path(components["post_freeze_input_bundle"].relative_path).parts
    )
    body = {
        "schema_version": 1,
        "contract_role": "M336K7_COMMITTED_F32_ATTESTATION",
        "exact_f32_sha": exact_f32_sha,
        "exact_q32_parent": parent,
        "committed_tree_hash": tree,
        "prospective_freeze_tree_hash": freeze_manifest.prospective_freeze_tree_hash,
        "prospective_tree_matches": prospective
        == freeze_manifest.prospective_freeze_tree_hash,
        "route_identity_bundle_hash": freeze_manifest.route_identity_bundle_hash,
        "authorization_hash": freeze_manifest.authorization_hash,
        "route_hash": freeze_manifest.route_hash,
        "post_freeze_input_bundle_hash": _semantic_hash(bundle_path, "bundle_hash"),
        "implementation_change_count": len(changes),
        "merge_count": merges,
        "head_upstream_remote_equal": head == upstream == remote,
        "worktree_clean": clean,
        "status": "PASS" if passed else "FAIL",
    }
    result = M336K7CommittedFreezeAttestation(
        **body, attestation_hash=content_hash(body)
    )
    if not passed:
        raise M336K2ProtocolError("M336K7 committed F32 attestation failed")
    result.verify()
    return result


def _verify_q32_lineage(
    root: Path, git: Path, implementation: str, q32: str, branch: str
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
        q32,
        "--",
        "src",
        "scripts",
        "tools",
        "tests",
        "schemas",
    )
    if (
        _git(git, root, "rev-parse", "HEAD^{commit}") != q32
        or _git(git, root, "rev-parse", "HEAD^1") != implementation
        or _git(git, root, "branch", "--show-current") != branch
        or _git(git, root, "rev-parse", "@{upstream}^{commit}") != q32
        or remote != q32
        or _git(git, root, "status", "--porcelain=v1")
        or changed
    ):
        raise M336K2ProtocolError("M336K7 F32 requires exact pushed evidence-only Q32")


def _verified_object(path: Path, hash_field: str) -> dict[str, Any]:
    value = _object(path.resolve(strict=True))
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if not isinstance(claimed, str) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K7 component semantic hash changed")
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
        raise M336K2ProtocolError("M336K7 F32 component is not metadata-only")
    _object(path)


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K7 JSON input is invalid") from error
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K7 JSON input is not an object")
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
    git: Path, root: Path, exact_f32_sha: str, exclusions: tuple[str, ...]
) -> str:
    freeze_roots = {str(Path(item).parent).replace("\\", "/") for item in exclusions}
    if len(freeze_roots) != 1:
        raise M336K2ProtocolError("M336K7 freeze exclusions changed")
    prefix = freeze_roots.pop()
    raw = subprocess.run(
        (str(git), "ls-tree", "-r", "-z", "--name-only", exact_f32_sha, "--", prefix),
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
            (str(git), "show", f"{exact_f32_sha}:{path}"),
            cwd=root,
            check=True,
            capture_output=True,
            env=m336k2_minimal_environment(),
        ).stdout
        rows.append(
            (Path(path).relative_to(prefix).as_posix(), len(blob), bytes_hash(blob))
        )
    return content_hash(tuple(sorted(rows, key=lambda item: item[0].encode("utf-8"))))


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
