"""Run fresh cold-family controls remotely against original frozen inference."""

import argparse
import hashlib
import json
import re
import shlex
import shutil
import stat
import sys
from pathlib import Path

import paramiko

SCREEN_CHILDREN = (
    "cold-family-screen-v1",
    "cold-family-screen-v2",
    "source-control-screen-v1",
    "source-control-screen-v2",
    "source-control-screen-v3",
    "source-control-screen-v4",
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args):
    prepared_source = getattr(args, "prepared_source", None)
    receipt = json.loads((args.reference / "remote-receipt.json").read_text())
    parent = receipt["remote"]
    if receipt["status"] != "REMOTE_CONTINUATION_REPLAYED" or not re.fullmatch(
        r"/home/ibicza/ai-brain/runs/m33-composition-\d{8}-v\d+", parent
    ):
        raise ValueError("Completed explicit remote reference required")
    if (
        args.child not in SCREEN_CHILDREN
        or args.child.startswith("source-control-") != (prepared_source is not None)
        or type(args.count) is not int
        or not 12 <= args.count <= 6000
        or type(args.seed) is not int
        or args.seed < 0
    ):
        raise ValueError("Scoped fresh bounded cold screen required")
    root = (args.reference / args.child).resolve()
    if root.exists():
        raise ValueError("Fresh local cold screen required")
    capsule_sha = sha(args.reference / "source-capsule.tgz")
    if capsule_sha != receipt["source_capsule_sha256"]:
        raise ValueError("Local completed source archive changed")
    root.mkdir(parents=True)
    shutil.copy2(__file__, root / "transport-executed.py")
    transport_sha = sha(root / "transport-executed.py")
    inputs = root / "input-sources"
    inputs.mkdir()
    scripts = {}
    script_names = (
        "m33_composition_novel_controls.py",
        "m33_composition_novel_screen.py",
    ) + (("m33_composition_source_dataset.py",) if prepared_source is not None else ())
    for name in script_names:
        original = args.repo / "scripts" / name
        before = sha(original)
        shutil.copy2(original, inputs / name)
        if before != sha(original) or before != sha(inputs / name):
            raise ValueError("Cold source changed during snapshot")
        scripts[name] = before
    source_inputs = {}
    if prepared_source is not None:
        copied_sources = root / "prepared-source"
        copied_sources.mkdir()
        for name in (
            "source-annotations.json",
            "dataset.npz",
            "records.json.gz",
            "source-crops.npz",
            "preparation-freeze.json",
            "preparation-executed.py",
            "preparation-receipt.json",
        ):
            original = prepared_source / name
            before = sha(original)
            shutil.copy2(original, copied_sources / name)
            if before != sha(original) or before != sha(copied_sources / name):
                raise ValueError("Prepared source changed during transport snapshot")
            source_inputs[name] = before
    (root / "transport-inputs.json").write_text(
        json.dumps(
            {
                "scripts": scripts,
                "source_inputs": source_inputs,
                "original_capsule_sha256": capsule_sha,
                "count": args.count,
                "seed": args.seed,
                "production_admitted": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    remote = parent + "/" + args.child
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
            raise RuntimeError(f"Remote cold screen failed ({code})")

    try:
        sftp = client.open_sftp()
        with sftp.open(parent + "/source-capsule.tgz", "rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != capsule_sha:
                raise ValueError("Remote original inference archive differs")
        sftp.mkdir(remote)
        sftp.mkdir(remote + "/scripts")
        for name, digest in scripts.items():
            destination = remote + "/scripts/" + name
            sftp.put(str(inputs / name), destination, confirm=True)
            with sftp.open(destination, "rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise ValueError("Remote cold source differs")
        if prepared_source is not None:
            sftp.mkdir(remote + "/prepared-source")
            for name, digest in source_inputs.items():
                destination = remote + "/prepared-source/" + name
                sftp.put(
                    str(root / "prepared-source" / name), destination, confirm=True
                )
                with sftp.open(destination, "rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                        raise ValueError("Prepared source transport differs")
        prefix = (
            "cd " + shlex.quote(remote) + " && /home/ibicza/ai-brain/.venv/bin/python "
        )
        command(
            prefix
            + "scripts/m33_composition_novel_screen.py --reference .. --output controls --device cuda --count "
            + str(args.count)
            + " --seed "
            + str(args.seed)
            + (
                " --prepared-source prepared-source"
                if prepared_source is not None
                else ""
            )
        )

        def pull(directory, local):
            local.mkdir(exist_ok=False)
            for entry in sftp.listdir_attr(directory):
                if entry.filename == "frozen-source":
                    # Original parent capsule is preserved; no duplicate unpack.
                    continue
                source, destination = (
                    directory + "/" + entry.filename,
                    local / entry.filename,
                )
                if stat.S_ISDIR(entry.st_mode):
                    pull(source, destination)
                elif stat.S_ISREG(entry.st_mode):
                    sftp.get(source, str(destination))
                    with sftp.open(source, "rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != sha(
                            destination
                        ):
                            raise ValueError("Cold downloaded evidence differs")
                else:
                    raise ValueError("Nonregular cold evidence rejected")

        pull(remote + "/controls", root / "controls")
        artifact_manifest = json.loads(
            (root / "controls/artifact-manifest.json").read_text()
        )
        for entry in artifact_manifest["files"]:
            path = root / "controls" / entry["file"]
            if path.parent != root / "controls" or sha(path) != entry["sha256"]:
                raise ValueError("Cold artifact manifest differs")
        frozen = json.loads((root / "controls/preregistered-freeze.json").read_text())
        expected_hashes = {
            parent + "/source-capsule.tgz": capsule_sha,
            parent + "/previous.pt": sha(args.reference / "previous.pt"),
        }
        parent_freeze = json.loads(
            (args.reference / "experiment/candidate-freeze.json").read_text()
        )
        schedule = parent_freeze["winner"]["schedule"]
        expected_hashes[parent + "/experiment/" + schedule + "/best.pt"] = (
            parent_freeze["winner"]["checkpoint_sha256"]
        )
        for name in (
            "protocol.json",
            "candidate-freeze.json",
            "policy-frozen.json",
            "result.json",
            "dataset-records.json.gz",
        ):
            expected_hashes[parent + "/experiment/" + name] = sha(
                args.reference / "experiment" / name
            )
        if (
            frozen["reference_hashes"] != expected_hashes
            or frozen["count"] != args.count
            or frozen["seed"] != args.seed
            or frozen["training_or_calibration"]
        ):
            raise ValueError("Cold reference inputs differ from local originals")
        if frozen["screen_source_hashes"] != {
            remote + "/scripts/" + name: digest for name, digest in scripts.items()
        }:
            raise ValueError("Cold executed screen source differs")
        if frozen["source_preparation_hashes"] != {
            remote + "/prepared-source/" + name: digest
            for name, digest in source_inputs.items()
        } or frozen["group_kind"] != (
            "source_asset" if prepared_source is not None else "shape_family"
        ):
            raise ValueError("Executed assessment source inputs differ")
        if sha(Path(__file__)) != transport_sha:
            raise ValueError("Cold transport changed during execution")
        report = {
            "status": "REMOTE_FROZEN_SOURCE_CONTROLS_REPLAYED"
            if prepared_source is not None
            else "REMOTE_COLD_FAMILY_CONTROLS_REPLAYED",
            "remote": remote,
            "reference_remote": parent,
            "original_capsule_sha256": capsule_sha,
            "transport_executed_sha256": transport_sha,
            "screen_source_hashes": scripts,
            "source_inputs": source_inputs,
            "controls_result_sha256": sha(root / "controls/result.json"),
            "production_admitted": False,
        }
        (root / "remote-receipt.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "reference", "key"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--child",
        choices=SCREEN_CHILDREN,
        default="cold-family-screen-v1",
    )
    parser.add_argument("--count", type=int, default=600)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--prepared-source", type=Path)
    run(parser.parse_args())
