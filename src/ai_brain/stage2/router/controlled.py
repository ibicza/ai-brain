"""Finite RU/EN controlled parsers used by the trusted router."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ai_brain.stage2.facts.canonical import normalize_label
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import EntityResolutionStatus
from ai_brain.stage2.models import SearchStatus
from ai_brain.stage2.router.models import RouteTarget


@dataclass(frozen=True)
class ParseOutcome:
    target: RouteTarget
    complete: bool
    payload: dict[str, Any]
    evidence: dict[str, Any]
    missing_field: str | None = None
    ambiguity: str | None = None


_EN_FACT = (
    re.compile(r"^What is the (?P<predicate>.+?) of (?P<entity>.+?)\?$", re.IGNORECASE),
    re.compile(
        r"^What was the (?P<predicate>.+?) of (?P<entity>.+?) on (?P<valid>\d{4}-\d{2}-\d{2})\?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^What did the system know about (?P<entity>.+?)(?:'s|’s) (?P<predicate>.+?) at (?P<known>[^?]+)\?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^Show all (?P<predicate>.+?) values for (?P<entity>.+?)\.?$", re.IGNORECASE
    ),
)
_RU_FACT = (
    re.compile(
        r"^Каково значение (?P<predicate>.+?) у (?:города|объекта) (?P<entity>.+?)(?: на (?P<valid>\d{4}-\d{2}-\d{2}))?\?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^Что система знала о (?P<predicate>.+?) (?:города|объекта) (?P<entity>.+?) на (?P<known>[^?]+)\?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^Покажи все значения (?P<predicate>.+?) у объекта (?P<entity>.+?)\.?$",
        re.IGNORECASE,
    ),
)


def parse_fact(
    text: str, language: str, memory: FactMemory | None
) -> ParseOutcome | None:
    patterns = _RU_FACT if language == "ru" else _EN_FACT
    match = next(
        (
            pattern.fullmatch(text.strip())
            for pattern in patterns
            if pattern.fullmatch(text.strip())
        ),
        None,
    )
    if match is None:
        return None
    if memory is None:
        return ParseOutcome(
            RouteTarget.FACT_QUERY,
            False,
            {},
            {"parser": "controlled_fact", "matched": True},
            missing_field="fact_memory",
        )
    fields = match.groupdict()
    entity = fields["entity"].strip().rstrip(".")
    resolution = memory.resolve_entity(entity, language)
    if resolution.status == EntityResolutionStatus.AMBIGUOUS_ENTITY:
        return ParseOutcome(
            RouteTarget.FACT_QUERY,
            False,
            {},
            {"parser": "controlled_fact", "entity": entity},
            missing_field="entity_id",
            ambiguity="MULTIPLE_FACT_ENTITIES",
        )
    if resolution.status == EntityResolutionStatus.UNKNOWN_ENTITY:
        return ParseOutcome(
            RouteTarget.FACT_QUERY,
            False,
            {},
            {"parser": "controlled_fact", "entity": entity},
            missing_field="known_entity",
            ambiguity="UNSUPPORTED_OPERATION",
        )
    predicate = _resolve_predicate(memory, fields["predicate"], language)
    if predicate is None:
        return ParseOutcome(
            RouteTarget.FACT_QUERY,
            False,
            {},
            {"parser": "controlled_fact", "predicate": fields["predicate"]},
            missing_field="predicate_id",
            ambiguity="UNKNOWN_FACT_PREDICATE",
        )
    payload = {
        "subject": resolution.entity_ids[0],
        "predicate_id": predicate,
        "valid_at_value": fields.get("valid"),
        "known_at": fields.get("known"),
        "include_evidence": True,
        "language": language,
    }
    return ParseOutcome(
        RouteTarget.FACT_QUERY,
        True,
        payload,
        {
            "parser": "controlled_fact",
            "entity_id": resolution.entity_ids[0],
            "predicate_id": predicate,
        },
    )


def _resolve_predicate(memory: FactMemory, value: str, language: str) -> str | None:
    normalized = normalize_label(value)
    field = "canonical_name_ru" if language == "ru" else "canonical_name_en"
    with memory.database.connect() as connection:
        for row in connection.execute(
            "SELECT predicate_id, payload_json FROM predicate_definitions WHERE active = 1"
        ):
            import json

            payload = json.loads(row["payload_json"])
            if normalize_label(str(payload[field])) == normalized:
                return str(row["predicate_id"])
    return None


def parse_skill(text: str, language: str, skill_router) -> ParseOutcome | None:
    if skill_router is None:
        return None
    try:
        query, result = skill_router.search_controlled(text.strip(), language)
    except (ValueError, KeyError):
        return None
    if result.status == SearchStatus.EXACT_MATCH and len(result.candidates) == 1:
        return ParseOutcome(
            RouteTarget.SKILL_REQUEST,
            True,
            {
                "query": asdict(query),
                "result": asdict(result),
                "selected_skill_id": result.candidates[0].skill_id,
            },
            {
                "parser": "stage1_controlled_skill",
                "query_hash": result.query_hash,
                "candidate_list": tuple(item.skill_id for item in result.candidates),
            },
        )
    if result.status == SearchStatus.AMBIGUOUS:
        return ParseOutcome(
            RouteTarget.SKILL_REQUEST,
            False,
            {"query": asdict(query), "result": asdict(result)},
            {"parser": "stage1_controlled_skill"},
            missing_field="skill_binding",
            ambiguity="MISSING_SKILL_DESTINATION",
        )
    return None


_NUMBER = r"[-+]?\d+(?:\.\d+)?"
_EN_ARITHMETIC = re.compile(
    rf"^(?:Calculate|Compute) (?P<a>{_NUMBER}) (?P<op>plus|minus|multiplied by|divided by) (?P<b>{_NUMBER})\.?$",
    re.IGNORECASE,
)
_RU_ARITHMETIC = re.compile(
    rf"^(?:Вычисли|Посчитай) (?P<a>{_NUMBER}) (?P<op>плюс|минус|умножить на|разделить на) (?P<b>{_NUMBER})\.?$",
    re.IGNORECASE,
)
_EN_DATES = re.compile(
    r"^How many days are between (?P<start>\d{4}-\d{2}-\d{2}) and (?P<end>\d{4}-\d{2}-\d{2})\?$",
    re.IGNORECASE,
)
_RU_DATES = re.compile(
    r"^Сколько дней между (?P<start>\d{4}-\d{2}-\d{2}) и (?P<end>\d{4}-\d{2}-\d{2})\?$",
    re.IGNORECASE,
)


def parse_tool(text: str, language: str) -> ParseOutcome | None:
    stripped = text.strip()
    arithmetic = (_RU_ARITHMETIC if language == "ru" else _EN_ARITHMETIC).fullmatch(
        stripped
    )
    if arithmetic:
        operations = {
            "plus": "ADD",
            "плюс": "ADD",
            "minus": "SUBTRACT",
            "минус": "SUBTRACT",
            "multiplied by": "MULTIPLY",
            "умножить на": "MULTIPLY",
            "divided by": "DIVIDE",
            "разделить на": "DIVIDE",
        }
        args = {
            "operation": operations[arithmetic.group("op").lower()],
            "operands": [arithmetic.group("a"), arithmetic.group("b")],
        }
        return ParseOutcome(
            RouteTarget.TOOL_REQUEST,
            True,
            {"tool_id": "decimal_arithmetic", "arguments": args},
            {"parser": "controlled_tool", "pattern": "decimal_arithmetic"},
        )
    dates = (_RU_DATES if language == "ru" else _EN_DATES).fullmatch(stripped)
    if dates:
        return ParseOutcome(
            RouteTarget.TOOL_REQUEST,
            True,
            {
                "tool_id": "date_difference",
                "arguments": {
                    "start_date": dates.group("start"),
                    "end_date": dates.group("end"),
                    "mode": "ABSOLUTE",
                },
            },
            {"parser": "controlled_tool", "pattern": "date_difference"},
        )
    prefixes = ("Calculate", "Compute", "Вычисли", "Посчитай", "Сколько дней")
    if stripped.startswith(prefixes):
        return ParseOutcome(
            RouteTarget.TOOL_REQUEST,
            False,
            {},
            {"parser": "controlled_tool", "matched_prefix": True},
            missing_field="tool_argument",
            ambiguity="MISSING_TOOL_ARGUMENT",
        )
    return None


def looks_composite(text: str) -> bool:
    lowered = normalize_label(text)
    connectors = (
        " and then ",
        " and store ",
        " and save ",
        " и затем ",
        " и сохрани",
        " и запиши",
    )
    if not any(item.strip() in lowered for item in connectors):
        return False
    intent_markers = (
        "what is",
        "calculate",
        "move ",
        "store",
        "execute",
        "каково",
        "вычисли",
        "перемести",
        "сохрани",
        "выполни",
    )
    return sum(marker in lowered for marker in intent_markers) >= 2
