"""Post-selection calibration diagnostics, never further fitting or threshold tuning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from m33_objects_data import sha, write_json
from m33_primary_objects_pilot import ObjectPrepared, probabilities, selected, summary

from ai_brain.training import primary_objects as obj


def diagnose(data, experiment, output):
    if output.exists():
        raise ValueError("Fresh diagnostic receipt required")
    manifest = json.loads((data / "dataset.json").read_text())
    frozen = json.loads((experiment / "frozen-calibration.json").read_text())
    if (
        sha(data / "pixels.npz") != manifest["pixels_sha256"]
        or sha(experiment / "best.pt") != frozen["checkpoint_sha256"]
    ):
        raise ValueError("Frozen evidence changed")
    if not torch.cuda.is_available():
        raise ValueError("CUDA required; no silent fallback")
    torch.set_num_threads(2)
    model = (
        obj.ObjectsModel.from_checkpoint(
            torch.load(experiment / "best.pt", weights_only=True, map_location="cpu")
        )
        .to("cuda")
        .eval()
    )
    archive = np.load(data / "pixels.npz", allow_pickle=False)
    cohort = ObjectPrepared(archive, "calibration", torch.device("cuda"))
    p = probabilities(model, cohort)
    grid = []
    for threshold in (0.99, 0.995, 0.999, 0.9995, 0.9999):
        stats = summary(cohort, p, {"object": threshold})["all"]
        grid.append(
            {
                "threshold": threshold,
                "stats": stats,
                "eligible": stats["accepted"] >= 50 and stats["false_assertions"] == 0,
            }
        )
    result = {
        "schema": 1,
        "status": "POST_SELECTION_DIAGNOSTIC_NO_NEW_TUNING",
        "checkpoint_sha256": sha(experiment / "best.pt"),
        "dataset_sha256": sha(data / "dataset.json"),
        "frozen_policy_sha256": sha(experiment / "frozen-calibration.json"),
        "script_sha256": sha(Path(__file__)),
        "grid": grid,
        "raw_consensus": summary(cohort, p, {"object": 0})["all"],
        "frozen_threshold": frozen["thresholds"]["object"],
        "records": [
            {
                "source_id": identity,
                "task": "object",
                "gold": obj.ANSWER_TEXT[gold],
                "selected": obj.ANSWER_TEXT[prediction],
                "probabilities": values,
            }
            for identity, gold, prediction, values in zip(
                cohort.ids,
                cohort.answers.cpu().tolist(),
                selected(cohort, p, {"object": 0}),
                p,
                strict=True,
            )
        ],
        "limits": "Calibration predictions explain an already frozen rejection. No new weights, policy changes, or selection from final images.",
    }
    write_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "experiment", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.data, args.experiment, args.output)
    print(
        json.dumps({"grid": result["grid"], "raw_consensus": result["raw_consensus"]})
    )
