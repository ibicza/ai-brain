from __future__ import annotations

import ast
import inspect
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.evaluation import verify_pack_evaluation
from ai_brain.stage3.acquisition.java_file_audit import EnforcedJavaProductionFileAudit
from ai_brain.stage3.acquisition.java_final_gate import (
    M344_FINAL_GATE_SPECS,
    JavaFinalOutcome,
    evaluate_java_final_gate,
)
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    M344_FROZEN_PREFIXES,
    _under,
    verify_java_git_freeze_protocol,
)
from ai_brain.stage3.acquisition.java_pre_freeze_gate_v2 import (
    M344_PRE_FREEZE_V2_SPECS,
    JavaPreFreezeV2Decision,
    evaluate_pre_freeze_gate_v2,
    run_m344_full_gate_mutations,
)
from ai_brain.stage3.acquisition.java_production import (
    run_java_acquisition_pipeline,
    seal_java_production_output,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    JAVA_PRODUCTION_REPLAY_FILENAME,
    verify_compiled_java_production_standalone,
)
from ai_brain.stage3.acquisition.java_release import (
    evaluate_java_release_consistency,
    frozen_java_release_identity,
    verify_java_release_identity,
)
from ai_brain.stage3.acquisition.java_source_selector import (
    _contains_real_callable_type,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION
from ai_brain.stage3.providers.registry import ProviderRegistry


def _tiny_production(tmp_path):
    source = tmp_path / "src" / "demo" / "Sample.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        "package demo; public class Sample { "
        "public Sample() {} public <T extends Number> T echo(T value) "
        "throws java.io.IOException { return value; } }\n",
        encoding="utf-8",
        newline="\n",
    )
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    bundle = ingest_bundle(
        (source,),
        bundle_id="m344-test",
        domain_tags=("java-api",),
        imported_at="2026-09-03T00:00:00Z",
        store=store,
        source_root=tmp_path / "src",
    )
    batch = run_java_acquisition_pipeline(
        bundle, store, deterministic_run_id="m344.test.v1"
    )
    return store, bundle, batch


def test_production_api_is_oracle_free_and_static_import_closure_is_clean():
    signature = inspect.signature(run_java_acquisition_pipeline)
    assert tuple(signature.parameters) == (
        "bundle",
        "store",
        "deterministic_run_id",
        "release_identity",
    )
    with pytest.raises(TypeError):
        run_java_acquisition_pipeline(None, None, golden_manifest=None)
    root = Path(__file__).parents[1] / "src/ai_brain/stage3/acquisition"
    forbidden = (
        "java_goldens",
        "java_seal",
        "java_production_evaluator",
        "m343_java_oracle",
    )
    pending = [root / "java_production.py"]
    seen = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            names = (
                [item.name for item in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            imported = (module, *names)
            assert not any(
                bad in (value or "") for bad in forbidden for value in imported
            )
            if module and module.startswith("ai_brain.stage3.acquisition."):
                candidate = root / f"{module.rsplit('.', 1)[-1]}.py"
                if candidate.exists():
                    pending.append(candidate)


def test_golden_presence_and_substitution_cannot_change_production(tmp_path):
    store, bundle, first = _tiny_production(tmp_path)
    variants = {
        "absent": None,
        "valid": '{"valid":true}\n',
        "forged": '{"expected_supported":false}\n',
        "unreadable": "blocked",
    }
    hashes = []
    for name, payload in variants.items():
        oracle = tmp_path / name / "oracle"
        if payload is not None:
            oracle.mkdir(parents=True)
            (oracle / "semantic_goldens.json").write_text(payload, encoding="utf-8")
        with EnforcedJavaProductionFileAudit() as audit:
            batch = run_java_acquisition_pipeline(
                bundle, store, deterministic_run_id="m344.test.v1"
            )
        assert audit.report().forbidden_read_count == 0
        hashes.append(seal_java_production_output(batch)["production_output_hash"])
    assert (
        len(
            set(hashes + [seal_java_production_output(first)["production_output_hash"]])
        )
        == 1
    )
    with EnforcedJavaProductionFileAudit() as audit, pytest.raises(PermissionError):
        (tmp_path / "forged" / "oracle" / "semantic_goldens.json").read_text()
    assert audit.report().forbidden_read_count == 1


def test_production_authorization_pack_and_replay_need_no_goldens(tmp_path):
    store, bundle, batch = _tiny_production(tmp_path)
    authorizations = verify_java_production_batch(batch, store)
    by_id = {item.trusted_proposal_id: item for item in authorizations}
    reviewed = []
    approvals = []
    for proposal in batch.trusted_proposals:
        updated, _review, approval = review_proposal(
            proposal,
            reviewer_identity="m344-exact-release-process",
            reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
            decision=ReviewDecision.APPROVE,
            rationale="exact mechanically verified production closure",
            timestamp="2026-09-03T00:00:00Z",
            trust_authorization=by_id[proposal.proposal_id],
        )
        reviewed.append(updated)
        approvals.append(approval)
    output = tmp_path / "pack"
    pack = compile_provisional_pack(
        bundle,
        batch.segmentation.segments,
        tuple(reviewed),
        tuple(approvals),
        output,
        domain_id="m344-java-test",
        production_trust_batch=batch,
        production_authorizations=authorizations,
        store=store,
    )
    artifact = json.loads((output / JAVA_PRODUCTION_REPLAY_FILENAME).read_text())
    text = json.dumps(artifact).casefold()
    assert "golden_manifest" not in text
    assert "expected_supported" not in text
    assert "confusion_matrix" not in text
    assert verify_compiled_java_production_standalone(output)["status"] == "PASS"
    verify_pack_evaluation(pack)
    providers = ProviderRegistry.build(tmp_path, ())
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
        reviewer_identity="m344-exact-release-process",
        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
        decision=PackApprovalDecision.APPROVE,
        policy_version="m344.test.v1",
        timestamp="2026-09-03T00:00:00Z",
    )
    registry = InstalledDomainRegistry.initialize(
        tmp_path / "installed",
        capability_registry=capabilities,
        provider_registry=providers,
        created_at="2026-09-03T00:00:00Z",
    )
    installed = registry.install(
        pack, approval, (), installed_at="2026-09-03T00:00:00Z"
    )
    assert installed.pack_hash == pack.manifest.pack_content_hash


def test_production_user_approval_requires_external_artifact(tmp_path):
    store, _bundle, batch = _tiny_production(tmp_path)
    authorization = verify_java_production_batch(batch, store)[0]
    with pytest.raises(ValueError, match="external approval"):
        review_proposal(
            batch.trusted_proposals[0],
            reviewer_identity="claimed-user",
            reviewer_type=ActorIdentityType.USER,
            decision=ReviewDecision.APPROVE,
            rationale="not actually externally approved",
            timestamp="2026-09-03T00:00:00Z",
            trust_authorization=authorization,
        )


def test_release_consistency_and_prefix_boundaries_fail_closed():
    identity = frozen_java_release_identity()
    verify_java_release_identity(identity)
    assert evaluate_java_release_consistency(identity).status == "PASS"
    mismatched = replace(identity, oracle_release=25)
    assert evaluate_java_release_consistency(mismatched).status == "FAIL"
    with pytest.raises(ValueError):
        verify_java_release_identity(mismatched)
    assert _under("evaluation/m344_final_java/a.json", ("evaluation/m344_final_java",))
    assert not _under(
        "evaluation/m344_final_java-evil/a.json", ("evaluation/m344_final_java",)
    )
    for unsafe in ("../final/a", "/final/a", "final\\a"):
        with pytest.raises(ValueError):
            _under(unsafe, ("final",))


def test_pre_freeze_gate_v2_and_all_required_mutations():
    raw = {}
    for _identifier, key, operator, threshold in M344_PRE_FREEZE_V2_SPECS:
        if operator == "BOOL":
            raw[key] = threshold == "true"
        elif "." in threshold:
            raw[key] = {"numerator": 1 if operator == "MIN" else 0, "denominator": 1}
        else:
            raw[key] = int(threshold) if operator == "MIN" else 0
    report = evaluate_pre_freeze_gate_v2(raw)
    assert report.decision is JavaPreFreezeV2Decision.READY_FOR_FRESH_FREEZE
    assert len(run_m344_full_gate_mutations(raw)) == 12


def test_git_freeze_verifier_derives_objects_and_rejects_policy_substitution(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()

    def git(*args):
        return subprocess.run(
            ("git", "-C", str(repository), *args),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(path, value, message):
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8", newline="\n")
        git("add", path)
        git("commit", "-m", message)
        return git("rev-parse", "HEAD")

    git("init", "-b", "main")
    git("config", "user.email", "m344@example.invalid")
    git("config", "user.name", "M344 Test")
    base = commit("src/frozen.py", "base\n", "base")
    git("switch", "-c", "excluded")
    excluded = commit("excluded.txt", "outside\n", "excluded")
    git("switch", "main")
    f13 = commit(
        "scripts/frozen.py",
        "f13\n",
        "M-34.4 freeze oracle-free Java acquisition",
    )
    h13 = commit(
        "evaluation/m344_final_java/input.json",
        "h13\n",
        "M-34.4 untouched real-Java evaluation",
    )
    e13 = commit(
        "runs/m344_fresh_java_freeze/report.json",
        "e13\n",
        "M-34.4 exact-SHA fresh-freeze evidence",
    )
    report = verify_java_git_freeze_protocol(
        repository,
        base_sha=base,
        f13_sha=f13,
        h13_sha=h13,
        e13_sha=e13,
        excluded_m33_sha=excluded,
        branch="main",
    )
    assert report.passed
    assert report.exact_commit_messages
    with pytest.raises(ValueError, match="frozen path policy"):
        verify_java_git_freeze_protocol(
            repository,
            base_sha=base,
            f13_sha=f13,
            h13_sha=h13,
            e13_sha=e13,
            excluded_m33_sha=excluded,
            branch="main",
            frozen_prefixes=M344_FROZEN_PREFIXES[:-1],
        )


def test_final_gate_selects_a_b_and_c_without_lowering_thresholds():
    raw = {}
    for _identifier, key, operator, threshold in M344_FINAL_GATE_SPECS:
        if operator == "BOOL":
            raw[key] = threshold == "true"
        elif "." in threshold:
            raw[key] = {"numerator": 1 if operator == "MIN" else 0, "denominator": 1}
        else:
            raw[key] = int(threshold) if operator == "MIN" else 0
    assert evaluate_java_final_gate(raw).outcome is JavaFinalOutcome.OUTCOME_A
    limited = {**raw, "real_callable_target_count": 1499}
    assert evaluate_java_final_gate(limited).outcome is JavaFinalOutcome.OUTCOME_B
    unsafe = {**raw, "wrong_trusted_count": 1}
    assert evaluate_java_final_gate(unsafe).outcome is JavaFinalOutcome.OUTCOME_C


def test_final_selector_requires_a_real_type_with_a_callable():
    assert _contains_real_callable_type(
        b"package x; public record R(int value) { public int twice() { return value * 2; } }"
    )
    assert not _contains_real_callable_type(b"package x;")
    assert not _contains_real_callable_type(b"package x; public interface Marker {}")
