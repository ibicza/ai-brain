from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.java_component_manifest import (
    JAVA_COMPONENT_STAGE_ORDER,
    JavaProductionComponent,
    JavaProductionComponentManifest,
    compare_java_component_manifests,
)
from ai_brain.stage3.acquisition.java_disclosed_corpus import (
    assert_not_disclosed_java_archive,
    load_m335_disclosed_corpus_denylist,
)
from ai_brain.stage3.acquisition.java_freeze_roles import (
    FinalArtifactRole,
    build_final_artifact_role_manifest,
    verify_role_aware_disclosure,
)
from ai_brain.stage3.acquisition.java_pre_freeze_gate_v3 import (
    M335_PRE_FREEZE_V3_SPECS,
    M335PreFreezeDecision,
    evaluate_m335_pre_freeze_gate_v3,
    run_m335_gate_mutations,
)
from ai_brain.stage3.acquisition.java_production import (
    detect_java_production_identity_conflicts,
    run_java_acquisition_pipeline,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.java_state_audit import (
    EnforcedJavaProductionStateAudit,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.domains.aliases import (
    AliasLookupStatus,
    AuthoritativeIdentity,
    ExactReferenceAlias,
    build_alias_semantics,
    resolve_alias,
)
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.runtime import GenericDomainRuntime
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION
from ai_brain.stage3.providers.registry import ProviderRegistry

STAMP = "2026-09-03T00:00:00Z"


def _write_java(root: Path, relative: str, value: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")
    return path


def _production_context(tmp_path, source_text):
    root = tmp_path / "src"
    source = _write_java(root, "demo/Overloads.java", source_text)
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        (source,),
        bundle_id="m335-test",
        domain_tags=("java-api",),
        imported_at=STAMP,
        source_root=root,
        store=store,
    )
    batch = run_java_acquisition_pipeline(
        bundle, store, deterministic_run_id="m335.test.v1"
    )
    return bundle, store, batch


def _production(tmp_path, source_text):
    return _production_context(tmp_path, source_text)[2]


def test_canonical_ingestion_ignores_input_root_order_and_event_timestamp(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "another-absolute-root"
    first = (
        _write_java(first_root, "b/B.java", "package b; public class B {}\n"),
        _write_java(first_root, "a/A.java", "package a; public class A {}\n"),
    )
    second = (
        _write_java(second_root, "a/A.java", "package a; public class A {}\n"),
        _write_java(second_root, "b/B.java", "package b; public class B {}\n"),
    )
    one = ingest_bundle(
        first,
        bundle_id="stable",
        imported_at="2026-09-03T00:00:00Z",
        source_root=first_root,
    )
    two = ingest_bundle(
        second,
        bundle_id="stable",
        imported_at="2030-01-01T00:00:00Z",
        source_root=second_root,
    )
    assert [item.relative_path for item in one.documents] == ["a/A.java", "b/B.java"]
    assert one.bundle_hash == two.bundle_hash
    assert one.manifest.manifest_hash == two.manifest.manifest_hash
    assert tuple(item.document_id for item in one.documents) == tuple(
        item.document_id for item in two.documents
    )
    assert tuple(item.document_hash for item in one.documents) == tuple(
        item.document_hash for item in two.documents
    )
    assert one.created_at != two.created_at


def test_canonical_ingestion_rejects_casefold_and_nfc_path_collisions(tmp_path):
    case_root = tmp_path / "case"
    case_paths = (
        _write_java(case_root, "ss.java", "class First {}\n"),
        _write_java(case_root, "ß.java", "class Second {}\n"),
    )
    with pytest.raises(ValueError, match="casefold source path collision"):
        ingest_bundle(
            case_paths,
            bundle_id="casefold-collision",
            source_root=case_root,
        )
    nfc_root = tmp_path / "nfc"
    nfc_paths = (
        _write_java(nfc_root, "café.java", "class First {}\n"),
        _write_java(nfc_root, "café.java", "class Second {}\n"),
    )
    with pytest.raises(ValueError, match="Unicode-normalization source path collision"):
        ingest_bundle(nfc_paths, bundle_id="nfc-collision", source_root=nfc_root)


def test_explicit_legacy_java_rebuild_retains_v1_event_bound_identity(tmp_path):
    root = tmp_path / "legacy"
    source = _write_java(root, "Legacy.java", "public class Legacy {}\n")
    first = ingest_bundle(
        (source,),
        bundle_id="legacy",
        imported_at="2026-09-03T00:00:00Z",
        source_root=root,
        canonical_identity=False,
    )
    second = ingest_bundle(
        (source,),
        bundle_id="legacy",
        imported_at="2030-01-01T00:00:00Z",
        source_root=root,
        canonical_identity=False,
    )
    assert first.manifest.schema_version == 1
    assert first.documents[0].document_id == "legacy.document.001"
    assert first.bundle_hash != second.bundle_hash


def test_callable_identity_distinguishes_primitive_wrapper_and_nested_owner(tmp_path):
    batch = _production(
        tmp_path,
        """package demo;
public class Overloads {
  public Overloads(boolean value) {}
  public Overloads(Boolean value) {}
  public void setValue(boolean value) {}
  public void setValue(Boolean value) {}
  public void doubles(double value) {}
  public void doubles(Double value) {}
  public void floats(float value) {}
  public void floats(Float value) {}
  public void longs(long value) {}
  public void longs(Long value) {}
  public void integers(int value) {}
  public void integers(Integer value) {}
  public void numeric(Number value) {}
  public void numbers(int a, Integer b, long c, Long d, float e, Float f,
                      double g, Double h, Number i) {}
  public void strings(String value) {}
  public void strings(CharSequence value) {}
  public void array(String... values) {}
  public <T> void generic(T value) {}
  public <T> void generic(T[] values) {}
  public void Overloads(boolean value) {}
  public static class Nested { public void ping() {} }
}
""",
    )
    report = batch.packability_report
    assert report.status == "PASS"
    assert batch.conflict_report.conflict_count == 0
    identities = tuple(item.identity for item in report.bindings)
    descriptors = {item.erased_parameter_descriptor for item in identities}
    assert {"Z", "Ljava/lang/Boolean;"} <= descriptors
    assert "Ljava/lang/String;" in descriptors
    assert "Ljava/lang/CharSequence;" in descriptors
    assert "[Ljava/lang/String;" in descriptors
    assert "Ljava/lang/Object;" in descriptors
    assert "[Ljava/lang/Object;" in descriptors
    assert any("$Nested" in item.binary_receiver_identity for item in identities)
    assert any(
        item.callable_kind == "CONSTRUCTOR" and item.member_name == "<init>"
        for item in identities
    )
    assert any(
        item.callable_kind == "METHOD" and item.member_name == "Overloads"
        for item in identities
    )


def test_varargs_and_array_share_one_authoritative_identity(tmp_path):
    batch = _production(
        tmp_path,
        """package demo; public class Overloads {
 public void same(String... values) {}
 public void same(String[] values) {}
 public void retained(int value) {}
}
""",
    )
    groups = batch.packability_report.true_conflict_groups
    assert len(groups) == 1
    assert groups[0].group_kind == "SAME_CANONICAL_IDENTITY_DIFFERENT_CONTENT"
    assert batch.trusted_count == 1


def test_unresolved_classpath_contract_and_overload_cohort_are_withheld(tmp_path):
    batch = _production(
        tmp_path,
        """package demo; public class Overloads extends MissingBase {
 public Overloads() {}
 @Override public void inherited() {}
 public void cohort(MissingType value) {}
 public void cohort(String value) {}
 public void retained(int value) {}
}
""",
    )
    decisions = {item.proposal_id: item for item in batch.decisions}
    bindings = {item.proposal_id: item for item in batch.proposal_batch.bindings}
    nodes = {item.node_id: item for item in batch.source_index.declarations}
    by_signature = {
        nodes[bindings[item].parser_node_id].canonical_source_signature: decision
        for item, decision in decisions.items()
    }
    assert by_signature["<init>():void"].final_state.value == "withheld"
    assert by_signature["inherited():void"].final_state.value == "withheld"
    assert by_signature["cohort(String):void"].blocker_reason.endswith(
        "unresolved_overload_cohort"
    )
    assert by_signature["retained(int):void"].final_state.value == "trusted"


def test_unresolved_sentinel_is_not_an_authoritative_signature(tmp_path):
    batch = _production(
        tmp_path,
        """package demo; public class Overloads {
 public Missing broken(Missing value) { return value; }
 public Missing broken(Missing value, int index) { return value; }
}
""",
    )
    report = detect_java_production_identity_conflicts(
        batch.proposal_batch, batch.source_index
    )
    assert report.conflict_count == 0
    assert batch.trusted_count == 0


def test_search_alias_is_many_to_many_but_exact_reference_is_unique():
    authorities = (
        AuthoritativeIdentity("demo.a", "TEST", "A", "a" * 64),
        AuthoritativeIdentity("demo.b", "TEST", "B", "b" * 64),
    )
    aliases = build_alias_semantics(
        authorities,
        (
            ExactReferenceAlias("A#f(I)", "demo.a"),
            ExactReferenceAlias("A#f(J)", "demo.b"),
        ),
        {"a.f": ("demo.b", "demo.a")},
    )
    assert resolve_alias(aliases, "A#f(I)").status is AliasLookupStatus.EXACT
    result = resolve_alias(aliases, "A.F")
    assert result.status is AliasLookupStatus.AMBIGUOUS_OVERLOAD
    assert result.record_ids == ("demo.a", "demo.b")


def test_candidate_pack_installs_and_answers_exact_java_contract_queries(tmp_path):
    bundle, store, batch = _production_context(
        tmp_path,
        """package demo;
import java.io.IOException;
public class Contracts {
  public Contracts(boolean value) {}
  public Contracts(Boolean value) {}
  public void setValue(boolean value) {}
  public void setValue(Boolean value) {}
  public <T> T generic(T value) throws IOException { return value; }
  public static class Nested { public void ping(String value) {} }
}
""",
    )
    assert batch.packability_report.status == "PASS"
    authorizations = verify_java_production_batch(batch, store)
    by_id = {item.trusted_proposal_id: item for item in authorizations}
    reviewed = []
    approvals = []
    for proposal in batch.trusted_proposals:
        updated, _review, approval = review_proposal(
            proposal,
            reviewer_identity="m335-test-process",
            reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
            decision=ReviewDecision.APPROVE,
            rationale="exact fixture packability closure",
            timestamp=STAMP,
            trust_authorization=by_id[proposal.proposal_id],
        )
        reviewed.append(updated)
        approvals.append(approval)
    pack = compile_provisional_pack(
        bundle,
        batch.segmentation.segments,
        tuple(reviewed),
        tuple(approvals),
        tmp_path / "pack",
        domain_id="m335-java-test",
        production_trust_batch=batch,
        production_authorizations=authorizations,
        store=store,
    )
    providers = ProviderRegistry.build(tmp_path / "providers", ())
    capabilities = CapabilityRegistry.build((), providers)
    validation = validate_pack(pack)
    pack_approval = approve_pack(
        pack_hash=pack.manifest.pack_content_hash,
        knowledge_ir_schema=UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
        concept_graph_hash=pack.manifest.concept_graph_hash,
        source_binding_hashes=pack.manifest.source_binding_hashes,
        capability_resolution_receipt_hashes=(),
        validation_report_hash=content_hash(validation),
        evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
        reviewer_identity="m335-test-install-process",
        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
        decision=PackApprovalDecision.APPROVE,
        policy_version="m335.test.install.v1",
        timestamp=STAMP,
    )
    registry = InstalledDomainRegistry.initialize(
        tmp_path / "installed",
        capability_registry=capabilities,
        provider_registry=providers,
        created_at=STAMP,
    )
    installed = registry.install(pack, pack_approval, (), installed_at=STAMP)
    runtime = GenericDomainRuntime(
        registry.load_installed_pack(installed.domain_id, installed.pack_version),
        installed_registry=registry,
    )
    bindings = batch.packability_report.bindings
    set_values = tuple(
        item for item in bindings if item.identity.member_name == "setValue"
    )
    constructors = tuple(
        item for item in bindings if item.identity.member_name == "<init>"
    )
    generic = next(item for item in bindings if item.identity.member_name == "generic")
    nested = next(item for item in bindings if item.identity.member_name == "ping")
    assert {item.identity.erased_parameter_descriptor for item in set_values} == {
        "Z",
        "Ljava/lang/Boolean;",
    }
    assert (
        len(
            {
                runtime.resolve_knowledge_alias(
                    item.identity.exact_reference
                ).record_ids[0]
                for item in set_values
            }
        )
        == 2
    )
    assert (
        runtime.resolve_knowledge_alias("demo.Contracts.setValue(boolean)").status
        is AliasLookupStatus.EXACT
    )
    assert (
        runtime.resolve_knowledge_alias("demo.Contracts.setValue").status
        is AliasLookupStatus.AMBIGUOUS_OVERLOAD
    )
    assert (
        len(
            {
                runtime.resolve_knowledge_alias(
                    item.identity.exact_reference
                ).record_ids[0]
                for item in constructors
            }
        )
        == 2
    )
    generic_record = runtime.resolve_fact_schema(generic.record_id)
    assert runtime.resolve_knowledge_alias(generic.identity.exact_reference).status is (
        AliasLookupStatus.EXACT
    )
    assert generic_record.content.declared_exceptions == ("IOException",)
    assert generic_record.content.resolved_declared_exceptions == (
        "java.io.IOException",
    )
    assert nested.identity.binary_receiver_identity == "demo.Contracts$Nested"
    assert runtime.resolve_knowledge_alias(nested.identity.exact_reference).status is (
        AliasLookupStatus.EXACT
    )
    assert (
        runtime.resolve_knowledge_alias("demo.Contracts.unknown").status
        is AliasLookupStatus.NOT_FOUND
    )
    assert runtime.verify_currentness()["current"] is True


def test_production_state_audit_is_fail_closed_and_zero_for_pipeline(tmp_path):
    with EnforcedJavaProductionStateAudit() as audit:
        batch = _production(
            tmp_path,
            "package demo; public class Overloads { public void ok(int v) {} }\n",
        )
        with pytest.raises(PermissionError, match="FactMemory.add_entity"):
            FactMemory.add_entity(None)
    report = audit.report()
    assert batch.trusted_count == 1
    assert report.fact_memory_write_attempts == 1
    assert report.rule_memory_write_attempts == 0
    assert report.skill_registry_write_attempts == 0
    assert report.provider_registry_mutation_attempts == 0
    assert report.domain_registry_mutation_attempts == 0


def test_h13_failure_census_is_complete_and_explained():
    root = Path(__file__).parents[1]
    census = json.loads(
        (root / "runs/m335_development/conflict_census.json").read_text(
            encoding="utf-8"
        )
    )
    assert census["alias_group_count"] == 6
    assert census["prior_conflict_count"] == 48
    assert census["unclassified_conflict_count"] == 0
    assert [item["classification"] for item in census["alias_groups"]].count(
        "CASEFOLD_COLLISION"
    ) == 2
    assert all(item["legal_overload"] for item in census["conflicts"])


def test_disclosed_corpus_is_permanently_denylisted():
    value = load_m335_disclosed_corpus_denylist()
    assert value["source_file_count"] == 240
    assert len(value["raw_source_hashes"]) == 240
    assert len(value["canonical_text_hashes"]) == 240
    assert (
        value["source_tree_hash"]
        == "a1da5983e0ab2ba64614d4e1bd69ada1953dfb3b86b8627dcfc317be89378192"
    )
    for digest in value["archive_hashes"]:
        with pytest.raises(ValueError, match="disclosed development archive"):
            assert_not_disclosed_java_archive(digest)


def test_role_aware_freeze_allows_neutral_blob_and_blocks_knowledge_mutations():
    zero = b'{"count":0,"status":"PASS"}\n'
    h = {
        "evaluation/final/source_snapshots/A.java": b"public class A {}\n",
        "evaluation/final/production_process_audit.json": zero,
        "evaluation/final/selector_receipt.json": b'{"selected":["A.java"]}\n',
    }
    manifest = build_final_artifact_role_manifest(h)
    positive = verify_role_aware_disclosure(
        {"runs/development/zero.json": zero}, h, manifest
    )
    assert positive.passed and positive.neutral_reuse_count == 1
    leaked = verify_role_aware_disclosure(
        {"hidden/renamed.txt": h["evaluation/final/source_snapshots/A.java"]},
        h,
        manifest,
    )
    assert not leaked.passed
    first = next(
        item
        for item in manifest.bindings
        if item.role is FinalArtifactRole.FINAL_SOURCE_BYTES
    )
    weakened = replace(
        manifest,
        bindings=tuple(
            replace(item, role=FinalArtifactRole.PROCESS_AUDIT)
            if item == first
            else item
            for item in manifest.bindings
        ),
    )
    weakened_body = asdict(weakened)
    weakened_body.pop("manifest_hash")
    weakened = replace(weakened, manifest_hash=content_hash(weakened_body))
    with pytest.raises(ValueError, match="weakened"):
        verify_role_aware_disclosure({}, h, weakened)


def test_all_sixteen_freeze_mutations_are_executably_blocked(tmp_path):
    root = Path(__file__).parents[1]
    output = tmp_path / "mutations.json"
    subprocess.run(
        (
            sys.executable,
            str(root / "scripts/m335_verify_freeze_mutations.py"),
            "--output",
            str(output),
        ),
        cwd=root,
        check=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mutation_count"] == report["blocked_count"] == 16
    assert report["neutral_audit_blob_reuse_pass"]


def test_component_comparator_reports_first_stage_and_identity():
    components = tuple(
        JavaProductionComponent(
            stage, content_hash(((stage, stage),)), ((stage, stage),)
        )
        for stage in JAVA_COMPONENT_STAGE_ORDER
    )
    body = {"schema_version": 1, "components": components, "platform_independent": True}
    left = JavaProductionComponentManifest(**body, manifest_hash=content_hash(body))
    changed = replace(
        components[1], component_hash="f" * 64, items=(("path", "f" * 64),)
    )
    right_components = (components[0], changed, *components[2:])
    right_body = {**body, "components": right_components}
    right = JavaProductionComponentManifest(
        **right_body, manifest_hash=content_hash(right_body)
    )
    difference = compare_java_component_manifests(left, right)
    assert difference.first_differing_stage == "source_content_manifest"
    assert difference.difference_count == 1


def test_pre_freeze_v3_is_strict_and_every_criterion_mutation_blocks():
    passing = {
        key: (expected == "true" if operator == "BOOL" else expected)
        for _name, key, operator, expected in M335_PRE_FREEZE_V3_SPECS
    }
    report = evaluate_m335_pre_freeze_gate_v3(passing)
    assert report.decision is M335PreFreezeDecision.READY_FOR_FRESH_JAVA_FREEZE
    assert len(run_m335_gate_mutations(passing)) == len(M335_PRE_FREEZE_V3_SPECS)
    with pytest.raises(ValueError, match="schema mismatch"):
        evaluate_m335_pre_freeze_gate_v3({**passing, "unexpected": True})
