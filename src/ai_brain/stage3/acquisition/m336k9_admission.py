"""Shared, side-effect-free controller admission and profile coverage gates."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Self

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
from ai_brain.stage3.acquisition.m336k9_authorization import (
    M336K10FinalAuthorization,
    M336K11FinalAuthorization,
    build_m336k9_final_authorization,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfileRegistry,
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)

M336K9_CONTROLLER_VERSION = "m336k11-controller.v4"
_HASH = re.compile(r"[0-9a-f]{64}")
_CONTROLLER_VERSION = re.compile(r"m336k([0-9]+)-controller\.v([0-9]+)")
M336K9_CONTROLLER_ADMISSION_CONTRACT = {
    "schema_version": 1,
    "contract_role": "M336K9_CONTROLLER_ADMISSION_CONTRACT",
    "verifier": "verify_m336k_controller_admission",
    "inputs": (
        "purpose",
        "route_identity_bundle",
        "expected_official_profile_id",
        "expected_profile_hash",
        "current_registry",
        "final_authorization",
        "freeze_manifest",
        "official_acquisition_binding",
        "official_executable_binding",
    ),
    "required_identity_fields": (
        "route_version",
        "protocol_run_id",
        "acquisition_run_id",
        "selector_run_id",
        "evaluator_run_id",
        "execution_mode",
    ),
    "official_required_status": "CURRENT_ACTIVE",
    "disposable_required_status": "REHEARSAL_ONLY",
    "side_effect_count": 0,
    "status": "FROZEN",
}
M336K9_CONTROLLER_ADMISSION_CONTRACT_HASH = content_hash(
    M336K9_CONTROLLER_ADMISSION_CONTRACT
)
M336K9_CONTROLLER_ADMISSION_TESTED_PROFILE_IDS = (
    "m336k5-final-v1",
    "m336k6-final-v1",
    "m336k7-final-v1",
    "m336k8-final-v1",
    "m336k8-final-v2",
    "m336k8-final-v3",
    "m336k8-final-v4",
    "m336k8-rehearsal-v2",
)
M336K9_ADMISSION_MUTATION_CASES = (
    "historical-k8-v1-new-official",
    "active-k8-v4",
    "profile-absent",
    "route-from-another-profile",
    "protocol-from-another-profile",
    "acquisition-from-another-profile",
    "selector-from-another-profile",
    "evaluator-from-another-profile",
    "execution-mode-changed",
    "purpose-changed-after-validation",
    "profile-status-changed",
    "profile-hash-changed",
    "registry-hash-changed",
    "authorization-another-profile",
    "freeze-another-profile",
    "validate-admission-missing",
    "validate-admission-another-bundle",
    "controller-recomputation-differs",
    "second-controller-whitelist",
    "typed-values-differ-from-registry",
    "active-profile-missing-from-tests",
    "new-profile-omitted-by-controller",
    "disposable-bypasses-identity",
    "official-validated-as-disposable",
    "read-only-promoted-without-registry-hash",
    "mixed-v1-v2-tuple",
    "f33-v1-used-as-f34-authority",
)


@dataclass(frozen=True)
class M336KControllerAdmissionReceipt:
    schema_version: int
    contract_role: str
    purpose: str
    profile_id: str
    profile_status: str
    profile_hash: str
    registry_hash: str
    route_identity_bundle_hash: str
    authorization_hash: str
    freeze_hash: str
    official_acquisition_binding_receipt_hash: str | None
    official_executable_binding_receipt_hash: str | None
    execution_mode: str
    official_admission_result: str
    side_effect_count: int
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K_CONTROLLER_ADMISSION_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return {name: item for name, item in value.items() if item is not None}

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        hashes = (
            self.profile_hash,
            self.registry_hash,
            self.route_identity_bundle_hash,
            self.authorization_hash,
            self.freeze_hash,
            self.receipt_hash,
        )
        binding_hash_valid = (
            self.official_acquisition_binding_receipt_hash is None
            or type(self.official_acquisition_binding_receipt_hash) is str
            and _HASH.fullmatch(self.official_acquisition_binding_receipt_hash)
            is not None
        )
        executable_hash_valid = (
            self.official_executable_binding_receipt_hash is None
            or type(self.official_executable_binding_receipt_hash) is str
            and _HASH.fullmatch(self.official_executable_binding_receipt_hash)
            is not None
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.purpose not in {"OFFICIAL", "DISPOSABLE"}
            or self.profile_status
            not in {item.value for item in M336KOfficialRouteProfileStatus}
            or self.execution_mode != "FINAL"
            or self.official_admission_result != "PASS"
            or self.side_effect_count != 0
            or not binding_hash_valid
            or not executable_hash_valid
            or any(
                type(value) is not str or _HASH.fullmatch(value) is None
                for value in hashes
            )
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K controller admission receipt is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        expected = {field.name for field in fields(cls)}
        optional = {
            "official_acquisition_binding_receipt_hash",
            "official_executable_binding_receipt_hash",
        }
        allowed = {
            expected,
            expected - {"official_acquisition_binding_receipt_hash"},
            expected - {"official_executable_binding_receipt_hash"},
            expected - optional,
        }
        if type(value) is not dict or set(value) not in allowed:
            raise M336K2ProtocolError("M336K controller admission fields changed")
        result = cls(
            **{
                "official_acquisition_binding_receipt_hash": None,
                "official_executable_binding_receipt_hash": None,
                **value,
            }
        )
        result.verify()
        return result


def verify_m336k_controller_admission(
    *,
    purpose: str,
    route_identity_bundle: M336K5RouteIdentityBundle,
    expected_official_profile_id: str,
    expected_profile_hash: str,
    current_registry: M336KOfficialRouteProfileRegistry,
    final_authorization: Any,
    freeze_manifest: Any,
    official_acquisition_binding: Any | None = None,
    official_executable_binding: Any | None = None,
) -> M336KControllerAdmissionReceipt:
    """Apply every controller identity predicate without producing side effects."""

    current_registry.verify()
    route_identity_bundle.verify()
    authorization_verifier = getattr(final_authorization, "verify", None)
    authorization_body = getattr(final_authorization, "_body", None)
    freeze_body = getattr(freeze_manifest, "_body", None)
    if (
        not callable(authorization_verifier)
        or not callable(authorization_body)
        or not callable(freeze_body)
    ):
        raise M336K2ProtocolError("M336K controller admission input is unverified")
    authorization_verifier(route_identity_bundle)
    profile = current_registry.profile(expected_official_profile_id)
    profile.verify()
    expected_status = {
        "OFFICIAL": M336KOfficialRouteProfileStatus.CURRENT_ACTIVE,
        "DISPOSABLE": M336KOfficialRouteProfileStatus.REHEARSAL_ONLY,
    }.get(purpose)
    identity_tuple = (
        route_identity_bundle.route_version.value,
        route_identity_bundle.protocol_run_id.value,
        route_identity_bundle.acquisition_run_id.value,
        route_identity_bundle.selector_run_id.value,
        route_identity_bundle.evaluator_run_id.value,
        route_identity_bundle.execution_mode.value,
    )
    authorization_hash = getattr(final_authorization, "authorization_hash", None)
    freeze_hash = getattr(freeze_manifest, "manifest_hash", None)
    binding_receipt_hash = getattr(official_acquisition_binding, "receipt_hash", None)
    binding_authorization_hash = getattr(
        official_acquisition_binding, "authorization_binding_hash", None
    )
    authorization_binding_hash = getattr(
        final_authorization, "acquisition_binding_receipt_hash", None
    )
    executable_receipt_hash = getattr(official_executable_binding, "receipt_hash", None)
    executable_binding_hash = getattr(
        official_executable_binding,
        "official_controller_executable_binding_hash",
        None,
    )
    current_controller = _CONTROLLER_VERSION.fullmatch(M336K9_CONTROLLER_VERSION)
    minimum_controller = _CONTROLLER_VERSION.fullmatch(
        profile.minimum_controller_version
    )
    executable_verifier = getattr(official_executable_binding, "verify", None)
    if official_executable_binding is not None and callable(executable_verifier):
        executable_verifier()
    if (
        expected_status is None
        or current_controller is None
        or minimum_controller is None
        or tuple(map(int, current_controller.groups()))
        < tuple(map(int, minimum_controller.groups()))
        or profile.profile_status is not expected_status
        or profile.profile_hash != expected_profile_hash
        or profile.identity_tuple != identity_tuple
        or current_registry.profile_for_identity_tuple(identity_tuple) != profile
        or route_identity_bundle.execution_mode.value != profile.execution_mode
        or getattr(final_authorization, "official_profile_id", None)
        != profile.profile_id
        or getattr(final_authorization, "official_profile_hash", None)
        != profile.profile_hash
        or getattr(final_authorization, "official_profile_registry_hash", None)
        != current_registry.registry_hash
        or getattr(final_authorization, "route_identity_bundle_hash", None)
        != route_identity_bundle.bundle_hash
        or getattr(final_authorization, "route_version_typed", None)
        != route_identity_bundle.route_version
        or getattr(final_authorization, "protocol_run_id_typed", None)
        != route_identity_bundle.protocol_run_id
        or getattr(final_authorization, "acquisition_run_id_typed", None)
        != route_identity_bundle.acquisition_run_id
        or getattr(final_authorization, "selector_run_id_typed", None)
        != route_identity_bundle.selector_run_id
        or getattr(final_authorization, "evaluator_run_id_typed", None)
        != route_identity_bundle.evaluator_run_id
        or getattr(final_authorization, "execution_mode_typed", None)
        != route_identity_bundle.execution_mode
        or getattr(freeze_manifest, "official_profile_id", None) != profile.profile_id
        or getattr(freeze_manifest, "official_profile_hash", None)
        != profile.profile_hash
        or getattr(freeze_manifest, "official_profile_registry_hash", None)
        != current_registry.registry_hash
        or getattr(freeze_manifest, "route_identity_bundle_hash", None)
        != route_identity_bundle.bundle_hash
        or getattr(freeze_manifest, "authorization_hash", None) != authorization_hash
        or type(authorization_hash) is not str
        or _HASH.fullmatch(authorization_hash) is None
        or authorization_hash != content_hash(authorization_body())
        or type(freeze_hash) is not str
        or _HASH.fullmatch(freeze_hash) is None
        or freeze_hash != content_hash(freeze_body())
        or profile.profile_id in {"m336k8-final-v3", "m336k8-final-v4"}
        and (
            official_acquisition_binding is None
            or type(binding_receipt_hash) is not str
            or _HASH.fullmatch(binding_receipt_hash) is None
            or binding_authorization_hash != authorization_binding_hash
            or getattr(
                freeze_manifest,
                "official_acquisition_binding_receipt_hash",
                None,
            )
            != binding_receipt_hash
        )
        or profile.profile_id == "m336k8-final-v4"
        and (
            official_executable_binding is None
            or not callable(getattr(official_executable_binding, "verify", None))
            or getattr(official_executable_binding, "status", None) != "PASS"
            or type(executable_receipt_hash) is not str
            or _HASH.fullmatch(executable_receipt_hash) is None
            or executable_binding_hash
            != getattr(
                final_authorization,
                "official_controller_executable_binding_hash",
                None,
            )
            or getattr(
                freeze_manifest,
                "official_executable_binding_receipt_hash",
                None,
            )
            != executable_receipt_hash
        )
    ):
        raise M336K2ProtocolError(
            "M336K controller admission rejected the route profile"
        )
    body = {
        "schema_version": 1,
        "contract_role": M336KControllerAdmissionReceipt.ROLE,
        "purpose": purpose,
        "profile_id": profile.profile_id,
        "profile_status": profile.profile_status.value,
        "profile_hash": profile.profile_hash,
        "registry_hash": current_registry.registry_hash,
        "route_identity_bundle_hash": route_identity_bundle.bundle_hash,
        "authorization_hash": authorization_hash,
        "freeze_hash": freeze_hash,
        "official_acquisition_binding_receipt_hash": binding_receipt_hash,
        "official_executable_binding_receipt_hash": executable_receipt_hash,
        "execution_mode": route_identity_bundle.execution_mode.value,
        "official_admission_result": "PASS",
        "side_effect_count": 0,
    }
    body = {name: value for name, value in body.items() if value is not None}
    receipt = M336KControllerAdmissionReceipt(
        **{
            "official_acquisition_binding_receipt_hash": None,
            "official_executable_binding_receipt_hash": None,
            **body,
        },
        receipt_hash=content_hash(body),
    )
    receipt.verify()
    return receipt


@dataclass(frozen=True)
class M336KOfficialProfileCoverageGate:
    schema_version: int
    contract_role: str
    official_profile_registry_hash: str
    registered_profile_count: int
    tested_profile_count: int
    untested_profile_count: int
    active_profile_count: int
    historical_read_only_profile_count: int
    rehearsal_only_profile_count: int
    historical_profiles_accepted_for_new_official_execution: int
    route_value_drift_count: int
    protocol_value_drift_count: int
    acquisition_value_drift_count: int
    selector_value_drift_count: int
    evaluator_value_drift_count: int
    independent_controller_whitelist_count: int
    controller_only_identity_predicate_count: int
    status: str
    gate_hash: str

    ROLE: ClassVar[str] = "M336K_OFFICIAL_PROFILE_COVERAGE_GATE"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("gate_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "gate_hash": self.gate_hash}

    def verify(self) -> None:
        counters = (
            self.untested_profile_count,
            self.historical_profiles_accepted_for_new_official_execution,
            self.route_value_drift_count,
            self.protocol_value_drift_count,
            self.acquisition_value_drift_count,
            self.selector_value_drift_count,
            self.evaluator_value_drift_count,
            self.independent_controller_whitelist_count,
            self.controller_only_identity_predicate_count,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.registered_profile_count != self.tested_profile_count
            or self.active_profile_count != 1
            or any(counters)
            or self.status != "PASS"
            or self.gate_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K official profile coverage gate failed")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K profile coverage fields changed")
        result = cls(**value)
        result.verify()
        return result


@dataclass(frozen=True)
class _CoverageFreeze:
    official_profile_id: str
    official_profile_hash: str
    official_profile_registry_hash: str
    route_identity_bundle_hash: str
    authorization_hash: str
    official_acquisition_binding_receipt_hash: str | None
    official_executable_binding_receipt_hash: str | None
    manifest_hash: str

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("manifest_hash")
        return value

    @classmethod
    def build(
        cls,
        *,
        profile_id: str,
        profile_hash: str,
        registry_hash: str,
        bundle_hash: str,
        authorization_hash: str,
        acquisition_binding_receipt_hash: str | None = None,
        executable_binding_receipt_hash: str | None = None,
    ) -> Self:
        body = {
            "official_profile_id": profile_id,
            "official_profile_hash": profile_hash,
            "official_profile_registry_hash": registry_hash,
            "route_identity_bundle_hash": bundle_hash,
            "authorization_hash": authorization_hash,
            "official_acquisition_binding_receipt_hash": (
                acquisition_binding_receipt_hash
            ),
            "official_executable_binding_receipt_hash": (
                executable_binding_receipt_hash
            ),
        }
        return cls(**body, manifest_hash=content_hash(body))


def _coverage_authorization(profile_id: str, bundle: M336K5RouteIdentityBundle) -> Any:
    profile = m336k_official_profile_registry().profile(profile_id)
    hashes = {
        name: content_hash((profile_id, name))
        for name in (
            "candidate_pool_hash",
            "acquisition_policy_hash",
            "archive_policy_hash",
            "candidate_terminal_policy_hash",
            "global_continuation_policy_hash",
            "route_manifest_hash",
            "route_registry_hash",
            "schema_registry_hash",
            "readiness_hash",
            "executable_dependency_manifest_hash",
            "python_environment_manifest_hash",
            "python_startup_policy_hash",
            "bootstrap_source_hash",
            "windows_launcher_source_hash",
            "karina_launcher_hash",
            "sanitized_environment_hash",
            "startup_receipt_schema_hash",
            "resource_budget_hash",
            "storage_reservation_receipt_hash",
            "resource_monitor_hash",
            "cleanup_policy_hash",
            "recovery_policy_hash",
            "authority_statement_hash",
            "disclosure_registry_manifest_hash",
            "selector_policy_hash",
            "evaluator_policy_hash",
        )
    }
    hashes.update(
        {
            "route_manifest_hash": bundle.route_manifest_hash,
            "route_registry_hash": bundle.route_registry_hash,
            "acquisition_policy_hash": bundle.acquisition_policy_hash,
            "selector_policy_hash": bundle.selector_policy_hash,
            "evaluator_policy_hash": bundle.evaluator_policy_hash,
        }
    )
    result = build_m336k9_final_authorization(
        bundle=bundle,
        official_profile_id=profile_id,
        exact_implementation_tip="1" * 40,
        exact_q30_sha="2" * 40,
        branch_ref=profile.authorization_branch_ref,
        allowed_network_hosts=("example.invalid",),
        minimum_candidate_families=80,
        minimum_organizations=64,
        maximum_candidates_per_organization=2,
        acquisition_reservation_limit=1,
        selector_reservation_limit=1,
        evaluator_reservation_limit=1,
        candidate_retry_limit=0,
        candidate_replacement_limit=0,
        pre_freeze_source_body_bytes=0,
        **hashes,
    )
    if profile_id not in {"m336k8-final-v3", "m336k8-final-v4"}:
        return result
    binding_commitment = content_hash((profile_id, "acquisition-binding"))
    body = {
        **{
            field.name: getattr(result, field.name)
            for field in fields(type(result))
            if field.name != "authorization_hash"
        },
        "official_candidate_pool_binding_hash": content_hash((profile_id, "pool")),
        "network_authority_manifest_hash": content_hash((profile_id, "network")),
        "official_acquisition_policy_hash": result.acquisition_policy_hash,
        "pool_semantic_hash": result.candidate_pool_hash,
        "pool_bytes_hash": content_hash((profile_id, "pool-bytes")),
        "derived_host_set_hash": content_hash((profile_id, "hosts")),
        "provider_configuration_hash": content_hash((profile_id, "provider")),
        "acquisition_binding_receipt_hash": binding_commitment,
    }
    authorization_type = M336K10FinalAuthorization
    if profile_id == "m336k8-final-v4":
        authorization_type = M336K11FinalAuthorization
        body.update(
            {
                "official_controller_executable_binding_hash": content_hash(
                    (profile_id, "executable-binding")
                ),
                "official_executable_binding_receipt_hash": content_hash(
                    (profile_id, "executable-binding")
                ),
            }
        )
    temporary = authorization_type(**body, authorization_hash="0" * 64)
    result_bound = authorization_type(
        **body, authorization_hash=content_hash(temporary._body())
    )
    result_bound.verify(bundle)
    return result_bound


@dataclass(frozen=True)
class _CoverageAcquisitionBinding:
    receipt_hash: str
    authorization_binding_hash: str


@dataclass(frozen=True)
class _CoverageExecutableBinding:
    receipt_hash: str
    official_controller_executable_binding_hash: str
    status: str = "PASS"

    def verify(self) -> None:
        if self.status != "PASS":
            raise M336K2ProtocolError("M336K11 coverage executable binding failed")


def run_m336k_official_profile_coverage_gate() -> M336KOfficialProfileCoverageGate:
    registry = m336k_official_profile_registry()
    tested = set(M336K9_CONTROLLER_ADMISSION_TESTED_PROFILE_IDS)
    registered = {profile.profile_id for profile in registry.profiles}
    historical_accepted = 0
    for profile in registry.profiles:
        bundle = M336K5RouteIdentityBundle.build(
            route_version=M336K5RouteVersion(profile.route_version),
            protocol_run_id=M336K5ProtocolRunId(profile.protocol_run_id),
            acquisition_run_id=M336K5AcquisitionRunId(profile.acquisition_run_id),
            selector_run_id=M336K5SelectorRunId(profile.selector_run_id),
            evaluator_run_id=M336K5EvaluatorRunId(profile.evaluator_run_id),
            execution_mode=M336K5ExecutionMode(profile.execution_mode),
            route_registry_hash=content_hash((profile.profile_id, "registry")),
            route_manifest_hash=content_hash((profile.profile_id, "manifest")),
            acquisition_policy_hash=content_hash((profile.profile_id, "acquisition")),
            selector_policy_hash=content_hash((profile.profile_id, "selector")),
            evaluator_policy_hash=content_hash((profile.profile_id, "evaluator")),
        )
        round_trip = M336K5RouteIdentityBundle.from_dict(bundle.canonical_object())
        if (
            round_trip != bundle
            or registry.profile_for_identity_tuple(profile.identity_tuple) != profile
        ):
            raise M336K2ProtocolError("M336K profile codec coverage changed")
        authorization = _coverage_authorization(profile.profile_id, bundle)
        acquisition_binding = None
        if profile.profile_id in {"m336k8-final-v3", "m336k8-final-v4"}:
            acquisition_binding = _CoverageAcquisitionBinding(
                receipt_hash=content_hash((profile.profile_id, "receipt")),
                authorization_binding_hash=(
                    authorization.acquisition_binding_receipt_hash
                ),
            )
        executable_binding = None
        if profile.profile_id == "m336k8-final-v4":
            executable_binding = _CoverageExecutableBinding(
                receipt_hash=content_hash((profile.profile_id, "executable-receipt")),
                official_controller_executable_binding_hash=(
                    authorization.official_controller_executable_binding_hash
                ),
            )
        freeze = _CoverageFreeze.build(
            profile_id=profile.profile_id,
            profile_hash=profile.profile_hash,
            registry_hash=registry.registry_hash,
            bundle_hash=bundle.bundle_hash,
            authorization_hash=authorization.authorization_hash,
            acquisition_binding_receipt_hash=(
                None
                if acquisition_binding is None
                else acquisition_binding.receipt_hash
            ),
            executable_binding_receipt_hash=(
                None if executable_binding is None else executable_binding.receipt_hash
            ),
        )
        purpose = (
            "DISPOSABLE"
            if profile.profile_status is M336KOfficialRouteProfileStatus.REHEARSAL_ONLY
            else "OFFICIAL"
        )
        try:
            verify_m336k_controller_admission(
                purpose=purpose,
                route_identity_bundle=bundle,
                expected_official_profile_id=profile.profile_id,
                expected_profile_hash=profile.profile_hash,
                current_registry=registry,
                final_authorization=authorization,
                freeze_manifest=freeze,
                official_acquisition_binding=acquisition_binding,
                official_executable_binding=executable_binding,
            )
        except M336K2ProtocolError:
            if (
                profile.profile_status
                is not M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
            ):
                raise
        else:
            if (
                profile.profile_status
                is M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
            ):
                historical_accepted += 1
    typed = {
        "route_version": M336K5RouteVersion.official_values,
        "protocol_run_id": M336K5ProtocolRunId.official_values,
        "acquisition_run_id": M336K5AcquisitionRunId.official_values,
        "selector_run_id": M336K5SelectorRunId.official_values,
        "evaluator_run_id": M336K5EvaluatorRunId.official_values,
    }
    drifts = {
        name: len(values.symmetric_difference(registry.official_values(name)))
        for name, values in typed.items()
    }
    controller = (
        Path(__file__).with_name("m336k5_controller.py").read_text(encoding="utf-8")
    )
    validator = (
        Path(__file__).with_name("m336k8_request.py").read_text(encoding="utf-8")
    )
    independent_whitelists = len(
        re.findall(
            r"protocol_run_id(?:_typed)?(?:\.value)?\s+(?:not\s+)?in\s*[({]", controller
        )
    )
    shared_call = "verify_m336k_controller_admission("
    controller_only_predicates = int(
        shared_call not in controller or shared_call not in validator
    )
    body = {
        "schema_version": 1,
        "contract_role": M336KOfficialProfileCoverageGate.ROLE,
        "official_profile_registry_hash": registry.registry_hash,
        "registered_profile_count": len(registered),
        "tested_profile_count": len(tested & registered),
        "untested_profile_count": len(registered - tested),
        "active_profile_count": sum(
            profile.profile_status is M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
            for profile in registry.profiles
        ),
        "historical_read_only_profile_count": sum(
            profile.profile_status
            is M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
            for profile in registry.profiles
        ),
        "rehearsal_only_profile_count": sum(
            profile.profile_status is M336KOfficialRouteProfileStatus.REHEARSAL_ONLY
            for profile in registry.profiles
        ),
        "historical_profiles_accepted_for_new_official_execution": historical_accepted,
        "route_value_drift_count": drifts["route_version"],
        "protocol_value_drift_count": drifts["protocol_run_id"],
        "acquisition_value_drift_count": drifts["acquisition_run_id"],
        "selector_value_drift_count": drifts["selector_run_id"],
        "evaluator_value_drift_count": drifts["evaluator_run_id"],
        "independent_controller_whitelist_count": independent_whitelists,
        "controller_only_identity_predicate_count": controller_only_predicates,
        "status": "PASS",
    }
    result = M336KOfficialProfileCoverageGate(**body, gate_hash=content_hash(body))
    result.verify()
    return result
