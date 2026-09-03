"""Permanent M-34.4 disclosed-development-corpus denylist."""

from __future__ import annotations

import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash

_PATH = Path(__file__).with_name("data") / "m335_disclosed_corpus_denylist.json"


def load_m335_disclosed_corpus_denylist() -> dict:
    row = json.loads(_PATH.read_text(encoding="utf-8"))
    claimed = row.pop("manifest_hash")
    if content_hash(row) != claimed:
        raise ValueError("M-33.5 disclosed-corpus denylist hash mismatch")
    return {**row, "manifest_hash": claimed}


def assert_not_disclosed_java_archive(archive_hash: str) -> None:
    values = load_m335_disclosed_corpus_denylist()
    if archive_hash in values["archive_hashes"]:
        raise ValueError("disclosed development archive is forbidden for final use")
