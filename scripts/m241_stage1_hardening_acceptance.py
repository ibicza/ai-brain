"""Run the reproducible Stage-1 v1.0.1 hardening acceptance battery."""

from __future__ import annotations

import argparse
import itertools
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ai_brain.rules.memory import RuleMemory, migrate_legacy_rule_memory
from ai_brain.stage1.audit import AuditLog, reconstruct_audit
from ai_brain.stage1.controlled_language import LEXICON, parse_controlled_language
from ai_brain.stage1.execution import BoundedExecutionError, validate_initial_state
from ai_brain.stage1.models import ExecutionLimits, ProposalStatus
from ai_brain.stage1.serde import receipt_from_json
from ai_brain.stage1.service import Stage1Service
from ai_brain.stage1.specifications import specification_from_dict
from ai_brain.stage1.version import STAGE1_VERSION

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runs" / "m241_stage1_hardening_acceptance.json"

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


def run() -> dict:
    started = time.perf_counter()
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    require(STAGE1_VERSION == "1.0.1", "release version")
    limits = ExecutionLimits()
    require(not limits.capture_trace, "trace-disabled trusted default")
    require(limits.max_register_value == 1_000_000, "register limit")
    require(limits.max_total_units == 1_000_000, "total-unit limit")
    require(limits.max_execution_steps == 1_000_008, "step limit")
    require(limits.max_trace_actions == 10_000, "trace limit")
    validate_initial_state({"R0": 1_000_000, "R1": 0, "R2": 0, "R3": 0}, limits)
    checks += 1
    try:
        validate_initial_state({"R0": 1_000_001, "R1": 0, "R2": 0, "R3": 0}, limits)
    except BoundedExecutionError:
        checks += 1
    else:
        raise AssertionError("register over-limit accepted")

    malformed_specification = {
        "inputs": "AB",
        "outputs": [],
        "transfers": [],
        "drops": [],
        "preserve": [],
        "terminate_when_empty": [],
        "allowed_variables": [],
        "allowed_primitives": [],
        "phase_constraints": [],
        "unsupported": False,
    }
    try:
        specification_from_dict(malformed_specification)
    except TypeError:
        checks += 1
    else:
        raise AssertionError("malformed ProgramSpecification accepted")

    for move, preserve in itertools.product(LEXICON["en"]["move"], EN_PRESERVE):
        outcome = parse_controlled_language(
            f"{move} every item from A into B; {preserve}; stop when A is empty.",
            "en",
        )
        require(outcome.status == ProposalStatus.CONTRADICTORY, "English contradiction")
    for move, preserve in itertools.product(LEXICON["ru"]["move"], RU_PRESERVE):
        outcome = parse_controlled_language(
            f"{move} все элементы из A в B; {preserve}; остановись, когда A опустеет.",
            "ru",
        )
        require(outcome.status == ProposalStatus.CONTRADICTORY, "Russian contradiction")

    with tempfile.TemporaryDirectory(prefix="ai-brain-m241-") as temporary:
        directory = Path(temporary)
        smoke = _standalone_smoke(directory)
        checks += smoke["checks"]
        memory_path = directory / "memory.json"
        audit_path = directory / "audit.jsonl"
        receipt = receipt_from_json(
            json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
        )
        reconstruction = reconstruct_audit(
            AuditLog(audit_path),
            RuleMemory.load(memory_path),
            receipt.proposal_id,
            receipt=receipt,
            require_execution=True,
        )
        require(reconstruction.valid, f"audit reconstruction: {reconstruction.errors}")

        memory_row = json.loads(memory_path.read_text(encoding="utf-8"))
        memory_row.pop("content_sha256")
        checksumless = directory / "checksumless.json"
        checksumless.write_text(json.dumps(memory_row), encoding="utf-8")
        try:
            RuleMemory.load(checksumless)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("normal load accepted checksum-less memory")
        migrated = directory / "migrated.json"
        migration = migrate_legacy_rule_memory(checksumless, migrated)
        require(migration["records"] == 1, "legacy migration record count")
        require(
            len(migration["active_rules_reverified"]) == 1,
            "legacy migration re-verification",
        )
        require(bool(RuleMemory.load(migrated).records), "migrated memory load")
        workflow_checks = _revision_and_id_smoke(directory / "workflow")
        checks += workflow_checks

    return {
        "outcome": "A",
        "release_version": STAGE1_VERSION,
        "acceptance_checks": checks,
        "synonym_contradiction_cases": 40,
        "standalone_cli_steps": smoke["checks"],
        "standalone_cli": "passed",
        "no_torch": True,
        "rule_memory_migration": "passed",
        "rule_memory_recovery": "passed",
        "audit_revision_reconstruction": "passed",
        "proposal_id_collision_isolation": "passed",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "source_sha": _git("rev-parse", "HEAD"),
    }


def _standalone_smoke(directory: Path) -> dict[str, int]:
    memory = directory / "memory.json"
    audit = directory / "audit.jsonl"
    proposal0 = directory / "proposal0.json"
    proposal1 = directory / "proposal1.json"
    proposal2 = directory / "proposal2.json"
    proposal3 = directory / "proposal3.json"
    proposal4 = directory / "proposal4.json"
    proposal5 = directory / "proposal5.json"
    proposal6 = directory / "proposal6.json"
    candidate = directory / "candidate.json"
    review = directory / "verified-review.json"
    approval = directory / "approval.json"
    receipt = directory / "receipt.json"
    result = directory / "result.json"
    common = ["--memory", str(memory), "--audit", str(audit)]
    commands = [
        ["--help"],
        [*common, "language-help", "--lang", "ru"],
        [
            *common,
            "propose-language",
            "--lang",
            "ru",
            "--text",
            f"{'Перенеси все элементы из A в B; C и D не изменяй; '}остановись, когда A опустеет.",
            "--output",
            str(proposal0),
        ],
        [*common, "review", "--proposal", str(proposal0), "--output", str(proposal1)],
        [
            *common,
            "verify",
            "--proposal",
            str(proposal1),
            "--proposal-output",
            str(proposal2),
            "--candidate-output",
            str(candidate),
        ],
        [
            *common,
            "review-verification",
            "--proposal",
            str(proposal2),
            "--candidate",
            str(candidate),
            "--proposal-output",
            str(proposal3),
            "--review-output",
            str(review),
        ],
        [
            *common,
            "approve",
            "--proposal",
            str(proposal3),
            "--candidate",
            str(candidate),
            "--review",
            str(review),
            "--identity",
            "m241-acceptance",
            "--proposal-output",
            str(proposal4),
            "--approval-output",
            str(approval),
        ],
        [
            *common,
            "install",
            "--proposal",
            str(proposal4),
            "--candidate",
            str(candidate),
            "--review",
            str(review),
            "--approval",
            str(approval),
            "--proposal-output",
            str(proposal5),
            "--receipt-output",
            str(receipt),
        ],
    ]
    for command in commands:
        _cli(command)
    receipt_row = json.loads(receipt.read_text(encoding="utf-8"))
    rule_id = receipt_row["installed_rule_id"]
    _cli(
        [
            *common,
            "execute",
            "--proposal",
            str(proposal5),
            "--receipt",
            str(receipt),
            "--rule-id",
            rule_id,
            "--state",
            '{"R0":2,"R1":3,"R2":4,"R3":5}',
            "--proposal-output",
            str(proposal6),
            "--result-output",
            str(result),
        ]
    )
    _cli([*common, "audit-replay"])
    _cli(
        [
            *common,
            "audit-reconstruct",
            "--proposal-id",
            receipt_row["proposal_id"],
            "--receipt",
            str(receipt),
            "--require-execution",
        ]
    )
    RuleMemory.load(memory).save(memory)
    corrupt_primary = b"{m241-corrupt-primary\xff"
    memory.write_bytes(corrupt_primary)
    recovery_evidence = directory / "recovery-evidence.json"
    _cli(
        [
            *common,
            "recover-rule-memory",
            "--evidence-output",
            str(recovery_evidence),
        ]
    )
    evidence = json.loads(recovery_evidence.read_text(encoding="utf-8"))
    preserved = Path(evidence["preserved_corrupt_primary"])
    if preserved.read_bytes() != corrupt_primary:
        raise AssertionError("recovery did not preserve exact corrupt primary bytes")
    if not RuleMemory.load(memory).records:
        raise AssertionError("recovered RuleMemory has no records")
    if AuditLog(audit).replay()[-1].event_type != "RULE_MEMORY_RECOVERED":
        raise AssertionError("recovery audit event missing")
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import ai_brain.stage1.cli; assert 'torch' not in sys.modules",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if probe.returncode != 0:
        raise AssertionError(f"standalone no-torch probe failed: {probe.stderr}")
    final_result = json.loads(result.read_text(encoding="utf-8"))
    if final_result["final_state"] != {"R0": 0, "R1": 5, "R2": 4, "R3": 5}:
        raise AssertionError("standalone execution result mismatch")
    if final_result["captured_actions"] != []:
        raise AssertionError("standalone trace default is not disabled")
    return {"checks": len(commands) + 12}


def _revision_and_id_smoke(directory: Path) -> int:
    service = Stage1Service(
        memory_path=directory / "memory.json",
        audit_path=directory / "audit.jsonl",
    )
    text = (
        "Move every item from A into B; leave C and D unchanged; stop when A is empty."
    )
    first = service.propose_language(text, language="en")
    second = service.propose_language(text, language="en")
    if first.proposal_id == second.proposal_id:
        raise AssertionError("identical submissions collided")
    received = [
        item
        for item in service.audit.replay()
        if item.event_type == "PROPOSAL_RECEIVED"
    ]
    if (
        received[0].payload["original_input_hash"]
        != received[1].payload["original_input_hash"]
    ):
        raise AssertionError("identical inputs have different deterministic hashes")

    first, _ = service.review(first)
    first, _ = service.verify(first)
    edited_specification = {
        "inputs": ["A"],
        "outputs": ["C"],
        "transfers": [["A", "C"]],
        "drops": [],
        "preserve": ["B", "D"],
        "terminate_when_empty": ["A"],
        "allowed_variables": ["A", "B", "C", "D"],
        "allowed_primitives": ["HALT", "MOVE_ONE"],
        "phase_constraints": [["MOVE_ONE", "A", "C"]],
        "unsupported": False,
    }
    first = service.edit(first, edited_specification)
    first, _ = service.review(first)
    first, candidate = service.verify(first)
    first, review = service.review_verification(first, candidate)
    first, approval = service.approve(
        first, candidate, review, identity="m241-acceptance"
    )
    first, _, receipt = service.install(first, candidate, review, approval)
    reconstruction = reconstruct_audit(
        service.audit,
        RuleMemory.load(service.memory_path),
        first.proposal_id,
        receipt=receipt,
    )
    if not reconstruction.valid:
        raise AssertionError(f"revision reconstruction: {reconstruction.errors}")
    if [item.status for item in reconstruction.revisions] != [
        "SUPERSEDED",
        "ACTIVE",
    ]:
        raise AssertionError("revision statuses are not preserved")
    return 7


def _cli(arguments: list[str]) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ai_brain.stage1.cli", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"standalone CLI failed: {arguments}\n{completed.stdout}\n{completed.stderr}"
        )


def _git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    result = run()
    if arguments.write:
        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
