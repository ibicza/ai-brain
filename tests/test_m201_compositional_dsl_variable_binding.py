import importlib.util
import sys
from pathlib import Path


def load_m201():
    module_name = "m201_compositional_dsl_variable_binding"
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "m201_compositional_dsl_variable_binding.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_binding_logical_to_physical_and_inverse() -> None:
    m201 = load_m201()
    binding = m201.Binding({"A": "R3", "B": "R0", "C": "R2", "D": "R1"})

    assert binding.physical("A") == "R3"
    assert binding.physical("C") == "R2"
    assert binding.logical("R3") == "A"
    assert binding.logical("R0") == "B"


def test_alpha_renaming_preserves_normalized_ast_and_template() -> None:
    m201 = load_m201()
    program = m201.merge_two_program(m201.TRAIN_VARS)
    alpha = program.alpha(("X", "Y", "Z"))

    assert m201.normalized_ast_hash(program) == m201.normalized_ast_hash(alpha)
    assert m201.template_hash(program) == m201.template_hash(alpha)
    assert "X" in m201.render_program(
        alpha, m201.Binding({"X": "R0", "Y": "R1", "Z": "R2"}), m201.zero_state()
    )


def test_predicate_evaluation_under_binding() -> None:
    m201 = load_m201()
    binding = m201.Binding({"A": "R2", "B": "R1", "C": "R0", "D": "R3"})
    state = {"R0": 0, "R1": 0, "R2": 3, "R3": 0}

    assert m201.Predicate("A", "NONEMPTY").matches(state, binding)
    assert not m201.Predicate("B", "NONEMPTY").matches(state, binding)
    assert m201.Predicate("B", "EMPTY").matches(state, binding)


def test_action_argument_resolution() -> None:
    m201 = load_m201()
    binding = m201.Binding({"A": "R3", "B": "R0", "C": "R2", "D": "R1"})

    assert m201.Action("MOVE_ONE", "A", "C").resolve(binding).render() == "M R3 R2"
    assert m201.Action("DROP_ONE", "B").resolve(binding).render() == "D R0"
    assert m201.Action("HALT").resolve(binding).render() == "H"


def test_ast_hashing_and_template_hashing() -> None:
    m201 = load_m201()
    drain_ac = m201.drain_program("A", "C")
    drain_bd = m201.drain_program("B", "D")
    clear_a = m201.clear_program("A")

    assert m201.normalized_ast(drain_ac)[0]["action"]["kind"] == "MOVE_ONE"
    assert m201.normalized_ast_hash(drain_ac) == m201.normalized_ast_hash(drain_bd)
    assert m201.template_hash(drain_ac) == m201.template_hash(drain_bd)
    assert m201.template_hash(drain_ac) != m201.template_hash(clear_a)


def test_heldout_ast_and_template_splits_are_clean() -> None:
    m201 = load_m201()
    train_programs = m201.grammar_train_programs()
    heldout_programs = m201.grammar_heldout_programs()
    merge_two = m201.merge_two_program(m201.TRAIN_VARS)
    train_ast_hashes = {m201.normalized_ast_hash(program) for program in train_programs}
    train_template_hashes = {m201.template_hash(program) for program in train_programs}

    assert train_ast_hashes.isdisjoint(
        {m201.normalized_ast_hash(program) for program in heldout_programs}
    )
    assert train_template_hashes.isdisjoint(
        {m201.template_hash(program) for program in heldout_programs}
    )
    assert m201.template_hash(merge_two) not in train_template_hashes


def test_heldout_register_bindings_are_disjoint() -> None:
    m201 = load_m201()
    train_bindings, heldout_bindings = m201.split_bindings(
        m201.all_bindings(m201.TRAIN_VARS)
    )
    train_hashes = {
        m201.stable_hash(str(binding.canonical_items())) for binding in train_bindings
    }
    heldout_hashes = {
        m201.stable_hash(str(binding.canonical_items())) for binding in heldout_bindings
    }

    assert train_hashes.isdisjoint(heldout_hashes)
    assert heldout_bindings


def test_clause_order_semantic_equivalence() -> None:
    m201 = load_m201()
    program = m201.drop_move_then_drop_program("A", "B", "C")
    binding = m201.Binding({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    state = {"R0": 0, "R1": 4, "R2": 0, "R3": 0}
    spec = m201.EpisodeSpec(
        program,
        binding,
        state,
        "eval",
        "order_invariance",
        clause_order=tuple(reversed(range(len(program.clauses)))),
    )

    assert m201.validate_mutually_exclusive(program, binding)
    assert m201.apply_oracle(program, binding, state)["actions"][0] == "M R1 R2"
    assert "M B C" in m201.render_prompt_for_spec(spec, m201.RegisterEnvironment(state))


def test_counterfactual_program_generation_changes_action() -> None:
    m201 = load_m201()
    binding = m201.Binding({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    state = {"R0": 2, "R1": 0, "R2": 0, "R3": 0}
    move = m201.Program(
        "move_counterfactual",
        (
            m201.Clause(
                (m201.Predicate("A", "NONEMPTY"),), m201.Action("MOVE_ONE", "A", "C")
            ),
        ),
        "test",
    )
    drop = m201.Program(
        "drop_counterfactual",
        (
            m201.Clause(
                (m201.Predicate("A", "NONEMPTY"),), m201.Action("DROP_ONE", "A")
            ),
        ),
        "test",
    )

    assert move.oracle_action(state, binding).render() == "M R0 R2"
    assert drop.oracle_action(state, binding).render() == "D R0"


def test_teacher_forced_clause_records_include_selected_clause() -> None:
    m201 = load_m201()
    binding = m201.Binding({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    program = m201.merge_two_program(m201.TRAIN_VARS)
    spec = m201.EpisodeSpec(
        program,
        binding,
        m201.merge_state(program, binding, left=0, right=2),
        "eval",
        "merge_two",
    )

    rows = m201.teacher_forced_records([spec], start_index=0)

    assert rows[0]["task_type"] == "m201.teacher_forced_clause"
    assert "CLS 1" in rows[0]["prompt"]
    assert rows[0]["answer"] == "FINAL M R1 R2"


def test_merge_two_oracle_semantics() -> None:
    m201 = load_m201()
    binding = m201.Binding({"A": "R3", "B": "R0", "C": "R2", "D": "R1"})
    program = m201.merge_two_program(m201.TRAIN_VARS)
    state = m201.merge_state(program, binding, left=3, right=4)

    result = m201.apply_oracle(program, binding, state)

    assert result["terminated"]
    assert not result["invalid"]
    assert result["final_state"]["R2"] == 7
    assert result["final_state"]["R3"] == 0
    assert result["final_state"]["R0"] == 0


def test_no_visible_program_or_case_ids_in_prompts() -> None:
    m201 = load_m201()
    binding = m201.Binding({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    program = m201.merge_two_program(m201.TRAIN_VARS)
    prompt = m201.render_prompt_for_spec(
        m201.EpisodeSpec(
            program,
            binding,
            m201.merge_state(program, binding, left=1, right=1),
            "eval",
            "merge_two",
        ),
        m201.RegisterEnvironment(m201.merge_state(program, binding, left=1, right=1)),
    )

    assert not m201.prompt_has_forbidden_marker(prompt)
    assert "PROGRAM_ID" not in prompt
    assert "CASE" not in prompt
