"""Independent source/owner bookkeeping across the photo reliability iteration."""

import argparse
import json
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_objects_photo_prepare import reviewed_rows


def verify(parent, data, review, photos, output):
    old = json.loads((parent / "dataset.json").read_text(encoding="utf-8"))
    new = json.loads((data / "dataset.json").read_text(encoding="utf-8"))
    if new["parent_dataset_sha256"] != sha(parent / "dataset.json"):
        raise ValueError("Parent binding differs")
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
        raise ValueError("Prior source was removed/added")
    for identity, (split, row) in previous.items():
        owner, actual = inherited[identity]
        if owner != ("regression" if split == "final" else split) or any(
            actual[k] != row[k]
            for k in ("pixel_sha256", "answer", "source_file_sha256")
        ):
            raise ValueError("Prior pixel/gold/owner changed")
    specification = json.loads(review.read_text(encoding="utf-8"))
    admitted, _, protected = reviewed_rows(photos, specification["photos"])
    reviewed = {r["source_id"]: r for r in admitted}
    owners, counts = {}, {}
    for split, rows in new["records"].items():
        for row in rows:
            if row["role"] != "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH":
                continue
            # Prior photo finals become known regression just like drawings.
            # Their gold/bytes/owner were checked above against the parent,
            # and must not be looked up in the new acquisition/review.
            if row.get("parent"):
                continue
            source = reviewed[row["source_id"]]
            if (
                split != source["declared_split"]
                or row["source_file_sha256"] != source["source_file_sha256"]
            ):
                raise ValueError("Photo acquired/reviewed ownership changed")
            if owners.setdefault(row["author_identity"], split) != split:
                raise ValueError("Photo author crossed partitions")
            counts[split] = counts.get(split, 0) + 1
    if any(sha(p) != value for p, value in protected.items()):
        raise ValueError("Protected photo evidence changed")
    result = {
        "status": "ALL_PARENT_NONCONSTANT_ROWS_PRESERVED",
        "parent_sources": len(previous),
        "prior_final_never_training": True,
        "photo_author_owners": owners,
        "photos_by_split": counts,
        "dataset_sha256": sha(data / "dataset.json"),
        "review_sha256": sha(review),
        "limits": "Bookkeeping against visually curated labels, not independent blind semantic truth. Thumbnail source bytes retained; full photo original not acquired.",
    }
    write_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "data", "review", "photos", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.parent, args.data, args.review, args.photos, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "photo_author_owners"}))
