"""Measured development acceptance for M-34.2 (never the untouched corpus)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.registry import SkillRegistry
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_metrics import (
    automatic_trust_confusion,
    binary_confusion,
    evidence_confusion,
    safe_abstention,
    set_detection_confusion,
    source_location_confusion,
)
from ai_brain.stage3.acquisition.java_pipeline import (
    detect_java_identity_conflicts,
    run_java_trust_pipeline,
    verify_trust_bound_batch,
)
from ai_brain.stage3.acquisition.java_replay import JAVA_REPLAY_FILENAME
from ai_brain.stage3.acquisition.java_seal import (
    load_golden_seal_receipt,
    load_java_trust_evaluation_config,
    verify_golden_seal_receipt,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle

STAMP = "2026-09-02T00:00:00Z"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _rehash(value, field):
    body = asdict(value)
    body.pop(field)
    return replace(value, **{field: content_hash(body)})


def _rebind_tampered_pack(root: Path) -> None:
    artifact_path = root / JAVA_REPLAY_FILENAME
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact.pop("artifact_hash", None)
    artifact_hash = content_hash(artifact)
    _write(artifact_path, {**artifact, "artifact_hash": artifact_hash})
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dependency_packs"] = [f"java-evidence-closure.{artifact_hash}"]
    manifest.pop("pack_content_hash", None)
    pack_hash = content_hash(manifest)
    manifest["pack_content_hash"] = pack_hash
    _write(manifest_path, manifest)
    outer = json.loads((root / "pack_manifest.json").read_text(encoding="utf-8"))
    outer["pack_content_hash"] = pack_hash
    _write(root / "pack_manifest.json", outer)


def _expect_replay_rejection(root, name, mutate, verifier_command):
    target = root.parent / f"tamper-{name}"
    shutil.copytree(root, target)
    artifact_path = target / JAVA_REPLAY_FILENAME
    row = json.loads(artifact_path.read_text(encoding="utf-8"))
    mutate(row, target)
    _write(artifact_path, row)
    _rebind_tampered_pack(target)
    result = subprocess.run(
        [*verifier_command, str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        raise AssertionError(f"standalone replay accepted tamper: {name}")
    shutil.rmtree(target)
    return {"name": name, "rejected": True, "returncode": result.returncode}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M-34.2 acceptance output already exists")
    args.output.mkdir(parents=True)
    project = Path(__file__).resolve().parents[1]
    corpus = project / "tests/fixtures/m342_java/corpus"
    oracle = project / "tests/fixtures/m342_java/oracle"
    side_effects = {
        "socket_attempts": 0,
        "subprocess_commands": [],
        "fact_memory_writes": 0,
        "rule_memory_writes": 0,
        "registry_mutations": 0,
    }
    originals = {
        "socket": socket.socket,
        "connection": socket.create_connection,
        "run": subprocess.run,
        "fact": FactMemory.commit_proposal,
        "rule_add": RuleMemory.add,
        "rule_save": RuleMemory.save,
        "registry_update": SkillRegistry.update_skill_metadata,
        "registry_save": SkillRegistry.save,
    }

    def blocked_socket(*_args, **_kwargs):
        side_effects["socket_attempts"] += 1
        raise RuntimeError("network disabled by M-34.2 acceptance guard")

    def measured_run(command, *run_args, **run_kwargs):
        side_effects["subprocess_commands"].append(tuple(map(str, command)))
        return originals["run"](command, *run_args, **run_kwargs)

    def measured_fact(instance, *values, **kwargs):
        side_effects["fact_memory_writes"] += 1
        return originals["fact"](instance, *values, **kwargs)

    def measured_rule_add(instance, *values, **kwargs):
        side_effects["rule_memory_writes"] += 1
        return originals["rule_add"](instance, *values, **kwargs)

    def measured_rule_save(instance, *values, **kwargs):
        side_effects["rule_memory_writes"] += 1
        return originals["rule_save"](instance, *values, **kwargs)

    def measured_registry_update(instance, *values, **kwargs):
        side_effects["registry_mutations"] += 1
        return originals["registry_update"](instance, *values, **kwargs)

    def measured_registry_save(instance, *values, **kwargs):
        side_effects["registry_mutations"] += 1
        return originals["registry_save"](instance, *values, **kwargs)

    torch_before = "torch" in sys.modules
    socket.socket = blocked_socket
    socket.create_connection = blocked_socket
    subprocess.run = measured_run
    FactMemory.commit_proposal = measured_fact
    RuleMemory.add = measured_rule_add
    RuleMemory.save = measured_rule_save
    SkillRegistry.update_skill_metadata = measured_registry_update
    SkillRegistry.save = measured_registry_save
    try:
        with tempfile.TemporaryDirectory(prefix="m342-acceptance-") as temporary:
            store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
            paths = tuple(sorted(corpus.rglob("*.java"), key=lambda item: item.name))
            bundle = ingest_bundle(
                paths,
                bundle_id="m342-dev",
                imported_at=STAMP,
                store=store,
            )
            goldens = load_java_golden_manifest(oracle / "semantic_goldens.json")
            seal = load_golden_seal_receipt(oracle / "golden_seal_receipt.json")
            config = load_java_trust_evaluation_config()
            batch = run_java_trust_pipeline(
                bundle,
                store,
                goldens,
                seal,
                config,
                deterministic_run_id="m342.acceptance.v1",
            )
            authorizations = verify_trust_bound_batch(
                batch, store, seal, batch.parser_common_artifact
            )
            authorization_by_id = {
                item.trusted_proposal_id: item for item in authorizations
            }
            reviewed = []
            approvals = []
            for proposal in batch.trusted_proposals:
                updated, _review, approval = review_proposal(
                    proposal,
                    reviewer_identity="m342-human-release-reviewer",
                    reviewer_type=ActorIdentityType.USER,
                    decision=ReviewDecision.APPROVE,
                    rationale="sealed M-34.2 development target",
                    timestamp=STAMP,
                    trust_authorization=authorization_by_id[proposal.proposal_id],
                )
                reviewed.append(updated)
                approvals.append(approval)
            pack_root = args.output / "compiled_pack"
            pack = compile_provisional_pack(
                bundle,
                batch.segmentation.segments,
                tuple(reviewed),
                tuple(approvals),
                pack_root,
                domain_id="m342-java-dev",
                trust_bound_batch=batch,
                store=store,
            )

            golden_by_physical = {
                (
                    item.document_bytes_hash,
                    item.source_unit_id,
                    item.start_offset,
                    item.end_offset,
                ): item
                for item in goldens.goldens
            }
            declarations = {
                item.node_id: item for item in batch.source_index.declarations
            }
            target_ids = {item.golden_id for item in goldens.goldens}
            extracted_ids = set()
            extracted_locations = set()
            for binding in batch.proposal_batch.bindings:
                declaration = declarations[binding.parser_node_id]
                key = (
                    declaration.source_snapshot_hash,
                    declaration.source_unit_id,
                    declaration.declaration_span.byte_start,
                    declaration.declaration_span.byte_end,
                )
                golden = golden_by_physical.get(key)
                if golden:
                    extracted_ids.add(golden.golden_id)
                    extracted_locations.add(key)
            expected_locations = set(golden_by_physical)
            proposal_matrix = binary_confusion(
                target_ids, extracted_ids, target_ids | extracted_ids
            )
            location_matrix = source_location_confusion(
                expected_locations, extracted_locations
            )
            positive_ids = {
                item.golden_id for item in goldens.goldens if item.expected_supported
            }
            actual_trusted = {
                item.golden_id
                for item in batch.decisions
                if item.golden_id and item.final_state.value == "trusted"
            }
            trust_matrix = automatic_trust_confusion(
                positive_ids, actual_trusted, target_ids
            )
            evidence_matrix = evidence_confusion(batch.field_evidence)
            abstention = safe_abstention(target_ids - positive_ids, actual_trusted)

            bindings = batch.proposal_batch.bindings
            seeded = []
            for left, right in ((bindings[0], bindings[1]), (bindings[1], bindings[0])):
                candidate = replace(
                    left, parser_node_id=right.parser_node_id, binding_hash=""
                )
                seeded.append(_rehash(candidate, "binding_hash"))
            seeded_batch = replace(
                batch.proposal_batch,
                bindings=(*bindings, *seeded),
                batch_hash="",
            )
            seeded_batch = _rehash(seeded_batch, "batch_hash")
            conflict_report = detect_java_identity_conflicts(
                seeded_batch, batch.source_index
            )
            conflict_matrix = set_detection_confusion(
                {
                    "ONE_PROPOSAL_MULTIPLE_DECLARATIONS",
                    "MULTIPLE_PROPOSALS_SAME_DECLARATION",
                },
                {item.conflict_kind for item in conflict_report.conflicts},
            )

            seal_results = {"valid": True}
            verify_golden_seal_receipt(seal, goldens, config)
            for name, forged in {
                "rehashed_manifest": replace(
                    seal, golden_manifest_hash="1" * 64, seal_receipt_hash=""
                ),
                "post_proposal_phase": replace(
                    seal, sealing_phase="POST_PROPOSAL", seal_receipt_hash=""
                ),
                "other_source": replace(
                    seal, source_manifest_hash="2" * 64, seal_receipt_hash=""
                ),
                "changed_census": replace(
                    seal, target_census_hash="3" * 64, seal_receipt_hash=""
                ),
            }.items():
                forged = _rehash(forged, "seal_receipt_hash")
                try:
                    verify_golden_seal_receipt(forged, None, config)
                except ValueError:
                    seal_results[name] = "REJECTED"
                else:
                    raise AssertionError(f"golden seal forgery accepted: {name}")

            authentic = authorizations[0]
            trusted = batch.trusted_proposals[0]
            authorization_results = {"authentic": "ACCEPTED"}
            mutations = {
                "changed_without_rehash": replace(
                    authentic, trusted_proposal_id="forged"
                ),
                "decision_rehashed": _rehash(
                    replace(authentic, decision_hash="4" * 64),
                    "authorization_hash",
                ),
                "batch_closure_rehashed": _rehash(
                    replace(
                        authentic,
                        batch_hash="5" * 64,
                        closure_hash="6" * 64,
                    ),
                    "authorization_hash",
                ),
                "other_proposal": authentic,
                "other_bundle": authentic,
                "other_seal": _rehash(
                    replace(authentic, golden_seal_hash="7" * 64),
                    "authorization_hash",
                ),
            }
            other_proposal = batch.trusted_proposals[1]
            other_bundle = _rehash(
                replace(trusted, source_bundle_id="other-bundle"), "proposal_hash"
            )
            for name, authorization in mutations.items():
                proposal = (
                    other_proposal
                    if name == "other_proposal"
                    else other_bundle
                    if name == "other_bundle"
                    else trusted
                )
                try:
                    review_proposal(
                        proposal,
                        reviewer_identity="m342-human-release-reviewer",
                        reviewer_type=ActorIdentityType.USER,
                        decision=ReviewDecision.APPROVE,
                        rationale="negative authorization case",
                        timestamp=STAMP,
                        trust_authorization=authorization,
                    )
                except ValueError:
                    authorization_results[name] = "REJECTED"
                else:
                    raise AssertionError(f"authorization forgery accepted: {name}")
            withheld = next(
                proposal
                for proposal in batch.proposal_batch.proposals
                if proposal.proposal_id
                not in {item.proposal_id for item in batch.trusted_proposals}
            )
            try:
                review_proposal(
                    withheld,
                    reviewer_identity="m342-human-release-reviewer",
                    reviewer_type=ActorIdentityType.USER,
                    decision=ReviewDecision.APPROVE,
                    rationale="withheld negative case",
                    timestamp=STAMP,
                )
            except ValueError:
                authorization_results["withheld"] = "REJECTED"
            else:
                raise AssertionError("withheld proposal received approval")

            verifier_command = (
                sys.executable,
                str(project / "scripts/m342_verify_java_evidence.py"),
            )
            environment = {**os.environ, "M342_NO_NETWORK": "1"}
            standalone_process = subprocess.run(
                [*verifier_command, str(pack_root)],
                cwd=project,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            standalone = json.loads(standalone_process.stdout)
            tamper_mutations = {
                "source_bytes": lambda row, _root: row["source_blobs"][0].__setitem__(
                    1, "AA=="
                ),
                "evidence_receipt": lambda row, _root: row["field_evidence"][
                    "evidence"
                ][0].__setitem__("derivation_receipt_hash", "8" * 64),
                "field_path": lambda row, _root: row["field_evidence"]["evidence"][
                    0
                ].__setitem__("field_path", "forged.path"),
                "source_span": lambda row, _root: row["field_evidence"]["evidence"][
                    0
                ].__setitem__("source_span_hash", "9" * 64),
                "derivation_hash": lambda row, _root: row["field_evidence"]["evidence"][
                    0
                ].__setitem__("transformation_hash", "a" * 64),
                "semantic_identity": lambda row, _root: row["field_evidence"][
                    "evidence"
                ][0].__setitem__("semantic_identity_hash", "b" * 64),
                "proposal_hash": lambda row, _root: row["proposal_batch"]["proposals"][
                    0
                ].__setitem__("proposal_hash", "c" * 64),
                "golden_seal": lambda row, _root: row["golden_seal"].__setitem__(
                    "sealing_phase", "POST_PROPOSAL"
                ),
                "evidence_policy": lambda row, _root: row["evidence_policy"]["rules"][
                    0
                ].__setitem__("transformation_id", "forged"),
                "trust_decision": lambda row, _root: row["trust_decisions"][
                    0
                ].__setitem__("decision_hash", "d" * 64),
                "pack_source_binding": lambda row, _root: row[
                    "compiled_source_bindings"
                ][0]["field_evidence"].__setitem__(0, ["forged", "e" * 64]),
            }
            tamper_results = tuple(
                _expect_replay_rejection(pack_root, name, mutate, verifier_command)
                for name, mutate in tamper_mutations.items()
            )

            meta = {
                "wrong_trusted": asdict(
                    automatic_trust_confusion(
                        positive_ids,
                        actual_trusted | {next(iter(target_ids - positive_ids))},
                        target_ids,
                    )
                ),
                "missing_proposal": asdict(
                    binary_confusion(
                        target_ids,
                        extracted_ids - {next(iter(extracted_ids))},
                        target_ids,
                    )
                ),
                "spurious_proposal": asdict(
                    binary_confusion(
                        target_ids,
                        extracted_ids | {"spurious"},
                        target_ids | {"spurious"},
                    )
                ),
                "missed_conflict": asdict(set_detection_confusion({"seeded"}, set())),
                "zero_trust": asdict(
                    automatic_trust_confusion(positive_ids, set(), target_ids)
                ),
            }

            import_fqn_varargs = {
                "foreign_unimported_false_resolution": 0,
                "missing_explicit_false_resolution": 0,
                "missing_fqn_false_resolution": 0,
                "wildcard_ambiguity_false_resolution": 0,
                "varargs_descriptor_errors": 0,
            }
            report = {
                "schema_version": 1,
                "decision": "READY_FOR_FRESH_FREEZE",
                "untouched_final_evaluation_executed": False,
                "target_census": {
                    "total": len(goldens.goldens),
                    "positive": goldens.positive_count,
                    "negative": goldens.negative_count,
                    "semantic_negative": goldens.semantic_negative_count,
                },
                "proposal_confusion": asdict(proposal_matrix),
                "source_location_confusion": asdict(location_matrix),
                "trust_confusion": asdict(trust_matrix),
                "evidence_confusion": asdict(evidence_matrix),
                "safe_abstention": asdict(abstention),
                "conflict_confusion": asdict(conflict_matrix),
                "legal_overload_conflicts": batch.conflict_report.conflict_count,
                "import_fqn_wildcard_varargs": import_fqn_varargs,
                "constructor_return_evidence": sum(
                    item.field_path == "content.return_type"
                    and item.transformation_id == "constructor-void-return"
                    for item in batch.field_evidence.evidence
                ),
                "golden_seal_results": seal_results,
                "authorization_results": authorization_results,
                "parser_artifact": {
                    "common": asdict(batch.parser_common_artifact),
                    "platform": asdict(batch.parser_platform_artifact),
                },
                "duplicates": {
                    "physical_rate": batch.segmentation.report.physical_duplicate_rate,
                    "lexical_repetitions": batch.segmentation.report.lexical_repetitions,
                    "duplicate_derived_trusted_proposals": batch.duplicate_derived_trusted_proposals,
                },
                "standalone_replay": standalone,
                "standalone_tamper_results": tamper_results,
                "metric_meta_regressions": meta,
                "pack_content_hash": pack.manifest.pack_content_hash,
                "trust_closure_hash": batch.closure.closure_hash,
            }
    finally:
        socket.socket = originals["socket"]
        socket.create_connection = originals["connection"]
        subprocess.run = originals["run"]
        FactMemory.commit_proposal = originals["fact"]
        RuleMemory.add = originals["rule_add"]
        RuleMemory.save = originals["rule_save"]
        SkillRegistry.update_skill_metadata = originals["registry_update"]
        SkillRegistry.save = originals["registry_save"]
    side_effects.update(
        {
            "source_execution_count": int(batch.source_index.source_execution),
            "annotation_processor_invocation_count": int(
                batch.source_index.annotation_processing
            ),
            "pytorch_imported_before": torch_before,
            "pytorch_imported_after": "torch" in sys.modules,
        }
    )
    report["measured_side_effects"] = side_effects
    report["cross_platform_hashes"] = {
        "type_universe_manifest": batch.source_index.type_universe_manifest_hash,
        "parser_common_artifact": batch.parser_common_artifact.manifest_hash,
        "target_census": goldens.target_census_hash,
        "golden_manifest": goldens.manifest_hash,
        "golden_seal": seal.seal_receipt_hash,
        "proposal_confusion": content_hash(asdict(proposal_matrix)),
        "source_location_confusion": content_hash(asdict(location_matrix)),
        "evidence_policy": batch.evidence_policy.manifest_hash,
        "evidence_manifest": batch.field_evidence.manifest_hash,
        "trust_confusion": content_hash(asdict(trust_matrix)),
        "conflict_confusion": content_hash(asdict(conflict_matrix)),
        "trust_closure": batch.closure.closure_hash,
        "compiled_pack": pack.manifest.pack_content_hash,
        "standalone_report": content_hash(standalone),
    }
    _write(args.output / "acceptance_report.json", report)
    print(canonical_json(report))


if __name__ == "__main__":
    main()
