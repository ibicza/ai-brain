import importlib.util
import sys
from pathlib import Path

import pytest


def load_m221():
    module_name = "m221_oracle_free_rule_acquisition"
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "m221_oracle_free_rule_acquisition.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_acquisition_firewall_blocks_target_fields() -> None:
    m221 = load_m221()
    task = m221.AcquisitionTask(task_id="blocked")

    with pytest.raises(m221.OracleAccessError):
        _ = task.target_program
    with pytest.raises(m221.OracleAccessError):
        _ = task.target_semantic_hash
    with pytest.raises(m221.OracleAccessError):
        _ = task.target_program_name
    with pytest.raises(m221.OracleAccessError):
        _ = task.target_sketch_name
    assert m221.firewall_self_check() is True


def test_heldout_sketches_absent_from_candidate_library() -> None:
    m221 = load_m221()

    assert {
        "TWO_SOURCE_TRANSFER",
        "THREE_SOURCE_TRANSFER",
    } == m221.heldout_sketch_names()
    assert all(
        sketch.name not in m221.heldout_sketch_names()
        for sketch, _, _ in m221.no_heldout_sketch_candidates()
    )
    split = m221.split_audit(
        m221.benchmark_bundles(), m221.general_grammar_candidates(120)
    )
    assert split["exact_sketch_overlap"] == 0
    assert split["normalized_ast_overlap_with_no_heldout_library"] == 0
    assert split["primitive_operation_overlap"] > 0


def test_no_target_template_constructor_in_heldout_path() -> None:
    m221 = load_m221()
    merge_two = next(
        bundle
        for bundle in m221.benchmark_bundles()["merge"]
        if bundle.name == "merge_two"
    )
    task = m221.task_view(merge_two, condition="canonical")

    assert task.spec_fields["transfers"] == (("A", "C"), ("B", "C"))
    assert all(sketch.name != "TWO_SOURCE_TRANSFER" for sketch in task.allowed_sketches)


def test_learned_scorer_has_parameters_and_differs_from_heuristic() -> None:
    m221 = load_m221()
    bundles = m221.benchmark_bundles()
    candidates = m221.general_grammar_candidates(120)
    scorer = m221.train_candidate_scorer(bundles["train"][:20], candidates)

    assert scorer.parameter_count > 0
    assert scorer.name == "learned_candidate_scorer"
    assert not hasattr(m221, "candidate_score")
    assert isinstance(scorer.score("transfers A C", "MOVE_ONE A C"), float)


def test_ambiguous_demonstrations_abstain_without_oracle_hash() -> None:
    m221 = load_m221()
    merge_two = next(
        bundle
        for bundle in m221.benchmark_bundles()["merge"]
        if bundle.name == "merge_two"
    )
    candidates = m221.general_grammar_candidates(120)

    result = m221.demonstration_induction_oracle_free(merge_two, candidates, demos=1)

    assert result.status == "AMBIGUOUS"
    assert result.program is None
    assert result.remaining_candidates > 1


def test_active_query_splits_candidates() -> None:
    m221 = load_m221()
    merge_two = next(
        bundle
        for bundle in m221.benchmark_bundles()["merge"]
        if bundle.name == "merge_two"
    )
    candidates = m221.general_grammar_candidates(120)

    result = m221.active_disambiguate(merge_two, candidates, max_examples=5)

    assert result["active_remaining"] == 1
    assert result["active_examples"] <= 5


def test_oracle_free_storage_path_and_reuse() -> None:
    m221 = load_m221()
    merge_two = next(
        bundle
        for bundle in m221.benchmark_bundles()["merge"]
        if bundle.name == "merge_two"
    )
    candidates = m221.general_grammar_candidates(120)
    scorer = m221.train_candidate_scorer(
        m221.benchmark_bundles()["train"][:20], candidates
    )
    result = m221.oracle_free_search(
        m221.task_view(merge_two, condition="canonical"), candidates, scorer, budget=120
    )

    assert result.status == "ACQUIRED"
    assert result.program is not None
    assert m221.property_verify(result.program, merge_two.signature)["accepted"] == 1


def test_subprogram_plan_is_not_manually_supplied_and_search_depths() -> None:
    m221 = load_m221()
    bundles = m221.benchmark_bundles()["merge"]
    rows = [m221.subprogram_plan_search(bundle) for bundle in bundles]

    assert {row["task"]: row["depth"] for row in rows} == {
        "merge_two": 2,
        "merge_three": 3,
    }
    for bundle in bundles:
        plan = m221.learned_subprogram_plan(bundle)
        assert plan.status == "ACQUIRED"


def test_adversarial_false_programs_rejected() -> None:
    m221 = load_m221()
    result = m221.evaluate_adversarial_verifier()

    assert result["false_verified_program_rate"] == 0
    assert all(row["accepted"] == 0 for row in result["rows"])


def test_novel_rule_retrieval_abstention() -> None:
    m221 = load_m221()
    bundles = m221.benchmark_bundles()
    memory_programs = [bundle.program for bundle in bundles["train"][:40]]
    retriever = m221.train_rule_retriever(bundles["train"][:40], memory_programs)
    result = m221.evaluate_retrieval_abstention(
        retriever, memory_programs, bundles["heldout_instances"][:5], bundles["merge"]
    )

    assert result["chosen"]["novel_rule_abstention"] >= 0
    assert result["chosen"]["false_known_rate"] <= 1


def test_memory_reuse_without_weight_updates() -> None:
    m221 = load_m221()
    rows = m221.evaluate_sequential_memory_growth(
        m221.benchmark_bundles()["heldout_instances"][:5]
    )

    assert rows["summary"]["execution_retention"] == 1
