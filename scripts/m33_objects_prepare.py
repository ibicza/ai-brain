"""Prepare a reviewed, provenance-bound small drawing block; no model training."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from m33_objects_data import CLASSES, raster, sha, write_json
from PIL import Image


def families(pixels: list[np.ndarray]) -> list[int]:
    """Conservative exact/mirrored/coarse-mask duplicate grouping, not artist IDs."""
    masks = np.stack(
        [
            (
                np.asarray(
                    Image.fromarray(p).resize((24, 24), Image.Resampling.BOX)
                ).mean(-1)
                < 225
            ).reshape(-1)
            for p in pixels
        ]
    ).astype(np.float32)
    areas = masks.sum(-1)
    intersection = masks @ masks.T
    union = areas[:, None] + areas[None, :] - intersection
    iou = intersection / np.maximum(union, 1)
    parent = list(range(len(pixels)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    exact = {}
    for index, pixel in enumerate(pixels):
        keys = (
            hashlib.sha256(pixel.tobytes()).hexdigest(),
            hashlib.sha256(pixel[:, ::-1].tobytes()).hexdigest(),
        )
        for key in keys:
            if key in exact:
                parent[find(index)] = find(exact[key])
            else:
                exact[key] = index
    for left, right in zip(*np.where(np.triu(iou >= 0.88, k=1)), strict=True):
        parent[find(int(right))] = find(int(left))
    return [find(i) for i in range(len(pixels))]


def build(
    root: Path, review: Path, crop_inventory: Path, concepts: Path, output: Path
) -> dict:
    if output.exists():
        raise ValueError("Fresh prepared destination required")
    specification = json.loads(review.read_text(encoding="utf-8"))
    acquired = json.loads((root / "acquisition.json").read_text(encoding="utf-8"))
    if (
        specification.get("training_started") is not False
        or set(specification["positive"]) != set(CLASSES)
        or acquired["classes"] != CLASSES
    ):
        raise ValueError("Scope/review mismatch")
    with concepts.open(encoding="utf-8-sig", newline="") as stream:
        concepts_by_name = {
            r["Слово / понятие"]: r["ID понятия"]
            for r in csv.DictReader(stream, delimiter=";")
        }
    if set(CLASSES.values()) - concepts_by_name.keys():
        raise ValueError("Objects not in permanent catalogue")
    pixels, records = [], []
    rejected = []
    for item in acquired["files"]:
        path = root / item["file"]
        if sha(path) != item["sha256"]:
            raise ValueError("Acquired source SHA mismatch")
        category = path.stem
        proposed = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
        decision = specification["positive"].get(category) or specification[
            "negative"
        ].get(category)
        if decision is None:
            raise ValueError("Unreviewed source category")
        accepted = set(decision.get("include", range(len(proposed)))) - set(
            decision.get("exclude", [])
        )
        if not accepted <= set(range(len(proposed))):
            raise ValueError("Invalid review index")
        for index, row in enumerate(proposed):
            if index not in accepted:
                rejected.append(
                    {
                        "category": category,
                        "index": index,
                        "key_id": row["key_id"],
                        "reason": "Explicit visual exclusion; not a new training/UNKNOWN label",
                    }
                )
                continue
            label = CLASSES.get(category, "UNKNOWN")
            pixels.append(raster(row))
            records.append(
                {
                    "source_id": "quickdraw/" + str(row["key_id"]),
                    "source_category": category,
                    "answer": label,
                    "concept_id": concepts_by_name.get(label),
                    "source_file": str(path),
                    "source_file_sha256": item["sha256"],
                    "source_index": index,
                    "licence": "CC BY 4.0",
                    "source_url": item["url"],
                    "role": "VISUALLY_CURATED_NONBLIND_SCHEMATIC_LABEL",
                }
            )
    if len({r["source_id"] for r in records}) != len(records):
        raise ValueError("Repeated source key ID")
    groups = families(pixels)
    grouped = defaultdict(list)
    for index, group in enumerate(groups):
        grouped[group].append(index)
    by_label = defaultdict(list)
    for indices in grouped.values():
        labels = {records[i]["answer"] for i in indices}
        if len(labels) != 1:
            for i in indices:
                rejected.append(
                    {
                        "source_id": records[i]["source_id"],
                        "reason": "Near/exact duplicate family has conflicting positive/UNKNOWN labels",
                    }
                )
            continue
        label = next(iter(labels))
        family_id = hashlib.sha256(
            "|".join(sorted(records[i]["source_id"] for i in indices)).encode()
        ).hexdigest()
        by_label[label].append((family_id, indices))
    rng = np.random.default_rng(20261009)
    prepared = {
        name: []
        for name in ("train", "dev", "calibration", "final", "textbook_diagnostic")
    }
    split_pixels = {name: [] for name in prepared}
    for label, items in sorted(by_label.items()):
        if label != "UNKNOWN" and len(items) < 20:
            raise ValueError("Insufficient independent families for " + label)
        items.sort()
        rng.shuffle(items)
        train_end = int(len(items) * 0.60)
        dev_end = int(len(items) * 0.70)
        cal_end = int(len(items) * 0.85)
        for offset, (family_id, indices) in enumerate(items):
            split = (
                "train"
                if offset < train_end
                else "dev"
                if offset < dev_end
                else "calibration"
                if offset < cal_end
                else "final"
            )
            for i in indices:
                record = records[i] | {
                    "family_id": family_id,
                    "split": split,
                    "pixel_sha256": hashlib.sha256(pixels[i].tobytes()).hexdigest(),
                }
                prepared[split].append(record)
                split_pixels[split].append(pixels[i])
    # Constant absence control is deliberately shared, never independent evidence.
    for split in ("train", "dev", "calibration", "final"):
        prepared[split].append(
            {
                "source_id": "constant/missing",
                "family_id": "constant/missing",
                "split": split,
                "answer": "UNKNOWN",
                "concept_id": None,
                "role": "SHARED_CONSTANT_CONTROL",
            }
        )
        split_pixels[split].append(np.zeros((96, 96, 3), dtype=np.uint8))
    inventory = json.loads(crop_inventory.read_text(encoding="utf-8"))
    for reviewed in specification["textbook_diagnostics"]:
        item = inventory[reviewed["inventory_index"]]
        path = Path(item["path"])
        if sha(path) != item["sha256"]:
            raise ValueError("Textbook crop changed")
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((88, 88), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (96, 96), "white")
            canvas.paste(image, ((96 - image.width) // 2, (96 - image.height) // 2))
            pixel = np.asarray(canvas)
        label = reviewed["answer"]
        media = item["media"][0]
        prepared["textbook_diagnostic"].append(
            {
                "source_id": "textbook/" + item["sha256"],
                "family_id": media["Группа родственных изображений"],
                "split": "textbook_diagnostic",
                "answer": label,
                "concept_id": concepts_by_name.get(label),
                "source_file": str(path),
                "source_file_sha256": item["sha256"],
                "media_id": media["ID медиа"],
                "licence": media["Права / лицензия"],
                "source_context": media["Источник / страница / область"],
                "note": reviewed["note"],
                "role": "INSPECTED_NONBLIND_DIAGNOSTIC_ONLY_NOT_TUNING",
                "pixel_sha256": hashlib.sha256(pixel.tobytes()).hexdigest(),
            }
        )
        split_pixels["textbook_diagnostic"].append(pixel)
    owners = {}
    for split, rows in prepared.items():
        for row in rows:
            if row["role"] == "SHARED_CONSTANT_CONTROL":
                continue
            for identity in (row["source_id"], row["family_id"], row["pixel_sha256"]):
                if owners.setdefault(identity, split) != split:
                    raise ValueError("Source/family/pixel leakage")
    output.mkdir(parents=True)
    payload = {}
    for split, rows in prepared.items():
        payload[split + "_pixels"] = np.stack(split_pixels[split])
        payload[split + "_answers"] = np.array([row["answer"] for row in rows])
        payload[split + "_ids"] = np.array([row["source_id"] for row in rows])
    np.savez_compressed(output / "pixels.npz", **payload)
    report = {
        "schema": 1,
        "classes": CLASSES,
        "concept_ids": {word: concepts_by_name[word] for word in CLASSES.values()},
        "acquisition_sha256": sha(root / "acquisition.json"),
        "review_sha256": sha(review),
        "licence_snapshot_sha256": sha(root / "LICENSE.quickdraw"),
        "crop_inventory_sha256": sha(crop_inventory),
        "concepts_export_sha256": sha(concepts),
        "pixels_sha256": sha(output / "pixels.npz"),
        "records": prepared,
        "excluded": rejected,
        "counts": {
            split: {
                "examples": len(rows),
                "labels": dict(Counter(r["answer"] for r in rows)),
                "families": len({r["family_id"] for r in rows}),
            }
            for split, rows in prepared.items()
        },
        "training_started": False,
        "limits": "Schematic non-blind curated drawings, not photos/general knowledge. Family grouping: source IDs, exact/mirrored pixels, coarse mask IoU>=.88 connected components. No participant IDs or exhaustive semantic duplicate guarantee. Seven already inspected textbook diagnostics never select weights, thresholds or hyperparameters. Shared absence control is not independent evidence.",
    }
    write_json(output / "dataset.json", report)
    print(
        json.dumps(
            {
                "counts": report["counts"],
                "excluded": len(rejected),
                "pixels_sha256": report["pixels_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "review", "crop-inventory", "concepts", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.review, args.crop_inventory, args.concepts, args.output)
