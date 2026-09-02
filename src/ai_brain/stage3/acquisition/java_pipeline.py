"""Authoritative end-to-end Java semantic trust acquisition pipeline."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from weakref import ref

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_evidence import (
    JavaFieldEvidenceManifest,
    build_java_field_evidence_manifest,
    evidence_by_proposal,
    incomplete_evidence_proposal_ids,
    verify_java_field_evidence_manifest,
)
from ai_brain.stage3.acquisition.java_evidence_policy import (
    JavaEvidencePolicyManifest,
    load_java_evidence_policy,
)
from ai_brain.stage3.acquisition.java_goldens import (
    JavaGoldenLocation,
    JavaGoldenManifest,
    verify_java_golden_manifest,
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
from ai_brain.stage3.acquisition.java_seal import (
    GoldenSealReceipt,
    JavaTrustEvaluationConfig,
    verify_golden_seal_receipt,
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

JAVA_TRUST_CHECKER_VERSION = "m342.authoritative-java-trust.v2"
JAVA_TRUST_VERIFIER_VERSION = "m342.java-trust-verifier.v1"
_ISSUED_AUTHORIZATIONS: dict[int, ref] = {}


@dataclass(frozen=True)
class JavaIdentityConflict:
    conflict_kind: str
    proposal_ids: tuple[str, ...]
    parser_node_ids: tuple[str, ...]
    source_locations: tuple[str, ...]
    conflict_hash: str


@dataclass(frozen=True)
class JavaConflictReport:
    status: str
    proposal_count: int
    conflict_count: int
    implicated_proposal_ids: tuple[str, ...]
    conflicts: tuple[JavaIdentityConflict, ...]
    report_hash: str


@dataclass(frozen=True)
class JavaTrustDecision:
    proposal_id: str
    proposal_hash: str
    parser_node_id: str
    final_state: ProposalTrustState
    blocker_reason: str | None
    golden_id: str | None
    exact_location_match: bool
    evidence_receipt_hashes: tuple[str, ...]
    transition_receipts: tuple[TrustTransitionReceipt, ...]
    decision_hash: str


@dataclass(frozen=True)
class JavaTrustClosure:
    bundle_id: str
    bundle_hash: str
    document_manifest_hash: str
    segmentation_report_hash: str
    physical_segment_manifest_hash: str
    proposal_manifest_hash: str
    semantic_identity_manifest_hash: str
    source_index_hash: str
    type_universe_manifest_hash: str
    resolution_receipt_manifest_hash: str
    parser_version: str
    parser_common_artifact_manifest_hash: str
    golden_manifest_hash: str
    golden_seal_hash: str
    target_census_hash: str
    evidence_policy_hash: str
    field_evidence_manifest_hash: str
    conflict_report_hash: str
    trust_decision_manifest_hash: str
    trusted_proposal_manifest_hash: str
    checker_version: str
    deterministic_run_id: str
    closure_hash: str


@dataclass(frozen=True)
class TrustBoundProposalBatch:
    bundle: SourceBundle
    segmentation: DeduplicatedSegments
    source_index: JavaSourceIndex
    proposal_batch: JavaProposalBatch
    field_evidence: JavaFieldEvidenceManifest
    evidence_policy: JavaEvidencePolicyManifest
    golden_manifest: JavaGoldenManifest
    golden_seal: GoldenSealReceipt
    evaluation_config: JavaTrustEvaluationConfig
    parser_common_artifact: JavaParserCommonArtifactManifest
    parser_platform_artifact: JavaParserArtifactManifest
    conflict_report: JavaConflictReport
    decisions: tuple[JavaTrustDecision, ...]
    trusted_proposals: tuple[KnowledgeProposal, ...]
    trusted_count: int
    withheld_count: int
    blocker_counts: tuple[tuple[str, int], ...]
    duplicate_derived_trusted_proposals: int
    closure: JavaTrustClosure
    batch_hash: str


@dataclass(frozen=True)
class VerifiedJavaTrustAuthorization:
    batch_hash: str
    closure_hash: str
    trusted_proposal_id: str
    trusted_proposal_hash: str
    decision_hash: str
    transition_receipt_hashes: tuple[str, ...]
    golden_seal_hash: str
    evidence_policy_hash: str
    source_index_hash: str
    verifier_version: str
    authorization_hash: str


def run_java_trust_pipeline(
    bundle: SourceBundle,
    store,
    golden_manifest: JavaGoldenManifest,
    golden_seal: GoldenSealReceipt,
    evaluation_config: JavaTrustEvaluationConfig,
    *,
    deterministic_run_id: str,
) -> TrustBoundProposalBatch:
    """Invoke the real ingest-adjacent production pipeline without test constructors."""

    if not bundle_requires_java_policy(bundle):
        raise ValueError("Java trust pipeline requires JAVA_SOURCE media")
    verify_golden_seal_receipt(golden_seal, golden_manifest, evaluation_config)
    parser_common, parser_platform = verify_java_parser_artifact()
    if (
        parser_common.manifest_hash
        != evaluation_config.expected_parser_common_artifact_hash
    ):
        raise ValueError("Java parser artifact is outside evaluation configuration")
    evidence_policy = load_java_evidence_policy()
    if evidence_policy.manifest_hash != evaluation_config.expected_evidence_policy_hash:
        raise ValueError("Java evidence policy is outside evaluation configuration")
    source_index = index_java_bundle(bundle, store)
    segmentation = segment_bundle_with_report(
        bundle, store, java_source_index=source_index
    )
    proposal_batch = propose_java_knowledge(bundle, segmentation, source_index)
    verified = verify_proposals(
        bundle, segmentation.segments, proposal_batch.proposals, store
    )
    if verified != proposal_batch.proposals:
        raise ValueError("Java structural verification changed proposal authority")
    evidence = build_java_field_evidence_manifest(
        proposal_batch,
        source_index,
        bundle,
        store,
        policy=evidence_policy,
    )
    return bind_java_trust(
        bundle,
        segmentation,
        source_index,
        proposal_batch,
        evidence,
        evidence_policy,
        golden_manifest,
        golden_seal,
        evaluation_config,
        parser_common,
        parser_platform,
        deterministic_run_id=deterministic_run_id,
    )


def bind_java_trust(
    bundle: SourceBundle,
    segmentation: DeduplicatedSegments,
    source_index: JavaSourceIndex,
    proposal_batch: JavaProposalBatch,
    field_evidence: JavaFieldEvidenceManifest,
    evidence_policy: JavaEvidencePolicyManifest,
    golden_manifest: JavaGoldenManifest,
    golden_seal: GoldenSealReceipt,
    evaluation_config: JavaTrustEvaluationConfig,
    parser_common_artifact: JavaParserCommonArtifactManifest,
    parser_platform_artifact: JavaParserArtifactManifest,
    *,
    deterministic_run_id: str,
) -> TrustBoundProposalBatch:
    if not bundle_requires_java_policy(bundle):
        raise ValueError("mutable domain tags cannot enable Java trust")
    _verify_golden_source_manifest(golden_manifest, bundle)
    verify_golden_seal_receipt(golden_seal, golden_manifest, evaluation_config)
    if field_evidence.evidence_policy_hash != evidence_policy.manifest_hash:
        raise ValueError("Java evidence is outside sealed evidence policy")
    conflict_report = detect_java_identity_conflicts(proposal_batch, source_index)
    nodes = declaration_by_node_id(source_index)
    binding_by_proposal = {item.proposal_id: item for item in proposal_batch.bindings}
    evidence_map = evidence_by_proposal(field_evidence)
    golden_map = _goldens_by_physical(golden_manifest)
    implicated = set(conflict_report.implicated_proposal_ids)
    incomplete_evidence = incomplete_evidence_proposal_ids(field_evidence)
    decisions = []
    for proposal in proposal_batch.proposals:
        binding = binding_by_proposal[proposal.proposal_id]
        declaration = nodes[binding.parser_node_id]
        golden_values = golden_map.get(_physical_key(declaration), ())
        blocker = None
        golden = None
        exact = False
        if proposal.status in {ProposalStatus.VERIFIED, ProposalStatus.APPROVED}:
            blocker = "untrusted_contradictory_proposal_status"
        elif not declaration.supported:
            blocker = (
                f"untrusted_{declaration.unsupported_reason or 'unsupported_syntax'}"
            )
        elif proposal.proposal_id in implicated:
            blocker = "untrusted_conflicting_identity"
        elif proposal.proposal_id in incomplete_evidence or not evidence_map.get(
            proposal.proposal_id
        ):
            blocker = "untrusted_missing_field_evidence"
        elif len(golden_values) == 0:
            blocker = "untrusted_golden_location_required"
        elif len(golden_values) > 1:
            blocker = "untrusted_ambiguous_identity"
        else:
            golden = golden_values[0]
            exact = _golden_exact(declaration, golden)
            if not exact:
                blocker = "untrusted_location_mismatch"
        decisions.append(
            _decision(
                proposal,
                declaration,
                evidence_map.get(proposal.proposal_id, ()),
                golden,
                exact,
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
    blocked_by_physical_duplicate = _duplicate_derived_candidates(
        segmentation, proposal_batch
    )
    segmentation = replace(
        segmentation,
        report=with_proposal_counts(
            segmentation.report,
            before=len(proposal_batch.proposals) + blocked_by_physical_duplicate,
            after=len(proposal_batch.proposals),
            trusted_blocked=blocked_by_physical_duplicate,
        ),
    )
    closure = _make_closure(
        bundle,
        segmentation,
        source_index,
        proposal_batch,
        field_evidence,
        evidence_policy,
        golden_manifest,
        golden_seal,
        parser_common_artifact,
        conflict_report,
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
        "golden_manifest": golden_manifest,
        "golden_seal": golden_seal,
        "evaluation_config": evaluation_config,
        "parser_common_artifact": parser_common_artifact,
        "parser_platform_artifact": parser_platform_artifact,
        "conflict_report": conflict_report,
        "decisions": decision_values,
        "trusted_proposals": trusted,
        "trusted_count": len(trusted),
        "withheld_count": len(decision_values) - len(trusted),
        "blocker_counts": tuple(sorted(counts.items())),
        "duplicate_derived_trusted_proposals": duplicate_derived,
        "closure": closure,
    }
    return TrustBoundProposalBatch(**body, batch_hash=content_hash(body))


def verify_trust_bound_batch(
    batch: TrustBoundProposalBatch,
    store,
    expected_golden_seal: GoldenSealReceipt,
    expected_parser_artifact: JavaParserCommonArtifactManifest,
) -> tuple[VerifiedJavaTrustAuthorization, ...]:
    body = asdict(batch)
    claimed = body.pop("batch_hash")
    if content_hash(body) != claimed:
        raise ValueError("trust-bound Java batch hash mismatch")
    verify_golden_seal_receipt(
        expected_golden_seal, batch.golden_manifest, batch.evaluation_config
    )
    actual_common, actual_platform = verify_java_parser_artifact()
    if (
        expected_parser_artifact != actual_common
        or batch.parser_common_artifact != actual_common
        or batch.parser_platform_artifact != actual_platform
    ):
        raise ValueError("trust closure parser artifact substitution")
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
        raise ValueError("trust closure proposal or segmentation replay mismatch")
    verify_java_field_evidence_manifest(
        batch.field_evidence,
        batch.proposal_batch,
        batch.source_index,
        batch.bundle,
        store,
        policy=batch.evidence_policy,
    )
    rebuilt = bind_java_trust(
        batch.bundle,
        rebuilt_segmentation,
        batch.source_index,
        batch.proposal_batch,
        batch.field_evidence,
        batch.evidence_policy,
        batch.golden_manifest,
        batch.golden_seal,
        batch.evaluation_config,
        batch.parser_common_artifact,
        batch.parser_platform_artifact,
        deterministic_run_id=batch.closure.deterministic_run_id,
    )
    if rebuilt != batch:
        raise ValueError("trust closure replay or substitution mismatch")
    return tuple(
        _authorization(batch, item)
        for item in batch.decisions
        if item.final_state is ProposalTrustState.TRUSTED
    )


def assert_java_proposal_state_authority(
    proposal: KnowledgeProposal, authorization: VerifiedJavaTrustAuthorization
) -> None:
    body = asdict(authorization)
    claimed = body.pop("authorization_hash")
    if content_hash(body) != claimed:
        raise ValueError("Java trust authorization hash mismatch")
    if (
        _ISSUED_AUTHORIZATIONS.get(id(authorization), lambda: None)()
        is not authorization
        or authorization.trusted_proposal_id != proposal.proposal_id
        or authorization.trusted_proposal_hash != proposal.proposal_hash
        or authorization.verifier_version != JAVA_TRUST_VERIFIER_VERSION
    ):
        raise ValueError("proposal is outside authoritative Java trust closure")


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
        "golden_seal_hash": batch.golden_seal.seal_receipt_hash,
        "evidence_policy_hash": batch.evidence_policy.manifest_hash,
        "source_index_hash": batch.source_index.index_hash,
        "verifier_version": JAVA_TRUST_VERIFIER_VERSION,
    }
    authorization = VerifiedJavaTrustAuthorization(
        **body, authorization_hash=content_hash(body)
    )
    identity = id(authorization)
    _ISSUED_AUTHORIZATIONS[identity] = ref(
        authorization,
        lambda _value, key=identity: _ISSUED_AUTHORIZATIONS.pop(key, None),
    )
    return authorization


def detect_java_identity_conflicts(
    proposal_batch: JavaProposalBatch, source_index: JavaSourceIndex
) -> JavaConflictReport:
    nodes = declaration_by_node_id(source_index)
    bindings = proposal_batch.bindings
    conflicts = {}
    by_proposal: dict[str, list] = {}
    for binding in bindings:
        by_proposal.setdefault(binding.proposal_id, []).append(binding)
    for proposal_id, values in by_proposal.items():
        if len(values) > 1:
            conflict = _conflict(
                "ONE_PROPOSAL_MULTIPLE_DECLARATIONS",
                (proposal_id,),
                tuple(item.parser_node_id for item in values),
                tuple(_location(nodes[item.parser_node_id]) for item in values),
            )
            conflicts[conflict.conflict_hash] = conflict
    for index, left in enumerate(bindings):
        left_node = nodes[left.parser_node_id]
        for right in bindings[index + 1 :]:
            right_node = nodes[right.parser_node_id]
            same_span = _physical_key(left_node) == _physical_key(right_node)
            same_logical = _logical_key(left_node) == _logical_key(right_node)
            kind = None
            if same_span and left.proposal_id == right.proposal_id:
                kind = "DUPLICATE_PROPOSAL_BINDING"
            elif same_span:
                kind = "MULTIPLE_PROPOSALS_SAME_DECLARATION"
            elif same_logical:
                kind = "ILLEGAL_DUPLICATE_SIGNATURE"
            if kind:
                conflict = _conflict(
                    kind,
                    (left.proposal_id, right.proposal_id),
                    (left.parser_node_id, right.parser_node_id),
                    (_location(left_node), _location(right_node)),
                )
                conflicts[conflict.conflict_hash] = conflict
    values = tuple(conflicts[key] for key in sorted(conflicts))
    implicated = tuple(
        sorted({proposal for item in values for proposal in item.proposal_ids})
    )
    body = {
        "status": "FAIL" if values else "PASS",
        "proposal_count": len(proposal_batch.proposals),
        "conflict_count": len(values),
        "implicated_proposal_ids": implicated,
        "conflicts": values,
    }
    return JavaConflictReport(**body, report_hash=content_hash(body))


def _decision(
    proposal,
    declaration,
    evidence,
    golden,
    exact,
    blocker,
    run_id,
):
    if blocker:
        transitions = (
            _transition(
                proposal.proposal_id,
                ProposalTrustState.CANDIDATE,
                ProposalTrustState.WITHHELD,
                blocker,
                declaration,
                run_id,
            ),
        )
        state = ProposalTrustState.WITHHELD
    else:
        steps = (
            (ProposalTrustState.CANDIDATE, ProposalTrustState.SOURCE_EVIDENCE_FOUND),
            (
                ProposalTrustState.SOURCE_EVIDENCE_FOUND,
                ProposalTrustState.IDENTITY_RESOLVED,
            ),
            (
                ProposalTrustState.IDENTITY_RESOLVED,
                ProposalTrustState.GOLDEN_LOCATION_MATCHED,
            ),
            (
                ProposalTrustState.GOLDEN_LOCATION_MATCHED,
                ProposalTrustState.TRUSTED,
            ),
        )
        transitions = tuple(
            _transition(
                proposal.proposal_id,
                previous,
                next_state,
                next_state.value,
                declaration,
                run_id,
            )
            for previous, next_state in steps
        )
        state = ProposalTrustState.TRUSTED
    body = {
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash,
        "parser_node_id": declaration.node_id,
        "final_state": state,
        "blocker_reason": blocker,
        "golden_id": golden.golden_id if golden else None,
        "exact_location_match": exact,
        "evidence_receipt_hashes": tuple(
            item.derivation_receipt_hash for item in evidence
        ),
        "transition_receipts": transitions,
    }
    return JavaTrustDecision(**body, decision_hash=content_hash(body))


def _transition(proposal_id, previous, next_state, reason, declaration, run_id):
    body = {
        "proposal_id": proposal_id,
        "previous_state": previous,
        "next_state": next_state,
        "reason": reason,
        "source_document_hash": declaration.source_snapshot_hash,
        "semantic_identity_hash": declaration.declaration_hash,
        "source_span_hash": declaration.source_span_hash,
        "checker_version": JAVA_TRUST_CHECKER_VERSION,
        "deterministic_run_id": run_id,
    }
    return TrustTransitionReceipt(**body, receipt_hash=content_hash(body))


def _make_closure(
    bundle,
    segmentation,
    source_index,
    proposal_batch,
    evidence,
    evidence_policy,
    goldens,
    golden_seal,
    parser_common,
    conflicts,
    decisions,
    trusted,
    run_id,
):
    physical_segments = tuple(
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
    proposal_nodes = {
        item.proposal_id: item.parser_node_id for item in proposal_batch.bindings
    }
    declarations = declaration_by_node_id(source_index)
    identity_manifest = tuple(
        (proposal_id, declarations[node_id].declaration_hash)
        for proposal_id, node_id in sorted(proposal_nodes.items())
    )
    resolution_receipts = tuple(
        (
            item.node_id,
            tuple(parameter.resolution_receipt_hash for parameter in item.parameters),
            item.return_resolution_receipt_hash,
        )
        for item in source_index.declarations
    )
    body = {
        "bundle_id": bundle.bundle_id,
        "bundle_hash": bundle.bundle_hash,
        "document_manifest_hash": source_index.document_manifest_hash,
        "segmentation_report_hash": segmentation.report.report_hash,
        "physical_segment_manifest_hash": content_hash(physical_segments),
        "proposal_manifest_hash": proposal_batch.proposal_manifest_hash,
        "semantic_identity_manifest_hash": content_hash(identity_manifest),
        "source_index_hash": source_index.index_hash,
        "type_universe_manifest_hash": source_index.type_universe_manifest_hash,
        "resolution_receipt_manifest_hash": content_hash(resolution_receipts),
        "parser_version": JAVA_PARSER_VERSION,
        "parser_common_artifact_manifest_hash": parser_common.manifest_hash,
        "golden_manifest_hash": goldens.manifest_hash,
        "golden_seal_hash": golden_seal.seal_receipt_hash,
        "target_census_hash": golden_seal.target_census_hash,
        "evidence_policy_hash": evidence_policy.manifest_hash,
        "field_evidence_manifest_hash": evidence.manifest_hash,
        "conflict_report_hash": conflicts.report_hash,
        "trust_decision_manifest_hash": content_hash(
            tuple((item.proposal_id, item.decision_hash) for item in decisions)
        ),
        "trusted_proposal_manifest_hash": content_hash(
            tuple((item.proposal_id, item.proposal_hash) for item in trusted)
        ),
        "checker_version": JAVA_TRUST_CHECKER_VERSION,
        "deterministic_run_id": run_id,
    }
    return JavaTrustClosure(**body, closure_hash=content_hash(body))


def _verify_golden_source_manifest(golden_manifest, bundle):
    verify_java_golden_manifest(golden_manifest)
    rows = tuple(
        (item.relative_path.replace("\\", "/"), item.bytes_hash)
        for item in sorted(bundle.documents, key=lambda value: value.relative_path)
        if item.media_type.value == "text/x-java-source"
    )
    if golden_manifest.source_manifest_hash != content_hash(rows):
        raise ValueError("golden manifest belongs to another source closure")


def _goldens_by_physical(manifest):
    result: dict[tuple, list[JavaGoldenLocation]] = {}
    for item in manifest.goldens:
        result.setdefault(
            (
                item.document_bytes_hash,
                item.source_unit_id,
                item.start_offset,
                item.end_offset,
            ),
            [],
        ).append(item)
    return {key: tuple(values) for key, values in result.items()}


def _golden_exact(declaration, golden):
    return (
        golden.document_bytes_hash == declaration.source_snapshot_hash
        and golden.start_offset == declaration.declaration_span.byte_start
        and golden.end_offset == declaration.declaration_span.byte_end
        and golden.start_line == declaration.declaration_span.line_start
        and golden.end_line == declaration.declaration_span.line_end
        and golden.package_name == declaration.package_name
        and golden.top_level_type_name == declaration.top_level_type_name
        and golden.nested_type_path == declaration.nested_type_path
        and golden.member_kind == declaration.member_kind
        and golden.member_name == declaration.member_name
        and golden.erased_jvm_descriptor == declaration.erased_jvm_descriptor
        and golden.expected_supported
    )


def _logical_key(value):
    return (
        value.package_name,
        value.top_level_type_name,
        value.nested_type_path,
        value.member_kind,
        value.member_name,
        value.erased_jvm_descriptor,
    )


def _physical_key(value):
    return (
        value.source_snapshot_hash,
        value.source_unit_id,
        value.declaration_span.byte_start,
        value.declaration_span.byte_end,
    )


def _location(value):
    span = value.declaration_span
    return f"{value.source_unit_id}:{span.line_start}-{span.line_end}:{span.byte_start}-{span.byte_end}"


def _conflict(kind, proposal_ids, node_ids, locations):
    body = {
        "conflict_kind": kind,
        "proposal_ids": tuple(sorted(proposal_ids)),
        "parser_node_ids": tuple(sorted(node_ids)),
        "source_locations": tuple(sorted(locations)),
    }
    return JavaIdentityConflict(**body, conflict_hash=content_hash(body))


def _duplicate_derived_candidates(segmentation, proposal_batch):
    multiplicity = Counter(item.canonical_segment_id for item in segmentation.aliases)
    return sum(multiplicity[item.segment_id] for item in proposal_batch.bindings)


def _duplicate_derived_trusted(segmentation, proposal_batch, trusted_ids):
    multiplicity = Counter(item.canonical_segment_id for item in segmentation.aliases)
    return sum(
        multiplicity[item.segment_id]
        for item in proposal_batch.bindings
        if item.proposal_id in trusted_ids
    )
