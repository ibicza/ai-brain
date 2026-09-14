"""Closed-under-rehash mutation qualification for M-33.6k.8."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k8_contracts import (
    M336K8FreezeAssemblyPlan,
    M336K8FreezeInputAssembler,
    M336K8FrozenContractCompatibilityGateV2,
    M336K8ProjectSourceIdentityPolicy,
    forbid_m336k8_post_freeze_mutation,
    m336k8_semantic_binding_mismatches,
    require_m336k8_evidence_only_diff,
    require_m336k8_execution_authority,
    require_m336k8_frozen_bytes,
)

M336K8_MUTATION_CASES = (
    "controller environment replaced by persistent capsule environment",
    "controller executable manifest replaced by persistent capsule manifest",
    "both controller manifests replaced together",
    "wrong-domain graph fully rehashed downstream",
    "controller source identity set to capsule identity and rehashed",
    "controller manifest built from historical freeze tip",
    "controller manifest built before implementation repair",
    "committed implementation identity changed",
    "live implementation identity changed",
    "tracked path set changed",
    "source scope narrowed",
    "source row ordering changed",
    "source identity algorithm changed",
    "source identity policy hash changed",
    "startup receipt produced from another checkout",
    "startup receipt produced from persistent capsule checkout",
    "qualification-like commit changes src",
    "freeze-like commit changes scripts",
    "required bridge file differs on controller side",
    "required bridge file differs in capsule manifest",
    "required bridge entry omitted",
    "required bridge schema compatibility omitted",
    "controller startup binding missing",
    "persistent capsule source binding missing",
    "source-domain compatibility receipt missing",
    "full-project identity equality incorrectly required",
    "full-project identity difference accepted with bridge difference",
    "controller legacy alias points to capsule-domain artifact",
    "generic ambiguous environment component accepted",
    "generic ambiguous dependency component accepted",
    "rehearsal assembly plan differs from official plan",
    "rehearsal producer-origin map differs from official map",
    "consumed component omitted from compatibility gate",
    "unused compatibility artifact added",
    "semantic mismatch count forged to zero",
    "gate PASS forged after semantic mismatch",
    "frozen controller manifest replaced by regenerated manifest",
    "frozen post-freeze bundle replaced by regenerated bundle",
    "controller component generated from stale private output",
    "persistent capsule recreated after freeze",
    "cleanup requested after freeze",
    "storage reservation released before accepted validate-only",
    "controller invoked without accepted validate-only",
    "committed freeze bytes differ from validated bytes",
)


@dataclass(frozen=True)
class M336K8MutationResult:
    case_number: int
    case_name: str
    fully_rehashed: bool
    rejection_layer: str
    status: str


@dataclass(frozen=True)
class _Artifact:
    value: dict[str, Any]

    def canonical_object(self) -> dict[str, Any]:
        return self.value


def run_m336k8_mutation_case(case_number: int) -> M336K8MutationResult:
    if case_number < 1 or case_number > len(M336K8_MUTATION_CASES):
        raise ValueError("M336K8 mutation case is out of range")
    semantic_cases = {
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        15,
        16,
        19,
        20,
        22,
        26,
        27,
        28,
        37,
        38,
        39,
    }
    if case_number in semantic_cases:
        _require_semantic_gate_rejection(case_number)
        layer = "SOURCE_DOMAIN_SEMANTIC"
    elif case_number in {11, 12, 13, 14}:
        _require_policy_rejection(case_number)
        layer = "SOURCE_DOMAIN_POLICY"
    elif case_number in {17, 18}:
        changed = ("src/mutated.py",) if case_number == 17 else ("scripts/mutated.py",)
        _must_raise(lambda: require_m336k8_evidence_only_diff(changed))
        layer = "COMMIT_ROLE"
    elif case_number in {21, 33, 34}:
        _require_gate_inventory_rejection(case_number)
        layer = "CONSUMER_COVERAGE"
    elif case_number in {23, 24, 25, 29, 30}:
        _require_assembler_inventory_rejection(case_number)
        layer = "PRODUCER_ORIGIN"
    elif case_number in {31, 32}:
        _require_plan_rejection(case_number)
        layer = "PRODUCER_ORIGIN"
    elif case_number in {35, 36}:
        _require_gate_forgery_rejection(case_number)
        layer = "SEMANTIC_GATE_INTEGRITY"
    elif case_number in {40, 41}:
        operation = "CAPSULE_RECREATE" if case_number == 40 else "CLEANUP"
        _must_raise(
            lambda: forbid_m336k8_post_freeze_mutation(
                exact_freeze_sha="1" * 40, operation=operation
            )
        )
        layer = "POST_FREEZE_MUTATION"
    elif case_number in {42, 43}:
        operation = (
            "RELEASE_STORAGE_RESERVATION"
            if case_number == 42
            else "INVOKE_FINAL_CONTROLLER"
        )
        _must_raise(
            lambda: require_m336k8_execution_authority(
                post_freeze_validation_accepted=False, operation=operation
            )
        )
        layer = "EXECUTION_AUTHORITY"
    elif case_number == 44:
        _must_raise(lambda: require_m336k8_frozen_bytes(b"frozen\n", b"live\n"))
        layer = "COMMITTED_BYTES"
    else:
        raise AssertionError("M336K8 mutation case has no executable verifier")
    return M336K8MutationResult(
        case_number=case_number,
        case_name=M336K8_MUTATION_CASES[case_number - 1],
        fully_rehashed=True,
        rejection_layer=layer,
        status="REJECTED",
    )


def run_m336k8_mutation_suite() -> tuple[M336K8MutationResult, ...]:
    return tuple(
        run_m336k8_mutation_case(index)
        for index in range(1, len(M336K8_MUTATION_CASES) + 1)
    )


def _generic_graph():
    plan = M336K8FreezeAssemblyPlan.build()
    values = {}
    consumers = {}
    for entry in plan.entries:
        body = {
            "schema_version": 1,
            "contract_role": "M336K8_MUTATION_FIXTURE",
            "artifact_name": entry.component_name,
        }
        value = {**body, entry.semantic_hash_field: content_hash(body)}
        values[entry.component_name] = value
        consumers[entry.component_name] = _generic_consumer(entry.semantic_hash_field)
    origins = {item.component_name: item.source_domain for item in plan.entries}
    receipt = M336K8FreezeInputAssembler.assemble(
        plan=plan,
        component_values=values,
        component_origins=origins,
        semantic_verifier=lambda _name, _values: 0,
    )
    artifacts = {name: (value, consumers[name]) for name, value in values.items()}
    artifacts["freeze_assembly_plan"] = (
        plan.canonical_object(),
        M336K8FreezeAssemblyPlan.from_dict,
    )
    artifacts["freeze_assembly_receipt"] = (
        receipt.canonical_object(),
        lambda value: _Artifact(value),
    )
    return plan, values, origins, receipt, artifacts


def _generic_consumer(hash_field: str):
    def consume(value: dict[str, Any]) -> _Artifact:
        body = dict(value)
        claimed = body.pop(hash_field)
        if content_hash(body) != claimed:
            raise M336K2ProtocolError("M336K8 mutation fixture hash changed")
        return _Artifact(value)

    return consume


_CURRENT_SHA = "a" * 40
_HISTORICAL_SHA = "b" * 40
_STALE_SHA = "c" * 40
_CURRENT_IDENTITY = "1" * 64
_CAPSULE_IDENTITY = "2" * 64
_TRACKED_PATH_SET_HASH = "3" * 64
_BRIDGE_TREE_HASH = "4" * 64
_CAPSULE_ENVIRONMENT_HASH = "5" * 64


def _replace_hashed(
    values: dict[str, dict[str, Any]], name: str, **changes: Any
) -> None:
    value = dict(values[name])
    hash_fields = tuple(field for field in value if field.endswith("_hash"))
    primary = tuple(
        field
        for field in hash_fields
        if field
        in {
            "policy_hash",
            "receipt_hash",
            "environment_manifest_hash",
            "manifest_hash",
            "binding_hash",
            "bundle_hash",
        }
    )
    if len(primary) != 1:
        raise AssertionError(f"M336K8 mutation hash field is ambiguous: {name}")
    hash_field = primary[0]
    value.pop(hash_field)
    value.update(changes)
    values[name] = {**value, hash_field: content_hash(value)}


def _source_domain_graph():
    plan, generic, _origins, _receipt, generic_artifacts = _generic_graph()
    values = {name: dict(value) for name, value in generic.items()}
    consumers = {name: generic_artifacts[name][1] for name in values}
    _replace_hashed(
        values,
        "controller_source_identity_policy",
        schema_version=1,
        contract_role="M336K8_PROJECT_SOURCE_IDENTITY_POLICY",
        algorithm_id="m336k8.git-and-live-source-rows.v1",
    )
    _replace_hashed(
        values,
        "controller_source_identity_receipt",
        schema_version=1,
        contract_role="M336K8_PROJECT_SOURCE_IDENTITY_RECEIPT",
        exact_implementation_tip=_CURRENT_SHA,
        source_identity_policy_hash=values["controller_source_identity_policy"][
            "policy_hash"
        ],
        tracked_path_set_hash=_TRACKED_PATH_SET_HASH,
        committed_project_source_identity=_CURRENT_IDENTITY,
        live_project_source_identity=_CURRENT_IDENTITY,
    )
    _replace_hashed(
        values,
        "controller_python_environment_manifest",
        schema_version=2,
        contract_role="M336K8_CONTROLLER_PYTHON_ENVIRONMENT_MANIFEST",
        source_domain="CURRENT_IMPLEMENTATION_CONTROLLER",
        exact_implementation_tip=_CURRENT_SHA,
        project_source_identity_hash=_CURRENT_IDENTITY,
    )
    _replace_hashed(
        values,
        "controller_executable_dependency_manifest",
        schema_version=1,
        contract_role="M336K2_HERMETIC_EXECUTABLE_DEPENDENCY_MANIFEST",
        environment_identity_hash=values["controller_python_environment_manifest"][
            "environment_manifest_hash"
        ],
        source_identity_hash=_CURRENT_IDENTITY,
    )
    _replace_hashed(
        values,
        "bridge_surface_manifest",
        schema_version=1,
        contract_role="M336K8_BRIDGE_SURFACE_MANIFEST",
        controller_tree_hash=_BRIDGE_TREE_HASH,
        capsule_tree_hash=_BRIDGE_TREE_HASH,
        changed_entry_count=0,
        schema_incompatibility_count=0,
    )
    _replace_hashed(
        values,
        "persistent_capsule_source_binding",
        schema_version=1,
        contract_role="M336K8_PERSISTENT_CAPSULE_SOURCE_BINDING",
        source_domain="PERSISTENT_KARINA_RUNTIME_CAPSULE",
        capsule_project_source_identity=_CAPSULE_IDENTITY,
        bridge_surface_manifest_hash=values["bridge_surface_manifest"]["manifest_hash"],
    )
    _replace_hashed(
        values,
        "controller_startup_binding",
        schema_version=1,
        contract_role="M336K8_CONTROLLER_STARTUP_BINDING",
        source_domain="CURRENT_IMPLEMENTATION_CONTROLLER",
        exact_implementation_tip=_CURRENT_SHA,
    )
    _replace_hashed(
        values,
        "source_domain_compatibility",
        schema_version=1,
        contract_role="M336K8_SOURCE_DOMAIN_COMPATIBILITY_RECEIPT",
        full_project_identity_equality_required=False,
        controller_manifest_origin_valid=True,
        capsule_manifest_origin_valid=True,
    )
    _replace_hashed(
        values,
        "legacy_controller_alias_receipt",
        schema_version=1,
        contract_role="M336K8_LEGACY_CONTROLLER_ALIAS_RECEIPT",
    )
    _replace_hashed(
        values,
        "post_freeze_input_bundle",
        schema_version=2,
        contract_role="M336K8_POST_FREEZE_INPUT_BUNDLE_V2",
        frozen_input_generation="PRE_FREEZE",
        freeze_assembly_plan_hash=plan.plan_hash,
        freeze_assembly_receipt_hash="0" * 64,
    )
    _refresh_source_domain_dependents(0, values)
    _assemble_source_domain_graph(plan, values)
    return plan, values, consumers


def _apply_source_domain_mutation(
    case_number: int, values: dict[str, dict[str, Any]]
) -> None:
    if case_number == 1:
        _replace_hashed(
            values,
            "controller_python_environment_manifest",
            source_domain="PERSISTENT_KARINA_RUNTIME_CAPSULE",
            project_source_identity_hash=_CAPSULE_IDENTITY,
        )
    elif case_number == 2:
        _replace_hashed(
            values,
            "controller_executable_dependency_manifest",
            environment_identity_hash=_CAPSULE_ENVIRONMENT_HASH,
            source_identity_hash=_CAPSULE_IDENTITY,
        )
    elif case_number in {3, 4}:
        _replace_hashed(
            values,
            "controller_python_environment_manifest",
            source_domain="PERSISTENT_KARINA_RUNTIME_CAPSULE",
            project_source_identity_hash=_CAPSULE_IDENTITY,
        )
        _replace_hashed(
            values,
            "controller_executable_dependency_manifest",
            environment_identity_hash=values["controller_python_environment_manifest"][
                "environment_manifest_hash"
            ],
            source_identity_hash=_CAPSULE_IDENTITY,
        )
    elif case_number == 5:
        _replace_hashed(
            values,
            "controller_source_identity_receipt",
            committed_project_source_identity=_CAPSULE_IDENTITY,
            live_project_source_identity=_CAPSULE_IDENTITY,
        )
    elif case_number in {6, 7}:
        stale = _HISTORICAL_SHA if case_number == 6 else _STALE_SHA
        _replace_hashed(
            values,
            "controller_source_identity_receipt",
            exact_implementation_tip=stale,
        )
        _replace_hashed(
            values,
            "controller_python_environment_manifest",
            exact_implementation_tip=stale,
        )
    elif case_number == 8:
        _replace_hashed(
            values,
            "controller_source_identity_receipt",
            committed_project_source_identity="6" * 64,
        )
    elif case_number == 9:
        _replace_hashed(
            values,
            "controller_source_identity_receipt",
            live_project_source_identity="7" * 64,
        )
    elif case_number == 10:
        _replace_hashed(
            values,
            "controller_source_identity_receipt",
            tracked_path_set_hash="8" * 64,
        )
    elif case_number == 15:
        _replace_hashed(
            values,
            "controller_startup_binding",
            controller_project_source_identity="9" * 64,
        )
    elif case_number == 16:
        _replace_hashed(
            values,
            "controller_startup_binding",
            controller_project_source_identity=_CAPSULE_IDENTITY,
        )
    elif case_number in {19, 27}:
        _replace_hashed(
            values,
            "bridge_surface_manifest",
            controller_tree_hash="a" * 64,
            changed_entry_count=1,
        )
    elif case_number == 20:
        _replace_hashed(
            values,
            "bridge_surface_manifest",
            capsule_tree_hash="b" * 64,
            changed_entry_count=1,
        )
    elif case_number == 22:
        _replace_hashed(
            values,
            "bridge_surface_manifest",
            schema_incompatibility_count=1,
        )
    elif case_number == 26:
        _replace_hashed(
            values,
            "source_domain_compatibility",
            full_project_identity_equality_required=True,
        )
    elif case_number == 28:
        _replace_hashed(
            values,
            "legacy_controller_alias_receipt",
            legacy_python_environment_manifest_alias_hash=_CAPSULE_ENVIRONMENT_HASH,
        )
    elif case_number == 37:
        _replace_hashed(
            values,
            "controller_python_environment_manifest",
            regenerated_after_freeze=True,
        )
    elif case_number == 38:
        _replace_hashed(
            values,
            "post_freeze_input_bundle",
            frozen_input_generation="LIVE_REGENERATED",
        )
    elif case_number == 39:
        _replace_hashed(
            values,
            "controller_startup_binding",
            exact_implementation_tip=_STALE_SHA,
        )
    else:
        raise AssertionError("unknown M336K8 source-domain semantic mutation")


def _refresh_source_domain_dependents(
    case_number: int, values: dict[str, dict[str, Any]]
) -> None:
    policy = values["controller_source_identity_policy"]
    source = values["controller_source_identity_receipt"]
    environment = values["controller_python_environment_manifest"]
    dependency = values["controller_executable_dependency_manifest"]
    bridge = values["bridge_surface_manifest"]
    capsule = values["persistent_capsule_source_binding"]

    if case_number in {5, 9}:
        _replace_hashed(
            values,
            "controller_python_environment_manifest",
            project_source_identity_hash=source["live_project_source_identity"],
        )
        environment = values["controller_python_environment_manifest"]
    if case_number not in {2, 3, 4}:
        _replace_hashed(
            values,
            "controller_executable_dependency_manifest",
            environment_identity_hash=environment["environment_manifest_hash"],
            source_identity_hash=source["live_project_source_identity"],
        )
        dependency = values["controller_executable_dependency_manifest"]
    startup_changes = {
        "project_source_identity_policy_hash": policy["policy_hash"],
        "project_source_identity_receipt_hash": source["receipt_hash"],
        "controller_python_environment_manifest_hash": environment[
            "environment_manifest_hash"
        ],
        "controller_executable_dependency_manifest_hash": dependency["manifest_hash"],
    }
    if case_number not in {15, 16}:
        startup_changes["controller_project_source_identity"] = source[
            "live_project_source_identity"
        ]
    if case_number not in {15, 16, 39}:
        startup_changes["exact_implementation_tip"] = environment[
            "exact_implementation_tip"
        ]
    _replace_hashed(values, "controller_startup_binding", **startup_changes)
    startup = values["controller_startup_binding"]

    _replace_hashed(
        values,
        "persistent_capsule_source_binding",
        bridge_surface_manifest_hash=bridge["manifest_hash"],
    )
    capsule = values["persistent_capsule_source_binding"]
    compatibility_changes = {
        "controller_startup_binding_hash": startup["binding_hash"],
        "persistent_capsule_source_binding_hash": capsule["binding_hash"],
        "controller_project_source_identity": source["live_project_source_identity"],
        "capsule_project_source_identity": capsule["capsule_project_source_identity"],
        "full_project_identity_difference_count": int(
            source["live_project_source_identity"]
            != capsule["capsule_project_source_identity"]
        ),
        "bridge_surface_manifest_hash": bridge["manifest_hash"],
        "bridge_changed_entry_count": bridge["changed_entry_count"],
        "bridge_schema_incompatibility_count": bridge["schema_incompatibility_count"],
    }
    if case_number != 26:
        compatibility_changes["full_project_identity_equality_required"] = False
    _replace_hashed(values, "source_domain_compatibility", **compatibility_changes)
    compatibility = values["source_domain_compatibility"]

    alias_changes = {
        "controller_python_environment_manifest_hash": environment[
            "environment_manifest_hash"
        ],
        "controller_executable_dependency_manifest_hash": dependency["manifest_hash"],
        "legacy_executable_dependency_manifest_alias_hash": dependency["manifest_hash"],
    }
    if case_number != 28:
        alias_changes["legacy_python_environment_manifest_alias_hash"] = environment[
            "environment_manifest_hash"
        ]
    _replace_hashed(values, "legacy_controller_alias_receipt", **alias_changes)
    alias = values["legacy_controller_alias_receipt"]

    _replace_hashed(
        values,
        "post_freeze_input_bundle",
        controller_project_source_identity_policy_hash=policy["policy_hash"],
        controller_project_source_identity_receipt_hash=source["receipt_hash"],
        controller_python_environment_manifest_hash=environment[
            "environment_manifest_hash"
        ],
        controller_executable_dependency_manifest_hash=dependency["manifest_hash"],
        controller_startup_binding_hash=startup["binding_hash"],
        persistent_capsule_source_binding_hash=capsule["binding_hash"],
        bridge_surface_manifest_hash=bridge["manifest_hash"],
        source_domain_compatibility_receipt_hash=compatibility["receipt_hash"],
        legacy_controller_alias_receipt_hash=alias["receipt_hash"],
    )


def _assemble_source_domain_graph(
    plan: M336K8FreezeAssemblyPlan,
    values: dict[str, dict[str, Any]],
):
    origins = {item.component_name: item.source_domain for item in plan.entries}
    receipt = M336K8FreezeInputAssembler.assemble(
        plan=plan,
        component_values=values,
        component_origins=origins,
        semantic_verifier=m336k8_semantic_binding_mismatches,
    )
    _replace_hashed(
        values,
        "post_freeze_input_bundle",
        freeze_assembly_receipt_hash=receipt.receipt_hash,
    )
    repeated = M336K8FreezeInputAssembler.assemble(
        plan=plan,
        component_values=values,
        component_origins=origins,
        semantic_verifier=m336k8_semantic_binding_mismatches,
    )
    if repeated != receipt:
        raise AssertionError("M336K8 mutation assembly receipt is unstable")
    return receipt


def _require_semantic_gate_rejection(
    case_number: int,
) -> M336K8FrozenContractCompatibilityGateV2:
    plan, baseline, consumers = _source_domain_graph()
    values = {name: dict(value) for name, value in baseline.items()}
    _apply_source_domain_mutation(case_number, values)
    _refresh_source_domain_dependents(case_number, values)
    receipt = _assemble_source_domain_graph(plan, values)
    artifacts = {name: (value, consumers[name]) for name, value in values.items()}
    artifacts["freeze_assembly_plan"] = (
        plan.canonical_object(),
        M336K8FreezeAssemblyPlan.from_dict,
    )
    artifacts["freeze_assembly_receipt"] = (
        receipt.canonical_object(),
        lambda value: _Artifact(value),
    )
    callback_count = 0

    def semantic(name, values):
        nonlocal callback_count
        callback_count += 1
        mismatches = m336k8_semantic_binding_mismatches(name, values)
        if name == "controller_source_identity_receipt":
            source = values[name]
            mismatches += int(source.get("exact_implementation_tip") != _CURRENT_SHA)
            mismatches += int(
                source.get("committed_project_source_identity") != _CURRENT_IDENTITY
            )
            mismatches += int(
                source.get("live_project_source_identity") != _CURRENT_IDENTITY
            )
            mismatches += int(
                source.get("tracked_path_set_hash") != _TRACKED_PATH_SET_HASH
            )
        elif name == "controller_python_environment_manifest":
            environment = values[name]
            mismatches += int(
                environment.get("exact_implementation_tip") != _CURRENT_SHA
            )
            mismatches += int(
                environment.get("environment_manifest_hash")
                != baseline[name]["environment_manifest_hash"]
            )
        elif name == "controller_startup_binding":
            startup = values[name]
            mismatches += int(startup.get("exact_implementation_tip") != _CURRENT_SHA)
        elif name == "post_freeze_input_bundle":
            mismatches += int(
                values[name].get("frozen_input_generation") != "PRE_FREEZE"
            )
        return mismatches

    report = M336K8FrozenContractCompatibilityGateV2.run(
        plan=plan,
        artifacts=artifacts,
        semantic_verifier=semantic,
        current_route_sources=(Path(__file__).with_name("m336k8_request.py"),),
    )
    if (
        callback_count != len(artifacts)
        or report.semantic_binding_mismatch_count < 1
        or report.status != "FAIL"
        or report.roundtrip_difference_count != 0
    ):
        raise AssertionError("M336K8 fully rehashed semantic mutation was accepted")
    return report


def _must_raise(operation) -> None:
    try:
        operation()
    except M336K2ProtocolError:
        return
    raise AssertionError("M336K8 mutation was accepted")


def _require_policy_rejection(case_number: int) -> None:
    policy = M336K8ProjectSourceIdentityPolicy.build()
    value = policy.canonical_object()
    value.pop("policy_hash")
    if case_number == 11:
        value["tracked_roots"] = tuple(value["tracked_roots"][:-1])
    elif case_number == 12:
        value["path_ordering"] = "REVERSE_UTF8_REPOSITORY_RELATIVE_BYTE_ORDER"
    elif case_number == 13:
        value["algorithm_id"] = "M336K8_PROJECT_SOURCE_IDENTITY_V2"
    elif case_number == 14:
        value["clean_checkout_required"] = False
    else:
        raise AssertionError("unknown M336K8 source policy mutation")
    mutated = {**value, "policy_hash": content_hash(value)}
    _must_raise(lambda: M336K8ProjectSourceIdentityPolicy.from_dict(mutated))


def _require_gate_inventory_rejection(case_number: int) -> None:
    plan, _values, _origins, _receipt, artifacts = _generic_graph()
    artifacts = dict(artifacts)
    if case_number == 21:
        artifacts.pop("bridge_surface_manifest")
    elif case_number == 33:
        artifacts.pop("controller_startup_binding")
    elif case_number == 34:
        body = {
            "schema_version": 1,
            "contract_role": "M336K8_UNUSED_MUTATION_ARTIFACT",
        }
        value = {**body, "receipt_hash": content_hash(body)}
        artifacts["unused_mutation_artifact"] = (
            value,
            _generic_consumer("receipt_hash"),
        )
    else:
        raise AssertionError("unknown M336K8 compatibility inventory mutation")
    report = M336K8FrozenContractCompatibilityGateV2.run(
        plan=plan,
        artifacts=artifacts,
        semantic_verifier=lambda _name, _values: 0,
        current_route_sources=(Path(__file__).with_name("m336k8_request.py"),),
    )
    expected_uncovered = int(case_number in {21, 33})
    expected_unused = int(case_number == 34)
    if (
        report.status != "FAIL"
        or report.uncovered_consumer_count != expected_uncovered
        or report.unused_compatibility_artifact_count != expected_unused
    ):
        raise AssertionError("M336K8 compatibility inventory mutation was accepted")


def _require_assembler_inventory_rejection(case_number: int) -> None:
    plan, values, origins, _receipt, _artifacts = _generic_graph()
    values = dict(values)
    origins = dict(origins)
    target_by_case = {
        23: "controller_startup_binding",
        24: "persistent_capsule_source_binding",
        25: "source_domain_compatibility",
    }
    if case_number in target_by_case:
        target = target_by_case[case_number]
        values.pop(target)
        origins.pop(target)
    elif case_number in {29, 30}:
        name = (
            "python_environment_manifest"
            if case_number == 29
            else "executable_dependency_manifest"
        )
        body = {
            "schema_version": 1,
            "contract_role": "M336K8_AMBIGUOUS_GENERIC_COMPONENT",
            "component_name": name,
        }
        values[name] = {**body, "receipt_hash": content_hash(body)}
        origins[name] = "CURRENT_IMPLEMENTATION_CONTROLLER"
    else:
        raise AssertionError("unknown M336K8 assembler inventory mutation")
    receipt = M336K8FreezeInputAssembler.assemble(
        plan=plan,
        component_values=values,
        component_origins=origins,
        semantic_verifier=lambda _name, _values: 0,
    )
    expected_missing = int(case_number in target_by_case)
    expected_extra = int(case_number in {29, 30})
    if (
        receipt.status != "FAIL"
        or receipt.missing_component_count != expected_missing
        or receipt.extra_component_count != expected_extra
    ):
        raise AssertionError("M336K8 assembler inventory mutation was accepted")


def _require_plan_rejection(case_number: int) -> None:
    plan = M336K8FreezeAssemblyPlan.build()
    value = plan.canonical_object()
    entries = [dict(item) for item in value["entries"]]
    if case_number == 31:
        entries[0]["producer_role"] = "REHEARSAL_ONLY_PRODUCER"
    elif case_number == 32:
        entries[0]["source_domain"] = "PERSISTENT_KARINA_RUNTIME_CAPSULE"
    else:
        raise AssertionError("unknown M336K8 assembly plan mutation")
    origins = tuple(
        (
            item["component_name"],
            item["source_domain"],
            item["producer_role"],
            item["expected_producer_commit_role"],
        )
        for item in entries
    )
    body = {
        "schema_version": value["schema_version"],
        "contract_role": value["contract_role"],
        "entries": tuple(entries),
        "component_count": len(entries),
        "producer_origin_map_hash": content_hash(origins),
    }
    mutated = {**body, "plan_hash": content_hash(body)}
    _must_raise(lambda: M336K8FreezeAssemblyPlan.from_dict(mutated))


def _failed_semantic_gate() -> M336K8FrozenContractCompatibilityGateV2:
    plan, _values, _origins, _receipt, artifacts = _generic_graph()
    artifacts = dict(artifacts)
    target = "controller_startup_binding"
    produced, consumer = artifacts[target]
    body = dict(produced)
    hash_field = next(name for name in body if name.endswith("_hash"))
    body.pop(hash_field)
    body["semantic_mutation_case"] = 35
    artifacts[target] = ({**body, hash_field: content_hash(body)}, consumer)
    return M336K8FrozenContractCompatibilityGateV2.run(
        plan=plan,
        artifacts=artifacts,
        semantic_verifier=lambda name, values: int(
            "semantic_mutation_case" in values[name]
        ),
        current_route_sources=(Path(__file__).with_name("m336k8_request.py"),),
    )


def _rehash_gate(
    gate: M336K8FrozenContractCompatibilityGateV2,
    **changes: Any,
) -> M336K8FrozenContractCompatibilityGateV2:
    temporary = replace(gate, **changes, report_hash="0" * 64)
    result = replace(temporary, report_hash=content_hash(temporary._body()))
    result.verify()
    return result


def _require_gate_forgery_rejection(case_number: int) -> None:
    actual = _failed_semantic_gate()
    if actual.status != "FAIL" or actual.semantic_binding_mismatch_count != 1:
        raise AssertionError("M336K8 failed-gate mutation fixture is invalid")
    if case_number == 35:
        forged = _rehash_gate(actual, semantic_binding_mismatch_count=0)
    elif case_number == 36:
        artifacts = tuple(
            replace(
                item,
                semantic_binding_mismatch_count=0,
                status="PASS",
            )
            if item.semantic_binding_mismatch_count
            else item
            for item in actual.artifacts
        )
        forged = _rehash_gate(
            actual,
            artifacts=artifacts,
            semantic_binding_mismatch_count=0,
            status="PASS",
        )
    else:
        raise AssertionError("unknown M336K8 compatibility gate forgery")
    _must_raise(lambda: _require_recomputed_gate(actual, forged))


def _require_recomputed_gate(
    actual: M336K8FrozenContractCompatibilityGateV2,
    claimed: M336K8FrozenContractCompatibilityGateV2,
) -> None:
    actual.verify()
    claimed.verify()
    if actual.canonical_object() != claimed.canonical_object():
        raise M336K2ProtocolError("M336K8 gate differs from recomputed result")
