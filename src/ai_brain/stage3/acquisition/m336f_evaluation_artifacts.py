"""Strict semantic/telemetry split for deterministic M-33.6f evaluation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from ai_brain.stage2.facts.canonical import canonical_json, content_hash

M336F_SEMANTIC_EVALUATION_CONTRACT = "m336f.semantic-evaluation.v1"
M336F_TELEMETRY_CONTRACT = "m336f.evaluation-telemetry.v1"
M336F_PUBLIC_CONTRACT_SCHEMA_VERSION = 2
_RATIO = re.compile(r"(?:0\.[0-9]{6}|1\.000000|N/A)\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ABSOLUTE_PATH = re.compile(r"(?:\A[A-Za-z]:[\\/]|\A/|[\\/]tmp[\\/])")


@dataclass(frozen=True)
class M336FSemanticEvaluationArtifact:
    schema_version: int
    contract_role: str
    identities: tuple[tuple[str, str], ...]
    counts: tuple[tuple[str, int], ...]
    ratios: tuple[tuple[str, str], ...]
    decisions: tuple[tuple[str, str], ...]
    hashes: tuple[tuple[str, str], ...]
    normalized_diagnostic_categories: tuple[tuple[str, int], ...]
    mismatch_manifest_hashes: tuple[tuple[str, str], ...]
    readiness_result: str
    artifact_hash: str


@dataclass(frozen=True)
class M336FEvaluationTelemetryReceipt:
    schema_version: int
    contract_role: str
    platform: str
    host_identity_hash: str
    operation_timings_seconds: tuple[tuple[str, str], ...]
    peak_memory_bytes: int
    jdk_executable_hash: str
    process_measurements: tuple[tuple[str, int], ...]
    receipt_hash: str


def build_m336f_semantic_evaluation_artifact(
    *,
    identities,
    counts,
    ratios,
    decisions,
    hashes,
    normalized_diagnostic_categories,
    mismatch_manifest_hashes,
    readiness_result: str,
) -> M336FSemanticEvaluationArtifact:
    body = {
        "schema_version": M336F_PUBLIC_CONTRACT_SCHEMA_VERSION,
        "contract_role": M336F_SEMANTIC_EVALUATION_CONTRACT,
        "identities": _ordered_pairs(identities, str),
        "counts": _ordered_pairs(counts, int),
        "ratios": _ordered_pairs(ratios, str),
        "decisions": _ordered_pairs(decisions, str),
        "hashes": _ordered_pairs(hashes, str),
        "normalized_diagnostic_categories": _ordered_pairs(
            normalized_diagnostic_categories, int
        ),
        "mismatch_manifest_hashes": _ordered_pairs(mismatch_manifest_hashes, str),
        "readiness_result": readiness_result,
    }
    value = M336FSemanticEvaluationArtifact(**body, artifact_hash=content_hash(body))
    verify_m336f_semantic_evaluation_artifact(value)
    return value


def build_m336f_evaluation_telemetry_receipt(
    *,
    platform: str,
    host_identity_hash: str,
    operation_timings_seconds,
    peak_memory_bytes: int,
    jdk_executable_hash: str,
    process_measurements,
) -> M336FEvaluationTelemetryReceipt:
    body = {
        "schema_version": M336F_PUBLIC_CONTRACT_SCHEMA_VERSION,
        "contract_role": M336F_TELEMETRY_CONTRACT,
        "platform": platform,
        "host_identity_hash": host_identity_hash,
        "operation_timings_seconds": _ordered_pairs(operation_timings_seconds, str),
        "peak_memory_bytes": peak_memory_bytes,
        "jdk_executable_hash": jdk_executable_hash,
        "process_measurements": _ordered_pairs(process_measurements, int),
    }
    value = M336FEvaluationTelemetryReceipt(**body, receipt_hash=content_hash(body))
    verify_m336f_evaluation_telemetry_receipt(value)
    return value


def verify_m336f_semantic_evaluation_artifact(
    value: M336FSemanticEvaluationArtifact,
) -> None:
    body = asdict(value)
    claimed = body.pop("artifact_hash")
    if (
        value.schema_version != M336F_PUBLIC_CONTRACT_SCHEMA_VERSION
        or value.contract_role != M336F_SEMANTIC_EVALUATION_CONTRACT
        or content_hash(body) != claimed
        or value.identities != _ordered_pairs(value.identities, str)
        or value.counts != _ordered_pairs(value.counts, int)
        or value.ratios != _ordered_pairs(value.ratios, str)
        or value.decisions != _ordered_pairs(value.decisions, str)
        or value.hashes != _ordered_pairs(value.hashes, str)
        or value.normalized_diagnostic_categories
        != _ordered_pairs(value.normalized_diagnostic_categories, int)
        or value.mismatch_manifest_hashes
        != _ordered_pairs(value.mismatch_manifest_hashes, str)
        or value.readiness_result not in {"PASS", "FAIL", "REVIEW_REQUIRED"}
        or any(not _RATIO.fullmatch(item) for _name, item in value.ratios)
        or any(not _HASH.fullmatch(item) for _name, item in value.hashes)
        or any(
            not _HASH.fullmatch(item) for _name, item in value.mismatch_manifest_hashes
        )
        or _contains_platform_data(body)
    ):
        raise ValueError("M-33.6f platform-neutral evaluation contract mismatch")


def verify_m336f_evaluation_telemetry_receipt(
    value: M336FEvaluationTelemetryReceipt,
) -> None:
    body = asdict(value)
    claimed = body.pop("receipt_hash")
    if (
        value.schema_version != M336F_PUBLIC_CONTRACT_SCHEMA_VERSION
        or value.contract_role != M336F_TELEMETRY_CONTRACT
        or value.platform not in {"windows", "karina"}
        or not _HASH.fullmatch(value.host_identity_hash)
        or not _HASH.fullmatch(value.jdk_executable_hash)
        or value.peak_memory_bytes < 0
        or value.operation_timings_seconds
        != _ordered_pairs(value.operation_timings_seconds, str)
        or value.process_measurements != _ordered_pairs(value.process_measurements, int)
        or any(
            _duration_is_invalid(item)
            for _name, item in value.operation_timings_seconds
        )
        or content_hash(body) != claimed
    ):
        raise ValueError("M-33.6f evaluation telemetry contract mismatch")


def semantic_artifacts_byte_identical(
    left: M336FSemanticEvaluationArtifact,
    right: M336FSemanticEvaluationArtifact,
) -> bool:
    verify_m336f_semantic_evaluation_artifact(left)
    verify_m336f_semantic_evaluation_artifact(right)
    return canonical_json(asdict(left)) == canonical_json(asdict(right))


def _ordered_pairs(values, value_type) -> tuple[tuple[str, object], ...]:
    items = tuple(values.items()) if isinstance(values, dict) else tuple(values)
    if any(
        not isinstance(name, str)
        or not name
        or (value_type is int and isinstance(value, bool))
        or not isinstance(value, value_type)
        for name, value in items
    ) or len({name for name, _value in items}) != len(items):
        raise ValueError("evaluation artifact contains invalid named values")
    return tuple(sorted(items))


def _contains_platform_data(value) -> bool:
    forbidden_names = {
        "elapsed",
        "duration",
        "host",
        "hostname",
        "os",
        "path",
        "pid",
        "platform",
        "timestamp",
        "timing",
    }
    for key, item in value.items():
        if set(re.split(r"[^a-z]+", key.casefold())) & forbidden_names:
            return True
        if isinstance(item, str) and _ABSOLUTE_PATH.search(item):
            return True
        if isinstance(item, (tuple, list)):
            for name, nested in item:
                if set(re.split(r"[^a-z]+", name.casefold())) & forbidden_names:
                    return True
                if isinstance(nested, str) and _ABSOLUTE_PATH.search(nested):
                    return True
    return False


def _duration_is_invalid(value: str) -> bool:
    try:
        duration = Decimal(value)
        return not duration.is_finite() or duration < 0
    except (InvalidOperation, TypeError, ValueError):
        return True
