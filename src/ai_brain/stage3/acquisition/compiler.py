"""Deterministic compilation of reviewed proposals into a provisional pack."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.evaluation import build_pack_evaluation_manifest
from ai_brain.stage3.acquisition.models import (
    FieldSourceEvidence,
    KnowledgeProposal,
    ProposalApproval,
    ProposalStatus,
    SourceBundle,
    SourceSegment,
)
from ai_brain.stage3.capabilities.models import CapabilityRequirement
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
    field_evidence: tuple[FieldSourceEvidence, ...] | None = None,
):
    if output.exists():
        raise FileExistsError("provisional pack target exists")
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
    if len(selected) != len(approvals) or (not selected and field_evidence is None):
        raise ValueError("pack compilation requires exact approved proposal closure")
    segment_by_id = {item.segment_id: item for item in segments}
    aliases = _aliases(domain_id, selected, strict_overloads=field_evidence is not None)
    records = []
    sources = []
    for proposal in selected:
        knowledge_id = aliases[proposal.proposal_id]
        content = _rewrite_content(proposal.proposed_content, aliases)
        dependencies = tuple(
            _resolve(alias, aliases) for alias in proposal.proposed_dependencies
        )
        applicability = _compile_applicability(proposal, aliases, field_evidence)
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
        if field_evidence is None:
            evidence = tuple(
                (f"content.{field}", segment.source_span_hash)
                for segment in bound_segments
                for field in sorted(asdict(content))
            )
        else:
            evidence = tuple(
                (item.field_path, item.evidence_hash)
                for item in field_evidence
                if item.proposal_id == proposal.proposal_id
            )
            if not evidence:
                raise ValueError("approved proposal has no field source evidence")
        source = SourceBinding(
            source_id,
            (),
            (),
            tuple(item.source_span_hash for item in bound_segments),
            tuple(
                next(
                    document.bytes_hash
                    for document in bundle.documents
                    if document.document_id == item.document_id
                )
                for item in bound_segments
            ),
            (),
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
    graph = _concept_graph(tuple(records), include_all=field_evidence is not None)
    capabilities = tuple(
        sorted(
            {item for proposal in selected for item in proposal.proposed_capabilities}
            | (
                {
                    "generic.record_query.v1",
                    "generic.taxonomy_query.v1",
                    "generic.temporal_query.v1",
                    "generic.api_contract_query.v1",
                    "generic.typed_scalar_equation_solver.v1",
                    "generic.unit_conversion.v1",
                    "generic.source_backed_explanation.v1",
                    "generic.exact_grading.v1",
                }
                if field_evidence is not None
                else set()
            )
        )
    )
    requirements = tuple(
        CapabilityRequirement(item, "^1.0.0", "USER_RUNTIME") for item in capabilities
    )
    families = _exercise_families(
        tuple(records), capabilities, strict_runtime=field_evidence is not None
    )
    evaluation = (
        {
            "schema_version": 2,
            "test_cases": ["pack.load", "source.dereference", "heldout.bounded"],
            "minimum_pass_rate": "1.0",
            "runtime_network": False,
            "expected_record_count": len(records),
            "source_span_exactness": "1.0",
        }
        if field_evidence is None
        else build_pack_evaluation_manifest(tuple(records), tuple(sources))
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
        (),
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
    _write(
        output / "pack_manifest.json",
        {
            "domain_id": domain_id,
            "pack_content_hash": manifest.pack_content_hash,
            "pack_version": pack_version,
            "schema_version": DOMAIN_PACK_SCHEMA_VERSION,
        },
    )
    return load_pack(output)


def _aliases(
    domain_id: str,
    proposals: tuple[KnowledgeProposal, ...],
    *,
    strict_overloads: bool = False,
) -> dict[str, str]:
    result = {}
    for proposal in proposals:
        identity = f"{domain_id}.knowledge.{proposal.proposal_hash[:32]}"
        result[proposal.proposal_id] = identity
        for alias in _content_aliases(
            proposal.proposed_content, strict_overloads=strict_overloads
        ):
            if alias in result and result[alias] != identity:
                raise ValueError(
                    "approved proposals contain a conflicting semantic identity"
                )
            result[alias] = identity
    return result


def _content_aliases(
    content: KnowledgeContent, *, strict_overloads: bool = False
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
        if strict_overloads:
            signature = ".".join(value for _, value in content.parameters) or "none"
            return (
                _slug(f"{content.receiver_type}.{content.predicate_id}.{signature}"),
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


def _compile_applicability(
    proposal: KnowledgeProposal,
    aliases: dict[str, str],
    field_evidence: tuple[FieldSourceEvidence, ...] | None,
) -> tuple[str, ...]:
    if field_evidence is None:
        # Preserve the exact M-32 pack compiler output for old artifacts.
        return tuple(
            _resolve(alias, aliases)
            for alias in proposal.proposed_applicability
            if alias in aliases
        )
    evidence_paths = {
        item.field_path
        for item in field_evidence
        if item.proposal_id == proposal.proposal_id
    }
    resolved = []
    inline_conditions = set()
    if isinstance(proposal.proposed_content, RuleContent):
        inline_conditions = set(proposal.proposed_content.applicability.preconditions)
    for index, item in enumerate(proposal.proposed_applicability):
        if item in aliases:
            resolved.append(_resolve(item, aliases))
        elif item in inline_conditions:
            if f"applicability[{index}]" not in evidence_paths:
                raise ValueError("inline applicability lacks exact source evidence")
        else:
            raise ValueError(f"approved proposal has unresolved applicability: {item}")
    return tuple(resolved)


def _concept_graph(
    records: tuple[KnowledgeRecord, ...], *, include_all: bool = False
) -> ConceptGraph:
    nodes = []
    ids = set()
    for record in records:
        if include_all or isinstance(
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
    records: tuple[KnowledgeRecord, ...],
    capabilities: tuple[str, ...],
    *,
    strict_runtime: bool = False,
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
        "generic.exact_grading.v1"
        if strict_runtime
        else capabilities[0]
        if capabilities
        else "generic.descriptive.grading.v1",
        "generic.source_backed_explanation.v1"
        if strict_runtime
        else capabilities[0]
        if capabilities
        else "generic.descriptive.explanation.v1",
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
    if isinstance(content, UnitDefinitionContent):
        return content.canonical_name_en
    if isinstance(content, DefinitionContent):
        return content.term_id
    if isinstance(content, ClaimSchemaContent):
        return ".".join(
            item for item in (content.receiver_type, content.predicate_id) if item
        )
    if isinstance(content, RelationContent):
        return f"{content.subject_id} {content.predicate_id} {content.object_id}"
    if isinstance(content, TemporalRelationContent):
        return f"{content.subject_id} {content.predicate_id} {content.object_id}"
    if isinstance(content, InterpretationContent):
        return content.perspective
    return type(content).__name__.removesuffix("Content")


def _slug(value: str) -> str:
    return "-".join(value.casefold().split())


def _write(path: Path, value) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
