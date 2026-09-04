from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.compiler import (
    compile_provisional_pack,
    resolve_applicability_references,
)
from ai_brain.stage3.acquisition.java_compilation_identity import (
    JAVA_SEMANTIC_COMPILATION_EPOCH,
    build_java_compilation_audit_receipt,
)
from ai_brain.stage3.acquisition.java_diagnostic_scope import (
    JavaDiagnosticScope,
    classify_java_diagnostic_scope,
    diagnostic_scope_from_receipt,
)
from ai_brain.stage3.acquisition.java_final_gate import (
    M336_FINAL_GATE_SPECS,
    M336FinalOutcome,
    evaluate_m336_final_gate,
)
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    M336_BASE_SHA,
    M336_BRANCH,
    M336_COMMIT_MESSAGES,
    M336_E15_PREFIXES,
    M336_EXCLUDED_M33_SHA,
    M336_H15_PREFIXES,
)
from ai_brain.stage3.acquisition.java_freeze_roles import (
    FinalArtifactRole,
    build_final_artifact_role_manifest,
    derive_protected_disclosure_tokens,
    verify_role_aware_disclosure,
)
from ai_brain.stage3.acquisition.java_jdk_provider import (
    M336_JAVAC_INVOCATION_POLICY,
    frozen_m336_jdk_provider_manifest,
)
from ai_brain.stage3.acquisition.java_packability import (
    verify_java_packability_report,
)
from ai_brain.stage3.acquisition.java_pre_freeze_gate_v4 import (
    M336_PRE_FREEZE_V4_SPECS,
    M336PreFreezeDecision,
    evaluate_m336_pre_freeze_gate_v4,
    run_m336_gate_mutations,
)
from ai_brain.stage3.acquisition.java_production import (
    run_java_acquisition_pipeline,
    seal_java_production_output,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX,
    JAVA_PRODUCTION_REPLAY_FILENAME,
    verify_compiled_java_production_standalone,
)
from ai_brain.stage3.acquisition.java_replay_mutations import (
    run_m336_replay_mutation_battery,
)
from ai_brain.stage3.acquisition.java_source_selector import (
    frozen_m336_final_source_selector_policy,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import (
    _bundle_semantic_body,
    _document_semantic_body,
    ingest_bundle,
    verify_bundle,
)
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION
from ai_brain.stage3.providers.registry import ProviderRegistry

STAMP = "2026-09-04T00:00:00Z"


def _write_java(root: Path, relative: str, value: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")
    return path


def _rehash_bundle(bundle):
    documents = []
    for document in bundle.documents:
        values = asdict(document)
        values.pop("document_hash")
        documents.append(
            replace(
                document, document_hash=content_hash(_document_semantic_body(values))
            )
        )
    manifest = replace(
        bundle.manifest, document_hashes=tuple(item.document_hash for item in documents)
    )
    values = asdict(manifest)
    values.pop("manifest_hash")
    manifest = replace(manifest, manifest_hash=content_hash(values))
    result = replace(bundle, documents=tuple(documents), manifest=manifest)
    values = asdict(result)
    values.pop("bundle_hash")
    return replace(result, bundle_hash=content_hash(_bundle_semantic_body(values)))


def _rehash_report(report):
    values = asdict(report)
    values.pop("report_hash")
    return replace(report, report_hash=content_hash(values))


def _production(tmp_path, source: str, *, stamp: str = STAMP, bundle_id="m336-test"):
    root = tmp_path / "source"
    path = _write_java(root, "root/demo/Contracts.java", source)
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        (path,),
        bundle_id=bundle_id,
        domain_tags=("java-api",),
        imported_at=stamp,
        source_root=root,
        store=store,
    )
    batch = run_java_acquisition_pipeline(
        bundle, store, deterministic_run_id="m336.test.v1"
    )
    return bundle, store, batch


def _compile_trusted(tmp_path, source: str, *, stamp: str):
    bundle, store, batch = _production(
        tmp_path, source, stamp=stamp, bundle_id="m336-clock"
    )
    authorizations = verify_java_production_batch(batch, store)
    by_id = {item.trusted_proposal_id: item for item in authorizations}
    proposals = []
    approvals = []
    for proposal in batch.trusted_proposals:
        approved, _review, approval = review_proposal(
            proposal,
            reviewer_identity="m336-test-process",
            reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
            decision=ReviewDecision.APPROVE,
            rationale="M-33.6 deterministic test approval",
            timestamp=STAMP,
            trust_authorization=by_id[proposal.proposal_id],
        )
        proposals.append(approved)
        approvals.append(approval)
    pack_root = tmp_path / "pack"
    pack = compile_provisional_pack(
        bundle,
        batch.segmentation.segments,
        tuple(proposals),
        tuple(approvals),
        pack_root,
        domain_id="m336-java-test",
        production_trust_batch=batch,
        production_authorizations=authorizations,
        store=store,
    )
    tree = tuple(
        (path.relative_to(pack_root).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(pack_root.rglob("*"))
        if path.is_file()
    )
    return bundle, batch, pack, tree


def test_canonical_bundle_verifier_blocks_rehashed_shape_tampering(tmp_path):
    root = tmp_path / "source"
    bundle = ingest_bundle(
        (
            _write_java(root, "b/B.java", "package b; public class B {}\n"),
            _write_java(root, "a/A.java", "package a; public class A {}\n"),
        ),
        bundle_id="m336-canonical",
        domain_tags=("z", "a", "z"),
        imported_at=STAMP,
        source_root=root,
    )
    assert bundle.domain_tags == ("a", "z")
    verify_bundle(bundle)

    reverse = _rehash_bundle(
        replace(bundle, documents=tuple(reversed(bundle.documents)))
    )
    with pytest.raises(ValueError, match="order"):
        verify_bundle(reverse)

    changed_id = replace(
        bundle,
        documents=(
            replace(bundle.documents[0], document_id="caller.supplied"),
            *bundle.documents[1:],
        ),
    )
    with pytest.raises(ValueError, match="content-derived"):
        verify_bundle(_rehash_bundle(changed_id))

    changed_path = replace(
        bundle,
        documents=(
            replace(bundle.documents[0], relative_path="C:/absolute/A.java"),
            *bundle.documents[1:],
        ),
    )
    with pytest.raises(ValueError, match="relative path"):
        verify_bundle(_rehash_bundle(changed_path))

    tags = _rehash_bundle(replace(bundle, domain_tags=("z", "a")))
    with pytest.raises(ValueError, match="tags"):
        verify_bundle(tags)

    non_nfc = replace(
        bundle,
        documents=(
            replace(bundle.documents[0], relative_path="cafe\u0301.java"),
            *bundle.documents[1:],
        ),
    )
    with pytest.raises(ValueError, match="NFC"):
        verify_bundle(_rehash_bundle(non_nfc))

    duplicate = replace(
        bundle,
        documents=(
            bundle.documents[0],
            replace(
                bundle.documents[1], relative_path=bundle.documents[0].relative_path
            ),
        ),
    )
    with pytest.raises(ValueError, match="unique"):
        verify_bundle(_rehash_bundle(duplicate))

    casefold = replace(
        bundle,
        documents=(
            bundle.documents[0],
            replace(
                bundle.documents[1],
                relative_path=bundle.documents[0].relative_path.upper(),
            ),
        ),
    )
    with pytest.raises(ValueError, match="casefold"):
        verify_bundle(_rehash_bundle(casefold))


def test_audit_timestamp_is_visible_but_semantically_inert(tmp_path):
    root = tmp_path / "source"
    source = _write_java(root, "demo/A.java", "package demo; public class A {}\n")
    one = ingest_bundle(
        (source,), bundle_id="clock", imported_at=STAMP, source_root=root
    )
    two = replace(
        one,
        documents=(replace(one.documents[0], imported_at="2031-01-01T03:00:00+03:00"),),
        created_at="2031-01-01T03:00:00+03:00",
    )
    verify_bundle(two)
    assert one.bundle_hash == two.bundle_hash
    assert one.created_at != two.created_at
    first = build_java_compilation_audit_receipt(
        bundle_hash=one.bundle_hash,
        compiler_identity_hash="a" * 64,
        audit_timestamp=one.created_at,
    )
    second = build_java_compilation_audit_receipt(
        bundle_hash=two.bundle_hash,
        compiler_identity_hash="a" * 64,
        audit_timestamp=two.created_at,
    )
    assert first.semantic_receipt_hash == second.semantic_receipt_hash
    assert first.audit_receipt_hash != second.audit_receipt_hash


def test_java_candidate_pack_is_wall_clock_independent(tmp_path):
    source = (
        "package demo; public class Contracts { public int get(int v) { return v; } }\n"
    )
    one = _compile_trusted(tmp_path / "one", source, stamp=STAMP)
    two = _compile_trusted(tmp_path / "two", source, stamp="2031-01-01T03:00:00+03:00")
    assert seal_java_production_output(one[1]) == seal_java_production_output(two[1])
    assert one[1].packability_report == two[1].packability_report
    assert one[3] == two[3]
    assert one[2].manifest.created_at == JAVA_SEMANTIC_COMPILATION_EPOCH
    assert two[2].manifest.created_at == JAVA_SEMANTIC_COMPILATION_EPOCH


def test_production_replay_binds_the_exact_java_release(tmp_path):
    _bundle, _batch, _pack, _tree = _compile_trusted(
        tmp_path,
        "package demo; public class A { public void call(int value) {} }\n",
        stamp=STAMP,
    )
    pack_root = tmp_path / "pack"
    assert verify_compiled_java_production_standalone(pack_root)["status"] == "PASS"
    replay_path = pack_root / JAVA_PRODUCTION_REPLAY_FILENAME
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay["release_identity"]["policy_version"] = "forged.release"
    replay.pop("artifact_hash")
    replay_hash = content_hash(replay)
    replay_path.write_text(
        canonical_json({**replay, "artifact_hash": replay_hash}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest_path = pack_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dependency_packs"] = [
        JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX + replay_hash
        if item.startswith(JAVA_PRODUCTION_REPLAY_DEPENDENCY_PREFIX)
        else item
        for item in manifest["dependency_packs"]
    ]
    manifest.pop("pack_content_hash")
    pack_hash = content_hash(manifest)
    manifest_path.write_text(
        canonical_json({**manifest, "pack_content_hash": pack_hash}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    outer_path = pack_root / "pack_manifest.json"
    outer = json.loads(outer_path.read_text(encoding="utf-8"))
    outer["pack_content_hash"] = pack_hash
    outer_path.write_text(canonical_json(outer) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="release"):
        verify_compiled_java_production_standalone(pack_root)


def test_all_twenty_replay_authority_mutations_fail_closed(tmp_path):
    _bundle, _batch, pack, _tree = _compile_trusted(
        tmp_path,
        "package demo; public class A { public void call(int value) {} }\n",
        stamp=STAMP,
    )
    providers = ProviderRegistry.build(tmp_path / "providers", ())
    capabilities = CapabilityRegistry.build((), providers)
    validation = validate_pack(pack)
    approval = approve_pack(
        pack_hash=pack.manifest.pack_content_hash,
        knowledge_ir_schema=UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
        concept_graph_hash=pack.manifest.concept_graph_hash,
        source_binding_hashes=pack.manifest.source_binding_hashes,
        capability_resolution_receipt_hashes=(),
        validation_report_hash=content_hash(validation),
        evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
        reviewer_identity="m336-test-release-process",
        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
        decision=PackApprovalDecision.APPROVE,
        policy_version="m336.test.release.v1",
        timestamp=STAMP,
    )
    registry = InstalledDomainRegistry.initialize(
        tmp_path / "installed",
        capability_registry=capabilities,
        provider_registry=providers,
        created_at=STAMP,
    )
    registry.install(pack, approval, (), installed_at=STAMP)
    report = run_m336_replay_mutation_battery(
        tmp_path / "pack",
        installed_pack_root=registry.root,
        provider_registry=providers,
    )
    assert report["status"] == "PASS"
    assert report["mutation_count"] == report["rejected_count"] == 20


def test_final_roles_fail_closed_and_disclosure_tokens_are_derived():
    digest = "d" * 64
    h = {
        "evaluation/m336_final_java/source_snapshots/root/A.java": b"class A {}\n",
        "evaluation/m336_final_java/selector_receipt.json": json.dumps(
            {"archive_hash": digest, "selected": ["root/A.java"]}
        ).encode(),
        "evaluation/m336_final_java/production_process_audit.json": b'{"count":0}\n',
    }
    manifest = build_final_artifact_role_manifest(h)
    assert derive_protected_disclosure_tokens(h, manifest)
    clean = verify_role_aware_disclosure(
        {"docs/process.md": b"neutral\n"}, h, manifest, protected_tokens=()
    )
    assert clean.passed and clean.derived_protected_token_count >= 3
    leaked = verify_role_aware_disclosure(
        {"src/frozen.py": f'ARCHIVE = "{digest}"\n'.encode()}, h, manifest
    )
    assert not leaked.passed and digest in leaked.leaked_tokens
    with pytest.raises(ValueError, match="unknown final artifact role"):
        build_final_artifact_role_manifest(
            {"evaluation/m336_final_java/unclassified.json": b"{}\n"}
        )
    source_binding = next(
        item
        for item in manifest.bindings
        if item.role is FinalArtifactRole.FINAL_SOURCE_BYTES
    )
    weakened = replace(
        manifest,
        bindings=tuple(
            replace(item, role=FinalArtifactRole.PROCESS_AUDIT)
            if item == source_binding
            else item
            for item in manifest.bindings
        ),
    )
    weakened = replace(
        weakened,
        manifest_hash=content_hash(
            {
                key: value
                for key, value in asdict(weakened).items()
                if key != "manifest_hash"
            }
        ),
    )
    with pytest.raises(ValueError, match="weakened"):
        verify_role_aware_disclosure({}, h, weakened)


def test_deep_packability_verifier_blocks_all_relational_mutations(tmp_path):
    _bundle, _store, batch = _production(
        tmp_path,
        """package demo;
public class Contracts {
  public void duplicate(int value) {}
  public void duplicate(int value) {}
  public void unique(String value) {}
}
""",
    )
    report = batch.packability_report
    verify_java_packability_report(
        report,
        trusted_proposal_ids=tuple(
            item.proposal_id for item in batch.trusted_proposals
        ),
    )
    assert report.withholding_reasons
    packable = report.packable_proposal_ids[0]
    withheld = report.withholding_reasons[0][0]
    binding = next(item for item in report.bindings if item.proposal_id == packable)

    changed_binding = replace(binding, record_id="java.knowledge." + "f" * 32)
    changed_binding = replace(
        changed_binding,
        binding_hash=content_hash(
            {
                key: value
                for key, value in asdict(changed_binding).items()
                if key != "binding_hash"
            }
        ),
    )
    mutations = [
        replace(report, withholding_reasons=report.withholding_reasons[1:]),
        replace(
            report,
            packable_proposal_ids=tuple(
                sorted((*report.packable_proposal_ids, withheld))
            ),
        ),
        replace(report, bindings=report.bindings[1:]),
        replace(
            report,
            bindings=tuple(
                changed_binding if item == binding else item for item in report.bindings
            ),
        ),
        replace(
            report,
            exact_references=tuple(
                (key, "unknown.record")
                if key == binding.identity.exact_reference
                else (key, value)
                for key, value in report.exact_references
            ),
        ),
        replace(
            report,
            search_aliases=(*report.search_aliases, ("unknown", ("unknown.record",))),
        ),
        replace(
            report,
            duplicate_groups=tuple(
                replace(item, group_kind="ALTERED") for item in report.duplicate_groups
            ),
        ),
        replace(report, duplicate_groups=()),
        replace(report, unresolved_references=((packable, "missing"),), status="PASS"),
        replace(report, candidate_record_ids=()),
    ]
    for mutation in mutations:
        with pytest.raises(ValueError):
            verify_java_packability_report(_rehash_report(mutation))


def test_scoped_exact_references_disambiguate_roots_modules_and_packs(tmp_path):
    root = tmp_path / "source"
    paths = (
        _write_java(
            root,
            "root-a/demo/Same.java",
            "package demo; public class Same { public void call(int v) {} }\n",
        ),
        _write_java(
            root,
            "root-b/demo/Same.java",
            "package demo; public class Same { public void call(int v) {} }\n",
        ),
        _write_java(
            root,
            "java.one/demo/Named.java",
            "package demo; public class Named { public void call(int v) {} }\n",
        ),
        _write_java(
            root,
            "java.two/demo/Named.java",
            "package demo; public class Named { public void call(int v) {} }\n",
        ),
    )
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        paths,
        bundle_id="scoped",
        domain_tags=("java-api",),
        imported_at=STAMP,
        source_root=root,
        store=store,
    )
    batch = run_java_acquisition_pipeline(bundle, store, deterministic_run_id="scoped")
    calls = tuple(
        item
        for item in batch.packability_report.bindings
        if item.identity.member_name == "call"
    )
    references = {item.identity.exact_reference for item in calls}
    assert len(calls) == len(references) == 4
    assert all(value.startswith("java:21/") for value in references)
    assert {item.identity.source_scope for item in calls} == {
        "root-a",
        "root-b",
        "java.one",
        "java.two",
    }
    verify_java_packability_report(batch.packability_report)


def test_diagnostic_scope_is_explicit_and_unknown_never_authorizes():
    def loc(start, end):
        return SimpleNamespace(byte_start=start, byte_end=end)

    target = SimpleNamespace(
        source_unit_id="root/A.java",
        receiver_type="demo.A",
        member_kind="method",
        declaration_span=loc(20, 80),
    )
    enclosing = SimpleNamespace(
        source_unit_id="root/A.java",
        receiver_type="demo.A",
        member_kind="class",
        declaration_span=loc(0, 100),
    )
    unrelated = SimpleNamespace(
        source_unit_id="root/A.java",
        receiver_type="demo.B",
        member_kind="method",
        declaration_span=loc(110, 150),
    )
    raw = b" " * 40 + b"{" + b" " * 159
    declarations = (target, enclosing, unrelated)
    assert (
        classify_java_diagnostic_scope(
            diagnostic_start=25,
            diagnostic_end=30,
            target=target,
            declarations=declarations,
            raw=raw,
        )
        is JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING
    )
    assert (
        classify_java_diagnostic_scope(
            diagnostic_start=50,
            diagnostic_end=55,
            target=target,
            declarations=declarations,
            raw=raw,
        )
        is JavaDiagnosticScope.BODY_ONLY
    )
    assert (
        classify_java_diagnostic_scope(
            diagnostic_start=5,
            diagnostic_end=10,
            target=target,
            declarations=declarations,
            raw=raw,
        )
        is JavaDiagnosticScope.ENCLOSING_TYPE_BLOCKING
    )
    assert (
        classify_java_diagnostic_scope(
            diagnostic_start=120,
            diagnostic_end=125,
            target=target,
            declarations=declarations,
            raw=raw,
        )
        is JavaDiagnosticScope.UNRELATED_DECLARATION
    )
    assert (
        classify_java_diagnostic_scope(
            diagnostic_start=170,
            diagnostic_end=175,
            target=target,
            declarations=declarations,
            raw=raw,
        )
        is JavaDiagnosticScope.AMBIENT_FILE
    )
    assert (
        diagnostic_scope_from_receipt(SimpleNamespace(applicability="nonsense"))
        is JavaDiagnosticScope.UNKNOWN_SCOPE
    )


def test_applicability_closure_never_silently_discards_a_reference():
    aliases = {"proposal.condition": "java.knowledge.condition"}
    assert resolve_applicability_references((), aliases) == ()
    assert resolve_applicability_references(("proposal.condition",), aliases) == (
        "java.knowledge.condition",
    )
    digest = "a" * 64
    assert (
        resolve_applicability_references(
            (f"inline-condition:{digest}",), aliases, inline_condition_hashes=(digest,)
        )
        == ()
    )
    assert (
        resolve_applicability_references(
            ("constant acceleration",),
            aliases,
            source_backed_inline_conditions=("constant acceleration",),
        )
        == ()
    )
    for value in ("missing", "ambiguous", "conflicting", "REVIEW_REQUIRED"):
        with pytest.raises(ValueError):
            resolve_applicability_references((value,), aliases)


def test_m336_policy_is_frozen_without_source_body_facts():
    policy = frozen_m336_final_source_selector_policy()
    assert len(policy.families) == 3
    assert dict(policy.minimums)["real_callable_targets"] == 2_000
    assert policy.maximum_root_target_fraction == "0.800000"
    assert {item.family_id for item in policy.families}.isdisjoint(
        {"apache-commons-lang3", "apache-commons-io", "jackson", "openjdk"}
    )
    assert M336_BASE_SHA == "6b0c31e6e6f987216923a66e332370aeeffa9f48"
    assert M336_EXCLUDED_M33_SHA == "b94c17dc8b1026fe9e338b5fc0a4926b23d68a39"
    assert M336_BRANCH == "exp/stage3-m336-fresh-java-freeze"
    assert M336_COMMIT_MESSAGES == (
        "M-33.6 freeze Java acquisition v2",
        "M-33.6 untouched Java black-box evaluation",
        "M-33.6 exact-SHA Java freeze evidence",
    )
    assert M336_H15_PREFIXES and M336_E15_PREFIXES
    provider = frozen_m336_jdk_provider_manifest()
    assert provider.target_release == 21
    assert provider.javac_invocation_policy == M336_JAVAC_INVOCATION_POLICY
    assert {item.platform for item in provider.platforms} == {"windows", "karina"}


def test_m336_pre_freeze_gate_is_closed_and_every_criterion_mutation_blocks():
    passing = {}
    for _identifier, key, operator, threshold in M336_PRE_FREEZE_V4_SPECS:
        if operator == "BOOL":
            passing[key] = threshold == "true"
        elif operator == "MAX":
            passing[key] = int(threshold)
        else:
            passing[key] = threshold
    report = evaluate_m336_pre_freeze_gate_v4(passing)
    assert report.decision is M336PreFreezeDecision.READY_FOR_FINAL_ACQUISITION
    assert report.pass_count == report.mandatory_count == len(M336_PRE_FREEZE_V4_SPECS)
    assert len(run_m336_gate_mutations(passing)) == len(M336_PRE_FREEZE_V4_SPECS)


def test_m336_final_gate_selects_a_b_and_c_without_threshold_mutation():
    passing = {}
    for _identifier, key, operator, threshold, _safety in M336_FINAL_GATE_SPECS:
        passing[key] = threshold == "true" if operator == "BOOL" else threshold
    assert evaluate_m336_final_gate(passing).outcome is M336FinalOutcome.OUTCOME_A
    quality = {**passing, "location_recall": "0.949999"}
    assert evaluate_m336_final_gate(quality).outcome is M336FinalOutcome.OUTCOME_B
    unsafe = {**passing, "wrong_trusted_count": 1}
    assert evaluate_m336_final_gate(unsafe).outcome is M336FinalOutcome.OUTCOME_C
