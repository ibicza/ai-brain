"""Phase-neutral frozen contracts for the M-33.6k.7 final route.

This module deliberately does not import the historical M336K5 request validator.
F30/F31 remain readable historical protocols; the current route consumes only the
strict objects defined here.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k2_registry import (
    M336K2_ROUTE_COMPONENTS,
    M336K2RouteComponent,
    M336K2RouteManifest,
    M336K2RouteRegistry,
    build_m336k2_route_manifest,
)
from ai_brain.stage3.acquisition.m336k5_resources import (
    M336K5StorageReservationReceipt,
)
from ai_brain.stage3.acquisition.m336k6_capsule import (
    M336K6CapsuleContentManifest,
)
from ai_brain.stage3.acquisition.m336k6_resources import M336K6ResourceSample

GIB = 1024**3
M336K7_REQUIRED_PRIVATE_STORAGE_BYTES = 24 * GIB
M336K7_REQUIRED_FREE_AFTER_RESERVATION_BYTES = 8 * GIB
M336K7_REQUIRED_FREE_INODES = 200_000
# This is the already-qualified M336K5 formula applied to the Q31 peak RSS:
# ceil(3 * 1_233_772_544 / 2) + 1 GiB.  It is intentionally not weakened.
M336K7_REQUIRED_AVAILABLE_RAM_BYTES = 2_924_400_640
M336K7_MAXIMUM_ALLOWED_SWAP_BYTES = 8 * GIB
M336K7_LONG_PHASE_SAMPLE_INTERVAL_SECONDS = 60
M336K7_PHASE_TOKENS = ("f30", "f31", "f32", "pre_f", "post_f")
M336K7_FINAL_CANDIDATE_POOL_HASH = (
    "b48ee354dc710a6c0ac0ed2cfceb1385c0d12cc8efb6b8fbef00e8d2f6ab572e"
)
M336K7_FINAL_CANDIDATE_POOL_BYTES_HASH = (
    "78cfb85fc59687186f0e420d410bf648816bce6ae2539acb445f8da74d77a0fa"
)
M336K7_FINAL_CANDIDATE_COUNT = 96
M336K7_FINAL_ORGANIZATION_COUNT = 64
M336K7_FINAL_MAXIMUM_CANDIDATES_PER_ORGANIZATION = 2
_HASH_LENGTH = 64


def _is_hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _HASH_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _strict_fields(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise M336K2ProtocolError(f"M336K7 {label} fields changed")
    return value


def _field_names(cls: type) -> set[str]:
    return {field.name for field in fields(cls)}


def _hash_body(value: object, hash_field: str) -> tuple[dict[str, Any], str]:
    if type(value) is not dict or hash_field not in value:
        raise M336K2ProtocolError("M336K7 hashed object is invalid")
    body = dict(value)
    claimed = body.pop(hash_field)
    if not _is_hash(claimed) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K7 object semantic hash changed")
    return body, claimed


def verify_m336k7_unchanged_candidate_pool(path: Path) -> dict[str, Any]:
    """Require the exact metadata-only pool authorized for the one-shot route."""
    raw = path.resolve(strict=True).read_bytes()
    if bytes_hash(raw) != M336K7_FINAL_CANDIDATE_POOL_BYTES_HASH:
        raise M336K2ProtocolError("M336K7 candidate-pool bytes changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError(
            "M336K7 candidate pool is not canonical JSON"
        ) from error
    _body, claimed = _hash_body(value, "pool_hash")
    if claimed != M336K7_FINAL_CANDIDATE_POOL_HASH:
        raise M336K2ProtocolError("M336K7 candidate-pool semantic hash changed")
    expected = (
        M336K7_FINAL_CANDIDATE_COUNT,
        M336K7_FINAL_ORGANIZATION_COUNT,
        M336K7_FINAL_MAXIMUM_CANDIDATES_PER_ORGANIZATION,
    )
    observed = (
        value.get("candidate_count"),
        value.get("organization_count"),
        value.get("maximum_candidates_per_organization"),
    )
    if observed != expected or len(value.get("candidates", ())) != expected[0]:
        raise M336K2ProtocolError("M336K7 candidate-pool population changed")
    if value.get("pre_freeze_source_body_bytes") != 0:
        raise M336K2ProtocolError("M336K7 candidate pool contains source bodies")
    return value


@dataclass(frozen=True)
class M336K7ResourceBudgetPolicy:
    schema_version: int
    contract_role: str
    required_private_storage_bytes: int
    required_free_after_reservation_bytes: int
    required_free_inodes: int
    required_available_ram_bytes: int
    maximum_allowed_swap_bytes: int
    storage_reservation_bytes: int
    long_phase_sample_interval_seconds: int
    policy_hash: str

    ROLE: ClassVar[str] = "M336K7_RESOURCE_BUDGET_POLICY"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("policy_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "policy_hash": self.policy_hash}

    def verify(self) -> None:
        field_names = tuple(_field_names(type(self)))
        integers = (
            self.required_private_storage_bytes,
            self.required_free_after_reservation_bytes,
            self.required_free_inodes,
            self.required_available_ram_bytes,
            self.maximum_allowed_swap_bytes,
            self.storage_reservation_bytes,
            self.long_phase_sample_interval_seconds,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(
                token in name.casefold()
                for name in field_names
                for token in M336K7_PHASE_TOKENS
            )
            or any(type(value) is not int or value < 0 for value in integers)
            or self.required_private_storage_bytes <= 0
            or self.required_free_after_reservation_bytes <= 0
            or self.required_free_inodes <= 0
            or self.required_available_ram_bytes <= 0
            or self.storage_reservation_bytes <= 0
            or not 1 <= self.long_phase_sample_interval_seconds <= 60
            or self.policy_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 resource budget policy is invalid")

    @classmethod
    def build(cls, *, storage_reservation_bytes: int) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "required_private_storage_bytes": M336K7_REQUIRED_PRIVATE_STORAGE_BYTES,
            "required_free_after_reservation_bytes": M336K7_REQUIRED_FREE_AFTER_RESERVATION_BYTES,
            "required_free_inodes": M336K7_REQUIRED_FREE_INODES,
            "required_available_ram_bytes": M336K7_REQUIRED_AVAILABLE_RAM_BYTES,
            "maximum_allowed_swap_bytes": M336K7_MAXIMUM_ALLOWED_SWAP_BYTES,
            "storage_reservation_bytes": storage_reservation_bytes,
            "long_phase_sample_interval_seconds": M336K7_LONG_PHASE_SAMPLE_INTERVAL_SECONDS,
        }
        result = cls(**body, policy_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, _field_names(cls), "resource budget policy")
        result = cls(**strict)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K7ResourceObservationReceipt:
    schema_version: int
    contract_role: str
    sample_count: int
    sample_chain_hash: str
    minimum_available_ram_bytes: int
    maximum_process_tree_peak_rss_bytes: int
    maximum_swap_used_bytes: int
    minimum_filesystem_free_bytes: int
    minimum_filesystem_free_inodes: int
    maximum_capsule_size_bytes: int
    maximum_official_vault_size_bytes: int
    maximum_selected_snapshot_size_bytes: int
    maximum_production_roots_size_bytes: int
    maximum_evaluator_root_size_bytes: int
    maximum_active_task_process_count: int
    observation_hash: str

    ROLE: ClassVar[str] = "PUBLIC_SAFE_M336K7_RESOURCE_OBSERVATION_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("observation_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "observation_hash": self.observation_hash}

    def verify(self) -> None:
        measured = tuple(
            value
            for name, value in self._body().items()
            if name not in {"schema_version", "contract_role", "sample_chain_hash"}
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.sample_count < 1
            or not _is_hash(self.sample_chain_hash)
            or any(type(value) is not int or value < 0 for value in measured)
            or self.observation_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 resource observation is invalid")

    @classmethod
    def from_samples(cls, samples: tuple[M336K6ResourceSample, ...]) -> Self:
        if not samples:
            raise M336K2ProtocolError("M336K7 resource observation is empty")
        previous: str | None = None
        for sequence, sample in enumerate(samples, 1):
            body = asdict(sample)
            claimed = body.pop("sample_hash")
            if (
                set(asdict(sample)) != _field_names(M336K6ResourceSample)
                or sample.schema_version != 1
                or sample.contract_role != "M336K6_PRIVATE_RESOURCE_SAMPLE"
                or sample.sequence != sequence
                or sample.previous_sample_hash != previous
                or content_hash(body) != claimed
            ):
                raise M336K2ProtocolError("M336K7 resource sample chain is invalid")
            previous = sample.sample_hash
        inode_values = tuple(
            sample.filesystem_free_inodes
            for sample in samples
            if sample.filesystem_free_inodes > 0
        )
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "sample_count": len(samples),
            "sample_chain_hash": samples[-1].sample_hash,
            "minimum_available_ram_bytes": min(
                sample.system_available_ram_bytes for sample in samples
            ),
            "maximum_process_tree_peak_rss_bytes": max(
                sample.process_tree_peak_rss_bytes for sample in samples
            ),
            "maximum_swap_used_bytes": max(
                sample.swap_used_bytes for sample in samples
            ),
            "minimum_filesystem_free_bytes": min(
                sample.filesystem_free_bytes for sample in samples
            ),
            "minimum_filesystem_free_inodes": min(inode_values) if inode_values else 0,
            "maximum_capsule_size_bytes": max(
                sample.capsule_size_bytes for sample in samples
            ),
            "maximum_official_vault_size_bytes": max(
                sample.official_vault_size_bytes for sample in samples
            ),
            "maximum_selected_snapshot_size_bytes": max(
                sample.selected_snapshot_size_bytes for sample in samples
            ),
            "maximum_production_roots_size_bytes": max(
                sample.production_roots_size_bytes for sample in samples
            ),
            "maximum_evaluator_root_size_bytes": max(
                sample.evaluator_root_size_bytes for sample in samples
            ),
            "maximum_active_task_process_count": max(
                sample.active_task_process_count for sample in samples
            ),
        }
        result = cls(**body, observation_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_m336k6_aggregate(cls, value: dict[str, Any]) -> Self:
        """Project the already-measured Q31 aggregate into the observation schema."""

        expected = {
            "schema_version",
            "contract_role",
            "source_receipt_hashes",
            "source_sample_count",
            "minimum_available_ram_bytes",
            "maximum_process_tree_peak_rss_bytes",
            "maximum_swap_used_bytes",
            "minimum_filesystem_free_bytes",
            "minimum_filesystem_free_inodes",
            "maximum_capsule_size_bytes",
            "maximum_official_vault_size_bytes",
            "maximum_selected_snapshot_size_bytes",
            "maximum_production_roots_size_bytes",
            "maximum_evaluator_root_size_bytes",
            "frozen_official_storage_budget_bytes",
            "required_pre_reservation_free_bytes",
            "required_post_reservation_free_bytes",
            "pre_reservation_storage_status",
            "post_reservation_storage_status",
            "inode_budget_status",
            "status",
            "receipt_hash",
        }
        strict = _strict_fields(value, expected, "M336K6 aggregate resource receipt")
        _hash_body(strict, "receipt_hash")
        source_hashes = strict["source_receipt_hashes"]
        if (
            strict["schema_version"] != 1
            or strict["contract_role"] != "PUBLIC_SAFE_M336K6_RESOURCE_MONITOR_RECEIPT"
            or type(source_hashes) is not list
            or not source_hashes
            or any(not _is_hash(item) for item in source_hashes)
            or strict["status"] != "PASS"
        ):
            raise M336K2ProtocolError("M336K6 aggregate resource receipt is invalid")
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "sample_count": strict["source_sample_count"],
            "sample_chain_hash": content_hash(tuple(source_hashes)),
            "minimum_available_ram_bytes": strict["minimum_available_ram_bytes"],
            "maximum_process_tree_peak_rss_bytes": strict[
                "maximum_process_tree_peak_rss_bytes"
            ],
            "maximum_swap_used_bytes": strict["maximum_swap_used_bytes"],
            "minimum_filesystem_free_bytes": strict["minimum_filesystem_free_bytes"],
            "minimum_filesystem_free_inodes": strict["minimum_filesystem_free_inodes"],
            "maximum_capsule_size_bytes": strict["maximum_capsule_size_bytes"],
            "maximum_official_vault_size_bytes": strict[
                "maximum_official_vault_size_bytes"
            ],
            "maximum_selected_snapshot_size_bytes": strict[
                "maximum_selected_snapshot_size_bytes"
            ],
            "maximum_production_roots_size_bytes": strict[
                "maximum_production_roots_size_bytes"
            ],
            "maximum_evaluator_root_size_bytes": strict[
                "maximum_evaluator_root_size_bytes"
            ],
            "maximum_active_task_process_count": 1,
        }
        result = cls(**body, observation_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, _field_names(cls), "resource observation")
        result = cls(**strict)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K7ResourceGateReceipt:
    schema_version: int
    contract_role: str
    resource_budget_policy_hash: str
    resource_observation_hash: str
    storage_reservation_receipt_hash: str
    filesystem_identity_hash: str
    storage_pass: bool
    inode_pass: bool
    ram_pass: bool
    swap_pass: bool
    reservation_pass: bool
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "PUBLIC_SAFE_M336K7_RESOURCE_GATE_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        passes = (
            self.storage_pass,
            self.inode_pass,
            self.ram_pass,
            self.swap_pass,
            self.reservation_pass,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(type(value) is not bool for value in passes)
            or any(
                not _is_hash(value)
                for value in (
                    self.resource_budget_policy_hash,
                    self.resource_observation_hash,
                    self.storage_reservation_receipt_hash,
                    self.filesystem_identity_hash,
                    self.receipt_hash,
                )
            )
            or self.status != ("PASS" if all(passes) else "FAIL")
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 resource gate receipt is invalid")

    @classmethod
    def build(
        cls,
        policy: M336K7ResourceBudgetPolicy,
        observation: M336K7ResourceObservationReceipt,
        reservation: M336K5StorageReservationReceipt,
    ) -> Self:
        policy.verify()
        observation.verify()
        verify_m336k7_storage_reservation(reservation)
        inode_pass = (
            observation.minimum_filesystem_free_inodes == 0
            or observation.minimum_filesystem_free_inodes >= policy.required_free_inodes
        )
        passes = {
            "storage_pass": (
                observation.minimum_filesystem_free_bytes
                >= policy.required_private_storage_bytes
            ),
            "inode_pass": inode_pass,
            "ram_pass": (
                observation.minimum_available_ram_bytes
                >= policy.required_available_ram_bytes
            ),
            "swap_pass": (
                observation.maximum_swap_used_bytes <= policy.maximum_allowed_swap_bytes
            ),
            "reservation_pass": (
                reservation.status == "PASS"
                and reservation.sparse is False
                and reservation.reservation_bytes == policy.storage_reservation_bytes
                and reservation.allocated_size_bytes >= policy.storage_reservation_bytes
                and reservation.free_bytes_after
                >= policy.required_free_after_reservation_bytes
                and reservation.minimum_post_reservation_free_bytes
                == policy.required_free_after_reservation_bytes
            ),
        }
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "resource_budget_policy_hash": policy.policy_hash,
            "resource_observation_hash": observation.observation_hash,
            "storage_reservation_receipt_hash": reservation.receipt_hash,
            "filesystem_identity_hash": reservation.filesystem_identity_hash,
            **passes,
            "status": "PASS" if all(passes.values()) else "FAIL",
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, _field_names(cls), "resource gate")
        result = cls(**strict)
        result.verify()
        return result


def storage_reservation_from_dict(
    value: dict[str, Any],
) -> M336K5StorageReservationReceipt:
    strict = _strict_fields(
        value,
        _field_names(M336K5StorageReservationReceipt),
        "storage reservation",
    )
    result = M336K5StorageReservationReceipt(**strict)
    verify_m336k7_storage_reservation(result)
    return result


def verify_m336k7_storage_reservation(
    receipt: M336K5StorageReservationReceipt,
) -> None:
    value = asdict(receipt)
    body = dict(value)
    claimed = body.pop("receipt_hash")
    if (
        receipt.schema_version != 1
        or receipt.contract_role != "PUBLIC_SAFE_M336K5_STORAGE_RESERVATION_RECEIPT"
        or receipt.reservation_bytes <= 0
        or receipt.allocated_size_bytes < receipt.reservation_bytes
        or receipt.free_bytes_before < receipt.free_bytes_after
        or receipt.minimum_post_reservation_free_bytes <= 0
        or receipt.sparse is not False
        or receipt.status != "PASS"
        or not _is_hash(receipt.reservation_content_hash)
        or not _is_hash(receipt.filesystem_identity_hash)
        or not _is_hash(claimed)
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K7 storage reservation is invalid")


def verify_m336k7_resource_gate_binding(
    policy: M336K7ResourceBudgetPolicy,
    observation: M336K7ResourceObservationReceipt,
    reservation: M336K5StorageReservationReceipt,
    gate: M336K7ResourceGateReceipt,
) -> None:
    expected = M336K7ResourceGateReceipt.build(policy, observation, reservation)
    if gate != expected or gate.status != "PASS":
        raise M336K2ProtocolError("M336K7 resource gate binding changed")


@dataclass(frozen=True)
class M336K7StorageReservationReleaseReceipt:
    schema_version: int
    contract_role: str
    storage_reservation_receipt_hash: str
    reservation_file_identity_hash: str
    released_bytes: int
    free_bytes_before_release: int
    free_bytes_after_release: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "PUBLIC_SAFE_M336K7_STORAGE_RESERVATION_RELEASE"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or not _is_hash(self.storage_reservation_receipt_hash)
            or not _is_hash(self.reservation_file_identity_hash)
            or type(self.released_bytes) is not int
            or self.released_bytes <= 0
            or type(self.free_bytes_before_release) is not int
            or self.free_bytes_before_release < 0
            or type(self.free_bytes_after_release) is not int
            or self.free_bytes_after_release < self.free_bytes_before_release
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 reservation release receipt is invalid")

    @classmethod
    def build(
        cls,
        *,
        reservation: M336K5StorageReservationReceipt,
        reservation_file: Path,
        free_bytes_before_release: int,
        free_bytes_after_release: int,
    ) -> Self:
        verify_m336k7_storage_reservation(reservation)
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "storage_reservation_receipt_hash": reservation.receipt_hash,
            "reservation_file_identity_hash": content_hash(
                os.path.normcase(str(reservation_file.resolve(strict=False)))
            ),
            "released_bytes": reservation.reservation_bytes,
            "free_bytes_before_release": free_bytes_before_release,
            "free_bytes_after_release": free_bytes_after_release,
            "status": "PASS",
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, _field_names(cls), "reservation release")
        result = cls(**strict)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K7PersistentCapsuleBindingSet:
    schema_version: int
    contract_role: str
    implementation_tip: str
    capsule_identity_hash: str
    capsule_root_identity_hash: str
    capsule_content_manifest_hash: str
    capsule_lifecycle_policy_hash: str
    capsule_liveness_receipt_hash: str
    persistent_capsule_public_receipt_hash: str
    legacy_public_capsule_receipt_hash: str
    python_environment_manifest_hash: str
    executable_dependency_manifest_hash: str
    startup_policy_hash: str
    bootstrap_source_hash: str
    launcher_source_hash: str
    stable_karina_host_identity_hash: str
    preservation_set_hash: str
    cleanup_cutoff_receipt_hash: str
    binding_set_hash: str

    ROLE: ClassVar[str] = "M336K7_PERSISTENT_CAPSULE_BINDING_SET"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("binding_set_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "binding_set_hash": self.binding_set_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or type(self.implementation_tip) is not str
            or len(self.implementation_tip) != 40
            or any(not _is_hash(value) for value in hashes)
            or self.binding_set_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 capsule binding set is invalid")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = {"schema_version": 1, "contract_role": cls.ROLE, **values}
        if set(body) != _field_names(cls) - {"binding_set_hash"}:
            raise M336K2ProtocolError("M336K7 capsule binding inputs changed")
        result = cls(**body, binding_set_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, _field_names(cls), "capsule binding set")
        result = cls(**strict)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K7LegacyCapsuleCompatibilityReceipt:
    schema_version: int
    contract_role: str
    persistent_public_receipt_hash: str
    legacy_public_receipt_hash: str
    executable_dependency_manifest_hash: str
    host_identity_hash: str
    python_environment_manifest_hash: str
    compatibility_status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "PUBLIC_SAFE_M336K7_LEGACY_CAPSULE_COMPATIBILITY_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        hashes = tuple(
            value for name, value in self._body().items() if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(not _is_hash(value) for value in hashes)
            or self.compatibility_status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 legacy capsule compatibility is invalid")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = {"schema_version": 1, "contract_role": cls.ROLE, **values}
        if set(body) != _field_names(cls) - {"receipt_hash"}:
            raise M336K2ProtocolError("M336K7 legacy compatibility inputs changed")
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, _field_names(cls), "legacy compatibility")
        result = cls(**strict)
        result.verify()
        return result


def verify_m336k7_capsule_compatibility_binding(
    binding: M336K7PersistentCapsuleBindingSet,
    compatibility: M336K7LegacyCapsuleCompatibilityReceipt,
) -> None:
    binding.verify()
    compatibility.verify()
    if (
        compatibility.persistent_public_receipt_hash
        != binding.persistent_capsule_public_receipt_hash
        or compatibility.legacy_public_receipt_hash
        != binding.legacy_public_capsule_receipt_hash
        or compatibility.executable_dependency_manifest_hash
        != binding.executable_dependency_manifest_hash
        or compatibility.host_identity_hash != binding.stable_karina_host_identity_hash
        or compatibility.python_environment_manifest_hash
        != binding.python_environment_manifest_hash
    ):
        raise M336K2ProtocolError("M336K7 legacy compatibility binding changed")


@dataclass(frozen=True)
class M336K7PostFreezeInputBundle:
    schema_version: int
    contract_role: str
    freeze_manifest_contract_hash: str
    final_authorization_hash: str
    route_identity_bundle_hash: str
    route_registry_hash: str
    route_manifest_hash: str
    legacy_capsule_route_registry_hash: str
    legacy_capsule_route_manifest_hash: str
    resource_budget_policy_hash: str
    resource_observation_hash: str
    storage_reservation_receipt_hash: str
    resource_gate_receipt_hash: str
    capsule_binding_set_hash: str
    legacy_compatibility_receipt_hash: str
    liveness_receipt_hash: str
    startup_policy_hash: str
    executable_dependency_manifest_hash: str
    windows_jdk_identity_hash: str
    karina_jdk_identity_hash: str
    karina_host_identity_hash: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    archive_policy_hash: str
    terminal_policy_hash: str
    selector_policy_hash: str
    evaluator_policy_hash: str
    threshold_manifest_hash: str
    publication_contract_hash: str
    bundle_hash: str

    ROLE: ClassVar[str] = "M336K7_POST_FREEZE_INPUT_BUNDLE"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("bundle_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "bundle_hash": self.bundle_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or any(not _is_hash(value) for value in hashes)
            or self.bundle_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 post-freeze input bundle is invalid")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = {"schema_version": 1, "contract_role": cls.ROLE, **values}
        if set(body) != _field_names(cls) - {"bundle_hash"}:
            raise M336K2ProtocolError("M336K7 post-freeze bundle inputs changed")
        result = cls(**body, bundle_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        strict = _strict_fields(value, _field_names(cls), "post-freeze input bundle")
        result = cls(**strict)
        result.verify()
        return result


def build_m336k7_persistent_capsule_route_registry(
    content_value: dict[str, Any],
) -> M336K2RouteRegistry:
    """Derive legacy remote route authority from frozen capsule source bytes."""

    manifest = M336K6CapsuleContentManifest.from_dict(content_value)
    entries = {item.relative_path: item for item in manifest.entries}
    components = []
    for role, relative_path in M336K2_ROUTE_COMPONENTS:
        entry = entries.get(relative_path)
        if entry is None:
            raise M336K2ProtocolError(
                "M336K7 persistent capsule route component is absent"
            )
        body = {
            "role": role,
            "repository_path": relative_path,
            "source_bytes_hash": entry.bytes_hash,
            "source_byte_count": entry.byte_count,
        }
        components.append(
            M336K2RouteComponent(**body, component_hash=content_hash(body))
        )
    roles = {item.role for item in components}
    body = {
        "schema_version": 1,
        "route_version": "m336k2.candidate-isolated-java-final-route.v1",
        "components": tuple(components),
        "native_h28_publisher_registered": "H28_PUBLISHER" in roles,
        "native_e28_publisher_registered": "E28_PUBLISHER" in roles,
        "final_commit_verifier_registered": "COMMIT_VERIFIER" in roles,
        "missing_component_count": 0,
    }
    result = M336K2RouteRegistry(**body, registry_hash=content_hash(body))
    if not (
        result.native_h28_publisher_registered
        and result.native_e28_publisher_registered
        and result.final_commit_verifier_registered
    ):
        raise M336K2ProtocolError(
            "M336K7 persistent capsule route registry is incomplete"
        )
    return result


def build_m336k7_persistent_capsule_route_manifest(
    route_value: dict[str, Any],
    registry: M336K2RouteRegistry,
) -> M336K2RouteManifest:
    """Retain run-specific bindings while using capsule-owned route source."""

    strict = _strict_fields(
        route_value,
        _field_names(M336K2RouteManifest),
        "persistent capsule route manifest",
    )
    route = M336K2RouteManifest(**strict)
    body = asdict(route)
    claimed = body.pop("manifest_hash")
    if content_hash(body) != claimed:
        raise M336K2ProtocolError(
            "M336K7 persistent capsule route manifest hash changed"
        )
    result = build_m336k2_route_manifest(
        registry=registry,
        executable_dependency_manifest_hash=route.executable_dependency_manifest_hash,
        python_environment_manifest_hash=route.python_environment_manifest_hash,
        command_renderer_hash=route.command_renderer_hash,
        minimal_environment_policy_hash=route.minimal_environment_policy_hash,
    )
    return result


def verify_m336k7_persistent_capsule_route_binding(
    *,
    content_value: dict[str, Any],
    registry_value: dict[str, Any],
    route_value: dict[str, Any],
) -> tuple[M336K2RouteRegistry, M336K2RouteManifest]:
    """Reject a committed legacy route that differs from preserved capsule bytes."""

    expected_registry = build_m336k7_persistent_capsule_route_registry(content_value)
    if canonical_json(registry_value) != canonical_json(expected_registry):
        raise M336K2ProtocolError(
            "M336K7 frozen route registry differs from persistent capsule"
        )
    expected_route = build_m336k7_persistent_capsule_route_manifest(
        route_value, expected_registry
    )
    if canonical_json(route_value) != canonical_json(expected_route):
        raise M336K2ProtocolError(
            "M336K7 frozen route manifest differs from persistent capsule"
        )
    return expected_registry, expected_route


@dataclass(frozen=True)
class M336K7FrozenContractArtifactResult:
    artifact_name: str
    producer_schema_hash: str
    consumer_schema_hash: str
    producer_field_count: int
    consumer_field_count: int
    missing_field_count: int
    extra_field_count: int
    roundtrip_difference_count: int
    semantic_binding_mismatch_count: int
    status: str


@dataclass(frozen=True)
class M336K7StrictArtifact:
    """Runtime typed consumer for frozen schemas owned by unchanged producers."""

    value: dict[str, Any]

    def canonical_object(self) -> dict[str, Any]:
        return self.value

    @classmethod
    def consume(
        cls,
        value: dict[str, Any],
        *,
        expected_fields: frozenset[str],
        semantic_role: str | None,
        hash_field: str,
    ) -> Self:
        strict = _strict_fields(value, set(expected_fields), "frozen artifact")
        if semantic_role is not None and strict["contract_role"] != semantic_role:
            raise M336K2ProtocolError("M336K7 frozen artifact role changed")
        _hash_body(strict, hash_field)
        return cls(dict(strict))


@dataclass(frozen=True)
class M336K7FrozenContractCompatibilityGate:
    schema_version: int
    contract_role: str
    artifacts: tuple[M336K7FrozenContractArtifactResult, ...]
    artifact_count: int
    missing_field_count: int
    extra_field_count: int
    roundtrip_difference_count: int
    semantic_binding_mismatch_count: int
    phase_specific_active_field_count: int
    mandatory_default_lookup_count: int
    direct_legacy_capsule_comparison_count: int
    status: str
    report_hash: str

    ROLE: ClassVar[str] = "M336K7_FROZEN_CONTRACT_COMPATIBILITY_GATE"

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "artifacts": tuple(asdict(item) for item in self.artifacts),
            "artifact_count": self.artifact_count,
            "missing_field_count": self.missing_field_count,
            "extra_field_count": self.extra_field_count,
            "roundtrip_difference_count": self.roundtrip_difference_count,
            "semantic_binding_mismatch_count": self.semantic_binding_mismatch_count,
            "phase_specific_active_field_count": self.phase_specific_active_field_count,
            "mandatory_default_lookup_count": self.mandatory_default_lookup_count,
            "direct_legacy_capsule_comparison_count": self.direct_legacy_capsule_comparison_count,
            "status": self.status,
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "report_hash": self.report_hash}

    def verify(self) -> None:
        totals = (
            self.missing_field_count,
            self.extra_field_count,
            self.roundtrip_difference_count,
            self.semantic_binding_mismatch_count,
            self.phase_specific_active_field_count,
            self.mandatory_default_lookup_count,
            self.direct_legacy_capsule_comparison_count,
        )
        passed = not any(totals) and all(
            item.status == "PASS" for item in self.artifacts
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.artifact_count != len(self.artifacts)
            or any(value < 0 for value in totals)
            or self.status != ("PASS" if passed else "FAIL")
            or self.report_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 compatibility gate is invalid")

    @classmethod
    def run(
        cls,
        artifacts: dict[str, tuple[dict[str, Any], Callable[[dict[str, Any]], Any]]],
        *,
        current_route_sources: tuple[Path, ...],
    ) -> Self:
        results = []
        for name in sorted(artifacts):
            produced, consumer = artifacts[name]
            produced_bytes = (canonical_json(produced) + "\n").encode("utf-8")
            loaded = consumer(produced)
            canonical_object = loaded.canonical_object()
            consumer_bytes = (canonical_json(canonical_object) + "\n").encode("utf-8")
            producer_fields = set(produced)
            consumer_fields = set(canonical_object)
            missing = consumer_fields - producer_fields
            extra = producer_fields - consumer_fields
            differences = 0 if produced_bytes == consumer_bytes else 1
            schema_hash = content_hash(tuple(sorted(producer_fields)))
            consumer_hash = content_hash(tuple(sorted(consumer_fields)))
            mismatches = 0
            status = "PASS" if not missing and not extra and not differences else "FAIL"
            results.append(
                M336K7FrozenContractArtifactResult(
                    artifact_name=name,
                    producer_schema_hash=schema_hash,
                    consumer_schema_hash=consumer_hash,
                    producer_field_count=len(producer_fields),
                    consumer_field_count=len(consumer_fields),
                    missing_field_count=len(missing),
                    extra_field_count=len(extra),
                    roundtrip_difference_count=differences,
                    semantic_binding_mismatch_count=mismatches,
                    status=status,
                )
            )
        source = "\n".join(
            path.read_text(encoding="utf-8") for path in current_route_sources
        )
        phase_count = sum(
            token in name.casefold()
            for name in _field_names(M336K7ResourceBudgetPolicy)
            for token in M336K7_PHASE_TOKENS
        )
        mandatory_defaults = source.count(".get(")
        legacy_comparisons = source.count("frozen_capsule.get(")
        totals = {
            "missing_field_count": sum(item.missing_field_count for item in results),
            "extra_field_count": sum(item.extra_field_count for item in results),
            "roundtrip_difference_count": sum(
                item.roundtrip_difference_count for item in results
            ),
            "semantic_binding_mismatch_count": sum(
                item.semantic_binding_mismatch_count for item in results
            ),
            "phase_specific_active_field_count": phase_count,
            "mandatory_default_lookup_count": mandatory_defaults,
            "direct_legacy_capsule_comparison_count": legacy_comparisons,
        }
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "artifacts": tuple(results),
            "artifact_count": len(results),
            **totals,
            "status": (
                "PASS"
                if not any(totals.values())
                and all(item.status == "PASS" for item in results)
                else "FAIL"
            ),
        }
        temporary = cls(**body, report_hash="0" * 64)
        result = cls(**body, report_hash=content_hash(temporary._body()))
        result.verify()
        return result


def forbid_m336k7_post_freeze_mutation(*, exact_f32_sha: str, operation: str) -> None:
    """Reject cleanup/capsule mutation after an exact F32 has been bound."""

    if exact_f32_sha != "0" * 40 and operation in {
        "CLEANUP",
        "CAPSULE_RECREATE",
        "CAPSULE_REMOVE",
    }:
        raise M336K2ProtocolError("M336K7 mutation is forbidden after F32")


def require_m336k7_frozen_bytes(expected: bytes, consumed: bytes) -> None:
    if expected != consumed:
        raise M336K2ProtocolError("M336K7 committed frozen bytes were replaced")
