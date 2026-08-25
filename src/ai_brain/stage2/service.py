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
    retrieve_semantic_signature,
    retrieve_structured,
    structured_query,
    validate_search_result,
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
        self, specification: ProgramSpecification, *, query_id_factory=None
    ) -> tuple[SkillQuery, SkillSearchResult]:
        query = structured_query(specification, query_id_factory=query_id_factory)
        return query, self._search(query)

    def search_semantic_signature(
        self, specification: ProgramSpecification, *, query_id_factory=None
    ) -> tuple[SkillQuery, SkillSearchResult]:
        query = structured_query(specification, query_id_factory=query_id_factory)
        return query, self._search(query, semantic_signature=True)

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
        if result.status in {
            SearchStatus.NO_MATCH,
            SearchStatus.AMBIGUOUS,
            SearchStatus.CONTRADICTORY,
            SearchStatus.UNSUPPORTED,
            SearchStatus.STALE_REGISTRY,
            SearchStatus.INCOMPATIBLE_STAGE1,
        }:
            raise SkillDispatchError(f"Cannot select from {result.status}")
        candidates = {item.skill_id: item for item in result.candidates}
        if selected_skill_id not in candidates:
            raise SkillDispatchError("Selected skill is absent from candidate list")
        candidate = candidates[selected_skill_id]
        if result.exact_match and candidate.rank != 1:
            raise SkillDispatchError("Exact selection must use the exact candidate")
        receipt = SkillSelectionReceipt(
            query_id=query.query_id,
            query_hash=content_hash(query),
            registry_hash=self.registry.manifest.registry_hash,
            registry_version=self.registry.manifest.registry_version,
            rule_memory_hash=self.registry.manifest.rule_memory_hash,
            selected_skill_id=candidate.skill_id,
            rule_id=candidate.rule_id,
            rule_semantic_hash=candidate.rule_semantic_hash,
            specification_hash=candidate.specification_hash,
            retrieval_mode=result.retrieval_mode,
            exact_match_evidence=(
                dict(candidate.evidence) if result.exact_match else {}
            ),
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
        self.audit.append(
            "SKILL_SELECTED",
            {
                "query_hash": receipt.query_hash,
                "registry_hash": receipt.registry_hash,
                "rule_semantic_hash": receipt.rule_semantic_hash,
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
        confirmed = replace(
            receipt,
            confirmation_decision=ConfirmationDecision(decision),
            confirmer_identity=identity,
            confirmer_identity_type=identity_type,
            created_at=utc_now(),
            receipt_hash="0" * 64,
        )
        confirmed = replace(confirmed, receipt_hash=_selection_hash(confirmed))
        self.audit.append(
            "SKILL_SELECTION_CONFIRMED",
            {
                "query_hash": confirmed.query_hash,
                "selection_receipt_hash": confirmed.receipt_hash,
                "decision": str(confirmed.confirmation_decision),
                "identity_type": identity_type,
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
            self.audit.append(
                "SKILL_DISPATCH_FAILED",
                {
                    "query_hash": content_hash(query),
                    "registry_hash": self.registry.manifest.registry_hash,
                    "rule_id_hash": content_hash(selection.rule_id),
                    "selection_receipt_hash": selection.receipt_hash,
                    "initial_state_hash": content_hash(initial_state),
                    "failure_type": type(exc).__name__,
                    "stage1_version": STAGE1_VERSION,
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
            specification_hash=selection.specification_hash,
            initial_state_hash=content_hash(initial_state),
            execution_limits=actual_limits,
            dispatch_policy="EXPLICIT_CONFIRMATION_REQUIRED",
            stage1_execution_hash=execution.execution_hash,
            created_at=utc_now(),
            dispatch_hash="0" * 64,
        )
        dispatch = replace(dispatch, dispatch_hash=_dispatch_hash(dispatch))
        self.audit.append(
            "SKILL_DISPATCHED",
            {
                "query_hash": content_hash(query),
                "registry_hash": self.registry.manifest.registry_hash,
                "rule_semantic_hash": selection.rule_semantic_hash,
                "selection_receipt_hash": selection.receipt_hash,
                "dispatch_receipt_hash": dispatch.dispatch_hash,
                "stage1_execution_hash": execution.execution_hash,
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
        semantic_signature: bool = False,
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
                "stage1_version": STAGE1_VERSION,
            },
            query.query_id,
        )
        memory = RuleMemory.load_with_backup(self.memory_path)
        if query.source_kind == QuerySourceKind.STRUCTURED_SPEC:
            result = (
                retrieve_semantic_signature(query, self.registry, memory)
                if semantic_signature
                else retrieve_structured(query, self.registry, memory)
            )
        elif query.source_kind == QuerySourceKind.CONTROLLED_LANGUAGE:
            result = retrieve_controlled(query, self.registry, memory)
        else:
            result = retrieve_assistive(
                query, self.registry, memory, mode=mode, top_k=top_k
            )
        event_type = {
            SearchStatus.AMBIGUOUS: "SKILL_AMBIGUOUS",
            SearchStatus.NO_MATCH: "SKILL_UNKNOWN",
            SearchStatus.UNSUPPORTED: "SKILL_UNKNOWN",
        }.get(result.status, "SKILL_SEARCH_COMPLETED")
        self.audit.append(
            event_type,
            {
                "query_hash": result.query_hash,
                "registry_hash": result.registry_hash,
                "rule_memory_hash": result.rule_memory_hash,
                "retrieval_mode": str(result.retrieval_mode),
                "status": str(result.status),
                "candidate_list_hash": candidate_list_hash(result),
                "result_hash": result.result_hash,
            },
            query.query_id,
        )
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
        if selection.confirmation_decision != ConfirmationDecision.CONFIRM_SELECTION:
            raise ConfirmationRequiredError("Explicit selection confirmation required")
        if selection.query_id != query.query_id or selection.query_hash != content_hash(
            query
        ):
            raise SkillDispatchError("Selection receipt replayed against another query")
        if selection.candidate_list_hash != candidate_list_hash(result):
            raise SkillDispatchError("Candidate list changed after selection")
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
            "specification_hash": skill.specification_hash,
        }
        if any(getattr(selection, name) != value for name, value in expected.items()):
            raise SkillDispatchError("Selection does not match current SkillRecord")
        if content_hash(installed_receipt) != skill.installed_receipt_hash:
            raise SkillDispatchError("Installed receipt does not match SkillRecord")
        if proposal.proposal_id != installed_receipt.proposal_id:
            raise SkillDispatchError("Proposal does not match installed receipt")


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
            RetrievalMode.EXACT_SEMANTIC,
            RetrievalMode.CONTROLLED_EXACT,
        }
        and receipt.exact_match_evidence
    ):
        raise SkillDispatchError("Assistive receipt cannot contain exact evidence")


def validate_dispatch_receipt(
    receipt: SkillDispatchReceipt, *, initial_state: dict[str, int] | None = None
) -> None:
    if receipt.dispatch_hash != _dispatch_hash(receipt):
        raise SkillDispatchError("Dispatch receipt hash mismatch")
    if initial_state is not None and receipt.initial_state_hash != content_hash(
        initial_state
    ):
        raise SkillDispatchError("Dispatch receipt replayed against another state")


def _selection_hash(receipt: SkillSelectionReceipt) -> str:
    row = asdict(receipt)
    row["receipt_hash"] = "0" * 64
    return content_hash(row)


def _dispatch_hash(receipt: SkillDispatchReceipt) -> str:
    row = asdict(receipt)
    row["dispatch_hash"] = "0" * 64
    return content_hash(row)
