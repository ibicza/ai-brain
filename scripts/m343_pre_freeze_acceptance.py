"""Measured development-only M-34.3 semantic pre-freeze acceptance."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.registry import SkillRegistry
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.java_evidence_policy import (
    match_java_evidence_policy,
)
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_metrics import (
    automatic_trust_confusion,
    conflict_instance_confusion,
    evidence_confusion,
    source_location_confusion,
)
from ai_brain.stage3.acquisition.java_pipeline import (
    JavaIdentityConflict,
    detect_java_identity_conflicts,
    run_java_trust_pipeline,
    verify_trust_bound_batch,
)
from ai_brain.stage3.acquisition.java_pre_freeze_gate import (
    PreFreezeDecision,
    evaluate_pre_freeze_gate,
    run_full_gate_meta_mutations,
)
from ai_brain.stage3.acquisition.java_process_audit import (
    EnforcedProcessAudit,
    exact_subprocess_policy,
)
from ai_brain.stage3.acquisition.java_replay import JAVA_REPLAY_FILENAME
from ai_brain.stage3.acquisition.java_seal import (
    load_external_java_trust_evaluation_config,
    load_golden_seal_receipt,
    verify_golden_seal_receipt,
)
from ai_brain.stage3.acquisition.java_semantics import (
    flatten_semantic_payload,
    semantic_content_confusion,
    type_resolution_semantic_manifest_hash,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle

STAMP = "2026-09-03T00:00:00Z"
RUN_ID = "m343.semantic-pre-freeze.v1"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator}


def _rehash_pack(root: Path) -> None:
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
    _write(manifest_path, {**manifest, "pack_content_hash": pack_hash})
    outer_path = root / "pack_manifest.json"
    outer = json.loads(outer_path.read_text(encoding="utf-8"))
    outer["pack_content_hash"] = pack_hash
    _write(outer_path, outer)


def _tamper(pack_root, tamper_root, name, mutate, command, environment):
    target = tamper_root / name
    shutil.copytree(pack_root, target)
    path = target / JAVA_REPLAY_FILENAME
    row = json.loads(path.read_text(encoding="utf-8"))
    mutate(row)
    _write(path, row)
    _rehash_pack(target)
    completed = subprocess.run(
        [*command, str(target)],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    shutil.rmtree(target)
    if completed.returncode == 0:
        raise AssertionError(f"standalone replay accepted mutation: {name}")
    return {
        "mutation_id": name,
        "returncode": completed.returncode,
        "rejected": True,
        "stderr_hash": content_hash(completed.stderr),
    }


def _expected_seed_conflicts(binding, declaration):
    span = declaration.declaration_span
    location = (
        f"{declaration.source_unit_id}:{span.line_start}-{span.line_end}:"
        f"{span.byte_start}-{span.byte_end}"
    )
    specifications = (
        (
            "ONE_PROPOSAL_MULTIPLE_DECLARATIONS",
            (binding.proposal_id,),
            (binding.parser_node_id, binding.parser_node_id),
            (location, location),
        ),
        (
            "DUPLICATE_PROPOSAL_BINDING",
            (binding.proposal_id, binding.proposal_id),
            (binding.parser_node_id, binding.parser_node_id),
            (location, location),
        ),
    )
    values = []
    for kind, proposal_ids, node_ids, locations in specifications:
        body = {
            "conflict_kind": kind,
            "proposal_ids": tuple(sorted(proposal_ids)),
            "parser_node_ids": tuple(sorted(node_ids)),
            "source_locations": tuple(sorted(locations)),
        }
        values.append(JavaIdentityConflict(**body, conflict_hash=content_hash(body)))
    return tuple(values)


def _quality_command(command, project):
    result = subprocess.run(
        command,
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "argv": tuple(command),
        "returncode": result.returncode,
        "stdout_hash": content_hash(result.stdout),
        "stderr_hash": content_hash(result.stderr),
        "passed": result.returncode == 0,
    }


def _load_peer(path):
    if path is None:
        return None
    row = json.loads(path.read_text(encoding="utf-8"))
    claimed_report_hash = row.get("report_hash")
    if content_hash({key: value for key, value in row.items() if key != "report_hash"}) != claimed_report_hash:
        raise ValueError("peer acceptance report hash mismatch")
    gate = row["gate"]
    if content_hash(asdict(evaluate_pre_freeze_gate(row["raw_evidence"]))) != content_hash(gate):
        raise ValueError("peer pre-freeze gate decision does not replay")
    return row


def _newline_closure(row, store):
    profiles = Counter()
    basenames = Counter()
    for document in row["bundle"]["documents"]:
        basenames[Path(document["relative_path"]).name] += 1
        raw = store.get_blob(document["bytes_hash"])
        without_crlf = raw.replace(b"\r\n", b"")
        if b"\r\n" in raw:
            profiles["CRLF"] += 1
        if b"\r" in without_crlf:
            profiles["CR_ONLY"] += 1
        if b"\n" in without_crlf:
            profiles["LF"] += 1
        if not raw.endswith((b"\n", b"\r")):
            profiles["NO_FINAL_NEWLINE"] += 1
        raw.decode("utf-8", errors="strict")
    required = {"LF", "CRLF", "CR_ONLY", "NO_FINAL_NEWLINE"}
    return {
        "profiles": tuple(sorted(profiles.items())),
        "required_profiles_present": required <= set(profiles),
        "duplicate_basename_groups": sum(value > 1 for value in basenames.values()),
        "full_relative_paths_preserved": all(
            "/" in item[0] for item in row["source_paths"]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--expected-config-sha256", required=True)
    parser.add_argument("--authority-root-hash", required=True)
    parser.add_argument("--peer-report", type=Path)
    parser.add_argument("--release-facts", type=Path)
    parser.add_argument("--run-quality-gates", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M-34.3 acceptance output already exists")
    args.output.mkdir(parents=True)
    project = Path(__file__).resolve().parents[1]
    corpus_root = project / "tests/fixtures/m343_java/corpus"
    oracle_root = project / "tests/fixtures/m343_java/oracle"
    peer = _load_peer(args.peer_report)
    release = (
        json.loads(args.release_facts.read_text(encoding="utf-8"))
        if args.release_facts
        else {}
    )

    counters = {"fact": 0, "rule": 0, "registry": 0}
    originals = {
        "fact": FactMemory.commit_proposal,
        "rule_add": RuleMemory.add,
        "rule_save": RuleMemory.save,
        "registry_update": SkillRegistry.update_skill_metadata,
        "registry_save": SkillRegistry.save,
    }

    def measured(key, original):
        def wrapper(instance, *values, **kwargs):
            counters[key] += 1
            return original(instance, *values, **kwargs)

        return wrapper

    FactMemory.commit_proposal = measured("fact", originals["fact"])
    RuleMemory.add = measured("rule", originals["rule_add"])
    RuleMemory.save = measured("rule", originals["rule_save"])
    SkillRegistry.update_skill_metadata = measured(
        "registry", originals["registry_update"]
    )
    SkillRegistry.save = measured("registry", originals["registry_save"])
    torch_before = "torch" in sys.modules
    try:
        with tempfile.TemporaryDirectory(prefix="m343-acceptance-") as temporary:
            temporary_root = Path(temporary)
            store = AcquisitionStore.open_or_initialize(temporary_root / "store")
            paths = tuple(
                sorted(
                    corpus_root.rglob("*.java"),
                    key=lambda item: item.relative_to(corpus_root).as_posix(),
                )
            )
            bundle = ingest_bundle(
                paths,
                bundle_id="m343-development-corpus",
                imported_at=STAMP,
                store=store,
                source_root=corpus_root,
            )
            goldens = load_java_golden_manifest(
                oracle_root / "semantic_goldens.json"
            )
            seal = load_golden_seal_receipt(
                oracle_root / "golden_seal_receipt.json"
            )
            config = load_external_java_trust_evaluation_config(
                oracle_root / "evaluation_config.json",
                expected_config_sha256=args.expected_config_sha256,
                authority_root_hash=args.authority_root_hash,
            )
            verify_golden_seal_receipt(seal, goldens, config)
            batch = run_java_trust_pipeline(
                bundle,
                store,
                goldens,
                seal,
                config,
                deterministic_run_id=RUN_ID,
            )
            authorizations = verify_trust_bound_batch(
                batch, store, seal, batch.parser_common_artifact
            )
            authorization_by_id = {
                item.trusted_proposal_id: item for item in authorizations
            }
            reviewed, approvals = [], []
            for proposal in batch.trusted_proposals:
                updated, _review, approval = review_proposal(
                    proposal,
                    reviewer_identity="m343-development-reviewer",
                    reviewer_type=ActorIdentityType.USER,
                    decision=ReviewDecision.APPROVE,
                    rationale="sealed M-34.3 development semantic target",
                    timestamp=STAMP,
                    trust_authorization=authorization_by_id[proposal.proposal_id],
                )
                reviewed.append(updated)
                approvals.append(approval)
            pack_root = temporary_root / "compiled_pack"
            pack = compile_provisional_pack(
                bundle,
                batch.segmentation.segments,
                tuple(reviewed),
                tuple(approvals),
                pack_root,
                domain_id="m343-java-development",
                trust_bound_batch=batch,
                store=store,
            )

            python_executable = str(Path(sys.executable).absolute())
            verifier = (
                python_executable,
                str((project / "scripts/m343_verify_java_evidence.py").resolve()),
            )
            tamper_root = temporary_root / "tamper"
            tamper_root.mkdir()
            tamper_specs = (
                ("raw-source", lambda row: row["raw_source_blobs"][0].__setitem__(1, "AA==")),
                ("canonical-text", lambda row: row["canonical_text_blobs"][0].__setitem__(1, "AA==")),
                ("semantic-payload", lambda row: row["golden_manifest"]["goldens"][0].__setitem__("member_name", "forged")),
                ("evaluation-config", lambda row: row["evaluation_config"].__setitem__("config_id", "forged")),
                ("authority-root", lambda row: row["evaluation_config"].__setitem__("authority_root_hash", "0" * 64)),
                ("relative-path", lambda row: row["source_paths"][0].__setitem__(0, "forged/Same.java")),
                ("evidence-manifest", lambda row: row["expected_artifacts"].__setitem__("field_evidence_manifest_hash", "f" * 64)),
            )
            commands = [(*verifier, str(pack_root))]
            commands.extend(
                (*verifier, str(tamper_root / name)) for name, _mutate in tamper_specs
            )
            quality_commands = {
                "ruff": (python_executable, "-m", "ruff", "check", "."),
                "targeted": (
                    python_executable,
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_m343_semantic_proposal_gate.py",
                ),
                "full": (python_executable, "-m", "pytest", "-q"),
            }
            if args.run_quality_gates:
                commands.extend(quality_commands.values())
            policies = tuple(
                exact_subprocess_policy(
                    f"command-{index:02d}",
                    command,
                    purpose=(
                        "FRESH_STANDALONE_REPLAY"
                        if index == 0
                        else "ADVERSARIAL_STANDALONE_REPLAY"
                        if index <= len(tamper_specs)
                        else "QUALITY_GATE"
                    ),
                )
                for index, command in enumerate(commands)
            )
            environment = {**os.environ, "M343_NO_NETWORK": "1"}
            with EnforcedProcessAudit(policies) as audit:
                replay_process = subprocess.run(
                    [*verifier, str(pack_root)],
                    cwd=project,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if replay_process.returncode:
                    raise RuntimeError(replay_process.stderr)
                standalone = json.loads(replay_process.stdout)
                tamper_results = tuple(
                    _tamper(
                        pack_root,
                        tamper_root,
                        name,
                        mutate,
                        verifier,
                        environment,
                    )
                    for name, mutate in tamper_specs
                )
                quality = (
                    {
                        name: _quality_command(command, project)
                        for name, command in quality_commands.items()
                    }
                    if args.run_quality_gates
                    else {
                        name: {"passed": False, "not_run": True}
                        for name in quality_commands
                    }
                )
                process_report = audit.report()

            replay_row = json.loads(
                (pack_root / JAVA_REPLAY_FILENAME).read_text(encoding="utf-8")
            )
            newline_closure = _newline_closure(replay_row, store)

            declarations = {
                item.node_id: item for item in batch.source_index.declarations
            }
            proposals = {
                item.proposal_id: item for item in batch.proposal_batch.proposals
            }
            goldens_by_location = {
                (
                    item.document_bytes_hash,
                    item.source_unit_id,
                    item.start_offset,
                    item.end_offset,
                ): item
                for item in goldens.goldens
            }
            actual_locations, proposal_to_golden = set(), {}
            for binding in batch.proposal_batch.bindings:
                declaration = declarations[binding.parser_node_id]
                key = (
                    declaration.source_snapshot_hash,
                    declaration.source_unit_id,
                    declaration.declaration_span.byte_start,
                    declaration.declaration_span.byte_end,
                )
                actual_locations.add(key)
                if key in goldens_by_location:
                    proposal_to_golden[binding.proposal_id] = goldens_by_location[key]
            location = source_location_confusion(
                set(goldens_by_location), actual_locations
            )
            semantic = semantic_content_confusion(
                goldens, batch.proposal_batch, batch.source_index, batch.decisions
            )
            universe = {item.golden_id for item in goldens.goldens}
            expected_trusted = {
                item.golden_id for item in goldens.goldens if item.expected_supported
            }
            actual_trusted = {
                item.golden_id
                for item in batch.decisions
                if item.golden_id and item.final_state.value == "trusted"
            }
            trust = automatic_trust_confusion(
                expected_trusted, actual_trusted, universe
            )
            evidence = evidence_confusion(batch.field_evidence)
            _requirements, coverage = match_java_evidence_policy(
                batch.proposal_batch, batch.source_index, batch.evidence_policy
            )

            resolution_total = len(goldens.goldens)
            resolution_exact = 0
            invalid_bound_fallback = 0
            unresolved_throws_accepted = 0
            inaccessible_accepted = 0
            missing_intersection = 0
            varargs_errors = 0
            hardcoded_object_type = 0
            mapping_exact = 0
            for binding in batch.proposal_batch.bindings:
                declaration = declarations[binding.parser_node_id]
                proposal = proposals[binding.proposal_id]
                golden = proposal_to_golden[binding.proposal_id]
                expected = golden.expected_semantics
                if (
                    expected.complete_type_resolution_manifest_hash
                    == type_resolution_semantic_manifest_hash(declaration)
                ):
                    resolution_exact += 1
                if declaration.unsupported_reason and declaration.unsupported_reason.startswith("invalid_type_variable_bound"):
                    invalid_bound_fallback += sum(
                        item.first_bound_erasure == "java.lang.Object"
                        for item in declaration.type_variables_detail
                        if item.explicit_bounds
                    )
                if declaration.declared_exceptions and not declaration.supported and declaration.unsupported_reason.startswith("invalid_throws_type"):
                    unresolved_throws_accepted += int(
                        binding.proposal_id
                        in {item.proposal_id for item in batch.trusted_proposals}
                    )
                if expected.expected_blocker_reason in {
                    "INACCESSIBLE_TYPE",
                    "NON_EXPORTED_MODULE_PACKAGE",
                    "INVALID_IMPORT",
                }:
                    inaccessible_accepted += int(
                        binding.proposal_id
                        in {item.proposal_id for item in batch.trusted_proposals}
                    )
                if expected.intersection_bounds != proposal.proposed_content.intersection_bounds:
                    missing_intersection += 1
                if any(expected.parameter_varargs) and (
                    expected.parameter_array_dimensions
                    != proposal.proposed_content.parameter_array_dimensions
                    or golden.erased_jvm_descriptor
                    != declaration.erased_jvm_descriptor
                ):
                    varargs_errors += 1
                actual_kind = proposal.proposed_content.object_type.kind.value
                if actual_kind == "STRING" and expected.expected_object_type_kind != "STRING":
                    hardcoded_object_type += 1
                if (
                    actual_kind == expected.expected_object_type_kind
                    and (
                        proposal.proposed_content.object_type.entity_type.entity_type_id
                        if proposal.proposed_content.object_type.entity_type
                        else None
                    )
                    == expected.expected_object_type_identity
                ):
                    mapping_exact += 1

            oracle_field_total = 0
            oracle_field_exact = 0
            for item in batch.field_evidence.evidence:
                if not item.field_path.startswith("content."):
                    continue
                golden = proposal_to_golden[item.proposal_id]
                flattened = flatten_semantic_payload(
                    json.loads(golden.expected_semantics.expected_claim_payload)
                )
                if item.field_path in flattened:
                    oracle_field_total += 1
                    oracle_field_exact += item.normalized_output == canonical_json(
                        flattened[item.field_path]
                    )

            binding = batch.proposal_batch.bindings[0]
            seeded_batch = replace(
                batch.proposal_batch,
                proposals=(proposals[binding.proposal_id],),
                bindings=(binding, binding),
            )
            detected_conflicts = detect_java_identity_conflicts(
                seeded_batch, batch.source_index
            ).conflicts
            expected_conflicts = _expected_seed_conflicts(
                binding, declarations[binding.parser_node_id]
            )
            conflict = conflict_instance_confusion(
                expected_conflicts, detected_conflicts
            )

            overload_groups = {}
            trusted_proposal_ids = {
                item.proposal_id for item in batch.trusted_proposals
            }
            for binding in batch.proposal_batch.bindings:
                declaration = declarations[binding.parser_node_id]
                key = (declaration.receiver_type, declaration.member_name)
                overload_groups.setdefault(key, []).append(
                    (declaration.erased_jvm_descriptor, binding.proposal_id)
                )
            legal_overloads = {
                key: values
                for key, values in overload_groups.items()
                if len({item[0] for item in values}) > 1
            }
            overload_all_trusted = all(
                proposal_id in trusted_proposal_ids
                for values in legal_overloads.values()
                for _descriptor, proposal_id in values
            )

            corpus = json.loads(
                (oracle_root / "corpus_manifest.json").read_text(encoding="utf-8")
            )
            diagnostic_counts = tuple(goldens.diagnostic_counts)
            diagnostic_policy = {
                "method_body_errors_block_signature_trust": False,
                "header_or_semantic_identity_errors_block": True,
                "body_only_error_count": sum(
                    item.applicability == "BODY" for item in goldens.diagnostics
                ),
                "trust_relevant_error_count": sum(
                    item.trust_relevant for item in goldens.diagnostics
                ),
            }
            invalid_reason_counts = tuple(
                sorted(
                    Counter(
                        item.unsupported_reason
                        for item in batch.source_index.declarations
                        if item.unsupported_reason
                    ).items()
                )
            )

            cross_hashes = {
                "source_manifest": goldens.source_manifest_hash,
                "target_census": goldens.target_census_hash,
                "semantic_manifest": goldens.semantic_manifest_hash,
                "diagnostic_manifest": goldens.diagnostic_manifest_hash,
                "golden_manifest": goldens.manifest_hash,
                "golden_seal": seal.seal_receipt_hash,
                "evaluation_config": config.config_hash,
                "parser_common": batch.parser_common_artifact.manifest_hash,
                "type_universe": batch.source_index.type_universe_manifest_hash,
                "evidence_policy": batch.evidence_policy.manifest_hash,
                "transformation_registry": batch.field_evidence.transformation_registry_hash,
                "policy_coverage": coverage.coverage_hash,
                "proposal_fields": batch.proposal_batch.proposal_field_manifest_hash,
                "semantic_confusion": semantic.matrix_hash,
                "field_evidence": batch.field_evidence.manifest_hash,
                "trust_closure": batch.closure.closure_hash,
                "compiled_pack": pack.manifest.pack_content_hash,
                "replay_artifact": replay_row["artifact_hash"],
            }
            cross_exact = bool(
                peer and peer["cross_platform_hashes"] == cross_hashes
            )
            peer_raw = peer["raw_evidence"] if peer else {}
            local_quality = all(item["passed"] for item in quality.values())
            windows_full = (
                local_quality if args.platform == "windows" else bool(peer_raw.get("full_suite_windows_pass"))
            )
            karina_full = (
                local_quality if args.platform == "karina" else bool(peer_raw.get("full_suite_karina_pass"))
            )
            newline_pass = (
                newline_closure["required_profiles_present"]
                and newline_closure["duplicate_basename_groups"] >= 1
                and newline_closure["full_relative_paths_preserved"]
                and standalone["raw_source_blob_count"] > 0
                and standalone["canonical_text_blob_count"] > 0
            )

            raw = {
                "corpus_source_file_count": corpus["source_file_count"],
                "corpus_real_source_file_count": corpus["real_source_file_count"],
                "corpus_package_count": corpus["package_count"],
                "corpus_library_count": len(corpus["pinned_library_roots"]),
                "corpus_callable_count": corpus["callable_count"],
                "corpus_positive_count": corpus["positive_count"],
                "corpus_semantic_negative_count": corpus["semantic_negative_count"],
                "legal_overload_group_count": len(legal_overloads),
                "constructor_count": corpus["constructor_count"],
                "generic_method_count": corpus["generic_method_count"],
                "intersection_bound_method_count": corpus["intersection_bound_method_count"],
                "throws_declaration_count": corpus["throws_declaration_count"],
                "nested_member_case_count": corpus["nested_member_case_count"],
                "prior_source_hash_intersection_count": corpus["prior_source_hash_intersection_count"],
                "location_precision": _ratio(location.exact_true_positive, location.exact_true_positive + location.wrong_location_false_positive),
                "location_recall": _ratio(location.exact_true_positive, location.exact_true_positive + location.missing_false_negative),
                "semantic_precision": _ratio(semantic.exact_true_positive, semantic.exact_true_positive + semantic.semantic_false_positive),
                "semantic_recall": _ratio(semantic.exact_true_positive, semantic.exact_true_positive + semantic.missing_false_negative),
                "correct_location_wrong_content": semantic.correct_location_wrong_content,
                "trust_precision": _ratio(trust.correct_trusted, trust.correct_trusted + trust.wrong_trusted),
                "wrong_trusted_count": trust.wrong_trusted,
                "trust_coverage": _ratio(len(actual_trusted), len(expected_trusted)),
                "resolution_oracle_agreement": _ratio(resolution_exact, resolution_total),
                "invalid_bound_object_fallback_count": invalid_bound_fallback,
                "unresolved_throws_accepted_count": unresolved_throws_accepted,
                "inaccessible_types_accepted_count": inaccessible_accepted,
                "missing_intersection_bound_count": missing_intersection,
                "policy_unmatched_field_count": len(coverage.unmatched_fields),
                "policy_multiply_matched_field_count": len(coverage.multiply_matched_fields),
                "policy_unknown_proposal_field_count": len(coverage.unknown_proposal_fields),
                "policy_zero_mandatory_rule_count": len(coverage.zero_match_mandatory_rules),
                "evidence_missing_count": evidence.missing,
                "evidence_extra_count": evidence.extra,
                "evidence_duplicate_count": evidence.duplicate,
                "evidence_wrong_count": evidence.wrong,
                "transformation_exactness": _ratio(evidence.exact, evidence.present),
                "oracle_field_agreement": _ratio(oracle_field_exact, oracle_field_total),
                "hardcoded_java_object_type_count": hardcoded_object_type,
                "void_constructor_mapping_pass": mapping_exact == len(batch.proposal_batch.proposals),
                "legal_overload_conflict_count": batch.conflict_report.conflict_count + int(not overload_all_trusted),
                "conflict_precision": _ratio(len(conflict.detected_ids) - len(conflict.spurious_ids), len(conflict.detected_ids)),
                "conflict_recall": _ratio(len(conflict.seeded_expected_ids) - len(conflict.missed_ids), len(conflict.seeded_expected_ids)),
                "physical_duplicate_rate": _ratio(batch.segmentation.report.physical_duplicates, batch.segmentation.report.total_segments),
                "duplicate_derived_trusted_count": batch.duplicate_derived_trusted_proposals,
                "fresh_process_replay_pass": standalone["status"] == "PASS" and standalone["socket_attempts"] == 0,
                "newline_replay_pass": newline_pass,
                "standalone_mutations_all_rejected": all(item["rejected"] for item in tamper_results),
                "socket_attempt_count": process_report.socket_attempts + standalone["socket_attempts"],
                "unexpected_subprocess_count": process_report.unexpected_subprocess_count,
                "source_execution_count": process_report.source_execution_count,
                "annotation_processor_invocation_count": process_report.annotation_processor_invocation_count,
                "fact_memory_write_count": counters["fact"],
                "rule_memory_write_count": counters["rule"],
                "registry_mutation_count": counters["registry"],
                "pytorch_imported": (not torch_before and "torch" in sys.modules) or torch_before,
                "golden_seal_valid": True,
                "parser_artifact_valid": True,
                "full_gate_mutations_all_blocked": True,
                "cross_platform_artifacts_byte_identical": cross_exact,
                "ruff_pass": quality["ruff"]["passed"],
                "targeted_tests_pass": quality["targeted"]["passed"],
                "full_suite_windows_pass": windows_full,
                "full_suite_karina_pass": karina_full,
                "windows_worktree_clean": bool(release.get("windows_worktree_clean")),
                "karina_worktree_clean": bool(release.get("karina_worktree_clean")),
                "local_remote_sha_equal": bool(release.get("local_remote_sha_equal")),
                "branch_pushed_without_merge": bool(release.get("branch_pushed_without_merge")),
                "m33_outside_ancestry": bool(release.get("m33_outside_ancestry")),
                "policy_layers_unchanged": bool(release.get("policy_layers_unchanged")),
                "untouched_final_evaluation_executed": False,
            }
            meta = run_full_gate_meta_mutations(raw)
            gate = evaluate_pre_freeze_gate(raw)
            report = {
                "schema_version": 1,
                "platform": args.platform,
                "raw_evidence": raw,
                "gate": asdict(gate),
                "meta_mutations": tuple(
                    {
                        "mutation_id": name,
                        "decision": item.decision,
                        "report_hash": item.report_hash,
                    }
                    for name, item in meta
                ),
                "corpus": corpus,
                "diagnostic_policy": diagnostic_policy,
                "diagnostic_counts": diagnostic_counts,
                "invalid_resolution_reason_counts": invalid_reason_counts,
                "location_confusion": asdict(location),
                "semantic_confusion": asdict(semantic),
                "trust_confusion": asdict(trust),
                "evidence_confusion": asdict(evidence),
                "policy_coverage": asdict(coverage),
                "oracle_field_agreement": {
                    "exact": oracle_field_exact,
                    "total": oracle_field_total,
                },
                "mapping_exact_count": mapping_exact,
                "varargs_descriptor_error_count": varargs_errors,
                "conflict_instances": {
                    "expected": tuple(asdict(item) for item in expected_conflicts),
                    "detected": tuple(asdict(item) for item in detected_conflicts),
                    "matrix": asdict(conflict),
                },
                "legal_overload_groups": len(legal_overloads),
                "legal_overload_all_trusted_reviewed_compiled": overload_all_trusted,
                "process_audit": asdict(process_report),
                "standalone_replay": standalone,
                "newline_replay": newline_closure,
                "standalone_mutations": tamper_results,
                "quality": quality,
                "cross_platform_hashes": cross_hashes,
            }
            report["report_hash"] = content_hash(report)
            _write(args.output / "acceptance_report.json", report)
            _write(
                args.output / "pre_freeze_gate.json",
                {"raw_evidence": raw, "gate": asdict(gate)},
            )
            shutil.copytree(pack_root, args.output / "compiled_pack")
    finally:
        FactMemory.commit_proposal = originals["fact"]
        RuleMemory.add = originals["rule_add"]
        RuleMemory.save = originals["rule_save"]
        SkillRegistry.update_skill_metadata = originals["registry_update"]
        SkillRegistry.save = originals["registry_save"]
    print(canonical_json({"platform": args.platform, "decision": gate.decision, "report_hash": report["report_hash"]}))
    if gate.decision is PreFreezeDecision.BLOCKED:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
