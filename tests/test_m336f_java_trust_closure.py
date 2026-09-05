from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_diagnostic_scope import JavaDiagnosticScope
from ai_brain.stage3.acquisition.java_evidence_policy import (
    enumerate_java_evidence_requirements,
)
from ai_brain.stage3.acquisition.java_jdk_provider import (
    frozen_m336_jdk_provider_manifest,
)
from ai_brain.stage3.acquisition.java_production import run_java_acquisition_pipeline
from ai_brain.stage3.acquisition.java_production_compiler import (
    _NOTE,
    DeclarationDiagnosticBinding,
    JavaCompilerDiagnostic,
    JavaProductionCompilationProbe,
    JavaProductionCompilerReport,
    _bind_diagnostic,
    _canonical_reported_path,
    build_java_compilation_trust_gate,
    java_production_compiler_identity_hash,
    utf16_line_column_to_utf8_span,
    verify_java_production_compilation_probe_receipt,
    verify_java_production_compiler_report,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.m336e_identity import (
    build_source_entry_binding,
    build_source_entry_binding_manifest,
    build_source_entry_id,
)
from ai_brain.stage3.acquisition.m336e_selectability import (
    build_selectable_source_census,
    build_selectable_source_decision,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    build_java_compilation_closure_manifest,
    prove_java_compilation_closure_feasibility,
)
from ai_brain.stage3.acquisition.m336f_contracts import (
    M336F_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    run_m336f_producer_contract_gate,
)
from ai_brain.stage3.acquisition.m336f_evaluation_artifacts import (
    build_m336f_evaluation_telemetry_receipt,
    build_m336f_semantic_evaluation_artifact,
    semantic_artifacts_byte_identical,
)
from ai_brain.stage3.acquisition.m336f_forensics import (
    CompilationContextObservation,
    classify_compilation_contexts,
)
from ai_brain.stage3.acquisition.m336f_license_evaluation import (
    split_m336f_license_evaluation,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    M336FSelectorLedger,
    select_compilation_closed_sources_once,
    verify_m336f_selection,
)
from ai_brain.stage3.acquisition.m336f_thresholds import (
    M336F_JAVA_ACCEPTANCE_THRESHOLDS,
    build_m336f_trust_metrics,
    ratio_meets_threshold,
    verify_m336f_threshold_manifest,
)
from ai_brain.stage3.acquisition.m336f_trust_opportunities import (
    build_trust_coverage_opportunity_report,
    classify_trust_coverage_blocker,
    verify_trust_coverage_opportunity_report,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle


def _bundle(tmp_path: Path, sources: dict[str, bytes]):
    root = tmp_path / "sources"
    paths = []
    for relative, raw in sources.items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        paths.append(path)
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        tuple(paths),
        bundle_id="m336f-test",
        domain_tags=("java-api",),
        imported_at="1970-01-01T00:00:00Z",
        source_root=root,
        store=store,
    )
    return store, bundle, index_java_bundle(bundle, store)


def _diagnostic(unit: str | None, raw: bytes, line: int, column: int):
    if unit is None:
        position = start = end = None
    else:
        position, start, end = utf16_line_column_to_utf8_span(raw, line, column)
    body = {
        "source_entry_id": "1" * 64 if unit else None,
        "source_unit_id": unit,
        "source_unit_identity": content_hash((unit, bytes_hash(raw))) if unit else None,
        "diagnostic_code": "compiler.err.cant.resolve.location",
        "normalized_category": "UNRESOLVED_TYPE",
        "diagnostic_kind": "ERROR",
        "line": line if unit else None,
        "column": column if unit else None,
        "canonical_position": position,
        "canonical_byte_start": start,
        "canonical_byte_end": end,
    }
    return JavaCompilerDiagnostic(**body, diagnostic_hash=content_hash(body))


def _report(index, diagnostics, bindings, *, malformed=()):
    body = {
        "schema_version": 2,
        "compiler_policy_version": "m336f.production-javac-diagnostics.v2",
        "compiler_identity_hash": "2" * 64,
        "compilation_run_hash": "3" * 64,
        "source_manifest_hash": "4" * 64,
        "source_file_count": len({item.source_unit_id for item in index.declarations}),
        "diagnostic_count": len(diagnostics),
        "error_count": len(diagnostics),
        "warning_count": 0,
        "unknown_scope_count": sum(
            item.diagnostic_scope is JavaDiagnosticScope.UNKNOWN_SCOPE
            for item in bindings
        ),
        "unmapped_diagnostic_count": sum(not item.declaration_ids for item in bindings),
        "source_unit_unbound_count": sum(
            item.source_unit_id is None for item in diagnostics
        ),
        "malformed_output_count": len(malformed),
        "malformed_output_hashes": tuple(malformed),
        "process_exit_code": 1 if diagnostics or malformed else 0,
        "diagnostics": tuple(diagnostics),
        "bindings": tuple(bindings),
    }
    value = JavaProductionCompilerReport(**body, report_hash=content_hash(body))
    verify_java_production_compiler_report(value)
    return value


def test_thresholds_are_frozen_count_first_and_exact():
    verify_m336f_threshold_manifest(M336F_JAVA_ACCEPTANCE_THRESHOLDS)
    assert ratio_meets_threshold(17, 20, "0.850000")
    assert not ratio_meets_threshold(849_999, 1_000_000, "0.850000")
    metrics = build_m336f_trust_metrics(
        actual_trusted=972,
        expected_trusted=1143,
        correct_trusted=972,
        wrong_trusted=0,
        correct_withheld=10,
        incorrect_withheld=171,
    )
    assert metrics.trust_precision == "1.000000"
    assert metrics.trust_recall == metrics.safe_trust_coverage == "0.850394"
    assert metrics.legacy_trust_coverage == metrics.safe_trust_coverage
    with pytest.raises(ValueError, match="denominator"):
        build_m336f_trust_metrics(
            actual_trusted=3,
            expected_trusted=3,
            correct_trusted=2,
            wrong_trusted=0,
            correct_withheld=0,
            incorrect_withheld=1,
        )


def test_trust_coverage_opportunities_are_evaluator_only_and_generic():
    location = {
        "document_bytes_hash": "1" * 64,
        "source_unit_id": "root/p/A.java",
        "start_offset": 1,
        "end_offset": 10,
    }
    golden = SimpleNamespace(
        **location,
        expected_supported=True,
        golden_hash="2" * 64,
    )
    candidate = {
        **location,
        "proposal_id": "proposal.generic",
        "declaration_hash": "3" * 64,
        "production_trust_state": "withheld",
        "production_blocker_reason": "untrusted_compiler_blocking_diagnostic",
        "compiler_report_hash": "4" * 64,
        "decision_hash": "5" * 64,
    }
    report = build_trust_coverage_opportunity_report(
        {"candidate_rows": [candidate]},
        SimpleNamespace(goldens=(golden,)),
    )
    verify_trust_coverage_opportunity_report(report)
    assert report.evaluation_only
    assert report.false_negative_opportunity_count == 1
    assert report.category_counts == (("COMPILER_DIAGNOSTIC_OVERREACH", 1),)
    assert (
        classify_trust_coverage_blocker("untrusted_missing_field_evidence")
        == "INCOMPLETE_FIELD_EVIDENCE"
    )
    assert (
        classify_trust_coverage_blocker("untrusted_missing_production_candidate")
        == "UNSUPPORTED_DECLARATION_MAPPING"
    )


def test_compiler_identity_is_common_while_platform_executable_hashes_differ():
    provider = frozen_m336_jdk_provider_manifest()
    assert len({item.javac_sha256 for item in provider.platforms}) == 2
    identities = {
        java_production_compiler_identity_hash(
            provider_manifest_hash=provider.manifest_hash,
            javac_version=f"javac {item.version}",
            release=21,
            classpath_manifest_hash=content_hash(()),
        )
        for item in provider.platforms
    }
    assert len(identities) == 1
    platform = provider.platforms[0]
    body = {
        "schema_version": 2,
        "policy_version": "m336f.production-javac-diagnostics.v2",
        "provider_manifest_hash": provider.manifest_hash,
        "compiler_identity_hash": next(iter(identities)),
        "javac_sha256": platform.javac_sha256,
        "javac_version": f"javac {platform.version}",
        "release": 21,
        "encoding": "UTF-8",
        "annotation_processing": False,
        "locale_policy": "JAVAC_XDRAWDIAGNOSTICS_EN_US",
        "classpath_manifest_hash": content_hash(()),
    }
    probe = JavaProductionCompilationProbe(**body, probe_hash=content_hash(body))
    verify_java_production_compilation_probe_receipt(probe)
    forged_body = {**body, "javac_sha256": "0" * 64}
    forged = JavaProductionCompilationProbe(
        **forged_body, probe_hash=content_hash(forged_body)
    )
    with pytest.raises(ValueError, match="identity or policy"):
        verify_java_production_compilation_probe_receipt(forged)
    forged_version_body = {
        **body,
        "javac_version": f"forged-javac {platform.version}",
    }
    forged_version_body["compiler_identity_hash"] = (
        java_production_compiler_identity_hash(
            provider_manifest_hash=provider.manifest_hash,
            javac_version=forged_version_body["javac_version"],
            release=21,
            classpath_manifest_hash=forged_version_body["classpath_manifest_hash"],
        )
    )
    forged_version = JavaProductionCompilationProbe(
        **forged_version_body,
        probe_hash=content_hash(forged_version_body),
    )
    with pytest.raises(ValueError, match="identity or policy"):
        verify_java_production_compilation_probe_receipt(forged_version)


def test_utf16_position_maps_unicode_and_canonicalizes_crlf():
    raw = "a\r\nб😀e\u0301\tz\r\n".encode()
    assert utf16_line_column_to_utf8_span(raw, 2, 4) == (4, 8, 9)
    assert utf16_line_column_to_utf8_span(raw, 2, 5) == (5, 9, 11)
    assert utf16_line_column_to_utf8_span(raw, 2, 7) == (7, 12, 13)
    with pytest.raises(ValueError, match="bisects"):
        utf16_line_column_to_utf8_span(raw, 2, 3)


def test_duplicate_javac_basenames_bind_by_stable_payload_and_occurrence():
    documents = {
        "root/a/package-info.java": object(),
        "root/b/package-info.java": object(),
        "root/c/package-info.java": object(),
    }
    raw = {
        "root/a/package-info.java": b"@Missing\npackage a;\n",
        "root/b/package-info.java": b"@Missing\npackage b;\n",
        "root/c/package-info.java": b"@Other\npackage c;\n",
    }
    kwargs = {
        "raw_by_unit": raw,
        "line": 1,
        "diagnostic_payload": "kindname.class, Missing, , ",
    }
    assert (
        _canonical_reported_path(
            "package-info.java", documents, occurrence_index=0, **kwargs
        )
        == "root/a/package-info.java"
    )
    assert (
        _canonical_reported_path(
            "package-info.java", documents, occurrence_index=1, **kwargs
        )
        == "root/b/package-info.java"
    )
    assert (
        _canonical_reported_path(
            "package-info.java", documents, occurrence_index=2, **kwargs
        )
        is None
    )


def test_inherited_nested_type_resolves_from_source_closure(tmp_path: Path):
    sources = {
        "p/Outer.java": (
            b"package p; public interface Outer<T> { interface Inner<T> {} }\n"
        ),
        "p/Marker.java": b"package p; public interface Marker {}\n",
        "q/Base.java": (
            b"package q; import p.*; public abstract class Base<E> "
            b"implements Outer<E>, Marker {}\n"
        ),
        "q/Child.java": (
            b"package q; public class Child<E> extends Base<E> { "
            b"public void use(Inner<E> value) {} }\n"
        ),
    }
    _store, _bundle_value, index = _bundle(tmp_path, sources)
    declaration = next(item for item in index.declarations if item.member_name == "use")
    assert declaration.parameters[0].resolution.resolved_type == "p.Outer.Inner"


def test_implicit_public_nested_interface_type_resolves_by_explicit_import(
    tmp_path: Path,
):
    sources = {
        "p/Outer.java": b"package p; public interface Outer { interface Inner {} }\n",
        "q/Use.java": (
            b"package q; import p.Outer.Inner; public class Use { "
            b"public void use(Inner value) {} }\n"
        ),
    }
    _store, _bundle_value, index = _bundle(tmp_path, sources)
    nested = next(
        item for item in index.declarations if item.receiver_type == "p.Outer.Inner"
    )
    declaration = next(item for item in index.declarations if item.member_name == "use")
    assert nested.accessibility == "PUBLIC"
    assert declaration.parameters[0].resolution.resolved_type == "p.Outer.Inner"


def test_locale_neutral_javac_note_payload_is_not_malformed_output():
    assert _NOTE.fullmatch("- compiler.note.deprecated.filename: UnsafeAccess.java")
    assert _NOTE.fullmatch("- compiler.note.unchecked.recompile")
    assert not _NOTE.fullmatch("unstructured compiler failure")


def test_diagnostic_binding_scopes_headers_bodies_fields_and_enclosing_type(
    tmp_path: Path,
):
    raw = (
        b"package p; @interface A { int[] value(); }\n"
        b"@A({1, 2}) public record R<T extends Number>(T value) {\n"
        b"  int field = missing;\n"
        b"  public R { value = missing; }\n"
        b"  public <E extends Throwable> void run(String... values) throws E { "
        b"missing(); }\n"
        b"  public void run(int value) {}\n"
        b"  class Nested { void nested() {} }\n"
        b"}\n"
    )
    _store, _bundle_value, index = _bundle(tmp_path, {"p/R.java": raw})

    def binding(token: bytes, offset: int = 0):
        byte = raw.index(token) + offset
        prefix = raw[:byte].decode()
        line = prefix.count("\n") + 1
        column = len(prefix.rsplit("\n", 1)[-1].encode("utf-16-le")) // 2 + 1
        diagnostic = _diagnostic("p/R.java", raw, line, column)
        return _bind_diagnostic(
            diagnostic,
            compilation_run_hash="3" * 64,
            source_index=index,
            raw_by_unit={"p/R.java": raw},
        )

    class_binding = binding(b"record R", len(b"record "))
    field_binding = binding(b"missing")
    compact_body_binding = binding(b"value = missing", len(b"value = "))
    method_header_binding = binding(b"run(String")
    method_body_binding = binding(b"missing();")
    nested_body_binding = binding(b"nested()")
    assert class_binding.diagnostic_scope is JavaDiagnosticScope.ENCLOSING_TYPE_BLOCKING
    assert field_binding.diagnostic_scope is JavaDiagnosticScope.UNRELATED_DECLARATION
    assert compact_body_binding.diagnostic_scope is JavaDiagnosticScope.BODY_ONLY
    assert (
        method_header_binding.diagnostic_scope
        is JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING
    )
    assert method_body_binding.diagnostic_scope is JavaDiagnosticScope.BODY_ONLY
    assert (
        nested_body_binding.diagnostic_scope
        is JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING
    )


def test_compiler_gate_is_declaration_scoped_and_fails_closed(tmp_path: Path):
    raw = b"package p; public class A { public void one() {} public void two() {} }\n"
    _store, _bundle_value, index = _bundle(tmp_path, {"p/A.java": raw})
    column = raw.index(b"one") + 1
    diagnostic = _diagnostic("p/A.java", raw, 1, column)
    binding = _bind_diagnostic(
        diagnostic,
        compilation_run_hash="3" * 64,
        source_index=index,
        raw_by_unit={"p/A.java": raw},
    )
    report = _report(index, (diagnostic,), (binding,))
    gate = build_java_compilation_trust_gate(report, index)
    assert gate.batch_blocked is False
    assert gate.blocked_declaration_count == 1

    unknown = replace(
        binding,
        declaration_ids=(),
        diagnostic_scope=JavaDiagnosticScope.UNKNOWN_SCOPE,
        binding_hash="",
    )
    unknown_body = asdict(unknown)
    unknown_body.pop("binding_hash")
    unknown = replace(unknown, binding_hash=content_hash(unknown_body))
    unknown_report = _report(index, (diagnostic,), (unknown,))
    assert (
        build_java_compilation_trust_gate(
            unknown_report, index
        ).blocked_declaration_count
        == 2
    )

    unbound_diagnostic = _diagnostic(None, raw, 1, 1)
    unbound_binding_body = {
        "compilation_run_hash": "3" * 64,
        "diagnostic_hash": unbound_diagnostic.diagnostic_hash,
        "source_entry_id": None,
        "source_unit_id": None,
        "source_unit_identity": None,
        "compiler_diagnostic_code": unbound_diagnostic.diagnostic_code,
        "normalized_category": unbound_diagnostic.normalized_category,
        "canonical_position": None,
        "canonical_byte_start": None,
        "canonical_byte_end": None,
        "declaration_ids": (),
        "diagnostic_scope": JavaDiagnosticScope.UNKNOWN_SCOPE,
        "enclosing_type_identity": None,
    }
    unbound_binding = DeclarationDiagnosticBinding(
        **unbound_binding_body,
        binding_hash=content_hash(unbound_binding_body),
    )
    unbound = _report(index, (unbound_diagnostic,), (unbound_binding,))
    assert build_java_compilation_trust_gate(unbound, index).batch_blocked
    malformed = _report(index, (), (), malformed=("5" * 64,))
    assert build_java_compilation_trust_gate(malformed, index).batch_blocked

    silent = replace(_report(index, (), ()), process_exit_code=2, report_hash="")
    silent_body = asdict(silent)
    silent_body.pop("report_hash")
    silent = replace(silent, report_hash=content_hash(silent_body))
    verify_java_production_compiler_report(silent)
    assert build_java_compilation_trust_gate(silent, index).batch_blocked

    missing_binding = replace(
        report,
        bindings=(),
        unknown_scope_count=0,
        unmapped_diagnostic_count=0,
        report_hash="",
    )
    missing_binding_body = asdict(missing_binding)
    missing_binding_body.pop("report_hash")
    missing_binding = replace(
        missing_binding, report_hash=content_hash(missing_binding_body)
    )
    with pytest.raises(ValueError, match="exactly one binding"):
        verify_java_production_compiler_report(missing_binding)


def test_internal_compilation_closure_counts_support_files(tmp_path: Path):
    sources = {
        "roota/p/A.java": b"package p; public class A extends B { public void a() {} }\n",
        "roota/p/B.java": b"package p; public class B {}\n",
        "roota/p/C.java": b"package p; public class C { public C() {} }\n",
    }
    _store, _bundle_value, index = _bundle(tmp_path, sources)
    report = _report(index, (), ())
    entry_ids = {unit: content_hash(unit) for unit in sources}
    manifest = build_java_compilation_closure_manifest(
        source_index=index,
        compiler_report=report,
        source_entry_ids=entry_ids,
    )
    by_unit = {item.source_unit_id: item for item in manifest.files}
    assert by_unit["roota/p/A.java"].closure_source_units == (
        "roota/p/A.java",
        "roota/p/B.java",
    )
    assert by_unit["roota/p/B.java"].supported_declaration_count == 0

    raw = sources["roota/p/A.java"]
    diagnostic = _diagnostic("roota/p/A.java", raw, 1, raw.index(b"A") + 1)
    binding = _bind_diagnostic(
        diagnostic,
        compilation_run_hash="3" * 64,
        source_index=index,
        raw_by_unit={"roota/p/A.java": raw},
    )
    assert binding.diagnostic_scope is JavaDiagnosticScope.ENCLOSING_TYPE_BLOCKING
    blocked_manifest = build_java_compilation_closure_manifest(
        source_index=index,
        compiler_report=_report(index, (diagnostic,), (binding,)),
        source_entry_ids=entry_ids,
    )
    blocked_a = next(
        item
        for item in blocked_manifest.files
        if item.source_unit_id == "roota/p/A.java"
    )
    assert blocked_a.enclosing_type_blocked_declaration_count == 1
    assert blocked_a.compiler_clean_supported_declaration_count == 0

    decisions = []
    source_bindings = []
    for unit in sources:
        family, _, path = unit.partition("/")
        source_id = build_source_entry_id(
            candidate_family_id=family,
            source_jar_sha256="6" * 64,
            archive_relative_path=path,
            raw_source_sha256="7" * 64,
            canonical_source_sha256="8" * 64,
        )
        closure = by_unit[unit]
        decisions.append(
            build_selectable_source_decision(
                source_entry_id=source_id,
                candidate_root=family,
                canonical_path=path,
                analysis_eligible=True,
                publication_allowed=True,
                source_use_receipt_valid=True,
                scoped_license_resolved=True,
                scm_correspondence_complete=True,
                parser_status="PASS",
                declaration_count=max(1, closure.supported_declaration_count),
                callable_declaration_count=closure.supported_declaration_count,
                supported_callable_declaration_count=closure.supported_declaration_count,
                construct_classes=("method",)
                if unit.endswith("A.java")
                else ("constructor",)
                if unit.endswith("C.java")
                else (),
                evidence_policy_path_declared=bool(closure.supported_declaration_count),
            )
        )
        source_bindings.append(
            build_source_entry_binding(
                source_entry_id=source_id,
                archive_path=path,
                scm_path=path,
                vault_path=f"candidates/{family}/sources/{path}",
                selected_path=unit,
                production_document_identity=unit,
            )
        )
    census = build_selectable_source_census(decisions)
    proof = prove_java_compilation_closure_feasibility(
        manifest,
        census,
        target_file_count=3,
        minimum_root_count=1,
        maximum_files_per_root=3,
        construct_quotas=(("constructor", 1), ("method", 1)),
        trust_capacity_target=2,
    )
    assert proof.hard_requirements_satisfied
    assert proof.witness_source_units == tuple(sorted(sources))
    selected, selector = select_compilation_closed_sources_once(
        census=census,
        closure_manifest=manifest,
        proof=proof,
        bindings=build_source_entry_binding_manifest(source_bindings),
        selector_seed="generic-test-seed",
        qualification_report_hash="7" * 64,
        qualification_summary_hash="8" * 64,
        ledger=M336FSelectorLedger(
            tmp_path / "selector-ledger.jsonl",
            git_worktrees=(Path(__file__).parents[1],),
        ),
    )
    verify_m336f_selection(selected, selector, proof)
    assert selected.qualification_report_hash == "7" * 64
    assert selector.qualification_summary_hash == "8" * 64
    tampered = replace(selected, root_count=selected.root_count + 1, manifest_hash="")
    tampered_body = asdict(tampered)
    tampered_body.pop("manifest_hash")
    tampered = replace(tampered, manifest_hash=content_hash(tampered_body))
    with pytest.raises(ValueError, match="selector invariants"):
        verify_m336f_selection(tampered, selector, proof)
    rebound = replace(selector, qualification_report_hash="9" * 64, receipt_hash="")
    rebound_body = asdict(rebound)
    rebound_body.pop("receipt_hash")
    rebound = replace(rebound, receipt_hash=content_hash(rebound_body))
    with pytest.raises(ValueError, match="selector invariants"):
        verify_m336f_selection(selected, rebound, proof)
    widened = replace(selector, evaluator_read_count=1, receipt_hash="")
    widened_body = asdict(widened)
    widened_body.pop("receipt_hash")
    widened = replace(widened, receipt_hash=content_hash(widened_body))
    with pytest.raises(ValueError, match="selector invariants"):
        verify_m336f_selection(selected, widened, proof)
    infeasible = prove_java_compilation_closure_feasibility(
        manifest,
        census,
        target_file_count=3,
        minimum_root_count=1,
        maximum_files_per_root=1,
        construct_quotas=(),
        trust_capacity_target=1,
    )
    assert not infeasible.hard_requirements_satisfied
    assert "TARGET_FILE_COUNT" in infeasible.failure_reasons


def test_method_generic_evidence_uses_callable_owner(tmp_path: Path):
    raw = (
        b"package p; public interface Base<C extends Base<C>> { "
        b"public <F extends Throwable> C call(Class<F> failure); }\n"
    )
    store, bundle, _index = _bundle(tmp_path, {"p/Base.java": raw})
    batch = run_java_acquisition_pipeline(
        bundle,
        store,
        deterministic_run_id="m336f-field-regression",
    )
    requirements = enumerate_java_evidence_requirements(
        batch.proposal_batch,
        batch.source_index,
        batch.evidence_policy,
    )
    expected = {
        (item.proposal_id, item.field_path): item.expected_output
        for item in requirements
    }
    row = next(
        item
        for item in batch.field_evidence.evidence
        if item.field_path == "content.generic_constraints[0]"
    )
    assert row.normalized_output == '"F extends Throwable"'
    assert row.normalized_output == expected[(row.proposal_id, row.field_path)]
    assert batch.field_evidence.wrong_count == 0


def test_callable_generic_ownership_is_stable_for_nested_and_neighboring_members(
    tmp_path: Path,
):
    raw = (
        b"package p; public class Outer<T> { class Inner<U extends Number> { "
        b"public <V extends CharSequence & Comparable<V>> V map(V value) { "
        b"return value; } public <X> Inner() {} public void plain() {} } }\n"
    )
    store, bundle, _index = _bundle(tmp_path / "original", {"p/Outer.java": raw})
    batch = run_java_acquisition_pipeline(
        bundle,
        store,
        deterministic_run_id="m336f-nested-generic-owner",
    )
    by_predicate = {
        item.proposed_content.predicate_id: item.proposed_content
        for item in batch.proposal_batch.proposals
    }
    assert by_predicate["map"].method_type_parameters == ("V",)
    assert by_predicate["map"].generic_constraints == (
        "V extends CharSequence & Comparable<V>",
    )
    assert by_predicate["<init>"].method_type_parameters == ("X",)
    assert by_predicate["<init>"].generic_constraints == ()
    assert by_predicate["plain"].method_type_parameters == ()

    changed = raw.replace(b"V extends CharSequence", b"V extends Number")
    changed_store, changed_bundle, _changed_index = _bundle(
        tmp_path / "changed", {"p/Outer.java": changed}
    )
    changed_batch = run_java_acquisition_pipeline(
        changed_bundle,
        changed_store,
        deterministic_run_id="m336f-nested-generic-owner",
    )
    changed_map = next(
        item.proposed_content
        for item in changed_batch.proposal_batch.proposals
        if item.proposed_content.predicate_id == "map"
    )
    assert changed_map.generic_constraints == ("V extends Number & Comparable<V>",)
    assert changed_map.generic_constraints != by_predicate["map"].generic_constraints


def test_semantic_artifact_is_host_neutral_and_telemetry_is_explicit():
    semantic = build_m336f_semantic_evaluation_artifact(
        identities={"production": "prod-v1"},
        counts={"wrong_trusted": 0},
        ratios={"safe_trust_coverage": "0.875000"},
        decisions={"outcome": "PASS"},
        hashes={"threshold_manifest": "9" * 64},
        normalized_diagnostic_categories={"UNRESOLVED_TYPE": 2},
        mismatch_manifest_hashes={"field_evidence": "a" * 64},
        readiness_result="PASS",
    )
    assert semantic_artifacts_byte_identical(semantic, semantic)
    windows = build_m336f_evaluation_telemetry_receipt(
        platform="windows",
        host_identity_hash="b" * 64,
        operation_timings_seconds={"compiler": "0.500000"},
        peak_memory_bytes=10,
        jdk_executable_hash="c" * 64,
        process_measurements={"compiler_invocations": 1},
    )
    karina = build_m336f_evaluation_telemetry_receipt(
        platform="karina",
        host_identity_hash="d" * 64,
        operation_timings_seconds={"compiler": "0.250000"},
        peak_memory_bytes=20,
        jdk_executable_hash="c" * 64,
        process_measurements={"compiler_invocations": 1},
    )
    assert windows.receipt_hash != karina.receipt_hash
    with pytest.raises(ValueError, match="platform-neutral"):
        build_m336f_semantic_evaluation_artifact(
            identities={"host": "windows"},
            counts={},
            ratios={},
            decisions={},
            hashes={},
            normalized_diagnostic_categories={},
            mismatch_manifest_hashes={},
            readiness_result="PASS",
        )
    with pytest.raises(ValueError, match="platform-neutral"):
        build_m336f_semantic_evaluation_artifact(
            identities={},
            counts={},
            ratios={"impossible_ratio": "1.000001"},
            decisions={},
            hashes={},
            normalized_diagnostic_categories={},
            mismatch_manifest_hashes={},
            readiness_result="FAIL",
        )
    with pytest.raises(ValueError, match="telemetry"):
        build_m336f_evaluation_telemetry_receipt(
            platform="windows",
            host_identity_hash="b" * 64,
            operation_timings_seconds={"compiler": "NaN"},
            peak_memory_bytes=10,
            jdk_executable_hash="c" * 64,
            process_measurements={"compiler_invocations": 1},
        )


def test_license_evaluation_splits_semantics_from_host_telemetry():
    def row(document_identity: str):
        body = {
            "document_identity": document_identity,
            "agreement": True,
        }
        return {**body, "row_hash": content_hash(body)}

    mixed = {
        "schema_version": 1,
        "document_count": 2,
        "production_reference_agreement": "1.000000",
        "disagreement_count": 0,
        "disagreement_review_required_count": 0,
        "false_automatic_license_identity_count": 0,
        "selected_root_unresolved_disagreement_count": 0,
        "java_reference_spdx_match_seconds": "0.25",
        "production_spdx_match_seconds": "0.01",
        "java_reference_compilation_seconds": "0.5",
        "peak_java_reference_bytes": 1024,
        "rows": (row("legal/one"), row("legal/two")),
        "status": "PASS",
        "report_hash": "3" * 64,
    }
    split = split_m336f_license_evaluation(mixed)
    assert split.semantic["production_reference_agreement"] == "1.000000"
    assert split.semantic["status"] == "PASS"
    assert "java_reference_spdx_match_seconds" not in split.semantic
    assert dict(split.telemetry_timings_seconds) == {
        "license_production_evaluation": "0.01",
        "license_reference_compilation": "0.5",
        "license_reference_evaluation": "0.25",
    }
    changed = split_m336f_license_evaluation(
        {**mixed, "java_reference_spdx_match_seconds": "99.0"}
    )
    assert split.semantic == changed.semantic
    assert split.telemetry_timings_seconds != changed.telemetry_timings_seconds


def test_m336f_producer_contract_gate_covers_every_new_variant():
    legacy = json.loads(
        Path("evaluation/m336d_final_java/h19/acquisition_receipts.json").read_text(
            encoding="utf-8"
        )
    )
    report = run_m336f_producer_contract_gate(legacy)
    assert report.status == "PASS"
    assert report.public_producer_count == report.covered_producer_count == 14
    assert report.declared_producer_variant_count == 41
    assert report.tested_producer_variant_count == 41
    assert report.uncontracted_produced_artifact_count == 0
    assert report.contract_type_without_producer_or_legacy_count == 0
    assert report.ambiguous_path_contract_count == 0
    assert len(M336F_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.contracts) == 14


def test_forensic_context_classification_is_identity_agnostic():
    present = CompilationContextObservation(True, "code", "HEADER", "a" * 64)
    absent = CompilationContextObservation(False, None, None, "a" * 64)
    assert (
        classify_compilation_contexts(
            current=present,
            selected_plus_internal=absent,
            all_same_root=absent,
            frozen_classpath=present,
        )
        == "MISSING_SELECTED_INTERNAL_TYPE"
    )
    assert (
        classify_compilation_contexts(
            current=replace(present, source_unit_binding_valid=False),
            selected_plus_internal=absent,
            all_same_root=absent,
            frozen_classpath=present,
        )
        == "DIAGNOSTIC_LOCATION_MAPPING_ERROR"
    )


def test_production_policy_has_no_source_identity_exception():
    root = Path(__file__).parents[1] / "src/ai_brain/stage3/acquisition"
    text = "\n".join(
        (root / name).read_text(encoding="utf-8").casefold()
        for name in (
            "java_production.py",
            "java_production_compiler.py",
            "m336f_compilation_closure.py",
        )
    )
    for source_identifier in (
        "errorprone-annotations",
        "failsafe",
        "jctools-core",
        "jetbrains-annotations",
        "modelmapper",
    ):
        assert source_identifier not in text
    forensic = json.loads(
        (
            Path(__file__).parents[1]
            / "artifacts/m336f/r20_wrong_trusted_forensics.json"
        ).read_text(encoding="utf-8")
    )
    for row in forensic["rows"]:
        assert row["production_proposal_id"].casefold() not in text


def test_public_r20_forensic_artifacts_are_sealed_and_source_safe():
    root = Path(__file__).parents[1] / "artifacts/m336f"
    names = (
        "r20_wrong_trusted_forensics.json",
        "r20_trust_confusion_counts.json",
        "r20_field_evidence_mismatches.json",
        "r20_platform_artifact_differences.json",
    )
    values = [json.loads((root / name).read_text(encoding="utf-8")) for name in names]
    for value in values:
        body = dict(value)
        claimed = body.pop("report_hash")
        assert content_hash(body) == claimed
    for row in values[0]["rows"]:
        body = dict(row)
        claimed = body.pop("forensic_row_hash")
        assert content_hash(body) == claimed
    for row in values[2]["rows"]:
        body = dict(row)
        claimed = body.pop("forensic_row_hash")
        assert content_hash(body) == claimed
    for row in values[3]["rows"]:
        body = dict(row)
        claimed = body.pop("difference_hash")
        assert content_hash(body) == claimed
    raw = "".join((root / name).read_text(encoding="utf-8") for name in names)
    assert not re.search(r"[A-Za-z]:[\\/]|/tmp/|AppData|\\Users\\", raw)
    assert all(token not in raw for token in ("public class ", "package ", "import "))
