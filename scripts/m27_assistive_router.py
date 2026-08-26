from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage2.router_research.baselines import (
    CharacterNgramRouter,
    TokenOverlapRouter,
)
from ai_brain.stage2.router_research.blind import open_blind_once
from ai_brain.stage2.router_research.dataset import (
    freeze_recipe,
    generate_router_dataset,
)
from ai_brain.stage2.router_research.evaluation import evaluate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    manifest = generate_router_dataset(root)
    train = _read(root / "train.jsonl")
    development = _read(root / "development.jsonl")
    calibration = _read(root / "calibration.jsonl")
    models = {
        "character_ngram": CharacterNgramRouter().fit(train),
        "token_overlap": TokenOverlapRouter().fit(train),
    }
    development_metrics = {
        name: evaluate(model, development) for name, model in models.items()
    }
    selected_name = max(models, key=lambda name: development_metrics[name]["top1"])
    selected = models[selected_name]
    calibration_metrics = evaluate(selected, calibration)
    freeze = freeze_recipe(
        root,
        {
            "selected_baseline": selected_name,
            "threshold": 0.0,
            "development_metrics": development_metrics[selected_name],
            "calibration_metrics": calibration_metrics,
            "authority": "ASSISTIVE_PROPOSAL_ONLY",
        },
    )
    blind_public = _read(root / "blind_public.jsonl")
    predictions_path = root / "blind_predictions.jsonl"
    predictions_path.write_text(
        "".join(
            canonical_json(
                {"row_id": row["row_id"], "prediction": selected.predict(row["text"])}
            )
            + "\n"
            for row in blind_public
        ),
        encoding="utf-8",
    )
    blind = open_blind_once(root, predictions_path)
    result = {
        "status": "PASS",
        "manifest_hash": manifest["manifest_hash"],
        "development": development_metrics,
        "calibration": calibration_metrics,
        "recipe_freeze_hash": freeze["freeze_hash"],
        "blind": blind,
        "false_exact_authority": 0,
    }
    (root / "assistive_router_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def _read(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


if __name__ == "__main__":
    main()
