"""Fail-closed structural, semantic and epistemic validation for IR v2."""

from __future__ import annotations

import re
from dataclasses import asdict
from decimal import Decimal, InvalidOperation

from ai_brain.stage2.facts.canonical import content_hash, normalize_datetime
from ai_brain.stage3.knowledge_ir.records import *
from ai_brain.stage3.knowledge_ir.serialization_types import CONTENT_TYPES
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION

_RULE_KINDS = {
    KnowledgeKind.EQUATION_RULE,
    KnowledgeKind.CONSTRAINT_RULE,
    KnowledgeKind.ALGORITHM,
    KnowledgeKind.STATE_TRANSITION,
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
    r"(?:\beval\s*\(|\bexec\s*\(|__import__|\blambda\b|os\.system|subprocess|[;&|`]\s*(?:sh|bash|cmd|powershell)\b)",
    re.IGNORECASE,
)
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,191}$")
_NUMERIC = {
    ValueTypeKind.INTEGER,
    ValueTypeKind.DECIMAL,
    ValueTypeKind.RATIONAL,
    ValueTypeKind.QUANTITY,
}


class VariableSymbolTable:
    """Exact immutable-by-convention symbol table used during validation."""

    def __init__(self, bindings: tuple[VariableBinding, ...]) -> None:
        self.bindings = {item.variable_id: item for item in bindings}
        if len(self.bindings) != len(bindings):
            raise ValueError("duplicate variable ID")
        if any(not _ID.fullmatch(item.variable_id) for item in bindings):
            raise ValueError("invalid variable ID")

    def require(self, variable_id: str) -> VariableBinding:
        try:
            return self.bindings[variable_id]
        except KeyError as error:
            raise ValueError("undeclared variable") from error


def record_content_hash(record: KnowledgeRecord) -> str:
    body = asdict(record)
    body.pop("content_hash")
    return content_hash(body)


def validate_dimension(value: DimensionVector) -> None:
    exponents = tuple(asdict(value).values())
    if any(
        isinstance(x, bool) or not isinstance(x, int) or not -24 <= x <= 24
        for x in exponents
    ):
        raise ValueError("invalid bounded dimension vector")


def validate_value_type(value: ValueTypeRef) -> None:
    if value.kind is ValueTypeKind.ENTITY:
        if value.entity_type is None or value.quantity_type is not None:
            raise ValueError("entity value type requires exactly one entity type")
    elif value.kind is ValueTypeKind.QUANTITY:
        if value.quantity_type is None or value.entity_type is not None:
            raise ValueError("quantity value type requires exactly one quantity type")
        validate_dimension(value.quantity_type.dimension)
        if value.quantity_type.canonical_unit is not None:
            unit = value.quantity_type.canonical_unit
            validate_dimension(unit.dimension)
            if unit.dimension != value.quantity_type.dimension:
                raise ValueError("unit and quantity dimensions differ")
            if unit.scale_denominator == 0:
                raise ValueError("unit scale denominator is zero")
    elif value.entity_type is not None or value.quantity_type is not None:
        raise ValueError("scalar value type cannot carry entity or quantity metadata")


def validate_expression(
    expression: Expression,
    *,
    depth: int = 0,
    symbols: VariableSymbolTable | None = None,
    required_capabilities: set[str] | None = None,
) -> ValueTypeRef:
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
    if expression.kind is ExpressionKind.VARIABLE:
        if not isinstance(expression.value, str) or symbols is None:
            raise ValueError("variable expression requires a symbol table")
        result = symbols.require(expression.value).value_type
    elif expression.kind is ExpressionKind.CONSTANT:
        result = _constant_type(expression.value, expression.result_type)
    elif expression.kind is ExpressionKind.CAPABILITY_REFERENCE:
        if (
            not expression.capability_id
            or expression.value is not None
            or expression.children
            or expression.result_type is None
            or required_capabilities is None
            or expression.capability_id not in required_capabilities
        ):
            raise ValueError(
                "capability reference lacks signature or declared authority"
            )
        validate_value_type(expression.result_type)
        result = expression.result_type
    else:
        if expression.value is not None or expression.capability_id is not None:
            raise ValueError("operator cannot contain an untyped value or authority")
        children = tuple(
            validate_expression(
                child,
                depth=depth + 1,
                symbols=symbols,
                required_capabilities=required_capabilities,
            )
            for child in expression.children
        )
        result = _operator_type(expression.kind, children, expression.children)
    if expression.result_type is not None:
        validate_value_type(expression.result_type)
        if not _compatible(result, expression.result_type):
            raise ValueError("declared expression result type mismatch")
        result = expression.result_type
    return result


def validate_record(record: KnowledgeRecord) -> None:
    if record.schema_version != UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION:
        raise ValueError("unsupported universal knowledge schema")
    if not record.knowledge_id or not record.domain_id or not record.provenance_refs:
        raise ValueError("knowledge identity, domain, and provenance are required")
    if not isinstance(record.content, CONTENT_TYPES[record.kind]):
        raise TypeError("knowledge kind has wrong tagged content type")
    normalize_datetime(record.created_at)
    for values, label in (
        (record.dependencies, "knowledge dependency"),
        (record.applicability_refs, "applicability reference"),
        (record.required_capability_ids, "required capability"),
    ):
        if len(set(values)) != len(values):
            raise ValueError(f"duplicate {label}")
    if record.knowledge_id in (*record.dependencies, *record.applicability_refs):
        raise ValueError("self knowledge reference")
    _validate_content(record)
    if record.content_hash != record_content_hash(record):
        raise ValueError("knowledge record content hash mismatch")


def validate_records(
    records: tuple[KnowledgeRecord, ...], *, external_targets: tuple[str, ...] = ()
) -> None:
    by_id = {item.knowledge_id: item for item in records}
    if len(by_id) != len(records):
        raise ValueError("duplicate knowledge ID")
    allowed = set(by_id) | set(external_targets)
    for item in records:
        validate_record(item)
        missing = (set(item.dependencies) | set(item.applicability_refs)) - allowed
        if missing:
            raise ValueError("dangling knowledge reference")
        for target in _semantic_targets(item.content):
            if target not in allowed:
                raise ValueError("relation or typed content target does not exist")
    _acyclic(by_id, lambda item: item.dependencies, "knowledge dependency")
    _acyclic(by_id, lambda item: item.applicability_refs, "applicability")
    _acyclic(
        by_id,
        lambda item: (
            item.content.exception_condition_ids
            if isinstance(item.content, ExceptionRuleContent)
            else ()
        ),
        "exception",
    )


def _validate_content(record: KnowledgeRecord) -> None:
    content = record.content
    if isinstance(content, RuleContent):
        if record.kind not in _RULE_KINDS:
            raise ValueError("typed rule content has incompatible kind")
        symbols = _validate_bindings(content.variables)
        validate_expression(
            content.expression,
            symbols=symbols,
            required_capabilities=set(record.required_capability_ids),
        )
        used = _variables(content.expression)
        if used != set(symbols.bindings):
            raise ValueError("declared and used variables must match exactly")
        if not content.applicability.preconditions:
            raise ValueError("rules require explicit applicability preconditions")
        if not set(content.applicability.required_capabilities) <= set(
            record.required_capability_ids
        ):
            raise ValueError("applicability uses undeclared capability")
        if record.epistemic_character in _NON_EXECUTABLE:
            raise ValueError("non-executable epistemic record cannot become a rule")
        if (
            record.epistemic_character is not EpistemicCharacter.DETERMINISTIC
            and not content.policy_authority_ref
        ):
            raise ValueError(
                "non-deterministic rule requires reviewed policy authority"
            )
        if (
            record.epistemic_character is EpistemicCharacter.APPROXIMATE
            and not content.approximation_conditions
        ):
            raise ValueError("approximate rule requires approximation conditions")
        if (
            record.epistemic_character is EpistemicCharacter.HEURISTIC
            and record.kind is KnowledgeKind.ALGORITHM
        ):
            raise ValueError("heuristic cannot masquerade as an exact algorithm")
    elif isinstance(content, ApplicabilityConditionContent):
        symbols = _validate_bindings(content.variables)
        result = validate_expression(
            content.expression, symbols=symbols, required_capabilities=set()
        )
        if result.kind is not ValueTypeKind.BOOLEAN:
            raise ValueError("applicability condition must be boolean")
    elif isinstance(content, ProcedureContent):
        if record.epistemic_character is not EpistemicCharacter.DETERMINISTIC:
            raise ValueError("executable procedure must be deterministic")
        _validate_procedure(content, set(record.required_capability_ids))
    elif isinstance(content, InterpretationContent):
        if record.epistemic_character not in {
            EpistemicCharacter.INTERPRETIVE,
            EpistemicCharacter.CONTESTED,
        }:
            raise ValueError("interpretation requires interpretive epistemic character")
    elif isinstance(content, CausalClaimContent):
        if record.epistemic_character is EpistemicCharacter.DETERMINISTIC:
            raise ValueError(
                "causal source claim cannot become deterministic authority"
            )
    elif isinstance(content, (QuantityContent, UnitDefinitionContent)):
        value = (
            ValueTypeRef(ValueTypeKind.QUANTITY, quantity_type=content.quantity_type)
            if isinstance(content, QuantityContent)
            else ValueTypeRef(
                ValueTypeKind.QUANTITY,
                quantity_type=QuantityTypeRef(
                    content.unit.unit_id, content.unit.dimension, content.unit
                ),
            )
        )
        validate_value_type(value)


def _validate_bindings(bindings: tuple[VariableBinding, ...]) -> VariableSymbolTable:
    table = VariableSymbolTable(bindings)
    for item in bindings:
        validate_value_type(item.value_type)
        low = _decimal(item.minimum) if item.minimum is not None else None
        high = _decimal(item.maximum) if item.maximum is not None else None
        if low is not None and high is not None and low > high:
            raise ValueError("variable minimum exceeds maximum")
    return table


def _validate_procedure(value: ProcedureContent, required: set[str]) -> None:
    validate_value_type(value.output_type)
    by_id = {step.step_id: step for step in value.steps}
    if len(by_id) != len(value.steps) or value.entry_step_id not in by_id:
        raise ValueError("procedure step identity or entry is invalid")
    for step in value.steps:
        validate_value_type(step.output_type)
        if any(item not in by_id for item in (*step.input_refs, *step.next_step_ids)):
            raise ValueError("procedure contains a dangling step reference")
        if step.kind is ProcedureStepKind.INVOKE_CAPABILITY:
            if (
                not step.capability_id
                or step.capability_id not in required
                or not step.authority_ref
            ):
                raise ValueError("procedure capability must bind installed authority")
        elif step.capability_id is not None:
            raise ValueError("only capability invocation steps may bind capabilities")
        if step.kind is ProcedureStepKind.BRANCH_TYPED_RESULT and (
            len(step.input_refs) != 1
            or by_id[step.input_refs[0]].output_type.kind is not ValueTypeKind.BOOLEAN
        ):
            raise ValueError("procedure branch condition must be boolean")
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
    terminal = tuple(step for step in value.steps if not step.next_step_ids)
    if not terminal or any(
        not _compatible(step.output_type, value.output_type) for step in terminal
    ):
        raise ValueError("procedure terminal output type mismatch")


def _constant_type(value, declared: ValueTypeRef | None) -> ValueTypeRef:
    if isinstance(value, bool):
        inferred = ValueTypeRef(ValueTypeKind.BOOLEAN)
    elif isinstance(value, int):
        inferred = ValueTypeRef(ValueTypeKind.INTEGER)
    elif isinstance(value, str):
        try:
            Decimal(value)
            inferred = ValueTypeRef(ValueTypeKind.DECIMAL)
        except InvalidOperation:
            inferred = ValueTypeRef(ValueTypeKind.STRING)
    else:
        raise TypeError("constant has unsupported type")
    if declared is not None and declared.kind is ValueTypeKind.QUANTITY:
        return declared
    if declared is not None and not _compatible(inferred, declared):
        raise ValueError("constant type mismatch")
    return declared or inferred


def _operator_type(kind, children, child_expressions) -> ValueTypeRef:
    left, right = children
    if kind in {ExpressionKind.AND, ExpressionKind.OR}:
        if any(x.kind is not ValueTypeKind.BOOLEAN for x in children):
            raise ValueError("boolean operator received non-boolean input")
        return ValueTypeRef(ValueTypeKind.BOOLEAN)
    if kind in {ExpressionKind.EQUAL, ExpressionKind.INEQUALITY}:
        if not _compatible(left, right):
            raise ValueError("comparison types or dimensions differ")
        if kind is ExpressionKind.INEQUALITY and left.kind not in _NUMERIC:
            raise ValueError("inequality requires ordered numeric inputs")
        return ValueTypeRef(ValueTypeKind.BOOLEAN)
    if kind in {ExpressionKind.ADD, ExpressionKind.SUBTRACT}:
        if left.kind not in _NUMERIC or not _compatible(left, right):
            raise ValueError("additive operator types or dimensions differ")
        return left
    if kind is ExpressionKind.POWER:
        exponent = child_expressions[1]
        if (
            exponent.kind is not ExpressionKind.CONSTANT
            or isinstance(exponent.value, bool)
            or not isinstance(exponent.value, int)
        ):
            raise ValueError("power exponent must be a typed integer constant")
        if not -12 <= exponent.value <= 12:
            raise ValueError("power exponent is outside the bounded policy")
        if left.kind not in _NUMERIC:
            raise ValueError("power base must be numeric")
        return _dimension_result(left, exponent.value)
    if kind in {ExpressionKind.MULTIPLY, ExpressionKind.DIVIDE}:
        if left.kind not in _NUMERIC or right.kind not in _NUMERIC:
            raise ValueError("multiplicative operator requires numeric inputs")
        return _multiply_type(left, right, divide=kind is ExpressionKind.DIVIDE)
    raise ValueError("unsupported expression operator")


def _compatible(left: ValueTypeRef, right: ValueTypeRef) -> bool:
    if left.kind != right.kind:
        return left.kind in _NUMERIC - {
            ValueTypeKind.QUANTITY
        } and right.kind in _NUMERIC - {ValueTypeKind.QUANTITY}
    if left.kind is ValueTypeKind.ENTITY:
        return left.entity_type == right.entity_type
    if left.kind is ValueTypeKind.QUANTITY:
        return (
            left.quantity_type is not None
            and right.quantity_type is not None
            and left.quantity_type.dimension == right.quantity_type.dimension
        )
    return True


def _multiply_type(
    left: ValueTypeRef, right: ValueTypeRef, *, divide: bool
) -> ValueTypeRef:
    if (
        left.kind is not ValueTypeKind.QUANTITY
        and right.kind is not ValueTypeKind.QUANTITY
    ):
        return ValueTypeRef(ValueTypeKind.DECIMAL)
    ld = _dimension_of(left)
    rd = _dimension_of(right)
    sign = -1 if divide else 1
    dimension = DimensionVector(
        *tuple(
            a + sign * b
            for a, b in zip(asdict(ld).values(), asdict(rd).values(), strict=True)
        )
    )
    validate_dimension(dimension)
    return ValueTypeRef(
        ValueTypeKind.QUANTITY,
        quantity_type=QuantityTypeRef("derived.quantity", dimension),
    )


def _dimension_result(value: ValueTypeRef, exponent: int) -> ValueTypeRef:
    if value.kind is not ValueTypeKind.QUANTITY:
        return value
    dimension = DimensionVector(
        *tuple(x * exponent for x in asdict(_dimension_of(value)).values())
    )
    validate_dimension(dimension)
    return ValueTypeRef(
        ValueTypeKind.QUANTITY,
        quantity_type=QuantityTypeRef("derived.power", dimension),
    )


def _dimension_of(value: ValueTypeRef) -> DimensionVector:
    return value.quantity_type.dimension if value.quantity_type else DimensionVector()


def _decimal(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("invalid exact decimal bound") from error
    if not result.is_finite():
        raise ValueError("non-finite variable bound")
    return result


def _variables(expression: Expression) -> set[str]:
    values = (
        {str(expression.value)} if expression.kind is ExpressionKind.VARIABLE else set()
    )
    for child in expression.children:
        values |= _variables(child)
    return values


def _semantic_targets(content: KnowledgeContent) -> tuple[str, ...]:
    if isinstance(content, RelationContent):
        return (content.subject_id, content.object_id)
    if isinstance(content, TemporalRelationContent):
        return (content.subject_id, content.object_id)
    if isinstance(content, SpatialRelationContent):
        return (content.subject_id, content.object_id)
    if isinstance(content, CausalClaimContent):
        return (content.cause_id, content.effect_id)
    if isinstance(content, InterpretationContent):
        return (*content.supported_record_ids, *content.contrast_record_ids)
    if isinstance(content, CounterexampleContent):
        return content.refuted_record_ids
    if isinstance(content, TestCaseContent):
        return (content.target_record_id,)
    return ()


def _acyclic(by_id, edges, label: str) -> None:
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"{label} cycle")
        if node in done or node not in by_id:
            return
        visiting.add(node)
        for child in edges(by_id[node]):
            visit(child)
        visiting.remove(node)
        done.add(node)

    for node in by_id:
        visit(node)
