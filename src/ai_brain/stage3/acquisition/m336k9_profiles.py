"""Canonical official-route profile authority for M-33.6k recovery routes."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError


class M336KOfficialRouteProfileStatus(str, Enum):
    HISTORICAL_READ_ONLY = "HISTORICAL_READ_ONLY"
    CURRENT_ACTIVE = "CURRENT_ACTIVE"
    REHEARSAL_ONLY = "REHEARSAL_ONLY"


@dataclass(frozen=True)
class M336KOfficialRouteProfile:
    schema_version: int
    contract_role: str
    profile_id: str
    profile_status: M336KOfficialRouteProfileStatus
    route_version: str
    protocol_run_id: str
    acquisition_run_id: str
    selector_run_id: str
    evaluator_run_id: str
    execution_mode: str
    minimum_controller_version: str
    authorization_branch_ref: str
    profile_hash: str

    ROLE: ClassVar[str] = "M336K_OFFICIAL_ROUTE_PROFILE"

    @property
    def identity_tuple(self) -> tuple[str, ...]:
        return (
            self.route_version,
            self.protocol_run_id,
            self.acquisition_run_id,
            self.selector_run_id,
            self.evaluator_run_id,
            self.execution_mode,
        )

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "profile_id": self.profile_id,
            "profile_status": self.profile_status.value,
            "route_version": self.route_version,
            "protocol_run_id": self.protocol_run_id,
            "acquisition_run_id": self.acquisition_run_id,
            "selector_run_id": self.selector_run_id,
            "evaluator_run_id": self.evaluator_run_id,
            "execution_mode": self.execution_mode,
            "minimum_controller_version": self.minimum_controller_version,
            "authorization_branch_ref": self.authorization_branch_ref,
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "profile_hash": self.profile_hash}

    def verify(self) -> None:
        values = self.identity_tuple
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or not self.profile_id
            or type(self.profile_status) is not M336KOfficialRouteProfileStatus
            or any(type(value) is not str or not value for value in values)
            or self.execution_mode != "FINAL"
            or not self.minimum_controller_version
            or not self.authorization_branch_ref.startswith("refs/heads/")
            or self.profile_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K official route profile is invalid")

    @classmethod
    def build(
        cls,
        *,
        profile_id: str,
        profile_status: M336KOfficialRouteProfileStatus,
        route_version: str,
        protocol_run_id: str,
        acquisition_run_id: str,
        selector_run_id: str,
        evaluator_run_id: str,
        execution_mode: str,
        minimum_controller_version: str,
        authorization_branch_ref: str,
    ) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "profile_id": profile_id,
            "profile_status": profile_status,
            "route_version": route_version,
            "protocol_run_id": protocol_run_id,
            "acquisition_run_id": acquisition_run_id,
            "selector_run_id": selector_run_id,
            "evaluator_run_id": evaluator_run_id,
            "execution_mode": execution_mode,
            "minimum_controller_version": minimum_controller_version,
            "authorization_branch_ref": authorization_branch_ref,
        }
        temporary = cls(**body, profile_hash="0" * 64)
        result = cls(**body, profile_hash=content_hash(temporary._body()))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K official route profile fields changed")
        try:
            status = M336KOfficialRouteProfileStatus(value["profile_status"])
        except (KeyError, ValueError) as error:
            raise M336K2ProtocolError(
                "M336K official route profile status is invalid"
            ) from error
        result = cls(**{**value, "profile_status": status})
        result.verify()
        return result


@dataclass(frozen=True)
class M336KOfficialRouteProfileRegistry:
    schema_version: int
    contract_role: str
    profiles: tuple[M336KOfficialRouteProfile, ...]
    registry_hash: str

    ROLE: ClassVar[str] = "M336K_OFFICIAL_ROUTE_PROFILE_REGISTRY"

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "profiles": tuple(profile.canonical_object() for profile in self.profiles),
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "registry_hash": self.registry_hash}

    def verify(self) -> None:
        for profile in self.profiles:
            profile.verify()
        ids = tuple(profile.profile_id for profile in self.profiles)
        hashes = tuple(profile.profile_hash for profile in self.profiles)
        identities = tuple(profile.identity_tuple for profile in self.profiles)
        active = tuple(
            profile
            for profile in self.profiles
            if profile.profile_status is M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or not self.profiles
            or ids != tuple(sorted(ids))
            or len(set(ids)) != len(ids)
            or len(set(hashes)) != len(hashes)
            or len(set(identities)) != len(identities)
            or len(active) != 1
            or active[0].profile_id != "m336k8-final-v4"
            or self.registry_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError(
                "M336K official route profile registry is invalid"
            )

    def profile(self, profile_id: str) -> M336KOfficialRouteProfile:
        matches = tuple(item for item in self.profiles if item.profile_id == profile_id)
        if len(matches) != 1:
            raise M336K2ProtocolError("M336K official route profile is not registered")
        return matches[0]

    def profile_for_identity_tuple(
        self, identity_tuple: tuple[str, ...]
    ) -> M336KOfficialRouteProfile:
        matches = tuple(
            item for item in self.profiles if item.identity_tuple == identity_tuple
        )
        if len(matches) != 1:
            raise M336K2ProtocolError("M336K route identity tuple is not registered")
        return matches[0]

    def official_values(self, field_name: str) -> frozenset[str]:
        allowed = {
            "route_version",
            "protocol_run_id",
            "acquisition_run_id",
            "selector_run_id",
            "evaluator_run_id",
        }
        if field_name not in allowed:
            raise M336K2ProtocolError("M336K official identity field is invalid")
        return frozenset(
            getattr(profile, field_name)
            for profile in self.profiles
            if profile.profile_status
            is not M336KOfficialRouteProfileStatus.REHEARSAL_ONLY
        )

    @classmethod
    def build(cls, profiles: tuple[M336KOfficialRouteProfile, ...]) -> Self:
        ordered = tuple(sorted(profiles, key=lambda item: item.profile_id))
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "profiles": tuple(profile.canonical_object() for profile in ordered),
        }
        result = cls(
            schema_version=1,
            contract_role=cls.ROLE,
            profiles=ordered,
            registry_hash=content_hash(body),
        )
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if (
            type(value) is not dict
            or set(value) != {field.name for field in fields(cls)}
            or type(value.get("profiles")) is not list
        ):
            raise M336K2ProtocolError("M336K profile registry fields changed")
        result = cls(
            schema_version=value["schema_version"],
            contract_role=value["contract_role"],
            profiles=tuple(
                M336KOfficialRouteProfile.from_dict(item) for item in value["profiles"]
            ),
            registry_hash=value["registry_hash"],
        )
        result.verify()
        return result


def _profile(
    profile_id: str,
    status: M336KOfficialRouteProfileStatus,
    namespace: str,
    version: int,
    branch: str,
    *,
    rehearsal: bool = False,
) -> M336KOfficialRouteProfile:
    if rehearsal:
        route = f"{namespace}.candidate-isolated-java-disposable-route.v{version}"
        protocol = f"{namespace}.disposable.controller-admission.v{version}"
        acquisition = (
            f"{namespace}.disposable.controller-admission.acquisition.v{version}"
        )
        selector = f"{namespace}.disposable.controller-admission.selector.v{version}"
        evaluator = f"{namespace}.disposable.controller-admission.evaluator.v{version}"
    else:
        route = f"{namespace}.candidate-isolated-java-final-route.v{version}"
        protocol = f"{namespace}.final-java.outcome-a.v{version}"
        acquisition = f"{namespace}.final-java.global-acquisition.v{version}"
        selector = f"{namespace}.final-java.selector.v{version}"
        evaluator = f"{namespace}.final-java.evaluator.v{version}"
    return M336KOfficialRouteProfile.build(
        profile_id=profile_id,
        profile_status=status,
        route_version=route,
        protocol_run_id=protocol,
        acquisition_run_id=acquisition,
        selector_run_id=selector,
        evaluator_run_id=evaluator,
        execution_mode="FINAL",
        minimum_controller_version=(
            (
                "m336k11-controller.v4"
                if version == 4
                else "m336k10-controller.v3"
                if version == 3
                else "m336k9-controller.v2"
            )
            if namespace == "m336k8" and version in {2, 3, 4}
            else "m336k5-controller.v1"
        ),
        authorization_branch_ref=branch,
    )


M336K_OFFICIAL_PROFILE_REGISTRY = M336KOfficialRouteProfileRegistry.build(
    (
        _profile(
            "m336k5-final-v1",
            M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY,
            "m336k5",
            1,
            "refs/heads/exp/stage3-m336k5-hermetic-python-final-v14",
        ),
        _profile(
            "m336k6-final-v1",
            M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY,
            "m336k6",
            1,
            "refs/heads/exp/stage3-m336k6-persistent-capsule-final-v15",
        ),
        _profile(
            "m336k7-final-v1",
            M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY,
            "m336k7",
            1,
            "refs/heads/exp/stage3-m336k7-frozen-contract-final-v16",
        ),
        _profile(
            "m336k8-final-v1",
            M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY,
            "m336k8",
            1,
            "refs/heads/exp/stage3-m336k8-source-domain-final-v17",
        ),
        _profile(
            "m336k8-final-v2",
            M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY,
            "m336k8",
            2,
            "refs/heads/exp/stage3-m336k9-controller-admission-final-v18",
        ),
        _profile(
            "m336k8-final-v3",
            M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY,
            "m336k8",
            3,
            "refs/heads/exp/stage3-m336k10-official-acquisition-binding-v19",
        ),
        _profile(
            "m336k8-final-v4",
            M336KOfficialRouteProfileStatus.CURRENT_ACTIVE,
            "m336k8",
            4,
            "refs/heads/exp/stage3-m336k11-hermetic-executable-binding-v20",
        ),
        _profile(
            "m336k8-rehearsal-v2",
            M336KOfficialRouteProfileStatus.REHEARSAL_ONLY,
            "m336k8",
            2,
            "refs/heads/disposable/m336k8-profile-rehearsal-v2",
            rehearsal=True,
        ),
    )
)


def m336k_official_profile_registry() -> M336KOfficialRouteProfileRegistry:
    """Return the immutable process-wide canonical registry."""

    M336K_OFFICIAL_PROFILE_REGISTRY.verify()
    return M336K_OFFICIAL_PROFILE_REGISTRY


def m336k_profile_registry_from_dict(
    value: dict[str, Any],
) -> M336KOfficialRouteProfileRegistry:
    return M336KOfficialRouteProfileRegistry.from_dict(value)
