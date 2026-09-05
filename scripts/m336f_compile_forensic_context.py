"""Compile one disclosed forensic context into normalized public-safe evidence."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_production_compiler import (
    build_java_production_compilation_probe,
    run_java_production_compilation_probe,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("fresh forensic compiler output already exists")
    sources = tuple(
        sorted(
            source_root.rglob("*.java"),
            key=lambda item: item.relative_to(source_root).as_posix().encode("utf-8"),
        )
    )
    if not sources:
        raise ValueError("forensic compilation context is empty")
    bindings = source_entry_binding_manifest_from_dict(_load(args.bindings))
    binding_by_unit = {item.selected_path: item for item in bindings.bindings}
    units = {item.relative_to(source_root).as_posix() for item in sources}
    if units - set(binding_by_unit):
        raise ValueError("forensic context lacks SourceEntryId bindings")
    for path in sources:
        unit = path.relative_to(source_root).as_posix()
        if (
            bytes_hash(path.read_bytes())
            != binding_by_unit[unit].source_entry_id.raw_source_sha256
        ):
            raise ValueError("forensic context source differs from SourceEntryId")
    probe = build_java_production_compilation_probe(args.javac.resolve(strict=True))
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="m336f-forensic-context-") as temporary:
        temporary_root = Path(temporary)
        store = AcquisitionStore.open_or_initialize(temporary_root / "store")
        bundle = ingest_bundle(
            sources,
            bundle_id="m336f-r20-forensic-context",
            domain_tags=("java-api",),
            imported_at="1970-01-01T00:00:00Z",
            source_root=source_root,
            store=store,
        )
        index = index_java_bundle(bundle, store)
        report = run_java_production_compilation_probe(
            bundle=bundle,
            store=store,
            source_index=index,
            probe=probe,
            javac_executable=args.javac.resolve(strict=True),
            source_entry_ids={
                unit: binding_by_unit[unit].source_entry_id.identity_hash
                for unit in sorted(units)
            },
        )
    declarations = tuple(
        {
            "source_unit_id": item.source_unit_id,
            "declaration_id": item.node_id,
            "member_kind": item.member_kind,
            "byte_start": item.declaration_span.byte_start,
            "byte_end": item.declaration_span.byte_end,
        }
        for item in index.declarations
    )
    declaration_body = {
        "schema_version": 1,
        "source_index_hash": index.index_hash,
        "declarations": declarations,
    }
    summary_body = {
        "schema_version": 1,
        "context": args.context,
        "source_file_count": len(sources),
        "compiler_probe_hash": probe.probe_hash,
        "compiler_identity_hash": probe.compiler_identity_hash,
        "compiler_report_hash": report.report_hash,
        "diagnostic_count": report.diagnostic_count,
        "unknown_scope_count": report.unknown_scope_count,
        "unmapped_diagnostic_count": report.unmapped_diagnostic_count,
        "source_unit_unbound_count": report.source_unit_unbound_count,
        "malformed_output_count": report.malformed_output_count,
    }
    _write(output / "compiler_probe.json", asdict(probe))
    _write(output / "compiler_report.json", asdict(report))
    _write(
        output / "declaration_index.json",
        {**declaration_body, "manifest_hash": content_hash(declaration_body)},
    )
    _write(
        output / "summary.json",
        {**summary_body, "summary_hash": content_hash(summary_body)},
    )


if __name__ == "__main__":
    main()
