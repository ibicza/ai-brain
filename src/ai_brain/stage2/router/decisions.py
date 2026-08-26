"""Hash-bound route decision and receipt construction."""

from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from ai_brain.stage2.facts.canonical import content_hash, utc_now
from ai_brain.stage2.router.models import (
    DependencySnapshot,
    NextAction,
    RequestEnvelope,
    RouteAuthority,
    RouteDecision,
    RouteReceipt,
    RouteStatus,
    RouteTarget,
)


def make_decision(
    request: RequestEnvelope,
    *,
    target: RouteTarget,
    status: RouteStatus,
    authority: RouteAuthority,
    exact_match: bool,
    candidates: tuple[RouteTarget, ...],
    parser_evidence: dict,
    ambiguity_fields: tuple[str, ...],
    next_action: NextAction,
    dependencies: DependencySnapshot,
    clock=utc_now,
) -> RouteDecision:
    body = {
        "route_id": f"route_{uuid4().hex}",
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "selected_target": target,
        "route_status": status,
        "route_authority": authority,
        "exact_match": exact_match,
        "candidate_targets": candidates,
        "parser_evidence": _trusted_value(parser_evidence),
        "ambiguity_fields": ambiguity_fields,
        "required_next_action": next_action,
        "dependencies": dependencies,
        "dependency_snapshot_hash": dependencies.dependency_snapshot_hash,
        "created_at": clock(),
    }
    return RouteDecision(**body, route_decision_hash=content_hash(body))


def _trusted_value(value):
    if isinstance(value, float):
        return format(value, ".17g")
    if isinstance(value, dict):
        return {str(key): _trusted_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_trusted_value(item) for item in value)
    return value


def validate_decision(
    decision: RouteDecision,
    request: RequestEnvelope,
    current: DependencySnapshot,
) -> None:
    body = asdict(decision)
    digest = body.pop("route_decision_hash")
    if content_hash(body) != digest:
        raise ValueError("route decision hash mismatch")
    if (
        decision.request_id != request.request_id
        or decision.request_hash != request.request_hash
    ):
        raise ValueError("route decision belongs to another request")
    if decision.dependencies != current:
        raise ValueError("route decision dependencies are stale")
    if (
        decision.route_authority == RouteAuthority.ASSISTIVE_PROPOSAL
        and decision.exact_match
    ):
        raise ValueError("assistive route cannot carry exact authority")


def make_route_receipt(
    request: RequestEnvelope,
    decision: RouteDecision,
    *,
    clarification_hash: str | None = None,
    confirmer_identity: str | None = None,
    confirmer_identity_type: str | None = None,
    clock=utc_now,
) -> RouteReceipt:
    body = {
        "receipt_id": f"route_receipt_{uuid4().hex}",
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "route_decision_hash": decision.route_decision_hash,
        "selected_target": decision.selected_target,
        "route_authority": decision.route_authority,
        "exact_parser_evidence_hash": content_hash(decision.parser_evidence),
        "dependency_hash": content_hash(asdict(decision.dependencies)),
        "dependency_snapshot_hash": decision.dependency_snapshot_hash,
        "clarification_hash": clarification_hash,
        "confirmer_identity": confirmer_identity,
        "confirmer_identity_type": confirmer_identity_type,
        "created_at": clock(),
    }
    provisional = RouteReceipt(**body)
    receipt_body = asdict(provisional)
    receipt_body.pop("receipt_hash")
    return RouteReceipt(**body, receipt_hash=content_hash(receipt_body))


def validate_route_receipt(
    receipt: RouteReceipt,
    request: RequestEnvelope,
    decision: RouteDecision,
    current: DependencySnapshot,
) -> None:
    body = asdict(receipt)
    digest = body.pop("receipt_hash")
    if content_hash(body) != digest:
        raise ValueError("route receipt hash mismatch")
    validate_decision(decision, request, current)
    if (
        receipt.request_id != request.request_id
        or receipt.request_hash != request.request_hash
        or receipt.route_decision_hash != decision.route_decision_hash
        or receipt.selected_target != decision.selected_target
        or receipt.route_authority != decision.route_authority
        or receipt.exact_parser_evidence_hash != content_hash(decision.parser_evidence)
        or receipt.dependency_hash != content_hash(asdict(decision.dependencies))
        or receipt.dependency_snapshot_hash != decision.dependency_snapshot_hash
    ):
        raise ValueError("route receipt binding mismatch")
