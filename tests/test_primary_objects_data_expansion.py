"""A larger source proposal batch must not silently recycle old drawing IDs."""

import importlib.util
import io
import json
from pathlib import Path
from typing import ClassVar

import pytest

spec = importlib.util.spec_from_file_location(
    "objects_data_expansion", Path(__file__).parents[1] / "scripts/m33_objects_data.py"
)
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)


class Response(io.BytesIO):
    headers: ClassVar[dict] = {}


def test_acquisition_excludes_old_proposals_and_records_parent_hash(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(data, "CLASSES", {"apple": "яблоко"})
    previous = tmp_path / "previous.json"
    previous.write_text(
        json.dumps({"files": [{"file": "raw/apple.ndjson", "selected_ids": ["old"]}]})
    )

    def fetch(url, timeout):
        if url == data.LICENSE_URL:
            return Response(b"Creative Commons Attribution 4.0")
        category = Path(url).stem
        records = [
            {
                "word": category,
                "key_id": key,
                "recognized": True,
                "drawing": [[[0, 10], [0, 10]]],
            }
            for key in ["old", "new"]
        ]
        return Response(("\n".join(json.dumps(row) for row in records) + "\n").encode())

    monkeypatch.setattr(data, "urlopen", fetch)
    data.acquire(
        tmp_path / "new",
        1,
        1,
        exclude_acquisition=previous,
        negative_categories=("pear",),
    )
    manifest = json.loads(
        (tmp_path / "new/acquisition.json").read_text(encoding="utf-8")
    )
    assert manifest["files"][0]["selected_ids"] == ["new"]
    assert manifest["files"][0]["prior_ids_excluded"] == 1
    assert manifest["excluded_acquisition_sha256"] == data.sha(previous)


@pytest.mark.parametrize("negative", [("apple",), ("pear", "pear"), ("../escape",), ()])
def test_invalid_source_scope_does_not_create_directory(tmp_path, negative):
    with pytest.raises(ValueError):
        data.acquire(tmp_path / "new", 1, 1, negative_categories=negative)
    assert not (tmp_path / "new").exists()
