from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import m223_stage1_acquisition_validation as m223
from scripts.m223_hidden_evaluator import m223_candidate_pool

DATASET_DIR = ROOT / "datasets" / "m223_stage1_validation"
RUN_DIR = ROOT / "runs" / "m223_stage1_validation"


def _analysis() -> dict:
    return json.loads((RUN_DIR / "analysis.json").read_text(encoding="utf-8"))


def _jsonl_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_m223_no_hardcoded_success_metric_audit() -> None:
    assert m223.no_hardcoded_metric_audit()["suspicious_assignment_count"] == 0


def test_m223_persisted_benchmark_records_and_manifest() -> None:
    manifest = json.loads((DATASET_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert _jsonl_count(DATASET_DIR / "train.jsonl") == 5000
    assert _jsonl_count(DATASET_DIR / "validation.jsonl") == 1000
    assert _jsonl_count(DATASET_DIR / "heldout_instances.jsonl") == 500
    assert _jsonl_count(DATASET_DIR / "heldout_templates.jsonl") == 200
    assert manifest["exact_ast_overlap"] == 0
    assert manifest["normalized_ast_overlap"] == 0
    assert manifest["alpha_normalized_overlap"] == 0
    assert manifest["model_visible_target_ids"] is False


def test_m223_acquisition_records_do_not_expose_hidden_asts() -> None:
    row = json.loads(
        (DATASET_DIR / "heldout_templates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert "program" not in row
    assert "exact_ast_hash" not in json.dumps(row)
    assert "alpha_ast_hash" not in json.dumps(row)
    assert (RUN_DIR / "hidden_targets.jsonl").exists()
    assert m223.source_dependency_audit()["target_leakage_count"] == 0


def test_m223_candidate_pool_is_actual_alpha_unique() -> None:
    pool = m223_candidate_pool(300)
    alpha = {
        program.semantic_hash(alpha=True, order_insensitive=True) for program in pool
    }
    assert len(pool) == 300
    assert len(alpha) == 300


def test_m223_analysis_uses_real_10k_candidate_space() -> None:
    row = _analysis()["candidate_scale"]["rows"][-1]
    assert row["requested"] >= 10000
    assert row["actual_searched"] >= 10000
    assert row["alpha_unique"] >= 10000


def test_m223_full_spec_benchmark_at_scale() -> None:
    full = _analysis()["full_spec_templates"]
    assert len(full["rows"]) >= 200
    assert full["summary"]["property_synthesis_success"] >= 0.95
    assert full["summary"]["semantic_correct"] >= 0.95


def test_m223_demo_only_does_not_guess_when_ambiguous() -> None:
    demo = _analysis()["demo"]["max_partition"]
    selected = [row for row in demo["rows"] if row["selected"]]
    false_selected = [row for row in demo["rows"] if row["false_selected_program"]]
    precision = 1.0 - (len(false_selected) / max(1, len(selected)))
    assert precision >= 0.99
    assert any(row["status"] == "AMBIGUOUS" for row in demo["rows"])


def test_m223_diverse_mutation_sweep() -> None:
    mutation = _analysis()["mutation"]
    target_ids = {row["target_id"] for row in mutation["rows"]}
    operators = {row["operator"] for row in mutation["rows"]}
    assert len(mutation["rows"]) >= 10000
    assert len(target_ids) >= 100
    assert len(operators) >= 10
    assert mutation["summary"]["false_accept"] == 0


def test_m223_rule_memory_reload_execution_retention() -> None:
    memory = _analysis()["rule_memory"]
    assert len(memory["rows"]) >= 100
    assert all(row["reload_retention"] == 1.0 for row in memory["rows"])
    assert all(row["execution_retention"] == 1.0 for row in memory["rows"])


def test_m223_sequential_acquires_100_distinct_rules_with_real_latency() -> None:
    final = _analysis()["sequential"]["rows"][-1]
    assert final["step"] == 100
    assert final["distinct_acquired_rules"] == 100
    assert final["execution_retention"] == 1.0
    assert final["latency_ms"] > 0


def test_m223_novelty_split_and_threshold() -> None:
    novelty = _analysis()["novelty"]["summary"]
    assert novelty["validation_only_threshold"] is True
    assert novelty["known_count"] >= 100
    assert novelty["novel_count"] >= 100
    assert novelty["novel_abstention"] >= 0.95
    assert novelty["false_known_rate"] <= 0.01


def test_m223_ranker_train_eval_disjoint() -> None:
    guidance = _analysis()["guidance"]
    assert guidance["train_eval_disjoint"] is True
    assert guidance["train_count"] == 5000
    assert guidance["validation_count"] == 1000
    assert guidance["heldout_instance_count"] == 500
    assert guidance["heldout_template_count"] == 200


def test_m223_negative_controls_never_property_verified() -> None:
    negative = _analysis()["negative"]
    assert len(negative["rows"]) >= 100
    assert negative["summary"]["accepted"] == 0
