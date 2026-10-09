"""Snapshot isolated expansion source/data without touching either Git index."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(repo, data, review, output):
    if output.exists():
        raise ValueError("Fresh source capsule required")
    sources = [
        (p, p.relative_to(repo).as_posix()) for p in (repo / "src").rglob("*.py")
    ]
    for name in (
        "m33_primary_zero_pilot.py",
        "m33_primary_relations_pilot.py",
        "m33_primary_objects_pilot.py",
        "m33_objects_data.py",
        "m33_objects_prepare.py",
        "m33_objects_expand_prepare.py",
        "m33_objects_illustrations.py",
        "m33_objects_photos.py",
        "m33_objects_photo_prepare.py",
        "m33_objects_photo_round.py",
        "m33_objects_photo_coverage.py",
        "m33_objects_context_probe_remote.py",
        "m33_objects_select.py",
        "m33_verify_objects_evidence.py",
    ):
        sources.append((repo / "scripts" / name, "scripts/" + name))
    for name in (
        "test_primary_zero.py",
        "test_primary_relations.py",
        "test_primary_objects.py",
        "test_primary_objects_vision_extension.py",
        "test_primary_objects_data_expansion.py",
        "test_primary_objects_expand_prepare.py",
        "test_primary_objects_evidence.py",
        "test_primary_objects_selection.py",
        "test_primary_objects_diversity.py",
        "test_primary_objects_photos.py",
        "test_primary_objects_photo_round.py",
        "test_primary_objects_photo_coverage.py",
        "conftest.py",
    ):
        sources.append((repo / "tests" / name, "tests/" + name))
    for name in ("dataset.json", "pixels.npz"):
        sources.append((data / name, "data/" + name))
    sources.append((review, "data/objects_expansion_review.json"))
    entries = []
    with tarfile.open(output, "x:gz") as archive:
        for path, relative in sorted(sources, key=lambda item: item[1]):
            before = sha(path)
            archive.add(path, arcname=relative, recursive=False)
            if sha(path) != before:
                raise ValueError("Input changed while snapshotting")
            entries.append(
                {"file": relative, "sha256": before, "bytes": path.stat().st_size}
            )
        blob = (
            json.dumps({"schema": 1, "files": entries}, ensure_ascii=False, indent=2)
            + "\n"
        ).encode()
        info = tarfile.TarInfo("source-manifest.json")
        info.size = len(blob)
        archive.addfile(info, io.BytesIO(blob))
    with tarfile.open(output) as archive:
        for entry in entries:
            with archive.extractfile(entry["file"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                    raise ValueError("Capsule roundtrip mismatch")
    return {
        "path": str(output),
        "sha256": sha(output),
        "bytes": output.stat().st_size,
        "files": len(entries),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "data", "review", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.repo, args.data, args.review, args.output)))
