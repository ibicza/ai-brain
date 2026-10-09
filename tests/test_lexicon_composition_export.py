"""The separate procedural route must not relax default textbook admission."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "composition_export",
    Path(__file__).parents[1] / "scripts/lexicon_catalogue_export.py",
)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def fixture(tmp_path):
    pixel = tmp_path / "scene.png"
    pixel.write_bytes(b"exact procedural pixel fixture")
    data_file = tmp_path / "dataset.npz"
    data_file.write_bytes(b"dataset")
    records_file = tmp_path / "records.gz"
    records_file.write_bytes(b"records")
    row = [None] * 19
    row[0], row[2], row[3], row[7], row[9], row[10], row[15], row[16] = (
        "cmp-v2-test",
        str(pixel),
        "train",
        "composition-v2/train/1",
        "composition-v2/train/1",
        export.sha(pixel),
        "Только процедурный эксперимент",
        "Полный кадр эксперимента",
    )
    registry = {
        "kind": "own_procedural_attribute_pilot",
        "asset_root": str(tmp_path),
        "dataset_path": str(data_file),
        "dataset_sha256": export.sha(data_file),
        "records_path": str(records_file),
        "records_sha256": export.sha(records_file),
        "production_admitted": False,
        "book_training_admitted": False,
        "rows": {row[0]: row.copy()},
    }
    return {"composition_media_registry": registry}, [row]


def test_bounded_procedural_assets(tmp_path):
    data, rows = fixture(tmp_path)
    export.validate_new_media(data, rows)
    with pytest.raises(ValueError):
        export.validate_new_media({}, rows)


@pytest.mark.parametrize(
    "error",
    ("book", "production", "split", "path", "hash", "extra", "dataset", "records"),
)
def test_no_broad_admission_or_mutated_assets(tmp_path, error):
    data, rows = fixture(tmp_path)
    registry = data["composition_media_registry"]
    if error == "book":
        registry["book_training_admitted"] = True
    elif error == "production":
        registry["production_admitted"] = True
    elif error == "split":
        rows[0][3] = "fresh_final"
    elif error == "path":
        registry["asset_root"] = str(tmp_path / "other")
    elif error == "hash":
        Path(rows[0][2]).write_bytes(b"changed")
    elif error == "extra":
        rows.append(rows[0].copy())
    elif error in ("dataset", "records"):
        Path(registry[error + "_path"]).write_bytes(b"changed")
    with pytest.raises(ValueError):
        export.validate_new_media(data, rows)
