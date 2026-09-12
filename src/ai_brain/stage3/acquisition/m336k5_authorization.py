"""Typed final authorization bound to the M-33.6k.5 route identity bundle."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Self

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K5AcquisitionRunId,
    M336K5EvaluatorRunId,
    M336K5ExecutionMode,
    M336K5ProtocolRunId,
    M336K5RouteIdentityBundle,
    M336K5RouteVersion,
    M336K5SelectorRunId,
)

_SHA = re.compile(r"[0-9a-f]{40}")
_HASH = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class M336K5FinalAuthorization:
    schema_version: int
    contract_role: str
    exact_implementation_tip: str
    exact_q30_sha: str
    branch_ref: str
    route_version_typed: M336K5RouteVersion
    protocol_run_id_typed: M336K5ProtocolRunId
    acquisition_run_id_typed: M336K5AcquisitionRunId
    selector_run_id_typed: M336K5SelectorRunId
    evaluator_run_id_typed: M336K5EvaluatorRunId
    execution_mode_typed: M336K5ExecutionMode
    route_identity_bundle_hash: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    archive_policy_hash: str
    candidate_terminal_policy_hash: str
    global_continuation_policy_hash: str
    route_manifest_hash: str
    route_registry_hash: str
    schema_registry_hash: str
    readiness_hash: str
    executable_dependency_manifest_hash: str
    python_environment_manifest_hash: str
    python_startup_policy_hash: str
    bootstrap_source_hash: str
    windows_launcher_source_hash: str
    karina_launcher_hash: str
    sanitized_environment_hash: str
    startup_receipt_schema_hash: str
    resource_budget_hash: str
    storage_reservation_receipt_hash: str
    resource_monitor_hash: str
    cleanup_policy_hash: str
    recovery_policy_hash: str
    authority_statement_hash: str
    disclosure_registry_manifest_hash: str
    selector_policy_hash: str
    evaluator_policy_hash: str
    allowed_network_hosts: tuple[str, ...]
    minimum_candidate_families: int
    minimum_organizations: int
    maximum_candidates_per_organization: int
    acquisition_reservation_limit: int
    selector_reservation_limit: int
    evaluator_reservation_limit: int
    candidate_retry_limit: int
    candidate_replacement_limit: int
    pre_freeze_source_body_bytes: int
    authorization_hash: str

    @property
    def exact_q28_sha(self) -> str:
        """Compatibility name used by the frozen M336K2 acquisition engine."""

        return self.exact_q30_sha

    @property
    def execution_mode(self) -> str:
        return self.execution_mode_typed.value

    @property
    def acquisition_run_id(self) -> str:
        return self.acquisition_run_id_typed.value

    @property
    def protocol_run_id(self) -> str:
        return self.protocol_run_id_typed.value

    @property
    def selector_run_id(self) -> str:
        return self.selector_run_id_typed.value

    @property
    def evaluator_run_id(self) -> str:
        return self.evaluator_run_id_typed.value

    def _body(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "contract_role": self.contract_role,
            "exact_implementation_tip": self.exact_implementation_tip,
            "exact_q30_sha": self.exact_q30_sha,
            "branch_ref": self.branch_ref,
            "route_version_typed": self.route_version_typed.canonical_object(),
            "protocol_run_id_typed": self.protocol_run_id_typed.canonical_object(),
            "acquisition_run_id_typed": self.acquisition_run_id_typed.canonical_object(),
            "selector_run_id_typed": self.selector_run_id_typed.canonical_object(),
            "evaluator_run_id_typed": self.evaluator_run_id_typed.canonical_object(),
            "execution_mode_typed": self.execution_mode_typed.canonical_object(),
            "route_identity_bundle_hash": self.route_identity_bundle_hash,
            "candidate_pool_hash": self.candidate_pool_hash,
            "acquisition_policy_hash": self.acquisition_policy_hash,
            "archive_policy_hash": self.archive_policy_hash,
            "candidate_terminal_policy_hash": self.candidate_terminal_policy_hash,
            "global_continuation_policy_hash": self.global_continuation_policy_hash,
            "route_manifest_hash": self.route_manifest_hash,
            "route_registry_hash": self.route_registry_hash,
            "schema_registry_hash": self.schema_registry_hash,
            "readiness_hash": self.readiness_hash,
            "executable_dependency_manifest_hash": self.executable_dependency_manifest_hash,
            "python_environment_manifest_hash": self.python_environment_manifest_hash,
            "python_startup_policy_hash": self.python_startup_policy_hash,
            "bootstrap_source_hash": self.bootstrap_source_hash,
            "windows_launcher_source_hash": self.windows_launcher_source_hash,
            "karina_launcher_hash": self.karina_launcher_hash,
            "sanitized_environment_hash": self.sanitized_environment_hash,
            "startup_receipt_schema_hash": self.startup_receipt_schema_hash,
            "resource_budget_hash": self.resource_budget_hash,
            "storage_reservation_receipt_hash": self.storage_reservation_receipt_hash,
            "resource_monitor_hash": self.resource_monitor_hash,
            "cleanup_policy_hash": self.cleanup_policy_hash,
            "recovery_policy_hash": self.recovery_policy_hash,
            "authority_statement_hash": self.authority_statement_hash,
            "disclosure_registry_manifest_hash": self.disclosure_registry_manifest_hash,
            "selector_policy_hash": self.selector_policy_hash,
            "evaluator_policy_hash": self.evaluator_policy_hash,
            "allowed_network_hosts": self.allowed_network_hosts,
            "minimum_candidate_families": self.minimum_candidate_families,
            "minimum_organizations": self.minimum_organizations,
            "maximum_candidates_per_organization": self.maximum_candidates_per_organization,
            "acquisition_reservation_limit": self.acquisition_reservation_limit,
            "selector_reservation_limit": self.selector_reservation_limit,
            "evaluator_reservation_limit": self.evaluator_reservation_limit,
            "candidate_retry_limit": self.candidate_retry_limit,
            "candidate_replacement_limit": self.candidate_replacement_limit,
            "pre_freeze_source_body_bytes": self.pre_freeze_source_body_bytes,
        }

    def canonical_object(self) -> dict:
        return {**self._body(), "authorization_hash": self.authorization_hash}

    def verify(self, bundle: M336K5RouteIdentityBundle | None = None) -> None:
        hashes = tuple(
            value for name, value in self._body().items() if name.endswith("_hash")
        ) + (self.authorization_hash,)
        official = self.protocol_run_id_typed.value == "m336k5.final-java.outcome-a.v1"
        branch_valid = (
            self.branch_ref == "refs/heads/exp/stage3-m336k5-hermetic-python-final-v14"
            if official
            else self.branch_ref.startswith("refs/heads/disposable/m336k5-")
        )
        if (
            self.schema_version != 2
            or self.contract_role != "M336K5_TYPED_FINAL_AUTHORIZATION_V2"
            or _SHA.fullmatch(self.exact_implementation_tip) is None
            or _SHA.fullmatch(self.exact_q30_sha) is None
            or not branch_valid
            or any(_HASH.fullmatch(value) is None for value in hashes)
            or tuple(sorted(set(self.allowed_network_hosts)))
            != self.allowed_network_hosts
            or not self.allowed_network_hosts
            or self.minimum_candidate_families < 80
            or self.minimum_organizations < 64
            or self.maximum_candidates_per_organization > 2
            or (
                self.acquisition_reservation_limit,
                self.selector_reservation_limit,
                self.evaluator_reservation_limit,
            )
            != (1, 1, 1)
            or self.candidate_retry_limit != 0
            or self.candidate_replacement_limit != 0
            or self.pre_freeze_source_body_bytes != 0
            or content_hash(self._body()) != self.authorization_hash
        ):
            raise M336K2ProtocolError("M336K5 typed final authorization is invalid")
        if bundle is not None and (
            self.route_version_typed != bundle.route_version
            or self.protocol_run_id_typed != bundle.protocol_run_id
            or self.acquisition_run_id_typed != bundle.acquisition_run_id
            or self.selector_run_id_typed != bundle.selector_run_id
            or self.evaluator_run_id_typed != bundle.evaluator_run_id
            or self.execution_mode_typed != bundle.execution_mode
            or self.route_identity_bundle_hash != bundle.bundle_hash
            or self.route_registry_hash != bundle.route_registry_hash
            or self.route_manifest_hash != bundle.route_manifest_hash
            or self.acquisition_policy_hash != bundle.acquisition_policy_hash
            or self.selector_policy_hash != bundle.selector_policy_hash
            or self.evaluator_policy_hash != bundle.evaluator_policy_hash
        ):
            raise M336K2ProtocolError("M336K5 authorization/identity bundle mismatch")

    @classmethod
    def from_dict(cls, value: dict) -> Self:
        expected = set(cls.__dataclass_fields__)
        if type(value) is not dict or set(value) != expected:
            raise M336K2ProtocolError("M336K5 authorization fields changed")
        result = cls(
            **{
                **value,
                "route_version_typed": M336K5RouteVersion.from_dict(
                    value.get("route_version_typed")
                ),
                "protocol_run_id_typed": M336K5ProtocolRunId.from_dict(
                    value.get("protocol_run_id_typed")
                ),
                "acquisition_run_id_typed": M336K5AcquisitionRunId.from_dict(
                    value.get("acquisition_run_id_typed")
                ),
                "selector_run_id_typed": M336K5SelectorRunId.from_dict(
                    value.get("selector_run_id_typed")
                ),
                "evaluator_run_id_typed": M336K5EvaluatorRunId.from_dict(
                    value.get("evaluator_run_id_typed")
                ),
                "execution_mode_typed": M336K5ExecutionMode.from_dict(
                    value.get("execution_mode_typed")
                ),
                "allowed_network_hosts": tuple(value.get("allowed_network_hosts", ())),
            }
        )
        result.verify()
        return result


def build_m336k5_final_authorization(
    *, bundle: M336K5RouteIdentityBundle, **values
) -> M336K5FinalAuthorization:
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
        **values,
    }
    temporary = M336K5FinalAuthorization(**body, authorization_hash="0" * 64)
    result = M336K5FinalAuthorization(
        **body, authorization_hash=content_hash(temporary._body())
    )
    result.verify(bundle)
    return result
