"""The adaptive series must never promote a worse candidate or falsify its budget."""

import json

import m33_objects_five_evidence as evidence
import pytest
from m33_objects_data import sha
from m33_verify_objects_evidence import selected, statistics

from ai_brain.training import primary_objects as obj


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def series(tmp_path, monkeypatch):
    root, data = tmp_path / "series", tmp_path / "data"
    data.mkdir()
    save(data / "dataset.json", {})
    data_sha = sha(data / "dataset.json")
    monkeypatch.setattr(evidence, "DATA", data_sha)
    monkeypatch.setattr(evidence, "dev_audit", lambda *args: None)
    warm_sha = "initial-warm-hash"
    monkeypatch.setattr(evidence, "WARM", warm_sha)
    save(
        root / "development-v1/plan.json",
        {
            "dataset_sha256": data_sha,
            "warm_sha256": warm_sha,
            "trials": evidence.TRIALS,
        },
    )
    save(
        root / "development-v1/initial-anchor-score.json",
        {"checkpoint_sha256": warm_sha, "round_id": 10981, "best_dev_loss": 1.0},
    )
    rows = []
    for label in (*obj.OBJECTS, "UNKNOWN"):
        probability = [0.0] * obj.VOCAB_SIZE
        probability[obj.UNKNOWN if label == "UNKNOWN" else obj.OBJECT_IDS[label]] = 1.0
        rows.append(
            {
                "source_id": label,
                "gold": label,
                "probabilities": probability,
                "selected": selected(probability, 0),
            }
        )
    stats = statistics(rows)
    classes = {
        label: statistics([r for r in rows if r["gold"] == label])
        for label in obj.OBJECTS
    }
    receipts = []
    champion_sha, champion_score, champion_name = warm_sha, 1.0, "initial_warm"
    for number, (trial, score) in enumerate(
        zip(evidence.TRIALS, (0.9, 0.8, 0.85, 0.7, 0.72), strict=True), 1
    ):
        name = trial["name"]
        candidate = root / "development-v1" / name
        candidate.mkdir()
        (candidate / "best.pt").write_bytes(name.encode())
        config = {
            "steps": 10000,
            "round_id": 10981,
            "learning_rate": 0.00003,
            "paired_object_training": True,
            **{
                k: trial[k]
                for k in (
                    "consistency_weight",
                    "supervised_contrastive_weight",
                    "vicreg_weight",
                    "object_prompt_balancing",
                )
            },
            "object_readout_adapter": False,
        }
        protocol = {"warm_start_sha256": champion_sha, "config": config}
        save(candidate / "protocol.json", protocol)
        report = {
            "checkpoint_sha256": sha(candidate / "best.pt"),
            "protocol_sha256": sha(candidate / "protocol.json"),
            "dataset_sha256": data_sha,
            "production_admitted": False,
            "inherited_tensors_byte_preserved": True,
            "status": "DEVELOPMENT_ONLY_NO_CALIBRATION_OR_FINAL",
            "best_dev_loss": score,
            "history": [
                {"step": step, "dev_loss": score + (step != 500)}
                for step in range(500, 10001, 500)
            ],
        }
        save(candidate / "development-report.json", report)
        value = {
            mode: {"records": rows, "raw_not_safe_policy": stats}
            for mode in ("single_view", "five_view")
        }
        save(root / (name + "-dev-photo.json"), {"candidates": {name: value}})
        receipt = {
            "iteration": number,
            "trial": trial,
            "warm_sha256": champion_sha,
            "champion_score_before": champion_score,
            "object_readout_adapter": False,
            "fixed_99_five_view_dev": stats,
            "by_concept": classes,
            "raw_single_view": stats,
            "raw_five_view": stats,
            "best_dev_loss": score,
            "checkpoint_sha256": report["checkpoint_sha256"],
            "fresh_acceptance_passed": False,
            "dev_screen_viable": False,
            "promoted_by_development_loss": score < champion_score,
        }
        save(root / "development-v1" / (name + "-receipt.json"), receipt)
        receipts.append(receipt)
        if score < champion_score:
            champion_score, champion_sha, champion_name = (
                score,
                report["checkpoint_sha256"],
                name,
            )
    save(
        root / "selection-development-only.json",
        {
            "production_admitted": False,
            "fresh_acceptance_passed": False,
            "selection_used": "DEVELOPMENT_ONLY",
            "iterations": receipts,
            "winner": {
                "checkpoint_sha256": champion_sha,
                "best_dev_loss": champion_score,
                "name": champion_name,
            },
        },
    )
    return root, data


def test_valid_sequential_lineage_keeps_better_ancestor(series):
    result = evidence.audit_lineage(*series)
    assert result["training_steps"] == 50000
    assert result["winner"]["name"] == "iteration4_readout_pairs"
    assert not result["iterations"][2]["promoted_by_development_loss"]
    assert not result["iterations"][4]["promoted_by_development_loss"]


@pytest.mark.parametrize(
    "change", ["promote_worse", "skip_steps", "change_objective", "fake_blindness"]
)
def test_tampering_rejected(series, change):
    root, data = series
    name = evidence.TRIALS[2]["name"]
    if change == "promote_worse":
        path = root / "development-v1" / (name + "-receipt.json")
        value = evidence.load(path)
        value["promoted_by_development_loss"] = True
    elif change == "skip_steps":
        path = root / "development-v1" / name / "development-report.json"
        value = evidence.load(path)
        value["history"].pop()
    elif change == "change_objective":
        path = root / "development-v1" / name / "protocol.json"
        value = evidence.load(path)
        value["config"]["vicreg_weight"] = 5
    else:
        path = root / "selection-development-only.json"
        value = evidence.load(path)
        value["fresh_acceptance_passed"] = True
    save(path, value)
    with pytest.raises(ValueError):
        evidence.audit_lineage(root, data)
