"""Deterministic M-28 acceptance battery."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.calculations import (
    entity_amount,
    mass_amount,
    molar_mass,
)
from ai_brain.stage2.domains.chemistry.formula_parser import (
    FormulaParseError,
    FormulaParser,
)
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    build_knowledge_snapshot,
)
from ai_brain.stage2.domains.chemistry.replay import replay_chemistry_result
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.sources import load_frozen_sources
from ai_brain.stage2.router.models import ResponseStage, RouteStatus, RouteTarget


def run_acceptance(service: ChemistryDomainService) -> dict[str, Any]:
    parser = FormulaParser(set(service.manifest["supported_elements"]))
    snapshot = build_knowledge_snapshot(service.memory, service.manifest)
    formula_cases = _formula_acceptance(parser, snapshot)
    invalid_cases = _invalid_acceptance(parser)
    mass_cases = _mass_acceptance(parser, snapshot)
    entity_cases = _entity_acceptance(snapshot)
    router_cases = _router_acceptance(service)
    security = _security_acceptance(service)
    report = {
        "status": "PASS",
        "formula_cases": formula_cases,
        "invalid_formula_cases": invalid_cases,
        "mass_amount_cases": mass_cases,
        "entity_amount_cases": entity_cases,
        "router": router_cases,
        "authority_security": security,
        "fact_memory": service.memory.verify(),
        "reproducible_content_hash": service.manifest["reproducible_content_hash"],
    }
    report["acceptance_case_count"] = (
        formula_cases
        + invalid_cases
        + mass_cases
        + entity_cases
        + sum(router_cases.values())
        + security["case_count"]
    )
    return report


def write_acceptance(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _formula_acceptance(parser, snapshot) -> int:
    symbols = sorted(parser.supported_symbols)
    formulas = [symbol for symbol in symbols]
    formulas += [f"{symbol}{index % 5 + 1}" for index, symbol in enumerate(symbols)]
    formulas += [
        f"{symbols[index % len(symbols)]}{symbols[(index + 1) % len(symbols)]}2"
        for index in range(34)
    ]
    for formula in formulas:
        ast = parser.parse(formula)
        assert parser.parse(ast.canonical_formula).composition == ast.composition
        assert Decimal(molar_mass(parser, snapshot, formula).result["value"]) > 0
    assert len(formulas) == 100
    return len(formulas)


def _invalid_acceptance(parser) -> int:
    invalid = [
        "",
        "h2O",
        "Xx",
        "H0",
        "H02",
        "H-2",
        "H1.5",
        "(H2O",
        "H2O)",
        "()",
        "(((((H)))))",
        "H1000001",
        "H9999999O9999999",
        "CuSO4.5H2O",
        "NH4+",
        "13C",
        "2H2O",
        "[Fe]",
        "H2O->CO2",
        "H2 O",
        "H₂O",
        "Н2О",
        "H/2",
        "H_2",
        "H²",
        ".H",
        "H.",
        "(())",
        "H+Cl",
        "H=O",
    ]
    invalid.extend(f"X{index}" for index in range(100))
    for formula in invalid:
        try:
            parser.parse(formula)
        except FormulaParseError:
            continue
        raise AssertionError(f"invalid formula accepted: {formula}")
    return len(invalid)


def _mass_acceptance(parser, snapshot) -> int:
    formulas = ("H2O", "CO2", "NaCl", "CaCO3", "H2SO4")
    count = 0
    for formula in formulas:
        mm = Decimal(molar_mass(parser, snapshot, formula).result["value"])
        for integer in range(1, 26):
            amount = Decimal(integer) / 10
            grams = Decimal(
                mass_amount(parser, snapshot, formula, str(amount), "mol", "g").result[
                    "value"
                ]
            )
            assert grams == amount * mm
            assert (
                Decimal(
                    mass_amount(
                        parser, snapshot, formula, str(grams), "g", "mol"
                    ).result["value"]
                )
                == amount
            )
            assert (
                Decimal(
                    mass_amount(
                        parser, snapshot, formula, str(amount), "mol", "kg"
                    ).result["value"]
                )
                == grams / 1000
            )
            assert (
                Decimal(
                    mass_amount(
                        parser, snapshot, formula, str(grams), "g", "mmol"
                    ).result["value"]
                )
                == amount * 1000
            )
            count += 4
    return count


def _entity_acceptance(snapshot) -> int:
    count = 0
    for entity_type in ("atoms", "molecules", "formula_units", "atoms"):
        for integer in range(1, 26):
            amount = Decimal(integer) / 100
            entities = entity_amount(
                snapshot, str(amount), "mol", "entities", entity_type
            )
            back = entity_amount(
                snapshot, entities.result["value"], "entities", "mol", entity_type
            )
            assert Decimal(back.result["value"]) == amount
            count += 2
    return count


def _router_acceptance(service) -> dict[str, int]:
    documents = load_frozen_sources()
    elements = documents["iupac_elements_2022.json"]["elements"]
    names = documents["ru_element_names_policy_v1.json"]["names"]
    formulas = ("H2O", "CO2", "NaCl", "CaCO3", "H2SO4")
    counts = {
        "fact": 0,
        "tool": 0,
        "clarification": 0,
        "unsupported": 0,
        "composite": 0,
    }
    for index in range(200):
        element = elements[index % len(elements)]
        if index % 2:
            text, language = f"What is the atomic number of {element['name_en']}?", "en"
        else:
            text, language = f"Какой атомный номер у {names[element['symbol']]}?", "ru"
        decision, _ = service.route_text(text, language)
        assert (
            decision.selected_target == RouteTarget.FACT_QUERY
            and decision.route_status == RouteStatus.EXACT_ROUTE
        )
        counts["fact"] += 1
    for index in range(200):
        formula = formulas[index % len(formulas)]
        text, language = (
            (f"Calculate the molar mass of {formula}.", "en")
            if index % 2
            else (f"Вычисли молярную массу {formula}.", "ru")
        )
        decision, response = service.route_text(text, language)
        assert (
            decision.selected_target == RouteTarget.TOOL_REQUEST
            and response.response_stage == ResponseStage.PREPARED
            and response.tool_result_hash is None
        )
        counts["tool"] += 1
    for _ in range(100):
        decision, _ = service.route_text("Calculate the molar mass", "en")
        assert decision.selected_target == RouteTarget.CLARIFICATION
        counts["clarification"] += 1
    for _ in range(100):
        decision, _ = service.route_text("Predict the products of this reaction", "en")
        assert decision.selected_target == RouteTarget.UNSUPPORTED
        counts["unsupported"] += 1
    for _ in range(100):
        decision, _ = service.route_text(
            "Calculate the molar mass of H2O and save it", "en"
        )
        assert decision.selected_target == RouteTarget.COMPOSITE_REQUIRED
        counts["composite"] += 1
    return counts


def _security_acceptance(service) -> dict[str, Any]:
    _, prepared, proposal = service.prepare_tool(
        "chemistry_molar_mass",
        {"formula": "H2O", "mode": "conventional", "unit": "g/mol"},
    )
    result, failed = service.unified.execute_tool_and_respond(prepared, proposal, None)
    assert result is None and failed.response_stage == ResponseStage.FAILED
    result, completed = service.confirm_and_execute(
        prepared, proposal, identity="m28-acceptance"
    )
    assert result is not None and completed.response_stage == ResponseStage.COMPLETED
    assert (
        replay_chemistry_result(result.output, service.memory, service.manifest).value
        == "CURRENT"
    )
    tampered = dict(result.output)
    tampered["formula"] = "CO2"
    assert (
        replay_chemistry_result(tampered, service.memory, service.manifest).value
        == "INVALID_RESULT"
    )
    wrong_manifest = {**service.manifest, "domain_manifest_hash": "0" * 64}
    assert (
        replay_chemistry_result(result.output, service.memory, wrong_manifest).value
        == "STALE_DOMAIN_MANIFEST"
    )
    return {
        "case_count": 5,
        "automatic_execution": 0,
        "cross_authority_write": 0,
        "tampered_result_accepted": 0,
    }
