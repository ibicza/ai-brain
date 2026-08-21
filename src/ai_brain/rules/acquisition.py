"""Acquisition-side helpers and source-integrity audits."""

from __future__ import annotations

from pathlib import Path


def forbidden_constructor_names() -> tuple[str, ...]:
    # Split strings so acquisition/generator modules do not contain full target
    # constructor names that the source audit is meant to catch.
    return (
        "merge_" + "two_" + "program",
        "merge_" + "three_" + "program",
        "conditional_" + "drop_" + "move_" + "program",
    )


def source_contains_forbidden_constructors(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [name for name in forbidden_constructor_names() if name in text]


def assert_no_forbidden_constructors(paths: list[Path]) -> None:
    offenders = {
        str(path): source_contains_forbidden_constructors(path)
        for path in paths
        if source_contains_forbidden_constructors(path)
    }
    if offenders:
        raise AssertionError(
            f"Forbidden constructors in acquisition source: {offenders}"
        )
