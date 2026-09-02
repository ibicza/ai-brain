"""Content-addressed, fresh-process replay of compiled Java trust evidence."""

from __future__ import annotations

import base64
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_pipeline import (
    TrustBoundProposalBatch,
    run_java_trust_pipeline,
    verify_trust_bound_batch,
)
from ai_brain.stage3.acquisition.java_seal import (
    GoldenSealReceipt,
    load_java_trust_evaluation_config,
)
from ai_brain.stage3.acquisition.models import AcquisitionManifest, SourceBundle
from ai_brain.stage3.acquisition.persistence import AcquisitionStore, _document
from ai_brain.stage3.domains.loader import load_pack

JAVA_REPLAY_SCHEMA_VERSION = 1
JAVA_REPLAY_FILENAME = "java_evidence_closure.json"
JAVA_REPLAY_DEPENDENCY_PREFIX = "java-evidence-closure."


def build_java_replay_artifact(batch: TrustBoundProposalBatch, store, source_bindings):
    blobs = tuple(
        (
            document.bytes_hash,
            base64.b64encode(store.get_blob(document.bytes_hash)).decode("ascii"),
        )
        for document in sorted(batch.bundle.documents, key=lambda item: item.bytes_hash)
    )
    body = {
        "schema_version": JAVA_REPLAY_SCHEMA_VERSION,
        "deterministic_run_id": batch.closure.deterministic_run_id,
        "bundle": asdict(batch.bundle),
        "source_blobs": blobs,
        "golden_manifest": asdict(batch.golden_manifest),
        "golden_seal": asdict(batch.golden_seal),
        "trust_closure": asdict(batch.closure),
        "field_evidence": asdict(batch.field_evidence),
        "field_evidence_manifest_hash": batch.field_evidence.manifest_hash,
        "evidence_policy": asdict(batch.evidence_policy),
        "evidence_policy_manifest_hash": batch.evidence_policy.manifest_hash,
        "source_index": asdict(batch.source_index),
        "source_index_hash": batch.source_index.index_hash,
        "type_universe_manifest_hash": batch.source_index.type_universe_manifest_hash,
        "proposal_manifest_hash": batch.proposal_batch.proposal_manifest_hash,
        "proposal_batch": asdict(batch.proposal_batch),
        "trust_decisions": tuple(asdict(item) for item in batch.decisions),
        "trusted_proposals": tuple(
            (item.proposal_id, item.proposal_hash) for item in batch.trusted_proposals
        ),
        "parser_common_artifact": asdict(batch.parser_common_artifact),
        "compiled_source_bindings": tuple(asdict(item) for item in source_bindings),
    }
    return {**body, "artifact_hash": content_hash(body)}


def verify_compiled_java_evidence_standalone(pack_root: Path) -> dict[str, object]:
    pack = load_pack(pack_root)
    path = pack_root / JAVA_REPLAY_FILENAME
    row = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict)
    claimed = row.pop("artifact_hash")
    if content_hash(row) != claimed:
        raise ValueError("Java replay artifact hash mismatch")
    expected_dependency = JAVA_REPLAY_DEPENDENCY_PREFIX + claimed
    if pack.manifest.dependency_packs != (expected_dependency,):
        raise ValueError("pack does not bind exact Java replay artifact")
    if row["schema_version"] != JAVA_REPLAY_SCHEMA_VERSION:
        raise ValueError("unsupported Java replay schema")
    with tempfile.TemporaryDirectory(prefix="m342-replay-") as temporary:
        root = Path(temporary)
        store = AcquisitionStore.open_or_initialize(root / "store")
        for digest, encoded in row["source_blobs"]:
            store.put_blob(
                base64.b64decode(encoded, validate=True), expected_hash=digest
            )
        bundle = _bundle(row["bundle"])
        golden_path = root / "semantic_goldens.json"
        golden_path.write_text(
            canonical_json(row["golden_manifest"]) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        goldens = load_java_golden_manifest(golden_path)
        seal_row = row["golden_seal"]
        seal = GoldenSealReceipt(**seal_row)
        config = load_java_trust_evaluation_config()
        batch = run_java_trust_pipeline(
            bundle,
            store,
            goldens,
            seal,
            config,
            deterministic_run_id=row["deterministic_run_id"],
        )
        authorizations = verify_trust_bound_batch(
            batch, store, seal, batch.parser_common_artifact
        )
    expected = {
        "trust_closure": asdict(batch.closure),
        "field_evidence": asdict(batch.field_evidence),
        "field_evidence_manifest_hash": batch.field_evidence.manifest_hash,
        "evidence_policy": asdict(batch.evidence_policy),
        "evidence_policy_manifest_hash": batch.evidence_policy.manifest_hash,
        "source_index": asdict(batch.source_index),
        "source_index_hash": batch.source_index.index_hash,
        "type_universe_manifest_hash": batch.source_index.type_universe_manifest_hash,
        "proposal_manifest_hash": batch.proposal_batch.proposal_manifest_hash,
        "proposal_batch": asdict(batch.proposal_batch),
        "trust_decisions": [asdict(item) for item in batch.decisions],
        "trusted_proposals": [
            [item.proposal_id, item.proposal_hash] for item in batch.trusted_proposals
        ],
        "parser_common_artifact": asdict(batch.parser_common_artifact),
        "compiled_source_bindings": [asdict(item) for item in pack.source_bindings],
    }
    for key, value in expected.items():
        if canonical_json(row[key]) != canonical_json(value):
            raise ValueError(f"standalone Java replay mismatch: {key}")
    return {
        "status": "PASS",
        "artifact_hash": claimed,
        "trusted_proposal_count": len(batch.trusted_proposals),
        "authorization_count": len(authorizations),
        "evidence_count": batch.field_evidence.evidence_count,
        "source_blob_count": len(row["source_blobs"]),
    }


def _bundle(row):
    documents = tuple(_document(item) for item in row["documents"])
    manifest_row = row["manifest"]
    manifest = AcquisitionManifest(
        **{
            **manifest_row,
            "document_hashes": tuple(manifest_row["document_hashes"]),
        }
    )
    return SourceBundle(
        **{
            **row,
            "domain_tags": tuple(row["domain_tags"]),
            "documents": documents,
            "manifest": manifest,
        }
    )


def _strict(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key in Java replay artifact")
        result[key] = value
    return result
