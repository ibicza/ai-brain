"""Generic deterministic structured and conservative pattern extractors."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from ai_brain.stage3.acquisition.models import (
    ExtractionMethod,
    ProposalStatus,
    SourceSegment,
)
from ai_brain.stage3.knowledge_ir.records import *


@dataclass(frozen=True)
class ExtractedCandidate:
    content: KnowledgeContent
    epistemic: EpistemicCharacter
    dependencies: tuple[str, ...] = ()
    applicability: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    ambiguity_fields: tuple[str, ...] = ()
    status: ProposalStatus = ProposalStatus.PROPOSED


def extract_candidate(
    segment: SourceSegment, kind: KnowledgeKind, method: ExtractionMethod
) -> ExtractedCandidate:
    text = segment.canonical_text.strip()
    if method is ExtractionMethod.DETERMINISTIC_PATTERN:
        return _pattern(text, kind)
    payload = text.split(maxsplit=1)[1].strip() if " " in text else ""
    if kind is KnowledgeKind.CONCEPT:
        parts = _parts(payload, minimum=2)
        return ExtractedCandidate(
            ConceptContent(parts[0], parts[0], parts[-1], parts[-1]),
            EpistemicCharacter.DETERMINISTIC,
        )
    if kind is KnowledgeKind.DEFINITION:
        parts = _parts(payload, minimum=2)
        return ExtractedCandidate(
            DefinitionContent(_slug(parts[0]), parts[-1], parts[-1]),
            EpistemicCharacter.DETERMINISTIC,
        )
    if kind is KnowledgeKind.ENTITY_TYPE:
        parts = _parts(payload, minimum=1)
        parents = (
            tuple(_slug(item) for item in parts[2].split(","))
            if len(parts) > 2 and parts[2]
            else ()
        )
        return ExtractedCandidate(
            EntityTypeContent(_slug(parts[0]), parts[0], parts[0], parents),
            EpistemicCharacter.DETERMINISTIC,
        )
    if kind is KnowledgeKind.RELATION_TYPE:
        parts = _parts(payload, minimum=3)
        return ExtractedCandidate(
            RelationTypeContent(
                _slug(parts[0]),
                EntityTypeRef(_slug(parts[1])),
                EntityTypeRef(_slug(parts[2])),
                "transitive" in parts[3:],
                "symmetric" in parts[3:],
            ),
            EpistemicCharacter.DETERMINISTIC,
        )
    if kind in {KnowledgeKind.TAXONOMY_EDGE, KnowledgeKind.PART_WHOLE_RELATION}:
        left, right = _arrow(payload)
        predicate = "is_a" if kind is KnowledgeKind.TAXONOMY_EDGE else "part_of"
        generic = EntityTypeRef("generic.entity")
        return ExtractedCandidate(
            RelationContent(_slug(left), predicate, _slug(right), generic, generic),
            EpistemicCharacter.DETERMINISTIC,
            dependencies=(_slug(left), _slug(right)),
        )
    if kind is KnowledgeKind.QUANTITY_TYPE:
        parts = _parts(payload, minimum=2)
        dimension = parse_dimension(parts[1])
        unit = UnitRef(parts[2], dimension) if len(parts) > 2 and parts[2] else None
        quantity = QuantityTypeRef(_slug(parts[0]), dimension, unit)
        return ExtractedCandidate(
            QuantityContent(quantity, parts[0], parts[0]),
            EpistemicCharacter.DETERMINISTIC,
        )
    if kind is KnowledgeKind.UNIT_DEFINITION:
        parts = _parts(payload, minimum=2)
        dimension = parse_dimension(parts[1])
        return ExtractedCandidate(
            UnitDefinitionContent(
                UnitRef(_slug(parts[0]), dimension), parts[0], parts[0], parts[0]
            ),
            EpistemicCharacter.DETERMINISTIC,
        )
    if kind is KnowledgeKind.EQUATION_RULE:
        return _equation(payload, method)
    if kind is KnowledgeKind.APPLICABILITY_CONDITION:
        condition_id, expression = _key_value(payload)
        parsed, variables = parse_boolean_expression(expression)
        return ExtractedCandidate(
            ApplicabilityConditionContent(_slug(condition_id), parsed, variables),
            EpistemicCharacter.DETERMINISTIC,
        )
    if kind is KnowledgeKind.EXCEPTION_RULE:
        parts = _parts(payload, minimum=3)
        refs = tuple(_slug(item) for item in parts[1].split(",") if item.strip())
        return ExtractedCandidate(
            ExceptionRuleContent(_slug(parts[0]), refs, parts[2]),
            EpistemicCharacter.NORMATIVE,
            dependencies=refs,
        )
    if kind is KnowledgeKind.TEMPORAL_RELATION:
        fields = _fields(payload)
        return ExtractedCandidate(
            TemporalRelationContent(
                _slug(fields["subject"]),
                fields.get("predicate", "precedes"),
                _slug(fields["object"]),
                fields.get("start"),
                fields.get("end"),
            ),
            EpistemicCharacter.EMPIRICAL,
            dependencies=(_slug(fields["subject"]), _slug(fields["object"])),
        )
    if kind is KnowledgeKind.SPATIAL_RELATION:
        fields = _fields(payload)
        return ExtractedCandidate(
            SpatialRelationContent(
                _slug(fields["subject"]),
                fields["predicate"],
                _slug(fields["object"]),
                fields["frame"],
            ),
            EpistemicCharacter.EMPIRICAL,
            dependencies=(_slug(fields["subject"]), _slug(fields["object"])),
        )
    if kind is KnowledgeKind.CAUSAL_RULE:
        fields = _fields(payload)
        epistemic = (
            EpistemicCharacter.CONTESTED
            if fields.get("status") == "contested"
            else EpistemicCharacter.EMPIRICAL
        )
        return ExtractedCandidate(
            CausalClaimContent(
                _slug(fields["cause"]),
                _slug(fields["effect"]),
                fields["claim"],
                fields.get("mechanism"),
            ),
            epistemic,
            dependencies=(_slug(fields["cause"]), _slug(fields["effect"])),
        )
    if kind is KnowledgeKind.INTERPRETATION:
        fields = _fields(payload)
        supported = tuple(
            _slug(item) for item in fields.get("supports", "").split(",") if item
        )
        contrasts = tuple(
            _slug(item) for item in fields.get("contrasts", "").split(",") if item
        )
        epistemic = (
            EpistemicCharacter.CONTESTED
            if contrasts
            else EpistemicCharacter.INTERPRETIVE
        )
        return ExtractedCandidate(
            InterpretationContent(
                fields["claim"], fields["perspective"], supported, contrasts
            ),
            epistemic,
            dependencies=(*supported, *contrasts),
        )
    if kind is KnowledgeKind.CLAIM_SCHEMA:
        return _api(payload, method)
    if kind is KnowledgeKind.EXAMPLE:
        fields = _fields(payload)
        refs = tuple(_slug(item) for item in fields.get("refs", "").split(",") if item)
        return ExtractedCandidate(
            ExampleContent(fields.get("statement", payload), refs),
            EpistemicCharacter.DETERMINISTIC,
            dependencies=refs,
        )
    if kind is KnowledgeKind.COUNTEREXAMPLE:
        fields = _fields(payload)
        refs = tuple(
            _slug(item) for item in fields.get("refutes", "").split(",") if item
        )
        return ExtractedCandidate(
            CounterexampleContent(fields.get("statement", payload), refs),
            EpistemicCharacter.DETERMINISTIC,
            dependencies=refs,
        )
    if kind is KnowledgeKind.TEST_CASE:
        fields = _fields(payload)
        inputs = _assignments(fields.get("inputs", ""))
        expected = _assignments(fields.get("expected", ""))
        target = _slug(fields["target"])
        return ExtractedCandidate(
            TestCaseContent(target, inputs, expected),
            EpistemicCharacter.DETERMINISTIC,
            dependencies=(target,),
        )
    raise ValueError("unsupported deterministic extraction kind")


def parse_dimension(value: str) -> DimensionVector:
    text = value.strip().removeprefix("[").removesuffix("]")
    mapping = {
        "L": "length",
        "M": "mass",
        "T": "time",
        "I": "electric_current",
        "K": "temperature",
        "N": "amount",
        "J": "luminous_intensity",
    }
    values = {name: 0 for name in mapping.values()}
    if text not in {"", "1", "dimensionless"}:
        for item in text.split(","):
            match = re.fullmatch(r"([LMTIKNJ])\s*=\s*(-?\d+)", item.strip())
            if not match:
                raise ValueError("unknown dimension syntax")
            values[mapping[match.group(1)]] = int(match.group(2))
    return DimensionVector(**values)


def parse_value_type(value: str) -> ValueTypeRef:
    text = value.strip()
    simple = {
        item.value.casefold(): item
        for item in ValueTypeKind
        if item not in {ValueTypeKind.ENTITY, ValueTypeKind.QUANTITY}
    }
    if text.casefold() in simple:
        return ValueTypeRef(simple[text.casefold()])
    match = re.fullmatch(r"entity\[([^]]+)]", text, re.IGNORECASE)
    if match:
        return ValueTypeRef(
            ValueTypeKind.ENTITY, entity_type=EntityTypeRef(_slug(match.group(1)))
        )
    match = re.fullmatch(r"quantity\[([^]]*)]", text, re.IGNORECASE)
    if match:
        dimension = parse_dimension(match.group(1))
        return ValueTypeRef(
            ValueTypeKind.QUANTITY,
            quantity_type=QuantityTypeRef("source.quantity", dimension),
        )
    raise ValueError("unknown value type")


def parse_boolean_expression(value: str):
    # Conditions use the same bounded AST but default all identifiers to Decimal.
    names = tuple(
        sorted(
            set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", value))
            - {"and", "or", "true", "false"}
        )
    )
    variables = tuple(
        VariableBinding(name, ValueTypeRef(ValueTypeKind.DECIMAL), "condition")
        for name in names
    )
    if value.strip().casefold() in {"true", "false"}:
        return Expression(
            ExpressionKind.CONSTANT,
            value.strip().casefold() == "true",
            result_type=ValueTypeRef(ValueTypeKind.BOOLEAN),
        ), variables
    raise ValueError("unsupported bounded condition expression")


def _equation(payload: str, method: ExtractionMethod) -> ExtractedCandidate:
    parts = _parts(payload, minimum=1)
    equation = parts[0]
    fields = _fields(" | ".join(parts[1:])) if len(parts) > 1 else {}
    applicability = fields.get("when", "").strip()
    variable_specs = _assignments(fields.get("vars", ""), separator=";")
    variables = tuple(
        VariableBinding(name, parse_value_type(value), "equation")
        for name, value in variable_specs
    )
    symbol_types = {item.variable_id: item.value_type for item in variables}
    if equation.count("=") != 1:
        raise ValueError("equation must contain one equality")
    left, right = (item.strip() for item in equation.split("=", 1))
    expression = Expression(
        ExpressionKind.EQUAL,
        children=(
            _math_expression(left, symbol_types),
            _math_expression(right, symbol_types),
        ),
        result_type=ValueTypeRef(ValueTypeKind.BOOLEAN),
    )
    ambiguity = []
    status = ProposalStatus.PROPOSED
    if not applicability:
        ambiguity.append("content.applicability.preconditions")
        status = ProposalStatus.REVIEW_REQUIRED
    if not variables:
        ambiguity.append("content.variables")
        status = ProposalStatus.REVIEW_REQUIRED
    content = RuleContent(
        expression,
        variables,
        Applicability((applicability,) if applicability else ("REVIEW_REQUIRED",)),
    )
    return ExtractedCandidate(
        content,
        EpistemicCharacter.DETERMINISTIC,
        applicability=(applicability,) if applicability else (),
        capabilities=("generic.scalar_equation_solver.v1",),
        ambiguity_fields=tuple(ambiguity),
        status=status
        if method is ExtractionMethod.DETERMINISTIC_STRUCTURED
        else ProposalStatus.REVIEW_REQUIRED,
    )


def _math_expression(value: str, types: dict[str, ValueTypeRef]) -> Expression:
    try:
        node = ast.parse(value, mode="eval").body
    except SyntaxError as error:
        raise ValueError("unsupported equation syntax") from error

    def convert(item) -> Expression:
        if isinstance(item, ast.Name):
            if item.id not in types:
                raise ValueError(f"undeclared variable: {item.id}")
            return Expression(
                ExpressionKind.VARIABLE, item.id, result_type=types[item.id]
            )
        if isinstance(item, ast.Constant) and isinstance(item.value, (int, bool)):
            kind = (
                ValueTypeKind.BOOLEAN
                if isinstance(item.value, bool)
                else ValueTypeKind.INTEGER
            )
            return Expression(
                ExpressionKind.CONSTANT, item.value, result_type=ValueTypeRef(kind)
            )
        operators = {
            ast.Add: ExpressionKind.ADD,
            ast.Sub: ExpressionKind.SUBTRACT,
            ast.Mult: ExpressionKind.MULTIPLY,
            ast.Div: ExpressionKind.DIVIDE,
            ast.Pow: ExpressionKind.POWER,
        }
        if isinstance(item, ast.BinOp) and type(item.op) in operators:
            return Expression(
                operators[type(item.op)],
                children=(convert(item.left), convert(item.right)),
            )
        if (
            isinstance(item, ast.UnaryOp)
            and isinstance(item.op, ast.USub)
            and isinstance(item.operand, ast.Constant)
            and isinstance(item.operand.value, int)
        ):
            return Expression(
                ExpressionKind.CONSTANT,
                -item.operand.value,
                result_type=ValueTypeRef(ValueTypeKind.INTEGER),
            )
        raise ValueError("equation contains unsupported code or function")

    return convert(node)


def _api(payload: str, method: ExtractionMethod) -> ExtractedCandidate:
    parts = _parts(payload, minimum=1)
    signature = parts[0]
    fields = _fields(" | ".join(parts[1:])) if len(parts) > 1 else {}
    match = re.fullmatch(
        r"(?:(?:public|protected|private)\s+)?(?:<([^>]+)>\s+)?([\w.<>?]+)\s+([\w.]+)\(([^)]*)\)(?:\s+throws\s+(.+))?",
        signature,
    )
    if not match:
        raise ValueError("unsupported API signature")
    generic, returns, qualified_name, parameters, exceptions = match.groups()
    receiver, _, method_name = qualified_name.rpartition(".")
    parsed_parameters = []
    for parameter in filter(None, (item.strip() for item in parameters.split(","))):
        pieces = parameter.split()
        if len(pieces) != 2:
            raise ValueError("API parameter lacks exact type and name")
        parsed_parameters.append((pieces[1], pieces[0]))
    ambiguity = tuple(
        exact
        for key, exact in (
            ("pre", "content.preconditions"),
            ("post", "content.postconditions"),
        )
        if key not in fields
    )
    content = ClaimSchemaContent(
        EntityTypeRef(_slug(receiver or "static.receiver")),
        _slug(method_name),
        ValueTypeRef(ValueTypeKind.STRING),
        receiver_type=receiver or None,
        parameters=tuple(parsed_parameters),
        return_type=returns,
        generic_constraints=tuple(
            item.strip() for item in (generic or "").split(",") if item.strip()
        ),
        preconditions=(fields["pre"],) if "pre" in fields else (),
        postconditions=(fields["post"],) if "post" in fields else (),
        declared_exceptions=tuple(
            item.strip()
            for item in (exceptions or fields.get("throws", "")).split(",")
            if item.strip()
        ),
        deprecated_since=fields.get("deprecated"),
        examples=(fields["example"],) if "example" in fields else (),
    )
    status = (
        ProposalStatus.REVIEW_REQUIRED
        if ambiguity or method is ExtractionMethod.DETERMINISTIC_PATTERN
        else ProposalStatus.PROPOSED
    )
    return ExtractedCandidate(
        content, EpistemicCharacter.NORMATIVE, ambiguity_fields=ambiguity, status=status
    )


def _pattern(text: str, kind: KnowledgeKind) -> ExtractedCandidate:
    if kind is KnowledgeKind.DEFINITION:
        match = re.fullmatch(
            r"([A-Z][\w -]{1,80})\s+(?:is|means|refers to)\s+(.+)[.]", text
        )
        if not match:
            raise ValueError("definition pattern mismatch")
        return ExtractedCandidate(
            DefinitionContent(_slug(match.group(1)), match.group(2), match.group(2)),
            EpistemicCharacter.EMPIRICAL,
            ambiguity_fields=("proposed_epistemic_character",),
            status=ProposalStatus.REVIEW_REQUIRED,
        )
    if kind is KnowledgeKind.CLAIM_SCHEMA:
        return _api(text, ExtractionMethod.DETERMINISTIC_PATTERN)
    if kind is KnowledgeKind.EQUATION_RULE:
        return _equation(text, ExtractionMethod.DETERMINISTIC_PATTERN)
    raise ValueError("unsupported pattern extraction")


def _parts(value: str, *, minimum: int) -> list[str]:
    parts = [item.strip() for item in value.split("|")]
    if len(parts) < minimum or any(not item for item in parts[:minimum]):
        raise ValueError("structured source field is missing")
    return parts


def _fields(value: str) -> dict[str, str]:
    result = {}
    for item in (part.strip() for part in value.split("|") if part.strip()):
        if ":" not in item:
            continue
        key, field = item.split(":", 1)
        key = key.strip().casefold()
        if key in result:
            raise ValueError("duplicate structured source field")
        result[key] = field.strip()
    return result


def _key_value(value: str):
    if ":" not in value:
        raise ValueError("structured key/value field is missing")
    return tuple(item.strip() for item in value.split(":", 1))


def _arrow(value: str):
    if value.count("->") != 1:
        raise ValueError("relation requires one directed edge")
    return tuple(item.strip() for item in value.split("->", 1))


def _assignments(value: str, separator: str = ",") -> tuple[tuple[str, str], ...]:
    if not value.strip():
        return ()
    result = []
    for item in value.split(separator):
        if ":" in item:
            key, field = item.split(":", 1)
        elif "=" in item:
            key, field = item.split("=", 1)
        else:
            raise ValueError("assignment lacks separator")
        result.append((key.strip(), field.strip()))
    if len({key for key, _ in result}) != len(result):
        raise ValueError("duplicate assignment")
    return tuple(result)


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9_.-]+", "-", value.strip().casefold()).strip("-")
    if not result:
        raise ValueError("source identity is empty")
    return result
