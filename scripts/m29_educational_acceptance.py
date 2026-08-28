"""Run and persist the reproducible M-29 acceptance and performance gates."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.domains.chemistry.education.exercise_catalog import (
    chemistry_exercise_specs,
)
from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.source_derivation import verify_source_chain
from ai_brain.stage2.education.acceptance import run_m29_acceptance
from ai_brain.stage2.education.benchmark import run_m29_benchmark
from ai_brain.stage2.education.version import (
    COMPATIBILITY,
    DERIVATION_GRAPH_SCHEMA_VERSION,
    EDUCATIONAL_LAYER_VERSION,
    EDUCATIONAL_SCHEMA_VERSION,
    EXERCISE_SCHEMA_VERSION,
    GRADING_SCHEMA_VERSION,
    HINT_POLICY_VERSION,
    TUTOR_SESSION_SCHEMA_VERSION,
)
from ai_brain.stage2.facts.canonical import canonical_json, content_hash, utc_now

ROOT = Path(__file__).resolve().parents[1]
CHEMISTRY_ROOT = ROOT / "artifacts" / "domains" / "chemistry" / "m29"
EDUCATION_ROOT = ROOT / "artifacts" / "education" / "m29"
RUNS_ROOT = ROOT / "runs" / "m29"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--chemistry-root", type=Path, default=CHEMISTRY_ROOT)
    args = parser.parse_args()
    chemistry_root = args.chemistry_root.resolve()
    service = ChemistryDomainService.open(chemistry_root)
    adapter = ChemistryEducationAdapter(service)
    source = verify_source_chain(chemistry_root / "sources")
    if args.quick:
        acceptance = run_m29_acceptance(
            adapter,
            explanation_count=30,
            exercise_count=100,
            grading_count=200,
            diagnosis_count=100,
            hint_sequence_count=30,
        )
        performance = run_m29_benchmark(adapter, interaction_count=200)
    else:
        acceptance = run_m29_acceptance(adapter)
        performance = run_m29_benchmark(adapter)
    catalog = _catalog(service)
    report = {
        "status": "PASS",
        "generated_at": utc_now(),
        "mode": "quick" if args.quick else "full",
        "preflight": source,
        "catalog_hash": catalog["catalog_hash"],
        "acceptance": acceptance,
        "performance": performance,
    }
    report["report_hash"] = content_hash(report)
    target = RUNS_ROOT / ("quick" if args.quick else "final")
    target.mkdir(parents=True, exist_ok=True)
    _write_json(target / "acceptance.json", report)
    _write_json(target / "performance.json", performance)
    if not args.quick:
        EDUCATION_ROOT.mkdir(parents=True, exist_ok=True)
        _write_json(EDUCATION_ROOT / "catalog.json", catalog)
    print(canonical_json(report))


def _catalog(service):
    body = {
        "educational_layer_version": EDUCATIONAL_LAYER_VERSION,
        "educational_schema_version": EDUCATIONAL_SCHEMA_VERSION,
        "derivation_graph_schema_version": DERIVATION_GRAPH_SCHEMA_VERSION,
        "exercise_schema_version": EXERCISE_SCHEMA_VERSION,
        "grading_schema_version": GRADING_SCHEMA_VERSION,
        "hint_policy_version": HINT_POLICY_VERSION,
        "tutor_session_schema_version": TUTOR_SESSION_SCHEMA_VERSION,
        "compatibility": COMPATIBILITY,
        "chemistry_domain_manifest_hash": service.manifest["domain_manifest_hash"],
        "chemistry_fact_memory_snapshot_hash": service.manifest[
            "fact_memory_snapshot_hash"
        ],
        "chemistry_source_chain_hash": service.manifest["source_chain_hash"],
        "exercise_specs": tuple(
            asdict(spec)
            for spec in chemistry_exercise_specs(service.manifest["domain_version"])
        ),
    }
    return {**body, "catalog_hash": content_hash(body)}


def _write_json(path: Path, value) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(value) + "\n")


if __name__ == "__main__":
    main()
