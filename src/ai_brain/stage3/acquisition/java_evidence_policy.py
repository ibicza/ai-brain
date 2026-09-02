"""Independent, exhaustive field inventory for Java trust evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_proposals import JavaProposalBatch
from ai_brain.stage3.acquisition.java_source_index import (
    JavaSourceIndex,
    declaration_by_node_id,
)
from ai_brain.stage3.acquisition.models import SourceLocation
from ai_brain.stage3.knowledge_ir.records import ClaimSchemaContent

JAVA_EVIDENCE_POLICY_VERSION = "m342.java-evidence-policy.v1"


class JavaEvidenceClass(StrEnum):
    DIRECT_SOURCE = "DIRECT_SOURCE"
    DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"
    FIXED_SCHEMA_METADATA = "FIXED_SCHEMA_METADATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class JavaEvidencePolicyRule:
    field_pattern: str
    evidence_class: JavaEvidenceClass
    transformation_id: str


@dataclass(frozen=True)
class JavaEvidencePolicyManifest:
    schema_version: int
    policy_version: str
    policy_artifact_hash: str
    rules: tuple[JavaEvidencePolicyRule, ...]
    rule_count: int
    manifest_hash: str


@dataclass(frozen=True)
class JavaEvidenceRequirement:
    proposal_id: str
    proposal_hash: str
    parser_node_id: str
    field_path: str
    evidence_class: JavaEvidenceClass
    transformation_id: str
    expected_output: str
    source_location: SourceLocation
    requirement_hash: str


_RULES = (
    ("content.subject_type", "FIXED_SCHEMA_METADATA", "fixed-subject-type"),
    ("content.predicate_id", "DIRECT_SOURCE", "member-name"),
    ("content.object_type", "FIXED_SCHEMA_METADATA", "fixed-object-type"),
    ("content.qualifier_ids", "FIXED_SCHEMA_METADATA", "fixed-empty-qualifiers"),
    ("content.receiver_type", "DETERMINISTIC_DERIVATION", "receiver-type"),
    ("content.parameters[*].name", "DIRECT_SOURCE", "parameter-name"),
    ("content.parameters[*].type", "DIRECT_SOURCE", "parameter-source-type"),
    ("content.return_type", "DIRECT_SOURCE", "return-source-type"),
    (
        "content.constructor_return_type",
        "DETERMINISTIC_DERIVATION",
        "constructor-void-return",
    ),
    (
        "content.generic_constraints[*]",
        "DETERMINISTIC_DERIVATION",
        "generic-constraint",
    ),
    ("content.preconditions", "FIXED_SCHEMA_METADATA", "fixed-empty-preconditions"),
    (
        "content.postconditions",
        "FIXED_SCHEMA_METADATA",
        "fixed-empty-postconditions",
    ),
    ("content.declared_exceptions[*]", "DIRECT_SOURCE", "declared-exception"),
    ("content.deprecated_since", "NOT_APPLICABLE", "absent-deprecated-since"),
    ("content.examples", "NOT_APPLICABLE", "absent-examples"),
    ("envelope.proposed_kind", "FIXED_SCHEMA_METADATA", "fixed-proposed-kind"),
    (
        "envelope.epistemic_character",
        "FIXED_SCHEMA_METADATA",
        "fixed-epistemic-character",
    ),
    (
        "envelope.extraction_method",
        "FIXED_SCHEMA_METADATA",
        "fixed-extraction-method",
    ),
    ("envelope.status_authority", "DETERMINISTIC_DERIVATION", "status-authority"),
    ("envelope.ambiguity_fields", "DETERMINISTIC_DERIVATION", "ambiguity-fields"),
    (
        "envelope.source_segment_binding",
        "DETERMINISTIC_DERIVATION",
        "source-segment-binding",
    ),
    (
        "envelope.parser_node_binding",
        "DETERMINISTIC_DERIVATION",
        "parser-node-binding",
    ),
)


def load_java_evidence_policy() -> JavaEvidencePolicyManifest:
    rules = tuple(
        JavaEvidencePolicyRule(pattern, JavaEvidenceClass(kind), transformation)
        for pattern, kind, transformation in _RULES
    )
    body = {
        "schema_version": 1,
        "policy_version": JAVA_EVIDENCE_POLICY_VERSION,
        "policy_artifact_hash": bytes_hash(Path(__file__).read_bytes()),
        "rules": rules,
        "rule_count": len(rules),
    }
    return JavaEvidencePolicyManifest(**body, manifest_hash=content_hash(body))


def verify_java_evidence_policy(policy: JavaEvidencePolicyManifest) -> None:
    if policy != load_java_evidence_policy():
        raise ValueError("Java evidence policy artifact or manifest mismatch")


def enumerate_java_evidence_requirements(
    proposal_batch: JavaProposalBatch,
    source_index: JavaSourceIndex,
    policy: JavaEvidencePolicyManifest,
) -> tuple[JavaEvidenceRequirement, ...]:
    verify_java_evidence_policy(policy)
    nodes = declaration_by_node_id(source_index)
    proposals = {item.proposal_id: item for item in proposal_batch.proposals}
    result = []
    for binding in proposal_batch.bindings:
        proposal = proposals[binding.proposal_id]
        declaration = nodes[binding.parser_node_id]
        for field in _field_inventory(proposal, declaration, binding.segment_id):
            body = {
                "proposal_id": proposal.proposal_id,
                "proposal_hash": proposal.proposal_hash,
                "parser_node_id": declaration.node_id,
                "field_path": field[0],
                "evidence_class": field[1],
                "transformation_id": field[2],
                "expected_output": field[3],
                "source_location": field[4],
            }
            result.append(
                JavaEvidenceRequirement(**body, requirement_hash=content_hash(body))
            )
    ordered = tuple(
        sorted(result, key=lambda item: (item.proposal_id, item.field_path))
    )
    keys = {(item.proposal_id, item.field_path) for item in ordered}
    if len(keys) != len(ordered):
        raise ValueError("Java evidence policy produced duplicate requirements")
    return ordered


def _field_inventory(proposal, declaration, segment_id):
    if not isinstance(proposal.proposed_content, ClaimSchemaContent):
        raise TypeError("Java AST proposal must contain ClaimSchemaContent")
    content = proposal.proposed_content
    name = declaration.name_span
    declaration_span = declaration.declaration_span
    fields = [
        _field(
            "content.subject_type", "FIXED_SCHEMA_METADATA", content.subject_type, name
        ),
        _field("content.predicate_id", "DIRECT_SOURCE", content.predicate_id, name),
        _field(
            "content.object_type", "FIXED_SCHEMA_METADATA", content.object_type, name
        ),
        _field(
            "content.qualifier_ids",
            "FIXED_SCHEMA_METADATA",
            content.qualifier_ids,
            name,
        ),
        _field(
            "content.receiver_type",
            "DETERMINISTIC_DERIVATION",
            content.receiver_type,
            name,
        ),
    ]
    for index, ((parameter_name, parameter_type), parameter) in enumerate(
        zip(content.parameters, declaration.parameters, strict=True)
    ):
        fields.extend(
            (
                _field(
                    f"content.parameters[{index}].name",
                    "DIRECT_SOURCE",
                    parameter_name,
                    parameter.name_span,
                    "parameter-name",
                ),
                _field(
                    f"content.parameters[{index}].type",
                    "DIRECT_SOURCE",
                    parameter_type,
                    parameter.type_span,
                    "parameter-source-type",
                ),
            )
        )
    if declaration.member_kind == "constructor":
        fields.append(
            _field(
                "content.return_type",
                "DETERMINISTIC_DERIVATION",
                content.return_type,
                declaration.name_span,
                "constructor-void-return",
            )
        )
    else:
        fields.append(
            _field(
                "content.return_type",
                "DIRECT_SOURCE",
                content.return_type,
                declaration.type_token_spans[-1],
                "return-source-type",
            )
        )
    fields.extend(
        _collection_fields(
            "content.generic_constraints",
            content.generic_constraints,
            "DETERMINISTIC_DERIVATION",
            "generic-constraint",
            declaration_span,
        )
    )
    fields.extend(
        (
            _field(
                "content.preconditions",
                "FIXED_SCHEMA_METADATA",
                content.preconditions,
                name,
            ),
            _field(
                "content.postconditions",
                "FIXED_SCHEMA_METADATA",
                content.postconditions,
                name,
            ),
        )
    )
    fields.extend(
        _collection_fields(
            "content.declared_exceptions",
            content.declared_exceptions,
            "DIRECT_SOURCE",
            "declared-exception",
            declaration_span,
        )
    )
    fields.extend(
        (
            _field(
                "content.deprecated_since",
                "NOT_APPLICABLE",
                content.deprecated_since,
                name,
            ),
            _field("content.examples", "NOT_APPLICABLE", content.examples, name),
            _field(
                "envelope.proposed_kind",
                "FIXED_SCHEMA_METADATA",
                proposal.proposed_kind,
                name,
            ),
            _field(
                "envelope.epistemic_character",
                "FIXED_SCHEMA_METADATA",
                proposal.proposed_epistemic_character,
                name,
            ),
            _field(
                "envelope.extraction_method",
                "FIXED_SCHEMA_METADATA",
                proposal.extraction_method,
                name,
            ),
            _field(
                "envelope.status_authority",
                "DETERMINISTIC_DERIVATION",
                proposal.status,
                name,
            ),
            _field(
                "envelope.ambiguity_fields",
                "DETERMINISTIC_DERIVATION",
                proposal.ambiguity_fields,
                declaration_span,
            ),
            _field(
                "envelope.source_segment_binding",
                "DETERMINISTIC_DERIVATION",
                segment_id,
                declaration_span,
            ),
            _field(
                "envelope.parser_node_binding",
                "DETERMINISTIC_DERIVATION",
                declaration.node_id,
                declaration_span,
            ),
        )
    )
    return tuple(fields)


def _field(path, kind, value, location, transformation=None):
    rule = (
        transformation
        or {
            "content.subject_type": "fixed-subject-type",
            "content.predicate_id": "member-name",
            "content.object_type": "fixed-object-type",
            "content.qualifier_ids": "fixed-empty-qualifiers",
            "content.receiver_type": "receiver-type",
            "content.preconditions": "fixed-empty-preconditions",
            "content.postconditions": "fixed-empty-postconditions",
            "content.deprecated_since": "absent-deprecated-since",
            "content.examples": "absent-examples",
            "envelope.proposed_kind": "fixed-proposed-kind",
            "envelope.epistemic_character": "fixed-epistemic-character",
            "envelope.extraction_method": "fixed-extraction-method",
            "envelope.status_authority": "status-authority",
            "envelope.ambiguity_fields": "ambiguity-fields",
            "envelope.source_segment_binding": "source-segment-binding",
            "envelope.parser_node_binding": "parser-node-binding",
        }[path]
    )
    return (path, JavaEvidenceClass(kind), rule, canonical_json(value), location)


def _collection_fields(prefix, values, kind, transformation, location):
    if not values:
        return (
            _field(
                prefix,
                "NOT_APPLICABLE",
                values,
                location,
                f"empty-{transformation}",
            ),
        )
    return tuple(
        _field(f"{prefix}[{index}]", kind, value, location, transformation)
        for index, value in enumerate(values)
    )
