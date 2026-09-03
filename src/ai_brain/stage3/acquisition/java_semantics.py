"""Sound Java callable semantics for Universal Knowledge IR proposals."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.knowledge_ir.records import (
    ClaimSchemaContent,
    EntityTypeRef,
    ValueTypeKind,
    ValueTypeRef,
)

_INTEGRAL = {"byte", "short", "int", "long", "char"}
_FLOATING = {"float", "double"}
_STRING_TYPES = {"String", "java.lang.String", "CharSequence", "java.lang.CharSequence"}


@dataclass(frozen=True)
class JavaSemanticMismatch:
    golden_id: str
    proposal_id: str | None
    field_path: str
    expected_hash: str
    actual_hash: str | None
    mismatch_hash: str


@dataclass(frozen=True)
class JavaSemanticConfusionMatrix:
    exact_true_positive: int
    semantic_false_positive: int
    missing_false_negative: int
    correct_location_wrong_content: int
    spurious_proposal: int
    exact_semantic_precision: str
    exact_semantic_recall: str
    per_field_mismatch_counts: tuple[tuple[str, int], ...]
    mismatches: tuple[JavaSemanticMismatch, ...]
    matrix_hash: str


def build_java_claim_content(declaration) -> ClaimSchemaContent:
    """Map one resolved declaration without a generic STRING fallback."""

    constructor = declaration.member_kind == "constructor"
    object_type = (
        ValueTypeRef(
            ValueTypeKind.ENTITY,
            entity_type=EntityTypeRef(declaration.receiver_type),
        )
        if constructor
        else java_value_type(
            declaration.return_type,
            declaration.resolved_return_type,
        )
    )
    details = tuple(
        item
        for item in declaration.type_variables_detail
        if not hasattr(item, "bound_spans")
        or all(
            declaration.declaration_span.byte_start <= span.byte_start
            and span.byte_end <= declaration.declaration_span.byte_end
            for span in item.bound_spans
        )
    )
    return_dimensions = (
        declaration.return_resolution.array_dimensions
        if declaration.return_resolution is not None
        else 0
    )
    return ClaimSchemaContent(
        subject_type=EntityTypeRef(declaration.receiver_type),
        predicate_id="<init>" if constructor else declaration.member_name,
        object_type=object_type,
        receiver_type=declaration.receiver_type,
        parameters=tuple(
            (parameter.name, _canonical_source_type(parameter.source_type))
            for parameter in declaration.parameters
        ),
        return_type=_canonical_source_type(declaration.return_type),
        generic_constraints=tuple(
            f"{item.name} extends {' & '.join(_canonical_source_type(value) for value in item.bounds)}"
            for item in details
            if item.explicit_bounds
        ),
        declared_exceptions=tuple(
            _canonical_source_type(item) for item in declaration.declared_exceptions
        ),
        deprecated_since=declaration.deprecated_since,
        java_callable_kind="CONSTRUCTOR" if constructor else "METHOD",
        resolved_parameter_types=tuple(
            parameter.resolved_type
            or f"UNRESOLVED:{_canonical_source_type(parameter.source_type)}"
            for parameter in declaration.parameters
        ),
        parameter_array_dimensions=tuple(
            parameter.resolution.array_dimensions if parameter.resolution else 0
            for parameter in declaration.parameters
        ),
        parameter_varargs=tuple(
            parameter.varargs for parameter in declaration.parameters
        ),
        resolved_return_type=(
            declaration.resolved_return_type
            or f"UNRESOLVED:{_canonical_source_type(declaration.return_type)}"
        ),
        return_array_dimensions=return_dimensions,
        method_type_parameters=tuple(item.name for item in details),
        intersection_bounds=tuple(
            (
                tuple(_canonical_source_type(value) for value in item.bounds)
                if item.explicit_bounds
                else ()
            )
            for item in details
        ),
        first_bound_erasures=tuple(
            item.first_bound_erasure
            or f"UNRESOLVED:{_canonical_source_type(item.bounds[0])}"
            for item in details
        ),
        resolved_declared_exceptions=tuple(
            value or f"UNRESOLVED:{_canonical_source_type(source)}"
            for source, value in zip(
                declaration.declared_exceptions,
                declaration.resolved_declared_exceptions,
                strict=True,
            )
        ),
        modifiers=declaration.modifiers,
        accessibility=declaration.accessibility,
        enclosing_type_accessibility=declaration.enclosing_type_accessibility,
        module_name=declaration.module_name,
        package_exported=declaration.package_exported,
    )


def java_value_type(source_type: str | None, resolved_type: str | None) -> ValueTypeRef:
    source_type = _canonical_source_type(source_type)
    resolved_type = _canonical_source_type(resolved_type)
    if (source_type or "").strip().endswith(("[]", "...")) or (
        resolved_type or ""
    ).strip().endswith("[]"):
        return ValueTypeRef(
            ValueTypeKind.ENTITY,
            entity_type=EntityTypeRef(resolved_type or source_type or "UNRESOLVED"),
        )
    source = _base_type(source_type or "")
    resolved = _base_type(resolved_type or "")
    if resolved == "void" or source == "void":
        return ValueTypeRef(ValueTypeKind.VOID)
    if resolved == "boolean" or source == "boolean":
        return ValueTypeRef(ValueTypeKind.BOOLEAN)
    if resolved in _INTEGRAL or source in _INTEGRAL:
        return ValueTypeRef(ValueTypeKind.INTEGER)
    if resolved in _FLOATING or source in _FLOATING:
        return ValueTypeRef(ValueTypeKind.DECIMAL)
    if resolved in _STRING_TYPES or source in _STRING_TYPES:
        return ValueTypeRef(ValueTypeKind.STRING)
    identity = resolved_type or source_type or "UNRESOLVED"
    return ValueTypeRef(
        ValueTypeKind.ENTITY,
        entity_type=EntityTypeRef(identity),
    )


def semantic_content_hash(content: ClaimSchemaContent) -> str:
    return content_hash(asdict(content))


def canonical_semantic_payload(content: ClaimSchemaContent) -> str:
    return canonical_json(asdict(content))


def proposal_field_manifest_hash(content: ClaimSchemaContent) -> str:
    flattened = flatten_semantic_payload(asdict(content))
    return content_hash(tuple(sorted(flattened.items())))


def type_resolution_semantic_manifest_hash(declaration) -> str:
    rows = []
    type_indexes = {}
    for item in declaration.type_occurrence_resolutions:
        field_path = item.field_path
        if field_path.startswith("type_parameters["):
            if not (
                declaration.declaration_span.byte_start
                <= item.source_location.byte_start
                and item.source_location.byte_end
                <= declaration.declaration_span.byte_end
            ):
                continue
            original = int(field_path.split("[", 1)[1].split("]", 1)[0])
            if original not in type_indexes:
                type_indexes[original] = len(type_indexes)
            field_path = re.sub(
                r"^type_parameters\[\d+\]",
                f"type_parameters[{type_indexes[original]}]",
                field_path,
            )
        rows.append(
            (
                field_path,
                _canonical_source_type(item.source_type),
                item.resolution.resolved_type,
                item.resolution.array_dimensions,
            )
        )
    return content_hash(tuple(rows))


def flatten_semantic_payload(value, prefix="content") -> dict[str, object]:
    result: dict[str, object] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            result.update(flatten_semantic_payload(value[key], f"{prefix}.{key}"))
    elif isinstance(value, (list, tuple)):
        if not value:
            result[prefix] = []
        for index, item in enumerate(value):
            result.update(flatten_semantic_payload(item, f"{prefix}[{index}]"))
    else:
        result[prefix] = value
    return result


def semantic_content_confusion(
    golden_manifest,
    proposal_batch,
    source_index,
    trust_decisions=(),
    *,
    include_semantic_status=True,
):
    declarations = {item.node_id: item for item in source_index.declarations}
    proposals = {item.proposal_id: item for item in proposal_batch.proposals}
    decisions = {item.proposal_id: item for item in trust_decisions}
    by_location: dict[tuple, list[tuple]] = {}
    for binding in proposal_batch.bindings:
        declaration = declarations[binding.parser_node_id]
        key = (
            declaration.source_snapshot_hash,
            declaration.source_unit_id,
            declaration.declaration_span.byte_start,
            declaration.declaration_span.byte_end,
        )
        by_location.setdefault(key, []).append(
            (proposals[binding.proposal_id], declaration)
        )
    expected_locations = set()
    exact = 0
    wrong_content = 0
    mismatches = []
    field_counts: Counter[str] = Counter()
    for golden in golden_manifest.goldens:
        key = (
            golden.document_bytes_hash,
            golden.source_unit_id,
            golden.start_offset,
            golden.end_offset,
        )
        expected_locations.add(key)
        values = by_location.get(key, ())
        if len(values) != 1 or golden.expected_semantics is None:
            continue
        proposal, declaration = values[0]
        semantics = golden.expected_semantics
        expected_content = json.loads(semantics.expected_claim_payload)
        actual_content = asdict(proposal.proposed_content)
        decision = decisions.get(proposal.proposal_id)
        if decision is None:
            actual_supported = declaration.supported
            actual_blocker = (
                None if declaration.supported else declaration.unsupported_reason
            )
        else:
            actual_supported = decision.final_state.value == "trusted"
            actual_blocker = _normalized_blocker(decision.blocker_reason)
        expected = {
            "content": expected_content,
            "envelope": {
                "knowledge_kind": semantics.expected_knowledge_kind,
                "epistemic_character": semantics.expected_epistemic_character,
            },
            "semantic_status": {
                "supported": semantics.expected_supported,
                "blocker_reason": semantics.expected_blocker_reason,
            },
        }
        actual = {
            "content": actual_content,
            "envelope": {
                "knowledge_kind": proposal.proposed_kind.value,
                "epistemic_character": proposal.proposed_epistemic_character.value,
            },
            "semantic_status": {
                "supported": actual_supported,
                "blocker_reason": actual_blocker,
            },
        }
        if not include_semantic_status:
            expected.pop("semantic_status")
            actual.pop("semantic_status")
        exact_value = (
            canonical_json(expected) == canonical_json(actual)
            and golden.canonical_source_signature
            == declaration.canonical_source_signature
            and golden.erased_jvm_descriptor == declaration.erased_jvm_descriptor
            and semantics.complete_type_resolution_manifest_hash
            == type_resolution_semantic_manifest_hash(declaration)
            and semantics.complete_proposal_field_manifest_hash
            == proposal_field_manifest_hash(proposal.proposed_content)
        )
        if exact_value:
            exact += 1
            continue
        wrong_content += 1
        expected_fields = flatten_semantic_payload(expected)
        actual_fields = flatten_semantic_payload(actual)
        for field in sorted(set(expected_fields) | set(actual_fields)):
            if expected_fields.get(field) == actual_fields.get(field):
                continue
            field_counts[field] += 1
            body = {
                "golden_id": golden.golden_id,
                "proposal_id": proposal.proposal_id,
                "field_path": field,
                "expected_hash": content_hash(expected_fields.get(field)),
                "actual_hash": (
                    content_hash(actual_fields[field])
                    if field in actual_fields
                    else None
                ),
            }
            mismatches.append(
                JavaSemanticMismatch(**body, mismatch_hash=content_hash(body))
            )
    spurious = sum(
        len(values)
        for key, values in by_location.items()
        if key not in expected_locations
    )
    total = len(golden_manifest.goldens)
    semantic_fp = wrong_content + spurious
    missing = total - exact
    body = {
        "exact_true_positive": exact,
        "semantic_false_positive": semantic_fp,
        "missing_false_negative": missing,
        "correct_location_wrong_content": wrong_content,
        "spurious_proposal": spurious,
        "exact_semantic_precision": ratio(exact, exact + semantic_fp),
        "exact_semantic_recall": ratio(exact, total),
        "per_field_mismatch_counts": tuple(sorted(field_counts.items())),
        "mismatches": tuple(mismatches),
    }
    return JavaSemanticConfusionMatrix(**body, matrix_hash=content_hash(body))


def ratio(numerator: int, denominator: int) -> str:
    return "N/A" if denominator == 0 else f"{numerator / denominator:.6f}"


def _normalized_blocker(value: str | None) -> str | None:
    if value is None:
        return None
    diagnostic = "untrusted_compiler_diagnostic:"
    if value.startswith(diagnostic):
        return value.removeprefix(diagnostic)
    return value


def _base_type(value: str) -> str:
    text = re.sub(r"@[\w.]+(?:\s*\([^)]*\))?\s*", "", value).strip()
    text = text.removesuffix("...")
    while text.endswith("[]"):
        text = text[:-2]
    result = []
    depth = 0
    for character in text:
        if character == "<":
            depth += 1
        elif character == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            result.append(character)
    return "".join(result).strip()


def _canonical_source_type(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r",\s+", ",", value.strip())
