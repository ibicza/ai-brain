"""Build the exact-I18-bound M-33.6c final evidence manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--i18-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include", type=Path, action="append", required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    paths = set()
    for supplied in args.include:
        target = supplied.resolve(strict=True)
        if target.is_file():
            paths.add(target)
        else:
            paths.update(item for item in target.rglob("*") if item.is_file())
    paths.discard(output)
    entries = tuple(
        (path.relative_to(root).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(
            paths, key=lambda item: item.relative_to(root).as_posix().encode("utf-8")
        )
    )
    body = {
        "schema_version": 1,
        "i18_sha": args.i18_sha,
        "entries": entries,
        "entry_count": len(entries),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json({**body, "manifest_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
