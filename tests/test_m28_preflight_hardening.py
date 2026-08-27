from __future__ import annotations

import re
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path

import pytest

from ai_brain.rules.memory import (
    RuleMemory,
    RuleMemoryIntegrityError,
    RuleMemoryIOError,
    RuleMemoryRecoveryError,
)
from ai_brain.stage1.execution import BoundedExecutionError
from ai_brain.stage1.models import ExecutionFailureCode
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage2.catalog import install_structural_catalog, structural_specs
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactApprovalError, FactMemory
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    Cardinality,
    ConflictResolutionKind,
    EvidenceLocationKind,
    EvidenceRelation,
    ExtractionMethod,
    ProposalSource,
    SourceKind,
    TemporalMode,
)
from ai_brain.stage2.facts.values import FactValue, FactValueKind
from ai_brain.stage2.registry import SkillRegistryStaleError, rebuild_from_rule_memory
from ai_brain.stage2.router import (
    ExactUnifiedRouter,
    ToolRegistry,
    UnifiedRouterService,
    create_request,
)
from ai_brain.stage2.router import tools as tool_module
from ai_brain.stage2.router.models import (
    ReplayStatus,
    RequestSourceKind,
    ResponseStage,
)
from ai_brain.stage2.router.service import UnifiedRouterError
from ai_brain.stage2.service import SkillDispatchError, Stage2Router


def _skill_service(root: Path):
    catalog = install_structural_catalog(root / "catalog")
    memory = RuleMemory.load(catalog.service.memory_path)
    registry = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
    stage2 = Stage2Router(
        registry=registry,
        memory_path=catalog.service.memory_path,
        stage1_audit_path=catalog.service.audit.path,
        stage2_audit_path=root / "stage2.jsonl",
    )
    service = UnifiedRouterService(
        ExactUnifiedRouter(tool_registry=ToolRegistry.default(), skill_router=stage2)
    )
    family, sources, destination = next(iter(structural_specs()))
    specification = build_family_specification(
        family, sources=sources, destination=destination
    )
    request = create_request(
        RequestSourceKind.STRUCTURED_SKILL,
        structured_payload=asdict(specification),
    )
    decision, prepared = service.handle(request)
    service.confirm_skill(decision, identity="user")
    skill = registry.records[decision.parser_evidence["selected_skill_id"]]
    kwargs = {
        "proposal": catalog.proposals[skill.rule_id],
        "installed_receipt": catalog.receipts[skill.rule_id],
        "initial_state": {"R0": 2, "R1": 3, "R2": 5, "R3": 7},
    }
    return service, request, decision, prepared, kwargs, catalog.service.memory_path


def test_live_rule_memory_change_never_replays_current(tmp_path: Path) -> None:
    service, request, decision, prepared, _, memory_path = _skill_service(tmp_path)
    assert service.replay(prepared).overall_status == ReplayStatus.CURRENT
    changed = RuleMemory.load(memory_path)
    changed.deprecate(next(iter(changed.records)))
    changed.save(memory_path)
    with pytest.raises(SkillRegistryStaleError):
        service.replay(prepared)
    assert request.request_hash == prepared.request_hash
    assert decision.dependency_snapshot_hash == prepared.dependency_snapshot_hash


def test_decimal_regex_is_manifest_bound_and_stales_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = UnifiedRouterService(
        ExactUnifiedRouter(tool_registry=ToolRegistry.default())
    )
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 2 plus 3.",
        language="en",
    )
    _, prepared = service.handle(request)
    proposal = service._tool_proposals[prepared.tool_proposal_hash]
    confirmation = service.confirm_tool(proposal, identity="user")
    monkeypatch.setattr(tool_module, "_DECIMAL_RE", re.compile(r"[0-9]+"))
    with pytest.raises(UnifiedRouterError, match="implementation is stale"):
        service.execute_tool(proposal, confirmation)


@pytest.mark.parametrize(
    "failure",
    (
        SkillDispatchError("dispatch"),
        SkillRegistryStaleError("registry"),
        BoundedExecutionError(ExecutionFailureCode.STEP_LIMIT_EXCEEDED, "bounded"),
        RuleMemoryIntegrityError("integrity"),
        RuleMemoryRecoveryError("recovery"),
        RuleMemoryIOError("io"),
        ValueError("schema"),
        TypeError("typed schema"),
    ),
)
def test_expected_skill_failures_return_failed_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    service, request, decision, prepared, kwargs, _ = _skill_service(tmp_path)

    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(service, "dispatch_skill", fail)
    dispatched, response = service.dispatch_skill_and_respond(
        prepared, request, decision, **kwargs
    )
    assert dispatched is None
    assert response.response_stage == ResponseStage.FAILED
    assert response.parent_prepared_response_hash == prepared.response_hash
    assert response.failure_artifact_hash is not None
    assert response.skill_dispatch_hash is None
    assert response.stage1_execution_hash is None


def test_resolution_rejects_future_created_or_attached_evidence(tmp_path: Path) -> None:
    now = ["2026-02-01T00:00:00Z"]
    memory = FactMemory.initialize(tmp_path / "facts", clock=lambda: now[0])
    memory.add_entity(
        entity_id="city.alpha",
        entity_type="CITY",
        canonical_label_ru="Альфа",
        canonical_label_en="Alpha",
    )
    memory.add_predicate(
        predicate_id="population",
        canonical_name_ru="население",
        canonical_name_en="population",
        subject_entity_type="CITY",
        object_kind=FactValueKind.INTEGER,
        cardinality=Cardinality.SINGLE,
        temporal_mode=TemporalMode.VALID_INTERVAL,
    )

    evidence_ids = []
    claim_ids = []
    for suffix, value, relation in (
        ("one", 100, EvidenceRelation.CONTRADICTS),
        ("two", 200, EvidenceRelation.SUPPORTS),
    ):
        source = memory.add_source(
            content={"population": value},
            source_kind=SourceKind.OFFICIAL_PRIMARY,
            title=suffix,
            source_family=suffix,
            trust_tier="T1",
            source_id=f"source.{suffix}",
        )
        support = memory.add_evidence(
            source_id=source.source_id,
            relation=EvidenceRelation.SUPPORTS,
            location_kind=EvidenceLocationKind.JSON_POINTER,
            location={"pointer": "/population"},
            extraction_method=ExtractionMethod.DETERMINISTIC,
            extraction_confidence=Decimal(1),
            reviewer="reviewer",
            reviewer_identity_type=ActorIdentityType.HUMAN,
            approved=True,
            evidence_id=f"evidence.{suffix}.support",
        )
        evidence = support
        if relation == EvidenceRelation.CONTRADICTS:
            evidence = memory.add_evidence(
                source_id=source.source_id,
                relation=relation,
                location_kind=EvidenceLocationKind.JSON_POINTER,
                location={"pointer": "/population"},
                extraction_method=ExtractionMethod.DETERMINISTIC,
                extraction_confidence=Decimal(1),
                reviewer="reviewer",
                reviewer_identity_type=ActorIdentityType.HUMAN,
                approved=True,
                evidence_id=f"evidence.{suffix}.contradiction",
            )
        proposal = memory.receive_proposal(
            source=ProposalSource.STRUCTURED_JSON,
            subject_entity_id="city.alpha",
            predicate_id="population",
            object_value=FactValue.create(FactValueKind.INTEGER, value),
            valid_from="2025-01-01",
            source_ids=(source.source_id,),
            evidence_ids=tuple(
                dict.fromkeys((support.evidence_id, evidence.evidence_id))
            ),
        )
        memory.prepare_for_review(
            proposal.proposal_id,
            reviewer="reviewer",
            reviewer_identity_type=ActorIdentityType.HUMAN,
        )
        approval = memory.approve_proposal(
            proposal.proposal_id,
            reviewer_identity="approver",
            reviewer_identity_type=ActorIdentityType.HUMAN,
        )
        claim = memory.commit_proposal(proposal.proposal_id, approval.approval_id)
        claim_ids.append(claim.claim_id)
        evidence_ids.append(evidence.evidence_id)

    group = memory.conflicts()[0]
    now[0] = "2026-01-01T00:00:00Z"
    with pytest.raises(FactApprovalError, match="before resolution"):
        memory.resolve_conflict(
            group.conflict_group_id,
            resolution_kind=ConflictResolutionKind.MANUAL_RESOLUTION,
            selected_claim_ids=(claim_ids[1],),
            remaining_claim_ids=(claim_ids[1],),
            evidence_ids=tuple(evidence_ids),
            actor_identity="reviewer",
            actor_identity_type=ActorIdentityType.HUMAN,
            reason="clock moved backwards",
        )


def test_replay_rejects_rehashed_wrong_response_schema(tmp_path: Path) -> None:
    service = UnifiedRouterService(
        ExactUnifiedRouter(tool_registry=ToolRegistry.default())
    )
    _, response = service.handle(
        create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 2 plus 3.",
            language="en",
        )
    )
    changed = replace(response, schema_version=999, response_hash="")
    body = asdict(changed)
    body.pop("response_hash")
    changed = replace(changed, response_hash=content_hash(body))
    assert service.replay(changed).overall_status == ReplayStatus.INCOMPATIBLE_VERSION


def test_catalog_fixture_stays_exact(tmp_path: Path) -> None:
    service, request, decision, _, _, _ = _skill_service(tmp_path)
    assert decision.exact_match
    assert decision.parser_evidence["selected_skill_id"]
    assert service.router.rule_memory_recovery_source == "primary"
    assert request.source_kind == RequestSourceKind.STRUCTURED_SKILL
