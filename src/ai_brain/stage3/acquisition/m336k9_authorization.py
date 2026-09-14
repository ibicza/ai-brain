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
