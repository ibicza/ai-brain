"""Fine-grained content-addressed diagnostics for Java production."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import content_hash

JAVA_COMPONENT_MANIFEST_SCHEMA_VERSION = 1
JAVA_COMPONENT_STAGE_ORDER = (
    "release_identity",
    "source_content_manifest",
    "bundle",
    "documents",
    "type_universe",
    "source_unit_index",
    "declarations",
    "physical_declarations",
    "segmentation",
    "proposals",
    "semantic_identities",
    "evidence_requirements",
    "evidence_receipts",
    "conflicts",
    "packability",
    "decisions",
    "trusted_proposals",
    "closure",
    "candidate_pack",
)


@dataclass(frozen=True)
class JavaProductionComponent:
    stage: str
    component_hash: str
    items: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class JavaProductionComponentManifest:
    schema_version: int
    components: tuple[JavaProductionComponent, ...]
    platform_independent: bool
    manifest_hash: str


@dataclass(frozen=True)
class JavaComponentDifference:
    first_differing_stage: str
    first_differing_identity: str | None
    first_differing_field_path: str | None
    left_hash: str | None
    right_hash: str | None
    dependency_chain: tuple[str, ...]
    difference_count: int


def build_java_production_component_manifest(batch, candidate_pack=None):
    documents = tuple(
        sorted(
            batch.bundle.documents, key=lambda item: item.relative_path.encode("utf-8")
        )
    )
    declarations = tuple(batch.source_index.declarations)
    source_units = {}
    for item in declarations:
        source_units.setdefault(item.source_unit_id, []).append(item.declaration_hash)
    binding_identity = {
        item.proposal_id: item.identity.identity_hash
        for item in batch.packability_report.bindings
    }
    components = (
        _component(
            "release_identity", (("release", batch.release_identity.identity_hash),)
        ),
        _component(
            "source_content_manifest",
            tuple(
                (
                    item.relative_path,
                    content_hash(
                        (item.relative_path, item.bytes_hash, item.canonical_text_hash)
                    ),
                )
                for item in documents
            ),
        ),
        _component("bundle", ((batch.bundle.bundle_id, batch.bundle.bundle_hash),)),
        _component(
            "documents",
            tuple((item.document_id, item.document_hash) for item in documents),
        ),
        _component(
            "type_universe",
            (("type_universe", batch.source_index.type_universe_manifest_hash),),
        ),
        _component(
            "source_unit_index",
            tuple(
                (key, content_hash(tuple(values)))
                for key, values in sorted(source_units.items())
            ),
        ),
        _component(
            "declarations",
            tuple((item.node_id, item.declaration_hash) for item in declarations),
        ),
        _component(
            "physical_declarations",
            tuple(
                (
                    f"{item.source_unit_id}:{item.declaration_span.byte_start}-{item.declaration_span.byte_end}",
                    item.source_span_hash,
                )
                for item in declarations
            ),
        ),
        _component(
            "segmentation",
            tuple(
                (item.segment_id, item.segment_hash)
                for item in batch.segmentation.segments
            ),
        ),
        _component(
            "proposals",
            tuple(
                (item.proposal_id, item.proposal_hash)
                for item in batch.proposal_batch.proposals
            ),
        ),
        _component("semantic_identities", tuple(sorted(binding_identity.items()))),
        _component(
            "evidence_requirements",
            tuple(
                (f"{item.proposal_id}:{item.field_path}", item.requirement_hash)
                for item in batch.field_evidence.evidence
            ),
        ),
        _component(
            "evidence_receipts",
            tuple(
                (f"{item.proposal_id}:{item.field_path}", item.evidence_hash)
                for item in batch.field_evidence.evidence
            ),
        ),
        _component(
            "conflicts",
            tuple(
                (item.conflict_hash, item.conflict_hash)
                for item in batch.conflict_report.conflicts
            ),
        ),
        _component(
            "packability",
            (("packability", batch.packability_report.report_hash),),
        ),
        _component(
            "decisions",
            tuple((item.proposal_id, item.decision_hash) for item in batch.decisions),
        ),
        _component(
            "trusted_proposals",
            tuple(
                (item.proposal_id, item.proposal_hash)
                for item in batch.trusted_proposals
            ),
        ),
        _component("closure", (("closure", batch.closure.closure_hash),)),
        _component(
            "candidate_pack",
            (
                (
                    "pack",
                    candidate_pack.manifest.pack_content_hash
                    if candidate_pack is not None
                    else content_hash(None),
                ),
            ),
        ),
    )
    body = {
        "schema_version": JAVA_COMPONENT_MANIFEST_SCHEMA_VERSION,
        "components": components,
        "platform_independent": True,
    }
    return JavaProductionComponentManifest(**body, manifest_hash=content_hash(body))


def compare_java_component_manifests(left, right) -> JavaComponentDifference:
    left_components = {item.stage: item for item in left.components}
    right_components = {item.stage: item for item in right.components}
    differing = tuple(
        stage
        for stage in JAVA_COMPONENT_STAGE_ORDER
        if left_components.get(stage) != right_components.get(stage)
    )
    if not differing:
        return JavaComponentDifference("NONE", None, None, None, None, (), 0)
    stage = differing[0]
    left_stage = left_components.get(stage)
    right_stage = right_components.get(stage)
    left_items = dict(left_stage.items) if left_stage else {}
    right_items = dict(right_stage.items) if right_stage else {}
    identity = next(
        (
            key
            for key in sorted(set(left_items) | set(right_items))
            if left_items.get(key) != right_items.get(key)
        ),
        None,
    )
    index = JAVA_COMPONENT_STAGE_ORDER.index(stage)
    return JavaComponentDifference(
        stage,
        identity,
        f"components.{stage}.items[{identity}]" if identity else f"components.{stage}",
        left_items.get(identity) if identity else None,
        right_items.get(identity) if identity else None,
        JAVA_COMPONENT_STAGE_ORDER[: index + 1],
        len(differing),
    )


def verify_java_component_manifest(value) -> None:
    body = asdict(value)
    claimed = body.pop("manifest_hash")
    if (
        value.schema_version != JAVA_COMPONENT_MANIFEST_SCHEMA_VERSION
        or tuple(item.stage for item in value.components) != JAVA_COMPONENT_STAGE_ORDER
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid Java production component manifest")


def _component(stage, items):
    values = tuple(sorted(items))
    return JavaProductionComponent(stage, content_hash(values), values)
