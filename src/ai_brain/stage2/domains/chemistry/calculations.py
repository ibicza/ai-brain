"""Bounded Decimal chemistry calculations over a current-state snapshot."""

from __future__ import annotations

from dataclasses import asdict
from decimal import ROUND_HALF_EVEN, Decimal, DecimalException, localcontext
from typing import Any

from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser, verify_ast
from ai_brain.stage2.domains.chemistry.models import (
    AtomicWeightKind,
    AtomicWeightMode,
    ChemistryKnowledgeSnapshot,
    ChemistryQuantityLimits,
    ChemistryResultBundle,
    ChemistryRoundingSpec,
    EntityAmountBasis,
    EntityAmountDirection,
)
from ai_brain.stage2.domains.chemistry.version import (
    CHEMISTRY_ATOMIC_WEIGHT_POLICY,
    CHEMISTRY_CALCULATION_POLICY_VERSION,
    CHEMISTRY_DOMAIN_VERSION,
    CHEMISTRY_FORMULA_GRAMMAR_VERSION,
    CHEMISTRY_RESULT_SCHEMA_VERSION,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.trusted_decimal import (
    DecimalLimits,
    TrustedDecimalError,
    parse_bounded_decimal,
    render_bounded_decimal,
)

CHEMISTRY_QUANTITY_LIMITS = ChemistryQuantityLimits()
DEFAULT_ROUNDING_SPEC = ChemistryRoundingSpec()
ROUNDING_POLICY = "SIGNIFICANT_DIGITS_ROUND_HALF_EVEN_V2"


class ChemistryCalculationError(ValueError):
    pass


def quantity_decimal(
    value: Any, *, nonnegative: bool = True, integer: bool = False
) -> Decimal:
    try:
        return parse_bounded_decimal(
            value,
            _decimal_limits(max_abs=True),
            nonnegative=nonnegative,
            integer=integer,
        )
    except TrustedDecimalError as error:
        raise ChemistryCalculationError(str(error)) from error


def canonical_decimal(
    value: Any, *, nonnegative: bool = True, integer: bool = False
) -> str:
    try:
        return render_bounded_decimal(
            quantity_decimal(value, nonnegative=nonnegative, integer=integer),
            _decimal_limits(max_abs=True),
        )
    except TrustedDecimalError as error:
        raise ChemistryCalculationError(str(error)) from error


def render_significant(
    value: Decimal, spec: ChemistryRoundingSpec = DEFAULT_ROUNDING_SPEC
) -> dict[str, Any]:
    if not 1 <= spec.significant_digits <= 12:
        raise ChemistryCalculationError("significant_digits must be in 1..12")
    if spec.rounding_mode != "ROUND_HALF_EVEN":
        raise ChemistryCalculationError("unsupported chemistry rounding mode")
    exact = _result_text(value)
    if value.is_zero():
        rounded = Decimal(0).quantize(Decimal(1).scaleb(-(spec.significant_digits - 1)))
    else:
        quantum = Decimal(1).scaleb(value.adjusted() - spec.significant_digits + 1)
        with localcontext() as context:
            context.prec = CHEMISTRY_QUANTITY_LIMITS.context_precision
            rounded = value.quantize(quantum, rounding=ROUND_HALF_EVEN)
    if (
        abs(rounded.adjusted()) >= spec.scientific_notation_threshold
        and not rounded.is_zero()
    ):
        rendered = format(rounded, f".{spec.significant_digits - 1}E")
        coefficient, exponent = rendered.split("E")
        rendered = f"{coefficient}E{int(exponent):+d}"
    else:
        try:
            rendered = render_bounded_decimal(
                rounded,
                _decimal_limits(max_abs=False),
                preserve_trailing_zeros=spec.trailing_zero_policy
                == "PRESERVE_SIGNIFICANCE",
            )
        except TrustedDecimalError as error:
            raise ChemistryCalculationError(str(error)) from error
    return {
        "exact_internal_value": exact,
        "rendered_value": rendered,
        "significant_digits": spec.significant_digits,
        "rounding_mode": spec.rounding_mode,
        "rounding_applied": Decimal(exact) != rounded,
    }


def formula_composition(
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
    formula: str,
) -> ChemistryResultBundle:
    ast = parser.parse(formula)
    verify_ast(ast)
    result = {
        "canonical_formula": ast.canonical_formula,
        "element_counts": {entry.symbol: entry.count for entry in ast.composition},
        "total_atom_count": sum(entry.count for entry in ast.composition),
        "grammar_version": ast.grammar_version,
    }
    return _bundle(
        "formula_composition",
        ast.canonical_formula,
        ast.ast_hash,
        ast.composition,
        snapshot,
        (),
        result,
        (),
    )


def molar_mass(
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
    formula: str,
    *,
    mode: AtomicWeightMode | str = AtomicWeightMode.CONVENTIONAL_CLASSROOM,
    unit: str = "g/mol",
    rounding: ChemistryRoundingSpec = DEFAULT_ROUNDING_SPEC,
) -> ChemistryResultBundle:
    ast = parser.parse(formula)
    selected_mode = _weight_mode(mode)
    weights = {record.symbol: record for record in snapshot.element_records}
    steps = []
    warnings: list[str] = []
    with localcontext() as context:
        context.prec = CHEMISTRY_QUANTITY_LIMITS.context_precision
        if selected_mode == AtomicWeightMode.CONVENTIONAL_CLASSROOM:
            total = Decimal(0)
            for entry in ast.composition:
                record = _weight(weights, entry.symbol)
                contribution = Decimal(record.abridged_value) * entry.count
                total += contribution
                steps.append(
                    {
                        "symbol": entry.symbol,
                        "count": entry.count,
                        "abridged_atomic_weight": record.abridged_value,
                        "abridged_uncertainty": record.abridged_uncertainty,
                        "exact_contribution_g_per_mol": _result_text(contribution),
                    }
                )
            if unit == "kg/mol":
                total /= Decimal(1000)
            elif unit != "g/mol":
                raise ChemistryCalculationError(
                    "molar-mass unit must be g/mol or kg/mol"
                )
            rendered = render_significant(total, rounding)
            result: dict[str, Any] = {
                "mode": selected_mode.value,
                "value": rendered["exact_internal_value"],
                **rendered,
                "unit": unit,
            }
            warnings.extend(
                (
                    "CONVENTIONAL_CLASSROOM_VALUE",
                    "NOT_AN_EXACT_NATURAL_CONSTANT",
                    "DISPLAY_ROUNDING_ONLY",
                )
            )
        else:
            lower = Decimal(0)
            upper = Decimal(0)
            has_single = False
            for entry in ast.composition:
                record = _weight(weights, entry.symbol)
                if record.standard_kind == AtomicWeightKind.INTERVAL:
                    lo = Decimal(record.standard_interval_lower or "0")
                    hi = Decimal(record.standard_interval_upper or "0")
                else:
                    lo = hi = Decimal(record.standard_nominal or "0")
                    has_single = True
                lower += lo * entry.count
                upper += hi * entry.count
                steps.append(
                    {
                        "symbol": entry.symbol,
                        "count": entry.count,
                        "standard_kind": record.standard_kind.value,
                        "exact_lower": _result_text(lo),
                        "exact_upper": _result_text(hi),
                        "standard_uncertainty": record.standard_uncertainty,
                    }
                )
            if unit == "kg/mol":
                lower /= Decimal(1000)
                upper /= Decimal(1000)
            elif unit != "g/mol":
                raise ChemistryCalculationError(
                    "molar-mass unit must be g/mol or kg/mol"
                )
            lower_rendered = render_significant(lower, rounding)
            upper_rendered = render_significant(upper, rounding)
            result = {
                "mode": selected_mode.value,
                "lower": lower_rendered["exact_internal_value"],
                "upper": upper_rendered["exact_internal_value"],
                "exact_internal_lower": lower_rendered["exact_internal_value"],
                "exact_internal_upper": upper_rendered["exact_internal_value"],
                "rendered_lower": lower_rendered["rendered_value"],
                "rendered_upper": upper_rendered["rendered_value"],
                "significant_digits": rounding.significant_digits,
                "rounding_mode": rounding.rounding_mode,
                "rounding_applied": lower_rendered["rounding_applied"]
                or upper_rendered["rounding_applied"],
                "unit": unit,
            }
            if has_single:
                warnings.append("SINGLE_VALUE_STANDARD_UNCERTAINTIES_NOT_PROPAGATED")
            warnings.append("NATURAL_VARIABILITY_ENVELOPE_NOT_FULL_UNCERTAINTY")
    return _bundle(
        "molar_mass",
        ast.canonical_formula,
        ast.ast_hash,
        ast.composition,
        snapshot,
        tuple(steps),
        result,
        tuple(warnings),
    )


def mass_amount(
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
    formula: str,
    value: Any,
    source_unit: str,
    target_unit: str,
    *,
    rounding: ChemistryRoundingSpec = DEFAULT_ROUNDING_SPEC,
) -> ChemistryResultBundle:
    quantity = quantity_decimal(value)
    mass = molar_mass(parser, snapshot, formula, rounding=rounding)
    mm = Decimal(mass.result["exact_internal_value"])
    try:
        with localcontext() as context:
            context.prec = CHEMISTRY_QUANTITY_LIMITS.context_precision
            if source_unit in {"g", "kg"} and target_unit in {"mol", "mmol"}:
                grams = quantity * (1000 if source_unit == "kg" else 1)
                result_value = grams / mm
                if target_unit == "mmol":
                    result_value *= 1000
            elif source_unit in {"mol", "mmol"} and target_unit in {"g", "kg"}:
                moles = quantity / (1000 if source_unit == "mmol" else 1)
                result_value = moles * mm
                if target_unit == "kg":
                    result_value /= 1000
            else:
                raise ChemistryCalculationError("conversion must be mass <-> amount")
    except DecimalException as error:
        raise ChemistryCalculationError("bounded Decimal calculation failed") from error
    rendered = render_significant(result_value, rounding)
    steps = (
        {"exact_input": _result_text(quantity), "source_unit": source_unit},
        {"exact_molar_mass": _result_text(mm), "unit": "g/mol"},
    )
    return _bundle(
        "mass_amount",
        mass.formula,
        mass.formula_ast_hash,
        (),
        snapshot,
        steps,
        {"value": rendered["exact_internal_value"], **rendered, "unit": target_unit},
        (
            "CONVENTIONAL_CLASSROOM_VALUE",
            "NOT_AN_EXACT_NATURAL_CONSTANT",
            "DISPLAY_ROUNDING_ONLY",
        ),
    )


def entity_amount(first: Any, *args: Any, **kwargs: Any) -> ChemistryResultBundle:
    """Execute v2 entity semantics while accepting the historical generic form."""

    if isinstance(first, FormulaParser):
        return _entity_amount_v2(first, *args, **kwargs)
    if len(args) != 4 or kwargs:
        raise ChemistryCalculationError("invalid entity_amount arguments")
    snapshot = first
    value, source_unit, target_unit, entity_type = args
    if entity_type not in {"atoms", "molecules", "formula_units"}:
        raise ChemistryCalculationError("unsupported legacy entity type")
    return _entity_amount_v2(
        FormulaParser({"H"}),
        snapshot,
        value,
        source_unit,
        target_unit,
        EntityAmountBasis.FORMULA_ENTITIES,
        formula=None,
        requested_display_label=entity_type,
    )


def _entity_amount_v2(
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
    value: Any,
    source_unit: str,
    target_unit: str,
    basis: EntityAmountBasis | str,
    *,
    formula: str | None,
    target_element: str | None = None,
    requested_display_label: str | None = None,
    rounding: ChemistryRoundingSpec = DEFAULT_ROUNDING_SPEC,
) -> ChemistryResultBundle:
    selected_basis = EntityAmountBasis(basis)
    direction = (
        EntityAmountDirection.ENTITIES_TO_MOLES
        if source_unit == "entities"
        else EntityAmountDirection.MOLES_TO_ENTITIES
    )
    quantity = quantity_decimal(
        value, integer=direction == EntityAmountDirection.ENTITIES_TO_MOLES
    )
    if formula is None:
        if selected_basis != EntityAmountBasis.FORMULA_ENTITIES:
            raise ChemistryCalculationError("selected entity basis requires a formula")
        ast = None
        counts: dict[str, int] = {}
    else:
        ast = parser.parse(formula)
        counts = {entry.symbol: entry.count for entry in ast.composition}
    if selected_basis == EntityAmountBasis.FORMULA_ENTITIES:
        multiplier = 1
    elif selected_basis == EntityAmountBasis.TOTAL_ATOMS_IN_FORMULA:
        multiplier = sum(counts.values())
    else:
        if target_element is None or target_element not in counts:
            raise ChemistryCalculationError("target element must occur in formula")
        multiplier = counts[target_element]
    constant = Decimal(snapshot.avogadro_constant)
    with localcontext() as context:
        context.prec = CHEMISTRY_QUANTITY_LIMITS.context_precision
        if (
            direction == EntityAmountDirection.MOLES_TO_ENTITIES
            and target_unit == "entities"
        ):
            moles = quantity / (1000 if source_unit == "mmol" else 1)
            result_value = moles * constant * multiplier
        elif direction == EntityAmountDirection.ENTITIES_TO_MOLES and target_unit in {
            "mol",
            "mmol",
        }:
            result_value = quantity / (constant * multiplier)
            if target_unit == "mmol":
                result_value *= 1000
        else:
            raise ChemistryCalculationError("conversion must be amount <-> entities")
    rendered = render_significant(result_value, rounding)
    warnings = ["DISPLAY_ROUNDING_ONLY"]
    if selected_basis == EntityAmountBasis.FORMULA_ENTITIES:
        warnings.append("CHEMICAL_ENTITY_CLASS_NOT_VALIDATED")
    return _bundle(
        "entity_amount",
        ast.canonical_formula if ast else None,
        ast.ast_hash if ast else None,
        ast.composition if ast else (),
        snapshot,
        (
            {
                "avogadro_constant": snapshot.avogadro_constant,
                "constant_exact": True,
                "basis": selected_basis.value,
                "stoichiometric_multiplier": multiplier,
                "direction": direction.value,
            },
        ),
        {
            "value": rendered["exact_internal_value"],
            **rendered,
            "unit": target_unit,
            "basis": selected_basis.value,
            "direction": direction.value,
            "formula": ast.canonical_formula if ast else None,
            "target_element": target_element,
            "requested_display_label": requested_display_label,
        },
        tuple(warnings),
    )


def _bundle(
    operation: str,
    formula: str | None,
    ast_hash: str | None,
    composition: Any,
    snapshot: ChemistryKnowledgeSnapshot,
    steps: tuple[dict[str, Any], ...],
    result: dict[str, Any],
    warnings: tuple[str, ...],
) -> ChemistryResultBundle:
    body = {
        "result_schema_version": CHEMISTRY_RESULT_SCHEMA_VERSION,
        "domain_version": CHEMISTRY_DOMAIN_VERSION,
        "domain_manifest_hash": snapshot.domain_manifest_hash,
        "operation": operation,
        "formula": formula,
        "formula_ast_hash": ast_hash,
        "composition_hash": content_hash(composition) if composition else None,
        "knowledge_snapshot_hash": snapshot.snapshot_hash,
        "fact_memory_snapshot_hash": snapshot.fact_memory_snapshot_hash,
        "claims_used": snapshot.claim_record_hashes,
        "claim_ids": snapshot.claim_ids,
        "claim_state_hashes": snapshot.claim_state_hashes,
        "evidence_ids": tuple(
            sorted({value for item in snapshot.bindings for value in item.evidence_ids})
        ),
        "evidence_hashes": snapshot.evidence_hashes,
        "source_ids": tuple(
            sorted({value for item in snapshot.bindings for value in item.source_ids})
        ),
        "source_hashes": snapshot.source_record_hashes,
        "source_state_hashes": snapshot.source_state_hashes,
        "derivation_hashes": snapshot.derivation_hashes,
        "calculation_steps": steps,
        "result": result,
        "warnings": warnings,
        "atomic_weight_policy": CHEMISTRY_ATOMIC_WEIGHT_POLICY,
        "formula_grammar_version": CHEMISTRY_FORMULA_GRAMMAR_VERSION,
        "calculation_policy_version": CHEMISTRY_CALCULATION_POLICY_VERSION,
        "rounding_policy": ROUNDING_POLICY,
        "rounding_policy_hash": content_hash(DEFAULT_ROUNDING_SPEC),
    }
    return ChemistryResultBundle(**body, result_hash=content_hash(body))


def verify_result(
    bundle: ChemistryResultBundle, snapshot: ChemistryKnowledgeSnapshot
) -> None:
    body = asdict(bundle)
    digest = body.pop("result_hash")
    if content_hash(body) != digest:
        raise ChemistryCalculationError("chemistry result hash mismatch")
    if bundle.knowledge_snapshot_hash != snapshot.snapshot_hash:
        raise ChemistryCalculationError("stale chemistry knowledge snapshot")
    if bundle.fact_memory_snapshot_hash != snapshot.fact_memory_snapshot_hash:
        raise ChemistryCalculationError("stale FactMemory snapshot")


def _weight(weights: dict[str, Any], symbol: str) -> Any:
    record = weights.get(symbol)
    if record is None:
        raise ChemistryCalculationError(f"unsupported calculation element: {symbol}")
    return record


def _weight_mode(mode: AtomicWeightMode | str) -> AtomicWeightMode:
    aliases = {
        "conventional": AtomicWeightMode.CONVENTIONAL_CLASSROOM,
        "interval": AtomicWeightMode.NATURAL_VARIABILITY_ENVELOPE,
    }
    text = str(mode)
    return aliases[text] if text in aliases else AtomicWeightMode(mode)


def _result_text(value: Decimal) -> str:
    try:
        return render_bounded_decimal(value, _decimal_limits(max_abs=False))
    except TrustedDecimalError as error:
        raise ChemistryCalculationError(str(error)) from error


def _decimal_limits(*, max_abs: bool) -> DecimalLimits:
    item = CHEMISTRY_QUANTITY_LIMITS
    return DecimalLimits(
        max_raw_chars=item.max_raw_chars,
        max_coefficient_digits=item.max_coefficient_digits,
        max_absolute_exponent=item.max_absolute_exponent,
        max_scale=item.max_scale,
        max_adjusted_exponent=item.max_adjusted_exponent,
        max_rendered_chars=item.max_rendered_chars,
        max_result_digits=item.max_result_digits,
        context_precision=item.context_precision,
        max_integer_bits=item.max_integer_bits,
        max_abs=Decimal(item.max_quantity_abs) if max_abs else None,
    )
