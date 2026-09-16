"""Profile-bound final authorization for the M-33.6k.9 recovery route."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Self

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_authorization import M336K5FinalAuthorization
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K5AcquisitionRunId,
    M336K5EvaluatorRunId,
    M336K5ExecutionMode,
    M336K5ProtocolRunId,
    M336K5RouteIdentityBundle,
    M336K5RouteVersion,
    M336K5SelectorRunId,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k10_binding import (
    M336K10_PROFILE_ID,
    M336K11_PROFILE_ID,
    M336K12_PROFILE_ID,
    M336K10NetworkAuthorityManifest,
    M336K10OfficialAcquisitionPolicy,
    M336K10OfficialCandidatePoolBinding,
    M336K10ProviderConfiguration,
)


@dataclass(frozen=True)
class M336K9FinalAuthorization(M336K5FinalAuthorization):
    official_profile_id: str
    official_profile_hash: str
    official_profile_registry_hash: str

    def _body(self) -> dict[str, Any]:
        return {
            **super()._body(),
            "official_profile_id": self.official_profile_id,
            "official_profile_hash": self.official_profile_hash,
            "official_profile_registry_hash": self.official_profile_registry_hash,
        }

    def verify(self, bundle: M336K5RouteIdentityBundle | None = None) -> None:
        super().verify(bundle)
        registry = m336k_official_profile_registry()
        profile = registry.profile(self.official_profile_id)
        authorization_identity_tuple = (
            self.route_version_typed.value,
            self.protocol_run_id_typed.value,
            self.acquisition_run_id_typed.value,
            self.selector_run_id_typed.value,
            self.evaluator_run_id_typed.value,
            self.execution_mode_typed.value,
        )
        if (
            profile.profile_hash != self.official_profile_hash
            or registry.registry_hash != self.official_profile_registry_hash
            or profile.identity_tuple != authorization_identity_tuple
            or bundle is not None
            and profile.identity_tuple
            != (
                bundle.route_version.value,
                bundle.protocol_run_id.value,
                bundle.acquisition_run_id.value,
                bundle.selector_run_id.value,
                bundle.evaluator_run_id.value,
                bundle.execution_mode.value,
            )
        ):
            raise M336K2ProtocolError("M336K9 authorization profile binding changed")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K9 authorization fields changed")
        result = cls(
            **{
                **value,
                "route_version_typed": M336K5RouteVersion.from_dict(
                    value["route_version_typed"]
                ),
                "protocol_run_id_typed": M336K5ProtocolRunId.from_dict(
                    value["protocol_run_id_typed"]
                ),
                "acquisition_run_id_typed": M336K5AcquisitionRunId.from_dict(
                    value["acquisition_run_id_typed"]
                ),
                "selector_run_id_typed": M336K5SelectorRunId.from_dict(
                    value["selector_run_id_typed"]
                ),
                "evaluator_run_id_typed": M336K5EvaluatorRunId.from_dict(
                    value["evaluator_run_id_typed"]
                ),
                "execution_mode_typed": M336K5ExecutionMode.from_dict(
                    value["execution_mode_typed"]
                ),
                "allowed_network_hosts": tuple(value["allowed_network_hosts"]),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K10FinalAuthorization(M336K9FinalAuthorization):
    """Final authority built from the same official acquisition objects."""

    official_candidate_pool_binding_hash: str
    network_authority_manifest_hash: str
    official_acquisition_policy_hash: str
    pool_semantic_hash: str
    pool_bytes_hash: str
    derived_host_set_hash: str
    provider_configuration_hash: str
    acquisition_binding_receipt_hash: str

    def _body(self) -> dict[str, Any]:
        return {
            **super()._body(),
            "official_candidate_pool_binding_hash": (
                self.official_candidate_pool_binding_hash
            ),
            "network_authority_manifest_hash": self.network_authority_manifest_hash,
            "official_acquisition_policy_hash": (self.official_acquisition_policy_hash),
            "pool_semantic_hash": self.pool_semantic_hash,
            "pool_bytes_hash": self.pool_bytes_hash,
            "derived_host_set_hash": self.derived_host_set_hash,
            "provider_configuration_hash": self.provider_configuration_hash,
            "acquisition_binding_receipt_hash": (self.acquisition_binding_receipt_hash),
        }

    def verify(self, bundle: M336K5RouteIdentityBundle | None = None) -> None:
        super().verify(bundle)
        profile = m336k_official_profile_registry().profile(self.official_profile_id)
        hashes = (
            self.official_candidate_pool_binding_hash,
            self.network_authority_manifest_hash,
            self.official_acquisition_policy_hash,
            self.pool_semantic_hash,
            self.pool_bytes_hash,
            self.derived_host_set_hash,
            self.provider_configuration_hash,
            self.acquisition_binding_receipt_hash,
        )
        if (
            self.official_profile_id
            not in {M336K10_PROFILE_ID, M336K11_PROFILE_ID, M336K12_PROFILE_ID}
            or self.candidate_pool_hash != self.pool_semantic_hash
            or self.acquisition_policy_hash != self.official_acquisition_policy_hash
            or self.acquisition_run_id != profile.acquisition_run_id
            or self.selector_run_id != profile.selector_run_id
            or self.evaluator_run_id != profile.evaluator_run_id
            or any(
                type(value) is not str
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in hashes
            )
        ):
            raise M336K2ProtocolError("M336K10 authorization binding changed")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K10 authorization fields changed")
        result = cls(
            **{
                **value,
                "route_version_typed": M336K5RouteVersion.from_dict(
                    value["route_version_typed"]
                ),
                "protocol_run_id_typed": M336K5ProtocolRunId.from_dict(
                    value["protocol_run_id_typed"]
                ),
                "acquisition_run_id_typed": M336K5AcquisitionRunId.from_dict(
                    value["acquisition_run_id_typed"]
                ),
                "selector_run_id_typed": M336K5SelectorRunId.from_dict(
                    value["selector_run_id_typed"]
                ),
                "evaluator_run_id_typed": M336K5EvaluatorRunId.from_dict(
                    value["evaluator_run_id_typed"]
                ),
                "execution_mode_typed": M336K5ExecutionMode.from_dict(
                    value["execution_mode_typed"]
                ),
                "allowed_network_hosts": tuple(value["allowed_network_hosts"]),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K11FinalAuthorization(M336K10FinalAuthorization):
    """V4 authority bound to one canonical controller executable closure."""

    official_controller_executable_binding_hash: str
    official_executable_binding_receipt_hash: str

    def _body(self) -> dict[str, Any]:
        return {
            **super()._body(),
            "official_controller_executable_binding_hash": (
                self.official_controller_executable_binding_hash
            ),
            "official_executable_binding_receipt_hash": (
                self.official_executable_binding_receipt_hash
            ),
        }

    def verify(self, bundle: M336K5RouteIdentityBundle | None = None) -> None:
        super().verify(bundle)
        if (
            self.official_profile_id != M336K11_PROFILE_ID
            or self.official_executable_binding_receipt_hash
            != self.official_controller_executable_binding_hash
            or any(
                type(value) is not str
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in (
                    self.official_controller_executable_binding_hash,
                    self.official_executable_binding_receipt_hash,
                )
            )
        ):
            raise M336K2ProtocolError("M336K11 authorization binding changed")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K11 authorization fields changed")
        result = cls(
            **{
                **value,
                "route_version_typed": M336K5RouteVersion.from_dict(
                    value["route_version_typed"]
                ),
                "protocol_run_id_typed": M336K5ProtocolRunId.from_dict(
                    value["protocol_run_id_typed"]
                ),
                "acquisition_run_id_typed": M336K5AcquisitionRunId.from_dict(
                    value["acquisition_run_id_typed"]
                ),
                "selector_run_id_typed": M336K5SelectorRunId.from_dict(
                    value["selector_run_id_typed"]
                ),
                "evaluator_run_id_typed": M336K5EvaluatorRunId.from_dict(
                    value["evaluator_run_id_typed"]
                ),
                "execution_mode_typed": M336K5ExecutionMode.from_dict(
                    value["execution_mode_typed"]
                ),
                "allowed_network_hosts": tuple(value["allowed_network_hosts"]),
            }
        )
        result.verify()
        return result


@dataclass(frozen=True)
class M336K12FinalAuthorization(M336K11FinalAuthorization):
    """V5 authority bound to the admitted native-stage plan and parity proof."""

    native_stage_plan_binding_hash: str
    producer_consumer_parity_receipt_hash: str
    native_execution_capsule_receipt_hash: str

    def _body(self) -> dict[str, Any]:
        return {
            **super()._body(),
            "native_stage_plan_binding_hash": self.native_stage_plan_binding_hash,
            "producer_consumer_parity_receipt_hash": (
                self.producer_consumer_parity_receipt_hash
            ),
            "native_execution_capsule_receipt_hash": (
                self.native_execution_capsule_receipt_hash
            ),
        }

    def verify(self, bundle: M336K5RouteIdentityBundle | None = None) -> None:
        # M336K11 verifies the same executable and acquisition closure but has a
        # historical profile predicate, so call its acquisition parent directly.
        M336K10FinalAuthorization.verify(self, bundle)
        hashes = (
            self.official_controller_executable_binding_hash,
            self.official_executable_binding_receipt_hash,
            self.native_stage_plan_binding_hash,
            self.producer_consumer_parity_receipt_hash,
            self.native_execution_capsule_receipt_hash,
        )
        if (
            self.official_profile_id != M336K12_PROFILE_ID
            or self.official_executable_binding_receipt_hash
            != self.official_controller_executable_binding_hash
            or any(
                type(value) is not str
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in hashes
            )
        ):
            raise M336K2ProtocolError("M336K12 authorization binding changed")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K12 authorization fields changed")
        result = cls(
            **{
                **value,
                "route_version_typed": M336K5RouteVersion.from_dict(
                    value["route_version_typed"]
                ),
                "protocol_run_id_typed": M336K5ProtocolRunId.from_dict(
                    value["protocol_run_id_typed"]
                ),
                "acquisition_run_id_typed": M336K5AcquisitionRunId.from_dict(
                    value["acquisition_run_id_typed"]
                ),
                "selector_run_id_typed": M336K5SelectorRunId.from_dict(
                    value["selector_run_id_typed"]
                ),
                "evaluator_run_id_typed": M336K5EvaluatorRunId.from_dict(
                    value["evaluator_run_id_typed"]
                ),
                "execution_mode_typed": M336K5ExecutionMode.from_dict(
                    value["execution_mode_typed"]
                ),
                "allowed_network_hosts": tuple(value["allowed_network_hosts"]),
            }
        )
        result.verify()
        return result


def m336k_current_final_authorization_from_dict(
    value: dict[str, Any],
) -> M336K5FinalAuthorization:
    """Read both historical K5 authorization and profile-bound K9 authority."""

    if "native_stage_plan_binding_hash" in value:
        return M336K12FinalAuthorization.from_dict(value)
    if "official_controller_executable_binding_hash" in value:
        return M336K11FinalAuthorization.from_dict(value)
    if "official_candidate_pool_binding_hash" in value:
        return M336K10FinalAuthorization.from_dict(value)
    if "official_profile_id" in value:
        return M336K9FinalAuthorization.from_dict(value)
    return M336K5FinalAuthorization.from_dict(value)


def build_m336k9_final_authorization(
    *,
    bundle: M336K5RouteIdentityBundle,
    official_profile_id: str,
    **values: Any,
) -> M336K9FinalAuthorization:
    registry = m336k_official_profile_registry()
    profile = registry.profile(official_profile_id)
    body = {
        "schema_version": 2,
        "contract_role": "M336K5_TYPED_FINAL_AUTHORIZATION_V2",
        "route_version_typed": bundle.route_version,
        "protocol_run_id_typed": bundle.protocol_run_id,
        "acquisition_run_id_typed": bundle.acquisition_run_id,
        "selector_run_id_typed": bundle.selector_run_id,
        "evaluator_run_id_typed": bundle.evaluator_run_id,
        "execution_mode_typed": bundle.execution_mode,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "official_profile_id": profile.profile_id,
        "official_profile_hash": profile.profile_hash,
        "official_profile_registry_hash": registry.registry_hash,
        **values,
    }
    temporary = M336K9FinalAuthorization(**body, authorization_hash="0" * 64)
    result = M336K9FinalAuthorization(
        **body, authorization_hash=content_hash(temporary._body())
    )
    result.verify(bundle)
    return result


def build_m336k10_final_authorization(
    *,
    bundle: M336K5RouteIdentityBundle,
    pool_binding: M336K10OfficialCandidatePoolBinding,
    network_authority: M336K10NetworkAuthorityManifest,
    acquisition_policy: M336K10OfficialAcquisitionPolicy,
    provider_configuration: M336K10ProviderConfiguration,
    acquisition_binding_receipt_hash: str,
    **values: Any,
) -> M336K10FinalAuthorization:
    """Build v3 authorization without accepting any legacy host/pool input."""

    pool_binding.verify()
    network_authority.verify()
    acquisition_policy.verify()
    provider_configuration.verify()
    registry = m336k_official_profile_registry()
    profile = registry.profile(
        str(values.get("official_profile_id", M336K10_PROFILE_ID))
    )
    if (
        bundle.acquisition_run_id.value != profile.acquisition_run_id
        or acquisition_policy.candidate_pool_hash != pool_binding.pool_semantic_hash
        or acquisition_policy.official_candidate_pool_binding_hash
        != pool_binding.binding_hash
        or acquisition_policy.network_authority_manifest_hash
        != network_authority.manifest_hash
        or acquisition_policy.allowed_network_hosts
        != network_authority.allowed_network_hosts
        or provider_configuration.official_candidate_pool_binding_hash
        != pool_binding.binding_hash
        or provider_configuration.network_authority_manifest_hash
        != network_authority.manifest_hash
    ):
        raise M336K2ProtocolError("M336K10 authorization inputs are inconsistent")
    body = {
        "schema_version": 2,
        "contract_role": "M336K5_TYPED_FINAL_AUTHORIZATION_V2",
        "route_version_typed": bundle.route_version,
        "protocol_run_id_typed": bundle.protocol_run_id,
        "acquisition_run_id_typed": bundle.acquisition_run_id,
        "selector_run_id_typed": bundle.selector_run_id,
        "evaluator_run_id_typed": bundle.evaluator_run_id,
        "execution_mode_typed": bundle.execution_mode,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "official_profile_id": profile.profile_id,
        "official_profile_hash": profile.profile_hash,
        "official_profile_registry_hash": registry.registry_hash,
        "candidate_pool_hash": pool_binding.pool_semantic_hash,
        "acquisition_policy_hash": acquisition_policy.acquisition_policy_hash,
        "allowed_network_hosts": network_authority.allowed_network_hosts,
        "official_candidate_pool_binding_hash": pool_binding.binding_hash,
        "network_authority_manifest_hash": network_authority.manifest_hash,
        "official_acquisition_policy_hash": acquisition_policy.acquisition_policy_hash,
        "pool_semantic_hash": pool_binding.pool_semantic_hash,
        "pool_bytes_hash": pool_binding.pool_bytes_hash,
        "derived_host_set_hash": network_authority.host_set_hash,
        "provider_configuration_hash": provider_configuration.configuration_hash,
        "acquisition_binding_receipt_hash": acquisition_binding_receipt_hash,
        **values,
    }
    temporary = M336K10FinalAuthorization(**body, authorization_hash="0" * 64)
    result = M336K10FinalAuthorization(
        **body, authorization_hash=content_hash(temporary._body())
    )
    result.verify(bundle)
    return result


def build_m336k11_final_authorization(
    *,
    official_controller_executable_binding_hash: str,
    **values: Any,
) -> M336K11FinalAuthorization:
    """Build v4 authority after the acquisition and executable commitments exist."""

    base = build_m336k10_final_authorization(**values)
    body = {
        **{
            field.name: getattr(base, field.name)
            for field in fields(type(base))
            if field.name != "authorization_hash"
        },
        "official_controller_executable_binding_hash": (
            official_controller_executable_binding_hash
        ),
        "official_executable_binding_receipt_hash": (
            official_controller_executable_binding_hash
        ),
    }
    temporary = M336K11FinalAuthorization(**body, authorization_hash="0" * 64)
    result = M336K11FinalAuthorization(
        **body, authorization_hash=content_hash(temporary._body())
    )
    result.verify(values.get("bundle"))
    return result


def build_m336k12_final_authorization(
    *,
    official_controller_executable_binding_hash: str,
    native_stage_plan_binding_hash: str,
    producer_consumer_parity_receipt_hash: str,
    native_execution_capsule_receipt_hash: str,
    **values: Any,
) -> M336K12FinalAuthorization:
    """Build v5 authority from one dispatch-bound executable closure."""

    base = build_m336k10_final_authorization(**values)
    body = {
        **{
            field.name: getattr(base, field.name)
            for field in fields(type(base))
            if field.name != "authorization_hash"
        },
        "official_controller_executable_binding_hash": (
            official_controller_executable_binding_hash
        ),
        "official_executable_binding_receipt_hash": (
            official_controller_executable_binding_hash
        ),
        "native_stage_plan_binding_hash": native_stage_plan_binding_hash,
        "producer_consumer_parity_receipt_hash": (
            producer_consumer_parity_receipt_hash
        ),
        "native_execution_capsule_receipt_hash": (
            native_execution_capsule_receipt_hash
        ),
    }
    temporary = M336K12FinalAuthorization(**body, authorization_hash="0" * 64)
    result = M336K12FinalAuthorization(
        **body, authorization_hash=content_hash(temporary._body())
    )
    result.verify(values.get("bundle"))
    return result
