from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from chemistry_reference_v2 import (
    generated_formula_cases,
    load_abridged_weights,
    reference_molar_mass,
)

from ai_brain.stage2.domains.chemistry.calculations import (
    ChemistryCalculationError,
    canonical_decimal,
    entity_amount,
    molar_mass,
    render_significant,
)
from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    ChemistryKnowledgeError,
    atomic_weight_answer,
    build_knowledge_snapshot,
)
from ai_brain.stage2.domains.chemistry.models import (
    AtomicWeightKind,
    ChemistryReplayStatus,
    ChemistryRoundingSpec,
)
from ai_brain.stage2.domains.chemistry.replay import replay_chemistry_result
from ai_brain.stage2.domains.chemistry.resolver import resolve_chemistry_element
from ai_brain.stage2.domains.chemistry.service import (
    ChemistryDomainService,
    build_domain,
)
from ai_brain.stage2.domains.chemistry.source_derivation import verify_source_chain
from ai_brain.stage2.domains.chemistry.version import (
    CHEMISTRY_DOMAIN_SCHEMA_VERSION,
    CHEMISTRY_DOMAIN_VERSION,
)
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    EvidenceRelation,
    ExtractionMethod,
    ProposalSource,
    QueryStatus,
    SourceKind,
)
from ai_brain.stage2.facts.values import FactValue
from ai_brain.stage2.router.models import RouteStatus, RouteTarget


@pytest.fixture(scope="session")
def m281_pack(tmp_path_factory) -> ChemistryDomainService:
    service, summary = build_domain(tmp_path_factory.mktemp("m281") / "domain")
    assert summary.claim_count == 430
    assert summary.evidence_count == 100
    assert summary.source_count == 9
    return service


def _copy_service(
    service: ChemistryDomainService, target: Path
) -> ChemistryDomainService:
    shutil.copytree(service.root, target)
    return ChemistryDomainService.open(target)


def _execute_water(service: ChemistryDomainService):
    _, prepared, proposal = service.prepare_tool(
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "CONVENTIONAL_CLASSROOM",
            "unit": "g/mol",
            "significant_digits": 6,
        },
    )
    result, _ = service.confirm_and_execute(
        prepared, proposal, identity="m281-test-user"
    )
    assert result is not None
    return result.output, proposal


def test_v2_manifest_and_source_chain(m281_pack) -> None:
    assert m281_pack.manifest["domain_version"] == CHEMISTRY_DOMAIN_VERSION == "1.1.0"
    assert (
        m281_pack.manifest["domain_schema_version"]
        == CHEMISTRY_DOMAIN_SCHEMA_VERSION
        == 2
    )
    verification = verify_source_chain(m281_pack.root / "sources")
    assert verification == {
        "status": "VERIFIED",
        "official_count": 5,
        "derived_count": 4,
        "derivation_count": 4,
        "source_chain_hash": m281_pack.manifest["source_chain"]["source_chain_hash"],
    }
    assert m281_pack.manifest["bipm_baseline"]["version"] == "4.01"
    assert m281_pack.manifest["bipm_baseline"]["publication_date"] == "2026-06-04"


def test_independent_reference_agrees_for_golden_and_generated_formulas(
    m281_pack,
) -> None:
    source_root = m281_pack.root / "sources"
    weights = load_abridged_weights(
        source_root / "derived" / "ciaaw_atomic_weights_2024.json"
    )
    golden_path = Path("tests/fixtures/m28_chemistry_golden.json")
    golden = json.loads(golden_path.read_text(encoding="utf-8"))["formulas"]
    cases = [
        (row["formula"], {key: int(value) for key, value in row["composition"].items()})
        for row in golden
    ]
    cases.extend(generated_formula_cases())
    assert len(golden) == 30
    assert len(cases) == 130

    parser = FormulaParser(set(m281_pack.manifest["supported_elements"]))
    snapshot = build_knowledge_snapshot(
        m281_pack.memory,
        m281_pack.manifest["domain_manifest_hash"],
        tuple(weights),
    )
    for formula, composition in cases:
        expected = reference_molar_mass(composition, weights)
        actual = Decimal(
            molar_mass(
                parser,
                snapshot,
                formula,
                mode="CONVENTIONAL_CLASSROOM",
            ).result["exact_internal_value"]
        )
        assert actual == expected, formula


def test_derived_sources_are_not_official_primary(m281_pack) -> None:
    chain = m281_pack.manifest["source_chain"]
    for row in chain["derived_extracts"]:
        state = m281_pack.memory.get_source_state(row["source_id"])
        assert state.record.source_kind == SourceKind.DETERMINISTIC_DERIVED_EXTRACT
        assert (
            state.record.license_metadata["derivation_hash"]
            in m281_pack.manifest["source_derivation_hashes"]
        )


def test_atomic_weight_v2_all_elements_and_uncertainty(m281_pack) -> None:
    snapshot = build_knowledge_snapshot(
        m281_pack.memory, m281_pack.manifest["domain_manifest_hash"]
    )
    assert len(snapshot.element_records) == 33
    assert all(row.abridged_uncertainty is not None for row in snapshot.element_records)
    intervals = [
        row
        for row in snapshot.element_records
        if row.standard_kind == AtomicWeightKind.INTERVAL
    ]
    singles = [
        row
        for row in snapshot.element_records
        if row.standard_kind == AtomicWeightKind.SINGLE
    ]
    assert len(intervals) == 12
    assert len(singles) == 21
    assert all(row.standard_uncertainty is not None for row in singles)
    assert all(row.standard_interval_lower is not None for row in intervals)


def test_typed_atomic_weight_interval_and_single(m281_pack) -> None:
    carbon = atomic_weight_answer(
        m281_pack.memory, m281_pack.manifest["domain_manifest_hash"], "C"
    )
    assert carbon.standard_kind == AtomicWeightKind.INTERVAL
    assert (carbon.standard_interval_lower, carbon.standard_interval_upper) == (
        "12.0096",
        "12.0116",
    )
    iron = atomic_weight_answer(
        m281_pack.memory, m281_pack.manifest["domain_manifest_hash"], "Fe"
    )
    assert iron.standard_nominal == "55.845"
    assert iron.standard_uncertainty == "0.002"
    assert iron.derivation_hashes


@pytest.mark.parametrize(
    ("token", "expected"),
    (
        ("Co", "element.Co"),
        ("CO", None),
        ("co", None),
        ("C", "element.C"),
        ("c", None),
        ("Na", "element.Na"),
        ("NA", None),
        ("Cl", "element.Cl"),
        ("CL", None),
        ("Fe", "element.Fe"),
        ("FE", None),
    ),
)
def test_exact_case_symbol_resolution(m281_pack, token, expected) -> None:
    resolution = resolve_chemistry_element(m281_pack.memory, token, "en")
    assert (resolution.entity_ids[0] if resolution.entity_ids else None) == expected


def test_symbol_policy_in_fact_and_formula_contexts(m281_pack) -> None:
    decision, _ = m281_pack.route_text("What is the atomic number of Co?", "en")
    assert decision.selected_target == RouteTarget.FACT_QUERY
    decision, _ = m281_pack.route_text("What is the atomic number of CO?", "en")
    assert decision.selected_target == RouteTarget.CLARIFICATION
    parser = FormulaParser(set(m281_pack.manifest["supported_elements"]))
    assert parser.parse("CO").canonical_formula == "CO"
    assert parser.parse("Co").canonical_formula == "Co"
    with pytest.raises(ValueError):
        parser.parse("co")


class _ExplosiveString:
    called = False

    def __str__(self) -> str:
        self.called = True
        raise AssertionError("must not be called")


@pytest.mark.parametrize(
    "value",
    (
        "1e999999",
        "1e-999999",
        "1e" + "9" * 1_000_000,
        "0" * 10_000,
        1 << 100_000,
        True,
        1.5,
        b"1",
        ["1"],
        {"value": "1"},
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("sNaN"),
        -1,
    ),
    ids=(
        "huge-positive-exponent",
        "huge-negative-exponent",
        "million-digit-exponent",
        "long-zero-sequence",
        "huge-integer",
        "bool",
        "float",
        "bytes",
        "list",
        "dict",
        "nan",
        "infinity",
        "snan",
        "negative",
    ),
)
def test_numeric_attack_battery_direct_and_structured(m281_pack, value) -> None:
    with pytest.raises(ChemistryCalculationError):
        canonical_decimal(value)
    validation = m281_pack.registry.validate_and_canonicalize_arguments(
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


def test_numeric_parser_never_invokes_arbitrary_str(m281_pack) -> None:
    value = _ExplosiveString()
    with pytest.raises(ChemistryCalculationError):
        canonical_decimal(value)
    assert not value.called


def test_controlled_exponent_attack_gets_no_route_or_proposal(m281_pack) -> None:
    decision, response = m281_pack.route_text(
        "How many mol are in 1e999999 g of H2O?", "en"
    )
    assert decision.route_status != RouteStatus.EXACT_ROUTE
    assert response.tool_proposal_hash is None


def test_entity_amount_semantics_300_cases(m281_pack) -> None:
    parser = FormulaParser(set(m281_pack.manifest["supported_elements"]))
    snapshot = build_knowledge_snapshot(
        m281_pack.memory,
        m281_pack.manifest["domain_manifest_hash"],
        ("H", "O", "Ca"),
    )
    constant = Decimal(snapshot.avogadro_constant)
    checked = 0
    for integer in range(1, 101):
        amount = Decimal(integer) / 10
        formula_entities = entity_amount(
            parser,
            snapshot,
            str(amount),
            "mol",
            "entities",
            "FORMULA_ENTITIES",
            formula="H2O",
        )
        total_atoms = entity_amount(
            parser,
            snapshot,
            str(amount),
            "mol",
            "entities",
            "TOTAL_ATOMS_IN_FORMULA",
            formula="H2O",
        )
        calcium_hydroxide = entity_amount(
            parser,
            snapshot,
            str(amount),
            "mol",
            "entities",
            "TOTAL_ATOMS_IN_FORMULA",
            formula="Ca(OH)2",
        )
        assert Decimal(formula_entities.result["value"]) == amount * constant
        assert Decimal(total_atoms.result["value"]) == amount * constant * 3
        assert Decimal(calcium_hydroxide.result["value"]) == amount * constant * 5
        checked += 3
    assert checked == 300


def test_entity_controlled_language_preserves_formula(m281_pack) -> None:
    decision, response = m281_pack.route_text(
        "How many total atoms are in 0.5 mol of H2O?", "en"
    )
    assert decision.selected_target == RouteTarget.TOOL_REQUEST
    assert response.tool_proposal_hash is not None
    payload = decision.parser_evidence["payload"]["arguments"]
    assert payload["formula"] == "H2O"
    assert payload["basis"] == "TOTAL_ATOMS_IN_FORMULA"
    missing, response = m281_pack.route_text(
        "How many total atoms are in 0.5 mol?", "en"
    )
    assert missing.selected_target == RouteTarget.CLARIFICATION
    assert response.tool_proposal_hash is None


def test_significant_figure_rounding_1_through_12() -> None:
    exact = Decimal("1.234567890123456")
    for digits in range(1, 13):
        rendered = render_significant(
            exact, ChemistryRoundingSpec(significant_digits=digits)
        )
        assert rendered["exact_internal_value"] == "1.234567890123456"
        assert rendered["significant_digits"] == digits
    assert (
        render_significant(Decimal("2.5"), ChemistryRoundingSpec(significant_digits=1))[
            "rendered_value"
        ]
        == "2"
    )
    assert (
        render_significant(Decimal("3.5"), ChemistryRoundingSpec(significant_digits=1))[
            "rendered_value"
        ]
        == "4"
    )


def test_source_retraction_blocks_new_snapshot_and_replay(m281_pack, tmp_path) -> None:
    service = _copy_service(m281_pack, tmp_path / "source-retract")
    output, _ = _execute_water(service)
    source_id = next(value for value in output["source_ids"] if "ciaaw" in value)
    service.memory.retract_source(
        source_id,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="M-28.1 source retraction test",
    )
    assert (
        replay_chemistry_result(output, service.memory, service.manifest)
        == ChemistryReplayStatus.RETRACTED_SOURCE
    )
    with pytest.raises(ChemistryKnowledgeError):
        build_knowledge_snapshot(
            service.memory, service.manifest["domain_manifest_hash"], ("H",)
        )


def test_claim_retraction_blocks_new_snapshot_and_replay(m281_pack, tmp_path) -> None:
    service = _copy_service(m281_pack, tmp_path / "claim-retract")
    output, _ = _execute_water(service)
    claim_id = next(
        value
        for value in output["claim_ids"]
        if service.memory.get_claim_record(value).predicate_id
        == "conventional_atomic_weight"
    )
    service.memory.retract_claim(
        claim_id,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="M-28.1 claim retraction test",
    )
    assert (
        replay_chemistry_result(output, service.memory, service.manifest)
        == ChemistryReplayStatus.RETRACTED_ELEMENT_CLAIM
    )
    with pytest.raises(ChemistryKnowledgeError):
        build_knowledge_snapshot(
            service.memory, service.manifest["domain_manifest_hash"], ("H", "O")
        )


def test_contradicting_evidence_blocks_snapshot_and_replay(m281_pack, tmp_path) -> None:
    service = _copy_service(m281_pack, tmp_path / "contradiction")
    output, _ = _execute_water(service)
    claim_id = next(
        value
        for value in output["claim_ids"]
        if service.memory.get_claim_record(value).predicate_id
        == "conventional_atomic_weight"
    )
    support_id = service.memory.get_claim_state(claim_id).supporting_evidence_ids[0]
    support = service.memory.get_evidence_record(support_id)
    contradiction = service.memory.add_evidence(
        source_id=support.source_id,
        relation=EvidenceRelation.CONTRADICTS,
        location_kind=support.location_kind,
        location=support.location,
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence="1",
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
        approved=True,
        evidence_id="m281_contradiction",
    )
    service.memory.attach_reviewed_evidence_to_claim(
        claim_id,
        contradiction.evidence_id,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
    )
    assert (
        replay_chemistry_result(output, service.memory, service.manifest)
        == ChemistryReplayStatus.CONTRADICTING_EVIDENCE
    )
    with pytest.raises(ChemistryKnowledgeError):
        build_knowledge_snapshot(
            service.memory, service.manifest["domain_manifest_hash"], ("H", "O")
        )


def test_superseded_claim_uses_reviewed_replacement(m281_pack, tmp_path) -> None:
    service = _copy_service(m281_pack, tmp_path / "supersession")
    snapshot = build_knowledge_snapshot(
        service.memory, service.manifest["domain_manifest_hash"], ("Fe",)
    )
    old_claim = next(
        value
        for value in snapshot.claim_ids
        if service.memory.get_claim_record(value).predicate_id
        == "conventional_atomic_weight"
    )
    old = service.memory.get_claim_record(old_claim)
    evidence_id = service.memory.get_claim_state(old_claim).supporting_evidence_ids[0]
    proposal = service.memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id=old.subject_entity_id,
        predicate_id=old.predicate_id,
        object_value=FactValue.create("DECIMAL", "55.846"),
        source_ids=(service.memory.get_evidence_record(evidence_id).source_id,),
        evidence_ids=(evidence_id,),
        proposal_id="m281_replacement",
    )
    service.memory.prepare_for_review(
        proposal.proposal_id,
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    approval = service.memory.approve_proposal(
        proposal.proposal_id,
        reviewer_identity="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    replacement = service.memory.commit_proposal(
        proposal.proposal_id, approval.approval_id
    )
    service.memory.supersede_claim(
        old_claim,
        replacement.claim_id,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="reviewed replacement",
    )
    current = build_knowledge_snapshot(
        service.memory, service.manifest["domain_manifest_hash"], ("Fe",)
    )
    assert current.element_records[0].abridged_value == "55.846"
    assert old_claim not in current.claim_ids


def test_moved_pack_uses_bundled_sources(m281_pack, tmp_path) -> None:
    moved = tmp_path / "moved" / "chemistry"
    service = _copy_service(m281_pack, moved)
    assert (
        service.verify()["reproducible_content_hash"]
        == m281_pack.manifest["reproducible_content_hash"]
    )
    derived = next((moved / "sources" / "derived").glob("*.json"))
    derived.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ChemistryDomainService.open(moved)


def test_standard_weight_controlled_query_is_not_no_fact(m281_pack) -> None:
    decision, _ = m281_pack.route_text(
        "What is the standard atomic weight of carbon?", "en"
    )
    payload = decision.parser_evidence["payload"]
    answer = m281_pack.memory.query(m281_pack.memory.make_query(**payload))
    assert answer.answer_status == QueryStatus.EXACT_SINGLE
    assert answer.claims[0].value.value == "[12.0096,12.0116]"


def test_snapshot_and_result_hashes_cover_v2_state(m281_pack) -> None:
    snapshot = build_knowledge_snapshot(
        m281_pack.memory, m281_pack.manifest["domain_manifest_hash"], ("H", "O")
    )
    assert snapshot.claim_state_hashes
    assert snapshot.source_state_hashes
    assert snapshot.derivation_hashes
    output, _ = _execute_water(m281_pack)
    tampered = dict(output)
    tampered["rounding_policy_hash"] = "0" * 64
    assert (
        replay_chemistry_result(tampered, m281_pack.memory, m281_pack.manifest)
        == ChemistryReplayStatus.INVALID_RESULT
    )


def test_old_v1_pack_is_rebuild_required() -> None:
    old_root = Path("artifacts/domains/chemistry/m28")
    if not old_root.exists():
        pytest.skip("historical M-28 pack is not present")
    with pytest.raises(ValueError, match="REBUILD_REQUIRED_FROM_FROZEN_SOURCES"):
        ChemistryDomainService.open(old_root)
