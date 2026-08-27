"""Versioned chemistry domain manifest construction and verification."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.models import (
    ChemistryQuantityLimits,
    ChemistryRoundingSpec,
    FormulaLimits,
)
from ai_brain.stage2.domains.chemistry.sources import (
    source_manifest,
    verify_source_chain,
)
from ai_brain.stage2.domains.chemistry.version import (
    CHEMISTRY_ATOMIC_WEIGHT_POLICY,
    CHEMISTRY_CALCULATION_POLICY_VERSION,
    CHEMISTRY_DOMAIN_SCHEMA_VERSION,
    CHEMISTRY_DOMAIN_VERSION,
    CHEMISTRY_FORMULA_GRAMMAR_VERSION,
    CHEMISTRY_KNOWLEDGE_SNAPSHOT_VERSION,
    CHEMISTRY_RENDERING_VERSION,
    CHEMISTRY_RESULT_SCHEMA_VERSION,
    CHEMISTRY_SOURCE_POLICY_VERSION,
)
from ai_brain.stage2.facts.canonical import canonicalize, content_hash
from ai_brain.stage2.facts.memory import FactMemory


def build_domain_manifest(
    memory: FactMemory,
    source_dir: Path | None = None,
    tool_manifest_hashes: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any]:
    symbols = _supported_symbols(memory)
    chain = source_manifest(source_dir)
    source_rows = (
        *chain["official_snapshots"],
        *chain["local_policy_snapshots"],
        *chain["derived_extracts"],
    )
    source_record_bindings = tuple(
        {
            "source_id": row["source_id"],
            "record_hash": memory.get_source_record(row["source_id"]).record_hash,
            "snapshot_hash": memory.get_source_record(row["source_id"]).snapshot_hash,
            "source_kind": memory.get_source_record(row["source_id"]).source_kind.value,
            "source_family": memory.get_source_record(row["source_id"]).source_family,
        }
        for row in source_rows
    )
    reproducible = {
        "domain_version": CHEMISTRY_DOMAIN_VERSION,
        "domain_schema_version": CHEMISTRY_DOMAIN_SCHEMA_VERSION,
        "source_policy_version": CHEMISTRY_SOURCE_POLICY_VERSION,
        "source_chain": chain,
        "source_chain_version": chain["source_chain_version"],
        "source_chain_hash": chain["source_chain_hash"],
        "source_record_bindings": source_record_bindings,
        "official_source_snapshot_hashes": tuple(
            row["sha256"] for row in chain["official_snapshots"]
        ),
        "local_policy_snapshot_hashes": tuple(
            row["sha256"] for row in chain["local_policy_snapshots"]
        ),
        "derived_extract_hashes": tuple(
            row["sha256"] for row in chain["derived_extracts"]
        ),
        "source_derivation_hashes": tuple(
            row["derivation_hash"] for row in chain["derivations"]
        ),
        "source_derivation_methods": tuple(
            row["record"]["derivation_method"] for row in chain["derivations"]
        ),
        "field_extraction_evidence_hashes": tuple(
            evidence["evidence_hash"]
            for row in chain["derivations"]
            for evidence in row["record"]["field_level_mappings"]
        ),
        "official_source_category": "AUTHORITY_PUBLISHED_SNAPSHOT",
        "local_policy_category": "PROJECT_REVIEWED_LOCAL_POLICY",
        "upstream_source_state_policy": "ALL_REQUIRED_UPSTREAM_SOURCES_ACTIVE_V3",
        "knowledge_snapshot_version": CHEMISTRY_KNOWLEDGE_SNAPSHOT_VERSION,
        "result_schema_version": CHEMISTRY_RESULT_SCHEMA_VERSION,
        "bipm_baseline": {
            "title": "The International System of Units (SI), 9th edition",
            "version": "4.01",
            "publication_date": "2026-06-04",
            "doi": "10.59161/AUEZ1291",
        },
        "ciaaw_baseline": {
            "standard": "Standard Atomic Weights 2024",
            "abridged": "Abridged Standard Atomic Weights 2024",
        },
        "supported_elements": symbols,
        "atomic_weight_policy": CHEMISTRY_ATOMIC_WEIGHT_POLICY,
        "formula_grammar_version": CHEMISTRY_FORMULA_GRAMMAR_VERSION,
        "formula_limits": FormulaLimits(),
        "quantity_limits": ChemistryQuantityLimits(),
        "calculation_policy_version": CHEMISTRY_CALCULATION_POLICY_VERSION,
        "rendering_version": CHEMISTRY_RENDERING_VERSION,
        "atomic_weight_record_schema": "AtomicWeightRecordV2",
        "atomic_weight_modes": (
            "CONVENTIONAL_CLASSROOM",
            "NATURAL_VARIABILITY_ENVELOPE",
        ),
        "symbol_resolution_policy": "EXACT_CASE_SYMBOL_OR_CASEFOLDED_NAME_V2",
        "entity_count_semantics": {
            "bases": (
                "FORMULA_ENTITIES",
                "TOTAL_ATOMS_IN_FORMULA",
                "ATOMS_OF_ELEMENT_IN_FORMULA",
            ),
            "formula_required_for_total_atoms": True,
        },
        "unit_policy": {
            "mass": ("g", "kg"),
            "amount": ("mol", "mmol"),
            "molar_mass": ("g/mol", "kg/mol"),
            "entities": ("atoms", "molecules", "formula_units"),
        },
        "rounding_policy": asdict(ChemistryRoundingSpec()),
        "tool_manifest_hashes": tool_manifest_hashes,
        "router_grammar_version": "1.0",
        "provenance_limitations": (
            "IUPAC selected identity fields are REVIEWED_MANUAL_MAPPING",
            "BIPM selected mole fields are REVIEWED_MANUAL_MAPPING",
            "CIAAW selected atomic-weight fields are DETERMINISTIC_EXTRACTION",
            "RU names are a local POLICY_TRANSFORMATION, not IUPAC data",
        ),
    }
    body = {
        **reproducible,
        "reproducible_content_hash": content_hash(reproducible),
        "fact_memory_snapshot_hash": memory.database.snapshot_hash(),
    }
    return {**body, "domain_manifest_hash": content_hash(body)}


def verify_domain_manifest(
    manifest: dict[str, Any], memory: FactMemory, source_dir: Path | None = None
) -> None:
    body = dict(manifest)
    digest = body.pop("domain_manifest_hash", None)
    if content_hash(body) != digest:
        raise ValueError("chemistry domain manifest hash mismatch")
    if body.get("domain_schema_version") != CHEMISTRY_DOMAIN_SCHEMA_VERSION:
        raise ValueError("REBUILD_REQUIRED_FROM_VERIFIED_SOURCE_CHAIN_V3")
    if body.get("domain_version") != CHEMISTRY_DOMAIN_VERSION:
        raise ValueError("incompatible chemistry domain pack")
    if body["fact_memory_snapshot_hash"] != memory.database.snapshot_hash():
        raise ValueError("chemistry domain manifest has stale FactMemory")
    verify_source_chain((source_dir or Path(".")).resolve())
    expected_sources = source_manifest(source_dir)
    if body["source_chain"] != expected_sources:
        raise ValueError("chemistry source snapshot changed")
    if body.get("source_chain_hash") != expected_sources["source_chain_hash"]:
        raise ValueError("chemistry source-chain binding changed")
    for binding in body.get("source_record_bindings", ()):
        record = memory.get_source_record(binding["source_id"])
        if (
            binding["record_hash"] != record.record_hash
            or binding["snapshot_hash"] != record.snapshot_hash
            or binding["source_kind"] != record.source_kind.value
            or binding["source_family"] != record.source_family
        ):
            raise ValueError("chemistry FactMemory source binding changed")
    reproducible = {
        key: value
        for key, value in body.items()
        if key not in {"reproducible_content_hash", "fact_memory_snapshot_hash"}
    }
    if content_hash(reproducible) != body["reproducible_content_hash"]:
        raise ValueError("chemistry reproducible content hash mismatch")


def write_domain_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(
                canonicalize(manifest), ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n"
        )


def load_domain_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _supported_symbols(memory: FactMemory) -> tuple[str, ...]:
    return tuple(
        sorted(
            item.external_identifiers["symbol"]
            for item in memory.list_entities(entity_type="chemical_element")
        )
    )
