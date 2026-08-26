"""Deterministic serialization and temporal helpers."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def canonicalize(value: Any) -> Any:
    if is_dataclass(value):
        return canonicalize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite Decimal is forbidden")
        return decimal_text(value)
    if isinstance(value, datetime):
        return normalize_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): canonicalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [canonicalize(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite float is forbidden")
        raise TypeError("float is forbidden in trusted factual artifacts")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize_datetime(value: str | datetime) -> str:
    parsed = value if isinstance(value, datetime) else _parse_datetime(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("DATETIME must include an offset")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def normalize_date(value: str | date) -> str:
    if isinstance(value, datetime):
        raise TypeError("DATE cannot be a datetime")
    parsed = value if isinstance(value, date) else date.fromisoformat(value)
    return parsed.isoformat()


def normalize_temporal(value: str | date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return normalize_datetime(value)
    if isinstance(value, date):
        return normalize_date(value)
    if "T" in value or value.endswith("Z"):
        return normalize_datetime(value)
    return normalize_date(value)


def temporal_key(value: str | None, *, upper: bool = False) -> str:
    if value is None:
        return "9999-12-31T23:59:59.999999Z" if upper else "0001-01-01T00:00:00Z"
    if "T" not in value:
        return f"{value}T00:00:00Z"
    return normalize_datetime(value)


def validate_interval(start: str | None, end: str | None) -> None:
    if (
        start is not None
        and end is not None
        and temporal_key(start) >= temporal_key(end)
    ):
        raise ValueError("valid interval must be half-open with start < end")


def intervals_overlap(
    left_start: str | None,
    left_end: str | None,
    right_start: str | None,
    right_end: str | None,
) -> bool:
    return temporal_key(left_start) < temporal_key(
        right_end, upper=True
    ) and temporal_key(right_start) < temporal_key(left_end, upper=True)


def valid_at(start: str | None, end: str | None, point: str) -> bool:
    key = temporal_key(point)
    return temporal_key(start) <= key < temporal_key(end, upper=True)


def normalize_label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _parse_datetime(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(text)
