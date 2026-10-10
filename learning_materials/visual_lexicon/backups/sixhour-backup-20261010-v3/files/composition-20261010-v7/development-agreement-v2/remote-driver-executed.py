"""Run a frozen-source, development-only agreement study on the own notebook."""

import argparse
import hashlib
import json
import re
import shlex
import shutil
import stat
from pathlib import Path

import paramiko


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(key, reference, output, study):
    if (
        not re.fullmatch(r"m33-composition-\d{8}-v\d+", reference)
        or not re.fullmatch(r"development-agreement-v\d+", study)
        or output.exists()
    ):
        raise ValueError("Fresh scoped study/reference required")
    output.mkdir(parents=True)
    source = Path(__file__).with_name("m33_composition_dev_probe.py")
    shutil.copy2(source, output / "diagnostic-input.py")
    shutil.copy2(__file__, output / "remote-driver-executed.py")
    source_hash = sha(output / "diagnostic-input.py")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.connect(
        "192.168.100.179",
        username="ibicza",
        key_filename=str(key),
        look_for_keys=False,
        allow_agent=False,
        timeout=20,
    )
    remote_ref = "/home/ibicza/ai-brain/runs/" + reference
    remote = remote_ref + "/" + study
    python = "/home/ibicza/ai-brain/.venv/bin/python"
    try:
        sftp = client.open_sftp()
        sftp.mkdir(remote)
        uploaded = remote + "/diagnostic-input.py"
        sftp.put(str(output / "diagnostic-input.py"), uploaded, confirm=True)
        with sftp.open(uploaded, "rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != source_hash:
                raise ValueError("Study source upload differs")
        command = " ".join(
            shlex.quote(x)
            for x in (
                python,
                uploaded,
                "--reference",
                remote_ref,
                "--output",
                remote + "/probe",
                "--device",
                "cuda",
            )
        )
        _, stdout, stderr = client.exec_command(command)
        for line in stdout:
            print(line.rstrip(), flush=True)
        error = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        (output / "remote-output.log").write_text(error, encoding="utf-8")
        # Original source capsule already exists locally/remotely and is hash
        # checked by the study. Do not copy its unpacked cache a third time.
        for entry in sftp.listdir_attr(remote + "/probe"):
            if not stat.S_ISREG(entry.st_mode):
                continue
            path = remote + "/probe/" + entry.filename
            destination = output / entry.filename
            if destination.exists():
                raise ValueError("Remote artifact would overwrite local study input")
            sftp.get(path, str(destination))
            script = "import hashlib,sys; print(hashlib.file_digest(open(sys.argv[1], 'rb'), 'sha256').hexdigest())"
            _, check, check_error = client.exec_command(
                python + " -c " + shlex.quote(script) + " " + shlex.quote(path)
            )
            digest = check.read().decode("ascii").strip()
            if (
                check.channel.recv_exit_status()
                or check_error.read()
                or digest != sha(destination)
            ):
                raise ValueError("Downloaded development evidence differs")
        receipt = {
            "status": "REMOTE_DEVELOPMENT_STUDY_REPLAYED"
            if code == 0
            else "REMOTE_DEVELOPMENT_STUDY_FAILED",
            "remote": remote,
            "executed_source_sha256": source_hash,
            "exit_code": code,
            "training_or_calibration": False,
            "production_admitted": False,
        }
        (output / "remote-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        if code:
            raise RuntimeError("Remote development study failed: " + error)
        report = json.loads((output / "result.json").read_text(encoding="utf-8"))
        if report["executed_script_sha256"] != source_hash:
            raise ValueError("Study did not use the pinned script")
        print(json.dumps(receipt), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--study", required=True)
    args = parser.parse_args()
    run(args.key.resolve(), args.reference, args.output.resolve(), args.study)
