from __future__ import annotations

import ast
import inspect
import json
import shutil
import subprocess
import textwrap
from dataclasses import fields
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K8_ACQUISITION_RUN_ID,
    M336K8_EVALUATOR_RUN_ID,
    M336K8_PROTOCOL_RUN_ID,
    M336K8_ROUTE_VERSION,
    M336K8_SELECTOR_RUN_ID,
    build_m336k8_official_identity_bundle,
)
from ai_brain.stage3.acquisition.m336k8_contracts import (
    M336K8_BRIDGE_PATHS,
    M336K8_POST_FREEZE_CONSUMED_COMPONENTS,
    M336K8BridgeSurfaceManifest,
    M336K8ControllerStartupBinding,
    M336K8FreezeAssemblyPlan,
    M336K8FreezeAssemblyReceipt,
    M336K8FrozenContractCompatibilityGateV2,
    M336K8LegacyControllerAliasReceipt,
    M336K8PersistentCapsuleSourceBinding,
    M336K8PostFreezeInputBundleV2,
    M336K8ProjectSourceIdentityPolicy,
    M336K8ProjectSourceIdentityReceipt,
    M336K8SourceDomainCompatibilityReceipt,
    _source_static_counts,
    build_m336k8_bridge_surface_manifest,
    build_m336k8_project_source_identity_receipt,
)
from ai_brain.stage3.acquisition.m336k8_mutations import (
    M336K8_MUTATION_CASES,
    _require_semantic_gate_rejection,
    run_m336k8_mutation_case,
)

H = "1" * 64
H2 = "2" * 64
SHA = "a" * 40


def _git() -> Path:
    executable = shutil.which("git")
    assert executable is not None
    return Path(executable).resolve(strict=True)


def _run_git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        (_git(), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _controller() -> M336K8ControllerStartupBinding:
    return M336K8ControllerStartupBinding.build(
        exact_implementation_tip=SHA,
        project_source_identity_policy_hash=H,
        project_source_identity_receipt_hash=H,
        controller_project_source_identity=H,
        controller_python_environment_manifest_hash=H,
        controller_executable_dependency_manifest_hash=H,
        startup_policy_hash=H,
        sanitized_environment_policy_hash=H,
        startup_receipt_schema_hash=H,
        bootstrap_source_hash=H,
        windows_launcher_source_hash=H,
        validate_only_target_source_hash=H,
        final_controller_target_source_hash=H,
    )


def _capsule(bridge_hash: str) -> M336K8PersistentCapsuleSourceBinding:
    return M336K8PersistentCapsuleSourceBinding.build(
        persistent_capsule_binding_set_hash=H,
        capsule_implementation_tip=SHA,
        capsule_project_source_identity=H2,
        capsule_python_environment_manifest_hash=H,
        capsule_executable_dependency_manifest_hash=H,
        capsule_identity_hash=H,
        capsule_content_manifest_hash=H,
        capsule_lifecycle_policy_hash=H,
        capsule_liveness_receipt_hash=H,
        persistent_public_receipt_hash=H,
        legacy_public_receipt_hash=H,
        stable_host_identity_hash=H,
        bridge_surface_manifest_hash=bridge_hash,
    )


def _bridge(tmp_path: Path) -> M336K8BridgeSurfaceManifest:
    entries = []
    for _role, relative in M336K8_BRIDGE_PATHS:
        path = tmp_path.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (relative + "\n").encode()
        path.write_bytes(payload)
        entries.append({"relative_path": relative, "bytes_hash": bytes_hash(payload)})
    return build_m336k8_bridge_surface_manifest(
        repository=tmp_path,
        capsule_content_manifest={"entries": entries},
    )


def test_m336k8_official_identity_namespace_is_exact() -> None:
    bundle = build_m336k8_official_identity_bundle(
        route_registry_hash=H,
        route_manifest_hash=H,
        acquisition_policy_hash=H,
        selector_policy_hash=H,
        evaluator_policy_hash=H,
    )

    assert bundle.route_version.value == M336K8_ROUTE_VERSION
    assert bundle.protocol_run_id.value == M336K8_PROTOCOL_RUN_ID
    assert bundle.acquisition_run_id.value == M336K8_ACQUISITION_RUN_ID
    assert bundle.selector_run_id.value == M336K8_SELECTOR_RUN_ID
    assert bundle.evaluator_run_id.value == M336K8_EVALUATOR_RUN_ID


def test_m336k8_source_identity_binds_committed_and_live_bytes(tmp_path: Path) -> None:
    _run_git(tmp_path, "init")
    _run_git(tmp_path, "config", "user.name", "M336K8 Test")
    _run_git(tmp_path, "config", "user.email", "m336k8@example.invalid")
    for relative in ("src/a.py", "scripts/a.py", "pyproject.toml", "uv.lock"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative + "\n", encoding="utf-8", newline="\n")
    _run_git(tmp_path, "add", ".")
    _run_git(tmp_path, "commit", "-m", "source identity fixture")
    exact_tip = _run_git(tmp_path, "rev-parse", "HEAD")
    policy = M336K8ProjectSourceIdentityPolicy.build()

    clean = build_m336k8_project_source_identity_receipt(
        repository=tmp_path,
        git_executable=_git(),
        exact_implementation_tip=exact_tip,
        policy=policy,
    )
    assert clean.status == "PASS"
    assert clean.identity_difference_count == 0
    assert clean.path_set_difference_count == 0
    assert clean.worktree_clean is True

    (tmp_path / "src/a.py").write_text("changed\n", encoding="utf-8", newline="\n")
    dirty = build_m336k8_project_source_identity_receipt(
        repository=tmp_path,
        git_executable=_git(),
        exact_implementation_tip=exact_tip,
        policy=policy,
    )
    assert dirty.status == "FAIL"
    assert dirty.identity_difference_count == 1
    assert dirty.worktree_clean is False


def test_m336k8_bridge_and_distinct_full_project_identities_pass(
    tmp_path: Path,
) -> None:
    bridge = _bridge(tmp_path)
    compatibility = M336K8SourceDomainCompatibilityReceipt.build(
        _controller(), _capsule(bridge.manifest_hash), bridge
    )

    assert bridge.entry_count == len(M336K8_BRIDGE_PATHS)
    assert bridge.changed_entry_count == 0
    assert compatibility.full_project_identity_equality_required is False
    assert compatibility.full_project_identity_difference_count == 1
    assert compatibility.status == "PASS"


def test_m336k8_freeze_plan_has_exact_typed_inventory() -> None:
    plan = M336K8FreezeAssemblyPlan.build()
    names = tuple(item.component_name for item in plan.entries)

    assert plan.component_count == 21
    assert len(M336K8_POST_FREEZE_CONSUMED_COMPONENTS) == 24
    assert "python_environment_manifest" not in names
    assert "executable_dependency_manifest" not in names
    assert "controller_python_environment_manifest" in names
    assert "persistent_capsule_python_environment_manifest" in names


def test_m336k8_schema_field_sets_match_typed_contracts() -> None:
    schema_path = Path(__file__).parents[1] / (
        "schemas/m336k8_source_domain_contracts.schema.json"
    )
    definitions = json.loads(schema_path.read_text(encoding="utf-8"))["$defs"]
    classes = {
        "sourceIdentityPolicy": M336K8ProjectSourceIdentityPolicy,
        "sourceIdentityReceipt": M336K8ProjectSourceIdentityReceipt,
        "controllerStartupBinding": M336K8ControllerStartupBinding,
        "capsuleSourceBinding": M336K8PersistentCapsuleSourceBinding,
        "bridgeSurface": M336K8BridgeSurfaceManifest,
        "sourceDomainCompatibility": M336K8SourceDomainCompatibilityReceipt,
        "assemblyPlan": M336K8FreezeAssemblyPlan,
        "assemblyReceipt": M336K8FreezeAssemblyReceipt,
        "legacyControllerAlias": M336K8LegacyControllerAliasReceipt,
        "postFreezeBundle": M336K8PostFreezeInputBundleV2,
        "compatibilityGate": M336K8FrozenContractCompatibilityGateV2,
    }

    for definition, contract in classes.items():
        expected = {field.name for field in fields(contract)}
        assert set(definitions[definition]["required"]) == expected
        assert set(definitions[definition]["properties"]) == expected


def test_m336k8_current_validator_has_no_phase_defaults_or_identity_equality() -> None:
    request_source = Path(__file__).parents[1] / (
        "src/ai_brain/stage3/acquisition/m336k8_request.py"
    )

    assert _source_static_counts((request_source,)) == (0, 0, 0)


def test_m336k8_gate_executes_semantic_verifier() -> None:
    source = inspect.getsource(M336K8FrozenContractCompatibilityGateV2.run)
    tree = ast.parse(textwrap.dedent(source))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "semantic_verifier"
    ]

    assert calls


def test_m336k8_fully_rehashed_wrong_domain_fails_semantically() -> None:
    report = _require_semantic_gate_rejection(4)

    assert report.roundtrip_difference_count == 0
    assert report.semantic_binding_mismatch_count > 0
    assert report.status == "FAIL"


@pytest.mark.parametrize("case_number", range(1, len(M336K8_MUTATION_CASES) + 1))
def test_m336k8_closed_under_rehash_mutation(case_number: int) -> None:
    result = run_m336k8_mutation_case(case_number)

    assert result.fully_rehashed is True
    assert result.status == "REJECTED"
    assert result.rejection_layer != "HASH_ONLY"
