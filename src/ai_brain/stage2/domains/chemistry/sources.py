"""Frozen source extract loading and integrity metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

SOURCE_FILES = (
    "iupac_elements_2022.json",
    "ciaaw_atomic_weights_2024.json",
    "bipm_si_mole_2026.json",
    "ru_element_names_policy_v1.json",
)


def default_source_dir() -> Path:
    return Path("artifacts/domains/chemistry/m28/sources")


def load_frozen_sources(source_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    root = (source_dir or default_source_dir()).resolve()
    documents: dict[str, dict[str, Any]] = {}
    for name in SOURCE_FILES:
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError(f"missing or unsafe chemistry source extract: {name}")
        if path.stat().st_size > 1_000_000:
            raise ValueError(f"chemistry source extract exceeds size limit: {name}")
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8", errors="strict"))
        if not isinstance(document, dict) or not isinstance(
            document.get("source"), dict
        ):
            raise TypeError(f"malformed chemistry source extract: {name}")
        document["_integrity"] = {
            "file": name,
            "sha256": bytes_hash(raw),
            "semantic_hash": content_hash(document),
            "size": len(raw),
        }
        documents[name] = document
    return documents


def source_manifest(source_dir: Path | None = None) -> tuple[dict[str, Any], ...]:
    documents = load_frozen_sources(source_dir)
    return tuple(
        {
            **documents[name]["source"],
            **documents[name]["_integrity"],
        }
        for name in SOURCE_FILES
    )
