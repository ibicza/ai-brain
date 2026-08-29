from __future__ import annotations

from collections import Counter
from dataclasses import asdict, is_dataclass
from enum import Enum

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.models import (
    FieldSourceEvidence,
    KnowledgeProposal,
    ProposalStatus,
)
from ai_brain.stage3.knowledge_ir.validation import validate_record

PACK_EVALUATOR_ID = "generic.pack-evaluator.v3"
PACK_EVALUATOR_IMPLEMENTATION_HASH = content_hash(
    {
        "evaluator_id": PACK_EVALUATOR_ID,
        "operations": (
            "KNOWLEDGE_RECORD_VALID",
            "SOURCE_BINDING_CLOSED",
            "CAPABILITY_DECLARED",
        ),
        "schema_version": 3,
    }
)


def evaluate_proposals(
    proposals: tuple[KnowledgeProposal, ...],
    golden: dict,
    segments=(),
    *,
    field_evidence: tuple[FieldSourceEvidence, ...] = (),
    conflicts=(),
) -> dict[str, object]:
    by_segment = {item.segment_id: item for item in segments}
    expected = {
        (item["document_id"], item["line_start"]): item for item in golden["expected"]
    }
    proposed = {
        (
            by_segment[item.segment_ids[0]].document_id,
            by_segment[item.segment_ids[0]].source_location.line_start,
        ): item
        for item in proposals
        if item.segment_ids and item.segment_ids[0] in by_segment
    }
    true_positive = sum(
        location in proposed and proposed[location].proposed_kind.value == row["kind"]
        for location, row in expected.items()
    )
    trusted_states = {
        ProposalStatus.SOURCE_ENTAILED,
        ProposalStatus.CROSS_SOURCE_CORROBORATED,
        ProposalStatus.APPROVED,
        ProposalStatus.VERIFIED,
    }
    wrong_verified = sum(
        item.status in trusted_states
        and (
            (
                by_segment[item.segment_ids[0]].document_id,
                by_segment[item.segment_ids[0]].source_location.line_start,
            )
            not in expected
            or expected[
                (
                    by_segment[item.segment_ids[0]].document_id,
                    by_segment[item.segment_ids[0]].source_location.line_start,
                )
            ]["kind"]
            != item.proposed_kind.value
        )
        for item in proposals
        if item.segment_ids and item.segment_ids[0] in by_segment
    )
    precision = _rate(true_positive, len(proposed))
    recall = _rate(true_positive, len(expected))
    verified = tuple(item for item in proposals if item.status in trusted_states)
    source_entailed = tuple(
        item
        for item in proposals
        if item.status
        in {
            ProposalStatus.SOURCE_ENTAILED,
            ProposalStatus.CROSS_SOURCE_CORROBORATED,
        }
    )
    approved = tuple(
        item for item in proposals if item.status is ProposalStatus.APPROVED
    )
    expected_fields = _expected_fields(golden)
    actual_fields = _actual_fields(proposals, by_segment)
    field_tp = len(expected_fields & actual_fields)
    expected_spans = _expected_spans(golden)
    proposal_locations = {
        item.proposal_id: (
            by_segment[item.segment_ids[0]].document_id,
            by_segment[item.segment_ids[0]].source_location.line_start,
        )
        for item in proposals
        if item.segment_ids and item.segment_ids[0] in by_segment
    }
    actual_spans = {
        (
            *proposal_locations[item.proposal_id],
            item.field_path,
            item.byte_start,
            item.byte_end,
        )
        for item in field_evidence
        if item.proposal_id in proposal_locations
    }
    span_tp = len(expected_spans & actual_spans)
    expected_capabilities = _expected_capabilities(golden)
    actual_capabilities = {
        (*proposal_locations[item.proposal_id], capability)
        for item in proposals
        for capability in item.proposed_capabilities
        if item.proposal_id in proposal_locations
    }
    capability_tp = len(expected_capabilities & actual_capabilities)
    expected_conflicts = {
        tuple(sorted(item["proposal_ids"])) for item in golden.get("conflicts", ())
    }
    actual_conflicts = {tuple(sorted(item.proposal_ids)) for item in conflicts}
    conflict_tp = len(expected_conflicts & actual_conflicts)
    segment_expected = {
        (item["document_id"], item["line_start"], item["kind"])
        for item in golden.get("segments", ())
    }
    segment_actual = {
        (item.document_id, item.source_location.line_start, item.kind.value)
        for item in segments
        if item.kind.value != "DOCUMENT"
    }
    segment_tp = len(segment_expected & segment_actual)

    def wrong(values):
        return sum(
            (
                by_segment[item.segment_ids[0]].document_id,
                by_segment[item.segment_ids[0]].source_location.line_start,
            )
            not in expected
            or expected[
                (
                    by_segment[item.segment_ids[0]].document_id,
                    by_segment[item.segment_ids[0]].source_location.line_start,
                )
            ]["kind"]
            != item.proposed_kind.value
            for item in values
            if item.segment_ids and item.segment_ids[0] in by_segment
        )

    result = {
        "proposal_count": len(proposals),
        "counts_by_kind": dict(
            sorted(Counter(item.proposed_kind.value for item in proposals).items())
        ),
        "proposal_precision": precision,
        "proposal_recall": recall,
        "segment_precision": _rate(segment_tp, len(segment_actual)),
        "segment_recall": _rate(segment_tp, len(segment_expected)),
        "source_entailment_precision": _rate(
            len(source_entailed) - wrong(source_entailed), len(source_entailed)
        ),
        "automatically_approved_precision": _rate(
            len(approved) - wrong(approved), len(approved)
        ),
        "automatically_trusted_precision": _rate(
            len(verified) - wrong_verified, len(verified)
        ),
        "coverage": _rate(len(proposed), len(expected)),
        "abstention": _rate(
            sum(
                item.status
                in {
                    ProposalStatus.REVIEW_REQUIRED,
                    ProposalStatus.NEEDS_NEW_CAPABILITY,
                }
                for item in proposals
            ),
            len(proposals),
        ),
        "review_required_rate": _rate(
            sum(item.status is ProposalStatus.REVIEW_REQUIRED for item in proposals),
            len(proposals),
        ),
        "wrong_automatically_verified": wrong_verified,
        "source_span_exactness": (
            _rate(span_tp, len(expected_spans)) if field_evidence else "1.000000"
        ),
        "field_precision": _rate(field_tp, len(actual_fields)),
        "field_recall": _rate(field_tp, len(expected_fields)),
        "capability_precision": _rate(capability_tp, len(actual_capabilities)),
        "capability_recall": _rate(capability_tp, len(expected_capabilities)),
        "conflict_precision": _rate(conflict_tp, len(actual_conflicts)),
        "conflict_recall": _rate(conflict_tp, len(expected_conflicts)),
    }
    return {**result, "evaluation_hash": content_hash(result)}


def _rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "N/A"
    return f"{numerator / denominator:.6f}"


def verify_pack_evaluation(pack) -> dict[str, object]:
    manifest = pack.evaluation_manifest
    if manifest.get("schema_version") == 2 and all(
        isinstance(item, str) for item in manifest.get("test_cases", ())
    ):
        return _verify_legacy_pack_evaluation(pack)
    if manifest.get("schema_version") != 2:
        raise ValueError("unsupported pack evaluation schema")
    results = tuple(_execute_test(pack, item) for item in manifest["test_cases"])
    mandatory = tuple(item for item in results if item["mandatory"])
    passed = sum(item["passed"] for item in mandatory)
    rate = _rate(passed, len(mandatory))
    result = {
        "status": (
            "PASS"
            if mandatory and passed == len(mandatory) and rate >= "1.000000"
            else "FAIL"
        ),
        "passed": passed,
        "total": len(mandatory),
        "pass_rate": rate,
        "abstention_behavior": "UNSUPPORTED_TEST_FAILS_CLOSED",
        "unsupported_cases": ("unknown evaluator operation",),
        "per_test_results": results,
        "complete_result_hash": content_hash(results),
        "pack_hash": pack.manifest.pack_content_hash,
    }
    return {**result, "evaluation_result_hash": content_hash(result)}


def _verify_legacy_pack_evaluation(pack) -> dict[str, object]:
    manifest = pack.evaluation_manifest
    passed = [
        bool(pack.knowledge_records),
        all(item.provenance_refs for item in pack.knowledge_records),
        manifest.get("runtime_network") is False,
        manifest.get("expected_record_count") == len(pack.knowledge_records),
    ]
    result = {
        "status": "PASS" if all(passed) else "FAIL",
        "passed": sum(passed),
        "total": len(passed),
        "pack_hash": pack.manifest.pack_content_hash,
    }
    return {**result, "evaluation_result_hash": content_hash(result)}


def build_pack_evaluation_manifest(records, source_bindings) -> dict[str, object]:
    source_by_id = {item.binding_id: item for item in source_bindings}
    tests = []
    if not records:
        body = {
            "operation": "EMPTY_PACK_ABSTAINS",
            "record_id": None,
            "source_dependencies": (),
            "record_dependencies": (),
        }
        tests.append(
            {
                "test_id": f"pack.{content_hash(body)[:32]}",
                "evaluator_id": PACK_EVALUATOR_ID,
                "evaluator_implementation_hash": PACK_EVALUATOR_IMPLEMENTATION_HASH,
                "required_capability": "generic.record_query.v1",
                "input": body,
                "expected": {
                    "status": "PASS",
                    "output_hash": content_hash("INSUFFICIENT_EVIDENCE"),
                },
                "mandatory": True,
            }
        )
    for record in records:
        for operation, expected in (
            ("KNOWLEDGE_RECORD_VALID", record.content_hash),
            (
                "SOURCE_BINDING_CLOSED",
                content_hash(
                    tuple(
                        source_by_id[item].binding_hash
                        for item in record.provenance_refs
                    )
                ),
            ),
            (
                "CAPABILITY_DECLARED",
                content_hash(tuple(sorted(record.required_capability_ids))),
            ),
        ):
            body = {
                "operation": operation,
                "record_id": record.knowledge_id,
                "source_dependencies": tuple(record.provenance_refs),
                "record_dependencies": tuple(record.dependencies),
            }
            tests.append(
                {
                    "test_id": f"pack.{content_hash(body)[:32]}",
                    "evaluator_id": PACK_EVALUATOR_ID,
                    "evaluator_implementation_hash": PACK_EVALUATOR_IMPLEMENTATION_HASH,
                    "required_capability": None,
                    "input": body,
                    "expected": {"status": "PASS", "output_hash": expected},
                    "mandatory": True,
                }
            )
    return {
        "schema_version": 2,
        "test_cases": tests,
        "minimum_pass_rate": "1.0",
        "runtime_network": False,
        "expected_record_count": len(records),
        "source_span_exactness": "1.0",
    }


def _execute_test(pack, test):
    expected_keys = {
        "test_id",
        "evaluator_id",
        "evaluator_implementation_hash",
        "required_capability",
        "input",
        "expected",
        "mandatory",
    }
    if set(test) != expected_keys:
        raise ValueError("pack evaluation test schema is not exact")
    if (
        test["evaluator_id"] != PACK_EVALUATOR_ID
        or test["evaluator_implementation_hash"] != PACK_EVALUATOR_IMPLEMENTATION_HASH
    ):
        raise ValueError("pack evaluation test binds an unknown evaluator")
    record_by_id = {item.knowledge_id: item for item in pack.knowledge_records}
    source_by_id = {item.binding_id: item for item in pack.source_bindings}
    value = test["input"]
    record = record_by_id.get(value.get("record_id"))
    status = "PASS"
    output_hash = ""
    try:
        operation = value.get("operation")
        if operation == "EMPTY_PACK_ABSTAINS":
            if pack.knowledge_records:
                raise ValueError("empty-pack abstention test has records")
            declared = {
                item.capability_id for item in pack.manifest.required_capabilities
            }
            if test["required_capability"] not in declared:
                raise ValueError("empty-pack abstention capability is undeclared")
            output_hash = content_hash("INSUFFICIENT_EVIDENCE")
        elif record is None:
            raise ValueError("unknown evaluation record")
        elif operation == "KNOWLEDGE_RECORD_VALID":
            validate_record(record)
            output_hash = record.content_hash
        elif operation == "SOURCE_BINDING_CLOSED":
            bindings = tuple(source_by_id[item] for item in record.provenance_refs)
            if not bindings or any(not item.field_evidence for item in bindings):
                raise ValueError("record field evidence is incomplete")
            output_hash = content_hash(tuple(item.binding_hash for item in bindings))
        elif operation == "CAPABILITY_DECLARED":
            declared = {
                item.capability_id for item in pack.manifest.required_capabilities
            }
            if not set(record.required_capability_ids) <= declared:
                raise ValueError("record capability is undeclared")
            output_hash = content_hash(tuple(sorted(record.required_capability_ids)))
        else:
            raise ValueError("unsupported evaluation operation")
    except (KeyError, ValueError):
        status = "FAIL"
    observed = {"status": status, "output_hash": output_hash}
    body = {
        "test_id": test["test_id"],
        "mandatory": bool(test["mandatory"]),
        "passed": observed == test["expected"],
        "observed": observed,
    }
    return {**body, "result_hash": content_hash(body)}


def _expected_fields(golden):
    return {
        (
            item["document_id"],
            item["line_start"],
            path,
            content_hash(value),
        )
        for item in golden.get("expected", ())
        for path, value in item.get("fields", {}).items()
    }


def _actual_fields(proposals, by_segment):
    result = set()
    for item in proposals:
        if not item.segment_ids or item.segment_ids[0] not in by_segment:
            continue
        segment = by_segment[item.segment_ids[0]]
        for path, value in _flatten("content", item.proposed_content):
            result.add(
                (
                    segment.document_id,
                    segment.source_location.line_start,
                    path,
                    content_hash(value),
                )
            )
    return result


def _expected_spans(golden):
    return {
        (
            item["document_id"],
            item["line_start"],
            path,
            value["byte_start"],
            value["byte_end"],
        )
        for item in golden.get("expected", ())
        for path, value in item.get("source_spans", {}).items()
    }


def _expected_capabilities(golden):
    return {
        (item["document_id"], item["line_start"], capability)
        for item in golden.get("expected", ())
        for capability in item.get("capabilities", ())
    }


def _flatten(path, value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return tuple(
            result
            for key in sorted(value)
            for result in _flatten(f"{path}.{key}", value[key])
        )
    if isinstance(value, (tuple, list)):
        return tuple(
            result
            for index, item in enumerate(value)
            for result in _flatten(f"{path}[{index}]", item)
        )
    if value is None or value == "":
        return ()
    if isinstance(value, Enum):
        value = value.value
    return ((path, value),)
