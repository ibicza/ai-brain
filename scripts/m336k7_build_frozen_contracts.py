"""Build the phase-neutral M-33.6k.7 resource and capsule contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    dependency_manifest_from_dict,
    public_execution_capsule_receipt_from_dict,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k6_capsule import (
    M336K6CapsuleLivenessReceipt,
    M336K6PrivateExecutionCapsule,
    M336K6PublicExecutionCapsuleReceipt,
)
from ai_brain.stage3.acquisition.m336k7_contracts import (
    M336K7LegacyCapsuleCompatibilityReceipt,
    M336K7PersistentCapsuleBindingSet,
    M336K7ResourceBudgetPolicy,
    M336K7ResourceGateReceipt,
    M336K7ResourceObservationReceipt,
    storage_reservation_from_dict,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    args = parser.parse_args()
    configuration = _object(args.configuration.resolve(strict=True))
    expected = {
        "capsule_implementation_tip",
        "legacy_resource_receipt",
        "storage_reservation_receipt",
        "persistent_private_capsule",
        "persistent_public_capsule_receipt",
        "legacy_public_capsule_receipt",
        "python_environment_manifest",
        "executable_dependency_manifest",
        "capsule_content_manifest",
        "capsule_lifecycle_policy",
        "capsule_liveness_receipt",
        "preservation_receipt",
        "cleanup_cutoff_receipt",
        "output",
    }
    if set(configuration) != expected:
        raise M336K2ProtocolError("M336K7 frozen-contract configuration changed")
    output = Path(configuration["output"]).resolve(strict=False)
    if output.exists():
        raise M336K2ProtocolError("M336K7 frozen-contract output is stale")

    reservation = storage_reservation_from_dict(
        _object(Path(configuration["storage_reservation_receipt"]).resolve(strict=True))
    )
    policy = M336K7ResourceBudgetPolicy.build(
        storage_reservation_bytes=reservation.reservation_bytes
    )
    observation = M336K7ResourceObservationReceipt.from_m336k6_aggregate(
        _object(Path(configuration["legacy_resource_receipt"]).resolve(strict=True))
    )
    gate = M336K7ResourceGateReceipt.build(policy, observation, reservation)
    if gate.status != "PASS":
        raise M336K2ProtocolError("M336K7 resource gate did not pass")

    private = M336K6PrivateExecutionCapsule.from_dict(
        _object(Path(configuration["persistent_private_capsule"]).resolve(strict=True))
    )
    persistent_value = _object(
        Path(configuration["persistent_public_capsule_receipt"]).resolve(strict=True)
    )
    if set(persistent_value) != set(
        M336K6PublicExecutionCapsuleReceipt.__dataclass_fields__
    ):
        raise M336K2ProtocolError("M336K7 persistent receipt fields changed")
    _verify_hash(persistent_value, "receipt_hash")
    persistent = M336K6PublicExecutionCapsuleReceipt(**persistent_value)
    legacy = public_execution_capsule_receipt_from_dict(
        _object(
            Path(configuration["legacy_public_capsule_receipt"]).resolve(strict=True)
        )
    )
    dependencies = dependency_manifest_from_dict(
        _object(
            Path(configuration["executable_dependency_manifest"]).resolve(strict=True)
        )
    )
    environment = _object(
        Path(configuration["python_environment_manifest"]).resolve(strict=True)
    )
    _verify_hash(environment, "identity_hash")
    content = _object(
        Path(configuration["capsule_content_manifest"]).resolve(strict=True)
    )
    _verify_hash(content, "manifest_hash")
    lifecycle = _object(
        Path(configuration["capsule_lifecycle_policy"]).resolve(strict=True)
    )
    _verify_hash(lifecycle, "policy_hash")
    liveness_value = _object(
        Path(configuration["capsule_liveness_receipt"]).resolve(strict=True)
    )
    if set(liveness_value) != set(M336K6CapsuleLivenessReceipt.__dataclass_fields__):
        raise M336K2ProtocolError("M336K7 liveness receipt fields changed")
    _verify_hash(liveness_value, "receipt_hash")
    liveness = M336K6CapsuleLivenessReceipt(**liveness_value)
    preservation = _object(
        Path(configuration["preservation_receipt"]).resolve(strict=True)
    )
    _verify_hash(preservation, "receipt_hash")
    cutoff = _object(Path(configuration["cleanup_cutoff_receipt"]).resolve(strict=True))
    _verify_hash(cutoff, "receipt_hash")

    if (
        configuration["capsule_implementation_tip"] != private.implementation_sha
        or persistent.implementation_sha != private.implementation_sha
        or persistent.capsule_identity_hash != private.capsule_identity_hash
        or persistent.capsule_root_identity_hash != private.capsule_root_identity_hash
        or persistent.content_manifest_hash != content["manifest_hash"]
        or persistent.lifecycle_policy_hash != lifecycle["policy_hash"]
        or persistent.legacy_public_receipt_hash != legacy.receipt_hash
        or persistent.python_environment_manifest_hash
        != environment["environment_manifest_hash"]
        or persistent.executable_dependency_manifest_hash != dependencies.manifest_hash
        or persistent.stable_host_identity_hash != legacy.host_identity_receipt_hash
        or liveness.capsule_identity_hash != private.capsule_identity_hash
        or liveness.content_manifest_hash != content["manifest_hash"]
        or liveness.lifecycle_policy_hash != lifecycle["policy_hash"]
        or liveness.legacy_public_receipt_hash != legacy.receipt_hash
        or liveness.status != "PASS"
        or any(
            (
                liveness.missing_file_count,
                liveness.changed_file_count,
                liveness.unexpected_file_count,
                liveness.mutable_quality_dependency_count,
                liveness.symlink_target_change_count,
            )
        )
    ):
        raise M336K2ProtocolError("M336K7 capsule inputs are not one identity")

    compatibility = M336K7LegacyCapsuleCompatibilityReceipt.build(
        persistent_public_receipt_hash=persistent.receipt_hash,
        legacy_public_receipt_hash=legacy.receipt_hash,
        executable_dependency_manifest_hash=dependencies.manifest_hash,
        host_identity_hash=legacy.host_identity_receipt_hash,
        python_environment_manifest_hash=environment["environment_manifest_hash"],
        compatibility_status="PASS",
    )
    binding = M336K7PersistentCapsuleBindingSet.build(
        implementation_tip=private.implementation_sha,
        capsule_identity_hash=private.capsule_identity_hash,
        capsule_root_identity_hash=private.capsule_root_identity_hash,
        capsule_content_manifest_hash=content["manifest_hash"],
        capsule_lifecycle_policy_hash=lifecycle["policy_hash"],
        capsule_liveness_receipt_hash=liveness.receipt_hash,
        persistent_capsule_public_receipt_hash=persistent.receipt_hash,
        legacy_public_capsule_receipt_hash=legacy.receipt_hash,
        python_environment_manifest_hash=environment["environment_manifest_hash"],
        executable_dependency_manifest_hash=dependencies.manifest_hash,
        startup_policy_hash=private.startup_policy_hash,
        bootstrap_source_hash=private.bootstrap_source_hash,
        launcher_source_hash=private.launcher_source_hash,
        stable_karina_host_identity_hash=legacy.host_identity_receipt_hash,
        preservation_set_hash=preservation["preservation_set_hash"],
        cleanup_cutoff_receipt_hash=cutoff["receipt_hash"],
    )

    output.mkdir(parents=True)
    values = {
        "resource_budget_policy": policy.canonical_object(),
        "resource_observation": observation.canonical_object(),
        "resource_gate": gate.canonical_object(),
        "capsule_binding_set": binding.canonical_object(),
        "legacy_capsule_compatibility": compatibility.canonical_object(),
    }
    for name, value in values.items():
        (output / f"{name}.json").write_text(
            canonical_json(value) + "\n", encoding="utf-8", newline="\n"
        )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K7_FROZEN_CONTRACT_BUILD_RECEIPT",
        "resource_budget_policy_hash": policy.policy_hash,
        "resource_observation_hash": observation.observation_hash,
        "storage_reservation_receipt_hash": reservation.receipt_hash,
        "resource_gate_receipt_hash": gate.receipt_hash,
        "capsule_binding_set_hash": binding.binding_set_hash,
        "legacy_compatibility_receipt_hash": compatibility.receipt_hash,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    (output / "build_receipt.json").write_text(
        canonical_json(receipt) + "\n", encoding="utf-8", newline="\n"
    )
    print(canonical_json(receipt))


def _verify_hash(value: dict, field: str) -> None:
    body = dict(value)
    claimed = body.pop(field)
    if type(claimed) is not str or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K7 component hash changed")


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K7 JSON input is invalid") from error
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K7 JSON input is not an object")
    return value


if __name__ == "__main__":
    main()
