"""Freeze a winner from development evidence only, before calibration/final runs."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from m33_objects_data import sha, write_json


def select(candidates, output, *, tuning=False):
    if output.exists() or (len(candidates) < 2 if tuning else len(candidates) != 3):
        raise ValueError("Predeclared candidates and fresh receipt required")
    reports = []
    dataset, round_id, learning_rate, normalization = None, None, None, None
    score_contract = None
    for root in candidates:
        report = json.loads(
            (root / "development-report.json").read_text(encoding="utf-8")
        )
        protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
        domain_score = tuple(
            protocol["config"].get(name, False)
            for name in ("domain_balanced_dev", "class_domain_balanced_dev")
        )
        if any(type(flag) is not bool for flag in domain_score) or (
            domain_score[1] and not domain_score[0]
        ):
            raise ValueError("Invalid development scoring contract")
        if score_contract is None:
            score_contract = domain_score
        elif score_contract != domain_score:
            raise ValueError(
                "Different development scoring contracts cannot be compared"
            )
        if reports and protocol.get("warm_start_sha256") != reports[0].get(
            "warm_start_sha256"
        ):
            raise ValueError("Candidates used different own warm-start checkpoints")
        if (
            report["status"] != "DEVELOPMENT_ONLY_NO_CALIBRATION_OR_FINAL"
            or report["production_admitted"]
            or report["checkpoint_sha256"] != sha(root / "best.pt")
            or report["protocol_sha256"] != sha(root / "protocol.json")
            or not report["inherited_tensors_byte_preserved"]
            or not protocol["development_only"]
            or protocol["config"]["steps"] != 10000
            or any(
                (root / filename).exists()
                for filename in (
                    "report.json",
                    "frozen-calibration.json",
                    "object-final-predictions.json",
                )
            )
        ):
            raise ValueError("Candidate not development-only protected evidence")
        score = report["best_dev_loss"]
        if not math.isfinite(score) or score != min(
            r["dev_loss"] for r in report["history"]
        ):
            raise ValueError("Invalid development selection score")
        if dataset is None:
            dataset, round_id = report["dataset_sha256"], protocol["config"]["round_id"]
            learning_rate = protocol["config"].get("learning_rate", 0.0001)
            normalization = report["architecture"].get("object_unknown_adapter", False)
        if (
            dataset != report["dataset_sha256"]
            or round_id != protocol["config"]["round_id"]
            or (
                not tuning
                and learning_rate != protocol["config"].get("learning_rate", 0.0001)
            )
            or (
                not tuning
                and normalization
                != report["architecture"].get("object_unknown_adapter", False)
            )
        ):
            raise ValueError("Candidates used different data/seeds")
        reports.append(
            {
                "name": root.name,
                "candidate_path": str(root),
                "checkpoint_sha256": report["checkpoint_sha256"],
                "development_report_sha256": sha(root / "development-report.json"),
                "protocol_sha256": sha(root / "protocol.json"),
                "best_dev_loss": score,
                "best_step": report["best_step"],
                "architecture": report["architecture"],
                "parameters": report["parameters"],
                "learning_rate": protocol["config"].get("learning_rate", 0.0001),
                "capsule_sha256": protocol.get("capsule_sha256"),
                "warm_start_sha256": protocol.get("warm_start_sha256"),
                "training_options": {
                    k: protocol["config"].get(
                        k, False if k == "diversity_augmentation" else 0
                    )
                    for k in (
                        "diversity_augmentation",
                        "illustration_fraction",
                        "domain_balanced_dev",
                        "class_domain_balanced_dev",
                    )
                },
            }
        )
    configs = {
        (
            r["architecture"]["vision_extension_channels"],
            r["architecture"]["vision_extension_depth"],
        )
        for r in reports
    }
    if len({r["checkpoint_sha256"] for r in reports}) != len(reports):
        raise ValueError("Repeated candidate checkpoint")
    if not tuning and configs != {(0, 0), (32, 0), (64, 2)}:
        raise ValueError("Candidates do not match predeclared architecture comparison")
    winner = min(reports, key=lambda r: (r["best_dev_loss"], r["name"]))
    result = {
        "schema": 1,
        "selection_used": "DEVELOPMENT_ONLY",
        "dataset_sha256": dataset,
        "round_id": round_id,
        "learning_rate": winner["learning_rate"],
        "comparison": "DEVELOPMENT_HYPERPARAMETER_TUNING_NOT_WEIGHT_SIZE_CAUSAL_PROOF"
        if tuning
        else "MATCHED_ARCHITECTURE_COMPARISON",
        "candidates": reports,
        "winner": winner,
        "production_admitted": False,
        "limits": "Candidate choice precedes all calibration/final evaluation. No fresh-final metrics used in selection. Raw development accuracy not a safe naming gate.",
    }
    write_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, nargs="+", required=True)
    parser.add_argument("--tuning-selection", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            select(args.candidates, args.output, tuning=args.tuning_selection),
            ensure_ascii=False,
        )
    )
