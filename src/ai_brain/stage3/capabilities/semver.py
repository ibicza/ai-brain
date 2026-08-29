from __future__ import annotations

import re

_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_COMPARATOR = re.compile(r"^(>=|<=|>|<|=)(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_semver(value: str) -> tuple[int, int, int]:
    match = _SEMVER.fullmatch(value)
    if not match:
        raise ValueError("version is not strict semver")
    return tuple(int(item) for item in match.groups())


def matches_version(version: str, expression: str) -> bool:
    selected = parse_semver(version)
    if expression == "*":
        return True
    if _SEMVER.fullmatch(expression):
        return selected == parse_semver(expression)
    if expression.endswith(".*") and expression.count(".") in {1, 2}:
        prefix = expression[:-2].split(".")
        if any(
            not item.isdigit() or (len(item) > 1 and item.startswith("0"))
            for item in prefix
        ):
            raise ValueError("invalid wildcard semver range")
        return selected[: len(prefix)] == tuple(int(item) for item in prefix)
    if expression.startswith("^"):
        base = parse_semver(expression[1:])
        upper = (
            (base[0] + 1, 0, 0)
            if base[0]
            else ((0, base[1] + 1, 0) if base[1] else (0, 0, base[2] + 1))
        )
        return base <= selected < upper
    if expression.startswith("~"):
        base = parse_semver(expression[1:])
        return base <= selected < (base[0], base[1] + 1, 0)
    parts = expression.split(",")
    if not parts or any(not part for part in parts):
        raise ValueError("invalid semver range")
    for part in parts:
        match = _COMPARATOR.fullmatch(part)
        if not match:
            raise ValueError("invalid semver comparator")
        other = tuple(int(item) for item in match.groups()[1:])
        operation = match.group(1)
        if not {
            ">=": selected >= other,
            "<=": selected <= other,
            ">": selected > other,
            "<": selected < other,
            "=": selected == other,
        }[operation]:
            return False
    return True
