"""Immutable preservation set and phase-gated cleanup planner for M-33.6k.6."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePath, PurePosixPath, PureWindowsPath
from typing import Any, Self

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError

M336K6_PRESERVATION_REJECTION = "PRESERVATION_SET_INTERSECTION"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OFFICIAL_ROLES = frozenset(
    {
        "OFFICIAL_ARTIFACT",
        "OFFICIAL_LEDGER",
        "OFFICIAL_VAULT",
        "SELECTED_SNAPSHOT",
        "PRODUCTION_ROOT",
        "EVALUATOR_ROOT",
        "STORAGE_RESERVATION",
    }
)
_ACTIVE_PHASES = frozenset(
    {
        "F31_CREATION",
        "POST_F31_VALIDATE_ONLY",
        "OFFICIAL_ACQUISITION",
        "OFFICIAL_PRODUCTION",
        "OFFICIAL_EVALUATION",
        "H31_PUBLICATION",
        "E31_PUBLICATION",
    }
)


class M336K6CleanupMode(StrEnum):
    PRE_FREEZE = "PRE_FREEZE"
    POST_SUCCESS = "POST_SUCCESS"


@dataclass(frozen=True)
class M336K6PreservedResource:
    schema_version: int
    opaque_resource_id: str
    role: str
    content_tree_hash: str
    lifecycle_owner: str
    required_until_phase: str
    path_identity_hash: str
    ancestor_identity_hashes: tuple[str, ...]
    descendant_policy: str
    resolved_target_identity_hash: str
    path_class: str
    private_path: str
    resource_hash: str

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("resource_hash")
        return value

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or not self.role
            or not self.lifecycle_owner
            or not self.required_until_phase
            or self.descendant_policy != "PRESERVE_ALL_DESCENDANTS"
            or not _absolute(self.private_path)
            or any(
                _SHA256.fullmatch(value) is None
                for value in (
                    self.opaque_resource_id,
                    self.content_tree_hash,
                    self.path_identity_hash,
                    self.resolved_target_identity_hash,
                    self.resource_hash,
                    *self.ancestor_identity_hashes,
                )
            )
            or self.path_identity_hash
            != content_hash(("M336K6_PRIVATE_PATH", _normalize(self.private_path)))
            or self.resource_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K6 preserved resource is invalid")

    @classmethod
    def build(
        cls,
        *,
        role: str,
        private_path: str,
        content_tree_hash: str,
        lifecycle_owner: str,
        required_until_phase: str,
        path_class: str,
        resolved_target_path: str | None = None,
    ) -> Self:
        normalized = _normalize(private_path)
        path = _pure_path(normalized)
        ancestors = tuple(
            content_hash(("M336K6_PRIVATE_PATH", _normalize(str(parent))))
            for parent in path.parents
            if _absolute(str(parent))
        )
        target = _normalize(resolved_target_path or private_path)
        body = {
            "schema_version": 1,
            "opaque_resource_id": content_hash(("M336K6_RESOURCE", role, normalized)),
            "role": role,
            "content_tree_hash": content_tree_hash,
            "lifecycle_owner": lifecycle_owner,
            "required_until_phase": required_until_phase,
            "path_identity_hash": content_hash(("M336K6_PRIVATE_PATH", normalized)),
            "ancestor_identity_hashes": ancestors,
            "descendant_policy": "PRESERVE_ALL_DESCENDANTS",
            "resolved_target_identity_hash": content_hash(
                ("M336K6_PRIVATE_PATH", target)
            ),
            "path_class": path_class,
            "private_path": normalized,
        }
        result = cls(**body, resource_hash=content_hash(body))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K6PreservationSet:
    schema_version: int
    contract_role: str
    resources: tuple[M336K6PreservedResource, ...]
    resource_count: int
    set_hash: str

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("set_hash")
        return value

    def verify(self) -> None:
        for resource in self.resources:
            resource.verify()
        if (
            self.schema_version != 1
            or self.contract_role != "M336K6_IMMUTABLE_PRESERVATION_SET"
            or self.resources
            != tuple(sorted(self.resources, key=lambda item: item.opaque_resource_id))
            or len({item.opaque_resource_id for item in self.resources})
            != len(self.resources)
            or self.resource_count != len(self.resources)
            or self.set_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K6 preservation set is invalid")

    @classmethod
    def build(cls, resources: Iterable[M336K6PreservedResource]) -> Self:
        ordered = tuple(sorted(resources, key=lambda item: item.opaque_resource_id))
        body = {
            "schema_version": 1,
            "contract_role": "M336K6_IMMUTABLE_PRESERVATION_SET",
            "resources": ordered,
            "resource_count": len(ordered),
        }
        result = cls(**body, set_hash=content_hash(body))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K6PreservationReceipt:
    schema_version: int
    contract_role: str
    preservation_set_hash: str
    preserved_resource_count: int
    capsule_resource_count: int
    official_resource_count: int
    status: str
    receipt_hash: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K6 preservation receipt fields changed")
        result = cls(**value)
        body = asdict(result)
        claimed = body.pop("receipt_hash")
        if (
            _SHA256.fullmatch(result.preservation_set_hash) is None
            or min(
                result.preserved_resource_count,
                result.capsule_resource_count,
                result.official_resource_count,
            )
            < 0
            or result.status != "PASS"
            or content_hash(body) != claimed
        ):
            raise M336K2ProtocolError("M336K6 preservation receipt is invalid")
        return result


@dataclass(frozen=True)
class M336K6CleanupCandidate:
    schema_version: int
    opaque_root_id: str
    private_path: str
    category: str
    tree_hash: str
    project_generated: bool
    terminal: bool
    lifecycle_ended: bool
    active_process_count: int
    open_file_count: int
    current_receipt_reference_count: int
    official_role: str | None
    resolved_target_paths: tuple[str, ...]

    @classmethod
    def build(
        cls,
        *,
        private_path: str,
        category: str,
        tree_hash: str,
        project_generated: bool = True,
        terminal: bool = True,
        lifecycle_ended: bool = True,
        active_process_count: int = 0,
        open_file_count: int = 0,
        current_receipt_reference_count: int = 0,
        official_role: str | None = None,
        resolved_target_paths: Iterable[str] = (),
    ) -> Self:
        normalized = _normalize(private_path)
        if not _absolute(normalized) or _SHA256.fullmatch(tree_hash) is None:
            raise M336K2ProtocolError("M336K6 cleanup candidate identity is invalid")
        return cls(
            schema_version=1,
            opaque_root_id=content_hash(("M336K6_CLEANUP_ROOT", normalized)),
            private_path=normalized,
            category=category,
            tree_hash=tree_hash,
            project_generated=project_generated,
            terminal=terminal,
            lifecycle_ended=lifecycle_ended,
            active_process_count=active_process_count,
            open_file_count=open_file_count,
            current_receipt_reference_count=current_receipt_reference_count,
            official_role=official_role,
            resolved_target_paths=tuple(
                _normalize(item) for item in resolved_target_paths
            ),
        )


@dataclass(frozen=True)
class M336K6CleanupDecision:
    schema_version: int
    opaque_root_id: str
    category: str
    eligible: bool
    rejection_reason: str | None
    preservation_intersection_count: int
    decision_hash: str


@dataclass(frozen=True)
class M336K6CleanupPlan:
    schema_version: int
    contract_role: str
    mode: str
    phase: str
    preservation_set_hash: str
    decisions: tuple[M336K6CleanupDecision, ...]
    candidate_count: int
    eligible_count: int
    rejected_count: int
    preservation_rejection_count: int
    operation_count_after_f31: int
    plan_hash: str


@dataclass(frozen=True)
class M336K6CleanupReceipt:
    schema_version: int
    contract_role: str
    plan_hash: str
    mode: str
    deleted_root_count: int
    deleted_file_count: int
    reclaimed_bytes: int
    unrelated_data_deleted: bool
    operation_count_after_f31: int
    status: str
    receipt_hash: str


def preservation_receipt(
    preservation_set: M336K6PreservationSet,
) -> M336K6PreservationReceipt:
    preservation_set.verify()
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K6_PRESERVATION_RECEIPT",
        "preservation_set_hash": preservation_set.set_hash,
        "preserved_resource_count": len(preservation_set.resources),
        "capsule_resource_count": sum(
            item.role.startswith("PERSISTENT_CAPSULE")
            or item.role == "PERSISTENT_PYTHON_ENVIRONMENT"
            for item in preservation_set.resources
        ),
        "official_resource_count": sum(
            item.role in _OFFICIAL_ROLES for item in preservation_set.resources
        ),
        "status": "PASS",
    }
    return M336K6PreservationReceipt(**body, receipt_hash=content_hash(body))


def plan_m336k6_cleanup(
    *,
    candidates: Iterable[M336K6CleanupCandidate],
    preservation_set: M336K6PreservationSet,
    mode: M336K6CleanupMode,
    phase: str,
    f31_created: bool = False,
    reservation_released: bool = False,
) -> M336K6CleanupPlan:
    preservation_set.verify()
    if phase in _ACTIVE_PHASES or f31_created or reservation_released:
        raise M336K2ProtocolError("M336K6 cleanup is forbidden in the current phase")
    if mode is M336K6CleanupMode.POST_SUCCESS and phase != "POST_E31_SUCCESS":
        raise M336K2ProtocolError("M336K6 POST_SUCCESS cleanup requires E31 success")
    decisions = []
    for candidate in candidates:
        intersections = preservation_intersection_count(candidate, preservation_set)
        reason = None
        if intersections:
            reason = M336K6_PRESERVATION_REJECTION
        elif candidate.official_role in _OFFICIAL_ROLES:
            reason = "OFFICIAL_RESOURCE"
        elif candidate.active_process_count or candidate.open_file_count:
            reason = "ACTIVE_RESOURCE"
        elif candidate.current_receipt_reference_count:
            reason = "CURRENT_RECEIPT_REFERENCE"
        elif not candidate.lifecycle_ended:
            reason = "LIFECYCLE_NOT_ENDED"
        elif not candidate.project_generated or not candidate.terminal:
            reason = "NOT_TERMINAL_PROJECT_RESOURCE"
        body = {
            "schema_version": 1,
            "opaque_root_id": candidate.opaque_root_id,
            "category": candidate.category,
            "eligible": reason is None,
            "rejection_reason": reason,
            "preservation_intersection_count": intersections,
        }
        decisions.append(
            M336K6CleanupDecision(**body, decision_hash=content_hash(body))
        )
    ordered = tuple(sorted(decisions, key=lambda item: item.opaque_root_id))
    body = {
        "schema_version": 1,
        "contract_role": "M336K6_PHASE_GATED_CLEANUP_PLAN",
        "mode": mode.value,
        "phase": phase,
        "preservation_set_hash": preservation_set.set_hash,
        "decisions": ordered,
        "candidate_count": len(ordered),
        "eligible_count": sum(item.eligible for item in ordered),
        "rejected_count": sum(not item.eligible for item in ordered),
        "preservation_rejection_count": sum(
            item.rejection_reason == M336K6_PRESERVATION_REJECTION for item in ordered
        ),
        "operation_count_after_f31": 0,
    }
    return M336K6CleanupPlan(**body, plan_hash=content_hash(body))


def preservation_intersection_count(
    candidate: M336K6CleanupCandidate, preservation_set: M336K6PreservationSet
) -> int:
    paths = (candidate.private_path, *candidate.resolved_target_paths)
    count = 0
    for resource in preservation_set.resources:
        preserved = _pure_path(resource.private_path)
        if any(_intersects(_pure_path(path), preserved) for path in paths):
            count += 1
    return count


def _intersects(left: PurePath, right: PurePath) -> bool:
    return left == right or left in right.parents or right in left.parents


def _pure_path(value: str) -> PurePath:
    return (
        PureWindowsPath(value)
        if re.match(r"^[A-Za-z]:[\\/]", value)
        else PurePosixPath(value)
    )


def _absolute(value: str) -> bool:
    return _pure_path(value).is_absolute()


def _normalize(value: str) -> str:
    path = _pure_path(str(value))
    if not path.is_absolute() or ".." in path.parts:
        raise M336K2ProtocolError("M336K6 private path is not absolute canonical")
    normalized = str(path)
    return normalized.casefold() if isinstance(path, PureWindowsPath) else normalized
