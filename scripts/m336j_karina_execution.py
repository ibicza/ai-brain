"""Isolated Karina-side execution entry point for M-33.6j."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336j_execution import (
    load_private_execution_capsule,
    public_dataclass,
    run_karina_host_preflight_v2,
    verify_execution_capsule,
)
from ai_brain.stage3.acquisition.m336j_remote_validation import (
    run_m336j_installed_runtime,
    run_m336j_remote_independent_evaluation,
    run_m336j_remote_replay_and_pack_verification,
)
from ai_brain.stage3.acquisition.m336j_storage import (
    build_private_storage_plan,
    preflight_private_storage,
)
from ai_brain.stage3.acquisition.m336j_transport import (
    M336J_DEFAULT_TREE_TRANSFER_LIMITS,
    extract_canonical_tree_archive_file,
    portable_tree_content_identity,
    stream_file_to_stdout,
    stream_stdin_to_private_file,
    write_canonical_tree_export,
)


def _capsule_receipt(args) -> None:
    receipt, python, dependencies, audit = verify_execution_capsule(
        args.private_capsule
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_M336J_EXECUTION_CAPSULE_VERIFICATION",
        "execution_capsule": public_dataclass(receipt),
        "python_environment": public_dataclass(python),
        "executable_dependency_manifest": public_dataclass(dependencies),
        "executable_dependency_audit": public_dataclass(audit),
        "status": "PASS",
    }
    print(canonical_json({**body, "receipt_hash": content_hash(body)}))


def _host_preflight(args) -> None:
    result = run_karina_host_preflight_v2(args.private_capsule)
    body = {
        **result,
        "request_hash": args.request_hash,
        "component_binding_hash": args.component_binding_hash,
    }
    body.pop("receipt_hash")
    print(canonical_json({**body, "receipt_hash": content_hash(body)}))


def _receive_tree(args) -> None:
    capsule = load_private_execution_capsule(args.private_capsule)
    receipt, _python, _dependencies, _audit = verify_execution_capsule(
        args.private_capsule
    )
    if receipt.receipt_hash != args.expected_capsule_receipt_hash:
        raise ValueError("M336J receive-tree capsule binding changed")
    destination = _private_destination(capsule.private_root, args.relative_destination)
    limits = M336J_DEFAULT_TREE_TRANSFER_LIMITS
    limit_hash = content_hash(asdict(limits))
    if args.transfer_limit_hash != limit_hash:
        raise ValueError("M336J receive-tree transfer limit binding changed")
    temporary = _fresh_private_transfer_file(capsule.private_root, "upload")
    try:
        stream_stdin_to_private_file(
            temporary,
            expected_hash=args.payload_hash,
            expected_size=args.payload_size,
            limits=limits,
        )
        count, tree_hash = extract_canonical_tree_archive_file(
            temporary,
            destination=destination,
            expected_payload_hash=args.payload_hash,
            limits=limits,
        )
    finally:
        temporary.unlink(missing_ok=True)
    if count != args.file_count or tree_hash != args.portable_tree_hash:
        raise ValueError("M336J receive-tree content declaration changed")
    content_root = _private_existing(
        PurePosixPath(destination.as_posix()), args.content_root
    )
    content_count, content_tree_hash = portable_tree_content_identity(content_root)
    if (
        content_count != args.expected_content_file_count
        or content_tree_hash != args.expected_content_tree_hash
    ):
        raise ValueError("M336J receive-tree unwrapped content identity changed")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_M336J_PRIVATE_TREE_TRANSFER_RECEIPT",
        "request_hash": args.request_hash,
        "component_binding_hash": args.component_binding_hash,
        "host_identity_hash": receipt.host_identity_receipt_hash,
        "payload_hash": args.payload_hash,
        "payload_size": args.payload_size,
        "file_count": count,
        "portable_tree_hash": tree_hash,
        "content_file_count": content_count,
        "content_tree_hash": content_tree_hash,
        "transfer_limit_hash": limit_hash,
        "status": "PASS",
    }
    print(canonical_json({**body, "receipt_hash": content_hash(body)}))


def _export_tree(args) -> None:
    capsule = load_private_execution_capsule(args.private_capsule)
    receipt, _python, _dependencies, _audit = verify_execution_capsule(
        args.private_capsule
    )
    if receipt.receipt_hash != args.expected_capsule_receipt_hash:
        raise ValueError("M336J export-tree capsule binding changed")
    source = _private_existing(capsule.private_root, args.relative_source)
    limits = M336J_DEFAULT_TREE_TRANSFER_LIMITS
    limit_hash = content_hash(asdict(limits))
    if args.transfer_limit_hash != limit_hash:
        raise ValueError("M336J export-tree transfer limit binding changed")
    temporary = _fresh_private_transfer_file(capsule.private_root, "download")
    try:
        artifact = write_canonical_tree_export(source, temporary, limits=limits)
        header_body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_M336J_PRIVATE_TREE_EXPORT_HEADER",
            "request_hash": args.request_hash,
            "component_binding_hash": args.component_binding_hash,
            "host_identity_hash": receipt.host_identity_receipt_hash,
            "payload_hash": artifact.archive_hash,
            "payload_size": artifact.archive_size,
            "file_count": artifact.file_count,
            "portable_tree_hash": artifact.portable_tree_hash,
            "transfer_limit_hash": limit_hash,
            "status": "PASS",
        }
        header = {**header_body, "receipt_hash": content_hash(header_body)}
        sys.stdout.buffer.write((canonical_json(header) + "\n").encode("utf-8"))
        stream_file_to_stdout(temporary, chunk_bytes=limits.chunk_bytes)
    finally:
        temporary.unlink(missing_ok=True)


def _storage_preflight(args) -> None:
    capsule = load_private_execution_capsule(args.private_capsule)
    receipt, _python, _dependencies, _audit = verify_execution_capsule(
        args.private_capsule
    )
    plan = build_private_storage_plan(
        (Path(str(capsule.private_root)),),
        maximum_expected_transfer_bytes=args.maximum_transfer_bytes,
        qualification_margin=args.qualification_margin,
    )
    result = preflight_private_storage(
        plan,
        git_worktrees=(Path(str(capsule.repository_checkout)),),
    )
    body = {
        **asdict(result),
        "request_hash": args.request_hash,
        "component_binding_hash": args.component_binding_hash,
        "host_identity_hash": receipt.host_identity_receipt_hash,
    }
    body.pop("receipt_hash")
    print(canonical_json({**body, "receipt_hash": content_hash(body)}))


def _independent_evaluation(args) -> None:
    capsule = load_private_execution_capsule(args.private_capsule)
    receipt, _python, _dependencies, _audit = verify_execution_capsule(
        args.private_capsule
    )
    config = _private_file(capsule.private_root, args.relative_config)
    output = _private_destination(capsule.private_root, args.relative_output)
    result = run_m336j_remote_independent_evaluation(config, output)
    legacy_hash = result.pop("result_hash")
    body = {
        **result,
        "request_hash": args.request_hash,
        "component_binding_hash": args.component_binding_hash,
        "host_identity_hash": receipt.host_identity_receipt_hash,
        "independent_evaluation_result_hash": legacy_hash,
    }
    print(canonical_json({**body, "receipt_hash": content_hash(body)}))


def _installed_runtime(args) -> None:
    capsule = load_private_execution_capsule(args.private_capsule)
    receipt, _python, _dependencies, _audit = verify_execution_capsule(
        args.private_capsule
    )
    pack = _private_existing(capsule.private_root, args.relative_pack)
    result = run_m336j_installed_runtime(pack)
    runtime_hash = result.pop("receipt_hash")
    body = {
        **result,
        "request_hash": args.request_hash,
        "component_binding_hash": args.component_binding_hash,
        "host_identity_hash": receipt.host_identity_receipt_hash,
        "runtime_check_receipt_hash": runtime_hash,
    }
    print(canonical_json({**body, "receipt_hash": content_hash(body)}))


def _replay_and_pack_verification(args) -> None:
    capsule = load_private_execution_capsule(args.private_capsule)
    receipt, _python, _dependencies, _audit = verify_execution_capsule(
        args.private_capsule
    )
    pack = _private_existing(capsule.private_root, args.relative_pack)
    replay_receipt = _private_file(capsule.private_root, args.relative_replay_receipt)
    result = run_m336j_remote_replay_and_pack_verification(pack, replay_receipt)
    replay_hash = result.pop("receipt_hash")
    body = {
        **result,
        "request_hash": args.request_hash,
        "component_binding_hash": args.component_binding_hash,
        "host_identity_hash": receipt.host_identity_receipt_hash,
        "replay_and_pack_verification_hash": replay_hash,
    }
    print(canonical_json({**body, "receipt_hash": content_hash(body)}))


def _produce_worker(args) -> None:
    capsule = load_private_execution_capsule(args.private_capsule)
    receipt, _python, _dependencies, _audit = verify_execution_capsule(
        args.private_capsule
    )
    payload = sys.stdin.buffer.read()
    try:
        request = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("M336J worker request is not strict JSON") from error
    if not isinstance(request, dict):
        raise TypeError("M336J worker request must be an object")
    supplied_hash = request.pop("request_hash", None)
    component_hash = request.pop("m336j_component_binding_hash", None)
    capsule_hash = request.pop("m336j_execution_capsule_receipt_hash", None)
    m336j_body = {
        **request,
        "m336j_execution_capsule_receipt_hash": capsule_hash,
        "m336j_component_binding_hash": component_hash,
    }
    if (
        supplied_hash != args.request_hash
        or content_hash(m336j_body) != supplied_hash
        or component_hash != args.component_binding_hash
        or capsule_hash != receipt.receipt_hash
        or request.get("repository") != capsule.repository_checkout.as_posix()
        or request.get("expected_head") != capsule.expected_head
        or request.get("javac") != capsule.javac_executable.as_posix()
        or request.get("host_identity_hash")
        != capsule.expected_host_identity_receipt_hash
        or request.get("jdk_receipt_hash")
        != capsule.expected_public_jdk_identity_receipt_hash
    ):
        raise ValueError("M336J worker request/capsule binding changed")

    request_path = Path(str(capsule.private_root)) / (
        f"consumed-worker-request-{supplied_hash}.json"
    )
    if request_path.exists():
        raise FileExistsError("M336J worker request replay detected")
    write_canonical_json(
        request_path, {**request, "request_hash": content_hash(request)}
    )
    module = _load_legacy_worker(capsule.repository_checkout)
    module._produce_worker(
        SimpleNamespace(
            request=request_path,
            git_executable=capsule.git_executable.as_posix(),
            m336j_mode=True,
        )
    )
    legacy = strict_json_file(Path(request["output"]))
    if not isinstance(legacy, dict):
        raise TypeError("M336J legacy worker response is not an object")
    legacy_body = dict(legacy)
    legacy_hash = legacy_body.pop("receipt_hash", None)
    if content_hash(legacy_body) != legacy_hash or legacy.get("status") != "PASS":
        raise ValueError("M336J legacy worker response is invalid")
    body = {
        **legacy_body,
        "request_hash": supplied_hash,
        "component_binding_hash": component_hash,
        "legacy_response_hash": legacy_hash,
    }
    print(canonical_json({**body, "receipt_hash": content_hash(body)}))


def _load_legacy_worker(repository: PurePosixPath):
    path = Path(str(repository)) / "scripts" / "m336i_java_final_route.py"
    spec = importlib.util.spec_from_file_location("m336j_legacy_worker", path)
    if spec is None or spec.loader is None:
        raise ImportError("M336J legacy worker could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _private_destination(private_root: PurePosixPath, relative: str) -> Path:
    root = Path(str(private_root)).resolve(strict=True)
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise ValueError("M336J private destination is unsafe")
    destination = root.joinpath(*candidate.parts).resolve(strict=False)
    if not destination.is_relative_to(root):
        raise ValueError("M336J private destination escapes capsule root")
    return destination


def _private_existing(private_root: PurePosixPath, relative: str) -> Path:
    candidate = _private_destination(private_root, relative).resolve(strict=True)
    if not candidate.is_dir():
        raise ValueError("M336J private export source is not a directory")
    return candidate


def _private_file(private_root: PurePosixPath, relative: str) -> Path:
    candidate = _private_destination(private_root, relative).resolve(strict=True)
    if not candidate.is_file():
        raise ValueError("M336J private input is not a file")
    return candidate


def _fresh_private_transfer_file(private_root: PurePosixPath, purpose: str) -> Path:
    root = Path(str(private_root)).resolve(strict=True)
    transfer_root = root / "m336j-transfer-temporary"
    transfer_root.mkdir(mode=0o700, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(
        prefix=f"{purpose}-", suffix=".zip", dir=transfer_root
    )
    os.close(descriptor)
    Path(raw).unlink()
    return Path(raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    capsule = commands.add_parser("capsule-receipt")
    capsule.add_argument("--private-capsule", type=Path, required=True)
    host = commands.add_parser("host-preflight")
    host.add_argument("--private-capsule", type=Path, required=True)
    host.add_argument("--request-hash", required=True)
    host.add_argument("--component-binding-hash", required=True)
    storage = commands.add_parser("storage-preflight")
    storage.add_argument("--private-capsule", type=Path, required=True)
    storage.add_argument("--request-hash", required=True)
    storage.add_argument("--component-binding-hash", required=True)
    storage.add_argument("--maximum-transfer-bytes", type=int, required=True)
    storage.add_argument("--qualification-margin", action="store_true")
    worker = commands.add_parser("produce-worker")
    worker.add_argument("--private-capsule", type=Path, required=True)
    worker.add_argument("--request-hash", required=True)
    worker.add_argument("--component-binding-hash", required=True)
    evaluation = commands.add_parser("independent-evaluation")
    evaluation.add_argument("--private-capsule", type=Path, required=True)
    evaluation.add_argument("--request-hash", required=True)
    evaluation.add_argument("--component-binding-hash", required=True)
    evaluation.add_argument("--relative-config", required=True)
    evaluation.add_argument("--relative-output", required=True)
    runtime = commands.add_parser("installed-runtime")
    runtime.add_argument("--private-capsule", type=Path, required=True)
    runtime.add_argument("--request-hash", required=True)
    runtime.add_argument("--component-binding-hash", required=True)
    runtime.add_argument("--relative-pack", required=True)
    replay = commands.add_parser("replay-and-pack-verification")
    replay.add_argument("--private-capsule", type=Path, required=True)
    replay.add_argument("--request-hash", required=True)
    replay.add_argument("--component-binding-hash", required=True)
    replay.add_argument("--relative-pack", required=True)
    replay.add_argument("--relative-replay-receipt", required=True)
    for name in ("receive-tree", "export-tree"):
        transfer = commands.add_parser(name)
        transfer.add_argument("--private-capsule", type=Path, required=True)
        transfer.add_argument("--expected-capsule-receipt-hash", required=True)
        transfer.add_argument("--request-hash", required=True)
        transfer.add_argument("--component-binding-hash", required=True)
        if name == "receive-tree":
            transfer.add_argument("--relative-destination", required=True)
            transfer.add_argument("--payload-hash", required=True)
            transfer.add_argument("--payload-size", type=int, required=True)
            transfer.add_argument("--file-count", type=int, required=True)
            transfer.add_argument("--portable-tree-hash", required=True)
            transfer.add_argument("--content-root", required=True)
            transfer.add_argument(
                "--expected-content-file-count", type=int, required=True
            )
            transfer.add_argument("--expected-content-tree-hash", required=True)
            transfer.add_argument("--transfer-limit-hash", required=True)
        else:
            transfer.add_argument("--relative-source", required=True)
            transfer.add_argument("--transfer-limit-hash", required=True)
    args = parser.parse_args()
    command = {
        "capsule-receipt": _capsule_receipt,
        "host-preflight": _host_preflight,
        "storage-preflight": _storage_preflight,
        "produce-worker": _produce_worker,
        "independent-evaluation": _independent_evaluation,
        "installed-runtime": _installed_runtime,
        "replay-and-pack-verification": _replay_and_pack_verification,
        "receive-tree": _receive_tree,
        "export-tree": _export_tree,
    }[args.command]
    command(args)


if __name__ == "__main__":
    main()
