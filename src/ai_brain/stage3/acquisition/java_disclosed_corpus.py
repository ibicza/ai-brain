"""Permanent M-34.4 disclosed-development-corpus denylist."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    load_disclosed_java_registry,
)

_PATH = Path(__file__).with_name("data") / "m335_disclosed_corpus_denylist.json"
_M336A_PATH = (
    Path(__file__).with_name("data") / "m336a_disclosed_candidate_denylist.json"
)


def load_m335_disclosed_corpus_denylist() -> dict:
    return dict(_load_m335_disclosed_corpus_denylist())


@cache
def _load_m335_disclosed_corpus_denylist() -> dict:
    row = json.loads(_PATH.read_text(encoding="utf-8"))
    claimed = row.pop("manifest_hash")
    if content_hash(row) != claimed:
        raise ValueError("M-33.5 disclosed-corpus denylist hash mismatch")
    return {**row, "manifest_hash": claimed}


def assert_not_disclosed_java_archive(archive_hash: str) -> None:
    values = load_disclosed_java_corpus_denylist()
    if archive_hash in values["archive_hashes"]:
        raise ValueError("disclosed development archive is forbidden for final use")


def load_m336a_disclosed_candidate_denylist() -> dict:
    return dict(_load_m336a_disclosed_candidate_denylist())


@cache
def _load_m336a_disclosed_candidate_denylist() -> dict:
    row = json.loads(_M336A_PATH.read_text(encoding="utf-8"))
    claimed = row.pop("manifest_hash")
    if content_hash(row) != claimed:
        raise ValueError("M-33.6a disclosed-candidate denylist hash mismatch")
    return {**row, "manifest_hash": claimed}


def load_disclosed_java_corpus_denylist() -> dict:
    """Return the accumulated M-33.5 + M-33.6 disclosed-material denylist."""

    return dict(_load_disclosed_java_corpus_denylist())


def _load_disclosed_java_corpus_denylist() -> dict:

    prior = load_m335_disclosed_corpus_denylist()
    current = load_m336a_disclosed_candidate_denylist()
    registry = load_disclosed_java_registry()
    body = {
        "schema_version": 3,
        "classification": "DISCLOSED_DEVELOPMENT_REGRESSION_ONLY",
        "coordinates": tuple(
            sorted({*current["coordinates"], *(item.coordinate for item in registry)})
        ),
        "source_archive_urls": tuple(
            sorted(
                {
                    *current["source_archive_urls"],
                    *(item.source_url for item in registry),
                }
            )
        ),
        "archive_hashes": tuple(
            sorted(
                {
                    *prior["archive_hashes"],
                    *current["archive_hashes"],
                    *(item.archive_hash for item in registry),
                }
            )
        ),
        "pom_hashes": tuple(
            sorted({*current["pom_hashes"], *(item.pom_hash for item in registry)})
        ),
        "raw_source_hashes": tuple(
            sorted(
                {
                    *prior["raw_source_hashes"],
                    *current["raw_source_hashes"],
                    *(value for item in registry for value in item.raw_source_hashes),
                }
            )
        ),
        "canonical_text_hashes": tuple(
            sorted(
                {
                    *prior["canonical_text_hashes"],
                    *current["canonical_text_hashes"],
                    *(
                        value
                        for item in registry
                        for value in item.canonical_source_hashes
                    ),
                }
            )
        ),
        "source_tree_hashes": tuple(
            sorted(
                {
                    prior["source_tree_hash"],
                    *current["source_tree_hashes"],
                    *(item.source_tree_hash for item in registry),
                }
            )
        ),
        "selected_path_manifest_hashes": tuple(
            sorted(
                {
                    prior["selected_relative_path_manifest_hash"],
                    *current["selected_path_manifest_hashes"],
                    *(item.selected_path_manifest_hash for item in registry),
                }
            )
        ),
        "declaration_fingerprints": tuple(
            sorted(
                {
                    *prior["declaration_fingerprints"],
                    *current["declaration_fingerprints"],
                    *(
                        value
                        for item in registry
                        for value in item.declaration_fingerprints
                    ),
                }
            )
        ),
        "scm_revision_hashes": tuple(
            sorted(
                {
                    *current["scm_revision_hashes"],
                    *(item.scm_revision for item in registry),
                }
            )
        ),
        "correspondence_hashes": tuple(
            sorted(
                {
                    *current["correspondence_hashes"],
                    *(item.correspondence_hash for item in registry),
                }
            )
        ),
        "registry_entry_hashes": tuple(sorted(item.entry_hash for item in registry)),
    }
    return {**body, "manifest_hash": content_hash(body)}


def disclosed_candidate_match(
    *,
    coordinate: str | None = None,
    archive_hash: str | None = None,
    source_url: str | None = None,
    raw_source_hashes=(),
    canonical_source_hashes=(),
    declaration_fingerprints=(),
    pom_hash: str | None = None,
    source_tree_hash: str | None = None,
    selected_path_manifest_hash: str | None = None,
    scm_revision: str | None = None,
    correspondence_hash: str | None = None,
) -> tuple[str, ...]:
    """Detect identity, byte, relocation/newline and declaration-level reuse."""

    return match_disclosed_material(
        coordinate=coordinate,
        archive_hash=archive_hash,
        source_url=source_url,
        raw_source_hashes=raw_source_hashes,
        canonical_source_hashes=canonical_source_hashes,
        declaration_fingerprints=declaration_fingerprints,
        pom_hash=pom_hash,
        source_tree_hash=source_tree_hash,
        selected_path_manifest_hash=selected_path_manifest_hash,
        scm_revision=scm_revision,
        correspondence_hash=correspondence_hash,
    ).matching_classes


@dataclass(frozen=True)
class DisclosedMaterialMatchReport:
    matching_classes: tuple[str, ...]
    match_count: int
    denied: bool
    report_hash: str


def match_disclosed_material(
    *,
    coordinate: str | None = None,
    archive_hash: str | None = None,
    source_url: str | None = None,
    raw_source_hashes=(),
    canonical_source_hashes=(),
    declaration_fingerprints=(),
    pom_hash: str | None = None,
    source_tree_hash: str | None = None,
    selected_path_manifest_hash: str | None = None,
    scm_revision: str | None = None,
    correspondence_hash: str | None = None,
) -> DisclosedMaterialMatchReport:
    values = _disclosed_match_sets()
    matches = []
    probes = (
        ("COORDINATE", coordinate, values["coordinates"]),
        ("ARCHIVE_BYTES", archive_hash, values["archive_hashes"]),
        ("SOURCE_URL", source_url, values["source_archive_urls"]),
        ("POM_BYTES", pom_hash, values["pom_hashes"]),
        ("SOURCE_TREE", source_tree_hash, values["source_tree_hashes"]),
        (
            "SELECTED_PATH_MANIFEST",
            selected_path_manifest_hash,
            values["selected_path_manifest_hashes"],
        ),
        ("SCM_REVISION", scm_revision, values["scm_revision_hashes"]),
        (
            "CORRESPONDENCE",
            correspondence_hash,
            values["correspondence_hashes"],
        ),
    )
    matches.extend(
        label for label, item, denied in probes if item is not None and item in denied
    )
    if set(raw_source_hashes) & values["raw_source_hashes"]:
        matches.append("RAW_SOURCE_BYTES")
    if set(canonical_source_hashes) & values["canonical_text_hashes"]:
        matches.append("CANONICAL_SOURCE_BYTES")
    if set(declaration_fingerprints) & values["declaration_fingerprints"]:
        matches.append("DECLARATION_FINGERPRINT")
    ordered = tuple(sorted(set(matches)))
    body = {
        "matching_classes": ordered,
        "match_count": len(ordered),
        "denied": bool(ordered),
    }
    return DisclosedMaterialMatchReport(**body, report_hash=content_hash(body))


def _disclosed_match_sets() -> dict[str, frozenset[str]]:
    values = _load_disclosed_java_corpus_denylist()
    return {
        key: frozenset(values[key])
        for key in (
            "coordinates",
            "archive_hashes",
            "source_archive_urls",
            "pom_hashes",
            "raw_source_hashes",
            "canonical_text_hashes",
            "source_tree_hashes",
            "selected_path_manifest_hashes",
            "declaration_fingerprints",
            "scm_revision_hashes",
            "correspondence_hashes",
        )
    }
