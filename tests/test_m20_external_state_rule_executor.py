from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "m20_external_state_rule_executor.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "m20_external_state_rule_executor",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_move_one_semantics() -> None:
    m20 = _load_module()
    env = m20.RegisterEnvironment(m20.state(R0=2, R1=0))

    result = env.step(m20.Action("MOVE_ONE", "R0", "R1"))

    assert not result.invalid
    assert result.state["R0"] == 1
    assert result.state["R1"] == 1


def test_drop_one_semantics() -> None:
    m20 = _load_module()
    env = m20.RegisterEnvironment(m20.state(R2=3))

    result = env.step(m20.Action("DROP_ONE", "R2"))

    assert not result.invalid
    assert result.state["R2"] == 2


def test_halt_terminates_without_state_change() -> None:
    m20 = _load_module()
    env = m20.RegisterEnvironment(m20.state(R0=1))

    result = env.step(m20.Action("HALT"))

    assert result.terminated
    assert result.state == m20.state(R0=1)


def test_invalid_action_rejection() -> None:
    m20 = _load_module()
    env = m20.RegisterEnvironment(m20.state(R0=0, R1=0))

    result = env.step(m20.Action("MOVE_ONE", "R0", "R1"))

    assert result.invalid
    assert env.invalid


def test_rule_predicate_evaluation() -> None:
    m20 = _load_module()
    state = m20.state(R0=0, R1=2)

    assert m20.Predicate("R0", "EMPTY").matches(state)
    assert m20.Predicate("R1", "NONEMPTY").matches(state)
    assert not m20.Predicate("R1", "EMPTY").matches(state)


def test_mutually_exclusive_program_validation() -> None:
    m20 = _load_module()

    assert m20.validate_mutually_exclusive(m20.drain_program("R0", "R1"))
    assert m20.validate_mutually_exclusive(m20.merge_two_program("R0", "R1", "R2"))


def test_oracle_interpreter_trajectory_correctness() -> None:
    m20 = _load_module()
    program = m20.drain_program("R0", "R2")

    result = m20.apply_oracle(program, m20.state(R0=4, R2=1))

    assert result["terminated"]
    assert not result["invalid"]
    assert result["final_state"]["R0"] == 0
    assert result["final_state"]["R2"] == 5
    assert result["actions"] == [
        "MOVE_ONE R0 R2",
        "MOVE_ONE R0 R2",
        "MOVE_ONE R0 R2",
        "MOVE_ONE R0 R2",
        "HALT",
    ]


def test_program_counterfactual_generation_changes_action_for_same_state() -> None:
    m20 = _load_module()
    specs = m20.counterfactual_specs(repeat=4)

    prompts = [
        m20.trajectory_examples(
            spec,
            mode=m20.ACTION_MODE,
            program_visible=True,
            start_index=index,
        )[0]
        for index, spec in enumerate(specs)
    ]

    states = {tuple(row["metadata"]["state"].items()) for row in prompts}
    actions = {row["metadata"]["oracle_action"] for row in prompts}
    assert len(states) == 1
    assert len(actions) > 1


def test_register_permutation_holds_out_declared_pairs() -> None:
    m20 = _load_module()
    train_keys = {program.key for program in m20.training_programs()}
    heldout_keys = {program.key for program in m20.heldout_register_programs()}

    assert train_keys.isdisjoint(heldout_keys)
    assert heldout_keys == {"drain_R0_R3", "drain_R3_R0"}


def test_heldout_program_split_correctness() -> None:
    m20 = _load_module()
    train_keys = {spec.program.key for spec in m20.build_episode_splits()["train"]}
    heldout_keys = {
        spec.program.key
        for spec in m20.build_episode_splits()["heldout_program_instances"]
    }

    assert train_keys.isdisjoint(heldout_keys)


def test_no_program_or_case_ids_in_prompt() -> None:
    m20 = _load_module()
    datasets = m20.build_datasets()
    prompts = [
        str(example["prompt"])
        for mode in datasets.values()
        for section in mode.values()
        for examples in section.values()
        for example in examples
    ]

    assert prompts
    assert not any(m20.prompt_has_forbidden_marker(prompt) for prompt in prompts)


def test_closed_loop_final_state_verification_with_oracle() -> None:
    m20 = _load_module()
    program = m20.merge_two_program("R0", "R1", "R2")

    result = m20.apply_oracle(program, m20.state(R0=3, R1=5))

    assert result["final_state"] == m20.state(R0=0, R1=0, R2=8)


def test_m192c_action_metric_parser_regression() -> None:
    m20 = _load_module()

    assert m20.parse_action_text("FINAL TAKE") == "TAKE"
    assert m20.parse_action_text("<|answer|>\nFINAL STOP\n<|end|>") == "STOP"
    assert m20.parse_action_text("FINAL MOVE_ONE R0 R1") == "MOVE_ONE R0 R1"
    assert m20.parse_action_text("FINAL APPLY_RULE_2") == "APPLY_RULE_2"
    assert m20.parse_action_text("FINAL C2") == "APPLY_RULE_2"
    assert m20.parse_action_text("FINAL M R0 R1") == "M R0 R1"
    assert m20.parse_action_text("FINAL D R3") == "D R3"
    assert m20.parse_action_text("FINAL H") == "H"
