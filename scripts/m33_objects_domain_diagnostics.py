"""Post-freeze source-style metrics, never candidate selection or policy fitting."""

import argparse
import json
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_verify_objects_evidence import selected, statistics, verify


def diagnose(experiment, data, output):
    audit = verify(experiment, data)
    registry = json.loads((data / "image-registry.json").read_text(encoding="utf-8"))
    records = {r["source_id"]: r for r in registry}
    predictions = json.loads(
        (experiment / "object-final-predictions.json").read_text(encoding="utf-8")
    )
    domains = {}
    for name in ("openmoji", "sketches_and_absence_control"):
        rows = [
            r
            for r in predictions
            if (records.get(r["source_id"], {}).get("publisher") == "openmoji")
            == (name == "openmoji")
        ]
        domains[name] = {
            "frozen_safe_policy": statistics(rows),
            "raw_consensus_not_safe_policy": statistics(
                [dict(r, selected=selected(r["probabilities"], 0)) for r in rows]
            ),
            "families": len(
                {
                    records.get(r["source_id"], {}).get("family_id", r["source_id"])
                    for r in rows
                }
            ),
        }
    result = {
        "status": "POST_FREEZE_DOMAIN_DIAGNOSTIC_NO_TUNING",
        "domains": domains,
        "checkpoint_sha256": sha(experiment / "best.pt"),
        "dataset_sha256": sha(data / "dataset.json"),
        "arithmetic_audit": audit,
        "limits": "Raw consensus is not permitted naming. Style subset is small and related variants are not independent. This final is now known and cannot be reused as fresh.",
    }
    write_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("experiment", "data", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.experiment, args.data, args.output)))
