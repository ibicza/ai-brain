"""Run a disposable FINAL-mode Q/F/H/E chain through the official M336K4 CLI."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from m336k4_prepare_karina_capsule import prepare_m336k4_karina_capsule

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336f_selection import M336FSelectorLedger
from ai_brain.stage3.acquisition.m336j_execution import (
    compute_m336j_project_source_identity,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    M336K2RouteLedger,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k2_publication import (
    publication_contract_from_dict,
    verify_m336k2_commit_protocol,
)
from ai_brain.stage3.acquisition.m336k4_authorization import (
    M336K4FinalAuthorization,
)
from ai_brain.stage3.acquisition.m336k4_controller import (
    verify_m336k4_acquisition_ledger_identity,
    verify_m336k4_evaluator_ledger_identity,
    verify_m336k4_route_ledger_identity,
    verify_m336k4_selector_ledger_identity,
)
from ai_brain.stage3.acquisition.m336k4_freeze import (
    M336K4FreezeManifest,
    attest_committed_m336k4_f29,
    materialize_m336k4_f29,
)
from ai_brain.stage3.acquisition.m336k4_identity import M336K4RouteIdentityBundle
from ai_brain.stage3.acquisition.m336k4_request import (
    build_m336k4_final_route_request,
    write_m336k4_final_route_request,
)
from ai_brain.stage3.acquisition.m336k_acquisition import M336KAcquisitionLedger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request.resolve(strict=True))
    expected = {
        "source_repository",
        "git_executable",
        "python_executable",
        "base_sha",
        "disposable_branch",
        "disposable_label",
        "legacy_component_request_template",
        "stage_request_template",
        "output",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K4 disposable request fields changed")
    output = Path(request["output"]).resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K4 disposable output must be fresh")
    output.mkdir(parents=True)
    git = Path(request["git_executable"]).resolve(strict=True)
    python = Path(request["python_executable"]).resolve(strict=True)
    source = Path(request["source_repository"]).resolve(strict=True)
    branch = request["disposable_branch"]
    if not branch.startswith("disposable/m336k4-"):
        raise M336K2ProtocolError("M336K4 disposable branch namespace changed")
    remote = output / "origin.git"
    repository = output / "repository"
    private = output / "private"
    public = output / "public"
    private.mkdir()
    public.mkdir()
    _git(git, None, "init", "--bare", str(remote))
    _git(git, None, "clone", "--no-local", str(source), str(repository))
    _git(git, repository, "config", "core.autocrlf", "false")
    _git(git, repository, "config", "user.email", "m336k4@example.invalid")
    _git(git, repository, "config", "user.name", "M336K4 Disposable Proof")
    _git(git, repository, "remote", "set-url", "origin", str(remote))
    _git(git, repository, "checkout", "-B", branch, request["base_sha"])
    _apply_working_tree(source, repository, git)
    _git(git, repository, "add", "--all")
    _git(
        git, repository, "commit", "-m", "M-33.6k.4 disposable implementation snapshot"
    )
    implementation = _git(git, repository, "rev-parse", "HEAD^{commit}")
    _git(git, repository, "push", "-u", "origin", branch)
    stage_template = _object(
        Path(request["stage_request_template"]).resolve(strict=True)
    )
    label = request["disposable_label"]
    if not isinstance(label, str) or re.fullmatch(r"[a-z0-9-]+", label) is None:
        raise M336K2ProtocolError("M336K4 disposable label is invalid")
    base_karina = stage_template["karina"]
    karina_preparation = prepare_m336k4_karina_capsule(
        {
            "repository": str(repository),
            "exact_head": implementation,
            "git_executable": str(git),
            "base_private_capsule": base_karina["private_execution_capsule"],
            "ssh_executable": base_karina["ssh_executable"],
            "scp_executable": stage_template["executable_handles"]["scp"],
            "ssh_key": base_karina["ssh_key"],
            "known_hosts_file": base_karina["known_hosts_file"],
            "worker_endpoint": base_karina["worker_endpoint"],
            "remote_workspace": (
                f"/home/ibicza/m336k4-disposable-{label}-{implementation[:12]}"
            ),
            "output": str(private / "karina-capsule"),
        }
    )
    karina_overlay = karina_preparation["karina_overlay"]
    environment_path = private / "python-environment.json"
    _run(
        python,
        repository,
        "scripts/m336k2_capture_local_environment.py",
        "--repository",
        str(repository),
        "--python-executable",
        str(python),
        "--git-executable",
        str(git),
        "--output",
        str(environment_path),
    )
    legacy_request = _object(
        Path(request["legacy_component_request_template"]).resolve(strict=True)
    )
    legacy_output = private / "legacy-components"
    legacy_request.update(
        {
            "repository": str(repository),
            "python_executable": str(python),
            "python_environment_manifest": str(environment_path),
            "output": str(legacy_output),
            "branch_ref": f"refs/heads/{branch}",
            "q_root": "artifacts/m336k4/disposable/q-like",
            "f_root": "artifacts/m336k4/disposable/f-like",
            "h_root": "artifacts/m336k4/disposable/h-like",
            "e_root": "artifacts/m336k4/disposable/e-like",
            "q_subject": "M-33.6k.4 disposable Q-like",
            "f_subject": "M-33.6k.4 disposable F-like",
            "h_subject": "M-33.6k.4 disposable H-like",
            "e_subject": "M-33.6k.4 disposable E-like",
            "execution_mode": "FINAL",
            "acquisition_run_id": (
                f"m336k4.disposable.{request['disposable_label']}.acquisition.v1"
            ),
        }
    )
    legacy_request["executables"]["python"]["path"] = str(python)
    legacy_request["karina_public_execution_capsule_receipt"] = karina_overlay[
        "public_execution_capsule_receipt"
    ]
    legacy_request["karina_executable_dependency_manifest"] = karina_overlay[
        "executable_dependency_manifest"
    ]
    legacy_request_path = private / "legacy-component-request.json"
    _write(legacy_request_path, legacy_request)
    _run(
        python,
        repository,
        "scripts/m336k2_build_component_bundle.py",
        "--request",
        str(legacy_request_path),
    )
    q_root = repository / "artifacts" / "m336k4" / "disposable" / "q-like"
    q_root.mkdir(parents=True)
    _write(
        q_root / "identity_qualification.json",
        _hashed(
            "receipt_hash",
            schema_version=1,
            contract_role="PUBLIC_SAFE_M336K4_DISPOSABLE_IDENTITY_QUALIFICATION",
            required_mutation_case_count=25,
            mutation_execution_phase="POST_F_LIKE_PRE_CONTROLLER",
            canonical_request_builder_present=True,
            external_route_run_id_absent=True,
            execution_mode="FINAL",
            status="PASS",
        ),
    )
    q_manifest = _q_manifest(q_root)
    q_manifest_path = q_root / "evidence_manifest.json"
    _write(q_manifest_path, q_manifest)
    readiness_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K4_DISPOSABLE_Q_LIKE_READINESS",
        "exact_implementation_tip": implementation,
        "official_one_shot_counter_count": 0,
        "new_final_source_body_bytes": 0,
        "status": "READY_FOR_TYPED_FINAL_JAVA_EXECUTION_V4",
    }
    readiness = {**readiness_body, "readiness_hash": content_hash(readiness_body)}
    readiness_path = q_root / "readiness.json"
    _write(readiness_path, readiness)
    q_like = _commit(
        git, repository, legacy_request["q_subject"], legacy_request["q_root"]
    )
    _git(git, repository, "push", "origin", branch)
    typed_output = private / "typed-components"
    typed_request = {
        "repository": str(repository),
        "legacy_bundle": str(legacy_output),
        "exact_implementation_tip": implementation,
        "exact_q29_sha": q_like,
        "branch_ref": f"refs/heads/{branch}",
        "readiness_hash": readiness["readiness_hash"],
        "q_readiness": str(readiness_path),
        "q_evidence_manifest": str(q_manifest_path),
        "identity_mode": "DISPOSABLE",
        "disposable_label": request["disposable_label"],
        "output": str(typed_output),
    }
    typed_request_path = private / "typed-component-request.json"
    _write(typed_request_path, typed_request)
    _run(
        python,
        repository,
        "scripts/m336k4_build_component_bundle.py",
        "--request",
        str(typed_request_path),
    )
    components = {
        path.stem: path
        for path in typed_output.glob("*.json")
        if path.name != "bundle_receipt.json"
    }
    f_root = repository / "artifacts" / "m336k4" / "disposable" / "f-like"
    build = materialize_m336k4_f29(
        repository=repository,
        git_executable=git,
        exact_implementation_tip=implementation,
        exact_q29_sha=q_like,
        readiness=readiness_path,
        component_sources=components,
        output=f_root,
        expected_branch=branch,
        freeze_relative_root=legacy_request["f_root"],
    )
    f_like = _commit(
        git, repository, legacy_request["f_subject"], legacy_request["f_root"]
    )
    _git(git, repository, "push", "origin", branch)
    freeze = M336K4FreezeManifest.from_dict(_object(f_root / "freeze_manifest.json"))
    attestation = attest_committed_m336k4_f29(
        repository, git, freeze_manifest=freeze, exact_f29_sha=f_like
    )
    attestation_path = private / "f29-attestation.json"
    _write(attestation_path, asdict(attestation))
    runtime = output / "runtime"
    destinations = {
        "acquisition_ledger": str(runtime / "ledgers" / "acquisition.jsonl"),
        "selector_ledger": str(runtime / "ledgers" / "selector.jsonl"),
        "evaluator_ledger": str(runtime / "ledgers" / "evaluator.jsonl"),
        "route_state_ledger": str(runtime / "ledgers" / "route.jsonl"),
        "vault": str(runtime / "vault"),
        "selected_source_snapshot": str(runtime / "windows-selected"),
        "windows_production": str(runtime / "windows-production"),
        "karina_production": str(runtime / "karina-production"),
        "evaluator_root": str(runtime / "evaluator"),
    }
    stage = _render_stage_template(
        stage_template,
        repository=repository,
        git=git,
        python=python,
        implementation=implementation,
        f_like=f_like,
        freeze_root=f_root,
        attestation=attestation_path,
        runtime=runtime,
        destinations=destinations,
    )
    stage["karina"].update(karina_overlay)
    bundle_path = _frozen_component(repository, freeze, "route_identity_bundle")
    authorization_path = _frozen_component(repository, freeze, "final_authorization")
    contract_path = _frozen_component(repository, freeze, "h28_publication_contract")
    final_request = build_m336k4_final_route_request(
        purpose="DISPOSABLE",
        repository=str(repository),
        git_executable=str(git),
        python_executable=str(python),
        exact_implementation_sha=implementation,
        exact_f29_sha=f_like,
        freeze_manifest=str(f_root / "freeze_manifest.json"),
        f29_attestation=str(attestation_path),
        final_authorization=str(authorization_path),
        route_identity_bundle=str(bundle_path),
        publication_contract=str(contract_path),
        route_ledger=destinations["route_state_ledger"],
        route_receipt=str(runtime / "route-receipt.json"),
        stage_state=str(runtime / "stage-state.json"),
        stage_receipt_root=str(runtime / "stage-receipts"),
        private_root=str(runtime / "private"),
        authority_statement=stage["authority_statement"],
        frozen_spdx_reference=stage["frozen_spdx_reference"],
        windows_java=stage["windows_java"],
        windows_javac=stage["windows_javac"],
        final_destinations=destinations,
        karina=stage["karina"],
        executable_handles=stage["executable_handles"],
    )
    final_request_path = private / "canonical-final-request.json"
    write_m336k4_final_route_request(final_request, final_request_path)
    mutation_path = public / "identity_mutation_receipt.json"
    _run(
        python,
        repository,
        "scripts/m336k4_run_identity_mutations.py",
        "--request",
        str(final_request_path),
        "--workspace",
        str(private / "identity-mutation-workspace"),
        "--output",
        str(mutation_path),
    )
    mutation = _object(mutation_path)
    if (
        mutation.get("case_count") != 25
        or mutation.get("accepted_invalid_case_count") != 0
        or mutation.get("wrong_rejection_layer_count") != 0
        or mutation.get("status") != "PASS"
    ):
        raise M336K2ProtocolError("M336K4 disposable mutation matrix failed")
    validation_path = private / "preledger-invocation.json"
    _run(
        python,
        repository,
        "scripts/m336k4_run_final_route.py",
        "--request",
        str(final_request_path),
        "--validate-only",
        "--validation-receipt",
        str(validation_path),
    )
    _run(
        python,
        repository,
        "scripts/m336k4_run_final_route.py",
        "--request",
        str(final_request_path),
    )
    e_like = _git(git, repository, "rev-parse", "HEAD^{commit}")
    h_like = _git(git, repository, "rev-parse", f"{e_like}^")
    contract = publication_contract_from_dict(_object(contract_path))
    protocol = verify_m336k2_commit_protocol(
        repository=repository,
        git_executable=git,
        exact_q28_sha=q_like,
        exact_f28_sha=f_like,
        exact_h28_sha=h_like,
        exact_e28_sha=e_like,
        contract=contract,
    )
    bundle = M336K4RouteIdentityBundle.from_dict(_object(bundle_path))
    route_receipt = _object(Path(final_request.route_receipt))
    observed = _identity_observations(
        repository,
        contract,
        route_receipt,
        bundle,
        final_request,
        _object(validation_path),
    )
    windows_source_identity = compute_m336j_project_source_identity(repository, git)
    karina_source_identity = karina_preparation["project_source_identity"]
    if windows_source_identity != karina_source_identity:
        raise M336K2ProtocolError("M336K4 disposable platform source identity differs")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K4_DISPOSABLE_FINAL_MODE_PROOF",
        "implementation_tip": implementation,
        "q_like_sha": q_like,
        "f_like_sha": f_like,
        "h_like_sha": h_like,
        "e_like_sha": e_like,
        "freeze_build_receipt_hash": build["receipt_hash"],
        "f_attestation_hash": attestation.attestation_hash,
        "canonical_final_request_hash": final_request.request_hash,
        "preledger_invocation_receipt_hash": _object(validation_path)["receipt_hash"],
        "identity_mutation_receipt_hash": mutation["receipt_hash"],
        "identity_mutation_case_count": mutation["case_count"],
        "accepted_invalid_case_count": mutation["accepted_invalid_case_count"],
        "wrong_rejection_layer_count": mutation["wrong_rejection_layer_count"],
        "route_identity_bundle_hash": bundle.bundle_hash,
        "derived_protocol_run_id_hash": bundle.protocol_run_id.identity_hash,
        "external_route_run_id_absent": "route_run_id"
        not in final_request.canonical_object(),
        "execution_mode": bundle.execution_mode.value,
        "identity_observer_count": observed,
        "windows_project_source_identity": windows_source_identity,
        "karina_project_source_identity": karina_source_identity,
        "platform_source_identity_difference_count": 0,
        "route_receipt_hash": route_receipt["receipt_hash"],
        "commit_protocol_receipt_hash": protocol["receipt_hash"],
        "source_leak_count": protocol["source_leak_count"],
        "absolute_path_count": protocol["absolute_path_count"],
        "private_public_artifact_count": protocol["private_artifact_count"],
        "official_one_shot_counter_count": 0,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    _write(public / "disposable_protocol_receipt.json", receipt)
    print(canonical_json(receipt))


def _apply_working_tree(source: Path, repository: Path, git: Path) -> None:
    patch = subprocess.run(
        (str(git), "diff", "--binary", "HEAD"),
        cwd=source,
        check=True,
        capture_output=True,
    ).stdout
    if patch:
        subprocess.run(
            (str(git), "apply", "--binary", "-"),
            cwd=repository,
            input=patch,
            check=True,
            capture_output=True,
        )
    untracked = _git(git, source, "ls-files", "--others", "--exclude-standard", "-z")
    for relative in (item for item in untracked.split("\0") if item):
        source_path = source / relative
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)


def _render_stage_template(
    value: dict,
    *,
    repository: Path,
    git: Path,
    python: Path,
    implementation: str,
    f_like: str,
    freeze_root: Path,
    attestation: Path,
    runtime: Path,
    destinations: dict[str, str],
) -> dict:
    replacements = {
        "@IMPLEMENTATION_TIP@": implementation,
        "@F_SHA@": f_like,
        "@REPOSITORY@": str(repository),
        "@GIT_EXECUTABLE@": str(git),
        "@FREEZE_MANIFEST@": str(freeze_root / "freeze_manifest.json"),
        "@F28_ATTESTATION@": str(attestation),
        "@PRIVATE_ROOT@": str(runtime / "private"),
        "@STAGE_STATE@": str(runtime / "stage-state.json"),
        "@STAGE_RECEIPT_ROOT@": str(runtime / "stage-receipts"),
        "@ACQUISITION_LEDGER@": destinations["acquisition_ledger"],
        "@SELECTOR_LEDGER@": destinations["selector_ledger"],
        "@EVALUATOR_LEDGER@": destinations["evaluator_ledger"],
        "@ROUTE_LEDGER@": destinations["route_state_ledger"],
        "@VAULT@": destinations["vault"],
        "@SELECTED_SOURCE_SNAPSHOT@": destinations["selected_source_snapshot"],
        "@WINDOWS_PRODUCTION@": destinations["windows_production"],
        "@KARINA_PRODUCTION@": destinations["karina_production"],
        "@EVALUATOR_ROOT@": destinations["evaluator_root"],
    }
    freeze = M336K4FreezeManifest.from_dict(
        _object(freeze_root / "freeze_manifest.json")
    )
    for component in freeze.components:
        replacements[f"@COMPONENT_{component.name.upper()}@"] = str(
            repository.joinpath(*Path(component.relative_path).parts)
        )
    result = _replace(value, replacements)
    result["python_executable"] = str(python)
    result["git_executable"] = str(git)
    result["executable_handles"]["python"] = str(python)
    result["executable_handles"]["git"] = str(git)
    return result


def _identity_observations(
    repository, contract, route_receipt, bundle, final_request, validation
) -> int:
    if (
        route_receipt.get("route_identity_bundle_hash") != bundle.bundle_hash
        or route_receipt.get("protocol_run_id")
        != bundle.protocol_run_id.canonical_object()
    ):
        raise M336K2ProtocolError("M336K4 controller identity observation differs")
    verified = 1
    verify_m336k4_route_ledger_identity(
        M336K2RouteLedger(
            Path(final_request.route_ledger), git_worktrees=(repository,)
        ),
        bundle=bundle,
        exact_f29_sha=final_request.exact_f29_sha,
        preledger_receipt_hash=validation["receipt_hash"],
    )
    verified += 1
    private = Path(final_request.private_root)
    authorization = M336K4FinalAuthorization.from_dict(
        _object(Path(final_request.final_authorization))
    )
    freeze = M336K4FreezeManifest.from_dict(
        _object(Path(final_request.freeze_manifest))
    )
    pool = _object(_frozen_component(repository, freeze, "candidate_pool"))
    acquisition_receipt = _object(private / "acquisition_public_receipt.json")
    if (
        acquisition_receipt.get("protocol_run_id")
        != bundle.protocol_run_id.canonical_object()
        or acquisition_receipt.get("acquisition_run_id_typed")
        != bundle.acquisition_run_id.canonical_object()
        or acquisition_receipt.get("route_identity_bundle_hash") != bundle.bundle_hash
    ):
        raise M336K2ProtocolError("M336K4 acquisition identity observation differs")
    verify_m336k4_acquisition_ledger_identity(
        M336KAcquisitionLedger(
            Path(final_request.final_destinations["acquisition_ledger"]),
            git_worktrees=(repository,),
        ),
        bundle=bundle,
        exact_f29_sha=final_request.exact_f29_sha,
        authorization_hash=authorization.authorization_hash,
        candidate_pool_hash=pool["pool_hash"],
    )
    verified += 1
    qualification = _object(private / "candidate_qualification.json")
    summary = _object(private / "compilation-closure" / "qualification_summary.json")
    census = _object(private / "selectability_census.json")
    closure = _object(
        private / "compilation-closure" / "compilation_closure_manifest.json"
    )
    proof = _object(
        private / "compilation-closure" / "compilation_closure_feasibility.json"
    )
    bindings = _object(private / "source_entry_binding_manifest.json")
    verify_m336k4_selector_ledger_identity(
        M336FSelectorLedger(
            Path(final_request.final_destinations["selector_ledger"]),
            git_worktrees=(repository,),
        ),
        bundle=bundle,
        qualification_report_hash=qualification["report_hash"],
        qualification_summary_hash=summary["summary_hash"],
        census_hash=census["census_hash"],
        closure_manifest_hash=closure["manifest_hash"],
        feasibility_proof_hash=proof["proof_hash"],
        binding_manifest_hash=bindings["manifest_hash"],
    )
    verified += 1
    h_commit = _object(private / "h28_commit_receipt.json")["exact_h28_sha"]
    windows_seal = _object(
        Path(final_request.final_destinations["windows_production"])
        / "m336i_production_seal.json"
    )["seal_hash"]
    karina_seal = _object(
        Path(final_request.final_destinations["karina_production"])
        / "m336i_production_seal.json"
    )["seal_hash"]
    verify_m336k4_evaluator_ledger_identity(
        Path(final_request.final_destinations["evaluator_ledger"]),
        bundle=bundle,
        exact_h29_sha=h_commit,
        windows_production_seal_hash=windows_seal,
        karina_production_seal_hash=karina_seal,
    )
    verified += 1
    for relative in (
        f"{contract.h_root}/route_identity_observation.json",
        f"{contract.e_root}/route_identity_observation.json",
    ):
        value = _object(repository.joinpath(*Path(relative).parts))
        _verify_identity_observation(value, bundle)
        verified += 1
    if verified != 7:
        raise M336K2ProtocolError("M336K4 identity observer closure changed")
    return verified


def _verify_identity_observation(value: dict, bundle) -> None:
    body = dict(value)
    claimed = body.pop("receipt_hash", None)
    if (
        content_hash(body) != claimed
        or value.get("route_version") != bundle.route_version.canonical_object()
        or value.get("protocol_run_id") != bundle.protocol_run_id.canonical_object()
        or value.get("acquisition_run_id")
        != bundle.acquisition_run_id.canonical_object()
        or value.get("selector_run_id") != bundle.selector_run_id.canonical_object()
        or value.get("evaluator_run_id") != bundle.evaluator_run_id.canonical_object()
        or value.get("execution_mode") != bundle.execution_mode.canonical_object()
        or value.get("route_identity_bundle_hash") != bundle.bundle_hash
        or value.get("status") != "PASS"
    ):
        raise M336K2ProtocolError("M336K4 publication identity observation differs")


def _frozen_component(repository: Path, freeze, name: str) -> Path:
    rows = [item for item in freeze.components if item.name == name]
    if len(rows) != 1:
        raise M336K2ProtocolError("M336K4 disposable frozen component lookup failed")
    return repository.joinpath(*Path(rows[0].relative_path).parts).resolve(strict=True)


def _q_manifest(root: Path) -> dict:
    rows = tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in root.rglob("*")
        if path.is_file()
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K4_DISPOSABLE_Q_LIKE_MANIFEST",
        "files": tuple(sorted(rows)),
        "file_count": len(rows),
        "tree_hash": content_hash(tuple(sorted(rows))),
        "source_leak_count": 0,
        "absolute_path_count": 0,
        "private_artifact_count": 0,
        "status": "PASS",
    }
    return {**body, "manifest_hash": content_hash(body)}


def _commit(git: Path, repository: Path, subject: str, relative: str) -> str:
    _git(git, repository, "add", "-f", "--", relative)
    _git(git, repository, "commit", "-m", subject)
    return _git(git, repository, "rev-parse", "HEAD^{commit}")


def _run(python: Path, repository: Path, script: str, *arguments: str) -> None:
    environment = m336k2_minimal_environment()
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(repository / "src"),
            "PYTHONUTF8": "1",
        }
    )
    subprocess.run(
        (str(python), "-B", str(repository / script), *arguments),
        cwd=repository,
        check=True,
        env=environment,
    )


def _git(git: Path, repository: Path | None, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()


def _hashed(field: str, **body) -> dict:
    return {**body, field: content_hash(body)}


def _replace(value, replacements: dict[str, str]):
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K4 disposable JSON input is not an object")
    return value


if __name__ == "__main__":
    main()
