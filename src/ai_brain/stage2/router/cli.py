"""CPU-only CLI for the trusted unified router."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.registry import SkillRegistry
from ai_brain.stage2.router.exact import ExactUnifiedRouter
from ai_brain.stage2.router.models import (
    ConfirmationDecision,
    DependencySnapshot,
    RequestEnvelope,
    RequestSourceKind,
    RouteAuthority,
    RouteDecision,
    RouteStatus,
    RouteTarget,
    ToolCallConfirmation,
    ToolCallProposal,
    UnifiedResponseEnvelope,
)
from ai_brain.stage2.router.persistence import RouterStore
from ai_brain.stage2.router.request import create_request
from ai_brain.stage2.router.service import UnifiedRouterService
from ai_brain.stage2.router.tool_registry import ToolRegistry
from ai_brain.stage2.service import Stage2Router


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-brain-router")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fact-root", type=Path)
    parser.add_argument("--skill-registry", type=Path)
    parser.add_argument("--rule-memory", type=Path)
    parser.add_argument("--stage1-audit", type=Path)
    parser.add_argument("--stage2-audit", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    route = commands.add_parser("route")
    route.add_argument("--request", type=Path, required=True)
    text = commands.add_parser("route-text")
    text.add_argument("--language", choices=("ru", "en"), required=True)
    text.add_argument("--text", required=True)
    text.add_argument("--assistive", action="store_true")
    show = commands.add_parser("show-route")
    show.add_argument("--route-id", required=True)
    clarify = commands.add_parser("clarify")
    clarify.add_argument("--route-id", required=True)
    clarify.add_argument("--answer", type=Path, required=True)
    confirm_skill = commands.add_parser("confirm-skill")
    confirm_skill.add_argument("--route-id", required=True)
    confirm_skill.add_argument("--identity", required=True)
    dispatch_skill = commands.add_parser("dispatch-skill")
    dispatch_skill.add_argument("--route-id", required=True)
    dispatch_skill.add_argument("--identity", required=True)
    dispatch_skill.add_argument("--proposal", type=Path, required=True)
    dispatch_skill.add_argument("--installed-receipt", type=Path, required=True)
    dispatch_skill.add_argument("--initial-state", type=Path, required=True)
    confirm = commands.add_parser("confirm-tool")
    confirm.add_argument("--proposal-hash", required=True)
    confirm.add_argument("--identity", required=True)
    confirm.add_argument("--identity-type", default="USER")
    execute = commands.add_parser("execute-tool")
    execute.add_argument("--proposal-hash", required=True)
    execute.add_argument("--confirmation-hash", required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("--response-hash", required=True)
    commands.add_parser("verify")
    backup = commands.add_parser("backup")
    backup.add_argument("--output-dir", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--backup-dir", type=Path, required=True)
    commands.add_parser("audit-replay")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "init":
        store = RouterStore.initialize(args.root)
        _print(store.verify())
        return
    if args.command == "restore":
        _print(RouterStore.restore(args.backup_dir, args.root).verify())
        return
    store = RouterStore(args.root)
    if args.command == "show-route":
        _print(store.get("route_decision", args.route_id))
        return
    if args.command in {"verify", "audit-replay"}:
        _print(store.verify())
        return
    if args.command == "backup":
        _print(store.backup(args.output_dir))
        return
    service = _service(args, store)
    if args.command == "route-text":
        request = create_request(
            RequestSourceKind.ASSISTIVE_TEXT
            if args.assistive
            else RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input=args.text,
            language=args.language,
        )
        decision, response = service.handle(request)
        _print(
            {
                "request": asdict(request),
                "decision": asdict(decision),
                "response": asdict(response),
            }
        )
    elif args.command == "route":
        row = _read(args.request)
        request = _request(row) if "request_hash" in row else create_request(**row)
        decision, response = service.handle(request)
        _print(
            {
                "request": asdict(request),
                "decision": asdict(decision),
                "response": asdict(response),
            }
        )
    elif args.command == "clarify":
        request, decision = _route_context(store, args.route_id)
        service._requests[request.request_id] = request
        service._decisions[decision.route_decision_hash] = decision
        row = _read(args.answer)
        clarified = _request(row) if "request_hash" in row else create_request(**row)
        clarified_decision, response = service.clarify(request, decision, clarified)
        _print(
            {
                "decision": asdict(clarified_decision),
                "response": asdict(response),
            }
        )
    elif args.command == "confirm-skill":
        request, decision = _route_context(store, args.route_id)
        service._requests[request.request_id] = request
        service._decisions[decision.route_decision_hash] = decision
        service.respond(request, decision)
        _print(asdict(service.confirm_skill(decision, identity=args.identity)))
    elif args.command == "dispatch-skill":
        from ai_brain.stage1.serde import (
            proposal_from_json,
            read_json,
            receipt_from_json,
        )

        request, decision = _route_context(store, args.route_id)
        service._requests[request.request_id] = request
        service._decisions[decision.route_decision_hash] = decision
        service.respond(request, decision)
        service.confirm_skill(decision, identity=args.identity)
        proposal = proposal_from_json(read_json(args.proposal))
        receipt = receipt_from_json(read_json(args.installed_receipt))
        state = _read(args.initial_state)
        _, execution, dispatch = service.dispatch_skill(
            request,
            decision,
            proposal=proposal,
            installed_receipt=receipt,
            initial_state=state,
        )
        _print({"execution": asdict(execution), "dispatch": asdict(dispatch)})
    elif args.command == "confirm-tool":
        proposal = _proposal(_artifact(store, args.proposal_hash, "tool_proposal"))
        _restore_context(service, store, proposal)
        _print(
            asdict(
                service.confirm_tool(
                    proposal, identity=args.identity, identity_type=args.identity_type
                )
            )
        )
    elif args.command == "execute-tool":
        proposal = _proposal(_artifact(store, args.proposal_hash, "tool_proposal"))
        confirmation = _confirmation(
            _artifact(store, args.confirmation_hash, "tool_confirmation")
        )
        _restore_context(service, store, proposal, confirmation)
        _print(asdict(service.execute_tool(proposal, confirmation)))
    elif args.command == "replay":
        response = _response(_artifact(store, args.response_hash, "response"))
        _print({"status": service.replay(response)})


def _service(args, store: RouterStore) -> UnifiedRouterService:
    fact_memory = FactMemory.open(args.fact_root) if args.fact_root else None
    skill_router = None
    skill_options = (
        args.skill_registry,
        args.rule_memory,
        args.stage1_audit,
        args.stage2_audit,
    )
    if any(skill_options):
        if not all(skill_options):
            raise ValueError("all skill routing paths must be supplied together")
        registry = SkillRegistry.load(args.skill_registry)
        skill_router = Stage2Router(
            registry=registry,
            memory_path=args.rule_memory,
            stage1_audit_path=args.stage1_audit,
            stage2_audit_path=args.stage2_audit,
        )
    router = ExactUnifiedRouter(
        tool_registry=ToolRegistry.default(),
        fact_memory=fact_memory,
        skill_router=skill_router,
    )
    return UnifiedRouterService(router, store=store)


def _restore_context(
    service: UnifiedRouterService,
    store: RouterStore,
    proposal: ToolCallProposal,
    confirmation: ToolCallConfirmation | None = None,
) -> None:
    request = _request(store.get("request", proposal.request_id))
    _, decision_row = store.find_hash(proposal.route_decision_hash)
    decision = _decision(decision_row)
    service._requests[request.request_id] = request
    service._decisions[decision.route_decision_hash] = decision
    service._tool_proposals[proposal.proposal_hash] = proposal
    if confirmation is not None:
        service._tool_confirmations[confirmation.confirmation_hash] = confirmation


def _artifact(
    store: RouterStore, artifact_hash: str, expected_type: str
) -> dict[str, Any]:
    artifact_type, payload = store.find_hash(artifact_hash)
    if artifact_type != expected_type:
        raise ValueError(f"expected {expected_type} artifact, received {artifact_type}")
    return payload


def _route_context(
    store: RouterStore, route_id: str
) -> tuple[RequestEnvelope, RouteDecision]:
    decision = _decision(store.get("route_decision", route_id))
    request = _request(store.get("request", decision.request_id))
    return request, decision


def _request(row: dict[str, Any]) -> RequestEnvelope:
    row = dict(row)
    row["source_kind"] = RequestSourceKind(row["source_kind"])
    return RequestEnvelope(**row)


def _decision(row: dict[str, Any]) -> RouteDecision:
    row = dict(row)
    row["selected_target"] = RouteTarget(row["selected_target"])
    row["route_status"] = RouteStatus(row["route_status"])
    row["route_authority"] = RouteAuthority(row["route_authority"])
    row["candidate_targets"] = tuple(
        RouteTarget(item) for item in row["candidate_targets"]
    )
    from ai_brain.stage2.router.models import NextAction

    row["required_next_action"] = NextAction(row["required_next_action"])
    row["ambiguity_fields"] = tuple(row["ambiguity_fields"])
    row["dependencies"] = DependencySnapshot(**row["dependencies"])
    return RouteDecision(**row)


def _proposal(row: dict[str, Any]) -> ToolCallProposal:
    return ToolCallProposal(**row)


def _confirmation(row: dict[str, Any]) -> ToolCallConfirmation:
    row = dict(row)
    row["decision"] = ConfirmationDecision(row["decision"])
    return ToolCallConfirmation(**row)


def _response(row: dict[str, Any]) -> UnifiedResponseEnvelope:
    row = dict(row)
    row["route_target"] = RouteTarget(row["route_target"])
    row["route_authority"] = RouteAuthority(row["route_authority"])
    row["route_status"] = RouteStatus(row["route_status"])
    row["warnings"] = tuple(row["warnings"])
    return UnifiedResponseEnvelope(**row)


def _read(path: Path) -> dict[str, Any]:
    row = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(row, dict):
        raise TypeError("request JSON must be an object")
    return row


def _print(value: Any) -> None:
    print(canonical_json(value))


if __name__ == "__main__":
    main()
