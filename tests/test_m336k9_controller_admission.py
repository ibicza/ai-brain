from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    verify_complete_freeze,
)
from ai_brain.stage3.acquisition.m336k2_stage import (
    _attestation as _stage_attestation,
)
from ai_brain.stage3.acquisition.m336k2_stage import _freeze as _stage_freeze
from ai_brain.stage3.acquisition.m336k5_controller import (
    run_m336k5_final_controller,
)
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K5AcquisitionRunId,
    M336K5EvaluatorRunId,
    M336K5ExecutionMode,
    M336K5ProtocolRunId,
    M336K5RouteIdentityBundle,
    M336K5RouteVersion,
    M336K5SelectorRunId,
    build_m336k_identity_bundle_for_profile,
)
from ai_brain.stage3.acquisition.m336k8_freeze import (
    M336K8FreezeManifest,
    M336K9CommittedFreezeAttestation,
)
from ai_brain.stage3.acquisition.m336k9_admission import (
    M336K9_ADMISSION_MUTATION_CASES,
    M336K9_CONTROLLER_ADMISSION_CONTRACT,
    M336K9_CONTROLLER_ADMISSION_CONTRACT_HASH,
    M336K9_CONTROLLER_ADMISSION_TESTED_PROFILE_IDS,
    M336KControllerAdmissionReceipt,
    run_m336k_official_profile_coverage_gate,
    verify_m336k_controller_admission,
)
from ai_brain.stage3.acquisition.m336k9_authorization import (
    M336K9FinalAuthorization,
    build_m336k9_final_authorization,
    m336k_current_final_authorization_from_dict,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfile,
    M336KOfficialRouteProfileRegistry,
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)


@dataclass(frozen=True)
class _Freeze:
    official_profile_id: str
    official_profile_hash: str
    official_profile_registry_hash: str
    route_identity_bundle_hash: str
    authorization_hash: str
    manifest_hash: str

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("manifest_hash")
        return value

    @classmethod
    def build(
        cls,
        profile: M336KOfficialRouteProfile,
        registry: M336KOfficialRouteProfileRegistry,
        bundle: M336K5RouteIdentityBundle,
        authorization: M336K9FinalAuthorization,
    ) -> _Freeze:
        body = {
            "official_profile_id": profile.profile_id,
            "official_profile_hash": profile.profile_hash,
            "official_profile_registry_hash": registry.registry_hash,
            "route_identity_bundle_hash": bundle.bundle_hash,
            "authorization_hash": authorization.authorization_hash,
        }
        return cls(**body, manifest_hash=content_hash(body))


class _EmptyLedger:
    def events(self) -> tuple[()]:
        return ()


def _hashes(label: str) -> dict[str, str]:
    return {
        name: content_hash((label, name))
        for name in (
            "route_registry_hash",
            "route_manifest_hash",
            "acquisition_policy_hash",
            "selector_policy_hash",
            "evaluator_policy_hash",
        )
    }


def _authorization(
    bundle: M336K5RouteIdentityBundle, profile_id: str
) -> M336K9FinalAuthorization:
    profile = m336k_official_profile_registry().profile(profile_id)
    bound_hashes = {
        name: content_hash((profile_id, name))
        for name in (
            "candidate_pool_hash",
            "archive_policy_hash",
            "candidate_terminal_policy_hash",
            "global_continuation_policy_hash",
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
        )
    }
    return build_m336k9_final_authorization(
        bundle=bundle,
        official_profile_id=profile_id,
        exact_implementation_tip="1" * 40,
        exact_q30_sha="2" * 40,
        branch_ref=profile.authorization_branch_ref,
        acquisition_policy_hash=bundle.acquisition_policy_hash,
        route_manifest_hash=bundle.route_manifest_hash,
        route_registry_hash=bundle.route_registry_hash,
        selector_policy_hash=bundle.selector_policy_hash,
        evaluator_policy_hash=bundle.evaluator_policy_hash,
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
        **bound_hashes,
    )


def _valid(
    profile_id: str = "m336k8-final-v2",
) -> tuple[
    M336KOfficialRouteProfileRegistry,
    M336KOfficialRouteProfile,
    M336K5RouteIdentityBundle,
    M336K9FinalAuthorization,
    _Freeze,
    str,
]:
    registry = m336k_official_profile_registry()
    profile = registry.profile(profile_id)
    bundle = build_m336k_identity_bundle_for_profile(profile_id, **_hashes(profile_id))
    authorization = _authorization(bundle, profile_id)
    freeze = _Freeze.build(profile, registry, bundle, authorization)
    purpose = (
        "DISPOSABLE"
        if profile.profile_status is M336KOfficialRouteProfileStatus.REHEARSAL_ONLY
        else "OFFICIAL"
    )
    return registry, profile, bundle, authorization, freeze, purpose


def _admit(
    state: tuple[
        M336KOfficialRouteProfileRegistry,
        M336KOfficialRouteProfile,
        M336K5RouteIdentityBundle,
        M336K9FinalAuthorization,
        _Freeze,
        str,
    ],
) -> M336KControllerAdmissionReceipt:
    registry, profile, bundle, authorization, freeze, purpose = state
    return verify_m336k_controller_admission(
        purpose=purpose,
        route_identity_bundle=bundle,
        expected_official_profile_id=profile.profile_id,
        expected_profile_hash=profile.profile_hash,
        current_registry=registry,
        final_authorization=authorization,
        freeze_manifest=freeze,
    )


def _mixed_bundle(
    base: M336K5RouteIdentityBundle,
    other: M336KOfficialRouteProfile,
    field: str,
) -> M336K5RouteIdentityBundle:
    values: dict[str, Any] = {
        "route_version": base.route_version,
        "protocol_run_id": base.protocol_run_id,
        "acquisition_run_id": base.acquisition_run_id,
        "selector_run_id": base.selector_run_id,
        "evaluator_run_id": base.evaluator_run_id,
        "execution_mode": base.execution_mode,
        "route_registry_hash": base.route_registry_hash,
        "route_manifest_hash": base.route_manifest_hash,
        "acquisition_policy_hash": base.acquisition_policy_hash,
        "selector_policy_hash": base.selector_policy_hash,
        "evaluator_policy_hash": base.evaluator_policy_hash,
    }
    codecs = {
        "route_version": M336K5RouteVersion,
        "protocol_run_id": M336K5ProtocolRunId,
        "acquisition_run_id": M336K5AcquisitionRunId,
        "selector_run_id": M336K5SelectorRunId,
        "evaluator_run_id": M336K5EvaluatorRunId,
        "execution_mode": M336K5ExecutionMode,
    }
    values[field] = codecs[field](getattr(other, field))
    return M336K5RouteIdentityBundle.build(**values)


def _controller(
    tmp_path: Path,
    *,
    bundle: M336K5RouteIdentityBundle,
    authorization: M336K9FinalAuthorization,
    freeze: _Freeze,
    purpose: str,
    admission: M336KControllerAdmissionReceipt | None,
) -> None:
    validated = SimpleNamespace(
        request=SimpleNamespace(purpose=purpose),
        bundle=bundle,
        authorization=authorization,
        freeze=freeze,
        receipt=SimpleNamespace(receipt_hash=content_hash("preledger")),
        controller_admission=admission,
    )
    run_m336k5_final_controller(
        validated=validated,
        ledger=_EmptyLedger(),
        preledger_guard=lambda: validated.receipt,
        worker=lambda _request: None,
        output=tmp_path / "must-not-exist.json",
    )


def _rehash_freeze(freeze: _Freeze, **changes: Any) -> _Freeze:
    temporary = replace(freeze, **changes, manifest_hash="0" * 64)
    return replace(temporary, manifest_hash=content_hash(temporary._body()))


def test_m336k9_stage_routes_v2_freeze_to_current_verifier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value = {
        "schema_version": 1,
        "contract_role": M336K8FreezeManifest.ROLE_V2,
        "implementation_tip": "1" * 40,
        "exact_qualification_sha": "2" * 40,
        "exact_freeze_sha": "3" * 40,
        "committed_freeze_tree": "4" * 40,
        **{
            name: content_hash(name)
            for name in (
                "readiness_hash",
                "authorization_hash",
                "route_hash",
                "route_identity_bundle_hash",
                "canonical_request_builder_hash",
                "post_freeze_input_bundle_hash",
                "source_identity_receipt_hash",
                "controller_startup_binding_hash",
                "persistent_capsule_source_binding_hash",
                "bridge_surface_manifest_hash",
                "source_domain_compatibility_receipt_hash",
                "freeze_assembly_plan_hash",
                "freeze_assembly_receipt_hash",
                "compatibility_gate_v2_hash",
                "official_profile_hash",
                "official_profile_registry_hash",
                "profile_coverage_gate_hash",
                "controller_admission_contract_hash",
            )
        },
        "components": [],
        "self_reference_safe_exclusions": [],
        "prospective_freeze_tree_hash": content_hash("prospective"),
        "manifest_hash": content_hash("manifest"),
        "official_profile_id": "m336k8-final-v2",
    }
    path = tmp_path / "freeze_manifest.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    freeze = _stage_freeze(path)
    observed: list[tuple[Path, bool]] = []
    monkeypatch.setattr(
        M336K8FreezeManifest,
        "verify",
        lambda self, root, *, allow_prospective=False: observed.append(
            (root, allow_prospective)
        ),
    )

    verify_complete_freeze(tmp_path, freeze, allow_prospective_f28=True)

    assert isinstance(freeze, M336K8FreezeManifest)
    assert freeze.contract_role == M336K8FreezeManifest.ROLE_V2
    assert observed == [(tmp_path.resolve(), True)]


def test_m336k9_stage_loads_v2_freeze_attestation(tmp_path: Path) -> None:
    body = {
        "schema_version": 1,
        "contract_role": M336K9CommittedFreezeAttestation.ROLE,
        "exact_freeze_sha": "1" * 40,
        "exact_qualification_parent": "2" * 40,
        "committed_tree_hash": "3" * 40,
        "prospective_freeze_tree_hash": content_hash("prospective"),
        "prospective_tree_matches": True,
        **{
            name: content_hash(name)
            for name in (
                "route_identity_bundle_hash",
                "authorization_hash",
                "route_hash",
                "post_freeze_input_bundle_hash",
                "source_identity_receipt_hash",
                "freeze_assembly_plan_hash",
                "producer_origin_map_hash",
                "official_profile_hash",
                "official_profile_registry_hash",
                "profile_coverage_gate_hash",
                "controller_admission_contract_hash",
            )
        },
        "implementation_change_count": 0,
        "merge_count": 0,
        "head_upstream_remote_equal": True,
        "worktree_clean": True,
        "status": "PASS",
        "official_profile_id": "m336k8-final-v2",
    }
    value = {**body, "attestation_hash": content_hash(body)}
    path = tmp_path / "freeze_attestation.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    attestation = _stage_attestation({"f28_attestation": str(path)})

    assert isinstance(attestation, M336K9CommittedFreezeAttestation)
    assert attestation.contract_role == M336K9CommittedFreezeAttestation.ROLE


@pytest.mark.parametrize("case", M336K9_ADMISSION_MUTATION_CASES)
def test_m336k9_controller_admission_mutations(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = _valid()
    registry, profile, bundle, authorization, freeze, purpose = active
    other = registry.profile("m336k8-final-v1")

    if case == "active-k8-v2":
        assert _admit(active).official_admission_result == "PASS"
        return
    if case in {"historical-k8-v1-new-official", "f33-v1-used-as-f34-authority"}:
        operation = lambda: _admit(_valid("m336k8-final-v1"))
    elif case == "profile-absent":
        operation = lambda: verify_m336k_controller_admission(
            purpose=purpose,
            route_identity_bundle=bundle,
            expected_official_profile_id="m336k8-absent-v2",
            expected_profile_hash=profile.profile_hash,
            current_registry=registry,
            final_authorization=authorization,
            freeze_manifest=freeze,
        )
    elif case in {
        "route-from-another-profile",
        "protocol-from-another-profile",
        "acquisition-from-another-profile",
        "selector-from-another-profile",
        "evaluator-from-another-profile",
        "mixed-v1-v2-tuple",
    }:
        field = {
            "route-from-another-profile": "route_version",
            "protocol-from-another-profile": "protocol_run_id",
            "acquisition-from-another-profile": "acquisition_run_id",
            "selector-from-another-profile": "selector_run_id",
            "evaluator-from-another-profile": "evaluator_run_id",
            "mixed-v1-v2-tuple": "protocol_run_id",
        }[case]
        mixed = _mixed_bundle(bundle, other, field)
        operation = lambda: verify_m336k_controller_admission(
            purpose=purpose,
            route_identity_bundle=mixed,
            expected_official_profile_id=profile.profile_id,
            expected_profile_hash=profile.profile_hash,
            current_registry=registry,
            final_authorization=authorization,
            freeze_manifest=freeze,
        )
    elif case == "execution-mode-changed":
        raw = bundle.canonical_object()
        raw["execution_mode"] = {
            "schema_version": 1,
            "identity_kind": "EXECUTION_MODE",
            "value": "DISPOSABLE",
            "identity_hash": "0" * 64,
        }
        operation = lambda: M336K5RouteIdentityBundle.from_dict(raw)
    elif case in {
        "purpose-changed-after-validation",
        "disposable-bypasses-identity",
    }:
        operation = lambda: verify_m336k_controller_admission(
            purpose="DISPOSABLE",
            route_identity_bundle=bundle,
            expected_official_profile_id=profile.profile_id,
            expected_profile_hash=profile.profile_hash,
            current_registry=registry,
            final_authorization=authorization,
            freeze_manifest=freeze,
        )
    elif case == "profile-status-changed":
        changed = replace(
            profile, profile_status=M336KOfficialRouteProfileStatus.REHEARSAL_ONLY
        )
        changed_registry = replace(
            registry,
            profiles=tuple(
                changed if item == profile else item for item in registry.profiles
            ),
        )
        operation = changed_registry.verify
    elif case == "profile-hash-changed":
        changed = replace(profile, profile_hash="f" * 64)
        changed_registry = replace(
            registry,
            profiles=tuple(
                changed if item == profile else item for item in registry.profiles
            ),
        )
        operation = changed_registry.verify
    elif case == "registry-hash-changed":
        operation = replace(registry, registry_hash="f" * 64).verify
    elif case == "authorization-another-profile":
        temporary = replace(
            authorization,
            official_profile_id=other.profile_id,
            official_profile_hash=other.profile_hash,
            authorization_hash="0" * 64,
        )
        changed_authorization = replace(
            temporary, authorization_hash=content_hash(temporary._body())
        )
        operation = lambda: verify_m336k_controller_admission(
            purpose=purpose,
            route_identity_bundle=bundle,
            expected_official_profile_id=profile.profile_id,
            expected_profile_hash=profile.profile_hash,
            current_registry=registry,
            final_authorization=changed_authorization,
            freeze_manifest=freeze,
        )
    elif case == "freeze-another-profile":
        changed_freeze = _rehash_freeze(
            freeze,
            official_profile_id=other.profile_id,
            official_profile_hash=other.profile_hash,
        )
        operation = lambda: verify_m336k_controller_admission(
            purpose=purpose,
            route_identity_bundle=bundle,
            expected_official_profile_id=profile.profile_id,
            expected_profile_hash=profile.profile_hash,
            current_registry=registry,
            final_authorization=authorization,
            freeze_manifest=changed_freeze,
        )
    elif case == "validate-admission-missing":
        operation = lambda: _controller(
            tmp_path,
            bundle=bundle,
            authorization=authorization,
            freeze=freeze,
            purpose=purpose,
            admission=None,
        )
    elif case == "validate-admission-another-bundle":
        rehearsal = _valid("m336k8-rehearsal-v2")
        operation = lambda: _controller(
            tmp_path,
            bundle=bundle,
            authorization=authorization,
            freeze=freeze,
            purpose=purpose,
            admission=_admit(rehearsal),
        )
    elif case == "controller-recomputation-differs":
        prior = _admit(active)
        changed = replace(prior, freeze_hash="f" * 64, receipt_hash="0" * 64)
        changed = replace(changed, receipt_hash=content_hash(changed._body()))
        operation = lambda: _controller(
            tmp_path,
            bundle=bundle,
            authorization=authorization,
            freeze=freeze,
            purpose=purpose,
            admission=changed,
        )
    elif case == "second-controller-whitelist":
        original = Path.read_text

        def changed_source(path: Path, *args: Any, **kwargs: Any) -> str:
            source = original(path, *args, **kwargs)
            if path.name == "m336k5_controller.py":
                source += "\nprotocol_run_id.value not in {M336K8_PROTOCOL_RUN_ID}\n"
            return source

        monkeypatch.setattr(Path, "read_text", changed_source)
        operation = run_m336k_official_profile_coverage_gate
    elif case == "typed-values-differ-from-registry":
        monkeypatch.setattr(
            M336K5ProtocolRunId,
            "official_values",
            frozenset({"m336k8.final-java.outcome-a.v2"}),
        )
        operation = run_m336k_official_profile_coverage_gate
    elif case == "active-profile-missing-from-tests":
        import ai_brain.stage3.acquisition.m336k9_admission as admission_module

        monkeypatch.setattr(
            admission_module,
            "M336K9_CONTROLLER_ADMISSION_TESTED_PROFILE_IDS",
            tuple(
                item
                for item in M336K9_CONTROLLER_ADMISSION_TESTED_PROFILE_IDS
                if item != "m336k8-final-v2"
            ),
        )
        operation = run_m336k_official_profile_coverage_gate
    elif case == "new-profile-omitted-by-controller":
        import ai_brain.stage3.acquisition.m336k9_profiles as profile_module

        added = M336KOfficialRouteProfile.build(
            profile_id="m336k8-rehearsal-v3",
            profile_status=M336KOfficialRouteProfileStatus.REHEARSAL_ONLY,
            route_version="m336k8.candidate-isolated-java-disposable-route.v3",
            protocol_run_id="m336k8.disposable.controller-admission-v3.v3",
            acquisition_run_id=(
                "m336k8.disposable.controller-admission-v3.acquisition.v3"
            ),
            selector_run_id="m336k8.disposable.controller-admission-v3.selector.v3",
            evaluator_run_id="m336k8.disposable.controller-admission-v3.evaluator.v3",
            execution_mode="FINAL",
            minimum_controller_version="m336k9-controller.v2",
            authorization_branch_ref="refs/heads/disposable/m336k8-profile-v3",
        )
        augmented = M336KOfficialRouteProfileRegistry.build((*registry.profiles, added))
        monkeypatch.setattr(
            profile_module, "M336K_OFFICIAL_PROFILE_REGISTRY", augmented
        )
        operation = run_m336k_official_profile_coverage_gate
    elif case == "official-validated-as-disposable":
        rehearsal = _valid("m336k8-rehearsal-v2")
        (
            rehearsal_registry,
            rehearsal_profile,
            rehearsal_bundle,
            rehearsal_auth,
            rehearsal_freeze,
            _,
        ) = rehearsal
        operation = lambda: verify_m336k_controller_admission(
            purpose="OFFICIAL",
            route_identity_bundle=rehearsal_bundle,
            expected_official_profile_id=rehearsal_profile.profile_id,
            expected_profile_hash=rehearsal_profile.profile_hash,
            current_registry=rehearsal_registry,
            final_authorization=rehearsal_auth,
            freeze_manifest=rehearsal_freeze,
        )
    elif case == "read-only-promoted-without-registry-hash":
        historical = registry.profile("m336k8-final-v1")
        temporary = replace(
            historical,
            profile_status=M336KOfficialRouteProfileStatus.CURRENT_ACTIVE,
            profile_hash="0" * 64,
        )
        promoted = replace(temporary, profile_hash=content_hash(temporary._body()))
        changed_registry = replace(
            registry,
            profiles=tuple(
                promoted if item == historical else item for item in registry.profiles
            ),
        )
        operation = changed_registry.verify
    else:
        raise AssertionError(f"unhandled mutation case: {case}")

    with pytest.raises(M336K2ProtocolError):
        operation()


def test_m336k9_profile_coverage_and_identity_sets() -> None:
    registry = m336k_official_profile_registry()
    gate = run_m336k_official_profile_coverage_gate()
    assert gate.status == "PASS"
    assert gate.registered_profile_count == gate.tested_profile_count == 6
    assert gate.untested_profile_count == 0
    assert gate.independent_controller_whitelist_count == 0
    assert gate.controller_only_identity_predicate_count == 0
    assert M336K5RouteVersion.official_values == registry.official_values(
        "route_version"
    )
    assert M336K5ProtocolRunId.official_values == registry.official_values(
        "protocol_run_id"
    )
    assert M336K5AcquisitionRunId.official_values == registry.official_values(
        "acquisition_run_id"
    )
    assert M336K5SelectorRunId.official_values == registry.official_values(
        "selector_run_id"
    )
    assert M336K5EvaluatorRunId.official_values == registry.official_values(
        "evaluator_run_id"
    )


def test_m336k9_rehearsal_profile_is_admitted_only_as_disposable() -> None:
    state = _valid("m336k8-rehearsal-v2")
    receipt = _admit(state)
    assert receipt.purpose == "DISPOSABLE"
    assert receipt.profile_status == "REHEARSAL_ONLY"
    assert receipt.side_effect_count == 0


def test_m336k9_current_authorization_consumer_roundtrips_profile_fields() -> None:
    _registry, _profile, _bundle, authorization, _freeze, _purpose = _valid(
        "m336k8-final-v2"
    )
    parsed = m336k_current_final_authorization_from_dict(
        authorization.canonical_object()
    )
    assert parsed == authorization
    assert isinstance(parsed, M336K9FinalAuthorization)


def test_m336k9_admission_contract_survives_json_sequence_roundtrip() -> None:
    serialized = json.loads(json.dumps(M336K9_CONTROLLER_ADMISSION_CONTRACT))
    assert serialized != M336K9_CONTROLLER_ADMISSION_CONTRACT
    assert content_hash(serialized) == M336K9_CONTROLLER_ADMISSION_CONTRACT_HASH


def test_m336k9_official_admission_rehearsal_uses_final_pool_for_gate() -> None:
    qualifier_source = Path("scripts/m336k5_qualify_disposable_protocol.py").read_text(
        encoding="utf-8"
    )
    assert (
        'request["candidate_pool"]\n                    if official_admission_only'
        in qualifier_source
    )
    assert 'else legacy_request["candidate_pool"]' in qualifier_source
    builder_source = Path("scripts/m336k5_build_component_bundle.py").read_text(
        encoding="utf-8"
    )
    assert 'not (profile_id is not None and mode == "OFFICIAL")' in builder_source
    assert "candidate_pool_hash=candidate_pool_hash" in builder_source
    mutation_source = Path("scripts/m336k9_run_admission_mutations.py").read_text(
        encoding="utf-8"
    )
    assert 'parser.add_argument("--startup-receipt"' in mutation_source
    assert '"startup_receipt_hash": startup.receipt_hash' in mutation_source
