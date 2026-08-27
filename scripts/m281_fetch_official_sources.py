"""Research/build-time acquisition of the allowlisted M-28.1 official sources."""

from __future__ import annotations

import argparse
import json
import ssl
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from ai_brain.stage2.domains.chemistry.source_derivation import (
    MAX_SOURCE_BYTES,
    OFFICIAL_SOURCE_SPECS,
)
from ai_brain.stage2.facts.canonical import bytes_hash

ALLOWED_HOSTS = frozenset({"iupac.org", "www.ciaaw.org", "www.bipm.org"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipts = []
    context = ssl.create_default_context()
    for spec in OFFICIAL_SOURCE_SPECS:
        request = urllib.request.Request(
            spec["url"], headers={"User-Agent": "ai-brain-m281-source-verifier/1.0"}
        )
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            final_url = response.geturl()
            if urlparse(final_url).hostname not in ALLOWED_HOSTS:
                raise RuntimeError(f"source redirected outside allowlist: {final_url}")
            content = response.read(MAX_SOURCE_BYTES + 1)
        if len(content) > MAX_SOURCE_BYTES:
            raise RuntimeError(f"source exceeds bounded download size: {spec['url']}")
        digest = bytes_hash(content)
        if digest != spec["sha256"]:
            raise RuntimeError(
                f"unexpected content hash for {spec['filename']}: {digest}"
            )
        (output / spec["filename"]).write_bytes(content)
        receipts.append(
            {
                "source_id": spec["source_id"],
                "requested_url": spec["url"],
                "final_url": final_url,
                "sha256": digest,
                "size": len(content),
                "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
    receipt = args.receipt or output.parent / "source_acquisition_receipt.json"
    with receipt.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(receipts, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
