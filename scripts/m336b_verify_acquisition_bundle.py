"""Verify the sealed one-shot M-33.6b acquisition bundle on a platform."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    load_source_artifact_provenance_envelope,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.bundle_root.resolve(strict=True)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    body = dict(manifest)
    claimed = body.pop("manifest_hash")
    if content_hash(body) != claimed:
        raise ValueError("sealed acquisition manifest hash mismatch")
    rows = tuple(
        (path.relative_to(root).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )
    if rows != tuple(tuple(item) for item in manifest["files"]):
        raise ValueError("sealed acquisition bundle file rows differ")
    if content_hash(rows) != manifest["bundle_tree_hash"]:
        raise ValueError("sealed acquisition bundle tree hash mismatch")
    provenance_paths = tuple(sorted(root.glob("candidates/*/provenance.json")))
    envelopes = tuple(
        load_source_artifact_provenance_envelope(path.read_bytes())
        for path in provenance_paths
    )
    report_body = {
        "schema_version": 1,
        "platform": args.platform,
        "bundle_tree_hash": manifest["bundle_tree_hash"],
        "file_count": len(rows),
        "provenance_envelope_count": len(envelopes),
        "provenance_envelope_hashes": tuple(item.envelope_hash for item in envelopes),
        "status": "PASS" if len(envelopes) == 6 else "FAIL",
    }
    report = {**report_body, "report_hash": content_hash(report_body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    if report_body["status"] != "PASS":
        raise SystemExit("sealed acquisition bundle is incomplete")


if __name__ == "__main__":
    main()
