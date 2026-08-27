"""Unified-router integration for exact bounded chemistry language."""

from __future__ import annotations

from ai_brain.stage2.domains.chemistry.controlled import (
    ChemistryParseKind,
    parse_chemistry,
)
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    ChemistryKnowledgeError,
    validate_fact_provenance,
)
from ai_brain.stage2.router.decisions import make_decision
from ai_brain.stage2.router.exact import ExactUnifiedRouter
from ai_brain.stage2.router.models import (
    NextAction,
    RouteAuthority,
    RouteStatus,
    RouteTarget,
)


class ChemistryUnifiedRouter(ExactUnifiedRouter):
    def _controlled(self, request, dependencies):
        assert self.fact_memory is not None
        parsed = parse_chemistry(
            request.original_input, request.language or "en", self.fact_memory
        )
        if parsed.kind == ChemistryParseKind.FACT:
            memory_snapshot = self.fact_memory.database.snapshot_hash()
            provenance_key = (
                memory_snapshot,
                parsed.payload["subject"],
                parsed.payload["predicate_id"],
            )
            provenance_cache = getattr(self, "_chemistry_provenance_cache", set())
            resolution_state = getattr(self, "_chemistry_resolution_cache", (None, {}))
            if resolution_state[0] != memory_snapshot:
                resolution_state = (memory_snapshot, {})
                self._chemistry_resolution_cache = resolution_state
            try:
                if provenance_key not in provenance_cache:
                    validate_fact_provenance(
                        self.fact_memory,
                        self.tool_registry.domain_manifest,
                        parsed.payload["subject"],
                        parsed.payload["predicate_id"],
                        resolution_cache=resolution_state[1],
                    )
                    provenance_cache.add(provenance_key)
                    self._chemistry_provenance_cache = provenance_cache
            except ChemistryKnowledgeError as error:
                return make_decision(
                    request,
                    target=RouteTarget.UNSUPPORTED,
                    status=RouteStatus.INVALID_REQUEST,
                    authority=RouteAuthority.EXACT_CONTROLLED,
                    exact_match=False,
                    candidates=(),
                    parser_evidence={
                        "parser": "chemistry_controlled_v3",
                        "issue": str(error),
                    },
                    ambiguity_fields=(),
                    next_action=NextAction.NO_ACTION,
                    dependencies=dependencies,
                )
            return make_decision(
                request,
                target=RouteTarget.FACT_QUERY,
                status=RouteStatus.EXACT_ROUTE,
                authority=RouteAuthority.EXACT_CONTROLLED,
                exact_match=True,
                candidates=(RouteTarget.FACT_QUERY,),
                parser_evidence={
                    "parser": "chemistry_controlled_v3",
                    "payload": parsed.payload,
                    **(parsed.evidence or {}),
                },
                ambiguity_fields=(),
                next_action=NextAction.ANSWER_FACT,
                dependencies=dependencies,
            )
        if parsed.kind == ChemistryParseKind.TOOL:
            tool_id = parsed.payload["tool_id"]
            validation = self.tool_registry.validate_and_canonicalize_arguments(
                tool_id, parsed.payload["arguments"]
            )
            if validation.canonical_arguments is None:
                return make_decision(
                    request,
                    target=RouteTarget.UNSUPPORTED,
                    status=RouteStatus.INVALID_REQUEST,
                    authority=RouteAuthority.EXACT_CONTROLLED,
                    exact_match=False,
                    candidates=(),
                    parser_evidence={
                        "parser": "chemistry_controlled_v2",
                        "issues": validation.issues,
                    },
                    ambiguity_fields=(),
                    next_action=NextAction.NO_ACTION,
                    dependencies=dependencies,
                )
            payload = {
                "tool_id": tool_id,
                "arguments": validation.canonical_arguments,
                "argument_hash": validation.argument_hash,
                "tool_implementation_manifest_hash": self.tool_registry.descriptor(
                    tool_id
                ).implementation_manifest_hash,
            }
            return make_decision(
                request,
                target=RouteTarget.TOOL_REQUEST,
                status=RouteStatus.EXACT_ROUTE,
                authority=RouteAuthority.EXACT_CONTROLLED,
                exact_match=True,
                candidates=(RouteTarget.TOOL_REQUEST,),
                parser_evidence={
                    "parser": "chemistry_controlled_v2",
                    "payload": payload,
                    **(parsed.evidence or {}),
                },
                ambiguity_fields=(),
                next_action=NextAction.CONFIRM_TOOL,
                dependencies=dependencies,
            )
        if parsed.kind == ChemistryParseKind.CLARIFICATION:
            return make_decision(
                request,
                target=RouteTarget.CLARIFICATION,
                status=RouteStatus.AMBIGUOUS_ROUTE,
                authority=RouteAuthority.EXACT_CONTROLLED,
                exact_match=False,
                candidates=(RouteTarget.TOOL_REQUEST,),
                parser_evidence={
                    "parser": "chemistry_controlled_v2",
                    "ambiguity": "MISSING_TOOL_ARGUMENT",
                },
                ambiguity_fields=parsed.missing_fields,
                next_action=NextAction.ASK_CLARIFICATION,
                dependencies=dependencies,
            )
        if parsed.kind == ChemistryParseKind.COMPOSITE:
            return make_decision(
                request,
                target=RouteTarget.COMPOSITE_REQUIRED,
                status=RouteStatus.COMPOSITE_ROUTE,
                authority=RouteAuthority.EXACT_CONTROLLED,
                exact_match=False,
                candidates=(),
                parser_evidence={
                    "parser": "chemistry_controlled_v2",
                    **(parsed.evidence or {}),
                },
                ambiguity_fields=("multi_intent",),
                next_action=NextAction.SPLIT_REQUEST_MANUALLY,
                dependencies=dependencies,
            )
        return make_decision(
            request,
            target=RouteTarget.UNSUPPORTED,
            status=RouteStatus.UNSUPPORTED_ROUTE,
            authority=RouteAuthority.EXACT_CONTROLLED,
            exact_match=False,
            candidates=(),
            parser_evidence={
                "parser": "chemistry_controlled_v2",
                **(parsed.evidence or {}),
            },
            ambiguity_fields=(),
            next_action=NextAction.NO_ACTION,
            dependencies=dependencies,
        )
