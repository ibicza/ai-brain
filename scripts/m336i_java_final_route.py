"""Native authorized M-33.6i Java route controller and isolated worker."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_jdk_provider import (
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.java_production_compiler import (
    build_java_production_compilation_probe,
    run_java_production_compilation_probe,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.m336e_identity import (
    portable_vault_manifest_from_dict,
    source_entry_binding_manifest_from_dict,
    verify_portable_vault_manifest,
)
from ai_brain.stage3.acquisition.m336e_selectability import (
    selectable_source_census_from_dict,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    build_java_compilation_closure_manifest,
    combine_java_compilation_closure_manifests,
    java_compilation_closure_feasibility_proof_from_dict,
    java_compilation_closure_manifest_from_dict,
    prove_java_compilation_closure_feasibility,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    M336FSelectorLedger,
    m336f_selected_source_manifest_from_dict,
    m336f_selector_receipt_from_dict,
    select_compilation_closed_sources_once,
)
from ai_brain.stage3.acquisition.m336g_publication import (
    ArtifactConfidentialityRole,
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336g_staging import validate_public_staging
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336h_evaluation import M336HEvaluatorLedger
from ai_brain.stage3.acquisition.m336h_materialization import (
    materialize_m336f_selected_source_snapshot,
)
from ai_brain.stage3.acquisition.m336h_production import (
    M336HCompilerAwareProductionRequest,
)
from ai_brain.stage3.acquisition.m336i_acquisition import (
    M336IFinalAcquisitionLedger,
    M336IFinalAcquisitionRequest,
    final_acquisition_authorization_from_dict,
    run_m336i_frozen_final_acquisition,
    validate_m336i_final_acquisition_request_before_side_effects,
)
from ai_brain.stage3.acquisition.m336i_evaluation import (
    M336IIndependentEvaluationRequest,
    independent_evaluator_identity,
    run_m336i_independent_java_evaluation,
)
from ai_brain.stage3.acquisition.m336i_production import (
    M336ICompilerAwareProductionRequest,
    run_m336i_compiler_aware_production,
)
from ai_brain.stage3.acquisition.m336i_registry import (
    build_m336i_final_java_route_manifest,
    build_m336i_final_java_route_registry,
)
from ai_brain.stage3.acquisition.m336i_route import M336IRouteStateLedger
from ai_brain.stage3.acquisition.m336j_evaluator_v2 import (
    M336JEvaluatorLedgerV2,
    M336JEvaluatorReservationInputV2,
    advance_m336j_evaluator_v2,
    reserve_m336j_evaluator_v2,
)
from ai_brain.stage3.acquisition.m336j_execution import (
    KarinaRemoteTokenClass,
    build_remote_command_plan,
    dependency_manifest_from_dict,
    load_private_execution_capsule,
    public_execution_capsule_receipt_from_dict,
)
from ai_brain.stage3.acquisition.m336j_final_v2 import (
    build_m336j_final_freeze_lineage_policy_v2,
    build_m336j_git_executable_receipt_v2,
    load_m336j_final_authorization_v2,
    load_m336j_final_freeze_manifest_v2,
    m336j_final_authorization_v2_to_legacy,
    verify_m336j_authorization_manifest_cross_bindings_v2,
    verify_m336j_final_freeze_lineage_v2,
)
from ai_brain.stage3.acquisition.m336j_registry import (
    build_m336j_route_manifest,
    build_m336j_route_registry,
    command_renderer_identity_hash,
)
from ai_brain.stage3.acquisition.m336j_transport import (
    M336J_DEFAULT_TREE_TRANSFER_LIMITS,
    KarinaPrivateSshTransport,
    canonical_json_bytes,
    extract_canonical_tree_export_file,
    hash_file,
    invoke_karina_command,
    invoke_karina_command_streaming,
    parse_bound_json_response,
    parse_framed_tree_response_file,
    portable_tree_content_identity,
    write_canonical_tree_archive,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError(f"M336I expected an object: {path.name}")
    return value


def _worktrees(
    repository: Path, git_executable: Path | None = None
) -> tuple[Path, ...]:
    git = (
        git_executable.resolve(strict=True)
        if git_executable is not None
        else Path(shutil.which("git") or "").resolve(strict=True)
    )
    output = subprocess.run(
        (str(git), "worktree", "list", "--porcelain"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    candidates = tuple(
        Path(line.removeprefix("worktree "))
        for line in output.splitlines()
        if line.startswith("worktree ")
    )
    return tuple(path.resolve(strict=True) for path in candidates if path.is_dir())


def _preflight(args) -> None:
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336I preflight output must be fresh")
    registry = build_m336i_final_java_route_registry()
    manifest = build_m336i_final_java_route_manifest(registry)
    output.mkdir(parents=True)
    write_canonical_json(output / "route_component_registry.json", registry)
    write_canonical_json(output / "route_manifest.json", manifest)
    body = {
        "schema_version": 1,
        "registry_hash": registry.registry_hash,
        "route_manifest_hash": manifest.manifest_hash,
        "component_count": registry.component_count,
        "edge_count": manifest.edge_count,
        "unresolved_callable_count": manifest.unresolved_callable_count,
        "incompatible_edge_count": manifest.incompatible_edge_count,
        "refusal_guard_registered_as_provider": (
            manifest.refusal_guard_registered_as_provider
        ),
        "status": "PASS",
    }
    write_canonical_json(
        output / "route_preflight_receipt.json",
        {**body, "receipt_hash": content_hash(body)},
    )


def _rehearse_existing(args) -> None:
    config = _object(args.config)
    required = {
        "repository",
        "sealed_vault",
        "qualification_report",
        "qualification_summary",
        "bindings",
        "census",
        "closure_manifest",
        "closure_proof",
        "candidate_pool",
        "selector_ledger",
        "selected_snapshot",
        "private_replay_root",
        "production_output",
        "public_staging_reserved",
        "javac",
        "preflight_root",
        "threshold_manifest",
        "publication_boundary_contract_hash",
        "selector_seed",
        "implementation_identity",
    }
    optional = {"acquisition_rehearsal_receipt", "route_manifest"}
    if not required <= set(config) <= required | optional:
        raise ValueError("M336I existing-source rehearsal config fields changed")
    acquisition_rehearsal = None
    if args.command == "rehearse-authorized":
        if "acquisition_rehearsal_receipt" not in config:
            raise ValueError("M336I authorized rehearsal lacks acquisition evidence")
        acquisition_rehearsal = _object(Path(config["acquisition_rehearsal_receipt"]))
        acquisition_body = dict(acquisition_rehearsal)
        acquisition_hash = acquisition_body.pop("receipt_hash", None)
        if (
            content_hash(acquisition_body) != acquisition_hash
            or acquisition_rehearsal.get("status") != "PASS"
            or acquisition_rehearsal.get("final_acquisition_reservation_count") != 0
            or acquisition_rehearsal.get("final_acquisition_invocation_count") != 0
            or acquisition_rehearsal.get("rehearsal_acquisition_reservation_count") != 1
            or acquisition_rehearsal.get("rehearsal_acquisition_invocation_count") != 1
            or acquisition_rehearsal.get("rehearsal_acquisition_rerun_count") != 0
        ):
            raise ValueError("M336I authorized acquisition rehearsal is not sealed")
    elif "acquisition_rehearsal_receipt" in config:
        raise ValueError(
            "M336I non-acquisition rehearsal supplied acquisition evidence"
        )
    repository = Path(config["repository"]).resolve(strict=True)
    worktrees = _worktrees(repository)
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336I rehearsal evidence output must be fresh")
    destinations = (
        output,
        Path(config["selector_ledger"]),
        Path(config["selected_snapshot"]),
        Path(config["private_replay_root"]),
        Path(config["production_output"]),
    )
    if any(path.exists() for path in destinations):
        raise FileExistsError("M336I rehearsal destinations must be fresh")
    preflight = Path(config["preflight_root"]).resolve(strict=True)
    route_manifest_path = (
        Path(config["route_manifest"])
        if "route_manifest" in config
        else preflight / "route_manifest.json"
    )
    frozen_route = _object(route_manifest_path)
    if "route_manifest" in config:
        registry = build_m336j_route_registry()
        manifest = build_m336j_route_manifest(
            registry,
            execution_capsule_public_receipt_hash=frozen_route[
                "execution_capsule_public_receipt_hash"
            ],
            remote_command_renderer_hash=frozen_route["remote_command_renderer_hash"],
            executable_dependency_manifest_hash=frozen_route[
                "executable_dependency_manifest_hash"
            ],
            minimal_environment_policy_hash=frozen_route[
                "minimal_environment_policy_hash"
            ],
        )
    else:
        registry = build_m336i_final_java_route_registry()
        manifest = build_m336i_final_java_route_manifest(registry)
    if frozen_route != json.loads(canonical_json(manifest)):
        raise ValueError("M336I rehearsal route manifest differs from live code")
    bindings = source_entry_binding_manifest_from_dict(
        _object(Path(config["bindings"]))
    )
    census = selectable_source_census_from_dict(_object(Path(config["census"])))
    closure = java_compilation_closure_manifest_from_dict(
        _object(Path(config["closure_manifest"]))
    )
    proof = java_compilation_closure_feasibility_proof_from_dict(
        _object(Path(config["closure_proof"]))
    )
    qualification = _object(Path(config["qualification_report"]))
    summary = _object(Path(config["qualification_summary"]))
    selector_ledger = M336FSelectorLedger(
        Path(config["selector_ledger"]), git_worktrees=worktrees
    )
    selected, selector = select_compilation_closed_sources_once(
        census=census,
        closure_manifest=closure,
        proof=proof,
        bindings=bindings,
        selector_seed=config["selector_seed"],
        ledger=selector_ledger,
        qualification_report_hash=qualification["report_hash"],
        qualification_summary_hash=summary["summary_hash"],
    )
    output.mkdir(parents=True, exist_ok=False)
    selected_path = output / "selected_source_manifest.json"
    selector_path = output / "selector_receipt.json"
    write_canonical_json(selected_path, selected)
    write_canonical_json(selector_path, selector)
    write_canonical_json(
        output / "selector_ledger_receipt.json", selector_ledger.receipt()
    )
    materialized = materialize_m336f_selected_source_snapshot(
        sealed_vault_root=Path(config["sealed_vault"]),
        bindings=bindings,
        selected_manifest=selected,
        selector_receipt=selector,
        closure_manifest=closure,
        closure_proof=proof,
        destination=Path(config["selected_snapshot"]),
        git_worktrees=worktrees,
        public_roots=(output, Path(config["production_output"])),
    )
    write_canonical_json(output / "materialization_receipt.json", materialized)
    javac = Path(config["javac"]).resolve(strict=True)
    java = javac.with_name("java.exe" if args.platform == "WINDOWS" else "java")
    _private_jdk, public_jdk = verify_m336_jdk_provider_evidence(
        platform=args.platform.casefold(), java=java, javac=javac
    )
    threshold_path = Path(config["threshold_manifest"]).resolve(strict=True)
    threshold = _object(threshold_path)
    base = M336HCompilerAwareProductionRequest(
        route_manifest_hash=manifest.manifest_hash,
        implementation_identity=config["implementation_identity"],
        platform_role=args.platform,
        source_snapshot_private_handle=Path(config["selected_snapshot"]),
        javac_private_handle=javac,
        public_jdk_identity_receipt_hash=public_jdk.receipt_hash,
        source_entry_bindings=Path(config["bindings"]),
        selected_manifest=selected_path,
        selector_receipt=selector_path,
        closure_manifest=Path(config["closure_manifest"]),
        closure_feasibility_proof=Path(config["closure_proof"]),
        sealed_vault=Path(config["sealed_vault"]),
        private_replay_root=Path(config["private_replay_root"]),
        public_production_destination=Path(config["production_output"]),
        publication_boundary_contract_hash=config["publication_boundary_contract_hash"],
        threshold_manifest_hash=threshold["threshold_manifest_hash"],
    )
    response, seal = run_m336i_compiler_aware_production(
        M336ICompilerAwareProductionRequest(
            production_request=base,
            frozen_route_manifest=route_manifest_path,
            frozen_implementation_identity=config["implementation_identity"],
            frozen_publication_boundary_hash=config[
                "publication_boundary_contract_hash"
            ],
            frozen_threshold_manifest=threshold_path,
            public_staging_root=Path(config["public_staging_reserved"]),
            git_worktrees=worktrees,
        )
    )
    write_canonical_json(
        Path(config["production_output"]) / "m336i_production_seal.json", seal
    )
    write_canonical_json(output / "production_seal.json", seal)
    pack = verify_java_public_candidate_pack(
        Path(config["production_output"]) / "candidate_pack"
    )
    replay = _object(
        Path(config["production_output"]) / "sealed_source_replay_receipt.json"
    )
    body = {
        "schema_version": 1,
        "rehearsal_kind": args.command.removeprefix("rehearse-")
        .replace("-", "_")
        .upper(),
        "platform_role": args.platform,
        "route_manifest_hash": manifest.manifest_hash,
        "selected_manifest_hash": selected.manifest_hash,
        "selector_receipt_hash": selector.receipt_hash,
        "materialization_receipt_hash": materialized.receipt_hash,
        "production_response_hash": response.response_hash,
        "production_seal_hash": seal.seal_hash,
        "selected_file_count": selected.file_count,
        "selected_root_count": selected.root_count,
        "root_distribution": selected.root_distribution,
        "closure_support_file_count": selected.closure_support_file_count,
        "proposal_count": seal.proposal_count,
        "trusted_count": seal.trusted_count,
        "withheld_count": seal.withheld_count,
        "network_access_count": seal.production_network_access_count,
        "final_acquisition_reservation_count": 0,
        "final_acquisition_invocation_count": 0,
        "rehearsal_acquisition_reservation_count": (
            acquisition_rehearsal["rehearsal_acquisition_reservation_count"]
            if acquisition_rehearsal
            else 0
        ),
        "rehearsal_acquisition_invocation_count": (
            acquisition_rehearsal["rehearsal_acquisition_invocation_count"]
            if acquisition_rehearsal
            else 0
        ),
        "rehearsal_acquisition_rerun_count": (
            acquisition_rehearsal["rehearsal_acquisition_rerun_count"]
            if acquisition_rehearsal
            else 0
        ),
        "candidate_pack_content_hash": pack.candidate_pack_content_hash,
        "candidate_pack_tree_hash": pack.candidate_pack_tree_hash,
        "public_replay_commitment_hash": seal.public_replay_commitment_hash,
        "sealed_replay_receipt_hash": replay["receipt_hash"],
        "runtime_status": "PASS",
        "status": "PASS",
    }
    write_canonical_json(
        output / "rehearsal_receipt.json",
        {**body, "receipt_hash": content_hash(body)},
    )


def _evaluate_rehearsal(args) -> None:
    config = _object(args.config)
    required = {
        "route_manifest",
        "threshold_manifest",
        "windows_production_root",
        "karina_production_root",
        "semantic_goldens",
        "sealed_vault",
        "bindings",
        "candidate_pool",
        "qualification_report",
        "selected_manifest",
        "frozen_spdx_reference",
        "evaluator_ledger",
        "repository",
    }
    if set(config) != required:
        raise ValueError("M336I rehearsal evaluation config fields changed")
    windows = Path(config["windows_production_root"])
    karina = Path(config["karina_production_root"])
    result = run_m336i_independent_java_evaluation(
        M336IIndependentEvaluationRequest(
            route_manifest=Path(config["route_manifest"]),
            threshold_manifest=Path(config["threshold_manifest"]),
            windows_production_seal=windows / "m336i_production_seal.json",
            karina_production_seal=karina / "m336i_production_seal.json",
            windows_production_output=windows / "production_output.json",
            karina_production_output=karina / "production_output.json",
            windows_field_evidence_manifest=windows / "field_evidence_manifest.json",
            karina_field_evidence_manifest=karina / "field_evidence_manifest.json",
            public_candidate_pack=windows / "candidate_pack",
            windows_replay_receipt=windows / "sealed_source_replay_receipt.json",
            karina_replay_receipt=karina / "sealed_source_replay_receipt.json",
            independently_authored_semantic_goldens=Path(config["semantic_goldens"]),
            external_sealed_vault=Path(config["sealed_vault"]),
            source_entry_bindings=Path(config["bindings"]),
            candidate_pool=Path(config["candidate_pool"]),
            qualification_report=Path(config["qualification_report"]),
            selected_manifest=Path(config["selected_manifest"]),
            frozen_spdx_reference=Path(config["frozen_spdx_reference"]),
            evaluator_ledger=Path(config["evaluator_ledger"]),
            git_worktrees=_worktrees(Path(config["repository"])),
        )
    )
    write_canonical_json(args.output, result)


def _verify_rehearsal_staging(args) -> None:
    config = _object(args.config)
    required = {
        "staging_root",
        "candidate_pack",
        "sealed_vault",
        "windows_production_seal",
        "karina_production_seal",
        "independent_evaluation",
    }
    if set(config) != required:
        raise ValueError("M336I rehearsal staging config fields changed")
    staging = Path(config["staging_root"])
    if staging.exists():
        raise FileExistsError("M336I rehearsal staging must be fresh")
    staging.mkdir(parents=True)
    shutil.copytree(Path(config["candidate_pack"]), staging / "candidate-pack")
    shutil.copytree(Path(config["candidate_pack"]), staging / "installed-pack")
    for name in (
        "windows_production_seal",
        "karina_production_seal",
        "independent_evaluation",
    ):
        shutil.copy2(Path(config[name]), staging / f"{name}.json")
    roles = {
        path.relative_to(staging).as_posix(): (
            ArtifactConfidentialityRole.PUBLIC_DERIVED_PACK
            if path.relative_to(staging).parts[0]
            in {"candidate-pack", "installed-pack"}
            else ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT
        )
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
    manifest, receipt = validate_public_staging(
        staging_root=staging,
        artifact_roles=roles,
        sealed_vault_root=Path(config["sealed_vault"]),
        candidate_pack_relative_path="candidate-pack",
        installed_pack_relative_path="installed-pack",
        prospective_git_tree_hash=content_hash(rows),
        prospective_git_entries=rows,
    )
    write_canonical_json(args.output, receipt)
    write_canonical_json(
        args.output.with_name(args.output.stem + "_manifest.json"), manifest
    )


def _build_closure(args, private: Path):
    bindings = source_entry_binding_manifest_from_dict(
        _object(private / "source_entry_binding_manifest.json")
    )
    census = selectable_source_census_from_dict(
        _object(private / "selectability_census.json")
    )
    eligible = {
        f"{item.candidate_root}/{item.canonical_path}": item
        for item in census.decisions
        if item.analysis_eligible
    }
    binding_by_unit = {
        item.selected_path: item
        for item in bindings.bindings
        if item.selected_path in eligible
    }
    if set(eligible) != set(binding_by_unit):
        raise ValueError("M336I eligible census lacks exact source bindings")
    closure_root = private / "compilation-closure"
    closure_root.mkdir()
    probe = build_java_production_compilation_probe(args.windows_javac)
    with tempfile.TemporaryDirectory(prefix="m336i-closure-") as temporary:
        temporary_root = Path(temporary)
        source_root = temporary_root / "sources"
        source_root.mkdir()
        store = AcquisitionStore.open_or_initialize(temporary_root / "store")
        for unit, binding in sorted(binding_by_unit.items()):
            target = source_root.joinpath(*unit.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((args.windows_vault / binding.vault_path).read_bytes())
        manifests = []
        reports = []
        for family in sorted({item.candidate_root for item in eligible.values()}):
            paths = tuple(
                sorted(
                    (source_root / family).rglob("*.java"),
                    key=lambda item: (
                        item.relative_to(source_root).as_posix().encode("utf-8")
                    ),
                )
            )
            bundle = ingest_bundle(
                paths,
                bundle_id=f"m336i-final-census-{family}",
                domain_tags=("java-api",),
                imported_at="1970-01-01T00:00:00Z",
                source_root=source_root,
                store=store,
            )
            index = index_java_bundle(bundle, store)
            identities = {
                unit: binding_by_unit[unit].source_entry_id.identity_hash
                for unit in binding_by_unit
                if unit.startswith(f"{family}/")
            }
            report = run_java_production_compilation_probe(
                bundle=bundle,
                store=store,
                source_index=index,
                probe=probe,
                javac_executable=args.windows_javac,
                source_entry_ids=identities,
            )
            manifests.append(
                build_java_compilation_closure_manifest(
                    source_index=index,
                    compiler_report=report,
                    source_entry_ids=identities,
                )
            )
            reports.append((family, report))
        closure = combine_java_compilation_closure_manifests(tuple(manifests))
    proof = prove_java_compilation_closure_feasibility(closure, census)
    write_canonical_json(closure_root / "compiler_probe.json", probe)
    write_canonical_json(closure_root / "compilation_closure_manifest.json", closure)
    write_canonical_json(closure_root / "compilation_closure_feasibility.json", proof)
    for family, report in reports:
        write_canonical_json(
            closure_root / "compiler-reports" / f"{family}.json", report
        )
    if not proof.hard_requirements_satisfied:
        raise ValueError("M336I compilation closure feasibility failed")
    qualification = _object(private / "candidate_qualification.json")
    summary_body = {
        "schema_version": 1,
        "contract_role": "M336I_REHEARSAL_QUALIFICATION_SUMMARY",
        "qualification_report_hash": qualification["report_hash"],
        "binding_manifest_hash": bindings.manifest_hash,
        "selectability_census_hash": census.census_hash,
        "closure_manifest_hash": closure.manifest_hash,
        "closure_feasibility_proof_hash": proof.proof_hash,
        "status": "PASS",
    }
    summary_hash = content_hash(summary_body)
    write_canonical_json(
        closure_root / "qualification_summary.json",
        {**summary_body, "summary_hash": summary_hash},
    )
    return (
        bindings,
        census,
        closure,
        proof,
        qualification["report_hash"],
        summary_hash,
    )


def _build_rehearsal_closure(args) -> None:
    private = args.private_acquisition_output.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("M336I rehearsal closure receipt must be fresh")
    bindings, census, closure, proof, qualification_hash, summary_hash = _build_closure(
        args, private
    )
    body = {
        "schema_version": 1,
        "contract_role": "M336I_REHEARSAL_COMPILATION_CLOSURE",
        "binding_manifest_hash": bindings.manifest_hash,
        "selectability_census_hash": census.census_hash,
        "closure_manifest_hash": closure.manifest_hash,
        "closure_feasibility_proof_hash": proof.proof_hash,
        "qualification_report_hash": qualification_hash,
        "qualification_summary_hash": summary_hash,
        "hard_requirements_satisfied": proof.hard_requirements_satisfied,
        "status": "PASS",
    }
    write_canonical_json(args.output, {**body, "receipt_hash": content_hash(body)})


def _author_rehearsal_spdx(args) -> None:
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336I rehearsal SPDX authority output must be fresh")
    selected = m336f_selected_source_manifest_from_dict(_object(args.selected_manifest))
    _object(args.input_qualification)
    reference = _object(args.frozen_spdx_reference)
    reference_body = dict(reference)
    reference_hash = reference_body.pop("snapshot_manifest_hash", None)
    expected_license_file = f"{args.license_expression}.txt"
    frozen_files = dict(reference.get("files", ()))
    license_path = args.frozen_spdx_reference.parent / expected_license_file
    if (
        content_hash(reference_body) != reference_hash
        or expected_license_file not in frozen_files
        or not license_path.is_file()
        or bytes_hash(license_path.read_bytes()) != frozen_files[expected_license_file]
    ):
        raise ValueError("M336I rehearsal SPDX expression is not frozen")
    roots = tuple(sorted({item.candidate_root for item in selected.files}))
    candidates = []
    decisions = []
    for root in roots:
        policy_body = {
            "family_id": root,
            "pom_license_declarations": [
                [
                    args.license_expression,
                    "repository-owned generated rehearsal fixture",
                    bytes_hash(license_path.read_bytes()),
                ]
            ],
        }
        candidates.append({**policy_body, "policy_hash": content_hash(policy_body)})
        decision_body = {
            "family_id": root,
            "scoped_license_decision": "RESOLVED",
            "scoped_license_expressions": [args.license_expression],
        }
        decisions.append(
            {**decision_body, "decision_hash": content_hash(decision_body)}
        )
    pool_body = {
        "schema_version": 1,
        "contract_role": "M336I_REHEARSAL_SPDX_POLICY",
        "selected_manifest_hash": selected.manifest_hash,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    pool = {**pool_body, "pool_hash": content_hash(pool_body)}
    qualification_body = {
        "schema_version": 1,
        "contract_role": "M336I_REHEARSAL_SPDX_AUTHORITY",
        "selected_manifest_hash": selected.manifest_hash,
        "candidate_pool_hash": pool["pool_hash"],
        "input_qualification_bytes_hash": bytes_hash(
            args.input_qualification.read_bytes()
        ),
        "selected_file_count": selected.file_count,
        "decisions": decisions,
    }
    qualification = {
        **qualification_body,
        "report_hash": content_hash(qualification_body),
    }
    output.mkdir(parents=True)
    write_canonical_json(output / "candidate_pool.json", pool)
    write_canonical_json(output / "qualification_report.json", qualification)


def _select(
    args,
    private,
    worktrees,
    bindings,
    census,
    closure,
    proof,
    qualification_hash,
    summary_hash,
):
    selector_ledger = M336FSelectorLedger(args.selector_ledger, git_worktrees=worktrees)
    selected, selector = select_compilation_closed_sources_once(
        census=census,
        closure_manifest=closure,
        proof=proof,
        bindings=bindings,
        selector_seed="m336i-final-java-freeze-v8-180",
        ledger=selector_ledger,
        qualification_report_hash=qualification_hash,
        qualification_summary_hash=summary_hash,
    )
    selected_path = private / "selected_source_manifest.json"
    selector_path = private / "selector_receipt.json"
    write_canonical_json(selected_path, selected)
    write_canonical_json(selector_path, selector)
    write_canonical_json(
        private / "selector_ledger_receipt.json", selector_ledger.receipt()
    )
    return selected, selector


def _materialize_windows(args, worktrees, bindings, closure, proof, selected, selector):
    receipt = materialize_m336f_selected_source_snapshot(
        sealed_vault_root=args.windows_vault,
        bindings=bindings,
        selected_manifest=selected,
        selector_receipt=selector,
        closure_manifest=closure,
        closure_proof=proof,
        destination=args.windows_selected_snapshot,
        git_worktrees=worktrees,
        public_roots=(
            args.windows_public_production_root,
            args.public_staging_root,
        ),
    )
    path = args.private_acquisition_output / "windows_materialization_receipt.json"
    write_canonical_json(path, receipt)
    return receipt


def _production_request(
    *,
    args,
    platform,
    snapshot,
    javac,
    jdk_hash,
    vault,
    replay,
    output,
    public_staging,
    worktrees,
    authorization,
):
    base = M336HCompilerAwareProductionRequest(
        route_manifest_hash=authorization.route_manifest_hash,
        implementation_identity=authorization.r24_implementation_tree_identity,
        platform_role=platform,
        source_snapshot_private_handle=snapshot,
        javac_private_handle=javac,
        public_jdk_identity_receipt_hash=jdk_hash,
        source_entry_bindings=args.private_acquisition_output
        / "source_entry_binding_manifest.json",
        selected_manifest=args.private_acquisition_output
        / "selected_source_manifest.json",
        selector_receipt=args.private_acquisition_output / "selector_receipt.json",
        closure_manifest=args.private_acquisition_output
        / "compilation-closure"
        / "compilation_closure_manifest.json",
        closure_feasibility_proof=args.private_acquisition_output
        / "compilation-closure"
        / "compilation_closure_feasibility.json",
        sealed_vault=vault,
        private_replay_root=replay,
        public_production_destination=output,
        publication_boundary_contract_hash=authorization.publication_boundary_hash,
        threshold_manifest_hash=authorization.threshold_manifest_hash,
    )
    return M336ICompilerAwareProductionRequest(
        production_request=base,
        frozen_route_manifest=args.frozen_route_manifest,
        frozen_implementation_identity=authorization.r24_implementation_tree_identity,
        frozen_publication_boundary_hash=authorization.publication_boundary_hash,
        frozen_threshold_manifest=args.threshold_manifest,
        public_staging_root=public_staging,
        git_worktrees=worktrees,
    )


def _karina_request(args, authorization, *, action, materialization_hash=None):
    remote = args.karina_private_root.rstrip("/")
    if hasattr(args, "karina_private_capsule"):
        registry = build_m336j_route_registry()
        role = (
            "REMOTE_SELECTED_SOURCE_MATERIALIZER"
            if action == "MATERIALIZE"
            else "REMOTE_COMPILER_AWARE_PRODUCTION_WORKER"
        )
    else:
        registry = build_m336i_final_java_route_registry()
        role = (
            "M336F_SELECTED_SOURCE_MATERIALIZER"
            if action == "MATERIALIZE"
            else "COMPILER_AWARE_PRODUCTION"
        )
    component = next(item for item in registry.components if item.route_role == role)
    return {
        "schema_version": 1,
        "action": action,
        "expected_head": args.supplied_f24_sha,
        "repository": args.karina_repository,
        "vault": f"{remote}/vault-upload/vault",
        "bindings": (
            f"{remote}/inputs-upload/inputs/source_entry_binding_manifest.json"
        ),
        "selected_manifest": (
            f"{remote}/inputs-upload/inputs/selected_source_manifest.json"
        ),
        "selector_receipt": f"{remote}/inputs-upload/inputs/selector_receipt.json",
        "closure_manifest": (
            f"{remote}/inputs-upload/inputs/compilation_closure_manifest.json"
        ),
        "closure_proof": (
            f"{remote}/inputs-upload/inputs/compilation_closure_feasibility.json"
        ),
        "route_manifest": f"{remote}/inputs-upload/inputs/route_manifest.json",
        "threshold_manifest": f"{remote}/inputs-upload/inputs/threshold_manifest.json",
        "portable_vault_manifest": (
            f"{remote}/inputs-upload/inputs/portable_vault_manifest.json"
        ),
        "karina_host_identity_receipt": (
            f"{remote}/inputs-upload/inputs/karina_host_identity_receipt.json"
        ),
        "snapshot": f"{remote}/selected-snapshot",
        "replay_root": f"{remote}/private-replay",
        "production_root": f"{remote}/public-production",
        "public_staging_root": f"{remote}/public-staging-reserved",
        "javac": args.karina_javac,
        "jdk_receipt_hash": authorization.karina_public_jdk_identity_receipt_hash,
        "implementation_identity": authorization.r24_implementation_tree_identity,
        "publication_boundary_hash": authorization.publication_boundary_hash,
        "host_identity_hash": authorization.karina_stable_host_identity_receipt_hash,
        "materialization_receipt_hash": materialization_hash,
        "output": f"{remote}/worker-receipt.json",
        "route_component_binding_hash": component.binding_hash,
        "request_schema_hash": component.request_schema_hash,
        "response_schema_hash": component.response_schema_hash,
    }


def _m336j_private_route(args):
    capsule = load_private_execution_capsule(args.karina_private_capsule)
    public = public_execution_capsule_receipt_from_dict(
        _object(args.karina_public_capsule_receipt)
    )
    dependencies = dependency_manifest_from_dict(
        _object(args.karina_executable_dependency_manifest)
    )
    if (
        capsule.expected_public_receipt_hash != public.receipt_hash
        or public.executable_dependency_manifest_hash != dependencies.manifest_hash
    ):
        raise ValueError("M336J private/public execution capsule binding changed")
    transport = KarinaPrivateSshTransport(
        ssh_executable=args.ssh_executable,
        endpoint=args.karina_worker_endpoint,
        identity_file=args.ssh_key,
        known_hosts_file=args.known_hosts_file,
    )
    return capsule, public, dependencies, transport, build_m336j_route_registry()


def _run_karina_storage_preflight(args):
    _capsule, public, _dependencies, _transport, registry = _m336j_private_route(args)
    component = next(
        item
        for item in registry.components
        if item.route_role == "REMOTE_STORAGE_PREFLIGHT"
    )
    maximum = M336J_DEFAULT_TREE_TRANSFER_LIMITS.maximum_archive_bytes
    request_hash = content_hash(
        (maximum, "QUALIFICATION_12_GIB", public.receipt_hash, component.binding_hash)
    )
    receipt, _component, _public = _invoke_m336j_remote(
        args,
        component_role="REMOTE_STORAGE_PREFLIGHT",
        subcommand="storage-preflight",
        receipt_name="karina-storage-preflight-command.json",
        expected_request_hash=request_hash,
        options=(
            (KarinaRemoteTokenClass.FLAG, "--maximum-transfer-bytes"),
            (KarinaRemoteTokenClass.OPAQUE_ARGUMENT, str(maximum)),
            (KarinaRemoteTokenClass.FLAG, "--qualification-margin"),
            (KarinaRemoteTokenClass.FLAG, "--request-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, request_hash),
            (KarinaRemoteTokenClass.FLAG, "--component-binding-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, component.binding_hash),
        ),
    )
    if (
        receipt.get("required_free_bytes") != 12 * 1024**3
        or receipt.get("available_free_bytes", 0) < receipt["required_free_bytes"]
        or receipt.get("available_free_inodes", 0) < 100_000
    ):
        raise ValueError("M336J Karina storage qualification failed")
    write_canonical_json(args.karina_storage_preflight_receipt, receipt)
    return receipt


def _invoke_m336j_remote(
    args,
    *,
    component_role,
    subcommand,
    receipt_name,
    expected_request_hash,
    payload=b"",
    payload_path=None,
    response_path=None,
    options=(),
    framed=False,
):
    capsule, public, dependencies, transport, registry = _m336j_private_route(args)
    component = next(
        item for item in registry.components if item.route_role == component_role
    )
    remote_script = (
        capsule.repository_checkout / "scripts" / "m336j_karina_execution.py"
    )
    arguments = (
        (KarinaRemoteTokenClass.FLAG, "-B"),
        (KarinaRemoteTokenClass.PRIVATE_PATH, remote_script),
        (KarinaRemoteTokenClass.SUBCOMMAND, subcommand),
        (KarinaRemoteTokenClass.FLAG, "--private-capsule"),
        (
            KarinaRemoteTokenClass.PRIVATE_PATH,
            args.karina_private_capsule_remote,
        ),
        *options,
    )
    if payload_path is not None and payload:
        raise ValueError("M336J remote remote input must be bytes or a file")
    source = (
        Path(payload_path).resolve(strict=True) if payload_path is not None else None
    )
    plan_arguments = {
        "component_id": component.component_id,
        "capsule": capsule,
        "arguments": arguments,
        "expected_capsule_receipt_hash": public.receipt_hash,
    }
    if source is None:
        plan = build_remote_command_plan(**plan_arguments, stdin_payload=payload)
    else:
        plan = build_remote_command_plan(
            **plan_arguments,
            stdin_payload_hash=hash_file(source),
            stdin_payload_size=source.stat().st_size,
        )
    streaming = source is not None or framed
    try:
        if streaming:
            with tempfile.TemporaryDirectory(
                prefix="m336j-ssh-stream-", dir=args.private_acquisition_output.parent
            ) as raw:
                temporary = Path(raw)
                if source is None:
                    source = temporary / "empty.stdin"
                    source.write_bytes(b"")
                output = (
                    Path(response_path).resolve(strict=False)
                    if response_path is not None
                    else temporary / "response.stdout"
                )
                result = invoke_karina_command_streaming(
                    transport=transport,
                    capsule=capsule,
                    plan=plan,
                    dependency_manifest=dependencies,
                    stdin_path=source,
                    stdout_path=output,
                )
                if not framed:
                    response = parse_bound_json_response(
                        result.stdout_path.read_bytes(),
                        request_hash=expected_request_hash,
                        component_binding_hash=component.binding_hash,
                        host_identity_hash=public.host_identity_receipt_hash,
                    )
        else:
            result = invoke_karina_command(
                transport=transport,
                capsule=capsule,
                plan=plan,
                dependency_manifest=dependencies,
                stdin_payload=payload,
            )
            response = parse_bound_json_response(
                result.stdout,
                request_hash=expected_request_hash,
                component_binding_hash=component.binding_hash,
                host_identity_hash=public.host_identity_receipt_hash,
            )
    except subprocess.CalledProcessError as error:
        _write_karina_command_failure_diagnostics(
            args.karina_command_receipt_root, receipt_name, error
        )
        raise
    args.karina_command_receipt_root.mkdir(parents=True, exist_ok=True)
    write_canonical_json(
        args.karina_command_receipt_root / receipt_name,
        result.command_receipt,
    )
    if framed:
        if response_path is None:
            raise ValueError("M336J streamed response needs an external destination")
        return result, component, public
    return response, component, public


def _write_karina_command_failure_diagnostics(
    root: Path, receipt_name: str, error: subprocess.CalledProcessError
) -> None:
    """Persist bounded SSH response bytes under the declared private root."""

    root.mkdir(parents=True, exist_ok=True)
    stem = Path(receipt_name).stem
    stdout = error.stdout if error.stdout is not None else error.output
    for suffix, value in (("stdout", stdout), ("stderr", error.stderr)):
        raw = value if isinstance(value, bytes) else str(value or "").encode("utf-8")
        (root / f"{stem}.{suffix}.log").write_bytes(raw)


def _invoke_karina_worker(args, request, request_name):
    request_path = args.private_acquisition_output / request_name
    role = (
        "REMOTE_SELECTED_SOURCE_MATERIALIZER"
        if request["action"] == "MATERIALIZE"
        else "REMOTE_COMPILER_AWARE_PRODUCTION_WORKER"
    )
    _capsule, public, _dependencies, _transport, registry = _m336j_private_route(args)
    component = next(item for item in registry.components if item.route_role == role)
    body = {
        **request,
        "m336j_execution_capsule_receipt_hash": public.receipt_hash,
        "m336j_component_binding_hash": component.binding_hash,
    }
    request_hash = content_hash(body)
    request_value = {**body, "request_hash": request_hash}
    write_canonical_json(request_path, request_value)
    response, _component, _public = _invoke_m336j_remote(
        args,
        component_role=role,
        subcommand="produce-worker",
        receipt_name=request_name.removesuffix(".json") + "-command.json",
        expected_request_hash=request_hash,
        payload=canonical_json_bytes(request_value),
        options=(
            (KarinaRemoteTokenClass.FLAG, "--request-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, request_hash),
            (KarinaRemoteTokenClass.FLAG, "--component-binding-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, component.binding_hash),
        ),
    )
    worker_receipt = args.private_acquisition_output / (
        request_name.removesuffix(".json") + "-receipt.json"
    )
    write_canonical_json(worker_receipt, response)
    return response


def _upload_karina_tree(args, *, label, source):
    capsule, public, _dependencies, _transport, registry = _m336j_private_route(args)
    remote = args.karina_private_root.rstrip("/")
    prefix = capsule.private_root.as_posix().rstrip("/") + "/"
    if not remote.startswith(prefix):
        raise ValueError("M336J Karina run root is outside private capsule")
    relative = remote.removeprefix(prefix)
    component = next(
        item for item in registry.components if item.route_role == "REMOTE_TREE_UPLOAD"
    )
    limits = M336J_DEFAULT_TREE_TRANSFER_LIMITS
    limit_hash = content_hash(asdict(limits))
    with tempfile.TemporaryDirectory(
        prefix="m336j-tree-upload-", dir=args.private_acquisition_output.parent
    ) as raw:
        transfer_root = Path(raw)
        artifact = write_canonical_tree_archive(
            source,
            transfer_root / f"{label}.zip",
            prefix=label,
            limits=limits,
        )
        content_file_count, content_tree_hash = portable_tree_content_identity(source)
        if content_file_count != artifact.file_count:
            raise ValueError("M336J upload content accounting changed")
        request_hash = content_hash(
            (
                label,
                artifact.archive_hash,
                artifact.archive_size,
                artifact.file_count,
                artifact.portable_tree_hash,
                content_file_count,
                content_tree_hash,
                limit_hash,
                public.receipt_hash,
            )
        )
        response, _binding, _receipt = _invoke_m336j_remote(
            args,
            component_role="REMOTE_TREE_UPLOAD",
            subcommand="receive-tree",
            receipt_name=f"karina-{label}-transfer-command.json",
            expected_request_hash=request_hash,
            payload_path=artifact.private_path,
            options=(
                (KarinaRemoteTokenClass.FLAG, "--relative-destination"),
                (
                    KarinaRemoteTokenClass.PRIVATE_PATH,
                    f"{relative}/{label}-upload",
                ),
                (KarinaRemoteTokenClass.FLAG, "--payload-hash"),
                (KarinaRemoteTokenClass.PUBLIC_IDENTITY, artifact.archive_hash),
                (KarinaRemoteTokenClass.FLAG, "--payload-size"),
                (
                    KarinaRemoteTokenClass.OPAQUE_ARGUMENT,
                    str(artifact.archive_size),
                ),
                (KarinaRemoteTokenClass.FLAG, "--file-count"),
                (KarinaRemoteTokenClass.OPAQUE_ARGUMENT, str(artifact.file_count)),
                (KarinaRemoteTokenClass.FLAG, "--portable-tree-hash"),
                (
                    KarinaRemoteTokenClass.PUBLIC_IDENTITY,
                    artifact.portable_tree_hash,
                ),
                (KarinaRemoteTokenClass.FLAG, "--content-root"),
                (KarinaRemoteTokenClass.PRIVATE_PATH, label),
                (KarinaRemoteTokenClass.FLAG, "--expected-content-file-count"),
                (
                    KarinaRemoteTokenClass.OPAQUE_ARGUMENT,
                    str(content_file_count),
                ),
                (KarinaRemoteTokenClass.FLAG, "--expected-content-tree-hash"),
                (
                    KarinaRemoteTokenClass.PUBLIC_IDENTITY,
                    content_tree_hash,
                ),
                (KarinaRemoteTokenClass.FLAG, "--transfer-limit-hash"),
                (KarinaRemoteTokenClass.PUBLIC_IDENTITY, limit_hash),
                (KarinaRemoteTokenClass.FLAG, "--expected-capsule-receipt-hash"),
                (KarinaRemoteTokenClass.PUBLIC_IDENTITY, public.receipt_hash),
                (KarinaRemoteTokenClass.FLAG, "--request-hash"),
                (KarinaRemoteTokenClass.PUBLIC_IDENTITY, request_hash),
                (KarinaRemoteTokenClass.FLAG, "--component-binding-hash"),
                (KarinaRemoteTokenClass.PUBLIC_IDENTITY, component.binding_hash),
            ),
        )
        if (
            response.get("status") != "PASS"
            or response.get("payload_hash") != artifact.archive_hash
            or response.get("payload_size") != artifact.archive_size
            or response.get("file_count") != artifact.file_count
            or response.get("portable_tree_hash") != artifact.portable_tree_hash
            or response.get("content_file_count") != content_file_count
            or response.get("content_tree_hash") != content_tree_hash
        ):
            raise ValueError("M336J remote tree upload receipt changed")
        write_canonical_json(
            args.private_acquisition_output / f"karina-{label}-transfer-receipt.json",
            response,
        )
    return response


def _prepare_karina(args, authorization, *, vault_already_uploaded=False):
    inputs = args.private_acquisition_output / "karina-inputs"
    inputs.mkdir()
    copies = {
        "source_entry_binding_manifest.json": args.private_acquisition_output
        / "source_entry_binding_manifest.json",
        "candidate_qualification.json": args.private_acquisition_output
        / "candidate_qualification.json",
        "selected_source_manifest.json": args.private_acquisition_output
        / "selected_source_manifest.json",
        "selector_receipt.json": args.private_acquisition_output
        / "selector_receipt.json",
        "compilation_closure_manifest.json": args.private_acquisition_output
        / "compilation-closure"
        / "compilation_closure_manifest.json",
        "compilation_closure_feasibility.json": args.private_acquisition_output
        / "compilation-closure"
        / "compilation_closure_feasibility.json",
        "route_manifest.json": args.frozen_route_manifest,
        "threshold_manifest.json": args.threshold_manifest,
        "karina_host_identity_receipt.json": args.karina_host_identity_receipt,
    }
    for name, source in copies.items():
        shutil.copy2(source, inputs / name)
    vault_manifest = args.private_acquisition_output / "portable_vault_manifest.json"
    shutil.copy2(vault_manifest, inputs / "portable_vault_manifest.json")
    if not vault_already_uploaded:
        _upload_karina_tree(args, label="vault", source=args.windows_vault)
    _upload_karina_tree(args, label="inputs", source=inputs)
    request = _karina_request(args, authorization, action="MATERIALIZE")
    return _invoke_karina_worker(args, request, "karina-materialize-request.json")


def _run_karina_production(args, authorization, materialization, *, run_runtime=True):
    remote = args.karina_private_root.rstrip("/")
    request = _karina_request(
        args,
        authorization,
        action="PRODUCE",
        materialization_hash=materialization["materialization_receipt_hash"],
    )
    worker = _invoke_karina_worker(args, request, "karina-production-request.json")
    local_parent = args.karina_public_production_root.parent
    local_parent.mkdir(parents=True, exist_ok=True)
    if args.karina_public_production_root.exists():
        raise FileExistsError("M336I Karina production copy must be fresh")
    capsule, public, _dependencies, _transport, registry = _m336j_private_route(args)
    prefix = capsule.private_root.as_posix().rstrip("/") + "/"
    if not remote.startswith(prefix):
        raise ValueError("M336J Karina run root is outside private capsule")
    relative = remote.removeprefix(prefix)
    component = next(
        item
        for item in registry.components
        if item.route_role == "REMOTE_TREE_DOWNLOAD"
    )
    request_hash = content_hash((relative, public.receipt_hash, worker["receipt_hash"]))
    limits = M336J_DEFAULT_TREE_TRANSFER_LIMITS
    limit_hash = content_hash(asdict(limits))
    with tempfile.TemporaryDirectory(
        prefix="m336j-tree-download-", dir=local_parent
    ) as raw:
        temporary = Path(raw)
        response_path = temporary / "framed-response.bin"
        result, _binding, _receipt = _invoke_m336j_remote(
            args,
            component_role="REMOTE_TREE_DOWNLOAD",
            subcommand="export-tree",
            receipt_name="karina-production-export-command.json",
            expected_request_hash=request_hash,
            response_path=response_path,
            options=(
                (KarinaRemoteTokenClass.FLAG, "--relative-source"),
                (
                    KarinaRemoteTokenClass.PRIVATE_PATH,
                    f"{relative}/public-production",
                ),
                (KarinaRemoteTokenClass.FLAG, "--transfer-limit-hash"),
                (KarinaRemoteTokenClass.PUBLIC_IDENTITY, limit_hash),
                (
                    KarinaRemoteTokenClass.FLAG,
                    "--expected-capsule-receipt-hash",
                ),
                (KarinaRemoteTokenClass.PUBLIC_IDENTITY, public.receipt_hash),
                (KarinaRemoteTokenClass.FLAG, "--request-hash"),
                (KarinaRemoteTokenClass.PUBLIC_IDENTITY, request_hash),
                (KarinaRemoteTokenClass.FLAG, "--component-binding-hash"),
                (KarinaRemoteTokenClass.PUBLIC_IDENTITY, component.binding_hash),
            ),
            framed=True,
        )
        archive = temporary / "production.zip"
        header = parse_framed_tree_response_file(
            result.stdout_path,
            payload_path=archive,
            request_hash=request_hash,
            component_binding_hash=component.binding_hash,
            host_identity_hash=public.host_identity_receipt_hash,
            limits=limits,
        )
        if header.get("transfer_limit_hash") != limit_hash:
            raise ValueError("M336J production export limit binding changed")
        write_canonical_json(
            args.private_acquisition_output / "karina-production-export-receipt.json",
            header,
        )
        extract_canonical_tree_export_file(
            archive,
            destination=args.karina_public_production_root,
            expected_payload_hash=header["payload_hash"],
            limits=limits,
        )
    replay_component = next(
        item
        for item in registry.components
        if item.route_role == "REMOTE_REPLAY_AND_PACK_VERIFIER"
    )
    replay_request_hash = content_hash(
        (relative, worker["receipt_hash"], replay_component.binding_hash)
    )
    replay, _binding, _receipt = _invoke_m336j_remote(
        args,
        component_role="REMOTE_REPLAY_AND_PACK_VERIFIER",
        subcommand="replay-and-pack-verification",
        receipt_name="karina-replay-command.json",
        expected_request_hash=replay_request_hash,
        options=(
            (KarinaRemoteTokenClass.FLAG, "--relative-pack"),
            (
                KarinaRemoteTokenClass.PRIVATE_PATH,
                f"{relative}/public-production/candidate_pack",
            ),
            (KarinaRemoteTokenClass.FLAG, "--relative-replay-receipt"),
            (
                KarinaRemoteTokenClass.PRIVATE_PATH,
                f"{relative}/public-production/sealed_source_replay_receipt.json",
            ),
            (KarinaRemoteTokenClass.FLAG, "--request-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, replay_request_hash),
            (KarinaRemoteTokenClass.FLAG, "--component-binding-hash"),
            (
                KarinaRemoteTokenClass.PUBLIC_IDENTITY,
                replay_component.binding_hash,
            ),
        ),
    )
    write_canonical_json(
        args.private_acquisition_output / "karina-replay-receipt.json", replay
    )
    if run_runtime:
        _run_karina_runtime(args, worker=worker, replay=replay)
    return worker


def _run_karina_runtime(args, *, worker=None, replay=None):
    remote = args.karina_private_root.rstrip("/")
    if worker is None:
        worker = _object(
            args.private_acquisition_output / "karina-production-request-receipt.json"
        )
    if replay is None:
        replay = _object(args.private_acquisition_output / "karina-replay-receipt.json")
    capsule, _public, _dependencies, _transport, registry = _m336j_private_route(args)
    prefix = capsule.private_root.as_posix().rstrip("/") + "/"
    if not remote.startswith(prefix):
        raise ValueError("M336J Karina run root is outside private capsule")
    relative = remote.removeprefix(prefix)
    runtime_component = next(
        item
        for item in registry.components
        if item.route_role == "REMOTE_INSTALLED_RUNTIME"
    )
    runtime_request_hash = content_hash(
        (relative, replay["receipt_hash"], runtime_component.binding_hash)
    )
    runtime, _binding, _receipt = _invoke_m336j_remote(
        args,
        component_role="REMOTE_INSTALLED_RUNTIME",
        subcommand="installed-runtime",
        receipt_name="karina-runtime-command.json",
        expected_request_hash=runtime_request_hash,
        options=(
            (KarinaRemoteTokenClass.FLAG, "--relative-pack"),
            (
                KarinaRemoteTokenClass.PRIVATE_PATH,
                f"{relative}/public-production/candidate_pack",
            ),
            (KarinaRemoteTokenClass.FLAG, "--request-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, runtime_request_hash),
            (KarinaRemoteTokenClass.FLAG, "--component-binding-hash"),
            (
                KarinaRemoteTokenClass.PUBLIC_IDENTITY,
                runtime_component.binding_hash,
            ),
        ),
    )
    write_canonical_json(
        args.private_acquisition_output / "karina-runtime-receipt.json", runtime
    )
    return runtime


def _produce_worker(args) -> None:
    request = _object(args.request)
    claimed = request.pop("request_hash", None)
    if content_hash(request) != claimed or request.pop("schema_version", None) != 1:
        raise ValueError("M336I Karina worker request hash/schema mismatch")
    expected_fields = {
        "action",
        "expected_head",
        "repository",
        "vault",
        "bindings",
        "selected_manifest",
        "selector_receipt",
        "closure_manifest",
        "closure_proof",
        "route_manifest",
        "threshold_manifest",
        "portable_vault_manifest",
        "karina_host_identity_receipt",
        "snapshot",
        "replay_root",
        "production_root",
        "public_staging_root",
        "javac",
        "jdk_receipt_hash",
        "implementation_identity",
        "publication_boundary_hash",
        "host_identity_hash",
        "materialization_receipt_hash",
        "output",
        "route_component_binding_hash",
        "request_schema_hash",
        "response_schema_hash",
    }
    if set(request) != expected_fields:
        raise ValueError("M336I Karina worker request fields changed")
    registry = build_m336i_final_java_route_registry()
    route_manifest = build_m336i_final_java_route_manifest(registry)
    frozen_route = _object(Path(request["route_manifest"]))
    if getattr(args, "m336j_mode", False):
        m336j_registry = build_m336j_route_registry()
        registry = m336j_registry
        route_manifest = build_m336j_route_manifest(
            m336j_registry,
            execution_capsule_public_receipt_hash=frozen_route[
                "execution_capsule_public_receipt_hash"
            ],
            remote_command_renderer_hash=frozen_route["remote_command_renderer_hash"],
            executable_dependency_manifest_hash=frozen_route[
                "executable_dependency_manifest_hash"
            ],
            minimal_environment_policy_hash=frozen_route[
                "minimal_environment_policy_hash"
            ],
        )
    if getattr(args, "m336j_mode", False):
        role = (
            "REMOTE_SELECTED_SOURCE_MATERIALIZER"
            if request["action"] == "MATERIALIZE"
            else "REMOTE_COMPILER_AWARE_PRODUCTION_WORKER"
        )
    else:
        role = (
            "M336F_SELECTED_SOURCE_MATERIALIZER"
            if request["action"] == "MATERIALIZE"
            else "COMPILER_AWARE_PRODUCTION"
        )
    component = next(item for item in registry.components if item.route_role == role)
    host_identity = _object(Path(request["karina_host_identity_receipt"]))
    host_body = dict(host_identity)
    host_receipt_hash = host_body.pop("receipt_hash", None)
    if (
        request["route_component_binding_hash"] != component.binding_hash
        or request["request_schema_hash"] != component.request_schema_hash
        or request["response_schema_hash"] != component.response_schema_hash
        or frozen_route != json.loads(canonical_json(route_manifest))
        or content_hash(host_body) != host_receipt_hash
        or host_receipt_hash != request["host_identity_hash"]
        or host_identity.get("public_jdk_identity_receipt_hash")
        != request["jdk_receipt_hash"]
    ):
        raise ValueError("M336I Karina worker authority binding changed")
    repository = Path(request["repository"]).resolve(strict=True)
    git_executable = Path(args.git_executable).resolve(strict=True)
    head = _run(
        (str(git_executable), "rev-parse", "HEAD^{commit}"), cwd=repository
    ).strip()
    status = _run((str(git_executable), "status", "--porcelain=v1"), cwd=repository)
    if head != request["expected_head"] or status:
        raise ValueError("M336I Karina worker is not clean exact-F24")
    vault = Path(request["vault"])
    manifest = portable_vault_manifest_from_dict(
        _object(Path(request["portable_vault_manifest"]))
    )
    verify_portable_vault_manifest(vault, manifest)
    bindings = source_entry_binding_manifest_from_dict(
        _object(Path(request["bindings"]))
    )
    selected = m336f_selected_source_manifest_from_dict(
        _object(Path(request["selected_manifest"]))
    )
    selector = m336f_selector_receipt_from_dict(
        _object(Path(request["selector_receipt"]))
    )
    closure = java_compilation_closure_manifest_from_dict(
        _object(Path(request["closure_manifest"]))
    )
    proof = java_compilation_closure_feasibility_proof_from_dict(
        _object(Path(request["closure_proof"]))
    )
    if request["action"] == "MATERIALIZE":
        materialized = materialize_m336f_selected_source_snapshot(
            sealed_vault_root=vault,
            bindings=bindings,
            selected_manifest=selected,
            selector_receipt=selector,
            closure_manifest=closure,
            closure_proof=proof,
            destination=Path(request["snapshot"]),
            git_worktrees=(repository,),
            public_roots=(
                Path(request["production_root"]),
                Path(request["public_staging_root"]),
            ),
        )
        body = {
            "schema_version": 1,
            "host_identity_hash": request["host_identity_hash"],
            "portable_vault_tree_hash": manifest.portable_tree_hash,
            "physical_source_difference_count": 0,
            "portable_tree_difference_count": 0,
            "materialization_receipt_hash": materialized.receipt_hash,
            "route_component_binding_hash": request["route_component_binding_hash"],
            "response_schema_hash": request["response_schema_hash"],
            "status": "PASS",
        }
        write_canonical_json(
            Path(request["output"]), {**body, "receipt_hash": content_hash(body)}
        )
        return
    if request["action"] != "PRODUCE" or not Path(request["snapshot"]).is_dir():
        raise ValueError("M336I Karina worker action/state is invalid")
    base = M336HCompilerAwareProductionRequest(
        route_manifest_hash=_object(Path(request["route_manifest"]))["manifest_hash"],
        implementation_identity=request["implementation_identity"],
        platform_role="KARINA",
        source_snapshot_private_handle=Path(request["snapshot"]),
        javac_private_handle=Path(request["javac"]),
        public_jdk_identity_receipt_hash=request["jdk_receipt_hash"],
        source_entry_bindings=Path(request["bindings"]),
        selected_manifest=Path(request["selected_manifest"]),
        selector_receipt=Path(request["selector_receipt"]),
        closure_manifest=Path(request["closure_manifest"]),
        closure_feasibility_proof=Path(request["closure_proof"]),
        sealed_vault=vault,
        private_replay_root=Path(request["replay_root"]),
        public_production_destination=Path(request["production_root"]),
        publication_boundary_contract_hash=request["publication_boundary_hash"],
        threshold_manifest_hash=_object(Path(request["threshold_manifest"]))[
            "threshold_manifest_hash"
        ],
    )
    wrapped = M336ICompilerAwareProductionRequest(
        production_request=base,
        frozen_route_manifest=Path(request["route_manifest"]),
        frozen_implementation_identity=request["implementation_identity"],
        frozen_publication_boundary_hash=request["publication_boundary_hash"],
        frozen_threshold_manifest=Path(request["threshold_manifest"]),
        public_staging_root=Path(request["public_staging_root"]),
        git_worktrees=(repository,),
    )
    response, seal = run_m336i_compiler_aware_production(wrapped)
    write_canonical_json(
        Path(request["production_root"]) / "m336i_production_seal.json", seal
    )
    body = {
        "schema_version": 1,
        "host_identity_hash": request["host_identity_hash"],
        "portable_vault_tree_hash": manifest.portable_tree_hash,
        "physical_source_difference_count": 0,
        "portable_tree_difference_count": 0,
        "materialization_receipt_hash": request["materialization_receipt_hash"],
        "production_response_hash": response.response_hash,
        "production_seal_hash": seal.seal_hash,
        "route_component_binding_hash": request["route_component_binding_hash"],
        "response_schema_hash": request["response_schema_hash"],
        "status": "PASS",
    }
    write_canonical_json(
        Path(request["output"]), {**body, "receipt_hash": content_hash(body)}
    )


def _author_goldens(args) -> Path:
    output = args.independent_evaluator_root / "oracle"
    source_input = args.independent_evaluator_root / "sealed-vault-source-input"
    source_input.mkdir(parents=True)
    _copy_selected_source_authority(
        vault=args.windows_vault,
        bindings_path=args.private_acquisition_output
        / "source_entry_binding_manifest.json",
        selected_path=args.private_acquisition_output / "selected_source_manifest.json",
        destination=source_input,
    )
    _invoke_golden_oracle(
        corpus=source_input,
        output=output,
        javac=args.windows_javac,
        production_root=args.windows_public_production_root,
        sealing_ref=args.supplied_f24_sha,
    )
    return output / "semantic_goldens.json"


def _copy_selected_source_authority(
    *, vault: Path, bindings_path: Path, selected_path: Path, destination: Path
) -> None:
    bindings = source_entry_binding_manifest_from_dict(_object(bindings_path))
    selected = m336f_selected_source_manifest_from_dict(_object(selected_path))
    binding_by_unit = {item.selected_path: item for item in bindings.bindings}
    for item in selected.files:
        binding = binding_by_unit[item.selected_path]
        source = vault.joinpath(*binding.vault_path.split("/"))
        target = destination.joinpath(*item.selected_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _invoke_golden_oracle(
    *, corpus: Path, output: Path, javac: Path, production_root: Path, sealing_ref: str
) -> None:
    commitment = _object(
        production_root / "candidate_pack" / "java_replay_commitment.json"
    )
    java = javac.with_name(
        "java.exe" if javac.name.casefold().endswith(".exe") else "java"
    )
    _run(
        (
            sys.executable,
            str(Path(__file__).with_name("m343_author_semantic_goldens.py")),
            "--corpus",
            str(corpus),
            "--helper",
            str(
                Path(__file__).resolve().parents[1]
                / "tools/m343_java_oracle/JavaSemanticProposalOracle.java"
            ),
            "--javac",
            str(javac),
            "--java",
            str(java),
            "--output",
            str(output),
            "--parser-common-hash",
            commitment["parser_artifact_manifest_hash"],
            "--evidence-policy-hash",
            commitment["evidence_policy_hash"],
            "--authority-id",
            "m336i-independent-post-seal-evaluator",
            "--sealing-ref",
            sealing_ref,
            "--authority-purpose",
            "post-seal-final-outcome-a-evaluation",
            "--config-id",
            "m336i.independent-final-evaluation.v1",
            "--diagnostic-scope-v2",
        )
    )


def _author_rehearsal_goldens(args) -> None:
    root = args.output.resolve(strict=False)
    if root.exists():
        raise FileExistsError("M336I rehearsal golden authority output must be fresh")
    source_input = root / "sealed-vault-source-input"
    oracle = root / "oracle"
    source_input.mkdir(parents=True)
    _copy_selected_source_authority(
        vault=args.sealed_vault,
        bindings_path=args.bindings,
        selected_path=args.selected_manifest,
        destination=source_input,
    )
    _invoke_golden_oracle(
        corpus=source_input,
        output=oracle,
        javac=args.javac,
        production_root=args.production_root,
        sealing_ref=args.sealing_ref,
    )
    print(oracle / "semantic_goldens.json")


def _stage_public(args, evaluation, route_receipt, acquisition_receipt):
    staging = args.public_staging_root
    if staging.exists():
        raise FileExistsError("M336I public staging must be fresh")
    candidate = staging / "candidate-pack"
    installed = staging / "installed-pack"
    staging.mkdir(parents=True)
    shutil.copytree(args.windows_public_production_root / "candidate_pack", candidate)
    shutil.copytree(candidate, installed)
    receipts = {
        "acquisition_receipt.json": acquisition_receipt,
        "windows_production_seal.json": _object(
            args.windows_public_production_root / "m336i_production_seal.json"
        ),
        "karina_production_seal.json": _object(
            args.karina_public_production_root / "m336i_production_seal.json"
        ),
        "independent_evaluation.json": evaluation,
        "pre_staging_route_state_receipt.json": route_receipt,
    }
    for name, value in receipts.items():
        write_canonical_json(staging / name, value)
    roles = {}
    for path in staging.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(staging).as_posix()
        roles[relative] = (
            ArtifactConfidentialityRole.PUBLIC_DERIVED_PACK
            if relative.startswith(("candidate-pack/", "installed-pack/"))
            else ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT
        )
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
    return validate_public_staging(
        staging_root=staging,
        artifact_roles=roles,
        sealed_vault_root=args.windows_vault,
        candidate_pack_relative_path="candidate-pack",
        installed_pack_relative_path="installed-pack",
        prospective_git_tree_hash=content_hash(rows),
        prospective_git_entries=rows,
    )


def _build_final_acquisition_request(
    *,
    args,
    repository: Path,
    authorization,
    v2_authorization,
    v2_freeze_manifest,
    v2_lineage_policy,
    v2_git_receipt,
) -> M336IFinalAcquisitionRequest:
    return M336IFinalAcquisitionRequest(
        repository=repository,
        supplied_f24_sha=args.supplied_f24_sha,
        authorization=authorization,
        candidate_pool=args.candidate_pool,
        acquisition_policy=args.acquisition_policy,
        denylist=args.denylist,
        authority_root=args.authority_root,
        authority_statement=args.authority_statement,
        frozen_route_registry=args.frozen_route_registry,
        frozen_route_manifest=args.frozen_route_manifest,
        selector_policy=args.selector_policy,
        threshold_manifest=args.threshold_manifest,
        publication_boundary_contract=args.publication_boundary_contract,
        public_artifact_contract=args.public_artifact_contract,
        compiler_jdk_identities=args.compiler_jdk_identities,
        karina_host_identity_receipt=args.karina_host_identity_receipt,
        acquisition_ledger=args.acquisition_ledger,
        vault_destination=args.windows_vault,
        private_acquisition_output=args.private_acquisition_output,
        public_receipt_output=args.public_acquisition_receipt,
        public_staging_root=args.public_staging_root,
        unused_selected_source_output=args.private_acquisition_output.parent
        / "unused-m336e-selection",
        platform_role="WINDOWS",
        git_executable=args.git_executable,
        v2_authorization=v2_authorization,
        v2_freeze_manifest=v2_freeze_manifest,
        v2_lineage_policy=v2_lineage_policy,
        v2_git_receipt=v2_git_receipt,
    )


def _final(args, *, rehearsal_acquisition_provider=None) -> None:
    repository = args.repository.resolve(strict=True)
    worktrees = _worktrees(repository, args.git_executable)
    raw_authorization = _object(args.frozen_authorization)
    is_m336j_v2 = raw_authorization.get("contract_role") == (
        "M336J_FINAL_ACQUISITION_AUTHORIZATION_V2"
    )
    if is_m336j_v2:
        v2_authorization = load_m336j_final_authorization_v2(raw_authorization)
        authorization = m336j_final_authorization_v2_to_legacy(v2_authorization)
        v2_freeze_manifest = load_m336j_final_freeze_manifest_v2(
            args.frozen_authorization.with_name("freeze_manifest_v2.json")
        )
        verify_m336j_authorization_manifest_cross_bindings_v2(
            v2_authorization, v2_freeze_manifest
        )
        v2_git_receipt = build_m336j_git_executable_receipt_v2(
            args.git_executable,
            execution_capsule_public_receipt_hash=(
                v2_authorization.execution_capsule_public_receipt_hash
            ),
            environment_identity_hash=(
                v2_authorization.python_environment_manifest_hash
            ),
        )
        v2_lineage_policy = build_m336j_final_freeze_lineage_policy_v2(
            exact_r26_sha=v2_authorization.exact_r26_sha,
            exact_q26_sha=v2_authorization.exact_q26_sha,
            exact_f26_sha=args.supplied_f24_sha,
        )
        verify_m336j_final_freeze_lineage_v2(
            repository,
            args.git_executable,
            v2_lineage_policy,
            v2_git_receipt,
        )
    else:
        v2_authorization = None
        v2_freeze_manifest = None
        v2_git_receipt = None
        v2_lineage_policy = None
        authorization = final_acquisition_authorization_from_dict(raw_authorization)
    is_m336j = authorization.branch_ref.endswith(
        "/exp/stage3-m336j-hermetic-karina-final-java-v9"
    )
    if rehearsal_acquisition_provider is not None and (
        not is_m336j_v2 or authorization.acquisition_mode != "REHEARSAL"
    ):
        raise ValueError(
            "M336J rehearsal provider is restricted to V2 REHEARSAL authorization"
        )
    if is_m336j:
        from ai_brain.stage3.acquisition.m336j_freeze import (
            verify_m336j_final_acquisition_authorization,
        )

        verify_m336j_final_acquisition_authorization(authorization)
    _validate_final_controller_inputs(
        args,
        authorization,
        worktrees,
        v2_freeze_manifest=v2_freeze_manifest,
        expected_acquisition_mode=(
            "REHEARSAL" if rehearsal_acquisition_provider is not None else "FINAL"
        ),
    )
    acquisition_request = _build_final_acquisition_request(
        args=args,
        repository=repository,
        authorization=authorization,
        v2_authorization=v2_authorization,
        v2_freeze_manifest=v2_freeze_manifest,
        v2_lineage_policy=v2_lineage_policy,
        v2_git_receipt=v2_git_receipt,
    )
    acquisition_context = validate_m336i_final_acquisition_request_before_side_effects(
        acquisition_request
    )
    active_authorization = v2_authorization or authorization
    context_values = (
        active_authorization.authorization_hash,
        args.supplied_f24_sha,
    )
    if is_m336j_v2:
        context_values += (active_authorization.acquisition_run_id,)
    context = acquisition_context if is_m336j_v2 else content_hash(context_values)
    state = M336IRouteStateLedger(args.route_state_ledger, git_worktrees=worktrees)
    state.advance(
        "INITIAL",
        context_hash=context,
        operation_receipt_hash=active_authorization.authorization_hash,
    )
    if is_m336j or is_m336j_v2:
        frozen_route = _object(args.frozen_route_manifest)
        registry = build_m336j_route_registry()
        manifest = build_m336j_route_manifest(
            registry,
            execution_capsule_public_receipt_hash=frozen_route[
                "execution_capsule_public_receipt_hash"
            ],
            remote_command_renderer_hash=frozen_route["remote_command_renderer_hash"],
            executable_dependency_manifest_hash=frozen_route[
                "executable_dependency_manifest_hash"
            ],
            minimal_environment_policy_hash=frozen_route[
                "minimal_environment_policy_hash"
            ],
        )
    else:
        registry = build_m336i_final_java_route_registry()
        manifest = build_m336i_final_java_route_manifest(registry)
    state.advance(
        "PREFLIGHT_PASSED",
        context_hash=context,
        operation_receipt_hash=manifest.manifest_hash,
    )
    if is_m336j_v2 and not acquisition_context:
        raise ValueError("M336J V2 acquisition preflight context is missing")
    acquisition_state_names = {
        "AUTHORIZATION_VALIDATED": "AUTHORIZATION_VALIDATED",
        "ACQUISITION_RESERVED": "ACQUISITION_RESERVED",
        "ACQUISITION_COMPLETED": "ACQUISITION_COMPLETED",
    }

    def advance_acquisition_state(event_name, event_hash):
        route_name = acquisition_state_names.get(event_name)
        if route_name is not None:
            state.advance(
                route_name,
                context_hash=context,
                operation_receipt_hash=event_hash,
            )

    provider_options = (
        {}
        if rehearsal_acquisition_provider is None
        else {
            "maven_provider": rehearsal_acquisition_provider.maven_provider,
            "scm_provider": rehearsal_acquisition_provider.scm_provider,
            "acquire_one": rehearsal_acquisition_provider.acquire_one,
        }
    )
    acquisition = run_m336i_frozen_final_acquisition(
        acquisition_request,
        event_callback=advance_acquisition_state,
        **provider_options,
    )
    acquisition_ledger = M336IFinalAcquisitionLedger(
        args.acquisition_ledger, git_worktrees=worktrees
    )
    for route_name, receipt_hash in (
        ("ACQUISITION_INPUT_BOUND", acquisition.receipt_hash),
        ("VAULT_PORTABILITY_VERIFIED", acquisition.portable_vault_manifest_hash),
        ("QUALIFICATION_SEALED", acquisition.qualification_report_hash),
        ("CENSUS_SEALED", acquisition.selectability_census_hash),
    ):
        state.advance(
            route_name,
            context_hash=context,
            operation_receipt_hash=receipt_hash,
        )
    (
        bindings,
        census,
        closure,
        proof,
        qualification_hash,
        qualification_summary_hash,
    ) = _build_closure(
        args,
        args.private_acquisition_output,
    )
    for route_name, receipt_hash in (
        ("COMPILATION_CLOSURE_SEALED", closure.manifest_hash),
        ("CLOSURE_FEASIBILITY_PASSED", proof.proof_hash),
    ):
        state.advance(
            route_name,
            context_hash=context,
            operation_receipt_hash=receipt_hash,
        )
    state.advance(
        "SELECTOR_RESERVED",
        context_hash=context,
        operation_receipt_hash=proof.proof_hash,
    )
    selected, selector = _select(
        args,
        args.private_acquisition_output,
        worktrees,
        bindings,
        census,
        closure,
        proof,
        qualification_hash,
        qualification_summary_hash,
    )
    state.advance(
        "SELECTION_COMPLETED",
        context_hash=context,
        operation_receipt_hash=selector.receipt_hash,
    )
    windows_materialization = _materialize_windows(
        args, worktrees, bindings, closure, proof, selected, selector
    )
    state.advance(
        "SOURCE_SNAPSHOT_MATERIALIZED_WINDOWS",
        context_hash=context,
        operation_receipt_hash=windows_materialization.receipt_hash,
    )
    karina_materialization = _prepare_karina(args, authorization)
    state.advance(
        "SOURCE_SNAPSHOT_MATERIALIZED_KARINA",
        context_hash=context,
        operation_receipt_hash=karina_materialization["materialization_receipt_hash"],
    )
    windows_request = _production_request(
        args=args,
        platform="WINDOWS",
        snapshot=args.windows_selected_snapshot,
        javac=args.windows_javac,
        jdk_hash=authorization.windows_public_jdk_identity_receipt_hash,
        vault=args.windows_vault,
        replay=args.windows_private_replay_root,
        output=args.windows_public_production_root,
        public_staging=args.public_staging_root,
        worktrees=worktrees,
        authorization=authorization,
    )
    windows_response, windows_seal = run_m336i_compiler_aware_production(
        windows_request
    )
    write_canonical_json(
        args.windows_public_production_root / "m336i_production_seal.json",
        windows_seal,
    )
    _run_karina_production(args, authorization, karina_materialization)
    karina_seal = _object(
        args.karina_public_production_root / "m336i_production_seal.json"
    )
    state.advance(
        "WINDOWS_PRODUCTION_SEALED",
        context_hash=context,
        operation_receipt_hash=windows_seal.seal_hash,
    )
    state.advance(
        "KARINA_PRODUCTION_SEALED",
        context_hash=context,
        operation_receipt_hash=karina_seal["seal_hash"],
    )
    pack = verify_java_public_candidate_pack(
        args.windows_public_production_root / "candidate_pack"
    )
    karina_pack = verify_java_public_candidate_pack(
        args.karina_public_production_root / "candidate_pack"
    )
    if (
        pack.candidate_pack_content_hash != karina_pack.candidate_pack_content_hash
        or pack.candidate_pack_tree_hash != karina_pack.candidate_pack_tree_hash
    ):
        raise ValueError("M336I platform-neutral candidate packs differ")
    state.advance(
        "CROSS_PLATFORM_PRODUCTION_VERIFIED",
        context_hash=context,
        operation_receipt_hash=content_hash(
            (windows_seal.seal_hash, karina_seal["seal_hash"])
        ),
    )
    state.advance(
        "PUBLIC_PACK_VERIFIED",
        context_hash=context,
        operation_receipt_hash=pack.receipt_hash,
    )
    for name, root in (
        ("SEALED_REPLAY_VERIFIED_WINDOWS", args.windows_public_production_root),
        ("SEALED_REPLAY_VERIFIED_KARINA", args.karina_public_production_root),
    ):
        replay = _object(root / "sealed_source_replay_receipt.json")
        state.advance(
            name,
            context_hash=context,
            operation_receipt_hash=replay["receipt_hash"],
        )
    if is_m336j_v2:
        evaluator_ledger = M336JEvaluatorLedgerV2(
            args.evaluator_ledger, git_worktrees=worktrees
        )
        evaluator_reservation = reserve_m336j_evaluator_v2(
            M336JEvaluatorReservationInputV2(
                windows_production_seal=(
                    args.windows_public_production_root / "m336i_production_seal.json"
                ),
                karina_production_seal=(
                    args.karina_public_production_root / "m336i_production_seal.json"
                ),
                selected_manifest=(
                    args.private_acquisition_output / "selected_source_manifest.json"
                ),
                sealed_vault=args.windows_vault,
                evaluator_implementation_hash=independent_evaluator_identity(),
                evaluator_jdk_identity_hash=(
                    active_authorization.windows_public_jdk_identity_receipt_hash
                ),
                golden_output_destination=(
                    args.independent_evaluator_root / "semantic_goldens.json"
                ),
                evaluation_run_id="m336j3.final-java.independent-evaluation.v2",
            ),
            evaluator_ledger,
        )
        state.advance(
            "EVALUATOR_RESERVED",
            context_hash=context,
            operation_receipt_hash=evaluator_reservation.receipt_hash,
        )
        advance_m336j_evaluator_v2(
            evaluator_ledger,
            "INDEPENDENT_GOLDEN_GENERATION_STARTED",
            context_hash=evaluator_reservation.context_hash,
            operation_hash=evaluator_reservation.receipt_hash,
        )
        goldens = _author_goldens(args)
        advance_m336j_evaluator_v2(
            evaluator_ledger,
            "INDEPENDENT_GOLDEN_GENERATION_COMPLETED",
            context_hash=evaluator_reservation.context_hash,
            operation_hash=bytes_hash(goldens.read_bytes()),
        )
        evaluator_context_hash = evaluator_reservation.context_hash
    else:
        goldens = _author_goldens(args)
        state.advance(
            "EVALUATOR_RESERVED",
            context_hash=context,
            operation_receipt_hash=content_hash(goldens.read_bytes()),
        )
        evaluator_context_hash = None
    evaluation = run_m336i_independent_java_evaluation(
        M336IIndependentEvaluationRequest(
            route_manifest=args.frozen_route_manifest,
            threshold_manifest=args.threshold_manifest,
            windows_production_seal=args.windows_public_production_root
            / "m336i_production_seal.json",
            karina_production_seal=args.karina_public_production_root
            / "m336i_production_seal.json",
            windows_production_output=args.windows_public_production_root
            / "production_output.json",
            karina_production_output=args.karina_public_production_root
            / "production_output.json",
            windows_field_evidence_manifest=args.windows_public_production_root
            / "field_evidence_manifest.json",
            karina_field_evidence_manifest=args.karina_public_production_root
            / "field_evidence_manifest.json",
            public_candidate_pack=args.windows_public_production_root
            / "candidate_pack",
            windows_replay_receipt=args.windows_public_production_root
            / "sealed_source_replay_receipt.json",
            karina_replay_receipt=args.karina_public_production_root
            / "sealed_source_replay_receipt.json",
            independently_authored_semantic_goldens=goldens,
            external_sealed_vault=args.windows_vault,
            source_entry_bindings=args.private_acquisition_output
            / "source_entry_binding_manifest.json",
            candidate_pool=args.candidate_pool,
            qualification_report=args.private_acquisition_output
            / "candidate_qualification.json",
            selected_manifest=args.private_acquisition_output
            / "selected_source_manifest.json",
            frozen_spdx_reference=args.frozen_spdx_reference,
            evaluator_ledger=args.evaluator_ledger,
            git_worktrees=worktrees,
            evaluator_context_hash=evaluator_context_hash,
            evaluator_pre_reserved=is_m336j_v2,
        )
    )
    evaluation_path = (
        args.windows_public_production_root / "m336i_independent_evaluation.json"
    )
    write_canonical_json(evaluation_path, evaluation)
    state.advance(
        "EVALUATION_COMPLETED",
        context_hash=context,
        operation_receipt_hash=evaluation.result_hash,
    )
    staging_manifest, staging_receipt = _stage_public(
        args, evaluation, state.receipt(), acquisition
    )
    write_canonical_json(
        args.windows_public_production_root / "public_staging_manifest.json",
        staging_manifest,
    )
    write_canonical_json(
        args.windows_public_production_root / "public_staging_receipt.json",
        staging_receipt,
    )
    state.advance(
        "PUBLIC_STAGING_VALIDATED",
        context_hash=context,
        operation_receipt_hash=staging_receipt.receipt_hash,
    )
    state.advance(
        "OUTCOME_A_READY",
        context_hash=context,
        operation_receipt_hash=evaluation.result_hash,
    )
    result_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336I_FINAL_ROUTE_RECEIPT",
        "status": "OUTCOME A",
        "f24_sha": args.supplied_f24_sha,
        "acquisition_receipt_hash": acquisition.receipt_hash,
        "acquisition_ledger_receipt_hash": acquisition_ledger.receipt().receipt_hash,
        "route_state_ledger_receipt_hash": state.receipt().receipt_hash,
        "route_final_state": state.receipt().final_state,
        "selected_manifest_hash": selected.manifest_hash,
        "selector_receipt_hash": selector.receipt_hash,
        "windows_production_response_hash": windows_response.response_hash,
        "windows_production_seal_hash": windows_seal.seal_hash,
        "karina_production_seal_hash": karina_seal["seal_hash"],
        "candidate_pack_content_hash": pack.candidate_pack_content_hash,
        "candidate_pack_tree_hash": pack.candidate_pack_tree_hash,
        "independent_evaluation_hash": evaluation.result_hash,
        "public_staging_receipt_hash": staging_receipt.receipt_hash,
    }
    result = {**result_body, "receipt_hash": content_hash(result_body)}
    write_canonical_json(args.final_receipt, result)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


def _write_final_failure_receipt(args, error: Exception) -> None:
    if args.final_receipt.exists():
        return
    worktrees = _worktrees(args.repository.resolve(strict=True), args.git_executable)
    acquisition = M336IFinalAcquisitionLedger(
        args.acquisition_ledger, git_worktrees=worktrees
    ).receipt()
    route = M336IRouteStateLedger(
        args.route_state_ledger, git_worktrees=worktrees
    ).receipt()
    selector = M336FSelectorLedger(
        args.selector_ledger, git_worktrees=worktrees
    ).receipt()
    raw_authorization = _object(args.frozen_authorization)
    if raw_authorization.get("contract_role") == (
        "M336J_FINAL_ACQUISITION_AUTHORIZATION_V2"
    ):
        evaluator_event_names = tuple(
            item.event
            for item in M336JEvaluatorLedgerV2(
                args.evaluator_ledger, git_worktrees=worktrees
            ).events()
        )
        evaluator_completion_name = "INDEPENDENT_EVALUATION_COMPLETED"
    else:
        evaluator_event_names = tuple(
            item["event"]
            for item in M336HEvaluatorLedger(
                args.evaluator_ledger, git_worktrees=worktrees
            ).events()
        )
        evaluator_completion_name = "EVALUATOR_COMPLETED"
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336I_OUTCOME_C_RECEIPT",
        "status": "OUTCOME C — BLOCKED",
        "failure_class": type(error).__name__,
        "failure_reason_hash": content_hash((type(error).__name__, str(error))),
        "acquisition_ledger_receipt_hash": acquisition.receipt_hash,
        "acquisition_reservation_count": acquisition.acquisition_reservation_count,
        "acquisition_invocation_count": acquisition.acquisition_start_count,
        "acquisition_rerun_count": acquisition.acquisition_rerun_count,
        "route_state_ledger_receipt_hash": route.receipt_hash,
        "route_final_state": route.final_state,
        "selector_reservation_count": selector["selector_reservation_count"],
        "selector_invocation_count": selector["selector_invocation_count"],
        "selector_rerun_count": selector["selector_rerun_count"],
        "evaluator_reservation_count": sum(
            item == "EVALUATOR_RESERVED" for item in evaluator_event_names
        ),
        "evaluator_invocation_count": sum(
            item == evaluator_completion_name for item in evaluator_event_names
        ),
    }
    args.final_receipt.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(
        args.final_receipt, {**body, "receipt_hash": content_hash(body)}
    )


def _run(command, *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        tuple(str(item) for item in command),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _validate_final_controller_inputs(
    args,
    authorization,
    worktrees,
    *,
    v2_freeze_manifest=None,
    expected_acquisition_mode: str = "FINAL",
) -> None:
    if authorization.acquisition_mode != expected_acquisition_mode:
        raise ValueError(
            "M336I final controller authorization mode differs from execution mode"
        )
    is_m336j_legacy = authorization.branch_ref.endswith(
        "/exp/stage3-m336j-hermetic-karina-final-java-v9"
    )
    is_m336j_v2 = authorization.branch_ref.endswith(
        "/exp/stage3-m336j3-final-freeze-handshake-v10"
    )
    spdx_binding_path = args.frozen_authorization.with_name(
        "spdx_reference_binding.json"
    )
    freeze_manifest_path = args.frozen_authorization.with_name(
        "freeze_manifest_v2.json" if is_m336j_v2 else "freeze_manifest.json"
    )
    required_inputs = (
        args.frozen_authorization,
        args.candidate_pool,
        args.acquisition_policy,
        args.denylist,
        args.authority_root,
        args.authority_statement,
        args.frozen_route_registry,
        args.frozen_route_manifest,
        args.selector_policy,
        args.threshold_manifest,
        args.publication_boundary_contract,
        args.public_artifact_contract,
        args.compiler_jdk_identities,
        args.karina_host_identity_receipt,
        args.frozen_spdx_reference,
        args.karina_private_capsule,
        args.karina_public_capsule_receipt,
        args.karina_executable_dependency_manifest,
        args.ssh_executable,
        args.known_hosts_file,
        spdx_binding_path,
        freeze_manifest_path,
        args.windows_javac,
        args.ssh_key,
    )
    if any(not path.exists() for path in required_inputs):
        raise ValueError("M336I final controller input is missing")
    spdx_reference = _object(args.frozen_spdx_reference)
    spdx_binding = _object(spdx_binding_path)
    if is_m336j_v2:
        if v2_freeze_manifest is None:
            raise ValueError("M336J V2 typed freeze manifest is missing")
        freeze_manifest = v2_freeze_manifest
        freeze_spdx_hash = freeze_manifest.spdx_reference_binding_hash
        freeze_manifest_hash_valid = True
    else:
        freeze_manifest = _object(freeze_manifest_path)
        freeze_spdx_hash = freeze_manifest.get("spdx_reference_binding_hash")
        freeze_body = dict(freeze_manifest)
        freeze_hash = freeze_body.pop("manifest_hash", None)
        freeze_manifest_hash_valid = content_hash(freeze_body) == freeze_hash
    reference_body = dict(spdx_reference)
    reference_hash = reference_body.pop("snapshot_manifest_hash", None)
    binding_body = dict(spdx_binding)
    binding_hash = binding_body.pop("spdx_reference_binding_hash", None)
    if (
        content_hash(reference_body) != reference_hash
        or content_hash(binding_body) != binding_hash
        or not freeze_manifest_hash_valid
        or freeze_spdx_hash != binding_hash
        or spdx_binding.get("snapshot_manifest_hash") != reference_hash
        or spdx_binding.get("snapshot_bytes_hash")
        != bytes_hash(args.frozen_spdx_reference.read_bytes())
        or spdx_binding.get("license_list_version")
        != spdx_reference.get("license_list_version")
    ):
        raise ValueError("M336I frozen SPDX reference differs from F24 binding")
    if is_m336j_legacy or is_m336j_v2:
        if is_m336j_legacy:
            from ai_brain.stage3.acquisition.m336j_freeze import (
                verify_m336j_final_acquisition_authorization,
            )

            verify_m336j_final_acquisition_authorization(authorization)
        _capsule, public, dependencies, _transport, registry = _m336j_private_route(
            args
        )
        route_manifest = build_m336j_route_manifest(
            registry,
            execution_capsule_public_receipt_hash=public.receipt_hash,
            remote_command_renderer_hash=command_renderer_identity_hash(),
            executable_dependency_manifest_hash=dependencies.manifest_hash,
            minimal_environment_policy_hash=public.minimal_environment_policy_hash,
        )
        frozen_registry = _object(args.frozen_route_registry)
        frozen_route = _object(args.frozen_route_manifest)
        frozen_python_environment_hash = (
            freeze_manifest.python_environment_manifest_hash
            if is_m336j_v2
            else freeze_manifest.get("python_environment_manifest_hash")
        )
        required_freeze_bindings = {
            "execution_capsule_public_receipt_hash": public.receipt_hash,
            "python_environment_manifest_hash": frozen_python_environment_hash,
            "executable_dependency_manifest_hash": dependencies.manifest_hash,
            "remote_command_renderer_hash": command_renderer_identity_hash(),
            "minimal_environment_policy_hash": (public.minimal_environment_policy_hash),
            "route_registry_hash": registry.registry_hash,
            "route_manifest_hash": route_manifest.manifest_hash,
        }
        if (
            frozen_registry != json.loads(canonical_json(registry))
            or frozen_route != json.loads(canonical_json(route_manifest))
            or authorization.route_registry_hash != registry.registry_hash
            or authorization.route_manifest_hash != route_manifest.manifest_hash
            or any(
                (
                    getattr(freeze_manifest, name)
                    if is_m336j_v2
                    else freeze_manifest.get(name)
                )
                != value
                for name, value in required_freeze_bindings.items()
                if name != "python_environment_manifest_hash"
            )
            or not isinstance(
                required_freeze_bindings["python_environment_manifest_hash"], str
            )
        ):
            raise ValueError("M336J frozen execution route binding changed")
    outputs = (
        args.acquisition_ledger,
        args.route_state_ledger,
        args.windows_vault,
        args.private_acquisition_output,
        args.public_acquisition_receipt,
        args.selector_ledger,
        args.evaluator_ledger,
        args.windows_selected_snapshot,
        args.windows_private_replay_root,
        args.windows_public_production_root,
        args.karina_public_production_root,
        args.independent_evaluator_root,
        args.public_staging_root,
        args.karina_command_receipt_root,
        args.karina_host_preflight_receipt,
        args.karina_storage_preflight_receipt,
        args.final_receipt,
    )
    if any(path.exists() for path in outputs):
        raise FileExistsError("M336I final controller destinations must be fresh")
    resolved = tuple(path.resolve(strict=False) for path in outputs)
    roots = tuple(path.resolve(strict=True) for path in worktrees)
    if any(path.is_relative_to(root) for path in resolved for root in roots):
        raise ValueError("M336I final controller destination overlaps Git")
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if (
                left == right
                or left.is_relative_to(right)
                or right.is_relative_to(left)
            ):
                raise ValueError("M336I final controller destinations overlap")
    _private_jdk, windows_jdk = verify_m336_jdk_provider_evidence(
        platform="windows",
        java=args.windows_javac.with_name("java.exe"),
        javac=args.windows_javac,
    )
    if (
        windows_jdk.receipt_hash
        != authorization.windows_public_jdk_identity_receipt_hash
    ):
        raise ValueError("M336I Windows JDK differs from frozen authority")
    _capsule, public, _dependencies, _transport, registry = _m336j_private_route(args)
    component = next(
        item
        for item in registry.components
        if item.route_role == "REMOTE_HOST_PREFLIGHT"
    )
    request_hash = content_hash(
        (args.supplied_f24_sha, public.receipt_hash, component.binding_hash)
    )
    receipt, _binding, _public = _invoke_m336j_remote(
        args,
        component_role="REMOTE_HOST_PREFLIGHT",
        subcommand="host-preflight",
        receipt_name="post-freeze-host-preflight-command.json",
        expected_request_hash=request_hash,
        options=(
            (KarinaRemoteTokenClass.FLAG, "--request-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, request_hash),
            (KarinaRemoteTokenClass.FLAG, "--component-binding-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, component.binding_hash),
        ),
    )
    write_canonical_json(args.karina_host_preflight_receipt, receipt)
    if (
        receipt.get("status") != "PASS"
        or receipt.get("host_identity_hash")
        != authorization.karina_stable_host_identity_receipt_hash
        or receipt.get("execution_capsule_receipt_hash") != public.receipt_hash
        or receipt.get("python_environment_manifest_hash")
        != frozen_python_environment_hash
    ):
        raise ValueError("M336I Karina preflight differs from frozen authority")
    _run_karina_storage_preflight(args)


def _host_preflight(args) -> None:
    repository = args.repository.resolve(strict=True)
    git_executable = args.git_executable.resolve(strict=True)
    head = _run((str(git_executable), "rev-parse", "HEAD^{commit}"), cwd=repository)
    status = _run((str(git_executable), "status", "--porcelain=v1"), cwd=repository)
    host = _object(args.host_receipt)
    host_body = dict(host)
    host_hash = host_body.pop("receipt_hash", None)
    java = args.javac.with_name("java")
    _private_jdk, public_jdk = verify_m336_jdk_provider_evidence(
        platform="karina", java=java, javac=args.javac
    )
    passed = (
        head == args.expected_head
        and not status
        and content_hash(host_body) == host_hash
        and host.get("verification_status") == "PASS"
        and host.get("hostname_hash") == bytes_hash(socket.gethostname().encode())
        and host.get("os_family").casefold() == platform.system().casefold()
        and host.get("architecture").casefold() == platform.machine().casefold()
        and host.get("public_jdk_identity_receipt_hash") == args.expected_jdk_hash
        and public_jdk.receipt_hash == args.expected_jdk_hash
    )
    body = {
        "schema_version": 1,
        "exact_head": head,
        "host_identity_hash": host_hash,
        "public_jdk_identity_receipt_hash": public_jdk.receipt_hash,
        "status": "PASS" if passed else "FAIL",
    }
    result = {**body, "receipt_hash": content_hash(body)}
    if not passed:
        raise ValueError("M336I Karina exact-host preflight failed")
    print(canonical_json(result))


def _add_final_arguments(parser) -> None:
    paths = (
        "repository",
        "frozen_authorization",
        "candidate_pool",
        "acquisition_policy",
        "denylist",
        "authority_root",
        "authority_statement",
        "frozen_route_registry",
        "frozen_route_manifest",
        "selector_policy",
        "threshold_manifest",
        "publication_boundary_contract",
        "public_artifact_contract",
        "compiler_jdk_identities",
        "karina_host_identity_receipt",
        "frozen_spdx_reference",
        "acquisition_ledger",
        "route_state_ledger",
        "windows_vault",
        "private_acquisition_output",
        "public_acquisition_receipt",
        "selector_ledger",
        "evaluator_ledger",
        "windows_selected_snapshot",
        "windows_private_replay_root",
        "windows_public_production_root",
        "karina_public_production_root",
        "independent_evaluator_root",
        "public_staging_root",
        "windows_javac",
        "git_executable",
        "ssh_key",
        "ssh_executable",
        "known_hosts_file",
        "karina_private_capsule",
        "karina_public_capsule_receipt",
        "karina_executable_dependency_manifest",
        "karina_command_receipt_root",
        "karina_host_preflight_receipt",
        "karina_storage_preflight_receipt",
        "final_receipt",
    )
    for name in paths:
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--supplied-f24-sha", required=True)
    parser.add_argument("--karina-worker-endpoint", required=True)
    parser.add_argument("--karina-repository", required=True)
    parser.add_argument("--karina-private-root", required=True)
    parser.add_argument("--karina-private-capsule-remote", required=True)
    parser.add_argument("--karina-javac", required=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--output", type=Path, required=True)
    for name in (
        "rehearse-disclosed",
        "rehearse-count-neutral",
        "rehearse-authorized",
    ):
        rehearsal = commands.add_parser(name)
        rehearsal.add_argument("--config", type=Path, required=True)
        rehearsal.add_argument(
            "--platform", choices=("WINDOWS", "KARINA"), required=True
        )
        rehearsal.add_argument("--output", type=Path, required=True)
    evaluation = commands.add_parser("evaluate-rehearsal")
    evaluation.add_argument("--config", type=Path, required=True)
    evaluation.add_argument("--output", type=Path, required=True)
    staging = commands.add_parser("verify-rehearsal-staging")
    staging.add_argument("--config", type=Path, required=True)
    staging.add_argument("--output", type=Path, required=True)
    goldens = commands.add_parser("author-rehearsal-goldens")
    for name in (
        "sealed_vault",
        "bindings",
        "selected_manifest",
        "production_root",
        "javac",
        "output",
    ):
        goldens.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    goldens.add_argument("--sealing-ref", required=True)
    closure = commands.add_parser("build-rehearsal-closure")
    closure.add_argument("--private-acquisition-output", type=Path, required=True)
    closure.add_argument("--windows-vault", type=Path, required=True)
    closure.add_argument("--windows-javac", type=Path, required=True)
    closure.add_argument("--output", type=Path, required=True)
    spdx = commands.add_parser("author-rehearsal-spdx")
    spdx.add_argument("--selected-manifest", type=Path, required=True)
    spdx.add_argument("--input-qualification", type=Path, required=True)
    spdx.add_argument("--frozen-spdx-reference", type=Path, required=True)
    spdx.add_argument("--license-expression", required=True)
    spdx.add_argument("--output", type=Path, required=True)
    final = commands.add_parser("final")
    _add_final_arguments(final)
    worker = commands.add_parser("produce-worker")
    worker.add_argument("--request", type=Path, required=True)
    worker.add_argument("--git-executable", type=Path, required=True)
    host = commands.add_parser("host-preflight")
    host.add_argument("--repository", type=Path, required=True)
    host.add_argument("--expected-head", required=True)
    host.add_argument("--javac", type=Path, required=True)
    host.add_argument("--expected-jdk-hash", required=True)
    host.add_argument("--host-receipt", type=Path, required=True)
    host.add_argument("--git-executable", type=Path, required=True)
    args = parser.parse_args()
    command = {
        "preflight": _preflight,
        "rehearse-disclosed": _rehearse_existing,
        "rehearse-count-neutral": _rehearse_existing,
        "rehearse-authorized": _rehearse_existing,
        "evaluate-rehearsal": _evaluate_rehearsal,
        "verify-rehearsal-staging": _verify_rehearsal_staging,
        "author-rehearsal-goldens": _author_rehearsal_goldens,
        "build-rehearsal-closure": _build_rehearsal_closure,
        "author-rehearsal-spdx": _author_rehearsal_spdx,
        "final": _final,
        "produce-worker": _produce_worker,
        "host-preflight": _host_preflight,
    }[args.command]
    try:
        command(args)
    except Exception as error:
        if args.command == "final":
            _write_final_failure_receipt(args, error)
        raise


if __name__ == "__main__":
    main()
