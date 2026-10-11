import importlib.util
import sys
from pathlib import Path

import pytest

from ai_brain.training import primary_composition as c

path = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(path))
try:
    spec = importlib.util.spec_from_file_location(
        "composition_compare_test", path / "m33_composition_compare.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
finally:
    sys.path.remove(str(path))


def rows():
    labels = [
        c.ANSWERS.index(a)
        for a in ("красный", "круг", "однотонный", "синий", "овал", "пятнистый")
    ]
    return [
        {"answer": labels[i], "task": task} for i, task in enumerate(list(c.VALUES) * 2)
    ]


def test_complete_description_metrics_not_individual_attribute_average():
    records = rows()
    predicted = [r["answer"] for r in records]
    predicted[1] = c.UNKNOWN
    report = module.score(records, predicted)
    assert report["overall"]["answerable_recall"] == 5 / 6
    assert report["complete_visible_descriptions"]["all_three_correct_rate"] == 0.5
    assert report["tasks"]["shape"]["answerable_recall"] == 0.5


def test_unknown_object_not_counted_as_complete_visible_description():
    records = rows()
    for row in records[:3]:
        row["answer"] = c.UNKNOWN
    report = module.score(records, [r["answer"] for r in records])
    assert report["complete_visible_descriptions"] == {
        "eligible_objects": 1,
        "all_three_correct_rate": 1.0,
    }
    assert report["overall"]["unknown_recall"] == 1.0


def test_comparison_rejects_partial_or_misaligned_records():
    with pytest.raises(ValueError):
        module.score(rows()[:3], [c.UNKNOWN] * 3)
    with pytest.raises(ValueError):
        module.score(rows(), [c.UNKNOWN])


def test_comparison_restores_original_precision_and_keeps_legacy_explicit():
    calls = []

    class Backend:
        def check_contract(self, contract):
            calls.append(("check", contract))
            return contract

        def configure(self, policy):
            calls.append(("configure", policy))
            return {"policy": policy}

    contract = {"policy": "ieee", "precision_settings": {"global": "ieee"}}
    assert module.restore_precision({"numeric_backend": contract}, Backend()) == contract
    assert calls == [("check", contract)]
    assert module.restore_precision({}, Backend()) == {"policy": "legacy"}
    assert calls[-1] == ("configure", "legacy")


def test_comparison_does_not_fall_back_when_precision_contract_is_invalid():
    class Backend:
        def check_contract(self, contract):
            raise ValueError("Frozen precision differs")

        def configure(self, policy):
            pytest.fail("Invalid frozen contract must not fall back")

    with pytest.raises(ValueError, match="Frozen precision differs"):
        module.restore_precision({"numeric_backend": {}}, Backend())
