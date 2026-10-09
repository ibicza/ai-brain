"""No photo cohort may silently omit any of the eight positive classes."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import m33_objects_photo_coverage as coverage
import m33_objects_reliability_lineage as lineage
from m33_objects_data import CLASSES


def rows():
    return [
        {
            "source_id": f"{split}-{label}-{i}",
            "author_identity": f"{split}-{i // 2}",
            "declared_split": split,
            "answer": label,
        }
        for split in coverage.SPLITS
        for label in (*CLASSES.values(), "UNKNOWN")
        for i in range(coverage.MIN_IMAGES[split] + 1)
    ]


def test_complete_class_cohorts_pass_but_missing_one_does_not():
    assert coverage.coverage(rows())["ready"] is True
    subset = [
        r
        for r in rows()
        if not (r["declared_split"] == "dev" and r["answer"] == "кружка")
    ]
    result = coverage.coverage(subset)
    assert result["ready"] is False
    assert len(result["missing"]) == 1
    assert result["missing"][0]["answer"] == "кружка"


def test_many_rows_from_one_author_not_independent_support():
    subset = rows()
    for row in subset:
        if row["declared_split"] == "final":
            row["author_identity"] = "one-final-author"
    assert coverage.coverage(subset)["ready"] is False
    with pytest.raises(ValueError, match="lacks class/cohort"):
        coverage.require_ready(subset)
    assert coverage.require_ready(rows())["ready"] is True


@pytest.mark.parametrize("field", ["source_id", "author_identity"])
def test_cohort_leakage_fails(field):
    subset = rows()
    subset[-1][field] = subset[0][field]
    with pytest.raises(ValueError, match="crossed"):
        coverage.coverage(subset)


def test_parent_photo_final_is_verified_as_regression_not_new_review(
    tmp_path, monkeypatch
):
    parent, data, photos = (tmp_path / name for name in ("parent", "new", "photos"))
    for path in (parent, data, photos):
        path.mkdir()
    previous = {
        "source_id": "commons/old",
        "role": "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH",
        "answer": "яблоко",
        "pixel_sha256": "pixels",
        "source_file_sha256": "source",
    }
    (parent / "dataset.json").write_text(json.dumps({"records": {"final": [previous]}}))
    inherited = previous | {"parent": True}
    (data / "dataset.json").write_text(
        json.dumps(
            {
                "parent_dataset_sha256": lineage.sha(parent / "dataset.json"),
                "records": {"regression": [inherited]},
            }
        )
    )
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"photos": {}}))
    monkeypatch.setattr(lineage, "reviewed_rows", lambda *args: ([], [], {}))
    result = lineage.verify(parent, data, review, photos, tmp_path / "receipt.json")
    assert result["parent_sources"] == 1
    assert result["prior_final_never_training"] is True
    assert result["photos_by_split"] == {}
