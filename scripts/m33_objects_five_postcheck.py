"""One post-selection known-cohort regression plus controlled prompt diagnostics."""

import json
import os
import subprocess
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_objects_five_iterations import DATA, PYTHON, TRIALS
from m33_verify_objects_evidence import verify


def main():
    root = Path.cwd()
    receipt = json.loads(
        (root / "selection-development-only.json").read_text(encoding="utf-8")
    )
    if len(receipt["iterations"]) != 5 or receipt["dataset_sha256"] != DATA:
        raise ValueError("All five iterations and frozen selection required")
    winner = receipt["winner"]
    checkpoint = (
        root / "warm.pt"
        if winner["name"] == "initial_warm"
        else root / "development-v1" / winner["name"] / "best.pt"
    )
    if sha(checkpoint) != winner["checkpoint_sha256"]:
        raise ValueError("Frozen winner bytes differ")
    env = dict(
        os.environ,
        PYTHONPATH=str(root / "src") + ":" + str(root / "scripts"),
        AI_BRAIN_CAPSULE_SHA256=sha(root / "capsule.tgz"),
        PYTHONIOENCODING="utf-8",
    )
    args = [
        PYTHON,
        "scripts/m33_primary_objects_pilot.py",
        "--output",
        "known-regression-evaluation",
        "--data",
        "data",
        "--previous",
        "previous.pt",
        "--previous-policy",
        "previous-policy.json",
        "--device",
        "cuda",
        "--protect-inherited",
        "--steps",
        "0",
        "--round-id",
        "10981",
        "--evaluate-checkpoint",
        str(checkpoint),
        "--selection-receipt",
        "selection-development-only.json",
        "--object-unknown-adapter",
        "--vision-extension-channels",
        "64",
        "--vision-extension-depth",
        "2",
        "--evaluation-note",
        "Known previously examined object cohorts. This is frozen post-selection regression, NOT fresh or blind acceptance; no subsequent selection from this result.",
    ]
    if winner["architecture"].get("object_readout_adapter", False):
        args.append("--object-readout-adapter")
    with (root / "postcheck.log").open("x", encoding="utf-8") as stream:
        subprocess.run(
            args, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True
        )
    write_json(
        root / "known-regression-arithmetic-audit.json",
        verify(root / "known-regression-evaluation", root / "data"),
    )
    # Supplemental diagnostic is frozen separately after the training capsule.
    from post_prompt_diagnostic import run

    controlled = run(root / "data", root, ("warm", *(t["name"] for t in TRIALS)))
    write_json(root / "controlled-prompt-arithmetic-audit.json", controlled)
    print(
        json.dumps(
            {
                "status": "FROZEN_KNOWN_REGRESSION_AND_CONTROLLED_PROMPTS_COMPLETED_NOT_FRESH_EXAM",
                "winner_checkpoint_sha256": winner["checkpoint_sha256"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
