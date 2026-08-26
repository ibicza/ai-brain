"""Immutable typed values used by factual claims."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from ai_brain.stage2.facts.canonical import (
    decimal_text,
    normalize_date,
    normalize_datetime,
)

_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_UNIT = re.compile(r"[A-Za-zµ°%][A-Za-z0-9µ°%*/.^_-]{0,63}\Z")


class FactValueKind(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    ENTITY_REF = "ENTITY_REF"
    QUANTITY = "QUANTITY"
    ENUM = "ENUM"


@dataclass(frozen=True)
class FactValue:
    kind: FactValueKind
    value: str | bool
    unit: str | None = None
    original_unit: str | None = None

    def __post_init__(self) -> None:
        try:
            kind = FactValueKind(self.kind)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Unknown FactValue kind: {self.kind!r}") from error
        object.__setattr__(self, "kind", kind)
        value, unit, original = _normalize(
            kind, self.value, self.unit, self.original_unit
        )
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "original_unit", original)

    @classmethod
    def create(
        cls,
        kind: FactValueKind | str,
        value: Any,
        *,
        unit: str | None = None,
        original_unit: str | None = None,
    ) -> FactValue:
        return cls(FactValueKind(kind), value, unit, original_unit)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> FactValue:
        if not isinstance(row, dict) or "kind" not in row or "value" not in row:
            raise ValueError("FactValue requires kind and value")
        return cls.create(
            row["kind"],
            row["value"],
            unit=row.get("unit"),
            original_unit=row.get("original_unit"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "value": self.value,
            "unit": self.unit,
            "original_unit": self.original_unit,
        }


def _normalize(
    kind: FactValueKind,
    value: Any,
    unit: str | None,
    original_unit: str | None,
) -> tuple[str | bool, str | None, str | None]:
    if kind == FactValueKind.STRING:
        if not isinstance(value, str):
            raise TypeError("STRING value must be text")
        return value, _forbid_unit(unit), _forbid_unit(original_unit)
    if kind == FactValueKind.INTEGER:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise TypeError("INTEGER value must be int or canonical integer text")
        text = str(value)
        if not re.fullmatch(r"-?(0|[1-9][0-9]*)", text):
            raise ValueError("Malformed INTEGER")
        return str(int(text)), _forbid_unit(unit), _forbid_unit(original_unit)
    if kind in {FactValueKind.DECIMAL, FactValueKind.QUANTITY}:
        if isinstance(value, (bool, float)):
            raise TypeError("DECIMAL values must not use bool or float")
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError("Malformed decimal") from error
        if not parsed.is_finite():
            raise ValueError("NaN and infinity are forbidden")
        if kind == FactValueKind.QUANTITY:
            if not isinstance(unit, str) or not _UNIT.fullmatch(unit):
                raise ValueError("QUANTITY requires a canonical unit")
            if original_unit is not None and not isinstance(original_unit, str):
                raise TypeError("original_unit must be text")
            return decimal_text(parsed), unit, original_unit
        return decimal_text(parsed), _forbid_unit(unit), _forbid_unit(original_unit)
    if kind == FactValueKind.BOOLEAN:
        if not isinstance(value, bool):
            raise TypeError("BOOLEAN value must be bool")
        return value, _forbid_unit(unit), _forbid_unit(original_unit)
    if kind == FactValueKind.DATE:
        if not isinstance(value, (str, date)) or isinstance(value, datetime):
            raise TypeError("DATE value must be ISO date")
        return normalize_date(value), _forbid_unit(unit), _forbid_unit(original_unit)
    if kind == FactValueKind.DATETIME:
        if not isinstance(value, (str, datetime)):
            raise TypeError("DATETIME value must be ISO datetime")
        return (
            normalize_datetime(value),
            _forbid_unit(unit),
            _forbid_unit(original_unit),
        )
    if kind in {FactValueKind.ENTITY_REF, FactValueKind.ENUM}:
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise ValueError(f"Malformed {kind.value} value")
        return value, _forbid_unit(unit), _forbid_unit(original_unit)
    raise ValueError(f"Unsupported FactValue kind: {kind}")


def _forbid_unit(value: str | None) -> None:
    if value is not None:
        raise ValueError("Units are only valid for QUANTITY")
