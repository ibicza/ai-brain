from __future__ import annotations

import io
import json
import runpy
import shutil
import subprocess
import zipfile
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition import m336j_transport
from ai_brain.stage3.acquisition.m336j_execution import (
    KarinaPrivateExecutionCapsule,
    KarinaRemoteTokenClass,
    RemoteExecutableDependency,
    RemoteExecutableDependencyManifest,
    audit_remote_dependencies,
    build_remote_command_plan,
    compute_m336j_project_source_identity,
    dependency_manifest_from_dict,
    load_private_execution_capsule,
    minimal_environment,
    minimal_environment_policy,
    public_value_has_private_path,
    render_remote_command,
)
from ai_brain.stage3.acquisition.m336j_freeze import (
    M336J_ACQUISITION_RUN_ID,
    M336J_BRANCH_REF,
    M336J_EXACT_Q23_SHA,
    build_m336j_final_acquisition_authorization,
    m336j_final_acquisition_authorization_from_dict,
)
from ai_brain.stage3.acquisition.m336j_mutations import (
    M336J_MUTATIONS,
    M336J_ROBUST_PASS_MUTATIONS,
    build_mutation_report,
    mutation_result,
)
from ai_brain.stage3.acquisition.m336j_registry import (
    M336J_REMOTE_COMPONENT_ROLES,
    build_m336j_route_manifest,
    build_m336j_route_registry,
    command_renderer_identity_hash,
)
from ai_brain.stage3.acquisition.m336j_transport import (
    canonical_tree_archive,
    extract_canonical_tree_archive,
    parse_bound_json_response,
    parse_framed_tree_response,
)

HASH = "a" * 64


def _capsule(tmp_path: Path) -> tuple[Path, KarinaPrivateExecutionCapsule]:
    value = {
        "schema_version": 1,
        "execution_strategy": "DIRECT_PROJECT_PYTHON",
        "python_executable": "/private env/bin/python",
        "git_executable": "/usr/bin/git",
        "java_executable": "/private jdk/bin/java",
        "javac_executable": "/private jdk/bin/javac",
        "shell_executable": "/bin/sh",
        "repository_checkout": "/private repo/checkout",
        "private_root": "/private root/m336j",
        "expected_head": "b" * 40,
        "host_identity_receipt": "/private repo/checkout/host.json",
        "expected_host_identity_receipt_hash": "c" * 64,
        "expected_public_jdk_identity_receipt_hash": "d" * 64,
        "expected_public_receipt_hash": "e" * 64,
    }
    path = tmp_path / "capsule.json"
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    return path, load_private_execution_capsule(path)


def _dependency(role: str, *, path_lookup: bool = False):
    body = {
        "logical_role": role,
        "public_binary_hash": HASH,
        "normalized_version_hash": HASH,
        "invocation_count_limit": 1,
        "path_lookup_allowed": path_lookup,
        "network_allowed": False,
        "child_process_policy": "NO_CHILD_PROCESSES",
    }
    return RemoteExecutableDependency(**body, identity_hash=content_hash(body))


def _manifest(*, bare: bool = False):
    roles = ("PROJECT_PYTHON", "GIT", "JAVA", "JAVAC", "POSIX_SHELL")
    dependencies = tuple(
        _dependency(role, path_lookup=bare and role == "GIT") for role in roles
    )
    body = {
        "schema_version": 1,
        "execution_strategy": "DIRECT_PROJECT_PYTHON",
        "dependencies": dependencies,
        "dependency_count": len(dependencies),
        "bare_executable_lookup_count": sum(
            item.path_lookup_allowed for item in dependencies
        ),
        "network_enabled_dependency_count": 0,
    }
    return RemoteExecutableDependencyManifest(**body, manifest_hash=content_hash(body))


def _plan(tmp_path: Path, argument: str = "plain"):
    _path, capsule = _capsule(tmp_path)
    plan = build_remote_command_plan(
        component_id="m336j.test.v1",
        capsule=capsule,
        arguments=(
            (KarinaRemoteTokenClass.FLAG, "-B"),
            (KarinaRemoteTokenClass.PRIVATE_PATH, "/private repo/worker.py"),
            (KarinaRemoteTokenClass.OPAQUE_ARGUMENT, argument),
        ),
        expected_capsule_receipt_hash="e" * 64,
    )
    return capsule, plan


def test_private_capsule_accepts_posix_paths_with_spaces_on_windows(
    tmp_path: Path,
) -> None:
    _path, capsule = _capsule(tmp_path)
    assert capsule.python_executable.as_posix() == "/private env/bin/python"
    assert capsule.private_root.as_posix() == "/private root/m336j"


def test_project_source_identity_ignores_evidence_but_binds_implementation(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "artifacts").mkdir()
    source = tmp_path / "src" / "worker.py"
    evidence = tmp_path / "artifacts" / "receipt.json"
    source.write_text("value = 1\n", encoding="utf-8")
    evidence.write_text("{}\n", encoding="utf-8")
    git = Path(shutil.which("git") or "")
    subprocess.run((str(git), "-C", str(tmp_path), "init", "-q"), check=True)
    subprocess.run((str(git), "-C", str(tmp_path), "add", "src"), check=True)
    before = compute_m336j_project_source_identity(tmp_path, git)
    evidence.write_text('{"status":"PASS"}\n', encoding="utf-8")
    assert compute_m336j_project_source_identity(tmp_path, git) == before
    source.write_text("value = 2\n", encoding="utf-8")
    assert compute_m336j_project_source_identity(tmp_path, git) != before


@pytest.mark.parametrize(
    "mutation",
    (
        {"python_executable": "python"},
        {"repository_checkout": "repo"},
        {"execution_strategy": "ABSOLUTE_UV_OFFLINE_FROZEN"},
        {"expected_head": "bad"},
        {"expected_public_receipt_hash": "bad"},
        {"private_root": "/private repo/checkout/subdir"},
    ),
)
def test_private_capsule_identity_mutations_fail(
    tmp_path: Path, mutation: dict
) -> None:
    path, _capsule_value = _capsule(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8")) | mutation
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError):
        load_private_execution_capsule(path)


def test_minimal_environment_omits_uv_and_profiles() -> None:
    environment = dict(minimal_environment())
    policy = minimal_environment_policy()
    assert environment["PATH"] == "/usr/bin:/bin"
    assert ".local" not in environment["PATH"]
    assert policy.uv_directory_present is False
    assert policy.profile_startup_allowed is False
    assert policy.login_shell_allowed is False


@pytest.mark.parametrize("argument", ("with space", "a'b", "a;b", "$(id)"))
def test_renderer_quotes_shell_metacharacters_without_interpreting_them(
    tmp_path: Path, argument: str
) -> None:
    capsule, plan = _plan(tmp_path, argument)
    rendered = render_remote_command(plan, shell_executable=capsule.shell_executable)
    assert argument not in rendered or "'" in rendered
    assert ".profile" not in rendered
    assert ".bashrc" not in rendered
    assert "bash -l" not in rendered


@pytest.mark.parametrize("argument", ("bad\x00value", "bad\nvalue", "bad\rvalue"))
def test_renderer_rejects_unrepresentable_tokens(tmp_path: Path, argument: str) -> None:
    with pytest.raises(ValueError):
        _plan(tmp_path, argument)


def test_renderer_rejects_unpaired_surrogate(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _plan(tmp_path, "bad\ud800value")


def test_renderer_rejects_bare_executable(tmp_path: Path) -> None:
    _path, capsule = _capsule(tmp_path)
    changed = replace(capsule, python_executable=Path("python"))
    with pytest.raises(ValueError):
        build_remote_command_plan(
            component_id="m336j.test.v1",
            capsule=changed,
            arguments=(),
            expected_capsule_receipt_hash=HASH,
        )


def test_renderer_rejects_rehashed_plan_mutation(tmp_path: Path) -> None:
    capsule, plan = _plan(tmp_path)
    changed = replace(plan, component_id="mutated")
    with pytest.raises(ValueError):
        render_remote_command(changed, shell_executable=capsule.shell_executable)


def test_dependency_manifest_round_trip_and_audit() -> None:
    manifest = _manifest()
    restored = dependency_manifest_from_dict(asdict(manifest))
    audit = audit_remote_dependencies(
        restored, ("PROJECT_PYTHON", "GIT", "JAVA", "JAVAC", "POSIX_SHELL")
    )
    assert audit.status == "PASS"
    assert audit.bare_executable_lookup_count == 0


def test_dependency_audit_blocks_bare_lookup() -> None:
    with pytest.raises(ValueError):
        audit_remote_dependencies(
            _manifest(bare=True),
            ("PROJECT_PYTHON", "GIT", "JAVA", "JAVAC", "POSIX_SHELL"),
        )


def test_dependency_audit_blocks_unregistered_role() -> None:
    with pytest.raises(ValueError):
        audit_remote_dependencies(_manifest(), ("PROJECT_PYTHON", "UV"))


def test_dependency_audit_blocks_changed_identity() -> None:
    manifest = _manifest()
    changed = replace(manifest.dependencies[0], public_binary_hash="f" * 64)
    mutated = replace(manifest, dependencies=(changed, *manifest.dependencies[1:]))
    with pytest.raises(ValueError):
        audit_remote_dependencies(
            mutated, ("PROJECT_PYTHON", "GIT", "JAVA", "JAVAC", "POSIX_SHELL")
        )


def test_dependency_parser_blocks_changed_manifest_hash() -> None:
    value = asdict(_manifest())
    value["dependency_count"] = 99
    with pytest.raises(ValueError):
        dependency_manifest_from_dict(value)


def test_dependency_parser_blocks_network_enabled_dependency() -> None:
    manifest = _manifest()
    changed = replace(manifest.dependencies[0], network_allowed=True)
    changed_body = asdict(changed)
    changed_body.pop("identity_hash")
    changed = replace(changed, identity_hash=content_hash(changed_body))
    body = {
        **asdict(manifest),
        "dependencies": tuple(
            asdict(item) for item in (changed, *manifest.dependencies[1:])
        ),
        "network_enabled_dependency_count": 1,
    }
    body.pop("manifest_hash")
    body["manifest_hash"] = content_hash(body)
    with pytest.raises(ValueError):
        dependency_manifest_from_dict(body)


def test_registry_contains_every_remote_component() -> None:
    registry = build_m336j_route_registry()
    roles = {item.route_role for item in registry.components}
    assert set(M336J_REMOTE_COMPONENT_ROLES) <= roles
    assert registry.remote_component_count == len(M336J_REMOTE_COMPONENT_ROLES)
    assert registry.unresolved_remote_component_count == 0
    assert registry.incompatible_remote_schema_edge_count == 0
    assert registry.unregistered_remote_command_call_site_count == 0


def test_route_manifest_binds_capsule_renderer_dependencies_and_environment() -> None:
    registry = build_m336j_route_registry()
    manifest = build_m336j_route_manifest(
        registry,
        execution_capsule_public_receipt_hash="1" * 64,
        remote_command_renderer_hash="2" * 64,
        executable_dependency_manifest_hash="3" * 64,
        minimal_environment_policy_hash="4" * 64,
    )
    assert manifest.execution_capsule_public_receipt_hash == "1" * 64
    assert manifest.remote_command_renderer_hash == "2" * 64
    assert command_renderer_identity_hash() != HASH


def test_canonical_archive_is_repeatable_and_extracts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "b.txt").write_bytes(b"b")
    (source / "nested" / "a.txt").write_bytes(b"a")
    first = canonical_tree_archive(source, prefix="payload")
    second = canonical_tree_archive(source, prefix="payload")
    assert first == second
    destination = tmp_path / "destination"
    count, _tree_hash = extract_canonical_tree_archive(
        first,
        destination=destination,
        expected_payload_hash=bytes_hash(first),
    )
    assert count == 2
    assert (destination / "payload" / "nested" / "a.txt").read_bytes() == b"a"


def test_archive_hash_mutation_fails_before_extraction(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_bytes(b"a")
    payload = canonical_tree_archive(source, prefix="payload")
    with pytest.raises(ValueError):
        extract_canonical_tree_archive(
            payload,
            destination=tmp_path / "destination",
            expected_payload_hash=HASH,
        )


def test_archive_path_traversal_fails_closed(tmp_path: Path) -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../escape", b"bad")
    payload = output.getvalue()
    with pytest.raises(ValueError):
        extract_canonical_tree_archive(
            payload,
            destination=tmp_path / "destination",
            expected_payload_hash=bytes_hash(payload),
        )
    assert not (tmp_path / "escape").exists()


def _bound_response(**mutations) -> bytes:
    body = {
        "request_hash": "1" * 64,
        "component_binding_hash": "2" * 64,
        "host_identity_hash": "3" * 64,
        "status": "PASS",
        **mutations,
    }
    return (
        canonical_json({**body, "receipt_hash": content_hash(body)}) + "\n"
    ).encode()


def test_bound_response_accepts_exact_bindings() -> None:
    value = parse_bound_json_response(
        _bound_response(),
        request_hash="1" * 64,
        component_binding_hash="2" * 64,
        host_identity_hash="3" * 64,
    )
    assert value["status"] == "PASS"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("request_hash", "4" * 64),
        ("component_binding_hash", "4" * 64),
        ("host_identity_hash", "4" * 64),
        ("status", "FAIL"),
    ),
)
def test_bound_response_mutations_fail(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        parse_bound_json_response(
            _bound_response(**{field: value}),
            request_hash="1" * 64,
            component_binding_hash="2" * 64,
            host_identity_hash="3" * 64,
        )


def test_framed_response_binds_header_and_payload() -> None:
    payload = b"tree"
    raw = _bound_response(payload_hash=bytes_hash(payload), payload_size=len(payload))
    header, observed = parse_framed_tree_response(
        raw.rstrip(b"\n") + b"\n" + payload,
        request_hash="1" * 64,
        component_binding_hash="2" * 64,
        host_identity_hash="3" * 64,
    )
    assert header["payload_hash"] == bytes_hash(payload)
    assert observed == payload


def test_framed_response_blocks_payload_hash_mutation() -> None:
    payload = b"tree"
    raw = _bound_response(payload_hash=bytes_hash(payload), payload_size=len(payload))
    with pytest.raises(ValueError):
        parse_framed_tree_response(
            raw.rstrip(b"\n") + b"\nchanged",
            request_hash="1" * 64,
            component_binding_hash="2" * 64,
            host_identity_hash="3" * 64,
        )


def test_framed_response_blocks_payload_size_mutation() -> None:
    payload = b"tree"
    raw = _bound_response(payload_hash=bytes_hash(payload), payload_size=999)
    with pytest.raises(ValueError):
        parse_framed_tree_response(
            raw.rstrip(b"\n") + b"\n" + payload,
            request_hash="1" * 64,
            component_binding_hash="2" * 64,
            host_identity_hash="3" * 64,
        )


def test_public_values_reject_private_paths() -> None:
    assert public_value_has_private_path({"path": "/home/user/private"})
    assert public_value_has_private_path({"path": r"C:\Users\private"})
    assert not public_value_has_private_path({"binary_hash": HASH})


def test_current_remote_route_contains_no_bare_uv_command() -> None:
    source = Path("scripts/m336i_java_final_route.py").read_text(encoding="utf-8")
    assert "uv run python" not in source
    assert '"scp"' not in source


@pytest.mark.parametrize("name", ("uv", "python", "python3", "git", "java", "javac"))
def test_command_builder_rejects_every_bare_executable_name(
    tmp_path: Path, name: str
) -> None:
    _path, capsule = _capsule(tmp_path)
    changed = replace(capsule, python_executable=Path(name))
    with pytest.raises(ValueError):
        build_remote_command_plan(
            component_id="m336j.test.v1",
            capsule=changed,
            arguments=(),
            expected_capsule_receipt_hash=HASH,
        )


def test_route_uses_single_registered_ssh_subprocess_boundary() -> None:
    transport = Path("src/ai_brain/stage3/acquisition/m336j_transport.py").read_text(
        encoding="utf-8"
    )
    controller = Path("scripts/m336i_java_final_route.py").read_text(encoding="utf-8")
    worker = Path("scripts/m336j_karina_execution.py").read_text(encoding="utf-8")
    assert transport.count("subprocess.run(") == 1
    assert "invoke_karina_command(" in controller
    assert "subprocess.run(" not in worker


def test_m336j_worker_request_uses_remote_component_binding() -> None:
    route = runpy.run_path("scripts/m336i_java_final_route.py")
    args = SimpleNamespace(
        karina_private_root="/private/run",
        karina_private_capsule=Path("private-capsule.json"),
        supplied_f24_sha="a" * 40,
        karina_repository="/private/repository",
        karina_javac="/private/jdk/bin/javac",
    )
    authorization = SimpleNamespace(
        karina_public_jdk_identity_receipt_hash="b" * 64,
        r24_implementation_tree_identity="c" * 64,
        publication_boundary_hash="d" * 64,
        karina_stable_host_identity_receipt_hash="e" * 64,
    )
    request = route["_karina_request"](args, authorization, action="MATERIALIZE")
    component = next(
        item
        for item in build_m336j_route_registry().components
        if item.route_role == "REMOTE_SELECTED_SOURCE_MATERIALIZER"
    )
    assert request["route_component_binding_hash"] == component.binding_hash


def test_private_capsule_rejects_overlapping_reverse_root(tmp_path: Path) -> None:
    path, _capsule_value = _capsule(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["repository_checkout"] = "/private root/m336j/repository"
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError):
        load_private_execution_capsule(path)


def test_renderer_rejects_relative_shell_handle(tmp_path: Path) -> None:
    _capsule_value, plan = _plan(tmp_path)
    with pytest.raises(ValueError):
        render_remote_command(plan, shell_executable="sh")


def test_transport_failure_preserves_nonzero_exit_class() -> None:
    error = subprocess.CalledProcessError(127, ("ssh",))
    assert error.returncode == 127


def test_windows_ssh_environment_keeps_system_crypto_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    monkeypatch.setenv("PATH", r"C:\untrusted")
    environment = m336j_transport._local_ssh_environment()
    assert environment["PROGRAMDATA"] == r"C:\ProgramData"
    assert "PATH" not in environment


def test_quality_runner_preserves_verified_venv_python_handle() -> None:
    source = Path("scripts/m336j_run_exact_quality.py").read_text(encoding="utf-8")
    assert "Path(sys.executable).absolute()" in source
    assert "Path(sys.executable).resolve" not in source


def test_m336j_authorization_round_trip() -> None:
    authorization = build_m336j_final_acquisition_authorization(
        acquisition_mode="FINAL",
        exact_q23_sha=M336J_EXACT_Q23_SHA,
        r24_implementation_tree_identity="1" * 64,
        q24_evidence_identity="2" * 64,
        f24_parent_sha="3" * 40,
        f24_freeze_tree_identity="4" * 64,
        route_registry_hash="5" * 64,
        route_manifest_hash="6" * 64,
        acquisition_provider_source_hash="7" * 64,
        acquisition_provider_callable_signature_hash="8" * 64,
        candidate_pool_hash="9" * 64,
        acquisition_policy_hash="a" * 64,
        denylist_hash="b" * 64,
        authority_root_hash="c" * 64,
        selector_policy_hash="d" * 64,
        threshold_manifest_hash="e" * 64,
        publication_boundary_hash="f" * 64,
        public_artifact_contract_hash="0" * 64,
        windows_public_jdk_identity_receipt_hash="1" * 64,
        karina_public_jdk_identity_receipt_hash="2" * 64,
        karina_stable_host_identity_receipt_hash="3" * 64,
        acquisition_run_id=M336J_ACQUISITION_RUN_ID,
        allowed_network_hosts=("example.invalid",),
        expected_global_acquisition_count=1,
        expected_windows_acquisition_count=1,
        expected_karina_acquisition_count=0,
        branch_ref=M336J_BRANCH_REF,
    )
    assert (
        m336j_final_acquisition_authorization_from_dict(
            json.loads(canonical_json(authorization))
        )
        == authorization
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("acquisition_run_id", "m336i.final-java.global-acquisition.v1"),
        ("branch_ref", "refs/heads/wrong"),
        ("exact_q23_sha", "0" * 40),
    ),
)
def test_m336j_authorization_rejects_frozen_identity_mutation(
    field: str, value: str
) -> None:
    authorization = build_m336j_final_acquisition_authorization(
        acquisition_mode="FINAL",
        exact_q23_sha=M336J_EXACT_Q23_SHA,
        r24_implementation_tree_identity="1" * 64,
        q24_evidence_identity="2" * 64,
        f24_parent_sha="3" * 40,
        f24_freeze_tree_identity="4" * 64,
        route_registry_hash="5" * 64,
        route_manifest_hash="6" * 64,
        acquisition_provider_source_hash="7" * 64,
        acquisition_provider_callable_signature_hash="8" * 64,
        candidate_pool_hash="9" * 64,
        acquisition_policy_hash="a" * 64,
        denylist_hash="b" * 64,
        authority_root_hash="c" * 64,
        selector_policy_hash="d" * 64,
        threshold_manifest_hash="e" * 64,
        publication_boundary_hash="f" * 64,
        public_artifact_contract_hash="0" * 64,
        windows_public_jdk_identity_receipt_hash="1" * 64,
        karina_public_jdk_identity_receipt_hash="2" * 64,
        karina_stable_host_identity_receipt_hash="3" * 64,
        acquisition_run_id=M336J_ACQUISITION_RUN_ID,
        allowed_network_hosts=("example.invalid",),
        expected_global_acquisition_count=1,
        expected_windows_acquisition_count=1,
        expected_karina_acquisition_count=0,
        branch_ref=M336J_BRANCH_REF,
    )
    changed = asdict(authorization)
    changed[field] = value
    body = dict(changed)
    body.pop("authorization_hash")
    changed["authorization_hash"] = content_hash(body)
    with pytest.raises(ValueError):
        m336j_final_acquisition_authorization_from_dict(changed)


def test_complete_mutation_report_accepts_no_mutation() -> None:
    rows = tuple(
        mutation_result(
            mutation_id,
            validator_class="REAL_TEST_VALIDATOR",
            failure=(
                None
                if mutation_id in M336J_ROBUST_PASS_MUTATIONS
                else ValueError(mutation_id)
            ),
        )
        for mutation_id in M336J_MUTATIONS
    )
    report = build_mutation_report(rows, final_acquisition_reservation_count=0)
    assert report.executed_mutation_count == 40
    assert report.rejected_mutation_count == 40
    assert report.accepted_mutation_count == 0


def test_incomplete_mutation_report_fails_closed() -> None:
    with pytest.raises(ValueError):
        build_mutation_report((), final_acquisition_reservation_count=0)
