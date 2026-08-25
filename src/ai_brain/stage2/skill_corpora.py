"""Explicit skill-encoder corpus conditions for fair retrieval ablations."""

from __future__ import annotations

import json
from collections.abc import Iterable

from ai_brain.stage1.models import content_hash
from ai_brain.stage1.specifications import specification_from_dict
from ai_brain.stage2.models import SkillRecord

CORPUS_CONDITIONS = ("rich", "sanitized", "minimal")


def build_skill_corpus(
    records: Iterable[SkillRecord], condition: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if condition not in CORPUS_CONDITIONS:
        raise ValueError(f"unknown skill corpus condition: {condition}")
    skills = sorted(
        (item for item in records if item.active and not item.deprecated),
        key=lambda item: item.skill_id,
    )
    texts = tuple(skill_corpus_text(item, condition) for item in skills)
    return tuple(item.skill_id for item in skills), texts


def skill_corpus_text(skill: SkillRecord, condition: str) -> str:
    specification = specification_from_dict(skill.effect_schema)
    if condition == "rich":
        fields = (
            skill.canonical_name_ru,
            skill.canonical_name_en,
            skill.effect_summary,
            *skill.aliases_ru,
            *skill.aliases_en,
            *skill.controlled_examples_ru,
            *skill.controlled_examples_en,
            json.dumps(skill.effect_schema, ensure_ascii=False, sort_keys=True),
        )
        return "\n".join(fields)
    phases = tuple(
        f"{action}({source},{destination or 'NONE'})"
        for action, source, destination in specification.phase_constraints
    )
    if condition == "sanitized":
        return "\n".join(
            (
                f"EFFECT_ACTIONS {' '.join(phases) or 'HALT'}",
                f"INPUT_ROLES {' '.join(specification.inputs) or 'NONE'}",
                f"OUTPUT_ROLES {' '.join(specification.outputs) or 'NONE'}",
                f"EMPTIED_ROLES {' '.join(specification.terminate_when_empty) or 'NONE'}",
                f"PRESERVED_ROLES {' '.join(specification.preserve) or 'NONE'}",
                f"PHASE_ORDER {'STRICT' if len(phases) > 1 else 'SINGLE'}",
            )
        )
    return " | ".join(
        (
            *phases,
            f"IN={','.join(specification.inputs) or '-'}",
            f"OUT={','.join(specification.outputs) or '-'}",
            f"KEEP={','.join(specification.preserve) or '-'}",
        )
    )


def skill_corpus_hash(records: Iterable[SkillRecord], condition: str) -> str:
    skill_ids, texts = build_skill_corpus(records, condition)
    return content_hash(
        {"condition": condition, "skill_ids": skill_ids, "texts": texts}
    )
