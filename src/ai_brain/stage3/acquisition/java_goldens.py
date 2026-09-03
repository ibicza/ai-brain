"""Strict loader for independently authored and sealed Java location goldens."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash


@dataclass(frozen=True)
class ExpectedJavaProposalSemantics:
    target_id: str
    receiver_source_identity: str
    receiver_binary_identity: str
    parameter_names: tuple[str, ...]
    source_parameter_types: tuple[str, ...]
    resolved_parameter_types: tuple[str, ...]
    parameter_varargs: tuple[bool, ...]
    parameter_array_dimensions: tuple[int, ...]
    source_return_type: str
    resolved_return_type: str
    return_array_dimensions: int
    method_type_parameters: tuple[str, ...]
    intersection_bounds: tuple[tuple[str, ...], ...]
    first_bound_erasures: tuple[str, ...]
    declared_exception_source_types: tuple[str, ...]
    resolved_declared_exception_types: tuple[str, ...]
    modifiers: tuple[str, ...]
    accessibility: str
    enclosing_type_accessibility: str
    module_name: str | None
    package_exported: bool
    deprecated_since: str | None
    expected_knowledge_kind: str
    expected_epistemic_character: str
    expected_subject_type: str
    expected_object_type_kind: str
    expected_object_type_identity: str | None
    expected_claim_payload: str
    expected_semantic_content_hash: str
    complete_type_resolution_manifest_hash: str
    complete_proposal_field_manifest_hash: str
    expected_supported: bool
    expected_blocker_reason: str | None
    semantic_hash: str


@dataclass(frozen=True)
class JavaDiagnosticReceipt:
    diagnostic_code: str
    diagnostic_kind: str
    source_unit_id: str
    start_offset: int
    end_offset: int
    line: int
    column: int
    target_ids: tuple[str, ...]
    normalized_category: str
    applicability: str
    trust_relevant: bool
    receipt_hash: str


@dataclass(frozen=True)
class JavaGoldenLocation:
    golden_id: str
    source_unit_id: str
    document_bytes_hash: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    package_name: str | None
    top_level_type_name: str
    nested_type_path: tuple[str, ...]
    member_kind: str
    member_name: str
    canonical_source_signature: str
    erased_jvm_descriptor: str
    expected_supported: bool
    unsupported_reason: str | None
    negative_kind: str | None
    golden_hash: str
    expected_semantics: ExpectedJavaProposalSemantics | None = None
    diagnostic_receipt_hashes: tuple[str, ...] = ()


@dataclass(frozen=True)
class JavaGoldenManifest:
    schema_version: int
    authoring_implementation: str
    sealed_before_proposals: bool
    source_manifest_hash: str
    target_census_hash: str | None
    oracle_implementation_hash: str | None
    goldens: tuple[JavaGoldenLocation, ...]
    positive_count: int
    negative_count: int
    semantic_negative_count: int
    manifest_hash: str
    semantic_manifest_hash: str | None = None
    diagnostic_manifest_hash: str | None = None
    diagnostics: tuple[JavaDiagnosticReceipt, ...] = ()
    diagnostic_counts: tuple[tuple[str, int], ...] = ()


def load_java_golden_manifest(path: Path) -> JavaGoldenManifest:
    def strict_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate Java golden JSON key")
            result[key] = value
        return result

    row = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_object)
    expected_top_v1 = {
        "schema_version",
        "authoring_implementation",
        "sealed_before_proposals",
        "source_manifest_hash",
        "goldens",
        "positive_count",
        "manifest_hash",
    }
    expected_top_v2 = expected_top_v1 | {
        "target_census_hash",
        "oracle_implementation_hash",
        "negative_count",
        "semantic_negative_count",
    }
    expected_top_v3 = expected_top_v2 | {
        "semantic_manifest_hash",
        "diagnostic_manifest_hash",
        "diagnostics",
        "diagnostic_counts",
    }
    if frozenset(row) not in {
        frozenset(expected_top_v1),
        frozenset(expected_top_v2),
        frozenset(expected_top_v3),
    }:
        raise ValueError("Java golden manifest schema mismatch")
    goldens = []
    expected_fields_v2 = {
        item.name for item in JavaGoldenLocation.__dataclass_fields__.values()
    }
    semantic_fields = {"expected_semantics", "diagnostic_receipt_hashes"}
    expected_fields_v2 = expected_fields_v2 - semantic_fields
    expected_fields_v1 = expected_fields_v2 - {"unsupported_reason", "negative_kind"}
    expected_fields_v3 = expected_fields_v2 | semantic_fields
    for item in row["goldens"]:
        if frozenset(item) not in {
            frozenset(expected_fields_v1),
            frozenset(expected_fields_v2),
            frozenset(expected_fields_v3),
        }:
            raise ValueError("Java golden location schema mismatch")
        values = {
            "unsupported_reason": None,
            "negative_kind": None,
            **item,
            "nested_type_path": tuple(item["nested_type_path"]),
            "expected_semantics": (
                _expected_semantics(item["expected_semantics"])
                if item.get("expected_semantics") is not None
                else None
            ),
            "diagnostic_receipt_hashes": tuple(
                item.get("diagnostic_receipt_hashes", ())
            ),
        }
        golden = JavaGoldenLocation(**values)
        body = dict(item)
        claimed = body.pop("golden_hash")
        if row["schema_version"] == 1:
            body.pop("unsupported_reason", None)
            body.pop("negative_kind", None)
        if row["schema_version"] in {1, 2}:
            body.pop("expected_semantics", None)
            body.pop("diagnostic_receipt_hashes", None)
        if content_hash(body) != claimed:
            raise ValueError("Java golden location hash mismatch")
        goldens.append(golden)
    manifest = JavaGoldenManifest(
        schema_version=row["schema_version"],
        authoring_implementation=row["authoring_implementation"],
        sealed_before_proposals=row["sealed_before_proposals"],
        source_manifest_hash=row["source_manifest_hash"],
        target_census_hash=row.get("target_census_hash"),
        oracle_implementation_hash=row.get("oracle_implementation_hash"),
        goldens=tuple(goldens),
        positive_count=row["positive_count"],
        negative_count=row.get("negative_count", 0),
        semantic_negative_count=row.get("semantic_negative_count", 0),
        manifest_hash=row["manifest_hash"],
        semantic_manifest_hash=row.get("semantic_manifest_hash"),
        diagnostic_manifest_hash=row.get("diagnostic_manifest_hash"),
        diagnostics=tuple(_diagnostic(item) for item in row.get("diagnostics", ())),
        diagnostic_counts=tuple(
            tuple(item) for item in row.get("diagnostic_counts", ())
        ),
    )
    verify_java_golden_manifest(manifest)
    return manifest


def verify_java_golden_manifest(manifest: JavaGoldenManifest) -> None:
    """Recompute every seal so in-memory callers cannot forge golden objects."""

    for golden in manifest.goldens:
        body = asdict(golden)
        claimed = body.pop("golden_hash")
        if manifest.schema_version == 1:
            body.pop("unsupported_reason")
            body.pop("negative_kind")
        if manifest.schema_version in {1, 2}:
            body.pop("expected_semantics")
            body.pop("diagnostic_receipt_hashes")
        if content_hash(body) != claimed:
            raise ValueError("Java golden location hash mismatch")
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    if manifest.schema_version == 1:
        body["goldens"] = tuple(
            {
                key: value
                for key, value in asdict(golden).items()
                if key not in {"unsupported_reason", "negative_kind"}
            }
            for golden in manifest.goldens
        )
        for field in (
            "target_census_hash",
            "oracle_implementation_hash",
            "negative_count",
            "semantic_negative_count",
        ):
            body.pop(field)
    if manifest.schema_version in {1, 2}:
        for field in (
            "semantic_manifest_hash",
            "diagnostic_manifest_hash",
            "diagnostics",
            "diagnostic_counts",
        ):
            body.pop(field)
        if manifest.schema_version == 2:
            body["goldens"] = tuple(
                {
                    key: value
                    for key, value in asdict(golden).items()
                    if key not in {"expected_semantics", "diagnostic_receipt_hashes"}
                }
                for golden in manifest.goldens
            )
    if (
        content_hash(body) != claimed
        or manifest.schema_version not in {1, 2, 3}
        or not manifest.sealed_before_proposals
        or manifest.positive_count
        != sum(item.expected_supported for item in manifest.goldens)
        or manifest.negative_count
        != sum(not item.expected_supported for item in manifest.goldens)
        or len({item.golden_id for item in manifest.goldens}) != len(manifest.goldens)
    ):
        raise ValueError("Java golden manifest is not sealed or complete")
    if manifest.schema_version == 2 and (
        not manifest.target_census_hash
        or not manifest.oracle_implementation_hash
        or manifest.semantic_negative_count
        != sum(item.negative_kind == "SEMANTIC" for item in manifest.goldens)
    ):
        raise ValueError("Java golden semantic census is incomplete")
    if manifest.schema_version == 3:
        semantics = tuple(
            item.expected_semantics for item in manifest.goldens if item.expected_semantics
        )
        if (
            len(semantics) != len(manifest.goldens)
            or manifest.semantic_manifest_hash != content_hash(semantics)
            or manifest.diagnostic_manifest_hash != content_hash(manifest.diagnostics)
            or any(_rehash(item, "semantic_hash") != item for item in semantics)
            or any(_rehash(item, "receipt_hash") != item for item in manifest.diagnostics)
            or tuple(sorted(manifest.diagnostic_counts))
            != tuple(sorted(_diagnostic_counts(manifest.diagnostics)))
        ):
            raise ValueError("Java semantic proposal oracle manifest is incomplete")


def _expected_semantics(row) -> ExpectedJavaProposalSemantics:
    expected = set(ExpectedJavaProposalSemantics.__dataclass_fields__)
    if set(row) != expected:
        raise ValueError("expected Java proposal semantics schema mismatch")
    tuple_fields = {
        "parameter_names",
        "source_parameter_types",
        "resolved_parameter_types",
        "parameter_varargs",
        "parameter_array_dimensions",
        "method_type_parameters",
        "first_bound_erasures",
        "declared_exception_source_types",
        "resolved_declared_exception_types",
        "modifiers",
    }
    values = dict(row)
    for field in tuple_fields:
        values[field] = tuple(values[field])
    values["intersection_bounds"] = tuple(
        tuple(item) for item in values["intersection_bounds"]
    )
    return ExpectedJavaProposalSemantics(**values)


def _diagnostic(row) -> JavaDiagnosticReceipt:
    if set(row) != set(JavaDiagnosticReceipt.__dataclass_fields__):
        raise ValueError("Java diagnostic receipt schema mismatch")
    return JavaDiagnosticReceipt(**{**row, "target_ids": tuple(row["target_ids"])})


def _rehash(value, field):
    body = asdict(value)
    claimed = body.pop(field)
    return value if content_hash(body) == claimed else None


def _diagnostic_counts(values):
    counts: dict[str, int] = {}
    for item in values:
        counts[item.normalized_category] = counts.get(item.normalized_category, 0) + 1
    return tuple(sorted(counts.items()))
