"""Deterministic authority-aware route selection."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.specifications import specification_from_dict
from ai_brain.stage1.version import RULE_MEMORY_SCHEMA_VERSION, STAGE1_VERSION
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import ClaimStatus, FactQuery
from ai_brain.stage2.facts.values import FactValue
from ai_brain.stage2.facts.version import (
    FACT_CONFLICT_POLICY_VERSION,
    FACT_MEMORY_SCHEMA_VERSION,
)
from ai_brain.stage2.models import EquivalenceScope, SearchStatus
from ai_brain.stage2.registry import rule_memory_hash
from ai_brain.stage2.router.controlled import (
    looks_composite,
    parse_fact,
    parse_skill,
    parse_tool,
)
from ai_brain.stage2.router.decisions import make_decision
from ai_brain.stage2.router.models import (
    DependencySnapshot,
    NextAction,
    RequestEnvelope,
    RequestSourceKind,
    RouteAuthority,
    RouteDecision,
    RouteStatus,
    RouteTarget,
)
from ai_brain.stage2.router.request import validate_request
from ai_brain.stage2.router.tool_registry import ToolRegistry
from ai_brain.stage2.router.version import (
    EQUIVALENCE_POLICY_VERSION,
    ROUTE_POLICY_VERSION,
    TOOL_IMPLEMENTATION_POLICY_VERSION,
    TOOL_REGISTRY_SCHEMA_VERSION,
    UNIFIED_ROUTER_SCHEMA_VERSION,
)
from ai_brain.stage2.version import SKILL_REGISTRY_SCHEMA_VERSION, STAGE2_SCHEMA_VERSION


class ExactUnifiedRouter:
    """One request, one exact authority domain, or a fail-closed result."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        fact_memory: FactMemory | None = None,
        skill_router=None,
    ) -> None:
        self.tool_registry = tool_registry
        self.fact_memory = fact_memory
        self.skill_router = skill_router

    def dependencies(self) -> DependencySnapshot:
        registry = self.skill_router.registry if self.skill_router is not None else None
        live_rule_memory_hash = None
        self.rule_memory_recovery_source = None
        if self.skill_router is not None:
            memory = RuleMemory.load_with_backup(self.skill_router.memory_path)
            registry.validate_against_rule_memory(memory)
            live_rule_memory_hash = rule_memory_hash(memory)
            self.rule_memory_recovery_source = memory.recovery_source
        body = {
            "fact_memory_hash": (
                self.fact_memory.database.snapshot_hash()
                if self.fact_memory is not None
                else None
            ),
            "skill_registry_hash": (
                registry.manifest.registry_hash if registry else None
            ),
            "rule_memory_hash": live_rule_memory_hash,
            "tool_registry_hash": self.tool_registry.registry_hash,
            "tool_implementation_manifest_hashes": self.tool_registry.current_manifest_hashes(),
            "stage1_version": STAGE1_VERSION,
            "stage2_schema_version": STAGE2_SCHEMA_VERSION,
            "fact_memory_schema_version": FACT_MEMORY_SCHEMA_VERSION,
            "skill_registry_schema_version": SKILL_REGISTRY_SCHEMA_VERSION,
            "rule_memory_schema_version": RULE_MEMORY_SCHEMA_VERSION,
            "tool_registry_schema_version": TOOL_REGISTRY_SCHEMA_VERSION,
            "unified_router_schema_version": UNIFIED_ROUTER_SCHEMA_VERSION,
            "route_policy_version": ROUTE_POLICY_VERSION,
            "tool_policy_version": TOOL_IMPLEMENTATION_POLICY_VERSION,
            "conflict_policy_version": FACT_CONFLICT_POLICY_VERSION,
            "equivalence_policy_version": EQUIVALENCE_POLICY_VERSION,
        }
        return DependencySnapshot(**body, dependency_snapshot_hash=content_hash(body))

    def route(self, request: RequestEnvelope) -> RouteDecision:
        validate_request(request)
        dependencies = self.dependencies()
        structured = {
            RequestSourceKind.STRUCTURED_FACT,
            RequestSourceKind.STRUCTURED_SKILL,
            RequestSourceKind.STRUCTURED_TOOL,
        }
        if request.source_kind in structured:
            return self._structured(request, dependencies)
        if request.source_kind == RequestSourceKind.ASSISTIVE_TEXT:
            return self._assistive(request, dependencies)
        return self._controlled(request, dependencies)

    def _structured(
        self, request: RequestEnvelope, dependencies: DependencySnapshot
    ) -> RouteDecision:
        payload = request.structured_payload or {}
        authority = RouteAuthority.EXACT_STRUCTURED
        try:
            if request.source_kind == RequestSourceKind.STRUCTURED_FACT:
                if self.fact_memory is None:
                    raise ValueError("FactMemory is unavailable")
                _validate_structured_fact_payload(payload)
                query = self._fact_query(payload, request)
                target = RouteTarget.FACT_QUERY
                evidence = {"parser": "structured_fact", "fact_query": asdict(query)}
                action = NextAction.ANSWER_FACT
            elif request.source_kind == RequestSourceKind.STRUCTURED_SKILL:
                if self.skill_router is None:
                    raise ValueError("SkillRegistry is unavailable")
                specification = specification_from_dict(payload)
                scope = EquivalenceScope(
                    request.requested_equivalence_scope
                    or EquivalenceScope.FULL_EXECUTION_TRACE
                )
                query, result = self.skill_router.search_structured(
                    specification, equivalence_scope=scope
                )
                if (
                    result.status != SearchStatus.EXACT_MATCH
                    or len(result.candidates) != 1
                ):
                    raise ValueError("structured skill has no unique exact match")
                target = RouteTarget.SKILL_REQUEST
                evidence = {
                    "parser": "structured_skill",
                    "specification": asdict(specification),
                    "skill_query": asdict(query),
                    "skill_result": asdict(result),
                    "selected_skill_id": result.candidates[0].skill_id,
                }
                action = NextAction.CONFIRM_SKILL
            else:
                tool_id = str(payload.get("tool_id", ""))
                arguments = payload.get("arguments")
                if not isinstance(arguments, dict):
                    raise ValueError("structured tool arguments must be an object")
                descriptor = self.tool_registry.descriptor(tool_id)
                validation = self.tool_registry.validate_and_canonicalize_arguments(
                    tool_id, arguments
                )
                if (
                    validation.argument_hash is None
                    or validation.canonical_arguments is None
                ):
                    raise ValueError("; ".join(validation.issues))
                target = RouteTarget.TOOL_REQUEST
                evidence = {
                    "parser": "structured_tool",
                    "tool_id": tool_id,
                    "tool_version": descriptor.version,
                    "arguments": validation.canonical_arguments,
                    "argument_hash": validation.argument_hash,
                    "tool_implementation_manifest_hash": descriptor.implementation_manifest_hash,
                }
                action = NextAction.CONFIRM_TOOL
        except (ValueError, KeyError, TypeError) as error:
            return make_decision(
                request,
                target=RouteTarget.UNSUPPORTED,
                status=RouteStatus.INVALID_REQUEST,
                authority=authority,
                exact_match=False,
                candidates=(),
                parser_evidence={"parser": request.source_kind, "error": str(error)},
                ambiguity_fields=(),
                next_action=NextAction.NO_ACTION,
                dependencies=dependencies,
            )
        return make_decision(
            request,
            target=target,
            status=RouteStatus.EXACT_ROUTE,
            authority=authority,
            exact_match=True,
            candidates=(target,),
            parser_evidence=evidence,
            ambiguity_fields=(),
            next_action=action,
            dependencies=dependencies,
        )

    def _controlled(
        self, request: RequestEnvelope, dependencies: DependencySnapshot
    ) -> RouteDecision:
        text = request.original_input
        language = request.language or "en"
        if looks_composite(text):
            return make_decision(
                request,
                target=RouteTarget.COMPOSITE_REQUIRED,
                status=RouteStatus.COMPOSITE_ROUTE,
                authority=RouteAuthority.EXACT_CONTROLLED,
                exact_match=False,
                candidates=(),
                parser_evidence={"policy": "no_hidden_multi_intent"},
                ambiguity_fields=("multi_intent",),
                next_action=NextAction.SPLIT_REQUEST_MANUALLY,
                dependencies=dependencies,
            )
        outcomes = tuple(
            item
            for item in (
                parse_fact(text, language, self.fact_memory),
                parse_skill(text, language, self.skill_router),
                parse_tool(text, language),
            )
            if item is not None
        )
        complete = tuple(item for item in outcomes if item.complete)
        if len(complete) == 1:
            item = complete[0]
            if item.target == RouteTarget.TOOL_REQUEST:
                tool_id = str(item.payload.get("tool_id", ""))
                validation = self.tool_registry.validate_and_canonicalize_arguments(
                    tool_id, item.payload.get("arguments")
                )
                if (
                    validation.argument_hash is None
                    or validation.canonical_arguments is None
                ):
                    return make_decision(
                        request,
                        target=RouteTarget.UNSUPPORTED,
                        status=RouteStatus.INVALID_REQUEST,
                        authority=RouteAuthority.EXACT_CONTROLLED,
                        exact_match=False,
                        candidates=(),
                        parser_evidence={**item.evidence, "issues": validation.issues},
                        ambiguity_fields=(),
                        next_action=NextAction.NO_ACTION,
                        dependencies=dependencies,
                    )
                descriptor = self.tool_registry.descriptor(tool_id)
                payload = {
                    "tool_id": tool_id,
                    "arguments": validation.canonical_arguments,
                    "argument_hash": validation.argument_hash,
                    "tool_implementation_manifest_hash": descriptor.implementation_manifest_hash,
                }
            else:
                payload = item.payload
            action = {
                RouteTarget.FACT_QUERY: NextAction.ANSWER_FACT,
                RouteTarget.SKILL_REQUEST: NextAction.CONFIRM_SKILL,
                RouteTarget.TOOL_REQUEST: NextAction.CONFIRM_TOOL,
            }[item.target]
            return make_decision(
                request,
                target=item.target,
                status=RouteStatus.EXACT_ROUTE,
                authority=RouteAuthority.EXACT_CONTROLLED,
                exact_match=True,
                candidates=(item.target,),
                parser_evidence={**item.evidence, "payload": payload},
                ambiguity_fields=(),
                next_action=action,
                dependencies=dependencies,
            )
        if len(complete) > 1:
            targets = tuple(sorted({item.target for item in complete}, key=str))
            return make_decision(
                request,
                target=RouteTarget.CLARIFICATION,
                status=RouteStatus.AMBIGUOUS_ROUTE,
                authority=RouteAuthority.EXACT_CONTROLLED,
                exact_match=False,
                candidates=targets,
                parser_evidence={"parsers": tuple(item.evidence for item in complete)},
                ambiguity_fields=("route_target",),
                next_action=NextAction.ASK_CLARIFICATION,
                dependencies=dependencies,
            )
        missing = tuple(item for item in outcomes if item.missing_field)
        unknown_predicate = any(
            item.ambiguity == "UNKNOWN_FACT_PREDICATE" for item in missing
        )
        if len(missing) == 1 and not unknown_predicate:
            item = missing[0]
            return make_decision(
                request,
                target=RouteTarget.CLARIFICATION,
                status=RouteStatus.AMBIGUOUS_ROUTE,
                authority=RouteAuthority.EXACT_CONTROLLED,
                exact_match=False,
                candidates=(item.target,),
                parser_evidence={**item.evidence, "ambiguity": item.ambiguity},
                ambiguity_fields=(str(item.missing_field),),
                next_action=NextAction.ASK_CLARIFICATION,
                dependencies=dependencies,
            )
        return make_decision(
            request,
            target=RouteTarget.UNSUPPORTED,
            status=RouteStatus.UNSUPPORTED_ROUTE,
            authority=RouteAuthority.EXACT_CONTROLLED,
            exact_match=False,
            candidates=(),
            parser_evidence={"parsers_attempted": ("fact", "skill", "tool")},
            ambiguity_fields=(),
            next_action=NextAction.NO_ACTION,
            dependencies=dependencies,
        )

    def _assistive(
        self, request: RequestEnvelope, dependencies: DependencySnapshot
    ) -> RouteDecision:
        text = request.original_input.casefold()
        scores = {
            RouteTarget.FACT_QUERY: sum(
                word in text
                for word in ("what", "stored", "recorded", "каков", "сохран")
            ),
            RouteTarget.SKILL_REQUEST: sum(
                word in text
                for word in ("move", "drop", "execute", "перемест", "выполн")
            ),
            RouteTarget.TOOL_REQUEST: sum(
                word in text
                for word in ("calculate", "days between", "вычисл", "дней между")
            ),
            RouteTarget.COMPOSITE_REQUIRED: int(
                looks_composite(request.original_input)
            ),
        }
        candidates = tuple(
            target
            for target, score in sorted(
                scores.items(), key=lambda item: (-item[1], str(item[0]))
            )
            if score > 0
        )
        return make_decision(
            request,
            target=(candidates[0] if candidates else RouteTarget.UNSUPPORTED),
            status=RouteStatus.ASSISTIVE_CANDIDATES,
            authority=RouteAuthority.ASSISTIVE_PROPOSAL,
            exact_match=False,
            candidates=candidates,
            parser_evidence={
                "baseline": "deterministic_keyword",
                "scores": {str(key): value for key, value in scores.items()},
            },
            ambiguity_fields=(),
            next_action=(
                NextAction.REVIEW_ROUTE if candidates else NextAction.ASK_CLARIFICATION
            ),
            dependencies=dependencies,
        )

    def _fact_query(
        self, payload: dict[str, Any], request: RequestEnvelope
    ) -> FactQuery:
        row = dict(payload)
        if row.get("object_filter") is not None and isinstance(
            row["object_filter"], dict
        ):
            row["object_filter"] = FactValue.from_dict(row["object_filter"])
        row["qualifier_filters"] = {
            key: FactValue.from_dict(value) if isinstance(value, dict) else value
            for key, value in row.get("qualifier_filters", {}).items()
        }
        if row.get("accepted_statuses") is not None:
            row["accepted_statuses"] = tuple(
                ClaimStatus(item) for item in row["accepted_statuses"]
            )
        row.setdefault("valid_at_value", request.requested_valid_at)
        row.setdefault("known_at", request.requested_known_at)
        row.setdefault("language", request.language or "en")
        return self.fact_memory.make_query(**row)


def _validate_structured_fact_payload(payload: dict[str, Any]) -> None:
    allowed = {
        "subject",
        "predicate_id",
        "object_filter",
        "qualifier_filters",
        "valid_at_value",
        "known_at",
        "accepted_statuses",
        "include_conflicts",
        "include_retracted",
        "include_evidence",
        "language",
        "memory_snapshot",
    }
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError("structured fact payload has unknown fields")
    if not isinstance(payload.get("subject"), str) or not payload["subject"].strip():
        raise TypeError("structured fact subject must be a non-empty string")
    predicate = payload.get("predicate_id")
    if predicate is not None and not isinstance(predicate, str):
        raise TypeError("structured fact predicate_id must be a string or null")
    for name in ("include_conflicts", "include_retracted", "include_evidence"):
        if name in payload and not isinstance(payload[name], bool):
            raise TypeError(f"structured fact {name} must be bool")
    if "qualifier_filters" in payload and not isinstance(
        payload["qualifier_filters"], dict
    ):
        raise TypeError("structured fact qualifier_filters must be an object")
    if (
        "object_filter" in payload
        and payload["object_filter"] is not None
        and not isinstance(payload["object_filter"], dict)
    ):
        raise TypeError("structured fact object_filter must be a FactValue object")
    statuses = payload.get("accepted_statuses")
    if statuses is not None and (
        not isinstance(statuses, list)
        or any(not isinstance(item, str) for item in statuses)
    ):
        raise TypeError("structured fact accepted_statuses must be a string array")
