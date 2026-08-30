"""Canonical proposal identities and strict Java source-location matching."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from enum import StrEnum

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.models import (
    KnowledgeProposal,
    SourceBundle,
    SourceDocument,
    SourceLocation,
    SourceSegment,
)
from ai_brain.stage3.knowledge_ir.records import ClaimSchemaContent


class IdentityMatch(StrEnum):
    EXACT = "exact_identity_match"
    EQUIVALENT = "equivalent_identity_match"
    AMBIGUOUS = "ambiguous_match"
    CONFLICT = "conflict"
    MISSING = "missing_identity"
    DUPLICATE = "duplicate_identity"


class JavaMemberKind(StrEnum):
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    RECORD = "record"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    FIELD = "field"
    CONSTANT = "constant"
    DOC_CLAIM = "doc_claim"


class IdentityBlocker(StrEnum):
    LOCATION_MISMATCH = "untrusted_location_mismatch"
    AMBIGUOUS_IDENTITY = "untrusted_ambiguous_identity"
    DUPLICATE_SEGMENT = "untrusted_duplicate_segment"
    CONFLICTING_IDENTITY = "untrusted_conflicting_identity"
    MISSING_IDENTITY = "untrusted_missing_identity"


@dataclass(frozen=True)
class CanonicalSemanticIdentity:
    domain: str
    source_document_id: str
    source_snapshot_hash: str
    source_unit_id: str
    package_name: str | None
    top_level_type_name: str | None
    nested_type_path: tuple[str, ...]
    member_kind: str
    member_name: str
    erased_jvm_signature: str | None
    start_line: int
    end_line: int
    start_offset: int
    end_offset: int
    normalized_claim_text_hash: str
    source_evidence_span_hash: str
    identity_hash: str


@dataclass(frozen=True)
class JavaLocationMatch:
    status: IdentityMatch
    proposal_identity_hash: str | None
    resolved_identity_hash: str | None
    candidate_identity_hashes: tuple[str, ...]
    blocker_reason: IdentityBlocker | None
    report_hash: str


@dataclass(frozen=True)
class IdentityConflict:
    conflict_kind: str
    identity_hashes: tuple[str, ...]
    proposal_ids: tuple[str, ...]
    source_locations: tuple[str, ...]
    conflict_hash: str


@dataclass(frozen=True)
class PrecompilerIdentityReport:
    status: str
    proposal_count: int
    identity_count: int
    conflicts: tuple[IdentityConflict, ...]
    duplicate_trusted_proposals: int
    report_hash: str


class PrecompilerIdentityConflict(ValueError):
    def __init__(self, report: PrecompilerIdentityReport) -> None:
        super().__init__("precompiler semantic identity conflict")
        self.report = report


@dataclass(frozen=True)
class _TypeScope:
    name: str
    kind: JavaMemberKind
    body_depth: int


_TYPE = re.compile(
    r"\b(?P<kind>class|interface|enum|record)\s+(?P<name>[A-Za-z_$][\w$]*)"
)
_METHOD = re.compile(
    r"^\s*(?:@[\w.]+(?:\([^)]*\))?\s+)*"
    r"(?:(?:public|protected|private|static|final|abstract|synchronized|native|"
    r"strictfp|default)\s+)*"
    r"(?:<[^>{}]+>\s+)?"
    r"(?:(?P<returns>[\w.$<>?,\[\]\s]+?)\s+)?"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*"
    r"\((?P<parameters>[^()]*)\)"
    r"(?:\s+throws\s+(?P<throws>[^;{]+))?\s*[;{]"
)
_FIELD = re.compile(
    r"^\s*(?P<modifiers>(?:(?:public|protected|private|static|final|volatile|"
    r"transient)\s+)*)"
    r"(?P<type>[\w.$<>?,\[\]]+)\s+(?P<name>[A-Za-z_$][\w$]*)"
    r"(?:\s*=.*)?;\s*$"
)
_CONTROL_NAMES = {"if", "for", "while", "switch", "catch", "try", "new"}


def make_semantic_identity(
    *,
    domain: str,
    source_document_id: str,
    source_snapshot_hash: str,
    source_unit_id: str,
    member_kind: str,
    member_name: str,
    location: SourceLocation,
    claim_text: str,
    source_evidence_span_hash: str,
    package_name: str | None = None,
    top_level_type_name: str | None = None,
    nested_type_path: tuple[str, ...] = (),
    erased_jvm_signature: str | None = None,
) -> CanonicalSemanticIdentity:
    values = {
        "domain": _normalized_name(domain),
        "source_document_id": source_document_id,
        "source_snapshot_hash": source_snapshot_hash,
        "source_unit_id": source_unit_id.replace("\\", "/"),
        "package_name": package_name,
        "top_level_type_name": top_level_type_name,
        "nested_type_path": nested_type_path,
        "member_kind": member_kind,
        "member_name": member_name,
        "erased_jvm_signature": erased_jvm_signature,
        "start_line": location.line_start,
        "end_line": location.line_end,
        "start_offset": location.byte_start,
        "end_offset": location.byte_end,
        "normalized_claim_text_hash": bytes_hash(
            _normalized_claim(claim_text).encode("utf-8")
        ),
        "source_evidence_span_hash": source_evidence_span_hash,
    }
    return CanonicalSemanticIdentity(**values, identity_hash=content_hash(values))


def verify_semantic_identity(value: CanonicalSemanticIdentity) -> None:
    body = asdict(value)
    claimed = body.pop("identity_hash")
    if content_hash(body) != claimed:
        raise ValueError("semantic identity hash mismatch")
    if (
        not value.domain
        or not value.source_document_id
        or not value.source_snapshot_hash
        or not value.source_unit_id
        or not value.member_kind
        or not value.member_name
        or value.start_line < 1
        or value.end_line < value.start_line
        or value.start_offset < 0
        or value.end_offset <= value.start_offset
    ):
        raise ValueError("semantic identity is incomplete")


def parse_java_source_identities(
    document: SourceDocument, raw: bytes
) -> tuple[CanonicalSemanticIdentity, ...]:
    """Parse bounded Java declarations at their physical source locations.

    This deliberately recognizes declarations only at a type-body depth. It is
    not a Java compiler and never treats similarity or proximity as identity.
    """

    if bytes_hash(raw) != document.bytes_hash:
        raise ValueError("Java source document hash mismatch")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Java source is not UTF-8") from error
    package_match = re.search(
        r"(?m)^\s*package\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*;",
        text,
    )
    package = package_match.group(1) if package_match else None
    scopes: list[_TypeScope] = []
    result: list[CanonicalSemanticIdentity] = []
    depth = 0
    byte_offset = 0
    in_block_comment = False
    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        encoded = line.encode("utf-8")
        line_end = byte_offset + len(encoded)
        visible, in_block_comment = _without_comments(line, in_block_comment)
        while scopes and depth < scopes[-1].body_depth:
            scopes.pop()
        type_match = _TYPE.search(visible)
        declaration_open = visible.find("{", type_match.end() if type_match else 0)
        if type_match and declaration_open >= 0:
            kind = JavaMemberKind(type_match.group("kind"))
            name = type_match.group("name")
            location = SourceLocation(
                byte_offset,
                line_end,
                line_number,
                line_number,
                tuple(scope.name for scope in scopes),
            )
            span_hash = bytes_hash(raw[byte_offset:line_end])
            names = tuple(scope.name for scope in scopes) + (name,)
            result.append(
                make_semantic_identity(
                    domain="java",
                    source_document_id=document.document_id,
                    source_snapshot_hash=document.bytes_hash,
                    source_unit_id=document.relative_path,
                    package_name=package,
                    top_level_type_name=names[0],
                    nested_type_path=names[1:],
                    member_kind=kind.value,
                    member_name=name,
                    location=location,
                    claim_text=visible,
                    source_evidence_span_hash=span_hash,
                )
            )
            scopes.append(_TypeScope(name, kind, depth + 1))
        elif scopes and depth == scopes[-1].body_depth:
            method = _METHOD.match(visible)
            if method and method.group("name") not in _CONTROL_NAMES:
                name = method.group("name")
                constructor = name == scopes[-1].name and not method.group("returns")
                kind = (
                    JavaMemberKind.CONSTRUCTOR if constructor else JavaMemberKind.METHOD
                )
                return_type = "void" if constructor else method.group("returns")
                parameter_types = _parameter_types(method.group("parameters"))
                signature = erased_jvm_signature(
                    "<init>" if constructor else name,
                    parameter_types,
                    "void" if constructor else (return_type or "void"),
                    package,
                )
                result.append(
                    _java_member_identity(
                        document,
                        raw,
                        byte_offset,
                        line_end,
                        line_number,
                        visible,
                        scopes,
                        kind,
                        name,
                        signature,
                        package,
                    )
                )
            elif "(" not in visible:
                field = _FIELD.match(visible)
                if field:
                    modifiers = set(field.group("modifiers").split())
                    kind = (
                        JavaMemberKind.CONSTANT
                        if {"static", "final"} <= modifiers
                        else JavaMemberKind.FIELD
                    )
                    result.append(
                        _java_member_identity(
                            document,
                            raw,
                            byte_offset,
                            line_end,
                            line_number,
                            visible,
                            scopes,
                            kind,
                            field.group("name"),
                            None,
                            package,
                        )
                    )
        depth += visible.count("{") - visible.count("}")
        while scopes and depth < scopes[-1].body_depth:
            scopes.pop()
        byte_offset = line_end
    values = tuple(
        sorted(result, key=lambda item: (item.start_offset, item.identity_hash))
    )
    for value in values:
        verify_semantic_identity(value)
    return values


def identity_from_java_proposal(
    proposal: KnowledgeProposal,
    bundle: SourceBundle,
    segment: SourceSegment,
) -> CanonicalSemanticIdentity:
    if not isinstance(proposal.proposed_content, ClaimSchemaContent):
        raise TypeError("Java proposal identity requires claim-schema content")
    document = next(
        (item for item in bundle.documents if item.document_id == segment.document_id),
        None,
    )
    if document is None:
        raise ValueError("proposal segment document is outside source bundle")
    content = proposal.proposed_content
    receiver = (content.receiver_type or "").replace("$", ".")
    type_parts = tuple(item for item in receiver.split(".") if item)
    package_parts = []
    type_start = 0
    for index, part in enumerate(type_parts):
        if part[:1].isupper():
            type_start = index
            break
        package_parts.append(part)
    type_names = type_parts[type_start:] if type_parts else ()
    package = ".".join(package_parts) or None
    parameter_types = tuple(value for _, value in content.parameters)
    signature = erased_jvm_signature(
        content.predicate_id,
        parameter_types,
        content.return_type or "void",
        package,
    )
    return make_semantic_identity(
        domain="java",
        source_document_id=document.document_id,
        source_snapshot_hash=document.bytes_hash,
        source_unit_id=document.relative_path,
        package_name=package,
        top_level_type_name=type_names[0] if type_names else receiver or None,
        nested_type_path=type_names[1:] if len(type_names) > 1 else (),
        member_kind=JavaMemberKind.METHOD.value,
        member_name=content.predicate_id,
        erased_jvm_signature=signature,
        location=segment.source_location,
        claim_text=segment.canonical_text,
        source_evidence_span_hash=segment.source_span_hash,
    )


def compare_identities(
    left: CanonicalSemanticIdentity | None,
    right: CanonicalSemanticIdentity | None,
) -> IdentityMatch:
    if left is None or right is None:
        return IdentityMatch.MISSING
    verify_semantic_identity(left)
    verify_semantic_identity(right)
    if left.identity_hash == right.identity_hash:
        return IdentityMatch.EXACT
    if _symbol_key(left) != _symbol_key(right):
        if _name_key(left) == _name_key(right):
            return IdentityMatch.CONFLICT
        return IdentityMatch.MISSING
    if left.erased_jvm_signature != right.erased_jvm_signature:
        return IdentityMatch.CONFLICT
    if not _locations_overlap(left, right):
        return IdentityMatch.CONFLICT
    if left.source_evidence_span_hash != right.source_evidence_span_hash:
        return IdentityMatch.CONFLICT
    return IdentityMatch.EQUIVALENT


def match_java_source_location(
    proposal_identity: CanonicalSemanticIdentity | None,
    source_identities: tuple[CanonicalSemanticIdentity, ...],
    *,
    golden_identity: CanonicalSemanticIdentity | None,
) -> JavaLocationMatch:
    if proposal_identity is None:
        return _match_result(
            IdentityMatch.MISSING,
            None,
            None,
            (),
            IdentityBlocker.MISSING_IDENTITY,
        )
    verify_semantic_identity(proposal_identity)
    candidates = tuple(
        item
        for item in source_identities
        if item.source_snapshot_hash == proposal_identity.source_snapshot_hash
        and item.source_document_id == proposal_identity.source_document_id
        and item.source_unit_id == proposal_identity.source_unit_id
        and _locations_overlap(item, proposal_identity)
    )
    exact_or_equivalent = tuple(
        item
        for item in candidates
        if compare_identities(proposal_identity, item)
        in {IdentityMatch.EXACT, IdentityMatch.EQUIVALENT}
    )
    if len(exact_or_equivalent) > 1:
        return _match_result(
            IdentityMatch.DUPLICATE,
            proposal_identity.identity_hash,
            None,
            tuple(item.identity_hash for item in exact_or_equivalent),
            IdentityBlocker.AMBIGUOUS_IDENTITY,
        )
    if not exact_or_equivalent:
        conflicts = tuple(
            item
            for item in source_identities
            if _name_key(item) == _name_key(proposal_identity)
        )
        status = IdentityMatch.CONFLICT if conflicts else IdentityMatch.MISSING
        blocker = (
            IdentityBlocker.CONFLICTING_IDENTITY
            if conflicts
            else IdentityBlocker.LOCATION_MISMATCH
        )
        return _match_result(
            status,
            proposal_identity.identity_hash,
            None,
            tuple(item.identity_hash for item in conflicts),
            blocker,
        )
    resolved = exact_or_equivalent[0]
    if golden_identity is None:
        return _match_result(
            IdentityMatch.MISSING,
            proposal_identity.identity_hash,
            resolved.identity_hash,
            (resolved.identity_hash,),
            IdentityBlocker.LOCATION_MISMATCH,
        )
    golden_match = compare_identities(resolved, golden_identity)
    if golden_match not in {IdentityMatch.EXACT, IdentityMatch.EQUIVALENT}:
        return _match_result(
            golden_match,
            proposal_identity.identity_hash,
            resolved.identity_hash,
            (resolved.identity_hash, golden_identity.identity_hash),
            IdentityBlocker.LOCATION_MISMATCH,
        )
    return _match_result(
        compare_identities(proposal_identity, resolved),
        proposal_identity.identity_hash,
        resolved.identity_hash,
        (resolved.identity_hash,),
        None,
    )


def detect_precompiler_identity_conflicts(
    proposal_identities: tuple[tuple[str, CanonicalSemanticIdentity], ...],
) -> PrecompilerIdentityReport:
    ordered = tuple(sorted(proposal_identities, key=lambda item: item[0]))
    for _, identity in ordered:
        verify_semantic_identity(identity)
    conflicts: dict[str, IdentityConflict] = {}
    for index, (left_id, left) in enumerate(ordered):
        for right_id, right in ordered[index + 1 :]:
            kind = _conflict_kind(left, right)
            if kind is None:
                continue
            values = {
                "conflict_kind": kind,
                "identity_hashes": tuple(
                    sorted((left.identity_hash, right.identity_hash))
                ),
                "proposal_ids": tuple(sorted((left_id, right_id))),
                "source_locations": tuple(
                    sorted((_location_key(left), _location_key(right)))
                ),
            }
            conflict = IdentityConflict(**values, conflict_hash=content_hash(values))
            conflicts[conflict.conflict_hash] = conflict
    values = tuple(conflicts[key] for key in sorted(conflicts))
    duplicate_count = sum(
        item.conflict_kind == "DUPLICATE_TRUSTED_PHYSICAL_LOCATION" for item in values
    )
    body = {
        "status": "FAIL" if values else "PASS",
        "proposal_count": len(ordered),
        "identity_count": len({item.identity_hash for _, item in ordered}),
        "conflicts": values,
        "duplicate_trusted_proposals": duplicate_count,
    }
    return PrecompilerIdentityReport(**body, report_hash=content_hash(body))


def require_precompiler_identity_closure(
    proposal_identities: tuple[tuple[str, CanonicalSemanticIdentity], ...],
) -> PrecompilerIdentityReport:
    report = detect_precompiler_identity_conflicts(proposal_identities)
    if report.status != "PASS":
        raise PrecompilerIdentityConflict(report)
    return report


def erased_jvm_signature(
    member_name: str,
    parameter_types: tuple[str, ...],
    return_type: str,
    package_name: str | None = None,
) -> str:
    parameters = "".join(
        _jvm_descriptor(item, package_name) for item in parameter_types
    )
    result = _jvm_descriptor(return_type, package_name, allow_void=True)
    return f"{member_name}({parameters}){result}"


def _java_member_identity(
    document,
    raw,
    start,
    end,
    line_number,
    visible,
    scopes,
    kind,
    name,
    signature,
    package,
):
    location = SourceLocation(
        start,
        end,
        line_number,
        line_number,
        tuple(scope.name for scope in scopes),
    )
    names = tuple(scope.name for scope in scopes)
    return make_semantic_identity(
        domain="java",
        source_document_id=document.document_id,
        source_snapshot_hash=document.bytes_hash,
        source_unit_id=document.relative_path,
        package_name=package,
        top_level_type_name=names[0],
        nested_type_path=names[1:],
        member_kind=kind.value,
        member_name=name,
        erased_jvm_signature=signature,
        location=location,
        claim_text=visible,
        source_evidence_span_hash=bytes_hash(raw[start:end]),
    )


def _parameter_types(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    result = []
    for parameter in _split_generic_commas(value):
        clean = re.sub(r"@[\w.]+(?:\([^)]*\))?\s*", "", parameter).strip()
        clean = re.sub(r"\b(?:final|volatile|transient)\b\s*", "", clean)
        parts = clean.split()
        if len(parts) < 2:
            raise ValueError("Java parameter lacks type and name")
        result.append(" ".join(parts[:-1]))
    return tuple(result)


def _split_generic_commas(value: str) -> tuple[str, ...]:
    result = []
    depth = 0
    start = 0
    for index, char in enumerate(value):
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif char == "," and depth == 0:
            result.append(value[start:index].strip())
            start = index + 1
    result.append(value[start:].strip())
    return tuple(item for item in result if item)


def _jvm_descriptor(
    value: str, package_name: str | None, *, allow_void: bool = False
) -> str:
    text = re.sub(r"<.*>", "", value.strip()).replace("?", "Object")
    text = text.replace("...", "[]")
    dimensions = 0
    while text.endswith("[]"):
        dimensions += 1
        text = text[:-2].strip()
    primitive = {
        "byte": "B",
        "char": "C",
        "double": "D",
        "float": "F",
        "int": "I",
        "long": "J",
        "short": "S",
        "boolean": "Z",
        "void": "V",
    }
    if text == "void" and not allow_void:
        raise ValueError("void is not a Java parameter type")
    if text in primitive:
        descriptor = primitive[text]
    else:
        common = {
            "String": "java.lang.String",
            "Object": "java.lang.Object",
            "Integer": "java.lang.Integer",
            "Long": "java.lang.Long",
            "Boolean": "java.lang.Boolean",
        }
        erased = common.get(text, text)
        if re.fullmatch(r"[A-Z]", erased):
            erased = "java.lang.Object"
        if "." not in erased and package_name:
            erased = f"{package_name}.{erased}"
        descriptor = f"L{erased.replace('.', '/')};"
    return "[" * dimensions + descriptor


def _without_comments(line: str, in_block: bool) -> tuple[str, bool]:
    result = []
    index = 0
    while index < len(line):
        if in_block:
            end = line.find("*/", index)
            if end < 0:
                return "".join(result), True
            index = end + 2
            in_block = False
            continue
        block = line.find("/*", index)
        single = line.find("//", index)
        if single >= 0 and (block < 0 or single < block):
            result.append(line[index:single])
            break
        if block < 0:
            result.append(line[index:])
            break
        result.append(line[index:block])
        index = block + 2
        in_block = True
    return "".join(result), in_block


def _normalized_claim(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _normalized_name(value: str) -> str:
    return "-".join(_normalized_claim(value).casefold().split())


def _symbol_key(value: CanonicalSemanticIdentity):
    return (
        value.domain,
        value.source_snapshot_hash,
        value.source_unit_id,
        value.package_name,
        value.top_level_type_name,
        value.nested_type_path,
        value.member_kind,
        value.member_name,
        value.erased_jvm_signature,
    )


def _name_key(value: CanonicalSemanticIdentity):
    return (
        value.domain,
        value.package_name,
        value.top_level_type_name,
        value.nested_type_path,
        value.member_kind,
        value.member_name,
    )


def _locations_overlap(left, right) -> bool:
    return (
        left.source_snapshot_hash == right.source_snapshot_hash
        and left.source_unit_id == right.source_unit_id
        and left.start_offset < right.end_offset
        and right.start_offset < left.end_offset
    )


def _location_key(value):
    return (
        f"{value.source_document_id}:{value.source_unit_id}:"
        f"{value.start_line}-{value.end_line}:"
        f"{value.start_offset}-{value.end_offset}"
    )


def _conflict_kind(left, right):
    same_identity = _symbol_key(left) == _symbol_key(right)
    same_span = (
        left.source_snapshot_hash == right.source_snapshot_hash
        and left.source_unit_id == right.source_unit_id
        and left.start_offset == right.start_offset
        and left.end_offset == right.end_offset
    )
    if left.identity_hash == right.identity_hash:
        return "DUPLICATE_CANONICAL_IDENTITY"
    if same_identity and not same_span:
        return "SAME_IDENTITY_DIFFERENT_SOURCE_SPANS"
    if same_span and (
        left.member_kind != right.member_kind
        or left.erased_jvm_signature != right.erased_jvm_signature
        or left.normalized_claim_text_hash != right.normalized_claim_text_hash
    ):
        return "SAME_SOURCE_SPAN_INCOMPATIBLE_CLAIM_SCHEMAS"
    if _name_key(left) == _name_key(right) and (
        left.erased_jvm_signature == right.erased_jvm_signature and not same_span
    ):
        return "DUPLICATE_TRUSTED_PHYSICAL_LOCATION"
    return None


def _match_result(status, proposal_hash, resolved_hash, candidates, blocker):
    values = {
        "status": status,
        "proposal_identity_hash": proposal_hash,
        "resolved_identity_hash": resolved_hash,
        "candidate_identity_hashes": tuple(sorted(candidates)),
        "blocker_reason": blocker,
    }
    return JavaLocationMatch(**values, report_hash=content_hash(values))
