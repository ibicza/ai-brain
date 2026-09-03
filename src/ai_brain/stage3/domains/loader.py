from __future__ import annotations

import json
from pathlib import Path

from ai_brain.stage3.capabilities.models import CapabilityRequirement
from ai_brain.stage3.domains.aliases import (
    ALIAS_SEMANTICS_DEPENDENCY_PREFIX,
    ALIAS_SEMANTICS_FILENAME,
    AliasSemantics,
    AuthoritativeIdentity,
    ExactReferenceAlias,
    SearchAliasEntry,
    verify_alias_semantics,
)
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
    unexpected = names - (
        _FILES
        | {
            "approval.json",
            "java_evidence_closure.json",
            "java_production_closure.json",
            ALIAS_SEMANTICS_FILENAME,
        }
    )
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
    java_dependencies = tuple(
        item
        for item in manifest.dependency_packs
        if item.startswith(("java-evidence-closure.", "java-production-closure."))
    )
    java_artifacts = sum(
        (root / name).is_file()
        for name in ("java_evidence_closure.json", "java_production_closure.json")
    )
    if java_artifacts != len(java_dependencies) or len(java_dependencies) > 1:
        raise ValueError("Java evidence closure dependency mismatch")
    alias_dependencies = tuple(
        item
        for item in manifest.dependency_packs
        if item.startswith(ALIAS_SEMANTICS_DEPENDENCY_PREFIX)
    )
    alias_path = root / ALIAS_SEMANTICS_FILENAME
    if (
        len(alias_dependencies) != int(alias_path.is_file())
        or len(alias_dependencies) > 1
    ):
        raise ValueError("pack alias-semantics dependency mismatch")
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
                "document_hashes": tuple(x["document_hashes"]),
                "segment_hashes": tuple(x["segment_hashes"]),
                "field_evidence": tuple(tuple(item) for item in x["field_evidence"]),
            }
        )
        for x in _read(root / "source_bindings.json")
    )
    alias_semantics = None
    if alias_path.is_file():
        alias_row = _read(alias_path)
        alias_semantics = AliasSemantics(
            schema_version=alias_row["schema_version"],
            authoritative_identities=tuple(
                AuthoritativeIdentity(**item)
                for item in alias_row["authoritative_identities"]
            ),
            exact_references=tuple(
                ExactReferenceAlias(**item) for item in alias_row["exact_references"]
            ),
            search_aliases=tuple(
                SearchAliasEntry(
                    alias=item["alias"], record_ids=tuple(item["record_ids"])
                )
                for item in alias_row["search_aliases"]
            ),
            index_hash=alias_row["index_hash"],
        )
        if alias_dependencies != (
            ALIAS_SEMANTICS_DEPENDENCY_PREFIX + alias_semantics.index_hash,
        ):
            raise ValueError("pack binds another alias-semantics index")
        verify_alias_semantics(
            alias_semantics, tuple(item.knowledge_id for item in records)
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
        alias_semantics,
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
