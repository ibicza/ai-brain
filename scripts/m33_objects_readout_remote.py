"""Predeclared 2x2 development experiment; known old final is never inferred here."""

import json
import os
import subprocess
from pathlib import Path

from m33_objects_context_probe_report import run as dev_photos
from m33_objects_data import sha, write_json
from m33_objects_select import select
from m33_primary_objects_pilot import POLICY_SHA, PREVIOUS_SHA

PYTHON = "/home/ibicza/ai-brain/.venv/bin/python"
WARM = "69788a227e95c7ed326f80f2bb3ba9d58d7ad171c2b6ac61d5b054ae7932d92f"
DATA = "c71dce559b11274b16aaf21bd9f0588e22fb5d7d99e4f7656437ef3bc9c9cf21"


def main():
    root = Path.cwd()
    manifest = json.loads((root / "source-manifest.json").read_text(encoding="utf-8"))
    anchors = {
        root / "warm.pt": WARM,
        root / "previous.pt": PREVIOUS_SHA,
        root / "previous-policy.json": POLICY_SHA,
        root / "data/dataset.json": DATA,
    }

    def protect():
        if any(sha(path) != digest for path, digest in anchors.items()):
            raise ValueError("Frozen own warm/core/data anchors changed")
        if any(sha(root / r["file"]) != r["sha256"] for r in manifest["files"]):
            raise ValueError("Frozen source capsule changed")

    protect()
    output = root / "development-v1"
    output.mkdir()
    trials = {
        "baseline_native": (False, False),
        "baseline_canvas": (False, True),
        "readout_native": (True, False),
        "readout_canvas": (True, True),
    }
    plan = {
        "trials": trials,
        "steps": 10000,
        "learning_rate": 0.00003,
        "round_id": 10971,
        "photo_fraction": 0.65,
        "dataset_sha256": DATA,
        "warm_sha256": WARM,
        "capsule_sha256": sha(root / "capsule.tgz"),
        "production_admitted": False,
        "selection": "Minimum same class/domain-balanced development loss, no calibration/final inference.",
        "limits": "Known curated training/development only; prior final now known and not read for predictions. Whole-frame canvas augmentation is not semantic foreground segmentation or new scene evidence. A separate fresh exam remains required before admission.",
    }
    write_json(output / "plan.json", plan)
    env = dict(
        os.environ,
        PYTHONPATH=str(root / "src") + ":" + str(root / "scripts"),
        AI_BRAIN_CAPSULE_SHA256=plan["capsule_sha256"],
        PYTHONIOENCODING="utf-8",
    )
    for name, (readout, canvas) in trials.items():
        args = [
            PYTHON,
            "scripts/m33_primary_objects_pilot.py",
            "--output",
            str(output / name),
            "--data",
            "data",
            "--previous",
            "previous.pt",
            "--previous-policy",
            "previous-policy.json",
            "--warm-start",
            "warm.pt",
            "--device",
            "cuda",
            "--protect-inherited",
            "--object-unknown-adapter",
            "--vision-extension-channels",
            "64",
            "--vision-extension-depth",
            "2",
            "--steps",
            "10000",
            "--eval-every",
            "500",
            "--round-id",
            "10971",
            "--learning-rate",
            ".00003",
            "--illustration-fraction",
            ".65",
            "--diversity-augmentation",
            "--domain-balanced-dev",
            "--class-domain-balanced-dev",
            "--development-only",
            "--evaluation-note",
            plan["limits"],
        ]
        if readout:
            args.append("--object-readout-adapter")
        if canvas:
            args.append("--background-augmentation")
        with (output / (name + ".log")).open("x", encoding="utf-8") as stream:
            code = subprocess.run(
                args, env=env, stdout=stream, stderr=subprocess.STDOUT, check=False
            ).returncode
        print(json.dumps({"candidate": name, "exit_code": code}), flush=True)
        protect()
        if code:
            raise RuntimeError("Development candidate failed: " + name)
    receipt = select(
        [output / name for name in trials],
        root / "selection-development-only.json",
        tuning=True,
    )
    print(
        json.dumps(
            {"winner": receipt["winner"]["name"], "selection_used": "DEVELOPMENT_ONLY"}
        ),
        flush=True,
    )
    diagnostic = dev_photos(
        root / "data", output, root / "dev-photo-diagnostic.json", ("warm", *trials)
    )
    write_json(root / "dev-photo-arithmetic-audit.json", diagnostic)
    protect()
    print(json.dumps(diagnostic), flush=True)


if __name__ == "__main__":
    main()
