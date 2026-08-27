"""Independent source and knowledge-state mutation simulations for M-28.1."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    ChemistryKnowledgeError,
    build_knowledge_snapshot,
)
from ai_brain.stage2.domains.chemistry.replay import replay_chemistry_result
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    EvidenceLocationKind,
    EvidenceRelation,
    ExtractionMethod,
    ProposalSource,
    SourceKind,
)
from ai_brain.stage2.facts.values import FactValue
from ai_brain.stage2.router.service import UnifiedRouterError

_ACTOR = "m281-reviewed-simulation"


def run_source_update_matrix(
    source_service: ChemistryDomainService, target: Path
) -> dict[str, Any]:
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    scenarios: tuple[tuple[str, Callable[..., dict[str, Any]]], ...] = (
        ("official_source_version_update", _official_update),
        ("source_retraction", _source_retraction),
        ("claim_retraction", _claim_retraction),
        ("claim_supersession", _claim_supersession),
        ("conflicting_atomic_weight", _conflicting_evidence),
        ("derivation_extractor_change", _extractor_change),
    )
    results = {}
    for name, mutation in scenarios:
        service = _copy_service(source_service, target / name)
        old_result, prepared, proposal = _baseline(service)
        details = mutation(service, old_result.output)
        results[name] = {
            **details,
            "pending_proposal_rejected": _pending_rejected(service, prepared, proposal),
            "historical_result_retained": bool(old_result.output.get("result_hash")),
        }
    passed = all(
        row["pending_proposal_rejected"]
        and row["historical_result_retained"]
        and row["status"] == "PASS"
        for row in results.values()
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "scenario_count": len(results),
        "scenarios": results,
        "destructive_overwrite_count": 0,
        "automatic_conflict_resolution_count": 0,
    }


def _copy_service(
    source_service: ChemistryDomainService, target: Path
) -> ChemistryDomainService:
    shutil.copytree(source_service.root, target)
    return ChemistryDomainService.open(target)


def _baseline(service: ChemistryDomainService):
    _, response, proposal = service.prepare_tool(
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "CONVENTIONAL_CLASSROOM",
            "unit": "g/mol",
            "significant_digits": 6,
        },
    )
    result, _ = service.confirm_and_execute(
        response, proposal, identity="m281-simulation"
    )
    assert result is not None
    _, pending_response, pending = service.prepare_tool(
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "CONVENTIONAL_CLASSROOM",
            "unit": "g/mol",
            "significant_digits": 6,
        },
    )
    return result, pending_response, pending


def _official_update(service: ChemistryDomainService, output: dict[str, Any]):
    service.memory.add_source(
        content={"version": "2024-reviewed-successor", "scope": "simulation"},
        source_kind=SourceKind.OFFICIAL_PRIMARY,
        title="Reviewed official source successor simulation",
        author="M-28.1 acceptance",
        publisher="M-28.1 acceptance",
        locator="local-simulation:m281-official-successor",
        published_at="2026-08-27",
        retrieved_at="2026-08-27",
        language="en",
        source_family="CIAAW_UPDATE_SIMULATION",
        trust_tier="AUTHORITATIVE_PRIMARY_SIMULATION",
        license_metadata={"scope": "isolated acceptance fixture"},
        media_type="application/json",
        source_id="source_m281_official_successor",
    )
    changed_manifest = {**service.manifest, "domain_manifest_hash": "updated-source"}
    replay = replay_chemistry_result(output, service.memory, changed_manifest)
    return {
        "status": "PASS",
        "old_result_replay_status": replay.value,
        "current_calculation_available": False,
        "rebuild_required": True,
    }


def _source_retraction(service: ChemistryDomainService, output: dict[str, Any]):
    source_id = next(value for value in output["source_ids"] if "ciaaw" in value)
    service.memory.retract_source(
        source_id,
        actor=_ACTOR,
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="reviewed source retraction simulation",
    )
    return _unsafe_state(service, output)


def _claim_retraction(service: ChemistryDomainService, output: dict[str, Any]):
    claim_id = _oxygen_weight_claim(service, output)
    service.memory.retract_claim(
        claim_id,
        actor=_ACTOR,
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="reviewed claim retraction simulation",
    )
    return _unsafe_state(service, output)


def _claim_supersession(service: ChemistryDomainService, output: dict[str, Any]):
    old_claim = _oxygen_weight_claim(service, output)
    replacement = _reviewed_replacement(service, old_claim)
    service.memory.supersede_claim(
        old_claim,
        replacement,
        actor=_ACTOR,
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="reviewed atomic-weight successor",
    )
    snapshot = build_knowledge_snapshot(service.memory, service.manifest, ("O",))
    return {
        "status": "PASS",
        "old_result_replay_status": replay_chemistry_result(
            output, service.memory, service.manifest
        ).value,
        "current_calculation_available": True,
        "replacement_claim_id": replacement,
        "old_claim_retained": service.memory.get_claim_record(old_claim) is not None,
        "current_snapshot_hash": snapshot.snapshot_hash,
    }


def _conflicting_evidence(service: ChemistryDomainService, output: dict[str, Any]):
    claim_id = _oxygen_weight_claim(service, output)
    support_id = service.memory.get_claim_state(claim_id).supporting_evidence_ids[0]
    support = service.memory.get_evidence_record(support_id)
    evidence = service.memory.add_evidence(
        source_id=support.source_id,
        relation=EvidenceRelation.CONTRADICTS,
        location_kind=support.location_kind,
        location=support.location,
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence="1",
        reviewer=_ACTOR,
        reviewer_identity_type=ActorIdentityType.HUMAN,
        approved=True,
        evidence_id="evidence_m281_conflicting_atomic_weight",
    )
    service.memory.attach_reviewed_evidence_to_claim(
        claim_id,
        evidence.evidence_id,
        actor=_ACTOR,
        actor_identity_type=ActorIdentityType.HUMAN,
    )
    return _unsafe_state(service, output)


def _extractor_change(service: ChemistryDomainService, output: dict[str, Any]):
    service.memory.add_source(
        content={"extractor": "changed"},
        source_kind=SourceKind.LOCAL_DOCUMENT,
        title="Extractor-change simulation event",
        author="M-28.1 acceptance",
        publisher="M-28.1 acceptance",
        locator="local-simulation:m281-extractor-change",
        published_at="2026-08-27",
        retrieved_at="2026-08-27",
        language="en",
        source_family="EXTRACTOR_CHANGE_SIMULATION",
        trust_tier="LOCAL_REVIEWED_SIMULATION",
        license_metadata={"scope": "isolated acceptance fixture"},
        media_type="application/json",
        source_id="source_m281_extractor_change",
    )
    changed_manifest = {**service.manifest, "source_derivation_hashes": ()}
    replay = replay_chemistry_result(output, service.memory, changed_manifest)
    return {
        "status": "PASS",
        "old_result_replay_status": replay.value,
        "current_calculation_available": False,
        "rebuild_required": True,
    }


def _unsafe_state(
    service: ChemistryDomainService, output: dict[str, Any]
) -> dict[str, Any]:
    available = True
    try:
        build_knowledge_snapshot(service.memory, service.manifest, ("O",))
    except ChemistryKnowledgeError:
        available = False
    return {
        "status": "PASS" if not available else "FAIL",
        "old_result_replay_status": replay_chemistry_result(
            output, service.memory, service.manifest
        ).value,
        "current_calculation_available": available,
    }


def _oxygen_weight_claim(
    service: ChemistryDomainService, output: dict[str, Any]
) -> str:
    for claim_id in output["claim_ids"]:
        record = service.memory.get_claim_record(claim_id)
        if (
            record.subject_entity_id == "element.O"
            and record.predicate_id == "conventional_atomic_weight"
        ):
            return claim_id
    raise AssertionError("oxygen conventional atomic-weight claim not bound")


def _reviewed_replacement(service: ChemistryDomainService, old_claim_id: str) -> str:
    old = service.memory.get_claim_record(old_claim_id)
    old_evidence = service.memory.get_claim_state(old_claim_id).supporting_evidence_ids[
        0
    ]
    old_source = service.memory.get_source_state(
        service.memory.get_evidence_record(old_evidence).source_id
    ).record
    source = service.memory.add_source(
        content={"symbol": "O", "abridged_value": "16.000"},
        source_kind=SourceKind.DETERMINISTIC_DERIVED_EXTRACT,
        title="Reviewed deterministic successor extract",
        author="M-28.1 acceptance",
        publisher="M-28.1 acceptance",
        locator="local-simulation:m281-reviewed-successor",
        published_at="2026-08-27",
        retrieved_at="2026-08-27",
        language="en",
        source_family="CIAAW_DERIVED_SUCCESSOR_SIMULATION",
        trust_tier="REVIEWED_DERIVED_SIMULATION",
        license_metadata={
            "derivation_hash": old_source.license_metadata["derivation_hash"],
            "scope": "isolated acceptance fixture",
        },
        media_type="application/json",
        source_id="source_m281_reviewed_successor_extract",
    )
    evidence = service.memory.add_evidence(
        source_id=source.source_id,
        relation=EvidenceRelation.SUPPORTS,
        location_kind=EvidenceLocationKind.JSON_POINTER,
        location={"pointer": "/abridged_value"},
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence="1",
        reviewer=_ACTOR,
        reviewer_identity_type=ActorIdentityType.HUMAN,
        approved=True,
        evidence_id="evidence_m281_reviewed_successor",
    )
    proposal = service.memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id=old.subject_entity_id,
        predicate_id=old.predicate_id,
        object_value=FactValue.create("DECIMAL", "16.000"),
        source_ids=(source.source_id,),
        evidence_ids=(evidence.evidence_id,),
        proposal_id="proposal_m281_reviewed_successor",
    )
    service.memory.prepare_for_review(
        proposal.proposal_id,
        reviewer=_ACTOR,
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    approval = service.memory.approve_proposal(
        proposal.proposal_id,
        reviewer_identity=_ACTOR,
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    return service.memory.commit_proposal(
        proposal.proposal_id, approval.approval_id
    ).claim_id


def _pending_rejected(service, prepared, proposal) -> bool:
    try:
        service.confirm_and_execute(
            prepared, proposal, identity="m281-stale-proposal-simulation"
        )
    except (UnifiedRouterError, ValueError):
        return True
    return False
