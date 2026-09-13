from __future__ import annotations

from dataclasses import asdict
from pathlib import PurePosixPath

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k6_capsule import (
    M336K6CapsuleContentEntry,
    M336K6CapsuleContentManifest,
    M336K6CapsuleLifecyclePolicy,
    M336K6PrivateExecutionCapsule,
    verify_m336k6_capsule_location,
    verify_m336k6_execution_identities,
    verify_m336k6_required_paths,
)
from ai_brain.stage3.acquisition.m336k6_cleanup import (
    M336K6CleanupCandidate,
    M336K6CleanupMode,
    M336K6PreservationReceipt,
    M336K6PreservationSet,
    M336K6PreservedResource,
    plan_m336k6_cleanup,
    preservation_receipt,
)

H = "a" * 64
H2 = "b" * 64
SHA = "1" * 40
ROOT = "/home/ibicza/.local/share/ai-brain/m336k6/capsules/capsule-alpha"


def _capsule(**changes) -> M336K6PrivateExecutionCapsule:
    body = {
        "schema_version": 1,
        "contract_role": "M336K6_PRIVATE_EXECUTION_CAPSULE",
        "execution_strategy": "PROTECTED_DETACHED_GIT_WORKTREE",
        "capsule_root": ROOT,
        "source_root": f"{ROOT}/source",
        "git_store": f"{ROOT}/git-store.git",
        "private_route_root": "/home/ibicza/.local/state/ai-brain/m336k6/route-alpha",
        "python_invocation_handle": "/opt/python-env/bin/python",
        "resolved_python_binary": "/opt/python/bin/python3",
        "python_environment_prefix": "/opt/python-env",
        "git_executable": "/usr/bin/git",
        "ssh_executable": "/usr/bin/ssh",
        "java_executable": "/opt/jdk/bin/java",
        "javac_executable": "/opt/jdk/bin/javac",
        "shell_executable": "/bin/sh",
        "legacy_capsule_path": f"{ROOT}/legacy.json",
        "content_manifest_path": f"{ROOT}/content.json",
        "lifecycle_policy_path": f"{ROOT}/lifecycle.json",
        "host_identity_receipt_path": f"{ROOT}/host.json",
        "implementation_sha": SHA,
        "project_source_identity": H,
        "legacy_public_receipt_hash": H,
        "python_environment_manifest_hash": H,
        "executable_dependency_manifest_hash": H,
        "startup_policy_hash": H,
        "bootstrap_source_hash": H,
        "launcher_source_hash": H,
        "ssh_executable_content_hash": H,
        "content_manifest_hash": H,
        "lifecycle_policy_hash": H,
        "capsule_root_identity_hash": content_hash(("M336K6_CAPSULE_ROOT", ROOT)),
    }
    body.update(changes)
    return M336K6PrivateExecutionCapsule(
        **body, capsule_identity_hash=content_hash(body)
    )


def _resource(path: str = ROOT, role: str = "PERSISTENT_CAPSULE_ROOT"):
    return M336K6PreservedResource.build(
        role=role,
        private_path=path,
        content_tree_hash=H,
        lifecycle_owner="M336K6_FINAL_ROUTE_CONTROLLER",
        required_until_phase="E31_FINAL_QUALITY_COMPLETE",
        path_class="PERSISTENT_PRIVATE_RESOURCE",
    )


def _set(*resources) -> M336K6PreservationSet:
    return M336K6PreservationSet.build(resources or (_resource(),))


def _candidate(path: str, **changes) -> M336K6CleanupCandidate:
    return M336K6CleanupCandidate.build(
        private_path=path,
        category="STAGING_TREE",
        tree_hash=H,
        **changes,
    )


def _plan(candidate, **changes):
    return plan_m336k6_cleanup(
        candidates=(candidate,),
        preservation_set=_set(),
        mode=M336K6CleanupMode.PRE_FREEZE,
        phase="PRE_Q31_CLEANUP",
        **changes,
    )


def test_mutation_01_capsule_under_quality_worktree_rejected() -> None:
    with pytest.raises(M336K2ProtocolError):
        verify_m336k6_capsule_location(PurePosixPath(f"{ROOT}/quality/capsule-beta"))


def test_mutation_02_capsule_under_disposable_root_rejected() -> None:
    with pytest.raises(M336K2ProtocolError):
        verify_m336k6_capsule_location(PurePosixPath(f"{ROOT}/disposable/capsule-beta"))


def test_mutation_03_capsule_under_tmp_rejected() -> None:
    with pytest.raises(M336K2ProtocolError):
        verify_m336k6_capsule_location(PurePosixPath("/tmp/capsule-beta"))


@pytest.mark.parametrize(
    "path",
    (ROOT, "/home/ibicza/.local/share/ai-brain/m336k6/capsules", f"{ROOT}/source"),
    ids=("equal", "parent", "child"),
)
def test_mutations_04_to_06_cleanup_capsule_intersection_rejected(path: str) -> None:
    decision = _plan(_candidate(path)).decisions[0]
    assert not decision.eligible
    assert decision.rejection_reason == "PRESERVATION_SET_INTERSECTION"


def test_mutation_07_symlink_resolution_into_capsule_rejected() -> None:
    candidate = _candidate(
        "/home/ibicza/stale-root", resolved_target_paths=(f"{ROOT}/source",)
    )
    assert _plan(candidate).decisions[0].rejection_reason == (
        "PRESERVATION_SET_INTERSECTION"
    )


def test_mutation_08_missing_capsule_python_rejected() -> None:
    capsule = _capsule()
    with pytest.raises(M336K2ProtocolError):
        verify_m336k6_required_paths(
            capsule, path_exists=lambda path: path != capsule.python_invocation_handle
        )


def test_mutation_09_missing_source_file_rejected() -> None:
    value = _manifest_dict()
    value["entry_count"] = 2
    value["manifest_hash"] = content_hash(
        {k: v for k, v in value.items() if k != "manifest_hash"}
    )
    with pytest.raises(M336K2ProtocolError):
        M336K6CapsuleContentManifest.from_dict(value)


def test_mutation_10_source_hash_change_rejected() -> None:
    value = _manifest_dict()
    value["entries"][0]["bytes_hash"] = H2
    with pytest.raises(M336K2ProtocolError):
        M336K6CapsuleContentManifest.from_dict(value)


def test_mutation_11_python_environment_change_rejected() -> None:
    with pytest.raises(M336K2ProtocolError):
        verify_m336k6_execution_identities(
            _capsule(),
            legacy_public_receipt_hash=H,
            python_environment_manifest_hash=H2,
            executable_dependency_manifest_hash=H,
            implementation_sha=SHA,
        )


def test_mutation_12_git_identity_change_rejected() -> None:
    with pytest.raises(M336K2ProtocolError):
        verify_m336k6_execution_identities(
            _capsule(),
            legacy_public_receipt_hash=H2,
            python_environment_manifest_hash=H,
            executable_dependency_manifest_hash=H,
            implementation_sha=SHA,
        )


def test_mutation_13_jdk_identity_change_rejected() -> None:
    with pytest.raises(M336K2ProtocolError):
        verify_m336k6_execution_identities(
            _capsule(),
            legacy_public_receipt_hash=H,
            python_environment_manifest_hash=H,
            executable_dependency_manifest_hash=H2,
            implementation_sha=SHA,
        )


def test_mutation_14_host_identity_change_rejected() -> None:
    capsule = _capsule()
    value = asdict(capsule)
    value["legacy_public_receipt_hash"] = H2
    with pytest.raises(M336K2ProtocolError):
        M336K6PrivateExecutionCapsule.from_dict(value)


def test_mutation_15_implementation_sha_change_rejected() -> None:
    with pytest.raises(M336K2ProtocolError):
        verify_m336k6_execution_identities(
            _capsule(),
            legacy_public_receipt_hash=H,
            python_environment_manifest_hash=H,
            executable_dependency_manifest_hash=H,
            implementation_sha="2" * 40,
        )


def test_mutation_16_quality_worktree_removal_preserves_capsule() -> None:
    decision = _plan(_candidate("/home/ibicza/m336k6-quality-old")).decisions[0]
    assert decision.eligible
    _capsule().verify_structure()


def test_mutation_17_disposable_worktree_removal_preserves_capsule() -> None:
    decision = _plan(_candidate("/home/ibicza/m336k6-disposable-old")).decisions[0]
    assert decision.eligible
    _capsule().verify_structure()


def test_mutation_18_cleanup_after_f31_rejected() -> None:
    with pytest.raises(M336K2ProtocolError):
        _plan(_candidate("/home/ibicza/stale"), f31_created=True)


def test_mutation_19_cleanup_after_reservation_release_rejected() -> None:
    with pytest.raises(M336K2ProtocolError):
        _plan(_candidate("/home/ibicza/stale"), reservation_released=True)


@pytest.mark.parametrize(
    "phase",
    ("OFFICIAL_ACQUISITION", "OFFICIAL_PRODUCTION", "OFFICIAL_EVALUATION"),
    ids=("acquisition", "production", "evaluation"),
)
def test_mutations_20_to_22_cleanup_during_official_phase_rejected(phase: str) -> None:
    with pytest.raises(M336K2ProtocolError):
        plan_m336k6_cleanup(
            candidates=(_candidate("/home/ibicza/stale"),),
            preservation_set=_set(),
            mode=M336K6CleanupMode.PRE_FREEZE,
            phase=phase,
        )


def test_mutation_23_preservation_receipt_change_rejected() -> None:
    receipt = preservation_receipt(_set())
    value = asdict(receipt)
    value["preserved_resource_count"] += 1
    with pytest.raises(M336K2ProtocolError):
        M336K6PreservationReceipt.from_dict(value)


def test_mutation_24_lifecycle_end_phase_forgery_rejected() -> None:
    value = asdict(M336K6CapsuleLifecyclePolicy.build())
    value["required_until_phase"] = "Q31"
    body = {key: item for key, item in value.items() if key != "policy_hash"}
    value["policy_hash"] = content_hash(body)
    with pytest.raises(M336K2ProtocolError):
        M336K6CapsuleLifecyclePolicy.from_dict(value)


def test_mutation_25_active_process_root_rejected() -> None:
    decision = _plan(
        _candidate("/home/ibicza/stale", active_process_count=1)
    ).decisions[0]
    assert decision.rejection_reason == "ACTIVE_RESOURCE"


@pytest.mark.parametrize(
    "role",
    ("OFFICIAL_LEDGER", "OFFICIAL_VAULT", "STORAGE_RESERVATION"),
    ids=("ledger", "vault", "reservation"),
)
def test_mutations_26_to_28_official_resources_rejected(role: str) -> None:
    decision = _plan(_candidate("/home/ibicza/stale", official_role=role)).decisions[0]
    assert decision.rejection_reason == "OFFICIAL_RESOURCE"


def test_cleanup_during_f31_and_publication_is_rejected() -> None:
    for phase in ("F31_CREATION", "H31_PUBLICATION", "E31_PUBLICATION"):
        with pytest.raises(M336K2ProtocolError):
            plan_m336k6_cleanup(
                candidates=(_candidate("/home/ibicza/stale"),),
                preservation_set=_set(),
                mode=M336K6CleanupMode.PRE_FREEZE,
                phase=phase,
            )


def _manifest_dict() -> dict:
    entries = [asdict(M336K6CapsuleContentEntry("src/a.py", 1, H))]
    body = {
        "schema_version": 1,
        "contract_role": "M336K6_CAPSULE_CONTENT_MANIFEST",
        "execution_strategy": "PROTECTED_DETACHED_GIT_WORKTREE",
        "implementation_sha": SHA,
        "entries": entries,
        "entry_count": 1,
        "byte_count": 1,
        "source_tree_hash": content_hash(tuple(entries)),
        "uv_lock_hash": H,
        "pyproject_toml_hash": H,
    }
    return {**body, "manifest_hash": content_hash(body)}
