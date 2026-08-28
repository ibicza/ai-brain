"""Finite chemistry curriculum graph; this module has no execution authority."""

from __future__ import annotations

CONCEPTS = (
    "ELEMENT_IDENTITY",
    "ATOMIC_NUMBER",
    "CHEMICAL_SYMBOL",
    "ATOMIC_WEIGHT_SINGLE",
    "ATOMIC_WEIGHT_INTERVAL",
    "FORMULA_PARSING",
    "SUBSCRIPT_COUNTING",
    "GROUP_MULTIPLIER",
    "FORMULA_COMPOSITION",
    "MOLAR_MASS_SIMPLE",
    "MOLAR_MASS_GROUPED",
    "MASS_TO_MOLES",
    "MOLES_TO_MASS",
    "GRAM_KILOGRAM_CONVERSION",
    "MOL_MMOL_CONVERSION",
    "MOLES_TO_FORMULA_ENTITIES",
    "MOLES_TO_TOTAL_ATOMS",
    "TARGET_ELEMENT_ATOM_COUNT",
    "SIGNIFICANT_FIGURES",
    "UNIT_DIMENSION",
)

PREREQUISITES: dict[str, tuple[str, ...]] = {
    "FORMULA_COMPOSITION": ("FORMULA_PARSING", "SUBSCRIPT_COUNTING"),
    "MOLAR_MASS_SIMPLE": ("FORMULA_COMPOSITION", "ATOMIC_WEIGHT_SINGLE"),
    "MOLAR_MASS_GROUPED": ("MOLAR_MASS_SIMPLE", "GROUP_MULTIPLIER"),
    "MASS_TO_MOLES": ("MOLAR_MASS_SIMPLE", "UNIT_DIMENSION"),
    "MOLES_TO_MASS": ("MOLAR_MASS_SIMPLE", "UNIT_DIMENSION"),
    "MOLES_TO_FORMULA_ENTITIES": ("MASS_TO_MOLES",),
    "MOLES_TO_TOTAL_ATOMS": ("MOLES_TO_FORMULA_ENTITIES", "SUBSCRIPT_COUNTING"),
    "TARGET_ELEMENT_ATOM_COUNT": ("MOLES_TO_TOTAL_ATOMS",),
    "GRAM_KILOGRAM_CONVERSION": ("UNIT_DIMENSION",),
    "MOL_MMOL_CONVERSION": ("UNIT_DIMENSION",),
}


def verify_curriculum() -> None:
    known = set(CONCEPTS)
    if any(
        key not in known or not set(value) <= known
        for key, value in PREREQUISITES.items()
    ):
        raise ValueError("curriculum references an unknown concept")
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(concept: str) -> None:
        if concept in visiting:
            raise ValueError("curriculum prerequisite cycle")
        if concept in complete:
            return
        visiting.add(concept)
        for dependency in PREREQUISITES.get(concept, ()):
            visit(dependency)
        visiting.remove(concept)
        complete.add(concept)

    for concept in CONCEPTS:
        visit(concept)


verify_curriculum()
