"""Build exact controller/capsule source-domain contracts for M-33.6k.8."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_execution import (
    build_m336k2_executable_dependency_manifest,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k7_contracts import (
    M336K7PersistentCapsuleBindingSet,
)
from ai_brain.stage3.acquisition.m336k8_contracts import (
    CURRENT_IMPLEMENTATION_CONTROLLER,
    M336K8ControllerStartupBinding,
    M336K8FreezeAssemblyPlan,
    M336K8LegacyControllerAliasReceipt,
    M336K8PersistentCapsuleSourceBinding,
    M336K8ProjectSourceIdentityPolicy,
    M336K8SourceDomainCompatibilityReceipt,
    build_m336k8_bridge_surface_manifest,
    build_m336k8_project_source_identity_receipt,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request.resolve(strict=True))
    expected = {
        "repository",
        "git_executable",
        "python_executable",
        "exact_implementation_tip",
        "startup_components",
        "capsule_binding_set",
        "capsule_content_manifest",
        "capsule_lifecycle_policy",
        "capsule_liveness_receipt",
        "persistent_public_receipt",
        "legacy_public_receipt",
        "persistent_capsule_python_environment_manifest",
        "persistent_capsule_executable_dependency_manifest",
        "stable_host_identity_receipt",
        "executable_handles",
        "output",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K8 source-domain request fields changed")
    root = Path(request["repository"]).resolve(strict=True)
    git = Path(request["git_executable"]).resolve(strict=True)
    python = Path(request["python_executable"]).absolute()
    implementation = request["exact_implementation_tip"]
    startup_root = Path(request["startup_components"]).resolve(strict=True)
    output = Path(request["output"]).resolve(strict=False)
    if output.exists() or output.is_relative_to(root):
        raise M336K2ProtocolError("M336K8 source-domain output is stale or public")

    policy = M336K8ProjectSourceIdentityPolicy.build()
    source_identity = build_m336k8_project_source_identity_receipt(
        repository=root,
        git_executable=git,
        exact_implementation_tip=implementation,
        policy=policy,
    )
    if source_identity.status != "PASS":
        raise M336K2ProtocolError("M336K8 current source identity did not pass")
    startup_policy = _verified(
        startup_root / "python_startup_policy.json", "policy_hash"
    )
    sanitized = _verified(
        startup_root / "sanitized_environment_policy.json", "receipt_hash"
    )
    bootstrap = _verified(
        startup_root / "python_startup_bootstrap.json", "receipt_hash"
    )
    launcher = _verified(startup_root / "windows_python_launcher.json", "receipt_hash")
    startup_schema = _verified(
        startup_root / "startup_receipt_schema.json", "schema_hash"
    )
    environment_body = {
        "schema_version": 2,
        "contract_role": "M336K8_CONTROLLER_PYTHON_ENVIRONMENT_MANIFEST",
        "source_domain": CURRENT_IMPLEMENTATION_CONTROLLER,
        "exact_implementation_tip": implementation,
        "startup_policy_hash": startup_policy["policy_hash"],
        "project_source_identity_policy_hash": policy.policy_hash,
        "project_source_identity_receipt_hash": source_identity.receipt_hash,
        "project_source_identity_hash": source_identity.live_project_source_identity,
        "sanitized_environment_policy_hash": sanitized["receipt_hash"],
        "python_path_inherited": False,
        "python_home_inherited": False,
        "python_user_base_inherited": False,
        "user_site_effective_state_required": True,
        "torch_at_startup_allowed": False,
    }
    environment = {
        **environment_body,
        "environment_manifest_hash": content_hash(environment_body),
    }
    handle_request = request["executable_handles"]
    if type(handle_request) is not dict:
        raise M336K2ProtocolError("M336K8 executable handle map changed")
    executables = {}
    for role, specification in handle_request.items():
        if type(specification) is not dict or set(specification) != {
            "path",
            "version_arguments",
        }:
            raise M336K2ProtocolError("M336K8 executable specification changed")
        if type(specification["version_arguments"]) is not list:
            raise M336K2ProtocolError("M336K8 executable arguments changed")
        executables[role] = (
            Path(specification["path"]).resolve(strict=True),
            tuple(specification["version_arguments"]),
        )
    dependency = build_m336k2_executable_dependency_manifest(
        executables=executables,
        python_invocation_handle=str(python),
        environment_identity_hash=environment["environment_manifest_hash"],
        source_identity_hash=source_identity.live_project_source_identity,
    )
    controller = M336K8ControllerStartupBinding.build(
        exact_implementation_tip=implementation,
        project_source_identity_policy_hash=policy.policy_hash,
        project_source_identity_receipt_hash=source_identity.receipt_hash,
        controller_project_source_identity=source_identity.live_project_source_identity,
        controller_python_environment_manifest_hash=environment[
            "environment_manifest_hash"
        ],
        controller_executable_dependency_manifest_hash=dependency.manifest_hash,
        startup_policy_hash=startup_policy["policy_hash"],
        sanitized_environment_policy_hash=sanitized["receipt_hash"],
        startup_receipt_schema_hash=startup_schema["schema_hash"],
        bootstrap_source_hash=bootstrap["source_bytes_hash"],
        windows_launcher_source_hash=launcher["source_bytes_hash"],
        validate_only_target_source_hash=bytes_hash(
            (root / "scripts/m336k8_run_final_route.py").read_bytes()
        ),
        final_controller_target_source_hash=bytes_hash(
            (root / "scripts/m336k8_run_final_route.py").read_bytes()
        ),
    )

    capsule_binding = M336K7PersistentCapsuleBindingSet.from_dict(
        _object(Path(request["capsule_binding_set"]))
    )
    capsule_content = _verified(
        Path(request["capsule_content_manifest"]), "manifest_hash"
    )
    capsule_lifecycle = _verified(
        Path(request["capsule_lifecycle_policy"]), "policy_hash"
    )
    capsule_liveness = _verified(
        Path(request["capsule_liveness_receipt"]), "receipt_hash"
    )
    persistent_public = _verified(
        Path(request["persistent_public_receipt"]), "receipt_hash"
    )
    legacy_public = _verified(Path(request["legacy_public_receipt"]), "receipt_hash")
    capsule_environment = _verified(
        Path(request["persistent_capsule_python_environment_manifest"]), "identity_hash"
    )
    capsule_dependency = _verified(
        Path(request["persistent_capsule_executable_dependency_manifest"]),
        "manifest_hash",
    )
    stable_host = _verified(
        Path(request["stable_host_identity_receipt"]), "receipt_hash"
    )
    if (
        persistent_public.get("implementation_sha")
        != capsule_binding.implementation_tip
        or persistent_public.get("project_source_identity") is None
        or persistent_public.get("python_environment_manifest_hash")
        != capsule_environment.get("environment_manifest_hash")
        or persistent_public.get("executable_dependency_manifest_hash")
        != capsule_dependency.get("manifest_hash")
        or persistent_public.get("capsule_identity_hash")
        != capsule_binding.capsule_identity_hash
        or persistent_public.get("content_manifest_hash")
        != capsule_content.get("manifest_hash")
        or persistent_public.get("lifecycle_policy_hash")
        != capsule_lifecycle.get("policy_hash")
        or persistent_public.get("legacy_public_receipt_hash")
        != legacy_public.get("receipt_hash")
        or persistent_public.get("stable_host_identity_hash")
        != stable_host.get("receipt_hash")
        or capsule_binding.capsule_liveness_receipt_hash
        != capsule_liveness.get("receipt_hash")
        or capsule_binding.persistent_capsule_public_receipt_hash
        != persistent_public.get("receipt_hash")
    ):
        raise M336K2ProtocolError("M336K8 persistent capsule source inputs diverged")
    bridge = build_m336k8_bridge_surface_manifest(
        repository=root, capsule_content_manifest=capsule_content
    )
    capsule_source = M336K8PersistentCapsuleSourceBinding.build(
        persistent_capsule_binding_set_hash=capsule_binding.binding_set_hash,
        capsule_implementation_tip=capsule_binding.implementation_tip,
        capsule_project_source_identity=persistent_public["project_source_identity"],
        capsule_python_environment_manifest_hash=capsule_environment["identity_hash"],
        capsule_executable_dependency_manifest_hash=capsule_dependency["manifest_hash"],
        capsule_identity_hash=capsule_binding.capsule_identity_hash,
        capsule_content_manifest_hash=capsule_content["manifest_hash"],
        capsule_lifecycle_policy_hash=capsule_lifecycle["policy_hash"],
        capsule_liveness_receipt_hash=capsule_liveness["receipt_hash"],
        persistent_public_receipt_hash=persistent_public["receipt_hash"],
        legacy_public_receipt_hash=legacy_public["receipt_hash"],
        stable_host_identity_hash=stable_host["receipt_hash"],
        bridge_surface_manifest_hash=bridge.manifest_hash,
    )
    compatibility = M336K8SourceDomainCompatibilityReceipt.build(
        controller, capsule_source, bridge
    )
    alias = M336K8LegacyControllerAliasReceipt.build(
        controller_environment=environment,
        legacy_environment=environment,
        controller_dependencies=asdict(dependency),
        legacy_dependencies=asdict(dependency),
    )
    plan = M336K8FreezeAssemblyPlan.build()
    output.mkdir(parents=True)
    values = {
        "controller_source_identity_policy": policy.canonical_object(),
        "controller_source_identity_receipt": source_identity.canonical_object(),
        "controller_python_environment_manifest": environment,
        "controller_executable_dependency_manifest": asdict(dependency),
        "controller_startup_binding": controller.canonical_object(),
        "persistent_capsule_source_binding": capsule_source.canonical_object(),
        "bridge_surface_manifest": bridge.canonical_object(),
        "source_domain_compatibility": compatibility.canonical_object(),
        "legacy_controller_alias_receipt": alias.canonical_object(),
        "freeze_assembly_plan": plan.canonical_object(),
    }
    for name, value in values.items():
        _write(output / f"{name}.json", value)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K8_SOURCE_DOMAIN_BUILD_RECEIPT",
        "exact_implementation_tip": implementation,
        "source_identity_receipt_hash": source_identity.receipt_hash,
        "controller_startup_binding_hash": controller.binding_hash,
        "persistent_capsule_source_binding_hash": capsule_source.binding_hash,
        "bridge_surface_manifest_hash": bridge.manifest_hash,
        "source_domain_compatibility_receipt_hash": compatibility.receipt_hash,
        "freeze_assembly_plan_hash": plan.plan_hash,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    _write(output / "build_receipt.json", receipt)
    print(canonical_json(receipt))


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K8 JSON input is not an object")
    return value


def _verified(path: Path, field: str) -> dict:
    value = _object(path)
    body = dict(value)
    claimed = body.pop(field)
    if content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K8 input hash changed")
    return value


def _write(path: Path, value: dict) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
