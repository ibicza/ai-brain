from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5PythonStartupReceipt,
    build_m336k5_python_invocation,
)
from ai_brain.stage3.acquisition.m336k7_contracts import (
    M336K7LegacyCapsuleCompatibilityReceipt,
    M336K7PersistentCapsuleBindingSet,
)
from ai_brain.stage3.acquisition.m336k8_contracts import (
    M336K8_POST_FREEZE_CONSUMED_COMPONENTS,
    M336K11_POST_FREEZE_CONSUMED_COMPONENTS,
    M336K12_POST_FREEZE_CONSUMED_COMPONENTS,
    M336K13_POST_FREEZE_CONSUMED_COMPONENTS,
    M336K8FrozenContractCompatibilityGateV2,
    m336k8_semantic_binding_mismatches,
)
from ai_brain.stage3.acquisition.m336k9_authorization import (
    M336K13FinalAuthorization,
)
from ai_brain.stage3.acquisition.m336k12_dispatch import (
    M336K12ProducerConsumerParityReceipt,
)
from ai_brain.stage3.acquisition.m336k13_plan import (
    M336K13ActualLauncherPlanReceiptSchema,
    M336K13EffectiveEnvironmentBinding,
    M336K13FinalControllerPlanBindingReceipt,
    M336K13NativeExecutionCapsuleReceipt,
    M336K13NativeRouteManifest,
    M336K13NativeStagePlanBinding,
    M336K13OfficialControllerExecutableBinding,
    M336K13OfficialExecutableBindingReceipt,
    M336K13PostFreezeInputBundle,
    build_m336k13_final_controller_plan_binding,
    build_m336k13_final_controller_plan_template,
    create_m336k13_final_controller_plan_once,
)

ROOT = Path(__file__).resolve().parents[1]
F37_COMPONENTS = ROOT / "artifacts/m336k12/f37-freeze/components"
F28_COMPONENTS = ROOT / "artifacts/m336k2/f28-freeze/components"
PROFILE_ID = "m336k8-final-v6"
BRANCH_REF = "refs/heads/exp/stage3-m336k13-final-controller-plan-binding-v23"
EXECUTABLE_ROLES = frozenset(
    {"cmd", "git", "java", "javac", "powershell", "python", "scp", "ssh", "tar"}
)
REQUIRED_OUTPUTS = frozenset(
    {
        "final_authorization.json",
        "official_candidate_pool_binding.json",
        "official_network_authority_manifest.json",
        "official_acquisition_binding_receipt.json",
        "effective_environment_binding.json",
        "official_controller_executable_binding.json",
        "official_executable_binding_receipt.json",
        "execution_capsule_receipt.json",
        "native_route_manifest.json",
        "native_stage_dispatches.json",
        "native_stage_plan_binding.json",
        "producer_consumer_parity_receipt.json",
        "post_freeze_input_bundle.json",
        "final_controller_plan_template.json",
        "final_controller_plan_binding_receipt.json",
        "actual_launcher_plan_receipt_schema.json",
        "final_controller_plan_lifecycle_policy.json",
        "final_controller_plan_path_role_manifest.json",
    }
)


def _tool(name: str) -> Path:
    value = shutil.which(name)
    if value is None:
        pytest.skip(f"required test executable is absent: {name}")
    return Path(value).resolve(strict=True)


def _component(name: str) -> Path:
    matches = tuple(F37_COMPONENTS.glob(f"[0-9][0-9]-{name}.json"))
    assert len(matches) == 1
    return matches[0]


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _rehash(value: dict, hash_field: str) -> dict:
    body = dict(value)
    body.pop(hash_field, None)
    return {**body, hash_field: content_hash(body)}


def _raw_windows_paths(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if re.match(r"^[A-Za-z]:[/\\]", value) else ()
    if isinstance(value, dict):
        return tuple(
            path for item in value.values() for path in _raw_windows_paths(item)
        )
    if isinstance(value, list):
        return tuple(path for item in value for path in _raw_windows_paths(item))
    return ()


def _empty_gate(
    consumed_artifact_count: int,
) -> M336K8FrozenContractCompatibilityGateV2:
    temporary = M336K8FrozenContractCompatibilityGateV2(
        schema_version=2,
        contract_role=M336K8FrozenContractCompatibilityGateV2.ROLE,
        artifacts=(),
        consumed_artifact_count=consumed_artifact_count,
        compatibility_artifact_count=0,
        uncovered_consumer_count=0,
        unused_compatibility_artifact_count=0,
        missing_field_count=0,
        extra_field_count=0,
        roundtrip_difference_count=0,
        semantic_check_count=0,
        semantic_binding_mismatch_count=0,
        producer_origin_mismatch_count=0,
        phase_specific_active_field_count=0,
        mandatory_default_lookup_count=0,
        direct_legacy_capsule_comparison_count=0,
        status="PASS",
        report_hash="0" * 64,
    )
    return replace(temporary, report_hash=content_hash(temporary._body()))


def _rehash_schema(value: dict[str, object]) -> dict[str, object]:
    body = {name: item for name, item in value.items() if name != "schema_hash"}
    return {**body, "schema_hash": content_hash(body)}


def _copy_current_source(repository: Path) -> tuple[str, str]:
    git = _tool("git")
    subprocess.run(
        (str(git), "clone", "--quiet", "--no-hardlinks", str(ROOT), str(repository)),
        check=True,
    )
    qualification = subprocess.run(
        (str(git), "rev-parse", "HEAD"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    for relative in (
        "src/ai_brain/stage3/acquisition/m336k8_contracts.py",
        "src/ai_brain/stage3/acquisition/m336k13_plan.py",
        "scripts/m336k5_build_component_bundle.py",
    ):
        destination = repository / relative
        shutil.copyfile(ROOT / relative, destination)
    subprocess.run(
        (str(git), "add", "--", "src", "scripts"), cwd=repository, check=True
    )
    subprocess.run(
        (
            str(git),
            "-c",
            "user.name=M336K13 Test",
            "-c",
            "user.email=m336k13-test@example.invalid",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "M336K13 temporary verifier fixture",
        ),
        cwd=repository,
        check=True,
    )
    implementation = subprocess.run(
        (str(git), "rev-parse", "HEAD"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert qualification != implementation
    return qualification, implementation


def _startup_receipt(plan) -> M336K5PythonStartupReceipt:
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_PYTHON_STARTUP_RECEIPT",
        "startup_policy_hash": plan.startup_policy.policy_hash,
        "interpreter_binding_hash": content_hash("m336k13-test-interpreter"),
        "invocation_argument_hash": content_hash("m336k13-test-arguments"),
        "sanitized_environment_hash": plan.sanitized_environment.environment_hash,
        "project_source_identity": plan.expected_project_source_identity,
        "user_site_disabled_result": True,
        "python_no_user_site": 1,
        "site_enable_user_site": False,
        "user_site_path_membership": False,
        "unsafe_path_count": 0,
        "unexpected_startup_module_count": 0,
        "torch_imported": False,
        "status": "PASS",
    }
    return M336K5PythonStartupReceipt(**body, receipt_hash=content_hash(body))


def _prepare_capsule_inputs(root: Path) -> dict[str, Path]:
    inputs = root / "capsule-inputs"
    inputs.mkdir()
    legacy_body = {
        "schema_version": 1,
        "contract_role": "M336K13_TEST_LEGACY_PUBLIC_CAPSULE_RECEIPT",
        "status": "PASS",
    }
    legacy = {**legacy_body, "receipt_hash": content_hash(legacy_body)}
    legacy_path = inputs / "legacy_public_receipt.json"
    _write(legacy_path, legacy)

    persistent = _load(_component("persistent_capsule_receipt"))
    persistent["legacy_public_receipt_hash"] = legacy["receipt_hash"]
    persistent = _rehash(persistent, "receipt_hash")
    persistent_path = inputs / "persistent_capsule_receipt.json"
    _write(persistent_path, persistent)

    liveness = _load(_component("capsule_liveness"))
    liveness["legacy_public_receipt_hash"] = legacy["receipt_hash"]
    liveness = _rehash(liveness, "receipt_hash")
    liveness_path = inputs / "capsule_liveness.json"
    _write(liveness_path, liveness)

    original_binding = _load(_component("capsule_binding_set"))
    binding_values = {
        field.name: original_binding[field.name]
        for field in fields(M336K7PersistentCapsuleBindingSet)
        if field.name not in {"schema_version", "contract_role", "binding_set_hash"}
    }
    binding_values.update(
        {
            "capsule_liveness_receipt_hash": liveness["receipt_hash"],
            "persistent_capsule_public_receipt_hash": persistent["receipt_hash"],
            "legacy_public_capsule_receipt_hash": legacy["receipt_hash"],
        }
    )
    binding = M336K7PersistentCapsuleBindingSet.build(**binding_values)
    binding_path = inputs / "capsule_binding_set.json"
    _write(binding_path, binding.canonical_object())

    original_compatibility = _load(_component("legacy_capsule_compatibility"))
    compatibility = M336K7LegacyCapsuleCompatibilityReceipt.build(
        persistent_public_receipt_hash=persistent["receipt_hash"],
        legacy_public_receipt_hash=legacy["receipt_hash"],
        executable_dependency_manifest_hash=(
            original_compatibility["executable_dependency_manifest_hash"]
        ),
        host_identity_hash=original_compatibility["host_identity_hash"],
        python_environment_manifest_hash=(
            original_compatibility["python_environment_manifest_hash"]
        ),
        compatibility_status="PASS",
    )
    compatibility_path = inputs / "legacy_capsule_compatibility.json"
    _write(compatibility_path, compatibility.canonical_object())
    return {
        "legacy": legacy_path,
        "persistent": persistent_path,
        "liveness": liveness_path,
        "binding": binding_path,
        "compatibility": compatibility_path,
    }


def _run_script(script: Path, request: Path, repository: Path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(repository / "src")
    return subprocess.run(
        (sys.executable, str(script), "--request", str(request)),
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def official_bundle(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    root = tmp_path_factory.mktemp("m336k13-official-component")
    repository = root / "repository"
    qualification, implementation = _copy_current_source(repository)
    private = root / "private"
    private.mkdir()
    handles_root = private / "executables"
    handles_root.mkdir()
    executable_handles: dict[str, Path] = {}
    for role in sorted(EXECUTABLE_ROLES):
        if role == "python":
            executable_handles[role] = Path(sys.executable).resolve(strict=True)
        elif role == "git":
            executable_handles[role] = _tool("git")
        else:
            path = handles_root / f"{role}.test-executable"
            path.write_bytes(f"m336k13-test-executable:{role}\n".encode())
            executable_handles[role] = path.resolve(strict=True)

    final_request = private / "final-request.json"
    validation = private / "post-freeze-validation.json"
    release = private / "reservation-release.json"
    validate_startup = private / "validate-startup.json"
    execute_startup = private / "execute-startup.json"
    plan_path = private / "final-controller-plan.json"
    target = repository / "scripts/m336k13_run_final_route.py"
    bootstrap = repository / "scripts/m336k13_final_controller_bootstrap.py"
    plan = build_m336k5_python_invocation(
        platform_role="WINDOWS",
        process_role="FINAL_CONTROLLER",
        python_executable=executable_handles["python"],
        git_executable=executable_handles["git"],
        powershell_executable=executable_handles["powershell"],
        repository=repository,
        working_directory=repository,
        bootstrap_script=bootstrap,
        target=target,
        validate_arguments=(
            "--request",
            str(final_request),
            "--validate-only",
            "--validation-receipt",
            str(validation),
        ),
        execute_arguments=(
            "--request",
            str(final_request),
            "--post-freeze-validation-receipt",
            str(validation),
            "--reservation-release-receipt",
            str(release),
        ),
        validate_startup_receipt=validate_startup,
        execute_startup_receipt=execute_startup,
        parent_environment={
            "SYSTEMROOT": "C:/Windows",
            "TEMP": str(private / "temp"),
            "TMP": str(private / "temp"),
        },
    )
    template = build_m336k13_final_controller_plan_template(
        target_source_hash=bytes_hash(target.read_bytes()),
        bootstrap_source_hash=bytes_hash(bootstrap.read_bytes()),
    )
    lifecycle = create_m336k13_final_controller_plan_once(
        plan=plan,
        plan_path=plan_path,
        template=template,
        exact_implementation_tip=implementation,
        exact_qualification_sha=qualification,
    )
    binding = build_m336k13_final_controller_plan_binding(
        plan=plan,
        plan_path=plan_path,
        template=template,
        lifecycle=lifecycle,
    )
    template_path = private / "final-controller-plan-template.json"
    lifecycle_path = private / "final-controller-plan-lifecycle.json"
    binding_path = private / "final-controller-plan-binding.json"
    startup_path = private / "windows-startup-receipt.json"
    _write(template_path, template.canonical_object())
    _write(lifecycle_path, lifecycle.canonical_object())
    _write(binding_path, binding.canonical_object())
    _write(startup_path, asdict(_startup_receipt(plan)))

    startup_components = root / "startup-components"
    startup_components.mkdir()
    for name in (
        "python_startup_policy",
        "python_startup_bootstrap",
        "windows_python_launcher",
        "startup_receipt_schema",
    ):
        shutil.copyfile(_component(name), startup_components / f"{name}.json")
    old_sanitized = _load(_component("sanitized_environment_policy"))
    sanitized_body = {
        **{
            name: value
            for name, value in old_sanitized.items()
            if name != "receipt_hash"
        },
        "startup_policy_hash": plan.startup_policy.policy_hash,
        "windows_environment_hash": plan.sanitized_environment.environment_hash,
    }
    _write(
        startup_components / "sanitized_environment_policy.json",
        {**sanitized_body, "receipt_hash": content_hash(sanitized_body)},
    )

    capsule = _prepare_capsule_inputs(root)
    source_output = root / "source-domain-components"
    source_request = {
        "repository": str(repository),
        "git_executable": str(executable_handles["git"]),
        "python_executable": str(executable_handles["python"]),
        "exact_implementation_tip": implementation,
        "startup_components": str(startup_components),
        "capsule_binding_set": str(capsule["binding"]),
        "capsule_content_manifest": str(_component("capsule_content_manifest")),
        "capsule_lifecycle_policy": str(_component("capsule_lifecycle_policy")),
        "capsule_liveness_receipt": str(capsule["liveness"]),
        "persistent_public_receipt": str(capsule["persistent"]),
        "legacy_public_receipt": str(capsule["legacy"]),
        "persistent_capsule_python_environment_manifest": str(
            _component("persistent_capsule_python_environment_manifest")
        ),
        "persistent_capsule_executable_dependency_manifest": str(
            _component("persistent_capsule_executable_dependency_manifest")
        ),
        "stable_host_identity_receipt": str(_component("karina_stable_host_identity")),
        "executable_handles": {
            role: {"path": str(path), "version_arguments": []}
            for role, path in executable_handles.items()
        },
        "output": str(source_output),
        "official_profile_id": PROFILE_ID,
        "windows_invocation_plan": str(plan_path),
        "windows_startup_receipt": str(startup_path),
    }
    source_request_path = private / "source-domain-request.json"
    _write(source_request_path, source_request)
    source_result = _run_script(
        repository / "scripts/m336k8_build_source_domain_contracts.py",
        source_request_path,
        repository,
    )
    assert source_result.returncode == 0, source_result.stderr

    legacy = root / "legacy-components"
    legacy.mkdir()
    for source in F28_COMPONENTS.glob("[0-9][0-9]-*.json"):
        name = re.sub(r"^[0-9]+-", "", source.name)
        shutil.copyfile(source, legacy / name)
    output = root / "official-components"
    q_readiness = _component("q28_readiness")
    readiness_hash = _load(q_readiness)["readiness_hash"]
    request = {
        "repository": str(repository),
        "legacy_bundle": str(legacy),
        "exact_implementation_tip": implementation,
        "exact_q30_sha": qualification,
        "branch_ref": BRANCH_REF,
        "readiness_hash": readiness_hash,
        "q_readiness": str(q_readiness),
        "q_evidence_manifest": str(_component("q28_evidence_manifest")),
        "identity_mode": "OFFICIAL",
        "identity_namespace": "m336k8",
        "official_profile_id": PROFILE_ID,
        "disposable_label": "official-v6-test",
        "output": str(output),
        "python_environment_manifest": str(_component("python_environment_manifest")),
        "python_startup_policy": str(startup_components / "python_startup_policy.json"),
        "python_startup_bootstrap": str(
            startup_components / "python_startup_bootstrap.json"
        ),
        "windows_python_launcher": str(
            startup_components / "windows_python_launcher.json"
        ),
        "karina_python_launcher": str(_component("karina_python_launcher")),
        "sanitized_environment_policy": str(
            startup_components / "sanitized_environment_policy.json"
        ),
        "startup_receipt_schema": str(
            startup_components / "startup_receipt_schema.json"
        ),
        "storage_reservation": str(_component("storage_reservation")),
        "resource_monitor": str(_component("resource_monitor")),
        "cleanup_policy": str(_component("cleanup_policy")),
        "recovery_checkpoint_policy": str(_component("recovery_checkpoint_policy")),
        "persistent_capsule_receipt": str(capsule["persistent"]),
        "capsule_content_manifest": str(_component("capsule_content_manifest")),
        "capsule_lifecycle_policy": str(_component("capsule_lifecycle_policy")),
        "capsule_liveness": str(capsule["liveness"]),
        "preservation_set": str(_component("preservation_set")),
        "cleanup_plan": str(_component("cleanup_plan")),
        "cleanup_cutoff_state": str(_component("cleanup_cutoff_state")),
        "resource_budget_policy": str(_component("resource_budget_policy")),
        "resource_observation": str(_component("resource_observation")),
        "resource_gate": str(_component("resource_gate")),
        "capsule_binding_set": str(capsule["binding"]),
        "legacy_capsule_compatibility": str(capsule["compatibility"]),
        "candidate_pool": str(_component("candidate_pool")),
        **{
            name: str(source_output / f"{name}.json")
            for name in (
                "controller_source_identity_policy",
                "controller_source_identity_receipt",
                "controller_python_environment_manifest",
                "controller_executable_dependency_manifest",
                "controller_startup_binding",
                "persistent_capsule_source_binding",
                "bridge_surface_manifest",
                "source_domain_compatibility",
                "legacy_controller_alias_receipt",
                "freeze_assembly_plan",
                "effective_environment_binding",
            )
        },
        "persistent_capsule_python_environment_manifest": str(
            _component("persistent_capsule_python_environment_manifest")
        ),
        "persistent_capsule_executable_dependency_manifest": str(
            _component("persistent_capsule_executable_dependency_manifest")
        ),
        "executable_handles": {
            role: str(path) for role, path in executable_handles.items()
        },
        "windows_invocation_plan": str(plan_path),
        "windows_startup_receipt": str(startup_path),
        "final_controller_plan_template": str(template_path),
        "final_controller_plan_lifecycle_receipt": str(lifecycle_path),
        "final_controller_plan_binding_receipt": str(binding_path),
    }
    request_path = private / "official-component-request.json"
    _write(request_path, request)
    result = _run_script(
        repository / "scripts/m336k5_build_component_bundle.py",
        request_path,
        repository,
    )
    assert result.returncode == 0, result.stderr
    assert "M336K12 live plan binding changed" not in result.stderr
    return SimpleNamespace(
        root=root,
        repository=repository,
        private=private,
        request=request,
        output=output,
        result=result,
    )


def test_official_v6_component_builder_completes_with_active_v6_authority(
    official_bundle: SimpleNamespace,
) -> None:
    output = official_bundle.output
    assert REQUIRED_OUTPUTS <= {path.name for path in output.glob("*.json")}
    plan = M336K13NativeStagePlanBinding.from_dict(
        _load(output / "native_stage_plan_binding.json")
    )
    parity = M336K12ProducerConsumerParityReceipt.from_dict(
        _load(output / "producer_consumer_parity_receipt.json")
    )
    parsed = (
        M336K13FinalAuthorization.from_dict(_load(output / "final_authorization.json")),
        M336K13EffectiveEnvironmentBinding.from_dict(
            _load(output / "effective_environment_binding.json")
        ),
        M336K13OfficialControllerExecutableBinding.from_dict(
            _load(output / "official_controller_executable_binding.json")
        ),
        M336K13OfficialExecutableBindingReceipt.from_dict(
            _load(output / "official_executable_binding_receipt.json")
        ),
        M336K13NativeExecutionCapsuleReceipt.from_dict(
            _load(output / "execution_capsule_receipt.json")
        ),
        M336K13NativeRouteManifest.from_dict(
            _load(output / "native_route_manifest.json")
        ),
        M336K13PostFreezeInputBundle.from_dict(
            _load(output / "post_freeze_input_bundle.json")
        ),
        M336K13FinalControllerPlanBindingReceipt.from_dict(
            _load(output / "final_controller_plan_binding_receipt.json")
        ),
    )

    assert all(value is not None for value in parsed)
    assert plan.contract_role == M336K13NativeStagePlanBinding.ROLE
    assert plan.schema_version == 2
    assert parity.native_stage_plan_binding_hash == plan.plan_binding_hash
    assert not (output / "base_native_stage_plan_binding.json").exists()
    assert all(
        value.get("executable_semantic_mismatch_count", 0) == 0
        for value in map(_load, output.glob("*.json"))
    )
    assert not tuple(
        raw_path
        for path in output.glob("*.json")
        for raw_path in _raw_windows_paths(_load(path))
    )


def test_official_v6_component_builder_rejects_rehashed_semantic_binding_mutation(
    official_bundle: SimpleNamespace,
) -> None:
    repository = official_bundle.repository
    source = (repository / "scripts/m336k5_build_component_bundle.py").read_text(
        encoding="utf-8"
    )
    marker = "            producer_consumer_parity = (\n"
    injection = (
        "            if profile_id == M336K13_PROFILE_ID:\n"
        "                mutated_body = plan_binding._body()\n"
        "                mutated_body['active_profile_hash'] = '0' * 64\n"
        "                plan_binding = M336K13NativeStagePlanBinding(\n"
        "                    **mutated_body,\n"
        "                    plan_binding_hash=content_hash(mutated_body),\n"
        "                )\n"
    )
    assert source.count(marker) == 1
    fault_script = official_bundle.private / "faulted-component-builder.py"
    fault_script.write_text(
        source.replace(marker, injection + marker),
        encoding="utf-8",
        newline="\n",
    )
    request = dict(official_bundle.request)
    rejected_output = official_bundle.root / "rejected-components"
    request["output"] = str(rejected_output)
    request_path = official_bundle.private / "rejected-component-request.json"
    _write(request_path, request)

    result = _run_script(fault_script, request_path, repository)

    assert result.returncode != 0
    assert "M336K13 native stage base projection changed" in result.stderr
    assert not (rejected_output / "native_stage_plan_binding.json").exists()
    assert not (rejected_output / "post_freeze_input_bundle.json").exists()
    assert not (rejected_output / "frozen_contract_compatibility_v2.json").exists()
    assert not (rejected_output / "official_acquisition_binding_receipt.json").exists()
    assert not (rejected_output / "official_executable_binding_receipt.json").exists()


def test_v6_consumed_inventory_is_exact_and_gate_round_trips() -> None:
    assert len(M336K13_POST_FREEZE_CONSUMED_COMPONENTS) == 38
    assert len(set(M336K13_POST_FREEZE_CONSUMED_COMPONENTS)) == 38

    gate = _empty_gate(len(M336K13_POST_FREEZE_CONSUMED_COMPONENTS))

    gate.verify()
    assert (
        M336K8FrozenContractCompatibilityGateV2.from_dict(gate.canonical_object())
        == gate
    )


@pytest.mark.parametrize(
    "consumed_artifact_count",
    [
        len(M336K8_POST_FREEZE_CONSUMED_COMPONENTS),
        len(M336K11_POST_FREEZE_CONSUMED_COMPONENTS),
        len(M336K12_POST_FREEZE_CONSUMED_COMPONENTS),
    ],
)
def test_historical_consumed_inventory_counts_remain_valid(
    consumed_artifact_count: int,
) -> None:
    _empty_gate(consumed_artifact_count).verify()


def test_unknown_consumed_inventory_count_is_rejected() -> None:
    with pytest.raises(M336K2ProtocolError, match="compatibility gate V2 is invalid"):
        _empty_gate(39).verify()


def test_v6_launcher_schema_uses_typed_bootstrap_producer_and_is_closed_under_rehash() -> (
    None
):
    schema = M336K13ActualLauncherPlanReceiptSchema.build().canonical_object()

    assert (
        m336k8_semantic_binding_mismatches(
            "actual_launcher_plan_receipt_schema",
            {"actual_launcher_plan_receipt_schema": schema},
        )
        == 0
    )

    wrong = _rehash_schema(
        {**schema, "producer_repository_path": "scripts/m336k5_python_bootstrap.py"}
    )
    assert wrong["schema_hash"] != schema["schema_hash"]
    assert (
        m336k8_semantic_binding_mismatches(
            "actual_launcher_plan_receipt_schema",
            {"actual_launcher_plan_receipt_schema": wrong},
        )
        == 1
    )


def test_non_v6_launcher_schema_keeps_legacy_producer_expectation() -> None:
    schema = M336K13ActualLauncherPlanReceiptSchema.build().canonical_object()
    legacy_like = _rehash_schema(
        {
            **schema,
            "contract_role": "M336K12_ACTUAL_LAUNCHER_PLAN_RECEIPT_SCHEMA",
            "producer_repository_path": "scripts/m336k5_python_bootstrap.py",
        }
    )

    assert (
        m336k8_semantic_binding_mismatches(
            "actual_launcher_plan_receipt_schema",
            {"actual_launcher_plan_receipt_schema": legacy_like},
        )
        == 1
    )
