"""Record actual frozen-candidate errors; never feed known controls into training."""

import argparse
import json
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_verify_objects_evidence import verify


def analyze(experiment, data, output, previous=None):
    verify(experiment, data)
    report = json.loads((experiment / "report.json").read_text(encoding="utf-8"))
    failures = {}
    controls = {}
    for cohort in ("object-final", "object-regression", "textbook-diagnostic"):
        path = experiment / (cohort + "-predictions.json")
        rows = json.loads(path.read_text(encoding="utf-8"))
        failures[cohort] = [
            {k: r[k] for k in ("source_id", "gold", "selected")}
            for r in rows
            if r["selected"] != "UNKNOWN" and r["gold"] != r["selected"]
        ]
        if previous:
            prior = json.loads(previous.read_text(encoding="utf-8"))
            known = {
                r["source_id"]: r for r in prior["confident_errors"].get(cohort, [])
            }
            # Prior final controls become regression. Never reclassify them as
            # fresh, use them for selection, or silently count abstention correct.
            if cohort == "object-regression":
                known.update(
                    {
                        r["source_id"]: r
                        for r in prior["confident_errors"].get("object-final", [])
                    }
                )
            controls[cohort] = [
                {
                    "source_id": r["source_id"],
                    "gold": r["gold"],
                    "previous_selected": known[r["source_id"]]["selected"],
                    "selected": r["selected"],
                    "outcome": "ABSTAINED_NOT_RECOGNITION"
                    if r["selected"] == "UNKNOWN"
                    else "CORRECT_ON_KNOWN_CONTROL"
                    if r["selected"] == r["gold"]
                    else "PERSISTENT_CONFIDENT_ERROR",
                }
                for r in rows
                if r["source_id"] in known
            ]
    result = {
        "status": "BOUNDED_GATES_PASSED_NOT_DEPLOYED"
        if report["object_gate"] and report["regression_gate"]
        else "CANDIDATE_REJECTED_NOT_DEPLOYED",
        "checkpoint_sha256": sha(experiment / "best.pt"),
        "report_sha256": sha(experiment / "report.json"),
        "confident_errors": failures,
        "prior_known_error_controls": controls,
        "previous_error_receipt_sha256": sha(previous) if previous else None,
        "next_data": "New independently reviewed fish lookalikes, mugs and apples across richer styles; hold new families out. Never move these known control images to training.",
        "limits": "Observed confusions, not a causal diagnosis. Do not tune thresholds against this final or claim general honesty.",
    }
    write_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("experiment", "data", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            analyze(args.experiment, args.data, args.output, args.previous),
            ensure_ascii=False,
        )
    )
