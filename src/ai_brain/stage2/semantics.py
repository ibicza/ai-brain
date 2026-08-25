"""Deterministic final-register-state equivalence classes for Stage 2."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.models import SemanticFamily, content_hash
from ai_brain.stage1.specifications import infer_family, specification_from_dict
from ai_brain.stage2.models import FinalStateEquivalenceGroup, SkillRecord


def final_state_effect_signature(
    specification: ProgramSpecification,
) -> dict[str, Any]:
    """Return a normal form for final register state, not execution trace."""
    family = infer_family(specification)
    if family is None:
        raise ValueError("unsupported semantic family")

    order_sensitive = family == SemanticFamily.DROP_THEN_TRANSFER
    transfers = tuple(specification.transfers)
    phases = tuple(specification.phase_constraints)
    inputs = tuple(specification.inputs)
    if family in {SemanticFamily.MERGE_TWO, SemanticFamily.MERGE_THREE}:
        transfers = tuple(sorted(transfers))
        phases = tuple(sorted(phases, key=lambda row: (row[0], row[1], row[2] or "")))
        inputs = tuple(sorted(inputs))

    # A valid NOOP has no changed roles. Its bookkeeping fields do not create an
    # observable state transition, so all valid catalog NOOPs share one class.
    if family == SemanticFamily.NOOP:
        return {
            "family": family.value,
            "changed_roles": (),
            "outputs": (),
            "drops": (),
            "transfers": (),
            "preserve": "ALL_ROLES_BY_NOOP_SEMANTICS",
            "terminate_when_empty": (),
            "order_sensitive_phases": (),
            "supported_primitives": ("HALT",),
        }

    changed_roles = tuple(
        sorted(
            set(specification.drops)
            | {role for transfer in transfers for role in transfer}
        )
    )
    return {
        "family": family.value,
        "inputs": inputs,
        "changed_roles": changed_roles,
        "outputs": tuple(sorted(specification.outputs)),
        "drops": tuple(sorted(specification.drops)),
        "transfers": transfers,
        "preserve": tuple(sorted(specification.preserve)),
        "terminate_when_empty": tuple(sorted(specification.terminate_when_empty)),
        "order_sensitive_phases": phases if order_sensitive else (),
        "supported_primitives": tuple(sorted(specification.allowed_primitives)),
    }


def final_state_effect_hash(specification: ProgramSpecification) -> str:
    return content_hash(final_state_effect_signature(specification))


def equivalence_proof_kind(specification: ProgramSpecification) -> str:
    family = infer_family(specification)
    if family in {SemanticFamily.MERGE_TWO, SemanticFamily.MERGE_THREE}:
        return "COMMUTING_DRAINS_SAME_DESTINATION"
    if family == SemanticFamily.DROP_THEN_TRANSFER:
        return "ORDER_PRESERVED_BY_PHASE_SEMANTICS"
    return "EXACT_STAGE1_EFFECT_NORMAL_FORM"


def build_final_state_equivalence_groups(
    records: Iterable[SkillRecord],
) -> tuple[FinalStateEquivalenceGroup, ...]:
    grouped: dict[str, list[SkillRecord]] = defaultdict(list)
    for record in records:
        if record.active and not record.deprecated:
            grouped[record.final_state_effect_hash].append(record)
    groups: list[FinalStateEquivalenceGroup] = []
    for effect_hash, members in sorted(grouped.items()):
        ordered = sorted(members, key=lambda item: item.skill_id)
        specification = specification_from_dict(ordered[0].effect_schema)
        family = infer_family(specification)
        groups.append(
            FinalStateEquivalenceGroup(
                final_state_effect_hash=effect_hash,
                member_skill_ids=tuple(item.skill_id for item in ordered),
                canonical_skill_id=ordered[0].skill_id,
                equivalence_proof_kind=equivalence_proof_kind(specification),
                order_sensitive=family == SemanticFamily.DROP_THEN_TRANSFER,
                member_count=len(ordered),
            )
        )
    return tuple(groups)


# Source aliases keep old reports and imports readable. New v3 artifacts and APIs use
# explicit final-state terminology and never treat these hashes as trace identity.
semantic_effect_signature = final_state_effect_signature
semantic_effect_hash = final_state_effect_hash
build_equivalence_groups = build_final_state_equivalence_groups
