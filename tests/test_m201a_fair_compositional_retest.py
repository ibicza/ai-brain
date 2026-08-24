import importlib.util
import sys
from pathlib import Path


def load_m201a():
    module_name = "m201a_fair_compositional_retest"
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "m201a_fair_compositional_retest.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_binding_metric_records_are_separated() -> None:
    m201a = load_m201a()
    binding = m201a.m201.Binding({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})

    rows = m201a.binding_records([binding], include_full_table=True, split="eval")
    counts = {}
    for row in rows:
        metric = row["metadata"]["binding_metric"]
        counts[metric] = counts.get(metric, 0) + 1

    assert counts == {"l2p": 4, "p2l": 4, "full_table": 1}
    assert {row["task_type"] for row in rows} == {
        "m201a.binding.l2p",
        "m201a.binding.p2l",
        "m201a.binding.full_table",
    }


def test_binding_candidates_are_metric_specific() -> None:
    m201a = load_m201a()
    l2p = {"metadata": {"binding_metric": "l2p"}}
    p2l = {"metadata": {"binding_metric": "p2l"}}
    table = {
        "metadata": {"binding_metric": "full_table", "variables": ("A", "B", "C", "D")}
    }

    assert m201a.candidates_for_expected("R0", l2p) == list(m201a.m201.REGISTERS)
    assert m201a.candidates_for_expected("A", p2l) == list(m201a.ALL_VARS)
    assert len(m201a.candidates_for_expected("A R0 B R1 C R2 D R3", table)) == 24


def test_known_token_alpha_renaming_uses_train_seen_symbols() -> None:
    m201a = load_m201a()
    train_tokens = {token for pair in m201a.train_alpha_pairs() for token in pair}
    eval_tokens = {token for pair in m201a.eval_alpha_pairs() for token in pair}

    assert eval_tokens <= train_tokens
    assert set(m201a.ALL_VARS) <= train_tokens


def test_heldout_binding_split_is_disjoint() -> None:
    m201a = load_m201a()
    train, heldout = m201a.all_split_bindings()

    train_hashes = {m201a.binding_hash(binding) for binding in train}
    heldout_hashes = {m201a.binding_hash(binding) for binding in heldout}

    assert heldout_hashes
    assert train_hashes.isdisjoint(heldout_hashes)


def test_single_clause_ladder_axes_are_distinct() -> None:
    m201a = load_m201a()
    train_specs = {spec.name for spec in m201a.train_clause_specs()}
    heldout_specs = {spec.name for spec in m201a.heldout_clause_specs()}
    train, heldout = m201a.all_split_bindings()
    rows = m201a.build_eval_rows(train, heldout)

    assert train_specs.isdisjoint(heldout_specs)
    assert rows["single_clause_seen_seen_binding"]
    assert rows["single_clause_new_seen_binding"]
    assert rows["single_clause_seen_heldout_binding"]
    assert rows["single_clause_new_heldout_binding"]


def test_primitive_replay_contains_prerequisite_tasks() -> None:
    m201a = load_m201a()
    train, _heldout = m201a.all_split_bindings()
    rows = m201a.build_train_rows(train)["program_replay25"]
    task_types = {row["task_type"] for row in rows}

    assert "m201a.binding.l2p" in task_types
    assert "m201a.predicate" in task_types
    assert "m201a.action.resolve" in task_types
    assert "m201a.single_clause" in task_types
    assert any(task_type.startswith("m201a.program") for task_type in task_types)


def test_selected_clause_teacher_forcing_uses_clause_text_not_index_only() -> None:
    m201a = load_m201a()
    binding = m201a.m201.Binding({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    program = m201a.m201.merge_two_program(m201a.PRIMARY_VARS)
    spec = m201a.m201.EpisodeSpec(
        program,
        binding,
        m201a.m201.merge_state(program, binding, left=0, right=2),
        "eval",
        "merge_two",
    )

    rows = m201a.selected_clause_records([spec], split_name="teacher_forced_merge_two")

    assert rows[0]["prompt"].startswith("SEL\n")
    assert "CLS" not in rows[0]["prompt"]
    assert "E A NE B M B C" in rows[0]["prompt"]
    assert rows[0]["answer"] == "FINAL M R1 R2"


def test_merge_two_phase_labeling() -> None:
    m201a = load_m201a()
    binding = m201a.m201.Binding({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    program = m201a.m201.merge_two_program(m201a.PRIMARY_VARS)

    assert (
        m201a.merge_two_phase(
            program, binding, {"R0": 2, "R1": 3, "R2": 0, "R3": 0}, False
        )
        == "PHASE_A_MOVE"
    )
    assert (
        m201a.merge_two_phase(
            program, binding, {"R0": 0, "R1": 3, "R2": 2, "R3": 0}, False
        )
        == "A_TO_B_SWITCH"
    )
    assert (
        m201a.merge_two_phase(
            program, binding, {"R0": 0, "R1": 2, "R2": 3, "R3": 0}, True
        )
        == "PHASE_B_MOVE"
    )
    assert (
        m201a.merge_two_phase(
            program, binding, {"R0": 0, "R1": 0, "R2": 5, "R3": 0}, True
        )
        == "FINAL_HALT"
    )


def test_merge_two_records_include_switch_and_b_move_phases() -> None:
    m201a = load_m201a()
    binding = m201a.m201.Binding({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    program = m201a.m201.merge_two_program(m201a.PRIMARY_VARS)

    rows = m201a.merge_two_records(
        program, [binding], (2,), split_name="merge_two_seen"
    )
    phases = [row["metadata"]["phase"] for row in rows]

    assert "PHASE_A_MOVE" in phases
    assert "A_TO_B_SWITCH" in phases
    assert "PHASE_B_MOVE" in phases
    assert "FINAL_HALT" in phases


def test_policy_action_vocabulary_and_environment_transition() -> None:
    m201a = load_m201a()
    actions = m201a.action_vocab()
    env = m201a.m201.RegisterEnvironment({"R0": 1, "R1": 0, "R2": 0, "R3": 0})

    assert len(actions) == 17
    assert "H" in actions
    assert "D R0" in actions
    assert "M R0 R1" in actions

    env.step(m201a.m201.parse_physical_action("M R0 R1"))
    assert env.state["R0"] == 0
    assert env.state["R1"] == 1
    assert not env.invalid


def test_parse_target_preserves_clause_handles() -> None:
    m201a = load_m201a()

    assert m201a.parse_target("FINAL C0") == "C0"
    assert m201a.parse_target("FINAL M R0 R1") == "M R0 R1"


def test_no_nuisance_ids_and_structural_overlap_manifest() -> None:
    m201a = load_m201a()
    train, heldout = m201a.all_split_bindings()
    train_rows = m201a.build_train_rows(train)
    eval_rows = m201a.build_eval_rows(train, heldout)
    manifest = m201a.build_manifest(train_rows, eval_rows, train, heldout)

    assert manifest["structural_overlap"]["forbidden_prompt_count"] == 0
    assert manifest["structural_overlap"]["normalized_ast_overlap_heldout_program"] == 0
    assert manifest["structural_overlap"]["template_overlap_heldout_program"] == 0
    assert manifest["structural_overlap"]["template_overlap_merge_two"] == 0
