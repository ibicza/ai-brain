"""Acquire sealed M-33 selectors and emit inert UTF-8 snapshots plus receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.source_adapters import (
    download,
    safe_name,
    snapshots,
    strict_object,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTORS = ROOT / "config/m33_final_source_selectors.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selectors", type=Path, default=DEFAULT_SELECTORS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fetched-at", required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("final source snapshot output must be absent")
    selectors_bytes = args.selectors.read_bytes()
    selectors = json.loads(selectors_bytes, object_pairs_hook=strict_object)
    allowed = set(selectors["allowed_authority_domains"])
    maximum = selectors["resource_policy"]["maximum_download_bytes"]
    receipts = []
    for source_set in selectors["sets"]:
        target = args.output / source_set["bundle_id"]
        target.mkdir(parents=True)
        ordinal = 0
        for resource in source_set["resources"]:
            downloaded, headers, final_url = download(resource["url"], allowed, maximum)
            selected_snapshots = snapshots(resource, downloaded)
            for snapshot in selected_snapshots:
                ordinal += 1
                name = f"{ordinal:03d}-{safe_name(snapshot.name)}.txt"
                path = target / name
                path.write_bytes(snapshot.data)
                receipts.append(
                    {
                        "adapter": resource["adapter"],
                        "bundle_id": source_set["bundle_id"],
                        "downloaded_bytes_hash": bytes_hash(downloaded),
                        "etag": headers.get("etag"),
                        "fetched_at": args.fetched_at,
                        "final_url": final_url,
                        "last_modified": headers.get("last-modified"),
                        "license": source_set["license"],
                        "license_url": source_set["license_url"],
                        "selector": resource["selector"],
                        "snapshot_bytes_hash": bytes_hash(snapshot.data),
                        "snapshot_relative_path": path.relative_to(
                            args.output
                        ).as_posix(),
                        "source_selector": snapshot.source_selector,
                        "transformation_hash": content_hash(
                            {"transformation_id": snapshot.transformation_id}
                        ),
                        "transformation_id": snapshot.transformation_id,
                        "url": resource["url"],
                        "version": source_set["version"],
                        "word_count": len(snapshot.data.decode("utf-8").split()),
                    }
                )
    manifest = {
        "fetched_at": args.fetched_at,
        "receipts": receipts,
        "selectors_hash": bytes_hash(selectors_bytes),
    }
    (args.output / "source_receipts.json").write_text(
        canonical_json({**manifest, "manifest_hash": content_hash(manifest)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
