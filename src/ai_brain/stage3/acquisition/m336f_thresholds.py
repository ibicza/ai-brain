"""Frozen count-first acceptance thresholds for M-33.6f Java evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from ai_brain.stage2.facts.canonical import content_hash


@dataclass(frozen=True)
class M336FJavaAcceptanceThresholds:
    schema_version: int
    location_precision: str
    location_recall: str
    semantic_precision: str
    semantic_recall: str
    trust_precision: str
    safe_trust_coverage: str
    field_evidence_exactness: str
    resolution_agreement: str
    wrong_trusted: int
    post_trust_pack_failures: int
    cross_platform_semantic_differences: int
    fresh_source_leaks: int
    manifest_hash: str


def _threshold_manifest() -> M336FJavaAcceptanceThresholds:
    body = {
        "schema_version": 1,
        "location_precision": "1.000000",
        "location_recall": "0.950000",
        "semantic_precision": "1.000000",
        "semantic_recall": "0.950000",
        "trust_precision": "1.000000",
        "safe_trust_coverage": "0.850000",
        "field_evidence_exactness": "1.000000",
        "resolution_agreement": "1.000000",
        "wrong_trusted": 0,
        "post_trust_pack_failures": 0,
        "cross_platform_semantic_differences": 0,
        "fresh_source_leaks": 0,
    }
    return M336FJavaAcceptanceThresholds(
        **body,
        manifest_hash=content_hash(body),
    )


M336F_JAVA_ACCEPTANCE_THRESHOLDS = _threshold_manifest()


@dataclass(frozen=True)
class M336FTrustMetrics:
    actual_trusted: int
    expected_trusted: int
    correct_trusted: int
    wrong_trusted: int
    correct_withheld: int
    incorrect_withheld: int
    trust_precision: str
    trust_recall: str
    legacy_trust_coverage: str
    safe_trust_coverage: str
    metrics_hash: str


def ratio_string(numerator: int, denominator: int) -> str:
    if numerator < 0 or denominator < 0:
        raise ValueError("ratio counts cannot be negative")
    if denominator == 0:
        return "N/A"
    return f"{Decimal(numerator) / Decimal(denominator):.6f}"


def ratio_meets_threshold(numerator: int, denominator: int, threshold: str) -> bool:
    """Compare a count ratio exactly; caller-provided display strings are ignored."""

    if numerator < 0 or denominator <= 0:
        return False
    try:
        limit = Decimal(threshold)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("acceptance threshold is not an exact decimal") from error
    if not Decimal(0) <= limit <= Decimal(1):
        raise ValueError("acceptance threshold is outside [0, 1]")
    return Decimal(numerator) >= limit * Decimal(denominator)


def build_m336f_trust_metrics(
    *,
    actual_trusted: int,
    expected_trusted: int,
    correct_trusted: int,
    wrong_trusted: int,
    correct_withheld: int,
    incorrect_withheld: int,
) -> M336FTrustMetrics:
    counts = (
        actual_trusted,
        expected_trusted,
        correct_trusted,
        wrong_trusted,
        correct_withheld,
        incorrect_withheld,
    )
    if any(value < 0 for value in counts):
        raise ValueError("trust confusion counts cannot be negative")
    if actual_trusted != correct_trusted + wrong_trusted:
        raise ValueError("actual trusted denominator differs from confusion counts")
    if expected_trusted != correct_trusted + incorrect_withheld:
        raise ValueError("expected trusted denominator differs from confusion counts")
    body = {
        "actual_trusted": actual_trusted,
        "expected_trusted": expected_trusted,
        "correct_trusted": correct_trusted,
        "wrong_trusted": wrong_trusted,
        "correct_withheld": correct_withheld,
        "incorrect_withheld": incorrect_withheld,
        "trust_precision": ratio_string(correct_trusted, actual_trusted),
        "trust_recall": ratio_string(correct_trusted, expected_trusted),
        "legacy_trust_coverage": ratio_string(actual_trusted, expected_trusted),
        "safe_trust_coverage": ratio_string(correct_trusted, expected_trusted),
    }
    if wrong_trusted == 0 and not (
        body["trust_recall"]
        == body["legacy_trust_coverage"]
        == body["safe_trust_coverage"]
    ):
        raise ValueError("perfect precision requires equal recall and coverage")
    return M336FTrustMetrics(**body, metrics_hash=content_hash(body))


def verify_m336f_threshold_manifest(
    value: M336FJavaAcceptanceThresholds,
) -> None:
    body = asdict(value)
    claimed = body.pop("manifest_hash")
    if value != M336F_JAVA_ACCEPTANCE_THRESHOLDS or content_hash(body) != claimed:
        raise ValueError("M-33.6f acceptance threshold manifest mismatch")
