from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_brain.eval.final_answer import extract_final_answer, normalize_final_answer

_ADD_TASK_TYPES = {
    "arithmetic.add_2digit_composed",
    "arithmetic.add_2digit_no_carry",
    "arithmetic.add_2digit_with_carry",
    "arithmetic.add",
}
_SUB_TASK_TYPES = {
    "arithmetic.sub_2digit_composed",
    "arithmetic.sub_2digit_no_borrow",
    "arithmetic.sub_2digit_with_borrow",
    "arithmetic.subtract",
}
_ROW_RE = re.compile(
    r"(?im)^\s*(?P<label>[A-Z]?(?:_)?[UTH])\s+"
    r"(?P<left>\d+)\s+(?P<right>\d+)\s+"
    r"(?:(?P<state_in_prefix>[CB])\s*)?(?P<state_in>\d+)\s*->\s*"
    r"(?:(?:S)\s*)?(?P<digit>\d+)\s+"
    r"(?:(?P<state_out_prefix>[CB])\s*)?(?P<state_out>\d+)\s*$"
)
_OUT_RE = re.compile(r"(?im)^\s*(?P<label>OUT|OUT_RTL)\b\s*(?P<value>.+?)\s*$")


def analyze_arithmetic_forensics(
    *,
    predictions_path: Path,
    eval_path: Path,
    train_path: Path | None = None,
) -> dict[str, Any]:
    examples = {str(record["id"]): record for record in _read_jsonl(eval_path)}
    train_combos = _digit_combo_set(_read_jsonl(train_path)) if train_path else set()
    predictions = list(_iter_joined_predictions(predictions_path, examples))

    addition = _bucket_analysis(
        predictions,
        operation="add",
        train_combos=train_combos,
    )
    subtraction = _bucket_analysis(
        predictions,
        operation="sub",
        train_combos=train_combos,
    )
    return {
        "predictions_path": str(predictions_path),
        "eval_path": str(eval_path),
        "train_path": str(train_path) if train_path else None,
        "addition": addition,
        "subtraction": subtraction,
    }


def output_length_distribution(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        name: _length_distribution_for_records(list(_read_jsonl(path)))
        for name, path in sorted(paths.items())
    }


@dataclass
class _BucketAccumulator:
    count: int = 0
    final_correct: int = 0
    digit_correct: int = 0
    digit_total: int = 0
    place_correct: dict[str, int] = field(
        default_factory=lambda: {"units": 0, "tens": 0, "hundreds": 0}
    )
    place_total: dict[str, int] = field(
        default_factory=lambda: {"units": 0, "tens": 0, "hundreds": 0}
    )
    state_correct: int = 0
    state_total: int = 0
    u_row_correct: int = 0
    u_row_total: int = 0
    t_row_correct: int = 0
    t_row_total: int = 0
    state_row_correct: int = 0
    state_row_total: int = 0
    out_correct: int = 0
    out_total: int = 0

    def add(self, prediction: dict[str, Any], *, operation: str) -> None:
        metadata = prediction["metadata"]
        a = int(metadata["a"])
        b = int(metadata["b"])
        expected_value = a + b if operation == "add" else a - b
        expected = str(expected_value)
        predicted = normalize_final_answer(
            extract_final_answer(str(prediction.get("predicted", "")))
        )

        self.count += 1
        if predicted == expected:
            self.final_correct += 1

        _add_digit_metrics(self, expected=expected, predicted=predicted)
        _add_trace_metrics(
            self,
            expected_text=str(prediction.get("expected", "")),
            predicted_text=str(prediction.get("predicted", "")),
            operation=operation,
        )

    def as_dict(self) -> dict[str, Any]:
        if self.count == 0:
            return {
                "count": 0,
                "final_normalized_exact_match": 0.0,
                "per_digit_accuracy": 0.0,
                "units_accuracy": None,
                "tens_accuracy": None,
                "hundreds_accuracy": None,
                "carry_or_borrow_prediction_accuracy": None,
                "u_row_accuracy": None,
                "t_row_accuracy": None,
                "carry_or_borrow_state_accuracy": None,
                "out_accuracy": None,
            }
        return {
            "count": self.count,
            "final_normalized_exact_match": self.final_correct / self.count,
            "per_digit_accuracy": _safe_rate(self.digit_correct, self.digit_total),
            "units_accuracy": _optional_rate(
                self.place_correct["units"], self.place_total["units"]
            ),
            "tens_accuracy": _optional_rate(
                self.place_correct["tens"], self.place_total["tens"]
            ),
            "hundreds_accuracy": _optional_rate(
                self.place_correct["hundreds"],
                self.place_total["hundreds"],
            ),
            "carry_or_borrow_prediction_accuracy": _optional_rate(
                self.state_correct,
                self.state_total,
            ),
            "u_row_accuracy": _optional_rate(self.u_row_correct, self.u_row_total),
            "t_row_accuracy": _optional_rate(self.t_row_correct, self.t_row_total),
            "carry_or_borrow_state_accuracy": _optional_rate(
                self.state_row_correct,
                self.state_row_total,
            ),
            "out_accuracy": _optional_rate(self.out_correct, self.out_total),
        }


def _bucket_analysis(
    predictions: list[dict[str, Any]],
    *,
    operation: str,
    train_combos: set[str],
) -> dict[str, Any]:
    buckets: dict[str, _BucketAccumulator] = defaultdict(_BucketAccumulator)
    for prediction in predictions:
        task_type = str(prediction["task_type"])
        if operation == "add" and task_type not in _ADD_TASK_TYPES:
            continue
        if operation == "sub" and task_type not in _SUB_TASK_TYPES:
            continue
        bucket_names = (
            _addition_buckets(prediction, train_combos)
            if operation == "add"
            else _subtraction_buckets(prediction, train_combos)
        )
        for bucket_name in ["all", *bucket_names]:
            buckets[bucket_name].add(prediction, operation=operation)
    return {
        "buckets": {
            name: buckets[name].as_dict()
            for name in sorted(buckets, key=_bucket_sort_key)
        }
    }


def _addition_buckets(
    prediction: dict[str, Any],
    train_combos: set[str],
) -> list[str]:
    metadata = prediction["metadata"]
    a = int(metadata["a"])
    b = int(metadata["b"])
    units_carry = a % 10 + b % 10 >= 10
    final_carry = a + b >= 100
    names = []
    if not units_carry and not final_carry:
        names.append("no_carry")
    if units_carry or final_carry:
        names.append("carry")
    if units_carry and not final_carry:
        names.append("units_carry_only")
    if final_carry:
        names.append("overflow_to_new_digit")
        names.append("result_3digit")
    else:
        names.append("result_2digit")
    names.append(_combo_bucket(metadata, train_combos))
    return names


def _subtraction_buckets(
    prediction: dict[str, Any],
    train_combos: set[str],
) -> list[str]:
    metadata = prediction["metadata"]
    a = int(metadata["a"])
    b = int(metadata["b"])
    borrow = a % 10 < b % 10
    result = a - b
    names = ["borrow" if borrow else "no_borrow"]
    names.append("result_1digit" if result < 10 else "result_2digit")
    names.append(_combo_bucket(metadata, train_combos))
    return names


def _combo_bucket(metadata: dict[str, Any], train_combos: set[str]) -> str:
    keys = [str(key) for key in metadata.get("digit_combo_keys", [])]
    if not train_combos or not keys:
        return "unknown_digit_combo"
    return (
        "seen_digit_combo"
        if all(key in train_combos for key in keys)
        else "unseen_digit_combo"
    )


def _add_digit_metrics(
    stats: _BucketAccumulator,
    *,
    expected: str,
    predicted: str,
) -> None:
    expected_digits = [char for char in expected if char.isdigit()]
    predicted_digits = [char for char in predicted if char.isdigit()]
    for index, expected_digit in enumerate(reversed(expected_digits)):
        predicted_index = len(predicted_digits) - 1 - index
        predicted_digit = (
            predicted_digits[predicted_index] if predicted_index >= 0 else None
        )
        correct = predicted_digit == expected_digit
        stats.digit_total += 1
        stats.digit_correct += int(correct)
        place = ("units", "tens", "hundreds")[index] if index < 3 else None
        if place is not None:
            stats.place_total[place] += 1
            stats.place_correct[place] += int(correct)


def _add_trace_metrics(
    stats: _BucketAccumulator,
    *,
    expected_text: str,
    predicted_text: str,
    operation: str,
) -> None:
    expected_rows = _parse_rows(expected_text)
    predicted_rows = _parse_rows(predicted_text)
    for label, total_attr, correct_attr in (
        ("U", "u_row_total", "u_row_correct"),
        ("T", "t_row_total", "t_row_correct"),
    ):
        if label in expected_rows:
            setattr(stats, total_attr, getattr(stats, total_attr) + 1)
            setattr(
                stats,
                correct_attr,
                getattr(stats, correct_attr)
                + int(predicted_rows.get(label) == expected_rows[label]),
            )
    for label in ("U", "T"):
        if label in expected_rows:
            stats.state_total += 1
            stats.state_row_total += 1
            expected_state = expected_rows[label]["state_out"]
            predicted_state = predicted_rows.get(label, {}).get("state_out")
            is_correct = predicted_state == expected_state
            stats.state_correct += int(is_correct)
            stats.state_row_correct += int(is_correct)
    expected_out = _parse_out(expected_text, operation=operation)
    predicted_out = _parse_out(predicted_text, operation=operation)
    if expected_out is not None:
        stats.out_total += 1
        stats.out_correct += int(predicted_out == expected_out)


def _parse_rows(text: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for match in _ROW_RE.finditer(text):
        label = match.group("label").split("_")[-1]
        rows[label] = {
            "left": match.group("left"),
            "right": match.group("right"),
            "state_in": match.group("state_in"),
            "digit": match.group("digit"),
            "state_out": match.group("state_out"),
        }
    return rows


def _parse_out(text: str, *, operation: str) -> str | None:
    matches = list(_OUT_RE.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    value = normalize_final_answer(match.group("value"))
    if match.group("label").upper() == "OUT_RTL":
        digits = [char for char in value if char.isdigit()]
        return "".join(reversed(digits))
    return value


def _length_distribution_for_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, int]] = {
        "addition": defaultdict(int),
        "subtraction": defaultdict(int),
    }
    counts = {"addition": 0, "subtraction": 0}
    for record in records:
        task_type = str(record["task_type"])
        metadata = dict(record.get("metadata", {}))
        if task_type in _ADD_TASK_TYPES:
            result = int(metadata["a"]) + int(metadata["b"])
            group = "addition"
        elif task_type in _SUB_TASK_TYPES:
            result = int(metadata["a"]) - int(metadata["b"])
            group = "subtraction"
        else:
            continue
        counts[group] += 1
        buckets[group][f"{len(str(result))}_digit"] += 1
    return {
        group: {
            "count": counts[group],
            "buckets": {
                bucket: {
                    "count": count,
                    "fraction": _safe_rate(count, counts[group]),
                }
                for bucket, count in sorted(buckets[group].items())
            },
        }
        for group in ("addition", "subtraction")
    }


def _iter_joined_predictions(
    predictions_path: Path,
    examples: dict[str, dict[str, Any]],
) -> Iterable[dict[str, Any]]:
    for prediction in _read_jsonl(predictions_path):
        example = examples.get(str(prediction.get("id")))
        if example is None:
            continue
        joined = dict(prediction)
        joined["metadata"] = dict(example.get("metadata", {}))
        joined["expected"] = str(prediction.get("expected", example.get("answer", "")))
        yield joined


def _read_jsonl(path: Path | None) -> Iterable[dict[str, Any]]:
    if path is None:
        return
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def _digit_combo_set(records: Iterable[dict[str, Any]]) -> set[str]:
    combos: set[str] = set()
    for record in records:
        metadata = dict(record.get("metadata", {}))
        combos.update(str(key) for key in metadata.get("digit_combo_keys", []))
    return combos


def _safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _optional_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _bucket_sort_key(name: str) -> tuple[int, str]:
    order = {
        "all": 0,
        "no_carry": 1,
        "carry": 2,
        "units_carry_only": 3,
        "overflow_to_new_digit": 4,
        "no_borrow": 5,
        "borrow": 6,
        "result_1digit": 7,
        "result_2digit": 8,
        "result_3digit": 9,
        "seen_digit_combo": 10,
        "unseen_digit_combo": 11,
        "unknown_digit_combo": 12,
    }
    return (order.get(name, 99), name)
