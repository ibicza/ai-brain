"""High-level trusted FactMemory workflow and exact query engine."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    intervals_overlap,
    normalize_datetime,
    normalize_label,
    normalize_temporal,
    temporal_key,
    utc_now,
    valid_at,
    validate_interval,
)
from ai_brain.stage2.facts.models import (
    ApprovalDecision,
    ApprovalStatus,
    Cardinality,
    ClaimAnswer,
    ClaimRecord,
    ClaimStatus,
    ConflictGroup,
    ConflictResolutionStatus,
    EntityRecord,
    EntityResolution,
    EntityResolutionStatus,
    EntityStatus,
    EvidenceLocationKind,
    EvidenceRecord,
    EvidenceRelation,
    ExtractionMethod,
    FactAnswerBundle,
    FactApprovalEnvelope,
    FactProposal,
    FactQuery,
    PredicateDefinition,
    ProposalSource,
    ProposalStatus,
    QueryStatus,
    ReplayStatus,
    SourceKind,
    SourceRecord,
    SourceStatus,
    TemporalMode,
)
from ai_brain.stage2.facts.persistence import FactDatabase, FactMemoryIntegrityError
from ai_brain.stage2.facts.sources import SourceIntegrityError, extract_evidence
from ai_brain.stage2.facts.values import FactValue, FactValueKind
from ai_brain.stage2.facts.version import (
    FACT_APPROVAL_POLICY_VERSION,
    FACT_MEMORY_SCHEMA_VERSION,
    FACT_RENDERING_VERSION,
)

_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_WORKFLOW_NEXT = {
    ProposalStatus.RECEIVED: ProposalStatus.PARSED,
    ProposalStatus.PARSED: ProposalStatus.EVIDENCE_ATTACHED,
    ProposalStatus.EVIDENCE_ATTACHED: ProposalStatus.VALIDATED,
    ProposalStatus.VALIDATED: ProposalStatus.REVIEWED,
    ProposalStatus.REVIEWED: ProposalStatus.APPROVED,
    ProposalStatus.APPROVED: ProposalStatus.COMMITTED,
}
_TERMINAL_PROPOSAL_STATUSES = {
    ProposalStatus.REJECTED,
    ProposalStatus.AMBIGUOUS_ENTITY,
    ProposalStatus.INVALID_SCHEMA,
    ProposalStatus.CONFLICT_DETECTED,
    ProposalStatus.UNSUPPORTED_PREDICATE,
}


class FactWorkflowError(ValueError):
    pass


class FactApprovalError(PermissionError):
    pass


class FactQueryError(ValueError):
    pass


class FactMemory:
    """Separate, non-executable factual memory with hash-bound writes."""

    def __init__(
        self,
        database: FactDatabase,
        *,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.database = database
        self._clock = clock
        self.database.verify_schema()

    @classmethod
    def initialize(
        cls, root: Path, *, clock: Callable[[], str] = utc_now
    ) -> FactMemory:
        return cls(FactDatabase.initialize(root), clock=clock)

    @classmethod
    def open(cls, root: Path, *, clock: Callable[[], str] = utc_now) -> FactMemory:
        return cls(FactDatabase(root), clock=clock)

    @property
    def root(self) -> Path:
        return self.database.root

    def add_entity(
        self,
        *,
        entity_id: str,
        entity_type: str,
        canonical_label_ru: str,
        canonical_label_en: str,
        aliases_ru: tuple[str, ...] | list[str] = (),
        aliases_en: tuple[str, ...] | list[str] = (),
        external_identifiers: dict[str, str] | None = None,
        provenance: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
    ) -> EntityRecord:
        _validate_id(entity_id, "entity_id")
        _validate_id(entity_type, "entity_type")
        if not canonical_label_ru.strip() or not canonical_label_en.strip():
            raise ValueError("canonical entity labels must be non-empty")
        now = self._now()
        payload = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "canonical_label_ru": canonical_label_ru.strip(),
            "canonical_label_en": canonical_label_en.strip(),
            "aliases_ru": tuple(_unique_text(aliases_ru)),
            "aliases_en": tuple(_unique_text(aliases_en)),
            "external_identifiers": dict(sorted((external_identifiers or {}).items())),
            "status": EntityStatus.ACTIVE,
            "created_at": now,
            "updated_at": now,
            "provenance": tuple(dict(row) for row in provenance),
            "schema_version": FACT_MEMORY_SCHEMA_VERSION,
        }
        record = EntityRecord(**payload, content_hash=content_hash(payload))
        aliases = {
            "ru": (record.canonical_label_ru, *record.aliases_ru),
            "en": (record.canonical_label_en, *record.aliases_en),
        }
        with self.database.write() as connection:
            connection.execute(
                """INSERT INTO entities(
                    entity_id, entity_type, status, created_at, updated_at,
                    content_hash, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.entity_id,
                    record.entity_type,
                    record.status,
                    record.created_at,
                    record.updated_at,
                    record.content_hash,
                    canonical_json(record),
                ),
            )
            for language, labels in aliases.items():
                for label in labels:
                    connection.execute(
                        "INSERT INTO entity_aliases VALUES (?, ?, ?, ?)",
                        (normalize_label(label), language, entity_id, label),
                    )
            self.database.append_audit(
                connection,
                "ENTITY_ADDED",
                {"entity_hash": record.content_hash},
                entity_id,
            )
        return record

    def add_entity_alias(self, entity_id: str, alias: str, language: str) -> None:
        if language not in {"ru", "en"} or not alias.strip():
            raise ValueError("alias requires ru/en language and non-empty text")
        with self.database.write() as connection:
            self._entity_row(connection, entity_id)
            connection.execute(
                "INSERT INTO entity_aliases VALUES (?, ?, ?, ?)",
                (normalize_label(alias), language, entity_id, alias.strip()),
            )
            self.database.append_audit(
                connection,
                "ENTITY_ALIAS_ADDED",
                {
                    "alias_hash": content_hash(normalize_label(alias)),
                    "language": language,
                },
                entity_id,
            )

    def resolve_entity(
        self, value: str, language: str | None = None
    ) -> EntityResolution:
        normalized = normalize_label(value)
        with self.database.connect() as connection:
            direct = connection.execute(
                "SELECT entity_id FROM entities WHERE entity_id = ? AND status = 'ACTIVE'",
                (value,),
            ).fetchall()
            if direct:
                return EntityResolution(
                    EntityResolutionStatus.EXACT, (value,), normalized
                )
            if language is None:
                rows = connection.execute(
                    """SELECT DISTINCT a.entity_id FROM entity_aliases a
                       JOIN entities e ON e.entity_id = a.entity_id
                       WHERE a.normalized_alias = ? AND e.status = 'ACTIVE'
                       ORDER BY a.entity_id""",
                    (normalized,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT DISTINCT a.entity_id FROM entity_aliases a
                       JOIN entities e ON e.entity_id = a.entity_id
                       WHERE a.normalized_alias = ? AND a.language = ?
                         AND e.status = 'ACTIVE' ORDER BY a.entity_id""",
                    (normalized, language),
                ).fetchall()
        ids = tuple(row[0] for row in rows)
        if len(ids) == 1:
            return EntityResolution(EntityResolutionStatus.EXACT, ids, normalized)
        if len(ids) > 1:
            return EntityResolution(
                EntityResolutionStatus.AMBIGUOUS_ENTITY, ids, normalized
            )
        return EntityResolution(EntityResolutionStatus.UNKNOWN_ENTITY, (), normalized)

    def add_predicate(
        self,
        *,
        predicate_id: str,
        canonical_name_ru: str,
        canonical_name_en: str,
        subject_entity_type: str,
        object_kind: FactValueKind | str,
        cardinality: Cardinality | str,
        temporal_mode: TemporalMode | str,
        allowed_qualifiers: dict[str, FactValueKind | str] | None = None,
        unit_dimension: str | None = None,
        conflict_key_fields: tuple[str, ...] | list[str] = (),
        overlapping_intervals_permitted: bool = False,
        schema_version: int = 1,
    ) -> PredicateDefinition:
        _validate_id(predicate_id, "predicate_id")
        _validate_id(subject_entity_type, "subject_entity_type")
        qualifiers = {
            key: FactValueKind(value)
            for key, value in sorted((allowed_qualifiers or {}).items())
        }
        for key in qualifiers:
            _validate_id(key, "qualifier")
        conflict_keys = tuple(conflict_key_fields)
        if any(key not in qualifiers for key in conflict_keys):
            raise ValueError("conflict key fields must be allowed qualifiers")
        payload = {
            "predicate_id": predicate_id,
            "canonical_name_ru": canonical_name_ru.strip(),
            "canonical_name_en": canonical_name_en.strip(),
            "subject_entity_type": subject_entity_type,
            "object_kind": FactValueKind(object_kind),
            "cardinality": Cardinality(cardinality),
            "temporal_mode": TemporalMode(temporal_mode),
            "allowed_qualifiers": qualifiers,
            "unit_dimension": unit_dimension,
            "conflict_key_fields": conflict_keys,
            "overlapping_intervals_permitted": bool(overlapping_intervals_permitted),
            "schema_version": schema_version,
            "active": True,
            "deprecated": False,
        }
        if not payload["canonical_name_ru"] or not payload["canonical_name_en"]:
            raise ValueError("predicate names must be non-empty")
        record = PredicateDefinition(**payload, content_hash=content_hash(payload))
        with self.database.write() as connection:
            connection.execute(
                """INSERT INTO predicate_definitions(
                    predicate_id, subject_entity_type, object_kind, cardinality,
                    temporal_mode, active, deprecated, content_hash, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.predicate_id,
                    record.subject_entity_type,
                    record.object_kind,
                    record.cardinality,
                    record.temporal_mode,
                    int(record.active),
                    int(record.deprecated),
                    record.content_hash,
                    canonical_json(record),
                ),
            )
            self.database.append_audit(
                connection,
                "PREDICATE_ADDED",
                {"predicate_hash": record.content_hash},
                predicate_id,
            )
        return record

    def add_source(
        self,
        *,
        content: bytes | str | dict[str, Any] | list[Any],
        source_kind: SourceKind | str,
        title: str,
        source_family: str,
        trust_tier: str,
        author: str | None = None,
        publisher: str | None = None,
        locator: str | None = None,
        published_at: str | None = None,
        retrieved_at: str | None = None,
        language: str | None = None,
        license_metadata: dict[str, Any] | None = None,
        original_filename: str | None = None,
        media_type: str | None = None,
        source_id: str | None = None,
    ) -> SourceRecord:
        identifier = source_id or f"src_{uuid4().hex}"
        _validate_id(identifier, "source_id")
        if isinstance(content, (dict, list)):
            raw = canonical_json(content).encode("utf-8")
            media = media_type or "application/json"
        elif isinstance(content, str):
            raw = content.encode("utf-8")
            media = media_type or "text/plain; charset=utf-8"
        elif isinstance(content, bytes):
            raw = content
            media = media_type or "application/octet-stream"
        else:
            raise TypeError("source content must be bytes, text, or JSON")
        snapshot_hash = self.database.blobs.put(raw)
        now = self._now()
        payload = {
            "source_id": identifier,
            "source_kind": SourceKind(source_kind),
            "title": title.strip(),
            "author": author,
            "publisher": publisher,
            "locator": locator,
            "published_at": normalize_temporal(published_at),
            "retrieved_at": normalize_temporal(retrieved_at) or now,
            "language": language,
            "source_family": source_family.strip(),
            "trust_tier": trust_tier.strip(),
            "content_hash": bytes_hash(raw),
            "snapshot_hash": snapshot_hash,
            "status": SourceStatus.ACTIVE,
            "license_metadata": dict(license_metadata or {}),
            "original_filename": Path(original_filename).name
            if original_filename
            else None,
            "media_type": media,
            "created_at": now,
        }
        if (
            not payload["title"]
            or not payload["source_family"]
            or not payload["trust_tier"]
        ):
            raise ValueError("source title, family and trust tier are required")
        record = SourceRecord(**payload, record_hash=content_hash(payload))
        with self.database.write() as connection:
            connection.execute(
                """INSERT INTO sources(
                    source_id, source_family, source_kind, trust_tier, snapshot_hash,
                    status, created_at, record_hash, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.source_id,
                    record.source_family,
                    record.source_kind,
                    record.trust_tier,
                    record.snapshot_hash,
                    record.status,
                    record.created_at,
                    record.record_hash,
                    canonical_json(record),
                ),
            )
            self.database.append_audit(
                connection,
                "SOURCE_ADDED",
                {"source_hash": record.record_hash, "snapshot_hash": snapshot_hash},
                identifier,
            )
        return record

    def add_evidence(
        self,
        *,
        source_id: str,
        relation: EvidenceRelation | str,
        location_kind: EvidenceLocationKind | str,
        location: dict[str, Any],
        extraction_method: ExtractionMethod | str,
        extraction_confidence: Decimal | str,
        reviewer: str | None = None,
        approved: bool = False,
        evidence_id: str | None = None,
    ) -> EvidenceRecord:
        identifier = evidence_id or f"ev_{uuid4().hex}"
        _validate_id(identifier, "evidence_id")
        method = ExtractionMethod(extraction_method)
        confidence = _confidence_text(extraction_confidence)
        if (
            method == ExtractionMethod.MODEL_PROPOSED
            and approved
            and (not reviewer or reviewer.casefold() in {"model", "self", "ai"})
        ):
            raise FactApprovalError(
                "model-proposed evidence requires an independent reviewer"
            )
        with self.database.connect() as connection:
            source = self._source(connection, source_id)
        content = self.database.blobs.read(source.snapshot_hash)
        excerpt = extract_evidence(
            content,
            location_kind,
            dict(location),
            media_type=source.media_type,
        )
        payload = {
            "evidence_id": identifier,
            "source_id": source_id,
            "relation": EvidenceRelation(relation),
            "snapshot_hash": source.snapshot_hash,
            "location_kind": EvidenceLocationKind(location_kind),
            "location": dict(location),
            "excerpt_hash": bytes_hash(excerpt),
            "extraction_method": method,
            "extraction_confidence": confidence,
            "reviewer": reviewer,
            "approval_status": ApprovalStatus.APPROVED
            if approved
            else ApprovalStatus.PENDING,
            "created_at": self._now(),
        }
        record = EvidenceRecord(**payload, evidence_hash=content_hash(payload))
        with self.database.write() as connection:
            self._source_row(connection, source_id)
            connection.execute(
                """INSERT INTO evidence(
                    evidence_id, source_id, relation, snapshot_hash, approval_status,
                    created_at, evidence_hash, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.evidence_id,
                    record.source_id,
                    record.relation,
                    record.snapshot_hash,
                    record.approval_status,
                    record.created_at,
                    record.evidence_hash,
                    canonical_json(record),
                ),
            )
            self.database.append_audit(
                connection,
                "EVIDENCE_ADDED",
                {
                    "evidence_hash": record.evidence_hash,
                    "source_hash": source.record_hash,
                },
                identifier,
            )
        return record

    def verify_evidence(
        self, evidence_id: str, *, require_approved: bool = True
    ) -> EvidenceRecord:
        with self.database.connect() as connection:
            evidence = self._evidence(connection, evidence_id)
            source = self._source(connection, evidence.source_id)
        if evidence.snapshot_hash != source.snapshot_hash:
            raise SourceIntegrityError("evidence snapshot hash differs from source")
        content = self.database.blobs.read(source.snapshot_hash)
        excerpt = extract_evidence(
            content,
            evidence.location_kind,
            evidence.location,
            media_type=source.media_type,
        )
        if bytes_hash(excerpt) != evidence.excerpt_hash:
            raise SourceIntegrityError("evidence excerpt hash mismatch")
        payload = asdict(evidence)
        digest = payload.pop("evidence_hash")
        if content_hash(payload) != digest:
            raise SourceIntegrityError("evidence record hash mismatch")
        if require_approved and evidence.approval_status != ApprovalStatus.APPROVED:
            raise FactApprovalError(
                "unapproved evidence cannot support a trusted claim"
            )
        if (
            require_approved
            and evidence.extraction_method == ExtractionMethod.MODEL_PROPOSED
            and not evidence.reviewer
        ):
            raise FactApprovalError("model-proposed evidence lacks independent review")
        return evidence

    def receive_proposal(
        self,
        *,
        source: ProposalSource | str,
        subject_entity_id: str,
        predicate_id: str,
        object_value: FactValue,
        qualifiers: dict[str, FactValue] | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        source_ids: tuple[str, ...] | list[str] = (),
        evidence_ids: tuple[str, ...] | list[str] = (),
        proposal_id: str | None = None,
    ) -> FactProposal:
        identifier = proposal_id or f"proposal_{uuid4().hex}"
        _validate_id(identifier, "proposal_id")
        now = self._now()
        payload = {
            "proposal_id": identifier,
            "revision": 1,
            "source": ProposalSource(source),
            "status": ProposalStatus.RECEIVED,
            "subject_entity_id": subject_entity_id,
            "predicate_id": predicate_id,
            "object_value": object_value,
            "qualifiers": dict(sorted((qualifiers or {}).items())),
            "valid_from": normalize_temporal(valid_from),
            "valid_to": normalize_temporal(valid_to),
            "source_ids": tuple(sorted(set(source_ids))),
            "evidence_ids": tuple(sorted(set(evidence_ids))),
            "created_at": now,
            "updated_at": now,
            "schema_version": FACT_MEMORY_SCHEMA_VERSION,
        }
        proposal = FactProposal(**payload, proposal_hash=content_hash(payload))
        self._store_proposal(proposal, "CLAIM_PROPOSED")
        return proposal

    def advance_proposal(
        self,
        proposal_id: str,
        target: ProposalStatus | str,
        *,
        reviewer: str | None = None,
    ) -> FactProposal:
        requested = ProposalStatus(target)
        with self.database.connect() as connection:
            current = self._latest_proposal(connection, proposal_id)
        expected = _WORKFLOW_NEXT.get(current.status)
        if requested in _TERMINAL_PROPOSAL_STATUSES:
            if current.status in _TERMINAL_PROPOSAL_STATUSES | {
                ProposalStatus.COMMITTED
            }:
                raise FactWorkflowError("terminal proposal cannot transition")
        elif requested != expected:
            raise FactWorkflowError(
                f"proposal transition must be {expected}, got {requested}"
            )
        if requested == ProposalStatus.PARSED:
            if not isinstance(current.object_value, FactValue):
                raise FactWorkflowError("proposal value was not parsed")
        elif requested == ProposalStatus.EVIDENCE_ATTACHED:
            if not current.evidence_ids:
                raise FactWorkflowError("proposal has no evidence")
            for evidence_id in current.evidence_ids:
                self.verify_evidence(evidence_id, require_approved=True)
        elif requested == ProposalStatus.VALIDATED:
            self._validate_proposal(current)
        elif requested == ProposalStatus.REVIEWED and not reviewer:
            raise FactWorkflowError("reviewer identity is required")
        elif requested in {ProposalStatus.APPROVED, ProposalStatus.COMMITTED}:
            raise FactWorkflowError(
                "use approve_proposal/commit_proposal for trusted transitions"
            )
        proposal = self._proposal_revision(current, requested)
        event = {
            ProposalStatus.PARSED: "CLAIM_PARSED",
            ProposalStatus.EVIDENCE_ATTACHED: "CLAIM_EVIDENCE_ATTACHED",
            ProposalStatus.VALIDATED: "CLAIM_VALIDATED",
            ProposalStatus.REVIEWED: "CLAIM_REVIEWED",
        }.get(requested, "CLAIM_PROPOSAL_TERMINATED")
        self._store_proposal(
            proposal, event, extra={"reviewer": reviewer} if reviewer else None
        )
        return proposal

    def prepare_for_review(self, proposal_id: str, *, reviewer: str) -> FactProposal:
        current = self.get_proposal(proposal_id)
        while current.status != ProposalStatus.REVIEWED:
            if current.status == ProposalStatus.VALIDATED:
                current = self.advance_proposal(
                    current.proposal_id, ProposalStatus.REVIEWED, reviewer=reviewer
                )
            else:
                target = _WORKFLOW_NEXT.get(current.status)
                if target is None:
                    raise FactWorkflowError(
                        f"cannot prepare proposal from {current.status}"
                    )
                current = self.advance_proposal(current.proposal_id, target)
        return current

    def approve_proposal(
        self,
        proposal_id: str,
        *,
        reviewer_identity: str,
        reviewer_identity_type: str = "HUMAN",
        decision: ApprovalDecision | str = ApprovalDecision.APPROVE,
        contested_approval: bool = False,
    ) -> FactApprovalEnvelope:
        with self.database.connect() as connection:
            proposal = self._latest_proposal(connection, proposal_id)
            entity = self._entity(connection, proposal.subject_entity_id)
            predicate = self._predicate(connection, proposal.predicate_id)
            sources = tuple(
                self._source(connection, item) for item in proposal.source_ids
            )
            evidence = tuple(
                self._evidence(connection, item) for item in proposal.evidence_ids
            )
        if proposal.status != ProposalStatus.REVIEWED:
            raise FactApprovalError("proposal must be REVIEWED before approval")
        if (
            proposal.source == ProposalSource.MODEL_EXTRACTION
            and reviewer_identity_type == "MODEL"
        ):
            raise FactApprovalError("a model-produced proposal cannot approve itself")
        chosen = ApprovalDecision(decision)
        if chosen not in {ApprovalDecision.APPROVE, ApprovalDecision.MARK_CONTESTED}:
            terminal = (
                ProposalStatus.REJECTED
                if chosen == ApprovalDecision.REJECT
                else ProposalStatus.INVALID_SCHEMA
            )
            self.advance_proposal(proposal_id, terminal)
            raise FactApprovalError(
                f"decision {chosen} does not authorize a FactMemory write"
            )
        if chosen == ApprovalDecision.MARK_CONTESTED and not contested_approval:
            raise FactApprovalError("contested claim approval must be explicit")
        self._validate_proposal(proposal)
        for item in evidence:
            self.verify_evidence(item.evidence_id, require_approved=True)
        payload = {
            "approval_id": f"fact_approval_{uuid4().hex}",
            "proposal_id": proposal.proposal_id,
            "proposal_hash": proposal.proposal_hash,
            "entity_hash": entity.content_hash,
            "predicate_definition_hash": predicate.content_hash,
            "typed_value_hash": content_hash(proposal.object_value),
            "qualifier_hash": content_hash(proposal.qualifiers),
            "valid_from": proposal.valid_from,
            "valid_to": proposal.valid_to,
            "source_hashes": tuple(sorted(item.record_hash for item in sources)),
            "evidence_hashes": tuple(sorted(item.evidence_hash for item in evidence)),
            "reviewer_identity": reviewer_identity,
            "reviewer_identity_type": reviewer_identity_type,
            "decision": chosen,
            "contested_approval": contested_approval,
            "policy_version": FACT_APPROVAL_POLICY_VERSION,
            "fact_memory_schema_version": FACT_MEMORY_SCHEMA_VERSION,
            "created_at": self._now(),
        }
        envelope = FactApprovalEnvelope(**payload, approval_hash=content_hash(payload))
        approved = self._proposal_revision(proposal, ProposalStatus.APPROVED)
        with self.database.write() as connection:
            connection.execute(
                """INSERT INTO approvals(
                    approval_id, proposal_id, proposal_hash, decision, created_at,
                    approval_hash, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    envelope.approval_id,
                    envelope.proposal_id,
                    envelope.proposal_hash,
                    envelope.decision,
                    envelope.created_at,
                    envelope.approval_hash,
                    canonical_json(envelope),
                ),
            )
            self._insert_proposal(connection, approved)
            self.database.append_audit(
                connection,
                "CLAIM_APPROVED",
                {
                    "proposal_hash": proposal.proposal_hash,
                    "approval_hash": envelope.approval_hash,
                    "decision": envelope.decision,
                },
                proposal_id,
            )
        return envelope

    def commit_proposal(self, proposal_id: str, approval_id: str) -> ClaimRecord:
        with self.database.connect() as connection:
            proposal = self._latest_proposal(connection, proposal_id)
            approval = self._approval(connection, approval_id)
        if proposal.status != ProposalStatus.APPROVED:
            raise FactApprovalError("only an APPROVED proposal can be committed")
        self._verify_approval(proposal, approval)
        self._validate_proposal(proposal)
        for evidence_id in proposal.evidence_ids:
            self.verify_evidence(evidence_id, require_approved=True)
        identity = _canonical_claim_identity(proposal)
        canonical_claim_hash = content_hash(identity)
        with self.database.write() as connection:
            duplicate = connection.execute(
                "SELECT claim_id FROM claims WHERE canonical_claim_hash = ?",
                (canonical_claim_hash,),
            ).fetchone()
            if duplicate is not None:
                claim_id = duplicate[0]
                self._attach_claim_evidence(connection, claim_id, proposal.evidence_ids)
                committed = self._proposal_revision(proposal, ProposalStatus.COMMITTED)
                self._insert_proposal(connection, committed)
                self.database.append_audit(
                    connection,
                    "CLAIM_CORROBORATED",
                    {
                        "proposal_hash": proposal.proposal_hash,
                        "claim_id": claim_id,
                        "evidence_ids": proposal.evidence_ids,
                    },
                    claim_id,
                )
                return self._claim(connection, claim_id)
            status = (
                ClaimStatus.CONTESTED
                if approval.decision == ApprovalDecision.MARK_CONTESTED
                else ClaimStatus.SUPPORTED
            )
            claim_id = f"claim_{uuid4().hex}"
            sources = tuple(
                self._source(connection, self._evidence(connection, item).source_id)
                for item in proposal.evidence_ids
            )
            payload = {
                "claim_id": claim_id,
                "subject_entity_id": proposal.subject_entity_id,
                "predicate_id": proposal.predicate_id,
                "object_value": proposal.object_value,
                "qualifiers": proposal.qualifiers,
                "valid_from": proposal.valid_from,
                "valid_to": proposal.valid_to,
                "recorded_at": self._now(),
                "status": status,
                "evidence_ids": tuple(sorted(proposal.evidence_ids)),
                "source_family_support_set": tuple(
                    sorted({item.source_family for item in sources})
                ),
                "supersedes_claim_ids": (),
                "retraction_reason": None,
                "proposal_hash": proposal.proposal_hash,
                "approval_hash": approval.approval_hash,
                "canonical_claim_hash": canonical_claim_hash,
                "schema_version": FACT_MEMORY_SCHEMA_VERSION,
            }
            claim = ClaimRecord(**payload)
            connection.execute(
                """INSERT INTO claims(
                    claim_id, subject_entity_id, predicate_id, object_hash,
                    qualifier_hash, valid_from_key, valid_to_key, recorded_at,
                    base_status, canonical_claim_hash, proposal_hash, approval_hash,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    claim.claim_id,
                    claim.subject_entity_id,
                    claim.predicate_id,
                    content_hash(claim.object_value),
                    content_hash(claim.qualifiers),
                    temporal_key(claim.valid_from),
                    temporal_key(claim.valid_to, upper=True),
                    claim.recorded_at,
                    claim.status,
                    claim.canonical_claim_hash,
                    claim.proposal_hash,
                    claim.approval_hash,
                    canonical_json(claim),
                ),
            )
            self._attach_claim_evidence(connection, claim_id, proposal.evidence_ids)
            connection.execute(
                "INSERT INTO claim_status_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                _status_event_values(
                    claim_id, status, "FACT_MEMORY", None, claim.recorded_at
                ),
            )
            conflicts = self._create_conflicts(connection, claim)
            committed = self._proposal_revision(proposal, ProposalStatus.COMMITTED)
            self._insert_proposal(connection, committed)
            self.database.append_audit(
                connection,
                "CLAIM_COMMITTED",
                {
                    "claim_hash": claim.canonical_claim_hash,
                    "approval_hash": claim.approval_hash,
                    "conflict_group_ids": tuple(
                        item.conflict_group_id for item in conflicts
                    ),
                },
                claim_id,
            )
            if conflicts:
                self.database.append_audit(
                    connection,
                    "CLAIM_CONTESTED",
                    {
                        "conflict_group_ids": tuple(
                            item.conflict_group_id for item in conflicts
                        )
                    },
                    claim_id,
                )
            return self._claim(connection, claim_id)

    def supersede_claim(
        self,
        old_claim_id: str,
        new_claim_id: str,
        *,
        actor: str,
        reason: str,
    ) -> None:
        if old_claim_id == new_claim_id:
            raise ValueError("claim cannot supersede itself")
        with self.database.write() as connection:
            self._claim_row(connection, old_claim_id)
            self._claim_row(connection, new_claim_id)
            if self._relation_reaches(connection, old_claim_id, new_claim_id):
                raise ValueError("supersession cycle detected")
            recorded_at = self._now()
            self._insert_relation(
                connection,
                source_claim_id=new_claim_id,
                target_claim_id=old_claim_id,
                relation_type="SUPERSEDES",
                actor=actor,
                reason=reason,
                recorded_at=recorded_at,
            )
            connection.execute(
                "INSERT INTO claim_status_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                _status_event_values(
                    old_claim_id, ClaimStatus.SUPERSEDED, actor, reason, recorded_at
                ),
            )
            self.database.append_audit(
                connection,
                "CLAIM_SUPERSEDED",
                {"new_claim_id": new_claim_id, "reason_hash": content_hash(reason)},
                old_claim_id,
            )

    def retract_claim(self, claim_id: str, *, actor: str, reason: str) -> None:
        if not reason.strip():
            raise ValueError("retraction reason is required")
        with self.database.write() as connection:
            self._claim_row(connection, claim_id)
            recorded_at = self._now()
            connection.execute(
                "INSERT INTO claim_status_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                _status_event_values(
                    claim_id, ClaimStatus.RETRACTED, actor, reason, recorded_at
                ),
            )
            self.database.append_audit(
                connection,
                "CLAIM_RETRACTED",
                {"actor": actor, "reason_hash": content_hash(reason)},
                claim_id,
            )

    def retract_source(self, source_id: str, *, actor: str, reason: str) -> None:
        self.set_source_status(
            source_id,
            status=SourceStatus.RETRACTED,
            actor=actor,
            reason=reason,
        )

    def set_source_status(
        self,
        source_id: str,
        *,
        status: SourceStatus | str,
        actor: str,
        reason: str,
    ) -> None:
        if not reason.strip():
            raise ValueError("source status reason is required")
        selected = SourceStatus(status)
        if selected == SourceStatus.ACTIVE:
            raise ValueError("source reactivation requires a future reviewed policy")
        with self.database.write() as connection:
            self._source_row(connection, source_id)
            recorded_at = self._now()
            payload = {
                "event_id": f"source_status_{uuid4().hex}",
                "source_id": source_id,
                "status": selected,
                "actor": actor,
                "reason": reason,
                "recorded_at": recorded_at,
            }
            event_hash = content_hash(payload)
            connection.execute(
                "INSERT INTO source_status_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (*payload.values(), event_hash),
            )
            self.database.append_audit(
                connection,
                "SOURCE_RETRACTED"
                if selected == SourceStatus.RETRACTED
                else "SOURCE_UNAVAILABLE",
                {"actor": actor, "reason_hash": content_hash(reason)},
                source_id,
            )

    def make_query(
        self,
        *,
        subject: str,
        predicate_id: str | None,
        object_filter: FactValue | None = None,
        qualifier_filters: dict[str, FactValue] | None = None,
        valid_at_value: str | None = None,
        known_at: str | None = None,
        accepted_statuses: tuple[ClaimStatus, ...] | None = None,
        include_conflicts: bool = True,
        include_retracted: bool = False,
        include_evidence: bool = True,
        language: str = "en",
        memory_snapshot: str | None = None,
    ) -> FactQuery:
        payload = {
            "query_id": f"fact_query_{uuid4().hex}",
            "subject": subject,
            "predicate_id": predicate_id,
            "object_filter": object_filter,
            "qualifier_filters": dict(sorted((qualifier_filters or {}).items())),
            "valid_at": normalize_temporal(valid_at_value),
            "known_at": normalize_temporal(known_at),
            "accepted_statuses": accepted_statuses
            or (
                ClaimStatus.SUPPORTED,
                ClaimStatus.CORROBORATED,
                ClaimStatus.CONTESTED,
            ),
            "include_conflicts": include_conflicts,
            "include_retracted": include_retracted,
            "include_evidence": include_evidence,
            "language": language,
            "memory_snapshot": memory_snapshot,
            "created_at": self._now(),
        }
        semantic = dict(payload)
        semantic.pop("query_id")
        semantic.pop("created_at")
        return FactQuery(**payload, query_hash=content_hash(semantic))

    def query(self, query: FactQuery) -> FactAnswerBundle:
        snapshot = self.database.snapshot_hash()
        with self.database.connect() as connection:
            reused = connection.execute(
                "SELECT 1 FROM fact_queries WHERE query_id = ?", (query.query_id,)
            ).fetchone()
        if reused is not None:
            raise FactQueryError("query_id was already used")
        if query.query_hash != _semantic_query_hash(query):
            return self._empty_answer(
                query, QueryStatus.INVALID_QUERY, snapshot, ("QUERY_HASH_MISMATCH",)
            )
        if query.memory_snapshot is not None and query.memory_snapshot != snapshot:
            return self._empty_answer(
                query, QueryStatus.INVALID_QUERY, snapshot, ("STALE_SNAPSHOT",)
            )
        resolution = self.resolve_entity(query.subject, query.language)
        if resolution.status == EntityResolutionStatus.AMBIGUOUS_ENTITY:
            return self._empty_answer(query, QueryStatus.AMBIGUOUS_ENTITY, snapshot)
        if resolution.status == EntityResolutionStatus.UNKNOWN_ENTITY:
            return self._empty_answer(query, QueryStatus.UNKNOWN_ENTITY, snapshot)
        entity_id = resolution.entity_ids[0]
        with self.database.connect() as connection:
            if query.predicate_id is not None:
                row = connection.execute(
                    "SELECT 1 FROM predicate_definitions WHERE predicate_id = ? AND active = 1",
                    (query.predicate_id,),
                ).fetchone()
                if row is None:
                    return self._empty_answer(
                        query, QueryStatus.UNKNOWN_PREDICATE, snapshot
                    )
            sql = "SELECT claim_id FROM claims WHERE subject_entity_id = ?"
            parameters: list[Any] = [entity_id]
            if query.predicate_id is not None:
                sql += " AND predicate_id = ?"
                parameters.append(query.predicate_id)
            sql += " ORDER BY recorded_at, claim_id"
            candidates = [
                self._claim(connection, row[0])
                for row in connection.execute(sql, parameters)
            ]
            known_point = query.known_at or self._now()
            world_point = query.valid_at or self._now()
            visible: list[ClaimRecord] = []
            excluded_statuses: list[ClaimStatus] = []
            stale_claims: list[ClaimRecord] = []
            for claim in candidates:
                if temporal_key(claim.recorded_at) > temporal_key(known_point):
                    continue
                predicate = self._predicate(connection, claim.predicate_id)
                if (
                    predicate.temporal_mode == TemporalMode.VALID_INTERVAL
                    and not valid_at(claim.valid_from, claim.valid_to, world_point)
                ):
                    continue
                if (
                    predicate.temporal_mode == TemporalMode.EVENT
                    and query.valid_at is not None
                    and temporal_key(claim.valid_from) != temporal_key(world_point)
                ):
                    continue
                if (
                    query.object_filter is not None
                    and claim.object_value != query.object_filter
                ):
                    continue
                if any(
                    claim.qualifiers.get(key) != value
                    for key, value in query.qualifier_filters.items()
                ):
                    continue
                evidence_ids = self._claim_evidence_at(
                    connection, claim.claim_id, known_point
                )
                claim = replace(claim, evidence_ids=evidence_ids)
                status = self._claim_status_at(connection, claim.claim_id, known_point)
                families = {
                    self._source(
                        connection, self._evidence(connection, item).source_id
                    ).source_family
                    for item in evidence_ids
                }
                if status == ClaimStatus.SUPPORTED and len(families) >= 2:
                    status = ClaimStatus.CORROBORATED
                claim = replace(
                    claim,
                    status=status,
                    source_family_support_set=tuple(sorted(families)),
                )
                source_state = self._claim_source_state(connection, claim, known_point)
                if source_state != "ACTIVE":
                    stale_claims.append(claim)
                    if not query.include_retracted:
                        continue
                if status not in query.accepted_statuses:
                    excluded_statuses.append(status)
                    if not (
                        query.include_retracted and status == ClaimStatus.RETRACTED
                    ):
                        continue
                visible.append(claim)
            if not visible:
                if stale_claims:
                    status = QueryStatus.STALE_ONLY
                elif excluded_statuses and all(
                    item == ClaimStatus.RETRACTED for item in excluded_statuses
                ):
                    status = QueryStatus.RETRACTED_ONLY
                else:
                    status = QueryStatus.NO_FACT
                return self._store_answer(
                    connection,
                    query,
                    self._build_answer(query, status, snapshot, (), (), ()),
                )
            conflict_pool = [*visible, *stale_claims]
            conflicts = self._matching_conflicts(connection, conflict_pool)
            stale_conflict_ids = {
                claim_id
                for group in conflicts
                for claim_id in group.claim_ids
                if claim_id in {item.claim_id for item in stale_claims}
            }
            if stale_conflict_ids:
                visible.extend(
                    item
                    for item in stale_claims
                    if item.claim_id in stale_conflict_ids
                    and item.claim_id not in {row.claim_id for row in visible}
                )
            if conflicts and query.include_conflicts:
                status = QueryStatus.CONFLICT
                warnings = ("UNRESOLVED_CONFLICT",) + (
                    ("SOURCE_RETRACTED_OR_UNAVAILABLE_SIDE",)
                    if stale_conflict_ids
                    else ()
                )
            else:
                predicate = self._predicate(connection, visible[0].predicate_id)
                status = (
                    QueryStatus.EXACT_MULTI
                    if predicate.cardinality == Cardinality.MULTI or len(visible) > 1
                    else QueryStatus.EXACT_SINGLE
                )
                warnings = ("CONFLICTS_EXCLUDED",) if conflicts else ()
            answers = tuple(
                self._claim_answer(connection, claim, known_point, bool(conflicts))
                for claim in visible
            )
            bundle = self._build_answer(
                query,
                status,
                snapshot,
                answers,
                tuple(item.conflict_group_id for item in conflicts),
                warnings,
            )
            return self._store_answer(connection, query, bundle)

    def claim_history(self, claim_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            claim = self._claim(connection, claim_id)
            states = [
                dict(row)
                for row in connection.execute(
                    "SELECT status, actor, reason, recorded_at, event_hash FROM claim_status_events WHERE claim_id = ? ORDER BY recorded_at",
                    (claim_id,),
                )
            ]
            relations = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM claim_relations WHERE source_claim_id = ? OR target_claim_id = ? ORDER BY recorded_at",
                    (claim_id, claim_id),
                )
            ]
        return {"claim": asdict(claim), "status_events": states, "relations": relations}

    def get_claim(self, claim_id: str) -> ClaimRecord:
        with self.database.connect() as connection:
            return self._claim(connection, claim_id)

    def get_source(self, source_id: str) -> SourceRecord:
        with self.database.connect() as connection:
            return self._source(connection, source_id)

    def claims_affected_by_source(self, source_id: str) -> tuple[ClaimRecord, ...]:
        with self.database.connect() as connection:
            self._source_row(connection, source_id)
            rows = connection.execute(
                """SELECT DISTINCT c.claim_id FROM claims c
                   JOIN claim_evidence ce ON ce.claim_id = c.claim_id
                   JOIN evidence e ON e.evidence_id = ce.evidence_id
                   WHERE e.source_id = ? ORDER BY c.claim_id""",
                (source_id,),
            )
            return tuple(self._claim(connection, row[0]) for row in rows)

    def conflicts(self, *, unresolved_only: bool = True) -> tuple[ConflictGroup, ...]:
        with self.database.connect() as connection:
            sql = "SELECT payload_json FROM conflict_groups"
            if unresolved_only:
                sql += " WHERE resolution_status = 'UNRESOLVED'"
            sql += " ORDER BY created_at, conflict_group_id"
            return tuple(_conflict_from_json(row[0]) for row in connection.execute(sql))

    def replay_answer(self, bundle: FactAnswerBundle) -> ReplayStatus:
        payload = asdict(bundle)
        digest = payload.pop("answer_hash")
        if content_hash(payload) != digest:
            raise FactMemoryIntegrityError("answer bundle hash mismatch")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT query_hash, snapshot_hash, payload_json FROM fact_answers WHERE answer_hash = ?",
                (bundle.answer_hash,),
            ).fetchone()
            if (
                row is None
                or row[0] != bundle.query_hash
                or row[2] != canonical_json(bundle)
            ):
                raise FactMemoryIntegrityError(
                    "answer receipt does not match its query"
                )
        return (
            ReplayStatus.CURRENT
            if bundle.memory_snapshot_hash == self.database.snapshot_hash()
            else ReplayStatus.STALE_SNAPSHOT
        )

    def verify(self) -> dict[str, Any]:
        result = self.database.integrity_check()
        with self.database.connect() as connection:
            for row in connection.execute("SELECT evidence_id FROM evidence"):
                self.verify_evidence(row[0], require_approved=False)
            for table, hash_column, payload_column in (
                ("entities", "content_hash", "payload_json"),
                ("predicate_definitions", "content_hash", "payload_json"),
                ("sources", "record_hash", "payload_json"),
                ("evidence", "evidence_hash", "payload_json"),
            ):
                for row in connection.execute(
                    f"SELECT {hash_column}, {payload_column} FROM {table}"
                ):
                    payload = json.loads(row[1])
                    field = "record_hash" if table == "sources" else hash_column
                    stored = payload.pop(field)
                    if stored != row[0] or content_hash(payload) != row[0]:
                        raise FactMemoryIntegrityError(f"{table} row hash mismatch")
            for row in connection.execute(
                "SELECT canonical_claim_hash, payload_json FROM claims"
            ):
                claim = _claim_from_json(row[1])
                identity = {
                    "subject_entity_id": claim.subject_entity_id,
                    "predicate_id": claim.predicate_id,
                    "object_value": claim.object_value,
                    "qualifiers": claim.qualifiers,
                    "valid_from": claim.valid_from,
                    "valid_to": claim.valid_to,
                }
                if (
                    claim.canonical_claim_hash != row[0]
                    or content_hash(identity) != row[0]
                ):
                    raise FactMemoryIntegrityError("claims row hash mismatch")
            self._verify_payload_table(
                connection, "proposals", "proposal_hash", "proposal_hash"
            )
            self._verify_payload_table(
                connection, "approvals", "approval_hash", "approval_hash"
            )
            self._verify_payload_table(
                connection, "conflict_groups", "group_hash", "group_hash"
            )
            for table, hash_column, fields in (
                (
                    "claim_evidence",
                    "transaction_hash",
                    ("claim_id", "evidence_id", "relation", "attached_at"),
                ),
                (
                    "claim_relations",
                    "relation_hash",
                    (
                        "relation_id",
                        "source_claim_id",
                        "target_claim_id",
                        "relation_type",
                        "actor",
                        "reason",
                        "recorded_at",
                    ),
                ),
                (
                    "claim_status_events",
                    "event_hash",
                    (
                        "event_id",
                        "claim_id",
                        "status",
                        "actor",
                        "reason",
                        "recorded_at",
                    ),
                ),
                (
                    "source_status_events",
                    "event_hash",
                    (
                        "event_id",
                        "source_id",
                        "status",
                        "actor",
                        "reason",
                        "recorded_at",
                    ),
                ),
            ):
                for row in connection.execute(f"SELECT * FROM {table}"):
                    payload = {field: row[field] for field in fields}
                    if content_hash(payload) != row[hash_column]:
                        raise FactMemoryIntegrityError(f"{table} row hash mismatch")
        return result

    @staticmethod
    def _verify_payload_table(
        connection: sqlite3.Connection,
        table: str,
        hash_column: str,
        payload_hash_field: str,
    ) -> None:
        for row in connection.execute(
            f"SELECT {hash_column}, payload_json FROM {table}"
        ):
            payload = json.loads(row[1])
            stored = payload.pop(payload_hash_field)
            if stored != row[0] or content_hash(payload) != row[0]:
                raise FactMemoryIntegrityError(f"{table} row hash mismatch")

    def _validate_proposal(self, proposal: FactProposal) -> None:
        validate_interval(proposal.valid_from, proposal.valid_to)
        with self.database.connect() as connection:
            entity = self._entity(connection, proposal.subject_entity_id)
            predicate = self._predicate(connection, proposal.predicate_id)
            if entity.entity_type != predicate.subject_entity_type:
                raise FactWorkflowError("subject entity type does not match predicate")
            if proposal.object_value.kind != predicate.object_kind:
                raise FactWorkflowError(
                    "object FactValue kind does not match predicate"
                )
            if predicate.temporal_mode == TemporalMode.ATEMPORAL and (
                proposal.valid_from is not None or proposal.valid_to is not None
            ):
                raise FactWorkflowError(
                    "ATEMPORAL predicate cannot have a valid interval"
                )
            if (
                predicate.temporal_mode == TemporalMode.VALID_INTERVAL
                and proposal.valid_from is None
            ):
                raise FactWorkflowError("VALID_INTERVAL predicate requires valid_from")
            if (
                predicate.temporal_mode == TemporalMode.EVENT
                and proposal.valid_from is None
            ):
                raise FactWorkflowError(
                    "EVENT predicate requires event time in valid_from"
                )
            if set(proposal.qualifiers) - set(predicate.allowed_qualifiers):
                raise FactWorkflowError("proposal contains unsupported qualifiers")
            for key, value in proposal.qualifiers.items():
                if value.kind != predicate.allowed_qualifiers[key]:
                    raise FactWorkflowError("qualifier FactValue kind mismatch")
            if proposal.object_value.kind == FactValueKind.ENTITY_REF:
                self._entity_row(connection, str(proposal.object_value.value))
            for source_id in proposal.source_ids:
                self._source_row(connection, source_id)
            evidence_sources = {
                self._evidence(connection, item).source_id
                for item in proposal.evidence_ids
            }
            if not evidence_sources <= set(proposal.source_ids):
                raise FactWorkflowError("evidence source is not bound to the proposal")
            supporting = [
                self._evidence(connection, item)
                for item in proposal.evidence_ids
                if self._evidence(connection, item).relation
                == EvidenceRelation.SUPPORTS
            ]
            if not supporting:
                raise FactWorkflowError("trusted proposal requires supporting evidence")
            if proposal.source == ProposalSource.MODEL_EXTRACTION and any(
                item.approval_status != ApprovalStatus.APPROVED for item in supporting
            ):
                raise FactApprovalError(
                    "model proposal cannot become supported without approved evidence"
                )

    def _verify_approval(
        self, proposal: FactProposal, approval: FactApprovalEnvelope
    ) -> None:
        if (
            approval.proposal_id != proposal.proposal_id
            or approval.proposal_hash != self._previous_proposal_hash(proposal)
        ):
            raise FactApprovalError("approval is stale or belongs to another proposal")
        with self.database.connect() as connection:
            entity = self._entity(connection, proposal.subject_entity_id)
            predicate = self._predicate(connection, proposal.predicate_id)
            sources = tuple(
                self._source(connection, item) for item in proposal.source_ids
            )
            evidence = tuple(
                self._evidence(connection, item) for item in proposal.evidence_ids
            )
        expected = {
            "entity_hash": entity.content_hash,
            "predicate_definition_hash": predicate.content_hash,
            "typed_value_hash": content_hash(proposal.object_value),
            "qualifier_hash": content_hash(proposal.qualifiers),
            "valid_from": proposal.valid_from,
            "valid_to": proposal.valid_to,
            "source_hashes": tuple(sorted(item.record_hash for item in sources)),
            "evidence_hashes": tuple(sorted(item.evidence_hash for item in evidence)),
            "policy_version": FACT_APPROVAL_POLICY_VERSION,
            "fact_memory_schema_version": FACT_MEMORY_SCHEMA_VERSION,
        }
        changed = next(
            (key for key, value in expected.items() if getattr(approval, key) != value),
            None,
        )
        if changed is not None:
            raise FactApprovalError(f"approval dependency changed: {changed}")
        payload = asdict(approval)
        digest = payload.pop("approval_hash")
        if content_hash(payload) != digest:
            raise FactApprovalError("approval envelope hash mismatch")

    def _previous_proposal_hash(self, approved: FactProposal) -> str:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT proposal_hash FROM proposals WHERE proposal_id = ? AND revision = ?",
                (approved.proposal_id, approved.revision - 1),
            ).fetchone()
        if row is None:
            raise FactApprovalError("approved proposal has no reviewed predecessor")
        return row[0]

    def _create_conflicts(
        self, connection: sqlite3.Connection, claim: ClaimRecord
    ) -> tuple[ConflictGroup, ...]:
        predicate = self._predicate(connection, claim.predicate_id)
        if predicate.cardinality != Cardinality.SINGLE:
            return ()
        groups = []
        rows = connection.execute(
            """SELECT claim_id FROM claims
               WHERE subject_entity_id = ? AND predicate_id = ? AND claim_id != ?
                 AND valid_from_key < ? AND ? < valid_to_key""",
            (
                claim.subject_entity_id,
                claim.predicate_id,
                claim.claim_id,
                temporal_key(claim.valid_to, upper=True),
                temporal_key(claim.valid_from),
            ),
        )
        for row in rows:
            other = self._claim(connection, row[0])
            if other.object_value == claim.object_value:
                continue
            if any(
                other.qualifiers.get(key) != claim.qualifiers.get(key)
                for key in predicate.conflict_key_fields
            ):
                continue
            status = self._claim_status_at(connection, other.claim_id, self._now())
            if status not in {
                ClaimStatus.SUPPORTED,
                ClaimStatus.CORROBORATED,
                ClaimStatus.CONTESTED,
            }:
                continue
            interval = _intersection(
                claim.valid_from, claim.valid_to, other.valid_from, other.valid_to
            )
            payload = {
                "conflict_group_id": f"conflict_{uuid4().hex}",
                "claim_ids": tuple(sorted((claim.claim_id, other.claim_id))),
                "subject_entity_id": claim.subject_entity_id,
                "predicate_id": claim.predicate_id,
                "overlapping_interval": interval,
                "conflict_reason": "SINGLE predicate has different values over an overlapping valid interval",
                "resolution_status": ConflictResolutionStatus.UNRESOLVED,
                "created_at": self._now(),
                "resolved_at": None,
                "resolution_evidence_ids": (),
            }
            group = ConflictGroup(**payload, group_hash=content_hash(payload))
            connection.execute(
                "INSERT INTO conflict_groups VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    group.conflict_group_id,
                    group.subject_entity_id,
                    group.predicate_id,
                    group.resolution_status,
                    group.created_at,
                    group.group_hash,
                    canonical_json(group),
                ),
            )
            connection.executemany(
                "INSERT INTO conflict_group_claims VALUES (?, ?)",
                ((group.conflict_group_id, item) for item in group.claim_ids),
            )
            groups.append(group)
        return tuple(groups)

    def _matching_conflicts(
        self, connection: sqlite3.Connection, claims: list[ClaimRecord]
    ) -> tuple[ConflictGroup, ...]:
        ids = {item.claim_id for item in claims}
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""SELECT DISTINCT g.payload_json FROM conflict_groups g
                JOIN conflict_group_claims c ON c.conflict_group_id = g.conflict_group_id
                WHERE g.resolution_status = 'UNRESOLVED' AND c.claim_id IN ({placeholders})""",
            tuple(sorted(ids)),
        )
        return tuple(
            group
            for row in rows
            if len(ids & set((group := _conflict_from_json(row[0])).claim_ids)) >= 2
        )

    def _claim_answer(
        self,
        connection: sqlite3.Connection,
        claim: ClaimRecord,
        known_at: str,
        conflicted: bool,
    ) -> ClaimAnswer:
        evidence = tuple(
            self._evidence(connection, item) for item in claim.evidence_ids
        )
        sources = tuple(self._source(connection, item.source_id) for item in evidence)
        source_states = tuple(
            self._source_status_at(connection, item.source_id, known_at)
            for item in sources
        )
        transaction_to = self._claim_transaction_end(connection, claim.claim_id)
        return ClaimAnswer(
            claim_id=claim.claim_id,
            claim_hash=claim.canonical_claim_hash,
            value=claim.object_value,
            status=claim.status,
            valid_from=claim.valid_from,
            valid_to=claim.valid_to,
            recorded_at=claim.recorded_at,
            transaction_to=transaction_to,
            source_ids=tuple(sorted({item.source_id for item in sources})),
            source_hashes=tuple(sorted({item.record_hash for item in sources})),
            source_citations=tuple(
                {
                    "source_id": item.source_id,
                    "title": item.title,
                    "locator": item.locator,
                    "trust_tier": item.trust_tier,
                    "source_hash": item.record_hash,
                }
                for item in sorted(sources, key=lambda row: row.source_id)
            ),
            evidence_ids=claim.evidence_ids,
            evidence_hashes=tuple(sorted(item.evidence_hash for item in evidence)),
            source_trust_tiers=tuple(sorted({item.trust_tier for item in sources})),
            independent_source_family_count=len(
                {item.source_family for item in sources}
            ),
            evidence_count=len(evidence),
            freshness_state="CURRENT"
            if all(item == SourceStatus.ACTIVE for item in source_states)
            else "STALE",
            review_state="APPROVED",
            conflict_state="CONTESTED" if conflicted else "UNCONTESTED",
            source_retraction_state="AFFECTED"
            if SourceStatus.RETRACTED in source_states
            else "CLEAR",
        )

    def _build_answer(
        self,
        query: FactQuery,
        status: QueryStatus,
        snapshot: str,
        claims: tuple[ClaimAnswer, ...],
        conflict_ids: tuple[str, ...],
        warnings: tuple[str, ...],
    ) -> FactAnswerBundle:
        payload = {
            "query_id": query.query_id,
            "query_hash": query.query_hash,
            "fact_memory_schema_version": FACT_MEMORY_SCHEMA_VERSION,
            "memory_snapshot_hash": snapshot,
            "answer_status": status,
            "selected_claim_ids": tuple(item.claim_id for item in claims),
            "conflict_group_ids": conflict_ids,
            "claims": claims,
            "warnings": warnings,
            "generated_at": self._now(),
            "rendering_version": FACT_RENDERING_VERSION,
        }
        return FactAnswerBundle(**payload, answer_hash=content_hash(payload))

    def _empty_answer(
        self,
        query: FactQuery,
        status: QueryStatus,
        snapshot: str,
        warnings: tuple[str, ...] = (),
    ) -> FactAnswerBundle:
        with self.database.connect() as connection:
            return self._store_answer(
                connection,
                query,
                self._build_answer(query, status, snapshot, (), (), warnings),
            )

    def _store_answer(
        self,
        connection: sqlite3.Connection,
        query: FactQuery,
        bundle: FactAnswerBundle,
    ) -> FactAnswerBundle:
        # Queries are receipts, not state changes; an independent transaction keeps readers concurrent.
        connection.execute(
            "INSERT INTO fact_queries VALUES (?, ?, ?, ?, ?)",
            (
                query.query_id,
                query.query_hash,
                bundle.memory_snapshot_hash,
                query.created_at,
                canonical_json(query),
            ),
        )
        connection.execute(
            "INSERT INTO fact_answers VALUES (?, ?, ?, ?, ?, ?)",
            (
                bundle.answer_hash,
                query.query_id,
                query.query_hash,
                bundle.memory_snapshot_hash,
                bundle.generated_at,
                canonical_json(bundle),
            ),
        )
        failed = bundle.answer_status in {
            QueryStatus.INVALID_QUERY,
            QueryStatus.UNKNOWN_ENTITY,
            QueryStatus.UNKNOWN_PREDICATE,
            QueryStatus.AMBIGUOUS_ENTITY,
        }
        self.database.append_audit(
            connection,
            "FACT_QUERY_FAILED" if failed else "FACT_QUERY_EXECUTED",
            {
                "query_hash": query.query_hash,
                "snapshot_hash": bundle.memory_snapshot_hash,
                "answer_status": bundle.answer_status,
            },
            query.query_id,
            advance_snapshot=False,
        )
        self.database.append_audit(
            connection,
            "FACT_ANSWER_EMITTED",
            {
                "answer_hash": bundle.answer_hash,
                "claim_hashes": tuple(item.claim_hash for item in bundle.claims),
                "evidence_hashes": tuple(
                    digest for item in bundle.claims for digest in item.evidence_hashes
                ),
                "source_hashes": tuple(
                    digest for item in bundle.claims for digest in item.source_hashes
                ),
            },
            query.query_id,
            advance_snapshot=False,
        )
        connection.commit()
        return bundle

    def _claim_source_state(
        self, connection: sqlite3.Connection, claim: ClaimRecord, known_at: str
    ) -> str:
        states = {
            self._source_status_at(
                connection, self._evidence(connection, item).source_id, known_at
            )
            for item in claim.evidence_ids
        }
        if SourceStatus.ACTIVE in states:
            return "ACTIVE"
        if SourceStatus.RETRACTED in states:
            return "SOURCE_RETRACTED"
        return "UNAVAILABLE"

    def _claim_status_at(
        self, connection: sqlite3.Connection, claim_id: str, point: str
    ) -> ClaimStatus:
        row = connection.execute(
            """SELECT status FROM claim_status_events
               WHERE claim_id = ? AND recorded_at <= ?
               ORDER BY recorded_at DESC, rowid DESC LIMIT 1""",
            (claim_id, normalize_temporal(point)),
        ).fetchone()
        return ClaimStatus(row[0]) if row else ClaimStatus.PROPOSED

    def _source_status_at(
        self, connection: sqlite3.Connection, source_id: str, point: str
    ) -> SourceStatus:
        row = connection.execute(
            """SELECT status FROM source_status_events
               WHERE source_id = ? AND recorded_at <= ?
               ORDER BY recorded_at DESC, rowid DESC LIMIT 1""",
            (source_id, normalize_temporal(point)),
        ).fetchone()
        return SourceStatus(row[0]) if row else SourceStatus.ACTIVE

    def _claim_transaction_end(
        self, connection: sqlite3.Connection, claim_id: str
    ) -> str | None:
        row = connection.execute(
            """SELECT recorded_at FROM claim_status_events
               WHERE claim_id = ? AND status IN ('SUPERSEDED', 'RETRACTED')
               ORDER BY recorded_at LIMIT 1""",
            (claim_id,),
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _claim_evidence_at(
        connection: sqlite3.Connection, claim_id: str, point: str
    ) -> tuple[str, ...]:
        return tuple(
            row[0]
            for row in connection.execute(
                """SELECT evidence_id FROM claim_evidence
                   WHERE claim_id = ? AND attached_at <= ? ORDER BY evidence_id""",
                (claim_id, normalize_temporal(point)),
            )
        )

    def _attach_claim_evidence(
        self,
        connection: sqlite3.Connection,
        claim_id: str,
        evidence_ids: tuple[str, ...],
    ) -> None:
        attached_at = self._now()
        for evidence_id in evidence_ids:
            evidence = self._evidence(connection, evidence_id)
            payload = {
                "claim_id": claim_id,
                "evidence_id": evidence_id,
                "relation": evidence.relation,
                "attached_at": attached_at,
            }
            connection.execute(
                "INSERT OR IGNORE INTO claim_evidence VALUES (?, ?, ?, ?, ?)",
                (*payload.values(), content_hash(payload)),
            )

    def _insert_relation(self, connection: sqlite3.Connection, **payload: Any) -> None:
        row = {"relation_id": f"claim_relation_{uuid4().hex}", **payload}
        connection.execute(
            "INSERT INTO claim_relations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (*row.values(), content_hash(row)),
        )

    def _relation_reaches(
        self, connection: sqlite3.Connection, start: str, target: str
    ) -> bool:
        frontier = [start]
        visited = set()
        while frontier:
            current = frontier.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            frontier.extend(
                row[0]
                for row in connection.execute(
                    "SELECT target_claim_id FROM claim_relations WHERE source_claim_id = ? AND relation_type = 'SUPERSEDES'",
                    (current,),
                )
            )
        return False

    def _store_proposal(
        self, proposal: FactProposal, event: str, extra: dict[str, Any] | None = None
    ) -> None:
        with self.database.write() as connection:
            self._insert_proposal(connection, proposal)
            payload = {
                "proposal_hash": proposal.proposal_hash,
                "status": proposal.status,
            }
            if extra:
                payload.update(extra)
            self.database.append_audit(connection, event, payload, proposal.proposal_id)

    @staticmethod
    def _insert_proposal(
        connection: sqlite3.Connection, proposal: FactProposal
    ) -> None:
        connection.execute(
            "INSERT INTO proposals VALUES (?, ?, ?, ?, ?, ?)",
            (
                proposal.proposal_id,
                proposal.revision,
                proposal.status,
                proposal.proposal_hash,
                proposal.created_at,
                canonical_json(proposal),
            ),
        )

    def _proposal_revision(
        self, current: FactProposal, status: ProposalStatus
    ) -> FactProposal:
        payload = asdict(current)
        payload.update(
            revision=current.revision + 1, status=status, updated_at=self._now()
        )
        payload.pop("proposal_hash")
        payload["object_value"] = current.object_value
        payload["qualifiers"] = current.qualifiers
        payload["source"] = current.source
        return FactProposal(**payload, proposal_hash=content_hash(payload))

    def get_proposal(self, proposal_id: str) -> FactProposal:
        with self.database.connect() as connection:
            return self._latest_proposal(connection, proposal_id)

    @staticmethod
    def _entity_row(connection: sqlite3.Connection, entity_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown entity: {entity_id}")
        return row

    def _entity(self, connection: sqlite3.Connection, entity_id: str) -> EntityRecord:
        return _entity_from_json(
            self._entity_row(connection, entity_id)["payload_json"]
        )

    @staticmethod
    def _source_row(connection: sqlite3.Connection, source_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown source: {source_id}")
        return row

    def _source(self, connection: sqlite3.Connection, source_id: str) -> SourceRecord:
        return _source_from_json(
            self._source_row(connection, source_id)["payload_json"]
        )

    @staticmethod
    def _claim_row(connection: sqlite3.Connection, claim_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown claim: {claim_id}")
        return row

    def _claim(self, connection: sqlite3.Connection, claim_id: str) -> ClaimRecord:
        claim = _claim_from_json(self._claim_row(connection, claim_id)["payload_json"])
        evidence_ids = tuple(
            row[0]
            for row in connection.execute(
                "SELECT evidence_id FROM claim_evidence WHERE claim_id = ? ORDER BY evidence_id",
                (claim_id,),
            )
        )
        sources = tuple(
            self._source(connection, self._evidence(connection, item).source_id)
            for item in evidence_ids
        )
        status = self._claim_status_at(connection, claim_id, self._now())
        supersedes = tuple(
            row[0]
            for row in connection.execute(
                "SELECT target_claim_id FROM claim_relations WHERE source_claim_id = ? AND relation_type = 'SUPERSEDES' ORDER BY target_claim_id",
                (claim_id,),
            )
        )
        return replace(
            claim,
            status=(
                ClaimStatus.CORROBORATED
                if status == ClaimStatus.SUPPORTED
                and len({item.source_family for item in sources}) >= 2
                else status
            ),
            evidence_ids=evidence_ids,
            source_family_support_set=tuple(
                sorted({item.source_family for item in sources})
            ),
            supersedes_claim_ids=supersedes,
        )

    @staticmethod
    def _predicate(
        connection: sqlite3.Connection, predicate_id: str
    ) -> PredicateDefinition:
        row = connection.execute(
            "SELECT payload_json FROM predicate_definitions WHERE predicate_id = ? AND active = 1",
            (predicate_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown predicate: {predicate_id}")
        return _predicate_from_json(row[0])

    @staticmethod
    def _evidence(connection: sqlite3.Connection, evidence_id: str) -> EvidenceRecord:
        row = connection.execute(
            "SELECT payload_json FROM evidence WHERE evidence_id = ?", (evidence_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown evidence: {evidence_id}")
        return _evidence_from_json(row[0])

    @staticmethod
    def _latest_proposal(
        connection: sqlite3.Connection, proposal_id: str
    ) -> FactProposal:
        row = connection.execute(
            "SELECT payload_json FROM proposals WHERE proposal_id = ? ORDER BY revision DESC LIMIT 1",
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown proposal: {proposal_id}")
        return _proposal_from_json(row[0])

    @staticmethod
    def _approval(
        connection: sqlite3.Connection, approval_id: str
    ) -> FactApprovalEnvelope:
        row = connection.execute(
            "SELECT payload_json FROM approvals WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown approval: {approval_id}")
        return _approval_from_json(row[0])

    def _now(self) -> str:
        return normalize_datetime(self._clock())


def _canonical_claim_identity(proposal: FactProposal) -> dict[str, Any]:
    return {
        "subject_entity_id": proposal.subject_entity_id,
        "predicate_id": proposal.predicate_id,
        "object_value": proposal.object_value,
        "qualifiers": proposal.qualifiers,
        "valid_from": proposal.valid_from,
        "valid_to": proposal.valid_to,
    }


def _semantic_query_hash(query: FactQuery) -> str:
    payload = asdict(query)
    payload.pop("query_id")
    payload.pop("created_at")
    payload.pop("query_hash")
    return content_hash(payload)


def _status_event_values(
    claim_id: str,
    status: ClaimStatus,
    actor: str,
    reason: str | None,
    recorded_at: str,
) -> tuple[str, str, ClaimStatus, str, str | None, str, str]:
    payload = {
        "event_id": f"claim_status_{uuid4().hex}",
        "claim_id": claim_id,
        "status": status,
        "actor": actor,
        "reason": reason,
        "recorded_at": recorded_at,
    }
    return (*payload.values(), content_hash(payload))


def _intersection(
    first_start: str | None,
    first_end: str | None,
    second_start: str | None,
    second_end: str | None,
) -> tuple[str | None, str | None]:
    if not intervals_overlap(first_start, first_end, second_start, second_end):
        raise ValueError("intervals do not overlap")
    starts = [item for item in (first_start, second_start) if item is not None]
    ends = [item for item in (first_end, second_end) if item is not None]
    return (
        max(starts, key=temporal_key) if starts else None,
        min(ends, key=temporal_key) if ends else None,
    )


def _confidence_text(value: Decimal | str) -> str:
    if isinstance(value, (float, bool)):
        raise TypeError("extraction confidence must use Decimal or text")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("malformed extraction confidence") from error
    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        raise ValueError("extraction confidence must be finite and in [0, 1]")
    return format(parsed.normalize(), "f")


def _validate_id(value: str, field: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"invalid {field}")


def _unique_text(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("aliases must be non-empty text")
        normalized = normalize_label(value)
        if normalized not in seen:
            seen.add(normalized)
            result.append(value.strip())
    return tuple(result)


def _fact_values(row: dict[str, Any]) -> dict[str, FactValue]:
    return {key: FactValue.from_dict(value) for key, value in row.items()}


def _entity_from_json(payload: str) -> EntityRecord:
    row = json.loads(payload)
    row["aliases_ru"] = tuple(row["aliases_ru"])
    row["aliases_en"] = tuple(row["aliases_en"])
    row["provenance"] = tuple(row["provenance"])
    row["status"] = EntityStatus(row["status"])
    return EntityRecord(**row)


def _predicate_from_json(payload: str) -> PredicateDefinition:
    row = json.loads(payload)
    row["object_kind"] = FactValueKind(row["object_kind"])
    row["cardinality"] = Cardinality(row["cardinality"])
    row["temporal_mode"] = TemporalMode(row["temporal_mode"])
    row["allowed_qualifiers"] = {
        key: FactValueKind(value) for key, value in row["allowed_qualifiers"].items()
    }
    row["conflict_key_fields"] = tuple(row["conflict_key_fields"])
    return PredicateDefinition(**row)


def _source_from_json(payload: str) -> SourceRecord:
    row = json.loads(payload)
    row["source_kind"] = SourceKind(row["source_kind"])
    row["status"] = SourceStatus(row["status"])
    return SourceRecord(**row)


def _evidence_from_json(payload: str) -> EvidenceRecord:
    row = json.loads(payload)
    row["relation"] = EvidenceRelation(row["relation"])
    row["location_kind"] = EvidenceLocationKind(row["location_kind"])
    row["extraction_method"] = ExtractionMethod(row["extraction_method"])
    row["approval_status"] = ApprovalStatus(row["approval_status"])
    return EvidenceRecord(**row)


def _proposal_from_json(payload: str) -> FactProposal:
    row = json.loads(payload)
    row["source"] = ProposalSource(row["source"])
    row["status"] = ProposalStatus(row["status"])
    row["object_value"] = FactValue.from_dict(row["object_value"])
    row["qualifiers"] = _fact_values(row["qualifiers"])
    row["source_ids"] = tuple(row["source_ids"])
    row["evidence_ids"] = tuple(row["evidence_ids"])
    return FactProposal(**row)


def _approval_from_json(payload: str) -> FactApprovalEnvelope:
    row = json.loads(payload)
    row["decision"] = ApprovalDecision(row["decision"])
    row["source_hashes"] = tuple(row["source_hashes"])
    row["evidence_hashes"] = tuple(row["evidence_hashes"])
    return FactApprovalEnvelope(**row)


def _claim_from_json(payload: str) -> ClaimRecord:
    row = json.loads(payload)
    row["status"] = ClaimStatus(row["status"])
    row["object_value"] = FactValue.from_dict(row["object_value"])
    row["qualifiers"] = _fact_values(row["qualifiers"])
    row["evidence_ids"] = tuple(row["evidence_ids"])
    row["source_family_support_set"] = tuple(row["source_family_support_set"])
    row["supersedes_claim_ids"] = tuple(row["supersedes_claim_ids"])
    return ClaimRecord(**row)


def _conflict_from_json(payload: str) -> ConflictGroup:
    row = json.loads(payload)
    row["claim_ids"] = tuple(row["claim_ids"])
    row["overlapping_interval"] = tuple(row["overlapping_interval"])
    row["resolution_status"] = ConflictResolutionStatus(row["resolution_status"])
    row["resolution_evidence_ids"] = tuple(row["resolution_evidence_ids"])
    return ConflictGroup(**row)
