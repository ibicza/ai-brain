"""Record actual frozen-candidate errors; never feed known controls into training."""

import argparse
import json
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_verify_objects_evidence import verify


def analyze(experiment, data, output):
    verify(experiment, data)
    failures = {}
    for cohort in ("object-final", "object-regression", "textbook-diagnostic"):
        path = experiment / (cohort + "-predictions.json")
        rows = json.loads(path.read_text(encoding="utf-8"))
        failures[cohort] = [
            {k: r[k] for k in ("source_id", "gold", "selected")}
            for r in rows
            if r["selected"] != "UNKNOWN" and r["gold"] != r["selected"]
        ]
    result = {
        "status": "CANDIDATE_REJECTED_NOT_DEPLOYED",
        "checkpoint_sha256": sha(experiment / "best.pt"),
        "report_sha256": sha(experiment / "report.json"),
        "confident_errors": failures,
        "next_data": "New independently reviewed fish lookalikes, mugs and apples across richer styles; hold new families out. Never move these known control images to training.",
        "limits": "Observed confusions, not a causal diagnosis. Do not tune thresholds against this final or claim general honesty.",
    }
    write_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("experiment", "data", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(analyze(args.experiment, args.data, args.output), ensure_ascii=False)
    )
