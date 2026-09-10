"""Bounded SSH transport and deterministic file-backed trees for M-33.6j."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
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
M336J_STREAM_CHUNK_BYTES = 1024 * 1024
M336J_SMALL_IN_MEMORY_LIMIT = 8 * 1024 * 1024
M336J_SMALL_JSON_LIMIT = 4 * 1024 * 1024
M336J_DEFAULT_MAXIMUM_TRANSFER_BYTES = 1024**3
M336J_DEFAULT_MAXIMUM_FILE_COUNT = 100_000
M336J_MAXIMUM_STDERR_BYTES = 1024 * 1024


@dataclass(frozen=True)
class KarinaPrivateSshTransport:
    ssh_executable: Path
    endpoint: str
    identity_file: Path
    known_hosts_file: Path
    connect_timeout_seconds: int = 10


@dataclass(frozen=True)
class M336JTreeTransferLimits:
    maximum_archive_bytes: int = M336J_DEFAULT_MAXIMUM_TRANSFER_BYTES
    maximum_unpacked_bytes: int = M336J_DEFAULT_MAXIMUM_TRANSFER_BYTES
    maximum_file_count: int = M336J_DEFAULT_MAXIMUM_FILE_COUNT
    chunk_bytes: int = M336J_STREAM_CHUNK_BYTES


M336J_DEFAULT_TREE_TRANSFER_LIMITS = M336JTreeTransferLimits()


@dataclass(frozen=True)
class M336JFileBackedTreeArtifact:
    private_path: Path
    archive_hash: str
    archive_size: int
    file_count: int
    unpacked_size: int
    portable_tree_hash: str


@dataclass(frozen=True)
class KarinaSshInvocationResult:
    stdout: bytes
    stderr: bytes
    command_receipt: KarinaRemoteCommandReceipt


@dataclass(frozen=True)
class KarinaStreamingInvocationResult:
    stdout_path: Path
    stdout_hash: str
    stdout_size: int
    stderr: bytes
    stderr_truncated: bool
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
    """Invoke one bounded JSON command over strict non-interactive SSH."""

    if len(stdin_payload) > M336J_SMALL_JSON_LIMIT:
        raise ValueError("M336J in-memory SSH payload exceeds the bounded JSON limit")
    if (
        bytes_hash(stdin_payload) != plan.stdin_payload_hash
        or len(stdin_payload) != plan.stdin_payload_size
    ):
        raise ValueError("M336J SSH stdin differs from command plan")
    command = _ssh_command(transport=transport, capsule=capsule, plan=plan)
    completed = subprocess.run(
        command,
        input=stdin_payload,
        check=False,
        capture_output=True,
        env=_local_ssh_environment(),
    )
    if (
        len(completed.stdout) > M336J_SMALL_JSON_LIMIT
        or len(completed.stderr) > M336J_MAXIMUM_STDERR_BYTES
    ):
        raise ValueError("M336J bounded SSH response limit exceeded")
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


def invoke_karina_command_streaming(
    *,
    transport: KarinaPrivateSshTransport,
    capsule: KarinaPrivateExecutionCapsule,
    plan: KarinaRemoteCommandPlan,
    dependency_manifest: RemoteExecutableDependencyManifest,
    stdin_path: Path,
    stdout_path: Path,
    maximum_stderr_bytes: int = M336J_MAXIMUM_STDERR_BYTES,
    check: bool = True,
) -> KarinaStreamingInvocationResult:
    """Stream binary stdin/stdout through files while retaining bounded stderr."""

    source = stdin_path.resolve(strict=True)
    destination = stdout_path.resolve(strict=False)
    if not source.is_file() or destination.exists() or source == destination:
        raise ValueError("M336J streaming transport paths are invalid")
    if source.stat().st_size != plan.stdin_payload_size:
        raise ValueError("M336J streamed stdin size differs from command plan")
    if hash_file(source) != plan.stdin_payload_hash:
        raise ValueError("M336J streamed stdin hash differs from command plan")
    if not 1 <= maximum_stderr_bytes <= 16 * 1024 * 1024:
        raise ValueError("M336J stderr bound is invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = _ssh_command(transport=transport, capsule=capsule, plan=plan)
    captured = bytearray()
    truncated = False

    def drain_stderr(pipe) -> None:
        nonlocal truncated
        while True:
            chunk = pipe.read(M336J_STREAM_CHUNK_BYTES)
            if not chunk:
                break
            remaining = maximum_stderr_bytes - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True

    try:
        with source.open("rb") as stdin, destination.open("xb") as stdout:
            process = subprocess.Popen(
                command,
                stdin=stdin,
                stdout=stdout,
                stderr=subprocess.PIPE,
                env=_local_ssh_environment(),
            )
            if process.stderr is None:
                raise RuntimeError("M336J SSH stderr pipe is unavailable")
            thread = threading.Thread(target=drain_stderr, args=(process.stderr,))
            thread.start()
            exit_code = process.wait()
            thread.join()
            stdout.flush()
            os.fsync(stdout.fileno())
        response_size = destination.stat().st_size
        response_hash = hash_file(destination)
        receipt = command_receipt(
            plan=plan,
            dependency_manifest=dependency_manifest,
            exit_code=exit_code,
            response_hash=response_hash,
            response_size=response_size,
        )
        result = KarinaStreamingInvocationResult(
            stdout_path=destination,
            stdout_hash=response_hash,
            stdout_size=response_size,
            stderr=bytes(captured),
            stderr_truncated=truncated,
            command_receipt=receipt,
        )
        if check and exit_code:
            raise subprocess.CalledProcessError(
                exit_code, command, output=None, stderr=bytes(captured)
            )
        return result
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def parse_bound_json_response(
    raw: bytes,
    *,
    request_hash: str,
    component_binding_hash: str,
    host_identity_hash: str,
) -> dict:
    """Verify a canonical bounded worker response."""

    if len(raw) > M336J_SMALL_JSON_LIMIT:
        raise ValueError("M336J remote JSON response exceeds its bound")
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
    """Legacy small-fixture frame parser with an explicit memory limit."""

    if len(raw) > M336J_SMALL_IN_MEMORY_LIMIT:
        raise ValueError("M336J in-memory framed response exceeds its small limit")
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


def parse_framed_tree_response_file(
    response_path: Path,
    *,
    payload_path: Path,
    request_hash: str,
    component_binding_hash: str,
    host_identity_hash: str,
    limits: M336JTreeTransferLimits = M336J_DEFAULT_TREE_TRANSFER_LIMITS,
) -> dict:
    """Split a streamed header/archive response without materializing the archive."""

    source = response_path.resolve(strict=True)
    destination = payload_path.resolve(strict=False)
    _verify_limits(limits)
    if destination.exists() or source == destination:
        raise ValueError("M336J framed response paths are invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    digest = hashlib.sha256()
    try:
        with source.open("rb") as incoming:
            header_raw = incoming.readline(M336J_SMALL_JSON_LIMIT + 1)
            if (
                not header_raw.endswith(b"\n")
                or len(header_raw) > M336J_SMALL_JSON_LIMIT
            ):
                raise ValueError("M336J streamed response header is invalid")
            header = parse_bound_json_response(
                header_raw[:-1],
                request_hash=request_hash,
                component_binding_hash=component_binding_hash,
                host_identity_hash=host_identity_hash,
            )
            with destination.open("xb") as output:
                while True:
                    chunk = incoming.read(limits.chunk_bytes)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limits.maximum_archive_bytes:
                        raise ValueError(
                            "M336J streamed response archive exceeds its bound"
                        )
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        if (
            header.get("payload_hash") != digest.hexdigest()
            or header.get("payload_size") != total
        ):
            raise ValueError("M336J streamed response payload changed")
        return header
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def write_canonical_tree_archive(
    root: Path,
    archive_path: Path,
    *,
    prefix: str,
    limits: M336JTreeTransferLimits = M336J_DEFAULT_TREE_TRANSFER_LIMITS,
) -> M336JFileBackedTreeArtifact:
    """Write a deterministic ZIP_STORED tree through bounded chunks."""

    _verify_limits(limits)
    source = root.resolve(strict=True)
    output = archive_path.resolve(strict=False)
    if not source.is_dir() or not _safe_archive_member(prefix) or output.exists():
        raise ValueError("M336J archive source, prefix, or destination is invalid")
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(
        (path for path in source.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source).as_posix().encode("utf-8"),
    )
    if len(files) > limits.maximum_file_count:
        raise ValueError("M336J archive file count exceeds its bound")
    unpacked = 0
    rows = []
    try:
        with output.open("xb") as raw_output:
            with zipfile.ZipFile(
                raw_output,
                "w",
                compression=zipfile.ZIP_STORED,
                allowZip64=True,
                strict_timestamps=True,
            ) as archive:
                for path in files:
                    if path.is_symlink():
                        raise ValueError("M336J archive source contains a symlink")
                    size = path.stat().st_size
                    unpacked += size
                    if unpacked > limits.maximum_unpacked_bytes:
                        raise ValueError(
                            "M336J archive unpacked size exceeds its bound"
                        )
                    relative = path.relative_to(source).as_posix()
                    name = f"{prefix}/{relative}"
                    if not _safe_archive_member(name):
                        raise ValueError("M336J archive member is unsafe")
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_STORED
                    info.create_system = 3
                    info.external_attr = 0o100600 << 16
                    info.flag_bits = 0x800
                    digest = hashlib.sha256()
                    copied = 0
                    with (
                        path.open("rb") as incoming,
                        archive.open(info, "w", force_zip64=True) as member,
                    ):
                        while True:
                            chunk = incoming.read(limits.chunk_bytes)
                            if not chunk:
                                break
                            member.write(chunk)
                            digest.update(chunk)
                            copied += len(chunk)
                    if copied != size:
                        raise ValueError(
                            "M336J archive source changed during streaming"
                        )
                    rows.append((name, size, digest.hexdigest()))
            raw_output.flush()
            os.fsync(raw_output.fileno())
        archive_size = output.stat().st_size
        if archive_size > limits.maximum_archive_bytes:
            raise ValueError("M336J archive bytes exceed their bound")
        return M336JFileBackedTreeArtifact(
            private_path=output,
            archive_hash=hash_file(output),
            archive_size=archive_size,
            file_count=len(files),
            unpacked_size=unpacked,
            portable_tree_hash=content_hash(tuple(rows)),
        )
    except Exception:
        output.unlink(missing_ok=True)
        raise


def extract_canonical_tree_archive_file(
    archive_path: Path,
    *,
    destination: Path,
    expected_payload_hash: str,
    limits: M336JTreeTransferLimits = M336J_DEFAULT_TREE_TRANSFER_LIMITS,
) -> tuple[int, str]:
    """Verify and atomically publish a streamed private tree."""

    _verify_limits(limits)
    archive_path = archive_path.resolve(strict=True)
    target = destination.resolve(strict=False)
    if not archive_path.is_file() or target.exists():
        raise ValueError("M336J archive or fresh destination is invalid")
    if archive_path.stat().st_size > limits.maximum_archive_bytes:
        raise ValueError("M336J incoming archive exceeds its byte bound")
    if hash_file(archive_path) != expected_payload_hash:
        raise ValueError("M336J transferred tree bytes changed")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.incoming-", dir=target.parent)
    )
    rows = []
    total = 0
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = tuple(archive.infolist())
            names = tuple(info.filename for info in infos)
            if names != tuple(sorted(names, key=lambda item: item.encode("utf-8"))):
                raise ValueError("M336J transferred tree order is not canonical")
            if len(names) != len(set(names)):
                raise ValueError("M336J transferred tree contains duplicates")
            if len(infos) > limits.maximum_file_count:
                raise ValueError("M336J transferred tree file count exceeds its bound")
            for info in infos:
                mode = info.external_attr >> 16
                if (
                    info.is_dir()
                    or not _safe_archive_member(info.filename)
                    or not stat.S_ISREG(mode)
                    or info.file_size < 0
                ):
                    raise ValueError("M336J transferred tree member is unsafe")
                total += info.file_size
                if total > limits.maximum_unpacked_bytes:
                    raise ValueError(
                        "M336J transferred tree unpacked size exceeds its bound"
                    )
                relative = PurePosixPath(info.filename)
                output = staging.joinpath(*relative.parts).resolve(strict=False)
                if not output.is_relative_to(staging):
                    raise ValueError("M336J transferred tree escapes destination")
                output.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                copied = 0
                with archive.open(info, "r") as incoming, output.open("xb") as handle:
                    while True:
                        chunk = incoming.read(limits.chunk_bytes)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > info.file_size:
                            raise ValueError(
                                "M336J archive member exceeds declared size"
                            )
                        digest.update(chunk)
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
                if copied != info.file_size:
                    raise ValueError("M336J archive member is truncated")
                rows.append((info.filename, copied, digest.hexdigest()))
        _fsync_tree_directories(staging)
        os.replace(staging, target)
        _fsync_directory(target.parent)
        return len(rows), content_hash(tuple(rows))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def canonical_tree_archive(root: Path, *, prefix: str) -> bytes:
    """Legacy helper limited to small test fixtures."""

    limits = _small_limits()
    with tempfile.TemporaryDirectory(prefix="m336j-small-archive-") as raw:
        path = Path(raw) / "tree.zip"
        artifact = write_canonical_tree_archive(
            root, path, prefix=prefix, limits=limits
        )
        if artifact.archive_size > M336J_SMALL_IN_MEMORY_LIMIT:
            raise ValueError("M336J in-memory archive exceeds its small limit")
        return path.read_bytes()


def extract_canonical_tree_archive(
    payload: bytes,
    *,
    destination: Path,
    expected_payload_hash: str,
) -> tuple[int, str]:
    """Legacy small-fixture extraction helper."""

    if len(payload) > M336J_SMALL_IN_MEMORY_LIMIT:
        raise ValueError("M336J in-memory archive exceeds its small limit")
    with tempfile.TemporaryDirectory(prefix="m336j-small-extract-") as raw:
        path = Path(raw) / "tree.zip"
        path.write_bytes(payload)
        return extract_canonical_tree_archive_file(
            path,
            destination=destination,
            expected_payload_hash=expected_payload_hash,
            limits=_small_limits(),
        )


def canonical_tree_export(root: Path) -> bytes:
    return canonical_tree_archive(root, prefix="payload")


def extract_canonical_tree_export(
    payload: bytes, *, destination: Path, expected_payload_hash: str
) -> tuple[int, str]:
    if len(payload) > M336J_SMALL_IN_MEMORY_LIMIT:
        raise ValueError("M336J in-memory export exceeds its small limit")
    with tempfile.TemporaryDirectory(prefix="m336j-small-export-") as raw:
        archive = Path(raw) / "export.zip"
        archive.write_bytes(payload)
        return extract_canonical_tree_export_file(
            archive,
            destination=destination,
            expected_payload_hash=expected_payload_hash,
            limits=_small_limits(),
        )


def write_canonical_tree_export(
    root: Path,
    archive_path: Path,
    *,
    limits: M336JTreeTransferLimits = M336J_DEFAULT_TREE_TRANSFER_LIMITS,
) -> M336JFileBackedTreeArtifact:
    return write_canonical_tree_archive(
        root, archive_path, prefix="payload", limits=limits
    )


def extract_canonical_tree_export_file(
    archive_path: Path,
    *,
    destination: Path,
    expected_payload_hash: str,
    limits: M336JTreeTransferLimits = M336J_DEFAULT_TREE_TRANSFER_LIMITS,
) -> tuple[int, str]:
    wrapper = destination.with_name(destination.name + ".verified-wrapper")
    count, tree_hash = extract_canonical_tree_archive_file(
        archive_path,
        destination=wrapper,
        expected_payload_hash=expected_payload_hash,
        limits=limits,
    )
    source = wrapper / "payload"
    if not source.is_dir() or destination.exists():
        shutil.rmtree(wrapper, ignore_errors=True)
        raise ValueError("M336J exported tree wrapper is invalid")
    os.replace(source, destination)
    wrapper.rmdir()
    _fsync_directory(destination.parent)
    return count, tree_hash


def stream_stdin_to_private_file(
    destination: Path,
    *,
    expected_hash: str,
    expected_size: int,
    limits: M336JTreeTransferLimits = M336J_DEFAULT_TREE_TRANSFER_LIMITS,
) -> Path:
    """Receive stdin into a private file with exact incremental bounds."""

    _verify_limits(limits)
    target = destination.resolve(strict=False)
    if (
        target.exists()
        or expected_size < 0
        or expected_size > limits.maximum_archive_bytes
    ):
        raise ValueError("M336J streamed stdin declaration is invalid")
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    try:
        with target.open("xb") as output:
            stdin = sys.stdin.buffer
            while True:
                chunk = stdin.read(limits.chunk_bytes)
                if not chunk:
                    break
                total += len(chunk)
                if total > expected_size or total > limits.maximum_archive_bytes:
                    raise ValueError("M336J streamed stdin exceeds its declared bound")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if total != expected_size or digest.hexdigest() != expected_hash:
            raise ValueError("M336J streamed stdin is truncated or changed")
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise


def stream_file_to_stdout(
    path: Path, *, chunk_bytes: int = M336J_STREAM_CHUNK_BYTES
) -> None:
    source = path.resolve(strict=True)
    if not source.is_file() or not 64 * 1024 <= chunk_bytes <= 8 * 1024 * 1024:
        raise ValueError("M336J streamed stdout source or chunk is invalid")
    stdout = sys.stdout.buffer
    with source.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            stdout.write(chunk)
    stdout.flush()


def canonical_json_bytes(value: object) -> bytes:
    raw = (canonical_json(value) + "\n").encode("utf-8")
    if len(raw) > M336J_SMALL_JSON_LIMIT:
        raise ValueError("M336J canonical JSON exceeds its in-memory bound")
    return raw


def hash_file(path: Path, *, chunk_bytes: int = M336J_STREAM_CHUNK_BYTES) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _ssh_command(
    *,
    transport: KarinaPrivateSshTransport,
    capsule: KarinaPrivateExecutionCapsule,
    plan: KarinaRemoteCommandPlan,
) -> tuple[str, ...]:
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
    rendered = render_remote_command(
        plan,
        shell_executable=capsule.shell_executable,
        repository_checkout=capsule.repository_checkout,
    )
    return (
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


def _safe_archive_member(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(
        value
        and _SAFE_ARCHIVE_PATH.fullmatch(value)
        and not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _small_limits() -> M336JTreeTransferLimits:
    return M336JTreeTransferLimits(
        maximum_archive_bytes=M336J_SMALL_IN_MEMORY_LIMIT,
        maximum_unpacked_bytes=M336J_SMALL_IN_MEMORY_LIMIT,
        maximum_file_count=10_000,
    )


def _verify_limits(limits: M336JTreeTransferLimits) -> None:
    if (
        limits.maximum_archive_bytes <= 0
        or limits.maximum_unpacked_bytes <= 0
        or limits.maximum_file_count <= 0
        or not 64 * 1024 <= limits.chunk_bytes <= 8 * 1024 * 1024
    ):
        raise ValueError("M336J tree transfer limits are invalid")


def _fsync_tree_directories(root: Path) -> None:
    directories = [root, *(path for path in root.rglob("*") if path.is_dir())]
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        _fsync_directory(directory)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _local_ssh_environment() -> dict[str, str]:
    # Windows OpenSSH needs ProgramData to resolve its system crypto/config.
    allowed = ("SYSTEMROOT", "WINDIR", "PROGRAMDATA")
    return {name: os.environ[name] for name in allowed if name in os.environ}
