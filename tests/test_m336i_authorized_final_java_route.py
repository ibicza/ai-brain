from __future__ import annotations

import importlib.util
import inspect
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.java_jdk_provider import (
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.java_production import (
    run_java_acquisition_pipeline,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.m336d_final_pipeline import (
    _legal_archive_entry_path,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    build_source_entry_binding,
    build_source_entry_id,
)
from ai_brain.stage3.acquisition.m336g_publication import (
    ArtifactConfidentialityRole,
    _reject_private_payload,
)
from ai_brain.stage3.acquisition.m336g_staging import validate_public_staging
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336h_production import (
    M336HCompilerAwareProductionRequest,
    M336HCompilerAwareProductionResponse,
)
from ai_brain.stage3.acquisition.m336h_route import (
    refuse_m336h_unfrozen_final_acquisition,
)
from ai_brain.stage3.acquisition.m336i_acquisition import (
    M336I_ACQUISITION_EVENTS,
    M336I_FINAL_ACQUISITION_RUN_ID,
    M336I_FREEZE_MANIFEST_PATH,
    M336I_FROZEN_AUTHORIZATION_PATH,
    M336IAcquisitionCrash,
    M336IFinalAcquisitionLedger,
    M336IFinalAcquisitionRequest,
    acquisition_provider_identity,
    build_m336i_final_acquisition_authorization,
    compute_m336i_commit_tree_identity,
    compute_m336i_freeze_tree_identity,
    final_acquisition_authorization_from_dict,
    run_m336i_frozen_final_acquisition,
)
from ai_brain.stage3.acquisition.m336i_evaluation import (
    M336IIndependentEvaluationRequest,
    _field_evidence_gate_passes,
    _field_evidence_metrics,
    _semantic_metrics,
    _spdx_metrics,
    run_m336i_independent_java_evaluation,
)
from ai_brain.stage3.acquisition.m336i_production import (
    M336ICompilerAwareProductionRequest,
    build_m336i_production_seal,
    validate_m336i_production_authority,
)
from ai_brain.stage3.acquisition.m336i_readiness import (
    verify_m336i_quality_receipt,
)
from ai_brain.stage3.acquisition.m336i_registry import (
    M336IRouteComponentBinding,
    M336IRouteRegistry,
    build_m336i_final_java_route_manifest,
    build_m336i_final_java_route_registry,
    validate_m336i_route_registry,
)
from ai_brain.stage3.acquisition.m336i_route import M336IRouteStateLedger
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.spdx_license import SPDX_SNAPSHOT_ROOT


def test_field_evidence_gate_uses_independently_recomputed_metrics() -> None:
    passing = {
        "field_evidence_exactness": "1.000000",
        "field_evidence_missing_count": 0,
        "field_evidence_extra_count": 0,
        "field_evidence_duplicate_count": 0,
        "field_evidence_wrong_count": 0,
    }
    assert _field_evidence_gate_passes(passing)
    assert not _field_evidence_gate_passes({**passing, "field_evidence_wrong_count": 1})


def _run(*command: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _hashed(path: Path, hash_field: str, **body) -> dict:
    value = {**body, hash_field: content_hash(body)}
    write_canonical_json(path, value)
    return value


def test_freeze_tree_identity_includes_ignored_freeze_artifacts(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _run("git", "init", cwd=repository)
    _run("git", "config", "user.email", "m336i@example.invalid", cwd=repository)
    _run("git", "config", "user.name", "M336I Test", cwd=repository)
    (repository / ".gitignore").write_text("artifacts/\n", encoding="utf-8")
    _run("git", "add", ".gitignore", cwd=repository)
    _run("git", "commit", "-m", "baseline", cwd=repository)

    freeze_root = repository / Path(M336I_FROZEN_AUTHORIZATION_PATH).parent
    freeze_root.mkdir(parents=True)
    policy = freeze_root / "selector_policy.json"
    write_canonical_json(policy, {"schema_version": 1})
    initial = compute_m336i_freeze_tree_identity(repository)
    write_canonical_json(policy, {"schema_version": 2})
    changed = compute_m336i_freeze_tree_identity(repository)
    assert changed != initial

    write_canonical_json(repository / M336I_FROZEN_AUTHORIZATION_PATH, {})
    write_canonical_json(repository / M336I_FREEZE_MANIFEST_PATH, {})
    assert compute_m336i_freeze_tree_identity(repository) == changed


def test_authorized_rehearsal_fixture_meets_frozen_trust_capacity(
    tmp_path: Path,
) -> None:
    path = Path("scripts/m336i_build_authorized_rehearsal_fixture.py").resolve()
    spec = importlib.util.spec_from_file_location("m336i_authorized_fixture", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    source_root = tmp_path / "sources"
    paths = []
    for family in module.FAMILIES:
        for relative, raw in module._java_entries(family):
            target = source_root / family / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            paths.append(target)
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        tuple(paths),
        bundle_id="m336i-authorized-capacity",
        domain_tags=("java-api",),
        imported_at="1970-01-01T00:00:00Z",
        source_root=source_root,
        store=store,
    )
    index = index_java_bundle(bundle, store)
    supported_callables = tuple(
        item
        for item in index.declarations
        if item.member_kind in {"constructor", "method"} and item.supported
    )
    assert len(paths) == 180
    assert len(supported_callables) == 1080


def test_controller_inventory_ignores_only_prunable_worktree_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = Path("scripts/m336i_java_final_route.py").resolve()
    spec = importlib.util.spec_from_file_location("m336i_route_controller", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    missing = tmp_path / "already-removed-worktree"
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=f"worktree {missing}\nHEAD {'1' * 40}\ndetached\n\n"
        ),
    )
    assert module._worktrees(tmp_path) == ()


def _rehash_authorization(authorization, **changes):
    value = replace(authorization, **changes, authorization_hash="0" * 64)
    body = asdict(value)
    body.pop("authorization_hash")
    return replace(value, authorization_hash=content_hash(body))


def _rehash_component(component: M336IRouteComponentBinding, **changes):
    value = replace(component, **changes, binding_hash="0" * 64)
    body = asdict(value)
    body.pop("binding_hash")
    return replace(value, binding_hash=content_hash(body))


def _rehash_registry(registry: M336IRouteRegistry, components):
    value = replace(registry, components=tuple(components), registry_hash="0" * 64)
    body = asdict(value)
    body.pop("registry_hash")
    return replace(value, registry_hash=content_hash(body))


def _git_add_commit(repository: Path, message: str) -> str:
    _run("git", "add", "-A", cwd=repository)
    _run("git", "commit", "-m", message, cwd=repository)
    return _run("git", "rev-parse", "HEAD", cwd=repository)


def _provider_fixture(tmp_path: Path):
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    repository.mkdir()
    _run("git", "init", "--bare", str(remote))
    _run("git", "init", "-b", "exp/m336i-test", str(repository))
    _run("git", "config", "user.email", "m336i@example.invalid", cwd=repository)
    _run("git", "config", "user.name", "M336I Test", cwd=repository)
    _run("git", "remote", "add", "origin", str(remote), cwd=repository)
    (repository / "base.txt").write_text("q23\n", encoding="utf-8", newline="\n")
    q23 = _git_add_commit(repository, "Q23")
    (repository / "r24.txt").write_text("r24\n", encoding="utf-8", newline="\n")
    r24 = _git_add_commit(repository, "R24")

    frozen = repository / "frozen"
    frozen.mkdir()
    registry = build_m336i_final_java_route_registry()
    route = build_m336i_final_java_route_manifest(registry)
    write_canonical_json(frozen / "route_registry.json", registry)
    write_canonical_json(frozen / "route_manifest.json", route)
    pool_body = {
        "schema_version": 3,
        "policy_version": "m336g.metadata-pool.v1",
        "candidate_count": 0,
        "candidates": [],
        "organization_count": 0,
        "maximum_candidates_per_organization": 0,
        "metadata_compilation_risk_counts": [],
        "required_candidate_count": 0,
        "optional_candidate_count": 0,
        "pre_f22_source_body_bytes_received": 0,
        "claims_final_eligibility": False,
    }
    pool = _hashed(frozen / "candidate_pool.json", "pool_hash", **pool_body)
    policy = _hashed(
        frozen / "acquisition_policy.json",
        "acquisition_policy_hash",
        schema_version=1,
        acquisition_run_id=M336I_FINAL_ACQUISITION_RUN_ID,
        acquire_every_frozen_candidate=True,
        replacement_candidates_allowed=False,
        adaptive_family_substitution_allowed=False,
        global_acquisition_count=1,
        windows_acquisition_count=1,
        karina_acquisition_count=0,
        acquisition_reruns_allowed=False,
        allowed_network_hosts=[],
    )
    denylist = _hashed(
        frozen / "denylist.json", "denylist_hash", schema_version=1, entries=[]
    )
    authority = _hashed(
        frozen / "authority_root.json",
        "authority_root_hash",
        schema_version=1,
        authority="test",
    )
    (frozen / "authority.txt").write_text(
        "rehearsal authority\n", encoding="utf-8", newline="\n"
    )
    selector = _hashed(
        frozen / "selector_policy.json",
        "selector_policy_hash",
        schema_version=1,
        selector="m336f",
    )
    threshold = _hashed(
        frozen / "threshold.json",
        "threshold_manifest_hash",
        schema_version=1,
        minimum_metrics={},
    )
    publication = _hashed(
        frozen / "publication.json",
        "publication_boundary_policy_hash",
        schema_version=1,
        raw_source_publication=False,
    )
    public_contract = _hashed(
        frozen / "public_contract.json",
        "public_artifact_contract_hash",
        schema_version=1,
        allowed_entries=[],
    )
    windows_jdk_hash = "1" * 64
    karina_jdk_hash = "2" * 64
    _hashed(
        frozen / "jdk.json",
        "compiler_jdk_identities_hash",
        schema_version=1,
        windows_public_jdk_receipt_hash=windows_jdk_hash,
        karina_public_jdk_receipt_hash=karina_jdk_hash,
    )
    karina_host = _hashed(
        frozen / "karina_host.json",
        "receipt_hash",
        schema_version=1,
        verification_status="PASS",
        public_jdk_identity_receipt_hash=karina_jdk_hash,
    )
    q24 = _git_add_commit(repository, "Q24")
    freeze_identity = compute_m336i_freeze_tree_identity(repository)
    provider_source, provider_signature = acquisition_provider_identity()
    authorization = build_m336i_final_acquisition_authorization(
        acquisition_mode="REHEARSAL",
        exact_q23_sha=q23,
        r24_implementation_tree_identity=compute_m336i_commit_tree_identity(
            repository, r24
        ),
        q24_evidence_identity="4" * 64,
        f24_parent_sha=q24,
        f24_freeze_tree_identity=freeze_identity,
        route_registry_hash=registry.registry_hash,
        route_manifest_hash=route.manifest_hash,
        acquisition_provider_source_hash=provider_source,
        acquisition_provider_callable_signature_hash=provider_signature,
        candidate_pool_hash=pool["pool_hash"],
        acquisition_policy_hash=policy["acquisition_policy_hash"],
        denylist_hash=denylist["denylist_hash"],
        authority_root_hash=authority["authority_root_hash"],
        selector_policy_hash=selector["selector_policy_hash"],
        threshold_manifest_hash=threshold["threshold_manifest_hash"],
        publication_boundary_hash=publication["publication_boundary_policy_hash"],
        public_artifact_contract_hash=public_contract["public_artifact_contract_hash"],
        windows_public_jdk_identity_receipt_hash=windows_jdk_hash,
        karina_public_jdk_identity_receipt_hash=karina_jdk_hash,
        karina_stable_host_identity_receipt_hash=karina_host["receipt_hash"],
        acquisition_run_id=M336I_FINAL_ACQUISITION_RUN_ID,
        allowed_network_hosts=(),
        expected_global_acquisition_count=1,
        expected_windows_acquisition_count=1,
        expected_karina_acquisition_count=0,
        branch_ref="refs/heads/exp/m336i-test",
    )
    authorization_path = repository / M336I_FROZEN_AUTHORIZATION_PATH
    write_canonical_json(authorization_path, authorization)
    freeze_body = {
        "schema_version": 1,
        "authorization_hash": authorization.authorization_hash,
        "f24_parent_sha": q24,
        "f24_freeze_tree_identity": freeze_identity,
        "q24_evidence_identity": authorization.q24_evidence_identity,
        "r24_implementation_tree_identity": (
            authorization.r24_implementation_tree_identity
        ),
    }
    write_canonical_json(
        repository / M336I_FREEZE_MANIFEST_PATH,
        {**freeze_body, "manifest_hash": content_hash(freeze_body)},
    )
    f24 = _git_add_commit(repository, "F24")
    _run("git", "push", "-u", "origin", "exp/m336i-test", cwd=repository)
    external = tmp_path / "external"
    external.mkdir()
    request = M336IFinalAcquisitionRequest(
        repository=repository,
        supplied_f24_sha=f24,
        authorization=authorization,
        candidate_pool=frozen / "candidate_pool.json",
        acquisition_policy=frozen / "acquisition_policy.json",
        denylist=frozen / "denylist.json",
        authority_root=frozen / "authority_root.json",
        authority_statement=frozen / "authority.txt",
        frozen_route_registry=frozen / "route_registry.json",
        frozen_route_manifest=frozen / "route_manifest.json",
        selector_policy=frozen / "selector_policy.json",
        threshold_manifest=frozen / "threshold.json",
        publication_boundary_contract=frozen / "publication.json",
        public_artifact_contract=frozen / "public_contract.json",
        compiler_jdk_identities=frozen / "jdk.json",
        karina_host_identity_receipt=frozen / "karina_host.json",
        acquisition_ledger=external / "acquisition.jsonl",
        vault_destination=external / "vault",
        private_acquisition_output=external / "private",
        public_receipt_output=external / "acquisition-receipt.json",
        public_staging_root=external / "public-stage",
        unused_selected_source_output=external / "unused-selection",
        platform_role="WINDOWS",
    )
    return SimpleNamespace(
        request=request,
        authorization=authorization,
        repository=repository,
        remote=remote,
    )


def test_mutation_01_unresolved_final_acquisition_callable() -> None:
    registry = build_m336i_final_java_route_registry()
    components = list(registry.components)
    index = next(
        index
        for index, item in enumerate(components)
        if item.route_role == "FINAL_ACQUISITION_PROVIDER"
    )
    components[index] = _rehash_component(
        components[index], qualified_callable_name="missing_provider"
    )
    with pytest.raises(AttributeError):
        validate_m336i_route_registry(_rehash_registry(registry, components))


def test_mutation_02_refusal_guard_registered_as_provider() -> None:
    registry = build_m336i_final_java_route_registry()
    components = list(registry.components)
    index = next(
        index
        for index, item in enumerate(components)
        if item.route_role == "FINAL_ACQUISITION_PROVIDER"
    )
    refusal = refuse_m336h_unfrozen_final_acquisition
    components[index] = _rehash_component(
        components[index],
        python_module=refusal.__module__,
        qualified_callable_name=refusal.__name__,
        source_file_content_hash=bytes_hash(
            Path(inspect.getsourcefile(refusal)).read_bytes()
        ),
        callable_signature_hash=content_hash(str(inspect.signature(refusal))),
    )
    mutated = _rehash_registry(registry, components)
    validate_m336i_route_registry(mutated)
    with pytest.raises(ValueError, match="refusal guard"):
        build_m336i_final_java_route_manifest(mutated)


def test_mutation_03_missing_f24_authorization(tmp_path: Path) -> None:
    fixture = _provider_fixture(tmp_path)
    value = asdict(fixture.authorization)
    value.pop("f24_parent_sha")
    with pytest.raises(ValueError, match="fields changed"):
        final_acquisition_authorization_from_dict(value)
    assert not fixture.request.acquisition_ledger.exists()


@pytest.mark.parametrize(
    ("case", "change"),
    (
        ("wrong-q24-parent", {"f24_parent_sha": "0" * 40}),
        ("wrong-frozen-tree", {"f24_freeze_tree_identity": "0" * 64}),
        ("wrong-candidate-pool-hash", {"candidate_pool_hash": "0" * 64}),
        ("wrong-acquisition-policy-hash", {"acquisition_policy_hash": "0" * 64}),
    ),
)
def test_mutations_04_to_07_frozen_authority_fail_before_ledger(
    tmp_path: Path, case: str, change: dict
) -> None:
    fixture = _provider_fixture(tmp_path)
    authorization = _rehash_authorization(fixture.authorization, **change)
    request = replace(fixture.request, authorization=authorization)
    with pytest.raises(ValueError):
        run_m336i_frozen_final_acquisition(request)
    assert not request.acquisition_ledger.exists(), case


def test_mutation_08_dirty_f24_worktree(tmp_path: Path) -> None:
    fixture = _provider_fixture(tmp_path)
    (fixture.repository / "base.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact-F24"):
        run_m336i_frozen_final_acquisition(fixture.request)
    assert not fixture.request.acquisition_ledger.exists()


def test_mutation_09_remote_branch_differs_from_local_f24(tmp_path: Path) -> None:
    fixture = _provider_fixture(tmp_path)
    _run(
        "git",
        f"--git-dir={fixture.remote}",
        "update-ref",
        "-d",
        "refs/heads/exp/m336i-test",
    )
    with pytest.raises(subprocess.CalledProcessError):
        run_m336i_frozen_final_acquisition(fixture.request)
    assert not fixture.request.acquisition_ledger.exists()


def test_mutation_10_preexisting_reservation_blocks(tmp_path: Path) -> None:
    fixture = _provider_fixture(tmp_path)
    ledger = M336IFinalAcquisitionLedger(fixture.request.acquisition_ledger)
    for event in M336I_ACQUISITION_EVENTS[:2]:
        ledger.append(event, context_hash="a" * 64, operation_hash="b" * 64)
    with pytest.raises(FileExistsError):
        run_m336i_frozen_final_acquisition(fixture.request)
    assert ledger.receipt().acquisition_reservation_count == 1
    assert ledger.receipt().acquisition_start_count == 0


def test_mutation_11_repeated_acquisition_invocation_blocks(tmp_path: Path) -> None:
    fixture = _provider_fixture(tmp_path)
    ledger = M336IFinalAcquisitionLedger(fixture.request.acquisition_ledger)
    for event in M336I_ACQUISITION_EVENTS:
        ledger.append(event, context_hash="a" * 64, operation_hash="b" * 64)
    with pytest.raises(FileExistsError):
        run_m336i_frozen_final_acquisition(fixture.request)
    receipt = ledger.receipt()
    assert receipt.acquisition_completion_count == 1
    assert receipt.acquisition_rerun_count == 0


@pytest.mark.parametrize(
    ("boundary", "expected_events", "expected_reservations"),
    (
        ("AUTHORIZATION_VALIDATED", 1, 0),
        ("ACQUISITION_RESERVED", 2, 1),
        ("ACQUISITION_STARTED", 3, 1),
    ),
)
def test_mutations_12_and_13_crash_is_terminal_without_rerun(
    tmp_path: Path,
    boundary: str,
    expected_events: int,
    expected_reservations: int,
) -> None:
    fixture = _provider_fixture(tmp_path)
    with pytest.raises(M336IAcquisitionCrash):
        run_m336i_frozen_final_acquisition(fixture.request, crash_after=boundary)
    ledger = M336IFinalAcquisitionLedger(fixture.request.acquisition_ledger)
    before = ledger.receipt()
    assert before.event_count == expected_events
    assert before.acquisition_reservation_count == expected_reservations
    assert before.acquisition_rerun_count == 0
    with pytest.raises(FileExistsError):
        run_m336i_frozen_final_acquisition(fixture.request)
    assert ledger.receipt() == before


def test_crash_after_completed_acquisition_is_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai_brain.stage3.acquisition.m336i_acquisition as acquisition_module

    fixture = _provider_fixture(tmp_path)
    monkeypatch.setattr(
        acquisition_module,
        "run_fresh_acquisition_and_preflight",
        lambda **_kwargs: SimpleNamespace(status="PASS"),
    )
    monkeypatch.setattr(
        acquisition_module, "_write_private_preflight", lambda *_args: None
    )
    monkeypatch.setattr(
        acquisition_module,
        "_build_public_receipt",
        lambda *_args: SimpleNamespace(receipt_hash="c" * 64),
    )
    monkeypatch.setattr(acquisition_module, "write_canonical_json", lambda *_args: None)
    with pytest.raises(M336IAcquisitionCrash):
        run_m336i_frozen_final_acquisition(
            fixture.request, crash_after="ACQUISITION_COMPLETED"
        )
    ledger = M336IFinalAcquisitionLedger(fixture.request.acquisition_ledger)
    before = ledger.receipt()
    assert before.event_count == 4
    assert before.acquisition_completion_count == 1
    assert before.acquisition_rerun_count == 0
    with pytest.raises(FileExistsError):
        run_m336i_frozen_final_acquisition(fixture.request)
    assert ledger.receipt() == before


def test_rooted_scm_legal_inventory_path_is_not_prefixed_twice() -> None:
    root = "fixture-1111111111111111111111111111111111111111/"
    assert _legal_archive_entry_path(f"{root}LICENSE", root) == f"{root}LICENSE"
    assert _legal_archive_entry_path("LICENSE", root) == f"{root}LICENSE"


def test_mutation_14_route_state_skip(tmp_path: Path) -> None:
    ledger = M336IRouteStateLedger(tmp_path / "route.jsonl")
    with pytest.raises(ValueError, match="skipped"):
        ledger.advance(
            "PREFLIGHT_PASSED",
            context_hash="a" * 64,
            operation_receipt_hash="b" * 64,
        )
    assert ledger.events() == ()


def test_mutation_15_route_state_repetition(tmp_path: Path) -> None:
    ledger = M336IRouteStateLedger(tmp_path / "route.jsonl")
    ledger.advance("INITIAL", context_hash="a" * 64, operation_receipt_hash="b" * 64)
    with pytest.raises(ValueError, match="skipped or repeated"):
        ledger.advance(
            "INITIAL", context_hash="a" * 64, operation_receipt_hash="b" * 64
        )
    assert len(ledger.events()) == 1


def test_mutation_16_missing_semantic_evaluation_cli(tmp_path: Path) -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "scripts/m336h_prepare_independent_evaluation.py",
            "--output",
            str(tmp_path / "out.json"),
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert not (tmp_path / "out.json").exists()


def test_mutation_17_synthetic_perfect_metrics_are_rejected() -> None:
    import importlib.util

    path = Path("scripts/m336h_prepare_independent_evaluation.py").resolve()
    spec = importlib.util.spec_from_file_location("m336i_metric_guard", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="real semantic evaluation"):
        module._metrics(None)


def _evaluation_request(tmp_path: Path, *, copied_reference: bool):
    pack = tmp_path / "pack"
    pack.mkdir()
    separate = tmp_path / "separate"
    separate.mkdir()
    for name in (
        "route.json",
        "threshold.json",
        "windows-seal.json",
        "karina-seal.json",
        "windows-output.json",
        "karina-output.json",
        "windows-field-evidence.json",
        "karina-field-evidence.json",
        "windows-replay.json",
        "karina-replay.json",
        "pool.json",
        "qualification.json",
        "selected.json",
        "spdx.txt",
        "bindings.json",
    ):
        (separate / name).write_text("{}\n", encoding="utf-8")
    vault = separate / "vault"
    vault.mkdir()
    golden = (
        pack / "copied-goldens.json" if copied_reference else separate / "goldens.json"
    )
    golden.write_text("{}\n", encoding="utf-8")
    return M336IIndependentEvaluationRequest(
        route_manifest=separate / "route.json",
        threshold_manifest=separate / "threshold.json",
        windows_production_seal=separate / "windows-seal.json",
        karina_production_seal=separate / "karina-seal.json",
        windows_production_output=separate / "windows-output.json",
        karina_production_output=separate / "karina-output.json",
        windows_field_evidence_manifest=separate / "windows-field-evidence.json",
        karina_field_evidence_manifest=separate / "karina-field-evidence.json",
        public_candidate_pack=pack,
        windows_replay_receipt=separate / "windows-replay.json",
        karina_replay_receipt=separate / "karina-replay.json",
        independently_authored_semantic_goldens=golden,
        external_sealed_vault=vault,
        source_entry_bindings=separate / "bindings.json",
        candidate_pool=separate / "pool.json",
        qualification_report=separate / "qualification.json",
        selected_manifest=separate / "selected.json",
        frozen_spdx_reference=separate / "spdx.txt",
        evaluator_ledger=separate / "ledger.jsonl",
        git_worktrees=(),
    )


def test_mutation_18_evaluator_reference_copied_from_candidate_pack(
    tmp_path: Path,
) -> None:
    baseline = _evaluation_request(tmp_path, copied_reference=False)
    mutated = replace(
        baseline,
        independently_authored_semantic_goldens=baseline.public_candidate_pack
        / "copied-goldens.json",
    )
    mutated.independently_authored_semantic_goldens.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="copied"):
        run_m336i_independent_java_evaluation(mutated)
    assert not mutated.evaluator_ledger.exists()


def test_independent_metrics_count_extra_trusted_locations_as_wrong() -> None:
    semantics = SimpleNamespace(
        expected_claim_payload='{"value":1}', receiver_source_identity="alpha.A"
    )
    expected = SimpleNamespace(
        document_bytes_hash="a" * 64,
        source_unit_id="alpha/A.java",
        start_offset=0,
        end_offset=1,
        expected_supported=True,
        expected_semantics=semantics,
        canonical_source_signature="value():int",
        erased_jvm_descriptor="value()I",
    )
    rows = [
        {
            "document_bytes_hash": "a" * 64,
            "source_unit_id": "alpha/A.java",
            "start_offset": 0,
            "end_offset": 1,
            "production_trust_state": "trusted",
            "proposal_content": {"value": 1},
            "canonical_source_signature": "value():int",
            "erased_jvm_descriptor": "value()I",
            "receiver_type": "alpha.A",
        },
        {
            "document_bytes_hash": "b" * 64,
            "source_unit_id": "beta/B.java",
            "start_offset": 0,
            "end_offset": 1,
            "production_trust_state": "trusted",
        },
    ]
    metrics = _semantic_metrics(
        {"candidate_rows": rows}, SimpleNamespace(goldens=(expected,))
    )
    assert metrics["wrong_trusted_count"] == 1
    assert metrics["trust_precision"] == "0.500000"


def test_field_evidence_metrics_are_derived_from_manifest_and_goldens() -> None:
    raw = b"x"
    document_hash = bytes_hash(raw)
    declaration_hash = "d" * 64
    proposal_hash = "p" * 64
    content = {
        "accessibility": "PUBLIC",
        "declared_exceptions": [],
        "deprecated_since": None,
        "enclosing_type_accessibility": "PUBLIC",
        "examples": [],
        "first_bound_erasures": [],
        "generic_constraints": [],
        "intersection_bounds": [],
        "java_callable_kind": "METHOD",
        "method_type_parameters": [],
        "modifiers": ["public"],
        "module_name": None,
        "object_type": {"entity_type": None, "kind": "INTEGER", "quantity_type": None},
        "package_exported": True,
        "parameter_array_dimensions": [],
        "parameter_varargs": [],
        "parameters": [],
        "postconditions": [],
        "preconditions": [],
        "predicate_id": "value",
        "qualifier_ids": [],
        "receiver_type": "alpha.A",
        "resolved_declared_exceptions": [],
        "resolved_parameter_types": [],
        "resolved_return_type": "int",
        "return_array_dimensions": 0,
        "return_type": "int",
        "subject_type": {"entity_type_id": "alpha.A"},
    }
    row = {
        "proposal_id": "proposal-1",
        "proposal_hash": proposal_hash,
        "document_bytes_hash": document_hash,
        "source_unit_id": "alpha/A.java",
        "start_offset": 0,
        "end_offset": 1,
        "member_kind": "method",
        "member_name": "value",
        "declaration_hash": declaration_hash,
        "production_trust_state": "trusted",
        "production_supported": True,
        "proposal_content": content,
        "canonical_source_signature": "value():int",
        "erased_jvm_descriptor": "value()I",
        "receiver_type": "alpha.A",
    }
    document_id = "m336-final-java.document.example"
    node_key = {
        "document": document_id,
        "snapshot": document_hash,
        "start": 0,
        "end": 1,
        "kind": "method",
        "name": "value",
    }
    evidence = {
        "proposal_id": "proposal-1",
        "proposal_hash": proposal_hash,
        "field_path": "content.predicate_id",
        "document_id": document_id,
        "document_bytes_hash": document_hash,
        "source_location": {"byte_start": 0, "byte_end": 1},
        "source_span_hash": document_hash,
        "parser_node_id": f"java-node.{content_hash(node_key)[:32]}",
        "semantic_identity_hash": declaration_hash,
        "normalized_output": canonical_json("value"),
    }
    semantics = SimpleNamespace(
        expected_claim_payload=canonical_json(content),
        expected_knowledge_kind="CLAIM_SCHEMA",
        expected_epistemic_character="NORMATIVE",
        receiver_source_identity="alpha.A",
    )
    golden = SimpleNamespace(
        document_bytes_hash=document_hash,
        source_unit_id="alpha/A.java",
        start_offset=0,
        end_offset=1,
        expected_supported=True,
        expected_semantics=semantics,
    )
    metrics = _field_evidence_metrics(
        {"candidate_rows": [row]},
        SimpleNamespace(goldens=(golden,)),
        {"evidence": [evidence]},
        {"alpha/A.java": raw},
    )
    assert metrics["field_evidence_present_count"] == 1
    assert metrics["field_evidence_exact_count"] == 1
    assert metrics["field_evidence_missing_count"] > 0
    mutated = {**evidence, "normalized_output": canonical_json("wrong")}
    failed = _field_evidence_metrics(
        {"candidate_rows": [row]},
        SimpleNamespace(goldens=(golden,)),
        {"evidence": [mutated]},
        {"alpha/A.java": raw},
    )
    assert failed["field_evidence_exact_count"] == 0
    assert failed["field_evidence_wrong_count"] == 1


def test_spdx_evaluator_checks_every_selected_file_and_frozen_bytes(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "spdx"
    shutil.copytree(SPDX_SNAPSHOT_ROOT, reference)
    policy_body = {
        "family_id": "alpha",
        "pom_license_declarations": [["Apache-2.0", "Apache", "a" * 64]],
    }
    pool_body = {
        "schema_version": 1,
        "candidates": [{**policy_body, "policy_hash": content_hash(policy_body)}],
    }
    pool = {**pool_body, "pool_hash": content_hash(pool_body)}
    decision_body = {
        "family_id": "alpha",
        "scoped_license_decision": "RESOLVED",
        "scoped_license_expressions": ["Apache-2.0"],
    }
    qualification_body = {
        "schema_version": 1,
        "decisions": [{**decision_body, "decision_hash": content_hash(decision_body)}],
    }
    qualification = {
        **qualification_body,
        "report_hash": content_hash(qualification_body),
    }
    selected = {
        "files": [
            {"candidate_root": "alpha", "canonical_path": f"A{index}.java"}
            for index in range(2)
        ]
    }
    metrics = _spdx_metrics(pool, qualification, selected, reference / "snapshot.json")
    assert metrics["spdx_expected_count"] == 2
    assert metrics["spdx_agreement"] == "1.000000"
    (reference / "Apache-2.0.txt").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="reference bytes changed"):
        _spdx_metrics(pool, qualification, selected, reference / "snapshot.json")


def test_readiness_rejects_claim_only_quality_receipt(tmp_path: Path) -> None:
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336I_QUALITY_RECEIPT",
        "platform_role": "WINDOWS",
        "exact_sha": "a" * 40,
        "checks": [],
        "check_count": 0,
        "status": "PASS",
    }
    path = tmp_path / "quality.json"
    write_canonical_json(path, {**body, "receipt_hash": content_hash(body)})
    with pytest.raises(ValueError, match="quality evidence failed"):
        verify_m336i_quality_receipt(path, "WINDOWS", "a" * 40)


def _production_authority_fixture(tmp_path: Path):
    platform_name = "windows" if os.name == "nt" else "karina"
    platform_role = platform_name.upper()
    java_name = "java.exe" if os.name == "nt" else "java"
    candidates = [Path(shutil.which("javac") or "")]
    if os.name == "nt":
        candidates.append(
            Path("W:/toolbox_IDEA/programs/IdeaProjects/.jdks/ms-21.0.11/bin/javac.exe")
        )
    public = None
    javac = candidates[0]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            _private, public = verify_m336_jdk_provider_evidence(
                platform=platform_name,
                java=candidate.with_name(java_name),
                javac=candidate,
            )
        except ValueError:
            continue
        javac = candidate
        break
    if public is None:
        pytest.skip("exact frozen JDK required for M336I production authority test")
    route = _hashed(
        tmp_path / "route.json", "manifest_hash", schema_version=1, route="test"
    )
    threshold = _hashed(
        tmp_path / "threshold.json",
        "threshold_manifest_hash",
        schema_version=1,
        minimum_metrics={},
    )
    source = tmp_path / "source"
    vault = tmp_path / "vault"
    source.mkdir()
    vault.mkdir()
    handles = {}
    for name in ("bindings", "selected", "selector", "closure", "proof"):
        path = tmp_path / f"{name}.json"
        path.write_text("{}\n", encoding="utf-8")
        handles[name] = path
    base = M336HCompilerAwareProductionRequest(
        route_manifest_hash=route["manifest_hash"],
        implementation_identity="a" * 64,
        platform_role=platform_role,
        source_snapshot_private_handle=source,
        javac_private_handle=javac,
        public_jdk_identity_receipt_hash=public.receipt_hash,
        source_entry_bindings=handles["bindings"],
        selected_manifest=handles["selected"],
        selector_receipt=handles["selector"],
        closure_manifest=handles["closure"],
        closure_feasibility_proof=handles["proof"],
        sealed_vault=vault,
        private_replay_root=tmp_path / "private-replay",
        public_production_destination=tmp_path / "production",
        publication_boundary_contract_hash="b" * 64,
        threshold_manifest_hash=threshold["threshold_manifest_hash"],
    )
    return M336ICompilerAwareProductionRequest(
        production_request=base,
        frozen_route_manifest=tmp_path / "route.json",
        frozen_implementation_identity="a" * 64,
        frozen_publication_boundary_hash="b" * 64,
        frozen_threshold_manifest=tmp_path / "threshold.json",
        public_staging_root=tmp_path / "staging",
        git_worktrees=(),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (("route_manifest_hash", "0" * 64), ("implementation_identity", "0" * 64)),
)
def test_mutations_19_and_20_production_frozen_authority(
    tmp_path: Path, field: str, value: str
) -> None:
    baseline = _production_authority_fixture(tmp_path)
    validate_m336i_production_authority(baseline)
    mutated = replace(
        baseline,
        production_request=replace(baseline.production_request, **{field: value}),
    )
    with pytest.raises(ValueError, match="frozen authority"):
        validate_m336i_production_authority(mutated)
    assert not baseline.production_request.public_production_destination.exists()


def _response() -> M336HCompilerAwareProductionResponse:
    body = {
        "schema_version": 1,
        "request_hash": "0" * 64,
        "request_schema_hash": "1" * 64,
        "response_schema_hash": "2" * 64,
        "route_manifest_hash": "3" * 64,
        "implementation_identity": "4" * 64,
        "platform_role": "WINDOWS",
        "compiler_aware_mode": True,
        "selected_manifest_hash": "5" * 64,
        "binding_manifest_hash": "6" * 64,
        "closure_manifest_hash": "7" * 64,
        "feasibility_proof_hash": "8" * 64,
        "compiler_identity_hash": "9" * 64,
        "compiler_report_hash": "a" * 64,
        "production_output_hash": "b" * 64,
        "production_batch_hash": "c" * 64,
        "candidate_pack_hash": "d" * 64,
        "candidate_pack_tree_hash": "e" * 64,
        "public_replay_commitment_hash": "f" * 64,
        "sealed_source_replay_receipt_hash": "0" * 64,
        "proposal_count": 1,
        "trusted_count": 1,
        "withheld_count": 0,
        "compiler_blocked_declaration_count": 0,
        "trusted_compiler_blocked_target_count": 0,
        "post_trust_pack_failures": 0,
        "status": "PASS",
    }
    return M336HCompilerAwareProductionResponse(
        **body, response_hash=content_hash(body)
    )


def _seal_root(tmp_path: Path) -> Path:
    root = tmp_path / "seal-root"
    root.mkdir()
    write_canonical_json(
        root / "production_counts.json",
        {
            "proposal_count": 1,
            "trusted_count": 1,
            "withheld_count": 0,
            "trusted_compiler_blocked_target_count": 0,
            "post_trust_pack_failures": 0,
        },
    )
    write_canonical_json(
        root / "production_output.json",
        {
            "candidate_rows": [
                {"proposal_id": "proposal-1", "production_trust_state": "trusted"}
            ]
        },
    )
    _write_authorizations(root, "proposal-1")
    write_canonical_json(
        root / "public_pack_integrity_receipt.json",
        {
            "status": "PASS",
            "source_bearing_entry_count": 0,
            "private_role_entry_count": 0,
            "unknown_entry_count": 0,
            "absolute_path_count": 0,
            "reversible_source_payload_count": 0,
        },
    )
    write_canonical_json(
        root / "sealed_source_replay_receipt.json",
        {"status": "PASS", "reconstructed_pack_byte_difference_count": 0},
    )
    write_canonical_json(root / "production_process_audit.json", {"socket_attempts": 0})
    write_canonical_json(
        root / "production_summary.json", {"production_golden_read_count": 0}
    )
    return root


def _write_authorizations(root: Path, proposal_id: str | None) -> None:
    rows = (
        []
        if proposal_id is None
        else [
            {
                "trusted_proposal_id": proposal_id,
                "trusted_proposal_hash": "a" * 64,
                "authorization_hash": "b" * 64,
            }
        ]
    )
    body = {
        "schema_version": 1,
        "authorization_count": len(rows),
        "authorizations": rows,
    }
    write_canonical_json(
        root / "production_authorization_manifest.json",
        {**body, "manifest_hash": content_hash(body)},
    )


def test_mutation_21_tautological_authorization_count_rejected(tmp_path: Path) -> None:
    root = _seal_root(tmp_path)
    assert (
        build_m336i_production_seal(production_root=root, response=_response()).status
        == "PASS"
    )
    _write_authorizations(root, None)
    with pytest.raises(ValueError, match="seal failed"):
        build_m336i_production_seal(production_root=root, response=_response())


def test_mutation_22_trusted_authorized_identity_mismatch_rejected(
    tmp_path: Path,
) -> None:
    root = _seal_root(tmp_path)
    assert (
        build_m336i_production_seal(production_root=root, response=_response()).status
        == "PASS"
    )
    _write_authorizations(root, "different-proposal")
    with pytest.raises(ValueError, match="seal failed"):
        build_m336i_production_seal(production_root=root, response=_response())


def test_mutation_23_evaluator_before_both_production_seals(tmp_path: Path) -> None:
    request = _evaluation_request(tmp_path, copied_reference=False)
    request.karina_production_seal.unlink()
    with pytest.raises(ValueError, match="input is missing"):
        run_m336i_independent_java_evaluation(request)
    assert not request.evaluator_ledger.exists()


def test_mutation_24_public_source_body_rejected() -> None:
    with pytest.raises(ValueError):
        _reject_private_payload({"nested": {"source_body": "class Secret {}"}})


def test_mutation_25_public_absolute_path_rejected() -> None:
    with pytest.raises(ValueError):
        _reject_private_payload({"message": r"C:\private\vault\Secret.java"})


def _public_pack(tmp_path: Path):
    vault = tmp_path / "vault"
    source = vault / "candidates/demo/sources/demo/A.java"
    source.parent.mkdir(parents=True)
    raw = b"package demo; public class A { public int get(int v) { return v; } }\n"
    source.write_bytes(raw)
    source_root = tmp_path / "selected"
    selected = source_root / "demo/demo/A.java"
    selected.parent.mkdir(parents=True)
    selected.write_bytes(raw)
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        (selected,),
        bundle_id="m336-final-java",
        domain_tags=("java-api",),
        imported_at="1970-01-01T00:00:00Z",
        source_root=source_root,
        store=store,
    )
    identity = build_source_entry_id(
        candidate_family_id="demo",
        source_jar_sha256="1" * 64,
        archive_relative_path="demo/A.java",
        raw_source_sha256=bundle.documents[0].bytes_hash,
        canonical_source_sha256=bundle.documents[0].canonical_text_hash,
    )
    binding = build_source_entry_binding(
        source_entry_id=identity,
        archive_path="demo/A.java",
        scm_path="src/demo/A.java",
        vault_path="candidates/demo/sources/demo/A.java",
        selected_path="demo/demo/A.java",
        production_document_identity=bundle.documents[0].document_id,
    )
    batch = run_java_acquisition_pipeline(
        bundle, store, deterministic_run_id="m336i.test"
    )
    authorizations = verify_java_production_batch(batch, store)
    by_id = {item.trusted_proposal_id: item for item in authorizations}
    proposals = []
    approvals = []
    for proposal in batch.trusted_proposals:
        approved, _review, approval = review_proposal(
            proposal,
            reviewer_identity="m336i-test-process",
            reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
            decision=ReviewDecision.APPROVE,
            rationale="source-free M336I staging mutation",
            timestamp="1970-01-01T00:00:00Z",
            trust_authorization=by_id[proposal.proposal_id],
        )
        proposals.append(approved)
        approvals.append(approval)
    pack_root = tmp_path / "pack"
    compile_provisional_pack(
        bundle,
        batch.segmentation.segments,
        tuple(proposals),
        tuple(approvals),
        pack_root,
        domain_id="m336-final-java",
        production_trust_batch=batch,
        production_authorizations=authorizations,
        java_source_entry_bindings=(binding,),
        store=store,
    )
    return vault, pack_root


def test_mutation_26_staging_mutation_after_scan_is_rejected(tmp_path: Path) -> None:
    vault, pack = _public_pack(tmp_path)
    staging = tmp_path / "staging"
    candidate = staging / "candidate-pack"
    installed = staging / "installed-pack"
    shutil.copytree(pack, candidate)
    shutil.copytree(pack, installed)
    roles = {
        path.relative_to(
            staging
        ).as_posix(): ArtifactConfidentialityRole.PUBLIC_DERIVED_PACK
        for path in staging.rglob("*")
        if path.is_file()
    }
    rows = tuple(
        (
            path.relative_to(staging).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in staging.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(staging).as_posix().encode(),
        )
    )
    validate_public_staging(
        staging_root=staging,
        artifact_roles=roles,
        sealed_vault_root=vault,
        candidate_pack_relative_path="candidate-pack",
        installed_pack_relative_path="installed-pack",
        prospective_git_tree_hash=content_hash(rows),
        prospective_git_entries=rows,
    )
    mutated_rows = (*rows[:-1], (rows[-1][0], rows[-1][1], "0" * 64))
    with pytest.raises(ValueError, match="changed after"):
        validate_public_staging(
            staging_root=staging,
            artifact_roles=roles,
            sealed_vault_root=vault,
            candidate_pack_relative_path="candidate-pack",
            installed_pack_relative_path="installed-pack",
            prospective_git_tree_hash=content_hash(mutated_rows),
            prospective_git_entries=mutated_rows,
        )
