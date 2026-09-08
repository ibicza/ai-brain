"""Typed cross-bound receipts and ordered remote transcript for M-33.6j."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import content_hash

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")

M336J_TRANSCRIPT_ORDER = (
    "HOST_PREFLIGHT",
    "STORAGE_CAPACITY",
    "TREE_UPLOAD_VAULT",
    "TREE_UPLOAD_INPUTS",
    "MATERIALIZATION",
    "PRODUCTION",
    "TREE_DOWNLOAD",
    "REPLAY",
    "INDEPENDENT_EVALUATION",
    "INSTALLED_RUNTIME",
)


@dataclass(frozen=True)
class M336JReceiptBinding:
    route_run_id: str
    exact_sha: str
    host_identity_hash: str
    capsule_receipt_hash: str
    dependency_manifest_hash: str
    command_renderer_hash: str
    route_manifest_hash: str
    component_binding_hash: str
    request_schema_hash: str
    response_schema_hash: str
    selected_manifest_hash: str | None
    binding_manifest_hash: str | None
    candidate_pack_hash: str | None
    binding_hash: str


@dataclass(frozen=True)
class M336JTypedReceipt:
    schema_version: int
    contract_role: str
    receipt_type: str
    operation_index: int
    binding: M336JReceiptBinding
    predecessor_receipt_hash: str | None
    payload_hash: str
    source_leak_count: int
    absolute_public_path_count: int
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336JRemoteRouteTranscript:
    schema_version: int
    contract_role: str
    route_run_id: str
    exact_sha: str
    host_identity_hash: str
    capsule_receipt_hash: str
    dependency_manifest_hash: str
    command_renderer_hash: str
    route_manifest_hash: str
    operations: tuple[M336JTypedReceipt, ...]
    operation_count: int
    orphan_receipt_count: int
    cross_run_receipt_acceptance_count: int
    cross_host_receipt_acceptance_count: int
    cross_sha_receipt_acceptance_count: int
    pack_hash_disagreement_count: int
    out_of_order_operation_acceptance_count: int
    source_leak_count: int
    absolute_public_path_count: int
    status: str
    transcript_hash: str


def build_receipt_binding(**values: str | None) -> M336JReceiptBinding:
    body = dict(values)
    required = {
        "route_run_id",
        "exact_sha",
        "host_identity_hash",
        "capsule_receipt_hash",
        "dependency_manifest_hash",
        "command_renderer_hash",
        "route_manifest_hash",
        "component_binding_hash",
        "request_schema_hash",
        "response_schema_hash",
        "selected_manifest_hash",
        "binding_manifest_hash",
        "candidate_pack_hash",
    }
    if set(body) != required:
        raise ValueError("M336J receipt binding fields changed")
    binding = M336JReceiptBinding(**body, binding_hash=content_hash(body))
    verify_receipt_binding(binding)
    return binding


def verify_receipt_binding(binding: M336JReceiptBinding) -> None:
    body = asdict(binding)
    claimed = body.pop("binding_hash")
    mandatory_hashes = (
        binding.host_identity_hash,
        binding.capsule_receipt_hash,
        binding.dependency_manifest_hash,
        binding.command_renderer_hash,
        binding.route_manifest_hash,
        binding.component_binding_hash,
        binding.request_schema_hash,
        binding.response_schema_hash,
    )
    optional_hashes = (
        binding.selected_manifest_hash,
        binding.binding_manifest_hash,
        binding.candidate_pack_hash,
    )
    if (
        not binding.route_run_id
        or _GIT_SHA.fullmatch(binding.exact_sha) is None
        or any(_SHA256.fullmatch(value) is None for value in mandatory_hashes)
        or any(
            value is not None and _SHA256.fullmatch(value) is None
            for value in optional_hashes
        )
        or content_hash(body) != claimed
    ):
        raise ValueError("M336J receipt binding is invalid")


def build_typed_receipt(
    receipt_type: str,
    *,
    operation_index: int,
    binding: M336JReceiptBinding,
    predecessor_receipt_hash: str | None,
    payload_hash: str,
) -> M336JTypedReceipt:
    verify_receipt_binding(binding)
    if receipt_type not in M336J_TRANSCRIPT_ORDER and receipt_type not in {
        "REMOTE_COMMAND",
        "RESPONSE",
        "QUALITY",
    }:
        raise ValueError("M336J typed receipt type is unknown")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_TYPED_RECEIPT",
        "receipt_type": receipt_type,
        "operation_index": operation_index,
        "binding": binding,
        "predecessor_receipt_hash": predecessor_receipt_hash,
        "payload_hash": payload_hash,
        "source_leak_count": 0,
        "absolute_public_path_count": 0,
        "status": "PASS",
    }
    receipt = M336JTypedReceipt(**body, receipt_hash=content_hash(body))
    verify_typed_receipt(receipt, expected_type=receipt_type)
    return receipt


def verify_typed_receipt(
    receipt: M336JTypedReceipt,
    *,
    expected_type: str,
    expected_binding: M336JReceiptBinding | None = None,
) -> None:
    verify_receipt_binding(receipt.binding)
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    if (
        receipt.schema_version != 1
        or receipt.contract_role != "PUBLIC_SAFE_M336J_TYPED_RECEIPT"
        or receipt.receipt_type != expected_type
        or receipt.operation_index < 0
        or (
            receipt.predecessor_receipt_hash is not None
            and _SHA256.fullmatch(receipt.predecessor_receipt_hash) is None
        )
        or _SHA256.fullmatch(receipt.payload_hash) is None
        or receipt.source_leak_count
        or receipt.absolute_public_path_count
        or receipt.status != "PASS"
        or content_hash(body) != claimed
        or (expected_binding is not None and receipt.binding != expected_binding)
    ):
        raise ValueError(f"M336J {expected_type} typed receipt is invalid")


def _named_verifier(receipt: M336JTypedReceipt, receipt_type: str) -> None:
    verify_typed_receipt(receipt, expected_type=receipt_type)


def verify_host_preflight_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "HOST_PREFLIGHT")


def verify_storage_capacity_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "STORAGE_CAPACITY")


def verify_materialization_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "MATERIALIZATION")


def verify_production_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "PRODUCTION")


def verify_replay_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "REPLAY")


def verify_evaluation_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "INDEPENDENT_EVALUATION")


def verify_runtime_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "INSTALLED_RUNTIME")


def verify_remote_command_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "REMOTE_COMMAND")


def verify_response_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "RESPONSE")


def verify_quality_receipt(receipt: M336JTypedReceipt) -> None:
    _named_verifier(receipt, "QUALITY")


def build_remote_route_transcript(
    operations: tuple[M336JTypedReceipt, ...],
) -> M336JRemoteRouteTranscript:
    if len(operations) != len(M336J_TRANSCRIPT_ORDER):
        raise ValueError("M336J route transcript operation count changed")
    for expected_index, (expected_type, receipt) in enumerate(
        zip(M336J_TRANSCRIPT_ORDER, operations, strict=True)
    ):
        verify_typed_receipt(receipt, expected_type=expected_type)
        if receipt.operation_index != expected_index:
            raise ValueError("M336J route transcript operation order changed")
        predecessor = (
            None if expected_index == 0 else operations[expected_index - 1].receipt_hash
        )
        if receipt.predecessor_receipt_hash != predecessor:
            raise ValueError("M336J route transcript contains an orphan receipt")
    first = operations[0].binding
    common = (
        first.route_run_id,
        first.exact_sha,
        first.host_identity_hash,
        first.capsule_receipt_hash,
        first.dependency_manifest_hash,
        first.command_renderer_hash,
        first.route_manifest_hash,
        first.selected_manifest_hash,
        first.binding_manifest_hash,
    )
    for receipt in operations:
        binding = receipt.binding
        if (
            binding.route_run_id,
            binding.exact_sha,
            binding.host_identity_hash,
            binding.capsule_receipt_hash,
            binding.dependency_manifest_hash,
            binding.command_renderer_hash,
            binding.route_manifest_hash,
            binding.selected_manifest_hash,
            binding.binding_manifest_hash,
        ) != common:
            raise ValueError("M336J route transcript accepts a cross-run binding")
    production = operations[M336J_TRANSCRIPT_ORDER.index("PRODUCTION")].binding
    if production.candidate_pack_hash is None:
        raise ValueError("M336J production receipt lacks the candidate-pack hash")
    for receipt_type in (
        "TREE_DOWNLOAD",
        "REPLAY",
        "INDEPENDENT_EVALUATION",
        "INSTALLED_RUNTIME",
    ):
        item = operations[M336J_TRANSCRIPT_ORDER.index(receipt_type)].binding
        if item.candidate_pack_hash != production.candidate_pack_hash:
            raise ValueError("M336J route transcript candidate-pack hashes differ")
    for receipt in operations[: M336J_TRANSCRIPT_ORDER.index("PRODUCTION")]:
        if receipt.binding.candidate_pack_hash is not None:
            raise ValueError("M336J pre-production receipt claims a candidate pack")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_REMOTE_ROUTE_TRANSCRIPT",
        "route_run_id": first.route_run_id,
        "exact_sha": first.exact_sha,
        "host_identity_hash": first.host_identity_hash,
        "capsule_receipt_hash": first.capsule_receipt_hash,
        "dependency_manifest_hash": first.dependency_manifest_hash,
        "command_renderer_hash": first.command_renderer_hash,
        "route_manifest_hash": first.route_manifest_hash,
        "operations": operations,
        "operation_count": len(operations),
        "orphan_receipt_count": 0,
        "cross_run_receipt_acceptance_count": 0,
        "cross_host_receipt_acceptance_count": 0,
        "cross_sha_receipt_acceptance_count": 0,
        "pack_hash_disagreement_count": 0,
        "out_of_order_operation_acceptance_count": 0,
        "source_leak_count": 0,
        "absolute_public_path_count": 0,
        "status": "PASS",
    }
    transcript = M336JRemoteRouteTranscript(**body, transcript_hash=content_hash(body))
    verify_remote_route_transcript(transcript)
    return transcript


def verify_remote_route_transcript(transcript: M336JRemoteRouteTranscript) -> None:
    body = asdict(transcript)
    claimed = body.pop("transcript_hash")
    rebuilt = build_remote_route_transcript_without_final_verification(
        transcript.operations
    )
    if (
        transcript != rebuilt
        or content_hash(body) != claimed
        or transcript.status != "PASS"
        or any(
            (
                transcript.orphan_receipt_count,
                transcript.cross_run_receipt_acceptance_count,
                transcript.cross_host_receipt_acceptance_count,
                transcript.cross_sha_receipt_acceptance_count,
                transcript.pack_hash_disagreement_count,
                transcript.out_of_order_operation_acceptance_count,
                transcript.source_leak_count,
                transcript.absolute_public_path_count,
            )
        )
    ):
        raise ValueError("M336J remote route transcript is invalid")


def build_remote_route_transcript_without_final_verification(
    operations: tuple[M336JTypedReceipt, ...],
) -> M336JRemoteRouteTranscript:
    """Internal non-recursive rebuild used by the independent verifier."""

    if len(operations) != len(M336J_TRANSCRIPT_ORDER):
        raise ValueError("M336J remote route transcript operation count changed")
    for expected_index, (expected_type, receipt) in enumerate(
        zip(M336J_TRANSCRIPT_ORDER, operations, strict=True)
    ):
        verify_typed_receipt(receipt, expected_type=expected_type)
        predecessor = (
            None if expected_index == 0 else operations[expected_index - 1].receipt_hash
        )
        if (
            receipt.operation_index != expected_index
            or receipt.predecessor_receipt_hash != predecessor
        ):
            raise ValueError("M336J remote route transcript sequence is invalid")
    first = operations[0].binding
    production = operations[M336J_TRANSCRIPT_ORDER.index("PRODUCTION")].binding
    if production.candidate_pack_hash is None:
        raise ValueError("M336J production receipt lacks the candidate-pack hash")
    common = {
        "route_run_id": first.route_run_id,
        "exact_sha": first.exact_sha,
        "host_identity_hash": first.host_identity_hash,
        "capsule_receipt_hash": first.capsule_receipt_hash,
        "dependency_manifest_hash": first.dependency_manifest_hash,
        "command_renderer_hash": first.command_renderer_hash,
        "route_manifest_hash": first.route_manifest_hash,
    }
    for receipt in operations:
        if any(
            getattr(receipt.binding, key) != value for key, value in common.items()
        ) or (
            receipt.binding.selected_manifest_hash,
            receipt.binding.binding_manifest_hash,
        ) != (
            first.selected_manifest_hash,
            first.binding_manifest_hash,
        ):
            raise ValueError("M336J remote route transcript common binding changed")
    for receipt_type in (
        "TREE_DOWNLOAD",
        "REPLAY",
        "INDEPENDENT_EVALUATION",
        "INSTALLED_RUNTIME",
    ):
        if (
            operations[
                M336J_TRANSCRIPT_ORDER.index(receipt_type)
            ].binding.candidate_pack_hash
            != production.candidate_pack_hash
        ):
            raise ValueError("M336J transcript pack binding changed")
    for receipt in operations[: M336J_TRANSCRIPT_ORDER.index("PRODUCTION")]:
        if receipt.binding.candidate_pack_hash is not None:
            raise ValueError("M336J pre-production transcript binding claims a pack")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_REMOTE_ROUTE_TRANSCRIPT",
        **common,
        "operations": operations,
        "operation_count": len(operations),
        "orphan_receipt_count": 0,
        "cross_run_receipt_acceptance_count": 0,
        "cross_host_receipt_acceptance_count": 0,
        "cross_sha_receipt_acceptance_count": 0,
        "pack_hash_disagreement_count": 0,
        "out_of_order_operation_acceptance_count": 0,
        "source_leak_count": 0,
        "absolute_public_path_count": 0,
        "status": "PASS",
    }
    return M336JRemoteRouteTranscript(**body, transcript_hash=content_hash(body))


def typed_receipt_from_dict(value: dict) -> M336JTypedReceipt:
    binding_value = value.get("binding")
    if not isinstance(binding_value, dict):
        raise TypeError("M336J typed receipt binding is absent")
    receipt = M336JTypedReceipt(
        **{**value, "binding": M336JReceiptBinding(**binding_value)}
    )
    verify_typed_receipt(receipt, expected_type=receipt.receipt_type)
    return receipt


def transcript_from_dict(value: dict) -> M336JRemoteRouteTranscript:
    operations = tuple(typed_receipt_from_dict(item) for item in value["operations"])
    transcript = M336JRemoteRouteTranscript(**{**value, "operations": operations})
    verify_remote_route_transcript(transcript)
    return transcript
