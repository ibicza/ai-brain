"""Trust-relevance classification for Java compiler/oracle diagnostics."""

from __future__ import annotations

from enum import StrEnum


class JavaDiagnosticScope(StrEnum):
    DECLARATION_HEADER_BLOCKING = "DECLARATION_HEADER_BLOCKING"
    ENCLOSING_TYPE_BLOCKING = "ENCLOSING_TYPE_BLOCKING"
    BODY_ONLY = "BODY_ONLY"
    AMBIENT_FILE = "AMBIENT_FILE"
    UNRELATED_DECLARATION = "UNRELATED_DECLARATION"
    UNKNOWN_SCOPE = "UNKNOWN_SCOPE"


TRUST_BLOCKING_DIAGNOSTIC_SCOPES = frozenset(
    {
        JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING,
        JavaDiagnosticScope.ENCLOSING_TYPE_BLOCKING,
    }
)


def classify_java_diagnostic_scope(
    *, diagnostic_start: int, diagnostic_end: int, target, declarations, raw: bytes
) -> JavaDiagnosticScope:
    """Classify by byte overlap with the target header/body and its source unit."""

    if diagnostic_start < 0 or diagnostic_end < diagnostic_start:
        return JavaDiagnosticScope.UNKNOWN_SCOPE
    same_unit = tuple(
        item for item in declarations if item.source_unit_id == target.source_unit_id
    )
    if not same_unit:
        return JavaDiagnosticScope.UNKNOWN_SCOPE
    if _overlaps(diagnostic_start, diagnostic_end, target.declaration_span):
        body_start = raw.find(
            b"{", target.declaration_span.byte_start, target.declaration_span.byte_end
        )
        if body_start >= 0 and diagnostic_start > body_start:
            return JavaDiagnosticScope.BODY_ONLY
        return JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING
    enclosing_types = tuple(
        item
        for item in same_unit
        if item.member_kind in {"class", "interface", "enum", "record", "annotation"}
        and item.receiver_type == target.receiver_type
    )
    if any(
        _overlaps(diagnostic_start, diagnostic_end, item.declaration_span)
        for item in enclosing_types
    ):
        return JavaDiagnosticScope.ENCLOSING_TYPE_BLOCKING
    if any(
        _overlaps(diagnostic_start, diagnostic_end, item.declaration_span)
        for item in same_unit
    ):
        return JavaDiagnosticScope.UNRELATED_DECLARATION
    return JavaDiagnosticScope.AMBIENT_FILE


def diagnostic_scope_from_receipt(receipt) -> JavaDiagnosticScope:
    value = getattr(receipt, "applicability", "UNKNOWN_SCOPE")
    aliases = {
        "HEADER": JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING,
        "UNIT_HEADER": JavaDiagnosticScope.ENCLOSING_TYPE_BLOCKING,
        "BODY": JavaDiagnosticScope.BODY_ONLY,
    }
    if value in aliases:
        return aliases[value]
    try:
        return JavaDiagnosticScope(value)
    except ValueError:
        return JavaDiagnosticScope.UNKNOWN_SCOPE


def diagnostic_scope_trust_relevant(scope: JavaDiagnosticScope) -> bool:
    return scope in TRUST_BLOCKING_DIAGNOSTIC_SCOPES


def _overlaps(start: int, end: int, location) -> bool:
    return start < location.byte_end and end > location.byte_start
