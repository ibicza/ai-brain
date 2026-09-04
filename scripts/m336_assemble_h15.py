"""Assemble only the frozen H15 data allowlist and its complete role manifest."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.java_freeze_roles import (
    build_final_artifact_role_manifest,
    classify_final_artifact_role,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _copy_tree(source: Path, target: Path) -> None:
    if source.exists():
        shutil.copytree(source, target)


def _markdown(path: Path, title: str, sections: tuple[tuple[str, str], ...]) -> None:
    lines = [f"# {title}", ""]
    for heading, body in sections:
        lines.extend((f"## {heading}", "", body, ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    destination = repository / "evaluation/m336_final_java"
    doc_paths = (
        repository / "docs/m336_final_source_inventory.md",
        repository / "docs/m336_final_semantic_metrics.md",
        repository / "docs/m336_final_trust_metrics.md",
        repository / "docs/m336_runtime_proof.md",
    )
    if destination.exists() or any(path.exists() for path in doc_paths):
        raise FileExistsError("H15 destination already exists")
    selection = args.selection_root.resolve(strict=True)
    production = args.production_root.resolve(strict=True)
    evaluation = args.evaluation_root.resolve(strict=True)
    destination.mkdir(parents=True)
    for name in (
        "source_acquisition_receipts.json",
        "selector_receipt.json",
        "selection_execution.json",
        "physical_census.json",
        "source_overlap.json",
    ):
        _copy_file(selection / name, destination / name)
    _copy_tree(selection / "source_snapshots", destination / "source_snapshots")
    for name in (
        "production_output.json",
        "component_manifest.json",
        "packability_report.json",
        "trust_closure.json",
        "production_counts.json",
        "candidate_replay.json",
        "production_summary.json",
    ):
        _copy_file(production / name, destination / name)
    _copy_tree(production / "candidate_pack", destination / "candidate_pack")
    for name in (
        "jdk_provider_receipt.json",
        "evaluation_report.json",
        "semantic_metrics.json",
        "trust_metrics.json",
        "diagnostic_metrics.json",
        "runtime_proof.json",
        "replay_mutations.json",
        "final_gate.json",
        "final_decision.json",
        "release_approval.json",
        "installation.json",
    ):
        if (evaluation / name).exists():
            _copy_file(evaluation / name, destination / name)
    _copy_tree(evaluation / "oracle", destination / "oracle")
    _copy_tree(evaluation / "installed_pack", destination / "installed_pack")

    acquisitions = _load(destination / "source_acquisition_receipts.json")
    census = _load(destination / "physical_census.json")
    semantic = _load(destination / "semantic_metrics.json")
    trust = _load(destination / "trust_metrics.json")
    diagnostics = _load(destination / "diagnostic_metrics.json")
    runtime = _load(destination / "runtime_proof.json")
    inventory_rows = "\n".join(
        f"- `{item['family_id']}:{item['version']}`; {item['license_spdx']}; "
        f"archive `{item['source_archive_sha256']}`"
        for item in acquisitions["receipts"]
    )
    census_rows = "\n".join(
        f"- {key}: `{value}`" for key, value in census.items() if key != "report_hash"
    )
    _markdown(
        doc_paths[0],
        "M-33.6 final Java source inventory",
        (("Sources", inventory_rows), ("Frozen physical census", census_rows)),
    )
    _markdown(
        doc_paths[1],
        "M-33.6 final Java semantic metrics",
        (
            (
                "Exact semantic result",
                "\n".join(
                    f"- {key}: `{value}`"
                    for key, value in semantic.items()
                    if key not in {"mismatches"}
                ),
            ),
            ("Mismatch rows", f"Count: `{len(semantic['mismatches'])}`."),
        ),
    )
    _markdown(
        doc_paths[2],
        "M-33.6 final Java trust metrics",
        (
            (
                "Trust",
                "\n".join(f"- {key}: `{value}`" for key, value in trust.items()),
            ),
            (
                "Diagnostic scope",
                "\n".join(
                    f"- {scope}: `{count}`" for scope, count in diagnostics["by_scope"]
                ),
            ),
        ),
    )
    _markdown(
        doc_paths[3],
        "M-33.6 installed runtime proof",
        (
            ("Status", f"`{runtime['status']}`"),
            (
                "Isolation",
                (
                    "Runtime queries used the installed content-addressed pack and current "
                    "provider/capability authority; source, oracle, and golden paths were "
                    "not placed on the runtime import path."
                ),
            ),
            (
                "Queries",
                "\n".join(
                    f"- {item['query_class']}: `{item['status']}`"
                    for item in runtime.get("queries", ())
                ),
            ),
        ),
    )
    role_path = destination / "role_manifest.json"
    relative_paths = tuple(
        path.relative_to(repository).as_posix()
        for path in repository.rglob("*")
        if path.is_file() and (path.is_relative_to(destination) or path in doc_paths)
    ) + (role_path.relative_to(repository).as_posix(),)
    for path in relative_paths:
        classify_final_artifact_role(path)
    manifest = build_final_artifact_role_manifest(
        {path: b"" for path in relative_paths}
    )
    role_path.write_text(
        canonical_json(asdict(manifest)) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
