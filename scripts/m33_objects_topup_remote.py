"""Frozen fresh-photo iteration: matched development trials, then one final run.

No production activation. Candidate choice precedes calibration/final inference;
the training data and safety gates are never weakened to obtain a passing score.
"""

import json
import os
import subprocess
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_objects_domain_diagnostics import diagnose
from m33_objects_select import select
from m33_primary_objects_pilot import POLICY_SHA, PREVIOUS_SHA
from m33_verify_objects_evidence import verify

PYTHON = "/home/ibicza/ai-brain/.venv/bin/python"
WARM_SHA = "f5d0c9b83d3b82ec512dc35ffe754338642178b7418f24de7b19574ea835205a"
PARENT_SHA = "5c2f7780b37efe725e1842384f8d25e1514f7d81897dc75079907f847e4b7386"


def main():
    root = Path.cwd()
    manifest = json.loads((root / "source-manifest.json").read_text())
    data = json.loads((root / "data/dataset.json").read_text())
    if (
        data["parent_dataset_sha256"] != PARENT_SHA
        or not data["photo_coverage_pretraining"]["ready"]
    ):
        raise ValueError("Fresh reviewed photo coverage and protected parent required")
    anchors = {
        root / "warm.pt": WARM_SHA,
        root / "previous.pt": PREVIOUS_SHA,
        root / "previous-policy.json": POLICY_SHA,
    }

    def check_inputs():
        for entry in manifest["files"]:
            if sha(root / entry["file"]) != entry["sha256"]:
                raise ValueError("Frozen source/data changed: " + entry["file"])
        if any(sha(path) != digest for path, digest in anchors.items()):
            raise ValueError("Own weight/policy anchor changed")

    check_inputs()
    output = root / "development-v1"
    output.mkdir()
    plan = {
        "candidates": {"vision64": 64, "vision128": 128},
        "steps": 10000,
        "eval_every": 500,
        "learning_rate": 0.0001,
        "round_id": 10961,
        "photo_fraction": 0.65,
        "diversity_augmentation": True,
        "domain_balanced_dev": True,
        "class_domain_balanced_dev": True,
        "dataset_sha256": sha(root / "data/dataset.json"),
        "capsule_sha256": sha(root / "capsule.tgz"),
        "warm_start_sha256": WARM_SHA,
        "production_admitted": False,
        "limits": "Curated nonblind photo examination, not independent semantic truth. Old final rows are known regression, never training. Equal settings and source corpus for both widths. Final never selects candidates or changes policy.",
    }
    write_json(output / "plan.json", plan)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + ":" + str(root / "scripts")
    env["AI_BRAIN_CAPSULE_SHA256"] = plan["capsule_sha256"]
    env["PYTHONIOENCODING"] = "utf-8"

    def command(path, channels, steps):
        return [
            PYTHON,
            "scripts/m33_primary_objects_pilot.py",
            "--output",
            str(path),
            "--data",
            "data",
            "--previous",
            "previous.pt",
            "--previous-policy",
            "previous-policy.json",
            "--device",
            "cuda",
            "--protect-inherited",
            "--object-unknown-adapter",
            "--vision-extension-channels",
            str(channels),
            "--vision-extension-depth",
            "2",
            "--steps",
            str(steps),
            "--eval-every",
            "500",
            "--round-id",
            "10961",
            "--learning-rate",
            ".0001",
            "--evaluation-note",
            plan["limits"],
        ]

    for name, channels in plan["candidates"].items():
        args = command(output / name, channels, 10000) + [
            "--warm-start",
            "warm.pt",
            "--diversity-augmentation",
            "--illustration-fraction",
            ".65",
            "--domain-balanced-dev",
            "--class-domain-balanced-dev",
            "--development-only",
        ]
        with (output / (name + ".log")).open("x") as stream:
            code = subprocess.run(
                args, env=env, stdout=stream, stderr=subprocess.STDOUT, check=False
            ).returncode
        print(json.dumps({"candidate": name, "exit_code": code}), flush=True)
        check_inputs()
        if code:
            raise RuntimeError("Development candidate failed: " + name)
    selection = root / "selection-frozen.json"
    receipt = select(
        [output / name for name in plan["candidates"]], selection, tuning=True
    )
    # This receipt is durably written before any held-out prediction is made.
    print(
        json.dumps(
            {"winner": receipt["winner"]["name"], "selection_used": "DEVELOPMENT_ONLY"}
        ),
        flush=True,
    )
    winner = receipt["winner"]
    args = command(
        root / "final-evaluation",
        winner["architecture"]["vision_extension_channels"],
        0,
    ) + [
        "--evaluate-checkpoint",
        str(output / winner["name"] / "best.pt"),
        "--selection-receipt",
        str(selection),
    ]
    with (root / "final-evaluation.log").open("x") as stream:
        code = subprocess.run(
            args, env=env, stdout=stream, stderr=subprocess.STDOUT, check=False
        ).returncode
    if code:
        raise RuntimeError("Frozen evaluation failed")
    check_inputs()
    write_json(
        root / "arithmetic-audit.json", verify(root / "final-evaluation", root / "data")
    )
    diagnose(root / "final-evaluation", root / "data", root / "domain-diagnostic.json")
    print(
        json.dumps(
            json.loads((root / "final-evaluation/report.json").read_text())["status"]
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
