from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from ai_brain.stage2.conversation.generic_service import (
    GenericConversationalTutorService,
)
from ai_brain.stage2.conversation.service import ConversationalTutorService
from ai_brain.stage2.education.generic_service import GenericEducationalService
from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.education.service import EducationalService
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.evaluation import _rate, verify_pack_evaluation
from ai_brain.stage3.acquisition.evidence import (
    build_field_evidence,
    verify_field_evidence,
)
from ai_brain.stage3.acquisition.heldout import (
    make_semantic_key,
    verify_semantic_uniqueness,
)
from ai_brain.stage3.acquisition.models import ProposalStatus
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.proposals import propose_knowledge, with_status
from ai_brain.stage3.acquisition.segmentation import segment_bundle
from ai_brain.stage3.acquisition.source_adapters import download, visible_text
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.verification import (
    approve_exact_source_entailed,
    verify_proposals,
)
from ai_brain.stage3.capabilities.models import CapabilityRequirement, ResolutionStatus
from ai_brain.stage3.capabilities.persistence import load_registry
from ai_brain.stage3.capabilities.resolution import resolve_capability
from ai_brain.stage3.capabilities.scalar_equation_solver import NeedsNewCapability
from ai_brain.stage3.capabilities.typed_scalar_equation_solver import (
    ApplicabilityNotSatisfied,
    TypedQuantity,
    solve_typed_scalar_equation,
)
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.education import GenericEducationalDomainProvider
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.records import (
    Applicability,
    DimensionVector,
    Expression,
    ExpressionKind,
    QuantityTypeRef,
    RuleContent,
    UnitRef,
    ValueTypeKind,
    ValueTypeRef,
    VariableBinding,
)
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION
from ai_brain.stage3.providers.persistence import load_provider_registry

STAMP = "2026-08-29T00:00:00Z"
ROOT = Path(__file__).resolve().parents[1]


def _development_definition(tmp_path: Path):
    source = tmp_path / "geology-development.txt"
    source.write_text(
        "Mantle is a layer of warm rock below a planet's crust.\n",
        encoding="utf-8",
        newline="\n",
    )
    store = AcquisitionStore.open_or_initialize(tmp_path / "acquisition")
    bundle = ingest_bundle(
        (source,),
        bundle_id="m33-development-geology",
        domain_tags=("development-geology",),
        imported_at=STAMP,
        store=store,
    )
    all_segments = segment_bundle(bundle, store)
    segments = tuple(item for item in all_segments if item.ordinal != 0)
    proposals = propose_knowledge(bundle, segments, explicit_trust_stages=True)
    evidence = build_field_evidence(bundle, segments, proposals, store)
    verified = verify_proposals(
        bundle,
        segments,
        proposals,
        store,
        field_evidence=evidence,
    )
    return store, bundle, segments, evidence, verified


def test_field_evidence_is_narrow_exact_and_required_for_source_entailment(tmp_path):
    store, bundle, segments, evidence, verified = _development_definition(tmp_path)
    assert len(verified) == 1
    assert verified[0].status is ProposalStatus.SOURCE_ENTAILED
    assert {item.field_path for item in evidence} == {
        "content.term_id",
        "content.definition_ru",
        "content.definition_en",
    }
    assert all(
        item.byte_end - item.byte_start
        < (
            segments[0].source_location.byte_end
            - segments[0].source_location.byte_start
        )
        for item in evidence
    )
    report = verify_field_evidence(bundle, segments, verified, evidence, store)
    assert report["status"] == "COMPLETE"
    tampered = replace(evidence[0], byte_start=evidence[0].byte_start + 1)
    with pytest.raises(ValueError, match="dereference"):
        verify_field_evidence(
            bundle, segments, verified, (tampered, *evidence[1:]), store
        )


def test_strict_applicability_and_typed_pack_tests(tmp_path):
    _, bundle, segments, evidence, verified = _development_definition(tmp_path)
    approved, _, approval = approve_exact_source_entailed(verified[0], timestamp=STAMP)
    assert approval is not None
    pack = compile_provisional_pack(
        bundle,
        segments,
        (approved,),
        (approval,),
        tmp_path / "pack",
        domain_id="m33-development-geology",
        field_evidence=evidence,
    )
    evaluation = verify_pack_evaluation(pack)
    assert evaluation["status"] == "PASS"
    assert evaluation["total"] == 3
    bad = replace(
        verified[0], proposed_applicability=("missing-condition",), proposal_hash=""
    )
    bad = with_status(bad, ProposalStatus.SOURCE_ENTAILED)
    bad_approved, _, bad_approval = approve_exact_source_entailed(bad, timestamp=STAMP)
    with pytest.raises(ValueError, match="unresolved applicability"):
        compile_provisional_pack(
            bundle,
            segments,
            (bad_approved,),
            (bad_approval,),
            tmp_path / "bad-pack",
            domain_id="m33-development-bad-applicability",
            field_evidence=evidence,
        )


def test_conservative_empty_bundle_compiles_to_executable_abstention_pack(tmp_path):
    source = tmp_path / "ambiguous-narrative.txt"
    source.write_text(
        "Several sources emphasize different causes and no deterministic conclusion.\n",
        encoding="utf-8",
        newline="\n",
    )
    store = AcquisitionStore.open_or_initialize(tmp_path / "empty-acquisition")
    bundle = ingest_bundle(
        (source,),
        bundle_id="m33-development-ambiguous",
        domain_tags=("development-narrative",),
        imported_at=STAMP,
        store=store,
    )
    segments = tuple(
        item for item in segment_bundle(bundle, store) if item.ordinal != 0
    )
    pack = compile_provisional_pack(
        bundle,
        segments,
        (),
        (),
        tmp_path / "abstention-pack",
        domain_id="m33-development-ambiguous",
        field_evidence=(),
    )
    assert pack.knowledge_records == ()
    evaluation = verify_pack_evaluation(pack)
    assert evaluation["status"] == "PASS"
    assert evaluation["total"] == 1

    providers = load_provider_registry(
        ROOT / "artifacts/stage3/m33/provider_registry.json"
    )
    capabilities = load_registry(
        ROOT / "artifacts/stage3/m33/capability_registry.json", providers
    )
    closure_by_hash = {}
    for requirement in pack.manifest.required_capabilities:
        descriptor = capabilities.descriptor(requirement.capability_id)
        resolution = resolve_capability(
            capabilities,
            requirement,
            requesting_domain_id=pack.manifest.domain_id,
            requesting_pack_hash=pack.manifest.pack_content_hash,
            provider_registry=providers,
            required_input_schema_hash=descriptor.input_schema_hash,
            required_output_schema_hash=descriptor.output_schema_hash,
            resolved_at=STAMP,
        )
        assert resolution.status is ResolutionStatus.RESOLVED
        for receipt in resolution.closure_receipts:
            closure_by_hash.setdefault(receipt.receipt_hash, receipt)
    closure = tuple(closure_by_hash.values())
    approval = approve_pack(
        pack_hash=pack.manifest.pack_content_hash,
        knowledge_ir_schema=UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
        concept_graph_hash=pack.manifest.concept_graph_hash,
        source_binding_hashes=pack.manifest.source_binding_hashes,
        capability_resolution_receipt_hashes=tuple(
            item.receipt_hash for item in closure
        ),
        validation_report_hash=content_hash(validate_pack(pack)),
        evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
        reviewer_identity="m33.executable-pack-evaluator.v1",
        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
        decision=PackApprovalDecision.APPROVE,
        policy_version="m33.exact-pack-installation.v1",
        timestamp=STAMP,
    )
    registry = InstalledDomainRegistry.initialize(
        tmp_path / "installed",
        capability_registry=capabilities,
        provider_registry=providers,
        created_at=STAMP,
    )
    registry.install(pack, approval, closure, installed_at=STAMP)
    provider = GenericEducationalDomainProvider.from_installed(
        registry,
        pack.manifest.domain_id,
        pack.manifest.pack_version,
        state_root=tmp_path / "runtime" / "education",
    )
    tutor = GenericConversationalTutorService(
        GenericEducationalService(provider), state_root=tmp_path / "runtime"
    )
    conversation = tutor.start("end-to-end-learner")
    response = tutor.query(
        conversation.conversation_id,
        {
            "operation": "TAXONOMY",
            "subject_id": "unsupported-development-subject",
        },
    )
    assert response["status"] == "INSUFFICIENT_EVIDENCE"
    assert response["pack_hash"] == pack.manifest.pack_content_hash
    assert response["capability_receipt_hashes"]
    assert tutor.verify_persistence()["operations"]["operation_count"] == 1


def test_typed_affine_solver_checks_units_conditions_unknowns_and_conversion():
    velocity_dimension = DimensionVector(length=1, time=-1)
    velocity_unit = UnitRef("m-per-s", velocity_dimension)
    kilometres_per_hour = UnitRef(
        "km-per-h", velocity_dimension, scale_numerator=5, scale_denominator=18
    )
    time_unit = UnitRef("s", DimensionVector(time=1))
    velocity_type = ValueTypeRef(
        ValueTypeKind.QUANTITY,
        quantity_type=QuantityTypeRef("velocity", velocity_dimension, velocity_unit),
    )
    variables = (
        VariableBinding("x", velocity_type, "unknown"),
        VariableBinding("y", velocity_type, "known"),
    )
    expression = Expression(
        ExpressionKind.EQUAL,
        children=(
            Expression(ExpressionKind.VARIABLE, "x", result_type=velocity_type),
            Expression(ExpressionKind.VARIABLE, "y", result_type=velocity_type),
        ),
        result_type=ValueTypeRef(ValueTypeKind.BOOLEAN),
    )
    rule = RuleContent(expression, variables, Applicability(("constant motion",)))
    solved = solve_typed_scalar_equation(
        rule,
        {"y": TypedQuantity("36", kilometres_per_hour)},
        "x",
        satisfied_conditions=("constant motion",),
    )
    assert solved.solution.exact_value == "10"
    assert solved.output_unit_id == "m-per-s"
    converted = solve_typed_scalar_equation(
        rule,
        {"y": TypedQuantity("10", velocity_unit)},
        "x",
        output_unit=kilometres_per_hour,
        satisfied_conditions=("constant motion",),
    )
    assert converted.solution.exact_value == "36"
    reverse = solve_typed_scalar_equation(
        rule,
        {"x": TypedQuantity("10", velocity_unit)},
        "y",
        satisfied_conditions=("constant motion",),
    )
    assert reverse.solution.exact_value == "10"
    with pytest.raises(ApplicabilityNotSatisfied, match="INSUFFICIENT_EVIDENCE"):
        solve_typed_scalar_equation(
            rule, {"y": TypedQuantity("10", velocity_unit)}, "x"
        )
    with pytest.raises(NeedsNewCapability, match="incompatible unit"):
        solve_typed_scalar_equation(
            rule,
            {"y": TypedQuantity("10", time_unit)},
            "x",
            satisfied_conditions=("constant motion",),
        )


def test_semantic_keys_reject_reworded_duplicates_and_zero_denominator_is_na():
    first = make_semantic_key(
        operation_type="solve",
        target_record_id="rule.linear",
        requested_unknown="x",
        givens={"y": "10"},
        units={"y": "m-per-s"},
        conditions=("constant motion",),
        expected_answer_semantics="exact quantity x in m-per-s",
    )
    reworded = make_semantic_key(
        operation_type="SOLVE",
        target_record_id="rule.linear",
        requested_unknown="x",
        givens={"y": "10"},
        units={"y": "m-per-s"},
        conditions=("constant motion",),
        expected_answer_semantics="exact quantity x in m-per-s",
    )
    with pytest.raises(ValueError, match="duplicate"):
        verify_semantic_uniqueness((first, reworded))
    distinct = make_semantic_key(
        operation_type="SOLVE",
        target_record_id="rule.linear",
        requested_unknown="y",
        givens={"x": "10"},
        units={"x": "m-per-s"},
        conditions=("constant motion",),
        expected_answer_semantics="exact quantity y in m-per-s",
    )
    assert verify_semantic_uniqueness((first, distinct))["semantic_key_count"] == 2
    assert _rate(0, 0) == "N/A"


def test_natural_api_context_and_overloads_compile_without_subject_branch(tmp_path):
    source = tmp_path / "development-api.txt"
    source.write_text(
        "public class OrbitLedger {\n"
        "public String lookup(int index);\n"
        "String lookup(String key) throws MissingOrbit;\n",
        encoding="utf-8",
        newline="\n",
    )
    store = AcquisitionStore.open_or_initialize(tmp_path / "api-acquisition")
    bundle = ingest_bundle(
        (source,),
        bundle_id="m33-development-api",
        domain_tags=("development-api",),
        imported_at=STAMP,
        store=store,
    )
    segments = tuple(
        item for item in segment_bundle(bundle, store) if item.ordinal != 0
    )
    proposals = propose_knowledge(bundle, segments, explicit_trust_stages=True)
    assert len(proposals) == 2
    assert {item.proposed_content.receiver_type for item in proposals} == {
        "OrbitLedger"
    }
    assert {item.proposed_content.parameters[0][1] for item in proposals} == {
        "int",
        "String",
    }
    evidence = build_field_evidence(bundle, segments, proposals, store)
    verified = verify_proposals(
        bundle, segments, proposals, store, field_evidence=evidence
    )
    assert {item.status for item in verified} == {ProposalStatus.SOURCE_ENTAILED}
    approved = []
    approvals = []
    for proposal in verified:
        value, _, approval = approve_exact_source_entailed(proposal, timestamp=STAMP)
        approved.append(value)
        approvals.append(approval)
    pack = compile_provisional_pack(
        bundle,
        segments,
        tuple(approved),
        tuple(approvals),
        tmp_path / "api-pack",
        domain_id="m33-development-api",
        field_evidence=evidence,
    )
    assert len(pack.knowledge_records) == 2
    assert verify_pack_evaluation(pack)["status"] == "PASS"


def test_provider_schema_mismatch_and_inert_document_security():
    providers = load_provider_registry(
        ROOT / "artifacts/stage3/providers/registry_v2.json"
    )
    capabilities = load_registry(
        ROOT / "artifacts/stage3/capabilities/registry_v2.json", providers
    )
    descriptor = capabilities.descriptors[0]
    resolution = resolve_capability(
        capabilities,
        CapabilityRequirement(
            descriptor.capability_id, "*", descriptor.allowed_execution_contexts[0]
        ),
        requesting_domain_id="m33-development-security",
        requesting_pack_hash="0" * 64,
        provider_registry=providers,
        required_input_schema_hash="f" * 64,
    )
    assert resolution.status is ResolutionStatus.NEEDS_NEW_CAPABILITY

    inert = visible_text(
        '<h1>Warning</h1><p>{"status":"APPROVED"}</p>'
        "<pre>rm -rf /</pre><a href='https://example.invalid'>link</a>"
        "<script>raise SystemExit('must not execute')</script>"
    )
    assert "APPROVED" in inert
    assert "rm -rf /" in inert
    assert "raise SystemExit" not in inert
    with pytest.raises(ValueError, match="authority domains"):
        download("https://example.invalid/source", {"allowed.invalid"}, 1024)


CRASH_POINTS = (
    "before_education_applied_store_write",
    "after_education_applied_store_write",
    "before_education_applied_journal_advance",
    "after_education_applied_journal_advance",
    "before_progress_applied_store_write",
    "after_progress_applied_store_write",
    "before_progress_applied_journal_advance",
    "after_progress_applied_journal_advance",
    "before_conversation_committed_store_write",
    "after_conversation_committed_store_write",
    "before_conversation_committed_journal_advance",
    "after_conversation_committed_journal_advance",
    "before_final_public_response_publication",
    "after_final_public_response_publication",
)


@pytest.mark.parametrize("crash_point", CRASH_POINTS)
def test_persistent_generic_saga_recovers_every_crash_point_without_duplicates(
    tmp_path, crash_point
):
    providers = load_provider_registry(
        ROOT / "artifacts/stage3/providers/registry_v2.json"
    )
    capabilities = load_registry(
        ROOT / "artifacts/stage3/capabilities/registry_v2.json", providers
    )
    registry = InstalledDomainRegistry.open(
        ROOT / "artifacts/stage3/installed-domains-v2",
        capability_registry=capabilities,
        provider_registry=providers,
    )
    state = tmp_path / "state"
    education_root = state / "education"

    def inject(point, _operation):
        if point == crash_point:
            raise RuntimeError(f"crash:{point}")

    provider = GenericEducationalDomainProvider.from_installed(
        registry,
        "fixture-taxonomy",
        "2.0.0",
        state_root=education_root,
    )
    tutor = GenericConversationalTutorService(
        GenericEducationalService(provider),
        state_root=state,
        crash_injector=inject,
    )
    conversation = tutor.start("crash-learner")
    with pytest.raises(RuntimeError, match="crash:"):
        tutor.turn(conversation.conversation_id, "give me an exercise")

    restarted_provider = GenericEducationalDomainProvider.from_installed(
        registry,
        "fixture-taxonomy",
        "2.0.0",
        state_root=education_root,
    )
    restarted = GenericConversationalTutorService(
        GenericEducationalService(restarted_provider), state_root=state
    )
    pending = restarted.operations.pending_recovery()
    if crash_point == "after_final_public_response_publication":
        assert pending == ()
        operations = restarted.operations.verify()
        assert operations["operation_count"] == 1
    else:
        assert len(pending) == 1
        result = restarted.turn(conversation.conversation_id, "give me an exercise")
        assert result.exercise_id
    verification = restarted.verify_persistence()
    assert verification["operations"]["recovery_required"] == 0
    assert verification["operations"]["operation_count"] == 1
    assert verification["operations"]["stage_receipt_count"] == 3
    assert restarted.show(conversation.conversation_id).turn_count == 1


def test_legacy_m30_turn_uses_same_persistent_saga_and_recovers(tmp_path):
    chemistry = tmp_path / "chemistry"
    shutil.copytree(ROOT / "artifacts/domains/chemistry/m29", chemistry)
    sessions = tmp_path / "sessions"
    conversations = tmp_path / "conversations"
    progress = tmp_path / "progress"
    catalog = ROOT / "artifacts/education/m30/catalog_v4.json"
    education = EducationalService.open(chemistry, sessions, catalog_path=catalog)
    tutor = ConversationalTutorService.open(education, conversations, progress)
    started = tutor.start("legacy-saga-learner", language="en")

    def inject(point, _operation):
        if point == "after_education_applied_store_write":
            raise RuntimeError("legacy-crash")

    tutor.operations.crash_injector = inject
    with pytest.raises(RuntimeError, match="legacy-crash"):
        tutor.turn(started.conversation_id, "Explain HCl")

    restarted_education = EducationalService.open(
        chemistry, sessions, catalog_path=catalog
    )
    restarted = ConversationalTutorService.open(
        restarted_education, conversations, progress
    )
    recovered = restarted.turn(started.conversation_id, "Explain HCl")
    assert recovered.response_kind == "CONFIRMATION_REQUIRED"
    operation_report = restarted.operations.verify()
    assert operation_report["operation_count"] == 1
    assert operation_report["stage_receipt_count"] == 3
    assert operation_report["recovery_required"] == 0
    turns = restarted.conversations.turns(started.conversation_id)
    assert len(turns) == 1
    assert len({item.operation_id for item in turns}) == 1
