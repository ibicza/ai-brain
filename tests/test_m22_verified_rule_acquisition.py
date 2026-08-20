import importlib.util
import sys
from pathlib import Path

import pytest


def load_m22():
    module_name = "m22_verified_rule_acquisition"
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "m22_verified_rule_acquisition.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_rule_memory_add_load_version_and_lookup(tmp_path: Path) -> None:
    m22 = load_m22()
    spec = next(item for item in m22.task_specs() if item.name == "drain_A_to_C")
    memory = m22.RuleMemory()

    record = memory.add_verified_rule(
        spec.target_program,
        signature=spec.signature,
        provenance="test",
        creation_method="canonical_ast",
        verification_tests=("smoke",),
        surface_name=spec.semantic_text(),
    )
    assert memory.find_by_semantic_hash(record.alpha_hash) == record

    path = tmp_path / "memory.json"
    memory.save(path)
    loaded = m22.RuleMemory.load(path)
    assert loaded.find_by_semantic_hash(record.alpha_hash) is not None

    versioned = loaded.version_rule(
        record.rule_id,
        m22.drain_program("B", "C"),
        signature=m22.RuleSignature(
            inputs=("B",),
            outputs=("C",),
            transfers=(("B", "C"),),
            terminate_when_empty=("B",),
            preserve=("A", "D"),
        ),
        provenance="test_update",
        creation_method="canonical_ast",
    )
    assert loaded.records[record.rule_id].deprecated
    assert versioned.version == 2


def test_duplicate_semantic_rule_detection() -> None:
    m22 = load_m22()
    spec = next(item for item in m22.task_specs() if item.name == "drain_A_to_C")
    memory = m22.RuleMemory()
    kwargs = {
        "signature": spec.signature,
        "provenance": "test",
        "creation_method": "canonical_ast",
        "verification_tests": ("smoke",),
        "surface_name": spec.semantic_text(),
    }
    memory.add_verified_rule(spec.target_program, **kwargs)
    with pytest.raises(ValueError, match="Duplicate semantic rule"):
        memory.add_verified_rule(spec.target_program, **kwargs)


def test_unverified_rule_rejection_and_false_accept_prevention() -> None:
    m22 = load_m22()
    merge = next(item for item in m22.task_specs() if item.name == "merge_two")
    bad = m22.clear_program("A")

    result = m22.RuleMemory().run_verification_suite(bad, merge.signature)
    assert result["verified"] is False
    with pytest.raises(ValueError, match="Unverified rule rejected"):
        m22.RuleMemory().add_verified_rule(
            bad,
            signature=merge.signature,
            provenance="test",
            creation_method="bad_candidate",
            verification_tests=("semantic_examples",),
        )
    assert m22.evaluate_confidence()["false_verified_program_rate"] == 0


def test_program_sketch_hole_typing_and_instantiation() -> None:
    m22 = load_m22()
    sketch = m22.sketch_by_name("DRAIN")

    assert sketch.holes()["SOURCE"] == m22.LOGICAL_VARS
    program = sketch.instantiate({"SOURCE": "A", "DEST": "C"})

    assert program.semantic_hash(
        alpha=True, order_insensitive=True
    ) == m22.drain_program("A", "C").semantic_hash(alpha=True, order_insensitive=True)


def test_grammar_constrained_production_masks() -> None:
    m22 = load_m22()
    action_mask = m22.grammar_production_mask("action_kind")
    variable_mask = m22.grammar_production_mask("variable", variables=("A", "C"))

    assert action_mask["MOVE_ONE"] == 1
    assert action_mask["A"] == 0
    assert variable_mask["A"] == 1
    assert variable_mask["B"] == 0
    with pytest.raises(ValueError):
        m22.grammar_production_mask("unknown")


def test_verifier_pruning_and_execution_guided_rejection() -> None:
    m22 = load_m22()
    invalid = m22.m21.ProgramAst(
        (
            m22.m21.ClauseAst(
                (m22.m21.PredicateAst("NONEMPTY", "A"),),
                m22.m21.ActionAst("HALT"),
            ),
            m22.m21.ClauseAst(
                (m22.m21.PredicateAst("NONEMPTY", "A"),),
                m22.m21.ActionAst("DROP_ONE", "A"),
            ),
        )
    )
    spec = next(item for item in m22.task_specs() if item.name == "drain_A_to_C")

    assert m22.is_valid_program(invalid) is False
    assert m22.partial_reject(invalid, spec) is True


def test_demonstration_consistency_and_ambiguity_detection() -> None:
    m22 = load_m22()
    spec = next(item for item in m22.task_specs() if item.name == "merge_two")
    candidates = m22.candidates_consistent_with_demos(m22.demonstrations_for(spec, 5))
    target_hash = spec.target_program.semantic_hash(alpha=True, order_insensitive=True)

    assert any(
        program.semantic_hash(alpha=True, order_insensitive=True) == target_hash
        for program in candidates
    )
    ambiguity = m22.evaluate_ambiguity()
    assert ambiguity["one_demo_ambiguous"] is True
    assert ambiguity["one_demo_candidate_set_size"] > 1


def test_learn_once_reuse_executes_stored_rule_on_ranges() -> None:
    m22 = load_m22()
    result = m22.evaluate_learn_once_reuse()

    for row in result["rows"]:
        assert row["stored"] == 1
        assert row["execution_0_10"] == 1
        assert row["execution_11_20"] == 1
        assert row["execution_21_50"] == 1
        assert row["execution_51_100"] == 1


def test_subprogram_call_execution_for_merge_plans() -> None:
    m22 = load_m22()
    result = m22.evaluate_subprogram_composition()

    assert {row["plan"] for row in result["rows"]} == {
        "merge_two_from_drains",
        "merge_three_from_drains",
    }
    assert all(row["execution_success"] == 1 for row in result["rows"])


def test_heldout_template_split_and_no_model_visible_ids() -> None:
    m22 = load_m22()
    overlap = m22.sketch_overlap_audit()
    memory = m22.build_memory(include_heldout_templates=False, distractors=2)

    assert overlap["exact_sketch_overlap"] == 0
    assert "TWO_SOURCE_TRANSFER" in overlap["heldout_templates"]
    for record in memory.records.values():
        assert record.rule_id not in record.surface_name
        assert "rule-" not in record.program_json


def test_complete_rule_retrieval_and_slot_filling_success() -> None:
    m22 = load_m22()
    memory = m22.build_memory(include_heldout_templates=True, distractors=5)
    retrieval = m22.evaluate_complete_rule_retrieval(memory)
    slots = m22.evaluate_slot_filling()

    assert retrieval["structured"]["seen_rule"]["top1"] == 1
    assert retrieval["structured"]["paraphrased_structured_spec"]["top1"] == 1
    assert slots["summary"]["complete_ast_semantic_exact"] == 1
    assert slots["summary"]["verification_success"] == 1
