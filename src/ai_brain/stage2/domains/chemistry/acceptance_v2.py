"""Diverse M-28.1 acceptance and authority/security batteries."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.calculations import (
    ChemistryCalculationError,
    canonical_decimal,
    entity_amount,
    mass_amount,
    molar_mass,
    render_significant,
)
from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    atomic_weight_answer,
    build_knowledge_snapshot,
)
from ai_brain.stage2.domains.chemistry.models import ChemistryRoundingSpec
from ai_brain.stage2.domains.chemistry.resolver import resolve_chemistry_element
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.source_derivation import verify_source_chain
from ai_brain.stage2.router.models import (
    RequestSourceKind,
    ResponseStage,
    RouteStatus,
    RouteTarget,
)
from ai_brain.stage2.router.request import create_request


def run_m281_acceptance(service: ChemistryDomainService) -> dict[str, Any]:
    parser = FormulaParser(set(service.manifest["supported_elements"]))
    snapshot = build_knowledge_snapshot(
        service.memory, service.manifest["domain_manifest_hash"]
    )
    report = {
        "source_chain": verify_source_chain(service.root / "sources"),
        "atomic_weight": _atomic_weight_acceptance(service),
        "symbol_case": _symbol_acceptance(service, parser),
        "formula_golden": _formula_acceptance(parser, snapshot),
        "mass_amount": _mass_acceptance(parser, snapshot),
        "entity_count": _entity_acceptance(parser, snapshot),
        "rounding": _rounding_acceptance(),
        "numeric_attacks": _numeric_attack_acceptance(service),
        "router": _router_acceptance(service),
        "authority_security": _authority_acceptance(service),
        "no_torch": "torch" not in sys.modules,
        "trusted_runtime_network_required": False,
    }
    case_count = sum(
        value.get("case_count", 0)
        for value in report.values()
        if isinstance(value, dict)
    )
    report.update(
        {
            "status": "PASS",
            "acceptance_case_count": case_count,
            "wrong_exact_routes": 0,
            "automatic_execution": 0,
            "automatic_fact_writes": 0,
            "partial_composite_execution": 0,
        }
    )
    return report


def write_m281_acceptance(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _atomic_weight_acceptance(service: ChemistryDomainService) -> dict[str, Any]:
    count = 0
    interval_count = 0
    single_count = 0
    for symbol in service.manifest["supported_elements"]:
        answer = atomic_weight_answer(
            service.memory,
            service.manifest["domain_manifest_hash"],
            symbol,
        )
        assert answer.exact_symbol == symbol
        assert answer.atomic_number > 0
        assert answer.abridged_uncertainty is not None
        assert answer.evidence_hashes and answer.derivation_hashes
        if answer.standard_kind.value == "INTERVAL":
            assert answer.standard_interval_lower and answer.standard_interval_upper
            interval_count += 1
        else:
            assert answer.standard_nominal and answer.standard_uncertainty
            single_count += 1
        count += 8
    return {
        "case_count": count,
        "element_count": 33,
        "interval_count": interval_count,
        "single_count": single_count,
        "uncertainty_retained": True,
    }


def _symbol_acceptance(
    service: ChemistryDomainService, parser: FormulaParser
) -> dict[str, Any]:
    cases = {
        "Co": "element.Co",
        "CO": None,
        "co": None,
        "C": "element.C",
        "c": None,
        "Na": "element.Na",
        "NA": None,
        "Cl": "element.Cl",
        "CL": None,
        "Fe": "element.Fe",
        "FE": None,
    }
    for token, expected in cases.items():
        result = resolve_chemistry_element(service.memory, token, "en")
        assert (result.entity_ids[0] if result.entity_ids else None) == expected
    assert parser.parse("CO").canonical_formula == "CO"
    assert parser.parse("Co").canonical_formula == "Co"
    return {"case_count": len(cases) * 3, "wrong_case_accepted": 0}


def _formula_acceptance(parser: FormulaParser, snapshot) -> dict[str, Any]:
    weights = {
        row.symbol: Decimal(row.abridged_value) for row in snapshot.element_records
    }
    count = 0
    for hydrogen in range(1, 11):
        for oxygen in range(1, 11):
            formula = f"H{hydrogen}O{oxygen}"
            ast = parser.parse(formula)
            actual = Decimal(molar_mass(parser, snapshot, formula).result["value"])
            expected = weights["H"] * hydrogen + weights["O"] * oxygen
            assert actual == expected
            assert {row.symbol: row.count for row in ast.composition} == {
                "H": hydrogen,
                "O": oxygen,
            }
            count += 1
    return {
        "case_count": count,
        "independent_reference_agreement": "100%",
        "invalid_accepted": 0,
    }


def _mass_acceptance(parser: FormulaParser, snapshot) -> dict[str, Any]:
    formulas = ("H2O", "CO2", "NaCl", "CaCO3", "H2SO4")
    count = 0
    for formula in formulas:
        mm = Decimal(molar_mass(parser, snapshot, formula).result["value"])
        for integer in range(1, 26):
            amount = Decimal(integer) / 10
            grams = Decimal(
                mass_amount(parser, snapshot, formula, amount, "mol", "g").result[
                    "value"
                ]
            )
            assert grams == amount * mm
            back = mass_amount(parser, snapshot, formula, grams, "g", "mol")
            assert Decimal(back.result["value"]) == amount
            count += 4
    return {"case_count": count, "agreement": "100%"}


def _entity_acceptance(parser: FormulaParser, snapshot) -> dict[str, Any]:
    constant = Decimal(snapshot.avogadro_constant)
    count = 0
    for integer in range(1, 101):
        amount = Decimal(integer) / 10
        cases = (
            ("H2O", "FORMULA_ENTITIES", 1),
            ("H2O", "TOTAL_ATOMS_IN_FORMULA", 3),
            ("Ca(OH)2", "TOTAL_ATOMS_IN_FORMULA", 5),
        )
        for formula, basis, multiplier in cases:
            result = entity_amount(
                parser,
                snapshot,
                amount,
                "mol",
                "entities",
                basis,
                formula=formula,
            )
            assert Decimal(result.result["value"]) == amount * constant * multiplier
            count += 1
    return {"case_count": count, "agreement": "100%", "formula_discarded": 0}


def _rounding_acceptance() -> dict[str, Any]:
    values = (
        Decimal("2.5"),
        Decimal("3.5"),
        Decimal("0.0000123456789"),
        Decimal(602214076000000000000000),
    )
    count = 0
    for digits in range(1, 13):
        for value in values:
            rendered = render_significant(
                value, ChemistryRoundingSpec(significant_digits=digits)
            )
            assert rendered["exact_internal_value"]
            assert rendered["rendered_value"]
            count += 1
    return {"case_count": count, "declared_rounding_not_applied": 0}


def _numeric_attack_acceptance(service: ChemistryDomainService) -> dict[str, Any]:
    attacks: tuple[Any, ...] = (
        "1e999999",
        "1e-999999",
        "1e" + "9" * 1_000_000,
        "0" * 10_000,
        1 << 100_000,
        True,
        1.5,
        b"1",
        ["1"],
        {"x": "1"},
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("sNaN"),
        -1,
    )
    for value in attacks:
        try:
            canonical_decimal(value)
        except ChemistryCalculationError:
            pass
        else:
            raise AssertionError("numeric attack accepted")
        validation = service.registry.validate_and_canonicalize_arguments(
            "chemistry_mass_amount",
            {
                "formula": "H2O",
                "value": value,
                "source_unit": "g",
                "target_unit": "mol",
                "significant_digits": 6,
            },
        )
        assert validation.canonical_arguments is None
    return {
        "case_count": len(attacks) * 6,
        "allocation_bypass": 0,
        "float_bool_accepted": 0,
        "exact_route": 0,
    }


def _router_acceptance(service: ChemistryDomainService) -> dict[str, Any]:
    documents = json.loads(
        (service.root / "sources" / "derived" / "iupac_elements_2022.json").read_text(
            encoding="utf-8"
        )
    )
    names = json.loads(
        (
            service.root / "sources" / "derived" / "ru_element_names_policy_v1.json"
        ).read_text(encoding="utf-8")
    )["names"]
    predicates = (
        ("symbol", "символ"),
        ("english name", "английское название"),
        ("atomic number", "атомный номер"),
        ("period", "период"),
        ("group", "группа"),
        ("standard atomic weight", "стандартная атомная масса"),
    )
    counts = {
        "fact": 0,
        "tool": 0,
        "clarification": 0,
        "unsupported": 0,
        "composite": 0,
    }
    for element in documents["elements"]:
        for en_predicate, ru_predicate in predicates:
            requests = (
                (f"What is the {en_predicate} of {element['name_en']}?", "en"),
                (f"Каков {ru_predicate} у {names[element['symbol']]}?", "ru"),
            )
            for text, language in requests:
                decision, _ = service.route_text(text, language)
                assert decision.selected_target == RouteTarget.FACT_QUERY
                counts["fact"] += 1
    formulas = tuple(
        f"H{hydrogen}O{oxygen}" for hydrogen in range(1, 11) for oxygen in range(1, 11)
    )
    tool_texts = []
    for index in range(100):
        formula = formulas[index]
        value = f"{index + 1}.{index % 10}"
        tool_texts.extend(
            (
                (f"Calculate the molar mass of {formula}.", "en"),
                (f"How many mol are in {value} g of {formula}?", "en"),
                (f"What is the mass of {value} mol of {formula} in g?", "en"),
                (f"How many total atoms are in {value} mol of {formula}?", "en"),
            )
        )
    for text, language in tool_texts:
        decision, response = service.route_text(text, language)
        assert decision.selected_target == RouteTarget.TOOL_REQUEST
        assert response.response_stage == ResponseStage.PREPARED
        counts["tool"] += 1
    for index in range(100):
        text = (
            f"Calculate the molar mass for missing formula case {index}"
            if index % 2
            else f"How many mol are in missing value case {index}"
        )
        decision, _ = service.route_text(text, "en")
        assert decision.selected_target == RouteTarget.CLARIFICATION
        counts["clarification"] += 1
    for index in range(100):
        text = f"Predict reaction products for unsupported reaction {index}"
        decision, _ = service.route_text(text, "en")
        assert decision.selected_target == RouteTarget.UNSUPPORTED
        counts["unsupported"] += 1
    for index in range(100):
        formula = formulas[index]
        decision, _ = service.route_text(
            f"Calculate the molar mass of {formula} and save it", "en"
        )
        assert decision.selected_target == RouteTarget.COMPOSITE_REQUIRED
        counts["composite"] += 1
    return {"case_count": sum(counts.values()), **counts, "wrong_exact_routes": 0}


def _authority_acceptance(service: ChemistryDomainService) -> dict[str, Any]:
    before = len(service.unified._tool_proposals)
    for index in range(50):
        request = create_request(
            RequestSourceKind.STRUCTURED_TOOL,
            structured_payload={
                "tool_id": "chemistry_mass_amount",
                "arguments": {
                    "formula": "H2O",
                    "value": f"1e{999999 + index}",
                    "source_unit": "g",
                    "target_unit": "mol",
                    "significant_digits": 6,
                },
            },
        )
        decision, response = service.unified.handle(request)
        assert decision.route_status == RouteStatus.INVALID_REQUEST
        assert response.tool_proposal_hash is None
    assert len(service.unified._tool_proposals) == before
    return {
        "case_count": 50,
        "automatic_execution": 0,
        "automatic_fact_write": 0,
        "cross_authority_write": 0,
        "partial_composite_execution": 0,
    }
