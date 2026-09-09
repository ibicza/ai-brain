from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336j_evaluator_v2 import (
    M336J3_EVALUATOR_EVENTS,
    M336JEvaluatorLedgerV2,
    M336JEvaluatorReservationInputV2,
    advance_m336j_evaluator_v2,
    reserve_m336j_evaluator_v2,
    verify_m336j_evaluator_ready_for_evaluation_v2,
)
from ai_brain.stage3.acquisition.m336j_final_v2 import (
    M336J3_BRANCH_NAME,
    M336J3_EXACT_Q25_SHA,
    M336J3_F26_SUBJECT,
    M336J3_Q26_SUBJECT,
    M336J3_R26_SUBJECT,
    M336JFinalV2Error,
    build_m336j_f26_frozen_file_manifest,
    build_m336j_final_authorization_v2,
    build_m336j_final_freeze_lineage_policy_v2,
    build_m336j_final_freeze_manifest_v2,
    build_m336j_git_executable_receipt_v2,
    dump_m336j_f26_frozen_file_manifest,
    dump_m336j_final_authorization_v2,
    load_m336j_f26_frozen_file_manifest,
    load_m336j_final_authorization_input_v2,
    load_m336j_final_authorization_v2,
    load_m336j_final_freeze_manifest_v2,
    verify_m336j_authorization_manifest_cross_bindings_v2,
    verify_m336j_f26_frozen_file_manifest,
    verify_m336j_final_freeze_lineage_v2,
)
from ai_brain.stage3.acquisition.m336j_publication_v2 import (
    _reject_private_payload,
    _reject_public_json_payload,
)

ROOT = Path(__file__).resolve().parents[1]
GIT = Path(shutil.which("git") or "").resolve(strict=True)

M336J3_MUTATION_CASES = (
    ("JSON_HOSTS_ARRAY_NOT_CONVERTED", "AUTHORIZATION_CODEC"),
    ("DUPLICATE_HOST", "AUTHORIZATION_CODEC"),
    ("UNSORTED_HOST", "AUTHORIZATION_CODEC"),
    ("UNKNOWN_AUTHORIZATION_FIELD", "AUTHORIZATION_CODEC"),
    ("MISSING_MANIFEST_HASH", "FREEZE_MANIFEST_CODEC"),
    ("WRONG_MANIFEST_HASH", "FREEZE_MANIFEST_CODEC"),
    ("MISSING_SPDX_BINDING", "FREEZE_MANIFEST_CODEC"),
    ("WRONG_SPDX_BINDING", "AUTHORIZATION_MANIFEST_CROSS_BINDING"),
    ("MISSING_CAPSULE_BINDING", "FREEZE_MANIFEST_CODEC"),
    ("WRONG_PYTHON_ENVIRONMENT_HASH", "AUTHORIZATION_MANIFEST_CROSS_BINDING"),
    ("WRONG_DEPENDENCY_MANIFEST", "AUTHORIZATION_MANIFEST_CROSS_BINDING"),
    ("WRONG_COMMAND_RENDERER", "AUTHORIZATION_MANIFEST_CROSS_BINDING"),
    ("WRONG_MINIMAL_ENVIRONMENT_POLICY", "AUTHORIZATION_MANIFEST_CROSS_BINDING"),
    ("CANDIDATE_POOL_HASH_CHANGED", "AUTHORIZATION_MANIFEST_CROSS_BINDING"),
    ("ACQUISITION_POLICY_HASH_CHANGED", "AUTHORIZATION_MANIFEST_CROSS_BINDING"),
    ("THRESHOLD_HASH_CHANGED", "AUTHORIZATION_MANIFEST_CROSS_BINDING"),
    ("RUN_ID_MISMATCH", "AUTHORIZATION_CODEC"),
    ("Q26_PARENT_CHANGED", "GIT_OBJECT_LINEAGE"),
    ("R26_PARENT_CHANGED", "GIT_OBJECT_LINEAGE"),
    ("MERGE_INSERTED", "GIT_OBJECT_LINEAGE"),
    ("EXTRA_COMMIT_INSERTED", "GIT_OBJECT_LINEAGE"),
    ("BARE_GIT_SUBSTITUTED", "GIT_EXECUTABLE_BINDING"),
    ("WRONG_GIT_BINARY", "GIT_EXECUTABLE_BINDING"),
    ("PREFLIGHT_LEDGER_WRITE_BEFORE_LINEAGE", "CONTROLLER_PREFLIGHT_ORDER"),
    ("GOLDENS_BEFORE_EVALUATOR_RESERVATION", "EVALUATOR_RESERVATION"),
    ("EVALUATOR_RESERVATION_REPEATED", "EVALUATOR_LEDGER"),
    ("EVALUATOR_CRASH_RETRY", "EVALUATOR_LEDGER"),
    ("H26_SOURCE_BEARING_PACK", "H26_PUBLICATION"),
    ("E26_CANDIDATE_PACK_CHANGE", "E26_COMMIT_PROTOCOL"),
    ("SELF_REFERENTIAL_OUTCOME_ARTIFACT", "E26_PUBLICATION"),
)


def _authorization_input(**changes):
    hashes = {
        "q26_staging_tree_hash": "1" * 64,
        "prospective_f26_freeze_identity": "2" * 64,
        "route_registry_hash": "3" * 64,
        "route_manifest_hash": "4" * 64,
        "acquisition_provider_source_hash": "5" * 64,
        "acquisition_provider_callable_signature_hash": "6" * 64,
        "candidate_pool_hash": "7" * 64,
        "acquisition_policy_hash": "8" * 64,
        "denylist_hash": "9" * 64,
        "authority_root_hash": "a" * 64,
        "selector_policy_hash": "b" * 64,
        "threshold_manifest_hash": "c" * 64,
        "publication_boundary_hash": "d" * 64,
        "public_artifact_contract_hash": "e" * 64,
        "spdx_reference_binding_hash": "f" * 64,
        "execution_capsule_public_receipt_hash": "0" * 64,
        "python_environment_manifest_hash": "1" * 64,
        "executable_dependency_manifest_hash": "2" * 64,
        "remote_command_renderer_hash": "3" * 64,
        "minimal_environment_policy_hash": "4" * 64,
        "windows_public_jdk_identity_receipt_hash": "5" * 64,
        "karina_public_jdk_identity_receipt_hash": "6" * 64,
        "karina_stable_host_identity_receipt_hash": "7" * 64,
    }
    value = {
        "acquisition_mode": "FINAL",
        "exact_q26_sha": "2" * 40,
        "exact_r26_sha": "1" * 40,
        **hashes,
        "acquisition_run_id": "m336i.final-java.global-acquisition.v1",
        "branch_ref": "refs/heads/exp/stage3-m336j3-final-freeze-handshake-v10",
        "allowed_network_hosts": [
            "codeload.github.com",
            "github.com",
            "repo.maven.apache.org",
        ],
        "expected_global_acquisition_count": 1,
        "expected_windows_acquisition_count": 1,
        "expected_karina_acquisition_count": 0,
    }
    value.update(changes)
    return value


def _typed_authorization(tmp_path: Path):
    path = tmp_path / "input.json"
    write_canonical_json(path, _authorization_input())
    return build_m336j_final_authorization_v2(
        load_m336j_final_authorization_input_v2(path)
    )


def test_authorization_json_typed_roundtrip_is_byte_identical(tmp_path: Path) -> None:
    authorization = _typed_authorization(tmp_path)
    encoded = dump_m336j_final_authorization_v2(authorization)
    path = tmp_path / "authorization.json"
    path.write_bytes(encoded)
    loaded = load_m336j_final_authorization_v2(path)
    assert loaded == authorization
    assert dump_m336j_final_authorization_v2(loaded) == encoded
    assert isinstance(loaded.allowed_network_hosts, tuple)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("allowed_network_hosts", "github.com"),
        ("allowed_network_hosts", ["github.com", "codeload.github.com"]),
        ("allowed_network_hosts", ["github.com", "github.com"]),
        ("allowed_network_hosts", ["GITHUB.com"]),
        ("allowed_network_hosts", [" github.com"]),
        ("expected_global_acquisition_count", 2),
        ("exact_q26_sha", "2" * 39),
        ("exact_r26_sha", "1" * 39),
        ("prospective_f26_freeze_identity", "x" * 64),
        ("route_manifest_hash", "x" * 64),
        ("python_environment_manifest_hash", "x" * 64),
    ),
)
def test_authorization_input_mutations_fail(
    tmp_path: Path, field: str, value: object
) -> None:
    path = tmp_path / "input.json"
    write_canonical_json(path, _authorization_input(**{field: value}))
    with pytest.raises(M336JFinalV2Error):
        load_m336j_final_authorization_input_v2(path)


def test_authorization_unknown_and_duplicate_json_keys_fail(tmp_path: Path) -> None:
    unknown = _authorization_input(unknown=True)
    path = tmp_path / "unknown.json"
    write_canonical_json(path, unknown)
    with pytest.raises(M336JFinalV2Error):
        load_m336j_final_authorization_input_v2(path)
    duplicate = tmp_path / "duplicate.json"
    raw = json.dumps(_authorization_input(), sort_keys=True, separators=(",", ":"))
    duplicate.write_text(
        raw[:-1] + ',"branch_ref":"refs/heads/forged"}\n',
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ValueError, match="duplicate key"):
        load_m336j_final_authorization_input_v2(duplicate)


def test_authorization_hash_and_freeze_cross_binding_mutations_fail(
    tmp_path: Path,
) -> None:
    authorization = _typed_authorization(tmp_path)
    with pytest.raises(M336JFinalV2Error):
        load_m336j_final_authorization_v2(
            {
                **asdict(authorization),
                "authorization_hash": "0" * 64,
            }
        )
    manifest = build_m336j_final_freeze_manifest_v2(authorization=authorization)
    verify_m336j_authorization_manifest_cross_bindings_v2(authorization, manifest)
    for field in (
        "spdx_reference_binding_hash",
        "execution_capsule_public_receipt_hash",
        "python_environment_manifest_hash",
        "executable_dependency_manifest_hash",
        "remote_command_renderer_hash",
        "minimal_environment_policy_hash",
        "candidate_pool_hash",
        "acquisition_policy_hash",
        "threshold_manifest_hash",
    ):
        body = asdict(manifest)
        body[field] = "0" * 64 if body[field] != "0" * 64 else "f" * 64
        body_without_hash = dict(body)
        body_without_hash.pop("manifest_hash")
        body["manifest_hash"] = content_hash(body_without_hash)
        mutated = load_m336j_final_freeze_manifest_v2(body)
        with pytest.raises(M336JFinalV2Error):
            verify_m336j_authorization_manifest_cross_bindings_v2(
                authorization, mutated
            )


def test_freeze_manifest_missing_unknown_and_wrong_hash_fail(tmp_path: Path) -> None:
    manifest = build_m336j_final_freeze_manifest_v2(
        authorization=_typed_authorization(tmp_path)
    )
    value = asdict(manifest)
    for mutation in (
        {key: item for key, item in value.items() if key != "manifest_hash"},
        {**value, "unknown": True},
        {**value, "manifest_hash": "0" * 64},
    ):
        with pytest.raises(M336JFinalV2Error):
            load_m336j_final_freeze_manifest_v2(mutation)


def test_f26_frozen_file_manifest_is_exact_and_complete() -> None:
    manifest = build_m336j_f26_frozen_file_manifest(ROOT)
    assert manifest.file_count == 20
    assert len({row.destination_path for row in manifest.files}) == 20
    assert all(len(row.bytes_hash) == 64 for row in manifest.files)
    encoded = dump_m336j_f26_frozen_file_manifest(manifest)
    assert load_m336j_f26_frozen_file_manifest(json.loads(encoded)) == manifest
    with pytest.raises(M336JFinalV2Error):
        verify_m336j_f26_frozen_file_manifest(
            replace(manifest, files=tuple(reversed(manifest.files)))
        )


def test_mutation_registry_is_exactly_the_required_thirty_cases() -> None:
    assert len(M336J3_MUTATION_CASES) == 30
    assert len({name for name, _layer in M336J3_MUTATION_CASES}) == 30
    assert all(name and layer for name, layer in M336J3_MUTATION_CASES)


def test_publication_rejects_source_absolute_paths_and_e26_self_reference(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "Leaked.java").write_text("class Leaked {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source"):
        _reject_private_payload(source)

    absolute = tmp_path / "absolute"
    absolute.mkdir()
    write_canonical_json(absolute / "receipt.json", {"path": "C:/private/item"})
    with pytest.raises(ValueError, match="absolute host path"):
        _reject_public_json_payload(absolute, reject_e26_identity=False)

    self_reference = tmp_path / "self-reference"
    self_reference.mkdir()
    write_canonical_json(self_reference / "evidence.json", {"exact_e26_sha": "0" * 40})
    with pytest.raises(ValueError, match="self-referential"):
        _reject_public_json_payload(self_reference, reject_e26_identity=True)


def test_schema_covers_all_typed_handshake_boundaries() -> None:
    schema = json.loads(
        (ROOT / "schemas/stage3/m336j_final_handshake_v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert {
        "authorizationInput",
        "authorization",
        "freezeManifest",
        "frozenFile",
        "frozenFileManifest",
    }.issubset(schema["$defs"])


def _hashed(path: Path, field: str, **body) -> dict:
    value = {**body, field: content_hash(body)}
    write_canonical_json(path, value)
    return value


def _evaluator_fixture(tmp_path: Path):
    neutral = {
        "schema_version": 1,
        "status": "PASS",
        "trusted_count": 1,
    }
    windows = _hashed(
        tmp_path / "windows.json",
        "seal_hash",
        **neutral,
        platform_role="WINDOWS",
        production_request_hash="1" * 64,
        production_response_hash="2" * 64,
    )
    karina = _hashed(
        tmp_path / "karina.json",
        "seal_hash",
        **neutral,
        platform_role="KARINA",
        production_request_hash="3" * 64,
        production_response_hash="4" * 64,
    )
    selected = _hashed(
        tmp_path / "selected.json",
        "manifest_hash",
        schema_version=1,
        files=[],
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "sealed.bin").write_bytes(b"sealed rehearsal bytes\n")
    request = M336JEvaluatorReservationInputV2(
        windows_production_seal=tmp_path / "windows.json",
        karina_production_seal=tmp_path / "karina.json",
        selected_manifest=tmp_path / "selected.json",
        sealed_vault=vault,
        evaluator_implementation_hash="5" * 64,
        evaluator_jdk_identity_hash="6" * 64,
        golden_output_destination=tmp_path / "goldens.json",
        evaluation_run_id="m336j3.final-java.independent-evaluation.v2",
    )
    return request, windows, karina, selected


def test_evaluator_is_reserved_before_goldens_and_cannot_retry(tmp_path: Path) -> None:
    request, *_ = _evaluator_fixture(tmp_path)
    ledger = M336JEvaluatorLedgerV2(tmp_path / "evaluator.jsonl")
    receipt = reserve_m336j_evaluator_v2(request, ledger)
    assert tuple(item.event for item in ledger.events()) == M336J3_EVALUATOR_EVENTS[:4]
    with pytest.raises(ValueError, match="already used"):
        reserve_m336j_evaluator_v2(request, ledger)
    advance_m336j_evaluator_v2(
        ledger,
        "INDEPENDENT_GOLDEN_GENERATION_STARTED",
        context_hash=receipt.context_hash,
        operation_hash=receipt.receipt_hash,
    )
    request.golden_output_destination.write_text("{}\n", encoding="utf-8", newline="\n")
    advance_m336j_evaluator_v2(
        ledger,
        "INDEPENDENT_GOLDEN_GENERATION_COMPLETED",
        context_hash=receipt.context_hash,
        operation_hash=bytes_hash(request.golden_output_destination.read_bytes()),
    )
    verify_m336j_evaluator_ready_for_evaluation_v2(
        ledger, context_hash=receipt.context_hash
    )


@pytest.mark.parametrize("completed_events", (4, 5, 6, 7))
def test_evaluator_crash_after_reservation_is_terminal(
    tmp_path: Path, completed_events: int
) -> None:
    request, *_ = _evaluator_fixture(tmp_path)
    ledger = M336JEvaluatorLedgerV2(tmp_path / "evaluator.jsonl")
    receipt = reserve_m336j_evaluator_v2(request, ledger)
    for event in M336J3_EVALUATOR_EVENTS[4:completed_events]:
        advance_m336j_evaluator_v2(
            ledger,
            event,
            context_hash=receipt.context_hash,
            operation_hash=receipt.receipt_hash,
        )
    with pytest.raises(ValueError, match="already used"):
        reserve_m336j_evaluator_v2(request, ledger)


def _run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        (str(GIT), *args),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _commit(repository: Path, subject: str, name: str) -> str:
    (repository / name).write_text(subject + "\n", encoding="utf-8", newline="\n")
    _run("add", "-A", cwd=repository)
    _run("commit", "-m", subject, cwd=repository)
    return _run("rev-parse", "HEAD", cwd=repository)


def test_final_lineage_uses_real_git_objects_without_depth_shortcuts(
    tmp_path: Path,
) -> None:
    remote = tmp_path / "remote.git"
    repository = tmp_path / "repository"
    _run("init", "--bare", str(remote))
    _run("clone", "--no-local", str(ROOT), str(repository))
    _run("config", "user.email", "m336j3@example.invalid", cwd=repository)
    _run("config", "user.name", "M336J3 Test", cwd=repository)
    _run("remote", "set-url", "origin", str(remote), cwd=repository)
    _run("checkout", "--detach", M336J3_EXACT_Q25_SHA, cwd=repository)
    _run("checkout", "-B", M336J3_BRANCH_NAME, M336J3_EXACT_Q25_SHA, cwd=repository)
    r26 = _commit(repository, M336J3_R26_SUBJECT, "r26.txt")
    q26 = _commit(repository, M336J3_Q26_SUBJECT, "q26.txt")
    freeze = repository / "artifacts/acquisition/m336j_freeze_v10"
    freeze.mkdir(parents=True)
    (freeze / "final_authorization_v2.json").write_text(
        "{}\n", encoding="utf-8", newline="\n"
    )
    (freeze / "freeze_manifest_v2.json").write_text(
        "{}\n", encoding="utf-8", newline="\n"
    )
    _run(
        "add",
        "-f",
        "artifacts/acquisition/m336j_freeze_v10/final_authorization_v2.json",
        "artifacts/acquisition/m336j_freeze_v10/freeze_manifest_v2.json",
        cwd=repository,
    )
    f26 = _commit(repository, M336J3_F26_SUBJECT, "f26.txt")
    _run("push", "-u", "origin", M336J3_BRANCH_NAME, cwd=repository)
    git_receipt = build_m336j_git_executable_receipt_v2(
        GIT,
        execution_capsule_public_receipt_hash="1" * 64,
        environment_identity_hash="2" * 64,
    )
    policy = build_m336j_final_freeze_lineage_policy_v2(
        exact_r26_sha=r26,
        exact_q26_sha=q26,
        exact_f26_sha=f26,
    )
    receipt = verify_m336j_final_freeze_lineage_v2(repository, GIT, policy, git_receipt)
    assert receipt.ordered_commit_shas == (r26, q26, f26)
    assert receipt.merge_count == 0
    assert receipt.committed_freeze_byte_mismatch_count == 0
    _commit(repository, "unexpected extra commit", "extra.txt")
    with pytest.raises(M336JFinalV2Error):
        verify_m336j_final_freeze_lineage_v2(repository, GIT, policy, git_receipt)


def test_current_v2_authority_contains_no_depth_or_bare_git_shortcuts() -> None:
    current_files = (
        ROOT / "src/ai_brain/stage3/acquisition/m336j_final_v2.py",
        ROOT / "scripts/m336j_build_f26.py",
        ROOT / "scripts/m336j_publish_h26.py",
        ROOT / "scripts/m336j_publish_e26.py",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in current_files)
    assert "HEAD~" not in text
    assert "HEAD^2" not in text
    assert '("git",' not in text


def test_exact_git_binding_rejects_bare_and_wrong_executables() -> None:
    kwargs = {
        "execution_capsule_public_receipt_hash": "1" * 64,
        "environment_identity_hash": "2" * 64,
    }
    with pytest.raises((FileNotFoundError, M336JFinalV2Error)):
        build_m336j_git_executable_receipt_v2(Path("git"), **kwargs)
    with pytest.raises(M336JFinalV2Error):
        build_m336j_git_executable_receipt_v2(Path(sys.executable), **kwargs)


def test_controller_preflight_and_evaluator_reservation_precede_side_effects() -> None:
    text = (ROOT / "scripts/m336i_java_final_route.py").read_text(encoding="utf-8")
    final = text[
        text.index("def _final(") : text.index("def _write_final_failure_receipt")
    ]
    assert final.index(
        "validate_m336i_final_acquisition_request_before_side_effects"
    ) < (final.index("state = M336IRouteStateLedger"))
    assert final.index("reserve_m336j_evaluator_v2(") < final.index(
        "goldens = _author_goldens(args)"
    )
