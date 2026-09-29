"""Fail-closed branch authority for M-33.6k disposable rehearsals."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_identity import (
    build_m336k_identity_bundle_for_profile,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfileRegistry,
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)

_HASH = re.compile(r"[0-9a-f]{64}")
_SHA = re.compile(r"[0-9a-f]{40}")
_BRANCH = re.compile(r"[a-z0-9][a-z0-9._/-]*")
_AUTHORITY_ERROR = "M336K9 route branch authority changed"

M336K13_BRANCH_AUTHORITY_MUTATION_CASES = (
    "exact-profile-wrong-branch",
    "exact-branch-wrong-profile",
    "exact-profile-branch-wrong-mode",
    "exact-identity-forged-authorization-branch",
    "rehashed-profile-branch-canonical-registry-unchanged",
    "rehashed-changed-registry",
    "branch-prefix-only",
    "branch-suffix",
    "branch-case",
    "branch-double-slash",
    "branch-trailing-slash",
    "branch-encoded-separator",
    "branch-whitespace",
    "unknown-profile-relabelled-rehearsal",
    "historical-profile-relabelled-rehearsal",
    "official-profile-relabelled-rehearsal",
    "branch-receipt-forged-pass",
    "early-gate-omitted",
    "early-gate-after-output-creation",
    "early-gate-after-q-like-commit",
    "typed-request-branch-changed-after-preflight",
    "typed-authorization-branch-differs-from-preflight",
    "q-like-commit-before-branch-parity-proof",
    "profileless-fallback-with-registered-profile",
    "caller-supplied-expected-branch",
    "caller-supplied-profile-bypasses-registry",
    "registry-lookup-omitted",
    "case-insensitive-branch-equality",
    "prefix-wildcard-admission",
    "branch-mismatch-warning-only",
)


@dataclass(frozen=True)
class M336K13BranchAuthorityDecision:
    namespace: str
    profile_id: str
    profile_hash: str
    profile_status: str
    registry_hash: str
    official_admission_only: bool
    expected_branch_ref: str
    actual_branch_ref: str
    branch_exact_match: bool
    namespace_prefix_match: bool
    mode_status_match: bool
    historical_profile_occurrence_count: int
    unknown_profile_occurrence_count: int


@dataclass(frozen=True)
class M336K13RehearsalBranchAuthorityReceipt:
    schema_version: int
    contract_role: str
    execution_scope: str
    namespace: str
    profile_id: str
    profile_hash: str
    profile_status: str
    registry_hash: str
    official_admission_only: bool
    expected_branch_ref_hash: str
    actual_branch_ref_hash: str
    branch_exact_match: bool
    namespace_prefix_match: bool
    mode_status_match: bool
    historical_profile_occurrence_count: int
    unknown_profile_occurrence_count: int
    authority_predicate_version: str
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_REHEARSAL_BRANCH_AUTHORITY_RECEIPT"
    PREDICATE_VERSION: ClassVar[str] = "m336k13.branch-authority.v1"

    def _body(self) -> dict[str, Any]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "receipt_hash"
        }

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        profile_bound = bool(self.profile_id)
        registry = m336k_official_profile_registry()
        profile_binding_valid = False
        if profile_bound:
            try:
                profile = registry.profile(self.profile_id)
            except M336K2ProtocolError:
                profile_binding_valid = False
            else:
                profile_binding_valid = (
                    self.profile_hash == profile.profile_hash
                    and self.profile_status == profile.profile_status.value
                    and self.expected_branch_ref_hash
                    == bytes_hash(profile.authorization_branch_ref.encode("utf-8"))
                )
        else:
            expected_prefix = f"refs/heads/disposable/{self.namespace}-"
            profile_binding_valid = (
                not self.profile_hash
                and not self.profile_status
                and self.expected_branch_ref_hash
                == bytes_hash(expected_prefix.encode("utf-8"))
            )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope != "REHEARSAL"
            or not self.namespace
            or type(self.official_admission_only) is not bool
            or self.official_admission_only
            or self.registry_hash != registry.registry_hash
            or not profile_binding_valid
            or _HASH.fullmatch(self.registry_hash) is None
            or _HASH.fullmatch(self.expected_branch_ref_hash) is None
            or _HASH.fullmatch(self.actual_branch_ref_hash) is None
            or type(self.branch_exact_match) is not bool
            or type(self.namespace_prefix_match) is not bool
            or type(self.mode_status_match) is not bool
            or not self.namespace_prefix_match
            or not self.mode_status_match
            or self.historical_profile_occurrence_count != 0
            or self.unknown_profile_occurrence_count != 0
            or self.authority_predicate_version != self.PREDICATE_VERSION
            or self.status != "PASS"
            or profile_bound
            and (
                _HASH.fullmatch(self.profile_hash) is None
                or self.profile_status
                != M336KOfficialRouteProfileStatus.REHEARSAL_ONLY.value
                or not self.branch_exact_match
                or self.expected_branch_ref_hash != self.actual_branch_ref_hash
            )
            or not profile_bound
            and self.branch_exact_match
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 branch authority receipt is invalid")

    @classmethod
    def build(cls, decision: M336K13BranchAuthorityDecision) -> Self:
        if decision.official_admission_only:
            raise M336K2ProtocolError("M336K13 rehearsal receipt scope changed")
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": "REHEARSAL",
            "namespace": decision.namespace,
            "profile_id": decision.profile_id,
            "profile_hash": decision.profile_hash,
            "profile_status": decision.profile_status,
            "registry_hash": decision.registry_hash,
            "official_admission_only": decision.official_admission_only,
            "expected_branch_ref_hash": bytes_hash(
                decision.expected_branch_ref.encode("utf-8")
            ),
            "actual_branch_ref_hash": bytes_hash(
                decision.actual_branch_ref.encode("utf-8")
            ),
            "branch_exact_match": decision.branch_exact_match,
            "namespace_prefix_match": decision.namespace_prefix_match,
            "mode_status_match": decision.mode_status_match,
            "historical_profile_occurrence_count": (
                decision.historical_profile_occurrence_count
            ),
            "unknown_profile_occurrence_count": (
                decision.unknown_profile_occurrence_count
            ),
            "authority_predicate_version": cls.PREDICATE_VERSION,
            "status": "PASS",
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != {
            field.name for field in fields(cls)
        }:
            raise M336K2ProtocolError("M336K13 branch authority receipt fields changed")
        result = cls(**value)
        result.verify()
        return result


def verify_m336k_rehearsal_branch_authority(
    *,
    namespace: str,
    disposable_branch: str,
    official_admission_only: bool,
    profile_id: str | None,
    registry: M336KOfficialRouteProfileRegistry | None = None,
) -> M336K13BranchAuthorityDecision:
    """Verify one canonical branch/profile/mode relation without side effects."""

    canonical_registry = m336k_official_profile_registry()
    supplied_registry = registry or canonical_registry
    try:
        supplied_registry.verify()
    except (AttributeError, M336K2ProtocolError) as error:
        raise M336K2ProtocolError(_AUTHORITY_ERROR) from error
    if (
        supplied_registry.registry_hash != canonical_registry.registry_hash
        or supplied_registry.canonical_object() != canonical_registry.canonical_object()
        or type(namespace) is not str
        or not namespace
        or type(disposable_branch) is not str
        or _BRANCH.fullmatch(disposable_branch) is None
        or "//" in disposable_branch
        or ".." in disposable_branch
        or "@{" in disposable_branch
        or disposable_branch.endswith(("/", ".lock"))
        or type(official_admission_only) is not bool
    ):
        raise M336K2ProtocolError(_AUTHORITY_ERROR)

    actual_branch_ref = f"refs/heads/{disposable_branch}"
    namespace_prefix = f"disposable/{namespace}-"
    namespace_prefix_match = disposable_branch.startswith(namespace_prefix)
    if profile_id is None:
        if official_admission_only or not namespace_prefix_match:
            raise M336K2ProtocolError(_AUTHORITY_ERROR)
        return M336K13BranchAuthorityDecision(
            namespace=namespace,
            profile_id="",
            profile_hash="",
            profile_status="",
            registry_hash=canonical_registry.registry_hash,
            official_admission_only=False,
            expected_branch_ref=f"refs/heads/{namespace_prefix}",
            actual_branch_ref=actual_branch_ref,
            branch_exact_match=False,
            namespace_prefix_match=True,
            mode_status_match=True,
            historical_profile_occurrence_count=0,
            unknown_profile_occurrence_count=0,
        )

    if type(profile_id) is not str or not profile_id:
        raise M336K2ProtocolError(_AUTHORITY_ERROR)
    try:
        profile = canonical_registry.profile(profile_id)
    except M336K2ProtocolError as error:
        raise M336K2ProtocolError(_AUTHORITY_ERROR) from error
    expected_status = (
        M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
        if official_admission_only
        else M336KOfficialRouteProfileStatus.REHEARSAL_ONLY
    )
    mode_status_match = profile.profile_status is expected_status
    branch_exact_match = actual_branch_ref == profile.authorization_branch_ref
    profile_namespace_match = profile.route_version.startswith(f"{namespace}.")
    historical = int(
        profile.profile_status is M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
    )
    if (
        historical
        or not mode_status_match
        or not branch_exact_match
        or not profile_namespace_match
    ):
        raise M336K2ProtocolError(_AUTHORITY_ERROR)
    return M336K13BranchAuthorityDecision(
        namespace=namespace,
        profile_id=profile.profile_id,
        profile_hash=profile.profile_hash,
        profile_status=profile.profile_status.value,
        registry_hash=canonical_registry.registry_hash,
        official_admission_only=official_admission_only,
        expected_branch_ref=profile.authorization_branch_ref,
        actual_branch_ref=actual_branch_ref,
        branch_exact_match=True,
        namespace_prefix_match=namespace_prefix_match,
        mode_status_match=True,
        historical_profile_occurrence_count=0,
        unknown_profile_occurrence_count=0,
    )


def build_m336k13_pre_reservation_authorization_projection(
    *,
    exact_implementation_tip: str,
    disposable_label: str,
    namespace: str,
    disposable_branch: str,
    profile_id: str,
) -> dict[str, Any]:
    """Run the real profile-bound authorization verifier using role placeholders."""

    if (
        _SHA.fullmatch(exact_implementation_tip) is None
        or not disposable_label
        or not profile_id
    ):
        raise M336K2ProtocolError("M336K13 authorization projection input changed")
    decision = verify_m336k_rehearsal_branch_authority(
        namespace=namespace,
        disposable_branch=disposable_branch,
        official_admission_only=False,
        profile_id=profile_id,
    )
    from ai_brain.stage3.acquisition.m336k9_authorization import (
        build_m336k9_final_authorization,
    )

    def placeholder(role: str) -> str:
        return content_hash(
            {
                "contract_role": "M336K13_PRE_RESERVATION_PLACEHOLDER",
                "semantic_role": role,
                "disposable_label": disposable_label,
            }
        )

    route_registry_hash = placeholder("route_registry")
    route_manifest_hash = placeholder("route_manifest")
    acquisition_policy_hash = placeholder("acquisition_policy")
    selector_policy_hash = placeholder("selector_policy")
    evaluator_policy_hash = placeholder("evaluator_policy")
    bundle = build_m336k_identity_bundle_for_profile(
        profile_id=profile_id,
        route_registry_hash=route_registry_hash,
        route_manifest_hash=route_manifest_hash,
        acquisition_policy_hash=acquisition_policy_hash,
        selector_policy_hash=selector_policy_hash,
        evaluator_policy_hash=evaluator_policy_hash,
    )
    hashes = {
        role: placeholder(role)
        for role in (
            "candidate_pool",
            "archive_policy",
            "candidate_terminal_policy",
            "global_continuation_policy",
            "schema_registry",
            "readiness",
            "executable_dependency_manifest",
            "python_environment_manifest",
            "python_startup_policy",
            "bootstrap_source",
            "windows_launcher_source",
            "karina_launcher",
            "sanitized_environment",
            "startup_receipt_schema",
            "resource_budget",
            "storage_reservation_receipt",
            "resource_monitor",
            "cleanup_policy",
            "recovery_policy",
            "authority_statement",
            "disclosure_registry_manifest",
        )
    }
    authorization = build_m336k9_final_authorization(
        bundle=bundle,
        official_profile_id=profile_id,
        exact_implementation_tip=exact_implementation_tip,
        exact_q30_sha="0" * 40,
        branch_ref=decision.actual_branch_ref,
        candidate_pool_hash=hashes["candidate_pool"],
        acquisition_policy_hash=acquisition_policy_hash,
        archive_policy_hash=hashes["archive_policy"],
        candidate_terminal_policy_hash=hashes["candidate_terminal_policy"],
        global_continuation_policy_hash=hashes["global_continuation_policy"],
        route_manifest_hash=route_manifest_hash,
        route_registry_hash=route_registry_hash,
        schema_registry_hash=hashes["schema_registry"],
        readiness_hash=hashes["readiness"],
        executable_dependency_manifest_hash=hashes["executable_dependency_manifest"],
        python_environment_manifest_hash=hashes["python_environment_manifest"],
        python_startup_policy_hash=hashes["python_startup_policy"],
        bootstrap_source_hash=hashes["bootstrap_source"],
        windows_launcher_source_hash=hashes["windows_launcher_source"],
        karina_launcher_hash=hashes["karina_launcher"],
        sanitized_environment_hash=hashes["sanitized_environment"],
        startup_receipt_schema_hash=hashes["startup_receipt_schema"],
        resource_budget_hash=hashes["resource_budget"],
        storage_reservation_receipt_hash=hashes["storage_reservation_receipt"],
        resource_monitor_hash=hashes["resource_monitor"],
        cleanup_policy_hash=hashes["cleanup_policy"],
        recovery_policy_hash=hashes["recovery_policy"],
        authority_statement_hash=hashes["authority_statement"],
        disclosure_registry_manifest_hash=hashes["disclosure_registry_manifest"],
        selector_policy_hash=selector_policy_hash,
        evaluator_policy_hash=evaluator_policy_hash,
        allowed_network_hosts=("projection.invalid",),
        minimum_candidate_families=80,
        minimum_organizations=64,
        maximum_candidates_per_organization=2,
        acquisition_reservation_limit=1,
        selector_reservation_limit=1,
        evaluator_reservation_limit=1,
        candidate_retry_limit=0,
        candidate_replacement_limit=0,
        pre_freeze_source_body_bytes=0,
    )
    authorization.verify(bundle)
    body = {
        "schema_version": 1,
        "contract_role": "M336K13_PRE_RESERVATION_AUTHORIZATION_PROJECTION",
        "execution_scope": "REHEARSAL",
        "exact_implementation_tip": exact_implementation_tip,
        "disposable_label": disposable_label,
        "namespace": namespace,
        "profile_id": profile_id,
        "profile_hash": decision.profile_hash,
        "registry_hash": decision.registry_hash,
        "expected_branch_ref_hash": bytes_hash(
            decision.expected_branch_ref.encode("utf-8")
        ),
        "actual_branch_ref_hash": bytes_hash(
            decision.actual_branch_ref.encode("utf-8")
        ),
        "branch_exact_match": decision.branch_exact_match,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "authorization_hash": authorization.authorization_hash,
        "placeholder_component_count": len(hashes),
        "base_predicate_failure_count": 0,
        "bundle_mismatch_count": 0,
        "status": "PASS",
    }
    return {**body, "report_hash": content_hash(body)}
