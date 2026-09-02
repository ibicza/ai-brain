"""M-34.2 supersedes the common-mode M-34.1 Java integration evaluator."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.java_evidence import (
    build_java_field_evidence_manifest,
)
from ai_brain.stage3.acquisition.java_goldens import (
    load_java_golden_manifest,
)
from ai_brain.stage3.acquisition.java_metrics import (
    automatic_trust_confusion,
    binary_confusion,
    evidence_confusion,
    safe_abstention,
    set_detection_confusion,
    source_location_confusion,
)
from ai_brain.stage3.acquisition.java_pipeline import (
    bind_java_trust,
    run_java_trust_pipeline,
    verify_trust_bound_batch,
)
from ai_brain.stage3.acquisition.java_replay import (
    JAVA_REPLAY_FILENAME,
    verify_compiled_java_evidence_standalone,
)
from ai_brain.stage3.acquisition.java_seal import (
    load_golden_seal_receipt,
    load_java_trust_evaluation_config,
    verify_golden_seal_receipt,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/m342_java/corpus"
ORACLE = ROOT / "tests/fixtures/m342_java/oracle"
STAMP = "2026-09-02T00:00:00Z"


@pytest.fixture(scope="module")
def java_closure(tmp_path_factory):
    root = tmp_path_factory.mktemp("m342-closure")
    store = AcquisitionStore.open_or_initialize(root / "store")
    paths = tuple(sorted(CORPUS.rglob("*.java"), key=lambda item: item.name))
    bundle = ingest_bundle(paths, bundle_id="m342-dev", imported_at=STAMP, store=store)
    goldens = load_java_golden_manifest(ORACLE / "semantic_goldens.json")
    seal = load_golden_seal_receipt(ORACLE / "golden_seal_receipt.json")
    config = load_java_trust_evaluation_config()
    batch = run_java_trust_pipeline(
        bundle,
        store,
        goldens,
        seal,
        config,
        deterministic_run_id="m342.pytest.v1",
    )
    authorizations = verify_trust_bound_batch(
        batch, store, seal, batch.parser_common_artifact
    )
    return root, store, batch, authorizations


def test_compiler_oracle_and_resolver_agree_on_all_600_targets(java_closure):
    _root, _store, batch, authorizations = java_closure
    assert (
        batch.golden_manifest.positive_count,
        batch.golden_manifest.negative_count,
    ) == (
        300,
        300,
    )
    assert batch.golden_manifest.semantic_negative_count == 300
    assert (batch.trusted_count, batch.withheld_count, len(authorizations)) == (
        300,
        300,
        300,
    )
    assert batch.blocker_counts == (
        ("untrusted_ambiguous_parameter_type:Value", 60),
        ("untrusted_unresolved_parameter_type:AbsentType", 60),
        ("untrusted_unresolved_parameter_type:Imported", 60),
        ("untrusted_unresolved_parameter_type:Widget", 60),
        ("untrusted_unresolved_parameter_type:missing.pkg.Type", 60),
    )
    assert batch.source_index.type_universe.symbol_count == 5002
    assert all(
        item.type_universe_manifest_hash
        == batch.source_index.type_universe_manifest_hash
        for item in batch.source_index.declarations
    )


def test_varargs_arrays_nested_and_generic_erasure_match_javac(java_closure):
    _root, _store, batch, _authorizations = java_closure
    declarations = {
        item.member_name: item
        for item in batch.source_index.declarations
        if item.member_kind == "method"
    }
    assert declarations["p004"].erased_jvm_descriptor.endswith(
        "([Ljava/lang/String;)[Ljava/lang/String;"
    )
    assert declarations["p005"].erased_jvm_descriptor.endswith(
        "([Ljava/lang/String;)[Ljava/lang/String;"
    )
    assert declarations["p007"].erased_jvm_descriptor.endswith(
        "([[Ljava/lang/Number;)[[Ljava/lang/Number;"
    )
    assert "Map$Entry" in declarations["p002"].erased_jvm_descriptor
    assert "PositiveCorpus$Nested" in declarations["p003"].erased_jvm_descriptor


def test_evidence_denominator_precedes_generation_and_constructor_void_is_required(
    java_closure,
):
    _root, store, batch, _authorizations = java_closure
    matrix = evidence_confusion(batch.field_evidence)
    assert (
        matrix.required,
        matrix.present,
        matrix.exact,
        matrix.missing,
        matrix.extra,
        matrix.duplicate,
        matrix.wrong,
    ) == (12598, 12598, 12598, 0, 0, 0, 0)
    constructor = next(
        item
        for item in batch.trusted_proposals
        if item.proposed_content.predicate_id == "<init>"
    )
    constructor_evidence = tuple(
        item
        for item in batch.field_evidence.evidence
        if item.proposal_id == constructor.proposal_id
        and item.field_path == "content.return_type"
    )
    assert len(constructor_evidence) == 1
    assert constructor_evidence[0].transformation_id == "constructor-void-return"
    mutated = build_java_field_evidence_manifest(
        batch.proposal_batch,
        batch.source_index,
        batch.bundle,
        store,
        policy=batch.evidence_policy,
        omit_fields=("content.return_type",),
    )
    assert mutated.required_field_count == 12598
    assert mutated.missing_count == 600
    rebound = bind_java_trust(
        batch.bundle,
        batch.segmentation,
        batch.source_index,
        batch.proposal_batch,
        mutated,
        batch.evidence_policy,
        batch.golden_manifest,
        batch.golden_seal,
        batch.evaluation_config,
        batch.parser_common_artifact,
        batch.parser_platform_artifact,
        deterministic_run_id="m342.pytest.missing-evidence",
    )
    assert rebound.trusted_count == 0


def test_external_seal_and_review_capabilities_reject_rehashed_forgery(java_closure):
    _root, _store, batch, authorizations = java_closure
    golden = batch.golden_manifest.goldens[0]
    altered = replace(golden, member_name="forged", golden_hash="")
    altered = replace(
        altered,
        golden_hash=content_hash(
            {
                key: value
                for key, value in asdict(altered).items()
                if key != "golden_hash"
            }
        ),
    )
    forged_manifest = replace(
        batch.golden_manifest,
        goldens=(altered, *batch.golden_manifest.goldens[1:]),
        manifest_hash="",
    )
    forged_manifest = replace(
        forged_manifest,
        manifest_hash=content_hash(
            {
                key: value
                for key, value in asdict(forged_manifest).items()
                if key != "manifest_hash"
            }
        ),
    )
    with pytest.raises(ValueError, match="golden seal"):
        verify_golden_seal_receipt(
            batch.golden_seal, forged_manifest, batch.evaluation_config
        )
    trusted = batch.trusted_proposals[0]
    authentic = next(
        item
        for item in authorizations
        if item.trusted_proposal_id == trusted.proposal_id
    )
    review_proposal(
        trusted,
        reviewer_identity="m342-human",
        reviewer_type=ActorIdentityType.USER,
        decision=ReviewDecision.APPROVE,
        rationale="authentic capability",
        timestamp=STAMP,
        trust_authorization=authentic,
    )
    forged = replace(authentic, authorization_hash="0" * 64)
    with pytest.raises(ValueError, match="authorization hash"):
        review_proposal(
            trusted,
            reviewer_identity="m342-human",
            reviewer_type=ActorIdentityType.USER,
            decision=ReviewDecision.APPROVE,
            rationale="forged capability",
            timestamp=STAMP,
            trust_authorization=forged,
        )
    copied = replace(authentic)
    with pytest.raises(ValueError, match="outside authoritative"):
        review_proposal(
            trusted,
            reviewer_identity="m342-human",
            reviewer_type=ActorIdentityType.USER,
            decision=ReviewDecision.APPROVE,
            rationale="copied capability",
            timestamp=STAMP,
            trust_authorization=copied,
        )


def test_all_metrics_are_derived_from_raw_sets(java_closure):
    _root, _store, batch, _authorizations = java_closure
    targets = {item.golden_id: item for item in batch.golden_manifest.goldens}
    expected = set(targets)
    extracted = set(targets)
    proposal = binary_confusion(expected, extracted, expected)
    assert (
        proposal.true_positive,
        proposal.false_positive,
        proposal.false_negative,
    ) == (
        600,
        0,
        0,
    )
    assert (proposal.precision, proposal.recall) == ("1.000000", "1.000000")
    locations = {
        (
            item.document_bytes_hash,
            item.start_offset,
            item.end_offset,
        )
        for item in targets.values()
    }
    location = source_location_confusion(locations, locations)
    assert (location.precision, location.recall) == ("1.000000", "1.000000")
    positive = {key for key, item in targets.items() if item.expected_supported}
    trusted = {
        decision.golden_id
        for decision in batch.decisions
        if decision.golden_id is not None and decision.final_state.value == "trusted"
    }
    trust = automatic_trust_confusion(positive, trusted, expected)
    assert (
        trust.correct_trusted,
        trust.wrong_trusted,
        trust.correct_withheld,
        trust.incorrect_withheld,
    ) == (300, 0, 300, 0)
    assert (trust.precision, trust.recall, trust.coverage, trust.wrong_count) == (
        "1.000000",
        "1.000000",
        "1.000000",
        0,
    )
    abstention = safe_abstention(expected - positive, trusted)
    assert abstention.abstention_rate == "1.000000"
    assert binary_confusion({"a"}, set(), {"a"}).recall == "0.000000"
    assert binary_confusion(set(), set(), set()).precision == "N/A"
    assert automatic_trust_confusion({"a"}, set(), {"a"}).coverage == "0.000000"
    conflict = set_detection_confusion({"seed"}, set())
    assert (conflict.recall, conflict.precision) == ("0.000000", "N/A")


@pytest.fixture(scope="module")
def compiled_pack(java_closure):
    root, store, batch, authorizations = java_closure
    authorization_by_id = {item.trusted_proposal_id: item for item in authorizations}
    reviewed = []
    approvals = []
    for proposal in batch.trusted_proposals:
        updated, _review, approval = review_proposal(
            proposal,
            reviewer_identity="m342-human",
            reviewer_type=ActorIdentityType.USER,
            decision=ReviewDecision.APPROVE,
            rationale="sealed development corpus",
            timestamp=STAMP,
            trust_authorization=authorization_by_id[proposal.proposal_id],
        )
        reviewed.append(updated)
        approvals.append(approval)
    output = root / "compiled-pack"
    compile_provisional_pack(
        batch.bundle,
        batch.segmentation.segments,
        tuple(reviewed),
        tuple(approvals),
        output,
        domain_id="m342-java-dev",
        trust_bound_batch=batch,
        store=store,
    )
    return output


def test_compiled_evidence_replays_in_a_fresh_process(compiled_pack):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/m342_verify_java_evidence.py"),
            str(compiled_pack),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["status"] == "PASS"
    assert report["trusted_proposal_count"] == 300
    assert report["evidence_count"] == 12598


@pytest.mark.parametrize(
    "path",
    (
        "source_blobs",
        "field_evidence_manifest_hash",
        "trust_closure",
        "golden_seal",
        "evidence_policy_manifest_hash",
        "trust_decisions",
        "proposal_manifest_hash",
        "compiled_source_bindings",
    ),
)
def test_standalone_replay_rejects_independent_tamper(compiled_pack, tmp_path, path):
    target = tmp_path / "pack"
    target.mkdir()
    for source in compiled_pack.iterdir():
        (target / source.name).write_bytes(source.read_bytes())
    artifact = target / JAVA_REPLAY_FILENAME
    row = json.loads(artifact.read_text(encoding="utf-8"))
    row[path] = "tampered"
    artifact.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_compiled_java_evidence_standalone(target)
