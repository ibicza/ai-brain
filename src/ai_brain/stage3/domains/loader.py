from __future__ import annotations

import json
from pathlib import Path

from ai_brain.stage3.capabilities.models import CapabilityRequirement
from ai_brain.stage3.domains.manifest import *
from ai_brain.stage3.domains.pack import *
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.serialization import load_record

_FILES = {
    "manifest.json",
    "knowledge.jsonl",
    "concept_graph.json",
    "exercise_families.json",
    "capability_requirements.json",
    "adapter_bindings.json",
    "evaluation_manifest.json",
    "source_bindings.json",
    "pack_manifest.json",
}


def load_pack(root: Path) -> DomainPack:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError("domain pack directory is missing")
    entries = tuple(root.iterdir())
    for item in entries:
        if item.is_symlink():
            raise ValueError("domain pack symlinks are forbidden")
        if not item.is_file():
            raise ValueError(f"unexpected domain pack entry: {item.name}")
    names = {item.name for item in entries}
    missing = _FILES - names
    if missing:
        raise ValueError(f"domain pack files missing: {sorted(missing)}")
    unexpected = names - (_FILES | {"approval.json"})
    if unexpected:
        raise ValueError(f"unexpected domain pack files: {sorted(unexpected)}")
    for name in _FILES:
        if (root / name).stat().st_size > 64 * 1024 * 1024:
            raise ValueError("domain pack file exceeds resource policy")
    manifest_row = _read(root / "manifest.json")
    requirements = tuple(
        CapabilityRequirement(**x) for x in _read(root / "capability_requirements.json")
    )
    manifest = DomainPackManifest(
        **{
            **manifest_row,
            "supported_languages": tuple(manifest_row["supported_languages"]),
            "subject_tags": tuple(manifest_row["subject_tags"]),
            "knowledge_record_hashes": tuple(manifest_row["knowledge_record_hashes"]),
            "exercise_family_hashes": tuple(manifest_row["exercise_family_hashes"]),
            "source_binding_hashes": tuple(manifest_row["source_binding_hashes"]),
            "required_capabilities": requirements,
            "adapter_binding_hashes": tuple(manifest_row["adapter_binding_hashes"]),
            "dependency_packs": tuple(manifest_row["dependency_packs"]),
        }
    )
    lines = (root / "knowledge.jsonl").read_text(encoding="utf-8").splitlines()
    if len(lines) > 100_000 or any(
        len(line.encode("utf-8")) > 4 * 1024 * 1024 for line in lines
    ):
        raise ValueError("knowledge JSONL exceeds resource policy")
    records = tuple(load_record(line) for line in lines if line.strip())
    graph_row = _read(root / "concept_graph.json")
    graph = ConceptGraph(
        tuple(ConceptNode(**x) for x in graph_row["nodes"]),
        tuple(
            ConceptEdge(**{**x, "kind": ConceptEdgeKind(x["kind"])})
            for x in graph_row["edges"]
        ),
        graph_row["schema_version"],
        graph_row["graph_hash"],
    )
    families = tuple(
        ExerciseFamilyBinding(
            **{
                **x,
                "concept_ids": tuple(x["concept_ids"]),
                "required_capabilities": tuple(x["required_capabilities"]),
                "difficulty_structure": tuple(x["difficulty_structure"]),
            }
        )
        for x in _read(root / "exercise_families.json")
    )
    adapters = tuple(
        AdapterBinding(
            **{
                **x,
                "capability_ids": tuple(x["capability_ids"]),
                "allowed_contexts": tuple(x["allowed_contexts"]),
                "compatible_pack_versions": tuple(x["compatible_pack_versions"]),
            }
        )
        for x in _read(root / "adapter_bindings.json")
    )
    sources = tuple(
        SourceBinding(
            **{
                **x,
                "fact_memory_refs": tuple(x["fact_memory_refs"]),
                "claim_refs": tuple(x["claim_refs"]),
                "evidence_hashes": tuple(x["evidence_hashes"]),
                "source_hashes": tuple(x["source_hashes"]),
                "derivation_hashes": tuple(x["derivation_hashes"]),
            }
        )
        for x in _read(root / "source_bindings.json")
    )
    value = DomainPack(
        str(root),
        manifest,
        records,
        graph,
        families,
        adapters,
        sources,
        _read(root / "evaluation_manifest.json"),
    )
    validate_pack(value)
    pack_manifest = _read(root / "pack_manifest.json")
    if pack_manifest != {
        "domain_id": manifest.domain_id,
        "pack_content_hash": manifest.pack_content_hash,
        "pack_version": manifest.pack_version,
        "schema_version": manifest.schema_version,
    }:
        raise ValueError("outer pack manifest mismatch")
    return value


def _read(path: Path):
    def strict_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key in domain pack")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_object)
