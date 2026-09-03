"""Count-first Java evaluation metrics; ratios cannot be supplied by callers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BinaryConfusionMatrix:
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    precision: str
    recall: str


@dataclass(frozen=True)
class SourceLocationConfusionMatrix:
    exact_true_positive: int
    wrong_location_false_positive: int
    missing_false_negative: int
    precision: str
    recall: str


@dataclass(frozen=True)
class AutomaticTrustConfusionMatrix:
    correct_trusted: int
    wrong_trusted: int
    correct_withheld: int
    incorrect_withheld: int
    precision: str
    recall: str
    coverage: str
    wrong_count: int


@dataclass(frozen=True)
class EvidenceConfusionMatrix:
    required: int
    present: int
    exact: int
    missing: int
    extra: int
    duplicate: int
    wrong: int
    completeness: str
    exactness: str


@dataclass(frozen=True)
class SetDetectionConfusionMatrix:
    seeded_expected_ids: tuple[str, ...]
    detected_ids: tuple[str, ...]
    missed_ids: tuple[str, ...]
    spurious_ids: tuple[str, ...]
    precision: str
    recall: str


@dataclass(frozen=True)
class SafeAbstentionMatrix:
    expected_unsupported_or_ambiguous: int
    correctly_withheld: int
    wrongly_trusted: int
    abstention_rate: str


def binary_confusion(expected_positive, actual_positive, universe):
    expected = set(expected_positive)
    actual = set(actual_positive)
    values = set(universe)
    if not expected <= values or not actual <= values:
        raise ValueError("confusion inputs exceed sealed universe")
    tp = len(expected & actual)
    fp = len(actual - expected)
    fn = len(expected - actual)
    tn = len(values - (expected | actual))
    return BinaryConfusionMatrix(
        tp,
        fp,
        fn,
        tn,
        _ratio(tp, tp + fp),
        _ratio(tp, tp + fn),
    )


def source_location_confusion(expected_locations, actual_locations):
    expected = set(expected_locations)
    actual = set(actual_locations)
    exact = len(expected & actual)
    wrong = len(actual - expected)
    missing = len(expected - actual)
    return SourceLocationConfusionMatrix(
        exact,
        wrong,
        missing,
        _ratio(exact, exact + wrong),
        _ratio(exact, exact + missing),
    )


def automatic_trust_confusion(expected_trusted, actual_trusted, universe):
    expected = set(expected_trusted)
    actual = set(actual_trusted)
    values = set(universe)
    if not expected <= values or not actual <= values:
        raise ValueError("trust inputs exceed sealed universe")
    correct_trusted = len(expected & actual)
    wrong_trusted = len(actual - expected)
    incorrect_withheld = len(expected - actual)
    correct_withheld = len(values - (expected | actual))
    return AutomaticTrustConfusionMatrix(
        correct_trusted,
        wrong_trusted,
        correct_withheld,
        incorrect_withheld,
        _ratio(correct_trusted, correct_trusted + wrong_trusted),
        _ratio(correct_trusted, correct_trusted + incorrect_withheld),
        _ratio(len(actual), len(expected)),
        wrong_trusted,
    )


def evidence_confusion(manifest):
    return EvidenceConfusionMatrix(
        manifest.required_field_count,
        manifest.evidence_count,
        manifest.exact_count,
        manifest.missing_count,
        manifest.extra_count,
        manifest.duplicate_count,
        manifest.wrong_count,
        _ratio(
            manifest.required_field_count - manifest.missing_count,
            manifest.required_field_count,
        ),
        _ratio(manifest.exact_count, manifest.evidence_count),
    )


def set_detection_confusion(expected_ids, detected_ids):
    expected = set(expected_ids)
    detected = set(detected_ids)
    missed = tuple(sorted(expected - detected))
    spurious = tuple(sorted(detected - expected))
    correct = len(expected & detected)
    return SetDetectionConfusionMatrix(
        tuple(sorted(expected)),
        tuple(sorted(detected)),
        missed,
        spurious,
        _ratio(correct, len(detected)),
        _ratio(correct, len(expected)),
    )


def conflict_instance_confusion(expected_conflicts, detected_conflicts):
    """Compare complete conflict instances, never only their kind labels."""

    expected_values = tuple(expected_conflicts)
    detected_values = tuple(detected_conflicts)
    expected = {item.conflict_hash: item for item in expected_values}
    detected = {item.conflict_hash: item for item in detected_values}
    if len(expected) != len(expected_values):
        raise ValueError("duplicate expected Java conflict instance ID")
    if len(detected) != len(detected_values):
        raise ValueError("duplicate detected Java conflict instance ID")
    # A matching ID must also carry the exact implicated proposals,
    # declarations, locations and kind. This explicitly guards fixtures that
    # accidentally reduce truth to a set of conflict-kind strings.
    exact_ids = {
        key for key in set(expected) & set(detected) if expected[key] == detected[key]
    }
    altered_ids = (set(expected) & set(detected)) - exact_ids
    expected_ids = (set(expected) - altered_ids) | {
        f"expected-altered:{key}" for key in altered_ids
    }
    detected_ids = (set(detected) - altered_ids) | {
        f"detected-altered:{key}" for key in altered_ids
    }
    return set_detection_confusion(expected_ids, detected_ids)


def safe_abstention(expected_withheld, actual_trusted):
    expected = set(expected_withheld)
    trusted = set(actual_trusted)
    wrong = len(expected & trusted)
    correct = len(expected) - wrong
    return SafeAbstentionMatrix(
        len(expected), correct, wrong, _ratio(correct, len(expected))
    )


def _ratio(numerator: int, denominator: int) -> str:
    return "N/A" if denominator == 0 else f"{numerator / denominator:.6f}"
