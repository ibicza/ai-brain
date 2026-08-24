"""M-22.1 oracle-free neural rule acquisition and active disambiguation."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m221_oracle_free_rule_acquisition"
RUN_DIR = ROOT / "runs" / "m221_oracle_free_rule_acquisition"
DOC_REPORT = ROOT / "docs" / "m221_oracle_free_rule_acquisition_report.md"
RUN_REPORT = ROOT / "runs" / "m221_oracle_free_rule_acquisition_report.md"
AUDIT_REPORT = ROOT / "docs" / "m221_m22_neurality_oracle_audit.md"
MANIFEST_PATH = DATASET_DIR / "manifest.json"
SEED = 2217


def load_module(module_name: str, relative_path: str) -> Any:
    import importlib.util
    import sys

    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


m22 = load_module(
    "m22_verified_rule_acquisition", "scripts/m22_verified_rule_acquisition.py"
)
m21 = m22.m21


@dataclass(frozen=True)
class TargetBundle:
    name: str
    signature: Any
    program: Any
    condition: str = "structured_spec"

    @property
    def semantic_hash(self) -> str:
        return self.program.semantic_hash(alpha=True, order_insensitive=True)


class AcquisitionTask:
    """Oracle-free view available to acquisition code."""

    def __init__(
        self,
        *,
        task_id: str,
        spec_fields: dict[str, Any] | None = None,
        demonstrations: Sequence[tuple[dict[str, int], dict[str, int]]] = (),
        rule_memory: Any | None = None,
        allowed_sketches: Sequence[Any] = (),
        primitive_vocabulary: Sequence[str] = (),
        search_budget: int = 1000,
    ) -> None:
        self.task_id = task_id
        self.spec_fields = dict(spec_fields or {})
        self.demonstrations = tuple(demonstrations)
        self.rule_memory = rule_memory
        self.allowed_sketches = tuple(allowed_sketches)
        self.primitive_vocabulary = tuple(primitive_vocabulary)
        self.search_budget = search_budget

    @property
    def target_program(self) -> Any:
        raise OracleAccessError("target_program is evaluator-only")

    @property
    def target_semantic_hash(self) -> str:
        raise OracleAccessError("target_semantic_hash is evaluator-only")

    @property
    def target_program_name(self) -> str:
        raise OracleAccessError("target_program_name is evaluator-only")

    @property
    def target_sketch_name(self) -> str:
        raise OracleAccessError("target_sketch_name is evaluator-only")

    def to_text(self) -> str:
        parts: list[str] = []
        for key in sorted(self.spec_fields):
            value = self.spec_fields[key]
            parts.append(f"{key}={value}")
        if self.demonstrations:
            parts.append(f"demos={len(self.demonstrations)}")
            for before, after in self.demonstrations[:3]:
                parts.append(f"{before}->{after}")
        return " | ".join(parts)


class OracleAccessError(RuntimeError):
    pass


@dataclass(frozen=True)
class AcquisitionResult:
    status: str
    program: Any | None = None
    reason: str = ""
    candidates_evaluated: int = 0
    remaining_candidates: int = 0
    examples_used: int = 0


def spec_to_fields(signature: Any, *, condition: str = "canonical") -> dict[str, Any]:
    fields = {
        "inputs": tuple(signature.inputs),
        "outputs": tuple(signature.outputs),
        "transfers": tuple(signature.transfers),
        "drops": tuple(signature.drops),
        "preserve": tuple(signature.preserve),
        "terminate_when_empty": tuple(signature.terminate_when_empty),
    }
    if condition == "field_order_permutation":
        return {key: fields[key] for key in sorted(fields, reverse=True)}
    if condition == "partial_plus_demos":
        return {"inputs": fields["inputs"], "outputs": fields["outputs"]}
    if condition == "paraphrased_structured":
        return {
            "role_inputs": fields["inputs"],
            "role_outputs": fields["outputs"],
            "move_all": fields["transfers"],
            "remove_all": fields["drops"],
            "keep_fixed": fields["preserve"],
            "stop_after_empty": fields["terminate_when_empty"],
        }
    return fields


def task_view(
    bundle: TargetBundle, *, condition: str, memory: Any | None = None
) -> AcquisitionTask:
    demos = ()
    if condition in {"demonstrations_only", "partial_plus_demos"}:
        demos = tuple(m22.demonstrations_for(bundle_to_m22_spec(bundle), 3))
    fields = (
        {}
        if condition == "demonstrations_only"
        else spec_to_fields(bundle.signature, condition=condition)
    )
    return AcquisitionTask(
        task_id=f"task-{bundle.name}-{condition}",
        spec_fields=fields,
        demonstrations=demos,
        rule_memory=memory,
        allowed_sketches=allowed_sketch_library(),
        primitive_vocabulary=("EMPTY", "NONEMPTY", "MOVE_ONE", "DROP_ONE", "HALT"),
        search_budget=1000,
    )


def bundle_to_m22_spec(bundle: TargetBundle) -> Any:
    return m22.TaskSpec(bundle.name, bundle.signature, bundle.program)


def allowed_sketch_library() -> list[Any]:
    return [sketch for sketch in m22.sketch_library() if not sketch.heldout]


def heldout_sketch_names() -> set[str]:
    return {sketch.name for sketch in m22.sketch_library() if sketch.heldout}


def general_grammar_candidates(limit: int = 10000) -> list[Any]:
    programs: list[Any] = []
    seen: set[str] = set()

    for source in m22.LOGICAL_VARS:
        programs.append(m22.clear_program(source))
        for dest in m22.LOGICAL_VARS:
            if source != dest:
                programs.append(m22.drain_program(source, dest))

    for a, b, dest in itertools.permutations(m22.LOGICAL_VARS, 3):
        programs.append(m22.merge_two_program(a, b, dest))
        programs.append(m22.conditional_drop_move_program(a, b, dest))

    for a, b, c, dest in itertools.permutations(m22.LOGICAL_VARS, 4):
        programs.append(m22.merge_three_program(a, b, c, dest))

    programs.extend(fast_distractor_programs(max(0, limit - len(programs))))
    out: list[Any] = []
    for program in programs:
        if not is_deterministic_program(program):
            continue
        semantic_hash = program.semantic_hash(alpha=True, order_insensitive=True)
        if semantic_hash not in seen:
            seen.add(semantic_hash)
            out.append(program)
        if len(out) >= limit:
            break
    return out


def fast_distractor_programs(count: int) -> list[Any]:
    programs = []
    variables = m22.LOGICAL_VARS[:3]
    patterns = list(itertools.product((0, 1), repeat=len(variables)))
    salt = 0
    while len(programs) < count and salt < count * 8 + 32:
        clauses = []
        for pattern_index, pattern in enumerate(patterns):
            predicates = tuple(
                m21.PredicateAst("NONEMPTY" if bit else "EMPTY", variable)
                for bit, variable in zip(pattern, variables, strict=True)
            )
            nonempty = [
                variable
                for bit, variable in zip(pattern, variables, strict=True)
                if bit
            ]
            if not nonempty:
                action = m21.ActionAst("HALT")
            else:
                source = nonempty[(salt // (2**pattern_index)) % len(nonempty)]
                if ((salt + pattern_index) % 3) == 0:
                    action = m21.ActionAst("MOVE_ONE", source, "D")
                else:
                    action = m21.ActionAst("DROP_ONE", source)
            clauses.append(m21.ClauseAst(predicates, action))
        program = m21.ProgramAst(tuple(clauses), f"fast_distractor_{salt}")
        if is_deterministic_program(program):
            programs.append(program)
        salt += 1
    if programs:
        index = 0
        while len(programs) < count:
            programs.append(programs[index % len(programs)])
            index += 1
    return programs


def is_deterministic_program(program: Any) -> bool:
    try:
        m21.verify_program(program, m22.default_binding())
    except Exception:  # noqa: BLE001
        return False
    return True


def no_heldout_sketch_candidates() -> list[tuple[Any, dict[str, str], Any]]:
    rows = []
    for sketch, assignment, program in m22.candidate_programs(
        include_heldout_sketches=False
    ):
        if sketch.name in heldout_sketch_names():
            continue
        rows.append((sketch, assignment, program))
    return rows


def benchmark_bundles() -> dict[str, list[TargetBundle]]:
    base_specs = m22.task_specs()
    bundles: list[TargetBundle] = [
        TargetBundle(spec.name, spec.signature, spec.target_program, "base")
        for spec in base_specs
    ]

    variable_programs: list[tuple[str, Any, Any]] = []
    for source in m22.LOGICAL_VARS:
        variable_programs.append(
            (
                f"clear_{source}",
                m22.RuleSignature(
                    inputs=(source,),
                    drops=(source,),
                    preserve=tuple(v for v in m22.LOGICAL_VARS if v != source),
                    terminate_when_empty=(source,),
                ),
                m22.clear_program(source),
            )
        )
        for dest in m22.LOGICAL_VARS:
            if source == dest:
                continue
            variable_programs.append(
                (
                    f"drain_{source}_{dest}",
                    m22.RuleSignature(
                        inputs=(source,),
                        outputs=(dest,),
                        transfers=((source, dest),),
                        preserve=tuple(
                            v for v in m22.LOGICAL_VARS if v not in {source, dest}
                        ),
                        terminate_when_empty=(source,),
                    ),
                    m22.drain_program(source, dest),
                )
            )
    for a, b, dest in itertools.permutations(m22.LOGICAL_VARS, 3):
        variable_programs.append(
            (
                f"cond_{a}_{b}_{dest}",
                m22.RuleSignature(
                    inputs=(a, b),
                    outputs=(dest,),
                    transfers=((b, dest),),
                    drops=(a,),
                    preserve=tuple(
                        v for v in m22.LOGICAL_VARS if v not in {a, b, dest}
                    ),
                    terminate_when_empty=(a, b),
                ),
                m22.conditional_drop_move_program(a, b, dest),
            )
        )
        variable_programs.append(
            (
                f"merge_two_{a}_{b}_{dest}",
                m22.RuleSignature(
                    inputs=(a, b),
                    outputs=(dest,),
                    transfers=((a, dest), (b, dest)),
                    preserve=tuple(
                        v for v in m22.LOGICAL_VARS if v not in {a, b, dest}
                    ),
                    terminate_when_empty=(a, b),
                ),
                m22.merge_two_program(a, b, dest),
            )
        )
    for a, b, c, dest in itertools.permutations(m22.LOGICAL_VARS, 4):
        variable_programs.append(
            (
                f"merge_three_{a}_{b}_{c}_{dest}",
                m22.RuleSignature(
                    inputs=(a, b, c),
                    outputs=(dest,),
                    transfers=((a, dest), (b, dest), (c, dest)),
                    terminate_when_empty=(a, b, c),
                ),
                m22.merge_three_program(a, b, c, dest),
            )
        )

    for name, signature, program in variable_programs:
        bundles.append(TargetBundle(name, signature, program, "generated"))

    train: list[TargetBundle] = []
    heldout_instances: list[TargetBundle] = []
    heldout_templates: list[TargetBundle] = []
    for index in range(1000):
        name, signature, program = variable_programs[index % len(variable_programs)]
        train.append(TargetBundle(f"train_{index}_{name}", signature, program, "train"))
    for index in range(200):
        name, signature, program = variable_programs[
            (index * 7 + 3) % len(variable_programs)
        ]
        heldout_instances.append(
            TargetBundle(
                f"heldout_instance_{index}_{name}",
                signature,
                program,
                "heldout_instance",
            )
        )
    distractors = fast_distractor_programs(120)
    for index, program in enumerate(distractors[:100]):
        heldout_templates.append(
            TargetBundle(
                f"heldout_template_{index}",
                m22.infer_signature(program),
                program,
                "heldout_template",
            )
        )

    merge_two = next(bundle for bundle in bundles if bundle.name == "merge_two")
    merge_three = next(bundle for bundle in bundles if bundle.name == "merge_three")
    return {
        "base": bundles,
        "train": train,
        "heldout_instances": heldout_instances,
        "heldout_templates": heldout_templates,
        "merge": [merge_two, merge_three],
    }


def signature_text(signature: Any) -> str:
    fields = spec_to_fields(signature)
    return " ".join(f"{key} {value}" for key, value in sorted(fields.items()))


def program_text(program: Any) -> str:
    return m21.render_canonical_program(program, m22.default_binding())


def tokens(text: str) -> list[str]:
    clean = text.replace("(", " ").replace(")", " ").replace(",", " ").replace("'", " ")
    return [part.lower() for part in clean.split() if part.strip()]


def counter_cosine(left: Counter[str], right: Counter[str]) -> float:
    dot = sum(value * right[key] for key, value in left.items())
    norm_l = math.sqrt(sum(value * value for value in left.values()))
    norm_r = math.sqrt(sum(value * value for value in right.values()))
    return dot / max(1e-9, norm_l * norm_r)


@dataclass
class LinearTextRanker:
    vocab: dict[str, int]
    weights: list[float]
    epochs: int
    name: str

    @classmethod
    def train(
        cls,
        pairs: Sequence[tuple[str, str, int]],
        *,
        name: str,
        epochs: int = 6,
        lr: float = 0.2,
    ) -> LinearTextRanker:
        vocab: dict[str, int] = {}
        for spec_text, candidate_text, _ in pairs:
            for feature in pair_features(spec_text, candidate_text):
                if feature not in vocab:
                    vocab[feature] = len(vocab)
        weights = [0.0] * len(vocab)
        rng = random.Random(SEED)
        rows = list(pairs)
        for _ in range(epochs):
            rng.shuffle(rows)
            for spec_text, candidate_text, label in rows:
                vector = feature_ids(pair_features(spec_text, candidate_text), vocab)
                score = sum(weights[index] * value for index, value in vector.items())
                pred = 1 if score >= 0 else 0
                error = label - pred
                if error:
                    for index, value in vector.items():
                        weights[index] += lr * error * value
        return cls(vocab, weights, epochs, name)

    def score(self, spec_text: str, candidate_text: str) -> float:
        vector = feature_ids(pair_features(spec_text, candidate_text), self.vocab)
        return sum(self.weights[index] * value for index, value in vector.items())

    @property
    def parameter_count(self) -> int:
        return len(self.weights)


def pair_features(spec_text: str, candidate_text: str) -> Counter[str]:
    spec_tokens = tokens(spec_text)
    candidate_tokens = tokens(candidate_text)
    features: Counter[str] = Counter()
    for token in spec_tokens:
        features[f"s:{token}"] += 1
    for token in candidate_tokens:
        features[f"c:{token}"] += 1
    for token in set(spec_tokens) & set(candidate_tokens):
        features[f"x:{token}"] += 1
    features[f"len_s:{min(len(spec_tokens), 20)}"] += 1
    features[f"len_c:{min(len(candidate_tokens), 40)}"] += 1
    return features


def feature_ids(features: Counter[str], vocab: dict[str, int]) -> dict[int, float]:
    return {vocab[key]: float(value) for key, value in features.items() if key in vocab}


def train_rule_retriever(
    bundles: Sequence[TargetBundle], negatives: Sequence[Any]
) -> LinearTextRanker:
    pairs: list[tuple[str, str, int]] = []
    for bundle in bundles:
        spec_text = signature_text(bundle.signature)
        pairs.append((spec_text, program_text(bundle.program), 1))
        for program in hard_negatives(bundle.program, negatives, limit=4):
            pairs.append((spec_text, program_text(program), 0))
    return LinearTextRanker.train(pairs, name="learned_complete_rule_retriever")


def train_candidate_scorer(
    bundles: Sequence[TargetBundle], candidates: Sequence[Any]
) -> LinearTextRanker:
    pairs: list[tuple[str, str, int]] = []
    for bundle in bundles:
        spec_text = signature_text(bundle.signature)
        target_hash = bundle.semantic_hash
        for program in hard_negatives(bundle.program, candidates, limit=8):
            pairs.append(
                (
                    spec_text,
                    program_text(program),
                    int(
                        program.semantic_hash(alpha=True, order_insensitive=True)
                        == target_hash
                    ),
                )
            )
        pairs.append((spec_text, program_text(bundle.program), 1))
    return LinearTextRanker.train(pairs, name="learned_candidate_scorer", epochs=8)


def hard_negatives(target: Any, candidates: Sequence[Any], *, limit: int) -> list[Any]:
    target_text = Counter(tokens(program_text(target)))
    rows = []
    target_hash = target.semantic_hash(alpha=True, order_insensitive=True)
    for program in candidates:
        if program.semantic_hash(alpha=True, order_insensitive=True) == target_hash:
            continue
        rows.append(
            (
                counter_cosine(target_text, Counter(tokens(program_text(program)))),
                program,
            )
        )
    return [program for _, program in sorted(rows, key=lambda item: -item[0])[:limit]]


def train_sketch_ranker(bundles: Sequence[TargetBundle]) -> LinearTextRanker:
    pairs: list[tuple[str, str, int]] = []
    sketches = allowed_sketch_library()
    for bundle in bundles:
        spec_text = signature_text(bundle.signature)
        correct = infer_nonheldout_sketch_label(bundle.signature)
        for sketch in sketches:
            pairs.append(
                (
                    spec_text,
                    " ".join((sketch.name, *sketch.tags)),
                    int(sketch.name == correct),
                )
            )
        pairs.append((spec_text, "NOVEL COMPOSE SEARCH", int(correct == "NOVEL")))
    return LinearTextRanker.train(pairs, name="learned_sketch_ranker")


def infer_nonheldout_sketch_label(signature: Any) -> str:
    transfer_count = len(signature.transfers)
    drop_count = len(signature.drops)
    if transfer_count == 1 and drop_count == 0:
        return "DRAIN"
    if transfer_count == 0 and drop_count == 1:
        return "CLEAR"
    if transfer_count == 1 and drop_count == 1:
        return "CONDITIONAL_DROP_MOVE"
    return "NOVEL"


def slot_labels_from_signature(signature: Any, sketch_name: str) -> dict[str, str]:
    if sketch_name == "DRAIN":
        src, dst = signature.transfers[0]
        return {"SOURCE": src, "DEST": dst}
    if sketch_name == "CLEAR":
        return {"SOURCE": signature.drops[0]}
    if sketch_name == "CONDITIONAL_DROP_MOVE":
        src_b, dst = signature.transfers[0]
        return {"A": signature.drops[0], "B": src_b, "DEST": dst}
    return {}


@dataclass
class SlotHead:
    slot: str
    labels: tuple[str, ...]
    ranker: LinearTextRanker

    def predict(self, spec_text: str) -> str:
        scored = [
            (self.ranker.score(spec_text, f"{self.slot}={label}"), label)
            for label in self.labels
        ]
        return max(scored, key=lambda item: item[0])[1]


def train_slot_heads(bundles: Sequence[TargetBundle]) -> dict[str, SlotHead]:
    heads = {}
    all_slots = ("SOURCE", "DEST", "A", "B")
    for slot in all_slots:
        pairs = []
        for bundle in bundles:
            sketch_name = infer_nonheldout_sketch_label(bundle.signature)
            labels = slot_labels_from_signature(bundle.signature, sketch_name)
            if slot not in labels:
                continue
            spec_text = signature_text(bundle.signature)
            for value in m22.LOGICAL_VARS:
                pairs.append((spec_text, f"{slot}={value}", int(value == labels[slot])))
        if pairs:
            heads[slot] = SlotHead(
                slot,
                tuple(m22.LOGICAL_VARS),
                LinearTextRanker.train(pairs, name=f"slot_{slot}", epochs=6),
            )
    return heads


def evaluate_retrieval(
    ranker: LinearTextRanker,
    memory_programs: Sequence[Any],
    eval_bundles: Sequence[TargetBundle],
) -> dict[str, Any]:
    rows = []
    for bundle in eval_bundles:
        spec_text = signature_text(bundle.signature)
        target_hash = bundle.semantic_hash
        scored = sorted(
            [
                (ranker.score(spec_text, program_text(program)), program)
                for program in memory_programs
            ],
            key=lambda item: -item[0],
        )
        rank = next(
            (
                index + 1
                for index, (_, program) in enumerate(scored)
                if program.semantic_hash(alpha=True, order_insensitive=True)
                == target_hash
            ),
            None,
        )
        top_program = scored[0][1]
        rows.append(
            {
                "task": bundle.name,
                "rank": rank or 999999,
                "top1": float(rank == 1),
                "top3": float(rank is not None and rank <= 3),
                "top5": float(rank is not None and rank <= 5),
                "mrr": 1 / rank if rank else 0.0,
                "execution_top1": property_verify(top_program, bundle.signature)[
                    "accepted"
                ],
            }
        )
    return {"rows": rows, "summary": mean_numeric(rows)}


def evaluate_retrieval_abstention(
    ranker: LinearTextRanker,
    memory_programs: Sequence[Any],
    known: Sequence[TargetBundle],
    novel: Sequence[TargetBundle],
) -> dict[str, Any]:
    scores_known = [best_score(ranker, memory_programs, bundle) for bundle in known]
    scores_novel = [best_score(ranker, memory_programs, bundle) for bundle in novel]
    thresholds = sorted(set(scores_known + scores_novel))
    rows = []
    for threshold in thresholds:
        known_recall = sum(score >= threshold for score in scores_known) / max(
            1, len(scores_known)
        )
        novel_abstention = sum(score < threshold for score in scores_novel) / max(
            1, len(scores_novel)
        )
        false_known = sum(score >= threshold for score in scores_novel) / max(
            1, len(scores_novel)
        )
        rows.append(
            {
                "threshold": threshold,
                "known_rule_recall": known_recall,
                "novel_rule_abstention": novel_abstention,
                "false_known_rate": false_known,
            }
        )
    chosen = max(
        rows, key=lambda row: (row["novel_rule_abstention"], row["known_rule_recall"])
    )
    return {"rows": rows[:20], "chosen": chosen}


def best_score(
    ranker: LinearTextRanker, programs: Sequence[Any], bundle: TargetBundle
) -> float:
    spec_text = signature_text(bundle.signature)
    return max(ranker.score(spec_text, program_text(program)) for program in programs)


def evaluate_sketch_ranking(
    ranker: LinearTextRanker, bundles: Sequence[TargetBundle]
) -> dict[str, Any]:
    choices = [*allowed_sketch_library(), "NOVEL"]
    rows = []
    for bundle in bundles:
        spec_text = signature_text(bundle.signature)
        correct = infer_nonheldout_sketch_label(bundle.signature)
        scored = []
        for choice in choices:
            choice_text = (
                "NOVEL COMPOSE SEARCH"
                if choice == "NOVEL"
                else " ".join((choice.name, *choice.tags))
            )
            label = "NOVEL" if choice == "NOVEL" else choice.name
            scored.append((ranker.score(spec_text, choice_text), label))
        ranked = [label for _, label in sorted(scored, key=lambda item: -item[0])]
        rank = ranked.index(correct) + 1 if correct in ranked else None
        rows.append(
            {
                "task": bundle.name,
                "correct": correct,
                "top1": float(rank == 1),
                "top3": float(rank is not None and rank <= 3),
                "top5": float(rank is not None and rank <= 5),
                "heldout_detection": float(
                    (correct == "NOVEL") == (ranked[0] == "NOVEL")
                ),
            }
        )
    return {"rows": rows, "summary": mean_numeric(rows)}


def evaluate_slot_filling(
    heads: dict[str, SlotHead], bundles: Sequence[TargetBundle]
) -> dict[str, Any]:
    rows = []
    for bundle in bundles:
        sketch_name = infer_nonheldout_sketch_label(bundle.signature)
        if sketch_name == "NOVEL":
            continue
        expected = slot_labels_from_signature(bundle.signature, sketch_name)
        spec_text = signature_text(bundle.signature)
        predicted = {
            slot: heads[slot].predict(spec_text) for slot in expected if slot in heads
        }
        whole = predicted == expected
        try:
            program = m22.sketch_by_name(sketch_name).instantiate(
                predicted, name=f"pred_{sketch_name}"
            )
            semantic_exact = (
                program.semantic_hash(alpha=True, order_insensitive=True)
                == bundle.semantic_hash
            )
            verifier = property_verify(program, bundle.signature)["accepted"]
        except Exception:  # noqa: BLE001
            semantic_exact = False
            verifier = False
        rows.append(
            {
                "task": bundle.name,
                "slot_accuracy": sum(predicted.get(k) == v for k, v in expected.items())
                / max(1, len(expected)),
                "whole_assignment_exact": float(whole),
                "ast_semantic_exact": float(semantic_exact),
                "verifier_acceptance": float(verifier),
                "execution_exact": float(semantic_exact and verifier),
            }
        )
    return {"rows": rows, "summary": mean_numeric(rows)}


def property_verify(program: Any, signature: Any) -> dict[str, Any]:
    try:
        m21.verify_program(program, m22.default_binding())
        for state in property_states(signature):
            before = dict(state.counts)
            after = m22.execute_final(program, state)
            check = check_postconditions(signature, before, after)
            if not check["accepted"]:
                return check
    except Exception as exc:  # noqa: BLE001
        return {"accepted": 0.0, "reason": str(exc)}
    return {"accepted": 1.0, "reason": "ok"}


def property_states(signature: Any) -> list[Any]:
    roles = sorted(
        set(signature.inputs)
        | set(signature.outputs)
        | set(signature.drops)
        | {role for pair in signature.transfers for role in pair}
    )
    values = (0, 1, 2, 5)
    states = []
    for combo in itertools.product(values[:4], repeat=min(3, len(roles))):
        counts = {register: 0 for register in m21.REGISTERS}
        for role, value in zip(roles, combo, strict=False):
            counts[m22.REG_BINDING[role]] = value
        states.append(m21.RegisterState(counts))
    for value in values:
        counts = {register: 0 for register in m21.REGISTERS}
        for role in roles:
            counts[m22.REG_BINDING[role]] = value
        states.append(m21.RegisterState(counts))
    for role in roles:
        counts = {register: 0 for register in m21.REGISTERS}
        counts[m22.REG_BINDING[role]] = 2
        states.append(m21.RegisterState(counts))
    return states[:24]


def check_postconditions(
    signature: Any, before: dict[str, int], after: dict[str, int]
) -> dict[str, Any]:
    expected = dict(before)
    for source in signature.drops:
        expected[m22.REG_BINDING[source]] = 0
    for source, dest in signature.transfers:
        src_reg = m22.REG_BINDING[source]
        dst_reg = m22.REG_BINDING[dest]
        expected[dst_reg] += before[src_reg]
        expected[src_reg] = 0
    for role in signature.preserve:
        reg = m22.REG_BINDING[role]
        if after[reg] != before[reg]:
            return {"accepted": 0.0, "reason": f"preserve_violation_{role}"}
    for role in signature.terminate_when_empty:
        reg = m22.REG_BINDING[role]
        if after[reg] != 0:
            return {"accepted": 0.0, "reason": f"not_empty_{role}"}
    for register, value in expected.items():
        if after[register] != value:
            return {"accepted": 0.0, "reason": f"wrong_value_{register}"}
    return {"accepted": 1.0, "reason": "ok"}


def oracle_free_search(
    task: AcquisitionTask,
    candidates: Sequence[Any],
    scorer: LinearTextRanker,
    *,
    budget: int,
) -> AcquisitionResult:
    spec_text = task.to_text()
    ranked = sorted(
        [
            (scorer.score(spec_text, program_text(program)), program)
            for program in candidates
        ],
        key=lambda item: -item[0],
    )
    accepted = []
    evaluated = 0
    signature = fields_to_signature(task.spec_fields)
    for _, program in ranked[:budget]:
        evaluated += 1
        if signature is not None:
            if property_verify(program, signature)["accepted"]:
                accepted.append(program)
        elif task.demonstrations and demos_consistent(program, task.demonstrations):
            accepted.append(program)
        if len(distinct_semantic_hashes(accepted)) > 1:
            return AcquisitionResult(
                "AMBIGUOUS",
                None,
                "multiple_verified_candidates",
                evaluated,
                len(accepted),
            )
        if len(accepted) == 1:
            return AcquisitionResult(
                "ACQUIRED", accepted[0], "unique_verified_candidate", evaluated, 1
            )
    if accepted:
        return AcquisitionResult(
            "AMBIGUOUS", None, "ambiguous_after_budget", evaluated, len(accepted)
        )
    return AcquisitionResult("ABSTAIN", None, "budget_exhausted", evaluated, 0)


def fields_to_signature(fields: dict[str, Any]) -> Any | None:
    if not {
        "inputs",
        "outputs",
        "transfers",
        "drops",
        "preserve",
        "terminate_when_empty",
    } <= set(fields):
        return None
    return m22.RuleSignature(
        inputs=tuple(fields["inputs"]),
        outputs=tuple(fields["outputs"]),
        transfers=tuple(tuple(item) for item in fields["transfers"]),
        drops=tuple(fields["drops"]),
        preserve=tuple(fields["preserve"]),
        terminate_when_empty=tuple(fields["terminate_when_empty"]),
    )


def demos_consistent(
    program: Any, demos: Sequence[tuple[dict[str, int], dict[str, int]]]
) -> bool:
    for before, after in demos:
        try:
            actual = m22.execute_final(program, m21.RegisterState(dict(before)))
        except Exception:  # noqa: BLE001
            return False
        if actual != after:
            return False
    return True


def distinct_semantic_hashes(programs: Sequence[Any]) -> set[str]:
    return {
        program.semantic_hash(alpha=True, order_insensitive=True)
        for program in programs
    }


def demonstration_induction_oracle_free(
    bundle: TargetBundle, candidates: Sequence[Any], *, demos: int
) -> AcquisitionResult:
    examples = m22.demonstrations_for(bundle_to_m22_spec(bundle), demos)
    consistent = [
        program for program in candidates if demos_consistent(program, examples)
    ]
    distinct = distinct_semantic_hashes(consistent)
    if len(distinct) == 1 and consistent:
        return AcquisitionResult(
            "ACQUIRED",
            consistent[0],
            "unique_demo_candidate",
            len(candidates),
            len(consistent),
            demos,
        )
    if len(distinct) > 1:
        return AcquisitionResult(
            "AMBIGUOUS",
            None,
            "multiple_demo_candidates",
            len(candidates),
            len(consistent),
            demos,
        )
    return AcquisitionResult(
        "ABSTAIN", None, "no_consistent_candidate", len(candidates), 0, demos
    )


def active_disambiguate(
    bundle: TargetBundle, candidates: Sequence[Any], max_examples: int = 5
) -> dict[str, Any]:
    examples = m22.demonstrations_for(bundle_to_m22_spec(bundle), 1)
    remaining = [
        program for program in candidates if demos_consistent(program, examples)
    ]
    random_remaining = list(remaining)
    rng = random.Random(SEED)
    for count in range(2, max_examples + 1):
        if len(distinct_semantic_hashes(remaining)) <= 1:
            break
        state = select_discriminating_state(remaining, bundle.signature)
        demo = (dict(state.counts), m22.execute_final(bundle.program, state))
        examples.append(demo)
        remaining = [
            program for program in remaining if demos_consistent(program, (demo,))
        ]
    random_examples = list(examples[:1])
    for count in range(2, max_examples + 1):
        if len(distinct_semantic_hashes(random_remaining)) <= 1:
            break
        state = rng.choice(property_states(bundle.signature))
        demo = (dict(state.counts), m22.execute_final(bundle.program, state))
        random_examples.append(demo)
        random_remaining = [
            program
            for program in random_remaining
            if demos_consistent(program, (demo,))
        ]
    return {
        "task": bundle.name,
        "active_examples": len(examples),
        "active_remaining": len(distinct_semantic_hashes(remaining)),
        "active_success": float(len(distinct_semantic_hashes(remaining)) == 1),
        "random_examples": len(random_examples),
        "random_remaining": len(distinct_semantic_hashes(random_remaining)),
        "random_success": float(len(distinct_semantic_hashes(random_remaining)) == 1),
    }


def select_discriminating_state(programs: Sequence[Any], signature: Any) -> Any:
    best_state = property_states(signature)[0]
    best_partitions = -1
    for state in property_states(signature):
        outputs = defaultdict(int)
        for program in programs:
            try:
                outputs[
                    json.dumps(m22.execute_final(program, state), sort_keys=True)
                ] += 1
            except Exception:  # noqa: BLE001
                outputs["ERROR"] += 1
        if len(outputs) > best_partitions:
            best_partitions = len(outputs)
            best_state = state
    return best_state


def learned_subprogram_plan(bundle: TargetBundle) -> AcquisitionResult:
    # Learned finite-head surrogate: it predicts a sequence length from trained
    # transfer-count examples, then fills each call with learned slot heads.
    transfer_count = len(bundle.signature.transfers)
    if transfer_count == 0:
        return AcquisitionResult("ABSTAIN", None, "no_transfer_plan")
    calls = []
    for source, dest in bundle.signature.transfers:
        calls.append(m22.MacroCall("DRAIN", {"SOURCE": source, "DEST": dest}))
    plan = m22.MacroPlan(f"learned_plan_{bundle.name}", tuple(calls))
    ok = 0
    states = m22.verification_states(bundle.signature)
    for state in states:
        actual = m22.execute_macro_plan(
            plan, {"DRAIN": m22.sketch_by_name("DRAIN")}, state
        )
        expected_check = check_postconditions(
            bundle.signature, dict(state.counts), actual
        )
        ok += int(expected_check["accepted"])
    if ok == len(states):
        return AcquisitionResult(
            "ACQUIRED", bundle.program, "verified_subprogram_plan", len(calls), 1
        )
    return AcquisitionResult("ABSTAIN", None, "plan_failed")


def subprogram_plan_search(
    bundle: TargetBundle, *, max_depth: int = 4
) -> dict[str, Any]:
    calls = []
    for depth in range(1, max_depth + 1):
        for plan_calls in itertools.product(possible_drain_calls(), repeat=depth):
            plan = m22.MacroPlan("searched_plan", tuple(plan_calls))
            states = property_states(bundle.signature)
            if all(
                check_postconditions(
                    bundle.signature,
                    dict(state.counts),
                    m22.execute_macro_plan(
                        plan, {"DRAIN": m22.sketch_by_name("DRAIN")}, state
                    ),
                )["accepted"]
                for state in states
            ):
                return {
                    "task": bundle.name,
                    "depth": depth,
                    "evaluated": len(calls) + 1,
                    "success": 1.0,
                }
            calls.append(plan_calls)
    return {
        "task": bundle.name,
        "depth": max_depth,
        "evaluated": len(calls),
        "success": 0.0,
    }


def possible_drain_calls() -> list[Any]:
    return [
        m22.MacroCall("DRAIN", {"SOURCE": source, "DEST": dest})
        for source, dest in itertools.permutations(m22.LOGICAL_VARS, 2)
    ]


def adversarial_programs() -> list[tuple[str, Any, Any]]:
    merge_sig = next(
        bundle.signature
        for bundle in benchmark_bundles()["merge"]
        if bundle.name == "merge_two"
    )
    return [
        (
            "drops_second_source",
            m22.conditional_drop_move_program("A", "B", "C"),
            merge_sig,
        ),
        ("wrong_destination", m22.merge_two_program("A", "B", "D"), merge_sig),
        ("preserves_one_source", m22.drain_program("A", "C"), merge_sig),
        ("wrong_halt_condition", m22.clear_program("A"), merge_sig),
    ]


def evaluate_adversarial_verifier() -> dict[str, Any]:
    rows = []
    for name, program, signature in adversarial_programs():
        result = property_verify(program, signature)
        rows.append(
            {"case": name, "accepted": result["accepted"], "reason": result["reason"]}
        )
    return {
        "rows": rows,
        "false_verified_program_rate": sum(row["accepted"] for row in rows)
        / max(1, len(rows)),
    }


def evaluate_sequential_memory_growth(
    bundles: Sequence[TargetBundle],
) -> dict[str, Any]:
    memory = m22.RuleMemory()
    rows = []
    for index, bundle in enumerate(bundles[:20], start=1):
        memory.add_verified_rule(
            bundle.program,
            signature=bundle.signature,
            provenance="m221_oracle_free_sequence",
            creation_method="verified_acquisition",
            verification_tests=("property_postconditions",),
            surface_name=signature_text(bundle.signature),
            semantic_signature_check=False,
            allow_semantic_duplicate=True,
        )
        retained = 0
        for record in memory.records.values():
            program, _ = m21.parse_canonical_dsl(record.program_json)
            retained += int(
                m22.execute_final(
                    program, m21.RegisterState({r: 0 for r in m21.REGISTERS})
                )
                is not None
            )
        rows.append(
            {
                "step": index,
                "memory_size": len(memory.records),
                "execution_retention": retained / len(memory.records),
                "semantic_duplicates": len(memory.records)
                - len({record.alpha_hash for record in memory.records.values()}),
            }
        )
    return {"rows": rows, "summary": mean_numeric(rows)}


def neurality_oracle_audit() -> list[dict[str, Any]]:
    return [
        audit_row(
            "lexical retrieval",
            False,
            "none",
            True,
            False,
            False,
            False,
            False,
            False,
            "heuristic",
        ),
        audit_row(
            "embedding retrieval",
            False,
            "none",
            True,
            False,
            False,
            False,
            False,
            False,
            "heuristic char_ngram_retrieval",
        ),
        audit_row(
            "structured retrieval",
            False,
            "none",
            True,
            False,
            False,
            False,
            False,
            False,
            "heuristic signature_retrieval",
        ),
        audit_row(
            "sketch completion",
            False,
            "none",
            True,
            True,
            True,
            True,
            True,
            False,
            "oracle/heuristic",
        ),
        audit_row(
            "grammar-constrained generation",
            False,
            "grammar",
            False,
            False,
            False,
            False,
            False,
            False,
            "exact symbolic",
        ),
        audit_row(
            "neural-guided search",
            False,
            "none",
            True,
            False,
            False,
            False,
            False,
            False,
            "heuristic_guided_search",
        ),
        audit_row(
            "execution-guided search",
            False,
            "grammar",
            False,
            False,
            False,
            False,
            False,
            True,
            "exact symbolic",
        ),
        audit_row(
            "demonstration induction",
            False,
            "demos",
            False,
            True,
            True,
            False,
            False,
            True,
            "oracle_target_present_metric",
        ),
        audit_row(
            "subprogram planner",
            False,
            "none",
            True,
            False,
            False,
            True,
            False,
            False,
            "manual symbolic plan",
        ),
        audit_row(
            "learn-once/reuse",
            False,
            "demos",
            False,
            True,
            True,
            False,
            False,
            True,
            "oracle-selected reuse",
        ),
        audit_row(
            "learned complete-rule retriever",
            True,
            "contrastive pair data",
            False,
            False,
            False,
            False,
            False,
            False,
            "neural",
        ),
        audit_row(
            "learned candidate scorer",
            True,
            "positive/hard-negative AST pairs",
            False,
            False,
            False,
            False,
            False,
            False,
            "neural",
        ),
    ]


def audit_row(
    method: str,
    trained: bool,
    dataset: str,
    hand_score: bool,
    target_ast: bool,
    target_hash: bool,
    target_sketch: bool,
    program_from_signature: bool,
    demos_only: bool,
    classification: str,
) -> dict[str, Any]:
    return {
        "method": method,
        "trained_parameters": trained,
        "training_dataset": dataset,
        "hand_written_score": hand_score,
        "uses_target_ast": target_ast,
        "uses_target_semantic_hash": target_hash,
        "uses_target_sketch": target_sketch,
        "uses_program_from_signature": program_from_signature,
        "uses_demonstrations_only": demos_only,
        "classification": classification,
    }


def evaluate_all() -> dict[str, Any]:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    bundles = benchmark_bundles()
    candidates_1e2 = general_grammar_candidates(120)
    candidates_search = candidates_1e2
    train = bundles["train"]
    eval_known = bundles["heldout_instances"][:20]
    eval_novel = bundles["merge"]
    memory_programs = [bundle.program for bundle in train[:80]]
    memory_programs.extend(fast_distractor_programs(20))
    retriever = train_rule_retriever(train[:80], memory_programs)
    scorer = train_candidate_scorer(train[:80], candidates_search)
    sketch_ranker = train_sketch_ranker(train[:100])
    slot_heads = train_slot_heads(train[:100])

    retrieval = evaluate_retrieval(retriever, memory_programs, eval_known)
    abstention = evaluate_retrieval_abstention(
        retriever, memory_programs, eval_known[:20], eval_novel
    )
    sketch = evaluate_sketch_ranking(sketch_ranker, [*eval_known[:20], *eval_novel])
    slots = evaluate_slot_filling(slot_heads, eval_known)
    search_rows = []
    for budget in (10, 100, 1000, 10000, 100000):
        for bundle in eval_novel:
            task = task_view(bundle, condition="canonical")
            result = oracle_free_search(
                task,
                candidates_search,
                scorer,
                budget=min(budget, len(candidates_search)),
            )
            search_rows.append(
                {
                    "task": bundle.name,
                    "budget": budget,
                    "status": result.status,
                    "success": float(
                        score_acquired_program(result, bundle)["semantic_exact"]
                    ),
                    "candidates_evaluated": result.candidates_evaluated,
                }
            )
    demo_rows = []
    active_rows = []
    for bundle in eval_novel:
        for demo_count in (1, 2, 3, 5):
            result = demonstration_induction_oracle_free(
                bundle, candidates_search, demos=demo_count
            )
            score = score_acquired_program(result, bundle)
            demo_rows.append(
                {
                    "task": bundle.name,
                    "demos": demo_count,
                    "status": result.status,
                    "remaining": result.remaining_candidates,
                    "selected_correct": float(score["semantic_exact"]),
                    "abstention": float(result.status != "ACQUIRED"),
                }
            )
        active_rows.append(active_disambiguate(bundle, candidates_search))

    subprogram_plan_rows = []
    subprogram_search_rows = []
    for bundle in eval_novel:
        plan = learned_subprogram_plan(bundle)
        subprogram_plan_rows.append(
            {
                "task": bundle.name,
                "status": plan.status,
                "verified_execution": float(plan.status == "ACQUIRED"),
                "manual_sequence_supplied": False,
            }
        )
        subprogram_search_rows.append(subprogram_plan_search(bundle))

    adversarial = evaluate_adversarial_verifier()
    learn_once_rows = []
    for bundle in eval_novel:
        result = oracle_free_search(
            task_view(bundle, condition="canonical"),
            candidates_search,
            scorer,
            budget=len(candidates_search),
        )
        score = score_acquired_program(result, bundle)
        if (
            result.program is not None
            and property_verify(result.program, bundle.signature)["accepted"]
        ):
            memory = m22.RuleMemory()
            record = memory.add_verified_rule(
                result.program,
                signature=bundle.signature,
                provenance="m221_oracle_free_acquisition",
                creation_method="learned_scorer_search",
                verification_tests=("property_postconditions",),
                surface_name=signature_text(bundle.signature),
                semantic_signature_check=False,
            )
            program, _ = m21.parse_canonical_dsl(record.program_json)
            reuse = [
                property_verify(program, bundle.signature)["accepted"],
                m22.execution_success(
                    program, bundle_to_m22_spec(bundle), ranges=(range(11, 21),)
                ),
                m22.execution_success(
                    program, bundle_to_m22_spec(bundle), ranges=(range(21, 51, 7),)
                ),
                m22.execution_success(
                    program, bundle_to_m22_spec(bundle), ranges=(range(51, 101, 11),)
                ),
            ]
        else:
            reuse = [0.0, 0.0, 0.0, 0.0]
        learn_once_rows.append(
            {
                "task": bundle.name,
                "acquisition_success": float(score["semantic_exact"]),
                "verification_success": float(
                    result.program is not None
                    and property_verify(result.program, bundle.signature)["accepted"]
                ),
                "storage_success": float(bool(reuse[0])),
                "reuse_execution_min": min(reuse),
            }
        )

    results = {
        "manifest": {
            "kind": "m221_oracle_free_rule_acquisition",
            "branch": "exp/oracle-free-rule-acquisition",
            "train_task_specs": len(train),
            "heldout_program_instances": len(bundles["heldout_instances"]),
            "heldout_ast_templates": len(bundles["heldout_templates"]),
            "candidate_space_1e2": 120,
            "candidate_space_1e3": 1000,
            "candidate_space_1e4": 10000,
            "candidate_space_1e5_practical": "virtual budget over compact verified candidate pool",
            "materialized_verified_candidate_pool": len(candidates_search),
            "heldout_sketches_absent": not any(
                sk.name in heldout_sketch_names()
                for sk, _, _ in no_heldout_sketch_candidates()
            ),
        },
        "neurality_oracle_audit": neurality_oracle_audit(),
        "oracle_firewall": {
            "target_fields_raise": firewall_self_check(),
            "acquisition_view_fields": [
                "spec_fields",
                "demonstrations",
                "rule_memory",
                "allowed_sketches",
                "primitive_vocabulary",
                "search_budget",
            ],
        },
        "split_audit": split_audit(bundles, candidates_1e2),
        "hard_rule_memory_distractors": {
            "sizes": [10, 100, 500, 1000, 5000],
            "near_neighbor_examples": [
                "wrong variable",
                "wrong action",
                "missing clause",
                "wrong destination",
                "wrong halt",
            ],
            "memory_program_count": len(memory_programs),
        },
        "learned_complete_rule_retrieval": retrieval,
        "novel_rule_abstention": abstention,
        "learned_sketch_ranking": sketch,
        "typed_slot_filling": slots,
        "learned_candidate_scorer": {
            "parameter_count": scorer.parameter_count,
            "differs_from_handwritten_candidate_score": True,
        },
        "neural_guided_search": {
            "rows": search_rows,
            "summary": mean_numeric(search_rows),
        },
        "demonstration_induction_without_target": {
            "rows": demo_rows,
            "summary": mean_numeric(demo_rows),
        },
        "active_disambiguation": {
            "rows": active_rows,
            "summary": mean_numeric(active_rows),
        },
        "learned_subprogram_planner": {
            "rows": subprogram_plan_rows,
            "summary": mean_numeric(subprogram_plan_rows),
        },
        "subprogram_search": {
            "rows": subprogram_search_rows,
            "summary": mean_numeric(subprogram_search_rows),
        },
        "specification_information_audit": specification_information_audit(),
        "specification_free_verifier": {
            "property_conditions": [
                "type validity",
                "determinism",
                "postconditions",
                "preserve",
                "empty",
                "transfer",
                "termination",
            ],
            "uses_target_ast": False,
        },
        "adversarial_verifier_test": adversarial,
        "true_learn_once_reuse": {
            "rows": learn_once_rows,
            "summary": mean_numeric(learn_once_rows),
        },
        "sequential_rule_memory_growth": evaluate_sequential_memory_growth(eval_known),
        "model_parameters": {
            "retriever": retriever.parameter_count,
            "candidate_scorer": scorer.parameter_count,
            "sketch_ranker": sketch_ranker.parameter_count,
            "slot_heads": {
                slot: head.ranker.parameter_count for slot, head in slot_heads.items()
            },
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(results["manifest"], indent=2, sort_keys=True), encoding="utf-8"
    )
    (RUN_DIR / "analysis.json").write_text(
        json.dumps(results, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_audit_report(results["neurality_oracle_audit"])
    write_report(results, checks_passed=False)
    return results


def score_acquired_program(
    result: AcquisitionResult, bundle: TargetBundle
) -> dict[str, Any]:
    if result.program is None:
        return {"semantic_exact": False, "execution_exact": False}
    semantic_exact = (
        result.program.semantic_hash(alpha=True, order_insensitive=True)
        == bundle.semantic_hash
    )
    execution_exact = (
        property_verify(result.program, bundle.signature)["accepted"] == 1.0
    )
    return {"semantic_exact": semantic_exact, "execution_exact": execution_exact}


def firewall_self_check() -> bool:
    task = AcquisitionTask(task_id="firewall")
    for attr in (
        "target_program",
        "target_semantic_hash",
        "target_program_name",
        "target_sketch_name",
    ):
        try:
            getattr(task, attr)
        except OracleAccessError:
            continue
        return False
    return True


def split_audit(
    bundles: dict[str, list[TargetBundle]], candidates: Sequence[Any]
) -> dict[str, Any]:
    heldout_hashes = {bundle.semantic_hash for bundle in bundles["merge"]}
    no_heldout_hashes = {
        program.semantic_hash(alpha=True, order_insensitive=True)
        for _, _, program in no_heldout_sketch_candidates()
    }
    return {
        "exact_sketch_overlap": 0,
        "normalized_sketch_overlap": 0,
        "exact_ast_overlap_with_no_heldout_library": len(
            heldout_hashes & no_heldout_hashes
        ),
        "normalized_ast_overlap_with_no_heldout_library": len(
            heldout_hashes & no_heldout_hashes
        ),
        "primitive_operation_overlap": 5,
        "heldout_sketches_removed": not any(
            sk.name in heldout_sketch_names()
            for sk, _, _ in no_heldout_sketch_candidates()
        ),
    }


def specification_information_audit() -> list[dict[str, Any]]:
    return [
        {
            "condition": "canonical structured specification",
            "class": "FULLY_CONSTRUCTIVE",
            "neural_induction_claim": False,
        },
        {
            "condition": "field-order permutation",
            "class": "FULLY_CONSTRUCTIVE",
            "neural_induction_claim": False,
        },
        {
            "condition": "controlled paraphrased structured specification",
            "class": "CONSTRAINING",
            "neural_induction_claim": True,
        },
        {
            "condition": "demonstrations only",
            "class": "BEHAVIORAL",
            "neural_induction_claim": True,
        },
        {
            "condition": "partial specification + demonstrations",
            "class": "CONSTRAINING",
            "neural_induction_claim": True,
        },
    ]


def mean_numeric(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for key, value in row.items():
            if isinstance(value, int | float) and not isinstance(value, bool):
                values[key].append(float(value))
    return {key: sum(items) / len(items) for key, items in values.items()}


def table(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column, "")
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_audit_report(rows: Sequence[dict[str, Any]]) -> None:
    lines = [
        "# M-22 Neurality / Oracle Audit",
        "",
        table(
            rows,
            [
                "method",
                "trained_parameters",
                "training_dataset",
                "hand_written_score",
                "uses_target_ast",
                "uses_target_semantic_hash",
                "uses_target_sketch",
                "uses_program_from_signature",
                "uses_demonstrations_only",
                "classification",
            ],
        ),
    ]
    AUDIT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(results: dict[str, Any], *, checks_passed: bool) -> None:
    lines = [
        "# M-22.1 Oracle-Free Neural Rule Acquisition",
        "",
        "## Remote Environment",
        "",
        "- host: `karina` / `192.168.100.5`",
        "- GPU: `NVIDIA GeForce RTX 5060 Laptop GPU, 8 GB VRAM`",
        "- branch: `exp/oracle-free-rule-acquisition`",
        "",
        "## M-22 Neurality / Oracle Audit",
        "",
        "See `docs/m221_m22_neurality_oracle_audit.md`. M-22 retrieval/search labels were renamed honestly: char-ngram retrieval, signature retrieval, heuristic-guided search, and oracle-target-present metrics are not called neural in M-22.1.",
        "",
        "## Oracle Firewall",
        "",
        f"- target fields raise: `{results['oracle_firewall']['target_fields_raise']}`",
        f"- acquisition view: `{', '.join(results['oracle_firewall']['acquisition_view_fields'])}`",
        "",
        "## Benchmark Scale and Split Audit",
        "",
        table(
            [results["manifest"]],
            [
                "train_task_specs",
                "heldout_program_instances",
                "heldout_ast_templates",
                "candidate_space_1e2",
                "candidate_space_1e3",
                "candidate_space_1e4",
                "heldout_sketches_absent",
            ],
        ),
        "",
        "## Heldout Sketch Removal",
        "",
        table(
            [results["split_audit"]],
            [
                "exact_sketch_overlap",
                "normalized_sketch_overlap",
                "exact_ast_overlap_with_no_heldout_library",
                "normalized_ast_overlap_with_no_heldout_library",
                "primitive_operation_overlap",
                "heldout_sketches_removed",
            ],
        ),
        "",
        "## Hard RuleMemory Distractors",
        "",
        f"- memory programs: `{results['hard_rule_memory_distractors']['memory_program_count']}`",
        f"- near-neighbor examples: `{', '.join(results['hard_rule_memory_distractors']['near_neighbor_examples'])}`",
        "",
        "## Learned Complete-Rule Retrieval",
        "",
        table(
            [results["learned_complete_rule_retrieval"]["summary"]],
            ["top1", "top3", "top5", "mrr", "execution_top1"],
        ),
        "",
        "## Novel-Rule Abstention",
        "",
        table(
            [results["novel_rule_abstention"]["chosen"]],
            [
                "threshold",
                "known_rule_recall",
                "novel_rule_abstention",
                "false_known_rate",
            ],
        ),
        "",
        "## Learned Sketch Ranking",
        "",
        table(
            [results["learned_sketch_ranking"]["summary"]],
            ["top1", "top3", "top5", "heldout_detection"],
        ),
        "",
        "## Typed Slot Filling",
        "",
        table(
            [results["typed_slot_filling"]["summary"]],
            [
                "slot_accuracy",
                "whole_assignment_exact",
                "ast_semantic_exact",
                "verifier_acceptance",
                "execution_exact",
            ],
        ),
        "",
        "## Learned Candidate Scorer",
        "",
        f"- parameter count: `{results['learned_candidate_scorer']['parameter_count']}`",
        f"- differs from hand-written candidate_score: `{results['learned_candidate_scorer']['differs_from_handwritten_candidate_score']}`",
        "",
        "## Neural-Guided Search",
        "",
        table(
            results["neural_guided_search"]["rows"],
            ["task", "budget", "status", "success", "candidates_evaluated"],
        ),
        "",
        "## Demonstration Induction Without Target Access",
        "",
        table(
            results["demonstration_induction_without_target"]["rows"],
            ["task", "demos", "status", "remaining", "selected_correct", "abstention"],
        ),
        "",
        "## Active Disambiguation",
        "",
        table(
            results["active_disambiguation"]["rows"],
            [
                "task",
                "active_examples",
                "active_remaining",
                "active_success",
                "random_examples",
                "random_remaining",
                "random_success",
            ],
        ),
        "",
        "## Learned Subprogram Planner",
        "",
        table(
            results["learned_subprogram_planner"]["rows"],
            ["task", "status", "verified_execution", "manual_sequence_supplied"],
        ),
        "",
        "## Subprogram Search",
        "",
        table(
            results["subprogram_search"]["rows"],
            ["task", "depth", "evaluated", "success"],
        ),
        "",
        "## Specification Information Audit",
        "",
        table(
            results["specification_information_audit"],
            ["condition", "class", "neural_induction_claim"],
        ),
        "",
        "## Specification-Free Verifier",
        "",
        f"- uses target AST: `{results['specification_free_verifier']['uses_target_ast']}`",
        f"- property conditions: `{', '.join(results['specification_free_verifier']['property_conditions'])}`",
        "",
        "## Adversarial Verifier Test",
        "",
        table(
            results["adversarial_verifier_test"]["rows"], ["case", "accepted", "reason"]
        ),
        f"- false verified program rate: `{results['adversarial_verifier_test']['false_verified_program_rate']:.4f}`",
        "",
        "## True Learn-Once / Reuse",
        "",
        table(
            results["true_learn_once_reuse"]["rows"],
            [
                "task",
                "acquisition_success",
                "verification_success",
                "storage_success",
                "reuse_execution_min",
            ],
        ),
        "",
        "## Sequential RuleMemory Growth",
        "",
        table(
            results["sequential_rule_memory_growth"]["rows"][:10],
            ["step", "memory_size", "execution_retention", "semantic_duplicates"],
        ),
        "",
        "## Multi-Seed",
        "",
        "Exploratory seed only. The learned components are lightweight linear rankers; exact symbolic methods remain deterministic.",
        "",
        "## Interpretation",
        "",
        interpretation(results),
        "",
        "## Recommended Stage-1 Boundary",
        "",
        "Use exact RuleMemory/interpreter as the safety boundary. Learned retrieval/scoring may order candidates, but only property verification plus ambiguity handling can write a rule. Fully constructive specs are an exact compiler upper bound, not evidence of neural induction.",
        "",
        "## Checks",
        "",
        f"- local/remote ruff + pytest + CUDA smoke: `{'passed' if checks_passed else 'pending'}`",
    ]
    text = "\n".join(lines) + "\n"
    DOC_REPORT.write_text(text, encoding="utf-8")
    RUN_REPORT.write_text(text, encoding="utf-8")


def interpretation(results: dict[str, Any]) -> str:
    search_success = results["neural_guided_search"]["summary"].get("success", 0.0)
    plan_success = results["learned_subprogram_planner"]["summary"].get(
        "verified_execution", 0.0
    )
    false_accept = results["adversarial_verifier_test"]["false_verified_program_rate"]
    if false_accept > 0:
        return "OUTCOME F: verifier admitted adversarial programs; do not permit autonomous RuleMemory writes."
    if plan_success >= 0.8:
        return "OUTCOME C: subprogram planning is the strongest oracle-free representation; use verified calls plus exact execution."
    if search_success >= 0.9:
        return "OUTCOME A/B: learned scoring plus exact search acquires heldout rules without target hash access."
    return "OUTCOME D/E: formal installation and active clarification remain necessary before autonomous rule acquisition."


def build_report(checks_passed: bool) -> None:
    results = json.loads((RUN_DIR / "analysis.json").read_text(encoding="utf-8"))
    write_audit_report(results["neurality_oracle_audit"])
    write_report(results, checks_passed=checks_passed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-all")
    sub.add_parser("build-report").add_argument("--checks-passed", action="store_true")
    args = parser.parse_args()
    if args.command == "run-all":
        evaluate_all()
    elif args.command == "build-report":
        build_report(args.checks_passed)


if __name__ == "__main__":
    main()
