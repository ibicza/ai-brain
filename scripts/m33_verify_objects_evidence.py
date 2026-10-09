"""Independent saved-probability arithmetic/hash audit; no PyTorch or training.

Checks bookkeeping against the prepared curated gold, not independent label truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

LABELS = dict(
    enumerate(
        (
            "0",
            "1",
            "2",
            "3",
            "4",
            "5",
            "круг",
            "овал",
            "квадрат",
            "прямоугольник",
            "треугольник",
            "звезда",
            "красный",
            "синий",
            "зелёный",
            "жёлтый",
            "оранжевый",
            "фиолетовый",
            "UNKNOWN",
        )
    )
)
LABELS.update({47: "YES", 48: "NO"})
LABELS.update(
    dict(
        enumerate(
            ("яблоко", "банан", "морковь", "рыба", "дерево", "кружка", "стул", "книга"),
            73,
        )
    )
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def statistics(rows):
    if not rows:
        raise ValueError("Empty saved prediction cohort")
    answerable = sum(r["gold"] != "UNKNOWN" for r in rows)
    unknown = len(rows) - answerable
    return {
        "examples": len(rows),
        "accepted": sum(r["selected"] != "UNKNOWN" for r in rows),
        "false_assertions": sum(
            r["selected"] != "UNKNOWN" and r["selected"] != r["gold"] for r in rows
        ),
        "accuracy": sum(r["selected"] == r["gold"] for r in rows) / len(rows),
        "answerable_recall": sum(
            r["selected"] == r["gold"] and r["gold"] != "UNKNOWN" for r in rows
        )
        / answerable
        if answerable
        else None,
        "unknown_recall": sum(r["selected"] == r["gold"] == "UNKNOWN" for r in rows)
        / unknown
        if unknown
        else None,
    }


def selected(p, threshold):
    if (
        len(p) != 91
        or any(
            not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in p
        )
        or not math.isclose(sum(p), 1, abs_tol=1e-5)
    ):
        raise ValueError("Invalid saved probabilities")
    if threshold is None:
        return "UNKNOWN"
    if not 0 <= threshold <= 1:
        raise ValueError("Invalid frozen threshold")
    index = max(range(len(p)), key=p.__getitem__)
    return LABELS.get(index, "UNKNOWN") if p[index] >= threshold else "UNKNOWN"


def verify(root: Path, data: Path):
    report = read(root / "report.json")
    protocol = read(root / "protocol.json")
    frozen = read(root / "frozen-calibration.json")
    dataset = read(data / "dataset.json")
    if not (
        report["checkpoint_sha256"]
        == frozen["checkpoint_sha256"]
        == sha(root / "best.pt")
        and report["protocol_sha256"]
        == frozen["protocol_sha256"]
        == sha(root / "protocol.json")
        and report["thresholds"] == frozen["thresholds"]
        and report["dataset_sha256"]
        == protocol["dataset_sha256"]
        == sha(data / "dataset.json")
        and dataset["pixels_sha256"]
        == protocol["pixels_sha256"]
        == sha(data / "pixels.npz")
    ):
        raise ValueError("Frozen evidence hashes/policy mismatch")
    total = 0
    cohorts = [
        ("object-final", "object_final", "final"),
        ("textbook-diagnostic", "textbook_diagnostic", "textbook_diagnostic"),
        ("legacy-final", "legacy_final", None),
        ("legacy-transfer", "legacy_transfer", None),
    ]
    if "object_regression" in report["tests"]:
        cohorts.append(("object-regression", "object_regression", "regression"))
    for mode in ("blank", "shuffled"):
        if (root / ("object-" + mode + "-predictions.json")).exists():
            cohorts.append(("object-" + mode, "object_" + mode, "final"))
    for name, key, source_split in cohorts:
        rows = read(root / (name + "-predictions.json"))
        for row in rows:
            if row["gold"] not in LABELS.values() or row["selected"] != selected(
                row["probabilities"], report["thresholds"][row["task"]]
            ):
                raise ValueError("Saved selector mismatch")
        if source_split:
            source = dataset["records"][source_split]
            if [(r["source_id"], r["gold"]) for r in rows] != [
                (r["source_id"], r["answer"]) for r in source
            ]:
                raise ValueError("Curated source/gold cohort mismatch")
        expected = report["tests"][key]
        if expected["all"] != statistics(rows):
            raise ValueError("Saved aggregate arithmetic mismatch")
        for task in {r["task"] for r in rows}:
            if expected[task] != statistics([r for r in rows if r["task"] == task]):
                raise ValueError("Saved skill arithmetic mismatch")
        if "by_concept" in expected:
            for label, value in expected["by_concept"].items():
                if value != statistics([r for r in rows if r["gold"] == label]):
                    raise ValueError("Saved concept arithmetic mismatch")
        total += len(rows)
    stat = report["tests"]["object_final"]["all"]
    object_gate = (
        stat["accepted"] >= 50
        and stat["false_assertions"] == 0
        and (stat["answerable_recall"] or 0) >= 0.8
        and (stat["unknown_recall"] or 0) >= 0.9
    )
    object_gate = (
        object_gate
        and len(report["tests"]["object_final"]["by_concept"]) == 8
        and all(
            v["accepted"] >= 5 and (v["answerable_recall"] or 0) >= 0.8
            for v in report["tests"]["object_final"]["by_concept"].values()
        )
    )
    for mode in ("blank", "shuffled"):
        object_gate = (
            object_gate
            and (stat["answerable_recall"] or 0)
            - (report["tests"]["object_" + mode]["all"]["answerable_recall"] or 0)
            >= 0.15
        )
    object_gate = (
        object_gate
        and report["tests"]["textbook_diagnostic"]["all"]["false_assertions"] == 0
    )
    retention = {}
    for split in ("final", "transfer"):
        for task in (
            "count",
            "shape",
            "color",
            "same_shape",
            "same_color",
            "horizontal",
            "vertical",
        ):
            value = report["tests"]["legacy_" + split][task]
            baseline = report["tests"]["previous_baseline_" + split][task]
            passed = (
                value["accepted"] >= 50
                and value["false_assertions"] == 0
                and (value["answerable_recall"] or 0) >= 0.8
                and (value["unknown_recall"] or 0) >= 0.9
                and (value["answerable_recall"] or 0)
                >= (baseline["answerable_recall"] or 0) - 0.02
            )
            retention[task] = retention.get(task, True) and passed
    regression_gate = True
    if "object_regression" in report["tests"]:
        rstat = report["tests"]["object_regression"]["all"]
        regression_gate = (
            rstat["false_assertions"] == 0
            and (rstat["answerable_recall"] or 0) >= 0.8
            and (rstat["unknown_recall"] or 0) >= 0.9
        )
        if regression_gate != report["regression_gate"]:
            raise ValueError("Saved regression gate mismatch")
    status = (
        "BOUNDED_OBJECT_GATE_PASSED_NOT_PRODUCTION"
        if object_gate and all(retention.values()) and regression_gate
        else "REJECTED_NOT_PRODUCTION"
    )
    if (
        bool(object_gate) != report["object_gate"]
        or retention != report["retention_gates"]
        or status != report["status"]
    ):
        raise ValueError("Saved gate/status mismatch")
    calibration_records = 0
    diagnostic_path = root / "calibration-diagnostics.json"
    if diagnostic_path.exists():
        diagnostic = read(diagnostic_path)
        if (
            diagnostic["checkpoint_sha256"] != sha(root / "best.pt")
            or diagnostic["dataset_sha256"] != sha(data / "dataset.json")
            or diagnostic["frozen_policy_sha256"]
            != sha(root / "frozen-calibration.json")
        ):
            raise ValueError("Calibration diagnostic hashes changed")
        rows = diagnostic["records"]
        if [(r["source_id"], r["gold"]) for r in rows] != [
            (r["source_id"], r["answer"]) for r in dataset["records"]["calibration"]
        ]:
            raise ValueError("Calibration diagnostic source/gold mismatch")
        if any(r["selected"] != selected(r["probabilities"], 0) for r in rows):
            raise ValueError("Calibration raw selector mismatch")
        if statistics(rows) != diagnostic["raw_consensus"]:
            raise ValueError("Calibration raw arithmetic mismatch")
        if [v["threshold"] for v in diagnostic["grid"]] != [
            0.99,
            0.995,
            0.999,
            0.9995,
            0.9999,
        ]:
            raise ValueError("Calibration threshold grid changed")
        eligible = []
        for entry in diagnostic["grid"]:
            stats = statistics(
                [
                    dict(r, selected=selected(r["probabilities"], entry["threshold"]))
                    for r in rows
                ]
            )
            admitted = stats["accepted"] >= 50 and stats["false_assertions"] == 0
            if stats != entry["stats"] or admitted != entry["eligible"]:
                raise ValueError("Calibration threshold arithmetic mismatch")
            if admitted:
                eligible.append((stats["accepted"], entry["threshold"]))
        expected_threshold = max(eligible)[1] if eligible else None
        if (
            expected_threshold != diagnostic["frozen_threshold"]
            or expected_threshold != frozen["thresholds"]["object"]
        ):
            raise ValueError("Frozen calibration selection mismatch")
        calibration_records = len(rows)
    return {
        "status": "VERIFIED_ARITHMETIC_NOT_INDEPENDENT_SEMANTIC_TRUTH",
        "prediction_records": total,
        "calibration_diagnostic_records": calibration_records,
        "report_sha256": sha(root / "report.json"),
        "checkpoint_sha256": sha(root / "best.pt"),
        "object_gate": bool(object_gate),
        "retention_gates": retention,
        "limits": "Independent pure-Python selector/metric/gate bookkeeping, not independent source-label verification, blind exam, training replay, or proof of general honesty.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.experiment, args.data)
    with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
