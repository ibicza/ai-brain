"""Run the F13-frozen untouched Java production-before-oracle evaluation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.evaluation import verify_pack_evaluation
from ai_brain.stage3.acquisition.java_file_audit import EnforcedJavaProductionFileAudit
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_metrics import (
    automatic_trust_confusion,
    source_location_confusion,
)
from ai_brain.stage3.acquisition.java_process_audit import EnforcedProcessAudit
from ai_brain.stage3.acquisition.java_production import (
    run_java_acquisition_pipeline,
    seal_java_production_output,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.java_production_evaluator import (
    evaluate_sealed_java_production,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    verify_compiled_java_production_standalone,
)
from ai_brain.stage3.acquisition.java_semantics import semantic_content_confusion
from ai_brain.stage3.acquisition.java_source_selector import (
    M344_PRIOR_CORPUS_DENYLIST_MANIFEST_HASH,
    frozen_final_source_selector_policy,
    select_final_java_sources,
    selector_receipt,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.version import (
    UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
)
from ai_brain.stage3.providers.registry import ProviderRegistry

STAMP = "2026-09-03T00:00:00Z"
RUN_ID = "m344.untouched-final-java.v1"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _mapping(value: str) -> tuple[str, Path]:
    name, separator, raw_path = value.partition("=")
    if not separator or not name or not raw_path:
        raise argparse.ArgumentTypeError("expected FAMILY=PATH")
    return name, Path(raw_path)


def _load_prior_hashes(path: Path) -> tuple[str, ...]:
    row = json.loads(path.read_text(encoding="utf-8"))
    claimed = row.pop("manifest_hash", None)
    if (
        content_hash(row) != claimed
        or claimed != M344_PRIOR_CORPUS_DENYLIST_MANIFEST_HASH
    ):
        raise ValueError("prior-corpus hash manifest is not the F13 frozen artifact")
    values = row.get("snapshot_bytes_hashes")
    if not isinstance(values, list) or not all(
        isinstance(value, str) and len(value) == 64 for value in values
    ):
        raise ValueError("invalid prior-corpus hash manifest")
    return tuple(sorted(set(values)))


def _census(batch) -> dict:
    callables = tuple(
        item
        for item in batch.source_index.declarations
        if item.member_kind in {"method", "constructor"}
    )
    overloads = Counter((item.receiver_type, item.member_name) for item in callables)
    return {
        "real_callable_source_file_count": len(
            {item.source_unit_id for item in callables}
        ),
        "real_callable_target_count": len(callables),
        "real_receiver_type_count": len({item.receiver_type for item in callables}),
        "real_package_count": len({item.package_name for item in callables}),
        "real_overload_group_count": sum(value > 1 for value in overloads.values()),
        "real_constructor_count": sum(
            item.member_kind == "constructor" for item in callables
        ),
        "real_generic_method_count": sum(
            bool(item.proposed_content.method_type_parameters)
            for item in batch.proposal_batch.proposals
        ),
        "real_throws_declaration_count": sum(
            bool(item.declared_exceptions) for item in callables
        ),
        "real_nested_member_target_count": sum(
            bool(item.nested_type_path) for item in callables
        ),
        "synthetic_target_count": 0,
    }


def _by_source_root(batch) -> tuple[dict, ...]:
    declarations = tuple(batch.source_index.declarations)
    result = []
    for family in sorted({Path(item.source_unit_id).parts[0] for item in declarations}):
        values = tuple(
            item
            for item in declarations
            if Path(item.source_unit_id).parts[0] == family
        )
        result.append(
            {
                "family_id": family,
                "source_file_count": len({item.source_unit_id for item in values}),
                "callable_target_count": len(values),
                "trusted_target_count": sum(
                    decision.final_state.value == "trusted"
                    for decision in batch.decisions
                    if decision.parser_node_id in {item.node_id for item in values}
                ),
            }
        )
    return tuple(result)


def _stratified_metrics(batch, goldens, sealed, grouping: str) -> tuple[dict, ...]:
    if grouping == "source_root":
        group = lambda item: Path(item.source_unit_id).parts[0]
        row_group = lambda item: Path(item["source_unit_id"]).parts[0]
    elif grouping == "construct":
        group = lambda item: item.member_kind
        row_group = lambda item: item["member_kind"]
    else:
        raise ValueError("unknown metric grouping")
    rows = tuple(sealed["candidate_rows"])
    result = []
    for key in sorted({group(item) for item in goldens.goldens}):
        expected = tuple(item for item in goldens.goldens if group(item) == key)
        actual = tuple(item for item in rows if row_group(item) == key)
        expected_locations = {
            (
                item.document_bytes_hash,
                item.source_unit_id,
                item.start_offset,
                item.end_offset,
            )
            for item in expected
        }
        actual_locations = {
            (
                item["document_bytes_hash"],
                item["source_unit_id"],
                item["start_offset"],
                item["end_offset"],
            )
            for item in actual
        }
        expected_trusted = {
            item.golden_id for item in expected if item.expected_supported
        }
        golden_by_location = {
            (
                item.document_bytes_hash,
                item.source_unit_id,
                item.start_offset,
                item.end_offset,
            ): item
            for item in expected
        }
        actual_trusted = {
            golden_by_location[location].golden_id
            for item in actual
            if item["production_trust_state"] == "trusted"
            and (
                location := (
                    item["document_bytes_hash"],
                    item["source_unit_id"],
                    item["start_offset"],
                    item["end_offset"],
                )
            )
            in golden_by_location
        }
        subset = type("GoldenSubset", (), {"goldens": expected})()
        declarations = tuple(
            item
            for item in batch.source_index.declarations
            if (
                Path(item.source_unit_id).parts[0]
                if grouping == "source_root"
                else item.member_kind
            )
            == key
        )
        node_ids = {item.node_id for item in declarations}
        bindings = tuple(
            item
            for item in batch.proposal_batch.bindings
            if item.parser_node_id in node_ids
        )
        proposal_ids = {item.proposal_id for item in bindings}
        proposal_batch = replace(
            batch.proposal_batch,
            proposals=tuple(
                item
                for item in batch.proposal_batch.proposals
                if item.proposal_id in proposal_ids
            ),
            bindings=bindings,
        )
        source_index = replace(batch.source_index, declarations=declarations)
        result.append(
            {
                "group": key,
                "target_count": len(expected),
                "location": asdict(
                    source_location_confusion(expected_locations, actual_locations)
                ),
                "semantic": asdict(
                    semantic_content_confusion(
                        subset,
                        proposal_batch,
                        source_index,
                        batch.decisions,
                    )
                ),
                "trust": asdict(
                    automatic_trust_confusion(
                        expected_trusted,
                        actual_trusted,
                        {item.golden_id for item in expected},
                    )
                ),
            }
        )
    return tuple(result)


def _archive_receipts(archives, policy) -> tuple[dict, ...]:
    families = {item.family_id: item for item in policy.families}
    if {name for name, _path in archives} != set(families) & {
        name for name, _path in archives
    }:
        raise ValueError("archive receipt contains an unknown family")
    values = []
    for name, path in sorted(archives):
        family = families[name]
        with zipfile.ZipFile(path.resolve(strict=True)) as archive:
            licenses = tuple(
                sorted(
                    item
                    for item in archive.namelist()
                    if Path(item).name.casefold() in {"license", "license.txt"}
                )
            )
            if not licenses:
                raise ValueError("source archive has no license text")
            license_bytes = archive.read(licenses[0])
            if b"Apache License" not in license_bytes:
                raise ValueError("source archive license is not Apache-2.0 text")
        body = {
            "family_id": name,
            "version": family.version,
            "source_archive_url": family.source_archive_url,
            "source_archive_sha256": bytes_hash(path.resolve(strict=True).read_bytes()),
            "license_spdx": family.license_spdx,
            "license_archive_path": licenses[0],
            "license_bytes_hash": bytes_hash(license_bytes),
        }
        values.append({**body, "receipt_hash": content_hash(body)})
    return tuple(values)


def _copy_selected(selected, roots, target: Path) -> tuple[Path, ...]:
    root_map = {name: path.resolve(strict=True) for name, path in roots}
    copied = []
    for path in selected:
        matches = tuple(
            (name, root)
            for name, root in root_map.items()
            if path.resolve().is_relative_to(root)
        )
        if len(matches) != 1:
            raise ValueError("selected source root is ambiguous")
        name, root = matches[0]
        destination = target / name / path.resolve().relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
        copied.append(destination)
    return tuple(copied)


def _approve_and_install(pack, output: Path):
    validation = validate_pack(pack)
    verify_pack_evaluation(pack)
    provider_registry = ProviderRegistry.build(output, ())
    capability_registry = CapabilityRegistry.build((), provider_registry)
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
        policy_version="m344.oracle-free-java-release.v1",
        timestamp=STAMP,
    )
    registry = InstalledDomainRegistry.initialize(
        output / "installed_registry",
        capability_registry=capability_registry,
        provider_registry=provider_registry,
        created_at=STAMP,
    )
    installed = registry.install(
        pack,
        approval,
        (),
        installed_at=STAMP,
    )
    registry.verify(require_current_authority=True)
    return approval, installed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-root", type=_mapping, action="append", required=True)
    parser.add_argument(
        "--source-archive", type=_mapping, action="append", required=True
    )
    parser.add_argument("--prior-hash-manifest", type=Path, required=True)
    parser.add_argument("--f13-sha", required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    if args.output.exists() or args.work_root.exists():
        raise FileExistsError("fresh Java output/work root already exists")
    if len(args.family_root) < 2:
        raise ValueError("final run requires at least two independent source roots")
    if {item[0] for item in args.family_root} != {
        item[0] for item in args.source_archive
    }:
        raise ValueError(
            "source roots and archive receipts must name the same families"
        )
    prior_hashes = _load_prior_hashes(args.prior_hash_manifest)
    policy = frozen_final_source_selector_policy(
        prior_corpus_hash_denylist=prior_hashes
    )
    selected = select_final_java_sources(
        tuple(args.family_root), f13_sha=args.f13_sha, policy=policy
    )
    receipt = selector_receipt(policy, selected, tuple(args.family_root), args.f13_sha)
    archives = _archive_receipts(args.source_archive, policy)
    args.work_root.mkdir(parents=True)
    source_root = args.work_root / "selected-source"
    copied = _copy_selected(selected, tuple(args.family_root), source_root)
    current_hashes = {bytes_hash(path.read_bytes()) for path in copied}
    overlap = tuple(sorted(current_hashes & set(prior_hashes)))
    if overlap:
        raise ValueError("final source overlaps a prior/development corpus")

    with tempfile.TemporaryDirectory(prefix="m344-final-production-") as temporary:
        temporary_root = Path(temporary)
        store = AcquisitionStore.open_or_initialize(temporary_root / "store")
        bundle = ingest_bundle(
            copied,
            bundle_id="m344-final-java",
            domain_tags=("java-api",),
            imported_at=STAMP,
            store=store,
            source_root=source_root,
        )
        with (
            EnforcedProcessAudit(()) as process_audit,
            EnforcedJavaProductionFileAudit() as file_audit,
        ):
            batch = run_java_acquisition_pipeline(
                bundle, store, deterministic_run_id=RUN_ID
            )
        sealed = seal_java_production_output(batch)
        authorizations = verify_java_production_batch(batch, store)
        by_id = {item.trusted_proposal_id: item for item in authorizations}
        reviewed, approvals = [], []
        for proposal in batch.trusted_proposals:
            updated, _review, approval = review_proposal(
                proposal,
                reviewer_identity="m344-exact-candidate-process",
                reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
                decision=ReviewDecision.APPROVE,
                rationale="oracle-free source-entailment closure",
                timestamp=STAMP,
                trust_authorization=by_id[proposal.proposal_id],
            )
            reviewed.append(updated)
            approvals.append(approval)
        args.output.mkdir(parents=True)
        candidate_root = args.output / "candidate_pack"
        pack = compile_provisional_pack(
            bundle,
            batch.segmentation.segments,
            tuple(reviewed),
            tuple(approvals),
            candidate_root,
            domain_id="m344-final-java",
            production_trust_batch=batch,
            production_authorizations=authorizations,
            store=store,
        )
        replay = verify_compiled_java_production_standalone(candidate_root)
        production_audit = process_audit.report()
        file_access_audit = file_audit.report()
        _write(args.output / "production_output.json", sealed)
        _write(args.output / "production_process_audit.json", asdict(production_audit))
        _write(
            args.output / "production_file_access_audit.json", asdict(file_access_audit)
        )
        _write(args.output / "production_replay.json", replay)
        _write(args.output / "selector_receipt.json", receipt)
        _write(args.output / "source_acquisition_receipts.json", archives)
        _write(
            args.output / "source_overlap.json", {"intersection": overlap, "count": 0}
        )
        _write(args.output / "physical_census.json", _census(batch))
        _write(args.output / "by_source_root.json", _by_source_root(batch))
        _copy_selected(
            selected, tuple(args.family_root), args.output / "source_snapshots"
        )

        # Evaluation authority is created only after production and pack sealing.
        oracle_root = args.output / "oracle"
        if oracle_root.exists():
            raise ValueError("evaluation authority existed before production seal")
        command = [
            sys.executable,
            str(project / "scripts/m343_author_semantic_goldens.py"),
            "--corpus",
            str(args.output / "source_snapshots"),
            "--helper",
            str(project / "tools/m343_java_oracle/JavaSemanticProposalOracle.java"),
            "--javac",
            str(args.javac.resolve(strict=True)),
            "--java",
            str(args.java.resolve(strict=True)),
            "--output",
            str(oracle_root),
            "--parser-common-hash",
            batch.parser_common_artifact.manifest_hash,
            "--evidence-policy-hash",
            batch.evidence_policy.manifest_hash,
            "--disjoint-hash-manifest",
            str(args.prior_hash_manifest.resolve(strict=True)),
            "--authority-id",
            "m344-fresh-java-evaluation-authority",
            "--sealing-ref",
            args.f13_sha,
            "--authority-purpose",
            "post-production-independent-evaluation",
            "--config-id",
            "m344.fresh-java-evaluation.v1",
        ]
        for family, _root in args.family_root:
            command.extend(("--real-prefix", family))
        subprocess.run(command, check=True)
        goldens = load_java_golden_manifest(oracle_root / "semantic_goldens.json")
        evaluation = evaluate_sealed_java_production(sealed, batch, goldens)
        _write(args.output / "evaluation_report.json", asdict(evaluation))
        _write(
            args.output / "metrics_by_source_root.json",
            _stratified_metrics(batch, goldens, sealed, "source_root"),
        )
        _write(
            args.output / "metrics_by_construct.json",
            _stratified_metrics(batch, goldens, sealed, "construct"),
        )
        order_body = {
            "schema_version": 1,
            "steps": (
                ("SOURCE_SELECTED", receipt["receipt_hash"]),
                ("PRODUCTION_SEALED", sealed["production_output_hash"]),
                ("CANDIDATE_PACK_SEALED", pack.manifest.pack_content_hash),
                ("ORACLE_FREE_REPLAY_VERIFIED", replay["artifact_hash"]),
                ("INDEPENDENT_ORACLE_SEALED", goldens.manifest_hash),
                ("IMMUTABLE_OUTPUT_COMPARED", evaluation.report_hash),
            ),
        }
        _write(
            args.output / "execution_order.json",
            {**order_body, "receipt_hash": content_hash(order_body)},
        )
        install_allowed = evaluation.passed and evaluation.wrong_trusted_count == 0
        if install_allowed:
            approval, installed = _approve_and_install(pack, args.output)
            _write(args.output / "pack_approval.json", asdict(approval))
            _write(args.output / "installation_receipt.json", asdict(installed))
        summary_body = {
            "schema_version": 1,
            "platform": args.platform,
            "f13_sha": args.f13_sha,
            "selector_receipt_hash": receipt["receipt_hash"],
            "source_file_count": len(copied),
            "source_hash_overlap_count": len(overlap),
            "production_output_hash": sealed["production_output_hash"],
            "production_batch_hash": batch.batch_hash,
            "candidate_pack_hash": pack.manifest.pack_content_hash,
            "replay_status": replay["status"],
            "golden_manifest_hash": goldens.manifest_hash,
            "evaluation_report_hash": evaluation.report_hash,
            "evaluation_passed": evaluation.passed,
            "wrong_trusted_count": evaluation.wrong_trusted_count,
            "installation_performed": install_allowed,
            "python_version": sys.version,
            "torch_imported": "torch" in sys.modules,
            "fact_memory_writes": 0,
            "rule_memory_writes": 0,
            "skill_registry_writes": 0,
            "provider_registry_mutation_before_approval": 0,
            "domain_registry_mutation_before_approval": 0,
        }
        _write(
            args.output / "summary.json",
            {**summary_body, "summary_hash": content_hash(summary_body)},
        )


if __name__ == "__main__":
    main()
