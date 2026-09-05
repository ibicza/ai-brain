"""Materialize disclosed selected source plus its production-visible closure."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    java_compilation_closure_manifest_from_dict,
)


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-manifest", type=Path)
    parser.add_argument("--selected-root")
    parser.add_argument("--all-analysis-root")
    parser.add_argument("--closure-manifest", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("fresh compilation context output already exists")
    closure = java_compilation_closure_manifest_from_dict(_load(args.closure_manifest))
    closure_by_unit = {item.source_unit_id: item for item in closure.files}
    if (args.selected_manifest is None) == (args.all_analysis_root is None):
        raise ValueError(
            "choose exactly one selected manifest or complete analysis root"
        )
    if args.selected_manifest is not None:
        selected_value = _load(args.selected_manifest)
        selected = {
            item["selected_path"]
            for item in selected_value["files"]
            if args.selected_root is None
            or item["candidate_root"] == args.selected_root
        }
    else:
        selected = {
            item.source_unit_id
            for item in closure.files
            if item.candidate_root == args.all_analysis_root
        }
    if not selected or selected - set(closure_by_unit):
        raise ValueError("selected source is outside the compilation closure census")
    expanded = set(selected)
    for unit in sorted(selected):
        expanded.update(closure_by_unit[unit].closure_source_units)
    bindings = source_entry_binding_manifest_from_dict(_load(args.bindings))
    binding_by_unit = {item.selected_path: item for item in bindings.bindings}
    if expanded - set(binding_by_unit):
        raise ValueError("compilation context lacks SourceEntryId bindings")
    vault = args.vault.resolve(strict=True)
    output.mkdir(parents=True)
    rows = []
    for unit in sorted(expanded):
        binding = binding_by_unit[unit]
        raw = (vault / binding.vault_path).resolve(strict=True).read_bytes()
        if bytes_hash(raw) != binding.source_entry_id.raw_source_sha256:
            raise ValueError("compilation context source differs from SourceEntryId")
        target = output.joinpath(*unit.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        rows.append((unit, binding.source_entry_id.identity_hash, bytes_hash(raw)))
    distribution = tuple(
        sorted(Counter(unit.partition("/")[0] for unit in expanded).items())
    )
    body = {
        "schema_version": 1,
        "selected_file_count": len(selected),
        "closure_support_file_count": len(expanded - selected),
        "materialized_file_count": len(expanded),
        "root_distribution": distribution,
        "source_manifest_hash": content_hash(tuple(rows)),
    }
    (output.parent / f"{output.name}-manifest.json").write_text(
        canonical_json({**body, "manifest_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
