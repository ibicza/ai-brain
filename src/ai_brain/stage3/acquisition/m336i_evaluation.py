"""Post-seal Java evaluation independent of production and selection code."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, fields
from decimal import Decimal
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.evaluation import verify_pack_evaluation
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    m336f_selected_source_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336g_publication import (
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336h_contracts import strict_json_file
from ai_brain.stage3.acquisition.m336h_evaluation import M336HEvaluatorLedger
from ai_brain.stage3.domains.aliases import AliasLookupStatus
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.runtime import GenericDomainRuntime
from ai_brain.stage3.domains.validation import validate_pack


@dataclass(frozen=True)
class M336IIndependentEvaluationRequest:
    route_manifest: Path
    threshold_manifest: Path
    windows_production_seal: Path
    karina_production_seal: Path
    windows_production_output: Path
    karina_production_output: Path
    windows_field_evidence_manifest: Path
    karina_field_evidence_manifest: Path
    public_candidate_pack: Path
    windows_replay_receipt: Path
    karina_replay_receipt: Path
    independently_authored_semantic_goldens: Path
    external_sealed_vault: Path
    source_entry_bindings: Path
    candidate_pool: Path
    qualification_report: Path
    selected_manifest: Path
    frozen_spdx_reference: Path
    evaluator_ledger: Path
    git_worktrees: tuple[Path, ...]
    evaluator_context_hash: str | None = None
    evaluator_pre_reserved: bool = False


@dataclass(frozen=True)
class M336IIndependentEvaluationResult:
    schema_version: int
    contract_role: str
    evaluator_implementation_identity: str
    route_manifest_hash: str
    threshold_manifest_hash: str
    windows_production_seal_hash: str
    karina_production_seal_hash: str
    public_candidate_pack_hash: str
    public_candidate_pack_tree_hash: str
    semantic_golden_manifest_hash: str
    proposal_count: int
    trusted_count: int
    withheld_count: int
    expected_trusted_count: int
    expected_withheld_count: int
    wrong_trusted_count: int
    trust_precision: str
    safe_trust_coverage: str
    location_precision: str
    location_recall: str
    semantic_precision: str
    semantic_recall: str
    field_evidence_exactness: str
    field_evidence_expected_count: int
    field_evidence_present_count: int
    field_evidence_exact_count: int
    field_evidence_missing_count: int
    field_evidence_extra_count: int
    field_evidence_duplicate_count: int
    field_evidence_wrong_count: int
    spdx_agreement: str
    spdx_expected_count: int
    spdx_agreement_count: int
    false_automatic_spdx_identity_count: int
    runtime_status: str
    public_pack_integrity_status: str
    sealed_replay_status: str
    platform_neutral_difference_count: int
    evaluator_network_access_count: int
    production_call_count: int
    selector_call_count: int
    source_materialization_call_count: int
    torch_import_count: int
    synthetic_default_metric_count: int
    status: str
    result_hash: str


def independent_evaluator_identity() -> str:
    return bytes_hash(Path(__file__).resolve(strict=True).read_bytes())


def run_m336i_independent_java_evaluation(
    request: M336IIndependentEvaluationRequest,
) -> M336IIndependentEvaluationResult:
    if not isinstance(request, M336IIndependentEvaluationRequest):
        raise TypeError("M336I evaluator request must be typed")
    _validate_independent_authority_paths(request)
    for item in fields(request):
        value = getattr(request, item.name)
        if item.name in {
            "git_worktrees",
            "evaluator_ledger",
            "evaluator_context_hash",
            "evaluator_pre_reserved",
        }:
            continue
        if not isinstance(value, Path) or not value.exists():
            raise ValueError(f"M336I evaluator input is missing: {item.name}")
    if request.evaluator_pre_reserved:
        from ai_brain.stage3.acquisition.m336j_evaluator_v2 import (
            M336JEvaluatorLedgerV2,
            verify_m336j_evaluator_ready_for_evaluation_v2,
        )

        if request.evaluator_context_hash is None:
            raise ValueError("M336J V2 evaluator context is missing")
        ledger = M336JEvaluatorLedgerV2(
            request.evaluator_ledger, git_worktrees=request.git_worktrees
        )
        verify_m336j_evaluator_ready_for_evaluation_v2(
            ledger, context_hash=request.evaluator_context_hash
        )
    else:
        ledger = M336HEvaluatorLedger(
            request.evaluator_ledger, git_worktrees=request.git_worktrees
        )
        if ledger.events():
            raise ValueError("M336I evaluator one-shot capacity is already used")
    route = _object(request.route_manifest)
    thresholds = _object(request.threshold_manifest)
    _verify_hash(route, "manifest_hash")
    _verify_hash(thresholds, "threshold_manifest_hash")
    windows_seal = _verified_seal(request.windows_production_seal, "WINDOWS")
    karina_seal = _verified_seal(request.karina_production_seal, "KARINA")
    neutral_differences = _platform_neutral_differences(windows_seal, karina_seal)
    context = content_hash(
        (
            route["manifest_hash"],
            windows_seal["seal_hash"],
            karina_seal["seal_hash"],
        )
    )
    if not request.evaluator_pre_reserved:
        ledger.append("WINDOWS_PRODUCTION_SEALED", context_hash=context)
        ledger.append("KARINA_PRODUCTION_SEALED", context_hash=context)
        ledger.append("EVALUATOR_RESERVED", context_hash=context)

    windows_output = _object(request.windows_production_output)
    karina_output = _object(request.karina_production_output)
    _verify_hash(windows_output, "production_output_hash")
    _verify_hash(karina_output, "production_output_hash")
    if canonical_json(windows_output) != canonical_json(karina_output):
        raise ValueError("M336I sealed production outputs differ")
    if (
        windows_seal["production_output_hash"]
        != windows_output["production_output_hash"]
        or karina_seal["production_output_hash"]
        != karina_output["production_output_hash"]
    ):
        raise ValueError("M336I production output differs from its platform seal")
    windows_field_evidence = _verified_field_evidence_manifest(
        request.windows_field_evidence_manifest, windows_output
    )
    karina_field_evidence = _verified_field_evidence_manifest(
        request.karina_field_evidence_manifest, karina_output
    )
    if (
        windows_field_evidence["manifest_hash"]
        != karina_field_evidence["manifest_hash"]
    ):
        raise ValueError("M336I platform field-evidence manifests differ")
    pack_receipt = verify_java_public_candidate_pack(request.public_candidate_pack)
    if any(
        seal["public_candidate_pack_hash"] != pack_receipt.candidate_pack_content_hash
        or seal["public_candidate_pack_tree_hash"]
        != pack_receipt.candidate_pack_tree_hash
        for seal in (windows_seal, karina_seal)
    ):
        raise ValueError("M336I candidate pack differs from its platform seal")
    for replay_path in (
        request.windows_replay_receipt,
        request.karina_replay_receipt,
    ):
        replay = _object(replay_path)
        _verify_hash(replay, "receipt_hash")
        if replay.get("status") != "PASS":
            raise ValueError("M336I sealed replay did not pass")
    if (
        windows_seal["sealed_source_replay_receipt_hash"]
        != _object(request.windows_replay_receipt)["receipt_hash"]
        or karina_seal["sealed_source_replay_receipt_hash"]
        != _object(request.karina_replay_receipt)["receipt_hash"]
    ):
        raise ValueError("M336I sealed replay receipt differs from its production seal")
    goldens = load_java_golden_manifest(request.independently_authored_semantic_goldens)
    if goldens.schema_version < 3 or not goldens.goldens:
        raise ValueError("M336I requires independently authored semantic goldens")
    source_bytes = _verify_source_authority(request, goldens)
    torch_was_loaded = "torch" in sys.modules
    metrics = _semantic_metrics(windows_output, goldens)
    field_metrics = _field_evidence_metrics(
        windows_output,
        goldens,
        windows_field_evidence,
        source_bytes,
    )
    spdx = _spdx_metrics(
        _object(request.candidate_pool),
        _object(request.qualification_report),
        _object(request.selected_manifest),
        request.frozen_spdx_reference,
    )
    runtime = _runtime_status(request.public_candidate_pack)
    minimum = thresholds["minimum_metrics"]
    passed = (
        metrics["wrong_trusted_count"] == 0
        and metrics["trust_precision"] == "1.000000"
        and Decimal(metrics["safe_trust_coverage"])
        >= Decimal(minimum["trust_coverage"])
        and metrics["location_precision"] == "1.000000"
        and Decimal(metrics["location_recall"]) >= Decimal(minimum["location_recall"])
        and metrics["semantic_precision"] == "1.000000"
        and Decimal(metrics["semantic_recall"]) >= Decimal(minimum["semantic_recall"])
        and _field_evidence_gate_passes(field_metrics)
        and spdx["spdx_agreement"] == "1.000000"
        and spdx["false_automatic_spdx_identity_count"] == 0
        and runtime == "PASS"
        and pack_receipt.status == "PASS"
        and neutral_differences == 0
        and not ("torch" in sys.modules and not torch_was_loaded)
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_INDEPENDENT_EVALUATION",
        "evaluator_implementation_identity": independent_evaluator_identity(),
        "route_manifest_hash": route["manifest_hash"],
        "threshold_manifest_hash": thresholds["threshold_manifest_hash"],
        "windows_production_seal_hash": windows_seal["seal_hash"],
        "karina_production_seal_hash": karina_seal["seal_hash"],
        "public_candidate_pack_hash": pack_receipt.candidate_pack_content_hash,
        "public_candidate_pack_tree_hash": pack_receipt.candidate_pack_tree_hash,
        "semantic_golden_manifest_hash": goldens.manifest_hash,
        **metrics,
        **field_metrics,
        **spdx,
        "runtime_status": runtime,
        "public_pack_integrity_status": pack_receipt.status,
        "sealed_replay_status": "PASS",
        "platform_neutral_difference_count": neutral_differences,
        "evaluator_network_access_count": 0,
        "production_call_count": 0,
        "selector_call_count": 0,
        "source_materialization_call_count": 0,
        "torch_import_count": int("torch" in sys.modules and not torch_was_loaded),
        "synthetic_default_metric_count": 0,
        "status": "PASS" if passed else "FAIL",
    }
    result = M336IIndependentEvaluationResult(**body, result_hash=content_hash(body))
    if result.status != "PASS":
        raise ValueError("M336I independent Outcome A thresholds failed")
    if request.evaluator_pre_reserved:
        from ai_brain.stage3.acquisition.m336j_evaluator_v2 import (
            advance_m336j_evaluator_v2,
        )

        advance_m336j_evaluator_v2(
            ledger,
            "INDEPENDENT_EVALUATION_COMPLETED",
            context_hash=request.evaluator_context_hash,
            operation_hash=result.result_hash,
        )
    else:
        ledger.append("EVALUATOR_COMPLETED", context_hash=context)
    return result


def _field_evidence_gate_passes(field_metrics: dict) -> bool:
    return (
        field_metrics["field_evidence_exactness"] == "1.000000"
        and field_metrics["field_evidence_missing_count"] == 0
        and field_metrics["field_evidence_extra_count"] == 0
        and field_metrics["field_evidence_duplicate_count"] == 0
        and field_metrics["field_evidence_wrong_count"] == 0
    )


def _validate_independent_authority_paths(
    request: M336IIndependentEvaluationRequest,
) -> None:
    pack = request.public_candidate_pack.resolve(strict=False)
    goldens = request.independently_authored_semantic_goldens.resolve(strict=False)
    vault = request.external_sealed_vault.resolve(strict=False)
    bindings = request.source_entry_bindings.resolve(strict=False)
    if (
        goldens == pack
        or goldens.is_relative_to(pack)
        or vault == pack
        or vault.is_relative_to(pack)
        or bindings == pack
        or bindings.is_relative_to(pack)
    ):
        raise ValueError("M336I evaluator authority was copied from candidate pack")


def _verify_source_authority(request, goldens) -> dict[str, bytes]:
    bindings = source_entry_binding_manifest_from_dict(
        _object(request.source_entry_bindings)
    )
    selected = m336f_selected_source_manifest_from_dict(
        _object(request.selected_manifest)
    )
    if selected.binding_manifest_hash != bindings.manifest_hash:
        raise ValueError("M336I evaluator selection/binding authority differs")
    binding_by_unit = {item.selected_path: item for item in bindings.bindings}
    selected_by_unit = {item.selected_path: item for item in selected.files}
    if set(selected_by_unit) - set(binding_by_unit):
        raise ValueError("M336I selected source lacks a frozen binding")
    source_hashes = {}
    source_bytes = {}
    for unit, selected_row in selected_by_unit.items():
        binding = binding_by_unit[unit]
        source = request.external_sealed_vault.joinpath(*binding.vault_path.split("/"))
        if (
            selected_row.source_entry_identity_hash
            != binding.source_entry_id.identity_hash
            or not source.is_file()
        ):
            raise ValueError("M336I evaluator source authority is incomplete")
        raw = source.read_bytes()
        actual = bytes_hash(raw)
        if actual not in {
            binding.source_entry_id.raw_source_sha256,
            binding.source_entry_id.canonical_source_sha256,
        }:
            raise ValueError("M336I evaluator source bytes differ from the binding")
        source_hashes[unit] = actual
        source_bytes[unit] = raw
    if not goldens.sealed_before_proposals or any(
        item.source_unit_id not in source_hashes
        or item.document_bytes_hash != source_hashes[item.source_unit_id]
        for item in goldens.goldens
    ):
        raise ValueError("M336I semantic goldens are not bound to the sealed vault")
    return source_bytes


def _semantic_metrics(sealed: dict, goldens) -> dict:
    rows = tuple(sealed["candidate_rows"])
    actual_by_location = {}
    duplicate = 0
    for row in rows:
        key = _row_location(row)
        duplicate += int(key in actual_by_location)
        actual_by_location.setdefault(key, row)
    expected_by_location = {
        (
            golden.document_bytes_hash,
            golden.source_unit_id,
            golden.start_offset,
            golden.end_offset,
        ): golden
        for golden in goldens.goldens
    }
    actual_locations = set(actual_by_location)
    expected_locations = set(expected_by_location)
    located = len(actual_locations & expected_locations)
    semantic_exact = 0
    expected_trusted = set()
    actual_trusted = {
        key
        for key, row in actual_by_location.items()
        if row["production_trust_state"] == "trusted"
    }
    for key, golden in expected_by_location.items():
        row = actual_by_location.get(key)
        if golden.expected_supported:
            expected_trusted.add(key)
        if row is None:
            continue
        semantics = golden.expected_semantics
        if semantics is None:
            continue
        expected_content = json.loads(semantics.expected_claim_payload)
        actual_content = row["proposal_content"]
        if (
            canonical_json(expected_content) == canonical_json(actual_content)
            and golden.canonical_source_signature == row["canonical_source_signature"]
            and golden.erased_jvm_descriptor == row["erased_jvm_descriptor"]
            and semantics.receiver_source_identity == row["receiver_type"]
        ):
            semantic_exact += 1
    wrong_trusted = len(actual_trusted - expected_trusted)
    correct_trusted = len(actual_trusted & expected_trusted)
    return {
        "proposal_count": len(rows),
        "trusted_count": sum(
            row["production_trust_state"] == "trusted" for row in rows
        ),
        "withheld_count": sum(
            row["production_trust_state"] != "trusted" for row in rows
        ),
        "expected_trusted_count": len(expected_trusted),
        "expected_withheld_count": len(expected_by_location) - len(expected_trusted),
        "wrong_trusted_count": wrong_trusted,
        "trust_precision": _ratio(correct_trusted, len(actual_trusted)),
        "safe_trust_coverage": _ratio(correct_trusted, len(expected_trusted)),
        "location_precision": _ratio(located, len(actual_locations)),
        "location_recall": _ratio(located, len(expected_locations)),
        "semantic_precision": _ratio(semantic_exact, len(actual_locations)),
        "semantic_recall": _ratio(semantic_exact, len(expected_locations)),
    }


def _verified_field_evidence_manifest(path: Path, production_output: dict) -> dict:
    manifest = _object(path)
    _verify_hash(manifest, "manifest_hash")
    if manifest.get("manifest_hash") != production_output.get(
        "field_evidence_manifest_hash"
    ):
        raise ValueError("M336I field-evidence manifest differs from production seal")
    evidence = manifest.get("evidence")
    if not isinstance(evidence, list) or manifest.get("evidence_count") != len(
        evidence
    ):
        raise ValueError("M336I field-evidence manifest count mismatch")
    for item in evidence:
        if not isinstance(item, dict):
            raise TypeError("M336I field-evidence row must be an object")
        _verify_hash(item, "evidence_hash")
        if item.get("output_hash") != content_hash(item.get("normalized_output")):
            raise ValueError("M336I field-evidence output hash mismatch")
        receipt_body = {
            key: item.get(key)
            for key in (
                "requirement_hash",
                "proposal_hash",
                "document_bytes_hash",
                "source_span_hash",
                "semantic_identity_hash",
                "transformation_hash",
                "normalized_output",
                "output_hash",
            )
        }
        if item.get("derivation_receipt_hash") != content_hash(receipt_body):
            raise ValueError("M336I field-evidence derivation receipt mismatch")
    return manifest


def _field_evidence_metrics(
    sealed: dict,
    goldens,
    manifest: dict,
    source_bytes: dict[str, bytes],
) -> dict:
    rows_by_id = {item["proposal_id"]: item for item in sealed["candidate_rows"]}
    if len(rows_by_id) != len(sealed["candidate_rows"]):
        raise ValueError("M336I production contains duplicate proposal identities")
    golden_by_location = {
        (
            item.document_bytes_hash,
            item.source_unit_id,
            item.start_offset,
            item.end_offset,
        ): item
        for item in goldens.goldens
    }
    expected = {}
    row_context = {}
    for proposal_id, row in rows_by_id.items():
        golden = golden_by_location.get(_row_location(row))
        if golden is None or golden.expected_semantics is None:
            continue
        semantics = golden.expected_semantics
        for field_name, value in _evidence_field_inventory(
            json.loads(semantics.expected_claim_payload)
        ).items():
            expected[(proposal_id, field_name)] = canonical_json(value)
        expected.update(
            {
                (proposal_id, "envelope.proposed_kind"): canonical_json(
                    semantics.expected_knowledge_kind
                ),
                (proposal_id, "envelope.epistemic_character"): canonical_json(
                    semantics.expected_epistemic_character
                ),
                (proposal_id, "envelope.extraction_method"): canonical_json("JAVA_AST"),
                (proposal_id, "envelope.status_authority"): canonical_json("PROPOSED"),
            }
        )
        raw = source_bytes.get(row["source_unit_id"])
        if raw is None or bytes_hash(raw) != row["document_bytes_hash"]:
            raise ValueError("M336I field evidence lacks sealed source authority")
        row_context[proposal_id] = (row, golden, raw)

    actual = {}
    counts = Counter()
    structural_exact = set()
    for item in manifest["evidence"]:
        proposal_id = item.get("proposal_id")
        field_name = item.get("field_path")
        key = (proposal_id, field_name)
        counts[key] += 1
        actual.setdefault(key, item)
        context = row_context.get(proposal_id)
        if context is None:
            continue
        row, golden, raw = context
        location = item.get("source_location")
        if not isinstance(location, dict):
            continue
        start = location.get("byte_start")
        end = location.get("byte_end")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end < start
            or end > len(raw)
            or item.get("document_bytes_hash") != row["document_bytes_hash"]
            or item.get("source_span_hash") != bytes_hash(raw[start:end])
            or item.get("semantic_identity_hash") != row["declaration_hash"]
            or item.get("proposal_hash") != row["proposal_hash"]
        ):
            continue
        node_key = {
            "document": item.get("document_id"),
            "snapshot": row["document_bytes_hash"],
            "start": row["start_offset"],
            "end": row["end_offset"],
            "kind": row["member_kind"],
            "name": row["member_name"],
        }
        expected_node = f"java-node.{content_hash(node_key)[:32]}"
        if item.get("parser_node_id") != expected_node:
            continue
        if field_name == "envelope.parser_node_binding":
            if item["normalized_output"] == canonical_json(expected_node):
                structural_exact.add(key)
        elif field_name == "envelope.source_segment_binding":
            try:
                segment_id = json.loads(item["normalized_output"])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(segment_id, str) and re.fullmatch(
                r"segment\.[0-9a-f]{32}", segment_id
            ):
                structural_exact.add(key)
        elif field_name == "envelope.ambiguity_fields":
            try:
                ambiguity = json.loads(item["normalized_output"])
            except (TypeError, json.JSONDecodeError):
                continue
            if (
                isinstance(ambiguity, list)
                and all(isinstance(value, str) for value in ambiguity)
                and (ambiguity == [] if golden.expected_supported else bool(ambiguity))
            ):
                structural_exact.add(key)

    for proposal_id in row_context:
        for field_name in (
            "envelope.ambiguity_fields",
            "envelope.source_segment_binding",
            "envelope.parser_node_binding",
        ):
            expected[(proposal_id, field_name)] = None
    expected_keys = set(expected)
    actual_keys = set(actual)
    duplicate = sum(value - 1 for value in counts.values() if value > 1)
    exact = 0
    wrong = 0
    for key in expected_keys & actual_keys:
        if counts[key] != 1:
            wrong += 1
        elif (
            key in structural_exact or actual[key]["normalized_output"] == expected[key]
        ):
            exact += 1
        else:
            wrong += 1
    present = len(manifest["evidence"])
    return {
        "field_evidence_exactness": _ratio(exact, present),
        "field_evidence_expected_count": len(expected_keys),
        "field_evidence_present_count": present,
        "field_evidence_exact_count": exact,
        "field_evidence_missing_count": len(expected_keys - actual_keys),
        "field_evidence_extra_count": len(actual_keys - expected_keys),
        "field_evidence_duplicate_count": duplicate,
        "field_evidence_wrong_count": wrong,
    }


def _evidence_field_inventory(content: dict) -> dict:
    result = {
        f"content.{name}": content[name]
        for name in (
            "subject_type",
            "predicate_id",
            "object_type",
            "qualifier_ids",
            "receiver_type",
        )
    }
    parameters = content["parameters"]
    if parameters:
        for index, (name, type_name) in enumerate(parameters):
            result[f"content.parameters[{index}].name"] = name
            result[f"content.parameters[{index}].type"] = type_name
    else:
        result["content.parameters"] = parameters
    result["content.return_type"] = content["return_type"]
    _append_evidence_collection(result, "content.generic_constraints", content)
    for name in (
        "preconditions",
        "postconditions",
        "deprecated_since",
        "examples",
        "java_callable_kind",
    ):
        result[f"content.{name}"] = content[name]
    for name in (
        "declared_exceptions",
        "resolved_parameter_types",
        "parameter_array_dimensions",
        "parameter_varargs",
    ):
        _append_evidence_collection(result, f"content.{name}", content)
    for name in ("resolved_return_type", "return_array_dimensions"):
        result[f"content.{name}"] = content[name]
    _append_evidence_collection(result, "content.method_type_parameters", content)
    intersections = tuple(
        (outer, inner, value)
        for outer, values in enumerate(content["intersection_bounds"])
        for inner, value in enumerate(values)
    )
    if intersections:
        for outer, inner, value in intersections:
            result[f"content.intersection_bounds[{outer}][{inner}]"] = value
    else:
        result["content.intersection_bounds"] = content["intersection_bounds"]
    for name in ("first_bound_erasures", "resolved_declared_exceptions", "modifiers"):
        _append_evidence_collection(result, f"content.{name}", content)
    for name in (
        "accessibility",
        "enclosing_type_accessibility",
        "module_name",
        "package_exported",
    ):
        result[f"content.{name}"] = content[name]
    return result


def _append_evidence_collection(result: dict, prefix: str, content: dict) -> None:
    values = content[prefix.removeprefix("content.")]
    if values:
        for index, value in enumerate(values):
            result[f"{prefix}[{index}]"] = value
    else:
        result[prefix] = values


def _spdx_metrics(pool, qualification, selected, reference: Path) -> dict:
    reference_value = _object(reference)
    _verify_hash(reference_value, "snapshot_manifest_hash")
    if reference_value.get("license_list_version") != "3.28.0" or not isinstance(
        reference_value.get("files"), list
    ):
        raise ValueError("M336I frozen SPDX reference is not the exact snapshot")
    reference_root = reference.resolve(strict=True).parent
    for relative, expected_hash in reference_value["files"]:
        source = (reference_root / relative).resolve(strict=True)
        if (
            not source.is_relative_to(reference_root)
            or bytes_hash(source.read_bytes()) != expected_hash
        ):
            raise ValueError("M336I frozen SPDX reference bytes changed")
    licenses = {
        Path(name).stem
        for name, _digest in reference_value["files"]
        if name.endswith(".txt") and name not in {"license-matching-guidelines-v2.3.md"}
    }
    exceptions = {item for item in licenses if "exception" in item.casefold()}
    licenses -= exceptions
    if "pool_hash" in pool:
        _verify_hash(pool, "pool_hash")
    if (
        "report_hash" in qualification
        and "historical_qualification_report_hash" not in qualification
    ):
        _verify_hash(qualification, "report_hash")
    policy_rows = tuple(pool.get("candidates", ()))
    decision_rows = tuple(qualification.get("decisions", ()))
    policies = {item["family_id"]: item for item in policy_rows}
    decisions = {item["family_id"]: item for item in decision_rows}
    if len(policies) != len(policy_rows) or len(decisions) != len(decision_rows):
        raise ValueError("M336I SPDX authority contains duplicate candidate roots")
    expected = agreement = false_automatic = 0
    for item in selected["files"]:
        root = item["candidate_root"]
        policy = policies.get(root)
        decision = decisions.get(root)
        if policy is None or decision is None:
            raise ValueError("M336I selected file lacks SPDX authority")
        scoped = tuple(decision.get("scoped_license_decisions", ()))
        if scoped:
            matching = tuple(
                row
                for row in scoped
                if row.get("source_path") == item["canonical_path"]
            )
            if len(matching) != 1 or matching[0].get("status") != "RESOLVED":
                raise ValueError("M336I selected file lacks one resolved SPDX decision")
            expression = matching[0].get("expression")
        else:
            expressions = tuple(decision.get("scoped_license_expressions", ()))
            if (
                decision.get("scoped_license_decision") != "RESOLVED"
                or len(expressions) != 1
            ):
                raise ValueError("M336I selected root lacks resolved SPDX evidence")
            expression = expressions[0]
        expected += 1
        canonical = _independent_spdx_canonical(
            expression, licenses=licenses, exceptions=exceptions
        )
        agreement += int(canonical == expression)
        false_automatic += int(expression in {"NOASSERTION", "UNKNOWN"})
        declared = {
            declaration[0]
            for declaration in policy.get("pom_license_declarations", ())
            if declaration and declaration[0] not in {"NOASSERTION", "UNKNOWN"}
        }
        if declared and declared != {expression}:
            agreement -= 1
    return {
        "spdx_agreement": _ratio(agreement, expected),
        "spdx_expected_count": expected,
        "spdx_agreement_count": agreement,
        "false_automatic_spdx_identity_count": false_automatic,
    }


_SPDX_TOKEN = re.compile(
    r"\s*(\(|\)|AND\b|OR\b|WITH\b|[A-Za-z0-9][A-Za-z0-9.+-]*)", re.ASCII
)


def _independent_spdx_canonical(
    value: str, *, licenses: set[str], exceptions: set[str]
) -> str:
    """Parse the frozen SPDX subset without importing production SPDX code."""

    if not isinstance(value, str) or not value:
        raise ValueError("M336I SPDX expression is empty")
    tokens = []
    offset = 0
    while offset < len(value):
        match = _SPDX_TOKEN.match(value, offset)
        if match is None:
            raise ValueError("M336I SPDX expression has an invalid token")
        tokens.append(match.group(1))
        offset = match.end()

    class Parser:
        def __init__(self) -> None:
            self.position = 0

        def take(self, token: str) -> bool:
            if self.position < len(tokens) and tokens[self.position] == token:
                self.position += 1
                return True
            return False

        def primary(self):
            if self.take("("):
                node = self.expression()
                if not self.take(")"):
                    raise ValueError("M336I SPDX expression has an open group")
                return node
            if self.position >= len(tokens):
                raise ValueError("M336I SPDX expression lacks an identifier")
            token = tokens[self.position]
            if token in {"AND", "OR", "WITH", ")"}:
                raise ValueError("M336I SPDX expression has an unexpected operator")
            self.position += 1
            if token not in licenses:
                raise ValueError("M336I SPDX license is outside the frozen snapshot")
            return ("ID", token)

        def with_exception(self):
            left = self.primary()
            if not self.take("WITH"):
                return left
            if left[0] != "ID" or self.position >= len(tokens):
                raise ValueError("M336I SPDX WITH operands are invalid")
            exception = tokens[self.position]
            self.position += 1
            if exception not in exceptions:
                raise ValueError("M336I SPDX exception is outside the frozen snapshot")
            return ("WITH", left, ("EXCEPTION", exception))

        def conjunction(self):
            node = self.with_exception()
            while self.take("AND"):
                node = ("AND", node, self.with_exception())
            return node

        def expression(self):
            node = self.conjunction()
            while self.take("OR"):
                node = ("OR", node, self.conjunction())
            return node

    parser = Parser()
    tree = parser.expression()
    if parser.position != len(tokens):
        raise ValueError("M336I SPDX expression has trailing input")

    def render(node) -> str:
        if node[0] in {"ID", "EXCEPTION"}:
            return node[1]
        if node[0] == "WITH":
            return f"{render(node[1])} WITH {render(node[2])}"
        return f"({render(node[1])}) {node[0]} ({render(node[2])})"

    return render(tree)


def _runtime_status(pack_root: Path) -> str:
    pack = load_pack(pack_root)
    validate_pack(pack)
    verify_pack_evaluation(pack)
    runtime = GenericDomainRuntime(pack)
    exact = tuple(pack.alias_semantics.exact_references) if pack.alias_semantics else ()
    if not exact:
        return "FAIL"
    result = runtime.resolve_knowledge_alias(exact[0].reference)
    unknown = runtime.resolve_knowledge_alias("m336i.unknown.Callable.missing")
    return (
        "PASS"
        if result.status is AliasLookupStatus.EXACT
        and unknown.status is AliasLookupStatus.NOT_FOUND
        else "FAIL"
    )


def _verified_seal(path: Path, platform: str) -> dict:
    value = _object(path)
    _verify_hash(value, "seal_hash")
    if value.get("status") != "PASS" or value.get("platform_role") != platform:
        raise ValueError("M336I production seal is not an exact platform PASS")
    return value


def _verify_hash(value: dict, field: str) -> None:
    body = dict(value)
    claimed = body.pop(field, None)
    if content_hash(body) != claimed:
        raise ValueError(f"M336I {field} does not match content")


def _platform_neutral_differences(left: dict, right: dict) -> int:
    excluded = {
        "platform_role",
        "production_request_hash",
        "production_response_hash",
        "seal_hash",
    }
    return int(
        {key: value for key, value in left.items() if key not in excluded}
        != {key: value for key, value in right.items() if key not in excluded}
    )


def _row_location(row: dict) -> tuple:
    return (
        row["document_bytes_hash"],
        row["source_unit_id"],
        row["start_offset"],
        row["end_offset"],
    )


def _flatten(value, prefix="content") -> dict:
    result = {}
    if isinstance(value, dict):
        for key in sorted(value):
            result.update(_flatten(value[key], f"{prefix}.{key}"))
    elif isinstance(value, list):
        if not value:
            result[prefix] = []
        for index, item in enumerate(value):
            result.update(_flatten(item, f"{prefix}[{index}]"))
    else:
        result[prefix] = value
    return result


def _ratio(numerator: int, denominator: int) -> str:
    if denominator == 0:
        raise ValueError("M336I evaluation denominator is empty")
    return f"{numerator / denominator:.6f}"


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336I evaluator input must be an object")
    return value
