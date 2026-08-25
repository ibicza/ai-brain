from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

import ai_brain.stage1.service as service_module
from ai_brain.rules.memory import (
    RuleMemory,
    RuleMemoryIOError,
    RuleMemoryRecoveryError,
    RuleMemoryRecoveryRequiredError,
    StoredRuleParseError,
)
from ai_brain.stage1.audit import reconstruct_audit
from ai_brain.stage1.execution import BoundedExecutionError
from ai_brain.stage1.models import ExecutionFailureCode, SemanticFamily
from ai_brain.stage1.service import Stage1Service
from ai_brain.stage1.specifications import build_family_specification


def _row(family: SemanticFamily, source: str, destination: str) -> dict:
    specification = build_family_specification(
        family, sources=(source,), destination=destination
    )
    return json.loads(json.dumps(asdict(specification)))


def _service(
    directory: Path,
    *,
    audit_path: Path | None = None,
    proposal_ids=None,
) -> Stage1Service:
    return Stage1Service(
        memory_path=directory / "memory.json",
        audit_path=audit_path or directory / "audit.jsonl",
        proposal_id_factory=proposal_ids,
    )


def _to_reviewed(service: Stage1Service, row: dict):
    proposal = service.propose_form(row)
    proposal, _ = service.review(proposal)
    return proposal


def _complete_reviewed(service: Stage1Service, proposal):
    proposal, candidate = service.verify(proposal)
    proposal, review = service.review_verification(proposal, candidate)
    proposal, approval = service.approve(
        proposal, candidate, review, identity="m241a-test"
    )
    proposal, record, receipt = service.install(proposal, candidate, review, approval)
    return proposal, candidate, review, approval, record, receipt


@pytest.mark.parametrize("edit_after_verification", [False, True])
def test_revision_chain_preserves_superseded_history(
    tmp_path: Path, edit_after_verification: bool
) -> None:
    service = _service(tmp_path, proposal_ids=lambda: "proposal-revision")
    proposal = _to_reviewed(service, _row(SemanticFamily.DRAIN, "A", "B"))
    if edit_after_verification:
        proposal, _ = service.verify(proposal)
    proposal = service.edit(proposal, _row(SemanticFamily.DRAIN, "A", "C"))
    proposal, _ = service.review(proposal)
    proposal, _, _, _, record, receipt = _complete_reviewed(service, proposal)
    result = reconstruct_audit(
        service.audit,
        RuleMemory.load(service.memory_path),
        proposal.proposal_id,
        receipt=receipt,
    )
    assert result.valid, result.errors
    assert result.active_revision == 2
    assert [item.status for item in result.revisions] == ["SUPERSEDED", "ACTIVE"]
    assert result.installed_rule_id == record.rule_id


def test_failed_verification_edit_retry_is_reconstructable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path, proposal_ids=lambda: "proposal-retry")
    proposal = _to_reviewed(service, _row(SemanticFamily.DRAIN, "A", "B"))
    original = service_module.verify_proposal
    monkeypatch.setattr(
        service_module,
        "verify_proposal",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("rejected")),
    )
    with pytest.raises(ValueError, match="rejected"):
        service.verify(proposal)
    monkeypatch.setattr(service_module, "verify_proposal", original)
    proposal = service.edit(proposal, _row(SemanticFamily.DRAIN, "A", "C"))
    proposal, _ = service.review(proposal)
    proposal, _, _, _, _, receipt = _complete_reviewed(service, proposal)
    result = reconstruct_audit(
        service.audit,
        RuleMemory.load(service.memory_path),
        proposal.proposal_id,
        receipt=receipt,
    )
    assert result.valid, result.errors
    assert "VERIFICATION_FAILED" in result.revisions[0].event_types


def test_identical_inputs_have_independent_opaque_ids_and_audits(
    tmp_path: Path,
) -> None:
    identifiers = iter(("opaque-one", "opaque-two"))
    audit_path = tmp_path / "shared-audit.jsonl"
    first = _service(
        tmp_path / "first", audit_path=audit_path, proposal_ids=identifiers.__next__
    )
    second = _service(
        tmp_path / "second", audit_path=audit_path, proposal_ids=identifiers.__next__
    )
    row = _row(SemanticFamily.DRAIN, "A", "B")
    first_proposal, *first_artifacts = _complete_reviewed(
        first, _to_reviewed(first, row)
    )
    second_proposal, *second_artifacts = _complete_reviewed(
        second, _to_reviewed(second, row)
    )
    first_receipt = first_artifacts[-1]
    second_receipt = second_artifacts[-1]
    assert first_proposal.proposal_id != second_proposal.proposal_id
    received = [
        item for item in first.audit.replay() if item.event_type == "PROPOSAL_RECEIVED"
    ]
    assert (
        received[0].payload["original_input_hash"]
        == received[1].payload["original_input_hash"]
    )
    for service, proposal, receipt in (
        (first, first_proposal, first_receipt),
        (second, second_proposal, second_receipt),
    ):
        result = reconstruct_audit(
            service.audit,
            RuleMemory.load(service.memory_path),
            proposal.proposal_id,
            receipt=receipt,
        )
        assert result.valid, result.errors
        assert all(
            item.proposal_id == proposal.proposal_id
            for item in service.audit.replay()
            if item.proposal_id == proposal.proposal_id
        )


def test_stale_review_approval_and_receipt_are_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path, proposal_ids=lambda: "proposal-stale")
    proposal = _to_reviewed(service, _row(SemanticFamily.DRAIN, "A", "B"))
    verified, old_candidate = service.verify(proposal)
    verified_reviewed, old_review = service.review_verification(verified, old_candidate)
    _, old_approval = service.approve(
        verified_reviewed, old_candidate, old_review, identity="old"
    )
    edited = service.edit(verified_reviewed, _row(SemanticFamily.DRAIN, "A", "C"))
    reviewed, _ = service.review(edited)
    with pytest.raises(ValueError):
        service.review_verification(reviewed, old_candidate)
    verified2, candidate2 = service.verify(reviewed)
    verified_reviewed2, review2 = service.review_verification(verified2, candidate2)
    approved2, approval2 = service.approve(
        verified_reviewed2, candidate2, review2, identity="new"
    )
    with pytest.raises(ValueError):
        service.install(approved2, candidate2, old_review, old_approval)
    installed, _, receipt = service.install(approved2, candidate2, review2, approval2)
    with pytest.raises(BoundedExecutionError) as caught:
        service.execute(
            installed,
            receipt.__class__(**{**asdict(receipt), "proposal_revision": 1}),
            receipt.installed_rule_id,
            {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    assert caught.value.code == ExecutionFailureCode.RULE_BINDING_MISMATCH


def test_backup_read_recovery_then_install_and_reload(tmp_path: Path) -> None:
    service = _service(tmp_path, proposal_ids=iter(("first", "second")).__next__)
    first, _, _, _, first_record, first_receipt = _complete_reviewed(
        service,
        _to_reviewed(service, _row(SemanticFamily.DRAIN, "A", "B")),
    )
    RuleMemory.load(service.memory_path).save(service.memory_path)
    corrupt = b"{corrupt-primary\xff"
    service.memory_path.write_bytes(corrupt)
    assert RuleMemory.load_with_backup(service.memory_path).recovery_source.startswith(
        "backup:"
    )
    _, execution = service.execute(
        first,
        first_receipt,
        first_record.rule_id,
        {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
    )
    assert execution.halted
    second = _to_reviewed(service, _row(SemanticFamily.DRAIN, "C", "D"))
    approved, candidate, review, approval, _, _ = _prepare_install(service, second)
    with pytest.raises(RuleMemoryRecoveryRequiredError):
        service.install(approved, candidate, review, approval)
    evidence = service.recover_rule_memory()
    preserved = Path(evidence["preserved_corrupt_primary"])
    assert preserved.read_bytes() == corrupt
    installed, _, _ = service.install(approved, candidate, review, approval)
    memory = RuleMemory.load(service.memory_path)
    assert len(memory.active_records()) == 2
    assert installed.revision == 1
    assert service.audit.replay()[-2].event_type == "RULE_MEMORY_RECOVERED"


def _prepare_install(service: Stage1Service, proposal):
    proposal, candidate = service.verify(proposal)
    proposal, review = service.review_verification(proposal, candidate)
    proposal, approval = service.approve(
        proposal, candidate, review, identity="m241a-test"
    )
    return proposal, candidate, review, approval, None, None


def test_invalid_backup_never_replaces_primary_and_is_audited(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.memory_path.parent.mkdir(parents=True, exist_ok=True)
    primary = b"broken-primary"
    service.memory_path.write_bytes(primary)
    service.memory_path.with_suffix(".json.bak").write_bytes(b"broken-backup")
    with pytest.raises(RuleMemoryRecoveryError):
        service.recover_rule_memory()
    assert service.memory_path.read_bytes() == primary
    event = service.audit.replay()[-1]
    assert event.event_type == "RULE_MEMORY_RECOVERY_FAILED"
    assert event.payload["failure_code"] == "RULE_MEMORY_RECOVERY_FAILURE"


def _rewrite_checksum(path: Path, mutation) -> None:
    row = json.loads(path.read_text(encoding="utf-8"))
    row.pop("content_sha256")
    mutation(row)
    canonical = json.dumps(
        row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    row["content_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path.write_text(json.dumps(row), encoding="utf-8")


def test_typed_memory_failures_are_audited_but_programmer_bugs_are_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path / "parse")
    proposal, _, _, _, record, receipt = _complete_reviewed(
        service,
        _to_reviewed(service, _row(SemanticFamily.DRAIN, "A", "B")),
    )
    _rewrite_checksum(
        service.memory_path,
        lambda row: row["records"][0].update(program_json="malformed"),
    )
    with pytest.raises(StoredRuleParseError):
        service.execute(
            proposal,
            receipt,
            record.rule_id,
            {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    assert service.audit.replay()[-1].payload["failure_code"] == (
        "STORED_RULE_PARSE_FAILURE"
    )

    io_service = _service(tmp_path / "io")
    io_proposal, _, _, _, io_record, io_receipt = _complete_reviewed(
        io_service,
        _to_reviewed(io_service, _row(SemanticFamily.DRAIN, "A", "B")),
    )
    original_loader = RuleMemory.load_with_backup
    monkeypatch.setattr(
        RuleMemory,
        "load_with_backup",
        classmethod(lambda cls, path: (_ for _ in ()).throw(RuleMemoryIOError("io"))),
    )
    with pytest.raises(RuleMemoryIOError):
        io_service.execute(
            io_proposal,
            io_receipt,
            io_record.rule_id,
            {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    assert io_service.audit.replay()[-1].payload["failure_code"] == (
        "EXECUTION_IO_FAILURE"
    )
    monkeypatch.setattr(RuleMemory, "load_with_backup", original_loader)
    event_count = len(io_service.audit.replay())
    monkeypatch.setattr(
        service_module,
        "execute_rule",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("bug")),
    )
    with pytest.raises(AssertionError, match="bug"):
        io_service.execute(
            io_proposal,
            io_receipt,
            io_record.rule_id,
            {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    assert len(io_service.audit.replay()) == event_count


@pytest.mark.parametrize(
    ("damage_backup", "expected_code", "expected_error"),
    [
        (False, "RULE_MEMORY_INTEGRITY_FAILURE", ValueError),
        (True, "RULE_MEMORY_RECOVERY_FAILURE", RuleMemoryRecoveryError),
    ],
)
def test_checksum_and_double_corruption_execution_failures_are_typed(
    tmp_path: Path,
    damage_backup: bool,
    expected_code: str,
    expected_error: type[Exception],
) -> None:
    service = _service(tmp_path)
    proposal, _, _, _, record, receipt = _complete_reviewed(
        service,
        _to_reviewed(service, _row(SemanticFamily.DRAIN, "A", "B")),
    )
    if damage_backup:
        RuleMemory.load(service.memory_path).save(service.memory_path)
        service.memory_path.with_suffix(".json.bak").write_text(
            "broken", encoding="utf-8"
        )
    row = json.loads(service.memory_path.read_text(encoding="utf-8"))
    row.pop("content_sha256")
    service.memory_path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(expected_error):
        service.execute(
            proposal,
            receipt,
            record.rule_id,
            {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    event = service.audit.replay()[-1]
    assert event.event_type == "EXECUTION_FAILED"
    assert event.payload["failure_code"] == expected_code
