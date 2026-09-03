"""Measure disclosed-corpus semantics without rebuilding the candidate pack."""

from __future__ import annotations

import argparse
import tempfile
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.java_file_audit import EnforcedJavaProductionFileAudit
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_process_audit import EnforcedProcessAudit
from ai_brain.stage3.acquisition.java_production import (
    run_java_acquisition_pipeline,
    seal_java_production_output,
)
from ai_brain.stage3.acquisition.java_production_evaluator import (
    evaluate_sealed_java_production,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle

STAMP = "2026-09-03T00:00:00Z"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--goldens", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("M-33.5 semantic diagnostic output already exists")
    args.output.mkdir(parents=True)
    paths = tuple(
        sorted(
            root.rglob("*.java"),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )
    with tempfile.TemporaryDirectory(prefix="m335-semantic-diagnostic-") as temporary:
        store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
        bundle = ingest_bundle(
            paths,
            bundle_id="m335-disclosed-java",
            domain_tags=("java-api",),
            imported_at=STAMP,
            source_root=root,
            store=store,
        )
        with (
            EnforcedProcessAudit(()) as process_audit,
            EnforcedJavaProductionFileAudit() as file_audit,
        ):
            batch = run_java_acquisition_pipeline(
                bundle,
                store,
                deterministic_run_id="m335.disclosed-development-java.v1",
            )
        sealed = seal_java_production_output(batch)
        goldens = load_java_golden_manifest(args.goldens.resolve(strict=True))
        report = evaluate_sealed_java_production(sealed, batch, goldens)
        _write(args.output / "production_output.json", sealed)
        _write(args.output / "evaluation_report.json", asdict(report))
        _write(args.output / "process_audit.json", asdict(process_audit.report()))
        _write(args.output / "file_audit.json", asdict(file_audit.report()))
        _write(
            args.output / "counts.json",
            {
                "proposal_count": len(batch.proposal_batch.proposals),
                "trusted_count": batch.trusted_count,
                "withheld_count": batch.withheld_count,
                "packable_count": len(batch.packability_report.packable_proposal_ids),
                "batch_hash": batch.batch_hash,
            },
        )
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
