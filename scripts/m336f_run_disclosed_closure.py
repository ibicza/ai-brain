"""Run exact-R21 disclosed compiler census, closure proof, and one-shot selector."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_production_compiler import (
    build_java_production_compilation_probe,
    run_java_production_compilation_probe,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336e_selectability import (
    selectable_source_census_from_dict,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    build_java_compilation_closure_manifest,
    combine_java_compilation_closure_manifests,
    prove_java_compilation_closure_feasibility,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    M336FSelectorLedger,
    select_compilation_closed_sources_once,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _require_clean_exact(repository: Path, expected: str) -> None:
    head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != expected or len(head) != 40 or status:
        raise ValueError("disclosed closure requires a clean exact-R21 worktree")


def _verify_qualification_inputs(
    qualification: dict,
    summary: dict,
    *,
    r21_sha: str,
    binding_manifest_hash: str,
    census_hash: str,
    exact_phase: str = "R21",
) -> None:
    qualification_fields = {
        "schema_version",
        "candidate_count",
        "candidates",
        "historical_qualification_report_hash",
        "report_hash",
    }
    candidate_fields = {
        "family_id",
        "source_jar_sha256",
        "source_tree_hash",
        "java_file_count",
        "legal_document_count",
        "unknown_legal_document_role_count",
        "correspondence_complete_file_count",
        "analysis_eligible",
        "authority_receipt_valid",
        "qualification_hash",
    }
    summary_fields = {
        "schema_version",
        "qualification_mode",
        "r21_sha",
        "preflight_report_hash",
        "candidate_count",
        "analysis_eligible_root_count",
        "analysis_eligible_file_count",
        "parser_valid_file_count",
        "callable_file_count",
        "production_supported_file_count",
        "selectable_root_count",
        "selectable_file_count",
        "balanced_capacity",
        "portable_vault_manifest_hash",
        "portable_vault_tree_hash",
        "candidate_qualification_hash",
        "source_entry_binding_manifest_hash",
        "selectability_census_hash",
        "legacy_feasibility_proof_hash",
        "registry_entry_count",
        "registry_manifest_bytes_hash",
        "authority_receipt_failure_count",
        "historical_qualification_equal",
        "selector_reservation_count",
        "selector_invocation_count",
        "selector_rerun_count",
        "status",
        "summary_hash",
    }
    if set(qualification) != qualification_fields or not isinstance(
        qualification.get("candidates"), list
    ):
        raise ValueError("qualification report schema changed")
    for row in qualification["candidates"]:
        if not isinstance(row, dict) or set(row) != candidate_fields:
            raise ValueError("qualification candidate schema changed")
        body = dict(row)
        claimed = body.pop("qualification_hash")
        if content_hash(body) != claimed:
            raise ValueError("qualification candidate hash mismatch")
    summary_body = dict(summary)
    summary_hash = summary_body.pop("summary_hash", None)
    if (
        set(summary) != summary_fields
        or qualification["schema_version"] != 1
        or qualification["candidate_count"] != len(qualification["candidates"])
        or content_hash(qualification["candidates"]) != qualification["report_hash"]
        or summary_hash is None
        or content_hash(summary_body) != summary_hash
        or summary.get("schema_version") != 1
        or summary.get("qualification_mode") != f"EXACT_{exact_phase}_AUTHORITATIVE"
        or summary.get("r21_sha") != r21_sha
        or summary.get("candidate_count") != qualification["candidate_count"]
        or summary.get("candidate_qualification_hash") != qualification["report_hash"]
        or summary.get("source_entry_binding_manifest_hash") != binding_manifest_hash
        or summary.get("selectability_census_hash") != census_hash
        or summary.get("authority_receipt_failure_count") != 0
        or summary.get("historical_qualification_equal") is not True
        or summary.get("selector_reservation_count") != 0
        or summary.get("selector_invocation_count") != 0
        or summary.get("selector_rerun_count") != 0
        or summary.get("status") != "PASS"
    ):
        raise ValueError("qualification report is not bound to exact-R21 census")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r21-sha", required=True)
    parser.add_argument("--exact-phase", choices=("R21", "R22"), default="R21")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--qualification-summary", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--selected-source-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--selector-seed", default="m336f-disclosed-closure-selector-v1"
    )
    parser.add_argument(
        "--development",
        action="store_true",
        help="allow a dirty pre-R21 worktree and mark output non-authoritative",
    )
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    if not args.development:
        _require_clean_exact(repository, args.r21_sha)
    if args.output.exists() or args.selected_source_output.exists():
        raise FileExistsError("fresh disclosed closure output already exists")
    if args.ledger.exists():
        raise FileExistsError("fresh disclosed selector ledger already exists")
    vault = args.vault.resolve(strict=True)
    bindings = source_entry_binding_manifest_from_dict(_load(args.bindings))
    census = selectable_source_census_from_dict(_load(args.census))
    qualification = _load(args.qualification)
    qualification_summary = _load(args.qualification_summary)
    _verify_qualification_inputs(
        qualification,
        qualification_summary,
        r21_sha=args.r21_sha,
        binding_manifest_hash=bindings.manifest_hash,
        census_hash=census.census_hash,
        exact_phase=args.exact_phase,
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
        raise ValueError("analysis-eligible census lacks exact source bindings")
    probe = build_java_production_compilation_probe(args.javac.resolve(strict=True))
    args.output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="m336f-disclosed-census-") as temporary:
        temporary_root = Path(temporary)
        source_root = temporary_root / "sources"
        source_root.mkdir()
        store = AcquisitionStore.open_or_initialize(temporary_root / "store")
        for unit, binding in sorted(binding_by_unit.items()):
            target = source_root.joinpath(*unit.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((vault / binding.vault_path).read_bytes())
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
                bundle_id=f"m336f-disclosed-census-{family}",
                domain_tags=("java-api",),
                imported_at="1970-01-01T00:00:00Z",
                source_root=source_root,
                store=store,
            )
            source_index = index_java_bundle(bundle, store)
            source_entry_ids = {
                unit: binding_by_unit[unit].source_entry_id.identity_hash
                for unit in sorted(binding_by_unit)
                if unit.startswith(f"{family}/")
            }
            report = run_java_production_compilation_probe(
                bundle=bundle,
                store=store,
                source_index=source_index,
                probe=probe,
                javac_executable=args.javac,
                source_entry_ids=source_entry_ids,
            )
            manifest = build_java_compilation_closure_manifest(
                source_index=source_index,
                compiler_report=report,
                source_entry_ids=source_entry_ids,
            )
            manifests.append(manifest)
            reports.append((family, report))
        combined = combine_java_compilation_closure_manifests(tuple(manifests))
        proof = prove_java_compilation_closure_feasibility(combined, census)
        _write(args.output / "compiler_probe.json", asdict(probe))
        _write(args.output / "compilation_closure_manifest.json", asdict(combined))
        _write(args.output / "compilation_closure_feasibility.json", asdict(proof))
        for family, report in reports:
            _write(args.output / "compiler_reports" / f"{family}.json", asdict(report))
        summary_body = {
            "schema_version": 1,
            "r21_sha": args.r21_sha,
            "qualification_mode": (
                "DEVELOPMENT_NON_AUTHORITATIVE"
                if args.development
                else f"EXACT_{args.exact_phase}_AUTHORITATIVE"
            ),
            "analysis_eligible_file_count": len(eligible),
            "analysis_eligible_root_count": len(reports),
            "qualification_report_hash": qualification["report_hash"],
            "qualification_summary_hash": qualification_summary["summary_hash"],
            "compiler_probe_hash": probe.probe_hash,
            "compiler_identity_hash": probe.compiler_identity_hash,
            "compiler_report_hashes": tuple(
                (family, report.report_hash) for family, report in reports
            ),
            "compiler_diagnostic_count": sum(
                report.diagnostic_count for _family, report in reports
            ),
            "unknown_scope_count": sum(
                report.unknown_scope_count for _family, report in reports
            ),
            "unmapped_diagnostic_count": sum(
                report.unmapped_diagnostic_count for _family, report in reports
            ),
            "source_unit_unbound_count": sum(
                report.source_unit_unbound_count for _family, report in reports
            ),
            "malformed_output_count": sum(
                report.malformed_output_count for _family, report in reports
            ),
            "closure_manifest_hash": combined.manifest_hash,
            "compiler_clean_supported_capacity": (
                combined.compiler_clean_supported_declaration_capacity
            ),
            "feasibility_proof_hash": proof.proof_hash,
            "hard_requirements_satisfied": proof.hard_requirements_satisfied,
            "failure_reasons": proof.failure_reasons,
        }
        _write(
            args.output / "compiler_census_summary.json",
            {**summary_body, "summary_hash": content_hash(summary_body)},
        )
        ledger = M336FSelectorLedger(args.ledger, git_worktrees=(repository,))
        if not proof.hard_requirements_satisfied:
            ledger.append(
                "CENSUS_SEALED",
                context_hash=content_hash(
                    (
                        census.census_hash,
                        qualification["report_hash"],
                        qualification_summary["summary_hash"],
                        combined.manifest_hash,
                        proof.proof_hash,
                        bindings.manifest_hash,
                    )
                ),
            )
            _write(args.output / "selector_ledger_receipt.json", ledger.receipt())
            raise SystemExit("disclosed compilation closure is infeasible")
        selected, selector = select_compilation_closed_sources_once(
            census=census,
            closure_manifest=combined,
            proof=proof,
            bindings=bindings,
            selector_seed=args.selector_seed,
            ledger=ledger,
            qualification_report_hash=qualification["report_hash"],
            qualification_summary_hash=qualification_summary["summary_hash"],
        )
        args.selected_source_output.mkdir(parents=True)
        for row in selected.files:
            binding = binding_by_unit[row.selected_path]
            target = args.selected_source_output.joinpath(*row.selected_path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((vault / binding.vault_path).read_bytes())
        _write(args.output / "selected_source_manifest.json", asdict(selected))
        _write(args.output / "selector_receipt.json", asdict(selector))
        _write(args.output / "selector_ledger_receipt.json", ledger.receipt())


if __name__ == "__main__":
    main()
