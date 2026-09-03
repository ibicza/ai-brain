"""Pinned, independently executed Java evidence transformations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.models import ExtractionMethod, ProposalStatus
from ai_brain.stage3.knowledge_ir.records import (
    EntityTypeRef,
    EpistemicCharacter,
    KnowledgeKind,
    ValueTypeKind,
    ValueTypeRef,
)

TRANSFORMATION_VERSION = "m343.independent-java-evidence-transforms.v1"


@dataclass(frozen=True)
class JavaEvidenceTransformationManifest:
    schema_version: int
    version: str
    source_artifact_hash: str
    transformation_ids: tuple[str, ...]
    transformation_manifest_hash: str


def load_java_evidence_transformation_manifest():
    identifiers = tuple(sorted(_TRANSFORMATIONS))
    body = {
        "schema_version": 1,
        "version": TRANSFORMATION_VERSION,
        "source_artifact_hash": bytes_hash(Path(__file__).read_bytes()),
        "transformation_ids": identifiers,
    }
    return JavaEvidenceTransformationManifest(
        **body, transformation_manifest_hash=content_hash(body)
    )


def execute_java_evidence_transformation(
    transformation_id,
    *,
    requirement,
    declaration,
    proposal,
    binding,
    raw_source: bytes,
):
    try:
        function = _TRANSFORMATIONS[transformation_id]
    except KeyError as error:
        raise ValueError("unknown Java evidence transformation") from error
    return function(requirement, declaration, proposal, binding, raw_source)


def _index(path: str, occurrence: int = 0) -> int:
    values = tuple(int(item) for item in re.findall(r"\[(\d+)\]", path))
    return values[occurrence]


def _span(raw: bytes, location) -> str:
    return raw[location.byte_start : location.byte_end].decode("utf-8", errors="strict")


def _member_name(requirement, declaration, *_args):
    return _span(_args[-1], declaration.name_span)


def _constructor_predicate(*_args):
    return "<init>"


def _parameter_name(requirement, declaration, *_args):
    parameter = declaration.parameters[_index(requirement.field_path)]
    return _span(_args[-1], parameter.name_span)


def _parameter_source_type(requirement, declaration, *_args):
    parameter = declaration.parameters[_index(requirement.field_path)]
    value = _normalize_type(_span(_args[-1], parameter.type_span))
    expected = _normalize_type(parameter.source_type)
    if value + ("..." if parameter.varargs else "") == expected:
        return expected
    compact_value = re.sub(r"\s+", "", value)
    compact_expected = re.sub(r"\s+", "", expected)
    if (
        parameter.name in value
        and _base_type(compact_expected) in compact_value
        and compact_value.count("[]") == compact_expected.count("[]")
    ):
        return expected
    raise ValueError("parameter source-type transformation is not source-entailed")


def _return_source_type(_requirement, declaration, *_args):
    if declaration.member_kind == "constructor":
        return "void"
    return _normalize_type(_span(_args[-1], declaration.type_token_spans[-1]))


def _constructor_return(*_args):
    return "void"


def _subject_type(_requirement, declaration, *_args):
    return EntityTypeRef(declaration.receiver_type)


def _receiver_type(_requirement, declaration, *_args):
    return declaration.receiver_type


def _java_object_type(_requirement, declaration, *_args):
    source_return = _normalize_type(declaration.return_type or "")
    resolved_return = _normalize_type(declaration.resolved_return_type or "")
    if declaration.member_kind == "constructor":
        return ValueTypeRef(
            ValueTypeKind.ENTITY, EntityTypeRef(declaration.receiver_type)
        )
    if source_return.endswith(("[]", "...")) or resolved_return.endswith("[]"):
        return ValueTypeRef(
            ValueTypeKind.ENTITY,
            EntityTypeRef(resolved_return or source_return),
        )
    source = _base_type(source_return)
    resolved = _base_type(resolved_return)
    if source == "void" or resolved == "void":
        return ValueTypeRef(ValueTypeKind.VOID)
    if source == "boolean" or resolved == "boolean":
        return ValueTypeRef(ValueTypeKind.BOOLEAN)
    if source in {"byte", "short", "int", "long", "char"} or resolved in {
        "byte",
        "short",
        "int",
        "long",
        "char",
    }:
        return ValueTypeRef(ValueTypeKind.INTEGER)
    if source in {"float", "double"} or resolved in {"float", "double"}:
        return ValueTypeRef(ValueTypeKind.DECIMAL)
    if source in {"String", "CharSequence"} or resolved in {
        "java.lang.String",
        "java.lang.CharSequence",
    }:
        return ValueTypeRef(ValueTypeKind.STRING)
    return ValueTypeRef(
        ValueTypeKind.ENTITY,
        EntityTypeRef(resolved_return or source_return),
    )


def _generic_constraint(requirement, declaration, *_args):
    item = tuple(
        value for value in declaration.type_variables_detail if value.explicit_bounds
    )[_index(requirement.field_path)]
    return f"{item.name} extends {' & '.join(_normalize_type(value) for value in item.bounds)}"


def _declared_exception_source(requirement, declaration, *_args):
    index = _index(requirement.field_path)
    return _normalize_type(
        _span(_args[-1], declaration.declared_exception_spans[index])
    )


def _deprecated_since(_requirement, declaration, *_args):
    text = _span(_args[-1], declaration.deprecation_span)
    match = re.search(r'\bsince\s*=\s*"([^"]*)"', text)
    if match is None:
        raise ValueError("deprecated-since transformation lacks source literal")
    return match.group(1)


def _callable_kind(_requirement, declaration, *_args):
    return "CONSTRUCTOR" if declaration.member_kind == "constructor" else "METHOD"


def _resolved_parameter(requirement, declaration, *_args):
    item = declaration.parameters[_index(requirement.field_path)]
    return item.resolved_type or f"UNRESOLVED:{_normalize_type(item.source_type)}"


def _parameter_dimensions(requirement, declaration, *_args):
    item = declaration.parameters[_index(requirement.field_path)]
    return item.resolution.array_dimensions


def _parameter_varargs(requirement, declaration, *_args):
    return declaration.parameters[_index(requirement.field_path)].varargs


def _resolved_return(_requirement, declaration, *_args):
    return declaration.resolved_return_type or (
        f"UNRESOLVED:{_normalize_type(declaration.return_type)}"
    )


def _return_dimensions(_requirement, declaration, *_args):
    return declaration.return_resolution.array_dimensions


def _method_type_parameter(requirement, declaration, *_args):
    return _callable_type_details(declaration)[_index(requirement.field_path)].name


def _intersection_bound(requirement, declaration, *_args):
    value = _callable_type_details(declaration)[_index(requirement.field_path)].bounds[
        _index(requirement.field_path, 1)
    ]
    return _normalize_type(value)


def _intersection_bound_shape(_requirement, declaration, *_args):
    return tuple(
        tuple(_normalize_type(value) for value in item.bounds)
        if item.explicit_bounds
        else ()
        for item in _callable_type_details(declaration)
    )


def _first_bound(requirement, declaration, *_args):
    item = _callable_type_details(declaration)[_index(requirement.field_path)]
    return item.first_bound_erasure or f"UNRESOLVED:{_normalize_type(item.bounds[0])}"


def _resolved_exception(requirement, declaration, *_args):
    index = _index(requirement.field_path)
    return declaration.resolved_declared_exceptions[index] or (
        f"UNRESOLVED:{_normalize_type(declaration.declared_exceptions[index])}"
    )


def _callable_type_details(declaration):
    span = declaration.declaration_span
    return tuple(
        item
        for item in declaration.type_variables_detail
        if all(
            span.byte_start <= location.byte_start
            and location.byte_end <= span.byte_end
            for location in item.bound_spans
        )
    )


def _modifier(requirement, declaration, *_args):
    return declaration.modifiers[_index(requirement.field_path)]


def _accessibility(_requirement, declaration, *_args):
    return declaration.accessibility


def _enclosing_accessibility(_requirement, declaration, *_args):
    return declaration.enclosing_type_accessibility


def _module_name(_requirement, declaration, *_args):
    return declaration.module_name


def _package_exported(_requirement, declaration, *_args):
    return declaration.package_exported


def _ambiguity(_requirement, declaration, *_args):
    return (declaration.unsupported_reason,) if declaration.unsupported_reason else ()


def _segment(_requirement, _declaration, _proposal, binding, _raw):
    return binding.segment_id


def _node(_requirement, declaration, *_args):
    return declaration.node_id


def _constant(value):
    return lambda *_args: value


def _normalize_type(value: str) -> str:
    return re.sub(r",\s+", ",", " ".join(value.split()).replace(" []", "[]"))


def _base_type(value: str) -> str:
    text = _normalize_type(value).removesuffix("...")
    while text.endswith("[]"):
        text = text[:-2]
    depth = 0
    result = []
    for character in text:
        if character == "<":
            depth += 1
        elif character == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            result.append(character)
    return "".join(result).strip()


_EMPTY = _constant(())
_TRANSFORMATIONS = {
    "subject-type": _subject_type,
    "member-name": _member_name,
    "constructor-predicate": _constructor_predicate,
    "java-object-type": _java_object_type,
    "fixed-empty-qualifiers": _EMPTY,
    "receiver-type": _receiver_type,
    "parameter-name": _parameter_name,
    "parameter-source-type": _parameter_source_type,
    "empty-parameters": _EMPTY,
    "return-source-type": _return_source_type,
    "constructor-return-type": _constructor_return,
    "generic-constraint": _generic_constraint,
    "empty-generic-constraints": _EMPTY,
    "fixed-empty-preconditions": _EMPTY,
    "fixed-empty-postconditions": _EMPTY,
    "declared-exception-source": _declared_exception_source,
    "empty-declared-exceptions": _EMPTY,
    "deprecated-since": _deprecated_since,
    "absent-deprecated-since": _constant(None),
    "fixed-empty-examples": _EMPTY,
    "callable-kind": _callable_kind,
    "resolved-parameter-type": _resolved_parameter,
    "empty-resolved-parameters": _EMPTY,
    "parameter-array-dimensions": _parameter_dimensions,
    "empty-parameter-dimensions": _EMPTY,
    "parameter-varargs": _parameter_varargs,
    "empty-parameter-varargs": _EMPTY,
    "resolved-return-type": _resolved_return,
    "return-array-dimensions": _return_dimensions,
    "method-type-parameter": _method_type_parameter,
    "empty-method-type-parameters": _EMPTY,
    "intersection-bound": _intersection_bound,
    "intersection-bound-shape": _intersection_bound_shape,
    "first-bound-erasure": _first_bound,
    "empty-first-bound-erasures": _EMPTY,
    "resolved-declared-exception": _resolved_exception,
    "empty-resolved-exceptions": _EMPTY,
    "modifier": _modifier,
    "empty-modifiers": _EMPTY,
    "accessibility": _accessibility,
    "enclosing-accessibility": _enclosing_accessibility,
    "module-name": _module_name,
    "package-exported": _package_exported,
    "fixed-proposed-kind": _constant(KnowledgeKind.CLAIM_SCHEMA),
    "fixed-epistemic-character": _constant(EpistemicCharacter.NORMATIVE),
    "fixed-extraction-method": _constant(ExtractionMethod.JAVA_AST),
    "status-authority": _constant(ProposalStatus.PROPOSED),
    "ambiguity-fields": _ambiguity,
    "source-segment-binding": _segment,
    "parser-node-binding": _node,
}


def normalized_transformation_output(*args, **kwargs) -> str:
    return canonical_json(execute_java_evidence_transformation(*args, **kwargs))
