"""Check all prior nonconstant controls remain byte-identical and never trained."""

import argparse
import json
from pathlib import Path

from m33_objects_data import sha, write_json


def verify(parent, data, output):
    old = json.loads((parent / "dataset.json").read_text())
    new = json.loads((data / "dataset.json").read_text())
    if new["parent_dataset_sha256"] != sha(parent / "dataset.json"):
        raise ValueError("Parent lineage changed")
    previous = {
        r["source_id"]: (s, r)
        for s, rows in old["records"].items()
        for r in rows
        if r["role"] != "SHARED_CONSTANT_CONTROL"
    }
    inherited = {
        r["source_id"]: (s, r)
        for s, rows in new["records"].items()
        for r in rows
        if r.get("parent")
    }
    if previous.keys() != inherited.keys():
        raise ValueError("An old source was removed or added to inherited evidence")
    for identity, (split, row) in previous.items():
        actual_split, actual = inherited[identity]
        if actual_split != ("regression" if split == "final" else split) or any(
            actual[k] != row[k]
            for k in ("pixel_sha256", "answer", "source_file_sha256")
        ):
            raise ValueError("Old ownership/pixels/gold changed")
    illustrations = [
        r for rows in new["records"].values() for r in rows if r.get("publisher")
    ]
    if any(
        r["split"] != ("final" if r["publisher"] == "openmoji" else "train")
        for r in illustrations
    ):
        raise ValueError("Publisher holdout boundary violated")
    result = {
        "status": "ALL_PARENT_NONCONSTANT_ROWS_PRESERVED",
        "parent_sources": len(previous),
        "prior_final_never_training": True,
        "openmoji_training_and_dev_sources": 0,
        "illustrations_by_split": {
            s: sum(r["split"] == s for r in illustrations)
            for s in ("train", "dev", "calibration", "final")
        },
        "dataset_sha256": sha(data / "dataset.json"),
        "limits": "Source/pixel/label/owner bookkeeping, not independent blind semantic truth. Full curator review required separately.",
    }
    write_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "data", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.parent, args.data, args.output)))
