"""Pretraining coverage of all eight names in each photographic cohort.

Coverage is a data-readiness check, not a claim of model recognition or truth.
No learned policy, weight, threshold or held-out prediction is consulted.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from m33_objects_data import CLASSES, sha, write_json
from m33_objects_photo_prepare import reviewed_rows

SPLITS = ("train", "dev", "calibration", "final")
MIN_IMAGES = {"train": 20, "dev": 5, "calibration": 5, "final": 5}
MIN_AUTHORS = {"train": 8, "dev": 3, "calibration": 3, "final": 3}


def coverage(rows):
    cells = defaultdict(list)
    source_owners, author_owners = {}, {}
    for row in rows:
        owner = row["split"] if "split" in row else row["declared_split"]
        if owner not in SPLITS:
            continue
        if row["answer"] not in (*CLASSES.values(), "UNKNOWN"):
            raise ValueError("Photo label outside eight-name answer scope")
        if source_owners.setdefault(row["source_id"], owner) != owner:
            raise ValueError("Photo source crossed cohorts")
        if author_owners.setdefault(row["author_identity"], owner) != owner:
            raise ValueError("Photo author crossed cohorts")
        cells[owner, row["answer"]].append(row)
    missing, counts = [], {}
    for split in SPLITS:
        counts[split] = {}
        for label in (*CLASSES.values(), "UNKNOWN"):
            group = cells[split, label]
            authors = len({r["author_identity"] for r in group})
            counts[split][label] = {"images": len(group), "authors": authors}
            if len(group) < MIN_IMAGES[split] or authors < MIN_AUTHORS[split]:
                missing.append(
                    {
                        "split": split,
                        "answer": label,
                        "images": len(group),
                        "authors": authors,
                        "required_images": MIN_IMAGES[split],
                        "required_authors": MIN_AUTHORS[split],
                    }
                )
    return {
        "ready": not missing,
        "counts": counts,
        "missing": missing,
        "minimum_images": MIN_IMAGES,
        "minimum_authors": MIN_AUTHORS,
        "limits": "Author strings are declared families, not exhaustive semantic/session independence. Image counts alone never establish model mastery. No threshold/gate weakened.",
    }


def check(photos, review, output, data=None):
    spec = json.loads(review.read_text(encoding="utf-8"))
    if spec.get("training_started") is not False:
        raise ValueError("Pretraining review required")
    rows, rejected, protected = reviewed_rows(photos, spec["photos"])
    reviewed = {r["source_id"]: r for r in rows}
    dataset_sha = None
    if data:
        dataset_sha = sha(data / "dataset.json")
        manifest = json.loads((data / "dataset.json").read_text(encoding="utf-8"))
        if manifest["review_sha256"] != sha(review) or manifest[
            "photos_acquisition_sha256"
        ] != sha(photos / "acquisition.json"):
            raise ValueError("Prepared photo review binding differs")
        rows = [
            r
            for cohort in manifest["records"].values()
            for r in cohort
            if r["role"] == "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
            and not r.get("parent")
        ]
        for row in rows:
            source = reviewed[row["source_id"]]
            if (
                any(
                    row[k] != source[k]
                    for k in ("answer", "source_file_sha256", "author_identity")
                )
                or row["split"] != source["declared_split"]
            ):
                raise ValueError("Prepared photo changed reviewed label/owner/bytes")
    result = coverage(rows) | {
        "acquisition_sha256": sha(photos / "acquisition.json"),
        "review_sha256": sha(review),
        "dataset_sha256": dataset_sha,
        "reviewed_photos": len(reviewed),
        "visually_excluded": len(rejected),
        "training_started": False,
    }
    if any(sha(path) != digest for path, digest in protected.items()):
        raise ValueError("Photo evidence changed")
    write_json(output, result)
    return result


def require_ready(rows):
    result = coverage(rows)
    if not result["ready"]:
        raise ValueError(
            "Fresh photo-only expansion lacks class/cohort image and author support"
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("photos", "review", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--data", type=Path)
    args = parser.parse_args()
    result = check(args.photos, args.review, args.output, args.data)
    print(
        json.dumps(
            {
                "ready": result["ready"],
                "missing_cells": len(result["missing"]),
                "reviewed_photos": result["reviewed_photos"],
            }
        )
    )
