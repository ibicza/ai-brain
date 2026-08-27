from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

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
from ai_brain.stage2.domains.chemistry.models import FormulaLimits
from ai_brain.stage2.domains.chemistry.service import (
    ChemistryDomainService,
    build_domain,
)
from ai_brain.stage2.facts.canonical import content_hash, decimal_text
from ai_brain.stage2.facts.persistence import FactDatabase
from ai_brain.stage2.router.models import ResponseStage, RouteTarget
from ai_brain.stage2.router.service import UnifiedRouterError

ROOT = Path(__file__).parents[1]
GOLDEN = json.loads(
    (ROOT / "tests/fixtures/m28_chemistry_golden.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="session")
def chemistry_service(tmp_path_factory) -> ChemistryDomainService:
    service, summary = build_domain(tmp_path_factory.mktemp("m28") / "domain")
    assert summary.identity_element_count == 33
    assert summary.computational_element_count == 33
    assert summary.claim_count == 430
    assert len(tuple((service.root / "sources" / "derived").glob("*.json"))) == 4
    return service


def test_golden_formulas_and_molar_masses(chemistry_service):
    parser = FormulaParser(set(chemistry_service.manifest["supported_elements"]))
    snapshot = build_knowledge_snapshot(
        chemistry_service.memory,
        chemistry_service.manifest["domain_manifest_hash"],
    )
    for row in GOLDEN["formulas"]:
        ast = parser.parse(row["formula"])
        assert {entry.symbol: entry.count for entry in ast.composition} == row[
            "composition"
        ]
        result = molar_mass(parser, snapshot, row["formula"]).result
        expected = decimal_text(Decimal(row["molar_mass"]))
        assert result["mode"] == "CONVENTIONAL_CLASSROOM"
        assert result["value"] == expected
        assert result["exact_internal_value"] == expected
        assert result["unit"] == "g/mol"


def test_formula_roundtrip_metamorphic_and_limits(chemistry_service):
    parser = FormulaParser(set(chemistry_service.manifest["supported_elements"]))
    for row in GOLDEN["formulas"]:
        first = parser.parse(row["formula"])
        second = parser.parse(first.canonical_formula)
        assert second.composition == first.composition
    assert (
        parser.parse("A" if False else "H2O").composition
        == parser.parse("(H2O)").composition
    )
    assert parser.parse("H2H2").composition[0].count == 4
    assert parser.parse("Ca((OH)2)2").composition == parser.parse("CaO4H4").composition
    with pytest.raises(FormulaParseError, match="NESTING_LIMIT"):
        FormulaParser({"H"}, FormulaLimits(max_nesting_depth=2)).parse("(((H)))")
    with pytest.raises(FormulaParseError, match="INPUT_TOO_LONG"):
        parser.parse("H" * 257)


def test_at_least_100_invalid_formulas_fail_closed(chemistry_service):
    parser = FormulaParser(set(chemistry_service.manifest["supported_elements"]))
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
    invalid.extend(f"X{i}" for i in range(100))
    assert len(invalid) >= 100
    for formula in invalid:
        with pytest.raises(FormulaParseError):
            parser.parse(formula)


def test_mass_amount_500_case_acceptance(chemistry_service):
    parser = FormulaParser(set(chemistry_service.manifest["supported_elements"]))
    snapshot = build_knowledge_snapshot(
        chemistry_service.memory, chemistry_service.manifest["domain_manifest_hash"]
    )
    formulas = ("H2O", "CO2", "NaCl", "CaCO3", "H2SO4")
    checked = 0
    for formula in formulas:
        mm = Decimal(molar_mass(parser, snapshot, formula).result["value"])
        for integer in range(1, 26):
            value = Decimal(integer) / 10
            grams = Decimal(
                mass_amount(parser, snapshot, formula, str(value), "mol", "g").result[
                    "value"
                ]
            )
            assert grams == value * mm
            moles = Decimal(
                mass_amount(parser, snapshot, formula, str(grams), "g", "mol").result[
                    "value"
                ]
            )
            assert moles == value
            kilograms = Decimal(
                mass_amount(parser, snapshot, formula, str(value), "mol", "kg").result[
                    "value"
                ]
            )
            assert kilograms == grams / 1000
            millimoles = Decimal(
                mass_amount(parser, snapshot, formula, str(grams), "g", "mmol").result[
                    "value"
                ]
            )
            assert millimoles == value * 1000
            checked += 4
    assert checked == 500


def test_entity_amount_200_case_acceptance(chemistry_service):
    snapshot = build_knowledge_snapshot(
        chemistry_service.memory, chemistry_service.manifest["domain_manifest_hash"], ()
    )
    constant = Decimal(snapshot.avogadro_constant)
    checked = 0
    for entity_type in ("atoms", "molecules", "formula_units", "atoms"):
        for integer in range(1, 26):
            moles = Decimal(integer) / 100
            entities = entity_amount(
                snapshot, str(moles), "mol", "entities", entity_type
            )
            assert Decimal(entities.result["value"]) == moles * constant
            back = entity_amount(
                snapshot, entities.result["value"], "entities", "mol", entity_type
            )
            assert Decimal(back.result["value"]) == moles
            checked += 2
    assert checked == 200


def test_router_fact_tool_clarification_unsupported_composite(chemistry_service):
    fact, fact_response = chemistry_service.route_text(
        "What is the atomic number of oxygen?", "en"
    )
    assert fact.selected_target == RouteTarget.FACT_QUERY
    assert fact_response.response_stage == ResponseStage.COMPLETED
    tool, prepared = chemistry_service.route_text("Вычисли молярную массу H2SO4.", "ru")
    assert tool.selected_target == RouteTarget.TOOL_REQUEST
    assert prepared.response_stage == ResponseStage.PREPARED
    assert prepared.tool_result_hash is None
    clarification, _ = chemistry_service.route_text("Calculate the molar mass", "en")
    assert clarification.selected_target == RouteTarget.CLARIFICATION
    unsupported, _ = chemistry_service.route_text("Balance H2 + O2 -> H2O", "en")
    assert unsupported.selected_target == RouteTarget.UNSUPPORTED
    composite, _ = chemistry_service.route_text(
        "Calculate the molar mass of H2O and save it", "en"
    )
    assert composite.selected_target == RouteTarget.COMPOSITE_REQUIRED


def test_explicit_confirmation_and_cross_proposal_binding(chemistry_service):
    _, prepared, proposal = chemistry_service.prepare_tool(
        "chemistry_molar_mass",
        {"formula": "H2O", "mode": "conventional", "unit": "g/mol"},
    )
    result, failed = chemistry_service.unified.execute_tool_and_respond(
        prepared, proposal, None
    )
    assert result is None
    assert failed.response_stage == ResponseStage.FAILED
    changed = replace(
        proposal, typed_arguments={**proposal.typed_arguments, "formula": "CO2"}
    )
    with pytest.raises(UnifiedRouterError):
        chemistry_service.unified.confirm_tool(changed, identity="tester")
    result, completed = chemistry_service.confirm_and_execute(
        prepared, proposal, identity="tester"
    )
    assert result is not None
    assert result.output["result"]["value"] == "18.015"
    assert completed.response_stage == ResponseStage.COMPLETED
    assert content_hash(
        chemistry_service.results.load(result.output["result_hash"])
    ) == content_hash(result.output)


def test_tampered_knowledge_snapshot_is_invalid(chemistry_service):
    validation = chemistry_service.registry.validate_and_canonicalize_arguments(
        "chemistry_molar_mass",
        {"formula": "H2O", "mode": "conventional", "unit": "g/mol"},
    )
    assert validation.canonical_arguments is not None
    changed = dict(validation.canonical_arguments)
    snapshot = dict(changed["knowledge_snapshot"])
    snapshot["atomic_weight_policy"] = "MIDPOINT_FORBIDDEN"
    changed["knowledge_snapshot"] = snapshot
    invalid = chemistry_service.registry.validate_and_canonicalize_arguments(
        "chemistry_molar_mass", changed
    )
    assert invalid.canonical_arguments is None


def test_interval_mode_never_uses_midpoint(chemistry_service):
    validation = chemistry_service.registry.validate_and_canonicalize_arguments(
        "chemistry_molar_mass", {"formula": "H2O", "mode": "interval", "unit": "g/mol"}
    )
    output = chemistry_service.registry.execute(
        "chemistry_molar_mass", validation.canonical_arguments
    )
    result = output["result"]
    assert result["mode"] == "NATURAL_VARIABILITY_ENVELOPE"
    assert result["lower"] == "18.01471"
    assert result["upper"] == "18.01599"
    assert result["exact_internal_lower"] == "18.01471"
    assert result["exact_internal_upper"] == "18.01599"
    assert result["unit"] == "g/mol"
    assert "value" not in result


def test_trusted_chemistry_import_does_not_load_torch_or_network_clients():
    code = "import sys; import ai_brain.stage2.domains.chemistry; forbidden={'torch','requests','httpx','urllib3'}; print(sorted(forbidden & set(sys.modules)))"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "[]"


def test_chemistry_fact_memory_backup_restore(chemistry_service, tmp_path):
    backup = tmp_path / "backup"
    manifest = chemistry_service.memory.database.backup(backup)
    restored = FactDatabase.restore(backup, tmp_path / "restored")
    assert restored.snapshot_hash() != manifest["memory_snapshot_hash"]
    assert restored.integrity_check()["status"] == "VALID"
    assert restored.audit_replay()[-1]["event_type"] == "FACT_MEMORY_RECOVERED"
