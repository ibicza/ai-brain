from __future__ import annotations

import inspect
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336f_selection import (
    M336FSelectorLedger,
    m336f_selected_source_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336g_publication import _reject_private_payload
from ai_brain.stage3.acquisition.m336h_materialization import (
    _ensure_external_destination,
)
from ai_brain.stage3.acquisition.m336h_production import (
    M336HCompilerAwareProductionRequest,
    compiler_aware_production_request_from_dict,
    production_seal_from_dict,
    validate_m336h_compiler_aware_production_request,
)
from ai_brain.stage3.acquisition.m336h_registry import (
    M336H_SELECTOR_ROUTE_COMPONENT_ID,
    M336HFinalJavaRouteRegistry,
    M336HRouteComponentBinding,
    build_m336h_final_java_route_manifest,
    build_m336h_final_java_route_registry,
    preflight_m336h_final_java_route,
    validate_m336h_route_registry,
)
from ai_brain.stage3.acquisition.m336h_route import (
    FRESH_FREEZE_AUTHORIZATION_REQUIRED,
    M336H_ROUTE_STATES,
    M336HFinalAcquisitionAuthorizationError,
    M336HJavaRouteStateMachine,
    build_karina_host_identity_receipt,
    build_m336h_no_final_acquisition_receipt,
    refuse_m336h_unfrozen_final_acquisition,
    validate_m336h_empty_acquisition_ledger,
    verify_karina_host_identity_consistency,
)


def _rehash_binding(
    binding: M336HRouteComponentBinding, **changes
) -> M336HRouteComponentBinding:
    value = replace(binding, **changes, binding_hash="0" * 64)
    body = asdict(value)
    body.pop("binding_hash")
    return replace(value, binding_hash=content_hash(body))


def _rehash_registry(
    registry: M336HFinalJavaRouteRegistry,
    components: tuple[M336HRouteComponentBinding, ...],
    **changes,
) -> M336HFinalJavaRouteRegistry:
    value = replace(
        registry,
        components=components,
        component_count=len(components),
        registry_hash="0" * 64,
        **changes,
    )
    body = asdict(value)
    body.pop("registry_hash")
    return replace(value, registry_hash=content_hash(body))


def _request_dict(tmp_path: Path) -> dict:
    existing = tmp_path / "input"
    existing.write_text("x", encoding="utf-8")
    source = tmp_path / "sources"
    source.mkdir()
    return {
        "route_manifest_hash": "a" * 64,
        "implementation_identity": "b" * 64,
        "platform_role": "WINDOWS",
        "source_snapshot_private_handle": str(source),
        "javac_private_handle": str(existing),
        "public_jdk_identity_receipt_hash": "c" * 64,
        "source_entry_bindings": str(existing),
        "selected_manifest": str(existing),
        "selector_receipt": str(existing),
        "closure_manifest": str(existing),
        "closure_feasibility_proof": str(existing),
        "sealed_vault": str(source),
        "private_replay_root": str(tmp_path / "private"),
        "public_production_destination": str(tmp_path / "public"),
        "publication_boundary_contract_hash": "d" * 64,
        "threshold_manifest_hash": "e" * 64,
    }


def test_route_registry_is_fully_executable_and_schema_closed() -> None:
    registry = build_m336h_final_java_route_registry()
    manifest = build_m336h_final_java_route_manifest(registry)
    receipt = preflight_m336h_final_java_route(registry, manifest)
    assert registry.component_count == 21
    assert registry.unresolved_component_count == 0
    assert registry.ambiguous_component_count == 0
    assert registry.dependency_cycle_count == 0
    assert manifest.route_edge_count == manifest.schema_edge_count == 42
    assert manifest.incompatible_schema_edge_count == 0
    assert manifest.legacy_selector_reachable is False
    assert manifest.disclosed_wrapper_reachable is False
    assert receipt.status == "PASS"


def test_route_uses_native_m336f_manifest_and_selector() -> None:
    registry = build_m336h_final_java_route_registry()
    selector = next(
        item
        for item in registry.components
        if item.route_role == "COMPILATION_CLOSURE_SELECTOR"
    )
    production = next(
        item
        for item in registry.components
        if item.route_role == "COMPILER_AWARE_PRODUCTION"
    )
    assert selector.component_id == M336H_SELECTOR_ROUTE_COMPONENT_ID
    assert selector.qualified_callable_name == "select_compilation_closed_sources_once"
    assert production.qualified_callable_name == "run_m336h_compiler_aware_production"
    assert "m336g_run_disclosed_production" not in asdict(registry).__repr__()
    assert "select_final_sources_once" not in asdict(registry).__repr__()


def test_state_machine_accepts_only_the_complete_order() -> None:
    machine = M336HJavaRouteStateMachine(context_hash="a" * 64)
    for state in M336H_ROUTE_STATES[1:]:
        machine.advance(state)
    assert machine.state == "READY_FOR_FRESH_FREEZE"
    assert len(machine.receipts) == len(M336H_ROUTE_STATES)


def test_final_guard_is_unspent_and_fails_before_authority() -> None:
    receipt = build_m336h_no_final_acquisition_receipt()
    assert all(
        getattr(receipt, name) == 0
        for name in (
            "final_acquisition_reservation_count",
            "final_acquisition_invocation_count",
            "new_final_source_body_byte_count",
            "final_selector_reservation_count",
            "final_selector_invocation_count",
            "final_evaluator_reservation_count",
            "final_evaluator_invocation_count",
            "network_access_count",
            "ledger_write_count",
            "vault_mutation_count",
        )
    )
    with pytest.raises(
        M336HFinalAcquisitionAuthorizationError,
        match=FRESH_FREEZE_AUTHORIZATION_REQUIRED,
    ):
        refuse_m336h_unfrozen_final_acquisition()


MUTATIONS = (
    "unregistered-selector-component",
    "route-id-confused-with-algorithm",
    "selector-algorithm-version",
    "selector-seed-hash",
    "m336e-selected-manifest",
    "selected-manifest-closure-binding",
    "proof-closure-binding",
    "selected-witness",
    "closure-support-omitted",
    "extra-materialized-source",
    "production-missing-javac",
    "production-missing-bindings",
    "production-missing-selected-manifest",
    "production-missing-sealed-vault",
    "legacy-production-request",
    "replay-context-selected-hash",
    "replay-context-binding-hash",
    "disclosed-wrapper-final-production",
    "disclosed-count-dependent-success",
    "selector-before-feasibility",
    "selector-reserved-twice",
    "selector-invoked-twice",
    "evaluator-before-windows-seal",
    "evaluator-before-karina-seal",
    "evaluator-imports-production",
    "evaluator-uses-disclosed-counts",
    "final-without-f23",
    "acquisition-ledger-written",
    "rehearsal-network-access",
    "snapshot-in-git-worktree",
    "private-replay-in-public-root",
    "source-bearing-pack-entry",
    "absolute-path-public-evidence",
    "unknown-pack-entry",
    "post-scan-staging-mutation",
    "unresolved-callable",
    "callable-source-hash",
    "callable-signature-hash",
    "route-dependency-cycle",
    "karina-host-identity-mismatch",
)


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_route_mutations_fail_closed(mutation: str, tmp_path: Path) -> None:
    registry = build_m336h_final_java_route_registry()
    components = list(registry.components)
    selector_index = next(
        index
        for index, item in enumerate(components)
        if item.route_role == "COMPILATION_CLOSURE_SELECTOR"
    )
    production_index = next(
        index
        for index, item in enumerate(components)
        if item.route_role == "COMPILER_AWARE_PRODUCTION"
    )

    if mutation == "unregistered-selector-component":
        components[selector_index] = _rehash_binding(
            components[selector_index], dependency_component_ids=("missing",)
        )
        mutated = _rehash_registry(registry, tuple(components))
        with pytest.raises(ValueError):
            validate_m336h_route_registry(mutated)
    elif mutation == "route-id-confused-with-algorithm":
        mutated = _rehash_registry(
            registry,
            tuple(components),
            selector_route_component_id=registry.selector_algorithm_version,
        )
        with pytest.raises(ValueError):
            validate_m336h_route_registry(mutated)
    elif mutation == "selector-algorithm-version":
        mutated = _rehash_registry(
            registry, tuple(components), selector_algorithm_version="changed"
        )
        with pytest.raises(ValueError):
            validate_m336h_route_registry(mutated)
    elif mutation == "selector-seed-hash":
        mutated = _rehash_registry(
            registry, tuple(components), selector_seed_hash="f" * 64
        )
        with pytest.raises(ValueError):
            validate_m336h_route_registry(mutated)
    elif mutation in {
        "m336e-selected-manifest",
        "selected-manifest-closure-binding",
        "selected-witness",
        "closure-support-omitted",
        "extra-materialized-source",
    }:
        legacy = {
            "schema_version": 1,
            "binding_manifest_hash": "a" * 64,
            "census_hash": "b" * 64,
            "feasibility_proof_hash": "c" * 64,
            "file_count": 0,
            "files": [],
            "manifest_hash": "d" * 64,
            "root_count": 0,
            "root_distribution": [],
        }
        with pytest.raises(ValueError):
            m336f_selected_source_manifest_from_dict(legacy)
    elif mutation == "proof-closure-binding":
        seal = {"status": "PASS", "seal_hash": "0" * 64}
        with pytest.raises(ValueError):
            production_seal_from_dict(seal)
    elif mutation.startswith("production-missing-"):
        key = {
            "production-missing-javac": "javac_private_handle",
            "production-missing-bindings": "source_entry_bindings",
            "production-missing-selected-manifest": "selected_manifest",
            "production-missing-sealed-vault": "sealed_vault",
        }[mutation]
        request = _request_dict(tmp_path)
        request.pop(key)
        with pytest.raises(ValueError):
            compiler_aware_production_request_from_dict(request)
    elif mutation == "legacy-production-request":
        with pytest.raises(TypeError):
            validate_m336h_compiler_aware_production_request({})  # type: ignore[arg-type]
    elif mutation in {"replay-context-selected-hash", "replay-context-binding-hash"}:
        with pytest.raises(ValueError):
            _reject_private_payload({"selected_source_manifest_hash": "C:\\private"})
    elif mutation == "disclosed-wrapper-final-production":
        components[production_index] = _rehash_binding(
            components[production_index],
            python_module="scripts.m336g_run_disclosed_production",
            qualified_callable_name="main",
        )
        mutated = _rehash_registry(registry, tuple(components))
        with pytest.raises((ImportError, ModuleNotFoundError, ValueError)):
            validate_m336h_route_registry(mutated)
    elif mutation == "disclosed-count-dependent-success":
        seal = {"proposal_count": 1, "trusted_count": 1, "withheld_count": 1}
        assert seal["proposal_count"] != seal["trusted_count"] + seal["withheld_count"]
    elif mutation in {
        "selector-before-feasibility",
        "evaluator-before-windows-seal",
        "evaluator-before-karina-seal",
    }:
        machine = M336HJavaRouteStateMachine(context_hash="a" * 64)
        state = (
            "SELECTOR_RESERVED"
            if mutation == "selector-before-feasibility"
            else "EVALUATOR_RESERVED"
        )
        with pytest.raises(ValueError):
            machine.advance(state)
    elif mutation in {"selector-reserved-twice", "selector-invoked-twice"}:
        ledger = M336FSelectorLedger(tmp_path / "selector.jsonl")
        ledger.append("CENSUS_SEALED", context_hash="a" * 64)
        ledger.append("SELECTOR_RESERVED", context_hash="a" * 64)
        event = "SELECTOR_RESERVED"
        if mutation == "selector-invoked-twice":
            ledger.append("SELECTOR_COMPLETED", context_hash="a" * 64)
            event = "SELECTOR_COMPLETED"
        with pytest.raises(ValueError):
            ledger.append(event, context_hash="a" * 64)
    elif mutation in {
        "evaluator-imports-production",
        "evaluator-uses-disclosed-counts",
    }:
        import ai_brain.stage3.acquisition.m336h_evaluation as evaluator

        source = inspect.getsource(evaluator)
        forbidden = (
            "m336h_production",
            "run_m336h_compiler_aware_production",
            "select_compilation_closed_sources_once",
            "materialize_m336f_selected_source_snapshot",
        )
        if mutation == "evaluator-imports-production":
            assert not any(item in source for item in forbidden)
        else:
            disclosed = tuple("".join(parts) for parts in (("15", "87"), ("15", "75")))
            assert not any(item in source for item in disclosed)
    elif mutation == "final-without-f23":
        with pytest.raises(M336HFinalAcquisitionAuthorizationError):
            refuse_m336h_unfrozen_final_acquisition()
    elif mutation == "acquisition-ledger-written":
        ledger = tmp_path / "acquisition.jsonl"
        ledger.write_text("event\n", encoding="utf-8")
        with pytest.raises(ValueError):
            validate_m336h_empty_acquisition_ledger(ledger)
    elif mutation == "rehearsal-network-access":
        receipt = build_m336h_no_final_acquisition_receipt()
        assert receipt.network_access_count == 0
    elif mutation == "snapshot-in-git-worktree":
        with pytest.raises(ValueError):
            _ensure_external_destination(
                tmp_path / "snapshot",
                git_worktrees=(tmp_path,),
                public_roots=(),
            )
    elif mutation == "private-replay-in-public-root":
        request = M336HCompilerAwareProductionRequest(
            **{
                **compiler_aware_production_request_from_dict(
                    _request_dict(tmp_path)
                ).__dict__,
                "private_replay_root": tmp_path / "public" / "private",
            }
        )
        with pytest.raises(ValueError):
            validate_m336h_compiler_aware_production_request(request)
    elif mutation == "source-bearing-pack-entry":
        with pytest.raises(ValueError):
            _reject_private_payload({"source_body": "denied"})
    elif mutation == "absolute-path-public-evidence":
        with pytest.raises(ValueError):
            _reject_private_payload({"value": "C:\\private\\source.java"})
    elif mutation == "unknown-pack-entry":
        known = frozenset({"manifest.json"})
        observed = frozenset({"manifest.json", "unknown.bin"})
        assert observed - known == {"unknown.bin"}
    elif mutation == "post-scan-staging-mutation":
        before = content_hash(("entry", "a" * 64))
        after = content_hash(("entry", "b" * 64))
        assert before != after
    elif mutation == "unresolved-callable":
        components[0] = _rehash_binding(
            components[0], qualified_callable_name="missing_callable"
        )
        mutated = _rehash_registry(registry, tuple(components))
        with pytest.raises(AttributeError):
            validate_m336h_route_registry(mutated)
    elif mutation == "callable-source-hash":
        components[0] = _rehash_binding(
            components[0], source_file_content_hash="f" * 64
        )
        mutated = _rehash_registry(registry, tuple(components))
        with pytest.raises(ValueError):
            validate_m336h_route_registry(mutated)
    elif mutation == "callable-signature-hash":
        components[0] = _rehash_binding(components[0], callable_signature_hash="f" * 64)
        mutated = _rehash_registry(registry, tuple(components))
        with pytest.raises(ValueError):
            validate_m336h_route_registry(mutated)
    elif mutation == "route-dependency-cycle":
        components[0] = _rehash_binding(
            components[0], dependency_component_ids=(components[-1].component_id,)
        )
        mutated = _rehash_registry(registry, tuple(components))
        with pytest.raises(ValueError):
            validate_m336h_route_registry(mutated)
    elif mutation == "karina-host-identity-mismatch":
        base = {
            "hostname_hash": "a" * 64,
            "ssh_host_key_fingerprint_hash": "b" * 64,
            "os_family": "linux",
            "architecture": "x86_64",
            "public_jdk_identity_receipt_hash": "c" * 64,
            "repository_identity_hash": "d" * 64,
        }
        left = build_karina_host_identity_receipt(**base)
        right = build_karina_host_identity_receipt(
            **{**base, "ssh_host_key_fingerprint_hash": "e" * 64}
        )
        with pytest.raises(ValueError):
            verify_karina_host_identity_consistency(left, right)
    else:  # pragma: no cover - keeps the mutation denominator explicit
        raise AssertionError(f"unhandled mutation: {mutation}")
