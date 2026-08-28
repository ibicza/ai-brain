"""Typed answer-equivalence leakage checks for pre-solution hints."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from ai_brain.stage2.education.answers import numeric_equivalent
from ai_brain.stage2.education.models import EducationalGraphNode
from ai_brain.stage2.facts.canonical import canonical_json

NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:[.,]\d+)?(?:[Ee][-+]?\d+)?")
QUANTITY = re.compile(
    r"(?P<value>[-+]?\d+(?:[.,]\d+)?(?:[Ee][-+]?\d+)?)\s*"
    r"(?P<unit>kg/mol|g/mol|mmol|mol|kg|g|entities|u)"
)


def verify_hint_no_answer_leakage(text: str, root: EducationalGraphNode) -> None:
    normalized = _normalize_numeric_unicode(text)
    if isinstance(root.exact_output, dict):
        _verify_structured(normalized, root.exact_output)
        return
    try:
        exact = Decimal(str(root.exact_output))
    except (InvalidOperation, ValueError):
        if str(root.exact_output) in normalized:
            raise ValueError("early hint leaks the final structured answer")
        return
    forbidden = {exact}
    if root.display_output:
        try:
            forbidden.add(Decimal(root.display_output))
        except InvalidOperation:
            pass
    for match in NUMBER.finditer(normalized):
        try:
            if Decimal(match.group().replace(",", ".")) in forbidden:
                raise ValueError("early hint leaks an equivalent final number")
        except InvalidOperation:
            continue
    if root.unit:
        for match in QUANTITY.finditer(normalized):
            try:
                equivalent = numeric_equivalent(
                    match.group("value").replace(",", "."),
                    match.group("unit"),
                    str(root.exact_output),
                    root.unit,
                )[0]
            except (TypeError, ValueError):
                continue
            if equivalent:
                raise ValueError("early hint leaks an equivalent-unit answer")


def _verify_structured(text: str, expected: dict) -> None:
    if set(expected) == {"lower", "upper"}:
        values = {
            Decimal(str(expected["lower"])),
            Decimal(str(expected["upper"])),
        }
        found = set()
        for token in NUMBER.findall(text):
            try:
                value = Decimal(token.replace(",", "."))
            except InvalidOperation:
                continue
            if value in values:
                found.add(value)
        if found == values:
            raise ValueError("early hint leaks the final interval endpoint pair")
        midpoint = sum(values, Decimal(0)) / Decimal(2)
        if midpoint in found:
            raise ValueError("early hint leaks a trivial final interval expression")
        return
    canonical = canonical_json(expected)
    compact = re.sub(r"\s+", "", text)
    if canonical in compact:
        raise ValueError("early hint leaks the final composition")
    pairs = tuple(f"{key}:{value}" for key, value in sorted(expected.items()))
    if pairs and all(pair in compact for pair in pairs):
        raise ValueError("early hint leaks a reordered final composition")


def _normalize_numeric_unicode(text: str) -> str:
    translated = []
    for character in unicodedata.normalize("NFKC", text):
        if character in {"−", "–", "—"}:
            translated.append("-")
            continue
        try:
            translated.append(str(unicodedata.digit(character)))
        except (TypeError, ValueError):
            translated.append(character)
    return "".join(translated)
