"""Provision one immutable, cleanup-independent M-33.6k.6 Karina capsule."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from m336k5_prepare_karina_capsule import (
    _create_repository_bundle,
    _remote_metadata,
    _run,
    _scp,
    _ssh,
    _ssh_options,
    _write,
)

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    KarinaRemoteTokenClass,
    load_private_execution_capsule,
    public_execution_capsule_receipt_from_dict,
    render_remote_command,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_karina_invocation,
    build_m336k5_python_startup_policy,
)
from ai_brain.stage3.acquisition.m336k6_capsule import (
    M336K6CapsuleLifecyclePolicy,
    M336K6PrivateExecutionCapsule,
    build_m336k6_capsule_content_manifest,
    build_m336k6_public_capsule_receipt,
    verify_m336k6_capsule_location,
    write_m336k6_json,
)

_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_ENDPOINT = re.compile(r"[A-Za-z0-9._-]+@[A-Za-z0-9.:-]+")
_STATE_PREFIX = PurePosixPath("/home/ibicza/.local/state/ai-brain/m336k6/routes")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    result = prepare_m336k6_karina_capsule(_object(args.request.resolve(strict=True)))
    print(canonical_json(result))


def prepare_m336k6_karina_capsule(request: dict) -> dict:
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
        "persistent_capsule_root",
        "private_route_root",
        "output",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K6 Karina preparation request fields changed")
    exact_head = request["exact_head"]
    endpoint = request["worker_endpoint"]
    if not isinstance(exact_head, str) or _SHA1.fullmatch(exact_head) is None:
        raise M336K2ProtocolError("M336K6 exact implementation SHA is invalid")
    if not isinstance(endpoint, str) or _ENDPOINT.fullmatch(endpoint) is None:
        raise M336K2ProtocolError("M336K6 Karina endpoint is invalid")
    repository = Path(request["repository"]).resolve(strict=True)
    git = Path(request["git_executable"]).resolve(strict=True)
    ssh = Path(request["ssh_executable"]).resolve(strict=True)
    scp = Path(request["scp_executable"]).resolve(strict=True)
    key = Path(request["ssh_key"]).resolve(strict=True)
    known_hosts = Path(request["known_hosts_file"]).resolve(strict=True)
    output = Path(request["output"]).resolve(strict=False)
    if output.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError("M336K6 preparation output is stale or public")
    head = _run((git, "rev-parse", "HEAD^{commit}"), repository).strip()
    status = _run((git, "status", "--porcelain=v1"), repository)
    if head != exact_head or status:
        raise M336K2ProtocolError("M336K6 source is not clean exact implementation")
    capsule_root = PurePosixPath(request["persistent_capsule_root"])
    verify_m336k6_capsule_location(capsule_root)
    route_root = PurePosixPath(request["private_route_root"])
    if (
        not route_root.is_absolute()
        or not route_root.is_relative_to(_STATE_PREFIX)
        or len(route_root.relative_to(_STATE_PREFIX).parts) != 1
    ):
        raise M336K2ProtocolError("M336K6 private route root is invalid")
    source_root = capsule_root / "source"
    git_store = capsule_root / "git-store.git"
    remote_bundle = capsule_root / "repository.bundle"
    legacy_remote = capsule_root / "legacy-execution-capsule.json"
    content_remote = capsule_root / "content-manifest.json"
    lifecycle_remote = capsule_root / "lifecycle-policy.json"
    host_remote = capsule_root / "host-identity.json"
    private_remote = capsule_root / "m336k6-private-capsule.json"
    output.mkdir(parents=True)
    bundle = output / "repository.bundle"
    base_private_path = Path(request["base_private_capsule"]).resolve(strict=True)
    base = load_private_execution_capsule(base_private_path)
    base_public = public_execution_capsule_receipt_from_dict(
        _object(
            Path(request["base_public_execution_capsule_receipt"]).resolve(strict=True)
        )
    )
    host_local = (
        repository
        / "artifacts/acquisition/m336j_freeze_v10/karina_host_identity_receipt.json"
    )
    host = _object(host_local)
    if host.get("receipt_hash") != base.expected_host_identity_receipt_hash:
        raise M336K2ProtocolError("M336K6 stable host receipt binding changed")
    content = build_m336k6_capsule_content_manifest(repository, git, exact_head)
    lifecycle = M336K6CapsuleLifecyclePolicy.build()
    content_local = output / "content-manifest.json"
    lifecycle_local = output / "lifecycle-policy.json"
    write_m336k6_json(content_local, content.canonical_object())
    write_m336k6_json(lifecycle_local, asdict(lifecycle))
    legacy_local = output / "legacy-execution-capsule.json"
    legacy = {
        "schema_version": 1,
        "execution_strategy": "DIRECT_PROJECT_PYTHON",
        "python_executable": base.python_executable.as_posix(),
        "git_executable": base.git_executable.as_posix(),
        "java_executable": base.java_executable.as_posix(),
        "javac_executable": base.javac_executable.as_posix(),
        "shell_executable": base.shell_executable.as_posix(),
        "repository_checkout": source_root.as_posix(),
        "private_root": route_root.as_posix(),
        "expected_head": exact_head,
        "host_identity_receipt": host_remote.as_posix(),
        "expected_host_identity_receipt_hash": base.expected_host_identity_receipt_hash,
        "expected_public_jdk_identity_receipt_hash": base.expected_public_jdk_identity_receipt_hash,
        "expected_public_receipt_hash": None,
    }
    _write(legacy_local, legacy)
    ssh_options = _ssh_options(key, known_hosts)
    try:
        _create_repository_bundle(git=git, bundle=bundle, repository=repository)
        parent = capsule_root.parent
        state_parent = route_root.parent
        setup_root = "; ".join(
            (
                "set -eu",
                "umask 077",
                "test ! -e " + shlex.quote(capsule_root.as_posix()),
                "test ! -e " + shlex.quote(route_root.as_posix()),
                "mkdir -p " + shlex.quote(parent.as_posix()),
                "mkdir -p " + shlex.quote(state_parent.as_posix()),
                "mkdir " + shlex.quote(capsule_root.as_posix()),
                "mkdir " + shlex.quote(route_root.as_posix()),
            )
        )
        _ssh(ssh, ssh_options, endpoint, setup_root)
        _scp(scp, key, known_hosts, bundle, endpoint, remote_bundle)
        setup_source = "; ".join(
            (
                "set -eu",
                "/usr/bin/git clone --quiet --bare "
                + shlex.quote(remote_bundle.as_posix())
                + " "
                + shlex.quote(git_store.as_posix()),
                "/usr/bin/git --git-dir="
                + shlex.quote(git_store.as_posix())
                + " worktree add --quiet --detach "
                + shlex.quote(source_root.as_posix())
                + " "
                + exact_head,
                "/usr/bin/git -C "
                + shlex.quote(source_root.as_posix())
                + " config core.autocrlf false",
                'test -z "$(/usr/bin/git -C '
                + shlex.quote(source_root.as_posix())
                + ' status --porcelain=v1)"',
                "/usr/bin/git --git-dir="
                + shlex.quote(git_store.as_posix())
                + " worktree lock --reason M336K6_PERSISTENT_CAPSULE "
                + shlex.quote(source_root.as_posix()),
                "rm -f -- " + shlex.quote(remote_bundle.as_posix()),
            )
        )
        _ssh(ssh, ssh_options, endpoint, setup_source)
        for local, remote in (
            (host_local, host_remote),
            (content_local, content_remote),
            (lifecycle_local, lifecycle_remote),
            (legacy_local, legacy_remote),
        ):
            _scp(scp, key, known_hosts, local, endpoint, remote)
        first = _remote_metadata(
            ssh=ssh,
            ssh_options=ssh_options,
            endpoint=endpoint,
            capsule=legacy,
            remote_repository=source_root,
            remote_capsule=legacy_remote,
            private_capsule=legacy_local,
            public_capsule=base_public,
            local_repository=repository,
            git=git,
        )
        legacy_receipt = first["public_execution_capsule_receipt"]
        legacy["expected_public_receipt_hash"] = legacy_receipt["receipt_hash"]
        _write(legacy_local, legacy)
        _scp(scp, key, known_hosts, legacy_local, endpoint, legacy_remote)
        second = _remote_metadata(
            ssh=ssh,
            ssh_options=ssh_options,
            endpoint=endpoint,
            capsule=legacy,
            remote_repository=source_root,
            remote_capsule=legacy_remote,
            private_capsule=legacy_local,
            public_capsule=public_execution_capsule_receipt_from_dict(legacy_receipt),
            local_repository=repository,
            git=git,
        )
        if first != second:
            raise M336K2ProtocolError("M336K6 legacy capsule identity is unstable")
        python_resolved = _ssh(
            ssh,
            ssh_options,
            endpoint,
            "/usr/bin/readlink -f " + shlex.quote(base.python_executable.as_posix()),
        )
        ssh_hash = _ssh(
            ssh,
            ssh_options,
            endpoint,
            "/usr/bin/sha256sum /usr/bin/ssh | /usr/bin/cut -d' ' -f1",
        )
        private_body = {
            "schema_version": 1,
            "contract_role": "M336K6_PRIVATE_EXECUTION_CAPSULE",
            "execution_strategy": "PROTECTED_DETACHED_GIT_WORKTREE",
            "capsule_root": capsule_root.as_posix(),
            "source_root": source_root.as_posix(),
            "git_store": git_store.as_posix(),
            "private_route_root": route_root.as_posix(),
            "python_invocation_handle": base.python_executable.as_posix(),
            "resolved_python_binary": python_resolved,
            "python_environment_prefix": base.python_executable.parent.parent.as_posix(),
            "git_executable": base.git_executable.as_posix(),
            "ssh_executable": "/usr/bin/ssh",
            "java_executable": base.java_executable.as_posix(),
            "javac_executable": base.javac_executable.as_posix(),
            "shell_executable": base.shell_executable.as_posix(),
            "legacy_capsule_path": legacy_remote.as_posix(),
            "content_manifest_path": content_remote.as_posix(),
            "lifecycle_policy_path": lifecycle_remote.as_posix(),
            "host_identity_receipt_path": host_remote.as_posix(),
            "implementation_sha": exact_head,
            "project_source_identity": first["project_source_identity"],
            "legacy_public_receipt_hash": legacy_receipt["receipt_hash"],
            "python_environment_manifest_hash": first["python_environment_identity"][
                "environment_manifest_hash"
            ],
            "executable_dependency_manifest_hash": first[
                "executable_dependency_manifest"
            ]["manifest_hash"],
            "startup_policy_hash": build_m336k5_python_startup_policy().policy_hash,
            "bootstrap_source_hash": bytes_hash(
                (repository / "scripts/m336k5_python_bootstrap.py").read_bytes()
            ),
            "launcher_source_hash": bytes_hash(
                (
                    repository / "src/ai_brain/stage3/acquisition/m336k5_startup.py"
                ).read_bytes()
            ),
            "ssh_executable_content_hash": ssh_hash,
            "content_manifest_hash": content.manifest_hash,
            "lifecycle_policy_hash": lifecycle.policy_hash,
            "capsule_root_identity_hash": content_hash(
                ("M336K6_CAPSULE_ROOT", capsule_root.as_posix())
            ),
        }
        private_capsule = M336K6PrivateExecutionCapsule(
            **private_body, capsule_identity_hash=content_hash(private_body)
        )
        private_capsule.verify_structure()
        private_local = output / "m336k6-private-capsule.json"
        write_m336k6_json(private_local, asdict(private_capsule))
        _scp(scp, key, known_hosts, private_local, endpoint, private_remote)
        public = build_m336k6_public_capsule_receipt(
            private_capsule, base.expected_host_identity_receipt_hash
        )
        live_legacy = load_private_execution_capsule(legacy_local)
        target = source_root / "scripts/m336k6_verify_persistent_capsule.py"
        plan, _inline = build_m336k5_karina_invocation(
            component_id="m336k6.persistent-capsule-liveness.v1",
            capsule=live_legacy,
            public_capsule=public_execution_capsule_receipt_from_dict(legacy_receipt),
            process_role="PERSISTENT_CAPSULE_LIVENESS",
            target=target,
            target_arguments=(
                (KarinaRemoteTokenClass.FLAG, "--capsule"),
                (KarinaRemoteTokenClass.PRIVATE_PATH, private_remote),
                (KarinaRemoteTokenClass.FLAG, "--phase"),
                (KarinaRemoteTokenClass.OPAQUE_ARGUMENT, "CAPSULE_CREATED"),
            ),
            bootstrap_source_hash=private_capsule.bootstrap_source_hash,
            target_source_hash=bytes_hash(
                (
                    repository / "scripts/m336k6_verify_persistent_capsule.py"
                ).read_bytes()
            ),
            project_source_identity=first["project_source_identity"],
            startup_receipt=route_root / "m336k6-startup-creation.json",
        )
        live_raw = _ssh(
            ssh,
            ssh_options,
            endpoint,
            render_remote_command(
                plan,
                shell_executable=live_legacy.shell_executable,
                repository_checkout=live_legacy.repository_checkout,
            ),
        )
        live = json.loads(live_raw)
        live_body = dict(live) if isinstance(live, dict) else {}
        live_hash = live_body.pop("receipt_hash", None)
        if live.get("status") != "PASS" or content_hash(live_body) != live_hash:
            raise M336K2ProtocolError("M336K6 initial capsule liveness failed")
        public_local = output / "m336k6-public-capsule.json"
        legacy_public_local = output / "legacy-public-capsule.json"
        dependencies_local = output / "executable-dependencies.json"
        python_local = output / "python-environment.json"
        _write(public_local, asdict(public))
        _write(legacy_public_local, legacy_receipt)
        _write(dependencies_local, first["executable_dependency_manifest"])
        _write(python_local, first["python_environment_identity"])
        _write(output / "liveness-created.json", live)
        overlay = {
            "private_execution_capsule": str(legacy_local),
            "public_execution_capsule_receipt": str(legacy_public_local),
            "executable_dependency_manifest": str(dependencies_local),
            "private_capsule_remote": legacy_remote.as_posix(),
            "repository": source_root.as_posix(),
            "private_root": route_root.as_posix(),
            "m336k6_private_capsule_remote": private_remote.as_posix(),
            "m336k6_public_capsule_receipt": str(public_local),
            "project_source_identity": first["project_source_identity"],
        }
        _write(output / "karina-overlay.private.json", overlay)
        body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336K6_PERSISTENT_CAPSULE_PREPARATION",
            "exact_implementation_sha": exact_head,
            "execution_strategy": private_capsule.execution_strategy,
            "capsule_identity_hash": private_capsule.capsule_identity_hash,
            "content_manifest_hash": content.manifest_hash,
            "lifecycle_policy_hash": lifecycle.policy_hash,
            "public_capsule_receipt_hash": public.receipt_hash,
            "initial_liveness_receipt_hash": live["receipt_hash"],
            "legacy_public_receipt_hash": legacy_receipt["receipt_hash"],
            "project_source_identity": first["project_source_identity"],
            "mutable_quality_dependency_count": 0,
            "cleanup_managed_root_count": 0,
            "status": "PASS",
        }
        preparation = {**body, "receipt_hash": content_hash(body)}
        _write(output / "preparation-receipt.json", preparation)
        return {**preparation, "karina_overlay": overlay}
    finally:
        bundle.unlink(missing_ok=True)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K6 JSON input is not an object")
    return value


if __name__ == "__main__":
    main()
