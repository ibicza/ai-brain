"""Finite Russian/English controlled language for the M-28 domain."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ai_brain.stage2.domains.chemistry.resolver import resolve_chemistry_element
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
        "standard atomic weight": "atomic_weight_standard_notation",
    },
    "ru": {
        "символ": "element_symbol",
        "название": "element_name_ru",
        "английское название": "element_name_en",
        "атомный номер": "atomic_number",
        "период": "period",
        "группа": "group",
        "условная атомная масса": "conventional_atomic_weight",
        "стандартная атомная масса": "atomic_weight_standard_notation",
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
    r"^How many (?P<entity>total atoms|atoms|molecules|formula units|formula entities) are in (?P<value>\d+(?:\.\d+)?) (?P<source>mol|mmol) of (?P<formula>\S+)\?$",
    re.IGNORECASE,
)
_RU_ENTITIES = re.compile(
    r"^Сколько (?P<entity>всего атомов|атомов|молекул|формульных единиц) содержится в (?P<value>\d+(?:[.,]\d+)?) (?P<source>моль|ммоль) (?P<formula>\S+)\?$",
    re.IGNORECASE,
)
_EN_ELEMENT_ATOMS = re.compile(
    r"^How many (?P<target_element>[A-Za-z]+) atoms are in (?P<value>\d+(?:\.\d+)?) (?P<source>mol|mmol) of (?P<formula>\S+)\?$",
    re.IGNORECASE,
)
_RU_ELEMENT_ATOMS = re.compile(
    r"^Сколько атомов (?P<target_element>\S+) содержится в (?P<value>\d+(?:[.,]\d+)?) (?P<source>моль|ммоль) (?P<formula>\S+)\?$",
    re.IGNORECASE,
)
_EN_ENTITIES_TO_AMOUNT = re.compile(
    r"^How many (?P<target>mol|mmol) are (?P<value>\d+) (?P<entity>formula entities|total atoms) of (?P<formula>\S+)\?$",
    re.IGNORECASE,
)
_RU_ENTITIES_TO_AMOUNT = re.compile(
    r"^Сколько (?P<target>моль|ммоль) составляют (?P<value>\d+) (?P<entity>формульных единиц|атомов) (?P<formula>\S+)\?$",
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
            try:
                arguments = _normalize_arguments(arguments, language, tool_id, memory)
            except (KeyError, ValueError):
                return ChemistryParse(
                    ChemistryParseKind.CLARIFICATION,
                    {},
                    ("element",),
                    {"matched": tool_id},
                )
            return ChemistryParse(
                ChemistryParseKind.TOOL,
                {"tool_id": tool_id, "arguments": arguments},
                evidence={"matched": tool_id},
            )
    fact_match = (_RU_FACT if language == "ru" else _EN_FACT).fullmatch(stripped)
    if fact_match:
        predicate = _PREDICATES[language].get(fact_match["predicate"].casefold())
        entity = fact_match["entity"].rstrip(".")
        resolution = resolve_chemistry_element(memory, entity, language)
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
            (_RU_ELEMENT_ATOMS, "chemistry_entity_amount", {"target_unit": "entities"}),
            (
                _RU_ENTITIES_TO_AMOUNT,
                "chemistry_entity_amount",
                {"source_unit": "entities"},
            ),
        )
    return (
        (_EN_MOLAR, "chemistry_molar_mass", {"mode": "conventional", "unit": "g/mol"}),
        (_EN_COMPOSITION, "chemistry_formula_composition", {}),
        (_EN_MASS_TO_MOLES, "chemistry_mass_amount", {}),
        (_EN_MOLES_TO_MASS, "chemistry_mass_amount", {}),
        (_EN_ENTITIES, "chemistry_entity_amount", {"target_unit": "entities"}),
        (_EN_ELEMENT_ATOMS, "chemistry_entity_amount", {"target_unit": "entities"}),
        (
            _EN_ENTITIES_TO_AMOUNT,
            "chemistry_entity_amount",
            {"source_unit": "entities"},
        ),
    )


def _normalize_arguments(
    arguments: dict[str, str],
    language: str,
    tool_id: str,
    memory: FactMemory,
) -> dict[str, Any]:
    normalized = dict(arguments)
    if "value" in normalized:
        normalized["value"] = normalized["value"].replace(",", ".")
    unit_map = {"г": "g", "кг": "kg", "моль": "mol", "ммоль": "mmol"}
    for key in ("source", "target"):
        if key in normalized:
            raw_unit = normalized.pop(key).casefold()
            normalized[f"{key}_unit"] = unit_map.get(raw_unit, raw_unit)
    if tool_id == "chemistry_entity_amount":
        bases = {
            "atoms": "TOTAL_ATOMS_IN_FORMULA",
            "total atoms": "TOTAL_ATOMS_IN_FORMULA",
            "всего атомов": "TOTAL_ATOMS_IN_FORMULA",
            "атомов": "TOTAL_ATOMS_IN_FORMULA",
            "molecules": "FORMULA_ENTITIES",
            "formula units": "FORMULA_ENTITIES",
            "formula entities": "FORMULA_ENTITIES",
            "молекул": "FORMULA_ENTITIES",
            "формульных единиц": "FORMULA_ENTITIES",
        }
        entity = normalized.pop("entity", None)
        if "target_element" in normalized:
            resolution = resolve_chemistry_element(
                memory, normalized["target_element"], language
            )
            if len(resolution.entity_ids) != 1:
                raise ValueError("unknown target element")
            record = memory.get_entity(resolution.entity_ids[0])
            normalized["target_element"] = record.external_identifiers["symbol"]
            normalized["basis"] = "ATOMS_OF_ELEMENT_IN_FORMULA"
            normalized["requested_display_label"] = "atoms"
        else:
            assert entity is not None
            normalized["basis"] = bases[entity.casefold()]
            normalized["requested_display_label"] = entity.casefold()
            normalized["target_element"] = None
        normalized["significant_digits"] = 6
    elif tool_id in {"chemistry_molar_mass", "chemistry_mass_amount"}:
        normalized["significant_digits"] = 6
    return normalized


def _looks_incomplete(lower: str, language: str) -> bool:
    markers = (
        (
            "molar mass",
            "composition",
            "how many mol",
            "what is the mass",
            "how many total atoms",
            "how many atoms",
            "how many molecules",
            "how many formula units",
            "how many formula entities",
        )
        if language == "en"
        else (
            "молярн",
            "состав",
            "сколько моль",
            "какова масса",
            "сколько всего атомов",
            "сколько атомов",
            "сколько молекул",
            "сколько формульных единиц",
        )
    )
    return any(marker in lower for marker in markers)
