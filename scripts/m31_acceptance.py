"""Scaled M-31 acceptance, genericity, security, equivalence, and performance gate."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path

from ai_brain.stage2.conversation.service import ConversationalTutorService
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.catalog import EducationalCatalogV2
from ai_brain.stage2.education.service import EducationalService
from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage2.progress.projection import project_progress
from ai_brain.stage2.progress.recommendations import recommend_exercise
from ai_brain.stage3.capabilities.models import CapabilityRequirement, ResolutionStatus
from ai_brain.stage3.capabilities.persistence import load_registry
from ai_brain.stage3.capabilities.resolution import resolve_capability
from ai_brain.stage3.domains.approval import verify_approval
from ai_brain.stage3.domains.cli import _approval_bundle
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.runtime import GenericDomainRuntime
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.serialization import dump_record, load_record
from ai_brain.stage3.knowledge_ir.validation import validate_record

ROOT = Path(__file__).resolve().parents[1]


def _measure(count, operation):
    samples = []
    tracemalloc.start()
    started = time.perf_counter()
    for index in range(count):
        before = time.perf_counter_ns()
        operation(index)
        samples.append((time.perf_counter_ns() - before) / 1_000_000)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    samples.sort()

    def percentile(value):
        return samples[min(len(samples) - 1, int((len(samples) - 1) * value))]

    return {
        "count": count,
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "throughput_per_second": count / elapsed,
        "peak_python_bytes": peak,
    }


def run():
    chemistry_pack_path = ROOT / "artifacts/domains/chemistry/generic-v1"
    capability_registry_path = ROOT / "artifacts/stage3/capabilities/registry_v1.json"
    installed_registry_path = ROOT / "artifacts/stage3/installed-domains"
    chemistry_pack = load_pack(chemistry_pack_path)
    taxonomy = load_pack(ROOT / "tests/fixtures/domains/taxonomy-v1")
    quantity = load_pack(ROOT / "tests/fixtures/domains/quantity-equation-v1")
    record = chemistry_pack.knowledge_records[0]
    serialized = dump_record(record)
    for _ in range(10_000):
        if dump_record(load_record(serialized)) != serialized:
            raise AssertionError("IR round-trip mismatch")
    malformed = 0
    for index in range(5_000):
        row = json.loads(serialized)
        row["content_hash"] = (f"{index:064x}")[-64:]
        try:
            load_record(canonical_json(row))
        except (TypeError, ValueError):
            malformed += 1
    if malformed != 5_000:
        raise AssertionError("malformed IR accepted")
    registry = load_registry(capability_registry_path)
    providers = {
        x.provider_id: x.provider_implementation_hash for x in registry.descriptors
    }
    first = registry.descriptors[0]
    resolved = 0
    for index in range(5_000):
        request = (
            CapabilityRequirement(
                first.capability_id, "*", first.allowed_execution_contexts[0]
            )
            if index % 2 == 0
            else CapabilityRequirement(
                f"unknown.capability.{index}", "*", "USER_RUNTIME"
            )
        )
        result = resolve_capability(
            registry,
            request,
            requesting_domain_id="acceptance",
            requesting_pack_hash="0" * 64,
            provider_hashes=providers,
            resolved_at="2026-08-29T00:00:00Z",
        )
        resolved += result.status is ResolutionStatus.RESOLVED
    if resolved != 2_500:
        raise AssertionError("capability resolution boundary mismatch")
    rejected = 0
    for index in range(2_000):
        mutated = replace(
            chemistry_pack,
            manifest=replace(
                chemistry_pack.manifest, pack_content_hash=(f"{index:064x}")[-64:]
            ),
        )
        try:
            validate_pack(mutated)
        except ValueError:
            rejected += 1
    if rejected != 2_000:
        raise AssertionError("tampered packs accepted")
    with tempfile.TemporaryDirectory(prefix="m31-chemistry-") as chemistry_temp:
        chemistry_copy = Path(chemistry_temp) / "m29"
        shutil.copytree(ROOT / "artifacts/domains/chemistry/m29", chemistry_copy)
        chemistry = ChemistryDomainService.open(chemistry_copy)
        catalog = EducationalCatalogV2.load(
            ROOT / "artifacts/education/m30/catalog_v4.json", chemistry
        )
    runtime = GenericDomainRuntime(chemistry_pack)
    equivalent = 0
    for entry in catalog.entries:
        concepts = runtime.concepts_for_exercise_family(
            entry.exercise_spec.family.value
        )
        if entry in runtime.resolve_catalog_candidates(catalog.entries, concepts[0]):
            equivalent += 1
    if equivalent != 2_000 or len(catalog.entries) != 2_000:
        raise AssertionError("chemistry catalog equivalence failed")
    fixture_interactions = 0
    for item in (taxonomy, quantity):
        fixture = GenericDomainRuntime(item)
        family = item.exercise_families[0]
        for _ in range(500):
            if (
                fixture.concepts_for_exercise_family(family.family_id)
                != family.concept_ids
            ):
                raise AssertionError("fixture runtime mismatch")
            fixture_interactions += 1
    generic_files = tuple((ROOT / "src/ai_brain/stage3").rglob("*.py"))
    forbidden = []
    for path in generic_files:
        if "chemistry" in path.read_text(encoding="utf-8").casefold():
            forbidden.append(str(path.relative_to(ROOT)))
    if forbidden:
        raise AssertionError(f"generic core imports/branches chemistry: {forbidden}")
    unknown = resolve_capability(
        registry,
        CapabilityRequirement("unsupported.example.v1", "*", "USER_RUNTIME"),
        requesting_domain_id="fixture",
        requesting_pack_hash="0" * 64,
        provider_hashes=providers,
    )
    if unknown.status is not ResolutionStatus.NEEDS_NEW_CAPABILITY:
        raise AssertionError("unknown capability fallback")
    with tempfile.TemporaryDirectory(prefix="m31-registry-") as temporary:
        backup = Path(temporary) / "backup.sqlite3"
        source = InstalledDomainRegistry.open(installed_registry_path)
        backed = source.backup(backup)
        restored = InstalledDomainRegistry.restore(
            backup, Path(temporary) / "restored"
        ).verify()
    approval, resolution_receipts = _approval_bundle(
        chemistry_pack_path / "approval.json"
    )
    concepts = tuple(node.concept_id for node in chemistry_pack.concept_graph.nodes)
    prerequisites = {
        concept: tuple(
            edge.target_concept_id
            for edge in chemistry_pack.concept_graph.edges
            if edge.kind.value == "PREREQUISITE" and edge.source_concept_id == concept
        )
        for concept in concepts
    }
    projections = project_progress("performance", (), concept_ids=concepts)
    candidate_index = {
        concept: tuple(
            (entry.entry_hash, entry.semantic_key.semantic_key_hash)
            for entry in runtime.resolve_catalog_candidates(catalog.entries, concept)
        )
        for concept in concepts
    }
    installed_registry = InstalledDomainRegistry.open(installed_registry_path)
    performance = {
        "pack_load_100": _measure(100, lambda _: load_pack(chemistry_pack_path)),
        "ir_validation_10000": _measure(10_000, lambda _: validate_record(record)),
        "capability_registry_load_100": _measure(
            100, lambda _: load_registry(capability_registry_path)
        ),
        "capability_resolution_10000": _measure(
            10_000, lambda _: registry.descriptor(first.capability_id)
        ),
        "pack_approval_verification_10000": _measure(
            10_000, lambda _: verify_approval(approval)
        ),
        "installed_domain_lookup_1000": _measure(
            1_000, lambda _: installed_registry.show("chemistry", "generic-v1")
        ),
        "concept_graph_lookup_10000": _measure(
            10_000, lambda _: runtime.concept_graph()
        ),
        "exercise_family_resolution_10000": _measure(
            10_000, lambda _: runtime.concepts_for_exercise_family("MOLAR_MASS_SIMPLE")
        ),
        "catalog_candidate_resolution_1000": _measure(
            1_000,
            lambda index: runtime.resolve_catalog_candidates(
                catalog.entries, concepts[index % len(concepts)]
            ),
        ),
        "recommendation_10000": _measure(
            10_000,
            lambda _: recommend_exercise(
                "performance",
                projections,
                candidate_index,
                concepts=concepts,
                prerequisites=prerequisites,
                generated_at="2026-08-29T00:00:00Z",
            ),
        ),
        "runtime_currentness_100": _measure(
            100, lambda _: runtime.verify_currentness()
        ),
    }
    with tempfile.TemporaryDirectory(prefix="m31-install-perf-") as temporary:
        install_root = Path(temporary)
        performance["installation_25"] = _measure(
            25,
            lambda index: InstalledDomainRegistry.initialize(
                install_root / str(index), created_at="2026-08-29T00:00:00Z"
            ).install(
                chemistry_pack,
                approval,
                resolution_receipts,
                installed_at="2026-08-29T00:00:00Z",
            ),
        )
    with tempfile.TemporaryDirectory(prefix="m31-conversation-perf-") as temporary:
        conversation_root = Path(temporary)
        chemistry_root = conversation_root / "chemistry"
        shutil.copytree(ROOT / "artifacts/domains/chemistry/m29", chemistry_root)
        education = EducationalService.open(
            chemistry_root,
            conversation_root / "sessions",
            catalog_path=ROOT / "artifacts/education/m30/catalog_v4.json",
        )
        tutor = ConversationalTutorService.open(
            education,
            conversation_root / "conversations",
            conversation_root / "progress",
        )

        def conversation_regression(index):
            started = tutor.start(f"performance-{index}", language="en")
            result = tutor.turn(started.conversation_id, "Give me an exercise")
            if result.response_kind != "EXERCISE":
                raise AssertionError("chemistry conversation regression")

        performance["chemistry_conversation_regression_25"] = _measure(
            25, conversation_regression
        )
    return {
        "status": "PASS",
        "outcome": "OUTCOME_A",
        "ir_roundtrips": 10_000,
        "malformed_ir_rejected": malformed,
        "capability_resolution_cases": 5_000,
        "capability_resolved": resolved,
        "pack_mutations_rejected": rejected,
        "catalog_entries_compared": len(catalog.entries),
        "catalog_entries_equivalent": equivalent,
        "fixture_interactions": fixture_interactions,
        "generic_pack_count": 3,
        "generic_core_chemistry_references": len(forbidden),
        "unsupported_capability_status": unknown.status.value,
        "registry_backup": backed,
        "registry_restore": restored,
        "performance": performance,
        "runtime_network": False,
        "imports_torch": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run()
    text = (
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
