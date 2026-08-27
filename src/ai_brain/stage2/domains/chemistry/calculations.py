"""Exact Decimal chemistry calculations over an immutable knowledge snapshot."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser, verify_ast
from ai_brain.stage2.domains.chemistry.models import (
    ChemistryKnowledgeSnapshot,
    ChemistryResultBundle,
)
from ai_brain.stage2.domains.chemistry.version import (
    CHEMISTRY_ATOMIC_WEIGHT_POLICY,
    CHEMISTRY_CALCULATION_POLICY_VERSION,
    CHEMISTRY_DOMAIN_VERSION,
    CHEMISTRY_FORMULA_GRAMMAR_VERSION,
)
from ai_brain.stage2.facts.canonical import content_hash, decimal_text

MAX_ABS_QUANTITY = Decimal("1e100")
ROUNDING_POLICY = "DECIMAL_EXACT_INTERNAL_RENDER_6_SIGNIFICANT"


class ChemistryCalculationError(ValueError):
    pass


def canonical_decimal(
    value: Any, *, nonnegative: bool = True, integer: bool = False
) -> str:
    if isinstance(value, (bool, float)):
        raise ChemistryCalculationError(
            "quantity must be a Decimal string, never float"
        )
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ChemistryCalculationError("invalid decimal quantity") from error
    if not result.is_finite() or abs(result) > MAX_ABS_QUANTITY:
        raise ChemistryCalculationError(
            "quantity is non-finite or outside the bounded range"
        )
    if nonnegative and result < 0:
        raise ChemistryCalculationError("negative quantities are unsupported")
    if integer and result != result.to_integral_value():
        raise ChemistryCalculationError("entity count must be an integer")
    return decimal_text(result)


def formula_composition(
    parser: FormulaParser, snapshot: ChemistryKnowledgeSnapshot, formula: str
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
    )


def molar_mass(
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
    formula: str,
    *,
    mode: str = "conventional",
    unit: str = "g/mol",
) -> ChemistryResultBundle:
    ast = parser.parse(formula)
    weights = {record.symbol: record for record in snapshot.element_records}
    steps = []
    with localcontext() as context:
        context.prec = 80
        if mode == "conventional":
            total = Decimal(0)
            for entry in ast.composition:
                record = weights.get(entry.symbol)
                if record is None:
                    raise ChemistryCalculationError(
                        f"unsupported calculation element: {entry.symbol}"
                    )
                contribution = Decimal(record.conventional_value) * entry.count
                total += contribution
                steps.append(
                    {
                        "symbol": entry.symbol,
                        "count": entry.count,
                        "atomic_weight": record.conventional_value,
                        "contribution_g_per_mol": decimal_text(contribution),
                    }
                )
            value = total
            result: dict[str, Any] = {
                "mode": mode,
                "value": decimal_text(value),
                "unit": "g/mol",
            }
        elif mode == "interval":
            lower = Decimal(0)
            upper = Decimal(0)
            for entry in ast.composition:
                record = weights.get(entry.symbol)
                if record is None:
                    raise ChemistryCalculationError(
                        f"unsupported calculation element: {entry.symbol}"
                    )
                lo = Decimal(
                    record.interval_lower
                    or record.standard_value
                    or record.conventional_value
                )
                hi = Decimal(
                    record.interval_upper
                    or record.standard_value
                    or record.conventional_value
                )
                lower += lo * entry.count
                upper += hi * entry.count
                steps.append(
                    {
                        "symbol": entry.symbol,
                        "count": entry.count,
                        "lower": decimal_text(lo),
                        "upper": decimal_text(hi),
                    }
                )
            result = {
                "mode": mode,
                "lower": decimal_text(lower),
                "upper": decimal_text(upper),
                "unit": "g/mol",
            }
        else:
            raise ChemistryCalculationError(
                "molar-mass mode must be conventional or interval"
            )
        if unit == "kg/mol":
            for key in ("value", "lower", "upper"):
                if key in result:
                    result[key] = decimal_text(Decimal(result[key]) / Decimal(1000))
            result["unit"] = unit
        elif unit != "g/mol":
            raise ChemistryCalculationError("molar-mass unit must be g/mol or kg/mol")
    return _bundle(
        "molar_mass",
        ast.canonical_formula,
        ast.ast_hash,
        ast.composition,
        snapshot,
        tuple(steps),
        result,
    )


def mass_amount(
    parser: FormulaParser,
    snapshot: ChemistryKnowledgeSnapshot,
    formula: str,
    value: str,
    source_unit: str,
    target_unit: str,
) -> ChemistryResultBundle:
    quantity = Decimal(canonical_decimal(value))
    mass = molar_mass(parser, snapshot, formula)
    mm = Decimal(mass.result["value"])
    with localcontext() as context:
        context.prec = 80
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
    steps = (
        {"input": decimal_text(quantity), "source_unit": source_unit},
        {"molar_mass": decimal_text(mm), "unit": "g/mol"},
    )
    return _bundle(
        "mass_amount",
        mass.formula,
        mass.formula_ast_hash,
        (),
        snapshot,
        steps,
        {"value": decimal_text(result_value), "unit": target_unit},
    )


def entity_amount(
    snapshot: ChemistryKnowledgeSnapshot,
    value: str,
    source_unit: str,
    target_unit: str,
    entity_type: str,
) -> ChemistryResultBundle:
    if entity_type not in {"atoms", "molecules", "formula_units"}:
        raise ChemistryCalculationError("unsupported entity type")
    quantity = Decimal(canonical_decimal(value, integer=source_unit == "entities"))
    constant = Decimal(snapshot.avogadro_constant)
    with localcontext() as context:
        context.prec = 80
        if source_unit in {"mol", "mmol"} and target_unit == "entities":
            moles = quantity / (1000 if source_unit == "mmol" else 1)
            result_value = moles * constant
        elif source_unit == "entities" and target_unit in {"mol", "mmol"}:
            result_value = quantity / constant
            if target_unit == "mmol":
                result_value *= 1000
        else:
            raise ChemistryCalculationError("conversion must be amount <-> entities")
    return _bundle(
        "entity_amount",
        None,
        None,
        (),
        snapshot,
        ({"avogadro_constant": snapshot.avogadro_constant, "unit": "mol^-1"},),
        {
            "value": decimal_text(result_value),
            "unit": target_unit,
            "entity_type": entity_type,
        },
    )


def _bundle(
    operation: str,
    formula: str | None,
    ast_hash: str | None,
    composition: Any,
    snapshot: ChemistryKnowledgeSnapshot,
    steps: tuple[dict[str, Any], ...],
    result: dict[str, Any],
) -> ChemistryResultBundle:
    composition_hash = content_hash(composition) if composition else None
    body = {
        "domain_version": CHEMISTRY_DOMAIN_VERSION,
        "domain_manifest_hash": snapshot.domain_manifest_hash,
        "operation": operation,
        "formula": formula,
        "formula_ast_hash": ast_hash,
        "composition_hash": composition_hash,
        "knowledge_snapshot_hash": snapshot.snapshot_hash,
        "fact_memory_snapshot_hash": snapshot.fact_memory_snapshot_hash,
        "claims_used": snapshot.claim_hashes,
        "evidence_hashes": snapshot.evidence_hashes,
        "source_hashes": snapshot.source_hashes,
        "calculation_steps": steps,
        "result": result,
        "warnings": ("CONVENTIONAL_ATOMIC_WEIGHTS_ARE_NOT_EXACT_CONSTANTS",)
        if operation in {"molar_mass", "mass_amount"}
        else (),
        "atomic_weight_policy": CHEMISTRY_ATOMIC_WEIGHT_POLICY,
        "formula_grammar_version": CHEMISTRY_FORMULA_GRAMMAR_VERSION,
        "calculation_policy_version": CHEMISTRY_CALCULATION_POLICY_VERSION,
        "rounding_policy": ROUNDING_POLICY,
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
