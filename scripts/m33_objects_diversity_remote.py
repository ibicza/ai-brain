"""Three predeclared own-weight development-only trials in an isolated capsule."""

import json
import os
import subprocess
from pathlib import Path

from m33_objects_data import sha

ROOT = Path.cwd()
PYTHON = "/home/ibicza/ai-brain/.venv/bin/python"
PREVIOUS = "/home/ibicza/ai-brain/runs/m33-primary-relations-20261008-v5/experiment"
TRIALS = (
    ("plain_lr1", "0.0001", False, "0"),
    ("diverse_lr1", "0.0001", True, "0.35"),
    ("diverse_lr3", "0.0003", True, "0.35"),
)


def main():
    manifest = json.loads((ROOT / "source-manifest.json").read_text())
    for entry in manifest["files"]:
        if sha(ROOT / entry["file"]) != entry["sha256"]:
            raise ValueError("Isolated source/data changed before training")
    if (
        sha(ROOT / "warm-start.pt")
        != "cdc3187ebcc127824fa7e5a4bbf35751ae26fad1d8dbeb68a71633ded4b8f272"
    ):
        raise ValueError("Unexpected warm-start own checkpoint")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + ":" + str(ROOT / "scripts")
    env["AI_BRAIN_CAPSULE_SHA256"] = sha(ROOT / "capsule.tgz")
    jobs = []
    for name, rate, diversity, fraction in TRIALS:
        if (ROOT / name).exists() or (ROOT / (name + ".log")).exists():
            raise ValueError("Fresh candidate outputs required")
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
            "10921",
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
            "--development-only",
            "--evaluation-note",
            "All previous finals only regression. OpenMoji reserved final; no final or calibration selection.",
        ]
        if diversity:
            command.append("--diversity-augmentation")
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
