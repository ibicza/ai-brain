"""Reject-option selection uses calibration only, never final answers."""

from types import SimpleNamespace

import numpy as np
import pytest
from m33_primary_composition_pilot import calibrate, course


def data(native_scores, authored_scores):
    records, labels, probabilities, cohorts = [], [], [], []
    for task, values in course.VALUES.items():
        answer = course.ANSWERS.index(values[0])
        for name, scores in (("native", native_scores), ("authored", authored_scores)):
            for score in scores:
                p = np.zeros(len(course.ANSWERS))
                p[answer], p[course.UNKNOWN] = score, 1 - score
                records.append({"task": task})
                labels.append(answer)
                probabilities.append(p)
                cohorts.append(name)
            for _ in range(2):
                p = np.zeros(len(course.ANSWERS))
                p[course.UNKNOWN] = 1
                records.append({"task": task})
                labels.append(course.UNKNOWN)
                probabilities.append(p)
                cohorts.append(name)
    return (
        SimpleNamespace(data={"records": records, "labels": np.array(labels)}),
        np.array(probabilities),
        cohorts,
    )


def test_strict_rule_uses_highest_safe_threshold_without_refusing_everything():
    prepared, p, cohorts = data([0.96] * 2 + [0.985] * 8, [0.91] * 2 + [0.985] * 8)
    default, _ = calibrate(prepared, p, 1)
    strict, report = calibrate(
        prepared, p, 1, rule="coverage_guarded_strict", cohorts=cohorts
    )
    assert default == {task: 0.9 for task in course.VALUES}
    assert strict == {task: 0.98 for task in course.VALUES}
    assert report["selection_split"] == "calibration_only"
    for task in course.VALUES:
        for m in report["tasks"][task]["cohort_metrics"].values():
            assert (
                m["false_assertions"] == 0
                and m["answerable_recall"] == 0.8
                and m["unknown_recall"] == 1
            )


def test_native_majority_cannot_hide_authored_recall_collapse():
    prepared, p, cohorts = data([0.9995] * 90, [0.96] * 10)
    selected, report = calibrate(
        prepared, p, 1, rule="coverage_guarded_strict", cohorts=cohorts
    )
    assert selected == {task: 0.95 for task in course.VALUES}
    assert all(
        report["tasks"][task]["cohort_metrics"]["authored"]["answerable_recall"] == 1
        for task in course.VALUES
    )


def test_no_eligible_threshold_is_honest_unknown_not_an_invented_safe_answer():
    prepared, p, cohorts = data([0.7] * 10, [0.7] * 10)
    selected, report = calibrate(
        prepared, p, 1, rule="coverage_guarded_strict", cohorts=cohorts
    )
    assert selected == {task: None for task in course.VALUES}
    assert all(
        report["tasks"][task]["metrics"]["accepted"] == 0 for task in course.VALUES
    )


@pytest.mark.parametrize(
    "cohorts", [None, [], ["native"], ["final"] * 72, np.array(["native"] * 72)]
)
def test_missing_or_untrusted_cohort_inventory_is_rejected(cohorts):
    prepared, p, _ = data([0.98] * 10, [0.98] * 10)
    with pytest.raises(ValueError, match="aligned calibration cohorts"):
        calibrate(prepared, p, 1, rule="coverage_guarded_strict", cohorts=cohorts)


@pytest.mark.parametrize(
    "rule,minimum",
    [
        ("choose_using_final_accuracy", 40),
        (True, 40),
        ("maximum_coverage", True),
        ("maximum_coverage", 0),
    ],
)
def test_invalid_selection_rules_and_aliased_support_counts_are_rejected(rule, minimum):
    prepared, p, _ = data([0.98] * 10, [0.98] * 10)
    with pytest.raises(ValueError, match="calibration rule"):
        calibrate(prepared, p, minimum, rule=rule)
