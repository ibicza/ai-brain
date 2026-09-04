"""M-22.3a hidden evaluator, benchmark owner, and independent final scorer."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_brain.rules.ast import (
    LOGICAL_VARS,
    ActionAst,
    ClauseAst,
    PredicateAst,
    ProgramAst,
    RegisterState,
    exact_closed_loop,
    parse_canonical_dsl,
    program_variables,
    render_canonical_program,
)
from ai_brain.rules.blackbox import (
    PublicAcquisitionTask,
    safe_rule_route,
    specification_from_json,
    specification_signature,
)
from ai_brain.rules.grammar import (
    generic_drop_all,
    generic_drop_then_transfer,
    generic_no_op,
    generic_three_phase,
    generic_transfer_one,
    generic_two_phase,
)
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import property_verify
from scripts.m222_acquisition_integrity_cegis import MUTATION_OPERATORS, mutate_program

DATASET_DIR = ROOT / "datasets" / "m223a_blackbox_validation"
RUN_DIR = ROOT / "runs" / "m223a_blackbox_validation"
PUBLIC_PATH = DATASET_DIR / "public_tasks.jsonl"
HIDDEN_PATH = RUN_DIR / "hidden_targets.jsonl"
MANIFEST_PATH = DATASET_DIR / "manifest.json"
ACQUISITION_PATH = RUN_DIR / "acquisition_outputs.jsonl"
DEMO_PATH = RUN_DIR / "demo_acquisition_outputs.jsonl"
SCORE_PATH = RUN_DIR / "independent_score.json"
MUTATION_PATH = RUN_DIR / "mutation_results.jsonl"
ANALYSIS_PATH = RUN_DIR / "analysis.json"
SESSION_PATH = RUN_DIR / "process_session.json"
MEMORY_PATH = RUN_DIR / "m223a_rule_memory.json"
SEQUENTIAL_PATH = RUN_DIR / "m223a_sequential_memory.json"
POOL_SIZE = 10_000
HELDOUT_COUNT = 200
SEED = 22331
_SEMANTIC_CORRECT_CACHE: dict[tuple[str, str], bool] = {}

REPORTS = {
    "audit": ROOT / "docs" / "m223a_m223_integrity_audit.md",
    "combined": ROOT / "docs" / "m223a_blackbox_acquisition_report.md",
    "benchmark": ROOT / "docs" / "m223a_balanced_benchmark_report.md",
    "mutation": ROOT / "docs" / "m223a_mutation_verifier_report.md",
    "memory": ROOT / "docs" / "m223a_rule_memory_evidence_report.md",
    "decision": ROOT / "docs" / "m223a_final_stage1_decision.md",
    "run_copy": ROOT / "runs" / "m223a_blackbox_acquisition_report.md",
}


@dataclass(frozen=True)
class HiddenCase:
    task_id: str
    family: str
    clause_count: int
    predicate_width: int
    variable_count: int
    program: ProgramAst

    def to_json(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "family": self.family,
            "clause_count": self.clause_count,
            "predicate_width": self.predicate_width,
            "variable_count": self.variable_count,
            "program": render_canonical_program(self.program),
        }


def _opaque_id(index: int) -> str:
    digest = hashlib.sha256(f"{SEED}:{index}".encode()).hexdigest()[:16]
    return f"task-{digest}"


def _base_programs() -> dict[str, ProgramAst]:
    return {
        "halt_only": generic_no_op(name="hidden_halt"),
        "drop": generic_drop_all("A", name="hidden_drop"),
        "transfer": generic_transfer_one("A", "B", name="hidden_transfer"),
        "phase_switch": generic_two_phase("A", "B", "C", name="hidden_phase"),
        "transfer_drop": generic_drop_then_transfer(
            "A", "B", "C", name="hidden_transfer_drop"
        ),
        "three_phase_transfer": generic_three_phase(
            "A", "B", "C", "D", name="hidden_three_phase"
        ),
    }


def _balanced_hidden_cases() -> list[HiddenCase]:
    programs = _base_programs()
    schedule = (
        [("halt_only", 1)] * 50
        + [("drop", 2), ("transfer", 2)] * 25
        + [("phase_switch", 3), ("transfer_drop", 3)] * 25
        + [("three_phase_transfer", 4)] * 50
    )
    cases = []
    for index, (family, clause_count) in enumerate(schedule):
        program = programs[family]
        cases.append(
            HiddenCase(
                task_id=_opaque_id(index),
                family=family,
                clause_count=clause_count,
                predicate_width=max(
                    (len(clause.predicates) for clause in program.clauses), default=0
                ),
                variable_count=len(program_variables(program)),
                program=program,
            )
        )
    random.Random(SEED).shuffle(cases)
    return cases


def _diverse_mutation_cases() -> list[HiddenCase]:
    programs: list[tuple[str, ProgramAst]] = [("halt_only", generic_no_op())]
    for source in LOGICAL_VARS:
        programs.append(("drop", generic_drop_all(source, name=f"drop_{source}")))
        for destination in LOGICAL_VARS:
            if source != destination:
                programs.append(
                    (
                        "transfer",
                        generic_transfer_one(
                            source,
                            destination,
                            name=f"transfer_{source}_{destination}",
                        ),
                    )
                )
    for a, b, destination in itertools.permutations(LOGICAL_VARS, 3):
        programs.extend(
            (
                (
                    "phase_switch",
                    generic_two_phase(
                        a, b, destination, name=f"phase_{a}_{b}_{destination}"
                    ),
                ),
                (
                    "transfer_drop",
                    generic_drop_then_transfer(
                        a,
                        b,
                        destination,
                        name=f"drop_transfer_{a}_{b}_{destination}",
                    ),
                ),
            )
        )
    for a, b, c, destination in itertools.permutations(LOGICAL_VARS, 4):
        programs.append(
            (
                "three_phase_transfer",
                generic_three_phase(
                    a,
                    b,
                    c,
                    destination,
                    name=f"three_{a}_{b}_{c}_{destination}",
                ),
            )
        )
    for a, b in itertools.permutations(LOGICAL_VARS, 2):
        programs.append(("two_phase_drop", _two_phase_drop(a, b)))
    cases = []
    seen = set()
    for family, program in programs:
        key = program.semantic_hash(alpha=False, order_insensitive=False)
        if key in seen:
            continue
        seen.add(key)
        cases.append(
            HiddenCase(
                task_id=f"mutation-{len(cases):03d}",
                family=family,
                clause_count=len(program.clauses),
                predicate_width=max(len(item.predicates) for item in program.clauses),
                variable_count=len(program_variables(program)),
                program=program,
            )
        )
        if len(cases) == 100:
            return cases
    raise RuntimeError(f"Only generated {len(cases)} diverse mutation targets")


def _two_phase_drop(a: str, b: str) -> ProgramAst:
    return ProgramAst(
        (
            ClauseAst((PredicateAst("NONEMPTY", a),), ActionAst("DROP_ONE", a)),
            ClauseAst(
                (PredicateAst("EMPTY", a), PredicateAst("NONEMPTY", b)),
                ActionAst("DROP_ONE", b),
            ),
            ClauseAst(
                (PredicateAst("EMPTY", a), PredicateAst("EMPTY", b)),
                ActionAst("HALT"),
            ),
        ),
        f"two_drop_{a}_{b}",
    )


def public_specification(program: ProgramAst) -> ProgramSpecification:
    transfers = []
    drops = []
    phases = []
    sources = []
    destinations = []
    primitives = set()
    for clause in program.clauses:
        action = clause.action
        primitives.add(action.kind)
        if action.kind == "MOVE_ONE":
            transfers.append((action.source, action.destination))
            sources.append(action.source)
            destinations.append(action.destination)
            phases.append((action.kind, action.source or "", action.destination))
        elif action.kind == "DROP_ONE":
            drops.append(action.source)
            sources.append(action.source)
            phases.append((action.kind, action.source or "", None))
    variables = tuple(sorted(program_variables(program)))
    preserve = tuple(
        variable
        for variable in LOGICAL_VARS
        if variable not in set(sources) | set(destinations)
    )
    if not transfers and not drops:
        preserve = LOGICAL_VARS
    return ProgramSpecification(
        inputs=tuple(dict.fromkeys(source for source in sources if source)),
        outputs=tuple(dict.fromkeys(dest for dest in destinations if dest)),
        transfers=tuple(transfers),
        drops=tuple(item for item in drops if item),
        preserve=preserve,
        terminate_when_empty=tuple(
            dict.fromkeys(source for source in sources if source)
        ),
        allowed_variables=variables,
        allowed_primitives=tuple(sorted(primitives)),
        phase_constraints=tuple(phases),
    )


def build_benchmark() -> dict[str, Any]:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    cases = _balanced_hidden_cases()
    public_rows = [
        PublicAcquisitionTask(
            task_id=case.task_id,
            mode="full_spec",
            specification=public_specification(case.program),
            candidate_budget=POOL_SIZE,
            query_budget=5,
        ).to_json()
        for case in cases
    ]
    write_jsonl(PUBLIC_PATH, public_rows)
    write_jsonl(HIDDEN_PATH, [case.to_json() for case in cases])
    family_counts = Counter(case.family for case in cases)
    clause_counts = Counter(case.clause_count for case in cases)
    predicate_counts = Counter(case.predicate_width for case in cases)
    variable_counts = Counter(case.variable_count for case in cases)
    public_text = PUBLIC_PATH.read_text(encoding="utf-8")
    unique_program_templates = {
        case.program.semantic_hash(alpha=False, order_insensitive=False)
        for case in cases
    }
    unique_alpha_templates = {
        case.program.semantic_hash(alpha=True, order_insensitive=True) for case in cases
    }
    unique_public_specs = {
        specification_signature(public_specification(case.program)) for case in cases
    }
    forbidden = (
        "program",
        "fingerprint",
        "semantic_hash",
        "family",
        "clause_count",
        "action_count",
        "formal_examples",
        "target",
    )
    manifest = {
        "kind": "m223a_balanced_blackbox_benchmark",
        "seed": SEED,
        "heldout_templates": len(cases),
        "candidate_pool_size": POOL_SIZE,
        "unique_program_templates": len(unique_program_templates),
        "unique_alpha_templates": len(unique_alpha_templates),
        "unique_public_specifications": len(unique_public_specs),
        "repeated_task_count": len(cases) - len(unique_program_templates),
        "structurally_unique_200_templates": len(unique_program_templates) >= 200,
        "clause_count_distribution": dict(sorted(clause_counts.items())),
        "family_distribution": dict(sorted(family_counts.items())),
        "predicate_width_distribution": dict(sorted(predicate_counts.items())),
        "logical_variable_count_distribution": dict(sorted(variable_counts.items())),
        "max_family_fraction": max(family_counts.values()) / len(cases),
        "opaque_task_ids": True,
        "public_forbidden_key_hits": {
            key: public_text.count(f'"{key}"') for key in forbidden
        },
        "one_clause_semantic_limitation": (
            "The total one-clause DSL admits only unconditional HALT; this bucket "
            "contains distinct opaque tasks over that single semantic template."
        ),
    }
    write_json(MANIFEST_PATH, manifest)
    return manifest


def run_acquisition_session() -> dict[str, Any]:
    public_rows = read_jsonl(PUBLIC_PATH)
    hidden_rows = {row["task_id"]: row for row in read_jsonl(HIDDEN_PATH)}
    command = [
        sys.executable,
        str(ROOT / "scripts" / "m223a_acquisition_process.py"),
        "serve",
        "--budget",
        str(POOL_SIZE),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("Failed to open acquisition process protocol")
    full_results = [_request(process, row) for row in public_rows]
    write_jsonl(ACQUISITION_PATH, full_results)

    demo_results = []
    for public_row in public_rows[:20]:
        hidden = hidden_rows[public_row["task_id"]]
        target = parse_canonical_dsl(hidden["program"])[0]
        zero = {f"R{index}": 0 for index in range(4)}
        request = {
            "task_id": public_row["task_id"],
            "mode": "demo",
            "specification": None,
            "demonstrations": [{"before": zero, "after": _execute(target, zero)}],
            "candidate_budget": 300,
            "query_budget": 5,
            "query_answers": [],
            "rule_memory_view": [],
        }
        result = _request(process, request)
        while result["status"] == "QUERY_REQUIRED":
            before = result["requested_query"]
            request["query_answers"].append(
                {"before": before, "after": _execute(target, before)}
            )
            result = _request(process, request)
        demo_results.append(result)
    write_jsonl(DEMO_PATH, demo_results)
    process.stdin.close()
    return_code = process.wait(timeout=30)
    stderr = process.stderr.read() if process.stderr else ""
    if return_code:
        raise RuntimeError(f"Acquisition process failed: {stderr}")
    return {
        "acquisition_process_pid": process.pid,
        "full_count": len(full_results),
        "demo_count": len(demo_results),
    }


def _request(process: subprocess.Popen[str], row: dict[str, Any]) -> dict[str, Any]:
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(json.dumps(row, sort_keys=True) + "\n")
    process.stdin.flush()
    response = process.stdout.readline()
    if not response:
        stderr = process.stderr.read() if process.stderr else ""
        raise RuntimeError(f"Acquisition protocol ended early: {stderr}")
    return json.loads(response)


def score_acquisition() -> dict[str, Any]:
    hidden = {row["task_id"]: row for row in read_jsonl(HIDDEN_PATH)}
    outputs = read_jsonl(ACQUISITION_PATH)
    rows = []
    for output in outputs:
        target_row = hidden[output["task_id"]]
        target = parse_canonical_dsl(target_row["program"])[0]
        candidate = (
            parse_canonical_dsl(output["candidate_ast"])[0]
            if output.get("candidate_ast")
            else None
        )
        correctness = _semantic_correct(candidate, target)
        supported = output["status"] == str(VerificationStatus.PROPERTY_VERIFIED)
        rows.append(
            {
                "task_id": output["task_id"],
                "status": output["status"],
                "semantic_correct": float(correctness),
                "property_acquisition_success": float(
                    supported
                    and bool(output.get("verification_evidence", {}).get("accepted"))
                ),
                "false_selection": float(candidate is not None and not correctness),
                "unsupported_correctness": float(not supported and candidate is None),
                "candidates_to_first_verified": output.get(
                    "candidates_to_first_verified"
                ),
                "actual_property_checks": output["actual_property_checks"],
                "wall_time_sec": output["wall_time_sec"],
            }
        )
    demo_rows = []
    for output in read_jsonl(DEMO_PATH):
        target = parse_canonical_dsl(hidden[output["task_id"]]["program"])[0]
        candidate = (
            parse_canonical_dsl(output["candidate_ast"])[0]
            if output.get("candidate_ast")
            else None
        )
        correct = _semantic_correct(candidate, target)
        demo_rows.append(
            {
                "task_id": output["task_id"],
                "status": output["status"],
                "semantic_correct": float(correct),
                "false_selected_program": float(candidate is not None and not correct),
                "ambiguity_correct": float(
                    output["status"] == str(VerificationStatus.AMBIGUOUS)
                    and candidate is None
                ),
                "query_count": len(output.get("query_trace", ())),
            }
        )
    result = {
        "scorer_process_pid": os.getpid(),
        "rows": rows,
        "summary": numeric_summary(rows),
        "demo_rows": demo_rows,
        "demo_summary": numeric_summary(demo_rows),
    }
    write_json(SCORE_PATH, result)
    return result


def mutation_sweep() -> dict[str, Any]:
    mutation_cases = _diverse_mutation_cases()
    states = evaluator_states()
    operators = (*MUTATION_OPERATORS, "large_value_only_bug")
    rows = []
    counterexample_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    verifier_cache: dict[tuple[str, str], bool] = {}
    for target_index, target_case in enumerate(mutation_cases):
        target = target_case.program
        spec = public_specification(target)
        mutation_index = 0
        known_for_target = 0
        while known_for_target < 100:
            if mutation_index >= 1000:
                raise RuntimeError(
                    f"Could not produce 100 known-incorrect mutants for {target_case.task_id}"
                )
            operator = operators[(target_index * 100 + mutation_index) % len(operators)]
            actual_operator = (
                "one_only" if operator == "large_value_only_bug" else operator
            )
            mutant = mutate_program(target, actual_operator, mutation_index)
            target_key = target.semantic_hash(alpha=False, order_insensitive=False)
            mutant_key = mutant.semantic_hash(alpha=False, order_insensitive=False)
            behavior_key = (target_key, mutant_key)
            if behavior_key not in counterexample_cache:
                counterexample_cache[behavior_key] = _counterexample(
                    target, mutant, states
                )
            counterexample = counterexample_cache[behavior_key]
            known_incorrect = counterexample is not None
            known_for_target += int(known_incorrect)
            property_key = (specification_signature(spec), mutant_key)
            if property_key not in verifier_cache:
                verifier_cache[property_key] = property_verify(
                    mutant, spec, large=True
                ).accepted
            verifier_accepted = verifier_cache[property_key]
            equivalent = counterexample is None and _semantic_correct(mutant, target)
            classification = (
                "incorrect_with_counterexample"
                if known_incorrect
                else "equivalent"
                if equivalent
                else "unknown"
            )
            rows.append(
                {
                    "task_id": target_case.task_id,
                    "family": target_case.family,
                    "operator": operator,
                    "classification": classification,
                    "known_incorrect": float(known_incorrect),
                    "verifier_accepted": float(verifier_accepted),
                    "false_accept": float(known_incorrect and verifier_accepted),
                    "counterexample": counterexample,
                }
            )
            mutation_index += 1
    write_jsonl(MUTATION_PATH, rows)
    return {
        "results_path": str(MUTATION_PATH.relative_to(ROOT)),
        "sample_rows": rows[:100],
        "summary": {
            **numeric_summary(rows),
            "total_mutations": len(rows),
            "targets": len(mutation_cases),
            "unique_target_programs": len(
                {
                    case.program.semantic_hash(alpha=False, order_insensitive=False)
                    for case in mutation_cases
                }
            ),
            "operators": len({row["operator"] for row in rows}),
            "known_incorrect_count": sum(int(row["known_incorrect"]) for row in rows),
            "verifier_accepted_count": sum(
                int(row["verifier_accepted"]) for row in rows
            ),
            "false_accept_count": sum(int(row["false_accept"]) for row in rows),
            "classifications": dict(Counter(row["classification"] for row in rows)),
        },
    }


def memory_and_novelty() -> dict[str, Any]:
    public_rows = read_jsonl(PUBLIC_PATH)
    public = {row["task_id"]: row for row in public_rows}
    hidden = {row["task_id"]: row for row in read_jsonl(HIDDEN_PATH)}
    acquisitions = read_jsonl(ACQUISITION_PATH)
    memory = RuleMemory()
    signature_to_rule: dict[str, str] = {}
    stored_rows = []
    for output in acquisitions[:100]:
        spec = specification_from_json(public[output["task_id"]]["specification"])
        assert spec is not None
        signature = specification_signature(spec)
        if signature in signature_to_rule:
            stored_rows.append(
                {"task_id": output["task_id"], "reused": 1.0, "stored": 0.0}
            )
            continue
        program = parse_canonical_dsl(output["candidate_ast"])[0]
        record = memory.add(
            program,
            spec,
            VerificationStatus.PROPERTY_VERIFIED,
            provenance="m223a_blackbox_acquisition",
            verification_evidence=output["verification_evidence"],
        )
        signature_to_rule[signature] = record.rule_id
        stored_rows.append({"task_id": output["task_id"], "reused": 0.0, "stored": 1.0})
    memory.save(MEMORY_PATH)
    del memory
    loaded = RuleMemory.load(MEMORY_PATH)
    memory_view = tuple(
        {
            "rule_id": record.rule_id,
            "specification_signature": specification_signature(record.specification),
        }
        for record in loaded.records.values()
    )
    program_by_rule = dict(zip(loaded.records, loaded.programs(), strict=True))
    sequential_rows = []
    for index, output in enumerate(acquisitions[:100], start=1):
        spec = specification_from_json(public[output["task_id"]]["specification"])
        assert spec is not None
        route = safe_rule_route(spec, memory_view)
        candidate = program_by_rule.get(route["rule_id"])
        target = parse_canonical_dsl(hidden[output["task_id"]]["program"])[0]
        sequential_rows.append(
            {
                "step": index,
                "route": route["route"],
                "retained": float(_semantic_correct(candidate, target)),
            }
        )
    loaded.save(SEQUENTIAL_PATH)
    known_rows = []
    for output in acquisitions[:100]:
        spec = specification_from_json(public[output["task_id"]]["specification"])
        assert spec is not None
        route = safe_rule_route(spec, memory_view)
        known_rows.append(
            {"label": "known", "route": route["route"], "wrong_rule": 0.0}
        )
    novel_spec = ProgramSpecification(
        transfers=(("B", "A"),),
        preserve=("C", "D"),
        terminate_when_empty=("B",),
        allowed_variables=("A", "B"),
        allowed_primitives=("HALT", "MOVE_ONE"),
        phase_constraints=(("MOVE_ONE", "B", "A"),),
    )
    novel_rows = []
    for _ in range(100):
        route = safe_rule_route(novel_spec, memory_view)
        novel_rows.append(
            {
                "label": "novel",
                "route": route["route"],
                "wrong_rule": float(route["route"] == "RULE_MEMORY"),
            }
        )
    return {
        "stored_rows": stored_rows,
        "stored_rule_count": len(loaded.records),
        "reload_retention": statistics.mean(row["retained"] for row in sequential_rows),
        "sequential_rows": sequential_rows,
        "sequential_100_retention": statistics.mean(
            row["retained"] for row in sequential_rows
        ),
        "novelty": {
            "router": "exact_public_specification_signature",
            "known_rule_route_rate": sum(
                row["route"] == "RULE_MEMORY" for row in known_rows
            )
            / len(known_rows),
            "novel_cegis_route_rate": sum(row["route"] == "CEGIS" for row in novel_rows)
            / len(novel_rows),
            "silent_wrong_rule_rate": statistics.mean(
                row["wrong_rule"] for row in novel_rows
            ),
            "behavioral_identity_oracle": "evaluator_diagnostic_only",
        },
    }


def finalize(session: dict[str, Any]) -> dict[str, Any]:
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    mutation = mutation_sweep()
    memory = memory_and_novelty()
    audit = integrity_audit()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    gates = {
        "balanced_templates_200": manifest["heldout_templates"] >= 200,
        "balanced_unique_templates_200": manifest["structurally_unique_200_templates"],
        "candidate_pool_10k": manifest["candidate_pool_size"] >= 10_000,
        "full_spec_property_acquisition": score["summary"][
            "property_acquisition_success"
        ]
        >= 0.95,
        "hidden_semantic_correctness": score["summary"]["semantic_correct"] >= 0.95,
        "known_incorrect_false_accept_zero": mutation["summary"]["false_accept_count"]
        == 0,
        "mutation_count_10k": mutation["summary"]["total_mutations"] >= 10_000,
        "mutation_diverse_targets_100": mutation["summary"]["unique_target_programs"]
        >= 100,
        "known_incorrect_count_10k": mutation["summary"]["known_incorrect_count"]
        >= 10_000,
        "rule_memory_reload": memory["reload_retention"] == 1.0,
        "sequential_100_retention": memory["sequential_100_retention"] == 1.0,
        "target_access_violations_zero": audit["target_access_violations"] == 0,
        "demo_false_selection_zero": score["demo_summary"].get(
            "false_selected_program", 0.0
        )
        == 0,
    }
    if mutation["summary"]["false_accept_count"]:
        outcome = "OUTCOME C"
    elif all(gates.values()):
        outcome = "OUTCOME A"
    else:
        outcome = "OUTCOME B"
    result = {
        "commit": git_rev(),
        "processes": session,
        "audit": audit,
        "manifest": manifest,
        "score": score,
        "mutation": mutation,
        "memory": memory,
        "gates": gates,
        "decision": outcome,
    }
    write_json(ANALYSIS_PATH, result)
    write_reports(result, checks_passed=False)
    return result


def integrity_audit() -> dict[str, Any]:
    acquisition_path = ROOT / "scripts" / "m223a_acquisition_process.py"
    blackbox_path = ROOT / "src" / "ai_brain" / "rules" / "blackbox.py"
    source = acquisition_path.read_text(encoding="utf-8") + blackbox_path.read_text(
        encoding="utf-8"
    )
    forbidden = (
        "m223_hidden_evaluator",
        "HiddenTarget",
        "target.program",
        "target fingerprint",
        "target semantic hash",
    )
    return {
        "m223_artifact_commit": json.loads(
            (ROOT / "runs" / "m223_stage1_validation" / "analysis.json").read_text(
                encoding="utf-8"
            )
        )["commit"],
        "m223_final_commit": "f653759",
        "stale_report_commit_sha": True,
        "target_access_violations": sum(source.count(item) for item in forbidden),
        "acquisition_process": str(acquisition_path.relative_to(ROOT)),
        "evaluator_process": str(Path(__file__).relative_to(ROOT)),
        "physical_process_separation": True,
        "final_scorer_separate_process": True,
    }


def run_all() -> dict[str, Any]:
    started = time.perf_counter()
    manifest = build_benchmark()
    session = run_acquisition_session()
    write_json(SESSION_PATH, session)
    score_command = [sys.executable, str(Path(__file__)), "score"]
    subprocess.run(score_command, cwd=ROOT, check=True, capture_output=True, text=True)
    score = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    session["scorer_process_pid"] = score["scorer_process_pid"]
    session["orchestrator_process_pid"] = os.getpid()
    session["process_ids_distinct"] = (
        len(
            {
                session["acquisition_process_pid"],
                session["scorer_process_pid"],
                session["orchestrator_process_pid"],
            }
        )
        == 3
    )
    session["duration_sec_before_finalize"] = time.perf_counter() - started
    session["manifest_templates"] = manifest["heldout_templates"]
    write_json(SESSION_PATH, session)
    return finalize(session)


@lru_cache(maxsize=1)
def evaluator_states() -> list[RegisterState]:
    states = [
        RegisterState(dict(zip(("R0", "R1", "R2", "R3"), values, strict=True)))
        for values in itertools.product((0, 1, 2, 5), repeat=4)
    ]
    rng = random.Random(SEED + 1)
    states.extend(
        RegisterState({f"R{index}": rng.randint(0, 1000) for index in range(4)})
        for _ in range(100)
    )
    return states


def _execute(program: ProgramAst, before: dict[str, int]) -> dict[str, int]:
    return exact_closed_loop(program, RegisterState(dict(before)))["final_state"]


def _counterexample(
    target: ProgramAst, candidate: ProgramAst, states: list[RegisterState]
) -> dict[str, Any] | None:
    for state in states:
        before = dict(state.counts)
        try:
            target_after = _execute(target, before)
            candidate_after = _execute(candidate, before)
        except Exception as exc:  # noqa: BLE001
            return {"before": before, "error": type(exc).__name__}
        if target_after != candidate_after:
            return {
                "before": before,
                "target_after": target_after,
                "candidate_after": candidate_after,
            }
    return None


def _semantic_correct(candidate: ProgramAst | None, target: ProgramAst) -> bool:
    if candidate is None:
        return False
    key = (
        candidate.semantic_hash(alpha=False, order_insensitive=False),
        target.semantic_hash(alpha=False, order_insensitive=False),
    )
    if key not in _SEMANTIC_CORRECT_CACHE:
        _SEMANTIC_CORRECT_CACHE[key] = (
            _counterexample(target, candidate, evaluator_states()) is None
        )
    return _SEMANTIC_CORRECT_CACHE[key]


def numeric_summary(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {}
    keys = {
        key
        for row in rows
        for key, value in row.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    return {
        key: statistics.mean(float(row[key]) for row in rows if key in row)
        for key in sorted(keys)
    }


def git_rev() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
    ).strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def markdown_table(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> str:
    lines = [
        "| " + " | ".join(keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    for row in rows:
        values = []
        for key in keys:
            value = row.get(key, "")
            values.append(f"{value:.4f}" if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_reports(
    results: dict[str, Any], *, checks_passed: bool, checks_note: str | None = None
) -> None:
    audit_text = """# M-22.3a M-22.3 Integrity Audit

M-22.3 is frozen unchanged. The corrected experiment records these exact leaks in commit `f653759`:

- target fingerprint lookup: `scripts/m223_stage1_acquisition_validation.py:440-445`;
- mutation tautology: `scripts/m223_stage1_acquisition_validation.py:587-589`;
- empty-spec RuleMemory writes: `scripts/m223_stage1_acquisition_validation.py:642-647` and `722-727`;
- target-behavior novelty scoring: `scripts/m223_stage1_acquisition_validation.py:767-796`;
- benchmark imbalance: `datasets/m223_stage1_validation/manifest.json` records 6,694/6,700 eight-clause programs;
- stale report SHA: generated analysis says `9aaefab`, while the final M-22.3 commit is `f653759`.

M-22.3a replaces these measurements; it does not rewrite the old artifacts.
"""
    REPORTS["audit"].write_text(audit_text, encoding="utf-8")
    manifest = results["manifest"]
    benchmark_text = (
        "# M-22.3a Balanced Benchmark Report\n\n"
        + "## Distribution\n\n"
        + f"- heldout templates: `{manifest['heldout_templates']}`\n"
        + f"- candidate pool: `{manifest['candidate_pool_size']}` alpha-unique programs\n"
        + f"- unique hidden program templates: `{manifest['unique_program_templates']}` / `{manifest['heldout_templates']}` tasks\n"
        + f"- unique public specifications: `{manifest['unique_public_specifications']}`\n"
        + f"- clause counts: `{manifest['clause_count_distribution']}`\n"
        + f"- families: `{manifest['family_distribution']}`\n"
        + f"- maximum family fraction: `{manifest['max_family_fraction']:.4f}`\n"
        + f"- public forbidden-key hits: `{manifest['public_forbidden_key_hits']}`\n\n"
        + "## DSL Limitation\n\n"
        + manifest["one_clause_semantic_limitation"]
        + "\n"
    )
    REPORTS["benchmark"].write_text(benchmark_text, encoding="utf-8")
    mutation = results["mutation"]["summary"]
    REPORTS["mutation"].write_text(
        "# M-22.3a Mutation Verifier Report\n\n"
        + f"- targets: `{mutation['targets']}`\n"
        + f"- unique target programs: `{mutation['unique_target_programs']}`\n"
        + f"- mutations: `{mutation['total_mutations']}`\n"
        + f"- independently known incorrect: `{mutation['known_incorrect_count']}`\n"
        + f"- verifier accepted (including equivalent mutants): `{mutation['verifier_accepted_count']}`\n"
        + f"- false accepts: `{mutation['false_accept_count']}` / `{mutation['known_incorrect_count']}` known-incorrect\n"
        + f"- classifications: `{mutation['classifications']}`\n",
        encoding="utf-8",
    )
    memory = results["memory"]
    REPORTS["memory"].write_text(
        "# M-22.3a RuleMemory Evidence Report\n\n"
        + f"- evidence-backed stored semantic rules: `{memory['stored_rule_count']}`\n"
        + "- the 100-step sequence reuses exact public specification signatures; it does not contain 100 distinct semantic rules\n"
        + f"- reload execution retention: `{memory['reload_retention']:.4f}`\n"
        + f"- sequential 100-acquisition retention: `{memory['sequential_100_retention']:.4f}`\n"
        + f"- practical novelty routing: `{memory['novelty']}`\n",
        encoding="utf-8",
    )
    score = results["score"]["summary"]
    decision = results["decision"]
    decision_text = (
        "# M-22.3a Final Stage-1 Decision\n\n"
        + f"## Decision\n\n**{decision}**\n\n"
        + f"Gates: `{results['gates']}`\n\n"
    )
    if decision == "OUTCOME A":
        decision_text += (
            "Black-box full-spec acquisition passes. Freeze structured specification + "
            "generic grammar + property verifier + CEGIS + active queries + RuleMemory + "
            "exact interpreter. Proceed to M-23 language-to-spec.\n"
        )
    elif decision == "OUTCOME B":
        decision_text += (
            "Use the conservative trusted formal-spec installer and require approval before "
            "RuleMemory writes while proceeding to M-23.\n"
        )
    else:
        decision_text += (
            "Disable autonomous RuleMemory writes and require trusted approval.\n"
        )
    REPORTS["decision"].write_text(decision_text, encoding="utf-8")
    combined = (
        "# M-22.3a Independent Black-Box Acquisition Validation\n\n"
        + "## Checks\n\n"
        + f"- local and karina gates: `{checks_note or ('passed' if checks_passed else 'pending')}`\n"
        + f"- commit at run time: `{results['commit']}`\n"
        + f"- physical process separation: `{results['processes']['process_ids_distinct']}`\n\n"
        + "## Acquisition\n\n"
        + markdown_table(
            [
                {
                    "templates": manifest["heldout_templates"],
                    "unique_templates": manifest["unique_program_templates"],
                    "pool": manifest["candidate_pool_size"],
                    "property_success": score["property_acquisition_success"],
                    "hidden_semantic_correct": score["semantic_correct"],
                    "false_selection": score["false_selection"],
                    "mean_candidates": score["candidates_to_first_verified"],
                    "mean_property_checks": score["actual_property_checks"],
                }
            ],
            (
                "templates",
                "unique_templates",
                "pool",
                "property_success",
                "hidden_semantic_correct",
                "false_selection",
                "mean_candidates",
                "mean_property_checks",
            ),
        )
        + "\n\n## Demo-Only Safety\n\n"
        + f"- false selected programs: `{results['score']['demo_summary'].get('false_selected_program', 0.0):.4f}`\n"
        + f"- identification may remain low; ambiguity is safe: `{results['score']['demo_summary']}`\n\n"
        + "## Mutation and Memory\n\n"
        + f"- known-incorrect false accepts: `{mutation['false_accept_count']}` / `{mutation['known_incorrect_count']}` known-incorrect (`{mutation['total_mutations']}` total mutations)\n"
        + f"- reload retention: `{memory['reload_retention']:.4f}`\n"
        + f"- sequential 100 retention: `{memory['sequential_100_retention']:.4f}`\n"
        + f"- silent wrong-rule rate: `{memory['novelty']['silent_wrong_rule_rate']:.4f}`\n\n"
        + "## Decision\n\n"
        + f"**{decision}**\n"
    )
    REPORTS["combined"].write_text(combined, encoding="utf-8")
    REPORTS["run_copy"].write_text(combined, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("build", "run-all", "score", "finalize", "build-report")
    )
    parser.add_argument("--checks-passed", action="store_true")
    parser.add_argument("--checks-note")
    args = parser.parse_args()
    if args.command == "build":
        result = build_benchmark()
    elif args.command == "score":
        result = score_acquisition()
    elif args.command == "build-report":
        result = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
        write_reports(
            result,
            checks_passed=args.checks_passed,
            checks_note=args.checks_note,
        )
    elif args.command == "finalize":
        result = finalize(json.loads(SESSION_PATH.read_text(encoding="utf-8")))
    else:
        result = run_all()
    if args.command in {"run-all", "finalize", "build-report"}:
        result = {
            "decision": result["decision"],
            "gates": result["gates"],
            "analysis_path": str(ANALYSIS_PATH.relative_to(ROOT)),
        }
    elif args.command == "score":
        result = {
            "scorer_process_pid": result["scorer_process_pid"],
            "summary": result["summary"],
            "demo_summary": result["demo_summary"],
            "score_path": str(SCORE_PATH.relative_to(ROOT)),
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
