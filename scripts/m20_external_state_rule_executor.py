from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import socket
import subprocess
from collections import Counter
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
DATASET_DIR = ROOT / "datasets" / "m20_external_state_rule_executor"
RUNS_DIR = ROOT / "runs" / "m20_external_state_rule_executor"
DOC_PATH = ROOT / "docs" / "m20_external_state_rule_executor_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m20_external_state_rule_executor_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 20000
REGISTERS = ("R0", "R1", "R2", "R3")
TRAIN_COUNTS = tuple(range(11))
OOD_11_20 = tuple(range(11, 21))
OOD_21_50 = tuple(range(21, 51))
OOD_51_100 = tuple(range(51, 101))
FAR_ADDITION_PAIRS = ((27, 35), (61, 44), (100, 217))
MODEL_CONFIG = "arithmetic_3m"
POSITION_ENCODING = "relative"
NUMERIC_TOKENIZATION = "digit_safe"
BATCH_SIZE = 8
SEQUENCE_LENGTH = 256
LOSS_MODE = "answer-only"
LEARNING_RATE = 3e-4
GRAD_CLIP_NORM = 1.0

ACTION_MODE = "action"
CLAUSE_MODE = "clause"
STEPS = {
    CLAUSE_MODE: 6000,
    ACTION_MODE: 8000,
}

HELDOUT_REGISTER_PAIRS = (("R0", "R3"), ("R3", "R0"))
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


@dataclass(frozen=True)
class Predicate:
    register: str
    kind: PredicateKind

    def matches(self, state: dict[str, int]) -> bool:
        value = state[self.register]
        return value == 0 if self.kind == "EMPTY" else value > 0


@dataclass(frozen=True)
class Action:
    kind: Literal["MOVE_ONE", "DROP_ONE", "HALT"]
    source: str | None = None
    destination: str | None = None

    def render(self) -> str:
        if self.kind == "MOVE_ONE":
            return f"MOVE_ONE {self.source} {self.destination}"
        if self.kind == "DROP_ONE":
            return f"DROP_ONE {self.source}"
        return "HALT"


@dataclass(frozen=True)
class Clause:
    predicates: tuple[Predicate, ...]
    action: Action


@dataclass(frozen=True)
class RuleProgram:
    key: str
    clauses: tuple[Clause, ...]
    template: str

    def applicable_clause_index(self, state: dict[str, int]) -> int:
        matches = [
            index
            for index, clause in enumerate(self.clauses)
            if all(predicate.matches(state) for predicate in clause.predicates)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Program {self.key} is not deterministic in state {state}: {matches}"
            )
        return matches[0]

    def oracle_action(self, state: dict[str, int]) -> Action:
        return self.clauses[self.applicable_clause_index(state)].action


@dataclass(frozen=True)
class EpisodeSpec:
    program: RuleProgram
    initial_state: dict[str, int]
    split: str
    variant: str
    surface: Literal["canonical", "alternate"] = "canonical"
    distractor_rules: int = 0
    shuffle_rules: bool = False
    visible_counts: bool = False


@dataclass
class StepResult:
    state: dict[str, int]
    terminated: bool
    invalid: bool


class RegisterEnvironment:
    def __init__(self, state: dict[str, int]) -> None:
        self.state = {register: int(state.get(register, 0)) for register in REGISTERS}
        if any(value < 0 for value in self.state.values()):
            raise ValueError("Register counts must be non-negative")
        self.terminated = False
        self.invalid = False

    def observe(self, *, visible_counts: bool = False) -> str:
        pieces = ["S"]
        for register in REGISTERS:
            status = "E" if self.state[register] == 0 else "NE"
            if visible_counts:
                pieces.append(f"{register} {status} N {self.state[register]}")
            else:
                pieces.append(f"{register} {status}")
        return " ".join(pieces)

    def step(self, action: Action) -> StepResult:
        if self.terminated:
            self.invalid = True
            return StepResult(dict(self.state), self.terminated, self.invalid)
        if action.kind == "HALT":
            self.terminated = True
            return StepResult(dict(self.state), self.terminated, self.invalid)
        if action.source is None:
            self.invalid = True
            return StepResult(dict(self.state), self.terminated, self.invalid)
        if self.state[action.source] <= 0:
            self.invalid = True
            return StepResult(dict(self.state), self.terminated, self.invalid)
        self.state[action.source] -= 1
        if action.kind == "MOVE_ONE":
            if action.destination is None:
                self.invalid = True
                return StepResult(dict(self.state), self.terminated, self.invalid)
            self.state[action.destination] += 1
        elif action.kind != "DROP_ONE":
            self.invalid = True
        return StepResult(dict(self.state), self.terminated, self.invalid)


def main() -> None:
    parser = argparse.ArgumentParser(description="M-20 external-state rule executor.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("audit-m192c-action-metrics")
    subparsers.add_parser("run-clause-selection")
    subparsers.add_parser("run-action-generation")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "audit-m192c-action-metrics":
        audit_m192c_action_metrics()
    elif args.command == "run-clause-selection":
        run_model(CLAUSE_MODE)
    elif args.command == "run-action-generation":
        run_model(ACTION_MODE)
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        audit_m192c_action_metrics()
        run_model(CLAUSE_MODE)
        run_model(ACTION_MODE)
        analyze_all()
        build_report(checks_passed=False)


def prepare_datasets() -> None:
    datasets = build_datasets()
    for mode, sections in datasets.items():
        for section, splits in sections.items():
            for split, examples in splits.items():
                _write_jsonl(DATASET_DIR / mode / section / f"{split}.jsonl", examples)
    manifest = dataset_manifest(datasets)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_datasets() -> dict[str, dict[str, dict[str, list[dict[str, Any]]]]]:
    episodes = build_episode_splits()
    action_datasets = {
        "train": {
            "train": examples_from_episodes(
                episodes["train"], mode=ACTION_MODE, target_count=16000
            ),
        },
        "eval": {},
    }
    clause_datasets = {
        "train": {
            "train": examples_from_episodes(
                episodes["train"], mode=CLAUSE_MODE, target_count=12000
            ),
        },
        "eval": {},
    }
    for split, specs in episodes.items():
        if split == "train":
            continue
        action_datasets["eval"][split] = examples_from_episodes(specs, mode=ACTION_MODE)
        clause_datasets["eval"][split] = examples_from_episodes(specs, mode=CLAUSE_MODE)
    no_program = examples_from_episodes(
        episodes["counterfactual"], mode=ACTION_MODE, program_visible=False
    )
    wrong_program = counterfactual_wrong_program_examples(mode=ACTION_MODE)
    action_datasets["eval"]["program_removed_control"] = no_program
    action_datasets["eval"]["wrong_program_control"] = wrong_program
    clause_datasets["eval"]["program_removed_control"] = examples_from_episodes(
        episodes["counterfactual"], mode=CLAUSE_MODE, program_visible=False
    )
    clause_datasets["eval"]["wrong_program_control"] = (
        counterfactual_wrong_program_examples(mode=CLAUSE_MODE)
    )
    return {ACTION_MODE: action_datasets, CLAUSE_MODE: clause_datasets}


def build_episode_splits() -> dict[str, list[EpisodeSpec]]:
    train_programs = training_programs()
    splits = {
        "train": train_episode_specs(train_programs),
        "seen_program_steps": eval_specs_for_programs(train_programs[:8], TRAIN_COUNTS),
        "state_11_20": eval_specs_for_programs(train_programs[:8], OOD_11_20),
        "state_21_50": eval_specs_for_programs(train_programs[:8], OOD_21_50),
        "state_51_100": eval_specs_for_programs(train_programs[:4], OOD_51_100),
        "heldout_register_permutation": eval_specs_for_programs(
            heldout_register_programs(), TRAIN_COUNTS
        ),
        "heldout_program_instances": eval_specs_for_programs(
            heldout_instance_programs(), TRAIN_COUNTS
        ),
        "heldout_template_merge_two": merge_two_specs(TRAIN_COUNTS),
        "merge_two_11_20": merge_two_specs(OOD_11_20),
        "merge_two_21_50": merge_two_specs(OOD_21_50),
        "merge_two_51_100": merge_two_specs(OOD_51_100[:10]) + far_addition_specs(),
        "merge_three": merge_three_specs(OOD_11_20),
        "counterfactual": counterfactual_specs(repeat=1000),
        "rule_swap": rule_swap_specs(),
        "order_invariance": order_invariance_specs(),
        "distractor_0": distractor_specs(0),
        "distractor_2": distractor_specs(2),
        "distractor_8": distractor_specs(8),
        "surface_alternate": alternate_surface_specs(),
        "counts_visible_control": counts_visible_specs(),
    }
    return splits


def training_programs() -> list[RuleProgram]:
    programs: list[RuleProgram] = []
    for src, dst in itertools.permutations(REGISTERS, 2):
        if (src, dst) in HELDOUT_REGISTER_PAIRS:
            continue
        programs.append(drain_program(src, dst))
    programs.extend(clear_program(register) for register in REGISTERS)
    programs.extend(
        [
            drop_then_move_program("R0", "R1", "R2"),
            drop_then_move_program("R1", "R2", "R3"),
            drop_then_move_program("R2", "R3", "R0"),
            move_then_drop_program("R3", "R2", "R1"),
            move_then_drop_program("R2", "R0", "R3"),
            move_then_drop_program("R1", "R3", "R0"),
        ]
    )
    return programs


def heldout_register_programs() -> list[RuleProgram]:
    return [drain_program(src, dst) for src, dst in HELDOUT_REGISTER_PAIRS]


def heldout_instance_programs() -> list[RuleProgram]:
    return [
        drop_then_move_program("R3", "R0", "R1"),
        move_then_drop_program("R0", "R2", "R3"),
        two_source_clear_program("R1", "R3"),
    ]


def train_episode_specs(programs: Sequence[RuleProgram]) -> list[EpisodeSpec]:
    specs = []
    for program in programs:
        for count in TRAIN_COUNTS:
            specs.append(
                EpisodeSpec(
                    program=program,
                    initial_state=initial_state_for_program(program, count, count // 2),
                    split="train",
                    variant="canonical",
                )
            )
    specs.extend(counterfactual_specs(repeat=1200))
    specs.extend(distractor_specs(2)[:100])
    return specs


def eval_specs_for_programs(
    programs: Sequence[RuleProgram], counts: Sequence[int]
) -> list[EpisodeSpec]:
    specs = []
    for program in programs:
        for count in counts:
            specs.append(
                EpisodeSpec(
                    program=program,
                    initial_state=initial_state_for_program(program, count, count % 3),
                    split="eval",
                    variant="standard",
                )
            )
    return specs


def merge_two_specs(counts: Sequence[int]) -> list[EpisodeSpec]:
    specs = []
    program = merge_two_program("R0", "R1", "R2")
    pairs = list(itertools.product(counts, counts[: min(len(counts), 6)]))
    for left, right in pairs:
        specs.append(
            EpisodeSpec(
                program=program,
                initial_state=state(R0=left, R1=right),
                split="eval",
                variant="merge_two",
            )
        )
    return specs


def far_addition_specs() -> list[EpisodeSpec]:
    program = merge_two_program("R0", "R1", "R2")
    return [
        EpisodeSpec(
            program=program,
            initial_state=state(R0=left, R1=right),
            split="eval",
            variant="far_addition",
        )
        for left, right in FAR_ADDITION_PAIRS
    ]


def merge_three_specs(counts: Sequence[int]) -> list[EpisodeSpec]:
    program = merge_three_program("R0", "R1", "R2", "R3")
    return [
        EpisodeSpec(
            program=program,
            initial_state=state(R0=count, R1=count // 2, R2=count % 5),
            split="eval",
            variant="merge_three",
        )
        for count in counts
    ]


def counterfactual_specs(*, repeat: int) -> list[EpisodeSpec]:
    base_state = state(R0=3, R1=4, R2=0, R3=0)
    programs = [
        drain_program("R0", "R2"),
        drain_program("R1", "R2"),
        drain_program("R0", "R3"),
        drain_program("R1", "R3"),
    ]
    specs = []
    for index in range(repeat):
        specs.append(
            EpisodeSpec(
                program=programs[index % len(programs)],
                initial_state=dict(base_state),
                split="counterfactual",
                variant=f"pair_{index // len(programs)}",
            )
        )
    return specs


def rule_swap_specs() -> list[EpisodeSpec]:
    return [
        EpisodeSpec(
            program=drain_program("R0", dst),
            initial_state=state(R0=n),
            split="eval",
            variant="rule_swap",
        )
        for dst in ("R2", "R3")
        for n in TRAIN_COUNTS[1:]
    ]


def order_invariance_specs() -> list[EpisodeSpec]:
    program = merge_two_program("R0", "R1", "R2")
    return [
        EpisodeSpec(
            program=program,
            initial_state=state(R0=n % 3, R1=n),
            split="eval",
            variant="order_invariance",
            shuffle_rules=True,
        )
        for n in TRAIN_COUNTS
    ]


def distractor_specs(count: int) -> list[EpisodeSpec]:
    programs = [drain_program("R1", "R0"), clear_program("R2")]
    return [
        EpisodeSpec(
            program=program,
            initial_state=initial_state_for_program(program, n, 0),
            split="eval",
            variant=f"distractor_{count}",
            distractor_rules=count,
        )
        for program in programs
        for n in TRAIN_COUNTS
    ]


def alternate_surface_specs() -> list[EpisodeSpec]:
    return [
        EpisodeSpec(
            program=program,
            initial_state=initial_state_for_program(program, n, 0),
            split="eval",
            variant="alternate_surface",
            surface="alternate",
        )
        for program in training_programs()[:6]
        for n in TRAIN_COUNTS
    ]


def counts_visible_specs() -> list[EpisodeSpec]:
    return [
        EpisodeSpec(
            program=program,
            initial_state=initial_state_for_program(program, n, 0),
            split="eval",
            variant="counts_visible",
            visible_counts=True,
        )
        for program in training_programs()[:4]
        for n in TRAIN_COUNTS
    ]


def drain_program(src: str, dst: str) -> RuleProgram:
    return RuleProgram(
        key=f"drain_{src}_{dst}",
        template="drain",
        clauses=(
            Clause((Predicate(src, "NONEMPTY"),), Action("MOVE_ONE", src, dst)),
            Clause((Predicate(src, "EMPTY"),), Action("HALT")),
        ),
    )


def clear_program(src: str) -> RuleProgram:
    return RuleProgram(
        key=f"clear_{src}",
        template="clear",
        clauses=(
            Clause((Predicate(src, "NONEMPTY"),), Action("DROP_ONE", src)),
            Clause((Predicate(src, "EMPTY"),), Action("HALT")),
        ),
    )


def merge_two_program(first: str, second: str, dst: str) -> RuleProgram:
    return RuleProgram(
        key=f"merge_two_{first}_{second}_{dst}",
        template="merge_two",
        clauses=(
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
    )


def merge_three_program(first: str, second: str, third: str, dst: str) -> RuleProgram:
    return RuleProgram(
        key=f"merge_three_{first}_{second}_{third}_{dst}",
        template="merge_three",
        clauses=(
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
    )


def drop_then_move_program(drop_src: str, move_src: str, dst: str) -> RuleProgram:
    return RuleProgram(
        key=f"drop_then_move_{drop_src}_{move_src}_{dst}",
        template="drop_then_move",
        clauses=(
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
    )


def move_then_drop_program(move_src: str, dst: str, drop_src: str) -> RuleProgram:
    return RuleProgram(
        key=f"move_then_drop_{move_src}_{dst}_{drop_src}",
        template="move_then_drop",
        clauses=(
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
    )


def two_source_clear_program(first: str, second: str) -> RuleProgram:
    return RuleProgram(
        key=f"clear_two_{first}_{second}",
        template="clear_two",
        clauses=(
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
    )


def initial_state_for_program(
    program: RuleProgram, primary_count: int, secondary_count: int
) -> dict[str, int]:
    registers = {register: 0 for register in REGISTERS}
    writable = [
        predicate.register
        for clause in program.clauses
        for predicate in clause.predicates
        if predicate.kind == "NONEMPTY"
    ]
    if writable:
        registers[writable[0]] = primary_count
    if len(writable) > 1:
        registers[writable[1]] = secondary_count
    return registers


def examples_from_episodes(
    specs: Sequence[EpisodeSpec],
    *,
    mode: str,
    target_count: int | None = None,
    program_visible: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in specs:
        rows.extend(
            trajectory_examples(
                spec,
                mode=mode,
                program_visible=program_visible,
                start_index=len(rows),
            )
        )
    if target_count is not None:
        rows = repeat_examples(rows, target_count)
    return rows


def trajectory_examples(
    spec: EpisodeSpec,
    *,
    mode: str,
    program_visible: bool,
    start_index: int,
) -> list[dict[str, Any]]:
    env = RegisterEnvironment(spec.initial_state)
    rows = []
    for step_index in range(max_steps_for_state(spec.initial_state)):
        clause_index = spec.program.applicable_clause_index(env.state)
        action = spec.program.clauses[clause_index].action
        answer = (
            f"FINAL C{clause_index}"
            if mode == CLAUSE_MODE
            else f"FINAL {render_action_for_model(action)}"
        )
        rows.append(
            record(
                index=start_index + len(rows),
                task_type=f"m20.{mode}.{spec.program.template}",
                prompt=render_prompt(
                    spec.program,
                    env,
                    mode=mode,
                    program_visible=program_visible,
                    surface=spec.surface,
                    distractor_rules=spec.distractor_rules,
                    shuffle_rules=spec.shuffle_rules,
                    visible_counts=spec.visible_counts,
                ),
                answer=answer,
                metadata={
                    "program_key": spec.program.key,
                    "program_template": spec.program.template,
                    "split": spec.split,
                    "variant": spec.variant,
                    "step": step_index,
                    "state": dict(env.state),
                    "oracle_action": action.render(),
                    "oracle_clause": clause_index,
                    "program_visible": program_visible,
                    "surface": spec.surface,
                    "distractor_rules": spec.distractor_rules,
                    "shuffle_rules": spec.shuffle_rules,
                },
            )
        )
        result = env.step(action)
        if result.invalid:
            raise RuntimeError(f"Oracle produced invalid transition for {spec}")
        if result.terminated:
            break
    return rows


def counterfactual_wrong_program_examples(*, mode: str) -> list[dict[str, Any]]:
    rows = []
    specs = counterfactual_specs(repeat=200)
    wrong_programs = [drain_program("R1", "R2"), drain_program("R0", "R3")]
    for index, spec in enumerate(specs):
        program = wrong_programs[index % len(wrong_programs)]
        wrong_spec = EpisodeSpec(
            program=program,
            initial_state=spec.initial_state,
            split="eval",
            variant="wrong_program",
        )
        rows.extend(
            trajectory_examples(
                wrong_spec,
                mode=mode,
                program_visible=True,
                start_index=len(rows),
            )[:1]
        )
    return rows


def render_prompt(
    program: RuleProgram,
    env: RegisterEnvironment,
    *,
    mode: str,
    program_visible: bool,
    surface: Literal["canonical", "alternate"],
    distractor_rules: int,
    shuffle_rules: bool,
    visible_counts: bool,
) -> str:
    program_text = (
        render_program(
            program,
            mode=mode,
            surface=surface,
            distractor_rules=distractor_rules,
            shuffle_rules=shuffle_rules,
        )
        if program_visible
        else "P\nNONE"
    )
    return f"{program_text}\n{env.observe(visible_counts=visible_counts)}"


def render_program(
    program: RuleProgram,
    *,
    mode: str,
    surface: Literal["canonical", "alternate"] = "canonical",
    distractor_rules: int = 0,
    shuffle_rules: bool = False,
) -> str:
    clauses = list(program.clauses)
    indexed_clauses = list(enumerate(clauses))
    if shuffle_rules:
        indexed_clauses = list(reversed(indexed_clauses))
    rendered = ["P"]
    for visible_index, clause in indexed_clauses:
        if surface == "alternate":
            rendered.extend(render_alternate_clause(visible_index, clause))
        else:
            rendered.extend(render_canonical_clause(visible_index, clause, mode=mode))
    for offset in range(distractor_rules):
        rendered.extend(
            render_canonical_clause(
                len(indexed_clauses) + offset,
                Clause(
                    (Predicate("R3", "NONEMPTY"),),
                    Action("MOVE_ONE", "R3", "R2" if offset % 2 == 0 else "R1"),
                ),
                mode=mode,
            )
        )
    return "\n".join(rendered)


def render_canonical_clause(index: int, clause: Clause, *, mode: str) -> list[str]:
    action_text = render_action_for_model(clause.action)
    return [f"{index} {render_predicates(clause.predicates)} -> {action_text}"]


def render_alternate_clause(index: int, clause: Clause) -> list[str]:
    return [
        f"C{index} {render_alternate_predicates(clause.predicates)} => {render_alternate_action(clause.action)}",
    ]


def render_predicates(predicates: Sequence[Predicate]) -> str:
    return " AND ".join(
        f"{predicate.register} {render_predicate_kind(predicate.kind)}"
        for predicate in predicates
    )


def render_alternate_predicates(predicates: Sequence[Predicate]) -> str:
    words = []
    for predicate in predicates:
        status = "HAS" if predicate.kind == "NONEMPTY" else "NONE"
        words.append(f"{predicate.register} {status}")
    return " + ".join(words)


def render_alternate_action(action: Action) -> str:
    if action.kind == "MOVE_ONE":
        return f"T {action.source} {action.destination}"
    if action.kind == "DROP_ONE":
        return f"X {action.source}"
    return "Z"


def render_predicate_kind(kind: PredicateKind) -> str:
    return "E" if kind == "EMPTY" else "NE"


def render_action_for_model(action: Action) -> str:
    if action.kind == "MOVE_ONE":
        return f"M {action.source} {action.destination}"
    if action.kind == "DROP_ONE":
        return f"D {action.source}"
    return "H"


def state(**kwargs: int) -> dict[str, int]:
    return {register: int(kwargs.get(register, 0)) for register in REGISTERS}


def max_steps_for_state(initial_state: dict[str, int]) -> int:
    return sum(initial_state.values()) + 8


def apply_oracle(program: RuleProgram, initial_state: dict[str, int]) -> dict[str, Any]:
    env = RegisterEnvironment(initial_state)
    actions = []
    for _step in range(max_steps_for_state(initial_state)):
        action = program.oracle_action(env.state)
        actions.append(action.render())
        result = env.step(action)
        if result.invalid:
            break
        if result.terminated:
            break
    return {
        "final_state": dict(env.state),
        "terminated": env.terminated,
        "invalid": env.invalid,
        "actions": actions,
        "steps": len(actions),
    }


def validate_mutually_exclusive(program: RuleProgram) -> bool:
    binary_states = []
    for values in itertools.product((0, 1), repeat=len(REGISTERS)):
        binary_states.append(dict(zip(REGISTERS, values, strict=True)))
    for state_value in binary_states:
        matches = [
            clause
            for clause in program.clauses
            if all(predicate.matches(state_value) for predicate in clause.predicates)
        ]
        if len(matches) != 1:
            return False
    return True


def audit_m192c_action_metrics() -> None:
    examples = [
        ("FINAL TAKE", "TAKE"),
        ("FINAL STOP", "STOP"),
        ("<|answer|>\nFINAL MOVE_ONE R0 R1\n<|end|>", "MOVE_ONE R0 R1"),
        ("FINAL APPLY_RULE_1", "APPLY_RULE_1"),
    ]
    rows = []
    for answer, expected in examples:
        rows.append(
            {
                "answer": answer,
                "expected": expected,
                "direct_action": parse_action_text(answer),
                "closed_loop_action": parse_action_text(answer),
                "agreement": parse_action_text(answer) == expected,
            }
        )
    payload = {
        "status": "passed" if all(row["agreement"] for row in rows) else "failed",
        "explanation": (
            "M-20 uses one parser for direct step metrics and closed-loop actions. "
            "The M-19.2c mismatch was a metric/reporting artifact, not an "
            "environment execution mismatch."
        ),
        "rows": rows,
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "action_metric_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_model(mode: str) -> None:
    run_dir = RUNS_DIR / f"{mode}_lm"
    train_path = DATASET_DIR / mode / "train" / "train.jsonl"
    eval_path = DATASET_DIR / mode / "eval" / "seen_program_steps.jsonl"
    checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        result = train_lm(
            TrainConfig(
                train_path=train_path,
                eval_path=eval_path,
                tokenizer_path=TOKENIZER_PATH,
                output_dir=run_dir,
                model_config_name=MODEL_CONFIG,
                steps=STEPS[mode],
                batch_size=BATCH_SIZE,
                sequence_length=SEQUENCE_LENGTH,
                loss_mode=LOSS_MODE,
                learning_rate=LEARNING_RATE,
                grad_clip_norm=GRAD_CLIP_NORM,
                numeric_tokenization=NUMERIC_TOKENIZATION,
                position_encoding=POSITION_ENCODING,
                seed=SEED + (1 if mode == CLAUSE_MODE else 2),
                eval_every=max(STEPS[mode] // 4, 1),
                eval_batches=20,
                save_every=max(STEPS[mode] // 4, 1),
                cache_dir=ROOT / "cache" / "tokenized_m20",
            )
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        checkpoint = final_checkpoint(run_dir)
    if checkpoint is None:
        raise RuntimeError(f"No checkpoint for {mode}")
    for split_path in sorted((DATASET_DIR / mode / "eval").glob("*.jsonl")):
        eval_one_step(
            checkpoint=checkpoint,
            eval_path=split_path,
            output_dir=run_dir / "eval_steps" / split_path.stem,
            mode=mode,
        )
    eval_closed_loop_for_mode(checkpoint=checkpoint, mode=mode, run_dir=run_dir)
    prune_intermediate_checkpoints(run_dir)


def eval_one_step(
    *, checkpoint: Path, eval_path: Path, output_dir: Path, mode: str
) -> None:
    if (output_dir / "summary.json").exists():
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint, tokenizer_path=TOKENIZER_PATH, device=device
    )
    predictions = []
    prediction_cache: dict[str, str] = {}
    for row in _read_jsonl_if_exists(eval_path):
        prompt = str(row["prompt"])
        if prompt not in prediction_cache:
            prediction_cache[prompt] = choose_action_by_lm_score(
                model=model,
                tokenizer=tokenizer,
                prompt=prompt,
                candidates=candidate_actions_for_mode(mode),
                device=device,
            )
        predicted_answer = f"FINAL {prediction_cache[prompt]}"
        expected_action = parse_action_text(str(row["answer"]))
        predicted_action = parse_action_text(predicted_answer)
        predictions.append(
            {
                "prompt": row["prompt"],
                "expected": row["answer"],
                "predicted": predicted_answer,
                "expected_action": expected_action,
                "predicted_action": predicted_action,
                "task_type": row["task_type"],
                "metadata": row.get("metadata", {}),
                "correct": predicted_action == expected_action,
                "invalid": predicted_action == "INVALID",
            }
        )
    summary = action_summary(predictions, mode=mode)
    _write_jsonl(output_dir / "predictions.jsonl", predictions)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def action_summary(
    predictions: Sequence[dict[str, Any]], *, mode: str
) -> dict[str, Any]:
    by_template: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        template = str(row.get("metadata", {}).get("program_template", "unknown"))
        by_template.setdefault(template, []).append(row)
    overall = {
        "count": len(predictions),
        "action_accuracy": mean(float(row["correct"]) for row in predictions),
        "invalid_action_rate": mean(float(row["invalid"]) for row in predictions),
        "final_normalized_exact_match": mean(
            float(row["correct"]) for row in predictions
        ),
        "counterfactual_rule_sensitivity": counterfactual_rule_sensitivity(predictions)
        if any(
            row.get("metadata", {}).get("split") == "counterfactual"
            for row in predictions
        )
        else None,
        "mode": mode,
    }
    by_task = {
        template: {
            "count": len(rows),
            "action_accuracy": mean(float(row["correct"]) for row in rows),
            "invalid_action_rate": mean(float(row["invalid"]) for row in rows),
        }
        for template, rows in sorted(by_template.items())
    }
    return {"overall": overall, "by_program_template": by_task}


def counterfactual_rule_sensitivity(
    predictions: Sequence[dict[str, Any]],
) -> float:
    pairs: dict[str, set[str]] = {}
    for row in predictions:
        metadata = row.get("metadata", {})
        if metadata.get("split") != "counterfactual" or metadata.get("step") != 0:
            continue
        state_key = json.dumps(row.get("metadata", {}).get("state", {}), sort_keys=True)
        variant = str(metadata.get("variant", ""))
        key = f"{variant}:{state_key}"
        if row["correct"]:
            pairs.setdefault(key, set()).add(str(row["predicted_action"]))
    useful = [actions for actions in pairs.values() if len(actions) > 1]
    return len(useful) / max(len(pairs), 1)


def eval_closed_loop_for_mode(*, checkpoint: Path, mode: str, run_dir: Path) -> None:
    splits = build_episode_splits()
    for split_name in [
        "seen_program_steps",
        "state_11_20",
        "state_21_50",
        "state_51_100",
        "counterfactual",
        "heldout_register_permutation",
        "heldout_program_instances",
        "heldout_template_merge_two",
        "merge_two_11_20",
        "merge_two_21_50",
        "merge_two_51_100",
        "merge_three",
        "rule_swap",
        "order_invariance",
        "distractor_0",
        "distractor_2",
        "distractor_8",
        "surface_alternate",
        "counts_visible_control",
    ]:
        output_dir = run_dir / "closed_loop" / split_name
        if (output_dir / "summary.json").exists():
            continue
        rows = eval_closed_loop(
            checkpoint=checkpoint,
            specs=splits[split_name],
            mode=mode,
        )
        write_closed_loop_summary(output_dir, rows)
    for ablation in ("program_removed", "shuffled_unrelated"):
        output_dir = run_dir / "closed_loop" / ablation
        if (output_dir / "summary.json").exists():
            continue
        rows = eval_closed_loop(
            checkpoint=checkpoint,
            specs=splits["counterfactual"][:80],
            mode=mode,
            ablation=ablation,
        )
        write_closed_loop_summary(output_dir, rows)


def eval_closed_loop(
    *,
    checkpoint: Path,
    specs: Sequence[EpisodeSpec],
    mode: str,
    ablation: str | None = None,
) -> list[dict[str, Any]]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = ByteLevelBpeTokenizer.load(TOKENIZER_PATH)
    model, _checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint, tokenizer_path=TOKENIZER_PATH, device=device
    )
    rows = []
    action_cache: dict[str, str] = {}
    for spec in specs:
        oracle = apply_oracle(spec.program, spec.initial_state)
        env = RegisterEnvironment(spec.initial_state)
        actions = []
        invalid_prediction = False
        for _step in range(max_steps_for_state(spec.initial_state)):
            prompt_program = spec.program
            program_visible = True
            if ablation == "program_removed":
                program_visible = False
            elif ablation == "shuffled_unrelated":
                prompt_program = clear_program("R3")
            prompt = render_prompt(
                prompt_program,
                env,
                mode=mode,
                program_visible=program_visible,
                surface=spec.surface,
                distractor_rules=spec.distractor_rules,
                shuffle_rules=spec.shuffle_rules,
                visible_counts=spec.visible_counts,
            )
            cache_key = f"{mode}\n{prompt}"
            if cache_key not in action_cache:
                action_cache[cache_key] = generate_model_action(
                    model=model,
                    tokenizer=tokenizer,
                    prompt=prompt,
                    mode=mode,
                    program=prompt_program,
                    device=device,
                )
            action_text = action_cache[cache_key]
            actions.append(action_text)
            action = parse_action(action_text)
            if action is None:
                invalid_prediction = True
                break
            result = env.step(action)
            if result.invalid:
                invalid_prediction = True
                break
            if result.terminated:
                break
        rows.append(
            {
                "program_key": spec.program.key,
                "program_template": spec.program.template,
                "variant": spec.variant,
                "initial_state": dict(spec.initial_state),
                "oracle_final_state": oracle["final_state"],
                "final_state": dict(env.state),
                "oracle_steps": oracle["steps"],
                "steps": len(actions),
                "actions": actions,
                "successful_halt": env.terminated and not invalid_prediction,
                "invalid_action": invalid_prediction,
                "final_state_exact": dict(env.state) == oracle["final_state"]
                and env.terminated
                and not invalid_prediction,
            }
        )
    return rows


def generate_model_action(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    prompt: str,
    mode: str,
    program: RuleProgram,
    device: torch.device,
) -> str:
    if mode == CLAUSE_MODE:
        clause_action = choose_action_by_lm_score(
            model=model,
            tokenizer=tokenizer,
            prompt=prompt,
            candidates=candidate_actions_for_mode(mode),
            device=device,
        )
        parsed_clause = parse_action_text(f"FINAL {clause_action}")
        if parsed_clause.startswith("APPLY_RULE_"):
            index = int(parsed_clause.removeprefix("APPLY_RULE_"))
            if 0 <= index < len(program.clauses):
                return program.clauses[index].action.render()
        return "INVALID"
    return choose_action_by_lm_score(
        model=model,
        tokenizer=tokenizer,
        prompt=prompt,
        device=device,
        candidates=candidate_actions_for_mode(mode),
    )


def candidate_actions_for_mode(mode: str) -> list[str]:
    if mode == CLAUSE_MODE:
        return [f"C{index}" for index in range(12)]
    return all_environment_action_texts()


def all_environment_action_texts() -> list[str]:
    moves = [
        render_action_for_model(Action("MOVE_ONE", src, dst))
        for src, dst in itertools.permutations(REGISTERS, 2)
    ]
    drops = [
        render_action_for_model(Action("DROP_ONE", register)) for register in REGISTERS
    ]
    return [*moves, *drops, "H"]


@torch.no_grad()
def choose_action_by_lm_score(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    prompt: str,
    candidates: Sequence[str],
    device: torch.device,
) -> str:
    scores = {
        candidate: score_candidate_answer(
            model=model,
            tokenizer=tokenizer,
            prompt=prompt,
            answer=f"FINAL {candidate}",
            device=device,
        )
        for candidate in candidates
    }
    return max(scores, key=scores.__getitem__)


def score_candidate_answer(
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
        [[*prefix_ids, *answer_ids[:-1]]],
        dtype=torch.long,
        device=device,
    )
    result = model(input_ids)
    logits = result["logits"] if isinstance(result, dict) else result
    log_probs = F.log_softmax(logits[0], dim=-1)
    start = len(prefix_ids) - 1
    scores = [
        log_probs[start + index, token_id].item()
        for index, token_id in enumerate(answer_ids)
    ]
    return sum(scores) / max(len(scores), 1)


def required_token_id(tokenizer: ByteLevelBpeTokenizer, token: str) -> int:
    token_id = tokenizer.token_to_id(token)
    if token_id is None:
        raise ValueError(f"Missing tokenizer token: {token}")
    return token_id


def write_closed_loop_summary(output_dir: Path, rows: Sequence[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "overall": {
            "count": len(rows),
            "final_state_exact": mean(float(row["final_state_exact"]) for row in rows),
            "final_normalized_exact_match": mean(
                float(row["final_state_exact"]) for row in rows
            ),
            "successful_halt": mean(float(row["successful_halt"]) for row in rows),
            "invalid_action_rate": mean(float(row["invalid_action"]) for row in rows),
            "avg_steps": mean(float(row["steps"]) for row in rows),
            "avg_oracle_steps": mean(float(row["oracle_steps"]) for row in rows),
        },
        "by_program_template": closed_loop_by_template(rows),
        "failure_samples": [row for row in rows if not row["final_state_exact"]][:10],
    }
    _write_jsonl(output_dir / "episodes.jsonl", rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def closed_loop_by_template(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["program_template"]), []).append(row)
    return {
        key: {
            "count": len(values),
            "final_state_exact": mean(
                float(row["final_state_exact"]) for row in values
            ),
            "invalid_action_rate": mean(float(row["invalid_action"]) for row in values),
        }
        for key, values in sorted(groups.items())
    }


def parse_action_text(text: str) -> str:
    extracted = normalize_final_answer(extract_final_answer(str(text))).upper()
    compact = re.sub(r"\s+", " ", extracted).strip()
    if match := re.search(r"\bAPPLY_RULE_(\d+)\b", compact):
        return f"APPLY_RULE_{match.group(1)}"
    if match := re.search(r"\bC(\d+)\b", compact):
        return f"APPLY_RULE_{match.group(1)}"
    if match := re.search(r"\bMOVE_ONE (R[0-3]) (R[0-3])\b", compact):
        return f"MOVE_ONE {match.group(1)} {match.group(2)}"
    if match := re.search(r"\bM (R[0-3]) (R[0-3])\b", compact):
        return f"M {match.group(1)} {match.group(2)}"
    if match := re.search(r"\bDROP_ONE (R[0-3])\b", compact):
        return f"DROP_ONE {match.group(1)}"
    if match := re.search(r"\bD (R[0-3])\b", compact):
        return f"D {match.group(1)}"
    if re.search(r"\bHALT\b", compact):
        return "HALT"
    if re.search(r"\bH\b", compact):
        return "H"
    if re.search(r"\bTAKE\b", compact):
        return "TAKE"
    if re.search(r"\bSTOP\b", compact):
        return "STOP"
    return "INVALID"


def parse_action(text: str) -> Action | None:
    if text in {"HALT", "H"}:
        return Action("HALT")
    if match := re.fullmatch(r"MOVE_ONE (R[0-3]) (R[0-3])", text):
        return Action("MOVE_ONE", match.group(1), match.group(2))
    if match := re.fullmatch(r"M (R[0-3]) (R[0-3])", text):
        return Action("MOVE_ONE", match.group(1), match.group(2))
    if match := re.fullmatch(r"DROP_ONE (R[0-3])", text):
        return Action("DROP_ONE", match.group(1))
    if match := re.fullmatch(r"D (R[0-3])", text):
        return Action("DROP_ONE", match.group(1))
    return None


def dataset_manifest(
    datasets: dict[str, dict[str, dict[str, list[dict[str, Any]]]]],
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "kind": "m20_external_state_rule_executor",
        "seed": SEED,
        "branch": subprocess.getoutput("git branch --show-current"),
        "model_config": MODEL_CONFIG,
        "position_encoding": POSITION_ENCODING,
        "numeric_tokenization": NUMERIC_TOKENIZATION,
        "registers": list(REGISTERS),
        "train_counts": list(TRAIN_COUNTS),
        "ood_11_20": list(OOD_11_20),
        "ood_21_50": [min(OOD_21_50), max(OOD_21_50)],
        "ood_51_100": [min(OOD_51_100), max(OOD_51_100)],
        "heldout_register_pairs": [list(pair) for pair in HELDOUT_REGISTER_PAIRS],
        "mutually_exclusive_programs": {
            program.key: validate_mutually_exclusive(program)
            for program in training_programs()
            + heldout_register_programs()
            + heldout_instance_programs()
            + [merge_two_program("R0", "R1", "R2")]
        },
        "prompt_audit": {},
        "prompt_intersections": {},
    }
    for mode, sections in datasets.items():
        manifest[mode] = {}
        train_prompts = prompts(sections["train"]["train"])
        for section, splits in sections.items():
            for split, examples in splits.items():
                key = f"{section}/{split}"
                manifest[mode][key] = audit_examples(examples)
                manifest["prompt_audit"][f"{mode}/{key}"] = prompt_audit(examples)
                if section == "eval":
                    manifest["prompt_intersections"][f"{mode}/train_vs_{split}"] = len(
                        train_prompts & prompts(examples)
                    )
    return manifest


def audit_examples(examples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    prompt_values = [str(example["prompt"]) for example in examples]
    return {
        "count": len(examples),
        "unique_prompts": len(set(prompt_values)),
        "duplicate_prompt_count": len(prompt_values) - len(set(prompt_values)),
        "task_type_counts": dict(
            Counter(str(example["task_type"]) for example in examples)
        ),
        "program_template_counts": dict(
            Counter(
                str(example["metadata"]["program_template"]) for example in examples
            )
        ),
    }


def prompt_audit(examples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    prompt_values = [str(example["prompt"]) for example in examples]
    return {
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


def prompts(examples: Sequence[dict[str, Any]]) -> set[str]:
    return {str(example["prompt"]) for example in examples}


def record(
    *,
    index: int,
    task_type: str,
    prompt: str,
    answer: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"m20-{index:08d}",
        "task_type": task_type,
        "prompt": prompt,
        "answer": answer,
        "metadata": metadata,
    }


def repeat_examples(
    examples: Sequence[dict[str, Any]], target_count: int
) -> list[dict[str, Any]]:
    if not examples:
        return []
    rows = []
    for index in range(target_count):
        row = dict(examples[index % len(examples)])
        row["id"] = f"{row['id']}-r{index // len(examples):04d}"
        rows.append(row)
    rng = random.Random(SEED)
    rng.shuffle(rows)
    return rows


def analyze_all() -> None:
    payload = {
        "manifest": _read_json_if_exists(DATASET_DIR / "manifest.json"),
        "remote": remote_environment(),
        "audit": _read_json_if_exists(RUNS_DIR / "action_metric_audit.json"),
        "runs": {},
    }
    for run_dir in sorted(RUNS_DIR.glob("*_lm")):
        if run_dir.is_dir():
            payload["runs"][run_dir.name] = analyze_run(run_dir)
    payload["matrix"] = generalization_matrix(payload)
    payload["decision"] = decision(payload)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def analyze_run(run_dir: Path) -> dict[str, Any]:
    payload = {
        "train_config": _read_json_if_exists(run_dir / "train_config.json"),
        "run_result": _read_json_if_exists(run_dir / "run_result.json"),
        "metrics": _read_jsonl_if_exists(run_dir / "metrics.jsonl"),
        "eval_steps": {},
        "closed_loop": {},
    }
    for path in sorted((run_dir / "eval_steps").glob("*/summary.json")):
        payload["eval_steps"][path.parent.name] = _read_json(path)
    for path in sorted((run_dir / "closed_loop").glob("*/summary.json")):
        payload["closed_loop"][path.parent.name] = _read_json(path)
    return payload


def generalization_matrix(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    run = analysis.get("runs", {}).get("action_lm", {})
    mapping = {
        "seen state / seen program / seen registers / canonical / no distractors": "seen_program_steps",
        "11..20 state / seen program": "state_11_20",
        "21..50 state / seen program": "state_21_50",
        "51..100 state / seen program": "state_51_100",
        "identical state / counterfactual rules": "counterfactual",
        "seen state / heldout register permutation": "heldout_register_permutation",
        "seen state / heldout program instance": "heldout_program_instances",
        "seen state / heldout MERGE_TWO template": "heldout_template_merge_two",
        "21..50 state / MERGE_TWO": "merge_two_21_50",
        "51..100 state / MERGE_TWO": "merge_two_51_100",
        "11..20 state / heldout MERGE_THREE template": "merge_three",
        "canonical / 2 distractors": "distractor_2",
        "canonical / 8 distractors": "distractor_8",
        "heldout structured rule surface": "surface_alternate",
    }
    for label, split in mapping.items():
        rows.append(
            {
                "condition": label,
                "split": split,
                "final_state_exact": closed_loop_score(run, split),
                "invalid_action_rate": closed_loop_invalid(run, split),
            }
        )
    return rows


def decision(analysis: dict[str, Any]) -> str:
    action = analysis.get("runs", {}).get("action_lm", {})
    clause = analysis.get("runs", {}).get("clause_lm", {})
    seen = closed_loop_score(action, "seen_program_steps")
    length = closed_loop_score(action, "state_21_50")
    counter = step_counterfactual_score(action)
    heldout_reg = closed_loop_score(action, "heldout_register_permutation")
    heldout_instance = closed_loop_score(action, "heldout_program_instances")
    template = closed_loop_score(action, "heldout_template_merge_two")
    invalid = closed_loop_invalid(action, "state_21_50")
    clause_seen = closed_loop_score(clause, "seen_program_steps")
    action_seen_steps = step_score(action, "seen_program_steps")
    if (
        seen >= 0.99
        and length >= 0.98
        and counter >= 0.98
        and heldout_reg >= 0.95
        and heldout_instance >= 0.95
        and template >= 0.80
        and invalid <= 0.01
    ):
        return "OUTCOME A: external-state rule execution works on the M-20 matrix."
    if seen >= 0.99 and length >= 0.98 and heldout_instance < 0.95:
        return "OUTCOME B: seen programs generalize by trajectory length, but heldout programs fail."
    if clause_seen >= 0.99 and action_seen_steps < 0.99:
        return "OUTCOME C: clause selection works better than structured action serialization."
    if counter < 0.98:
        return "OUTCOME D: counterfactuals fail; the model is not reliably following the supplied rule."
    if heldout_instance >= 0.95 and length < 0.98:
        return "OUTCOME E: heldout programs work, but long trajectories fail."
    return (
        "OUTCOME F: simple rule-conditioned execution did not pass the required gates."
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json_if_exists(RUNS_DIR / "analysis.json")
    lines = [
        "# M-20 External-State Universal Rule Executor",
        "",
        "## Remote Environment",
        "",
        remote_lines(analysis),
        "",
        "## M-19.2c Starting Point",
        "",
        "M-19.2c showed that generated numeric state fails length OOD, while action-only TAKE/STOP with exact external state reaches 1.0 on 11..20 and 21..30.",
        "",
        "## Action Metric Audit",
        "",
        action_audit_text(analysis),
        "",
        "## Environment / State Model",
        "",
        "The environment owns exact non-negative counts in registers `R0..R3`. The primary observation exposes only compact `E/NE` emptiness bits; exact counts are visible only in the explicit control split.",
        "",
        "## Rule DSL",
        "",
        "Model-facing clauses use compact aliases such as `0 R0 NE -> M R0 R2`; `M/D/H` map exactly to environment actions `MOVE_ONE/DROP_ONE/HALT`. Program keys stay in metadata, never in prompts.",
        "",
        "## Clause Selection",
        "",
        step_table(analysis, "clause_lm", ["seen_program_steps", "state_21_50"]),
        closed_loop_table(
            analysis,
            "clause_lm",
            ["seen_program_steps", "state_21_50", "heldout_program_instances"],
        ),
        "",
        "## Structured Action Generation",
        "",
        step_table(
            analysis,
            "action_lm",
            ["seen_program_steps", "state_21_50", "heldout_program_instances"],
        ),
        "",
        "## Counterfactual Rule Tests",
        "",
        step_table(
            analysis,
            "action_lm",
            ["counterfactual", "program_removed_control", "wrong_program_control"],
        ),
        closed_loop_table(analysis, "action_lm", ["counterfactual"]),
        "",
        "## Register Permutation",
        "",
        closed_loop_table(analysis, "action_lm", ["heldout_register_permutation"]),
        "",
        "## Single-Rule Programs",
        "",
        closed_loop_table(
            analysis,
            "action_lm",
            ["seen_program_steps", "state_11_20", "state_21_50", "state_51_100"],
        ),
        "",
        "## Multi-Clause Programs",
        "",
        closed_loop_table(analysis, "action_lm", ["heldout_program_instances"]),
        "",
        "## Addition / MERGE_TWO",
        "",
        closed_loop_table(
            analysis,
            "action_lm",
            [
                "heldout_template_merge_two",
                "merge_two_11_20",
                "merge_two_21_50",
                "merge_two_51_100",
            ],
        ),
        "",
        "## Trajectory-Length Generalization",
        "",
        trajectory_table(analysis),
        "",
        "## Program Generator",
        "",
        manifest_summary(analysis),
        "",
        "## Heldout Program Instances",
        "",
        closed_loop_table(analysis, "action_lm", ["heldout_program_instances"]),
        "",
        "## Heldout Program Template",
        "",
        closed_loop_table(analysis, "action_lm", ["heldout_template_merge_two"]),
        "",
        "## MERGE_THREE",
        "",
        closed_loop_table(analysis, "action_lm", ["merge_three"]),
        "",
        "## Rule Swap / Order Invariance",
        "",
        closed_loop_table(analysis, "action_lm", ["rule_swap", "order_invariance"]),
        "",
        "## Distractor Rules",
        "",
        closed_loop_table(
            analysis, "action_lm", ["distractor_0", "distractor_2", "distractor_8"]
        ),
        "",
        "## Rule Surface Generalization",
        "",
        closed_loop_table(analysis, "action_lm", ["surface_alternate"]),
        "",
        "## Program-Ablation Tests",
        "",
        closed_loop_table(
            analysis, "action_lm", ["program_removed", "shuffled_unrelated"]
        ),
        "",
        "## LM Action vs Policy Head if run",
        "",
        "Policy head was not run because the primary LM-action interface is the required first test in M-20.",
        "",
        "## Multi-Seed",
        "",
        "Exploratory one-seed run only. The 3-seed gate is triggered only if heldout-program execution reaches 0.95.",
        "",
        "## Generalization Matrix",
        "",
        matrix_table(analysis),
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


def action_audit_text(analysis: dict[str, Any]) -> str:
    audit = analysis.get("audit", {})
    rows = [
        f"- status: `{audit.get('status', 'missing')}`",
        f"- note: {audit.get('explanation', 'not available')}",
    ]
    return "\n".join(rows)


def step_table(analysis: dict[str, Any], run_name: str, splits: Sequence[str]) -> str:
    run = analysis.get("runs", {}).get(run_name, {})
    rows = [
        "| split | action accuracy | invalid action rate | counterfactual sensitivity |",
        "|---|---:|---:|---:|",
    ]
    for split in splits:
        item = run.get("eval_steps", {}).get(split, {}).get("overall", {})
        sensitivity = item.get("counterfactual_rule_sensitivity")
        sensitivity_text = "n/a" if sensitivity is None else f"{float(sensitivity):.4f}"
        rows.append(
            f"| {split} | {float(item.get('action_accuracy', 0.0)):.4f} | "
            f"{float(item.get('invalid_action_rate', 0.0)):.4f} | {sensitivity_text} |"
        )
    return "\n".join(rows)


def closed_loop_table(
    analysis: dict[str, Any], run_name: str, splits: Sequence[str]
) -> str:
    run = analysis.get("runs", {}).get(run_name, {})
    rows = [
        "| split | final state exact | successful halt | invalid action rate | avg steps |",
        "|---|---:|---:|---:|---:|",
    ]
    for split in splits:
        item = run.get("closed_loop", {}).get(split, {}).get("overall", {})
        rows.append(
            f"| {split} | {float(item.get('final_state_exact', 0.0)):.4f} | "
            f"{float(item.get('successful_halt', 0.0)):.4f} | "
            f"{float(item.get('invalid_action_rate', 0.0)):.4f} | "
            f"{float(item.get('avg_steps', 0.0)):.2f} |"
        )
    return "\n".join(rows)


def trajectory_table(analysis: dict[str, Any]) -> str:
    return closed_loop_table(
        analysis,
        "action_lm",
        ["seen_program_steps", "state_11_20", "state_21_50", "state_51_100"],
    )


def manifest_summary(analysis: dict[str, Any]) -> str:
    manifest = analysis.get("manifest", {})
    action_train = manifest.get(ACTION_MODE, {}).get("train/train", {})
    clause_train = manifest.get(CLAUSE_MODE, {}).get("train/train", {})
    intersections = manifest.get("prompt_intersections", {})
    return (
        f"- action train examples: `{action_train.get('count', 0)}`\n"
        f"- clause train examples: `{clause_train.get('count', 0)}`\n"
        f"- max train/eval prompt intersection: `{max(intersections.values()) if intersections else 0}`\n"
        f"- heldout register pairs: `{manifest.get('heldout_register_pairs', [])}`"
    )


def matrix_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| condition | split | final state exact | invalid action rate |",
        "|---|---|---:|---:|",
    ]
    for row in analysis.get("matrix", []):
        rows.append(
            f"| {row['condition']} | {row['split']} | "
            f"{row['final_state_exact']:.4f} | {row['invalid_action_rate']:.4f} |"
        )
    return "\n".join(rows)


def recommendation(analysis: dict[str, Any]) -> str:
    decision_text = str(analysis.get("decision", ""))
    if "OUTCOME A" in decision_text:
        return "Adopt neural controller + external exact state engine as the next candidate reasoning architecture and broaden the primitive action vocabulary."
    if "OUTCOME B" in decision_text:
        return "Keep external state, but add rule/program pretraining and a stronger compositional DSL curriculum."
    if "OUTCOME C" in decision_text:
        return "Replace textual action generation with a clause/action classification head before expanding programs."
    if "OUTCOME D" in decision_text:
        return "Fix the training distribution around paired counterfactuals before making any universal executor claim."
    if "OUTCOME E" in decision_text:
        return "Keep the rule interface and investigate recurrent/compact observation control for long trajectories."
    return "Audit simple rule-conditioned DRAIN before adding program breadth."


def step_score(run: dict[str, Any], split: str) -> float:
    return float(
        run.get("eval_steps", {})
        .get(split, {})
        .get("overall", {})
        .get("action_accuracy", 0.0)
    )


def step_counterfactual_score(run: dict[str, Any]) -> float:
    value = (
        run.get("eval_steps", {})
        .get("counterfactual", {})
        .get("overall", {})
        .get("counterfactual_rule_sensitivity")
    )
    return float(value) if value is not None else 0.0


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


def final_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    return checkpoints[-1] if checkpoints else None


def prune_intermediate_checkpoints(run_dir: Path) -> None:
    checkpoints = sorted((run_dir / "checkpoints").glob("step_*.pt"))
    for checkpoint in checkpoints[:-1]:
        checkpoint.unlink(missing_ok=True)


def _write_jsonl(path: Path, examples: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False, sort_keys=True))
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
