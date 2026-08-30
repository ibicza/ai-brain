"""Deterministic typed segmentation with exact source-byte locations."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_source_index import (
    JavaSourceIndex,
    bundle_requires_java_policy,
)
from ai_brain.stage3.acquisition.models import (
    SegmentKind,
    SourceBundle,
    SourceLocation,
    SourceMediaType,
    SourceSegment,
)
from ai_brain.stage3.acquisition.sources import verify_bundle
from ai_brain.stage3.acquisition.version import MAX_CODE_BLOCK_BYTES, MAX_SEGMENTS

_API = re.compile(r"(?:@api\s+|\b(?:public|protected|private)\s+).+\([^)]*\)")
_EQUATION = re.compile(r"(?:@equation\s+|\b[A-Za-z][A-Za-z0-9_]*\s*=\s*[^=])")
MAX_EXACT_DUPLICATE_RATE = "0.02"
_MAX_DUPLICATE_NUMERATOR = 2
_MAX_DUPLICATE_DENOMINATOR = 100


@dataclass(frozen=True)
class SegmentAlias:
    duplicate_segment_id: str
    canonical_segment_id: str
    normalized_segment_hash: str
    original_document_id: str
    original_source_location: SourceLocation
    original_source_span_hash: str
    alias_hash: str


@dataclass(frozen=True)
class SegmentDeduplicationReport:
    status: str
    total_segments: int
    unique_segments: int
    exact_duplicates: int
    duplicate_rate: str
    input_exact_duplicates: int
    input_duplicate_rate: str
    top_duplicate_sources: tuple[tuple[str, int, tuple[str, ...]], ...]
    proposal_count_before: int
    proposal_count_after: int
    trusted_proposals_blocked: int
    alias_count: int
    physical_duplicates: int
    physical_duplicate_rate: str
    lexical_repetitions: int
    lexical_repetition_rate: str
    top_lexical_repetitions: tuple[tuple[str, int, tuple[str, ...]], ...]
    report_hash: str


@dataclass(frozen=True)
class DeduplicatedSegments:
    segments: tuple[SourceSegment, ...]
    aliases: tuple[SegmentAlias, ...]
    report: SegmentDeduplicationReport


class DuplicateSegmentGateError(ValueError):
    def __init__(self, report: SegmentDeduplicationReport) -> None:
        super().__init__("exact duplicate segment rate exceeds 0.02")
        self.report = report


def segment_bundle(bundle: SourceBundle, store) -> tuple[SourceSegment, ...]:
    return segment_bundle_with_report(bundle, store).segments


def segment_bundle_with_report(
    bundle: SourceBundle,
    store,
    *,
    java_source_index: JavaSourceIndex | None = None,
) -> DeduplicatedSegments:
    verify_bundle(bundle, store=store)
    java_policy = bundle_requires_java_policy(bundle)
    authoritative_java = java_policy and java_source_index is not None
    result: list[SourceSegment] = []
    for document in bundle.documents:
        raw = store.get_blob(document.bytes_hash)
        canonical = store.get_blob(document.canonical_text_hash).decode("utf-8")
        result.append(
            _segment(
                bundle.bundle_id,
                document.document_id,
                SegmentKind.DOCUMENT,
                len(result),
                canonical.rstrip(),
                raw,
                0,
                len(raw),
                1,
                max(1, canonical.count("\n")),
                (),
                page=1 if document.media_type is SourceMediaType.PDF else None,
            )
        )
        if document.media_type is SourceMediaType.JAVA_SOURCE and authoritative_java:
            declarations = tuple(
                item
                for item in java_source_index.declarations
                if item.document_id == document.document_id
            )
            for declaration in declarations:
                location = declaration.declaration_span
                result.append(
                    _segment(
                        bundle.bundle_id,
                        document.document_id,
                        SegmentKind.API_SIGNATURE,
                        len(result),
                        raw[location.byte_start : location.byte_end].decode("utf-8"),
                        raw,
                        location.byte_start,
                        location.byte_end,
                        location.line_start,
                        location.line_end,
                        (declaration.receiver_type,),
                    )
                )
        elif document.media_type is SourceMediaType.PDF:
            result.extend(
                _pdf_segments(bundle.bundle_id, document.document_id, raw, len(result))
            )
        else:
            result.extend(
                _line_segments(bundle.bundle_id, document.document_id, raw, len(result))
            )
        if len(result) > MAX_SEGMENTS:
            raise ValueError("segment count exceeds resource policy")
    values = tuple(result)
    verify_segments(bundle, values, store)
    if authoritative_java:
        deduplicated = deduplicate_segments(values)
        verify_segments(bundle, deduplicated.segments, store)
        require_unique_segments(deduplicated.segments)
        return deduplicated
    if java_policy:
        return _legacy_lexical_deduplication(values)
    report = _deduplication_report(values, values, (), ())
    return DeduplicatedSegments(values, (), report)


def normalized_segment_hash(segment: SourceSegment) -> str:
    text = unicodedata.normalize("NFKC", segment.canonical_text)
    normalized = "\n".join(" ".join(line.split()) for line in text.splitlines()).strip()
    return bytes_hash(normalized.encode("utf-8"))


def deduplicate_segments(
    segments: tuple[SourceSegment, ...],
) -> DeduplicatedSegments:
    canonical: dict[tuple[str, int, int, str, SegmentKind], SourceSegment] = {}
    kept: list[SourceSegment] = []
    aliases: list[SegmentAlias] = []
    physical_groups: dict[
        tuple[str, int, int, str, SegmentKind], list[SourceSegment]
    ] = defaultdict(list)
    lexical_groups: dict[str, list[SourceSegment]] = defaultdict(list)
    for segment in segments:
        if segment.kind is SegmentKind.DOCUMENT:
            kept.append(segment)
            continue
        digest = normalized_segment_hash(segment)
        location = segment.source_location
        key = (
            segment.document_id,
            location.byte_start,
            location.byte_end,
            segment.source_span_hash,
            segment.kind,
        )
        physical_groups[key].append(segment)
        lexical_groups[digest].append(segment)
        first = canonical.get(key)
        if first is None:
            canonical[key] = segment
            kept.append(segment)
            continue
        values = {
            "duplicate_segment_id": segment.segment_id,
            "canonical_segment_id": first.segment_id,
            "normalized_segment_hash": digest,
            "original_document_id": segment.document_id,
            "original_source_location": segment.source_location,
            "original_source_span_hash": segment.source_span_hash,
        }
        aliases.append(SegmentAlias(**values, alias_hash=content_hash(values)))
    report = _deduplication_report(
        segments,
        tuple(kept),
        tuple(aliases),
        tuple(physical_groups.values()),
        tuple(lexical_groups.values()),
    )
    return DeduplicatedSegments(tuple(kept), tuple(aliases), report)


def _legacy_lexical_deduplication(
    segments: tuple[SourceSegment, ...],
) -> DeduplicatedSegments:
    """Keep the M-34 diagnostic API stable; it is not trust-bearing in M-34.1."""

    canonical: dict[tuple[str, SegmentKind], SourceSegment] = {}
    kept = []
    aliases = []
    groups: dict[tuple[str, SegmentKind], list[SourceSegment]] = defaultdict(list)
    for segment in segments:
        if segment.kind is SegmentKind.DOCUMENT:
            kept.append(segment)
            continue
        digest = normalized_segment_hash(segment)
        key = (digest, segment.kind)
        groups[key].append(segment)
        first = canonical.get(key)
        if first is None:
            canonical[key] = segment
            kept.append(segment)
            continue
        values = {
            "duplicate_segment_id": segment.segment_id,
            "canonical_segment_id": first.segment_id,
            "normalized_segment_hash": digest,
            "original_document_id": segment.document_id,
            "original_source_location": segment.source_location,
            "original_source_span_hash": segment.source_span_hash,
        }
        aliases.append(SegmentAlias(**values, alias_hash=content_hash(values)))
    report = _deduplication_report(
        segments,
        tuple(kept),
        tuple(aliases),
        tuple(groups.values()),
        tuple(groups.values()),
    )
    input_total = sum(item.kind is not SegmentKind.DOCUMENT for item in segments)
    report = replace(
        report,
        input_exact_duplicates=len(aliases),
        input_duplicate_rate=_rate(len(aliases), input_total),
        report_hash="",
    )
    report_body = asdict(report)
    report_body.pop("report_hash")
    report = replace(report, report_hash=content_hash(report_body))
    return DeduplicatedSegments(tuple(kept), tuple(aliases), report)


def require_unique_segments(
    segments: tuple[SourceSegment, ...],
) -> SegmentDeduplicationReport:
    audited = deduplicate_segments(segments)
    input_total = audited.report.unique_segments + audited.report.input_exact_duplicates
    if (
        audited.report.input_exact_duplicates * _MAX_DUPLICATE_DENOMINATOR
        >= input_total * _MAX_DUPLICATE_NUMERATOR
    ):
        raise DuplicateSegmentGateError(audited.report)
    return audited.report


def with_proposal_counts(
    report: SegmentDeduplicationReport,
    *,
    before: int,
    after: int,
    trusted_blocked: int,
) -> SegmentDeduplicationReport:
    provisional = replace(
        report,
        proposal_count_before=before,
        proposal_count_after=after,
        trusted_proposals_blocked=trusted_blocked,
        report_hash="",
    )
    body = asdict(provisional)
    body.pop("report_hash")
    return replace(provisional, report_hash=content_hash(body))


def _deduplication_report(before, after, aliases, physical_groups, lexical_groups=()):
    after_values = tuple(
        item for item in after if item.kind is not SegmentKind.DOCUMENT
    )
    before_values = tuple(
        item for item in before if item.kind is not SegmentKind.DOCUMENT
    )
    after_total = len(after_values)
    after_physical = Counter(_physical_key(item) for item in after_values)
    after_duplicates = sum(count - 1 for count in after_physical.values() if count > 1)
    input_total = len(before_values)
    input_physical = Counter(_physical_key(item) for item in before_values)
    input_duplicates = sum(count - 1 for count in input_physical.values() if count > 1)
    lexical_counts = Counter(normalized_segment_hash(item) for item in after_values)
    lexical_repetitions = sum(
        count - 1 for count in lexical_counts.values() if count > 1
    )
    top = []
    for group in physical_groups:
        if len(group) < 2:
            continue
        top.append(
            (
                normalized_segment_hash(group[0]),
                len(group),
                tuple(sorted({item.document_id for item in group})),
            )
        )
    top.sort(key=lambda item: (-item[1], item[0]))
    lexical_top = []
    for group in lexical_groups:
        physical = {_physical_key(item) for item in group}
        if len(physical) < 2:
            continue
        lexical_top.append(
            (
                normalized_segment_hash(group[0]),
                len(physical),
                tuple(sorted({item.document_id for item in group})),
            )
        )
    lexical_top.sort(key=lambda item: (-item[1], item[0]))
    body = {
        "status": "PASS" if after_duplicates == 0 else "FAIL",
        "total_segments": after_total,
        "unique_segments": after_total - after_duplicates,
        "exact_duplicates": after_duplicates,
        "duplicate_rate": _rate(after_duplicates, after_total),
        "input_exact_duplicates": input_duplicates,
        "input_duplicate_rate": _rate(input_duplicates, input_total),
        "top_duplicate_sources": tuple(top[:20]),
        "proposal_count_before": 0,
        "proposal_count_after": 0,
        "trusted_proposals_blocked": 0,
        "alias_count": len(aliases),
        "physical_duplicates": after_duplicates,
        "physical_duplicate_rate": _rate(after_duplicates, after_total),
        "lexical_repetitions": lexical_repetitions,
        "lexical_repetition_rate": _rate(lexical_repetitions, after_total),
        "top_lexical_repetitions": tuple(lexical_top[:20]),
    }
    return SegmentDeduplicationReport(**body, report_hash=content_hash(body))


def _physical_key(segment: SourceSegment):
    location = segment.source_location
    return (
        segment.document_id,
        location.byte_start,
        location.byte_end,
        segment.source_span_hash,
        segment.kind,
    )


def _rate(numerator: int, denominator: int) -> str:
    return "0.000000" if denominator == 0 else f"{numerator / denominator:.6f}"


def verify_segments(
    bundle: SourceBundle, segments: tuple[SourceSegment, ...], store
) -> None:
    documents = {item.document_id: item for item in bundle.documents}
    if len({item.segment_id for item in segments}) != len(segments):
        raise ValueError("duplicate source segment ID")
    for segment in segments:
        document = documents.get(segment.document_id)
        if document is None or segment.bundle_id != bundle.bundle_id:
            raise ValueError("segment source binding is invalid")
        raw = store.get_blob(document.bytes_hash)
        location = segment.source_location
        if not 0 <= location.byte_start <= location.byte_end <= len(raw):
            raise ValueError("segment source byte range is invalid")
        if (
            bytes_hash(raw[location.byte_start : location.byte_end])
            != segment.source_span_hash
        ):
            raise ValueError("segment cannot dereference original source bytes")
        body = asdict(segment)
        digest = body.pop("segment_hash")
        if content_hash(body) != digest:
            raise ValueError("source segment hash mismatch")


def _line_segments(
    bundle_id: str, document_id: str, raw: bytes, ordinal: int
) -> list[SourceSegment]:
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("segmentation source is not UTF-8") from error
    chunks = raw.splitlines(keepends=True)
    result = []
    offset = 0
    headings: list[str] = []
    in_code = False
    code_start = 0
    code_line = 0
    code_bytes = bytearray()
    for line_number, chunk in enumerate(chunks, 1):
        end = offset + len(chunk)
        text = chunk.decode("utf-8").rstrip("\r\n")
        stripped = _strip_html(text).strip()
        if text.lstrip().startswith("```"):
            if not in_code:
                in_code = True
                code_start, code_line = offset, line_number
                code_bytes = bytearray(chunk)
            else:
                code_bytes.extend(chunk)
                if len(code_bytes) > MAX_CODE_BLOCK_BYTES:
                    raise ValueError("code block exceeds resource policy")
                result.append(
                    _segment(
                        bundle_id,
                        document_id,
                        SegmentKind.CODE_BLOCK,
                        ordinal + len(result),
                        _strip_fence(code_bytes.decode("utf-8")),
                        raw,
                        code_start,
                        end,
                        code_line,
                        line_number,
                        tuple(headings),
                    )
                )
                in_code = False
            offset = end
            continue
        if in_code:
            code_bytes.extend(chunk)
            if len(code_bytes) > MAX_CODE_BLOCK_BYTES:
                raise ValueError("code block exceeds resource policy")
            offset = end
            continue
        if not stripped:
            offset = end
            continue
        kind = _kind(stripped, text)
        if kind is SegmentKind.HEADING:
            level = _heading_level(text)
            headings[:] = headings[: level - 1]
            headings.append(stripped.lstrip("#").strip())
        result.append(
            _segment(
                bundle_id,
                document_id,
                kind,
                ordinal + len(result),
                stripped,
                raw,
                offset,
                end,
                line_number,
                line_number,
                tuple(headings),
            )
        )
        offset = end
    if in_code:
        raise ValueError("unterminated source code block")
    return result


def _pdf_segments(
    bundle_id: str, document_id: str, raw: bytes, ordinal: int
) -> list[SourceSegment]:
    result = []
    for index, match in enumerate(re.finditer(rb"\(([^()]*)\)\s*Tj", raw), 1):
        text = match.group(1).decode("utf-8", errors="strict")
        result.append(
            _segment(
                bundle_id,
                document_id,
                _kind(text, text),
                ordinal + len(result),
                text,
                raw,
                match.start(1),
                match.end(1),
                index,
                index,
                (),
                page=1,
            )
        )
    return result


def _kind(text: str, raw_line: str) -> SegmentKind:
    lower = text.casefold()
    if raw_line.lstrip().startswith("#") or re.search(
        r"<h[1-6](?:\s|>)", raw_line, re.IGNORECASE
    ):
        return SegmentKind.HEADING
    if lower.startswith("section:"):
        return SegmentKind.SECTION
    if lower.startswith(("warning:", "@warning")):
        return SegmentKind.WARNING
    if lower.startswith(("note:", "@note")):
        return SegmentKind.NOTE
    if lower.startswith(("@example", "example:", "пример:")):
        return SegmentKind.EXAMPLE_BLOCK
    if lower.startswith(("@test", "test:")):
        return SegmentKind.TEST_BLOCK
    if _API.search(text):
        return SegmentKind.API_SIGNATURE
    if _EQUATION.search(text):
        return SegmentKind.EQUATION_BLOCK
    if lower.startswith(("@definition", "@concept", "@entity", "definition:")):
        return SegmentKind.DEFINITION_BLOCK
    if text.count("|") >= 2:
        return SegmentKind.TABLE
    if re.match(r"^(?:[-*+] |\d+[.)] )", text):
        return SegmentKind.LIST
    return SegmentKind.PARAGRAPH


def _segment(
    bundle_id,
    document_id,
    kind,
    ordinal,
    text,
    raw,
    start,
    end,
    line_start,
    line_end,
    headings,
    *,
    page=None,
):
    location = SourceLocation(start, end, line_start, line_end, headings, page=page)
    values = {
        "segment_id": "",
        "bundle_id": bundle_id,
        "document_id": document_id,
        "kind": kind,
        "ordinal": ordinal,
        "canonical_text": text,
        "source_location": location,
        "source_span_hash": bytes_hash(raw[start:end]),
    }
    values["segment_id"] = f"segment.{content_hash(values)[:32]}"
    return SourceSegment(**values, segment_hash=content_hash(values))


def _strip_html(value: str) -> str:
    return (
        re.sub(r"<[^>]+>", " ", value)
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )


def _strip_fence(value: str) -> str:
    lines = value.splitlines()
    return "\n".join(lines[1:-1]).strip()


def _heading_level(value: str) -> int:
    stripped = value.lstrip()
    if stripped.startswith("#"):
        return min(6, len(stripped) - len(stripped.lstrip("#")))
    match = re.search(r"<h([1-6])", value, re.IGNORECASE)
    return int(match.group(1)) if match else 1
