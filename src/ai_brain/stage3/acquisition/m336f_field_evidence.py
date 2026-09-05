"""Independent golden-backed field-evidence conformance for M-33.6f."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_evidence_policy import (
    enumerate_java_evidence_requirements,
)
from ai_brain.stage3.acquisition.java_goldens import JavaGoldenManifest
from ai_brain.stage3.acquisition.java_production import JavaProductionTrustBatch
from ai_brain.stage3.acquisition.m336f_thresholds import ratio_string

M336F_FIELD_EVIDENCE_SPECIFICATION = "m336f.java-field-evidence-conformance.v1"
_PATH_PART = re.compile(r"(?P<name>[a-z_]+)(?P<indexes>(?:\[[0-9]+\])*)\Z")
_MISSING = object()


@dataclass(frozen=True)
class JavaFieldEvidenceConformanceRow:
    proposal_id: str
    declaration_id: str
    field_name: str
    canonical_value_hash: str
    expected_value_hash: str | None
    source_node_evidence_hash: str
    source_span_evidence_hash: str
    resolver_manifest_hash: str
    evidence_policy_hash: str
    production_evidence_hash: str
    exact: bool
    row_hash: str


@dataclass(frozen=True)
class JavaFieldEvidenceMismatch:
    proposal_id: str
    declaration_id: str
    field_name: str
    mismatch_kind: str
    expected_value_hash: str | None
    actual_value_hash: str | None
    mismatch_hash: str


@dataclass(frozen=True)
class JavaFieldEvidenceConformanceReport:
    schema_version: int
    specification_version: str
    production_field_evidence_manifest_hash: str
    independent_golden_manifest_hash: str
    evidence_policy_hash: str
    resolver_manifest_hash: str
    required_count: int
    present_count: int
    exact_count: int
    missing_count: int
    extra_count: int
    duplicate_count: int
    wrong_count: int
    completeness: str
    exactness: str
    rows: tuple[JavaFieldEvidenceConformanceRow, ...]
    mismatches: tuple[JavaFieldEvidenceMismatch, ...]
    report_hash: str


def build_java_field_evidence_conformance_report(
    batch: JavaProductionTrustBatch,
    goldens: JavaGoldenManifest,
) -> JavaFieldEvidenceConformanceReport:
    """Compare production evidence with independent golden semantic payloads."""

    declarations = {item.node_id: item for item in batch.source_index.declarations}
    bindings = {item.proposal_id: item for item in batch.proposal_batch.bindings}
    golden_by_location = {
        (
            item.document_bytes_hash,
            item.source_unit_id,
            item.start_offset,
            item.end_offset,
        ): item
        for item in goldens.goldens
        if item.expected_semantics is not None
    }
    golden_by_proposal = {}
    declaration_by_proposal = {}
    for proposal_id, binding in bindings.items():
        declaration = declarations[binding.parser_node_id]
        declaration_by_proposal[proposal_id] = declaration
        golden = golden_by_location.get(
            (
                declaration.source_snapshot_hash,
                declaration.source_unit_id,
                declaration.declaration_span.byte_start,
                declaration.declaration_span.byte_end,
            )
        )
        if golden is None or golden.expected_semantics is None:
            continue
        golden_by_proposal[proposal_id] = golden

    requirements = enumerate_java_evidence_requirements(
        batch.proposal_batch,
        batch.source_index,
        batch.evidence_policy,
    )
    required = {(item.proposal_id, item.field_path): item for item in requirements}
    proposals = {item.proposal_id: item for item in batch.proposal_batch.proposals}
    expected_by_key = {}
    for requirement in requirements:
        proposal_id = requirement.proposal_id
        golden = golden_by_proposal.get(proposal_id)
        if golden is None or golden.expected_semantics is None:
            continue
        expected = _independent_expected_value(
            requirement.field_path,
            golden.expected_semantics,
            proposals[proposal_id],
            bindings[proposal_id],
            declaration_by_proposal[proposal_id],
        )
        if expected is not _MISSING:
            expected_by_key[(proposal_id, requirement.field_path)] = canonical_json(
                expected
            )
    evidence_by_key = {}
    for item in batch.field_evidence.evidence:
        evidence_by_key.setdefault((item.proposal_id, item.field_path), []).append(item)
    counts = Counter(
        (item.proposal_id, item.field_path) for item in batch.field_evidence.evidence
    )
    rows = []
    mismatches = []
    exact_count = 0
    for evidence in batch.field_evidence.evidence:
        key = (evidence.proposal_id, evidence.field_path)
        declaration = declaration_by_proposal[evidence.proposal_id]
        expected = expected_by_key.get(key)
        exact = (
            key in required
            and counts[key] == 1
            and expected is not None
            and evidence.normalized_output == expected
        )
        if exact:
            exact_count += 1
        body = {
            "proposal_id": evidence.proposal_id,
            "declaration_id": declaration.node_id,
            "field_name": evidence.field_path,
            "canonical_value_hash": evidence.output_hash,
            "expected_value_hash": content_hash(expected)
            if expected is not None
            else None,
            "source_node_evidence_hash": evidence.semantic_identity_hash,
            "source_span_evidence_hash": evidence.source_span_hash,
            "resolver_manifest_hash": batch.source_index.type_universe_manifest_hash,
            "evidence_policy_hash": batch.evidence_policy.manifest_hash,
            "production_evidence_hash": evidence.evidence_hash,
            "exact": exact,
        }
        rows.append(
            JavaFieldEvidenceConformanceRow(**body, row_hash=content_hash(body))
        )

    missing_keys = sorted(set(required) - set(evidence_by_key))
    extra_keys = sorted(set(evidence_by_key) - set(required))
    wrong_keys = sorted(
        key
        for key in set(required) & set(evidence_by_key)
        if len(evidence_by_key[key]) != 1
        or expected_by_key.get(key) is None
        or evidence_by_key[key][0].normalized_output != expected_by_key[key]
    )
    for key, kind in (
        *((item, "MISSING") for item in missing_keys),
        *((item, "EXTRA") for item in extra_keys),
        *((item, "WRONG") for item in wrong_keys),
    ):
        proposal_id, field_name = key
        declaration = declaration_by_proposal[proposal_id]
        evidence = evidence_by_key.get(key, [None])[0]
        expected = expected_by_key.get(key)
        body = {
            "proposal_id": proposal_id,
            "declaration_id": declaration.node_id,
            "field_name": field_name,
            "mismatch_kind": kind,
            "expected_value_hash": content_hash(expected)
            if expected is not None
            else None,
            "actual_value_hash": evidence.output_hash if evidence is not None else None,
        }
        mismatches.append(
            JavaFieldEvidenceMismatch(**body, mismatch_hash=content_hash(body))
        )
    duplicate_count = sum(value - 1 for value in counts.values() if value > 1)
    report_body = {
        "schema_version": 1,
        "specification_version": M336F_FIELD_EVIDENCE_SPECIFICATION,
        "production_field_evidence_manifest_hash": batch.field_evidence.manifest_hash,
        "independent_golden_manifest_hash": goldens.manifest_hash,
        "evidence_policy_hash": batch.evidence_policy.manifest_hash,
        "resolver_manifest_hash": batch.source_index.type_universe_manifest_hash,
        "required_count": len(required),
        "present_count": len(batch.field_evidence.evidence),
        "exact_count": exact_count,
        "missing_count": len(missing_keys),
        "extra_count": len(extra_keys),
        "duplicate_count": duplicate_count,
        "wrong_count": len(wrong_keys),
        "completeness": ratio_string(len(required) - len(missing_keys), len(required)),
        "exactness": ratio_string(exact_count, len(batch.field_evidence.evidence)),
        "rows": tuple(
            sorted(rows, key=lambda item: (item.proposal_id, item.field_name))
        ),
        "mismatches": tuple(
            sorted(
                mismatches,
                key=lambda item: (
                    item.proposal_id,
                    item.field_name,
                    item.mismatch_kind,
                ),
            )
        ),
    }
    report = JavaFieldEvidenceConformanceReport(
        **report_body, report_hash=content_hash(report_body)
    )
    verify_java_field_evidence_conformance_report(report)
    return report


def verify_java_field_evidence_conformance_report(
    report: JavaFieldEvidenceConformanceReport,
) -> None:
    for row in report.rows:
        body = asdict(row)
        claimed = body.pop("row_hash")
        if content_hash(body) != claimed:
            raise ValueError("field-evidence conformance row hash mismatch")
    for mismatch in report.mismatches:
        body = asdict(mismatch)
        claimed = body.pop("mismatch_hash")
        if content_hash(body) != claimed:
            raise ValueError("field-evidence mismatch hash mismatch")
    body = asdict(report)
    claimed = body.pop("report_hash")
    mismatch_counts = Counter(item.mismatch_kind for item in report.mismatches)
    evidence_keys = Counter((item.proposal_id, item.field_name) for item in report.rows)
    duplicate_count = sum(value - 1 for value in evidence_keys.values() if value > 1)
    expected_completeness = ratio_string(
        report.required_count - report.missing_count, report.required_count
    )
    expected_exactness = ratio_string(report.exact_count, report.present_count)
    if (
        report.schema_version != 1
        or report.specification_version != M336F_FIELD_EVIDENCE_SPECIFICATION
        or content_hash(body) != claimed
        or min(
            report.required_count,
            report.present_count,
            report.exact_count,
            report.missing_count,
            report.extra_count,
            report.duplicate_count,
            report.wrong_count,
        )
        < 0
        or report.present_count != len(report.rows)
        or report.exact_count != sum(item.exact for item in report.rows)
        or report.missing_count != mismatch_counts["MISSING"]
        or report.extra_count != mismatch_counts["EXTRA"]
        or report.wrong_count != mismatch_counts["WRONG"]
        or report.duplicate_count != duplicate_count
        or report.completeness != expected_completeness
        or report.exactness != expected_exactness
        or report.rows
        != tuple(
            sorted(report.rows, key=lambda item: (item.proposal_id, item.field_name))
        )
        or report.mismatches
        != tuple(
            sorted(
                report.mismatches,
                key=lambda item: (
                    item.proposal_id,
                    item.field_name,
                    item.mismatch_kind,
                ),
            )
        )
    ):
        raise ValueError("field-evidence conformance report mismatch")


def _independent_expected_value(
    field_name,
    semantics,
    proposal,
    binding,
    declaration,
):
    if field_name.startswith("content."):
        payload = json.loads(semantics.expected_claim_payload)
        return _resolve_payload_path(payload, field_name.removeprefix("content."))
    envelope = {
        "envelope.proposed_kind": semantics.expected_knowledge_kind,
        "envelope.epistemic_character": semantics.expected_epistemic_character,
        "envelope.extraction_method": proposal.extraction_method,
        "envelope.status_authority": proposal.status,
        "envelope.ambiguity_fields": proposal.ambiguity_fields,
        "envelope.source_segment_binding": binding.segment_id,
        "envelope.parser_node_binding": declaration.node_id,
    }
    return envelope.get(field_name, _MISSING)


def _resolve_payload_path(payload, field_path):
    current = payload
    previous_name = None
    for raw_part in field_path.split("."):
        match = _PATH_PART.fullmatch(raw_part)
        if match is None:
            return _MISSING
        name = match.group("name")
        indexes = tuple(
            int(item) for item in re.findall(r"[0-9]+", match.group("indexes"))
        )
        if isinstance(current, dict):
            if name not in current:
                return _MISSING
            current = current[name]
        elif (
            isinstance(current, (list, tuple))
            and previous_name == "parameters"
            and name in {"name", "type"}
            and len(current) == 2
        ):
            current = current[0 if name == "name" else 1]
        else:
            return _MISSING
        for index in indexes:
            if not isinstance(current, (list, tuple)) or index >= len(current):
                return _MISSING
            current = current[index]
        previous_name = name
    return current
