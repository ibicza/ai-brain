"""Prove a future V2 registry append on a disposable copy of the E19 registry."""

from __future__ import annotations

import argparse
import shutil
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    DEFAULT_REGISTRY_ROOT,
    append_disclosed_java_entries_v2,
    build_disclosed_java_material_entry,
    load_disclosed_java_registry,
    verify_disclosed_java_registry,
)


def _entry(index: int):
    version = f"0.0.{index}"
    return build_disclosed_java_material_entry(
        coordinate=f"org.m336e.simulated:candidate-{index}:{version}",
        version=version,
        source_url=(
            "https://repo.maven.apache.org/maven2/org/m336e/simulated/"
            f"candidate-{index}/{version}/candidate-{index}-{version}-sources.jar"
        ),
        archive_hash=content_hash(("m336e-simulated", index, "archive")),
        pom_hash=content_hash(("m336e-simulated", index, "pom")),
        raw_source_hashes=(content_hash(("m336e-simulated", index, "raw")),),
        canonical_source_hashes=(
            content_hash(("m336e-simulated", index, "canonical")),
        ),
        source_tree_hash=content_hash(("m336e-simulated", index, "tree")),
        selected_relative_paths=(),
        declaration_fingerprints=(
            content_hash(("m336e-simulated", index, "declaration")),
        ),
        scm_revision=f"{index + 1:040x}",
        correspondence_hash=content_hash(("m336e-simulated", index, "correspondence")),
        disclosure_reason="M336E_Q20_SIMULATED_FUTURE_APPEND",
        originating_chain="E19-R20-Q20-F20-H20-E20",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-registry", type=Path, default=DEFAULT_REGISTRY_ROOT)
    parser.add_argument("--working-registry", type=Path, required=True)
    parser.add_argument("--append-count", type=int, default=48)
    parser.add_argument("--freeze-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_registry.resolve(strict=True)
    if args.working_registry.exists() or args.output.exists():
        raise FileExistsError("registry simulation targets must be new")
    if not 1 <= args.append_count <= 96:
        raise ValueError("registry simulation append count must be in 1..96")
    verify_disclosed_java_registry(source)
    original = load_disclosed_java_registry(source)
    # The entry filenames are their immutable hashes; bind every pre-append byte
    # so the simulation proves prefix preservation, including the original six.
    original_bytes = {
        path.name: bytes_hash(path.read_bytes())
        for path in (source / "entries").glob("*.json")
    }
    shutil.copytree(source, args.working_registry)
    manifest, receipt = append_disclosed_java_entries_v2(
        args.working_registry,
        tuple(_entry(index) for index in range(args.append_count)),
        acquisition_run_id="m336e.disclosed-registry-simulation.v1",
        f20_sha=args.freeze_sha,
    )
    verify_disclosed_java_registry(args.working_registry)
    current = load_disclosed_java_registry(args.working_registry)
    unchanged = all(
        bytes_hash((args.working_registry / "entries" / name).read_bytes()) == digest
        for name, digest in original_bytes.items()
    )
    if (
        len(original) != 30
        or len(current) != 30 + args.append_count
        or not unchanged
        or manifest.entry_hashes[:30] != tuple(item.entry_hash for item in original)
    ):
        raise ValueError("registry simulation did not preserve the exact E19 prefix")
    args.output.mkdir(parents=True)
    (args.output / "append_receipt.json").write_text(
        canonical_json(asdict(receipt)) + "\n", encoding="utf-8", newline="\n"
    )
    body = {
        "schema_version": 1,
        "previous_entry_count": len(original),
        "appended_entry_count": args.append_count,
        "resulting_entry_count": len(current),
        "all_previous_entry_bytes_unchanged": unchanged,
        "original_six_entries_preserved": True,
        "exact_prefix_preserved": True,
        "resulting_manifest_hash": manifest.manifest_hash,
        "append_receipt_hash": receipt.receipt_hash,
        "status": "PASS",
    }
    (args.output / "verification.json").write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
