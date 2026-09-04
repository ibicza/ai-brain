from __future__ import annotations

import json
import socket
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    frozen_tree_snapshot,
    verify_java_freeze_protocol,
)
from ai_brain.stage3.acquisition.java_pipeline import _golden_exact
from ai_brain.stage3.acquisition.java_pre_freeze_gate import (
    _SPECS,
    PreFreezeDecision,
    evaluate_pre_freeze_gate,
    load_pre_freeze_gate_report,
    run_full_gate_meta_mutations,
    verify_pre_freeze_gate_report,
)
from ai_brain.stage3.acquisition.java_process_audit import (
    EnforcedProcessAudit,
    exact_subprocess_policy,
)
from ai_brain.stage3.acquisition.java_seal import (
    load_external_java_trust_evaluation_config,
)
from ai_brain.stage3.acquisition.java_semantics import (
    build_java_claim_content,
    canonical_semantic_payload,
    java_value_type,
    proposal_field_manifest_hash,
    semantic_content_confusion,
    semantic_content_hash,
    type_resolution_semantic_manifest_hash,
)
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.knowledge_ir.records import (
    EpistemicCharacter,
    KnowledgeKind,
    ValueTypeKind,
)

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "tests/fixtures/m343_java/oracle"
CORPUS = ROOT / "tests/fixtures/m343_java/corpus"


@pytest.fixture(scope="module")
def m343_index(tmp_path_factory):
    store = AcquisitionStore.open_or_initialize(
        tmp_path_factory.mktemp("m343-index") / "store"
    )
    paths = tuple(
        sorted(
            CORPUS.rglob("*.java"), key=lambda item: item.relative_to(CORPUS).as_posix()
        )
    )
    bundle = ingest_bundle(
        paths,
        bundle_id="m343-targeted",
        imported_at="2026-09-03T00:00:00Z",
        store=store,
        source_root=CORPUS,
    )
    return bundle, index_java_bundle(bundle, store)


def _passing_raw():
    result = {}
    for _identifier, key, operator, threshold in _SPECS:
        if operator == "BOOL":
            result[key] = threshold == "true"
        elif "." in threshold:
            result[key] = {
                "numerator": 1 if operator == "MIN" else 0,
                "denominator": 1,
            }
        else:
            result[key] = int(threshold)
    return result


def _declaration(**changes):
    values = {
        "member_kind": "method",
        "member_name": "value",
        "receiver_type": "demo.Sample",
        "return_type": "void",
        "resolved_return_type": "void",
        "return_resolution": SimpleNamespace(array_dimensions=0),
        "type_variables_detail": (),
        "parameters": (),
        "declared_exceptions": (),
        "resolved_declared_exceptions": (),
        "deprecated_since": None,
        "modifiers": ("public",),
        "accessibility": "PUBLIC",
        "enclosing_type_accessibility": "PUBLIC",
        "module_name": None,
        "package_exported": True,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_gate_is_derived_replay_verified_and_all_17_mutations_block(tmp_path):
    raw = _passing_raw()
    report = evaluate_pre_freeze_gate(raw)
    assert report.decision is PreFreezeDecision.READY_FOR_FRESH_FREEZE
    mutations = run_full_gate_meta_mutations(raw)
    assert len(mutations) == 17
    assert all(item.decision is PreFreezeDecision.BLOCKED for _name, item in mutations)

    path = tmp_path / "gate.json"
    path.write_text(
        canonical_json({"raw_evidence": raw, "gate": asdict(report)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    loaded_raw, loaded = load_pre_freeze_gate_report(path)
    assert loaded_raw == raw and loaded == report
    json_round_trip = json.loads(canonical_json(asdict(report)))
    assert content_hash(json_round_trip) == content_hash(
        asdict(evaluate_pre_freeze_gate(raw))
    )
    forged = replace(report, fail_count=1)
    with pytest.raises(ValueError, match="altered"):
        verify_pre_freeze_gate_report(forged, raw)


def test_na_ratio_fails_a_mandatory_gate_criterion():
    raw = _passing_raw()
    raw["semantic_precision"] = {"numerator": 0, "denominator": 0}
    report = evaluate_pre_freeze_gate(raw)
    criterion = next(
        item for item in report.criteria if item.criterion_id == "semantic.precision"
    )
    assert criterion.measured_value == "N/A"
    assert criterion.measured_numerator == 0
    assert criterion.measured_denominator == 0
    assert criterion.status == "FAIL"
    assert report.decision is PreFreezeDecision.BLOCKED


def test_mixed_corpus_has_separately_measured_real_openjdk_sources():
    corpus = json.loads((ORACLE / "corpus_manifest.json").read_text(encoding="utf-8"))
    provenance = json.loads(
        (CORPUS / "OPENJDK_PROVENANCE.json").read_text(encoding="utf-8")
    )
    real_sources = tuple((CORPUS / "real" / "openjdk-25").rglob("*.java"))
    assert corpus["real_source_file_count"] == len(real_sources) == 50
    assert corpus["synthetic_source_file_count"] == 55
    assert provenance["real_source_count"] == 50
    assert provenance["archive_sha256"] == (
        "658d6fe751ad9fc23d40a129654e2b26931209babf5ff7802273f3c468674e52"
    )
    real_root = CORPUS / "real" / "openjdk-25"
    assert len({path.relative_to(real_root).parts[0] for path in real_sources}) >= 3


@pytest.mark.parametrize(
    ("source", "resolved", "kind"),
    (
        ("void", "void", ValueTypeKind.VOID),
        ("boolean", "boolean", ValueTypeKind.BOOLEAN),
        ("char", "char", ValueTypeKind.INTEGER),
        ("long", "long", ValueTypeKind.INTEGER),
        ("float", "float", ValueTypeKind.DECIMAL),
        ("double", "double", ValueTypeKind.DECIMAL),
        ("String", "java.lang.String", ValueTypeKind.STRING),
        ("Object", "java.lang.Object", ValueTypeKind.ENTITY),
        ("String[][]", "java.lang.String[][]", ValueTypeKind.ENTITY),
        ("T", "java.lang.Number", ValueTypeKind.ENTITY),
        ("List<? extends Number>", "java.util.List", ValueTypeKind.ENTITY),
    ),
)
def test_java_value_mapping_preserves_semantic_distinctions(source, resolved, kind):
    value = java_value_type(source, resolved)
    assert value.kind is kind
    if kind is ValueTypeKind.ENTITY:
        assert value.entity_type.entity_type_id == resolved


def test_constructor_is_explicit_entity_semantic():
    content = build_java_claim_content(
        _declaration(
            member_kind="constructor",
            return_type="void",
            resolved_return_type="void",
        )
    )
    assert content.java_callable_kind == "CONSTRUCTOR"
    assert content.predicate_id == "<init>"
    assert content.object_type.kind is ValueTypeKind.ENTITY
    assert content.object_type.entity_type.entity_type_id == "demo.Sample"


def test_same_erasure_semantic_mutations_have_distinct_hashes():
    list_string = build_java_claim_content(
        _declaration(return_type="List<String>", resolved_return_type="java.util.List")
    )
    list_integer = build_java_claim_content(
        _declaration(return_type="List<Integer>", resolved_return_type="java.util.List")
    )
    map_left = build_java_claim_content(
        _declaration(
            return_type="Map<String,Integer>", resolved_return_type="java.util.Map"
        )
    )
    map_right = build_java_claim_content(
        _declaration(
            return_type="Map<Integer,String>", resolved_return_type="java.util.Map"
        )
    )
    assert semantic_content_hash(list_string) != semantic_content_hash(list_integer)
    assert semantic_content_hash(map_left) != semantic_content_hash(map_right)


def test_parameter_name_throws_and_second_bound_are_semantic():
    resolution = SimpleNamespace(array_dimensions=0)
    parameter = lambda name: SimpleNamespace(
        name=name,
        source_type="int",
        resolved_type="int",
        resolution=resolution,
        varargs=False,
    )
    type_variable = lambda bounds: SimpleNamespace(
        name="T",
        bounds=bounds,
        explicit_bounds=True,
        first_bound_erasure="java.lang.Number",
    )
    base = _declaration(
        parameters=(parameter("value"),),
        declared_exceptions=("IOException",),
        resolved_declared_exceptions=("java.io.IOException",),
        type_variables_detail=(type_variable(("Number", "Comparable<T>")),),
    )
    values = (
        _declaration(**{**base.__dict__, "parameters": (parameter("other"),)}),
        _declaration(
            **{
                **base.__dict__,
                "declared_exceptions": ("SQLException",),
                "resolved_declared_exceptions": ("java.sql.SQLException",),
            }
        ),
        _declaration(
            **{
                **base.__dict__,
                "type_variables_detail": (type_variable(("Number",)),),
            }
        ),
    )
    original = semantic_content_hash(build_java_claim_content(base))
    assert all(
        semantic_content_hash(build_java_claim_content(item)) != original
        for item in values
    )


def test_correct_location_wrong_object_type_is_semantic_false_positive():
    declaration = _declaration(
        node_id="node",
        source_snapshot_hash="a" * 64,
        source_unit_id="src/Sample.java",
        declaration_span=SimpleNamespace(byte_start=1, byte_end=4),
        canonical_source_signature="value():int",
        erased_jvm_descriptor="value()I",
        supported=True,
        unsupported_reason=None,
        type_occurrence_resolutions=(),
    )
    correct = build_java_claim_content(
        _declaration(return_type="int", resolved_return_type="int")
    )
    wrong = build_java_claim_content(
        _declaration(return_type="String", resolved_return_type="java.lang.String")
    )
    semantics = SimpleNamespace(
        expected_claim_payload=canonical_semantic_payload(correct),
        expected_knowledge_kind="CLAIM_SCHEMA",
        expected_epistemic_character="NORMATIVE",
        expected_supported=True,
        expected_blocker_reason=None,
        complete_type_resolution_manifest_hash=type_resolution_semantic_manifest_hash(
            declaration
        ),
        complete_proposal_field_manifest_hash=proposal_field_manifest_hash(correct),
    )
    golden = SimpleNamespace(
        golden_id="golden",
        document_bytes_hash=declaration.source_snapshot_hash,
        source_unit_id=declaration.source_unit_id,
        start_offset=1,
        end_offset=4,
        expected_semantics=semantics,
        canonical_source_signature=declaration.canonical_source_signature,
        erased_jvm_descriptor=declaration.erased_jvm_descriptor,
    )
    proposal = SimpleNamespace(
        proposal_id="proposal",
        proposed_content=wrong,
        proposed_kind=KnowledgeKind.CLAIM_SCHEMA,
        proposed_epistemic_character=EpistemicCharacter.NORMATIVE,
    )
    batch = SimpleNamespace(
        proposals=(proposal,),
        bindings=(SimpleNamespace(proposal_id="proposal", parser_node_id="node"),),
    )
    matrix = semantic_content_confusion(
        SimpleNamespace(goldens=(golden,)),
        batch,
        SimpleNamespace(declarations=(declaration,)),
    )
    assert matrix.correct_location_wrong_content == 1
    assert matrix.semantic_false_positive == 1
    assert matrix.exact_true_positive == 0


def test_canonical_signature_change_is_rejected_even_when_descriptor_is_same():
    declaration = _declaration(
        source_snapshot_hash="b" * 64,
        source_unit_id="src/Sample.java",
        declaration_span=SimpleNamespace(
            byte_start=2, byte_end=8, line_start=1, line_end=1
        ),
        package_name="demo",
        top_level_type_name="Sample",
        nested_type_path=(),
        member_name="value",
        canonical_source_signature="value(int):int",
        erased_jvm_descriptor="value(I)I",
        supported=True,
        unsupported_reason=None,
        type_occurrence_resolutions=(),
    )
    content = build_java_claim_content(
        _declaration(return_type="int", resolved_return_type="int")
    )
    semantics = SimpleNamespace(
        expected_supported=True,
        expected_claim_payload=canonical_semantic_payload(content),
        expected_semantic_content_hash=semantic_content_hash(content),
        complete_type_resolution_manifest_hash=type_resolution_semantic_manifest_hash(
            declaration
        ),
        complete_proposal_field_manifest_hash=proposal_field_manifest_hash(content),
    )
    golden = SimpleNamespace(
        document_bytes_hash=declaration.source_snapshot_hash,
        start_offset=2,
        end_offset=8,
        start_line=1,
        end_line=1,
        package_name="demo",
        top_level_type_name="Sample",
        nested_type_path=(),
        member_kind="method",
        member_name="value",
        canonical_source_signature="value(other.Type):int",
        erased_jvm_descriptor=declaration.erased_jvm_descriptor,
        expected_supported=True,
        expected_semantics=semantics,
    )
    location, semantic = _golden_exact(
        declaration, golden, SimpleNamespace(proposed_content=content)
    )
    assert location is True
    assert semantic is False


def test_process_allowlist_is_exact_and_network_is_blocked():
    command = (str(Path(sys.executable).resolve()), "-c", "pass")
    policy = exact_subprocess_policy("python-pass", command, purpose="TEST")
    with EnforcedProcessAudit((policy,)) as audit:
        subprocess.run(command, check=True)
        with pytest.raises(PermissionError, match="allowlist"):
            subprocess.run((command[0], "-c", "print('unexpected')"), check=True)
        with pytest.raises(PermissionError, match="network"):
            socket.socket()
        report = audit.report()
    assert report.subprocess_invocation_count == 1
    assert report.unexpected_subprocess_count == 1
    assert report.socket_attempts == 1


def test_external_config_needs_both_bytes_hash_and_authority_root():
    config_path = ORACLE / "evaluation_config.json"
    authority = json.loads((ORACLE / "authority_root.json").read_text())[
        "authority_root_hash"
    ]
    config = load_external_java_trust_evaluation_config(
        config_path,
        expected_config_sha256=bytes_hash(config_path.read_bytes()),
        authority_root_hash=authority,
    )
    assert config.authority_root_hash == authority
    with pytest.raises(ValueError, match="unauthorized"):
        load_external_java_trust_evaluation_config(
            config_path,
            expected_config_sha256="0" * 64,
            authority_root_hash=authority,
        )
    with pytest.raises(ValueError, match="authority root"):
        load_external_java_trust_evaluation_config(
            config_path,
            expected_config_sha256=bytes_hash(config_path.read_bytes()),
            authority_root_hash="0" * 64,
        )


def test_future_f13_h13_e13_protocol_is_path_and_hash_closed():
    f13 = frozen_tree_snapshot("F13", "1" * 40, {"src/product.py": "a" * 64})
    h13 = frozen_tree_snapshot(
        "H13",
        "2" * 40,
        {
            "src/product.py": "a" * 64,
            "sealed/input.json": "b" * 64,
        },
    )
    e13 = frozen_tree_snapshot(
        "E13",
        "3" * 40,
        {
            "src/product.py": "a" * 64,
            "sealed/input.json": "b" * 64,
            "evidence/report.json": "c" * 64,
        },
    )
    report = verify_java_freeze_protocol(
        f13,
        h13,
        e13,
        evaluation_input_prefixes=("sealed/",),
        evidence_prefixes=("evidence/",),
    )
    assert report.passed
    changed = frozen_tree_snapshot(
        "E13",
        "4" * 40,
        {
            "src/product.py": "d" * 64,
            "sealed/input.json": "b" * 64,
        },
    )
    assert not verify_java_freeze_protocol(
        f13,
        h13,
        changed,
        evaluation_input_prefixes=("sealed/",),
        evidence_prefixes=("evidence/",),
    ).passed


def test_complete_resolver_withholds_all_adversarial_type_classes(m343_index):
    _bundle, index = m343_index
    by_prefix = {
        prefix: [
            item for item in index.declarations if item.member_name.startswith(prefix)
        ]
        for prefix in (
            "invalidBound",
            "invalidThrows",
            "inaccessible",
            "privateNested",
            "nonExported",
            "localFqn",
            "staticImport",
        )
    }
    assert all(len(values) >= 20 for values in by_prefix.values())
    assert all(not item.supported for values in by_prefix.values() for item in values)
    assert all(
        detail.first_bound_erasure != "java.lang.Object"
        for item in by_prefix["invalidBound"]
        for detail in item.type_variables_detail
        if detail.explicit_bounds
    )
    assert all(
        item.declared_exceptions and item.resolved_declared_exceptions == (None,)
        for item in by_prefix["invalidThrows"]
    )
    assert all(
        "java.util.Collections.emptyList" in item.static_imports
        and all("emptyList" not in value for value in item.imports)
        for item in by_prefix["staticImport"]
    )


def test_intersection_varargs_deprecation_and_cr_lines_are_preserved(m343_index):
    _bundle, index = m343_index
    intersection = next(
        item for item in index.declarations if item.member_name == "intersection"
    )
    assert intersection.type_variables_detail[0].bounds == (
        "Number",
        "Comparable<T>",
    )
    assert len(intersection.type_variables_detail[0].resolution_receipt_hashes) == 2
    varargs = next(
        item for item in index.declarations if item.member_name == "arrayValue"
    )
    assert varargs.parameters[0].varargs
    assert varargs.parameters[0].resolution.array_dimensions == 2
    assert varargs.return_resolution.array_dimensions == 2
    deprecated = next(
        item for item in index.declarations if item.member_name == "legacyValue"
    )
    assert deprecated.deprecated_since == "21"
    assert deprecated.deprecation_span is not None
    cr_only = [
        item
        for item in index.declarations
        if item.source_unit_id.endswith("NegativeCatalog24.java")
    ]
    assert len({item.declaration_span.line_start for item in cr_only}) == len(cr_only)


def test_source_ids_retain_full_paths_for_duplicate_basenames(m343_index):
    bundle, _index = m343_index
    service_paths = sorted(
        item.relative_path
        for item in bundle.documents
        if Path(item.relative_path).name == "Service.java"
    )
    assert service_paths == [
        "synthetic/library-1/shared/Service.java",
        "synthetic/library-2/shared/Service.java",
    ]


def test_m343_scripts_do_not_assign_a_literal_ready_decision():
    for path in (ROOT / "scripts").glob("m343*.py"):
        text = path.read_text(encoding="utf-8")
        assert 'decision = "READY_FOR_FRESH_FREEZE"' not in text
        assert "decision='READY_FOR_FRESH_FREEZE'" not in text
