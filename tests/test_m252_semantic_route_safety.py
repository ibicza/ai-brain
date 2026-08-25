from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.models import SemanticFamily, content_hash, specification_hash
from ai_brain.stage1.specifications import build_family_specification
from ai_brain.stage2.catalog import install_structural_catalog, structural_specs
from ai_brain.stage2.dispatch_validation import expected_final_state
from ai_brain.stage2.equivalence_validation import (
    observe_execution,
    validate_final_state_equivalence_classes,
)
from ai_brain.stage2.models import (
    ConfirmationDecision,
    EquivalenceScope,
    RetrievalMode,
    SearchStatus,
)
from ai_brain.stage2.registry import (
    SkillRegistry,
    SkillRegistryIntegrityError,
    SkillRegistryStaleError,
    rebuild_from_rule_memory,
)
from ai_brain.stage2.retrieval import (
    _result_content_hash,
    validate_search_result,
)
from ai_brain.stage2.semantics import final_state_effect_hash
from ai_brain.stage2.service import (
    ConfirmationRequiredError,
    SkillDispatchError,
    Stage2Router,
    validate_dispatch_receipt,
    validate_selection_receipt,
)
from ai_brain.stage2.version import (
    SKILL_REGISTRY_SCHEMA_VERSION,
    STAGE2_SCHEMA_VERSION,
)


@pytest.fixture(scope="module")
def m252_catalog(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("m252-catalog")
    catalog = install_structural_catalog(root / "catalog")
    memory = RuleMemory.load(catalog.service.memory_path)
    registry = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
    return root, catalog, memory, registry


def _router(root: Path, catalog, registry, suffix: str) -> Stage2Router:
    return Stage2Router(
        registry=registry,
        memory_path=catalog.service.memory_path,
        stage1_audit_path=catalog.service.audit.path,
        stage2_audit_path=root / f"stage2-{suffix}.jsonl",
    )


def _without_exact_member(
    tmp_path: Path, catalog, registry, specification
) -> tuple[Stage2Router, SkillRegistry, RuleMemory]:
    expected_hash = specification_hash(specification)
    exact = next(
        item
        for item in registry.active_records()
        if item.specification_hash == expected_hash
    )
    memory = RuleMemory.load(catalog.service.memory_path)
    memory.deprecate(exact.rule_id)
    memory_path = tmp_path / "reduced_rule_memory.json"
    memory.save(memory_path)
    reduced = rebuild_from_rule_memory(memory, receipts=catalog.receipts)
    router = Stage2Router(
        registry=reduced,
        memory_path=memory_path,
        stage1_audit_path=tmp_path / "stage1.jsonl",
        stage2_audit_path=tmp_path / "stage2.jsonl",
    )
    return router, reduced, memory


def test_v3_scope_defaults_and_registry_counts(m252_catalog) -> None:
    root, catalog, _, registry = m252_catalog
    specification = build_family_specification(
        SemanticFamily.MERGE_TWO, sources=("A", "B"), destination="C"
    )
    query, result = _router(root, catalog, registry, "defaults").search_structured(
        specification
    )
    assert STAGE2_SCHEMA_VERSION == 3
    assert SKILL_REGISTRY_SCHEMA_VERSION == 3
    assert query.equivalence_scope == EquivalenceScope.FULL_EXECUTION_TRACE
    assert result.equivalence_scope == EquivalenceScope.FULL_EXECUTION_TRACE
    assert registry.manifest.final_state_effect_class_count == 57
    assert registry.manifest.full_execution_equivalence_class_count == 89
    assert registry.manifest.trace_distinct_class_count == 16


def test_exact_structural_member_always_wins_for_both_scopes(m252_catalog) -> None:
    root, catalog, _, registry = m252_catalog
    router = _router(root, catalog, registry, "exact-matrix")
    counter = 0
    for family, sources, destination in structural_specs():
        specification = build_family_specification(
            family, sources=sources, destination=destination
        )
        expected_hash = specification_hash(specification)
        for scope in EquivalenceScope:
            query, result = router.search_final_state_effect(
                specification,
                equivalence_scope=scope,
                query_id_factory=lambda i=counter: f"m252-exact-{i}",
            )
            counter += 1
            assert query.equivalence_scope == scope
            assert result.status == SearchStatus.EXACT_MATCH
            assert result.exact_match
            assert len(result.candidates) == 1
            assert result.candidates[0].specification_hash == expected_hash
            assert result.candidates[0].evidence["type"] == "STRUCTURAL_IDENTITY"
            assert not result.candidates[0].evidence["structural_identity_differs"]
    assert counter == 178


def test_all_final_state_classes_pass_property_and_trace_validation(
    m252_catalog,
) -> None:
    _, catalog, _, registry = m252_catalog
    result = validate_final_state_equivalence_classes(
        catalog.service.memory_path, registry
    )
    assert result["status"] == "PASS"
    assert result["structural_skill_count"] == 89
    assert result["final_state_effect_class_count"] == 57
    assert result["full_execution_equivalence_class_count"] == 89
    assert result["trace_distinct_class_count"] == 16
    assert result["class_size_distribution"] == {"1": 41, "2": 12, "6": 4}


@pytest.mark.parametrize(
    ("family", "first_sources", "second_sources", "destination"),
    [
        (SemanticFamily.MERGE_TWO, ("A", "B"), ("B", "A"), "C"),
        (
            SemanticFamily.MERGE_THREE,
            ("A", "B", "C"),
            ("C", "A", "B"),
            "D",
        ),
    ],
)
def test_merge_permutations_share_final_state_but_not_trace(
    m252_catalog, family, first_sources, second_sources, destination
) -> None:
    _, catalog, _, registry = m252_catalog
    specs = [
        build_family_specification(family, sources=sources, destination=destination)
        for sources in (first_sources, second_sources)
    ]
    skills = [
        next(
            item
            for item in registry.active_records()
            if item.specification_hash == specification_hash(specification)
        )
        for specification in specs
    ]
    state = {"R0": 2, "R1": 3, "R2": 5, "R3": 7}
    first, second = (
        observe_execution(catalog.service.memory_path, skill, state) for skill in skills
    )
    assert first["final_state"] == second["final_state"]
    assert first["executed_steps"] == second["executed_steps"]
    assert first["captured_actions"] != second["captured_actions"]
    assert first["intermediate_states"] != second["intermediate_states"]
    assert first["action_stream_hash"] != second["action_stream_hash"]
    assert first["specification_hash"] != second["specification_hash"]
    assert first["final_state_effect_hash"] == second["final_state_effect_hash"]


def test_drop_then_transfer_order_is_a_negative_control(
    m252_catalog, tmp_path: Path
) -> None:
    _, catalog, _, registry = m252_catalog
    first = build_family_specification(
        SemanticFamily.DROP_THEN_TRANSFER,
        sources=("A", "B"),
        destination="C",
    )
    reversed_order = build_family_specification(
        SemanticFamily.DROP_THEN_TRANSFER,
        sources=("B", "A"),
        destination="C",
    )
    assert final_state_effect_hash(first) != final_state_effect_hash(reversed_order)
    router, _, _ = _without_exact_member(tmp_path, catalog, registry, first)
    for index, scope in enumerate(EquivalenceScope):
        _, result = router.search_final_state_effect(
            first,
            equivalence_scope=scope,
            query_id_factory=lambda i=index: f"drop-negative-{i}",
        )
        assert result.status == SearchStatus.NO_MATCH
        assert not result.candidates


def test_equivalent_only_route_requires_special_confirmation_and_dispatches(
    m252_catalog, tmp_path: Path
) -> None:
    _, catalog, _, registry = m252_catalog
    requested = build_family_specification(
        SemanticFamily.MERGE_TWO, sources=("A", "B"), destination="C"
    )
    router, _, _ = _without_exact_member(tmp_path, catalog, registry, requested)
    _, full = router.search_final_state_effect(
        requested,
        query_id_factory=lambda: "equivalent-full",
    )
    assert full.status == SearchStatus.NO_MATCH
    assert not full.candidates

    query, result = router.search_final_state_effect(
        requested,
        equivalence_scope=EquivalenceScope.FINAL_STATE_ONLY,
        query_id_factory=lambda: "equivalent-final",
    )
    assert result.status == SearchStatus.FINAL_STATE_EQUIVALENT
    assert not result.exact_match
    assert result.candidates
    candidate = result.candidates[0]
    evidence = candidate.evidence
    assert (
        evidence["requested_specification_hash"]
        != evidence["selected_specification_hash"]
    )
    assert evidence["structural_identity_differs"]
    assert not evidence["full_trace_equivalent"]
    assert "action order" in evidence["warning"]

    pending = router.prepare_selection(query, result, candidate.skill_id)
    validate_selection_receipt(pending)
    with pytest.raises(ConfirmationRequiredError, match="special confirmation"):
        router.confirm_selection(pending, identity="reviewer")
    confirmed = router.confirm_selection(
        pending,
        identity="reviewer",
        decision=ConfirmationDecision.CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION,
    )
    validate_selection_receipt(confirmed)
    state = {"R0": 2, "R1": 3, "R2": 5, "R3": 7}
    _, execution, dispatch = router.dispatch(
        query=query,
        result=result,
        selection=confirmed,
        proposal=catalog.proposals[candidate.rule_id],
        installed_receipt=catalog.receipts[candidate.rule_id],
        initial_state=state,
    )
    assert execution.final_state == expected_final_state(requested, state)
    assert dispatch.structural_identity_differs
    assert not dispatch.full_trace_equivalent
    assert dispatch.requested_specification_hash != dispatch.selected_specification_hash
    validate_dispatch_receipt(dispatch, initial_state=state)

    event_types = [event.event_type for event in router.audit.replay()]
    for required in (
        "FINAL_STATE_EQUIVALENT_FOUND",
        "EQUIVALENT_SELECTION_REVIEWED",
        "EQUIVALENT_SELECTION_CONFIRMED",
        "EQUIVALENT_SKILL_DISPATCHED",
    ):
        assert required in event_types


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("equivalence_scope", EquivalenceScope.FULL_EXECUTION_TRACE),
        ("requested_specification_hash", "0" * 64),
        ("selected_specification_hash", "1" * 64),
        ("equivalence_class_hash", "2" * 64),
    ],
)
def test_equivalent_selection_tampering_invalidates_receipt(
    m252_catalog, tmp_path: Path, field: str, value
) -> None:
    _, catalog, _, registry = m252_catalog
    requested = build_family_specification(
        SemanticFamily.MERGE_TWO, sources=("A", "B"), destination="C"
    )
    router, _, _ = _without_exact_member(tmp_path, catalog, registry, requested)
    query, result = router.search_final_state_effect(
        requested,
        equivalence_scope=EquivalenceScope.FINAL_STATE_ONLY,
    )
    pending = router.prepare_selection(query, result, result.candidates[0].skill_id)
    with pytest.raises(SkillDispatchError, match="hash mismatch"):
        validate_selection_receipt(replace(pending, **{field: value}))


def test_stale_equivalence_membership_fails_dispatch(
    m252_catalog, tmp_path: Path
) -> None:
    _, catalog, _, registry = m252_catalog
    requested = build_family_specification(
        SemanticFamily.MERGE_TWO, sources=("A", "B"), destination="C"
    )
    router, _, memory = _without_exact_member(tmp_path, catalog, registry, requested)
    query, result = router.search_final_state_effect(
        requested,
        equivalence_scope=EquivalenceScope.FINAL_STATE_ONLY,
    )
    candidate = result.candidates[0]
    selection = router.confirm_selection(
        router.prepare_selection(query, result, candidate.skill_id),
        identity="reviewer",
        decision=ConfirmationDecision.CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION,
    )
    memory.deprecate(candidate.rule_id)
    memory.save(router.memory_path)
    with pytest.raises(SkillRegistryStaleError):
        router.dispatch(
            query=query,
            result=result,
            selection=selection,
            proposal=catalog.proposals[candidate.rule_id],
            installed_receipt=catalog.receipts[candidate.rule_id],
            initial_state={"R0": 2, "R1": 3, "R2": 5, "R3": 7},
        )


def test_v2_registry_is_rejected_with_rebuild_instruction(
    m252_catalog, tmp_path: Path
) -> None:
    _, _, _, registry = m252_catalog
    path = tmp_path / "registry.json"
    registry.save(path)
    row = json.loads(path.read_text(encoding="utf-8"))
    row["schema_version"] = 2
    body = {key: value for key, value in row.items() if key != "content_sha256"}
    row["content_sha256"] = content_hash(body)
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(SkillRegistryIntegrityError, match="v2 must be rebuilt"):
        SkillRegistry.load(path)


def test_learned_result_has_no_exact_or_equivalence_authority(m252_catalog) -> None:
    root, catalog, _, registry = m252_catalog
    _, result = _router(root, catalog, registry, "learned-authority").search_assistive(
        "Move A into B", "en"
    )
    learned = replace(result, retrieval_mode=RetrievalMode.LEARNED_BI_ENCODER)
    fake_exact = replace(
        learned,
        status=SearchStatus.EXACT_MATCH,
        exact_match=True,
        result_hash="0" * 64,
    )
    fake_exact = replace(fake_exact, result_hash=_result_content_hash(fake_exact))
    with pytest.raises(ValueError, match="Assistive retrieval"):
        validate_search_result(fake_exact)

    fake_equivalent = replace(
        learned,
        status=SearchStatus.FINAL_STATE_EQUIVALENT,
        equivalence_scope=EquivalenceScope.FINAL_STATE_ONLY,
        result_hash="0" * 64,
    )
    fake_equivalent = replace(
        fake_equivalent, result_hash=_result_content_hash(fake_equivalent)
    )
    with pytest.raises(ValueError, match="Only trusted"):
        validate_search_result(fake_equivalent)
