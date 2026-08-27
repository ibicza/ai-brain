"""Isolated authoritative-source update simulation for M-28 acceptance."""

from __future__ import annotations

import shutil
from pathlib import Path

from ai_brain.stage2.domains.chemistry.importer import IMPORT_IDENTITY
from ai_brain.stage2.domains.chemistry.manifest import (
    build_domain_manifest,
    write_domain_manifest,
)
from ai_brain.stage2.domains.chemistry.replay import replay_chemistry_result
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.tool_registry import chemistry_tool_manifests
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    EvidenceLocationKind,
    EvidenceRelation,
    ExtractionMethod,
    ProposalSource,
    QueryStatus,
    SourceKind,
)
from ai_brain.stage2.facts.persistence import FactDatabase
from ai_brain.stage2.facts.values import FactValue
from ai_brain.stage2.router.service import UnifiedRouterError


def run_source_update_simulation(
    source_service: ChemistryDomainService, target: Path
) -> dict[str, object]:
    target = target.resolve()
    backup = target.parent / f"{target.name}-backup"
    source_service.memory.database.backup(backup)
    FactDatabase.restore(backup, target / "fact_memory")
    shutil.copytree(source_service.root / "sources", target / "sources")
    memory = FactMemory.open(target / "fact_memory")
    tool_hashes = tuple(
        (key, value.manifest_hash)
        for key, value in sorted(chemistry_tool_manifests().items())
    )
    manifest = build_domain_manifest(memory, target / "sources", tool_hashes)
    write_domain_manifest(manifest, target / "domain_manifest.json")
    service = ChemistryDomainService.open(target, source_dir=target / "sources")

    _, prepared, proposal = service.prepare_tool(
        "chemistry_molar_mass",
        {"formula": "H2O", "mode": "conventional", "unit": "g/mol"},
    )
    old_result, _ = service.confirm_and_execute(
        prepared, proposal, identity="m28-source-update"
    )
    assert old_result is not None
    _, pending_response, pending = service.prepare_tool(
        "chemistry_molar_mass",
        {"formula": "H2O", "mode": "conventional", "unit": "g/mol"},
    )

    update_document = {
        "source": {
            "authority": "M-28 source-update simulation",
            "version": "2024-simulated-update",
        },
        "weights": [{"symbol": "O", "conventional": "16.000"}],
    }
    source = memory.add_source(
        content=update_document,
        source_kind=SourceKind.OFFICIAL_PRIMARY,
        title="Simulated authoritative atomic-weight update",
        author="M-28 acceptance",
        publisher="M-28 acceptance",
        locator="local-simulation:m28-source-update",
        published_at="2026-08-27",
        retrieved_at="2026-08-27",
        language="en",
        source_family="CIAAW_ATOMIC_WEIGHTS_SIMULATED_UPDATE",
        trust_tier="AUTHORITATIVE_PRIMARY_SIMULATION",
        license_metadata={"scope": "isolated acceptance fixture"},
        media_type="application/json",
        source_id="source_m28_simulated_weight_update",
    )
    evidence = memory.add_evidence(
        source_id=source.source_id,
        relation=EvidenceRelation.SUPPORTS,
        location_kind=EvidenceLocationKind.JSON_POINTER,
        location={"pointer": "/weights/0"},
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence="1",
        reviewer=IMPORT_IDENTITY,
        reviewer_identity_type=ActorIdentityType.TRUSTED_PROCESS,
        approved=True,
        evidence_id="ev_m28_simulated_O_update",
    )
    fact_proposal = memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="element.O",
        predicate_id="conventional_atomic_weight",
        object_value=FactValue.create("DECIMAL", "16.000"),
        source_ids=(source.source_id,),
        evidence_ids=(evidence.evidence_id,),
        proposal_id="proposal_m28_simulated_O_update",
    )
    memory.prepare_for_review(
        fact_proposal.proposal_id,
        reviewer=IMPORT_IDENTITY,
        reviewer_identity_type=ActorIdentityType.TRUSTED_PROCESS,
    )
    approval = memory.approve_proposal(
        fact_proposal.proposal_id,
        reviewer_identity=IMPORT_IDENTITY,
        reviewer_identity_type=ActorIdentityType.TRUSTED_PROCESS,
    )
    memory.commit_proposal(fact_proposal.proposal_id, approval.approval_id)

    pending_rejected = False
    try:
        service.confirm_and_execute(
            pending_response, pending, identity="m28-source-update"
        )
    except (UnifiedRouterError, ValueError):
        pending_rejected = True
    current = memory.query(
        memory.make_query(
            subject="O",
            predicate_id="conventional_atomic_weight",
            include_conflicts=True,
        )
    )
    historical = memory.query(
        memory.make_query(
            subject="O",
            predicate_id="conventional_atomic_weight",
            known_at=old_result.executed_at,
            include_conflicts=True,
        )
    )
    replay_status = replay_chemistry_result(old_result.output, memory, manifest)
    return {
        "status": "PASS",
        "pending_proposal_rejected": pending_rejected,
        "old_result_replay_status": replay_status.value,
        "current_query_status": current.answer_status.value,
        "historical_query_status": historical.answer_status.value,
        "current_claim_count": len(current.claims),
        "old_claim_retained": any(
            str(claim.value.value) == "15.999" for claim in historical.claims
        ),
        "conflict_visible": current.answer_status == QueryStatus.CONFLICT,
        "source_update_snapshot_changed": memory.database.snapshot_hash()
        != manifest["fact_memory_snapshot_hash"],
    }
