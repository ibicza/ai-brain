from __future__ import annotations

import json
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path

import pytest

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage2.catalog import install_structural_catalog, structural_specs
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage2.facts.memory import FactApprovalError, FactMemory
from ai_brain.stage2.facts.migration import (
    create_v3_compatibility_fixture,
    migrate_v3_to_v4,
)
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    Cardinality,
    ConflictResolutionKind,
    EvidenceLocationKind,
    EvidenceRelation,
    ExtractionMethod,
    ProposalSource,
    ResolutionEvidenceRole,
    SourceKind,
    TemporalMode,
)
from ai_brain.stage2.facts.values import FactValue, FactValueKind
from ai_brain.stage2.registry import rebuild_from_rule_memory
from ai_brain.stage2.router import (
    ExactUnifiedRouter,
    ToolRegistry,
    UnifiedRouterService,
    create_request,
)
from ai_brain.stage2.router import tools as tool_module
from ai_brain.stage2.router.cli import _response
from ai_brain.stage2.router.models import (
    DependencySnapshot,
    ReplayStatus,
    RequestSourceKind,
    ResponseStage,
    RouteStatus,
)
from ai_brain.stage2.router.persistence import (
    RouterStore,
    create_router_v1_compatibility_fixture,
    migrate_router_store_v1_to_v2,
)
from ai_brain.stage2.router.request import validate_request
from ai_brain.stage2.router.tool_registry import build_tool_implementation_manifest
from ai_brain.stage2.router.tools import (
    DecimalToolLimits,
    ToolInputError,
    _render_decimal,
    decimal_arithmetic,
)
from ai_brain.stage2.service import Stage2Router


def _tool_service(tmp_path: Path, facts: FactMemory | None = None):
    store = RouterStore.initialize(tmp_path / "router")
    service = UnifiedRouterService(
        ExactUnifiedRouter(tool_registry=ToolRegistry.default(), fact_memory=facts),
        store=store,
    )
    return service, store


def _rehash_response(response, snapshot: DependencySnapshot):
    changed = replace(
        response,
        dependency_snapshots=asdict(snapshot),
        dependency_snapshot_hash=snapshot.dependency_snapshot_hash,
        response_hash="",
    )
    body = asdict(changed)
    body.pop("response_hash")
    return replace(changed, response_hash=content_hash(body))


def _changed_snapshot(snapshot: DependencySnapshot, field: str, value):
    body = asdict(snapshot)
    body.pop("dependency_snapshot_hash")
    body[field] = value
    return DependencySnapshot(**body, dependency_snapshot_hash=content_hash(body))


@pytest.mark.parametrize(
    ("field", "value", "status"),
    (
        ("fact_memory_hash", "1" * 64, ReplayStatus.STALE_FACT_MEMORY),
        ("skill_registry_hash", "2" * 64, ReplayStatus.STALE_SKILL_REGISTRY),
        ("rule_memory_hash", "3" * 64, ReplayStatus.STALE_RULE_MEMORY),
        ("tool_registry_hash", "4" * 64, ReplayStatus.STALE_TOOL_REGISTRY),
        (
            "tool_implementation_manifest_hashes",
            (("decimal_arithmetic", "5" * 64),),
            ReplayStatus.STALE_TOOL_IMPLEMENTATION,
        ),
        ("stage1_version", "0.0.0", ReplayStatus.INCOMPATIBLE_VERSION),
        ("tool_policy_version", "stale", ReplayStatus.INCOMPATIBLE_VERSION),
        ("equivalence_policy_version", "stale", ReplayStatus.INCOMPATIBLE_VERSION),
    ),
)
def test_dependency_replay_reports_each_component(
    tmp_path: Path, field: str, value, status: ReplayStatus
) -> None:
    service, _ = _tool_service(tmp_path)
    _, response = service.handle(
        create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 2 plus 3.",
            language="en",
        )
    )
    current = service.router.dependencies()
    stored = _changed_snapshot(current, field, value)
    report = service.replay(_rehash_response(response, stored))
    assert report.overall_status == status
    assert field in {*report.stale_components, *report.incompatible_versions}


def test_replay_rejects_tamper_and_legacy_artifact(tmp_path: Path) -> None:
    service, store = _tool_service(tmp_path / "live")
    _, response = service.handle(
        create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 2 plus 3.",
            language="en",
        )
    )
    assert (
        service.replay(replace(response, warnings=("tampered",))).overall_status
        == ReplayStatus.INVALID_ARTIFACT
    )
    create_router_v1_compatibility_fixture(store.root, tmp_path / "v1")
    migrate_router_store_v1_to_v2(tmp_path / "v1", tmp_path / "v2")
    migrated = RouterStore(tmp_path / "v2")
    with migrated.connect() as connection:
        digest = connection.execute(
            "SELECT artifact_hash FROM artifacts WHERE artifact_type = 'response'"
        ).fetchone()[0]
    legacy = _response(migrated.find_hash(digest)[1])
    assert (
        service.replay(legacy).overall_status
        == ReplayStatus.INCOMPATIBLE_LEGACY_ARTIFACT
    )


@pytest.mark.parametrize(
    ("source_overrides", "constant_overrides"),
    (
        ({"decimal_arithmetic": "changed entry"}, {}),
        ({"_decimal": "changed helper"}, {}),
        ({}, {"MAX_OPERANDS": 15}),
        ({}, {"DECIMAL_TOOL_LIMITS": {"max_absolute_exponent": 1}}),
        ({}, {"DECIMAL_RENDERING_POLICY": "changed"}),
    ),
)
def test_tool_manifest_hashes_helpers_constants_and_policies(
    source_overrides: dict[str, str], constant_overrides: dict[str, object]
) -> None:
    baseline = build_tool_implementation_manifest("decimal_arithmetic")
    changed = build_tool_implementation_manifest(
        "decimal_arithmetic",
        source_overrides=source_overrides,
        constant_overrides=constant_overrides,
    )
    assert changed.manifest_hash != baseline.manifest_hash


def test_date_manifest_binds_parsing_policy() -> None:
    baseline = build_tool_implementation_manifest("date_difference")
    changed = build_tool_implementation_manifest(
        "date_difference", constant_overrides={"DATE_PARSING_POLICY": "changed"}
    )
    assert changed.manifest_hash != baseline.manifest_hash


def test_stale_constant_proposal_cannot_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = _tool_service(tmp_path)
    _, prepared = service.handle(
        create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 2 plus 3.",
            language="en",
        )
    )
    proposal = service._tool_proposals[prepared.tool_proposal_hash]
    confirmation = service.confirm_tool(proposal, identity="user")
    monkeypatch.setattr(tool_module, "MAX_OPERANDS", 15)
    with pytest.raises((ValueError, RuntimeError), match="stale|changed"):
        service.execute_tool(proposal, confirmation)


class _ExplosiveString:
    called = False

    def __str__(self) -> str:
        self.called = True
        raise AssertionError("__str__ must not be called")


@pytest.mark.parametrize(
    "operand",
    (
        "1e999999",
        "1e-999999",
        "1e" + "9" * 1_000_000,
        "0" * 1000,
        True,
        1.5,
        b"1",
        [],
        {},
        "NaN",
        "Infinity",
        "sNaN",
    ),
    ids=(
        "huge-positive-exponent",
        "huge-negative-exponent",
        "million-digit-exponent",
        "long-zero-sequence",
        "bool",
        "float",
        "bytes",
        "list",
        "dict",
        "nan",
        "infinity",
        "snan",
    ),
)
def test_decimal_attack_operands_are_typed_rejections(operand) -> None:
    with pytest.raises(ToolInputError):
        decimal_arithmetic({"operation": "ADD", "operands": [operand, "1"]})


def test_decimal_resource_edges_and_no_arbitrary_string_coercion() -> None:
    explosive = _ExplosiveString()
    with pytest.raises(ToolInputError):
        decimal_arithmetic({"operation": "ADD", "operands": [explosive, "1"]})
    assert not explosive.called
    huge = 1 << 100_000
    with pytest.raises(ToolInputError):
        decimal_arithmetic({"operation": "ADD", "operands": [huge, "1"]})
    assert (
        decimal_arithmetic({"operation": "ADD", "operands": ["1"] * 16})["result"]
        == "16"
    )
    with pytest.raises(ToolInputError):
        decimal_arithmetic({"operation": "ADD", "operands": ["1"] * 17})
    with pytest.raises(ToolInputError):
        decimal_arithmetic({"operation": "DIVIDE", "operands": ["1", "0"]})


def test_decimal_render_limit_is_checked_before_fixed_rendering() -> None:
    limits = DecimalToolLimits(
        max_absolute_exponent=510,
        max_adjusted_exponent=510,
        max_rendered_chars=511,
    )
    assert len(_render_decimal(Decimal("1e510"), limits)) == 511
    with pytest.raises(ToolInputError, match="rendering"):
        _render_decimal(
            Decimal("1e511"),
            replace(limits, max_absolute_exponent=511, max_adjusted_exponent=511),
        )


def test_invalid_tool_arguments_receive_no_exact_authority_or_confirmation(
    tmp_path: Path,
) -> None:
    service, store = _tool_service(tmp_path)
    request = create_request(
        RequestSourceKind.STRUCTURED_TOOL,
        structured_payload={
            "tool_id": "decimal_arithmetic",
            "arguments": {"operation": "DIVIDE", "operands": ["1", "0"]},
        },
    )
    decision, response = service.handle(request)
    assert decision.route_status == RouteStatus.INVALID_REQUEST
    assert response.tool_proposal_hash is None
    assert not service._tool_proposals
    assert "TOOL_ARGUMENT_INVALID" in {
        item["event_type"] for item in store.audit_replay()
    }


def test_request_semantic_hash_and_structured_schema_are_strict() -> None:
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 2 plus 3.",
        language="en",
    )
    body = asdict(request)
    body["semantic_input_hash"] = "0" * 64
    body.pop("request_hash")
    tampered = replace(
        request,
        semantic_input_hash="0" * 64,
        request_hash=content_hash(body),
    )
    with pytest.raises(ValueError, match="semantic"):
        validate_request(tampered)


def test_tool_response_lifecycle_and_failure(tmp_path: Path) -> None:
    service, _ = _tool_service(tmp_path)
    request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 2 plus 3.",
        language="en",
    )
    _, prepared = service.handle(request)
    assert prepared.response_stage == ResponseStage.PREPARED
    proposal = service._tool_proposals[prepared.tool_proposal_hash]
    confirmation = service.confirm_tool(proposal, identity="user")
    result, completed = service.execute_tool_and_respond(
        prepared, proposal, confirmation
    )
    assert result is not None and result.output["result"] == "5"
    assert completed.response_stage == ResponseStage.COMPLETED
    assert completed.parent_prepared_response_hash == prepared.response_hash
    assert completed.fact_answer_hash is None and completed.skill_dispatch_hash is None
    assert service.replay(completed).overall_status == ReplayStatus.CURRENT

    other_request = create_request(
        RequestSourceKind.CONTROLLED_LANGUAGE,
        original_input="Calculate 4 plus 5.",
        language="en",
    )
    _, other_prepared = service.handle(other_request)
    other_proposal = service._tool_proposals[other_prepared.tool_proposal_hash]
    result, failed = service.execute_tool_and_respond(
        other_prepared, other_proposal, None
    )
    assert result is None and failed.response_stage == ResponseStage.FAILED
    assert failed.failure_artifact_hash is not None and failed.tool_result_hash is None


def test_skill_response_lifecycle(tmp_path: Path) -> None:
    catalog = install_structural_catalog(tmp_path / "catalog")
    memory = RuleMemory.load(catalog.service.memory_path)
    registry = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
    skill_router = Stage2Router(
        registry=registry,
        memory_path=catalog.service.memory_path,
        stage1_audit_path=catalog.service.audit.path,
        stage2_audit_path=tmp_path / "stage2.jsonl",
    )
    service = UnifiedRouterService(
        ExactUnifiedRouter(
            tool_registry=ToolRegistry.default(), skill_router=skill_router
        )
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
    assert prepared.response_stage == ResponseStage.PREPARED
    service.confirm_skill(decision, identity="user")
    skill = registry.records[decision.parser_evidence["selected_skill_id"]]
    dispatched, completed = service.dispatch_skill_and_respond(
        prepared,
        request,
        decision,
        proposal=catalog.proposals[skill.rule_id],
        installed_receipt=catalog.receipts[skill.rule_id],
        initial_state={"R0": 2, "R1": 3, "R2": 5, "R3": 7},
    )
    assert dispatched is not None
    assert completed.response_stage == ResponseStage.COMPLETED
    assert completed.skill_dispatch_hash is not None
    assert completed.stage1_execution_hash is not None
    assert completed.fact_answer_hash is None and completed.tool_result_hash is None


def _fact_memory_with_conflict(root: Path) -> tuple[FactMemory, str, str, str, str]:
    memory = FactMemory.initialize(root)
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

    def commit(suffix: str, value: int, with_contradiction: bool):
        source = memory.add_source(
            content=f"population={value}; reviewed",
            source_kind=SourceKind.OFFICIAL_PRIMARY,
            title=suffix,
            source_family=suffix,
            trust_tier="T1",
            source_id=f"source.{suffix}",
        )
        support = memory.add_evidence(
            source_id=source.source_id,
            relation=EvidenceRelation.SUPPORTS,
            location_kind=EvidenceLocationKind.CHAR_SPAN,
            location={"start": 0, "end": 10},
            extraction_method=ExtractionMethod.DETERMINISTIC,
            extraction_confidence=Decimal(1),
            reviewer="reviewer",
            reviewer_identity_type=ActorIdentityType.HUMAN,
            approved=True,
            evidence_id=f"evidence.{suffix}.support",
        )
        evidence_ids = [support.evidence_id]
        contradiction_id = ""
        if with_contradiction:
            contradiction = memory.add_evidence(
                source_id=source.source_id,
                relation=EvidenceRelation.CONTRADICTS,
                location_kind=EvidenceLocationKind.CHAR_SPAN,
                location={"start": 11, "end": 19},
                extraction_method=ExtractionMethod.DETERMINISTIC,
                extraction_confidence=Decimal(1),
                reviewer="reviewer",
                reviewer_identity_type=ActorIdentityType.HUMAN,
                approved=True,
                evidence_id=f"evidence.{suffix}.contradiction",
            )
            contradiction_id = contradiction.evidence_id
            evidence_ids.append(contradiction_id)
        proposal = memory.receive_proposal(
            source=ProposalSource.STRUCTURED_JSON,
            subject_entity_id="city.alpha",
            predicate_id="population",
            object_value=FactValue.create(FactValueKind.INTEGER, value),
            valid_from="2025-01-01",
            source_ids=(source.source_id,),
            evidence_ids=tuple(evidence_ids),
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
        return claim.claim_id, support.evidence_id, contradiction_id

    first, _, first_contradiction = commit("first", 100, True)
    second, second_support, _ = commit("second", 200, False)
    return memory, first, second, first_contradiction, second_support


def test_conflict_resolution_requires_complete_partition(tmp_path: Path) -> None:
    memory, _, second, first_contradiction, second_support = _fact_memory_with_conflict(
        tmp_path / "facts"
    )
    group = memory.conflicts()[0]
    with pytest.raises(FactApprovalError, match="every retained and removed"):
        memory.resolve_conflict(
            group.conflict_group_id,
            resolution_kind=ConflictResolutionKind.MANUAL_RESOLUTION,
            selected_claim_ids=(second,),
            remaining_claim_ids=(second,),
            evidence_ids=(second_support,),
            actor_identity="reviewer",
            actor_identity_type=ActorIdentityType.HUMAN,
            reason="winner support is insufficient",
        )
    event = memory.resolve_conflict(
        group.conflict_group_id,
        resolution_kind=ConflictResolutionKind.MANUAL_RESOLUTION,
        selected_claim_ids=(second,),
        remaining_claim_ids=(second,),
        evidence_ids=(second_support, first_contradiction),
        actor_identity="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="complete reviewed partition",
    )
    roles = {item.role for item in event.evidence_links}
    assert roles == {
        ResolutionEvidenceRole.SUPPORTS_REMAINING,
        ResolutionEvidenceRole.CONTRADICTS_REMOVED,
    }
    assert memory.verify()["status"] == "VALID"


def test_supersession_outside_group_does_not_resolve(tmp_path: Path) -> None:
    memory, first, _, _, _ = _fact_memory_with_conflict(tmp_path / "facts")
    original_group = next(
        group for group in memory.conflicts() if first in group.claim_ids
    )
    # A third claim creates pairwise groups; it is not a member of the original pair.
    # Reuse the helper logic through a fresh proposal in the target memory.
    source = memory.add_source(
        content="population=300",
        source_kind=SourceKind.OFFICIAL_PRIMARY,
        title="third",
        source_family="third",
        trust_tier="T1",
        source_id="source.third",
    )
    evidence = memory.add_evidence(
        source_id=source.source_id,
        relation=EvidenceRelation.SUPPORTS,
        location_kind=EvidenceLocationKind.CHAR_SPAN,
        location={"start": 0, "end": 14},
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence=Decimal(1),
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
        approved=True,
        evidence_id="evidence.third",
    )
    proposal = memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create(FactValueKind.INTEGER, 300),
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
    third = memory.commit_proposal(proposal.proposal_id, approval.approval_id)
    memory.supersede_claim(
        first,
        third.claim_id,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="new replacement",
    )
    projected = {group.conflict_group_id: group for group in memory.conflicts()}[
        original_group.conflict_group_id
    ]
    assert projected.resolution_status.value == "UNRESOLVED"
    assert "SUPERSESSION_OUTSIDE_GROUP_NO_AUTO_RESOLUTION" in {
        row["event_type"] for row in memory.database.audit_replay()
    }


def test_fact_v3_to_v4_and_router_v1_to_v2_migrations_are_non_destructive(
    tmp_path: Path,
) -> None:
    facts, *_ = _fact_memory_with_conflict(tmp_path / "facts-v4")
    create_v3_compatibility_fixture(facts.root, tmp_path / "facts-v3")
    before = {
        item.relative_to(tmp_path / "facts-v3"): item.read_bytes()
        for item in (tmp_path / "facts-v3").rglob("*")
        if item.is_file()
    }
    manifest = migrate_v3_to_v4(tmp_path / "facts-v3", tmp_path / "facts-out")
    assert manifest["source_unchanged"] is True
    assert FactMemory.open(tmp_path / "facts-out").verify()["status"] == "VALID"
    assert before == {
        item.relative_to(tmp_path / "facts-v3"): item.read_bytes()
        for item in (tmp_path / "facts-v3").rglob("*")
        if item.is_file()
    }

    service, store = _tool_service(tmp_path / "router-live")
    service.handle(
        create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input="Calculate 2 plus 3.",
            language="en",
        )
    )
    create_router_v1_compatibility_fixture(store.root, tmp_path / "router-v1")
    router_before = (tmp_path / "router-v1" / "unified_router.sqlite3").read_bytes()
    router_manifest = migrate_router_store_v1_to_v2(
        tmp_path / "router-v1", tmp_path / "router-out"
    )
    assert router_manifest["source_unchanged"] is True
    assert (
        tmp_path / "router-v1" / "unified_router.sqlite3"
    ).read_bytes() == router_before
    assert RouterStore(tmp_path / "router-out").verify()["status"] == "VALID"


def test_unsafe_v3_resolution_migrates_to_review_required(tmp_path: Path) -> None:
    facts, first, second, _, second_support = _fact_memory_with_conflict(
        tmp_path / "facts-v4"
    )
    create_v3_compatibility_fixture(facts.root, tmp_path / "facts-v3")
    path = tmp_path / "facts-v3" / "fact_memory.sqlite3"
    import sqlite3

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM conflict_resolution_events LIMIT 1"
        ).fetchone()
        payload = json.loads(row["payload_json"])
        link_body = {
            "evidence_id": second_support,
            "claim_id": second,
            "role": ResolutionEvidenceRole.SUPPORTS_REMAINING,
        }
        link = {**link_body, "link_hash": content_hash(link_body)}
        payload.update(
            {
                "new_status": "RESOLVED",
                "resolution_kind": "MANUAL_RESOLUTION",
                "selected_claim_ids": (second,),
                "remaining_claim_ids": (second,),
                "evidence_ids": (second_support,),
                "evidence_links": (link,),
                "reason": "legacy winner support only",
            }
        )
        payload.pop("event_hash")
        digest = content_hash(payload)
        payload["event_hash"] = digest
        connection.execute(
            "UPDATE conflict_resolution_events SET new_status = 'RESOLVED', "
            "resolution_kind = 'MANUAL_RESOLUTION', event_hash = ?, payload_json = ? "
            "WHERE event_id = ?",
            (digest, canonical_json(payload), row["event_id"]),
        )
        connection.execute(
            "INSERT INTO resolution_evidence_links VALUES (?, ?, ?, ?, ?)",
            (
                row["event_id"],
                second_support,
                second,
                ResolutionEvidenceRole.SUPPORTS_REMAINING,
                link["link_hash"],
            ),
        )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    manifest = migrate_v3_to_v4(tmp_path / "facts-v3", tmp_path / "facts-out")
    assert manifest["legacy_resolution_review_required_count"] == 1
    migrated = FactMemory.open(tmp_path / "facts-out")
    group = next(group for group in migrated.conflicts() if first in group.claim_ids)
    assert group.resolution_status.value == "UNRESOLVED"
    assert migrated.verify()["status"] == "VALID"
