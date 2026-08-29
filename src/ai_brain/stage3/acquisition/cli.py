"""Offline trusted CLI for bounded source acquisition."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.clarifications import generate_clarifications
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.evaluation import evaluate_proposals
from ai_brain.stage3.acquisition.evidence import build_field_evidence
from ai_brain.stage3.acquisition.models import ProposalApproval, ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.proposals import propose_knowledge
from ai_brain.stage3.acquisition.replay import replay_acquisition
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.segmentation import segment_bundle
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.verification import verify_proposals
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityResolutionReceipt,
)
from ai_brain.stage3.capabilities.persistence import load_registry
from ai_brain.stage3.domains.approval import (
    DomainPackApprovalEnvelope,
    PackApprovalDecision,
)
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.providers.persistence import load_provider_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-brain-acquire")
    parser.add_argument("--store", type=Path, default=Path(".ai-brain/acquisition"))
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("paths", nargs="+", type=Path)
    ingest.add_argument("--bundle-id", required=True)
    ingest.add_argument("--domain-tag", action="append", default=[])
    ingest.add_argument("--language", choices=("ru", "en", "mixed"), default="en")
    for name in ("segment", "replay"):
        command = commands.add_parser(name)
        command.add_argument("--bundle", required=True)
        if name == "replay":
            command.add_argument("--segments", required=True)
    propose = commands.add_parser("propose")
    propose.add_argument("--bundle", required=True)
    propose.add_argument("--segments", required=True)
    evidence = commands.add_parser("build-field-evidence")
    evidence.add_argument("--bundle", required=True)
    evidence.add_argument("--segments", required=True)
    evidence.add_argument("--proposals", required=True)
    show = commands.add_parser("show-proposals")
    show.add_argument("--proposals", required=True)
    clarify = commands.add_parser("clarify")
    clarify.add_argument("--proposals", required=True)
    review = commands.add_parser("review")
    review.add_argument("--proposals", required=True)
    review.add_argument("--proposal-id", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument(
        "--decision",
        choices=tuple(item.value for item in ReviewDecision),
        required=True,
    )
    verify = commands.add_parser("verify")
    verify.add_argument("--bundle", required=True)
    verify.add_argument("--segments", required=True)
    verify.add_argument("--proposals", required=True)
    verify.add_argument("--field-evidence")
    compile_pack = commands.add_parser("compile-pack")
    compile_pack.add_argument("--bundle", required=True)
    compile_pack.add_argument("--segments", required=True)
    compile_pack.add_argument("--proposals", required=True)
    compile_pack.add_argument("--approvals", type=Path, required=True)
    compile_pack.add_argument("--domain-id", required=True)
    compile_pack.add_argument("--output", type=Path, required=True)
    compile_pack.add_argument("--field-evidence")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--proposals", required=True)
    evaluate.add_argument("--segments", required=True)
    evaluate.add_argument("--golden", type=Path, required=True)
    evaluate.add_argument("--field-evidence")
    install = commands.add_parser("install")
    install.add_argument("--pack", type=Path, required=True)
    install.add_argument("--approval", type=Path, required=True)
    install.add_argument("--registry-root", type=Path, required=True)
    install.add_argument("--capabilities", type=Path, required=True)
    install.add_argument("--providers", type=Path, required=True)
    export = commands.add_parser("export")
    export.add_argument("--bundle", required=True)
    export.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = AcquisitionStore.open_or_initialize(args.store)
    if args.command == "ingest":
        bundle = ingest_bundle(
            tuple(args.paths),
            bundle_id=args.bundle_id,
            domain_tags=tuple(args.domain_tag),
            language=args.language,
            store=store,
        )
        object_path = store.save_bundle(bundle)
        result = {
            "status": "INGESTED",
            "bundle_hash": bundle.bundle_hash,
            "bundle_object": object_path.stem,
        }
    elif args.command == "segment":
        bundle = store.load_bundle(args.bundle)
        segments = segment_bundle(bundle, store)
        digest = store.save_segments(bundle.bundle_hash, segments)
        result = {
            "status": "SEGMENTED",
            "segment_count": len(segments),
            "segment_set": digest,
        }
    elif args.command == "propose":
        bundle = store.load_bundle(args.bundle)
        segments = store.load_segments(args.segments)
        proposals = propose_knowledge(bundle, segments, explicit_trust_stages=True)
        digest = store.save_proposals(args.segments, proposals)
        result = {
            "status": "PROPOSED",
            "proposal_count": len(proposals),
            "proposal_set": digest,
        }
    elif args.command == "show-proposals":
        proposals = store.load_proposals(args.proposals)
        result = {
            "status": "OK",
            "proposals": [
                {
                    "proposal_id": item.proposal_id,
                    "kind": item.proposed_kind.value,
                    "status": item.status.value,
                }
                for item in proposals
            ],
        }
    elif args.command == "build-field-evidence":
        bundle = store.load_bundle(args.bundle)
        segments = store.load_segments(args.segments)
        values = build_field_evidence(
            bundle,
            segments,
            store.load_proposals(args.proposals),
            store,
        )
        digest = store.save_field_evidence(args.proposals, values)
        result = {
            "status": "FIELD_EVIDENCE_BUILT",
            "field_evidence_count": len(values),
            "field_evidence_set": digest,
        }
    elif args.command == "clarify":
        questions = generate_clarifications(store.load_proposals(args.proposals))
        result = {
            "status": "OK",
            "clarifications": [asdict(item) for item in questions],
        }
    elif args.command == "review":
        proposals = store.load_proposals(args.proposals)
        selected = next(
            item for item in proposals if item.proposal_id == args.proposal_id
        )
        updated, review, approval = review_proposal(
            selected,
            reviewer_identity=args.reviewer,
            reviewer_type=ActorIdentityType.USER,
            decision=ReviewDecision(args.decision),
            rationale="CLI explicit review",
        )
        result = {
            "status": updated.status.value,
            "proposal": asdict(updated),
            "review": asdict(review),
            "approval": asdict(approval) if approval else None,
        }
    elif args.command == "verify":
        bundle = store.load_bundle(args.bundle)
        segments = store.load_segments(args.segments)
        proposals = verify_proposals(
            bundle,
            segments,
            store.load_proposals(args.proposals),
            store,
            field_evidence=(
                store.load_field_evidence(args.field_evidence)
                if args.field_evidence
                else None
            ),
        )
        digest = store.save_proposals(args.segments, proposals)
        result = {
            "status": "VERIFIED",
            "proposal_set": digest,
            "source_entailed_count": sum(
                item.status.value == "SOURCE_ENTAILED" for item in proposals
            ),
            "structure_verified_count": sum(
                item.status.value == "STRUCTURE_VERIFIED" for item in proposals
            ),
            "legacy_verified_count": sum(
                item.status.value == "VERIFIED" for item in proposals
            ),
        }
    elif args.command == "compile-pack":
        bundle = store.load_bundle(args.bundle)
        segments = store.load_segments(args.segments)
        proposals = store.load_proposals(args.proposals)
        approvals = tuple(
            ProposalApproval(**item)
            for item in json.loads(args.approvals.read_text(encoding="utf-8"))
        )
        pack = compile_provisional_pack(
            bundle,
            segments,
            proposals,
            approvals,
            args.output,
            domain_id=args.domain_id,
            field_evidence=(
                store.load_field_evidence(args.field_evidence)
                if args.field_evidence
                else None
            ),
        )
        result = {
            "status": "PROVISIONAL",
            "pack_hash": pack.manifest.pack_content_hash,
            "installed": False,
        }
    elif args.command == "evaluate":
        golden = json.loads(args.golden.read_text(encoding="utf-8"))
        result = evaluate_proposals(
            store.load_proposals(args.proposals),
            golden,
            store.load_segments(args.segments),
            field_evidence=(
                store.load_field_evidence(args.field_evidence)
                if args.field_evidence
                else ()
            ),
        )
    elif args.command == "replay":
        result = replay_acquisition(
            store.load_bundle(args.bundle), store.load_segments(args.segments), store
        )
    elif args.command == "export":
        bundle = store.load_bundle(args.bundle)
        text = canonical_json(asdict(bundle)) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
        result = {
            "status": "EXPORTED",
            "output": str(args.output),
            "bundle_hash": bundle.bundle_hash,
        }
    else:
        providers = load_provider_registry(args.providers)
        capabilities = load_registry(args.capabilities, providers)
        registry = InstalledDomainRegistry.open_or_initialize(
            args.registry_root,
            capability_registry=capabilities,
            provider_registry=providers,
        )
        approval, receipts = _approval_bundle(args.approval)
        installed = registry.install(load_pack(args.pack), approval, receipts)
        result = {
            "status": "INSTALLED",
            "domain_id": installed.domain_id,
            "pack_version": installed.pack_version,
            "pack_hash": installed.pack_hash,
            "installation_receipt_hash": installed.installation_receipt_hash,
        }
    print(canonical_json(result))
    return 0


def _approval_bundle(path: Path):
    row = json.loads(path.read_text(encoding="utf-8"))
    approval_row = dict(row["approval"])
    approval_row["reviewer_type"] = ActorIdentityType(approval_row["reviewer_type"])
    approval_row["decision"] = PackApprovalDecision(approval_row["decision"])
    for key in (
        "source_binding_hashes",
        "capability_resolution_receipt_hashes",
    ):
        approval_row[key] = tuple(approval_row[key])
    approval = DomainPackApprovalEnvelope(**approval_row)
    receipts = []
    for item in row["resolutions"]:
        value = dict(item)
        for key in ("dependency_capabilities", "dependency_receipt_hashes"):
            value[key] = tuple(value[key])
        value["authority_class"] = AuthorityClass(value["authority_class"])
        receipts.append(CapabilityResolutionReceipt(**value))
    return approval, tuple(receipts)


if __name__ == "__main__":
    raise SystemExit(main())
