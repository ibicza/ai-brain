from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactApprovalError, FactMemory
from ai_brain.stage2.facts.migration import (
    create_v2_compatibility_fixture,
    migrate_v2_to_v3,
)
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
from ai_brain.stage2.facts.persistence import FactMemoryIntegrityError
from ai_brain.stage2.facts.values import FactValue, FactValueKind
from ai_brain.stage2.router import (
    ExactUnifiedRouter,
    ToolRegistry,
    UnifiedRouterService,
    create_request,
)
from ai_brain.stage2.router.decisions import make_route_receipt, validate_route_receipt
from ai_brain.stage2.router.models import (
    RequestSourceKind,
    RouteAuthority,
    RouteStatus,
    RouteTarget,
    ToolExecutionStatus,
)
from ai_brain.stage2.router.persistence import RouterStore, RouterStoreIntegrityError
from ai_brain.stage2.router.service import (
    ConfirmationRequiredError,
    UnifiedRouterError,
)
from ai_brain.stage2.router_research.baselines import CharacterNgramRouter
from ai_brain.stage2.router_research.dataset import (
    freeze_recipe,
    generate_router_dataset,
)
from ai_brain.stage2.router_research.evaluation import evaluate


def _service(tmp_path: Path, facts: FactMemory | None = None):
    store = RouterStore.initialize(tmp_path / "router")
    router = ExactUnifiedRouter(tool_registry=ToolRegistry.default(), fact_memory=facts)
    return UnifiedRouterService(router, store=store), store


def _facts(tmp_path: Path) -> FactMemory:
    memory = FactMemory.initialize(tmp_path / "facts")
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
    source = memory.add_source(
        content="population=100",
        source_kind=SourceKind.OFFICIAL_PRIMARY,
        title="Population",
        source_family="official",
        trust_tier="T1",
        source_id="source.population",
    )
    evidence = memory.add_evidence(
        source_id=source.source_id,
        relation=EvidenceRelation.SUPPORTS,
        location_kind=EvidenceLocationKind.CHAR_SPAN,
        location={"start": 11, "end": 14},
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence=Decimal(1),
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
        approved=True,
        evidence_id="evidence.population",
    )
    proposal = memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create(FactValueKind.INTEGER, 100),
        valid_from="2025-01-01",
        source_ids=(source.source_id,),
        evidence_ids=(evidence.evidence_id,),
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
    memory.commit_proposal(proposal.proposal_id, approval.approval_id)
    return memory


def _commit_value(
    memory: FactMemory, suffix: str, entity_id: str, value: int
) -> tuple[str, str]:
    text = f"population={value}"
    source = memory.add_source(
        content=text,
        source_kind=SourceKind.OFFICIAL_PRIMARY,
        title=suffix,
        source_family=f"family-{suffix}",
        trust_tier="T1",
        source_id=f"source.{suffix}",
    )
    evidence = memory.add_evidence(
        source_id=source.source_id,
        relation=EvidenceRelation.SUPPORTS,
        location_kind=EvidenceLocationKind.CHAR_SPAN,
        location={"start": 11, "end": len(text)},
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence=Decimal(1),
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
        approved=True,
        evidence_id=f"evidence.{suffix}",
    )
    proposal = memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id=entity_id,
        predicate_id="population",
        object_value=FactValue.create(FactValueKind.INTEGER, value),
        valid_from="2025-01-01",
        source_ids=(source.source_id,),
        evidence_ids=(evidence.evidence_id,),
        proposal_id=f"proposal.{suffix}",
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
    return claim.claim_id, evidence.evidence_id


def test_request_ids_are_unique_but_semantics_are_stable() -> None:
    first = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 2 plus 3.",
        language="en",
    )
    second = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 2 plus 3.",
        language="en",
    )
    assert first.request_id != second.request_id
    assert first.request_hash != second.request_hash
    assert first.original_input_hash == second.original_input_hash
    assert first.semantic_input_hash == second.semantic_input_hash
    assert first.request_id not in first.original_input


@pytest.mark.parametrize(
    ("language", "text", "expected"),
    (
        ("en", "Calculate 12.5 plus 3.", "15.5"),
        ("ru", "Вычисли 12 умножить на 4.", "48"),
    ),
)
def test_controlled_tool_requires_confirmation_and_executes(
    tmp_path: Path, language: str, text: str, expected: str
) -> None:
    service, store = _service(tmp_path)
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input=text,
        language=language,
    )
    decision, response = service.handle(request)
    assert decision.selected_target == RouteTarget.TOOL_REQUEST
    assert decision.route_status == RouteStatus.EXACT_ROUTE
    proposal = service._tool_proposals[response.tool_proposal_hash]
    with pytest.raises(ConfirmationRequiredError):
        service.execute_tool(proposal, None)
    confirmation = service.confirm_tool(proposal, identity="user")
    result = service.execute_tool(proposal, confirmation)
    assert result.status == ToolExecutionStatus.EXECUTED
    assert result.output["result"] == expected
    assert store.verify()["status"] == "VALID"


def test_date_tool_and_division_by_zero(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="How many days are between 2026-01-01 and 2026-01-10?",
        language="en",
    )
    _, response = service.handle(request)
    proposal = service._tool_proposals[response.tool_proposal_hash]
    result = service.execute_tool(
        proposal, service.confirm_tool(proposal, identity="user")
    )
    assert result.output["days"] == 9

    request = create_request(
        RequestSourceKind.STRUCTURED_TOOL,
        structured_payload={
            "tool_id": "decimal_arithmetic",
            "arguments": {"operation": "DIVIDE", "operands": ["1", "0"]},
        },
    )
    _, response = service.handle(request)
    proposal = service._tool_proposals[response.tool_proposal_hash]
    result = service.execute_tool(
        proposal, service.confirm_tool(proposal, identity="user")
    )
    assert result.status == ToolExecutionStatus.REJECTED
    assert result.output == {"error": "division by zero"}


def test_tampered_tool_argument_fails_closed(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 2 plus 3.",
        language="en",
    )
    _, response = service.handle(request)
    proposal = service._tool_proposals[response.tool_proposal_hash]
    tampered = replace(
        proposal,
        typed_arguments={"operation": "ADD", "operands": ["200", "300"]},
    )
    with pytest.raises(UnifiedRouterError, match="hash mismatch"):
        service.confirm_tool(tampered, identity="user")


def test_forged_tool_confirmation_fails_closed(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 2 plus 3.",
        language="en",
    )
    _, response = service.handle(request)
    proposal = service._tool_proposals[response.tool_proposal_hash]
    issued = service.confirm_tool(proposal, identity="user")
    forged_body = asdict(
        replace(issued, confirmation_id="forged", confirmation_hash="")
    )
    forged_body.pop("confirmation_hash")
    forged = replace(
        issued, confirmation_id="forged", confirmation_hash=content_hash(forged_body)
    )
    with pytest.raises(UnifiedRouterError, match="not issued"):
        service.execute_tool(proposal, forged)


def test_route_receipt_target_change_and_stale_dependency_fail_closed(
    tmp_path: Path,
) -> None:
    facts = _facts(tmp_path)
    service, _ = _service(tmp_path, facts)
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 2 plus 3.",
        language="en",
    )
    decision, response = service.handle(request)
    receipt = make_route_receipt(request, decision)
    validate_route_receipt(receipt, request, decision, service.router.dependencies())
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_route_receipt(
            replace(receipt, selected_target=RouteTarget.FACT_QUERY),
            request,
            decision,
            service.router.dependencies(),
        )

    facts.add_entity(
        entity_id="city.changed",
        entity_type="CITY",
        canonical_label_ru="Изменённый",
        canonical_label_en="Changed",
    )
    proposal = service._tool_proposals[response.tool_proposal_hash]
    with pytest.raises(ValueError, match="dependencies are stale"):
        service.confirm_tool(proposal, identity="user")


def test_structured_source_kind_is_not_reinterpreted(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    request = create_request(
        RequestSourceKind.STRUCTURED_FACT,
        structured_payload={"tool_id": "decimal_arithmetic", "arguments": {}},
    )
    decision = service.route(request)
    assert decision.selected_target == RouteTarget.UNSUPPORTED
    assert decision.route_status == RouteStatus.INVALID_REQUEST


def test_assistive_never_has_exact_authority(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    request = create_request(
        RequestSourceKind.ASSISTIVE_TEXT,
        original_input="Could you calculate roughly twelve and five?",
        language="en",
    )
    decision = service.route(request)
    assert decision.route_authority == RouteAuthority.ASSISTIVE_PROPOSAL
    assert not decision.exact_match
    assert decision.route_status == RouteStatus.ASSISTIVE_CANDIDATES


def test_composite_request_is_not_partially_executed(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 12 plus 5 and store the result as a trusted fact.",
        language="en",
    )
    decision, response = service.handle(request)
    assert decision.selected_target == RouteTarget.COMPOSITE_REQUIRED
    assert response.fact_answer_hash is None
    assert response.skill_dispatch_hash is None
    assert response.tool_result_hash is None


@pytest.mark.parametrize(
    ("language", "text"),
    (
        ("en", "What is the population of Alpha?"),
        ("ru", "Каково значение население у города Альфа?"),
    ),
)
def test_controlled_fact_route_answers_read_only(
    tmp_path: Path, language: str, text: str
) -> None:
    facts = _facts(tmp_path)
    service, _ = _service(tmp_path, facts)
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input=text,
        language=language,
    )
    decision, response = service.handle(request)
    assert decision.selected_target == RouteTarget.FACT_QUERY
    assert response.fact_answer_hash is not None
    assert response.tool_proposal_hash is None


def test_current_query_intent_is_not_audited_as_historical(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    query = facts.make_query(subject="city.alpha", predicate_id="population")
    facts.query(query)
    events = facts.database.audit_replay(object_id=query.query_id)
    assert "FACT_QUERY_EXECUTED" in {item["event_type"] for item in events}
    assert "HISTORICAL_QUERY_EXECUTED" not in {item["event_type"] for item in events}


def test_full_claim_payload_tamper_is_detected(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    with facts.database.connect() as connection:
        row = connection.execute(
            "SELECT claim_id, payload_json FROM claims LIMIT 1"
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["recorded_at"] = "2027-01-01T00:00:00Z"
        connection.execute(
            "UPDATE claims SET payload_json = ? WHERE claim_id = ?",
            (json.dumps(payload), row["claim_id"]),
        )
        connection.commit()
    with pytest.raises(FactMemoryIntegrityError, match="full-record"):
        facts.verify()


def test_v2_to_v3_migration_is_non_destructive(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    source = tmp_path / "facts-v2"
    create_v2_compatibility_fixture(facts.root, source)
    source_bytes = {
        item.relative_to(source): item.read_bytes()
        for item in source.rglob("*")
        if item.is_file()
    }
    target = tmp_path / "facts-v3"
    manifest = migrate_v2_to_v3(source, target)
    assert manifest["source_unchanged"] is True
    assert manifest["claim_record_hash_count"] == 1
    assert FactMemory.open(target).verify()["status"] == "VALID"
    assert source_bytes == {
        item.relative_to(source): item.read_bytes()
        for item in source.rglob("*")
        if item.is_file()
    }


def test_cross_domain_supersession_and_unrelated_resolution_evidence_fail(
    tmp_path: Path,
) -> None:
    facts = _facts(tmp_path)
    answer = facts.query(
        facts.make_query(subject="city.alpha", predicate_id="population")
    )
    first = answer.selected_claim_ids[0]
    second, second_evidence = _commit_value(facts, "alpha-second", "city.alpha", 200)
    facts.add_entity(
        entity_id="city.beta",
        entity_type="CITY",
        canonical_label_ru="Бета",
        canonical_label_en="Beta",
    )
    beta, beta_evidence = _commit_value(facts, "beta", "city.beta", 300)
    with pytest.raises(ValueError, match="subject and predicate"):
        facts.supersede_claim(
            first,
            beta,
            actor="reviewer",
            actor_identity_type=ActorIdentityType.HUMAN,
            reason="invalid domain",
        )
    group = facts.conflicts()[0]
    with pytest.raises(FactApprovalError, match="unrelated"):
        facts.resolve_conflict(
            group.conflict_group_id,
            resolution_kind=ConflictResolutionKind.MANUAL_RESOLUTION,
            selected_claim_ids=(second,),
            remaining_claim_ids=(second,),
            evidence_ids=(beta_evidence,),
            actor_identity="reviewer",
            actor_identity_type=ActorIdentityType.HUMAN,
            reason="unrelated evidence",
        )
    event = facts.resolve_conflict(
        group.conflict_group_id,
        resolution_kind=ConflictResolutionKind.MANUAL_RESOLUTION,
        selected_claim_ids=(second,),
        remaining_claim_ids=(second,),
        evidence_ids=(second_evidence,),
        actor_identity="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="use retained support",
    )
    assert event.evidence_links[0].claim_id == second


def test_router_backup_restore(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    service.handle(
        create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 1 plus 2.",
            language="en",
        )
    )
    backup = tmp_path / "backup"
    store.backup(backup)
    restored = RouterStore.restore(backup, tmp_path / "restored")
    assert restored.verify()["artifact_count"] == store.verify()["artifact_count"]


def test_router_store_detects_artifact_payload_tamper(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    service.handle(
        create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 1 plus 2.",
            language="en",
        )
    )
    with store.connect() as connection:
        row = connection.execute(
            "SELECT artifact_type, artifact_id, payload_json FROM artifacts "
            "WHERE artifact_type = 'request' LIMIT 1"
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["original_input"] = "tampered"
        connection.execute(
            "UPDATE artifacts SET payload_json = ? "
            "WHERE artifact_type = ? AND artifact_id = ?",
            (json.dumps(payload), row["artifact_type"], row["artifact_id"]),
        )
        connection.commit()
    with pytest.raises(RouterStoreIntegrityError, match="artifact hash mismatch"):
        store.verify()


def test_trusted_router_import_does_not_load_torch() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import ai_brain.stage2.router; print('torch' in sys.modules)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "False"


def test_fair_router_dataset_blind_separation_and_baseline(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    manifest = generate_router_dataset(
        root,
        split_counts={
            "train": 600,
            "validation": 60,
            "calibration": 60,
            "development": 120,
            "blind": 120,
        },
    )
    assert manifest["split_counts"]["train"] == 600
    public = [
        json.loads(line)
        for line in (root / "blind_public.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert all("label" not in row for row in public)
    freeze = freeze_recipe(root, {"baseline": "char_ngram", "n": 3})
    assert freeze["freeze_hash"]
    with pytest.raises(ValueError, match="already frozen"):
        freeze_recipe(root, {"baseline": "changed"})
    train = [
        json.loads(line)
        for line in (root / "train.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    development = [
        json.loads(line)
        for line in (root / "development.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    metrics = evaluate(CharacterNgramRouter().fit(train), development)
    assert metrics["false_exact_authority"] == 0
    assert metrics["top1"] >= 0.80
