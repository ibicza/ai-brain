"""Persist the known background shortcut reproduction and its domain fix."""

import argparse
import hashlib
import json
from pathlib import Path

from ai_brain.training import primary_composition_rng_audit as audit_module


def run(output, seed):
    if output.exists():
        raise ValueError("Fresh immutable audit receipt required")
    old = audit_module.audit(seed=seed, independent_labels=False)
    fixed = audit_module.audit(seed=seed)
    old_zero = audit_module.audit_zero(independent_labels=False)
    fixed_zero = audit_module.audit_zero()
    if old["background_only_pattern_accuracy"] != [1.0, 1.0]:
        raise ValueError("Historical confound no longer reproduced")
    if not fixed["known_shortcut_absent"]:
        raise ValueError("Fix still exposes the known shortcut")
    if not fixed_zero["known_shortcut_absent"]:
        raise ValueError("Zero-class texture shortcut still exposed")
    repo = Path(__file__).resolve().parents[1]
    paths = [Path(__file__).resolve()] + [
        repo / "src/ai_brain/training" / name
        for name in (
            "primary_composition.py",
            "primary_composition_rng_audit.py",
            "primary_composition_controls.py",
            "primary_zero.py",
            "primary_relations.py",
        )
    ]
    report = {
        "schema": 1,
        "status": "KNOWN_RNG_SHORTCUT_REPRODUCED_AND_DOMAIN_SEPARATED",
        "archival_reproduction": old,
        "future_generator": fixed,
        "archival_zero_textured_transfer": old_zero,
        "future_zero_textured_transfer": fixed_zero,
        "interpretation": "High native pattern scores of historical V1-V7 are not proof of visual pattern understanding. Do not alter their frozen sources, weights or numerical results. Future scores need freshly generated domain-separated cohorts.",
        "sources": [
            {"file": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in paths
        ],
        "production_admitted": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "old_accuracy": old["background_only_pattern_accuracy"],
                "fixed_accuracy": fixed["background_only_pattern_accuracy"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=55150000)
    args = parser.parse_args()
    run(args.output.resolve(), args.seed)
