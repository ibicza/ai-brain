"""Run a sealed own-weight continuation on the authorized notebook, using SSH key."""

import argparse
import hashlib
import json
import re
import shlex
import shutil
import stat
import sys
import time
from pathlib import Path

import paramiko
from m33_composition_package import build, sha


def run(args):
    if not re.fullmatch(r"m33-composition-\d{8}-v\d+", args.remote_name):
        raise ValueError("Explicit scoped run name required")
    root = args.output.resolve()
    if root.exists():
        raise ValueError("Fresh local continuation directory required")
    root.mkdir(parents=True)
    capsule = root / "source-capsule.tgz"
    manifest = build(args.repo.resolve(), capsule)
    shutil.copy2(args.previous, root / "previous.pt")
    shutil.copy2(args.warm_candidate, root / "warm-candidate.pt")
    remote = "/home/ibicza/ai-brain/runs/" + args.remote_name
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.connect(
        "192.168.100.179",
        username="ibicza",
        key_filename=str(args.key),
        look_for_keys=False,
        allow_agent=False,
        timeout=20,
    )

    def command(value):
        _, stdout, stderr = client.exec_command(value)
        for line in stdout:
            print(line.rstrip(), flush=True)
        error = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        if error:
            print(error.rstrip(), file=sys.stderr, flush=True)
        if code:
            raise RuntimeError(f"Remote command failed ({code})")

    try:
        sftp = client.open_sftp()
        sftp.mkdir(remote)
        for path in (capsule, root / "previous.pt", root / "warm-candidate.pt"):
            destination = remote + "/" + path.name
            sftp.put(str(path), destination, confirm=True)
            # Verify bytes over the independent SFTP read, before execution.
            with sftp.open(destination, "rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != sha(path):
                    raise ValueError("Remote input hash mismatch")
        unpack = "import tarfile; tarfile.open('source-capsule.tgz').extractall('.', filter='data')"
        python = "/home/ibicza/ai-brain/.venv/bin/python"
        prefix = (
            "cd "
            + shlex.quote(remote)
            + " && PYTHONPATH=src AI_BRAIN_CAPSULE_SHA256="
            + manifest["capsule_sha256"]
            + " "
            + python
            + " "
        )
        command(prefix + "-c " + shlex.quote(unpack))
        command(
            prefix
            + "-m pytest tests/test_primary_composition.py tests/test_primary_composition_pipeline.py tests/test_primary_composition_views.py tests/test_primary_composition_controls.py -q --junitxml=remote-tests.xml"
        )
        started = time.monotonic()
        command(
            prefix
            + "scripts/m33_primary_composition_pilot.py --previous previous.pt --warm-candidate warm-candidate.pt --output experiment --device cuda --dataset-profile "
            + args.dataset_profile
            + " --steps "
            + str(args.steps)
            + " --eval-every 600 --train-images "
            + str(args.train_images)
            + " --holdout-images "
            + str(args.holdout_images)
            + " --seed "
            + str(args.seed)
            + (" --spatial-readout" if args.spatial_readout else "")
            + (" --shape-edges" if args.shape_edges else "")
            + " --label-smoothing "
            + str(args.label_smoothing)
            + (" --reflection-consensus" if args.reflection_consensus else "")
            + " --auxiliary-images "
            + str(args.auxiliary_images)
            + " --consistency-loss "
            + str(args.consistency_loss)
        )
        command(
            prefix
            + "scripts/m33_composition_verify.py --root experiment --previous previous.pt --capsule source-capsule.tgz --output independent-arithmetic-replay.json --device cuda"
        )

        def pull(directory, local):
            local.mkdir(exist_ok=True)
            for entry in sftp.listdir_attr(directory):
                source = directory + "/" + entry.filename
                destination = local / entry.filename
                if stat.S_ISDIR(entry.st_mode):
                    pull(source, destination)
                elif stat.S_ISREG(entry.st_mode):
                    sftp.get(source, str(destination))
                    with sftp.open(source, "rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != sha(
                            destination
                        ):
                            raise ValueError("Downloaded evidence mismatch")
                else:
                    raise ValueError("Nonregular evidence file")

        pull(remote + "/experiment", root / "experiment")
        for name in ("remote-tests.xml", "independent-arithmetic-replay.json"):
            sftp.get(remote + "/" + name, str(root / name))
        receipt = {
            "status": "REMOTE_CONTINUATION_REPLAYED",
            "remote": remote,
            "source_capsule_sha256": manifest["capsule_sha256"],
            "previous_sha256": sha(root / "previous.pt"),
            "warm_candidate_sha256": sha(root / "warm-candidate.pt"),
            "elapsed_seconds": time.monotonic() - started,
            "production_admitted": False,
        }
        (root / "remote-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "output", "previous", "warm-candidate", "key"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--remote-name", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--steps", type=int, default=9000)
    parser.add_argument("--train-images", type=int, default=4500)
    parser.add_argument("--holdout-images", type=int, default=480)
    parser.add_argument("--spatial-readout", action="store_true")
    parser.add_argument("--shape-edges", action="store_true")
    parser.add_argument("--label-smoothing", type=float, default=0.0)
    parser.add_argument("--reflection-consensus", action="store_true")
    parser.add_argument("--auxiliary-images", type=int, default=0)
    parser.add_argument("--consistency-loss", type=float, default=0.0)
    parser.add_argument(
        "--dataset-profile", choices=("diverse", "diverse_clear"), default="diverse"
    )
    args = parser.parse_args()
    if min(args.steps, args.train_images, args.holdout_images) < 1:
        parser.error("Positive experiment sizes required")
    run(args)
