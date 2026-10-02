from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k8_freeze import (
    M336K13_BRANCH,
    M336K13_READY_STATUS,
    M336K13_REQUIRED_FREEZE_COMPONENTS,
    M336K8FreezeManifest,
    materialize_m336k8_freeze,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k13_readiness import (
    M336K13FreezeReadinessSeal,
    M336K13VerifiedReceipt,
    build_m336k13_freeze_readiness,
    verify_m336k13_freeze_readiness_sources,
)

_TIP = "a" * 40
_ROOT = Path(__file__).resolve().parents[1]


def _receipt(**values: Any) -> dict[str, Any]:
    body = {
        "schema_version": 1,
        "contract_role": values.pop("contract_role", "TEST_M336K13_RECEIPT"),
        "status": "PASS",
        **values,
    }
    return {**body, "receipt_hash": content_hash(body)}


def _fixture(
    tip: str = _TIP,
) -> tuple[M336K13FreezeReadinessSeal, dict[str, dict[str, Any]]]:
    registry = m336k_official_profile_registry()
    profile = registry.profile("m336k8-final-v6")
    reservation = _receipt(
        exact_implementation_tip=tip,
        released=False,
        reused=False,
    )
    raw = {
        "official_acquisition_static_readiness": _receipt(
            exact_source_sha=tip,
            source_request_count=0,
            source_body_byte_count=0,
        ),
        "official_unspent_state": _receipt(
            exact_implementation_tip=tip,
            source_request_count=0,
            source_body_byte_count=0,
            candidate_body_count=0,
            official_one_shot_counter_count=0,
            official_ledger_count=0,
            official_route_event_count=0,
            official_vault_state="ABSENT",
            final_request_state="ABSENT",
            post_freeze_validation_receipt_state="ABSENT",
            reservation_release_receipt_state="ABSENT",
        ),
        "leak_report": _receipt(
            exact_source_sha=tip,
            source_body_byte_count=0,
            candidate_body_count=0,
            source_leak_count=0,
            private_artifact_count=0,
            raw_private_path_count=0,
        ),
        "generation4_storage_reservation": reservation,
        "generation4_pre_resource_gate": _receipt(
            exact_implementation_tip=tip,
            preserved_reservation_count=5,
        ),
        "generation4_post_resource_gate": _receipt(
            exact_implementation_tip=tip,
            generation4_reservation_receipt_hash=reservation["receipt_hash"],
            generation4_reservation_released=False,
            generation4_reservation_reused=False,
            total_preserved_reservation_count=6,
            total_released_reservation_count=0,
        ),
        "generation_supersession": _receipt(
            exact_implementation_tip=tip,
            active_generation_count=1,
            preserved_superseded_generation_count=3,
        ),
        "evidence_binding_manifest": _receipt(exact_implementation_tip=tip),
    }
    verified = {
        name: M336K13VerifiedReceipt.from_dict(value) for name, value in raw.items()
    }
    seal = build_m336k13_freeze_readiness(
        active_profile=profile,
        profile_registry=registry,
        official_acquisition_static_readiness=verified[
            "official_acquisition_static_readiness"
        ],
        official_unspent_state=verified["official_unspent_state"],
        leak_report=verified["leak_report"],
        current_storage_reservation=verified["generation4_storage_reservation"],
        pre_resource_gate=verified["generation4_pre_resource_gate"],
        post_resource_gate=verified["generation4_post_resource_gate"],
        generation_supersession=verified["generation_supersession"],
        evidence_binding_manifest=verified["evidence_binding_manifest"],
        exact_implementation_tip=tip,
        qualification_label="Q38U",
    )
    return seal, raw


def _rehash_readiness(value: dict[str, Any]) -> dict[str, Any]:
    body = dict(value)
    body.pop("readiness_hash", None)
    return {**body, "readiness_hash": content_hash(body)}


def _rewrite_receipt(value: dict[str, Any], **changes: Any) -> dict[str, Any]:
    body = dict(value)
    body.pop("receipt_hash")
    body.update(changes)
    return {**body, "receipt_hash": content_hash(body)}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _write_readiness_evidence(
    root: Path,
    seal: M336K13FreezeReadinessSeal,
    raw: dict[str, dict[str, Any]],
) -> Path:
    registry = m336k_official_profile_registry()
    profile = registry.profile("m336k8-final-v6")
    for name, value in raw.items():
        if name == "generation_supersession":
            continue
        _write_json(root / f"{name}.json", value)
    _write_json(root / "active_official_profile.json", profile.canonical_object())
    _write_json(root / "official_profile_registry.json", registry.canonical_object())
    path = root / "readiness.json"
    _write_json(path, seal.canonical_object())
    return path


def test_exact_q38u_readiness_is_accepted(tmp_path: Path) -> None:
    seal, raw = _fixture()
    path = _write_readiness_evidence(tmp_path, seal, raw)

    loaded = M336K13FreezeReadinessSeal.from_dict(
        json.loads(path.read_text(encoding="utf-8"))
    )
    verify_m336k13_freeze_readiness_sources(path, loaded)

    assert loaded.new_final_source_body_bytes == 0
    assert loaded.readiness_hash == seal.readiness_hash


_PARSER_MUTATIONS = (
    ("new_final_source_body_bytes", None),
    ("new_final_source_body_bytes", "0"),
    ("new_final_source_body_bytes", False),
    ("new_final_source_body_bytes", -1),
    ("new_final_source_body_bytes", 1),
    ("status", None),
    ("status", "WRONG"),
    ("branch_ref", "refs/heads/wrong"),
    ("active_official_profile_id", "historical"),
    ("official_one_shot_counter_count", 1),
    ("official_one_shot_counter_count", False),
    ("official_ledger_count", 1),
    ("official_route_event_count", 1),
    ("official_source_request_count", 1),
    ("official_candidate_body_count", 1),
    ("source_leak_count", 1),
    ("private_artifact_count", 1),
    ("raw_private_path_count", 1),
    ("official_vault_state", "PRESENT"),
    ("final_request_state", "PRESENT"),
    ("post_freeze_validation_receipt_state", "PRESENT"),
    ("reservation_release_receipt_state", "PRESENT"),
    ("active_generation_count", 0),
    ("preserved_superseded_generation_count", 1),
    ("preserved_reservation_count", 4),
    ("schema_version", True),
    ("schema_version", 2),
    ("qualification_label", "Q38S"),
    ("contract_role", "PUBLIC_SAFE_M336K13_Q38S_READINESS"),
)


@pytest.mark.parametrize(("field_name", "changed"), _PARSER_MUTATIONS)
def test_typed_parser_rejects_semantic_mutations(field_name: str, changed: Any) -> None:
    value = _fixture()[0].canonical_object()
    value[field_name] = changed

    with pytest.raises(M336K2ProtocolError):
        M336K13FreezeReadinessSeal.from_dict(_rehash_readiness(value))


def test_typed_parser_rejects_missing_source_body_without_key_error() -> None:
    value = _fixture()[0].canonical_object()
    value.pop("new_final_source_body_bytes")

    with pytest.raises(M336K2ProtocolError, match="freeze readiness fields changed"):
        M336K13FreezeReadinessSeal.from_dict(_rehash_readiness(value))


def test_typed_parser_rejects_extra_field_and_stale_hash() -> None:
    exact = _fixture()[0].canonical_object()
    extra = {**exact, "unknown": 0}
    stale = {**exact, "readiness_hash": "f" * 64}

    with pytest.raises(M336K2ProtocolError, match="fields changed"):
        M336K13FreezeReadinessSeal.from_dict(extra)
    with pytest.raises(M336K2ProtocolError, match="readiness is invalid"):
        M336K13FreezeReadinessSeal.from_dict(stale)


def test_materialization_binding_rejects_wrong_implementation_tip() -> None:
    seal = _fixture()[0]

    with pytest.raises(M336K2ProtocolError, match="does not match materialization"):
        seal.verify_for_materialization(
            exact_implementation_tip="b" * 40,
            expected_status=M336K13_READY_STATUS,
            expected_branch=M336K13_BRANCH,
        )


@pytest.mark.parametrize(
    "artifact",
    (
        "artifacts/m336k13/q38/readiness.json",
        "artifacts/m336k13/q38r/readiness.json",
        "artifacts/m336k13/q38s/readiness.json",
        "artifacts/m336k13/q38t/readiness.json",
    ),
)
def test_historical_readiness_is_diagnostic_only(artifact: str) -> None:
    root = Path(__file__).resolve().parents[1]
    value = json.loads((root / artifact).read_text(encoding="utf-8"))

    with pytest.raises(M336K2ProtocolError, match="fields changed|is invalid"):
        M336K13FreezeReadinessSeal.from_dict(value)


@pytest.mark.parametrize(
    ("source_name", "field_name", "changed"),
    (
        ("official_acquisition_static_readiness", "source_body_byte_count", 1),
        ("official_acquisition_static_readiness", "source_request_count", 1),
        ("official_unspent_state", "source_body_byte_count", 1),
        ("official_unspent_state", "source_request_count", 1),
        ("official_unspent_state", "candidate_body_count", 1),
        ("leak_report", "source_leak_count", 1),
        ("leak_report", "private_artifact_count", 1),
        ("leak_report", "raw_private_path_count", 1),
        ("generation_supersession", "active_generation_count", 2),
        (
            "generation_supersession",
            "preserved_superseded_generation_count",
            1,
        ),
        ("generation4_post_resource_gate", "total_preserved_reservation_count", 5),
        ("generation4_post_resource_gate", "total_released_reservation_count", 1),
    ),
)
def test_builder_rejects_fully_rehashed_source_mutations(
    source_name: str, field_name: str, changed: Any
) -> None:
    _, raw = _fixture()
    raw[source_name] = _rewrite_receipt(raw[source_name], **{field_name: changed})
    verified = {
        name: M336K13VerifiedReceipt.from_dict(value) for name, value in raw.items()
    }
    registry = m336k_official_profile_registry()

    with pytest.raises(M336K2ProtocolError):
        build_m336k13_freeze_readiness(
            active_profile=registry.profile("m336k8-final-v6"),
            profile_registry=registry,
            official_acquisition_static_readiness=verified[
                "official_acquisition_static_readiness"
            ],
            official_unspent_state=verified["official_unspent_state"],
            leak_report=verified["leak_report"],
            current_storage_reservation=verified["generation4_storage_reservation"],
            pre_resource_gate=verified["generation4_pre_resource_gate"],
            post_resource_gate=verified["generation4_post_resource_gate"],
            generation_supersession=verified["generation_supersession"],
            evidence_binding_manifest=verified["evidence_binding_manifest"],
            exact_implementation_tip=_TIP,
            qualification_label="Q38U",
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "official_acquisition_static_readiness_hash",
        "official_unspent_state_hash",
        "leak_report_hash",
        "current_storage_reservation_receipt_hash",
        "generation_resource_gate_hash",
        "evidence_binding_manifest_hash",
        "active_official_profile_hash",
        "active_profile_registry_hash",
    ),
)
def test_source_verifier_rejects_rehashed_binding_mutations(
    tmp_path: Path, field_name: str
) -> None:
    seal, raw = _fixture()
    value = seal.canonical_object()
    value[field_name] = "f" * 64
    path = _write_readiness_evidence(
        tmp_path,
        M336K13FreezeReadinessSeal.from_dict(_rehash_readiness(value)),
        raw,
    )

    with pytest.raises(M336K2ProtocolError, match="source evidence changed"):
        verify_m336k13_freeze_readiness_sources(
            path,
            M336K13FreezeReadinessSeal.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            ),
        )


def test_materializer_rejects_malformed_readiness_before_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai_brain.stage3.acquisition.m336k8_freeze as freeze

    root = tmp_path / "repo"
    root.mkdir()
    readiness = root / "readiness.json"
    value = _fixture()[0].canonical_object()
    value.pop("new_final_source_body_bytes")
    _write_json(readiness, _rehash_readiness(value))
    output = root / "artifacts/m336k13/f38-freeze"
    monkeypatch.setattr(freeze, "_verify_qualification_lineage", lambda *args: None)

    with pytest.raises(M336K2ProtocolError, match="fields changed"):
        materialize_m336k8_freeze(
            repository=root,
            git_executable=Path(shutil.which("git") or "git"),
            exact_implementation_tip=_TIP,
            exact_qualification_sha="b" * 40,
            readiness=readiness,
            component_sources={
                name: readiness for name in M336K13_REQUIRED_FREEZE_COMPONENTS
            },
            output=output,
            expected_branch=M336K13_BRANCH,
            freeze_relative_root="artifacts/m336k13/f38-freeze",
            readiness_status=M336K13_READY_STATUS,
            freeze_role=M336K8FreezeManifest.ROLE_V6,
            required_components=M336K13_REQUIRED_FREEZE_COMPONENTS,
            build_receipt_name="prospective_freeze_build_receipt.json",
            allow_unpublished_qualification=True,
        )
    assert not output.exists()


_COMPONENT_HASH_FIELDS = {
    "final_authorization": "authorization_hash",
    "typed_route_manifest": "manifest_hash",
    "route_identity_bundle": "bundle_hash",
    "canonical_request_builder_identity": "builder_hash",
    "post_freeze_input_bundle": "bundle_hash",
    "controller_source_identity_receipt": "receipt_hash",
    "controller_startup_binding": "binding_hash",
    "persistent_capsule_source_binding": "binding_hash",
    "bridge_surface_manifest": "manifest_hash",
    "source_domain_compatibility": "receipt_hash",
    "freeze_assembly_plan": "plan_hash",
    "freeze_assembly_receipt": "receipt_hash",
    "frozen_contract_compatibility_v2": "report_hash",
    "active_official_profile": "profile_hash",
    "official_profile_registry": "registry_hash",
    "profile_coverage_gate": "gate_hash",
    "controller_admission_contract": "contract_hash",
    "official_candidate_pool_binding": "binding_hash",
    "official_network_authority_manifest": "manifest_hash",
    "acquisition_policy": "acquisition_policy_hash",
    "official_acquisition_binding_receipt": "receipt_hash",
    "official_provider_configuration": "configuration_hash",
    "stage_request_acquisition_binding": "binding_hash",
    "acquisition_ledger_context_template": "template_hash",
    "official_freeze_origin_receipt": "receipt_hash",
    "official_controller_executable_binding": "binding_hash",
    "effective_environment_binding": "receipt_hash",
    "execution_capsule_receipt": "receipt_hash",
    "native_route_manifest": "manifest_hash",
    "official_executable_binding_receipt": "receipt_hash",
    "native_stage_plan_binding": "plan_binding_hash",
    "producer_consumer_parity_receipt": "receipt_hash",
    "native_stage_dispatches": "receipt_hash",
    "final_controller_plan_binding_receipt": "receipt_hash",
}


def _component_sources(root: Path) -> dict[str, Path]:
    result = {}
    fixed_hash = content_hash("m336k13-test-component")
    for name in sorted(M336K13_REQUIRED_FREEZE_COMPONENTS):
        body: dict[str, Any] = {
            "schema_version": 1,
            "contract_role": f"TEST_{name.upper()}",
            "status": "PASS",
        }
        if name == "active_official_profile":
            body["profile_id"] = "m336k8-final-v6"
        if name == "native_stage_dispatches":
            body["dispatch_contract_hash"] = fixed_hash
        if name == "candidate_pool":
            value = {**body, "pool_hash": fixed_hash}
        else:
            field_name = _COMPONENT_HASH_FIELDS.get(name, "receipt_hash")
            value = {**body, field_name: content_hash(body)}
        path = root / "inputs" / f"{name}.json"
        _write_json(path, value)
        result[name] = path
    return result


def _git(root: Path, *arguments: str) -> str:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable")
    return subprocess.run(
        (git, "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _build_materializer_repository(
    root: Path,
    *,
    readiness_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    parent_mismatch: bool = False,
    source_diff: bool = False,
    dirty: bool = False,
    remote_mismatch: bool = False,
) -> tuple[Path, str, str, dict[str, Path]]:
    remote = root.parent / f"{root.name}-remote.git"
    remote.mkdir(parents=True)
    _git(remote, "init", "--bare")
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "m336k13@example.invalid")
    _git(root, "config", "user.name", "M336K13 Test")
    _git(root, "checkout", "-b", M336K13_BRANCH)
    (root / "src").mkdir()
    (root / "src" / "implementation.py").write_text(
        "VALUE = 1\n", encoding="utf-8", newline="\n"
    )
    components = _component_sources(root)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "implementation")
    implementation = _git(root, "rev-parse", "HEAD")
    if parent_mismatch:
        (root / "notes").mkdir()
        (root / "notes" / "intermediate.txt").write_text("x\n", encoding="utf-8")
        _git(root, "add", ".")
        _git(root, "commit", "-m", "intermediate evidence")

    seal, raw = _fixture(implementation)
    readiness_root = root / "artifacts/m336k13/q38u"
    readiness_value = seal.canonical_object()
    if readiness_mutator is not None:
        readiness_value = readiness_mutator(deepcopy(readiness_value))
        readiness_value = _rehash_readiness(readiness_value)
    _write_readiness_evidence(readiness_root, seal, raw)
    if readiness_mutator is not None:
        _write_json(readiness_root / "readiness.json", readiness_value)
    if source_diff:
        (root / "src" / "qualification_change.py").write_text(
            "CHANGED = True\n", encoding="utf-8", newline="\n"
        )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "qualification")
    qualification = _git(root, "rev-parse", "HEAD")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", M336K13_BRANCH)
    if dirty:
        (root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    if remote_mismatch:
        peer = root.parent / f"{root.name}-peer"
        git = shutil.which("git")
        assert git is not None
        subprocess.run(
            (git, "clone", "--branch", M336K13_BRANCH, str(remote), str(peer)),
            check=True,
        )
        _git(peer, "config", "user.email", "peer@example.invalid")
        _git(peer, "config", "user.name", "Peer")
        (peer / "remote-only.txt").write_text("remote\n", encoding="utf-8")
        _git(peer, "add", ".")
        _git(peer, "commit", "-m", "remote mismatch")
        _git(peer, "push", "origin", M336K13_BRANCH)
    return readiness_root / "readiness.json", implementation, qualification, components


def _call_materializer(
    root: Path,
    readiness: Path,
    implementation: str,
    qualification: str,
    components: dict[str, Path],
) -> dict[str, Any]:
    git = shutil.which("git")
    assert git is not None
    return materialize_m336k8_freeze(
        repository=root,
        git_executable=Path(git),
        exact_implementation_tip=implementation,
        exact_qualification_sha=qualification,
        readiness=readiness,
        component_sources=components,
        output=root / "artifacts/m336k13/f38-freeze",
        expected_branch=M336K13_BRANCH,
        freeze_relative_root="artifacts/m336k13/f38-freeze",
        readiness_status=M336K13_READY_STATUS,
        freeze_role=M336K8FreezeManifest.ROLE_V6,
        required_components=M336K13_REQUIRED_FREEZE_COMPONENTS,
        build_receipt_name="prospective_freeze_build_receipt.json",
        allow_unpublished_qualification=True,
    )


def _call_official_materializer(
    root: Path,
    readiness: Path,
    implementation: str,
    qualification: str,
    components: dict[str, Path],
) -> dict[str, Any]:
    git = shutil.which("git")
    assert git is not None
    return materialize_m336k8_freeze(
        repository=root,
        git_executable=Path(git),
        exact_implementation_tip=implementation,
        exact_qualification_sha=qualification,
        readiness=readiness,
        component_sources=components,
        output=root / "artifacts/m336k13/f38-freeze",
        expected_branch=M336K13_BRANCH,
        freeze_relative_root="artifacts/m336k13/f38-freeze",
        readiness_status=M336K13_READY_STATUS,
        freeze_role=M336K8FreezeManifest.ROLE_V6,
        required_components=M336K13_REQUIRED_FREEZE_COMPONENTS,
        build_receipt_name="f38_build_receipt.json",
        allow_unpublished_qualification=False,
    )


def test_exact_materializer_accepts_typed_readiness_in_complete_git_chain(
    tmp_path: Path,
) -> None:
    root = tmp_path / "success"
    readiness, implementation, qualification, components = (
        _build_materializer_repository(root)
    )

    result = _call_materializer(
        root, readiness, implementation, qualification, components
    )

    output = root / "artifacts/m336k13/f38-freeze"
    assert result["status"] == "PASS"
    assert (output / "freeze_manifest.json").is_file()
    assert (output / "prospective_freeze_build_receipt.json").is_file()
    assert len(tuple((output / "components").iterdir())) == len(
        M336K13_REQUIRED_FREEZE_COMPONENTS
    )


def test_exact_official_precommit_materializer_accepts_f38_receipt_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "official-success"
    readiness, implementation, qualification, components = (
        _build_materializer_repository(root)
    )

    result = _call_official_materializer(
        root, readiness, implementation, qualification, components
    )

    output = root / "artifacts/m336k13/f38-freeze"
    manifest = json.loads(
        (output / "freeze_manifest.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "PASS"
    assert manifest["self_reference_safe_exclusions"] == [
        "artifacts/m336k13/f38-freeze/freeze_manifest.json",
        "artifacts/m336k13/f38-freeze/f38_build_receipt.json",
    ]
    assert (output / "f38_build_receipt.json").is_file()
    assert not (output / "prospective_freeze_build_receipt.json").exists()


def test_f38_entrypoint_accepts_exact_official_precommit_configuration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "official-entrypoint-success"
    readiness, implementation, qualification, components = (
        _build_materializer_repository(root)
    )
    output = root / "artifacts/m336k13/f38-freeze"
    configuration = tmp_path / "f38-configuration.json"
    _write_json(
        configuration,
        {
            "repository": str(root),
            "git_executable": str(Path(shutil.which("git") or "git")),
            "exact_implementation_tip": implementation,
            "exact_qualification_sha": qualification,
            "readiness": str(readiness),
            "component_sources": {
                name: str(path) for name, path in components.items()
            },
            "output": str(output),
            "expected_branch": M336K13_BRANCH,
            "freeze_relative_root": "artifacts/m336k13/f38-freeze",
        },
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            (str(_ROOT / "src"), environment.get("PYTHONPATH", "")),
        )
    )

    completed = subprocess.run(
        (
            sys.executable,
            str(_ROOT / "scripts/m336k13_materialize_f38.py"),
            "--configuration",
            str(configuration),
        ),
        cwd=_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    receipt = json.loads(completed.stdout)
    assert receipt["status"] == "PASS"
    assert (output / "f38_build_receipt.json").is_file()
    assert not (output / "prospective_freeze_build_receipt.json").exists()


def _remove_source_body(value: dict[str, Any]) -> dict[str, Any]:
    value.pop("new_final_source_body_bytes")
    return value


def _wrong_source_body(value: dict[str, Any]) -> dict[str, Any]:
    value["new_final_source_body_bytes"] = 1
    return value


def _stale_static_hash(value: dict[str, Any]) -> dict[str, Any]:
    value["official_acquisition_static_readiness_hash"] = "f" * 64
    return value


def _stale_unspent_hash(value: dict[str, Any]) -> dict[str, Any]:
    value["official_unspent_state_hash"] = "f" * 64
    return value


@pytest.mark.parametrize(
    ("readiness_mutator", "parent_mismatch", "source_diff", "dirty", "remote"),
    (
        (_remove_source_body, False, False, False, False),
        (_wrong_source_body, False, False, False, False),
        (_stale_static_hash, False, False, False, False),
        (_stale_unspent_hash, False, False, False, False),
        (None, True, False, False, False),
        (None, False, True, False, False),
        (None, False, False, True, False),
        (None, False, False, False, True),
    ),
)
def test_exact_materializer_rejects_closed_failure_matrix_before_destination(
    tmp_path: Path,
    readiness_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None,
    parent_mismatch: bool,
    source_diff: bool,
    dirty: bool,
    remote: bool,
) -> None:
    root = tmp_path / "failure"
    readiness, implementation, qualification, components = (
        _build_materializer_repository(
            root,
            readiness_mutator=readiness_mutator,
            parent_mismatch=parent_mismatch,
            source_diff=source_diff,
            dirty=dirty,
            remote_mismatch=remote,
        )
    )

    with pytest.raises(M336K2ProtocolError):
        _call_materializer(root, readiness, implementation, qualification, components)
    assert not (root / "artifacts/m336k13/f38-freeze").exists()
