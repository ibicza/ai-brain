"""CLI wiring for the Stage-1 v1 production workflow."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage1.controlled_language import language_help
from ai_brain.stage1.models import ApprovalDecision
from ai_brain.stage1.serde import (
    approval_from_json,
    candidate_from_json,
    proposal_from_json,
    read_json,
    write_artifact,
)
from ai_brain.stage1.service import Stage1Service


def add_stage1_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "stage1", help="Stage-1 v1 trusted production workflow."
    )
    parser.add_argument(
        "--memory", type=Path, default=Path("artifacts/stage1/rule_memory.json")
    )
    parser.add_argument(
        "--audit", type=Path, default=Path("artifacts/stage1/audit.jsonl")
    )
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

    approve = commands.add_parser("approve")
    approve.add_argument("--proposal", type=Path, required=True)
    approve.add_argument("--candidate", type=Path, required=True)
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
    install.add_argument("--approval", type=Path, required=True)
    install.add_argument("--proposal-output", type=Path, required=True)

    commands.add_parser("list")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--rule-id", required=True)

    execute = commands.add_parser("execute")
    execute.add_argument("--proposal", type=Path, required=True)
    execute.add_argument("--rule-id", required=True)
    execute.add_argument(
        "--state", required=True, help='JSON object, e.g. {"R0":2,...}'
    )
    execute.add_argument("--proposal-output", type=Path, required=True)

    commands.add_parser("audit-replay")


def run_stage1(args: argparse.Namespace) -> int:
    service = Stage1Service(memory_path=args.memory, audit_path=args.audit)
    command = args.stage1_command
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
    if command == "approve":
        proposal, approval = service.approve(
            proposal_from_json(read_json(args.proposal)),
            candidate_from_json(read_json(args.candidate)),
            identity=args.identity,
            identity_type=args.identity_type,
            decision=ApprovalDecision(args.decision),
        )
        write_artifact(args.proposal_output, proposal)
        write_artifact(args.approval_output, approval)
        return _print(approval)
    if command == "install":
        proposal, record = service.install(
            proposal_from_json(read_json(args.proposal)),
            candidate_from_json(read_json(args.candidate)),
            approval_from_json(read_json(args.approval)),
        )
        write_artifact(args.proposal_output, proposal)
        return _print(record)
    if command == "list":
        return _print(service.list_rules())
    if command == "inspect":
        return _print(service.inspect_rule(args.rule_id))
    if command == "execute":
        state = json.loads(args.state)
        proposal, result = service.execute(
            proposal_from_json(read_json(args.proposal)), args.rule_id, state
        )
        write_artifact(args.proposal_output, proposal)
        return _print(result)
    if command == "audit-replay":
        return _print(service.audit.replay())
    raise ValueError(f"Unknown stage1 command {command}")


def _print(value) -> int:
    if isinstance(value, list):
        value = [asdict(item) for item in value]
    elif hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
