"""Matched short development probe; no calibration/final or production admission."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path.cwd()
PYTHON = "/home/ibicza/ai-brain/.venv/bin/python"
WARM_SHA = "f5d0c9b83d3b82ec512dc35ffe754338642178b7418f24de7b19574ea835205a"
DATA_SHA = "5c2f7780b37efe725e1842384f8d25e1514f7d81897dc75079907f847e4b7386"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    manifest = json.loads((ROOT / "source-manifest.json").read_text())
    for row in manifest["files"]:
        if sha(ROOT / row["file"]) != row["sha256"]:
            raise ValueError("Frozen source/data changed: " + row["file"])
    if sha(ROOT / "warm.pt") != WARM_SHA or sha(ROOT / "data/dataset.json") != DATA_SHA:
        raise ValueError("Probe warm/data mismatch")
    output = ROOT / "development-probe-v1"
    output.mkdir()
    plan = {
        "status": "SHORT_DEVELOPMENT_PROBE_NOT_FRESH_EXAM",
        "steps": 4000,
        "round_id": 10941,
        "learning_rate": 0.0001,
        "candidates": ["local_only", "global_context"],
        "warm_sha256": WARM_SHA,
        "dataset_sha256": DATA_SHA,
        "calibration_final_predictions_forbidden": True,
        "production_admitted": False,
    }
    with (output / "plan.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + ":" + str(ROOT / "scripts")
    env["AI_BRAIN_CAPSULE_SHA256"] = sha(ROOT / "capsule.tgz")
    env["PYTHONIOENCODING"] = "utf-8"
    jobs = []
    for name in plan["candidates"]:
        command = [
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
            "--steps",
            "4000",
            "--eval-every",
            "500",
            "--round-id",
            "10941",
            "--device",
            "cuda",
            "--protect-inherited",
            "--vision-extension-channels",
            "64",
            "--vision-extension-depth",
            "2",
            "--object-unknown-adapter",
            "--warm-start",
            "warm.pt",
            "--diversity-augmentation",
            "--illustration-fraction",
            ".35",
            "--domain-balanced-dev",
            "--learning-rate",
            ".0001",
            "--development-only",
            "--evaluation-note",
            "Known parent development only; no new photo final opened or training admitted.",
        ]
        if name == "global_context":
            command.append("--vision-global-context")
        log = (output / (name + ".log")).open("x")
        jobs.append(
            (
                name,
                subprocess.Popen(
                    command, env=env, stdout=log, stderr=subprocess.STDOUT
                ),
                log,
            )
        )
    exits = {}
    for name, process, log in jobs:
        exits[name] = process.wait()
        log.close()
    with (output / "exitcodes.json").open("x") as stream:
        json.dump(exits, stream, indent=2)
    print(json.dumps(exits), flush=True)
    if any(exits.values()):
        raise SystemExit(1)
    for row in manifest["files"]:
        if sha(ROOT / row["file"]) != row["sha256"]:
            raise ValueError("Frozen source/data changed after probe")
    if sha(ROOT / "warm.pt") != WARM_SHA:
        raise ValueError("Probe warm bytes changed")


if __name__ == "__main__":
    main()
