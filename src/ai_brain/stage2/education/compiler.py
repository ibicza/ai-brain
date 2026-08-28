"""Offline-only trusted answer-key compilation boundary.

Runtime education modules must never import this module.  It is the sole
educational owner of a direct ``ChemistryToolRegistry.execute`` call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    EDUCATIONAL_TOOL_IDS,
    ChemistryEducationAdapter,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.compilation_receipts import (
    COMPILER_IDENTITY,
    verify_compilation_receipt,
)
from ai_brain.stage2.education.models import (
    ActorIdentityType,
    EducationalCompilationReceipt,
)
from ai_brain.stage2.education.version import EDUCATIONAL_COMPILATION_POLICY_VERSION
from ai_brain.stage2.facts.canonical import canonical_json, content_hash, utc_now


def compile_answer_key(
    service: ChemistryDomainService,
    tool_id: str,
    arguments: dict[str, Any],
    *,
    actor_identity_type: ActorIdentityType,
    compiler_identity: str,
    exercise_spec_hash: str | None = None,
    created_at: str | None = None,
    audit_path: Path | None = None,
):
    """Execute one exact tool under explicit offline build authority."""
    if actor_identity_type is not ActorIdentityType.TRUSTED_PROCESS:
        raise PermissionError("only TRUSTED_PROCESS may compile answer keys")
    if compiler_identity != COMPILER_IDENTITY:
        raise PermissionError("unrecognized educational compiler identity")
    if tool_id not in EDUCATIONAL_TOOL_IDS:
        raise ValueError("tool is outside the educational compilation allowlist")
    if not isinstance(arguments, dict) or not arguments:
        raise ValueError("compilation arguments must be an immutable object")
    canonical_arguments = _immutable_arguments(arguments)
    manifest_hash = service.registry.descriptor(tool_id).implementation_manifest_hash
    # This is intentionally the only direct educational registry execution.
    result = service.registry.execute(
        tool_id,
        canonical_arguments,
        expected_manifest_hash=manifest_hash,
    )
    graph = ChemistryEducationAdapter(service).graph_from_completed_result(
        tool_id,
        canonical_arguments,
        result,
        created_at=created_at,
        request_hash=content_hash(
            {"tool_id": tool_id, "arguments": canonical_arguments}
        ),
    )
    timestamp = created_at or utc_now()
    body = {
        "compilation_id": "",
        "compiler_identity": compiler_identity,
        "actor_identity_type": actor_identity_type,
        "compilation_policy_version": EDUCATIONAL_COMPILATION_POLICY_VERSION,
        "chemistry_domain_manifest_hash": service.manifest["domain_manifest_hash"],
        "fact_memory_snapshot_hash": service.manifest["fact_memory_snapshot_hash"],
        "source_chain_hash": service.manifest["source_chain_hash"],
        "tool_id": tool_id,
        "canonical_arguments": canonical_arguments,
        "tool_implementation_manifest_hash": manifest_hash,
        "knowledge_snapshot_hash": result["knowledge_snapshot_hash"],
        "exact_result_hash": result["result_hash"],
        "educational_graph_hash": graph.graph_hash,
        "exercise_spec_hash": exercise_spec_hash,
        "generated_at": timestamp,
    }
    body["compilation_id"] = f"education.compilation.{content_hash(body)[:24]}"
    receipt = EducationalCompilationReceipt(**body, receipt_hash=content_hash(body))
    verify_compilation_receipt(receipt, service, graph_hash=graph.graph_hash)
    if audit_path is not None:
        _append_audit(audit_path, receipt)
    return result, graph, receipt


def compile_fact_answer_key(
    service: ChemistryDomainService,
    symbol: str,
    given_predicate: str,
    answer_predicate: str,
    *,
    language: str,
    actor_identity_type: ActorIdentityType,
    compiler_identity: str,
    exercise_spec_hash: str | None = None,
    created_at: str | None = None,
    audit_path: Path | None = None,
):
    """Compile a paired factual answer under the same offline authority."""
    if actor_identity_type is not ActorIdentityType.TRUSTED_PROCESS:
        raise PermissionError("only TRUSTED_PROCESS may compile answer keys")
    if compiler_identity != COMPILER_IDENTITY:
        raise PermissionError("unrecognized educational compiler identity")
    timestamp = created_at or utc_now()
    given, answer, graph = ChemistryEducationAdapter(service).paired_fact_graph(
        symbol,
        given_predicate,
        answer_predicate,
        language=language,
        created_at=timestamp,
    )
    arguments = {
        "symbol": symbol,
        "given_predicate": given_predicate,
        "answer_predicate": answer_predicate,
        "language": language,
    }
    body = {
        "compilation_id": "",
        "compiler_identity": compiler_identity,
        "actor_identity_type": actor_identity_type,
        "compilation_policy_version": EDUCATIONAL_COMPILATION_POLICY_VERSION,
        "chemistry_domain_manifest_hash": service.manifest["domain_manifest_hash"],
        "fact_memory_snapshot_hash": service.manifest["fact_memory_snapshot_hash"],
        "source_chain_hash": service.manifest["source_chain_hash"],
        "tool_id": "chemistry_fact_lookup",
        "canonical_arguments": arguments,
        "tool_implementation_manifest_hash": content_hash("chemistry_fact_lookup_v1"),
        "knowledge_snapshot_hash": graph.knowledge_snapshot_hash,
        "exact_result_hash": graph.source_result_hash,
        "educational_graph_hash": graph.graph_hash,
        "exercise_spec_hash": exercise_spec_hash,
        "generated_at": timestamp,
    }
    body["compilation_id"] = f"education.compilation.{content_hash(body)[:24]}"
    receipt = EducationalCompilationReceipt(**body, receipt_hash=content_hash(body))
    verify_compilation_receipt(receipt, service, graph_hash=graph.graph_hash)
    if audit_path is not None:
        _append_audit(audit_path, receipt)
    return given, answer, graph, receipt


def _immutable_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    # Canonical JSON round-trip rejects non-JSON values and severs caller aliases.
    import json

    value = json.loads(canonical_json(arguments))
    if not isinstance(value, dict) or value != arguments:
        raise ValueError("compilation arguments are not canonically immutable")
    return value


def _append_audit(path: Path, receipt: EducationalCompilationReceipt) -> None:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event_type": "EDUCATIONAL_ANSWER_KEY_COMPILED",
        "receipt_hash": receipt.receipt_hash,
        "compilation_id": receipt.compilation_id,
        "exact_result_hash": receipt.exact_result_hash,
        "graph_hash": receipt.educational_graph_hash,
    }
    with resolved.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(event) + "\n")
