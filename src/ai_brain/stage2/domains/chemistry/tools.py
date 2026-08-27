"""Knowledge-bound entry functions for trusted chemistry tools."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.stage2.domains.chemistry.calculations import (
    entity_amount,
    formula_composition,
    mass_amount,
    molar_mass,
)
from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser
from ai_brain.stage2.domains.chemistry.models import (
    ChemistryKnowledgeSnapshot,
    ChemistryRoundingSpec,
)


def chemistry_formula_composition(
    arguments: dict[str, Any],
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
) -> dict[str, Any]:
    return asdict(formula_composition(parser, snapshot, arguments["formula"]))


def chemistry_molar_mass(
    arguments: dict[str, Any],
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
) -> dict[str, Any]:
    return asdict(
        molar_mass(
            parser,
            snapshot,
            arguments["formula"],
            mode=arguments["mode"],
            unit=arguments["unit"],
            rounding=ChemistryRoundingSpec(
                significant_digits=arguments["significant_digits"]
            ),
        )
    )


def chemistry_mass_amount(
    arguments: dict[str, Any],
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
) -> dict[str, Any]:
    return asdict(
        mass_amount(
            parser,
            snapshot,
            arguments["formula"],
            arguments["value"],
            arguments["source_unit"],
            arguments["target_unit"],
            rounding=ChemistryRoundingSpec(
                significant_digits=arguments["significant_digits"]
            ),
        )
    )


def chemistry_entity_amount(
    arguments: dict[str, Any],
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
) -> dict[str, Any]:
    return asdict(
        entity_amount(
            parser,
            snapshot,
            arguments["value"],
            arguments["source_unit"],
            arguments["target_unit"],
            arguments["basis"],
            formula=arguments["formula"],
            target_element=arguments["target_element"],
            requested_display_label=arguments["requested_display_label"],
            rounding=ChemistryRoundingSpec(
                significant_digits=arguments["significant_digits"]
            ),
        )
    )
