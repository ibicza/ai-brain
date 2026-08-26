"""CPU-only command line interface for trusted factual memory."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import (
    ApprovalDecision,
    ProposalStatus,
)
from ai_brain.stage2.facts.persistence import FactDatabase
from ai_brain.stage2.facts.rendering import render_answer
from ai_brain.stage2.facts.values import FactValue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-brain-facts",
        description="Provenance-aware bitemporal factual memory.",
    )
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")

    for name in ("add-entity", "add-predicate", "propose-claim", "query"):
        command = commands.add_parser(name)
        command.add_argument("--json", type=Path, required=True)

    source = commands.add_parser("add-source")
    source.add_argument("--file", type=Path, required=True)
    source.add_argument("--metadata", type=Path, required=True)

    evidence = commands.add_parser("attach-evidence")
    evidence.add_argument("--json", type=Path, required=True)
    evidence.add_argument("--proposal-id")

    review = commands.add_parser("review-claim")
    review.add_argument("--proposal-id", required=True)
    review.add_argument("--reviewer", required=True)

    approve = commands.add_parser("approve-claim")
    approve.add_argument("--proposal-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reviewer-type", default="HUMAN")
    approve.add_argument(
        "--decision",
        choices=("APPROVE", "MARK_CONTESTED"),
        default="APPROVE",
    )
    approve.add_argument("--contested", action="store_true")

    commit = commands.add_parser("commit-claim")
    commit.add_argument("--proposal-id", required=True)
    commit.add_argument("--approval-id", required=True)

    for name in ("show-claim", "history"):
        command = commands.add_parser(name)
        command.add_argument("--claim-id", required=True)

    conflicts = commands.add_parser("conflicts")
    conflicts.add_argument("--include-resolved", action="store_true")

    supersede = commands.add_parser("supersede")
    supersede.add_argument("--old-claim-id", required=True)
    supersede.add_argument("--new-claim-id", required=True)
    supersede.add_argument("--actor", required=True)
    supersede.add_argument("--reason", required=True)

    retract_claim = commands.add_parser("retract-claim")
    retract_claim.add_argument("--claim-id", required=True)
    retract_claim.add_argument("--actor", required=True)
    retract_claim.add_argument("--reason", required=True)

    retract_source = commands.add_parser("retract-source")
    retract_source.add_argument("--source-id", required=True)
    retract_source.add_argument("--actor", required=True)
    retract_source.add_argument("--reason", required=True)

    commands.add_parser("verify")
    backup = commands.add_parser("backup")
    backup.add_argument("--output-dir", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--backup-dir", type=Path, required=True)
    export = commands.add_parser("export")
    export.add_argument("--output-dir", type=Path, required=True)
    audit = commands.add_parser("audit-replay")
    audit.add_argument("--object-id")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "init":
        memory = FactMemory.initialize(args.root)
        _print(
            {"status": "INITIALIZED", "snapshot_hash": memory.database.snapshot_hash()}
        )
        return
    if args.command == "restore":
        memory = FactMemory(FactDatabase.restore(args.backup_dir, args.root))
        _print({"status": "RESTORED", "snapshot_hash": memory.database.snapshot_hash()})
        return
    memory = FactMemory.open(args.root)
    if args.command == "add-entity":
        _print(asdict(memory.add_entity(**_read_json(args.json))))
    elif args.command == "add-predicate":
        _print(asdict(memory.add_predicate(**_read_json(args.json))))
    elif args.command == "add-source":
        metadata = _read_json(args.metadata)
        metadata["content"] = args.file.read_bytes()
        metadata.setdefault("original_filename", args.file.name)
        _print(asdict(memory.add_source(**metadata)))
    elif args.command == "attach-evidence":
        record = memory.add_evidence(**_read_json(args.json))
        if args.proposal_id:
            proposal = memory.get_proposal(args.proposal_id)
            if record.evidence_id not in proposal.evidence_ids:
                raise ValueError(
                    "evidence must be bound in an immutable proposal revision; create a new proposal"
                )
            if proposal.status == ProposalStatus.RECEIVED:
                proposal = memory.advance_proposal(
                    proposal.proposal_id, ProposalStatus.PARSED
                )
            proposal = memory.advance_proposal(
                proposal.proposal_id, ProposalStatus.EVIDENCE_ATTACHED
            )
            _print(asdict(proposal))
        else:
            _print(asdict(record))
    elif args.command == "propose-claim":
        row = _read_json(args.json)
        row["object_value"] = FactValue.from_dict(row["object_value"])
        row["qualifiers"] = {
            key: FactValue.from_dict(value)
            for key, value in row.get("qualifiers", {}).items()
        }
        _print(asdict(memory.receive_proposal(**row)))
    elif args.command == "review-claim":
        _print(
            asdict(memory.prepare_for_review(args.proposal_id, reviewer=args.reviewer))
        )
    elif args.command == "approve-claim":
        envelope = memory.approve_proposal(
            args.proposal_id,
            reviewer_identity=args.reviewer,
            reviewer_identity_type=args.reviewer_type,
            decision=ApprovalDecision(args.decision),
            contested_approval=args.contested,
        )
        _print(asdict(envelope))
    elif args.command == "commit-claim":
        _print(asdict(memory.commit_proposal(args.proposal_id, args.approval_id)))
    elif args.command == "query":
        row = _read_json(args.json)
        if row.get("object_filter"):
            row["object_filter"] = FactValue.from_dict(row["object_filter"])
        row["qualifier_filters"] = {
            key: FactValue.from_dict(value)
            for key, value in row.get("qualifier_filters", {}).items()
        }
        query = memory.make_query(**row)
        bundle = memory.query(query)
        _print(asdict(bundle))
        print(render_answer(bundle, language=query.language))
    elif args.command == "show-claim":
        _print(asdict(memory.get_claim(args.claim_id)))
    elif args.command == "history":
        _print(memory.claim_history(args.claim_id))
    elif args.command == "conflicts":
        _print(
            [
                asdict(item)
                for item in memory.conflicts(unresolved_only=not args.include_resolved)
            ]
        )
    elif args.command == "supersede":
        memory.supersede_claim(
            args.old_claim_id,
            args.new_claim_id,
            actor=args.actor,
            reason=args.reason,
        )
        _print({"status": "SUPERSEDED"})
    elif args.command == "retract-claim":
        memory.retract_claim(args.claim_id, actor=args.actor, reason=args.reason)
        _print({"status": "RETRACTED"})
    elif args.command == "retract-source":
        memory.retract_source(args.source_id, actor=args.actor, reason=args.reason)
        _print(
            {
                "status": "SOURCE_RETRACTED",
                "affected_claim_ids": [
                    item.claim_id
                    for item in memory.claims_affected_by_source(args.source_id)
                ],
            }
        )
    elif args.command == "verify":
        _print(memory.verify())
    elif args.command == "backup":
        _print(memory.database.backup(args.output_dir))
    elif args.command == "export":
        _print(memory.database.export(args.output_dir))
    elif args.command == "audit-replay":
        _print(memory.database.audit_replay(args.object_id))
    else:
        raise AssertionError(f"unhandled command: {args.command}")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("CLI JSON artifact must be an object")
    return payload


def _print(value: Any) -> None:
    print(canonical_json(value))


if __name__ == "__main__":
    main()
