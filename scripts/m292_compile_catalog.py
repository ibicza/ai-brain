"""Compile the M-29.2 v3 educational catalog under offline authority."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.catalog_compiler import compile_catalog_v2
from ai_brain.stage2.facts.canonical import canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chemistry-root",
        type=Path,
        default=Path("artifacts/domains/chemistry/m29"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/education/m292/catalog_v3.json"),
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("runs/m292_compilation/audit.jsonl"),
    )
    parser.add_argument("--entry-count", type=int, default=2_000)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="m292-compile-") as directory:
        chemistry_copy = Path(directory) / "chemistry"
        shutil.copytree(args.chemistry_root.resolve(), chemistry_copy)
        service = ChemistryDomainService.open(chemistry_copy)
        print(
            canonical_json(
                compile_catalog_v2(
                    service,
                    args.output,
                    entry_count=args.entry_count,
                    audit_path=args.audit,
                )
            )
        )


if __name__ == "__main__":
    main()
