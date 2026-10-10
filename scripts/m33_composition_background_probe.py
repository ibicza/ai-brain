"""Known-dev paired background intervention, never a new blind final test."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from m33_composition_verify import decisions, equal, measure, read, replay, sha
from m33_primary_composition_pilot import Prepared, evaluate, probabilities, write
from PIL import Image

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_objects as old


def run(reference, output, capsule, count, device):
    if output.exists() or type(count) is not int or not 12 <= count <= 600:
        raise ValueError("Fresh bounded development probe required")
    freeze = read(reference / "experiment/candidate-freeze.json")
    protocol = read(reference / "experiment/protocol.json")
    policy = read(reference / "experiment/policy-frozen.json")
    source_result = read(reference / "experiment/result.json")
    checkpoint_path = (
        reference / "experiment" / freeze["winner"]["schedule"] / "best.pt"
    )
    source_hashes = {
        str(path): sha(path)
        for path in (
            checkpoint_path,
            reference / "previous.pt",
            reference / "experiment/dataset.npz",
            reference / "experiment/dataset-records.json.gz",
            reference / "experiment/policy-frozen.json",
            reference / "experiment/protocol.json",
        )
    }
    if (
        sha(checkpoint_path) != source_result["checkpoint_sha256"]
        or sha(reference / "previous.pt")
        != source_result["inherited_checkpoint_sha256"]
    ):
        raise ValueError("Frozen reference changed")
    thresholds = {task: entry["threshold"] for task, entry in policy["tasks"].items()}
    if thresholds != source_result["thresholds"]:
        raise ValueError("Frozen policy changed")
    with np.load(reference / "experiment/dataset.npz", allow_pickle=False) as archive:
        data = {
            k: archive["dev_" + k][: count if k == "pixels" else count * 6]
            for k in ("pixels", "questions", "labels", "image_index")
        }
    with gzip.open(
        reference / "experiment/dataset-records.json.gz", "rt", encoding="utf-8"
    ) as stream:
        original_records = json.load(stream)["dev"]
    data["records"], data["scenes"] = (
        original_records["records"][: count * 6],
        original_records["scenes"][:count],
    )
    if len(data["pixels"]) != count:
        raise ValueError("Insufficient existing development scenes")
    scenes = [
        c.Scene(
            row["identity"],
            row["seed"],
            tuple(c.Item(**item) for item in row["items"]),
            row["style"],
        )
        for row in data["scenes"]
    ]
    for i, scene in enumerate(scenes):
        if not np.array_equal(c.render(scene), data["pixels"][i]):
            raise ValueError(
                "Reference cannot be rerendered exactly; no causal attribution"
            )
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    prior = torch.load(reference / "previous.pt", map_location="cpu", weights_only=True)
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
        output / "frozen-reference.json",
        {
            "schema": 1,
            "reference_hashes": source_hashes,
            "capsule_sha256": sha(capsule),
            "backgrounds": {"dark": [45, 45, 45], "light": [225, 225, 225]},
            "count": count,
            "split": "known_dev_only",
            "training_or_calibration": False,
            "production_admitted": False,
            "limits": "Only the base background changes. Foreground geometry/color/pattern and RNG draws are fixed; antialias boundary RGB changes with background. Faint contrast may affect visibility. Not a blind exam or proof of photographic transfer.",
        },
    )
    groups = {"original": data}
    for name, rgb in (("dark", (45, 45, 45)), ("light", (225, 225, 225))):
        pixels = np.stack(
            [c.render_diverse(scene, background_override=rgb) for scene in scenes]
        )
        records = [dict(row) for row in data["records"]]
        for i, row in enumerate(records):
            row["original_image_sha256"] = row["image_sha256"]
            row["image_sha256"] = hashlib.sha256(pixels[i // 6].tobytes()).hexdigest()
        groups[name] = {**data, "pixels": pixels, "records": records}
    np.savez_compressed(
        output / "paired-inputs.npz",
        **{
            name + "_" + key: group[key]
            for name, group in groups.items()
            for key in ("pixels", "questions", "labels", "image_index")
        },
    )
    with gzip.open(output / "paired-records.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(
            {
                name: {k: group[k] for k in ("records", "scenes")}
                for name, group in groups.items()
            },
            stream,
            ensure_ascii=False,
        )
    sheet = Image.new("RGB", (96 * 8, 96 * 3))
    for row, group in enumerate(groups.values()):
        for col, pixels in enumerate(group["pixels"][:8]):
            sheet.paste(Image.fromarray(pixels), (col * 96, row * 96))
    sheet.save(output / "paired-backgrounds.png")
    reports, original_predictions = {}, None
    for name, group in groups.items():
        prepared = Prepared(group, device)
        p = probabilities(model, prepared)
        evaluated = evaluate(prepared, p, thresholds)
        arrays = {
            "probe_" + k: group[k]
            for k in ("pixels", "questions", "labels", "image_index")
        }
        reproduced = replay(
            model,
            arrays,
            "probe",
            device,
            reflection_consensus=model.reflection_consensus,
        )
        selected = decisions(reproduced, group["records"], thresholds)
        if (
            not np.allclose(reproduced, p, atol=2e-6, rtol=2e-5)
            or selected != evaluated["predictions"]
        ):
            raise ValueError("Paired background replay differs")
        equal(measure(group["labels"].tolist(), selected), evaluated["overall"])
        if name == "original":
            original_predictions = selected
        reports[name] = {
            "selected": {k: val for k, val in evaluated.items() if k != "predictions"},
            "decisions_changed_from_original": sum(
                a != b for a, b in zip(selected, original_predictions, strict=True)
            ),
            "first_accepted_errors": [
                {
                    "scene_id": r["scene_id"],
                    "task": r["task"],
                    "side": r["side"],
                    "gold": c.ANSWERS[r["answer"]],
                    "predicted": c.ANSWERS[selected[i]],
                    "score": float(p[i].max()),
                }
                for i, r in enumerate(group["records"])
                if selected[i] != c.UNKNOWN and selected[i] != r["answer"]
            ][:20],
        }
        with gzip.open(
            output / (name + "-predictions.json.gz"), "wt", encoding="utf-8"
        ) as stream:
            json.dump({"probabilities": p.tolist(), "selected": selected}, stream)
    if any(sha(Path(path)) != digest for path, digest in source_hashes.items()):
        raise ValueError("Reference changed during background probe")
    report = {
        "schema": 1,
        "status": "KNOWN_DEV_PAIRED_BACKGROUND_PROBE_REPLAYED",
        "reports": reports,
        "independent_inference_and_arithmetic_replayed": True,
        "production_admitted": False,
        "input_sha256": sha(output / "paired-inputs.npz"),
        "frozen_reference_sha256": sha(output / "frozen-reference.json"),
        "limits": "Known development intervention, not independent sources or new blind final. Do not use it to retune the original frozen policy.",
    }
    write(output / "result.json", report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "errors": {
                    name: val["selected"]["overall"]["false_assertions"]
                    for name, val in reports.items()
                },
            }
        ),
        flush=True,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "output", "capsule"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    run(
        args.reference.resolve(),
        args.output.resolve(),
        args.capsule.resolve(),
        args.count,
        args.device,
    )
