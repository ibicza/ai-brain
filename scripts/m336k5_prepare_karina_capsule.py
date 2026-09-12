"""Prepare a fresh exact-HEAD private Karina checkout and execution capsule."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    KarinaRemoteTokenClass,
    compute_m336j_project_source_identity,
    load_private_execution_capsule,
    public_execution_capsule_receipt_from_dict,
    render_remote_command,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_karina_invocation,
)

_SHA1 = re.compile(r"[0-9a-f]{40}")
_ENDPOINT = re.compile(r"[A-Za-z0-9._-]+@[A-Za-z0-9.:-]+")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    result = prepare_m336k5_karina_capsule(_object(args.request.resolve(strict=True)))
    print(canonical_json(result))


def prepare_m336k5_karina_capsule(request: dict) -> dict:
    expected = {
        "repository",
        "exact_head",
        "git_executable",
        "base_private_capsule",
        "base_public_execution_capsule_receipt",
        "ssh_executable",
        "scp_executable",
        "ssh_key",
        "known_hosts_file",
        "worker_endpoint",
        "remote_workspace",
        "output",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K5 Karina preparation request fields changed")
    exact_head = request["exact_head"]
    if not isinstance(exact_head, str) or _SHA1.fullmatch(exact_head) is None:
        raise M336K2ProtocolError("M336K5 Karina preparation HEAD is invalid")
    endpoint = request["worker_endpoint"]
    if not isinstance(endpoint, str) or _ENDPOINT.fullmatch(endpoint) is None:
        raise M336K2ProtocolError("M336K5 Karina endpoint is invalid")
    repository = Path(request["repository"]).resolve(strict=True)
    git = Path(request["git_executable"]).resolve(strict=True)
    ssh = Path(request["ssh_executable"]).resolve(strict=True)
    scp = Path(request["scp_executable"]).resolve(strict=True)
    key = Path(request["ssh_key"]).resolve(strict=True)
    known_hosts = Path(request["known_hosts_file"]).resolve(strict=True)
    output = Path(request["output"]).resolve(strict=False)
    if output.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError("M336K5 Karina preparation output is not fresh")
    head = _run((git, "rev-parse", "HEAD^{commit}"), repository).strip()
    status = _run((git, "status", "--porcelain=v1"), repository)
    if head != exact_head or status:
        raise M336K2ProtocolError("M336K5 Karina source is not clean exact HEAD")
    remote_workspace = _remote_workspace(request["remote_workspace"])
    remote_repository = remote_workspace / "repository"
    remote_capsule_root = remote_workspace / "capsule-root"
    remote_route_root = remote_capsule_root / "route"
    remote_bundle = remote_workspace / "repository.bundle"
    remote_capsule = remote_workspace / "private-execution-capsule.json"
    output.mkdir(parents=True)
    bundle = output / "repository.bundle"
    private_capsule = output / "private-execution-capsule.json"
    public_capsule = output / "karina-public-capsule.json"
    dependencies_path = output / "karina-executable-dependencies.json"
    python_path = output / "karina-python-environment.json"
    audit_path = output / "karina-dependency-audit.json"
    base = _object(Path(request["base_private_capsule"]).resolve(strict=True))
    base_public = public_execution_capsule_receipt_from_dict(
        _object(
            Path(request["base_public_execution_capsule_receipt"]).resolve(strict=True)
        )
    )
    required_capsule_fields = {
        "schema_version",
        "execution_strategy",
        "python_executable",
        "git_executable",
        "java_executable",
        "javac_executable",
        "shell_executable",
        "repository_checkout",
        "private_root",
        "expected_head",
        "host_identity_receipt",
        "expected_host_identity_receipt_hash",
        "expected_public_jdk_identity_receipt_hash",
        "expected_public_receipt_hash",
    }
    if set(base) != required_capsule_fields:
        raise M336K2ProtocolError("M336K5 base Karina capsule fields changed")
    capsule = {
        **base,
        "repository_checkout": remote_repository.as_posix(),
        "private_root": remote_capsule_root.as_posix(),
        "expected_head": exact_head,
        "expected_public_receipt_hash": None,
    }
    _write(private_capsule, capsule)
    ssh_options = _ssh_options(key, known_hosts)
    try:
        _run((git, "bundle", "create", str(bundle), "HEAD"), repository)
        _ssh(
            ssh,
            ssh_options,
            endpoint,
            "umask 077; test ! -e "
            + shlex.quote(remote_workspace.as_posix())
            + "; mkdir -p "
            + shlex.quote(remote_workspace.as_posix()),
        )
        _scp(
            scp,
            key,
            known_hosts,
            bundle,
            endpoint,
            remote_bundle,
        )
        setup = "; ".join(
            (
                "set -eu",
                "/usr/bin/git clone --quiet "
                + shlex.quote(remote_bundle.as_posix())
                + " "
                + shlex.quote(remote_repository.as_posix()),
                "/usr/bin/git -C "
                + shlex.quote(remote_repository.as_posix())
                + " checkout --quiet --detach "
                + exact_head,
                "/usr/bin/git -C "
                + shlex.quote(remote_repository.as_posix())
                + " config core.autocrlf false",
                'test -z "$(/usr/bin/git -C '
                + shlex.quote(remote_repository.as_posix())
                + ' status --porcelain=v1)"',
                "mkdir -p " + shlex.quote(remote_capsule_root.as_posix()),
                "rm -f -- " + shlex.quote(remote_bundle.as_posix()),
            )
        )
        _ssh(ssh, ssh_options, endpoint, setup)
        _scp(scp, key, known_hosts, private_capsule, endpoint, remote_capsule)
        first = _remote_metadata(
            ssh=ssh,
            ssh_options=ssh_options,
            endpoint=endpoint,
            capsule=capsule,
            remote_repository=remote_repository,
            remote_capsule=remote_capsule,
            private_capsule=private_capsule,
            public_capsule=base_public,
            local_repository=repository,
            git=git,
        )
        receipt = first["public_execution_capsule_receipt"]
        capsule["expected_public_receipt_hash"] = receipt["receipt_hash"]
        _write(private_capsule, capsule)
        _scp(scp, key, known_hosts, private_capsule, endpoint, remote_capsule)
        second = _remote_metadata(
            ssh=ssh,
            ssh_options=ssh_options,
            endpoint=endpoint,
            capsule=capsule,
            remote_repository=remote_repository,
            remote_capsule=remote_capsule,
            private_capsule=private_capsule,
            public_capsule=public_execution_capsule_receipt_from_dict(receipt),
            local_repository=repository,
            git=git,
        )
        if first != second:
            raise M336K2ProtocolError("M336K5 Karina capsule metadata is unstable")
        _write(public_capsule, receipt)
        _write(dependencies_path, first["executable_dependency_manifest"])
        _write(python_path, first["python_environment_identity"])
        _write(audit_path, first["dependency_audit"])
        body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336K5_KARINA_PREPARATION_RECEIPT",
            "exact_head": exact_head,
            "public_execution_capsule_receipt_hash": receipt["receipt_hash"],
            "executable_dependency_manifest_hash": first[
                "executable_dependency_manifest"
            ]["manifest_hash"],
            "python_environment_identity_hash": first["python_environment_identity"][
                "identity_hash"
            ],
            "dependency_audit_hash": first["dependency_audit"]["audit_hash"],
            "metadata_hash": first["metadata_hash"],
            "project_source_identity": first["project_source_identity"],
            "status": "PASS",
        }
        preparation = {**body, "receipt_hash": content_hash(body)}
        _write(output / "preparation-receipt.json", preparation)
        private_overlay = {
            "private_execution_capsule": str(private_capsule),
            "public_execution_capsule_receipt": str(public_capsule),
            "executable_dependency_manifest": str(dependencies_path),
            "private_capsule_remote": remote_capsule.as_posix(),
            "repository": remote_repository.as_posix(),
            "private_root": remote_route_root.as_posix(),
        }
        _write(output / "karina-overlay.private.json", private_overlay)
        return {**preparation, "karina_overlay": private_overlay}
    finally:
        bundle.unlink(missing_ok=True)


def _remote_metadata(
    *,
    ssh: Path,
    ssh_options: tuple[str, ...],
    endpoint: str,
    capsule: dict,
    remote_repository: PurePosixPath,
    remote_capsule: PurePosixPath,
    private_capsule: Path,
    public_capsule,
    local_repository: Path,
    git: Path,
) -> dict:
    private = load_private_execution_capsule(private_capsule)
    target = remote_repository / "scripts/m336k5_export_karina_capsule_metadata.py"
    plan, _inline = build_m336k5_karina_invocation(
        component_id="m336k5.karina-capsule-metadata.v1",
        capsule=private,
        public_capsule=public_capsule,
        process_role="KARINA_CAPSULE_METADATA",
        target=target,
        target_arguments=(
            (KarinaRemoteTokenClass.FLAG, "--private-capsule"),
            (KarinaRemoteTokenClass.PRIVATE_PATH, remote_capsule),
        ),
        bootstrap_source_hash=bytes_hash(
            (local_repository / "scripts/m336k5_python_bootstrap.py").read_bytes()
        ),
        target_source_hash=bytes_hash(
            (
                local_repository / "scripts/m336k5_export_karina_capsule_metadata.py"
            ).read_bytes()
        ),
        project_source_identity=compute_m336j_project_source_identity(
            local_repository, git
        ),
        startup_receipt=private.private_root / "m336k5-startup-receipt.json",
    )
    command = render_remote_command(
        plan,
        shell_executable=private.shell_executable,
        repository_checkout=private.repository_checkout,
    )
    raw = _ssh(ssh, ssh_options, endpoint, command)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise M336K2ProtocolError("M336K5 Karina metadata is not JSON") from error
    expected = {
        "schema_version",
        "contract_role",
        "public_execution_capsule_receipt",
        "python_environment_identity",
        "executable_dependency_manifest",
        "dependency_audit",
        "project_source_identity",
        "startup_receipt_hash",
        "status",
        "metadata_hash",
    }
    body = dict(value) if isinstance(value, dict) else {}
    claimed = body.pop("metadata_hash", None)
    if (
        set(value) != expected
        or content_hash(body) != claimed
        or value.get("status") != "PASS"
        or value.get("contract_role") != "PUBLIC_SAFE_M336K5_KARINA_CAPSULE_METADATA"
    ):
        raise M336K2ProtocolError("M336K5 Karina metadata failed verification")
    return value


def _remote_workspace(value: object) -> PurePosixPath:
    if not isinstance(value, str):
        raise M336K2ProtocolError("M336K5 Karina workspace is invalid")
    path = PurePosixPath(value)
    if (
        not path.is_absolute()
        or len(path.parts) != 4
        or path.parts[:3] != ("/", "home", "ibicza")
        or not path.name.startswith("m336k5-")
        or re.fullmatch(r"[a-z0-9-]+", path.name) is None
    ):
        raise M336K2ProtocolError("M336K5 Karina workspace is unsafe")
    return path


def _ssh_options(key: Path, known_hosts: Path) -> tuple[str, ...]:
    return (
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
        "ConnectTimeout=10",
        "-i",
        str(key),
    )


def _ssh(
    executable: Path,
    options: tuple[str, ...],
    endpoint: str,
    remote_command: str,
) -> str:
    return _run((executable, *options, endpoint, remote_command), None).strip()


def _scp(
    executable: Path,
    key: Path,
    known_hosts: Path,
    source: Path,
    endpoint: str,
    destination: PurePosixPath,
) -> None:
    options = (
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "ConnectTimeout=10",
        "-i",
        str(key),
    )
    _run(
        (
            executable,
            "-q",
            *options,
            str(source.resolve(strict=True)),
            f"{endpoint}:{destination.as_posix()}",
        ),
        None,
    )


def _run(arguments: tuple[object, ...], cwd: Path | None) -> str:
    result = subprocess.run(
        tuple(str(item) for item in arguments),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    )
    return result.stdout


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K5 Karina JSON input is not an object")
    return value


if __name__ == "__main__":
    main()
