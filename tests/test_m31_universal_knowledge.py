from __future__ import annotations

import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.conversation.models import ConversationIntent, ConversationState
from ai_brain.stage2.conversation.operations import (
    TutorOperationJournal,
    TutorOperationStatus,
)
from ai_brain.stage2.conversation.state_machine import require_action_allowed
from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.capabilities.models import CapabilityRequirement, ResolutionStatus
from ai_brain.stage3.capabilities.persistence import load_registry
from ai_brain.stage3.capabilities.resolution import resolve_capability
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.runtime import GenericDomainRuntime
from ai_brain.stage3.domains.validation import hash_without, validate_pack
from ai_brain.stage3.knowledge_ir.records import (
    EpistemicCharacter,
    Expression,
    ExpressionKind,
    KnowledgeKind,
)
from ai_brain.stage3.knowledge_ir.serialization import dump_record, load_record
from ai_brain.stage3.knowledge_ir.validation import (
    record_content_hash,
    validate_expression,
)
from ai_brain.stage3.knowledge_ir.version import (
    CAPABILITY_REGISTRY_SCHEMA_VERSION,
    CAPABILITY_RESOLUTION_SCHEMA_VERSION,
    CONCEPT_GRAPH_SCHEMA_VERSION,
    DOMAIN_PACK_SCHEMA_VERSION,
    DOMAIN_REGISTRY_SCHEMA_VERSION,
    PACK_APPROVAL_SCHEMA_VERSION,
    UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
    UNIVERSAL_KNOWLEDGE_IR_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]
CHEMISTRY = ROOT / "artifacts/domains/chemistry/generic-v1"
TAXONOMY = ROOT / "tests/fixtures/domains/taxonomy-v1"
QUANTITY = ROOT / "tests/fixtures/domains/quantity-equation-v1"
CAPABILITIES = ROOT / "artifacts/stage3/capabilities/registry_v1.json"
INSTALLED = ROOT / "artifacts/stage3/installed-domains"


def test_versions_and_complete_typed_vocabulary():
    assert UNIVERSAL_KNOWLEDGE_IR_VERSION == "1.0.0"
    assert {
        UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
        DOMAIN_PACK_SCHEMA_VERSION,
        CAPABILITY_REGISTRY_SCHEMA_VERSION,
        DOMAIN_REGISTRY_SCHEMA_VERSION,
        CONCEPT_GRAPH_SCHEMA_VERSION,
        PACK_APPROVAL_SCHEMA_VERSION,
        CAPABILITY_RESOLUTION_SCHEMA_VERSION,
    } == {1}
    assert len(KnowledgeKind) == 25
    assert len(EpistemicCharacter) == 7


def test_ir_roundtrip_and_malformed_hash_fail_closed():
    record = load_pack(CHEMISTRY).knowledge_records[0]
    text = dump_record(record)
    assert load_record(text) == record
    row = json.loads(text)
    row["content_hash"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        load_record(json.dumps(row))


@pytest.mark.parametrize(
    "value",
    ("eval('x')", "__import__('os')", "exec('x')", "subprocess.run"),
)
def test_expression_code_injection_is_non_executable_and_rejected(value):
    with pytest.raises(ValueError, match="source text"):
        validate_expression(Expression(ExpressionKind.CONSTANT, value))


def test_expression_arity_depth_and_power_are_bounded():
    with pytest.raises(ValueError, match="arity"):
        validate_expression(Expression(ExpressionKind.ADD, children=()))
    with pytest.raises(ValueError, match="exponent"):
        validate_expression(
            Expression(
                ExpressionKind.POWER,
                children=(
                    Expression(ExpressionKind.CONSTANT, 2),
                    Expression(ExpressionKind.CONSTANT, 99),
                ),
            )
        )


def test_three_data_only_packs_use_one_runtime_without_core_changes():
    packs = tuple(load_pack(path) for path in (CHEMISTRY, TAXONOMY, QUANTITY))
    summaries = tuple(
        GenericDomainRuntime(pack).public_domain_summary() for pack in packs
    )
    assert [item["domain_id"] for item in summaries] == [
        "chemistry",
        "fixture-taxonomy",
        "fixture-quantity-equation",
    ]
    assert all(validate_pack(pack)["status"] == "VERIFIED" for pack in packs)


def test_generic_core_has_no_chemistry_import_or_domain_branch():
    files = tuple((ROOT / "src/ai_brain/stage3").rglob("*.py"))
    assert not [
        path
        for path in files
        if "chemistry" in path.read_text(encoding="utf-8").casefold()
    ]


def test_capabilities_resolve_exactly_and_never_fall_back():
    registry = load_registry(CAPABILITIES)
    providers = {
        item.provider_id: item.provider_implementation_hash
        for item in registry.descriptors
    }
    known = registry.descriptors[0]
    result = resolve_capability(
        registry,
        CapabilityRequirement(
            known.capability_id, "*", known.allowed_execution_contexts[0]
        ),
        requesting_domain_id="test",
        requesting_pack_hash="0" * 64,
        provider_hashes=providers,
    )
    assert result.status is ResolutionStatus.RESOLVED
    providers[known.provider_id] = "0" * 64
    with pytest.raises(ValueError, match="implementation"):
        resolve_capability(
            registry,
            CapabilityRequirement(
                known.capability_id, "*", known.allowed_execution_contexts[0]
            ),
            requesting_domain_id="test",
            requesting_pack_hash="0" * 64,
            provider_hashes=providers,
        )
    unknown = resolve_capability(
        registry,
        CapabilityRequirement("missing.capability.v1", "*", "USER_RUNTIME"),
        requesting_domain_id="test",
        requesting_pack_hash="0" * 64,
        provider_hashes={
            item.provider_id: item.provider_implementation_hash
            for item in registry.descriptors
        },
    )
    assert unknown.status is ResolutionStatus.NEEDS_NEW_CAPABILITY


def test_installed_registry_backup_restore_and_history_safe_uninstall(tmp_path):
    registry = InstalledDomainRegistry.open(INSTALLED)
    assert registry.verify()["installed_count"] == 1
    backup = tmp_path / "registry.sqlite3"
    assert registry.backup(backup)["status"] == "BACKED_UP"
    restored = InstalledDomainRegistry.restore(backup, tmp_path / "restored")
    item = restored.show("chemistry", "generic-v1")
    result = restored.uninstall(item.domain_id, item.pack_version)
    assert result["history_status"] == "HISTORY_VALID_BUT_PACK_UNAVAILABLE"


def test_pack_hash_and_unknown_files_fail_closed(tmp_path):
    pack = load_pack(TAXONOMY)
    with pytest.raises(ValueError, match="content hash"):
        validate_pack(
            replace(pack, manifest=replace(pack.manifest, pack_content_hash="0" * 64))
        )


def test_strict_pack_loader_rejects_duplicate_jsonl_keys_and_nested_entries(tmp_path):
    duplicate = tmp_path / "duplicate"
    shutil.copytree(TAXONOMY, duplicate)
    line = (duplicate / "knowledge.jsonl").read_text(encoding="utf-8").splitlines()[0]
    (duplicate / "knowledge.jsonl").write_text(
        line[:-1] + ',"knowledge_id":"shadow"}\n',
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_pack(duplicate)

    nested = tmp_path / "nested"
    shutil.copytree(TAXONOMY, nested)
    (nested / "escape").mkdir()
    with pytest.raises(ValueError, match="unexpected domain pack entry"):
        load_pack(nested)


def test_pack_authority_closure_rejects_dangling_provenance_and_capability():
    pack = load_pack(TAXONOMY)
    first = replace(pack.knowledge_records[0], provenance_refs=("missing.source",))
    first = replace(first, content_hash=record_content_hash(first))
    records = (first, *pack.knowledge_records[1:])
    manifest = replace(
        pack.manifest,
        knowledge_record_hashes=tuple(item.content_hash for item in records),
    )
    manifest_body = asdict(manifest)
    manifest_body.pop("pack_content_hash")
    manifest = replace(manifest, pack_content_hash=content_hash(manifest_body))
    with pytest.raises(ValueError, match="dangling provenance"):
        validate_pack(replace(pack, manifest=manifest, knowledge_records=records))

    family = replace(
        pack.exercise_families[0], required_capabilities=("missing.capability",)
    )
    family = replace(family, family_hash=hash_without(family, "family_hash"))
    with pytest.raises(ValueError, match="undeclared capability"):
        validate_pack(replace(pack, exercise_families=(family,)))


def test_pack_source_hashes_and_offline_evaluation_fail_closed():
    pack = load_pack(TAXONOMY)
    source = replace(pack.source_bindings[0], source_chain_hash="not-a-hash")
    source = replace(source, binding_hash=hash_without(source, "binding_hash"))
    with pytest.raises(ValueError, match="source reference"):
        validate_pack(replace(pack, source_bindings=(source,)))

    evaluation = {**pack.evaluation_manifest, "runtime_network": True}
    manifest = replace(pack.manifest, evaluation_manifest_hash=content_hash(evaluation))
    manifest_body = asdict(manifest)
    manifest_body.pop("pack_content_hash")
    manifest = replace(
        manifest,
        pack_content_hash=content_hash(manifest_body),
    )
    with pytest.raises(ValueError, match="offline test policy"):
        validate_pack(replace(pack, manifest=manifest, evaluation_manifest=evaluation))


def test_model_cannot_self_approve_pack():
    pack = load_pack(TAXONOMY)
    with pytest.raises(ValueError, match="MODEL or blank reviewer"):
        approve_pack(
            pack_hash=pack.manifest.pack_content_hash,
            knowledge_ir_schema=1,
            concept_graph_hash=pack.manifest.concept_graph_hash,
            source_binding_hashes=pack.manifest.source_binding_hashes,
            capability_resolution_receipt_hashes=(),
            validation_report_hash="0" * 64,
            evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
            reviewer_identity="self",
            reviewer_type=ActorIdentityType.MODEL,
            decision=PackApprovalDecision.APPROVE,
            policy_version="m31.1",
            timestamp="2026-08-29T00:00:00Z",
        )


def test_awaiting_confirmation_only_allows_bounded_control_actions():
    for allowed in (
        ConversationIntent.CONFIRM_PENDING_ACTION,
        ConversationIntent.CANCEL_PENDING_ACTION,
        ConversationIntent.PAUSE,
        ConversationIntent.END_CONVERSATION,
    ):
        require_action_allowed(
            ConversationState.AWAITING_CONFIRMATION,
            allowed,
            active_session=True,
            pending_action=True,
        )
    with pytest.raises(ValueError, match="only confirm"):
        require_action_allowed(
            ConversationState.AWAITING_CONFIRMATION,
            ConversationIntent.REQUEST_PROGRESS,
            active_session=True,
            pending_action=True,
        )


@pytest.mark.parametrize(
    "crash_stage",
    tuple(
        item.value
        for item in TutorOperationStatus
        if item
        not in {TutorOperationStatus.RECOVERY_REQUIRED, TutorOperationStatus.FAILED}
    ),
)
def test_operation_journal_persists_every_injected_crash_stage(tmp_path, crash_stage):
    def crash(stage, _operation):
        if stage == crash_stage:
            raise RuntimeError("injected crash")

    journal = TutorOperationJournal.open_or_initialize(tmp_path / crash_stage)
    journal.crash_injector = crash
    try:
        operation = journal.prepare(
            learner_id="learner",
            conversation_id="conversation",
            intent="REQUEST_EXERCISE",
            input_hash="0" * 64,
        )
        for status in (
            TutorOperationStatus.EDUCATION_APPLIED,
            TutorOperationStatus.PROGRESS_APPLIED,
            TutorOperationStatus.CONVERSATION_COMMITTED,
            TutorOperationStatus.COMPLETED,
        ):
            operation = journal.advance(operation, status, status.value)
    except RuntimeError:
        persisted = journal.pending_recovery()
        if crash_stage == TutorOperationStatus.COMPLETED.value:
            assert not persisted
        else:
            assert persisted[0].status.value == crash_stage
