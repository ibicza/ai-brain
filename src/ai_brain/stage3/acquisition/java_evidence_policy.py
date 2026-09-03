"""Independent, exhaustive field inventory for Java trust evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
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
M343_JAVA_EVIDENCE_POLICY_VERSION = "m343.executable-java-evidence-policy.v1"
M344_JAVA_EVIDENCE_POLICY_VERSION = "m344.production-java-evidence-policy.v1"
_M342_POLICY_ARTIFACT_HASH = (
    "49e50398c3f568afdf74ab4a261c44396efcc1e9075001d6d3ee1578ffa99afd"
)


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
class ExecutableJavaEvidencePolicyRule:
    rule_id: str
    field_pattern: str
    evidence_class: JavaEvidenceClass
    transformation_id: str
    applicability: str
    required: bool
    corpus_inapplicable_allowed: bool
    rule_hash: str


@dataclass(frozen=True)
class JavaEvidencePolicyManifest:
    schema_version: int
    policy_version: str
    policy_artifact_hash: str
    rules: tuple[JavaEvidencePolicyRule | ExecutableJavaEvidencePolicyRule, ...]
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
    policy_rule_id: str | None
    policy_rule_hash: str | None
    requirement_hash: str


@dataclass(frozen=True)
class JavaEvidencePolicyCoverage:
    policy_manifest_hash: str
    generated_field_count: int
    exactly_matched_field_count: int
    unmatched_fields: tuple[str, ...]
    multiply_matched_fields: tuple[str, ...]
    unknown_proposal_fields: tuple[str, ...]
    rule_match_counts: tuple[tuple[str, int], ...]
    zero_match_mandatory_rules: tuple[str, ...]
    coverage_hash: str


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

_M343_RULES = (
    (
        "subject",
        "content.subject_type",
        "FIXED_SCHEMA_METADATA",
        "subject-type",
        "ALL",
        True,
        False,
    ),
    (
        "predicate-method",
        "content.predicate_id",
        "DIRECT_SOURCE",
        "member-name",
        "METHOD",
        True,
        False,
    ),
    (
        "predicate-constructor",
        "content.predicate_id",
        "DETERMINISTIC_DERIVATION",
        "constructor-predicate",
        "CONSTRUCTOR",
        True,
        False,
    ),
    (
        "object",
        "content.object_type",
        "DETERMINISTIC_DERIVATION",
        "java-object-type",
        "ALL",
        True,
        False,
    ),
    (
        "qualifiers",
        "content.qualifier_ids",
        "FIXED_SCHEMA_METADATA",
        "fixed-empty-qualifiers",
        "ALL",
        True,
        False,
    ),
    (
        "receiver",
        "content.receiver_type",
        "DETERMINISTIC_DERIVATION",
        "receiver-type",
        "ALL",
        True,
        False,
    ),
    (
        "parameter-name",
        "content.parameters[*].name",
        "DIRECT_SOURCE",
        "parameter-name",
        "ALL",
        True,
        False,
    ),
    (
        "parameter-type",
        "content.parameters[*].type",
        "DIRECT_SOURCE",
        "parameter-source-type",
        "ALL",
        True,
        False,
    ),
    (
        "parameters-empty",
        "content.parameters",
        "NOT_APPLICABLE",
        "empty-parameters",
        "ALL",
        False,
        True,
    ),
    (
        "return-method",
        "content.return_type",
        "DIRECT_SOURCE",
        "return-source-type",
        "METHOD",
        True,
        False,
    ),
    (
        "return-constructor",
        "content.return_type",
        "DETERMINISTIC_DERIVATION",
        "constructor-return-type",
        "CONSTRUCTOR",
        True,
        False,
    ),
    (
        "generic-constraint",
        "content.generic_constraints[*]",
        "DETERMINISTIC_DERIVATION",
        "generic-constraint",
        "ALL",
        True,
        False,
    ),
    (
        "generic-empty",
        "content.generic_constraints",
        "NOT_APPLICABLE",
        "empty-generic-constraints",
        "ALL",
        False,
        True,
    ),
    (
        "preconditions",
        "content.preconditions",
        "FIXED_SCHEMA_METADATA",
        "fixed-empty-preconditions",
        "ALL",
        True,
        False,
    ),
    (
        "postconditions",
        "content.postconditions",
        "FIXED_SCHEMA_METADATA",
        "fixed-empty-postconditions",
        "ALL",
        True,
        False,
    ),
    (
        "exception-source",
        "content.declared_exceptions[*]",
        "DIRECT_SOURCE",
        "declared-exception-source",
        "ALL",
        True,
        False,
    ),
    (
        "exceptions-empty",
        "content.declared_exceptions",
        "NOT_APPLICABLE",
        "empty-declared-exceptions",
        "ALL",
        False,
        True,
    ),
    (
        "deprecated-present",
        "content.deprecated_since",
        "DIRECT_SOURCE",
        "deprecated-since",
        "DEPRECATED",
        True,
        False,
    ),
    (
        "deprecated-absent",
        "content.deprecated_since",
        "NOT_APPLICABLE",
        "absent-deprecated-since",
        "NOT_DEPRECATED",
        True,
        False,
    ),
    (
        "examples",
        "content.examples",
        "NOT_APPLICABLE",
        "fixed-empty-examples",
        "ALL",
        True,
        False,
    ),
    (
        "callable-kind",
        "content.java_callable_kind",
        "DETERMINISTIC_DERIVATION",
        "callable-kind",
        "ALL",
        True,
        False,
    ),
    (
        "resolved-parameter",
        "content.resolved_parameter_types[*]",
        "DETERMINISTIC_DERIVATION",
        "resolved-parameter-type",
        "ALL",
        True,
        False,
    ),
    (
        "resolved-parameters-empty",
        "content.resolved_parameter_types",
        "NOT_APPLICABLE",
        "empty-resolved-parameters",
        "ALL",
        False,
        True,
    ),
    (
        "parameter-dimension",
        "content.parameter_array_dimensions[*]",
        "DETERMINISTIC_DERIVATION",
        "parameter-array-dimensions",
        "ALL",
        True,
        False,
    ),
    (
        "parameter-dimensions-empty",
        "content.parameter_array_dimensions",
        "NOT_APPLICABLE",
        "empty-parameter-dimensions",
        "ALL",
        False,
        True,
    ),
    (
        "parameter-varargs",
        "content.parameter_varargs[*]",
        "DETERMINISTIC_DERIVATION",
        "parameter-varargs",
        "ALL",
        True,
        False,
    ),
    (
        "parameter-varargs-empty",
        "content.parameter_varargs",
        "NOT_APPLICABLE",
        "empty-parameter-varargs",
        "ALL",
        False,
        True,
    ),
    (
        "resolved-return",
        "content.resolved_return_type",
        "DETERMINISTIC_DERIVATION",
        "resolved-return-type",
        "ALL",
        True,
        False,
    ),
    (
        "return-dimension",
        "content.return_array_dimensions",
        "DETERMINISTIC_DERIVATION",
        "return-array-dimensions",
        "ALL",
        True,
        False,
    ),
    (
        "type-parameter",
        "content.method_type_parameters[*]",
        "DIRECT_SOURCE",
        "method-type-parameter",
        "ALL",
        True,
        False,
    ),
    (
        "type-parameters-empty",
        "content.method_type_parameters",
        "NOT_APPLICABLE",
        "empty-method-type-parameters",
        "ALL",
        False,
        True,
    ),
    (
        "intersection-bound",
        "content.intersection_bounds[*][*]",
        "DIRECT_SOURCE",
        "intersection-bound",
        "ALL",
        True,
        False,
    ),
    (
        "intersection-shape",
        "content.intersection_bounds",
        "DETERMINISTIC_DERIVATION",
        "intersection-bound-shape",
        "ALL",
        False,
        True,
    ),
    (
        "first-bound",
        "content.first_bound_erasures[*]",
        "DETERMINISTIC_DERIVATION",
        "first-bound-erasure",
        "ALL",
        True,
        False,
    ),
    (
        "first-bounds-empty",
        "content.first_bound_erasures",
        "NOT_APPLICABLE",
        "empty-first-bound-erasures",
        "ALL",
        False,
        True,
    ),
    (
        "resolved-exception",
        "content.resolved_declared_exceptions[*]",
        "DETERMINISTIC_DERIVATION",
        "resolved-declared-exception",
        "ALL",
        True,
        False,
    ),
    (
        "resolved-exceptions-empty",
        "content.resolved_declared_exceptions",
        "NOT_APPLICABLE",
        "empty-resolved-exceptions",
        "ALL",
        False,
        True,
    ),
    (
        "modifier",
        "content.modifiers[*]",
        "DIRECT_SOURCE",
        "modifier",
        "ALL",
        True,
        False,
    ),
    (
        "modifiers-empty",
        "content.modifiers",
        "NOT_APPLICABLE",
        "empty-modifiers",
        "ALL",
        False,
        True,
    ),
    (
        "accessibility",
        "content.accessibility",
        "DETERMINISTIC_DERIVATION",
        "accessibility",
        "ALL",
        True,
        False,
    ),
    (
        "enclosing-access",
        "content.enclosing_type_accessibility",
        "DETERMINISTIC_DERIVATION",
        "enclosing-accessibility",
        "ALL",
        True,
        False,
    ),
    (
        "module",
        "content.module_name",
        "NOT_APPLICABLE",
        "module-name",
        "ALL",
        True,
        False,
    ),
    (
        "package-export",
        "content.package_exported",
        "DETERMINISTIC_DERIVATION",
        "package-exported",
        "ALL",
        True,
        False,
    ),
    (
        "envelope-kind",
        "envelope.proposed_kind",
        "FIXED_SCHEMA_METADATA",
        "fixed-proposed-kind",
        "ALL",
        True,
        False,
    ),
    (
        "envelope-epistemic",
        "envelope.epistemic_character",
        "FIXED_SCHEMA_METADATA",
        "fixed-epistemic-character",
        "ALL",
        True,
        False,
    ),
    (
        "envelope-extraction",
        "envelope.extraction_method",
        "FIXED_SCHEMA_METADATA",
        "fixed-extraction-method",
        "ALL",
        True,
        False,
    ),
    (
        "envelope-status",
        "envelope.status_authority",
        "DETERMINISTIC_DERIVATION",
        "status-authority",
        "ALL",
        True,
        False,
    ),
    (
        "envelope-ambiguity",
        "envelope.ambiguity_fields",
        "DETERMINISTIC_DERIVATION",
        "ambiguity-fields",
        "ALL",
        True,
        False,
    ),
    (
        "envelope-segment",
        "envelope.source_segment_binding",
        "DETERMINISTIC_DERIVATION",
        "source-segment-binding",
        "ALL",
        True,
        False,
    ),
    (
        "envelope-node",
        "envelope.parser_node_binding",
        "DETERMINISTIC_DERIVATION",
        "parser-node-binding",
        "ALL",
        True,
        False,
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
        "policy_artifact_hash": _M342_POLICY_ARTIFACT_HASH,
        "rules": rules,
        "rule_count": len(rules),
    }
    return JavaEvidencePolicyManifest(**body, manifest_hash=content_hash(body))


def load_executable_java_evidence_policy() -> JavaEvidencePolicyManifest:
    rules = []
    for values in _M343_RULES:
        body = {
            "rule_id": values[0],
            "field_pattern": values[1],
            "evidence_class": JavaEvidenceClass(values[2]),
            "transformation_id": values[3],
            "applicability": values[4],
            "required": values[5],
            "corpus_inapplicable_allowed": values[6],
        }
        rules.append(
            ExecutableJavaEvidencePolicyRule(**body, rule_hash=content_hash(body))
        )
    body = {
        "schema_version": 2,
        "policy_version": M343_JAVA_EVIDENCE_POLICY_VERSION,
        "policy_artifact_hash": bytes_hash(Path(__file__).read_bytes()),
        "rules": tuple(rules),
        "rule_count": len(rules),
    }
    return JavaEvidencePolicyManifest(**body, manifest_hash=content_hash(body))


def load_production_java_evidence_policy() -> JavaEvidencePolicyManifest:
    """Return the frozen production policy without corpus-shape assumptions.

    Rules remain mandatory whenever applicable to a proposal.  A rule applying
    only to a construct (for example constructors or generic bounds) may have a
    zero corpus denominator; diversity is enforced separately by the corpus
    gate and must never weaken per-proposal evidence completeness.
    """

    rules = []
    for values in _M343_RULES:
        applicability = values[4]
        body = {
            "rule_id": values[0],
            "field_pattern": values[1],
            "evidence_class": JavaEvidenceClass(values[2]),
            "transformation_id": values[3],
            "applicability": applicability,
            "required": values[5],
            "corpus_inapplicable_allowed": (
                values[6] or applicability != "ALL" or "[*]" in values[1]
            ),
        }
        rules.append(
            ExecutableJavaEvidencePolicyRule(**body, rule_hash=content_hash(body))
        )
    body = {
        "schema_version": 3,
        "policy_version": M344_JAVA_EVIDENCE_POLICY_VERSION,
        "policy_artifact_hash": bytes_hash(Path(__file__).read_bytes()),
        "rules": tuple(rules),
        "rule_count": len(rules),
    }
    return JavaEvidencePolicyManifest(**body, manifest_hash=content_hash(body))


def verify_java_evidence_policy(policy: JavaEvidencePolicyManifest) -> None:
    loaders = {
        1: load_java_evidence_policy,
        2: load_executable_java_evidence_policy,
        3: load_production_java_evidence_policy,
    }
    try:
        expected = loaders[policy.schema_version]()
    except KeyError as error:
        raise ValueError("unknown Java evidence policy schema") from error
    if policy != expected:
        raise ValueError("Java evidence policy artifact or manifest mismatch")


def enumerate_java_evidence_requirements(
    proposal_batch: JavaProposalBatch,
    source_index: JavaSourceIndex,
    policy: JavaEvidencePolicyManifest,
) -> tuple[JavaEvidenceRequirement, ...]:
    verify_java_evidence_policy(policy)
    if policy.schema_version in {2, 3}:
        requirements, coverage = match_java_evidence_policy(
            proposal_batch, source_index, policy
        )
        if (
            coverage.unmatched_fields
            or coverage.multiply_matched_fields
            or coverage.unknown_proposal_fields
            or coverage.zero_match_mandatory_rules
        ):
            raise ValueError("executable Java evidence policy coverage failed")
        return requirements
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
                "policy_rule_id": None,
                "policy_rule_hash": None,
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


def match_java_evidence_policy(
    proposal_batch: JavaProposalBatch,
    source_index: JavaSourceIndex,
    policy: JavaEvidencePolicyManifest,
) -> tuple[tuple[JavaEvidenceRequirement, ...], JavaEvidencePolicyCoverage]:
    if policy.schema_version not in {2, 3}:
        raise ValueError("executable policy matcher requires schema v2 or v3")
    nodes = declaration_by_node_id(source_index)
    proposals = {item.proposal_id: item for item in proposal_batch.proposals}
    result = []
    unmatched = []
    multiple = []
    counts = {item.rule_id: 0 for item in policy.rules}
    seen_content_fields = set()
    for binding in proposal_batch.bindings:
        proposal = proposals[binding.proposal_id]
        declaration = nodes[binding.parser_node_id]
        inventory = _semantic_field_inventory(proposal, declaration, binding.segment_id)
        seen_content_fields.update(
            item[0].split(".", 2)[1].split("[", 1)[0]
            for item in inventory
            if item[0].startswith("content.")
        )
        for path, value, location in inventory:
            matches = tuple(
                rule for rule in policy.rules if _rule_matches(rule, path, declaration)
            )
            if not matches:
                unmatched.append(f"{proposal.proposal_id}:{path}")
                continue
            if len(matches) != 1:
                multiple.append(f"{proposal.proposal_id}:{path}")
                continue
            rule = matches[0]
            counts[rule.rule_id] += 1
            body = {
                "proposal_id": proposal.proposal_id,
                "proposal_hash": proposal.proposal_hash,
                "parser_node_id": declaration.node_id,
                "field_path": path,
                "evidence_class": rule.evidence_class,
                "transformation_id": rule.transformation_id,
                "expected_output": canonical_json(value),
                "source_location": location,
                "policy_rule_id": rule.rule_id,
                "policy_rule_hash": rule.rule_hash,
            }
            result.append(
                JavaEvidenceRequirement(**body, requirement_hash=content_hash(body))
            )
    expected_content_fields = {item.name for item in fields(ClaimSchemaContent)}
    unknown = tuple(sorted(expected_content_fields - seen_content_fields))
    zero = tuple(
        sorted(
            rule.rule_id
            for rule in policy.rules
            if rule.required
            and not rule.corpus_inapplicable_allowed
            and counts[rule.rule_id] == 0
        )
    )
    ordered = tuple(
        sorted(result, key=lambda item: (item.proposal_id, item.field_path))
    )
    coverage_body = {
        "policy_manifest_hash": policy.manifest_hash,
        "generated_field_count": len(ordered) + len(unmatched) + len(multiple),
        "exactly_matched_field_count": len(ordered),
        "unmatched_fields": tuple(sorted(unmatched)),
        "multiply_matched_fields": tuple(sorted(multiple)),
        "unknown_proposal_fields": unknown,
        "rule_match_counts": tuple(sorted(counts.items())),
        "zero_match_mandatory_rules": zero,
    }
    return ordered, JavaEvidencePolicyCoverage(
        **coverage_body, coverage_hash=content_hash(coverage_body)
    )


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


def _semantic_field_inventory(proposal, declaration, segment_id):
    if not isinstance(proposal.proposed_content, ClaimSchemaContent):
        raise TypeError("Java AST proposal must contain ClaimSchemaContent")
    content = proposal.proposed_content
    name = declaration.name_span
    declaration_span = declaration.declaration_span
    callable_type_details = tuple(
        item
        for item in declaration.type_variables_detail
        if all(
            declaration_span.byte_start <= span.byte_start
            and span.byte_end <= declaration_span.byte_end
            for span in item.bound_spans
        )
    )
    result = [
        ("content.subject_type", content.subject_type, name),
        ("content.predicate_id", content.predicate_id, name),
        ("content.object_type", content.object_type, name),
        ("content.qualifier_ids", content.qualifier_ids, name),
        ("content.receiver_type", content.receiver_type, name),
    ]
    if content.parameters:
        for index, ((parameter_name, parameter_type), parameter) in enumerate(
            zip(content.parameters, declaration.parameters, strict=True)
        ):
            result.extend(
                (
                    (
                        f"content.parameters[{index}].name",
                        parameter_name,
                        parameter.name_span,
                    ),
                    (
                        f"content.parameters[{index}].type",
                        parameter_type,
                        parameter.type_span,
                    ),
                )
            )
    else:
        result.append(("content.parameters", content.parameters, name))
    return_location = (
        name
        if declaration.member_kind == "constructor"
        else declaration.type_token_spans[-1]
    )
    result.append(("content.return_type", content.return_type, return_location))
    _append_collection(
        result,
        "content.generic_constraints",
        content.generic_constraints,
        tuple(
            item.bound_spans[0]
            for item in callable_type_details
            if item.explicit_bounds
        ),
        declaration_span,
    )
    result.extend(
        (
            ("content.preconditions", content.preconditions, name),
            ("content.postconditions", content.postconditions, name),
        )
    )
    _append_collection(
        result,
        "content.declared_exceptions",
        content.declared_exceptions,
        declaration.declared_exception_spans,
        declaration_span,
    )
    result.extend(
        (
            (
                "content.deprecated_since",
                content.deprecated_since,
                declaration.deprecation_span or name,
            ),
            ("content.examples", content.examples, name),
            ("content.java_callable_kind", content.java_callable_kind, name),
        )
    )
    _append_collection(
        result,
        "content.resolved_parameter_types",
        content.resolved_parameter_types,
        tuple(item.type_span for item in declaration.parameters),
        name,
    )
    _append_collection(
        result,
        "content.parameter_array_dimensions",
        content.parameter_array_dimensions,
        tuple(item.type_span for item in declaration.parameters),
        name,
    )
    _append_collection(
        result,
        "content.parameter_varargs",
        content.parameter_varargs,
        tuple(item.type_span for item in declaration.parameters),
        name,
    )
    result.extend(
        (
            (
                "content.resolved_return_type",
                content.resolved_return_type,
                return_location,
            ),
            (
                "content.return_array_dimensions",
                content.return_array_dimensions,
                return_location,
            ),
        )
    )
    _append_collection(
        result,
        "content.method_type_parameters",
        content.method_type_parameters,
        tuple(item.bound_spans[0] for item in callable_type_details),
        declaration_span,
    )
    intersection_values = tuple(
        (outer, inner, value)
        for outer, values in enumerate(content.intersection_bounds)
        for inner, value in enumerate(values)
    )
    if intersection_values:
        for outer, inner, value in intersection_values:
            detail = callable_type_details[outer]
            result.append(
                (
                    f"content.intersection_bounds[{outer}][{inner}]",
                    value,
                    detail.bound_spans[inner],
                )
            )
    else:
        result.append(
            (
                "content.intersection_bounds",
                content.intersection_bounds,
                declaration_span,
            )
        )
    _append_collection(
        result,
        "content.first_bound_erasures",
        content.first_bound_erasures,
        tuple(item.bound_spans[0] for item in callable_type_details),
        declaration_span,
    )
    _append_collection(
        result,
        "content.resolved_declared_exceptions",
        content.resolved_declared_exceptions,
        declaration.declared_exception_spans,
        declaration_span,
    )
    _append_collection(
        result,
        "content.modifiers",
        content.modifiers,
        tuple(declaration_span for _ in content.modifiers),
        declaration_span,
    )
    result.extend(
        (
            ("content.accessibility", content.accessibility, declaration_span),
            (
                "content.enclosing_type_accessibility",
                content.enclosing_type_accessibility,
                declaration_span,
            ),
            ("content.module_name", content.module_name, declaration_span),
            ("content.package_exported", content.package_exported, declaration_span),
            ("envelope.proposed_kind", proposal.proposed_kind, name),
            (
                "envelope.epistemic_character",
                proposal.proposed_epistemic_character,
                name,
            ),
            ("envelope.extraction_method", proposal.extraction_method, name),
            ("envelope.status_authority", proposal.status, name),
            ("envelope.ambiguity_fields", proposal.ambiguity_fields, declaration_span),
            ("envelope.source_segment_binding", segment_id, declaration_span),
            ("envelope.parser_node_binding", declaration.node_id, declaration_span),
        )
    )
    return tuple(result)


def _append_collection(result, prefix, values, locations, fallback):
    if not values:
        result.append((prefix, values, fallback))
        return
    if len(values) != len(locations):
        raise ValueError(f"Java evidence source-location coverage mismatch: {prefix}")
    result.extend(
        (f"{prefix}[{index}]", value, locations[index])
        for index, value in enumerate(values)
    )


def _rule_matches(rule, path: str, declaration) -> bool:
    if rule.applicability == "METHOD" and declaration.member_kind != "method":
        return False
    if rule.applicability == "CONSTRUCTOR" and declaration.member_kind != "constructor":
        return False
    if rule.applicability == "DEPRECATED" and declaration.deprecated_since is None:
        return False
    if (
        rule.applicability == "NOT_DEPRECATED"
        and declaration.deprecated_since is not None
    ):
        return False
    pattern = re.escape(rule.field_pattern).replace(r"\[\*\]", r"\[\d+\]")
    return re.fullmatch(pattern, path) is not None


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
