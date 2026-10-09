"""Short matched own-weight width probe on known parent development data only.

This does not admit the pending new photos or certify a fresh final gate.
"""

import json
import os
import subprocess
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_primary_objects_pilot import POLICY_SHA, PREVIOUS_SHA

WARM_SHA = "f5d0c9b83d3b82ec512dc35ffe754338642178b7418f24de7b19574ea835205a"
DATA_SHA = "5c2f7780b37efe725e1842384f8d25e1514f7d81897dc75079907f847e4b7386"
PYTHON = "/home/ibicza/ai-brain/.venv/bin/python"


def main():
    root = Path.cwd()
    manifest = json.loads((root / "source-manifest.json").read_text())
    anchors = {
        root / "warm.pt": WARM_SHA,
        root / "previous.pt": PREVIOUS_SHA,
        root / "previous-policy.json": POLICY_SHA,
        root / "data/dataset.json": DATA_SHA,
    }

    def verify():
        for row in manifest["files"]:
            if sha(root / row["file"]) != row["sha256"]:
                raise ValueError("Frozen source/data changed: " + row["file"])
        if any(sha(path) != digest for path, digest in anchors.items()):
            raise ValueError("Capacity probe anchor mismatch")

    verify()
    output = root / "capacity-probe-v1"
    output.mkdir()
    plan = {
        "status": "SHORT_KNOWN_DATA_DEVELOPMENT_PROBE_NOT_FRESH_EXAM",
        "steps": 4000,
        "round_id": 10951,
        "learning_rate": 0.0001,
        "photo_fraction": 0.35,
        "candidates": {"vision64": 64, "vision128": 128},
        "warm_sha256": WARM_SHA,
        "dataset_sha256": DATA_SHA,
        "capsule_sha256": sha(root / "capsule.tgz"),
        "calibration_final_predictions_forbidden": True,
        "production_admitted": False,
        "pending_new_photos_admitted": False,
        "limits": "Known parent dev photos have incomplete eight-name coverage. This checks width migration, resources and diagnostic development behavior only. No checkpoint promotion or safe-recognition claim.",
    }
    write_json(output / "plan.json", plan)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + ":" + str(root / "scripts")
    env["AI_BRAIN_CAPSULE_SHA256"] = plan["capsule_sha256"]
    env["PYTHONIOENCODING"] = "utf-8"
    exits = {}
    # Sequential candidates avoid unnecessary GPU pressure from the wide model.
    for name, channels in plan["candidates"].items():
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
            "10951",
            "--device",
            "cuda",
            "--protect-inherited",
            "--vision-extension-channels",
            str(channels),
            "--vision-extension-depth",
            "2",
            "--object-unknown-adapter",
            "--warm-start",
            "warm.pt",
            "--diversity-augmentation",
            "--illustration-fraction",
            ".35",
            "--domain-balanced-dev",
            "--class-domain-balanced-dev",
            "--learning-rate",
            ".0001",
            "--development-only",
            "--evaluation-note",
            "Known parent development data only; pending top-up photos never trained. Matched width probe, no calibration/final and no production admission.",
        ]
        with (output / (name + ".log")).open("x") as stream:
            exits[name] = subprocess.run(
                command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=False
            ).returncode
        print(json.dumps({"candidate": name, "exit_code": exits[name]}), flush=True)
        verify()
        if exits[name]:
            break
    write_json(output / "exitcodes.json", exits)
    if any(exits.values()) or len(exits) != 2:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
