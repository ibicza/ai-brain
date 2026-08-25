"""Run and persist the M-25.1 complete trusted dispatch matrix."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage2.catalog import install_structural_catalog
from ai_brain.stage2.dispatch_validation import validate_all_skill_dispatches
from ai_brain.stage2.registry import rebuild_from_rule_memory

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "runs" / "m251_all_skill_dispatch.json"
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ai-brain-m251-dispatch-") as directory:
        work = Path(directory)
        catalog = install_structural_catalog(work / "catalog")
        memory = RuleMemory.load(catalog.service.memory_path)
        registry = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
        result = validate_all_skill_dispatches(catalog, registry, work)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}))


if __name__ == "__main__":
    main()
