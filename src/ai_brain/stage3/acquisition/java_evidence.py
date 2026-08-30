"""Independently reproducible Java proposal field evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_proposals import JavaProposalBatch
from ai_brain.stage3.acquisition.java_source_index import (
    JavaSourceIndex,
    declaration_by_node_id,
)
from ai_brain.stage3.acquisition.models import (
    SourceBundle,
    SourceLocation,
)
from ai_brain.stage3.knowledge_ir.records import ClaimSchemaContent

JAVA_EVIDENCE_EXTRACTOR_VERSION = "m341.java-field-evidence.v1"
JAVA_EVIDENCE_EXTRACTOR_HASH = content_hash(
    {
        "extractor": JAVA_EVIDENCE_EXTRACTOR_VERSION,
        "policy": "ast-node-or-token-span;schema-metadata-excluded",
    }
)


@dataclass(frozen=True)
class JavaFieldEvidence:
    proposal_id: str
    proposal_hash: str
    field_path: str
    evidence_class: str
    document_id: str
    document_bytes_hash: str
    source_location: SourceLocation
    source_span_hash: str
    parser_node_id: str
    semantic_identity_hash: str
    transformation_id: str
    transformation_version: str
    transformation_hash: str
    normalized_output: str
    derivation_receipt_hash: str
    evidence_hash: str


@dataclass(frozen=True)
class JavaFieldEvidenceManifest:
    bundle_hash: str
    source_index_hash: str
    proposal_manifest_hash: str
    required_field_count: int
    evidence_count: int
    completeness_ratio: str
    evidence: tuple[JavaFieldEvidence, ...]
    manifest_hash: str


def build_java_field_evidence_manifest(
    proposal_batch: JavaProposalBatch,
    source_index: JavaSourceIndex,
    bundle: SourceBundle,
    store,
) -> JavaFieldEvidenceManifest:
    evidence = _recompute_evidence(proposal_batch, source_index, bundle, store)
    body = {
        "bundle_hash": bundle.bundle_hash,
        "source_index_hash": source_index.index_hash,
        "proposal_manifest_hash": proposal_batch.proposal_manifest_hash,
        "required_field_count": len(evidence),
        "evidence_count": len(evidence),
        "completeness_ratio": "1.000000" if evidence else "0.000000",
        "evidence": evidence,
    }
    if not evidence:
        raise ValueError("Java field evidence denominator cannot be empty")
    return JavaFieldEvidenceManifest(**body, manifest_hash=content_hash(body))


def verify_java_field_evidence_manifest(
    manifest: JavaFieldEvidenceManifest,
    proposal_batch: JavaProposalBatch,
    source_index: JavaSourceIndex,
    bundle: SourceBundle,
    store,
) -> None:
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    if content_hash(body) != claimed:
        raise ValueError("Java field evidence manifest hash mismatch")
    expected = _recompute_evidence(proposal_batch, source_index, bundle, store)
    if not expected:
        raise ValueError("Java field evidence denominator cannot be empty")
    if (
        manifest.bundle_hash != bundle.bundle_hash
        or manifest.source_index_hash != source_index.index_hash
        or manifest.proposal_manifest_hash != proposal_batch.proposal_manifest_hash
        or manifest.required_field_count != len(expected)
        or manifest.evidence_count != len(expected)
        or manifest.completeness_ratio != "1.000000"
        or manifest.evidence != expected
    ):
        raise ValueError("Java field evidence is incomplete or not reproducible")


def evidence_by_proposal(
    manifest: JavaFieldEvidenceManifest,
) -> dict[str, tuple[JavaFieldEvidence, ...]]:
    result: dict[str, list[JavaFieldEvidence]] = {}
    for item in manifest.evidence:
        result.setdefault(item.proposal_id, []).append(item)
    return {
        key: tuple(sorted(values, key=lambda item: item.field_path))
        for key, values in result.items()
    }


def _recompute_evidence(proposal_batch, source_index, bundle, store):
    if (
        proposal_batch.bundle_hash != bundle.bundle_hash
        or proposal_batch.source_index_hash != source_index.index_hash
    ):
        raise ValueError("Java evidence input closure mismatch")
    nodes = declaration_by_node_id(source_index)
    proposals = {item.proposal_id: item for item in proposal_batch.proposals}
    documents = {item.document_id: item for item in bundle.documents}
    result = []
    for binding in proposal_batch.bindings:
        proposal = proposals.get(binding.proposal_id)
        declaration = nodes.get(binding.parser_node_id)
        if proposal is None or declaration is None:
            raise ValueError("Java proposal-to-AST binding is incomplete")
        document = documents.get(declaration.document_id)
        if document is None:
            raise ValueError("Java evidence document is outside bundle")
        raw = store.get_blob(document.bytes_hash)
        result.extend(_proposal_evidence(proposal, declaration, raw))
    ordered = tuple(
        sorted(result, key=lambda item: (item.proposal_id, item.field_path))
    )
    keys = {(item.proposal_id, item.field_path) for item in ordered}
    if len(keys) != len(ordered):
        raise ValueError("duplicate Java field evidence")
    return ordered


def _proposal_evidence(proposal, declaration, raw):
    if not isinstance(proposal.proposed_content, ClaimSchemaContent):
        raise TypeError("Java AST proposal must contain ClaimSchemaContent")
    content = proposal.proposed_content
    fields = [
        (
            "content.receiver_type",
            "deterministically_derived",
            declaration.name_span,
            "receiver",
            declaration.receiver_type,
        ),
        (
            "content.predicate_id",
            "directly_source_backed",
            declaration.name_span,
            "member-name",
            "<init>"
            if declaration.member_kind == "constructor"
            else declaration.member_name,
        ),
    ]
    for index, parameter in enumerate(declaration.parameters):
        fields.extend(
            (
                (
                    f"content.parameters[{index}].name",
                    "directly_source_backed",
                    parameter.name_span,
                    "parameter-name",
                    parameter.name,
                ),
                (
                    f"content.parameters[{index}].type",
                    "directly_source_backed",
                    parameter.type_span,
                    "parameter-type",
                    parameter.source_type,
                ),
            )
        )
    if declaration.member_kind == "method" and declaration.return_type is not None:
        return_span = declaration.type_token_spans[-1]
        fields.append(
            (
                "content.return_type",
                "directly_source_backed",
                return_span,
                "return-type",
                declaration.return_type,
            )
        )
    for index, (name, bound) in enumerate(declaration.type_variable_bounds):
        fields.append(
            (
                f"content.generic_constraints[{index}]",
                "deterministically_derived",
                declaration.declaration_span,
                "generic-constraint",
                f"{name} extends {bound}",
            )
        )
    for index, exception in enumerate(declaration.declared_exceptions):
        fields.append(
            (
                f"content.declared_exceptions[{index}]",
                "directly_source_backed",
                declaration.declaration_span,
                "declared-exception",
                exception,
            )
        )
    expected = _proposal_field_values(content)
    result = []
    for field_path, evidence_class, location, transformation, normalized in fields:
        if expected.get(field_path) != normalized:
            raise ValueError(f"Java proposal field differs from AST: {field_path}")
        span = raw[location.byte_start : location.byte_end]
        transformation_id = f"m341.java.{transformation}.v1"
        transformation_hash = content_hash(
            {
                "extractor_hash": JAVA_EVIDENCE_EXTRACTOR_HASH,
                "transformation_id": transformation_id,
            }
        )
        receipt_body = {
            "proposal_id": proposal.proposal_id,
            "proposal_hash": proposal.proposal_hash,
            "field_path": field_path,
            "document_bytes_hash": declaration.source_snapshot_hash,
            "source_span_hash": bytes_hash(span),
            "parser_node_id": declaration.node_id,
            "transformation_hash": transformation_hash,
            "normalized_output": normalized,
        }
        body = {
            "proposal_id": proposal.proposal_id,
            "proposal_hash": proposal.proposal_hash,
            "field_path": field_path,
            "evidence_class": evidence_class,
            "document_id": declaration.document_id,
            "document_bytes_hash": declaration.source_snapshot_hash,
            "source_location": location,
            "source_span_hash": bytes_hash(span),
            "parser_node_id": declaration.node_id,
            "semantic_identity_hash": declaration.declaration_hash,
            "transformation_id": transformation_id,
            "transformation_version": JAVA_EVIDENCE_EXTRACTOR_VERSION,
            "transformation_hash": transformation_hash,
            "normalized_output": normalized,
            "derivation_receipt_hash": content_hash(receipt_body),
        }
        result.append(JavaFieldEvidence(**body, evidence_hash=content_hash(body)))
    return tuple(result)


def _proposal_field_values(content: ClaimSchemaContent):
    values = {
        "content.receiver_type": content.receiver_type,
        "content.predicate_id": content.predicate_id,
        "content.return_type": content.return_type,
    }
    for index, (name, value_type) in enumerate(content.parameters):
        values[f"content.parameters[{index}].name"] = name
        values[f"content.parameters[{index}].type"] = value_type
    for index, value in enumerate(content.generic_constraints):
        values[f"content.generic_constraints[{index}]"] = value
    for index, value in enumerate(content.declared_exceptions):
        values[f"content.declared_exceptions[{index}]"] = value
    return values
