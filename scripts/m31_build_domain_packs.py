"""Deterministically compile the reviewed M-31 data-only packs (offline only)."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityRequirement,
    CapabilityStatus,
    ProviderType,
)
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.capabilities.resolution import resolve_capability
from ai_brain.stage3.capabilities.validation import descriptor_hash
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.manifest import (
    AdapterBinding,
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
from ai_brain.stage3.domains.validation import hash_without
from ai_brain.stage3.knowledge_ir.records import (
    Applicability,
    EpistemicCharacter,
    ExerciseFamilyContent,
    Expression,
    ExpressionKind,
    KnowledgeKind,
    KnowledgeRecord,
    RuleContent,
    TextContent,
    VariableBinding,
)

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-08-29T00:00:00Z"
ZERO_SCHEMA = content_hash({"type": "object", "additionalProperties": False})
RESOURCE = content_hash({"cpu_only": True, "network": False, "memory_write": False})


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _source_hash(path: str) -> str:
    return bytes_hash((ROOT / path).read_bytes())


def capability_registry() -> CapabilityRegistry:
    manifest = json.loads(
        (ROOT / "artifacts/domains/chemistry/m29/domain_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    tools = dict(manifest["tool_manifest_hashes"])
    specs = (
        (
            "chemistry.element_fact_retrieval.v1",
            CapabilityKind.FACT_RETRIEVAL,
            ProviderType.ADAPTER,
            "chemistry.education.graph_adapter",
            _source_hash(
                "src/ai_brain/stage2/domains/chemistry/education/graph_adapter.py"
            ),
            AuthorityClass.READ_ONLY_EXACT,
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
        ),
        (
            "chemistry.formula_parsing.v1",
            CapabilityKind.FORMULA_PARSING,
            ProviderType.PARSER,
            "chemistry.formula_parser",
            _source_hash("src/ai_brain/stage2/domains/chemistry/formula_parser.py"),
            AuthorityClass.READ_ONLY_EXACT,
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
        ),
        (
            "chemistry.formula_composition.v1",
            CapabilityKind.QUANTITY_ARITHMETIC,
            ProviderType.TOOL,
            "chemistry_formula_composition",
            tools["chemistry_formula_composition"],
            AuthorityClass.CONFIRMATION_REQUIRED,
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
        ),
        (
            "chemistry.molar_mass.v2",
            CapabilityKind.QUANTITY_ARITHMETIC,
            ProviderType.TOOL,
            "chemistry_molar_mass",
            tools["chemistry_molar_mass"],
            AuthorityClass.CONFIRMATION_REQUIRED,
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
        ),
        (
            "chemistry.mass_amount_conversion.v2",
            CapabilityKind.UNIT_CONVERSION,
            ProviderType.TOOL,
            "chemistry_mass_amount",
            tools["chemistry_mass_amount"],
            AuthorityClass.CONFIRMATION_REQUIRED,
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
        ),
        (
            "chemistry.entity_amount_conversion.v2",
            CapabilityKind.QUANTITY_ARITHMETIC,
            ProviderType.TOOL,
            "chemistry_entity_amount",
            tools["chemistry_entity_amount"],
            AuthorityClass.CONFIRMATION_REQUIRED,
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
        ),
        (
            "chemistry.educational_graph_compilation.v1",
            CapabilityKind.PROCEDURE_EXECUTION,
            ProviderType.CATALOG_COMPILER,
            "education.catalog_compiler",
            _source_hash("src/ai_brain/stage2/education/catalog_compiler.py"),
            AuthorityClass.OFFLINE_COMPILATION_ONLY,
            ("OFFLINE_COMPILATION",),
        ),
        (
            "chemistry.controlled_language.v1",
            CapabilityKind.CODE_PARSING,
            ProviderType.PARSER,
            "chemistry.education.controlled",
            _source_hash(
                "src/ai_brain/stage2/domains/chemistry/education/controlled.py"
            ),
            AuthorityClass.ASSISTIVE_ONLY,
            ("USER_RUNTIME",),
        ),
        (
            "generic.taxonomy_reasoning.v1",
            CapabilityKind.TAXONOMY_REASONING,
            ProviderType.VERIFIER,
            "stage3.concept_graph",
            _source_hash("src/ai_brain/stage3/domains/validation.py"),
            AuthorityClass.READ_ONLY_EXACT,
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
        ),
        (
            "generic.equation_validation.v1",
            CapabilityKind.EQUATION_EVALUATION,
            ProviderType.VERIFIER,
            "stage3.expression_validator",
            _source_hash("src/ai_brain/stage3/knowledge_ir/validation.py"),
            AuthorityClass.READ_ONLY_EXACT,
            ("USER_RUNTIME", "OFFLINE_COMPILATION"),
        ),
    )
    result = []
    for (
        capability_id,
        kind,
        provider_type,
        provider_id,
        provider_hash,
        authority,
        contexts,
    ) in specs:
        value = CapabilityDescriptor(
            capability_id,
            "1.0.0",
            kind,
            capability_id.replace(".", " "),
            capability_id.replace(".", " "),
            ZERO_SCHEMA,
            ZERO_SCHEMA,
            True,
            authority,
            provider_type,
            provider_id,
            provider_hash,
            (),
            contexts,
            RESOURCE,
            CapabilityStatus.ACTIVE,
            "",
        )
        result.append(replace(value, descriptor_hash=descriptor_hash(value)))
    registry = CapabilityRegistry.build(tuple(result))
    _write(ROOT / "artifacts/stage3/capabilities/registry_v1.json", asdict(registry))
    return registry


def _record(
    domain: str,
    knowledge_id: str,
    kind: KnowledgeKind,
    content,
    *,
    epistemic=EpistemicCharacter.DETERMINISTIC,
    capabilities: tuple[str, ...] = (),
) -> KnowledgeRecord:
    value = KnowledgeRecord(
        knowledge_id,
        domain,
        kind,
        1,
        epistemic,
        (f"{domain}.reviewed-source.v1",),
        (),
        (),
        capabilities,
        STAMP,
        content,
        "",
    )
    body = asdict(value)
    body.pop("content_hash")
    return replace(value, content_hash=content_hash(body))


def _concept(domain: str, concept_id: str) -> KnowledgeRecord:
    return _record(
        domain,
        f"{domain}.concept.{concept_id.lower()}",
        KnowledgeKind.CONCEPT,
        TextContent(
            concept_id.replace("_", " "),
            concept_id.replace("_", " "),
            f"Проверенное понятие {concept_id}.",
            f"Reviewed concept {concept_id}.",
        ),
    )


def _build_pack(
    domain: str,
    version: str,
    names: tuple[str, str],
    concepts: tuple[str, ...],
    prerequisites: dict[str, tuple[str, ...]],
    families: dict[str, tuple[str, ...]],
    capabilities: tuple[str, ...],
    root: Path,
    *,
    equation: bool = False,
    source_binding: SourceBinding | None = None,
) -> None:
    records = [_concept(domain, item) for item in concepts]
    if equation:
        variables = (VariableBinding("x", "DECIMAL", "fixture.dimension", "input"),)
        expression = Expression(
            ExpressionKind.EQUAL,
            children=(
                Expression(ExpressionKind.VARIABLE, "x"),
                Expression(ExpressionKind.CONSTANT, 1),
            ),
        )
        records.append(
            _record(
                domain,
                f"{domain}.rule.identity",
                KnowledgeKind.EQUATION_RULE,
                RuleContent(expression, variables, Applicability(("fixture_scope",))),
                capabilities=(capabilities[0],),
            )
        )
    nodes = []
    for concept, record in zip(concepts, records, strict=False):
        node = ConceptNode(concept, record.knowledge_id, concept, concept, "")
        nodes.append(replace(node, node_hash=hash_without(node, "node_hash")))
    edges = []
    for concept, deps in prerequisites.items():
        for dependency in deps:
            edge = ConceptEdge(
                concept, dependency, ConceptEdgeKind.PREREQUISITE, None, ""
            )
            edges.append(replace(edge, edge_hash=hash_without(edge, "edge_hash")))
    graph = ConceptGraph(tuple(nodes), tuple(edges), 1, "")
    graph = replace(graph, graph_hash=hash_without(graph, "graph_hash"))
    family_rows = []
    for family, bound in families.items():
        row = ExerciseFamilyBinding(
            family,
            bound,
            capabilities,
            ZERO_SCHEMA,
            ZERO_SCHEMA,
            ("FOUNDATIONAL", "PRACTICE", "TRANSFER"),
            "generic.catalog.compiler.v1",
            capabilities[0],
            capabilities[0],
            "AUTHORITY_REFERENCES_ONLY",
            "",
        )
        family_rows.append(replace(row, family_hash=hash_without(row, "family_hash")))
        records.append(
            _record(
                domain,
                f"{domain}.exercise_family.{family.lower()}",
                KnowledgeKind.EXERCISE_FAMILY,
                ExerciseFamilyContent(
                    family,
                    bound,
                    ZERO_SCHEMA,
                    ZERO_SCHEMA,
                    ("FOUNDATIONAL", "PRACTICE", "TRANSFER"),
                ),
                capabilities=capabilities,
            )
        )
    sources = (
        (source_binding,)
        if source_binding
        else (
            SourceBinding(
                f"{domain}.reviewed-source.v1",
                (),
                (),
                (),
                (),
                (),
                content_hash({"domain": domain}),
                "",
            ),
        )
    )
    sources = tuple(
        replace(x, binding_hash=hash_without(x, "binding_hash")) for x in sources
    )
    adapters: tuple[AdapterBinding, ...] = ()
    if domain == "chemistry":
        raw_adapters = (
            AdapterBinding(
                "chemistry.education.graph_adapter",
                _source_hash(
                    "src/ai_brain/stage2/domains/chemistry/education/graph_adapter.py"
                ),
                ("chemistry.element_fact_retrieval.v1",),
                ("USER_RUNTIME", "OFFLINE_COMPILATION"),
                (version,),
                "",
            ),
            AdapterBinding(
                "chemistry.formula_parser",
                _source_hash("src/ai_brain/stage2/domains/chemistry/formula_parser.py"),
                ("chemistry.formula_parsing.v1",),
                ("USER_RUNTIME", "OFFLINE_COMPILATION"),
                (version,),
                "",
            ),
        )
        adapters = tuple(
            replace(x, binding_hash=hash_without(x, "binding_hash"))
            for x in raw_adapters
        )
    evaluation = {
        "schema_version": 1,
        "test_cases": [f"{domain}.load", f"{domain}.recommend"],
        "minimum_pass_rate": "1.0",
        "runtime_network": False,
    }
    requirements = tuple(
        CapabilityRequirement(x, "^1.0.0", "USER_RUNTIME") for x in capabilities
    )
    manifest = DomainPackManifest(
        domain,
        version,
        1,
        names[0],
        names[1],
        ("ru", "en"),
        (domain,),
        tuple(x.content_hash for x in records),
        graph.graph_hash,
        tuple(x.family_hash for x in family_rows),
        tuple(x.binding_hash for x in sources),
        requirements,
        tuple(x.binding_hash for x in adapters),
        content_hash(evaluation),
        (),
        "",
        STAMP,
    )
    body = asdict(manifest)
    body.pop("pack_content_hash")
    manifest = replace(manifest, pack_content_hash=content_hash(body))
    _write(root / "manifest.json", asdict(manifest))
    root.mkdir(parents=True, exist_ok=True)
    (root / "knowledge.jsonl").write_text(
        "".join(canonical_json(asdict(x)) + "\n" for x in records),
        encoding="utf-8",
        newline="\n",
    )
    _write(root / "concept_graph.json", asdict(graph))
    _write(root / "exercise_families.json", [asdict(x) for x in family_rows])
    _write(root / "capability_requirements.json", [asdict(x) for x in requirements])
    _write(root / "adapter_bindings.json", [asdict(x) for x in adapters])
    _write(root / "evaluation_manifest.json", evaluation)
    _write(root / "source_bindings.json", [asdict(x) for x in sources])
    _write(
        root / "pack_manifest.json",
        {
            "domain_id": domain,
            "pack_content_hash": manifest.pack_content_hash,
            "pack_version": version,
            "schema_version": 1,
        },
    )


def main() -> int:
    registry = capability_registry()
    chemistry_manifest = json.loads(
        (ROOT / "artifacts/domains/chemistry/m29/domain_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    concepts = (
        "ELEMENT_IDENTITY",
        "ATOMIC_NUMBER",
        "CHEMICAL_SYMBOL",
        "ATOMIC_WEIGHT_SINGLE",
        "ATOMIC_WEIGHT_INTERVAL",
        "FORMULA_PARSING",
        "SUBSCRIPT_COUNTING",
        "GROUP_MULTIPLIER",
        "FORMULA_COMPOSITION",
        "MOLAR_MASS_SIMPLE",
        "MOLAR_MASS_GROUPED",
        "MASS_TO_MOLES",
        "MOLES_TO_MASS",
        "GRAM_KILOGRAM_CONVERSION",
        "MOL_MMOL_CONVERSION",
        "MOLES_TO_FORMULA_ENTITIES",
        "MOLES_TO_TOTAL_ATOMS",
        "TARGET_ELEMENT_ATOM_COUNT",
        "SIGNIFICANT_FIGURES",
        "UNIT_DIMENSION",
    )
    prerequisites = {
        "FORMULA_COMPOSITION": ("FORMULA_PARSING", "SUBSCRIPT_COUNTING"),
        "MOLAR_MASS_SIMPLE": ("FORMULA_COMPOSITION", "ATOMIC_WEIGHT_SINGLE"),
        "MOLAR_MASS_GROUPED": ("MOLAR_MASS_SIMPLE", "GROUP_MULTIPLIER"),
        "MASS_TO_MOLES": ("MOLAR_MASS_SIMPLE", "UNIT_DIMENSION"),
        "MOLES_TO_MASS": ("MOLAR_MASS_SIMPLE", "UNIT_DIMENSION"),
        "MOLES_TO_FORMULA_ENTITIES": ("MASS_TO_MOLES",),
    }
    families = {
        "FACT_RETRIEVAL": ("ELEMENT_IDENTITY",),
        "FORMULA_COMPOSITION": (
            "FORMULA_PARSING",
            "SUBSCRIPT_COUNTING",
            "FORMULA_COMPOSITION",
        ),
        "MOLAR_MASS_SIMPLE": (
            "ATOMIC_WEIGHT_SINGLE",
            "FORMULA_PARSING",
            "MOLAR_MASS_SIMPLE",
        ),
        "MOLAR_MASS_GROUPED": ("GROUP_MULTIPLIER", "MOLAR_MASS_GROUPED"),
        "MASS_AMOUNT": ("MASS_TO_MOLES", "MOLES_TO_MASS", "UNIT_DIMENSION"),
        "AMOUNT_ENTITIES": ("MOLES_TO_FORMULA_ENTITIES", "UNIT_DIMENSION"),
    }
    chemistry_caps = (
        "chemistry.element_fact_retrieval.v1",
        "chemistry.formula_parsing.v1",
        "chemistry.formula_composition.v1",
        "chemistry.molar_mass.v2",
        "chemistry.mass_amount_conversion.v2",
        "chemistry.entity_amount_conversion.v2",
    )
    source = SourceBinding(
        "chemistry.reviewed-source.v1",
        (chemistry_manifest["fact_memory_snapshot_hash"],),
        (),
        tuple(chemistry_manifest["field_extraction_evidence_hashes"]),
        tuple(chemistry_manifest["official_source_snapshot_hashes"]),
        tuple(chemistry_manifest["source_derivation_hashes"]),
        chemistry_manifest["source_chain_hash"],
        "",
    )
    _build_pack(
        "chemistry",
        "generic-v1",
        ("Химия", "Chemistry"),
        concepts,
        prerequisites,
        families,
        chemistry_caps,
        ROOT / "artifacts/domains/chemistry/generic-v1",
        source_binding=source,
    )
    _build_pack(
        "fixture-taxonomy",
        "1.0.0",
        ("Таксономия", "Taxonomy fixture"),
        ("LIVING_THING", "PLANT", "TREE"),
        {"TREE": ("PLANT",), "PLANT": ("LIVING_THING",)},
        {"CLASSIFY": ("LIVING_THING", "PLANT", "TREE")},
        ("generic.taxonomy_reasoning.v1",),
        ROOT / "tests/fixtures/domains/taxonomy-v1",
    )
    _build_pack(
        "fixture-quantity-equation",
        "1.0.0",
        ("Величины и уравнения", "Quantity/equation fixture"),
        ("QUANTITY", "UNIT", "EQUATION"),
        {"EQUATION": ("QUANTITY", "UNIT")},
        {"EVALUATE": ("QUANTITY", "UNIT", "EQUATION")},
        ("generic.equation_validation.v1",),
        ROOT / "tests/fixtures/domains/quantity-equation-v1",
        equation=True,
    )
    pack = load_pack(ROOT / "artifacts/domains/chemistry/generic-v1")
    provider_hashes = {
        item.provider_id: item.provider_implementation_hash
        for item in registry.descriptors
    }
    receipts = tuple(
        resolve_capability(
            registry,
            requirement,
            requesting_domain_id=pack.manifest.domain_id,
            requesting_pack_hash=pack.manifest.pack_content_hash,
            provider_hashes=provider_hashes,
            resolved_at=STAMP,
        ).receipt
        for requirement in pack.manifest.required_capabilities
    )
    if any(item is None for item in receipts):
        raise RuntimeError("chemistry pack has an unresolved capability")
    validation = {"status": "VERIFIED", "pack_hash": pack.manifest.pack_content_hash}
    approval = approve_pack(
        pack_hash=pack.manifest.pack_content_hash,
        knowledge_ir_schema=1,
        concept_graph_hash=pack.manifest.concept_graph_hash,
        source_binding_hashes=pack.manifest.source_binding_hashes,
        capability_resolution_receipt_hashes=tuple(x.receipt_hash for x in receipts),
        validation_report_hash=content_hash(validation),
        evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
        reviewer_identity="m31-trusted-release-process",
        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
        decision=PackApprovalDecision.APPROVE,
        policy_version="m31.1",
        timestamp=STAMP,
    )
    _write(
        ROOT / "artifacts/domains/chemistry/generic-v1/approval.json",
        {"approval": asdict(approval), "resolutions": [asdict(x) for x in receipts]},
    )
    target = ROOT / "artifacts/stage3/installed-domains"
    temporary = ROOT / "artifacts/stage3/.installed-domains-build"
    if temporary.exists():
        shutil.rmtree(temporary)
    installed = InstalledDomainRegistry.initialize(temporary, created_at=STAMP)
    installed.install(pack, approval, receipts, installed_at=STAMP)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        temporary / "installed_domains.sqlite3", target / "installed_domains.sqlite3"
    )
    shutil.rmtree(temporary)
    print(canonical_json({"status": "BUILT", "packs": 3}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
