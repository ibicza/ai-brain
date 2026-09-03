"""Rebuild the permanent disclosed M-34.4 Java corpus denylist."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

ARCHIVE_HASHES = (
    "1f51af8452a6160a30dbcd8c93e3c69fa165f8adbbac1cc9aac7b0006f3f8c9b",
    "5fdcac21ad329766054a95367d7583dfcdca737d221d5e01a5f2a198c04c6b18",
)


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    root = project / "evaluation/m344_final_java/source_snapshots"
    paths = tuple(
        sorted(
            root.rglob("*.java"),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )
    entries = []
    for path in paths:
        raw = path.read_bytes()
        canonical = (
            raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").rstrip()
            + "\n"
        )
        entries.append(
            (
                path.relative_to(root).as_posix(),
                bytes_hash(raw),
                bytes_hash(canonical.encode("utf-8")),
            )
        )
    production = json.loads(
        (project / "evaluation/m344_final_java/production_output.json").read_text(
            encoding="utf-8"
        )
    )
    by_source = defaultdict(list)
    for item in production["candidate_rows"]:
        fingerprint = content_hash(
            (
                item["receiver_type"],
                item["member_kind"],
                item["member_name"],
                item["canonical_source_signature"],
                item["erased_jvm_descriptor"],
            )
        )
        by_source[item["source_unit_id"]].append(fingerprint)
    declaration_manifests = tuple(
        (path, content_hash(tuple(sorted(values))))
        for path, values in sorted(by_source.items())
    )
    body = {
        "schema_version": 1,
        "classification": "DISCLOSED_DEVELOPMENT_REGRESSION_ONLY",
        "source_file_count": len(entries),
        "archive_hashes": ARCHIVE_HASHES,
        "raw_source_hashes": tuple(sorted({item[1] for item in entries})),
        "canonical_text_hashes": tuple(sorted({item[2] for item in entries})),
        "source_tree_hash": "a1da5983e0ab2ba64614d4e1bd69ada1953dfb3b86b8627dcfc317be89378192",
        "content_tree_manifest_hash": content_hash(entries),
        "selected_relative_path_manifest_hash": content_hash(
            tuple(item[0] for item in entries)
        ),
        "path_hash_manifest": tuple(entries),
        "declaration_manifest_hashes": declaration_manifests,
        "declaration_fingerprint_manifest_hash": content_hash(declaration_manifests),
    }
    output = (
        project
        / "src/ai_brain/stage3/acquisition/data/m335_disclosed_corpus_denylist.json"
    )
    output.write_text(
        canonical_json({**body, "manifest_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
