"""Command-line tools for the trusted M-25 registry and candidate router."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.serde import write_artifact
from ai_brain.stage1.specifications import specification_from_dict
from ai_brain.stage2.catalog import install_structural_catalog
from ai_brain.stage2.dataset import generate_query_dataset, verify_blind_freeze
from ai_brain.stage2.models import RetrievalMode
from ai_brain.stage2.registry import SkillRegistry, rebuild_from_rule_memory
from ai_brain.stage2.service import Stage2Router


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-brain-stage2", description="Verified skill registry and safe routing."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build-catalog")
    build.add_argument("--output-dir", type=Path, required=True)

    validate = commands.add_parser("validate-registry")
    validate.add_argument("--registry", type=Path, required=True)
    validate.add_argument("--memory", type=Path, required=True)

    dataset = commands.add_parser("generate-query-dataset")
    dataset.add_argument("--registry", type=Path, required=True)
    dataset.add_argument("--output-dir", type=Path, required=True)
    dataset.add_argument("--seed", type=int, default=25_001)

    blind = commands.add_parser("verify-blind-freeze")
    blind.add_argument("--dataset-dir", type=Path, required=True)

    for name in ("search-controlled", "search-assistive", "search-structured"):
        search = commands.add_parser(name)
        search.add_argument("--registry", type=Path, required=True)
        search.add_argument("--memory", type=Path, required=True)
        search.add_argument("--stage1-audit", type=Path, required=True)
        search.add_argument("--stage2-audit", type=Path, required=True)
        if name == "search-structured":
            search.add_argument("--spec", type=Path, required=True)
        else:
            search.add_argument("--text", required=True)
            search.add_argument("--lang", choices=("ru", "en"))
        if name == "search-assistive":
            search.add_argument(
                "--mode",
                choices=("LEXICAL", "CHARACTER_NGRAM", "BM25"),
                default="BM25",
            )
            search.add_argument("--top-k", type=int, default=5)
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    if arguments.command == "build-catalog":
        installed = install_structural_catalog(arguments.output_dir)
        memory = RuleMemory.load(installed.service.memory_path)
        registry = rebuild_from_rule_memory(memory, receipts=installed.receipts)
        registry.save(arguments.output_dir / "skill_registry.json")
        for rule_id in sorted(installed.proposals):
            write_artifact(
                arguments.output_dir / "proposals" / f"{rule_id}.json",
                installed.proposals[rule_id],
            )
            write_artifact(
                arguments.output_dir / "receipts" / f"{rule_id}.json",
                installed.receipts[rule_id],
            )
        _print(
            {
                "active_skills": len(registry.active_records()),
                "registry_hash": registry.manifest.registry_hash,
            }
        )
        return
    if arguments.command == "validate-registry":
        registry = SkillRegistry.load(arguments.registry)
        registry.validate_against_rule_memory(RuleMemory.load(arguments.memory))
        _print({"status": "VALID", "manifest": asdict(registry.manifest)})
        return
    if arguments.command == "generate-query-dataset":
        registry = SkillRegistry.load(arguments.registry)
        manifest = generate_query_dataset(
            registry, arguments.output_dir, seed=arguments.seed
        )
        _print(asdict(manifest))
        return
    if arguments.command == "verify-blind-freeze":
        verify_blind_freeze(arguments.dataset_dir)
        _print({"status": "VALID"})
        return

    registry = SkillRegistry.load(arguments.registry)
    router = Stage2Router(
        registry=registry,
        memory_path=arguments.memory,
        stage1_audit_path=arguments.stage1_audit,
        stage2_audit_path=arguments.stage2_audit,
    )
    if arguments.command == "search-structured":
        specification = specification_from_dict(
            json.loads(arguments.spec.read_text(encoding="utf-8"))
        )
        query, result = router.search_structured(specification)
    elif arguments.command == "search-controlled":
        query, result = router.search_controlled(arguments.text, arguments.lang)
    else:
        query, result = router.search_assistive(
            arguments.text,
            arguments.lang,
            mode=RetrievalMode(arguments.mode),
            top_k=arguments.top_k,
        )
    _print({"query": asdict(query), "result": asdict(result)})


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
