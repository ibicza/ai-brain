"""Exact, immutable field-level source evidence construction and verification."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from enum import Enum

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.models import (
    FieldSourceEvidence,
    KnowledgeProposal,
    SourceBundle,
    SourceSegment,
)

TRANSFORMATION_IDENTITY = "source-utf8-exact.v1"
TRANSFORMATION_NORMALIZED = "source-literal-normalization.v1"


def build_field_evidence(
    bundle: SourceBundle,
    segments: tuple[SourceSegment, ...],
    proposals: tuple[KnowledgeProposal, ...],
    store,
) -> tuple[FieldSourceEvidence, ...]:
    """Bind each supported proposal leaf to the narrowest exact source span.

    Missing leaves are deliberately omitted. Verification treats an omitted
    required leaf as incomplete evidence; it is never widened to the segment.
    """

    documents = {item.document_id: item for item in bundle.documents}
    by_id = {item.segment_id: item for item in segments}
    result: list[FieldSourceEvidence] = []
    for proposal in proposals:
        proposal_segments = tuple(by_id[item] for item in proposal.segment_ids)
        for field_path, normalized, candidates in _required_fields(proposal):
            match = _locate(candidates, proposal_segments, documents, store)
            if match is None:
                continue
            segment, raw, start, end, raw_text, transformation = match
            document = documents[segment.document_id]
            location = segment.source_location
            value = FieldSourceEvidence(
                proposal.proposal_id,
                field_path,
                document.document_id,
                start,
                end,
                _line_number(raw, start),
                _line_number(raw, max(start, end - 1)),
                location.heading_path,
                location.table_row,
                location.table_cell,
                location.page,
                document.bytes_hash,
                bytes_hash(raw[start:end]),
                raw_text,
                normalized,
                transformation,
                content_hash({"transformation_id": transformation}),
                proposal.extraction_method,
                "",
            )
            result.append(
                replace(value, evidence_hash=content_hash(_without_hash(value)))
            )
    values = tuple(sorted(result, key=lambda item: (item.proposal_id, item.field_path)))
    verify_field_evidence(bundle, segments, proposals, values, store)
    return values


def verify_field_evidence(
    bundle: SourceBundle,
    segments: tuple[SourceSegment, ...],
    proposals: tuple[KnowledgeProposal, ...],
    evidence: tuple[FieldSourceEvidence, ...],
    store,
) -> dict[str, object]:
    documents = {item.document_id: item for item in bundle.documents}
    proposals_by_id = {item.proposal_id: item for item in proposals}
    allowed_documents = {
        proposal.proposal_id: {
            segment.document_id
            for segment in segments
            if segment.segment_id in proposal.segment_ids
        }
        for proposal in proposals
    }
    seen: set[tuple[str, str]] = set()
    for item in evidence:
        key = (item.proposal_id, item.field_path)
        if key in seen:
            raise ValueError("duplicate field source evidence")
        seen.add(key)
        proposal = proposals_by_id.get(item.proposal_id)
        document = documents.get(item.document_id)
        if (
            proposal is None
            or document is None
            or item.document_id not in allowed_documents[item.proposal_id]
            or item.document_bytes_hash != document.bytes_hash
        ):
            raise ValueError("field evidence source closure is invalid")
        required = {
            path: normalized for path, normalized, _ in _required_fields(proposal)
        }
        if required.get(item.field_path) != item.normalized_value:
            raise ValueError("field evidence normalized value mismatch")
        raw = store.get_blob(document.bytes_hash)
        if not 0 <= item.byte_start < item.byte_end <= len(raw):
            raise ValueError("field evidence byte range is invalid")
        span = raw[item.byte_start : item.byte_end]
        if (
            bytes_hash(span) != item.source_bytes_hash
            or span.decode("utf-8", errors="strict") != item.raw_text
            or content_hash(_without_hash(item)) != item.evidence_hash
        ):
            raise ValueError("field evidence cannot dereference exact source bytes")
        if item.transformation_hash != content_hash(
            {"transformation_id": item.transformation_id}
        ):
            raise ValueError("field evidence transformation identity mismatch")
    required_keys = {
        (proposal.proposal_id, path)
        for proposal in proposals
        for path, _, _ in _required_fields(proposal)
    }
    missing = tuple(sorted(required_keys - seen))
    return {
        "status": "COMPLETE" if not missing else "INCOMPLETE",
        "required_count": len(required_keys),
        "evidence_count": len(seen),
        "missing": missing,
        "evidence_set_hash": content_hash(
            tuple(item.evidence_hash for item in evidence)
        ),
    }


def required_field_paths(proposal: KnowledgeProposal) -> tuple[str, ...]:
    return tuple(path for path, _, _ in _required_fields(proposal))


def _required_fields(proposal: KnowledgeProposal):
    values = {
        "content": proposal.proposed_content,
        "applicability": proposal.proposed_applicability,
    }
    result = []
    for root, value in values.items():
        result.extend(
            item
            for item in _leaves(root, value)
            if item[0] != "content.object_type.kind"
        )
    return tuple(result)


def _leaves(path: str, value):
    if is_dataclass(value):
        result = []
        for key, item in asdict(value).items():
            result.extend(_leaves(f"{path}.{key}", item))
        return result
    if isinstance(value, dict):
        result = []
        for key in sorted(value):
            result.extend(_leaves(f"{path}.{key}", value[key]))
        return result
    if isinstance(value, (tuple, list)):
        result = []
        for index, item in enumerate(value):
            result.extend(_leaves(f"{path}[{index}]", item))
        return result
    if value is None or value == "":
        return []
    normalized = value.value if isinstance(value, Enum) else value
    normalized_text = canonical_json(normalized)
    literal = str(normalized)
    candidates = tuple(
        dict.fromkeys(
            (
                literal,
                literal.replace("_", " "),
                literal.replace("-", " "),
            )
        )
    )
    return [(path, normalized_text, candidates)]


def _locate(candidates, segments, documents, store):
    for segment in segments:
        document = documents[segment.document_id]
        raw = store.get_blob(document.bytes_hash)
        source = raw[
            segment.source_location.byte_start : segment.source_location.byte_end
        ]
        for candidate in candidates:
            encoded = candidate.encode("utf-8")
            relative = source.find(encoded)
            transformation = (
                TRANSFORMATION_IDENTITY
                if candidate == candidates[0]
                else TRANSFORMATION_NORMALIZED
            )
            if relative < 0 and encoded.isascii():
                relative = source.lower().find(encoded.lower())
                transformation = TRANSFORMATION_NORMALIZED
            if relative >= 0 and encoded:
                start = segment.source_location.byte_start + relative
                end = start + len(encoded)
                return (
                    segment,
                    raw,
                    start,
                    end,
                    raw[start:end].decode("utf-8", errors="strict"),
                    transformation,
                )
    return None


def _line_number(raw: bytes, offset: int) -> int:
    return raw[:offset].count(b"\n") + 1


def _without_hash(value):
    row = asdict(value)
    row.pop("evidence_hash")
    return row
