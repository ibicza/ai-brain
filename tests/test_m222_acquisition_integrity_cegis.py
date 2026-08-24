from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from ai_brain.rules.ast import (
    ActionAst,
    ClauseAst,
    PredicateAst,
    ProgramAst,
    RegisterState,
)
from ai_brain.rules.cegis import (
    AcquisitionTask,
    HiddenTaskOracle,
    OracleAccessError,
    cegis_acquire,
    semantic_classes,
)
from ai_brain.rules.grammar import (
    enumerate_generic_programs,
    generic_three_phase,
    generic_transfer_one,
    generic_two_phase,
    summarize_candidate_space,
)
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.subprograms import search_macro_plan
from ai_brain.rules.verifier import property_verify


def load_m222():
    module_name = "m222_acquisition_integrity_cegis"
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "m222_acquisition_integrity_cegis.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


m222 = load_m222()


def test_oracle_boundary_exposes_no_target_fields() -> None:
    task = AcquisitionTask(task_id="blocked", specification=None)
    for attr in ("target_ast", "target_hash", "target_name", "target_template"):
        with pytest.raises(OracleAccessError):
            getattr(task, attr)

    oracle = HiddenTaskOracle(generic_transfer_one("A", "C", name="hidden"))
    assert not hasattr(oracle, "target_program")
    assert oracle.query(RegisterState({"R0": 2, "R1": 0, "R2": 0, "R3": 0})) == {
        "R0": 0,
        "R1": 0,
        "R2": 2,
        "R3": 0,
    }


def test_source_audit_has_no_target_specific_constructors() -> None:
    audit = m222.source_oracle_audit()
    assert audit["forbidden_constructor_refs"] == 0
    assert all(audit["target_access_guards"].values())


def test_candidate_space_is_actual_alpha_unique() -> None:
    summary = summarize_candidate_space(300)
    assert summary.raw_generated == 300
    assert summary.exact_ast_unique == 300
    assert summary.alpha_normalized_unique == 300


def test_promptless_structural_split_can_be_disjoint() -> None:
    train = list(enumerate_generic_programs(120))
    heldout = list(enumerate_generic_programs(180))[120:180]
    train_exact = {
        program.semantic_hash(alpha=False, order_insensitive=False) for program in train
    }
    heldout_exact = {
        program.semantic_hash(alpha=False, order_insensitive=False)
        for program in heldout
    }
    train_alpha = {
        program.semantic_hash(alpha=True, order_insensitive=True) for program in train
    }
    heldout_alpha = {
        program.semantic_hash(alpha=True, order_insensitive=True) for program in heldout
    }
    assert train_exact.isdisjoint(heldout_exact)
    assert train_alpha.isdisjoint(heldout_alpha)


def test_property_verifier_rejects_noise_register_side_effects() -> None:
    program = ProgramAst(
        (
            ClauseAst((PredicateAst("NONEMPTY", "D"),), ActionAst("DROP_ONE", "D")),
            ClauseAst(
                (PredicateAst("NONEMPTY", "A"),), ActionAst("MOVE_ONE", "A", "C")
            ),
            ClauseAst(
                (PredicateAst("EMPTY", "A"), PredicateAst("NONEMPTY", "B")),
                ActionAst("MOVE_ONE", "B", "C"),
            ),
            ClauseAst(
                (PredicateAst("EMPTY", "A"), PredicateAst("EMPTY", "B")),
                ActionAst("HALT"),
            ),
        ),
        "bad_extra_d_side_effect",
    )
    result = property_verify(program, m222.spec_two("A", "B", "C"), large=True)
    assert result.accepted is False
    assert result.status == VerificationStatus.REJECTED


def test_mutation_sweep_has_no_false_accepts_on_small_regression() -> None:
    result = m222.mutation_sweep(360)
    assert result["surviving_mutants"] == 0
    assert result["false_accept_rate"] == 0


def test_cegis_does_not_accept_first_demo_candidate_when_ambiguous() -> None:
    candidates = [
        generic_transfer_one("A", "C", name="transfer_a"),
        generic_transfer_one("B", "C", name="transfer_b"),
    ]
    task = AcquisitionTask(task_id="demo_only", specification=None, search_budget=2)
    result = cegis_acquire(task, candidates)
    assert result.status == VerificationStatus.AMBIGUOUS
    assert result.program is None
    assert result.semantic_class_count > 1


def test_active_query_collapses_demo_only_hypothesis_space() -> None:
    target = generic_transfer_one("A", "C", name="hidden")
    oracle = HiddenTaskOracle(target)
    candidates = [
        generic_transfer_one("A", "C", name="transfer_a"),
        generic_transfer_one("B", "C", name="transfer_b"),
    ]
    task = AcquisitionTask(
        task_id="active",
        specification=None,
        search_budget=2,
        query_budget=2,
    )
    result = cegis_acquire(task, candidates, query_callback=oracle.query)
    assert result.status == VerificationStatus.IDENTIFIED_IN_HYPOTHESIS_SPACE
    assert result.query_count == 1
    assert oracle.score_after_termination(result.program)


def test_full_spec_cegis_returns_property_verified_status() -> None:
    candidates = [
        generic_two_phase("A", "B", "C", name="target"),
        *list(enumerate_generic_programs(500)),
    ]
    task = AcquisitionTask(
        task_id="full",
        specification=m222.spec_two("A", "B", "C"),
        search_budget=len(candidates),
    )
    result = cegis_acquire(task, candidates)
    assert result.status == VerificationStatus.PROPERTY_VERIFIED
    assert result.program is not None


def test_semantic_classes_deduplicate_order_and_alpha_equivalence() -> None:
    left = generic_two_phase("A", "B", "C", name="left")
    right = generic_two_phase("B", "A", "C", name="right")
    classes = semantic_classes(
        [left, right],
        [
            RegisterState({"R0": 1, "R1": 2, "R2": 0, "R3": 0}),
            RegisterState({"R0": 0, "R1": 2, "R2": 1, "R3": 0}),
        ],
    )
    assert len(classes) == 1


def test_rule_memory_status_policy_duplicate_and_reload(tmp_path: Path) -> None:
    memory = RuleMemory()
    program = generic_three_phase("A", "B", "C", "D", name="three")
    spec = m222.spec_three("A", "B", "C", "D")
    evidence = property_verify(program, spec, large=True)
    memory.add(
        program,
        spec,
        VerificationStatus.PROPERTY_VERIFIED,
        verification_evidence=evidence,
    )
    with pytest.raises(ValueError, match="Duplicate semantic rule"):
        memory.add(
            program,
            spec,
            VerificationStatus.PROPERTY_VERIFIED,
            verification_evidence=evidence,
        )
    with pytest.raises(ValueError, match="rejects status"):
        RuleMemory().add(
            generic_transfer_one("A", "C", name="provisional"),
            ProgramSpecification(),
            VerificationStatus.AMBIGUOUS,
        )

    path = tmp_path / "memory.json"
    memory.save(path)
    loaded = RuleMemory.load(path)
    assert len(loaded.records) == 1
    assert loaded.programs()[0].semantic_hash(
        alpha=True, order_insensitive=True
    ) == program.semantic_hash(alpha=True, order_insensitive=True)


def test_rule_memory_rejects_corrupted_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad_memory.json"
    path.write_text(
        json.dumps({"schema_version": 999, "records": []}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Unsupported RuleMemory schema"):
        RuleMemory.load(path)


def test_subprogram_search_finds_plan_without_target_sequence() -> None:
    plan, evaluated = search_macro_plan(m222.spec_two("A", "B", "C"), max_depth=2)
    assert plan is not None
    assert evaluated > 0
    assert len(plan.calls) == 2
