"""Post-freeze photo learning/consistency diagnosis; never change selection or gates."""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from m33_objects_data import sha, write_json
from m33_primary_objects_pilot import ObjectPrepared, probabilities
from m33_verify_objects_evidence import selected, statistics

from ai_brain.training import primary_objects as obj


def audit(data, experiment, output):
    receipt = json.loads(output.read_text(encoding="utf-8"))
    dataset = json.loads((data / "dataset.json").read_text(encoding="utf-8"))
    policy = json.loads((experiment / "frozen-calibration.json").read_text())
    if (
        receipt["checkpoint_sha256"] != sha(experiment / "best.pt")
        or receipt["dataset_sha256"] != sha(data / "dataset.json")
        or receipt["policy_sha256"] != sha(experiment / "frozen-calibration.json")
    ):
        raise ValueError("Frozen photo diagnostic binding differs")
    total = 0
    for split, value in receipt["cohorts"].items():
        gold = [
            (r["source_id"], r["answer"])
            for r in dataset["records"][split]
            if r["role"] == "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
        ]
        for mode in ("single_view", "five_view"):
            rows = value[mode]["records"]
            if [(r["source_id"], r["gold"]) for r in rows] != gold:
                raise ValueError("Photo diagnostic gold/identity changed")
            for row in rows:
                if row["selected"] != selected(row["probabilities"], 0):
                    raise ValueError("Raw photo diagnostic selector changed")
            if statistics(rows) != value[mode]["raw_not_safe_policy"]:
                raise ValueError("Raw photo arithmetic changed")
            frozen = [
                dict(
                    r,
                    selected=selected(
                        r["probabilities"], policy["thresholds"]["object"]
                    ),
                )
                for r in rows
            ]
            if statistics(frozen) != value[mode]["frozen_threshold_diagnostic"]:
                raise ValueError("Frozen-threshold photo arithmetic changed")
        total += len(gold)
    if set(receipt["cohorts"]) != {"train", "dev", "calibration", "final"}:
        raise ValueError("All pre-existing photo cohorts required")
    return {
        "status": "VERIFIED_POST_FREEZE_PHOTO_DIAGNOSTIC_NO_POLICY_CHANGE",
        "photo_sources": total,
        "cohorts": {
            k: {m: v[m]["raw_not_safe_policy"] for m in ("single_view", "five_view")}
            for k, v in receipt["cohorts"].items()
        },
    }


def run(data, experiment, output):
    if output.exists() or not torch.cuda.is_available():
        raise ValueError("Fresh output and CUDA required")
    torch.set_num_threads(2)
    dataset = json.loads((data / "dataset.json").read_text(encoding="utf-8"))
    policy = json.loads((experiment / "frozen-calibration.json").read_text())
    if dataset["pixels_sha256"] != sha(data / "pixels.npz") or policy[
        "checkpoint_sha256"
    ] != sha(experiment / "best.pt"):
        raise ValueError("Frozen pixels/checkpoint changed")
    model = (
        obj.ObjectsModel.from_checkpoint(
            torch.load(experiment / "best.pt", weights_only=True, map_location="cpu")
        )
        .to("cuda")
        .eval()
    )
    archive = np.load(data / "pixels.npz", allow_pickle=False)
    cohorts = {}
    for split in ("train", "dev", "calibration", "final"):
        prepared = ObjectPrepared(archive, split, torch.device("cuda"))
        photo_indices = [
            i
            for i, r in enumerate(dataset["records"][split])
            if r["role"] == "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
        ]
        value = {}
        for mode, consensus in (("single_view", False), ("five_view", True)):
            probs = probabilities(model, prepared, consensus=consensus)
            rows = [
                {
                    "source_id": prepared.ids[i],
                    "gold": dataset["records"][split][i]["answer"],
                    "selected": selected(probs[i], 0),
                    "probabilities": probs[i],
                }
                for i in photo_indices
            ]
            safe = [
                dict(
                    r,
                    selected=selected(
                        r["probabilities"], policy["thresholds"]["object"]
                    ),
                )
                for r in rows
            ]
            value[mode] = {
                "records": rows,
                "raw_not_safe_policy": statistics(rows),
                "frozen_threshold_diagnostic": statistics(safe),
            }
        cohorts[split] = value
        del prepared
    write_json(
        output,
        {
            "status": "POST_FREEZE_DIAGNOSTIC_NOT_SELECTION",
            "cohorts": cohorts,
            "checkpoint_sha256": sha(experiment / "best.pt"),
            "dataset_sha256": sha(data / "dataset.json"),
            "policy_sha256": sha(experiment / "frozen-calibration.json"),
            "script_sha256": sha(Path(__file__)),
            "limits": "Training scores are memorization diagnostics, not generalization. Single-view naming is not the accepted five-view policy. Related photos are not independent. Known final diagnostics never select another winner or relax gates.",
        },
    )
    return audit(data, experiment, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "audit"))
    for name in ("data", "experiment", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            (run if args.mode == "run" else audit)(
                args.data, args.experiment, args.output
            )
        )
    )
