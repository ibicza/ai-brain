"""Generate and validate the complete CPU-only M-25.1 fair benchmark."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.models import content_hash
from ai_brain.stage2.catalog import install_structural_catalog
from ai_brain.stage2.dataset import load_jsonl
from ai_brain.stage2.dispatch_validation import validate_all_skill_dispatches
from ai_brain.stage2.fair_benchmark import evaluate_fair_deterministic_baselines
from ai_brain.stage2.fair_dataset import generate_fair_query_dataset
from ai_brain.stage2.fair_diagnostics import diagnose_label_leakage
from ai_brain.stage2.registry import rebuild_from_rule_memory
from ai_brain.stage2.semantics import build_equivalence_groups
from ai_brain.stage2.skill_corpora import skill_corpus_hash

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "stage2" / "m251"
DEFAULT_RESULT = ROOT / "runs" / "m251_fair_acceptance.json"


def run(output_dir: Path, result_path: Path, *, small: bool = False) -> dict:
    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = (
        {
            key: 240
            for key in ("train", "validation", "calibration", "development", "blind")
        }
        if small
        else None
    )
    with tempfile.TemporaryDirectory(prefix="ai-brain-m251-") as directory:
        work = Path(directory)
        catalog = install_structural_catalog(work / "catalog")
        memory = RuleMemory.load(catalog.service.memory_path)
        registry = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
        registry_path = output_dir / "skill_registry_v2.json"
        registry.save(registry_path)
        query_dir = output_dir / "queries_v2"
        manifest = generate_fair_query_dataset(registry, query_dir, split_counts=counts)
        train = load_jsonl(query_dir / "train.jsonl")
        development = load_jsonl(query_dir / "development.jsonl")
        deterministic = evaluate_fair_deterministic_baselines(
            registry.active_records(), development
        )
        leakage = diagnose_label_leakage(train, development, registry.active_records())
        dispatch = validate_all_skill_dispatches(catalog, registry, work)
        groups = build_equivalence_groups(registry.active_records())
        no_torch = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import ai_brain.stage2; assert 'torch' not in sys.modules",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    result = {
        "milestone": "M-25.1",
        "status": "PASS",
        "git_sha": _git("rev-parse", "HEAD"),
        "platform": platform.platform(),
        "python": sys.version,
        "trusted_import_no_torch": no_torch.returncode == 0,
        "registry": {
            "structural_skill_count": registry.manifest.skill_count,
            "semantic_effect_class_count": registry.manifest.semantic_effect_class_count,
            "order_sensitive_class_count": registry.manifest.order_sensitive_class_count,
            "order_insensitive_class_count": registry.manifest.order_insensitive_class_count,
            "registry_hash": registry.manifest.registry_hash,
            "rule_memory_hash": registry.manifest.rule_memory_hash,
            "class_size_distribution": dict(
                sorted(
                    {
                        str(size): sum(group.member_count == size for group in groups)
                        for size in {group.member_count for group in groups}
                    }.items()
                )
            ),
        },
        "dataset": {
            "split_counts": manifest.split_counts,
            "evaluation_slices": manifest.evaluation_slices,
            "zero_query_skill_count": len(manifest.zero_query_skill_ids),
            "prompt_intersections": manifest.prompt_intersections,
            "blind_public_sha256": manifest.blind_public_sha256,
            "blind_targets_sha256": manifest.blind_targets_sha256,
            "query_surface_inventory_hash": manifest.query_surface_inventory_hash,
            "ood_split_definition_hash": manifest.ood_split_definition_hash,
        },
        "skill_corpus_hashes": {
            condition: skill_corpus_hash(registry.active_records(), condition)
            for condition in ("rich", "sanitized", "minimal")
        },
        "label_leakage": leakage,
        "deterministic_baselines": deterministic,
        "dispatch": {
            key: value
            for key, value in dispatch.items()
            if key not in {"rows", "representative_battery", "controlled_rows"}
        },
        "dispatch_evidence_hash": content_hash(dispatch),
        "duration_seconds": time.perf_counter() - started,
    }
    if result["registry"]["semantic_effect_class_count"] != 57:
        raise AssertionError("unexpected semantic class count")
    if result["dispatch"]["structural_dispatch_success"] != 89:
        raise AssertionError("all-skill dispatch failed")
    if leakage["wrapper_only"]["alert"]:
        raise AssertionError("wrapper-only leakage AUROC exceeded 0.60")
    if leakage["length_punctuation"]["alert"]:
        raise AssertionError("length/punctuation leakage AUROC exceeded 0.60")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (result_path.parent / "m251_all_skill_dispatch.json").write_text(
        json.dumps(dispatch, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--small", action="store_true")
    args = parser.parse_args()
    result = run(args.output_dir, args.result, small=args.small)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
