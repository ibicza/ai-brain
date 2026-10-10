"""Run frozen-policy controls remotely in a fresh child, preserving parent evidence."""

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
from m33_composition_package import build, sha


def run(args):
    receipt = json.loads((args.reference / "remote-receipt.json").read_text())
    parent = receipt["remote"]
    if not re.fullmatch(
        r"/home/ibicza/ai-brain/runs/m33-composition-\d{8}-v\d+", parent
    ):
        raise ValueError("Explicit reference run required")
    root = (args.reference / "control-screen-v1").resolve()
    if root.exists():
        raise ValueError("Fresh control evidence child required")
    root.mkdir(parents=True)
    shutil.copy2(Path(__file__), root / "transport-executed.py")
    capsule = root / "source-capsule.tgz"
    manifest = build(args.repo.resolve(), capsule)
    remote = parent + "/control-screen-v1"
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
            raise RuntimeError(f"Remote controls failed ({code})")

    try:
        sftp = client.open_sftp()
        sftp.mkdir(remote)
        sftp.put(str(capsule), remote + "/source-capsule.tgz", confirm=True)
        with sftp.open(remote + "/source-capsule.tgz", "rb") as stream:
            if (
                hashlib.file_digest(stream, "sha256").hexdigest()
                != manifest["capsule_sha256"]
            ):
                raise ValueError("Control capsule transport hash differs")
        prefix = (
            "cd "
            + shlex.quote(remote)
            + " && PYTHONPATH=src:scripts /home/ibicza/ai-brain/.venv/bin/python "
        )
        unpack = "import tarfile; tarfile.open('source-capsule.tgz').extractall('.', filter='data')"
        command(prefix + "-c " + shlex.quote(unpack))
        command(
            prefix
            + "-m pytest tests/test_primary_composition_controls.py -q --junitxml=control-tests.xml"
        )
        command(
            prefix
            + "scripts/m33_composition_control_screen.py --reference .. --output controls --capsule source-capsule.tgz --device cuda --count "
            + str(args.count)
            + " --seed "
            + str(args.seed)
        )

        def pull(directory, local):
            local.mkdir(exist_ok=True)
            for entry in sftp.listdir_attr(directory):
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
                            raise ValueError("Control evidence download differs")
                else:
                    raise ValueError("Nonregular control evidence")

        pull(remote + "/controls", root / "controls")
        sftp.get(remote + "/control-tests.xml", str(root / "control-tests.xml"))
        output = {
            "status": "REMOTE_FIXED_POLICY_CONTROLS_REPLAYED",
            "remote": remote,
            "reference_remote": parent,
            "source_capsule_sha256": manifest["capsule_sha256"],
            "production_admitted": False,
        }
        (root / "remote-receipt.json").write_text(
            json.dumps(output, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(output), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "reference", "key"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--count", type=int, default=600)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    run(args)
