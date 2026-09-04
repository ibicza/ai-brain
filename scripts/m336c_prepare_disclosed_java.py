"""Prepare the one disclosed-development selector invocation for M-33.6c."""

from __future__ import annotations

import argparse
import time
import tracemalloc
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336c_development import (
    dump_preparation_reports,
    prepare_disclosed_rehearsal,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disclosed-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--selected-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    performance_samples: dict[str, list[float]] = {}
    tracemalloc.start()
    started = time.perf_counter()
    preparation = prepare_disclosed_rehearsal(
        disclosed_root=args.disclosed_root.resolve(strict=True),
        work_root=args.work_root,
        selected_root=args.selected_root,
        performance_samples=performance_samples,
    )
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    dump_preparation_reports(preparation, args.output)
    body = {
        "schema_version": 1,
        "base_sha": "1541805f9cd6c19ff9c372afeefbd41148217736",
        "candidate_count": len(preparation.assessments),
        "analysis_eligible_root_count": len(preparation.roots),
        "selected_source_count": len(preparation.selected_sources),
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
        "preparation_report_hash": preparation.report_hash,
        "selector_receipt_hash": preparation.selector_receipt["receipt_hash"],
    }
    (args.output / "preparation_summary.json").write_text(
        canonical_json({**body, "summary_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    performance = {
        "schema_version": 1,
        "sample_count": 1,
        "complete_disclosed_provenance_seconds": f"{elapsed:.6f}",
        "p50_seconds": f"{elapsed:.6f}",
        "p95_seconds": f"{elapsed:.6f}",
        "p99_seconds": f"{elapsed:.6f}",
        "candidate_throughput_per_second": f"{len(preparation.assessments) / elapsed:.6f}",
        "entry_throughput_per_second": f"{sum(item.eligible_source_set.total_entry_count for item in preparation.assessments) / elapsed:.6f}",
        "peak_python_bytes": peak,
        "suboperations": {
            name: _percentiles(samples)
            for name, samples in sorted(performance_samples.items())
        },
    }
    (args.output / "preparation_performance.json").write_text(
        canonical_json({**performance, "report_hash": content_hash(performance)})
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _percentiles(samples: list[float]) -> dict[str, object]:
    values = sorted(samples)

    def at(fraction: float) -> str:
        return f"{values[round((len(values) - 1) * fraction)]:.9f}"

    return {
        "sample_count": len(values),
        "p50_seconds": at(0.50),
        "p95_seconds": at(0.95),
        "p99_seconds": at(0.99),
        "throughput_per_second": f"{len(values) / sum(values):.6f}",
    }


if __name__ == "__main__":
    main()
