"""Fresh fixed-policy authored/OOD control screen; never trains or calibrates."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import torch
from m33_composition_verify import decisions, equal, measure, read, replay, sha
from m33_primary_composition_pilot import Prepared, evaluate, probabilities, write
from PIL import Image

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_composition_controls as controls
from ai_brain.training import primary_objects as old


def run(reference, output, count, seed, device, capsule):
    if (
        output.exists()
        or type(count) is not int
        or not 12 <= count <= 6000
        or type(seed) is not int
        or seed < 0
    ):
        raise ValueError("Fresh bounded control screen required")
    protocol = read(reference / "experiment/protocol.json")
    freeze = read(reference / "experiment/candidate-freeze.json")
    result = read(reference / "experiment/result.json")
    policy_path = reference / "experiment/policy-frozen.json"
    policy = read(policy_path)
    checkpoint_path = (
        reference / "experiment" / freeze["winner"]["schedule"] / "best.pt"
    )
    previous_path = reference / "previous.pt"
    hashes = {
        str(p): sha(p)
        for p in (
            checkpoint_path,
            previous_path,
            policy_path,
            reference / "experiment/protocol.json",
        )
    }
    if (
        sha(checkpoint_path) != result["checkpoint_sha256"]
        or sha(previous_path) != result["inherited_checkpoint_sha256"]
    ):
        raise ValueError("Reference frozen weights changed")
    thresholds = {task: entry["threshold"] for task, entry in policy["tasks"].items()}
    if thresholds != result["thresholds"]:
        raise ValueError("Reference frozen policy changed")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    prior = torch.load(previous_path, map_location="cpu", weights_only=True)
    if (
        checkpoint["previous_sha256"] != sha(previous_path)
        or tuple(checkpoint["answers"]) != c.ANSWERS
    ):
        raise ValueError("Control vocabulary/inheritance differs")
    torch.set_num_threads(2)
    model = (
        c.CompositionModel(
            old.ObjectsModel.from_checkpoint(prior),
            spatial_readout=checkpoint.get("spatial_readout", False),
            shape_edges=checkpoint.get("shape_edges", False),
        )
        .to(device)
        .eval()
    )
    model.load_candidate(checkpoint["candidate"])
    model.reflection_consensus = protocol.get("reflection_consensus", False)
    output.mkdir(parents=True)
    write(
        output / "preregistered-freeze.json",
        {
            "schema": 1,
            "reference_hashes": hashes,
            "source_capsule_sha256": sha(capsule),
            "count": count,
            "seed": seed,
            "thresholds": thresholds,
            "reflection_consensus": model.reflection_consensus,
            "training_or_calibration": False,
            "production_admitted": False,
            "unknown_shape_families": controls.HELD_OUT_SHAPES,
            "limits": "Separate authored synthetic generator sharing Pillow, not independent photographic or semantic annotation. Unknown means unsupported by this four-shape readout, not absent from all legacy knowledge.",
        },
    )
    rows = controls.scenes("held_control", count, seed)
    # Enforce fresh seeds against every cohort of the reference, before inference.
    with gzip.open(
        reference / "experiment/dataset-records.json.gz", "rt", encoding="utf-8"
    ) as f:
        original = json.load(f)
    old_seeds = {r["seed"] for group in original.values() for r in group["scenes"]}
    if old_seeds & {r.seed for r in rows}:
        raise ValueError("Control scenes reuse reference seeds")
    data = controls.prepare(rows)
    arrays = {
        "controls_" + key: data[key]
        for key in ("pixels", "questions", "labels", "image_index")
    }
    np.savez_compressed(output / "dataset.npz", **arrays)
    with gzip.open(output / "records.json.gz", "wt", encoding="utf-8") as f:
        json.dump({k: data[k] for k in ("records", "scenes")}, f, ensure_ascii=False)
    sheet = Image.new("RGB", (8 * 96, 4 * 96))
    for i, pixels in enumerate(data["pixels"][:32]):
        sheet.paste(Image.fromarray(pixels), (i % 8 * 96, i // 8 * 96))
    sheet.save(output / "actual-control-inputs.png")
    prepared = Prepared(data, device)
    p = probabilities(model, prepared)
    single_p = probabilities(model, prepared, single_view=True)
    evaluated = evaluate(prepared, p, thresholds)
    raw = evaluate(prepared, single_p, {task: 0 for task in c.VALUES})
    # Arithmetic and the reflection inference are independently implemented.
    rerun = replay(
        model,
        arrays,
        "controls",
        device,
        reflection_consensus=model.reflection_consensus,
    )
    choices = decisions(rerun, data["records"], thresholds)
    if (
        not np.allclose(p, rerun, atol=2e-6, rtol=2e-5)
        or choices != evaluated["predictions"]
    ):
        raise ValueError("Independent control inference differs")
    equal(measure(data["labels"].tolist(), choices), evaluated["overall"])
    for task in c.VALUES:
        idx = [i for i, record in enumerate(data["records"]) if record["task"] == task]
        equal(
            measure([int(data["labels"][i]) for i in idx], [choices[i] for i in idx]),
            evaluated["tasks"][task],
        )
    if any(sha(Path(path)) != digest for path, digest in hashes.items()):
        raise ValueError("Reference changed during control screen")
    with gzip.open(output / "predictions.json.gz", "wt", encoding="utf-8") as f:
        json.dump(
            {
                "probabilities": p.tolist(),
                "selected": choices,
                "single_view_probabilities": single_p.tolist(),
                "single_view_raw_predictions": raw["predictions"],
            },
            f,
        )
    passed = all(
        m["false_assertions"] == 0
        and m["answerable_recall"] >= 0.8
        and m["unknown_recall"] >= 0.9
        for m in evaluated["tasks"].values()
    )
    report = {
        "schema": 1,
        "status": "BOUNDED_CONTROL_SCREEN_PASSED"
        if passed
        else "CONTROL_FAILURE_NOT_PRODUCTION",
        "selected": {k: val for k, val in evaluated.items() if k != "predictions"},
        "single_view_raw_argmax": {
            k: val for k, val in raw.items() if k != "predictions"
        },
        "independent_inference_and_arithmetic_replayed": True,
        "dataset_sha256": sha(output / "dataset.npz"),
        "records_sha256": sha(output / "records.json.gz"),
        "preregistered_freeze_sha256": sha(output / "preregistered-freeze.json"),
        "production_admitted": False,
        "scope": "Authored graphics and unsupported contours; not all future OODs, photographs or textbook acceptance.",
    }
    write(output / "result.json", report)
    print(
        json.dumps(
            {"status": report["status"], "overall": report["selected"]["overall"]}
        ),
        flush=True,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "output", "capsule"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--count", type=int, default=600)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    run(
        args.reference.resolve(),
        args.output.resolve(),
        args.count,
        args.seed,
        args.device,
        args.capsule.resolve(),
    )
