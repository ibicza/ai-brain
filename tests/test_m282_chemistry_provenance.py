from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ai_brain.stage2.domains.chemistry.acceptance_v3 import _mutation_battery
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    ATOMIC_WEIGHTS,
    AVOGADRO,
    ChemistryKnowledgeError,
    build_knowledge_snapshot,
    validate_fact_provenance,
)
from ai_brain.stage2.domains.chemistry.models import ChemistryReplayStatus
from ai_brain.stage2.domains.chemistry.provenance import resolve_source_derivation
from ai_brain.stage2.domains.chemistry.replay import replay_chemistry_result
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.source_derivation import verify_source_chain
from ai_brain.stage2.facts.models import ActorIdentityType, SourceStatus


@pytest.fixture(scope="session")
def m282_pack(tmp_path_factory) -> ChemistryDomainService:
    target = tmp_path_factory.mktemp("m282-current") / "domain"
    shutil.copytree(Path("artifacts/domains/chemistry/m29"), target)
    return ChemistryDomainService.open(target)


def _copy_service(
    service: ChemistryDomainService, target: Path
) -> ChemistryDomainService:
    shutil.copytree(service.root, target)
    return ChemistryDomainService.open(target)


def _execute(service: ChemistryDomainService, tool_id: str, arguments: dict):
    _, prepared, proposal = service.prepare_tool(tool_id, arguments)
    result, _ = service.confirm_and_execute(prepared, proposal, identity="m282-test")
    assert result is not None
    return result.output


def test_source_chain_v3_categories_and_methods(m282_pack) -> None:
    verification = verify_source_chain(m282_pack.root / "sources")
    assert verification["official_snapshot_count"] == 4
    assert verification["local_policy_snapshot_count"] == 1
    assert verification["derived_extract_count"] == 4
    assert verification["deterministic_derivation_count"] == 1
    assert verification["manual_mapping_derivation_count"] == 2
    assert verification["policy_transformation_count"] == 1
    assert verification["field_evidence_count"] == 534


def test_every_derived_source_resolves_exactly(m282_pack) -> None:
    chain = m282_pack.manifest["source_chain"]
    for row in chain["derived_extracts"]:
        source = m282_pack.memory.get_source_record(row["source_id"])
        resolution = resolve_source_derivation(
            source,
            chain,
            m282_pack.memory,
            source_record_bindings=tuple(m282_pack.manifest["source_record_bindings"]),
        )
        assert source.snapshot_hash == row["sha256"]
        assert resolution.derivation.derived_file_byte_sha256 == row["sha256"]
        assert (
            resolution.derivation.derived_canonical_content_hash
            == row["canonical_content_hash"]
        )
        assert resolution.field_mapping_evidence_hashes


def test_borrowed_derivation_mutation_battery_rejects_all(m282_pack) -> None:
    report = _mutation_battery(m282_pack)
    assert report["case_count"] == 101
    assert report["accepted_count"] == 0


def test_manual_mappings_are_human_approved_and_not_deterministic(m282_pack) -> None:
    chain = m282_pack.manifest["source_chain"]
    approvals = {
        row["approval_id"]: row["record"] for row in chain["manual_mapping_approvals"]
    }
    manual = [
        row["record"]
        for row in chain["derivations"]
        if row["record"]["derivation_method"] == "REVIEWED_MANUAL_MAPPING"
    ]
    assert len(manual) == 2
    for record in manual:
        approval = approvals[record["manual_mapping_approval_id"]]
        assert approval["reviewer_identity_type"] == "HUMAN"
        assert approval["reviewer_identity"]
        assert approval["review_decision"] == "APPROVED"
        assert (
            record["extractor_reviewer_identity"]
            != "m282-deterministic-source-extractor"
        )


def test_dependency_minimization_in_tool_results(m282_pack) -> None:
    molar = _execute(
        m282_pack,
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "CONVENTIONAL_CLASSROOM",
            "unit": "g/mol",
            "significant_digits": 6,
        },
    )
    entities = _execute(
        m282_pack,
        "chemistry_entity_amount",
        {
            "value": "1",
            "source_unit": "mol",
            "target_unit": "entities",
            "basis": "FORMULA_ENTITIES",
            "formula": "H2O",
            "target_element": None,
            "requested_display_label": None,
            "significant_digits": 6,
        },
    )
    assert "local_ru_element_names_policy_v1" not in molar["upstream_source_ids"]
    assert "official_bipm_si_brochure_4_01" not in molar["upstream_source_ids"]
    assert entities["upstream_source_ids"] == ("official_bipm_si_brochure_4_01",)
    assert not any("ciaaw" in item for item in entities["upstream_source_ids"])


@pytest.mark.parametrize("status", (SourceStatus.RETRACTED, SourceStatus.UNAVAILABLE))
def test_bipm_state_blocks_entity_but_not_molar_mass(
    m282_pack, tmp_path, status
) -> None:
    service = _copy_service(m282_pack, tmp_path / status.value.lower())
    molar = _execute(
        service,
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "CONVENTIONAL_CLASSROOM",
            "unit": "g/mol",
            "significant_digits": 6,
        },
    )
    service.memory.set_source_status(
        "official_bipm_si_brochure_4_01",
        status=status,
        actor="m282-test-reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="M-28.2 upstream status test",
    )
    assert replay_chemistry_result(molar, service.memory, service.manifest) == (
        ChemistryReplayStatus.CURRENT
    )
    with pytest.raises(ChemistryKnowledgeError):
        build_knowledge_snapshot(
            service.memory, service.manifest, (), requirements=(AVOGADRO,)
        )


def test_ciaaw_retraction_has_typed_replay_status(m282_pack, tmp_path) -> None:
    service = _copy_service(m282_pack, tmp_path / "ciaaw-retracted")
    output = _execute(
        service,
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "CONVENTIONAL_CLASSROOM",
            "unit": "g/mol",
            "significant_digits": 6,
        },
    )
    service.memory.retract_source(
        "official_ciaaw_standard_weights_2024",
        actor="m282-test-reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="M-28.2 CIAAW retraction test",
    )
    assert replay_chemistry_result(output, service.memory, service.manifest) == (
        ChemistryReplayStatus.RETRACTED_UPSTREAM_SOURCE
    )
    with pytest.raises(ChemistryKnowledgeError):
        build_knowledge_snapshot(
            service.memory,
            service.manifest,
            ("H", "O"),
            requirements=(ATOMIC_WEIGHTS,),
        )


def test_ru_policy_retraction_only_blocks_ru_name(m282_pack, tmp_path) -> None:
    service = _copy_service(m282_pack, tmp_path / "ru-policy")
    service.memory.retract_source(
        "local_ru_element_names_policy_v1",
        actor="m282-test-reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="M-28.2 RU policy retraction test",
    )
    with pytest.raises(ChemistryKnowledgeError):
        validate_fact_provenance(
            service.memory, service.manifest, "element.Fe", "element_name_ru"
        )
    validate_fact_provenance(
        service.memory, service.manifest, "element.Fe", "element_name_en"
    )
    build_knowledge_snapshot(
        service.memory,
        service.manifest,
        ("Fe",),
        requirements=(ATOMIC_WEIGHTS,),
    )


def test_v2_pack_is_explicitly_rejected() -> None:
    with pytest.raises(ValueError, match="REBUILD_REQUIRED_FROM_SOURCE_KIND_V4"):
        ChemistryDomainService.open(Path("artifacts/domains/chemistry/m281"))
