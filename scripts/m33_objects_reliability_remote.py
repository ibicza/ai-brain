"""Three predeclared photo-replay trials; development domains equally weighted."""

import json
import os
import subprocess
from pathlib import Path

from m33_objects_data import sha

ROOT = Path.cwd()
PYTHON = "/home/ibicza/ai-brain/.venv/bin/python"
PREVIOUS = "/home/ibicza/ai-brain/runs/m33-primary-relations-20261008-v5/experiment"
TRIALS = (
    ("photo35_lr1", "0.0001", "0.35"),
    ("photo65_lr1", "0.0001", "0.65"),
    ("photo65_lr3", "0.0003", "0.65"),
)


def main():
    manifest = json.loads((ROOT / "source-manifest.json").read_text())
    for entry in manifest["files"]:
        if sha(ROOT / entry["file"]) != entry["sha256"]:
            raise ValueError("Isolated source/data changed")
    if (
        sha(ROOT / "warm-start.pt")
        != "9f68aa1a3b51dfdef7d0624545d2d8226c46b9976f5bb8a430c20c0a1463415c"
    ):
        raise ValueError("Unexpected own warm start")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + ":" + str(ROOT / "scripts")
    env["AI_BRAIN_CAPSULE_SHA256"] = sha(ROOT / "capsule.tgz")
    jobs = []
    for name, rate, fraction in TRIALS:
        if (ROOT / name).exists() or (ROOT / (name + ".log")).exists():
            raise ValueError("Fresh candidate required")
        command = [
            PYTHON,
            "scripts/m33_primary_objects_pilot.py",
            "--output",
            name,
            "--data",
            "data",
            "--previous",
            PREVIOUS + "/best.pt",
            "--previous-policy",
            PREVIOUS + "/frozen-calibration.json",
            "--warm-start",
            "warm-start.pt",
            "--steps",
            "10000",
            "--round-id",
            "10931",
            "--learning-rate",
            rate,
            "--protect-inherited",
            "--object-unknown-adapter",
            "--vision-extension-channels",
            "64",
            "--vision-extension-depth",
            "2",
            "--illustration-fraction",
            fraction,
            "--diversity-augmentation",
            "--domain-balanced-dev",
            "--development-only",
            "--evaluation-note",
            "Known old controls never training. Photo artists own one predeclared partition. Development domains equally weighted. No calibration/final selection.",
        ]
        stream = (ROOT / (name + ".log")).open("x")
        jobs.append(
            (
                name,
                subprocess.Popen(
                    command, env=env, stdout=stream, stderr=subprocess.STDOUT
                ),
                stream,
            )
        )
    failed = []
    for name, process, stream in jobs:
        code = process.wait()
        stream.close()
        print(json.dumps({"candidate": name, "exit_code": code}), flush=True)
        if code:
            failed.append(name)
    if failed:
        raise RuntimeError("Failed candidates: " + str(failed))


if __name__ == "__main__":
    main()
