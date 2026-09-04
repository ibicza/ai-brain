"""Build the evidence-only M-33.6 E15 tree from sealed H15 and external logs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    M336_BASE_SHA,
    M336_E15_PREFIXES,
    M336_H15_PREFIXES,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--f15-sha", required=True)
    parser.add_argument("--windows-production", type=Path, required=True)
    parser.add_argument("--karina-production", type=Path, required=True)
    parser.add_argument("--platform-comparison", type=Path, required=True)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    parser.add_argument("--windows-quality-log", type=Path, required=True)
    parser.add_argument("--karina-quality-log", type=Path, required=True)
    parser.add_argument("--graph-report", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    h15_sha = _git(repository, "rev-parse", "HEAD")
    if _git(repository, "rev-parse", f"{h15_sha}^") != args.f15_sha:
        raise ValueError("H15 is not the direct child of exact F15")
    if _git(repository, "rev-parse", f"{args.f15_sha}^") != M336_BASE_SHA:
        raise ValueError("F15 is not the direct child of exact E14")
    if _git(repository, "show", "-s", "--format=%s", h15_sha) != (
        "M-33.6 untouched Java black-box evaluation"
    ):
        raise ValueError("H15 commit subject mismatch")
    run_root = repository / "runs/m336_final_gate"
    docs_report = repository / "docs/m336_final_freeze_report.md"
    runs_report = repository / "runs/m336_final_freeze_report.md"
    if run_root.exists() or docs_report.exists() or runs_report.exists():
        raise FileExistsError("E15 evidence destination already exists")
    changed_h = tuple(
        item
        for item in _git(
            repository, "diff", "--name-only", args.f15_sha, h15_sha
        ).splitlines()
        if item
    )
    unauthorized_h = tuple(
        path
        for path in changed_h
        if not any(
            path == prefix or path.startswith(prefix.rstrip("/") + "/")
            for prefix in M336_H15_PREFIXES
        )
    )
    if unauthorized_h:
        raise ValueError("H15 changed a path outside its frozen allowlist")
    frozen_diff = tuple(
        item
        for item in _git(
            repository,
            "diff",
            "--name-only",
            args.f15_sha,
            h15_sha,
            "--",
            "src",
            "scripts",
            "tools",
            "tests",
            "schemas",
            "pyproject.toml",
            "uv.lock",
            ".gitattributes",
        ).splitlines()
        if item
    )
    if frozen_diff:
        raise ValueError("frozen implementation changed between F15 and H15")
    run_root.mkdir(parents=True)
    for platform, root in (
        ("windows", args.windows_production.resolve(strict=True)),
        ("karina", args.karina_production.resolve(strict=True)),
    ):
        for name in (
            "production_process_audit.json",
            "production_file_access_audit.json",
            "production_state_audit.json",
            "production_performance.json",
            "production_summary.json",
        ):
            _copy(root / name, run_root / "platform" / platform / name)
    _copy(
        args.platform_comparison.resolve(strict=True),
        run_root / "platform_comparison.json",
    )
    _copy(
        args.evaluation_root.resolve(strict=True) / "evaluation_performance.json",
        run_root / "evaluation_performance.json",
    )
    _copy(args.windows_quality_log, run_root / "quality/windows_full_suite.log")
    _copy(args.karina_quality_log, run_root / "quality/karina_full_suite.log")
    _copy(args.graph_report, run_root / "graph_post_freeze.json")
    final_root = repository / "evaluation/m336_final_java"
    decision = _load(final_root / "final_decision.json")
    evaluation = _load(final_root / "evaluation_report.json")
    census = _load(final_root / "physical_census.json")
    overlap = _load(final_root / "source_overlap.json")
    production = _load(final_root / "production_summary.json")
    runtime = _load(final_root / "runtime_proof.json")
    comparison = _load(args.platform_comparison)
    roadmap = repository / "docs/lifelong_cognitive_system_roadmap.md"
    integrity_body = {
        "schema_version": 1,
        "e14_sha": M336_BASE_SHA,
        "f15_sha": args.f15_sha,
        "h15_sha": h15_sha,
        "e15_sha_binding": "RESOLVE_CURRENT_COMMIT_FROM_GIT_OBJECT",
        "h15_parent_is_f15": True,
        "f15_parent_is_e14": True,
        "h15_unauthorized_paths": unauthorized_h,
        "frozen_paths_changed_after_f15": frozen_diff,
        "e15_path_allowlist": M336_E15_PREFIXES,
        "roadmap_sha256": bytes_hash(roadmap.read_bytes()),
        "outcome_c_outside_ancestry": subprocess.run(
            (
                "git",
                "merge-base",
                "--is-ancestor",
                "b94c17dc8b1026fe9e338b5fc0a4926b23d68a39",
                h15_sha,
            ),
            cwd=repository,
            check=False,
        ).returncode
        == 1,
        "status": "PASS",
    }
    _write(
        run_root / "pre_e15_freeze_integrity.json",
        {**integrity_body, "report_hash": content_hash(integrity_body)},
    )
    envelope_body = {
        "schema_version": 1,
        "outcome": decision["outcome"],
        "location": evaluation["location"],
        "semantic": evaluation["semantic"],
        "trust": evaluation["trust"],
        "field_evidence": evaluation["field_evidence"],
        "resolution": evaluation["resolution"],
        "corpus": census,
        "overlap": overlap,
        "production": production,
        "platform_comparison": comparison,
        "runtime_status": runtime["status"],
    }
    _write(
        run_root / "metric_envelope.json",
        {**envelope_body, "envelope_hash": content_hash(envelope_body)},
    )
    report = "\n".join(
        (
            "# M-33.6 final Java freeze report",
            "",
            f"Outcome: `{decision['outcome']}`.",
            "",
            f"Chain before E15: `{M336_BASE_SHA} -> {args.f15_sha} -> {h15_sha}`.",
            (
                "E15 is self-bound by its Git object and is verified after commit; "
                "embedding its own SHA in its own content is cryptographically circular."
            ),
            "",
            f"Roadmap SHA-256: `{integrity_body['roadmap_sha256']}`.",
            (
                "M-33.6 is the final Java freeze for roadmap M-33. M-33.7 remains "
                "required. Episodic and relationship memory have not started."
            ),
            "",
            (
                f"Corpus: `{census['real_callable_source_file_count']}` files, "
                f"`{census['real_callable_target_count']}` callables, "
                f"`{census['real_receiver_type_count']}` receiver types, "
                f"`{census['real_package_count']}` packages."
            ),
            (
                f"Overlap: `{overlap['normalized_similarity_overlap_count']}`. "
                f"Cross-platform differences: "
                f"`{comparison['platform_independent_difference_count']}`."
            ),
            f"Wrong trusted: `{evaluation['wrong_trusted_count']}`. Runtime: `{runtime['status']}`.",
            "",
            (
                "No moral, moderation, refusal, political, ideological, or topic "
                "restriction was added. All abstentions are technical or epistemic states."
            ),
            "",
            (
                "Performance percentiles use the measured sample counts in the "
                "machine-readable evidence. Production substages that the current "
                "implementation cannot time independently are marked "
                "NOT_MEASURED_SEPARATELY."
            ),
            "",
        )
    )
    docs_report.write_text(report, encoding="utf-8", newline="\n")
    runs_report.parent.mkdir(parents=True, exist_ok=True)
    runs_report.write_text(report, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
