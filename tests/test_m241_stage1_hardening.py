from __future__ import annotations

import hashlib
import itertools
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

import ai_brain.rules.memory as memory_module
from ai_brain.rules.memory import RuleMemory, migrate_legacy_rule_memory
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.stage1.audit import reconstruct_audit
from ai_brain.stage1.controlled_language import LEXICON, parse_controlled_language
from ai_brain.stage1.execution import (
    BoundedExecutionError,
    execute_rule,
    validate_initial_state,
)
from ai_brain.stage1.known_family_compiler import compile_known_family
from ai_brain.stage1.models import (
    ExecutionFailureCode,
    ExecutionLimits,
    ProposalStatus,
    SemanticFamily,
)
from ai_brain.stage1.serde import (
    approval_from_json,
    candidate_from_json,
    execution_result_from_json,
    proposal_from_json,
    receipt_from_json,
    review_from_json,
)
from ai_brain.stage1.service import Stage1Service
from ai_brain.stage1.specifications import (
    build_family_specification,
    specification_from_dict,
)


def _json_row(value):
    return json.loads(json.dumps(asdict(value)))


def _complete(tmp_path: Path, *, source: str = "A", destination: str = "B"):
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    proposal = service.propose_language(
        f"Move every item from {source} into {destination}; "
        f"leave C and D unchanged; stop when {source} is empty.",
        language="en",
    )
    proposal, _ = service.review(proposal)
    proposal, candidate = service.verify(proposal)
    proposal, review = service.review_verification(proposal, candidate)
    proposal, approval = service.approve(
        proposal, candidate, review, identity="m241-test"
    )
    proposal, record, receipt = service.install(proposal, candidate, review, approval)
    return service, proposal, candidate, review, approval, record, receipt


@pytest.mark.parametrize(
    "bad_state",
    [
        {"R0": True, "R1": 0, "R2": 0, "R3": 0},
        {"R0": 1.0, "R1": 0, "R2": 0, "R3": 0},
        {"R0": "1", "R1": 0, "R2": 0, "R3": 0},
        {"R0": -1, "R1": 0, "R2": 0, "R3": 0},
        {"R0": 0, "R1": 0, "R2": 0},
        {"R0": 0, "R1": 0, "R2": 0, "R3": 0, "R4": 0},
    ],
)
def test_strict_state_types_and_registers(bad_state: dict) -> None:
    with pytest.raises(BoundedExecutionError) as caught:
        validate_initial_state(bad_state, ExecutionLimits())
    assert caught.value.code == ExecutionFailureCode.INVALID_STATE


def test_state_value_and_total_boundaries_without_execution() -> None:
    limits = ExecutionLimits(max_register_value=1_000_000, max_total_units=1_000_000)
    assert validate_initial_state({"R0": 1_000_000, "R1": 0, "R2": 0, "R3": 0}, limits)
    with pytest.raises(BoundedExecutionError) as value_error:
        validate_initial_state({"R0": 1_000_001, "R1": 0, "R2": 0, "R3": 0}, limits)
    assert value_error.value.code == ExecutionFailureCode.REGISTER_LIMIT_EXCEEDED
    with pytest.raises(BoundedExecutionError) as total_error:
        validate_initial_state({"R0": 500_001, "R1": 500_000, "R2": 0, "R3": 0}, limits)
    assert total_error.value.code == ExecutionFailureCode.TOTAL_LIMIT_EXCEEDED
    with pytest.raises(BoundedExecutionError) as huge_error:
        validate_initial_state({"R0": 10**1000, "R1": 0, "R2": 0, "R3": 0}, limits)
    assert huge_error.value.code == ExecutionFailureCode.REGISTER_LIMIT_EXCEEDED


def test_step_boundary_trace_policy_and_default(tmp_path: Path) -> None:
    service, proposal, _, _, _, record, receipt = _complete(tmp_path)
    state = {"R0": 2, "R1": 0, "R2": 0, "R3": 0}
    _, default_result = service.execute(proposal, receipt, record.rule_id, state)
    assert default_result.executed_steps == 3
    assert default_result.halted
    assert not default_result.trace_requested
    assert default_result.captured_actions == ()

    traced = execute_rule(
        service.memory_path,
        record.rule_id,
        state,
        limits=ExecutionLimits(
            max_execution_steps=3, capture_trace=True, max_trace_actions=3
        ),
    )
    assert traced.captured_actions == ("M R0 R1", "M R0 R1", "H")
    assert not traced.trace_truncated
    truncated = execute_rule(
        service.memory_path,
        record.rule_id,
        state,
        limits=ExecutionLimits(capture_trace=True, max_trace_actions=2),
    )
    assert truncated.halted and truncated.trace_truncated
    assert len(truncated.captured_actions) == 2
    with pytest.raises(BoundedExecutionError) as trace_error:
        execute_rule(
            service.memory_path,
            record.rule_id,
            state,
            limits=ExecutionLimits(
                capture_trace=True,
                max_trace_actions=2,
                fail_on_trace_overflow=True,
            ),
        )
    assert trace_error.value.code == ExecutionFailureCode.TRACE_LIMIT_EXCEEDED
    assert trace_error.value.executed_steps == 2
    with pytest.raises(BoundedExecutionError) as step_error:
        execute_rule(
            service.memory_path,
            record.rule_id,
            state,
            limits=ExecutionLimits(max_execution_steps=2),
        )
    assert step_error.value.code == ExecutionFailureCode.STEP_LIMIT_EXCEEDED
    assert step_error.value.executed_steps == 2


def test_hard_limit_ceiling_is_enforced() -> None:
    with pytest.raises(BoundedExecutionError) as caught:
        validate_initial_state(
            {"R0": 0, "R1": 0, "R2": 0, "R3": 0},
            ExecutionLimits(max_trace_actions=100_001),
        )
    assert caught.value.code == ExecutionFailureCode.INVALID_LIMITS


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("inputs", "AB"),
        ("outputs", ("A",)),
        ("transfers", [["A"]]),
        ("drops", [1]),
        ("phase_constraints", [["MOVE_ONE", "A"]]),
        ("unsupported", 0),
    ],
)
def test_program_specification_json_is_strict(field: str, bad_value) -> None:
    row = _json_row(
        build_family_specification(
            SemanticFamily.DRAIN, sources=("A",), destination="B"
        )
    )
    row[field] = bad_value
    with pytest.raises((TypeError, ValueError)):
        specification_from_dict(row)


def test_program_specification_rejects_extra_missing_and_duplicates() -> None:
    row = _json_row(build_family_specification(SemanticFamily.CLEAR, sources=("A",)))
    with pytest.raises(ValueError, match="extra"):
        specification_from_dict({**row, "extra": []})
    missing = dict(row)
    missing.pop("inputs")
    with pytest.raises(ValueError, match="missing"):
        specification_from_dict(missing)
    duplicate = dict(row)
    duplicate["drops"] = ["A", "A"]
    with pytest.raises(ValueError, match="duplicate"):
        specification_from_dict(duplicate)


def test_strict_artifact_roundtrip_and_schema_rejection(tmp_path: Path) -> None:
    service, proposal, candidate, review, approval, record, receipt = _complete(
        tmp_path
    )
    executed, result = service.execute(
        proposal,
        receipt,
        record.rule_id,
        {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
    )
    artifacts = (
        (proposal_from_json, _json_row(executed)),
        (candidate_from_json, _json_row(candidate)),
        (review_from_json, _json_row(review)),
        (approval_from_json, _json_row(approval)),
        (receipt_from_json, _json_row(receipt)),
        (execution_result_from_json, _json_row(result)),
    )
    for parser, row in artifacts:
        assert parser(row)
        with pytest.raises(ValueError, match="extra"):
            parser({**row, "unexpected": True})
        missing = dict(row)
        missing.pop(next(iter(row)))
        with pytest.raises(ValueError, match="missing"):
            parser(missing)


def test_artifact_hash_timestamp_revision_and_type_rejection(tmp_path: Path) -> None:
    _, proposal, candidate, review, approval, _, receipt = _complete(tmp_path)
    candidate_row = _json_row(candidate)
    candidate_row["candidate_hash"] = "not-a-hash"
    with pytest.raises(ValueError, match="SHA-256"):
        candidate_from_json(candidate_row)
    proposal_row = _json_row(proposal)
    proposal_row["revision"] = True
    with pytest.raises(TypeError, match="positive integer"):
        proposal_from_json(proposal_row)
    approval_row = _json_row(approval)
    approval_row["timestamp"] = "2026-01-01T00:00:00"
    with pytest.raises(ValueError, match="timezone"):
        approval_from_json(approval_row)
    receipt_row = _json_row(receipt)
    receipt_row["rule_memory_schema_version"] = "1"
    with pytest.raises(TypeError, match="positive integer"):
        receipt_from_json(receipt_row)
    review_row = _json_row(review)
    review_row["ordered_phases"] = [("MOVE_ONE", "A", "B")]
    with pytest.raises(TypeError, match="three-item array"):
        review_from_json(review_row)


def test_verified_review_security_bindings(tmp_path: Path) -> None:
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    proposal = service.propose_language(
        "Clear every item from A; leave B, C and D unchanged; stop when A is empty.",
        language="en",
    )
    proposal, _ = service.review(proposal)
    proposal, candidate = service.verify(proposal)
    with pytest.raises(ValueError, match="review is required"):
        service.approve(proposal, candidate, None, identity="operator")
    proposal, review = service.review_verification(proposal, candidate)
    with pytest.raises(ValueError, match="identity is required"):
        service.approve(proposal, candidate, review, identity="   ")
    with pytest.raises(ValueError, match="identity_type"):
        service.approve(
            proposal,
            candidate,
            review,
            identity="operator",
            identity_type="SERVICE",
        )
    with pytest.raises(ValueError, match="review_hash mismatch"):
        service.approve(
            proposal,
            candidate,
            replace(review, warnings=(*review.warnings, "altered")),
            identity="operator",
        )
    other = service.propose_language(
        "Clear every item from B; leave A, C and D unchanged; stop when B is empty.",
        language="en",
    )
    other, _ = service.review(other)
    other, other_candidate = service.verify(other)
    _, other_review = service.review_verification(other, other_candidate)
    with pytest.raises(ValueError, match="verified review: proposal_id mismatch"):
        service.approve(proposal, candidate, other_review, identity="operator")
    with pytest.raises(ValueError, match="stage1_version mismatch"):
        service.approve(
            proposal,
            candidate,
            replace(review, stage1_version="1.0.0"),
            identity="operator",
        )


def test_receipt_rejects_unrelated_rule_and_audits_failure(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    service, proposal, _, _, _, record, receipt = _complete(first_dir)
    specification = build_family_specification(
        SemanticFamily.DRAIN, sources=("C",), destination="D"
    )
    memory = RuleMemory.load(service.memory_path)
    second = memory.add(
        compile_known_family(specification),
        specification,
        VerificationStatus.PROPERTY_VERIFIED,
        verification_evidence={"accepted": True, "status": "PROPERTY_VERIFIED"},
    )
    memory.save(service.memory_path)
    with pytest.raises(BoundedExecutionError) as caught:
        service.execute(
            proposal,
            receipt,
            second.rule_id,
            {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    assert caught.value.code == ExecutionFailureCode.RULE_BINDING_MISMATCH
    failed = service.audit.replay()[-1]
    assert failed.event_type == "EXECUTION_FAILED"
    assert failed.payload["failure_code"] == "RULE_BINDING_MISMATCH"
    assert "initial_state" not in failed.payload
    assert record.rule_id != second.rule_id


@pytest.mark.parametrize(
    "field",
    (
        "candidate_hash",
        "evidence_hash",
        "verified_review_hash",
        "approval_hash",
    ),
)
def test_receipt_rejects_tampered_workflow_hash(tmp_path: Path, field: str) -> None:
    service, proposal, _, _, _, record, receipt = _complete(tmp_path)
    tampered = replace(receipt, **{field: "0" * 64})
    with pytest.raises(BoundedExecutionError) as caught:
        service.execute(
            proposal,
            tampered,
            record.rule_id,
            {"R0": 1, "R1": 0, "R2": 0, "R3": 0},
        )
    assert caught.value.code == ExecutionFailureCode.RULE_BINDING_MISMATCH


def test_audit_reconstruction_validates_complete_chain(tmp_path: Path) -> None:
    service, proposal, _, _, _, record, receipt = _complete(tmp_path)
    proposal, _ = service.execute(
        proposal,
        receipt,
        record.rule_id,
        {"R0": 2, "R1": 0, "R2": 0, "R3": 0},
    )
    reconstruction = reconstruct_audit(
        service.audit,
        RuleMemory.load(service.memory_path),
        proposal.proposal_id,
        receipt=receipt,
        require_execution=True,
    )
    assert reconstruction.valid, reconstruction.errors
    assert reconstruction.installed_rule_id == record.rule_id
    assert len(reconstruction.execution_hashes) == 1
    service.audit.append(
        "CANDIDATE_VERIFIED", {"candidate_hash": "0" * 64}, proposal.proposal_id
    )
    broken = reconstruct_audit(
        service.audit, RuleMemory.load(service.memory_path), proposal.proposal_id
    )
    assert not broken.valid


def _rewrite_checksum(path: Path, mutate) -> None:
    row = json.loads(path.read_text(encoding="utf-8"))
    row.pop("content_sha256")
    mutate(row)
    canonical = json.dumps(
        row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    row["content_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path.write_text(json.dumps(row), encoding="utf-8")


def test_rule_memory_checksum_recovery_and_corruption_cases(tmp_path: Path) -> None:
    service, *_ = _complete(tmp_path)
    row = json.loads(service.memory_path.read_text(encoding="utf-8"))
    row.pop("content_sha256")
    service.memory_path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        RuleMemory.load(service.memory_path)
    row["content_sha256"] = "z" * 64
    service.memory_path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        RuleMemory.load(service.memory_path)

    # Create a validated backup, then prove recovery source is explicit.
    service2, *_ = _complete(tmp_path / "recovery")
    memory = RuleMemory.load(service2.memory_path)
    memory.save(service2.memory_path)
    service2.memory_path.write_text('{"truncated":', encoding="utf-8")
    recovered = RuleMemory.load_with_backup(service2.memory_path)
    assert recovered.recovery_source.startswith("backup:")
    service2.memory_path.with_suffix(".json.bak").write_text("bad", encoding="utf-8")
    with pytest.raises(ValueError, match="both primary and backup"):
        RuleMemory.load_with_backup(service2.memory_path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.update(extra=True),
        lambda row: row.pop("records"),
        lambda row: row.update(schema_version=99),
        lambda row: row["records"][0].update(version=True),
        lambda row: row["records"][0].pop("specification"),
        lambda row: row["records"][0]["specification"].update(inputs="A"),
        lambda row: row["records"][0].update(program_json="not dsl"),
    ],
)
def test_rule_memory_strict_schema_cases(tmp_path: Path, mutation) -> None:
    service, *_ = _complete(tmp_path)
    _rewrite_checksum(service.memory_path, mutation)
    with pytest.raises((TypeError, ValueError)):
        RuleMemory.load(service.memory_path)


def test_rule_memory_duplicate_id_and_active_hash(tmp_path: Path) -> None:
    service, *_ = _complete(tmp_path)

    def duplicate_id(row):
        row["records"].append(dict(row["records"][0]))

    _rewrite_checksum(service.memory_path, duplicate_id)
    with pytest.raises(ValueError, match="duplicate id"):
        RuleMemory.load(service.memory_path)

    service2, *_ = _complete(tmp_path / "hash")

    def duplicate_hash(row):
        copy = dict(row["records"][0])
        copy["rule_id"] = "rule-99999-duplicate"
        row["records"].append(copy)

    _rewrite_checksum(service2.memory_path, duplicate_hash)
    with pytest.raises(ValueError, match="duplicate active semantic"):
        RuleMemory.load(service2.memory_path)


def test_rule_memory_stale_temp_and_directory_fsync_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, *_ = _complete(tmp_path)
    stale = tmp_path / ".memory.json.stale.tmp"
    stale.write_text("unrelated", encoding="utf-8")
    RuleMemory.load(service.memory_path).save(service.memory_path)
    assert stale.read_text(encoding="utf-8") == "unrelated"
    monkeypatch.setattr(
        os, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError())
    )
    memory_module._fsync_directory(tmp_path)


def test_explicit_legacy_migration_success_and_failure(tmp_path: Path) -> None:
    service, *_ = _complete(tmp_path / "source")
    legacy = tmp_path / "legacy.json"
    row = json.loads(service.memory_path.read_text(encoding="utf-8"))
    row.pop("content_sha256")
    legacy.write_text(json.dumps(row), encoding="utf-8")
    destination = tmp_path / "migrated.json"
    evidence = migrate_legacy_rule_memory(legacy, destination)
    assert evidence["records"] == 1
    assert len(evidence["active_rules_reverified"]) == 1
    assert RuleMemory.load(destination).recovery_source == "primary"
    assert destination.with_suffix(".json.legacy.bak").exists()

    invalid = tmp_path / "invalid-legacy.json"
    row["records"][0]["program_json"] = "malformed"
    invalid.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError):
        migrate_legacy_rule_memory(invalid, tmp_path / "must-not-exist.json")


EN_PRESERVE = (
    "leave A unchanged",
    "preserve A",
    "do not modify A",
    "retain A untouched",
    "maintain A intact",
)
RU_PRESERVE = (
    "A не изменяй",
    "сохрани A без изменений",
    "A не меняй",
    "сбереги A как есть",
    "поддерживай A без изменений",
)


@pytest.mark.parametrize(
    ("language", "move", "preserve"),
    [
        *(
            ("en", move, preserve)
            for move, preserve in itertools.product(LEXICON["en"]["move"], EN_PRESERVE)
        ),
        *(
            ("ru", move, preserve)
            for move, preserve in itertools.product(LEXICON["ru"]["move"], RU_PRESERVE)
        ),
    ],
)
def test_full_synonym_contradiction_matrix(
    language: str, move: str, preserve: str
) -> None:
    if language == "en":
        text = f"{move} every item from A into B; {preserve}; stop when A is empty."
    else:
        text = (
            f"{move} все элементы из A в B; {preserve}; остановись, когда A опустеет."
        )
    assert (
        parse_controlled_language(text, language).status == ProposalStatus.CONTRADICTORY
    )


@pytest.mark.parametrize(
    "text",
    [
        "Move A into A; leave B, C and D unchanged; stop when A is empty.",
        "Clear A and move A into B; leave C and D unchanged; stop when A is empty.",
        "Move A into B; leave C and D unchanged; stop when C is empty.",
        "Move A into B; leave C and D unchanged; stop when A is empty; destination=E",
        "Move A and A into B; leave C and D unchanged; stop when A is empty.",
    ],
)
def test_controlled_language_negative_contradictions(text: str) -> None:
    assert parse_controlled_language(text, "en").status == ProposalStatus.CONTRADICTORY


def test_standalone_cli_help_language_and_no_torch() -> None:
    root = Path(__file__).resolve().parents[1]
    help_result = subprocess.run(
        [sys.executable, "-m", "ai_brain.stage1.cli", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert help_result.returncode == 0
    assert "review-verification" in help_result.stdout
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            f"{'import sys; from ai_brain.stage1.cli import main; '}assert main(['language-help','--lang','ru']) == 0; assert 'torch' not in sys.modules",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    assert "Укажите" in probe.stdout
