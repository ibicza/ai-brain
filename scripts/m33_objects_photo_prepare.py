"""Reviewed photo admission and photo-aware duplicate families, not inferred gold."""

import hashlib
import json
from pathlib import Path

import numpy as np
from m33_objects_data import CLASSES, sha
from m33_objects_photos import QUERIES, author_owner, rights
from m33_objects_prepare import families
from PIL import Image


def reviewed_rows(root, specification):
    path = root / "acquisition.json"
    acquired = json.loads(path.read_text(encoding="utf-8"))
    protected = {path: sha(path)}
    if acquired["training_started"] is not False or set(specification) != set(QUERIES):
        raise ValueError("Complete explicit photo review required")
    result, rejected, seen = [], [], set()
    for category in QUERIES:
        rows = [r for r in acquired["sources"] if r["source_category"] == category]
        choice = specification[category]
        if ("include" in choice) == ("exclude" in choice):
            raise ValueError("One explicit photo decision required")
        selected = choice.get("include", choice.get("exclude"))
        if len(set(selected)) != len(selected) or any(
            type(i) is not int or not 0 <= i < len(rows) for i in selected
        ):
            raise ValueError("Invalid photo review indices")
        for i, row in enumerate(rows):
            if row["source_id"] in seen:
                raise ValueError("Repeated photo ID")
            seen.add(row["source_id"])
            for key in ("source_file", "metadata_file"):
                source = Path(row[key])
                digest = row[
                    "source_file_sha256" if key == "source_file" else "metadata_sha256"
                ]
                if (
                    not source.resolve().is_relative_to(root.resolve())
                    or sha(source) != digest
                ):
                    raise ValueError("Photo source/rights metadata changed or escaped")
                protected[source] = digest
            metadata = json.loads(
                Path(row["metadata_file"]).read_text(encoding="utf-8")
            )
            info = metadata["imageinfo"][0]
            if (
                row["source_id"] != "commons/" + str(metadata["pageid"])
                or row["source_url"] != info["descriptionurl"]
                or row["download_url"] != info.get("thumburl", info["url"])
                or row["original_url_not_acquired"] != info["url"]
            ):
                raise ValueError("Photo identity/metadata/download URL binding changed")
            name, url, artist = rights(metadata["imageinfo"][0]["extmetadata"])
            owner, split = author_owner(artist)
            if (
                row["licence"],
                row["licence_url"],
                row["attribution"],
                row["author_identity"],
                row["declared_split"],
                row["declared_family"],
                row["proposed_answer"],
            ) != (
                name,
                url,
                artist,
                owner,
                split,
                "commons/" + owner + "/" + category,
                CLASSES.get(category, "UNKNOWN"),
            ):
                raise ValueError("Photo rights/author-owner/label proposal changed")
            if (i in selected) != ("include" in choice):
                rejected.append(
                    {
                        "source_id": row["source_id"],
                        "reason": "Explicit visual photo exclusion: ambiguous, incidental object, illustration/text, or unsuitable rights context",
                    }
                )
                continue
            result.append(
                row
                | {
                    "answer": row["proposed_answer"],
                    "parent": False,
                    "role": "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH",
                }
            )
    return result, rejected, protected


def photo_aware_families(pixels, records):
    """Preserve sketch mask checks; full-background photos require RGB proximity."""
    n = len(records)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    nonphoto = [
        i
        for i, r in enumerate(records)
        if r["role"] != "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
    ]
    roots = {}
    for index, family in zip(
        nonphoto,
        families([pixels[i] for i in nonphoto]) if nonphoto else [],
        strict=True,
    ):
        if family in roots:
            parent[find(index)] = find(roots[family])
        roots[family] = index
    seen = {}
    for i, pixel in enumerate(pixels):
        for view in (pixel, pixel[:, ::-1]):
            digest = hashlib.sha256(view.tobytes()).hexdigest()
            if digest in seen:
                parent[find(i)] = find(seen[digest])
            seen[digest] = i
    photo = [
        i
        for i, r in enumerate(records)
        if r["role"] == "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
    ]
    small = [
        np.asarray(Image.fromarray(pixels[i]).resize((24, 24)), dtype=np.float32)
        for i in photo
    ]
    for i, first in enumerate(small):
        for j in range(i):
            if (
                min(
                    np.abs(first - small[j]).mean(),
                    np.abs(first - small[j][:, ::-1]).mean(),
                )
                <= 6
            ):
                parent[find(photo[i])] = find(photo[j])
    return [find(i) for i in range(n)]
