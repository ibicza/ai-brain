from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_python_invocation,
    write_m336k5_python_invocation_plan,
)
from ai_brain.stage3.acquisition.m336k8_contracts import M336K8_BRIDGE_PATHS
from ai_brain.stage3.acquisition.m336k8_freeze import M336K8FreezeManifest
from ai_brain.stage3.acquisition.m336k8_request import _controller_target_source
from ai_brain.stage3.acquisition.m336k9_profiles import (
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k13_plan import (
    M336K13_BOOTSTRAP_REPOSITORY_PATH,
    M336K13_MUTATION_CASES,
    M336K13_PLAN_BINDING_CONSUMERS,
    M336K13ActualLauncherPlanReceipt,
    M336K13ActualLauncherPlanReceiptSchema,
    M336K13FinalControllerPlanLifecyclePolicy,
    M336K13FinalControllerPlanPathRoleManifest,
    _path_identity,
    build_m336k13_final_controller_plan_binding,
    build_m336k13_final_controller_plan_template,
    create_m336k13_final_controller_plan_once,
    verify_m336k13_final_controller_plan_binding,
)
from ai_brain.stage3.acquisition.m336k13_startup import (
    run_m336k13_python_invocation,
)


@dataclass(frozen=True)
class _SyntheticPreledgerReceipt:
    receipt_hash: str
    startup_receipt_hash: str
    actual_launcher_plan_receipt_hash: str
    final_controller_plan_binding_receipt_hash: str
    canonical_final_request_hash: str


def _tool(name: str) -> Path:
    value = shutil.which(name)
    if value is None:
        pytest.skip(f"required test executable is absent: {name}")
    return Path(value)


def test_m336k13_two_operation_preledger_comparison_is_stable_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    from m336k8_run_final_route import _stable_preledger_authority

    validate = _SyntheticPreledgerReceipt(
        receipt_hash="1" * 64,
        startup_receipt_hash="2" * 64,
        actual_launcher_plan_receipt_hash="3" * 64,
        final_controller_plan_binding_receipt_hash="4" * 64,
        canonical_final_request_hash="5" * 64,
    )
    execute = replace(
        validate,
        receipt_hash="6" * 64,
        startup_receipt_hash="7" * 64,
        actual_launcher_plan_receipt_hash="8" * 64,
    )
    assert _stable_preledger_authority(validate) == _stable_preledger_authority(execute)
    changed = replace(execute, canonical_final_request_hash="9" * 64)
    assert _stable_preledger_authority(validate) != _stable_preledger_authority(changed)


def test_m336k13_disposable_harness_reuses_one_exact_plan_source() -> None:
    source = Path("scripts/m336k5_qualify_disposable_protocol.py").read_text(
        encoding="utf-8"
    )
    assert 'final_controller_plan_generation != "m336k13"' in source
    assert '_run_m336k13_plan_operation(final_plan_state, "validate")' in source
    assert '_run_m336k13_plan_operation(final_plan_state, "execute")' in source
    helper = source.split("def _run_m336k13_plan_operation", maxsplit=1)[1].split(
        "def _persistent_disposable_private_root", maxsplit=1
    )[0]
    assert 'plan_path=state["plan_path"]' in helper
    assert 'execution_scope="REHEARSAL"' in helper


def test_m336k13_controller_source_domain_uses_v13_target() -> None:
    root = Path(__file__).resolve().parents[1]
    authorization = SimpleNamespace(official_profile_id="m336k8-final-v6")
    assert _controller_target_source(root, object(), authorization) == (
        root / "scripts/m336k13_run_final_route.py"
    )


def test_m336k13_controller_bootstrap_preserves_frozen_capsule_bridge() -> None:
    root = Path(__file__).resolve().parents[1]
    shared_paths = (
        "scripts/m336k5_python_bootstrap.py",
        "src/ai_brain/stage3/acquisition/m336k5_startup.py",
    )
    for relative in shared_paths:
        frozen = subprocess.run(
            (
                str(_tool("git")),
                "show",
                f"9de5a86082a12ce4be4b285bb3a91e8340fd2c72:{relative}",
            ),
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        assert (root / relative).read_bytes() == frozen
    bridge_paths = {relative for _role, relative in M336K8_BRIDGE_PATHS}
    assert M336K13_BOOTSTRAP_REPOSITORY_PATH not in bridge_paths
    assert (root / M336K13_BOOTSTRAP_REPOSITORY_PATH).is_file()


@pytest.fixture(scope="module")
def closure(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    root = Path(__file__).resolve().parents[1]
    private = tmp_path_factory.mktemp("m336k13-plan")
    request = private / "stable-final-request.json"
    validation = private / "post-freeze-validation.json"
    release = private / "reservation-release.json"
    validate_startup = private / "validate-startup.json"
    execute_startup = private / "execute-startup.json"
    plan_path = private / "final-controller-plan.json"
    target = root / "scripts/m336k13_run_final_route.py"
    bootstrap = root / "scripts/m336k13_final_controller_bootstrap.py"
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is absent")
    plan = build_m336k5_python_invocation(
        platform_role="WINDOWS",
        process_role="FINAL_CONTROLLER",
        python_executable=Path(sys.executable),
        git_executable=_tool("git"),
        powershell_executable=Path(powershell),
        repository=root,
        working_directory=root,
        bootstrap_script=bootstrap,
        target=target,
        validate_arguments=(
            "--request",
            str(request),
            "--validate-only",
            "--validation-receipt",
            str(validation),
        ),
        execute_arguments=(
            "--request",
            str(request),
            "--post-freeze-validation-receipt",
            str(validation),
            "--reservation-release-receipt",
            str(release),
        ),
        validate_startup_receipt=validate_startup,
        execute_startup_receipt=execute_startup,
    )
    template = build_m336k13_final_controller_plan_template(
        target_source_hash=bytes_hash(target.read_bytes()),
        bootstrap_source_hash=bytes_hash(bootstrap.read_bytes()),
    )
    lifecycle = create_m336k13_final_controller_plan_once(
        plan=plan,
        plan_path=plan_path,
        template=template,
        exact_implementation_tip="1" * 40,
        exact_qualification_sha="2" * 40,
    )
    binding = build_m336k13_final_controller_plan_binding(
        plan=plan,
        plan_path=plan_path,
        template=template,
        lifecycle=lifecycle,
    )
    startup_hash = content_hash("startup")
    validate_startup.write_text(
        canonical_json({"receipt_hash": startup_hash}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    actual_body = {
        "schema_version": 1,
        "contract_role": M336K13ActualLauncherPlanReceipt.ROLE,
        "execution_scope": "OFFICIAL_CONTROLLER",
        "actual_invocation_plan_hash": plan.invocation_plan_hash,
        "actual_plan_bytes_hash": bytes_hash(plan_path.read_bytes()),
        "actual_plan_file_identity_hash": _path_identity(plan_path),
        "selected_operation": "validate",
        "selected_target_kind": "SCRIPT",
        "selected_target_source_hash": plan.expected_target_source_hash,
        "selected_operation_argument_hash": content_hash(plan.validate_arguments),
        "startup_receipt_hash": startup_hash,
        "startup_policy_hash": plan.startup_policy.policy_hash,
        "sanitized_environment_hash": plan.sanitized_environment.environment_hash,
        "project_source_identity_hash": plan.expected_project_source_identity,
        "interpreter_binding_hash": content_hash(
            {
                "implementation": plan.expected_python_implementation,
                "version": plan.expected_python_version,
                "executable_hash": plan.expected_python_executable_hash,
                "prefix_hash": bytes_hash(
                    os.path.normcase(
                        os.path.realpath(plan.expected_environment_prefix)
                    ).encode("utf-8")
                ),
            }
        ),
        "outer_invocation_argument_hash": content_hash(
            (
                "-s",
                "-B",
                os.path.normcase(os.path.realpath(plan.bootstrap_script)),
                "--invocation-plan",
                os.path.normcase(os.path.realpath(plan_path)),
                "--operation",
                "validate",
            )
        ),
        "forbidden_variable_occurrence_count": 0,
        "unexpected_variable_count": 0,
        "attestation_before_target_dispatch": True,
        "status": "PASS",
    }
    actual = M336K13ActualLauncherPlanReceipt(
        **actual_body, receipt_hash=content_hash(actual_body)
    )
    actual.verify()
    return SimpleNamespace(
        plan=plan,
        plan_path=plan_path,
        template=template,
        lifecycle=lifecycle,
        binding=binding,
        actual=actual,
    )


def _rehash(value, *, hash_field: str, **changes):
    temporary = replace(value, **changes, **{hash_field: "0" * 64})
    return replace(temporary, **{hash_field: content_hash(temporary._body())})


def test_m336k13_public_template_has_no_private_path_or_phase_sha(closure) -> None:
    value = canonical_json(closure.template.canonical_object())
    closure.template.verify()
    assert not re.search(r"[A-Za-z]:[/\\]", value)
    assert not re.search(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", value)
    assert "prospective" not in value.casefold()


def test_m336k13_public_plan_support_contracts_are_hash_only(closure) -> None:
    objects = (
        M336K13ActualLauncherPlanReceiptSchema.build(),
        M336K13FinalControllerPlanLifecyclePolicy.build(),
        M336K13FinalControllerPlanPathRoleManifest.build(
            template=closure.template,
            lifecycle=closure.lifecycle,
            binding=closure.binding,
        ),
    )
    for value in objects:
        serialized = canonical_json(value.canonical_object())
        assert not re.search(r"[A-Za-z]:[/\\]", serialized)
        assert str(closure.plan_path) not in serialized


def test_m336k13_post_q_prospective_freeze_uses_prospective_receipt_name() -> None:
    probe = SimpleNamespace(
        exact_freeze_sha="0" * 40,
        exact_qualification_sha="2" * 40,
        implementation_tip="1" * 40,
        contract_role=M336K8FreezeManifest.ROLE_V6,
        ROLE_V4=M336K8FreezeManifest.ROLE_V4,
        ROLE_V5=M336K8FreezeManifest.ROLE_V5,
        ROLE_V6=M336K8FreezeManifest.ROLE_V6,
    )
    assert (
        M336K8FreezeManifest._build_receipt_name(probe)
        == "prospective_freeze_build_receipt.json"
    )


def test_m336k13_plan_scope_relation_is_directly_typed(closure) -> None:
    changed = _rehash(
        closure.lifecycle,
        hash_field="receipt_hash",
        execution_scope="REHEARSAL",
    )
    with pytest.raises(M336K2ProtocolError):
        build_m336k13_final_controller_plan_binding(
            plan=closure.plan,
            plan_path=closure.plan_path,
            template=closure.template,
            lifecycle=changed,
        )


def test_m336k13_template_repository_target_role_cannot_be_spoofed(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    target = root / "tests/fixtures/m336k13_bootstrap_probe.py"
    bootstrap = root / "scripts/m336k13_final_controller_bootstrap.py"
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is absent")
    plan = build_m336k5_python_invocation(
        platform_role="WINDOWS",
        process_role="FINAL_CONTROLLER",
        python_executable=Path(sys.executable),
        git_executable=_tool("git"),
        powershell_executable=Path(powershell),
        repository=root,
        working_directory=root,
        bootstrap_script=bootstrap,
        target=target,
        validate_arguments=(
            "--request",
            str(tmp_path / "request.json"),
            "--validate-only",
            "--validation-receipt",
            str(tmp_path / "validation.json"),
        ),
        execute_arguments=(
            "--request",
            str(tmp_path / "request.json"),
            "--post-freeze-validation-receipt",
            str(tmp_path / "validation.json"),
            "--reservation-release-receipt",
            str(tmp_path / "release.json"),
        ),
        validate_startup_receipt=tmp_path / "validate-startup.json",
        execute_startup_receipt=tmp_path / "execute-startup.json",
    )
    template = build_m336k13_final_controller_plan_template(
        target_source_hash=bytes_hash(target.read_bytes()),
        bootstrap_source_hash=bytes_hash(bootstrap.read_bytes()),
    )
    plan_path = tmp_path / "spoofed-target-plan.json"
    with pytest.raises(M336K2ProtocolError):
        create_m336k13_final_controller_plan_once(
            plan=plan,
            plan_path=plan_path,
            template=template,
            exact_implementation_tip="1" * 40,
            exact_qualification_sha="2" * 40,
        )
    assert not plan_path.exists()


def test_m336k13_final_route_wrapper_is_directly_invocable() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        (sys.executable, str(root / "scripts/m336k13_run_final_route.py"), "--help"),
        cwd=root,
        check=False,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_m336k13_exact_plan_is_write_once_parent_fsynced_and_equal_sha_safe(
    closure,
) -> None:
    assert closure.lifecycle.creation_count == closure.lifecycle.write_count == 1
    assert closure.lifecycle.rewrite_count == closure.lifecycle.overwrite_count == 0
    assert closure.lifecycle.parent_directory_fsync_result == "PASS"
    assert (
        closure.lifecycle.exact_implementation_tip
        != closure.lifecycle.exact_qualification_sha
    )
    accepted = verify_m336k13_final_controller_plan_binding(
        plan_path=closure.plan_path,
        template=closure.template,
        lifecycle=closure.lifecycle,
        binding=closure.binding,
        actual_launcher_receipt=closure.actual,
        selected_operation="validate",
        expected_consumer_binding_hashes={
            name: closure.binding.receipt_hash
            for name in M336K13_PLAN_BINDING_CONSUMERS
        },
    )
    assert accepted == closure.plan
    with pytest.raises(FileExistsError):
        create_m336k13_final_controller_plan_once(
            plan=closure.plan,
            plan_path=closure.plan_path,
            template=closure.template,
            exact_implementation_tip="1" * 40,
            exact_qualification_sha="2" * 40,
        )


def test_m336k13_bootstrap_attests_same_exact_plan_for_both_operations(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    request = tmp_path / "request.json"
    request.write_text('{"probe":true}\n', encoding="utf-8", newline="\n")
    validation = tmp_path / "validation.json"
    execution = tmp_path / "execution.json"
    plan_path = tmp_path / "one-plan.json"
    validate_actual = tmp_path / "validate-actual.json"
    execute_actual = tmp_path / "execute-actual.json"
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is absent")
    plan = build_m336k5_python_invocation(
        platform_role="WINDOWS",
        process_role="FINAL_CONTROLLER",
        python_executable=Path(sys.executable),
        git_executable=_tool("git"),
        powershell_executable=Path(powershell),
        repository=root,
        working_directory=root,
        bootstrap_script=root / "scripts/m336k13_final_controller_bootstrap.py",
        target=root / "tests/fixtures/m336k13_bootstrap_probe.py",
        validate_arguments=(
            "--request",
            str(request),
            "--validate-only",
            "--validation-receipt",
            str(validation),
        ),
        execute_arguments=(
            "--request",
            str(request),
            "--post-freeze-validation-receipt",
            str(validation),
            "--reservation-release-receipt",
            str(execution),
        ),
        validate_startup_receipt=tmp_path / "validate-startup.json",
        execute_startup_receipt=tmp_path / "execute-startup.json",
    )
    write_m336k5_python_invocation_plan(plan, plan_path)
    frozen_bytes = plan_path.read_bytes()
    validate = run_m336k13_python_invocation(
        plan_path=plan_path,
        operation="validate",
        actual_launcher_plan_receipt=validate_actual,
        execution_scope="REHEARSAL",
    )
    assert validate.returncode == 0, validate.stderr.decode(errors="replace")
    assert plan_path.read_bytes() == frozen_bytes
    execute = run_m336k13_python_invocation(
        plan_path=plan_path,
        operation="execute",
        actual_launcher_plan_receipt=execute_actual,
        execution_scope="REHEARSAL",
    )
    assert execute.returncode == 0, execute.stderr.decode(errors="replace")
    assert plan_path.read_bytes() == frozen_bytes
    validate_receipt = M336K13ActualLauncherPlanReceipt.from_dict(
        json.loads(validate_actual.read_bytes())
    )
    execute_receipt = M336K13ActualLauncherPlanReceipt.from_dict(
        json.loads(execute_actual.read_bytes())
    )
    assert validate_receipt.selected_operation == "validate"
    assert execute_receipt.selected_operation == "execute"
    assert (
        validate_receipt.actual_invocation_plan_hash
        == execute_receipt.actual_invocation_plan_hash
        == plan.invocation_plan_hash
    )
    assert (
        validate_receipt.actual_plan_bytes_hash
        == execute_receipt.actual_plan_bytes_hash
        == bytes_hash(frozen_bytes)
    )
    assert (
        validate_receipt.actual_plan_file_identity_hash
        == execute_receipt.actual_plan_file_identity_hash
    )
    collision = run_m336k13_python_invocation(
        plan_path=plan_path,
        operation="validate",
        actual_launcher_plan_receipt=validation,
        execution_scope="REHEARSAL",
    )
    assert collision.returncode != 0
    assert b"destination collides with a plan role" in collision.stderr


@pytest.mark.parametrize(
    "field",
    ("interpreter_binding_hash", "outer_invocation_argument_hash"),
)
def test_m336k13_actual_launcher_runtime_binding_mutation_rejects(
    field: str, closure
) -> None:
    changed = _rehash(
        closure.actual,
        hash_field="receipt_hash",
        **{field: content_hash((field, "changed"))},
    )
    with pytest.raises(M336K2ProtocolError):
        verify_m336k13_final_controller_plan_binding(
            plan_path=closure.plan_path,
            template=closure.template,
            lifecycle=closure.lifecycle,
            binding=closure.binding,
            actual_launcher_receipt=changed,
            selected_operation="validate",
        )


@pytest.mark.parametrize("case", M336K13_MUTATION_CASES)
def test_m336k13_fully_rehashed_mutations_reject_at_semantic_layer(
    case: str, closure, tmp_path: Path
) -> None:
    def binding_gate(changed):
        return verify_m336k13_final_controller_plan_binding(
            plan_path=closure.plan_path,
            template=closure.template,
            lifecycle=closure.lifecycle,
            binding=changed,
        )

    binding_fields = {
        "same-filename-different-plan-bytes": "canonical_plan_bytes_hash",
        "same-operation-shape-different-invocation-plan-hash": (
            "canonical_invocation_plan_hash"
        ),
        "correct-plan-hash-wrong-plan-bytes-hash": "canonical_plan_bytes_hash",
        "correct-plan-bytes-hash-wrong-plan-file-identity": ("plan_file_identity_hash"),
        "execute-validation-receipt-differs-from-validate-output": (
            "post_freeze_validation_destination_identity_hash"
        ),
        "non-prospective-name-with-wrong-validation-identity": (
            "post_freeze_validation_destination_identity_hash"
        ),
        "release-path-changed": "release_destination_identity_hash",
        "validate-startup-receipt-changed": (
            "validate_startup_destination_identity_hash"
        ),
        "execute-startup-receipt-changed": (
            "execute_startup_destination_identity_hash"
        ),
        "target-changed": "target_source_hash",
        "target-source-bytes-changed": "target_source_hash",
        "bootstrap-changed": "bootstrap_source_hash",
        "python-executable-changed": "python_executable_binding_hash",
        "git-executable-changed": "git_executable_binding_hash",
        "powershell-executable-changed": "powershell_executable_binding_hash",
        "repository-changed": "repository_identity_hash",
        "working-directory-changed": "working_directory_identity_hash",
        "environment-prefix-changed": "python_executable_binding_hash",
        "sanitized-environment-changed": "sanitized_environment_hash",
        "source-identity-changed": "project_source_identity_hash",
        "startup-policy-changed": "startup_policy_hash",
        "stable-looking-filename-with-unstable-plan": "canonical_plan_bytes_hash",
        "r38a-shape-with-different-full-plan-hash": ("canonical_invocation_plan_hash"),
        "historical-f37-binding-used-in-v6": "exact_implementation_tip",
    }
    lifecycle_changes = {
        "validate-request-differs-from-execute-request": {
            "execute_request_path_identity_hash": content_hash(case)
        },
        "startup-receipts-swapped": {
            "validate_startup_receipt_path_identity_hash": (
                closure.lifecycle.execute_startup_receipt_path_identity_hash
            ),
            "execute_startup_receipt_path_identity_hash": (
                closure.lifecycle.validate_startup_receipt_path_identity_hash
            ),
        },
        "duplicate-startup-receipt-path": {
            "execute_startup_receipt_path_identity_hash": (
                closure.lifecycle.validate_startup_receipt_path_identity_hash
            )
        },
        "request-collides-with-validation": {
            "validate_request_path_identity_hash": (
                closure.lifecycle.post_freeze_validation_receipt_path_identity_hash
            )
        },
        "release-collides-with-startup": {
            "reservation_release_receipt_path_identity_hash": (
                closure.lifecycle.validate_startup_receipt_path_identity_hash
            )
        },
        "plan-overwritten-after-q": {"rewrite_count": 1},
        "plan-overwritten-after-f": {"post_freeze_modification_count": 1},
        "plan-regenerated-before-execute": {
            "creation_count": 2,
            "write_count": 2,
        },
        "parent-fsync-proof-omitted": {"parent_directory_fsync_result": "OMITTED"},
    }
    actual_changes = {
        "actual-plan-hash-differs-from-frozen": {
            "actual_invocation_plan_hash": content_hash(case)
        },
        "actual-plan-bytes-differs-from-frozen": {
            "actual_plan_bytes_hash": content_hash(case)
        },
        "actual-launcher-receipt-forged-pass": {"status": "FORGED_PASS"},
        "actual-receipt-references-another-startup": {
            "startup_receipt_hash": content_hash(case)
        },
        "selected-operation-changed": {"selected_operation": "execute"},
        "selected-argument-hash-changed": {
            "selected_operation_argument_hash": content_hash(case)
        },
        "selected-target-hash-changed": {
            "selected_target_source_hash": content_hash(case)
        },
        "canonical-request-plan-b-launcher-plan-a": {
            "actual_invocation_plan_hash": content_hash(case)
        },
        "target-reopens-plan-b": {"actual_plan_file_identity_hash": content_hash(case)},
        "bootstrap-attestation-after-dispatch": {
            "attestation_before_target_dispatch": False
        },
    }
    consumer_omissions = {
        "route-event-before-plan-admission": "route_context",
        "reservation-release-before-plan-admission": "preledger_receipt",
        "controller-before-plan-admission": "controller_admission_receipt",
        "plan-binding-omitted-from-authorization": "final_authorization",
        "plan-binding-omitted-from-post-freeze": "post_freeze_input_bundle",
        "plan-binding-omitted-from-freeze": "freeze_manifest",
        "plan-binding-omitted-from-preledger": "preledger_receipt",
    }

    if case in binding_fields:
        field = binding_fields[case]
        replacement = (
            "d90dc54f121cec13ac90131e8f52c4129033c65b"
            if field == "exact_implementation_tip"
            else content_hash((case, "fully-rehashed"))
        )
        changed = _rehash(
            closure.binding,
            hash_field="receipt_hash",
            **{field: replacement},
        )
        operation = lambda: binding_gate(changed)
    elif case == "equal-lineage-sha-bypass":
        changed = _rehash(
            closure.lifecycle,
            hash_field="receipt_hash",
            exact_qualification_sha=closure.lifecycle.exact_implementation_tip,
        )
        operation = changed.verify
    elif case in lifecycle_changes:
        changed = _rehash(
            closure.lifecycle,
            hash_field="receipt_hash",
            **lifecycle_changes[case],
        )
        operation = lambda: verify_m336k13_final_controller_plan_binding(
            plan_path=closure.plan_path,
            template=closure.template,
            lifecycle=changed,
            binding=closure.binding,
        )
    elif case == "relative-private-path":
        operation = lambda: _path_identity("relative/private-plan.json")
    elif case == "second-execute-only-plan":
        changed = _rehash(
            closure.template,
            hash_field="template_hash",
            same_plan_file_required=False,
        )
        operation = changed.verify
    elif case in actual_changes:
        changed = _rehash(
            closure.actual,
            hash_field="receipt_hash",
            **actual_changes[case],
        )
        operation = lambda: verify_m336k13_final_controller_plan_binding(
            plan_path=closure.plan_path,
            template=closure.template,
            lifecycle=closure.lifecycle,
            binding=closure.binding,
            actual_launcher_receipt=changed,
            selected_operation="validate",
        )
    elif case == "actual-launcher-receipt-absent":
        operation = lambda: verify_m336k13_final_controller_plan_binding(
            plan_path=closure.plan_path,
            template=closure.template,
            lifecycle=closure.lifecycle,
            binding=closure.binding,
            selected_operation="validate",
        )
    elif case in consumer_omissions:
        consumers = {
            name: closure.binding.receipt_hash
            for name in M336K13_PLAN_BINDING_CONSUMERS
        }
        consumers.pop(consumer_omissions[case])
        operation = lambda: verify_m336k13_final_controller_plan_binding(
            plan_path=closure.plan_path,
            template=closure.template,
            lifecycle=closure.lifecycle,
            binding=closure.binding,
            expected_consumer_binding_hashes=consumers,
        )
    elif case == "historical-v5-profile-used-in-v6":
        profile = m336k_official_profile_registry().profile("m336k8-final-v5")
        changed = _rehash(
            closure.template,
            hash_field="template_hash",
            profile_id=profile.profile_id,
            profile_hash=profile.profile_hash,
        )
        operation = changed.verify
    elif case == "raw-private-plan-path-published":
        changed = _rehash(
            closure.template,
            hash_field="template_hash",
            target_repository_path=str(closure.plan_path),
        )
        operation = changed.verify
    elif case == "private-environment-value-published":
        value = closure.template.canonical_object()
        value["private_environment_value"] = "SECRET"
        body = dict(value)
        body.pop("template_hash")
        value["template_hash"] = content_hash(body)
        operation = lambda: type(closure.template).from_dict(value)
    elif case == "rewrite-counter-forged-zero":
        temporary = replace(
            closure.plan,
            expected_target_source_hash=content_hash(case),
            invocation_plan_hash="0" * 64,
        )
        changed_plan = replace(
            temporary, invocation_plan_hash=content_hash(temporary._body())
        )
        changed_path = tmp_path / "rewritten-plan.json"
        changed_path.write_text(
            canonical_json(changed_plan.canonical_object()) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        operation = lambda: verify_m336k13_final_controller_plan_binding(
            plan_path=changed_path,
            template=closure.template,
            lifecycle=closure.lifecycle,
            binding=closure.binding,
        )
    else:
        raise AssertionError(f"unmapped mutation case: {case}")
    with pytest.raises((M336K2ProtocolError, FileNotFoundError)):
        operation()
