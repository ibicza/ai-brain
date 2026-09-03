"""Deterministic compilation of reviewed proposals into a provisional pack."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.identity import PrecompilerIdentityConflict
from ai_brain.stage3.acquisition.java_evidence import evidence_by_proposal
from ai_brain.stage3.acquisition.java_pipeline import (
    TrustBoundProposalBatch,
    verify_trust_bound_batch,
)
from ai_brain.stage3.acquisition.java_production import (
    JavaProductionTrustBatch,
    VerifiedJavaProductionAuthorization,
    assert_java_production_authority,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX,
    JAVA_PRODUCTION_REPLAY_FILENAME,
    build_java_production_replay_artifact,
)
from ai_brain.stage3.acquisition.java_replay import (
    JAVA_REPLAY_DEPENDENCY_PREFIX,
    JAVA_REPLAY_FILENAME,
    build_java_replay_artifact,
)
from ai_brain.stage3.acquisition.java_source_index import bundle_requires_java_policy
from ai_brain.stage3.acquisition.models import (
    KnowledgeProposal,
    ProposalApproval,
    ProposalStatus,
    SourceBundle,
    SourceSegment,
)
from ai_brain.stage3.acquisition.trust import (
    ProposalTrustGateReport,
)
from ai_brain.stage3.capabilities.models import CapabilityRequirement
from ai_brain.stage3.domains.aliases import (
    ALIAS_SEMANTICS_DEPENDENCY_PREFIX,
    ALIAS_SEMANTICS_FILENAME,
    AuthoritativeIdentity,
    ExactReferenceAlias,
    build_alias_semantics,
)
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.manifest import (
    DomainPackManifest,
    ExerciseFamilyBinding,
    SourceBinding,
)
from ai_brain.stage3.domains.pack import (
    ConceptEdge,
    ConceptEdgeKind,
    ConceptGraph,
    ConceptNode,
)
from ai_brain.stage3.domains.validation import hash_without
from ai_brain.stage3.knowledge_ir.records import *
from ai_brain.stage3.knowledge_ir.validation import record_content_hash
from ai_brain.stage3.knowledge_ir.version import (
    CONCEPT_GRAPH_SCHEMA_VERSION,
    DOMAIN_PACK_SCHEMA_VERSION,
    UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
)

_SCHEMA = content_hash({"type": "object", "additionalProperties": False})


def compile_provisional_pack(
    bundle: SourceBundle,
    segments: tuple[SourceSegment, ...],
    proposals: tuple[KnowledgeProposal, ...],
    approvals: tuple[ProposalApproval, ...],
    output: Path,
    *,
    domain_id: str,
    pack_version: str = "0.1.0-provisional",
    trust_gate_report: ProposalTrustGateReport | None = None,
    trust_bound_batch: TrustBoundProposalBatch | None = None,
    production_trust_batch: JavaProductionTrustBatch | None = None,
    production_authorizations: tuple[VerifiedJavaProductionAuthorization, ...] = (),
    store=None,
):
    if output.exists():
        raise FileExistsError("provisional pack target exists")
    java_domain = bundle_requires_java_policy(bundle)
    if java_domain:
        if trust_gate_report is not None:
            if trust_gate_report.precompiler.status == "FAIL":
                raise PrecompilerIdentityConflict(trust_gate_report.precompiler)
            trusted_ids = set(trust_gate_report.trusted_proposal_ids)
            if any(item.proposal_id not in trusted_ids for item in proposals):
                raise ValueError(
                    "Java pack selection is outside trusted proposal closure"
                )
            raise ValueError(
                "legacy Java trust gate report is not a complete trust closure"
            )
        if (trust_bound_batch is None) == (
            production_trust_batch is None
        ) or store is None:
            raise ValueError(
                "Java pack compilation requires exactly one trust batch and store; "
                "a legacy trust gate report is insufficient"
            )
        batch = production_trust_batch or trust_bound_batch
        if production_trust_batch is not None:
            if production_authorizations:
                trusted = {
                    item.proposal_id: item
                    for item in production_trust_batch.trusted_proposals
                }
                if {
                    item.trusted_proposal_id for item in production_authorizations
                } != set(trusted):
                    raise ValueError("production authorization denominator mismatch")
                for authorization in production_authorizations:
                    assert_java_production_authority(
                        trusted[authorization.trusted_proposal_id], authorization
                    )
            else:
                verify_java_production_batch(production_trust_batch, store)
        else:
            verify_trust_bound_batch(
                trust_bound_batch,
                store,
                trust_bound_batch.golden_seal,
                trust_bound_batch.parser_common_artifact,
            )
        if batch.bundle != bundle or batch.segmentation.segments != segments:
            raise ValueError("Java compiler inputs differ from trust closure")
    approved_hashes = {item.approved_proposal_hash for item in approvals}
    selected = tuple(
        sorted(
            (
                item
                for item in proposals
                if item.status is ProposalStatus.APPROVED
                and item.proposal_hash in approved_hashes
            ),
            key=lambda item: item.proposal_id,
        )
    )
    if not selected or len(selected) != len(approvals):
        raise ValueError("pack compilation requires exact approved proposal closure")
    if java_domain:
        batch = production_trust_batch or trust_bound_batch
        trusted = {item.proposal_id: item for item in batch.trusted_proposals}
        approval_by_id = {item.proposal_id: item for item in approvals}
        if {item.proposal_id for item in selected} != set(trusted):
            raise ValueError("Java pack selection is outside trusted proposal closure")
        for item in selected:
            approval = approval_by_id[item.proposal_id]
            if (
                approval.original_proposal_hash
                != trusted[item.proposal_id].proposal_hash
                or approval.approved_proposal_hash != item.proposal_hash
            ):
                raise ValueError(
                    "Java approval does not bind trusted proposal revision"
                )
    segment_by_id = {item.segment_id: item for item in segments}
    alias_semantics = None
    if production_trust_batch is not None:
        report = production_trust_batch.packability_report
        if report.status != "PASS":
            raise ValueError("Java final trust has no successful packability report")
        pack_bindings = {item.proposal_id: item for item in report.bindings}
        aliases = dict(report.exact_references)
        authorities = tuple(
            AuthoritativeIdentity(
                record_id=pack_bindings[item.proposal_id].record_id,
                authority_kind="JAVA_CANONICAL_CALLABLE",
                canonical_value=canonical_json(
                    asdict(pack_bindings[item.proposal_id].identity)
                ),
                identity_hash=pack_bindings[item.proposal_id].identity.identity_hash,
            )
            for item in selected
        )
        alias_semantics = build_alias_semantics(
            authorities,
            tuple(
                ExactReferenceAlias(reference, record_id)
                for reference, record_id in report.exact_references
            ),
            dict(report.search_aliases),
        )
    else:
        aliases = _aliases(domain_id, selected, signature_aware=java_domain)
    records = []
    sources = []
    for proposal in selected:
        knowledge_id = aliases[proposal.proposal_id]
        content = _rewrite_content(proposal.proposed_content, aliases)
        dependencies = tuple(
            _resolve(alias, aliases) for alias in proposal.proposed_dependencies
        )
        applicability = tuple(
            _resolve(alias, aliases)
            for alias in proposal.proposed_applicability
            if alias in aliases
        )
        source_id = f"source.{proposal.proposal_hash[:32]}"
        bound_segments = tuple(segment_by_id[item] for item in proposal.segment_ids)
        document_hashes = tuple(
            sorted(
                {
                    next(
                        document.document_hash
                        for document in bundle.documents
                        if document.document_id == segment.document_id
                    )
                    for segment in bound_segments
                }
            )
        )
        segment_hashes = tuple(item.segment_hash for item in bound_segments)
        if java_domain:
            batch = production_trust_batch or trust_bound_batch
            exact_evidence = evidence_by_proposal(batch.field_evidence)[
                proposal.proposal_id
            ]
            evidence = tuple(
                (item.field_path, item.evidence_hash) for item in exact_evidence
            )
            evidence_hashes = tuple(item.evidence_hash for item in exact_evidence)
            source_hashes = tuple(item.source_span_hash for item in exact_evidence)
            derivation_hashes = tuple(
                item.transformation_hash for item in exact_evidence
            )
            semantic_identity_hashes = tuple(
                sorted({item.semantic_identity_hash for item in exact_evidence})
            )
        else:
            evidence = tuple(
                (f"content.{field}", segment.source_span_hash)
                for segment in bound_segments
                for field in sorted(asdict(content))
            )
            evidence_hashes = tuple(item.source_span_hash for item in bound_segments)
            source_hashes = tuple(
                next(
                    document.bytes_hash
                    for document in bundle.documents
                    if document.document_id == item.document_id
                )
                for item in bound_segments
            )
            derivation_hashes = ()
            semantic_identity_hashes = ()
        source = SourceBinding(
            source_id,
            (),
            semantic_identity_hashes,
            evidence_hashes,
            source_hashes,
            derivation_hashes,
            content_hash((document_hashes, segment_hashes, evidence)),
            document_hashes,
            segment_hashes,
            evidence,
            "",
        )
        sources.append(
            replace(source, binding_hash=hash_without(source, "binding_hash"))
        )
        record = KnowledgeRecord(
            knowledge_id,
            domain_id,
            proposal.proposed_kind,
            UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
            proposal.proposed_epistemic_character,
            (source_id,),
            dependencies,
            applicability,
            proposal.proposed_capabilities,
            bundle.created_at,
            content,
            "",
        )
        records.append(replace(record, content_hash=record_content_hash(record)))
    graph = _concept_graph(tuple(records))
    capabilities = tuple(
        sorted(
            {item for proposal in selected for item in proposal.proposed_capabilities}
        )
    )
    requirements = tuple(
        CapabilityRequirement(item, "^1.0.0", "USER_RUNTIME") for item in capabilities
    )
    families = _exercise_families(tuple(records), capabilities)
    evaluation = {
        "schema_version": 2,
        "test_cases": ["pack.load", "source.dereference", "heldout.bounded"],
        "minimum_pass_rate": "1.0",
        "runtime_network": False,
        "expected_record_count": len(records),
        "source_span_exactness": "1.0",
    }
    replay_artifact = None
    replay_filename = None
    replay_prefix = None
    if java_domain and production_trust_batch is not None:
        replay_artifact = build_java_production_replay_artifact(
            production_trust_batch, store, tuple(sources)
        )
        replay_filename = JAVA_PRODUCTION_REPLAY_FILENAME
        replay_prefix = JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX
    elif java_domain:
        replay_artifact = build_java_replay_artifact(
            trust_bound_batch, store, tuple(sources)
        )
        replay_filename = JAVA_REPLAY_FILENAME
        replay_prefix = JAVA_REPLAY_DEPENDENCY_PREFIX
    dependencies = tuple(
        item
        for item in (
            (
                replay_prefix + replay_artifact["artifact_hash"]
                if replay_artifact
                else None
            ),
            (
                ALIAS_SEMANTICS_DEPENDENCY_PREFIX + alias_semantics.index_hash
                if alias_semantics
                else None
            ),
        )
        if item is not None
    )
    manifest = DomainPackManifest(
        domain_id,
        pack_version,
        DOMAIN_PACK_SCHEMA_VERSION,
        domain_id.replace("-", " "),
        domain_id.replace("-", " "),
        ("ru", "en"),
        bundle.domain_tags,
        tuple(item.content_hash for item in records),
        graph.graph_hash,
        tuple(item.family_hash for item in families),
        tuple(item.binding_hash for item in sources),
        requirements,
        (),
        content_hash(evaluation),
        dependencies,
        "",
        bundle.created_at,
    )
    manifest = replace(
        manifest,
        pack_content_hash=content_hash(
            {
                key: value
                for key, value in asdict(manifest).items()
                if key != "pack_content_hash"
            }
        ),
    )
    output.mkdir(parents=True)
    _write(output / "manifest.json", asdict(manifest))
    (output / "knowledge.jsonl").write_text(
        "".join(canonical_json(asdict(item)) + "\n" for item in records),
        encoding="utf-8",
        newline="\n",
    )
    _write(output / "concept_graph.json", asdict(graph))
    _write(output / "exercise_families.json", [asdict(item) for item in families])
    _write(
        output / "capability_requirements.json", [asdict(item) for item in requirements]
    )
    _write(output / "adapter_bindings.json", [])
    _write(output / "evaluation_manifest.json", evaluation)
    _write(output / "source_bindings.json", [asdict(item) for item in sources])
    if replay_artifact is not None:
        _write(output / replay_filename, replay_artifact)
    if alias_semantics is not None:
        _write(output / ALIAS_SEMANTICS_FILENAME, asdict(alias_semantics))
    _write(
        output / "pack_manifest.json",
        {
            "domain_id": domain_id,
            "pack_content_hash": manifest.pack_content_hash,
            "pack_version": pack_version,
            "schema_version": DOMAIN_PACK_SCHEMA_VERSION,
        },
    )
    pack = load_pack(output)
    if java_domain:
        verify_compiled_java_evidence(
            pack, production_trust_batch or trust_bound_batch, selected
        )
    return pack


def verify_compiled_java_evidence(pack, batch, selected_proposals=None) -> None:
    selected = selected_proposals or batch.trusted_proposals
    evidence_map = evidence_by_proposal(batch.field_evidence)
    if len(pack.source_bindings) != len(selected):
        raise ValueError("compiled Java evidence binding count mismatch")
    for proposal, binding in zip(selected, pack.source_bindings, strict=True):
        evidence = evidence_map[proposal.proposal_id]
        if (
            binding.evidence_hashes != tuple(item.evidence_hash for item in evidence)
            or binding.source_hashes
            != tuple(item.source_span_hash for item in evidence)
            or binding.derivation_hashes
            != tuple(item.transformation_hash for item in evidence)
            or binding.claim_refs
            != tuple(sorted({item.semantic_identity_hash for item in evidence}))
            or binding.field_evidence
            != tuple((item.field_path, item.evidence_hash) for item in evidence)
        ):
            raise ValueError(
                "compiled Java source binding lost exact evidence receipts"
            )


def _aliases(
    domain_id: str,
    proposals: tuple[KnowledgeProposal, ...],
    *,
    signature_aware: bool = False,
) -> dict[str, str]:
    result = {}
    for proposal in proposals:
        identity = f"{domain_id}.knowledge.{proposal.proposal_hash[:32]}"
        result[proposal.proposal_id] = identity
        for alias in _content_aliases(
            proposal.proposed_content, signature_aware=signature_aware
        ):
            if alias in result and result[alias] != identity:
                raise ValueError(
                    "approved proposals contain a conflicting semantic identity"
                )
            result[alias] = identity
    return result


def _content_aliases(
    content: KnowledgeContent, *, signature_aware: bool = False
) -> tuple[str, ...]:
    if isinstance(content, ConceptContent):
        return (_slug(content.canonical_name_en),)
    if isinstance(content, DefinitionContent):
        return (content.term_id,)
    if isinstance(content, EntityTypeContent):
        return (content.entity_type_id,)
    if isinstance(content, QuantityContent):
        return (content.quantity_type.quantity_type_id,)
    if isinstance(content, UnitDefinitionContent):
        return (content.unit.unit_id,)
    if isinstance(content, ClaimSchemaContent) and content.receiver_type:
        if signature_aware:
            parameters = ",".join(value for _, value in content.parameters)
            return (
                _slug(f"{content.receiver_type}.{content.predicate_id}({parameters})"),
            )
        return (_slug(f"{content.receiver_type}.{content.predicate_id}"),)
    return ()


def _rewrite_content(
    content: KnowledgeContent, aliases: dict[str, str]
) -> KnowledgeContent:
    if isinstance(content, RelationContent):
        return replace(
            content,
            subject_id=_resolve(content.subject_id, aliases),
            object_id=_resolve(content.object_id, aliases),
        )
    if isinstance(content, TemporalRelationContent):
        return replace(
            content,
            subject_id=_resolve(content.subject_id, aliases),
            object_id=_resolve(content.object_id, aliases),
        )
    if isinstance(content, SpatialRelationContent):
        return replace(
            content,
            subject_id=_resolve(content.subject_id, aliases),
            object_id=_resolve(content.object_id, aliases),
        )
    if isinstance(content, CausalClaimContent):
        return replace(
            content,
            cause_id=_resolve(content.cause_id, aliases),
            effect_id=_resolve(content.effect_id, aliases),
        )
    if isinstance(content, InterpretationContent):
        return replace(
            content,
            supported_record_ids=tuple(
                _resolve(item, aliases) for item in content.supported_record_ids
            ),
            contrast_record_ids=tuple(
                _resolve(item, aliases) for item in content.contrast_record_ids
            ),
        )
    if isinstance(content, CounterexampleContent):
        return replace(
            content,
            refuted_record_ids=tuple(
                _resolve(item, aliases) for item in content.refuted_record_ids
            ),
        )
    if isinstance(content, TestCaseContent):
        return replace(
            content, target_record_id=_resolve(content.target_record_id, aliases)
        )
    if isinstance(content, ExceptionRuleContent):
        return replace(
            content,
            exception_condition_ids=tuple(
                _resolve(item, aliases) for item in content.exception_condition_ids
            ),
        )
    return content


def _resolve(value: str, aliases: dict[str, str]) -> str:
    try:
        return aliases[value]
    except KeyError as error:
        raise ValueError(f"approved proposal has unresolved target: {value}") from error


def _concept_graph(records: tuple[KnowledgeRecord, ...]) -> ConceptGraph:
    nodes = []
    ids = set()
    for record in records:
        if isinstance(
            record.content,
            (ConceptContent, EntityTypeContent, QuantityContent, UnitDefinitionContent),
        ):
            name = _display_name(record.content)
            node = ConceptNode(record.knowledge_id, record.knowledge_id, name, name, "")
            nodes.append(replace(node, node_hash=hash_without(node, "node_hash")))
            ids.add(record.knowledge_id)
    edges = []
    for record in records:
        if (
            isinstance(record.content, RelationContent)
            and record.content.subject_id in ids
            and record.content.object_id in ids
        ):
            kind = (
                ConceptEdgeKind.IS_A
                if record.kind is KnowledgeKind.TAXONOMY_EDGE
                else ConceptEdgeKind.PART_OF
            )
            edge = ConceptEdge(
                record.content.subject_id, record.content.object_id, kind, None, ""
            )
            edges.append(replace(edge, edge_hash=hash_without(edge, "edge_hash")))
    graph = ConceptGraph(tuple(nodes), tuple(edges), CONCEPT_GRAPH_SCHEMA_VERSION, "")
    return replace(graph, graph_hash=hash_without(graph, "graph_hash"))


def _exercise_families(
    records: tuple[KnowledgeRecord, ...], capabilities: tuple[str, ...]
) -> tuple[ExerciseFamilyBinding, ...]:
    concepts = tuple(
        item.knowledge_id
        for item in records
        if isinstance(
            item.content, (ConceptContent, EntityTypeContent, QuantityContent)
        )
    )
    if not concepts:
        return ()
    family = ExerciseFamilyBinding(
        "GENERIC_APPLICATION",
        concepts[:64],
        capabilities,
        _SCHEMA,
        _SCHEMA,
        ("FOUNDATIONAL", "TRANSFER"),
        "generic.catalog.provider.v1",
        capabilities[0] if capabilities else "generic.descriptive.grading.v1",
        capabilities[0] if capabilities else "generic.descriptive.explanation.v1",
        "SOURCE_SEGMENT_EXACT",
        "",
    )
    return (replace(family, family_hash=hash_without(family, "family_hash")),)


def _display_name(content) -> str:
    if isinstance(content, ConceptContent):
        return content.canonical_name_en
    if isinstance(content, EntityTypeContent):
        return content.canonical_name_en
    if isinstance(content, QuantityContent):
        return content.canonical_name_en
    return content.canonical_name_en


def _slug(value: str) -> str:
    return "-".join(value.casefold().split())


def _write(path: Path, value) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
