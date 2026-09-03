"""Oracle-free production Java acquisition and source-entailment trust."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from itertools import combinations
from weakref import ref

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_evidence import (
    JavaFieldEvidenceManifest,
    build_java_field_evidence_manifest,
    evidence_by_proposal,
    nonexact_evidence_proposal_ids,
    verify_java_field_evidence_manifest,
)
from ai_brain.stage3.acquisition.java_evidence_policy import (
    JavaEvidencePolicyManifest,
    load_production_java_evidence_policy,
)
from ai_brain.stage3.acquisition.java_parser_artifact import (
    JavaParserArtifactManifest,
    JavaParserCommonArtifactManifest,
    verify_java_parser_artifact,
)
from ai_brain.stage3.acquisition.java_proposals import (
    JavaProposalBatch,
    propose_java_knowledge,
)
from ai_brain.stage3.acquisition.java_release import (
    JavaReleaseConsistencyReport,
    JavaReleaseIdentity,
    evaluate_java_release_consistency,
    frozen_java_release_identity,
    verify_java_release_identity,
)
from ai_brain.stage3.acquisition.java_source_index import (
    JAVA_PARSER_VERSION,
    JavaSourceIndex,
    bundle_requires_java_policy,
    declaration_by_node_id,
    index_java_bundle,
    verify_java_source_index,
)
from ai_brain.stage3.acquisition.models import (
    KnowledgeProposal,
    ProposalStatus,
    SourceBundle,
)
from ai_brain.stage3.acquisition.segmentation import (
    DeduplicatedSegments,
    segment_bundle_with_report,
    verify_segments,
    with_proposal_counts,
)
from ai_brain.stage3.acquisition.trust import (
    ProposalTrustState,
    TrustTransitionReceipt,
)
from ai_brain.stage3.acquisition.verification import verify_proposals

JAVA_PRODUCTION_CHECKER_VERSION = "m344.source-entailed-java-trust.v1"
JAVA_PRODUCTION_VERIFIER_VERSION = "m344.java-production-verifier.v1"
_ISSUED_AUTHORIZATIONS: dict[int, ref] = {}


@dataclass(frozen=True)
class JavaProductionIdentityConflict:
    conflict_kind: str
    proposal_ids: tuple[str, ...]
    parser_node_ids: tuple[str, ...]
    source_locations: tuple[str, ...]
    conflict_hash: str


@dataclass(frozen=True)
class JavaProductionConflictReport:
    status: str
    proposal_count: int
    conflict_count: int
    implicated_proposal_ids: tuple[str, ...]
    conflicts: tuple[JavaProductionIdentityConflict, ...]
    report_hash: str


@dataclass(frozen=True)
class JavaProductionTrustDecision:
    proposal_id: str
    proposal_hash: str
    parser_node_id: str
    final_state: ProposalTrustState
    blocker_reason: str | None
    evidence_receipt_hashes: tuple[str, ...]
    transition_receipts: tuple[TrustTransitionReceipt, ...]
    decision_hash: str


@dataclass(frozen=True)
class JavaProductionTrustClosure:
    bundle_id: str
    bundle_hash: str
    document_manifest_hash: str
    segmentation_report_hash: str
    physical_segment_manifest_hash: str
    proposal_manifest_hash: str
    proposal_field_manifest_hash: str
    semantic_identity_manifest_hash: str
    source_index_hash: str
    type_universe_manifest_hash: str
    resolution_receipt_manifest_hash: str
    parser_version: str
    parser_common_artifact_manifest_hash: str
    release_identity_hash: str
    evidence_policy_hash: str
    evidence_transformation_registry_hash: str | None
    evidence_policy_coverage_hash: str | None
    field_evidence_manifest_hash: str
    conflict_report_hash: str
    trust_decision_manifest_hash: str
    trusted_proposal_manifest_hash: str
    checker_version: str
    deterministic_run_id: str
    closure_hash: str


@dataclass(frozen=True)
class JavaProductionTrustBatch:
    bundle: SourceBundle
    segmentation: DeduplicatedSegments
    source_index: JavaSourceIndex
    proposal_batch: JavaProposalBatch
    field_evidence: JavaFieldEvidenceManifest
    evidence_policy: JavaEvidencePolicyManifest
    release_identity: JavaReleaseIdentity
    release_consistency: JavaReleaseConsistencyReport
    parser_common_artifact: JavaParserCommonArtifactManifest
    parser_platform_artifact: JavaParserArtifactManifest
    conflict_report: JavaProductionConflictReport
    decisions: tuple[JavaProductionTrustDecision, ...]
    trusted_proposals: tuple[KnowledgeProposal, ...]
    trusted_count: int
    withheld_count: int
    blocker_counts: tuple[tuple[str, int], ...]
    duplicate_derived_trusted_proposals: int
    closure: JavaProductionTrustClosure
    batch_hash: str


@dataclass(frozen=True)
class VerifiedJavaProductionAuthorization:
    batch_hash: str
    closure_hash: str
    trusted_proposal_id: str
    trusted_proposal_hash: str
    decision_hash: str
    transition_receipt_hashes: tuple[str, ...]
    release_identity_hash: str
    evidence_policy_hash: str
    source_index_hash: str
    verifier_version: str
    authorization_hash: str


def run_java_acquisition_pipeline(
    bundle: SourceBundle,
    store,
    *,
    deterministic_run_id: str,
    release_identity: JavaReleaseIdentity | None = None,
) -> JavaProductionTrustBatch:
    """Run production trust without evaluation census, goldens, or expected labels."""

    if not bundle_requires_java_policy(bundle):
        raise ValueError("Java acquisition requires JAVA_SOURCE media")
    release = release_identity or frozen_java_release_identity()
    verify_java_release_identity(release)
    consistency = evaluate_java_release_consistency(release)
    if consistency.status != "PASS":
        raise ValueError("Java production release identity is inconsistent")
    parser_common, parser_platform = verify_java_parser_artifact()
    policy = load_production_java_evidence_policy()
    source_index = index_java_bundle(bundle, store)
    if source_index.type_universe.platform_inventory.release != release.ct_sym_release:
        raise ValueError("Java source index and release policy disagree")
    segmentation = segment_bundle_with_report(
        bundle, store, java_source_index=source_index
    )
    proposals = propose_java_knowledge(bundle, segmentation, source_index)
    verified = verify_proposals(
        bundle, segmentation.segments, proposals.proposals, store
    )
    if verified != proposals.proposals:
        raise ValueError("Java structural verification changed proposal authority")
    evidence = build_java_field_evidence_manifest(
        proposals, source_index, bundle, store, policy=policy
    )
    return bind_java_production_trust(
        bundle,
        segmentation,
        source_index,
        proposals,
        evidence,
        policy,
        release,
        parser_common,
        parser_platform,
        deterministic_run_id=deterministic_run_id,
    )


def bind_java_production_trust(
    bundle: SourceBundle,
    segmentation: DeduplicatedSegments,
    source_index: JavaSourceIndex,
    proposal_batch: JavaProposalBatch,
    field_evidence: JavaFieldEvidenceManifest,
    evidence_policy: JavaEvidencePolicyManifest,
    release_identity: JavaReleaseIdentity,
    parser_common_artifact: JavaParserCommonArtifactManifest,
    parser_platform_artifact: JavaParserArtifactManifest,
    *,
    deterministic_run_id: str,
) -> JavaProductionTrustBatch:
    """Grant trust from source identity, resolution, and exact field evidence only."""

    if not bundle_requires_java_policy(bundle):
        raise ValueError("mutable domain tags cannot enable Java production trust")
    verify_java_release_identity(release_identity)
    consistency = evaluate_java_release_consistency(release_identity)
    if field_evidence.evidence_policy_hash != evidence_policy.manifest_hash:
        raise ValueError("Java evidence is outside frozen production policy")
    conflicts = detect_java_production_identity_conflicts(proposal_batch, source_index)
    nodes = declaration_by_node_id(source_index)
    bindings = {item.proposal_id: item for item in proposal_batch.bindings}
    evidence_map = evidence_by_proposal(field_evidence)
    incomplete = nonexact_evidence_proposal_ids(
        field_evidence, proposal_batch, source_index, evidence_policy
    )
    implicated = set(conflicts.implicated_proposal_ids)
    decisions = []
    for proposal in proposal_batch.proposals:
        declaration = nodes[bindings[proposal.proposal_id].parser_node_id]
        blocker = None
        if proposal.status in {ProposalStatus.VERIFIED, ProposalStatus.APPROVED}:
            blocker = "untrusted_contradictory_proposal_status"
        elif not declaration.supported:
            blocker = (
                f"untrusted_{declaration.unsupported_reason or 'unsupported_syntax'}"
            )
        elif proposal.proposal_id in implicated:
            blocker = "untrusted_conflicting_identity"
        elif proposal.proposal_id in incomplete or not evidence_map.get(
            proposal.proposal_id
        ):
            blocker = "untrusted_missing_field_evidence"
        decisions.append(
            _production_decision(
                proposal,
                declaration,
                evidence_map.get(proposal.proposal_id, ()),
                blocker,
                deterministic_run_id,
            )
        )
    decision_values = tuple(sorted(decisions, key=lambda item: item.proposal_id))
    trusted_ids = {
        item.proposal_id
        for item in decision_values
        if item.final_state is ProposalTrustState.TRUSTED
    }
    trusted = tuple(
        item for item in proposal_batch.proposals if item.proposal_id in trusted_ids
    )
    duplicate_derived = _duplicate_derived_trusted(
        segmentation, proposal_batch, trusted_ids
    )
    if duplicate_derived:
        raise ValueError("physical duplicate ancestry produced trusted proposals")
    segmentation = replace(
        segmentation,
        report=with_proposal_counts(
            segmentation.report,
            before=len(proposal_batch.proposals),
            after=len(proposal_batch.proposals),
            trusted_blocked=0,
        ),
    )
    closure = _make_production_closure(
        bundle,
        segmentation,
        source_index,
        proposal_batch,
        field_evidence,
        evidence_policy,
        release_identity,
        parser_common_artifact,
        conflicts,
        decision_values,
        trusted,
        deterministic_run_id,
    )
    counts = Counter(
        item.blocker_reason for item in decision_values if item.blocker_reason
    )
    body = {
        "bundle": bundle,
        "segmentation": segmentation,
        "source_index": source_index,
        "proposal_batch": proposal_batch,
        "field_evidence": field_evidence,
        "evidence_policy": evidence_policy,
        "release_identity": release_identity,
        "release_consistency": consistency,
        "parser_common_artifact": parser_common_artifact,
        "parser_platform_artifact": parser_platform_artifact,
        "conflict_report": conflicts,
        "decisions": decision_values,
        "trusted_proposals": trusted,
        "trusted_count": len(trusted),
        "withheld_count": len(decision_values) - len(trusted),
        "blocker_counts": tuple(sorted(counts.items())),
        "duplicate_derived_trusted_proposals": duplicate_derived,
        "closure": closure,
    }
    return JavaProductionTrustBatch(**body, batch_hash=content_hash(body))


def verify_java_production_batch(
    batch: JavaProductionTrustBatch,
    store,
) -> tuple[VerifiedJavaProductionAuthorization, ...]:
    body = asdict(batch)
    claimed = body.pop("batch_hash")
    if content_hash(body) != claimed:
        raise ValueError("Java production batch hash mismatch")
    verify_java_release_identity(batch.release_identity)
    actual_common, actual_platform = verify_java_parser_artifact()
    if (
        batch.parser_common_artifact != actual_common
        or batch.parser_platform_artifact != actual_platform
    ):
        raise ValueError("Java production parser artifact substitution")
    verify_java_source_index(batch.source_index, batch.bundle, store)
    verify_segments(batch.bundle, batch.segmentation.segments, store)
    rebuilt_segmentation = segment_bundle_with_report(
        batch.bundle, store, java_source_index=batch.source_index
    )
    rebuilt_proposals = propose_java_knowledge(
        batch.bundle, rebuilt_segmentation, batch.source_index
    )
    if (
        rebuilt_proposals != batch.proposal_batch
        or rebuilt_segmentation.segments != batch.segmentation.segments
        or rebuilt_segmentation.aliases != batch.segmentation.aliases
    ):
        raise ValueError("Java production proposal replay mismatch")
    verify_java_field_evidence_manifest(
        batch.field_evidence,
        batch.proposal_batch,
        batch.source_index,
        batch.bundle,
        store,
        policy=batch.evidence_policy,
    )
    rebuilt = bind_java_production_trust(
        batch.bundle,
        rebuilt_segmentation,
        batch.source_index,
        batch.proposal_batch,
        batch.field_evidence,
        batch.evidence_policy,
        batch.release_identity,
        batch.parser_common_artifact,
        batch.parser_platform_artifact,
        deterministic_run_id=batch.closure.deterministic_run_id,
    )
    if rebuilt != batch:
        raise ValueError("Java production trust closure replay mismatch")
    return tuple(
        _authorization(batch, item)
        for item in batch.decisions
        if item.final_state is ProposalTrustState.TRUSTED
    )


def assert_java_production_authority(
    proposal: KnowledgeProposal,
    authorization: VerifiedJavaProductionAuthorization,
) -> None:
    body = asdict(authorization)
    claimed = body.pop("authorization_hash")
    if content_hash(body) != claimed:
        raise ValueError("Java production authorization hash mismatch")
    if (
        _ISSUED_AUTHORIZATIONS.get(id(authorization), lambda: None)()
        is not authorization
        or authorization.trusted_proposal_id != proposal.proposal_id
        or authorization.trusted_proposal_hash != proposal.proposal_hash
        or authorization.verifier_version != JAVA_PRODUCTION_VERIFIER_VERSION
    ):
        raise ValueError("proposal is outside Java production trust closure")


def seal_java_production_output(batch: JavaProductionTrustBatch) -> dict:
    """Create evaluator-facing immutable output without evaluation truth fields."""

    nodes = declaration_by_node_id(batch.source_index)
    bindings = {item.proposal_id: item for item in batch.proposal_batch.bindings}
    decisions = {item.proposal_id: item for item in batch.decisions}
    rows = []
    for proposal in sorted(
        batch.proposal_batch.proposals, key=lambda item: item.proposal_id
    ):
        declaration = nodes[bindings[proposal.proposal_id].parser_node_id]
        decision = decisions[proposal.proposal_id]
        rows.append(
            {
                "proposal_id": proposal.proposal_id,
                "proposal_hash": proposal.proposal_hash,
                "source_unit_id": declaration.source_unit_id,
                "document_bytes_hash": declaration.source_snapshot_hash,
                "start_offset": declaration.declaration_span.byte_start,
                "end_offset": declaration.declaration_span.byte_end,
                "canonical_source_signature": declaration.canonical_source_signature,
                "erased_jvm_descriptor": declaration.erased_jvm_descriptor,
                "receiver_type": declaration.receiver_type,
                "member_kind": declaration.member_kind,
                "member_name": declaration.member_name,
                "declaration_hash": declaration.declaration_hash,
                "proposal_content": asdict(proposal.proposed_content),
                "production_supported": declaration.supported,
                "production_trust_state": decision.final_state.value,
                "production_blocker_reason": decision.blocker_reason,
                "decision_hash": decision.decision_hash,
            }
        )
    body = {
        "schema_version": 1,
        "release_identity": asdict(batch.release_identity),
        "bundle_hash": batch.bundle.bundle_hash,
        "source_index_hash": batch.source_index.index_hash,
        "proposal_manifest_hash": batch.proposal_batch.proposal_manifest_hash,
        "proposal_field_manifest_hash": (
            batch.proposal_batch.proposal_field_manifest_hash
        ),
        "field_evidence_manifest_hash": batch.field_evidence.manifest_hash,
        "trust_closure_hash": batch.closure.closure_hash,
        "candidate_rows": tuple(rows),
    }
    return {**body, "production_output_hash": content_hash(body)}


def detect_java_production_identity_conflicts(
    proposal_batch: JavaProposalBatch,
    source_index: JavaSourceIndex,
) -> JavaProductionConflictReport:
    nodes = declaration_by_node_id(source_index)
    conflicts = {}
    by_proposal: dict[str, list] = {}
    by_physical: dict[tuple, list] = {}
    by_signature: dict[tuple, list] = {}
    for binding in proposal_batch.bindings:
        declaration = nodes[binding.parser_node_id]
        by_proposal.setdefault(binding.proposal_id, []).append(binding)
        by_physical.setdefault(_physical_key(declaration), []).append(binding)
        by_signature.setdefault(
            (
                declaration.receiver_type,
                declaration.member_kind,
                declaration.member_name,
                declaration.erased_jvm_descriptor,
            ),
            [],
        ).append(binding)
    for values, kind in (
        *(
            (values, "ONE_PROPOSAL_MULTIPLE_DECLARATIONS")
            for values in by_proposal.values()
        ),
        *(
            (values, "MULTIPLE_PROPOSALS_SAME_DECLARATION")
            for values in by_physical.values()
        ),
        *((values, "ILLEGAL_DUPLICATE_SIGNATURE") for values in by_signature.values()),
    ):
        if len(values) < 2:
            continue
        for left, right in combinations(values, 2):
            left_node, right_node = (
                nodes[left.parser_node_id],
                nodes[right.parser_node_id],
            )
            actual_kind = (
                "DUPLICATE_PROPOSAL_BINDING"
                if kind == "MULTIPLE_PROPOSALS_SAME_DECLARATION"
                and left.proposal_id == right.proposal_id
                else kind
            )
            conflict = _conflict(
                actual_kind,
                (left.proposal_id, right.proposal_id),
                (left.parser_node_id, right.parser_node_id),
                (_location(left_node), _location(right_node)),
            )
            conflicts[conflict.conflict_hash] = conflict
    values = tuple(conflicts[key] for key in sorted(conflicts))
    implicated = tuple(
        sorted({value for item in values for value in item.proposal_ids})
    )
    body = {
        "status": "FAIL" if values else "PASS",
        "proposal_count": len(proposal_batch.proposals),
        "conflict_count": len(values),
        "implicated_proposal_ids": implicated,
        "conflicts": values,
    }
    return JavaProductionConflictReport(**body, report_hash=content_hash(body))


def _production_decision(proposal, declaration, evidence, blocker, run_id):
    if blocker:
        steps = ((ProposalTrustState.CANDIDATE, ProposalTrustState.WITHHELD, blocker),)
        state = ProposalTrustState.WITHHELD
    else:
        steps = (
            (
                ProposalTrustState.CANDIDATE,
                ProposalTrustState.SOURCE_EVIDENCE_FOUND,
                "source_bytes_verified",
            ),
            (
                ProposalTrustState.SOURCE_EVIDENCE_FOUND,
                ProposalTrustState.IDENTITY_RESOLVED,
                "physical_and_semantic_identity_unique",
            ),
            (
                ProposalTrustState.IDENTITY_RESOLVED,
                ProposalTrustState.TRUSTED,
                "source_entailed_and_structurally_verified",
            ),
        )
        state = ProposalTrustState.TRUSTED
    transitions = tuple(
        _transition(
            proposal.proposal_id, previous, following, reason, declaration, run_id
        )
        for previous, following, reason in steps
    )
    body = {
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash,
        "parser_node_id": declaration.node_id,
        "final_state": state,
        "blocker_reason": blocker,
        "evidence_receipt_hashes": tuple(
            item.derivation_receipt_hash for item in evidence
        ),
        "transition_receipts": transitions,
    }
    return JavaProductionTrustDecision(**body, decision_hash=content_hash(body))


def _transition(proposal_id, previous, following, reason, declaration, run_id):
    body = {
        "proposal_id": proposal_id,
        "previous_state": previous,
        "next_state": following,
        "reason": reason,
        "source_document_hash": declaration.source_snapshot_hash,
        "semantic_identity_hash": declaration.declaration_hash,
        "source_span_hash": declaration.source_span_hash,
        "checker_version": JAVA_PRODUCTION_CHECKER_VERSION,
        "deterministic_run_id": run_id,
    }
    return TrustTransitionReceipt(**body, receipt_hash=content_hash(body))


def _make_production_closure(
    bundle,
    segmentation,
    source_index,
    proposals,
    evidence,
    policy,
    release,
    parser_common,
    conflicts,
    decisions,
    trusted,
    run_id,
):
    physical = tuple(
        (
            item.segment_id,
            item.segment_hash,
            item.document_id,
            item.source_location.byte_start,
            item.source_location.byte_end,
            item.source_span_hash,
        )
        for item in segmentation.segments
    )
    nodes = declaration_by_node_id(source_index)
    identity = tuple(
        (binding.proposal_id, nodes[binding.parser_node_id].declaration_hash)
        for binding in proposals.bindings
    )
    resolution = tuple(
        (
            item.node_id,
            tuple(value.occurrence_hash for value in item.type_occurrence_resolutions),
        )
        for item in source_index.declarations
    )
    body = {
        "bundle_id": bundle.bundle_id,
        "bundle_hash": bundle.bundle_hash,
        "document_manifest_hash": source_index.document_manifest_hash,
        "segmentation_report_hash": segmentation.report.report_hash,
        "physical_segment_manifest_hash": content_hash(physical),
        "proposal_manifest_hash": proposals.proposal_manifest_hash,
        "proposal_field_manifest_hash": proposals.proposal_field_manifest_hash,
        "semantic_identity_manifest_hash": content_hash(identity),
        "source_index_hash": source_index.index_hash,
        "type_universe_manifest_hash": source_index.type_universe_manifest_hash,
        "resolution_receipt_manifest_hash": content_hash(resolution),
        "parser_version": JAVA_PARSER_VERSION,
        "parser_common_artifact_manifest_hash": parser_common.manifest_hash,
        "release_identity_hash": release.identity_hash,
        "evidence_policy_hash": policy.manifest_hash,
        "evidence_transformation_registry_hash": evidence.transformation_registry_hash,
        "evidence_policy_coverage_hash": evidence.policy_coverage_hash,
        "field_evidence_manifest_hash": evidence.manifest_hash,
        "conflict_report_hash": conflicts.report_hash,
        "trust_decision_manifest_hash": content_hash(
            tuple((item.proposal_id, item.decision_hash) for item in decisions)
        ),
        "trusted_proposal_manifest_hash": content_hash(
            tuple((item.proposal_id, item.proposal_hash) for item in trusted)
        ),
        "checker_version": JAVA_PRODUCTION_CHECKER_VERSION,
        "deterministic_run_id": run_id,
    }
    return JavaProductionTrustClosure(**body, closure_hash=content_hash(body))


def _authorization(batch, decision):
    proposal = next(
        item
        for item in batch.trusted_proposals
        if item.proposal_id == decision.proposal_id
    )
    body = {
        "batch_hash": batch.batch_hash,
        "closure_hash": batch.closure.closure_hash,
        "trusted_proposal_id": proposal.proposal_id,
        "trusted_proposal_hash": proposal.proposal_hash,
        "decision_hash": decision.decision_hash,
        "transition_receipt_hashes": tuple(
            item.receipt_hash for item in decision.transition_receipts
        ),
        "release_identity_hash": batch.release_identity.identity_hash,
        "evidence_policy_hash": batch.evidence_policy.manifest_hash,
        "source_index_hash": batch.source_index.index_hash,
        "verifier_version": JAVA_PRODUCTION_VERIFIER_VERSION,
    }
    authorization = VerifiedJavaProductionAuthorization(
        **body, authorization_hash=content_hash(body)
    )
    identity = id(authorization)
    _ISSUED_AUTHORIZATIONS[identity] = ref(
        authorization,
        lambda _value, key=identity: _ISSUED_AUTHORIZATIONS.pop(key, None),
    )
    return authorization


def _physical_key(declaration):
    location = declaration.declaration_span
    return (
        declaration.source_unit_id,
        declaration.source_snapshot_hash,
        location.byte_start,
        location.byte_end,
    )


def _location(declaration):
    value = declaration.declaration_span
    return (
        f"{declaration.source_unit_id}:{value.line_start}-{value.line_end}:"
        f"{value.byte_start}-{value.byte_end}"
    )


def _conflict(kind, proposal_ids, node_ids, locations):
    body = {
        "conflict_kind": kind,
        "proposal_ids": tuple(proposal_ids),
        "parser_node_ids": tuple(node_ids),
        "source_locations": tuple(locations),
    }
    return JavaProductionIdentityConflict(**body, conflict_hash=content_hash(body))


def _duplicate_derived_trusted(segmentation, proposal_batch, trusted_ids):
    aliases = {item.canonical_segment_id for item in segmentation.aliases}
    segment_by_proposal = {
        item.proposal_id: item.segment_id for item in proposal_batch.bindings
    }
    return sum(segment_by_proposal[item] in aliases for item in trusted_ids)
