"""Canonical typed freeze-readiness authority for M-33.6k.13.

The seal is deliberately narrower than the surrounding qualification evidence:
it contains only values which the ROLE_V6 freeze materializer must admit.  The
source-body count has one authority and is always derived from the verified
official acquisition static-readiness receipt.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfile,
    M336KOfficialRouteProfileRegistry,
    M336KOfficialRouteProfileStatus,
)

M336K13_READINESS_STATUS = (
    "READY_FOR_IMMUTABLE_FINAL_CONTROLLER_PLAN_BOUND_EXECUTION_V13"
)
M336K13_READINESS_BRANCH = "exp/stage3-m336k13-final-controller-plan-binding-v23"
M336K13_READINESS_BRANCH_REF = f"refs/heads/{M336K13_READINESS_BRANCH}"
M336K13_ACTIVE_PROFILE_ID = "m336k8-final-v6"
M336K13_QUALIFICATION_LABEL = "Q38T"

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _is_hash(value: object) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def _is_sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _exact_int(value: object, expected: int) -> bool:
    return type(value) is int and value == expected


@dataclass(frozen=True)
class M336K13VerifiedReceipt:
    """A source receipt whose semantic hash was verified before derivation."""

    value: dict[str, Any]
    hash_field: str
    semantic_hash: str

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
        *,
        hash_field: str = "receipt_hash",
        expected_role: str | None = None,
        require_pass: bool = True,
    ) -> Self:
        if type(value) is not dict or type(hash_field) is not str or not hash_field:
            raise M336K2ProtocolError("M336K13 source receipt fields changed")
        body = dict(value)
        claimed = body.pop(hash_field, None)
        if not _is_hash(claimed) or content_hash(body) != claimed:
            raise M336K2ProtocolError("M336K13 source receipt semantic hash changed")
        if expected_role is not None and value.get("contract_role") != expected_role:
            raise M336K2ProtocolError("M336K13 source receipt role changed")
        if require_pass and value.get("status") != "PASS":
            raise M336K2ProtocolError("M336K13 source receipt is not PASS")
        return cls(value=dict(value), hash_field=hash_field, semantic_hash=claimed)

    def field(self, name: str) -> Any:
        if name not in self.value:
            raise M336K2ProtocolError(f"M336K13 source receipt omitted {name}")
        return self.value[name]


@dataclass(frozen=True)
class M336K13FreezeReadinessSeal:
    schema_version: int
    contract_role: str
    qualification_label: str
    exact_implementation_tip: str
    branch_ref: str
    status: str
    active_official_profile_id: str
    active_official_profile_hash: str
    active_profile_registry_hash: str
    official_one_shot_counter_count: int
    official_ledger_count: int
    official_route_event_count: int
    official_source_request_count: int
    new_final_source_body_bytes: int
    official_candidate_body_count: int
    source_leak_count: int
    private_artifact_count: int
    raw_private_path_count: int
    official_vault_state: str
    final_request_state: str
    post_freeze_validation_receipt_state: str
    reservation_release_receipt_state: str
    active_generation_count: int
    preserved_superseded_generation_count: int
    preserved_reservation_count: int
    current_storage_reservation_receipt_hash: str
    official_acquisition_static_readiness_hash: str
    official_unspent_state_hash: str
    leak_report_hash: str
    generation_resource_gate_hash: str
    evidence_binding_manifest_hash: str
    readiness_hash: str

    ROLE: ClassVar[str] = "M336K13_OFFICIAL_FREEZE_READINESS_V1"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("readiness_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "readiness_hash": self.readiness_hash}

    def verify(self) -> None:
        integer_expectations = {
            "schema_version": 1,
            "official_one_shot_counter_count": 0,
            "official_ledger_count": 0,
            "official_route_event_count": 0,
            "official_source_request_count": 0,
            "new_final_source_body_bytes": 0,
            "official_candidate_body_count": 0,
            "source_leak_count": 0,
            "private_artifact_count": 0,
            "raw_private_path_count": 0,
            "active_generation_count": 1,
            "preserved_superseded_generation_count": 2,
            "preserved_reservation_count": 5,
        }
        hashes = (
            self.active_official_profile_hash,
            self.active_profile_registry_hash,
            self.current_storage_reservation_receipt_hash,
            self.official_acquisition_static_readiness_hash,
            self.official_unspent_state_hash,
            self.leak_report_hash,
            self.generation_resource_gate_hash,
            self.evidence_binding_manifest_hash,
            self.readiness_hash,
        )
        if (
            any(
                not _exact_int(getattr(self, name), expected)
                for name, expected in integer_expectations.items()
            )
            or self.contract_role != self.ROLE
            or self.qualification_label != M336K13_QUALIFICATION_LABEL
            or not _is_sha(self.exact_implementation_tip)
            or self.branch_ref != M336K13_READINESS_BRANCH_REF
            or self.status != M336K13_READINESS_STATUS
            or self.active_official_profile_id != M336K13_ACTIVE_PROFILE_ID
            or any(not _is_hash(value) for value in hashes)
            or self.official_vault_state != "ABSENT"
            or self.final_request_state != "ABSENT"
            or self.post_freeze_validation_receipt_state != "ABSENT"
            or self.reservation_release_receipt_state != "ABSENT"
            or self.readiness_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 freeze readiness is invalid")

    def verify_for_materialization(
        self,
        *,
        exact_implementation_tip: str,
        expected_status: str,
        expected_branch: str,
    ) -> None:
        self.verify()
        if (
            self.exact_implementation_tip != exact_implementation_tip
            or self.status != expected_status
            or self.branch_ref != f"refs/heads/{expected_branch}"
        ):
            raise M336K2ProtocolError(
                "M336K13 freeze readiness does not match materialization"
            )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K13 freeze readiness fields changed")
        try:
            result = cls(**value)
        except TypeError as error:
            raise M336K2ProtocolError(
                "M336K13 freeze readiness fields changed"
            ) from error
        result.verify()
        return result


def _require_int(receipt: M336K13VerifiedReceipt, name: str) -> int:
    value = receipt.field(name)
    if type(value) is not int:
        raise M336K2ProtocolError(f"M336K13 source receipt {name} is not an integer")
    return value


def _require_state(receipt: M336K13VerifiedReceipt, name: str) -> str:
    value = receipt.field(name)
    if type(value) is not str:
        raise M336K2ProtocolError(f"M336K13 source receipt {name} is not a state")
    return value


def _bind_source_tip(receipt: M336K13VerifiedReceipt, exact_tip: str) -> None:
    for field_name in ("exact_implementation_tip", "exact_source_sha"):
        if field_name in receipt.value and receipt.value[field_name] != exact_tip:
            raise M336K2ProtocolError("M336K13 source receipt implementation changed")


def build_m336k13_freeze_readiness(
    *,
    active_profile: M336KOfficialRouteProfile,
    profile_registry: M336KOfficialRouteProfileRegistry,
    official_acquisition_static_readiness: M336K13VerifiedReceipt,
    official_unspent_state: M336K13VerifiedReceipt,
    leak_report: M336K13VerifiedReceipt,
    current_storage_reservation: M336K13VerifiedReceipt,
    pre_resource_gate: M336K13VerifiedReceipt,
    post_resource_gate: M336K13VerifiedReceipt,
    generation_supersession: M336K13VerifiedReceipt,
    evidence_binding_manifest: M336K13VerifiedReceipt,
    exact_implementation_tip: str,
    qualification_label: str,
) -> M336K13FreezeReadinessSeal:
    """Derive one current seal from verified, independently hashed evidence."""

    active_profile.verify()
    profile_registry.verify()
    registered = profile_registry.profile(active_profile.profile_id)
    if (
        not _is_sha(exact_implementation_tip)
        or qualification_label != M336K13_QUALIFICATION_LABEL
        or active_profile.profile_id != M336K13_ACTIVE_PROFILE_ID
        or active_profile.profile_status
        is not M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
        or active_profile.profile_hash != registered.profile_hash
        or active_profile.authorization_branch_ref != M336K13_READINESS_BRANCH_REF
    ):
        raise M336K2ProtocolError("M336K13 readiness profile authority changed")

    receipts = (
        official_acquisition_static_readiness,
        official_unspent_state,
        leak_report,
        current_storage_reservation,
        pre_resource_gate,
        post_resource_gate,
        generation_supersession,
        evidence_binding_manifest,
    )
    if any(type(receipt) is not M336K13VerifiedReceipt for receipt in receipts):
        raise M336K2ProtocolError("M336K13 readiness source is not verified")
    for receipt in receipts:
        _bind_source_tip(receipt, exact_implementation_tip)

    acquisition_requests = _require_int(
        official_acquisition_static_readiness, "source_request_count"
    )
    acquisition_body_bytes = _require_int(
        official_acquisition_static_readiness, "source_body_byte_count"
    )
    unspent_requests = _require_int(official_unspent_state, "source_request_count")
    unspent_body_bytes = _require_int(official_unspent_state, "source_body_byte_count")
    unspent_candidate_bodies = _require_int(
        official_unspent_state, "candidate_body_count"
    )
    leak_body_bytes = _require_int(leak_report, "source_body_byte_count")
    leak_candidate_bodies = _require_int(leak_report, "candidate_body_count")
    values_required_zero = (
        acquisition_requests,
        acquisition_body_bytes,
        unspent_requests,
        unspent_body_bytes,
        unspent_candidate_bodies,
        leak_body_bytes,
        leak_candidate_bodies,
        _require_int(official_unspent_state, "official_one_shot_counter_count"),
        _require_int(official_unspent_state, "official_ledger_count"),
        _require_int(official_unspent_state, "official_route_event_count"),
        _require_int(leak_report, "source_leak_count"),
        _require_int(leak_report, "private_artifact_count"),
        _require_int(leak_report, "raw_private_path_count"),
    )
    if any(value != 0 for value in values_required_zero):
        raise M336K2ProtocolError("M336K13 readiness source is spent")
    if not (
        acquisition_requests == unspent_requests
        and acquisition_body_bytes == unspent_body_bytes == leak_body_bytes
        and unspent_candidate_bodies == leak_candidate_bodies
    ):
        raise M336K2ProtocolError("M336K13 readiness source counters diverged")

    vault_state = _require_state(official_unspent_state, "official_vault_state")
    final_request_state = _require_state(official_unspent_state, "final_request_state")
    validation_state = _require_state(
        official_unspent_state, "post_freeze_validation_receipt_state"
    )
    release_state = _require_state(
        official_unspent_state, "reservation_release_receipt_state"
    )
    if (vault_state, final_request_state, validation_state, release_state) != (
        "ABSENT",
        "ABSENT",
        "ABSENT",
        "ABSENT",
    ):
        raise M336K2ProtocolError("M336K13 readiness future output exists")

    active_generation_count = _require_int(
        generation_supersession, "active_generation_count"
    )
    preserved_generation_count = _require_int(
        generation_supersession, "preserved_superseded_generation_count"
    )
    preserved_reservation_count = _require_int(
        post_resource_gate, "total_preserved_reservation_count"
    )
    current_reservation_hash = current_storage_reservation.semantic_hash
    if (
        active_generation_count != 1
        or preserved_generation_count != 2
        or preserved_reservation_count != 5
        or post_resource_gate.field("generation3_reservation_receipt_hash")
        != current_reservation_hash
        or post_resource_gate.field("generation3_reservation_released") is not False
        or post_resource_gate.field("generation3_reservation_reused") is not False
        or _require_int(post_resource_gate, "total_released_reservation_count") != 0
    ):
        raise M336K2ProtocolError("M336K13 generation readiness changed")

    body = {
        "schema_version": 1,
        "contract_role": M336K13FreezeReadinessSeal.ROLE,
        "qualification_label": qualification_label,
        "exact_implementation_tip": exact_implementation_tip,
        "branch_ref": M336K13_READINESS_BRANCH_REF,
        "status": M336K13_READINESS_STATUS,
        "active_official_profile_id": active_profile.profile_id,
        "active_official_profile_hash": active_profile.profile_hash,
        "active_profile_registry_hash": profile_registry.registry_hash,
        "official_one_shot_counter_count": 0,
        "official_ledger_count": 0,
        "official_route_event_count": 0,
        "official_source_request_count": acquisition_requests,
        "new_final_source_body_bytes": acquisition_body_bytes,
        "official_candidate_body_count": unspent_candidate_bodies,
        "source_leak_count": 0,
        "private_artifact_count": 0,
        "raw_private_path_count": 0,
        "official_vault_state": vault_state,
        "final_request_state": final_request_state,
        "post_freeze_validation_receipt_state": validation_state,
        "reservation_release_receipt_state": release_state,
        "active_generation_count": active_generation_count,
        "preserved_superseded_generation_count": preserved_generation_count,
        "preserved_reservation_count": preserved_reservation_count,
        "current_storage_reservation_receipt_hash": current_reservation_hash,
        "official_acquisition_static_readiness_hash": (
            official_acquisition_static_readiness.semantic_hash
        ),
        "official_unspent_state_hash": official_unspent_state.semantic_hash,
        "leak_report_hash": leak_report.semantic_hash,
        "generation_resource_gate_hash": content_hash(
            (pre_resource_gate.semantic_hash, post_resource_gate.semantic_hash)
        ),
        "evidence_binding_manifest_hash": evidence_binding_manifest.semantic_hash,
    }
    result = M336K13FreezeReadinessSeal(**body, readiness_hash=content_hash(body))
    result.verify()
    return result


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError(
            "M336K13 freeze readiness source evidence is unavailable"
        ) from error
    if type(value) is not dict:
        raise M336K2ProtocolError(
            "M336K13 freeze readiness source evidence is not an object"
        )
    return value


def verify_m336k13_freeze_readiness_sources(
    readiness_path: Path,
    readiness: M336K13FreezeReadinessSeal,
) -> None:
    """Rebind a seal to its committed canonical source receipts."""

    readiness.verify()
    root = readiness_path.resolve(strict=True).parent
    profile = M336KOfficialRouteProfile.from_dict(
        _load_object(root / "active_official_profile.json")
    )
    registry = M336KOfficialRouteProfileRegistry.from_dict(
        _load_object(root / "official_profile_registry.json")
    )
    acquisition = M336K13VerifiedReceipt.from_dict(
        _load_object(root / "official_acquisition_static_readiness.json")
    )
    unspent = M336K13VerifiedReceipt.from_dict(
        _load_object(root / "official_unspent_state.json")
    )
    leak = M336K13VerifiedReceipt.from_dict(_load_object(root / "leak_report.json"))
    reservation = M336K13VerifiedReceipt.from_dict(
        _load_object(root / "generation3_storage_reservation.json")
    )
    pre_gate = M336K13VerifiedReceipt.from_dict(
        _load_object(root / "generation3_pre_resource_gate.json")
    )
    post_gate = M336K13VerifiedReceipt.from_dict(
        _load_object(root / "generation3_post_resource_gate.json")
    )
    evidence_binding = M336K13VerifiedReceipt.from_dict(
        _load_object(root / "evidence_binding_manifest.json")
    )

    if (
        profile.profile_id != readiness.active_official_profile_id
        or profile.profile_hash != readiness.active_official_profile_hash
        or registry.profile(profile.profile_id).profile_hash != profile.profile_hash
        or registry.registry_hash != readiness.active_profile_registry_hash
        or acquisition.semantic_hash
        != readiness.official_acquisition_static_readiness_hash
        or unspent.semantic_hash != readiness.official_unspent_state_hash
        or leak.semantic_hash != readiness.leak_report_hash
        or reservation.semantic_hash
        != readiness.current_storage_reservation_receipt_hash
        or content_hash((pre_gate.semantic_hash, post_gate.semantic_hash))
        != readiness.generation_resource_gate_hash
        or evidence_binding.semantic_hash != readiness.evidence_binding_manifest_hash
        or _require_int(acquisition, "source_request_count")
        != readiness.official_source_request_count
        or _require_int(acquisition, "source_body_byte_count")
        != readiness.new_final_source_body_bytes
        or _require_int(unspent, "source_request_count")
        != readiness.official_source_request_count
        or _require_int(unspent, "source_body_byte_count")
        != readiness.new_final_source_body_bytes
        or _require_int(unspent, "candidate_body_count")
        != readiness.official_candidate_body_count
        or _require_int(leak, "source_body_byte_count")
        != readiness.new_final_source_body_bytes
        or _require_int(leak, "candidate_body_count")
        != readiness.official_candidate_body_count
        or _require_int(leak, "source_leak_count") != readiness.source_leak_count
        or _require_int(leak, "private_artifact_count")
        != readiness.private_artifact_count
        or _require_int(leak, "raw_private_path_count")
        != readiness.raw_private_path_count
        or _require_int(unspent, "official_one_shot_counter_count")
        != readiness.official_one_shot_counter_count
        or _require_int(unspent, "official_ledger_count")
        != readiness.official_ledger_count
        or _require_int(unspent, "official_route_event_count")
        != readiness.official_route_event_count
        or _require_state(unspent, "official_vault_state")
        != readiness.official_vault_state
        or _require_state(unspent, "final_request_state")
        != readiness.final_request_state
        or _require_state(unspent, "post_freeze_validation_receipt_state")
        != readiness.post_freeze_validation_receipt_state
        or _require_state(unspent, "reservation_release_receipt_state")
        != readiness.reservation_release_receipt_state
    ):
        raise M336K2ProtocolError("M336K13 freeze readiness source evidence changed")
