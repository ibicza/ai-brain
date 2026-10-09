import gzip
import json

import pytest
from m33_objects_data import sha, write_json
from m33_objects_prompt_diagnostic import audit, metrics

from ai_brain.training import primary_objects as obj


def fixture(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    write_json(
        data / "dataset.json",
        {
            "records": {
                "dev": [
                    {
                        "source_id": "one",
                        "answer": "яблоко",
                        "role": "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH",
                    }
                ]
            }
        },
    )
    (tmp_path / "warm.pt").write_bytes(b"frozen warm")
    probabilities = [0.0] * obj.VOCAB_SIZE
    probabilities[obj.OBJECT_IDS["яблоко"]] = 0.95
    probabilities[obj.UNKNOWN] = 0.05
    rows = [{"source_id": "one", "gold": "яблоко", "probabilities": probabilities}]
    records = {"warm": {"question": {"single_view": rows, "five_view": rows}}}
    path = tmp_path / "records.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(records, stream)
    expected = {
        "raw_not_safe_policy": metrics(rows, 0),
        "fixed_099_dev_only": metrics(rows, 0.99),
    }
    report = tmp_path / "report.json"
    write_json(
        report,
        {
            "prompts": ["question"],
            "dataset_sha256": sha(data / "dataset.json"),
            "records_sha256": sha(path),
            "candidates": {
                "warm": {
                    "checkpoint_sha256": sha(tmp_path / "warm.pt"),
                    "prompts": {
                        "question": {"single_view": expected, "five_view": expected}
                    },
                }
            },
        },
    )
    return data, path, report


def test_repeated_prompts_and_views_do_not_inflate_unique_sources(tmp_path):
    data, path, report = fixture(tmp_path)
    result = audit(data, tmp_path, path, report)
    assert result["unique_photos"] == 1
    assert result["candidates"] == 1


def test_modified_stats_are_detected(tmp_path):
    data, path, report = fixture(tmp_path)
    value = json.loads(report.read_text(encoding="utf-8"))
    value["candidates"]["warm"]["prompts"]["question"]["single_view"][
        "fixed_099_dev_only"
    ]["accepted"] = 1
    report.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="arithmetic"):
        audit(data, tmp_path, path, report)
