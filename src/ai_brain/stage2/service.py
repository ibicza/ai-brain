"""Audited Stage-2 routing, explicit selection, and frozen Stage-1 dispatch."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from ai_brain.rules.memory import (
    RuleMemory,
    RuleMemoryIntegrityError,
    RuleMemoryIOError,
    RuleMemoryRecoveryError,
)
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.audit import AuditLog
from ai_brain.stage1.execution import BoundedExecutionError
from ai_brain.stage1.models import (
    ExecutionLimits,
    InstalledRuleReceipt,
    RuleProposal,
    content_hash,
    utc_now,
)
from ai_brain.stage1.service import Stage1Service
from ai_brain.stage1.version import STAGE1_VERSION
from ai_brain.stage2.models import (
    ConfirmationDecision,
    EquivalenceScope,
    QuerySourceKind,
    RetrievalMode,
    SearchStatus,
    SkillDispatchReceipt,
    SkillQuery,
    SkillSearchResult,
    SkillSelectionReceipt,
)
from ai_brain.stage2.registry import SkillRegistry, SkillRegistryStaleError
from ai_brain.stage2.retrieval import (
    assistive_query,
    candidate_list_hash,
    controlled_query,
    retrieve_assistive,
    retrieve_controlled,
    retrieve_final_state_effect,
    retrieve_structured,
    structured_query,
    validate_search_result,
)
from ai_brain.stage2.semantics import (
    build_final_state_equivalence_groups,
    final_state_effect_hash,
)
from ai_brain.stage2.version import STAGE2_SCHEMA_VERSION, ensure_stage1_compatible


class SkillDispatchError(RuntimeError):
    pass


class ConfirmationRequiredError(SkillDispatchError):
    pass


class Stage2Router:
    def __init__(
        self,
        *,
        registry: SkillRegistry,
        memory_path: Path,
        stage1_audit_path: Path,
        stage2_audit_path: Path,
    ) -> None:
        ensure_stage1_compatible()
        self.registry = registry
        self.memory_path = memory_path
        self.stage1 = Stage1Service(
            memory_path=memory_path,
            audit_path=stage1_audit_path,
        )
        self.audit = AuditLog(stage2_audit_path)
        self._issued_query_ids: set[str] = set()

    def search_structured(
        self,
        specification: ProgramSpecification,
        *,
        equivalence_scope: EquivalenceScope = EquivalenceScope.FULL_EXECUTION_TRACE,
        query_id_factory=None,
    ) -> tuple[SkillQuery, SkillSearchResult]:
        query = structured_query(
            specification,
            equivalence_scope=equivalence_scope,
            query_id_factory=query_id_factory,
        )
        return query, self._search(query)

    def search_final_state_effect(
        self,
        specification: ProgramSpecification,
        *,
        equivalence_scope: EquivalenceScope = EquivalenceScope.FULL_EXECUTION_TRACE,
        query_id_factory=None,
    ) -> tuple[SkillQuery, SkillSearchResult]:
        query = structured_query(
            specification,
            equivalence_scope=equivalence_scope,
            query_id_factory=query_id_factory,
        )
        return query, self._search(query, final_state_effect=True)

    search_semantic_signature = search_final_state_effect

    def search_controlled(
        self, text: str, language: str, *, query_id_factory=None
    ) -> tuple[SkillQuery, SkillSearchResult]:
        query = controlled_query(text, language, query_id_factory=query_id_factory)
        return query, self._search(query)

    def search_assistive(
        self,
        text: str,
        language: str | None = None,
        *,
        mode: RetrievalMode = RetrievalMode.BM25,
        top_k: int = 5,
        query_id_factory=None,
    ) -> tuple[SkillQuery, SkillSearchResult]:
        query = assistive_query(text, language, query_id_factory=query_id_factory)
        return query, self._search(query, mode=mode, top_k=top_k)

    def prepare_selection(
        self,
        query: SkillQuery,
        result: SkillSearchResult,
        selected_skill_id: str,
    ) -> SkillSelectionReceipt:
        self._validate_query_result(query, result)
        if result.status not in {
            SearchStatus.EXACT_MATCH,
            SearchStatus.FINAL_STATE_EQUIVALENT,
            SearchStatus.CANDIDATES,
        }:
            raise SkillDispatchError(f"Cannot select from {result.status}")
        candidates = {item.skill_id: item for item in result.candidates}
        if selected_skill_id not in candidates:
            raise SkillDispatchError("Selected skill is absent from candidate list")
        candidate = candidates[selected_skill_id]
        if result.exact_match and candidate.rank != 1:
            raise SkillDispatchError("Exact selection must use the exact candidate")
        evidence = dict(candidate.evidence)
        structural_difference = bool(evidence.get("structural_identity_differs", False))
        if result.status == SearchStatus.EXACT_MATCH:
            if (
                result.requested_specification_hash is not None
                and candidate.specification_hash != result.requested_specification_hash
            ):
                raise SkillDispatchError(
                    "Exact candidate is not structurally identical"
                )
            structural_difference = False
        if result.status == SearchStatus.FINAL_STATE_EQUIVALENT:
            if result.exact_match or not structural_difference:
                raise SkillDispatchError("Equivalent candidate evidence is incomplete")
            required = {
                "equivalence_class_hash",
                "final_state_effect_hash",
                "warning",
            }
            if not required <= evidence.keys():
                raise SkillDispatchError("Equivalent candidate lacks review evidence")
        skill = self.registry.records[candidate.skill_id]
        receipt = SkillSelectionReceipt(
            query_id=query.query_id,
            query_hash=content_hash(query),
            registry_hash=self.registry.manifest.registry_hash,
            registry_version=self.registry.manifest.registry_version,
            rule_memory_hash=self.registry.manifest.rule_memory_hash,
            selected_skill_id=candidate.skill_id,
            rule_id=candidate.rule_id,
            rule_semantic_hash=candidate.rule_semantic_hash,
            requested_specification_hash=result.requested_specification_hash,
            selected_specification_hash=candidate.specification_hash,
            final_state_effect_hash=skill.final_state_effect_hash,
            equivalence_class_hash=(
                str(evidence["equivalence_class_hash"])
                if result.status == SearchStatus.FINAL_STATE_EQUIVALENT
                else None
            ),
            equivalence_scope=result.equivalence_scope,
            search_status=result.status,
            structural_identity_differs=structural_difference,
            full_trace_equivalent=not structural_difference,
            retrieval_mode=result.retrieval_mode,
            retrieval_evidence=evidence,
            candidate_list_hash=candidate_list_hash(result),
            confirmation_decision=ConfirmationDecision.PENDING,
            confirmer_identity="",
            confirmer_identity_type="",
            created_at=utc_now(),
            stage1_version=STAGE1_VERSION,
            stage2_schema_version=STAGE2_SCHEMA_VERSION,
            receipt_hash="0" * 64,
        )
        receipt = replace(receipt, receipt_hash=_selection_hash(receipt))
        equivalent = result.status == SearchStatus.FINAL_STATE_EQUIVALENT
        self.audit.append(
            "EQUIVALENT_SELECTION_REVIEWED" if equivalent else "SKILL_SELECTED",
            {
                "query_hash": receipt.query_hash,
                "registry_hash": receipt.registry_hash,
                "rule_semantic_hash": receipt.rule_semantic_hash,
                "requested_specification_hash": receipt.requested_specification_hash,
                "selected_specification_hash": receipt.selected_specification_hash,
                "final_state_effect_hash": receipt.final_state_effect_hash,
                "equivalence_class_hash": receipt.equivalence_class_hash,
                "equivalence_scope": str(receipt.equivalence_scope),
                "selection_receipt_hash": receipt.receipt_hash,
                "retrieval_mode": str(receipt.retrieval_mode),
            },
            query.query_id,
        )
        return receipt

    def confirm_selection(
        self,
        receipt: SkillSelectionReceipt,
        *,
        identity: str,
        identity_type: str = "USER",
        decision: ConfirmationDecision = ConfirmationDecision.CONFIRM_SELECTION,
    ) -> SkillSelectionReceipt:
        validate_selection_receipt(receipt)
        if not identity.strip():
            raise ValueError("Confirmer identity is required")
        if identity_type not in {"USER", "TRUSTED_SUPERVISOR"}:
            raise ValueError("Invalid confirmer identity type")
        actual_decision = ConfirmationDecision(decision)
        if receipt.search_status == SearchStatus.FINAL_STATE_EQUIVALENT:
            if (
                actual_decision
                != ConfirmationDecision.CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION
            ):
                raise ConfirmationRequiredError(
                    "Final-state substitution requires special confirmation"
                )
        elif (
            actual_decision
            == ConfirmationDecision.CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION
        ):
            raise SkillDispatchError(
                "Equivalent-selection confirmation requires equivalent evidence"
            )
        confirmed = replace(
            receipt,
            confirmation_decision=actual_decision,
            confirmer_identity=identity,
            confirmer_identity_type=identity_type,
            created_at=utc_now(),
            receipt_hash="0" * 64,
        )
        confirmed = replace(confirmed, receipt_hash=_selection_hash(confirmed))
        equivalent = receipt.search_status == SearchStatus.FINAL_STATE_EQUIVALENT
        self.audit.append(
            (
                "EQUIVALENT_SELECTION_CONFIRMED"
                if equivalent
                else "SKILL_SELECTION_CONFIRMED"
            ),
            {
                "query_hash": confirmed.query_hash,
                "selection_receipt_hash": confirmed.receipt_hash,
                "decision": str(confirmed.confirmation_decision),
                "identity_type": identity_type,
                "requested_specification_hash": (
                    confirmed.requested_specification_hash
                ),
                "selected_specification_hash": confirmed.selected_specification_hash,
                "final_state_effect_hash": confirmed.final_state_effect_hash,
                "equivalence_class_hash": confirmed.equivalence_class_hash,
                "equivalence_scope": str(confirmed.equivalence_scope),
            },
            confirmed.query_id,
        )
        return confirmed

    def dispatch(
        self,
        *,
        query: SkillQuery,
        result: SkillSearchResult,
        selection: SkillSelectionReceipt,
        proposal: RuleProposal,
        installed_receipt: InstalledRuleReceipt,
        initial_state: dict[str, int],
        limits: ExecutionLimits | None = None,
    ) -> tuple[RuleProposal, Any, SkillDispatchReceipt]:
        actual_limits = limits or ExecutionLimits()
        try:
            self._validate_dispatch(
                query, result, selection, proposal, installed_receipt
            )
            executed, execution = self.stage1.execute(
                proposal,
                installed_receipt,
                selection.rule_id,
                initial_state,
                limits=actual_limits,
            )
        except (
            SkillDispatchError,
            SkillRegistryStaleError,
            BoundedExecutionError,
            RuleMemoryIntegrityError,
            RuleMemoryRecoveryError,
            RuleMemoryIOError,
            ValueError,
        ) as exc:
            equivalent = selection.search_status == SearchStatus.FINAL_STATE_EQUIVALENT
            self.audit.append(
                (
                    "EQUIVALENT_SKILL_DISPATCH_FAILED"
                    if equivalent
                    else "SKILL_DISPATCH_FAILED"
                ),
                {
                    "query_hash": content_hash(query),
                    "registry_hash": self.registry.manifest.registry_hash,
                    "rule_id_hash": content_hash(selection.rule_id),
                    "selection_receipt_hash": selection.receipt_hash,
                    "initial_state_hash": content_hash(initial_state),
                    "failure_type": type(exc).__name__,
                    "stage1_version": STAGE1_VERSION,
                    "requested_specification_hash": (
                        selection.requested_specification_hash
                    ),
                    "selected_specification_hash": (
                        selection.selected_specification_hash
                    ),
                    "final_state_effect_hash": selection.final_state_effect_hash,
                    "equivalence_class_hash": selection.equivalence_class_hash,
                    "equivalence_scope": str(selection.equivalence_scope),
                    "confirmation_decision": str(selection.confirmation_decision),
                },
                query.query_id,
            )
            raise
        dispatch = SkillDispatchReceipt(
            selection_receipt_hash=selection.receipt_hash,
            skill_id=selection.selected_skill_id,
            rule_id=selection.rule_id,
            installed_receipt_hash=content_hash(installed_receipt),
            rule_semantic_hash=selection.rule_semantic_hash,
            requested_specification_hash=selection.requested_specification_hash,
            selected_specification_hash=selection.selected_specification_hash,
            final_state_effect_hash=selection.final_state_effect_hash,
            equivalence_class_hash=selection.equivalence_class_hash,
            equivalence_scope=selection.equivalence_scope,
            search_status=selection.search_status,
            confirmation_decision=selection.confirmation_decision,
            structural_identity_differs=selection.structural_identity_differs,
            full_trace_equivalent=selection.full_trace_equivalent,
            initial_state_hash=content_hash(initial_state),
            execution_limits=actual_limits,
            dispatch_policy=(
                "FINAL_STATE_EQUIVALENT_EXPLICIT_REVIEW"
                if selection.search_status == SearchStatus.FINAL_STATE_EQUIVALENT
                else "EXPLICIT_CONFIRMATION_REQUIRED"
            ),
            stage1_execution_hash=execution.execution_hash,
            created_at=utc_now(),
            dispatch_hash="0" * 64,
        )
        dispatch = replace(dispatch, dispatch_hash=_dispatch_hash(dispatch))
        equivalent = selection.search_status == SearchStatus.FINAL_STATE_EQUIVALENT
        self.audit.append(
            "EQUIVALENT_SKILL_DISPATCHED" if equivalent else "SKILL_DISPATCHED",
            {
                "query_hash": content_hash(query),
                "registry_hash": self.registry.manifest.registry_hash,
                "rule_semantic_hash": selection.rule_semantic_hash,
                "selection_receipt_hash": selection.receipt_hash,
                "dispatch_receipt_hash": dispatch.dispatch_hash,
                "stage1_execution_hash": execution.execution_hash,
                "requested_specification_hash": (
                    selection.requested_specification_hash
                ),
                "selected_specification_hash": selection.selected_specification_hash,
                "final_state_effect_hash": selection.final_state_effect_hash,
                "equivalence_class_hash": selection.equivalence_class_hash,
                "equivalence_scope": str(selection.equivalence_scope),
                "confirmation_decision": str(selection.confirmation_decision),
                "structural_identity_differs": (selection.structural_identity_differs),
                "full_trace_equivalent": selection.full_trace_equivalent,
            },
            query.query_id,
        )
        return executed, execution, dispatch

    def _search(
        self,
        query: SkillQuery,
        *,
        mode: RetrievalMode = RetrievalMode.BM25,
        top_k: int = 5,
        final_state_effect: bool = False,
    ) -> SkillSearchResult:
        if query.query_id in self._issued_query_ids:
            raise ValueError("Duplicate query ID")
        existing = {
            event.proposal_id
            for event in self.audit.replay()
            if event.proposal_id is not None
        }
        if query.query_id in existing:
            raise ValueError("Query ID already exists in audit")
        self._issued_query_ids.add(query.query_id)
        self.audit.append(
            "SKILL_QUERY_RECEIVED",
            {
                "query_hash": content_hash(query),
                "original_input_hash": query.original_input_hash,
                "source_kind": str(query.source_kind),
                "equivalence_scope": str(query.equivalence_scope),
                "stage1_version": STAGE1_VERSION,
            },
            query.query_id,
        )
        memory = RuleMemory.load_with_backup(self.memory_path)
        if query.source_kind == QuerySourceKind.STRUCTURED_SPEC:
            result = (
                retrieve_final_state_effect(query, self.registry, memory)
                if final_state_effect
                else retrieve_structured(query, self.registry, memory)
            )
        elif query.source_kind == QuerySourceKind.CONTROLLED_LANGUAGE:
            result = retrieve_controlled(query, self.registry, memory)
        else:
            result = retrieve_assistive(
                query, self.registry, memory, mode=mode, top_k=top_k
            )
        event_type = {
            SearchStatus.FINAL_STATE_EQUIVALENT: "FINAL_STATE_EQUIVALENT_FOUND",
            SearchStatus.AMBIGUOUS: "SKILL_AMBIGUOUS",
            SearchStatus.NO_MATCH: "SKILL_UNKNOWN",
            SearchStatus.UNSUPPORTED: "SKILL_UNKNOWN",
        }.get(result.status, "SKILL_SEARCH_COMPLETED")
        payload = {
            "query_hash": result.query_hash,
            "registry_hash": result.registry_hash,
            "rule_memory_hash": result.rule_memory_hash,
            "retrieval_mode": str(result.retrieval_mode),
            "status": str(result.status),
            "candidate_list_hash": candidate_list_hash(result),
            "result_hash": result.result_hash,
            "requested_specification_hash": result.requested_specification_hash,
            "equivalence_scope": str(result.equivalence_scope),
        }
        if result.status == SearchStatus.FINAL_STATE_EQUIVALENT:
            evidence = result.candidates[0].evidence
            payload.update(
                {
                    "selected_specification_hash": evidence[
                        "selected_specification_hash"
                    ],
                    "final_state_effect_hash": evidence["final_state_effect_hash"],
                    "equivalence_class_hash": evidence["equivalence_class_hash"],
                    "structural_identity_differs": True,
                    "full_trace_equivalent": False,
                }
            )
        self.audit.append(event_type, payload, query.query_id)
        return result

    def _validate_query_result(
        self, query: SkillQuery, result: SkillSearchResult
    ) -> None:
        validate_search_result(result)
        if result.query_id != query.query_id or result.query_hash != content_hash(
            query
        ):
            raise SkillDispatchError("Search result belongs to another query")
        if result.registry_hash != self.registry.manifest.registry_hash:
            raise SkillDispatchError("Search result registry hash is stale")
        if result.equivalence_scope != query.equivalence_scope:
            raise SkillDispatchError("Search result equivalence scope changed")
        if query.specification is not None:
            from ai_brain.stage1.models import specification_hash

            if result.requested_specification_hash != specification_hash(
                query.specification
            ):
                raise SkillDispatchError("Requested structural hash changed")

    def _validate_dispatch(
        self,
        query: SkillQuery,
        result: SkillSearchResult,
        selection: SkillSelectionReceipt,
        proposal: RuleProposal,
        installed_receipt: InstalledRuleReceipt,
    ) -> None:
        self._validate_query_result(query, result)
        validate_selection_receipt(selection)
        equivalent = result.status == SearchStatus.FINAL_STATE_EQUIVALENT
        required_decision = (
            ConfirmationDecision.CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION
            if equivalent
            else ConfirmationDecision.CONFIRM_SELECTION
        )
        if selection.confirmation_decision != required_decision:
            raise ConfirmationRequiredError("Required selection confirmation is absent")
        if selection.query_id != query.query_id or selection.query_hash != content_hash(
            query
        ):
            raise SkillDispatchError("Selection receipt replayed against another query")
        if selection.candidate_list_hash != candidate_list_hash(result):
            raise SkillDispatchError("Candidate list changed after selection")
        if selection.equivalence_scope != query.equivalence_scope:
            raise SkillDispatchError("Selection equivalence scope changed")
        if selection.search_status != result.status:
            raise SkillDispatchError("Selection search status changed")
        if (
            selection.requested_specification_hash
            != result.requested_specification_hash
        ):
            raise SkillDispatchError("Requested structural hash changed")
        memory = RuleMemory.load_with_backup(self.memory_path)
        self.registry.validate_against_rule_memory(memory)
        if selection.registry_hash != self.registry.manifest.registry_hash:
            raise SkillDispatchError("Registry changed after selection")
        if selection.rule_memory_hash != self.registry.manifest.rule_memory_hash:
            raise SkillDispatchError("RuleMemory changed after selection")
        skill = self.registry.records.get(selection.selected_skill_id)
        if skill is None or not skill.active or skill.deprecated:
            raise SkillDispatchError("Selected skill is inactive or absent")
        expected = {
            "rule_id": skill.rule_id,
            "rule_semantic_hash": skill.rule_semantic_hash,
            "selected_specification_hash": skill.specification_hash,
            "final_state_effect_hash": skill.final_state_effect_hash,
        }
        if any(getattr(selection, name) != value for name, value in expected.items()):
            raise SkillDispatchError("Selection does not match current SkillRecord")
        candidate_ids = {item.skill_id for item in result.candidates}
        if selection.selected_skill_id not in candidate_ids:
            raise SkillDispatchError("Selected skill left the candidate set")
        selected_candidate = next(
            item
            for item in result.candidates
            if item.skill_id == selection.selected_skill_id
        )
        if selection.retrieval_evidence != selected_candidate.evidence:
            raise SkillDispatchError("Reviewed retrieval evidence changed")
        if equivalent:
            self._validate_equivalent_dispatch(query, selection, skill)
        elif (
            result.exact_match
            and selection.requested_specification_hash
            != selection.selected_specification_hash
        ):
            raise SkillDispatchError("Exact dispatch lost structural identity")
        if content_hash(installed_receipt) != skill.installed_receipt_hash:
            raise SkillDispatchError("Installed receipt does not match SkillRecord")
        if proposal.proposal_id != installed_receipt.proposal_id:
            raise SkillDispatchError("Proposal does not match installed receipt")

    def _validate_equivalent_dispatch(self, query, selection, skill) -> None:
        if query.equivalence_scope != EquivalenceScope.FINAL_STATE_ONLY:
            raise SkillDispatchError("Equivalent dispatch requires FINAL_STATE_ONLY")
        if query.specification is None:
            raise SkillDispatchError("Equivalent dispatch requires a specification")
        if not selection.structural_identity_differs or selection.full_trace_equivalent:
            raise SkillDispatchError("Structural difference was not acknowledged")
        effect_hash = final_state_effect_hash(query.specification)
        if effect_hash != selection.final_state_effect_hash:
            raise SkillDispatchError("Final-state effect changed")
        groups = [
            item
            for item in build_final_state_equivalence_groups(
                self.registry.active_records()
            )
            if item.final_state_effect_hash == effect_hash
        ]
        if len(groups) != 1:
            raise SkillDispatchError("Final-state equivalence class is unavailable")
        group = groups[0]
        if group.order_sensitive:
            raise SkillDispatchError("Order-sensitive substitution is forbidden")
        if group.equivalence_class_hash != selection.equivalence_class_hash:
            raise SkillDispatchError("Equivalence class changed")
        if skill.skill_id not in group.member_skill_ids:
            raise SkillDispatchError("Candidate left the equivalence class")


def validate_selection_receipt(receipt: SkillSelectionReceipt) -> None:
    if receipt.receipt_hash != _selection_hash(receipt):
        raise SkillDispatchError("Selection receipt hash mismatch")
    if receipt.stage1_version != STAGE1_VERSION:
        raise SkillDispatchError("Selection receipt Stage-1 version mismatch")
    if receipt.stage2_schema_version != STAGE2_SCHEMA_VERSION:
        raise SkillDispatchError("Selection receipt Stage-2 schema mismatch")
    if (
        receipt.retrieval_mode
        not in {
            RetrievalMode.EXACT_SPECIFICATION,
            RetrievalMode.FINAL_STATE_EFFECT,
            RetrievalMode.CONTROLLED_EXACT,
        }
        and receipt.search_status == SearchStatus.EXACT_MATCH
    ):
        raise SkillDispatchError("Assistive receipt cannot contain exact authority")
    if receipt.search_status == SearchStatus.EXACT_MATCH:
        if (
            receipt.requested_specification_hash is not None
            and receipt.requested_specification_hash
            != receipt.selected_specification_hash
        ):
            raise SkillDispatchError("Exact receipt is not structurally identical")
        if receipt.structural_identity_differs or not receipt.full_trace_equivalent:
            raise SkillDispatchError("Exact receipt misstates execution identity")
    if receipt.search_status == SearchStatus.FINAL_STATE_EQUIVALENT:
        if receipt.equivalence_scope != EquivalenceScope.FINAL_STATE_ONLY:
            raise SkillDispatchError("Equivalent receipt has the wrong scope")
        if not receipt.equivalence_class_hash:
            raise SkillDispatchError("Equivalent receipt lacks a class hash")
        if not receipt.structural_identity_differs or receipt.full_trace_equivalent:
            raise SkillDispatchError("Equivalent receipt hides structural difference")
        evidence = receipt.retrieval_evidence
        expected_evidence = {
            "requested_specification_hash": receipt.requested_specification_hash,
            "selected_specification_hash": receipt.selected_specification_hash,
            "final_state_effect_hash": receipt.final_state_effect_hash,
            "equivalence_class_hash": receipt.equivalence_class_hash,
            "equivalence_scope": str(receipt.equivalence_scope),
            "structural_identity_differs": True,
            "full_trace_equivalent": False,
        }
        if any(
            evidence.get(name) != value for name, value in expected_evidence.items()
        ):
            raise SkillDispatchError("Equivalent receipt evidence is inconsistent")
        if not isinstance(evidence.get("warning"), str) or not evidence["warning"]:
            raise SkillDispatchError("Equivalent receipt lacks structural warning")


def validate_dispatch_receipt(
    receipt: SkillDispatchReceipt, *, initial_state: dict[str, int] | None = None
) -> None:
    if receipt.schema_version != STAGE2_SCHEMA_VERSION:
        raise SkillDispatchError("Dispatch receipt Stage-2 schema mismatch")
    if receipt.dispatch_hash != _dispatch_hash(receipt):
        raise SkillDispatchError("Dispatch receipt hash mismatch")
    if initial_state is not None and receipt.initial_state_hash != content_hash(
        initial_state
    ):
        raise SkillDispatchError("Dispatch receipt replayed against another state")
    if receipt.search_status == SearchStatus.FINAL_STATE_EQUIVALENT and (
        receipt.equivalence_scope != EquivalenceScope.FINAL_STATE_ONLY
        or receipt.confirmation_decision
        != ConfirmationDecision.CONFIRM_FINAL_STATE_EQUIVALENT_SELECTION
        or not receipt.structural_identity_differs
        or receipt.full_trace_equivalent
        or not receipt.equivalence_class_hash
    ):
        raise SkillDispatchError("Unsafe equivalent dispatch receipt")


def _selection_hash(receipt: SkillSelectionReceipt) -> str:
    row = asdict(receipt)
    row["receipt_hash"] = "0" * 64
    return content_hash(row)


def _dispatch_hash(receipt: SkillDispatchReceipt) -> str:
    row = asdict(receipt)
    row["dispatch_hash"] = "0" * 64
    return content_hash(row)
