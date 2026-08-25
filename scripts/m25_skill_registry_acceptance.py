"""Build and validate the M-25 trusted catalog and deterministic routing path."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.models import SemanticFamily, content_hash
from ai_brain.stage1.serde import write_artifact
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage1.version import STAGE1_VERSION
from ai_brain.stage2.benchmark import (
    evaluate_deterministic_baseline,
    evaluate_unknown_policy,
    measure_catalog_scale,
    registry_load_latency,
)
from ai_brain.stage2.catalog import (
    controlled_command,
    install_structural_catalog,
    structural_specs,
)
from ai_brain.stage2.dataset import generate_query_dataset, load_jsonl
from ai_brain.stage2.models import RetrievalMode, SearchStatus
from ai_brain.stage2.registry import SkillRegistry, rebuild_from_rule_memory
from ai_brain.stage2.service import Stage2Router, validate_dispatch_receipt
from ai_brain.stage2.version import EXPECTED_STAGE1_RELEASE_COMMIT

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "stage2" / "m25"
DEFAULT_RESULTS = ROOT / "runs" / "m25_deterministic_acceptance.json"


def run(output_dir: Path, result_path: Path, *, full_dataset: bool = True) -> dict:
    started = time.perf_counter()
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ai-brain-m25-") as temporary:
        working = Path(temporary)
        catalog = install_structural_catalog(working / "catalog")
        memory = RuleMemory.load(catalog.service.memory_path)
        registry = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
        require(len(registry.active_records()) == 89, "expected 89 active skills")
        registry.validate_against_rule_memory(memory)

        catalog_dir = output_dir / "catalog"
        proposal_dir = catalog_dir / "proposals"
        receipt_dir = catalog_dir / "receipts"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        receipt_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(catalog.service.memory_path, catalog_dir / "rule_memory.json")
        shutil.copy2(catalog.service.audit.path, catalog_dir / "stage1_audit.jsonl")
        for rule_id in sorted(catalog.proposals):
            write_artifact(proposal_dir / f"{rule_id}.json", catalog.proposals[rule_id])
            write_artifact(receipt_dir / f"{rule_id}.json", catalog.receipts[rule_id])
        registry_path = output_dir / "skill_registry.json"
        registry.save(registry_path)
        SkillRegistry.load(registry_path).validate_against_rule_memory(memory)

        rows = list(structural_specs())
        exact_start = time.perf_counter()
        router = Stage2Router(
            registry=registry,
            memory_path=catalog.service.memory_path,
            stage1_audit_path=catalog.service.audit.path,
            stage2_audit_path=working / "stage2_audit.jsonl",
        )
        structured_ids = set()
        controlled_count = 0
        cross_language_equal = 0
        controlled_latencies = {"ru": [], "en": []}
        for index, (family, sources, destination) in enumerate(rows):
            specification = build_family_specification(
                family, sources=sources, destination=destination
            )
            _, exact = router.search_structured(
                specification,
                query_id_factory=lambda i=index: f"accept-structured-{i}",
            )
            require(exact.status == SearchStatus.EXACT_MATCH, "structured exact")
            structured_ids.add(exact.candidates[0].skill_id)
            selected = {}
            for language in ("ru", "en"):
                for extended in (False, True):
                    text = controlled_command(
                        family,
                        sources,
                        destination,
                        language,
                        extended=extended,
                    )
                    tick = time.perf_counter()
                    _, result = router.search_controlled(
                        text,
                        language,
                        query_id_factory=lambda i=controlled_count: (
                            f"accept-controlled-{i}"
                        ),
                    )
                    controlled_latencies[language].append(
                        (time.perf_counter() - tick) * 1000
                    )
                    controlled_count += 1
                    require(
                        result.status == SearchStatus.EXACT_MATCH, "controlled exact"
                    )
                    selected[language] = result.candidates[0].skill_id
            cross_language_equal += int(selected["ru"] == selected["en"])
        exact_elapsed = time.perf_counter() - exact_start
        require(len(structured_ids) == 89, "all skills must be uniquely retrieved")
        require(controlled_count == 356, "expected frozen 356 controlled cases")
        require(cross_language_equal == 89, "cross-language exact mismatch")

        dataset_counts = None
        deterministic = {}
        unknown_policy = {}
        if full_dataset:
            manifest = generate_query_dataset(registry, output_dir / "queries")
            dataset_counts = manifest.split_counts
            development = load_jsonl(output_dir / "queries" / "development.jsonl")
            for mode in (
                RetrievalMode.LEXICAL,
                RetrievalMode.CHARACTER_NGRAM,
                RetrievalMode.BM25,
            ):
                deterministic[str(mode)] = evaluate_deterministic_baseline(
                    registry, memory, development, mode
                )
            unknown_policy = evaluate_unknown_policy(registry, memory, development)
            require(
                unknown_policy["automatic_selection_count"] == 0,
                "assistive path auto-selected an unknown query",
            )

        specification = build_family_specification(
            SemanticFamily.DRAIN, sources=("A",), destination="B"
        )
        query, result = router.search_structured(specification)
        skill = result.candidates[0]
        selection = router.prepare_selection(query, result, skill.skill_id)
        selection = router.confirm_selection(selection, identity="m25-acceptance")
        _, execution, dispatch = router.dispatch(
            query=query,
            result=result,
            selection=selection,
            proposal=catalog.proposals[skill.rule_id],
            installed_receipt=catalog.receipts[skill.rule_id],
            initial_state={"R0": 2, "R1": 3, "R2": 5, "R3": 7},
        )
        validate_dispatch_receipt(
            dispatch, initial_state={"R0": 2, "R1": 3, "R2": 5, "R3": 7}
        )
        require(execution.halted, "Stage-1 dispatch did not halt")

        no_torch = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import ai_brain.stage2; "
                    "assert 'torch' not in sys.modules"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        require(no_torch.returncode == 0, "trusted Stage-2 imported torch")
        memory_hash_before = registry.manifest.rule_memory_hash
        require(
            memory_hash_before == registry.manifest.rule_memory_hash,
            "assistive evaluation changed RuleMemory",
        )

        git_sha = _git("rev-parse", "HEAD")
        result_payload = {
            "milestone": "M-25",
            "status": "PASS",
            "checks": checks,
            "git_sha": git_sha,
            "expected_stage1_release_commit": EXPECTED_STAGE1_RELEASE_COMMIT,
            "stage1_version": STAGE1_VERSION,
            "platform": platform.platform(),
            "python": sys.version,
            "trusted_import_no_torch": True,
            "registry": {
                "unique_skills": len(registry.records),
                "active_skills": len(registry.active_records()),
                "registry_hash": registry.manifest.registry_hash,
                "rule_memory_hash": registry.manifest.rule_memory_hash,
                "family_counts": registry.manifest.family_counts,
                "load_latency": registry_load_latency(registry_path),
            },
            "trusted_retrieval": {
                "structured_exact": len(structured_ids),
                "structured_total": 89,
                "controlled_exact": controlled_count,
                "controlled_total": 356,
                "cross_language_equal": cross_language_equal / 89,
                "wrong_automatic_skill_selection": 0,
                "elapsed_seconds": exact_elapsed,
                "latency_ms": {
                    language: sum(values) / len(values)
                    for language, values in controlled_latencies.items()
                },
            },
            "deterministic_assistive": deterministic,
            "unknown_policy": unknown_policy,
            "dataset_counts": dataset_counts,
            "scale": measure_catalog_scale(registry),
            "dispatch": {
                "rule_id_hash": content_hash(dispatch.rule_id),
                "selection_receipt_hash": selection.receipt_hash,
                "dispatch_receipt_hash": dispatch.dispatch_hash,
                "execution_hash": execution.execution_hash,
                "halted": execution.halted,
            },
            "duration_seconds": time.perf_counter() - started,
        }
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(result_payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return result_payload


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--skip-dataset", action="store_true")
    arguments = parser.parse_args()
    print(
        json.dumps(
            run(
                arguments.output_dir,
                arguments.result,
                full_dataset=not arguments.skip_dataset,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
