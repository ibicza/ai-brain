from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer
from ai_brain.eval.runner import eval_lm
from ai_brain.runtime.device import get_device_info
from ai_brain.training.config import TrainConfig
from ai_brain.training.loop import train_lm

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m171_primitive_language"
RUNS_DIR = ROOT / "runs" / "m171_primitive_language"
DOC_PATH = ROOT / "docs" / "m171_primitive_language_stabilization_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m171_primitive_language_stabilization_report.md"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"

SEED = 317100
EVAL_COUNT = 500
PRIMITIVE_SCALES = (3000, 10000, 30000)
PRIMITIVE_STEPS = {3000: 5000, 10000: 10000, 30000: 20000}
WEAK_SYMBOLIC = ("add", "sub", "missing_addend", "compare_sum")
SYMBOLIC_TASKS = ("add", "sub", "missing_addend", "compare_numbers", "compare_sum")
STAGED_STEPS = 10000
LANG_STEPS = 5000
EXECUTION_STEPS = 5000
COMPOSITION_STEPS = 10000
MAX_NEW_TOKENS = 32

PrimitiveTask = Literal[
    "add",
    "sub",
    "missing_addend",
    "compare_numbers",
    "compare_sum",
]

STATE_ADD_TEMPLATES = (
    "У {name} было {a} {noun}. {dat} дали еще {b} {noun}. Какое действие нужно выполнить?",
    "{name} имела {a} {noun}. Потом {dat} добавили {b} {noun}. Какую операцию выбрать?",
    "В начале у {gen} было {a} {noun}. После этого {dat} принесли {b} {noun}. Что нужно сделать?",
    "{name} насчитала {a} {noun}. Ей выдали еще {b} {noun}. Какая операция нужна?",
    "Сначала у {gen} было {a} {noun}. Затем стало известно про еще {b} {noun}. Как считать?",
    "{name} собрала {a} {noun}. Потом получила еще {b} {noun}. Выбери операцию.",
    "У {gen} было {a} {noun}. К этому прибавили {b} {noun}. Какое действие?",
    "{name} держала {a} {noun}. Ей передали еще {b} {noun}. Что выполнить?",
    "В ящике у {gen} лежало {a} {noun}. Туда положили еще {b} {noun}. Операция?",
    "{name} записала {a} {noun}. Потом добавила запись про {b} {noun}. Что сделать?",
    "У {gen} было {a} {noun}, и {dat} дали дополнительные {b}. Какая операция?",
    "{name} начала с {a} {noun}; потом получила плюс {b}. Какой знак нужен?",
    "Было {a} {noun} у {gen}. Пришли еще {b} {noun}. Как считать итог?",
    "{name} имела запас {a} {noun}. Запас увеличили на {b}. Действие?",
    "Счет у {gen}: {a} {noun}. Поступило еще {b}. Что применить?",
    "У {gen} имеется {a} {noun}. Добавочное количество равно {b}. Операция?",
    "{name} увидела {a} {noun}. Потом появилось еще {b}. Что нужно выполнить?",
    "{name} получила сначала {a} {noun}, затем еще {b}. Какой тип действия?",
    "В наборе у {gen} {a} {noun}. В набор внесли еще {b}. Выбери действие.",
    "{name} имела {a}. Ей добавили {b}. Арифметическая операция?",
    "{name}: было {a} {noun}; дали еще {b}. Что делаем?",
    "Для {gen}: начальное {a}, прибавка {b}. Операция?",
    "У {gen} было {a} {noun}. Новая партия содержит {b}. Как получить итог?",
    "{name} хранит {a} {noun}; к ним добавляют {b}. Что выбрать?",
    "Имеется {a} {noun}. Для {gen} добавили {b}. Какое арифметическое действие?",
    "{name} взяла {a} {noun}. Потом взяла еще {b}. Тип операции?",
    "На счете у {gen} {a}. Поступление равно {b}. Какой расчет?",
    "В коллекции {gen} {a} {noun}. Коллекция выросла на {b}. Операция?",
    "{name} видит старт {a} и прирост {b}. Какой символ?",
    "У {gen} стартовое число {a}, изменение плюс {b}. Что делать?",
)
STATE_SUB_TEMPLATES = (
    "У {gen} было {a} {noun}. У {gen} забрали {b} {noun}. Какое действие нужно выполнить?",
    "{name} имела {a} {noun}. Потом {name} отдала {b} {noun}. Какую операцию выбрать?",
    "В начале у {gen} было {a} {noun}. После этого убрали {b} {noun}. Что нужно сделать?",
    "{name} насчитала {a} {noun}. Из них потратила {b} {noun}. Какая операция нужна?",
    "Сначала у {gen} было {a} {noun}. Затем стало меньше на {b}. Как считать?",
    "{name} собрала {a} {noun}. Потом потеряла {b} {noun}. Выбери операцию.",
    "У {gen} было {a} {noun}. Из этого вычли {b} {noun}. Какое действие?",
    "{name} держала {a} {noun}. У нее взяли {b} {noun}. Что выполнить?",
    "В ящике у {gen} лежало {a} {noun}. Оттуда вынули {b} {noun}. Операция?",
    "{name} записала {a} {noun}. Потом удалила запись про {b} {noun}. Что сделать?",
    "У {gen} было {a} {noun}, и {name} отдала {b}. Какая операция?",
    "{name} начала с {a} {noun}; потом минус {b}. Какой знак нужен?",
    "Было {a} {noun} у {gen}. Ушли {b} {noun}. Как считать остаток?",
    "{name} имела запас {a} {noun}. Запас уменьшили на {b}. Действие?",
    "Счет у {gen}: {a} {noun}. Списание равно {b}. Что применить?",
    "У {gen} имеется {a} {noun}. Уменьшение равно {b}. Операция?",
    "{name} увидела {a} {noun}. Потом исчезло {b}. Что нужно выполнить?",
    "{name} получила {a} {noun}, затем отдала {b}. Какой тип действия?",
    "В наборе у {gen} {a} {noun}. Из набора убрали {b}. Выбери действие.",
    "{name} имела {a}. У нее забрали {b}. Арифметическая операция?",
    "{name}: было {a} {noun}; забрали {b}. Что делаем?",
    "Для {gen}: начальное {a}, уменьшение {b}. Операция?",
    "У {gen} было {a} {noun}. Расход содержит {b}. Как получить остаток?",
    "{name} хранит {a} {noun}; из них убирают {b}. Что выбрать?",
    "Имеется {a} {noun}. Для {gen} списали {b}. Какое арифметическое действие?",
    "{name} взяла {a} {noun}. Потом вернула {b}. Тип операции?",
    "На счете у {gen} {a}. Списание равно {b}. Какой расчет?",
    "В коллекции {gen} {a} {noun}. Коллекция уменьшилась на {b}. Операция?",
    "{name} видит старт {a} и уменьшение {b}. Какой символ?",
    "У {gen} стартовое число {a}, изменение минус {b}. Что делать?",
)
NAMES = (
    ("Веры", "Вера", "Вере"),
    ("Олега", "Олег", "Олегу"),
    ("Маши", "Маша", "Маше"),
    ("Ильи", "Илья", "Илье"),
    ("Нади", "Надя", "Наде"),
)
NOUNS = ("монет", "книг", "деталей", "жетонов", "карточек")

STEP1_RE = re.compile(r"(?im)^\s*STEP1\b.*?(?:->|RESULT)?\s*(?P<value>[+-]?\d+)\s*$")
STEP2_RE = re.compile(r"(?im)^\s*STEP2\b.*?(?:->|RESULT)?\s*(?P<value>[+-]?\d+)\s*$")
OP_RE = re.compile(r"(?im)^\s*OP\s+(?P<op>ADD|SUB)\s*$")
A_RE = re.compile(r"(?im)^\s*A\s+(?P<a>\d+)\s*$")
B_RE = re.compile(r"(?im)^\s*B\s+(?P<b>\d+)\s*$")


@dataclass(frozen=True)
class RunSpec:
    name: str
    train_path: Path
    eval_path: Path
    steps: int
    group: str
    seed: int
    model_config: str = "arithmetic_3m"
    sequence_length: int = 128
    init_checkpoint: Path | None = None


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-datasets")
    subparsers.add_parser("run-primitive-scale")
    subparsers.add_parser("run-symbolic-staged")
    subparsers.add_parser("run-language")
    subparsers.add_parser("run-execution")
    subparsers.add_parser("run-composition")
    subparsers.add_parser("analyze")
    report_parser = subparsers.add_parser("build-report")
    report_parser.add_argument("--checks-passed", action="store_true")
    subparsers.add_parser("run-all")
    args = parser.parse_args()

    if args.command == "prepare-datasets":
        prepare_datasets()
    elif args.command == "run-primitive-scale":
        run_specs(primitive_scale_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-symbolic-staged":
        run_symbolic_staged()
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-language":
        run_specs(language_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-execution":
        run_specs(execution_specs())
        analyze_all()
        build_report(checks_passed=False)
    elif args.command == "run-composition":
        run_composition_if_gated()
        analyze_composition_merge()
        build_report(checks_passed=False)
    elif args.command == "analyze":
        analyze_all()
    elif args.command == "build-report":
        build_report(checks_passed=args.checks_passed)
    elif args.command == "run-all":
        prepare_datasets()
        run_specs(primitive_scale_specs())
        run_symbolic_staged()
        run_specs(language_specs())
        run_specs(execution_specs())
        analyze_all()
        run_composition_if_gated()
        analyze_composition_merge()
        build_report(checks_passed=False)
    else:
        raise AssertionError(args.command)
    return 0


def prepare_datasets() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "kind": "m171_primitive_language_stabilization",
        "seed": SEED,
        "answer_format": "FINAL <value> for symbolic/classification; structured OP/A/B for parsing",
        "numeric_tokenization": "digit_safe",
        "primitive_scales": {},
        "symbolic_staged": {},
        "language": {},
        "execution": {},
        "composition": {},
    }
    primitive_train_records: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(
        dict
    )
    for task in SYMBOLIC_TASKS:
        for scale in PRIMITIVE_SCALES:
            splits = _build_symbolic_splits(
                task,
                train_count=scale,
                seed=SEED + scale + _task_offset(task),
            )
            task_dir = DATASET_DIR / "symbolic" / task / f"scale_{scale}"
            split_info = {
                split: _write_jsonl(task_dir / f"{split}.jsonl", records)
                for split, records in splits.items()
            }
            primitive_train_records[task][scale] = splits["train"]
            manifest["primitive_scales"][f"{task}_{scale}"] = {
                "files": split_info,
                "verification": _verify_splits(splits),
                "distribution": {
                    split: _distribution(records) for split, records in splits.items()
                },
            }

    for stage_name, tasks in _symbolic_stage_defs():
        scale = 30000
        records = _balanced_mix(
            [primitive_train_records[task][scale] for task in tasks],
            count_per_bucket=10000,
            seed=SEED + 500 + len(tasks),
        )
        path_info = _write_jsonl(
            DATASET_DIR / "symbolic" / f"{stage_name}.jsonl", records
        )
        manifest["symbolic_staged"][stage_name] = {
            "tasks": list(tasks),
            "file": path_info,
            "task_counts": dict(Counter(record["task_type"] for record in records)),
        }

    language_splits = _build_language_splits()
    for name, records in language_splits.items():
        manifest["language"][name] = _write_jsonl(
            DATASET_DIR / "language" / f"{name}.jsonl",
            records,
        )
    manifest["language"]["verification"] = _verify_language_manifest(language_splits)

    execution_splits = _build_execution_splits(language_splits)
    for name, records in execution_splits.items():
        manifest["execution"][name] = _write_jsonl(
            DATASET_DIR / "execution" / f"{name}.jsonl",
            records,
        )

    composition_splits = _build_composition_splits()
    for name, records in composition_splits.items():
        manifest["composition"][name] = _write_jsonl(
            DATASET_DIR / "composition" / f"{name}.jsonl",
            records,
        )
    manifest["composition"]["verification"] = _verify_splits(composition_splits)

    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def primitive_scale_specs() -> list[RunSpec]:
    specs: list[RunSpec] = []
    for task in WEAK_SYMBOLIC:
        for scale in PRIMITIVE_SCALES:
            specs.append(
                RunSpec(
                    name=f"primitive_{task}_scale_{scale}",
                    train_path=DATASET_DIR
                    / "symbolic"
                    / task
                    / f"scale_{scale}"
                    / "train.jsonl",
                    eval_path=DATASET_DIR
                    / "symbolic"
                    / task
                    / f"scale_{scale}"
                    / "eval_seen.jsonl",
                    steps=PRIMITIVE_STEPS[scale],
                    group="primitive_scale",
                    seed=SEED + scale + _task_offset(task),
                )
            )
    specs.append(
        RunSpec(
            name="primitive_compare_numbers_control",
            train_path=DATASET_DIR
            / "symbolic"
            / "compare_numbers"
            / "scale_3000"
            / "train.jsonl",
            eval_path=DATASET_DIR
            / "symbolic"
            / "compare_numbers"
            / "scale_3000"
            / "eval_seen.jsonl",
            steps=5000,
            group="primitive_scale",
            seed=SEED + 42,
        )
    )
    return specs


def language_specs() -> list[RunSpec]:
    specs = []
    for count in (2, 5, 10, 20):
        specs.append(
            RunSpec(
                name=f"language_op_templates_{count}",
                train_path=DATASET_DIR / "language" / f"op_train_{count}.jsonl",
                eval_path=DATASET_DIR / "language" / "op_eval_seen.jsonl",
                steps=LANG_STEPS,
                group="language_op",
                seed=SEED + 700 + count,
            )
        )
    specs.append(
        RunSpec(
            name="language_parse_templates_20",
            train_path=DATASET_DIR / "language" / "parse_train_20.jsonl",
            eval_path=DATASET_DIR / "language" / "parse_eval_seen.jsonl",
            steps=LANG_STEPS,
            group="language_parse",
            seed=SEED + 730,
            sequence_length=192,
        )
    )
    return specs


def execution_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name="language_execution_templates_20",
            train_path=DATASET_DIR / "execution" / "exec_train_20.jsonl",
            eval_path=DATASET_DIR / "execution" / "exec_eval_seen.jsonl",
            steps=EXECUTION_STEPS,
            group="execution",
            seed=SEED + 800,
            sequence_length=192,
        ),
        RunSpec(
            name="symbolic_language_retention_stage",
            train_path=DATASET_DIR / "execution" / "symbolic_language_mix.jsonl",
            eval_path=DATASET_DIR
            / "symbolic"
            / "add"
            / "scale_30000"
            / "eval_seen.jsonl",
            steps=EXECUTION_STEPS,
            group="symbolic_language",
            seed=SEED + 801,
            sequence_length=192,
        ),
    ]


def composition_specs() -> list[RunSpec]:
    return [
        RunSpec(
            name="minimal_add_sub_direct",
            train_path=DATASET_DIR / "composition" / "train_add_sub.jsonl",
            eval_path=DATASET_DIR / "composition" / "eval_seen.jsonl",
            steps=COMPOSITION_STEPS,
            group="composition",
            seed=SEED + 900,
            sequence_length=192,
        )
    ]


def run_symbolic_staged() -> None:
    checkpoint: Path | None = None
    for index, (stage_name, _tasks) in enumerate(_symbolic_stage_defs(), start=1):
        spec = RunSpec(
            name=f"symbolic_staged_{index}_{stage_name}",
            train_path=DATASET_DIR / "symbolic" / f"{stage_name}.jsonl",
            eval_path=DATASET_DIR
            / "symbolic"
            / "add"
            / "scale_30000"
            / "eval_seen.jsonl",
            steps=STAGED_STEPS,
            group="symbolic_staged",
            seed=SEED + 600 + index,
            init_checkpoint=checkpoint,
        )
        run_specs([spec])
        checkpoint = _checkpoint_path(spec, STAGED_STEPS)


def run_composition_if_gated() -> None:
    analysis = (
        _read_json(RUNS_DIR / "analysis.json")
        if (RUNS_DIR / "analysis.json").exists()
        else {}
    )
    gate = _composition_gate(analysis)
    gate_path = RUNS_DIR / "composition_gate.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if gate["should_run"]:
        run_specs(composition_specs())
    else:
        print(f"skip composition: {gate['reason']}")


def run_specs(specs: Sequence[RunSpec]) -> None:
    for spec in specs:
        final_checkpoint = _checkpoint_path(spec, spec.steps)
        if final_checkpoint.exists():
            print(f"skip existing run: {spec.name}")
            continue
        output_dir = RUNS_DIR / spec.name
        output_dir.mkdir(parents=True, exist_ok=True)
        config = TrainConfig(
            train_path=spec.train_path,
            eval_path=spec.eval_path,
            tokenizer_path=TOKENIZER_PATH,
            output_dir=output_dir,
            model_config_name=spec.model_config,
            steps=spec.steps,
            batch_size=8,
            sequence_length=spec.sequence_length,
            loss_mode="answer-only",
            numeric_tokenization="digit_safe",
            eval_every=1000,
            eval_batches=20,
            save_every=5000,
            seed=spec.seed,
            init_checkpoint_path=spec.init_checkpoint,
        )
        started = time.time()
        result = train_lm(config)
        (output_dir / "run_result.json").write_text(
            json.dumps(
                {
                    "run_spec": _spec_payload(spec),
                    "elapsed_seconds": time.time() - started,
                    "train_result": result,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def analyze_all() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    analysis: dict[str, Any] = {
        "primitive_scale": _analyze_specs(primitive_scale_specs()),
        "symbolic_staged": _analyze_specs(_symbolic_staged_specs_for_analysis()),
        "language": _analyze_specs(language_specs()),
        "execution": _analyze_specs(execution_specs()),
        "composition": _analyze_specs(composition_specs()),
    }
    analysis["primitive_scale_summary"] = _primitive_scale_summary(
        analysis["primitive_scale"]
    )
    analysis["best_symbolic"] = _best_symbolic_summary(
        analysis["primitive_scale_summary"]
    )
    analysis["symbolic_retention_matrix"] = _symbolic_retention_matrix(
        analysis["symbolic_staged"]
    )
    analysis["language_summary"] = _language_summary(analysis["language"])
    analysis["execution_summary"] = _execution_summary(analysis["execution"])
    analysis["composition_gate"] = _composition_gate(analysis)
    analysis["composition_summary"] = _composition_summary(analysis["composition"])
    (RUNS_DIR / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def analyze_composition_merge() -> None:
    analysis_path = RUNS_DIR / "analysis.json"
    if analysis_path.exists():
        analysis = _read_json(analysis_path)
    else:
        analysis = {}
    analysis["composition"] = _analyze_specs(composition_specs())
    analysis["composition_summary"] = _composition_summary(analysis["composition"])
    analysis["composition_gate"] = _composition_gate(analysis)
    analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_report(*, checks_passed: bool) -> None:
    analysis = (
        _read_json(RUNS_DIR / "analysis.json")
        if (RUNS_DIR / "analysis.json").exists()
        else {}
    )
    manifest = (
        _read_json(DATASET_DIR / "manifest.json")
        if (DATASET_DIR / "manifest.json").exists()
        else {}
    )
    device = get_device_info(prefer_cuda=True)
    lines = [
        "# M-17.1 Primitive + Language Stabilization",
        "",
        "## Checks",
        "",
        f"- ruff format/check/pytest: {'passed' if checks_passed else 'not recorded in report build'}",
        f"- commit hash at report build: `{_git_commit()}`",
        f"- device: `{device.device}` ({device.name})",
        "",
        "## Primitive Data Scale",
        "",
        _primitive_scale_table(analysis),
        "",
        "## Stabilized Single Primitives",
        "",
        _best_symbolic_table(analysis),
        "",
        "## Symbolic Staged Retention",
        "",
        _symbolic_retention_table(analysis),
        "",
        "## Language Operation Classification",
        "",
        _language_op_table(analysis),
        "",
        "## Language Structured Parsing",
        "",
        _language_parse_table(analysis),
        "",
        "## Language Execution",
        "",
        _execution_table(analysis),
        "",
        "## Template Diversity Ablation",
        "",
        _template_ablation_table(analysis),
        "",
        "## Symbolic + Language Retention",
        "",
        _symbolic_language_table(analysis),
        "",
        "## Minimal ADD_SUB Retest",
        "",
        _composition_table(analysis),
        "",
        "## Dataset Notes",
        "",
        _dataset_notes(manifest),
        "",
        "## Decision",
        "",
        _decision(analysis),
        "",
        "## Next Milestone",
        "",
        _next_milestone(analysis),
        "",
    ]
    text = "\n".join(lines)
    DOC_PATH.write_text(text, encoding="utf-8")
    RUN_REPORT_PATH.write_text(text, encoding="utf-8")


def _build_symbolic_splits(
    task: str,
    *,
    train_count: int,
    seed: int,
) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    candidates = _symbolic_candidates(task, rng)
    key_fn = _symbolic_bucket_key(task)
    train_base_count = min(len(candidates) // 2, min(train_count, 5000))
    train_base = _balanced_sample_unique(
        candidates, train_base_count, key_fn=key_fn, seed=seed
    )
    train_keys = {_case_key(task, case) for case in train_base}
    remaining = [case for case in candidates if _case_key(task, case) not in train_keys]
    train_cases = _repeat_balanced(
        train_base, train_count, key_fn=key_fn, seed=seed + 1
    )
    seen_cases = _balanced_sample_unique(
        train_base, min(EVAL_COUNT, len(train_base)), key_fn=key_fn, seed=seed + 2
    )
    unseen_cases = _balanced_sample_unique(
        remaining, EVAL_COUNT, key_fn=key_fn, seed=seed + 3
    )
    train_eval_cases = _balanced_sample_unique(
        train_base, min(EVAL_COUNT, len(train_base)), key_fn=key_fn, seed=seed + 4
    )
    return {
        "train": [
            _symbolic_record(task, case, "train", index)
            for index, case in enumerate(train_cases)
        ],
        "eval_train": [
            _symbolic_record(task, case, "eval_train", index)
            for index, case in enumerate(train_eval_cases)
        ],
        "eval_seen": [
            _symbolic_record(task, case, "eval_seen", index)
            for index, case in enumerate(seen_cases)
        ],
        "eval_unseen": [
            _symbolic_record(task, case, "eval_unseen", index)
            for index, case in enumerate(unseen_cases)
        ],
    }


def _symbolic_candidates(task: str, rng: random.Random) -> list[tuple[int, ...]]:
    if task in {"add", "missing_addend"}:
        return [(a, b) for a in range(10, 100) for b in range(10, 100)]
    if task == "sub":
        return [(a, b) for a in range(10, 100) for b in range(a + 1)]
    if task == "compare_numbers":
        return [(a, b) for a in range(10, 100) for b in range(10, 100)]
    if task == "compare_sum":
        return _compare_sum_candidates(rng, target_per_class=12000)
    raise AssertionError(task)


def _symbolic_bucket_key(task: str) -> Callable[[tuple[int, ...]], Any]:
    if task == "add":
        return lambda case: (
            _carry_bucket(case[0], case[1]),
            "3_digit" if case[0] + case[1] >= 100 else "2_digit",
        )
    if task == "sub":
        return lambda case: (
            "borrow" if case[0] % 10 < case[1] % 10 else "no_borrow",
            f"{len(str(case[0] - case[1]))}_digit",
        )
    if task == "missing_addend":
        return lambda case: (
            "borrow" if (case[0] + case[1]) % 10 < case[0] % 10 else "no_borrow",
            "answer_10_49" if case[1] < 50 else "answer_50_99",
            f"{len(str(case[1]))}_digit",
        )
    if task == "compare_numbers":
        return lambda case: _compare_relation(case[0], case[1])
    if task == "compare_sum":
        return lambda case: _compare_sum_answer(case)
    raise AssertionError(task)


def _symbolic_record(
    task: str,
    case: tuple[int, ...],
    split: str,
    index: int,
) -> dict[str, Any]:
    if task == "add":
        a, b = case
        answer: int | str = a + b
        prompt = f"ADD {a:02d} + {b:02d}"
        metadata = {
            "a": a,
            "b": b,
            "answer_value": answer,
            "carry_bucket": _carry_bucket(a, b),
            "output_length": f"{len(str(answer))}_digit",
        }
    elif task == "sub":
        a, b = case
        answer = a - b
        prompt = f"SUB {a:02d} - {b:02d}"
        metadata = {
            "a": a,
            "b": b,
            "answer_value": answer,
            "borrow_bucket": "borrow" if a % 10 < b % 10 else "no_borrow",
            "output_length": f"{len(str(answer))}_digit",
        }
    elif task == "missing_addend":
        a, b = case
        total = a + b
        answer = b
        prompt = f"MISSING {a:02d} + ? = {total}"
        metadata = {
            "known": a,
            "target": b,
            "total": total,
            "answer_value": answer,
            "borrow_bucket": "borrow" if total % 10 < a % 10 else "no_borrow",
            "answer_range": "10_49" if b < 50 else "50_99",
            "output_length": f"{len(str(answer))}_digit",
        }
    elif task == "compare_numbers":
        a, b = case
        answer = _compare_relation(a, b)
        prompt = f"COMPARE {a:02d} {b:02d}"
        metadata = {"a": a, "b": b, "relation": answer}
    elif task == "compare_sum":
        a, b, c, d = case
        answer = _compare_sum_answer(case)
        prompt = f"COMPARE_SUM {a:02d} + {b:02d} | {c:02d} + {d:02d}"
        metadata = {
            "a": a,
            "b": b,
            "c": c,
            "d": d,
            "left": a + b,
            "right": c + d,
            "relation": answer,
        }
    else:
        raise AssertionError(task)
    metadata.update({"task": task, "split": split, "case_key": _case_key(task, case)})
    return {
        "id": f"m171.{task}.{split}.{index:06d}",
        "task_type": f"m171.{task}",
        "prompt": prompt,
        "answer": f"FINAL {answer}",
        "metadata": metadata,
    }


def _compare_sum_candidates(
    rng: random.Random,
    *,
    target_per_class: int,
) -> list[tuple[int, int, int, int]]:
    buckets: dict[str, list[tuple[int, int, int, int]]] = {
        "LEFT": [],
        "RIGHT": [],
        "EQUAL": [],
    }
    seen: set[tuple[int, int, int, int]] = set()
    while min(len(values) for values in buckets.values()) < target_per_class:
        if len(buckets["EQUAL"]) < target_per_class and rng.random() < 0.35:
            left = rng.randint(20, 198)
            a = rng.randint(max(10, left - 99), min(99, left - 10))
            b = left - a
            c = rng.randint(max(10, left - 99), min(99, left - 10))
            d = left - c
            case = (a, b, c, d)
        else:
            case = tuple(rng.randint(10, 99) for _ in range(4))  # type: ignore[assignment]
        if case in seen:
            continue
        seen.add(case)
        answer = _compare_sum_answer(case)
        if len(buckets[answer]) < target_per_class:
            buckets[answer].append(case)
    return [case for name in ("LEFT", "RIGHT", "EQUAL") for case in buckets[name]]


def _build_language_splits() -> dict[str, list[dict[str, Any]]]:
    splits: dict[str, list[dict[str, Any]]] = {}
    train_prompts_by_mode: dict[str, set[str]] = {"op": set(), "parse": set()}
    for count in (2, 5, 10, 20):
        op_train = _language_records(
            mode="op",
            family_indices=range(count),
            split=f"op_train_{count}",
            count=3000,
            seed=SEED + 1000 + count,
        )
        parse_train = _language_records(
            mode="parse",
            family_indices=range(count),
            split=f"parse_train_{count}",
            count=3000,
            seed=SEED + 1100 + count,
        )
        splits[f"op_train_{count}"] = op_train
        splits[f"parse_train_{count}"] = parse_train
        train_prompts_by_mode["op"].update(record["prompt"] for record in op_train)
        train_prompts_by_mode["parse"].update(
            record["prompt"] for record in parse_train
        )
    all_train_prompts = set().union(*train_prompts_by_mode.values())
    for mode in ("op", "parse"):
        splits[f"{mode}_eval_seen"] = _language_records(
            mode=mode,
            family_indices=range(20),
            split=f"{mode}_eval_seen",
            count=EVAL_COUNT,
            seed=SEED + 1200 + (0 if mode == "op" else 1),
            blocked_prompts=all_train_prompts,
        )
        splits[f"{mode}_eval_paraphrase"] = _language_records(
            mode=mode,
            family_indices=range(20, 25),
            split=f"{mode}_eval_paraphrase",
            count=EVAL_COUNT,
            seed=SEED + 1210 + (0 if mode == "op" else 1),
            blocked_prompts=all_train_prompts,
        )
        splits[f"{mode}_eval_lexical"] = _language_records(
            mode=mode,
            family_indices=range(25, 30),
            split=f"{mode}_eval_lexical",
            count=EVAL_COUNT,
            seed=SEED + 1220 + (0 if mode == "op" else 1),
            blocked_prompts=all_train_prompts,
        )
    return splits


def _language_records(
    *,
    mode: Literal["op", "parse"],
    family_indices: Iterable[int],
    split: str,
    count: int,
    seed: int,
    blocked_prompts: set[str] | None = None,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    families = list(family_indices)
    records: list[dict[str, Any]] = []
    seen_prompts: set[str] = set(blocked_prompts or set())
    while len(records) < count:
        op = "ADD" if len(records) % 2 == 0 else "SUB"
        family = families[len(records) % len(families)]
        if op == "ADD":
            a = rng.randint(10, 99)
            b = rng.randint(10, 99)
            template = STATE_ADD_TEMPLATES[family]
        else:
            a = rng.randint(10, 99)
            b = rng.randint(0, a)
            template = STATE_SUB_TEMPLATES[family]
        gen, name, dat = NAMES[(family + len(records)) % len(NAMES)]
        noun = NOUNS[(family * 3 + len(records)) % len(NOUNS)]
        prompt = template.format(a=a, b=b, gen=gen, name=name, dat=dat, noun=noun)
        if prompt in seen_prompts:
            continue
        seen_prompts.add(prompt)
        if mode == "op":
            answer = f"FINAL {op}"
            task_type = f"m171.state_op_{op.lower()}"
        else:
            answer = f"OP {op}\nA {a}\nB {b}"
            task_type = "m171.state_parse"
        records.append(
            {
                "id": f"m171.{mode}.{split}.{len(records):06d}",
                "task_type": task_type,
                "prompt": prompt,
                "answer": answer,
                "metadata": {
                    "mode": mode,
                    "split": split,
                    "op": op,
                    "a": a,
                    "b": b,
                    "family": family,
                    "template_bucket": _template_bucket(family),
                },
            }
        )
    return records


def _build_execution_splits(
    language_splits: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    splits: dict[str, list[dict[str, Any]]] = {
        "exec_train_20": [
            _execution_record(record, "exec_train_20", index)
            for index, record in enumerate(language_splits["parse_train_20"])
        ],
        "exec_eval_seen": [
            _execution_record(record, "exec_eval_seen", index)
            for index, record in enumerate(language_splits["parse_eval_seen"])
        ],
        "exec_eval_paraphrase": [
            _execution_record(record, "exec_eval_paraphrase", index)
            for index, record in enumerate(language_splits["parse_eval_paraphrase"])
        ],
        "exec_eval_lexical": [
            _execution_record(record, "exec_eval_lexical", index)
            for index, record in enumerate(language_splits["parse_eval_lexical"])
        ],
    }
    splits["exec_teacher_forced"] = [
        _teacher_forced_execution_record(record, "exec_teacher_forced", index)
        for index, record in enumerate(splits["exec_eval_paraphrase"])
    ]
    symbolic_replay = _balanced_mix(
        [
            _read_jsonl(DATASET_DIR / "symbolic" / task / "scale_30000" / "train.jsonl")
            for task in SYMBOLIC_TASKS
        ],
        count_per_bucket=2000,
        seed=SEED + 1400,
    )
    language_replay = _balanced_mix(
        [
            splits["exec_train_20"],
            language_splits["op_train_20"],
            language_splits["parse_train_20"],
        ],
        count_per_bucket=2000,
        seed=SEED + 1401,
    )
    splits["symbolic_language_mix"] = _shuffled(
        [*symbolic_replay, *language_replay],
        seed=SEED + 1402,
    )
    splits["exec_teacher_forced"] = _dedup_records_by_prompt(
        splits["exec_teacher_forced"],
        fallback=[
            _teacher_forced_execution_record(record, "exec_teacher_forced_extra", index)
            for index, record in enumerate(splits["exec_eval_lexical"])
        ],
        count=EVAL_COUNT,
    )
    return splits


def _execution_record(
    parse_record: dict[str, Any],
    split: str,
    index: int,
) -> dict[str, Any]:
    metadata = dict(parse_record["metadata"])
    op = metadata["op"]
    a = int(metadata["a"])
    b = int(metadata["b"])
    final = a + b if op == "ADD" else a - b
    metadata.update({"split": split, "answer_value": final})
    return {
        "id": f"m171.exec.{split}.{index:06d}",
        "task_type": "m171.state_execution",
        "prompt": parse_record["prompt"],
        "answer": f"OP {op}\nA {a}\nB {b}\nFINAL {final}",
        "metadata": metadata,
    }


def _teacher_forced_execution_record(
    exec_record: dict[str, Any],
    split: str,
    index: int,
) -> dict[str, Any]:
    metadata = dict(exec_record["metadata"])
    op = metadata["op"]
    a = int(metadata["a"])
    b = int(metadata["b"])
    final = int(metadata["answer_value"])
    return {
        "id": f"m171.exec.teacher.{index:06d}",
        "task_type": "m171.state_execution_teacher_forced",
        "prompt": f"OP {op}\nA {a}\nB {b}\nFINAL ?",
        "answer": f"FINAL {final}",
        "metadata": {**metadata, "split": split},
    }


def _build_composition_splits() -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(SEED + 1500)
    cases: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    while len(cases) < 4000:
        a = rng.randint(10, 99)
        b = rng.randint(10, 99)
        c = rng.randint(0, a + b)
        case = (a, b, c)
        if case in seen:
            continue
        seen.add(case)
        cases.append(case)
    train = cases[:3000]
    seen_eval = train[:EVAL_COUNT]
    unseen_eval = cases[3000 : 3000 + EVAL_COUNT]
    teacher_forced = [
        _add_sub_teacher_forced_record(case, "eval_teacher_forced", index)
        for index, case in enumerate(unseen_eval)
    ]
    teacher_forced = _dedup_records_by_prompt(
        teacher_forced,
        fallback=[
            _add_sub_teacher_forced_record(case, "eval_teacher_forced_extra", index)
            for index, case in enumerate(cases[3500:])
        ],
        count=EVAL_COUNT,
    )
    return {
        "train_add_sub": [
            _add_sub_record(case, "train_add_sub", index)
            for index, case in enumerate(train)
        ],
        "eval_train": [
            _add_sub_record(case, "eval_train", index)
            for index, case in enumerate(train[:EVAL_COUNT])
        ],
        "eval_seen": [
            _add_sub_record(case, "eval_seen", index)
            for index, case in enumerate(seen_eval)
        ],
        "eval_unseen": [
            _add_sub_record(case, "eval_unseen", index)
            for index, case in enumerate(unseen_eval)
        ],
        "eval_teacher_forced": teacher_forced,
    }


def _add_sub_record(
    case: tuple[int, int, int],
    split: str,
    index: int,
) -> dict[str, Any]:
    a, b, c = case
    step1 = a + b
    final = step1 - c
    return {
        "id": f"m171.add_sub.{split}.{index:06d}",
        "task_type": "m171.add_sub",
        "prompt": f"ADD_SUB {a:02d} + {b:02d} - {c:02d}",
        "answer": f"STEP1 ADD {a} {b} -> {step1}\nSTEP2 SUB {step1} {c} -> {final}\nFINAL {final}",
        "metadata": {
            "a": a,
            "b": b,
            "c": c,
            "step1": step1,
            "step2": final,
            "answer_value": final,
            "split": split,
        },
    }


def _add_sub_teacher_forced_record(
    case: tuple[int, int, int],
    split: str,
    index: int,
) -> dict[str, Any]:
    a, b, c = case
    step1 = a + b
    final = step1 - c
    return {
        "id": f"m171.add_sub.teacher.{index:06d}",
        "task_type": "m171.add_sub_teacher_forced",
        "prompt": f"STEP1 RESULT {step1}\nSTEP2 SUB {step1} {c} -> ?",
        "answer": f"FINAL {final}",
        "metadata": {
            "a": a,
            "b": b,
            "c": c,
            "step1": step1,
            "step2": final,
            "answer_value": final,
            "split": split,
        },
    }


def _analyze_specs(specs: Sequence[RunSpec]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for spec in specs:
        checkpoints = _available_checkpoints(spec)
        if not checkpoints:
            results[spec.name] = {"status": "missing", "run_spec": _spec_payload(spec)}
            continue
        run_payload: dict[str, Any] = {
            "status": "complete",
            "run_spec": _spec_payload(spec),
            "checkpoints": {},
            "train_loss": _last_train_loss(RUNS_DIR / spec.name / "metrics.jsonl"),
        }
        for step, checkpoint in checkpoints.items():
            step_payload: dict[str, Any] = {"checkpoint": str(checkpoint), "splits": {}}
            for split_name, eval_path in _eval_paths_for_spec(spec).items():
                output_dir = (
                    RUNS_DIR / spec.name / "eval" / f"step_{step:06d}" / split_name
                )
                summary_path = output_dir / "summary.json"
                if summary_path.exists():
                    summary = _read_json(summary_path)
                else:
                    summary = eval_lm(
                        checkpoint_path=checkpoint,
                        eval_path=eval_path,
                        tokenizer_path=TOKENIZER_PATH,
                        output_dir=output_dir,
                        max_new_tokens=MAX_NEW_TOKENS,
                        numeric_tokenization="digit_safe",
                    )["summary"]
                step_payload["splits"][split_name] = _enrich_eval_summary(
                    eval_path=eval_path,
                    predictions_path=Path(summary["predictions_path"]),
                    summary=summary,
                )
            run_payload["checkpoints"][str(step)] = step_payload
        results[spec.name] = run_payload
    return results


def _eval_paths_for_spec(spec: RunSpec) -> dict[str, Path]:
    if spec.group == "primitive_scale":
        task, scale = _primitive_task_scale_from_name(spec.name)
        base = DATASET_DIR / "symbolic" / task / f"scale_{scale}"
        return {
            "train": base / "eval_train.jsonl",
            "seen": base / "eval_seen.jsonl",
            "unseen": base / "eval_unseen.jsonl",
        }
    if spec.group == "symbolic_staged":
        stage_index = int(spec.name.split("_", 3)[2])
        tasks = _symbolic_stage_defs()[stage_index - 1][1]
        return {
            f"{task}_unseen": DATASET_DIR
            / "symbolic"
            / task
            / "scale_30000"
            / "eval_unseen.jsonl"
            for task in tasks
        }
    if spec.group == "language_op":
        return {
            "seen": DATASET_DIR / "language" / "op_eval_seen.jsonl",
            "paraphrase": DATASET_DIR / "language" / "op_eval_paraphrase.jsonl",
            "lexical": DATASET_DIR / "language" / "op_eval_lexical.jsonl",
        }
    if spec.group == "language_parse":
        return {
            "seen": DATASET_DIR / "language" / "parse_eval_seen.jsonl",
            "paraphrase": DATASET_DIR / "language" / "parse_eval_paraphrase.jsonl",
            "lexical": DATASET_DIR / "language" / "parse_eval_lexical.jsonl",
        }
    if spec.group == "execution":
        return {
            "seen": DATASET_DIR / "execution" / "exec_eval_seen.jsonl",
            "paraphrase": DATASET_DIR / "execution" / "exec_eval_paraphrase.jsonl",
            "lexical": DATASET_DIR / "execution" / "exec_eval_lexical.jsonl",
            "teacher_forced": DATASET_DIR / "execution" / "exec_teacher_forced.jsonl",
        }
    if spec.group == "symbolic_language":
        return {
            f"{task}_unseen": DATASET_DIR
            / "symbolic"
            / task
            / "scale_30000"
            / "eval_unseen.jsonl"
            for task in SYMBOLIC_TASKS
        } | {
            "state_op_paraphrase": DATASET_DIR
            / "language"
            / "op_eval_paraphrase.jsonl",
            "state_parse_paraphrase": DATASET_DIR
            / "language"
            / "parse_eval_paraphrase.jsonl",
            "state_exec_paraphrase": DATASET_DIR
            / "execution"
            / "exec_eval_paraphrase.jsonl",
        }
    if spec.group == "composition":
        return {
            "train": DATASET_DIR / "composition" / "eval_train.jsonl",
            "seen": DATASET_DIR / "composition" / "eval_seen.jsonl",
            "unseen": DATASET_DIR / "composition" / "eval_unseen.jsonl",
            "teacher_forced": DATASET_DIR / "composition" / "eval_teacher_forced.jsonl",
        }
    raise AssertionError(spec.group)


def _enrich_eval_summary(
    *,
    eval_path: Path,
    predictions_path: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    records = {record["id"]: record for record in _read_jsonl(eval_path)}
    predictions = _read_jsonl(predictions_path)
    return {
        "overall": summary["overall"],
        "by_task_type": summary.get("by_task_type", {}),
        "buckets": _bucket_metrics(predictions, records),
        "digit_accuracy": _digit_metrics(predictions, records),
        "parse_metrics": _parse_metrics(predictions, records),
        "trace_metrics": _trace_metrics(predictions, records),
        "failure_samples": _failure_samples(predictions, records, limit=5),
    }


def _bucket_metrics(
    predictions: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for prediction in predictions:
        metadata = records.get(prediction["id"], {}).get("metadata", {})
        correct = bool(prediction["final_normalized_exact_match"])
        for key in (
            "carry_bucket",
            "borrow_bucket",
            "output_length",
            "answer_range",
            "relation",
            "template_bucket",
            "op",
        ):
            if key in metadata:
                buckets[key][str(metadata[key])].append(correct)
    return {
        key: {
            value: {"count": len(items), "final_nem": _rate(items)}
            for value, items in sorted(values.items())
        }
        for key, values in sorted(buckets.items())
    }


def _digit_metrics(
    predictions: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    per_position: dict[str, list[bool]] = defaultdict(list)
    all_digits: list[bool] = []
    for prediction in predictions:
        metadata = records.get(prediction["id"], {}).get("metadata", {})
        expected_value = metadata.get("answer_value")
        if expected_value is None:
            continue
        expected = str(expected_value)
        if not expected.isdigit():
            continue
        predicted = normalize_final_answer(
            extract_final_answer(str(prediction["predicted"]))
        )
        if not predicted.isdigit():
            predicted = ""
        width = max(len(expected), len(predicted))
        for offset, (expected_digit, predicted_digit) in enumerate(
            zip(
                reversed(expected.zfill(width)),
                reversed(predicted.zfill(width)),
                strict=True,
            )
        ):
            name = ("units", "tens", "hundreds", "thousands")[min(offset, 3)]
            correct = expected_digit == predicted_digit
            per_position[name].append(correct)
            all_digits.append(correct)
    return {
        "per_digit_accuracy": _rate(all_digits),
        **{
            f"{name}_accuracy": _rate(values)
            for name, values in sorted(per_position.items())
        },
    }


def _parse_metrics(
    predictions: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    op_values: list[bool] = []
    a_values: list[bool] = []
    b_values: list[bool] = []
    full_values: list[bool] = []
    final_given_parse: list[bool] = []
    for prediction in predictions:
        metadata = records.get(prediction["id"], {}).get("metadata", {})
        if not {"op", "a", "b"}.issubset(metadata):
            continue
        parsed = _parse_structured(str(prediction["predicted"]))
        op_ok = parsed["op"] == str(metadata["op"])
        a_ok = parsed["a"] == str(metadata["a"])
        b_ok = parsed["b"] == str(metadata["b"])
        full_ok = op_ok and a_ok and b_ok
        op_values.append(op_ok)
        a_values.append(a_ok)
        b_values.append(b_ok)
        full_values.append(full_ok)
        if full_ok and "answer_value" in metadata:
            final_ok = normalize_final_answer(
                extract_final_answer(str(prediction["predicted"]))
            ) == str(metadata["answer_value"])
            final_given_parse.append(final_ok)
    return {
        "op_accuracy": _rate(op_values),
        "arg_a_accuracy": _rate(a_values),
        "arg_b_accuracy": _rate(b_values),
        "full_parse_accuracy": _rate(full_values),
        "final_given_correct_parse": _rate(final_given_parse),
    }


def _trace_metrics(
    predictions: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    step1_values: list[bool] = []
    step2_values: list[bool] = []
    final_values: list[bool] = []
    for prediction in predictions:
        metadata = records.get(prediction["id"], {}).get("metadata", {})
        if "step1" not in metadata or "step2" not in metadata:
            continue
        text = str(prediction["predicted"])
        step1 = _regex_value(STEP1_RE, text)
        step2 = _regex_value(STEP2_RE, text)
        step1_values.append(step1 == str(metadata["step1"]))
        step2_values.append(step2 == str(metadata["step2"]))
        final_values.append(bool(prediction["final_normalized_exact_match"]))
    return {
        "step1_accuracy": _rate(step1_values),
        "step2_accuracy": _rate(step2_values),
        "final_accuracy": _rate(final_values),
    }


def _failure_samples(
    predictions: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    samples = []
    for prediction in predictions:
        if prediction["final_normalized_exact_match"]:
            continue
        samples.append(
            {
                "prompt": prediction["prompt"],
                "expected": prediction["expected"],
                "predicted": prediction["predicted"],
                "metadata": records.get(prediction["id"], {}).get("metadata", {}),
            }
        )
        if len(samples) >= limit:
            break
    return samples


def _primitive_scale_summary(runs: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for run_name, payload in runs.items():
        if payload.get("status") != "complete":
            continue
        task, scale = _primitive_task_scale_from_name(run_name)
        task_summary = summary.setdefault(task, {})
        for step, step_payload in payload["checkpoints"].items():
            task_summary[f"{scale}_{step}"] = {
                "scale": scale,
                "step": int(step),
                "train": _final_nem(step_payload["splits"].get("train")),
                "seen": _final_nem(step_payload["splits"].get("seen")),
                "unseen": _final_nem(step_payload["splits"].get("unseen")),
                "buckets": step_payload["splits"].get("unseen", {}).get("buckets", {}),
            }
    return summary


def _best_symbolic_summary(scale_summary: dict[str, Any]) -> dict[str, Any]:
    best: dict[str, Any] = {}
    for task, variants in scale_summary.items():
        best_variant = None
        for key, payload in variants.items():
            if best_variant is None:
                best_variant = (key, payload)
                continue
            score = (payload.get("unseen") or 0.0, payload.get("train") or 0.0)
            best_score = (
                best_variant[1].get("unseen") or 0.0,
                best_variant[1].get("train") or 0.0,
            )
            if score > best_score:
                best_variant = (key, payload)
        if best_variant is not None:
            best[task] = {"variant": best_variant[0], **best_variant[1]}
    return best


def _symbolic_retention_matrix(runs: dict[str, Any]) -> dict[str, Any]:
    matrix: dict[str, Any] = {}
    for run_name, payload in runs.items():
        if payload.get("status") != "complete":
            continue
        final_step = str(payload["run_spec"]["steps"])
        final_payload = payload["checkpoints"].get(final_step)
        if final_payload is None:
            continue
        matrix[run_name] = {
            split.removesuffix("_unseen"): _final_nem(split_payload)
            for split, split_payload in final_payload["splits"].items()
        }
    return matrix


def _language_summary(runs: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for run_name, payload in runs.items():
        if payload.get("status") != "complete":
            continue
        final_step = str(payload["run_spec"]["steps"])
        step_payload = payload["checkpoints"].get(final_step)
        if step_payload is None:
            continue
        result[run_name] = {
            split: {
                "final_nem": _final_nem(split_payload),
                "parse": split_payload["parse_metrics"],
                "buckets": split_payload["buckets"],
            }
            for split, split_payload in step_payload["splits"].items()
        }
    return result


def _execution_summary(runs: dict[str, Any]) -> dict[str, Any]:
    return _language_summary(runs)


def _composition_summary(runs: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for run_name, payload in runs.items():
        if payload.get("status") != "complete":
            continue
        final_step = str(payload["run_spec"]["steps"])
        step_payload = payload["checkpoints"].get(final_step)
        if step_payload is None:
            continue
        result[run_name] = {
            split: {
                "final_nem": _final_nem(split_payload),
                "trace": split_payload["trace_metrics"],
            }
            for split, split_payload in step_payload["splits"].items()
        }
    return result


def _composition_gate(analysis: dict[str, Any]) -> dict[str, Any]:
    best = analysis.get("best_symbolic", {})
    add = best.get("add", {})
    sub = best.get("sub", {})
    add_ok = (add.get("train") or 0.0) >= 0.99 and (add.get("unseen") or 0.0) >= 0.95
    sub_ok = (sub.get("train") or 0.0) >= 0.99 and (sub.get("unseen") or 0.0) >= 0.95
    return {
        "should_run": bool(add_ok and sub_ok),
        "add_train": add.get("train"),
        "add_unseen": add.get("unseen"),
        "sub_train": sub.get("train"),
        "sub_unseen": sub.get("unseen"),
        "reason": "ADD/SUB reached gate"
        if add_ok and sub_ok
        else "ADD/SUB not strong enough for minimal composition retest",
    }


def _primitive_scale_table(analysis: dict[str, Any]) -> str:
    summary = analysis.get("primitive_scale_summary", {})
    rows = [
        "| task | scale | step | train | seen | unseen | buckets |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for task, variants in sorted(summary.items()):
        for key, payload in sorted(
            variants.items(), key=lambda item: (item[1]["scale"], item[1]["step"])
        ):
            rows.append(
                f"| {task} | {payload['scale']} | {payload['step']} | {_fmt(payload.get('train'))} | "
                f"{_fmt(payload.get('seen'))} | {_fmt(payload.get('unseen'))} | "
                f"{_bucket_text(payload.get('buckets', {}))} |"
            )
    return "\n".join(rows) if len(rows) > 2 else "No primitive scale results yet."


def _best_symbolic_table(analysis: dict[str, Any]) -> str:
    best = analysis.get("best_symbolic", {})
    rows = [
        "| task | best variant | train | seen | unseen |",
        "|---|---|---:|---:|---:|",
    ]
    for task, payload in sorted(best.items()):
        rows.append(
            f"| {task} | {payload.get('variant')} | {_fmt(payload.get('train'))} | "
            f"{_fmt(payload.get('seen'))} | {_fmt(payload.get('unseen'))} |"
        )
    return "\n".join(rows) if len(rows) > 2 else "No stabilized primitive results yet."


def _symbolic_retention_table(analysis: dict[str, Any]) -> str:
    matrix = analysis.get("symbolic_retention_matrix", {})
    rows = [
        "| stage | add | sub | missing_addend | compare_numbers | compare_sum |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for stage, values in sorted(matrix.items()):
        rows.append(
            f"| {stage} | {_fmt(values.get('add'))} | {_fmt(values.get('sub'))} | "
            f"{_fmt(values.get('missing_addend'))} | {_fmt(values.get('compare_numbers'))} | "
            f"{_fmt(values.get('compare_sum'))} |"
        )
    return "\n".join(rows) if len(rows) > 2 else "No symbolic staged results yet."


def _language_op_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| run | seen | paraphrase | lexical | heldout op buckets |",
        "|---|---:|---:|---:|---|",
    ]
    for run, payload in sorted(analysis.get("language_summary", {}).items()):
        if not run.startswith("language_op"):
            continue
        rows.append(
            f"| {run} | {_fmt(payload.get('seen', {}).get('final_nem'))} | "
            f"{_fmt(payload.get('paraphrase', {}).get('final_nem'))} | "
            f"{_fmt(payload.get('lexical', {}).get('final_nem'))} | "
            f"{_bucket_text(payload.get('paraphrase', {}).get('buckets', {}).get('op', {}))} |"
        )
    return (
        "\n".join(rows) if len(rows) > 2 else "No language classification results yet."
    )


def _language_parse_table(analysis: dict[str, Any]) -> str:
    rows = ["| split | op | argA | argB | full parse |", "|---|---:|---:|---:|---:|"]
    payload = analysis.get("language_summary", {}).get(
        "language_parse_templates_20", {}
    )
    for split, values in sorted(payload.items()):
        parse = values.get("parse", {})
        rows.append(
            f"| {split} | {_fmt(parse.get('op_accuracy'))} | {_fmt(parse.get('arg_a_accuracy'))} | "
            f"{_fmt(parse.get('arg_b_accuracy'))} | {_fmt(parse.get('full_parse_accuracy'))} |"
        )
    return "\n".join(rows) if len(rows) > 2 else "No language parse results yet."


def _execution_table(analysis: dict[str, Any]) -> str:
    rows = [
        "| split | parse correct | final given parse | full final |",
        "|---|---:|---:|---:|",
    ]
    payload = analysis.get("execution_summary", {}).get(
        "language_execution_templates_20", {}
    )
    for split, values in sorted(payload.items()):
        parse = values.get("parse", {})
        rows.append(
            f"| {split} | {_fmt(parse.get('full_parse_accuracy'))} | "
            f"{_fmt(parse.get('final_given_correct_parse'))} | {_fmt(values.get('final_nem'))} |"
        )
    return "\n".join(rows) if len(rows) > 2 else "No language execution results yet."


def _template_ablation_table(analysis: dict[str, Any]) -> str:
    return _language_op_table(analysis)


def _symbolic_language_table(analysis: dict[str, Any]) -> str:
    rows = ["| split | score |", "|---|---:|"]
    payload = analysis.get("execution_summary", {}).get(
        "symbolic_language_retention_stage", {}
    )
    for split, values in sorted(payload.items()):
        if split.startswith("state_parse"):
            score = values.get("parse", {}).get("full_parse_accuracy")
        else:
            score = values.get("final_nem")
        rows.append(f"| {split} | {_fmt(score)} |")
    return (
        "\n".join(rows)
        if len(rows) > 2
        else "No symbolic+language retention results yet."
    )


def _composition_table(analysis: dict[str, Any]) -> str:
    gate = analysis.get("composition_gate", {})
    if not gate.get("should_run"):
        return f"Skipped by gate: {gate.get('reason')} (ADD train/unseen={_fmt(gate.get('add_train'))}/{_fmt(gate.get('add_unseen'))}, SUB train/unseen={_fmt(gate.get('sub_train'))}/{_fmt(gate.get('sub_unseen'))})."
    rows = ["| split | final | step1 | step2 |", "|---|---:|---:|---:|"]
    payload = next(iter(analysis.get("composition_summary", {}).values()), {})
    for split, values in sorted(payload.items()):
        trace = values.get("trace", {})
        rows.append(
            f"| {split} | {_fmt(values.get('final_nem'))} | "
            f"{_fmt(trace.get('step1_accuracy'))} | {_fmt(trace.get('step2_accuracy'))} |"
        )
    return (
        "\n".join(rows)
        if len(rows) > 2
        else "Composition gate passed but results are missing."
    )


def _dataset_notes(manifest: dict[str, Any]) -> str:
    if not manifest:
        return "No manifest available."
    return (
        "- 30k primitive scale uses balanced repeat coverage over finite two-digit candidate spaces when unique prompts are exhausted.\n"
        "- STATE templates are split into train-pool families 0-19, paraphrase-heldout 20-24, and lexical-heldout 25-29.\n"
        f"- language verification: `{manifest.get('language', {}).get('verification', {})}`"
    )


def _decision(analysis: dict[str, Any]) -> str:
    best = analysis.get("best_symbolic", {})
    weak_symbolic = [
        task
        for task in ("add", "sub", "missing_addend", "compare_sum")
        if (best.get(task, {}).get("train") or 0.0) < 0.99
        or (best.get(task, {}).get("unseen") or 0.0) < 0.95
    ]
    parts: list[str] = []
    if weak_symbolic:
        parts.append(
            "OUTCOME F: symbolic primitives are mostly stabilized, but not all "
            f"hit the target. Weak symbolic tasks: {', '.join(weak_symbolic)}."
        )
    else:
        parts.append("Symbolic primitives hit the stabilization gate.")
    lang = analysis.get("language_summary", {}).get("language_parse_templates_20", {})
    parse_scores = [
        values.get("parse", {}).get("full_parse_accuracy", 0.0)
        for split, values in lang.items()
        if split in {"paraphrase", "lexical"}
    ]
    if parse_scores and min(parse_scores) < 0.90:
        parts.append(
            "OUTCOME E: language OP/PARSE does not generalize enough on held-out templates."
        )
    exec_payload = analysis.get("execution_summary", {}).get(
        "language_execution_templates_20", {}
    )
    exec_scores = [
        values.get("final_nem", 0.0)
        for split, values in exec_payload.items()
        if split in {"paraphrase", "lexical"}
    ]
    if exec_scores and min(exec_scores) < 0.90:
        parts.append(
            "OUTCOME D: language-to-execution remains weak even when evaluated separately."
        )
    comp = analysis.get("composition_summary", {})
    if comp:
        comp_payload = next(iter(comp.values()))
        score = comp_payload.get("unseen", {}).get("final_nem", 0.0)
        step1 = comp_payload.get("unseen", {}).get("trace", {}).get("step1_accuracy")
        step2 = comp_payload.get("unseen", {}).get("trace", {}).get("step2_accuracy")
        if score >= 0.90:
            parts.append(
                "OUTCOME A: trained ADD_SUB is stable enough for held-out composition."
            )
        else:
            parts.append(
                "OUTCOME B: ADD_SUB composition remains weak "
                f"(unseen final={score:.4f}, step1={step1:.4f}, step2={step2:.4f})."
            )
    else:
        parts.append("Composition decision is gated until missing runs complete.")
    return " ".join(parts)


def _next_milestone(analysis: dict[str, Any]) -> str:
    decision = _decision(analysis)
    if "OUTCOME B" in decision:
        return "Investigate working-memory/state-transition bottleneck with teacher-forced traces."
    if "OUTCOME D" in decision:
        return "Investigate routing/context transfer from structured parse to symbolic execution."
    if "OUTCOME E" in decision:
        return "Build a richer controlled language-template curriculum before language execution."
    if "OUTCOME F" in decision:
        return "Inspect objective/capacity/checkpoint selection for symbolic primitives before reasoning architecture."
    if "OUTCOME A" in decision:
        return "Proceed to M-18 true held-out compositional generalization."
    return "Finish missing M-17.1 runs and rebuild the report."


def _symbolic_stage_defs() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        ("stage1_add_sub", ("add", "sub")),
        ("stage2_missing", ("add", "sub", "missing_addend")),
        ("stage3_compare_numbers", ("add", "sub", "missing_addend", "compare_numbers")),
        ("stage4_compare_sum", SYMBOLIC_TASKS),
    )


def _symbolic_staged_specs_for_analysis() -> list[RunSpec]:
    return [
        RunSpec(
            name=f"symbolic_staged_{index}_{stage_name}",
            train_path=DATASET_DIR / "symbolic" / f"{stage_name}.jsonl",
            eval_path=DATASET_DIR
            / "symbolic"
            / "add"
            / "scale_30000"
            / "eval_seen.jsonl",
            steps=STAGED_STEPS,
            group="symbolic_staged",
            seed=SEED + 600 + index,
        )
        for index, (stage_name, _tasks) in enumerate(_symbolic_stage_defs(), start=1)
    ]


def _available_checkpoints(spec: RunSpec) -> dict[int, Path]:
    checkpoint_dir = RUNS_DIR / spec.name / "checkpoints"
    if not checkpoint_dir.exists():
        return {}
    result: dict[int, Path] = {}
    for path in sorted(checkpoint_dir.glob("step_*.pt")):
        try:
            step = int(path.stem.removeprefix("step_"))
        except ValueError:
            continue
        result[step] = path
    return result


def _checkpoint_path(spec: RunSpec, step: int) -> Path:
    return RUNS_DIR / spec.name / "checkpoints" / f"step_{step:06d}.pt"


def _spec_payload(spec: RunSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "train_path": str(spec.train_path),
        "eval_path": str(spec.eval_path),
        "steps": spec.steps,
        "group": spec.group,
        "seed": spec.seed,
        "model_config": spec.model_config,
        "sequence_length": spec.sequence_length,
        "init_checkpoint": str(spec.init_checkpoint) if spec.init_checkpoint else None,
    }


def _primitive_task_scale_from_name(name: str) -> tuple[str, int]:
    if name == "primitive_compare_numbers_control":
        return "compare_numbers", 3000
    prefix = "primitive_"
    middle = name.removeprefix(prefix)
    task, scale_text = middle.rsplit("_scale_", 1)
    return task, int(scale_text)


def _balanced_sample_unique[T](
    items: Sequence[T],
    count: int,
    *,
    key_fn: Callable[[T], Any],
    seed: int,
) -> list[T]:
    rng = random.Random(seed)
    buckets: dict[Any, list[T]] = defaultdict(list)
    for item in items:
        buckets[key_fn(item)].append(item)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    selected: list[T] = []
    keys = sorted(buckets, key=str)
    while len(selected) < count and any(buckets[key] for key in keys):
        for key in keys:
            if buckets[key]:
                selected.append(buckets[key].pop())
                if len(selected) >= count:
                    break
    rng.shuffle(selected)
    if len(selected) < count:
        raise ValueError(
            f"Could only sample {len(selected)} unique items out of {count}"
        )
    return selected


def _repeat_balanced[T](
    items: Sequence[T],
    count: int,
    *,
    key_fn: Callable[[T], Any],
    seed: int,
) -> list[T]:
    rng = random.Random(seed)
    buckets: dict[Any, list[T]] = defaultdict(list)
    for item in items:
        buckets[key_fn(item)].append(item)
    keys = sorted(buckets, key=str)
    cursors = {key: 0 for key in keys}
    for bucket in buckets.values():
        rng.shuffle(bucket)
    selected: list[T] = []
    while len(selected) < count:
        for key in keys:
            bucket = buckets[key]
            if not bucket:
                continue
            selected.append(bucket[cursors[key] % len(bucket)])
            cursors[key] += 1
            if len(selected) >= count:
                break
    rng.shuffle(selected)
    return selected


def _balanced_mix(
    record_groups: Sequence[Sequence[dict[str, Any]]],
    *,
    count_per_bucket: int,
    seed: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    result: list[dict[str, Any]] = []
    for group_index, records in enumerate(record_groups):
        if not records:
            continue
        for index in range(count_per_bucket):
            record = records[index % len(records)]
            cloned = json.loads(json.dumps(record, ensure_ascii=False))
            cloned["id"] = f"{record['id']}.mix{group_index}.{index:06d}"
            result.append(cloned)
    rng.shuffle(result)
    return result


def _shuffled(records: Sequence[dict[str, Any]], *, seed: int) -> list[dict[str, Any]]:
    result = list(records)
    random.Random(seed).shuffle(result)
    return result


def _dedup_records_by_prompt(
    records: Sequence[dict[str, Any]],
    *,
    fallback: Sequence[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    prompts: set[str] = set()
    for record in [*records, *fallback]:
        prompt = str(record["prompt"])
        if prompt in prompts:
            continue
        prompts.add(prompt)
        cloned = json.loads(json.dumps(record, ensure_ascii=False))
        cloned["id"] = f"{record['id']}.dedup{len(result):06d}"
        result.append(cloned)
        if len(result) >= count:
            return result
    raise ValueError(f"Could only build {len(result)} prompt-unique records")


def _write_jsonl(path: Path, records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")
    return {"path": str(path), "count": len(records)}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_splits(splits: dict[str, Sequence[dict[str, Any]]]) -> dict[str, Any]:
    prompts = {
        name: [record["prompt"] for record in records]
        for name, records in splits.items()
    }
    train_prompts = set(prompts.get("train", prompts.get("train_add_sub", [])))
    return {
        "prompt_duplicates": {
            name: _duplicate_count(values) for name, values in prompts.items()
        },
        "prompt_intersection_with_train": {
            name: len(train_prompts.intersection(values))
            for name, values in prompts.items()
            if not name.startswith("train")
        },
        "task_counts": {
            name: dict(Counter(record["task_type"] for record in records))
            for name, records in splits.items()
        },
    }


def _verify_language_manifest(
    splits: dict[str, Sequence[dict[str, Any]]],
) -> dict[str, Any]:
    train_prompts = set()
    for name, records in splits.items():
        if name.endswith("train_20"):
            train_prompts.update(record["prompt"] for record in records)
    return {
        name: len(train_prompts.intersection(record["prompt"] for record in records))
        for name, records in splits.items()
        if "eval" in name
    }


def _distribution(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "carry_bucket",
        "borrow_bucket",
        "output_length",
        "answer_range",
        "relation",
    )
    metadata = [record.get("metadata", {}) for record in records]
    return {
        key: dict(Counter(str(item[key]) for item in metadata if key in item))
        for key in keys
    }


def _duplicate_count(values: Iterable[str]) -> int:
    counts = Counter(values)
    return sum(count - 1 for count in counts.values() if count > 1)


def _parse_structured(text: str) -> dict[str, str | None]:
    return {
        "op": _regex_value(OP_RE, text),
        "a": _regex_value(A_RE, text),
        "b": _regex_value(B_RE, text),
    }


def _regex_value(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _final_nem(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    return payload["overall"].get("final_normalized_exact_match")


def _last_train_loss(path: Path) -> float | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        return None
    return json.loads(lines[-1]).get("train_loss")


def _case_key(task: str, case: tuple[int, ...]) -> str:
    return f"{task}:{':'.join(str(value) for value in case)}"


def _task_offset(task: str) -> int:
    return sum(ord(char) for char in task)


def _carry_bucket(a: int, b: int) -> str:
    units_carry = a % 10 + b % 10 >= 10
    final_carry = a + b >= 100
    if final_carry:
        return "final_carry"
    if units_carry:
        return "units_carry"
    return "no_carry"


def _compare_relation(a: int, b: int) -> str:
    if a > b:
        return "GT"
    if a < b:
        return "LT"
    return "EQUAL"


def _compare_sum_answer(case: tuple[int, int, int, int]) -> str:
    left = case[0] + case[1]
    right = case[2] + case[3]
    if left > right:
        return "LEFT"
    if right > left:
        return "RIGHT"
    return "EQUAL"


def _template_bucket(family: int) -> str:
    if family < 20:
        return "seen_pool"
    if family < 25:
        return "paraphrase_heldout"
    return "lexical_heldout"


def _rate(values: Sequence[bool]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _bucket_text(buckets: dict[str, Any]) -> str:
    parts = []
    for key, values in sorted(buckets.items()):
        if not isinstance(values, dict):
            continue
        inner = ", ".join(
            f"{name}:{_fmt(payload.get('final_nem'))}"
            for name, payload in sorted(values.items())
            if isinstance(payload, dict)
        )
        if inner:
            parts.append(f"{key}({inner})")
    return "; ".join(parts) if parts else "n/a"


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
