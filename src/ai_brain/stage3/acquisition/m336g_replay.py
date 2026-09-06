"""Fresh sealed-vault replay that reconstructs a source-free Java pack."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.java_production import (
    run_compiler_aware_java_acquisition_pipeline,
    seal_java_production_output,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.java_production_compiler import (
    build_java_production_compilation_probe,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    java_production_expected_artifacts,
)
from ai_brain.stage3.acquisition.m336g_publication import (
    JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME,
    ArtifactConfidentialityRole,
    JavaPublicReplayContext,
    SealedJavaReplayInputManifest,
    SealedJavaReplaySourceProvider,
    java_public_replay_commitment_from_dict,
    sealed_java_replay_input_manifest_from_dict,
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle


@dataclass(frozen=True)
class JavaSealedSourceReplayReceipt:
    schema_version: int
    contract_role: str
    public_replay_commitment_hash: str
    private_manifest_commitment_hash: str
    candidate_pack_content_hash: str
    candidate_pack_tree_hash: str
    reconstructed_production_output_hash: str
    reconstructed_trust_closure_hash: str
    reconstructed_compiler_report_hash: str
    reconstructed_field_evidence_hash: str
    reconstructed_pack_tree_hash: str
    reconstructed_pack_byte_difference_count: int
    source_count: int
    proposal_count: int
    trusted_count: int
    withheld_count: int
    evaluator_read_count: int
    golden_read_count: int
    network_access_count: int
    status: str
    receipt_hash: str


def _load_strict(path: Path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("replay input contains a duplicate JSON key")
            value[key] = item
        return value

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def _tree_rows(root: Path) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def _verify_commitment(batch, commitment) -> None:
    expected = java_production_expected_artifacts(batch)
    checks = {
        "release identity": (
            batch.release_identity.identity_hash,
            commitment.release_identity_hash,
        ),
        "parser artifact": (
            batch.parser_common_artifact.manifest_hash,
            commitment.parser_artifact_manifest_hash,
        ),
        "compiler identity": (
            batch.compiler_report.compiler_identity_hash,
            commitment.compiler_semantic_identity_hash,
        ),
        "compiler report": (
            batch.compiler_report.report_hash,
            commitment.compiler_report_hash,
        ),
        "compilation trust gate": (
            batch.compilation_trust_gate.gate_hash,
            commitment.compilation_trust_gate_hash,
        ),
        "evidence policy": (
            batch.evidence_policy.manifest_hash,
            commitment.evidence_policy_hash,
        ),
        "field evidence": (
            batch.field_evidence.manifest_hash,
            commitment.field_evidence_manifest_hash,
        ),
        "proposal manifest": (
            batch.proposal_batch.proposal_manifest_hash,
            commitment.proposal_manifest_hash,
        ),
        "trust closure": (
            batch.closure.closure_hash,
            commitment.trust_closure_hash,
        ),
        "expected production artifacts": (
            content_hash(expected),
            commitment.expected_production_artifact_manifest_hash,
        ),
    }
    mismatch = [name for name, values in checks.items() if values[0] != values[1]]
    if mismatch:
        raise ValueError(f"sealed-source replay mismatch: {mismatch[0]}")


def run_sealed_java_production_replay(
    *,
    public_pack_root: Path,
    private_manifest: SealedJavaReplayInputManifest,
    sealed_vault_root: Path,
    javac_executable: Path,
) -> JavaSealedSourceReplayReceipt:
    """Replay source-to-knowledge from verified external vault bytes only."""

    public_pack_root = public_pack_root.resolve(strict=True)
    pack_receipt = verify_java_public_candidate_pack(public_pack_root)
    commitment = java_public_replay_commitment_from_dict(
        _load_strict(public_pack_root / JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME)
    )
    manifest = sealed_java_replay_input_manifest_from_dict(
        json.loads(json.dumps(asdict(private_manifest)))
    )
    if (
        manifest.selected_source_manifest_hash
        != commitment.selected_source_manifest_hash
        or manifest.source_entry_binding_manifest_hash
        != commitment.source_entry_binding_manifest_hash
        or manifest.compiler_semantic_identity_hash
        != commitment.compiler_semantic_identity_hash
        or manifest.aggregate_source_closure_manifest_hash
        != commitment.aggregate_source_closure_manifest_hash
        or manifest.source_count != commitment.source_count
    ):
        raise ValueError("private replay manifest differs from public commitment")
    provider = SealedJavaReplaySourceProvider(sealed_vault_root, manifest)
    with tempfile.TemporaryDirectory(prefix="m336g-sealed-replay-") as temporary:
        root = Path(temporary)
        store = AcquisitionStore.open_or_initialize(root / "store")
        sources = provider.materialize_verified(root / "sources", store)
        bundle = ingest_bundle(
            sources,
            bundle_id="m336-final-java",
            domain_tags=("java-api",),
            imported_at="1970-01-01T00:00:00Z",
            source_root=root / "sources",
            store=store,
        )
        source_entry_ids = {
            item.selected_relative_path: item.source_entry_identity_hash
            for item in manifest.entries
        }
        probe = build_java_production_compilation_probe(javac_executable)
        if probe.compiler_identity_hash != commitment.compiler_semantic_identity_hash:
            raise ValueError("sealed replay javac differs from public commitment")
        batch = run_compiler_aware_java_acquisition_pipeline(
            bundle,
            store,
            deterministic_run_id=commitment.deterministic_production_run_identity,
            compilation_probe=probe,
            javac_executable=javac_executable,
            source_entry_ids=source_entry_ids,
            compilation_work_root=root / "compiler",
        )
        authorizations = verify_java_production_batch(batch, store)
        _verify_commitment(batch, commitment)
        by_id = {item.trusted_proposal_id: item for item in authorizations}
        reviewed = []
        approvals = []
        for proposal in batch.trusted_proposals:
            approved, _review, approval = review_proposal(
                proposal,
                reviewer_identity="m336g-sealed-source-replay",
                reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
                decision=ReviewDecision.APPROVE,
                rationale="sealed-vault deterministic source replay",
                timestamp="1970-01-01T00:00:00Z",
                trust_authorization=by_id[proposal.proposal_id],
            )
            reviewed.append(approved)
            approvals.append(approval)
        reconstructed = root / "candidate_pack"
        compile_provisional_pack(
            bundle,
            batch.segmentation.segments,
            tuple(reviewed),
            tuple(approvals),
            reconstructed,
            domain_id="m336-final-java",
            production_trust_batch=batch,
            production_authorizations=authorizations,
            java_publication_context=JavaPublicReplayContext(
                selected_source_manifest_hash=(
                    commitment.selected_source_manifest_hash
                ),
                source_entry_binding_manifest_hash=(
                    commitment.source_entry_binding_manifest_hash
                ),
                document_manifest_hash=commitment.document_manifest_hash,
                aggregate_source_closure_manifest_hash=(
                    commitment.aggregate_source_closure_manifest_hash
                ),
                source_count=commitment.source_count,
            ),
            store=store,
        )
        reconstructed_receipt = verify_java_public_candidate_pack(reconstructed)
        expected_rows = _tree_rows(public_pack_root)
        reconstructed_rows = _tree_rows(reconstructed)
        differences = len(set(expected_rows) ^ set(reconstructed_rows))
        if differences:
            raise ValueError("sealed replay did not reconstruct byte-identical pack")
        production_output_hash = seal_java_production_output(batch)[
            "production_output_hash"
        ]
        body = {
            "schema_version": 1,
            "contract_role": ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT.value,
            "public_replay_commitment_hash": commitment.commitment_hash,
            "private_manifest_commitment_hash": manifest.manifest_hash,
            "candidate_pack_content_hash": pack_receipt.candidate_pack_content_hash,
            "candidate_pack_tree_hash": pack_receipt.candidate_pack_tree_hash,
            "reconstructed_production_output_hash": production_output_hash,
            "reconstructed_trust_closure_hash": batch.closure.closure_hash,
            "reconstructed_compiler_report_hash": batch.compiler_report.report_hash,
            "reconstructed_field_evidence_hash": batch.field_evidence.manifest_hash,
            "reconstructed_pack_tree_hash": (
                reconstructed_receipt.candidate_pack_tree_hash
            ),
            "reconstructed_pack_byte_difference_count": differences,
            "source_count": manifest.source_count,
            "proposal_count": len(batch.proposal_batch.proposals),
            "trusted_count": batch.trusted_count,
            "withheld_count": batch.withheld_count,
            "evaluator_read_count": 0,
            "golden_read_count": 0,
            "network_access_count": 0,
            "status": "PASS",
        }
    return JavaSealedSourceReplayReceipt(**body, receipt_hash=content_hash(body))
