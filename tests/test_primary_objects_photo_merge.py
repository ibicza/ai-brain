"""Reviewed top-ups preserve bytes, explicit labels, and author partitions."""

import io
import sys
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import m33_objects_photo_round as proposals
from m33_objects_data import sha, write_json
from m33_objects_photo_merge import merge
from m33_objects_photo_prepare import reviewed_rows
from m33_objects_photos import QUERIES


def source(tmp_path, monkeypatch, name, page_id):
    root = tmp_path / name
    root.mkdir()
    for folder in ("images", "downloads", "metadata"):
        (root / folder).mkdir()
    blob = io.BytesIO()
    Image.new("RGB", (96, 96), "red").save(blob, format="PNG")
    monkeypatch.setattr(proposals, "get", lambda *_: blob.getvalue())
    page = {
        "pageid": page_id,
        "imageinfo": [
            {
                "extmetadata": {
                    "LicenseShortName": {"value": "CC0"},
                    "Artist": {"value": "Same pending author"},
                },
                "mime": "image/png",
                "url": "https://upload.wikimedia.org/a.png",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:a.png",
                "sha1": "abc",
            }
        ],
    }
    row = proposals.candidate(page, "apple", root, set(), set(), set(), Counter())
    write_json(root / "acquisition.json", {"training_started": False, "sources": [row]})
    review = root / "review.json"
    write_json(
        review,
        {
            "training_started": False,
            "photos": {k: {"include": [0] if k == "apple" else []} for k in QUERIES},
        },
    )
    return root, review


def test_same_pending_author_stays_one_family_and_copies_bound_bytes(
    tmp_path, monkeypatch
):
    inputs = [
        source(tmp_path, monkeypatch, "a", 1),
        source(tmp_path, monkeypatch, "b", 2),
    ]
    import json

    before = {p: sha(p) for r, v in inputs for p in (*r.rglob("*.json"), v)}
    dest = tmp_path / "merged"
    result = merge(inputs, dest)
    assert result["photos"] == 2 and result["authors"] == 1
    review = json.loads((dest / "review.json").read_text())
    rows, excluded, _ = reviewed_rows(dest, review["photos"])
    assert not excluded and len({r["declared_family"] for r in rows}) == 1
    assert len({r["declared_split"] for r in rows}) == 1
    assert all(Path(r["source_file"]).is_relative_to(dest) for r in rows)
    assert all(sha(p) == digest for p, digest in before.items())
    with pytest.raises(ValueError, match="Fresh"):
        merge(inputs, dest)


def test_repeated_ids_fail_before_destination_created(tmp_path, monkeypatch):
    inputs = [
        source(tmp_path, monkeypatch, "a", 1),
        source(tmp_path, monkeypatch, "b", 1),
    ]
    dest = tmp_path / "merged"
    with pytest.raises(ValueError, match="Repeated"):
        merge(inputs, dest)
    assert not dest.exists()


def test_changed_source_rejected_not_copied(tmp_path, monkeypatch):
    inputs = [
        source(tmp_path, monkeypatch, "a", 1),
        source(tmp_path, monkeypatch, "b", 2),
    ]
    (inputs[0][0] / "images/1.image").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        merge(inputs, tmp_path / "merged")


def test_review_cannot_rebind_indices_to_a_different_acquisition(tmp_path, monkeypatch):
    import json

    inputs = [
        source(tmp_path, monkeypatch, "a", 1),
        source(tmp_path, monkeypatch, "b", 2),
    ]
    review_path = inputs[0][1]
    review = json.loads(review_path.read_text())
    review["acquisition_sha256"] = "0" * 64
    review_path.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="acquisition binding"):
        merge(inputs, tmp_path / "merged")
