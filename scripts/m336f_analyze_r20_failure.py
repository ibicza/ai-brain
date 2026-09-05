"""Build public-safe M-33.6f forensic reports from exact-R20 primary evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_production_compiler import (
    java_production_compiler_report_from_dict,
)
from ai_brain.stage3.acquisition.m336f_forensics import (
    CompilationContextObservation,
    classify_compilation_contexts,
)
from ai_brain.stage3.acquisition.m336f_thresholds import build_m336f_trust_metrics

R20_SHA = "8e0b542bd180e33ae38fea81d53e45195d4a918e"


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _sealed(value):
    return {**value, "report_hash": content_hash(value)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-output", type=Path, required=True)
    parser.add_argument("--packability-report", type=Path, required=True)
    parser.add_argument("--source-entry-bindings", type=Path, required=True)
    parser.add_argument("--semantic-goldens", type=Path, required=True)
    parser.add_argument("--evaluation-report", type=Path, required=True)
    parser.add_argument("--r20-field-primary", type=Path, required=True)
    parser.add_argument("--windows-license-evaluation", type=Path, required=True)
    parser.add_argument("--karina-license-evaluation", type=Path, required=True)
    parser.add_argument("--current-compiler-context", type=Path, required=True)
    parser.add_argument("--internal-compiler-context", type=Path, required=True)
    parser.add_argument("--same-root-compiler-context", type=Path, required=True)
    parser.add_argument("--frozen-compiler-context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    production = _load(args.production_output)
    packability = _load(args.packability_report)
    bindings = _load(args.source_entry_bindings)
    goldens = _load(args.semantic_goldens)
    evaluation = _load(args.evaluation_report)
    field_primary = _load(args.r20_field_primary)
    contexts = tuple(
        _load_compiler_context(path)
        for path in (
            args.current_compiler_context,
            args.internal_compiler_context,
            args.same_root_compiler_context,
            args.frozen_compiler_context,
        )
    )

    candidates = {
        (
            item["document_bytes_hash"],
            item["source_unit_id"],
            item["start_offset"],
            item["end_offset"],
        ): item
        for item in production["candidate_rows"]
    }
    diagnostic_by_hash = {item["receipt_hash"]: item for item in goldens["diagnostics"]}
    binding_by_unit = {item["selected_path"]: item for item in bindings["bindings"]}
    packability_by_proposal = {
        item["proposal_id"]: item for item in packability["bindings"]
    }
    wrong = []
    for golden in goldens["goldens"]:
        key = (
            golden["document_bytes_hash"],
            golden["source_unit_id"],
            golden["start_offset"],
            golden["end_offset"],
        )
        candidate = candidates.get(key)
        if (
            candidate is None
            or candidate["production_trust_state"] != "trusted"
            or golden["expected_supported"]
        ):
            continue
        target_id = golden["expected_semantics"]["target_id"]
        diagnostics = [
            diagnostic_by_hash[item]
            for item in golden["diagnostic_receipt_hashes"]
            if target_id in diagnostic_by_hash[item]["target_ids"]
        ]
        diagnostic = next(
            (
                item
                for item in diagnostics
                if item["applicability"] == "DECLARATION_HEADER_BLOCKING"
            ),
            diagnostics[0],
        )
        context = _context_rows(candidate, contexts)
        classification = classify_compilation_contexts(
            current=context[0][1],
            selected_plus_internal=context[1][1],
            all_same_root=context[2][1],
            frozen_classpath=context[3][1],
        )
        source_binding = binding_by_unit[golden["source_unit_id"]]
        packability_binding = packability_by_proposal[candidate["proposal_id"]]
        body = {
            "production_proposal_id": candidate["proposal_id"],
            "production_target_id": target_id,
            "declaration_identity_hash": candidate["declaration_hash"],
            "source_entry_id": source_binding["source_entry_id"],
            "family_root_id": golden["source_unit_id"].partition("/")[0],
            "source_unit_identity": content_hash(
                (golden["source_unit_id"], golden["document_bytes_hash"])
            ),
            "declaration_kind": golden["member_kind"],
            "declaration_byte_span": (
                golden["start_offset"],
                golden["end_offset"],
            ),
            "normalized_compiler_diagnostic_code": diagnostic["diagnostic_code"],
            "normalized_diagnostic_category": diagnostic["normalized_category"],
            "diagnostic_character_span": {
                "line": diagnostic["line"],
                "column": diagnostic["column"],
            },
            "mapped_byte_span": (
                diagnostic["start_offset"],
                diagnostic["end_offset"],
            ),
            "diagnostic_scope": diagnostic["applicability"],
            "enclosing_type_identity": content_hash(
                ("JAVA_TYPE", candidate["receiver_type"])
            ),
            "production_trust_decision_hash": candidate["decision_hash"],
            "production_evidence_manifest_hash": production[
                "field_evidence_manifest_hash"
            ],
            "production_packability_receipt_hash": packability_binding["binding_hash"],
            "independent_expected_state": "WITHHELD",
            "reason_for_disagreement": classification,
            "compilation_contexts": tuple(
                _public_context(name, observation, context[0][1])
                for name, observation in context
            ),
        }
        wrong.append({**body, "forensic_row_hash": content_hash(body)})
    wrong.sort(key=lambda item: item["production_target_id"])
    if len(wrong) != 29:
        raise ValueError("exact R20 wrong-trusted target count changed")
    root_cause_counts = tuple(
        sorted(Counter(item["reason_for_disagreement"] for item in wrong).items())
    )

    trust = evaluation["trust"]
    metrics = build_m336f_trust_metrics(
        actual_trusted=trust["correct_trusted"] + trust["wrong_trusted"],
        expected_trusted=trust["correct_trusted"] + trust["incorrect_withheld"],
        correct_trusted=trust["correct_trusted"],
        wrong_trusted=trust["wrong_trusted"],
        correct_withheld=trust["correct_withheld"],
        incorrect_withheld=trust["incorrect_withheld"],
    )
    trust_report = _sealed(
        {
            "schema_version": 1,
            "exact_r20_sha": R20_SHA,
            **{
                name: getattr(metrics, name)
                for name in (
                    "actual_trusted",
                    "expected_trusted",
                    "correct_trusted",
                    "wrong_trusted",
                    "correct_withheld",
                    "incorrect_withheld",
                    "trust_precision",
                    "trust_recall",
                    "legacy_trust_coverage",
                    "safe_trust_coverage",
                )
            },
            "metrics_hash": metrics.metrics_hash,
        }
    )
    wrong_report = _sealed(
        {
            "schema_version": 1,
            "exact_r20_sha": R20_SHA,
            "wrong_trusted_count": len(wrong),
            "root_cause_counts": root_cause_counts,
            "diagnostics_disappear_with_internal_closure": all(
                item["compilation_contexts"][1]["diagnostic_transition"] == "DISAPPEARS"
                for item in wrong
            ),
            "rows": tuple(wrong),
        }
    )
    public_field_rows = []
    for row in field_primary["rows"]:
        body = {
            key: value
            for key, value in row.items()
            if key not in {"actual_output", "expected_output", "forensic_row_hash"}
        }
        public_field_rows.append({**body, "forensic_row_hash": content_hash(body)})
    field_report = _sealed(
        {
            key: value
            for key, value in field_primary.items()
            if key not in {"report_hash", "rows"}
        }
        | {"rows": tuple(public_field_rows)}
    )
    platform_report = _platform_report(
        _load(args.windows_license_evaluation),
        _load(args.karina_license_evaluation),
    )
    _write(args.output / "r20_wrong_trusted_forensics.json", wrong_report)
    _write(args.output / "r20_trust_confusion_counts.json", trust_report)
    _write(args.output / "r20_field_evidence_mismatches.json", field_report)
    _write(args.output / "r20_platform_artifact_differences.json", platform_report)


def _load_compiler_context(path: Path):
    root = path.resolve(strict=True)
    report = java_production_compiler_report_from_dict(
        _load(root / "compiler_report.json")
    )
    index = _load(root / "declaration_index.json")
    return report, index


def _declaration_id_for_candidate(candidate, index):
    matches = tuple(
        item["declaration_id"]
        for item in index["declarations"]
        if item["source_unit_id"] == candidate["source_unit_id"]
        and item["byte_start"] == candidate["start_offset"]
        and item["byte_end"] == candidate["end_offset"]
    )
    if len(matches) != 1:
        raise ValueError("R20 candidate does not map to one compiler declaration")
    return matches[0]


def _context_rows(candidate, contexts):
    names = (
        "CURRENT_SELECTED_SET",
        "SELECTED_PLUS_INTERNAL_SOURCE_CLOSURE",
        "ALL_ANALYSIS_ELIGIBLE_FILES_FROM_THE_SAME_ROOT",
        "EXACT_FROZEN_PRODUCTION_CLASSPATH",
    )
    result = []
    for name, (report, index) in zip(names, contexts, strict=True):
        declaration_id = _declaration_id_for_candidate(candidate, index)
        enclosing_type_ids = frozenset(
            item["declaration_id"]
            for item in index["declarations"]
            if item["source_unit_id"] == candidate["source_unit_id"]
            and item["member_kind"]
            in {"class", "interface", "enum", "record", "annotation"}
            and item["byte_start"] <= candidate["start_offset"]
            and item["byte_end"] >= candidate["end_offset"]
        )
        diagnostic_by_hash = {item.diagnostic_hash: item for item in report.diagnostics}
        matches = tuple(
            (diagnostic_by_hash[item.diagnostic_hash], item)
            for item in report.bindings
            if _binding_blocks_candidate(
                item,
                declaration_id=declaration_id,
                enclosing_type_ids=enclosing_type_ids,
                source_unit_id=candidate["source_unit_id"],
            )
        )
        if matches:
            diagnostic, binding = min(
                matches,
                key=lambda item: (
                    item[0].diagnostic_kind != "ERROR",
                    item[1].diagnostic_scope.value,
                    item[0].diagnostic_code,
                ),
            )
            observation = CompilationContextObservation(
                True,
                diagnostic.diagnostic_code,
                binding.diagnostic_scope.value,
                report.compiler_identity_hash,
                not report.source_unit_unbound_count
                and not report.malformed_output_count,
                diagnostic.normalized_category,
            )
        else:
            observation = CompilationContextObservation(
                False,
                None,
                None,
                report.compiler_identity_hash,
                not report.source_unit_unbound_count
                and not report.malformed_output_count,
                None,
            )
        result.append((name, observation))
    return tuple(result)


def _binding_blocks_candidate(
    binding,
    *,
    declaration_id,
    enclosing_type_ids,
    source_unit_id,
):
    scope = binding.diagnostic_scope.value
    if scope == "DECLARATION_HEADER_BLOCKING":
        return declaration_id in binding.declaration_ids
    if scope == "ENCLOSING_TYPE_BLOCKING":
        return bool(enclosing_type_ids.intersection(binding.declaration_ids))
    if scope == "UNKNOWN_SCOPE":
        return binding.source_unit_id == source_unit_id
    return (
        scope == "AMBIENT_FILE"
        and binding.source_unit_id == source_unit_id
        and binding.normalized_category
        in {"DUPLICATE_SIGNATURE", "INVALID_IMPORT", "COMPILER_ENVIRONMENT_MISMATCH"}
    )


def _public_context(name, observation, current):
    if not observation.diagnostic_present:
        transition = "DISAPPEARS"
    elif observation.normalized_category != current.normalized_category:
        transition = "CHANGES_CATEGORY"
    elif observation.diagnostic_scope != current.diagnostic_scope:
        transition = "CHANGES_SCOPE"
    elif observation.diagnostic_code != current.diagnostic_code:
        transition = "CHANGES_DIAGNOSTIC_CODE"
    else:
        transition = "REMAINS_IDENTICAL"
    return {
        "context": name,
        "diagnostic_transition": transition,
        "diagnostic_code": observation.diagnostic_code,
        "diagnostic_scope": observation.diagnostic_scope,
        "normalized_category": observation.normalized_category,
        "compiler_identity_hash": observation.compiler_identity_hash,
    }


def _platform_report(windows, karina):
    rows = []
    telemetry = {
        "java_reference_compilation_seconds",
        "java_reference_spdx_match_seconds",
        "peak_java_reference_bytes",
        "production_spdx_match_seconds",
    }
    for name in sorted(set(windows) | set(karina)):
        if windows.get(name) == karina.get(name):
            continue
        derived = name == "report_hash"
        body = {
            "artifact_type": "independent_license_evaluation",
            "json_pointer": f"/{name}",
            "windows_value_class": type(windows.get(name)).__name__,
            "karina_value_class": type(karina.get(name)).__name__,
            "field_role": (
                "TELEMETRY_DERIVED_IDENTITY"
                if derived
                else "TELEMETRY"
                if name in telemetry
                else "SEMANTIC"
            ),
            "contract_role": "MISCLASSIFIED_PLATFORM_NEUTRAL",
            "remediation_class": "SPLIT_SEMANTIC_PAYLOAD_AND_HOST_TELEMETRY",
        }
        rows.append({**body, "difference_hash": content_hash(body)})
    body = {
        "schema_version": 1,
        "exact_r20_sha": R20_SHA,
        "artifact_byte_difference_count": int(bool(rows)),
        "semantic_field_difference_count": sum(
            item["field_role"] == "SEMANTIC" for item in rows
        ),
        "telemetry_field_difference_count": sum(
            item["field_role"] != "SEMANTIC" for item in rows
        ),
        "rows": tuple(rows),
    }
    return _sealed(body)


if __name__ == "__main__":
    main()
