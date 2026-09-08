"""Build the ordered typed M-33.6j transcript from inspected route receipts."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336j_receipts import (
    M336J_TRANSCRIPT_ORDER,
    build_receipt_binding,
    build_remote_route_transcript,
    build_typed_receipt,
)
from ai_brain.stage3.acquisition.m336j_registry import build_m336j_route_registry

_ROLE_BY_OPERATION = {
    "HOST_PREFLIGHT": "REMOTE_HOST_PREFLIGHT",
    "STORAGE_CAPACITY": "REMOTE_STORAGE_PREFLIGHT",
    "TREE_UPLOAD_VAULT": "REMOTE_TREE_UPLOAD",
    "TREE_UPLOAD_INPUTS": "REMOTE_TREE_UPLOAD",
    "MATERIALIZATION": "REMOTE_SELECTED_SOURCE_MATERIALIZER",
    "PRODUCTION": "REMOTE_COMPILER_AWARE_PRODUCTION_WORKER",
    "TREE_DOWNLOAD": "REMOTE_TREE_DOWNLOAD",
    "REPLAY": "REMOTE_REPLAY_AND_PACK_VERIFIER",
    "INDEPENDENT_EVALUATION": "REMOTE_INDEPENDENT_EVALUATOR",
    "INSTALLED_RUNTIME": "REMOTE_INSTALLED_RUNTIME",
}
_REQUEST_FIELDS = {
    "route_run_id",
    "exact_sha",
    "host_identity_hash",
    "capsule_receipt_hash",
    "dependency_manifest_hash",
    "command_renderer_hash",
    "route_manifest_hash",
    "selected_manifest_hash",
    "binding_manifest_hash",
    "candidate_pack_hash",
    "receipt_paths",
    "output",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request)
    if set(request) != _REQUEST_FIELDS:
        raise ValueError("M336J route transcript request fields changed")
    paths = request["receipt_paths"]
    if not isinstance(paths, dict) or set(paths) != set(M336J_TRANSCRIPT_ORDER):
        raise ValueError("M336J route transcript receipt paths are incomplete")
    registry = build_m336j_route_registry()
    by_role = {item.route_role: item for item in registry.components}
    receipts = tuple(_verified(Path(paths[name])) for name in M336J_TRANSCRIPT_ORDER)
    operations = []
    predecessor = None
    production_index = M336J_TRANSCRIPT_ORDER.index("PRODUCTION")
    for index, (operation, receipt) in enumerate(
        zip(M336J_TRANSCRIPT_ORDER, receipts, strict=True)
    ):
        component = by_role[_ROLE_BY_OPERATION[operation]]
        binding = build_receipt_binding(
            route_run_id=request["route_run_id"],
            exact_sha=request["exact_sha"],
            host_identity_hash=request["host_identity_hash"],
            capsule_receipt_hash=request["capsule_receipt_hash"],
            dependency_manifest_hash=request["dependency_manifest_hash"],
            command_renderer_hash=request["command_renderer_hash"],
            route_manifest_hash=request["route_manifest_hash"],
            component_binding_hash=component.binding_hash,
            request_schema_hash=component.request_schema_hash,
            response_schema_hash=component.response_schema_hash,
            selected_manifest_hash=request["selected_manifest_hash"],
            binding_manifest_hash=request["binding_manifest_hash"],
            candidate_pack_hash=(
                request["candidate_pack_hash"] if index >= production_index else None
            ),
        )
        typed = build_typed_receipt(
            operation,
            operation_index=index,
            binding=binding,
            predecessor_receipt_hash=predecessor,
            payload_hash=receipt["receipt_hash"],
        )
        operations.append(typed)
        predecessor = typed.receipt_hash
    transcript = build_remote_route_transcript(tuple(operations))
    write_canonical_json(Path(request["output"]), transcript)


def _object(path: Path) -> dict:
    value = strict_json_file(path.resolve(strict=True))
    if not isinstance(value, dict):
        raise TypeError("M336J route transcript input must be an object")
    return value


def _verified(path: Path) -> dict:
    value = _object(path)
    body = dict(value)
    claimed = body.pop("receipt_hash", None)
    if content_hash(body) != claimed or value.get("status") not in {
        "PASS",
        "OUTCOME A",
    }:
        raise ValueError("M336J route transcript source receipt is invalid")
    return value


if __name__ == "__main__":
    main()
