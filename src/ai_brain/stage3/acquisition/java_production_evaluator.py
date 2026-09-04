"""Evaluation-only comparison of sealed Java production output and goldens."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_diagnostic_scope import (
    JavaDiagnosticScope,
    diagnostic_scope_from_receipt,
)
from ai_brain.stage3.acquisition.java_goldens import (
    JavaGoldenManifest,
    verify_java_golden_manifest,
)
from ai_brain.stage3.acquisition.java_metrics import (
    automatic_trust_confusion,
    evidence_confusion,
    source_location_confusion,
)
from ai_brain.stage3.acquisition.java_production import (
    JavaProductionTrustBatch,
    seal_java_production_output,
)
from ai_brain.stage3.acquisition.java_semantics import (
    semantic_content_confusion,
    type_resolution_semantic_manifest_hash,
)

JAVA_DIAGNOSTIC_CATEGORIES = (
    "AMBIGUOUS_TYPE",
    "COMPILER_ERROR",
    "DUPLICATE_SIGNATURE",
    "INACCESSIBLE_TYPE",
    "INVALID_IMPORT",
    "INVALID_RECEIVER_OR_ENCLOSING_TYPE",
    "INVALID_THROWS_TYPE",
    "INVALID_TYPE_VARIABLE_BOUND",
    "MALFORMED_GENERIC_DECLARATION",
    "NON_EXPORTED_MODULE_PACKAGE",
    "UNRESOLVED_TYPE",
)


@dataclass(frozen=True)
class JavaProductionEvaluationReport:
    production_output_hash: str
    golden_manifest_hash: str
    location: object
    semantic: object
    trust: object
    field_evidence: object
    resolution: object
    diagnostic_categories: tuple[dict, ...]
    breakdowns: dict
    wrong_trusted_count: int
    passed: bool
    report_hash: str


def evaluate_sealed_java_production(
    sealed_output: dict,
    batch: JavaProductionTrustBatch,
    golden_manifest: JavaGoldenManifest,
) -> JavaProductionEvaluationReport:
    if canonical_json(seal_java_production_output(batch)) != canonical_json(
        sealed_output
    ):
        raise ValueError("evaluator received a batch different from sealed production")
    verify_java_golden_manifest(golden_manifest)
    expected_locations = {
        (
            item.document_bytes_hash,
            item.source_unit_id,
            item.start_offset,
            item.end_offset,
        )
        for item in golden_manifest.goldens
    }
    actual_locations = {
        (
            item["document_bytes_hash"],
            item["source_unit_id"],
            item["start_offset"],
            item["end_offset"],
        )
        for item in sealed_output["candidate_rows"]
    }
    location = source_location_confusion(expected_locations, actual_locations)
    semantic = semantic_content_confusion(
        golden_manifest,
        batch.proposal_batch,
        batch.source_index,
        batch.decisions,
        include_semantic_status=not batch.closure.checker_version.startswith("m335."),
    )
    by_location = {
        (
            item.document_bytes_hash,
            item.source_unit_id,
            item.start_offset,
            item.end_offset,
        ): item
        for item in golden_manifest.goldens
    }
    expected_trusted = {
        item.golden_id for item in golden_manifest.goldens if item.expected_supported
    }
    actual_trusted = set()
    for row in sealed_output["candidate_rows"]:
        golden = by_location.get(
            (
                row["document_bytes_hash"],
                row["source_unit_id"],
                row["start_offset"],
                row["end_offset"],
            )
        )
        if golden is not None and row["production_trust_state"] == "trusted":
            actual_trusted.add(golden.golden_id)
    trust = automatic_trust_confusion(
        expected_trusted,
        actual_trusted,
        {item.golden_id for item in golden_manifest.goldens},
    )
    evidence = evidence_confusion(batch.field_evidence)
    resolution = _resolution_report(golden_manifest, batch)
    diagnostic_categories = _diagnostic_report(golden_manifest, sealed_output)
    breakdowns = _breakdown_report(golden_manifest, sealed_output, semantic)
    passed = (
        location.precision == "1.000000"
        and location.recall >= "0.950000"
        and semantic.exact_semantic_precision == "1.000000"
        and semantic.exact_semantic_recall >= "0.950000"
        and trust.precision == "1.000000"
        and trust.wrong_trusted == 0
        and trust.coverage >= "0.800000"
        and evidence.exactness == "1.000000"
        and resolution["oracle_agreement"] == "1.000000"
        and sum(
            item["trusted_count"]
            for item in diagnostic_categories
            if item["scope"] == JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING.value
        )
        == 0
    )
    body = {
        "production_output_hash": sealed_output["production_output_hash"],
        "golden_manifest_hash": golden_manifest.manifest_hash,
        "location": location,
        "semantic": semantic,
        "trust": trust,
        "field_evidence": evidence,
        "resolution": resolution,
        "diagnostic_categories": diagnostic_categories,
        "breakdowns": breakdowns,
        "wrong_trusted_count": trust.wrong_trusted,
        "passed": passed,
    }
    return JavaProductionEvaluationReport(**body, report_hash=content_hash(body))


def _resolution_report(goldens, batch):
    declarations = {
        (
            item.source_snapshot_hash,
            item.source_unit_id,
            item.declaration_span.byte_start,
            item.declaration_span.byte_end,
        ): item
        for item in batch.source_index.declarations
    }
    counts = {
        "parameters": 0,
        "returns": 0,
        "bounds": 0,
        "throws": 0,
        "receivers": 0,
        "module_accessibility": 0,
        "descriptor_agreement": 0,
        "declaration_agreement": 0,
        "declaration_total": 0,
        "expected_declaration_total": 0,
    }
    mismatches = []
    for golden in goldens.goldens:
        semantics = golden.expected_semantics
        if semantics is None:
            continue
        counts["expected_declaration_total"] += 1
        key = (
            golden.document_bytes_hash,
            golden.source_unit_id,
            golden.start_offset,
            golden.end_offset,
        )
        declaration = declarations.get(key)
        if declaration is None:
            continue
        counts["declaration_total"] += 1
        counts["parameters"] += len(semantics.source_parameter_types)
        counts["returns"] += 1
        counts["bounds"] += sum(len(item) for item in semantics.intersection_bounds)
        counts["throws"] += len(semantics.declared_exception_source_types)
        counts["receivers"] += 1
        counts["module_accessibility"] += 1
        if golden.erased_jvm_descriptor == declaration.erased_jvm_descriptor:
            counts["descriptor_agreement"] += 1
        actual_resolution_hash = type_resolution_semantic_manifest_hash(declaration)
        if semantics.complete_type_resolution_manifest_hash == actual_resolution_hash:
            counts["declaration_agreement"] += 1
        else:
            mismatches.append(
                {
                    "golden_id": golden.golden_id,
                    "source_unit_id": golden.source_unit_id,
                    "start_offset": golden.start_offset,
                    "canonical_source_signature": golden.canonical_source_signature,
                    "expected_hash": semantics.complete_type_resolution_manifest_hash,
                    "actual_hash": actual_resolution_hash,
                }
            )
    total = counts["declaration_total"]
    counts["oracle_agreement"] = (
        "N/A" if total == 0 else f"{counts['declaration_agreement'] / total:.6f}"
    )
    counts["declaration_mismatches"] = tuple(mismatches)
    return counts


def _diagnostic_report(goldens, sealed_output):
    state_by_target = {}
    golden_by_location = {
        (
            item.document_bytes_hash,
            item.source_unit_id,
            item.start_offset,
            item.end_offset,
        ): item
        for item in goldens.goldens
    }
    for row in sealed_output["candidate_rows"]:
        golden = golden_by_location.get(
            (
                row["document_bytes_hash"],
                row["source_unit_id"],
                row["start_offset"],
                row["end_offset"],
            )
        )
        if golden is not None and golden.expected_semantics is not None:
            state_by_target[golden.expected_semantics.target_id] = row[
                "production_trust_state"
            ]
    result = []
    observed = {
        (category, scope.value)
        for category in JAVA_DIAGNOSTIC_CATEGORIES
        for scope in JavaDiagnosticScope
    }
    for category, scope_value in sorted(observed):
        receipts = tuple(
            item
            for item in goldens.diagnostics
            if item.normalized_category == category
            and diagnostic_scope_from_receipt(item).value == scope_value
        )
        targets = {target for item in receipts for target in item.target_ids}
        trusted = sum(state_by_target.get(item) == "trusted" for item in targets)
        withheld = sum(state_by_target.get(item) == "withheld" for item in targets)
        result.append(
            {
                "category": category,
                "scope": scope_value,
                "expected_count": len(receipts),
                "observed_count": len(receipts),
                "target_count": len(targets),
                "trusted_count": trusted,
                "withheld_count": withheld,
                "precision": "N/A",
                "recall": "N/A",
                "measurement_status": "NOT_MEASURED" if not receipts else "OBSERVED",
            }
        )
    return tuple(result)


def _breakdown_report(goldens, sealed_output, semantic):
    rows = {
        (
            item["document_bytes_hash"],
            item["source_unit_id"],
            item["start_offset"],
            item["end_offset"],
        ): item
        for item in sealed_output["candidate_rows"]
    }
    semantic_mismatches = {item.golden_id for item in semantic.mismatches}
    dimensions = {"source_root": {}, "java_construct": {}, "blocker_category": {}}
    for golden in goldens.goldens:
        expected = golden.expected_semantics
        if expected is None:
            continue
        key = (
            golden.document_bytes_hash,
            golden.source_unit_id,
            golden.start_offset,
            golden.end_offset,
        )
        row = rows.get(key)
        values = {
            "source_root": golden.source_unit_id.partition("/")[0],
            "java_construct": (
                "CONSTRUCTOR"
                if golden.canonical_source_signature.startswith("<init>(")
                else "METHOD"
            ),
            "blocker_category": expected.expected_blocker_reason or "SUPPORTED",
        }
        for dimension, value in values.items():
            counters = dimensions[dimension].setdefault(
                value,
                {
                    "expected_count": 0,
                    "located_count": 0,
                    "semantic_exact_count": 0,
                    "expected_supported_count": 0,
                    "trusted_count": 0,
                    "correct_trusted_count": 0,
                    "wrong_trusted_count": 0,
                    "withheld_count": 0,
                },
            )
            counters["expected_count"] += 1
            counters["expected_supported_count"] += int(expected.expected_supported)
            if row is None:
                continue
            counters["located_count"] += 1
            counters["semantic_exact_count"] += int(
                golden.golden_id not in semantic_mismatches
            )
            trusted = row["production_trust_state"] == "trusted"
            counters["trusted_count"] += int(trusted)
            counters["correct_trusted_count"] += int(
                trusted and expected.expected_supported
            )
            counters["wrong_trusted_count"] += int(
                trusted and not expected.expected_supported
            )
            counters["withheld_count"] += int(not trusted)
    return {
        dimension: tuple(
            {"value": value, **counters} for value, counters in sorted(groups.items())
        )
        for dimension, groups in sorted(dimensions.items())
    }
