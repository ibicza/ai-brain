"""Standalone CPU-only CLI for the trusted Stage-1 v1 workflow."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.rules.memory import RuleMemory, migrate_legacy_rule_memory
from ai_brain.stage1.audit import reconstruct_audit
from ai_brain.stage1.controlled_language import language_help
from ai_brain.stage1.models import ApprovalDecision, ExecutionLimits
from ai_brain.stage1.serde import (
    approval_from_json,
    candidate_from_json,
    proposal_from_json,
    read_json,
    receipt_from_json,
    review_from_json,
    write_artifact,
)
from ai_brain.stage1.service import Stage1Service

DEFAULT_MEMORY = Path("artifacts/stage1/rule_memory.json")
DEFAULT_AUDIT = Path("artifacts/stage1/audit.jsonl")


def add_stage1_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "stage1", help="Stage-1 v1 trusted production workflow."
    )
    _add_runtime_arguments(parser)
    _add_commands(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-brain-stage1",
        description="Trusted deterministic Stage-1 v1 production workflow.",
    )
    _add_runtime_arguments(parser)
    _add_commands(parser)
    return parser


def _add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--memory", type=Path, default=DEFAULT_MEMORY)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)


def _add_commands(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="stage1_command", required=True)

    help_parser = commands.add_parser("language-help")
    help_parser.add_argument("--lang", choices=("ru", "en"), default="en")

    language = commands.add_parser("propose-language")
    language.add_argument("--text", required=True)
    language.add_argument("--lang", choices=("ru", "en"))
    language.add_argument("--output", type=Path, required=True)

    form = commands.add_parser("propose-form")
    form.add_argument("--input", type=Path, required=True)
    form.add_argument("--output", type=Path, required=True)

    dsl = commands.add_parser("propose-dsl")
    dsl.add_argument("--dsl", type=Path, required=True)
    dsl.add_argument("--spec", type=Path, required=True)
    dsl.add_argument("--output", type=Path, required=True)

    clarify = commands.add_parser("clarify")
    clarify.add_argument("--proposal", type=Path, required=True)
    clarify.add_argument("--answer", required=True)
    clarify.add_argument("--output", type=Path, required=True)

    review = commands.add_parser("review")
    review.add_argument("--proposal", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--proposal", type=Path, required=True)
    verify.add_argument("--proposal-output", type=Path, required=True)
    verify.add_argument("--candidate-output", type=Path, required=True)

    verified_review = commands.add_parser("review-verification")
    verified_review.add_argument("--proposal", type=Path, required=True)
    verified_review.add_argument("--candidate", type=Path, required=True)
    verified_review.add_argument("--review-output", type=Path, required=True)
    verified_review.add_argument("--proposal-output", type=Path)

    approve = commands.add_parser("approve")
    approve.add_argument("--proposal", type=Path, required=True)
    approve.add_argument("--candidate", type=Path, required=True)
    approve.add_argument("--review", type=Path, required=True)
    approve.add_argument("--identity", required=True)
    approve.add_argument(
        "--identity-type", choices=("USER", "TRUSTED_SUPERVISOR"), default="USER"
    )
    approve.add_argument("--decision", choices=("APPROVE", "REJECT"), default="APPROVE")
    approve.add_argument("--proposal-output", type=Path, required=True)
    approve.add_argument("--approval-output", type=Path, required=True)

    install = commands.add_parser("install")
    install.add_argument("--proposal", type=Path, required=True)
    install.add_argument("--candidate", type=Path, required=True)
    install.add_argument("--review", type=Path, required=True)
    install.add_argument("--approval", type=Path, required=True)
    install.add_argument("--proposal-output", type=Path, required=True)
    install.add_argument("--receipt-output", type=Path, required=True)

    commands.add_parser("list")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--rule-id", required=True)

    execute = commands.add_parser("execute")
    execute.add_argument("--proposal", type=Path, required=True)
    execute.add_argument("--receipt", type=Path, required=True)
    execute.add_argument("--rule-id", required=True)
    execute.add_argument("--state", required=True, help='JSON, e.g. {"R0":2,...}')
    execute.add_argument("--proposal-output", type=Path, required=True)
    execute.add_argument("--result-output", type=Path)
    execute.add_argument("--trace", action="store_true")
    execute.add_argument("--fail-on-trace-overflow", action="store_true")
    execute.add_argument("--max-register-value", type=int, default=1_000_000)
    execute.add_argument("--max-total-units", type=int, default=1_000_000)
    execute.add_argument("--max-execution-steps", type=int, default=1_000_008)
    execute.add_argument("--max-trace-actions", type=int, default=10_000)

    commands.add_parser("audit-replay")
    reconstruction = commands.add_parser("audit-reconstruct")
    reconstruction.add_argument("--proposal-id", required=True)
    reconstruction.add_argument("--receipt", type=Path)
    reconstruction.add_argument("--require-execution", action="store_true")

    migration = commands.add_parser("migrate-rule-memory")
    migration.add_argument("--source", type=Path, required=True)
    migration.add_argument("--destination", type=Path, required=True)
    migration.add_argument("--evidence-output", type=Path)

    recovery = commands.add_parser("recover-rule-memory")
    recovery.add_argument("--evidence-output", type=Path)


def run_stage1(args: argparse.Namespace) -> int:
    command = args.stage1_command
    if command == "migrate-rule-memory":
        evidence = migrate_legacy_rule_memory(args.source, args.destination)
        if args.evidence_output:
            _write_json(args.evidence_output, evidence)
        return _print(evidence)
    service = Stage1Service(memory_path=args.memory, audit_path=args.audit)
    if command == "recover-rule-memory":
        evidence = service.recover_rule_memory()
        if args.evidence_output:
            _write_json(args.evidence_output, evidence)
        return _print(evidence)
    if command == "language-help":
        print(language_help(args.lang))
        return 0
    if command == "propose-language":
        proposal = service.propose_language(args.text, language=args.lang)
        write_artifact(args.output, proposal)
        return _print(proposal)
    if command == "propose-form":
        proposal = service.propose_form(read_json(args.input))
        write_artifact(args.output, proposal)
        return _print(proposal)
    if command == "propose-dsl":
        proposal = service.propose_dsl(
            args.dsl.read_text(encoding="utf-8"), read_json(args.spec)
        )
        write_artifact(args.output, proposal)
        return _print(proposal)
    if command == "clarify":
        proposal = service.clarify(
            proposal_from_json(read_json(args.proposal)), args.answer
        )
        write_artifact(args.output, proposal)
        return _print(proposal)
    if command == "review":
        proposal, view = service.review(proposal_from_json(read_json(args.proposal)))
        write_artifact(args.output, proposal)
        return _print(view)
    if command == "verify":
        proposal, candidate = service.verify(
            proposal_from_json(read_json(args.proposal))
        )
        write_artifact(args.proposal_output, proposal)
        write_artifact(args.candidate_output, candidate)
        return _print(candidate)
    if command == "review-verification":
        proposal, review = service.review_verification(
            proposal_from_json(read_json(args.proposal)),
            candidate_from_json(read_json(args.candidate)),
        )
        write_artifact(args.proposal_output or args.proposal, proposal)
        write_artifact(args.review_output, review)
        return _print(review)
    if command == "approve":
        proposal, approval = service.approve(
            proposal_from_json(read_json(args.proposal)),
            candidate_from_json(read_json(args.candidate)),
            review_from_json(read_json(args.review)),
            identity=args.identity,
            identity_type=args.identity_type,
            decision=ApprovalDecision(args.decision),
        )
        write_artifact(args.proposal_output, proposal)
        write_artifact(args.approval_output, approval)
        return _print(approval)
    if command == "install":
        proposal, record, receipt = service.install(
            proposal_from_json(read_json(args.proposal)),
            candidate_from_json(read_json(args.candidate)),
            review_from_json(read_json(args.review)),
            approval_from_json(read_json(args.approval)),
        )
        write_artifact(args.proposal_output, proposal)
        write_artifact(args.receipt_output, receipt)
        return _print(record)
    if command == "list":
        return _print(service.list_rules())
    if command == "inspect":
        return _print(service.inspect_rule(args.rule_id))
    if command == "execute":
        try:
            state = json.loads(args.state)
        except json.JSONDecodeError as exc:
            raise ValueError("--state must be valid JSON") from exc
        limits = ExecutionLimits(
            max_register_value=args.max_register_value,
            max_total_units=args.max_total_units,
            max_execution_steps=args.max_execution_steps,
            max_trace_actions=args.max_trace_actions,
            capture_trace=args.trace,
            fail_on_trace_overflow=args.fail_on_trace_overflow,
        )
        proposal, result = service.execute(
            proposal_from_json(read_json(args.proposal)),
            receipt_from_json(read_json(args.receipt)),
            args.rule_id,
            state,
            limits=limits,
        )
        write_artifact(args.proposal_output, proposal)
        if args.result_output:
            write_artifact(args.result_output, result)
        return _print(result)
    if command == "audit-replay":
        return _print(service.audit.replay())
    if command == "audit-reconstruct":
        memory = RuleMemory.load_with_backup(args.memory)
        receipt = receipt_from_json(read_json(args.receipt)) if args.receipt else None
        result = reconstruct_audit(
            service.audit,
            memory,
            args.proposal_id,
            receipt=receipt,
            require_execution=args.require_execution,
        )
        if not result.valid:
            _print(result)
            return 1
        return _print(result)
    raise ValueError(f"Unknown stage1 command {command}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    return run_stage1(build_parser().parse_args(argv))


def _print(value: Any) -> int:
    if isinstance(value, list):
        value = [asdict(item) for item in value]
    elif hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
