"""Build deterministic M-32 provider, pack, source and golden artifacts."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.clarifications import generate_clarifications
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.conflicts import detect_conflicts
from ai_brain.stage3.acquisition.models import ProposalStatus, ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.proposals import propose_knowledge
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.segmentation import segment_bundle
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.verification import verify_proposals
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityRequirement,
    CapabilityStatus,
    ProviderType,
)
from ai_brain.stage3.capabilities.persistence import save_registry
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.capabilities.resolution import resolve_capability
from ai_brain.stage3.capabilities.validation import descriptor_hash
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
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
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.validation import hash_without, validate_pack
from ai_brain.stage3.knowledge_ir.records import (
    Applicability,
    ConceptContent,
    EpistemicCharacter,
    ExerciseFamilyContent,
    Expression,
    ExpressionKind,
    KnowledgeKind,
    KnowledgeRecord,
    RuleContent,
    ValueTypeKind,
    ValueTypeRef,
    VariableBinding,
)
from ai_brain.stage3.knowledge_ir.validation import record_content_hash
from ai_brain.stage3.knowledge_ir.version import (
    CONCEPT_GRAPH_SCHEMA_VERSION,
    DOMAIN_PACK_SCHEMA_VERSION,
    UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
)
from ai_brain.stage3.providers.models import ProviderSource, ProviderStatus
from ai_brain.stage3.providers.persistence import save_provider_registry
from ai_brain.stage3.providers.registry import (
    ProviderRegistry,
    make_provider_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-08-29T00:00:00Z"
SCHEMA_IN = "schemas/stage3/provider_input_v2.schema.json"
SCHEMA_OUT = "schemas/stage3/provider_output_v2.schema.json"
RESOURCE = "schemas/stage3/provider_resource_policy_v2.json"
ZERO_SCHEMA = content_hash({"type": "object", "additionalProperties": False})


def main() -> int:
    sources, goldens = _write_fixture_sources()
    providers, capabilities = _build_authority()
    _build_platform_packs(providers, capabilities)
    acquisition = _build_acquisition(sources, goldens)
    _install_acquired_packs(providers, capabilities, acquisition)
    print(
        canonical_json(
            {
                "status": "BUILT",
                "source_bundles": len(acquisition),
                "providers": len(providers.manifests),
                "capabilities": len(capabilities.descriptors),
            }
        )
    )
    return 0


def _write_fixture_sources():
    root = ROOT / "tests/fixtures/acquisition/m32"
    source_root = root / "sources"
    golden_root = root / "goldens"
    source_root.mkdir(parents=True, exist_ok=True)
    golden_root.mkdir(parents=True, exist_ok=True)
    outputs = {}
    goldens = {}

    lines = ["# Reviewed constant-acceleration notes"]
    expected = []

    def add(line, kind):
        lines.append(line)
        expected.append(
            {
                "document_id": "m32-kinematics.document.001",
                "line_start": len(lines),
                "kind": kind,
            }
        )

    for name in ("motion", "constant-acceleration", "kinematic-state"):
        add(f"@concept {name} | Reviewed kinematics concept {name}.", "CONCEPT")
    add("@quantity displacement | L=1 | m", "QUANTITY_TYPE")
    add("@quantity elapsed-time | T=1 | s", "QUANTITY_TYPE")
    add("@quantity velocity | L=1,T=-1 | m/s", "QUANTITY_TYPE")
    add("@quantity acceleration | L=1,T=-2 | m/s^2", "QUANTITY_TYPE")
    add(
        "@equation v = v0 + a*t | when: constant acceleration | vars: v:quantity[L=1,T=-1];v0:quantity[L=1,T=-1];a:quantity[L=1,T=-2];t:quantity[T=1]",
        "EQUATION_RULE",
    )
    for index in range(120):
        add(
            f"@definition reviewed-kinematics-term-{index:03d} | A reviewed bounded glossary item {index:03d}.",
            "DEFINITION",
        )
    for index in range(12):
        add(
            f"@example statement: Worked exact example {index}; refs: velocity",
            "EXAMPLE",
        )
    path = source_root / "kinematics.md"
    _write_text(path, "\n".join(lines) + "\n")
    outputs["kinematics"] = path
    goldens["kinematics"] = {
        "expected": expected,
        "field_exactness": "1.0",
        "capability_detection": "1.0",
        "conflict_detection": "1.0",
    }

    lines = ["Reviewed taxonomy fixture"]
    expected = []

    def add_tax(line, kind):
        lines.append(line)
        expected.append(
            {
                "document_id": "m32-taxonomy.document.001",
                "line_start": len(lines),
                "kind": kind,
            }
        )

    for index in range(110):
        add_tax(f"@entity taxon-{index:03d} | Taxon {index:03d}", "ENTITY_TYPE")
    for index in range(1, 110):
        add_tax(
            f"@taxonomy taxon-{index:03d} -> taxon-{(index - 1) // 2:03d}",
            "TAXONOMY_EDGE",
        )
    for index in range(35):
        add_tax(
            f"@definition taxon-definition-{index:03d} | Reviewed taxonomic definition {index:03d}.",
            "DEFINITION",
        )
    path = source_root / "taxonomy.txt"
    _write_text(path, "\n".join(lines) + "\n")
    outputs["taxonomy"] = path
    goldens["taxonomy"] = {
        "expected": expected,
        "field_exactness": "1.0",
        "capability_detection": "1.0",
        "conflict_detection": "1.0",
    }

    lines = ["# Historical source set"]
    expected = []

    def add_history(line, kind):
        lines.append(line)
        expected.append(
            {
                "document_id": "m32-history.document.001",
                "line_start": len(lines),
                "kind": kind,
            }
        )

    for index in range(65):
        add_history(f"@concept event-{index:03d} | Dated event {index:03d}.", "CONCEPT")
    for index in range(64):
        add_history(
            f"@event subject:event-{index:03d} | predicate:precedes | object:event-{index + 1:03d} | start:19{index:02d}-01-01T00:00:00Z | end:19{index:02d}-12-31T00:00:00Z",
            "TEMPORAL_RELATION",
        )
    add_history(
        "@interpretation perspective:institutional | supports:event-010,event-011 | claim:Institutional continuity shaped the transition.",
        "INTERPRETATION",
    )
    add_history(
        "@interpretation perspective:material | supports:event-010,event-011 | claim:Material constraints shaped the transition.",
        "INTERPRETATION",
    )
    add_history(
        "@causal status:contested | cause:event-010 | effect:event-011 | claim:The first event caused the second.",
        "CAUSAL_RULE",
    )
    path = source_root / "history.md"
    _write_text(path, "\n".join(lines) + "\n")
    outputs["history"] = path
    goldens["history"] = {
        "expected": expected,
        "field_exactness": "1.0",
        "capability_detection": "1.0",
        "conflict_detection": "1.0",
    }

    lines = [
        "<!doctype html>",
        '<html><head><meta name="javadoc" content="fixture"></head><body>',
    ]
    expected = []
    for index in range(80):
        lines.append(
            f"<p>@api public &lt;T&gt; T Fixture{index:03d}.get(int index) throws IndexOutOfBoundsException | pre: index is within the documented range | post: returns the selected value | example: fixture.get(0)</p>"
        )
        expected.append(
            {
                "document_id": "m32-javadoc.document.001",
                "line_start": len(lines),
                "kind": "CLAIM_SCHEMA",
            }
        )
    for index in range(30):
        lines.append(
            f"<p>@test target:fixture{index:03d}.get | inputs:index=0 | expected:value=reviewed</p>"
        )
        expected.append(
            {
                "document_id": "m32-javadoc.document.001",
                "line_start": len(lines),
                "kind": "TEST_CASE",
            }
        )
    lines.append("</body></html>")
    path = source_root / "javadoc.html"
    _write_text(path, "\n".join(lines) + "\n")
    outputs["javadoc"] = path
    goldens["javadoc"] = {
        "expected": expected,
        "field_exactness": "1.0",
        "capability_detection": "1.0",
        "conflict_detection": "1.0",
    }

    for name, value in goldens.items():
        _write_json(golden_root / f"{name}.json", value)
    heldout = {
        "kinematics": [
            {"unknown": "v", "known": {"v0": "3", "a": "2", "t": "4"}, "expected": "11"}
            for _ in range(125)
        ],
        "taxonomy": [
            {
                "child": f"taxon-{(index % 109) + 1:03d}",
                "ancestor": "taxon-000",
            }
            for index in range(125)
        ],
        "history": [
            {
                "before": f"event-{index % 64:03d}",
                "after": f"event-{(index % 64) + 1:03d}",
            }
            for index in range(125)
        ],
        "javadoc": [
            {
                "method": f"Fixture{index % 80:03d}.get",
                "exception": "IndexOutOfBoundsException",
            }
            for index in range(125)
        ],
    }
    _write_json(golden_root / "heldout_500.json", heldout)
    return outputs, goldens


def _build_authority():
    input_hash = bytes_hash((ROOT / SCHEMA_IN).read_bytes())
    output_hash = bytes_hash((ROOT / SCHEMA_OUT).read_bytes())
    resource_hash = bytes_hash((ROOT / RESOURCE).read_bytes())
    specs = (
        (
            "chemistry.education.graph_adapter",
            ProviderType.ADAPTER,
            "src/ai_brain/stage2/domains/chemistry/education/graph_adapter.py",
            (),
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
            (),
        ),
        (
            "chemistry.formula_parser",
            ProviderType.PARSER,
            "src/ai_brain/stage2/domains/chemistry/formula_parser.py",
            (),
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
            (),
        ),
        (
            "chemistry.formula_composition",
            ProviderType.TOOL,
            "src/ai_brain/stage2/domains/chemistry/tools.py",
            ("src/ai_brain/stage2/domains/chemistry/calculations.py",),
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
            ("chemistry_formula_composition",),
        ),
        (
            "chemistry.molar_mass",
            ProviderType.TOOL,
            "src/ai_brain/stage2/domains/chemistry/tools.py",
            ("src/ai_brain/stage2/domains/chemistry/calculations.py",),
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
            ("chemistry_molar_mass",),
        ),
        (
            "chemistry.mass_amount",
            ProviderType.TOOL,
            "src/ai_brain/stage2/domains/chemistry/tools.py",
            ("src/ai_brain/stage2/domains/chemistry/calculations.py",),
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
            ("chemistry_mass_amount",),
        ),
        (
            "chemistry.entity_amount",
            ProviderType.TOOL,
            "src/ai_brain/stage2/domains/chemistry/tools.py",
            ("src/ai_brain/stage2/domains/chemistry/calculations.py",),
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
            ("chemistry_entity_amount",),
        ),
        (
            "stage3.concept_graph",
            ProviderType.VERIFIER,
            "src/ai_brain/stage3/domains/validation.py",
            ("src/ai_brain/stage3/knowledge_ir/validation.py",),
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
            (),
        ),
        (
            "stage3.expression_validator",
            ProviderType.VERIFIER,
            "src/ai_brain/stage3/knowledge_ir/validation.py",
            ("src/ai_brain/stage3/knowledge_ir/records.py",),
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
            (),
        ),
        (
            "generic.scalar_equation_solver",
            ProviderType.SOLVER,
            "src/ai_brain/stage3/capabilities/scalar_equation_solver.py",
            ("src/ai_brain/stage3/knowledge_ir/validation.py",),
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
            (),
        ),
    )
    manifests = []
    for (
        provider_id,
        provider_type,
        source_path,
        helpers,
        contexts,
        authorities,
    ) in specs:
        manifests.append(
            make_provider_manifest(
                provider_id=provider_id,
                version="1.0.0",
                provider_type=provider_type,
                implementation_sources=(
                    ProviderSource(
                        source_path,
                        "IMPLEMENTATION",
                        bytes_hash((ROOT / source_path).read_bytes()),
                    ),
                ),
                transitive_helpers=tuple(
                    ProviderSource(
                        path,
                        "TRANSITIVE_HELPER",
                        bytes_hash((ROOT / path).read_bytes()),
                    )
                    for path in helpers
                ),
                resource_policy_path=RESOURCE,
                resource_policy_hash=resource_hash,
                input_schema_path=SCHEMA_IN,
                input_schema_hash=input_hash,
                output_schema_path=SCHEMA_OUT,
                output_schema_hash=output_hash,
                allowed_execution_contexts=contexts,
                underlying_authority_ids=authorities,
                status=ProviderStatus.ACTIVE,
            )
        )
    provider_registry = ProviderRegistry.build(ROOT, tuple(manifests))
    save_provider_registry(
        provider_registry, ROOT / "artifacts/stage3/providers/registry_v2.json"
    )
    cap_specs = (
        (
            "chemistry.element_fact_retrieval.v1",
            CapabilityKind.FACT_RETRIEVAL,
            "chemistry.education.graph_adapter",
            AuthorityClass.READ_ONLY_EXACT,
            (),
        ),
        (
            "chemistry.formula_parsing.v1",
            CapabilityKind.FORMULA_PARSING,
            "chemistry.formula_parser",
            AuthorityClass.READ_ONLY_EXACT,
            (),
        ),
        (
            "chemistry.formula_composition.v1",
            CapabilityKind.QUANTITY_ARITHMETIC,
            "chemistry.formula_composition",
            AuthorityClass.CONFIRMATION_REQUIRED,
            (),
        ),
        (
            "chemistry.molar_mass.v2",
            CapabilityKind.QUANTITY_ARITHMETIC,
            "chemistry.molar_mass",
            AuthorityClass.CONFIRMATION_REQUIRED,
            (),
        ),
        (
            "chemistry.mass_amount_conversion.v2",
            CapabilityKind.UNIT_CONVERSION,
            "chemistry.mass_amount",
            AuthorityClass.CONFIRMATION_REQUIRED,
            (),
        ),
        (
            "chemistry.entity_amount_conversion.v2",
            CapabilityKind.QUANTITY_ARITHMETIC,
            "chemistry.entity_amount",
            AuthorityClass.CONFIRMATION_REQUIRED,
            (),
        ),
        (
            "generic.taxonomy_reasoning.v1",
            CapabilityKind.TAXONOMY_REASONING,
            "stage3.concept_graph",
            AuthorityClass.READ_ONLY_EXACT,
            (),
        ),
        (
            "generic.equation_validation.v1",
            CapabilityKind.EQUATION_EVALUATION,
            "stage3.expression_validator",
            AuthorityClass.READ_ONLY_EXACT,
            (),
        ),
        (
            "generic.scalar_equation_solver.v1",
            CapabilityKind.EQUATION_EVALUATION,
            "generic.scalar_equation_solver",
            AuthorityClass.READ_ONLY_EXACT,
            ("generic.equation_validation.v1",),
        ),
    )
    descriptors = []
    for capability_id, kind, provider_id, authority, dependencies in cap_specs:
        provider = provider_registry.manifest(provider_id, "1.0.0")
        implementation_hash = content_hash(
            tuple(
                item.bytes_hash
                for item in (
                    *provider.implementation_sources,
                    *provider.transitive_helpers,
                )
            )
        )
        descriptor = CapabilityDescriptor(
            capability_id,
            "1.0.0",
            kind,
            capability_id,
            capability_id,
            provider.input_schema_hash,
            provider.output_schema_hash,
            True,
            authority,
            provider.provider_type,
            provider.provider_id,
            provider.version,
            provider.manifest_hash,
            implementation_hash,
            dependencies,
            provider.allowed_execution_contexts,
            provider.resource_policy_hash,
            CapabilityStatus.ACTIVE,
            "",
        )
        descriptors.append(
            replace(descriptor, descriptor_hash=descriptor_hash(descriptor))
        )
    capability_registry = CapabilityRegistry.build(
        tuple(descriptors), provider_registry
    )
    save_registry(
        capability_registry,
        ROOT / "artifacts/stage3/capabilities/registry_v2.json",
        provider_registry,
    )
    return provider_registry, capability_registry


def _build_platform_packs(providers, capabilities):
    roots = {
        "chemistry": ROOT / "artifacts/domains/chemistry/generic-v2",
        "fixture-taxonomy": ROOT / "tests/fixtures/domains/taxonomy-v2",
        "fixture-quantity-equation": ROOT
        / "tests/fixtures/domains/quantity-equation-v2",
    }
    for path in roots.values():
        if path.exists():
            shutil.rmtree(path)
    chemistry_caps = (
        "chemistry.element_fact_retrieval.v1",
        "chemistry.formula_parsing.v1",
        "chemistry.formula_composition.v1",
        "chemistry.molar_mass.v2",
        "chemistry.mass_amount_conversion.v2",
        "chemistry.entity_amount_conversion.v2",
    )
    legacy_graph = json.loads(
        (ROOT / "artifacts/domains/chemistry/generic-v1/concept_graph.json").read_text(
            encoding="utf-8"
        )
    )
    legacy_families = json.loads(
        (
            ROOT / "artifacts/domains/chemistry/generic-v1/exercise_families.json"
        ).read_text(encoding="utf-8")
    )
    _make_platform_pack(
        "chemistry",
        "generic-v2",
        tuple(item["concept_id"] for item in legacy_graph["nodes"]),
        chemistry_caps,
        roots["chemistry"],
        families=tuple(
            (
                item["family_id"],
                tuple(item["concept_ids"]),
                tuple(item["difficulty_structure"]),
            )
            for item in legacy_families
        ),
    )
    _make_platform_pack(
        "fixture-taxonomy",
        "2.0.0",
        ("LIVING_THING", "PLANT", "TREE"),
        ("generic.taxonomy_reasoning.v1",),
        roots["fixture-taxonomy"],
        edges=(("TREE", "PLANT"), ("PLANT", "LIVING_THING")),
    )
    _make_platform_pack(
        "fixture-quantity-equation",
        "2.0.0",
        ("QUANTITY", "UNIT", "EQUATION"),
        ("generic.equation_validation.v1",),
        roots["fixture-quantity-equation"],
        equation=True,
    )
    registry_root = ROOT / "artifacts/stage3/installed-domains-v2"
    if registry_root.exists():
        shutil.rmtree(registry_root)
    registry = InstalledDomainRegistry.initialize(
        registry_root,
        capability_registry=capabilities,
        provider_registry=providers,
        created_at=STAMP,
    )
    for root in roots.values():
        _approve_install(root, registry, providers, capabilities)


def _make_platform_pack(
    domain,
    version,
    concepts,
    capability_ids,
    root,
    *,
    edges=(),
    equation=False,
    families=None,
):
    source_hash = bytes_hash(Path(__file__).read_bytes())
    records = [
        _record(
            domain,
            f"{domain}.concept.{item.casefold()}",
            KnowledgeKind.CONCEPT,
            ConceptContent(item, item, f"Reviewed {item}.", f"Reviewed {item}."),
        )
        for item in concepts
    ]
    if equation:
        scalar = ValueTypeRef(ValueTypeKind.DECIMAL)
        variables = (VariableBinding("x", scalar, "input"),)
        expression = Expression(
            ExpressionKind.EQUAL,
            children=(
                Expression(ExpressionKind.VARIABLE, "x", result_type=scalar),
                Expression(
                    ExpressionKind.CONSTANT,
                    1,
                    result_type=ValueTypeRef(ValueTypeKind.INTEGER),
                ),
            ),
            result_type=ValueTypeRef(ValueTypeKind.BOOLEAN),
        )
        records.append(
            _record(
                domain,
                f"{domain}.rule.identity",
                KnowledgeKind.EQUATION_RULE,
                RuleContent(
                    expression, variables, Applicability(("reviewed fixture scope",))
                ),
                capabilities=capability_ids,
            )
        )
    nodes = []
    by_name = {}
    for item, record in zip(concepts, records, strict=False):
        node = ConceptNode(item, record.knowledge_id, item, item, "")
        node = replace(node, node_hash=hash_without(node, "node_hash"))
        nodes.append(node)
        by_name[item] = node
    graph_edges = []
    for child, parent in edges:
        edge = ConceptEdge(child, parent, ConceptEdgeKind.PREREQUISITE, None, "")
        graph_edges.append(replace(edge, edge_hash=hash_without(edge, "edge_hash")))
    graph = ConceptGraph(
        tuple(nodes), tuple(graph_edges), CONCEPT_GRAPH_SCHEMA_VERSION, ""
    )
    graph = replace(graph, graph_hash=hash_without(graph, "graph_hash"))
    family_specs = families or (
        ("GENERIC_APPLICATION", concepts, ("FOUNDATIONAL", "TRANSFER")),
    )
    family_bindings = []
    for family_id, family_concepts, difficulty_structure in family_specs:
        family = ExerciseFamilyBinding(
            family_id,
            family_concepts,
            capability_ids,
            ZERO_SCHEMA,
            ZERO_SCHEMA,
            difficulty_structure,
            "generic.catalog.provider.v1",
            capability_ids[0],
            capability_ids[0],
            "SOURCE_SEGMENT_EXACT",
            "",
        )
        family = replace(family, family_hash=hash_without(family, "family_hash"))
        family_bindings.append(family)
        records.append(
            _record(
                domain,
                f"{domain}.exercise.{family_id.casefold()}",
                KnowledgeKind.EXERCISE_FAMILY,
                ExerciseFamilyContent(
                    family.family_id,
                    family_concepts,
                    ZERO_SCHEMA,
                    ZERO_SCHEMA,
                    family.difficulty_structure,
                ),
                capabilities=capability_ids,
            )
        )
    segment_hash = content_hash({"domain": domain, "source": source_hash})
    source = SourceBinding(
        f"{domain}.reviewed-source.v2",
        (),
        (),
        (source_hash,),
        (source_hash,),
        (),
        content_hash((source_hash, segment_hash)),
        (source_hash,),
        (segment_hash,),
        (("content", source_hash),),
        "",
    )
    source = replace(source, binding_hash=hash_without(source, "binding_hash"))
    evaluation = {
        "schema_version": 2,
        "test_cases": ["pack.load", "source.dereference", "heldout.bounded"],
        "minimum_pass_rate": "1.0",
        "runtime_network": False,
        "expected_record_count": len(records),
        "source_span_exactness": "1.0",
    }
    requirements = tuple(
        CapabilityRequirement(item, "^1.0.0", "USER_RUNTIME") for item in capability_ids
    )
    manifest = DomainPackManifest(
        domain,
        version,
        DOMAIN_PACK_SCHEMA_VERSION,
        domain,
        domain,
        ("ru", "en"),
        (domain,),
        tuple(item.content_hash for item in records),
        graph.graph_hash,
        tuple(item.family_hash for item in family_bindings),
        (source.binding_hash,),
        requirements,
        (),
        content_hash(evaluation),
        (),
        "",
        STAMP,
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
    root.mkdir(parents=True)
    _write_json(root / "manifest.json", asdict(manifest))
    _write_text(
        root / "knowledge.jsonl",
        "".join(canonical_json(asdict(item)) + "\n" for item in records),
    )
    _write_json(root / "concept_graph.json", asdict(graph))
    _write_json(
        root / "exercise_families.json",
        [asdict(item) for item in family_bindings],
    )
    _write_json(
        root / "capability_requirements.json", [asdict(item) for item in requirements]
    )
    _write_json(root / "adapter_bindings.json", [])
    _write_json(root / "evaluation_manifest.json", evaluation)
    _write_json(root / "source_bindings.json", [asdict(source)])
    _write_json(
        root / "pack_manifest.json",
        {
            "domain_id": domain,
            "pack_content_hash": manifest.pack_content_hash,
            "pack_version": version,
            "schema_version": DOMAIN_PACK_SCHEMA_VERSION,
        },
    )


def _record(
    domain,
    knowledge_id,
    kind,
    content,
    *,
    epistemic=EpistemicCharacter.DETERMINISTIC,
    capabilities=(),
):
    value = KnowledgeRecord(
        knowledge_id,
        domain,
        kind,
        UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
        epistemic,
        (f"{domain}.reviewed-source.v2",),
        (),
        (),
        capabilities,
        STAMP,
        content,
        "",
    )
    return replace(value, content_hash=record_content_hash(value))


def _build_acquisition(sources, goldens):
    artifact_root = ROOT / "artifacts/stage3/acquisition/m32"
    pack_root = ROOT / "artifacts/domains/m32"
    if artifact_root.exists():
        shutil.rmtree(artifact_root)
    if pack_root.exists():
        shutil.rmtree(pack_root)
    artifact_root.mkdir(parents=True)
    pack_root.mkdir(parents=True)
    result = {}
    with tempfile.TemporaryDirectory(prefix="m32-acquisition-") as directory:
        store = AcquisitionStore.open_or_initialize(Path(directory) / "store")
        for name, path in sources.items():
            bundle = ingest_bundle(
                (path,),
                bundle_id=f"m32-{name}",
                domain_tags=(name,),
                imported_at=STAMP,
                store=store,
            )
            segments = segment_bundle(bundle, store)
            proposals = propose_knowledge(bundle, segments)
            proposals = verify_proposals(bundle, segments, proposals, store)
            conflicts = detect_conflicts(proposals)
            clarifications = generate_clarifications(proposals)
            approved, reviews, approvals = [], [], []
            for proposal in proposals:
                if proposal.status is ProposalStatus.VERIFIED:
                    updated, review, approval = review_proposal(
                        proposal,
                        reviewer_identity="m32-reviewed-fixture-authority",
                        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
                        decision=ReviewDecision.APPROVE,
                        rationale="Independent reviewed fixture mapping",
                        timestamp=STAMP,
                    )
                    approved.append(updated)
                    reviews.append(review)
                    approvals.append(approval)
                else:
                    approved.append(proposal)
            output = pack_root / f"{name}-provisional-v2"
            pack = compile_provisional_pack(
                bundle,
                segments,
                tuple(approved),
                tuple(item for item in approvals if item is not None),
                output,
                domain_id=f"acquired-{name}",
            )
            destination = artifact_root / name
            destination.mkdir()
            _write_json(destination / "bundle.json", asdict(bundle))
            _write_text(
                destination / "segments.jsonl",
                "".join(canonical_json(asdict(item)) + "\n" for item in segments),
            )
            _write_text(
                destination / "proposals.jsonl",
                "".join(canonical_json(asdict(item)) + "\n" for item in approved),
            )
            _write_json(
                destination / "reviews.json", [asdict(item) for item in reviews]
            )
            _write_json(
                destination / "proposal_approvals.json",
                [asdict(item) for item in approvals if item],
            )
            _write_json(
                destination / "conflicts.json",
                [asdict(item) for item in conflicts],
            )
            _write_json(
                destination / "clarifications.json",
                [asdict(item) for item in clarifications],
            )
            _write_json(destination / "golden.json", goldens[name])
            result[name] = (pack, len(segments), len(proposals), len(approvals))
    _write_json(
        artifact_root / "build_summary.json",
        {
            name: {
                "pack_hash": values[0].manifest.pack_content_hash,
                "segments": values[1],
                "proposals": values[2],
                "approved": values[3],
                "conflicts": len(
                    json.loads(
                        (artifact_root / name / "conflicts.json").read_text(
                            encoding="utf-8"
                        )
                    )
                ),
                "clarifications": len(
                    json.loads(
                        (artifact_root / name / "clarifications.json").read_text(
                            encoding="utf-8"
                        )
                    )
                ),
            }
            for name, values in result.items()
        },
    )
    return result


def _install_acquired_packs(providers, capabilities, acquired):
    registry = InstalledDomainRegistry.open(
        ROOT / "artifacts/stage3/installed-domains-v2",
        capability_registry=capabilities,
        provider_registry=providers,
    )
    for pack, _, _, _ in acquired.values():
        _approve_install(Path(pack.root), registry, providers, capabilities)


def _approve_install(root, registry, providers, capabilities):
    pack = load_pack(root)
    resolutions = []
    for requirement in pack.manifest.required_capabilities:
        resolution = resolve_capability(
            capabilities,
            requirement,
            requesting_domain_id=pack.manifest.domain_id,
            requesting_pack_hash=pack.manifest.pack_content_hash,
            provider_registry=providers,
            resolved_at=STAMP,
        )
        if resolution.receipt is None:
            raise RuntimeError(
                f"unresolved fixture capability: {requirement.capability_id}"
            )
        for receipt in resolution.closure_receipts:
            if receipt.receipt_hash not in {item.receipt_hash for item in resolutions}:
                resolutions.append(receipt)
    validation = validate_pack(pack)
    approval = approve_pack(
        pack_hash=pack.manifest.pack_content_hash,
        knowledge_ir_schema=UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
        concept_graph_hash=pack.manifest.concept_graph_hash,
        source_binding_hashes=pack.manifest.source_binding_hashes,
        capability_resolution_receipt_hashes=tuple(
            item.receipt_hash for item in resolutions
        ),
        validation_report_hash=content_hash(validation),
        evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
        reviewer_identity="m32-trusted-release-process",
        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
        decision=PackApprovalDecision.APPROVE,
        policy_version="m32.1",
        timestamp=STAMP,
    )
    _write_json(
        root / "approval.json",
        {
            "approval": asdict(approval),
            "resolutions": [asdict(item) for item in resolutions],
        },
    )
    pack = load_pack(root)
    registry.install(
        pack,
        approval,
        tuple(resolutions),
        capability_registry=capabilities,
        provider_registry=providers,
        installed_at=STAMP,
    )


def _write_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def _write_json(path, value):
    _write_text(path, canonical_json(value) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
