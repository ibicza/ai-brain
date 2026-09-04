"""Permanent M-34.4 disclosed-development-corpus denylist."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash

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


@cache
def _load_disclosed_java_corpus_denylist() -> dict:

    prior = load_m335_disclosed_corpus_denylist()
    current = load_m336a_disclosed_candidate_denylist()
    body = {
        "schema_version": 2,
        "classification": "DISCLOSED_DEVELOPMENT_REGRESSION_ONLY",
        "coordinates": tuple(sorted(current["coordinates"])),
        "source_archive_urls": tuple(sorted(current["source_archive_urls"])),
        "archive_hashes": tuple(
            sorted({*prior["archive_hashes"], *current["archive_hashes"]})
        ),
        "pom_hashes": tuple(sorted(current["pom_hashes"])),
        "raw_source_hashes": tuple(
            sorted({*prior["raw_source_hashes"], *current["raw_source_hashes"]})
        ),
        "canonical_text_hashes": tuple(
            sorted({*prior["canonical_text_hashes"], *current["canonical_text_hashes"]})
        ),
        "source_tree_hashes": tuple(
            sorted({prior["source_tree_hash"], *current["source_tree_hashes"]})
        ),
        "selected_path_manifest_hashes": tuple(
            sorted(
                {
                    prior["selected_relative_path_manifest_hash"],
                    *current["selected_path_manifest_hashes"],
                }
            )
        ),
        "declaration_fingerprints": tuple(
            sorted(
                {
                    *prior["declaration_fingerprints"],
                    *current["declaration_fingerprints"],
                }
            )
        ),
        "scm_revision_hashes": tuple(sorted(current["scm_revision_hashes"])),
        "correspondence_hashes": tuple(sorted(current["correspondence_hashes"])),
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
) -> tuple[str, ...]:
    """Detect identity, byte, relocation/newline and declaration-level reuse."""

    values = _disclosed_match_sets()
    matches = []
    probes = (
        ("COORDINATE", coordinate, values["coordinates"]),
        ("ARCHIVE_BYTES", archive_hash, values["archive_hashes"]),
        ("SOURCE_URL", source_url, values["source_archive_urls"]),
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
    return tuple(sorted(set(matches)))


@cache
def _disclosed_match_sets() -> dict[str, frozenset[str]]:
    values = _load_disclosed_java_corpus_denylist()
    return {
        key: frozenset(values[key])
        for key in (
            "coordinates",
            "archive_hashes",
            "source_archive_urls",
            "raw_source_hashes",
            "canonical_text_hashes",
            "declaration_fingerprints",
        )
    }
