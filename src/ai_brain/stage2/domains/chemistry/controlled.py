"""Finite Russian/English controlled language for the M-28 domain."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ai_brain.stage2.facts.memory import FactMemory


class ChemistryParseKind(StrEnum):
    FACT = "FACT"
    TOOL = "TOOL"
    CLARIFICATION = "CLARIFICATION"
    UNSUPPORTED = "UNSUPPORTED"
    COMPOSITE = "COMPOSITE"


@dataclass(frozen=True)
class ChemistryParse:
    kind: ChemistryParseKind
    payload: dict[str, Any]
    missing_fields: tuple[str, ...] = ()
    evidence: dict[str, Any] | None = None


_PREDICATES = {
    "en": {
        "symbol": "element_symbol",
        "english name": "element_name_en",
        "russian name": "element_name_ru",
        "atomic number": "atomic_number",
        "period": "period",
        "group": "group",
        "conventional atomic weight": "conventional_atomic_weight",
        "standard atomic weight": "standard_atomic_weight",
    },
    "ru": {
        "символ": "element_symbol",
        "название": "element_name_ru",
        "английское название": "element_name_en",
        "атомный номер": "atomic_number",
        "период": "period",
        "группа": "group",
        "условная атомная масса": "conventional_atomic_weight",
        "стандартная атомная масса": "standard_atomic_weight",
    },
}

_EN_FACT = re.compile(
    r"^What is the (?P<predicate>.+?) of (?P<entity>.+?)\?$", re.IGNORECASE
)
_RU_FACT = re.compile(
    r"^Как(?:ов|ой|ая) (?P<predicate>.+?) у (?P<entity>.+?)\?$", re.IGNORECASE
)
_EN_MOLAR = re.compile(
    r"^(?:Calculate|What is) the molar mass of (?P<formula>\S+?)[.?]?$", re.IGNORECASE
)
_RU_MOLAR = re.compile(
    r"^(?:Вычисли|Рассчитай|Какова) молярн(?:ую|ая) масс[уа] (?P<formula>\S+?)[.?]?$",
    re.IGNORECASE,
)
_EN_COMPOSITION = re.compile(
    r"^(?:Show|Calculate) the composition of (?P<formula>\S+?)[.?]?$", re.IGNORECASE
)
_RU_COMPOSITION = re.compile(
    r"^(?:Покажи|Вычисли) состав (?:формулы )?(?P<formula>\S+?)[.?]?$", re.IGNORECASE
)
_EN_MASS_TO_MOLES = re.compile(
    r"^How many (?P<target>mol|mmol) are in (?P<value>\d+(?:\.\d+)?) (?P<source>g|kg) of (?P<formula>\S+?)\?$",
    re.IGNORECASE,
)
_EN_MOLES_TO_MASS = re.compile(
    r"^What is the mass of (?P<value>\d+(?:\.\d+)?) (?P<source>mol|mmol) of (?P<formula>\S+?) in (?P<target>g|kg)\?$",
    re.IGNORECASE,
)
_RU_MASS_TO_MOLES = re.compile(
    r"^Сколько (?P<target>моль|ммоль) содержится в (?P<value>\d+(?:[.,]\d+)?) (?P<source>г|кг) (?P<formula>\S+?)\?$",
    re.IGNORECASE,
)
_RU_MOLES_TO_MASS = re.compile(
    r"^Какова масса (?P<value>\d+(?:[.,]\d+)?) (?P<source>моль|ммоль) (?P<formula>\S+?) в (?P<target>г|кг)\?$",
    re.IGNORECASE,
)
_EN_ENTITIES = re.compile(
    r"^How many (?P<entity>atoms|molecules|formula units) are in (?P<value>\d+(?:\.\d+)?) (?P<source>mol|mmol)(?: of \S+)?\?$",
    re.IGNORECASE,
)
_RU_ENTITIES = re.compile(
    r"^Сколько (?P<entity>атомов|молекул|формульных единиц) содержится в (?P<value>\d+(?:[.,]\d+)?) (?P<source>моль|ммоль)(?: \S+)?\?$",
    re.IGNORECASE,
)


def parse_chemistry(text: str, language: str, memory: FactMemory) -> ChemistryParse:
    stripped = text.strip()
    lower = stripped.casefold()
    if any(
        marker in lower
        for marker in (" and save", " and remember", "и сохрани", "и запомни")
    ):
        return ChemistryParse(
            ChemistryParseKind.COMPOSITE,
            {},
            evidence={"policy": "no_fact_write_from_calculation"},
        )
    fact_match = (_RU_FACT if language == "ru" else _EN_FACT).fullmatch(stripped)
    if fact_match:
        predicate = _PREDICATES[language].get(fact_match["predicate"].casefold())
        entity = fact_match["entity"].rstrip(".")
        resolution = memory.resolve_entity(entity, language)
        if predicate is None:
            return ChemistryParse(
                ChemistryParseKind.CLARIFICATION,
                {},
                ("predicate",),
                {"matched": "chemistry_fact"},
            )
        if len(resolution.entity_ids) != 1:
            return ChemistryParse(
                ChemistryParseKind.CLARIFICATION,
                {},
                ("element",),
                {"matched": "chemistry_fact"},
            )
        return ChemistryParse(
            ChemistryParseKind.FACT,
            {
                "subject": resolution.entity_ids[0],
                "predicate_id": predicate,
                "include_evidence": True,
                "language": language,
            },
            evidence={"matched": "chemistry_fact"},
        )
    for pattern, tool_id, defaults in _tool_patterns(language):
        match = pattern.fullmatch(stripped)
        if match:
            arguments = {
                **defaults,
                **{
                    key: value
                    for key, value in match.groupdict().items()
                    if value is not None
                },
            }
            arguments = _normalize_arguments(arguments, language, tool_id)
            return ChemistryParse(
                ChemistryParseKind.TOOL,
                {"tool_id": tool_id, "arguments": arguments},
                evidence={"matched": tool_id},
            )
    if _looks_incomplete(lower, language):
        return ChemistryParse(
            ChemistryParseKind.CLARIFICATION,
            {},
            ("formula_or_value_or_unit",),
            {"matched": "incomplete_chemistry"},
        )
    return ChemistryParse(
        ChemistryParseKind.UNSUPPORTED,
        {},
        evidence={"policy": "bounded_introductory_chemistry_v1"},
    )


def _tool_patterns(language: str):
    if language == "ru":
        return (
            (
                _RU_MOLAR,
                "chemistry_molar_mass",
                {"mode": "conventional", "unit": "g/mol"},
            ),
            (_RU_COMPOSITION, "chemistry_formula_composition", {}),
            (_RU_MASS_TO_MOLES, "chemistry_mass_amount", {}),
            (_RU_MOLES_TO_MASS, "chemistry_mass_amount", {}),
            (_RU_ENTITIES, "chemistry_entity_amount", {"target_unit": "entities"}),
        )
    return (
        (_EN_MOLAR, "chemistry_molar_mass", {"mode": "conventional", "unit": "g/mol"}),
        (_EN_COMPOSITION, "chemistry_formula_composition", {}),
        (_EN_MASS_TO_MOLES, "chemistry_mass_amount", {}),
        (_EN_MOLES_TO_MASS, "chemistry_mass_amount", {}),
        (_EN_ENTITIES, "chemistry_entity_amount", {"target_unit": "entities"}),
    )


def _normalize_arguments(
    arguments: dict[str, str], language: str, tool_id: str
) -> dict[str, str]:
    normalized = dict(arguments)
    if "value" in normalized:
        normalized["value"] = normalized["value"].replace(",", ".")
    unit_map = {"г": "g", "кг": "kg", "моль": "mol", "ммоль": "mmol"}
    for key in ("source", "target"):
        if key in normalized:
            normalized[f"{key}_unit"] = unit_map.get(
                normalized.pop(key).casefold(), normalized.get(key, "").casefold()
            )
    if tool_id == "chemistry_entity_amount":
        entities = {
            "atoms": "atoms",
            "molecules": "molecules",
            "formula units": "formula_units",
            "атомов": "atoms",
            "молекул": "molecules",
            "формульных единиц": "formula_units",
        }
        normalized["entity_type"] = entities[normalized.pop("entity").casefold()]
    return normalized


def _looks_incomplete(lower: str, language: str) -> bool:
    markers = (
        ("molar mass", "composition", "how many mol", "what is the mass")
        if language == "en"
        else ("молярн", "состав", "сколько моль", "какова масса")
    )
    return any(marker in lower for marker in markers)
