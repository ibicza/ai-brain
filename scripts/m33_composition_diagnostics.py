"""Known development-data diagnostics; not a fresh blind evaluation."""

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

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


def exposed_errors(root, split, output, preview):
    """Inspect saved final errors without rerendering, fitting, or changing policy."""
    if split not in ("final", "transfer", "combinations", "control_final"):
        raise ValueError("Explicit previously evaluated split required")
    if output.exists() or preview.exists():
        raise ValueError("Fresh exposed diagnostic paths required")
    prediction_file = root / (split + "-predictions.json.gz")
    record_file = root / "dataset-records.json.gz"
    dataset_file = root / "dataset.npz"
    with gzip.open(prediction_file, "rt", encoding="utf-8") as stream:
        data = json.load(stream)
    with gzip.open(record_file, "rt", encoding="utf-8") as stream:
        saved = json.load(stream)[split]
    if data["records"] != saved["records"]:
        raise ValueError("Prediction and dataset records differ")
    records = data["records"]
    with np.load(dataset_file, allow_pickle=False) as arrays:
        pixels = arrays[split + "_pixels"]
        indices = arrays[split + "_image_index"]
        labels = arrays[split + "_labels"]
    if (
        pixels.dtype != np.uint8
        or pixels.ndim != 4
        or pixels.shape[1:] != (96, 96, 3)
        or len(indices) != len(records)
        or len(labels) != len(records)
        or len(data["selected"]) != len(records)
        or len(data["probabilities"]) != len(records)
    ):
        raise ValueError("Invalid saved diagnostic alignment")
    errors = []
    for i, row in enumerate(records):
        index = int(indices[i])
        if index < 0 or index >= len(pixels):
            raise ValueError("Saved image index out of range")
        digest = hashlib.sha256(pixels[index].tobytes()).hexdigest()
        if digest != row["image_sha256"] or int(labels[i]) != row["answer"]:
            raise ValueError("Saved pixel or gold hash mismatch")
        prediction = data["selected"][i]
        if prediction != course.UNKNOWN and prediction != row["answer"]:
            errors.append(
                {
                    "record_index": i,
                    "image_index": index,
                    "image_sha256": digest,
                    "scene_id": row["scene_id"],
                    "question": row["question"],
                    "task": row["task"],
                    "side": row["side"],
                    "gold": course.ANSWERS[row["answer"]],
                    "predicted": course.ANSWERS[prediction],
                    "score": float(max(data["probabilities"][i])),
                }
            )
    # These are exact stored 96px model inputs, not illustrative regeneration.
    shown = errors[:48]
    canvas = Image.new("RGB", (96 * 8, 120 * max(1, (len(shown) + 7) // 8)), "white")
    pen = ImageDraw.Draw(canvas)
    for j, row in enumerate(shown):
        x, y = j % 8 * 96, j // 8 * 120
        canvas.paste(Image.fromarray(pixels[row["image_index"]]), (x, y))
        pen.text((x + 2, y + 98), str(row["record_index"]), fill="black")
    canvas.save(preview)
    hashes = {}
    for path in (prediction_file, record_file, dataset_file, preview):
        with path.open("rb") as stream:
            hashes[path.name] = hashlib.file_digest(stream, "sha256").hexdigest()
    result = {
        "schema": 1,
        "split": split,
        "status": "EXPOSED_FINAL_ERRORS_NOT_FRESH_TEST",
        "production_admitted": False,
        "false_assertions": len(errors),
        "errors": errors,
        "preview_records": [row["record_index"] for row in shown],
        "sha256": hashes,
        "limits": "Previously evaluated errors only. No fitting, policy changes, fresh-test claim, or calibrated probability claim.",
    }
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--edge-preview", type=Path)
    parser.add_argument(
        "--exposed-split",
        choices=("final", "transfer", "combinations", "control_final"),
    )
    parser.add_argument("--error-preview", type=Path)
    args = parser.parse_args()
    if args.exposed_split is not None:
        if args.error_preview is None:
            parser.error("--error-preview required for exposed diagnostics")
        result = exposed_errors(
            args.root.resolve(),
            args.exposed_split,
            args.output.resolve(),
            args.error_preview.resolve(),
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "false_assertions": result["false_assertions"],
                }
            )
        )
        raise SystemExit(0)
    if args.error_preview is not None:
        parser.error("--error-preview requires --exposed-split")
    diagnose(args.root.resolve(), args.output.resolve())
    if args.edge_preview is not None:
        edge_preview(args.root.resolve(), args.edge_preview.resolve())
