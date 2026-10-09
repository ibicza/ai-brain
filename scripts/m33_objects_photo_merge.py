"""Combine reviewed, untrained photo top-ups without changing source ownership.

The destination contains byte-identical copies under its own path boundary. Prior
reviews remain immutable; this is curated data, never a blind semantic examination.
"""

import argparse
import json
import shutil
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_objects_photo_prepare import reviewed_rows
from m33_objects_photos import QUERIES


def merge(inputs, output):
    if output.exists() or len(inputs) < 2:
        raise ValueError("Fresh destination and at least two reviewed rounds required")
    protected, selected, lineage, ids, author_owners = {}, [], [], set(), {}
    for root, review in inputs:
        spec = json.loads(review.read_text(encoding="utf-8"))
        if spec.get("training_started") is not False:
            raise ValueError("Only untrained, explicitly reviewed data can be combined")
        acquisition_sha = sha(root / "acquisition.json")
        if spec.get("acquisition_sha256", acquisition_sha) != acquisition_sha:
            raise ValueError("Visual review acquisition binding changed")
        rows, rejected, bindings = reviewed_rows(root, spec["photos"])
        protected.update(bindings)
        protected[review] = sha(review)
        lineage.append(
            {
                "acquisition": str((root / "acquisition.json").resolve()),
                "acquisition_sha256": bindings[root / "acquisition.json"],
                "review": str(review.resolve()),
                "review_sha256": sha(review),
                "admitted": len(rows),
                "excluded": len(rejected),
            }
        )
        for row in rows:
            if row["source_id"] in ids:
                raise ValueError("Repeated source ID across reviewed rounds")
            ids.add(row["source_id"])
            owner = row["declared_split"]
            if author_owners.setdefault(row["author_identity"], owner) != owner:
                raise ValueError("Author crossed cohorts")
            selected.append(row.copy())
    if any(sha(path) != digest for path, digest in protected.items()):
        raise ValueError("Input changed before copying")
    output.mkdir(parents=True)
    (output / "images").mkdir()
    (output / "metadata").mkdir()
    for row in selected:
        page_id = row["source_id"].split("/")[1]
        for key, folder, digest_key in (
            ("source_file", "images", "source_file_sha256"),
            ("metadata_file", "metadata", "metadata_sha256"),
        ):
            old = Path(row[key])
            dest = output / folder / (page_id + old.suffix)
            shutil.copyfile(old, dest)
            if sha(dest) != row[digest_key]:
                raise ValueError("Copy changed source or rights bytes")
            row[key] = str(dest.resolve())
    if any(sha(path) != digest for path, digest in protected.items()):
        raise ValueError("Input changed while copying")
    write_json(
        output / "acquisition.json",
        {
            "schema": 1,
            "training_started": False,
            "status": "COMBINED_CURATED_UNTRAINED_PHOTOS_NOT_BLIND_GOLD",
            "lineage": lineage,
            "sources": selected,
        },
    )
    review = {
        "training_started": False,
        "acquisition_sha256": sha(output / "acquisition.json"),
        "lineage": lineage,
        "photos": {
            category: {
                "include": list(
                    range(sum(r["source_category"] == category for r in selected))
                )
            }
            for category in QUERIES
        },
        "limits": "All included images inherit explicit earlier visual decisions. No labels inferred from search metadata. Same-author images retain their family and owner, not counted as independent scenes.",
    }
    write_json(output / "review.json", review)
    checked, excluded, _ = reviewed_rows(output, review["photos"])
    if len(checked) != len(selected) or excluded:
        raise ValueError("Combined admission roundtrip differs")
    return {"photos": len(checked), "authors": len(author_owners), "lineage": lineage}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs=2, type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(merge(args.input, args.output), ensure_ascii=False))
