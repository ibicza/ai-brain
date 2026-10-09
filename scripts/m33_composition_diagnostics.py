"""Known development-data diagnostics; not a fresh blind evaluation."""

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from ai_brain.training import primary_composition as course


def diagnose(root, output):
    if output.exists():
        raise ValueError("Fresh diagnostic receipt required")
    prediction_file = root / "dev-predictions.json.gz"
    with gzip.open(prediction_file, "rt", encoding="utf-8") as stream:
        data = json.load(stream)
    with gzip.open(root / "dataset-records.json.gz", "rt", encoding="utf-8") as stream:
        scenes = json.load(stream)["dev"]["scenes"]
    report = {}
    for task in course.VALUES:
        confusion = Counter()
        groups = defaultdict(lambda: [0, 0])
        errors = []
        for i, row in enumerate(data["records"]):
            if row["task"] != task:
                continue
            gold, predicted = row["answer"], data["raw_predictions"][i]
            confusion[(course.ANSWERS[gold], course.ANSWERS[predicted])] += 1
            scene = scenes[i // 6]
            key = (
                scene["style"]
                + "/"
                + ("English" if row["question"].startswith("What") else "Russian")
                + "/"
                + str(row["side"])
            )
            groups[key][0] += 1
            groups[key][1] += gold == predicted
            if gold != predicted and len(errors) < 12:
                errors.append(
                    {
                        "scene_id": row["scene_id"],
                        "question": row["question"],
                        "gold": course.ANSWERS[gold],
                        "predicted": course.ANSWERS[predicted],
                        "confidence": float(np.max(data["probabilities"][i])),
                        "style": scene["style"],
                    }
                )
        report[task] = {
            "confusion": [
                {"gold": g, "predicted": p, "count": n}
                for (g, p), n in sorted(confusion.items())
            ],
            "groups": {
                k: {"examples": v[0], "raw_accuracy": v[1] / v[0]}
                for k, v in groups.items()
            },
            "first_known_errors": errors,
        }
    with prediction_file.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    result = {
        "schema": 1,
        "split": "dev",
        "prediction_sha256": digest,
        "production_admitted": False,
        "tasks": report,
        "limits": "Known development errors, not blind testing or ground-truth-assisted inference.",
    }
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps({"status": "DEVELOPMENT_DIAGNOSTICS_SAVED", "output": str(output)})
    )


def edge_preview(root, output):
    if output.exists():
        raise ValueError("Fresh effective-input preview required")
    with np.load(root / "dataset.npz", allow_pickle=False) as arrays:
        pixels = arrays["train_pixels"][:32]
    images = torch.from_numpy(pixels).permute(0, 3, 1, 2).float() / 255
    transformed = (
        (course.shape_edge_pixels(images).permute(0, 2, 3, 1).numpy() * 255)
        .round()
        .astype(np.uint8)
    )
    canvas = Image.new("RGB", (96 * 8, 96 * 4))
    for i, pixel in enumerate(transformed):
        canvas.paste(Image.fromarray(pixel), (i % 8 * 96, i // 8 * 96))
    canvas.save(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--edge-preview", type=Path)
    args = parser.parse_args()
    diagnose(args.root.resolve(), args.output.resolve())
    if args.edge_preview is not None:
        edge_preview(args.root.resolve(), args.edge_preview.resolve())
