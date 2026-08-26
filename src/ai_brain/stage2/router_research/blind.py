"""One-opening blind evidence validation for assistive routing research."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash, utc_now


def open_blind_once(dataset_dir: Path, predictions_path: Path) -> dict[str, Any]:
    root = dataset_dir.resolve()
    freeze = json.loads((root / "recipe_freeze.json").read_text(encoding="utf-8"))
    marker = root / "blind_opened.json"
    if marker.exists():
        raise ValueError("blind targets have already been opened")
    target_path = root / "blind_targets.hidden.jsonl"
    if bytes_hash(target_path.read_bytes()) != freeze["blind_hashes"][target_path.name]:
        raise ValueError("blind target hash differs from recipe freeze")
    targets = {row["row_id"]: row["label"] for row in _read_jsonl(target_path)}
    predictions = {
        row["row_id"]: row["prediction"] for row in _read_jsonl(predictions_path)
    }
    if set(targets) != set(predictions):
        raise ValueError("blind prediction IDs do not match frozen targets")
    correct = sum(predictions[key] == value for key, value in targets.items())
    body = {
        "blind_target_hash": freeze["blind_hashes"][target_path.name],
        "prediction_hash": bytes_hash(predictions_path.read_bytes()),
        "count": len(targets),
        "top1": correct / len(targets) if targets else 0.0,
        "opened_at": utc_now(),
    }
    evidence = {
        **body,
        "evidence_hash": content_hash({**body, "top1": format(body["top1"], ".17g")}),
    }
    marker.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return evidence


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
