"""Qualify the M-33.6j.3 F26/H26/E26 protocol in disposable state only."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from m336i_build_authorized_rehearsal_fixture import (
    _acquire_fixture,
    _FixtureMaven,
    _FixtureScm,
)
from m336i_java_final_route import _final
from m336j_build_f26 import (
    _expected_authorization_values,
    materialize_m336j_f26_prospective_tree,
)

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336f_selection import M336FSelectorLedger
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336i_acquisition import (
    M336I_FINAL_ACQUISITION_RUN_ID,
    M336IFinalAcquisitionLedger,
)
from ai_brain.stage3.acquisition.m336j_evaluator_v2 import (
    M336J3_EVALUATOR_EVENTS,
    M336JEvaluatorLedgerV2,
)
from ai_brain.stage3.acquisition.m336j_execution import (
    dependency_manifest_from_dict,
    public_execution_capsule_receipt_from_dict,
)
from ai_brain.stage3.acquisition.m336j_final_v2 import (
    M336J3_BRANCH_NAME,
    M336J3_BRANCH_REF,
    M336J3_E26_SUBJECT,
    M336J3_EXACT_Q25_SHA,
    M336J3_F26_SUBJECT,
    M336J3_FREEZE_ROOT,
    M336J3_H26_SUBJECT,
    M336J3_Q26_SUBJECT,
    M336J3_R26_SUBJECT,
    build_m336j_f26_frozen_file_manifest,
    build_m336j_final_freeze_lineage_policy_v2,
    build_m336j_git_executable_receipt_v2,
    compute_m336j_freeze_tree_identity_v2,
    compute_m336j_q26_staging_tree_hash,
    dump_m336j_f26_frozen_file_manifest,
    resolve_m336j_f26_frozen_sources,
    verify_m336j_final_freeze_lineage_v2,
)
from ai_brain.stage3.acquisition.m336j_publication_v2 import (
    verify_m336j_h26_e26_commit_protocol,
)

_PREPARE_FIELDS = {
    "source_repository",
    "git_executable",
    "exact_r26_sha",
    "readiness",
    "public_capsule_receipt",
    "python_environment_manifest",
    "executable_dependency_manifest",
    "spdx_binding",
    "output",
}
_COMPLETE_FIELDS = {
    "prepared_state",
    "private_execution_capsule",
    "ssh_executable",
    "ssh_key",
    "known_hosts_file",
    "karina_worker_endpoint",
    "karina_repository",
    "karina_private_root",
    "karina_private_capsule_remote",
    "karina_javac",
    "windows_javac",
    "frozen_spdx_reference",
}


def _run(git: Path, repository: Path | None, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _commit(git: Path, repository: Path, subject: str) -> str:
    _run(git, repository, "add", "-A")
    _run(git, repository, "commit", "-m", subject)
    return _run(git, repository, "rev-parse", "HEAD^{commit}")


def _object(path: Path) -> dict:
    value = strict_json_file(path.resolve(strict=True))
    if not isinstance(value, dict):
        raise TypeError("M336J3 qualification input must be an object")
    return value


def _write_authorization_input(
    *,
    path: Path,
    expected: dict,
    q26: str,
    r26: str,
    acquisition_policy: Path,
) -> dict:
    policy = _object(acquisition_policy)
    value = {
        "acquisition_mode": "REHEARSAL",
        "exact_q26_sha": q26,
        "exact_r26_sha": r26,
        **expected,
        "acquisition_run_id": M336I_FINAL_ACQUISITION_RUN_ID,
        "branch_ref": M336J3_BRANCH_REF,
        "allowed_network_hosts": policy["allowed_network_hosts"],
        "expected_global_acquisition_count": 1,
        "expected_windows_acquisition_count": 1,
        "expected_karina_acquisition_count": 0,
    }
    write_canonical_json(path, value)
    return value


def prepare(request_path: Path) -> dict:
    request = _object(request_path)
    if set(request) != _PREPARE_FIELDS or any(
        not isinstance(value, str) for value in request.values()
    ):
        raise ValueError("M336J3 disposable prepare request fields changed")
    source = Path(request["source_repository"]).resolve(strict=True)
    git = Path(request["git_executable"]).resolve(strict=True)
    r26 = request["exact_r26_sha"]
    output = Path(request["output"]).resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336J3 disposable qualification output must be fresh")
    output.mkdir(parents=True)
    remote = output / "origin.git"
    repository = output / "repository"
    private = output / "private"
    public = output / "public"
    private.mkdir()
    public.mkdir()
    _run(git, None, "init", "--bare", str(remote))
    _run(git, None, "clone", "--no-local", str(source), str(repository))
    _run(git, repository, "config", "user.email", "m336j3@example.invalid")
    _run(git, repository, "config", "user.name", "M336J3 Qualification")
    _run(git, repository, "remote", "set-url", "origin", str(remote))
    _run(git, repository, "checkout", "--detach", r26)
    _run(git, repository, "checkout", "-B", M336J3_BRANCH_NAME, r26)
    if (
        _run(git, repository, "rev-parse", f"{r26}^{{commit}}^") != M336J3_EXACT_Q25_SHA
        or _run(git, repository, "show", "-s", "--format=%s", r26) != M336J3_R26_SUBJECT
        or _run(git, repository, "status", "--porcelain=v1")
    ):
        raise ValueError("M336J3 disposable protocol did not start at exact R26")
    anchor = repository / "artifacts" / "m336j3" / "disposable"
    anchor.mkdir(parents=True)
    q26_body = {
        "schema_version": 2,
        "contract_role": "M336J3_DISPOSABLE_Q26_ANCHOR",
        "exact_r26_sha": r26,
        "final_real_one_shot_ledger_write_count": 0,
        "new_final_source_body_bytes": 0,
        "status": "QUALIFICATION_ONLY",
    }
    write_canonical_json(
        anchor / "q26_anchor.json",
        {**q26_body, "receipt_hash": content_hash(q26_body)},
    )
    _run(git, repository, "add", "-f", "artifacts/m336j3/disposable/q26_anchor.json")
    q26 = _commit(git, repository, M336J3_Q26_SUBJECT)
    _run(git, repository, "push", "-u", "origin", M336J3_BRANCH_NAME)
    staging_hash = compute_m336j_q26_staging_tree_hash(
        repository,
        git,
        exact_r26_sha=r26,
        exact_q26_sha=q26,
    )
    readiness = Path(request["readiness"]).resolve(strict=True)
    public_capsule_path = Path(request["public_capsule_receipt"]).resolve(strict=True)
    python_environment_path = Path(request["python_environment_manifest"]).resolve(
        strict=True
    )
    dependencies_path = Path(request["executable_dependency_manifest"]).resolve(
        strict=True
    )
    spdx_path = Path(request["spdx_binding"]).resolve(strict=True)
    frozen_files = build_m336j_f26_frozen_file_manifest(
        repository,
        acquisition_mode="REHEARSAL",
        readiness=readiness,
        public_capsule_receipt=public_capsule_path,
        python_environment_manifest=python_environment_path,
        executable_dependency_manifest=dependencies_path,
        spdx_binding=spdx_path,
    )
    frozen_manifest_path = private / "frozen_file_manifest_v2.json"
    frozen_manifest_path.write_bytes(dump_m336j_f26_frozen_file_manifest(frozen_files))
    capsule = public_execution_capsule_receipt_from_dict(_object(public_capsule_path))
    dependencies = dependency_manifest_from_dict(_object(dependencies_path))
    sources = resolve_m336j_f26_frozen_sources(
        repository,
        acquisition_mode="REHEARSAL",
        readiness=readiness,
        public_capsule_receipt=public_capsule_path,
        python_environment_manifest=python_environment_path,
        executable_dependency_manifest=dependencies_path,
        spdx_binding=spdx_path,
    )
    prospective, registry, route = materialize_m336j_f26_prospective_tree(
        repository=repository,
        frozen_files=frozen_files,
        frozen_sources=sources,
        capsule=capsule,
        dependencies=dependencies,
    )
    freeze_identity = compute_m336j_freeze_tree_identity_v2(repository, git)
    python_environment = _object(python_environment_path)
    spdx = _object(spdx_path)
    expected = _expected_authorization_values(
        output=prospective,
        q26=q26,
        r26=r26,
        staging_hash=staging_hash,
        freeze_identity=freeze_identity,
        capsule=capsule,
        dependencies=dependencies,
        python_environment=python_environment,
        spdx_binding=spdx,
        registry=registry,
        route=route,
    )
    authorization_input_path = private / "authorization_input_v2.json"
    _write_authorization_input(
        path=authorization_input_path,
        expected=expected,
        q26=q26,
        r26=r26,
        acquisition_policy=prospective / "acquisition_policy.json",
    )
    if prospective != repository / M336J3_FREEZE_ROOT:
        raise ValueError("M336J3 prospective freeze cleanup target changed")
    shutil.rmtree(prospective)
    builder_request = {
        "repository": str(repository),
        "git_executable": str(git),
        "exact_q26_sha": q26,
        "exact_r26_sha": r26,
        "q26_staging_tree_hash": staging_hash,
        "readiness": str(readiness),
        "public_capsule_receipt": str(public_capsule_path),
        "python_environment_manifest": str(python_environment_path),
        "executable_dependency_manifest": str(dependencies_path),
        "spdx_binding": str(spdx_path),
        "authorization_input": str(authorization_input_path),
        "frozen_file_manifest": str(frozen_manifest_path),
    }
    builder_request_path = private / "f26_builder_request.json"
    write_canonical_json(builder_request_path, builder_request)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository / "src")
    result = subprocess.run(
        (
            sys.executable,
            "-B",
            str(repository / "scripts" / "m336j_build_f26.py"),
            "--request",
            str(builder_request_path),
        ),
        cwd=repository,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    builder_receipt = json.loads(result.stdout)
    write_canonical_json(
        public / "disposable_f26_builder_receipt.json", builder_receipt
    )
    _run(
        git,
        repository,
        "add",
        "-f",
        M336J3_FREEZE_ROOT.as_posix(),
    )
    f26 = _commit(git, repository, M336J3_F26_SUBJECT)
    _run(git, repository, "push", "origin", M336J3_BRANCH_NAME)
    git_receipt = build_m336j_git_executable_receipt_v2(
        git,
        execution_capsule_public_receipt_hash=capsule.receipt_hash,
        environment_identity_hash=python_environment["environment_manifest_hash"],
    )
    lineage_policy = build_m336j_final_freeze_lineage_policy_v2(
        exact_r26_sha=r26,
        exact_q26_sha=q26,
        exact_f26_sha=f26,
    )
    lineage = verify_m336j_final_freeze_lineage_v2(
        repository,
        git,
        lineage_policy,
        git_receipt,
    )
    write_canonical_json(
        public / "disposable_f26_lineage_receipt.json",
        asdict(lineage),
    )
    state = {
        "repository": str(repository),
        "git_executable": str(git),
        "exact_r26_sha": r26,
        "exact_q26_sha": q26,
        "exact_f26_sha": f26,
        "private_root": str(private),
        "public_root": str(public),
        "public_capsule_receipt": str(public_capsule_path),
        "python_environment_manifest": str(python_environment_path),
        "executable_dependency_manifest": str(dependencies_path),
        "spdx_binding": str(spdx_path),
    }
    write_canonical_json(private / "prepared_state.json", state)
    body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336J3_DISPOSABLE_PREPARE_RECEIPT",
        "exact_r26_sha": r26,
        "q26_like_sha": q26,
        "f26_like_sha": f26,
        "q26_staging_tree_hash": staging_hash,
        "freeze_tree_identity": freeze_identity,
        "authorization_schema_version": 2,
        "freeze_manifest_schema_version": 2,
        "frozen_file_count": frozen_files.file_count,
        "git_executable_receipt_hash": git_receipt.receipt_hash,
        "lineage_policy_hash": lineage_policy.policy_hash,
        "lineage_receipt_hash": lineage.receipt_hash,
        "bare_git_lookup_count": git_receipt.bare_executable_lookup_count,
        "final_real_one_shot_ledger_write_count": 0,
        "new_final_source_body_bytes": 0,
        "status": "F26_DISPOSABLE_PREPARED",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    write_canonical_json(public / "disposable_prepare_receipt.json", receipt)
    print(canonical_json(receipt))
    return receipt


def _invoke_publication_script(
    *,
    repository: Path,
    private_root: Path,
    script_name: str,
    request_name: str,
    request: dict,
) -> dict:
    request_path = private_root / request_name
    write_canonical_json(request_path, request)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository / "src")
    result = subprocess.run(
        (
            sys.executable,
            "-B",
            str(repository / "scripts" / script_name),
            "--request",
            str(request_path),
        ),
        cwd=repository,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise TypeError("M336J3 publisher did not return an object")
    return value


def _run_disposable_h26_quality(repository: Path) -> dict:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository / "src")
    result = subprocess.run(
        (
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "tests/test_m336j3_final_handshake.py",
        ),
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise ValueError("M336J3 disposable H26 targeted quality failed")
    body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336J3_DISPOSABLE_H26_QUALITY",
        "command_hash": content_hash(
            (
                "python",
                "-B",
                "-m",
                "pytest",
                "-q",
                "tests/test_m336j3_final_handshake.py",
            )
        ),
        "stdout_hash": content_hash(result.stdout),
        "stderr_hash": content_hash(result.stderr),
        "exit_code": result.returncode,
        "status": "PASS",
    }
    return {**body, "receipt_hash": content_hash(body)}


def complete(request_path: Path) -> dict:
    request = _object(request_path)
    if set(request) != _COMPLETE_FIELDS or any(
        not isinstance(value, str) for value in request.values()
    ):
        raise ValueError("M336J3 disposable complete request fields changed")
    state = _object(Path(request["prepared_state"]))
    expected_state_fields = {
        "repository",
        "git_executable",
        "exact_r26_sha",
        "exact_q26_sha",
        "exact_f26_sha",
        "private_root",
        "public_root",
        "public_capsule_receipt",
        "python_environment_manifest",
        "executable_dependency_manifest",
        "spdx_binding",
    }
    if set(state) != expected_state_fields:
        raise ValueError("M336J3 disposable prepared state fields changed")
    repository = Path(state["repository"]).resolve(strict=True)
    git = Path(state["git_executable"]).resolve(strict=True)
    private = Path(state["private_root"]).resolve(strict=True)
    public = Path(state["public_root"]).resolve(strict=True)
    f26 = state["exact_f26_sha"]
    freeze = repository / M336J3_FREEZE_ROOT
    runtime = private / "runtime"
    args = SimpleNamespace(
        repository=repository,
        supplied_f24_sha=f26,
        frozen_authorization=freeze / "final_authorization_v2.json",
        candidate_pool=freeze / "candidate_pool.json",
        acquisition_policy=freeze / "acquisition_policy.json",
        denylist=freeze / "denylist.json",
        authority_root=freeze / "authority_root.json",
        authority_statement=freeze / "authority_statement.txt",
        frozen_route_registry=freeze / "route_component_registry.json",
        frozen_route_manifest=freeze / "route_manifest.json",
        selector_policy=freeze / "selector_policy.json",
        threshold_manifest=freeze / "threshold_manifest.json",
        publication_boundary_contract=freeze / "publication_boundary_contract.json",
        public_artifact_contract=freeze / "public_artifact_contract.json",
        compiler_jdk_identities=freeze / "compiler_jdk_identities.json",
        karina_host_identity_receipt=freeze / "karina_host_identity_receipt.json",
        frozen_spdx_reference=Path(request["frozen_spdx_reference"]).resolve(
            strict=True
        ),
        acquisition_ledger=runtime / "ledgers" / "acquisition.jsonl",
        route_state_ledger=runtime / "ledgers" / "route.jsonl",
        windows_vault=runtime / "windows-vault",
        private_acquisition_output=runtime / "acquisition",
        public_acquisition_receipt=runtime / "public-acquisition.json",
        selector_ledger=runtime / "ledgers" / "selector.jsonl",
        evaluator_ledger=runtime / "ledgers" / "evaluator.jsonl",
        windows_selected_snapshot=runtime / "windows-selected",
        windows_private_replay_root=runtime / "windows-replay",
        windows_public_production_root=runtime / "windows-production",
        karina_public_production_root=runtime / "karina-production",
        independent_evaluator_root=runtime / "evaluator",
        public_staging_root=runtime / "public-staging",
        windows_javac=Path(request["windows_javac"]).resolve(strict=True),
        git_executable=git,
        ssh_key=Path(request["ssh_key"]).resolve(strict=True),
        ssh_executable=Path(request["ssh_executable"]).resolve(strict=True),
        known_hosts_file=Path(request["known_hosts_file"]).resolve(strict=True),
        karina_command_receipt_root=runtime / "command-receipts",
        karina_host_preflight_receipt=runtime / "post-f26-host-preflight.json",
        karina_storage_preflight_receipt=runtime / "post-f26-storage-preflight.json",
        final_receipt=runtime / "final-route-receipt.json",
        karina_private_capsule=Path(request["private_execution_capsule"]).resolve(
            strict=True
        ),
        karina_public_capsule_receipt=freeze
        / "q25"
        / "public_execution_capsule_receipt.json",
        karina_executable_dependency_manifest=freeze
        / "q25"
        / "executable_dependency_manifest.json",
        karina_worker_endpoint=request["karina_worker_endpoint"],
        karina_repository=request["karina_repository"],
        karina_private_root=request["karina_private_root"],
        karina_private_capsule_remote=request["karina_private_capsule_remote"],
        karina_javac=request["karina_javac"],
    )
    provider = SimpleNamespace(
        maven_provider=_FixtureMaven(),
        scm_provider=_FixtureScm(),
        acquire_one=_acquire_fixture,
    )
    _final(args, rehearsal_acquisition_provider=provider)
    final_route = _object(args.final_receipt)
    acquisition = M336IFinalAcquisitionLedger(
        args.acquisition_ledger, git_worktrees=(repository,)
    ).receipt()
    selector = M336FSelectorLedger(
        args.selector_ledger, git_worktrees=(repository,)
    ).receipt()
    evaluator_events = M336JEvaluatorLedgerV2(
        args.evaluator_ledger, git_worktrees=(repository,)
    ).events()
    if (
        final_route.get("status") != "OUTCOME A"
        or acquisition.acquisition_reservation_count != 1
        or acquisition.acquisition_start_count != 1
        or acquisition.acquisition_rerun_count != 0
        or selector["selector_reservation_count"] != 1
        or selector["selector_invocation_count"] != 1
        or tuple(item.event for item in evaluator_events) != M336J3_EVALUATOR_EVENTS
    ):
        raise ValueError("M336J3 disposable final controller did not close once")
    h_output = repository / "artifacts" / "m336j3" / "h26-production"
    h_report = _invoke_publication_script(
        repository=repository,
        private_root=private,
        script_name="m336j_publish_h26.py",
        request_name="h26-publisher-request.json",
        request={
            "repository": str(repository),
            "git_executable": str(git),
            "exact_f26_sha": f26,
            "freeze_manifest": str(freeze / "freeze_manifest_v2.json"),
            "production_source": str(args.windows_public_production_root),
            "output": str(h_output),
        },
    )
    _run(git, repository, "add", "-f", "artifacts/m336j3/h26-production")
    h26 = _commit(
        git,
        repository,
        M336J3_H26_SUBJECT,
    )
    _run(git, repository, "push", "origin", M336J3_BRANCH_NAME)
    h_quality = _run_disposable_h26_quality(repository)
    write_canonical_json(public / "disposable_h26_quality.json", h_quality)
    evidence_source = public / "e26-source"
    evidence_source.mkdir()
    evaluation = _object(
        args.windows_public_production_root / "m336i_independent_evaluation.json"
    )
    evidence_body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336J3_DISPOSABLE_E26_EVIDENCE",
        "final_route_receipt_hash": final_route["receipt_hash"],
        "acquisition_receipt_hash": final_route["acquisition_receipt_hash"],
        "selector_receipt_hash": final_route["selector_receipt_hash"],
        "windows_production_seal_hash": final_route["windows_production_seal_hash"],
        "karina_production_seal_hash": final_route["karina_production_seal_hash"],
        "independent_evaluation_hash": evaluation["result_hash"],
        "evaluator_event_hashes": [item.event_hash for item in evaluator_events],
        "evaluator_reserved_before_goldens": True,
        "source_leak_count": 0,
        "absolute_public_path_count": 0,
        "status": "PASS",
    }
    write_canonical_json(
        evidence_source / "protocol_evidence.json",
        {**evidence_body, "evidence_hash": content_hash(evidence_body)},
    )
    e_output = repository / "artifacts" / "m336j3" / "e26-evidence"
    e_report = _invoke_publication_script(
        repository=repository,
        private_root=private,
        script_name="m336j_publish_e26.py",
        request_name="e26-publisher-request.json",
        request={
            "repository": str(repository),
            "git_executable": str(git),
            "exact_f26_sha": f26,
            "exact_h26_sha": h26,
            "freeze_manifest": str(freeze / "freeze_manifest_v2.json"),
            "evidence_source": str(evidence_source),
            "output": str(e_output),
        },
    )
    _run(git, repository, "add", "-f", "artifacts/m336j3/e26-evidence")
    e26 = _commit(
        git,
        repository,
        M336J3_E26_SUBJECT,
    )
    _run(git, repository, "push", "origin", M336J3_BRANCH_NAME)
    protocol = verify_m336j_h26_e26_commit_protocol(
        repository=repository,
        git_executable=git,
        exact_f26_sha=f26,
        exact_h26_sha=h26,
        exact_e26_sha=e26,
        freeze_manifest=freeze / "freeze_manifest_v2.json",
    )
    ordered = tuple(
        line
        for line in _run(
            git,
            repository,
            "rev-list",
            "--first-parent",
            "--reverse",
            f"{M336J3_EXACT_Q25_SHA}..{e26}",
        ).splitlines()
        if line
    )
    expected = (
        state["exact_r26_sha"],
        state["exact_q26_sha"],
        f26,
        h26,
        e26,
    )
    merge_count = int(
        _run(
            git,
            repository,
            "rev-list",
            "--count",
            "--merges",
            f"{M336J3_EXACT_Q25_SHA}..{e26}",
        )
    )
    if ordered != expected or merge_count != 0:
        raise ValueError("M336J3 disposable Q/F/H/E chain is not exact and linear")
    body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336J3_DISPOSABLE_PROTOCOL_RECEIPT",
        "r26_sha": state["exact_r26_sha"],
        "q26_like_sha": state["exact_q26_sha"],
        "f26_like_sha": f26,
        "h26_like_sha": h26,
        "e26_like_sha": e26,
        "ordered_commit_shas": ordered,
        "merge_count": merge_count,
        "final_route_receipt_hash": final_route["receipt_hash"],
        "acquisition_ledger_receipt_hash": acquisition.receipt_hash,
        "selector_ledger_receipt_hash": selector["receipt_hash"],
        "evaluator_event_count": len(evaluator_events),
        "evaluator_reserved_before_goldens": True,
        "evaluator_retry_count": 0,
        "windows_production_status": "PASS",
        "karina_production_status": "PASS",
        "public_pack_status": "PASS",
        "sealed_replay_status": "PASS",
        "independent_evaluation_status": evaluation["status"],
        "h26_report_hash": h_report["report_hash"],
        "h26_quality_receipt_hash": h_quality["receipt_hash"],
        "e26_report_hash": e_report["report_hash"],
        "commit_protocol_receipt_hash": protocol["receipt_hash"],
        "source_leak_count": 0,
        "absolute_public_path_count": 0,
        "private_public_artifact_count": 0,
        "final_real_acquisition_reservation_count": 0,
        "final_real_acquisition_invocation_count": 0,
        "final_real_selector_reservation_count": 0,
        "final_real_selector_invocation_count": 0,
        "final_real_evaluator_reservation_count": 0,
        "final_real_evaluator_invocation_count": 0,
        "new_final_source_body_bytes": 0,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    write_canonical_json(public / "disposable_protocol_receipt.json", receipt)
    print(canonical_json(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--request", type=Path, required=True)
    complete_parser = commands.add_parser("complete")
    complete_parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.request)
    elif args.command == "complete":
        complete(args.request)


if __name__ == "__main__":
    main()
