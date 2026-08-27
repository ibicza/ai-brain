"""Strict chemistry source-derivation and upstream-state resolution."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ai_brain.stage2.domains.chemistry.models import (
    DerivationMethod,
    FieldExtractionEvidence,
    ManualSourceMappingApproval,
    SourceDerivationRecordV2,
    UpstreamSourceReference,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import SourceRecord, SourceStatus


class DerivationResolutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ResolvedSourceDerivation:
    source_record: SourceRecord
    derivation: SourceDerivationRecordV2
    upstream_source_ids: tuple[str, ...]
    upstream_source_record_hashes: tuple[str, ...]
    upstream_source_snapshot_hashes: tuple[str, ...]
    upstream_source_state_hashes: tuple[str, ...]
    upstream_status_event_hashes: tuple[str | None, ...]
    field_mapping_evidence_hashes: tuple[str, ...]


def resolve_source_derivation(
    source_record: SourceRecord,
    source_chain: dict[str, Any],
    fact_memory: FactMemory,
    *,
    source_record_bindings: tuple[dict[str, Any], ...] = (),
) -> ResolvedSourceDerivation:
    _verify_chain_hash(source_chain)
    derived_rows = [
        row
        for row in source_chain.get("derived_extracts", ())
        if row.get("source_id") == source_record.source_id
    ]
    if len(derived_rows) != 1:
        _fail("DERIVATION_SOURCE_MISMATCH", "derived source must have one manifest row")
    derivation_rows = [
        row
        for row in source_chain.get("derivations", ())
        if row.get("derived_source_id") == source_record.source_id
    ]
    if len(derivation_rows) != 1:
        _fail("DERIVATION_SOURCE_MISMATCH", "derived source must have one derivation")
    if len({row.get("derivation_id") for row in source_chain["derivations"]}) != len(
        source_chain["derivations"]
    ):
        _fail("DERIVATION_SOURCE_MISMATCH", "duplicate derivation ID")
    claimed_sources = [
        row.get("derived_source_id") for row in source_chain["derivations"]
    ]
    if len(set(claimed_sources)) != len(claimed_sources):
        _fail("DERIVATION_SOURCE_MISMATCH", "multiple derivations claim one source")

    derived_row = derived_rows[0]
    derivation_row = derivation_rows[0]
    derivation = derivation_from_dict(derivation_row["record"])
    _verify_derivation_hash(derivation, derivation_row)
    if derivation.derived_source_id != source_record.source_id:
        _fail("DERIVATION_SOURCE_MISMATCH", "derivation/source ID mismatch")
    if derivation.derived_source_kind != source_record.source_kind.value:
        _fail("DERIVATION_SOURCE_MISMATCH", "derivation/source kind mismatch")
    if derivation.derived_media_type != source_record.media_type:
        _fail("DERIVATION_SOURCE_MISMATCH", "derivation/source media type mismatch")
    if derivation.derived_file_path != derived_row.get("file"):
        _fail("DERIVATION_SOURCE_MISMATCH", "derivation file path mismatch")
    if derivation.derived_file_byte_sha256 != derived_row.get("sha256"):
        _fail("DERIVATION_CONTENT_MISMATCH", "derived file hash mismatch")
    if source_record.snapshot_hash != derivation.expected_source_snapshot_hash:
        _fail("DERIVATION_CONTENT_MISMATCH", "FactMemory snapshot hash mismatch")
    if source_record.snapshot_hash != derivation.derived_file_byte_sha256:
        _fail(
            "DERIVATION_CONTENT_MISMATCH",
            "FactMemory does not store exact derived bytes",
        )
    if (
        derivation.expected_source_record_hash is not None
        and derivation.expected_source_record_hash != source_record.record_hash
    ):
        _fail("DERIVATION_SOURCE_MISMATCH", "derived source record hash mismatch")

    raw = fact_memory.database.blobs.read(source_record.snapshot_hash)
    try:
        canonical_hash = content_hash(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DerivationResolutionError(
            "DERIVATION_CONTENT_MISMATCH", "derived source is not canonical JSON"
        ) from error
    if canonical_hash != derivation.derived_canonical_content_hash:
        _fail("DERIVATION_CONTENT_MISMATCH", "derived canonical content mismatch")

    metadata = source_record.license_metadata
    expected_metadata = {
        "derived_file_sha256": derivation.derived_file_byte_sha256,
        "derived_canonical_content_hash": derivation.derived_canonical_content_hash,
        "derivation_id": derivation.derivation_id,
        "derivation_hash": derivation.derivation_hash,
        "derivation_method": derivation.derivation_method.value,
        "upstream_source_ids": tuple(
            item.source_id for item in derivation.upstream_sources
        ),
        "upstream_snapshot_hashes": tuple(
            item.snapshot_hash for item in derivation.upstream_sources
        ),
    }
    for key, expected in expected_metadata.items():
        actual = metadata.get(key)
        if isinstance(actual, list):
            actual = tuple(actual)
        if actual != expected:
            _fail("DERIVATION_SOURCE_MISMATCH", f"derived metadata mismatch: {key}")

    bindings = {row["source_id"]: row for row in source_record_bindings}
    category_rows = tuple(source_chain.get("official_snapshots", ())) + tuple(
        source_chain.get("local_policy_snapshots", ())
    )
    category_by_id = {row["source_id"]: row for row in category_rows}
    upstream_ids: list[str] = []
    upstream_records: list[str] = []
    upstream_snapshots: list[str] = []
    upstream_states: list[str] = []
    upstream_events: list[str | None] = []
    for reference in derivation.upstream_sources:
        row = category_by_id.get(reference.source_id)
        if row is None:
            _fail("DERIVATION_SOURCE_MISMATCH", "unknown upstream source")
        if (
            row.get("sha256") != reference.snapshot_hash
            or row.get("source_kind") != reference.source_kind
            or row.get("source_family") != reference.source_family
        ):
            _fail("DERIVATION_SOURCE_MISMATCH", "upstream manifest binding changed")
        _verify_reference_hash(reference)
        state = fact_memory.get_source_state(reference.source_id)
        if state.status == SourceStatus.RETRACTED:
            _fail("RETRACTED_UPSTREAM_SOURCE", "required upstream source is retracted")
        if state.status == SourceStatus.UNAVAILABLE:
            _fail(
                "UNAVAILABLE_UPSTREAM_SOURCE", "required upstream source is unavailable"
            )
        if state.status != SourceStatus.ACTIVE:
            _fail("STALE_UPSTREAM_SOURCE", "required upstream source is not active")
        if (
            state.record.snapshot_hash != reference.snapshot_hash
            or state.record.source_kind.value != reference.source_kind
            or state.record.source_family != reference.source_family
        ):
            _fail("STALE_UPSTREAM_SOURCE", "upstream FactMemory source changed")
        if (
            reference.expected_source_record_hash is not None
            and state.record.record_hash != reference.expected_source_record_hash
        ):
            _fail("STALE_UPSTREAM_SOURCE", "upstream source record hash changed")
        bound = bindings.get(reference.source_id)
        if bound is not None and (
            bound.get("record_hash") != state.record.record_hash
            or bound.get("snapshot_hash") != state.record.snapshot_hash
        ):
            _fail("STALE_UPSTREAM_SOURCE", "domain source-record binding changed")
        upstream_ids.append(reference.source_id)
        upstream_records.append(state.record.record_hash)
        upstream_snapshots.append(state.record.snapshot_hash)
        upstream_states.append(source_state_hash(state))
        upstream_events.append(state.status_event_hash)

    _verify_method_policy(derivation, source_chain)
    evidence_hashes = []
    if not derivation.field_level_mappings:
        _fail("DERIVATION_CONTENT_MISMATCH", "derivation has no field evidence")
    for evidence in derivation.field_level_mappings:
        _verify_field_evidence(evidence, derivation)
        evidence_hashes.append(evidence.evidence_hash)
    return ResolvedSourceDerivation(
        source_record=source_record,
        derivation=derivation,
        upstream_source_ids=tuple(upstream_ids),
        upstream_source_record_hashes=tuple(upstream_records),
        upstream_source_snapshot_hashes=tuple(upstream_snapshots),
        upstream_source_state_hashes=tuple(upstream_states),
        upstream_status_event_hashes=tuple(upstream_events),
        field_mapping_evidence_hashes=tuple(evidence_hashes),
    )


def derivation_from_dict(payload: dict[str, Any]) -> SourceDerivationRecordV2:
    row = dict(payload)
    row["derivation_method"] = DerivationMethod(row["derivation_method"])
    row["upstream_sources"] = tuple(
        UpstreamSourceReference(
            **{**item, "field_location_used": tuple(item["field_location_used"])}
        )
        for item in row["upstream_sources"]
    )
    row["field_level_mappings"] = tuple(
        FieldExtractionEvidence(
            **{
                **item,
                "extraction_method": DerivationMethod(item["extraction_method"]),
            }
        )
        for item in row["field_level_mappings"]
    )
    return SourceDerivationRecordV2(**row)


def manual_approval_from_dict(payload: dict[str, Any]) -> ManualSourceMappingApproval:
    return ManualSourceMappingApproval(
        **{**payload, "selected_fields": tuple(payload["selected_fields"])}
    )


def source_state_hash(state: Any) -> str:
    return content_hash(
        {
            "source_record_hash": state.record.record_hash,
            "status": state.status,
            "status_event_hash": state.status_event_hash,
        }
    )


def _verify_chain_hash(source_chain: dict[str, Any]) -> None:
    body = dict(source_chain)
    digest = body.pop("source_chain_hash", None)
    if content_hash(body) != digest:
        _fail("STALE_SOURCE_CHAIN", "source-chain hash mismatch")


def _verify_derivation_hash(
    derivation: SourceDerivationRecordV2, row: dict[str, Any]
) -> None:
    body = asdict(derivation)
    digest = body.pop("derivation_hash")
    if content_hash(body) != digest or row.get("derivation_hash") != digest:
        _fail("DERIVATION_CONTENT_MISMATCH", "derivation hash mismatch")
    if row.get("derivation_id") != derivation.derivation_id:
        _fail("DERIVATION_SOURCE_MISMATCH", "derivation ID mismatch")


def _verify_reference_hash(reference: UpstreamSourceReference) -> None:
    body = asdict(reference)
    digest = body.pop("reference_hash")
    if content_hash(body) != digest:
        _fail("DERIVATION_SOURCE_MISMATCH", "upstream reference hash mismatch")


def _verify_field_evidence(
    evidence: FieldExtractionEvidence, derivation: SourceDerivationRecordV2
) -> None:
    body = asdict(evidence)
    digest = body.pop("evidence_hash")
    if content_hash(body) != digest:
        _fail("DERIVATION_CONTENT_MISMATCH", "field evidence hash mismatch")
    if evidence.extraction_method != derivation.derivation_method:
        _fail("DERIVATION_METHOD_CHANGED", "field evidence method mismatch")
    if evidence.upstream_source_id not in {
        item.source_id for item in derivation.upstream_sources
    }:
        _fail("DERIVATION_SOURCE_MISMATCH", "field evidence uses unknown upstream")
    if evidence.parser_mapping_implementation_hash != (
        derivation.extractor_implementation_manifest_hash
    ):
        _fail("STALE_EXTRACTION_POLICY", "field mapping implementation changed")
    if (
        derivation.derivation_method == DerivationMethod.REVIEWED_MANUAL_MAPPING
        and not evidence.reviewer
    ):
        _fail("DERIVATION_METHOD_CHANGED", "manual field lacks reviewer")


def _verify_method_policy(
    derivation: SourceDerivationRecordV2, source_chain: dict[str, Any]
) -> None:
    if derivation.extraction_policy_version != source_chain.get(
        "extraction_policy_version"
    ):
        _fail("STALE_EXTRACTION_POLICY", "extraction policy changed")
    if derivation.derivation_method == DerivationMethod.DETERMINISTIC_EXTRACTION:
        if derivation.manual_mapping_approval_id is not None:
            _fail("DERIVATION_METHOD_CHANGED", "deterministic derivation has approval")
        return
    if derivation.derivation_method == DerivationMethod.POLICY_TRANSFORMATION:
        if not derivation.reviewer_identity:
            _fail("DERIVATION_METHOD_CHANGED", "policy transformation lacks reviewer")
        if any(
            item.source_kind != "LOCAL_DOCUMENT" for item in derivation.upstream_sources
        ):
            _fail(
                "DERIVATION_METHOD_CHANGED", "policy presented as official extraction"
            )
        return
    approvals = [
        item
        for item in source_chain.get("manual_mapping_approvals", ())
        if item.get("approval_id") == derivation.manual_mapping_approval_id
    ]
    if len(approvals) != 1:
        _fail("DERIVATION_METHOD_CHANGED", "manual mapping approval missing")
    approval = manual_approval_from_dict(approvals[0]["record"])
    body = asdict(approval)
    digest = body.pop("approval_hash")
    if (
        content_hash(body) != digest
        or digest != derivation.manual_mapping_approval_hash
    ):
        _fail("DERIVATION_METHOD_CHANGED", "manual mapping approval changed")
    if (
        not approval.reviewer_identity.strip()
        or approval.reviewer_identity_type == "MODEL"
        or approval.review_decision != "APPROVED"
    ):
        _fail(
            "DERIVATION_METHOD_CHANGED", "manual mapping approval is not human-approved"
        )
    if content_hash(approval.selected_fields) != approval.mapping_hash:
        _fail("DERIVATION_CONTENT_MISMATCH", "approved mapping changed")


def _fail(code: str, message: str) -> None:
    raise DerivationResolutionError(code, message)
