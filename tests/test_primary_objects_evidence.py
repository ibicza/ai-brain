"""Arithmetic verifier rejects false confidence and ignores no-error-only claims."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "object_audit",
    Path(__file__).resolve().parents[1] / "scripts/m33_verify_objects_evidence.py",
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_correct_class_selected_with_frozen_threshold():
    p = [0.0] * 91
    p[73] = 0.999
    p[18] = 0.001
    assert audit.selected(p, 0.995) == "яблоко"
    assert audit.selected(p, 0.9999) == "UNKNOWN"
    assert audit.selected(p, None) == "UNKNOWN"


def test_invalid_word_token_not_a_fact():
    p = [0.0] * 91
    p[88] = 1.0
    assert audit.selected(p, 0.99) == "UNKNOWN"


@pytest.mark.parametrize(
    "values", [[0.0] * 91, [float("inf")] * 91, [1.0], [-1.0] * 91]
)
def test_invalid_saved_probability_vectors_rejected(values):
    with pytest.raises(ValueError):
        audit.selected(values, 0.99)


def test_wrong_assertion_is_counted_not_hidden():
    rows = [
        {"gold": "яблоко", "selected": "книга"},
        {"gold": "UNKNOWN", "selected": "яблоко"},
        {"gold": "книга", "selected": "UNKNOWN"},
    ]
    stats = audit.statistics(rows)
    assert stats["false_assertions"] == 2
    assert stats["accepted"] == 2
    assert stats["answerable_recall"] == 0
    assert stats["unknown_recall"] == 0


def test_all_unknown_is_not_mastery():
    rows = [{"gold": "яблоко", "selected": "UNKNOWN"}] * 5 + [
        {"gold": "UNKNOWN", "selected": "UNKNOWN"}
    ]
    stats = audit.statistics(rows)
    assert stats["false_assertions"] == 0
    assert stats["accepted"] == 0
    assert stats["answerable_recall"] == 0
