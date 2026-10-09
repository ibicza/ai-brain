"""Past frozen policies on the SAME new final pixels; no calibration retuning."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import torch
from m33_composition_verify import decisions, measure, read, replay, sha

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_objects as old


def score(records, predicted):
    if not records or len(records) % 6 or len(records) != len(predicted):
        raise ValueError("Complete two-target observation records required")
    gold = [r["answer"] for r in records]
    tasks = {}
    for task in c.VALUES:
        indices = [i for i, row in enumerate(records) if row["task"] == task]
        tasks[task] = measure(
            [gold[i] for i in indices], [predicted[i] for i in indices]
        )
    complete = [
        predicted[i : i + 3] == gold[i : i + 3]
        for i in range(0, len(gold), 3)
        if c.UNKNOWN not in gold[i : i + 3]
    ]
    return {
        "overall": measure(gold, predicted),
        "tasks": tasks,
        "complete_visible_descriptions": {
            "eligible_objects": len(complete),
            "all_three_correct_rate": sum(complete) / len(complete)
            if complete
            else None,
        },
    }


def compare(root, baselines, output, device):
    if output.exists():
        raise ValueError("Fresh comparison required")
    freeze = read(root / "candidate-freeze.json")
    if (
        sha(root / "dataset.npz") != freeze["dataset_sha256"]
        or sha(root / "dataset-records.json.gz") != freeze["records_sha256"]
    ):
        raise ValueError("New final data changed")
    with np.load(root / "dataset.npz", allow_pickle=False) as stored_arrays:
        arrays = {key: stored_arrays[key] for key in stored_arrays.files}
    with gzip.open(root / "dataset-records.json.gz", "rt", encoding="utf-8") as stream:
        records = json.load(stream)
    torch.set_num_threads(2)
    comparisons = []
    for baseline in baselines:
        baseline_root = baseline / "experiment"
        baseline_freeze = read(baseline_root / "candidate-freeze.json")
        baseline_policy = read(baseline_root / "policy-frozen.json")
        baseline_result = read(baseline_root / "result.json")
        if {
            task: value["threshold"] for task, value in baseline_policy["tasks"].items()
        } != baseline_result["thresholds"]:
            raise ValueError("Past frozen policy differs from its original report")
        checkpoint_path = (
            baseline_root / baseline_freeze["winner"]["schedule"] / "best.pt"
        )
        if sha(checkpoint_path) != baseline_freeze["winner"]["checkpoint_sha256"]:
            raise ValueError("Past frozen checkpoint changed")
        checkpoint = torch.load(checkpoint_path, weights_only=True, map_location="cpu")
        if (
            tuple(checkpoint["answers"]) != c.ANSWERS
            or checkpoint["new_words"] != c.NEW_WORDS
        ):
            raise ValueError("Baseline answer/token vocabulary differs")
        if checkpoint["previous_sha256"] != sha(baseline / "previous.pt"):
            raise ValueError("Baseline inherited checkpoint changed")
        prior = torch.load(
            baseline / "previous.pt", weights_only=True, map_location="cpu"
        )
        options = {"attribute_attention": checkpoint["attribute_attention"]}
        if checkpoint.get("spatial_readout", False):
            options["spatial_readout"] = True
        if checkpoint.get("shape_edges", False):
            options["shape_edges"] = True
        model = (
            c.CompositionModel(
                old.ObjectsModel.from_checkpoint(prior),
                **options,
            )
            .to(device)
            .eval()
        )
        model.load_candidate(checkpoint["candidate"])
        thresholds = {
            task: value["threshold"] for task, value in baseline_policy["tasks"].items()
        }
        reports = {}
        for split in ("final", "combinations", "transfer"):
            p = replay(model, arrays, split, device)
            rows = records[split]["records"]
            raw, safe = p.argmax(1).tolist(), decisions(p, rows, thresholds)
            reports[split] = {
                "raw_argmax": score(rows, raw),
                "selected": score(rows, safe),
            }
        comparisons.append(
            {
                "baseline": baseline.name,
                "checkpoint_sha256": sha(checkpoint_path),
                "policy_sha256": sha(baseline_root / "policy-frozen.json"),
                "thresholds": thresholds,
                "reports": reports,
            }
        )
    current = read(root / "result.json")
    result = {
        "schema": 1,
        "status": "SAME_PIXEL_FROZEN_POLICY_COMPARISON",
        "dataset_sha256": freeze["dataset_sha256"],
        "candidate_checkpoint_sha256": current["checkpoint_sha256"],
        "current": {
            split: current["reports"][split]
            for split in ("final", "combinations", "transfer")
        },
        "baselines": comparisons,
        "calibration_retuned": False,
        "production_admitted": False,
        "limits": "Same new procedural pixels, past frozen policies. Current data/capacity changes are combined, so this is not an ablation proving an individual cause.",
    }
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "baselines": len(baselines)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    compare(
        args.root.resolve(),
        [p.resolve() for p in args.baseline],
        args.output.resolve(),
        args.device,
    )
