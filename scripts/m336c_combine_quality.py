"""Combine two exact-I18 platform quality reports for readiness input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M-33.6c combined quality output exists")
    windows = _load(args.windows.resolve(strict=True))
    karina = _load(args.karina.resolve(strict=True))
    if windows["platform"] != "windows" or karina["platform"] != "karina":
        raise ValueError("M-33.6c quality platform binding mismatch")
    body = {
        "ruff_format": windows["ruff_format"] and karina["ruff_format"],
        "ruff_lint": windows["ruff_lint"] and karina["ruff_lint"],
        "windows_suite": windows["full_suite_pass"],
        "karina_suite": karina["full_suite_pass"],
        "windows_clean": windows["clean"],
        "karina_clean": karina["clean"],
        "branch_upstream_equal": windows["branch_upstream_equal"]
        and karina["branch_upstream_equal"],
        "new_untouched_corpus_acquired": windows["new_untouched_corpus_acquired"]
        or karina["new_untouched_corpus_acquired"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(body) + "\n", encoding="utf-8", newline="\n")
    if not all(
        value is True
        for key, value in body.items()
        if key != "new_untouched_corpus_acquired"
    ):
        raise SystemExit("M-33.6c combined quality failed")
    if body["new_untouched_corpus_acquired"]:
        raise SystemExit("M-33.6c used a new untouched corpus")


if __name__ == "__main__":
    main()
