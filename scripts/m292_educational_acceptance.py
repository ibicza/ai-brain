"""Run the M-29.2 hardening acceptance battery."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from ai_brain.stage2.education.acceptance_v3 import run_m292_acceptance
from ai_brain.stage2.education.service import EducationalService
from ai_brain.stage2.facts.canonical import canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chemistry-root",
        type=Path,
        default=Path("artifacts/domains/chemistry/m29"),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("artifacts/education/m30/catalog_v4.json"),
    )
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures/m292_synthetic_student_errors.jsonl"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="m292-acceptance-") as directory:
        chemistry_copy = Path(directory) / "chemistry"
        shutil.copytree(args.chemistry_root.resolve(), chemistry_copy)
        service = EducationalService.open(
            chemistry_copy, args.store, catalog_path=args.catalog
        )
        result = run_m292_acceptance(service, args.fixtures)
    resolved = args.output.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    print(canonical_json({"status": result["status"], "output": str(resolved)}))


if __name__ == "__main__":
    main()
