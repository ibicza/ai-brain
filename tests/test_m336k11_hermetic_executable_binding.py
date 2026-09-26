from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_execution import (
    executable_dependency_manifest_from_dict,
    minimal_environment_policy_identity,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_registry import build_m336k5_route_registry
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5PythonStartupReceipt,
    build_m336k5_python_invocation,
    build_m336k5_python_startup_policy,
    build_m336k5_sanitized_environment,
)
from ai_brain.stage3.acquisition.m336k8_freeze import M336K8FreezeManifest
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k11_execution import (
    HISTORICAL_READ_ONLY,
    M336K11_MUTATION_CASES,
    OFFICIAL_CONTROLLER,
    REHEARSAL,
    M336K11EffectiveEnvironmentBinding,
    M336K11HermeticExecutableDependencyManifest,
    M336K11NativeExecutionCapsuleReceipt,
    M336K11NativeRouteManifest,
    M336K11OfficialControllerExecutableBinding,
    M336K11OfficialExecutableBindingReceipt,
    build_m336k11_final_request_binding,
    build_m336k11_native_execution_plan,
    build_official_executable_components,
    load_historical_executable_components_read_only,
    m336k11_official_component_scopes,
    verify_m336k11_live_execution_inputs,
    verify_m336k11_official_executable_binding,
)

ROOT = Path(__file__).resolve().parents[1]
F35_COMPONENTS = ROOT / "artifacts/m336k10/f35-freeze/components"


def _tool(name: str) -> Path:
    value = shutil.which(name)
    assert value is not None
    return Path(value).resolve(strict=True)


def _test_executable(root: Path, name: str) -> Path:
    path = root / f"{name}.test-executable"
    path.write_bytes(f"m336k11-test-executable:{name}\n".encode())
    return path.resolve(strict=True)


def _hashed(body: dict, field: str) -> dict:
    return {**body, field: content_hash(body)}


def _startup_receipt(plan, label: str = "primary") -> M336K5PythonStartupReceipt:
    body = {
        "schema_version": 1,
        "contract_role": "M336K5_PYTHON_STARTUP_RECEIPT",
        "startup_policy_hash": plan.startup_policy.policy_hash,
        "interpreter_binding_hash": content_hash((label, "interpreter")),
        "invocation_argument_hash": content_hash((label, "arguments")),
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


@pytest.fixture(scope="module")
def graph(tmp_path_factory: pytest.TempPathFactory) -> dict:
    private = tmp_path_factory.mktemp("m336k11-executable")
    python = Path(__import__("sys").executable).absolute()
    git = _tool("git")
    powershell = _test_executable(private, "powershell")
    plan = build_m336k5_python_invocation(
        platform_role="WINDOWS",
        process_role="VALIDATE_ONLY",
        python_executable=python,
        git_executable=git,
        powershell_executable=powershell,
        repository=ROOT,
        working_directory=ROOT,
        bootstrap_script=ROOT / "scripts/m336k5_python_bootstrap.py",
        target=ROOT / "scripts/m336k11_run_final_route.py",
        execute_arguments=("--request", "prospective.json"),
        validate_arguments=("--validate-only",),
        execute_startup_receipt=private / "execute-startup.json",
        validate_startup_receipt=private / "validate-startup.json",
        parent_environment={
            "SYSTEMROOT": "C:/Windows",
            "TEMP": "C:/private/temp-a",
            "TMP": "C:/private/tmp-a",
        },
    )
    startup = _startup_receipt(plan)
    sanitized_body = {
        "schema_version": 1,
        "contract_role": "M336K5_PUBLIC_SANITIZED_ENVIRONMENT_POLICY",
        "startup_policy_hash": plan.startup_policy.policy_hash,
        "windows_environment_hash": plan.sanitized_environment.environment_hash,
        "karina_environment_hash": content_hash("karina-environment"),
        "forbidden_environment_names": plan.startup_policy.forbidden_environment_names,
        "private_environment_values_published": False,
    }
    sanitized = _hashed(sanitized_body, "receipt_hash")
    source = _hashed(
        {
            "schema_version": 1,
            "live_project_source_identity": plan.expected_project_source_identity,
        },
        "receipt_hash",
    )
    environment = _hashed(
        {
            "schema_version": 2,
            "project_source_identity_hash": plan.expected_project_source_identity,
            "startup_policy_hash": plan.startup_policy.policy_hash,
            "sanitized_environment_policy_hash": sanitized["receipt_hash"],
        },
        "environment_manifest_hash",
    )
    handles = {"git": git, "python": python, "powershell": powershell}
    handles.update(
        {
            name: _test_executable(private, name)
            for name in ("java", "javac", "ssh", "scp", "tar", "cmd")
        }
    )
    manifest = M336K11HermeticExecutableDependencyManifest.build(
        executables={name: (path, ()) for name, path in handles.items()},
        python_invocation_handle=str(python),
        execution_scope=OFFICIAL_CONTROLLER,
        exact_implementation_tip=subprocess.run(
            (str(git), "rev-parse", "HEAD"),
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        controller_python_environment_manifest_hash=environment[
            "environment_manifest_hash"
        ],
        controller_source_identity_hash=plan.expected_project_source_identity,
        static_startup_policy_hash=plan.startup_policy.policy_hash,
        sanitized_environment_policy_hash=sanitized["receipt_hash"],
        expected_windows_sanitized_environment_hash=plan.sanitized_environment.environment_hash,
        startup_receipt_schema_hash=content_hash("startup-schema"),
        bootstrap_source_hash=bytes_hash(
            (ROOT / "scripts/m336k5_python_bootstrap.py").read_bytes()
        ),
        windows_launcher_source_hash=bytes_hash(
            (ROOT / "scripts/m336k5_launch_python.ps1").read_bytes()
        ),
    )
    effective = M336K11EffectiveEnvironmentBinding.build(
        plan=plan,
        startup_receipt=startup,
        sanitized_environment_policy_hash=sanitized["receipt_hash"],
        execution_scope=OFFICIAL_CONTROLLER,
    )
    registry = _hashed({"schema_version": 1}, "registry_hash")
    route_manifest = _hashed({"schema_version": 1}, "manifest_hash")
    capsule = M336K11NativeExecutionCapsuleReceipt.build(
        repository=ROOT,
        route_registry_hash=registry["registry_hash"],
        typed_route_manifest_hash=route_manifest["manifest_hash"],
        dependency_manifest=manifest,
        effective_environment=effective,
    )
    profile = m336k_official_profile_registry().profile("m336k8-final-v4")
    binding = M336K11OfficialControllerExecutableBinding.build(
        profile=profile,
        source_identity_receipt_hash=source["receipt_hash"],
        source_identity_hash=source["live_project_source_identity"],
        environment_manifest_hash=environment["environment_manifest_hash"],
        manifest=manifest,
        effective_environment=effective,
        route_registry_hash=registry["registry_hash"],
        typed_route_manifest_hash=route_manifest["manifest_hash"],
        native_stage_worker_source_hash=capsule.stage_worker_bytes_hash,
        native_command_contract_hash=capsule.command_contract_hash,
    )
    native_route = M336K11NativeRouteManifest.build(
        profile=profile, binding=binding, capsule=capsule
    )
    startup_binding = _hashed(
        {
            "controller_executable_dependency_manifest_hash": manifest.manifest_hash,
            "startup_policy_hash": plan.startup_policy.policy_hash,
            "sanitized_environment_policy_hash": sanitized["receipt_hash"],
            "startup_receipt_schema_hash": manifest.startup_receipt_schema_hash,
            "bootstrap_source_hash": manifest.bootstrap_source_hash,
            "windows_launcher_source_hash": manifest.windows_launcher_source_hash,
        },
        "binding_hash",
    )
    authorization = _hashed(
        {
            "executable_dependency_manifest_hash": manifest.manifest_hash,
            "official_controller_executable_binding_hash": binding.binding_hash,
            "official_executable_binding_receipt_hash": binding.binding_hash,
        },
        "authorization_hash",
    )
    post = _hashed(
        {
            "controller_executable_dependency_manifest_hash": manifest.manifest_hash,
            "official_controller_executable_binding_hash": binding.binding_hash,
            "effective_environment_binding_receipt_hash": effective.receipt_hash,
            "native_execution_capsule_receipt_hash": capsule.receipt_hash,
            "native_route_manifest_hash": native_route.manifest_hash,
            "official_executable_binding_receipt_hash": binding.binding_hash,
        },
        "bundle_hash",
    )
    request = build_m336k11_final_request_binding(
        official_controller_executable_binding_hash=binding.binding_hash,
        builder_identity_hash=content_hash("builder"),
    )
    return {
        "plan": plan,
        "startup": startup,
        "sanitized": sanitized,
        "source": source,
        "environment": environment,
        "handles": handles,
        "manifest": manifest,
        "effective": effective,
        "registry": registry,
        "route_manifest": route_manifest,
        "capsule": capsule,
        "profile": profile,
        "binding": binding,
        "native_route": native_route,
        "startup_binding": startup_binding,
        "authorization": authorization,
        "post": post,
        "request": request,
        "private": private,
    }


def _verify(graph: dict, **changes):
    values = {**graph, **changes}
    manifest = values["manifest"]
    manifest_bytes = (canonical_json(manifest.canonical_object()) + "\n").encode()
    return verify_m336k11_official_executable_binding(
        binding=values["binding"],
        manifest=manifest,
        active_alias_bytes=values.get("alias_bytes", manifest_bytes),
        canonical_manifest_bytes=manifest_bytes,
        startup_policy=values["plan"].startup_policy,
        sanitized_environment_policy=values["sanitized"],
        controller_environment_manifest=values["environment"],
        controller_source_identity=values["source"],
        effective_environment=values["effective"],
        controller_startup_binding=values["startup_binding"],
        native_capsule=values["capsule"],
        native_route=values["native_route"],
        route_registry=values["registry"],
        typed_route_manifest=values["route_manifest"],
        final_authorization=values["authorization"],
        post_freeze_input_bundle=values["post"],
        final_request=values["request"],
        component_scopes=values.get(
            "scopes",
            m336k11_official_component_scopes(),
        ),
        invocation_plan=values.get("plan", graph["plan"]),
        startup_receipt=values.get("startup", graph["startup"]),
        executable_handles=values.get("handles", graph["handles"]),
        native_stage_worker_bytes=values.get(
            "native_stage_worker_bytes",
            (ROOT / "scripts/m336k2_run_stage.py").read_bytes(),
        ),
        expected_target=ROOT / "scripts/m336k11_run_final_route.py",
    )


def _rehash_dataclass(value, hash_field: str, **changes):
    temporary = replace(value, **changes, **{hash_field: "0" * 64})
    body = asdict(temporary)
    body.pop(hash_field)
    return replace(temporary, **{hash_field: content_hash(body)})


def test_static_policy_and_effective_environment_are_separate(graph: dict) -> None:
    policy = build_m336k5_python_startup_policy()
    assert policy.policy_hash == graph["manifest"].static_startup_policy_hash
    for name in ("TEMP", "TMP"):
        first = build_m336k5_sanitized_environment(
            platform_role="WINDOWS", parent_environment={name: "C:/one"}
        )
        second = build_m336k5_sanitized_environment(
            platform_role="WINDOWS", parent_environment={name: "D:/two"}
        )
        assert (
            first.startup_policy_hash
            == second.startup_policy_hash
            == policy.policy_hash
        )
        assert first.environment_hash != second.environment_hash
    first_home = build_m336k5_sanitized_environment(
        platform_role="WINDOWS", parent_environment={"HOME": "C:/one"}
    )
    second_home = build_m336k5_sanitized_environment(
        platform_role="WINDOWS", parent_environment={"HOME": "D:/two"}
    )
    assert first_home.startup_policy_hash == second_home.startup_policy_hash
    assert first_home.environment_hash == second_home.environment_hash


def test_f35_failure_is_reproduced_from_committed_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historical = json.loads(
        (
            F35_COMPONENTS / "18-controller_executable_dependency_manifest.json"
        ).read_text(encoding="utf-8")
    )
    allowed = {
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "PATHEXT",
        "PROGRAMDATA",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "WINDIR",
    }
    for name in allowed:
        monkeypatch.delenv(name, raising=False)
    for name in (
        "COMSPEC",
        "PATHEXT",
        "PROGRAMDATA",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "WINDIR",
    ):
        monkeypatch.setenv(name, "redacted")
    assert (
        minimal_environment_policy_identity()
        == "476f9fb7422f6f8bc644e8266021a50df8ede0f4f65ea765f51f3f7671fa7360"
    )
    with pytest.raises(
        M336K2ProtocolError, match="M336K2 executable manifest is invalid"
    ):
        executable_dependency_manifest_from_dict(historical)


def test_v4_route_registry_covers_the_executable_closure(graph: dict) -> None:
    registry = build_m336k5_route_registry(ROOT, "m336k8", profile_id="m336k8-final-v4")
    paths = {item.repository_path for item in registry.components}
    assert {
        "src/ai_brain/stage3/acquisition/m336k11_execution.py",
        "scripts/m336k11_build_component_bundle.py",
        "scripts/m336k11_materialize_f36.py",
        "scripts/m336k11_materialize_prospective_freeze.py",
        "scripts/m336k11_run_final_route.py",
    }.issubset(paths)


def test_v4_v5_and_v6_builders_do_not_require_a_denied_legacy_route() -> None:
    source = (ROOT / "scripts/m336k5_build_component_bundle.py").read_text(
        encoding="utf-8"
    )
    condition_start = source.index("if profile_id not in {")
    condition_end = source.index("}:", condition_start)
    condition = source[condition_start:condition_end]
    assert all(
        name in condition
        for name in (
            "M336K11_PROFILE_ID",
            "M336K12_PROFILE_ID",
            "M336K13_PROFILE_ID",
        )
    )
    assert "_write_m336k7_persistent_capsule_route(output)" in source
    compatibility_source = (
        ROOT / "src/ai_brain/stage3/acquisition/m336k8_request.py"
    ).read_text(encoding="utf-8")
    assert (
        '"controller_executable_dependency_manifest": (\n'
        "                    M336K11HermeticExecutableDependencyManifest.from_dict"
    ) in compatibility_source
    assert (
        "require_capsule_route_authority=(\n"
        "                freeze.contract_role\n"
        "                not in {"
    ) in compatibility_source
    legacy_validator_source = (
        ROOT / "src/ai_brain/stage3/acquisition/m336k7_request.py"
    ).read_text(encoding="utf-8")
    assert (
        "if require_capsule_route_authority:\n"
        "        verify_m336k7_persistent_capsule_route_binding("
    ) in legacy_validator_source


def test_v4_prospective_freeze_has_a_distinct_build_receipt_name() -> None:
    manifest = object.__new__(M336K8FreezeManifest)
    object.__setattr__(manifest, "contract_role", M336K8FreezeManifest.ROLE_V4)
    object.__setattr__(manifest, "implementation_tip", "a" * 40)
    object.__setattr__(manifest, "exact_qualification_sha", "a" * 40)
    object.__setattr__(manifest, "exact_freeze_sha", "0" * 40)

    assert manifest._build_receipt_name() == "prospective_freeze_build_receipt.json"

    object.__setattr__(manifest, "exact_qualification_sha", "b" * 40)
    assert manifest._build_receipt_name() == "f36_build_receipt.json"


def test_current_binding_alias_live_inputs_and_native_plan(graph: dict) -> None:
    receipt = _verify(graph)
    assert receipt.status == "PASS"
    components = build_official_executable_components(
        manifest=graph["manifest"],
        effective_environment=graph["effective"],
        official_binding=graph["binding"],
        native_capsule=graph["capsule"],
        native_route=graph["native_route"],
    )
    assert (
        components["controller_executable_dependency_manifest"]
        == components["executable_dependency_manifest"]
    )
    verify_m336k11_live_execution_inputs(
        manifest=graph["manifest"],
        effective_environment=graph["effective"],
        invocation_plan=graph["plan"],
        startup_receipt=graph["startup"],
        executable_handles=graph["handles"],
        native_stage_worker_bytes=(ROOT / "scripts/m336k2_run_stage.py").read_bytes(),
        native_capsule=graph["capsule"],
        expected_target=ROOT / "scripts/m336k11_run_final_route.py",
    )
    request = graph["private"] / "stage-request.json"
    request.write_text("{}\n", encoding="utf-8", newline="\n")
    plan = build_m336k11_native_execution_plan(
        repository=ROOT,
        python_executable=graph["handles"]["python"],
        stage_request=request,
        stage_receipt_root=graph["private"] / "receipts",
        route_run_id="m336k8.final-java.outcome-a.v4",
        exact_f36_sha="a" * 40,
        route_registry_hash=graph["registry"]["registry_hash"],
        dependency_manifest=graph["manifest"],
        effective_environment=graph["effective"],
        capsule=graph["capsule"],
    )
    assert all(command.arguments[:2] == ("-s", "-B") for command in plan.commands)


def test_official_verifier_rejects_a_self_hashed_effective_failure(
    graph: dict,
) -> None:
    effective = _rehash_dataclass(
        graph["effective"],
        "receipt_hash",
        unexpected_variable_count=1,
        status="FAIL",
    )
    effective.verify()
    with pytest.raises(M336K2ProtocolError, match="effective environment did not pass"):
        _verify(graph, effective=effective)


def test_official_binding_rejects_rehearsal_scopes(graph: dict) -> None:
    manifest = _rehash_dataclass(
        graph["manifest"], "manifest_hash", execution_scope=REHEARSAL
    )
    effective = _rehash_dataclass(
        graph["effective"], "receipt_hash", execution_scope=REHEARSAL
    )
    with pytest.raises(M336K2ProtocolError, match="official executable input"):
        M336K11OfficialControllerExecutableBinding.build(
            profile=graph["profile"],
            source_identity_receipt_hash=graph["source"]["receipt_hash"],
            source_identity_hash=graph["source"]["live_project_source_identity"],
            environment_manifest_hash=graph["environment"]["environment_manifest_hash"],
            manifest=manifest,
            effective_environment=effective,
            route_registry_hash=graph["registry"]["registry_hash"],
            typed_route_manifest_hash=graph["route_manifest"]["manifest_hash"],
            native_stage_worker_source_hash=graph["capsule"].stage_worker_bytes_hash,
            native_command_contract_hash=graph["capsule"].command_contract_hash,
        )


def test_startup_receipt_from_another_invocation_plan_is_rejected(
    graph: dict,
) -> None:
    other_plan = build_m336k5_python_invocation(
        platform_role="WINDOWS",
        process_role="VALIDATE_ONLY",
        python_executable=graph["handles"]["python"],
        git_executable=graph["handles"]["git"],
        powershell_executable=graph["handles"]["powershell"],
        repository=ROOT,
        working_directory=ROOT,
        bootstrap_script=ROOT / "scripts/m336k5_python_bootstrap.py",
        target=ROOT / "scripts/m336k11_run_final_route.py",
        execute_arguments=("--request", "different-prospective.json"),
        validate_arguments=("--validate-only",),
        execute_startup_receipt=graph["private"] / "other-execute-startup.json",
        validate_startup_receipt=graph["private"] / "other-validate-startup.json",
        parent_environment={
            "SYSTEMROOT": "C:/Windows",
            "TEMP": "C:/private/temp-a",
            "TMP": "C:/private/tmp-a",
        },
    )
    assert other_plan.sanitized_environment == graph["plan"].sanitized_environment
    assert other_plan.invocation_plan_hash != graph["plan"].invocation_plan_hash
    with pytest.raises(M336K2ProtocolError, match="live executable binding changed"):
        _verify(graph, plan=other_plan)


def test_historical_f35_loader_is_read_only_and_v4_is_historical(
    graph: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    historical = json.loads(
        (
            F35_COMPONENTS / "18-controller_executable_dependency_manifest.json"
        ).read_text(encoding="utf-8")
    )
    monkeypatch.setattr(
        "ai_brain.stage3.acquisition.m336k2_execution.minimal_environment_policy_identity",
        lambda: (_ for _ in ()).throw(AssertionError("live environment read")),
    )
    parsed = load_historical_executable_components_read_only(historical)
    assert parsed.manifest_hash == historical["manifest_hash"]
    registry = m336k_official_profile_registry()
    assert registry.profile("m336k8-final-v3").profile_status is (
        M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
    )
    assert (
        graph["profile"].profile_status
        is M336KOfficialRouteProfileStatus.HISTORICAL_READ_ONLY
    )


@pytest.mark.parametrize("case", M336K11_MUTATION_CASES)
def test_closed_under_rehash_executable_mutations(case: str, graph: dict) -> None:
    number = M336K11_MUTATION_CASES.index(case) + 1
    operation = None
    if number in {1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 33, 34}:
        effective = _rehash_dataclass(
            graph["effective"],
            "receipt_hash",
            actual_startup_receipt_sanitized_environment_hash=content_hash(case),
        )
        operation = lambda: _verify(graph, effective=effective)
    elif number in {5, 12, 13, 14, 15, 16, 17, 23, 25, 26}:
        authorization = _hashed(
            {
                **{
                    name: value
                    for name, value in graph["authorization"].items()
                    if name != "authorization_hash"
                },
                "executable_dependency_manifest_hash": content_hash(case),
            },
            "authorization_hash",
        )
        operation = lambda: _verify(graph, authorization=authorization)
    elif number == 18:
        manifest = _rehash_dataclass(
            graph["manifest"], "manifest_hash", bindings=graph["manifest"].bindings[:-1]
        )
        operation = manifest.verify
    elif number in {19, 30}:
        scopes = {
            **m336k11_official_component_scopes(),
            "duplicate_executable_dependency_manifest": OFFICIAL_CONTROLLER,
        }
        operation = lambda: _verify(graph, scopes=scopes)
    elif number in {20, 21, 22}:
        binding = graph["manifest"].bindings[0]
        field = {20: "file_sha256", 21: "path_identity_hash", 22: "semantic_version"}[
            number
        ]
        changed_value = content_hash(case) if number != 22 else "mutated-version"
        changed = replace(binding, **{field: changed_value}, binding_hash="0" * 64)
        if number == 22:
            changed = replace(
                changed, semantic_version_hash=content_hash(changed.semantic_version)
            )
        binding_body = asdict(changed)
        binding_body.pop("binding_hash")
        changed = replace(changed, binding_hash=content_hash(binding_body))
        manifest = _rehash_dataclass(
            graph["manifest"],
            "manifest_hash",
            bindings=(changed, *graph["manifest"].bindings[1:]),
        )
        operation = lambda: _verify(graph, manifest=manifest)
    elif number == 24:
        environment = _hashed(
            {"schema_version": 2, "project_source_identity_hash": content_hash(case)},
            "environment_manifest_hash",
        )
        operation = lambda: _verify(graph, environment=environment)
    elif number == 27:
        operation = lambda: _verify(graph, alias_bytes=b"{}\n")
    elif number in {28, 29}:
        scope = HISTORICAL_READ_ONLY if number == 28 else REHEARSAL
        scopes = {
            **m336k11_official_component_scopes(),
            "executable_dependency_manifest": scope,
        }
        operation = lambda: _verify(graph, scopes=scopes)
    elif number == 31:
        forged = replace(
            _verify(graph),
            executable_semantic_mismatch_count=1,
            status="PASS",
            receipt_hash="0" * 64,
        )
        body = asdict(forged)
        body.pop("receipt_hash")
        forged = replace(forged, receipt_hash=content_hash(body))
        operation = forged.verify
    elif number in {32, 35}:
        scopes = {
            name: scope
            for name, scope in m336k11_official_component_scopes().items()
            if name != "official_executable_binding_receipt"
        }
        operation = lambda: _verify(graph, scopes=scopes)
    elif number == 36:
        leaked_body = {
            **{
                name: value
                for name, value in graph["sanitized"].items()
                if name != "receipt_hash"
            },
            "private_value": "C:/private/temp-a",
        }
        leaked = _hashed(leaked_body, "receipt_hash")
        operation = lambda: _verify(graph, sanitized=leaked)
    elif number == 37:
        scopes = {
            **m336k11_official_component_scopes(),
            "persistent_capsule_executable_dependency_manifest": (OFFICIAL_CONTROLLER),
        }
        operation = lambda: _verify(graph, scopes=scopes)
    elif number == 38:
        historical = m336k_official_profile_registry().profile("m336k8-final-v3")
        binding = _rehash_dataclass(
            graph["binding"],
            "binding_hash",
            official_profile_id=historical.profile_id,
            official_profile_hash=historical.profile_hash,
        )
        operation = binding.verify
    else:
        raise AssertionError(f"unhandled M336K11 mutation {number}: {case}")
    with pytest.raises(M336K2ProtocolError):
        operation()


def test_mutation_suite_shape_and_receipt_codec(graph: dict) -> None:
    receipt = _verify(graph)
    assert len(M336K11_MUTATION_CASES) == 38
    assert len(set(M336K11_MUTATION_CASES)) == 38
    assert (
        M336K11OfficialExecutableBindingReceipt.from_dict(receipt.canonical_object())
        == receipt
    )
