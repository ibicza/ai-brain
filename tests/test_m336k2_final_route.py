from __future__ import annotations

import base64
import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition import m336k2_execution
from ai_brain.stage3.acquisition.m336k2_acquisition import (
    M336K2_FINAL_ACQUISITION_RUN_ID,
    build_m336k2_final_authorization,
    validate_m336k2_candidate_pool,
)
from ai_brain.stage3.acquisition.m336k2_controller import (
    M336K2_FINAL_RUN_ID,
    M336K2_ROUTE_STAGES,
    M336K2StageReceipt,
    build_m336k2_schema_registry,
    build_preledger_proof,
    run_m336k2_final_controller,
)
from ai_brain.stage3.acquisition.m336k2_execution import (
    M336K2_REQUIRED_EXECUTABLE_ROLES,
    m336k2_python_invocation_handle,
    verify_m336k2_executable_handles,
    verify_m336k2_python_environment_manifest,
)
from ai_brain.stage3.acquisition.m336k2_freeze import _semantic_component_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_MUTATION_MATRIX,
    M336K2_READY_STATUS,
    M336K2_REQUIRED_FREEZE_COMPONENTS,
    M336K2_ROUTE_EVENTS,
    M336K2FreezeManifest,
    M336K2FrozenComponent,
    M336K2MutationLayer,
    M336K2ProtocolError,
    M336K2RouteLedger,
    build_executable_binding,
    build_unspent_readiness_state,
    m336k2_minimal_environment,
    validate_count_neutral_pool,
    verify_complete_freeze,
    verify_mutation_rejected_at_layer,
)
from ai_brain.stage3.acquisition.m336k2_publication import (
    build_m336k2_publication_contract,
    scan_m336k2_public_tree,
)
from ai_brain.stage3.acquisition.m336k2_readiness import (
    M336K2ReadinessResult,
    verify_m336k2_readiness_destinations,
)
from ai_brain.stage3.acquisition.m336k2_stage import (
    _append_evaluator_event,
    _evaluator_receipt,
    _karina_expected_head,
    _rehearsal_provider,
    _verify_request,
    _write_private_state,
)
from scripts.m336k2_qualify_disposable_protocol import _commit as disposable_commit


def test_route_ledger_enforces_complete_exact_order_and_one_shot_counts(
    tmp_path: Path,
) -> None:
    ledger = M336K2RouteLedger(tmp_path / "route.jsonl")
    context = content_hash("context")
    for event in M336K2_ROUTE_EVENTS:
        ledger.append(event, context_hash=context, operation_hash=content_hash(event))
    receipt = ledger.receipt()
    assert receipt.final_event == "FINAL_VERIFICATION_COMPLETED"
    assert receipt.event_count == len(M336K2_ROUTE_EVENTS)
    assert receipt.acquisition_reservation_count == 1
    assert receipt.acquisition_invocation_count == 1
    assert receipt.selector_reservation_count == 1
    assert receipt.selector_invocation_count == 1
    assert receipt.evaluator_reservation_count == 1
    assert receipt.evaluator_invocation_count == 1
    assert receipt.retry_count == 0
    with pytest.raises(M336K2ProtocolError, match="terminal"):
        ledger.append(
            "FINAL_VERIFICATION_COMPLETED",
            context_hash=context,
            operation_hash=content_hash("again"),
        )


def test_native_evaluator_ledger_reserves_once_and_coordinates_both_platforms(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "evaluator.jsonl"
    events = (
        "EVALUATOR_RESERVED",
        "GOLDENS_CREATED",
        "WINDOWS_EVALUATION_COMPLETED",
        "KARINA_EVALUATION_COMPLETED",
        "EVALUATION_COMPARISON_PASSED",
    )
    for event in events:
        _append_evaluator_event(ledger, event, content_hash(event))
    receipt = _evaluator_receipt(ledger)
    assert receipt["reservation_count"] == 1
    assert receipt["windows_evaluation_count"] == 1
    assert receipt["karina_evaluation_count"] == 1
    assert receipt["retry_count"] == 0
    with pytest.raises(M336K2ProtocolError, match="event order changed"):
        _append_evaluator_event(
            ledger, "EVALUATOR_RESERVED", content_hash("second reservation")
        )


def test_private_stage_state_is_durably_replaced(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    value = {"schema_version": 1, "status": "PASS"}

    _write_private_state(state, value)

    assert state.read_text(encoding="utf-8") == canonical_json(value) + "\n"
    assert not state.with_name(state.name + ".next").exists()


def test_rehearsal_provider_uses_candidate_isolated_acquisition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    provider = _rehearsal_provider({"execution_mode": "REHEARSAL"})

    assert set(provider) == {"maven_provider", "scm_provider"}
    assert _rehearsal_provider({"execution_mode": "FINAL"}) == {}


def test_schema_registry_covers_all_twenty_eight_route_stages() -> None:
    registry = build_m336k2_schema_registry()
    assert len(M336K2_ROUTE_STAGES) == len(registry.bindings) == 28
    assert tuple(item.stage for item in registry.bindings) == M336K2_ROUTE_STAGES
    assert len({item.request_schema_hash for item in registry.bindings}) == 28
    assert len({item.response_schema_hash for item in registry.bindings}) == 28
    assert registry.incompatible_edge_count == 0


def test_one_controller_executes_complete_rehearsal_route(tmp_path: Path) -> None:
    route_registry_hash = content_hash("route-registry")
    exact_f28 = "a" * 40

    def guard():
        return build_preledger_proof(
            preflight_receipt_hash="1" * 64,
            freeze_receipt_hash="2" * 64,
            authorization_receipt_hash="3" * 64,
            exact_f28_sha=exact_f28,
            route_registry_hash=route_registry_hash,
        )

    calls = []

    def worker(request):
        calls.append(request.event)
        body = {
            "schema_version": 1,
            "event": request.event,
            "request_hash": request.request_hash,
            "operation_hash": content_hash((request.event, request.request_hash)),
            "status": "PASS",
        }
        return M336K2StageReceipt(**body, receipt_hash=content_hash(body))

    ledger = M336K2RouteLedger(tmp_path / "route.jsonl")
    result = run_m336k2_final_controller(
        route_run_id="m336k2.disposable.rehearsal.01",
        execution_mode="REHEARSAL",
        exact_f28_sha=exact_f28,
        route_registry_hash=route_registry_hash,
        ledger=ledger,
        preledger_guard=guard,
        worker=worker,
        output=tmp_path / "receipt.json",
    )
    assert tuple(calls) == M336K2_ROUTE_EVENTS[3:]
    assert result.status == "OUTCOME A — VERIFIED_GENERALIZATION"
    assert result.acquisition_count == 1
    assert result.selector_count == 1
    assert result.evaluator_reservation_count == 1
    assert result.retry_count == 0
    assert result.route_registry_hash == route_registry_hash


def test_controller_failure_is_terminal_and_not_retryable(tmp_path: Path) -> None:
    route_registry_hash = content_hash("route-registry")
    exact_f28 = "b" * 40

    def guard():
        return build_preledger_proof(
            preflight_receipt_hash="1" * 64,
            freeze_receipt_hash="2" * 64,
            authorization_receipt_hash="3" * 64,
            exact_f28_sha=exact_f28,
            route_registry_hash=route_registry_hash,
        )

    def worker(request):
        raise RuntimeError("bounded worker failure")

    ledger = M336K2RouteLedger(tmp_path / "route.jsonl")
    with pytest.raises(RuntimeError, match="bounded worker failure"):
        run_m336k2_final_controller(
            route_run_id="m336k2.disposable.failure.01",
            execution_mode="REHEARSAL",
            exact_f28_sha=exact_f28,
            route_registry_hash=route_registry_hash,
            ledger=ledger,
            preledger_guard=guard,
            worker=worker,
            output=tmp_path / "receipt.json",
        )
    assert ledger.receipt().final_event == "FINAL_ROUTE_FAILED"
    with pytest.raises(M336K2ProtocolError, match="ledger must be fresh"):
        run_m336k2_final_controller(
            route_run_id="m336k2.disposable.failure.01",
            execution_mode="REHEARSAL",
            exact_f28_sha=exact_f28,
            route_registry_hash=route_registry_hash,
            ledger=ledger,
            preledger_guard=guard,
            worker=worker,
            output=tmp_path / "receipt.json",
        )


@pytest.mark.parametrize(
    ("route_run_id", "mode"),
    [(M336K2_FINAL_RUN_ID, "REHEARSAL"), ("rehearsal", "FINAL")],
)
def test_final_run_identity_cannot_be_spent_in_wrong_mode(
    tmp_path: Path, route_run_id: str, mode: str
) -> None:
    with pytest.raises(M336K2ProtocolError, match="identity is reserved"):
        run_m336k2_final_controller(
            route_run_id=route_run_id,
            execution_mode=mode,
            exact_f28_sha="c" * 40,
            route_registry_hash=content_hash("route-registry"),
            ledger=M336K2RouteLedger(tmp_path / "route.jsonl"),
            preledger_guard=lambda: pytest.fail("guard must not run"),
            worker=lambda request: pytest.fail("worker must not run"),
            output=tmp_path / "receipt.json",
        )


@pytest.mark.parametrize(
    "event",
    [
        "FREEZE_VERIFIED",
        "SELECTOR_RESERVED",
        "EVALUATOR_RESERVED",
        "H_PUBLICATION_READY",
        "E_PUBLICATION_READY",
    ],
)
def test_route_ledger_rejects_wrong_order_at_ordering_layer(
    tmp_path: Path, event: str
) -> None:
    ledger = M336K2RouteLedger(tmp_path / "route.jsonl")
    with pytest.raises(M336K2ProtocolError, match="out of order"):
        ledger.append(
            event,
            context_hash=content_hash("context"),
            operation_hash=content_hash(event),
        )


def test_terminal_failure_is_final_and_cannot_retry(tmp_path: Path) -> None:
    ledger = M336K2RouteLedger(tmp_path / "route.jsonl")
    context = content_hash("context")
    ledger.append(
        "PREFLIGHT_VERIFIED",
        context_hash=context,
        operation_hash=content_hash("preflight"),
    )
    ledger.fail(context_hash=context, operation_hash=content_hash("worker-crash"))
    with pytest.raises(M336K2ProtocolError, match="terminal"):
        ledger.append(
            "FREEZE_VERIFIED",
            context_hash=context,
            operation_hash=content_hash("retry"),
        )


def _destinations(root: Path) -> dict[str, Path]:
    return {
        "acquisition_ledger": root / "acquisition.jsonl",
        "selector_ledger": root / "selector.jsonl",
        "evaluator_ledger": root / "evaluator.jsonl",
        "route_state_ledger": root / "route.jsonl",
        "vault": root / "vault",
        "selected_source_snapshot": root / "selected",
        "windows_production": root / "windows-production",
        "karina_production": root / "karina-production",
        "evaluator_root": root / "evaluator",
    }


def test_readiness_proves_all_global_states_unspent(tmp_path: Path) -> None:
    result = build_unspent_readiness_state(_destinations(tmp_path))
    assert result.status == M336K2_READY_STATUS
    assert result.destination_count == result.absent_destination_count == 9
    assert result.final_candidate_source_body_bytes == 0
    assert (
        sum(
            (
                result.acquisition_reservations,
                result.acquisition_invocations,
                result.selector_reservations,
                result.selector_invocations,
                result.evaluator_reservations,
                result.evaluator_invocations,
                result.route_state_events,
            )
        )
        == 0
    )


def test_readiness_binds_every_private_destination_handle(tmp_path: Path) -> None:
    destinations = _destinations(tmp_path)
    identities = tuple(
        sorted(
            (name, content_hash(path.resolve(strict=False).as_posix()))
            for name, path in destinations.items()
        )
    )
    value = M336K2ReadinessResult(
        schema_version=1,
        contract_role="PUBLIC_SAFE_M336K2_Q28_READINESS",
        exact_implementation_tip="1" * 40,
        branch="disposable/m336k2-proof",
        upstream_sha="1" * 40,
        remote_sha="1" * 40,
        clean_worktree_count=1,
        dirty_worktree_count=0,
        evidence_hashes=(),
        evidence_bytes_hashes=(),
        final_destination_identity_hashes=identities,
        final_state_readiness_hash="2" * 64,
        acquisition_reservations=0,
        acquisition_invocations=0,
        selector_reservations=0,
        selector_invocations=0,
        evaluator_reservations=0,
        evaluator_invocations=0,
        route_state_events=0,
        final_candidate_source_body_bytes=0,
        status=M336K2_READY_STATUS,
        readiness_hash="3" * 64,
    )
    verify_m336k2_readiness_destinations(value, destinations)
    changed = dict(destinations)
    changed["vault"] = tmp_path / "other-vault"
    with pytest.raises(M336K2ProtocolError, match="destination handles changed"):
        verify_m336k2_readiness_destinations(value, changed)


@pytest.mark.parametrize("stale", tuple(_destinations(Path("root"))))
def test_readiness_rejects_each_preexisting_final_destination(
    tmp_path: Path, stale: str
) -> None:
    destinations = _destinations(tmp_path)
    path = destinations[stale]
    if path.suffix:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("spent", encoding="utf-8")
    else:
        path.mkdir(parents=True)
    with pytest.raises(M336K2ProtocolError, match="already spent"):
        build_unspent_readiness_state(destinations)


def test_pool_diversity_is_threshold_driven_not_historical_count_driven() -> None:
    candidates = tuple(
        {
            "family_id": f"family-{index}",
            "organization_id": f"organization-{index}",
            "requirement": "OPTIONAL",
        }
        for index in range(81)
    )
    receipt = validate_count_neutral_pool(
        candidates,
        minimum_families=80,
        minimum_organizations=64,
        maximum_per_organization=2,
    )
    assert receipt["candidate_family_count"] == 81
    assert receipt["status"] == "PASS"


def test_pool_diversity_rejects_capacity_organization_and_requirement_mutations() -> (
    None
):
    base = [
        {
            "family_id": f"family-{index}",
            "organization_id": f"organization-{index}",
            "requirement": "OPTIONAL",
        }
        for index in range(80)
    ]
    mutations = (
        base[:-1],
        [
            {**row, "organization_id": f"organization-{index // 3}"}
            for index, row in enumerate(base)
        ],
        [
            {**row, "requirement": "REQUIRED"} if index == 0 else row
            for index, row in enumerate(base)
        ],
    )
    for mutated in mutations:
        with pytest.raises(M336K2ProtocolError, match="diversity"):
            validate_count_neutral_pool(
                mutated,
                minimum_families=80,
                minimum_organizations=64,
                maximum_per_organization=2,
            )


def _metadata_pool() -> dict:
    candidates = []
    for index in range(80):
        body = {
            "family_id": f"family-{index:03d}",
            "organization_id": f"organization-{index:03d}",
            "coordinate": f"example.organization{index}:artifact{index}:1.0.0",
            "source_url": f"https://repo.example.invalid/o{index}/a{index}-sources.jar",
            "pom_url": f"https://repo.example.invalid/o{index}/a{index}.pom",
            "scm_repository": f"https://scm.example.invalid/o{index}/a{index}",
            "scm_commit": f"{index + 1:040x}",
            "source_content_length": 1000 + index,
            "metadata_authority": "MAVEN_CENTRAL_HEAD",
            "metadata_compilation_risk": "MEDIUM",
            "metadata_receipt_hashes": [f"{index + 11:064x}"],
            "repository_source_prefixes": [],
            "pom_license_declarations": ["Apache-2.0"],
            "requirement": "OPTIONAL",
        }
        candidates.append({**body, "policy_hash": content_hash(body)})
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_METADATA_ONLY_CANDIDATE_POOL",
        "candidate_count": len(candidates),
        "organization_count": len(candidates),
        "maximum_candidates_per_organization": 1,
        "pre_freeze_source_body_bytes": 0,
        "claims_final_eligibility": False,
        "candidates": candidates,
    }
    return {**body, "pool_hash": content_hash(body)}


def test_native_metadata_pool_is_count_neutral_and_uses_no_old_phase_fields() -> None:
    pool = _metadata_pool()
    assert len(validate_m336k2_candidate_pool(pool)) == 80
    assert "pre_f22_source_body_bytes_received" not in pool
    assert "r21_sha" not in pool
    assert "exact_r27_sha" not in pool


def test_native_authorization_binds_all_global_one_shot_limits() -> None:
    pool = _metadata_pool()
    values = {
        "execution_mode": "FINAL",
        "exact_implementation_tip": "1" * 40,
        "exact_q28_sha": "2" * 40,
        "branch_ref": "refs/heads/exp/stage3-m336k2-final-java-outcome-a-v12",
        "acquisition_run_id": M336K2_FINAL_ACQUISITION_RUN_ID,
        "candidate_pool_hash": pool["pool_hash"],
        "acquisition_policy_hash": "3" * 64,
        "archive_policy_hash": "4" * 64,
        "candidate_terminal_policy_hash": "5" * 64,
        "global_continuation_policy_hash": "6" * 64,
        "route_manifest_hash": "7" * 64,
        "route_registry_hash": "8" * 64,
        "schema_registry_hash": "9" * 64,
        "readiness_hash": "a" * 64,
        "executable_dependency_manifest_hash": "b" * 64,
        "python_environment_manifest_hash": "c" * 64,
        "authority_statement_hash": "d" * 64,
        "disclosure_registry_manifest_hash": "e" * 64,
        "allowed_network_hosts": ("repo.example.invalid", "scm.example.invalid"),
        "minimum_candidate_families": 80,
        "minimum_organizations": 64,
        "maximum_candidates_per_organization": 2,
        "acquisition_reservation_limit": 1,
        "selector_reservation_limit": 1,
        "evaluator_reservation_limit": 1,
        "candidate_retry_limit": 0,
        "candidate_replacement_limit": 0,
        "pre_freeze_source_body_bytes": 0,
    }
    authorization = build_m336k2_final_authorization(**values)
    assert authorization.acquisition_reservation_limit == 1
    assert authorization.selector_reservation_limit == 1
    assert authorization.evaluator_reservation_limit == 1
    assert authorization.candidate_retry_limit == 0
    assert authorization.candidate_replacement_limit == 0


def test_bare_executable_is_rejected_before_subprocess() -> None:
    with pytest.raises(M336K2ProtocolError, match="bare executable"):
        build_executable_binding(
            Path("git"), role="git", version_arguments=("--version",)
        )


def test_executable_without_version_api_uses_explicit_content_identity(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "scp.exe"
    executable.write_bytes(b"frozen executable")
    binding = build_executable_binding(
        executable.resolve(), role="scp", version_arguments=()
    )
    assert binding.version_arguments == ()
    assert binding.semantic_version == f"CONTENT_IDENTITY_ONLY:{binding.file_sha256}"


def test_executable_handle_verification_replays_every_frozen_binding(
    monkeypatch, tmp_path: Path
) -> None:
    bindings = tuple(
        type("Binding", (), {"role": role})()
        for role in sorted(M336K2_REQUIRED_EXECUTABLE_ROLES)
    )
    manifest = type("Manifest", (), {"bindings": bindings})()
    handles = {role: tmp_path / role for role in M336K2_REQUIRED_EXECUTABLE_ROLES}
    calls = []
    monkeypatch.setattr(
        m336k2_execution,
        "verify_executable_binding",
        lambda path, binding: calls.append((path, binding.role)),
    )

    verify_m336k2_executable_handles(manifest, handles)

    assert set(calls) == {(handles[role], role) for role in handles}


def test_exact_quality_preflight_passes_explicit_repository() -> None:
    source = Path("scripts/m336k2_run_exact_quality.py").read_text(encoding="utf-8")
    assert "build_m336k2_route_registry(__import__('pathlib').Path('.'))" in source
    assert "build_m336k2_route_registry()" not in source
    assert '"PATH": os.pathsep.join(' in source
    assert (
        "executable_directories = (git.parent, javac.parent, python.parent)" in source
    )


def test_disposable_commit_force_adds_only_the_validated_ignored_root(
    tmp_path: Path,
) -> None:
    discovered = shutil.which("git")
    assert discovered is not None
    git = Path(discovered).resolve(strict=True)
    repository = tmp_path / "repository"
    repository.mkdir()

    def run(*arguments: str) -> str:
        return subprocess.run(
            (str(git), *arguments),
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()

    run("init", "-q", "-b", "main")
    run("config", "user.name", "M336K2 Test")
    run("config", "user.email", "m336k2@example.invalid")
    (repository / ".gitignore").write_text("artifacts/\n", encoding="utf-8")
    (repository / "base.txt").write_text("base\n", encoding="utf-8")
    run("add", ".gitignore", "base.txt")
    run("commit", "-q", "-m", "base")
    evidence = repository / "artifacts/m336k2/disposable/q-like/evidence.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("{}\n", encoding="utf-8")

    commit = disposable_commit(
        git,
        repository,
        "M-33.6k.2 disposable Q-like",
        "artifacts/m336k2/disposable/q-like",
    )

    assert (
        run("show", f"{commit}:artifacts/m336k2/disposable/q-like/evidence.json")
        == "{}"
    )
    assert not run("status", "--porcelain=v1")


def test_freeze_uses_verified_semantic_component_hash(tmp_path: Path) -> None:
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_TEST_AUTHORIZATION",
    }
    semantic_hash = content_hash(body)
    path = tmp_path / "authorization.json"
    path.write_text(
        canonical_json({**body, "authorization_hash": semantic_hash}) + "\n",
        encoding="utf-8",
    )

    assert _semantic_component_hash(path, "authorization_hash") == semantic_hash
    assert bytes_hash(path.read_bytes()) != semantic_hash

    path.write_text(
        canonical_json({**body, "authorization_hash": "0" * 64}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(M336K2ProtocolError, match="semantic component hash"):
        _semantic_component_hash(path, "authorization_hash")


def test_minimal_environment_disables_network_install_and_user_site() -> None:
    environment = m336k2_minimal_environment()
    assert environment["PATH"] == ""
    assert environment["PIP_NO_INDEX"] == "1"
    assert environment["UV_OFFLINE"] == "1"
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    if "PROGRAMDATA" in os.environ:
        assert environment["PROGRAMDATA"] == os.environ["PROGRAMDATA"]


def test_live_python_environment_must_equal_frozen_manifest(monkeypatch) -> None:
    monkeypatch.setattr(
        "ai_brain.stage3.acquisition.m336k2_execution.build_m336k2_python_environment_manifest",
        lambda **_kwargs: {"environment_manifest_hash": "a" * 64},
    )
    with pytest.raises(M336K2ProtocolError, match="environment identity changed"):
        verify_m336k2_python_environment_manifest(
            {"environment_manifest_hash": "b" * 64},
            repository=Path("repository"),
            python_executable=Path("python"),
            git_executable=Path("git"),
        )


def test_python_invocation_handle_is_not_resolved_away_from_venv(
    monkeypatch, tmp_path: Path
) -> None:
    handle = tmp_path / "venv" / "bin" / "python"
    monkeypatch.setattr(
        "ai_brain.stage3.acquisition.m336k2_execution.sys.executable", str(handle)
    )
    assert m336k2_python_invocation_handle() == handle.absolute()


def _load_metadata_pool_script(name: str):
    from importlib.util import module_from_spec, spec_from_file_location

    script = Path(__file__).parents[1] / "scripts" / "m336k2_build_metadata_pool.py"
    spec = spec_from_file_location(name, script)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_exact_quality_script(name: str):
    from importlib.util import module_from_spec, spec_from_file_location

    script = Path(__file__).parents[1] / "scripts" / "m336k2_run_exact_quality.py"
    spec = spec_from_file_location(name, script)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_component_bundle_script(name: str):
    from importlib.util import module_from_spec, spec_from_file_location

    script = Path(__file__).parents[1] / "scripts" / "m336k2_build_component_bundle.py"
    spec = spec_from_file_location(name, script)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_evidence_binding_script(name: str):
    from importlib.util import module_from_spec, spec_from_file_location

    script = Path(__file__).parents[1] / "scripts" / "m336k2_build_evidence_bindings.py"
    spec = spec_from_file_location(name, script)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evidence_binding_loader_rejects_non_object_json(tmp_path: Path) -> None:
    module = _load_evidence_binding_script("m336k2_evidence_bindings")
    path = tmp_path / "source.json"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(M336K2ProtocolError, match="not an object"):
        module._object(path)


def test_component_bundle_wraps_legacy_boundary_with_native_hash(
    tmp_path: Path,
) -> None:
    module = _load_component_bundle_script("m336k2_component_bundle")
    path = tmp_path / "boundary.json"
    path.write_text('{"schema_version":1,"raw_source_publication":false}\n')
    value = module._publication_boundary_component(path)
    claimed = value.pop("publication_boundary_hash")
    assert claimed == content_hash(value)


def test_exact_quality_children_run_with_minimal_offline_environment(
    tmp_path: Path,
) -> None:
    module = _load_exact_quality_script("m336k2_exact_quality")
    (tmp_path / "src").mkdir()
    environment = module._environment(tmp_path)
    assert environment["PATH"] == ""
    assert environment["PIP_NO_INDEX"] == "1"
    assert environment["UV_OFFLINE"] == "1"
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTHONPATH"] == str((tmp_path / "src").resolve())


def test_metadata_guard_rejects_source_and_scm_archive_body_gets() -> None:
    module = _load_metadata_pool_script("m336k2_metadata_pool")
    for url in (
        "https://repo.example/a-sources.jar",
        "https://codeload.example/project.zip",
        "https://example.test/project.tar.gz",
    ):
        with pytest.raises(ValueError, match="forbidden"):
            module._metadata_bytes(url, maximum=16)


def test_metadata_tag_resolution_prefers_peeled_commit(
    monkeypatch, tmp_path: Path
) -> None:
    from subprocess import CompletedProcess

    module = _load_metadata_pool_script("m336k2_metadata_pool_tags")
    tag_object = "1" * 40
    commit = "2" * 40

    def fake_run(*_args, **_kwargs):
        return CompletedProcess(
            args=(),
            returncode=0,
            stdout=(f"{tag_object}\trefs/tags/v1.0\n{commit}\trefs/tags/v1.0^{{}}\n"),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module._resolve_tag(
        tmp_path / "git", "https://github.com/o/r.git", "v1.0", "1.0"
    ) == ("v1.0", commit)


def test_metadata_read_retries_transient_timeout_twice(monkeypatch) -> None:
    module = _load_metadata_pool_script("m336k2_metadata_pool_retry")
    attempts = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _maximum):
            return b"metadata"

    def fake_urlopen(_request, *, timeout):
        attempts.append(timeout)
        if len(attempts) < 3:
            raise TimeoutError("transient metadata timeout")
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    assert (
        module._metadata_bytes("https://example.test/metadata", maximum=16)
        == b"metadata"
    )
    assert attempts == [60, 60, 60]


def test_metadata_discovery_uses_body_free_central_browse_api(monkeypatch) -> None:
    module = _load_metadata_pool_script("m336k2_metadata_pool_browse")
    observed = {}

    def fake_post(url, payload):
        observed.update({"url": url, "payload": payload})
        return {
            "components": [
                {
                    "namespace": "org.example",
                    "name": "example-core",
                    "packaging": "jar",
                    "ec": [".pom", "-sources.jar", ".jar"],
                    "latestVersionInfo": {
                        "version": "1.2.3",
                        "timestampUnixWithMS": 123,
                    },
                }
            ]
        }

    monkeypatch.setattr(module, "_metadata_json_post", fake_post)
    assert module._search_page(4) == (
        {
            "g": "org.example",
            "a": "example-core",
            "v": "1.2.3",
            "p": "jar",
            "ec": [".pom", "-sources.jar", ".jar"],
            "timestamp": 123,
        },
    )
    assert observed["url"] == module._BROWSE
    assert observed["payload"]["page"] == 4
    assert observed["payload"]["size"] == 20


def _freeze(tmp_path: Path) -> M336K2FreezeManifest:
    components = []
    for index, name in enumerate(sorted(M336K2_REQUIRED_FREEZE_COMPONENTS)):
        relative = f"components/{index:02d}-{name}.json"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('{"name":"' + name + '"}\n').encode())
        components.append(
            M336K2FrozenComponent(
                name=name,
                relative_path=relative,
                bytes_hash=bytes_hash(path.read_bytes()),
                byte_count=path.stat().st_size,
            )
        )
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_F28_FREEZE",
        "implementation_tip": "1" * 40,
        "exact_q28_sha": "2" * 40,
        "exact_f28_sha": "3" * 40,
        "committed_f28_tree": "4" * 40,
        "readiness_hash": "5" * 64,
        "authorization_hash": "6" * 64,
        "route_hash": "7" * 64,
        "components": tuple(components),
        "self_reference_safe_exclusions": ("freeze_manifest.json",),
        "prospective_freeze_tree_hash": "8" * 64,
    }
    return M336K2FreezeManifest(**body, manifest_hash=content_hash(body))


def test_complete_freeze_rejects_missing_extra_and_changed_components(
    tmp_path: Path,
) -> None:
    manifest = _freeze(tmp_path)
    verify_complete_freeze(tmp_path, manifest)
    changed = tmp_path / manifest.components[0].relative_path
    changed.write_text("changed\n", encoding="utf-8")
    with pytest.raises(M336K2ProtocolError, match="component changed"):
        verify_complete_freeze(tmp_path, manifest)
    body = asdict(manifest)
    body.pop("manifest_hash")
    body["components"] = tuple(manifest.components[1:])
    missing = M336K2FreezeManifest(**body, manifest_hash=content_hash(body))
    with pytest.raises(M336K2ProtocolError, match="component set"):
        verify_complete_freeze(tmp_path, missing)


def test_mutation_matrix_is_complete_and_wrong_layer_count_is_zero() -> None:
    expected_counts = {
        M336K2MutationLayer.ARCHIVE: 21,
        M336K2MutationLayer.CANDIDATE: 19,
        M336K2MutationLayer.FREEZE: 18,
        M336K2MutationLayer.ORDERING: 8,
        M336K2MutationLayer.PUBLICATION: 12,
    }
    assert len(M336K2_MUTATION_MATRIX) == sum(expected_counts.values()) == 78
    assert {
        layer: tuple(M336K2_MUTATION_MATRIX.values()).count(layer)
        for layer in expected_counts
    } == expected_counts
    for mutation, layer in M336K2_MUTATION_MATRIX.items():
        verify_mutation_rejected_at_layer(mutation, layer)
        wrong = next(item for item in M336K2MutationLayer if item != layer)
        with pytest.raises(M336K2ProtocolError, match="wrong layer"):
            verify_mutation_rejected_at_layer(mutation, wrong)


@pytest.mark.parametrize(
    ("name", "payload", "counter"),
    [
        ("payload.java", b"public class X { int value; }", "source_leak_count"),
        (
            "encoded.json",
            base64.b64encode(b"public class X {" + b"a" * 256 + b"}"),
            "source_leak_count",
        ),
        (
            "encoded.json",
            (b"public class X {" + b"a" * 256 + b"}").hex().encode(),
            "source_leak_count",
        ),
        ("path.json", b'{"path":"C:\\\\Users\\\\secret"}', "absolute_path_count"),
        ("private_manifest.json", b"{}", "private_artifact_count"),
    ],
)
def test_publication_scan_rejects_source_encodings_paths_and_private_artifacts(
    tmp_path: Path, name: str, payload: bytes, counter: str
) -> None:
    (tmp_path / name).write_bytes(payload)
    report = scan_m336k2_public_tree(tmp_path, allowed_root_files=frozenset({name}))
    assert report[counter] > 0


def test_publication_scan_rejects_uncontracted_json(tmp_path: Path) -> None:
    (tmp_path / "unexpected.json").write_text("{}", encoding="utf-8")
    report = scan_m336k2_public_tree(tmp_path, allowed_root_files=frozenset())
    assert report["uncontracted_artifact_count"] == 1


def test_same_native_publication_contract_supports_disposable_roots() -> None:
    contract = build_m336k2_publication_contract(
        branch_ref="refs/heads/disposable/m336k2-proof",
        q_root="artifacts/m336k2/disposable/q-like",
        f_root="artifacts/m336k2/disposable/f-like",
        h_root="artifacts/m336k2/disposable/h-like",
        e_root="artifacts/m336k2/disposable/e-like",
        q_subject="M-33.6k.2 disposable Q-like",
        f_subject="M-33.6k.2 disposable F-like",
        h_subject="M-33.6k.2 disposable H-like",
        e_subject="M-33.6k.2 disposable E-like",
    )
    assert contract.contract_role == "M336K2_NATIVE_H28_E28_PUBLICATION_CONTRACT"
    assert len(contract.contract_hash) == 64


def test_karina_execution_remains_pinned_to_frozen_implementation_tip(
    tmp_path: Path,
) -> None:
    manifest = _freeze(tmp_path)
    path = tmp_path / "freeze_manifest.json"
    path.write_text(canonical_json(asdict(manifest)) + "\n", encoding="utf-8")
    assert _karina_expected_head({"freeze_manifest": str(path)}) == "1" * 40


def test_stage_request_rejects_final_destination_in_any_git_worktree(
    monkeypatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    other_worktree = tmp_path / "other-worktree"
    repository.mkdir()
    other_worktree.mkdir()
    handles = {}
    for role in (
        "git",
        "python",
        "java",
        "javac",
        "ssh",
        "scp",
        "tar",
        "powershell",
        "cmd",
    ):
        executable = tmp_path / f"{role}.exe"
        executable.write_bytes(b"executable")
        handles[role] = str(executable)
    destinations = {
        name: str(tmp_path / "external" / name)
        for name in (
            "acquisition_ledger",
            "selector_ledger",
            "evaluator_ledger",
            "route_state_ledger",
            "vault",
            "selected_source_snapshot",
            "windows_production",
            "karina_production",
            "evaluator_root",
        )
    }
    destinations["vault"] = str(other_worktree / "private-vault")
    request = {
        "schema_version": 1,
        "repository": str(repository),
        "git_executable": handles["git"],
        "python_executable": handles["python"],
        "exact_f28_sha": "3" * 40,
        "freeze_manifest": str(repository / "freeze.json"),
        "f28_attestation": str(tmp_path / "attestation.json"),
        "final_authorization": str(repository / "authorization.json"),
        "publication_contract": str(repository / "publication.json"),
        "route_run_id": "disposable-m336k2-test",
        "execution_mode": "REHEARSAL",
        "stage_state": str(tmp_path / "state.json"),
        "stage_receipt_root": str(tmp_path / "receipts"),
        "private_root": str(tmp_path / "private"),
        "authority_statement": str(repository / "authority.json"),
        "frozen_spdx_reference": str(repository / "spdx.json"),
        "windows_java": handles["java"],
        "windows_javac": handles["javac"],
        "final_destinations": destinations,
        "karina": {
            "private_execution_capsule": str(tmp_path / "capsule.json"),
            "public_execution_capsule_receipt": str(tmp_path / "public.json"),
            "executable_dependency_manifest": str(tmp_path / "dependencies.json"),
            "ssh_executable": handles["ssh"],
            "ssh_key": str(tmp_path / "key"),
            "known_hosts_file": str(tmp_path / "known-hosts"),
            "worker_endpoint": "opaque-endpoint",
            "repository": "/remote/repository",
            "private_root": "/remote/private",
            "private_capsule_remote": "/remote/capsule.json",
            "javac": "/remote/javac",
        },
        "executable_handles": handles,
    }
    monkeypatch.setattr(
        "ai_brain.stage3.acquisition.m336k2_stage._git_worktrees",
        lambda *_args: (repository, other_worktree),
    )
    with pytest.raises(M336K2ProtocolError, match="inside Git"):
        _verify_request(request)
