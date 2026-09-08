"""Native SSH transport and canonical tree streaming for M-33.6j."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    KarinaPrivateExecutionCapsule,
    KarinaRemoteCommandPlan,
    KarinaRemoteCommandReceipt,
    RemoteExecutableDependencyManifest,
    command_receipt,
    render_remote_command,
)

_SAFE_ARCHIVE_PATH = re.compile(r"[A-Za-z0-9_.@+() -]+(?:/[A-Za-z0-9_.@+() -]+)*\Z")


@dataclass(frozen=True)
class KarinaPrivateSshTransport:
    ssh_executable: Path
    endpoint: str
    identity_file: Path
    known_hosts_file: Path
    connect_timeout_seconds: int = 10


@dataclass(frozen=True)
class KarinaSshInvocationResult:
    stdout: bytes
    stderr: bytes
    command_receipt: KarinaRemoteCommandReceipt


def invoke_karina_command(
    *,
    transport: KarinaPrivateSshTransport,
    capsule: KarinaPrivateExecutionCapsule,
    plan: KarinaRemoteCommandPlan,
    dependency_manifest: RemoteExecutableDependencyManifest,
    stdin_payload: bytes = b"",
    check: bool = True,
) -> KarinaSshInvocationResult:
    """Invoke one typed command over non-interactive, strict-host-key SSH."""

    if bytes_hash(stdin_payload) != plan.stdin_payload_hash:
        raise ValueError("M336J SSH stdin differs from command plan")
    ssh = transport.ssh_executable.resolve(strict=True)
    identity = transport.identity_file.resolve(strict=True)
    known_hosts = transport.known_hosts_file.resolve(strict=True)
    if (
        not ssh.is_file()
        or not identity.is_file()
        or not known_hosts.is_file()
        or not 1 <= transport.connect_timeout_seconds <= 60
    ):
        raise ValueError("M336J private SSH transport is invalid")
    rendered = render_remote_command(plan, shell_executable=capsule.shell_executable)
    command = (
        str(ssh),
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "RequestTTY=no",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        f"ConnectTimeout={transport.connect_timeout_seconds}",
        "-i",
        str(identity),
        transport.endpoint,
        rendered,
    )
    completed = subprocess.run(
        command,
        input=stdin_payload,
        check=False,
        capture_output=True,
        env=_local_ssh_environment(),
    )
    receipt = command_receipt(
        plan=plan,
        dependency_manifest=dependency_manifest,
        exit_code=completed.returncode,
        response=completed.stdout,
    )
    result = KarinaSshInvocationResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        command_receipt=receipt,
    )
    if check and completed.returncode:
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return result


def parse_bound_json_response(
    raw: bytes,
    *,
    request_hash: str,
    component_binding_hash: str,
    host_identity_hash: str,
) -> dict:
    """Verify a canonical worker response without exposing transport details."""

    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("M336J remote response is not strict JSON") from error
    if not isinstance(value, dict):
        raise TypeError("M336J remote response must be an object")
    body = dict(value)
    claimed = body.pop("receipt_hash", None)
    if (
        content_hash(body) != claimed
        or value.get("request_hash") != request_hash
        or value.get("component_binding_hash") != component_binding_hash
        or value.get("host_identity_hash") != host_identity_hash
        or value.get("status") != "PASS"
    ):
        raise ValueError("M336J remote response binding changed")
    return value


def parse_framed_tree_response(
    raw: bytes,
    *,
    request_hash: str,
    component_binding_hash: str,
    host_identity_hash: str,
) -> tuple[dict, bytes]:
    header_raw, separator, payload = raw.partition(b"\n")
    if not separator:
        raise ValueError("M336J framed response lacks a header boundary")
    header = parse_bound_json_response(
        header_raw,
        request_hash=request_hash,
        component_binding_hash=component_binding_hash,
        host_identity_hash=host_identity_hash,
    )
    if header.get("payload_hash") != bytes_hash(payload) or header.get(
        "payload_size"
    ) != len(payload):
        raise ValueError("M336J framed response payload changed")
    return header, payload


def canonical_tree_archive(root: Path, *, prefix: str) -> bytes:
    """Create deterministic ZIP bytes for a private SSH stdin transfer."""

    source = root.resolve(strict=True)
    if not source.is_dir() or not _safe_archive_member(prefix):
        raise ValueError("M336J archive source or prefix is invalid")
    files = sorted(
        (path for path in source.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source).as_posix().encode("utf-8"),
    )
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True
    ) as archive:
        for path in files:
            relative = path.relative_to(source).as_posix()
            name = f"{prefix}/{relative}"
            if not _safe_archive_member(name):
                raise ValueError("M336J archive member is unsafe")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            info.flag_bits = 0x800
            archive.writestr(info, path.read_bytes())
    return output.getvalue()


def extract_canonical_tree_archive(
    payload: bytes,
    *,
    destination: Path,
    expected_payload_hash: str,
) -> tuple[int, str]:
    """Safely extract a fresh private tree with no external executable."""

    if bytes_hash(payload) != expected_payload_hash:
        raise ValueError("M336J transferred tree bytes changed")
    target = destination.resolve(strict=False)
    if target.exists():
        raise FileExistsError("M336J private transfer destination must be fresh")
    target.mkdir(parents=True)
    count = 0
    rows = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            names = tuple(info.filename for info in archive.infolist())
            if names != tuple(sorted(names, key=lambda item: item.encode("utf-8"))):
                raise ValueError("M336J transferred tree order is not canonical")
            if len(names) != len(set(names)):
                raise ValueError("M336J transferred tree contains duplicates")
            for info in archive.infolist():
                if info.is_dir() or not _safe_archive_member(info.filename):
                    raise ValueError("M336J transferred tree member is unsafe")
                relative = PurePosixPath(info.filename)
                output = target.joinpath(*relative.parts).resolve(strict=False)
                if not output.is_relative_to(target):
                    raise ValueError("M336J transferred tree escapes destination")
                output.parent.mkdir(parents=True, exist_ok=True)
                raw = archive.read(info)
                output.write_bytes(raw)
                rows.append((info.filename, len(raw), bytes_hash(raw)))
                count += 1
    except Exception:
        _remove_fresh_tree(target)
        raise
    return count, content_hash(tuple(rows))


def canonical_tree_export(root: Path) -> bytes:
    return canonical_tree_archive(root, prefix="payload")


def extract_canonical_tree_export(
    payload: bytes, *, destination: Path, expected_payload_hash: str
) -> tuple[int, str]:
    temporary = destination.with_name(destination.name + ".incoming")
    count, tree_hash = extract_canonical_tree_archive(
        payload,
        destination=temporary,
        expected_payload_hash=expected_payload_hash,
    )
    source = temporary / "payload"
    if not source.is_dir() or destination.exists():
        _remove_fresh_tree(temporary)
        raise ValueError("M336J exported tree wrapper is invalid")
    source.replace(destination)
    temporary.rmdir()
    return count, tree_hash


def canonical_json_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _safe_archive_member(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(
        value
        and _SAFE_ARCHIVE_PATH.fullmatch(value)
        and not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _remove_fresh_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink()
        else:
            path.rmdir()
    root.rmdir()


def _local_ssh_environment() -> dict[str, str]:
    # Windows OpenSSH needs ProgramData to resolve its system crypto/config
    # location even when every SSH identity and host-key input is explicit.
    allowed = ("SYSTEMROOT", "WINDIR", "PROGRAMDATA")
    return {name: os.environ[name] for name in allowed if name in os.environ}
