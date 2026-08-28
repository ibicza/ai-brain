"""Verified runtime loader for the precompiled educational catalog v2."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.catalog_anchor import verify_catalog_entry_anchor
from ai_brain.stage2.education.compilation_receipts import (
    verify_compilation_receipt,
    verify_compilation_receipt_structure,
)
from ai_brain.stage2.education.exercise_generation import verify_exercise_instance
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.models import (
    EducationalCatalogEntryV2,
    EducationalCatalogManifestV2,
    ExerciseFamily,
    SemanticExerciseKey,
)
from ai_brain.stage2.education.serialization import (
    compilation_receipt_from_dict,
    graph_from_dict,
    instance_from_dict,
    spec_from_dict,
)
from ai_brain.stage2.education.version import (
    EDUCATIONAL_CATALOG_SCHEMA_VERSION,
    EXERCISE_GENERATOR_VERSION,
    INCOMPATIBLE_V1_CATALOG,
)
from ai_brain.stage2.facts.canonical import canonical_json, content_hash


class EducationalCatalogV2:
    def __init__(
        self,
        manifest: EducationalCatalogManifestV2,
        entries: tuple[EducationalCatalogEntryV2, ...],
        split_manifests: tuple[dict[str, Any], ...],
    ) -> None:
        self.manifest = manifest
        self.entries = entries
        self.split_manifests = split_manifests
        self._entries_by_hash = {entry.entry_hash: entry for entry in entries}
        if len(self._entries_by_hash) != len(entries):
            raise ValueError("educational catalog contains duplicate entry anchors")

    @classmethod
    def load(cls, path: Path, service: ChemistryDomainService) -> EducationalCatalogV2:
        result = cls._read(path)
        result.verify(service)
        return result

    @classmethod
    def load_historical(cls, path: Path) -> EducationalCatalogV2:
        result = cls._read(path)
        result.verify_history()
        return result

    @classmethod
    def _read(cls, path: Path) -> EducationalCatalogV2:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(INCOMPATIBLE_V1_CATALOG)
        if resolved.stat().st_size > 512 * 1024 * 1024:
            raise ValueError("educational catalog exceeds the resource limit")
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != {
            "catalog_manifest",
            "entries",
            "split_manifests",
        }:
            raise ValueError(INCOMPATIBLE_V1_CATALOG)
        manifest = _manifest_from_dict(payload["catalog_manifest"])
        entries = tuple(_entry_from_dict(item) for item in payload["entries"])
        return cls(manifest, entries, tuple(payload["split_manifests"]))

    def verify(self, service: ChemistryDomainService) -> dict[str, Any]:
        historical = self.verify_history()
        manifest = service.manifest
        if (
            self.manifest.chemistry_domain_manifest_hash
            != manifest["domain_manifest_hash"]
            or self.manifest.fact_memory_snapshot_hash
            != manifest["fact_memory_snapshot_hash"]
            or self.manifest.source_chain_hash != manifest["source_chain_hash"]
            or self.manifest.generator_version != EXERCISE_GENERATOR_VERSION
        ):
            raise ValueError("precompiled educational catalog is stale")
        current_tools = tuple(service.registry.current_manifest_hashes())
        if self.manifest.tool_manifest_hashes != current_tools:
            raise ValueError("precompiled educational catalog tool set is stale")
        adapter = ChemistryEducationAdapter(service)
        for entry in self.entries:
            verify_compilation_receipt(
                entry.compilation_receipt,
                service,
                graph_hash=entry.graph.graph_hash,
                graph=entry.graph,
                spec=entry.exercise_spec,
            )
            adapter.verify_graph(entry.graph)
        return {**historical, "status": "VERIFIED"}

    def verify_history(self) -> dict[str, Any]:
        body = asdict(self.manifest)
        digest = body.pop("catalog_hash")
        if content_hash(body) != digest:
            raise ValueError("educational catalog manifest hash mismatch")
        if self.manifest.schema_version != EDUCATIONAL_CATALOG_SCHEMA_VERSION:
            raise ValueError(INCOMPATIBLE_V1_CATALOG)
        if self.manifest.entry_hashes != tuple(
            entry.entry_hash for entry in self.entries
        ):
            raise ValueError("educational catalog entry manifest mismatch")
        split_hashes = tuple(item.get("manifest_hash") for item in self.split_manifests)
        if self.manifest.split_manifest_hashes != split_hashes:
            raise ValueError("educational split manifest mismatch")
        semantic_hashes = set()
        for entry in self.entries:
            _verify_entry_hash(entry)
            verify_compilation_receipt_structure(entry.compilation_receipt)
            verify_derivation_graph(
                entry.graph, expected_source_result=entry.graph.source_result_artifact
            )
            verify_exercise_instance(
                entry.internal_instance, entry.exercise_spec, entry.graph
            )
            if (
                entry.semantic_key.semantic_key_hash
                != entry.internal_instance.semantic_key_hash
            ):
                raise ValueError("catalog semantic key mismatch")
            semantic_hashes.add(entry.semantic_key.semantic_key_hash)
        _verify_splits(self.split_manifests, semantic_hashes)
        return {
            "status": "HISTORY_VERIFIED",
            "entry_count": len(self.entries),
            "distinct_semantic_keys": len(semantic_hashes),
            "catalog_hash": self.manifest.catalog_hash,
        }

    def select(
        self,
        family: ExerciseFamily,
        *,
        seed: int,
        difficulty: int | None = None,
    ) -> EducationalCatalogEntryV2:
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("exercise seed must be a nonnegative integer")
        matches = tuple(
            entry
            for entry in self.entries
            if entry.exercise_spec.family == family
            and (
                difficulty is None or entry.exercise_spec.difficulty_tier == difficulty
            )
        )
        if not matches:
            raise ValueError("no precompiled exercise matches the request")
        return matches[seed % len(matches)]

    def by_entry_hash(self, entry_hash: str) -> EducationalCatalogEntryV2:
        entry = self._entries_by_hash.get(entry_hash)
        if entry is None:
            raise KeyError("unknown trusted educational catalog entry")
        return entry

    def find_tool(
        self, tool_id: str, arguments: dict[str, Any]
    ) -> EducationalCatalogEntryV2 | None:
        expected = canonical_json(arguments)
        for entry in self.entries:
            receipt = entry.compilation_receipt
            if (
                receipt.tool_id == tool_id
                and canonical_json(receipt.canonical_arguments) == expected
            ):
                return entry
        return None


def _manifest_from_dict(row: dict[str, Any]) -> EducationalCatalogManifestV2:
    if set(row) != set(EducationalCatalogManifestV2.__dataclass_fields__):
        raise ValueError("invalid educational catalog manifest schema")
    return EducationalCatalogManifestV2(
        **{
            **row,
            "tool_manifest_hashes": tuple(
                tuple(item) for item in row["tool_manifest_hashes"]
            ),
            "entry_hashes": tuple(row["entry_hashes"]),
            "split_manifest_hashes": tuple(row["split_manifest_hashes"]),
        }
    )


def _entry_from_dict(row: dict[str, Any]) -> EducationalCatalogEntryV2:
    if set(row) != set(EducationalCatalogEntryV2.__dataclass_fields__):
        raise ValueError("invalid educational catalog entry schema")
    semantic_row = row["semantic_key"]
    semantic = SemanticExerciseKey(
        **{
            **semantic_row,
            "exercise_family": ExerciseFamily(semantic_row["exercise_family"]),
            "numeric_givens": tuple(
                tuple(item) for item in semantic_row["numeric_givens"]
            ),
        }
    )
    return EducationalCatalogEntryV2(
        semantic_key=semantic,
        exercise_spec=spec_from_dict(row["exercise_spec"]),
        internal_instance=instance_from_dict(row["internal_instance"]),
        graph=graph_from_dict(row["graph"]),
        compilation_receipt=compilation_receipt_from_dict(row["compilation_receipt"]),
        entry_hash=row["entry_hash"],
    )


def _verify_entry_hash(entry: EducationalCatalogEntryV2) -> None:
    verify_catalog_entry_anchor(entry)


def _verify_splits(
    manifests: tuple[dict[str, Any], ...], semantic_hashes: set[str]
) -> None:
    axes = set()
    expected_universe = set(semantic_hashes)
    expected_hash = content_hash(tuple(sorted(expected_universe)))
    for manifest in manifests:
        body = dict(manifest)
        digest = body.pop("manifest_hash", None)
        if digest != content_hash(body):
            raise ValueError("educational split manifest hash mismatch")
        axis = manifest.get("axis")
        if axis in axes:
            raise ValueError("duplicate educational split axis")
        axes.add(axis)
        development_values = tuple(manifest.get("development", ()))
        final_values = tuple(manifest.get("final_validation", ()))
        development = set(development_values)
        final = set(final_values)
        intersection = len(development & final)
        if (
            not development
            or not final
            or len(development_values) != len(development)
            or len(final_values) != len(final)
            or intersection
        ):
            raise ValueError("educational split is not disjoint")
        if development | final != expected_universe:
            raise ValueError("educational split does not exactly cover its universe")
        if (
            manifest.get("intersection_count") != intersection
            or manifest.get("universe_kind") != "semantic_key_hash"
            or manifest.get("universe_hash") != expected_hash
            or manifest.get("universe_count") != len(expected_universe)
            or manifest.get("axis_kind")
            not in {"TRUE_CONTENT_HOLDOUT", "DETERMINISTIC_PARTITION"}
        ):
            raise ValueError("educational split universe metadata mismatch")
