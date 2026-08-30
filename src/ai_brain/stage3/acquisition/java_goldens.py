"""Strict loader for independently authored and sealed Java location goldens."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash


@dataclass(frozen=True)
class JavaGoldenLocation:
    golden_id: str
    source_unit_id: str
    document_bytes_hash: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    package_name: str | None
    top_level_type_name: str
    nested_type_path: tuple[str, ...]
    member_kind: str
    member_name: str
    canonical_source_signature: str
    erased_jvm_descriptor: str
    expected_supported: bool
    golden_hash: str


@dataclass(frozen=True)
class JavaGoldenManifest:
    schema_version: int
    authoring_implementation: str
    sealed_before_proposals: bool
    source_manifest_hash: str
    goldens: tuple[JavaGoldenLocation, ...]
    positive_count: int
    manifest_hash: str


def load_java_golden_manifest(path: Path) -> JavaGoldenManifest:
    def strict_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate Java golden JSON key")
            result[key] = value
        return result

    row = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_object)
    expected_top = {
        "schema_version",
        "authoring_implementation",
        "sealed_before_proposals",
        "source_manifest_hash",
        "goldens",
        "positive_count",
        "manifest_hash",
    }
    if set(row) != expected_top:
        raise ValueError("Java golden manifest schema mismatch")
    goldens = []
    expected_fields = {
        item.name for item in JavaGoldenLocation.__dataclass_fields__.values()
    }
    for item in row["goldens"]:
        if set(item) != expected_fields:
            raise ValueError("Java golden location schema mismatch")
        values = {**item, "nested_type_path": tuple(item["nested_type_path"])}
        golden = JavaGoldenLocation(**values)
        body = asdict(golden)
        claimed = body.pop("golden_hash")
        if content_hash(body) != claimed:
            raise ValueError("Java golden location hash mismatch")
        goldens.append(golden)
    manifest = JavaGoldenManifest(
        schema_version=row["schema_version"],
        authoring_implementation=row["authoring_implementation"],
        sealed_before_proposals=row["sealed_before_proposals"],
        source_manifest_hash=row["source_manifest_hash"],
        goldens=tuple(goldens),
        positive_count=row["positive_count"],
        manifest_hash=row["manifest_hash"],
    )
    verify_java_golden_manifest(manifest)
    return manifest


def verify_java_golden_manifest(manifest: JavaGoldenManifest) -> None:
    """Recompute every seal so in-memory callers cannot forge golden objects."""

    for golden in manifest.goldens:
        body = asdict(golden)
        claimed = body.pop("golden_hash")
        if content_hash(body) != claimed:
            raise ValueError("Java golden location hash mismatch")
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    if (
        content_hash(body) != claimed
        or manifest.schema_version != 1
        or not manifest.sealed_before_proposals
        or manifest.positive_count != len(manifest.goldens)
        or len({item.golden_id for item in manifest.goldens}) != len(manifest.goldens)
    ):
        raise ValueError("Java golden manifest is not sealed or complete")
