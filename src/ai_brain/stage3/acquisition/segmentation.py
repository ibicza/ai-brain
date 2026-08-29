"""Deterministic typed segmentation with exact source-byte locations."""

from __future__ import annotations

import re
from dataclasses import asdict

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.models import (
    SegmentKind,
    SourceBundle,
    SourceLocation,
    SourceMediaType,
    SourceSegment,
)
from ai_brain.stage3.acquisition.sources import verify_bundle
from ai_brain.stage3.acquisition.version import MAX_CODE_BLOCK_BYTES, MAX_SEGMENTS

_API = re.compile(
    r"(?:@api\s+|"
    r"^(?:(?:public|protected|private|static|final|abstract|default|"
    r"synchronized|native|strictfp)\s+)*"
    r"(?:<[^>]+>\s+)?[\w.$<>?\[\], ]+\s+[\w.$]+\([^)]*\)"
    r"(?:\s+throws\s+[^;{]+)?\s*[;{]\s*$)"
)
_EQUATION = re.compile(r"(?:@equation\s+|\b[A-Za-z][A-Za-z0-9_]*\s*=\s*[^=])")


def segment_bundle(bundle: SourceBundle, store) -> tuple[SourceSegment, ...]:
    verify_bundle(bundle, store=store)
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
        if document.media_type is SourceMediaType.PDF:
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
    return values


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
