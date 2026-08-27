"""Versioned chemistry domain manifest construction and verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.models import FormulaLimits
from ai_brain.stage2.domains.chemistry.sources import source_manifest
from ai_brain.stage2.domains.chemistry.version import (
    CHEMISTRY_ATOMIC_WEIGHT_POLICY,
    CHEMISTRY_CALCULATION_POLICY_VERSION,
    CHEMISTRY_DOMAIN_SCHEMA_VERSION,
    CHEMISTRY_DOMAIN_VERSION,
    CHEMISTRY_FORMULA_GRAMMAR_VERSION,
    CHEMISTRY_RENDERING_VERSION,
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
    reproducible = {
        "domain_version": CHEMISTRY_DOMAIN_VERSION,
        "domain_schema_version": CHEMISTRY_DOMAIN_SCHEMA_VERSION,
        "source_policy_version": CHEMISTRY_SOURCE_POLICY_VERSION,
        "source_snapshots": source_manifest(source_dir),
        "supported_elements": symbols,
        "atomic_weight_policy": CHEMISTRY_ATOMIC_WEIGHT_POLICY,
        "formula_grammar_version": CHEMISTRY_FORMULA_GRAMMAR_VERSION,
        "formula_limits": FormulaLimits(),
        "calculation_policy_version": CHEMISTRY_CALCULATION_POLICY_VERSION,
        "rendering_version": CHEMISTRY_RENDERING_VERSION,
        "unit_policy": {
            "mass": ("g", "kg"),
            "amount": ("mol", "mmol"),
            "molar_mass": ("g/mol", "kg/mol"),
            "entities": ("atoms", "molecules", "formula_units"),
        },
        "rounding_policy": "DECIMAL_EXACT_INTERNAL_RENDER_6_SIGNIFICANT",
        "tool_manifest_hashes": tool_manifest_hashes,
        "router_grammar_version": "1.0",
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
    if (
        body["domain_version"] != CHEMISTRY_DOMAIN_VERSION
        or body["domain_schema_version"] != CHEMISTRY_DOMAIN_SCHEMA_VERSION
    ):
        raise ValueError("incompatible chemistry domain pack")
    if body["fact_memory_snapshot_hash"] != memory.database.snapshot_hash():
        raise ValueError("chemistry domain manifest has stale FactMemory")
    expected_sources = source_manifest(source_dir)
    if tuple(body["source_snapshots"]) != expected_sources:
        raise ValueError("chemistry source snapshot changed")
    reproducible = {
        key: value
        for key, value in body.items()
        if key not in {"reproducible_content_hash", "fact_memory_snapshot_hash"}
    }
    if content_hash(reproducible) != body["reproducible_content_hash"]:
        raise ValueError("chemistry reproducible content hash mismatch")


def write_domain_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(canonicalize(manifest), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def load_domain_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _supported_symbols(memory: FactMemory) -> tuple[str, ...]:
    with memory.database.connect() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM claims WHERE predicate_id = 'element_symbol' ORDER BY subject_entity_id"
        ).fetchall()
    return tuple(json.loads(row[0])["object_value"]["value"] for row in rows)
