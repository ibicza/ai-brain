"""Build reviewed-style student-error fixtures without production counterfactuals."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.catalog import EducationalCatalogV2
from ai_brain.stage2.education.models import ExerciseFamily, MisconceptionCode
from ai_brain.stage2.facts.canonical import canonical_json, content_hash

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = (
    MisconceptionCode.SUBSCRIPT_IGNORED,
    MisconceptionCode.GROUP_MULTIPLIER_IGNORED,
    MisconceptionCode.ELEMENT_COUNT_WRONG,
    MisconceptionCode.ATOMIC_WEIGHT_WRONG,
    MisconceptionCode.MOLAR_MASS_TERM_WRONG,
    MisconceptionCode.MOLAR_MASS_SUM_WRONG,
    MisconceptionCode.MULTIPLY_INSTEAD_OF_DIVIDE,
    MisconceptionCode.GRAM_KILOGRAM_CONVERSION_ERROR,
    MisconceptionCode.MOL_MMOL_CONVERSION_ERROR,
    MisconceptionCode.AVOGADRO_FACTOR_MISSING,
    MisconceptionCode.AVOGADRO_FACTOR_EXTRA,
    MisconceptionCode.FORMULA_ENTITY_ATOM_MULTIPLIER_MISSING,
    MisconceptionCode.TARGET_ELEMENT_MULTIPLIER_WRONG,
    MisconceptionCode.UNIT_MISSING,
    MisconceptionCode.UNIT_WRONG_DIMENSION,
    MisconceptionCode.ROUNDING_OUTSIDE_POLICY,
    MisconceptionCode.INTERVAL_COLLAPSED_TO_MIDPOINT,
    MisconceptionCode.AMBIGUOUS_DIAGNOSIS,
    MisconceptionCode.ARITHMETIC_ERROR,
    MisconceptionCode.UNCLASSIFIED_ERROR,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chemistry-root",
        type=Path,
        default=ROOT / "artifacts" / "domains" / "chemistry" / "m29",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "artifacts" / "education" / "m291" / "catalog_v2.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "m291_independent_student_errors.jsonl",
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="m291-fixtures-") as directory:
        chemistry_copy = Path(directory) / "chemistry"
        shutil.copytree(args.chemistry_root.resolve(), chemistry_copy)
        chemistry = ChemistryDomainService.open(chemistry_copy)
        catalog = EducationalCatalogV2.load(args.catalog, chemistry)
        fixtures = _fixtures(catalog)
    target = args.output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("".join(canonical_json(item) + "\n" for item in fixtures))
    print(canonical_json({"fixture_count": len(fixtures), "path": str(target)}))


def _fixtures(catalog):
    fixtures = []
    for category_index, category in enumerate(CATEGORIES):
        pool = _pool(catalog.entries, category)
        for offset in range(60):
            entry = pool[offset % len(pool)]
            answer = _independent_error(
                entry.internal_instance.hidden_expected_answer, category
            )
            supported = (
                ()
                if category == MisconceptionCode.UNCLASSIFIED_ERROR
                else (
                    (
                        MisconceptionCode.MULTIPLY_INSTEAD_OF_DIVIDE.value,
                        MisconceptionCode.GRAM_KILOGRAM_CONVERSION_ERROR.value,
                    )
                    if category == MisconceptionCode.AMBIGUOUS_DIAGNOSIS
                    else (category.value,)
                )
            )
            body = {
                "fixture_id": f"m291-independent-{category_index:02d}-{offset:03d}",
                "public_exercise": {
                    "exercise_id": entry.internal_instance.instance_id,
                    "language": "en",
                    "question_text": entry.internal_instance.question_text,
                    "structured_public_givens": entry.internal_instance.structured_givens,
                    "difficulty_metadata": entry.internal_instance.difficulty_metadata,
                },
                "internal_fixture_binding": entry.semantic_key.semantic_key_hash,
                "submitted_answer": answer,
                "expected_grading_status": _expected_status(
                    entry.internal_instance.hidden_expected_answer,
                    answer,
                    category,
                ),
                "supported_diagnosis_set": supported,
                "forbidden_diagnosis_set": tuple(
                    item.value for item in CATEGORIES if item.value not in supported
                ),
                "ambiguity_status": "AMBIGUOUS"
                if category == MisconceptionCode.AMBIGUOUS_DIAGNOSIS
                else "UNAMBIGUOUS",
                "human_readable_rationale": (
                    "Independently constructed concrete error pattern for "
                    + category.value
                ),
                "fixture_reviewer": "m291-independent-fixture-review",
            }
            fixtures.append({**body, "fixture_hash": content_hash(body)})
    return fixtures


def _pool(entries, category):
    family = (
        ExerciseFamily.FORMULA_COMPOSITION
        if category
        in {
            MisconceptionCode.SUBSCRIPT_IGNORED,
            MisconceptionCode.GROUP_MULTIPLIER_IGNORED,
            MisconceptionCode.ELEMENT_COUNT_WRONG,
        }
        else ExerciseFamily.FACT_RETRIEVAL
        if category == MisconceptionCode.INTERVAL_COLLAPSED_TO_MIDPOINT
        else ExerciseFamily.AMOUNT_ENTITIES
        if category
        in {
            MisconceptionCode.AVOGADRO_FACTOR_MISSING,
            MisconceptionCode.AVOGADRO_FACTOR_EXTRA,
            MisconceptionCode.FORMULA_ENTITY_ATOM_MULTIPLIER_MISSING,
            MisconceptionCode.TARGET_ELEMENT_MULTIPLIER_WRONG,
        }
        else ExerciseFamily.MASS_AMOUNT
    )
    result = tuple(
        entry
        for entry in entries
        if entry.exercise_spec.family == family
        and (
            category != MisconceptionCode.INTERVAL_COLLAPSED_TO_MIDPOINT
            or {"lower", "upper"}
            <= entry.internal_instance.hidden_expected_answer.keys()
        )
        and (
            category != MisconceptionCode.SUBSCRIPT_IGNORED
            or any(
                value > 1
                for value in entry.internal_instance.hidden_expected_answer.get(
                    "element_counts", {}
                ).values()
            )
        )
        and (
            category != MisconceptionCode.GROUP_MULTIPLIER_IGNORED
            or "(" in entry.internal_instance.structured_givens.get("formula", "")
        )
    )
    if not result:
        raise ValueError(f"no independent fixture pool for {category.value}")
    return result


def _independent_error(expected, category):
    if "element_counts" in expected:
        counts = dict(expected["element_counts"])
        if category == MisconceptionCode.SUBSCRIPT_IGNORED:
            counts = {key: 1 for key in counts}
        elif category == MisconceptionCode.GROUP_MULTIPLIER_IGNORED:
            key = max(counts, key=counts.get)
            counts[key] = max(1, counts[key] - 1)
        else:
            key = max(counts)
            counts[key] += 1
        return {"interpreted_answer": {"element_counts": counts}, "issues": ()}
    if {"lower", "upper"} <= expected.keys():
        midpoint = (Decimal(expected["lower"]) + Decimal(expected["upper"])) / 2
        return {
            "interpreted_answer": {"lower": str(midpoint), "upper": str(midpoint)},
            "issues": (),
        }
    value = Decimal(expected.get("value", "1"))
    unit = expected.get("unit", "g")
    factors = {
        MisconceptionCode.ATOMIC_WEIGHT_WRONG: Decimal("1.01"),
        MisconceptionCode.MOLAR_MASS_TERM_WRONG: Decimal("0.9"),
        MisconceptionCode.MOLAR_MASS_SUM_WRONG: Decimal("1.1"),
        MisconceptionCode.MULTIPLY_INSTEAD_OF_DIVIDE: value or Decimal(2),
        MisconceptionCode.GRAM_KILOGRAM_CONVERSION_ERROR: Decimal(1000),
        MisconceptionCode.MOL_MMOL_CONVERSION_ERROR: Decimal("0.001"),
        MisconceptionCode.AVOGADRO_FACTOR_MISSING: Decimal("1e-23"),
        MisconceptionCode.AVOGADRO_FACTOR_EXTRA: Decimal("1e23"),
        MisconceptionCode.FORMULA_ENTITY_ATOM_MULTIPLIER_MISSING: Decimal("0.5"),
        MisconceptionCode.TARGET_ELEMENT_MULTIPLIER_WRONG: Decimal(2),
        MisconceptionCode.ROUNDING_OUTSIDE_POLICY: Decimal(2),
        MisconceptionCode.ARITHMETIC_ERROR: Decimal("1.2345"),
        MisconceptionCode.UNCLASSIFIED_ERROR: Decimal("7.777"),
        MisconceptionCode.AMBIGUOUS_DIAGNOSIS: Decimal(1000),
    }
    if category == MisconceptionCode.UNIT_MISSING:
        return {"interpreted_answer": None, "issues": ("unit is required",)}
    if category == MisconceptionCode.UNIT_WRONG_DIMENSION:
        return {
            "interpreted_answer": {"value": str(value), "unit": "entities"},
            "issues": (),
        }
    factor = factors.get(category, Decimal("1.5"))
    wrong = (
        Decimal(1) / value
        if category == MisconceptionCode.MULTIPLY_INSTEAD_OF_DIVIDE and value
        else value * factor
    )
    return {
        "interpreted_answer": {"value": str(wrong), "unit": unit},
        "issues": (),
    }


def _expected_status(expected, answer, category) -> str:
    if category == MisconceptionCode.UNIT_MISSING:
        return "INVALID_ANSWER"
    if "element_counts" in expected:
        actual = answer["interpreted_answer"]["element_counts"]
        matched = any(
            expected["element_counts"].get(key) == actual.get(key)
            for key in set(expected["element_counts"]) | set(actual)
        )
        return "PARTIALLY_CORRECT" if matched else "INCORRECT"
    return "INCORRECT"


if __name__ == "__main__":
    main()
