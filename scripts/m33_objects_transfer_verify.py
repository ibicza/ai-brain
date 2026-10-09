"""Verify retrieved expansion artifacts and isolated remote source against capsules."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import tarfile
from pathlib import Path

from m33_objects_data import sha, write_json

KEY = "C:/Users/artio/.ssh/id_ed25519_ai_brain_m192"
HOST = "ibicza@192.168.100.179"
ACCEPTED = "/home/ibicza/ai-brain/runs/m33-primary-relations-20261008-v5/experiment"
PREVIOUS_SHA = "a4a168a362f6afb20b9dc579ad91c47ca725ab0cbadb6a556a3d6e257e6c1fae"
POLICY_SHA = "21529d9cfd6e0b71f0fd58b6694dd3d32b7d680fd91d7bb002491c9c635591f6"


def verify(root, version, output):
    if version not in ("v1", "v2") or output.exists():
        raise ValueError("Explicit version and fresh receipt required")
    capsule = root / ("source-capsule-" + version + ".tgz")
    local = root / ("development-" + version)
    remote = (
        "/home/ibicza/ai-brain/runs/m33-primary-objects-expansion-20261009-" + version
    )
    if not local.is_dir():
        raise ValueError("Retrieved candidate directory required")
    expectations = {
        remote + "/capsule.tgz": sha(capsule),
        ACCEPTED + "/best.pt": PREVIOUS_SHA,
        ACCEPTED + "/frozen-calibration.json": POLICY_SHA,
    }
    with tarfile.open(capsule) as archive:
        manifest_blob = archive.extractfile("source-manifest.json").read()
        expectations[remote + "/source-manifest.json"] = hashlib.sha256(
            manifest_blob
        ).hexdigest()
        manifest = json.loads(manifest_blob)
        for entry in manifest["files"]:
            with archive.extractfile(entry["file"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                    raise ValueError("Local capsule corrupt")
            expectations[remote + "/" + entry["file"]] = entry["sha256"]
    local_paths = {}
    for path in sorted(local.rglob("*")):
        if path.is_file():
            if path.suffix not in (".json", ".pt", ".log"):
                raise ValueError("Unexpected retrieved artifact")
            remote_path = remote + "/" + path.relative_to(local).as_posix()
            expectations[remote_path] = sha(path)
            local_paths[remote_path] = str(path)
    # Fixed read-only command; filenames are argument data and shell quoted.
    source = "import sys,json,hashlib,pathlib; paths=json.load(sys.stdin); print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in paths}))"
    command = "/home/ibicza/ai-brain/.venv/bin/python -c " + shlex.quote(source)
    result = subprocess.run(
        [
            "ssh",
            "-i",
            KEY,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            HOST,
            command,
        ],
        check=True,
        capture_output=True,
        input=json.dumps(list(expectations)),
        text=True,
        encoding="utf-8",
    )
    actual = json.loads(result.stdout)
    if actual != expectations:
        raise ValueError("Local/remote source/artifact/accepted-checkpoint mismatch")
    receipt = {
        "schema": 1,
        "status": "VERIFIED_BYTE_IDENTICAL",
        "host": "karina",
        "version": version,
        "remote_root": remote,
        "capsule_sha256": sha(capsule),
        "accepted_checkpoint_unchanged": True,
        "accepted_policy_unchanged": True,
        "source_files_verified": len(manifest["files"]),
        "retrieved_files_verified": len(local_paths),
        "files": [
            {"remote_path": p, "local_path": local_paths.get(p), "sha256": s}
            for p, s in sorted(expectations.items())
        ],
    }
    write_json(output, receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--version", choices=("v1", "v2"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root, args.version, args.output)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "status",
                    "source_files_verified",
                    "retrieved_files_verified",
                    "accepted_checkpoint_unchanged",
                )
            }
        )
    )
