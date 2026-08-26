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
    ActorIdentityType,
    ApprovalDecision,
    ApprovalStatus,
    Cardinality,
    ClaimAnswer,
    ClaimRecord,
    ClaimState,
    ClaimStatus,
    ConflictGroup,
    ConflictResolutionEvent,
    ConflictResolutionIntegrityStatus,
    ConflictResolutionKind,
    ConflictResolutionStatus,
    EntityRecord,
    EntityResolution,
    EntityResolutionStatus,
    EntityStatus,
    EvidenceConflictState,
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
    ProvenanceDetailMode,
    QueryStatus,
    ReplayStatus,
    ResolutionEvidenceLink,
    ResolutionEvidenceRole,
    SourceKind,
    SourceRecord,
    SourceState,
    SourceStatus,
    TemporalMode,
    TransactionIntervalState,
)
from ai_brain.stage2.facts.persistence import FactDatabase, FactMemoryIntegrityError
from ai_brain.stage2.facts.sources import SourceIntegrityError, extract_evidence
from ai_brain.stage2.facts.values import FactValue, FactValueKind
from ai_brain.stage2.facts.version import (
    FACT_ANSWER_SCHEMA_VERSION,
    FACT_APPROVAL_POLICY_VERSION,
    FACT_CONFLICT_POLICY_VERSION,
    FACT_MEMORY_SCHEMA_VERSION,
    FACT_RENDERING_VERSION,
)

_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_RESERVED_MODEL_IDENTITIES = {"ai", "assistant", "model", "self"}
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
        reviewer_identity_type: ActorIdentityType | str | None = None,
        approved: bool = False,
        evidence_id: str | None = None,
    ) -> EvidenceRecord:
        identifier = evidence_id or f"ev_{uuid4().hex}"
        _validate_id(identifier, "evidence_id")
        method = ExtractionMethod(extraction_method)
        confidence = _confidence_text(extraction_confidence)
        if approved:
            reviewer, actor_type = self._trusted_actor(
                reviewer,
                reviewer_identity_type,
                purpose="evidence review",
            )
        else:
            actor_type = _parse_actor_type(reviewer_identity_type)
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
            "reviewer_identity_type": actor_type,
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
                "CONTRADICTING_EVIDENCE_ATTACHED"
                if record.relation == EvidenceRelation.CONTRADICTS
                else "EVIDENCE_ADDED",
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
        interpreted_hash = content_hash(payload)
        if interpreted_hash != digest:
            with self.database.connect() as connection:
                migrated = self._migration_hash_allows(
                    connection,
                    "evidence",
                    evidence.evidence_id,
                    digest,
                    interpreted_hash,
                )
            if not migrated:
                raise SourceIntegrityError("evidence record hash mismatch")
        if require_approved and evidence.approval_status != ApprovalStatus.APPROVED:
            raise FactApprovalError(
                "unapproved evidence cannot support a trusted claim"
            )
        if require_approved and (
            not evidence.reviewer
            or evidence.reviewer_identity_type in {None, ActorIdentityType.MODEL}
        ):
            raise FactApprovalError("approved evidence lacks an independent reviewer")
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
            "reviewer_identity": None,
            "reviewer_identity_type": None,
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
        reviewer_identity_type: ActorIdentityType | str | None = None,
    ) -> FactProposal:
        requested = ProposalStatus(target)
        with self.database.connect() as connection:
            current = self._latest_proposal(connection, proposal_id)
        actor_type = current.reviewer_identity_type
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
        elif requested == ProposalStatus.REVIEWED:
            reviewer, actor_type = self._trusted_actor(
                reviewer,
                reviewer_identity_type,
                purpose="proposal review",
            )
        elif requested in {ProposalStatus.APPROVED, ProposalStatus.COMMITTED}:
            raise FactWorkflowError(
                "use approve_proposal/commit_proposal for trusted transitions"
            )
        proposal = self._proposal_revision(
            current,
            requested,
            reviewer_identity=reviewer
            if requested == ProposalStatus.REVIEWED
            else current.reviewer_identity,
            reviewer_identity_type=actor_type
            if requested == ProposalStatus.REVIEWED
            else current.reviewer_identity_type,
        )
        event = {
            ProposalStatus.PARSED: "CLAIM_PARSED",
            ProposalStatus.EVIDENCE_ATTACHED: "CLAIM_EVIDENCE_ATTACHED",
            ProposalStatus.VALIDATED: "CLAIM_VALIDATED",
            ProposalStatus.REVIEWED: "CLAIM_REVIEWED",
        }.get(requested, "CLAIM_PROPOSAL_TERMINATED")
        self._store_proposal(
            proposal,
            event,
            extra={
                "reviewer": reviewer,
                "reviewer_identity_type": actor_type,
            }
            if requested == ProposalStatus.REVIEWED
            else None,
        )
        return proposal

    def prepare_for_review(
        self,
        proposal_id: str,
        *,
        reviewer: str,
        reviewer_identity_type: ActorIdentityType | str,
    ) -> FactProposal:
        current = self.get_proposal(proposal_id)
        while current.status != ProposalStatus.REVIEWED:
            if current.status == ProposalStatus.VALIDATED:
                current = self.advance_proposal(
                    current.proposal_id,
                    ProposalStatus.REVIEWED,
                    reviewer=reviewer,
                    reviewer_identity_type=reviewer_identity_type,
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
        reviewer_identity_type: ActorIdentityType | str,
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
        reviewer_identity, actor_type = self._trusted_actor(
            reviewer_identity,
            reviewer_identity_type,
            purpose="claim approval",
        )
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
        supporting = tuple(
            item for item in evidence if item.relation == EvidenceRelation.SUPPORTS
        )
        non_model_support = tuple(
            item
            for item in supporting
            if next(
                source for source in sources if source.source_id == item.source_id
            ).source_kind
            != SourceKind.MODEL_INFERENCE
        )
        if not non_model_support:
            self._audit_rejection(
                "MODEL_SOURCE_REQUIRES_INDEPENDENT_SUPPORT",
                proposal.proposal_id,
                {"proposal_hash": proposal.proposal_hash},
            )
            raise FactApprovalError(
                "trusted claim requires independently approved non-model support"
            )
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
            "reviewer_identity_type": actor_type,
            "supporting_evidence_hashes": tuple(
                sorted(item.evidence_hash for item in supporting)
            ),
            "independent_non_model_support": True,
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
                    "CLAIM_EVIDENCE_MERGED",
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
            evidence = tuple(
                self._evidence(connection, item) for item in proposal.evidence_ids
            )
            supporting = tuple(
                item for item in evidence if item.relation == EvidenceRelation.SUPPORTS
            )
            contradicting = tuple(
                item
                for item in evidence
                if item.relation == EvidenceRelation.CONTRADICTS
            )
            supporting_sources = tuple(
                self._source(connection, item.source_id) for item in supporting
            )
            contradicting_sources = tuple(
                self._source(connection, item.source_id) for item in contradicting
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
                "supporting_evidence_ids": tuple(
                    sorted(item.evidence_id for item in supporting)
                ),
                "contradicting_evidence_ids": tuple(
                    sorted(item.evidence_id for item in contradicting)
                ),
                "source_family_support_set": tuple(
                    sorted(
                        {
                            item.source_family
                            for item in supporting_sources
                            if item.source_kind != SourceKind.MODEL_INFERENCE
                        }
                    )
                ),
                "source_family_contradiction_set": tuple(
                    sorted({item.source_family for item in contradicting_sources})
                ),
                "supersedes_claim_ids": (),
                "retraction_reason": None,
                "proposal_hash": proposal.proposal_hash,
                "approval_hash": approval.approval_hash,
                "canonical_claim_hash": canonical_claim_hash,
                "schema_version": FACT_MEMORY_SCHEMA_VERSION,
            }
            payload["claim_record_hash"] = content_hash(payload)
            claim = ClaimRecord(**payload)
            connection.execute(
                """INSERT INTO claims(
                    claim_id, subject_entity_id, predicate_id, object_hash,
                    qualifier_hash, valid_from_key, valid_to_key, recorded_at,
                    base_status, canonical_claim_hash, claim_record_hash,
                    proposal_hash, approval_hash,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    claim.claim_record_hash,
                    claim.proposal_hash,
                    claim.approval_hash,
                    canonical_json(claim),
                ),
            )
            self._attach_claim_evidence(connection, claim_id, proposal.evidence_ids)
            connection.execute(
                "INSERT INTO claim_status_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                _status_event_values(
                    claim_id,
                    status,
                    "FACT_MEMORY",
                    ActorIdentityType.TRUSTED_PROCESS,
                    None,
                    claim.recorded_at,
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
            if contradicting:
                self.database.append_audit(
                    connection,
                    "CLAIM_EVIDENCE_CONTESTED",
                    {
                        "claim_hash": claim.canonical_claim_hash,
                        "contradicting_evidence_hashes": tuple(
                            sorted(item.evidence_hash for item in contradicting)
                        ),
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
        actor_identity_type: ActorIdentityType | str,
        reason: str,
    ) -> None:
        actor, actor_type = self._trusted_actor(
            actor,
            actor_identity_type,
            purpose="claim supersession",
        )
        if old_claim_id == new_claim_id:
            raise ValueError("claim cannot supersede itself")
        with self.database.write() as connection:
            old_claim = self._claim(connection, old_claim_id)
            new_claim = self._claim(connection, new_claim_id)
            if self._relation_reaches(connection, old_claim_id, new_claim_id):
                raise ValueError("supersession cycle detected")
            self._validate_supersession_domain(connection, old_claim, new_claim)
            recorded_at = self._now()
            self._insert_relation(
                connection,
                source_claim_id=new_claim_id,
                target_claim_id=old_claim_id,
                relation_type="SUPERSEDES",
                actor=actor,
                actor_identity_type=actor_type,
                reason=reason,
                recorded_at=recorded_at,
            )
            connection.execute(
                "INSERT INTO claim_status_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                _status_event_values(
                    old_claim_id,
                    ClaimStatus.SUPERSEDED,
                    actor,
                    actor_type,
                    reason,
                    recorded_at,
                ),
            )
            self._resolve_conflicts_for_claim_event(
                connection,
                old_claim_id,
                ConflictResolutionKind.CLAIM_SUPERSEDED,
                actor,
                actor_type,
                reason,
                recorded_at,
                selected_claim_ids=(new_claim_id,),
            )
            self.database.append_audit(
                connection,
                "CLAIM_SUPERSEDED",
                {"new_claim_id": new_claim_id, "reason_hash": content_hash(reason)},
                old_claim_id,
            )

    def retract_claim(
        self,
        claim_id: str,
        *,
        actor: str,
        actor_identity_type: ActorIdentityType | str,
        reason: str,
    ) -> None:
        if not reason.strip():
            raise ValueError("retraction reason is required")
        actor, actor_type = self._trusted_actor(
            actor,
            actor_identity_type,
            purpose="claim retraction",
        )
        with self.database.write() as connection:
            self._claim_row(connection, claim_id)
            recorded_at = self._now()
            connection.execute(
                "INSERT INTO claim_status_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                _status_event_values(
                    claim_id,
                    ClaimStatus.RETRACTED,
                    actor,
                    actor_type,
                    reason,
                    recorded_at,
                ),
            )
            self._resolve_conflicts_for_claim_event(
                connection,
                claim_id,
                ConflictResolutionKind.CLAIM_RETRACTED,
                actor,
                actor_type,
                reason,
                recorded_at,
            )
            self.database.append_audit(
                connection,
                "CLAIM_RETRACTED",
                {"actor": actor, "reason_hash": content_hash(reason)},
                claim_id,
            )

    def retract_source(
        self,
        source_id: str,
        *,
        actor: str,
        actor_identity_type: ActorIdentityType | str,
        reason: str,
    ) -> None:
        self.set_source_status(
            source_id,
            status=SourceStatus.RETRACTED,
            actor=actor,
            actor_identity_type=actor_identity_type,
            reason=reason,
        )

    def set_source_status(
        self,
        source_id: str,
        *,
        status: SourceStatus | str,
        actor: str,
        actor_identity_type: ActorIdentityType | str,
        reason: str,
    ) -> None:
        if not reason.strip():
            raise ValueError("source status reason is required")
        selected = SourceStatus(status)
        actor, actor_type = self._trusted_actor(
            actor,
            actor_identity_type,
            purpose="source status change",
        )
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
                "actor_identity_type": actor_type,
                "reason": reason,
                "recorded_at": recorded_at,
            }
            event_hash = content_hash(payload)
            connection.execute(
                "INSERT INTO source_status_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (*payload.values(), event_hash),
            )
            self.database.append_audit(
                connection,
                "SOURCE_RETRACTED"
                if selected == SourceStatus.RETRACTED
                else "SOURCE_UNAVAILABLE",
                {
                    "actor": actor,
                    "actor_identity_type": actor_type,
                    "reason_hash": content_hash(reason),
                },
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
        now = self._now()
        payload = {
            "query_id": f"fact_query_{uuid4().hex}",
            "subject": subject,
            "predicate_id": predicate_id,
            "object_filter": object_filter,
            "qualifier_filters": dict(sorted((qualifier_filters or {}).items())),
            "valid_at": normalize_temporal(valid_at_value),
            "known_at": normalize_temporal(known_at) or now,
            "known_at_explicitly_requested": known_at is not None,
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
            "created_at": now,
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
                supporting, contradicting = self._claim_evidence_by_polarity_at(
                    connection,
                    claim.claim_id,
                    known_point,
                )
                evidence_ids = tuple(
                    sorted(item.evidence_id for item in (*supporting, *contradicting))
                )
                supporting_sources = tuple(
                    self._source(connection, item.source_id) for item in supporting
                )
                contradicting_sources = tuple(
                    self._source(connection, item.source_id) for item in contradicting
                )
                status = self._claim_status_at(connection, claim.claim_id, known_point)
                active_supporting_sources = tuple(
                    item
                    for item in supporting_sources
                    if self._source_status_at(connection, item.source_id, known_point)
                    == SourceStatus.ACTIVE
                    and item.source_kind != SourceKind.MODEL_INFERENCE
                )
                families = {item.source_family for item in active_supporting_sources}
                if status == ClaimStatus.SUPPORTED and len(families) >= 2:
                    status = ClaimStatus.CORROBORATED
                claim = replace(
                    claim,
                    status=status,
                    evidence_ids=evidence_ids,
                    supporting_evidence_ids=tuple(
                        item.evidence_id for item in supporting
                    ),
                    contradicting_evidence_ids=tuple(
                        item.evidence_id for item in contradicting
                    ),
                    source_family_support_set=tuple(sorted(families)),
                    source_family_contradiction_set=tuple(
                        sorted({item.source_family for item in contradicting_sources})
                    ),
                )
                source_state = self._claim_support_state(
                    connection,
                    supporting_sources,
                    known_point,
                )
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
            conflicts = self._matching_conflicts(
                connection,
                conflict_pool,
                known_point,
            )
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
            resolved_history = self._resolved_conflict_history(
                connection,
                conflict_pool,
                known_point,
            )
            for group in resolved_history:
                event = self._conflict_resolution_event_at(
                    connection,
                    group.conflict_group_id,
                    known_point,
                )
                if event is None:
                    continue
                allowed = set(event.remaining_claim_ids)
                visible = [
                    item
                    for item in visible
                    if item.claim_id not in set(group.claim_ids)
                    or item.claim_id in allowed
                ]
            if not visible:
                return self._store_answer(
                    connection,
                    query,
                    self._build_answer(
                        query,
                        QueryStatus.NO_FACT,
                        snapshot,
                        (),
                        (),
                        ("RESOLUTION_HAS_NO_VISIBLE_CLAIMS",),
                    ),
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
                if resolved_history:
                    warnings += ("RESOLVED_CONFLICT_HISTORY",)
            answers = tuple(
                self._claim_answer(
                    connection,
                    claim,
                    known_point,
                    bool(conflicts),
                    include_details=query.include_evidence,
                )
                for claim in visible
            )
            if any(
                item.evidence_conflict_state == EvidenceConflictState.CONTESTED
                for item in answers
            ):
                warnings += ("CONTRADICTING_EVIDENCE_PRESENT",)
            if not query.include_evidence:
                warnings += ("EVIDENCE_DETAILS_OMITTED",)
            bundle = self._build_answer(
                query,
                status,
                snapshot,
                answers,
                tuple(item.conflict_group_id for item in conflicts),
                warnings,
                conflict_resolution_statuses=tuple(
                    (item.conflict_group_id, ConflictResolutionStatus.UNRESOLVED)
                    for item in conflicts
                )
                + tuple(
                    (item.conflict_group_id, ConflictResolutionStatus.RESOLVED)
                    for item in resolved_history
                ),
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
            evidence_attachments = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM claim_evidence WHERE claim_id = ? ORDER BY attached_at, evidence_id",
                    (claim_id,),
                )
            ]
            conflict_resolution_events = [
                json.loads(row[0])
                for row in connection.execute(
                    """SELECT e.payload_json FROM conflict_resolution_events e
                       JOIN conflict_group_claims c
                         ON c.conflict_group_id = e.conflict_group_id
                       WHERE c.claim_id = ? ORDER BY e.recorded_at, e.event_id""",
                    (claim_id,),
                )
            ]
        return {
            "claim": asdict(claim),
            "status_events": states,
            "relations": relations,
            "evidence_attachments": evidence_attachments,
            "conflict_resolution_events": conflict_resolution_events,
        }

    def get_claim_record(self, claim_id: str) -> ClaimRecord:
        with self.database.connect() as connection:
            return self._claim_record(connection, claim_id)

    def get_claim_state(self, claim_id: str) -> ClaimState:
        return self.get_claim_state_at(claim_id, self._now())

    def get_claim_state_at(self, claim_id: str, known_at: str) -> ClaimState:
        point = normalize_temporal(known_at)
        if point is None:
            raise ValueError("known_at is required")
        with self.database.connect() as connection:
            record = self._claim_record(connection, claim_id)
            supporting, contradicting = self._claim_evidence_by_polarity_at(
                connection,
                claim_id,
                point,
            )
            transaction = self.transaction_interval_as_known_at(
                claim_id,
                point,
                connection=connection,
            )
            supporting_families = {
                source.source_family
                for evidence in supporting
                if (source := self._source(connection, evidence.source_id)).source_kind
                != SourceKind.MODEL_INFERENCE
                and self._source_status_at(connection, source.source_id, point)
                == SourceStatus.ACTIVE
            }
            derived_status = transaction.status
            if (
                derived_status == ClaimStatus.SUPPORTED
                and len(supporting_families) >= 2
            ):
                derived_status = ClaimStatus.CORROBORATED
            return ClaimState(
                record=record,
                status=derived_status,
                transaction=transaction,
                supporting_evidence_ids=tuple(item.evidence_id for item in supporting),
                contradicting_evidence_ids=tuple(
                    item.evidence_id for item in contradicting
                ),
                evidence_conflict_state=EvidenceConflictState.CONTESTED
                if contradicting
                else EvidenceConflictState.CLEAR,
            )

    def get_claim(self, claim_id: str) -> ClaimRecord:
        """Compatibility alias returning the explicit current projection."""
        with self.database.connect() as connection:
            return self._claim(connection, claim_id)

    def get_source_record(self, source_id: str) -> SourceRecord:
        with self.database.connect() as connection:
            return self._source(connection, source_id)

    def get_source_state_at(self, source_id: str, known_at: str) -> SourceState:
        point = normalize_temporal(known_at)
        if point is None:
            raise ValueError("known_at is required")
        with self.database.connect() as connection:
            record = self._source(connection, source_id)
            status, event_hash = self._source_status_projection(
                connection,
                source_id,
                point,
            )
            return SourceState(
                record=record,
                status=status,
                known_at=point,
                status_event_hash=event_hash,
            )

    def get_source_at(self, source_id: str, known_at: str) -> SourceRecord:
        state = self.get_source_state_at(source_id, known_at)
        return replace(state.record, status=state.status)

    def get_source(self, source_id: str) -> SourceRecord:
        return self.get_source_at(source_id, self._now())

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
        return self.conflicts_at(self._now(), unresolved_only=unresolved_only)

    def conflicts_at(
        self,
        known_at: str,
        *,
        unresolved_only: bool = True,
    ) -> tuple[ConflictGroup, ...]:
        point = normalize_temporal(known_at)
        if point is None:
            raise ValueError("known_at is required")
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM conflict_groups WHERE created_at <= ? ORDER BY created_at, conflict_group_id",
                (point,),
            )
            projected = tuple(
                self._conflict_as_known_at(
                    connection,
                    _conflict_from_json(row[0]),
                    point,
                )
                for row in rows
            )
            return tuple(
                item
                for item in projected
                if not unresolved_only
                or item.resolution_status == ConflictResolutionStatus.UNRESOLVED
            )

    def resolve_conflict(
        self,
        conflict_group_id: str,
        *,
        resolution_kind: ConflictResolutionKind | str,
        selected_claim_ids: tuple[str, ...] | list[str],
        remaining_claim_ids: tuple[str, ...] | list[str],
        evidence_ids: tuple[str, ...] | list[str],
        evidence_links: tuple[ResolutionEvidenceLink, ...]
        | list[ResolutionEvidenceLink]
        | None = None,
        actor_identity: str,
        actor_identity_type: ActorIdentityType | str,
        reason: str,
    ) -> ConflictResolutionEvent:
        kind = ConflictResolutionKind(resolution_kind)
        if kind not in {
            ConflictResolutionKind.MANUAL_RESOLUTION,
            ConflictResolutionKind.DISMISSED_AS_NOT_CONFLICTING,
        }:
            raise FactApprovalError(
                "claim retraction/supersession resolutions require their reviewed claim event"
            )
        actor_identity, actor_type = self._trusted_actor(
            actor_identity,
            actor_identity_type,
            purpose="conflict resolution",
        )
        if not reason.strip() or not evidence_ids:
            self._audit_rejection(
                "CONFLICT_RESOLUTION_REJECTED",
                conflict_group_id,
                {"reason": "resolution requires evidence and reason"},
            )
            raise FactApprovalError("manual conflict resolution requires evidence")
        for evidence_id in evidence_ids:
            self.verify_evidence(evidence_id, require_approved=True)
        with self.database.write() as connection:
            row = connection.execute(
                "SELECT payload_json FROM conflict_groups WHERE conflict_group_id = ?",
                (conflict_group_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown conflict group: {conflict_group_id}")
            group = self._conflict_as_known_at(
                connection,
                _conflict_from_json(row[0]),
                self._now(),
            )
            if group.resolution_status != ConflictResolutionStatus.UNRESOLVED:
                raise FactWorkflowError("conflict is already resolved")
            selected = tuple(sorted(set(selected_claim_ids)))
            remaining = tuple(sorted(set(remaining_claim_ids)))
            group_claims = set(group.claim_ids)
            if not {*selected, *remaining} <= group_claims:
                raise ValueError("resolution claims must belong to the conflict group")
            if kind == ConflictResolutionKind.MANUAL_RESOLUTION:
                if not remaining:
                    raise ValueError("manual resolution must retain at least one claim")
                if selected != remaining:
                    raise ValueError(
                        "manual resolution selected claims must equal remaining claims"
                    )
            elif selected != tuple(sorted(group_claims)) or remaining != tuple(
                sorted(group_claims)
            ):
                raise ValueError(
                    "dismissal must retain and select every conflict claim"
                )
            links = self._resolution_evidence_links(
                connection,
                group,
                kind,
                remaining,
                tuple(sorted(set(evidence_ids))),
                tuple(evidence_links or ()),
            )
            self.database.append_audit(
                connection,
                "CONFLICT_RESOLUTION_PROPOSED",
                {
                    "kind": kind,
                    "evidence_hashes": tuple(
                        sorted(
                            self._evidence(connection, item).evidence_hash
                            for item in evidence_ids
                        )
                    ),
                },
                conflict_group_id,
            )
            event = self._insert_conflict_resolution_event(
                connection,
                group,
                kind=kind,
                new_status=ConflictResolutionStatus.RESOLVED,
                actor_identity=actor_identity,
                actor_identity_type=actor_type,
                reason=reason,
                evidence_ids=tuple(sorted(set(evidence_ids))),
                evidence_links=links,
                selected_claim_ids=selected,
                remaining_claim_ids=remaining,
                recorded_at=self._now(),
            )
            self.database.append_audit(
                connection,
                "CONFLICT_RESOLVED",
                {"resolution_event_hash": event.event_hash, "kind": kind},
                conflict_group_id,
            )
            return event

    def replay_answer(self, bundle: FactAnswerBundle) -> ReplayStatus:
        if (
            bundle.fact_memory_schema_version != FACT_MEMORY_SCHEMA_VERSION
            or bundle.answer_schema_version != FACT_ANSWER_SCHEMA_VERSION
            or bundle.rendering_version != FACT_RENDERING_VERSION
        ):
            raise FactMemoryIntegrityError(
                "answer receipt requires explicit schema-v2 re-query"
            )
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

    @staticmethod
    def _validate_supersession_domain(
        connection: sqlite3.Connection,
        old_claim: ClaimRecord,
        new_claim: ClaimRecord,
    ) -> None:
        if (
            old_claim.subject_entity_id != new_claim.subject_entity_id
            or old_claim.predicate_id != new_claim.predicate_id
        ):
            raise ValueError("supersession claims must share subject and predicate")
        predicate = FactMemory._predicate(connection, old_claim.predicate_id)
        if old_claim.object_value.kind != new_claim.object_value.kind:
            raise ValueError("supersession claims have incompatible value kinds")
        if any(
            old_claim.qualifiers.get(field) != new_claim.qualifiers.get(field)
            for field in predicate.conflict_key_fields
        ):
            raise ValueError("supersession claims have different conflict qualifiers")
        if new_claim.status in {ClaimStatus.RETRACTED, ClaimStatus.SUPERSEDED}:
            raise ValueError("inactive claim cannot supersede another claim")
        if (
            old_claim.valid_from is not None
            and new_claim.valid_to is not None
            and temporal_key(new_claim.valid_to) < temporal_key(old_claim.valid_from)
        ):
            raise ValueError(
                "supersession cannot replace a later claim with an older interval"
            )

    def _resolution_evidence_links(
        self,
        connection: sqlite3.Connection,
        group: ConflictGroup,
        kind: ConflictResolutionKind,
        remaining: tuple[str, ...],
        evidence_ids: tuple[str, ...],
        supplied: tuple[ResolutionEvidenceLink, ...],
    ) -> tuple[ResolutionEvidenceLink, ...]:
        group_claims = set(group.claim_ids)
        retained = set(remaining)
        removed = group_claims - retained
        links: list[ResolutionEvidenceLink] = []
        if supplied:
            for item in supplied:
                if not isinstance(item, ResolutionEvidenceLink):
                    raise TypeError("resolution evidence links must be typed")
                body = {
                    "evidence_id": item.evidence_id,
                    "claim_id": item.claim_id,
                    "role": item.role,
                }
                if content_hash(body) != item.link_hash:
                    raise FactApprovalError("resolution evidence link hash mismatch")
                links.append(item)
        else:
            for evidence_id in evidence_ids:
                candidates = tuple(
                    connection.execute(
                        """SELECT claim_id, relation FROM claim_evidence
                           WHERE evidence_id = ? ORDER BY claim_id""",
                        (evidence_id,),
                    )
                )
                selected: tuple[str, ResolutionEvidenceRole] | None = None
                for row in candidates:
                    claim_id = str(row["claim_id"])
                    relation = EvidenceRelation(row["relation"])
                    if claim_id not in group_claims:
                        continue
                    if kind == ConflictResolutionKind.DISMISSED_AS_NOT_CONFLICTING:
                        if relation == EvidenceRelation.SUPPORTS:
                            selected = (
                                claim_id,
                                ResolutionEvidenceRole.SUPPORTS_DISMISSAL,
                            )
                            break
                    elif claim_id in retained and relation == EvidenceRelation.SUPPORTS:
                        selected = (
                            claim_id,
                            ResolutionEvidenceRole.SUPPORTS_REMAINING,
                        )
                        break
                    elif (
                        claim_id in removed and relation == EvidenceRelation.CONTRADICTS
                    ):
                        selected = (
                            claim_id,
                            ResolutionEvidenceRole.CONTRADICTS_REMOVED,
                        )
                        break
                if selected is None:
                    raise FactApprovalError(
                        "resolution evidence is unrelated to the conflict partition"
                    )
                body = {
                    "evidence_id": evidence_id,
                    "claim_id": selected[0],
                    "role": selected[1],
                }
                links.append(
                    ResolutionEvidenceLink(**body, link_hash=content_hash(body))
                )
        if {item.evidence_id for item in links} != set(evidence_ids):
            raise FactApprovalError(
                "resolution evidence links do not bind all evidence"
            )
        for link in links:
            if link.claim_id not in group_claims:
                raise FactApprovalError(
                    "resolution evidence claim is outside the group"
                )
            row = connection.execute(
                """SELECT relation FROM claim_evidence
                   WHERE claim_id = ? AND evidence_id = ?""",
                (link.claim_id, link.evidence_id),
            ).fetchone()
            if row is None:
                raise FactApprovalError(
                    "resolution evidence is not attached to its claim"
                )
            relation = EvidenceRelation(row[0])
            valid = (
                (
                    link.role == ResolutionEvidenceRole.SUPPORTS_REMAINING
                    and link.claim_id in retained
                    and relation == EvidenceRelation.SUPPORTS
                )
                or (
                    link.role == ResolutionEvidenceRole.CONTRADICTS_REMOVED
                    and link.claim_id in removed
                    and relation == EvidenceRelation.CONTRADICTS
                )
                or (
                    link.role == ResolutionEvidenceRole.SUPPORTS_DISMISSAL
                    and kind == ConflictResolutionKind.DISMISSED_AS_NOT_CONFLICTING
                    and relation == EvidenceRelation.SUPPORTS
                )
            )
            if not valid:
                raise FactApprovalError(
                    "resolution evidence role or polarity is invalid"
                )
        if kind == ConflictResolutionKind.MANUAL_RESOLUTION:
            directly_justified = {
                item.claim_id
                for item in links
                if item.role == ResolutionEvidenceRole.CONTRADICTS_REMOVED
            }
            supported_retained = {
                item.claim_id
                for item in links
                if item.role == ResolutionEvidenceRole.SUPPORTS_REMAINING
            }
            removed_links = tuple(
                item
                for item in links
                if item.role == ResolutionEvidenceRole.CONTRADICTS_REMOVED
            )
            if (
                supported_retained != retained
                or directly_justified != removed
                or len({item.evidence_id for item in removed_links})
                != len(removed_links)
            ):
                raise FactApprovalError(
                    "resolution evidence must justify every retained and removed side"
                )
        if kind == ConflictResolutionKind.DISMISSED_AS_NOT_CONFLICTING:
            dismissal_supported = {
                item.claim_id
                for item in links
                if item.role == ResolutionEvidenceRole.SUPPORTS_DISMISSAL
            }
            if dismissal_supported != group_claims:
                raise FactApprovalError(
                    "dismissal evidence must support every retained claim"
                )
        return tuple(
            sorted(links, key=lambda item: (item.claim_id, item.evidence_id, item.role))
        )

    @staticmethod
    def _verify_resolution_evidence_links(connection: sqlite3.Connection) -> None:
        rows = tuple(connection.execute("SELECT * FROM resolution_evidence_links"))
        for row in rows:
            body = {
                "evidence_id": row["evidence_id"],
                "claim_id": row["claim_id"],
                "role": ResolutionEvidenceRole(row["role"]),
            }
            if content_hash(body) != row["link_hash"]:
                raise FactMemoryIntegrityError("resolution evidence link hash mismatch")
            relation_row = connection.execute(
                """SELECT relation FROM claim_evidence
                   WHERE claim_id = ? AND evidence_id = ?""",
                (row["claim_id"], row["evidence_id"]),
            ).fetchone()
            if relation_row is None:
                raise FactMemoryIntegrityError("resolution evidence link is detached")
            role = ResolutionEvidenceRole(row["role"])
            relation = EvidenceRelation(relation_row[0])
            if (
                role
                in {
                    ResolutionEvidenceRole.SUPPORTS_REMAINING,
                    ResolutionEvidenceRole.SUPPORTS_DISMISSAL,
                }
                and relation != EvidenceRelation.SUPPORTS
            ) or (
                role == ResolutionEvidenceRole.CONTRADICTS_REMOVED
                and relation != EvidenceRelation.CONTRADICTS
            ):
                raise FactMemoryIntegrityError("resolution evidence polarity changed")
        by_event: dict[str, set[tuple[str, str, str, str]]] = {}
        for row in rows:
            by_event.setdefault(str(row["event_id"]), set()).add(
                (
                    str(row["evidence_id"]),
                    str(row["claim_id"]),
                    str(row["role"]),
                    str(row["link_hash"]),
                )
            )
        for row in connection.execute(
            "SELECT event_id, conflict_group_id, payload_json FROM conflict_resolution_events"
        ):
            payload = json.loads(row["payload_json"])
            event = _conflict_resolution_from_json(row["payload_json"])
            payload_links = {
                (
                    str(item["evidence_id"]),
                    str(item["claim_id"]),
                    str(item["role"]),
                    str(item["link_hash"]),
                )
                for item in payload.get("evidence_links", ())
            }
            if payload_links != by_event.get(str(row["event_id"]), set()):
                raise FactMemoryIntegrityError(
                    "resolution event and evidence links differ"
                )
            group_claims = {
                str(item[0])
                for item in connection.execute(
                    "SELECT claim_id FROM conflict_group_claims WHERE conflict_group_id = ?",
                    (row["conflict_group_id"],),
                )
            }
            remaining = set(payload.get("remaining_claim_ids", ()))
            selected = set(payload.get("selected_claim_ids", ()))
            if not selected <= group_claims or not remaining <= group_claims:
                raise FactMemoryIntegrityError(
                    "conflict resolution contains a foreign claim"
                )
            if event.integrity_status == ConflictResolutionIntegrityStatus.VERIFIED_V4:
                if event.policy_version != FACT_CONFLICT_POLICY_VERSION:
                    raise FactMemoryIntegrityError(
                        "conflict resolution policy version is incompatible"
                    )
                if event.resolution_kind == ConflictResolutionKind.MANUAL_RESOLUTION:
                    if selected != remaining or not remaining:
                        raise FactMemoryIntegrityError(
                            "manual conflict partition is invalid"
                        )
                    supported = {
                        claim_id
                        for _, claim_id, role, _ in payload_links
                        if role == ResolutionEvidenceRole.SUPPORTS_REMAINING
                    }
                    contradicted = {
                        claim_id
                        for _, claim_id, role, _ in payload_links
                        if role == ResolutionEvidenceRole.CONTRADICTS_REMOVED
                    }
                    if (
                        supported != remaining
                        or contradicted != group_claims - remaining
                    ):
                        raise FactMemoryIntegrityError(
                            "manual conflict evidence partition is incomplete"
                        )
                if (
                    event.resolution_kind
                    == ConflictResolutionKind.DISMISSED_AS_NOT_CONFLICTING
                ):
                    dismissal_supported = {
                        claim_id
                        for _, claim_id, role, _ in payload_links
                        if role == ResolutionEvidenceRole.SUPPORTS_DISMISSAL
                    }
                    if (
                        selected != group_claims
                        or remaining != group_claims
                        or dismissal_supported != group_claims
                    ):
                        raise FactMemoryIntegrityError(
                            "dismissal conflict evidence partition is incomplete"
                        )
            elif event.new_status != ConflictResolutionStatus.UNRESOLVED:
                raise FactMemoryIntegrityError(
                    "legacy review-required resolution cannot be trusted as resolved"
                )
            for _, claim_id, role_value, _ in payload_links:
                role = ResolutionEvidenceRole(role_value)
                if claim_id not in group_claims:
                    raise FactMemoryIntegrityError(
                        "resolution evidence claim is outside conflict group"
                    )
                if (
                    event.integrity_status
                    == ConflictResolutionIntegrityStatus.VERIFIED_V4
                    and (
                        (
                            role == ResolutionEvidenceRole.SUPPORTS_REMAINING
                            and claim_id not in remaining
                        )
                        or (
                            role == ResolutionEvidenceRole.CONTRADICTS_REMOVED
                            and claim_id in remaining
                        )
                    )
                ):
                    raise FactMemoryIntegrityError(
                        "resolution evidence partition binding changed"
                    )
            for evidence_id, _, _, _ in payload_links:
                evidence_row = connection.execute(
                    "SELECT created_at FROM evidence WHERE evidence_id = ?",
                    (evidence_id,),
                ).fetchone()
                if evidence_row is None or temporal_key(evidence_row[0]) > temporal_key(
                    event.recorded_at
                ):
                    raise FactMemoryIntegrityError(
                        "resolution evidence postdates the resolution"
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
                "SELECT canonical_claim_hash, claim_record_hash, payload_json FROM claims"
            ):
                raw = json.loads(row[2])
                claim = _claim_from_json(row[2])
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
                stored_record_hash = raw.pop("claim_record_hash", None)
                if (
                    stored_record_hash != row[1]
                    or claim.claim_record_hash != row[1]
                    or content_hash(raw) != row[1]
                ):
                    raise FactMemoryIntegrityError("claim full-record hash mismatch")
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
                        "actor_identity_type",
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
                        "actor_identity_type",
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
                        "actor_identity_type",
                        "reason",
                        "recorded_at",
                    ),
                ),
            ):
                for row in connection.execute(f"SELECT * FROM {table}"):
                    payload = {field: row[field] for field in fields}
                    interpreted_hash = content_hash(payload)
                    record_id = (
                        f"{row['claim_id']}:{row['evidence_id']}"
                        if table == "claim_evidence"
                        else str(row[fields[0]])
                    )
                    if interpreted_hash != row[
                        hash_column
                    ] and not self._migration_hash_allows(
                        connection,
                        table,
                        record_id,
                        str(row[hash_column]),
                        interpreted_hash,
                    ):
                        raise FactMemoryIntegrityError(f"{table} row hash mismatch")
            self._verify_payload_table(
                connection,
                "conflict_resolution_events",
                "event_hash",
                "event_hash",
            )
            self._verify_resolution_evidence_links(connection)
            for row in connection.execute(
                """SELECT ce.relation, e.payload_json FROM claim_evidence ce
                   JOIN evidence e ON e.evidence_id = ce.evidence_id"""
            ):
                if EvidenceRelation(row[0]) != _evidence_from_json(row[1]).relation:
                    raise FactMemoryIntegrityError(
                        "claim evidence polarity does not match immutable evidence"
                    )
            for row in connection.execute("SELECT * FROM migration_record_hashes"):
                if not re.fullmatch(
                    r"[0-9a-f]{64}", row["source_hash"]
                ) or not re.fullmatch(r"[0-9a-f]{64}", row["interpreted_v2_hash"]):
                    raise FactMemoryIntegrityError("migration record hash is invalid")
        return result

    @staticmethod
    def _migration_hash_allows(
        connection: sqlite3.Connection,
        table: str,
        record_id: str,
        source_hash: str,
        interpreted_hash: str,
    ) -> bool:
        row = connection.execute(
            """SELECT 1 FROM migration_record_hashes
               WHERE table_name = ? AND record_id = ?
                 AND source_hash = ? AND interpreted_v2_hash = ?""",
            (table, record_id, source_hash, interpreted_hash),
        ).fetchone()
        return row is not None

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
        self._trusted_actor(
            approval.reviewer_identity,
            approval.reviewer_identity_type,
            purpose="claim approval replay",
        )
        if not proposal.reviewer_identity or proposal.reviewer_identity_type in {
            None,
            ActorIdentityType.MODEL,
        }:
            raise FactApprovalError(
                "proposal reviewer artifact is missing or untrusted"
            )
        supporting = tuple(
            item for item in evidence if item.relation == EvidenceRelation.SUPPORTS
        )
        independent_non_model_support = any(
            source.source_kind != SourceKind.MODEL_INFERENCE
            for source in sources
            if source.source_id in {item.source_id for item in supporting}
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
            "supporting_evidence_hashes": tuple(
                sorted(item.evidence_hash for item in supporting)
            ),
            "independent_non_model_support": independent_non_model_support,
            "policy_version": FACT_APPROVAL_POLICY_VERSION,
            "fact_memory_schema_version": FACT_MEMORY_SCHEMA_VERSION,
        }
        changed = next(
            (key for key, value in expected.items() if getattr(approval, key) != value),
            None,
        )
        if changed is not None:
            raise FactApprovalError(f"approval dependency changed: {changed}")
        if not independent_non_model_support:
            raise FactApprovalError(
                "approval lacks independently approved non-model support"
            )
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
        if (
            predicate.cardinality != Cardinality.SINGLE
            or predicate.overlapping_intervals_permitted
        ):
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
            self._insert_conflict_resolution_event(
                connection,
                group,
                kind=ConflictResolutionKind.INITIAL_STATE,
                new_status=ConflictResolutionStatus.UNRESOLVED,
                actor_identity="FACT_MEMORY",
                actor_identity_type=ActorIdentityType.TRUSTED_PROCESS,
                reason="conflict group created",
                evidence_ids=(),
                selected_claim_ids=(),
                remaining_claim_ids=group.claim_ids,
                recorded_at=group.created_at,
            )
            groups.append(group)
        return tuple(groups)

    def _matching_conflicts(
        self,
        connection: sqlite3.Connection,
        claims: list[ClaimRecord],
        known_at: str,
    ) -> tuple[ConflictGroup, ...]:
        ids = {item.claim_id for item in claims}
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""SELECT DISTINCT g.payload_json FROM conflict_groups g
                JOIN conflict_group_claims c ON c.conflict_group_id = g.conflict_group_id
                WHERE g.created_at <= ? AND c.claim_id IN ({placeholders})""",
            (normalize_temporal(known_at), *tuple(sorted(ids))),
        )
        return tuple(
            projected
            for row in rows
            if len(ids & set((group := _conflict_from_json(row[0])).claim_ids)) >= 2
            and (
                projected := self._conflict_as_known_at(
                    connection,
                    group,
                    known_at,
                )
            ).resolution_status
            == ConflictResolutionStatus.UNRESOLVED
        )

    def _resolved_conflict_history(
        self,
        connection: sqlite3.Connection,
        claims: list[ClaimRecord],
        known_at: str,
    ) -> tuple[ConflictGroup, ...]:
        ids = {item.claim_id for item in claims}
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""SELECT DISTINCT g.payload_json FROM conflict_groups g
                JOIN conflict_group_claims c ON c.conflict_group_id = g.conflict_group_id
                WHERE g.created_at <= ? AND c.claim_id IN ({placeholders})""",
            (normalize_temporal(known_at), *tuple(sorted(ids))),
        )
        projected = tuple(
            self._conflict_as_known_at(
                connection,
                _conflict_from_json(row[0]),
                known_at,
            )
            for row in rows
        )
        return tuple(
            item
            for item in projected
            if item.resolution_status == ConflictResolutionStatus.RESOLVED
        )

    def _conflict_as_known_at(
        self,
        connection: sqlite3.Connection,
        group: ConflictGroup,
        known_at: str,
    ) -> ConflictGroup:
        event = self._conflict_resolution_event_at(
            connection,
            group.conflict_group_id,
            known_at,
        )
        if event is None:
            return group
        return replace(
            group,
            resolution_status=event.new_status,
            resolved_at=event.recorded_at
            if event.new_status == ConflictResolutionStatus.RESOLVED
            else None,
            resolution_evidence_ids=event.evidence_ids,
        )

    @staticmethod
    def _conflict_resolution_event_at(
        connection: sqlite3.Connection,
        conflict_group_id: str,
        known_at: str,
    ) -> ConflictResolutionEvent | None:
        row = connection.execute(
            """SELECT payload_json FROM conflict_resolution_events
               WHERE conflict_group_id = ? AND recorded_at <= ?
               ORDER BY recorded_at DESC, rowid DESC LIMIT 1""",
            (conflict_group_id, normalize_temporal(known_at)),
        ).fetchone()
        if row is None:
            return None
        return _conflict_resolution_from_json(row[0])

    def _insert_conflict_resolution_event(
        self,
        connection: sqlite3.Connection,
        group: ConflictGroup,
        *,
        kind: ConflictResolutionKind,
        new_status: ConflictResolutionStatus,
        actor_identity: str,
        actor_identity_type: ActorIdentityType,
        reason: str,
        evidence_ids: tuple[str, ...],
        evidence_links: tuple[ResolutionEvidenceLink, ...] = (),
        selected_claim_ids: tuple[str, ...],
        remaining_claim_ids: tuple[str, ...],
        recorded_at: str,
    ) -> ConflictResolutionEvent:
        current = self._conflict_as_known_at(connection, group, recorded_at)
        payload = {
            "event_id": f"conflict_resolution_{uuid4().hex}",
            "conflict_group_id": group.conflict_group_id,
            "prior_status": current.resolution_status,
            "new_status": new_status,
            "resolution_kind": kind,
            "selected_claim_ids": tuple(sorted(selected_claim_ids)),
            "remaining_claim_ids": tuple(sorted(remaining_claim_ids)),
            "evidence_ids": tuple(sorted(evidence_ids)),
            "evidence_links": tuple(evidence_links),
            "actor_identity": actor_identity,
            "actor_identity_type": actor_identity_type,
            "reason": reason.strip(),
            "recorded_at": recorded_at,
            "policy_version": FACT_CONFLICT_POLICY_VERSION,
            "integrity_status": ConflictResolutionIntegrityStatus.VERIFIED_V4,
            "legacy_event_hash": None,
        }
        event = ConflictResolutionEvent(
            **payload,
            event_hash=content_hash(payload),
        )
        connection.execute(
            """INSERT INTO conflict_resolution_events(
                event_id, conflict_group_id, prior_status, new_status,
                resolution_kind, actor_identity, actor_identity_type,
                recorded_at, event_hash, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.conflict_group_id,
                event.prior_status,
                event.new_status,
                event.resolution_kind,
                event.actor_identity,
                event.actor_identity_type,
                event.recorded_at,
                event.event_hash,
                canonical_json(event),
            ),
        )
        connection.executemany(
            "INSERT INTO resolution_evidence_links VALUES (?, ?, ?, ?, ?)",
            (
                (
                    event.event_id,
                    link.evidence_id,
                    link.claim_id,
                    link.role,
                    link.link_hash,
                )
                for link in event.evidence_links
            ),
        )
        return event

    def _resolve_conflicts_for_claim_event(
        self,
        connection: sqlite3.Connection,
        claim_id: str,
        kind: ConflictResolutionKind,
        actor_identity: str,
        actor_identity_type: ActorIdentityType,
        reason: str,
        recorded_at: str,
        *,
        selected_claim_ids: tuple[str, ...] = (),
    ) -> None:
        rows = connection.execute(
            """SELECT g.payload_json FROM conflict_groups g
               JOIN conflict_group_claims c
                 ON c.conflict_group_id = g.conflict_group_id
               WHERE c.claim_id = ?""",
            (claim_id,),
        )
        for row in rows:
            group = _conflict_from_json(row[0])
            projected = self._conflict_as_known_at(connection, group, recorded_at)
            if projected.resolution_status != ConflictResolutionStatus.UNRESOLVED:
                continue
            foreign_selected = set(selected_claim_ids) - set(group.claim_ids)
            if foreign_selected:
                self.database.append_audit(
                    connection,
                    "SUPERSESSION_OUTSIDE_GROUP_NO_AUTO_RESOLUTION",
                    {
                        "claim_id": claim_id,
                        "foreign_selected_claim_ids": tuple(sorted(foreign_selected)),
                    },
                    group.conflict_group_id,
                )
                continue
            remaining = tuple(
                item
                for item in group.claim_ids
                if item != claim_id
                and self._claim_status_at(connection, item, recorded_at)
                not in {ClaimStatus.RETRACTED, ClaimStatus.SUPERSEDED}
            )
            if not remaining:
                continue
            evidence_ids = self._claim_evidence_at(
                connection,
                claim_id,
                recorded_at,
            )
            event = self._insert_conflict_resolution_event(
                connection,
                group,
                kind=kind,
                new_status=ConflictResolutionStatus.RESOLVED,
                actor_identity=actor_identity,
                actor_identity_type=actor_identity_type,
                reason=reason,
                evidence_ids=evidence_ids,
                evidence_links=(),
                selected_claim_ids=selected_claim_ids or remaining,
                remaining_claim_ids=remaining,
                recorded_at=recorded_at,
            )
            self.database.append_audit(
                connection,
                "CONFLICT_RESOLVED",
                {
                    "resolution_event_hash": event.event_hash,
                    "kind": kind,
                },
                group.conflict_group_id,
            )

    def _claim_answer(
        self,
        connection: sqlite3.Connection,
        claim: ClaimRecord,
        known_at: str,
        conflicted: bool,
        *,
        include_details: bool,
    ) -> ClaimAnswer:
        supporting = tuple(
            self._evidence(connection, item) for item in claim.supporting_evidence_ids
        )
        contradicting = tuple(
            self._evidence(connection, item)
            for item in claim.contradicting_evidence_ids
        )
        supporting_sources = tuple(
            self._source(connection, item.source_id) for item in supporting
        )
        contradicting_sources = tuple(
            self._source(connection, item.source_id) for item in contradicting
        )
        supporting_states = tuple(
            self._source_status_at(connection, item.source_id, known_at)
            for item in supporting_sources
        )
        contradicting_states = tuple(
            self._source_status_at(connection, item.source_id, known_at)
            for item in contradicting_sources
        )
        evidence = (*supporting, *contradicting)
        sources = (*supporting_sources, *contradicting_sources)
        transaction = self.transaction_interval_as_known_at(
            claim.claim_id,
            known_at,
            connection=connection,
        )
        evidence_state = (
            EvidenceConflictState.CONTESTED
            if contradicting
            else EvidenceConflictState.CLEAR
        )
        return ClaimAnswer(
            claim_id=claim.claim_id,
            claim_hash=claim.canonical_claim_hash,
            value=claim.object_value,
            status=claim.status,
            valid_from=claim.valid_from,
            valid_to=claim.valid_to,
            recorded_at=claim.recorded_at,
            transaction_to=transaction.transaction_to,
            transaction_status_as_known_at=transaction.status,
            known_at=known_at,
            supporting_evidence_ids=tuple(item.evidence_id for item in supporting),
            supporting_evidence_hashes=tuple(
                sorted(item.evidence_hash for item in supporting)
            ),
            supporting_source_ids=tuple(
                sorted({item.source_id for item in supporting_sources})
            ),
            supporting_source_hashes=tuple(
                sorted({item.record_hash for item in supporting_sources})
            ),
            supporting_source_citations=tuple(
                _source_citation(item)
                for item in sorted(supporting_sources, key=lambda row: row.source_id)
            )
            if include_details
            else (),
            supporting_source_trust_tiers=tuple(
                sorted({item.trust_tier for item in supporting_sources})
            ),
            independent_supporting_source_family_count=len(
                {
                    item.source_family
                    for item in supporting_sources
                    if item.source_kind != SourceKind.MODEL_INFERENCE
                    and self._source_status_at(connection, item.source_id, known_at)
                    == SourceStatus.ACTIVE
                }
            ),
            contradicting_evidence_ids=tuple(
                item.evidence_id for item in contradicting
            ),
            contradicting_evidence_hashes=tuple(
                sorted(item.evidence_hash for item in contradicting)
            ),
            contradicting_source_ids=tuple(
                sorted({item.source_id for item in contradicting_sources})
            ),
            contradicting_source_hashes=tuple(
                sorted({item.record_hash for item in contradicting_sources})
            ),
            contradicting_source_citations=tuple(
                _source_citation(item)
                for item in sorted(
                    contradicting_sources,
                    key=lambda row: row.source_id,
                )
            )
            if include_details
            else (),
            contradicting_source_trust_tiers=tuple(
                sorted({item.trust_tier for item in contradicting_sources})
            ),
            independent_contradicting_source_family_count=len(
                {item.source_family for item in contradicting_sources}
            ),
            support_freshness_state=_freshness_state(supporting_states),
            contradiction_freshness_state=_freshness_state(
                contradicting_states,
                empty="NONE",
            ),
            evidence_conflict_state=evidence_state,
            source_ids=tuple(sorted({item.source_id for item in sources})),
            source_hashes=tuple(sorted({item.record_hash for item in sources})),
            source_citations=tuple(
                _source_citation(item)
                for item in sorted(sources, key=lambda row: row.source_id)
            )
            if include_details
            else (),
            evidence_ids=claim.evidence_ids,
            evidence_hashes=tuple(sorted(item.evidence_hash for item in evidence)),
            source_trust_tiers=tuple(sorted({item.trust_tier for item in sources})),
            independent_source_family_count=len(
                {item.source_family for item in sources}
            ),
            evidence_count=len(evidence),
            freshness_state=_freshness_state(supporting_states),
            review_state="APPROVED",
            conflict_state="CONTESTED"
            if conflicted or evidence_state == EvidenceConflictState.CONTESTED
            else "UNCONTESTED",
            source_retraction_state="AFFECTED"
            if SourceStatus.RETRACTED in (*supporting_states, *contradicting_states)
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
        *,
        conflict_resolution_statuses: tuple[
            tuple[str, ConflictResolutionStatus], ...
        ] = (),
    ) -> FactAnswerBundle:
        known_at = query.known_at or query.created_at
        payload = {
            "query_id": query.query_id,
            "query_hash": query.query_hash,
            "fact_memory_schema_version": FACT_MEMORY_SCHEMA_VERSION,
            "answer_schema_version": FACT_ANSWER_SCHEMA_VERSION,
            "memory_snapshot_hash": snapshot,
            "valid_at": query.valid_at,
            "known_at": known_at,
            "answer_status": status,
            "selected_claim_ids": tuple(item.claim_id for item in claims),
            "conflict_group_ids": conflict_ids,
            "conflict_resolution_statuses": conflict_resolution_statuses,
            "claims": claims,
            "provenance_detail_mode": ProvenanceDetailMode.FULL
            if query.include_evidence
            else ProvenanceDetailMode.REFERENCES_ONLY,
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
            "FACT_QUERY_FAILED"
            if failed
            else (
                "HISTORICAL_QUERY_EXECUTED"
                if query.known_at_explicitly_requested
                else "FACT_QUERY_EXECUTED"
            ),
            {
                "query_hash": query.query_hash,
                "snapshot_hash": bundle.memory_snapshot_hash,
                "answer_status": bundle.answer_status,
                "valid_at": query.valid_at,
                "known_at": bundle.known_at,
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

    def _claim_support_state(
        self,
        connection: sqlite3.Connection,
        supporting_sources: tuple[SourceRecord, ...],
        known_at: str,
    ) -> str:
        trusted_sources = tuple(
            item
            for item in supporting_sources
            if item.source_kind != SourceKind.MODEL_INFERENCE
        )
        states = {
            self._source_status_at(
                connection,
                item.source_id,
                known_at,
            )
            for item in trusted_sources
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
        return self._source_status_projection(connection, source_id, point)[0]

    @staticmethod
    def _source_status_projection(
        connection: sqlite3.Connection,
        source_id: str,
        point: str,
    ) -> tuple[SourceStatus, str | None]:
        row = connection.execute(
            """SELECT status, event_hash FROM source_status_events
               WHERE source_id = ? AND recorded_at <= ?
               ORDER BY recorded_at DESC, rowid DESC LIMIT 1""",
            (source_id, normalize_temporal(point)),
        ).fetchone()
        if row is None:
            return SourceStatus.ACTIVE, None
        return SourceStatus(row[0]), str(row[1])

    def transaction_interval_as_known_at(
        self,
        claim_id: str,
        known_at: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> TransactionIntervalState:
        point = normalize_temporal(known_at)
        if point is None:
            raise ValueError("known_at is required")
        if connection is None:
            with self.database.connect() as opened:
                return self.transaction_interval_as_known_at(
                    claim_id,
                    point,
                    connection=opened,
                )
        claim = self._claim_record(connection, claim_id)
        row = connection.execute(
            """SELECT status, recorded_at, event_hash FROM claim_status_events
               WHERE claim_id = ? AND recorded_at <= ?
               ORDER BY recorded_at DESC, rowid DESC LIMIT 1""",
            (claim_id, point),
        ).fetchone()
        status = ClaimStatus(row[0]) if row else ClaimStatus.PROPOSED
        terminal = connection.execute(
            """SELECT recorded_at FROM claim_status_events
               WHERE claim_id = ? AND recorded_at <= ?
                 AND status IN ('SUPERSEDED', 'RETRACTED')
               ORDER BY recorded_at LIMIT 1""",
            (claim_id, point),
        ).fetchone()
        return TransactionIntervalState(
            claim_id=claim_id,
            transaction_from=claim.recorded_at,
            transaction_to=terminal[0] if terminal else None,
            status=status,
            known_at=point,
            status_event_hash=str(row[2]) if row else None,
        )

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

    def _claim_evidence_by_polarity_at(
        self,
        connection: sqlite3.Connection,
        claim_id: str,
        point: str,
    ) -> tuple[tuple[EvidenceRecord, ...], tuple[EvidenceRecord, ...]]:
        rows = connection.execute(
            """SELECT ce.relation, e.payload_json FROM claim_evidence ce
               JOIN evidence e ON e.evidence_id = ce.evidence_id
               WHERE ce.claim_id = ? AND ce.attached_at <= ?
               ORDER BY ce.evidence_id""",
            (claim_id, normalize_temporal(point)),
        )
        supporting: list[EvidenceRecord] = []
        contradicting: list[EvidenceRecord] = []
        for row in rows:
            evidence = _evidence_from_json(row[1])
            relation = EvidenceRelation(row[0])
            if relation != evidence.relation:
                raise FactMemoryIntegrityError("claim evidence polarity mismatch")
            target = (
                supporting if relation == EvidenceRelation.SUPPORTS else contradicting
            )
            target.append(evidence)
        return tuple(supporting), tuple(contradicting)

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
            cursor = connection.execute(
                "INSERT OR IGNORE INTO claim_evidence VALUES (?, ?, ?, ?, ?)",
                (*payload.values(), content_hash(payload)),
            )
            if cursor.rowcount:
                self.database.append_audit(
                    connection,
                    "CLAIM_EVIDENCE_CONTESTED"
                    if evidence.relation == EvidenceRelation.CONTRADICTS
                    else "CLAIM_EVIDENCE_ATTACHED",
                    {
                        "evidence_hash": evidence.evidence_hash,
                        "relation": evidence.relation,
                        "attached_at": attached_at,
                    },
                    claim_id,
                )

    def _insert_relation(self, connection: sqlite3.Connection, **payload: Any) -> None:
        row = {"relation_id": f"claim_relation_{uuid4().hex}", **payload}
        connection.execute(
            "INSERT INTO claim_relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        self,
        current: FactProposal,
        status: ProposalStatus,
        *,
        reviewer_identity: str | None = None,
        reviewer_identity_type: ActorIdentityType | None = None,
    ) -> FactProposal:
        payload = asdict(current)
        payload.update(
            revision=current.revision + 1,
            status=status,
            updated_at=self._now(),
            reviewer_identity=reviewer_identity
            if reviewer_identity is not None
            else current.reviewer_identity,
            reviewer_identity_type=reviewer_identity_type
            if reviewer_identity_type is not None
            else current.reviewer_identity_type,
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

    def _claim_record(
        self,
        connection: sqlite3.Connection,
        claim_id: str,
    ) -> ClaimRecord:
        return _claim_from_json(self._claim_row(connection, claim_id)["payload_json"])

    def _claim(self, connection: sqlite3.Connection, claim_id: str) -> ClaimRecord:
        claim = self._claim_record(connection, claim_id)
        point = self._now()
        supporting, contradicting = self._claim_evidence_by_polarity_at(
            connection,
            claim_id,
            point,
        )
        supporting_sources = tuple(
            self._source(connection, item.source_id) for item in supporting
        )
        contradicting_sources = tuple(
            self._source(connection, item.source_id) for item in contradicting
        )
        active_supporting_families = {
            item.source_family
            for item in supporting_sources
            if item.source_kind != SourceKind.MODEL_INFERENCE
            and self._source_status_at(connection, item.source_id, point)
            == SourceStatus.ACTIVE
        }
        status = self._claim_status_at(connection, claim_id, point)
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
                and len(active_supporting_families) >= 2
                else status
            ),
            evidence_ids=tuple(
                sorted(item.evidence_id for item in (*supporting, *contradicting))
            ),
            supporting_evidence_ids=tuple(item.evidence_id for item in supporting),
            contradicting_evidence_ids=tuple(
                item.evidence_id for item in contradicting
            ),
            source_family_support_set=tuple(sorted(active_supporting_families)),
            source_family_contradiction_set=tuple(
                sorted({item.source_family for item in contradicting_sources})
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

    def _trusted_actor(
        self,
        identity: str | None,
        actor_type: ActorIdentityType | str | None,
        *,
        purpose: str,
    ) -> tuple[str, ActorIdentityType]:
        normalized = identity.strip() if isinstance(identity, str) else ""
        try:
            parsed_type = (
                ActorIdentityType(actor_type) if actor_type is not None else None
            )
        except (TypeError, ValueError):
            parsed_type = None
        rejected = (
            not normalized
            or parsed_type is None
            or parsed_type == ActorIdentityType.MODEL
            or normalized.casefold() in _RESERVED_MODEL_IDENTITIES
        )
        if rejected:
            self._audit_rejection(
                "FACT_ACTOR_REJECTED",
                None,
                {
                    "purpose": purpose,
                    "identity_present": bool(normalized),
                    "actor_identity_type": parsed_type,
                    "actor_identity_type_valid": parsed_type is not None,
                },
            )
            raise FactApprovalError(
                f"{purpose} requires a non-model typed actor identity"
            )
        return normalized, parsed_type

    def _audit_rejection(
        self,
        event_type: str,
        object_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        with self.database.write() as connection:
            self.database.append_audit(
                connection,
                event_type,
                payload,
                object_id,
            )

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
    actor_identity_type: ActorIdentityType,
    reason: str | None,
    recorded_at: str,
) -> tuple[str, str, ClaimStatus, str, ActorIdentityType, str | None, str, str]:
    payload = {
        "event_id": f"claim_status_{uuid4().hex}",
        "claim_id": claim_id,
        "status": status,
        "actor": actor,
        "actor_identity_type": actor_identity_type,
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
    reviewer_type = row.get("reviewer_identity_type")
    row["reviewer_identity_type"] = (
        ActorIdentityType(reviewer_type) if reviewer_type else None
    )
    return EvidenceRecord(**row)


def _proposal_from_json(payload: str) -> FactProposal:
    row = json.loads(payload)
    row["source"] = ProposalSource(row["source"])
    row["status"] = ProposalStatus(row["status"])
    row["object_value"] = FactValue.from_dict(row["object_value"])
    row["qualifiers"] = _fact_values(row["qualifiers"])
    row["source_ids"] = tuple(row["source_ids"])
    row["evidence_ids"] = tuple(row["evidence_ids"])
    row.setdefault("reviewer_identity", None)
    reviewer_type = row.get("reviewer_identity_type")
    row["reviewer_identity_type"] = (
        ActorIdentityType(reviewer_type) if reviewer_type else None
    )
    return FactProposal(**row)


def _approval_from_json(payload: str) -> FactApprovalEnvelope:
    row = json.loads(payload)
    row["decision"] = ApprovalDecision(row["decision"])
    row["source_hashes"] = tuple(row["source_hashes"])
    row["evidence_hashes"] = tuple(row["evidence_hashes"])
    row["reviewer_identity_type"] = ActorIdentityType(row["reviewer_identity_type"])
    row["supporting_evidence_hashes"] = tuple(
        row.get("supporting_evidence_hashes", row["evidence_hashes"])
    )
    row.setdefault("independent_non_model_support", True)
    return FactApprovalEnvelope(**row)


def _claim_from_json(payload: str) -> ClaimRecord:
    row = json.loads(payload)
    row["status"] = ClaimStatus(row["status"])
    row["object_value"] = FactValue.from_dict(row["object_value"])
    row["qualifiers"] = _fact_values(row["qualifiers"])
    row["evidence_ids"] = tuple(row["evidence_ids"])
    row["supporting_evidence_ids"] = tuple(
        row.get("supporting_evidence_ids", row["evidence_ids"])
    )
    row["contradicting_evidence_ids"] = tuple(row.get("contradicting_evidence_ids", ()))
    row["source_family_support_set"] = tuple(row["source_family_support_set"])
    row["source_family_contradiction_set"] = tuple(
        row.get("source_family_contradiction_set", ())
    )
    row["supersedes_claim_ids"] = tuple(row["supersedes_claim_ids"])
    return ClaimRecord(**row)


def _conflict_from_json(payload: str) -> ConflictGroup:
    row = json.loads(payload)
    row["claim_ids"] = tuple(row["claim_ids"])
    row["overlapping_interval"] = tuple(row["overlapping_interval"])
    row["resolution_status"] = ConflictResolutionStatus(row["resolution_status"])
    row["resolution_evidence_ids"] = tuple(row["resolution_evidence_ids"])
    return ConflictGroup(**row)


def _conflict_resolution_from_json(payload: str) -> ConflictResolutionEvent:
    row = json.loads(payload)
    row["prior_status"] = ConflictResolutionStatus(row["prior_status"])
    row["new_status"] = ConflictResolutionStatus(row["new_status"])
    row["resolution_kind"] = ConflictResolutionKind(row["resolution_kind"])
    row["selected_claim_ids"] = tuple(row["selected_claim_ids"])
    row["remaining_claim_ids"] = tuple(row["remaining_claim_ids"])
    row["evidence_ids"] = tuple(row["evidence_ids"])
    row["evidence_links"] = tuple(
        ResolutionEvidenceLink(
            evidence_id=item["evidence_id"],
            claim_id=item["claim_id"],
            role=ResolutionEvidenceRole(item["role"]),
            link_hash=item["link_hash"],
        )
        for item in row.get("evidence_links", ())
    )
    row["actor_identity_type"] = ActorIdentityType(row["actor_identity_type"])
    row["integrity_status"] = ConflictResolutionIntegrityStatus(
        row.get("integrity_status", "LEGACY_RESOLUTION_REVIEW_REQUIRED")
    )
    row.setdefault("policy_version", "3.0")
    row.setdefault("legacy_event_hash", None)
    return ConflictResolutionEvent(**row)


def _parse_actor_type(
    value: ActorIdentityType | str | None,
) -> ActorIdentityType | None:
    if value is None:
        return None
    return ActorIdentityType(value)


def _source_citation(source: SourceRecord) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "title": source.title,
        "locator": source.locator,
        "trust_tier": source.trust_tier,
        "source_hash": source.record_hash,
    }


def _freshness_state(
    states: tuple[SourceStatus, ...],
    *,
    empty: str = "STALE",
) -> str:
    if not states:
        return empty
    active = sum(item == SourceStatus.ACTIVE for item in states)
    if active == len(states):
        return "CURRENT"
    if active:
        return "PARTIALLY_STALE"
    return "STALE"
