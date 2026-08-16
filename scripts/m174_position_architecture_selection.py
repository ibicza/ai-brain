from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ai_brain.eval.runner import eval_lm
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m174_position_architecture"
RUNS_DIR = ROOT / "runs" / "m174_position_architecture"
DOC_PATH = ROOT / "docs" / "m174_position_architecture_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m174_position_architecture_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 317400
TRAIN_PER_OP = 6000
EVAL_PER_OP = 100
SEQUENCE_LENGTH = 128
MAX_NEW_TOKENS = 32
FIT_STEPS = (5000, 10000, 20000)
OFFSETS = (0, 1, 2, 4, 8, 16, 32, 64)
PREFIX_LENGTHS = (0, 1, 2, 4, 8, 16, 32)
FACTORIAL_OFFSETS = (0, 8, 32)
FACTORIAL_PREFIX_LENGTHS = (0, 8, 32)
DISTRACTOR_TYPES = (
    "neutral",
    "random_vocab",
    "natural_phrase",
    "previous_arithmetic",
)
CONTEXTS = (
    "canonical",
    "task_prefix",
    "step_prefix",
    "state_prefix",
    "previous_result",
    "previous_operation",
    "language_parse_prefix",
)

Primitive = Literal["add", "sub"]


@dataclass(frozen=True)
class Case:
    op: Primitive
    a: int
    b: int

    @property
    def op_token(self) -> str:
        return "ADD" if self.op == "add" else "SUB"

    @property
    def sign(self) -> str:
        return "+" if self.op == "add" else "-"

    @property
    def result(self) -> int:
        return self.a + self.b if self.op == "add" else self.a - self.b

    @property
    def key(self) -> str:
        return f"{self.op}:{self.a}:{self.b}"


@dataclass(frozen=True)
class MethodSpec:
    name: str
    position_encoding: str
    position_shift_max: int = 0
    learning_rate: float = 3e-4
    train_path: Path = DATASET_DIR / "train_canonical.jsonl"
    eval_path: Path = DATASET_DIR / "eval_canonical_unseen.jsonl"
    steps: int = FIT_STEPS[-1]
    seed: int = SEED
    sequence_length: int = SEQUENCE_LENGTH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-fit")
    subparsers.add_parser("analyze")
    subparsers.add_parser("run-distractor-curriculum")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-fit":
        run_methods(method_specs())
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "run-distractor-curriculum":
        run_distractor_curriculum()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_methods(method_specs())
        analyze_all()
        run_distractor_curriculum()
        analyze_all()
        build_report(checks_passed=False)
    return 0


def method_specs() -> list[MethodSpec]:
    return [
        MethodSpec(
            name="absolute",
            position_encoding="absolute",
            seed=SEED + 1,
        ),
        MethodSpec(
            name="shifted_absolute_64",
            position_encoding="shifted_absolute",
            position_shift_max=64,
            seed=SEED + 2,
        ),
        MethodSpec(
            name="relative_shaw",
            position_encoding="relative",
            seed=SEED + 3,
        ),
        MethodSpec(
            name="randomized_absolute_128",
            position_encoding="randomized_absolute",
            position_shift_max=128,
            seed=SEED + 4,
        ),
        MethodSpec(
            name="nope",
            position_encoding="nope",
            seed=SEED + 5,
        ),
    ]


def prepare_datasets() -> None:
    rng = random.Random(SEED)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    splits = {op: _split_cases(op, rng) for op in ("add", "sub")}
    _write_jsonl(
        DATASET_DIR / "train_canonical.jsonl",
        _balanced_records(
            splits,
            rng,
            split="train",
            prompt_fn=_canonical_prompt,
            count_per_op=TRAIN_PER_OP,
        ),
    )
    _write_jsonl(
        DATASET_DIR / "eval_canonical_train_sample.jsonl",
        _records_for_cases(
            [
                case
                for op in ("add", "sub")
                for case in splits[op]["train"][:EVAL_PER_OP]
            ],
            split="train_sample",
            prompt_fn=_canonical_prompt,
        ),
    )
    _write_jsonl(
        DATASET_DIR / "eval_canonical_unseen.jsonl",
        _records_for_cases(
            [case for op in ("add", "sub") for case in splits[op]["eval"]],
            split="unseen",
            prompt_fn=_canonical_prompt,
        ),
    )
    _write_distractor_evals(splits)
    _write_factorial_evals(splits)
    _write_context_evals(splits)
    _write_prefix_curriculum_train(splits, rng)
    _write_manifest(splits)


def run_methods(specs: list[MethodSpec]) -> None:
    for spec in specs:
        output_dir = RUNS_DIR / spec.name
        checkpoint = _checkpoint_path(output_dir, spec.steps)
        if checkpoint.exists():
            print(f"skip existing fit run: {spec.name}")
            continue
        _train_spec(spec=spec, output_dir=output_dir)


def run_distractor_curriculum() -> None:
    analysis_path = RUNS_DIR / "analysis.json"
    if not analysis_path.exists():
        analyze_all()
    analysis = _read_json(analysis_path)
    best = analysis.get("best_position_robust", {})
    if best.get("status") != "complete":
        print("skip distractor curriculum: no fitted position-robust method")
        return
    spec = MethodSpec(
        name=f"prefix_curriculum_{best['method']}",
        train_path=DATASET_DIR / "train_distractor_prefix_curriculum.jsonl",
        eval_path=DATASET_DIR / "eval_canonical_unseen.jsonl",
        position_encoding=str(best["position_encoding"]),
        position_shift_max=int(best["position_shift_max"]),
        seed=SEED + 80,
        sequence_length=256,
    )
    output_dir = RUNS_DIR / spec.name
    checkpoint = _checkpoint_path(output_dir, spec.steps)
    if checkpoint.exists():
        print(f"skip existing distractor curriculum run: {spec.name}")
        return
    _train_spec(spec=spec, output_dir=output_dir)


def analyze_all() -> None:
    methods = _analyze_methods()
    analysis: dict[str, Any] = {
        "manifest": _read_json(DATASET_DIR / "manifest.json"),
        "methods": methods,
    }
    analysis["fit_gate"] = _fit_gate_summary(methods)
    analysis["best_position_robust"] = _best_position_robust(analysis)
    analysis["distractor_curriculum"] = _analyze_distractor_curriculum(analysis)
    analysis["semantic_context"] = _semantic_context_retest(analysis)
    analysis["composition_gate"] = _composition_gate(analysis)
    analysis["composition"] = {
        "status": "skipped",
        "reason": analysis["composition_gate"]["reason"],
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = _read_json(RUNS_DIR / "analysis.json")
    lines = [
        "# M-17.4 Position Architecture Selection Report",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        f"- device: `{_device_name(analysis)}`",
        "",
        "## Implementation Notes",
        "",
        "- Relative attention: Shaw et al.-style relation-aware self-attention using learned relative key/value embeddings indexed by clipped `j - i`; no learned absolute positional embedding is added in the primary relative run.",
        "- Randomized PE: Ruoss et al.-style ordered subset sampling. For each training row, the script samples `sequence_length` positions without replacement from a virtual range, sorts them, and uses those absolute embedding rows while preserving token order.",
        "- Sources: Shaw et al. 2018 https://arxiv.org/abs/1803.02155 ; Ruoss et al. 2023 https://arxiv.org/abs/2305.16843",
        "",
        "## Dataset Verification",
        "",
        _dataset_notes(analysis),
        "",
        "## Fit Gate",
        "",
        _fit_gate_table(analysis),
        "",
        "## Pure Offset Curves",
        "",
        _pure_offset_tables(analysis),
        "",
        "## Distractor Prefix Curves",
        "",
        _distractor_tables(analysis),
        "",
        "## Position x History Matrix",
        "",
        _factorial_tables(analysis),
        "",
        "## Distractor Curriculum Comparison",
        "",
        _distractor_curriculum_table(analysis),
        "",
        "## Semantic Context Retest",
        "",
        _semantic_context_table(analysis),
        "",
        "## Composition Retest",
        "",
        _composition_table(analysis),
        "",
        "## Recommended Default",
        "",
        _decision(analysis),
    ]
    text = "\n".join(lines)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def _train_spec(*, spec: MethodSpec, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = TrainConfig(
        train_path=spec.train_path,
        eval_path=spec.eval_path,
        tokenizer_path=TOKENIZER_PATH,
        output_dir=output_dir,
        model_config_name="arithmetic_3m",
        steps=spec.steps,
        batch_size=8,
        sequence_length=spec.sequence_length,
        loss_mode="answer-only",
        learning_rate=spec.learning_rate,
        grad_clip_norm=1.0,
        numeric_tokenization="digit_safe",
        position_encoding=spec.position_encoding,
        position_shift_max=spec.position_shift_max,
        seed=spec.seed,
        eval_every=2500,
        eval_batches=20,
        save_every=5000,
    )
    started = time.time()
    result = train_lm(config)
    (output_dir / "run_result.json").write_text(
        json.dumps(
            {
                "method_spec": _spec_payload(spec),
                "elapsed_seconds": time.time() - started,
                "train_result": result,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _analyze_methods() -> dict[str, Any]:
    result = {}
    for spec in method_specs():
        result[spec.name] = _analyze_method(spec)
    return result


def _analyze_method(spec: MethodSpec) -> dict[str, Any]:
    output_dir = RUNS_DIR / spec.name
    checkpoints = {}
    for step in FIT_STEPS:
        checkpoint = _checkpoint_path(output_dir, step)
        if not checkpoint.exists():
            checkpoints[str(step)] = {"status": "missing"}
            continue
        train_eval = _eval_checkpoint(
            checkpoint=checkpoint,
            eval_path=DATASET_DIR / "eval_canonical_train_sample.jsonl",
            output_dir=output_dir / "fit_eval" / f"step_{step:06d}" / "train",
            position_offset=0,
        )
        unseen_eval = _eval_checkpoint(
            checkpoint=checkpoint,
            eval_path=DATASET_DIR / "eval_canonical_unseen.jsonl",
            output_dir=output_dir / "fit_eval" / f"step_{step:06d}" / "unseen",
            position_offset=0,
        )
        checkpoints[str(step)] = {
            "status": "complete",
            "checkpoint": str(checkpoint),
            "train": train_eval,
            "unseen": unseen_eval,
            "train_loss": _metric_at_step(output_dir / "metrics.jsonl", step),
        }
    fit = _first_fit_checkpoint(checkpoints)
    if fit.get("status") != "complete":
        return {
            "status": "underfit",
            "method_spec": _spec_payload(spec),
            "fit": fit,
            "checkpoints": checkpoints,
        }
    checkpoint = Path(str(fit["checkpoint"]))
    return {
        "status": "complete",
        "method_spec": _spec_payload(spec),
        "fit": fit,
        "checkpoints": checkpoints,
        "pure_offsets": _pure_offset_curve(spec, checkpoint),
        "distractors": _distractor_curves(spec, checkpoint),
        "factorial": _factorial_matrix(spec, checkpoint),
    }


def _pure_offset_curve(spec: MethodSpec, checkpoint: Path) -> dict[str, Any]:
    return {
        str(offset): _eval_checkpoint(
            checkpoint=checkpoint,
            eval_path=DATASET_DIR / "eval_canonical_unseen.jsonl",
            output_dir=RUNS_DIR
            / spec.name
            / "robust_eval"
            / "pure"
            / f"offset_{offset}",
            position_offset=offset,
        )
        for offset in OFFSETS
    }


def _distractor_curves(spec: MethodSpec, checkpoint: Path) -> dict[str, Any]:
    result = {}
    for distractor in DISTRACTOR_TYPES:
        result[distractor] = {}
        for length in PREFIX_LENGTHS:
            result[distractor][str(length)] = _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=DATASET_DIR
                / "distractors"
                / distractor
                / f"prefix_{length}.jsonl",
                output_dir=RUNS_DIR
                / spec.name
                / "robust_eval"
                / "distractors"
                / distractor
                / f"prefix_{length}",
                position_offset=0,
            )
    return result


def _factorial_matrix(spec: MethodSpec, checkpoint: Path) -> dict[str, Any]:
    result = {}
    for prefix_length in FACTORIAL_PREFIX_LENGTHS:
        result[str(prefix_length)] = {}
        for offset in FACTORIAL_OFFSETS:
            result[str(prefix_length)][str(offset)] = _eval_checkpoint(
                checkpoint=checkpoint,
                eval_path=DATASET_DIR
                / "factorial"
                / f"neutral_prefix_{prefix_length}.jsonl",
                output_dir=RUNS_DIR
                / spec.name
                / "robust_eval"
                / "factorial"
                / f"prefix_{prefix_length}"
                / f"offset_{offset}",
                position_offset=offset,
            )
    return result


def _analyze_distractor_curriculum(analysis: dict[str, Any]) -> dict[str, Any]:
    best = analysis.get("best_position_robust", {})
    if best.get("status") != "complete":
        return {"status": "skipped", "reason": "no fitted position-robust method"}
    spec = MethodSpec(
        name=f"prefix_curriculum_{best['method']}",
        train_path=DATASET_DIR / "train_distractor_prefix_curriculum.jsonl",
        eval_path=DATASET_DIR / "eval_canonical_unseen.jsonl",
        position_encoding=str(best["position_encoding"]),
        position_shift_max=int(best["position_shift_max"]),
        seed=SEED + 80,
        sequence_length=256,
    )
    checkpoint = _checkpoint_path(RUNS_DIR / spec.name, spec.steps)
    if not checkpoint.exists():
        return {"status": "missing", "method_spec": _spec_payload(spec)}
    payload = {
        "status": "complete",
        "method": spec.name,
        "checkpoint": str(checkpoint),
        "method_spec": _spec_payload(spec),
        "canonical": _eval_checkpoint(
            checkpoint=checkpoint,
            eval_path=DATASET_DIR / "eval_canonical_unseen.jsonl",
            output_dir=RUNS_DIR / spec.name / "robust_eval" / "canonical",
            position_offset=0,
        ),
        "pure_offsets": _pure_offset_curve(spec, checkpoint),
        "distractors": _distractor_curves(spec, checkpoint),
        "factorial": _factorial_matrix(spec, checkpoint),
    }
    return payload


def _semantic_context_retest(analysis: dict[str, Any]) -> dict[str, Any]:
    candidate = analysis.get("distractor_curriculum", {})
    if candidate.get("status") != "complete":
        candidate = analysis.get("best_position_robust", {})
    if not _passes_semantic_entry_gate(candidate):
        return {
            "status": "skipped",
            "reason": "neutral/distractor prefix robustness did not reach >= .90",
        }
    checkpoint = Path(str(candidate["checkpoint"]))
    if not checkpoint.exists():
        spec = MethodSpec(**candidate["method_spec"])
        checkpoint = _checkpoint_path(RUNS_DIR / spec.name, spec.steps)
    result = {}
    for context in CONTEXTS:
        result[context] = _eval_checkpoint(
            checkpoint=checkpoint,
            eval_path=DATASET_DIR / "contexts" / f"{context}.jsonl",
            output_dir=RUNS_DIR / "semantic_context" / candidate["method"] / context,
            position_offset=0,
        )
    return {"status": "complete", "contexts": result}


def _composition_gate(analysis: dict[str, Any]) -> dict[str, Any]:
    candidate = analysis.get("distractor_curriculum", {})
    if candidate.get("status") != "complete":
        candidate = analysis.get("best_position_robust", {})
    canonical = _canonical_score(candidate)
    pure_min = _pure_min(candidate, max_offset=32)
    prefix_min = _prefix_min(candidate, max_length=16)
    semantic = analysis.get("semantic_context", {})
    semantic_min = 0.0
    if semantic.get("status") == "complete":
        semantic_min = min(_final_nem(value) for value in semantic["contexts"].values())
    passed = (
        canonical >= 0.98
        and pure_min >= 0.95
        and prefix_min >= 0.90
        and semantic_min >= 0.90
    )
    reason = (
        f"canonical={canonical:.4f}, pure_min={pure_min:.4f}, "
        f"prefix_min={prefix_min:.4f}, semantic_min={semantic_min:.4f}"
    )
    return {"should_run": passed, "reason": reason}


def _split_cases(op: Primitive, rng: random.Random) -> dict[str, list[Case]]:
    if op == "add":
        candidates = [Case(op, a, b) for a in range(10, 100) for b in range(10, 100)]
    else:
        candidates = [Case(op, a, b) for a in range(10, 100) for b in range(1, a + 1)]
    rng.shuffle(candidates)
    eval_cases = candidates[:EVAL_PER_OP]
    train_cases = candidates[EVAL_PER_OP:]
    return {"train": train_cases, "eval": eval_cases}


def _balanced_records(
    splits: dict[str, dict[str, list[Case]]],
    rng: random.Random,
    *,
    split: str,
    prompt_fn,
    count_per_op: int,
) -> list[dict[str, Any]]:
    records = []
    for op in ("add", "sub"):
        cases = splits[op]["train"]
        for index in range(count_per_op):
            case = rng.choice(cases)
            records.append(_record(case, prompt_fn(case), split, len(records)))
    rng.shuffle(records)
    return records


def _records_for_cases(
    cases: list[Case],
    *,
    split: str,
    prompt_fn,
) -> list[dict[str, Any]]:
    return [
        _record(case, prompt_fn(case), split, index) for index, case in enumerate(cases)
    ]


def _write_distractor_evals(splits: dict[str, dict[str, list[Case]]]) -> None:
    cases = [case for op in ("add", "sub") for case in splits[op]["eval"]]
    for distractor in DISTRACTOR_TYPES:
        for length in PREFIX_LENGTHS:
            path = DATASET_DIR / "distractors" / distractor / f"prefix_{length}.jsonl"
            _write_jsonl(
                path,
                _records_for_cases(
                    cases,
                    split=f"{distractor}_{length}",
                    prompt_fn=lambda case, d=distractor, n=length: _distractor_prompt(
                        case,
                        d,
                        n,
                    ),
                ),
            )


def _write_factorial_evals(splits: dict[str, dict[str, list[Case]]]) -> None:
    cases = [case for op in ("add", "sub") for case in splits[op]["eval"]]
    for length in FACTORIAL_PREFIX_LENGTHS:
        _write_jsonl(
            DATASET_DIR / "factorial" / f"neutral_prefix_{length}.jsonl",
            _records_for_cases(
                cases,
                split=f"factorial_neutral_{length}",
                prompt_fn=lambda case, n=length: _distractor_prompt(
                    case,
                    "neutral",
                    n,
                ),
            ),
        )


def _write_context_evals(splits: dict[str, dict[str, list[Case]]]) -> None:
    cases = [case for op in ("add", "sub") for case in splits[op]["eval"]]
    for context in CONTEXTS:
        _write_jsonl(
            DATASET_DIR / "contexts" / f"{context}.jsonl",
            _records_for_cases(
                cases,
                split=f"context_{context}",
                prompt_fn=lambda case, c=context: _context_prompt(case, c),
            ),
        )


def _write_prefix_curriculum_train(
    splits: dict[str, dict[str, list[Case]]],
    rng: random.Random,
) -> None:
    records = []
    for op in ("add", "sub"):
        for index in range(TRAIN_PER_OP):
            case = rng.choice(splits[op]["train"])
            distractor = rng.choice(DISTRACTOR_TYPES)
            length = rng.randint(0, 32)
            records.append(
                _record(
                    case,
                    _distractor_prompt(case, distractor, length, heldout=False),
                    "prefix_curriculum",
                    len(records),
                )
            )
    rng.shuffle(records)
    _write_jsonl(DATASET_DIR / "train_distractor_prefix_curriculum.jsonl", records)


def _write_manifest(splits: dict[str, dict[str, list[Case]]]) -> None:
    train_prompts = _prompts(DATASET_DIR / "train_canonical.jsonl")
    eval_prompts = _prompts(DATASET_DIR / "eval_canonical_unseen.jsonl")
    manifest = {
        "kind": "m174_position_architecture_selection",
        "seed": SEED,
        "train_per_op": TRAIN_PER_OP,
        "eval_per_op": EVAL_PER_OP,
        "sequence_length": SEQUENCE_LENGTH,
        "offsets": list(OFFSETS),
        "prefix_lengths": list(PREFIX_LENGTHS),
        "distractor_types": list(DISTRACTOR_TYPES),
        "prompt_intersections": len(train_prompts & eval_prompts),
        "case_counts": {
            op: {split: len(cases) for split, cases in payload.items()}
            for op, payload in splits.items()
        },
        "methods": [_spec_payload(spec) for spec in method_specs()],
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _canonical_prompt(case: Case) -> str:
    return f"{case.op_token} {case.a:02d} {case.sign} {case.b:02d}"


def _distractor_prompt(
    case: Case,
    distractor: str,
    length: int,
    *,
    heldout: bool = True,
) -> str:
    base = _canonical_prompt(case)
    if length <= 0:
        return base
    if distractor == "neutral":
        prefix = " ".join(["CTX"] * length)
    elif distractor == "random_vocab":
        words = [
            "ALPHA",
            "BRAVO",
            "CLOUD",
            "DELTA",
            "ECHO",
            "FLAME",
            "GLASS",
            "HARBOR",
            "IVORY",
            "JAZZ",
            "KILO",
            "LEMON",
            "MANGO",
            "NOVA",
            "OCEAN",
            "PULSE",
            "QUARTZ",
            "RIVER",
            "SOLAR",
            "TULIP",
        ]
        prefix = " ".join(
            words[(index * 7 + length) % len(words)] for index in range(length)
        )
    elif distractor == "natural_phrase":
        if not heldout:
            return f"{' '.join(['NOTE'] * length)}\n{base}"
        train_chunks = [
            "irrelevant note",
            "ignore this context",
            "background text only",
            "unrelated sentence",
        ]
        heldout_chunks = [
            "side remark only",
            "not part of task",
            "separate background",
            "unused instruction",
        ]
        chunks = heldout_chunks if heldout else train_chunks
        prefix = " ".join(chunks[index % len(chunks)] for index in range(length))
    elif distractor == "previous_arithmetic":
        lines = []
        for index in range(length):
            a = 10 + ((17 * index + 3 * length) % 80)
            b = 10 + ((11 * index + 5 * length) % 80)
            if heldout:
                lines.append(f"DONE ADD {a} + {b} = {a + b}")
            else:
                lines.append("D1+1=2")
        prefix = "\n".join(lines) if heldout else " ".join(lines)
    else:
        raise AssertionError(distractor)
    return f"{prefix}\n{base}"


def _context_prompt(case: Case, context: str) -> str:
    expr = f"{case.a:02d} {case.sign} {case.b:02d}"
    if context == "canonical":
        return _canonical_prompt(case)
    if context == "task_prefix":
        return f"TASK {case.op_token}\n{expr}"
    if context == "step_prefix":
        return f"STEP2 {case.op_token} {expr}"
    if context == "state_prefix":
        return f"STATE {case.a}\nOP {case.op_token}\nARG {case.b}"
    if context == "previous_result":
        return f"STEP1 RESULT {case.a}\n{case.op_token} {expr}"
    if context == "previous_operation":
        prev_a = max(1, case.a // 2)
        prev_b = case.a - prev_a
        return f"{prev_a} + {prev_b} = {case.a}\nSTEP2 {case.op_token} {expr}"
    if context == "language_parse_prefix":
        return f"OP {case.op_token}\nA {case.a}\nB {case.b}\nRUN"
    raise AssertionError(context)


def _record(case: Case, prompt: str, split: str, index: int) -> dict[str, Any]:
    return {
        "id": f"m174.{case.op}.{split}.{index:06d}",
        "task_type": f"m174.{case.op}",
        "prompt": prompt,
        "answer": f"FINAL {case.result}",
        "metadata": {
            "op": case.op_token,
            "a": case.a,
            "b": case.b,
            "answer_value": case.result,
            "case_key": case.key,
            "split": split,
        },
    }


def _eval_checkpoint(
    *,
    checkpoint: Path,
    eval_path: Path,
    output_dir: Path,
    position_offset: int,
) -> dict[str, Any]:
    summary_path = output_dir / "summary.json"
    if summary_path.exists():
        try:
            summary = _read_json(summary_path)
        except json.JSONDecodeError:
            summary_path.unlink()
            summary = eval_lm(
                checkpoint_path=checkpoint,
                eval_path=eval_path,
                tokenizer_path=TOKENIZER_PATH,
                output_dir=output_dir,
                max_new_tokens=MAX_NEW_TOKENS,
                numeric_tokenization="digit_safe",
                position_offset=position_offset,
            )["summary"]
    else:
        summary = eval_lm(
            checkpoint_path=checkpoint,
            eval_path=eval_path,
            tokenizer_path=TOKENIZER_PATH,
            output_dir=output_dir,
            max_new_tokens=MAX_NEW_TOKENS,
            numeric_tokenization="digit_safe",
            position_offset=position_offset,
        )["summary"]
    overall = summary.get("overall", summary)
    by_task = summary.get("by_task_type", {})
    return {
        "summary": summary,
        "final_nem": float(overall.get("final_normalized_exact_match", 0.0)),
        "normalized_exact_match": float(overall.get("normalized_exact_match", 0.0)),
        "false_answer_rate": float(overall.get("false_answer_rate", 0.0)),
        "empty_prediction_rate": float(summary.get("empty_prediction_rate", 0.0)),
        "avg_tokens_generated": float(summary.get("avg_tokens_generated", 0.0)),
        "by_task_type": {
            key: float(value.get("final_normalized_exact_match", 0.0))
            for key, value in by_task.items()
        },
    }


def _first_fit_checkpoint(checkpoints: dict[str, Any]) -> dict[str, Any]:
    for step in FIT_STEPS:
        payload = checkpoints.get(str(step), {})
        if payload.get("status") != "complete":
            continue
        by_task = payload["unseen"]["by_task_type"]
        add = by_task.get("m174.add", 0.0)
        sub = by_task.get("m174.sub", 0.0)
        if add >= 0.98 and sub >= 0.98:
            return {
                "status": "complete",
                "step": step,
                "checkpoint": payload["checkpoint"],
                "canonical_add": add,
                "canonical_sub": sub,
                "canonical_train_nem": payload["train"]["final_nem"],
                "canonical_unseen_nem": payload["unseen"]["final_nem"],
                "train_loss": payload["train_loss"],
            }
    return {"status": "underfit"}


def _fit_gate_summary(methods: dict[str, Any]) -> dict[str, Any]:
    return {
        name: payload.get("fit", {"status": payload.get("status", "missing")})
        for name, payload in methods.items()
    }


def _best_position_robust(analysis: dict[str, Any]) -> dict[str, Any]:
    best_name = None
    best_score = -1.0
    for name, payload in analysis["methods"].items():
        if payload.get("status") != "complete":
            continue
        pure_min = _pure_min(payload, max_offset=32)
        prefix_min = _prefix_min(payload, max_length=16)
        canonical = _canonical_score(payload)
        score = pure_min + 0.5 * prefix_min + 0.25 * canonical
        if score > best_score:
            best_score = score
            best_name = name
    if best_name is None:
        return {"status": "missing"}
    payload = analysis["methods"][best_name]
    spec = payload["method_spec"]
    return {
        "status": "complete",
        "method": best_name,
        "checkpoint": payload["fit"]["checkpoint"],
        "position_encoding": spec["position_encoding"],
        "position_shift_max": spec["position_shift_max"],
        "canonical": _canonical_score(payload),
        "pure_min_32": _pure_min(payload, max_offset=32),
        "prefix_min_16": _prefix_min(payload, max_length=16),
        "score": best_score,
    }


def _passes_semantic_entry_gate(payload: dict[str, Any]) -> bool:
    if payload.get("status") != "complete":
        return False
    return (
        _canonical_score(payload) >= 0.98
        and _prefix_min(payload, max_length=16) >= 0.90
    )


def _canonical_score(payload: dict[str, Any]) -> float:
    if "canonical" in payload:
        if isinstance(payload["canonical"], int | float):
            return float(payload["canonical"])
        return _final_nem(payload["canonical"])
    fit = payload.get("fit", {})
    return float(fit.get("canonical_unseen_nem", 0.0))


def _pure_min(payload: dict[str, Any], *, max_offset: int) -> float:
    values = [
        _final_nem(value)
        for offset, value in payload.get("pure_offsets", {}).items()
        if int(offset) <= max_offset
    ]
    return min(values) if values else 0.0


def _prefix_min(payload: dict[str, Any], *, max_length: int) -> float:
    values = []
    for curve in payload.get("distractors", {}).values():
        values.extend(
            _final_nem(value)
            for length, value in curve.items()
            if int(length) <= max_length
        )
    return min(values) if values else 0.0


def _final_nem(payload: dict[str, Any]) -> float:
    return float(payload.get("final_nem", 0.0))


def _metric_at_step(path: Path, step: int) -> dict[str, Any] | None:
    if not path.exists():
        return None
    result = None
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            payload = json.loads(line)
            if int(payload.get("step", -1)) == step:
                result = payload
    return result


def _checkpoint_path(output_dir: Path, step: int) -> Path:
    return output_dir / "checkpoints" / f"step_{step:06d}.pt"


def _spec_payload(spec: MethodSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "position_encoding": spec.position_encoding,
        "position_shift_max": spec.position_shift_max,
        "learning_rate": spec.learning_rate,
        "train_path": str(spec.train_path),
        "eval_path": str(spec.eval_path),
        "steps": spec.steps,
        "seed": spec.seed,
        "sequence_length": spec.sequence_length,
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
        )
        + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _prompts(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8") as file:
        return {json.loads(line)["prompt"] for line in file if line.strip()}


def _dataset_notes(analysis: dict[str, Any]) -> str:
    manifest = analysis["manifest"]
    return "\n".join(
        [
            f"- train_per_op: `{manifest['train_per_op']}`",
            f"- eval_per_op: `{manifest['eval_per_op']}`",
            f"- prompt_intersections: `{manifest['prompt_intersections']}`",
            f"- offsets: `{manifest['offsets']}`",
            f"- prefix_lengths: `{manifest['prefix_lengths']}`",
            f"- distractor_types: `{manifest['distractor_types']}`",
        ]
    )


def _fit_gate_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| method | params | steps | train loss | train NEM | unseen ADD | unseen SUB | unseen NEM | gate |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, payload in analysis["methods"].items():
        spec = payload["method_spec"]
        fit = payload.get("fit", {})
        if fit.get("status") == "complete":
            rows.append(
                "| "
                f"{name} | {spec['position_encoding']}:{spec['position_shift_max']} | "
                f"{fit['step']} | {_loss_value(fit.get('train_loss'))} | "
                f"{fit['canonical_train_nem']:.4f} | {fit['canonical_add']:.4f} | "
                f"{fit['canonical_sub']:.4f} | {fit['canonical_unseen_nem']:.4f} | pass |"
            )
        else:
            last = _last_complete_checkpoint(payload.get("checkpoints", {}))
            rows.append(
                "| "
                f"{name} | {spec['position_encoding']}:{spec['position_shift_max']} | "
                f"{last.get('step', 'missing')} | {_loss_value(last.get('train_loss'))} | "
                f"{last.get('train_nem', 0.0):.4f} | {last.get('add', 0.0):.4f} | "
                f"{last.get('sub', 0.0):.4f} | {last.get('unseen_nem', 0.0):.4f} | fail |"
            )
    return "\n".join(rows)


def _pure_offset_tables(analysis: dict[str, Any]) -> str:
    sections = []
    for name, payload in analysis["methods"].items():
        if payload.get("status") != "complete":
            continue
        rows = [
            f"### {name}",
            "",
            "| offset | ADD | SUB | overall |",
            "|---:|---:|---:|---:|",
        ]
        for offset in OFFSETS:
            value = payload["pure_offsets"][str(offset)]
            by_task = value["by_task_type"]
            rows.append(
                f"| {offset} | {by_task.get('m174.add', 0.0):.4f} | "
                f"{by_task.get('m174.sub', 0.0):.4f} | {_final_nem(value):.4f} |"
            )
        sections.append("\n".join(rows))
    return "\n\n".join(sections) if sections else "No fitted variants."


def _distractor_tables(analysis: dict[str, Any]) -> str:
    sections = []
    for name, payload in analysis["methods"].items():
        if payload.get("status") != "complete":
            continue
        rows = [
            f"### {name}",
            "",
            "| distractor | len0 | len1 | len2 | len4 | len8 | len16 | len32 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for distractor, curve in payload["distractors"].items():
            scores = [_final_nem(curve[str(length)]) for length in PREFIX_LENGTHS]
            rows.append(
                f"| {distractor} | "
                + " | ".join(f"{score:.4f}" for score in scores)
                + " |"
            )
        sections.append("\n".join(rows))
    return "\n\n".join(sections) if sections else "No fitted variants."


def _factorial_tables(analysis: dict[str, Any]) -> str:
    sections = []
    for name, payload in analysis["methods"].items():
        if payload.get("status") != "complete":
            continue
        rows = [
            f"### {name}",
            "",
            "| prefix_len \\ offset | 0 | 8 | 32 |",
            "|---:|---:|---:|---:|",
        ]
        for length in FACTORIAL_PREFIX_LENGTHS:
            row = [
                _final_nem(payload["factorial"][str(length)][str(offset)])
                for offset in FACTORIAL_OFFSETS
            ]
            rows.append(
                f"| {length} | " + " | ".join(f"{score:.4f}" for score in row) + " |"
            )
        sections.append("\n".join(rows))
    return "\n\n".join(sections) if sections else "No fitted variants."


def _distractor_curriculum_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("distractor_curriculum", {})
    if payload.get("status") != "complete":
        return payload.get("reason", payload.get("status", "missing"))
    return "\n".join(
        [
            "| run | canonical | pure_min_32 | prefix_min_16 | prefix_min_32 |",
            "|---|---:|---:|---:|---:|",
            (
                f"| {payload['method_spec']['name']} | {_canonical_score(payload):.4f} | "
                f"{_pure_min(payload, max_offset=32):.4f} | "
                f"{_prefix_min(payload, max_length=16):.4f} | "
                f"{_prefix_min(payload, max_length=32):.4f} |"
            ),
        ]
    )


def _semantic_context_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("semantic_context", {})
    if payload.get("status") != "complete":
        return payload.get("reason", payload.get("status", "missing"))
    rows = ["| context | final NEM |", "|---|---:|"]
    for context, value in payload["contexts"].items():
        rows.append(f"| {context} | {_final_nem(value):.4f} |")
    return "\n".join(rows)


def _composition_table(analysis: dict[str, Any]) -> str:
    payload = analysis.get("composition", {})
    return f"{payload.get('status', 'missing')}: {payload.get('reason', '')}"


def _decision(analysis: dict[str, Any]) -> str:
    best = analysis.get("best_position_robust", {})
    curriculum = analysis.get("distractor_curriculum", {})
    gate = analysis.get("composition_gate", {})
    if gate.get("should_run"):
        return "Outcome B: relative/position method plus distractor curriculum passed all gates; proceed to composition."
    if best.get("status") != "complete":
        return "Outcome E: no alternative reached canonical fit gate; investigate implementation/optimization before reasoning experiments."
    if best.get("pure_min_32", 0.0) >= 0.95 and best.get("prefix_min_16", 0.0) < 0.90:
        return (
            f"Outcome A: `{best['method']}` solves or nearly solves global shift but "
            "distractors remain weak; next bottleneck is irrelevant-context filtering/routing."
        )
    if (
        curriculum.get("status") == "complete"
        and _prefix_min(curriculum, max_length=16) < 0.90
    ):
        return (
            f"Outcome D: `{best['method']}` is the recommended interim positional "
            "architecture, but fitted position methods still fail content prefixes; "
            "next work should target attention/routing/distractor suppression."
        )
    return (
        f"Recommended interim default: `{best['method']}`. Composition remains gated. "
        f"Gate detail: {gate.get('reason', 'missing')}."
    )


def _last_complete_checkpoint(checkpoints: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for step in FIT_STEPS:
        payload = checkpoints.get(str(step), {})
        if payload.get("status") == "complete":
            by_task = payload["unseen"]["by_task_type"]
            result = {
                "step": step,
                "train_loss": payload["train_loss"],
                "train_nem": payload["train"]["final_nem"],
                "unseen_nem": payload["unseen"]["final_nem"],
                "add": by_task.get("m174.add", 0.0),
                "sub": by_task.get("m174.sub", 0.0),
            }
    return result


def _loss_value(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "n/a"
    return f"{float(payload.get('train_loss', 0.0)):.4f}"


def _device_name(analysis: dict[str, Any]) -> str:
    for payload in analysis.get("methods", {}).values():
        for checkpoint in payload.get("checkpoints", {}).values():
            summary = checkpoint.get("unseen", {}).get("summary", {})
            if "device" in summary:
                return f"{summary.get('device')} ({summary.get('device_name')})"
    return "unknown"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
