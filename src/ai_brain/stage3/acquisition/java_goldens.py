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
    unsupported_reason: str | None
    negative_kind: str | None
    golden_hash: str


@dataclass(frozen=True)
class JavaGoldenManifest:
    schema_version: int
    authoring_implementation: str
    sealed_before_proposals: bool
    source_manifest_hash: str
    target_census_hash: str | None
    oracle_implementation_hash: str | None
    goldens: tuple[JavaGoldenLocation, ...]
    positive_count: int
    negative_count: int
    semantic_negative_count: int
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
    expected_top_v1 = {
        "schema_version",
        "authoring_implementation",
        "sealed_before_proposals",
        "source_manifest_hash",
        "goldens",
        "positive_count",
        "manifest_hash",
    }
    expected_top_v2 = expected_top_v1 | {
        "target_census_hash",
        "oracle_implementation_hash",
        "negative_count",
        "semantic_negative_count",
    }
    if frozenset(row) not in {
        frozenset(expected_top_v1),
        frozenset(expected_top_v2),
    }:
        raise ValueError("Java golden manifest schema mismatch")
    goldens = []
    expected_fields_v2 = {
        item.name for item in JavaGoldenLocation.__dataclass_fields__.values()
    }
    expected_fields_v1 = expected_fields_v2 - {"unsupported_reason", "negative_kind"}
    for item in row["goldens"]:
        if frozenset(item) not in {
            frozenset(expected_fields_v1),
            frozenset(expected_fields_v2),
        }:
            raise ValueError("Java golden location schema mismatch")
        values = {
            "unsupported_reason": None,
            "negative_kind": None,
            **item,
            "nested_type_path": tuple(item["nested_type_path"]),
        }
        golden = JavaGoldenLocation(**values)
        body = dict(item)
        claimed = body.pop("golden_hash")
        if content_hash(body) != claimed:
            raise ValueError("Java golden location hash mismatch")
        goldens.append(golden)
    manifest = JavaGoldenManifest(
        schema_version=row["schema_version"],
        authoring_implementation=row["authoring_implementation"],
        sealed_before_proposals=row["sealed_before_proposals"],
        source_manifest_hash=row["source_manifest_hash"],
        target_census_hash=row.get("target_census_hash"),
        oracle_implementation_hash=row.get("oracle_implementation_hash"),
        goldens=tuple(goldens),
        positive_count=row["positive_count"],
        negative_count=row.get("negative_count", 0),
        semantic_negative_count=row.get("semantic_negative_count", 0),
        manifest_hash=row["manifest_hash"],
    )
    verify_java_golden_manifest(manifest)
    return manifest


def verify_java_golden_manifest(manifest: JavaGoldenManifest) -> None:
    """Recompute every seal so in-memory callers cannot forge golden objects."""

    for golden in manifest.goldens:
        body = asdict(golden)
        claimed = body.pop("golden_hash")
        if manifest.schema_version == 1:
            body.pop("unsupported_reason")
            body.pop("negative_kind")
        if content_hash(body) != claimed:
            raise ValueError("Java golden location hash mismatch")
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    if manifest.schema_version == 1:
        body["goldens"] = tuple(
            {
                key: value
                for key, value in asdict(golden).items()
                if key not in {"unsupported_reason", "negative_kind"}
            }
            for golden in manifest.goldens
        )
        for field in (
            "target_census_hash",
            "oracle_implementation_hash",
            "negative_count",
            "semantic_negative_count",
        ):
            body.pop(field)
    if (
        content_hash(body) != claimed
        or manifest.schema_version not in {1, 2}
        or not manifest.sealed_before_proposals
        or manifest.positive_count
        != sum(item.expected_supported for item in manifest.goldens)
        or manifest.negative_count
        != sum(not item.expected_supported for item in manifest.goldens)
        or len({item.golden_id for item in manifest.goldens}) != len(manifest.goldens)
    ):
        raise ValueError("Java golden manifest is not sealed or complete")
    if manifest.schema_version == 2 and (
        not manifest.target_census_hash
        or not manifest.oracle_implementation_hash
        or manifest.semantic_negative_count
        != sum(item.negative_kind == "SEMANTIC" for item in manifest.goldens)
    ):
        raise ValueError("Java golden semantic census is incomplete")
