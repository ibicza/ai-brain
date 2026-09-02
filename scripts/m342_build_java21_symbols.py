"""Build the checked-in Java 21 platform symbol inventory from a JDK ct.sym."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

RELEASE_CODE = "L"


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ct-sym", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.ct_sym.read_bytes()
    symbols = set()
    with zipfile.ZipFile(args.ct_sym) as archive:
        for name in archive.namelist():
            parts = name.split("/", 2)
            if (
                len(parts) != 3
                or RELEASE_CODE not in parts[0]
                or not name.endswith(".sig")
                or name.endswith("module-info.sig")
            ):
                continue
            symbol = parts[2][:-4].replace("/", ".").replace("$", ".")
            symbols.add(symbol)
    body = {
        "schema_version": 1,
        "inventory_id": "java-platform-release-21",
        "release": 21,
        "source_kind": "jdk-ct.sym-release-signatures",
        "source_ct_sym_sha256": hashlib.sha256(raw).hexdigest(),
        "symbols": sorted(symbols),
        "symbol_count": len(symbols),
    }
    output = {**body, "manifest_hash": digest(body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(output) + "\n", encoding="utf-8", newline="\n"
    )
    print(output["symbol_count"], output["manifest_hash"])


if __name__ == "__main__":
    main()
