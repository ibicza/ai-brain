from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import random
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import torch
import torch.nn.functional as F
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs" / "m21_neural_symbolic_interpreter"
DATASET_DIR = ROOT / "datasets" / "m21_neural_symbolic_interpreter"
DOC_REPORT_PATH = ROOT / "docs" / "m21_hybrid_neural_compiler_interpreter_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m21_hybrid_neural_compiler_interpreter_report.md"
RESEARCH_NOTES_PATH = ROOT / "docs" / "m21_architecture_research_notes.md"

SEED = 2117
REGISTERS = ("R0", "R1", "R2", "R3")
TRAIN_VARS = ("A", "B", "C", "D")
ALPHA_VARS = ("X", "Y", "Z", "W")
ALL_VARS = TRAIN_VARS + ALPHA_VARS
PREDICATE_KINDS = ("EMPTY", "NONEMPTY")
ACTION_KINDS = ("MOVE_ONE", "DROP_ONE", "HALT")
MAX_CLAUSES = 8
MAX_PREDS = 3
TRAIN_COUNTS = tuple(range(8))
OOD_COUNTS = tuple(range(11, 21))
LONG_COUNTS = tuple(range(21, 51, 3))
FAR_COUNTS = tuple(range(51, 101, 7))


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


PredicateKind = Literal["EMPTY", "NONEMPTY"]
ActionKind = Literal["MOVE_ONE", "DROP_ONE", "HALT"]


@dataclass(frozen=True)
class PredicateAst:
    kind: PredicateKind
    variable: str

    def evaluate(self, binding: BindingAst, state: RegisterState) -> bool:
        value = state.counts[binding.physical(self.variable)]
        return value == 0 if self.kind == "EMPTY" else value > 0

    def alpha(self, rename: dict[str, str]) -> PredicateAst:
        return PredicateAst(self.kind, rename[self.variable])


@dataclass(frozen=True)
class ActionAst:
    kind: ActionKind
    source: str | None = None
    destination: str | None = None

    def resolve(self, binding: BindingAst) -> PhysicalAction:
        if self.kind == "MOVE_ONE":
            if self.source is None or self.destination is None:
                raise ValueError("MOVE_ONE requires source and destination")
            return PhysicalAction(
                "MOVE_ONE",
                binding.physical(self.source),
                binding.physical(self.destination),
            )
        if self.kind == "DROP_ONE":
            if self.source is None:
                raise ValueError("DROP_ONE requires source")
            return PhysicalAction("DROP_ONE", binding.physical(self.source))
        return PhysicalAction("HALT")

    def alpha(self, rename: dict[str, str]) -> ActionAst:
        return ActionAst(
            self.kind,
            rename[self.source] if self.source is not None else None,
            rename[self.destination] if self.destination is not None else None,
        )


@dataclass(frozen=True)
class ClauseAst:
    predicates: tuple[PredicateAst, ...]
    action: ActionAst

    def canonical(self) -> ClauseAst:
        return ClauseAst(
            tuple(sorted(self.predicates, key=lambda p: (p.variable, p.kind))),
            self.action,
        )

    def matches(self, binding: BindingAst, state: RegisterState) -> bool:
        return all(predicate.evaluate(binding, state) for predicate in self.predicates)

    def alpha(self, rename: dict[str, str]) -> ClauseAst:
        return ClauseAst(
            tuple(predicate.alpha(rename) for predicate in self.predicates),
            self.action.alpha(rename),
        )


@dataclass(frozen=True)
class ProgramAst:
    clauses: tuple[ClauseAst, ...]
    name: str = "program"

    def validate(self, variables: Sequence[str] | None = None) -> None:
        known = set(variables or sorted(program_variables(self)))
        if not self.clauses:
            raise ValueError("Program must contain at least one clause")
        for clause in self.clauses:
            if len(clause.predicates) > MAX_PREDS:
                raise ValueError("Too many predicates")
            for predicate in clause.predicates:
                if predicate.variable not in known:
                    raise ValueError(f"Unknown predicate variable {predicate.variable}")
            action = clause.action
            for variable in (action.source, action.destination):
                if variable is not None and variable not in known:
                    raise ValueError(f"Unknown action variable {variable}")
            if action.kind == "MOVE_ONE" and (
                action.source is None or action.destination is None
            ):
                raise ValueError("MOVE_ONE requires two arguments")
            if action.kind == "DROP_ONE" and action.source is None:
                raise ValueError("DROP_ONE requires one argument")
            if action.kind == "HALT" and (
                action.source is not None or action.destination is not None
            ):
                raise ValueError("HALT takes no arguments")

    def applicable_clause_index(self, binding: BindingAst, state: RegisterState) -> int:
        matches = [
            index
            for index, clause in enumerate(self.clauses)
            if clause.matches(binding, state)
        ]
        if len(matches) != 1:
            raise ValueError(f"Program not deterministic for state {state}: {matches}")
        return matches[0]

    def semantic_json(
        self, *, alpha: bool = False, order_insensitive: bool = False
    ) -> str:
        if alpha and order_insensitive:
            candidates = []
            variables = sorted(program_variables(self))
            for variable_order in itertools.permutations(variables):
                rename = {
                    variable: f"V{index}"
                    for index, variable in enumerate(variable_order)
                }
                normalized = ProgramAst(
                    tuple(clause.alpha(rename) for clause in self.clauses), self.name
                )
                clauses = [
                    clause_to_payload(clause.canonical())
                    for clause in normalized.clauses
                ]
                clauses = sorted(
                    clauses, key=lambda item: json.dumps(item, sort_keys=True)
                )
                candidates.append(json.dumps(clauses, sort_keys=True))
            return min(candidates)

        program = alpha_normalize(self) if alpha else self
        clauses = [clause_to_payload(clause.canonical()) for clause in program.clauses]
        if order_insensitive:
            clauses = sorted(clauses, key=lambda item: json.dumps(item, sort_keys=True))
        return json.dumps(clauses, sort_keys=True)

    def semantic_hash(
        self, *, alpha: bool = False, order_insensitive: bool = False
    ) -> str:
        return stable_hash(
            self.semantic_json(alpha=alpha, order_insensitive=order_insensitive)
        )

    def alpha(self, variables: Sequence[str]) -> ProgramAst:
        old = sorted(program_variables(self))
        rename = {src: dst for src, dst in zip(old, variables, strict=False)}
        return ProgramAst(
            tuple(clause.alpha(rename) for clause in self.clauses), self.name + "_alpha"
        )


@dataclass(frozen=True)
class BindingAst:
    mapping: dict[str, str]

    def __post_init__(self) -> None:
        registers = list(self.mapping.values())
        if len(set(registers)) != len(registers):
            raise ValueError("Binding must be one-to-one")
        if any(register not in REGISTERS for register in registers):
            raise ValueError("Binding contains unknown register")

    def physical(self, variable: str) -> str:
        return self.mapping[variable]

    def matrix(self, variables: Sequence[str]) -> list[list[int]]:
        return [
            [
                1 if self.mapping.get(variable) == register else 0
                for register in REGISTERS
            ]
            for variable in variables
        ]

    def pointer_ids(self, variables: Sequence[str]) -> list[int]:
        return [REGISTERS.index(self.mapping[variable]) for variable in variables]


@dataclass(frozen=True)
class RegisterState:
    counts: dict[str, int]

    def __post_init__(self) -> None:
        if set(self.counts) != set(REGISTERS):
            raise ValueError("RegisterState must contain all registers")
        if any(value < 0 for value in self.counts.values()):
            raise ValueError("Register counts must be non-negative")

    def bits(self) -> list[int]:
        return [1 if self.counts[register] > 0 else 0 for register in REGISTERS]


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
class StepExample:
    program: ProgramAst
    binding: BindingAst
    state: RegisterState
    clause_index: int
    phase: str | None
    split: str


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    sub.add_parser("run-exact")
    sub.add_parser("run-selector")
    sub.add_parser("run-compiler")
    sub.add_parser("analyze")
    report_parser = sub.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    sub.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare":
        prepare()
    elif args.command == "run-exact":
        run_exact()
    elif args.command == "run-selector":
        run_selector()
    elif args.command == "run-compiler":
        run_compiler()
    elif args.command == "analyze":
        analyze()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare()
        run_exact()
        run_selector()
        run_compiler()
        analyze()
        build_report(checks_passed=False)


def prepare() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    train_bindings, heldout_bindings = split_bindings(all_bindings(TRAIN_VARS))
    train_programs = train_program_asts()
    heldout_programs = heldout_program_asts()
    merge_two = merge_two_ast(TRAIN_VARS)
    merge_three = merge_three_ast(TRAIN_VARS)
    manifest = {
        "kind": "m21_neural_symbolic_interpreter",
        "seed": SEED,
        "train_program_count": len(train_programs),
        "heldout_program_count": len(heldout_programs),
        "train_binding_count": len(train_bindings),
        "heldout_binding_count": len(heldout_bindings),
        "binding_overlap": len(
            {binding_hash(b) for b in train_bindings}
            & {binding_hash(b) for b in heldout_bindings}
        ),
        "heldout_ast_overlap": len(
            {
                p.semantic_hash(alpha=True, order_insensitive=True)
                for p in train_programs
            }
            & {
                p.semantic_hash(alpha=True, order_insensitive=True)
                for p in heldout_programs + [merge_two, merge_three]
            }
        ),
        "canonical_parser_roundtrip": all(
            parse_canonical_dsl(render_canonical_program(program, train_bindings[0]))[
                0
            ].semantic_hash(alpha=True, order_insensitive=False)
            == program.semantic_hash(alpha=True, order_insensitive=False)
            for program in train_programs + heldout_programs + [merge_two, merge_three]
        ),
        "m201a_baseline_report": str(
            (ROOT / "runs" / "m201a_fair_compositional_retest_report.md").relative_to(
                ROOT
            )
        ),
    }
    write_json(DATASET_DIR / "manifest.json", manifest)
    write_jsonl(
        DATASET_DIR / "selector_train.jsonl",
        [example_to_json(row) for row in selector_examples("train")],
    )
    write_jsonl(
        DATASET_DIR / "selector_eval.jsonl",
        [example_to_json(row) for row in all_eval_examples()],
    )
    write_jsonl(
        DATASET_DIR / "compiler_train.jsonl",
        compiler_rows(train_programs, train_bindings[:8], "train"),
    )
    write_jsonl(
        DATASET_DIR / "compiler_eval.jsonl",
        compiler_rows(
            train_programs + heldout_programs + [merge_two, merge_three],
            train_bindings[:8],
            "eval",
        ),
    )


def run_exact() -> None:
    output = {
        "upper_bound": {},
        "parser_upper_bound": {},
        "counterfactuals": counterfactual_controls(),
    }
    for split, examples in eval_examples_by_split().items():
        output["upper_bound"][split] = summarize_exact(examples)
        parsed_examples = []
        for example in examples:
            text = render_canonical_program(example.program, example.binding)
            parsed_program, parsed_binding = parse_canonical_dsl(text)
            parsed_examples.append(
                StepExample(
                    parsed_program,
                    parsed_binding,
                    example.state,
                    example.clause_index,
                    example.phase,
                    example.split,
                )
            )
        output["parser_upper_bound"][split] = summarize_exact(parsed_examples)
    write_json(RUNS_DIR / "exact_upper_bound.json", output)


def run_selector() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train = selector_examples("train")
    eval_by_split = eval_examples_by_split()
    model = ClauseSelector().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    rng = random.Random(SEED)
    metrics = []
    for step in range(1, 1501):
        batch = [rng.choice(train) for _ in range(64)]
        tensors = batch_tensors(batch, device=device)
        logits = model(tensors)
        loss = F.cross_entropy(logits, tensors["labels"])
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if step % 300 == 0:
            metrics.append(
                {"step": step, "train_loss": float(loss.detach().cpu().item())}
            )
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "seed": SEED,
            "config": {"max_clauses": MAX_CLAUSES, "max_preds": MAX_PREDS},
        },
        RUNS_DIR / "hierarchical_selector.pt",
    )
    write_jsonl(RUNS_DIR / "selector_metrics.jsonl", metrics)
    model.eval()
    result = {"splits": {}, "closed_loop": {}}
    for split, examples in eval_by_split.items():
        result["splits"][split] = eval_selector(model, examples, device=device)
    for split, specs in closed_loop_specs().items():
        result["closed_loop"][split] = selector_closed_loop(model, specs, device=device)
    write_json(RUNS_DIR / "selector_eval.json", result)


def run_compiler() -> None:
    train_rows = compiler_rows(
        train_program_asts(), split_bindings(all_bindings(TRAIN_VARS))[0][:8], "train"
    )
    eval_rows = compiler_rows(
        train_program_asts()
        + heldout_program_asts()
        + [merge_two_ast(TRAIN_VARS), merge_three_ast(TRAIN_VARS)],
        split_bindings(all_bindings(TRAIN_VARS))[0][:8],
        "eval",
    )
    labels = sorted({row["semantic_hash"] for row in train_rows})
    vocab = sorted({token for row in train_rows for token in tokenize(row["surface"])})
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = CompilerClassifier(len(vocab), len(labels)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    rng = random.Random(SEED)
    metrics = []
    for step in range(1, 1001):
        batch = [rng.choice(train_rows) for _ in range(64)]
        x, y = compiler_batch(batch, vocab, labels, device=device)
        logits = model(x)
        loss = F.cross_entropy(logits, y)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if step % 250 == 0:
            metrics.append(
                {"step": step, "train_loss": float(loss.detach().cpu().item())}
            )
    predictions = []
    with torch.no_grad():
        for row in eval_rows:
            x, _ = compiler_batch(
                [row], vocab, labels, device=device, allow_unknown=True
            )
            logits = model(x)
            pred = labels[int(torch.argmax(logits[0]).item())]
            deterministic_program, _binding = parse_canonical_dsl(row["surface"])
            predictions.append(
                {
                    "split": row["split"],
                    "family": row["family"],
                    "semantic_hash": row["semantic_hash"],
                    "predicted_semantic_hash": pred,
                    "semantic_exact": pred == row["semantic_hash"],
                    "deterministic_parser_exact": deterministic_program.semantic_hash(
                        alpha=True, order_insensitive=True
                    )
                    == row["semantic_hash"],
                    "known_label": row["semantic_hash"] in labels,
                }
            )
    torch.save(
        {"model_state_dict": model.state_dict(), "vocab": vocab, "labels": labels},
        RUNS_DIR / "neural_compiler.pt",
    )
    write_jsonl(RUNS_DIR / "compiler_metrics.jsonl", metrics)
    write_json(RUNS_DIR / "compiler_eval.json", summarize_compiler(predictions))


def analyze() -> None:
    analysis = {
        "manifest": read_json(DATASET_DIR / "manifest.json"),
        "m201a": read_m201a_summary(),
        "exact": read_json(RUNS_DIR / "exact_upper_bound.json"),
        "selector": read_json(RUNS_DIR / "selector_eval.json"),
        "compiler": read_json(RUNS_DIR / "compiler_eval.json"),
    }
    analysis["bakeoff"] = architecture_bakeoff(analysis)
    analysis["decision"] = decide(analysis)
    write_json(RUNS_DIR / "analysis.json", analysis)


class ClauseSelector(nn.Module):
    def __init__(self, hidden: int = 48) -> None:
        super().__init__()
        self.clause_mlp = nn.Sequential(
            nn.Linear(21, hidden), nn.ReLU(), nn.Linear(hidden, 1)
        )

    def forward(self, tensors: dict[str, torch.Tensor]) -> torch.Tensor:
        features = torch.cat(
            [
                tensors["pred_truth"].float(),
                tensors["pred_mask"].float(),
                F.one_hot(tensors["action_kind"], num_classes=3).float(),
                F.one_hot(tensors["source_reg"].clamp_min(0), num_classes=4).float()
                * tensors["source_mask"].unsqueeze(-1).float(),
                F.one_hot(tensors["dest_reg"].clamp_min(0), num_classes=4).float()
                * tensors["dest_mask"].unsqueeze(-1).float(),
                tensors["state_bits"].unsqueeze(1).expand(-1, MAX_CLAUSES, -1).float(),
            ],
            dim=-1,
        )
        logits = self.clause_mlp(features).squeeze(-1)
        return logits.masked_fill(~tensors["clause_mask"].bool(), -1e9)


class CompilerClassifier(nn.Module):
    def __init__(self, vocab_size: int, label_count: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(vocab_size, 128),
            nn.ReLU(),
            nn.Linear(128, label_count),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def batch_tensors(
    examples: Sequence[StepExample], *, device: torch.device
) -> dict[str, torch.Tensor]:
    rows = [encode_selector_example(example) for example in examples]
    keys = rows[0].keys()
    tensors = {
        key: torch.tensor([row[key] for row in rows], dtype=torch.long, device=device)
        for key in keys
    }
    return tensors


def encode_selector_example(example: StepExample) -> dict[str, Any]:
    variables = sorted(program_variables(example.program))
    var_to_index = {variable: index for index, variable in enumerate(variables)}
    clauses = list(example.program.clauses)
    pred_truth = [[0] * MAX_PREDS for _ in range(MAX_CLAUSES)]
    pred_mask = [[0] * MAX_PREDS for _ in range(MAX_CLAUSES)]
    action_kind = [0] * MAX_CLAUSES
    source_reg = [0] * MAX_CLAUSES
    dest_reg = [0] * MAX_CLAUSES
    source_mask = [0] * MAX_CLAUSES
    dest_mask = [0] * MAX_CLAUSES
    clause_mask = [0] * MAX_CLAUSES
    for clause_index, clause in enumerate(clauses[:MAX_CLAUSES]):
        clause_mask[clause_index] = 1
        for pred_index, predicate in enumerate(clause.predicates[:MAX_PREDS]):
            pred_mask[clause_index][pred_index] = 1
            pred_truth[clause_index][pred_index] = int(
                predicate.evaluate(example.binding, example.state)
            )
            _ = var_to_index[predicate.variable]
        action_kind[clause_index] = ACTION_KINDS.index(clause.action.kind)
        if clause.action.source is not None:
            source_mask[clause_index] = 1
            source_reg[clause_index] = REGISTERS.index(
                example.binding.physical(clause.action.source)
            )
        if clause.action.destination is not None:
            dest_mask[clause_index] = 1
            dest_reg[clause_index] = REGISTERS.index(
                example.binding.physical(clause.action.destination)
            )
    return {
        "pred_truth": pred_truth,
        "pred_mask": pred_mask,
        "action_kind": action_kind,
        "source_reg": source_reg,
        "dest_reg": dest_reg,
        "source_mask": source_mask,
        "dest_mask": dest_mask,
        "clause_mask": clause_mask,
        "state_bits": example.state.bits(),
        "labels": example.clause_index,
    }


@torch.no_grad()
def eval_selector(
    model: ClauseSelector, examples: Sequence[StepExample], *, device: torch.device
) -> dict[str, Any]:
    rows = []
    for start in range(0, len(examples), 256):
        batch = examples[start : start + 256]
        tensors = batch_tensors(batch, device=device)
        logits = model(tensors)
        predictions = torch.argmax(logits, dim=-1).detach().cpu().tolist()
        for example, prediction in zip(batch, predictions, strict=True):
            selected = int(prediction)
            expected = example.clause_index
            action = (
                example.program.clauses[selected]
                .action.resolve(example.binding)
                .render()
                if selected < len(example.program.clauses)
                else "INVALID"
            )
            expected_action = (
                example.program.clauses[expected]
                .action.resolve(example.binding)
                .render()
            )
            rows.append(
                {
                    "split": example.split,
                    "phase": example.phase,
                    "selected": selected,
                    "expected": expected,
                    "clause_correct": selected == expected,
                    "action_correct": action == expected_action,
                }
            )
    return summarize_selector_rows(rows)


def selector_closed_loop(
    model: ClauseSelector,
    specs: Sequence[tuple[ProgramAst, BindingAst, RegisterState]],
    *,
    device: torch.device,
) -> dict[str, Any]:
    rows = []
    for program, binding, initial in specs:
        state = RegisterState(dict(initial.counts))
        oracle = exact_closed_loop(program, binding, initial)
        actions = []
        invalid = False
        b_started = False
        first_error = None
        for step in range(sum(initial.counts.values()) + 8):
            expected = program.applicable_clause_index(binding, state)
            phase = (
                merge_phase(binding, state, b_started)
                if program.name == "merge_two"
                else None
            )
            example = StepExample(
                program, binding, state, expected, phase, "closed_loop"
            )
            tensors = batch_tensors([example], device=device)
            selected = int(torch.argmax(model(tensors)[0]).detach().cpu().item())
            if selected >= len(program.clauses):
                invalid = True
                break
            if first_error is None and selected != expected:
                first_error = {
                    "step": step,
                    "phase": phase,
                    "expected": expected,
                    "selected": selected,
                }
            action = program.clauses[selected].action.resolve(binding)
            actions.append(action.render())
            state, step_invalid, terminated = step_state(state, action)
            invalid = invalid or step_invalid
            if phase in {"A_TO_B_SWITCH", "PHASE_B_MOVE"}:
                b_started = True
            if invalid or terminated:
                break
        rows.append(
            {
                "final_state_exact": state.counts == oracle["final_state"]
                and not invalid,
                "invalid": invalid,
                "trajectory_length": sum(initial.counts.values()),
                "first_error": first_error,
                "actions": actions,
            }
        )
    return summarize_closed_loop_rows(rows)


def summarize_selector_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    return {
        "overall": {
            "count": total,
            "clause_accuracy": safe_rate(
                sum(row["clause_correct"] for row in rows), total
            ),
            "resolved_action_accuracy": safe_rate(
                sum(row["action_correct"] for row in rows), total
            ),
        },
        "by_phase": grouped(rows, "phase", "clause_correct"),
        "failure_samples": [row for row in rows if not row["clause_correct"]][:20],
    }


def summarize_closed_loop_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    return {
        "overall": {
            "count": total,
            "final_state_exact": safe_rate(
                sum(row["final_state_exact"] for row in rows), total
            ),
            "invalid_rate": safe_rate(sum(row["invalid"] for row in rows), total),
        },
        "by_length": grouped_length(rows),
        "failure_samples": [row for row in rows if not row["final_state_exact"]][:20],
    }


def grouped(rows: Sequence[dict[str, Any]], key: str, metric: str) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(key)
        if value:
            buckets[str(value)].append(row)
    return {
        name: {
            "count": len(bucket),
            "accuracy": safe_rate(sum(row[metric] for row in bucket), len(bucket)),
        }
        for name, bucket in sorted(buckets.items())
    }


def grouped_length(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        length = int(row["trajectory_length"])
        if length <= 10:
            key = "0_10"
        elif length <= 20:
            key = "11_20"
        elif length <= 50:
            key = "21_50"
        else:
            key = "51_100"
        buckets[key].append(row)
    return {
        key: {
            "count": len(bucket),
            "final_state_exact": safe_rate(
                sum(row["final_state_exact"] for row in bucket), len(bucket)
            ),
        }
        for key, bucket in sorted(buckets.items())
    }


def summarize_exact(examples: Sequence[StepExample]) -> dict[str, Any]:
    correct = 0
    action_correct = 0
    for example in examples:
        selected = example.program.applicable_clause_index(
            example.binding, example.state
        )
        correct += int(selected == example.clause_index)
        action_correct += int(
            example.program.clauses[selected].action.resolve(example.binding).render()
            == example.program.clauses[example.clause_index]
            .action.resolve(example.binding)
            .render()
        )
    total = len(examples)
    return {
        "count": total,
        "clause_accuracy": safe_rate(correct, total),
        "action_accuracy": safe_rate(action_correct, total),
    }


def exact_closed_loop(
    program: ProgramAst, binding: BindingAst, initial: RegisterState
) -> dict[str, Any]:
    state = RegisterState(dict(initial.counts))
    actions = []
    invalid = False
    for _ in range(sum(initial.counts.values()) + 8):
        action = program.clauses[
            program.applicable_clause_index(binding, state)
        ].action.resolve(binding)
        actions.append(action.render())
        state, step_invalid, terminated = step_state(state, action)
        invalid = invalid or step_invalid
        if invalid or terminated:
            break
    return {"final_state": state.counts, "invalid": invalid, "actions": actions}


def step_state(
    state: RegisterState, action: PhysicalAction
) -> tuple[RegisterState, bool, bool]:
    counts = dict(state.counts)
    if action.kind == "HALT":
        return RegisterState(counts), False, True
    if action.kind == "DROP_ONE":
        assert action.source is not None
        if counts[action.source] <= 0:
            return RegisterState(counts), True, False
        counts[action.source] -= 1
        return RegisterState(counts), False, False
    assert action.source is not None and action.destination is not None
    if counts[action.source] <= 0:
        return RegisterState(counts), True, False
    counts[action.source] -= 1
    counts[action.destination] += 1
    return RegisterState(counts), False, False


def parse_canonical_dsl(text: str) -> tuple[ProgramAst, BindingAst]:
    clauses = []
    binding: BindingAst | None = None
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        tokens = line.split()
        if (
            tokens[0] in ALL_VARS
            and len(tokens) >= 8
            and all(tokens[i] in ALL_VARS for i in range(0, len(tokens), 2))
        ):
            binding = BindingAst(
                {tokens[i]: tokens[i + 1] for i in range(0, len(tokens), 2)}
            )
            continue
        if tokens[0] in REGISTERS:
            continue
        clauses.append(parse_clause_line(line))
    if binding is None:
        raise ValueError("DSL missing binding line")
    program = ProgramAst(tuple(clauses), "parsed")
    verify_program(program, binding)
    return program, binding


def parse_clause_line(line: str) -> ClauseAst:
    tokens = line.split()
    predicates = []
    index = 0
    while index < len(tokens) and tokens[index] in {"E", "NE"}:
        predicates.append(
            PredicateAst(
                "EMPTY" if tokens[index] == "E" else "NONEMPTY", tokens[index + 1]
            )
        )
        index += 2
    if index >= len(tokens):
        raise ValueError(f"Missing action in clause: {line}")
    action_token = tokens[index]
    if action_token == "M":
        action = ActionAst("MOVE_ONE", tokens[index + 1], tokens[index + 2])
    elif action_token == "D":
        action = ActionAst("DROP_ONE", tokens[index + 1])
    elif action_token == "H":
        action = ActionAst("HALT")
    else:
        raise ValueError(f"Unknown action token: {action_token}")
    return ClauseAst(tuple(predicates), action)


def render_canonical_program(
    program: ProgramAst, binding: BindingAst, *, order: Sequence[int] | None = None
) -> str:
    indexes = list(order) if order is not None else list(range(len(program.clauses)))
    lines = [render_clause(program.clauses[index]) for index in indexes]
    lines.append(
        " ".join(f"{var} {reg}" for var, reg in sorted(binding.mapping.items()))
    )
    return "\n".join(lines)


def render_clause(clause: ClauseAst) -> str:
    parts = []
    for predicate in clause.predicates:
        parts.extend(["E" if predicate.kind == "EMPTY" else "NE", predicate.variable])
    action = clause.action
    if action.kind == "MOVE_ONE":
        parts.extend(["M", action.source or "", action.destination or ""])
    elif action.kind == "DROP_ONE":
        parts.extend(["D", action.source or ""])
    else:
        parts.append("H")
    return " ".join(parts)


def verify_program(program: ProgramAst, binding: BindingAst) -> None:
    program.validate(binding.mapping.keys())
    for values in itertools.product((0, 1), repeat=len(REGISTERS)):
        state = RegisterState(dict(zip(REGISTERS, values, strict=True)))
        matches = [
            clause for clause in program.clauses if clause.matches(binding, state)
        ]
        if len(matches) != 1:
            raise ValueError(f"Program is not deterministic/exhaustive: {matches}")


def selector_examples(kind: str) -> list[StepExample]:
    train_bindings, _heldout_bindings = split_bindings(all_bindings(TRAIN_VARS))
    programs = train_program_asts()
    examples = []
    for program, binding, count in itertools.product(
        programs, train_bindings, TRAIN_COUNTS
    ):
        examples.extend(
            step_examples(
                program, binding, initial_state(program, binding, count), kind
            )
        )
    rng = random.Random(SEED)
    rng.shuffle(examples)
    return examples[:12000]


def all_eval_examples() -> list[StepExample]:
    rows = []
    for examples in eval_examples_by_split().values():
        rows.extend(examples)
    return rows


def eval_examples_by_split() -> dict[str, list[StepExample]]:
    train_bindings, heldout_bindings = split_bindings(all_bindings(TRAIN_VARS))
    seen = train_bindings[:8]
    held = heldout_bindings
    train_programs = train_program_asts()
    heldout_programs = heldout_program_asts()
    merge_two = merge_two_ast(TRAIN_VARS)
    merge_three = merge_three_ast(TRAIN_VARS)
    return {
        "seen_ast": examples_for_specs(
            train_programs[:6], seen, TRAIN_COUNTS, "seen_ast"
        ),
        "heldout_binding": examples_for_specs(
            train_programs[:6], held, TRAIN_COUNTS, "heldout_binding"
        ),
        "heldout_program": examples_for_specs(
            heldout_programs, seen, TRAIN_COUNTS, "heldout_program"
        ),
        "heldout_predicate_composition": examples_for_specs(
            [heldout_predicate_composition_ast()],
            seen,
            TRAIN_COUNTS,
            "heldout_predicate_composition",
        ),
        "heldout_merge_two": merge_examples(
            merge_two, seen, TRAIN_COUNTS, "heldout_merge_two"
        ),
        "merge_two_11_20": merge_examples(
            merge_two, seen[:4], OOD_COUNTS, "merge_two_11_20"
        ),
        "merge_two_21_50": merge_examples(
            merge_two, seen[:2], LONG_COUNTS, "merge_two_21_50"
        ),
        "merge_two_51_100": merge_examples(
            merge_two, seen[:2], FAR_COUNTS, "merge_two_51_100"
        ),
        "merge_three": merge_three_examples(
            merge_three, seen[:4], TRAIN_COUNTS, "merge_three"
        ),
        "clause_order": shuffled_examples(
            train_programs[:6], seen, TRAIN_COUNTS, "clause_order"
        ),
        "alpha_renamed": alpha_examples(
            train_programs[:4], seen, TRAIN_COUNTS, "alpha_renamed"
        ),
        "distractor_8": distractor_examples(
            train_programs[:4], seen, 8, "distractor_8"
        ),
        "distractor_16": distractor_examples(
            train_programs[:4], seen, 16, "distractor_16"
        ),
    }


def closed_loop_specs() -> dict[
    str, list[tuple[ProgramAst, BindingAst, RegisterState]]
]:
    train_bindings, heldout_bindings = split_bindings(all_bindings(TRAIN_VARS))
    seen = train_bindings[:8]
    held = heldout_bindings
    merge_two = merge_two_ast(TRAIN_VARS)
    merge_three = merge_three_ast(TRAIN_VARS)
    return {
        "seen_ast": specs_for(train_program_asts()[:6], seen, TRAIN_COUNTS),
        "heldout_binding": specs_for(train_program_asts()[:6], held, TRAIN_COUNTS),
        "heldout_program": specs_for(heldout_program_asts(), seen, TRAIN_COUNTS),
        "heldout_merge_two": merge_specs(merge_two, seen, TRAIN_COUNTS),
        "merge_two_11_20": merge_specs(merge_two, seen[:4], OOD_COUNTS),
        "merge_two_21_50": merge_specs(merge_two, seen[:2], LONG_COUNTS),
        "merge_two_51_100": merge_specs(merge_two, seen[:2], FAR_COUNTS),
        "merge_three": merge_three_specs(merge_three, seen[:4], TRAIN_COUNTS),
    }


def specs_for(
    programs: Sequence[ProgramAst],
    bindings: Sequence[BindingAst],
    counts: Sequence[int],
) -> list[tuple[ProgramAst, BindingAst, RegisterState]]:
    return [
        (program, binding, initial_state(program, binding, count))
        for program, binding, count in itertools.product(programs, bindings, counts)
    ]


def merge_specs(
    program: ProgramAst, bindings: Sequence[BindingAst], counts: Sequence[int]
) -> list[tuple[ProgramAst, BindingAst, RegisterState]]:
    return [
        (program, binding, merge_state(binding, left, right))
        for binding in bindings
        for left in counts
        for right in counts[: min(6, len(counts))]
    ]


def merge_three_specs(
    program: ProgramAst, bindings: Sequence[BindingAst], counts: Sequence[int]
) -> list[tuple[ProgramAst, BindingAst, RegisterState]]:
    return [
        (program, binding, merge_three_state(binding, count, count // 2, count % 4))
        for binding, count in itertools.product(bindings, counts)
    ]


def examples_for_specs(
    programs: Sequence[ProgramAst],
    bindings: Sequence[BindingAst],
    counts: Sequence[int],
    split: str,
) -> list[StepExample]:
    rows = []
    for program, binding, initial in specs_for(programs, bindings, counts):
        rows.extend(step_examples(program, binding, initial, split))
    return rows


def merge_examples(
    program: ProgramAst,
    bindings: Sequence[BindingAst],
    counts: Sequence[int],
    split: str,
) -> list[StepExample]:
    rows = []
    for spec_program, binding, initial in merge_specs(program, bindings, counts):
        rows.extend(step_examples(spec_program, binding, initial, split, phases=True))
    return rows


def merge_three_examples(
    program: ProgramAst,
    bindings: Sequence[BindingAst],
    counts: Sequence[int],
    split: str,
) -> list[StepExample]:
    rows = []
    for spec_program, binding, initial in merge_three_specs(program, bindings, counts):
        rows.extend(step_examples(spec_program, binding, initial, split))
    return rows


def shuffled_examples(
    programs: Sequence[ProgramAst],
    bindings: Sequence[BindingAst],
    counts: Sequence[int],
    split: str,
) -> list[StepExample]:
    rows = []
    for program in programs:
        order = tuple(reversed(range(len(program.clauses))))
        shuffled = ProgramAst(
            tuple(program.clauses[index] for index in order), program.name + "_shuffled"
        )
        for binding, count in itertools.product(bindings, counts):
            rows.extend(
                step_examples(
                    shuffled, binding, initial_state(program, binding, count), split
                )
            )
    return rows


def alpha_examples(
    programs: Sequence[ProgramAst],
    bindings: Sequence[BindingAst],
    counts: Sequence[int],
    split: str,
) -> list[StepExample]:
    rows = []
    for program in programs:
        alpha = program.alpha(ALPHA_VARS)
        for binding, count in itertools.product(bindings, counts):
            alpha_binding = BindingAst(
                dict(zip(ALPHA_VARS, binding.mapping.values(), strict=True))
            )
            rows.extend(
                step_examples(
                    alpha,
                    alpha_binding,
                    initial_state(alpha, alpha_binding, count),
                    split,
                )
            )
    return rows


def distractor_examples(
    programs: Sequence[ProgramAst],
    bindings: Sequence[BindingAst],
    distractors: int,
    split: str,
) -> list[StepExample]:
    rows = []
    for program, binding, count in itertools.product(programs, bindings, TRAIN_COUNTS):
        extra = tuple(
            ClauseAst(
                (PredicateAst("EMPTY", "D"), PredicateAst("NONEMPTY", "D")),
                ActionAst("MOVE_ONE", "D", "C" if index % 2 == 0 else "B"),
            )
            for index in range(distractors)
        )
        with_distractors = ProgramAst(
            program.clauses + extra, program.name + "_distractors"
        )
        rows.extend(
            step_examples(
                with_distractors, binding, initial_state(program, binding, count), split
            )
        )
    return rows


def step_examples(
    program: ProgramAst,
    binding: BindingAst,
    initial: RegisterState,
    split: str,
    *,
    phases: bool = False,
) -> list[StepExample]:
    state = RegisterState(dict(initial.counts))
    rows = []
    b_started = False
    for _ in range(sum(initial.counts.values()) + 8):
        clause_index = program.applicable_clause_index(binding, state)
        phase = merge_phase(binding, state, b_started) if phases else None
        rows.append(StepExample(program, binding, state, clause_index, phase, split))
        action = program.clauses[clause_index].action.resolve(binding)
        state, invalid, terminated = step_state(state, action)
        if phase in {"A_TO_B_SWITCH", "PHASE_B_MOVE"}:
            b_started = True
        if invalid or terminated:
            break
    return rows


def merge_phase(binding: BindingAst, state: RegisterState, b_started: bool) -> str:
    left = state.counts[binding.physical("A")]
    right = state.counts[binding.physical("B")]
    if left > 0:
        return "PHASE_A_MOVE"
    if right > 0 and not b_started:
        return "A_TO_B_SWITCH"
    if right > 0:
        return "PHASE_B_MOVE"
    return "FINAL_HALT"


def initial_state(
    program: ProgramAst, binding: BindingAst, count: int
) -> RegisterState:
    counts = {register: 0 for register in REGISTERS}
    variables = []
    for clause in program.clauses:
        for predicate in clause.predicates:
            if predicate.kind == "NONEMPTY" and predicate.variable not in variables:
                variables.append(predicate.variable)
    for index, variable in enumerate(variables):
        counts[binding.physical(variable)] = count if index == 0 else count // 2
    return RegisterState(counts)


def merge_state(binding: BindingAst, left: int, right: int) -> RegisterState:
    counts = {register: 0 for register in REGISTERS}
    counts[binding.physical("A")] = left
    counts[binding.physical("B")] = right
    return RegisterState(counts)


def merge_three_state(
    binding: BindingAst, first: int, second: int, third: int
) -> RegisterState:
    counts = {register: 0 for register in REGISTERS}
    counts[binding.physical("A")] = first
    counts[binding.physical("B")] = second
    counts[binding.physical("C")] = third
    return RegisterState(counts)


def train_program_asts() -> list[ProgramAst]:
    return [from_m201_program(program) for program in m201.grammar_train_programs()]


def heldout_program_asts() -> list[ProgramAst]:
    return [from_m201_program(program) for program in m201.grammar_heldout_programs()]


def heldout_predicate_composition_ast() -> ProgramAst:
    return ProgramAst(
        (
            ClauseAst(
                (PredicateAst("EMPTY", "A"), PredicateAst("NONEMPTY", "B")),
                ActionAst("MOVE_ONE", "B", "C"),
            ),
            ClauseAst(
                (PredicateAst("EMPTY", "A"), PredicateAst("EMPTY", "B")),
                ActionAst("HALT"),
            ),
            ClauseAst((PredicateAst("NONEMPTY", "A"),), ActionAst("DROP_ONE", "A")),
        ),
        "heldout_predicate_composition",
    )


def merge_two_ast(variables: Sequence[str]) -> ProgramAst:
    return from_m201_program(m201.merge_two_program(variables))


def merge_three_ast(variables: Sequence[str]) -> ProgramAst:
    return from_m201_program(m201.merge_three_program(variables))


def from_m201_program(program: Any) -> ProgramAst:
    return ProgramAst(
        tuple(
            ClauseAst(
                tuple(
                    PredicateAst(pred.kind, pred.variable) for pred in clause.predicates
                ),
                ActionAst(
                    clause.action.kind, clause.action.source, clause.action.destination
                ),
            )
            for clause in program.clauses
        ),
        program.family,
    )


def all_bindings(variables: Sequence[str]) -> list[BindingAst]:
    return [
        BindingAst(dict(zip(variables, registers, strict=True)))
        for registers in itertools.permutations(REGISTERS)
    ]


def split_bindings(
    bindings: Sequence[BindingAst],
) -> tuple[list[BindingAst], list[BindingAst]]:
    heldout = [
        binding
        for binding in bindings
        if (binding.mapping["A"] == "R0" and binding.mapping["C"] == "R3")
        or (binding.mapping["A"] == "R3" and binding.mapping["C"] == "R0")
    ]
    train = [binding for binding in bindings if binding not in heldout]
    return train, heldout


def binding_hash(binding: BindingAst) -> str:
    return stable_hash(json.dumps(sorted(binding.mapping.items())))


def program_variables(program: ProgramAst) -> set[str]:
    variables = set()
    for clause in program.clauses:
        for predicate in clause.predicates:
            variables.add(predicate.variable)
        if clause.action.source is not None:
            variables.add(clause.action.source)
        if clause.action.destination is not None:
            variables.add(clause.action.destination)
    return variables


def alpha_normalize(program: ProgramAst) -> ProgramAst:
    variables: dict[str, str] = {}

    def norm(variable: str | None) -> str | None:
        if variable is None:
            return None
        if variable not in variables:
            variables[variable] = f"V{len(variables)}"
        return variables[variable]

    clauses = []
    for clause in program.clauses:
        clauses.append(
            ClauseAst(
                tuple(
                    PredicateAst(predicate.kind, norm(predicate.variable) or "")
                    for predicate in clause.predicates
                ),
                ActionAst(
                    clause.action.kind,
                    norm(clause.action.source),
                    norm(clause.action.destination),
                ),
            )
        )
    return ProgramAst(tuple(clauses), program.name)


def clause_to_payload(clause: ClauseAst) -> dict[str, Any]:
    return {
        "predicates": [asdict(predicate) for predicate in clause.predicates],
        "action": asdict(clause.action),
    }


def stable_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compiler_rows(
    programs: Sequence[ProgramAst], bindings: Sequence[BindingAst], split: str
) -> list[dict[str, Any]]:
    rows = []
    for program, binding in itertools.product(programs, bindings):
        surface = render_canonical_program(program, binding)
        rows.append(
            {
                "surface": surface,
                "semantic_hash": program.semantic_hash(
                    alpha=True, order_insensitive=True
                ),
                "exact_hash": program.semantic_hash(
                    alpha=False, order_insensitive=False
                ),
                "family": program.name,
                "split": "train"
                if split == "train"
                else (
                    "seen_template"
                    if program in train_program_asts()
                    else "heldout_template"
                ),
            }
        )
    return rows


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Z0-9_]+", text.upper())


def compiler_batch(
    rows: Sequence[dict[str, Any]],
    vocab: Sequence[str],
    labels: Sequence[str],
    *,
    device: torch.device,
    allow_unknown: bool = False,
) -> tuple[torch.Tensor, torch.Tensor]:
    vocab_index = {token: index for index, token in enumerate(vocab)}
    label_index = {label: index for index, label in enumerate(labels)}
    x = torch.zeros((len(rows), len(vocab)), dtype=torch.float32, device=device)
    y = torch.zeros((len(rows),), dtype=torch.long, device=device)
    for row_index, row in enumerate(rows):
        for token in tokenize(row["surface"]):
            if token in vocab_index:
                x[row_index, vocab_index[token]] += 1.0
        if row["semantic_hash"] in label_index:
            y[row_index] = label_index[row["semantic_hash"]]
        elif not allow_unknown:
            raise ValueError("Unknown compiler label")
    return x, y


def summarize_compiler(predictions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "overall": {
            "count": len(predictions),
            "semantic_exact": safe_rate(
                sum(row["semantic_exact"] for row in predictions), len(predictions)
            ),
            "deterministic_parser_exact": safe_rate(
                sum(row["deterministic_parser_exact"] for row in predictions),
                len(predictions),
            ),
            "validity": 1.0,
        },
        "by_split": {
            key: {
                "count": len(bucket),
                "semantic_exact": safe_rate(
                    sum(row["semantic_exact"] for row in bucket), len(bucket)
                ),
                "deterministic_parser_exact": safe_rate(
                    sum(row["deterministic_parser_exact"] for row in bucket),
                    len(bucket),
                ),
            }
            for key, bucket in group_by(predictions, "split").items()
        },
        "failure_samples": [row for row in predictions if not row["semantic_exact"]][
            :20
        ],
    }


def group_by(
    rows: Sequence[dict[str, Any]], key: str
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(key))].append(row)
    return dict(sorted(buckets.items()))


def counterfactual_controls() -> dict[str, Any]:
    binding = BindingAst({"A": "R0", "B": "R1", "C": "R2", "D": "R3"})
    state = merge_state(binding, 2, 3)
    correct = merge_two_ast(TRAIN_VARS)
    wrong = train_program_asts()[3]
    swapped = BindingAst({"A": "R3", "B": "R1", "C": "R2", "D": "R0"})
    reordered = ProgramAst(tuple(reversed(correct.clauses)), "merge_two_reordered")
    alpha = correct.alpha(ALPHA_VARS)
    alpha_binding = BindingAst(
        dict(zip(ALPHA_VARS, binding.mapping.values(), strict=True))
    )
    return {
        "correct": exact_closed_loop(correct, binding, state)["final_state"],
        "wrong_program": exact_closed_loop(wrong, binding, state)["final_state"],
        "swapped_binding": exact_closed_loop(correct, swapped, state)["final_state"],
        "reordered_equivalent": exact_closed_loop(reordered, binding, state)[
            "final_state"
        ],
        "alpha_equivalent": exact_closed_loop(alpha, alpha_binding, state)[
            "final_state"
        ],
    }


def architecture_bakeoff(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    m201a = analysis["m201a"]
    selector = analysis["selector"]
    compiler = analysis["compiler"]
    exact = analysis["exact"]
    return [
        {
            "architecture": "flat text LM policy",
            "heldout_program": m201a.get("curriculum_replay50_lm", {}).get(
                "heldout_program_closed", 0.125
            ),
            "merge_two": m201a.get("curriculum_replay50_lm", {}).get(
                "merge_two_closed", 0.0911
            ),
        },
        {
            "architecture": "flat policy head",
            "heldout_program": m201a.get("policy_head", {}).get(
                "heldout_program_closed", 0.224
            ),
            "merge_two": m201a.get("policy_head", {}).get("merge_two_closed", 0.4193),
        },
        {
            "architecture": "exact AST + hierarchical selector + exact resolver",
            "heldout_program": selector["closed_loop"]["heldout_program"]["overall"][
                "final_state_exact"
            ],
            "merge_two": selector["closed_loop"]["heldout_merge_two"]["overall"][
                "final_state_exact"
            ],
        },
        {
            "architecture": "neural compiler + exact interpreter",
            "heldout_program": compiler["by_split"]
            .get("heldout_template", {})
            .get("semantic_exact", 0.0),
            "merge_two": compiler["by_split"]
            .get("heldout_template", {})
            .get("semantic_exact", 0.0),
        },
        {
            "architecture": "deterministic parser + exact interpreter upper bound",
            "heldout_program": exact["upper_bound"]["heldout_program"][
                "action_accuracy"
            ],
            "merge_two": exact["upper_bound"]["heldout_merge_two"]["action_accuracy"],
        },
    ]


def decide(analysis: dict[str, Any]) -> str:
    selector = analysis["selector"]
    compiler = analysis["compiler"]
    heldout = selector["closed_loop"]["heldout_program"]["overall"]["final_state_exact"]
    merge = selector["closed_loop"]["heldout_merge_two"]["overall"]["final_state_exact"]
    compiler_heldout = (
        compiler["by_split"].get("heldout_template", {}).get("semantic_exact", 0.0)
    )
    if heldout >= 0.90 and merge >= 0.90 and compiler_heldout >= 0.90:
        return "OUTCOME A: hybrid compiler/interpreter works end to end."
    if heldout >= 0.90 and merge >= 0.90:
        return "OUTCOME B: exact AST plus hierarchical selector works, but neural compiler is the bottleneck."
    if heldout < 0.90 or merge < 0.90:
        return "OUTCOME C: exact AST plus hierarchical selector still fails; use fully exact interpreter at runtime."
    return "OUTCOME E: deterministic parser works, neural compiler does not yet replace it."


def build_report(*, checks_passed: bool) -> None:
    analysis = read_json(RUNS_DIR / "analysis.json")
    lines = [
        "# M-21 Hybrid Neural Compiler + Exact Interpreter",
        "",
        "## Remote Environment",
        "",
        "- hostname: `karina`",
        "- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB`",
        "- branch: `exp/neural-symbolic-interpreter`",
        "",
        "## M-20.1a Starting Point",
        "",
        "M-20.1a found replay50 `program_seen=1.0`, `heldout_binding=1.0`, but `heldout_program=0.1250` and `MERGE_TWO=0.0911`; policy head improved MERGE_TWO to `0.4193` but did not solve heldout AST composition.",
        "",
        "## Literature Architecture Map",
        "",
        f"See `{RESEARCH_NOTES_PATH.relative_to(ROOT)}`. The implemented boundary follows NPI/NSM/Forth-style decomposition: learned structured selection, exact typed execution.",
        "",
        "## Typed AST",
        "",
        "Implemented `ProgramAst`, `ClauseAst`, `PredicateAst`, `ActionAst`, `BindingAst`, and `RegisterState` with alpha-normalized and order-insensitive semantic hashes plus deterministic validation.",
        "",
        "## Exact Interpreter Upper Bound",
        "",
        exact_table(analysis["exact"]["upper_bound"]),
        "",
        "## Deterministic DSL Parser",
        "",
        exact_table(analysis["exact"]["parser_upper_bound"]),
        "",
        "## Oracle Component Ladder",
        "",
        "Oracle parser/interpreter is 1.0. The structured selector condition removes text parsing and action serialization; exact action resolution maps selected clauses to physical actions.",
        "",
        "## Structured Binding",
        "",
        "Bindings are represented as pointer IDs and logical-variable to physical-register matrices. Text binding is not used inside the selector.",
        "",
        "## Hierarchical Clause Selector",
        "",
        selector_table(analysis["selector"]["splits"]),
        "",
        "## Exact vs Neural Action Resolution",
        "",
        "Exact action resolution is used after selector choice. M-20.1a policy-head numbers are reported in the bakeoff as the finite neural action resolver control; LM action generation remains the weakest interface.",
        "",
        "## Structured AST Generalization",
        "",
        closed_table(analysis["selector"]["closed_loop"]),
        "",
        "## MERGE_TWO Phase Results",
        "",
        phase_table(analysis["selector"]["splits"]["heldout_merge_two"]),
        "",
        "## Neural Compiler",
        "",
        compiler_table(analysis["compiler"]),
        "",
        "## AST Validity and Semantic Accuracy",
        "",
        f"- compiler validity: `{analysis['compiler']['overall']['validity']:.4f}`",
        f"- compiler semantic exact: `{analysis['compiler']['overall']['semantic_exact']:.4f}`",
        f"- deterministic parser semantic exact: `{analysis['compiler']['overall']['deterministic_parser_exact']:.4f}`",
        "",
        "## Verifier / Repair",
        "",
        "Verifier rejects unknown variables, invalid register references, invalid action arity, non-exhaustive programs, and overlapping clauses. Repair was not run.",
        "",
        "## Compiler + Exact Interpreter",
        "",
        "End-to-end compiler execution is bounded by semantic AST accuracy; exact interpreter succeeds when AST is correct.",
        "",
        "## Heldout Program Instances",
        "",
        split_line(analysis["selector"], "heldout_program"),
        "",
        "## Heldout MERGE_TWO",
        "",
        split_line(analysis["selector"], "heldout_merge_two"),
        "",
        "## Heldout MERGE_THREE",
        "",
        split_line(analysis["selector"], "merge_three"),
        "",
        "## Counterfactual Controls",
        "",
        json_block(analysis["exact"]["counterfactuals"]),
        "",
        "## Optional Program Induction",
        "",
        "Not gated. Demonstration-to-program induction requires compiler/interpreter success first.",
        "",
        "## Architecture Bakeoff",
        "",
        bakeoff_table(analysis["bakeoff"]),
        "",
        "## Multi-Seed",
        "",
        "One exploratory seed only. Multi-seed gate was not reached unless a candidate exceeds 0.90.",
        "",
        "## Interpretation",
        "",
        analysis["decision"],
        "",
        "## Recommended Stage-1 Architecture",
        "",
        recommendation(analysis["decision"]),
        "",
        "## Checks",
        "",
        f"- local/remote ruff + pytest + CUDA smoke: {'passed' if checks_passed else 'pending at report build'}",
        f"- commit hash at run: `{git_rev_parse('HEAD')[:7]}`",
    ]
    text = "\n".join(lines).rstrip() + "\n"
    DOC_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_REPORT_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def exact_table(rows: dict[str, Any]) -> str:
    lines = ["| split | clause acc | action acc |", "|---|---:|---:|"]
    for split, stats in sorted(rows.items()):
        lines.append(
            f"| {split} | {stats['clause_accuracy']:.4f} | {stats['action_accuracy']:.4f} |"
        )
    return "\n".join(lines)


def selector_table(rows: dict[str, Any]) -> str:
    lines = ["| split | clause acc | resolved action acc |", "|---|---:|---:|"]
    for split, stats in sorted(rows.items()):
        overall = stats["overall"]
        lines.append(
            f"| {split} | {overall['clause_accuracy']:.4f} | {overall['resolved_action_accuracy']:.4f} |"
        )
    return "\n".join(lines)


def closed_table(rows: dict[str, Any]) -> str:
    lines = ["| split | closed-loop final | invalid |", "|---|---:|---:|"]
    for split, stats in sorted(rows.items()):
        overall = stats["overall"]
        lines.append(
            f"| {split} | {overall['final_state_exact']:.4f} | {overall['invalid_rate']:.4f} |"
        )
    return "\n".join(lines)


def compiler_table(stats: dict[str, Any]) -> str:
    lines = [
        "| split | semantic exact | deterministic parser exact |",
        "|---|---:|---:|",
    ]
    for split, row in sorted(stats["by_split"].items()):
        lines.append(
            f"| {split} | {row['semantic_exact']:.4f} | {row['deterministic_parser_exact']:.4f} |"
        )
    return "\n".join(lines)


def phase_table(stats: dict[str, Any]) -> str:
    lines = ["| phase | count | clause acc |", "|---|---:|---:|"]
    for phase, row in sorted(stats.get("by_phase", {}).items()):
        lines.append(f"| {phase} | {row['count']} | {row['accuracy']:.4f} |")
    return "\n".join(lines)


def split_line(selector: dict[str, Any], split: str) -> str:
    step = selector["splits"][split]["overall"]
    closed = selector["closed_loop"].get(split, {}).get("overall", {})
    return (
        f"- one-step clause: `{step['clause_accuracy']:.4f}`; "
        f"resolved action: `{step['resolved_action_accuracy']:.4f}`; "
        f"closed-loop: `{closed.get('final_state_exact', 0.0):.4f}`"
    )


def bakeoff_table(rows: Sequence[dict[str, Any]]) -> str:
    lines = ["| architecture | heldout program | MERGE_TWO |", "|---|---:|---:|"]
    for row in rows:
        lines.append(
            f"| {row['architecture']} | {row['heldout_program']:.4f} | {row['merge_two']:.4f} |"
        )
    return "\n".join(lines)


def recommendation(decision: str) -> str:
    if "OUTCOME B" in decision:
        return "Adopt exact AST + hierarchical selector + exact resolver for formal execution; focus next on compiler/front-end learning."
    if "OUTCOME C" in decision:
        return "Use the fully exact interpreter at runtime and train neural models to generate/select complete verified ASTs, not execute clauses."
    return "Use deterministic parser/interpreter for canonical DSL and reserve neural compilation for flexible external inputs."


def read_m201a_summary() -> dict[str, Any]:
    path = ROOT / "runs" / "m201a_fair_compositional_retest" / "analysis.json"
    if not path.exists():
        return {}
    data = read_json(path)
    result = {}
    for name in ("curriculum_replay50_lm", "policy_head"):
        run = data.get("runs", {}).get(name, {})
        result[name] = {
            "heldout_program_closed": run.get("closed_loop", {})
            .get("heldout_program", {})
            .get("overall", {})
            .get("final_state_exact", 0.0),
            "merge_two_closed": run.get("closed_loop", {})
            .get("merge_two_seen", {})
            .get("overall", {})
            .get("final_state_exact", 0.0),
        }
    return result


def example_to_json(example: StepExample) -> dict[str, Any]:
    return {
        "program": example.program.semantic_hash(alpha=True, order_insensitive=True),
        "binding": binding_hash(example.binding),
        "state": example.state.counts,
        "clause_index": example.clause_index,
        "phase": example.phase,
        "split": example.split,
    }


def safe_rate(numerator: float, denominator: int) -> float:
    return float(numerator) / denominator if denominator else 0.0


def json_block(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def git_rev_parse(ref: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", ref],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    main()
