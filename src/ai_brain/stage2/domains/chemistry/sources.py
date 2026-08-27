"""Frozen M-28.2 source-chain loading and integrity metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.source_derivation import (
    load_derivations,
    load_derived_documents,
    load_source_chain,
    verify_source_chain,
)

SOURCE_FILES = (
    "iupac_elements_2022.json",
    "ciaaw_atomic_weights_2024.json",
    "bipm_si_mole_2026.json",
    "ru_element_names_policy_v1.json",
)


def default_source_dir() -> Path:
    return Path("artifacts/domains/chemistry/m282/sources")


def load_frozen_sources(source_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    return load_derived_documents((source_dir or default_source_dir()).resolve())


def source_manifest(source_dir: Path | None = None) -> dict[str, Any]:
    return load_source_chain((source_dir or default_source_dir()).resolve())


__all__ = [
    "SOURCE_FILES",
    "default_source_dir",
    "load_derivations",
    "load_frozen_sources",
    "source_manifest",
    "verify_source_chain",
]
