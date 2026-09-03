"""Run the disclosed-corpus M-33.5 determinism matrix in fresh processes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash

PLATFORM_INDEPENDENT_KEYS = (
    "bundle_hash",
    "source_index_hash",
    "proposal_manifest_hash",
    "evidence_manifest_hash",
    "conflict_report_hash",
    "packability_report_hash",
    "trust_closure_hash",
    "candidate_pack_hash",
    "candidate_pack_tree_hash",
    "component_manifest_hash",
    "replay_status",
    "source_execution",
    "annotation_processing",
)

CASES = (
    ("original", "original", "0", "UTC", "C", "source"),
    ("reverse", "reverse", "1", "UTC", "C", "source"),
    ("shuffle", "shuffle", "335", "UTC", "C", "source"),
    ("native", "native", "999", "UTC", "C", "source"),
    ("copied_root", "original", "0", "Europe/Minsk", "C.UTF-8", "copy"),
    (
        "creation_reverse",
        "native",
        "1",
        "Europe/Minsk",
        "C.UTF-8",
        "reverse_copy",
    ),
    (
        "hashseed_locale",
        "shuffle",
        "8675309",
        "America/New_York",
        "C.UTF-8",
        "copy",
    ),
    (
        "timezone_root",
        "reverse",
        "335",
        "America/Los_Angeles",
        "C",
        "reverse_copy",
    ),
)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _copy_source(source: Path, destination: Path, *, reverse: bool) -> None:
    files = sorted(
        (item for item in source.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(source).as_posix().encode("utf-8"),
        reverse=reverse,
    )
    for item in files:
        target = destination / item.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)


def _percentiles(values: list[float]) -> dict[str, str]:
    ordered = sorted(values)

    def value(point: float) -> float:
        return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * point))]

    return {
        "p50": f"{value(0.50):.9f}",
        "p95": f"{value(0.95):.9f}",
        "p99": f"{value(0.99):.9f}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    if args.jobs < 1 or args.jobs > len(CASES):
        raise ValueError("M-33.5 matrix jobs must be between 1 and case count")
    source = args.source_root.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("M-33.5 matrix output already exists")
    args.output.mkdir(parents=True)
    project = Path(__file__).resolve().parents[1]
    runner = project / "scripts/m335_run_development_gate.py"
    rows = []
    with tempfile.TemporaryDirectory(prefix="m335-matrix-roots-") as temporary:
        temporary_root = Path(temporary)
        roots = {"source": source}
        for mode, reverse in (("copy", False), ("reverse_copy", True)):
            root = temporary_root / mode / "different-absolute-root"
            _copy_source(source, root, reverse=reverse)
            roots[mode] = root

        def run_case(case):
            name, order, seed, timezone, locale, root_mode = case
            case_output = args.output / name
            environment = dict(os.environ)
            environment.update(
                {
                    "PYTHONHASHSEED": seed,
                    "TZ": timezone,
                    "LC_ALL": locale,
                    "LANG": locale,
                }
            )
            command = (
                sys.executable,
                str(runner),
                "--source-root",
                str(roots[root_mode]),
                "--output",
                str(case_output),
                "--order",
                order,
                "--compact",
            )
            completed = subprocess.run(
                command,
                cwd=project,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            (case_output / "runner.log").write_text(
                completed.stdout, encoding="utf-8", newline="\n"
            )
            if completed.returncode:
                raise RuntimeError(f"M-33.5 matrix case failed: {name}")
            summary = json.loads((case_output / "summary.json").read_text("utf-8"))
            roots_row = json.loads(
                (case_output / "component_roots.json").read_text("utf-8")
            )
            return {
                "case": name,
                "input_order": order,
                "python_hash_seed": seed,
                "timezone": timezone,
                "locale": locale,
                "root_mode": root_mode,
                "platform_independent": {
                    key: summary[key] for key in PLATFORM_INDEPENDENT_KEYS
                },
                "component_roots_hash": content_hash(roots_row),
                "timings": summary["timings"],
                "performance": summary["performance"],
                "proposal_throughput_per_second": summary[
                    "proposal_throughput_per_second"
                ],
                "peak_python_memory_bytes": summary["peak_python_memory_bytes"],
            }

        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            rows.extend(executor.map(run_case, CASES))
    baseline = rows[0]
    differences = []
    for row in rows[1:]:
        for key in PLATFORM_INDEPENDENT_KEYS:
            if (
                row["platform_independent"][key]
                != baseline["platform_independent"][key]
            ):
                differences.append((row["case"], key))
        if row["component_roots_hash"] != baseline["component_roots_hash"]:
            differences.append((row["case"], "component_roots_hash"))
    timing_keys = sorted(rows[0]["timings"])
    performance = {
        "stage_seconds": {
            key: _percentiles([float(row["timings"][key]) for row in rows])
            for key in timing_keys
        },
        "proposal_throughput_per_second": _percentiles(
            [float(row["proposal_throughput_per_second"]) for row in rows]
        ),
        "peak_python_memory_bytes": _percentiles(
            [row["peak_python_memory_bytes"] for row in rows]
        ),
        "lookup_and_comparison_ns": {
            key: {
                percentile: _percentiles(
                    [row["performance"][key][percentile] for row in rows]
                )["p50"]
                for percentile in ("p50", "p95", "p99")
            }
            for key in rows[0]["performance"]
        },
    }
    body = {
        "schema_version": 1,
        "classification": "DISCLOSED_DEVELOPMENT_REGRESSION_ONLY",
        "case_count": len(rows),
        "cases": tuple(rows),
        "platform_independent_keys": PLATFORM_INDEPENDENT_KEYS,
        "difference_count": len(differences),
        "differences": tuple(differences),
        "performance": performance,
        "status": "PASS" if not differences else "FAIL",
    }
    _write(
        args.output / "matrix_report.json", {**body, "report_hash": content_hash(body)}
    )
    if differences:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
