"""Deterministic RU/EN rendering without factual selection authority."""

from __future__ import annotations

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage2.facts.models import FactAnswerBundle


def render_answer(bundle: FactAnswerBundle, *, language: str = "en") -> str:
    if language not in {"ru", "en"}:
        raise ValueError("renderer language must be ru or en")
    labels = _RU if language == "ru" else _EN
    lines = [f"{labels['status']}: {bundle.answer_status}"]
    for claim in bundle.claims:
        value = _render_value(claim.value.value, claim.value.unit)
        lines.extend(
            (
                f"{labels['claim']}: {claim.claim_id}",
                f"{labels['value']}: {value}",
                f"{labels['valid']}: [{claim.valid_from or '-inf'}, {claim.valid_to or '+inf'})",
                f"{labels['recorded']}: [{claim.recorded_at}, {claim.transaction_to or '+inf'})",
                f"{labels['support']}: {len(claim.supporting_evidence_ids)}",
                f"{labels['contradiction']}: {len(claim.contradicting_evidence_ids)}",
                f"{labels['corroboration']}: {claim.independent_supporting_source_family_count}",
            )
        )
        for citation in claim.supporting_source_citations:
            locator = citation["locator"] or "-"
            lines.append(
                f"{labels['source']}: {citation['title']} | {locator} | {citation['source_id']}"
            )
        for citation in claim.contradicting_source_citations:
            locator = citation["locator"] or "-"
            lines.append(
                f"{labels['contradicting_source']}: {citation['title']} | {locator} | {citation['source_id']}"
            )
        if claim.source_retraction_state != "CLEAR":
            lines.append(labels["source_warning"])
    if bundle.conflict_group_ids:
        lines.append(f"{labels['conflict']}: {', '.join(bundle.conflict_group_ids)}")
    for warning in bundle.warnings:
        lines.append(f"{labels['warning']}: {warning}")
    lines.append(f"query_hash: {bundle.query_hash}")
    lines.append(f"snapshot_hash: {bundle.memory_snapshot_hash}")
    lines.append(f"answer_hash: {bundle.answer_hash}")
    return "\n".join(lines)


def render_answer_json(bundle: FactAnswerBundle) -> str:
    return canonical_json(bundle)


def _render_value(value: str | bool, unit: str | None) -> str:
    rendered = str(value).lower() if isinstance(value, bool) else value
    return f"{rendered} {unit}" if unit else rendered


_EN = {
    "status": "Status",
    "claim": "Claim",
    "value": "Value",
    "valid": "Valid time",
    "recorded": "Transaction time",
    "support": "Supporting evidence",
    "contradiction": "Contradicting evidence",
    "corroboration": "Independent source families",
    "source": "Source",
    "contradicting_source": "Contradicting source",
    "conflict": "Unresolved conflict",
    "warning": "Warning",
    "source_warning": "Warning: a supporting source is stale or retracted",
}

_RU = {
    "status": "Статус",
    "claim": "Утверждение",
    "value": "Значение",
    "valid": "Время применимости",
    "recorded": "Время знания системы",
    "support": "Поддерживающие свидетельства",
    "contradiction": "Опровергающие свидетельства",
    "corroboration": "Независимые семейства источников",
    "source": "Источник",
    "contradicting_source": "Опровергающий источник",
    "conflict": "Неразрешённый конфликт",
    "warning": "Предупреждение",
    "source_warning": "Предупреждение: источник устарел или отозван",
}
