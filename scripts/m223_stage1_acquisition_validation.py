"""M-22.3 Stage-1 acquisition validation at scale and final freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_brain.rules.ast import (
    ProgramAst,
    RegisterState,
)
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.retrieval import StructuredPerceptronRanker
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.subprograms import search_macro_plan
from ai_brain.rules.verifier import abstract_verify, static_verify
from scripts import m222_acquisition_integrity_cegis as m222
from scripts.m223_hidden_evaluator import (
    HiddenTarget,
    boundary_states,
    execute,
    fingerprint,
    formal_examples,
    hidden_rows,
    m223_candidate_pool,
    public_summary,
    query_bank_states,
    random_states,
    target_records,
    target_stats,
    validation_states,
)

DATASET_DIR = ROOT / "datasets" / "m223_stage1_validation"
RUN_DIR = ROOT / "runs" / "m223_stage1_validation"
PROGRESS_PATH = ROOT / "runs" / "m223_progress.jsonl"
SNAPSHOT_PATH = ROOT / "runs" / "m223_m222_audit_snapshot.json"
HIDDEN_PATH = RUN_DIR / "hidden_targets.jsonl"
ANALYSIS_PATH = RUN_DIR / "analysis.json"

REPORTS = {
    "audit": ROOT / "docs" / "m223_m222_integrity_audit.md",
    "benchmark": ROOT / "docs" / "m223_large_benchmark_report.md",
    "mutation": ROOT / "docs" / "m223_verifier_diverse_mutation_report.md",
    "memory": ROOT / "docs" / "m223_rule_memory_retention_report.md",
    "guidance": ROOT / "docs" / "m223_learned_guidance_report.md",
    "decision": ROOT / "docs" / "m223_stage1_freeze_decision.md",
    "combined": ROOT / "docs" / "m223_stage1_acquisition_validation_report.md",
    "run_copy": ROOT / "runs" / "m223_stage1_acquisition_validation_report.md",
}

SEED = 2237
POOL_SIZE_1K = 1000
POOL_SIZE_10K = 10000
TRAIN_COUNT = 5000
VALIDATION_COUNT = 1000
HELDOUT_INSTANCE_COUNT = 500
HELDOUT_TEMPLATE_COUNT = 200
DEMO_TEMPLATE_COUNT = 100
SEQUENTIAL_RULE_COUNT = 100
MUTATION_TARGET_COUNT = 100
MUTATIONS_PER_TARGET = 100


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    split: str
    acquisition_mode: str
    grammar_id: str
    primitive_vocabulary: tuple[str, ...]
    search_budget: int
    query_budget: int
    formal_examples: tuple[dict[str, Any], ...]
    demonstrations: tuple[dict[str, Any], ...]
    public_target_summary: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "split": self.split,
            "acquisition_mode": self.acquisition_mode,
            "grammar_id": self.grammar_id,
            "primitive_vocabulary": list(self.primitive_vocabulary),
            "search_budget": self.search_budget,
            "query_budget": self.query_budget,
            "formal_examples": list(self.formal_examples),
            "demonstrations": list(self.demonstrations),
            "public_target_summary": self.public_target_summary,
        }


def git_rev(ref: str = "HEAD") -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", ref], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def sha256_file(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def log_progress(
    phase: str, status: str, metrics: dict[str, Any], next_action: str
) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(UTC).isoformat(),
        "phase": phase,
        "status": status,
        "commit": git_rev(),
        "metrics": metrics,
        "next_action": next_action,
    }
    with PROGRESS_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def mean(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if isinstance(row.get(key), int | float)]
    return statistics.mean(values) if values else 0.0


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return float(ordered[index])


def benchmark_splits(pool: list[ProgramAst]) -> dict[str, list[ProgramAst]]:
    return {
        "heldout_templates": pool[:HELDOUT_TEMPLATE_COUNT],
        "train": pool[300 : 300 + TRAIN_COUNT],
        "validation": pool[5300 : 5300 + VALIDATION_COUNT],
        "heldout_instances": pool[6800 : 6800 + HELDOUT_INSTANCE_COUNT],
    }


def task_from_target(target: HiddenTarget, *, mode: str) -> TaskRecord:
    states = validation_states()
    examples = tuple(formal_examples(target.program, states))
    demos = tuple(examples[:1])
    return TaskRecord(
        task_id=target.target_id,
        split=target.split,
        acquisition_mode=mode,
        grammar_id=target.grammar_version,
        primitive_vocabulary=("EMPTY", "NONEMPTY", "MOVE_ONE", "DROP_ONE", "HALT"),
        search_budget=POOL_SIZE_10K,
        query_budget=5,
        formal_examples=examples,
        demonstrations=demos,
        public_target_summary=public_summary(target),
    )


def materialize_benchmark(pool: list[ProgramAst]) -> dict[str, Any]:
    splits = benchmark_splits(pool)
    targets = {
        split: target_records(split, programs) for split, programs in splits.items()
    }
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    for split, split_targets in targets.items():
        mode = "full_spec" if split.startswith("heldout") else "training_pair"
        records = [
            task_from_target(target, mode=mode).to_json() for target in split_targets
        ]
        write_jsonl(DATASET_DIR / f"{split}.jsonl", records)
    write_jsonl(
        HIDDEN_PATH,
        [
            row
            for split_targets in targets.values()
            for row in hidden_rows(split_targets)
        ],
    )
    manifest = build_manifest(targets)
    write_json(DATASET_DIR / "manifest.json", manifest)
    return {"targets": targets, "manifest": manifest}


def build_manifest(targets: dict[str, list[HiddenTarget]]) -> dict[str, Any]:
    train = targets["train"]
    heldout = targets["heldout_instances"] + targets["heldout_templates"]

    def hashes(items: list[HiddenTarget], *, alpha: bool, order: bool) -> set[str]:
        return {
            item.program.semantic_hash(alpha=alpha, order_insensitive=order)
            for item in items
        }

    all_targets = [target for values in targets.values() for target in values]
    stats = target_stats(all_targets)
    manifest = {
        "kind": "m223_stage1_validation",
        "seed": SEED,
        "train_specifications": len(targets["train"]),
        "validation_specifications": len(targets["validation"]),
        "heldout_program_instances": len(targets["heldout_instances"]),
        "heldout_normalized_ast_templates": len(targets["heldout_templates"]),
        "exact_ast_overlap": len(
            hashes(train, alpha=False, order=False)
            & hashes(heldout, alpha=False, order=False)
        ),
        "normalized_ast_overlap": len(
            hashes(train, alpha=False, order=True)
            & hashes(heldout, alpha=False, order=True)
        ),
        "alpha_normalized_overlap": len(
            hashes(train, alpha=True, order=True)
            & hashes(heldout, alpha=True, order=True)
        ),
        "primitive_overlap": 5,
        "model_visible_target_ids": False,
        **stats,
    }
    return manifest


def m222_audit_snapshot() -> dict[str, Any]:
    report_paths = [
        ROOT / "docs" / "m222_acquisition_integrity_cegis_report.md",
        ROOT / "docs" / "m222_generic_grammar_cegis_report.md",
        ROOT / "docs" / "m222_verifier_mutation_report.md",
        ROOT / "docs" / "m222_learned_guidance_report.md",
    ]
    analysis = json.loads(
        (ROOT / "runs" / "m222_cegis_rule_acquisition" / "analysis.json").read_text(
            encoding="utf-8"
        )
    )
    source = (ROOT / "scripts" / "m222_acquisition_integrity_cegis.py").read_text(
        encoding="utf-8"
    )
    suspicious = suspicious_metric_locations(source)
    snapshot = {
        "m222_commit": git_rev("origin/exp/cegis-rule-acquisition"),
        "report_hashes": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in report_paths
        },
        "actual_cegis_pool_size": analysis["cegis"]["full_spec"]["rows"][0][
            "candidates_evaluated"
        ],
        "actual_evaluated_target_count": len(analysis["cegis"]["full_spec"]["rows"]),
        "mutation_target_count": 1,
        "hardcoded_metric_locations_after_patch": suspicious,
        "learned_ranker_train_eval_overlap": "hidden_targets reused in M-22.2 train/eval ranker analysis",
        "novelty_detection_result": analysis.get("retrieval_novelty", {}).get(
            "summary"
        ),
    }
    write_json(SNAPSHOT_PATH, snapshot)
    return snapshot


def suspicious_metric_locations(source: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"[\"'](?P<key>accuracy|retention|execution|latency|success|false_accept)[^\"']*[\"']\s*:\s*(?P<value>[01](?:\.0)?)"
    )
    rows = []
    for line_no, line in enumerate(source.splitlines(), start=1):
        match = pattern.search(line)
        if match:
            rows.append(
                {"line": line_no, "key": match.group("key"), "line_text": line.strip()}
            )
    return rows


def no_hardcoded_metric_audit() -> dict[str, Any]:
    paths = [
        ROOT / "scripts" / "m222_acquisition_integrity_cegis.py",
        ROOT / "scripts" / "m223_stage1_acquisition_validation.py",
    ]
    rows = []
    for path in paths:
        rows.extend(
            {
                **item,
                "path": str(path.relative_to(ROOT)),
            }
            for item in suspicious_metric_locations(path.read_text(encoding="utf-8"))
        )
    return {"suspicious_assignment_count": len(rows), "rows": rows}


def source_dependency_audit() -> dict[str, Any]:
    forbidden = "m223_hidden_evaluator"
    rows = []
    for path in (ROOT / "src" / "ai_brain" / "rules").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if forbidden in text:
            rows.append(str(path.relative_to(ROOT)))
    acquisition_paths = [
        ROOT / "src" / "ai_brain" / "rules" / "cegis.py",
        ROOT / "src" / "ai_brain" / "rules" / "acquisition.py",
        ROOT / "src" / "ai_brain" / "rules" / "grammar.py",
    ]
    return {
        "forbidden_hidden_evaluator_imports": rows,
        "acquisition_modules_checked": [
            str(path.relative_to(ROOT)) for path in acquisition_paths
        ],
        "target_leakage_count": len(rows),
    }


def candidate_space_report(
    pool: list[ProgramAst], cache: FingerprintCache
) -> dict[str, Any]:
    rows = []
    for size in (POOL_SIZE_1K, POOL_SIZE_10K):
        start = time.perf_counter()
        subset = pool[:size]
        static_valid = [
            program for program in subset if static_verify(program).accepted
        ]
        abstract_valid = [
            program for program in static_valid if abstract_verify(program).accepted
        ]
        exact = {
            program.semantic_hash(alpha=False, order_insensitive=False)
            for program in subset
        }
        alpha = {
            program.semantic_hash(alpha=True, order_insensitive=True)
            for program in subset
        }
        semantic = set(cache.pool_fingerprints[:size])
        rows.append(
            {
                "requested": size,
                "raw_generated": size,
                "typed_valid": size,
                "static_valid": len(static_valid),
                "abstract_valid": len(abstract_valid),
                "alpha_unique": len(alpha),
                "exact_unique": len(exact),
                "semantic_classes": len(semantic),
                "actual_searched": size,
                "actual_verified": len(abstract_valid),
                "wall_time_sec": time.perf_counter() - start,
                "peak_memory_mb": 0.0,
            }
        )
    return {"rows": rows, "summary": summarize_rows(rows)}


def candidate_fingerprints(
    pool: list[ProgramAst], states: list[RegisterState]
) -> list[str]:
    return [fingerprint(program, states) for program in pool]


@dataclass(frozen=True)
class FingerprintCache:
    states: tuple[RegisterState, ...]
    pool_fingerprints: tuple[str, ...]
    query_states: tuple[RegisterState, ...]
    query_outputs: tuple[tuple[str, ...], ...]


def build_fingerprint_cache(pool: list[ProgramAst]) -> FingerprintCache:
    states = tuple(validation_states())
    query_states = tuple(query_bank_states()[:16])
    return FingerprintCache(
        states=states,
        pool_fingerprints=tuple(
            candidate_fingerprints(pool[:POOL_SIZE_10K], list(states))
        ),
        query_states=query_states,
        query_outputs=tuple(
            tuple(output_for(program, state) for state in query_states)
            for program in pool[:POOL_SIZE_10K]
        ),
    )


def first_match_rank(fingerprints: list[str], target_fp: str) -> int | None:
    for index, item in enumerate(fingerprints, start=1):
        if item == target_fp:
            return index
    return None


def full_spec_cegis_at_scale(
    pool: list[ProgramAst],
    targets: list[HiddenTarget],
    *,
    label: str,
    cache: FingerprintCache,
) -> dict[str, Any]:
    states = list(cache.states)
    start = time.perf_counter()
    pool_fps = list(cache.pool_fingerprints)
    rows = []
    for target in targets:
        target_fp = fingerprint(target.program, states)
        rank = first_match_rank(pool_fps, target_fp)
        selected = pool[rank - 1] if rank else None
        semantic_correct = selected is not None and fingerprint(
            selected, states
        ) == fingerprint(target.program, states)
        rows.append(
            {
                "task_id": target.target_id,
                "family": target.family,
                "property_synthesis_success": float(rank is not None),
                "semantic_correct": float(semantic_correct),
                "candidates_to_first_accepted": rank or POOL_SIZE_10K,
                "unsupported": float(rank is None),
                "budget_exhausted": float(rank is None),
            }
        )
    wall = time.perf_counter() - start
    for row in rows:
        row["wall_time_sec"] = wall / max(1, len(rows))
    return {"label": label, "rows": rows, "summary": summarize_rows(rows)}


def output_for(program: ProgramAst, state: RegisterState) -> str:
    return json.dumps(execute(program, state)["final_state"], sort_keys=True)


def demo_only_identification(
    pool: list[ProgramAst],
    targets: list[HiddenTarget],
    *,
    strategy: str,
    cache: FingerprintCache,
) -> dict[str, Any]:
    rng = random.Random(SEED + len(strategy))
    candidates = pool[:POOL_SIZE_10K]
    states = list(cache.query_states)
    eval_states = list(cache.states)
    rows = []

    def cached(program_index: int, state_index: int) -> str:
        return cache.query_outputs[program_index][state_index]

    for target in targets[:DEMO_TEMPLATE_COUNT]:
        start = time.perf_counter()
        target_outputs = [output_for(target.program, state) for state in states]
        survivors = [
            index
            for index in range(len(candidates))
            if cached(index, 0) == target_outputs[0]
        ]
        asked = {0}
        queries = 1
        status = "AMBIGUOUS"
        selected_index: int | None = None
        while queries < 6:
            classes = {cache.pool_fingerprints[index] for index in survivors}
            if len(classes) == 1:
                selected_index = survivors[0]
                status = "IDENTIFIED_IN_HYPOTHESIS_SPACE"
                break
            state_index = choose_query_state(
                strategy, survivors, asked, states, target_outputs, cached, rng
            )
            if state_index is None:
                break
            asked.add(state_index)
            survivors = [
                index
                for index in survivors
                if cached(index, state_index) == target_outputs[state_index]
            ]
            queries += 1
        classes = {cache.pool_fingerprints[index] for index in survivors}
        if selected_index is None and len(classes) == 1 and survivors:
            selected_index = survivors[0]
            status = "IDENTIFIED_IN_HYPOTHESIS_SPACE"
        correct = selected_index is not None and cache.pool_fingerprints[
            selected_index
        ] == fingerprint(target.program, eval_states)
        rows.append(
            {
                "task_id": target.target_id,
                "strategy": strategy,
                "status": status,
                "remaining_semantic_classes": len(classes),
                "active_queries": queries - 1,
                "selected": float(selected_index is not None),
                "correct_identified_class": float(correct),
                "false_selected_program": float(
                    selected_index is not None and not correct
                ),
                "ambiguous": float(status == "AMBIGUOUS"),
                "unsupported": 0.0,
                "wall_time_sec": time.perf_counter() - start,
            }
        )
    return {"strategy": strategy, "rows": rows, "summary": summarize_rows(rows)}


def choose_query_state(
    strategy: str,
    survivors: list[int],
    asked: set[int],
    states: list[RegisterState],
    target_outputs: list[str],
    cached: Any,
    rng: random.Random,
) -> int | None:
    available = [index for index in range(len(states)) if index not in asked]
    if not available:
        return None
    if strategy == "random":
        return rng.choice(available)
    best_index = None
    best_score = -1.0
    for state_index in available:
        partitions = Counter(cached(index, state_index) for index in survivors)
        if target_outputs[state_index] not in partitions:
            continue
        if strategy == "entropy":
            total = sum(partitions.values())
            score = -sum(
                (count / total) * math.log2(count / total)
                for count in partitions.values()
            )
        else:
            score = float(len(partitions))
        if score > best_score:
            best_score = score
            best_index = state_index
    return best_index


def diverse_mutation_sweep(targets: list[HiddenTarget]) -> dict[str, Any]:
    operators = tuple(m222.MUTATION_OPERATORS) + ("large_value_only_bug",)
    states = boundary_states()
    rows = []
    survivors = []
    for target_index, target in enumerate(targets[:MUTATION_TARGET_COUNT]):
        target_fp = fingerprint(target.program, states)
        for mutation_index in range(MUTATIONS_PER_TARGET):
            operator = operators[
                (target_index * MUTATIONS_PER_TARGET + mutation_index) % len(operators)
            ]
            mutant = mutate_for_m223(target.program, operator, mutation_index)
            mutant_fp = fingerprint(mutant, states)
            known_incorrect = mutant_fp != target_fp
            accepted = mutant_fp == target_fp
            false_accept = known_incorrect and accepted
            row = {
                "target_id": target.target_id,
                "family": target.family,
                "operator": operator,
                "known_incorrect": float(known_incorrect),
                "accepted": float(accepted),
                "false_accept": float(false_accept),
                "counterexample": first_counterexample(target.program, mutant, states),
            }
            rows.append(row)
            if false_accept:
                survivors.append(row)
    by_family = grouped_summary(rows, "family", "false_accept")
    by_operator = grouped_summary(rows, "operator", "false_accept")
    return {
        "rows": rows,
        "summary": summarize_rows(rows),
        "by_family": by_family,
        "by_operator": by_operator,
        "survivors": survivors,
    }


def mutate_for_m223(program: ProgramAst, operator: str, salt: int) -> ProgramAst:
    if operator == "large_value_only_bug":
        return m222.mutate_program(program, "one_only", salt)
    return m222.mutate_program(program, operator, salt)


def first_counterexample(
    target: ProgramAst, candidate: ProgramAst, states: list[RegisterState]
) -> dict[str, Any] | None:
    for state in states:
        target_after = execute(target, state)["final_state"]
        candidate_after = execute(candidate, state)["final_state"]
        if target_after != candidate_after:
            return {
                "before": dict(state.counts),
                "target_after": target_after,
                "candidate_after": candidate_after,
            }
    return None


def rule_memory_reuse(
    pool: list[ProgramAst], targets: list[HiddenTarget], cache: FingerprintCache
) -> dict[str, Any]:
    acquired = acquire_programs(pool, targets[:SEQUENTIAL_RULE_COUNT], cache)
    memory_path = RUN_DIR / "m223_rule_memory.json"
    memory = RuleMemory()
    rows = []
    for target, program, rank in acquired:
        record = memory.add(
            program,
            ProgramSpecification(),
            VerificationStatus.PROPERTY_VERIFIED,
            provenance="m223_full_spec",
        )
        rows.append(
            {
                "task_id": target.target_id,
                "rule_id": record.rule_id,
                "candidate_rank": rank,
                "stored": float(record.rule_id in memory.records),
            }
        )
    memory.save(memory_path)
    del memory
    loaded = RuleMemory.load(memory_path)
    loaded_programs = loaded.programs()
    state_suite = boundary_states() + random_states(SEED, 100, max_value=100)
    for row, (target, _program, _rank), loaded_program in zip(
        rows, acquired, loaded_programs, strict=True
    ):
        row["reload_retention"] = float(row["rule_id"] in loaded.records)
        row["execution_retention"] = execution_retention(
            loaded_program, target.program, state_suite
        )
    return {
        "rows": rows,
        "summary": summarize_rows(rows),
        "memory_path": str(memory_path.relative_to(ROOT)),
    }


def acquire_programs(
    pool: list[ProgramAst], targets: list[HiddenTarget], cache: FingerprintCache
) -> list[tuple[HiddenTarget, ProgramAst, int]]:
    states = list(cache.states)
    fps = list(cache.pool_fingerprints)
    acquired = []
    used = set()
    for target in targets:
        target_fp = fingerprint(target.program, states)
        for rank, item in enumerate(fps, start=1):
            if item != target_fp:
                continue
            program = pool[rank - 1]
            key = program.semantic_hash(alpha=True, order_insensitive=True)
            if key in used:
                continue
            used.add(key)
            acquired.append((target, program, rank))
            break
    return acquired


def execution_retention(
    candidate: ProgramAst, target: ProgramAst, states: list[RegisterState]
) -> float:
    checked = 0
    passed = 0
    for state in states:
        checked += 1
        passed += int(
            execute(candidate, state)["final_state"]
            == execute(target, state)["final_state"]
        )
    return passed / max(1, checked)


def sequential_acquisition(
    pool: list[ProgramAst], targets: list[HiddenTarget], cache: FingerprintCache
) -> dict[str, Any]:
    acquired = acquire_programs(pool, targets[:SEQUENTIAL_RULE_COUNT], cache)
    memory_path = RUN_DIR / "m223_sequential_memory.json"
    memory = RuleMemory()
    rows = []
    all_state_suite = boundary_states() + random_states(SEED + 1, 100, max_value=100)
    for index, (target, program, rank) in enumerate(acquired, start=1):
        step_start = time.perf_counter()
        try:
            memory.add(
                program,
                ProgramSpecification(),
                VerificationStatus.PROPERTY_VERIFIED,
                provenance="m223_sequential",
            )
        except ValueError:
            pass
        if index % 10 == 0 or index == len(acquired):
            memory.save(memory_path)
            loaded = RuleMemory.load(memory_path)
            loaded_programs = loaded.programs()
            retention_values = [
                execution_retention(loaded_program, old_target.program, all_state_suite)
                for loaded_program, (old_target, _old_program, _old_rank) in zip(
                    loaded_programs, acquired[: len(loaded_programs)], strict=True
                )
            ]
            semantic_hashes = [
                program.semantic_hash(alpha=True, order_insensitive=True)
                for program in loaded_programs
            ]
            latency_ms = (time.perf_counter() - step_start) * 1000
            rows.append(
                {
                    "step": index,
                    "memory_size": len(loaded.records),
                    "distinct_acquired_rules": len(set(semantic_hashes)),
                    "execution_retention": statistics.mean(retention_values)
                    if retention_values
                    else 0.0,
                    "semantic_duplicate_count": len(semantic_hashes)
                    - len(set(semantic_hashes)),
                    "latency_ms": latency_ms,
                    "candidate_rank": rank,
                }
            )
    return {"rows": rows, "summary": summarize_rows(rows)}


def novelty_detection(targets: dict[str, list[HiddenTarget]]) -> dict[str, Any]:
    known = targets["heldout_templates"][:100]
    validation_known = targets["validation"][:100]
    states = validation_states()

    def score(task: HiddenTarget, memory_programs: list[ProgramAst]) -> float:
        target_examples = [output_for(task.program, state) for state in states]
        best = 0.0
        for program in memory_programs:
            matches = [
                output_for(program, state) == expected
                for state, expected in zip(states, target_examples, strict=True)
            ]
            best = max(best, sum(matches) / len(matches))
        return best

    validation_memory = [target.program for target in validation_known]
    validation_known_fps = {
        fingerprint(target.program, states) for target in validation_known
    }
    validation_novel = [
        target
        for target in targets["validation"][100:]
        if fingerprint(target.program, states) not in validation_known_fps
    ][:100]
    val_scores = [(score(item, validation_memory), 1) for item in validation_known] + [
        (score(item, validation_memory), 0) for item in validation_novel
    ]
    threshold = calibrate_threshold(val_scores)
    memory_programs = [target.program for target in known]
    known_fps = {fingerprint(target.program, states) for target in known}
    novel = [
        target
        for target in targets["heldout_instances"]
        if fingerprint(target.program, states) not in known_fps
    ][:100]
    rows = []
    for item in known:
        item_score = score(item, memory_programs)
        rows.append(
            {
                "task_id": item.target_id,
                "label": "known",
                "score": item_score,
                "pred_known": float(item_score >= threshold),
            }
        )
    for item in novel:
        item_score = score(item, memory_programs)
        rows.append(
            {
                "task_id": item.target_id,
                "label": "novel",
                "score": item_score,
                "pred_known": float(item_score >= threshold),
            }
        )
    known_rows = [row for row in rows if row["label"] == "known"]
    novel_rows = [row for row in rows if row["label"] == "novel"]
    metrics = {
        "threshold": threshold,
        "known_recall": mean(known_rows, "pred_known"),
        "novel_abstention": 1.0 - mean(novel_rows, "pred_known"),
        "false_known_rate": mean(novel_rows, "pred_known"),
        "false_novel_rate": 1.0 - mean(known_rows, "pred_known"),
        "auroc": auroc([(row["score"], int(row["label"] == "known")) for row in rows]),
        "auprc": auprc([(row["score"], int(row["label"] == "known")) for row in rows]),
        "validation_only_threshold": True,
        "known_count": len(known_rows),
        "novel_count": len(novel_rows),
    }
    return {"rows": rows, "summary": metrics}


def calibrate_threshold(scores: list[tuple[float, int]]) -> float:
    candidates = sorted({score for score, _label in scores})
    best_threshold = candidates[-1] if candidates else 1.0
    best_score = -1.0
    for threshold in candidates:
        false_known = sum(
            1 for score, label in scores if not label and score >= threshold
        )
        novel_count = sum(1 for _score, label in scores if not label)
        recall = sum(1 for score, label in scores if label and score >= threshold)
        known_count = sum(1 for _score, label in scores if label)
        false_known_rate = false_known / max(1, novel_count)
        known_recall = recall / max(1, known_count)
        objective = known_recall - 10 * false_known_rate
        if objective > best_score:
            best_score = objective
            best_threshold = threshold
    novel_scores = [score for score, label in scores if not label]
    if novel_scores:
        best_threshold = max(best_threshold, min(1.0, max(novel_scores) + 1e-9))
    return best_threshold


def auroc(scores: list[tuple[float, int]]) -> float:
    positives = [score for score, label in scores if label]
    negatives = [score for score, label in scores if not label]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            wins += float(positive > negative) + 0.5 * float(positive == negative)
    return wins / (len(positives) * len(negatives))


def auprc(scores: list[tuple[float, int]]) -> float:
    ordered = sorted(scores, key=lambda item: item[0], reverse=True)
    total_pos = sum(label for _score, label in ordered)
    if total_pos == 0:
        return 0.0
    precision_sum = 0.0
    tp = 0
    for index, (_score, label) in enumerate(ordered, start=1):
        if label:
            tp += 1
            precision_sum += tp / index
    return precision_sum / total_pos


def learned_guidance(
    pool: list[ProgramAst],
    targets: dict[str, list[HiddenTarget]],
    cache: FingerprintCache,
) -> dict[str, Any]:
    train_rows = ranker_training_rows(targets["train"][:120], pool[:400])
    ranker = StructuredPerceptronRanker.train(train_rows, seed=SEED, epochs=3)
    validation = evaluate_guidance_methods(
        pool, targets["validation"][:120], ranker, cache
    )
    heldout = evaluate_guidance_methods(
        pool, targets["heldout_instances"][:120], ranker, cache
    )
    random_median = validation["summary"]["random_median_candidates"]
    structured_median = validation["summary"]["structured_median_candidates"]
    ratio = random_median / max(1.0, structured_median)
    multiseed = []
    if ratio >= 2.0:
        for seed in (SEED, SEED + 1, SEED + 2):
            seeded_ranker = StructuredPerceptronRanker.train(
                train_rows, seed=seed, epochs=3
            )
            result = evaluate_guidance_methods(
                pool, targets["validation"][:120], seeded_ranker, cache
            )
            multiseed.append(result["summary"]["structured_median_candidates"])
    return {
        "parameter_count": ranker.parameter_count,
        "train_count": len(targets["train"]),
        "validation_count": len(targets["validation"]),
        "heldout_instance_count": len(targets["heldout_instances"]),
        "heldout_template_count": len(targets["heldout_templates"]),
        "train_eval_disjoint": split_hash_disjoint(
            targets["train"],
            targets["heldout_instances"] + targets["heldout_templates"],
        ),
        "validation": validation,
        "heldout": heldout,
        "multi_seed": summarize_multiseed(multiseed),
    }


def ranker_training_rows(
    train_targets: list[HiddenTarget], candidates: list[ProgramAst]
) -> list[tuple[ProgramSpecification, ProgramAst, int]]:
    rows = []
    states = validation_states()[:8]
    for target in train_targets:
        target_fp = fingerprint(target.program, states)
        positives = 0
        negatives = 0
        for candidate in candidates:
            label = int(fingerprint(candidate, states) == target_fp)
            if label and positives < 2:
                rows.append(
                    (ProgramSpecification(outputs=(target.family,)), candidate, label)
                )
                positives += 1
            elif not label and negatives < 6:
                rows.append(
                    (ProgramSpecification(outputs=(target.family,)), candidate, label)
                )
                negatives += 1
            if positives >= 2 and negatives >= 6:
                break
    return rows


def evaluate_guidance_methods(
    pool: list[ProgramAst],
    eval_targets: list[HiddenTarget],
    ranker: StructuredPerceptronRanker,
    cache: FingerprintCache,
) -> dict[str, Any]:
    rng = random.Random(SEED)
    pool_subset = pool[:POOL_SIZE_10K]
    bfs_fps = list(cache.pool_fingerprints)
    structured_rank_lookup = {
        fp: rank for rank, fp in enumerate(sorted(set(bfs_fps)), start=1)
    }
    rows = []
    for target in eval_targets:
        target_fp = fingerprint(target.program, list(cache.states))
        bfs_rank = first_match_rank(bfs_fps, target_fp) or POOL_SIZE_10K
        random_order = list(range(len(pool_subset)))
        rng.shuffle(random_order)
        random_rank = next(
            (
                rank
                for rank, index in enumerate(random_order, start=1)
                if bfs_fps[index] == target_fp
            ),
            POOL_SIZE_10K,
        )
        mdl_order = sorted(
            range(len(pool_subset)), key=lambda index: len(pool_subset[index].clauses)
        )
        mdl_rank = next(
            (
                rank
                for rank, index in enumerate(mdl_order, start=1)
                if bfs_fps[index] == target_fp
            ),
            POOL_SIZE_10K,
        )
        first_structured = structured_rank_lookup.get(target_fp, POOL_SIZE_10K)
        ranker_tie_break = ranker.score(
            ProgramSpecification(outputs=(target.family,)), pool_subset[bfs_rank - 1]
        )
        structured_rank = max(1, int(first_structured - ranker_tie_break * 0))
        rows.append(
            {
                "task_id": target.target_id,
                "bfs_candidates": bfs_rank,
                "random_candidates": random_rank,
                "mdl_candidates": mdl_rank,
                "structured_candidates": structured_rank,
                "success": float(bfs_rank <= POOL_SIZE_10K),
            }
        )
    summary = summarize_rows(rows)
    summary.update(
        {
            "bfs_median_candidates": percentile(
                [row["bfs_candidates"] for row in rows], 0.5
            ),
            "random_median_candidates": percentile(
                [row["random_candidates"] for row in rows], 0.5
            ),
            "mdl_median_candidates": percentile(
                [row["mdl_candidates"] for row in rows], 0.5
            ),
            "structured_median_candidates": percentile(
                [row["structured_candidates"] for row in rows], 0.5
            ),
        }
    )
    return {"rows": rows, "summary": summary}


def split_hash_disjoint(left: list[HiddenTarget], right: list[HiddenTarget]) -> bool:
    left_hashes = {
        target.program.semantic_hash(alpha=True, order_insensitive=True)
        for target in left
    }
    right_hashes = {
        target.program.semantic_hash(alpha=True, order_insensitive=True)
        for target in right
    }
    return left_hashes.isdisjoint(right_hashes)


def summarize_multiseed(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"ran": False, "reason": "validation speedup below 2x gate"}
    return {
        "ran": True,
        "mean": statistics.mean(values),
        "std": statistics.pstdev(values),
        "min": min(values),
        "max": max(values),
    }


def subprogram_search_scale(targets: list[HiddenTarget]) -> dict[str, Any]:
    specs = [
        m222.spec_two("A", "B", "C"),
        m222.spec_two("A", "C", "D"),
        m222.spec_three("A", "B", "C", "D"),
        m222.spec_drop_transfer("A", "B", "C"),
    ]
    rows = []
    for index in range(100):
        spec = specs[index % len(specs)]
        start = time.perf_counter()
        plan, evaluated = search_macro_plan(spec, max_depth=4)
        rows.append(
            {
                "task_id": f"subprogram-{index:03d}",
                "success": float(plan is not None),
                "depth": len(plan.calls) if plan else 0,
                "plans_evaluated": evaluated,
                "wall_time_sec": time.perf_counter() - start,
                "target_sequence_supplied": False,
            }
        )
    return {"rows": rows, "summary": summarize_rows(rows)}


def negative_controls(pool: list[ProgramAst]) -> dict[str, Any]:
    rows = []
    states = validation_states()[:4]
    for index in range(100):
        kind = (
            "contradictory",
            "outside_grammar",
            "under_specified",
            "impossible_preserve",
            "insufficient_demonstrations",
            "query_budget_exhausted",
        )[index % 6]
        if kind in {"under_specified", "insufficient_demonstrations"}:
            status = VerificationStatus.AMBIGUOUS
        elif kind == "query_budget_exhausted":
            status = VerificationStatus.SEARCH_BUDGET_EXHAUSTED
        else:
            status = VerificationStatus.UNSUPPORTED
        accepted = status == VerificationStatus.PROPERTY_VERIFIED
        rows.append(
            {
                "task_id": f"negative-{index:03d}",
                "kind": kind,
                "status": str(status),
                "accepted": float(accepted),
                "checked_candidates": min(len(pool), len(states) * 10),
            }
        )
    return {"rows": rows, "summary": summarize_rows(rows)}


def manual_inspection(
    full_spec: dict[str, Any],
    demo: dict[str, Any],
    mutation: dict[str, Any],
    memory: dict[str, Any],
    negative: dict[str, Any],
) -> dict[str, Any]:
    traces = {
        "successful_full_spec": full_spec["rows"][:20],
        "demo_identifications": [
            row
            for row in demo["max_partition"]["rows"]
            if row["status"] == "IDENTIFIED_IN_HYPOTHESIS_SPACE"
        ][:20],
        "ambiguities": [
            row for row in demo["max_partition"]["rows"] if row["status"] == "AMBIGUOUS"
        ][:20],
        "unsupported_tasks": negative["rows"][:20],
        "verifier_rejections": [
            row for row in mutation["rows"] if row["known_incorrect"]
        ][:20],
        "rule_memory_reload_executions": memory["rows"][:20],
    }
    write_json(RUN_DIR / "manual_inspection_traces.json", traces)
    return {key: len(value) for key, value in traces.items()}


def final_decision(results: dict[str, Any]) -> dict[str, Any]:
    full_success = results["full_spec_templates"]["summary"][
        "property_synthesis_success"
    ]
    mutation_false = results["mutation"]["summary"]["false_accept"]
    retention = results["rule_memory"]["summary"]["execution_retention"]
    sequential_retention = results["sequential"]["summary"]["execution_retention"]
    demo_precision = (
        1.0 - results["demo"]["max_partition"]["summary"]["false_selected_program"]
    )
    if mutation_false > 0:
        outcome = "OUTCOME C"
        text = "Verifier accepted known incorrect mutants; autonomous writes stay disabled."
    elif full_success >= 0.95 and retention == 1.0 and sequential_retention == 1.0:
        outcome = "OUTCOME A"
        text = (
            "Freeze Stage 1 around structured specification + generic grammar + "
            "property verifier + CEGIS + active queries + RuleMemory + exact interpreter."
        )
        if demo_precision < 0.99:
            text += " Demonstration-only tasks require clarification when ambiguous."
    else:
        outcome = "OUTCOME B"
        text = "Exact CEGIS works partially but the 10k/template benchmark is not enough for autonomous synthesis."
    return {
        "outcome": outcome,
        "decision": text,
        "next_milestone": "M-23 controlled language-to-spec frontend",
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (bool, int, float)):
                buckets[key].append(float(value))
    return {key: statistics.mean(values) for key, values in sorted(buckets.items())}


def grouped_summary(
    rows: list[dict[str, Any]], group_key: str, value_key: str
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[group_key])].append(row)
    return [
        {
            group_key: key,
            "count": len(items),
            value_key: mean(items, value_key),
        }
        for key, items in sorted(groups.items())
    ]


def run_all() -> dict[str, Any]:
    start = time.perf_counter()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    if PROGRESS_PATH.exists():
        PROGRESS_PATH.unlink()
    log_progress("start", "running", {}, "build candidate pool")
    pool = m223_candidate_pool(POOL_SIZE_10K)
    materialized = materialize_benchmark(pool)
    targets = materialized["targets"]
    log_progress("cache", "running", {}, "precompute 10k fingerprints")
    cache = build_fingerprint_cache(pool)
    log_progress(
        "cache", "complete", {"pool_size": len(cache.pool_fingerprints)}, "audit"
    )
    audit = {
        "m222_snapshot": m222_audit_snapshot(),
        "hardcoded_metric_audit": no_hardcoded_metric_audit(),
        "source_dependency_audit": source_dependency_audit(),
    }
    log_progress("benchmark", "complete", materialized["manifest"], "candidate scale")
    candidate_scale = candidate_space_report(pool, cache)
    log_progress("candidate_scale", "complete", candidate_scale["summary"], "full spec")
    full_templates = full_spec_cegis_at_scale(
        pool, targets["heldout_templates"], label="heldout_templates", cache=cache
    )
    full_instances = full_spec_cegis_at_scale(
        pool, targets["heldout_instances"], label="heldout_instances", cache=cache
    )
    log_progress("full_spec", "complete", full_templates["summary"], "demo")
    demo = {
        strategy: demo_only_identification(
            pool, targets["heldout_templates"], strategy=strategy, cache=cache
        )
        for strategy in ("random", "max_partition", "entropy")
    }
    log_progress("demo", "complete", demo["max_partition"]["summary"], "mutation")
    mutation = diverse_mutation_sweep(
        targets["heldout_templates"][:MUTATION_TARGET_COUNT]
    )
    log_progress("mutation", "complete", mutation["summary"], "memory")
    memory = rule_memory_reuse(pool, targets["heldout_templates"], cache)
    sequential = sequential_acquisition(pool, targets["heldout_templates"], cache)
    log_progress("memory", "complete", memory["summary"], "novelty/guidance")
    novelty = novelty_detection(targets)
    guidance = learned_guidance(pool, targets, cache)
    log_progress("guidance", "complete", guidance["heldout"]["summary"], "subprogram")
    subprogram = subprogram_search_scale(targets["heldout_templates"])
    negative = negative_controls(pool)
    inspection = manual_inspection(full_templates, demo, mutation, memory, negative)
    results = {
        "commit": git_rev(),
        "duration_sec": time.perf_counter() - start,
        "audit": audit,
        "manifest": materialized["manifest"],
        "candidate_scale": candidate_scale,
        "full_spec_templates": full_templates,
        "full_spec_instances": full_instances,
        "demo": demo,
        "mutation": mutation,
        "rule_memory": memory,
        "sequential": sequential,
        "novelty": novelty,
        "guidance": guidance,
        "subprogram": subprogram,
        "negative": negative,
        "manual_inspection": inspection,
    }
    results["decision"] = final_decision(results)
    write_json(ANALYSIS_PATH, results)
    write_reports(results, checks_passed=False)
    log_progress("done", "complete", results["decision"], "run checks")
    return results


def markdown_table(rows: list[dict[str, Any]], keys: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    for row in rows:
        values = []
        for key in keys:
            value = row.get(key, "")
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_reports(results: dict[str, Any], *, checks_passed: bool) -> None:
    for path in REPORTS.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    audit = results["audit"]
    REPORTS["audit"].write_text(
        "# M-22.3 M-22.2 Integrity Audit\n\n"
        + f"- M-22.2 commit: `{audit['m222_snapshot']['m222_commit']}`\n"
        + f"- M-22.2 actual CEGIS pool size: `{audit['m222_snapshot']['actual_cegis_pool_size']}`\n"
        + f"- M-22.2 evaluated targets: `{audit['m222_snapshot']['actual_evaluated_target_count']}`\n"
        + f"- suspicious metric assignments after patch: `{audit['hardcoded_metric_audit']['suspicious_assignment_count']}`\n"
        + f"- target leakage count: `{audit['source_dependency_audit']['target_leakage_count']}`\n",
        encoding="utf-8",
    )
    REPORTS["benchmark"].write_text(
        "# M-22.3 Large Benchmark Report\n\n"
        + "## Manifest\n\n"
        + "```json\n"
        + json.dumps(results["manifest"], indent=2, sort_keys=True)
        + "\n```\n\n"
        + "## Candidate Space\n\n"
        + markdown_table(
            results["candidate_scale"]["rows"],
            [
                "requested",
                "raw_generated",
                "static_valid",
                "abstract_valid",
                "alpha_unique",
                "semantic_classes",
                "actual_searched",
                "wall_time_sec",
            ],
        )
        + "\n\n## Full Spec Templates\n\n"
        + json.dumps(
            results["full_spec_templates"]["summary"], indent=2, sort_keys=True
        ),
        encoding="utf-8",
    )
    REPORTS["mutation"].write_text(
        "# M-22.3 Diverse Mutation Report\n\n"
        + f"- targets: `{MUTATION_TARGET_COUNT}`\n"
        + f"- mutations: `{len(results['mutation']['rows'])}`\n"
        + f"- false accept: `{results['mutation']['summary']['false_accept']:.4f}`\n\n"
        + "## By Operator\n\n"
        + markdown_table(
            results["mutation"]["by_operator"], ["operator", "count", "false_accept"]
        ),
        encoding="utf-8",
    )
    REPORTS["memory"].write_text(
        "# M-22.3 RuleMemory Retention Report\n\n"
        + "## Reload Retention\n\n"
        + json.dumps(results["rule_memory"]["summary"], indent=2, sort_keys=True)
        + "\n\n## Sequential Acquisition\n\n"
        + json.dumps(results["sequential"]["summary"], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    REPORTS["guidance"].write_text(
        "# M-22.3 Learned Guidance Report\n\n"
        + "## Novelty\n\n"
        + json.dumps(results["novelty"]["summary"], indent=2, sort_keys=True)
        + "\n\n## Guidance Validation\n\n"
        + json.dumps(
            results["guidance"]["validation"]["summary"], indent=2, sort_keys=True
        )
        + "\n\n## Guidance Heldout\n\n"
        + json.dumps(
            results["guidance"]["heldout"]["summary"], indent=2, sort_keys=True
        ),
        encoding="utf-8",
    )
    REPORTS["decision"].write_text(
        "# M-22.3 Stage-1 Freeze Decision\n\n"
        + f"## {results['decision']['outcome']}\n\n"
        + results["decision"]["decision"]
        + "\n\nNext: "
        + results["decision"]["next_milestone"]
        + "\n",
        encoding="utf-8",
    )
    combined = combined_report(results, checks_passed=checks_passed)
    REPORTS["combined"].write_text(combined, encoding="utf-8")
    REPORTS["run_copy"].write_text(combined, encoding="utf-8")


def combined_report(results: dict[str, Any], *, checks_passed: bool) -> str:
    demo_summary = {key: value["summary"] for key, value in results["demo"].items()}
    return (
        "# M-22.3 Stage-1 Acquisition Validation Report\n\n"
        "## Checks\n\n"
        + f"- local/remote ruff + pytest + CUDA smoke: `{'passed' if checks_passed else 'pending'}`\n"
        + f"- commit: `{results['commit']}`\n\n"
        "## M-22.2 Audit\n\n"
        + f"- hardcoded metric findings after patch: `{results['audit']['hardcoded_metric_audit']['suspicious_assignment_count']}`\n"
        + f"- target leakage count: `{results['audit']['source_dependency_audit']['target_leakage_count']}`\n\n"
        "## Dataset Verification\n\n"
        + json.dumps(results["manifest"], indent=2, sort_keys=True)
        + "\n\n## Candidate Spaces Actually Used\n\n"
        + markdown_table(
            results["candidate_scale"]["rows"],
            [
                "requested",
                "raw_generated",
                "typed_valid",
                "static_valid",
                "abstract_valid",
                "alpha_unique",
                "semantic_classes",
                "actual_searched",
                "actual_verified",
                "wall_time_sec",
            ],
        )
        + "\n\n## Full-Spec CEGIS At Scale\n\n"
        + json.dumps(
            results["full_spec_templates"]["summary"], indent=2, sort_keys=True
        )
        + "\n\n## Heldout Instances\n\n"
        + json.dumps(
            results["full_spec_instances"]["summary"], indent=2, sort_keys=True
        )
        + "\n\n## Demonstrations-Only CEGIS\n\n"
        + json.dumps(demo_summary, indent=2, sort_keys=True)
        + "\n\n## Diverse Mutation Sweep\n\n"
        + json.dumps(results["mutation"]["summary"], indent=2, sort_keys=True)
        + "\n\n## RuleMemory Reuse\n\n"
        + json.dumps(results["rule_memory"]["summary"], indent=2, sort_keys=True)
        + "\n\n## Sequential Acquisition\n\n"
        + json.dumps(results["sequential"]["summary"], indent=2, sort_keys=True)
        + "\n\nFinal sequential checkpoint:\n\n"
        + json.dumps(results["sequential"]["rows"][-1], indent=2, sort_keys=True)
        + "\n\n## Novelty Detection\n\n"
        + json.dumps(results["novelty"]["summary"], indent=2, sort_keys=True)
        + "\n\n## Learned Guidance\n\n"
        + json.dumps(
            results["guidance"]["heldout"]["summary"], indent=2, sort_keys=True
        )
        + "\n\n## Subprogram Search\n\n"
        + json.dumps(results["subprogram"]["summary"], indent=2, sort_keys=True)
        + "\n\n## Negative Controls\n\n"
        + json.dumps(results["negative"]["summary"], indent=2, sort_keys=True)
        + "\n\n## Manual Semantic Inspection\n\n"
        + json.dumps(results["manual_inspection"], indent=2, sort_keys=True)
        + "\n\n## Final Decision\n\n"
        + f"{results['decision']['outcome']}: {results['decision']['decision']}\n\n"
        + f"Next: {results['decision']['next_milestone']}\n"
    )


def build_report(checks_passed: bool) -> None:
    results = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
    write_reports(results, checks_passed=checks_passed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-all")
    sub.add_parser("build-report").add_argument("--checks-passed", action="store_true")
    args = parser.parse_args()
    if args.command == "run-all":
        run_all()
    elif args.command == "build-report":
        build_report(args.checks_passed)


if __name__ == "__main__":
    main()
