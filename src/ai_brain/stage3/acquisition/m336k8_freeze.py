"""Phase-neutral F33 freeze and committed-tree attestation for M-33.6k.8."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k7_freeze import (
    M336K7_REQUIRED_FREEZE_COMPONENTS,
)

M336K8_READY_STATUS = "READY_FOR_SOURCE_DOMAIN_BOUND_FINAL_JAVA_EXECUTION_V8"
M336K8_BRANCH = "exp/stage3-m336k8-source-domain-final-v17"
M336K8_F33_ROOT = Path("artifacts/m336k8/f33-freeze")
M336K9_READY_STATUS = "READY_FOR_UNIFIED_ADMISSION_FINAL_JAVA_EXECUTION_V9"
M336K9_BRANCH = "exp/stage3-m336k9-controller-admission-final-v18"
M336K9_F34_ROOT = Path("artifacts/m336k9/f34-freeze")
M336K10_READY_STATUS = "READY_FOR_OFFICIAL_ACQUISITION_BOUND_FINAL_JAVA_EXECUTION_V10"
M336K10_BRANCH = "exp/stage3-m336k10-official-acquisition-binding-v19"
M336K10_F35_ROOT = Path("artifacts/m336k10/f35-freeze")
M336K8_REQUIRED_FREEZE_COMPONENTS = frozenset(
    (set(M336K7_REQUIRED_FREEZE_COMPONENTS) - {"frozen_contract_compatibility"})
    | {
        "controller_python_environment_manifest",
        "controller_executable_dependency_manifest",
        "controller_source_identity_policy",
        "controller_source_identity_receipt",
        "controller_startup_binding",
        "persistent_capsule_python_environment_manifest",
        "persistent_capsule_executable_dependency_manifest",
        "persistent_capsule_source_binding",
        "bridge_surface_manifest",
        "source_domain_compatibility",
        "freeze_assembly_plan",
        "freeze_assembly_receipt",
        "frozen_contract_compatibility_v2",
        "legacy_controller_alias_receipt",
    }
)
M336K9_REQUIRED_FREEZE_COMPONENTS = frozenset(
    set(M336K8_REQUIRED_FREEZE_COMPONENTS)
    | {
        "official_profile_registry",
        "active_official_profile",
        "profile_coverage_gate",
        "controller_admission_contract",
    }
)
M336K10_REQUIRED_FREEZE_COMPONENTS = frozenset(
    set(M336K9_REQUIRED_FREEZE_COMPONENTS)
    | {
        "official_candidate_pool_binding",
        "official_network_authority_manifest",
        "shared_acquisition_policy_binding",
        "official_provider_configuration",
        "acquisition_ledger_context_template",
        "stage_request_acquisition_binding",
        "official_acquisition_binding_receipt",
        "official_freeze_origin_receipt",
    }
)
_SOURCE_SCOPE = ("src", "scripts", "tools", "schemas", "pyproject.toml", "uv.lock")


def _is_hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_sha(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True)
class M336K8FrozenComponent:
    name: str
    relative_path: str
    bytes_hash: str
    byte_count: int

    def verify(self) -> None:
        relative = Path(self.relative_path)
        if (
            not self.name
            or not self.relative_path
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in self.relative_path
            or relative.as_posix() != self.relative_path
            or not _is_hash(self.bytes_hash)
            or type(self.byte_count) is not int
            or self.byte_count < 0
        ):
            raise M336K2ProtocolError("M336K8 frozen component is invalid")


@dataclass(frozen=True)
class M336K8FreezeManifest:
    schema_version: int
    contract_role: str
    implementation_tip: str
    exact_qualification_sha: str
    exact_freeze_sha: str
    committed_freeze_tree: str
    readiness_hash: str
    authorization_hash: str
    route_hash: str
    route_identity_bundle_hash: str
    canonical_request_builder_hash: str
    post_freeze_input_bundle_hash: str
    source_identity_receipt_hash: str
    controller_startup_binding_hash: str
    persistent_capsule_source_binding_hash: str
    bridge_surface_manifest_hash: str
    source_domain_compatibility_receipt_hash: str
    freeze_assembly_plan_hash: str
    freeze_assembly_receipt_hash: str
    compatibility_gate_v2_hash: str
    components: tuple[M336K8FrozenComponent, ...]
    self_reference_safe_exclusions: tuple[str, ...]
    prospective_freeze_tree_hash: str
    manifest_hash: str
    official_profile_id: str | None = None
    official_profile_hash: str | None = None
    official_profile_registry_hash: str | None = None
    profile_coverage_gate_hash: str | None = None
    controller_admission_contract_hash: str | None = None
    official_candidate_pool_binding_hash: str | None = None
    official_network_authority_manifest_hash: str | None = None
    official_acquisition_policy_hash: str | None = None
    official_acquisition_binding_receipt_hash: str | None = None
    official_provider_configuration_hash: str | None = None
    stage_request_acquisition_binding_hash: str | None = None
    acquisition_ledger_context_template_hash: str | None = None
    official_freeze_origin_receipt_hash: str | None = None

    ROLE: ClassVar[str] = "M336K8_SOURCE_DOMAIN_BOUND_FREEZE_V1"
    ROLE_V2: ClassVar[str] = "M336K9_UNIFIED_ADMISSION_FREEZE_V2"
    ROLE_V3: ClassVar[str] = "M336K10_OFFICIAL_ACQUISITION_BOUND_FREEZE_V3"

    @property
    def exact_q28_sha(self) -> str:
        return self.exact_qualification_sha

    @property
    def exact_f28_sha(self) -> str:
        return self.exact_freeze_sha

    @property
    def committed_f28_tree(self) -> str:
        return self.committed_freeze_tree

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("manifest_hash")
        return {name: item for name, item in value.items() if item is not None}

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
                    f"M336K8 frozen component changed: {item.name}"
                )
        exclusions = self.self_reference_safe_exclusions
        exclusion_roots = {Path(item).parent.as_posix() for item in exclusions}
        current = self.contract_role in {self.ROLE_V2, self.ROLE_V3}
        acquisition_bound = self.contract_role == self.ROLE_V3
        expected_names = {
            "freeze_manifest.json",
            (
                "f35_build_receipt.json"
                if acquisition_bound
                else "f34_build_receipt.json"
                if current
                else "f33_build_receipt.json"
            ),
        }
        required_components = (
            M336K10_REQUIRED_FREEZE_COMPONENTS
            if acquisition_bound
            else M336K9_REQUIRED_FREEZE_COMPONENTS
            if current
            else M336K8_REQUIRED_FREEZE_COMPONENTS
        )
        profile_values = (
            self.official_profile_id,
            self.official_profile_hash,
            self.official_profile_registry_hash,
            self.profile_coverage_gate_hash,
            self.controller_admission_contract_hash,
        )
        acquisition_values = (
            self.official_candidate_pool_binding_hash,
            self.official_network_authority_manifest_hash,
            self.official_acquisition_policy_hash,
            self.official_acquisition_binding_receipt_hash,
            self.official_provider_configuration_hash,
            self.stage_request_acquisition_binding_hash,
            self.acquisition_ledger_context_template_hash,
            self.official_freeze_origin_receipt_hash,
        )
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        prospective = self.exact_freeze_sha == "0" * 40
        if (
            self.schema_version != 1
            or self.contract_role not in {self.ROLE, self.ROLE_V2, self.ROLE_V3}
            or names != required_components
            or len(names) != len(self.components)
            or not _is_sha(self.implementation_tip)
            or not _is_sha(self.exact_qualification_sha)
            or not _is_sha(self.exact_freeze_sha)
            or not _is_sha(self.committed_freeze_tree)
            or any(not _is_hash(value) for value in hashes)
            or len(exclusion_roots) != 1
            or {Path(item).name for item in exclusions} != expected_names
            or prospective != (self.committed_freeze_tree == "0" * 40)
            or prospective
            and not allow_prospective
            or current
            and (
                type(self.official_profile_id) is not str
                or not self.official_profile_id
                or any(not _is_hash(value) for value in profile_values[1:])
            )
            or not current
            and any(value is not None for value in profile_values)
            or acquisition_bound
            and any(not _is_hash(value) for value in acquisition_values)
            or not acquisition_bound
            and any(value is not None for value in acquisition_values)
            or self.manifest_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 freeze manifest is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        all_fields = {field.name for field in fields(cls)}
        optional = {
            "official_profile_id",
            "official_profile_hash",
            "official_profile_registry_hash",
            "profile_coverage_gate_hash",
            "controller_admission_contract_hash",
            "official_candidate_pool_binding_hash",
            "official_network_authority_manifest_hash",
            "official_acquisition_policy_hash",
            "official_acquisition_binding_receipt_hash",
            "official_provider_configuration_hash",
            "stage_request_acquisition_binding_hash",
            "acquisition_ledger_context_template_hash",
            "official_freeze_origin_receipt_hash",
        }
        mandatory = all_fields - optional
        if (
            type(value) is not dict
            or not mandatory.issubset(value)
            or set(value) - mandatory - optional
        ):
            raise M336K2ProtocolError("M336K8 freeze manifest fields changed")
        if (
            type(value["components"]) is not list
            or type(value["self_reference_safe_exclusions"]) is not list
        ):
            raise M336K2ProtocolError("M336K8 freeze collections changed")
        return cls(
            **{
                **{name: None for name in optional},
                **value,
                "components": tuple(
                    M336K8FrozenComponent(**item) for item in value["components"]
                ),
                "self_reference_safe_exclusions": tuple(
                    value["self_reference_safe_exclusions"]
                ),
            }
        )


@dataclass(frozen=True)
class M336K8CommittedFreezeAttestation:
    schema_version: int
    contract_role: str
    exact_freeze_sha: str
    exact_qualification_parent: str
    committed_tree_hash: str
    prospective_freeze_tree_hash: str
    prospective_tree_matches: bool
    route_identity_bundle_hash: str
    authorization_hash: str
    route_hash: str
    post_freeze_input_bundle_hash: str
    source_identity_receipt_hash: str
    freeze_assembly_plan_hash: str
    producer_origin_map_hash: str
    implementation_change_count: int
    merge_count: int
    head_upstream_remote_equal: bool
    worktree_clean: bool
    status: str
    attestation_hash: str

    ROLE: ClassVar[str] = "M336K8_COMMITTED_FREEZE_ATTESTATION"

    @property
    def exact_f28_sha(self) -> str:
        return self.exact_freeze_sha

    @property
    def exact_q28_parent(self) -> str:
        return self.exact_qualification_parent

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("attestation_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "attestation_hash": self.attestation_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash") and name != "committed_tree_hash"
        )
        passed = (
            self.prospective_tree_matches
            and self.implementation_change_count == 0
            and self.merge_count == 0
            and self.head_upstream_remote_equal
            and self.worktree_clean
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or not _is_sha(self.exact_freeze_sha)
            or not _is_sha(self.exact_qualification_parent)
            or not _is_sha(self.committed_tree_hash)
            or any(not _is_hash(value) for value in hashes)
            or self.status != ("PASS" if passed else "FAIL")
            or self.attestation_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 committed freeze attestation is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K8 freeze attestation fields changed")
        result = cls(**value)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K9CommittedFreezeAttestation(M336K8CommittedFreezeAttestation):
    official_profile_id: str
    official_profile_hash: str
    official_profile_registry_hash: str
    profile_coverage_gate_hash: str
    controller_admission_contract_hash: str

    ROLE: ClassVar[str] = "M336K9_COMMITTED_FREEZE_ATTESTATION"

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash") and name != "committed_tree_hash"
        )
        passed = (
            self.prospective_tree_matches
            and self.implementation_change_count == 0
            and self.merge_count == 0
            and self.head_upstream_remote_equal
            and self.worktree_clean
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or not self.official_profile_id
            or not _is_sha(self.exact_freeze_sha)
            or not _is_sha(self.exact_qualification_parent)
            or not _is_sha(self.committed_tree_hash)
            or any(not _is_hash(value) for value in hashes)
            or self.status != ("PASS" if passed else "FAIL")
            or self.attestation_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K9 committed freeze attestation is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K9 freeze attestation fields changed")
        result = cls(**value)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10CommittedFreezeAttestation(M336K9CommittedFreezeAttestation):
    official_candidate_pool_binding_hash: str
    official_network_authority_manifest_hash: str
    official_acquisition_policy_hash: str
    official_acquisition_binding_receipt_hash: str
    official_provider_configuration_hash: str
    stage_request_acquisition_binding_hash: str
    acquisition_ledger_context_template_hash: str
    official_freeze_origin_receipt_hash: str

    ROLE: ClassVar[str] = "M336K10_COMMITTED_FREEZE_ATTESTATION"

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash") and name != "committed_tree_hash"
        )
        passed = (
            self.prospective_tree_matches
            and self.implementation_change_count == 0
            and self.merge_count == 0
            and self.head_upstream_remote_equal
            and self.worktree_clean
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.official_profile_id != "m336k8-final-v3"
            or not _is_sha(self.exact_freeze_sha)
            or not _is_sha(self.exact_qualification_parent)
            or not _is_sha(self.committed_tree_hash)
            or any(not _is_hash(value) for value in hashes)
            or self.status != ("PASS" if passed else "FAIL")
            or self.attestation_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K10 committed freeze attestation is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K10 freeze attestation fields changed")
        result = cls(**value)
        result.verify()
        return result


def materialize_m336k8_freeze(
    *,
    repository: Path,
    git_executable: Path,
    exact_implementation_tip: str,
    exact_qualification_sha: str,
    readiness: Path,
    component_sources: dict[str, Path],
    output: Path,
    expected_branch: str = M336K8_BRANCH,
    freeze_relative_root: str = M336K8_F33_ROOT.as_posix(),
    readiness_status: str = M336K8_READY_STATUS,
    freeze_role: str = M336K8FreezeManifest.ROLE,
    required_components: frozenset[str] = M336K8_REQUIRED_FREEZE_COMPONENTS,
    build_receipt_name: str = "f33_build_receipt.json",
) -> dict[str, Any]:
    """Materialize prospective F-like bytes through one strict component map."""

    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    destination = output.resolve(strict=False)
    try:
        relative_output = destination.relative_to(root).as_posix()
    except ValueError as error:
        raise M336K2ProtocolError("M336K8 freeze output escaped repository") from error
    if (
        destination.exists()
        or relative_output != freeze_relative_root
        or set(component_sources) != required_components
        or freeze_role
        not in {
            M336K8FreezeManifest.ROLE,
            M336K8FreezeManifest.ROLE_V2,
            M336K8FreezeManifest.ROLE_V3,
        }
        or build_receipt_name
        not in {
            "f33_build_receipt.json",
            "f34_build_receipt.json",
            "f35_build_receipt.json",
        }
    ):
        raise M336K2ProtocolError("M336K8 freeze destination/component set changed")
    _verify_qualification_lineage(
        root,
        git,
        exact_implementation_tip,
        exact_qualification_sha,
        expected_branch,
    )
    readiness_value = _verified_object(readiness, "readiness_hash")
    if (
        readiness_value["status"] != readiness_status
        or readiness_value["exact_implementation_tip"] != exact_implementation_tip
        or readiness_value["official_one_shot_counter_count"] != 0
        or readiness_value["new_final_source_body_bytes"] != 0
    ):
        raise M336K2ProtocolError("M336K8 readiness is not sealed and unspent")
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
                M336K8FrozenComponent(
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
            "contract_role": "M336K8_FROZEN_FILE_MANIFEST",
            "files": rows,
            "file_count": len(rows),
        }
        _write(
            destination / "frozen_file_manifest.json",
            {
                **frozen_body,
                "frozen_file_manifest_hash": content_hash(frozen_body),
            },
        )
        prospective = content_hash(_tree_rows(destination))
        values = {
            "schema_version": 1,
            "contract_role": freeze_role,
            "implementation_tip": exact_implementation_tip,
            "exact_qualification_sha": exact_qualification_sha,
            "exact_freeze_sha": "0" * 40,
            "committed_freeze_tree": "0" * 40,
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
            "post_freeze_input_bundle_hash": _semantic_hash(
                component_sources["post_freeze_input_bundle"], "bundle_hash"
            ),
            "source_identity_receipt_hash": _semantic_hash(
                component_sources["controller_source_identity_receipt"],
                "receipt_hash",
            ),
            "controller_startup_binding_hash": _semantic_hash(
                component_sources["controller_startup_binding"], "binding_hash"
            ),
            "persistent_capsule_source_binding_hash": _semantic_hash(
                component_sources["persistent_capsule_source_binding"], "binding_hash"
            ),
            "bridge_surface_manifest_hash": _semantic_hash(
                component_sources["bridge_surface_manifest"], "manifest_hash"
            ),
            "source_domain_compatibility_receipt_hash": _semantic_hash(
                component_sources["source_domain_compatibility"], "receipt_hash"
            ),
            "freeze_assembly_plan_hash": _semantic_hash(
                component_sources["freeze_assembly_plan"], "plan_hash"
            ),
            "freeze_assembly_receipt_hash": _semantic_hash(
                component_sources["freeze_assembly_receipt"], "receipt_hash"
            ),
            "compatibility_gate_v2_hash": _semantic_hash(
                component_sources["frozen_contract_compatibility_v2"], "report_hash"
            ),
            "components": tuple(components),
            "self_reference_safe_exclusions": (
                f"{freeze_relative_root}/freeze_manifest.json",
                f"{freeze_relative_root}/{build_receipt_name}",
            ),
            "prospective_freeze_tree_hash": prospective,
        }
        if freeze_role in {
            M336K8FreezeManifest.ROLE_V2,
            M336K8FreezeManifest.ROLE_V3,
        }:
            profile = _object(component_sources["active_official_profile"])
            values.update(
                {
                    "official_profile_id": profile["profile_id"],
                    "official_profile_hash": _semantic_hash(
                        component_sources["active_official_profile"], "profile_hash"
                    ),
                    "official_profile_registry_hash": _semantic_hash(
                        component_sources["official_profile_registry"], "registry_hash"
                    ),
                    "profile_coverage_gate_hash": _semantic_hash(
                        component_sources["profile_coverage_gate"], "gate_hash"
                    ),
                    "controller_admission_contract_hash": _semantic_hash(
                        component_sources["controller_admission_contract"],
                        "contract_hash",
                    ),
                }
            )
        if freeze_role == M336K8FreezeManifest.ROLE_V3:
            values.update(
                {
                    "official_candidate_pool_binding_hash": _semantic_hash(
                        component_sources["official_candidate_pool_binding"],
                        "binding_hash",
                    ),
                    "official_network_authority_manifest_hash": _semantic_hash(
                        component_sources["official_network_authority_manifest"],
                        "manifest_hash",
                    ),
                    "official_acquisition_policy_hash": _semantic_hash(
                        component_sources["acquisition_policy"],
                        "acquisition_policy_hash",
                    ),
                    "official_acquisition_binding_receipt_hash": _semantic_hash(
                        component_sources["official_acquisition_binding_receipt"],
                        "receipt_hash",
                    ),
                    "official_provider_configuration_hash": _semantic_hash(
                        component_sources["official_provider_configuration"],
                        "configuration_hash",
                    ),
                    "stage_request_acquisition_binding_hash": _semantic_hash(
                        component_sources["stage_request_acquisition_binding"],
                        "binding_hash",
                    ),
                    "acquisition_ledger_context_template_hash": _semantic_hash(
                        component_sources["acquisition_ledger_context_template"],
                        "template_hash",
                    ),
                    "official_freeze_origin_receipt_hash": _semantic_hash(
                        component_sources["official_freeze_origin_receipt"],
                        "receipt_hash",
                    ),
                }
            )
        temporary = M336K8FreezeManifest(**values, manifest_hash="0" * 64)
        manifest = M336K8FreezeManifest(
            **values, manifest_hash=content_hash(temporary._body())
        )
        _write(destination / "freeze_manifest.json", manifest.canonical_object())
        manifest.verify(root, allow_prospective=True)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    body = {
        "schema_version": 1,
        "contract_role": (
            "PUBLIC_SAFE_M336K10_FREEZE_BUILD_RECEIPT"
            if freeze_role == M336K8FreezeManifest.ROLE_V3
            else "PUBLIC_SAFE_M336K9_FREEZE_BUILD_RECEIPT"
            if freeze_role == M336K8FreezeManifest.ROLE_V2
            else "PUBLIC_SAFE_M336K8_FREEZE_BUILD_RECEIPT"
        ),
        "exact_implementation_tip": exact_implementation_tip,
        "exact_qualification_sha": exact_qualification_sha,
        "component_count": len(components),
        "candidate_pool_hash": _object(component_sources["candidate_pool"])[
            "pool_hash"
        ],
        "post_freeze_input_bundle_hash": manifest.post_freeze_input_bundle_hash,
        "freeze_manifest_hash": manifest.manifest_hash,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    _write(destination / build_receipt_name, receipt)
    return receipt


def attest_committed_m336k8_freeze(
    repository: Path,
    git_executable: Path,
    *,
    freeze_manifest: M336K8FreezeManifest,
    exact_freeze_sha: str,
) -> M336K8CommittedFreezeAttestation:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    freeze_manifest.verify(root, allow_prospective=True)
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    parent = _git(git, root, "rev-parse", f"{exact_freeze_sha}^")
    tree = _git(git, root, "rev-parse", f"{exact_freeze_sha}^{{tree}}")
    branch = _git(git, root, "branch", "--show-current")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    remote_rows = _git(
        git, root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"
    ).split()
    remote = remote_rows[0] if remote_rows else ""
    changes = tuple(
        line
        for line in _git(
            git,
            root,
            "diff",
            "--name-only",
            freeze_manifest.implementation_tip,
            exact_freeze_sha,
            "--",
            *_SOURCE_SCOPE,
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
            f"{freeze_manifest.implementation_tip}..{exact_freeze_sha}",
        )
    )
    prospective = _committed_prospective_identity(
        git, root, exact_freeze_sha, freeze_manifest.self_reference_safe_exclusions
    )
    clean = not _git(git, root, "status", "--porcelain=v1")
    passed = (
        head == exact_freeze_sha
        and parent == freeze_manifest.exact_qualification_sha
        and head == upstream == remote
        and clean
        and not changes
        and merges == 0
        and prospective == freeze_manifest.prospective_freeze_tree_hash
    )
    plan = _component_object(root, freeze_manifest, "freeze_assembly_plan")
    attestation_type = (
        M336K10CommittedFreezeAttestation
        if freeze_manifest.contract_role == M336K8FreezeManifest.ROLE_V3
        else M336K9CommittedFreezeAttestation
        if freeze_manifest.contract_role == M336K8FreezeManifest.ROLE_V2
        else M336K8CommittedFreezeAttestation
    )
    body = {
        "schema_version": 1,
        "contract_role": attestation_type.ROLE,
        "exact_freeze_sha": exact_freeze_sha,
        "exact_qualification_parent": parent,
        "committed_tree_hash": tree,
        "prospective_freeze_tree_hash": freeze_manifest.prospective_freeze_tree_hash,
        "prospective_tree_matches": prospective
        == freeze_manifest.prospective_freeze_tree_hash,
        "route_identity_bundle_hash": freeze_manifest.route_identity_bundle_hash,
        "authorization_hash": freeze_manifest.authorization_hash,
        "route_hash": freeze_manifest.route_hash,
        "post_freeze_input_bundle_hash": freeze_manifest.post_freeze_input_bundle_hash,
        "source_identity_receipt_hash": freeze_manifest.source_identity_receipt_hash,
        "freeze_assembly_plan_hash": freeze_manifest.freeze_assembly_plan_hash,
        "producer_origin_map_hash": plan["producer_origin_map_hash"],
        "implementation_change_count": len(changes),
        "merge_count": merges,
        "head_upstream_remote_equal": head == upstream == remote,
        "worktree_clean": clean,
        "status": "PASS" if passed else "FAIL",
    }
    if freeze_manifest.contract_role in {
        M336K8FreezeManifest.ROLE_V2,
        M336K8FreezeManifest.ROLE_V3,
    }:
        body.update(
            {
                "official_profile_id": freeze_manifest.official_profile_id,
                "official_profile_hash": freeze_manifest.official_profile_hash,
                "official_profile_registry_hash": freeze_manifest.official_profile_registry_hash,
                "profile_coverage_gate_hash": freeze_manifest.profile_coverage_gate_hash,
                "controller_admission_contract_hash": freeze_manifest.controller_admission_contract_hash,
            }
        )
    if freeze_manifest.contract_role == M336K8FreezeManifest.ROLE_V3:
        body.update(
            {
                "official_candidate_pool_binding_hash": freeze_manifest.official_candidate_pool_binding_hash,
                "official_network_authority_manifest_hash": freeze_manifest.official_network_authority_manifest_hash,
                "official_acquisition_policy_hash": freeze_manifest.official_acquisition_policy_hash,
                "official_acquisition_binding_receipt_hash": freeze_manifest.official_acquisition_binding_receipt_hash,
                "official_provider_configuration_hash": freeze_manifest.official_provider_configuration_hash,
                "stage_request_acquisition_binding_hash": freeze_manifest.stage_request_acquisition_binding_hash,
                "acquisition_ledger_context_template_hash": freeze_manifest.acquisition_ledger_context_template_hash,
                "official_freeze_origin_receipt_hash": freeze_manifest.official_freeze_origin_receipt_hash,
            }
        )
    result = attestation_type(**body, attestation_hash=content_hash(body))
    result.verify()
    if not passed:
        raise M336K2ProtocolError("M336K8 committed freeze attestation failed")
    return result


def _verify_qualification_lineage(
    root: Path,
    git: Path,
    implementation: str,
    qualification: str,
    branch: str,
) -> None:
    remote_rows = _git(
        git, root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"
    ).split()
    remote = remote_rows[0] if remote_rows else ""
    changed = _git(
        git,
        root,
        "diff",
        "--name-only",
        implementation,
        qualification,
        "--",
        *_SOURCE_SCOPE,
    )
    if (
        _git(git, root, "rev-parse", "HEAD^{commit}") != qualification
        or _git(git, root, "rev-parse", "HEAD^1") != implementation
        or _git(git, root, "branch", "--show-current") != branch
        or _git(git, root, "rev-parse", "@{upstream}^{commit}") != qualification
        or remote != qualification
        or _git(git, root, "status", "--porcelain=v1")
        or changed
    ):
        raise M336K2ProtocolError(
            "M336K8 freeze requires exact pushed evidence-only qualification"
        )


def _component_object(
    root: Path, manifest: M336K8FreezeManifest, name: str
) -> dict[str, Any]:
    rows = tuple(item for item in manifest.components if item.name == name)
    if len(rows) != 1:
        raise M336K2ProtocolError("M336K8 frozen component lookup failed")
    return _object(root.joinpath(*Path(rows[0].relative_path).parts))


def _verified_object(path: Path, hash_field: str) -> dict[str, Any]:
    value = _object(path.resolve(strict=True))
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if not _is_hash(claimed) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K8 component semantic hash changed")
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
        raise M336K2ProtocolError("M336K8 freeze component is not metadata-only")
    _object(path)


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K8 JSON input is invalid") from error
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K8 JSON input is not an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


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
    git: Path,
    root: Path,
    exact_freeze_sha: str,
    exclusions: tuple[str, ...],
) -> str:
    freeze_roots = {Path(item).parent.as_posix() for item in exclusions}
    if len(freeze_roots) != 1:
        raise M336K2ProtocolError("M336K8 freeze exclusions changed")
    prefix = freeze_roots.pop()
    raw = subprocess.run(
        (
            str(git),
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            exact_freeze_sha,
            "--",
            prefix,
        ),
        cwd=root,
        check=True,
        capture_output=True,
        env=m336k2_minimal_environment(),
    ).stdout
    rows = []
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        path = encoded.decode("utf-8", errors="strict")
        if path in exclusions:
            continue
        blob = subprocess.run(
            (str(git), "show", f"{exact_freeze_sha}:{path}"),
            cwd=root,
            check=True,
            capture_output=True,
            env=m336k2_minimal_environment(),
        ).stdout
        rows.append(
            (Path(path).relative_to(prefix).as_posix(), len(blob), bytes_hash(blob))
        )
    ordered = tuple(sorted(rows, key=lambda item: item[0].encode("utf-8")))
    return content_hash(ordered)


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
