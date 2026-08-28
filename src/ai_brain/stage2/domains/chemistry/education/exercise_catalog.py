"""Bounded chemistry formulas and structural exercise templates."""

from __future__ import annotations

from ai_brain.stage2.education.exercises import make_exercise_spec
from ai_brain.stage2.education.models import ExerciseFamily, StudentAnswerKind

SIMPLE_FORMULAS = (
    "H2O",
    "CO2",
    "NH3",
    "CH4",
    "NaCl",
    "H2S",
    "SO2",
    "NO2",
    "FeO",
    "AgCl",
    "MgO",
    "CaO",
)

GROUPED_FORMULAS = (
    "Ca(OH)2",
    "Mg(OH)2",
    "Al(OH)3",
    "Fe(OH)2",
    "Fe(OH)3",
    "Ca(NO3)2",
    "Mg(NO3)2",
    "Al2(SO4)3",
    "Ca3(PO4)2",
    "(NH4)2SO4",
    "(NH4)3PO4",
    "K2SO4",
)

ALL_EXERCISE_FORMULAS = SIMPLE_FORMULAS + GROUPED_FORMULAS

INTERVAL_ELEMENTS = ("H", "C", "N", "O", "Mg", "Si", "S", "Cl", "Br")

FACT_PREDICATES = (
    "element_symbol",
    "atomic_number",
    "element_name_en",
    "element_name_ru",
    "conventional_atomic_weight",
    "standard_atomic_weight",
)

SPLIT_BUCKETS = {
    "development": SIMPLE_FORMULAS[:8] + GROUPED_FORMULAS[:6],
    "final": SIMPLE_FORMULAS[8:] + GROUPED_FORMULAS[6:],
}


def chemistry_exercise_specs(domain_version: str):
    """Return the frozen bounded M-29 chemistry exercise catalog."""
    return (
        make_exercise_spec(
            "chemistry.fact.text.v1",
            ExerciseFamily.FACT_RETRIEVAL,
            domain_version,
            0,
            learning_objectives=("retrieve verified element identity",),
            required_concepts=("element identity",),
            parameter_constraints={
                "predicates": (
                    "element_symbol",
                    "element_name_en",
                    "element_name_ru",
                )
            },
            accepted_answer_type=StudentAnswerKind.FREE_TEXT_ASSISTIVE,
        ),
        make_exercise_spec(
            "chemistry.fact.number.v1",
            ExerciseFamily.FACT_RETRIEVAL,
            domain_version,
            0,
            learning_objectives=("retrieve verified atomic number",),
            required_concepts=("atomic number",),
            parameter_constraints={"predicates": ("atomic_number",)},
            accepted_answer_type=StudentAnswerKind.FREE_TEXT_ASSISTIVE,
        ),
        make_exercise_spec(
            "chemistry.fact.weight.v1",
            ExerciseFamily.FACT_RETRIEVAL,
            domain_version,
            0,
            learning_objectives=("read an atomic-weight record",),
            required_concepts=("atomic weight policy",),
            parameter_constraints={"predicates": ("conventional_atomic_weight",)},
            accepted_answer_type=StudentAnswerKind.NUMERIC_WITH_UNIT,
            allowed_units=("u",),
        ),
        make_exercise_spec(
            "chemistry.fact.interval.v1",
            ExerciseFamily.FACT_RETRIEVAL,
            domain_version,
            0,
            learning_objectives=("read a standard atomic-weight interval",),
            required_concepts=("natural variability interval",),
            parameter_constraints={"predicates": ("standard_atomic_weight",)},
            accepted_answer_type=StudentAnswerKind.ATOMIC_WEIGHT_INTERVAL,
        ),
        make_exercise_spec(
            "chemistry.formula.v1",
            ExerciseFamily.FORMULA_COMPOSITION,
            domain_version,
            1,
            learning_objectives=("parse element counts",),
            required_concepts=("subscripts", "group multipliers"),
            parameter_constraints={"formula_set": "bounded_m29"},
            accepted_answer_type=StudentAnswerKind.ELEMENT_COUNT_MAP,
        ),
        make_exercise_spec(
            "chemistry.molar.simple.v1",
            ExerciseFamily.MOLAR_MASS_SIMPLE,
            domain_version,
            2,
            learning_objectives=("calculate molar mass",),
            required_concepts=("atomic weights", "stoichiometric sum"),
            parameter_constraints={"parentheses": False},
            accepted_answer_type=StudentAnswerKind.NUMERIC_WITH_UNIT,
            allowed_units=("g/mol", "kg/mol"),
        ),
        make_exercise_spec(
            "chemistry.molar.grouped.v1",
            ExerciseFamily.MOLAR_MASS_GROUPED,
            domain_version,
            3,
            learning_objectives=("calculate grouped-formula molar mass",),
            required_concepts=("group multipliers", "stoichiometric sum"),
            parameter_constraints={"parentheses": True},
            accepted_answer_type=StudentAnswerKind.NUMERIC_WITH_UNIT,
            allowed_units=("g/mol", "kg/mol"),
        ),
        make_exercise_spec(
            "chemistry.mass.amount.v1",
            ExerciseFamily.MASS_AMOUNT,
            domain_version,
            4,
            learning_objectives=("convert mass and amount",),
            required_concepts=("molar mass", "unit conversion"),
            parameter_constraints={"directions": ("mass_to_amount", "amount_to_mass")},
            accepted_answer_type=StudentAnswerKind.NUMERIC_WITH_UNIT,
            allowed_units=("g", "kg", "mol", "mmol"),
        ),
        make_exercise_spec(
            "chemistry.amount.entities.v1",
            ExerciseFamily.AMOUNT_ENTITIES,
            domain_version,
            5,
            learning_objectives=("convert amount and entity count",),
            required_concepts=("Avogadro constant", "formula multiplier"),
            parameter_constraints={
                "bases": ("FORMULA_ENTITIES", "TOTAL_ATOMS_IN_FORMULA")
            },
            accepted_answer_type=StudentAnswerKind.NUMERIC_WITH_UNIT,
            allowed_units=("mol", "mmol", "entities"),
        ),
    )
