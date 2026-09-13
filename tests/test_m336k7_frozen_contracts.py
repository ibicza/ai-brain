from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition import m336k7_contracts
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k2_publication import (
    _e_source_files,
    _h_source_files,
    build_m336k2_publication_contract,
)
from ai_brain.stage3.acquisition.m336k2_registry import (
    build_m336k2_route_manifest,
    build_m336k2_route_registry,
)
from ai_brain.stage3.acquisition.m336k5_resources import (
    M336K5StorageReservationReceipt,
)
from ai_brain.stage3.acquisition.m336k6_capsule import (
    M336K6CapsuleContentEntry,
    M336K6CapsuleContentManifest,
)
from ai_brain.stage3.acquisition.m336k7_contracts import (
    M336K7FrozenContractCompatibilityGate,
    M336K7LegacyCapsuleCompatibilityReceipt,
    M336K7PersistentCapsuleBindingSet,
    M336K7PostFreezeInputBundle,
    M336K7ResourceBudgetPolicy,
    M336K7ResourceGateReceipt,
    M336K7ResourceObservationReceipt,
    M336K7StorageReservationReleaseReceipt,
    M336K7StrictArtifact,
    build_m336k7_persistent_capsule_route_manifest,
    build_m336k7_persistent_capsule_route_registry,
    forbid_m336k7_post_freeze_mutation,
    require_m336k7_frozen_bytes,
    storage_reservation_from_dict,
    verify_m336k7_capsule_compatibility_binding,
    verify_m336k7_persistent_capsule_route_binding,
    verify_m336k7_resource_gate_binding,
    verify_m336k7_unchanged_candidate_pool,
)
from ai_brain.stage3.acquisition.m336k7_freeze import (
    M336K7CommittedFreezeAttestation,
)

H = "1" * 64
H2 = "2" * 64


def test_m336k7_candidate_pool_requires_exact_frozen_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {
        "candidate_count": 2,
        "candidates": [{"candidate_id": "a"}, {"candidate_id": "b"}],
        "organization_count": 1,
        "maximum_candidates_per_organization": 2,
        "pre_freeze_source_body_bytes": 0,
    }
    pool = {**body, "pool_hash": content_hash(body)}
    raw = (canonical_json(pool) + "\n").encode()
    path = tmp_path / "candidate_pool.json"
    path.write_bytes(raw)
    monkeypatch.setattr(
        m336k7_contracts, "M336K7_FINAL_CANDIDATE_POOL_HASH", pool["pool_hash"]
    )
    monkeypatch.setattr(
        m336k7_contracts, "M336K7_FINAL_CANDIDATE_POOL_BYTES_HASH", bytes_hash(raw)
    )
    monkeypatch.setattr(m336k7_contracts, "M336K7_FINAL_CANDIDATE_COUNT", 2)
    monkeypatch.setattr(m336k7_contracts, "M336K7_FINAL_ORGANIZATION_COUNT", 1)

    assert verify_m336k7_unchanged_candidate_pool(path) == pool

    path.write_bytes(raw + b"\n")
    with pytest.raises(M336K2ProtocolError, match="candidate-pool bytes changed"):
        verify_m336k7_unchanged_candidate_pool(path)


def test_m336k7_publication_requires_typed_identity_observation() -> None:
    contract = build_m336k2_publication_contract(
        q_root="artifacts/m336k7/q32",
        f_root="artifacts/m336k7/f32-freeze",
        h_root="artifacts/m336k7/h32",
        e_root="artifacts/m336k7/e32",
    )

    assert "route_identity_observation.json" in _h_source_files(contract)
    assert "route_identity_observation.json" in _e_source_files(contract)


def _policy() -> M336K7ResourceBudgetPolicy:
    return M336K7ResourceBudgetPolicy.build(storage_reservation_bytes=1024)


def _observation() -> M336K7ResourceObservationReceipt:
    body = {
        "schema_version": 1,
        "contract_role": M336K7ResourceObservationReceipt.ROLE,
        "sample_count": 2,
        "sample_chain_hash": H,
        "minimum_available_ram_bytes": 16 * 1024**3,
        "maximum_process_tree_peak_rss_bytes": 1024,
        "maximum_swap_used_bytes": 0,
        "minimum_filesystem_free_bytes": 64 * 1024**3,
        "minimum_filesystem_free_inodes": 1_000_000,
        "maximum_capsule_size_bytes": 1024,
        "maximum_official_vault_size_bytes": 0,
        "maximum_selected_snapshot_size_bytes": 0,
        "maximum_production_roots_size_bytes": 0,
        "maximum_evaluator_root_size_bytes": 0,
        "maximum_active_task_process_count": 1,
    }
    return M336K7ResourceObservationReceipt(**body, observation_hash=content_hash(body))


def _reservation() -> M336K5StorageReservationReceipt:
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K5_STORAGE_RESERVATION_RECEIPT",
        "reservation_bytes": 1024,
        "reservation_content_hash": H,
        "filesystem_identity_hash": H,
        "free_bytes_before": 64 * 1024**3,
        "free_bytes_after": 63 * 1024**3,
        "allocated_size_bytes": 1024,
        "minimum_post_reservation_free_bytes": 8 * 1024**3,
        "sparse": False,
        "status": "PASS",
    }
    return M336K5StorageReservationReceipt(**body, receipt_hash=content_hash(body))


def _binding() -> M336K7PersistentCapsuleBindingSet:
    return M336K7PersistentCapsuleBindingSet.build(
        implementation_tip="a" * 40,
        capsule_identity_hash=H,
        capsule_root_identity_hash=H,
        capsule_content_manifest_hash=H,
        capsule_lifecycle_policy_hash=H,
        capsule_liveness_receipt_hash=H,
        persistent_capsule_public_receipt_hash=H,
        legacy_public_capsule_receipt_hash=H,
        python_environment_manifest_hash=H,
        executable_dependency_manifest_hash=H,
        startup_policy_hash=H,
        bootstrap_source_hash=H,
        launcher_source_hash=H,
        stable_karina_host_identity_hash=H,
        preservation_set_hash=H,
        cleanup_cutoff_receipt_hash=H,
    )


def _compatibility() -> M336K7LegacyCapsuleCompatibilityReceipt:
    return M336K7LegacyCapsuleCompatibilityReceipt.build(
        persistent_public_receipt_hash=H,
        legacy_public_receipt_hash=H,
        executable_dependency_manifest_hash=H,
        host_identity_hash=H,
        python_environment_manifest_hash=H,
        compatibility_status="PASS",
    )


def _bundle() -> M336K7PostFreezeInputBundle:
    names = {field.name for field in fields(M336K7PostFreezeInputBundle)} - {
        "schema_version",
        "contract_role",
        "bundle_hash",
    }
    return M336K7PostFreezeInputBundle.build(**{name: H for name in names})


def _rehash(value: dict, field: str) -> dict:
    result = dict(value)
    result.pop(field)
    result[field] = content_hash(result)
    return result


def _reject(callable_) -> None:
    with pytest.raises(M336K2ProtocolError):
        callable_()


@pytest.mark.parametrize(
    ("case", "run"),
    (
        (
            "01_missing_required_private_storage_bytes",
            lambda: M336K7ResourceBudgetPolicy.from_dict(
                {
                    key: value
                    for key, value in _policy().canonical_object().items()
                    if key != "required_private_storage_bytes"
                }
            ),
        ),
        (
            "02_obsolete_phase_specific_field_used_instead",
            lambda: M336K7ResourceBudgetPolicy.from_dict(
                {
                    **{
                        key: value
                        for key, value in _policy().canonical_object().items()
                        if key != "required_private_storage_bytes"
                    },
                    "required_pre_f30_private_storage_bytes": 1,
                }
            ),
        ),
        (
            "03_extra_resource_policy_field",
            lambda: M336K7ResourceBudgetPolicy.from_dict(
                {**_policy().canonical_object(), "extra": 1}
            ),
        ),
        (
            "04_observation_supplied_as_policy",
            lambda: M336K7ResourceBudgetPolicy.from_dict(
                _observation().canonical_object()
            ),
        ),
        (
            "05_policy_supplied_as_observation",
            lambda: M336K7ResourceObservationReceipt.from_dict(
                _policy().canonical_object()
            ),
        ),
        (
            "06_storage_threshold_changed",
            lambda: verify_m336k7_resource_gate_binding(
                M336K7ResourceBudgetPolicy.from_dict(
                    _rehash(
                        {
                            **_policy().canonical_object(),
                            "required_private_storage_bytes": 1,
                        },
                        "policy_hash",
                    )
                ),
                _observation(),
                _reservation(),
                M336K7ResourceGateReceipt.build(
                    _policy(), _observation(), _reservation()
                ),
            ),
        ),
        (
            "07_ram_threshold_changed",
            lambda: verify_m336k7_resource_gate_binding(
                M336K7ResourceBudgetPolicy.from_dict(
                    _rehash(
                        {
                            **_policy().canonical_object(),
                            "required_available_ram_bytes": 1,
                        },
                        "policy_hash",
                    )
                ),
                _observation(),
                _reservation(),
                M336K7ResourceGateReceipt.build(
                    _policy(), _observation(), _reservation()
                ),
            ),
        ),
        (
            "08_inode_threshold_changed",
            lambda: verify_m336k7_resource_gate_binding(
                M336K7ResourceBudgetPolicy.from_dict(
                    _rehash(
                        {**_policy().canonical_object(), "required_free_inodes": 1},
                        "policy_hash",
                    )
                ),
                _observation(),
                _reservation(),
                M336K7ResourceGateReceipt.build(
                    _policy(), _observation(), _reservation()
                ),
            ),
        ),
        (
            "09_reservation_size_changed",
            lambda: verify_m336k7_resource_gate_binding(
                _policy(),
                _observation(),
                storage_reservation_from_dict(
                    _rehash(
                        {**asdict(_reservation()), "reservation_bytes": 512},
                        "receipt_hash",
                    )
                ),
                M336K7ResourceGateReceipt.build(
                    _policy(), _observation(), _reservation()
                ),
            ),
        ),
        (
            "10_observation_hash_changed",
            lambda: M336K7ResourceObservationReceipt.from_dict(
                {**_observation().canonical_object(), "observation_hash": H2}
            ),
        ),
        (
            "11_resource_gate_hash_changed",
            lambda: M336K7ResourceGateReceipt.from_dict(
                {
                    **M336K7ResourceGateReceipt.build(
                        _policy(), _observation(), _reservation()
                    ).canonical_object(),
                    "receipt_hash": H2,
                }
            ),
        ),
        (
            "12_resource_gate_pass_forged",
            lambda: verify_m336k7_resource_gate_binding(
                _policy(),
                M336K7ResourceObservationReceipt.from_dict(
                    _rehash(
                        {
                            **_observation().canonical_object(),
                            "minimum_available_ram_bytes": 1,
                        },
                        "observation_hash",
                    )
                ),
                _reservation(),
                M336K7ResourceGateReceipt.build(
                    _policy(), _observation(), _reservation()
                ),
            ),
        ),
        *tuple(
            (
                f"{number:02d}_{field}_changed",
                lambda field=field: M336K7PersistentCapsuleBindingSet.from_dict(
                    {**_binding().canonical_object(), field: H2}
                ),
            )
            for number, field in (
                (13, "persistent_capsule_public_receipt_hash"),
                (14, "legacy_public_capsule_receipt_hash"),
                (15, "executable_dependency_manifest_hash"),
                (16, "python_environment_manifest_hash"),
                (17, "capsule_content_manifest_hash"),
                (18, "capsule_lifecycle_policy_hash"),
                (19, "capsule_liveness_receipt_hash"),
                (20, "stable_karina_host_identity_hash"),
                (21, "preservation_set_hash"),
                (22, "cleanup_cutoff_receipt_hash"),
            )
        ),
        (
            "23_compatibility_receipt_missing",
            lambda: M336K7LegacyCapsuleCompatibilityReceipt.from_dict(
                {
                    key: value
                    for key, value in _compatibility().canonical_object().items()
                    if key != "receipt_hash"
                }
            ),
        ),
        (
            "24_compatibility_belongs_to_another_capsule",
            lambda: verify_m336k7_capsule_compatibility_binding(
                _binding(),
                M336K7LegacyCapsuleCompatibilityReceipt.from_dict(
                    _rehash(
                        {
                            **_compatibility().canonical_object(),
                            "persistent_public_receipt_hash": H2,
                        },
                        "receipt_hash",
                    )
                ),
            ),
        ),
        (
            "25_frozen_input_replaced_by_live_receipt",
            lambda: require_m336k7_frozen_bytes(
                (canonical_json(_bundle().canonical_object()) + "\n").encode(),
                (
                    canonical_json(
                        _rehash(
                            {
                                **_bundle().canonical_object(),
                                "resource_observation_hash": H2,
                            },
                            "bundle_hash",
                        )
                    )
                    + "\n"
                ).encode(),
            ),
        ),
        (
            "26_producer_consumer_field_set_difference",
            lambda: M336K7StrictArtifact.consume(
                {**_policy().canonical_object(), "extra": 1},
                expected_fields=frozenset(_policy().canonical_object()),
                semantic_role=M336K7ResourceBudgetPolicy.ROLE,
                hash_field="policy_hash",
            ),
        ),
        (
            "28_phase_specific_current_policy_field",
            lambda: M336K7ResourceBudgetPolicy.from_dict(
                {**_policy().canonical_object(), "post_f32_required_bytes": 1}
            ),
        ),
    ),
)
def test_contract_mutations_are_rejected(case: str, run) -> None:
    assert case
    _reject(run)


def test_27_mandatory_default_lookup_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "bad_current_route.py"
    source.write_text('required = policy.get("mandatory", 0)\n', encoding="utf-8")
    policy = _policy().canonical_object()
    report = M336K7FrozenContractCompatibilityGate.run(
        {
            "resource_budget_policy": (
                policy,
                lambda value: M336K7ResourceBudgetPolicy.from_dict(value),
            )
        },
        current_route_sources=(source,),
    )
    assert report.status == "FAIL"
    assert report.mandatory_default_lookup_count == 1


@pytest.mark.parametrize(
    ("case", "operation"),
    (
        ("29_persistent_capsule_recreated_after_f32", "CAPSULE_RECREATE"),
        ("30_cleanup_requested_after_f32", "CLEANUP"),
        ("31_capsule_removed_after_f32", "CAPSULE_REMOVE"),
    ),
)
def test_post_freeze_mutation_is_rejected(case: str, operation: str) -> None:
    assert case
    _reject(
        lambda: forbid_m336k7_post_freeze_mutation(
            exact_f32_sha="a" * 40, operation=operation
        )
    )


def test_32_committed_frozen_bytes_must_match() -> None:
    _reject(lambda: require_m336k7_frozen_bytes(b"committed\n", b"regenerated\n"))


def test_current_contract_roundtrip_and_field_count(tmp_path: Path) -> None:
    source = tmp_path / "current_route.py"
    source.write_text(
        "mandatory = policy['required_private_storage_bytes']\n", encoding="utf-8"
    )
    artifacts = {
        "resource_budget_policy": (
            _policy().canonical_object(),
            M336K7ResourceBudgetPolicy.from_dict,
        ),
        "resource_observation": (
            _observation().canonical_object(),
            M336K7ResourceObservationReceipt.from_dict,
        ),
        "resource_gate": (
            M336K7ResourceGateReceipt.build(
                _policy(), _observation(), _reservation()
            ).canonical_object(),
            M336K7ResourceGateReceipt.from_dict,
        ),
        "capsule_binding_set": (
            _binding().canonical_object(),
            M336K7PersistentCapsuleBindingSet.from_dict,
        ),
        "legacy_compatibility": (
            _compatibility().canonical_object(),
            M336K7LegacyCapsuleCompatibilityReceipt.from_dict,
        ),
        "post_freeze_input_bundle": (
            _bundle().canonical_object(),
            M336K7PostFreezeInputBundle.from_dict,
        ),
    }
    report = M336K7FrozenContractCompatibilityGate.run(
        artifacts, current_route_sources=(source,)
    )
    assert report.status == "PASS"
    assert report.artifact_count == len(artifacts)
    assert report.missing_field_count == 0
    assert report.extra_field_count == 0
    assert report.roundtrip_difference_count == 0
    assert report.semantic_binding_mismatch_count == 0


def test_storage_reservation_release_receipt_is_strict(tmp_path: Path) -> None:
    receipt = M336K7StorageReservationReleaseReceipt.build(
        reservation=_reservation(),
        reservation_file=tmp_path / "reservation.bin",
        free_bytes_before_release=32 * 1024**3,
        free_bytes_after_release=33 * 1024**3,
    )
    assert (
        M336K7StorageReservationReleaseReceipt.from_dict(receipt.canonical_object())
        == receipt
    )
    _reject(
        lambda: M336K7StorageReservationReleaseReceipt.from_dict(
            {**receipt.canonical_object(), "unexpected": 1}
        )
    )


def test_committed_f32_attestation_distinguishes_git_and_content_hashes() -> None:
    body = {
        "schema_version": 1,
        "contract_role": "M336K7_COMMITTED_F32_ATTESTATION",
        "exact_f32_sha": "a" * 40,
        "exact_q32_parent": "b" * 40,
        "committed_tree_hash": "c" * 40,
        "prospective_freeze_tree_hash": H,
        "prospective_tree_matches": True,
        "route_identity_bundle_hash": H,
        "authorization_hash": H,
        "route_hash": H,
        "post_freeze_input_bundle_hash": H,
        "implementation_change_count": 0,
        "merge_count": 0,
        "head_upstream_remote_equal": True,
        "worktree_clean": True,
        "status": "PASS",
    }
    receipt = M336K7CommittedFreezeAttestation(
        **body, attestation_hash=content_hash(body)
    )
    receipt.verify()


def test_persistent_capsule_route_is_derived_from_frozen_source_bytes() -> None:
    repository = Path(__file__).parents[1]
    current = build_m336k2_route_registry(repository)
    entries = tuple(
        M336K6CapsuleContentEntry(
            relative_path=item.repository_path,
            byte_count=item.source_byte_count,
            bytes_hash=item.source_bytes_hash,
        )
        for item in sorted(
            current.components, key=lambda item: item.repository_path.encode("utf-8")
        )
    )
    manifest_body = {
        "schema_version": 1,
        "contract_role": "M336K6_CAPSULE_CONTENT_MANIFEST",
        "execution_strategy": "PROTECTED_DETACHED_GIT_WORKTREE",
        "implementation_sha": "a" * 40,
        "entries": entries,
        "entry_count": len(entries),
        "byte_count": sum(item.byte_count for item in entries),
        "source_tree_hash": content_hash(tuple(asdict(item) for item in entries)),
        "uv_lock_hash": H,
        "pyproject_toml_hash": H,
    }
    manifest = M336K6CapsuleContentManifest(
        **manifest_body, manifest_hash=content_hash(manifest_body)
    )
    manifest.verify()
    manifest_value = json.loads(canonical_json(manifest))
    derived = build_m336k7_persistent_capsule_route_registry(manifest_value)
    assert derived == current

    template = build_m336k2_route_manifest(
        registry=current,
        executable_dependency_manifest_hash=H,
        python_environment_manifest_hash=H,
        command_renderer_hash=H,
        minimal_environment_policy_hash=H,
    )
    route = build_m336k7_persistent_capsule_route_manifest(asdict(template), derived)
    verify_m336k7_persistent_capsule_route_binding(
        content_value=manifest_value,
        registry_value=json.loads(canonical_json(derived)),
        route_value=json.loads(canonical_json(route)),
    )

    changed_registry = json.loads(canonical_json(derived))
    changed_registry["registry_hash"] = H2
    _reject(
        lambda: verify_m336k7_persistent_capsule_route_binding(
            content_value=manifest_value,
            registry_value=changed_registry,
            route_value=asdict(route),
        )
    )
