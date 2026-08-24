from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import re
import socket
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import torch
import torch.nn.functional as F

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.generation import load_model_for_inference
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import (
    ANSWER_TOKEN,
    BOS_TOKEN,
    END_TOKEN,
    EOS_TOKEN,
    PROMPT_TOKEN,
)
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m201_compositional_dsl_variable_binding"
RUNS_DIR = ROOT / "runs" / "m201_compositional_dsl_variable_binding"
DOC_PATH = ROOT / "docs" / "m201_compositional_dsl_variable_binding_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m201_compositional_dsl_variable_binding_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 20100
REGISTERS = ("R0", "R1", "R2", "R3")
TRAIN_VARS = ("A", "B", "C", "D")
ALPHA_VARS = ("X", "Y", "Z", "W")
TRAIN_COUNTS = tuple(range(11))
OOD_11_20 = tuple(range(11, 21))
OOD_21_50 = tuple(range(21, 51))
OOD_51_100 = tuple(range(51, 101))
HELDOUT_REGISTER_PAIRS = (("R0", "R3"), ("R3", "R0"))
MODEL_CONFIG = "arithmetic_3m"
POSITION_ENCODING = "relative"
NUMERIC_TOKENIZATION = "digit_safe"
BATCH_SIZE = 8
SEQUENCE_LENGTH = 256
LOSS_MODE = "answer-only"
LEARNING_RATE = 3e-4
GRAD_CLIP_NORM = 1.0

PRIMITIVE_STEPS = 5000
FLAT_STEPS = 8000
CURRICULUM_STAGE_STEPS = 3000

FORBIDDEN_PROMPT_PATTERNS = (
    r"\bCASE\b",
    r"\bID\b",
    r"\bEXAMPLE\b",
    r"\bTRAIN\b",
    r"\bEVAL\b",
    r"\bSPLIT\b",
    r"\bSEED\b",
    r"\bPROGRAM_ID\b",
)

PredicateKind = Literal["EMPTY", "NONEMPTY"]
ActionKind = Literal["MOVE_ONE", "DROP_ONE", "HALT"]


@dataclass(frozen=True)
class Binding:
    mapping: dict[str, str]

    def physical(self, variable: str) -> str:
        return self.mapping[variable]

    def logical(self, register: str) -> str:
        matches = [var for var, value in self.mapping.items() if value == register]
        if len(matches) != 1:
            raise ValueError(f"Register {register} has no unique logical variable")
        return matches[0]

    def canonical_items(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self.mapping.items()))


@dataclass(frozen=True)
class Predicate:
    variable: str
    kind: PredicateKind

    def matches(self, state: dict[str, int], binding: Binding) -> bool:
        value = state[binding.physical(self.variable)]
        return value == 0 if self.kind == "EMPTY" else value > 0

    def alpha(self, rename: dict[str, str]) -> Predicate:
        return Predicate(rename[self.variable], self.kind)


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    source: str | None = None
    destination: str | None = None

    def resolve(self, binding: Binding) -> PhysicalAction:
        if self.kind == "MOVE_ONE":
            if self.source is None or self.destination is None:
                raise ValueError("MOVE_ONE needs source and destination")
            return PhysicalAction(
                "MOVE_ONE",
                binding.physical(self.source),
                binding.physical(self.destination),
            )
        if self.kind == "DROP_ONE":
            if self.source is None:
                raise ValueError("DROP_ONE needs source")
            return PhysicalAction("DROP_ONE", binding.physical(self.source))
        return PhysicalAction("HALT")

    def alpha(self, rename: dict[str, str]) -> Action:
        return Action(
            self.kind,
            rename[self.source] if self.source is not None else None,
            rename[self.destination] if self.destination is not None else None,
        )


@dataclass(frozen=True)
class PhysicalAction:
    kind: ActionKind
    source: str | None = None
    destination: str | None = None

    def render(self) -> str:
        if self.kind == "MOVE_ONE":
            return f"M {self.source} {self.destination}"
        if self.kind == "DROP_ONE":
            return f"D {self.source}"
        return "H"


@dataclass(frozen=True)
class Clause:
    predicates: tuple[Predicate, ...]
    action: Action

    def matches(self, state: dict[str, int], binding: Binding) -> bool:
        return all(predicate.matches(state, binding) for predicate in self.predicates)

    def alpha(self, rename: dict[str, str]) -> Clause:
        return Clause(
            tuple(predicate.alpha(rename) for predicate in self.predicates),
            self.action.alpha(rename),
        )


@dataclass(frozen=True)
class Program:
    name: str
    clauses: tuple[Clause, ...]
    family: str

    def applicable_clause_index(self, state: dict[str, int], binding: Binding) -> int:
        matches = [
            index
            for index, clause in enumerate(self.clauses)
            if clause.matches(state, binding)
        ]
        if len(matches) != 1:
            raise ValueError(f"Program {self.name} not deterministic: {matches}")
        return matches[0]

    def oracle_action(self, state: dict[str, int], binding: Binding) -> PhysicalAction:
        return self.clauses[
            self.applicable_clause_index(state, binding)
        ].action.resolve(binding)

    def alpha(self, variables: Sequence[str]) -> Program:
        old_vars = sorted(program_variables(self))
        rename = {old: new for old, new in zip(old_vars, variables, strict=False)}
        return Program(
            f"{self.name}_alpha",
            tuple(clause.alpha(rename) for clause in self.clauses),
            self.family,
        )


@dataclass
class RegisterEnvironment:
    state: dict[str, int]
    terminated: bool = False
    invalid: bool = False

    def __post_init__(self) -> None:
        self.state = {
            register: int(self.state.get(register, 0)) for register in REGISTERS
        }
        if any(value < 0 for value in self.state.values()):
            raise ValueError("Register counts must be non-negative")

    def observe(self) -> str:
        pieces = []
        for register in REGISTERS:
            pieces.append(register)
            pieces.append("E" if self.state[register] == 0 else "NE")
        return " ".join(pieces)

    def step(self, action: PhysicalAction) -> None:
        if self.terminated:
            self.invalid = True
            return
        if action.kind == "HALT":
            self.terminated = True
            return
        if action.source is None or self.state[action.source] <= 0:
            self.invalid = True
            return
        self.state[action.source] -= 1
        if action.kind == "MOVE_ONE":
            if action.destination is None:
                self.invalid = True
                return
            self.state[action.destination] += 1
        elif action.kind != "DROP_ONE":
            self.invalid = True


@dataclass(frozen=True)
class EpisodeSpec:
    program: Program
    binding: Binding
    initial_state: dict[str, int]
    split: str
    variant: str
    clause_order: tuple[int, ...] | None = None
    distractor_count: int = 0
    surface: Literal["structured", "compact", "alternate"] = "structured"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M-20.1 compositional DSL and variable binding lab."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-primitives")
    subparsers.add_parser("run-flat")
    subparsers.add_parser("run-curriculum")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-primitives":
        run_primitives()
    elif args.command == "run-flat":
        run_model(
            "flat_program_lm", DATASET_DIR / "train" / "flat_program.jsonl", FLAT_STEPS
        )
    elif args.command == "run-curriculum":
        run_curriculum()
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_primitives()
        run_model(
            "flat_program_lm", DATASET_DIR / "train" / "flat_program.jsonl", FLAT_STEPS
        )
        run_curriculum()
        analyze_all()
        build_report(checks_passed=False)


def prepare_datasets() -> None:
    payload = build_datasets()
    for section, splits in payload["datasets"].items():
        for name, rows in splits.items():
            _write_jsonl(DATASET_DIR / section / f"{name}.jsonl", rows)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(payload["manifest"], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_datasets() -> dict[str, Any]:
    bindings = all_bindings(TRAIN_VARS)
    train_bindings, heldout_bindings = split_bindings(bindings)
    train_programs = grammar_train_programs()
    heldout_programs = grammar_heldout_programs()
    merge_two = merge_two_program(TRAIN_VARS)
    merge_three = merge_three_program(TRAIN_VARS)
    datasets: dict[str, dict[str, list[dict[str, Any]]]] = {"train": {}, "eval": {}}

    datasets["train"]["binding"] = repeat_records(
        binding_records(train_bindings, target_vars=TRAIN_VARS, start_index=0), 4000
    )
    datasets["eval"]["binding_seen"] = binding_records(
        train_bindings[:6], target_vars=TRAIN_VARS, start_index=10_000
    )
    datasets["eval"]["binding_heldout"] = binding_records(
        heldout_bindings, target_vars=TRAIN_VARS, start_index=11_000
    )
    datasets["train"]["predicate"] = repeat_records(
        predicate_records(train_bindings, TRAIN_VARS, start_index=20_000), 4000
    )
    datasets["eval"]["predicate_seen"] = predicate_records(
        train_bindings[:6], TRAIN_VARS, start_index=21_000
    )
    datasets["eval"]["predicate_heldout"] = predicate_records(
        heldout_bindings, TRAIN_VARS, start_index=22_000
    )
    datasets["train"]["action_semantics"] = repeat_records(
        action_semantics_records(train_bindings, TRAIN_VARS, start_index=30_000), 5000
    )
    datasets["eval"]["action_seen"] = action_semantics_records(
        train_bindings[:6], TRAIN_VARS, start_index=31_000
    )
    datasets["eval"]["action_heldout_register_pairs"] = action_semantics_records(
        heldout_bindings, TRAIN_VARS, start_index=32_000, only_heldout_pairs=True
    )
    single_clause_train = single_clause_records(
        train_bindings, TRAIN_VARS, start_index=40_000
    )
    datasets["train"]["single_clause"] = repeat_records(single_clause_train, 6000)
    datasets["eval"]["single_clause_heldout"] = single_clause_records(
        heldout_bindings, TRAIN_VARS, start_index=41_000
    )
    datasets["eval"]["alpha_renaming"] = single_clause_records(
        alpha_bindings(train_bindings[:6]), ALPHA_VARS, start_index=42_000, alpha=True
    )

    flat_train = program_records(
        train_programs,
        train_bindings,
        TRAIN_COUNTS,
        start_index=50_000,
        include_families=True,
        target_count=14000,
    )
    primitive_train = (
        datasets["train"]["binding"]
        + datasets["train"]["predicate"]
        + datasets["train"]["action_semantics"]
        + datasets["train"]["single_clause"]
    )
    datasets["train"]["primitives"] = repeat_records(primitive_train, 12000)
    datasets["train"]["flat_program"] = flat_train
    datasets["train"]["curriculum_stage1"] = repeat_records(
        primitive_train + single_clause_train, 12000
    )
    datasets["train"]["curriculum_stage2"] = program_records(
        train_programs,
        train_bindings,
        TRAIN_COUNTS,
        start_index=60_000,
        include_families=True,
        target_count=16000,
        randomized_order=True,
        distractor_choices=(0, 1, 2, 4),
    )
    eval_specs = {
        "program_seen": episode_specs(
            train_programs[:8], train_bindings[:6], TRAIN_COUNTS
        ),
        "program_length_21_50": episode_specs(
            train_programs[:6], train_bindings[:4], OOD_21_50
        ),
        "program_length_51_100": episode_specs(
            train_programs[:4], train_bindings[:3], OOD_51_100[:10]
        ),
        "heldout_binding": episode_specs(
            train_programs[:8], heldout_bindings, TRAIN_COUNTS
        ),
        "heldout_program_instance": episode_specs(
            heldout_programs, train_bindings[:8], TRAIN_COUNTS
        ),
        "heldout_predicate_composition": episode_specs(
            [heldout_predicate_composition_program()], train_bindings[:8], TRAIN_COUNTS
        ),
        "heldout_merge_two_seen": merge_two_specs(
            merge_two, train_bindings[:8], TRAIN_COUNTS
        ),
        "heldout_merge_two_11_20": merge_two_specs(
            merge_two, train_bindings[:4], OOD_11_20
        ),
        "heldout_merge_two_21_50": merge_two_specs(
            merge_two, train_bindings[:4], OOD_21_50
        ),
        "heldout_merge_two_51_100": merge_two_specs(
            merge_two, train_bindings[:3], OOD_51_100[:10]
        ),
        "merge_three": merge_three_specs(merge_three, train_bindings[:4], OOD_11_20),
        "order_invariance": order_specs(
            train_programs[:8], train_bindings[:4], TRAIN_COUNTS
        ),
        "distractor_0": distractor_specs(train_programs[:4], train_bindings[:4], 0),
        "distractor_2": distractor_specs(train_programs[:4], train_bindings[:4], 2),
        "distractor_8": distractor_specs(train_programs[:4], train_bindings[:4], 8),
        "distractor_16": distractor_specs(train_programs[:4], train_bindings[:4], 16),
        "surface_alternate": alternate_surface_specs(
            train_programs[:6], train_bindings[:4]
        ),
        "program_removed": ablation_specs(
            train_programs[:6], train_bindings[:4], "program_removed"
        ),
        "wrong_program": ablation_specs(
            train_programs[:6], train_bindings[:4], "wrong_program"
        ),
        "binding_swapped": ablation_specs(
            train_programs[:6], train_bindings[:4], "binding_swapped"
        ),
    }
    for name, specs in eval_specs.items():
        datasets["eval"][name] = records_from_specs(specs, start_index=70_000)
    datasets["eval"]["teacher_forced_merge_two"] = teacher_forced_records(
        merge_two_specs(merge_two, train_bindings[:8], TRAIN_COUNTS), start_index=90_000
    )

    manifest = build_manifest(datasets, train_programs, heldout_programs, merge_two)
    return {"datasets": datasets, "manifest": manifest}


def all_bindings(variables: Sequence[str]) -> list[Binding]:
    return [
        Binding(dict(zip(variables, registers, strict=True)))
        for registers in itertools.permutations(REGISTERS)
    ]


def split_bindings(bindings: Sequence[Binding]) -> tuple[list[Binding], list[Binding]]:
    heldout = [
        binding
        for binding in bindings
        if ("A", "R0") in binding.canonical_items()
        and ("C", "R3") in binding.canonical_items()
        or ("A", "R3") in binding.canonical_items()
        and ("C", "R0") in binding.canonical_items()
    ]
    train = [binding for binding in bindings if binding not in heldout]
    return train, heldout


def alpha_bindings(bindings: Sequence[Binding]) -> list[Binding]:
    return [
        Binding(dict(zip(ALPHA_VARS, binding.mapping.values(), strict=True)))
        for binding in bindings
    ]


def binding_records(
    bindings: Sequence[Binding], *, target_vars: Sequence[str], start_index: int
) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        for variable in target_vars:
            rows.append(
                record(
                    start_index + len(rows),
                    "m201.binding.logical_to_physical",
                    f"{render_binding(binding)}\nQ PHYS {variable}",
                    f"FINAL {binding.physical(variable)}",
                    {"kind": "binding", "binding": binding.mapping, "query": variable},
                )
            )
        for register in REGISTERS:
            rows.append(
                record(
                    start_index + len(rows),
                    "m201.binding.physical_to_logical",
                    f"{render_binding(binding)}\nQ LOG {register}",
                    f"FINAL {binding.logical(register)}",
                    {"kind": "binding", "binding": binding.mapping, "query": register},
                )
            )
        rows.append(
            record(
                start_index + len(rows),
                "m201.binding.full_table",
                f"{render_binding(binding)}\nQ TABLE",
                "FINAL " + render_binding_table(binding),
                {"kind": "binding", "binding": binding.mapping},
            )
        )
    return rows


def predicate_records(
    bindings: Sequence[Binding], variables: Sequence[str], *, start_index: int
) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        for variable in variables:
            register = binding.physical(variable)
            for kind in ("EMPTY", "NONEMPTY"):
                for value in (0, 3):
                    state = zero_state()
                    state[register] = value
                    predicate = Predicate(variable, kind)  # type: ignore[arg-type]
                    rows.append(
                        record(
                            start_index + len(rows),
                            f"m201.predicate.{kind.lower()}",
                            f"TEST {pred_token(kind)} {variable}\n{render_binding(binding)}\n{render_state(state)}",
                            f"FINAL {'TRUE' if predicate.matches(state, binding) else 'FALSE'}",
                            {
                                "kind": "predicate",
                                "predicate": kind,
                                "variable": variable,
                                "register": register,
                                "state": state,
                                "binding": binding.mapping,
                            },
                        )
                    )
    return rows


def action_semantics_records(
    bindings: Sequence[Binding],
    variables: Sequence[str],
    *,
    start_index: int,
    only_heldout_pairs: bool = False,
) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        for source, destination in itertools.permutations(variables, 2):
            action = Action("MOVE_ONE", source, destination)
            physical = action.resolve(binding).render()
            pair = (binding.physical(source), binding.physical(destination))
            if only_heldout_pairs and pair not in HELDOUT_REGISTER_PAIRS:
                continue
            rows.append(
                record(
                    start_index + len(rows),
                    "m201.action.move",
                    f"ACT M SRC {source} DST {destination}\n{render_binding(binding)}",
                    f"FINAL {physical}",
                    {
                        "kind": "action",
                        "action": "MOVE_ONE",
                        "source": source,
                        "destination": destination,
                        "physical_pair": pair,
                        "binding": binding.mapping,
                    },
                )
            )
        for source in variables:
            action = Action("DROP_ONE", source)
            rows.append(
                record(
                    start_index + len(rows),
                    "m201.action.drop",
                    f"ACT D SRC {source}\n{render_binding(binding)}",
                    f"FINAL {action.resolve(binding).render()}",
                    {
                        "kind": "action",
                        "action": "DROP_ONE",
                        "binding": binding.mapping,
                    },
                )
            )
        rows.append(
            record(
                start_index + len(rows),
                "m201.action.halt",
                f"ACT H\n{render_binding(binding)}",
                "FINAL H",
                {"kind": "action", "action": "HALT", "binding": binding.mapping},
            )
        )
    return rows


def single_clause_records(
    bindings: Sequence[Binding],
    variables: Sequence[str],
    *,
    start_index: int,
    alpha: bool = False,
) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        for source, destination in itertools.permutations(variables[:4], 2):
            for kind in ("EMPTY", "NONEMPTY"):
                for truth_value in (False, True):
                    state = zero_state()
                    state[binding.physical(source)] = int(truth_value)
                    predicate = Predicate(source, kind)  # type: ignore[arg-type]
                    action = Action("MOVE_ONE", source, destination)
                    clause = Clause((predicate,), action)
                    expected = (
                        action.resolve(binding).render()
                        if clause.matches(state, binding)
                        else "H"
                    )
                    rows.append(
                        record(
                            start_index + len(rows),
                            "m201.single_clause",
                            f"{render_program(Program('single', (clause,), 'single'), binding, state)}",
                            f"FINAL {expected}",
                            {
                                "kind": "single_clause",
                                "binding": binding.mapping,
                                "state": state,
                                "alpha": alpha,
                                "expected_action": expected,
                            },
                        )
                    )
    return rows


def grammar_train_programs() -> list[Program]:
    v = TRAIN_VARS
    return [
        drain_program(v[0], v[2]),
        drain_program(v[1], v[2]),
        drain_program(v[0], v[3]),
        clear_program(v[0]),
        clear_program(v[1]),
        clear_two_program(v[0], v[1]),
        drop_then_move_program(v[0], v[1], v[2]),
        move_then_drop_program(v[0], v[2], v[1]),
        switch_drop_then_move_program(v[0], v[1], v[2]),
        inspect_second_then_move_program(v[0], v[1], v[3]),
    ]


def grammar_heldout_programs() -> list[Program]:
    v = TRAIN_VARS
    return [
        move_move_then_drop_program(v[0], v[1], v[2], v[3]),
        drop_move_then_drop_program(v[0], v[1], v[2]),
        move_two_sources_program(v[0], v[2], v[3]),
    ]


def drain_program(src: str, dst: str) -> Program:
    return Program(
        f"drain_{src}_{dst}",
        (
            Clause((Predicate(src, "NONEMPTY"),), Action("MOVE_ONE", src, dst)),
            Clause((Predicate(src, "EMPTY"),), Action("HALT")),
        ),
        "drain",
    )


def clear_program(src: str) -> Program:
    return Program(
        f"clear_{src}",
        (
            Clause((Predicate(src, "NONEMPTY"),), Action("DROP_ONE", src)),
            Clause((Predicate(src, "EMPTY"),), Action("HALT")),
        ),
        "clear",
    )


def clear_two_program(first: str, second: str) -> Program:
    return Program(
        f"clear_two_{first}_{second}",
        (
            Clause((Predicate(first, "NONEMPTY"),), Action("DROP_ONE", first)),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "NONEMPTY")),
                Action("DROP_ONE", second),
            ),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "EMPTY")),
                Action("HALT"),
            ),
        ),
        "clear_two",
    )


def drop_then_move_program(drop_src: str, move_src: str, dst: str) -> Program:
    return Program(
        f"drop_then_move_{drop_src}_{move_src}_{dst}",
        (
            Clause((Predicate(drop_src, "NONEMPTY"),), Action("DROP_ONE", drop_src)),
            Clause(
                (Predicate(drop_src, "EMPTY"), Predicate(move_src, "NONEMPTY")),
                Action("MOVE_ONE", move_src, dst),
            ),
            Clause(
                (Predicate(drop_src, "EMPTY"), Predicate(move_src, "EMPTY")),
                Action("HALT"),
            ),
        ),
        "drop_then_move",
    )


def move_then_drop_program(move_src: str, dst: str, drop_src: str) -> Program:
    return Program(
        f"move_then_drop_{move_src}_{dst}_{drop_src}",
        (
            Clause(
                (Predicate(move_src, "NONEMPTY"),), Action("MOVE_ONE", move_src, dst)
            ),
            Clause(
                (Predicate(move_src, "EMPTY"), Predicate(drop_src, "NONEMPTY")),
                Action("DROP_ONE", drop_src),
            ),
            Clause(
                (Predicate(move_src, "EMPTY"), Predicate(drop_src, "EMPTY")),
                Action("HALT"),
            ),
        ),
        "move_then_drop",
    )


def switch_drop_then_move_program(first: str, second: str, dst: str) -> Program:
    return Program(
        f"switch_drop_move_{first}_{second}_{dst}",
        (
            Clause((Predicate(first, "NONEMPTY"),), Action("DROP_ONE", first)),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "NONEMPTY")),
                Action("MOVE_ONE", second, dst),
            ),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "EMPTY")),
                Action("HALT"),
            ),
        ),
        "switch_drop_move",
    )


def inspect_second_then_move_program(first: str, second: str, dst: str) -> Program:
    return Program(
        f"inspect_second_move_{first}_{second}_{dst}",
        (
            Clause((Predicate(first, "NONEMPTY"),), Action("MOVE_ONE", first, dst)),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "NONEMPTY")),
                Action("DROP_ONE", second),
            ),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "EMPTY")),
                Action("HALT"),
            ),
        ),
        "inspect_second_move",
    )


def move_move_then_drop_program(
    first: str, second: str, third: str, dst: str
) -> Program:
    return Program(
        f"move_move_drop_{first}_{second}_{third}_{dst}",
        (
            Clause((Predicate(first, "NONEMPTY"),), Action("MOVE_ONE", first, dst)),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "NONEMPTY")),
                Action("MOVE_ONE", second, dst),
            ),
            Clause(
                (
                    Predicate(first, "EMPTY"),
                    Predicate(second, "EMPTY"),
                    Predicate(third, "NONEMPTY"),
                ),
                Action("DROP_ONE", third),
            ),
            Clause(
                (
                    Predicate(first, "EMPTY"),
                    Predicate(second, "EMPTY"),
                    Predicate(third, "EMPTY"),
                ),
                Action("HALT"),
            ),
        ),
        "move_move_then_drop",
    )


def drop_move_then_drop_program(first: str, second: str, third: str) -> Program:
    return Program(
        f"drop_move_drop_{first}_{second}_{third}",
        (
            Clause((Predicate(first, "NONEMPTY"),), Action("DROP_ONE", first)),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "NONEMPTY")),
                Action("MOVE_ONE", second, third),
            ),
            Clause(
                (
                    Predicate(first, "EMPTY"),
                    Predicate(second, "EMPTY"),
                    Predicate(third, "NONEMPTY"),
                ),
                Action("DROP_ONE", third),
            ),
            Clause(
                (
                    Predicate(first, "EMPTY"),
                    Predicate(second, "EMPTY"),
                    Predicate(third, "EMPTY"),
                ),
                Action("HALT"),
            ),
        ),
        "drop_move_then_drop",
    )


def move_two_sources_program(first: str, second: str, dst: str) -> Program:
    return Program(
        f"move_two_sources_{first}_{second}_{dst}",
        (
            Clause((Predicate(first, "NONEMPTY"),), Action("MOVE_ONE", first, dst)),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "NONEMPTY")),
                Action("MOVE_ONE", second, dst),
            ),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "EMPTY")),
                Action("HALT"),
            ),
        ),
        "move_two_sources",
    )


def merge_two_program(variables: Sequence[str]) -> Program:
    first, second, dst = variables[0], variables[1], variables[2]
    return Program(
        "merge_two_heldout",
        (
            Clause((Predicate(first, "NONEMPTY"),), Action("MOVE_ONE", first, dst)),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "NONEMPTY")),
                Action("MOVE_ONE", second, dst),
            ),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "EMPTY")),
                Action("HALT"),
            ),
        ),
        "merge_two",
    )


def merge_three_program(variables: Sequence[str]) -> Program:
    first, second, third, dst = variables[0], variables[1], variables[2], variables[3]
    return Program(
        "merge_three_heldout",
        (
            Clause((Predicate(first, "NONEMPTY"),), Action("MOVE_ONE", first, dst)),
            Clause(
                (Predicate(first, "EMPTY"), Predicate(second, "NONEMPTY")),
                Action("MOVE_ONE", second, dst),
            ),
            Clause(
                (
                    Predicate(first, "EMPTY"),
                    Predicate(second, "EMPTY"),
                    Predicate(third, "NONEMPTY"),
                ),
                Action("MOVE_ONE", third, dst),
            ),
            Clause(
                (
                    Predicate(first, "EMPTY"),
                    Predicate(second, "EMPTY"),
                    Predicate(third, "EMPTY"),
                ),
                Action("HALT"),
            ),
        ),
        "merge_three",
    )


def heldout_predicate_composition_program() -> Program:
    return Program(
        "heldout_empty_a_nonempty_b",
        (
            Clause(
                (Predicate("A", "EMPTY"), Predicate("B", "NONEMPTY")),
                Action("MOVE_ONE", "B", "C"),
            ),
            Clause((Predicate("B", "EMPTY"),), Action("HALT")),
            Clause((Predicate("A", "NONEMPTY"),), Action("DROP_ONE", "A")),
        ),
        "heldout_predicate_composition",
    )


def episode_specs(
    programs: Sequence[Program],
    bindings: Sequence[Binding],
    counts: Sequence[int],
) -> list[EpisodeSpec]:
    specs = []
    for program, binding, count in itertools.product(programs, bindings, counts):
        specs.append(
            EpisodeSpec(
                program,
                binding,
                initial_state_for_program(program, binding, count),
                "eval",
                program.family,
            )
        )
    return specs


def merge_two_specs(
    program: Program, bindings: Sequence[Binding], counts: Sequence[int]
) -> list[EpisodeSpec]:
    specs = []
    for binding in bindings:
        for left in counts:
            for right in counts[: min(6, len(counts))]:
                specs.append(
                    EpisodeSpec(
                        program,
                        binding,
                        merge_state(program, binding, left, right),
                        "eval",
                        "merge_two",
                    )
                )
    return specs


def merge_three_specs(
    program: Program, bindings: Sequence[Binding], counts: Sequence[int]
) -> list[EpisodeSpec]:
    return [
        EpisodeSpec(
            program,
            binding,
            merge_three_state(program, binding, count, count // 2, count % 5),
            "eval",
            "merge_three",
        )
        for binding, count in itertools.product(bindings, counts)
    ]


def order_specs(
    programs: Sequence[Program], bindings: Sequence[Binding], counts: Sequence[int]
) -> list[EpisodeSpec]:
    specs = []
    for program, binding, count in itertools.product(programs, bindings, counts):
        order = tuple(reversed(range(len(program.clauses))))
        specs.append(
            EpisodeSpec(
                program,
                binding,
                initial_state_for_program(program, binding, count),
                "eval",
                "order_invariance",
                clause_order=order,
            )
        )
    return specs


def distractor_specs(
    programs: Sequence[Program], bindings: Sequence[Binding], distractor_count: int
) -> list[EpisodeSpec]:
    return [
        EpisodeSpec(
            program,
            binding,
            initial_state_for_program(program, binding, count),
            "eval",
            f"distractor_{distractor_count}",
            distractor_count=distractor_count,
        )
        for program, binding, count in itertools.product(
            programs, bindings, TRAIN_COUNTS
        )
    ]


def alternate_surface_specs(
    programs: Sequence[Program], bindings: Sequence[Binding]
) -> list[EpisodeSpec]:
    return [
        EpisodeSpec(
            program,
            binding,
            initial_state_for_program(program, binding, count),
            "eval",
            "alternate_surface",
            surface="alternate",
        )
        for program, binding, count in itertools.product(
            programs, bindings, TRAIN_COUNTS
        )
    ]


def ablation_specs(
    programs: Sequence[Program], bindings: Sequence[Binding], variant: str
) -> list[EpisodeSpec]:
    return [
        EpisodeSpec(
            program,
            binding,
            initial_state_for_program(program, binding, count),
            "eval",
            variant,
        )
        for program, binding, count in itertools.product(
            programs, bindings, TRAIN_COUNTS[:4]
        )
    ]


def program_records(
    programs: Sequence[Program],
    bindings: Sequence[Binding],
    counts: Sequence[int],
    *,
    start_index: int,
    include_families: bool,
    target_count: int,
    randomized_order: bool = False,
    distractor_choices: Sequence[int] = (0,),
) -> list[dict[str, Any]]:
    specs = []
    for program, binding, count in itertools.product(programs, bindings, counts):
        specs.append(
            EpisodeSpec(
                program,
                binding,
                initial_state_for_program(program, binding, count),
                "train",
                program.family if include_families else "program",
                clause_order=random_clause_order(program) if randomized_order else None,
                distractor_count=distractor_choices[
                    (count + len(specs)) % len(distractor_choices)
                ],
            )
        )
    rows = records_from_specs(specs, start_index=start_index)
    return repeat_records(rows, target_count)


def records_from_specs(
    specs: Sequence[EpisodeSpec], *, start_index: int
) -> list[dict[str, Any]]:
    rows = []
    for spec in specs:
        rows.extend(trajectory_records(spec, start_index=start_index + len(rows)))
    return rows


def trajectory_records(spec: EpisodeSpec, *, start_index: int) -> list[dict[str, Any]]:
    env = RegisterEnvironment(dict(spec.initial_state))
    rows = []
    for step in range(max_steps(spec.initial_state)):
        action = spec.program.oracle_action(env.state, spec.binding)
        rows.append(
            record(
                start_index + len(rows),
                f"m201.program.{spec.program.family}",
                render_prompt_for_spec(spec, env),
                f"FINAL {action.render()}",
                {
                    "kind": "program_action",
                    "program_family": spec.program.family,
                    "program_name": spec.program.name,
                    "exact_program_hash": exact_program_hash(
                        spec.program, spec.binding
                    ),
                    "normalized_ast_hash": normalized_ast_hash(spec.program),
                    "template_hash": template_hash(spec.program),
                    "clause_hashes": clause_hashes(spec.program),
                    "predicate_action_tuples": predicate_action_tuples(spec.program),
                    "binding_hash": stable_hash(
                        json.dumps(spec.binding.canonical_items())
                    ),
                    "binding": spec.binding.mapping,
                    "state": dict(env.state),
                    "step": step,
                    "variant": spec.variant,
                    "expected_action": action.render(),
                },
            )
        )
        env.step(action)
        if env.invalid:
            raise RuntimeError(f"Oracle invalid for {spec}")
        if env.terminated:
            break
    return rows


def teacher_forced_records(
    specs: Sequence[EpisodeSpec], *, start_index: int
) -> list[dict[str, Any]]:
    rows = []
    for spec in specs:
        env = RegisterEnvironment(dict(spec.initial_state))
        for step in range(max_steps(spec.initial_state)):
            clause_index = spec.program.applicable_clause_index(env.state, spec.binding)
            action = spec.program.clauses[clause_index].action.resolve(spec.binding)
            prompt = (
                f"{render_program(spec.program, spec.binding, env.state, order=spec.clause_order)}\n"
                f"CLS {clause_index}\n{render_binding(spec.binding)}\n{env.observe()}"
            )
            rows.append(
                record(
                    start_index + len(rows),
                    "m201.teacher_forced_clause",
                    prompt,
                    f"FINAL {action.render()}",
                    {
                        "kind": "teacher_forced",
                        "program_family": spec.program.family,
                        "clause_index": clause_index,
                        "state": dict(env.state),
                        "binding": spec.binding.mapping,
                    },
                )
            )
            env.step(action)
            if env.terminated:
                break
    return rows


def render_prompt_for_spec(spec: EpisodeSpec, env: RegisterEnvironment) -> str:
    if spec.variant == "program_removed":
        program_text = "NONE"
    elif spec.variant == "wrong_program":
        program_text = render_program(clear_program("D"), spec.binding, env.state)
    else:
        program_text = render_program(
            spec.program,
            spec.binding,
            env.state,
            order=spec.clause_order,
            distractor_count=spec.distractor_count,
            surface=spec.surface,
        )
    binding = spec.binding
    if spec.variant == "binding_swapped":
        values = list(binding.mapping.values())
        swapped = dict(binding.mapping)
        swapped["A"], swapped["C"] = values[2], values[0]
        binding = Binding(swapped)
    return f"{program_text}\n{render_binding(binding)}\n{env.observe()}"


def render_program(
    program: Program,
    binding: Binding,
    state: dict[str, int],
    *,
    order: Sequence[int] | None = None,
    distractor_count: int = 0,
    surface: Literal["structured", "compact", "alternate"] = "structured",
) -> str:
    indexes = list(order) if order is not None else list(range(len(program.clauses)))
    lines = []
    for visible_index in indexes:
        clause = program.clauses[visible_index]
        if surface == "alternate":
            lines.append(render_alternate_clause(visible_index, clause))
        elif surface == "compact":
            lines.append(render_compact_clause(visible_index, clause))
        else:
            lines.append(render_structured_clause(visible_index, clause))
    for offset in range(distractor_count):
        lines.append(
            render_structured_clause(
                len(indexes) + offset,
                Clause(
                    (Predicate("D", "NONEMPTY"),),
                    Action("MOVE_ONE", "D", "C" if offset % 2 == 0 else "B"),
                ),
            )
        )
    return "\n".join(lines)


def render_structured_clause(index: int, clause: Clause) -> str:
    del index
    parts = []
    for predicate in clause.predicates:
        parts.extend([pred_token(predicate.kind), predicate.variable])
    parts.append(action_token(clause.action.kind))
    if clause.action.source is not None:
        parts.append(clause.action.source)
    if clause.action.destination is not None:
        parts.append(clause.action.destination)
    return " ".join(parts)


def render_compact_clause(index: int, clause: Clause) -> str:
    pred = " ".join(f"{pred_token(p.kind)} {p.variable}" for p in clause.predicates)
    action = render_logical_action(clause.action)
    return f"{index} {pred} -> {action}"


def render_alternate_clause(index: int, clause: Clause) -> str:
    pred = " + ".join(
        f"TEST {p.variable} {'HAS' if p.kind == 'NONEMPTY' else 'NONE'}"
        for p in clause.predicates
    )
    return f"C{index} {pred} => {render_logical_action(clause.action)}"


def render_logical_action(action: Action) -> str:
    if action.kind == "MOVE_ONE":
        return f"M {action.source} {action.destination}"
    if action.kind == "DROP_ONE":
        return f"D {action.source}"
    return "H"


def render_binding(binding: Binding) -> str:
    parts = []
    for variable, register in sorted(binding.mapping.items()):
        parts.extend([variable, register])
    return " ".join(parts)


def render_binding_table(binding: Binding) -> str:
    return " ".join(f"{var} {reg}" for var, reg in sorted(binding.mapping.items()))


def render_state(state: dict[str, int]) -> str:
    return RegisterEnvironment(dict(state)).observe()


def pred_token(kind: str) -> str:
    return "E" if kind == "EMPTY" else "NE"


def action_token(kind: str) -> str:
    return {"MOVE_ONE": "M", "DROP_ONE": "D", "HALT": "H"}[kind]


def parse_action_text(text: str) -> str:
    extracted = normalize_final_answer(extract_final_answer(str(text))).upper()
    compact = re.sub(r"\s+", " ", extracted).strip()
    if re.fullmatch(r"(?:[A-Z] R[0-3]\s*){2,4}", compact):
        return compact
    if match := re.search(r"\bM (R[0-3]) (R[0-3])\b", compact):
        return f"M {match.group(1)} {match.group(2)}"
    if match := re.search(r"\bD (R[0-3])\b", compact):
        return f"D {match.group(1)}"
    if re.search(r"\bH\b", compact):
        return "H"
    if re.search(r"\bTRUE\b", compact):
        return "TRUE"
    if re.search(r"\bFALSE\b", compact):
        return "FALSE"
    if match := re.search(r"\bR[0-3]\b", compact):
        return match.group(0)
    if match := re.search(r"\b[A-Z]\b", compact):
        return match.group(0)
    return compact if compact else "INVALID"


def parse_physical_action(text: str) -> PhysicalAction | None:
    if text == "H":
        return PhysicalAction("HALT")
    if match := re.fullmatch(r"M (R[0-3]) (R[0-3])", text):
        return PhysicalAction("MOVE_ONE", match.group(1), match.group(2))
    if match := re.fullmatch(r"D (R[0-3])", text):
        return PhysicalAction("DROP_ONE", match.group(1))
    return None


def initial_state_for_program(
    program: Program, binding: Binding, primary_count: int
) -> dict[str, int]:
    state = zero_state()
    nonempty_vars = [
        predicate.variable
        for clause in program.clauses
        for predicate in clause.predicates
        if predicate.kind == "NONEMPTY"
    ]
    for index, variable in enumerate(dict.fromkeys(nonempty_vars)):
        state[binding.physical(variable)] = (
            primary_count if index == 0 else primary_count // 2
        )
    return state


def merge_state(
    program: Program, binding: Binding, left: int, right: int
) -> dict[str, int]:
    state = zero_state()
    state[binding.physical("A")] = left
    state[binding.physical("B")] = right
    return state


def merge_three_state(
    program: Program, binding: Binding, first: int, second: int, third: int
) -> dict[str, int]:
    state = zero_state()
    state[binding.physical("A")] = first
    state[binding.physical("B")] = second
    state[binding.physical("C")] = third
    return state


def zero_state() -> dict[str, int]:
    return {register: 0 for register in REGISTERS}


def max_steps(state: dict[str, int]) -> int:
    return sum(state.values()) + 8


def random_clause_order(program: Program) -> tuple[int, ...]:
    indexes = list(range(len(program.clauses)))
    random.Random(SEED + len(program.name)).shuffle(indexes)
    return tuple(indexes)


def validate_mutually_exclusive(program: Program, binding: Binding) -> bool:
    for values in itertools.product((0, 1), repeat=len(REGISTERS)):
        state = dict(zip(REGISTERS, values, strict=True))
        matches = [
            clause for clause in program.clauses if clause.matches(state, binding)
        ]
        if len(matches) != 1:
            return False
    return True


def apply_oracle(
    program: Program, binding: Binding, initial_state: dict[str, int]
) -> dict[str, Any]:
    env = RegisterEnvironment(dict(initial_state))
    actions = []
    for _ in range(max_steps(initial_state)):
        action = program.oracle_action(env.state, binding)
        actions.append(action.render())
        env.step(action)
        if env.invalid or env.terminated:
            break
    return {
        "final_state": dict(env.state),
        "terminated": env.terminated,
        "invalid": env.invalid,
        "actions": actions,
    }


def exact_program_hash(program: Program, binding: Binding) -> str:
    return stable_hash(render_program(program, binding, zero_state()))


def normalized_ast_hash(program: Program) -> str:
    return stable_hash(json.dumps(normalized_ast(program), sort_keys=True))


def template_hash(program: Program) -> str:
    ast = normalized_ast(program)
    for clause in ast:
        for predicate in clause["predicates"]:
            predicate["var"] = "VAR"
        action = clause["action"]
        action["src"] = "VAR" if action.get("src") else None
        action["dst"] = "VAR" if action.get("dst") else None
    return stable_hash(json.dumps(ast, sort_keys=True))


def normalized_ast(program: Program) -> list[dict[str, Any]]:
    variables = {}

    def norm_var(var: str | None) -> str | None:
        if var is None:
            return None
        if var not in variables:
            variables[var] = f"V{len(variables)}"
        return variables[var]

    rows = []
    for clause in program.clauses:
        rows.append(
            {
                "predicates": [
                    {"kind": predicate.kind, "var": norm_var(predicate.variable)}
                    for predicate in clause.predicates
                ],
                "action": {
                    "kind": clause.action.kind,
                    "src": norm_var(clause.action.source),
                    "dst": norm_var(clause.action.destination),
                },
            }
        )
    return rows


def clause_hashes(program: Program) -> list[str]:
    return [
        stable_hash(json.dumps(row, sort_keys=True)) for row in normalized_ast(program)
    ]


def predicate_action_tuples(program: Program) -> list[str]:
    rows = []
    for clause in program.clauses:
        predicate_text = "+".join(f"{p.kind}:{p.variable}" for p in clause.predicates)
        rows.append(f"{predicate_text}->{clause.action.kind}")
    return rows


def program_variables(program: Program) -> set[str]:
    variables = set()
    for clause in program.clauses:
        for predicate in clause.predicates:
            variables.add(predicate.variable)
        if clause.action.source is not None:
            variables.add(clause.action.source)
        if clause.action.destination is not None:
            variables.add(clause.action.destination)
    return variables


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run_primitives() -> None:
    train_path = DATASET_DIR / "train" / "primitives.jsonl"
    run_model(
        "primitive_lm",
        train_path,
        PRIMITIVE_STEPS,
        eval_prefixes=("binding", "predicate", "action", "single_clause", "alpha"),
    )


def run_curriculum() -> None:
    stage1_dir = RUNS_DIR / "curriculum_stage1_lm"
    stage1_checkpoint = final_checkpoint(stage1_dir)
    if stage1_checkpoint is None:
        train_once(
            "curriculum_stage1_lm",
            DATASET_DIR / "train" / "curriculum_stage1.jsonl",
            CURRICULUM_STAGE_STEPS,
        )
        stage1_checkpoint = final_checkpoint(stage1_dir)
    run_model(
        "curriculum_lm",
        DATASET_DIR / "train" / "curriculum_stage2.jsonl",
        FLAT_STEPS,
        init_checkpoint_path=stage1_checkpoint,
    )


def run_model(
    name: str,
    train_path: Path,
    steps: int,
    *,
    eval_prefixes: Sequence[str] | None = None,
    init_checkpoint_path: Path | None = None,
) -> None:
    checkpoint = train_once(
        name, train_path, steps, init_checkpoint_path=init_checkpoint_path
    )
    eval_splits = [
        path
        for path in sorted((DATASET_DIR / "eval").glob("*.jsonl"))
        if eval_prefixes is None or path.stem.startswith(tuple(eval_prefixes))
    ]
    for eval_path in eval_splits:
        eval_one_step(
            checkpoint=checkpoint,
            eval_path=eval_path,
            output_dir=RUNS_DIR / name / "eval_steps" / eval_path.stem,
        )
    if eval_prefixes is None:
        eval_closed_loop(checkpoint=checkpoint, run_name=name)
    prune_intermediate_checkpoints(RUNS_DIR / name)


def train_once(
    name: str,
    train_path: Path,
    steps: int,
    *,
    init_checkpoint_path: Path | None = None,
) -> Path:
    run_dir = RUNS_DIR / name
    checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        result = train_lm(
            TrainConfig(
                train_path=train_path,
                eval_path=DATASET_DIR / "eval" / "program_seen.jsonl",
                tokenizer_path=TOKENIZER_PATH,
                output_dir=run_dir,
                model_config_name=MODEL_CONFIG,
                steps=steps,
                batch_size=BATCH_SIZE,
                sequence_length=SEQUENCE_LENGTH,
                loss_mode=LOSS_MODE,
                learning_rate=LEARNING_RATE,
                grad_clip_norm=GRAD_CLIP_NORM,
                numeric_tokenization=NUMERIC_TOKENIZATION,
                position_encoding=POSITION_ENCODING,
                seed=SEED + len(name),
                eval_every=max(steps // 4, 1),
                eval_batches=20,
                save_every=max(steps // 4, 1),
                cache_dir=ROOT / "cache" / "tokenized_m201",
                init_checkpoint_path=init_checkpoint_path,
            )
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        raise RuntimeError(f"No checkpoint for {name}")
    return checkpoint


def eval_one_step(*, checkpoint: Path, eval_path: Path, output_dir: Path) -> None:
    if (output_dir / "summary.json").exists():
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _ = load_model_for_inference(
        checkpoint_path=checkpoint, tokenizer_path=TOKENIZER_PATH, device=device
    )
    rows = []
    cache: dict[str, str] = {}
    for record_item in _read_jsonl_if_exists(eval_path):
        prompt = str(record_item["prompt"])
        expected = parse_action_text(str(record_item["answer"]))
        candidates = candidates_for_expected(expected)
        if prompt not in cache:
            cache[prompt] = choose_answer(
                model=model,
                tokenizer=tokenizer,
                prompt=prompt,
                candidates=candidates,
                device=device,
            )
        predicted = parse_action_text(f"FINAL {cache[prompt]}")
        rows.append(
            {
                "expected": expected,
                "predicted": predicted,
                "correct": expected == predicted,
                "invalid": predicted == "INVALID",
                "task_type": record_item["task_type"],
                "metadata": record_item.get("metadata", {}),
            }
        )
    _write_jsonl(output_dir / "predictions.jsonl", rows)
    (output_dir / "summary.json").write_text(
        json.dumps(step_summary(rows), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def candidates_for_expected(expected: str) -> list[str]:
    if expected in {"TRUE", "FALSE"}:
        return ["TRUE", "FALSE"]
    if expected in REGISTERS:
        return list(REGISTERS)
    if expected in TRAIN_VARS or expected in ALPHA_VARS:
        return list(TRAIN_VARS + ALPHA_VARS)
    if re.fullmatch(r"([A-Z] R[0-3] ?)+", expected):
        return [expected]
    return all_action_candidates()


def all_action_candidates() -> list[str]:
    return (
        [f"M {src} {dst}" for src, dst in itertools.permutations(REGISTERS, 2)]
        + [f"D {register}" for register in REGISTERS]
        + ["H"]
    )


@torch.no_grad()
def choose_answer(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    prompt: str,
    candidates: Sequence[str],
    device: torch.device,
) -> str:
    scores = {
        candidate: score_answer(
            model=model,
            tokenizer=tokenizer,
            prompt=prompt,
            answer=f"FINAL {candidate}",
            device=device,
        )
        for candidate in candidates
    }
    return max(scores, key=scores.__getitem__)


def score_answer(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    prompt: str,
    answer: str,
    device: torch.device,
) -> float:
    bos_id = required_token_id(tokenizer, BOS_TOKEN)
    eos_id = required_token_id(tokenizer, EOS_TOKEN)
    prefix_ids = [
        bos_id,
        *tokenizer.encode(
            f"{PROMPT_TOKEN}\n{prompt.strip()}\n{ANSWER_TOKEN}\n",
            numeric_tokenization=NUMERIC_TOKENIZATION,
        ),
    ]
    answer_ids = [
        *tokenizer.encode(
            f"{answer.strip()}\n{END_TOKEN}",
            numeric_tokenization=NUMERIC_TOKENIZATION,
        ),
        eos_id,
    ]
    input_ids = torch.tensor(
        [[*prefix_ids, *answer_ids[:-1]]], dtype=torch.long, device=device
    )
    if input_ids.shape[1] > SEQUENCE_LENGTH:
        raise ValueError(f"Scoring input too long: {input_ids.shape[1]}")
    result = model(input_ids)
    logits = result["logits"] if isinstance(result, dict) else result
    log_probs = F.log_softmax(logits[0], dim=-1)
    start = len(prefix_ids) - 1
    scores = [
        log_probs[start + index, token_id].item()
        for index, token_id in enumerate(answer_ids)
    ]
    return sum(scores) / max(len(scores), 1)


def eval_closed_loop(*, checkpoint: Path, run_name: str) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _ = load_model_for_inference(
        checkpoint_path=checkpoint, tokenizer_path=TOKENIZER_PATH, device=device
    )
    specs_by_split = eval_episode_splits()
    for split_name, specs in specs_by_split.items():
        output_dir = RUNS_DIR / run_name / "closed_loop" / split_name
        if (output_dir / "summary.json").exists():
            continue
        rows = []
        cache: dict[str, str] = {}
        for spec in specs:
            oracle = apply_oracle(spec.program, spec.binding, spec.initial_state)
            env = RegisterEnvironment(dict(spec.initial_state))
            actions = []
            for _ in range(max_steps(spec.initial_state)):
                prompt = render_prompt_for_spec(spec, env)
                if prompt not in cache:
                    cache[prompt] = choose_answer(
                        model=model,
                        tokenizer=tokenizer,
                        prompt=prompt,
                        candidates=all_action_candidates(),
                        device=device,
                    )
                predicted = parse_action_text(f"FINAL {cache[prompt]}")
                actions.append(predicted)
                action = parse_physical_action(predicted)
                if action is None:
                    env.invalid = True
                    break
                env.step(action)
                if env.invalid or env.terminated:
                    break
            rows.append(
                {
                    "program_family": spec.program.family,
                    "variant": spec.variant,
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
                }
            )
        write_closed_loop_summary(output_dir, rows)


def eval_episode_splits() -> dict[str, list[EpisodeSpec]]:
    # Rebuild from JSONL metadata would be awkward; the generator is deterministic.
    train_bindings, heldout_bindings = split_bindings(all_bindings(TRAIN_VARS))
    train_programs = grammar_train_programs()
    heldout_programs = grammar_heldout_programs()
    merge_two = merge_two_program(TRAIN_VARS)
    merge_three = merge_three_program(TRAIN_VARS)
    return {
        "program_seen": episode_specs(
            train_programs[:8], train_bindings[:6], TRAIN_COUNTS
        ),
        "program_length_21_50": episode_specs(
            train_programs[:6], train_bindings[:4], OOD_21_50
        ),
        "program_length_51_100": episode_specs(
            train_programs[:4], train_bindings[:3], OOD_51_100[:10]
        ),
        "heldout_binding": episode_specs(
            train_programs[:8], heldout_bindings, TRAIN_COUNTS
        ),
        "heldout_program_instance": episode_specs(
            heldout_programs, train_bindings[:8], TRAIN_COUNTS
        ),
        "heldout_predicate_composition": episode_specs(
            [heldout_predicate_composition_program()], train_bindings[:8], TRAIN_COUNTS
        ),
        "heldout_merge_two_seen": merge_two_specs(
            merge_two, train_bindings[:8], TRAIN_COUNTS
        ),
        "heldout_merge_two_21_50": merge_two_specs(
            merge_two, train_bindings[:4], OOD_21_50
        ),
        "heldout_merge_two_51_100": merge_two_specs(
            merge_two, train_bindings[:3], OOD_51_100[:10]
        ),
        "merge_three": merge_three_specs(merge_three, train_bindings[:4], OOD_11_20),
        "order_invariance": order_specs(
            train_programs[:8], train_bindings[:4], TRAIN_COUNTS
        ),
        "distractor_8": distractor_specs(train_programs[:4], train_bindings[:4], 8),
        "distractor_16": distractor_specs(train_programs[:4], train_bindings[:4], 16),
        "surface_alternate": alternate_surface_specs(
            train_programs[:6], train_bindings[:4]
        ),
        "program_removed": ablation_specs(
            train_programs[:6], train_bindings[:4], "program_removed"
        ),
        "wrong_program": ablation_specs(
            train_programs[:6], train_bindings[:4], "wrong_program"
        ),
        "binding_swapped": ablation_specs(
            train_programs[:6], train_bindings[:4], "binding_swapped"
        ),
    }


def step_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        task_type = str(row["task_type"])
        by_kind.setdefault(task_type, []).append(row)
    return {
        "overall": {
            "count": len(rows),
            "action_accuracy": mean(float(row["correct"]) for row in rows),
            "invalid_action_rate": mean(float(row["invalid"]) for row in rows),
            "final_normalized_exact_match": mean(float(row["correct"]) for row in rows),
        },
        "by_task_type": {
            key: {
                "count": len(values),
                "action_accuracy": mean(float(row["correct"]) for row in values),
                "invalid_action_rate": mean(float(row["invalid"]) for row in values),
            }
            for key, values in sorted(by_kind.items())
        },
    }


def write_closed_loop_summary(output_dir: Path, rows: Sequence[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "episodes.jsonl", rows)
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "overall": {
                    "count": len(rows),
                    "final_state_exact": mean(
                        float(row["final_state_exact"]) for row in rows
                    ),
                    "successful_halt": mean(float(row["terminated"]) for row in rows),
                    "invalid_action_rate": mean(float(row["invalid"]) for row in rows),
                    "avg_steps": mean(float(len(row["actions"])) for row in rows),
                },
                "failure_samples": [
                    row for row in rows if not row["final_state_exact"]
                ][:10],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def analyze_all() -> None:
    analysis = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "remote": remote_environment(),
        "runs": {},
    }
    for run_dir in sorted(RUNS_DIR.glob("*_lm")):
        analysis["runs"][run_dir.name] = analyze_run(run_dir)
    analysis["grid"] = generalization_grid(analysis)
    analysis["decision"] = decision(analysis)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def analyze_run(run_dir: Path) -> dict[str, Any]:
    payload = {
        "train_config": _read_json_if_exists(run_dir / "train_config.json"),
        "metrics": _read_jsonl_if_exists(run_dir / "metrics.jsonl"),
        "eval_steps": {},
        "closed_loop": {},
    }
    for summary_path in sorted((run_dir / "eval_steps").glob("*/summary.json")):
        payload["eval_steps"][summary_path.parent.name] = _read_json(summary_path)
    for summary_path in sorted((run_dir / "closed_loop").glob("*/summary.json")):
        payload["closed_loop"][summary_path.parent.name] = _read_json(summary_path)
    return payload


def generalization_grid(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    run = analysis.get("runs", {}).get("curriculum_lm", {})
    rows = []
    for split in (
        "program_seen",
        "program_length_21_50",
        "program_length_51_100",
        "heldout_binding",
        "heldout_program_instance",
        "heldout_predicate_composition",
        "heldout_merge_two_seen",
        "heldout_merge_two_21_50",
        "heldout_merge_two_51_100",
        "merge_three",
        "order_invariance",
        "distractor_8",
        "distractor_16",
        "surface_alternate",
    ):
        rows.append(
            {
                "split": split,
                "one_step": step_score(run, split),
                "closed_loop": closed_loop_score(run, split),
                "invalid": closed_loop_invalid(run, split),
            }
        )
    return rows


def decision(analysis: dict[str, Any]) -> str:
    primitive = analysis.get("runs", {}).get("primitive_lm", {})
    curriculum = analysis.get("runs", {}).get("curriculum_lm", {})
    binding = step_score(primitive, "binding_heldout")
    predicate = step_score(primitive, "predicate_heldout")
    action = step_score(primitive, "action_heldout_register_pairs")
    heldout_program = closed_loop_score(curriculum, "heldout_program_instance")
    merge_two = closed_loop_score(curriculum, "heldout_merge_two_seen")
    order = closed_loop_score(curriculum, "order_invariance")
    if heldout_program >= 0.95 and merge_two >= 0.95:
        return "OUTCOME A: compositional DSL works for heldout programs and MERGE_TWO."
    if (
        binding >= 0.98
        and predicate >= 0.99
        and action >= 0.98
        and max(heldout_program, merge_two) < 0.90
    ):
        return "OUTCOME B: binding is fixed, but program composition still fails."
    if order >= 0.98 and heldout_program < 0.90:
        return "OUTCOME D: structured curriculum helps locally but is not enough for heldout ASTs."
    return "OUTCOME E: factorized primitives do not compose reliably in this setup."


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    lines = [
        "# M-20.1 Compositional DSL and Variable Binding",
        "",
        "## Remote Environment",
        "",
        remote_lines(analysis),
        "",
        "## M-20 Starting Point",
        "",
        "M-20 solved seen-program trajectory length with external exact state, but failed heldout register/program/template generalization.",
        "",
        "## Structural Leakage Audit",
        "",
        leakage_table(analysis),
        "",
        "## DSL Definition",
        "",
        "Programs use logical variables (`A B C D`), compact structured clauses such as `NE A M A C`, a separate binding line (`A R0 B R1 ...`), a separate physical state line (`R0 NE ...`), and physical actions only after binding resolution.",
        "",
        "## Binding Pretraining",
        "",
        step_table(analysis, "primitive_lm", ["binding_seen", "binding_heldout"]),
        "",
        "## Predicate Semantics",
        "",
        step_table(analysis, "primitive_lm", ["predicate_seen", "predicate_heldout"]),
        "",
        "## Action Semantics",
        "",
        step_table(
            analysis, "primitive_lm", ["action_seen", "action_heldout_register_pairs"]
        ),
        "",
        "## Single-Clause Composition",
        "",
        step_table(analysis, "primitive_lm", ["single_clause_heldout"]),
        "",
        "## Alpha-Renaming",
        "",
        step_table(analysis, "primitive_lm", ["alpha_renaming"]),
        "",
        "## Clause Selection Curriculum",
        "",
        "Clause selection is represented by the primitive and curriculum one-step action decisions; a separate text clause-ID run was not launched because M-20 already showed clause IDs can fit seen programs.",
        "",
        "## Clause Order Invariance",
        "",
        metric_table(analysis, "curriculum_lm", ["order_invariance"]),
        "",
        "## Structured DSL",
        "",
        "The curriculum model uses the structured DSL. The flat model uses the same underlying examples without staged prerequisite training.",
        "",
        "## Program Grammar Pretraining",
        "",
        train_summary(analysis),
        "",
        "## Combination Coverage",
        "",
        coverage_summary(analysis),
        "",
        "## Heldout Register Bindings",
        "",
        metric_table(analysis, "curriculum_lm", ["heldout_binding"]),
        "",
        "## Heldout Program Instances",
        "",
        metric_table(analysis, "curriculum_lm", ["heldout_program_instance"]),
        "",
        "## Heldout Predicate Compositions",
        "",
        metric_table(analysis, "curriculum_lm", ["heldout_predicate_composition"]),
        "",
        "## MERGE_TWO Curriculum",
        "",
        "Training includes DRAIN components, two-clause switching, and non-MERGE multi-clause programs; exact MERGE_TWO AST is held out.",
        "",
        "## Heldout MERGE_TWO",
        "",
        metric_table(
            analysis,
            "curriculum_lm",
            [
                "heldout_merge_two_seen",
                "heldout_merge_two_21_50",
                "heldout_merge_two_51_100",
            ],
        ),
        "",
        "## Teacher-Forced Clause Diagnostic",
        "",
        step_table(analysis, "curriculum_lm", ["teacher_forced_merge_two"]),
        "",
        "## MERGE_THREE if gated",
        "",
        metric_table(analysis, "curriculum_lm", ["merge_three"]),
        "",
        "## Program Ablations",
        "",
        metric_table(
            analysis,
            "curriculum_lm",
            ["program_removed", "wrong_program", "binding_swapped"],
        ),
        "",
        "## Distractor Clauses",
        "",
        metric_table(analysis, "curriculum_lm", ["distractor_8", "distractor_16"]),
        "",
        "## Structural vs Surface Generalization",
        "",
        metric_table(analysis, "curriculum_lm", ["surface_alternate"]),
        "",
        "## Role Embeddings if gated",
        "",
        "Not run; M-20.1 first tests plain token embeddings with explicit structured DSL.",
        "",
        "## Policy Head if gated",
        "",
        "Not run; action generation and binding composition are measured first.",
        "",
        "## Flat vs Compositional Curriculum",
        "",
        compare_table(analysis),
        "",
        "## Final Generalization Grid",
        "",
        grid_table(analysis),
        "",
        "## Multi-Seed if gated",
        "",
        "Exploratory one-seed run only. Multi-seed gate was not reached unless the report metrics exceed heldout-program/MERGE_TWO 0.90.",
        "",
        "## Interpretation",
        "",
        str(analysis.get("decision", "not enough data")),
        "",
        "## Recommended Next Architecture",
        "",
        recommendation(analysis),
        "",
        "## Checks",
        "",
        f"- remote/local ruff + pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{git_commit()}`",
        "",
    ]
    text = "\n".join(lines)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def leakage_table(analysis: dict[str, Any]) -> str:
    audit = analysis.get("manifest", {}).get("structural_audit", {})
    rows = ["| audit | value |", "|---|---:|"]
    for key, value in sorted(audit.items()):
        rows.append(f"| {key} | {value} |")
    return "\n".join(rows)


def step_table(analysis: dict[str, Any], run_name: str, splits: Sequence[str]) -> str:
    run = analysis.get("runs", {}).get(run_name, {})
    rows = ["| split | one-step accuracy | invalid rate |", "|---|---:|---:|"]
    for split in splits:
        item = run.get("eval_steps", {}).get(split, {}).get("overall", {})
        rows.append(
            f"| {split} | {float(item.get('action_accuracy', 0.0)):.4f} | {float(item.get('invalid_action_rate', 0.0)):.4f} |"
        )
    return "\n".join(rows)


def metric_table(analysis: dict[str, Any], run_name: str, splits: Sequence[str]) -> str:
    run = analysis.get("runs", {}).get(run_name, {})
    rows = [
        "| split | one-step | closed-loop final | invalid rate |",
        "|---|---:|---:|---:|",
    ]
    for split in splits:
        rows.append(
            f"| {split} | {step_score(run, split):.4f} | {closed_loop_score(run, split):.4f} | {closed_loop_invalid(run, split):.4f} |"
        )
    return "\n".join(rows)


def train_summary(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    return (
        f"- primitive train examples: `{manifest.get('train_counts', {}).get('primitives', 0)}`\n"
        f"- flat program examples: `{manifest.get('train_counts', {}).get('flat_program', 0)}`\n"
        f"- curriculum stage2 examples: `{manifest.get('train_counts', {}).get('curriculum_stage2', 0)}`"
    )


def coverage_summary(analysis: dict[str, Any]) -> str:
    coverage = analysis.get("manifest", {}).get("coverage", {})
    rows = ["| feature | unique |", "|---|---:|"]
    for key, value in sorted(coverage.items()):
        rows.append(f"| {key} | {value} |")
    return "\n".join(rows)


def compare_table(analysis: dict[str, Any]) -> str:
    rows = ["| split | flat closed-loop | curriculum closed-loop |", "|---|---:|---:|"]
    for split in (
        "program_seen",
        "heldout_binding",
        "heldout_program_instance",
        "heldout_merge_two_seen",
    ):
        rows.append(
            f"| {split} | {closed_loop_score(analysis.get('runs', {}).get('flat_program_lm', {}), split):.4f} | {closed_loop_score(analysis.get('runs', {}).get('curriculum_lm', {}), split):.4f} |"
        )
    return "\n".join(rows)


def grid_table(analysis: dict[str, Any]) -> str:
    rows = ["| split | one-step | closed-loop | invalid |", "|---|---:|---:|---:|"]
    for row in analysis.get("grid", []):
        rows.append(
            f"| {row['split']} | {row['one_step']:.4f} | {row['closed_loop']:.4f} | {row['invalid']:.4f} |"
        )
    return "\n".join(rows)


def recommendation(analysis: dict[str, Any]) -> str:
    decision_text = str(analysis.get("decision", ""))
    if "OUTCOME A" in decision_text:
        return "Adopt structured DSL plus external state as the Stage-1 reasoning architecture."
    if "OUTCOME B" in decision_text:
        return "Keep explicit bindings, but add hierarchical/subprogram execution before broadening tasks."
    if "OUTCOME D" in decision_text:
        return "Continue program-interpreter curriculum and test role embeddings/policy head next."
    return "Current Transformer core did not acquire systematic program interpretation; test explicit hierarchical interpreter or policy-head decomposition."


def step_score(run: dict[str, Any], split: str) -> float:
    return float(
        run.get("eval_steps", {})
        .get(split, {})
        .get("overall", {})
        .get("action_accuracy", 0.0)
    )


def closed_loop_score(run: dict[str, Any], split: str) -> float:
    return float(
        run.get("closed_loop", {})
        .get(split, {})
        .get("overall", {})
        .get("final_state_exact", 0.0)
    )


def closed_loop_invalid(run: dict[str, Any], split: str) -> float:
    return float(
        run.get("closed_loop", {})
        .get(split, {})
        .get("overall", {})
        .get("invalid_action_rate", 0.0)
    )


def build_manifest(
    datasets: dict[str, dict[str, list[dict[str, Any]]]],
    train_programs: Sequence[Program],
    heldout_programs: Sequence[Program],
    merge_two: Program,
) -> dict[str, Any]:
    train_prompts = prompts(datasets["train"])
    eval_prompts = prompts(datasets["eval"])
    train_meta = metadata_rows(datasets["train"])
    eval_meta = metadata_rows(datasets["eval"])
    structural_audit = {
        "exact_prompt_overlap": len(train_prompts & eval_prompts),
        "exact_program_text_overlap": overlap_count(
            train_meta, eval_meta, "exact_program_hash"
        ),
        "normalized_ast_overlap": overlap_count(
            train_meta, eval_meta, "normalized_ast_hash"
        ),
        "clause_overlap": nested_overlap_count(train_meta, eval_meta, "clause_hashes"),
        "predicate_action_tuple_overlap": nested_overlap_count(
            train_meta, eval_meta, "predicate_action_tuples"
        ),
        "logical_variable_pattern_overlap": len(
            {tuple(sorted(program_variables(p))) for p in train_programs}
            & {
                tuple(sorted(program_variables(p)))
                for p in heldout_programs + [merge_two]
            }
        ),
        "physical_binding_overlap": overlap_count(
            train_meta, eval_meta, "binding_hash"
        ),
        "heldout_template_overlap": len(
            {template_hash(p) for p in train_programs}
            & {template_hash(p) for p in heldout_programs + [merge_two]}
        ),
    }
    split_structural_audit = {
        name: structural_overlap(train_meta, metadata_rows({"split": rows}))
        for name, rows in datasets["eval"].items()
    }
    return {
        "kind": "m201_compositional_dsl_variable_binding",
        "seed": SEED,
        "model_config": MODEL_CONFIG,
        "train_counts": {name: len(rows) for name, rows in datasets["train"].items()},
        "eval_counts": {name: len(rows) for name, rows in datasets["eval"].items()},
        "structural_audit": structural_audit,
        "split_structural_audit": split_structural_audit,
        "coverage": coverage_audit(datasets["train"]),
        "prompt_audit": {
            f"{section}/{name}": prompt_audit(rows)
            for section, splits in datasets.items()
            for name, rows in splits.items()
        },
    }


def structural_overlap(
    train_meta: Sequence[dict[str, Any]], eval_meta: Sequence[dict[str, Any]]
) -> dict[str, int]:
    return {
        "exact_program_text_overlap": overlap_count(
            train_meta, eval_meta, "exact_program_hash"
        ),
        "normalized_ast_overlap": overlap_count(
            train_meta, eval_meta, "normalized_ast_hash"
        ),
        "clause_overlap": nested_overlap_count(train_meta, eval_meta, "clause_hashes"),
        "predicate_action_tuple_overlap": nested_overlap_count(
            train_meta, eval_meta, "predicate_action_tuples"
        ),
        "physical_binding_overlap": overlap_count(
            train_meta, eval_meta, "binding_hash"
        ),
        "template_overlap": overlap_count(train_meta, eval_meta, "template_hash"),
    }


def prompts(section: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {str(row["prompt"]) for rows in section.values() for row in rows}


def metadata_rows(section: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [row.get("metadata", {}) for rows in section.values() for row in rows]


def overlap_count(
    left: Sequence[dict[str, Any]], right: Sequence[dict[str, Any]], key: str
) -> int:
    left_values = {row[key] for row in left if key in row}
    right_values = {row[key] for row in right if key in row}
    return len(left_values & right_values)


def nested_overlap_count(
    left: Sequence[dict[str, Any]], right: Sequence[dict[str, Any]], key: str
) -> int:
    left_values = {item for row in left for item in row.get(key, [])}
    right_values = {item for row in right for item in row.get(key, [])}
    return len(left_values & right_values)


def coverage_audit(section: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    metas = metadata_rows(section)
    return {
        "program_families": len(
            {row.get("program_family") for row in metas if row.get("program_family")}
        ),
        "bindings": len(
            {row.get("binding_hash") for row in metas if row.get("binding_hash")}
        ),
        "templates": len(
            {row.get("template_hash") for row in metas if row.get("template_hash")}
        ),
        "predicate_action_tuples": len(
            {item for row in metas for item in row.get("predicate_action_tuples", [])}
        ),
    }


def prompt_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    prompt_values = [str(row["prompt"]) for row in rows]
    return {
        "count": len(prompt_values),
        "forbidden_prompt_count": sum(
            prompt_has_forbidden_marker(prompt) for prompt in prompt_values
        ),
        "contains_program_id": any("PROGRAM_ID" in prompt for prompt in prompt_values),
        "contains_case": any("CASE" in prompt for prompt in prompt_values),
    }


def prompt_has_forbidden_marker(prompt: str) -> bool:
    return any(
        re.search(pattern, prompt, flags=re.IGNORECASE)
        for pattern in FORBIDDEN_PROMPT_PATTERNS
    )


def record(
    index: int, task_type: str, prompt: str, answer: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": f"m201-{index:08d}",
        "task_type": task_type,
        "prompt": prompt,
        "answer": answer,
        "metadata": metadata,
    }


def repeat_records(
    rows: Sequence[dict[str, Any]], target_count: int
) -> list[dict[str, Any]]:
    if not rows:
        return []
    repeated = []
    for index in range(target_count):
        row = dict(rows[index % len(rows)])
        row["id"] = f"{row['id']}-r{index // len(rows):04d}"
        repeated.append(row)
    random.Random(SEED).shuffle(repeated)
    return repeated


def final_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    return checkpoints[-1] if checkpoints else None


def prune_intermediate_checkpoints(run_dir: Path) -> None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    for checkpoint in checkpoints[:-1]:
        checkpoint.unlink(missing_ok=True)


def required_token_id(tokenizer: ByteLevelBpeTokenizer, token: str) -> int:
    token_id = tokenizer.token_to_id(token)
    if token_id is None:
        raise ValueError(f"Missing tokenizer token: {token}")
    return token_id


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            file.write("\n")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> Any:
    return _read_json(path) if path.exists() else {}


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def remote_lines(analysis: dict[str, Any]) -> str:
    remote = analysis.get("remote", {})
    return "\n".join(
        [
            f"- hostname: `{remote.get('hostname', 'unknown')}`",
            f"- GPU: `{remote.get('gpu', 'unknown')}`",
            f"- CUDA visible: `{remote.get('cuda_visible', 'unknown')}`",
            f"- commit SHA: `{remote.get('git_commit', git_commit())}`",
        ]
    )


def remote_environment() -> dict[str, Any]:
    gpu = "unavailable"
    cuda_visible = False
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            gpu = result.stdout.strip()
            cuda_visible = True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {
        "hostname": socket.gethostname(),
        "gpu": gpu,
        "cuda_visible": cuda_visible,
        "git_commit": git_commit(),
        "git_branch": subprocess.getoutput("git branch --show-current"),
    }


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


if __name__ == "__main__":
    main()
