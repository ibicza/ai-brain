"""Fail-closed structural and epistemic validation for Universal Knowledge IR."""

from __future__ import annotations

import re
from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash, normalize_datetime
from ai_brain.stage3.knowledge_ir.records import (
    EpistemicCharacter,
    ExerciseFamilyContent,
    Expression,
    ExpressionKind,
    KnowledgeKind,
    KnowledgeRecord,
    ProcedureContent,
    ProcedureStepKind,
    QuantityContent,
    RelationContent,
    RuleContent,
)
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION

_RULE_KINDS = {
    KnowledgeKind.EQUATION_RULE,
    KnowledgeKind.CONSTRAINT_RULE,
    KnowledgeKind.ALGORITHM,
    KnowledgeKind.STATE_TRANSITION,
    KnowledgeKind.CAUSAL_RULE,
    KnowledgeKind.DEPENDENCY_RULE,
}
_NON_EXECUTABLE = {
    EpistemicCharacter.EMPIRICAL,
    EpistemicCharacter.INTERPRETIVE,
    EpistemicCharacter.CONTESTED,
}
_ARITY = {
    ExpressionKind.ADD: 2,
    ExpressionKind.SUBTRACT: 2,
    ExpressionKind.MULTIPLY: 2,
    ExpressionKind.DIVIDE: 2,
    ExpressionKind.POWER: 2,
    ExpressionKind.EQUAL: 2,
    ExpressionKind.INEQUALITY: 2,
    ExpressionKind.AND: 2,
    ExpressionKind.OR: 2,
}
_CODE_TEXT = re.compile(
    r"(?:\beval\s*\(|\bexec\s*\(|__import__|\blambda\b|os\.system|subprocess)",
    re.IGNORECASE,
)
_RELATION_KINDS = {
    KnowledgeKind.TAXONOMY_EDGE,
    KnowledgeKind.PART_WHOLE_RELATION,
    KnowledgeKind.TEMPORAL_RELATION,
    KnowledgeKind.SPATIAL_RELATION,
    KnowledgeKind.RELATION_TYPE,
}


def record_content_hash(record: KnowledgeRecord) -> str:
    body = asdict(record)
    body.pop("content_hash")
    return content_hash(body)


def validate_expression(expression: Expression, *, depth: int = 0) -> None:
    if depth > 32:
        raise ValueError("expression depth exceeds policy")
    if (
        expression.kind in _ARITY
        and len(expression.children) != _ARITY[expression.kind]
    ):
        raise ValueError("expression operator arity mismatch")
    if expression.kind in {ExpressionKind.VARIABLE, ExpressionKind.CONSTANT}:
        if expression.value is None or expression.children:
            raise ValueError("expression leaf is malformed")
        if isinstance(expression.value, str) and _CODE_TEXT.search(expression.value):
            raise ValueError("executable source text is forbidden in typed expressions")
    elif expression.kind is ExpressionKind.CAPABILITY_REFERENCE:
        if not expression.capability_id or expression.value is not None:
            raise ValueError("capability expression requires an exact capability ID")
    elif expression.value is not None:
        raise ValueError("operator cannot contain an untyped value")
    if expression.kind is ExpressionKind.POWER:
        exponent = expression.children[1]
        if (
            exponent.kind is not ExpressionKind.CONSTANT
            or isinstance(exponent.value, bool)
            or not isinstance(exponent.value, int)
        ):
            raise ValueError("power exponent must be a typed integer constant")
        if not -12 <= exponent.value <= 12:
            raise ValueError("power exponent is outside the bounded policy")
    for child in expression.children:
        validate_expression(child, depth=depth + 1)


def validate_record(record: KnowledgeRecord) -> None:
    if record.schema_version != UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION:
        raise ValueError("unsupported universal knowledge schema")
    if not record.knowledge_id or not record.domain_id or not record.provenance_refs:
        raise ValueError("knowledge identity, domain, and provenance are required")
    normalize_datetime(record.created_at)
    if len(set(record.dependencies)) != len(record.dependencies):
        raise ValueError("duplicate knowledge dependency")
    if record.knowledge_id in record.dependencies:
        raise ValueError("self knowledge dependency")
    if isinstance(record.content, RuleContent):
        if record.kind not in _RULE_KINDS:
            raise ValueError("typed rule content has incompatible kind")
        validate_expression(record.content.expression)
        if not record.content.applicability.preconditions:
            raise ValueError("rules require explicit applicability preconditions")
        if record.epistemic_character in _NON_EXECUTABLE:
            raise ValueError("non-executable epistemic record cannot become a rule")
        if (
            record.epistemic_character is not EpistemicCharacter.DETERMINISTIC
            and not record.content.policy_authority_ref
        ):
            raise ValueError(
                "non-deterministic rule requires reviewed policy authority"
            )
        if (
            record.epistemic_character is EpistemicCharacter.APPROXIMATE
            and not record.content.approximation_conditions
        ):
            raise ValueError("approximate rule requires approximation conditions")
        if (
            record.epistemic_character is EpistemicCharacter.NORMATIVE
            and not record.content.policy_authority_ref
        ):
            raise ValueError("normative rule requires reviewed authority context")
        if (
            record.epistemic_character is EpistemicCharacter.HEURISTIC
            and record.kind is KnowledgeKind.ALGORITHM
        ):
            raise ValueError("heuristic cannot masquerade as an exact algorithm")
    if isinstance(record.content, ProcedureContent):
        if record.kind is not KnowledgeKind.PROCEDURE:
            raise ValueError("procedure content has incompatible kind")
        if record.epistemic_character is not EpistemicCharacter.DETERMINISTIC:
            raise ValueError("executable procedure must be deterministic")
        _validate_procedure(record.content, set(record.required_capability_ids))
    elif record.kind is KnowledgeKind.PROCEDURE:
        raise ValueError("procedure kind requires typed procedure content")
    if record.kind in _RELATION_KINDS and not isinstance(
        record.content, RelationContent
    ):
        raise ValueError("relation kind requires typed relation content")
    if record.kind in {
        KnowledgeKind.QUANTITY_TYPE,
        KnowledgeKind.UNIT_DEFINITION,
    } and not isinstance(record.content, QuantityContent):
        raise ValueError("quantity kind requires typed quantity content")
    if record.kind is KnowledgeKind.EXERCISE_FAMILY and not isinstance(
        record.content, ExerciseFamilyContent
    ):
        raise ValueError("exercise-family kind requires typed exercise content")
    if record.content_hash != record_content_hash(record):
        raise ValueError("knowledge record content hash mismatch")


def _validate_procedure(value: ProcedureContent, required: set[str]) -> None:
    by_id = {step.step_id: step for step in value.steps}
    if len(by_id) != len(value.steps) or value.entry_step_id not in by_id:
        raise ValueError("procedure step identity or entry is invalid")
    for step in value.steps:
        if not step.output_type or any(
            item not in by_id for item in step.next_step_ids
        ):
            raise ValueError("procedure contains a dangling or untyped step")
        if step.kind is ProcedureStepKind.INVOKE_CAPABILITY:
            if (
                not step.capability_id
                or step.capability_id not in required
                or not step.authority_ref
            ):
                raise ValueError("procedure capability must bind installed authority")
        elif step.capability_id is not None:
            raise ValueError("only capability invocation steps may bind capabilities")
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValueError("procedure step graph contains a cycle")
        if step_id in done:
            return
        visiting.add(step_id)
        for child in by_id[step_id].next_step_ids:
            visit(child)
        visiting.remove(step_id)
        done.add(step_id)

    visit(value.entry_step_id)
    if done != set(by_id):
        raise ValueError("procedure contains unreachable steps")


def validate_records(records: tuple[KnowledgeRecord, ...]) -> None:
    by_id = {item.knowledge_id: item for item in records}
    if len(by_id) != len(records):
        raise ValueError("duplicate knowledge ID")
    for item in records:
        validate_record(item)
        missing = (set(item.dependencies) | set(item.applicability_refs)) - set(by_id)
        if missing:
            raise ValueError("dangling knowledge reference")
