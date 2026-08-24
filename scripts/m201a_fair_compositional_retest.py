from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import random
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch import nn

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import (
    ANSWER_TOKEN,
    BOS_TOKEN,
    EOS_TOKEN,
    PROMPT_TOKEN,
)
from ai_brain.model.config import get_named_model_config
from ai_brain.model.factory import build_model
from ai_brain.runtime.device import get_device_info
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m201a_fair_compositional_retest"
RUNS_DIR = ROOT / "runs" / "m201a_fair_compositional_retest"
DOC_REPORT_PATH = ROOT / "docs" / "m201a_fair_compositional_retest_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m201a_fair_compositional_retest_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 2031
MODEL_CONFIG = "arithmetic_3m"
POSITION_ENCODING = "relative"
NUMERIC_TOKENIZATION = "digit_safe"
SEQUENCE_LENGTH = 256
BATCH_SIZE = 8
EVAL_BATCHES = 20
GRAD_CLIP_NORM = 1.0

TRAIN_COUNTS = tuple(range(8))
OOD_COUNTS = tuple(range(11, 21))
LONG_COUNTS = tuple(range(21, 51))
ALL_VARS = ("A", "B", "C", "D", "X", "Y", "Z", "W")
PRIMARY_VARS = ("A", "B", "C", "D")
VARSETS = (
    ("A", "B", "C", "D"),
    ("X", "Y", "Z", "W"),
    ("A", "X", "B", "Y"),
    ("C", "Z", "D", "W"),
)

RUN_SPECS = {
    "binding_lm": {
        "train": "binding_point",
        "eval": "binding_eval_mixed",
        "steps": 3000,
        "init": None,
    },
    "single_clause_base_lm": {
        "train": "single_clause_replay",
        "eval": "single_clause_eval_mixed",
        "steps": 5000,
        "init": None,
    },
    "flat_balanced_lm": {
        "train": "flat_balanced",
        "eval": "program_eval_mixed",
        "steps": 7000,
        "init": None,
    },
    "curriculum_no_replay_lm": {
        "train": "program_only",
        "eval": "program_eval_mixed",
        "steps": 5000,
        "init": "single_clause_base_lm",
    },
    "curriculum_replay25_lm": {
        "train": "program_replay25",
        "eval": "program_eval_mixed",
        "steps": 5000,
        "init": "single_clause_base_lm",
    },
    "curriculum_replay50_lm": {
        "train": "program_replay50",
        "eval": "program_eval_mixed",
        "steps": 5000,
        "init": "single_clause_base_lm",
    },
}


def load_m201():
    module_name = "m201_compositional_dsl_variable_binding"
    module_path = ROOT / "scripts" / "m201_compositional_dsl_variable_binding.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


m201 = load_m201()


@dataclass(frozen=True)
class PolicyExample:
    prompt: str
    action: str
    split: str
    metadata: dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare-datasets")
    sub.add_parser("run-lm")
    sub.add_parser("run-policy")
    sub.add_parser("analyze")
    report_parser = sub.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    sub.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-lm":
        run_lm_variants()
    elif args.command == "run-policy":
        run_policy_head()
    elif args.command == "analyze":
        analyze()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_lm_variants()
        run_policy_head()
        analyze()
        build_report(checks_passed=False)


def prepare_datasets() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / "train").mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / "eval").mkdir(parents=True, exist_ok=True)

    train_bindings, heldout_bindings = all_split_bindings()
    train_rows = build_train_rows(train_bindings)
    eval_rows = build_eval_rows(train_bindings, heldout_bindings)

    for name, rows in train_rows.items():
        write_jsonl(DATASET_DIR / "train" / f"{name}.jsonl", rows)
    for name, rows in eval_rows.items():
        write_jsonl(DATASET_DIR / "eval" / f"{name}.jsonl", rows)

    policy_train = policy_examples_from_rows(train_rows["program_replay25"])
    policy_eval = {
        name: policy_examples_from_rows(rows)
        for name, rows in eval_rows.items()
        if name.startswith(("program_", "heldout_", "merge_two_", "teacher_forced"))
    }
    write_policy_jsonl(DATASET_DIR / "train" / "policy_head.jsonl", policy_train)
    for name, rows in policy_eval.items():
        write_policy_jsonl(DATASET_DIR / "eval" / f"policy_{name}.jsonl", rows)

    manifest = build_manifest(train_rows, eval_rows, train_bindings, heldout_bindings)
    write_json(DATASET_DIR / "manifest.json", manifest)


def build_train_rows(bindings: Sequence[Any]) -> dict[str, list[dict[str, Any]]]:
    primary_bindings = [
        binding for binding in bindings if tuple(binding.mapping) == PRIMARY_VARS
    ]
    binding_point = binding_records(bindings, include_full_table=False, split="train")
    primitives = (
        binding_point
        + predicate_records(bindings, split="train")
        + action_records(bindings, split="train")
    )
    single_seen = single_clause_records(
        train_clause_specs(), bindings, split="train", ladder="seen_clause_seen_binding"
    )
    alpha_train = alpha_records(train_alpha_pairs(), bindings, split="train")
    program_only = program_records(
        program_specs(m201.grammar_train_programs(), primary_bindings, TRAIN_COUNTS),
        split_name="program_train",
    )
    clause_selection = clause_selection_records(
        program_specs(
            m201.grammar_train_programs()[:6], primary_bindings[:8], TRAIN_COUNTS
        ),
        split_name="clause_selection_train",
    )

    primitive_replay = balance_rows(primitives + single_seen + alpha_train, 16000)
    program_balanced = balance_rows(program_only + clause_selection, 16000)

    return {
        "binding_point": balance_rows(binding_point, 5000),
        "single_clause_replay": primitive_replay,
        "program_only": program_balanced,
        "program_replay25": mix_rows(program_balanced, primitive_replay, 0.25, 18000),
        "program_replay50": mix_rows(program_balanced, primitive_replay, 0.50, 18000),
        "flat_balanced": mix_rows(program_balanced, primitive_replay, 0.50, 20000),
    }


def build_eval_rows(
    train_bindings: Sequence[Any], heldout_bindings: Sequence[Any]
) -> dict[str, list[dict[str, Any]]]:
    seen_bindings = list(train_bindings[:8])
    held_bindings = list(heldout_bindings)
    seen_primary = [
        binding for binding in train_bindings if tuple(binding.mapping) == PRIMARY_VARS
    ][:8]
    held_primary = [
        binding
        for binding in heldout_bindings
        if tuple(binding.mapping) == PRIMARY_VARS
    ]
    merge_two = m201.merge_two_program(PRIMARY_VARS)

    rows: dict[str, list[dict[str, Any]]] = {
        "binding_l2p_seen": [
            row
            for row in binding_records(
                seen_bindings, include_full_table=True, split="eval"
            )
            if row["metadata"]["binding_metric"] == "l2p"
        ],
        "binding_l2p_heldout": [
            row
            for row in binding_records(
                held_bindings, include_full_table=True, split="eval"
            )
            if row["metadata"]["binding_metric"] == "l2p"
        ],
        "binding_p2l_seen": [
            row
            for row in binding_records(
                seen_bindings, include_full_table=True, split="eval"
            )
            if row["metadata"]["binding_metric"] == "p2l"
        ],
        "binding_p2l_heldout": [
            row
            for row in binding_records(
                held_bindings, include_full_table=True, split="eval"
            )
            if row["metadata"]["binding_metric"] == "p2l"
        ],
        "binding_full_table_seen": [
            row
            for row in binding_records(
                seen_bindings, include_full_table=True, split="eval"
            )
            if row["metadata"]["binding_metric"] == "full_table"
        ],
        "binding_full_table_heldout": [
            row
            for row in binding_records(
                held_bindings, include_full_table=True, split="eval"
            )
            if row["metadata"]["binding_metric"] == "full_table"
        ],
        "predicate_seen": predicate_records(seen_bindings, split="eval"),
        "predicate_heldout": predicate_records(held_bindings, split="eval"),
        "action_seen": action_records(seen_bindings, split="eval"),
        "action_heldout": action_records(held_bindings, split="eval"),
        "single_clause_seen_seen_binding": single_clause_records(
            train_clause_specs(),
            seen_bindings,
            split="eval",
            ladder="same_clause_seen_binding",
        ),
        "single_clause_new_seen_binding": single_clause_records(
            heldout_clause_specs(),
            seen_bindings,
            split="eval",
            ladder="new_clause_seen_binding",
        ),
        "single_clause_seen_heldout_binding": single_clause_records(
            train_clause_specs(),
            held_bindings,
            split="eval",
            ladder="same_clause_heldout_binding",
        ),
        "single_clause_new_heldout_binding": single_clause_records(
            heldout_clause_specs(),
            held_bindings,
            split="eval",
            ladder="new_clause_heldout_binding",
        ),
        "alpha_known": alpha_records(eval_alpha_pairs(), seen_bindings, split="eval"),
        "teacher_forced_clause_seen": selected_clause_records(
            program_specs(
                m201.grammar_train_programs()[:6], seen_primary, TRAIN_COUNTS
            ),
            split_name="teacher_forced_seen",
        ),
        "teacher_forced_clause_heldout_binding": selected_clause_records(
            program_specs(
                m201.grammar_train_programs()[:6], held_primary, TRAIN_COUNTS
            ),
            split_name="teacher_forced_heldout_binding",
        ),
        "teacher_forced_clause_merge_two": selected_clause_records(
            merge_two_specs(merge_two, seen_primary, TRAIN_COUNTS),
            split_name="teacher_forced_merge_two",
        ),
        "clause_selection_seen": clause_selection_records(
            program_specs(
                m201.grammar_train_programs()[:6], seen_primary, TRAIN_COUNTS
            ),
            split_name="clause_selection_seen",
        ),
        "heldout_binding": program_records(
            program_specs(
                m201.grammar_train_programs()[:6], held_primary, TRAIN_COUNTS
            ),
            split_name="heldout_binding",
        ),
        "heldout_program": program_records(
            program_specs(m201.grammar_heldout_programs(), seen_primary, TRAIN_COUNTS),
            split_name="heldout_program",
        ),
        "heldout_predicate_composition": program_records(
            program_specs(
                [m201.heldout_predicate_composition_program()],
                seen_primary,
                TRAIN_COUNTS,
            ),
            split_name="heldout_predicate_composition",
        ),
        "program_seen": program_records(
            program_specs(
                m201.grammar_train_programs()[:6], seen_primary, TRAIN_COUNTS
            ),
            split_name="program_seen",
        ),
        "merge_two_seen": merge_two_records(
            merge_two, seen_primary, TRAIN_COUNTS, split_name="merge_two_seen"
        ),
        "merge_two_11_20": merge_two_records(
            merge_two, seen_primary[:4], OOD_COUNTS, split_name="merge_two_11_20"
        ),
        "merge_two_21_50": merge_two_records(
            merge_two, seen_primary[:2], LONG_COUNTS[::3], split_name="merge_two_21_50"
        ),
    }
    rows["binding_eval_mixed"] = balance_rows(
        rows["binding_l2p_seen"]
        + rows["binding_l2p_heldout"]
        + rows["binding_p2l_seen"]
        + rows["binding_p2l_heldout"],
        1024,
    )
    rows["single_clause_eval_mixed"] = balance_rows(
        rows["single_clause_seen_seen_binding"]
        + rows["single_clause_new_seen_binding"]
        + rows["single_clause_seen_heldout_binding"]
        + rows["single_clause_new_heldout_binding"]
        + rows["alpha_known"],
        2048,
    )
    rows["program_eval_mixed"] = balance_rows(
        rows["program_seen"] + rows["heldout_binding"] + rows["merge_two_seen"], 2048
    )
    return rows


def all_split_bindings() -> tuple[list[Any], list[Any]]:
    train: list[Any] = []
    heldout: list[Any] = []
    for variables in VARSETS:
        bindings = [
            m201.Binding(dict(zip(variables, registers, strict=True)))
            for registers in itertools.permutations(m201.REGISTERS)
        ]
        first, third = variables[0], variables[2]
        local_heldout = [
            binding
            for binding in bindings
            if (binding.mapping[first] == "R0" and binding.mapping[third] == "R3")
            or (binding.mapping[first] == "R3" and binding.mapping[third] == "R0")
        ]
        heldout.extend(local_heldout)
        train.extend([binding for binding in bindings if binding not in local_heldout])
    return train, heldout


def binding_records(
    bindings: Sequence[Any], *, include_full_table: bool, split: str
) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        variables = tuple(binding.mapping)
        for variable, register in sorted(binding.mapping.items()):
            rows.append(
                make_record(
                    "m201a.binding.l2p",
                    f"{m201.render_binding(binding)}\nQ L2P {variable}",
                    f"FINAL {register}",
                    {
                        "split": split,
                        "binding_metric": "l2p",
                        "variable": variable,
                        "register": register,
                        "binding_hash": binding_hash(binding),
                        "variables": variables,
                    },
                )
            )
        for register in m201.REGISTERS:
            variable = binding.logical(register)
            rows.append(
                make_record(
                    "m201a.binding.p2l",
                    f"{m201.render_binding(binding)}\nQ P2L {register}",
                    f"FINAL {variable}",
                    {
                        "split": split,
                        "binding_metric": "p2l",
                        "variable": variable,
                        "register": register,
                        "binding_hash": binding_hash(binding),
                        "variables": variables,
                    },
                )
            )
        if include_full_table:
            rows.append(
                make_record(
                    "m201a.binding.full_table",
                    f"{m201.render_binding(binding)}\nQ TABLE",
                    f"FINAL {m201.render_binding_table(binding)}",
                    {
                        "split": split,
                        "binding_metric": "full_table",
                        "binding_hash": binding_hash(binding),
                        "variables": variables,
                    },
                )
            )
    return rows


def predicate_records(bindings: Sequence[Any], *, split: str) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        for variable in binding.mapping:
            for kind in ("EMPTY", "NONEMPTY"):
                for truth in (False, True):
                    state = m201.zero_state()
                    state[binding.physical(variable)] = 2 if truth else 0
                    predicate = m201.Predicate(variable, kind)
                    expected = predicate.matches(state, binding)
                    rows.append(
                        make_record(
                            "m201a.predicate",
                            f"{m201.render_binding(binding)}\n{m201.render_state(state)}\nTEST {m201.pred_token(kind)} {variable}",
                            f"FINAL {'TRUE' if expected else 'FALSE'}",
                            {
                                "split": split,
                                "predicate_kind": kind,
                                "variable": variable,
                                "binding_hash": binding_hash(binding),
                            },
                        )
                    )
    return rows


def action_records(bindings: Sequence[Any], *, split: str) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        variables = tuple(binding.mapping)
        for source in variables:
            for destination in variables:
                if source == destination:
                    continue
                action = m201.Action("MOVE_ONE", source, destination)
                rows.append(
                    make_record(
                        "m201a.action.resolve",
                        f"ACT M {source} {destination}\n{m201.render_binding(binding)}",
                        f"FINAL {action.resolve(binding).render()}",
                        {
                            "split": split,
                            "action_kind": "MOVE_ONE",
                            "binding_hash": binding_hash(binding),
                        },
                    )
                )
            action = m201.Action("DROP_ONE", source)
            rows.append(
                make_record(
                    "m201a.action.resolve",
                    f"ACT D {source}\n{m201.render_binding(binding)}",
                    f"FINAL {action.resolve(binding).render()}",
                    {
                        "split": split,
                        "action_kind": "DROP_ONE",
                        "binding_hash": binding_hash(binding),
                    },
                )
            )
        rows.append(
            make_record(
                "m201a.action.resolve",
                f"ACT H\n{m201.render_binding(binding)}",
                "FINAL H",
                {
                    "split": split,
                    "action_kind": "HALT",
                    "binding_hash": binding_hash(binding),
                },
            )
        )
    return rows


@dataclass(frozen=True)
class ClauseSpec:
    name: str
    predicate_kind: str
    action_kind: str
    source_role: str
    destination_role: str | None = None


def train_clause_specs() -> tuple[ClauseSpec, ...]:
    return (
        ClauseSpec(
            "ne_move_self_to_other", "NONEMPTY", "MOVE_ONE", "predicate", "other"
        ),
        ClauseSpec("ne_drop_self", "NONEMPTY", "DROP_ONE", "predicate"),
        ClauseSpec("empty_halt", "EMPTY", "HALT", "predicate"),
    )


def heldout_clause_specs() -> tuple[ClauseSpec, ...]:
    return (
        ClauseSpec("empty_move_other_to_third", "EMPTY", "MOVE_ONE", "other", "third"),
        ClauseSpec(
            "nonempty_move_other_to_predicate",
            "NONEMPTY",
            "MOVE_ONE",
            "other",
            "predicate",
        ),
        ClauseSpec("empty_drop_other", "EMPTY", "DROP_ONE", "other"),
    )


def single_clause_records(
    specs: Sequence[ClauseSpec],
    bindings: Sequence[Any],
    *,
    split: str,
    ladder: str,
) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        variables = tuple(binding.mapping)
        if len(variables) < 3:
            continue
        for predicate_var, other_var, third_var in rotating_var_triples(variables):
            for spec in specs:
                clause = clause_from_spec(spec, predicate_var, other_var, third_var)
                state = state_for_single_clause(clause, binding)
                program = m201.Program("single_clause", (clause,), "single_clause")
                expected = clause.action.resolve(binding).render()
                rows.append(
                    make_record(
                        "m201a.single_clause",
                        f"{m201.render_program(program, binding, state)}\n{m201.render_binding(binding)}\n{m201.render_state(state)}",
                        f"FINAL {expected}",
                        {
                            "split": split,
                            "ladder": ladder,
                            "clause_spec": spec.name,
                            "binding_hash": binding_hash(binding),
                            "expected_action": expected,
                        },
                    )
                )
    return rows


def rotating_var_triples(variables: Sequence[str]) -> list[tuple[str, str, str]]:
    triples = []
    for index, variable in enumerate(variables):
        triples.append(
            (
                variable,
                variables[(index + 1) % len(variables)],
                variables[(index + 2) % len(variables)],
            )
        )
    return triples


def clause_from_spec(
    spec: ClauseSpec, predicate_var: str, other_var: str, third_var: str
) -> Any:
    source = {"predicate": predicate_var, "other": other_var, "third": third_var}[
        spec.source_role
    ]
    destination = (
        {"predicate": predicate_var, "other": other_var, "third": third_var}[
            spec.destination_role
        ]
        if spec.destination_role is not None
        else None
    )
    if spec.action_kind == "MOVE_ONE":
        action = m201.Action("MOVE_ONE", source, destination)
    elif spec.action_kind == "DROP_ONE":
        action = m201.Action("DROP_ONE", source)
    else:
        action = m201.Action("HALT")
    return m201.Clause((m201.Predicate(predicate_var, spec.predicate_kind),), action)


def state_for_single_clause(clause: Any, binding: Any) -> dict[str, int]:
    state = m201.zero_state()
    predicate = clause.predicates[0]
    state[binding.physical(predicate.variable)] = 0 if predicate.kind == "EMPTY" else 2
    if clause.action.source is not None:
        source_register = binding.physical(clause.action.source)
        if source_register != binding.physical(predicate.variable):
            state[source_register] = 2
    return state


def train_alpha_pairs() -> tuple[tuple[str, str], ...]:
    return (("A", "C"), ("X", "W"), ("B", "D"), ("Y", "Z"), ("A", "X"), ("C", "W"))


def eval_alpha_pairs() -> tuple[tuple[str, str], ...]:
    return (("X", "C"), ("D", "W"), ("B", "Z"), ("Y", "A"))


def alpha_records(
    pairs: Sequence[tuple[str, str]], bindings: Sequence[Any], *, split: str
) -> list[dict[str, Any]]:
    rows = []
    for src, dst in pairs:
        for base_binding in bindings[:12]:
            binding = binding_for_vars((src, dst), base_binding)
            program = m201.drain_program(src, dst)
            for count in (0, 1, 3):
                state = m201.zero_state()
                state[binding.physical(src)] = count
                action = program.oracle_action(state, binding).render()
                rows.append(
                    make_record(
                        "m201a.alpha_known",
                        f"{m201.render_program(program, binding, state)}\n{m201.render_binding(binding)}\n{m201.render_state(state)}",
                        f"FINAL {action}",
                        {
                            "split": split,
                            "alpha_pair": [src, dst],
                            "binding_hash": binding_hash(binding),
                            "normalized_ast_hash": m201.normalized_ast_hash(program),
                            "expected_action": action,
                        },
                    )
                )
    return rows


def binding_for_vars(required: Sequence[str], base_binding: Any) -> Any:
    variables = list(dict.fromkeys(required))
    for variable in ALL_VARS:
        if variable not in variables and len(variables) < 4:
            variables.append(variable)
    registers = list(base_binding.mapping.values())
    return m201.Binding(dict(zip(variables, registers, strict=True)))


def program_specs(
    programs: Sequence[Any], bindings: Sequence[Any], counts: Sequence[int]
) -> list[Any]:
    return [
        m201.EpisodeSpec(
            program,
            binding,
            m201.initial_state_for_program(program, binding, count),
            "eval",
            program.family,
        )
        for program, binding, count in itertools.product(programs, bindings, counts)
    ]


def merge_two_specs(
    program: Any, bindings: Sequence[Any], counts: Sequence[int]
) -> list[Any]:
    return [
        m201.EpisodeSpec(
            program,
            binding,
            m201.merge_state(program, binding, left, right),
            "eval",
            "merge_two",
        )
        for binding in bindings
        for left in counts
        for right in counts[: min(6, len(counts))]
    ]


def program_records(specs: Sequence[Any], *, split_name: str) -> list[dict[str, Any]]:
    rows = []
    for spec in specs:
        rows.extend(records_for_episode(spec, split_name=split_name))
    return rows


def merge_two_records(
    program: Any, bindings: Sequence[Any], counts: Sequence[int], *, split_name: str
) -> list[dict[str, Any]]:
    rows = []
    for spec in merge_two_specs(program, bindings, counts):
        rows.extend(records_for_episode(spec, split_name=split_name, phase_labels=True))
    return rows


def records_for_episode(
    spec: Any, *, split_name: str, phase_labels: bool = False
) -> list[dict[str, Any]]:
    rows = []
    env = m201.RegisterEnvironment(dict(spec.initial_state))
    b_started = False
    for step in range(m201.max_steps(spec.initial_state)):
        clause_index = spec.program.applicable_clause_index(env.state, spec.binding)
        action = spec.program.clauses[clause_index].action.resolve(spec.binding)
        phase = (
            merge_two_phase(spec.program, spec.binding, env.state, b_started)
            if phase_labels
            else None
        )
        if phase in {"A_TO_B_SWITCH", "PHASE_B_MOVE"}:
            b_started = True
        rows.append(
            make_record(
                f"m201a.program.{spec.program.family}",
                m201.render_prompt_for_spec(spec, env),
                f"FINAL {action.render()}",
                {
                    "split": split_name,
                    "program_family": spec.program.family,
                    "program_name": spec.program.name,
                    "binding_hash": binding_hash(spec.binding),
                    "normalized_ast_hash": m201.normalized_ast_hash(spec.program),
                    "template_hash": m201.template_hash(spec.program),
                    "clause_hashes": m201.clause_hashes(spec.program),
                    "predicate_action_tuples": m201.predicate_action_tuples(
                        spec.program
                    ),
                    "state": dict(env.state),
                    "initial_state": dict(spec.initial_state),
                    "step": step,
                    "expected_clause_index": clause_index,
                    "expected_clause_text": render_selected_clause(
                        spec.program.clauses[clause_index]
                    ),
                    "expected_action": action.render(),
                    "phase": phase,
                },
            )
        )
        env.step(action)
        if env.terminated:
            break
    return rows


def selected_clause_records(
    specs: Sequence[Any], *, split_name: str
) -> list[dict[str, Any]]:
    rows = []
    for spec in specs:
        env = m201.RegisterEnvironment(dict(spec.initial_state))
        for step in range(m201.max_steps(spec.initial_state)):
            clause_index = spec.program.applicable_clause_index(env.state, spec.binding)
            clause = spec.program.clauses[clause_index]
            action = clause.action.resolve(spec.binding).render()
            prompt = (
                f"SEL\n{render_selected_clause(clause)}\n"
                f"{m201.render_binding(spec.binding)}\n{m201.render_state(env.state)}"
            )
            rows.append(
                make_record(
                    "m201a.teacher_forced.selected_clause",
                    prompt,
                    f"FINAL {action}",
                    {
                        "split": split_name,
                        "program_family": spec.program.family,
                        "binding_hash": binding_hash(spec.binding),
                        "expected_clause_index": clause_index,
                        "expected_clause_text": render_selected_clause(clause),
                        "expected_action": action,
                        "step": step,
                    },
                )
            )
            env.step(clause.action.resolve(spec.binding))
            if env.terminated:
                break
    return rows


def clause_selection_records(
    specs: Sequence[Any], *, split_name: str
) -> list[dict[str, Any]]:
    rows = []
    for spec in specs:
        env = m201.RegisterEnvironment(dict(spec.initial_state))
        for step in range(m201.max_steps(spec.initial_state)):
            clause_index = spec.program.applicable_clause_index(env.state, spec.binding)
            prompt = m201.render_prompt_for_spec(spec, env)
            rows.append(
                make_record(
                    "m201a.clause_selection",
                    f"{prompt}\nQ CLAUSE",
                    f"FINAL C{clause_index}",
                    {
                        "split": split_name,
                        "program_family": spec.program.family,
                        "binding_hash": binding_hash(spec.binding),
                        "expected_clause_index": clause_index,
                        "expected_action": spec.program.clauses[clause_index]
                        .action.resolve(spec.binding)
                        .render(),
                        "step": step,
                    },
                )
            )
            env.step(spec.program.clauses[clause_index].action.resolve(spec.binding))
            if env.terminated:
                break
    return rows


def render_selected_clause(clause: Any) -> str:
    return m201.render_structured_clause(0, clause)


def merge_two_phase(
    program: Any, binding: Any, state: dict[str, int], b_started: bool
) -> str:
    del program
    left = state[binding.physical("A")]
    right = state[binding.physical("B")]
    if left > 0:
        return "PHASE_A_MOVE"
    if right > 0 and not b_started:
        return "A_TO_B_SWITCH"
    if right > 0:
        return "PHASE_B_MOVE"
    return "FINAL_HALT"


def run_lm_variants() -> None:
    for run_name, spec in RUN_SPECS.items():
        run_dir = RUNS_DIR / run_name
        checkpoint = final_checkpoint(run_dir)
        if checkpoint is None:
            init_checkpoint = None
            if spec["init"]:
                init_checkpoint = final_checkpoint(RUNS_DIR / str(spec["init"]))
                if init_checkpoint is None:
                    raise RuntimeError(f"Missing init checkpoint for {run_name}")
            train_lm(
                TrainConfig(
                    train_path=DATASET_DIR / "train" / f"{spec['train']}.jsonl",
                    eval_path=DATASET_DIR / "eval" / f"{spec['eval']}.jsonl",
                    tokenizer_path=TOKENIZER_PATH,
                    output_dir=run_dir,
                    model_config_name=MODEL_CONFIG,
                    steps=int(spec["steps"]),
                    batch_size=BATCH_SIZE,
                    sequence_length=SEQUENCE_LENGTH,
                    loss_mode="answer-only",
                    numeric_tokenization=NUMERIC_TOKENIZATION,
                    position_encoding=POSITION_ENCODING,
                    eval_every=max(int(spec["steps"]) // 4, 1),
                    save_every=max(int(spec["steps"]) // 2, 1),
                    eval_batches=EVAL_BATCHES,
                    grad_clip_norm=GRAD_CLIP_NORM,
                    seed=SEED,
                    init_checkpoint_path=init_checkpoint,
                )
            )
            prune_intermediate_checkpoints(run_dir)
            checkpoint = final_checkpoint(run_dir)
        if checkpoint is None:
            raise RuntimeError(f"No checkpoint for {run_name}")
        eval_lm_run(run_name, checkpoint)


def eval_lm_run(run_name: str, checkpoint: Path) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _checkpoint_payload = m201.load_model_for_inference(
        checkpoint_path=checkpoint, tokenizer_path=TOKENIZER_PATH, device=device
    )
    eval_root = RUNS_DIR / run_name / "eval"
    eval_root.mkdir(parents=True, exist_ok=True)
    for path in sorted((DATASET_DIR / "eval").glob("*.jsonl")):
        if path.name.startswith("policy_"):
            continue
        split = path.stem
        out_dir = eval_root / split
        summary_path = out_dir / "summary.json"
        if summary_path.exists():
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
        predictions = []
        cache: dict[tuple[str, tuple[str, ...]], str] = {}
        for row in rows:
            expected = parse_target(row["answer"])
            candidates = candidates_for_expected(expected, row)
            cache_key = (row["prompt"], tuple(candidates))
            if cache_key not in cache:
                cache[cache_key] = m201.choose_answer(
                    model=model,
                    tokenizer=tokenizer,
                    prompt=row["prompt"],
                    candidates=candidates,
                    device=device,
                )
            prediction = parse_target(f"FINAL {cache[cache_key]}")
            correct = prediction == expected
            predictions.append(
                {
                    "id": row["id"],
                    "expected": expected,
                    "prediction": prediction,
                    "correct": correct,
                    "metadata": row.get("metadata", {}),
                }
            )
        write_jsonl(out_dir / "predictions.jsonl", predictions)
        write_json(out_dir / "summary.json", summarize_predictions(predictions))
    if run_name not in {"binding_lm", "single_clause_base_lm"}:
        eval_lm_closed_loop(run_name, checkpoint)


def eval_lm_closed_loop(run_name: str, checkpoint: Path) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _checkpoint_payload = m201.load_model_for_inference(
        checkpoint_path=checkpoint, tokenizer_path=TOKENIZER_PATH, device=device
    )
    specs_by_split = closed_loop_specs()
    for split, specs in specs_by_split.items():
        out_dir = RUNS_DIR / run_name / "closed_loop" / split
        if (out_dir / "summary.json").exists():
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = closed_loop_rows(
            specs,
            predict=lambda prompt: m201.choose_answer(
                model=model,
                tokenizer=tokenizer,
                prompt=prompt,
                candidates=action_vocab(),
                device=device,
            ),
        )
        write_jsonl(out_dir / "episodes.jsonl", rows)
        write_json(out_dir / "summary.json", summarize_episodes(rows))


class PolicyHeadModel(nn.Module):
    def __init__(self, vocab_size: int, action_count: int) -> None:
        super().__init__()
        config = get_named_model_config(MODEL_CONFIG)
        config = type(config)(
            **{
                **config.__dict__,
                "vocab_size": vocab_size,
                "max_sequence_length": SEQUENCE_LENGTH,
                "position_encoding": POSITION_ENCODING,
            }
        )
        self.backbone = build_model(config)
        self.head = nn.Linear(config.d_model, action_count)

    def forward(self, input_ids: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        embeddings = self.backbone.embed_tokens_and_positions(input_ids)
        _lm_logits, hidden = self.backbone.forward_embeddings(
            embeddings, return_hidden=True
        )
        gather_index = (lengths - 1).view(-1, 1, 1).expand(-1, 1, hidden.shape[-1])
        pooled = hidden.gather(1, gather_index).squeeze(1)
        return self.head(pooled)


def run_policy_head() -> None:
    out_dir = RUNS_DIR / "policy_head"
    checkpoint_path = out_dir / "policy_head.pt"
    out_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    device_info = get_device_info(prefer_cuda=True)
    device = device_info.device
    train_rows = read_policy_jsonl(DATASET_DIR / "train" / "policy_head.jsonl")
    if not checkpoint_path.exists():
        torch.manual_seed(SEED)
        model = PolicyHeadModel(tokenizer.vocab_size, len(action_vocab())).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
        generator = random.Random(SEED)
        metrics = []
        for step in range(1, 5001):
            batch = [generator.choice(train_rows) for _ in range(BATCH_SIZE)]
            input_ids, lengths, labels = encode_policy_batch(
                tokenizer, batch, device=device
            )
            logits = model(input_ids, lengths)
            loss = F.cross_entropy(logits, labels)
            if not torch.isfinite(loss):
                raise ValueError(f"Non-finite policy loss at step {step}")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(
                model.parameters(), GRAD_CLIP_NORM
            )
            optimizer.step()
            if step % 1000 == 0:
                metrics.append(
                    {
                        "step": step,
                        "train_loss": float(loss.detach().cpu().item()),
                        "grad_norm": float(grad_norm.detach().cpu().item()),
                    }
                )
                write_jsonl(out_dir / "metrics.jsonl", metrics)
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "action_vocab": action_vocab(),
                "model_config_name": MODEL_CONFIG,
                "sequence_length": SEQUENCE_LENGTH,
                "seed": SEED,
            },
            checkpoint_path,
        )
    model = PolicyHeadModel(tokenizer.vocab_size, len(action_vocab())).to(device)
    payload = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    eval_policy_model(model, tokenizer, device)


def eval_policy_model(
    model: PolicyHeadModel, tokenizer: ByteLevelBpeTokenizer, device: torch.device
) -> None:
    eval_root = RUNS_DIR / "policy_head" / "eval"
    eval_root.mkdir(parents=True, exist_ok=True)
    for path in sorted((DATASET_DIR / "eval").glob("policy_*.jsonl")):
        split = path.stem.removeprefix("policy_")
        out_dir = eval_root / split
        if (out_dir / "summary.json").exists():
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = read_policy_jsonl(path)
        predictions = []
        for row in rows:
            predicted = predict_policy_action(model, tokenizer, row["prompt"], device)
            correct = predicted == row["action"]
            predictions.append(
                {
                    "expected": row["action"],
                    "prediction": predicted,
                    "correct": correct,
                    "metadata": row["metadata"],
                }
            )
        write_jsonl(out_dir / "predictions.jsonl", predictions)
        write_json(out_dir / "summary.json", summarize_predictions(predictions))

    for split, specs in closed_loop_specs().items():
        out_dir = RUNS_DIR / "policy_head" / "closed_loop" / split
        if (out_dir / "summary.json").exists():
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = closed_loop_rows(
            specs,
            predict=lambda prompt: predict_policy_action(
                model, tokenizer, prompt, device
            ),
        )
        write_jsonl(out_dir / "episodes.jsonl", rows)
        write_json(out_dir / "summary.json", summarize_episodes(rows))


@torch.no_grad()
def predict_policy_action(
    model: PolicyHeadModel,
    tokenizer: ByteLevelBpeTokenizer,
    prompt: str,
    device: torch.device,
) -> str:
    row = {"prompt": prompt, "action": "H", "metadata": {}}
    input_ids, lengths, _labels = encode_policy_batch(tokenizer, [row], device=device)
    logits = model(input_ids, lengths)
    return action_vocab()[int(torch.argmax(logits[0]).detach().cpu().item())]


def encode_policy_batch(
    tokenizer: ByteLevelBpeTokenizer,
    rows: Sequence[dict[str, Any]],
    *,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    bos_id = tokenizer.token_to_id(BOS_TOKEN)
    eos_id = tokenizer.token_to_id(EOS_TOKEN)
    if bos_id is None or eos_id is None:
        raise ValueError("Tokenizer missing BOS/EOS")
    encoded = []
    lengths = []
    for row in rows:
        ids = [
            bos_id,
            *tokenizer.encode(
                f"{PROMPT_TOKEN}\n{row['prompt'].strip()}\n{ANSWER_TOKEN}\n",
                numeric_tokenization=NUMERIC_TOKENIZATION,
            ),
        ]
        if len(ids) > SEQUENCE_LENGTH:
            raise ValueError(f"Policy prompt too long: {len(ids)}")
        encoded.append(ids)
        lengths.append(len(ids))
    max_len = max(lengths)
    padded = [ids + [eos_id] * (max_len - len(ids)) for ids in encoded]
    labels = [action_to_id(row["action"]) for row in rows]
    return (
        torch.tensor(padded, dtype=torch.long, device=device),
        torch.tensor(lengths, dtype=torch.long, device=device),
        torch.tensor(labels, dtype=torch.long, device=device),
    )


def closed_loop_specs() -> dict[str, list[Any]]:
    train_bindings, heldout_bindings = all_split_bindings()
    seen = [
        binding for binding in train_bindings if tuple(binding.mapping) == PRIMARY_VARS
    ][:8]
    held = [
        binding
        for binding in heldout_bindings
        if tuple(binding.mapping) == PRIMARY_VARS
    ][:8]
    merge_two = m201.merge_two_program(PRIMARY_VARS)
    return {
        "program_seen": program_specs(
            m201.grammar_train_programs()[:6], seen, TRAIN_COUNTS
        ),
        "heldout_binding": program_specs(
            m201.grammar_train_programs()[:6], held, TRAIN_COUNTS
        ),
        "heldout_program": program_specs(
            m201.grammar_heldout_programs(), seen, TRAIN_COUNTS
        ),
        "merge_two_seen": merge_two_specs(merge_two, seen, TRAIN_COUNTS),
        "merge_two_11_20": merge_two_specs(merge_two, seen[:4], OOD_COUNTS),
        "merge_two_21_50": merge_two_specs(merge_two, seen[:2], LONG_COUNTS[::3]),
    }


def closed_loop_rows(specs: Sequence[Any], *, predict) -> list[dict[str, Any]]:
    rows = []
    cache: dict[str, str] = {}
    for spec in specs:
        oracle = m201.apply_oracle(spec.program, spec.binding, spec.initial_state)
        env = m201.RegisterEnvironment(dict(spec.initial_state))
        actions = []
        first_error = None
        b_started = False
        for step in range(m201.max_steps(spec.initial_state)):
            prompt = m201.render_prompt_for_spec(spec, env)
            if prompt not in cache:
                cache[prompt] = predict(prompt)
            predicted = m201.parse_action_text(f"FINAL {cache[prompt]}")
            expected_action = spec.program.oracle_action(
                env.state, spec.binding
            ).render()
            phase = (
                merge_two_phase(spec.program, spec.binding, env.state, b_started)
                if spec.program.family == "merge_two"
                else None
            )
            if phase in {"A_TO_B_SWITCH", "PHASE_B_MOVE"}:
                b_started = True
            if first_error is None and predicted != expected_action:
                first_error = {
                    "step": step,
                    "phase": phase,
                    "expected_action": expected_action,
                    "predicted_action": predicted,
                    "state": dict(env.state),
                    "binding": spec.binding.mapping,
                }
            actions.append(predicted)
            parsed = m201.parse_physical_action(predicted)
            if parsed is None:
                env.invalid = True
                break
            env.step(parsed)
            if env.invalid or env.terminated:
                break
        rows.append(
            {
                "program_family": spec.program.family,
                "initial_state": spec.initial_state,
                "oracle_final_state": oracle["final_state"],
                "final_state": env.state,
                "oracle_actions": oracle["actions"],
                "actions": actions,
                "terminated": env.terminated,
                "invalid": env.invalid,
                "final_state_exact": env.terminated
                and not env.invalid
                and env.state == oracle["final_state"],
                "trajectory_length": sum(spec.initial_state.values()),
                "first_error": first_error,
            }
        )
    return rows


def analyze() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    analysis = {
        "m201_starting_point": read_m201_starting_point(),
        "manifest": json.loads(
            (DATASET_DIR / "manifest.json").read_text(encoding="utf-8")
        ),
        "runs": {},
    }
    for run_dir in sorted(RUNS_DIR.glob("*")):
        if not run_dir.is_dir():
            continue
        run = {
            "eval": {},
            "closed_loop": {},
            "metrics": read_jsonl_if_exists(run_dir / "metrics.jsonl"),
        }
        for summary in sorted((run_dir / "eval").glob("*/summary.json")):
            run["eval"][summary.parent.name] = json.loads(
                summary.read_text(encoding="utf-8")
            )
        for summary in sorted((run_dir / "closed_loop").glob("*/summary.json")):
            run["closed_loop"][summary.parent.name] = json.loads(
                summary.read_text(encoding="utf-8")
            )
        analysis["runs"][run_dir.name] = run
    analysis["fit_gate"] = fit_gate(analysis)
    analysis["decision"] = decide(analysis)
    write_json(RUNS_DIR / "analysis.json", analysis)


def read_m201_starting_point() -> dict[str, Any]:
    report = ROOT / "runs" / "m201_compositional_dsl_variable_binding_report.md"
    return {
        "commit": git_rev_parse("HEAD~1") if report.exists() else None,
        "report_present": report.exists(),
        "report_path": str(report.relative_to(ROOT)) if report.exists() else None,
    }


def fit_gate(analysis: dict[str, Any]) -> dict[str, Any]:
    best = best_lm_run(analysis)
    binding_run = analysis["runs"].get("binding_lm", {})
    policy = analysis["runs"].get("policy_head", {})
    checks = {
        "point_binding_l2p": metric(binding_run, "binding_l2p_heldout") >= 0.99,
        "point_binding_p2l": metric(binding_run, "binding_p2l_heldout") >= 0.99,
        "predicate": metric(best, "predicate_heldout") >= 0.99,
        "action": metric(best, "action_heldout") >= 0.99,
        "single_clause_seen": metric(best, "single_clause_seen_seen_binding") >= 0.995,
        "program_seen_one_step": metric(best, "program_seen") >= 0.98,
        "program_seen_closed_loop": closed_metric(best, "program_seen") >= 0.95,
        "teacher_forced": metric(best, "teacher_forced_clause_seen") >= 0.98,
        "policy_program_seen_closed_loop": closed_metric(policy, "program_seen")
        >= 0.95,
    }
    return {
        "best_lm_run": best.get("name"),
        "checks": checks,
        "passed": all(checks.values()),
    }


def decide(analysis: dict[str, Any]) -> str:
    best = best_lm_run(analysis)
    policy = analysis["runs"].get("policy_head", {})
    if not analysis["fit_gate"]["passed"]:
        if (
            closed_metric(policy, "program_seen")
            > closed_metric(best, "program_seen") + 0.20
        ):
            return "OUTCOME C: policy head improves the interface, but fit gate is still not fully solved."
        return "OUTCOME E: fair retest still fails the seen-fit prerequisite gate; do not make OOD claims."
    if (
        metric(best, "teacher_forced_clause_merge_two") >= 0.98
        and metric(best, "merge_two_seen") < 0.90
    ):
        return "OUTCOME B: selected clauses work but full clause selection remains the bottleneck."
    if (
        closed_metric(policy, "merge_two_seen")
        > closed_metric(best, "merge_two_seen") + 0.20
    ):
        return "OUTCOME C: finite policy head beats LM action serialization."
    if closed_metric(best, "heldout_program") < 0.90:
        return (
            "OUTCOME D: clean primitives fit but heldout AST composition remains weak."
        )
    return "OUTCOME A: fair retest reaches useful compositional program execution."


def build_report(*, checks_passed: bool) -> None:
    analysis = json.loads((RUNS_DIR / "analysis.json").read_text(encoding="utf-8"))
    manifest = analysis["manifest"]
    best = best_lm_run(analysis)
    binding_run = analysis["runs"].get("binding_lm", {})
    policy = analysis["runs"].get("policy_head", {})
    lines = [
        "# M-20.1a Fair Compositional Retest",
        "",
        "## Remote Environment",
        "",
        remote_environment_section(),
        "",
        "## M-20.1 Starting Point",
        "",
        "M-20.1 reported binding aggregate `0.8889`, primitive predicate/action success, but failed single-clause, alpha-renaming, heldout program, and MERGE_TWO. M-20.1a retests the confounded axes separately.",
        "",
        f"- seed: `{SEED}`",
        f"- model: `{MODEL_CONFIG}` with `{POSITION_ENCODING}` positions",
        f"- run steps: `{json.dumps({name: spec['steps'] for name, spec in RUN_SPECS.items()}, sort_keys=True)}`",
        f"- prior M-20.1 report present: `{analysis['m201_starting_point'].get('report_present')}`",
        "",
        "## Binding Metric Decomposition",
        "",
        metric_table(
            binding_run,
            [
                "binding_l2p_seen",
                "binding_l2p_heldout",
                "binding_p2l_seen",
                "binding_p2l_heldout",
                "binding_full_table_seen",
                "binding_full_table_heldout",
            ],
        ),
        "",
        binding_interpretation(binding_run),
        "",
        "## Fair Alpha-Renaming",
        "",
        metric_table(best, ["alpha_known"]),
        "",
        "## Single-Clause Fit Ladder",
        "",
        metric_table(
            best,
            [
                "single_clause_seen_seen_binding",
                "single_clause_new_seen_binding",
                "single_clause_seen_heldout_binding",
                "single_clause_new_heldout_binding",
            ],
        ),
        "",
        "## Primitive Retention Across Curriculum",
        "",
        retention_table(analysis),
        "",
        "## Replay Ablation",
        "",
        replay_table(analysis),
        "",
        "## Flat vs Curriculum",
        "",
        flat_vs_curriculum_table(analysis),
        "",
        "## Seen Fit Gate",
        "",
        fit_gate_table(analysis["fit_gate"]),
        "",
        "## Real Teacher-Forced Clause Diagnostic",
        "",
        metric_table(
            best,
            [
                "teacher_forced_clause_seen",
                "teacher_forced_clause_heldout_binding",
                "teacher_forced_clause_merge_two",
            ],
        ),
        "",
        "## Clause Selection Diagnostic",
        "",
        metric_table(best, ["clause_selection_seen"]),
        "",
        "## LM Action vs Policy Head",
        "",
        lm_vs_policy_table(best, policy),
        "",
        "## Role Embeddings if gated",
        "",
        "Not run. The fit gate was not reached with plain token DSL and replay variants, so role embeddings remain a later controlled ablation.",
        "",
        "## MERGE_TWO Phase Accuracy",
        "",
        phase_table(best, "merge_two_seen"),
        "",
        "## Error Propagation",
        "",
        error_propagation_table(best),
        "",
        "## Heldout Binding",
        "",
        metric_closed_table(best, ["heldout_binding"]),
        "",
        "## Heldout Program",
        "",
        metric_closed_table(best, ["heldout_program"]),
        "",
        "## MERGE_TWO Ladder",
        "",
        metric_closed_table(
            best, ["merge_two_seen", "merge_two_11_20", "merge_two_21_50"]
        ),
        "",
        "## Closed-Loop MERGE_TWO if gated",
        "",
        "Closed-loop MERGE_TWO was run as a diagnostic, but should not be interpreted as true OOD success because the seen-fit gate was not fully passed.",
        "",
        "## Structural Overlap Audit",
        "",
        json_block(manifest["structural_overlap"]),
        "",
        "## Interpretation",
        "",
        analysis["decision"],
        "",
        "## Recommended Architecture",
        "",
        recommendation(analysis["decision"]),
        "",
        "## Checks",
        "",
        f"- local/remote ruff + pytest + CUDA smoke: {'passed' if checks_passed else 'pending at report build'}",
        f"- commit hash at run: `{git_rev_parse('HEAD')[:7]}`",
    ]
    DOC_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines).rstrip() + "\n"
    DOC_REPORT_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def best_lm_run(analysis: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        name
        for name in (
            "flat_balanced_lm",
            "curriculum_no_replay_lm",
            "curriculum_replay25_lm",
            "curriculum_replay50_lm",
            "single_clause_base_lm",
            "binding_lm",
        )
        if name in analysis["runs"]
    ]
    if not candidates:
        return {"name": None, "eval": {}, "closed_loop": {}}
    name = max(
        candidates,
        key=lambda item: (
            closed_metric(analysis["runs"][item], "program_seen"),
            metric(analysis["runs"][item], "single_clause_seen_seen_binding"),
            metric(analysis["runs"][item], "binding_l2p_heldout"),
        ),
    )
    result = dict(analysis["runs"][name])
    result["name"] = name
    return result


def metric(run: dict[str, Any], split: str) -> float:
    return float(
        run.get("eval", {}).get(split, {}).get("overall", {}).get("accuracy", 0.0)
    )


def closed_metric(run: dict[str, Any], split: str) -> float:
    return float(
        run.get("closed_loop", {})
        .get(split, {})
        .get("overall", {})
        .get("final_state_exact", 0.0)
    )


def invalid_metric(run: dict[str, Any], split: str) -> float:
    return float(
        run.get("closed_loop", {})
        .get(split, {})
        .get("overall", {})
        .get("invalid_action_rate", 0.0)
    )


def metric_table(run: dict[str, Any], splits: Sequence[str]) -> str:
    lines = ["| split | accuracy | invalid |", "|---|---:|---:|"]
    for split in splits:
        summary = run.get("eval", {}).get(split, {})
        overall = summary.get("overall", {})
        lines.append(
            f"| {split} | {float(overall.get('accuracy', 0.0)):.4f} | {float(overall.get('invalid_rate', 0.0)):.4f} |"
        )
    return "\n".join(lines)


def metric_closed_table(run: dict[str, Any], splits: Sequence[str]) -> str:
    lines = ["| split | one-step | closed-loop | invalid |", "|---|---:|---:|---:|"]
    for split in splits:
        lines.append(
            f"| {split} | {metric(run, split):.4f} | {closed_metric(run, split):.4f} | {invalid_metric(run, split):.4f} |"
        )
    return "\n".join(lines)


def retention_table(analysis: dict[str, Any]) -> str:
    splits = [
        "binding_l2p_heldout",
        "binding_p2l_heldout",
        "predicate_heldout",
        "action_heldout",
        "single_clause_seen_seen_binding",
        "program_seen",
    ]
    lines = ["| run | " + " | ".join(splits) + " |", "|" + "---|" * (len(splits) + 1)]
    for name in RUN_SPECS:
        run = analysis["runs"].get(name, {})
        values = [f"{metric(run, split):.4f}" for split in splits]
        lines.append(f"| {name} | " + " | ".join(values) + " |")
    return "\n".join(lines)


def replay_table(analysis: dict[str, Any]) -> str:
    return metric_closed_table_for_runs(
        analysis,
        ["curriculum_no_replay_lm", "curriculum_replay25_lm", "curriculum_replay50_lm"],
        ["program_seen", "heldout_binding", "heldout_program", "merge_two_seen"],
    )


def flat_vs_curriculum_table(analysis: dict[str, Any]) -> str:
    return metric_closed_table_for_runs(
        analysis,
        ["flat_balanced_lm", "curriculum_replay25_lm", "curriculum_replay50_lm"],
        [
            "program_seen",
            "single_clause_new_heldout_binding",
            "heldout_program",
            "merge_two_seen",
        ],
    )


def metric_closed_table_for_runs(
    analysis: dict[str, Any], runs: Sequence[str], splits: Sequence[str]
) -> str:
    lines = ["| run | " + " | ".join(splits) + " |", "|" + "---|" * (len(splits) + 1)]
    for run_name in runs:
        run = analysis["runs"].get(run_name, {})
        values = []
        for split in splits:
            if split.startswith("single_clause"):
                values.append(f"{metric(run, split):.4f}")
            else:
                values.append(
                    f"{metric(run, split):.4f}/{closed_metric(run, split):.4f}"
                )
        lines.append(f"| {run_name} | " + " | ".join(values) + " |")
    return "\n".join(lines)


def fit_gate_table(gate: dict[str, Any]) -> str:
    lines = ["| check | passed |", "|---|---:|"]
    for name, passed in gate["checks"].items():
        lines.append(f"| {name} | {str(bool(passed)).lower()} |")
    lines.append(f"| overall | {str(bool(gate['passed'])).lower()} |")
    return "\n".join(lines)


def lm_vs_policy_table(lm_run: dict[str, Any], policy_run: dict[str, Any]) -> str:
    splits = ["program_seen", "heldout_binding", "heldout_program", "merge_two_seen"]
    lines = ["| split | LM one/closed | policy one/closed |", "|---|---:|---:|"]
    for split in splits:
        lines.append(
            f"| {split} | {metric(lm_run, split):.4f}/{closed_metric(lm_run, split):.4f} | {metric(policy_run, split):.4f}/{closed_metric(policy_run, split):.4f} |"
        )
    return "\n".join(lines)


def phase_table(run: dict[str, Any], split: str) -> str:
    by_phase = run.get("eval", {}).get(split, {}).get("by_phase", {})
    lines = ["| phase | count | accuracy |", "|---|---:|---:|"]
    for phase, stats in sorted(by_phase.items()):
        lines.append(
            f"| {phase} | {int(stats.get('count', 0))} | {float(stats.get('accuracy', 0.0)):.4f} |"
        )
    return "\n".join(lines)


def error_propagation_table(run: dict[str, Any]) -> str:
    lines = [
        "| split | length bucket | episodes | success | first-error step avg |",
        "|---|---:|---:|---:|---:|",
    ]
    for split in ("merge_two_seen", "merge_two_11_20", "merge_two_21_50"):
        buckets = run.get("closed_loop", {}).get(split, {}).get("by_length_bucket", {})
        for bucket, stats in sorted(buckets.items()):
            lines.append(
                f"| {split} | {bucket} | {int(stats.get('count', 0))} | {float(stats.get('final_state_exact', 0.0)):.4f} | {fmt_optional(stats.get('avg_first_error_step'))} |"
            )
    return "\n".join(lines)


def binding_interpretation(run: dict[str, Any]) -> str:
    l2p = min(metric(run, "binding_l2p_seen"), metric(run, "binding_l2p_heldout"))
    p2l = min(metric(run, "binding_p2l_seen"), metric(run, "binding_p2l_heldout"))
    table = min(
        metric(run, "binding_full_table_seen"),
        metric(run, "binding_full_table_heldout"),
    )
    if l2p >= 0.99 and p2l >= 0.99 and table < 0.99:
        return "BINDING SEMANTICS SOLVED; full-table serialization is not solved."
    if l2p >= 0.99 and p2l >= 0.99:
        return "BINDING SEMANTICS SOLVED."
    return "Point binding remains below gate; downstream composition should not be blamed alone."


def recommendation(decision: str) -> str:
    if "OUTCOME C" in decision:
        return "Continue with a discrete internal action policy interface before changing memory architecture."
    if "OUTCOME B" in decision:
        return "Move to hierarchical clause/subprogram selection while preserving exact external state."
    if "OUTCOME D" in decision:
        return "Use an explicit symbolic DSL interpreter plus a neural compiler/planner rather than forcing a flat LM to execute programs."
    if "OUTCOME E" in decision:
        return "Fix curriculum/objective and seen-fit reliability before further OOD interpretation."
    return "External-state neural program interpreter remains viable; broaden primitives cautiously."


def summarize_predictions(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row["correct"])
    invalid = sum(1 for row in rows if row["prediction"] == "INVALID")
    return {
        "overall": {
            "count": total,
            "accuracy": correct / total if total else 0.0,
            "invalid_rate": invalid / total if total else 0.0,
        },
        "by_task_type": grouped_accuracy(
            rows, lambda row: row["metadata"].get("split", "")
        ),
        "by_metric": grouped_accuracy(
            rows, lambda row: row["metadata"].get("binding_metric", "")
        ),
        "by_ladder": grouped_accuracy(
            rows, lambda row: row["metadata"].get("ladder", "")
        ),
        "by_phase": grouped_accuracy(
            rows, lambda row: row["metadata"].get("phase", "")
        ),
        "failure_samples": [row for row in rows if not row["correct"]][:20],
    }


def grouped_accuracy(rows: Sequence[dict[str, Any]], key_fn) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = key_fn(row)
        if key:
            buckets[str(key)].append(row)
    return {
        key: {
            "count": len(bucket),
            "accuracy": sum(1 for row in bucket if row["correct"]) / len(bucket),
        }
        for key, bucket in sorted(buckets.items())
    }


def summarize_episodes(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    success = sum(1 for row in rows if row["final_state_exact"])
    invalid = sum(1 for row in rows if row["invalid"])
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        length = int(row["trajectory_length"])
        if length <= 10:
            bucket = "0_10"
        elif length <= 20:
            bucket = "11_20"
        elif length <= 50:
            bucket = "21_50"
        else:
            bucket = "51_plus"
        buckets[bucket].append(row)
    return {
        "overall": {
            "count": total,
            "final_state_exact": success / total if total else 0.0,
            "invalid_action_rate": invalid / total if total else 0.0,
        },
        "by_length_bucket": {
            key: episode_bucket_stats(bucket) for key, bucket in sorted(buckets.items())
        },
        "first_error_histogram": first_error_histogram(rows),
        "failure_samples": [row for row in rows if not row["final_state_exact"]][:20],
    }


def episode_bucket_stats(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    error_steps = [
        row["first_error"]["step"]
        for row in rows
        if isinstance(row.get("first_error"), dict)
    ]
    return {
        "count": len(rows),
        "final_state_exact": sum(1 for row in rows if row["final_state_exact"])
        / len(rows),
        "avg_first_error_step": sum(error_steps) / len(error_steps)
        if error_steps
        else None,
    }


def first_error_histogram(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    counter = Counter()
    for row in rows:
        error = row.get("first_error")
        if isinstance(error, dict):
            counter[str(error.get("phase") or "NO_PHASE")] += 1
    return dict(sorted(counter.items()))


def candidates_for_expected(expected: str, row: dict[str, Any]) -> list[str]:
    metric_name = row.get("metadata", {}).get("binding_metric")
    if metric_name == "l2p":
        return list(m201.REGISTERS)
    if metric_name == "p2l":
        return list(ALL_VARS)
    if metric_name == "full_table":
        variables = tuple(row.get("metadata", {}).get("variables", PRIMARY_VARS))
        return [
            m201.render_binding_table(
                m201.Binding(dict(zip(variables, registers, strict=True)))
            )
            for registers in itertools.permutations(m201.REGISTERS)
        ]
    if expected in {"TRUE", "FALSE"}:
        return ["TRUE", "FALSE"]
    if re.fullmatch(r"C\d+", expected):
        return [f"C{i}" for i in range(6)]
    if expected in action_vocab():
        return action_vocab()
    if expected in ALL_VARS:
        return list(ALL_VARS)
    if expected in m201.REGISTERS:
        return list(m201.REGISTERS)
    return [expected]


def parse_target(text: str) -> str:
    compact = re.sub(r"\s+", " ", str(text).upper()).strip()
    if match := re.search(r"\bC\d+\b", compact):
        return match.group(0)
    return m201.parse_action_text(compact)


def policy_examples_from_rows(rows: Sequence[dict[str, Any]]) -> list[PolicyExample]:
    result = []
    for row in rows:
        expected = m201.parse_action_text(row["answer"])
        if expected in action_vocab():
            result.append(
                PolicyExample(
                    prompt=row["prompt"],
                    action=expected,
                    split=row.get("metadata", {}).get("split", ""),
                    metadata=row.get("metadata", {}),
                )
            )
    return result


def action_vocab() -> list[str]:
    actions = ["H"]
    actions.extend(f"D {reg}" for reg in m201.REGISTERS)
    actions.extend(
        f"M {src} {dst}"
        for src in m201.REGISTERS
        for dst in m201.REGISTERS
        if src != dst
    )
    return actions


def action_to_id(action: str) -> int:
    return action_vocab().index(action)


def make_record(
    task_type: str, prompt: str, answer: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    payload = {
        "task_type": task_type,
        "prompt": prompt,
        "answer": answer,
        "metadata": metadata,
    }
    payload["id"] = (
        f"m201a-{m201.stable_hash(json.dumps(payload, sort_keys=True))[:16]}"
    )
    return payload


def balance_rows(rows: Sequence[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if not rows:
        return []
    rng = random.Random(SEED + count + len(rows))
    result = [dict(rows[index % len(rows)]) for index in range(count)]
    rng.shuffle(result)
    return result


def mix_rows(
    program_rows: Sequence[dict[str, Any]],
    primitive_rows: Sequence[dict[str, Any]],
    primitive_fraction: float,
    count: int,
) -> list[dict[str, Any]]:
    primitive_count = round(count * primitive_fraction)
    program_count = count - primitive_count
    return balance_rows(program_rows, program_count) + balance_rows(
        primitive_rows, primitive_count
    )


def binding_hash(binding: Any) -> str:
    return m201.stable_hash(json.dumps(binding.canonical_items()))


def build_manifest(
    train_rows: dict[str, list[dict[str, Any]]],
    eval_rows: dict[str, list[dict[str, Any]]],
    train_bindings: Sequence[Any],
    heldout_bindings: Sequence[Any],
) -> dict[str, Any]:
    train_meta = [
        row.get("metadata", {}) for rows in train_rows.values() for row in rows
    ]
    eval_meta = [row.get("metadata", {}) for rows in eval_rows.values() for row in rows]
    return {
        "kind": "m201a_fair_compositional_retest",
        "seed": SEED,
        "model_config": MODEL_CONFIG,
        "train_counts": {name: len(rows) for name, rows in train_rows.items()},
        "eval_counts": {name: len(rows) for name, rows in eval_rows.items()},
        "binding_split": {
            "train": len(train_bindings),
            "heldout": len(heldout_bindings),
            "overlap": len(
                {binding_hash(b) for b in train_bindings}
                & {binding_hash(b) for b in heldout_bindings}
            ),
        },
        "structural_overlap": {
            "exact_prompt_overlap": len(
                {row["prompt"] for rows in train_rows.values() for row in rows}
                & {row["prompt"] for rows in eval_rows.values() for row in rows}
            ),
            "normalized_ast_overlap_heldout_program": split_overlap(
                train_meta, eval_rows.get("heldout_program", []), "normalized_ast_hash"
            ),
            "template_overlap_heldout_program": split_overlap(
                train_meta, eval_rows.get("heldout_program", []), "template_hash"
            ),
            "template_overlap_merge_two": split_overlap(
                train_meta, eval_rows.get("merge_two_seen", []), "template_hash"
            ),
            "forbidden_prompt_count": sum(
                1
                for rows in [*train_rows.values(), *eval_rows.values()]
                for row in rows
                if m201.prompt_has_forbidden_marker(row["prompt"])
            ),
        },
        "coverage": {
            "train_variable_tokens": sorted(
                {var for row in train_meta for var in row.get("variables", [])}
                | {var for row in train_meta for var in row.get("alpha_pair", [])}
            ),
            "train_binding_hashes": len(
                {
                    row.get("binding_hash")
                    for row in train_meta
                    if row.get("binding_hash")
                }
            ),
            "eval_binding_hashes": len(
                {
                    row.get("binding_hash")
                    for row in eval_meta
                    if row.get("binding_hash")
                }
            ),
        },
    }


def split_overlap(
    train_meta: Sequence[dict[str, Any]], eval_rows: Sequence[dict[str, Any]], key: str
) -> int:
    train_values = {row[key] for row in train_meta if key in row}
    eval_values = {
        row.get("metadata", {}).get(key)
        for row in eval_rows
        if row.get("metadata", {}).get(key)
    }
    return len(train_values & eval_values)


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def write_policy_jsonl(path: Path, rows: Sequence[PolicyExample]) -> None:
    write_jsonl(
        path,
        [
            {
                "prompt": row.prompt,
                "action": row.action,
                "split": row.split,
                "metadata": row.metadata,
            }
            for row in rows
        ],
    )


def read_policy_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def final_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    return checkpoints[-1] if checkpoints else None


def prune_intermediate_checkpoints(run_dir: Path) -> None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    for checkpoint in checkpoints[:-1]:
        checkpoint.unlink(missing_ok=True)


def remote_environment_section() -> str:
    return (
        "- hostname: `karina`\n"
        "- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB`\n"
        f"- model config: `{MODEL_CONFIG}`\n"
        f"- sequence length: `{SEQUENCE_LENGTH}`"
    )


def json_block(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```"


def fmt_optional(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def git_rev_parse(ref: str) -> str:
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    main()
