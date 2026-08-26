"""Safe one-route orchestration across facts, skills, and bounded local tools."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from ai_brain.stage1.specifications import specification_from_dict
from ai_brain.stage2.facts.canonical import content_hash, utc_now
from ai_brain.stage2.facts.models import ClaimStatus, FactQuery, QueryStatus
from ai_brain.stage2.facts.values import FactValue
from ai_brain.stage2.models import ConfirmationDecision as SkillConfirmationDecision
from ai_brain.stage2.router.clarification import make_clarification
from ai_brain.stage2.router.decisions import (
    make_route_receipt,
    validate_decision,
    validate_route_receipt,
)
from ai_brain.stage2.router.exact import ExactUnifiedRouter
from ai_brain.stage2.router.models import (
    ClarificationKind,
    ConfirmationDecision,
    ReplayStatus,
    RequestEnvelope,
    RouteAuthority,
    RouteDecision,
    RouteStatus,
    RouteTarget,
    ToolCallConfirmation,
    ToolCallProposal,
    ToolExecutionStatus,
    ToolResultBundle,
    UnifiedResponseEnvelope,
)
from ai_brain.stage2.router.persistence import RouterStore
from ai_brain.stage2.router.request import validate_request
from ai_brain.stage2.router.tools import ToolInputError


class UnifiedRouterError(RuntimeError):
    pass


class ConfirmationRequiredError(UnifiedRouterError):
    pass


class CrossAuthorityError(PermissionError):
    pass


class UnifiedRouterService:
    def __init__(
        self,
        router: ExactUnifiedRouter,
        *,
        store: RouterStore | None = None,
        clock=utc_now,
    ) -> None:
        self.router = router
        self.store = store
        self._clock = clock
        self._requests: dict[str, RequestEnvelope] = {}
        self._decisions: dict[str, RouteDecision] = {}
        self._tool_proposals: dict[str, ToolCallProposal] = {}
        self._tool_confirmations: dict[str, ToolCallConfirmation] = {}
        self._skill_context: dict[str, tuple[Any, Any, Any]] = {}
        self._route_receipts: dict[str, Any] = {}

    def route(self, request: RequestEnvelope) -> RouteDecision:
        decision = self.router.route(request)
        self._requests[request.request_id] = request
        self._decisions[decision.route_decision_hash] = decision
        self._save(
            "request",
            request,
            request.request_id,
            request.request_hash,
            "REQUEST_RECEIVED",
        )
        event = {
            RouteStatus.EXACT_ROUTE: "ROUTE_EXACT",
            RouteStatus.ASSISTIVE_CANDIDATES: "ROUTE_ASSISTIVE",
            RouteStatus.AMBIGUOUS_ROUTE: "ROUTE_AMBIGUOUS",
            RouteStatus.UNSUPPORTED_ROUTE: "ROUTE_UNSUPPORTED",
            RouteStatus.COMPOSITE_ROUTE: "ROUTE_COMPOSITE",
            RouteStatus.INVALID_REQUEST: "ROUTE_UNSUPPORTED",
        }.get(decision.route_status, "ROUTE_UNSUPPORTED")
        self._save(
            "route_decision",
            decision,
            decision.route_id,
            decision.route_decision_hash,
            event,
        )
        receipt = make_route_receipt(request, decision)
        validate_route_receipt(receipt, request, decision, self.router.dependencies())
        self._route_receipts[decision.route_decision_hash] = receipt
        self._save(
            "route_receipt",
            receipt,
            receipt.receipt_id,
            receipt.receipt_hash,
            "ROUTE_RECEIPT_ISSUED",
        )
        return decision

    def handle(
        self, request: RequestEnvelope
    ) -> tuple[RouteDecision, UnifiedResponseEnvelope]:
        decision = self.route(request)
        return decision, self.respond(request, decision)

    def respond(
        self, request: RequestEnvelope, decision: RouteDecision
    ) -> UnifiedResponseEnvelope:
        validate_request(request)
        validate_decision(decision, request, self.router.dependencies())
        if decision.route_authority == RouteAuthority.ASSISTIVE_PROPOSAL:
            return self._response(
                request, decision, warnings=("MANUAL_ROUTE_REVIEW_REQUIRED",)
            )
        if decision.selected_target == RouteTarget.FACT_QUERY and decision.exact_match:
            if self.router.fact_memory is None:
                raise UnifiedRouterError("FactMemory is unavailable")
            query = self._query_for(request, decision)
            answer = self.router.fact_memory.query(query)
            warnings = tuple(answer.warnings)
            if answer.answer_status == QueryStatus.CONFLICT:
                warnings += ("REVIEW_FACT_CONFLICT",)
            response = self._response(
                request,
                decision,
                fact_answer_hash=answer.answer_hash,
                warnings=warnings,
            )
            if self.store:
                self.store.append_audit(
                    "FACT_ANSWER_RETURNED",
                    {"answer_hash": answer.answer_hash},
                    request.request_id,
                )
            return response
        if (
            decision.selected_target == RouteTarget.SKILL_REQUEST
            and decision.exact_match
        ):
            pending = self._prepare_skill(request, decision)
            return self._response(
                request,
                decision,
                skill_selection_hash=pending.receipt_hash,
                warnings=("EXPLICIT_SKILL_CONFIRMATION_REQUIRED",),
            )
        if (
            decision.selected_target == RouteTarget.TOOL_REQUEST
            and decision.exact_match
        ):
            proposal = self.prepare_tool(request, decision)
            return self._response(
                request,
                decision,
                tool_proposal_hash=proposal.proposal_hash,
                warnings=("EXPLICIT_TOOL_CONFIRMATION_REQUIRED",),
            )
        if decision.selected_target == RouteTarget.CLARIFICATION:
            clarification = make_clarification(
                decision,
                self._clarification_kind(decision),
                missing_field=decision.ambiguity_fields[0]
                if decision.ambiguity_fields
                else "route_target",
            )
            self._save(
                "clarification",
                clarification,
                clarification.clarification_id,
                clarification.clarification_hash,
                "CLARIFICATION_REQUESTED",
            )
            return self._response(
                request,
                decision,
                clarification_hash=clarification.clarification_hash,
            )
        return self._response(request, decision)

    def prepare_tool(
        self, request: RequestEnvelope, decision: RouteDecision
    ) -> ToolCallProposal:
        validate_decision(decision, request, self.router.dependencies())
        if (
            decision.selected_target != RouteTarget.TOOL_REQUEST
            or not decision.exact_match
        ):
            raise CrossAuthorityError("route does not authorize a tool proposal")
        parsed = decision.parser_evidence
        payload = parsed.get("payload", parsed)
        tool_id = str(payload["tool_id"])
        arguments = dict(payload["arguments"])
        descriptor = self.router.tool_registry.descriptor(tool_id)
        body = {
            "proposal_id": f"tool_proposal_{uuid4().hex}",
            "request_id": request.request_id,
            "request_hash": request.request_hash,
            "route_decision_hash": decision.route_decision_hash,
            "tool_id": tool_id,
            "tool_version": descriptor.version,
            "typed_arguments": arguments,
            "argument_hash": content_hash(arguments),
            "tool_implementation_hash": descriptor.implementation_hash,
            "tool_registry_hash": self.router.tool_registry.registry_hash,
            "confirmation_required": True,
            "created_at": self._clock(),
        }
        proposal = ToolCallProposal(**body, proposal_hash=content_hash(body))
        self._tool_proposals[proposal.proposal_hash] = proposal
        self._save(
            "tool_proposal",
            proposal,
            proposal.proposal_id,
            proposal.proposal_hash,
            "TOOL_CALL_PREPARED",
        )
        return proposal

    def confirm_tool(
        self,
        proposal: ToolCallProposal,
        *,
        identity: str,
        identity_type: str = "USER",
        decision: ConfirmationDecision = ConfirmationDecision.CONFIRMED,
    ) -> ToolCallConfirmation:
        self._validate_tool_proposal(proposal)
        if not identity.strip() or identity_type not in {"USER", "TRUSTED_SUPERVISOR"}:
            raise ValueError("valid confirmer identity is required")
        body = {
            "confirmation_id": f"tool_confirmation_{uuid4().hex}",
            "proposal_hash": proposal.proposal_hash,
            "request_hash": proposal.request_hash,
            "route_decision_hash": proposal.route_decision_hash,
            "tool_registry_hash": proposal.tool_registry_hash,
            "argument_hash": proposal.argument_hash,
            "decision": ConfirmationDecision(decision),
            "confirmer_identity": identity,
            "confirmer_identity_type": identity_type,
            "created_at": self._clock(),
        }
        confirmation = ToolCallConfirmation(
            **body, confirmation_hash=content_hash(body)
        )
        self._tool_confirmations[confirmation.confirmation_hash] = confirmation
        self._save(
            "tool_confirmation",
            confirmation,
            confirmation.confirmation_id,
            confirmation.confirmation_hash,
            "TOOL_CALL_CONFIRMED",
        )
        request = self._requests[proposal.request_id]
        decision_artifact = self._decisions[proposal.route_decision_hash]
        receipt = make_route_receipt(
            request,
            decision_artifact,
            confirmer_identity=identity,
            confirmer_identity_type=identity_type,
        )
        validate_route_receipt(
            receipt, request, decision_artifact, self.router.dependencies()
        )
        self._route_receipts[proposal.route_decision_hash] = receipt
        self._save(
            "route_receipt",
            receipt,
            receipt.receipt_id,
            receipt.receipt_hash,
            "ROUTE_CONFIRMATION_BOUND",
        )
        return confirmation

    def execute_tool(
        self,
        proposal: ToolCallProposal,
        confirmation: ToolCallConfirmation | None,
    ) -> ToolResultBundle:
        if confirmation is None:
            raise ConfirmationRequiredError("explicit tool confirmation is required")
        self._validate_tool_proposal(proposal)
        confirmation_body = asdict(confirmation)
        confirmation_hash = confirmation_body.pop("confirmation_hash")
        if content_hash(confirmation_body) != confirmation_hash:
            raise UnifiedRouterError("tool confirmation hash mismatch")
        if self._tool_confirmations.get(confirmation_hash) != confirmation:
            raise UnifiedRouterError("tool confirmation was not issued by this service")
        if (
            confirmation.proposal_hash != proposal.proposal_hash
            or confirmation.request_hash != proposal.request_hash
            or confirmation.route_decision_hash != proposal.route_decision_hash
            or confirmation.argument_hash != proposal.argument_hash
            or confirmation.tool_registry_hash
            != self.router.tool_registry.registry_hash
        ):
            raise UnifiedRouterError("tool confirmation binding mismatch")
        if confirmation.decision != ConfirmationDecision.CONFIRMED:
            raise ConfirmationRequiredError("tool call was not confirmed")
        status = ToolExecutionStatus.EXECUTED
        try:
            output = self.router.tool_registry.execute(
                proposal.tool_id, proposal.typed_arguments
            )
        except ToolInputError as error:
            status = ToolExecutionStatus.REJECTED
            output = {"error": str(error)}
        body = {
            "result_id": f"tool_result_{uuid4().hex}",
            "request_id": proposal.request_id,
            "request_hash": proposal.request_hash,
            "route_decision_hash": proposal.route_decision_hash,
            "proposal_hash": proposal.proposal_hash,
            "confirmation_hash": confirmation.confirmation_hash,
            "tool_id": proposal.tool_id,
            "tool_version": proposal.tool_version,
            "tool_implementation_hash": proposal.tool_implementation_hash,
            "tool_registry_hash": proposal.tool_registry_hash,
            "argument_hash": proposal.argument_hash,
            "status": status,
            "output": output,
            "executed_at": self._clock(),
        }
        result = ToolResultBundle(**body, result_hash=content_hash(body))
        self._save(
            "tool_result",
            result,
            result.result_id,
            result.result_hash,
            "TOOL_EXECUTED"
            if status == ToolExecutionStatus.EXECUTED
            else "TOOL_EXECUTION_FAILED",
        )
        return result

    def confirm_skill(
        self,
        decision: RouteDecision,
        *,
        identity: str,
        identity_type: str = "USER",
        confirmation_decision: SkillConfirmationDecision = SkillConfirmationDecision.CONFIRM_SELECTION,
    ):
        if decision.selected_target != RouteTarget.SKILL_REQUEST:
            raise CrossAuthorityError("route does not authorize skill confirmation")
        request = self._requests.get(decision.request_id)
        if request is None:
            raise UnifiedRouterError("skill request context is unavailable")
        validate_decision(decision, request, self.router.dependencies())
        try:
            query, result, pending = self._skill_context[decision.route_decision_hash]
        except KeyError as error:
            raise UnifiedRouterError("skill selection was not prepared") from error
        confirmed = self.router.skill_router.confirm_selection(
            pending,
            identity=identity,
            identity_type=identity_type,
            decision=confirmation_decision,
        )
        self._skill_context[decision.route_decision_hash] = (query, result, confirmed)
        receipt = make_route_receipt(
            request,
            decision,
            confirmer_identity=identity,
            confirmer_identity_type=identity_type,
        )
        validate_route_receipt(receipt, request, decision, self.router.dependencies())
        self._route_receipts[decision.route_decision_hash] = receipt
        self._save(
            "route_receipt",
            receipt,
            receipt.receipt_id,
            receipt.receipt_hash,
            "ROUTE_CONFIRMATION_BOUND",
        )
        if self.store:
            self.store.append_audit(
                "SKILL_SELECTION_CONFIRMED",
                {"selection_receipt_hash": confirmed.receipt_hash},
                decision.request_id,
            )
        return confirmed

    def clarify(
        self,
        request: RequestEnvelope,
        decision: RouteDecision,
        clarified_request: RequestEnvelope,
    ) -> tuple[RouteDecision, UnifiedResponseEnvelope]:
        validate_decision(decision, request, self.router.dependencies())
        if decision.selected_target != RouteTarget.CLARIFICATION:
            raise UnifiedRouterError("route does not require clarification")
        if clarified_request.request_id == request.request_id:
            raise ValueError("clarification must use a fresh request ID")
        if self.store:
            self.store.append_audit(
                "CLARIFICATION_RESOLVED",
                {
                    "prior_route_hash": decision.route_decision_hash,
                    "clarified_request_hash": clarified_request.request_hash,
                    "round": 1,
                },
                request.request_id,
            )
        clarified_decision, response = self.handle(clarified_request)
        if clarified_decision.selected_target == RouteTarget.CLARIFICATION:
            response = self._response(
                clarified_request,
                clarified_decision,
                clarification_hash=response.clarification_hash,
                warnings=tuple(response.warnings) + ("CLARIFICATION_LIMIT_REACHED",),
            )
        return clarified_decision, response

    def dispatch_skill(
        self,
        request: RequestEnvelope,
        decision: RouteDecision,
        *,
        proposal,
        installed_receipt,
        initial_state: dict[str, int],
        limits=None,
    ):
        validate_decision(decision, request, self.router.dependencies())
        if decision.selected_target != RouteTarget.SKILL_REQUEST:
            raise CrossAuthorityError("route does not authorize skill dispatch")
        query, result, selection = self._skill_context[decision.route_decision_hash]
        if selection.confirmation_decision not in {
            SkillConfirmationDecision.CONFIRM_SELECTION,
            SkillConfirmationDecision.CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION,
        }:
            raise ConfirmationRequiredError("explicit skill confirmation is required")
        kwargs = {
            "query": query,
            "result": result,
            "selection": selection,
            "proposal": proposal,
            "installed_receipt": installed_receipt,
            "initial_state": initial_state,
        }
        if limits is not None:
            kwargs["limits"] = limits
        dispatched = self.router.skill_router.dispatch(**kwargs)
        if self.store:
            self.store.append_audit(
                "SKILL_DISPATCHED",
                {"dispatch_hash": dispatched[2].dispatch_hash},
                request.request_id,
            )
        return dispatched

    def replay(self, response: UnifiedResponseEnvelope) -> ReplayStatus:
        body = asdict(response)
        digest = body.pop("response_hash")
        if content_hash(body) != digest:
            raise UnifiedRouterError("unified response hash mismatch")
        snapshot = response.dependency_snapshots.get("fact_memory_hash")
        current = self.router.dependencies().fact_memory_hash
        return (
            ReplayStatus.CURRENT if snapshot == current else ReplayStatus.STALE_SNAPSHOT
        )

    def reject_cross_authority(
        self, source_domain: RouteTarget, target_domain: RouteTarget
    ) -> None:
        if source_domain != target_domain:
            if self.store:
                self.store.append_audit(
                    "CROSS_AUTHORITY_ACTION_REJECTED",
                    {"source": source_domain, "target": target_domain},
                )
            raise CrossAuthorityError(
                f"{source_domain} cannot authorize {target_domain}"
            )

    def _prepare_skill(self, request: RequestEnvelope, decision: RouteDecision):
        if self.router.skill_router is None:
            raise UnifiedRouterError("SkillRegistry is unavailable")
        if "specification" in decision.parser_evidence:
            specification = specification_from_dict(
                json.loads(json.dumps(decision.parser_evidence["specification"]))
            )
            query, result = self.router.skill_router.search_structured(specification)
        else:
            query, result = self.router.skill_router.search_controlled(
                request.original_input, request.language or "en"
            )
        if len(result.candidates) != 1:
            raise UnifiedRouterError("exact skill route no longer has one candidate")
        pending = self.router.skill_router.prepare_selection(
            query, result, result.candidates[0].skill_id
        )
        self._skill_context[decision.route_decision_hash] = (query, result, pending)
        if self.store:
            self.store.append_audit(
                "SKILL_SELECTION_PREPARED",
                {"selection_receipt_hash": pending.receipt_hash},
                request.request_id,
            )
        return pending

    def _query_for(
        self, request: RequestEnvelope, decision: RouteDecision
    ) -> FactQuery:
        if "fact_query" in decision.parser_evidence:
            row = dict(decision.parser_evidence["fact_query"])
            if row.get("object_filter") is not None:
                row["object_filter"] = FactValue.from_dict(row["object_filter"])
            row["qualifier_filters"] = {
                key: FactValue.from_dict(value)
                for key, value in row.get("qualifier_filters", {}).items()
            }
            row["accepted_statuses"] = tuple(
                ClaimStatus(item) for item in row["accepted_statuses"]
            )
            return FactQuery(**row)
        payload = decision.parser_evidence["payload"]
        return self.router.fact_memory.make_query(**payload)

    def _validate_tool_proposal(self, proposal: ToolCallProposal) -> None:
        body = asdict(proposal)
        digest = body.pop("proposal_hash")
        if content_hash(body) != digest:
            raise UnifiedRouterError("tool proposal hash mismatch")
        if self._tool_proposals.get(digest) != proposal:
            raise UnifiedRouterError("tool proposal was not issued by this service")
        request = self._requests.get(proposal.request_id)
        decision = self._decisions.get(proposal.route_decision_hash)
        if request is None or decision is None:
            raise UnifiedRouterError("tool proposal context is unavailable")
        validate_decision(decision, request, self.router.dependencies())
        descriptor = self.router.tool_registry.descriptor(proposal.tool_id)
        if (
            proposal.request_hash != request.request_hash
            or proposal.tool_registry_hash != self.router.tool_registry.registry_hash
            or proposal.tool_implementation_hash != descriptor.implementation_hash
            or proposal.argument_hash != content_hash(proposal.typed_arguments)
        ):
            raise UnifiedRouterError("tool proposal dependency is stale or changed")

    @staticmethod
    def _clarification_kind(decision: RouteDecision) -> ClarificationKind:
        candidates = set(decision.candidate_targets)
        if candidates == {RouteTarget.FACT_QUERY, RouteTarget.SKILL_REQUEST}:
            return ClarificationKind.FACT_OR_SKILL
        if candidates == {RouteTarget.FACT_QUERY, RouteTarget.TOOL_REQUEST}:
            return ClarificationKind.FACT_OR_TOOL
        if candidates == {RouteTarget.SKILL_REQUEST, RouteTarget.TOOL_REQUEST}:
            return ClarificationKind.SKILL_OR_TOOL
        evidence = str(decision.parser_evidence.get("ambiguity", ""))
        try:
            return ClarificationKind(evidence)
        except ValueError:
            return ClarificationKind.UNSUPPORTED_OPERATION

    def _response(
        self, request: RequestEnvelope, decision: RouteDecision, **updates
    ) -> UnifiedResponseEnvelope:
        body = {
            "response_id": f"response_{uuid4().hex}",
            "request_id": request.request_id,
            "request_hash": request.request_hash,
            "route_decision_hash": decision.route_decision_hash,
            "route_target": decision.selected_target,
            "route_authority": decision.route_authority,
            "route_status": decision.route_status,
            "fact_answer_hash": None,
            "skill_selection_hash": None,
            "skill_dispatch_hash": None,
            "tool_proposal_hash": None,
            "tool_result_hash": None,
            "clarification_hash": None,
            "warnings": (),
            "dependency_snapshots": asdict(decision.dependencies),
            "created_at": self._clock(),
        }
        body.update(updates)
        response = UnifiedResponseEnvelope(**body, response_hash=content_hash(body))
        self._save(
            "response",
            response,
            response.response_id,
            response.response_hash,
            "UNIFIED_RESPONSE_RETURNED",
        )
        return response

    def _save(
        self, kind: str, artifact: Any, artifact_id: str, artifact_hash: str, event: str
    ) -> None:
        if self.store is not None:
            self.store.save(
                kind,
                artifact,
                artifact_id=artifact_id,
                artifact_hash=artifact_hash,
                request_id=getattr(artifact, "request_id", None),
                event_type=event,
            )
