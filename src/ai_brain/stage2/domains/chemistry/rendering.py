"""Deterministic educational rendering of chemistry result bundles."""

from __future__ import annotations

from typing import Any


def render_tool_output(output: dict[str, Any], language: str = "en") -> str:
    if language not in {"ru", "en"}:
        raise ValueError("language must be ru or en")
    operation = output["operation"]
    result = output["result"]
    lines = []
    if output.get("formula"):
        lines.append(
            ("Формула" if language == "ru" else "Formula") + f": {output['formula']}"
        )
    if operation == "formula_composition":
        heading = "Состав" if language == "ru" else "Composition"
        lines.append(f"{heading}:")
        for symbol, count in result["element_counts"].items():
            lines.append(f"- {symbol}: {count}")
    elif "value" in result:
        label = "Результат" if language == "ru" else "Result"
        lines.append(
            f"{label}: {result.get('rendered_value', result['value'])} {result['unit']}"
        )
    else:
        label = "Интервал" if language == "ru" else "Interval"
        lines.append(
            f"{label}: [{result.get('rendered_lower', result['lower'])}, "
            f"{result.get('rendered_upper', result['upper'])}] {result['unit']}"
        )
    policy_label = (
        "Политика атомных масс" if language == "ru" else "Atomic-weight policy"
    )
    lines.append(f"{policy_label}: {output['atomic_weight_policy']}")
    source_label = "Источники" if language == "ru" else "Sources"
    lines.append(f"{source_label}: {', '.join(output['source_hashes'])}")
    for warning in output.get("warnings", ()):
        lines.append(
            ("Предупреждение" if language == "ru" else "Warning") + f": {warning}"
        )
    return "\n".join(lines)
