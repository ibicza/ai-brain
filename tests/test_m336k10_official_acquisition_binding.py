from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_identity import (
    build_m336k13_official_identity_bundle,
)
from ai_brain.stage3.acquisition.m336k8_freeze import (
    M336K10CommittedFreezeAttestation,
)
from ai_brain.stage3.acquisition.m336k9_authorization import (
    build_m336k13_final_authorization,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k10_binding import (
    M336K10_MUTATION_CASES,
    M336K10_PROFILE_ID,
    M336K10_REQUIRED_OFFICIAL_HOSTS,
    M336K13_ACQUISITION_RUN_ID,
    M336K13_PROFILE_ID,
    M336K10FreezeOriginReceipt,
    _m336k10_preledger_source_evidence,
    build_m336k10_post_authorization_components,
    build_official_acquisition_components,
    read_provider_sources,
    verify_m336k10_official_acquisition_binding,
    verify_m336k10_preledger_coverage,
)

ROOT = Path(__file__).resolve().parents[1]
F34 = ROOT / "artifacts/m336k9/f34-freeze/components"
POOL = F34 / "04-candidate_pool.json"
AUTHORITY = ROOT / "artifacts/acquisition/m336i_freeze_v8/authority_statement.txt"
DISCLOSURE = F34 / "23-disclosure_registry_manifest.json"
H = "a" * 64


def _rehash(value, field: str):
    temporary = replace(value, **{field: "0" * 64})
    return replace(temporary, **{field: content_hash(temporary._body())})


def _pool_with(mutator) -> tuple[dict, bytes]:
    value = json.loads(POOL.read_text(encoding="utf-8"))
    mutator(value)
    body = dict(value)
    body.pop("pool_hash")
    value["pool_hash"] = content_hash(body)
    return value, (canonical_json(value) + "\n").encode()


def _graph() -> dict:
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    selector = json.loads((F34 / "69-selector_policy.json").read_text("utf-8"))
    maven_source, scm_source = read_provider_sources(ROOT)
    profile = m336k_official_profile_registry().profile(M336K13_PROFILE_ID)
    components = build_official_acquisition_components(
        pool=pool,
        pool_bytes=POOL.read_bytes(),
        profile=profile,
        archive_policy_hash="239f6aad9c6d0068a353e065cde9f996c38f1cc9e79509141dea13e1a37d108a",
        candidate_terminal_policy_hash="39da07828af484753198e2704837626001d742fa9c66e611c97aab34a8406203",
        global_continuation_policy_hash="01f4fe20e3ca3ab749d5444579bcd176a71ca3dbea5c70b6b06bf5c50e791838",
        authority_statement_hash="f5d12c85ce1cb2a9b11a76bc4de229be0dc42c0b91ca99234325e7eb44305e77",
        disclosure_registry_manifest_hash="01825bab163e9bed45e26e7af79fa54cb365b561319cb0e0b7d4671e4f0c5446",
        selector_policy=selector,
        selector_policy_hash=selector["policy_hash"],
        maven_provider_source=maven_source,
        scm_provider_source=scm_source,
    )
    policy = components["acquisition_policy"]
    bundle = build_m336k13_official_identity_bundle(
        route_registry_hash=content_hash("route-registry"),
        route_manifest_hash=content_hash("route-manifest"),
        acquisition_policy_hash=policy.acquisition_policy_hash,
        selector_policy_hash=selector["policy_hash"],
        evaluator_policy_hash=content_hash("evaluator-policy"),
    )
    authorization = build_m336k13_final_authorization(
        official_controller_executable_binding_hash=H,
        native_stage_plan_binding_hash=H,
        producer_consumer_parity_receipt_hash=H,
        native_execution_capsule_receipt_hash=H,
        final_controller_plan_binding_receipt_hash=H,
        official_profile_id=M336K13_PROFILE_ID,
        bundle=bundle,
        pool_binding=components["pool_binding"],
        network_authority=components["network_authority"],
        acquisition_policy=policy,
        provider_configuration=components["provider_configuration"],
        acquisition_binding_receipt_hash=components["authorization_binding_hash"],
        exact_implementation_tip="1" * 40,
        exact_q30_sha="2" * 40,
        branch_ref=profile.authorization_branch_ref,
        archive_policy_hash=policy.archive_policy_hash,
        candidate_terminal_policy_hash=policy.candidate_terminal_policy_hash,
        global_continuation_policy_hash=policy.global_continuation_policy_hash,
        route_manifest_hash=bundle.route_manifest_hash,
        route_registry_hash=bundle.route_registry_hash,
        schema_registry_hash=H,
        readiness_hash=H,
        executable_dependency_manifest_hash=H,
        python_environment_manifest_hash=H,
        python_startup_policy_hash=H,
        bootstrap_source_hash=H,
        windows_launcher_source_hash=H,
        karina_launcher_hash=H,
        sanitized_environment_hash=H,
        startup_receipt_schema_hash=H,
        resource_budget_hash=H,
        storage_reservation_receipt_hash=H,
        resource_monitor_hash=H,
        cleanup_policy_hash=H,
        recovery_policy_hash=H,
        authority_statement_hash=policy.authority_statement_hash,
        disclosure_registry_manifest_hash=policy.disclosure_registry_manifest_hash,
        selector_policy_hash=bundle.selector_policy_hash,
        evaluator_policy_hash=bundle.evaluator_policy_hash,
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
    post = build_m336k10_post_authorization_components(
        pool_binding=components["pool_binding"],
        network_authority=components["network_authority"],
        policy=policy,
        profile=profile,
        provider=components["provider_configuration"],
        authorization=authorization,
        route_identity_bundle_hash=bundle.bundle_hash,
        authorization_binding_hash=components["authorization_binding_hash"],
    )
    return {
        **components,
        **post,
        "pool": pool,
        "pool_bytes": POOL.read_bytes(),
        "profile": profile,
        "authorization": authorization,
        "bundle": bundle,
        "maven_source": maven_source,
        "scm_source": scm_source,
    }


def _verify(graph: dict):
    return verify_m336k10_official_acquisition_binding(
        pool=graph["pool"],
        pool_bytes=graph["pool_bytes"],
        pool_binding=graph["pool_binding"],
        network_authority=graph["network_authority"],
        policy=graph["acquisition_policy"],
        profile=graph["profile"],
        shared_policy=graph["shared_policy"],
        provider=graph["provider_configuration"],
        authorization=graph["authorization"],
        ledger_context=graph["ledger_context"],
        stage_binding=graph["stage_binding"],
        authority_statement_bytes=AUTHORITY.read_bytes(),
        disclosure_registry_manifest_bytes=DISCLOSURE.read_bytes(),
        maven_provider_source=graph["maven_source"],
        scm_provider_source=graph["scm_source"],
        expected_receipt=graph["receipt"],
    )


def test_exact_official_binding_and_metadata_only_admission() -> None:
    graph = _graph()
    receipt = _verify(graph)
    assert graph["pool_binding"].pool_semantic_hash == (
        "b48ee354dc710a6c0ac0ed2cfceb1385c0d12cc8efb6b8fbef00e8d2f6ab572e"
    )
    assert graph["pool_binding"].pool_bytes_hash == (
        "78cfb85fc59687186f0e420d410bf648816bce6ae2539acb445f8da74d77a0fa"
    )
    assert graph["pool_binding"].candidate_count == 96
    assert graph["pool_binding"].organization_count == 64
    assert graph["network_authority"].allowed_network_hosts == (
        M336K10_REQUIRED_OFFICIAL_HOSTS
    )
    assert graph["acquisition_policy"].acquisition_run_id == (
        M336K13_ACQUISITION_RUN_ID
    )
    assert receipt.status == "PASS"


def test_profile_v6_is_only_active_profile() -> None:
    registry = m336k_official_profile_registry()
    active = [
        item
        for item in registry.profiles
        if item.profile_status is M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
    ]
    assert [item.profile_id for item in active] == [M336K13_PROFILE_ID]
    assert registry.profile("m336k8-final-v5").profile_status is (
        M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
    )
    assert registry.profile("m336k8-final-v4").profile_status is (
        M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
    )
    assert registry.profile(M336K10_PROFILE_ID).profile_status is (
        M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
    )
    assert registry.profile("m336k8-final-v2").profile_status is (
        M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
    )


def test_f34_forensics_is_public_safe_and_hash_bound() -> None:
    path = ROOT / "artifacts/m336k10/f34-acquisition-binding-forensics.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("report_hash")
    encoded = canonical_json(value)
    assert claimed == content_hash(value)
    assert "m336k9-official-f34" not in encoded
    assert "m336k9-dev-r34" not in encoded
    assert "\\\\" not in encoded
    assert value["unclassified_root_cause_count"] == 0
    assert value["failure_reproduction"]["side_effect_count"] == 0
    assert value["candidate_pool"]["pool_semantic_hash"] == (
        "b48ee354dc710a6c0ac0ed2cfceb1385c0d12cc8efb6b8fbef00e8d2f6ab572e"
    )


def test_f35_attestation_binds_every_official_acquisition_identity() -> None:
    body = {
        "schema_version": 1,
        "contract_role": M336K10CommittedFreezeAttestation.ROLE,
        "exact_freeze_sha": "1" * 40,
        "exact_qualification_parent": "2" * 40,
        "committed_tree_hash": "3" * 40,
        "prospective_freeze_tree_hash": H,
        "prospective_tree_matches": True,
        "route_identity_bundle_hash": H,
        "authorization_hash": H,
        "route_hash": H,
        "post_freeze_input_bundle_hash": H,
        "source_identity_receipt_hash": H,
        "freeze_assembly_plan_hash": H,
        "producer_origin_map_hash": H,
        "implementation_change_count": 0,
        "merge_count": 0,
        "head_upstream_remote_equal": True,
        "worktree_clean": True,
        "status": "PASS",
        "official_profile_id": M336K10_PROFILE_ID,
        "official_profile_hash": H,
        "official_profile_registry_hash": H,
        "profile_coverage_gate_hash": H,
        "controller_admission_contract_hash": H,
        "official_candidate_pool_binding_hash": H,
        "official_network_authority_manifest_hash": H,
        "official_acquisition_policy_hash": H,
        "official_acquisition_binding_receipt_hash": H,
        "official_provider_configuration_hash": H,
        "stage_request_acquisition_binding_hash": H,
        "acquisition_ledger_context_template_hash": H,
        "official_freeze_origin_receipt_hash": H,
    }
    value = {**body, "attestation_hash": content_hash(body)}
    parsed = M336K10CommittedFreezeAttestation.from_dict(value)
    assert parsed.canonical_object() == value


def test_validate_only_and_controller_cover_acquisition_before_route_events() -> None:
    receipt = verify_m336k10_preledger_coverage(ROOT)
    assert receipt.status == "PASS"
    assert receipt.uncovered_acquisition_predicate_count == 0
    assert receipt.route_event_before_acquisition_admission_count == 0


@pytest.mark.parametrize("case", M336K10_MUTATION_CASES)
def test_closed_under_rehash_semantic_mutations(case: str) -> None:
    graph = _graph()

    if case in {
        "official-pool-with-disposable-policy",
        "official-pool-with-fixture-hosts",
        "policy-hosts-wrong",
        "missing-official-host",
        "extra-official-host",
        "uppercase-host-variant",
        "legacy-acquisition-policy-copied",
    }:
        hosts = ("fixture.invalid",)
        if case == "missing-official-host":
            hosts = M336K10_REQUIRED_OFFICIAL_HOSTS[:-1]
        elif case == "extra-official-host":
            hosts = (*M336K10_REQUIRED_OFFICIAL_HOSTS, "extra.invalid")
        elif case == "uppercase-host-variant":
            hosts = ("GitHub.com", *M336K10_REQUIRED_OFFICIAL_HOSTS[1:])
        changed = replace(graph["acquisition_policy"], allowed_network_hosts=hosts)
        graph["acquisition_policy"] = _rehash(changed, "acquisition_policy_hash")
    elif case == "policy-pool-hash-wrong":
        changed = replace(graph["acquisition_policy"], candidate_pool_hash=H)
        graph["acquisition_policy"] = _rehash(changed, "acquisition_policy_hash")
    elif case in {
        "authorization-pool-hash-wrong",
        "legacy-authorization-copied",
    }:
        changed = replace(graph["authorization"], pool_semantic_hash=H)
        graph["authorization"] = _rehash(changed, "authorization_hash")
    elif case == "authorization-hosts-wrong":
        changed = replace(
            graph["authorization"], allowed_network_hosts=("fixture.invalid",)
        )
        graph["authorization"] = _rehash(changed, "authorization_hash")
    elif case in {
        "provider-pool-binding-wrong",
        "provider-hosts-wrong",
        "worker-provider-host-set-changed",
    }:
        values = {"official_candidate_pool_binding_hash": H}
        if case != "provider-pool-binding-wrong":
            values = {"maven_provider_hosts": ("fixture.invalid",)}
        changed = replace(graph["provider_configuration"], **values)
        graph["provider_configuration"] = _rehash(changed, "configuration_hash")
    elif case in {"url-host-changed", "http-url", "uppercase-host-variant"}:

        def mutate(value):
            candidate = value["candidates"][0]
            if case == "http-url":
                candidate["source_url"] = candidate["source_url"].replace(
                    "https://", "http://"
                )
            elif case == "uppercase-host-variant":
                candidate["source_url"] = candidate["source_url"].replace(
                    "repo.maven.apache.org", "Repo.Maven.Apache.Org"
                )
            else:
                candidate["source_url"] = candidate["source_url"].replace(
                    "repo.maven.apache.org", "fixture.invalid"
                )

        graph["pool"], graph["pool_bytes"] = _pool_with(mutate)
    elif case in {
        "candidate-order-changed",
        "candidate-added",
        "candidate-removed",
        "candidate-policy-hash-changed",
    }:

        def mutate(value):
            if case == "candidate-order-changed":
                value["candidates"][0], value["candidates"][1] = (
                    value["candidates"][1],
                    value["candidates"][0],
                )
            elif case == "candidate-added":
                value["candidates"].append(dict(value["candidates"][0]))
                value["candidate_count"] += 1
            elif case == "candidate-removed":
                value["candidates"].pop()
                value["candidate_count"] -= 1
            else:
                value["candidates"][0]["policy_hash"] = H

        graph["pool"], graph["pool_bytes"] = _pool_with(mutate)
    elif case == "v2-acquisition-run-id":
        changed = replace(
            graph["acquisition_policy"],
            acquisition_run_id="m336k8.final-java.global-acquisition.v2",
        )
        graph["acquisition_policy"] = _rehash(changed, "acquisition_policy_hash")
    elif case == "rehearsal-profile-in-official-policy":
        graph["profile"] = m336k_official_profile_registry().profile(
            "m336k8-rehearsal-v2"
        )
    elif case == "rehearsal-scope-relabeled-official":
        changed = replace(
            graph["acquisition_policy"],
            policy_version="m336k5.candidate-isolated-final.v1",
        )
        graph["acquisition_policy"] = _rehash(changed, "acquisition_policy_hash")
    elif case == "forged-pass-receipt":
        changed = replace(graph["receipt"], final_authorization_hash=H)
        graph["receipt"] = _rehash(changed, "receipt_hash")
    elif case in {"validate-only-verifier-omitted", "route-event-before-admission"}:
        request_source = (
            ROOT / "src/ai_brain/stage3/acquisition/m336k8_request.py"
        ).read_text(encoding="utf-8")
        controller_source = (
            ROOT / "src/ai_brain/stage3/acquisition/m336k5_controller.py"
        ).read_text(encoding="utf-8")
        binding_source = (
            ROOT / "src/ai_brain/stage3/acquisition/m336k10_binding.py"
        ).read_text(encoding="utf-8")
        worker_source = (
            ROOT / "src/ai_brain/stage3/acquisition/m336k2_acquisition.py"
        ).read_text(encoding="utf-8")
        if case == "validate-only-verifier-omitted":
            request_source = request_source.replace(
                "acquisition_binding = _verify_m336k10_acquisition_components(",
                "acquisition_binding = omitted_acquisition_verifier(",
                1,
            )
        else:
            controller_source = "ledger.append(\n" + controller_source
        with pytest.raises(M336K2ProtocolError):
            _m336k10_preledger_source_evidence(
                request_source,
                controller_source,
                binding_source,
                worker_source,
            )
        return
    elif case == "controller-receipt-differs":
        changed = replace(graph["receipt"], authorization_binding_hash=H)
        graph["receipt"] = _rehash(changed, "receipt_hash")
    elif case == "stage-request-binding-changed":
        changed = replace(graph["stage_binding"], provider_configuration_hash=H)
        graph["stage_binding"] = _rehash(changed, "binding_hash")
    elif case in {
        "fixture-host-in-official-components",
        "wrong-pool-in-official-components",
    }:
        values = {
            "schema_version": 1,
            "contract_role": M336K10FreezeOriginReceipt.ROLE,
            "entries": (),
            "component_count": 0,
            "rehearsal_scope_component_count": 0,
            "fixture_host_occurrence_count": int(case.startswith("fixture")),
            "wrong_pool_occurrence_count": int(case.startswith("wrong")),
            "unclassified_component_count": 0,
            "status": "PASS",
        }
        receipt = M336K10FreezeOriginReceipt(
            **values, receipt_hash=content_hash(values)
        )
        with pytest.raises(M336K2ProtocolError):
            receipt.verify()
        return
    else:
        raise AssertionError(f"unhandled mutation case: {case}")

    with pytest.raises(M336K2ProtocolError):
        _verify(graph)
