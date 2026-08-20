import importlib.util
import sys
from pathlib import Path

import pytest


def load_m21():
    module_name = "m21_hybrid_neural_compiler_interpreter"
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "m21_hybrid_neural_compiler_interpreter.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_typed_ast_construction_and_exact_action() -> None:
    m21 = load_m21()
    program = m21.merge_two_ast(m21.TRAIN_VARS)
    binding = m21.BindingAst({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    state = m21.merge_state(binding, left=2, right=3)

    program.validate(binding.mapping.keys())

    index = program.applicable_clause_index(binding, state)
    action = program.clauses[index].action.resolve(binding)
    assert index == 0
    assert action.render() == "M R0 R2"


def test_ast_normalization_alpha_and_clause_order_equivalence() -> None:
    m21 = load_m21()
    program = m21.merge_two_ast(m21.TRAIN_VARS)
    alpha = program.alpha(m21.ALPHA_VARS)
    reordered = m21.ProgramAst(tuple(reversed(program.clauses)), "reordered")

    assert program.semantic_hash(alpha=True) == alpha.semantic_hash(alpha=True)
    assert program.semantic_hash(
        alpha=True, order_insensitive=True
    ) == reordered.semantic_hash(alpha=True, order_insensitive=True)
    assert program.semantic_hash(alpha=False) != alpha.semantic_hash(alpha=False)


def test_deterministic_parser_roundtrip() -> None:
    m21 = load_m21()
    program = m21.merge_two_ast(m21.TRAIN_VARS)
    binding = m21.BindingAst({"A": "R3", "B": "R0", "C": "R2", "D": "R1"})
    text = m21.render_canonical_program(program, binding)

    parsed_program, parsed_binding = m21.parse_canonical_dsl(text)

    assert parsed_binding == binding
    assert parsed_program.semantic_hash(alpha=True) == program.semantic_hash(alpha=True)


def test_exact_closed_loop_merge_two_and_merge_three() -> None:
    m21 = load_m21()
    binding = m21.BindingAst({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    merge_two = m21.merge_two_ast(m21.TRAIN_VARS)
    merge_three = m21.merge_three_ast(m21.TRAIN_VARS)

    result_two = m21.exact_closed_loop(
        merge_two, binding, m21.merge_state(binding, 3, 4)
    )
    result_three = m21.exact_closed_loop(
        merge_three, binding, m21.merge_three_state(binding, 3, 4, 5)
    )

    assert result_two["final_state"]["R2"] == 7
    assert result_two["final_state"]["R0"] == 0
    assert result_two["final_state"]["R1"] == 0
    assert result_three["final_state"]["R3"] == 12
    assert result_three["final_state"]["R0"] == 0
    assert result_three["final_state"]["R1"] == 0
    assert result_three["final_state"]["R2"] == 0


def test_binding_matrix_and_pointer_ids() -> None:
    m21 = load_m21()
    binding = m21.BindingAst({"A": "R3", "B": "R0", "C": "R2", "D": "R1"})

    assert binding.pointer_ids(("A", "B", "C", "D")) == [3, 0, 2, 1]
    assert binding.matrix(("A", "B")) == [[0, 0, 0, 1], [1, 0, 0, 0]]


def test_clause_mask_and_selector_input_construction() -> None:
    m21 = load_m21()
    binding = m21.BindingAst({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    program = m21.merge_two_ast(m21.TRAIN_VARS)
    state = m21.merge_state(binding, left=0, right=2)
    clause_index = program.applicable_clause_index(binding, state)
    example = m21.StepExample(
        program, binding, state, clause_index, "A_TO_B_SWITCH", "test"
    )

    encoded = m21.encode_selector_example(example)

    assert encoded["labels"] == 1
    assert encoded["clause_mask"][:3] == [1, 1, 1]
    assert encoded["clause_mask"][3:] == [0] * (m21.MAX_CLAUSES - 3)
    assert encoded["pred_truth"][1][:2] == [1, 1]


def test_compiler_ast_validity_with_deterministic_parser() -> None:
    m21 = load_m21()
    binding = m21.BindingAst({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    program = m21.heldout_program_asts()[0]
    row = m21.compiler_rows([program], [binding], "eval")[0]

    parsed, _ = m21.parse_canonical_dsl(row["surface"])

    assert (
        parsed.semantic_hash(alpha=True, order_insensitive=True) == row["semantic_hash"]
    )


def test_verifier_rejects_overlapping_or_invalid_programs() -> None:
    m21 = load_m21()
    binding = m21.BindingAst({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    overlapping = m21.ProgramAst(
        (
            m21.ClauseAst((m21.PredicateAst("NONEMPTY", "A"),), m21.ActionAst("HALT")),
            m21.ClauseAst(
                (m21.PredicateAst("NONEMPTY", "A"),), m21.ActionAst("DROP_ONE", "A")
            ),
        )
    )
    invalid = m21.ProgramAst(
        (m21.ClauseAst((m21.PredicateAst("NONEMPTY", "Z"),), m21.ActionAst("HALT")),)
    )

    with pytest.raises(ValueError):
        m21.verify_program(overlapping, binding)
    with pytest.raises(ValueError):
        invalid.validate(binding.mapping.keys())


def test_heldout_ast_split_is_clean() -> None:
    m21 = load_m21()
    train_hashes = {
        program.semantic_hash(alpha=True, order_insensitive=True)
        for program in m21.train_program_asts()
    }
    heldout_hashes = {
        program.semantic_hash(alpha=True, order_insensitive=True)
        for program in [*m21.heldout_program_asts(), m21.merge_two_ast(m21.TRAIN_VARS)]
    }

    assert train_hashes.isdisjoint(heldout_hashes)


def test_no_model_visible_ids_in_canonical_surface() -> None:
    m21 = load_m21()
    binding = m21.BindingAst({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    text = m21.render_canonical_program(m21.merge_two_ast(m21.TRAIN_VARS), binding)

    assert "PROGRAM_ID" not in text
    assert "CASE" not in text
    assert "merge" not in text.lower()


def test_program_counterfactuals_change_and_equivalences_hold() -> None:
    m21 = load_m21()
    controls = m21.counterfactual_controls()

    assert controls["correct"] != controls["wrong_program"]
    assert controls["correct"] == controls["reordered_equivalent"]
    assert controls["correct"] == controls["alpha_equivalent"]
