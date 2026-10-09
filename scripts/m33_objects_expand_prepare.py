"""Expand reviewed object data without promoting old held-out images into training."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from m33_objects_data import CLASSES, raster, sha, write_json
from m33_objects_prepare import families
from PIL import Image

SPLITS = ("train", "dev", "calibration", "final", "regression", "textbook_diagnostic")


def bound_json(path):
    blob = path.read_bytes()
    return json.loads(blob), hashlib.sha256(blob).hexdigest()


def assign_groups(records, groups, seed=20261010):
    """Existing split owners are immutable; mixed-owner/label bridges quarantined."""
    grouped = defaultdict(list)
    for index, group in enumerate(groups):
        grouped[group].append(index)
    admitted, excluded, fresh = [], [], defaultdict(list)
    for indices in grouped.values():
        labels = {records[i]["answer"] for i in indices}
        owners = {records[i]["split"] for i in indices if records[i].get("parent")}
        owners.update(
            records[i]["declared_split"]
            for i in indices
            if records[i].get("declared_split") and not records[i].get("parent")
        )
        if len(labels) != 1 or len(owners) > 1:
            excluded.extend(
                {
                    "source_id": records[i]["source_id"],
                    "reason": "Conflicting label or prior-partition bridge; whole family quarantined",
                }
                for i in indices
            )
            continue
        identity = hashlib.sha256(
            "|".join(sorted(records[i]["source_id"] for i in indices)).encode()
        ).hexdigest()
        if owners:
            admitted.extend((i, next(iter(owners)), identity) for i in indices)
        else:
            fresh[next(iter(labels))].append((identity, indices))
    rng = np.random.default_rng(seed)
    fresh_counts = {}
    for label, items in sorted(fresh.items()):
        items.sort()
        rng.shuffle(items)
        fresh_counts[label] = len(items)
        boundaries = (
            int(len(items) * 0.6),
            int(len(items) * 0.7),
            int(len(items) * 0.85),
        )
        for n, (identity, indices) in enumerate(items):
            split = (
                "train"
                if n < boundaries[0]
                else "dev"
                if n < boundaries[1]
                else "calibration"
                if n < boundaries[2]
                else "final"
            )
            admitted.extend((i, split, identity) for i in indices)
    return admitted, excluded, fresh_counts


def declared_groups(records, groups):
    """Union pixel families with explicit related artwork families."""
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, record in enumerate(records):
        keys = [("pixel", groups[i])]
        if record.get("declared_family"):
            keys.append(("declared", record["declared_family"]))
        for key in keys:
            if key in seen:
                parent[find(i)] = find(seen[key])
            else:
                seen[key] = i
    return [find(i) for i in range(len(records))]


def build(
    parent: Path,
    root: Path,
    review: Path,
    output: Path,
    illustrations: Path | None = None,
):
    if output.exists():
        raise ValueError("Fresh prepared destination required")
    parent_path = parent / "dataset.json"
    parent_manifest, parent_sha = bound_json(parent_path)
    if (
        parent_manifest["classes"] != CLASSES
        or sha(parent / "pixels.npz") != parent_manifest["pixels_sha256"]
    ):
        raise ValueError("Parent scope/hash mismatch")
    acquired, acquisition_sha = bound_json(root / "acquisition.json")
    specification, review_sha = bound_json(review)
    protected_inputs = {
        parent_path: parent_sha,
        parent / "pixels.npz": parent_manifest["pixels_sha256"],
        root / "acquisition.json": acquisition_sha,
        review: review_sha,
        root / "LICENSE.quickdraw": sha(root / "LICENSE.quickdraw"),
    }
    if (
        acquired["classes"] != CLASSES
        or acquired["excluded_acquisition_sha256"]
        != parent_manifest["acquisition_sha256"]
        or specification["training_started"] is not False
    ):
        raise ValueError("Fresh acquisition/review lineage mismatch")
    if set(specification["positive"]) != set(CLASSES):
        raise ValueError("Review scope mismatch")
    if set(specification["negative"]) != set(acquired["negative_categories"]):
        raise ValueError("Negative review scope mismatch")
    records, pixels, rejected = [], [], []
    archive = np.load(parent / "pixels.npz", allow_pickle=False)
    for split, rows in parent_manifest["records"].items():
        split_pixels = archive[split + "_pixels"]
        if archive[split + "_ids"].tolist() != [
            r["source_id"] for r in rows
        ] or archive[split + "_answers"].tolist() != [r["answer"] for r in rows]:
            raise ValueError("Parent arrays/records mismatch")
        for n, row in enumerate(rows):
            pixel = split_pixels[n]
            if row["role"] == "SHARED_CONSTANT_CONTROL":
                if pixel.any() or row["answer"] != "UNKNOWN":
                    raise ValueError("Invalid parent absence control")
                continue
            if hashlib.sha256(pixel.tobytes()).hexdigest() != row["pixel_sha256"]:
                raise ValueError("Parent pixel changed")
            records.append(
                row
                | {
                    "parent": True,
                    "origin_split": split,
                    "origin_family_id": row["family_id"],
                    "origin_dataset_sha256": parent_sha,
                    "split": "regression" if split == "final" else split,
                }
            )
            pixels.append(pixel)
    for item in acquired["files"]:
        path = root / item["file"]
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != item["sha256"]:
            raise ValueError("New source changed")
        protected_inputs[path] = item["sha256"]
        category = path.stem
        proposed = [json.loads(line) for line in blob.decode("utf-8").splitlines()]
        if [str(r["key_id"]) for r in proposed] != item["selected_ids"]:
            raise ValueError("Acquisition IDs not aligned with source bytes")
        decision = specification["positive"].get(category) or specification[
            "negative"
        ].get(category)
        if decision is None or ("include" in decision) == ("exclude" in decision):
            raise ValueError("Explicit visual decision required for every category")
        values = decision.get("include", decision.get("exclude"))
        if len(set(values)) != len(values) or not set(values) <= set(
            range(len(proposed))
        ):
            raise ValueError("Review index invalid")
        accepted = (
            set(values)
            if "include" in decision
            else set(range(len(proposed))) - set(values)
        )
        for n, row in enumerate(proposed):
            identity = "quickdraw/" + str(row["key_id"])
            if n not in accepted:
                rejected.append(
                    {
                        "source_id": identity,
                        "source_category": category,
                        "source_index": n,
                        "reason": "Visual exclusion; not relabelled UNKNOWN",
                    }
                )
                continue
            label = CLASSES.get(category, "UNKNOWN")
            records.append(
                {
                    "source_id": identity,
                    "source_category": category,
                    "source_index": n,
                    "source_file": str(path),
                    "source_file_sha256": item["sha256"],
                    "source_url": item["url"],
                    "licence": "CC BY 4.0",
                    "answer": label,
                    "concept_id": parent_manifest["concept_ids"].get(label),
                    "role": "VISUALLY_CURATED_NONBLIND_SCHEMATIC_LABEL",
                    "parent": False,
                }
            )
            pixels.append(raster(row))
    if len({r["source_id"] for r in records}) != len(records):
        raise ValueError("Source ID overlap between parent/new acquisition")
    illustration_sha = None
    if illustrations:
        from m33_objects_illustrations import normalized

        acquired_images, illustration_sha = bound_json(
            illustrations / "acquisition.json"
        )
        protected_inputs[illustrations / "acquisition.json"] = illustration_sha
        excluded_ids = specification["illustrations"]["excluded_ids"]
        source_ids = {r["source_id"] for r in acquired_images["sources"]}
        if (
            len(set(excluded_ids)) != len(excluded_ids)
            or not set(excluded_ids) <= source_ids
        ):
            raise ValueError("Invalid explicit illustration review")
        for row in acquired_images["sources"]:
            path = Path(row["source_file"])
            if (
                not path.resolve().is_relative_to(illustrations.resolve())
                or sha(path) != row["source_file_sha256"]
            ):
                raise ValueError("Illustration source/path changed")
            protected_inputs[path] = row["source_file_sha256"]
            config = acquired_images["publishers"][row["publisher"]]
            licence = illustrations / row["publisher"] / config["licence_file"]
            if sha(licence) != row["licence_sha256"]:
                raise ValueError("Illustration licence changed")
            protected_inputs[licence] = row["licence_sha256"]
            if row["source_id"] in excluded_ids:
                rejected.append(
                    {
                        "source_id": row["source_id"],
                        "reason": "Explicit visual exclusion: teacup/saucer or visible volume text",
                    }
                )
                continue
            if row["declared_split"] != (
                "final" if row["publisher"] == "openmoji" else "train"
            ) or row["proposed_answer"] not in (*CLASSES.values(), "UNKNOWN"):
                raise ValueError("Predeclared publisher scope changed")
            records.append(
                row
                | {
                    "answer": row["proposed_answer"],
                    "parent": False,
                    "concept_id": parent_manifest["concept_ids"].get(
                        row["proposed_answer"]
                    ),
                    "role": "VISUALLY_CURATED_NONBLIND_COLOR_ILLUSTRATION",
                }
            )
            pixels.append(np.asarray(normalized(path)))
        groups = declared_groups(records, families(pixels))
        grouped = defaultdict(list)
        for i, group in enumerate(groups):
            grouped[group].append(i)
        remove = set()
        for indices in grouped.values():
            labels = {records[i]["answer"] for i in indices}
            owners = {records[i]["split"] for i in indices if records[i].get("parent")}
            owners.update(
                records[i]["declared_split"]
                for i in indices
                if records[i].get("declared_split") and not records[i].get("parent")
            )
            if len(labels) > 1 or len(owners) > 1:
                # Reject new bridges; never silently remove old evaluation rows.
                remove.update(i for i in indices if not records[i].get("parent"))
        for i in sorted(remove):
            rejected.append(
                {
                    "source_id": records[i]["source_id"],
                    "reason": "New conflicting-label/partition bridge excluded; all parent rows retained",
                }
            )
        records, pixels = (
            [r for i, r in enumerate(records) if i not in remove],
            [p for i, p in enumerate(pixels) if i not in remove],
        )
        groups = declared_groups(records, families(pixels))
    else:
        groups = families(pixels)
    assigned, conflicts, fresh_counts = assign_groups(records, groups)
    rejected.extend(conflicts)
    if any(fresh_counts.get(label, 0) < 20 for label in CLASSES.values()):
        raise ValueError("Too few fresh independent positive families")
    prepared = {split: [] for split in SPLITS}
    prepared_pixels = {split: [] for split in SPLITS}
    for index, split, identity in sorted(assigned):
        pixel = pixels[index]
        prepared[split].append(
            records[index]
            | {
                "split": split,
                "family_id": identity,
                "pixel_sha256": hashlib.sha256(pixel.tobytes()).hexdigest(),
            }
        )
        prepared_pixels[split].append(pixel)
    if any(
        sum(r["answer"] == label for r in prepared["final"]) < 5
        for label in CLASSES.values()
    ):
        raise ValueError("Fresh final lacks positive class support")
    owners = {}
    for split, rows in prepared.items():
        for row in rows:
            for identity in (row["source_id"], row["family_id"], row["pixel_sha256"]):
                if owners.setdefault(identity, split) != split:
                    raise ValueError("Cross-partition source/family/pixel leakage")
    for split in SPLITS[:-1]:
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
        prepared_pixels[split].append(np.zeros((96, 96, 3), dtype=np.uint8))
    output.mkdir(parents=True)
    payload, registry = {}, []
    (output / "images").mkdir()
    for split, rows in prepared.items():
        payload[split + "_pixels"] = np.stack(prepared_pixels[split])
        payload[split + "_answers"] = np.array([r["answer"] for r in rows])
        payload[split + "_ids"] = np.array([r["source_id"] for r in rows])
        for row, pixel in zip(rows, prepared_pixels[split], strict=True):
            if row["role"] == "SHARED_CONSTANT_CONTROL":
                continue
            path = output / "images" / (row["pixel_sha256"] + ".png")
            Image.fromarray(pixel).save(path)
            registry.append(row | {"image_path": str(path), "image_sha256": sha(path)})
    np.savez_compressed(output / "pixels.npz", **payload)
    result = {
        "schema": 2,
        "classes": CLASSES,
        "concept_ids": parent_manifest["concept_ids"],
        "parent_dataset_sha256": parent_sha,
        "parent_pixels_sha256": parent_manifest["pixels_sha256"],
        "acquisition_sha256": acquisition_sha,
        "illustrations_acquisition_sha256": illustration_sha,
        "review_sha256": review_sha,
        "licence_snapshot_sha256": protected_inputs[root / "LICENSE.quickdraw"],
        "pixels_sha256": sha(output / "pixels.npz"),
        "fresh_family_counts": fresh_counts,
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
        "limits": "Non-blind visually curated QuickDraw sketches and optional licensed color illustrations, not photos/general sight. All old final images held as known regression, never training. Global source/exact/mirror/coarse-mask-IoU>=.88 and declared artwork families. With illustrations, new conflicting bridges excluded while every parent row retained; publisher OpenMoji entirely final. Fresh final only newly acquired sources with no prior members. No artist IDs/exhaustive semantic independence. Related illustration variants are not independent families. Seven known textbook diagnostics never select weights/thresholds. Shared absence controls not independent evidence.",
    }
    write_json(output / "dataset.json", result)
    write_json(output / "image-registry.json", registry)
    if any(sha(path) != expected for path, expected in protected_inputs.items()):
        raise ValueError("Source/review/parent changed during expansion")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "root", "review", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--illustrations", type=Path)
    args = parser.parse_args()
    result = build(args.parent, args.root, args.review, args.output, args.illustrations)
    print(
        json.dumps(
            {
                "counts": result["counts"],
                "fresh_family_counts": result["fresh_family_counts"],
                "excluded": len(result["excluded"]),
            },
            ensure_ascii=False,
        )
    )
